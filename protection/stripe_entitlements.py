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


def extract_paid_checkout(event: Mapping, known_prices: Mapping[str, str]) -> PaidCheckout | None:
    """Return verified paid checkout metadata only for an allowlisted price.

    Caller must retrieve Checkout Session line items from Stripe with its
    server credential and pass their authoritative price ID as known_prices
    mapping context, or populate it from a trusted Stripe API retrieval.
    Do not use browser metadata or client-provided price values.
    """
    if event.get("type") != "checkout.session.completed":
        return None
    obj = event.get("data", {}).get("object", {})
    if (obj.get("object") != "checkout.session"
        or obj.get("mode") != "payment"
        or obj.get("payment_status") != "paid"
        or not obj.get("client_reference_id")
        or not obj.get("customer")
        or not obj.get("id")
        or not isinstance(obj.get("amount_total"), int)
        or obj.get("amount_total") < 0
        or not isinstance(obj.get("currency"), str)):
        return None
    # A Stripe webhook checkout session does not normally include its line
    # items. Require the integration's server-verified line-item price ID.
    price_id = obj.get("_server_verified_price_id")
    if not isinstance(price_id, str) or price_id not in known_prices:
        return None
    return PaidCheckout(
        event_id=event["id"], session_id=obj["id"],
        customer_id=obj["customer"],
        client_reference_id=obj["client_reference_id"],
        stripe_price_id=price_id, amount_total=obj["amount_total"],
        currency=obj["currency"].lower(),
    )
