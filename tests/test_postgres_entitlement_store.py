"""Unit tests for the Postgres store without a live database.

Actual PostgreSQL integration and concurrency tests remain release blockers.
"""
import unittest
from protection.postgres_entitlement_store import (
    PostgresEntitlementStore, SCHEMA_SQL, psycopg_connect_factory,
)
from protection.entitlement_store import PricePlan
from protection.stripe_entitlements import PaidCheckout


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self.rowcount = 0
        self.row = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params):
        if query.strip().startswith("INSERT"):
            session, event, buyer, customer, price, scope, cents, currency = params
            if session not in self.db and all(r[0] != event for r in self.db.values()):
                self.db[session] = (event, buyer, customer, price, scope, cents, currency, False)
                self.row = (session,)
            else:
                self.row = None
        elif query.strip().startswith("SELECT event_id"):
            row = self.db.get(params[0])
            self.row = row[:7] if row else None
        elif query.strip().startswith("SELECT EXISTS"):
            buyer, scope = params
            exists = any(
                r[1] == buyer and not r[7] and (r[4] == scope or r[4] == "all_services")
                for r in self.db.values()
            )
            self.row = (exists,)
        elif query.strip().startswith("UPDATE"):
            session = params[0]
            row = self.db.get(session)
            self.rowcount = int(bool(row and not row[7]))
            if self.rowcount:
                self.db[session] = row[:7] + (True,)
        else:
            raise AssertionError("Unexpected SQL")

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, db):
        self.db = db
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def cursor(self):
        return FakeCursor(self.db)

    def close(self):
        self.closed = True


class PostgresEntitlementStoreTests(unittest.TestCase):
    def setUp(self):
        self.db = {}
        self.connections = []
        def connect():
            c = FakeConnection(self.db)
            self.connections.append(c)
            return c
        self.store = PostgresEntitlementStore(connect)
        self.purchase = PaidCheckout("evt1", "cs1", "cus1", "buyer1", "price_pro", 3500, "usd")
        self.plan = PricePlan("all_services", 3500)

    def test_paid_replay_revoke_never_resurrects(self):
        self.assertFalse(self.store.authorized("buyer1", "call_proof"))
        self.assertTrue(self.store.grant(self.purchase, "buyer1", self.plan))
        self.assertTrue(self.store.authorized("buyer1", "guard"))
        self.assertFalse(self.store.authorized("other", "guard"))
        self.assertFalse(self.store.grant(self.purchase, "buyer1", self.plan))
        self.assertTrue(self.store.revoke_session("cs1"))
        self.assertFalse(self.store.authorized("buyer1", "guard"))
        self.assertFalse(self.store.grant(self.purchase, "buyer1", self.plan))
        self.assertFalse(self.store.authorized("buyer1", "guard"))
        self.assertFalse(self.store.revoke_session("cs1"))
        self.assertTrue(all(c.closed for c in self.connections))

    def test_conflicting_replays_denied(self):
        self.store.grant(self.purchase, "buyer1", self.plan)
        with self.assertRaises(ValueError):
            self.store.grant(
                PaidCheckout("evt2", "cs1", "cus1", "buyer1", "price_pro", 3500, "usd"),
                "buyer1", self.plan,
            )
        with self.assertRaises(ValueError):
            self.store.grant(
                PaidCheckout("evt1", "cs2", "cus1", "buyer1", "price_pro", 3500, "usd"),
                "buyer1", self.plan,
            )

    def test_single_service_only(self):
        p = PaidCheckout("evt2", "cs2", "cus1", "buyer1", "price_callproof", 1999, "usd")
        self.assertTrue(self.store.grant(p, "buyer1", PricePlan("call_proof", 1999)))
        self.assertTrue(self.store.authorized("buyer1", "call_proof"))
        self.assertFalse(self.store.authorized("buyer1", "guard"))

    def test_bad_account_binding_denied(self):
        with self.assertRaises(ValueError):
            self.store.grant(self.purchase, "buyer2", self.plan)

    def test_schema_and_url_validation(self):
        self.assertIn("PRIMARY KEY", SCHEMA_SQL)
        self.assertIn("UNIQUE", SCHEMA_SQL)
        with self.assertRaises(ValueError):
            psycopg_connect_factory("sqlite:///tmp/privi.db")


if __name__ == "__main__":
    unittest.main()
