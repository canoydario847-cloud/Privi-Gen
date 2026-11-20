"""Real PostgreSQL refund/dispute reconciliation tests (disposable CI DB)."""
import os
import unittest
from protection.entitlement_store import PricePlan
from protection.postgres_entitlement_store import (
    SCHEMA_SQL, PostgresEntitlementStore, psycopg_connect_factory,
)
from protection.refund_reconciliation import reconcile_checkout
from protection.stripe_entitlements import PaidCheckout


@unittest.skipUnless(os.getenv("PRIVI_TEST_DATABASE_URL"), "Disposable PostgreSQL required")
class ReconcilePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.getenv("PRIVI_TEST_ALLOW_SCHEMA_RESET") != "ephemeral-ci-only":
            raise RuntimeError("Never reset a shared database")
        cls.connect = staticmethod(psycopg_connect_factory(os.environ["PRIVI_TEST_DATABASE_URL"]))
        with cls.connect() as conn:
            conn.execute(SCHEMA_SQL)
        cls.store = PostgresEntitlementStore(cls.connect)

    def setUp(self):
        with self.connect() as conn:
            conn.execute("TRUNCATE TABLE privi_processed_checkouts")
        self.purchase = PaidCheckout("evt_refund", "cs_refund", "cus_1", "buyer_1",
                                     "price_pro", 3500, "usd")
        self.store.grant(self.purchase, "buyer_1", PricePlan("all_services", 3500))
        self.session = {
            "object": "checkout.session", "id": "cs_refund",
            "mode": "payment", "customer": "cus_1", "client_reference_id": "buyer_1",
            "amount_total": 3500, "currency": "usd", "payment_intent": "pi_refund",
        }
        self.intent = {
            "object": "payment_intent", "id": "pi_refund", "customer": "cus_1",
            "amount": 3500, "currency": "usd", "latest_charge": "ch_refund",
        }
        self.charge = {
            "object": "charge", "id": "ch_refund", "payment_intent": "pi_refund",
            "amount": 3500, "currency": "usd", "amount_refunded": 0,
            "disputed": False,
        }
        self.calls = []

    def reconcile(self, session="cs_refund"):
        def get_session(key):
            self.calls.append(("session", key))
            return self.session
        def get_intent(key):
            self.calls.append(("intent", key))
            return self.intent
        def get_charge(key):
            self.calls.append(("charge", key))
            return self.charge
        return reconcile_checkout(
            session, store=self.store, retrieve_session=get_session,
            retrieve_payment_intent=get_intent, retrieve_charge=get_charge,
        )

    def test_active_and_partial_refund_keep_access(self):
        self.assertEqual(self.reconcile(), "active")
        self.charge["amount_refunded"] = 900
        self.assertEqual(self.reconcile(), "partial_refund")
        self.assertTrue(self.store.authorized("buyer_1", "guard"))

    def test_full_refund_revokes_and_cannot_be_replayed(self):
        self.charge["amount_refunded"] = 3500
        self.assertEqual(self.reconcile(), "revoked")
        self.assertFalse(self.store.authorized("buyer_1", "guard"))
        self.assertEqual(self.reconcile(), "already_revoked")
        self.assertFalse(self.store.grant(self.purchase, "buyer_1", PricePlan("all_services", 3500)))
        self.assertFalse(self.store.authorized("buyer_1", "guard"))

    def test_dispute_revokes_even_if_no_refund_yet(self):
        self.charge["disputed"] = True
        self.assertEqual(self.reconcile(), "revoked")
        self.assertFalse(self.store.authorized("buyer_1", "guard"))

    def test_mismatched_payment_chain_fails_closed(self):
        for data, field, wrong in [
            (self.session, "client_reference_id", "someone_else"),
            (self.session, "payment_intent", "pi_other"),
            (self.intent, "customer", "cus_other"),
            (self.intent, "amount", True),
            (self.charge, "payment_intent", "pi_other"),
            (self.charge, "currency", "eur"),
            (self.charge, "amount_refunded", True),
            (self.charge, "amount_refunded", 4000),
            (self.charge, "disputed", "true"),
        ]:
            with self.subTest(field=field, wrong=wrong):
                old = data[field]
                data[field] = wrong
                with self.assertRaises(ValueError):
                    self.reconcile()
                self.assertTrue(self.store.authorized("buyer_1", "guard"))
                data[field] = old

    def test_unknown_session_does_not_fetch_provider(self):
        self.assertEqual(self.reconcile("cs_unknown"), "not_found")
        self.assertEqual(self.calls, [])
        self.assertTrue(self.store.authorized("buyer_1", "guard"))


if __name__ == "__main__":
    unittest.main()
