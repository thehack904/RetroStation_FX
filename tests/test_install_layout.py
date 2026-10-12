from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class InstallLayoutTests(unittest.TestCase):
    def test_installed_selftest_without_installer_source(self):
        with tempfile.TemporaryDirectory() as directory:
            install_root = Path(directory) / "opt" / "rsfx"
            app_source = REPOSITORY_ROOT / "app"
            for path in (
                install_root / "rsfx",
                install_root / "rsfx" / "static",
                install_root / "adapter",
                install_root / "tools",
            ):
                path.mkdir(parents=True, exist_ok=True)
            for path in (app_source / "rsfx").glob("*.py"):
                shutil.copy2(path, install_root / "rsfx" / path.name)
            for name in ("index.html", "app.js", "style.css"):
                shutil.copy2(
                    app_source / "rsfx" / "static" / name,
                    install_root / "rsfx" / "static" / name,
                )
            shutil.copy2(
                app_source / "adapter" / "rsfx-etv-adapter.py",
                install_root / "adapter" / "rsfx-etv-adapter.py",
            )
            shutil.copy2(
                app_source / "tools" / "selftest.py",
                install_root / "tools" / "selftest.py",
            )
            shutil.copy2(
                app_source / "tools" / "etv_yaml_owner.py",
                install_root / "tools" / "etv_yaml_owner.py",
            )
            for name in ("requirements.txt", "requirements.lock", "VERSION"):
                shutil.copy2(app_source / name, install_root / name)
            selftest = install_root / "tools" / "selftest.py"
            self.assertTrue((install_root / "tools" / "etv_yaml_owner.py").is_file())
            self.assertTrue(selftest.is_file())
            self.assertFalse((install_root.parent / "retrostation_fx_linux.sh").exists())

            env = os.environ.copy()
            env["PYTHONPATH"] = str(install_root)
            result = subprocess.run(
                [sys.executable, str(selftest)],
                capture_output=True,
                env=env,
                text=True,
                check=True,
            )

            self.assertIn("PASS: Packet v1 RECTANGLES stream generation", result.stdout)


if __name__ == "__main__":
    unittest.main()
