#!/usr/bin/env bash
# Background one loopback worker, with a disk-backed model cache.
set +x
set -euo pipefail
umask 077
# shellcheck source=common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"

native_private_home
if native_running; then
    native_error 'Native backend is already running.'
fi
native_load_env
[[ -x "$NATIVE_PYTHON" ]] || native_error 'Native venv is missing; run setup.sh.'
native_free_port || native_error 'Native backend port is unavailable; check MAESTRO_PORT locally.'
cd -- "$NATIVE_BACKEND"
: > "$MAESTRO_HOME/logs/backend.log"
chmod 600 "$MAESTRO_HOME/logs/backend.log"
# exec keeps the pidfile's PID; the session also owns any spawned helpers.
nohup "$NATIVE_PYTHON" -c \
    'import os, sys; os.setsid(); os.execv(sys.executable, [sys.executable, "-m", "uvicorn", *sys.argv[1:]])' \
    app.main:app --host 127.0.0.1 --port "$MAESTRO_PORT" --workers 1 \
    > "$MAESTRO_HOME/logs/backend.log" 2>&1 < /dev/null &
NATIVE_PID=$!
trap 'native_stop; exit 1' INT TERM
if ! printf '%s\n' "$NATIVE_PID" > "$MAESTRO_HOME/backend.pid"; then
    native_signal KILL
    native_error 'Cannot create the native pidfile.'
fi
if ! native_wait_for_health; then
    native_stop
    native_error 'Native backend did not become healthy within 30 seconds.'
fi
trap - INT TERM
printf '%s\n' 'Native backend started.'
