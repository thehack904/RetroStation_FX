# RetroStation FX — User Guide

For the quick introduction, installation, and your first overlay, start with the [README](../README.md).

## Install

Extract the branch/release archive, open its directory, and run:

    sudo bash ./retrostation_fx_linux.sh install

GitHub-generated ZIP files may not preserve Unix executable permissions,
even though Git tracks the installer as executable. Alternatively, enable
direct execution first:

    chmod +x retrostation_fx_linux.sh
    sudo ./retrostation_fx_linux.sh install

Verify:

    sudo bash verify.sh

Web UI:

Use the Web UI URL printed by the installer. For example, it might show:

`http://192.168.1.100:5055/`

This is an example address; use the actual address displayed by your installer.

For a **Local-only** install, open `http://127.0.0.1:5055/` on the
RSFX host. From another trusted machine with SSH access to that host,
create a local tunnel:

```bash
ssh -L 5055:127.0.0.1:5055 user@rsfx-host
```

Replace `user@rsfx-host` with your SSH login and RSFX host address, keep
the SSH session open, and browse to `http://127.0.0.1:5055/` on **your
local machine**. The tunnel does not expose the RSFX management interface
to the internet.

## ErsatzTV setup

After saving a managed Style in RSFX:

1. Use the **Sync** control in RSFX to synchronize the saved graphics with ErsatzTV. Follow the displayed status and any manual instructions; a Save alone does not complete discovery.
2. Reload or reopen the ErsatzTV Schedule Items editor. The editor loads its Graphics Elements list when the page/component initializes, so an already-open editor may not show newly discovered entries.
3. Edit the desired Program Schedule Item.
4. Select the RSFX Style under **Graphics Elements** and save.

## Holiday Broadcast (v0.1.1)

The **Holiday Broadcast** built-in design contains Thanksgiving, Christmas
and New Year's illustrations with stable per-program variation. Choose the
season automatically by date or force a holiday manually. The neutral
fallback is used outside the seasonal windows.

The **Channel label** checkbox controls both the channel-name text *and its
entire plaque*. The **NOW** and **NEXT** checkboxes each control their row's
text, badge and vertical divider. Turning off **Enable seasonal artwork**
removes the decorative illustrations without disabling the main overlay.

The illustrations are rendered in full, fitted inside transparent bounds:
there is no deliberate artificial fade at their left/right edges. Opacity
and animation settings still apply to the complete overlay.

An optional Channel label text field overrides missing channel metadata.
It does not rename the ErsatzTV channel or change the actual schedule.

Holiday Broadcast uses bundled artwork. Uploading replacement graphics is
not supported in this version. Details: [Holiday Broadcast](HOLIDAY-BROADCAST.md).

## Upgrade behavior

The installer preserves:

- `/var/lib/retrostation-fx/rsfx.db`
- `/etc/retrostation-fx/rsfx.env`
- existing managed ErsatzTV YAML files
- existing ErsatzTV Graphics Element assignments when the same YAML path remains in place

Timestamped backups are written under:

    /var/backups/retrostation-fx/

A full `uninstall --purge` intentionally removes RSFX state and managed YAML. After a purge, ErsatzTV removes stale Graphics Elements on refresh/restart; newly created Styles receive newly discovered Graphics Element IDs and must be assigned to schedules again.

## Common problems

**My Style is not listed in ErsatzTV.** Save it in RSFX, restart ErsatzTV if discovery is required, then close/reopen the Schedule Items editor (or reload the page).

**I cannot open the RSFX web UI from another device.** Check the URL printed by the installer. A `--local-only` installation intentionally accepts only local connections; do not change it to a wildcard bind address.

**Saving or syncing a Style reports an ACL/permissions error.** The installer
checks ErsatzTV Script Graphics directory traversal and the effective ACL
mask for the RSFX service account. Re-run a non-purge install/upgrade to
revalidate permissions; do not recursively make ErsatzTV's home directory
world-accessible. See [v0.1.1 release notes](RELEASE-NOTES.md).

**Holiday Channel plaque shows a movie title.** Set an explicit
**Channel label text** override in the Style editor. The v0.1.1 runtime
also avoids substituting the current EPG movie title for a missing station
name.

**I want to check my installation.** From the extracted release directory, run `sudo bash verify.sh`.

**I want to remove RSFX without deleting my Styles.** Use the normal uninstall operation rather than `uninstall --purge`; see [Technical Reference](TECHNICAL-REFERENCE.md) for state preservation details.
