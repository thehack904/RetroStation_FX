# RetroStation FX — Technical Reference

This document contains the implementation and operational details moved out of the main README. The [README](../README.md) is the starting point for everyday ErsatzTV users.

> This reference describes the private development baseline. Review release-validation or development-status language before exporting to the public repository.

## Architecture

RSFX Styles are reusable and channel-independent.

1. RSFX saves a Style in SQLite and writes one managed ErsatzTV Script Graphics YAML file for that Style.
2. ErsatzTV discovers the YAML as a Script Graphics element.
3. In ErsatzTV, assign that Graphics Element to one or more Program Schedule Items.
4. When a matching playout item runs, ErsatzTV launches the RSFX adapter and sends Legacy TemplateVariables JSON.
5. The adapter sends the runtime context and Style ID to RSFX.
6. RSFX uses `Channel_StartTime` as the playback-session identity when ErsatzTV does not provide a channel identity.
7. RSFX evaluates tune, program-change, and percentage-position triggers and returns ErsatzTV Graphics Packet v1 output.
8. ErsatzTV owns final graphics composition and video encoding.

No ErsatzTV source patch or API extension is required for this integration.

---

## Validated ErsatzTV integration

Validated against ErsatzTV Legacy v26.10.0 using:

- Script Graphics
- Packet v1
- `epg_entries: 2`
- `pixel_format: bgra`
- Program Schedule Item Graphics Element assignment
- channel-less Legacy Script context using `Channel_StartTime`

A clean purge/reinstall was validated through Style creation, ErsatzTV
discovery, schedule assignment, tune rendering, and program-change rendering
before the dedicated service-account change. Repeat this validation on the
target host with the service-account installer before release.

---

## Management API security

The web UI and management API have no authentication. A normal install
automatically detects the active source IPv4 address and binds only to that
address (never `0.0.0.0`), without prompting. It prints the detected address,
the Web UI URL, and a warning that the management API must not be exposed to
the Internet or an untrusted network.
Use `sudo ./retrostation_fx_linux.sh install --local-only` to bind to
`127.0.0.1` for SSH-only, reverse-proxy, development, or other local
administration. The UI then is not directly reachable from another LAN machine;
open it on the RSFX host or use an SSH tunnel. If address detection fails, a
normal install stops and instructs you to use `--local-only` rather than
silently opening a wildcard listener.

For Local only, open `http://127.0.0.1:5055/` on the RSFX host or use an SSH
tunnel from an administrator workstation:

    ssh -L 5055:127.0.0.1:5055 user@rsfx-host

Then open `http://127.0.0.1:5055/` on that workstation. Style and template
management endpoints are protected by this local-only network boundary, not
by user authentication.

### Runtime diagnostics and retention

RSFX stores operational state in its SQLite database. `runtime_diagnostics`
keeps session-level diagnostic snapshots keyed by style and playback session,
including channel/session identifiers, show and episode titles and schedule
times, render format, frame rate, dimensions, render count, timeline plan, and
the latest sanitized render error. It is limited to 30 days and 1,000 rows.
`channel_diagnostics` keeps a single sanitized latest snapshot per configured
channel. That row remains while the channel exists and is deleted with the
channel; it is not subject to runtime-history pruning.

Both diagnostic tables use the same minimized context by default: only timing,
resolution, title, and EPG fields needed to troubleshoot normalization and
rendering are retained; local media paths and the derived program key are not
included. Trigger state is stored separately so runtime-history cleanup does
not change trigger/session behavior.

Runtime-history cleanup runs when runtime diagnostics are written; expired
rows may remain until the next runtime event. To temporarily retain more
ErsatzTV context for support, set
`RSFX_RETAIN_RAW_CONTEXT=true` in `/etc/retrostation-fx/rsfx.env` and restart
RSFX. Raw retention includes local media paths and detailed library/program
metadata; credential-like fields (for example passwords, tokens, and
authorization values) are redacted in both diagnostic paths. Runtime history
keeps the same 30-day/1,000-row limit. Leave this setting disabled unless
needed, and remove diagnostic database backups according to the same privacy
expectations. The health and
restart-state API responses do not return the database path or ErsatzTV
process ID/start details.

Trusted-LAN access is unauthenticated: restrict the selected address and port
to administrator devices with a host/network firewall. Do not expose it to
untrusted networks or the public internet. Upgrades with an existing specific
non-loopback `RSFX_BIND_HOST` preserve it; pass `--local-only` to explicitly
override it with loopback. The configured `RSFX_PORT` is used by Uvicorn and
the adapter.

Every upgrade migrates an existing wildcard `RSFX_BIND_HOST` (`0.0.0.0` or
`::`) to `127.0.0.1`, whether it was the old default or an intentional
administrator choice. After migration, normal upgrades use the detected
Trusted-LAN address; `install --local-only` explicitly overrides it with
loopback. If detection fails, installation stops and requires the explicit
local-only option. Do not restore a wildcard setting.

### Service account and filesystem permissions

The systemd service runs as the locked `retrostation-fx` system account, not
root. `/opt/rsfx` remains root-owned and not service-writable; the service gets
read/execute access to the application. `/var/lib/retrostation-fx` is owned by
the service account for SQLite state. `/etc/retrostation-fx/rsfx.env` remains
root-only; systemd reads it before starting the service, so the application
account does not need configuration-file access.

For managed ErsatzTV YAML, the installer uses POSIX ACLs to grant the service
account traversal-only access to otherwise inaccessible parent directories,
write access to the configured Script Graphics directory, and write access to
existing RSFX-managed YAML files. On install and upgrade, identified RSFX YAML
is assigned to ErsatzTV's effective service UID/GID; unrelated YAML ownership
is left unchanged. To preserve RSFX create/update behavior without making the
web process root, a systemd socket activates a separate, hardened root helper.
Only `retrostation-fx` can connect to the mode-0600 socket, and the helper
verifies the peer UID. It accepts a single path on standard input, verifies it
is a regular `rsfx-*.yml` or `rsfx-*.yaml` file inside the configured Script
Graphics directory with the RSFX marker, then applies only the owner/group and
RSFX write ACL. It rejects unrelated named ACL entries. The helper is not a
general-purpose root filesystem operation and does not grant access to
unrelated YAML; the web process retains `NoNewPrivileges=true`.

Normal uninstall preserves the service account, state, configuration, and
managed YAML so reinstall remains possible; purge removes managed YAML, the
root helper socket/unit, and RSFX ACL entries but retains the locked system
account. The installer checks for `setfacl`, `getfacl`, and `runuser` before
backing up or changing an existing installation. If missing on Debian/Ubuntu,
it automatically installs the required `acl` and/or `util-linux` packages using
the existing root/sudo installer context. It first tries the current package
indexes and runs `apt-get update` only if that install attempt fails, then
retries once. Unsupported distributions or package-install failures stop with
a clear error; upgrades skip package installation when the tools are present.

### Remaining release validation

The non-root service model is implemented. Target-host install and upgrade,
`sudo bash verify.sh`, the installed selftest, Style and template lifecycle,
managed YAML create/update/delete, restart-state detection, adapter and live
ErsatzTV rendering, and purge behavior remain release gates in the active
Critical/High release chain. Also verify the configured LAN bind from a second
LAN host and confirm restoring loopback removes LAN access. This sandbox has no
installed RSFX systemd service, ErsatzTV host, or second LAN host to perform
those deployment checks.

---

## Services

Current service:

    retrostation-fx.service

Legacy service:

    rsfx.service

The lifecycle manager disables and stops the legacy service if it exists.
