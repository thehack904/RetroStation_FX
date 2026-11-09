#!/usr/bin/env python3
"""Render exact Pillow holiday lower-thirds as PNGs for visual acceptance.

No RSFX database, installed service, ErsatzTV API, YAML changes or network.
Usage: python3 app/tools/render_holiday_previews.py --output /tmp/rsfx-holiday-previews
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from PIL import Image

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from rsfx.normalize import normalize_context
from rsfx.renderer import _frame, _region
from rsfx.templates import BUILTIN_TEMPLATES
from rsfx.holiday import ARTWORK


SAMPLES = {
    "thanksgiving": ("Planes, Trains and Automobiles",
                     "A Charlie Brown Thanksgiving"),
    "christmas": ("White Christmas", "Miracle on 34th Street"),
    "new-year": ("When Harry Met Sally", "The Apartment"),
}
RESOLUTIONS = ((640, 480), (1280, 720), (1920, 1080))


def generate(directory: Path, resolutions=RESOLUTIONS):
    directory.mkdir(parents=True, exist_ok=True)
    source = next(
        item["style"] for item in BUILTIN_TEMPLATES
        if item["id"] == "holiday-broadcast"
    )
    paths = []
    for width, height in resolutions:
        for holiday, (current, upcoming) in SAMPLES.items():
            style = source.model_copy(update={
                "appearance": source.appearance.model_copy(update={
                    "holiday_theme": holiday,
                    "holiday_decorations": True,
                    "channel_label_text": "HOLIDAY VAULT",
                })
            })
            normalized = normalize_context(
                "", "HOLIDAY VAULT", {
                    "FrameRate": 30,
                    "Resolution": {"Width": width, "Height": height},
                    "Epg": [
                        {"Title": current, "Start": "2026-11-08T20:00:00"},
                        {"Title": upcoming},
                    ],
                }
            )
            region = _region(style, normalized)
            _, _, rw, rh = region
            # Stable selected identity and a real renderer frame, not a mockup.
            choice = (holiday, ARTWORK[holiday][0])
            raw = _frame(style, normalized, 1.0, region,
                         "none", "enter", choice)
            image = Image.frombytes("RGBA", (rw, rh), raw, "raw", "BGRA")
            background = Image.new("RGBA", (width, height), (13, 20, 33, 255))
            background.alpha_composite(image, region[:2])
            path = directory / f"{holiday}-{width}x{height}.png"
            background.convert("RGB").save(path, format="PNG")
            paths.append(path)
    return paths


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="Directory to receive nine exact Pillow frame previews")
    args = parser.parse_args()
    for path in generate(args.output):
        print(path)
