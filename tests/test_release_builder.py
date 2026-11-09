"""Check the actual sanitized release artifact, not only source manifests."""
from __future__ import annotations

from datetime import date
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class ReleaseBuilderTests(unittest.TestCase):
    def test_candidate_and_final_source_archives(self):
        if not (ROOT / ".git").exists():
            self.skipTest("a Git checkout is required for git archive")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            for final in (False, True):
                with self.subTest(final=final):
                    archive = output / ("final.zip" if final else "candidate.zip")
                    command = [
                        sys.executable,
                        "tools/build_release_archive.py",
                        "--checkout", str(ROOT),
                        "--output", str(archive),
                    ]
                    if final:
                        command.extend(["--release-date", "2026-11-08"])
                    result = subprocess.run(
                        command, cwd=ROOT, check=False,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        text=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    with zipfile.ZipFile(archive) as zipped:
                        self.assertIsNone(zipped.testzip())
                        filenames = zipped.namelist()
                        self.assertTrue(filenames)
                        top = filenames[0].split("/", 1)[0]
                        self.assertEqual(top, "RetroStation_FX-v0.1.1" +
                                         ("" if final else "-rc"))
                        relative = {p.split("/", 1)[1] for p in filenames}
                        for excluded in (
                            "docs/PUBLICATION-AUDIT.md",
                            "docs/PILLOW-AUDIT-2026-11-08.md",
                            "tools/audit_release_tree.py",
                            "tests/test_release_audit.py",
                            ".gitattributes",
                        ):
                            self.assertNotIn(excluded, relative)
                        self.assertIn("docs/PACKAGE-SHA256.txt", relative)
                        self.assertIn("docs/LIVE-SOURCE-SHA256.txt", relative)
                        readme = zipped.read(top + "/README.md").decode()
                        changelog = zipped.read(top + "/CHANGELOG.md").decode()
                        if final:
                            self.assertIn("Release status: Released", readme)
                            self.assertIn("## [v0.1.1] — 2026-11-08", changelog)
                        else:
                            self.assertIn("Release status: Release Candidate", readme)
                        live_manifest = zipped.read(top + "/docs/LIVE-SOURCE-SHA256.txt").decode()
                        manifest = zipped.read(top + "/docs/PACKAGE-SHA256.txt").decode()
                        for frozen in (live_manifest, manifest):
                            self.assertIn("verified release archive", frozen)
                            self.assertNotIn("development branch", frozen)
                        self.assertRegex(manifest, r"(?m)^[a-f0-9]{64}  ./README.md$")
                        self.assertNotRegex(manifest, r"(?m)^.*(?:PUBLICATION-AUDIT|PILLOW-AUDIT)")
                        installer = zipped.getinfo(top + "/retrostation_fx_linux.sh")
                        self.assertEqual(installer.external_attr >> 16 & 0o777, 0o755)


if __name__ == "__main__":
    unittest.main()
