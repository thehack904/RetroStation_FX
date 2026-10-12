#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="0.1.0"

INSTALL_ROOT="/opt/rsfx"
CONFIG_ROOT="/etc/retrostation-fx"
STATE_ROOT="/var/lib/retrostation-fx"
BACKUP_ROOT="/var/backups/retrostation-fx"
SERVICE="/etc/systemd/system/retrostation-fx.service"
LEGACY_SERVICE="/etc/systemd/system/rsfx.service"
SERVICE_USER="retrostation-fx"
SERVICE_GROUP="retrostation-fx"
ETV_OWNER_SERVICE="/etc/systemd/system/retrostation-fx-etv-yaml-owner@.service"
ETV_OWNER_SOCKET="/etc/systemd/system/retrostation-fx-etv-yaml-owner.socket"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_SOURCE="$SCRIPT_DIR/app"
ENV_FILE="$CONFIG_ROOT/rsfx.env"
ENV_EXAMPLE="$SCRIPT_DIR/config/rsfx.env.example"
DEFAULT_ETV_SCRIPT_DIR="/home/ersatztv/.local/share/ersatztv/templates/graphics-elements/script"

ACTION=""
PURGE=0
LOCAL_ONLY=0

usage() {
    cat <<'EOF'
RetroStation FX lifecycle manager

Usage:
  sudo ./retrostation_fx_linux.sh install
                                       Install or upgrade RSFX on detected Trusted LAN
  sudo ./retrostation_fx_linux.sh install --local-only
                                       Bind RSFX management to loopback; direct LAN access is unavailable
  sudo ./retrostation_fx_linux.sh uninstall
                                       Remove RSFX, preserve settings/state
  sudo ./retrostation_fx_linux.sh uninstall --purge
                                       Remove RSFX and persistent settings/state
  ./retrostation_fx_linux.sh --help    Show this help

Normal uninstall preserves:
  /etc/retrostation-fx
  /var/lib/retrostation-fx

Purge additionally removes those persistent paths and positively identified
RSFX-managed ErsatzTV Script Graphics YAML files. Backups under
/var/backups/retrostation-fx are retained for recovery.
EOF
}

if [ "$#" -eq 0 ]; then
    usage
    exit 2
fi

case "$1" in
    install)
        ACTION="install"
        shift
        ;;
    uninstall)
        ACTION="uninstall"
        shift
        ;;
    --help|-h)
        usage
        exit 0
        ;;
    *)
        echo "ERROR: First argument must be install or uninstall." >&2
        echo >&2
        usage >&2
        exit 2
        ;;
esac

while [ "$#" -gt 0 ]; do
    case "$1" in
        --local-only)
            if [ "$ACTION" != "install" ]; then
                echo "ERROR: --local-only is valid only with install." >&2
                exit 2
            fi
            LOCAL_ONLY=1
            ;;
        --purge)
            if [ "$ACTION" != "uninstall" ]; then
                echo "ERROR: --purge is valid only with uninstall." >&2
                exit 2
            fi
            PURGE=1
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "ERROR: Unknown argument: $1" >&2
            echo >&2
            usage >&2
            exit 2
            ;;
    esac
    shift
done

if [ "$(id -u)" -ne 0 ]; then
    echo "Run system-changing operations with sudo:"
    echo
    if [ "$ACTION" = "uninstall" ]; then
        if [ "$PURGE" -eq 1 ]; then echo "  sudo ./retrostation_fx_linux.sh uninstall --purge"; else echo "  sudo ./retrostation_fx_linux.sh uninstall"; fi
    else
        echo "  sudo ./retrostation_fx_linux.sh install"
    fi
    exit 1
fi

read_env_value() {
    local key="$1" file="$2" line
    [ -f "$file" ] || return 1
    line="$(grep -E "^[[:space:]]*${key}=" "$file" | tail -n 1 || true)"
    [ -n "$line" ] || return 1
    line="${line#*=}"
    line="${line%$'\r'}"
    if [[ "$line" == \"*\" && "$line" == *\" ]]; then line="${line:1:${#line}-2}"; fi
    if [[ "$line" == \'*\' && "$line" == *\' ]]; then line="${line:1:${#line}-2}"; fi
    printf '%s\n' "$line"
}

set_env_value() {
    local key="$1" value="$2" temporary
    temporary="$(mktemp "$CONFIG_ROOT/.rsfx.env.XXXXXX")"
    awk -v key="$key" -v value="$value" '
        {
            line = $0
            name = line
            sub(/=.*/, "", name)
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", name)
            if (index(line, "=") && name == key) {
                if (!written++) print key "=" value
                next
            }
            print
        }
        END {
            if (!written) print key "=" value
        }
    ' "$ENV_FILE" > "$temporary"
    chmod 0600 "$temporary"
    mv -f -- "$temporary" "$ENV_FILE"
}

ensure_permission_dependencies() {
    local os_release="${RSFX_OS_RELEASE_FILE:-/etc/os-release}"
    local os_id="" os_like="" packages=() package
    local missing_setfacl=0 missing_getfacl=0 missing_runuser=0

    command -v setfacl >/dev/null 2>&1 || missing_setfacl=1
    command -v getfacl >/dev/null 2>&1 || missing_getfacl=1
    command -v runuser >/dev/null 2>&1 || missing_runuser=1
    if [ "$missing_setfacl" -eq 0 ] && [ "$missing_getfacl" -eq 0 ] &&
        [ "$missing_runuser" -eq 0 ]; then
        return 0
    fi

    if [ -r "$os_release" ]; then
        os_id="$(. "$os_release"; printf '%s' "${ID:-}")"
        os_like="$(. "$os_release"; printf '%s' "${ID_LIKE:-}")"
    fi
    case " $os_id $os_like " in
        *" debian "*|*" ubuntu "*) ;;
        *)
            echo "ERROR: Missing ACL/service-account utilities and automatic package installation is supported only on Debian/Ubuntu." >&2
            return 1
            ;;
    esac
    if ! command -v apt-get >/dev/null 2>&1; then
        echo "ERROR: apt-get is required to install the missing ACL/service-account utilities." >&2
        return 1
    fi

    if [ "$missing_setfacl" -eq 1 ] || [ "$missing_getfacl" -eq 1 ]; then
        packages+=(acl)
    fi
    if [ "$missing_runuser" -eq 1 ]; then
        packages+=(util-linux)
    fi
    echo "Installing required system package(s): ${packages[*]}"
    if ! DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${packages[@]}"; then
        echo "Package installation failed with the current indexes; refreshing package indexes and retrying once."
        if ! DEBIAN_FRONTEND=noninteractive apt-get update; then
            echo "ERROR: apt-get update failed while preparing required RSFX system utilities." >&2
            return 1
        fi
        if ! DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${packages[@]}"; then
            echo "ERROR: Could not install required RSFX system package(s): ${packages[*]}." >&2
            return 1
        fi
    fi

    for package in setfacl getfacl runuser; do
        if ! command -v "$package" >/dev/null 2>&1; then
            echo "ERROR: Required command '$package' is still unavailable after package installation." >&2
            return 1
        fi
    done
}

detect_ersatztv_identity() {
    local properties load_state active_state main_pid configured_user configured_group
    local uid gid passwd_entry group_entry
    properties="$(systemctl show ersatztv.service --property=LoadState,ActiveState,MainPID,User,Group --no-pager 2>/dev/null)" || {
        echo "ERROR: Could not inspect ersatztv.service to determine the ErsatzTV YAML owner." >&2
        return 1
    }
    load_state="$(awk -F= '$1 == "LoadState" {print $2}' <<< "$properties")"
    active_state="$(awk -F= '$1 == "ActiveState" {print $2}' <<< "$properties")"
    main_pid="$(awk -F= '$1 == "MainPID" {print $2}' <<< "$properties")"
    configured_user="$(awk -F= '$1 == "User" {print $2}' <<< "$properties")"
    configured_group="$(awk -F= '$1 == "Group" {print $2}' <<< "$properties")"
    if [ "$load_state" != "loaded" ]; then
        echo "ERROR: ersatztv.service is not loaded; cannot safely determine managed YAML ownership." >&2
        return 1
    fi

    if [ "$active_state" = "active" ] && [[ "$main_pid" =~ ^[1-9][0-9]*$ ]] &&
        [ -r "/proc/$main_pid/status" ]; then
        uid="$(awk '/^Uid:/ {print $3}' "/proc/$main_pid/status")"
        gid="$(awk '/^Gid:/ {print $3}' "/proc/$main_pid/status")"
        passwd_entry="$(getent passwd "$uid" || true)"
        group_entry="$(getent group "$gid" || true)"
        if [ -z "$passwd_entry" ] || [ -z "$group_entry" ]; then
            echo "ERROR: ErsatzTV's active process UID/GID does not map to local accounts." >&2
            return 1
        fi
    else
        configured_user="${configured_user:-root}"
        passwd_entry="$(getent passwd "$configured_user" || true)"
        if [ -z "$passwd_entry" ]; then
            echo "ERROR: ErsatzTV service user '$configured_user' cannot be resolved." >&2
            return 1
        fi
        uid="$(cut -d: -f3 <<< "$passwd_entry")"
        gid="$(cut -d: -f4 <<< "$passwd_entry")"
        if [ -n "$configured_group" ]; then
            group_entry="$(getent group "$configured_group" || true)"
            if [ -z "$group_entry" ]; then
                echo "ERROR: ErsatzTV service group '$configured_group' cannot be resolved." >&2
                return 1
            fi
            gid="$(cut -d: -f3 <<< "$group_entry")"
        else
            group_entry="$(getent group "$gid" || true)"
        fi
        if [ -z "$group_entry" ]; then
            echo "ERROR: ErsatzTV primary service group cannot be resolved." >&2
            return 1
        fi
    fi

    ETV_UID="$(cut -d: -f3 <<< "$passwd_entry")"
    ETV_USER="$(cut -d: -f1 <<< "$passwd_entry")"
    ETV_GID="$(cut -d: -f3 <<< "$group_entry")"
    ETV_GROUP="$(cut -d: -f1 <<< "$group_entry")"
    if [[ ! "$ETV_UID" =~ ^[0-9]+$ ]] || [[ ! "$ETV_GID" =~ ^[0-9]+$ ]]; then
        echo "ERROR: ErsatzTV service account UID/GID is invalid." >&2
        return 1
    fi
    echo "Detected ErsatzTV YAML owner: ${ETV_USER}:${ETV_GROUP} (${ETV_UID}:${ETV_GID})"
}

ensure_service_account() {
    local group_entry group_gid member name password uid primary_gid
    local -a members=()
    if ! getent group "$SERVICE_GROUP" >/dev/null; then
        groupadd --system "$SERVICE_GROUP"
    fi
    group_entry="$(getent group "$SERVICE_GROUP")"
    group_gid="$(cut -d: -f3 <<< "$group_entry")"
    IFS=, read -r -a members <<< "${group_entry##*:}"
    for member in "${members[@]}"; do
        if [ -n "$member" ] && [ "$member" != "$SERVICE_USER" ]; then
            echo "ERROR: Group $SERVICE_GROUP already has unrelated member $member." >&2
            return 1
        fi
    done
    while IFS=: read -r name password uid primary_gid _; do
        if [ "$primary_gid" = "$group_gid" ] && [ "$name" != "$SERVICE_USER" ]; then
            echo "ERROR: Group $SERVICE_GROUP is already the primary group of unrelated account $name." >&2
            return 1
        fi
    done < <(getent passwd)
    if getent passwd "$SERVICE_USER" >/dev/null; then
        usermod --gid "$SERVICE_GROUP" --groups "" --home /nonexistent \
            --shell /usr/sbin/nologin --lock "$SERVICE_USER"
    else
        useradd --system --gid "$SERVICE_GROUP" --home-dir /nonexistent --no-create-home \
            --shell /usr/sbin/nologin --comment "RetroStation FX service" "$SERVICE_USER"
    fi
}

assert_acl_scope() {
    local path="$1" service_user="$2"
    if ! getfacl -cp -- "$path" | awk -F: -v service_user="$service_user" '
        /^user:[^:]+:/ || /^group:[^:]+:/ {
            if ($2 != service_user) invalid = 1
        }
        /^default:user:[^:]+:/ || /^default:group:[^:]+:/ {
            if ($3 != service_user) invalid = 1
        }
        END { exit invalid }
    '; then
        echo "ERROR: $path has existing named ACL entries. Refusing to widen its ACL mask; resolve those ACLs before installing." >&2
        return 1
    fi
}

configure_etv_script_dir_access() {
    local script_dir="$1" service_user="$2" owner_uid="$3" owner_gid="$4"
    local canonical parent file created=0
    local -a parents=()
    canonical="$(realpath -m -- "$script_dir")"
    if [ ! -d "$canonical" ]; then
        mkdir -p -- "$canonical"
        chown "${owner_uid}:${owner_gid}" "$canonical"
        chmod 0750 "$canonical"
        created=1
    fi

    parent="$(dirname -- "$canonical")"
    while [ "$parent" != "/" ]; do
        parents+=("$parent")
        parent="$(dirname -- "$parent")"
    done
    for ((i=${#parents[@]}-1; i>=0; i--)); do
        parent="${parents[$i]}"
        if ! runuser -u "$service_user" -- test -x "$parent"; then
            assert_acl_scope "$parent" "$service_user"
            setfacl -m "u:${service_user}:--x" -- "$parent"
        fi
    done

    assert_acl_scope "$canonical" "$service_user"
    setfacl -m "u:${service_user}:rwx" -- "$canonical"
    while IFS= read -r -d '' file; do
        [ ! -L "$file" ] || continue
        if grep -Eq '^# Managed by RetroStation FX([[:space:]]|$)' "$file" 2>/dev/null; then
            assert_acl_scope "$file" "$service_user"
            chown "${owner_uid}:${owner_gid}" "$file"
            setfacl -m "u:${service_user}:rw-" -- "$file"
        fi
    done < <(find "$canonical" -maxdepth 1 -type f \( -name 'rsfx-*.yml' -o -name 'rsfx-*.yaml' \) -print0)
    [ "$created" -eq 0 ] || echo "Created Script Graphics directory owned by ErsatzTV: $canonical"
}

remove_etv_script_dir_access() {
    local script_dir="$1" service_user="$2" canonical parent file
    canonical="$(realpath -m -- "$script_dir")"
    if [ -d "$canonical" ]; then
        while IFS= read -r -d '' file; do
            [ ! -L "$file" ] || continue
            if grep -Eq 'Managed by RetroStation FX|/opt/rsfx/|rsfx-etv-adapter\.py' "$file" 2>/dev/null; then
                setfacl -x "u:${service_user}" -- "$file" 2>/dev/null || true
            fi
        done < <(find "$canonical" -maxdepth 1 -type f \( -name 'rsfx-*.yml' -o -name 'rsfx-*.yaml' \) -print0)
        setfacl -x "u:${service_user}" -x "d:u:${service_user}" -- "$canonical" 2>/dev/null || true
    fi
    parent="$(dirname -- "$canonical")"
    while [ "$parent" != "/" ]; do
        setfacl -x "u:${service_user}" -- "$parent" 2>/dev/null || true
        parent="$(dirname -- "$parent")"
    done
}

configure_service_filesystem_access() {
    local script_dir path
    local -a directories=()
    local -a files=()

    [ ! -L "$INSTALL_ROOT" ] || { echo "ERROR: Refusing to set service ownership through a symlink: $INSTALL_ROOT" >&2; return 1; }
    [ ! -L "$STATE_ROOT" ] || { echo "ERROR: Refusing to set service ownership through a symlink: $STATE_ROOT" >&2; return 1; }
    [ ! -L "$CONFIG_ROOT" ] || { echo "ERROR: Refusing to change configuration permissions through a symlink: $CONFIG_ROOT" >&2; return 1; }

    chown -R root:root "$INSTALL_ROOT"
    while IFS= read -r -d '' path; do directories+=("$path"); done < <(find "$INSTALL_ROOT" -type d -print0)
    while IFS= read -r -d '' path; do files+=("$path"); done < <(find "$INSTALL_ROOT" -type f -print0)
    ((${#directories[@]} == 0)) || chmod 0755 "${directories[@]}"
    ((${#files[@]} == 0)) || chmod a+rX,go-w "${files[@]}"

    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "$STATE_ROOT"
    while IFS= read -r -d '' path; do chmod 0750 "$path"; done < <(find "$STATE_ROOT" -type d -print0)
    while IFS= read -r -d '' path; do chmod 0640 "$path"; done < <(find "$STATE_ROOT" -type f -print0)

    chown root:root "$CONFIG_ROOT" "$ENV_FILE"
    chmod 0750 "$CONFIG_ROOT"
    chmod 0600 "$ENV_FILE"
    set_env_value RSFX_SERVICE_UID "$(id -u "$SERVICE_USER")"

    script_dir="$(read_env_value RSFX_ETV_SCRIPT_DIR "$ENV_FILE" 2>/dev/null || echo "$DEFAULT_ETV_SCRIPT_DIR")"
    case "$script_dir" in
        /*) ;;
        *) echo "ERROR: RSFX_ETV_SCRIPT_DIR must be an absolute path." >&2; return 1 ;;
    esac
    configure_etv_script_dir_access "$script_dir" "$SERVICE_USER" "$ETV_UID" "$ETV_GID"
}

detect_lan_ipv4() {
    local route source device
    command -v ip >/dev/null 2>&1 || return 1
    route="$(ip -4 route get 1.1.1.1 2>/dev/null | head -n 1 || true)"
    source="$(awk '{for (i=1; i<NF; i++) if ($i == "src") {print $(i+1); exit}}' <<< "$route")"
    if [[ "$source" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] &&
        [[ "$source" != 127.* ]] &&
        ip -o -4 addr show scope global 2>/dev/null |
            awk '{split($4, address, "/"); print address[1]}' |
            grep -Fxq "$source"; then
        printf '%s\n' "$source"
        return 0
    fi

    device="$(ip -4 route show default 2>/dev/null | awk 'NR == 1 {for (i=1; i<NF; i++) if ($i == "dev") {print $(i+1); exit}}')"
    [ -n "$device" ] || return 1
    ip -o -4 addr show dev "$device" scope global 2>/dev/null |
        awk 'NR == 1 {split($4, address, "/"); if (address[1] !~ /^127\./) print address[1]}'
}

choose_management_bind() {
    local detected="$1" port="$2" local_only="${3:-0}"
    if [ "$local_only" -eq 1 ]; then
        echo "Local-only management selected; the Web UI is not directly reachable from another LAN machine."
        echo "Open it on this host or use an SSH tunnel: ssh -L ${port}:127.0.0.1:${port} user@rsfx-host"
        set_env_value RSFX_BIND_HOST "127.0.0.1"
        return
    fi

    if [ -n "$detected" ]; then
        echo "Detected RSFX management address: $detected"
        echo
        echo "RSFX will make the Web UI available on your trusted LAN at:"
        echo "http://${detected}:${port}/"
        echo
        echo "The management API is unauthenticated. Do not expose port $port"
        echo "to the Internet or an untrusted network."
        echo
        set_env_value RSFX_BIND_HOST "$detected"
    else
        echo "ERROR: No active LAN IPv4 address was detected; refusing to bind to a wildcard."
        echo "Use --local-only to install with management bound to 127.0.0.1."
        return 1
    fi
}

safe_rm_tree() {
    local target="$1" expected="$2"
    [ "$target" = "$expected" ] || { echo "ERROR: Refusing unsafe removal target: $target" >&2; exit 1; }
    [ ! -L "$target" ] || { echo "ERROR: Refusing to recursively remove symlink: $target" >&2; exit 1; }
    rm -rf -- "$target"
}

stop_remove_services() {
    echo "--- Stop and disable RSFX services ---"
    systemctl stop retrostation-fx.service 2>/dev/null || true
    systemctl disable retrostation-fx.service 2>/dev/null || true
    systemctl stop rsfx.service 2>/dev/null || true
    systemctl disable rsfx.service 2>/dev/null || true
    systemctl stop retrostation-fx-etv-yaml-owner.socket 2>/dev/null || true
    systemctl disable retrostation-fx-etv-yaml-owner.socket 2>/dev/null || true

    rm -f -- "$SERVICE" "$LEGACY_SERVICE"
    rm -f -- "$ETV_OWNER_SERVICE" "$ETV_OWNER_SOCKET"
    rm -rf -- /etc/systemd/system/retrostation-fx.service.d /etc/systemd/system/rsfx.service.d
    systemctl daemon-reload
    systemctl reset-failed retrostation-fx.service rsfx.service 2>/dev/null || true
}

purge_managed_yaml() {
    local script_dir="$DEFAULT_ETV_SCRIPT_DIR" db="$STATE_ROOT/rsfx.db" removed=0
    local configured
    configured="$(read_env_value RSFX_ETV_SCRIPT_DIR "$ENV_FILE" 2>/dev/null || true)"
    [ -n "$configured" ] && script_dir="$configured"

    if [ ! -d "$script_dir" ]; then
        echo "ErsatzTV Script Graphics directory not present; no managed YAML removed."
        remove_etv_script_dir_access "$script_dir" "$SERVICE_USER"
        return 0
    fi

    echo "--- Remove positively identified RSFX-managed ErsatzTV YAML ---"
    echo "Script Graphics directory: $script_dir"

    # Preferred source: persisted Style inventory. Query only the managed YAML
    # filenames; never print configuration or secret values.
    if [ -f "$db" ] && command -v sqlite3 >/dev/null 2>&1; then
        while IFS= read -r managed_path; do
            [ -n "$managed_path" ] || continue
            filename="${managed_path##*/}"
            case "$filename" in
                *..*)
                    echo "WARNING: Ignoring unsafe managed YAML filename from state: $filename" >&2
                    continue
                    ;;
            esac
            case "$filename" in
                rsfx-*.yml|rsfx-*.yaml)
                    if [ -f "$script_dir/$filename" ] && [ ! -L "$script_dir/$filename" ]; then
                        rm -f -- "$script_dir/$filename"
                        echo "Removed managed YAML: $filename"
                        removed=1
                    fi
                    ;;
            esac
        done < <(sqlite3 -noheader "$db" "SELECT yaml_path FROM styles WHERE manage_ersatztv_yaml = 1 AND yaml_path IS NOT NULL;" 2>/dev/null || true)
    fi

    # Safe fallback for current generated files: require both the narrow RSFX
    # filename prefix and an RSFX marker in the file contents. This avoids
    # deleting unrelated YAML based on filename alone.
    while IFS= read -r -d '' file; do
        [ ! -L "$file" ] || continue
        if grep -Eq 'RetroStation FX|/opt/rsfx/|rsfx-etv-adapter\.py' "$file" 2>/dev/null; then
            rm -f -- "$file"
            echo "Removed managed YAML: $(basename "$file")"
            removed=1
        fi
    done < <(find "$script_dir" -maxdepth 1 -type f \( -name 'rsfx-*.yml' -o -name 'rsfx-*.yaml' \) -print0 2>/dev/null)

    remove_etv_script_dir_access "$script_dir" "$SERVICE_USER"

    if [ "$removed" -eq 0 ]; then echo "No positively identified RSFX-managed YAML files found."; fi
}

uninstall_rsfx() {
    echo "============================================================"
    if [ "$PURGE" -eq 1 ]; then
        echo " RetroStation FX ${VERSION} PURGE"
    else
        echo " RetroStation FX ${VERSION} UNINSTALL"
    fi
    echo "============================================================"
    echo

    if [ "$PURGE" -eq 1 ]; then
        echo "Application/service will be removed."
        echo "Configuration and persistent state will be removed."
        echo "RSFX-managed ErsatzTV Script Graphics YAML will be removed when positively identified."
        echo "Backups under $BACKUP_ROOT will be retained."
    else
        echo "Application/service will be removed."
        echo "Configuration will be preserved: $CONFIG_ROOT"
        echo "Persistent state will be preserved: $STATE_ROOT"
        echo "Managed ErsatzTV YAML will be preserved."
    fi
    echo

    stop_remove_services

    if [ "$PURGE" -eq 1 ]; then
        # YAML discovery must occur before persistent configuration/state are deleted.
        purge_managed_yaml
    fi

    echo "--- Remove installed application ---"
    if [ -e "$INSTALL_ROOT" ] || [ -L "$INSTALL_ROOT" ]; then safe_rm_tree "$INSTALL_ROOT" "/opt/rsfx"; else echo "$INSTALL_ROOT already absent."; fi

    if [ "$PURGE" -eq 1 ]; then
        echo "--- Remove persistent RSFX configuration/state ---"
        if [ -e "$CONFIG_ROOT" ] || [ -L "$CONFIG_ROOT" ]; then safe_rm_tree "$CONFIG_ROOT" "/etc/retrostation-fx"; fi
        if [ -e "$STATE_ROOT" ] || [ -L "$STATE_ROOT" ]; then safe_rm_tree "$STATE_ROOT" "/var/lib/retrostation-fx"; fi
    fi

    echo
    echo "============================================================"
    if [ "$PURGE" -eq 1 ]; then
        echo " RetroStation FX purge complete"
        echo " Persistent configuration/state: removed"
        echo " Backups: retained at $BACKUP_ROOT"
        echo
        echo " If managed Script Graphics YAML was removed, restart ErsatzTV"
        echo " so stale Script Graphics entries are removed from ErsatzTV."
    else
        echo " RetroStation FX uninstall complete"
        echo " Persistent configuration/state: preserved"
        echo " Reinstall with: sudo ./retrostation_fx_linux.sh install"
    fi
    echo "============================================================"
}

if [ "$ACTION" = "uninstall" ]; then
    uninstall_rsfx
    exit 0
fi

ensure_permission_dependencies || exit 1
detect_ersatztv_identity || exit 1

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$BACKUP_ROOT/install-${VERSION}-${STAMP}"

echo "============================================================"
echo " RetroStation FX ${VERSION} Installer"
echo "============================================================"
echo

rollback() {
    rc=$?
    echo
    echo "============================================================"
    echo " INSTALL FAILED"
    echo "============================================================"
    echo "Backup retained at: $BACKUP"
    exit "$rc"
}
trap rollback ERR

echo "--- Detect existing installation ---"
if [ -d "$INSTALL_ROOT" ]; then MODE="upgrade"; else MODE="install"; fi
echo "Mode: $MODE"

echo
echo "--- Create backup ---"
mkdir -p "$BACKUP"
if [ -d "$INSTALL_ROOT" ]; then
    mkdir -p "$BACKUP/opt"
    tar --exclude='venv' --exclude='__pycache__' --exclude='*.pyc' --exclude='backups' -C /opt -cpf "$BACKUP/opt/rsfx.tar" rsfx
fi
if [ -d "$CONFIG_ROOT" ]; then cp -a "$CONFIG_ROOT" "$BACKUP/etc-retrostation-fx"; fi
if [ -f "$SERVICE" ]; then cp -a "$SERVICE" "$BACKUP/retrostation-fx.service"; fi
if [ -f "$STATE_ROOT/rsfx.db" ]; then
    mkdir -p "$BACKUP/state"
    if command -v sqlite3 >/dev/null 2>&1; then sqlite3 "$STATE_ROOT/rsfx.db" ".backup '$BACKUP/state/rsfx.db'"; else cp -a "$STATE_ROOT/rsfx.db" "$BACKUP/state/rsfx.db"; fi
fi
echo "Backup: $BACKUP"

echo
echo "--- Stop RSFX services ---"
systemctl stop retrostation-fx.service 2>/dev/null || true
systemctl stop retrostation-fx-etv-yaml-owner.socket 2>/dev/null || true
systemctl disable rsfx.service 2>/dev/null || true
systemctl stop rsfx.service 2>/dev/null || true

echo
echo "--- Preserve persistent state ---"
mkdir -p "$STATE_ROOT" "$CONFIG_ROOT" "$BACKUP_ROOT"

echo
echo "--- Install application files ---"
mkdir -p "$INSTALL_ROOT/rsfx/static" "$INSTALL_ROOT/adapter" "$INSTALL_ROOT/tools"
find "$INSTALL_ROOT/rsfx" -maxdepth 1 -type f -name '*.py' -delete 2>/dev/null || true
rm -rf "$INSTALL_ROOT/rsfx/__pycache__" "$INSTALL_ROOT/adapter/__pycache__" "$INSTALL_ROOT/tools/__pycache__"
install -m 0644 "$APP_SOURCE"/rsfx/*.py "$INSTALL_ROOT/rsfx/"
install -m 0644 "$APP_SOURCE/rsfx/static/index.html" "$APP_SOURCE/rsfx/static/app.js" "$APP_SOURCE/rsfx/static/style.css" "$INSTALL_ROOT/rsfx/static/"
install -m 0755 "$APP_SOURCE/adapter/rsfx-etv-adapter.py" "$INSTALL_ROOT/adapter/rsfx-etv-adapter.py"
if [ -f "$APP_SOURCE/tools/selftest.py" ]; then install -m 0755 "$APP_SOURCE/tools/selftest.py" "$INSTALL_ROOT/tools/selftest.py"; fi
install -m 0755 "$APP_SOURCE/tools/etv_yaml_owner.py" "$INSTALL_ROOT/tools/etv_yaml_owner.py"
install -m 0644 "$APP_SOURCE/requirements.txt" "$INSTALL_ROOT/requirements.txt"
install -m 0644 "$APP_SOURCE/requirements.lock" "$INSTALL_ROOT/requirements.lock"
install -m 0644 "$APP_SOURCE/VERSION" "$INSTALL_ROOT/VERSION"

echo
echo "--- Rebuild Python virtual environment ---"
rm -rf "$INSTALL_ROOT/venv"
python3 -m venv "$INSTALL_ROOT/venv"
"$INSTALL_ROOT/venv/bin/python" -m pip install --disable-pip-version-check --require-hashes -r "$INSTALL_ROOT/requirements.lock"

echo
echo "--- Install / migrate configuration ---"
ETV_UID="$(getent passwd "$ETV_USER" | cut -d: -f3)"
ETV_GID="$(getent group "$ETV_GROUP" | cut -d: -f3)"
PREVIOUS_BIND_HOST="$(read_env_value RSFX_BIND_HOST "$ENV_FILE" 2>/dev/null || true)"
if [ ! -f "$ENV_FILE" ]; then
    install -m 0600 "$ENV_EXAMPLE" "$ENV_FILE"
    echo "Created new: $ENV_FILE"
else
    echo "Preserved existing values in: $ENV_FILE"
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in ''|'#'*) continue ;; esac
        key="${line%%=*}"
        if ! grep -q "^${key}=" "$ENV_FILE"; then printf '%s\n' "$line" >> "$ENV_FILE"; echo "Added configuration key: $key"; fi
    done < "$ENV_EXAMPLE"
    chmod 0600 "$ENV_FILE"
fi
set_env_value RSFX_ETV_OWNER_UID "$ETV_UID"
set_env_value RSFX_ETV_OWNER_GID "$ETV_GID"

RSFX_PORT="$(read_env_value RSFX_PORT "$ENV_FILE" 2>/dev/null || echo 5055)"
WILDCARD_BIND=0
case "$PREVIOUS_BIND_HOST" in
    0.0.0.0|::)
        WILDCARD_BIND=1
        set_env_value RSFX_BIND_HOST "127.0.0.1"
        echo "Migrated the existing wildcard bind to loopback for safety."
        ;;
esac

if [ "$LOCAL_ONLY" -eq 1 ] ||
    [ -z "$PREVIOUS_BIND_HOST" ] ||
    [ "$PREVIOUS_BIND_HOST" = "127.0.0.1" ] ||
    [ "$WILDCARD_BIND" -eq 1 ]; then
    DETECTED_LAN_IPV4=""
    if [ "$LOCAL_ONLY" -eq 0 ]; then
        DETECTED_LAN_IPV4="$(detect_lan_ipv4 || true)"
    fi
    choose_management_bind "$DETECTED_LAN_IPV4" "$RSFX_PORT" "$LOCAL_ONLY" || exit 1
fi

RSFX_BIND_HOST="$(read_env_value RSFX_BIND_HOST "$ENV_FILE" 2>/dev/null || echo 127.0.0.1)"
set_env_value RSFX_BIND_HOST "$RSFX_BIND_HOST"
RSFX_PORT="$(read_env_value RSFX_PORT "$ENV_FILE" 2>/dev/null || echo 5055)"
RSFX_PUBLIC_URL="$(read_env_value RSFX_PUBLIC_URL "$ENV_FILE" 2>/dev/null || true)"
URL_BIND_HOST="$RSFX_BIND_HOST"
if [[ "$URL_BIND_HOST" == *:* && "$URL_BIND_HOST" != \[*\] ]]; then URL_BIND_HOST="[$URL_BIND_HOST]"; fi
case "$RSFX_PUBLIC_URL" in
    "http://127.0.0.1:5055"|"http://127.0.0.1:$RSFX_PORT")
        set_env_value RSFX_PUBLIC_URL "http://${URL_BIND_HOST}:${RSFX_PORT}"
        ;;
esac

if [ "$LOCAL_ONLY" -eq 1 ]; then
    set_env_value RSFX_PUBLIC_URL "http://127.0.0.1:${RSFX_PORT}"
elif [ "$RSFX_BIND_HOST" = "127.0.0.1" ] && [ "$RSFX_PUBLIC_URL" != "http://127.0.0.1:$RSFX_PORT" ]; then
    case "$RSFX_PUBLIC_URL" in
        "http://127.0.0.1:5055")
            set_env_value RSFX_PUBLIC_URL "http://127.0.0.1:${RSFX_PORT}"
            ;;
    esac
fi

echo
echo "--- Configure dedicated service account and filesystem access ---"
ensure_service_account
configure_service_filesystem_access

HEALTH_HOST="$RSFX_BIND_HOST"
case "$HEALTH_HOST" in
    0.0.0.0|'') HEALTH_HOST="127.0.0.1" ;;
    ::) HEALTH_HOST="::1" ;;
esac
if [[ "$HEALTH_HOST" == *:* && "$HEALTH_HOST" != \[*\] ]]; then HEALTH_HOST="[$HEALTH_HOST]"; fi
HEALTH_URL="http://${HEALTH_HOST}:${RSFX_PORT}"

echo
echo "--- Install systemd unit ---"
install -m 0644 "$SCRIPT_DIR/systemd/retrostation-fx.service" "$SERVICE"
install -m 0644 "$SCRIPT_DIR/systemd/retrostation-fx-etv-yaml-owner@.service" "$ETV_OWNER_SERVICE"
install -m 0644 "$SCRIPT_DIR/systemd/retrostation-fx-etv-yaml-owner.socket" "$ETV_OWNER_SOCKET"
systemctl daemon-reload
systemctl enable --now retrostation-fx-etv-yaml-owner.socket
systemctl enable retrostation-fx.service
systemctl start retrostation-fx.service

echo
echo "--- Wait for health endpoint ---"
HEALTH_OK=0
for i in $(seq 1 20); do
    if curl -fsS "$HEALTH_URL/v1/health" >/tmp/rsfx-install-health.json 2>/dev/null; then HEALTH_OK=1; break; fi
    sleep 1
done
if [ "$HEALTH_OK" -ne 1 ]; then echo "RSFX did not become healthy."; journalctl -u retrostation-fx.service -n 100 --no-pager; exit 1; fi
cat /tmp/rsfx-install-health.json
echo

echo
echo "--- Verify installed version ---"
INSTALLED_VERSION="$(HEALTH_URL="$HEALTH_URL" "$INSTALL_ROOT/venv/bin/python" - <<'PY_VERSION'
import json
import urllib.request
import os
with urllib.request.urlopen(os.environ["HEALTH_URL"] + "/v1/health", timeout=5) as response:
    data = json.load(response)
print(data["version"])
PY_VERSION
)"
if [ "$INSTALLED_VERSION" != "$VERSION" ]; then echo "Expected: $VERSION"; echo "Found:    $INSTALLED_VERSION"; exit 1; fi

echo
echo "--- Run installed RSFX selftest ---"
if [ -x "$INSTALL_ROOT/tools/selftest.py" ]; then
    SELFTEST_STATE="$(mktemp -d "$STATE_ROOT/.selftest.XXXXXX")"
    chown "${SERVICE_USER}:${SERVICE_GROUP}" "$SELFTEST_STATE"
    chmod 0750 "$SELFTEST_STATE"
    if runuser -u "$SERVICE_USER" -- env \
        PYTHONPATH="$INSTALL_ROOT" \
        RSFX_DATABASE="$SELFTEST_STATE/rsfx.db" \
        "$INSTALL_ROOT/venv/bin/python" "$INSTALL_ROOT/tools/selftest.py"; then
        rm -rf -- "$SELFTEST_STATE"
    else
        rm -rf -- "$SELFTEST_STATE"
        exit 1
    fi
fi

echo
echo "--- Verify legacy service state ---"
if systemctl is-active --quiet rsfx.service 2>/dev/null; then echo "ERROR: legacy rsfx.service is still active"; exit 1; fi

echo
echo "============================================================"
echo " RetroStation FX ${VERSION} installed successfully"
echo "============================================================"
echo "Mode:              $MODE"
echo "Application:       $INSTALL_ROOT"
echo "Configuration:     $CONFIG_ROOT"
echo "Persistent state:  $STATE_ROOT"
echo "Backup:            $BACKUP"
echo "Service:           retrostation-fx.service"
echo "Web UI:            $HEALTH_URL/"
echo "============================================================"
