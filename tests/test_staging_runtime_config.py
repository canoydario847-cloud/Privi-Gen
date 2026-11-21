import unittest
from protection.staging_runtime_config import load_config, require_test_object, require_test_page


class StagingRuntimeConfigTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "PRIVI_PAYMENT_MODE": "test",
            "PRIVI_STAGING_DATABASE_URL": "postgresql://fixture:fixture@localhost/privi_billing_staging",
            "PRIVI_STRIPE_TEST_KEY": "sk_test_fixture_only",
            "PRIVI_STRIPE_TEST_WEBHOOK_SECRET": "whsec_fixture_only",
            "PRIVI_TEST_PRICE_CALLPROOF": "price_call_fixture",
            "PRIVI_TEST_PRICE_GUARD": "price_guard_fixture",
            "PRIVI_TEST_PRICE_PRO": "price_pro_fixture",
        }

    def test_prices_and_redacted_repr(self):
        cfg = load_config(self.env)
        self.assertEqual(cfg.price_allowlist["price_pro_fixture"].amount_cents, 3500)
        self.assertEqual(cfg.price_allowlist["price_call_fixture"].amount_cents, 1999)
        self.assertNotIn(self.env["PRIVI_STAGING_DATABASE_URL"], repr(cfg))
        self.assertNotIn(self.env["PRIVI_STRIPE_TEST_KEY"], repr(cfg))
        self.assertNotIn(self.env["PRIVI_STRIPE_TEST_WEBHOOK_SECRET"], repr(cfg))

    def test_missing_settings_rejected(self):
        for name in self.env:
            with self.subTest(name=name):
                env = dict(self.env)
                del env[name]
                with self.assertRaises(ValueError):
                    load_config(env)

    def test_live_key_production_database_duplicate_price_rejected(self):
        for key, value in [
            ("PRIVI_PAYMENT_MODE", "live"),
            ("PRIVI_STRIPE_TEST_KEY", "sk_live_fixture_only"),
            ("PRIVI_STRIPE_TEST_KEY", "rk_live_fixture_only"),
            ("PRIVI_STAGING_DATABASE_URL", "postgresql://a:b@localhost/privi_billing_production"),
            ("PRIVI_TEST_PRICE_PRO", "price_call_fixture"),
        ]:
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    load_config(dict(self.env, **{key: value}))

    def test_only_explicit_test_objects(self):
        self.assertEqual(require_test_object({"livemode": False}), {"livemode": False})
        for obj in ({}, {"livemode": True}, {"livemode": 0}, None):
            with self.assertRaises(ValueError):
                require_test_object(obj)
        with self.assertRaises(ValueError):
            require_test_page({"data": [{"livemode": False}, {"livemode": True}]})


if __name__ == "__main__":
    unittest.main()
