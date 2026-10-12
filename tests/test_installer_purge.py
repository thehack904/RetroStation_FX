from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "retrostation_fx_linux.sh"


class InstallerPurgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = INSTALLER.read_text(encoding="utf-8")
        start = source.index("purge_managed_yaml() {")
        end = source.index("\nuninstall_rsfx() {", start)
        cls.function = source[start:end]

    def test_purge_fallback_preserves_unrelated_nested_and_symlink_files(self):
        with tempfile.TemporaryDirectory(prefix="rsfx purge ") as directory:
            root = Path(directory)
            graphics = root / "graphics"
            graphics.mkdir()
            files = {
                "rsfx-managed.yml": "# Managed by RetroStation FX 0.1.0\n",
                "rsfx-legacy.yaml": "command: /opt/rsfx/venv/bin/python\n",
                "rsfx-unrelated.yml": "name: Unrelated\n",
                "other.yml": "# Managed by RetroStation FX 0.1.0\n",
            }
            for name, contents in files.items():
                (graphics / name).write_text(contents, encoding="utf-8")
            nested = graphics / "nested"
            nested.mkdir()
            (nested / "rsfx-managed.yml").write_text(files["rsfx-managed.yml"], encoding="utf-8")
            outside = root / "rsfx-outside.yml"
            outside.write_text(files["rsfx-managed.yml"], encoding="utf-8")
            link = graphics / "rsfx-link.yml"
            link.symlink_to(outside)
            result = self.invoke(root, graphics)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((graphics / "rsfx-managed.yml").exists())
            self.assertFalse((graphics / "rsfx-legacy.yaml").exists())
            for name in ("rsfx-unrelated.yml", "other.yml"):
                self.assertEqual((graphics / name).read_text(encoding="utf-8"), files[name])
            self.assertTrue(link.is_symlink())
            self.assertTrue(outside.exists())
            self.assertTrue((nested / "rsfx-managed.yml").exists())

    def test_inventory_paths_cannot_delete_outside_configured_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            graphics = root / "graphics"
            graphics.mkdir()
            outside = root / "rsfx-outside.yml"
            outside.write_text("name: Outside\n", encoding="utf-8")
            unrelated = graphics / "unrelated.yml"
            unrelated.write_text("name: Unrelated\n", encoding="utf-8")
            unsafe = graphics / "rsfx-..unsafe.yml"
            unsafe.write_text("name: Unsafe\n", encoding="utf-8")
            managed = graphics / "rsfx-inventory.yml"
            managed.write_text("name: Previously managed\n", encoding="utf-8")
            (root / "rsfx.db").touch()
            bin_dir = root / "bin"
            bin_dir.mkdir()
            sqlite = bin_dir / "sqlite3"
            sqlite.write_text(
                "#!/bin/sh\nprintf '%s\\n' "
                + " ".join(shlex.quote(str(path)) for path in (outside, unrelated, unsafe, managed))
                + "\n",
                encoding="utf-8",
            )
            sqlite.chmod(0o755)
            result = self.invoke(root, graphics, bin_dir)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(managed.exists())
            self.assertTrue(outside.exists())
            self.assertTrue(unrelated.exists())
            self.assertTrue(unsafe.exists())
            self.assertIn("Ignoring unsafe managed YAML filename", result.stderr)

    def invoke(self, root, graphics, bin_dir=None):
        environment = {
            **os.environ,
            "DEFAULT_ETV_SCRIPT_DIR": str(graphics),
            "STATE_ROOT": str(root),
            "ENV_FILE": str(root / "absent.env"),
            "SERVICE_USER": "unused-test-user",
        }
        if bin_dir:
            environment["PATH"] = f"{bin_dir}{os.pathsep}{os.environ['PATH']}"
        # Only the purge function runs; service and ACL operations are stubbed.
        return subprocess.run(
            ["bash", "-c", "set -euo pipefail\n"
             "read_env_value() { return 1; }\n"
             "remove_etv_script_dir_access() { :; }\n"
             + self.function + "\npurge_managed_yaml\n"],
            env=environment, capture_output=True, text=True,
        )


if __name__ == "__main__":
    unittest.main()
