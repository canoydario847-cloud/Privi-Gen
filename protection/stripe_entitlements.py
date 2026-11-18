"""Verified Stripe Checkout event parser for Privi entitlements.

Application integration must authenticate users, persist events/entitlements
atomically, map configured Stripe price IDs to plan scope, and handle refunds.
No effect on live Stripe or production services until explicitly integrated.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Callable, Mapping


class WebhookRejected(ValueError):
    pass


@dataclass(frozen=True)
class PaidCheckout:
    event_id: str
    session_id: str
    customer_id: str
    client_reference_id: str
    stripe_price_id: str
    amount_total: int
    currency: str


def verify_stripe_signature(payload: bytes, signature: str, secret: str,
                            *, clock: Callable[[], int] = lambda: int(time.time()),
                            tolerance_seconds: int = 300) -> dict:
    """Verify raw-body Stripe v1 HMAC and timestamp; fail closed."""
    if not secret or not signature or tolerance_seconds < 0:
        raise WebhookRejected("Missing webhook verification configuration")
    try:
        parts: dict[str, list[str]] = {}
        for pair in signature.split(","):
            k, v = pair.strip().split("=", 1)
            parts.setdefault(k, []).append(v)
        timestamp = int(parts["t"][0])
        candidates = parts["v1"]
    except (KeyError, IndexError, ValueError) as exc:
        raise WebhookRejected("Invalid Stripe signature header") from exc
    if abs(clock() - timestamp) > tolerance_seconds:
        raise WebhookRejected("Expired Stripe signature timestamp")
    expected = hmac.new(secret.encode(), str(timestamp).encode() + b"." + payload,
                        hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, provided) for provided in candidates):
        raise WebhookRejected("Invalid Stripe webhook signature")
    try:
        event = json.loads(payload)
    except (ValueError, UnicodeDecodeError) as exc:
        raise WebhookRejected("Malformed event JSON") from exc
    if not isinstance(event, dict) or not isinstance(event.get("id"), str):
        raise WebhookRejected("Invalid event shape")
    return event


def extract_paid_checkout(
    event: Mapping,
    known_prices: Mapping[str, tuple[str, int, str]],
    *,
    verified_session: Mapping,
    verified_line_items: list[Mapping],
) -> PaidCheckout | None:
    """Extract a paid purchase only from server-fetched Stripe data.

    `verified_session` and `verified_line_items` must be fetched directly
    from Stripe with the backend secret key, never from the webhook JSON,
    client request, session metadata, or frontend state. Price configurations
    map Stripe price ID -> (scope, expected cents, ISO currency).
    One line item with quantity=1 is supported; reject mixed carts.
    Customer identity binding and atomic persistence are separate steps.
    """
    if event.get("type") != "checkout.session.completed":
        return None
    obj = event.get("data", {}).get("object", {})
    if not isinstance(obj, Mapping) or not isinstance(verified_session, Mapping):
        return None
    if not isinstance(verified_line_items, list) or len(verified_line_items) != 1:
        return None
    item = verified_line_items[0]
    if not isinstance(item, Mapping) or not isinstance(item.get("price"), Mapping):
        return None
    price_id = item["price"].get("id")
    plan = known_prices.get(price_id) if isinstance(price_id, str) else None
    if not plan or len(plan) != 3:
        return None
    _, expected_cents, expected_currency = plan
    # Require API-fetched data to match the signed event's Checkout Session ID.
    if (
        obj.get("object") != "checkout.session"
        or not isinstance(obj.get("id"), str)
        or not obj["id"]
        or verified_session.get("id") != obj["id"]
        or verified_session.get("object") != "checkout.session"
        or verified_session.get("mode") != "payment"
        or verified_session.get("payment_status") != "paid"
        or not isinstance(verified_session.get("client_reference_id"), str)
        or not verified_session["client_reference_id"]
        or not isinstance(verified_session.get("customer"), str)
        or not verified_session["customer"]
        or item.get("quantity") != 1
        or type(expected_cents) is not int
        or expected_cents <= 0
        or type(verified_session.get("amount_total")) is not int
        or verified_session["amount_total"] != expected_cents
        or verified_session.get("currency", "").lower() != expected_currency.lower()
        or item["price"].get("unit_amount") != expected_cents
        or item["price"].get("currency", "").lower() != expected_currency.lower()
    ):
        return None
    return PaidCheckout(
        event_id=event["id"],
        session_id=obj["id"],
        customer_id=verified_session["customer"],
        client_reference_id=verified_session["client_reference_id"],
        stripe_price_id=price_id,
        amount_total=expected_cents,
        currency=expected_currency.lower(),
    )
