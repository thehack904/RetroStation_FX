from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from rsfx import __version__
from rsfx.app import capabilities, health
from rsfx.config import settings
from rsfx.ersatztv import generate_yaml
from tools.update_hashes import VERSION as HASH_MANIFEST_VERSION
from tools.update_hashes import VERSION_HEADER, package_files


class VersionMetadataTests(unittest.TestCase):
    def test_runtime_and_managed_yaml_use_release_version(self):
        version = (ROOT / "app/VERSION").read_text(encoding="utf-8").strip()
        style = SimpleNamespace(
            display_name="Test Style",
            generated_description="Test description",
            z_index=1,
            eligibility=SimpleNamespace(start_seconds=0, duration_seconds=10),
            id=1,
        )

        self.assertEqual(version, "0.1.0")
        self.assertEqual(__version__, version)
        self.assertEqual(settings.version, version)
        self.assertEqual(health()["version"], version)
        self.assertEqual(capabilities()["version"], version)
        self.assertTrue(generate_yaml(style).startswith(f"# Managed by RetroStation FX {version}\n"))

    def test_user_visible_release_metadata_uses_v0_1_0(self):
        version = (ROOT / "app/VERSION").read_text(encoding="utf-8").strip()
        installer = (ROOT / "retrostation_fx_linux.sh").read_text(encoding="utf-8")
        verify = (ROOT / "verify.sh").read_text(encoding="utf-8")
        ui = (ROOT / "app/rsfx/static/index.html").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        release_notes = (ROOT / "docs/RELEASE-NOTES.md").read_text(encoding="utf-8")
        live_manifest = (ROOT / "docs/LIVE-SOURCE-SHA256.txt").read_text(encoding="utf-8")
        package_manifest = (ROOT / "docs/PACKAGE-SHA256.txt").read_text(encoding="utf-8")

        self.assertEqual(re.search(r'^VERSION="([^"]+)"', installer, re.MULTILINE).group(1), "0.1.0")
        self.assertIn('EXPECTED_VERSION="0.1.0"', verify)
        self.assertIn(
            "<h1>RetroStation FX</h1><p>Graphics &amp; Overlay Engine for ErsatzTV</p>",
            ui,
        )
        self.assertNotIn("<p>v0.1.0", ui)
        self.assertIn('<div id="health" class="pill">Checking…</div>', ui)
        self.assertTrue(readme.startswith("# RetroStation FX v0.1.0\n"))
        self.assertIn("first public RSFX release", readme)
        self.assertIn("First Public Release", release_notes)
        self.assertIn("first public RSFX release", release_notes)
        self.assertIn("python3 tools/update_hashes.py", readme)
        self.assertEqual(HASH_MANIFEST_VERSION, version)
        self.assertEqual(VERSION_HEADER, f"# RetroStation FX v{version} release manifest")
        self.assertTrue(live_manifest.startswith(f"# RetroStation FX v{version} release manifest\n"))
        self.assertTrue(package_manifest.startswith(f"# RetroStation FX v{version} release manifest\n"))
        self.assertIn("Regenerate after any source change", live_manifest)
        self.assertIn("Regenerate after any package file change", package_manifest)
        self.assertEqual(len([line for line in live_manifest.splitlines() if re.match(r"^[0-9a-f]{64}  ", line)]), len(__import__("tools.update_hashes", fromlist=["LIVE_PATHS"]).LIVE_PATHS))
        self.assertTrue(any(re.match(r"^[0-9a-f]{64}  ", line) for line in package_manifest.splitlines()))

    def test_package_hash_generation_includes_license_and_security_policy(self):
        package_paths = {path.relative_to(ROOT).as_posix() for path in package_files()}

        self.assertTrue({"LICENSE", "SECURITY.md"} <= package_paths)


if __name__ == "__main__":
    unittest.main()
