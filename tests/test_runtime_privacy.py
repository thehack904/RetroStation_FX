from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import rsfx.app as app_module
from rsfx.database import Database, utc_now
from rsfx.models import ChannelPut, StylePut


class RuntimePrivacyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.directory.name) / "rsfx.db")
        self.database.initialize()
        self.style = self.database.put_style(StylePut(name="Privacy Test"))

    def tearDown(self):
        self.directory.cleanup()

    def record(self, state_key, context, normalized=None):
        self.database.record_runtime_render(
            state_key,
            self.style.id,
            "channel-1",
            "2026-10-08T12:00:00Z",
            "Test Show",
            context,
            normalized or {
                "current_show": "Test Show",
                "media_path": "/library/secret.mkv",
                "program_key": "start|stop|show|/library/secret.mkv",
                "fps": 30,
                "width": 1920,
                "height": 1080,
            },
            "packet-v1",
            30,
            1920,
            1080,
            time.time(),
        )

    def diagnostic_row(self, state_key):
        with self.database.connect() as connection:
            return connection.execute(
                "SELECT * FROM runtime_diagnostics WHERE state_key=?",
                (state_key,),
            ).fetchone()

    def test_default_context_is_minimized_and_path_free(self):
        self.record(
            "default",
            {
                "FrameRate": 30,
                "Channel_StartTime": "2026-10-08T12:00:00Z",
                "MediaItem_ShowTitle": "Test Show",
                "MediaItem_Path": "/library/secret.mkv",
                "Authorization": "******",
                "Unexpected": "not retained",
                "Resolution": {"Width": 1920, "Height": 1080, "token": "secret-value"},
                "Epg": [
                    {"Title": "Test Show", "Start": "start", "Path": "/library/secret.mkv"},
                    {"Title": "Next Show"},
                    {"Title": "Not retained"},
                ],
            },
        )

        row = self.diagnostic_row("default")
        context = json.loads(row["last_context_json"])
        normalized = json.loads(row["last_normalized_json"])
        persisted = row["last_context_json"] + row["last_normalized_json"]
        self.assertEqual(context["FrameRate"], 30)
        self.assertEqual(context["Resolution"], {"Width": 1920, "Height": 1080})
        self.assertEqual(len(context["Epg"]), 2)
        self.assertNotIn("Unexpected", context)
        self.assertNotIn("MediaItem_Path", context)
        self.assertNotIn("media_path", normalized)
        self.assertNotIn("program_key", normalized)
        self.assertNotIn("/library/secret.mkv", persisted)
        self.assertNotIn("secret-value", persisted)
        self.assertEqual(row["renders"], 1)
        self.assertEqual(row["last_render_format"], "packet-v1")

    def test_raw_context_opt_in_keeps_paths_but_redacts_secrets(self):
        raw_database = Database(
            Path(self.directory.name) / "raw.db",
            retain_raw_context=True,
        )
        raw_database.initialize()
        style = raw_database.put_style(StylePut(name="Raw Privacy Test"))
        raw_database.record_runtime_context(
            "raw",
            style.id,
            "channel-1",
            "session",
            "Test Show",
            {
                "MediaItem_Path": "/library/secret.mkv",
                "api_key": "secret-value",
                "Authorization": "******",
            },
            {"media_path": "/library/secret.mkv", "program_key": "private"},
            30,
            1920,
            1080,
            time.time(),
        )

        with raw_database.connect() as connection:
            row = connection.execute(
                "SELECT last_context_json,last_normalized_json "
                "FROM runtime_diagnostics WHERE state_key='raw'"
            ).fetchone()
        context = json.loads(row["last_context_json"])
        normalized = json.loads(row["last_normalized_json"])
        self.assertEqual(context["MediaItem_Path"], "/library/secret.mkv")
        self.assertEqual(context["api_key"], "[REDACTED]")
        self.assertEqual(context["Authorization"], "[REDACTED]")
        self.assertNotIn("media_path", normalized)
        self.assertNotIn("program_key", normalized)
        self.assertNotIn("secret-value", row["last_context_json"])

    def test_startup_migration_scrubs_existing_diagnostics(self):
        path = Path(self.directory.name) / "legacy.db"
        legacy = Database(path, retain_raw_context=True)
        legacy.initialize()
        style = legacy.put_style(StylePut(name="Legacy Privacy Test"))
        legacy.record_runtime_render(
            "legacy",
            style.id,
            "channel-1",
            "session",
            "Test Show",
            {"MediaItem_Path": "/library/legacy.mkv"},
            {"media_path": "/library/legacy.mkv"},
            "packet-v1",
            30,
            1920,
            1080,
            time.time(),
        )
        with legacy.connect() as connection:
            connection.execute(
                "UPDATE runtime_diagnostics SET "
                "last_context_json=?,last_normalized_json=?,last_error=? "
                "WHERE state_key='legacy'",
                (
                    json.dumps({"MediaItem_Path": "/library/legacy.mkv"}),
                    json.dumps({"media_path": "/library/legacy.mkv"}),
                    "token=legacy-secret",
                ),
            )

        Database(path).initialize()

        with legacy.connect() as connection:
            row = connection.execute(
                "SELECT last_context_json,last_normalized_json,last_error "
                "FROM runtime_diagnostics WHERE state_key='legacy'"
            ).fetchone()
        self.assertNotIn("/library/legacy.mkv", row["last_context_json"])
        self.assertNotIn("/library/legacy.mkv", row["last_normalized_json"])
        self.assertNotIn("legacy-secret", row["last_error"])

    def test_context_only_suppressed_render_keeps_path_free_diagnostics(self):
        self.database.record_runtime_context(
            "suppressed",
            self.style.id,
            "channel-1",
            "session",
            "Test Show",
            {
                "Channel_StartTime": "session",
                "MediaItem_Path": "/library/suppressed.mkv",
                "FrameRate": 25,
            },
            {
                "current_show": "Test Show",
                "media_path": "/library/suppressed.mkv",
                "program_key": "contains/path",
                "fps": 25,
            },
            25,
            1920,
            1080,
            time.time(),
        )

        row = self.diagnostic_row("suppressed")
        self.assertEqual(row["renders"], 0)
        self.assertEqual(json.loads(row["last_context_json"])["FrameRate"], 25)
        self.assertNotIn("/library/suppressed.mkv", row["last_context_json"])
        self.assertNotIn("/library/suppressed.mkv", row["last_normalized_json"])

    def test_channel_diagnostics_are_minimized_and_not_runtime_pruned(self):
        self.database.put_channel("channel-1", ChannelPut(name="Test Channel"))
        self.database.record_context(
            "channel-1",
            {
                "FrameRate": 30,
                "Channel_StartTime": "session",
                "MediaItem_Path": "/library/channel.mkv",
                "Unexpected": "not retained",
            },
            {
                "current_show": "Test Show",
                "media_path": "/library/channel.mkv",
                "program_key": "contains/path",
                "fps": 30,
            },
            30,
            1920,
            1080,
            time.time(),
        )
        self.database.record_context(
            "channel-1",
            {
                "FrameRate": 24,
                "MediaItem_ShowTitle": "Latest Show",
                "MediaItem_Path": "/library/latest.mkv",
            },
            {
                "current_show": "Latest Show",
                "media_path": "/library/latest.mkv",
                "program_key": "latest/path",
                "fps": 24,
            },
            24,
            1280,
            720,
            time.time(),
        )
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE channel_diagnostics SET updated_at=? WHERE channel_id=?",
                ("2000-01-01T00:00:00+00:00", "channel-1"),
            )

        self.database.record_runtime_error(
            "runtime-prune-trigger",
            self.style.id,
            "channel-1",
            "session",
            "Test Show",
            "render error",
            time.time(),
        )

        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT last_context_json,last_normalized_json "
                "FROM channel_diagnostics WHERE channel_id=?",
                ("channel-1",),
            ).fetchall()
        self.assertEqual(len(rows), 1)
        context = json.loads(rows[0]["last_context_json"])
        normalized = json.loads(rows[0]["last_normalized_json"])
        self.assertEqual(context["FrameRate"], 24)
        self.assertEqual(context["MediaItem_ShowTitle"], "Latest Show")
        self.assertNotIn("Unexpected", context)
        self.assertNotIn("MediaItem_Path", context)
        self.assertNotIn("media_path", normalized)
        self.assertNotIn("program_key", normalized)
        self.assertNotIn("/library/channel.mkv", rows[0]["last_context_json"])
        self.assertNotIn("/library/channel.mkv", rows[0]["last_normalized_json"])
        self.assertNotIn("/library/latest.mkv", rows[0]["last_context_json"])
        self.assertNotIn("/library/latest.mkv", rows[0]["last_normalized_json"])

    def test_deleting_channel_cascades_to_channel_diagnostics(self):
        self.database.put_channel("channel-1", ChannelPut(name="Test Channel"))
        self.database.record_context(
            "channel-1",
            {"FrameRate": 30},
            {"fps": 30},
            30,
            1920,
            1080,
            time.time(),
        )
        self.assertIsNotNone(self.database.diagnostics("channel-1"))

        self.assertTrue(self.database.delete_channel("channel-1"))

        self.assertIsNone(self.database.diagnostics("channel-1"))

    def test_runtime_diagnostics_are_bounded_and_errors_redacted(self):
        stamp = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO runtime_diagnostics(state_key,style_id,updated_at) "
                "VALUES('expired',?,'2000-01-01T00:00:00+00:00')",
                (self.style.id,),
            )
            connection.executemany(
                "INSERT INTO runtime_diagnostics(state_key,style_id,updated_at) "
                "VALUES(?,?,?)",
                [
                    (f"recent-{index}", self.style.id, stamp)
                    for index in range(1000)
                ],
            )

        self.database.record_runtime_error(
            "latest",
            self.style.id,
            "channel-1",
            "session",
            "Test Show",
            "invalid token: another-secret",
            time.time(),
        )

        with self.database.connect() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM runtime_diagnostics"
            ).fetchone()[0]
            expired = connection.execute(
                "SELECT 1 FROM runtime_diagnostics WHERE state_key='expired'"
            ).fetchone()
            error = connection.execute(
                "SELECT last_error FROM runtime_diagnostics WHERE state_key='latest'"
            ).fetchone()[0]
        self.assertEqual(count, 1000)
        self.assertIsNone(expired)
        self.assertNotIn("another-secret", error)

    def test_health_and_restart_state_hide_host_details(self):
        self.assertEqual(
            app_module.health(),
            {"ok": True, "version": app_module.__version__, "packet_mode": True},
        )
        with (
            patch.object(app_module.db, "get_integration_state", return_value="2026-10-07T12:00:00+00:00"),
            patch.object(
                app_module,
                "detect_ersatztv_start",
                return_value={
                    "detected": True,
                    "active": True,
                    "pid": 1234,
                    "started_at": "2026-10-08T12:00:00+00:00",
                },
            ),
        ):
            response = app_module.ersatztv_restart_state()

        self.assertEqual(
            set(response),
            {"yaml_changed_at", "restart_required", "state", "message"},
        )
        self.assertFalse(response["restart_required"])
        self.assertNotIn("observed", response)


if __name__ == "__main__":
    unittest.main()
