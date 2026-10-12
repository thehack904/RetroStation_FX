from __future__ import annotations

import subprocess
from datetime import datetime, timezone


def _parse_systemd_timestamp(value: str) -> datetime | None:
    value = value.strip()
    if not value or value == "n/a":
        return None
    try:
        return datetime.strptime(value, "%a %Y-%m-%d %H:%M:%S %Z").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def detect_ersatztv_start() -> dict:
    """Observe local ErsatzTV lifecycle only; never call the ErsatzTV API."""
    try:
        result = subprocess.run(
            ["systemctl", "show", "ersatztv.service", "--property=ActiveState,MainPID,ExecMainStartTimestamp", "--no-pager"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"detected": False, "method": "systemd", "reason": str(exc)}

    if result.returncode != 0:
        return {"detected": False, "method": "systemd", "reason": "ersatztv.service not available"}

    props = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            props[key] = value
    started = _parse_systemd_timestamp(props.get("ExecMainStartTimestamp", ""))
    active = props.get("ActiveState") == "active"
    if started is None:
        return {"detected": False, "method": "systemd", "active": active, "pid": props.get("MainPID"), "reason": "start time unavailable"}
    return {
        "detected": True,
        "method": "systemd",
        "active": active,
        "pid": int(props.get("MainPID") or 0),
        "started_at": started.isoformat(),
    }
