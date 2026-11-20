"""Request-level ASGI tests for the runnable staging paid-access service."""
import asyncio
import json
import unittest

from protection.staging_app import app, create_app


def request(application, path, *, method="GET", buyer=None, headers=()):
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    state = {} if buyer is None else {"privi_buyer_id": buyer}
    scope = {
        "type": "http", "method": method,
        "path": path, "raw_path": path.encode(),
        "state": state, "headers": list(headers),
    }
    asyncio.run(application(scope, receive, send))
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return status, body


class StagingAppTests(unittest.TestCase):
    def test_public_health_and_discovery(self):
        status, raw = request(app, "/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["payments"], "disabled")
        self.assertEqual(request(app, "/catalog")[0], 200)

    def test_default_denies_paid_routes_even_with_forged_buyer_header(self):
        self.assertEqual(request(app, "/premium/guard", method="POST")[0], 401)
        self.assertEqual(
            request(app, "/premium/guard", method="POST",
                    headers=((b"x-buyer-id", b"buyer_fixture"),))[0], 401)
        self.assertEqual(
            request(app, "/premium/guard", method="POST", buyer="buyer_fixture")[0], 403)

    def test_scoped_entitlements_from_trusted_state_only(self):
        grants = {("buyer_a", "call_proof")}
        staged = create_app(authorized=lambda buyer, scope: (buyer, scope) in grants)
        status, raw = request(staged, "/premium/callproof", method="POST", buyer="buyer_a")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["result"], "synthetic-authorized-demo")
        self.assertEqual(request(staged, "/premium/guard", method="POST", buyer="buyer_a")[0], 403)
        self.assertEqual(request(staged, "/premium/callproof", method="POST", buyer="buyer_b")[0], 403)

    def test_fail_closed_on_db_error(self):
        def broken(_buyer, _scope):
            raise RuntimeError("simulated database outage")
        staged = create_app(authorized=broken)
        self.assertEqual(request(staged, "/premium/guard", method="POST", buyer="buyer_a")[0], 503)

    def test_unknown_paths_and_traversal_blocked(self):
        self.assertEqual(request(app, "/admin/secrets")[0], 403)
        self.assertEqual(request(app, "/catalog/../premium/guard")[0], 400)
        self.assertEqual(request(app, "/premium/guardians", method="POST")[0], 403)


if __name__ == "__main__":
    unittest.main()
