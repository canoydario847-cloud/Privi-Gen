# Signed payment reversal ingestion adapter (prelaunch)

The `process_verified_payment_reversal` function verifies the raw Stripe
event HMAC before fetching any payment or account data. For a supported
`charge.refunded`, `charge.dispute.created` or
`charge.dispute.updated` event, it uses **trusted server-side Stripe API**
callbacks to retrieve a Charge and PaymentIntent and find exactly one
Checkout Session for that PaymentIntent. It validates customer identity,
amount, currency, session-to-buyer binding and any pre-existing grant.

Full refunds and active disputes call the PostgreSQL `block_session`
tombstone mechanism, including before the initial checkout is granted.
Partial refunds are returned for separate operator review.
Unavailable buyer binding or inconsistent API evidence must trigger a
retry; never infer an account from Stripe-supplied metadata.

**This is not a mounted HTTP endpoint or production Stripe integration.**
The host must provide authenticated Stripe API callbacks, webhook request
body/signature handling, durable migrations, monitoring/reconciliation
and secure server credentials. The tests use synthetic Stripe payloads
with real ephemeral CI PostgreSQL only. Operational review is required
for reopened disputes, charge history, unusual payment methods, and
refund-related event types not covered by this adapter.
