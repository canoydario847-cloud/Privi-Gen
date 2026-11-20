"""Real PostgreSQL + ASGI staging webhook integration tests.

This suite must run ONLY against the disposable GitHub Actions PostgreSQL
service: it creates tables and truncates test data. No real Stripe API calls.
"""
import asyncio
import hashlib
import hmac
import json
import os
import unittest

from protection.checkout_bindings import BINDING_SCHEMA_SQL, PostgresCheckoutBindings
from protection.entitlement_store import PricePlan
from protection.postgres_entitlement_store import (
    SCHEMA_SQL, PostgresEntitlementStore, psycopg_connect_factory,
)
from protection.staging_webhook_app import create_staging_webhook_app


@unittest.skipUnless(os.getenv("PRIVI_TEST_DATABASE_URL"), "Disposable PostgreSQL required")
class HTTPPostgresPaidAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.getenv("PRIVI_TEST_ALLOW_SCHEMA_RESET") != "ephemeral-ci-only":
            raise RuntimeError("Refusing to modify a non-disposable database")
        cls.connect = staticmethod(psycopg_connect_factory(os.environ["PRIVI_TEST_DATABASE_URL"]))
        with cls.connect() as conn:
            conn.execute(SCHEMA_SQL)
            conn.execute(BINDING_SCHEMA_SQL)
        cls.store = PostgresEntitlementStore(cls.connect)
        cls.bindings = PostgresCheckoutBindings(cls.connect)

    def setUp(self):
        with self.connect() as conn:
            conn.execute("TRUNCATE TABLE privi_processed_checkouts, privi_checkout_buyers, privi_blocked_checkouts")
        self.secret = "whsec_offline_http_fixture"
        self.now = 1784480000
        self.event = {
            "id": "evt_ci", "type": "checkout.session.completed",
            "data": {"object": {"object": "checkout.session", "id": "cs_ci"}},
        }
        self.session = {
            "id": "cs_ci", "object": "checkout.session", "mode": "payment",
            "payment_status": "paid", "client_reference_id": "buyer_ci",
            "customer": "cus_ci", "amount_total": 3500, "currency": "usd",
        }
        self.page = {"has_more": False, "data": [{"quantity": 1, "price": {
            "id": "price_pro", "unit_amount": 3500, "currency": "usd",
        }}]}
        self.calls = []

        def retrieve(session_id):
            self.calls.append(("session", session_id))
            return self.session

        def list_items(session_id):
            self.calls.append(("items", session_id))
            return self.page

        self.app = create_staging_webhook_app(
            webhook_secret=self.secret,
            retrieve_session=retrieve, list_line_items=list_items,
            bindings=self.bindings, store=self.store,
            price_allowlist={
                "price_pro": PricePlan("all_services", 3500),
                "price_callproof": PricePlan("call_proof", 1999),
            }, clock=lambda: self.now,
        )

    def request(self, path, *, buyer=None, method="GET", body=b"", headers=()):
        sent = []
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}
        async def send(message):
            sent.append(message)
        scope = {
            "type": "http", "path": path, "raw_path": path.encode(),
            "method": method, "headers": list(headers),
            # Explicitly injected identity is a synthetic trusted-host fixture.
            "state": {} if buyer is None else {"privi_buyer_id": buyer},
        }
        asyncio.run(self.app(scope, receive, send))
        return next(x["status"] for x in sent if x["type"] == "http.response.start")

    def webhook(self, *, bad_signature=False):
        body = json.dumps(self.event).encode()
        digest = hmac.new(
            self.secret.encode(), str(self.now).encode() + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        if bad_signature:
            digest = "0" * 64
        return self.request(
            "/staging/stripe-webhook", method="POST", body=body,
            headers=((b"stripe-signature", f"t={self.now},v1={digest}".encode()),),
        )

    def test_http_paid_pro_replay_revocation(self):
        self.assertEqual(self.request("/health"), 200)
        self.assertEqual(self.request("/catalog"), 200)
        self.assertEqual(self.request("/premium/guard", buyer="buyer_ci", method="POST"), 403)
        self.assertTrue(self.bindings.bind("cs_ci", "buyer_ci"))
        self.assertEqual(self.webhook(), 200)
        self.assertEqual(self.request("/premium/guard", buyer="buyer_ci", method="POST"), 200)
        self.assertEqual(self.request("/premium/callproof", buyer="buyer_ci", method="POST"), 200)
        self.assertEqual(self.request("/premium/guard", buyer="other", method="POST"), 403)
        self.assertEqual(self.webhook(), 200)
        self.assertTrue(self.store.revoke_session("cs_ci"))
        self.assertEqual(self.request("/premium/guard", buyer="buyer_ci", method="POST"), 403)
        self.assertEqual(self.webhook(), 200)
        self.assertFalse(self.store.authorized("buyer_ci", "guard"))

    def test_unbound_paid_webhook_retries_then_success(self):
        self.assertEqual(self.webhook(), 503)
        self.assertFalse(self.store.authorized("buyer_ci", "guard"))
        self.assertTrue(self.bindings.bind("cs_ci", "buyer_ci"))
        self.assertEqual(self.webhook(), 200)
        self.assertTrue(self.store.authorized("buyer_ci", "guard"))

    def test_invalid_signature_cannot_fetch_or_grant(self):
        self.assertTrue(self.bindings.bind("cs_ci", "buyer_ci"))
        self.assertEqual(self.webhook(bad_signature=True), 400)
        self.assertEqual(self.calls, [])
        self.assertFalse(self.store.authorized("buyer_ci", "guard"))

    def test_scoped_purchase_cannot_unlock_guard(self):
        self.assertTrue(self.bindings.bind("cs_ci", "buyer_ci"))
        self.session = dict(self.session, amount_total=1999)
        self.page = {"has_more": False, "data": [{"quantity": 1, "price": {
            "id": "price_callproof", "unit_amount": 1999, "currency": "usd",
        }}]}
        self.assertEqual(self.webhook(), 200)
        self.assertEqual(self.request("/premium/callproof", buyer="buyer_ci", method="POST"), 200)
        self.assertEqual(self.request("/premium/guard", buyer="buyer_ci", method="POST"), 403)

    def test_untrusted_buyer_header_never_authenticates(self):
        self.assertTrue(self.bindings.bind("cs_ci", "buyer_ci"))
        self.assertEqual(self.webhook(), 200)
        self.assertEqual(self.request("/premium/guard", method="POST", headers=(
            (b"x-buyer-id", b"buyer_ci"),)), 401)


if __name__ == "__main__":
    unittest.main()
