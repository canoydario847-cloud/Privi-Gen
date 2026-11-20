import asyncio
import hashlib
import hmac
import json
import os
import tempfile
import unittest

from protection.entitlement_store import EntitlementStore, PricePlan
from protection.staging_webhook_app import create_staging_webhook_app


class StubBindings:
    def __init__(self, buyer="buyer_1"):
        self.buyer = buyer

    def buyer_for(self, session_id):
        return self.buyer if session_id == "cs_1" else None


class WebhookStagingTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = EntitlementStore(os.path.join(tmp.name, "staging.db"))
        self.secret = "whsec_synthetic_fixture"
        self.now = 1784480000
        self.event = {
            "id": "evt_1", "type": "checkout.session.completed",
            "data": {"object": {"object": "checkout.session", "id": "cs_1"}},
        }
        self.session = {
            "id": "cs_1", "object": "checkout.session", "mode": "payment",
            "payment_status": "paid", "client_reference_id": "buyer_1",
            "customer": "cus_1", "amount_total": 1999, "currency": "usd",
        }
        self.lines = {"has_more": False, "data": [{"quantity": 1, "price": {
            "id": "price_callproof", "unit_amount": 1999, "currency": "usd",
        }}]}
        self.stripe_calls = []

        def retrieve(session_id):
            self.stripe_calls.append(("retrieve", session_id))
            return self.session

        def items(session_id):
            self.stripe_calls.append(("items", session_id))
            return self.lines

        self.app = create_staging_webhook_app(
            webhook_secret=self.secret, retrieve_session=retrieve,
            list_line_items=items, bindings=StubBindings(),
            store=self.store,
            price_allowlist={"price_callproof": PricePlan("call_proof", 1999)},
            clock=lambda: self.now,
        )

    def call(self, path, *, body=b"", method="GET", headers=(), buyer=None):
        messages = []
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}
        async def send(msg):
            messages.append(msg)
        scope = {
            "type": "http", "path": path, "raw_path": path.encode(),
            "method": method, "headers": list(headers),
            "state": {} if buyer is None else {"privi_buyer_id": buyer},
        }
        asyncio.run(self.app(scope, receive, send))
        status = next(x["status"] for x in messages if x["type"] == "http.response.start")
        output = b"".join(x.get("body", b"") for x in messages if x["type"] == "http.response.body")
        return status, json.loads(output) if output.startswith(b"{") else output

    def signed(self, bad=False):
        body = json.dumps(self.event).encode()
        digest = hmac.new(
            self.secret.encode(), str(self.now).encode() + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        if bad:
            digest = "0" * 64
        return body, ((b"stripe-signature", f"t={self.now},v1={digest}".encode()),)

    def test_purchase_then_authorize_then_revoke(self):
        self.assertEqual(self.call("/premium/callproof", method="POST", buyer="buyer_1")[0], 403)
        body, headers = self.signed()
        status, result = self.call("/staging/stripe-webhook", body=body, method="POST", headers=headers)
        self.assertEqual((status, result["new_entitlement"]), (200, True))
        self.assertEqual(self.call("/premium/callproof", method="POST", buyer="buyer_1")[0], 200)
        self.assertEqual(self.call("/premium/guard", method="POST", buyer="buyer_1")[0], 403)
        self.assertEqual(self.call("/premium/callproof", method="POST", buyer="buyer_2")[0], 403)
        self.assertEqual(self.call("/staging/stripe-webhook", body=body, method="POST", headers=headers)[1]["new_entitlement"], False)
        self.assertTrue(self.store.revoke_session("cs_1"))
        self.assertEqual(self.call("/premium/callproof", method="POST", buyer="buyer_1")[0], 403)

    def test_invalid_signature_never_calls_stripe(self):
        body, headers = self.signed(bad=True)
        self.assertEqual(self.call("/staging/stripe-webhook", body=body, method="POST", headers=headers)[0], 400)
        self.assertEqual(self.stripe_calls, [])
        self.assertEqual(self.call("/premium/callproof", method="POST", buyer="buyer_1")[0], 403)

    def test_missing_or_duplicate_signature_rejected(self):
        body, headers = self.signed()
        for h in ((), headers + headers):
            with self.subTest(headers=h):
                self.assertEqual(self.call("/staging/stripe-webhook", body=body, method="POST", headers=h)[0], 400)
        self.assertEqual(self.stripe_calls, [])

    def test_api_failure_never_grants(self):
        self.session = dict(self.session, id="cs_other")
        body, headers = self.signed()
        self.assertEqual(self.call("/staging/stripe-webhook", body=body, method="POST", headers=headers)[0], 503)
        self.assertFalse(self.store.authorized("buyer_1", "call_proof"))

    def test_method_and_size_limits(self):
        body, headers = self.signed()
        self.assertEqual(self.call("/staging/stripe-webhook", body=body, headers=headers)[0], 405)
        self.assertEqual(self.call("/staging/stripe-webhook", body=b"x" * 65537, method="POST", headers=headers)[0], 413)
        self.assertEqual(self.stripe_calls, [])

    def test_public_catalog_and_unknown_paths(self):
        self.assertEqual(self.call("/health")[0], 200)
        self.assertEqual(self.call("/catalog")[0], 200)
        self.assertEqual(self.call("/admin")[0], 403)


if __name__ == "__main__":
    unittest.main()
