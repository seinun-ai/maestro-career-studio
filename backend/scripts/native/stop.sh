#!/usr/bin/env bash
# TERM the backend and helpers, then KILL after ten seconds if needed.
set +x
set -euo pipefail
umask 077
# shellcheck source=common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"

native_stop
printf '%s\n' 'Native backend stopped.'
