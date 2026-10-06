#!/usr/bin/env bash
# Background one loopback worker, with a disk-backed model cache.
# --watchdog is for supervisors: it declines while stop.sh has paused maintenance.
set +x
set -euo pipefail
umask 077
# shellcheck source=common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"

watchdog=0
for arg in "$@"; do
    case "$arg" in
        --watchdog) watchdog=1 ;;
        *) native_error 'Usage: start.sh [--watchdog]' ;;
    esac
done

native_private_home
resume=0
if paused_since="$(native_paused_since)"; then
    if (( watchdog )); then
        printf '%s\n' "Maestro is paused for maintenance since $paused_since; not starting. Run start.sh to resume."
        exit 0
    fi
    resume=1  # a manual start resumes, once it owns the pidfile
fi
if native_running; then
    native_error 'Native backend is already running.'
fi
native_load_env
[[ -x "$NATIVE_PYTHON" ]] || native_error 'Native venv is missing; run setup.sh.'
native_free_port || native_error 'Native backend port is unavailable; check MAESTRO_PORT locally.'
cd -- "$NATIVE_BACKEND"
log="$MAESTRO_HOME/logs/backend.log"
# Keep the last run's log: a watchdog restart must not wipe the crash traceback.
if [[ -e "$log" || -L "$log" ]]; then
    mv -f -- "$log" "$log.1" 2>/dev/null || true
fi
: > "$log"
chmod 600 "$log"
# exec keeps the pidfile's PID; the session also owns any spawned helpers.
nohup "$NATIVE_PYTHON" -c \
    'import os, sys; os.setsid(); os.execv(sys.executable, [sys.executable, "-m", "uvicorn", *sys.argv[1:]])' \
    app.main:app --host 127.0.0.1 --port "$MAESTRO_PORT" --workers 1 \
    > "$log" 2>&1 < /dev/null &
NATIVE_PID=$!
trap 'native_abort_launch; exit 1' INT TERM
if ! printf '%s\n' "$NATIVE_PID" > "$MAESTRO_HOME/backend.pid"; then
    native_signal KILL
    native_error 'Cannot create the native pidfile.'
fi
if ! native_wait_for_health; then
    native_abort_launch
    native_error 'Native backend did not become healthy within 30 seconds.'
fi
# Only now: before the pidfile, a watchdog tick would start a second backend,
# and a resume that fails keeps the pause.
if (( resume )); then
    native_clear_pause
fi
trap - INT TERM
printf '%s\n' 'Native backend started.'
