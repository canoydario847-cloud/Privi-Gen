import unittest
from datetime import datetime, timezone
from protection.licensed_view import AccessDenied, Entitlement, licensed_view

KEY = b"privi-development-only-32-byte-test-key-0000"

class LicensedViewTests(unittest.TestCase):
    def test_rejects_unpaid(self):
        with self.assertRaises(AccessDenied):
            licensed_view(source="secret", buyer_id="u", asset_id="a",
                          entitlement_lookup=lambda *_: None, watermark_key=KEY)
    def test_rejects_wrong_buyer(self):
        with self.assertRaises(AccessDenied):
            licensed_view(source="secret", buyer_id="u", asset_id="a",
                          entitlement_lookup=lambda *_: Entitlement("other", "a", True, "o"),
                          watermark_key=KEY)
    def test_watermark_html_escape_and_headers(self):
        html, headers = licensed_view(
            source="<script>alert('x')</script>\nsecond",
            buyer_id="buyer1", asset_id="asset1",
            entitlement_lookup=lambda *_: Entitlement("buyer1", "asset1", True, "order1"),
            watermark_key=KEY,
            now=datetime(2026, 11, 18, tzinfo=timezone.utc),
        )
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)
        self.assertGreaterEqual(html.count("PRIVI WORLD CORP"), 3)
        self.assertIn("no-store", headers["Cache-Control"])
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])

if __name__ == "__main__":
    unittest.main()
