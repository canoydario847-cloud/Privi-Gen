#!/usr/bin/env python3
"""Privi-Gen: read-only Privi source workspace and provenance inventory.

No deployment, production writes, financial operations, or remote code execution.
Python 3.10+; git required for sync and tracked-file inventory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "catalog.json"
MAX_INDEX_FILE_BYTES = 2 * 1024 * 1024
SOURCE_SUFFIXES = {
    ".py", ".js", ".jsx", ".cjs", ".mjs", ".ts", ".tsx", ".go",
    ".rs", ".sol", ".sh", ".bash", ".c", ".h", ".cpp", ".hpp",
    ".java", ".kt", ".kts", ".swift", ".proto", ".sql",
    ".html", ".css", ".scss", ".json", ".yaml", ".yml",
    ".toml", ".xml", ".md", ".mdx", ".txt", ".mod",
}
EXCLUDED_PARTS = {
    ".git", "node_modules", "vendor", "dist", "build", "coverage",
    "__pycache__", ".venv", ".privi-gen-tool", ".next",
}


def run_git(*args: str, cwd: Path | None = None, timeout: int = 180) -> str:
    """Use argument arrays, never a shell, when calling git."""
    completed = subprocess.run(
        ["git", *args], cwd=cwd, text=True, encoding="utf-8",
        errors="replace", capture_output=True, timeout=timeout, check=True
    )
    return completed.stdout.strip()


def load_catalog(path: Path = CATALOG) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported catalog schema")
    owner = data.get("owner")
    if owner != "canoydario847-cloud":
        raise ValueError("Unexpected source owner")
    names: set[str] = set()
    for project in data.get("projects", []):
        name = project["name"]
        branch = project["branch"]
        if not name.startswith("Privi") or not all(
            c.isascii() and (c.isalnum() or c == "-") for c in name
        ):
            raise ValueError("Invalid repository name")
        if branch != "main" or name in names:
            raise ValueError("Invalid branch or duplicate repository")
        if project.get("status") not in {"source", "empty"}:
            raise ValueError("Invalid source status")
        if project.get("visibility") not in {"public", "private"}:
            raise ValueError("Invalid repository visibility")
        names.add(name)
    return data


def catalog_lines(data: dict) -> list[str]:
    return [
        f'{p["name"]} [{p["status"]}, {p["visibility"]}] - {p["component"]}'
        for p in data["projects"]
    ]


def sync(data: dict, destination: Path, only: list[str] | None = None,
         include_private: bool = False) -> dict:
    """Clone missing public repos by default, never overwriting existing targets."""
    projects = {p["name"]: p for p in data["projects"]}
    selected = only if only else list(projects)
    if len(selected) != len(set(selected)):
        raise ValueError("Duplicate repository selection")
    unknown = sorted(set(selected) - set(projects))
    if unknown:
        raise ValueError("Unknown repositories: " + ", ".join(unknown))
    destination = destination.expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    lock: dict = {"schema_version": 1, "owner": data["owner"], "projects": {}}
    failures: list[str] = []
    for name in selected:
        project = projects[name]
        target = destination / name
        if project["visibility"] == "private" and not include_private:
            lock["projects"][name] = {"status": "skipped-private"}
            continue
        if project["status"] == "empty":
            lock["projects"][name] = {"status": "empty"}
            continue
        url = f'https://github.com/{data["owner"]}/{name}.git'
        if target.exists():
            # Intentionally skip rather than pull/reset an existing checkout.
            lock["projects"][name] = {"status": "skipped-existing"}
            continue
        try:
            run_git(
                "clone", "--depth", "1", "--branch", project["branch"],
                "--", url, str(target), timeout=240
            )
            commit = run_git("rev-parse", "HEAD", cwd=target)
            lock["projects"][name] = {"status": "cloned", "commit": commit}
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            details = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) and exc.stderr else str(exc)
            failures.append(f"{name}: {details}")
            lock["projects"][name] = {"status": "failed"}
    (destination / "privi-lock.json").write_text(
        json.dumps(lock, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    if failures:
        raise RuntimeError("Failed cloning: " + "; ".join(failures))
    return lock


def inventory(repo: Path) -> dict:
    """Hash the tracked source/configuration files in one local Git checkout."""
    repo = repo.expanduser().resolve(strict=True)
    if not repo.is_dir():
        raise ValueError("Repository must be a directory")
    git_root = Path(run_git("rev-parse", "--show-toplevel", cwd=repo)).resolve()
    if repo != git_root:
        raise ValueError("--repo must be the root of the Git checkout")
    head = run_git("rev-parse", "HEAD", cwd=repo)
    # Files are selected from Git's index, not from untracked build outputs.
    tracked_raw = subprocess.run(
        ["git", "ls-files", "-z", "--cached"], cwd=repo, capture_output=True,
        check=True, timeout=60
    ).stdout
    files: list[dict] = []
    for raw_path in tracked_raw.split(b"\x00"):
        if not raw_path:
            continue
        relative = raw_path.decode("utf-8", "surrogateescape")
        source = Path(relative)
        if source.is_absolute() or ".." in source.parts:
            continue
        if any(part in EXCLUDED_PARTS for part in source.parts):
            continue
        if source.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        full = repo / source
        if full.is_symlink() or not full.is_file():
            continue
        if not full.resolve().is_relative_to(repo):
            continue
        size = full.stat().st_size
        if size > MAX_INDEX_FILE_BYTES:
            continue
        digest = hashlib.sha256()
        with full.open("rb") as reader:
            for chunk in iter(lambda: reader.read(128 * 1024), b""):
                digest.update(chunk)
        files.append({
            "path": relative.replace("\\", "/"),
            "bytes": size,
            "sha256": digest.hexdigest(),
        })
    files.sort(key=lambda item: item["path"])
    return {
        "schema_version": 1,
        "repo": repo.name,
        "commit": head,
        "files_indexed": len(files),
        "files": files,
        "note": "Tracked-source inventory only; not an audit, attestation or deployment authorization.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("catalog", help="Show registered source repositories")
    clone = commands.add_parser("sync", help="Clone missing repositories read-only")
    clone.add_argument("--dest", required=True, type=Path)
    clone.add_argument("--only", nargs="+", metavar="REPOSITORY")
    clone.add_argument("--include-private", action="store_true",
                       help="Explicitly attempt private clones using your local Git credentials; never use in public CI")
    index = commands.add_parser("inventory", help="SHA-256 inventory of tracked files")
    index.add_argument("--repo", required=True, type=Path)
    index.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        data = load_catalog()
        if args.command == "catalog":
            print("\n".join(catalog_lines(data)))
        elif args.command == "sync":
            lock = sync(data, args.dest, args.only, include_private=args.include_private)
            print(json.dumps(lock, indent=2))
        elif args.command == "inventory":
            result = inventory(args.repo)
            out = args.out.expanduser().resolve()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            print(f'Indexed {result["files_indexed"]} files at {result["commit"]} -> {out}')
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"privi-gen: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
