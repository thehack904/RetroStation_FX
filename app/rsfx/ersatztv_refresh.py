"""Best-effort ErsatzTV graphics refresh without management API credentials.

ErsatzTV Legacy 26.10.0 refreshes registered YAML graphics when it creates
an HLS Segmenter session. This does not guarantee a refresh when a session
already exists. In particular, a one-second read timeout is NOT success.
"""
from __future__ import annotations

import os
import re
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

MAX_PLAYLIST_BYTES = 2 * 1024 * 1024
CHANNEL_PATTERN = re.compile(r"[0-9]+(?:\.[0-9]+)?")
NUMBER_PATTERN = re.compile(r'channel-number="([0-9]+(?:\.[0-9]+)?)"')


class GraphicsRefreshError(Exception):
    """The request could not be issued or ErsatzTV rejected it."""


class _SameOriginRedirect(HTTPRedirectHandler):
    def __init__(self, origin):
        super().__init__()
        self.origin = origin

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        source = urlsplit(self.origin)
        target = urlsplit(newurl)
        if (source.scheme, source.netloc) != (target.scheme, target.netloc):
            raise GraphicsRefreshError("ErsatzTV returned a cross-origin redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def request_graphics_refresh(channel: str = "") -> dict:
    """Discover a channel, request segmenter for <=1 second; never stop it."""
    base = os.getenv("RSFX_ETV_URL", "http://127.0.0.1:8409").strip().rstrip("/")
    origin = urlsplit(base)
    if (origin.scheme not in ("http", "https") or not origin.hostname
            or origin.username or origin.password or origin.path not in ("", "/")
            or origin.query or origin.fragment):
        raise GraphicsRefreshError("RSFX_ETV_URL must be an HTTP(S) origin")
    channel = str(channel or "").strip()
    if channel and not CHANNEL_PATTERN.fullmatch(channel):
        raise GraphicsRefreshError("Invalid channel number")
    # This is an optional IPTV playback token, NOT the ErsatzTV management API key.
    token = os.getenv("RSFX_ETV_TOKEN", "")
    opener = build_opener(ProxyHandler({}), _SameOriginRedirect(base))

    def get(path: str, timeout: float) -> str:
        request = Request(base + path, headers={"User-Agent": "RetroStation-FX/0.1.0"})
        with opener.open(request, timeout=timeout) as response:
            if response.status != 200:
                raise GraphicsRefreshError("Unexpected ErsatzTV HTTP status")
            data = response.read(MAX_PLAYLIST_BYTES + 1)
        if len(data) > MAX_PLAYLIST_BYTES:
            raise GraphicsRefreshError("ErsatzTV playlist too large")
        return data.decode("utf-8", "replace")

    try:
        query = ("?" + urlencode({"access_token": token})) if token else ""
        channels_m3u = get("/iptv/channels.m3u" + query, timeout=10)
        numbers = NUMBER_PATTERN.findall(channels_m3u)
        if not numbers:
            raise GraphicsRefreshError("No numbered channels in ErsatzTV lineup")
        chosen = channel or numbers[0]
        if chosen not in numbers:
            raise GraphicsRefreshError("Selected channel is not in ErsatzTV lineup")
        query_params = {"mode": "segmenter"}
        if token:
            query_params["access_token"] = token
        stream_path = ("/iptv/channel/" + quote(chosen, safe="")
                       + ".m3u8?" + urlencode(query_params))
        timed_out = False
        try:
            playlist = get(stream_path, timeout=1)
            if not playlist.startswith("#EXTM3U"):
                raise GraphicsRefreshError("ErsatzTV did not return an HLS playlist")
        except (TimeoutError, socket.timeout):
            timed_out = True
        except URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                timed_out = True
            else:
                raise
    except (HTTPError, URLError, OSError, ValueError) as exc:
        if isinstance(exc, GraphicsRefreshError):
            raise
        raise GraphicsRefreshError(f"ErsatzTV request failed: {type(exc).__name__}") from exc

    return {
        "ok": True,
        "channel": chosen,
        "timed_out": timed_out,
        "request_completed": not timed_out,
        "database_refresh_confirmed": False,
        "message": (
            f"Requested graphics refresh using channel {chosen}. "
            + ("HLS request timed out after one second; refresh is not confirmed. "
               if timed_out else "ErsatzTV returned an HLS playlist. ")
            + "Reopen ErsatzTV's graphics dropdown to verify. "
            + "An already-active HLS session can skip the refresh."
        ),
    }

# RSFX_CHANNEL_DROPDOWN_MANUAL_V1
# Read-only discovery. No management API key and no HLS worker started.
import shlex


def _channel_lineup() -> tuple[str, str, list[dict[str, str]]]:
    base = os.getenv('RSFX_ETV_URL', 'http://127.0.0.1:8409').strip().rstrip('/')
    origin = urlsplit(base)
    if (origin.scheme not in ('http', 'https') or not origin.hostname
            or origin.username or origin.password or origin.path not in ('', '/')
            or origin.query or origin.fragment):
        raise GraphicsRefreshError('RSFX_ETV_URL must be an HTTP(S) origin')

    token = os.getenv('RSFX_ETV_TOKEN', '')
    params = '?' + urlencode({'access_token': token}) if token else ''
    opener = build_opener(ProxyHandler({}), _SameOriginRedirect(base))
    try:
        req = Request(base + '/iptv/channels.m3u' + params,
                      headers={'User-Agent': 'RetroStation-FX/0.1.0'})
        with opener.open(req, timeout=10) as response:
            if response.status != 200:
                raise GraphicsRefreshError('ErsatzTV lineup request failed')
            data = response.read(MAX_PLAYLIST_BYTES + 1)
        if len(data) > MAX_PLAYLIST_BYTES:
            raise GraphicsRefreshError('ErsatzTV lineup exceeds size limit')
        listing = data.decode('utf-8', 'replace')
    except (HTTPError, URLError, OSError, TimeoutError) as exc:
        raise GraphicsRefreshError(f'ErsatzTV channel discovery failed: {type(exc).__name__}') from exc

    channels = []
    seen = set()
    for line in listing.splitlines():
        if not line.startswith('#EXTINF:'):
            continue
        match = NUMBER_PATTERN.search(line)
        if match is None:
            continue
        number = match.group(1)
        if number in seen:
            continue
        seen.add(number)
        title = line.split(',', 1)[1].strip() if ',' in line else ''
        title = ''.join(c for c in title if c.isprintable())[:120]
        channels.append({'number': number, 'name': title or f'Channel {number}'})
    if not channels:
        raise GraphicsRefreshError('No numbered channels in ErsatzTV M3U lineup')
    return base, token, channels


def discover_channels() -> dict:
    _base, _token, channels = _channel_lineup()
    return {'channels': channels}


def manual_command_info(channel: str = '') -> dict:
    base, token, channels = _channel_lineup()
    channel = str(channel or '').strip()
    valid = {item['number'] for item in channels}
    if channel and (not CHANNEL_PATTERN.fullmatch(channel) or channel not in valid):
        raise GraphicsRefreshError('Selected channel is not in ErsatzTV lineup')
    selected = channel or channels[0]['number']
    if token:
        return {
            'channel': selected, 'command': None,
            'notice': 'IPTV authentication is configured. RSFX does not expose tokens in a browser-visible command. Use an authorized playback URL on the ErsatzTV host.',
        }
    url = base + '/iptv/channel/' + quote(selected, safe='') + '.m3u8?' + urlencode({'mode': 'segmenter'})
    # RSFX_MANUAL_COPY_TIMEOUT_FIX_V2
    # Filter only curl timeout code 28, retaining other curl diagnostics.
    command = ("curl -sS --max-time 1 " + shlex.quote(url)
               + " -o /dev/null 2>&1 | sed '/^curl: (28) Operation timed out /d'")
    return {
        'channel': selected,
        'command': command,
        'notice': 'Run on a machine that can reach ErsatzTV. For a 127.0.0.1 URL, run on the ErsatzTV host. A timeout does not prove graphics were synchronized.',
    }
