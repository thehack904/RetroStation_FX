from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPOSITORY_ROOT / "retrostation_fx_linux.sh"
SERVICE_UNIT = REPOSITORY_ROOT / "systemd" / "retrostation-fx.service"


class ServiceAccountTests(unittest.TestCase):
    def test_unit_uses_dedicated_unprivileged_account(self):
        unit = SERVICE_UNIT.read_text(encoding="utf-8")
        self.assertIn("User=retrostation-fx", unit)
        self.assertIn("Group=retrostation-fx", unit)
        self.assertNotIn("User=root", unit)
        self.assertIn("NoNewPrivileges=true", unit)
        handoff_service = (
            REPOSITORY_ROOT / "systemd" / "retrostation-fx-etv-yaml-owner@.service"
        ).read_text(encoding="utf-8")
        handoff_socket = (
            REPOSITORY_ROOT / "systemd" / "retrostation-fx-etv-yaml-owner.socket"
        ).read_text(encoding="utf-8")
        self.assertIn("User=root", handoff_service)
        self.assertIn("NoNewPrivileges=true", handoff_service)
        self.assertIn(
            "CapabilityBoundingSet=CAP_CHOWN CAP_FOWNER CAP_DAC_OVERRIDE",
            handoff_service,
        )
        self.assertIn("SocketUser=retrostation-fx", handoff_socket)
        self.assertIn("SocketMode=0600", handoff_socket)
        self.assertIn(
            "SO_PEERCRED",
            (REPOSITORY_ROOT / "app/tools/etv_yaml_owner.py").read_text(encoding="utf-8"),
        )
        installer = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('install -m 0644 "$SCRIPT_DIR/systemd/retrostation-fx-etv-yaml-owner@.service"', installer)
        self.assertIn('install -m 0644 "$SCRIPT_DIR/systemd/retrostation-fx-etv-yaml-owner.socket"', installer)
        self.assertLess(
            installer.index("systemctl enable --now retrostation-fx-etv-yaml-owner.socket"),
            installer.index("systemctl start retrostation-fx.service"),
        )

    def test_installer_detects_active_ersatztv_effective_uid_and_gid(self):
        source = INSTALLER.read_text(encoding="utf-8")
        start = source.index("detect_ersatztv_identity() {")
        end = source.index("\nensure_service_account() {", start)

        with tempfile.TemporaryDirectory() as directory:
            mock_bin = Path(directory)
            systemctl = mock_bin / "systemctl"
            systemctl.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' 'LoadState=loaded' 'ActiveState=active' "
                f"'MainPID={os.getpid()}' 'User=ignored' 'Group=ignored'\n",
                encoding="utf-8",
            )
            systemctl.chmod(0o755)
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    source[start:end] + "\ndetect_ersatztv_identity\n"
                    + 'printf "%s:%s\\n" "$ETV_UID" "$ETV_GID"',
                ],
                capture_output=True,
                text=True,
                env={**os.environ, "PATH": f"{mock_bin}{os.pathsep}{os.environ['PATH']}"},
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.strip().splitlines()[-1],
            f"{os.getuid()}:{os.getgid()}",
        )

    def test_installer_refuses_unloaded_ersatztv_identity(self):
        source = INSTALLER.read_text(encoding="utf-8")
        start = source.index("detect_ersatztv_identity() {")
        end = source.index("\nensure_service_account() {", start)

        with tempfile.TemporaryDirectory() as directory:
            mock_bin = Path(directory)
            systemctl = mock_bin / "systemctl"
            systemctl.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' 'LoadState=not-found' 'ActiveState=inactive' "
                "'MainPID=0' 'User=' 'Group='\n",
                encoding="utf-8",
            )
            systemctl.chmod(0o755)
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    source[start:end] + "\ndetect_ersatztv_identity\n",
                ],
                capture_output=True,
                text=True,
                env={**os.environ, "PATH": f"{mock_bin}{os.pathsep}{os.environ['PATH']}"},
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("is not loaded", result.stderr)

    def test_installer_creates_or_reuses_locked_system_account(self):
        source = INSTALLER.read_text(encoding="utf-8")
        start = source.index("ensure_service_account() {")
        end = source.index("\nassert_acl_scope() {", start)
        function = source[start:end]

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mock_bin = root / "bin"
            mock_bin.mkdir()
            log = root / "commands"
            for command, body in {
                "getent": (
                    "#!/bin/sh\n"
                    'case "$1:$2" in\n'
                    '  group:retrostation-fx) [ -f "$GROUP_EXISTS" ] && echo "retrostation-fx:x:54999:";;\n'
                    '  passwd:retrostation-fx) [ -f "$USER_EXISTS" ] && echo "retrostation-fx:x:54999:54999:RSFX:/nonexistent:/usr/sbin/nologin";;\n'
                    "  *) exit 1;;\n"
                    "esac\n"
                ),
                "groupadd": (
                    "#!/bin/sh\n"
                    'echo "groupadd $*" >> "$COMMAND_LOG"\n'
                    'touch "$GROUP_EXISTS"\n'
                ),
                "useradd": (
                    "#!/bin/sh\n"
                    'echo "useradd $*" >> "$COMMAND_LOG"\n'
                    'touch "$USER_EXISTS"\n'
                ),
                "usermod": (
                    "#!/bin/sh\n"
                    'echo "usermod $*" >> "$COMMAND_LOG"\n'
                ),
            }.items():
                path = mock_bin / command
                path.write_text(body, encoding="utf-8")
                path.chmod(0o755)

            env = {
                **os.environ,
                "PATH": f"{mock_bin}{os.pathsep}{os.environ['PATH']}",
                "GROUP_EXISTS": str(root / "group"),
                "USER_EXISTS": str(root / "user"),
                "COMMAND_LOG": str(log),
            }
            subprocess.run(
                [
                    "bash",
                    "-c",
                    'SERVICE_USER="retrostation-fx"; SERVICE_GROUP="retrostation-fx"\n'
                    + function
                    + "\nensure_service_account",
                ],
                check=True,
                env=env,
            )
            created = log.read_text(encoding="utf-8")
            self.assertIn("groupadd --system retrostation-fx", created)
            self.assertIn("--no-create-home", created)
            self.assertIn("--shell /usr/sbin/nologin", created)
            self.assertTrue((root / "group").exists())
            self.assertTrue((root / "user").exists())

            log.unlink()
            subprocess.run(
                [
                    "bash",
                    "-c",
                    'SERVICE_USER="retrostation-fx"; SERVICE_GROUP="retrostation-fx"\n'
                    + function
                    + "\nensure_service_account",
                ],
                check=True,
                env=env,
            )
            upgraded = log.read_text(encoding="utf-8")
            self.assertNotIn("groupadd", upgraded)
            self.assertNotIn("useradd", upgraded)
            self.assertIn("usermod --gid retrostation-fx", upgraded)
            self.assertIn("--groups  --home /nonexistent", upgraded)
            self.assertIn("--lock retrostation-fx", upgraded)

    def test_acl_setup_refuses_to_widen_existing_named_permissions(self):
        if shutil.which("setfacl") is None or shutil.which("getfacl") is None:
            self.skipTest("POSIX ACL utilities are unavailable")
        source = INSTALLER.read_text(encoding="utf-8")
        start = source.index("assert_acl_scope() {")
        end = source.index("\nconfigure_etv_script_dir_access() {", start)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "graphics"
            path.mkdir()
            subprocess.run(["setfacl", "-m", "u:root:r-x", str(path)], check=True)
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    source[start:end] + '\nassert_acl_scope "$1" retrostation-fx',
                    "test",
                    str(path),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Refusing to widen its ACL mask", result.stderr)

    def test_etv_acl_allows_service_yaml_lifecycle(self):
        required = ("setfacl", "getfacl", "runuser")
        if any(shutil.which(command) is None for command in required):
            self.skipTest("POSIX ACL utilities are unavailable")
        if subprocess.run(["getent", "passwd", "nobody"], capture_output=True).returncode:
            self.skipTest("nobody account is unavailable for ACL test")

        source = INSTALLER.read_text(encoding="utf-8")
        start = source.index("assert_acl_scope() {")
        end = source.index("\nremove_etv_script_dir_access() {", start)
        function = source[start:end]

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mock_bin = root / "bin"
            mock_bin.mkdir()
            if os.geteuid() != 0:
                mock_runuser = mock_bin / "runuser"
                mock_runuser.write_text(
                    "#!/bin/sh\n"
                    '[ "$1" = "-u" ] || exit 2\n'
                    "shift 3\n"
                    'exec "$@"\n',
                    encoding="utf-8",
                )
                mock_runuser.chmod(0o755)
            script_dir = root / "home" / "ersatztv" / "graphics"
            script_dir.mkdir(parents=True)
            script_dir.chmod(0o700)
            owner_uid = subprocess.run(
                ["id", "-u", "nobody" if os.geteuid() == 0 else str(os.getuid())],
                capture_output=True,
                check=True,
                text=True,
            ).stdout.strip()
            owner_gid = subprocess.run(
                ["id", "-g", "nobody" if os.geteuid() == 0 else str(os.getuid())],
                capture_output=True,
                check=True,
                text=True,
            ).stdout.strip()
            old_yaml = script_dir / "rsfx-existing.yml"
            old_yaml.write_text("# Managed by RetroStation FX\nname: Existing\n", encoding="utf-8")
            old_yaml.chmod(0o644)
            original_owner = old_yaml.stat().st_uid
            if os.geteuid() == 0:
                os.chown(old_yaml, int(owner_uid), int(owner_gid))
                original_owner = int(owner_uid)
            unrelated_yaml = script_dir / "rsfx-unrelated.yml"
            unrelated_yaml.write_text("# Managed by someone else\nname: Unrelated\n", encoding="utf-8")
            unrelated_yaml.chmod(0o644)
            state_dir = root / "state"
            state_dir.mkdir(mode=0o700)
            subprocess.run(
                ["setfacl", "-m", "u:nobody:rwx", str(state_dir)],
                check=True,
            )

            subprocess.run(
                [
                    "bash",
                    "-c",
                    function + '\nconfigure_etv_script_dir_access "$1" nobody "$2" "$3"',
                    "test",
                    str(script_dir),
                    owner_uid,
                    owner_gid,
                ],
                env={**os.environ, "PATH": f"{mock_bin}{os.pathsep}{os.environ['PATH']}"},
                check=True,
            )
            acl = subprocess.run(
                ["getfacl", "-cp", str(old_yaml)],
                capture_output=True,
                check=True,
                text=True,
            ).stdout
            self.assertIn("user:nobody:rw-", acl)
            unrelated_acl = subprocess.run(
                ["getfacl", "-cp", str(unrelated_yaml)],
                capture_output=True,
                check=True,
                text=True,
            ).stdout
            self.assertNotIn("user:nobody:", unrelated_acl)
            if os.geteuid() == 0:
                subprocess.run(
                    ["runuser", "-u", "nobody", "--", "test", "-w", str(script_dir)],
                    check=True,
                )
                subprocess.run(
                    ["runuser", "-u", "nobody", "--", "test", "-w", str(old_yaml)],
                    check=True,
                )
            self.assertEqual(old_yaml.stat().st_uid, int(owner_uid))

            env = os.environ.copy()
            env.update(
                PYTHONPATH=str(REPOSITORY_ROOT / "app"),
                RSFX_DATABASE=str(state_dir / "rsfx.db"),
                RSFX_ETV_SCRIPT_DIR=str(script_dir),
                RSFX_ETV_OWNER_UID="",
                RSFX_ETV_OWNER_GID="",
                RSFX_EXISTING_YAML=str(old_yaml),
                PATH=f"{mock_bin}{os.pathsep}{os.environ['PATH']}",
            )
            mock_systemctl = mock_bin / "systemctl"
            mock_systemctl.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' "
                "'ActiveState=active' "
                "'MainPID=1234' "
                "'ExecMainStartTimestamp=Wed 2026-10-07 12:00:00 UTC'\n",
                encoding="utf-8",
            )
            mock_systemctl.chmod(0o755)
            lifecycle = """
from rsfx.database import Database
from rsfx.ersatztv import delete_yaml, sync_yaml
from rsfx.ersatztv_restart import detect_ersatztv_start
from rsfx.models import StylePut

restart = detect_ersatztv_start()
assert restart["detected"] and restart["active"] and restart["pid"] == 1234
db = Database(__import__("pathlib").Path(__import__("os").environ["RSFX_DATABASE"]))
db.initialize()
style = db.put_style(StylePut(name="ACL Lifecycle Test"))
db.set_style_yaml_path(style.id, __import__("os").environ["RSFX_EXISTING_YAML"])
style = db.get_style(style.id)
path = sync_yaml(style)
assert path.is_file()
updated = db.put_style(StylePut(name="ACL Lifecycle Updated"), style_id=style.id)
sync_yaml(updated)
assert "ACL Lifecycle Updated" in path.read_text(encoding="utf-8")
delete_yaml(updated)
assert not path.exists()
"""
            command = [sys.executable, "-c", lifecycle]
            if os.geteuid() == 0:
                command = ["runuser", "-u", "nobody", "--", *command]
            subprocess.run(command, check=True, env=env)

            remove_start = source.index("remove_etv_script_dir_access() {")
            remove_end = source.index("\nconfigure_service_filesystem_access() {", remove_start)
            subprocess.run(
                [
                    "bash",
                    "-c",
                    source[remove_start:remove_end]
                    + '\nremove_etv_script_dir_access "$1" nobody',
                    "test",
                    str(script_dir),
                ],
                check=True,
            )
            remaining_acl = subprocess.run(
                ["getfacl", "-cp", str(script_dir)],
                capture_output=True,
                check=True,
                text=True,
            ).stdout
            self.assertNotIn("user:nobody:", remaining_acl)
            self.assertNotIn("default:user:nobody:", remaining_acl)


if __name__ == "__main__":
    unittest.main()
