# Verified refunds arriving before entitlement grants (prelaunch)

The PostgreSQL entitlement backend now supports `block_session(session_id,
reason)` for **server-verified** full refunds and disputed charges that may
arrive before a checkout-completed webhook. The persistent
`privi_blocked_checkouts` table prevents subsequent grants for that checkout.

`grant()` and `block_session()` share a PostgreSQL transaction advisory
lock keyed to the Checkout session. This serializes concurrent webhook
deliveries and blocks, including the first grant. An existing grant is
revoked when a block arrives. Blocks are deliberately never undone by a
duplicate successful-checkout event.

**Important:** No Stripe refund/dispute event ingestion is wired up yet.
Only a trusted operator or backend reconciler, after authenticating the event
and verifying the Charge/PaymentIntent/Checkout chain directly with Stripe,
may call this function. Never accept browser-supplied session IDs or
unverified refund status. The original `revoke_session` API still handles
known entitlement revocation; prefer `block_session` for authoritative
refund/dispute events that can precede a grant.

Apply the revised `SCHEMA_SQL` using a reviewed migration, test against a
durable database and install an authoritative refund/dispute event handler
before production launch. The tests use only a disposable GitHub Actions
PostgreSQL instance and synthetic purchases.
