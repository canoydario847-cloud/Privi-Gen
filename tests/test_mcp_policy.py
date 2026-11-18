import unittest

from protection.mcp_policy import MCPAccessPolicy


class MCPPolicyTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        def authorized(buyer, scope):
            self.calls.append((buyer, scope))
            return buyer == "paid" and scope == "call_proof"
        self.policy = MCPAccessPolicy(
            tool_scopes={"privi_callproof": "call_proof", "privi_guard": "guard"},
            authorized=authorized,
        )

    def req(self, method, params=None):
        return {"jsonrpc": "2.0", "id": 12, "method": method, "params": params or {}}

    def test_public_discovery(self):
        for method in ("initialize", "tools/list", "ping", "notifications/initialized"):
            self.assertTrue(self.policy.decide(self.req(method), buyer_id=None).allowed)
        self.assertEqual(self.calls, [])

    def test_paid_call_allowed(self):
        d = self.policy.decide(self.req("tools/call", {"name": "privi_callproof"}), buyer_id="paid")
        self.assertEqual((d.allowed, d.scope), (True, "call_proof"))

    def test_unpaid_call_denied(self):
        self.assertFalse(self.policy.decide(self.req("tools/call", {"name": "privi_guard"}), buyer_id="paid").allowed)
        self.assertFalse(self.policy.decide(self.req("tools/call", {"name": "privi_callproof"}), buyer_id=None).allowed)

    def test_unknown_tool_and_method_fail_closed(self):
        self.assertEqual(self.policy.decide(self.req("tools/call", {"name": "new_tool"}), buyer_id="paid").reason, "unknown_tool")
        for method in ("resources/read", "prompts/get", "completion/complete", "admin/debug"):
            self.assertFalse(self.policy.decide(self.req(method), buyer_id="paid").allowed)

    def test_client_identity_and_scope_ignored(self):
        d = self.policy.decide(self.req("tools/call", {
            "name": "privi_callproof",
            "buyer_id": "paid", "scope": "all_services",
        }), buyer_id=None)
        self.assertFalse(d.allowed)
        self.assertEqual(self.calls, [])

    def test_batch_and_malformed_denied(self):
        for request in (
            [self.req("tools/call", {"name": "privi_callproof"})],
            {"method": "tools/list"},
            self.req("tools/call", {"name": []}),
            self.req("tools/call", {"name": "privi_callproof"}) | {"params": None},
        ):
            self.assertFalse(self.policy.decide(request, buyer_id="paid").allowed)

    def test_backend_error_fails_closed(self):
        policy = MCPAccessPolicy(tool_scopes={"privi_callproof": "call_proof"},
                                 authorized=lambda *_: 1 / 0)
        self.assertEqual(policy.decide(self.req("tools/call", {"name": "privi_callproof"}), buyer_id="paid").reason,
                         "authorization_unavailable")


if __name__ == "__main__":
    unittest.main()
