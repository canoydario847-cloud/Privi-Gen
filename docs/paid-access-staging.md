# Privi paid-access staging demonstration

This is a **runnable, synthetic staging example**, not a deployed payment
service. It requires no Stripe API key or database and does not grant paid
access by default.

## Run locally

```sh
python -m pip install uvicorn
uvicorn protection.staging_app:app --host 127.0.0.1 --port 8000
curl -i http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/catalog
curl -i -X POST http://127.0.0.1:8000/premium/callproof
```

Expected: health/catalog 200; anonymous premium requests 401. Forged
`X-Buyer-ID` headers do not authenticate the caller. Even if the hosting
framework supplies a buyer identity, the default configuration refuses all
paid requests (403) because it has no verified entitlement backend.

`create_app(authorized=...)` accepts an authorized(buyer_id, scope) function
backed by a trusted PostgreSQL entitlement store. The trusted host is
responsible for authenticating the session and setting the ASGI
`scope["state"]["privi_buyer_id"]` **after** validating it server-side.
Never derive buyer identity from a plain browser header or query string.

The premium routes produce **synthetic test responses**, not real Guard or
Call Proof services. To use the staging example as the start of a real paid
service, replace demo handlers with actual protected functions, integrate a
secure identity provider, server-only checkout creation, the signed Stripe
API adapter and a persistent PostgreSQL database, and verify refunds,
entitlements, rate limiting and audit logs. Keep the `deny_unmapped=True`
default. Do not enable public deployment as a production service before
security review.
