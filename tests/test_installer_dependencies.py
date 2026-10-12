from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPOSITORY_ROOT / "retrostation_fx_linux.sh"


class InstallerDependencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = INSTALLER.read_text(encoding="utf-8")
        start = source.index("ensure_permission_dependencies() {")
        end = source.index("\nensure_service_account() {", start)
        cls.function = source[start:end]

    def make_harness(self, root: Path, *, missing: tuple[str, ...], os_id: str = "ubuntu"):
        bin_dir = root / "bin"
        bin_dir.mkdir()
        os_release = root / "os-release"
        os_release.write_text(f'ID="{os_id}"\nID_LIKE=""\n', encoding="utf-8")
        log = root / "apt.log"

        for tool in ("setfacl", "getfacl", "runuser"):
            if tool not in missing:
                path = bin_dir / tool
                path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                path.chmod(0o755)

        apt_get = bin_dir / "apt-get"
        apt_get.write_text(
            "#!/bin/bash\n"
            'echo "$*" >> "$APT_LOG"\n'
            'if [[ "$1" == update && "${FAIL_UPDATE:-0}" == 1 ]]; then exit 1; fi\n'
            'if [[ "$1" == install ]]; then\n'
            '  install_count=0\n'
            '  while IFS= read -r line; do [[ "$line" == install\\ * ]] && ((install_count+=1)); done < "$APT_LOG"\n'
            '  if [[ "${FAIL_FIRST_INSTALL:-0}" == 1 && "$install_count" == 1 ]]; then exit 1; fi\n'
            '  if [[ "${FAIL_ALL_INSTALLS:-0}" == 1 ]]; then exit 1; fi\n'
            '  for tool in ${INSTALL_TOOLS:-}; do\n'
            '    printf "#!/bin/sh\\nexit 0\\n" > "$MOCK_BIN/$tool"\n'
            '    /bin/chmod +x "$MOCK_BIN/$tool"\n'
            "  done\n"
            "fi\n",
            encoding="utf-8",
        )
        apt_get.chmod(0o755)
        env = {
            **os.environ,
            "PATH": str(bin_dir),
            "RSFX_OS_RELEASE_FILE": str(os_release),
            "APT_LOG": str(log),
            "MOCK_BIN": str(bin_dir),
            "INSTALL_TOOLS": " ".join(missing),
        }
        return bin_dir, log, env

    def invoke(self, env: dict[str, str]):
        return subprocess.run(
            ["/bin/bash", "-c", self.function + "\nensure_permission_dependencies"],
            capture_output=True,
            env=env,
            text=True,
        )

    def test_missing_acl_commands_are_installed_automatically(self):
        with tempfile.TemporaryDirectory() as directory:
            _, log, env = self.make_harness(
                Path(directory),
                missing=("setfacl", "getfacl"),
            )
            result = self.invoke(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                log.read_text(encoding="utf-8").splitlines(),
                ["install -y --no-install-recommends acl"],
            )

    def test_missing_runuser_uses_util_linux_package(self):
        with tempfile.TemporaryDirectory() as directory:
            _, log, env = self.make_harness(Path(directory), missing=("runuser",))
            result = self.invoke(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                log.read_text(encoding="utf-8").splitlines(),
                ["install -y --no-install-recommends util-linux"],
            )

    def test_retry_refreshes_indexes_only_after_failed_install(self):
        with tempfile.TemporaryDirectory() as directory:
            _, log, env = self.make_harness(
                Path(directory),
                missing=("setfacl", "getfacl"),
            )
            env["FAIL_FIRST_INSTALL"] = "1"
            result = self.invoke(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                log.read_text(encoding="utf-8").splitlines(),
                [
                    "install -y --no-install-recommends acl",
                    "update",
                    "install -y --no-install-recommends acl",
                ],
            )
            self.assertIn("retrying once", result.stdout)

    def test_existing_commands_skip_package_manager(self):
        with tempfile.TemporaryDirectory() as directory:
            _, log, env = self.make_harness(Path(directory), missing=())
            result = self.invoke(env)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(log.exists())

    def test_unsupported_os_fails_without_invoking_package_manager(self):
        with tempfile.TemporaryDirectory() as directory:
            _, log, env = self.make_harness(
                Path(directory),
                missing=("setfacl", "getfacl"),
                os_id="fedora",
            )
            result = self.invoke(env)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("only on Debian/Ubuntu", result.stderr)
            self.assertFalse(log.exists())

    def test_package_install_failure_reports_clear_error(self):
        with tempfile.TemporaryDirectory() as directory:
            _, log, env = self.make_harness(
                Path(directory),
                missing=("setfacl", "getfacl"),
            )
            env["FAIL_ALL_INSTALLS"] = "1"
            result = self.invoke(env)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Could not install required RSFX system package(s): acl", result.stderr)
            self.assertEqual(
                log.read_text(encoding="utf-8").splitlines(),
                [
                    "install -y --no-install-recommends acl",
                    "update",
                    "install -y --no-install-recommends acl",
                ],
            )

    def test_failed_index_refresh_reports_clear_error(self):
        with tempfile.TemporaryDirectory() as directory:
            _, log, env = self.make_harness(
                Path(directory),
                missing=("setfacl", "getfacl"),
            )
            env["FAIL_FIRST_INSTALL"] = "1"
            env["FAIL_UPDATE"] = "1"
            result = self.invoke(env)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("apt-get update failed", result.stderr)
            self.assertEqual(
                log.read_text(encoding="utf-8").splitlines(),
                ["install -y --no-install-recommends acl", "update"],
            )

    def test_missing_command_after_successful_package_install_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            _, log, env = self.make_harness(
                Path(directory),
                missing=("setfacl", "getfacl"),
            )
            env["INSTALL_TOOLS"] = ""
            result = self.invoke(env)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("still unavailable after package installation", result.stderr)
            self.assertEqual(
                log.read_text(encoding="utf-8").splitlines(),
                ["install -y --no-install-recommends acl"],
            )

    def test_dependency_bootstrap_precedes_installation_mutations(self):
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertLess(
            source.index("ensure_permission_dependencies || exit 1"),
            source.index('echo "--- Create backup ---"'),
        )

    def test_runtime_install_requires_hashes_without_upgrading_packaging_tools(self):
        source = INSTALLER.read_text(encoding="utf-8")

        self.assertNotIn("--upgrade pip wheel", source)
        self.assertIn(
            '"$INSTALL_ROOT/venv/bin/python" -m pip install '
            '--disable-pip-version-check --require-hashes '
            '-r "$INSTALL_ROOT/requirements.lock"',
            source,
        )

    def test_every_runtime_lock_entry_has_sha256_hashes(self):
        lock = (REPOSITORY_ROOT / "app/requirements.lock").read_text(encoding="utf-8")
        entries = []
        entry = []
        for line in lock.splitlines():
            if line.strip().startswith("# via"):
                entries.append("\n".join(entry))
                entry = []
            elif line and not line.startswith("#") and not line[0].isspace():
                entry = [line]
            elif entry:
                entry.append(line)

        self.assertTrue(entries)
        for locked_requirement in entries:
            with self.subTest(requirement=locked_requirement.splitlines()[0]):
                self.assertRegex(locked_requirement, r"--hash=sha256:[0-9a-f]{64}")


if __name__ == "__main__":
    unittest.main()
