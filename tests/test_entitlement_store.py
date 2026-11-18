import os
import tempfile
import unittest
from dataclasses import replace

from protection.entitlement_store import EntitlementStore, PricePlan
from protection.stripe_entitlements import PaidCheckout


class EntitlementStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = EntitlementStore(os.path.join(self.tmp.name, "entitlements.db"))
        self.purchase = PaidCheckout(
            "evt1", "cs1", "cus1", "buyer1", "price_pro", 3500, "usd")
        self.plan = PricePlan("all_services", 3500)

    def test_paid_access_and_idempotency(self):
        self.assertFalse(self.store.authorized("buyer1", "tool51"))
        self.assertTrue(self.store.grant(self.purchase, "buyer1", self.plan))
        self.assertFalse(self.store.grant(self.purchase, "buyer1", self.plan))
        self.assertTrue(self.store.authorized("buyer1", "tool51"))
        self.assertFalse(self.store.authorized("buyer2", "tool51"))
        self.assertTrue(self.store.revoke_session("cs1"))
        self.assertFalse(self.store.revoke_session("cs1"))
        self.assertFalse(self.store.authorized("buyer1", "tool51"))

    def test_scoped_plan(self):
        p = replace(self.purchase, stripe_price_id="price_single", amount_total=1999)
        self.store.grant(p, "buyer1", PricePlan("call_proof", 1999))
        self.assertTrue(self.store.authorized("buyer1", "call_proof"))
        self.assertFalse(self.store.authorized("buyer1", "privi_car"))

    def test_replay_conflict(self):
        self.store.grant(self.purchase, "buyer1", self.plan)
        with self.assertRaises(ValueError):
            self.store.grant(replace(self.purchase, event_id="evt2"), "buyer1", self.plan)

    def test_buyer_mismatch(self):
        with self.assertRaises(ValueError):
            self.store.grant(self.purchase, "buyer2", self.plan)

    def test_amount_mismatch(self):
        with self.assertRaises(ValueError):
            self.store.grant(self.purchase, "buyer1", PricePlan("all_services", 1999))


if __name__ == "__main__":
    unittest.main()
