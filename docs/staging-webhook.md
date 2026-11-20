# Privi synthetic Stripe webhook staging service

This opt-in staging application is **not deployed** and is separate from
the default `protection.staging_app:app`, which continues to deny all
paid requests. Use `create_staging_webhook_app(...)` in a trusted,
isolated test harness, injecting a server-held webhook secret, real
server-only Stripe Checkout retrieval callbacks, immutable checkout
bindings, and the PostgreSQL entitlement store.

The `/staging/stripe-webhook` endpoint accepts only POST and validates
the raw Stripe signature before contacting Stripe's API. It limits
request bodies to 64 KiB and rejects missing or duplicate signature headers.
A verified completed checkout with a trusted existing buyer binding and a
single allowlisted item grants access; duplicate events are idempotent.
Operational failures respond 503 so the provider may retry, without
leaking database or Stripe details. The `/premium/*` routes remain
synthetic placeholders; they are **not** Call Proof or Guard execution.

Never set up production traffic using the synthetic fixtures in tests.
Before deploying even to an internet-facing staging host, implement trusted
session identity, Stripe test-mode API credentials with secure secret storage,
a persistent test PostgreSQL instance, secure TLS/reverse proxy rules, and
rate limiting. Review refund/dispute notification reconciliation separately.
This module does not change live billing, customer permissions, or PRVI mainnet.

If a *signed paid* Checkout session arrives before its trusted customer binding exists, the webhook responds with a retryable HTTP 503 rather than acknowledging it as complete. Investigate repeated 503s and reconcile payment/account state; do not bind accounts from webhook payloads.
