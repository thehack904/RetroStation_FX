#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
VERSION = (ROOT / "app/VERSION").read_text(encoding="utf-8").strip()
VERSION_HEADER = f"# RetroStation FX v{VERSION} development branch"
RELEASE_HEADER = f"# RetroStation FX v{VERSION} verified release archive"

LIVE_PATHS = [
    "app/rsfx/__init__.py",
    "app/rsfx/app.py",
    "app/rsfx/compositions.py",
    "app/rsfx/config.py",
    "app/rsfx/holiday.py",
    "app/rsfx/holiday_decor.py",
    "app/rsfx/database.py",
    "app/rsfx/ersatztv.py",
    "app/rsfx/ersatztv_refresh.py",
    "app/rsfx/ersatztv_restart.py",
    "app/rsfx/models.py",
    "app/rsfx/normalize.py",
    "app/rsfx/packet.py",
    "app/rsfx/renderer.py",
    "app/rsfx/templates.py",
    "app/rsfx/timeline.py",
    "app/rsfx/trigger.py",
    "app/rsfx/static/index.html",
    "app/rsfx/static/app.js",
    "app/rsfx/static/style.css",
    "app/rsfx/assets/holiday/acorns.png",
    "app/rsfx/assets/holiday/autumn-leaves.png",
    "app/rsfx/assets/holiday/confetti.png",
    "app/rsfx/assets/holiday/evergreen.png",
    "app/rsfx/assets/holiday/fireworks.png",
    "app/rsfx/assets/holiday/gold-stars.png",
    "app/rsfx/assets/holiday/harvest-wreath.png",
    "app/rsfx/assets/holiday/holly.png",
    "app/rsfx/assets/holiday/midnight-clock.png",
    "app/rsfx/assets/holiday/ornament.png",
    "app/rsfx/assets/holiday/pumpkin.png",
    "app/rsfx/assets/holiday/snowflake.png",
    "app/adapter/rsfx-etv-adapter.py",
    "app/tools/selftest.py",
    "app/tools/etv_yaml_owner.py",
    "app/requirements.txt",
    "app/requirements.lock",
    "app/VERSION",
]

EXCLUDE_PACKAGE = {
    ".git",
    "docs/PACKAGE-SHA256.txt",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def installed_path(relative: str) -> str:
    if relative.startswith("app/"):
        return "/opt/rsfx/" + relative.removeprefix("app/")
    return relative


def write_live(*, release: bool = False) -> None:
    lines = [
        RELEASE_HEADER if release else VERSION_HEADER,
        "# Current installed-source hashes",
        "# SHA-256 checksums of the exact application files in this archive."
        if release else "# Regenerate with: python3 tools/update_hashes.py",
    ]
    if not release:
        lines.extend([
            "# Static hashes are intentionally not frozen on the development branch.",
            "# Release/frozen packaging must commit the generated hashes.",
        ])
    lines.append("")
    for relative in LIVE_PATHS:
        path = ROOT / relative
        if not path.is_file():
            raise SystemExit(f"missing LIVE source: {relative}")
        lines.append(f"{sha256(path)}  {installed_path(relative)}")
    (DOCS / "LIVE-SOURCE-SHA256.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def package_files() -> list[Path]:
    # Respect the same export-ignore inventory used by git archive. Generating
    # manifests from a development checkout must never list an internal file
    # that is absent from the public source archive.
    ignored: set[str] = set()
    attributes = ROOT / ".gitattributes"
    if attributes.is_file():
        for line in attributes.read_text(encoding="utf-8").splitlines():
            fields = line.split()
            if len(fields) == 2 and fields[1] == "export-ignore":
                ignored.add(fields[0])
    result: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT).as_posix()
        if relative.startswith(".git/") or relative in EXCLUDE_PACKAGE or relative in ignored:
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        result.append(path)
    return sorted(result, key=lambda p: p.relative_to(ROOT).as_posix())


def write_package(*, release: bool = False) -> None:
    lines = [
        RELEASE_HEADER if release else VERSION_HEADER,
        "# SHA-256 checksums of the exact exported source files."
        if release else "# Regenerate with: python3 tools/update_hashes.py",
        "# PACKAGE-SHA256.txt excludes itself.",
    ]
    if not release:
        lines.append("# Static hashes are intentionally not frozen on the development branch.")
    lines.append("")
    for path in package_files():
        relative = path.relative_to(ROOT).as_posix()
        lines.append(f"{sha256(path)}  ./{relative}")
    (DOCS / "PACKAGE-SHA256.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate RSFX source checksums")
    parser.add_argument("--release", action="store_true",
                        help="Label manifests for a frozen release archive")
    args = parser.parse_args()
    write_live(release=args.release)
    write_package(release=args.release)
    print("Updated docs/LIVE-SOURCE-SHA256.txt")
    print("Updated docs/PACKAGE-SHA256.txt")


if __name__ == "__main__":
    main()
