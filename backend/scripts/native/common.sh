#!/usr/bin/env bash
# Shared native runtime. Source this file; never print the loaded environment.
set +x
set -euo pipefail
umask 077

NATIVE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
NATIVE_BACKEND="$(cd -- "$NATIVE_DIR/../.." && pwd)"
MAESTRO_HOME="${MAESTRO_HOME:-$HOME/maestro}"
case "$MAESTRO_HOME" in
    /*) ;;
    *) MAESTRO_HOME="$PWD/$MAESTRO_HOME" ;;
esac

native_error() {
    printf '%s\n' "$1" >&2
    exit 1
}

native_private_home() {
    [[ -d "$MAESTRO_HOME" && ! -L "$MAESTRO_HOME" ]] \
        || native_error 'Native home is missing or is a symlink; run setup.sh.'
    chmod 700 "$MAESTRO_HOME" 2>/dev/null \
        || native_error 'Cannot secure the native home.'
    MAESTRO_HOME="$(cd -- "$MAESTRO_HOME" && pwd)"
}

native_prepare_home() {
    mkdir -p -- "$MAESTRO_HOME" 2>/dev/null \
        || native_error 'Cannot create the native home.'
    native_private_home
    mkdir -p -- "$MAESTRO_HOME"/{data,applications,settings,base_resumes,kb_documents,logs,exports,fastembed_cache} \
        2>/dev/null || native_error 'Cannot create the native directories.'
    if [[ ! -e "$MAESTRO_HOME/maestro.env" && ! -L "$MAESTRO_HOME/maestro.env" ]]; then
        cp -- "$NATIVE_DIR/maestro.env.example" "$MAESTRO_HOME/maestro.env" 2>/dev/null \
            || native_error 'Cannot create maestro.env.'
    fi
}

native_export_env() {
    export MAESTRO_HOME APP_ROOT="$MAESTRO_HOME"
    export DATA_DIR="$MAESTRO_HOME/data" APPLICATIONS_DIR="$MAESTRO_HOME/applications"
    export SETTINGS_DIR="$MAESTRO_HOME/settings" BASE_RESUMES_DIR="$MAESTRO_HOME/base_resumes"
    export KB_DOCUMENTS_DIR="$MAESTRO_HOME/kb_documents" LOGS_DIR="$MAESTRO_HOME/logs"
    export EXPORTS_DIR="$MAESTRO_HOME/exports"
    export DATABASE_URL="sqlite:///$MAESTRO_HOME/data/maestro_cs.sqlite3"
    export MALLOC_ARENA_MAX=2 EMBEDDINGS_OUT_OF_PROCESS=1
    export ALLOWED_HOSTS=localhost,127.0.0.1
    export FASTEMBED_CACHE_PATH="$MAESTRO_HOME/fastembed_cache"
    unset TEST_DATABASE_URL
    NATIVE_PYTHON="$MAESTRO_HOME/venv/bin/python"
}

native_load_env() {
    native_private_home
    local home="$MAESTRO_HOME"
    [[ -f "$home/maestro.env" && ! -L "$home/maestro.env" ]] \
        || native_error 'maestro.env is missing or is a symlink; run setup.sh.'
    chmod 600 "$home/maestro.env" 2>/dev/null \
        || native_error 'Cannot secure maestro.env.'
    "$BASH" -n "$home/maestro.env" >/dev/null 2>&1 \
        || native_error 'Cannot load maestro.env; check its shell syntax locally.'
    set -a
    # Local, trusted bash assignments. Suppress even syntax-error diagnostics.
    if ! source "$home/maestro.env" >/dev/null 2>&1; then
        set +a
        native_error 'Cannot load maestro.env; check its shell syntax locally.'
    fi
    set +a
    set +x
    MAESTRO_HOME="$home"
    native_export_env
    MAESTRO_PORT="${MAESTRO_PORT:-8001}"
    [[ "$MAESTRO_PORT" =~ ^[0-9]{1,5}$ ]] \
        || native_error 'MAESTRO_PORT must be a port number from 1 to 65535.'
    MAESTRO_PORT="$((10#$MAESTRO_PORT))"
    (( MAESTRO_PORT > 0 && MAESTRO_PORT <= 65535 )) \
        || native_error 'MAESTRO_PORT must be a port number from 1 to 65535.'
}

native_read_pid() {
    [[ -f "$MAESTRO_HOME/backend.pid" && ! -L "$MAESTRO_HOME/backend.pid" ]] || return 1
    NATIVE_PID="$(<"$MAESTRO_HOME/backend.pid")"
    [[ "$NATIVE_PID" =~ ^[1-9][0-9]{0,9}$ ]] || return 1
    (( NATIVE_PID > 1 && NATIVE_PID <= 2147483647 ))
}

native_pid_alive() {
    kill -0 "$NATIVE_PID" 2>/dev/null || return 1
    local state
    state="$(ps -o stat= -p "$NATIVE_PID" 2>/dev/null)" || return 1
    state="${state//[[:space:]]/}"
    [[ -n "$state" && "$state" != Z* ]]
}

native_running() {
    native_read_pid && native_pid_alive
}

native_group_alive() {
    # Ignore zombies: they have no resident model and cannot receive signals.
    ps -eo pgid=,stat= 2>/dev/null | awk -v group="$NATIVE_PID" \
        '$1 == group && $2 !~ /^Z/ { live = 1 } END { exit !live }'
}

native_signal() {
    # start.sh gives uvicorn its own session; include embedding/render helpers.
    kill "-$1" -- "-$NATIVE_PID" 2>/dev/null \
        || kill "-$1" "$NATIVE_PID" 2>/dev/null || true
}

native_stop() {
    if native_read_pid; then
        native_signal TERM
        local deadline=$((SECONDS + 10))
        while native_group_alive || native_pid_alive; do
            (( SECONDS < deadline )) || break
            sleep 0.2
        done
        native_signal KILL
    fi
    rm -f -- "$MAESTRO_HOME/backend.pid" 2>/dev/null \
        || native_error 'Cannot remove the native pidfile.'
}

native_free_port() {
    "$NATIVE_PYTHON" - "$MAESTRO_PORT" >/dev/null 2>&1 <<'PY'
import socket
import sys

try:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", int(sys.argv[1])))
except OSError:
    raise SystemExit(1) from None
PY
}

native_get() {
    "$NATIVE_PYTHON" - "$MAESTRO_PORT" "$1" 2>/dev/null <<'PY'
import json
import math
import sys
import urllib.request


def read_health(port, path):
    # Loopback must bypass inherited proxy settings. Errors never print a body.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f"http://127.0.0.1:{port}{path}", timeout=1) as response:
        if response.status != 200:
            raise ValueError("unhealthy")
        return json.loads(response.read(16384))


def valid_memory(body):
    if not isinstance(body, dict) or set(body) != {"rss_mb", "peak_mb", "platform"}:
        return False
    if body["platform"] not in ("linux", "darwin", "win32"):
        return False
    return all(type(body[key]) in (int, float) and math.isfinite(body[key]) and body[key] > 0
               for key in ("rss_mb", "peak_mb"))


try:
    path = sys.argv[2]
    body = read_health(sys.argv[1], path)
    if path == "/health":
        raise SystemExit(0 if body == {"status": "ok"} else 1)
    if not valid_memory(body):
        raise SystemExit(1)
    print(json.dumps(body, allow_nan=False))
except (OSError, ValueError, TypeError):
    raise SystemExit(1) from None
PY
}

native_wait_for_health() {
    local deadline=$((SECONDS + 30))
    while (( SECONDS < deadline )); do
        native_running || return 1
        if native_get /health >/dev/null; then
            native_running
            return
        fi
        sleep 0.2
    done
    return 1
}
