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
from tools.update_hashes import LIVE_PATHS, VERSION_HEADER, package_files


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

        self.assertEqual(version, "0.1.1")
        self.assertEqual(__version__, version)
        self.assertEqual(settings.version, version)
        self.assertEqual(health()["version"], version)
        self.assertEqual(capabilities()["version"], version)
        self.assertTrue(generate_yaml(style).startswith(f"# Managed by RetroStation FX {version}\n"))

    def test_user_visible_release_metadata_uses_v0_1_1(self):
        version = (ROOT / "app/VERSION").read_text(encoding="utf-8").strip()
        installer = (ROOT / "retrostation_fx_linux.sh").read_text(encoding="utf-8")
        verify = (ROOT / "verify.sh").read_text(encoding="utf-8")
        ui = (ROOT / "app/rsfx/static/index.html").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        release_notes = (ROOT / "docs/RELEASE-NOTES.md").read_text(encoding="utf-8")
        live_manifest = (ROOT / "docs/LIVE-SOURCE-SHA256.txt").read_text(encoding="utf-8")
        package_manifest = (ROOT / "docs/PACKAGE-SHA256.txt").read_text(encoding="utf-8")

        self.assertEqual(re.search(r'^VERSION="([^"]+)"', installer, re.MULTILINE).group(1), version)
        self.assertIn(f'EXPECTED_VERSION="{version}"', verify)
        self.assertIn(
            "<h1>RetroStation FX</h1><p>Graphics &amp; Overlay Engine for ErsatzTV</p>",
            ui,
        )
        self.assertNotIn("<p>v0.1.0", ui)
        self.assertIn('<div id="health" class="pill">Checking…</div>', ui)
        frontend = (ROOT / "app/rsfx/static/app.js").read_text(encoding="utf-8")
        # Web UI must display the runtime health version, not a static string.
        self.assertIn("RSFX ${h.version} · online", frontend)
        self.assertNotIn("RSFX 0.1.0 · online", frontend)
        self.assertIn(f"RetroStation FX v{version} Verification", verify)
        audit_script = ROOT / "tools/audit_release_tree.py"
        # The release audit script is intentionally absent from public
        # archives. Verify its version if present in a maintainer checkout.
        if audit_script.is_file():
            release_audit = audit_script.read_text(encoding="utf-8")
            self.assertEqual(
                re.search(r'^RELEASE_VERSION = "([^"]+)"',
                          release_audit, re.MULTILINE).group(1), version
            )
        self.assertTrue(readme.startswith("# RetroStation FX (RSFX)\n"))
        # Code-version badge is valid before a public release is published.
        # Keep branch version and release status independent; never require a
        # GitHub Releases tag for the branch currently under development.
        self.assertIn(
            f"https://img.shields.io/badge/version-v{version}-blue?style=for-the-badge",
            readme,
        )
        self.assertTrue(
            'alt="Release status: Release Candidate"' in readme
            or 'alt="Release status: Released"' in readme
        )
        self.assertIn('href="CHANGELOG.md"', readme)
        self.assertNotIn("img.shields.io/github/v/release", readme)
        self.assertIn("[Changelog](CHANGELOG.md)", readme)
        self.assertNotIn("v0.2.0", readme)
        self.assertRegex(release_notes, r"v0\.1\.1 — (Release candidate|Released)")
        self.assertIn("v0.1.0 — First public release", release_notes)
        self.assertNotIn("PR #", release_notes)
        self.assertNotRegex(release_notes, r"(?i)github\.com/[^/\s]+/[^/\s]+[-_]private")
        maintainer = (ROOT / "docs/MAINTAINER-GUIDE.md").read_text(encoding="utf-8")
        self.assertIn("python3 tools/update_hashes.py", maintainer)
        self.assertEqual(HASH_MANIFEST_VERSION, version)
        self.assertEqual(VERSION_HEADER, f"# RetroStation FX v{version} development branch")
        for manifest in (live_manifest, package_manifest):
            hashes = [line for line in manifest.splitlines()
                      if re.match(r"^[0-9a-f]{64}\\s", line)]
            if "Static hashes are intentionally not frozen" in manifest:
                self.assertFalse(hashes)
            else:
                self.assertTrue(hashes, "release manifests must contain hashes")

    def test_live_source_manifest_inventory_covers_installed_artwork(self):
        # Install copies all rsfx/*.py, static files and seasonal PNG assets.
        # The manifest inventory must not silently omit newly added runtime
        # modules or graphics in later releases.
        expected = {
            path.relative_to(ROOT).as_posix()
            for subdir, pattern in (
                ("app/rsfx", "*.py"),
                ("app/rsfx/static", "*"),
                ("app/rsfx/assets/holiday", "*.png"),
            )
            for path in (ROOT / subdir).glob(pattern) if path.is_file()
        }
        expected.update((
            "app/adapter/rsfx-etv-adapter.py",
            "app/tools/etv_yaml_owner.py",
            "app/tools/selftest.py",
            "app/requirements.txt",
            "app/requirements.lock",
            "app/VERSION",
        ))
        self.assertEqual(
            expected, set(LIVE_PATHS),
            f"missing live hash coverage: {sorted(expected - set(LIVE_PATHS))}; "
            f"uninstalled inventory paths: {sorted(set(LIVE_PATHS) - expected)}",
        )

    def test_package_hash_generation_includes_license_and_security_policy(self):
        package_paths = {path.relative_to(ROOT).as_posix() for path in package_files()}

        self.assertTrue({"LICENSE", "SECURITY.md"} <= package_paths)


if __name__ == "__main__":
    unittest.main()
