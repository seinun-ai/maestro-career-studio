#!/usr/bin/env bash
# Run one sync round on the always-on copy: ask its local backend to talk to the laptop.
# Cron-safe: exits 0 on success, on a skip (not set up, backoff, a round already running) and
# while stop.sh has paused maintenance; exits 1 on any other failure. Never prints the key.
#   sync.sh                                  a plain round
#   sync.sh --pair [--accept-profile-overwrite]   the first round, at the keyboard
set +x
set -euo pipefail
umask 077
# shellcheck source=common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"

usage='Usage: sync.sh [--pair [--accept-profile-overwrite]]'
pair=false accept=false
for arg in "$@"; do
    case "$arg" in
        --pair) pair=true ;;
        --accept-profile-overwrite) accept=true ;;
        *) native_error "$usage" ;;
    esac
done
[[ "$accept" == false || "$pair" == true ]] || native_error "$usage"

native_private_home
if paused_since="$(native_paused_since)"; then
    printf '%s\n' "Maestro is paused for maintenance since $paused_since; not syncing. Run start.sh to resume."
    exit 0
fi
native_load_env
[[ -x "$NATIVE_PYTHON" ]] || native_error 'Native venv is missing; run setup.sh.'
# A person pairing wants the round now, even inside a backoff window; cron never forces.
body="$(printf '{"force": %s, "pair": %s, "accept_profile_overwrite": %s}' "$pair" "$pair" "$accept")"
reply="$(native_post /api/sync/round "$body")" \
    || native_error 'Native backend is not reachable; check start.sh and health.sh.'
status="${reply%%$'\n'*}"
printf '%s' "${reply#*$'\n'}" | "$NATIVE_PYTHON" -c '
import json
import sys

status = int(sys.argv[1])


def line(text):
    return " ".join(str(text).split())[:300]


def finish(code, text):
    print(text, file=sys.stderr if code else sys.stdout)
    raise SystemExit(code)


try:
    body = json.loads(sys.stdin.read())
except ValueError:
    body = None
if status == 409:
    finish(0, "A sync is already running; nothing to do.")
if status == 404:
    finish(1, "This copy is not set up as the always-on copy (needs a key file and SYNC_REMOTE_URL).")
if status == 403:
    finish(1, "The backend refused the request.")
if status != 200:
    finish(1, f"The backend answered {status}.")
if not isinstance(body, dict) or not isinstance(body.get("ok"), bool):
    finish(1, "The sync answer was unreadable.")
summary = json.dumps({key: body[key] for key in ("ok", "steps") if key in body}, sort_keys=True)
if body["ok"]:
    print("Synced.")
    print(summary)
    raise SystemExit(0)
if isinstance(body.get("skipped"), str):
    finish(0, "Skipped: " + line(body["skipped"]))
print(summary)
finish(1, "Sync failed: " + line(body["error"]) if isinstance(body.get("error"), str) else "Sync failed.")
' "$status"
