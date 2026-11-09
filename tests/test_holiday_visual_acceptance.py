"""Visual-acceptance regressions for Holiday Broadcast redesigned layout.

These tests are intentionally structural and pixel-based, rather than asserting
that automated tests can replace human approval of broadcast artwork.
"""
from __future__ import annotations

from io import BytesIO
import importlib.util
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image, ImageChops

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import rsfx.app as app_module
from rsfx.models import RenderRequest
from rsfx.compositions import get_composition
from rsfx.holiday import ARTWORK
from rsfx.holiday_decor import corner_art, scaled_corner_art
from rsfx.models import Appearance
from rsfx.normalize import normalize_context
from rsfx.renderer import _frame, _region
from rsfx.templates import BUILTIN_TEMPLATES


class HolidayVisualAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.style = next(
            item["style"] for item in BUILTIN_TEMPLATES
            if item["id"] == "holiday-broadcast"
        )

    def test_illustrated_corner_assets_are_original_rgba_and_seasonally_distinct(self):
        signatures = []
        for holiday in ARTWORK:
            with self.subTest(holiday=holiday):
                left = corner_art(holiday, 0, "left")
                right = corner_art(holiday, 0, "right")
                self.assertEqual(left.size, (360, 240))
                self.assertEqual(left.mode, "RGBA")
                self.assertEqual(right.mode, "RGBA")
                self.assertEqual(left.getchannel("A").getextrema()[0], 0)
                self.assertGreater(left.getchannel("A").getextrema()[1], 0)
                self.assertGreater(
                    sum(1 for a in left.getchannel("A").getdata() if a > 150),
                    1200,
                )
                signatures.append(left.tobytes())
        self.assertEqual(len(set(signatures)), 3)

    def test_label_text_and_channel_plaque_have_nonoverlapping_regions(self):
        comp = get_composition("holiday-broadcast")
        bounds = comp["regions"]
        channel, now, upcoming = (bounds[x] for x in ("channel","now","next"))
        self.assertLess(channel["y"] + channel["h"], now["y"])
        self.assertLess(now["y"] + now["h"], upcoming["y"])
        left_art_end = .002 + .224
        right_art_start = 1 - .226
        self.assertGreaterEqual(channel["x"], left_art_end)
        self.assertGreaterEqual(now["x"], left_art_end)
        self.assertGreaterEqual(upcoming["x"], left_art_end)
        self.assertGreaterEqual(now["x"], .34)
        self.assertGreaterEqual(upcoming["x"], .34)
        self.assertLessEqual(now["x"]+now["w"], right_art_start)
        self.assertLessEqual(upcoming["x"]+upcoming["w"], right_art_start)

    def test_complete_seasonal_art_has_transparent_padding_without_fading(self):
        # The artwork must be fully drawn and fitted in its own transparent
        # source canvas. No opacity ramp should be imposed on the outer edge:
        # the user rejected the previous fade as visibly worse than clipping.
        for season in ARTWORK:
            for variant in range(4):
                for side in ("left", "right"):
                    with self.subTest(season=season, variant=variant, side=side):
                        source = corner_art(season, variant, side)
                        self.assertEqual(source.size, (360, 240))
                        alpha = source.getchannel("A")
                        bounds = alpha.getbbox()
                        self.assertIsNotNone(bounds)
                        # All original shapes must fit within source artwork,
                        # with clean transparent margins instead of crop/fade.
                        self.assertGreaterEqual(bounds[0], 5)
                        self.assertGreaterEqual(bounds[1], 5)
                        self.assertLessEqual(bounds[2], source.width - 5)
                        self.assertLessEqual(bounds[3], source.height - 5)
                        image = scaled_corner_art(
                            season, variant, side, 244, 180, 255,
                        )
                        scaled_alpha = image.getchannel("A")
                        self.assertEqual(scaled_alpha.getpixel((0, 90)), 0)
                        self.assertEqual(scaled_alpha.getpixel((243, 90)), 0)
                        self.assertGreater(scaled_alpha.getextrema()[1], 150)
                        # Ordinary sprite scaling should not cap the alpha
                        # throughout any 18% outside strip.
                        self.assertGreaterEqual(scaled_alpha.getextrema()[1], 240)

    def test_scaled_artwork_opacity_is_uniform_not_outer_edge_feathered(self):
        for season in ARTWORK:
            for side in ("left", "right"):
                base = scaled_corner_art(season, 0, side, 244, 180, 255)
                half = scaled_corner_art(season, 0, side, 244, 180, 128)
                full_a = list(base.getchannel("A").getdata())
                half_a = list(half.getchannel("A").getdata())
                self.assertEqual(
                    half_a, [value * 128 // 255 for value in full_a]
                )

    def test_full_renderer_artwork_does_not_clip_to_region_sides(self):
        for season in ARTWORK:
            with self.subTest(season=season):
                context = normalize_context(
                    "101", "Holiday Channel", {
                        "FrameRate": 30,
                        "Resolution": {"Width": 1280, "Height": 720},
                        "Epg": [
                            {"Title": "Planes, Trains and Automobiles"},
                            {"Title": "Son in Law"},
                        ],
                    },
                )
                visible = self.style.model_copy(update={
                    "appearance": self.style.appearance.model_copy(update={
                        "holiday_theme": season,
                        "holiday_decorations": True,
                    })
                })
                plain = self.style.model_copy(update={
                    "appearance": visible.appearance.model_copy(update={
                        "holiday_decorations": False,
                    })
                })
                region = _region(visible, context)
                frames = []
                for style in (visible, plain):
                    raw = _frame(style, context, 1, region, "none", "enter",
                                 (season, ARTWORK[season][0]))
                    frames.append(Image.frombytes(
                        "RGBA", region[2:], raw, "raw", "BGRA"
                    ))
                picture, baseline = frames
                width, height = picture.size
                for edge_x in (0, width - 1):
                    self.assertEqual(
                        picture.getchannel("A").crop(
                            (edge_x, 0, edge_x + 1, height)
                        ).getextrema(), (0, 0),
                    )
                # Decorative art must not bleed into the title-safe center.
                safe_rect = (int(width*.34), int(height*.30),
                             int(width*.765), int(height*.90))
                self.assertIsNone(ImageChops.difference(
                    picture.crop(safe_rect),
                    baseline.crop(safe_rect)
                ).getbbox())

    def test_all_seasons_render_with_visible_corners_and_titles(self):
        for holiday in ARTWORK:
            with self.subTest(holiday=holiday):
                appearance = self.style.appearance.model_copy(
                    update={"holiday_theme": holiday, "holiday_decorations": True}
                )
                style = self.style.model_copy(update={"appearance": appearance})
                context = normalize_context(
                    "", "HOLIDAY VAULT",
                    {
                        "FrameRate": 30,
                        "Resolution": {"Width": 1280, "Height": 720},
                        "Epg": [
                            {"Title": "Planes, Trains and Automobiles",
                             "Start": "2026-11-08T20:00:00"},
                            {"Title": "A Charlie Brown Thanksgiving"},
                        ],
                    },
                )
                region = _region(style, context)
                buf = _frame(style, context, 1, region, "none", "enter",
                             (holiday, ARTWORK[holiday][0]))
                image = Image.frombytes(
                    "RGBA", region[2:], buf, "raw", "BGRA"
                )
                self.assertGreater(image.getchannel("A").getextrema()[1], 0)
                self.assertGreater(
                    image.crop((0, int(region[3]*.40),
                                int(region[2]*.20), region[3]))
                    .getchannel("A").getbbox() is not None, False
                )
                self.assertGreater(
                    image.crop((int(region[2]*.81), int(region[3]*.40),
                                region[2], region[3]))
                    .getchannel("A").getbbox() is not None, False
                )

    def test_decorations_off_does_not_remove_channel_or_text_regions(self):
        base = self.style.appearance.model_copy(update={
            "holiday_theme": "christmas", "holiday_decorations": False
        })
        self.assertEqual(base.theme, "holiday-broadcast")
        self.assertTrue(base.show_now)
        self.assertTrue(base.show_next)
        self.assertTrue(base.show_channel_label)
        context = normalize_context(
            "", "HOLIDAY VAULT",
            {
                "FrameRate": 30,
                "Resolution": {"Width": 1280, "Height": 720},
                "Epg": [
                    {"Title": "A Long Holiday Film Title", "Start": "2026-11-08T20:00:00"},
                    {"Title": "The Next Holiday Feature"},
                ],
            },
        )
        frames = {}
        region = _region(self.style, context)
        for enabled in (False, True):
            appearance = base.model_copy(update={"holiday_decorations": enabled})
            style = self.style.model_copy(update={"appearance": appearance})
            raw = _frame(
                style, context, 1, region, "none", "enter",
                ("christmas", ARTWORK["christmas"][0]),
            )
            frames[enabled] = Image.frombytes(
                "RGBA", region[2:], raw, "raw", "BGRA"
            )

        for name in ("channel", "now", "next"):
            spec = get_composition("holiday-broadcast")["regions"][name]
            box = (
                int(spec["x"] * region[2]),
                int(spec["y"] * region[3]),
                int((spec["x"] + spec["w"]) * region[2]),
                int((spec["y"] + spec["h"]) * region[3]),
            )
            clean_text = frames[False].crop(box)
            self.assertIsNone(
                ImageChops.difference(clean_text, frames[True].crop(box)).getbbox()
            )
            if name == "now":
                colors = clean_text.convert("RGB").getcolors(
                    maxcolors=clean_text.width * clean_text.height
                )
                self.assertTrue(any(color == (255, 247, 229) for _, color in colors))

    def test_holiday_fade_opacity_caps_rendered_alpha(self):
        appearance = self.style.appearance.model_copy(update={
            "holiday_theme": "christmas", "opacity": .3
        })
        style = self.style.model_copy(update={"appearance": appearance})
        context = normalize_context(
            "", "HOLIDAY VAULT",
            {
                "FrameRate": 30,
                "Resolution": {"Width": 1280, "Height": 720},
                "Epg": [{"Title": "Holiday Film"}],
            },
        )
        region = _region(style, context)
        raw = _frame(
            style, context, .5, region, "fade", "enter",
            ("christmas", ARTWORK["christmas"][0]),
        )
        image = Image.frombytes("RGBA", region[2:], raw, "raw", "BGRA")
        self.assertGreater(image.getchannel("A").getextrema()[1], 0)
        self.assertLessEqual(
            image.getchannel("A").getextrema()[1], int(.3 * .5 * 255)
        )

    def test_channel_plaque_occludes_main_panel_top_and_inset_borders(self):
        # A real installed RSFX/VLC screenshot exposed two gold panel strokes
        # crossing the middle of the channel-name plaque. The plaque must be
        # drawn as the foreground layer, not a translucent box behind them.
        for holiday in ("thanksgiving", "christmas", "new-year"):
            with self.subTest(holiday=holiday):
                appearance = self.style.appearance.model_copy(update={
                    "holiday_theme": holiday,
                    "holiday_decorations": False,
                    "show_channel_label": True,
                    "channel_label_text": "Holiday Channel",
                })
                style = self.style.model_copy(update={"appearance": appearance})
                context = normalize_context(
                    "101", "Holiday Channel", {
                        "FrameRate": 30,
                        "Resolution": {"Width": 1280, "Height": 720},
                        "Epg": [{"Title": "Planes, Trains & Automobiles"},
                                {"Title": "Son in Law"}],
                    },
                )
                region = _region(style, context)
                raw = _frame(
                    style, context, 1, region, "none", "enter",
                    (holiday, ARTWORK[holiday][0]),
                )
                image = Image.frombytes(
                    "RGBA", region[2:], raw, "raw", "BGRA"
                )
                width, height = image.size
                # These two rows were crossed by the main frame (20.5%)
                # and its inset (21.8%). Both must look identical to nearby
                # plaque interior at the center, with no gold stroke visible.
                x = int(width * .5)
                reference = image.getpixel((x, int(height * .231)))
                for y_fraction in (.205, .218):
                    self.assertEqual(
                        image.getpixel((x, int(height * y_fraction))),
                        reference,
                        "Main frame must be occluded by foreground plaque",
                    )

    def test_now_next_visibility_removes_corresponding_vertical_divider(self):
        # Installed broadcast playback showed the thin vertical separator
        # remaining when NOW or NEXT was unchecked. Its visibility must match
        # its corresponding badge and title, independently for both rows.
        for holiday in ("thanksgiving", "christmas", "new-year"):
            with self.subTest(holiday=holiday):
                context = normalize_context(
                    "101", "Holiday Channel", {
                        "FrameRate": 30,
                        "Resolution": {"Width": 1280, "Height": 720},
                        "Epg": [
                            {"Title": "Planes, Trains & Automobiles"},
                            {"Title": "Son in Law"},
                        ],
                    },
                )
                frames = {}
                for show_now in (False, True):
                    for show_next in (False, True):
                        appearance = self.style.appearance.model_copy(update={
                            "holiday_theme": holiday,
                            "holiday_decorations": False,
                            "show_now": show_now,
                            "show_next": show_next,
                        })
                        style = self.style.model_copy(update={
                            "appearance": appearance
                        })
                        region = _region(style, context)
                        raw = _frame(
                            style, context, 1, region, "none", "enter",
                            (holiday, ARTWORK[holiday][0]),
                        )
                        frames[(show_now, show_next)] = Image.frombytes(
                            "RGBA", region[2:], raw, "raw", "BGRA"
                        )
                width, height = frames[(True, True)].size
                divider_x = int(width * .325)
                # At these points the only optional visual is the row divider;
                # badges, titles and horizontal separator cannot reach them.
                for row, (y_fraction, enabled, disabled) in {
                    "NOW": (.57, (True, False), (False, False)),
                    "NEXT": (.81, (False, True), (False, False)),
                }.items():
                    with self.subTest(row=row):
                        y = int(height * y_fraction)
                        active = frames[enabled].getpixel((divider_x, y))
                        inactive = frames[disabled].getpixel((divider_x, y))
                        background = frames[disabled].getpixel(
                            (divider_x + max(8, int(width * .015)), y)
                        )
                        self.assertNotEqual(
                            active, inactive,
                            f"{row} divider should exist only while shown",
                        )
                        self.assertEqual(
                            inactive, background,
                            f"{row} divider must leave no line when hidden",
                        )
                # Turning one row off never affects the other row.
                self.assertEqual(
                    frames[(True, False)].getpixel(
                        (divider_x, int(height * .57))
                    ),
                    frames[(True, True)].getpixel(
                        (divider_x, int(height * .57))
                    ),
                )
                self.assertEqual(
                    frames[(False, True)].getpixel(
                        (divider_x, int(height * .81))
                    ),
                    frames[(True, True)].getpixel(
                        (divider_x, int(height * .81))
                    ),
                )

    def test_hide_channel_name_removes_entire_plaque_without_changing_now_next(self):
        base = self.style.appearance.model_copy(update={
            "holiday_theme": "thanksgiving",
            "channel_label_text": "Holiday Channel",
            "holiday_decorations": False,
        })
        context = normalize_context(
            "101", "Holiday Channel",
            {
                "FrameRate": 30,
                "Resolution": {"Width": 1280, "Height": 720},
                "Epg": [
                    {"Title": "A Charlie Brown Thanksgiving"},
                    {"Title": "Planes, Trains & Automobiles"},
                ],
            },
        )
        with_channel = self.style.model_copy(update={
            "appearance": base.model_copy(update={"show_channel_label": True})
        })
        hidden_channel = self.style.model_copy(update={
            "appearance": base.model_copy(update={"show_channel_label": False})
        })
        region = _region(with_channel, context)
        frames = []
        for style in (with_channel, hidden_channel):
            raw = _frame(style, context, 1, region, "none", "enter",
                         ("thanksgiving", ARTWORK["thanksgiving"][0]))
            frames.append(Image.frombytes("RGBA", region[2:], raw, "raw", "BGRA"))
        width, height = frames[0].size
        # Without a channel label, the entire upper plaque region must be
        # transparent (no plaque fill, frame, text or filigree).
        x0, x1 = int(width*.28), int(width*.72)
        y0, y1 = 0, int(height*.19)
        shown_alpha = frames[0].crop((x0, y0, x1, y1)).getchannel("A")
        hidden_alpha = frames[1].crop((x0, y0, x1, y1)).getchannel("A")
        self.assertIsNotNone(shown_alpha.getbbox())
        self.assertIsNone(hidden_alpha.getbbox())
        # The NOW/NEXT body is pixel-identical regardless of plaque toggle.
        body = (0, int(height*.30), width, height)
        self.assertIsNone(ImageChops.difference(
            frames[0].crop(body), frames[1].crop(body)
        ).getbbox())

    def test_live_channel_plaque_never_uses_the_current_program_title(self):
        context = {
            "Epg": [
                {"Title": "A Charlie Brown Thanksgiving"},
                {"Title": "Planes, Trains & Automobiles"},
            ],
            "MediaItem_ShowTitle": "A Charlie Brown Thanksgiving",
        }
        style = SimpleNamespace(
            appearance=Appearance(theme="holiday-broadcast"),
            display_name="Holiday Broadcast",
        )
        request = SimpleNamespace(channel_name="", channel_id="101")
        resolve = app_module._holiday_runtime_channel_name

        # The old code used EPG Title here. That must never happen.
        self.assertEqual(resolve(request, style, context), "Holiday Broadcast")

        # An ambiguous Channel_Title delivered through the adapter is not
        # allowed to replace the actual channel name.
        request.channel_name = "A Charlie Brown Thanksgiving"
        self.assertEqual(resolve(request, style, context), "Holiday Broadcast")

        context["Channel_Name"] = "Holiday Channel"
        self.assertEqual(resolve(request, style, context), "Holiday Channel")

        # Explicit Style label wins, even if Legacy channel metadata is absent.
        style.appearance = Appearance(
            theme="holiday-broadcast", channel_label_text="The Holiday Vault"
        )
        self.assertEqual(resolve(request, style, context), "The Holiday Vault")

    def test_legacy_adapter_rejects_ambiguous_channel_title_alias(self):
        path = (
            Path(__file__).resolve().parents[1] / "app" / "adapter"
            / "rsfx-etv-adapter.py"
        )
        spec = importlib.util.spec_from_file_location("rsfx_etv_adapter_test", path)
        adapter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(adapter)

        context = {
            "Channel_Title": "A Charlie Brown Thanksgiving",
            "MediaItem_Title": "A Charlie Brown Thanksgiving",
            "Epg": [{"Title": "A Charlie Brown Thanksgiving"}],
        }
        self.assertEqual(adapter.channel_name_from_context(context), "")
        context["Channel_Name"] = "Holiday Channel"
        self.assertEqual(
            adapter.channel_name_from_context(context), "Holiday Channel"
        )
        context.pop("Channel_Name")
        context["Channel_Title"] = "Holiday Channel"
        self.assertEqual(
            adapter.channel_name_from_context(context), "Holiday Channel"
        )

    def test_real_packet_endpoint_passes_station_not_movie_to_normalizer(self):
        context = {
            "Channel_StartTime": "session-2026-11-08",
            "Epg": [
                {"Title": "A Charlie Brown Thanksgiving"},
                {"Title": "Planes, Trains & Automobiles"},
            ],
        }
        record = SimpleNamespace(
            id=42,
            display_name="Holiday Broadcast",
            appearance=Appearance(theme="holiday-broadcast"),
        )
        store = Mock()
        store.get_style.return_value = record
        request = RenderRequest(
            style_id=42, channel_id="101",
            channel_name="A Charlie Brown Thanksgiving", context=context
        )
        with (
            patch.object(app_module, "db", store),
            patch.object(app_module, "normalize_context",
                         side_effect=RuntimeError("intentional stop")) as normalized,
        ):
            with self.assertRaises(app_module.HTTPException):
                app_module.render_packet(request)
        self.assertEqual(
            normalized.call_args.args[:2], ("101", "Holiday Broadcast")
        )
        # The program name must remain in the context for NOW rendering.
        self.assertEqual(
            normalized.call_args.args[2]["Epg"][0]["Title"],
            "A Charlie Brown Thanksgiving",
        )

    def test_web_preview_region_matches_server_overlay_height_formula(self):
        script = (
            Path(__file__).resolve().parents[1]
            / "app" / "rsfx" / "static" / "app.js"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "$('theme').value==='holiday-broadcast'?7.25:4.75",
            script,
        )
        self.assertIn(
            "$('theme').value==='holiday-broadcast'?lh-2*my:lh-16",
            script,
        )


if __name__ == "__main__":
    unittest.main()
