"""Regression tests for scoped native Linux ACL repair.

A real POSIX ACL integration test runs only when privileges and acl utilities
are available; CI remains non-destructive when those prerequisites are absent.
"""
from __future__ import annotations

import os
from pathlib import Path
import pwd
import shutil
import subprocess
import tempfile
import unittest


INSTALLER = Path(__file__).resolve().parents[1] / "retrostation_fx_linux.sh"


def _installer_functions() -> str:
    """Extract only the permission functions; never execute installer startup."""
    source = INSTALLER.read_text(encoding="utf-8")
    start = source.index("assert_acl_scope() {")
    end = source.index("remove_etv_script_dir_access() {", start)
    return "set -Eeuo pipefail\n" + source[start:end]


class InstallerACLTests(unittest.TestCase):
    def test_acl_function_syntax(self):
        subprocess.run(["bash", "-n"], input=_installer_functions(),
                       check=True, text=True, capture_output=True)

    @unittest.skipUnless(os.geteuid() == 0, "real ACL integration requires root")
    def test_repairs_masked_ancestors_and_tests_real_write(self):
        required = ("getfacl", "setfacl", "runuser", "mktemp")
        if any(shutil.which(program) is None for program in required):
            self.skipTest("POSIX ACL utilities are unavailable")
        try:
            pwd.getpwnam("nobody")
            pwd.getpwnam("daemon")
        except KeyError:
            self.skipTest("nobody/daemon users unavailable")
        with tempfile.TemporaryDirectory(prefix="rsfx-acl-", dir="/tmp") as tmp:
            root = Path(tmp)
            parent = root / "one"
            nested = parent / "two"
            script = nested / "script"
            script.mkdir(parents=True)
            for directory in (root, parent, nested, script):
                directory.chmod(0o700)
                subprocess.run(
                    ["setfacl", "-m", "u:nobody:--x" if directory != script
                     else "u:nobody:rwx", str(directory)],
                    check=True, capture_output=True,
                )
                # chmod changes the effective mask to --- (original defect).
                directory.chmod(0o700)

            managed = script / "rsfx-existing.yml"
            managed.write_text("# Managed by RetroStation FX 0.1.0\\nname: existing\\n",
                               encoding="utf-8")
            managed.chmod(0o600)
            subprocess.run(["setfacl", "-m", "u:nobody:rw-", str(managed)],
                           check=True)
            managed.chmod(0o600)  # Mask now removes service-account write access.

            denied = subprocess.run(
                ["runuser", "-u", "nobody", "--", "test", "-x", str(nested)],
            )
            self.assertNotEqual(denied.returncode, 0)
            original = {str(p): (p.stat().st_uid, p.stat().st_gid)
                        for p in (root, parent, nested, script)}
            cmd = (_installer_functions()
                   + '\nconfigure_etv_script_dir_access "$1" nobody 0 0\n')
            subprocess.run(
                ["bash", "-c", cmd, "acl-test", str(script)],
                check=True, text=True, capture_output=True,
            )
            for directory in (root, parent, nested):
                subprocess.run(
                    ["runuser", "-u", "nobody", "--", "test", "-x", str(directory)],
                    check=True,
                )
                # A different service identity must not gain traversal.
                denied = subprocess.run(
                    ["runuser", "-u", "daemon", "--", "test", "-x", str(directory)],
                )
                self.assertNotEqual(denied.returncode, 0)
            subprocess.run(
                ["runuser", "-u", "nobody", "--", "sh", "-c",
                 'touch "$1/rsfx-test.yml" && rm "$1/rsfx-test.yml"',
                 "sh", str(script)],
                check=True,
            )
            subprocess.run(["runuser", "-u", "nobody", "--", "test", "-w", str(managed)],
                           check=True)
            self.assertEqual(managed.stat().st_uid, 0)
            self.assertEqual(
                original,
                {str(p): (p.stat().st_uid, p.stat().st_gid)
                 for p in (root, parent, nested, script)},
            )

    @unittest.skipUnless(os.geteuid() == 0, "real ACL integration requires root")
    def test_refuses_to_widen_mask_for_unrelated_group(self):
        required = ("getfacl", "setfacl", "runuser")
        if any(shutil.which(program) is None for program in required):
            self.skipTest("POSIX ACL utilities are unavailable")
        try:
            pwd.getpwnam("nobody")
        except KeyError:
            self.skipTest("nobody user unavailable")
        with tempfile.TemporaryDirectory(prefix="rsfx-acl-", dir="/tmp") as tmp:
            path = Path(tmp)
            # Owning group has x but currently cannot traverse due to mask ---.
            path.chmod(0o710)
            subprocess.run(["setfacl", "-m", "u:nobody:--x", str(path)], check=True)
            path.chmod(0o710)
            subprocess.run(["setfacl", "-m", "m::---", str(path)], check=True)
            cmd = (_installer_functions()
                   + '\nrepair_service_acl "$1" nobody --x\n')
            result = subprocess.run(
                ["bash", "-c", cmd, "acl-test", str(path)],
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("broaden owning-group access", result.stderr)

    @unittest.skipUnless(os.geteuid() == 0, "real ACL integration requires root")
    def test_repairs_numeric_acl_and_acl_without_existing_mask(self):
        required = ("getfacl", "setfacl")
        if any(shutil.which(program) is None for program in required):
            self.skipTest("POSIX ACL utilities are unavailable")
        try:
            service_uid = pwd.getpwnam("nobody").pw_uid
        except KeyError:
            self.skipTest("nobody user unavailable")
        with tempfile.TemporaryDirectory(prefix="rsfx-acl-", dir="/tmp") as tmp:
            root = Path(tmp)
            numeric = root / "numeric"
            numeric.mkdir(mode=0o700)
            subprocess.run(
                ["setfacl", "-m", f"u:{service_uid}:rwx", str(numeric)],
                check=True,
            )
            numeric.chmod(0o700)
            no_mask = root / "no-mask"
            no_mask.mkdir(mode=0o700)

            for path in (numeric, no_mask):
                cmd = _installer_functions() + '\nrepair_service_acl "$1" nobody rwx\n'
                subprocess.run(
                    ["bash", "-c", cmd, "acl-test", str(path)],
                    check=True, text=True, capture_output=True,
                )
                acl = subprocess.run(
                    ["getfacl", "-cp", str(path)],
                    check=True, capture_output=True, text=True,
                ).stdout
                self.assertIn("user:nobody:rwx", acl)
                self.assertIn("mask::rwx", acl)
                self.assertIn("group::---", acl)

    @unittest.skipUnless(os.geteuid() == 0, "symlink safety test requires root")
    def test_refuses_symlinked_script_graphics_paths(self):
        required = ("getfacl", "setfacl", "runuser")
        if any(shutil.which(program) is None for program in required):
            self.skipTest("POSIX ACL utilities are unavailable")
        with tempfile.TemporaryDirectory(prefix="rsfx-acl-", dir="/tmp") as tmp:
            root = Path(tmp)
            target = root / "target"
            script = target / "script"
            script.mkdir(parents=True)
            script.chmod(0o700)
            final_link = root / "final-link"
            final_link.symlink_to(script, target_is_directory=True)
            parent_link = root / "parent-link"
            parent_link.symlink_to(target, target_is_directory=True)
            before = subprocess.run(
                ["getfacl", "-cp", str(script)],
                check=True, capture_output=True, text=True,
            ).stdout

            for path in (final_link, parent_link / "script"):
                cmd = (_installer_functions()
                       + '\nconfigure_etv_script_dir_access "$1" nobody 0 0\n')
                result = subprocess.run(
                    ["bash", "-c", cmd, "acl-test", str(path)],
                    capture_output=True, text=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("through a symlink", result.stderr)

            after = subprocess.run(
                ["getfacl", "-cp", str(script)],
                check=True, capture_output=True, text=True,
            ).stdout
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
