"""Offline HTTP integration regression tests for Privi's ASGI paid access gate.

These verify transport-level authorization and a real entitlement lookup using
fabricated records. They do not enable access controls in production.
"""
import asyncio
import os
import tempfile
import unittest

from protection.asgi_gate import PaidAccessGate
from protection.entitlement_store import EntitlementStore, PricePlan
from protection.stripe_entitlements import PaidCheckout


class HTTPPaidAccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = EntitlementStore(os.path.join(self.tmp.name, "http-test.db"))
        self.executed = []

        async def premium_app(scope, receive, send):
            self.executed.append(scope["path"])
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"premium-response"})

        self.app = PaidAccessGate(
            premium_app,
            protected_mounts={
                "/premium": "all_services",
                "/premium/callproof": "call_proof",
                "/premium/guard": "guard",
            },
            authorized=self.store.authorized,
            deny_unmapped=True,
            public_mounts=("/health", "/mcp/discovery"),
        )

    def request(self, path, buyer=None):
        messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        # In real deployment this state MUST come from trusted auth middleware.
        state = {} if buyer is None else {"privi_buyer_id": buyer}
        asyncio.run(self.app(
            {"type": "http", "path": path, "method": "POST",
             "state": state, "raw_path": path.encode()},
            receive, send,
        ))
        return next(m["status"] for m in messages if m["type"] == "http.response.start")

    def purchase(self, scope, price, cents, session):
        # Synthetic fixture only. Production requires server-fetched, verified Stripe data.
        checkout = PaidCheckout(
            "evt_" + session, session, "cus_buyer", "buyer",
            price, cents, "usd",
        )
        self.store.grant(checkout, "buyer", PricePlan(scope, cents))

    def test_unpaid_access_denied_with_no_handler_execution(self):
        self.assertEqual(self.request("/premium/callproof/run", "buyer"), 403)
        self.assertEqual(self.request("/premium/callproof/run"), 401)
        self.assertEqual(self.request("/premium/guard", "other"), 403)
        self.assertEqual(self.executed, [])

    def test_scoped_purchase_then_revocation(self):
        self.purchase("call_proof", "price_single_fixture", 1999, "cs_single")
        self.assertEqual(self.request("/premium/callproof/run", "buyer"), 200)
        self.assertEqual(self.request("/premium/guard", "buyer"), 403)
        self.assertEqual(self.request("/premium/callproof/run", "other"), 403)
        self.assertTrue(self.store.revoke_session("cs_single"))
        self.assertEqual(self.request("/premium/callproof/run", "buyer"), 403)
        self.assertEqual(self.executed, ["/premium/callproof/run"])

    def test_pro_purchase_allows_both_scopes_then_revokes(self):
        # The existing entitlement store intentionally grants "all_services"
        # as the Pro super-scope; this covers any explicitly mapped service.
        self.purchase("all_services", "price_pro_fixture", 3500, "cs_pro")
        self.assertEqual(self.request("/premium/callproof/run", "buyer"), 200)
        self.assertEqual(self.request("/premium/guard/run", "buyer"), 200)
        self.assertTrue(self.store.revoke_session("cs_pro"))
        self.assertEqual(self.request("/premium/guard/run", "buyer"), 403)

    def test_unmapped_admin_denied_but_discovery_available(self):
        self.assertEqual(self.request("/admin/debug", "buyer"), 403)
        self.assertEqual(self.request("/mcp/discovery"), 200)
        self.assertEqual(self.executed, ["/mcp/discovery"])

    def test_malformed_route_rejected(self):
        self.assertEqual(self.request("/public/../premium/callproof", "buyer"), 400)
        self.assertEqual(self.executed, [])


if __name__ == "__main__":
    unittest.main()
