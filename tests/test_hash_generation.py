from __future__ import annotations

import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import update_hashes


class HashGenerationTests(unittest.TestCase):
    def test_generated_manifests_match_isolated_source_and_are_repeatable(self):
        original = update_hashes.ROOT
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            for relative in [*update_hashes.LIVE_PATHS, "LICENSE", "SECURITY.md"]:
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(original / relative, destination)
            (root / ".git").mkdir()
            (root / ".git" / "config").write_text("not package content", encoding="utf-8")
            (root / "app" / "__pycache__").mkdir()
            (root / "app" / "__pycache__" / "ignored.pyc").write_bytes(b"ignored")
            with patch.object(update_hashes, "ROOT", root), patch.object(update_hashes, "DOCS", root / "docs"):
                update_hashes.write_live()
                update_hashes.write_package()
                live = (root / "docs/LIVE-SOURCE-SHA256.txt").read_text(encoding="utf-8")
                package = (root / "docs/PACKAGE-SHA256.txt").read_text(encoding="utf-8")
                for manifest, installed in ((live, True), (package, False)):
                    entries = [line.split("  ", 1) for line in manifest.splitlines()
                               if line and not line.startswith("#")]
                    self.assertTrue(entries)
                    for digest, path in entries:
                        relative = ("app/" + path.removeprefix("/opt/rsfx/")) if installed else path.removeprefix("./")
                        self.assertEqual(digest, hashlib.sha256((root / relative).read_bytes()).hexdigest())
                    if installed:
                        self.assertEqual(len(entries), len(update_hashes.LIVE_PATHS))
                    else:
                        paths = {path for _, path in entries}
                        self.assertIn("./LICENSE", paths)
                        self.assertIn("./SECURITY.md", paths)
                        self.assertIn("./docs/LIVE-SOURCE-SHA256.txt", paths)
                        self.assertNotIn("./docs/PACKAGE-SHA256.txt", paths)
                        self.assertFalse(any(".git/" in path or "__pycache__" in path for path in paths))
                update_hashes.write_live()
                update_hashes.write_package()
                self.assertEqual((root / "docs/LIVE-SOURCE-SHA256.txt").read_text(encoding="utf-8"), live)
                self.assertEqual((root / "docs/PACKAGE-SHA256.txt").read_text(encoding="utf-8"), package)
                (root / update_hashes.LIVE_PATHS[0]).unlink()
                with self.assertRaisesRegex(SystemExit, "missing LIVE source"):
                    update_hashes.write_live()


if __name__ == "__main__":
    unittest.main()
