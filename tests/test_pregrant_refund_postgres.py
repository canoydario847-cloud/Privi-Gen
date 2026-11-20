"""PostgreSQL pre-grant refund/dispute tombstones and concurrency.

Only execute against an ephemeral CI DB with reset acknowledgment.
"""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from protection.entitlement_store import PricePlan
from protection.postgres_entitlement_store import (
    SCHEMA_SQL, PostgresEntitlementStore, psycopg_connect_factory,
)
from protection.stripe_entitlements import PaidCheckout


@unittest.skipUnless(os.getenv("PRIVI_TEST_DATABASE_URL"), "Disposable PostgreSQL required")
class PreGrantBlocksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.getenv("PRIVI_TEST_ALLOW_SCHEMA_RESET") != "ephemeral-ci-only":
            raise RuntimeError("Never reset a non-ephemeral database")
        cls.connect = staticmethod(psycopg_connect_factory(os.environ["PRIVI_TEST_DATABASE_URL"]))
        with cls.connect() as conn:
            conn.execute(SCHEMA_SQL)
        cls.store = PostgresEntitlementStore(cls.connect)

    def setUp(self):
        with self.connect() as conn:
            conn.execute("TRUNCATE TABLE privi_processed_checkouts, privi_blocked_checkouts")
        self.purchase = PaidCheckout(
            "evt_block", "cs_block", "cus_1", "buyer_1", "price_pro", 3500, "usd"
        )
        self.plan = PricePlan("all_services", 3500)

    def test_verified_refund_before_grant_prevents_later_delivery(self):
        self.assertTrue(self.store.block_session("cs_block", "full_refund"))
        self.assertFalse(self.store.grant(self.purchase, "buyer_1", self.plan))
        self.assertFalse(self.store.authorized("buyer_1", "guard"))
        self.assertFalse(self.store.block_session("cs_block", "full_refund"))

    def test_dispute_after_grant_revokes_irreversibly(self):
        self.assertTrue(self.store.grant(self.purchase, "buyer_1", self.plan))
        self.assertTrue(self.store.authorized("buyer_1", "guard"))
        self.assertTrue(self.store.block_session("cs_block", "dispute"))
        self.assertFalse(self.store.authorized("buyer_1", "guard"))
        self.assertFalse(self.store.grant(self.purchase, "buyer_1", self.plan))

    def test_racing_grant_and_block_never_leave_active_access(self):
        barrier = Barrier(2)
        def grant():
            barrier.wait()
            return self.store.grant(self.purchase, "buyer_1", self.plan)
        def block():
            barrier.wait()
            return self.store.block_session("cs_block", "full_refund")
        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(grant)
            f2 = pool.submit(block)
            f1.result()
            self.assertTrue(f2.result())
        self.assertFalse(self.store.authorized("buyer_1", "guard"))
        self.assertFalse(self.store.grant(self.purchase, "buyer_1", self.plan))

    def test_invalid_block_request_does_not_revoke(self):
        self.assertTrue(self.store.grant(self.purchase, "buyer_1", self.plan))
        for session, reason in (("", "full_refund"), ("cs_block", "partial_refund"), ("cs_block", None)):
            with self.subTest(session=session, reason=reason):
                with self.assertRaises(ValueError):
                    self.store.block_session(session, reason)
        self.assertTrue(self.store.authorized("buyer_1", "guard"))


if __name__ == "__main__":
    unittest.main()
