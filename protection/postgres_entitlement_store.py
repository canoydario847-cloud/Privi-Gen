"""PostgreSQL reference backend for Privi paid-service entitlements.

Requires psycopg 3 and an externally provisioned persistent PostgreSQL DB.
No connection is made at import time. Run schema SQL as an explicit migration.
Do not run migrations automatically on production startup.

The webhook handler must independently verify the buyer's checkout binding,
Stripe signature, fetched session + line items and refund/dispute status.
"""
from __future__ import annotations

from contextlib import closing
from typing import Callable

from .entitlement_store import PricePlan
from .stripe_entitlements import PaidCheckout


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS privi_processed_checkouts (
    session_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    buyer_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    price_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    currency TEXT NOT NULL,
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS privi_checkouts_buyer_idx
    ON privi_processed_checkouts (buyer_id, scope)
    WHERE revoked = FALSE;
"""


class PostgresEntitlementStore:
    """Shared, transaction-safe entitlement backend.

    Pass a zero-argument factory returning a new DB-API-style PostgreSQL
    connection. Callers should use a limited-privilege service DB role.
    Neither SQLite nor an ephemeral Render filesystem is appropriate here.
    """

    def __init__(self, connect: Callable[[], object]):
        if not callable(connect):
            raise ValueError("A PostgreSQL connection factory is required")
        self.connect = connect

    def grant(self, purchase: PaidCheckout, buyer_id: str, plan: PricePlan) -> bool:
        if not isinstance(buyer_id, str) or not buyer_id.strip() or purchase.client_reference_id != buyer_id:
            raise ValueError("Checkout buyer identity mismatch")
        if (not purchase.session_id or not purchase.event_id or not purchase.customer_id
                or not purchase.stripe_price_id or not isinstance(plan.scope, str)
                or not plan.scope.strip() or type(plan.amount_cents) is not int
                or plan.amount_cents <= 0 or not isinstance(plan.currency, str)
                or purchase.amount_total != plan.amount_cents
                or purchase.currency != plan.currency.lower()):
            raise ValueError("Invalid verified purchase or price plan")
        # ON CONFLICT handles concurrent webhook deliveries safely. Do not grant
        # from browser redirects; only an authenticated verified purchase.
        with closing(self.connect()) as conn:
            with conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """INSERT INTO privi_processed_checkouts
                        (session_id,event_id,buyer_id,customer_id,price_id,
                         scope,amount_cents,currency)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT DO NOTHING RETURNING session_id""",
                        (purchase.session_id, purchase.event_id, buyer_id,
                         purchase.customer_id, purchase.stripe_price_id,
                         plan.scope, plan.amount_cents, plan.currency.lower()),
                    )
                    if cursor.fetchone() is not None:
                        return True
                    # Existing session replay: verify every immutable field,
                    # not merely the session ID. A duplicate event attached to
                    # another checkout must never silently pass.
                    cursor.execute(
                        """SELECT event_id,buyer_id,customer_id,price_id,scope,
                                  amount_cents,currency
                           FROM privi_processed_checkouts
                           WHERE session_id=%s""",
                        (purchase.session_id,),
                    )
                    existing = cursor.fetchone()
                    expected = (
                        purchase.event_id, buyer_id, purchase.customer_id,
                        purchase.stripe_price_id, plan.scope, plan.amount_cents,
                        plan.currency.lower(),
                    )
                    if existing != expected:
                        raise ValueError("Conflicting checkout replay or event ID")
                    # A revoked grant stays revoked, even after webhook replay.
                    return False

    def authorized(self, buyer_id: str, scope: str) -> bool:
        if not isinstance(buyer_id, str) or not buyer_id.strip() or not isinstance(scope, str) or not scope.strip():
            return False
        with closing(self.connect()) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """SELECT EXISTS (
                       SELECT 1 FROM privi_processed_checkouts
                       WHERE buyer_id=%s AND revoked=FALSE
                         AND (scope=%s OR scope='all_services')
                    )""",
                    (buyer_id, scope),
                )
                return cursor.fetchone() == (True,)

    def purchase_for_session(self, session_id: str) -> dict | None:
        """Return immutable server-side purchase facts for reconciliation."""
        if not isinstance(session_id, str) or not session_id.strip():
            return None
        with closing(self.connect()) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """SELECT buyer_id,customer_id,amount_cents,currency,revoked
                       FROM privi_processed_checkouts WHERE session_id=%s""",
                    (session_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                return {
                    "buyer_id": row[0], "customer_id": row[1],
                    "amount_cents": row[2], "currency": row[3],
                    "revoked": row[4],
                }

    def revoke_session(self, session_id: str) -> bool:
        # Only call after authoritative provider refund/dispute verification
        # or a trusted administrator's revocation decision.
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("Checkout session ID required")
        with closing(self.connect()) as conn:
            with conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """UPDATE privi_processed_checkouts
                           SET revoked=TRUE
                           WHERE session_id=%s AND revoked=FALSE""",
                        (session_id,),
                    )
                    return cursor.rowcount == 1


def psycopg_connect_factory(database_url: str):
    """Create a connection factory; psycopg is an optional runtime dependency.

    Supply DATABASE_URL from a trusted server secret manager, never in Git.
    """
    if not isinstance(database_url, str) or not database_url.startswith(("postgres://", "postgresql://")):
        raise ValueError("Valid PostgreSQL DATABASE_URL required")

    def connect():
        import psycopg
        return psycopg.connect(database_url, connect_timeout=5)

    return connect
