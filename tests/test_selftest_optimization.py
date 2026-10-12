from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELFTEST = ROOT / "app" / "tools" / "selftest.py"


class SelftestOptimizationTests(unittest.TestCase):
    def test_selftest_does_not_depend_on_assert_statement(self):
        source = SELFTEST.read_text(encoding="utf-8")
        tree = __import__("ast").parse(source)
        self.assertFalse(
            any(isinstance(node, __import__("ast").Assert) for node in __import__("ast").walk(tree))
        )

    def test_selftest_source_compiles_in_optimized_mode(self):
        result = subprocess.run(
            [sys.executable, "-O", "-m", "py_compile", str(SELFTEST)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
