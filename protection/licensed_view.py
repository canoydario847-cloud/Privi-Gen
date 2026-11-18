"""Privi licensed source-view delivery helper.

Server-side use only. Never place this module's entitlement verifier or secret
credentials in browser code. Viewing source cannot make it uncopyable.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable


class AccessDenied(PermissionError):
    """No verified entitlement to this asset."""


@dataclass(frozen=True)
class Entitlement:
    buyer_id: str
    asset_id: str
    active: bool
    order_id: str


def safe_identifier(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.@-]", "_", value)[:100]


def licensed_view(
    *,
    source: str,
    buyer_id: str,
    asset_id: str,
    entitlement_lookup: Callable[[str, str], Entitlement | None],
    watermark_key: bytes,
    now: datetime | None = None,
) -> tuple[str, dict[str, str]]:
    """Return escaped HTML plus privacy-conscious anti-cache response headers.

    The entitlement_lookup MUST run on the trusted server against a persisted,
    Stripe-webhook-verified purchase, NOT a client-supplied 'paid' flag.
    Source is watermarked only after authorization. Do not deliver full source
    unless selling source access is an explicit part of the purchased license.
    """
    if not watermark_key or len(watermark_key) < 32:
        raise ValueError("Use a random server-side watermark key of >=32 bytes")
    entitlement = entitlement_lookup(buyer_id, asset_id)
    if (
        entitlement is None
        or not entitlement.active
        or entitlement.buyer_id != buyer_id
        or entitlement.asset_id != asset_id
        or not entitlement.order_id
    ):
        raise AccessDenied("Verified purchase required")
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    fingerprint = hmac.new(
        watermark_key,
        f"{buyer_id}\x00{asset_id}\x00{entitlement.order_id}".encode(),
        hashlib.sha256,
    ).hexdigest()[:18]
    mark = f"PRIVI WORLD CORP | LICENSED VIEW | {safe_identifier(buyer_id)} | {safe_identifier(asset_id)} | {fingerprint} | {stamp}"
    # Repeated visible text discourages casual redistribution; not a DRM guarantee.
    numbered = "\n".join(f"{line}  /* {mark} */" for line in source.splitlines())
    content = html.escape(numbered, quote=True)
    label = html.escape(mark, quote=True)
    body = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='robots' content='noindex,nofollow,noarchive'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Privi Licensed View</title>"
        "<style>body{font:14px system-ui;background:#0c1525;color:#e6efff;padding:24px}"
        ".mark{position:sticky;top:0;background:#182b45;padding:12px;overflow-wrap:anywhere}"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.7}</style>"
        "</head><body><div class='mark'>" + label + "</div><pre>" + content + "</pre></body></html>"
    )
    headers = {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "private, no-store, max-age=0",
        "Pragma": "no-cache",
        "X-Robots-Tag": "noindex, nofollow, noarchive",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    }
    return body, headers
