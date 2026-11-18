# Privi-Gen

Privi-Gen is the central **source inventory and workspace generator** for the Privi family of repositories.

The workspace generator commands **do not** deploy, mint, bridge, activate a financial mainnet, modify a running service, or replace source files in other repositories. Existing projects remain the source of truth for their runtime code.

## Source registry

`catalog.json` registers the source repositories and their main components. Repositories remain independently versioned and licensed.

## Commands

Requires Python 3.10+ and Git:

```bash
python3 privi_gen.py catalog
python3 privi_gen.py sync --dest ./privi-workspace
python3 privi_gen.py inventory --repo ./privi-workspace/Privi-Network --out ./privi-network-index.json
python3 -m unittest discover -s tests -v
```

`sync` clones **public** source repositories by default into a workspace directory and records their exact commit SHAs in `privi-lock.json`. It never overwrites an existing checkout. An empty repository is represented in the registry but is not cloned. Private repositories are recorded as `skipped-private`, not copied. For a private local workspace, use `--include-private` only on a trusted machine with your own authorized Git credentials; never enable it in public GitHub Actions.

`inventory` hashes tracked source/configuration files from a local Git checkout. It ignores generated artifacts, symlinks, Git metadata, untracked files and large binaries. The JSON inventory provides traceability, not a security audit or deployment certification.

## Integrating a Privi project

Each project can add a read-only CI check which checks out a **pinned** Privi-Gen revision, runs `inventory`, and uploads the resulting source index as a CI artifact. No generated files are automatically merged into production.

## Boundaries

- Privi-Network financial mainnet release gates and validator settings must remain governed by that repository's own validation and approval workflow.
- No automated copy of contracts, private keys, payment credentials or production configuration into other projects.
- No change in ownership or license of source imported from other repositories.
- Avoid writing generated indexes back to source branches.

Copyright © 2026 Privi World Corp. All rights reserved for original Privi-Gen material, subject to any applicable third-party terms.

## Source workspace artifact

The [Assemble Privi source workspace](https://github.com/canoydario847-cloud/Privi-Gen/actions/workflows/assemble-privi-source.yml) GitHub workflow packages **public source only** and its commit lockfile into a downloadable GitHub Actions artifact. The workflow never collects private repository source or secrets.

Private projects (currently Privi and Privi-Chainflow) have their own read-only inventory workflow inside their **private** repositories. Access to their inventory artifacts follows the private repository's GitHub permissions. Their source is not published through Privi-Gen.

## Privi PR Guard — paid checks for AI-generated GitHub changes

**New:** [Privi PR Guard](docs/pr-guard.md) screens Git diffs for prompt-injection and secret-leak patterns using the existing Privi Guard service. Agents receive JSON decisions and receipt IDs tied to the exact patch hash. Warnings, blocked changes and service errors stop the check.

Use the Python CLI or the root GitHub Action. Quotes are local; submitting a check requires explicit authorization and a Guard organization key with credits or an existing allowance. The normal diff costs two Guard credit units; the client enforces a per-run limit. No payment credentials or separate ledger are added to this repository.

See the [setup, billing, GitHub Action example and limitations](docs/pr-guard.md). Source is published here; live paid execution requires customer configuration.

## 100 paid services for GitHub, AI agents and call networks

The [Privi Paid Service Suite](docs/paid-suite.md) adds **100 implemented policy checks**: 35 GitHub, 35 AI-agent and 30 call-network services. Examples include release provenance, context budgets, tool permissions, retry amplification and call-cost limits. Each checks supplied evidence against explicit rules and returns remediation, policy/input hashes and existing Privi Guard receipt references.

- [All 100 services and inputs](docs/paid-service-catalog.md)
- [Machine-readable catalog](suite/catalog.json)
- [CLI, GitHub Action, MCP and paid-access setup](docs/paid-suite.md)

The supported dispatcher requires confirmed prepaid credit billing or a verified active paid-plan allowance; there is no unverified free report path. Catalog discovery is free. The suite is source-published, not installed as 100 new tools on the hosted ledger. Paid fulfillment has not yet been tested with a real customer account. These are original Privi implementations, with no unsupported claim that competing services cannot offer similar checks.

## Commercial source protection

[Privi's licensed-view guard and watermarking checklist](protection/README.md) adds a reusable authenticated source-view helper with buyer-specific watermarking and tests. **It is not connected to live Stripe verification or deployed to other Privi services yet.** Proprietary code should remain private and server-side; paid API access is preferred to distributing source. Publicly released code and Git history cannot be made uncopyable by a website watermark.
