"""Local SQLite reference store for Privi paid-service entitlements.

Production deployments must use a durable shared DB (typically PostgreSQL),
not Render's ephemeral filesystem. A Stripe webhook signature alone is not a
customer identity proof: bind checkout client_reference_id to the authenticated
buyer before calling grant().
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass

from .stripe_entitlements import PaidCheckout


@dataclass(frozen=True)
class PricePlan:
    scope: str  # "all_services" for $35 Pro, else one exact service ID
    amount_cents: int
    currency: str = "usd"


class EntitlementStore:
    """SQLite reference implementation with atomic, idempotent grant/revoke."""

    def __init__(self, database_path: str):
        self.database_path = database_path
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS processed_checkouts (
                    session_id TEXT PRIMARY KEY,
                    event_id TEXT UNIQUE NOT NULL,
                    buyer_id TEXT NOT NULL,
                    customer_id TEXT NOT NULL,
                    price_id TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    amount_cents INTEGER NOT NULL,
                    currency TEXT NOT NULL,
                    revoked INTEGER NOT NULL DEFAULT 0 CHECK(revoked IN (0,1))
                );
                CREATE INDEX IF NOT EXISTS idx_checkouts_buyer
                  ON processed_checkouts(buyer_id, scope, revoked);
            """)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.database_path, timeout=10)
        try:
            db.execute("PRAGMA busy_timeout=10000")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def grant(self, purchase: PaidCheckout, buyer_id: str, plan: PricePlan) -> bool:
        """Persist a verified purchase once; returns False for replay.

        Only call after checking authenticated buyer -> Stripe client_reference_id
        correspondence, server-fetched Checkout Session and line items, and
        exact allowlisted plan/price. Never grant from redirect parameters.
        """
        if not buyer_id or purchase.client_reference_id != buyer_id:
            raise ValueError("Checkout customer identity mismatch")
        if (not purchase.session_id or not purchase.event_id
                or not purchase.customer_id or not purchase.stripe_price_id
                or not plan.scope or plan.amount_cents <= 0
                or purchase.amount_total != plan.amount_cents
                or purchase.currency != plan.currency.lower()):
            raise ValueError("Invalid verified purchase or price plan")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT event_id, buyer_id, customer_id, price_id, scope FROM processed_checkouts WHERE session_id=?",
                (purchase.session_id,),
            ).fetchone()
            if old:
                if old != (purchase.event_id, buyer_id, purchase.customer_id, purchase.stripe_price_id, plan.scope):
                    raise ValueError("Conflicting checkout replay")
                return False
            db.execute(
                """INSERT INTO processed_checkouts
                (session_id,event_id,buyer_id,customer_id,price_id,scope,amount_cents,currency)
                VALUES (?,?,?,?,?,?,?,?)""",
                (purchase.session_id, purchase.event_id, buyer_id,
                 purchase.customer_id, purchase.stripe_price_id, plan.scope,
                 plan.amount_cents, plan.currency.lower()),
            )
            return True

    def authorized(self, buyer_id: str, scope: str) -> bool:
        """Check a currently held service-specific or unlimited entitlement."""
        if not buyer_id or not scope:
            return False
        with self._db() as db:
            return db.execute(
                """SELECT 1 FROM processed_checkouts
                WHERE buyer_id=? AND revoked=0 AND (scope=? OR scope='all_services')
                LIMIT 1""", (buyer_id, scope),
            ).fetchone() is not None

    def revoke_session(self, session_id: str) -> bool:
        """Operator-verified refund/dispute revocation; safe on repeated calls."""
        if not session_id:
            raise ValueError("Missing session ID")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            result = db.execute(
                "UPDATE processed_checkouts SET revoked=1 WHERE session_id=? AND revoked=0",
                (session_id,),
            )
            return result.rowcount == 1
