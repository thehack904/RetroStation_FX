# Changelog

Notable completed changes to RetroStation FX are recorded here. This file describes released versions and the current development candidate; it does not commit to a future roadmap.

## [v0.1.1-rc.1] — 2026-11-09 (Release Candidate 1 / Beta)

### Added
- **Holiday Broadcast**, a tenth built-in FX template with Thanksgiving, Christmas and New Year's seasonal presentations, automatic date-based theme selection, manual overrides and deterministic per-program artwork rotation.
- Twelve bundled original seasonal PNG assets, with richer cached corner illustrations and consistent Pillow-rendered previews.
- Independent channel-label, NOW and NEXT visibility controls for the Holiday Broadcast layout, including their associated plaques, badges and dividers.
- Optional explicit channel-label text override when ErsatzTV does not provide a usable station name.
- Automated visual-acceptance tests and version-consistency checks for runtime health, installer, verifier and the release audit.

### Fixed
- Effective ancestor ACL masks that could prevent the unprivileged RSFX service account from traversing ErsatzTV directories or deploying managed YAML during Save + Sync.
- Channel identity fallback that could incorrectly display a program/movie title as the channel name.
- Holiday Broadcast foreground plaque layering, unwanted dividers and clipped seasonal illustration edges. Complete artwork now fits inside transparent bounds without an artificial edge fade.
- Application, installer, verification script and release-audit version identifiers aligned to 0.1.1.
- Installed-source SHA-256 inventory coverage expanded to include holiday runtime modules, graphics-refresh code and all twelve packaged PNGs.

### Security and maintenance
- Updated the SHA-256-locked runtime dependency to Pillow 13.0.0 and retained the corresponding security audit evidence.
- Restrict bundled Holiday Broadcast artwork decoding to PNG before decoder selection, preventing crafted JPEG 2000 content from entering the application's artwork loader.
- Add sanitized release-archive construction with verified SHA-256 manifests, CI-produced installation candidates and separate final-publication labeling.
- Continued release validation is required before v0.1.1 is published. A clean automated dependency audit alone does not resolve the separately documented bundled OpenJPEG wheel question.

## [v0.1.0] — 2026-10-12

First public release of RetroStation FX.

### Added
- Native Linux installation and lifecycle management for ErsatzTV Legacy Script Graphics.
- Nine original built-in broadcast-inspired templates and reusable, channel-independent FX Styles.
- Web UI for previewing and customizing appearance, typography, timing, position, animations and triggers.
- Save + Sync support for managed ErsatzTV Script Graphics YAML and schedule-item assignments.
- Packet v1/BGRA graphics rendering, runtime validation, automated testing and release security checks.

For detailed release evidence and operating notes, see [Release details](docs/RELEASE-NOTES.md).

[v0.1.0]: https://github.com/thehack904/RetroStation_FX/releases/tag/v0.1.0
