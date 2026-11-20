import hashlib
import hmac
import json
import os
import tempfile
import unittest

from protection.checkout_fulfillment import fulfill_verified_checkout
from protection.entitlement_store import EntitlementStore, PricePlan
from protection.stripe_entitlements import WebhookRejected


class VerifiedFulfillmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = EntitlementStore(os.path.join(self.temp.name, "checkouts.db"))
        self.secret = "whsec_fixture_not_live"
        self.now = 1784480000
        self.event = {
            "id": "evt_123", "type": "checkout.session.completed",
            "data": {"object": {"object": "checkout.session", "id": "cs_123"}},
        }
        self.session = {
            "id": "cs_123", "object": "checkout.session", "mode": "payment",
            "payment_status": "paid", "client_reference_id": "buyer_1",
            "customer": "cus_123", "amount_total": 3500, "currency": "usd",
        }
        self.lines = [{"quantity": 1, "price": {
            "id": "price_pro", "unit_amount": 3500, "currency": "usd",
        }}]
        self.allowlist = {
            "price_pro": PricePlan("all_services", 3500),
            "price_callproof": PricePlan("call_proof", 1999),
        }

    def call(self, *, event=None, session=None, lines=None, buyer="buyer_1",
             allowlist=None, bad_signature=False):
        body = json.dumps(self.event if event is None else event).encode()
        digest = hmac.new(
            self.secret.encode(), str(self.now).encode() + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        if bad_signature:
            digest = "0" * 64
        return fulfill_verified_checkout(
            payload=body, signature=f"t={self.now},v1={digest}",
            webhook_secret=self.secret,
            verified_session=self.session if session is None else session,
            verified_line_items=self.lines if lines is None else lines,
            checkout_buyer_id=buyer,
            price_allowlist=self.allowlist if allowlist is None else allowlist,
            store=self.store, clock=lambda: self.now,
        )

    def test_pro_entitlement_and_revocation(self):
        self.assertFalse(self.store.authorized("buyer_1", "guard"))
        self.assertTrue(self.call())
        self.assertTrue(self.store.authorized("buyer_1", "guard"))
        self.assertFalse(self.call())  # identical replay is idempotent
        self.assertTrue(self.store.revoke_session("cs_123"))
        self.assertFalse(self.store.authorized("buyer_1", "guard"))
        self.assertFalse(self.call())  # replay never restores revoked access
        self.assertFalse(self.store.authorized("buyer_1", "guard"))

    def test_single_service_scope(self):
        session = dict(self.session, amount_total=1999)
        lines = [{"quantity": 1, "price": {
            "id": "price_callproof", "unit_amount": 1999, "currency": "usd",
        }}]
        self.assertTrue(self.call(session=session, lines=lines))
        self.assertTrue(self.store.authorized("buyer_1", "call_proof"))
        self.assertFalse(self.store.authorized("buyer_1", "guard"))

    def test_mismatched_customer_never_unlocks(self):
        with self.assertRaises(ValueError):
            self.call(buyer="other_buyer")
        self.assertFalse(self.store.authorized("buyer_1", "guard"))
        self.assertFalse(self.store.authorized("other_buyer", "guard"))

    def test_bad_signature_never_unlocks(self):
        with self.assertRaises(WebhookRejected):
            self.call(bad_signature=True)
        self.assertFalse(self.store.authorized("buyer_1", "guard"))

    def test_unknown_price_never_unlocks(self):
        lines = [{"quantity": 1, "price": {
            "id": "price_unknown", "unit_amount": 3500, "currency": "usd",
        }}]
        self.assertFalse(self.call(lines=lines))
        self.assertFalse(self.store.authorized("buyer_1", "guard"))

    def test_unpaid_checkout_never_unlocks(self):
        self.assertFalse(self.call(session=dict(self.session, payment_status="unpaid")))
        self.assertFalse(self.store.authorized("buyer_1", "guard"))

    def test_mixed_cart_never_unlocks(self):
        self.assertFalse(self.call(lines=self.lines + self.lines))
        self.assertFalse(self.store.authorized("buyer_1", "guard"))

    def test_invalid_allowlist_rejected(self):
        with self.assertRaises(ValueError):
            self.call(allowlist={"price_pro": PricePlan("all_services", 0)})

    def test_invalid_server_buyer_binding_rejected(self):
        with self.assertRaises(ValueError):
            self.call(buyer="")


if __name__ == "__main__":
    unittest.main()
