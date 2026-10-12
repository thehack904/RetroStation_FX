from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


APP_ROOT = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP_ROOT))

from tools.etv_yaml_owner import handoff_yaml_ownership
from rsfx.ersatztv import handoff_yaml_ownership as request_ownership_handoff


class ErsatzTVOwnerHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.script_dir = self.root / "graphics"
        self.script_dir.mkdir()
        self.config = self.root / "rsfx.env"
        self.config.write_text(
            "\n".join(
                (
                    f"RSFX_ETV_SCRIPT_DIR={self.script_dir}",
                    f"RSFX_ETV_OWNER_UID={os.getuid()}",
                    f"RSFX_ETV_OWNER_GID={os.getgid()}",
                    f"RSFX_SERVICE_UID={os.getuid() + 1}",
                    "RSFX_ADAPTER_PYTHON=/opt/rsfx/venv/bin/python",
                    "RSFX_ADAPTER_PATH=/opt/rsfx/adapter/rsfx-etv-adapter.py",
                    "RSFX_PUBLIC_URL=http://127.0.0.1:5055",
                )
            )
            + "\n",
            encoding="utf-8",
        )
        self.managed_file = self.script_dir / "rsfx-managed-style.yml"
        self.managed_file.write_text(self.valid_yaml(), encoding="utf-8")

    def valid_yaml(self):
        return """# Managed by RetroStation FX 0.1.0
name: Managed
command: /opt/rsfx/venv/bin/python
args:
  - /opt/rsfx/adapter/rsfx-etv-adapter.py
  - --url
  - http://127.0.0.1:5055
  - --style-id
  - "1"
z_index: 20
epg_entries: 2
start_seconds: 0
duration_seconds: 21600
pixel_format: bgra
format: Packet
"""

    def tearDown(self):
        self.temporary.cleanup()

    def getfacl_result(self, output="user::rw-\ngroup::r--\nother::r--\n"):
        return subprocess.CompletedProcess(
            args=["getfacl"],
            returncode=0,
            stdout=output,
            stderr="",
        )

    def test_valid_managed_file_changes_owner_and_applies_service_acl(self):
        with (
            patch(
                "tools.etv_yaml_owner.subprocess.run",
                side_effect=[self.getfacl_result(), subprocess.CompletedProcess([], 0)],
            ) as run,
            patch("tools.etv_yaml_owner.os.fchown") as fchown,
        ):
            handoff_yaml_ownership(self.managed_file, self.config)

        fchown.assert_called_once_with(
            fchown.call_args.args[0],
            os.getuid(),
            os.getgid(),
        )
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].args[0][0], "/usr/bin/getfacl")
        self.assertEqual(run.call_args_list[1].args[0][0], "/usr/bin/setfacl")
        self.assertEqual(
            run.call_args_list[1].args[0][1:],
            ["-m", "u:retrostation-fx:rw-,m::rw-", run.call_args_list[1].args[0][-1]],
        )
        self.assertTrue(run.call_args_list[1].kwargs["pass_fds"])

    def test_acl_utilities_do_not_use_path_lookup(self):
        with (
            patch(
                "tools.etv_yaml_owner.subprocess.run",
                side_effect=[self.getfacl_result(), subprocess.CompletedProcess([], 0)],
            ) as run,
            patch("tools.etv_yaml_owner.os.fchown"),
            patch.dict(os.environ, {"PATH": "/tmp/attacker-first:/usr/bin:/bin"}),
        ):
            handoff_yaml_ownership(self.managed_file, self.config)
        self.assertEqual(run.call_args_list[0].args[0][0], "/usr/bin/getfacl")
        self.assertEqual(run.call_args_list[1].args[0][0], "/usr/bin/setfacl")

    def test_rejects_yaml_outside_configured_script_directory(self):
        outside = self.root / "rsfx-outside.yml"
        outside.write_text("# Managed by RetroStation FX\n", encoding="utf-8")
        with patch("tools.etv_yaml_owner.os.fchown") as fchown:
            with self.assertRaisesRegex(ValueError, "outside"):
                handoff_yaml_ownership(outside, self.config)
        fchown.assert_not_called()

    def test_rejects_unmanaged_yaml_before_chown(self):
        self.managed_file.write_text("# Managed by someone else\n", encoding="utf-8")
        with (
            patch("tools.etv_yaml_owner.subprocess.run") as run,
            patch("tools.etv_yaml_owner.os.fchown") as fchown,
        ):
            with self.assertRaisesRegex(ValueError, "marker"):
                handoff_yaml_ownership(self.managed_file, self.config)
        run.assert_not_called()
        fchown.assert_not_called()

    def test_rejects_unrelated_named_acl_before_chown(self):
        with (
            patch(
                "tools.etv_yaml_owner.subprocess.run",
                return_value=self.getfacl_result("user::rw-\nuser:unrelated:r--\n"),
            ),
            patch("tools.etv_yaml_owner.os.fchown") as fchown,
        ):
            with self.assertRaisesRegex(ValueError, "unrelated named ACL"):
                handoff_yaml_ownership(self.managed_file, self.config)
        fchown.assert_not_called()

    def test_rejects_invalid_filename(self):
        invalid = self.script_dir / "unrelated.yml"
        invalid.write_text(self.valid_yaml(), encoding="utf-8")
        with patch("tools.etv_yaml_owner.os.fchown") as fchown:
            with self.assertRaisesRegex(ValueError, "filename"):
                handoff_yaml_ownership(invalid, self.config)
        fchown.assert_not_called()

    def test_rejects_hardlinked_managed_files(self):
        hardlink = self.script_dir / "rsfx-hardlinked-style.yml"
        os.link(self.managed_file, hardlink)
        with patch("tools.etv_yaml_owner.os.fchown") as fchown:
            with self.assertRaisesRegex(ValueError, "regular file"):
                handoff_yaml_ownership(hardlink, self.config)
        fchown.assert_not_called()

    def test_rejects_duplicate_yaml_keys(self):
        self.managed_file.write_text(
            self.valid_yaml().replace(
                "name: Managed\n",
                "name: Managed\nname: Unexpected\n",
            ),
            encoding="utf-8",
        )
        with patch("tools.etv_yaml_owner.os.fchown") as fchown:
            with self.assertRaisesRegex(ValueError, "duplicate keys"):
                handoff_yaml_ownership(self.managed_file, self.config)
        fchown.assert_not_called()

    def test_rejects_untrusted_yaml_command(self):
        self.managed_file.write_text(
            self.valid_yaml().replace(
                "command: /opt/rsfx/venv/bin/python",
                "command: /bin/sh",
            ),
            encoding="utf-8",
        )
        with (
            patch("tools.etv_yaml_owner.subprocess.run") as run,
            patch("tools.etv_yaml_owner.os.fchown") as fchown,
        ):
            with self.assertRaisesRegex(ValueError, "command or arguments"):
                handoff_yaml_ownership(self.managed_file, self.config)
        run.assert_not_called()
        fchown.assert_not_called()

    def test_rsfx_requests_handoff_over_local_systemd_socket(self):
        class FakeSocket:
            def __init__(self, response=b"OK\n"):
                self.response = response
                self.sent = b""
                self.path = None
                self.read = False

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

            def settimeout(self, _timeout):
                pass

            def connect(self, path):
                self.path = path

            def sendall(self, data):
                self.sent = data

            def shutdown(self, _how):
                pass

            def recv(self, _size):
                if self.read:
                    return b""
                self.read = True
                return self.response

        connection = FakeSocket()
        with (
            patch(
                "rsfx.ersatztv.settings",
                SimpleNamespace(ersatztv_owner_uid=100, ersatztv_owner_gid=100),
            ),
            patch("rsfx.ersatztv.socket.socket", return_value=connection),
        ):
            request_ownership_handoff(self.managed_file)
        self.assertEqual(connection.path, "/run/retrostation-fx-etv-yaml-owner.sock")
        self.assertEqual(connection.sent, f"{self.managed_file}\n".encode())

    def test_rsfx_reports_ownership_handoff_failure(self):
        class FailedSocket:
            def __init__(self):
                self.read = False

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

            def settimeout(self, _timeout):
                pass

            def connect(self, _path):
                pass

            def sendall(self, _data):
                pass

            def shutdown(self, _how):
                pass

            def recv(self, _size):
                if self.read:
                    return b""
                self.read = True
                return b"ERROR: rejected\n"

        with (
            patch(
                "rsfx.ersatztv.settings",
                SimpleNamespace(ersatztv_owner_uid=100, ersatztv_owner_gid=100),
            ),
            patch("rsfx.ersatztv.socket.socket", return_value=FailedSocket()),
        ):
            with self.assertRaisesRegex(RuntimeError, "rejected"):
                request_ownership_handoff(self.managed_file)

    @unittest.skipUnless(os.geteuid() == 0, "ownership integration requires root")
    def test_root_handoff_preserves_both_accounts_lifecycle_access(self):
        required = ("setfacl", "getfacl", "runuser")
        if any(shutil.which(command) is None for command in required):
            self.skipTest("POSIX ACL utilities are unavailable")
        try:
            service_uid = subprocess.run(
                ["id", "-u", "retrostation-fx"], check=True, capture_output=True, text=True
            ).stdout.strip()
            owner_uid = subprocess.run(
                ["id", "-u", "daemon"], check=True, capture_output=True, text=True
            ).stdout.strip()
            owner_gid = subprocess.run(
                ["id", "-g", "daemon"], check=True, capture_output=True, text=True
            ).stdout.strip()
        except subprocess.CalledProcessError:
            self.skipTest("retrostation-fx and daemon accounts are required")

        subprocess.run(
            ["setfacl", "-m", f"u:retrostation-fx:--x,u:daemon:--x", str(self.root)],
            check=True,
        )
        self.script_dir.chmod(0o750)
        os.chown(self.script_dir, int(owner_uid), int(owner_gid))
        subprocess.run(
            ["setfacl", "-m", "u:retrostation-fx:rwx", str(self.script_dir)],
            check=True,
        )
        self.config.write_text(
            "\n".join(
                (
                    f"RSFX_ETV_SCRIPT_DIR={self.script_dir}",
                    f"RSFX_ETV_OWNER_UID={owner_uid}",
                    f"RSFX_ETV_OWNER_GID={owner_gid}",
                    f"RSFX_SERVICE_UID={service_uid}",
                    "RSFX_ADAPTER_PYTHON=/opt/rsfx/venv/bin/python",
                    "RSFX_ADAPTER_PATH=/opt/rsfx/adapter/rsfx-etv-adapter.py",
                    "RSFX_PUBLIC_URL=http://127.0.0.1:5055",
                )
            )
            + "\n",
            encoding="utf-8",
        )
        self.managed_file.unlink()
        unrelated_file = self.script_dir / "rsfx-unrelated.yml"
        unrelated_file.write_text("# Managed by another tool\n", encoding="utf-8")
        unrelated_file.chmod(0o644)
        os.chown(unrelated_file, int(owner_uid), int(owner_gid))
        subprocess.run(
            [
                "runuser",
                "-u",
                "retrostation-fx",
                "--",
                "sh",
                "-c",
                'cat > "$1" <<\'YAML\'\n'
                + self.valid_yaml()
                + "YAML\n",
                "sh",
                str(self.managed_file),
            ],
            check=True,
        )

        handoff_yaml_ownership(self.managed_file, self.config)
        stat_result = self.managed_file.stat()
        self.assertEqual((stat_result.st_uid, stat_result.st_gid), (int(owner_uid), int(owner_gid)))
        subprocess.run(["runuser", "-u", "daemon", "--", "cat", str(self.managed_file)], check=True)
        subprocess.run(
            [
                "runuser",
                "-u",
                "retrostation-fx",
                "--",
                "sh",
                "-c",
                'printf "%s\\n" "updated: true" >> "$1" && test -w "$1"',
                "sh",
                str(self.managed_file),
            ],
            check=True,
        )
        subprocess.run(
            [
                "runuser",
                "-u",
                "retrostation-fx",
                "--",
                "rm",
                str(self.managed_file),
            ],
            check=True,
        )
        self.assertEqual(unrelated_file.stat().st_uid, int(owner_uid))
        self.assertNotIn(
            "user:retrostation-fx:",
            subprocess.run(
                ["getfacl", "-cp", str(unrelated_file)],
                check=True,
                capture_output=True,
                text=True,
            ).stdout,
        )


if __name__ == "__main__":
    unittest.main()
