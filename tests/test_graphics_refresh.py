"""No-credential, best-effort ErsatzTV graphics refresh regression tests."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from rsfx import ersatztv_refresh as sync


class FakeResponse:
    status = 200
    def __init__(self, body):
        self.body = body
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, size):
        return self.body[:size]


class FakeOpener:
    def __init__(self, stream_error=None):
        self.calls = []
        self.stream_error = stream_error
    def open(self, request, timeout):
        self.calls.append((request.full_url, timeout))
        if "/channels.m3u" in request.full_url:
            return FakeResponse(b'#EXTM3U\n#EXTINF:-1 channel-number="26.4",Test\nhttp://localhost/26.4\n')
        if self.stream_error:
            raise self.stream_error
        return FakeResponse(b"#EXTM3U\n")


class GraphicsSyncTests(unittest.TestCase):
    def run_sync(self, fake, channel="26.4"):
        with patch.dict(os.environ, {"RSFX_ETV_URL": "http://127.0.0.1:8409"}, clear=False):
            with patch.object(sync, "build_opener", return_value=fake):
                return sync.request_graphics_refresh(channel)

    def test_stream_timeout_is_attempted_not_verified(self):
        fake = FakeOpener(TimeoutError("timed out"))
        result = self.run_sync(fake)
        self.assertTrue(result["timed_out"])
        self.assertFalse(result["database_refresh_confirmed"])
        self.assertEqual(fake.calls[-1][1], 1)
        self.assertIn("mode=segmenter", fake.calls[-1][0])

    def test_fast_playlist_does_not_claim_database_confirmation(self):
        fake = FakeOpener()
        result = self.run_sync(fake)
        self.assertTrue(result["request_completed"])
        self.assertFalse(result["database_refresh_confirmed"])

    def test_invalid_channel_rejected_before_network(self):
        with self.assertRaises(sync.GraphicsRefreshError):
            sync.request_graphics_refresh("../admin")

    def test_unknown_channel_rejected(self):
        with self.assertRaises(sync.GraphicsRefreshError):
            self.run_sync(FakeOpener(), "99.1")


    def test_discovery_returns_actual_channel_numbers_and_names(self):
        fake = FakeOpener()
        with patch.dict(os.environ, {"RSFX_ETV_URL": "http://127.0.0.1:8409", "RSFX_ETV_TOKEN": ""}):
            with patch.object(sync, "build_opener", return_value=fake):
                result = sync.discover_channels()
        self.assertEqual(result["channels"], [{"number": "26.4", "name": "Test"}])
        self.assertEqual(len(fake.calls), 1)
        self.assertIn("/iptv/channels.m3u", fake.calls[0][0])

    def test_manual_command_uses_selected_channel_and_suppresses_only_timeout(self):
        fake = FakeOpener()
        with patch.dict(os.environ, {"RSFX_ETV_URL": "http://127.0.0.1:8409", "RSFX_ETV_TOKEN": ""}):
            with patch.object(sync, "build_opener", return_value=fake):
                info = sync.manual_command_info("26.4")
        self.assertEqual(info["channel"], "26.4")
        self.assertIn("/iptv/channel/26.4.m3u8?mode=segmenter", info["command"])
        self.assertIn("--max-time 1", info["command"])
        self.assertIn("sed '/^curl: (28) Operation timed out /d'", info["command"])
        self.assertNotIn("ETV_API_KEY", info["command"])

    def test_manual_command_rejects_unknown_channel(self):
        with patch.dict(os.environ, {"RSFX_ETV_URL": "http://127.0.0.1:8409", "RSFX_ETV_TOKEN": ""}):
            with patch.object(sync, "build_opener", return_value=FakeOpener()):
                with self.assertRaises(sync.GraphicsRefreshError):
                    sync.manual_command_info("1")

    def test_manual_command_never_exposes_token(self):
        with patch.dict(os.environ, {"RSFX_ETV_URL": "http://127.0.0.1:8409", "RSFX_ETV_TOKEN": "sensitive-value"}):
            with patch.object(sync, "build_opener", return_value=FakeOpener()):
                info = sync.manual_command_info("26.4")
        self.assertIsNone(info["command"])
        self.assertNotIn("sensitive-value", str(info))

    def test_auto_detect_command_uses_first_available_channel(self):
        with patch.dict(os.environ, {"RSFX_ETV_URL": "http://127.0.0.1:8409", "RSFX_ETV_TOKEN": ""}):
            with patch.object(sync, "build_opener", return_value=FakeOpener()):
                info = sync.manual_command_info()
        self.assertEqual(info["channel"], "26.4")

    def test_ui_contains_manual_help_and_clipboard_fallback(self):
        web = Path(__file__).resolve().parents[1] / "app" / "rsfx" / "static"
        html = (web / "index.html").read_text(encoding="utf-8")
        js = (web / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="syncChannel"', html)
        self.assertIn('id="refreshChannelList"', html)
        self.assertIn('id="manualSyncDetails"', html)
        self.assertIn('id="copyManualSync"', html)
        self.assertIn("rsfxCopyCommand", js)
        self.assertIn("document.execCommand('copy')", js)
        self.assertIn("rsfxLastSyncChannel=sync.channel", js)


if __name__ == "__main__":
    unittest.main()
