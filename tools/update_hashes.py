#!/usr/bin/env python3
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
VERSION = (ROOT / "app/VERSION").read_text(encoding="utf-8").strip()
VERSION_HEADER = f"# RetroStation FX v{VERSION} release manifest"

LIVE_PATHS = [
    "app/rsfx/__init__.py",
    "app/rsfx/app.py",
    "app/rsfx/compositions.py",
    "app/rsfx/config.py",
    "app/rsfx/database.py",
    "app/rsfx/ersatztv.py",
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


def write_live() -> None:
    lines = [
        VERSION_HEADER,
        "# Current installed-source hashes",
        "# Regenerate with: python3 tools/update_hashes.py",
        "# Regenerate after any source change and before release packaging.",
        "",
    ]
    for relative in LIVE_PATHS:
        path = ROOT / relative
        if not path.is_file():
            raise SystemExit(f"missing LIVE source: {relative}")
        lines.append(f"{sha256(path)}  {installed_path(relative)}")
    (DOCS / "LIVE-SOURCE-SHA256.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def package_files() -> list[Path]:
    result: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT).as_posix()
        if relative.startswith(".git/") or relative in EXCLUDE_PACKAGE:
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        result.append(path)
    return sorted(result, key=lambda p: p.relative_to(ROOT).as_posix())


def write_package() -> None:
    lines = [
        VERSION_HEADER,
        "# Regenerate with: python3 tools/update_hashes.py",
        "# PACKAGE-SHA256.txt excludes itself.",
        "# Regenerate after any package file change and before release packaging.",
        "",
    ]
    for path in package_files():
        relative = path.relative_to(ROOT).as_posix()
        lines.append(f"{sha256(path)}  ./{relative}")
    (DOCS / "PACKAGE-SHA256.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    write_live()
    write_package()
    print("Updated docs/LIVE-SOURCE-SHA256.txt")
    print("Updated docs/PACKAGE-SHA256.txt")


if __name__ == "__main__":
    main()
