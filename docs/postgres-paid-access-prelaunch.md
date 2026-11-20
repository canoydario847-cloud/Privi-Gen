# PostgreSQL entitlement backend (prelaunch)

The `PostgresEntitlementStore` in `protection/postgres_entitlement_store.py`
is a **reference implementation**, not a deployed service. It is designed
to replace the SQLite-only test/reference backend for multiple Render instances.

Before use:
1. Create a durable PostgreSQL database with encryption and backups, and a dedicated least-privilege service role. Do not use an ephemeral filesystem or commit credentials.
2. Run the reviewed `SCHEMA_SQL` as an explicit, versioned migration with a privileged migration role.
3. Install `psycopg[binary]` in the service build and inject DATABASE_URL through the service secrets manager. Require TLS according to your provider's connection configuration.
4. At Checkout creation, persist an immutable authenticated buyer-to-session mapping server-side. At webhook handling, verify Stripe's raw-body signature, fetch paid session and complete line items from Stripe's API, validate matching customer and price configuration, and only then call `fulfill_verified_checkout`.
5. Gate every tool API and MCP `tools/call` using the authenticated buyer ID and a database-backed `authorized` lookup; default deny unknown routes, protect service-to-service calls, rate-limit, and log audit metadata only.
6. Process verified refunds/disputes and administrator revocations idempotently; test retries, chargebacks, payment reconciliation, and concurrent webhooks against a **real PostgreSQL instance** before launch.

Do not infer billing completion from a client redirect. Do not grant GitHub
repository write/admin permissions to purchasers; private source is separate
from server-side product access. Existing publicly cloned code cannot be
withdrawn. No live deployment or customer access changes are made by this code.

The CI unit tests use a small fake SQL connection to check behavior and SQL
structure. They do **not** verify SQL against PostgreSQL or production readiness.
