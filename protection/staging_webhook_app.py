"""Opt-in Privi staging webhook ASGI adapter.

Not deployed or enabled by the default staging_app.app. Callers must inject a
server-held Stripe webhook secret, server API callbacks, a trusted customer
binding store, and a durable entitlement backend. Never expose fixture keys.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping

from .staging_app import create_app, _reply
from .stripe_api_adapter import fulfill_from_stripe_api
from .stripe_entitlements import WebhookRejected

MAX_BODY = 65536


def create_staging_webhook_app(
    *, webhook_secret: str, retrieve_session: Callable, list_line_items: Callable,
    bindings, store, price_allowlist: Mapping, clock=None,
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
    paid_app = create_app(authorized=store.authorized)

    async def app(scope, receive, send):
        if scope.get("type") != "http" or scope.get("path") != "/staging/stripe-webhook":
            await paid_app(scope, receive, send)
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
