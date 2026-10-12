from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


class CIWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.workflow = yaml.load(
            (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"),
            Loader=yaml.BaseLoader,
        )

    def test_read_only_triggers_and_immutable_actions(self):
        self.assertEqual(set(self.workflow["on"]), {"pull_request", "push", "workflow_dispatch"})
        self.assertEqual(self.workflow["permissions"], {"contents": "read"})
        for job in self.workflow["jobs"].values():
            self.assertNotIn("permissions", job)
            for value in job.get("env", {}).values():
                self.assertNotIn("runner.", value)
                self.assertNotIn("secrets.", value)
            for step in job["steps"]:
                self.assertNotIn("continue-on-error", step)
                if "uses" in step:
                    self.assertRegex(step["uses"], r"^actions/(checkout|setup-python|upload-artifact)@[0-9a-f]{40}$")
                if step.get("uses", "").startswith("actions/checkout@"):
                    self.assertEqual(step["with"]["persist-credentials"], "false")

    def test_state_setup_uses_runner_temp_without_touching_checkout(self):
        step = next(step for step in self.workflow["jobs"]["validation"]["steps"]
                    if step.get("name") == "Configure isolated state")
        with tempfile.TemporaryDirectory(prefix="rsfx runner ") as directory:
            root = Path(directory)
            environment_file = root / "github-env"
            subprocess.run(
                ["bash", "-euo", "pipefail", "-c", step["run"]],
                env={**os.environ, "RUNNER_TEMP": str(root), "GITHUB_ENV": str(environment_file)},
                check=True,
            )
            values = dict(line.split("=", 1) for line in environment_file.read_text().splitlines())
            database = Path(values["RSFX_DATABASE"])
            graphics = Path(values["RSFX_ETV_SCRIPT_DIR"])
            self.assertTrue(database.is_relative_to(root))
            self.assertTrue(graphics.is_relative_to(root))
            self.assertTrue(graphics.is_dir())
            self.assertFalse(database.exists())


if __name__ == "__main__":
    unittest.main()
