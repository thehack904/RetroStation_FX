# RetroStation FX — Release details

For a concise version history, see [CHANGELOG.md](../CHANGELOG.md).
This document describes shipped behavior and technical release requirements.
It does not represent a commitment to future features or release dates.

## v0.1.1-rc.1 — Release Candidate 1 (Public Beta, 2026-11-09)

This public beta is labeled **v0.1.1-rc.1**; the application identifies
itself as **0.1.1** in the application, health endpoint,
Web UI, installer, managed YAML metadata and verification script. An older
installation keeps its original runtime version until upgraded and restarted.
The version badge describes the source version; it is not proof that a public
GitHub release has been published.

### Holiday Broadcast

- Adds **Holiday Broadcast** as the tenth built-in FX template, retaining
  the original nine designs and compatibility with previously saved Styles.
- Provides Thanksgiving, Christmas, New Year's, and neutral presentations,
  with automatic holiday windows and manual theme selection.
- Includes twelve original transparent PNGs (four for each holiday) and
  deterministic program-specific artwork rotation. Artwork does not change
  randomly from frame to frame or depend on remote image servers.
- Renders seasonal illustrations completely within transparent margins
  without clipping or artificial edge-specific fading.
- Supports independent channel plaque, NOW and NEXT display controls.
  Disabling an element also removes its corresponding plaque, label or
  divider. An explicit channel-label override handles missing station names
  without mistaking the current program title for the channel.
- Uses the same Pillow rendering implementation for the browser preview and
  ErsatzTV Legacy Packet v1/BGRA output.

For configuration, calendar boundaries and controls, see
[Holiday Broadcast](HOLIDAY-BROADCAST.md).

### Native Linux installation and Save + Sync

- Checks effective service-account ACL traversal through ErsatzTV Script
  Graphics ancestor directories, including access masked by an ACL group
  mask. It limits any repair to the required RSFX access and avoids widening
  unrelated directory identities.
- Tests write access using the unprivileged RSFX account before deployment.
  Filesystem permission problems are reported without exposing local host paths.
- Retains saved Styles when deployment fails, allowing correction and retry.
- Preserves existing RSFX data, configuration and managed YAML during supported
  non-purge upgrades. A purge deliberately removes managed state.

### Dependencies and validation

- Updates the direct Pillow constraint to `pillow>=13.0.0,<14` and the
  SHA-256-verified dependency lock to Pillow 13.0.0.
- Regression coverage includes original and seasonal templates, version
  consistency, rendering, input validation, native installer permissions, and
  package-file inventory. The final installed-source manifest must cover all
  deployed modules and bundled graphics.
- **OpenJPEG security assessment:** GitHub advisory
  [GHSA-78g4-xqwv-q3g8](https://github.com/advisories/GHSA-78g4-xqwv-q3g8)
  identifies Pillow 13.0.0 as the corrected version. Pillow upstream applied
  the OpenJPEG backport in commits
  [5f8114c](https://github.com/python-pillow/Pillow/commit/5f8114c8096b181fae493543cd3837d9f9a971cc)
  and [d3470c3](https://github.com/python-pillow/Pillow/commit/d3470c327840f4c216a1610f30e7091dfd0b97c0).
  The RSFX artwork loader additionally restricts the decoded formats to
  `PNG` **before header inspection**, so a JPEG 2000 codestream renamed
  with a PNG extension cannot select the OpenJPEG decoder through that path.
  This is an application-level mitigation and vendor-patch reference, not
  independent proof of the exact native binary in the locked Linux wheel.
  Verify the shipped wheel's patch provenance or document explicit acceptance
  of the restricted-codec attack surface before public publication.
- **Release package:** The sanitized source archive builder exports only
  public-facing files, verifies both generated SHA-256 manifests against
  the exact package, preserves executable installer permissions and can
  finalize changelog/README status after installation acceptance.
- **Before publication:** Validate a fresh native Linux install and a
  non-purge upgrade, including a populated database, preserved YAML and
  ErsatzTV schedule assignments. Confirm actual tune and program-change
  playback, Save + Sync, and `RSFX 0.1.1 · online` on the installed Web UI.
  Re-run CI/security checks and generate final SHA-256 manifests against the
  audited, frozen release source.

The built-in artwork is packaged with the application. This version does not
provide an arbitrary image upload endpoint or require an ErsatzTV API key.

## v0.1.0 — First public release (2026-10-12)

### Features

- Reusable, channel-independent graphical Styles.
- Nine original broadcast-inspired built-in templates.
- Web UI to create, preview and customize lower-third designs, typography,
  positions, opacity, animations and triggers.
- NOW/NEXT overlays driven by ErsatzTV Legacy Script Graphics schedule context.
- Managed YAML Save + Sync with manually selected Program Schedule Item
  Graphics Elements.
- Packet v1/BGRA output for ErsatzTV's graphics composition and encoding.
- Native Linux installation, service management and verification utilities.

### Installation and upgrade behavior

The native installer configures a dedicated `retrostation-fx` service account
and its state and configuration directories. Normal reinstall and upgrade
paths preserve the SQLite database, environment configuration and managed
ErsatzTV YAML. Explicit `uninstall --purge` removes managed RSFX state;
ErsatzTV may then assign new Graphics Element IDs to newly discovered YAML.

Validated installation work for the original release included non-purge
uninstall/reinstall and upgrade lifecycle checks, endpoint/selftest checks
and an empty-state preservation scenario. Those results do **not** establish
populated-Style data preservation or prove correctness for later versions.
Current releases require their own installed-host acceptance tests.

### Security and compatibility

- Uses restricted filesystem permissions for application code, state,
  environment configuration and managed ErsatzTV graphics.
- Supports local-first operation; the management Web UI does not provide
  authentication and should not be exposed directly to the public internet.
- Keeps a hash-locked runtime dependency tree and CI-based dependency checks.
- Integrates through ErsatzTV Legacy Script Graphics rather than modifying
  ErsatzTV itself or requiring an ErsatzTV API credential.

For installation and troubleshooting, see [User Guide](USER-GUIDE.md).
For implementation details, see [Technical Reference](TECHNICAL-REFERENCE.md).
