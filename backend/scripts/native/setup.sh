#!/usr/bin/env bash
# Install just the backend and its MCP extra; rerunning preserves local keys.
set +x
set -euo pipefail
umask 077
# shellcheck source=common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"

native_prepare_home
native_load_env
if [[ ! -d "$MAESTRO_HOME/venv" ]]; then
    installer_python="${PYTHON:-python3.12}"
    "$installer_python" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' \
        >/dev/null 2>&1 || native_error 'Setup needs Python 3.12+; set PYTHON or install python3.12.'
    "$installer_python" -m venv "$MAESTRO_HOME/venv" >/dev/null 2>&1 \
        || native_error 'Cannot create the native venv; check Python venv support.'
fi
"$NATIVE_PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' \
    >/dev/null 2>&1 || native_error 'The native venv needs a working Python 3.12+.'

# Installer/migration output can contain authenticated URLs or env values.
"$NATIVE_PYTHON" -m pip install -e "$NATIVE_BACKEND[mcp]" >/dev/null 2>&1 \
    || native_error 'Native dependency installation failed; check package access locally.'
cd -- "$NATIVE_BACKEND"
"$NATIVE_PYTHON" -m alembic upgrade head >/dev/null 2>&1 \
    || native_error 'Native database migration failed; inspect the database locally.'
printf '%s\n' 'Native backend setup complete.'
