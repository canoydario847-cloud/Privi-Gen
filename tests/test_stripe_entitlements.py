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
                "currency": "usd", "_server_verified_price_id": "price_attacker_supplied",
            }},
        }
        self.payload = json.dumps(self.obj).encode()
        self.session = {
            "object": "checkout.session", "id": "cs_1", "mode": "payment",
            "payment_status": "paid", "client_reference_id": "user_1",
            "customer": "cus_1", "amount_total": 3500, "currency": "usd",
        }
        self.line_items = [{"quantity": 1, "price": {
            "id": "price_pro", "unit_amount": 3500, "currency": "usd"
        }}]
        self.prices = {"price_pro": ("all_services", 3500, "usd")}

    def header(self, payload=None, timestamp=None):
        payload = self.payload if payload is None else payload
        timestamp = self.now if timestamp is None else timestamp
        digest = hmac.new(self.secret.encode(), str(timestamp).encode() + b"." + payload,
                          hashlib.sha256).hexdigest()
        return f"t={timestamp},v1={digest}"

    def extract(self, event=None, session=None, line_items=None):
        return extract_paid_checkout(
            self.obj if event is None else event,
            self.prices,
            verified_session=self.session if session is None else session,
            verified_line_items=self.line_items if line_items is None else line_items,
        )

    def test_signature_and_payment(self):
        event = verify_stripe_signature(self.payload, self.header(), self.secret,
                                        clock=lambda: self.now)
        paid = self.extract(event=event)
        self.assertEqual(paid.client_reference_id, "user_1")
        self.assertEqual(paid.stripe_price_id, "price_pro")

    def test_tampering_rejected(self):
        with self.assertRaises(WebhookRejected):
            verify_stripe_signature(self.payload + b" ", self.header(), self.secret,
                                    clock=lambda: self.now)

    def test_expired_signature_rejected(self):
        with self.assertRaises(WebhookRejected):
            verify_stripe_signature(self.payload, self.header(), self.secret,
                                    clock=lambda: self.now + 301)

    def test_unpaid_rejected(self):
        bad = dict(self.session, payment_status="unpaid")
        self.assertIsNone(self.extract(session=bad))

    def test_injected_price_metadata_ignored(self):
        self.assertEqual(self.extract().stripe_price_id, "price_pro")
        self.assertIsNone(self.extract(line_items=[{"quantity": 1, "price": {
            "id": "price_attacker_supplied", "unit_amount": 3500, "currency": "usd"
        }}]))

    def test_wrong_session_rejected(self):
        self.assertIsNone(self.extract(session=dict(self.session, id="cs_other")))

    def test_wrong_amount_rejected(self):
        self.assertIsNone(self.extract(session=dict(self.session, amount_total=1999)))

    def test_malformed_signed_event_rejected_without_exception(self):
        self.assertIsNone(extract_paid_checkout(
            None, self.prices, verified_session=self.session,
            verified_line_items=self.line_items,
        ))
        for event in (
            [],
            {"type": "checkout.session.completed", "data": None},
            {"type": "checkout.session.completed", "data": []},
            {"type": "checkout.session.completed", "data": {"object": None}},
        ):
            with self.subTest(event=event):
                self.assertIsNone(self.extract(event=event))

    def test_malformed_currency_rejected_without_exception(self):
        for currency in (None, 840, [], {}):
            with self.subTest(currency=currency):
                self.assertIsNone(self.extract(session=dict(self.session, currency=currency)))
                items = [{"quantity": 1, "price": {
                    "id": "price_pro", "unit_amount": 3500, "currency": currency
                }}]
                self.assertIsNone(self.extract(line_items=items))

    def test_mixed_cart_rejected(self):
        self.assertIsNone(self.extract(line_items=self.line_items * 2))


if __name__ == "__main__":
    unittest.main()
