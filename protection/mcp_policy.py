"""Fail-closed authorization policy for MCP JSON-RPC requests.

Invoke this on the parsed JSON-RPC request inside the MCP handler, before
executing any tool, reading protected resources, or starting paid prompts.
It does not authenticate identities itself and is not an HTTP middleware.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass


PUBLIC_METHODS = frozenset({
    "initialize", "notifications/initialized", "ping", "tools/list",
})


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    scope: str | None = None


class MCPAccessPolicy:
    """Explicitly map paid tools to entitlements; unknown methods fail closed."""

    def __init__(
        self,
        *,
        tool_scopes: Mapping[str, str],
        authorized: Callable[[str, str], bool],
        public_methods: frozenset[str] = PUBLIC_METHODS,
    ):
        if not tool_scopes:
            raise ValueError("At least one protected tool is required")
        if not all(
            isinstance(name, str) and name.strip()
            and isinstance(scope, str) and scope.strip()
            for name, scope in tool_scopes.items()
        ):
            raise ValueError("Every paid tool must have an explicit scope")
        if not public_methods.issubset(PUBLIC_METHODS):
            raise ValueError("Cannot allow additional methods through discovery")
        self.tool_scopes = dict(tool_scopes)
        self.authorized = authorized
        self.public_methods = public_methods

    def decide(self, request: object, *, buyer_id: str | None) -> Decision:
        """Return decision for one parsed JSON-RPC message.

        The caller must derive buyer_id from verified server-side auth, never
        JSON-RPC params, headers chosen by clients, or query parameters.
        Reject batch requests and JSON-RPC method names not explicitly known.
        Other MCP handlers (resources/read, prompts/get, etc.) need dedicated
        scoped authorization and must not bypass this check.
        """
        if not isinstance(request, dict):
            return Decision(False, "invalid_request")
        if request.get("jsonrpc") != "2.0":
            return Decision(False, "invalid_jsonrpc")
        method = request.get("method")
        if not isinstance(method, str) or not method:
            return Decision(False, "invalid_method")
        if method in self.public_methods:
            return Decision(True, "public_discovery")
        if method != "tools/call":
            return Decision(False, "unrecognized_or_protected_method")
        params = request.get("params")
        if not isinstance(params, dict):
            return Decision(False, "invalid_params")
        name = params.get("name")
        if not isinstance(name, str):
            return Decision(False, "missing_tool_name")
        scope = self.tool_scopes.get(name)
        if scope is None:
            return Decision(False, "unknown_tool")
        if not isinstance(buyer_id, str) or not buyer_id.strip():
            return Decision(False, "authentication_required", scope)
        try:
            allowed = self.authorized(buyer_id, scope)
        except Exception:
            return Decision(False, "authorization_unavailable", scope)
        if allowed is not True:
            return Decision(False, "purchase_required", scope)
        return Decision(True, "authorized", scope)
