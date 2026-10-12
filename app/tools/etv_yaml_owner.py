#!/opt/rsfx/venv/bin/python
from __future__ import annotations

import math
import os
import re
import socket
import stat
import struct
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values
import yaml


CONFIG_FILE = Path("/etc/retrostation-fx/rsfx.env")
MANAGED_HEADER = b"# Managed by RetroStation FX"
MANAGED_NAME = re.compile(r"^rsfx-[a-z0-9]+(?:-[a-z0-9]+)*\.ya?ml$")
MAX_YAML_BYTES = 65536


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError("managed YAML contains duplicate keys")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def validate_managed_yaml(content: bytes, config: dict[str, str | None]) -> None:
    if len(content) > MAX_YAML_BYTES or not content.startswith(MANAGED_HEADER):
        raise ValueError("managed YAML marker is missing or file is too large")
    try:
        payload = yaml.load(content, Loader=UniqueKeyLoader)
    except (TypeError, yaml.YAMLError) as exc:
        raise ValueError("managed YAML is invalid") from exc
    expected_keys = {
        "name",
        "command",
        "args",
        "z_index",
        "epg_entries",
        "start_seconds",
        "duration_seconds",
        "pixel_format",
        "format",
    }
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        raise ValueError("managed YAML does not match the RSFX Script Graphics schema")
    adapter_python = config.get("RSFX_ADAPTER_PYTHON") or "/opt/rsfx/venv/bin/python"
    adapter_path = config.get("RSFX_ADAPTER_PATH") or "/opt/rsfx/adapter/rsfx-etv-adapter.py"
    public_url = config.get("RSFX_PUBLIC_URL") or "http://127.0.0.1:5055"
    args = payload.get("args")
    if (
        not isinstance(payload.get("name"), str)
        or len(payload["name"]) > 200
        or payload.get("command") != adapter_python
        or not isinstance(args, list)
        or len(args) != 5
        or args[:4] != [adapter_path, "--url", public_url, "--style-id"]
    ):
        raise ValueError("managed YAML command or arguments are not the configured RSFX adapter")
    if not isinstance(args[-1], str) or not re.fullmatch(r"[1-9][0-9]*", args[-1]):
        raise ValueError("managed YAML Style ID is invalid")
    if (
        not isinstance(payload.get("z_index"), int)
        or isinstance(payload.get("z_index"), bool)
        or payload.get("epg_entries") != 2
        or payload.get("pixel_format") != "bgra"
        or payload.get("format") != "Packet"
        or not isinstance(payload.get("start_seconds"), (int, float))
        or isinstance(payload.get("start_seconds"), bool)
        or not isinstance(payload.get("duration_seconds"), (int, float))
        or isinstance(payload.get("duration_seconds"), bool)
        or not math.isfinite(payload["start_seconds"])
        or not math.isfinite(payload["duration_seconds"])
        or payload["start_seconds"] < 0
        or payload["duration_seconds"] <= 0
    ):
        raise ValueError("managed YAML rendering values are invalid")


def handoff_yaml_ownership(path: Path, config_file: Path = CONFIG_FILE) -> None:
    config = dotenv_values(config_file)
    script_dir_value = config.get("RSFX_ETV_SCRIPT_DIR") or (
        "/home/ersatztv/.local/share/ersatztv/templates/graphics-elements/script"
    )
    try:
        owner_uid = int(config["RSFX_ETV_OWNER_UID"])
        owner_gid = int(config["RSFX_ETV_OWNER_GID"])
        service_uid = int(config["RSFX_SERVICE_UID"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("ErsatzTV and RSFX service identities are not configured") from exc

    directory = Path(script_dir_value).resolve(strict=True)
    path = Path(path)
    if not path.is_absolute() or path.parent.resolve(strict=True) != directory:
        raise ValueError("managed YAML path is outside the configured Script Graphics directory")
    if not MANAGED_NAME.fullmatch(path.name):
        raise ValueError("managed YAML filename is invalid")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("managed YAML target is not a regular file")
        if info.st_uid not in (service_uid, owner_uid):
            raise ValueError("managed YAML is not owned by RSFX or ErsatzTV")
        if info.st_size > MAX_YAML_BYTES:
            raise ValueError("managed YAML file is too large")
        chunks = []
        remaining = MAX_YAML_BYTES + 1
        while remaining:
            chunk = os.read(fd, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        validate_managed_yaml(content, config)

        acl = subprocess.run(
            ["/usr/bin/getfacl", "-cp", f"/proc/self/fd/{fd}"],
            check=True,
            capture_output=True,
            text=True,
            pass_fds=(fd,),
        ).stdout
        for line in acl.splitlines():
            if line.startswith(("user:", "group:")) and line.count(":") >= 2:
                entry_type, name, _permissions = line.split(":", 2)
                if name and not (entry_type == "user" and name == "retrostation-fx"):
                    raise ValueError("managed YAML has unrelated named ACL entries")

        os.fchown(fd, owner_uid, owner_gid)
        subprocess.run(
            [
                "/usr/bin/setfacl",
                "-m",
                "u:retrostation-fx:rw-,m::rw-",
                f"/proc/self/fd/{fd}",
            ],
            check=True,
            pass_fds=(fd,),
        )
    finally:
        os.close(fd)


def main() -> int:
    try:
        if len(sys.argv) != 1:
            raise ValueError("unexpected arguments")
        configured_service_uid = int(dotenv_values(CONFIG_FILE)["RSFX_SERVICE_UID"])
        with socket.fromfd(0, socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            credentials = connection.getsockopt(
                socket.SOL_SOCKET,
                socket.SO_PEERCRED,
                struct.calcsize("3i"),
            )
        _peer_pid, peer_uid, _peer_gid = struct.unpack("3i", credentials)
        if peer_uid != configured_service_uid:
            raise ValueError("request did not originate from the RSFX service account")
        raw_path = sys.stdin.buffer.read(4097)
        if len(raw_path) > 4096 or not raw_path.endswith(b"\n"):
            raise ValueError("expected one bounded newline-terminated YAML path")
        handoff_yaml_ownership(Path(raw_path[:-1].decode("utf-8")))
    except (OSError, TypeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"RSFX managed-YAML ownership handoff failed: {exc}", file=sys.stderr)
        print(f"ERROR: {exc}", flush=True)
        return 1
    print("OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
