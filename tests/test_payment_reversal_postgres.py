"""Synthetic signed Stripe reversal -> real PostgreSQL tombstone integration."""
import hashlib
import hmac
import json
import os
import unittest
from protection.checkout_bindings import BINDING_SCHEMA_SQL, PostgresCheckoutBindings
from protection.entitlement_store import PricePlan
from protection.postgres_entitlement_store import SCHEMA_SQL, PostgresEntitlementStore, psycopg_connect_factory
from protection.stripe_entitlements import PaidCheckout, WebhookRejected
from protection.payment_reversal_adapter import process_verified_payment_reversal


@unittest.skipUnless(os.getenv("PRIVI_TEST_DATABASE_URL"), "Disposable PostgreSQL only")
class PaymentReversalIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.getenv("PRIVI_TEST_ALLOW_SCHEMA_RESET") != "ephemeral-ci-only":
            raise RuntimeError("Refusing to touch non-disposable database")
        cls.connect = staticmethod(psycopg_connect_factory(os.environ["PRIVI_TEST_DATABASE_URL"]))
        with cls.connect() as conn:
            conn.execute(SCHEMA_SQL)
            conn.execute(BINDING_SCHEMA_SQL)
        cls.store = PostgresEntitlementStore(cls.connect)
        cls.bindings = PostgresCheckoutBindings(cls.connect)

    def setUp(self):
        with self.connect() as conn:
            conn.execute("TRUNCATE TABLE privi_processed_checkouts, privi_blocked_checkouts, privi_checkout_buyers")
        self.secret = "whsec_fixture_only"
        self.now = 1784480000
        self.purchase = PaidCheckout("evt_paid", "cs_rev", "cus_1", "buyer_1", "price_pro", 3500, "usd")
        self.plan = PricePlan("all_services", 3500)
        self.bindings.bind("cs_rev", "buyer_1")
        self.charge = {
            "id": "ch_rev", "object": "charge", "payment_intent": "pi_rev",
            "amount": 3500, "amount_refunded": 3500, "currency": "usd", "disputed": False,
        }
        self.intent = {
            "id": "pi_rev", "object": "payment_intent", "latest_charge": "ch_rev",
            "customer": "cus_1", "amount": 3500, "currency": "usd",
        }
        self.session = {
            "id": "cs_rev", "object": "checkout.session", "payment_intent": "pi_rev",
            "mode": "payment", "customer": "cus_1", "client_reference_id": "buyer_1",
            "amount_total": 3500, "currency": "usd",
        }
        self.calls = []

    def deliver(self, kind="charge.refunded", *, bad=False, event_object=None):
        if event_object is None:
            event_object = (
                {"object": "charge", "id": "ch_rev"} if kind == "charge.refunded"
                else {"object": "dispute", "id": "dp_rev", "charge": "ch_rev"}
            )
        event = {"id": "evt_reversal", "type": kind, "data": {"object": event_object}}
        body = json.dumps(event).encode()
        digest = hmac.new(self.secret.encode(), str(self.now).encode() + b"." + body, hashlib.sha256).hexdigest()
        if bad:
            digest = "0"*64
        def charge(key):
            self.calls.append(("charge", key))
            return self.charge
        def intent(key):
            self.calls.append(("intent", key))
            return self.intent
        def sessions(key):
            self.calls.append(("sessions", key))
            return {"has_more": False, "data": [self.session]}
        return process_verified_payment_reversal(
            payload=body, signature=f"t={self.now},v1={digest}",
            webhook_secret=self.secret, bindings=self.bindings, store=self.store,
            retrieve_charge=charge, retrieve_payment_intent=intent,
            list_checkout_sessions=sessions, clock=lambda: self.now,
        )

    def test_full_refund_before_grant_blocks_later_checkout(self):
        self.assertEqual(self.deliver(), "blocked")
        self.assertFalse(self.store.grant(self.purchase, "buyer_1", self.plan))
        self.assertFalse(self.store.authorized("buyer_1", "guard"))
        self.assertEqual(self.deliver(), "already_blocked")

    def test_dispute_revokes_existing_entitlement(self):
        self.assertTrue(self.store.grant(self.purchase, "buyer_1", self.plan))
        self.charge["disputed"] = True
        self.charge["amount_refunded"] = 0
        self.assertEqual(self.deliver("charge.dispute.created"), "blocked")
        self.assertFalse(self.store.authorized("buyer_1", "guard"))
        self.assertFalse(self.store.grant(self.purchase, "buyer_1", self.plan))

    def test_partial_refund_requires_review_not_block(self):
        self.store.grant(self.purchase, "buyer_1", self.plan)
        self.charge["amount_refunded"] = 300
        self.assertEqual(self.deliver(), "partial_refund")
        self.assertTrue(self.store.authorized("buyer_1", "guard"))

    def test_signature_failure_does_not_fetch_or_revoke(self):
        self.store.grant(self.purchase, "buyer_1", self.plan)
        with self.assertRaises(WebhookRejected):
            self.deliver(bad=True)
        self.assertEqual(self.calls, [])
        self.assertTrue(self.store.authorized("buyer_1", "guard"))

    def test_account_or_provider_mismatch_denies_block(self):
        self.store.grant(self.purchase, "buyer_1", self.plan)
        for record, field, wrong in [
            (self.session, "client_reference_id", "other"),
            (self.session, "payment_intent", "pi_other"),
            (self.intent, "customer", "cus_other"),
            (self.charge, "amount", True),
        ]:
            with self.subTest(field=field):
                original = record[field]
                record[field] = wrong
                with self.assertRaises(ValueError):
                    self.deliver()
                self.assertTrue(self.store.authorized("buyer_1", "guard"))
                record[field] = original

    def test_unknown_or_ambiguous_checkout_rejected(self):
        self.session["id"] = "cs_other"
        with self.assertRaises(ValueError):
            self.deliver()
        self.assertFalse(self.store.purchase_for_session("cs_other"))

    def test_unrelated_event_ignored_without_fetch(self):
        self.assertEqual(self.deliver("customer.created", event_object={"object": "customer"}), "ignored")
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
