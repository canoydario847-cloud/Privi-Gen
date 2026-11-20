"""Server-authoritative reconciliation of Privi paid access after refunds/disputes.

This is an opt-in *operator/scheduled job* function, NOT an unauthenticated
public webhook endpoint. No Stripe requests are made by this module itself.
All retrieval callbacks must use the Stripe account's server-side API key.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping


def reconcile_checkout(
    session_id: str,
    *,
    store,
    retrieve_session: Callable[[str], Mapping],
    retrieve_payment_intent: Callable[[str], Mapping],
    retrieve_charge: Callable[[str], Mapping],
) -> str:
    """Revoke a held entitlement on a *fully refunded* or disputed payment.

    Only session IDs recorded in Privi's own entitlement database are accepted.
    Verify the authoritative Checkout -> PaymentIntent -> Charge chain with
    exact customer/amount/currency matching before updating permissions.

    Returns: not_found, active, partial_refund, revoked, already_revoked.
    Raises on provider errors or inconsistent data so monitoring can retry.
    A partially refunded purchase is NOT automatically revoked.
    This does not handle subscription, multi-charge or alternative-payment
    arrangements; those require additional provider-specific reconciliation.
    """
    if not isinstance(session_id, str) or not session_id.startswith("cs_"):
        raise ValueError("Invalid checkout session ID")
    purchase = store.purchase_for_session(session_id)
    if purchase is None:
        return "not_found"
    if not isinstance(purchase, Mapping):
        raise ValueError("Invalid stored entitlement")
    session = retrieve_session(session_id)
    if (not isinstance(session, Mapping) or session.get("id") != session_id
            or session.get("object") != "checkout.session"
            or session.get("mode") != "payment"
            or session.get("customer") != purchase["customer_id"]
            or session.get("client_reference_id") != purchase["buyer_id"]
            or type(session.get("amount_total")) is not int
            or session["amount_total"] != purchase["amount_cents"]
            or session.get("currency") != purchase["currency"]):
        raise ValueError("Stripe checkout does not match stored purchase")
    pi_id = session.get("payment_intent")
    if not isinstance(pi_id, str) or not pi_id.startswith("pi_"):
        raise ValueError("PaymentIntent unavailable")
    intent = retrieve_payment_intent(pi_id)
    if (not isinstance(intent, Mapping) or intent.get("id") != pi_id
            or intent.get("object") != "payment_intent"
            or intent.get("customer") != purchase["customer_id"]
            or type(intent.get("amount")) is not int
            or intent["amount"] != purchase["amount_cents"]
            or intent.get("currency") != purchase["currency"]):
        raise ValueError("Stripe PaymentIntent mismatches checkout")
    charge_id = intent.get("latest_charge")
    if not isinstance(charge_id, str) or not charge_id.startswith("ch_"):
        raise ValueError("Charge unavailable")
    charge = retrieve_charge(charge_id)
    if (not isinstance(charge, Mapping) or charge.get("id") != charge_id
            or charge.get("object") != "charge"
            or charge.get("payment_intent") != pi_id
            or type(charge.get("amount")) is not int
            or charge["amount"] != purchase["amount_cents"]
            or charge.get("currency") != purchase["currency"]
            or type(charge.get("amount_refunded")) is not int
            or not (0 <= charge["amount_refunded"] <= charge["amount"])
            or type(charge.get("disputed")) is not bool):
        raise ValueError("Stripe charge mismatches payment")
    if charge["disputed"] or charge["amount_refunded"] == charge["amount"]:
        return "revoked" if store.revoke_session(session_id) else "already_revoked"
    if charge["amount_refunded"] > 0:
        return "partial_refund"
    return "active"
