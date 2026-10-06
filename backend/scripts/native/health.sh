#!/usr/bin/env bash
# Print only a validated memory readout; usable by a supervisor.
set +x
set -euo pipefail
umask 077
# shellcheck source=common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"

if ! native_running; then
    if paused_since="$(native_paused_since)"; then
        native_error "Native backend is paused for maintenance since $paused_since."
    fi
    native_error 'Native backend is not running.'
fi
native_load_env
native_get /health/memory || native_error 'Native backend is unhealthy.'
