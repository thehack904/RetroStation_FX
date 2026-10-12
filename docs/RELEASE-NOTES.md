# RetroStation FX v0.1.0 — First Public Release

## Status

RetroStation FX v0.1.0 is the first public RSFX release. No private prototype,
proof-of-concept, or beta build is part of the public release history.

## Proven behavior

- Styles are reusable and channel-independent.
- RSFX writes one managed Script Graphics YAML per Style.
- ErsatzTV discovers managed YAML as Script Graphics elements.
- Program Schedule Items can reference those Graphics Elements.
- Materialized playout items carry the assigned Graphics Element.
- ErsatzTV launches the RSFX adapter for active scheduled graphics.
- Legacy Script Graphics context can omit channel identity.
- RSFX uses `Channel_StartTime` as the playback-session identity.
- Tune and program-change triggers render correctly in the same session.
- Percentage-position triggers use persistent runtime-session state.
- RSFX returns Packet v1 Rectangle payloads.
- ErsatzTV performs final graphics composition and encoding.
- No ErsatzTV source patch is required.

## Target-host installation validation (2026-10-09)

The Ubuntu 24.04 `iptv` host completed a controlled **non-purge**
uninstall, reinstall with preserved state, and second in-place installation
(upgrade mode). The recorded validation reported:

- ErsatzTV and RSFX active at preflight; SQLite integrity `ok`.
- Existing `rsfx.env` configuration: 11 values retained across both passes.
- Both installations rebuilt the hash-locked Python environment, completed the
  installed selftest, and reported `{"ok":true,"version":"0.1.0","packet_mode":true}`.
- `retrostation-fx.service` remained enabled and running; the YAML ownership
  helper socket was active after reinstall.
- No `uninstall --purge` operation was performed.

**Scope limitation:** The persistent SQLite database held zero channels,
zero Styles, zero user templates, and zero Style-to-channel assignments.
The RSFX YAML snapshot also held zero files. Therefore the successful
comparisons prove preservation of existing environment settings and an
empty database only; they do **not** demonstrate preservation of populated
Styles, assignments, or ErsatzTV YAML/Graphics Element IDs.

The successful validation evidence is retained on the host under
`/var/backups/retrostation-fx/validation-v010-20261009-195702`.
The later Bandit-hardening changes merged under PR #54 passed GitHub CI
and security scans, but this installation run predates those changes.
A fresh host verification against the final release candidate is required.

Newly discovered Graphics Elements may require reloading or reopening
the ErsatzTV Schedule Items editor because its Graphics Element list
is populated when the editor initializes.

## Regression coverage

The installed selftest covers:

- SQLite Style creation
- computed Style display labels
- managed YAML friendly-name generation
- Legacy EPG NOW/NEXT normalization
- channel-less `Channel_StartTime` runtime sessions
- runtime diagnostics insertion
- tune trigger
- program-change trigger
- Packet v1 Rectangle output

The installer and `verify.sh` run the installed selftest.

## Upgrade behavior

Normal install/upgrade preserves:

- RSFX SQLite state
- RSFX configuration
- managed YAML paths
- existing ErsatzTV assignments when the YAML path remains unchanged

A purge intentionally removes RSFX state and managed YAML. Schedule assignments are not recreated automatically after a purge because ErsatzTV creates new Graphics Element IDs for newly discovered YAML files.

## Service account and filesystem permissions

RSFX now runs as the locked `retrostation-fx` system account. `/opt/rsfx`
remains root-owned and service-read-only, `/var/lib/retrostation-fx` is
service-owned, and the environment file stays root-only for systemd to load.
Installer-managed POSIX ACLs give the account only the access required for the
configured ErsatzTV Script Graphics path and existing RSFX-managed YAML; the
installer refuses to widen pre-existing named ACL permissions. Normal
uninstall preserves the account and managed state, while purge removes
RSFX-managed YAML and its ACL entries. On install and upgrade, identified RSFX
YAML is owned by ErsatzTV's effective service UID/GID; unrelated YAML ownership
is left unchanged. A hardened root-owned helper, activated through a mode-0600
systemd socket accessible only to the RSFX service account, validates the peer,
configured directory, managed filename, and marker before handing off a YAML
file and applying its RSFX write ACL. The web service retains
`NoNewPrivileges=true`.

Before backup or installation changes, the installer verifies `setfacl`,
`getfacl`, and `runuser`. On Debian/Ubuntu it automatically installs missing
`acl` and/or `util-linux` packages, tries existing package indexes first, and
refreshes indexes only when the initial install fails. Package installation is
skipped when all tools are already available.

## Dependency security baseline

The runtime lock was rebuilt from the direct requirements with pip-tools 7.6.2
and includes SHA-256 hashes for the 21 pinned runtime packages. Dependency
installation was verified on Ubuntu 24.04 with CPython 3.12.3 and venv-seeded
pip 24.0; the installer does not upgrade pip or install wheel during normal
install/upgrade. The relevant pinned baseline is FastAPI 0.142.4 with Starlette
1.7.0 and Pillow 12.3.0. `python-multipart` 0.0.20 was removed because RSFX does
not use multipart forms or uploads.

This refresh addresses the known Pillow 11.2.1 issues, including BCn encoding
buffer overflow, PSD/FITS decoding issues, and missing decompression-bomb checks.
It also replaces Starlette 0.46.2, which was affected by the form-limit DoS,
Windows UNC-path, and Range-header DoS advisories. Starlette 0.x versions remain
affected by the form-limit and UNC-path advisories, so the compatible FastAPI
pair uses the patched 1.x line. The unused `python-multipart` version was
affected by multipart-header and query-string denial-of-service advisories.

`pip-audit` 2.10.1 reported no known vulnerabilities in the complete
21-package `app/requirements.lock` on 2026-10-08. See
`docs/PUBLICATION-AUDIT.md` for the lock-generation, installation, and
per-release audit procedure. This application-level audit is not a substitute
for live target-host/ErsatzTV validation.

The hash-locked dependencies installed cleanly in a fresh Python 3.12
environment with `--require-hashes`;
`pip check`, `pip-audit`, the 69-test unittest suite (one root-only test
skipped), the installed selftest, and a FastAPI/Starlette health/capabilities
smoke test passed. The selftest generated 210 Packet v1 frames. In the earlier
installer-change sandbox, `verify.sh` could not run because no RSFX system
service was installed. The subsequent October 9 host install/upgrade result
is recorded above; live ErsatzTV rendering and populated-state verification
remain unproven by that result.

## Remaining target-host validation

The controlled install/upgrade lifecycle passed on 2026-10-09, as recorded
above. Still requiring release-candidate verification are a **populated**
Style/template/assignment database and managed-YAML preservation test;
ErsatzTV Graphics Element discovery and assignment; materialized playout and
visible tune/program-change overlays; and any purge/stale-element cleanup
claims, which were not exercised in the non-purge test. Validate restart-state
detection, `verify.sh`, and final-candidate privileged YAML ownership behavior
on the actual host as applicable. LAN/loopback exposure controls also require
target-host verification. Do not characterize these checks as completed until
their own evidence exists.

## Deferred, not release-blocking

- automatic ErsatzTV schedule assignment management
- broader platform/distribution testing
- additional overlay types beyond NOW/NEXT
