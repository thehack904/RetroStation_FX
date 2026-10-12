# RetroStation FX — Maintainer Guide

Development, CI, release, and contributor details moved from the README. For the user-facing introduction, see [README](../README.md).

## Automated checks and contributing

The `CI` GitHub Actions workflow runs on every pull request and push, and can
also be run manually. It uses Python 3.12, immutable action revisions,
read-only repository permissions, and no production credentials. It checks
Python syntax/imports, Bash syntax, Ruff correctness rules, all `unittest`
tests (including isolated hash-generation validation), the runtime selftest,
and dependency vulnerabilities. Audit errors and findings fail CI; they are
not silently ignored. Ruff intentionally checks correctness, not a new
formatting convention for the existing source.

From the repository root, the local equivalents are:

```sh
(
  set -eu
  work="$(mktemp -d)"
  trap 'rm -rf "$work"' EXIT
  python3.12 -m venv "$work/venv"
  py="$work/venv/bin/python"
  "$py" -m pip install --require-hashes -r app/requirements.lock
  "$py" -m pip install -r requirements-ci.txt
  "$py" -m pip check
  export PYTHONPATH="$PWD/app"
  export RSFX_DATABASE="$work/rsfx.db"
  export RSFX_ETV_SCRIPT_DIR="$work/graphics"
  export RSFX_BIND_HOST=127.0.0.1 RSFX_PORT=5055
  unset RSFX_ETV_OWNER_UID RSFX_ETV_OWNER_GID RSFX_RETAIN_RAW_CONTEXT
  "$py" -m compileall -q app tests tools
  "$py" -c 'import rsfx.app, rsfx.renderer, rsfx.timeline, rsfx.trigger'
  bash -n retrostation_fx_linux.sh verify.sh
  "$py" -m ruff check --select E9,F63,F7,F82 app tests tools
  "$py" -m unittest discover -s tests -v
  "$py" app/tools/selftest.py
  "$py" -m pip_audit --strict --disable-pip --no-deps -r app/requirements.lock
  "$py" -m pip_audit --strict
)
```

Keep virtual environments and test state outside the checkout: the package
hash tool inventories the working tree. The hash regression test generates
and independently verifies both manifests in a temporary copy; CI does not
overwrite or freeze the development manifests. For release packaging, still
generate and verify hashes on the final reviewed release tree. Ownership/ACL
integration tests may skip when root or ACL tools are unavailable; mocked
installer/helper regressions still run without installing or changing a
service.

Before accepting external contributions, maintainers must configure branch
protection/rulesets to require **Python, tests and static checks** and
**Dependency vulnerability audit** on release/default branches. A workflow
file alone cannot enforce merge protection. Enable GitHub **secret scanning**
and **push protection** under repository Settings → Security (where supported
by the repository's visibility/plan), review alerts, and enable private
vulnerability reporting as described in [SECURITY.md](SECURITY.md). These
GitHub-managed scans do not need credentials in CI; `.gitignore` and the
credential-hygiene regression tests complement them, not replace them.
Repository settings are owner-controlled and must be verified before opening
the public repository.

Review updates to the pinned actions and `requirements-ci.txt`, and rerun the
complete workflow on the final release candidate. Do not merge a release PR
with failed correctness/security checks. Live ErsatzTV integration remains a
separate manual release gate: run the installed `app/tools/selftest.py` and
`sudo bash verify.sh`, plus the target-host checks above. CI neither runs the
installer nor contacts a real ErsatzTV instance.

---

## Development status

The dedicated service account and filesystem permissions are implemented.
Target-host install/upgrade, rendering, purge, and second-host LAN validation
remain release gates; see [Management API security](#management-api-security).
The sanitized public-repository export and publication gate is documented in
[PUBLICATION-AUDIT.md](docs/PUBLICATION-AUDIT.md). Publication requires a final
#18 freeze and explicit owner approval; the final owner-controlled publication
is tracked in #27.

---

## Versioning

The public release baseline is v0.1.0. For each subsequent release, update
`app/VERSION`, `app/rsfx/__init__.py`, `app/rsfx/config.py`,
`retrostation_fx_linux.sh`, `verify.sh`, the Web UI label, and the release
notes to the same version. If retained for private release review, update the
release version expected by `tools/audit_release_tree.py` as well. Run the test
suite and installed selftest; complete the target-host validation above before
freezing a release. Regenerate `docs/LIVE-SOURCE-SHA256.txt` and
`docs/PACKAGE-SHA256.txt` with `python3 tools/update_hashes.py` as part of the
final freeze, after all release files are final.
