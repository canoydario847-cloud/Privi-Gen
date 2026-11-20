"""Real PostgreSQL integration tests for Privi paid entitlements.

Requires a disposable local PostgreSQL service and PRIVI_TEST_DATABASE_URL.
Never point this suite at a production database: the test truncates its table.
"""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

from protection.entitlement_store import PricePlan
from protection.postgres_entitlement_store import (
    PostgresEntitlementStore, SCHEMA_SQL, psycopg_connect_factory,
)
from protection.stripe_entitlements import PaidCheckout


@unittest.skipUnless(os.getenv("PRIVI_TEST_DATABASE_URL"), "Disposable PostgreSQL service required")
class RealPostgresEntitlements(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.getenv("PRIVI_TEST_DATABASE_URL")
        cls.connect = psycopg_connect_factory(cls.url)
        # CI-only disposable DB; never run this test against a shared server.
        if os.getenv("PRIVI_TEST_ALLOW_SCHEMA_RESET") != "ephemeral-ci-only":
            raise RuntimeError("Explicit disposable database confirmation required")
        with cls.connect() as conn:
            conn.execute(SCHEMA_SQL)
        cls.store = PostgresEntitlementStore(cls.connect)

    def setUp(self):
        with self.connect() as conn:
            conn.execute("TRUNCATE TABLE privi_processed_checkouts")

    def test_grant_replay_revoke_and_account_isolation(self):
        p = PaidCheckout("evt_1", "cs_1", "cus_1", "buyer_1", "price_pro", 3500, "usd")
        plan = PricePlan("all_services", 3500)
        self.assertFalse(self.store.authorized("buyer_1", "guard"))
        self.assertTrue(self.store.grant(p, "buyer_1", plan))
        self.assertTrue(self.store.authorized("buyer_1", "guard"))
        self.assertFalse(self.store.authorized("buyer_2", "guard"))
        self.assertFalse(self.store.grant(p, "buyer_1", plan))
        self.assertTrue(self.store.revoke_session("cs_1"))
        self.assertFalse(self.store.authorized("buyer_1", "guard"))
        self.assertFalse(self.store.grant(p, "buyer_1", plan))
        self.assertFalse(self.store.authorized("buyer_1", "guard"))

    def test_single_service_and_conflicting_replays(self):
        p = PaidCheckout("evt_2", "cs_2", "cus_1", "buyer_1", "price_callproof", 1999, "usd")
        plan = PricePlan("call_proof", 1999)
        self.assertTrue(self.store.grant(p, "buyer_1", plan))
        self.assertTrue(self.store.authorized("buyer_1", "call_proof"))
        self.assertFalse(self.store.authorized("buyer_1", "guard"))
        with self.assertRaises(ValueError):
            self.store.grant(replace(p, event_id="evt_other"), "buyer_1", plan)
        with self.assertRaises(ValueError):
            self.store.grant(replace(p, session_id="cs_other"), "buyer_1", plan)
        with self.assertRaises(ValueError):
            self.store.grant(p, "buyer_2", plan)

    def test_concurrent_duplicate_delivery_grants_once(self):
        p = PaidCheckout("evt_3", "cs_3", "cus_1", "buyer_1", "price_pro", 3500, "usd")
        plan = PricePlan("all_services", 3500)
        with ThreadPoolExecutor(max_workers=6) as pool:
            outcomes = list(pool.map(lambda _: self.store.grant(p, "buyer_1", plan), range(12)))
        self.assertEqual(outcomes.count(True), 1)
        self.assertEqual(outcomes.count(False), 11)
        self.assertTrue(self.store.authorized("buyer_1", "guard"))
        self.assertTrue(self.store.revoke_session("cs_3"))
        self.assertFalse(self.store.authorized("buyer_1", "guard"))


if __name__ == "__main__":
    unittest.main()
