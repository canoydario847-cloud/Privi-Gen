"""Fail-closed glue for Stripe checkout and Privi paid entitlements.

This is an integration seam, NOT an HTTP endpoint. The caller must verify
the signature on the raw webhook body, fetch the session and ALL line items
directly from Stripe, and look up the buyer bound at checkout creation in its
own trusted server database. Never construct these values from browser input.
"""
from __future__ import annotations

from collections.abc import Mapping

from .entitlement_store import EntitlementStore, PricePlan
from .stripe_entitlements import extract_paid_checkout, verify_stripe_signature


def fulfill_verified_checkout(
    *,
    payload: bytes,
    signature: str,
    webhook_secret: str,
    verified_session: Mapping,
    verified_line_items: list[Mapping],
    checkout_buyer_id: str,
    price_allowlist: Mapping[str, PricePlan],
    store: EntitlementStore,
    clock=None,
) -> bool:
    """Grant at most once for an authenticated, server-bound Stripe checkout.

    Returns False for non-paid, unknown-price and malformed checkouts. Raises
    on invalid webhook signature, wrong buyer, or a conflicting replay.
    Replayed *identical* checkouts return False and cannot resurrect revocations.
    """
    kwargs = {"clock": clock} if clock is not None else {}
    event = verify_stripe_signature(payload, signature, webhook_secret, **kwargs)
    if not isinstance(checkout_buyer_id, str) or not checkout_buyer_id.strip():
        raise ValueError("Checkout has no trusted buyer binding")
    if not price_allowlist or not all(
        isinstance(price, str) and price.strip()
        and isinstance(plan, PricePlan)
        and isinstance(plan.scope, str) and plan.scope.strip()
        and type(plan.amount_cents) is int and plan.amount_cents > 0
        and isinstance(plan.currency, str) and plan.currency.lower() == "usd"
        for price, plan in price_allowlist.items()
    ):
        raise ValueError("Invalid server-owned Stripe price allowlist")
    known_prices = {
        price: (plan.scope, plan.amount_cents, plan.currency)
        for price, plan in price_allowlist.items()
    }
    purchase = extract_paid_checkout(
        event,
        known_prices,
        verified_session=verified_session,
        verified_line_items=verified_line_items,
    )
    if purchase is None:
        return False
    plan = price_allowlist[purchase.stripe_price_id]
    if purchase.client_reference_id != checkout_buyer_id:
        raise ValueError("Checkout buyer does not match server binding")
    return store.grant(purchase, checkout_buyer_id, plan)
