"""Server-side Stripe retrieval adapter for Privi's verified checkout flow.

The caller supplies functions bound to a server-side Stripe API client, never
client-provided data. This module performs no network operations on import.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from .checkout_fulfillment import fulfill_bound_checkout
from .entitlement_store import PricePlan
from .stripe_entitlements import verify_stripe_signature


def fulfill_from_stripe_api(
    *, payload: bytes, signature: str, webhook_secret: str,
    retrieve_session: Callable[[str], Mapping],
    list_line_items: Callable[[str], Mapping],
    bindings, store, price_allowlist: Mapping[str, PricePlan], clock=None,
) -> bool:
    """Verify the webhook before any Stripe API call or database lookup.

    Expected callbacks perform authenticated Stripe API requests with a
    server-held key: checkout.sessions.retrieve(session_id) and
    checkout.sessions.list_line_items(session_id, limit=2). Convert Stripe
    objects to ordinary dicts in the caller. Refuse paginated/multi-item
    carts, rather than granting access from an incomplete first page.

    Return False on unrelated signed events; raise on bad signatures and
    incomplete or untrusted fetched objects so webhook handlers can retry.
    """
    kwargs = {"clock": clock} if clock is not None else {}
    event = verify_stripe_signature(payload, signature, webhook_secret, **kwargs)
    if event.get("type") != "checkout.session.completed":
        return False
    data = event.get("data")
    obj = data.get("object") if isinstance(data, Mapping) else None
    if not isinstance(obj, Mapping) or obj.get("object") != "checkout.session":
        raise ValueError("Missing signed Checkout Session")
    session_id = obj.get("id")
    if not isinstance(session_id, str) or not session_id.startswith("cs_"):
        raise ValueError("Invalid signed Checkout Session ID")
    if not callable(retrieve_session) or not callable(list_line_items):
        raise ValueError("Server Stripe API callbacks required")
    session = retrieve_session(session_id)
    if not isinstance(session, Mapping) or session.get("id") != session_id:
        raise ValueError("Stripe session lookup mismatch")
    page = list_line_items(session_id)
    if not isinstance(page, Mapping) or page.get("has_more") is not False:
        raise ValueError("Stripe line items must be fully retrieved")
    items = page.get("data")
    if not isinstance(items, list) or len(items) != 1:
        raise ValueError("Exactly one complete Stripe line item required")
    return fulfill_bound_checkout(
        payload=payload, signature=signature, webhook_secret=webhook_secret,
        verified_session=session, verified_line_items=items,
        bindings=bindings, store=store,
        price_allowlist=price_allowlist, clock=clock,
    )
