from __future__ import annotations

import asyncio
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import rsfx.app as app_module
import rsfx.ersatztv as etv
from rsfx.database import Database
from rsfx.models import (
    RenderRequest,
    StylePut,
    TriggerPolicy,
    UserTemplatePut,
    style_slug,
)
from rsfx.normalize import normalize_context
from rsfx.packet import HEADER, MAGIC, RECTANGLES, VERSION
from rsfx.renderer import _region, render_packet_stream
from rsfx.templates import BUILTIN_TEMPLATES
from rsfx.trigger import claim_position_schedule, evaluate_trigger


class CoreLogicTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.db = Database(self.root / "rsfx.db")
        self.db.initialize()

    def test_user_template_name_rejects_empty_or_whitespace_only(self):
        for name in ("", "   ", "\t\n"):
            with self.subTest(name=repr(name)), self.assertRaises(ValidationError):
                UserTemplatePut.model_validate({"name": name, "style": {}})

    def test_user_template_name_trims_unicode_and_keeps_length_limit(self):
        value = UserTemplatePut.model_validate({
            "name": "  Café 東京  ",
            "description": "  ",
            "source_template_id": "\t",
            "source_template_name": "\n",
            "style": {"name": "  "},
        })
        self.assertEqual(value.name, "Café 東京")
        self.assertIsNone(value.description)
        self.assertIsNone(value.source_template_id)
        self.assertIsNone(value.source_template_name)
        self.assertIsNone(value.style.name)
        UserTemplatePut.model_validate({"name": "x" * 160, "style": {}})
        with self.assertRaises(ValidationError):
            UserTemplatePut.model_validate({"name": "x" * 161, "style": {}})

    def test_user_template_api_rejects_blank_name_without_database_changes(self):
        existing = self.db.put_user_template(
            UserTemplatePut.model_validate({"name": "Existing", "style": {}})
        )
        before = self.db.list_user_templates()
        with patch.object(app_module, "db", self.db):
            for name in ("", "   ", "\t\n"):
                payload = {"name": name, "style": {}}
                with self.subTest(operation="create", name=repr(name)):
                    status = self.api_request(
                        "POST",
                        "/v1/user-templates",
                        payload,
                    )
                    self.assertEqual(status, 422)
                with self.subTest(operation="update", name=repr(name)):
                    status = self.api_request(
                        "PUT",
                        f"/v1/user-templates/{existing.id}",
                        payload,
                    )
                    self.assertEqual(status, 422)
        self.assertEqual(self.db.list_user_templates(), before)

    def api_request(self, method, path, payload):
        body = json.dumps(payload).encode()
        messages = []
        request_sent = False

        async def receive():
            nonlocal request_sent
            if request_sent:
                return {"type": "http.disconnect"}
            request_sent = True
            return {
                "type": "http.request",
                "body": body,
                "more_body": False,
            }

        async def send(message):
            messages.append(message)

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [
                (b"host", b"testserver"),
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }
        asyncio.run(app_module.app(scope, receive, send))
        return next(
            message["status"]
            for message in messages
            if message["type"] == "http.response.start"
        )

    def test_slugs_and_generated_paths_stay_inside_script_directory(self):
        cases = {
            "  Cable · NOW/NEXT  ": "cable-now-next",
            "../../outside\\file": "outside-file",
            "Ü✨": "style",
            "": "style",
        }
        with patch.object(etv, "settings", ersatztv_script_dir=self.root / "graphics"):
            for name, expected in cases.items():
                with self.subTest(name=name):
                    self.assertEqual(style_slug(name), expected)
                    style = self.db.put_style(StylePut(name=name))
                    path = etv.yaml_path_for(style)
                    self.assertEqual(path.parent, self.root / "graphics")
                    self.assertEqual(path.name, f"rsfx-{style.slug}.yml")

    def test_slug_collisions_and_rename_preserve_yaml_identity(self):
        styles = [self.db.put_style(StylePut(name="Same / Name")) for _ in range(3)]
        self.assertEqual([s.slug for s in styles], ["same-name", "same-name-2", "same-name-3"])
        original_path = str(self.root / "rsfx-same-name.yml")
        self.db.set_style_yaml_path(styles[0].id, original_path)
        renamed = self.db.put_style(StylePut(name="Renamed"), style_id=styles[0].id)
        self.assertEqual(renamed.slug, styles[0].slug)
        self.assertEqual(renamed.yaml_path, original_path)

    def test_yaml_round_trips_name_and_packet_contract(self):
        style = self.db.put_style(StylePut(name='Cable: "Now" # & Next · ☀'))
        document = yaml.safe_load(etv.generate_yaml(style))
        self.assertEqual(document["name"], style.display_name)
        self.assertEqual(document["args"][-2:], ["--style-id", str(style.id)])
        self.assertEqual(document["format"], "Packet")
        self.assertEqual(document["pixel_format"], "bgra")
        self.assertEqual(document["epg_entries"], 2)
        self.assertEqual(document["start_seconds"], style.eligibility.start_seconds)
        self.assertEqual(document["duration_seconds"], style.eligibility.duration_seconds)
        self.assertEqual(document["z_index"], style.z_index)

    def test_unmanaged_style_sync_does_not_create_directories(self):
        style = self.db.put_style(StylePut(name="Unmanaged", manage_ersatztv_yaml=False))
        with patch.object(etv, "settings", ersatztv_script_dir=self.root / "absent"):
            self.assertIsNone(etv.sync_yaml(style))
        self.assertFalse((self.root / "absent").exists())

    def test_render_request_rejects_malformed_input(self):
        invalid = [
            {},
            {"style_id": "not-an-id", "context": {}},
            {"style_id": 1, "context": []},
            {"style_id": 1, "context": None},
            {"style_id": 1, "context": "not-json"},
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                RenderRequest.model_validate(value)
        with self.assertRaises(ValidationError):
            RenderRequest.model_validate_json("{")

    def test_style_rejects_oversized_and_out_of_range_values(self):
        for value in [
            {"name": "x" * 161},
            {"overlay_display_seconds": 121},
            {"appearance": {"channel_label_text": "x" * 161}},
            {"appearance": {"accent": "#ZZZZZZ"}},
            {"eligibility": {"duration_seconds": 0}},
            {"trigger_policy": {"position_percent": 100}},
        ]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                StylePut.model_validate(value)

    def test_missing_style_or_session_suppresses_render_without_state(self):
        with patch.object(app_module, "db", self.db):
            self.assertEqual(
                app_module.render_packet(RenderRequest(style_id=999, context={})).status_code,
                204,
            )
            style = self.db.put_style(StylePut(name="No session"))
            response = app_module.render_packet(RenderRequest(style_id=style.id, context={}))
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers["X-RSFX-Trigger-Reason"], "missing-runtime-session-context")
        with self.db.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM runtime_trigger_state").fetchone()[0], 0)

    def test_invalid_numeric_context_falls_back_without_losing_session(self):
        context = normalize_context(
            "", "Fallback",
            {
                "Channel_StartTime": "session",
                "FrameRate": "invalid",
                "Resolution": {"Width": "invalid", "Height": -1},
                "Epg": [None, "invalid"],
            },
        )
        self.assertEqual((context.fps, context.width, context.height), (30, 640, 480))
        self.assertEqual(context.session_key, "session")
        self.assertEqual(context.next_title, "")

    def test_trigger_boundaries_suppress_duplicates_and_persist(self):
        style = self.db.put_style(StylePut(
            name="Triggers", trigger_policy=TriggerPolicy(show_on_program_change=True),
        ))
        context = normalize_context("channel", "Fallback", {
            "Channel_StartTime": "session-1", "MediaItem_Title": "Program A",
        })
        first = evaluate_trigger(self.db, style, context, "state")
        self.assertEqual((first.show, first.reason), (True, "channel-tune"))
        reopened = Database(self.root / "rsfx.db")
        repeated = evaluate_trigger(reopened, style, context, "state")
        self.assertEqual((repeated.show, repeated.reason), (False, "no-trigger"))
        changed = context.model_copy(update={"program_key": "Program B"})
        decision = evaluate_trigger(reopened, style, changed, "state")
        self.assertEqual((decision.show, decision.reason), (True, "program-change"))
        self.assertFalse(evaluate_trigger(reopened, style, changed, "state").show)
        new_session = changed.model_copy(update={"session_key": "session-2"})
        self.assertEqual(evaluate_trigger(reopened, style, new_session, "state").reason, "channel-tune")

    def test_disabled_triggers_and_position_claim_are_isolated(self):
        style = self.db.put_style(StylePut(
            name="Disabled", trigger_policy=TriggerPolicy(show_on_tune=False),
        ))
        context = normalize_context("", "Fallback", {"Channel_StartTime": "session"})
        baseline = evaluate_trigger(self.db, style, context, "one")
        self.assertEqual((baseline.show, baseline.reason), (False, "baseline"))
        evaluate_trigger(self.db, style, context, "two")
        claim_position_schedule(self.db, "one", style.id, "", "position")
        self.assertTrue(self.db.get_runtime_trigger_state("one")["fired_position"])
        self.assertFalse(self.db.get_runtime_trigger_state("two")["fired_position"])
        claim_position_schedule(self.db, "missing", style.id, "", "position")
        self.assertIsNone(self.db.get_runtime_trigger_state("missing"))

    def test_builtin_template_regions_and_packet_rectangles_stay_in_frame(self):
        positions = (
            "top-left", "top-center", "top-right",
            "bottom-left", "bottom-center", "bottom-right",
        )
        font_maxima = (
            {"channel_font_size": 96},
            {"now_font_size": 96},
            {"next_font_size": 96},
            {
                "channel_font_size": 96,
                "now_font_size": 96,
                "next_font_size": 96,
            },
        )

        for template in BUILTIN_TEMPLATES:
            base_style = template["style"]
            for width in (640, 720):
                context = normalize_context(
                    "", "Test Channel",
                    {"Resolution": {"Width": width, "Height": 480}},
                )
                for position in positions:
                    normal_style = base_style.model_copy(update={
                        "appearance": base_style.appearance.model_copy(
                            update={"position": position},
                        ),
                    })
                    normal_region = _region(normal_style, context)
                    normal_margin = max(8, int(480 * 0.055))
                    self.assertEqual(
                        normal_region[3],
                        max(
                            118,
                            int(max(
                                normal_style.appearance.channel_font_size,
                                normal_style.appearance.now_font_size,
                                normal_style.appearance.next_font_size,
                            ) * 4.75),
                        ),
                    )
                    self.assertEqual(
                        normal_region[1],
                        normal_margin
                        if position.startswith("top")
                        else 480 - normal_region[3] - normal_margin,
                    )

                    for maximum in font_maxima:
                        with self.subTest(
                            template=template["id"],
                            width=width,
                            position=position,
                            font=next(iter(maximum)),
                        ):
                            appearance = normal_style.appearance.model_copy(
                                update=maximum,
                            )
                            appearance = appearance.model_copy(update={
                                "entrance_animation_style": "none",
                                "entrance_duration_seconds": 0,
                                "exit_animation_style": "none",
                                "exit_duration_seconds": 0,
                            })
                            style = base_style.model_copy(
                                update={"appearance": appearance},
                            )
                            region = _region(style, context)
                            x, y, region_width, region_height = region
                            self.assertGreaterEqual(x, 0)
                            self.assertGreaterEqual(y, 0)
                            self.assertLessEqual(x + region_width, width)
                            self.assertLessEqual(y + region_height, 480)

                            payload, _ = render_packet_stream(style, context)
                            packet_header = HEADER.unpack_from(payload)
                            self.assertEqual(packet_header[0], MAGIC)
                            self.assertEqual(packet_header[1], VERSION)
                            packet_type = packet_header[2]
                            payload_size = packet_header[3]
                            self.assertEqual(packet_type, RECTANGLES)
                            rectangle_count, packet_x, packet_y, packet_width, packet_height = (
                                struct.unpack_from(">HHHHH", payload, HEADER.size)
                            )
                            self.assertEqual(rectangle_count, 1)
                            self.assertEqual(
                                (packet_x, packet_y, packet_width, packet_height),
                                region,
                            )
                            self.assertLessEqual(
                                packet_x + packet_width,
                                width,
                            )
                            self.assertLessEqual(
                                packet_y + packet_height,
                                480,
                            )
                            self.assertEqual(
                                payload_size,
                                struct.calcsize(">HHHHH")
                                + packet_width * packet_height * 4,
                            )


class ConfigurationTests(unittest.TestCase):
    def load_settings(self, values):
        environment = {key: value for key, value in os.environ.items() if not key.startswith("RSFX_")}
        environment.update(values)
        environment["PYTHONPATH"] = str(ROOT / "app")
        return subprocess.run(
            [sys.executable, "-c",
             "import json; from rsfx.config import settings; "
             "from dataclasses import asdict; print(json.dumps(asdict(settings), default=str))"],
            env=environment, capture_output=True, text=True,
        )

    def test_defaults_and_explicit_paths(self):
        result = self.load_settings({})
        self.assertEqual(result.returncode, 0, result.stderr)
        settings = json.loads(result.stdout)
        self.assertEqual((settings["bind_host"], settings["port"]), ("127.0.0.1", 5055))
        self.assertFalse(settings["retain_raw_context"])
        with tempfile.TemporaryDirectory(prefix="rsfx config ") as directory:
            result = self.load_settings({
                "RSFX_PORT": "6060",
                "RSFX_DATABASE": str(Path(directory) / "state.db"),
                "RSFX_ETV_SCRIPT_DIR": str(Path(directory) / "graphics"),
                "RSFX_RETAIN_RAW_CONTEXT": " YES ",
                "RSFX_ETV_OWNER_UID": "123",
                "RSFX_ETV_OWNER_GID": "456",
            })
            self.assertEqual(result.returncode, 0, result.stderr)
            settings = json.loads(result.stdout)
            self.assertEqual(settings["database_path"], str(Path(directory) / "state.db"))
            self.assertEqual(settings["ersatztv_script_dir"], str(Path(directory) / "graphics"))
            self.assertEqual(settings["public_url"], "http://127.0.0.1:6060")
            self.assertEqual((settings["ersatztv_owner_uid"], settings["ersatztv_owner_gid"]), (123, 456))
            self.assertTrue(settings["retain_raw_context"])
            self.assertFalse((Path(directory) / "state.db").exists())

    def test_invalid_integer_configuration_fails_clearly(self):
        for key in ("RSFX_PORT", "RSFX_ETV_OWNER_UID", "RSFX_ETV_OWNER_GID"):
            with self.subTest(key=key):
                result = self.load_settings({key: "invalid"})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("ValueError", result.stderr)



class AdapterEndpointSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import runpy
        cls.adapter = runpy.run_path(str(ROOT / "app" / "adapter" / "rsfx-etv-adapter.py"))

    def test_accepts_http_https_origins(self):
        endpoint = self.adapter["render_endpoint"]
        self.assertEqual(endpoint("http://127.0.0.1:5055"), "http://127.0.0.1:5055/v1/render/packet")
        self.assertEqual(endpoint("https://rsfx.example.org/"), "https://rsfx.example.org/v1/render/packet")
        self.assertEqual(endpoint("http://[::1]:5055"), "http://[::1]:5055/v1/render/packet")

    def test_rejects_invalid_url_forms(self):
        endpoint = self.adapter["render_endpoint"]
        for url in ("file:///etc/passwd", "ftp://example.org", "http://user:pass@example.org",
                    "http://example.org/extra", "http://example.org?x=1",
                    "http://example.org#fragment", "http://example.org:99999",
                    "http://example.org:0", "http://", "http://example.org\n"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                endpoint(url)

    def test_refuses_redirects(self):
        redirect = self.adapter["_NoRedirect"]()
        with self.assertRaises(ValueError):
            redirect.redirect_request(None, None, 302, "Found", {}, "http://other.example/")


if __name__ == "__main__":
    unittest.main()
