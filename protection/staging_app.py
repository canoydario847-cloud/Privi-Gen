"""Minimal Privi paid-access ASGI staging demo, fail-closed by default.

Run locally: python -m pip install uvicorn
             uvicorn protection.staging_app:app --host 127.0.0.1 --port 8000

The default app has no buyer authentication or grant source and deliberately
DENIES all paid endpoints. An authenticated host application may construct
create_app(authorized=...) and set scope['state']['privi_buyer_id'] itself after
server-side session validation. Never trust an X-Buyer-ID header.
"""
from __future__ import annotations

import json
from collections.abc import Callable

from .asgi_gate import PaidAccessGate


async def _reply(send, status: int, body: dict):
    raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", b"application/json; charset=utf-8"),
            (b"cache-control", b"no-store"),
            (b"x-content-type-options", b"nosniff"),
        ],
    })
    await send({"type": "http.response.body", "body": raw})


def create_app(*, authorized: Callable[[str, str], bool] | None = None):
    """Create a minimal staging app. All unknown routes are denied.

    Authorization must be a server-trusted entitlement lookup; by default,
    paid access is denied even when clients forge identity headers or cookies.
    """
    if authorized is None:
        authorized = lambda _buyer, _scope: False
    if not callable(authorized):
        raise ValueError("Authorization function must be callable")

    async def routes(scope, receive, send):
        if scope.get("type") != "http":
            return
        path = scope.get("path")
        method = scope.get("method")
        if path == "/health" and method == "GET":
            await _reply(send, 200, {"status": "ok", "mode": "staging", "payments": "disabled"})
        elif path == "/catalog" and method == "GET":
            await _reply(send, 200, {
                "service": "Privi paid-access staging",
                "discovery": "public",
                "tools": ["call_proof", "guard"],
                "execution": "requires authenticated purchase",
            })
        elif path == "/premium/callproof" and method == "POST":
            await _reply(send, 200, {"service": "call_proof", "result": "synthetic-authorized-demo"})
        elif path == "/premium/guard" and method == "POST":
            await _reply(send, 200, {"service": "guard", "result": "synthetic-authorized-demo"})
        else:
            await _reply(send, 404, {"error": "not_found"})

    return PaidAccessGate(
        routes,
        protected_mounts={"/premium/callproof": "call_proof", "/premium/guard": "guard"},
        authorized=authorized,
        public_mounts=("/health", "/catalog"),
        deny_unmapped=True,
    )


app = create_app()
