"""Deterministic, channel-independent artwork selection for Holiday Broadcast.

Stable across process restarts and tune/program triggers, without global mutable
selection state or network requests. Calendar dates use the RSFX host timezone.
"""
from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
from hashlib import sha256
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


ARTWORK = {
    "thanksgiving": ("autumn-leaves", "pumpkin", "acorns", "harvest-wreath"),
    "christmas": ("snowflake", "ornament", "holly", "evergreen"),
    "new-year": ("fireworks", "gold-stars", "confetti", "midnight-clock"),
}
ASSET_DIR = Path(__file__).resolve().parent / "assets" / "holiday"

CALENDAR = {
    "thanksgiving": ("11-01", "11-30"),
    "christmas": ("12-01", "12-25"),
    "new-year": ("12-26", "01-07"),
}


def configured_calendar() -> dict[str, tuple[str, str]]:
    """Optional bounded JSON override with MM-DD inclusive windows."""
    raw = os.environ.get("RSFX_HOLIDAY_CALENDAR", "").strip()
    if not raw:
        return CALENDAR
    if len(raw) > 256:
        raise ValueError("RSFX_HOLIDAY_CALENDAR is too long")
    try:
        source = json.loads(raw)
        if not isinstance(source, dict) or set(source) != set(CALENDAR):
            raise ValueError("calendar requires all three holidays")
        result = {}
        for theme in CALENDAR:
            pair = source[theme]
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError("calendar intervals must contain two dates")
            for part in pair:
                if not isinstance(part, str) or len(part) != 5:
                    raise ValueError("invalid MM-DD date")
                datetime.strptime("2000-" + part, "%Y-%m-%d")
            result[theme] = tuple(pair)
        return result
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError("invalid RSFX_HOLIDAY_CALENDAR configuration") from exc


def _within(month_day: str, start: str, end: str) -> bool:
    return (start <= month_day <= end) if start <= end else (
        month_day >= start or month_day <= end
    )




def host_date(now: datetime | None = None) -> date:
    """Resolve in the explicitly configured timezone, or host local timezone."""
    if now is None:
        now = datetime.now().astimezone()
    timezone = os.environ.get("RSFX_HOLIDAY_TIMEZONE", "").strip()
    if timezone:
        try:
            return now.astimezone(ZoneInfo(timezone)).date()
        except ZoneInfoNotFoundError as exc:
            raise ValueError("invalid RSFX_HOLIDAY_TIMEZONE") from exc
    return now.astimezone().date()


def active_holiday(mode: str = "automatic", today: date | None = None) -> str:
    if mode != "automatic":
        if mode not in ARTWORK:
            raise ValueError("unknown holiday theme")
        return mode
    today = today or host_date()
    month_day = today.strftime("%m-%d")
    for holiday, (start, end) in configured_calendar().items():
        if _within(month_day, start, end):
            return holiday
    return "neutral"


def select_artwork(
    mode: str,
    program_key: str,
    *,
    today: date | None = None,
    previous_program_key: str | None = None,
) -> tuple[str, str | None]:
    theme = active_holiday(mode, today=today)
    if theme == "neutral":
        return theme, None
    # Normalize *missing* identity to the same documented stable fallback.
    key = (program_key or "").strip() or "program-unavailable"
    digest = sha256((theme + "\0" + key).encode("utf-8")).digest()
    choices = ARTWORK[theme]
    position = int.from_bytes(digest[:8], "big") % len(choices)
    if previous_program_key and previous_program_key != key and len(choices) > 1:
        previous = sha256((theme + "\0" + previous_program_key).encode("utf-8")).digest()
        previous_position = int.from_bytes(previous[:8], "big") % len(choices)
        if position == previous_position:
            position = (position + 1) % len(choices)
    return theme, choices[position]


def asset_path(theme: str, asset: str) -> Path:
    """Strict registry lookup, never an arbitrary user-controlled path."""
    if theme not in ARTWORK or asset not in ARTWORK[theme]:
        raise ValueError("unknown bundled holiday artwork")
    return ASSET_DIR / f"{asset}.png"


@lru_cache(maxsize=48)
def loaded_asset(theme: str, asset: str):
    """Decode a bounded, shipped-only RGBA image once per worker."""
    from PIL import Image
    path = asset_path(theme, asset)
    # Explicitly limit the decoder before Pillow sniffs the file header.
    # Filename/extension checks alone cannot prevent JPEG 2000 decoding.
    with Image.open(path, formats=("PNG",)) as source:
        if source.format != "PNG" or source.width > 512 or source.height > 512:
            raise ValueError("unexpected bundled holiday image format or dimensions")
        return source.convert("RGBA").copy()


@lru_cache(maxsize=128)
def scaled_asset(theme: str, asset: str, dimension: int, opacity: int = 255):
    from PIL import Image
    dimension = max(8, min(int(dimension), 256))
    image = loaded_asset(theme, asset)
    result = image.resize((dimension, dimension), Image.Resampling.LANCZOS)
    opacity = max(0, min(int(opacity), 255))
    if opacity < 255:
        result.putalpha(result.getchannel("A").point(lambda value: value * opacity // 255))
    return result
