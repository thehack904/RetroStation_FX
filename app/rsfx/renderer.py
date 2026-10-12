from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from .packet import full_packet, repeat_packet, clear_packet
from .compositions import get_composition


@dataclass
class RenderStats:
    frames: int
    packet_bytes: int
    region: tuple[int, int, int, int]


def _font(size, bold=False):
    choices = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]

    for path in choices:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            pass

    return ImageFont.load_default()


def _rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def _text_width(draw, text, font):
    box = draw.textbbox((0, 0), text or "", font=font)
    return box[2] - box[0]


def _line_height(draw, font):
    box = draw.textbbox((0, 0), "Ag", font=font)
    return max(1, box[3] - box[1])


def _truncate(draw, text, font, maxw):
    """
    Single-line ellipsis fallback.
    """

    text = text or ""

    if _text_width(draw, text, font) <= maxw:
        return text

    ellipsis = "…"

    while text:
        text = text[:-1]
        candidate = text.rstrip() + ellipsis

        if _text_width(draw, candidate, font) <= maxw:
            return candidate

    return ellipsis


def _wrap_words(draw, text, font, maxw):
    """
    Greedy word wrapping.

    Returns every required line; the caller decides whether the number
    of lines is acceptable.
    """

    words = (text or "").split()

    if not words:
        return [""]

    lines = []
    current = ""

    for word in words:
        candidate = word if not current else f"{current} {word}"

        if _text_width(draw, candidate, font) <= maxw:
            current = candidate
            continue

        if current:
            lines.append(current)
            current = ""

        # A single word may itself be wider than the available region.
        if _text_width(draw, word, font) <= maxw:
            current = word
            continue

        # Split an unusually long word into fitting pieces.
        piece = ""

        for char in word:
            test = piece + char

            if piece and _text_width(draw, test, font) > maxw:
                lines.append(piece)
                piece = char
            else:
                piece = test

        current = piece

    if current:
        lines.append(current)

    return lines


def _wrapped_text_height(draw, font, line_count):
    """
    Return the vertical space consumed by rendered wrapped text.

    Keep this calculation synchronized with the line spacing used
    when NOW text is actually drawn.
    """

    if line_count <= 0:
        return 0

    line_h = _line_height(draw, font)
    gap = max(2, int(line_h * 0.12))

    return (
        line_count * line_h
        + max(0, line_count - 1) * gap
    )


def _truncate_wrapped_lines(
    draw,
    lines,
    font,
    maxw,
    max_lines,
):
    """
    Reduce an already wrapped value to max_lines while preserving as
    much text as possible in the final visible line.
    """

    if len(lines) <= max_lines:
        return lines

    visible = lines[:max_lines]
    remaining = " ".join(
        lines[max_lines - 1 :]
    )

    if max_lines == 1:
        visible[0] = _truncate(
            draw,
            remaining,
            font,
            maxw,
        )
    else:
        visible[-1] = _truncate(
            draw,
            remaining,
            font,
            maxw,
        )

    return visible


def _fit_wrapped_text(
    draw,
    text,
    maxw,
    max_lines,
    preferred_size,
    minimum_size,
    bold=False,
    max_height=None,
):
    """
    Fit text using this priority:

      1. wrap to max_lines;
      2. progressively reduce font size;
      3. honor the text region's vertical height when supplied;
      4. ellipsize only when the configured minimum size cannot
         contain the complete wrapped value;
      5. as a final safety measure, reduce below the preferred
         minimum only when necessary to prevent text escaping its
         assigned region.

    Returns (font, lines).
    """

    preferred_size = max(
        1,
        int(preferred_size),
    )

    minimum_size = max(
        1,
        min(
            int(minimum_size),
            preferred_size,
        ),
    )

    def height_fits(font, lines):
        if max_height is None:
            return True

        return (
            _wrapped_text_height(
                draw,
                font,
                len(lines),
            )
            <= max_height
        )

    #
    # Preserve the existing behavior first: prefer wrapping and
    # shrinking over truncation.
    #
    for size in range(
        preferred_size,
        minimum_size - 1,
        -1,
    ):
        font = _font(
            size,
            bold,
        )

        lines = _wrap_words(
            draw,
            text,
            font,
            maxw,
        )

        if (
            len(lines) <= max_lines
            and height_fits(
                font,
                lines,
            )
        ):
            return (
                font,
                lines,
            )

    #
    # At the configured minimum, preserve as much text as possible
    # and ellipsize the final visible line if necessary.
    #
    font = _font(
        minimum_size,
        bold,
    )

    lines = _wrap_words(
        draw,
        text,
        font,
        maxw,
    )

    visible = _truncate_wrapped_lines(
        draw,
        lines,
        font,
        maxw,
        max_lines,
    )

    if height_fits(
        font,
        visible,
    ):
        return (
            font,
            visible,
        )

    #
    # The old renderer had no vertical constraint. At small output
    # resolutions a two-line value could therefore spill into the
    # NEXT region even though it fit horizontally.
    #
    # Going below minimum_size is intentionally a last-resort safety
    # path. It is preferable to slightly smaller text rather than
    # allowing text to escape its declared composition region.
    #
    hard_floor = 8

    for size in range(
        minimum_size - 1,
        hard_floor - 1,
        -1,
    ):
        font = _font(
            size,
            bold,
        )

        lines = _wrap_words(
            draw,
            text,
            font,
            maxw,
        )

        visible = _truncate_wrapped_lines(
            draw,
            lines,
            font,
            maxw,
            max_lines,
        )

        if height_fits(
            font,
            visible,
        ):
            return (
                font,
                visible,
            )

    #
    # Defensive fallback. With current RSFX composition geometry this
    # should never be reached, but return a bounded value rather than
    # reverting to unbounded text.
    #
    font = _font(
        hard_floor,
        bold,
    )

    lines = _wrap_words(
        draw,
        text,
        font,
        maxw,
    )

    visible = _truncate_wrapped_lines(
        draw,
        lines,
        font,
        maxw,
        max_lines,
    )

    return (
        font,
        visible,
    )


def _region(ch, n):
    w = min(
        max(220, int(n.width * ch.appearance.width_percent / 100)),
        max(220, n.width - 16),
    )

    # Keep the overlay large enough for whichever enabled text
    # element requests the largest preferred size.
    largest_text = max(
        ch.appearance.channel_font_size,
        ch.appearance.now_font_size,
        ch.appearance.next_font_size,
    )

    preferred_h = int(
        largest_text * 4.75
    )

    mx = max(8, int(n.width * 0.035))
    my = max(8, int(n.height * 0.055))

    h = min(
        n.height - 2 * my,
        max(118, preferred_h),
    )

    pos = ch.appearance.position

    if pos.endswith("left"):
        x = mx
    elif pos.endswith("right"):
        x = n.width - w - mx
    else:
        x = (n.width - w) // 2

    if pos.startswith("top"):
        y = my
    else:
        y = n.height - h - my

    return max(0, x), max(0, y), w, h


def _palette(accent, background_alpha, foreground_alpha, muted_alpha):
    return {
        "panel": (10, 12, 18, background_alpha),
        "navy": (18, 26, 58, background_alpha),
        "purple": (46, 36, 82, background_alpha),
        "glass": (12, 34, 58, background_alpha),
        "cream": (238, 235, 220, background_alpha),
        "black": (5, 5, 7, background_alpha),
        "dark": (14, 18, 24, background_alpha),
        "charcoal": (14, 16, 20, background_alpha),
        "accent": (*accent, foreground_alpha),
        "accent_soft": (*accent, int(foreground_alpha * 0.34)),
        "hot": (255, 93, 108, foreground_alpha),
        "light": (245, 247, 250, foreground_alpha),
        "muted": (210, 214, 222, muted_alpha),
        "ink": (35, 35, 35, foreground_alpha),
        "ink_muted": (75, 75, 75, muted_alpha),
    }


def _box(spec, w, h):
    return (
        int(spec.get("x", 0) * w),
        int(spec.get("y", 0) * h),
        max(1, int(spec.get("w", 1) * w)),
        max(1, int(spec.get("h", 1) * h)),
    )


def _draw_composition(draw, w, h, composition, palette):
    for panel in composition.get("panels", []):
        kind = panel.get("kind", "rect")
        fill = palette.get(panel.get("fill"), palette["panel"])

        if kind == "polygon":
            points = [
                (int(px * w), int(py * h))
                for px, py in panel.get("points", [])
            ]
            if points:
                draw.polygon(points, fill=fill)
            continue

        x, y, pw, ph = _box(panel, w, h)
        xy = (x, y, x + pw - 1, y + ph - 1)

        if kind == "ellipse":
            draw.ellipse(xy, fill=fill)
        elif kind == "round_rect":
            radius = max(0, int(min(pw, ph) * panel.get("radius", 0.08)))
            draw.rounded_rectangle(xy, radius=radius, fill=fill)
        else:
            draw.rectangle(xy, fill=fill)


def _text_x(draw, text, font, x, width, align):
    if align == "center":
        return x + max(0, (width - _text_width(draw, text, font)) // 2)
    if align == "right":
        return x + max(0, width - _text_width(draw, text, font))
    return x


def _frame(
    ch,
    n,
    progress,
    region,
    style,
    phase,
):
    _, _, w, h = region

    accent = _rgb(ch.appearance.accent)
    alpha = ch.appearance.opacity

    progress = max(
        0.0,
        min(1.0, float(progress)),
    )

    lx = 0
    ly = 0

    if phase == "enter":
        if style == "fade":
            alpha *= progress

        elif style == "slide-left":
            lx = int(
                (1.0 - progress)
                * -w
            )

        elif style == "slide-right":
            lx = int((1.0 - progress) * w)

        elif style == "slide-up":
            ly = int((1.0 - progress) * h)

        elif style == "slide-down":
            ly = int((1.0 - progress) * -h)

    elif phase == "exit":
        if style == "fade":
            alpha *= (
                1.0 - progress
            )

        elif style == "slide-left":
            lx = int(
                progress
                * -w
            )

        elif style == "slide-right":
            lx = int(progress * w)

        elif style == "slide-up":
            ly = int(progress * -h)

        elif style == "slide-down":
            ly = int(progress * h)

    im = Image.new(
        "RGBA",
        (w, h),
        (0, 0, 0, 0),
    )

    draw = ImageDraw.Draw(im)

    background_alpha = int(
        220 * alpha
    )

    foreground_alpha = int(
        255 * alpha
    )

    muted_alpha = int(
        215 * alpha
    )

    composition = get_composition(ch.appearance.theme)
    palette = _palette(accent, background_alpha, foreground_alpha, muted_alpha)
    _draw_composition(draw, w, h, composition, palette)

    regions = composition.get("regions", {})

    if (
        ch.appearance.show_channel_label
        and "channel" in regions
    ):
        spec = regions["channel"]

        x, y, rw, rh = _box(
            spec,
            w,
            h,
        )

        channel_preferred = int(
            ch.appearance.channel_font_size
        )

        channel_minimum = max(
            8,
            int(
                channel_preferred
                * 0.70
            ),
        )

        channel_label = (
            ch.appearance.channel_label_text
            or n.channel_name
        )

        label_font, label_lines = _fit_wrapped_text(
            draw=draw,
            text=channel_label,
            maxw=rw,
            max_lines=1,
            preferred_size=channel_preferred,
            minimum_size=channel_minimum,
            bold=True,
            max_height=rh,
        )

        label = label_lines[0]

        tx = _text_x(
            draw,
            label,
            label_font,
            x,
            rw,
            spec.get(
                "align",
                "left",
            ),
        )

        ty = y + max(
            0,
            (
                rh
                - _line_height(
                    draw,
                    label_font,
                )
            )
            // 2,
        )

        draw.text(
            (tx, ty),
            label,
            font=label_font,
            fill=palette.get(
                spec.get("color"),
                palette["accent"],
            ),
        )

    if (
        ch.appearance.show_now
        and "now" in regions
    ):
        spec = regions["now"]

        x, y, rw, rh = _box(
            spec,
            w,
            h,
        )

        now_preferred = int(
            ch.appearance.now_font_size
        )

        now_minimum = max(
            8,
            int(
                now_preferred
                * 0.60
            ),
        )

        now_text = (
            "NOW  "
            + (
                n.current_title
                or "Programming"
            )
        )

        now_font, now_lines = _fit_wrapped_text(
            draw=draw,
            text=now_text,
            maxw=rw,
            max_lines=2,
            preferred_size=now_preferred,
            minimum_size=now_minimum,
            bold=True,
            max_height=rh,
        )

        line_h = _line_height(
            draw,
            now_font,
        )

        gap = max(
            2,
            int(
                line_h
                * 0.12
            ),
        )

        total_h = (
            len(now_lines)
            * line_h
            + max(
                0,
                len(now_lines) - 1,
            )
            * gap
        )

        ty = y + max(
            0,
            (
                rh
                - total_h
            )
            // 2,
        )

        for line in now_lines:
            tx = _text_x(
                draw,
                line,
                now_font,
                x,
                rw,
                spec.get(
                    "align",
                    "left",
                ),
            )

            draw.text(
                (tx, ty),
                line,
                font=now_font,
                fill=palette.get(
                    spec.get("color"),
                    palette["light"],
                ),
            )

            ty += (
                line_h
                + gap
            )

    if (
        ch.appearance.show_next
        and "next" in regions
    ):
        spec = regions["next"]

        x, y, rw, rh = _box(
            spec,
            w,
            h,
        )

        next_preferred = int(
            ch.appearance.next_font_size
        )

        next_minimum = max(
            8,
            int(
                next_preferred
                * 0.65
            ),
        )

        next_text = (
            "NEXT  "
            + (
                n.next_title
                or "To Be Announced"
            )
        )

        next_font, next_lines = _fit_wrapped_text(
            draw=draw,
            text=next_text,
            maxw=rw,
            max_lines=1,
            preferred_size=next_preferred,
            minimum_size=next_minimum,
            bold=False,
            max_height=rh,
        )

        line = next_lines[0]

        tx = _text_x(
            draw,
            line,
            next_font,
            x,
            rw,
            spec.get(
                "align",
                "left",
            ),
        )

        ty = y + max(
            0,
            (
                rh
                - _line_height(
                    draw,
                    next_font,
                )
            )
            // 2,
        )

        draw.text(
            (tx, ty),
            line,
            font=next_font,
            fill=palette.get(
                spec.get("color"),
                palette["muted"],
            ),
        )

    if lx or ly:
        canvas = Image.new(
            "RGBA",
            (w, h),
            (0, 0, 0, 0),
        )

        canvas.alpha_composite(
            im,
            (lx, ly),
        )

        im = canvas

    return im.tobytes(
        "raw",
        "BGRA",
    )

def render_packet_stream(ch, n):
    region = _region(ch, n)
    x, y, w, h = region

    fps = max(
        1.0,
        min(
            120.0,
            n.fps,
        ),
    )

    total = max(
        1,
        int(
            round(
                ch.overlay_display_seconds
                * fps
            )
        ),
    )

    enter_style = (
        ch.appearance
        .entrance_animation_style
    )

    exit_style = (
        ch.appearance
        .exit_animation_style
    )

    requested_enter = (
        0
        if (
            enter_style == "none"
            or ch.appearance
            .entrance_duration_seconds
            <= 0
        )
        else max(
            1,
            int(
                round(
                    ch.appearance
                    .entrance_duration_seconds
                    * fps
                )
            ),
        )
    )

    requested_exit = (
        0
        if (
            exit_style == "none"
            or ch.appearance
            .exit_duration_seconds
            <= 0
        )
        else max(
            1,
            int(
                round(
                    ch.appearance
                    .exit_duration_seconds
                    * fps
                )
            ),
        )
    )

    enter = requested_enter
    exit_frames = requested_exit

    #
    # If requested transition time exceeds the total display
    # lifetime, scale both phases proportionally so neither phase
    # silently consumes the other.
    #
    transition_total = (
        enter
        + exit_frames
    )

    if (
        transition_total > total
        and transition_total > 0
    ):
        scale = (
            total
            / transition_total
        )

        enter = (
            max(
                1,
                int(
                    round(
                        enter
                        * scale
                    )
                ),
            )
            if enter
            else 0
        )

        exit_frames = (
            max(
                1,
                total - enter,
            )
            if exit_frames
            else 0
        )

        if (
            enter
            + exit_frames
            > total
        ):
            if exit_frames > 0:
                exit_frames = max(
                    0,
                    total - enter,
                )

    hold = max(
        0,
        total
        - enter
        - exit_frames,
    )

    chunks = []

    #
    # Entrance.
    #
    if enter > 0:
        for i in range(enter):
            progress = (
                (i + 1)
                / enter
            )

            progress = (
                progress
                * progress
                * (
                    3
                    - 2 * progress
                )
            )

            chunks.append(
                full_packet(
                    x,
                    y,
                    w,
                    h,
                    _frame(
                        ch,
                        n,
                        progress,
                        region,
                        enter_style,
                        "enter",
                    ),
                )
            )

    else:
        chunks.append(
            full_packet(
                x,
                y,
                w,
                h,
                _frame(
                    ch,
                    n,
                    1.0,
                    region,
                    "none",
                    "enter",
                ),
            )
        )

        #
        # The static frame already consumes one frame of lifetime.
        #
        if hold > 0:
            hold -= 1

    #
    # Hold.
    #
    if hold > 0:
        chunks.append(
            repeat_packet(
                hold
            )
        )

    #
    # Exit.
    #
    if exit_frames > 0:
        for i in range(exit_frames):
            progress = (
                (i + 1)
                / exit_frames
            )

            progress = (
                progress
                * progress
                * (
                    3
                    - 2 * progress
                )
            )

            chunks.append(
                full_packet(
                    x,
                    y,
                    w,
                    h,
                    _frame(
                        ch,
                        n,
                        progress,
                        region,
                        exit_style,
                        "exit",
                    ),
                )
            )

    chunks.append(
        clear_packet()
    )

    payload = b"".join(
        chunks
    )

    return payload, RenderStats(
        total,
        len(payload),
        region,
    )

def render_boundary_packet_stream(ch, n, reason):
    """
    Render an immediate boundary overlay.

    Tune/start overlays may begin with a transparent Packet-v1 delay.
    This allows ErsatzTV/HLS/client startup to stabilize before the
    visible graphics begin.

    Program-change overlays remain immediate.
    """

    import math

    payload, stats = render_packet_stream(
        ch,
        n,
    )

    if reason != "channel-tune":
        return (
            payload,
            stats,
            0,
        )

    delay_seconds = max(
        0.0,
        min(
            30.0,
            float(
                ch.trigger_policy
                .tune_delay_seconds
            ),
        ),
    )

    if delay_seconds <= 0:
        return (
            payload,
            stats,
            0,
        )

    fps = max(
        1.0,
        min(
            120.0,
            n.fps,
        ),
    )

    delay_frames = max(
        1,
        int(
            math.ceil(
                delay_seconds
                * fps
            )
        ),
    )

    #
    # Start on a transparent canvas, then Repeat it until the
    # configured tune delay expires.
    #
    prefix = clear_packet()

    if delay_frames > 1:
        prefix += repeat_packet(
            delay_frames - 1
        )

    delayed_payload = (
        prefix
        + payload
    )

    delayed_stats = RenderStats(
        frames=(
            stats.frames
            + delay_frames
        ),
        packet_bytes=
            len(delayed_payload),
        region=
            stats.region,
    )

    return (
        delayed_payload,
        delayed_stats,
        delay_frames,
    )

