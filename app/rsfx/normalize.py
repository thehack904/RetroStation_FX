from __future__ import annotations

from .models import NormalizedContext


def _float(v, default):
    try:
        f = float(v)
        return f if f > 0 else default
    except (TypeError, ValueError):
        return default


def _dim(context, key, default):
    for block_name in ("ScaledResolution", "Resolution"):
        block = context.get(block_name) or {}

        try:
            v = int(block.get(key) or 0)

            if v > 0:
                return v
        except (TypeError, ValueError):
            pass

    return default


def _title(show, subtitle):
    show = (show or "").strip()
    subtitle = (subtitle or "").strip()

    if (
        show
        and subtitle
        and show.casefold() != subtitle.casefold()
    ):
        return f"{show} — {subtitle}"

    return subtitle or show


def _timespan_seconds(value):
    """
    Parse ErsatzTV/.NET TimeSpan values such as:

        00:12:53.5743447
        1.02:03:04.500

    Returns None when unavailable.
    """

    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    sign = -1.0

    if text.startswith("-"):
        text = text[1:]
    else:
        sign = 1.0

    try:
        parts = text.split(":")

        if len(parts) != 3:
            return None

        first = parts[0]
        minutes = int(parts[1])
        seconds = float(parts[2])

        days = 0

        if "." in first:
            day_text, hour_text = first.split(".", 1)
            days = int(day_text)
            hours = int(hour_text)
        else:
            hours = int(first)

        total = (
            days * 86400
            + hours * 3600
            + minutes * 60
            + seconds
        )

        return sign * total

    except (TypeError, ValueError):
        return None


def normalize_context(
    channel_id,
    fallback_name,
    context,
):
    fps = _float(
        context.get("FrameRate"),
        0.0,
    )

    if fps <= 0:
        fps = _float(
            context.get("RFrameRate"),
            30.0,
        )

    epg = context.get("Epg") or []

    cur = (
        epg[0]
        if len(epg) > 0 and isinstance(epg[0], dict)
        else {}
    )

    nxt = (
        epg[1]
        if len(epg) > 1 and isinstance(epg[1], dict)
        else {}
    )

    cs = str(
        cur.get("Title")
        or context.get("MediaItem_ShowTitle")
        or ""
    ).strip()

    csub = str(
        cur.get("SubTitle")
        or context.get("MediaItem_Title")
        or ""
    ).strip()

    ns = str(
        nxt.get("Title")
        or ""
    ).strip()

    nsub = str(
        nxt.get("SubTitle")
        or ""
    ).strip()

    media_path = str(
        context.get("MediaItem_Path")
        or ""
    ).strip()

    session_key = str(
        context.get("Channel_StartTime")
        or ""
    ).strip()

    program_start = str(
        cur.get("Start")
        or context.get("MediaItem_Start")
        or ""
    ).strip()

    program_stop = str(
        cur.get("Stop")
        or context.get("MediaItem_Stop")
        or ""
    ).strip()

    program_key = "|".join(
        [
            program_start,
            program_stop,
            cs,
            csub,
            media_path,
        ]
    )

    elapsed = _timespan_seconds(
        context.get("MediaItem_StreamSeek")
    )

    duration = _timespan_seconds(
        context.get("MediaItem_Duration")
    )

    elapsed_percent = None
    remaining_percent = None

    if (
        elapsed is not None
        and duration is not None
        and duration > 0
    ):
        elapsed = max(0.0, elapsed)

        elapsed_percent = max(
            0.0,
            min(
                100.0,
                elapsed / duration * 100.0,
            ),
        )

        remaining_percent = max(
            0.0,
            100.0 - elapsed_percent,
        )

    return NormalizedContext(
        channel_id=channel_id,
        channel_name=fallback_name,
        current_show=cs,
        current_subtitle=csub,
        current_title=_title(cs, csub),
        next_show=ns,
        next_subtitle=nsub,
        next_title=_title(ns, nsub),
        session_key=session_key,
        program_key=program_key,
        media_path=media_path,
        elapsed_seconds=elapsed,
        duration_seconds=duration,
        elapsed_percent=elapsed_percent,
        remaining_percent=remaining_percent,
        width=_dim(
            context,
            "Width",
            640,
        ),
        height=_dim(
            context,
            "Height",
            480,
        ),
        fps=fps,
    )
