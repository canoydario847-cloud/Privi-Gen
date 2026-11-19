"""Synthetic, offline end-to-end payment entitlement tests.

No Stripe credentials, live payments, network calls, or production databases.
This verifies the seam between signed webhook parsing, server-side purchase
verification, entitlement persistence, and MCP paid tool authorization.
"""
import hashlib
import hmac
import json
import os
import tempfile
import unittest

from protection.entitlement_store import EntitlementStore, PricePlan
from protection.mcp_policy import MCPAccessPolicy
from protection.stripe_entitlements import (
    WebhookRejected, extract_paid_checkout, verify_stripe_signature,
)


class PaidAccessEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = EntitlementStore(os.path.join(self.temp.name, "test.db"))
        self.policy = MCPAccessPolicy(
            tool_scopes={"privi_callproof": "call_proof", "privi_guard": "guard"},
            authorized=self.store.authorized,
        )
        self.key = "whsec_offline_fixture_only"
        self.timestamp = 1784480000
        self.event = {
            "id": "evt_fixture", "type": "checkout.session.completed",
            "data": {"object": {"object": "checkout.session", "id": "cs_fixture"}},
        }
        self.session = {
            "object": "checkout.session", "id": "cs_fixture",
            "mode": "payment", "payment_status": "paid",
            "client_reference_id": "buyer_fixture",
            "customer": "cus_fixture", "amount_total": 3500, "currency": "usd",
        }
        self.lines = [{"quantity": 1, "price": {
            "id": "price_pro_fixture", "unit_amount": 3500, "currency": "usd",
        }}]
        self.prices = {
            "price_pro_fixture": ("all_services", 3500, "usd"),
            "price_callproof_fixture": ("call_proof", 1999, "usd"),
        }

    def signed_event(self, event=None):
        payload = json.dumps(self.event if event is None else event).encode()
        signature = hmac.new(
            self.key.encode(), str(self.timestamp).encode() + b"." + payload,
            hashlib.sha256,
        ).hexdigest()
        return verify_stripe_signature(
            payload, f"t={self.timestamp},v1={signature}", self.key,
            clock=lambda: self.timestamp,
        )

    def decision(self, name, buyer="buyer_fixture"):
        return self.policy.decide(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"name": name}},
            buyer_id=buyer,
        )

    def grant(self, scope="all_services"):
        amount, price_id = (
            (3500, "price_pro_fixture") if scope == "all_services"
            else (1999, "price_callproof_fixture")
        )
        session = dict(self.session, amount_total=amount)
        lines = [{"quantity": 1, "price": {
            "id": price_id, "unit_amount": amount, "currency": "usd",
        }}]
        purchase = extract_paid_checkout(
            self.signed_event(), self.prices,
            verified_session=session, verified_line_items=lines,
        )
        self.assertIsNotNone(purchase)
        plan = PricePlan(scope, amount, "usd")
        return self.store.grant(purchase, "buyer_fixture", plan)

    def test_unpaid_and_unknown_users_denied(self):
        self.assertFalse(self.decision("privi_callproof").allowed)
        self.assertFalse(self.decision("privi_callproof", None).allowed)
        self.assertFalse(self.decision("privi_guard", "other_buyer").allowed)
        self.assertFalse(self.decision("not_registered").allowed)

    def test_paid_pro_granted_once_then_revoked(self):
        self.assertFalse(self.decision("privi_callproof").allowed)
        self.assertTrue(self.grant("all_services"))
        self.assertFalse(self.grant("all_services"))
        self.assertTrue(self.decision("privi_callproof").allowed)
        self.assertTrue(self.decision("privi_guard").allowed)
        self.assertFalse(self.decision("privi_guard", "other_buyer").allowed)
        self.assertTrue(self.store.revoke_session("cs_fixture"))
        self.assertFalse(self.decision("privi_guard").allowed)
        self.assertFalse(self.decision("privi_callproof").allowed)
        self.assertFalse(self.store.revoke_session("cs_fixture"))

    def test_single_service_does_not_unlock_other_tools(self):
        self.assertTrue(self.grant("call_proof"))
        self.assertTrue(self.decision("privi_callproof").allowed)
        self.assertFalse(self.decision("privi_guard").allowed)

    def test_tampered_webhook_cannot_create_entitlement(self):
        payload = json.dumps(self.event).encode() + b" "
        original = json.dumps(self.event).encode()
        digest = hmac.new(
            self.key.encode(), str(self.timestamp).encode() + b"." + original,
            hashlib.sha256,
        ).hexdigest()
        with self.assertRaises(WebhookRejected):
            verify_stripe_signature(
                payload, f"t={self.timestamp},v1={digest}", self.key,
                clock=lambda: self.timestamp,
            )
        self.assertFalse(self.decision("privi_callproof").allowed)


if __name__ == "__main__":
    unittest.main()
