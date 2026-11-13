# Privi-Gen

Privi-Gen is the central **source inventory and workspace generator** for the Privi family of repositories.

It **does not** deploy, mint, bridge, activate a financial mainnet, modify a running service, or replace source files in other repositories. Existing projects remain the source of truth for their runtime code.

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

`sync` clones public source repositories into an **empty** destination directory and records their exact commit SHAs in `privi-lock.json`. It never overwrites an existing checkout. An empty repository is represented in the registry but is not cloned.

`inventory` hashes tracked source/configuration files from a local Git checkout. It ignores generated artifacts, symlinks, Git metadata, untracked files and large binaries. The JSON inventory provides traceability, not a security audit or deployment certification.

## Integrating a Privi project

Each project can add a read-only CI check which checks out a **pinned** Privi-Gen revision, runs `inventory`, and uploads the resulting source index as a CI artifact. No generated files are automatically merged into production.

## Boundaries

- Privi-Network financial mainnet release gates and validator settings must remain governed by that repository's own validation and approval workflow.
- No automated copy of contracts, private keys, payment credentials or production configuration into other projects.
- No change in ownership or license of source imported from other repositories.
- Avoid writing generated indexes back to source branches.

Copyright © 2026 Privi World Corp. All rights reserved for original Privi-Gen material, subject to any applicable third-party terms.
