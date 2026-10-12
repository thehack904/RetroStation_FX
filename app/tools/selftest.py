#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("RSFX_DATABASE", str(Path(tempfile.gettempdir()) / "rsfx-selftest.db"))

config_env = os.environ.copy()
config_env.pop("RSFX_BIND_HOST", None)
config_env.pop("RSFX_PORT", None)
config_env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
subprocess.run(
    [
        sys.executable,
        "-c",
        "from rsfx.config import settings; import sys; "
        "sys.exit(0 if settings.bind_host == '127.0.0.1' and settings.port == 5055 else 1)",
    ],
    env=config_env,
    check=True,
)
config_env["RSFX_BIND_HOST"] = "192.0.2.10"
config_env["RSFX_PORT"] = "6060"
subprocess.run(
    [
        sys.executable,
        "-c",
        "from rsfx.config import settings; import sys; "
        "sys.exit(0 if settings.bind_host == '192.0.2.10' and "
        "settings.port == 6060 and settings.public_url == 'http://127.0.0.1:6060' else 1)",
    ],
    env=config_env,
    check=True,
)

from rsfx.database import Database
from rsfx.ersatztv import generate_yaml
from rsfx.models import StylePut, TriggerPolicy
from rsfx.normalize import normalize_context
from rsfx.packet import MAGIC, RECTANGLES, VERSION, inspect_header
from rsfx.renderer import render_packet_stream
from rsfx.trigger import evaluate_trigger

p = Path(os.environ["RSFX_DATABASE"])
p.unlink(missing_ok=True)

db = Database(p)
db.initialize()

style = db.put_style(
    StylePut(
        name="Selftest Style",
        trigger_policy=TriggerPolicy(
            show_on_tune=True,
            show_on_program_change=True,
        ),
    )
)

if not (style.display_name == "Selftest Style"):
    raise AssertionError("selftest check failed: style.display_name == \"Selftest Style\"")
if not (style.generated_description.startswith("Slide Left")):
    raise AssertionError("selftest check failed: style.generated_description.startswith(\"Slide Left\")")

yaml = generate_yaml(style)
if not ('name: "Selftest Style"' in yaml):
    raise AssertionError("selftest check failed: 'name: \"Selftest Style\"' in yaml")
if not ('--style-id' in yaml):
    raise AssertionError("selftest check failed: '--style-id' in yaml")
if not (f'  - "{style.id}"' in yaml):
    raise AssertionError("selftest check failed: f'  - \"{style.id}\"' in yaml")

session = "2026-10-06T19:20:12.6278443-05:00"
ctx = {
    "FrameRate": 29.97,
    "Resolution": {"Width": 640, "Height": 480},
    "Channel_StartTime": session,
    "MediaItem_ShowTitle": "Snorks",
    "MediaItem_Title": "Episode A",
    "MediaItem_Start": "2026-10-07T00:13:29+00:00",
    "MediaItem_Stop": "2026-10-07T00:20:40+00:00",
    "MediaItem_Duration": "00:07:11.000",
    "MediaItem_StreamSeek": "00:00:01.000",
    "MediaItem_Path": "/media/snorks-a.mkv",
    "Epg": [
        {
            "Title": "Snorks",
            "SubTitle": "Episode A",
            "Start": "2026-10-07T00:13:29+00:00",
            "Stop": "2026-10-07T00:20:40+00:00",
        },
        {
            "Title": "Wuzzles",
            "SubTitle": "Episode B",
            "Start": "2026-10-07T00:20:40+00:00",
            "Stop": "2026-10-07T00:28:12+00:00",
        },
    ],
}

n = normalize_context("", "Looney Tunes", ctx)
if not (n.fps == 29.97):
    raise AssertionError("selftest check failed: n.fps == 29.97")
if not (n.current_show == "Snorks"):
    raise AssertionError("selftest check failed: n.current_show == \"Snorks\"")
if not (n.next_show == "Wuzzles"):
    raise AssertionError("selftest check failed: n.next_show == \"Wuzzles\"")
if not (n.session_key == session):
    raise AssertionError("selftest check failed: n.session_key == session")

state_key = f"style:{style.id}|channel:|session:{session}"
seen = time.time()

# Regression guard: this insert previously failed with
# sqlite3.OperationalError: 14 values for 13 columns.
db.record_runtime_context(
    state_key,
    style.id,
    "",
    n.session_key,
    "Looney Tunes",
    ctx,
    n.model_dump(),
    n.fps,
    n.width,
    n.height,
    seen,
)

first = evaluate_trigger(db, style, n, state_key)
if not (first.show is True):
    raise AssertionError("selftest check failed: first.show is True")
if not (first.reason == "channel-tune"):
    raise AssertionError("selftest check failed: first.reason == \"channel-tune\"")

ctx2 = dict(ctx)
ctx2.update(
    {
        "MediaItem_Title": "Episode B",
        "MediaItem_Start": "2026-10-07T00:20:40+00:00",
        "MediaItem_Stop": "2026-10-07T00:28:12+00:00",
        "MediaItem_Path": "/media/snorks-b.mkv",
        "Epg": [
            {
                "Title": "Snorks",
                "SubTitle": "Episode B",
                "Start": "2026-10-07T00:20:40+00:00",
                "Stop": "2026-10-07T00:28:12+00:00",
            },
            {
                "Title": "Snorks",
                "SubTitle": "Episode C",
                "Start": "2026-10-07T00:28:12+00:00",
                "Stop": "2026-10-07T00:35:34+00:00",
            },
        ],
    }
)

n2 = normalize_context("", "Looney Tunes", ctx2)
second = evaluate_trigger(db, style, n2, state_key)
if not (second.show is True):
    raise AssertionError("selftest check failed: second.show is True")
if not (second.reason == "program-change"):
    raise AssertionError("selftest check failed: second.reason == \"program-change\"")

data, stats = render_packet_stream(style, n2)
h = inspect_header(data)
if not (h["magic"] == MAGIC):
    raise AssertionError("selftest check failed: h[\"magic\"] == MAGIC")
if not (h["version"] == VERSION):
    raise AssertionError("selftest check failed: h[\"version\"] == VERSION")
if not (h["type"] == RECTANGLES):
    raise AssertionError("selftest check failed: h[\"type\"] == RECTANGLES")
if not (stats.frames == round(style.overlay_display_seconds * n2.fps)):
    raise AssertionError("selftest check failed: stats.frames == round(style.overlay_display_seconds * n2.fps)")

db.record_runtime_render(
    state_key,
    style.id,
    "",
    n2.session_key,
    "Looney Tunes",
    ctx2,
    n2.model_dump(),
    "packet-v1",
    n2.fps,
    n2.width,
    n2.height,
    seen,
)

with db.connect() as c:
    runtime = c.execute(
        "SELECT renders,last_error FROM runtime_diagnostics WHERE state_key=?",
        (state_key,),
    ).fetchone()

if not (runtime is not None):
    raise AssertionError("selftest check failed: runtime is not None")
if not (runtime["renders"] == 1):
    raise AssertionError("selftest check failed: runtime[\"renders\"] == 1")
if not (runtime["last_error"] is None):
    raise AssertionError("selftest check failed: runtime[\"last_error\"] is None")

print("PASS: database/style model")
print("PASS: computed Style API labels")
print("PASS: ErsatzTV YAML friendly name")
print("PASS: Legacy Epg[] Now/Next normalization")
print("PASS: channel-less Channel_StartTime runtime session")
print("PASS: runtime_diagnostics context insert")
print("PASS: tune trigger")
print("PASS: program-change trigger")
print("PASS: dynamic FrameRate")
print("PASS: Packet v1 RECTANGLES stream generation")
print(f"PASS: rendered {stats.frames} frames, {len(data)} packet bytes")

p.unlink(missing_ok=True)
