# Paid entitlement refund/dispute reconciliation (prelaunch)

`protection.refund_reconciliation.reconcile_checkout` is an **opt-in trusted
operator job**, not an internet-facing route. It checks a previously granted
checkout's **server-fetched** Stripe Checkout Session, PaymentIntent and
latest Charge IDs, customer, price, currency, full refund amount and dispute
status against immutable purchase fields stored in PostgreSQL.

A **full refund** or flagged **dispute** revokes access; a partial refund
requires an explicit business policy and does not revoke automatically.
Duplicate reconciliation is safe, and replays of the original completed
checkout do not re-grant a revoked entitlement.

Integration requirements:
- Provide real Stripe server-side API callbacks from a trusted backend.
  Never accept caller-supplied payment objects as authoritative.
- Run reconciliation on an authenticated job queue for owned purchases and
  alert on mismatches, unavailable provider data and repeated failures.
- Review partial refunds, resolved/won disputes, multi-charge transactions,
  payment-method variants and subscriptions separately; this module does not
  automatically restore entitlements.
- A refund or dispute *before* the first grant still needs a pre-grant
  provider-status check or durable deny-first tombstone; this module is
  post-grant reconciliation and does not solve that race.
- Do not expose reconciliation or grant operations as public HTTP endpoints.
- No production Stripe/Render/customer or PRVI chain changes occur here.

The corresponding CI integration suite uses a disposable PostgreSQL 16
instance and synthetic provider responses; it is not a live Stripe refund test.
