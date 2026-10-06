#!/usr/bin/env bash
# TERM the backend and helpers, then KILL after ten seconds if needed.
# By default also pause the watchdog (start.sh --watchdog); --no-pause skips that.
set +x
set -euo pipefail
umask 077
# shellcheck source=common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"

pause=1
for arg in "$@"; do
    case "$arg" in
        --no-pause) pause=0 ;;
        *) native_error 'Usage: stop.sh [--no-pause]' ;;
    esac
done

# Mark the pause first, so a watchdog tick during the stop cannot restart the backend.
paused=0
if (( pause )) && [[ -d "$MAESTRO_HOME" && ! -L "$MAESTRO_HOME" ]]; then
    native_set_pause
    paused=1
fi
native_stop
printf '%s\n' 'Native backend stopped.'
if (( paused )); then
    printf '%s\n' 'Watchdog paused for maintenance. Run start.sh to resume.'
fi
