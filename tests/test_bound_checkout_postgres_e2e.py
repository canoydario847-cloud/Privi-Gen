"""Real PostgreSQL integration of signed Stripe checkout, buyer binding, entitlements.

Uses a disposable PostgreSQL CI service. This file is destructive only for
tables in the ephemeral test database; never run against production.
"""
import hashlib
import hmac
import json
import os
import unittest

from protection.checkout_bindings import BINDING_SCHEMA_SQL, PostgresCheckoutBindings
from protection.checkout_fulfillment import fulfill_bound_checkout
from protection.entitlement_store import PricePlan
from protection.postgres_entitlement_store import (
    SCHEMA_SQL, PostgresEntitlementStore, psycopg_connect_factory,
)
from protection.stripe_entitlements import WebhookRejected


@unittest.skipUnless(os.getenv("PRIVI_TEST_DATABASE_URL"), "Disposable PostgreSQL required")
class BoundCheckoutEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.getenv("PRIVI_TEST_ALLOW_SCHEMA_RESET") != "ephemeral-ci-only":
            raise RuntimeError("Explicit disposable database confirmation required")
        cls.connect = staticmethod(psycopg_connect_factory(os.environ["PRIVI_TEST_DATABASE_URL"]))
        with cls.connect() as conn:
            conn.execute(SCHEMA_SQL)
            conn.execute(BINDING_SCHEMA_SQL)
        cls.bindings = PostgresCheckoutBindings(cls.connect)
        cls.store = PostgresEntitlementStore(cls.connect)

    def setUp(self):
        with self.connect() as conn:
            conn.execute("TRUNCATE TABLE privi_processed_checkouts, privi_checkout_buyers, privi_blocked_checkouts")
        self.secret = "whsec_disposable_fixture_only"
        self.now = 1784480000
        self.event = {
            "id": "evt_e2e",
            "type": "checkout.session.completed",
            "data": {"object": {"object": "checkout.session", "id": "cs_e2e"}},
        }
        self.session = {
            "id": "cs_e2e", "object": "checkout.session",
            "mode": "payment", "payment_status": "paid",
            "client_reference_id": "buyer_e2e", "customer": "cus_e2e",
            "amount_total": 3500, "currency": "usd",
        }
        self.lines = [{"quantity": 1, "price": {
            "id": "price_pro", "unit_amount": 3500, "currency": "usd",
        }}]
        self.prices = {
            "price_pro": PricePlan("all_services", 3500),
            "price_callproof": PricePlan("call_proof", 1999),
        }

    def deliver(self, *, bad_signature=False, session=None, lines=None):
        payload = json.dumps(self.event).encode()
        sig = hmac.new(
            self.secret.encode(),
            str(self.now).encode() + b"." + payload,
            hashlib.sha256,
        ).hexdigest()
        if bad_signature:
            sig = "0" * 64
        return fulfill_bound_checkout(
            payload=payload,
            signature=f"t={self.now},v1={sig}",
            webhook_secret=self.secret,
            verified_session=self.session if session is None else session,
            verified_line_items=self.lines if lines is None else lines,
            price_allowlist=self.prices,
            store=self.store,
            bindings=self.bindings,
            clock=lambda: self.now,
        )

    def test_verified_pro_purchase_replay_and_revocation(self):
        self.assertFalse(self.store.authorized("buyer_e2e", "guard"))
        self.assertTrue(self.bindings.bind("cs_e2e", "buyer_e2e"))
        self.assertTrue(self.deliver())
        self.assertTrue(self.store.authorized("buyer_e2e", "guard"))
        self.assertFalse(self.store.authorized("another_buyer", "guard"))
        self.assertFalse(self.deliver())
        self.assertTrue(self.store.revoke_session("cs_e2e"))
        self.assertFalse(self.deliver())
        self.assertFalse(self.store.authorized("buyer_e2e", "guard"))

    def test_unbound_checkout_does_not_grant(self):
        self.assertFalse(self.deliver())
        self.assertFalse(self.store.authorized("buyer_e2e", "guard"))

    def test_invalid_signature_rejected_even_for_unbound_checkout(self):
        with self.assertRaises(WebhookRejected):
            self.deliver(bad_signature=True)
        self.assertFalse(self.store.authorized("buyer_e2e", "guard"))

    def test_server_binding_mismatch_rejected(self):
        self.assertTrue(self.bindings.bind("cs_e2e", "different_buyer"))
        with self.assertRaises(ValueError):
            self.deliver()
        self.assertFalse(self.store.authorized("different_buyer", "guard"))
        self.assertFalse(self.store.authorized("buyer_e2e", "guard"))

    def test_single_service_is_not_pro(self):
        self.assertTrue(self.bindings.bind("cs_e2e", "buyer_e2e"))
        session = dict(self.session, amount_total=1999)
        lines = [{"quantity": 1, "price": {
            "id": "price_callproof", "unit_amount": 1999, "currency": "usd",
        }}]
        self.assertTrue(self.deliver(session=session, lines=lines))
        self.assertTrue(self.store.authorized("buyer_e2e", "call_proof"))
        self.assertFalse(self.store.authorized("buyer_e2e", "guard"))


if __name__ == "__main__":
    unittest.main()
