from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPOSITORY_ROOT / "retrostation_fx_linux.sh"


class InstallerManagementTests(unittest.TestCase):
    def test_management_bind_selection(self):
        source = INSTALLER.read_text(encoding="utf-8")
        start = source.index("detect_lan_ipv4() {")
        end = source.index("\nsafe_rm_tree() {", start)
        function = source[start:end]

        with tempfile.TemporaryDirectory() as directory:
            result_path = Path(directory) / "selected-bind"
            ip_path = Path(directory) / "ip"
            ip_path.write_text(
                "#!/bin/sh\n"
                '[ -n "$MOCK_IP_FAIL" ] && exit 1\n'
                'case "$*" in\n'
                "  '-4 route get 1.1.1.1') "
                "echo '1.1.1.1 via 192.0.2.1 dev eth0 src 192.0.2.44 uid 0';;\n"
                "  '-o -4 addr show scope global') "
                "echo '2: eth0 inet 192.0.2.44/24 scope global eth0';;\n"
                "esac\n",
                encoding="utf-8",
            )
            ip_path.chmod(0o755)
            script = (
                'set_env_value() { printf "%s\\n" "$2" > "$RESULT_PATH"; }\n'
                + function
                + '\nif [ "$LOCAL_ONLY" -eq 1 ]; then detected=""; '
                + 'else detected="$(detect_lan_ipv4)"; fi\n'
                + 'choose_management_bind "$detected" "$PORT" "$LOCAL_ONLY"\n'
            )
            env = os.environ.copy()
            env.update(
                RESULT_PATH=str(result_path),
                PORT="6060",
                LOCAL_ONLY="0",
                PATH=f"{directory}{os.pathsep}{os.environ['PATH']}",
            )
            result = subprocess.run(
                ["bash", "-c", script],
                text=True,
                capture_output=True,
                env=env,
                check=True,
            )
            self.assertEqual(result_path.read_text(encoding="utf-8").strip(), "192.0.2.44")
            self.assertIn("Detected RSFX management address: 192.0.2.44", result.stdout)
            self.assertIn("http://192.0.2.44:6060/", result.stdout)
            self.assertIn("management API is unauthenticated", result.stdout)
            self.assertNotIn("Use this Trusted LAN address?", result.stdout)

            help_output = subprocess.run(
                ["bash", str(INSTALLER), "--help"],
                text=True,
                capture_output=True,
                check=True,
            ).stdout
            self.assertIn("install --local-only", help_output)

            env["LOCAL_ONLY"] = "1"
            local = subprocess.run(
                ["bash", "-c", script],
                text=True,
                capture_output=True,
                env=env,
                check=True,
            )
            self.assertEqual(result_path.read_text(encoding="utf-8").strip(), "127.0.0.1")
            self.assertIn("not directly reachable from another LAN machine", local.stdout)
            self.assertIn("ssh -L 6060:127.0.0.1:6060", local.stdout)

            env["MOCK_IP_FAIL"] = "1"
            env["LOCAL_ONLY"] = "0"
            failed = subprocess.run(
                ["bash", "-c", script],
                text=True,
                capture_output=True,
                env=env,
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("No active LAN IPv4 address was detected", failed.stdout)


if __name__ == "__main__":
    unittest.main()
