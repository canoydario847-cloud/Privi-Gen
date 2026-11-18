"""Privi paid API access middleware, framework-neutral ASGI reference.

Wrap protected application *mounts*, not individual discovered tools. The
trusted authentication layer must set scope["state"]["privi_buyer_id"].
Never use a buyer ID from a header, query parameter, cookie string or body.
Never treat this gate as a source-code DRM system.
"""
from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping

ASGIApp = Callable[[dict, Callable, Callable], Awaitable[None]]
INVALID_PATH = re.compile(r"[%\\]|//|/\.{1,2}(?:/|$)")


class PaidAccessGate:
    """Protect one or more exact paths / mount prefixes with entitlements.

    By default, all traffic in a protected prefix requires paid access. Use
    a separate public discovery app (MCP tools/list, docs, public samples).
    If a database or entitlement check fails, the gate returns 503, never
    exposes protected content. This component must be attached *after* the
    authentication middleware that sets the trusted buyer identity.
    """

    def __init__(self, app: ASGIApp, *, protected_mounts: Mapping[str, str],
                 authorized: Callable[[str, str], bool]):
        if not protected_mounts:
            raise ValueError("Provide at least one protected mount")
        self.app = app
        self.authorized = authorized
        self.mounts = []
        for path, asset in protected_mounts.items():
            if not path.startswith("/") or path == "/" or not asset or INVALID_PATH.search(path):
                raise ValueError("Invalid protected mount")
            self.mounts.append((path.rstrip("/"), asset))
        self.mounts.sort(key=lambda pair: len(pair[0]), reverse=True)

    async def __call__(self, scope: dict, receive: Callable, send: Callable):
        if scope.get("type") != "http":
            # Not a WebSocket guard; do not mount premium WS routes here.
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if not isinstance(path, str):
            await self._reply(send, 400, b"Invalid path")
            return
        match = next(((mount, asset) for mount, asset in self.mounts
                      if path == mount or path.startswith(mount + "/")), None)
        if not match:
            await self.app(scope, receive, send)
            return
        if INVALID_PATH.search(path):
            await self._reply(send, 400, b"Invalid path")
            return
        state = scope.get("state")
        buyer_id = state.get("privi_buyer_id") if isinstance(state, dict) else None
        if not isinstance(buyer_id, str) or not buyer_id.strip():
            await self._reply(send, 401, b"Authentication required")
            return
        try:
            allowed = self.authorized(buyer_id, match[1])
        except Exception:
            await self._reply(send, 503, b"Entitlement verification unavailable")
            return
        if allowed is not True:
            await self._reply(send, 403, b"Verified Privi purchase required")
            return
        await self.app(scope, receive, send)

    @staticmethod
    async def _reply(send: Callable, status: int, body: bytes):
        await send({"type": "http.response.start", "status": status, "headers": [
            (b"content-type", b"text/plain; charset=utf-8"),
            (b"cache-control", b"no-store"),
            (b"x-content-type-options", b"nosniff"),
        ]})
        await send({"type": "http.response.body", "body": body})
