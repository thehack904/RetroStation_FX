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
vulnerability reporting as described in [SECURITY.md](../SECURITY.md). These
GitHub-managed scans do not need credentials in CI; `.gitignore` and the
credential-hygiene regression tests complement them, not replace them.
Repository security settings and required checks should be reviewed before publication.

Review updates to the pinned actions and `requirements-ci.txt`, and rerun the
complete workflow on the final release candidate. Do not merge a release PR
with failed correctness/security checks. Live ErsatzTV integration remains a
separate manual release gate: run the installed `app/tools/selftest.py` and
`sudo bash verify.sh`, plus the target-host checks above. CI neither runs the
installer nor contacts a real ErsatzTV instance.

---

## Release verification

Before publication, complete fresh-install and non-purge upgrade validation,
including a populated Style database, existing managed YAML, and actual
ErsatzTV Legacy playback. Verify the live `/v1/health` version and browser
status against the candidate. Re-run CI, dependency audits, and the security
workflow against the final reviewed commit. Generate final SHA-256 manifests
after freezing and auditing the release tree. A green CI run does not by
itself validate installed-system permissions or broadcast playback.

The release changelog is [CHANGELOG.md](../CHANGELOG.md); detailed release
information is maintained in [RELEASE-NOTES.md](RELEASE-NOTES.md).
The runtime contains only bundled seasonal artwork; there is no custom image
upload endpoint.

## Sanitized source archive

The GitHub-generated source ZIP from the development repository is **not**
the public-release package: it has development-root naming and the checksum
manifests are intentionally unfrozen in development checkouts.

Generate a local, sanitized, checksum-verified candidate from a clean Git
checkout of the release branch:

```sh
python3 tools/build_release_archive.py --output /tmp/RetroStation_FX-v0.1.1-rc.zip
```

Alternatively, pass `--source-zip /path/to/downloaded-source.zip` to build
from an unmodified GitHub source archive without using Git history. The builder
removes explicitly internal-only files, rejects private repository references,
retains installer executable mode, generates both SHA-256 manifests, checks
every listed hash and package inventory, and verifies ZIP integrity. The
candidate retains its Release Candidate labeling for installation testing.

After target-host installation, security, playback and Save + Sync acceptance,
build the final public source artifact with a verified release date:

```sh
python3 tools/build_release_archive.py --release-date YYYY-MM-DD \\
  --output /tmp/RetroStation_FX-v0.1.1.zip
```

The finalization flag changes the published artifact's README status badge,
changelog heading and release notes without rewriting the private development
history or creating a GitHub tag. A public release must publish **only** the
audited source snapshot, never a push or merge of private repository Git
history. An output ZIP is not evidence that target-host acceptance passed.

## Versioning

The public release baseline is v0.1.0. For each subsequent release, update
`app/VERSION`, `app/rsfx/__init__.py`, `retrostation_fx_linux.sh`,
`verify.sh`, `tools/audit_release_tree.py` and release notes together.
`app/rsfx/config.py` and the Web UI obtain the runtime version dynamically;
verify `/v1/health` after the installed service restarts. Update the release-audit expected version when preparing a new release. Run the test
suite and installed selftest; complete the target-host validation above before
freezing a release. Regenerate `docs/LIVE-SOURCE-SHA256.txt` and
`docs/PACKAGE-SHA256.txt` with `python3 tools/update_hashes.py` as part of the
final freeze, after all release files are final.
