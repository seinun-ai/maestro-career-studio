#!/usr/bin/env bash
# Run one sync round on the always-on copy: ask its local backend to talk to the laptop.
# Cron-safe: exits 0 on ok or transient outcomes (backoff, busy, laptop unreachable) and
# while stop.sh has paused maintenance; exits 1 when a person must act or the local backend
# is unreachable, unreadable or not set up (404). Exits 3 when the round's wait ended and
# the round is still running here. Never prints the key.
#   sync.sh                                  a plain round
#   sync.sh --now                            a round now, past a backoff (not past the 30 s floor)
#   sync.sh --pair [--code <code>] [--accept-profile-overwrite]
#       the first round, at the keyboard. --code - reads the code from stdin.
set +x
set -euo pipefail
umask 077
# shellcheck source=common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"

usage='Usage: sync.sh [--now | --pair [--code <code>] [--accept-profile-overwrite]]'
pair=false accept=false now=false have_code=false code=''
args=("$@")
i=0
while [[ "$i" -lt ${#args[@]} ]]; do
    arg="${args[$i]}"
    case "$arg" in
        --now) now=true ;;
        --pair) pair=true ;;
        --accept-profile-overwrite) accept=true ;;
        --code)
            i=$((i + 1))
            [[ "$i" -lt ${#args[@]} ]] || native_error "$usage"
            code="${args[$i]}"
            have_code=true
            ;;
        *) native_error "$usage" ;;
    esac
    i=$((i + 1))
done
[[ "$accept" == false || "$pair" == true ]] || native_error "$usage"
[[ "$now" == false || "$pair" == false ]] || native_error "$usage"
[[ "$have_code" == false || "$pair" == true ]] || native_error "$usage"

native_private_home
if paused_since="$(native_paused_since)"; then
    printf '%s\n' "Maestro is paused for maintenance since $paused_since; not syncing. Run start.sh to resume."
    exit 0
fi
native_load_env
[[ -x "$NATIVE_PYTHON" ]] || native_error 'Native venv is missing; run setup.sh.'
if [[ "$pair" == true && ! -e "$SYNC_KEY_FILE" && ! -L "$SYNC_KEY_FILE" ]]; then
    [[ "$have_code" == true ]] || native_error "$usage"
    if [[ "$code" == "-" ]]; then
        IFS= read -r code || native_error "$usage"
    fi
    body="$(printf '%s' "$code" | "$NATIVE_PYTHON" -c 'import json,sys; sys.stdout.write(json.dumps({"code": sys.stdin.read()}))')"
    enrollment="$(printf '%s' "$body" | native_post /api/sync-setup/enroll)" \
        || native_error 'Native backend is not reachable; check start.sh and health.sh.'
    enrollment_status="${enrollment%%$'\n'*}"
    printf '%s' "${enrollment#*$'\n'}" | "$NATIVE_PYTHON" -c '
import json
import sys

try:
    body = json.loads(sys.stdin.read())
except ValueError:
    body = None
status = int(sys.argv[1])
if status == 200 and isinstance(body, dict) and body.get("ok") is True:
    raise SystemExit(0)
if isinstance(body, dict) and body.get("outcome") in ("needs_person", "transient"):
    # The local backend returns fixed sentences, never the laptop body or a key.
    text = body.get("detail")
    if isinstance(text, str):
        print(" ".join(text.split())[:300], file=sys.stderr)
        raise SystemExit(1)
print("This copy could not fetch the sync key. Show a pairing code on your laptop and try again.", file=sys.stderr)
raise SystemExit(1)
' "$enrollment_status" || exit 1
fi
# A person pairing or asking for --now wants the round now, even inside a backoff window; cron never forces.
force="$pair"
[[ "$now" == false ]] || force=true
body="$(printf '{"force": %s, "pair": %s, "accept_profile_overwrite": %s}' "$force" "$pair" "$accept")"
# An hour, not the 900 s every other native_post uses. The first pairing round pulls every
# page and can outlive that shorter wait; the backend keeps going after this script stops.
set +e
reply="$(printf '%s' "$body" | native_post /api/sync/round 3600)"
round_status=$?
set -e
if [[ "$round_status" -eq 28 ]]; then
    printf '%s\n' 'The round is still running on this machine. Check later with sync.sh --now; "A sync is already running" means it hasn'"'"'t finished yet.' >&2
    exit 3
fi
if [[ "$round_status" -ne 0 ]]; then
    native_error 'Native backend is not reachable; check start.sh and health.sh.'
fi
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
