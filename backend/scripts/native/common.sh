#!/usr/bin/env bash
# Shared native runtime. Source this file; never print the loaded environment.
set +x
set -euo pipefail
umask 077

NATIVE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC2034  # read by setup.sh and start.sh, which source this file
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
    # Setup writes no key. The path is always exported, so a key created later is read without a
    # restart; a missing key file (or a symlink) means sync is off. The path is never printed.
    export SYNC_KEY_FILE="$MAESTRO_HOME/sync-key"
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
    # shellcheck source=/dev/null
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

native_require_ps() {
    command -v ps >/dev/null 2>&1 \
        || native_error 'This system has no /proc and no ps command; install procps.'
}

native_inspect_pid() {
    # Sets NATIVE_PID_STATE and NATIVE_PID_ARGS from /proc, else ps; fails if the pid is gone.
    NATIVE_PID_STATE="" NATIVE_PID_ARGS=""
    if [[ -d "/proc/$NATIVE_PID" ]]; then
        local key value
        while read -r key value _; do
            if [[ "$key" == State: ]]; then NATIVE_PID_STATE="$value"; break; fi
        done < "/proc/$NATIVE_PID/status" 2>/dev/null || return 1
        NATIVE_PID_ARGS="$(tr '\0' ' ' < "/proc/$NATIVE_PID/cmdline" 2>/dev/null)" || return 1
    else
        native_require_ps
        NATIVE_PID_STATE="$(ps -o stat= -p "$NATIVE_PID" 2>/dev/null)" || return 1
        NATIVE_PID_ARGS="$(ps -o args= -p "$NATIVE_PID" 2>/dev/null)" || return 1
        NATIVE_PID_STATE="${NATIVE_PID_STATE//[[:space:]]/}"
    fi
}

native_pid_alive() {
    kill -0 "$NATIVE_PID" 2>/dev/null || return 1
    native_inspect_pid || return 1
    [[ -n "$NATIVE_PID_STATE" && "$NATIVE_PID_STATE" != Z* ]]
}

native_pid_ours() {
    # After a reboot a pidfile can name an unrelated process; only our uvicorn counts.
    native_pid_alive || return 1
    local home
    home="$(cd -- "$MAESTRO_HOME" 2>/dev/null && pwd)" || home="$MAESTRO_HOME"
    [[ "$NATIVE_PID_ARGS" == "$home/venv/bin/python -m uvicorn app.main:app"* ]]
}

native_running() {
    native_read_pid || return 1
    native_pid_ours && return 0
    rm -f -- "$MAESTRO_HOME/backend.pid" 2>/dev/null || true  # stale: never signal it
    return 1
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

native_terminate() {
    # TERM the group of a pid the caller has proven is ours, then KILL after ten seconds.
    native_signal TERM
    local deadline=$((SECONDS + 10))
    while native_group_alive || native_pid_alive; do
        (( SECONDS < deadline )) || break
        sleep 0.2
    done
    native_signal KILL
}

native_remove_pidfile() {
    rm -f -- "$MAESTRO_HOME/backend.pid" 2>/dev/null \
        || native_error 'Cannot remove the native pidfile.'
}

native_abort_launch() {
    # start.sh's own child: trusted even before it has exec'd into uvicorn.
    native_terminate
    native_remove_pidfile
}

native_stop() {
    if native_read_pid && native_pid_ours; then
        native_terminate
    fi
    native_remove_pidfile
}

native_paused_since() {
    # Prints when stop.sh paused the watchdog; fails when no maintenance marker exists.
    local marker="$MAESTRO_HOME/maintenance" stamp=""
    [[ -f "$marker" && ! -L "$marker" ]] || return 1
    read -r stamp < "$marker" 2>/dev/null || true
    # Only a well-formed UTC time is ever printed; anything else is not echoed.
    [[ "$stamp" =~ ^[0-9]{4}(-[0-9]{2}){2}T[0-9]{2}(:[0-9]{2}){2}Z$ ]] || stamp='an unknown time'
    printf '%s\n' "$stamp"
}

native_set_pause() {
    local marker="$MAESTRO_HOME/maintenance"
    rm -f -- "$marker" 2>/dev/null || native_error 'Cannot write the maintenance marker.'
    date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null > "$marker" \
        || native_error 'Cannot write the maintenance marker.'
    chmod 600 "$marker" 2>/dev/null || native_error 'Cannot secure the maintenance marker.'
}

native_clear_pause() {
    rm -f -- "$MAESTRO_HOME/maintenance" 2>/dev/null \
        || native_error 'Cannot remove the maintenance marker.'
}

native_free_port() {
    "$NATIVE_PYTHON" - "$MAESTRO_PORT" >/dev/null 2>&1 <<'PY'
import socket
import sys

try:
    with socket.socket() as probe:
        # A just-stopped backend leaves TIME_WAIT sockets; a live listener still fails.
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
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

native_post() {
    # POST a JSON body ($2) to the loopback backend. Prints the HTTP status, then the response
    # body (at most 64 KiB); fails without printing when nothing answers. A round can be long.
    "$NATIVE_PYTHON" - "$MAESTRO_PORT" "$1" "$2" 2>/dev/null <<'PY'
import sys
import urllib.error
import urllib.request

port, path, body = sys.argv[1:4]
# Loopback must bypass inherited proxy settings. Errors never print what was sent.
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
request = urllib.request.Request(
    f"http://127.0.0.1:{port}{path}", data=body.encode(),
    headers={"Content-Type": "application/json"}, method="POST")
try:
    with opener.open(request, timeout=900) as response:
        status, reply = response.status, response.read(65536)
except urllib.error.HTTPError as refusal:
    status, reply = refusal.code, refusal.read(65536)
except (OSError, ValueError):
    raise SystemExit(1) from None
sys.stdout.write(f"{status}\n{reply.decode('utf-8', 'replace')}")
PY
}

native_wait_for_health() {
    local deadline=$((SECONDS + 30))
    while (( SECONDS < deadline )); do
        native_pid_alive || return 1  # our own launch: not yet exec'd uvicorn is fine
        if native_get /health >/dev/null; then
            native_pid_alive
            return
        fi
        sleep 0.2
    done
    return 1
}
