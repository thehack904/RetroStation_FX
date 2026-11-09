"""Browser contract regression for the Holiday Broadcast editor."""
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
import unittest


STATIC = Path(__file__).resolve().parents[1] / "app" / "rsfx" / "static"


class _Ids(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key == "id":
                self.ids.add(value)


class HolidayFrontendTests(unittest.TestCase):
    def test_holiday_editor_controls_exist_and_are_connected(self):
        parser = _Ids()
        parser.feed((STATIC / "index.html").read_text(encoding="utf-8"))
        self.assertTrue({
            "theme", "holidayControls", "holiday_theme",
            "holiday_artwork_mode", "holiday_decorations",
        }.issubset(parser.ids))
        script = (STATIC / "app.js").read_text(encoding="utf-8")
        for value in (
            "renderHolidayPillowPreview", "holiday_theme:",
            "holiday_decorations:", "/v1/holiday/preview",
            "toggleHolidayControls", "image.onerror",
        ):
            self.assertIn(value, script)

    def test_script_syntax_with_node_when_available(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is not available for optional browser syntax gate")
        subprocess.run(
            [node, "--check", str(STATIC / "app.js")],
            capture_output=True, text=True, check=True,
        )


if __name__ == "__main__":
    unittest.main()
