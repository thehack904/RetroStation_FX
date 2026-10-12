from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GitignoreTests(unittest.TestCase):
    def is_ignored(self, path: str) -> bool:
        result = subprocess.run(
            ["git", "check-ignore", "--quiet", "--no-index", "--", path],
            cwd=ROOT,
            check=False,
        )
        if result.returncode not in (0, 1):
            self.fail(f"git check-ignore failed for {path}: {result.returncode}")
        return result.returncode == 0

    def test_local_and_generated_artifacts_are_ignored(self):
        ignored_paths = (
            ".venv/lib/python/site-packages",
            "app/rsfx/__pycache__/app.cpython-313.pyc",
            ".env.local",
            "config/rsfx.env",
            "var/lib/retrostation-fx/rsfx.db",
            "var/lib/retrostation-fx/rsfx.db-wal",
            "logs/rsfx.log",
            "captures/failure.pcap",
            "tmp/work.tmp",
            "build/rsfx.whl",
            "release.tar.gz",
            ".idea/workspace.xml",
            ".vscode/settings.json",
            ".DS_Store",
            "app/Thumbs.db",
            "tests/test-output/results.xml",
            "credentials/id_ed25519",
            "credentials.json",
            "certs/server.crt",
            "secrets/production.secret",
            "secrets.yaml",
        )
        for path in ignored_paths:
            with self.subTest(path=path):
                self.assertTrue(self.is_ignored(path), path)

    def test_examples_and_release_hash_manifests_are_not_ignored(self):
        required_paths = (
            "config/rsfx.env.example",
            "docs/LIVE-SOURCE-SHA256.txt",
            "docs/PACKAGE-SHA256.txt",
        )
        for path in required_paths:
            with self.subTest(path=path):
                self.assertFalse(self.is_ignored(path), path)


if __name__ == "__main__":
    unittest.main()
