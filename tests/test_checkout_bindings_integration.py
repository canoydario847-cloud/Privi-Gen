"""Real PostgreSQL tests for immutable checkout/account bindings.

Uses only the throwaway PostgreSQL CI database.
"""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor

from protection.checkout_bindings import BINDING_SCHEMA_SQL, PostgresCheckoutBindings
from protection.postgres_entitlement_store import psycopg_connect_factory


@unittest.skipUnless(os.getenv("PRIVI_TEST_DATABASE_URL"), "Disposable PostgreSQL required")
class RealCheckoutBindingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.getenv("PRIVI_TEST_ALLOW_SCHEMA_RESET") != "ephemeral-ci-only":
            raise RuntimeError("Never reset non-ephemeral checkout data")
        cls.connect = staticmethod(psycopg_connect_factory(os.environ["PRIVI_TEST_DATABASE_URL"]))
        with cls.connect() as conn:
            conn.execute(BINDING_SCHEMA_SQL)
        cls.bindings = PostgresCheckoutBindings(cls.connect)

    def setUp(self):
        with self.connect() as conn:
            conn.execute("TRUNCATE TABLE privi_checkout_buyers")

    def test_unbound_checkout_denied(self):
        self.assertIsNone(self.bindings.buyer_for("cs_unknown"))
        self.assertIsNone(self.bindings.buyer_for(""))

    def test_binding_immutable_and_idempotent(self):
        self.assertTrue(self.bindings.bind("cs_1", "buyer_1"))
        self.assertFalse(self.bindings.bind("cs_1", "buyer_1"))
        self.assertEqual(self.bindings.buyer_for("cs_1"), "buyer_1")
        with self.assertRaises(ValueError):
            self.bindings.bind("cs_1", "buyer_2")
        self.assertEqual(self.bindings.buyer_for("cs_1"), "buyer_1")

    def test_concurrent_conflicting_binders_only_one_wins(self):
        def attempt(buyer):
            try:
                return ("ok", self.bindings.bind("cs_race", buyer))
            except ValueError:
                return ("denied", False)

        buyers = ["buyer_a", "buyer_b"] * 8
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(attempt, buyers))
        self.assertEqual(sum(1 for status, inserted in results if inserted), 1)
        winner = self.bindings.buyer_for("cs_race")
        self.assertIn(winner, {"buyer_a", "buyer_b"})
        self.assertEqual(sum(1 for status, _ in results if status == "denied"), 8)

    def test_invalid_buyer_identity_rejected(self):
        for session, buyer in (("", "buyer_1"), ("cs_1", ""), (None, "buyer_1")):
            with self.subTest(session=session, buyer=buyer):
                with self.assertRaises(ValueError):
                    self.bindings.bind(session, buyer)


if __name__ == "__main__":
    unittest.main()
