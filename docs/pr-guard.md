# Privi PR Guard for AI coding agents

Screen a proposed GitHub change before an agent merges it. Privi PR Guard sends a unified diff to the existing Privi Guard API for two checks: inbound prompt-injection patterns and outbound secret/data-leak patterns. It returns a JSON decision bound to the diff's SHA-256 and supplied base/head commit IDs. It never executes repository code or merges a PR.

## Why an agent operator would buy it

Use one consistent check across coding agents, obtain receipt IDs for review, and stop automation on warnings, blocked changes, unavailable billing, or incomplete results. This is a purchasable integration with an existing service, not a claim of paying customers or guaranteed vulnerability detection.

## Billing and activation

Use your authorized Privi organization API key with purchased Guard credits (or an existing account allowance). Obtain current terms and credit packs from `guard_pricing` / `guard_buy_credits` on [Privi MCP](https://privi-ledger-aqe5.onrender.com/mcp). No new price, checkout, wallet, or separate ledger is introduced.

Each direction consumes one Guard unit per 100,000 characters, rounded up: an ordinary patch uses **2 units**. The default maximum is 2; the hard maximum is 8. The remote API owns accounting and entitlement decisions. The cap bounds requested units per invocation, not dollar prices or aggregate workflow reruns. This client never buys credits, signs transactions, or retries automatically. A lost response may have consumed credits; check usage before rerunning.

A quote is local and free. `--submit` explicitly authorizes sending the patch to Privi and consuming account credits. Diff contents can contain proprietary source or secrets: only submit source your organization permits Privi to process. Reports and logs omit source text, finding excerpts, and keys.

## Agent CLI

Requires Python 3.10+. Generate the exact diff from commits in a trusted workspace:

```bash
BASE=$(git rev-parse HEAD^)
HEAD=$(git rev-parse HEAD)
git diff --no-ext-diff --no-textconv --binary "$BASE" "$HEAD" -- > change.diff
python3 /trusted/Privi-Gen/privi_pr_guard.py --patch change.diff \
  --base-sha "$BASE" --head-sha "$HEAD" --max-credit-units 2
# Supply PRIVI_API_KEY securely through your environment, then authorize the call:
python3 /trusted/Privi-Gen/privi_pr_guard.py --patch change.diff \
  --base-sha "$BASE" --head-sha "$HEAD" --max-credit-units 2 --submit
```

Exit codes: `0` quote or allowed check (inspect `status` to distinguish); `1` invalid input, access/payment failure, or unavailable service; `2` warn/block requiring review. Only accept `status: checked` and `verdict: allow` for an automated gate. Do not treat a quote as a passed check.

## GitHub Action

The root `action.yml` is a reusable composite action. In a trusted workflow, generate the patch first, then call this action pinned to a reviewed **full commit SHA**:

```yaml
- name: Privi PR Guard
  uses: canoydario847-cloud/Privi-Gen@REPLACE_WITH_REVIEWED_FULL_COMMIT_SHA
  env:
    PRIVI_API_KEY: ${{ secrets.PRIVI_API_KEY }}
  with:
    patch-path: change.diff
    base-sha: ${{ env.BASE_SHA }}
    head-sha: ${{ env.HEAD_SHA }}
    max-credit-units: '2'
    submit: 'true'
```

Use read-only repository permissions. Keep the action and patch-generation commands trusted; never run changed scripts with the paid key. For fork PRs, have a maintainer explicitly authorize the exact head SHA in a trusted manual workflow. Do not enable automatic paid calls from arbitrary pull requests or use `pull_request_target` to execute a fork checkout. See [GitHub's secure-use guidance](https://docs.github.com/en/actions/reference/security/secure-use).

## Scope and limitations

- The supplied diff is the scope. Commit labels are supplied by the caller; the client does not independently fetch GitHub or prove the diff matches those commits. Trusted generation and checking the head is still current before merge are the caller's responsibility.
- Binary patches, submodule changes, invalid UTF-8, empty diffs, and patches above 400,000 bytes fail closed. No truncation or partial clean report.
- Pattern detection can miss attacks and report false positives. It does not compile code, inspect dependencies, prove correctness, or replace tests/security review. Removed/context lines may trigger findings.
- Receipts are checked for body-hash integrity and input/direction binding. This client does not independently verify Ed25519 signatures or chain anchoring. Receipt IDs can be checked through `guard_receipt` on the existing Privi ledger service.
- Local tests mock paid responses; publishing the source does not prove live billing or establish a new customer. No paid production request was made during development.
