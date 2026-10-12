#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from urllib.parse import urlsplit


def _normalized_key(value):
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _walk_scalars(value, prefix=""):
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield from _walk_scalars(child, path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            path = f"{prefix}[{index}]"
            yield from _walk_scalars(child, path)
    else:
        yield prefix, value


def first_value(context, *keys):
    wanted = {_normalized_key(key) for key in keys}

    # Prefer exact top-level matches first.
    for key, value in context.items():
        if _normalized_key(key) in wanted and value not in (None, ""):
            if not isinstance(value, (dict, list)):
                return str(value)

    # ErsatzTV template-variable payloads can evolve or group values.
    # Fall back to a recursive key-name match so Channel_Number,
    # channelNumber, Channel.Number, etc. all resolve consistently.
    for path, value in _walk_scalars(context):
        leaf = re.split(r"[.\[]", path)[-1].rstrip("]")
        if _normalized_key(leaf) in wanted and value not in (None, ""):
            return str(value)

    return ""


def diagnostic_keys(context):
    paths = []
    for path, _ in _walk_scalars(context):
        if path:
            paths.append(path)
    return sorted(set(paths), key=str.casefold)


def channelish_values(context):
    result = []
    for path, value in _walk_scalars(context):
        if "channel" not in _normalized_key(path):
            continue
        if value in (None, "") or isinstance(value, (dict, list)):
            continue
        text = str(value)
        if len(text) > 160:
            text = text[:157] + "..."
        result.append(f"{path}={text!r}")
    return sorted(set(result), key=str.casefold)



def render_endpoint(base_url):
    """Accept HTTP(S) RSFX endpoints only; reject ambiguous authority and path."""
    url = urlsplit(base_url)
    if (
        url.scheme.lower() not in ("http", "https")
        or not url.hostname
        or url.username is not None
        or url.password is not None
        or url.path not in ("", "/")
        or url.query
        or url.fragment
        or any(c.isspace() or ord(c) < 32 for c in base_url)
    ):
        raise ValueError("RSFX URL must be an HTTP(S) origin without credentials, path, query or fragment")
    try:
        port = url.port
    except ValueError as exc:
        raise ValueError("RSFX URL has invalid port") from exc
    if port is not None and port < 1:
        raise ValueError("RSFX URL has invalid port")
    return base_url.rstrip("/") + "/v1/render/packet"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("RSFX adapter refuses HTTP redirects")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:5055")
    ap.add_argument("--style-id", type=int, required=True)
    ap.add_argument("--timeout", type=float, default=4.0)
    args = ap.parse_args()

    try:
        raw = sys.stdin.buffer.read()
        context = json.loads(raw.decode("utf-8")) if raw else {}

        if not isinstance(context, dict):
            print(
                f"RSFX adapter: expected JSON object, got {type(context).__name__}",
                file=sys.stderr,
            )
            return 0

        # Channel identity is optional. ErsatzTV owns Style assignment and
        # Legacy Script Graphics reliably supplies Channel_StartTime for the
        # playback session; RSFX uses that session context for trigger state.
        channel_id = first_value(
            context,
            "channel_id",
            "channelId",
            "Channel_Id",
            "Channel_ID",
            "channel_number",
            "channelNumber",
            "Channel_Number",
            "ChannelNumber",
            "channel",
            "Channel",
        )
        channel_name = first_value(
            context,
            "channel_name",
            "channelName",
            "Channel_Name",
            "ChannelName",
            "channel_title",
            "channelTitle",
            "Channel_Title",
            "ChannelTitle",
        )

        if not channel_id and not first_value(context, "Channel_StartTime"):
            keys = diagnostic_keys(context)
            channel_values = channelish_values(context)
            print(
                "RSFX adapter: runtime channel and session identity unavailable; "
                f"style_id={args.style_id}; "
                f"context_keys={keys}; "
                f"channelish_values={channel_values}",
                file=sys.stderr,
            )

        body = json.dumps(
            {
                "style_id": args.style_id,
                "channel_id": channel_id,
                "channel_name": channel_name or channel_id,
                "context": context,
            },
            separators=(",", ":"),
        ).encode()

        req = urllib.request.Request(
            render_endpoint(args.url),
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/octet-stream",
                "User-Agent": "RetroStation-FX-Adapter/0.1.0",
            },
        )
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=args.timeout) as response:
            if response.status == 204:
                reason = response.headers.get("X-RSFX-Trigger-Reason", "unspecified")
                print(
                    f"RSFX adapter: render suppressed; "
                    f"style_id={args.style_id}; channel_id={channel_id!r}; "
                    f"reason={reason}",
                    file=sys.stderr,
                )
                return 0
            data = response.read()
            if data:
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
        return 0
    except Exception as exc:
        # Fail-open is deliberate. stderr is diagnostic; stdout stays empty.
        print(f"RSFX adapter fail-open: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
