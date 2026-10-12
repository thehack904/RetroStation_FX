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

For a **Local-only** install, open `http://127.0.0.1:5055/` on the RSFX host, or connect through the SSH tunnel described above.

## ErsatzTV setup

After saving a managed Style in RSFX:

1. Use the **Sync** control in RSFX to synchronize the saved graphics with ErsatzTV. Follow the displayed status and any manual instructions; a Save alone does not complete discovery.
2. Reload or reopen the ErsatzTV Schedule Items editor. The editor loads its Graphics Elements list when the page/component initializes, so an already-open editor may not show newly discovered entries.
3. Edit the desired Program Schedule Item.
4. Select the RSFX Style under **Graphics Elements** and save.

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

**I want to check my installation.** From the extracted release directory, run `sudo bash verify.sh`.

**I want to remove RSFX without deleting my Styles.** Use the normal uninstall operation rather than `uninstall --purge`; see [Technical Reference](TECHNICAL-REFERENCE.md) for state preservation details.
