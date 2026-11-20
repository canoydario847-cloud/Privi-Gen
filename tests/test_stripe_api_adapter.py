import hashlib
import hmac
import json
import os
import tempfile
import unittest

from protection.stripe_api_adapter import fulfill_from_stripe_api
from protection.entitlement_store import EntitlementStore, PricePlan
from protection.stripe_entitlements import WebhookRejected


class Bindings:
    def __init__(self, buyer="buyer"):
        self.buyer = buyer

    def buyer_for(self, session_id):
        return self.buyer if session_id == "cs_test" else None


class StripeAdapterTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = EntitlementStore(os.path.join(tmp.name, "test.db"))
        self.now = 1784480000
        self.secret = "whsec_fixture"
        self.event = {
            "id": "evt_test", "type": "checkout.session.completed",
            "data": {"object": {"object": "checkout.session", "id": "cs_test"}},
        }
        self.session = {
            "object": "checkout.session", "id": "cs_test",
            "mode": "payment", "payment_status": "paid",
            "client_reference_id": "buyer", "customer": "cus_test",
            "amount_total": 3500, "currency": "usd",
        }
        self.page = {"has_more": False, "data": [{"quantity": 1, "price": {
            "id": "price_pro", "unit_amount": 3500, "currency": "usd",
        }}]}
        self.called = []

    def attempt(self, *, event=None, signature_bad=False, session=None,
                page=None, buyer="buyer"):
        payload = json.dumps(self.event if event is None else event).encode()
        digest = hmac.new(
            self.secret.encode(), str(self.now).encode() + b"." + payload,
            hashlib.sha256,
        ).hexdigest()
        if signature_bad:
            digest = "0" * 64

        def retrieve(session_id):
            self.called.append(("retrieve", session_id))
            return self.session if session is None else session

        def line_items(session_id):
            self.called.append(("items", session_id))
            return self.page if page is None else page

        return fulfill_from_stripe_api(
            payload=payload, signature=f"t={self.now},v1={digest}",
            webhook_secret=self.secret, retrieve_session=retrieve,
            list_line_items=line_items, bindings=Bindings(buyer),
            store=self.store,
            price_allowlist={"price_pro": PricePlan("all_services", 3500)},
            clock=lambda: self.now,
        )

    def test_paid_checkout_grants_and_replays(self):
        self.assertTrue(self.attempt())
        self.assertFalse(self.attempt())
        self.assertEqual(self.called, [
            ("retrieve", "cs_test"), ("items", "cs_test"),
            ("retrieve", "cs_test"), ("items", "cs_test"),
        ])
        self.assertTrue(self.store.authorized("buyer", "call_proof"))
        self.assertTrue(self.store.revoke_session("cs_test"))
        self.assertFalse(self.attempt())
        self.assertFalse(self.store.authorized("buyer", "call_proof"))

    def test_bad_signature_never_fetches(self):
        with self.assertRaises(WebhookRejected):
            self.attempt(signature_bad=True)
        self.assertEqual(self.called, [])
        self.assertFalse(self.store.authorized("buyer", "call_proof"))

    def test_unrelated_event_never_fetches(self):
        event = dict(self.event, type="customer.created")
        self.assertFalse(self.attempt(event=event))
        self.assertEqual(self.called, [])

    def test_pagination_and_extra_items_rejected(self):
        for page in (
            {"has_more": True, "data": self.page["data"]},
            {"data": self.page["data"]},
            {"has_more": False, "data": self.page["data"] * 2},
            {"has_more": False, "data": []},
        ):
            with self.subTest(page=page):
                with self.assertRaises(ValueError):
                    self.attempt(page=page)
        self.assertFalse(self.store.authorized("buyer", "call_proof"))

    def test_wrong_fetched_session_denied(self):
        with self.assertRaises(ValueError):
            self.attempt(session=dict(self.session, id="cs_other"))
        self.assertFalse(self.store.authorized("buyer", "call_proof"))

    def test_missing_or_wrong_buyer_denied(self):
        self.assertFalse(self.attempt(buyer=None))
        with self.assertRaises(ValueError):
            self.attempt(buyer="other")
        self.assertFalse(self.store.authorized("buyer", "call_proof"))

    def test_unpaid_rejected(self):
        self.assertFalse(self.attempt(session=dict(self.session, payment_status="unpaid")))
        self.assertFalse(self.store.authorized("buyer", "call_proof"))


if __name__ == "__main__":
    unittest.main()
