# Privi commercial source protection — deployment checklist

**Status: reusable implementation committed to Privi-Gen; NOT installed on every Privi production endpoint.**

Privi's public GitHub repositories already expose their source and commit history. Watermarks, disabling right-click, minification and `robots.txt` cannot take that source back or make rendered code uncopyable. Do not promise buyers technical impossibility of copying.

## Protection policy

1. **Before payment:** show only product description, API schema, marketing demos and intentionally public open-source modules. Keep proprietary implementations in *private* repositories and on the server. Review existing licenses and dependencies before changing repository visibility or removing anything. Do not put source, maps, secrets or private logic in static-site JS, container images or public CI artifacts.
2. **Purchase:** use signed Stripe webhooks, verify signature using the raw request body, fetch authoritative transaction status, and persist an idempotent entitlement tied to the authenticated buyer and product. $19.99 single-service and $35 one-time Pro purchases should retain their purchased scope. Do not trust success redirect, query parameters or browser state.
3. **After payment:** default to providing API/tool access rather than source files. Authenticated requests require active entitlements; check every request server-side. Never expose developer credentials. If source viewing is a *separate expressly licensed offer*, use `protection/licensed_view.py` from a server route with a server-held HMAC key and a real entitlement lookup.
4. **Watermarks:** add a Privi World Corp ownership notice to pages, reports, videos, PDF exports, source-view pages, and customer artifacts. For exports, add per-buyer license ID/order fingerprint and delivery timestamp; avoid exposing personal emails to other viewers. Keep origin metadata inside downloadable files where possible. Branding can be removed and does not replace access control.
5. **Reuse:** add license terms, permitted use, prohibition on redistribution where enforceable, and copyright attribution. Preserve third-party open-source license notices and obligations.
6. **Audit:** inventory public GitHub content and git history, published packages, build artifacts, static JS bundles, and exposed sourcemaps. If secrets were leaked, rotate them immediately; making a repo private is insufficient.

## Integration example (Python)

```python
from protection.licensed_view import licensed_view, Entitlement
# Your backend resolves user identity from an authenticated session.
# Your server-side lookup must consult verified, persisted Stripe entitlements.
page, headers = licensed_view(
    source=private_source_from_server,
    buyer_id=session.user_id,
    asset_id="approved-source-view-product",
    entitlement_lookup=database_verified_entitlement_lookup,
    watermark_key=server_secret_from_environment,
)
return Response(page, headers=headers, media_type="text/html")
```

Do not call this function in a public repo script with sensitive source contents. Only mount it behind authentication in an authorized service. Neither the snippet nor this repository change modifies Stripe, Render, other repos, or existing live payment/access flows.

**Blockchain note:** public validator nodes and independently verifiable network protocol behavior must remain auditable; do not gate required protocol verification behind a purchase.

## Stripe webhook adapter foundation (added November 18, 2026)

`protection/stripe_entitlements.py` verifies Stripe's raw-body `Stripe-Signature` header and rejects expired or modified signatures, then extracts an eligible paid Checkout Session when an **allowlisted, server-verified Stripe line-item price** is provided. `tests/test_stripe_entitlements.py` contains unit tests; CI execution is not verified.

**Required before enabling fulfillment:** retrieve Checkout Session and line items from the Stripe API using server credentials; validate expected price ID, amount, currency, mode and paid status; independently bind `client_reference_id` to the authenticated customer's account (do not trust it alone); persist event ID and session ID atomically to prevent duplicates; map purchased prices to individual service or $35 unlimited access; handle asynchronous checkout events, chargebacks, refunds, account revocation and webhook retries. Never log full payment payloads or secrets. No production webhook endpoint has been modified by this foundation.


## Entitlement storage reference (November 18, 2026)

`protection/entitlement_store.py` provides a local SQLite reference: atomic per-Checkout-Session grants, replay conflict rejection, scoped single-service purchases, $35 all-services scope, and explicit session revocation. It is **not a production database**. Deploy with a durable, shared PostgreSQL implementation and ensure refund/dispute events and administrator revocations are verified before changing records. Tests live at `tests/test_entitlement_store.py`.

The hardened `extract_paid_checkout` now requires two **separately retrieved, authoritative Stripe API objects**: `verified_session` and `verified_line_items`. A webhook's hidden/custom `_server_verified_price_id` or browser parameter is never trusted. Configure the allowlist of Stripe price IDs and exact charge totals from the actual Stripe account. Do not guess price IDs from checkout link URLs.

**No live deployment or customer unlock is claimed.** Before launch: (a) authenticate the buyer when creating Checkout, (b) persist their account-bound session ID, (c) verify webhook and retrieve Stripe objects, (d) confirm the session belongs to that account, (e) process grants idempotently in a shared database, (f) wire every protected tool endpoint to that database, (g) test payment, replay, refund and chargeback flows, and (h) verify no proprietary source code leaks through public repos or static bundles.


## ASGI paid API gate (November 18, 2026)

`protection/asgi_gate.py` is a framework-neutral ASGI middleware reference. It requires a trusted, authenticated `scope["state"]["privi_buyer_id"]`, checks the entitled service scope with a server-side `authorized(buyer_id, scope)` callback, and returns 401 (missing identity), 403 (not paid) or 503 (entitlement backend unavailable), without exposing protected content. Paths are protected by mount prefix; the longest configured prefix wins. Public onboarding/discovery routes must live outside these mounts.

Example (illustrative only, after authenticated buyer session and a shared durable database are configured):

```python
from protection.asgi_gate import PaidAccessGate

paid_app = PaidAccessGate(
    premium_asgi_app,
    protected_mounts={
        "/premium": "all_tools",
        "/premium/callproof": "call_proof",
    },
    authorized=production_entitlement_store.authorized,
)
# Install after authentication middleware, or ensure trusted state is set.
```

**Critical:** This is not currently installed on Render, and an ASGI gate is not sufficient to protect raw source embedded in browser bundles or public GitHub history. Ensure every premium endpoint (including WebSocket/streaming endpoints) is protected by its own appropriate authorization controls. Public discovery should remain accessible. Test with real Stripe test-mode sessions, refund and replay events, and an account with no paid entitlements before connecting live checkout. Do not place source-viewing services or secrets in public repos.

Tests: `python -m unittest discover -s tests -p 'test_asgi_gate.py' -v`. GitHub Actions runs this when configured; execution success must be verified separately.

## Strict route allowlist (security hardening, November 18, 2026)

The paid ASGI gate now supports `deny_unmapped=True` with explicit `public_mounts`. This is safer for a new private service than allowing all routes outside the protected premium prefixes, because a newly added developer/debug/administrative endpoint cannot silently become public.

```python
PaidAccessGate(
    authenticated_asgi_app,
    protected_mounts={"/premium": "all_tools", "/premium/callproof": "call_proof"},
    public_mounts=("/health", "/mcp/discovery"),
    deny_unmapped=True,
    authorized=durable_entitlements.authorized,
)
```

Only list genuinely public endpoints. In particular, a public MCP tools/list or initialize response is **not** the same as a free tools/call operation; multiplexed JSON-RPC POST routes require **per-method authorization in the MCP handler**, not just this path middleware. Do not deploy an unprotected shared `/mcp` route because discovery is public. Explicitly protect REST, WebSocket and streaming routes and any admin/debug/metrics paths. Test reverse-proxy path normalization, percent-encoding and authentication middleware order. Changing `deny_unmapped` to true in a production service requires a route inventory and integration test first; the library default remains compatible with existing deployments.

This code is a reference guard and is not proof of penetration-testing or operational certification. GitHub checks and deployment status must be verified independently.
