from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path

from . import __version__

@dataclass(frozen=True)
class Settings:
    version: str = __version__
    bind_host: str = os.getenv("RSFX_BIND_HOST", "127.0.0.1")
    port: int = int(os.getenv("RSFX_PORT", "5055"))
    database_path: Path = Path(os.getenv("RSFX_DATABASE", "/var/lib/retrostation-fx/rsfx.db"))
    retain_raw_context: bool = os.getenv("RSFX_RETAIN_RAW_CONTEXT", "").strip().lower() in {"1", "true", "yes", "on"}
    ersatztv_script_dir: Path = Path(os.getenv(
        "RSFX_ETV_SCRIPT_DIR",
        "/home/ersatztv/.local/share/ersatztv/templates/graphics-elements/script",
    ))
    ersatztv_owner_uid: int | None = int(os.environ["RSFX_ETV_OWNER_UID"]) if os.getenv("RSFX_ETV_OWNER_UID") else None
    ersatztv_owner_gid: int | None = int(os.environ["RSFX_ETV_OWNER_GID"]) if os.getenv("RSFX_ETV_OWNER_GID") else None
    adapter_python: str = os.getenv("RSFX_ADAPTER_PYTHON", "/opt/rsfx/venv/bin/python")
    adapter_path: str = os.getenv("RSFX_ADAPTER_PATH", "/opt/rsfx/adapter/rsfx-etv-adapter.py")
    public_url: str = os.getenv(
        "RSFX_PUBLIC_URL",
        f"http://127.0.0.1:{os.getenv('RSFX_PORT', '5055')}",
    )

settings = Settings()
