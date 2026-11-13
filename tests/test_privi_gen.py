import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import privi_gen


class CatalogTests(unittest.TestCase):
    def test_catalog_registers_primary_repositories(self):
        data = privi_gen.load_catalog()
        names = {project["name"] for project in data["projects"]}
        self.assertTrue({"Privi-Network", "Privi", "Privi-Chain", "Privi-Boot-code"} <= names)
        self.assertEqual(len(names), len(data["projects"]))

    def test_unexpected_owner_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "catalog.json"
            path.write_text(json.dumps({
                "schema_version": 1, "owner": "unknown",
                "projects": [],
            }), encoding="utf-8")
            with self.assertRaises(ValueError):
                privi_gen.load_catalog(path)


class InventoryTests(unittest.TestCase):
    def test_inventory_indexes_only_tracked_allowed_files(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "Privi-example"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "main.py").write_text("print('privi')\n", encoding="utf-8")
            (repo / "ignored.bin").write_bytes(b"binary")
            (repo / "untracked.js").write_text("const unsafe = true;\n", encoding="utf-8")
            subprocess.run(["git", "add", "main.py", "ignored.bin"], cwd=repo, check=True)
            subprocess.run(
                ["git", "-c", "user.name=CI", "-c", "user.email=ci@example.invalid",
                 "commit", "-q", "-m", "test"],
                cwd=repo, check=True,
            )
            result = privi_gen.inventory(repo)
            self.assertEqual(result["files_indexed"], 1)
            self.assertEqual(result["files"][0]["path"], "main.py")
            self.assertEqual(len(result["files"][0]["sha256"]), 64)

    def test_inventory_requires_git_checkout(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(subprocess.CalledProcessError):
                privi_gen.inventory(Path(temp))


class SyncTests(unittest.TestCase):
    def test_sync_does_not_overwrite_existing_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            existing = base / "Privi"
            existing.mkdir()
            marker = existing / "do-not-overwrite"
            marker.write_text("keep me", encoding="utf-8")
            data = privi_gen.load_catalog()
            result = privi_gen.sync(data, base, ["Privi"])
            self.assertEqual(result["projects"]["Privi"]["status"], "skipped-existing")
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep me")
            self.assertTrue((base / "privi-lock.json").exists())

    def test_sync_rejects_unknown_repo(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                privi_gen.sync(privi_gen.load_catalog(), Path(temp), ["OtherRepo"])

    def test_sync_marks_empty_repo_without_cloning(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            result = privi_gen.sync(privi_gen.load_catalog(), base, ["Privi-DAO1"])
            self.assertEqual(result["projects"]["Privi-DAO1"]["status"], "empty")
            self.assertFalse((base / "Privi-DAO1").exists())


if __name__ == "__main__":
    unittest.main()
