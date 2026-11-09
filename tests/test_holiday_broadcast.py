"""Holiday Broadcast selection, artwork, compatibility and preview tests."""
from __future__ import annotations

from datetime import date, datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from PIL import Image

APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))

from rsfx.holiday import ARTWORK, active_holiday, asset_path, configured_calendar, loaded_asset, select_artwork
from rsfx.models import Appearance, StylePut
from rsfx.normalize import normalize_context
from rsfx.renderer import _frame, _region, render_packet_stream
from rsfx.templates import BUILTIN_TEMPLATES
from rsfx.app import holiday_preview


class HolidayBroadcastTests(unittest.TestCase):
    def test_calendar_bounds_and_neutral(self):
        expected = {
            (1, 1): "new-year", (1, 7): "new-year", (1, 8): "neutral",
            (10, 31): "neutral", (11, 1): "thanksgiving",
            (11, 30): "thanksgiving", (12, 1): "christmas",
            (12, 25): "christmas", (12, 26): "new-year",
            (12, 31): "new-year",
        }
        for (month, day), holiday in expected.items():
            with self.subTest(month=month, day=day):
                self.assertEqual(
                    active_holiday("automatic", date(2026, month, day)), holiday
                )

    def test_configured_calendar_and_timezone_validation(self):
        override = {
            "thanksgiving": ["10-20", "11-30"],
            "christmas": ["12-01", "12-24"],
            "new-year": ["12-25", "01-10"],
        }
        with patch.dict("os.environ", {"RSFX_HOLIDAY_CALENDAR": json.dumps(override)}):
            self.assertEqual(active_holiday("automatic", date(2026, 10, 22)), "thanksgiving")
            self.assertEqual(active_holiday("automatic", date(2027, 1, 9)), "new-year")
            self.assertEqual(active_holiday("automatic", date(2027, 1, 11)), "neutral")
            self.assertEqual(configured_calendar()["christmas"], ("12-01", "12-24"))
        with patch.dict("os.environ", {"RSFX_HOLIDAY_CALENDAR": "{bad json"}):
            with self.assertRaises(ValueError):
                active_holiday("automatic", date(2026, 11, 20))

    def test_repeat_avoidance_when_previous_program_identity_available(self):
        today = date(2026, 11, 15)
        for n in range(20):
            previous_key = f"prior-{n}"
            current_key = f"now-{n}"
            previous = select_artwork("thanksgiving", previous_key, today=today)[1]
            selected = select_artwork(
                "thanksgiving", current_key, today=today,
                previous_program_key=previous_key,
            )[1]
            self.assertNotEqual(previous, selected)
            self.assertEqual(
                selected,
                select_artwork("thanksgiving", current_key, today=today,
                               previous_program_key=previous_key)[1],
            )

    def test_manual_override_and_validation(self):
        for name in ARTWORK:
            self.assertEqual(active_holiday(name, date(2026, 5, 10)), name)
        with self.assertRaises(ValueError):
            active_holiday("../../etc", date(2026, 5, 10))
        with self.assertRaises(ValueError):
            asset_path("christmas", "../../unsafe")

    def test_selection_is_stable_and_program_dependent(self):
        today = date(2026, 12, 20)
        first = select_artwork("automatic", "program:the-same", today=today)
        for _ in range(40):
            self.assertEqual(select_artwork("automatic", "program:the-same", today=today), first)
        choices = {
            select_artwork("christmas", f"show-{i}", today=today)[1]
            for i in range(32)
        }
        self.assertGreaterEqual(len(choices), 3)
        self.assertEqual(select_artwork("christmas", "", today=today),
                         select_artwork("christmas", " ", today=today))
        self.assertEqual(select_artwork("automatic", "anything", today=date(2026, 7, 1)),
                         ("neutral", None))

    def test_missing_context_identity_uses_stable_fallback(self):
        context = normalize_context("", "Fallback", {})
        self.assertEqual(context.program_key, "")
        self.assertEqual(
            select_artwork("christmas", context.program_key, today=date(2026, 12, 20)),
            select_artwork("christmas", "program-unavailable", today=date(2026, 12, 20)),
        )

    def test_all_twelve_bundled_assets_are_transparent_safe_pngs(self):
        seen = set()
        for theme, assets in ARTWORK.items():
            self.assertEqual(len(assets), 4)
            for asset in assets:
                with self.subTest(theme=theme, asset=asset):
                    path = asset_path(theme, asset)
                    self.assertTrue(path.is_file(), str(path))
                    with Image.open(path) as image:
                        self.assertEqual(image.format, "PNG")
                        self.assertEqual(image.mode, "RGBA")
                        self.assertLessEqual(max(image.size), 512)
                        self.assertEqual(image.getchannel("A").getextrema()[0], 0)
                        self.assertGreater(image.getchannel("A").getextrema()[1], 0)
                    self.assertEqual(loaded_asset(theme, asset).mode, "RGBA")
                    seen.add(asset)
        self.assertEqual(len(seen), 12)

    def test_bundled_artwork_decoder_restricts_formats_to_png(self):
        from rsfx.holiday import loaded_asset
        from unittest.mock import patch
        original_open = Image.open
        seen = []

        def checked_open(*args, **kwargs):
            seen.append(kwargs.get("formats"))
            return original_open(*args, **kwargs)

        loaded_asset.cache_clear()
        with patch("PIL.Image.open", side_effect=checked_open):
            loaded_asset("christmas", ARTWORK["christmas"][0])
        self.assertEqual(seen, [("PNG",)])
        loaded_asset.cache_clear()

    def test_old_nine_template_ids_and_defaults_unchanged(self):
        ids = [item["id"] for item in BUILTIN_TEMPLATES]
        self.assertEqual(ids[:9], [
            "classic-cable", "broadcast-1980s", "cable-1990s",
            "digital-cable-2000s", "retro-local", "saturday-morning",
            "movie-channel", "sports-info", "modern-minimal",
        ])
        self.assertEqual(ids[-1], "holiday-broadcast")
        old = Appearance(theme="classic-cable")
        self.assertTrue(old.holiday_decorations)
        self.assertEqual(old.holiday_theme, "automatic")

    def test_packet_output_and_decorations_toggle(self):
        template = BUILTIN_TEMPLATES[-1]["style"]
        context = normalize_context(
            "", "HOLIDAY VAULT", {
                "FrameRate": 3,
                "Resolution": {"Width": 640, "Height": 480},
                "Epg": [{"Title": "White Christmas", "Start": "show-1"},
                        {"Title": "Miracle on 34th Street"}],
            },
        )
        style = template.model_copy(update={
            "appearance": template.appearance.model_copy(update={
                "holiday_theme": "christmas", "holiday_decorations": True,
                "entrance_animation_style": "none",
                "exit_animation_style": "none",
            }),
            "overlay_display_seconds": 1,
        })
        raw, stats = render_packet_stream(style, context)
        self.assertGreater(stats.packet_bytes, stats.region[2] * stats.region[3] * 4)
        self.assertEqual(len(raw), stats.packet_bytes)
        region = _region(style, context)
        one = _frame(style, context, 1, region, "none", "enter", ("christmas", "holly"))
        clean = style.model_copy(update={
            "appearance": style.appearance.model_copy(update={"holiday_decorations": False})
        })
        two = _frame(clean, context, 1, region, "none", "enter", ("christmas", "holly"))
        self.assertNotEqual(one, two)
        self.assertEqual(len(one), region[2] * region[3] * 4)

    def test_preview_returns_true_renderer_png_without_yaml_side_effect(self):
        style = BUILTIN_TEMPLATES[-1]["style"]
        with patch("rsfx.app.sync_yaml", side_effect=AssertionError("unexpected sync")):
            response = holiday_preview(style, width=640, height=480)
        with Image.open(BytesIO(response.body)) as image:
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.mode, "RGBA")
            self.assertGreater(image.getchannel("A").getextrema()[1], 0)


if __name__ == "__main__":
    unittest.main()
