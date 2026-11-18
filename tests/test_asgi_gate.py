import asyncio
import unittest

from protection.asgi_gate import PaidAccessGate


class PaidAccessGateTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        async def app(scope, receive, send):
            self.calls.append(scope["path"])
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"protected"})
        self.app = app

    def request(self, path, buyer=None, authorized=lambda buyer, service: False, **extra):
        messages = []
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}
        async def send(msg):
            messages.append(msg)
        scope = {"type": "http", "path": path, "method": "POST", "state": {}}
        if buyer is not None:
            scope["state"]["privi_buyer_id"] = buyer
        scope.update(extra)
        gate = PaidAccessGate(self.app, protected_mounts={
            "/premium": "all_tools",
            "/premium/callproof": "call_proof",
        }, authorized=authorized)
        asyncio.run(gate(scope, receive, send))
        return messages[0]["status"]

    def test_non_paid_blocked(self):
        self.assertEqual(self.request("/premium/report", buyer="buyer1"), 403)
        self.assertEqual(self.calls, [])

    def test_no_auth_blocked(self):
        self.assertEqual(self.request("/premium", authorized=lambda *_: True), 401)

    def test_valid_paid_access(self):
        self.assertEqual(self.request("/premium/report", buyer="buyer1",
                                      authorized=lambda *_: True), 200)
        self.assertEqual(self.calls, ["/premium/report"])

    def test_specific_scope_wins(self):
        seen = []
        def auth(buyer, scope):
            seen.append(scope)
            return scope == "call_proof"
        self.assertEqual(self.request("/premium/callproof/run", buyer="buyer1",
                                      authorized=auth), 200)
        self.assertEqual(seen, ["call_proof"])

    def test_public_discovery_preserved(self):
        self.assertEqual(self.request("/mcp/tools/list"), 200)

    def test_prefix_not_bypassed(self):
        self.assertEqual(self.request("/premium-other"), 200)
        self.assertEqual(self.request("/premium//report", buyer="buyer1",
                                      authorized=lambda *_: True), 400)

    def test_encoded_path_denied(self):
        self.assertEqual(self.request("/premium/report", buyer="buyer1",
                                      authorized=lambda *_: True,
                                      raw_path=b"/premium/%2e%2e/public"), 400)

    def test_websocket_premium_denied_without_purchase(self):
        received = []
        async def receive():
            return {"type": "websocket.connect"}
        async def send(message):
            received.append(message)
        gate = PaidAccessGate(self.app, protected_mounts={"/premium": "all_tools"},
                              authorized=lambda *_: False)
        asyncio.run(gate({"type": "websocket", "path": "/premium/ws",
                          "state": {"privi_buyer_id": "buyer1"}},
                         receive, send))
        self.assertEqual(received, [{"type": "websocket.close", "code": 1008}])
        self.assertEqual(self.calls, [])

    def test_websocket_paid_passes(self):
        received = []
        async def receive():
            return {"type": "websocket.connect"}
        async def send(message):
            received.append(message)
        async def ws_app(scope, receive, send):
            self.calls.append(scope["path"])
            await send({"type": "websocket.accept"})
        gate = PaidAccessGate(ws_app, protected_mounts={"/premium": "all_tools"},
                              authorized=lambda *_: True)
        asyncio.run(gate({"type": "websocket", "path": "/premium/ws",
                          "state": {"privi_buyer_id": "buyer1"}},
                         receive, send))
        self.assertEqual(received, [{"type": "websocket.accept"}])

    def test_strict_mode_denies_unknown_routes(self):
        messages = []
        async def receive():
            return {"type": "http.request", "body": b""}
        async def send(message):
            messages.append(message)
        gate = PaidAccessGate(
            self.app, protected_mounts={"/premium": "all_tools"},
            authorized=lambda *_: True, public_mounts=("/health", "/mcp/discovery"),
            deny_unmapped=True)
        asyncio.run(gate({"type": "http", "path": "/admin/debug", "state": {}}, receive, send))
        self.assertEqual(messages[0]["status"], 403)
        self.assertNotIn("/admin/debug", self.calls)
        messages.clear()
        asyncio.run(gate({"type": "http", "path": "/health", "state": {}}, receive, send))
        self.assertEqual(messages[0]["status"], 200)

    def test_raw_path_mismatch_rejected(self):
        self.assertEqual(self.request("/premium/run", buyer="buyer1",
                                      authorized=lambda *_: True,
                                      raw_path=b"/public/run"), 400)

    def test_fail_closed_on_database_error(self):
        def broken(*_):
            raise RuntimeError("db unavailable")
        self.assertEqual(self.request("/premium/report", buyer="buyer1",
                                      authorized=broken), 503)


if __name__ == "__main__":
    unittest.main()
