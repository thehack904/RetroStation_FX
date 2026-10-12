#!/usr/bin/env bash
set -euo pipefail

EXPECTED_VERSION="0.1.0"
PY="/opt/rsfx/venv/bin/python"
SELFTEST="/opt/rsfx/tools/selftest.py"

read_env_value() {
    local key="$1" file="/etc/retrostation-fx/rsfx.env" line
    [ -f "$file" ] || return 1
    line="$(grep -E "^[[:space:]]*${key}=" "$file" | tail -n 1 || true)"
    [ -n "$line" ] || return 1
    line="${line#*=}"
    line="${line%$'\r'}"
    if [[ "$line" == \"*\" && "$line" == *\" ]]; then line="${line:1:${#line}-2}"; fi
    if [[ "$line" == \'*\' && "$line" == *\' ]]; then line="${line:1:${#line}-2}"; fi
    printf '%s\n' "$line"
}

BIND_HOST="$(read_env_value RSFX_BIND_HOST || echo 127.0.0.1)"
PORT="$(read_env_value RSFX_PORT || echo 5055)"
HEALTH_HOST="$BIND_HOST"
case "$HEALTH_HOST" in
    0.0.0.0|'') HEALTH_HOST="127.0.0.1" ;;
    ::) HEALTH_HOST="::1" ;;
esac
if [[ "$HEALTH_HOST" == *:* && "$HEALTH_HOST" != \[*\] ]]; then HEALTH_HOST="[$HEALTH_HOST]"; fi
BASE="http://${HEALTH_HOST}:${PORT}"

PASS=0
FAIL=0

pass() { echo "PASS: $*"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $*"; FAIL=$((FAIL + 1)); }

echo "============================================================"
echo " RetroStation FX v0.1.0 Verification"
echo "============================================================"

if systemctl is-active --quiet retrostation-fx.service; then
    pass "retrostation-fx.service active"
else
    fail "retrostation-fx.service inactive"
fi

SERVICE_USER="$(systemctl show retrostation-fx.service --property=User --value 2>/dev/null || true)"
if [ "$SERVICE_USER" = "retrostation-fx" ]; then
    pass "service runs as dedicated retrostation-fx account"
else
    fail "service user is ${SERVICE_USER:-unset}, expected retrostation-fx"
fi

if systemctl is-active --quiet rsfx.service 2>/dev/null; then
    fail "legacy rsfx.service active"
else
    pass "legacy rsfx.service inactive"
fi

if HEALTH="$(curl -fsS "$BASE/v1/health" 2>/dev/null)"; then
    pass "health endpoint reachable"
    VERSION="$(printf '%s' "$HEALTH" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["version"])')"
    if [ "$VERSION" = "$EXPECTED_VERSION" ]; then
        pass "version = $EXPECTED_VERSION"
    else
        fail "version = $VERSION"
    fi
else
    fail "health endpoint unreachable"
fi

if CAPS="$(curl -fsS "$BASE/v1/capabilities" 2>/dev/null)"; then
    CAPS_JSON="$CAPS" "$PY" - <<'PY_CAPS'         && pass "capability contract"         || fail "capability contract"
import json
import os

data = json.loads(os.environ["CAPS_JSON"])
assert data["graphics"]["packet_v1"] is True
assert data["graphics"]["raw_mode"] is False
assert data["graphics"]["pixel_format"] == "bgra"
assert data["style_management"]["reusable"] is True
assert data["style_management"]["channel_independent"] is True
assert data["style_management"]["managed_ersatztv_yaml"] is True
assert data["integration"]["runtime_channel_context"] is False
assert data["integration"]["runtime_session_context"] is True
assert data["integration"]["ersatztv_api_required"] is False
assert data["integration"]["schedule_assignment_owner"] == "ersatztv"
assert data["integration"]["deco_assignment_required"] is False
PY_CAPS
else
    fail "capabilities endpoint unreachable"
fi

if [ -f /var/lib/retrostation-fx/rsfx.db ]; then
    pass "SQLite database exists"
else
    fail "SQLite database missing"
fi

LISTENERS="$(ss -H -ltn "sport = :$PORT" | awk '{print $4}')"
if [ -n "$LISTENERS" ]; then
    pass "configured port $PORT listening"
else
    fail "configured port $PORT not listening"
fi

if [ "$BIND_HOST" = "127.0.0.1" ]; then
    if printf '%s\n' "$LISTENERS" | grep -Fxq "127.0.0.1:$PORT"; then
        pass "management listener bound to loopback"
    else
        fail "management listener is not bound to loopback"
    fi
fi

if [ -x "$SELFTEST" ]; then
    if PYTHONPATH=/opt/rsfx "$PY" "$SELFTEST"; then
        pass "runtime/session selftest"
    else
        fail "runtime/session selftest"
    fi
else
    fail "installed selftest missing"
fi

echo
echo "============================================================"
echo "PASS: $PASS"
echo "FAIL: $FAIL"
echo "============================================================"

if [ "$FAIL" -ne 0 ]; then
    exit 1
fi

echo "RESULT: PASS"
