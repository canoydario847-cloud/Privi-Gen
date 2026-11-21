"""Opt-in Privi staging webhook ASGI adapter.

Not deployed or enabled by the default staging_app.app. Callers must inject a
server-held Stripe webhook secret, server API callbacks, a trusted customer
binding store, and a durable entitlement backend. Never expose fixture keys.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping

from .staging_app import create_app, _reply
from .stripe_api_adapter import fulfill_from_stripe_api
from .stripe_entitlements import WebhookRejected, verify_stripe_signature
from .payment_reversal_adapter import SUPPORTED, process_verified_payment_reversal

MAX_BODY = 65536


def create_staging_webhook_app(
    *, webhook_secret: str, retrieve_session: Callable, list_line_items: Callable,
    bindings, store, price_allowlist: Mapping, clock=None,
    retrieve_charge=None, retrieve_payment_intent=None, list_checkout_sessions=None,
):
    """Mount an explicit, signature-checked webhook alongside paid demo routes."""
    if not isinstance(webhook_secret, str) or not webhook_secret.strip():
        raise ValueError("Staging webhook secret is required")
    if not callable(retrieve_session) or not callable(list_line_items):
        raise ValueError("Server-only Stripe retrieval callbacks required")
    if not callable(getattr(store, "authorized", None)):
        raise ValueError("Entitlement backend required")
    if not callable(getattr(bindings, "buyer_for", None)):
        raise ValueError("Trusted checkout bindings required")
    reversal_callbacks = (retrieve_charge, retrieve_payment_intent, list_checkout_sessions)
    if any(callback is not None for callback in reversal_callbacks):
        if not all(callable(callback) for callback in reversal_callbacks):
            raise ValueError("All reversal callbacks required")
        if not all(callable(getattr(store, name, None)) for name in
                   ("purchase_for_session", "block_session")):
            raise ValueError("Reversal-capable entitlement backend required")
    paid_app = create_app(authorized=store.authorized)

    async def app(scope, receive, send):
        if scope.get("type") != "http" or scope.get("path") != "/staging/stripe-webhook":
            await paid_app(scope, receive, send)
            return
        if scope.get("raw_path", b"/staging/stripe-webhook") != b"/staging/stripe-webhook":
            await _reply(send, 400, {"error": "invalid_path"})
            return
        if scope.get("method") != "POST":
            await _reply(send, 405, {"error": "method_not_allowed"})
            return
        headers = scope.get("headers", [])
        sigs = [v for k, v in headers if k.lower() == b"stripe-signature"]
        if len(sigs) != 1:
            await _reply(send, 400, {"error": "invalid_signature"})
            return
        try:
            signature = sigs[0].decode("ascii")
        except (UnicodeError, AttributeError):
            await _reply(send, 400, {"error": "invalid_signature"})
            return
        body = bytearray()
        while True:
            item = await receive()
            if item.get("type") != "http.request":
                await _reply(send, 400, {"error": "invalid_request"})
                return
            chunk = item.get("body", b"")
            if not isinstance(chunk, bytes) or len(body) + len(chunk) > MAX_BODY:
                await _reply(send, 413, {"error": "payload_too_large"})
                return
            body.extend(chunk)
            if not item.get("more_body", False):
                break
        try:
            kwargs = {"clock": clock} if clock is not None else {}
            event = verify_stripe_signature(bytes(body), signature, webhook_secret, **kwargs)
            if event.get("type") in SUPPORTED:
                if not all(callable(callback) for callback in reversal_callbacks):
                    raise RuntimeError("Reversal processing not configured")
                reversal = process_verified_payment_reversal(
                    payload=bytes(body), signature=signature,
                    webhook_secret=webhook_secret, bindings=bindings, store=store,
                    retrieve_charge=retrieve_charge,
                    retrieve_payment_intent=retrieve_payment_intent,
                    list_checkout_sessions=list_checkout_sessions, clock=clock,
                )
                await _reply(send, 200, {"accepted": True, "reversal": reversal})
                return
            result = fulfill_from_stripe_api(
                payload=bytes(body), signature=signature,
                webhook_secret=webhook_secret,
                retrieve_session=retrieve_session, list_line_items=list_line_items,
                bindings=bindings, store=store, price_allowlist=price_allowlist,
                clock=clock,
            )
        except WebhookRejected:
            await _reply(send, 400, {"error": "invalid_signature_or_event"})
            return
        except Exception:
            # Incomplete provider responses, SQL outages and identity conflicts
            # should retry; do not expose internals or claim a purchase.
            await _reply(send, 503, {"error": "fulfillment_unavailable"})
            return
        await _reply(send, 200, {"accepted": True, "new_entitlement": result is True})

    return app
