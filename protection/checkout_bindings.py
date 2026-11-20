"""Server-side immutable Stripe Checkout Session -> authenticated buyer binding.

Create binding only from an authenticated server-side checkout creation request,
after receiving the session ID from Stripe. Never accept either buyer_id or
session_id from an untrusted callback as proof of ownership.
"""
from __future__ import annotations

from contextlib import closing
from typing import Callable

BINDING_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS privi_checkout_buyers (
    session_id TEXT PRIMARY KEY,
    buyer_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS privi_checkout_buyers_buyer_idx
    ON privi_checkout_buyers (buyer_id);
"""


class PostgresCheckoutBindings:
    """Immutable mapping; a replay with the same buyer is idempotent."""

    def __init__(self, connect: Callable[[], object]):
        if not callable(connect):
            raise ValueError("Database connection factory required")
        self.connect = connect

    def bind(self, session_id: str, buyer_id: str) -> bool:
        if (not isinstance(session_id, str) or not session_id.strip()
                or not isinstance(buyer_id, str) or not buyer_id.strip()):
            raise ValueError("Authenticated buyer and server-created session required")
        with closing(self.connect()) as conn:
            with conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """INSERT INTO privi_checkout_buyers (session_id,buyer_id)
                           VALUES (%s,%s) ON CONFLICT DO NOTHING
                           RETURNING session_id""",
                        (session_id, buyer_id),
                    )
                    if cursor.fetchone() is not None:
                        return True
                    cursor.execute(
                        "SELECT buyer_id FROM privi_checkout_buyers WHERE session_id=%s",
                        (session_id,),
                    )
                    row = cursor.fetchone()
                    if row != (buyer_id,):
                        raise ValueError("Checkout session already bound to another buyer")
                    return False

    def buyer_for(self, session_id: str) -> str | None:
        if not isinstance(session_id, str) or not session_id.strip():
            return None
        with closing(self.connect()) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT buyer_id FROM privi_checkout_buyers WHERE session_id=%s",
                    (session_id,),
                )
                row = cursor.fetchone()
                return row[0] if row is not None else None
