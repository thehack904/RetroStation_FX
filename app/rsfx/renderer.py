from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from .packet import full_packet, repeat_packet, clear_packet
from .compositions import get_composition
from .holiday import host_date, select_artwork, scaled_asset, ARTWORK
from .holiday_decor import scaled_corner_art


@dataclass
class RenderStats:
    frames: int
    packet_bytes: int
    region: tuple[int, int, int, int]


def _font(size, bold=False, serif=False):
    if serif:
        choices = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
            if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf"
            if bold else "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf",
        ]
    else:
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
    serif=False,
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
        font = _font(size, bold, serif)

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
    font = _font(minimum_size, bold, serif)

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
        font = _font(size, bold, serif)

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
    font = _font(hard_floor, bold, serif)

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
        largest_text * (7.25 if ch.appearance.theme == "holiday-broadcast" else 4.75)
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
    holiday_choice=None,
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
    if ch.appearance.theme == "holiday-broadcast":
        if holiday_choice is None:
            holiday_choice = select_artwork(ch.appearance.holiday_theme, n.program_key)
        holiday_theme, _holiday_asset = holiday_choice
        holiday_colors = {
            "thanksgiving": ((60, 29, 18), (247, 172, 83)),
            "christmas": ((10, 40, 30), (227, 188, 103)),
            "new-year": ((14, 24, 48), (239, 201, 120)),
            "neutral": ((27, 31, 42), (200, 204, 213)),
        }
        panel_color, gold_color = holiday_colors[holiday_theme]
        palette["dark"] = (*panel_color, background_alpha)
        palette["navy"] = (*panel_color, background_alpha)
        palette["accent"] = (*gold_color, foreground_alpha)
        palette["accent_soft"] = (*gold_color, int(foreground_alpha * 0.65))
        palette["light"] = (255, 247, 229, foreground_alpha)
        palette["muted"] = (234, 219, 192, muted_alpha)
    if (
        ch.appearance.theme == "holiday-broadcast"
        and not ch.appearance.show_channel_label
    ):
        # The plaque is a real structural element, not merely text.
        # Remove its fill as well as its frame and embellishments when hidden.
        panels = composition.get("panels", [])
        composition = {
            **composition,
            "panels": [
                panel for index, panel in enumerate(panels)
                if index != 1
            ],
        }
    _draw_composition(draw, w, h, composition, palette)
    if ch.appearance.theme == "holiday-broadcast":
        # Premium broadcast frame. The central NOW/NEXT columns are isolated
        # from ornaments and labels by the declarative text-safe regions.
        edge = palette["accent"]
        soft = palette["accent_soft"]
        draw.rounded_rectangle(
            (int(w*.054), int(h*.20), int(w*.946), int(h*.934)),
            radius=max(7, int(h*.048)), outline=edge,
            width=max(2, int(h*.009)),
        )
        # Pinstripes and hairlines are confined to the information panel.
        draw.line(
            (int(w*.240), int(h*.646), int(w*.810), int(h*.646)),
            fill=soft, width=max(1, int(h*.005)),
        )
        if ch.appearance.show_now:
            draw.line(
                (int(w*.325), int(h*.338), int(w*.325), int(h*.602)),
                fill=soft, width=max(1, int(h*.005)),
            )
        if ch.appearance.show_next:
            draw.line(
                (int(w*.325), int(h*.686), int(w*.325), int(h*.826)),
                fill=soft, width=max(1, int(h*.005)),
            )
        # Gold inset and channel plaque filigree echo the approved mockups.
        draw.rounded_rectangle(
            (int(w*.065), int(h*.218), int(w*.935), int(h*.919)),
            radius=max(5,int(h*.038)), outline=soft,
            width=max(1,int(h*.004)),
        )
        # The channel plaque is the foreground layer. Draw its *fill* after
        # both main-panel border strokes so those strokes cannot show through
        # its translucent interior. ImageDraw writes RGBA pixels directly here,
        # rather than alpha-compositing the old border into the plaque.
        if ch.appearance.show_channel_label:
            draw.rounded_rectangle(
                (int(w*.288), int(h*.022), int(w*.712), int(h*.251)),
                radius=max(5, int(h*.045)),
                fill=palette["navy"],
                outline=edge,
                width=max(2, int(h*.009)),
            )
        if ch.appearance.show_channel_label:
            for cx in (int(w*.311), int(w*.689)):
                cy = int(h*.135)
                rr = max(4, int(h*.024))
                draw.polygon(
                    [(cx,cy-rr),(cx+rr*.3,cy-rr*.3),(cx+rr,cy),
                     (cx+rr*.3,cy+rr*.3),(cx,cy+rr),
                     (cx-rr*.3,cy+rr*.3),(cx-rr,cy),
                     (cx-rr*.3,cy-rr*.3)],
                    fill=edge,
                )
        if ch.appearance.show_now:
            draw.rounded_rectangle(
                (int(w*.227),int(h*.374),int(w*.322),int(h*.540)),
                radius=max(3,int(h*.021)), outline=edge,
                fill=(*panel_color,background_alpha),
                width=max(1,int(h*.007)),
            )
        if ch.appearance.show_next:
            draw.rounded_rectangle(
                (int(w*.227),int(h*.691),int(w*.322),int(h*.844)),
                radius=max(3,int(h*.021)), outline=edge,
                fill=(*panel_color,background_alpha),
                width=max(1,int(h*.007)),
            )
        if ch.appearance.show_now:
            draw.text(
                (int(w*.242), int(h*.402)), "NOW",
                font=_font(max(13, int(h*.099)), True), fill=edge,
            )
        if ch.appearance.show_next:
            draw.text(
                (int(w*.242), int(h*.722)), "NEXT",
                font=_font(max(12, int(h*.086)), True), fill=edge,
            )
        if ch.appearance.holiday_decorations:
            season, asset_id = holiday_choice
            if asset_id is not None:
                art_index = ARTWORK[season].index(asset_id)
                # Keep the ornament outside the title/badge safe zones, but
                # inside the region's hard clipping edge. The scaled art also
                # feathers its outer alpha (see holiday_decor.py), so no
                # illustration ends at a straight vertical cut.
                inset = max(3, int(w * .009))
                aw = max(30, min(int(w * .212), 360))
                ah = max(25, min(int(h * .79), 240))
                for side, x_art in (
                    ("left", inset),
                    ("right", w - inset - aw),
                ):
                    art = scaled_corner_art(
                        season, art_index, side, aw, ah, foreground_alpha
                    )
                    im.alpha_composite(art, (max(0,x_art), max(0,int(h*.155))))
                # Retain all twelve original, packaged per-program PNG
                # variations as small accent details in the art-only gutters.
                detail_size = max(10,min(int(h*.22),int(w*.057),64))
                accent_asset = scaled_asset(
                    season, asset_id, detail_size, foreground_alpha
                )
                im.alpha_composite(
                    accent_asset,
                    (int(w*.078), int(h*.72)),
                )
                companion = ARTWORK[season][(art_index + 1) % len(ARTWORK[season])]
                accent_right = scaled_asset(
                    season, companion, detail_size, foreground_alpha
                )
                im.alpha_composite(
                    accent_right,
                    (w-int(w*.078)-detail_size, int(h*.72)),
                )

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
            serif=(ch.appearance.theme == 'holiday-broadcast'),
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

        now_text = (n.current_title or "Programming")
        if ch.appearance.theme != "holiday-broadcast":
            now_text = "NOW  " + now_text

        now_font, now_lines = _fit_wrapped_text(
            draw=draw,
            text=now_text,
            maxw=rw,
            max_lines=2,
            preferred_size=now_preferred,
            minimum_size=now_minimum,
            bold=True,
            max_height=rh,
            serif=(ch.appearance.theme == 'holiday-broadcast'),
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

        next_text = (n.next_title or "To Be Announced")
        if ch.appearance.theme != "holiday-broadcast":
            next_text = "NEXT  " + next_text

        next_font, next_lines = _fit_wrapped_text(
            draw=draw,
            text=next_text,
            maxw=rw,
            max_lines=1,
            preferred_size=next_preferred,
            minimum_size=next_minimum,
            bold=False,
            max_height=rh,
            serif=(ch.appearance.theme == 'holiday-broadcast'),
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


    if ch.appearance.theme == "holiday-broadcast" and alpha < 1.0:
        # Drawing + RGBA compositing can otherwise increase effective opacity
        # where decorations overlap the semi-transparent panel. Clamp the
        # finished image to the user-selected fade/opacity ceiling.
        limit = max(0, min(255, int(alpha * 255)))
        im.putalpha(im.getchannel("A").point(lambda value: min(value, limit)))

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
    # Freeze the holiday date and program choice for the entire overlay.
    holiday_choice = (
        select_artwork(ch.appearance.holiday_theme, n.program_key, today=host_date())
        if ch.appearance.theme == "holiday-broadcast" else None
    )
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
                        holiday_choice,
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
                    holiday_choice,
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
                        holiday_choice,
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

