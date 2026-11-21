"""Configuration gate for isolated Privi payment staging.

No database migration, external request or payment is made on import.
Use only a dedicated staging database and Stripe sandbox credentials.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from collections.abc import Mapping
from urllib.parse import urlsplit
from .entitlement_store import PricePlan


@dataclass(frozen=True)
class StagingConfig:
    database_url: str = field(repr=False)
    stripe_key: str = field(repr=False)
    webhook_secret: str = field(repr=False)
    price_allowlist: dict


def load_config(env: Mapping[str, str]) -> StagingConfig:
    if env.get("PRIVI_PAYMENT_MODE") != "test":
        raise ValueError("Explicit test mode required")
    db = env.get("PRIVI_STAGING_DATABASE_URL", "")
    parts = urlsplit(db)
    if (parts.scheme not in ("postgres", "postgresql")
            or not parts.hostname
            or parts.path != "/privi_billing_staging"
            or not parts.username or not parts.password):
        raise ValueError("Dedicated staging database URL required")
    key = env.get("PRIVI_STRIPE_TEST_KEY", "")
    if not key.startswith(("sk_test_", "rk_test_")) or len(key) < 16:
        raise ValueError("Stripe test-only secret key required")
    secret = env.get("PRIVI_STRIPE_TEST_WEBHOOK_SECRET", "")
    if not secret.startswith("whsec_") or len(secret) < 16:
        raise ValueError("Staging webhook secret required")
    names = (
        ("PRIVI_TEST_PRICE_CALLPROOF", PricePlan("call_proof", 1999)),
        ("PRIVI_TEST_PRICE_GUARD", PricePlan("guard", 1999)),
        ("PRIVI_TEST_PRICE_PRO", PricePlan("all_services", 3500)),
    )
    prices = {}
    for name, plan in names:
        pid = env.get(name, "")
        if not pid.startswith("price_") or len(pid) <= 6 or pid in prices:
            raise ValueError("Three distinct configured test-mode price IDs required")
        prices[pid] = plan
    return StagingConfig(db, key, secret, prices)


def require_test_object(obj):
    """Reject live or ambiguous Stripe records, including signed events."""
    if not isinstance(obj, Mapping) or obj.get("livemode") is not False:
        raise ValueError("Expected explicitly test-mode Stripe object")
    return obj


def require_test_page(page):
    if not isinstance(page, Mapping) or not isinstance(page.get("data"), list):
        raise ValueError("Expected Stripe list response")
    for obj in page["data"]:
        require_test_object(obj)
    return page
