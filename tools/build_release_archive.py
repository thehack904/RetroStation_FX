#!/usr/bin/env python3
"""Build an independently verified, sanitized RetroStation FX source ZIP.

A release candidate remains labeled as such until installed-host acceptance
and explicit finalization. This script does not push, tag, or publish anything.
"""
from __future__ import annotations

import argparse
import hashlib
import io
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile

INTERNAL_ONLY = {
    ".gitattributes",
    "docs/PUBLICATION-AUDIT.md",
    "docs/PILLOW-AUDIT-2026-11-08.md",
    "tools/audit_release_tree.py",
    "tests/test_release_audit.py",
}
PRIVATE_REF = re.compile(
    r"(?i)(?:retrostation[-_]fx[-_]private|"
    r"github\.com/[^/\s]+/[^/\s]+[-_]private\b|"
    r"\b(?:PR\s*#\d+|issues?\s*#?\d+)\b)"
)
SHA_LINE = re.compile(r"^([a-f0-9]{64})  (.+)$")


def collect_source(source_zip: Path | None, checkout: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    if source_zip is not None:
        with zipfile.ZipFile(source_zip) as archive:
            members = [(item.filename, item) for item in archive.infolist() if not item.is_dir()]
            roots = {name.split("/", 1)[0] for name, _ in members}
            if len(roots) != 1:
                raise ValueError("Source ZIP must contain one top-level directory")
            for name, item in members:
                relative = name.split("/", 1)[1] if "/" in name else ""
                if not relative:
                    continue
                normalized = PurePosixPath(relative)
                if normalized.is_absolute() or ".." in normalized.parts:
                    raise ValueError("Unsafe archive path")
                if (item.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Symbolic links are not allowed in publication")
                if relative in files:
                    raise ValueError("Duplicate archive member: " + relative)
                if item.file_size > 20 * 1024 * 1024:
                    raise ValueError("Unexpected large archive member: " + relative)
                files[relative] = archive.read(item)
    else:
        result = subprocess.run(
            ["git", "archive", "--format=tar", "HEAD"],
            cwd=checkout, capture_output=True, check=True,
        )
        with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
            for item in archive.getmembers():
                if item.isdir():
                    continue
                if not item.isfile():
                    raise ValueError("Unexpected non-file archive entry: " + item.name)
                files[item.name] = archive.extractfile(item).read()
    for path in INTERNAL_ONLY:
        files.pop(path, None)
    return files


def check_files(files: dict[str, bytes]) -> None:
    essential = (
        "README.md", "CHANGELOG.md", "LICENSE", "SECURITY.md",
        "app/VERSION", "retrostation_fx_linux.sh",
        "app/requirements.lock", "tools/update_hashes.py",
        "docs/RELEASE-NOTES.md",
    )
    missing = [path for path in essential if path not in files]
    if missing:
        raise ValueError("Required release files missing: " + ", ".join(missing))
    for path, data in files.items():
        if path in INTERNAL_ONLY or "-private" in path.lower() or "_private" in path.lower():
            raise ValueError("Internal-only file reached export: " + path)
        if not path or PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts:
            raise ValueError("Unsafe path: " + path)
        if path.endswith((".png", ".jpg", ".jpeg", ".webp")):
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("Unexpected binary file: " + path) from None
        if PRIVATE_REF.search(text):
            raise ValueError("Internal repository/work-item reference in " + path)


def update_release_labels(root: Path, version: str, release_date: str) -> None:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", release_date):
        raise ValueError("Use YYYY-MM-DD for release date")
    readme = root / "README.md"
    value = readme.read_text(encoding="utf-8")
    value = value.replace(
        "status-release%20candidate-orange",
        "status-released-brightgreen",
    ).replace("Release status: Release Candidate", "Release status: Released")
    readme.write_text(value, encoding="utf-8")
    changelog = root / "CHANGELOG.md"
    value = changelog.read_text(encoding="utf-8")
    needle = f"## [Unreleased] — v{version} development candidate"
    if needle not in value:
        raise ValueError("Unexpected development changelog heading")
    changelog.write_text(value.replace(needle, f"## [v{version}] — {release_date}"), encoding="utf-8")
    release_notes = root / "docs/RELEASE-NOTES.md"
    value = release_notes.read_text(encoding="utf-8")
    value = value.replace(f"## v{version} — Release candidate (unpublished)",
                          f"## v{version} — Released {release_date}")
    value = value.replace(
        f"This build identifies itself as **{version}**",
        f"Version **{version}** identifies itself",
    )
    release_notes.write_text(value, encoding="utf-8")


def verify_manifests(root: Path) -> None:
    for manifest, live in (
        ("docs/LIVE-SOURCE-SHA256.txt", True),
        ("docs/PACKAGE-SHA256.txt", False),
    ):
        lines = (root / manifest).read_text(encoding="utf-8").splitlines()
        entries = [SHA_LINE.match(line) for line in lines]
        entries = [entry for entry in entries if entry]
        if not entries:
            raise ValueError("No hashes in " + manifest)
        for entry in entries:
            listed, name = entry.groups()
            if live:
                prefix = "/opt/rsfx/"
                if not name.startswith(prefix):
                    raise ValueError("Unexpected installed file: " + name)
                relative = "app/" + name[len(prefix):]
            else:
                if not name.startswith("./"):
                    raise ValueError("Unexpected package path: " + name)
                relative = name[2:]
            target = root / relative
            if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != listed:
                raise ValueError("SHA-256 mismatch: " + relative)
        if not live:
            actual = {p.relative_to(root).as_posix() for p in root.rglob("*")
                      if p.is_file() and p.relative_to(root).as_posix() != manifest}
            recorded = {entry.group(2)[2:] for entry in entries}
            if actual != recorded:
                raise ValueError("Package manifest inventory differs from release files")


def build(source_zip: Path | None, checkout: Path, out: Path, release_date: str | None) -> Path:
    files = collect_source(source_zip, checkout)
    check_files(files)
    version = files["app/VERSION"].decode("utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Invalid release version")
    with tempfile.TemporaryDirectory(prefix="rsfx-package-") as temporary:
        root = Path(temporary)
        for relative, data in files.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        if release_date is not None:
            update_release_labels(root, version, release_date)
        subprocess.run([sys.executable, "tools/update_hashes.py", "--release"], cwd=root, check=True)
        verify_manifests(root)
        check_files({p.relative_to(root).as_posix(): p.read_bytes()
                     for p in root.rglob("*") if p.is_file()})
        suffix = "" if release_date is not None else "-rc"
        folder = f"RetroStation_FX-v{version}{suffix}"
        out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(root.rglob("*")):
                if not path.is_file():
                    continue
                relative = path.relative_to(root).as_posix()
                info = zipfile.ZipInfo(f"{folder}/{relative}")
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (0o100755 if relative in {
                    "retrostation_fx_linux.sh", "verify.sh"
                } else 0o100644) << 16
                archive.writestr(info, path.read_bytes())
        with zipfile.ZipFile(out) as archive:
            if archive.testzip() is not None:
                raise ValueError("Generated archive failed integrity check")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-zip", type=Path, help="GitHub source ZIP; otherwise use git archive HEAD")
    parser.add_argument("--checkout", type=Path, default=Path.cwd())
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--release-date", help="Finalize release labels with YYYY-MM-DD (only after acceptance)")
    args = parser.parse_args()
    result = build(args.source_zip, args.checkout, args.output, args.release_date)
    print(f"Verified sanitized source archive: {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
