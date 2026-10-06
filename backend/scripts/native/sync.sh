#!/usr/bin/env bash
# Run one sync round on the always-on copy: ask its local backend to talk to the laptop.
# Cron-safe: exits 0 on ok or transient outcomes (backoff, busy, laptop unreachable) and
# while stop.sh has paused maintenance; exits 1 when a person must act or the local backend
# is unreachable, unreadable or not set up (404). Never prints the key.
#   sync.sh                                  a plain round
#   sync.sh --now                            a round now, past a backoff (not past the 30 s floor)
#   sync.sh --pair [--accept-profile-overwrite]   the first round, at the keyboard
set +x
set -euo pipefail
umask 077
# shellcheck source=common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"

usage='Usage: sync.sh [--now | --pair [--accept-profile-overwrite]]'
pair=false accept=false now=false
for arg in "$@"; do
    case "$arg" in
        --now) now=true ;;
        --pair) pair=true ;;
        --accept-profile-overwrite) accept=true ;;
        *) native_error "$usage" ;;
    esac
done
[[ "$accept" == false || "$pair" == true ]] || native_error "$usage"
[[ "$now" == false || "$pair" == false ]] || native_error "$usage"

native_private_home
if paused_since="$(native_paused_since)"; then
    printf '%s\n' "Maestro is paused for maintenance since $paused_since; not syncing. Run start.sh to resume."
    exit 0
fi
native_load_env
[[ -x "$NATIVE_PYTHON" ]] || native_error 'Native venv is missing; run setup.sh.'
# A person pairing or asking for --now wants the round now, even inside a backoff window; cron never forces.
force="$pair"
[[ "$now" == false ]] || force=true
body="$(printf '{"force": %s, "pair": %s, "accept_profile_overwrite": %s}' "$force" "$pair" "$accept")"
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
if status == 404:
    finish(1, "This copy is not set up as the always-on copy (needs a key file and SYNC_REMOTE_URL).")
if status == 403:
    finish(1, "The backend refused the request.")
if status not in (200, 409):
    finish(1, f"The backend answered {status}.")
if not isinstance(body, dict) or body.get("outcome") not in ("ok", "transient", "needs_person"):
    finish(1, "The sync answer was unreadable.")
if status == 200 and not isinstance(body.get("ok"), bool):
    finish(1, "The sync answer was unreadable.")
outcome = body["outcome"]
code = int(outcome == "needs_person" or (status == 409 and outcome != "transient"))
summary = json.dumps({key: body[key] for key in ("ok", "steps") if key in body}, sort_keys=True)
if outcome == "ok" and code == 0:
    print("Synced.")
    print(summary)
    raise SystemExit(0)
if status == 200 and not isinstance(body.get("skipped"), str):
    print(summary)
transient = outcome == "transient"
for field, prefix in (("skipped", "Skipped: "),
                      ("error", "Sync didn\x27t run: " if transient else "Sync failed: "), ("detail", "")):
    if isinstance(body.get(field), str):
        suffix = " It will try again." if transient and field == "error" else ""
        finish(code, prefix + line(body[field]) + suffix)
finish(code, "Sync deferred." if outcome == "transient" else "Sync failed.")
' "$status"
