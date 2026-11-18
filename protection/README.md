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
