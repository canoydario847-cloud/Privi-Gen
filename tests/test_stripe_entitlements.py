import hashlib
import hmac
import json
import unittest
from protection.stripe_entitlements import (
    WebhookRejected, extract_paid_checkout, verify_stripe_signature,
)

class StripeVerificationTests(unittest.TestCase):
    def setUp(self):
        self.secret = "whsec_testing_only"
        self.now = 1784480000
        self.obj = {
            "id": "evt_1", "type": "checkout.session.completed",
            "data": {"object": {
                "object": "checkout.session", "id": "cs_1", "mode": "payment",
                "payment_status": "paid", "client_reference_id": "user_1",
                "customer": "cus_1", "amount_total": 3500,
                "currency": "usd", "_server_verified_price_id": "price_pro",
            }},
        }
        self.payload = json.dumps(self.obj).encode()
    def header(self, payload=None, timestamp=None):
        payload = self.payload if payload is None else payload
        timestamp = self.now if timestamp is None else timestamp
        digest = hmac.new(self.secret.encode(), str(timestamp).encode()+b"."+payload, hashlib.sha256).hexdigest()
        return f"t={timestamp},v1={digest}"
    def test_signature_and_payment(self):
        ev = verify_stripe_signature(self.payload, self.header(), self.secret, clock=lambda: self.now)
        paid = extract_paid_checkout(ev, {"price_pro": "all_services"})
        self.assertEqual(paid.client_reference_id, "user_1")
    def test_tampering_rejected(self):
        with self.assertRaises(WebhookRejected):
            verify_stripe_signature(self.payload+b" ", self.header(), self.secret, clock=lambda: self.now)
    def test_old_timestamp_rejected(self):
        with self.assertRaises(WebhookRejected):
            verify_stripe_signature(self.payload, self.header(), self.secret, clock=lambda: self.now+301)
    def test_unpaid_not_granted(self):
        self.obj["data"]["object"]["payment_status"] = "unpaid"
        self.assertIsNone(extract_paid_checkout(self.obj, {"price_pro":"all_services"}))
    def test_unverified_price_not_granted(self):
        del self.obj["data"]["object"]["_server_verified_price_id"]
        self.assertIsNone(extract_paid_checkout(self.obj, {"price_pro":"all_services"}))

if __name__ == "__main__":
    unittest.main()
