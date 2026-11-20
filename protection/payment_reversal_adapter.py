"""Verified Stripe refund/dispute event adapter for Privi paid access.

Prelaunch pure adapter. The caller MUST supply Stripe server-secret-backed API
callbacks; never accept arbitrary request objects or allow HTTP callers to
select the checkout to revoke. This does not run by itself or change live API.
"""
from __future__ import annotations
from collections.abc import Callable, Mapping
from .stripe_entitlements import verify_stripe_signature

SUPPORTED = {"charge.refunded", "charge.dispute.created", "charge.dispute.updated"}


def process_verified_payment_reversal(
    *, payload: bytes, signature: str, webhook_secret: str, bindings, store,
    retrieve_charge: Callable[[str], Mapping],
    retrieve_payment_intent: Callable[[str], Mapping],
    list_checkout_sessions: Callable[[str], Mapping], clock=None,
) -> str:
    """Check an authoritative Charge->Intent->Checkout chain and block grants.

    Callbacks retrieve the Charge and PaymentIntent using Stripe's secret key
    and list Checkout Sessions filtered by payment_intent, using a limit of 2.
    Return ignored, active, partial_refund, blocked or already_blocked.
    Raise on invalid signatures, ambiguous Stripe records and absent binding
    so the webhook handler can retry instead of acknowledging unsafe events.
    """
    kwargs = {"clock": clock} if clock is not None else {}
    event = verify_stripe_signature(payload, signature, webhook_secret, **kwargs)
    event_type = event.get("type")
    if event_type not in SUPPORTED:
        return "ignored"
    obj = (event.get("data") or {}).get("object") if isinstance(event.get("data"), Mapping) else None
    if not isinstance(obj, Mapping):
        raise ValueError("Signed reversal has no object")
    if event_type == "charge.refunded":
        charge_id = obj.get("id") if obj.get("object") == "charge" else None
    else:
        charge_id = obj.get("charge") if obj.get("object") == "dispute" else None
    if not isinstance(charge_id, str) or not charge_id.startswith("ch_"):
        raise ValueError("Invalid reversal charge")
    charge = retrieve_charge(charge_id)
    if (not isinstance(charge, Mapping) or charge.get("object") != "charge"
            or charge.get("id") != charge_id
            or not isinstance(charge.get("payment_intent"), str)
            or not charge["payment_intent"].startswith("pi_")
            or type(charge.get("amount")) is not int or charge["amount"] <= 0
            or type(charge.get("amount_refunded")) is not int
            or not 0 <= charge["amount_refunded"] <= charge["amount"]
            or type(charge.get("disputed")) is not bool
            or not isinstance(charge.get("currency"), str)):
        raise ValueError("Authoritative charge invalid")
    if event_type == "charge.refunded" and charge["amount_refunded"] == 0:
        raise ValueError("Refund event not reflected in Stripe charge")
    if event_type.startswith("charge.dispute.") and charge["disputed"] is not True:
        raise ValueError("Dispute not reflected in Stripe charge")
    pi_id = charge["payment_intent"]
    intent = retrieve_payment_intent(pi_id)
    if (not isinstance(intent, Mapping) or intent.get("object") != "payment_intent"
            or intent.get("id") != pi_id or intent.get("latest_charge") != charge_id
            or type(intent.get("amount")) is not int
            or intent["amount"] != charge["amount"]
            or intent.get("currency") != charge["currency"]
            or not isinstance(intent.get("customer"), str)
            or not intent["customer"]):
        raise ValueError("PaymentIntent and charge mismatch")
    page = list_checkout_sessions(pi_id)
    if not isinstance(page, Mapping) or page.get("has_more") is not False:
        raise ValueError("Checkout lookup must be complete")
    sessions = page.get("data")
    if not isinstance(sessions, list) or len(sessions) != 1:
        raise ValueError("Expected one unambiguous Checkout session")
    session = sessions[0]
    if (not isinstance(session, Mapping) or session.get("object") != "checkout.session"
            or not isinstance(session.get("id"), str)
            or not session["id"].startswith("cs_")
            or session.get("mode") != "payment"
            or session.get("payment_intent") != pi_id
            or session.get("customer") != intent["customer"]
            or type(session.get("amount_total")) is not int
            or session["amount_total"] != charge["amount"]
            or session.get("currency") != charge["currency"]):
        raise ValueError("Checkout does not match charge")
    session_id = session["id"]
    buyer = bindings.buyer_for(session_id)
    if not isinstance(buyer, str) or not buyer.strip():
        raise ValueError("Trusted checkout buyer binding is not ready")
    if session.get("client_reference_id") != buyer:
        raise ValueError("Checkout account mismatch")
    # If the original grant exists, verify it also matches the provider.
    purchase = store.purchase_for_session(session_id)
    if purchase is not None and (
        purchase["buyer_id"] != buyer
        or purchase["customer_id"] != session["customer"]
        or purchase["amount_cents"] != session["amount_total"]
        or purchase["currency"] != session["currency"]
    ):
        raise ValueError("Stored entitlement does not match verified purchase")
    if charge["disputed"] is True:
        return "blocked" if store.block_session(session_id, "dispute") else "already_blocked"
    if charge["amount_refunded"] == charge["amount"]:
        return "blocked" if store.block_session(session_id, "full_refund") else "already_blocked"
    if charge["amount_refunded"] > 0:
        return "partial_refund"
    return "active"
