from __future__ import annotations

from pathlib import Path
import json
import socket

from .config import settings


def yaml_path_for(style):
    return settings.ersatztv_script_dir / f"rsfx-{style.slug}.yml"


def generate_yaml(style):
    return f"""# Managed by RetroStation FX {settings.version}
# Style: {style.display_name}
# {style.generated_description}
name: {json.dumps(style.display_name)}
command: {settings.adapter_python}
args:
  - {settings.adapter_path}
  - --url
  - {settings.public_url}
  - --style-id
  - "{style.id}"

z_index: {style.z_index}
epg_entries: 2

# ErsatzTV Legacy eligibility window.
start_seconds: {style.eligibility.start_seconds:g}
duration_seconds: {style.eligibility.duration_seconds:g}

pixel_format: bgra
format: Packet
"""


def path_for_style(style):
    return Path(style.yaml_path) if style.yaml_path else yaml_path_for(style)


def handoff_yaml_ownership(path):
    if settings.ersatztv_owner_uid is None and settings.ersatztv_owner_gid is None:
        return
    if settings.ersatztv_owner_uid is None or settings.ersatztv_owner_gid is None:
        raise RuntimeError("ErsatzTV ownership identity is only partially configured")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(10)
        connection.connect("/run/retrostation-fx-etv-yaml-owner.sock")
        connection.sendall(f"{path}\n".encode("utf-8"))
        connection.shutdown(socket.SHUT_WR)
        response = bytearray()
        while chunk := connection.recv(4096):
            response.extend(chunk)
            if len(response) > 4096:
                raise RuntimeError("managed-YAML ownership helper response was too large")
        response = response.decode("utf-8", errors="replace").strip()
    if response != "OK":
        raise RuntimeError(response or "managed-YAML ownership handoff failed")


def sync_yaml(style):
    path = path_for_style(style)
    if not style.manage_ersatztv_yaml:
        return None

    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()

    # ErsatzTV watches this directory. Rewrite in place so an existing
    # graphics element is not removed/recreated merely because a Style
    # was edited.
    path.write_text(generate_yaml(style), encoding="utf-8")
    if is_new:
        path.chmod(0o644)
    handoff_yaml_ownership(path)
    return path


def delete_yaml(style):
    path_for_style(style).unlink(missing_ok=True)
