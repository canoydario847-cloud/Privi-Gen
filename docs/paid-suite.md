# Privi Paid Service Suite

**100 implemented policy services: 35 GitHub, 35 AI-agent, 30 call-network checks.** Each has a separate tool name, strict input schema, concrete policy rules, remediation, and passing/failing test cases. One shared runner handles metering, input validation, receipts and delivery. These are 100 callable policy services, not 100 separately deployed servers.

The suite analyzes **caller-supplied evidence**. It does not fetch repositories, verify a signature merely because you supply `signature_valid: true`, run an AI model, place calls, execute code, or independently audit a live system. A pass means the supplied evidence satisfies the documented Privi policy. Numerical thresholds are product defaults, not regulatory or universal security standards.

Original implementation remains covered by the repository's Privi World Corp proprietary rights notice. Privi branding and original code do not establish that competing products lack similar capabilities.

## Paid access

Every successful service execution requires **two Privi Guard check units**, funded by prepaid credits or a verified active Pro/enterprise plan allowance, and an authorized organization API key. Catalog/schema discovery is available without payment; no policy report is available through the CLI, GitHub Action or MCP dispatcher without confirmed credits or paid-plan entitlement. There is no local free-execution flag, mock-payment option, automatic credit purchase, wallet signing, or new price schedule.

The implementation calls the existing [Privi Guard service](https://privi-ledger-aqe5.onrender.com/mcp), screens a request containing the service ID, policy hash and arguments in two directions, and accepts `paid_by: credits`. When the provider labels a check `free`, the suite independently calls `ledger_plan` with the same key, requires an active Pro/enterprise entitlement, checks Pro expiry, and binds the plan organization to both receipts. It binds each receipt to the exact request and a fresh request ID before evaluating the policy. Unverified free allowances, open mode, payment errors, mismatched receipts and incomplete results do not unlock a report.

**Account compatibility:** Guard spends included checks before credits. Included checks unlock this suite only after server-side paid-plan verification. A free account's allowance does not qualify. When a paid plan's Guard allowance is exhausted, the provider's existing credit rules apply; this code changes neither checkout prices nor account quotas. Confirm customer entitlements against the existing provider before selling an unlimited plan. No extra subscription is created by this suite.

Set `PRIVI_API_KEY` from your secret manager. Obtain credits using the existing provider's supported purchase flow; this suite does not submit payment transactions. Credit pack terms remain controlled by that service. No dollars, new subscription prices or earnings are asserted here.

## Limits and receipts

- Maximum input: 64,000 UTF-8 bytes; at most 1,024 elements per list and 512 characters per ordinary string. Numbers must be finite, correctly typed and inside the declared bounds. Coverage, precision, quorum, tracing and error-budget fractions cannot claim a numerator greater than the total. Retry-backoff sequences require at least two observations. Unknown fields and duplicate JSON keys are rejected.
- Each authorized attempt reserves two check units before contacting the provider. The CLI or MCP session has an explicit cap, at most 200 units. A normal single-service run uses a cap of 2. The cap counts checks even when a paid plan includes them. Restarting or rerunning creates a new budget and may charge again; this is not a global account spending limit.
- No automatic retries. Failed/flagged calls can already have consumed credits. A missing response leaves the local reservation consumed; check provider usage before trying again. The provider does not promise refunds for flagged input.
- Only response metadata, numeric measurements, rule IDs and remediation appear in results. Raw evidence, secrets, receipt bodies and finding excerpts are omitted from logs/results. **The supplied evidence is transmitted to Privi Guard**: submit only information you authorize that provider to process.
- The existing Guard service owns credit accounting and receipts. This repository adds no wallet, customer database or alternate ledger. Receipt hashes and input bindings are checked; independent Ed25519 verification and chain finality are not claimed.
- A receipt proves the provider reported the input check; it does not attest the truth of supplied evidence, independently certify a GitHub state, or sign the locally computed policy report.
- The proprietary source is visible on GitHub. Paid enforcement is the supported runner's dispatch boundary, not copy protection of source downloaded to a machine controlled by someone else.

## Run a service

Python 3.10+, standard library only. Discovery performs no remote calls:

```bash
python3 privi_suite.py list
python3 privi_suite.py describe privi_context_budget
```

Save input matching the returned schema, for example `examples/context-budget.json`, then use an authorized key from your environment:

```bash
python3 privi_suite.py --enable-paid --max-session-units 2 \
  run privi_context_budget --input examples/context-budget.json
```

Exit `0`: paid report passed policy; `2`: paid report requires review; `1`: validation, payment, authorization or provider failure. There is no free quote mode returning a policy decision. Inspect `status: paid_result` and `decision`, not just whether JSON was returned. Policy reports can guide a review gate; they are not merge authorization.

## GitHub Action

Use a reviewed full commit SHA in place of `REVIEWED_COMMIT_SHA`. Produce evidence using trusted collectors in a trusted workflow. Keep the paid API key out of fork jobs and changed scripts. Set read-only GitHub permissions, and authorize each paid workflow run; do not automatically bill arbitrary PR contributors.

```yaml
- name: Privi Context Budget
  uses: canoydario847-cloud/Privi-Gen/suite@REVIEWED_COMMIT_SHA
  env:
    PRIVI_API_KEY: ${{ secrets.PRIVI_API_KEY }}
  with:
    service: privi_context_budget
    input-path: evidence/context-budget.json
    authorize-paid: 'true'
```

The action exits nonzero for policy failures and does not post comments, merge changes, or enable other workflows. Put independent tests and security checks alongside it.

## MCP for AI agents and call routers

The stdio MCP server lists all 100 tools. Launch without flags for discovery-only mode:

```bash
python3 /trusted/Privi-Gen/privi_suite.py mcp
```

For an explicitly authorized session of at most five service attempts:

```bash
python3 /trusted/Privi-Gen/privi_suite.py --enable-paid --max-session-units 10 mcp
```

Pass `PRIVI_API_KEY` securely in the process environment. Do not commit it to client configuration. Clients can use `initialize`, `tools/list`, and `tools/call`; each call has the service-specific schema. Calls are processed sequentially. Tool notifications do not execute services. Paid tools are intentionally marked non-idempotent because another call can consume more credits. A `review` decision is a successfully delivered paid report; a billing failure is an MCP `isError` result.

The server is a local stdio integration, not a public HTTP endpoint. The 100 tools have not been installed into the deployed Privi Ledger MCP server merely by publishing this repository.

## Validation and launch status

Tests cover all 100 positive and 100 negative policy cases, strict inputs, denied free execution, receipt replay, provider failures, session budgets and real subprocess MCP discovery. Tests use mocked paid responses and do not charge a real account. A live paid request and end-to-end customer fulfillment still require an authorized credit-billed account. Publishing this source does not establish paying customers, revenue or exclusivity.

Run tests with `python3 -m unittest discover -s tests -v`. Use [the full catalog](paid-service-catalog.md) to select services and inspect exact policy inputs. The machine-readable catalog is [suite/catalog.json](../suite/catalog.json).


### November 15, 2026 double-check

Read-only live discovery returned 136 tools from the existing ledger, including `guard_check_many` and `ledger_plan`; none of the new suite tool IDs were present there. The suite remains a source-published CLI/Action/stdio integration. No live paid request was made. Regression checks now include oversized integer input, impossible fractions, insufficient backoff observations, partial HTTP responses and reset connections; these cases cannot produce a passing paid report.
