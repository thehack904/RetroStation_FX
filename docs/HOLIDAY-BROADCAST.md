# Holiday Broadcast — built-in RSFX template (v0.1.1)

This is one **channel-independent**, reusable NOW/NEXT Style, not a new ErsatzTV
graphics integration. It uses the existing Packet v1/BGRA path and
Style-managed YAML lifecycle. Browsing or previewing the template does not save
Styles or create ErsatzTV YAML.

## Seasonal illustration rendering

The renderer provides distinct decorative arrangements for Thanksgiving,
Christmas and New Year's, with four stable per-program variants per season.
Illustrations use cached transparent artwork composed outside the title-safe
zones. The channel-name plaque and NOW/NEXT labels remain legible at television
resolutions; hiding a text element also hides its associated plaque or divider.

Full illustrations are drawn on an overscan canvas, cropped to their visible
alpha bounds, and fitted proportionally into a 360 × 240 RGBA canvas with
transparent margins. Both side illustrations fit inside the final overlay
without hard clipping or artificial edge feathering. Normal Style opacity and
entrance/exit animation settings remain available.

The browser preview and live Packet v1 renderer use the same Pillow-generated
frame, preserving artwork placement and text layout.

## Look and operation

The Holiday Broadcast composition renders a translucent cinematic lower-third
with a gold-outlined plaque and clear channel, NOW and NEXT regions. Its original
RGBA artwork sits outside the reserved text regions; decorations can be turned
off to leave the complete text panel intact. The user can still control overlay
position, width, font sizes, opacity, timing, entrance and exit animations, the
displayed channel label, and trigger behavior using existing Style controls.

The three presentation families use:
- **Thanksgiving:** amber and warm burgundy with autumn leaves, pumpkin,
  acorns and harvest wreath.
- **Christmas:** deep evergreen and gold with snowflake, ornament, holly and
  evergreen branch.
- **New Year's:** navy and champagne gold with fireworks, gold stars, confetti
  and midnight clock.
- **Neutral:** muted charcoal and light silver, no decorative PNG.

The shipped assets are 12 original, 128×128 transparent RGBA PNGs in
`app/rsfx/assets/holiday/`; the native Linux installer copies them to
`/opt/rsfx/rsfx/assets/holiday/`. The renderer uses package-relative paths and
a strict asset registry, so it does not fetch network art or read arbitrary
user-selected paths. Existing Styles and the nine original built-ins are
unchanged.

## Editor controls and defaults

Choose **Holiday Broadcast** under Broadcast theme or create a Style from
the built-in template library. Set **Holiday season** to Automatic,
Thanksgiving, Christmas or New Year's. Artwork mode defaults to
**Stable random per program**, and **Enable seasonal artwork** is checked.
Use the same Save or Save + Sync buttons as any other Style.

Automatic selection is based on the **RSFX server's local date**, not the
client browser's date. By default:
- Nov 1 through Nov 30: Thanksgiving
- Dec 1 through Dec 25: Christmas
- Dec 26 through Jan 7 (year crossing): New Year's
- Other dates: neutral seasonal fallback, no artwork

Set `RSFX_HOLIDAY_TIMEZONE` in the RSFX service environment to a valid IANA
timezone such as `America/Chicago` to resolve calendar dates explicitly.
Manual season selection overrides the calendar at any time.

Administrators can override the inclusive MM-DD calendar windows using a
bounded JSON object in `RSFX_HOLIDAY_CALENDAR` containing all three
holiday keys:

```text
RSFX_HOLIDAY_CALENDAR={"thanksgiving":["11-01","11-30"],"christmas":["12-01","12-25"],"new-year":["12-26","01-07"]}
```

Quotes must be preserved correctly in the service environment (systemd
EnvironmentFile syntax or a correctly escaped drop-in). Each window can cross
the year boundary. Invalid settings fail validation rather than silently
selecting another holiday. Avoid overlapping windows; if they overlap, the
order is Thanksgiving, Christmas, New Year's.

## Artwork rotation

A SHA-256 digest of the active holiday and normalized program identity chooses
one of the four holiday assets. The choice is computed once per render, so it
cannot flicker between frames. Repeated overlays of the same program obtain
the same asset across requests and restarts as long as its program identity and
holiday theme remain the same.

When program identity is absent, a documented fixed fallback is used instead
of per-frame randomness. The selection helper can avoid reusing the previous
program's asset **when the previous program identity is explicitly supplied**.
Legacy ErsatzTV's current runtime context does not reliably provide that
prior identity, so the live renderer currently uses deterministic hashing
without guaranteed immediate-repeat prevention. No new persistent process or
state database was introduced.

The UI obtains its seasonal preview from the **same Pillow renderer** used for
Packet v1 output via `POST /v1/holiday/preview`, using illustrative channel
and movie names; the preview does not save state, write managed YAML, or use
the ErsatzTV API. It is a still image, not an encoded playback stream.

## Security and compatibility

Only the enumerated package-owned artwork is decoded. PNG format and
dimensions are validated before conversion to RGBA, and resized results
are cached. No uploads, arbitrary file paths, third-party artwork, or
additional ErsatzTV credentials are introduced. Existing saved Styles
migrate through the optional defaulted Appearance fields. The installer
continues using the hash-locked Pillow dependency.

**Release validation remains a separate step:** Execute actual ErsatzTV Legacy
tune/program-change overlays, review rendered artwork and text readability on
TV, perform non-purge upgrade verification, confirm existing Styles/YAML
remain unchanged, and confirm final hosted CI/security scans. The published
concept mockups are visual targets; the runtime renderer produces a
composited lower-third, not the mockups' illustrative film background.
