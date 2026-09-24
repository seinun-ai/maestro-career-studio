#!/usr/bin/env bash
#
# Update an installed Maestro CS to the newest v* release.
#
# Why this exists: an install IS a git checkout. The unpacked extension loads
# from extension/ and the MCP venv sits over backend/, so checkout and images
# must move together. `docker compose pull` alone updates two surfaces of four.
# This also snapshots the SQLite database (data/maestro_cs.sqlite3) before the
# one irreversible step (migrations, which run themselves at backend boot) and
# reports .env drift without editing it.
#
#   ./scripts/update.sh            # SQLite snapshot → ff-to-tag → pull/build → up
#   ./scripts/update.sh --check    # report only; always exits 0
#   ./scripts/update.sh --force    # allow a dirty working tree
#   ./scripts/update.sh --help
#
# Nothing here edits .env. Report, never auto-edit, anything the user owns.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CANONICAL="seinun-ai/maestro-career-studio"

die() { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }
note() { printf '\033[36m→\033[0m %s\n' "$*"; }
ok()   { printf '\033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!\033[0m %s\n' "$*" >&2; }

usage() {
  sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

# Parse a KEY from $REPO/.env the way compose would: last uncommented assignment
# wins. Never read the shell environment — it will not have these.
env_get() {
  local key="$1"
  local default="${2:-}"
  local val=""
  if [ -f "$REPO/.env" ]; then
    val="$(grep -E "^[[:space:]]*${key}=" "$REPO/.env" | tail -n 1 | cut -d= -f2- | tr -d ' "'"'"'' || true)"
  fi
  printf '%s' "${val:-$default}"
}

compose() {
  docker compose --project-directory "$REPO" "$@"
}

is_pull_mode() {
  local registry="$1"
  case "$registry" in
    *.*|*/*) return 0 ;;
    *) return 1 ;;
  esac
}

warn_if_fork() {
  local origin
  origin="$(git -C "$REPO" remote get-url origin 2>/dev/null || true)"
  if [ -z "$origin" ]; then
    warn "no 'origin' remote — cannot fetch official tags"
    return 0
  fi
  case "$origin" in
    *"$CANONICAL"*) ;;
    *)
      warn "origin is $origin, not the canonical $CANONICAL — a fork pulls its own remote and never sees official tags"
      ;;
  esac
}

json_field() {
  local json="$1"
  local field="$2"
  if command -v python3 >/dev/null 2>&1; then
    printf '%s' "$json" | python3 -c 'import json,sys; print(json.load(sys.stdin).get(sys.argv[1]) or "")' "$field" 2>/dev/null || true
  else
    printf '%s' "$json" | sed -n "s/.*\"${field}\"[[:space:]]*:[[:space:]]*\"\\([^\"]*\\)\".*/\\1/p" | head -n 1
  fi
}

# Keys from an env file, including commented-out assignments (IMAGE_REGISTRY
# lives commented in .env.example and is the key an existing install is missing).
env_keys() {
  local file="$1"
  [ -f "$file" ] || return 0
  grep -E '^[[:space:]]*#?[[:space:]]*[A-Za-z_][A-Za-z0-9_]*=' "$file" \
    | sed -E 's/^[[:space:]]*#[[:space:]]*//; s/^[[:space:]]*//; s/=.*//' \
    | sort -u
}

report_env_diff() {
  local example="$REPO/.env.example"
  local envfile="$REPO/.env"
  if [ ! -f "$example" ]; then
    note ".env.example: not present (skipping drift report)"
    return 0
  fi
  if [ ! -f "$envfile" ]; then
    note ".env: not present (skipping drift report)"
    return 0
  fi
  local missing extra
  missing="$(comm -23 <(env_keys "$example") <(env_keys "$envfile") || true)"
  extra="$(comm -13 <(env_keys "$example") <(env_keys "$envfile") || true)"
  if [ -z "$missing" ] && [ -z "$extra" ]; then
    ok ".env keys match .env.example"
    return 0
  fi
  if [ -n "$missing" ]; then
    warn "keys in .env.example missing from .env (printed, not edited):"
    local key
    while IFS= read -r key; do
      [ -n "$key" ] || continue
      printf '\n'
      grep -B5 -E "^[[:space:]]*#?[[:space:]]*${key}=" "$example" | sed 's/^/    /' || printf '    %s\n' "$key"
    done <<< "$missing"
    printf '\n'
  fi
  if [ -n "$extra" ]; then
    warn "keys in .env not in .env.example (possibly removed upstream):"
    printf '%s\n' "$extra" | sed 's/^/    /'
  fi
}

probe_backend() {
  local port="$1"
  local body
  if ! command -v curl >/dev/null 2>&1; then
    note "backend: curl not available"
    return 0
  fi
  if body="$(curl -fsS --max-time 3 "http://127.0.0.1:${port}/api/version" 2>/dev/null)"; then
    ok "backend: version=$(json_field "$body" version) schema_revision=$(json_field "$body" schema_revision)"
  else
    note "backend: not running"
  fi
}

do_check() {
  local port describe newest newest_sha head remote_tags volume
  port="$(env_get BACKEND_HOST_PORT 8001)"
  note "checkout: $REPO"
  probe_backend "$port"

  volume="$(pgdata_volume)"
  if legacy_import_pending; then
    warn "database: $volume holds a Postgres database that was never imported, and this version cannot read it"
    print_import_first
  elif [ ! -s "$SQLITE_FILE" ]; then
    note "database: not created yet (first boot creates it)"
  elif [ -n "$volume" ]; then
    ok "database: data/maestro_cs.sqlite3 (the old Postgres volume is unused; remove it with docker volume rm $volume)"
  else
    ok "database: data/maestro_cs.sqlite3"
  fi

  if describe="$(git -C "$REPO" describe --tags --always 2>/dev/null)"; then
    ok "local: $describe"
  else
    note "local: tags unavailable"
  fi

  # No --refs: an ANNOTATED tag's plain line carries the tag-object sha, which
  # never equals a commit; its peeled "^{}" line carries the commit sha. Prefer
  # the peeled sha so the HEAD comparison works for both tag flavours.
  if ! remote_tags="$(git -C "$REPO" ls-remote --tags origin 'v*' 2>/dev/null)"; then
    note "tags: unavailable (could not query origin)"
  elif [ -z "$remote_tags" ]; then
    note "tags: no v* tags on origin yet (pre-release)"
  else
    newest="$(printf '%s\n' "$remote_tags" | sed 's@.*refs/tags/@@; s@\^{}$@@' | sort -u -V | tail -n 1)"
    newest_sha="$(printf '%s\n' "$remote_tags" | grep -F "refs/tags/${newest}^{}" | cut -f1 | head -n 1 || true)"
    if [ -z "$newest_sha" ]; then
      newest_sha="$(printf '%s\n' "$remote_tags" | grep -E "refs/tags/${newest}\$" | cut -f1 | head -n 1 || true)"
    fi
    head="$(git -C "$REPO" rev-parse HEAD 2>/dev/null || true)"
    if [ -n "$newest_sha" ] && [ "$head" = "$newest_sha" ]; then
      ok "newest remote v* tag: $newest (checkout matches)"
    elif [ -n "$newest_sha" ] && git -C "$REPO" merge-base --is-ancestor "$newest_sha" HEAD 2>/dev/null; then
      note "newest remote v* tag: $newest (checkout is ahead)"
    else
      note "newest remote v* tag: $newest (run ./scripts/update.sh to move to it)"
    fi
  fi

  report_env_diff
}

print_restore() {
  local dump="$1"
  note "restore this snapshot (stack STOPPED):  docker compose --project-directory \"$REPO\" down && gunzip -c \"$dump\" > \"$SQLITE_FILE\" && rm -f \"$SQLITE_FILE-wal\" \"$SQLITE_FILE-shm\" && docker compose --project-directory \"$REPO\" up -d"
  note "Rollback is one recipe: old git ref + old images + this backup. Never restore a backup into a newer schema."
  note "This backup guards the migration. base_resumes/, applications/, settings/, kb_documents/ are on disk and no step here touches them."
}

prune_keep_last() {
  local dir="$1"
  local prefix="$2"
  local count=0
  local f
  shopt -s nullglob
  local files=("$dir/$prefix"*)
  shopt -u nullglob
  if [ "${#files[@]}" -eq 0 ]; then
    return 0
  fi
  # ls -t is the portable mtime sort (GNU find -printf is not on macOS).
  # shellcheck disable=SC2012
  while IFS= read -r f; do
    count=$((count + 1))
    if [ "$count" -gt 5 ]; then
      rm -f "$f"
    fi
  done < <(ls -1t "${files[@]}")
}

SQLITE_FILE="$REPO/data/maestro_cs.sqlite3"
IMPORT_MARKER="$REPO/data/.migrated-from-postgres.json"

pgdata_volume() {
  # The compose file pins the project name; COMPOSE_PROJECT_NAME still overrides
  # it, the same way it does for compose.
  local project="${COMPOSE_PROJECT_NAME:-maestro-career-studio}"
  docker volume ls --format '{{.Name}}' 2>/dev/null | grep -Fx "${project}_pgdata" || true
}

# A v0.3.0-or-older install kept its data in Postgres. v0.4.0 is the one
# release that imports it (it writes $IMPORT_MARKER when it does); this version
# has no importer. A pgdata volume with no marker is data that never moved.
legacy_import_pending() {
  [ ! -f "$IMPORT_MARKER" ] && [ -n "$(pgdata_volume)" ]
}

print_import_first() {
  note "Import it with v0.4.0 first. Nothing has been deleted; from $REPO:"
  note "  docker compose down"
  note "  [ -f data/maestro_cs.sqlite3 ] && mv data/maestro_cs.sqlite3 data/maestro_cs.sqlite3.not-imported"
  note "  rm -f data/maestro_cs.sqlite3-wal data/maestro_cs.sqlite3-shm"
  note "  git fetch --tags origin && git checkout v0.4.0"
  note "  IMAGE_TAG=0.4.0 docker compose pull && IMAGE_TAG=0.4.0 docker compose up -d --force-recreate"
  note "When data/.migrated-from-postgres.json exists, run ./scripts/update.sh again. Details: docs/UPDATING.md"
}

# `--status running`, not a bare `ps`: a container `compose stop` left behind
# is not one to exec into, and some compose versions list it anyway.
backend_container_running() {
  [ -n "$(compose ps -q --status running backend 2>/dev/null || true)" ]
}

backup_sqlite() {
  local dump="$1"
  local registry="$2"
  local version="$3"
  local -a via
  local pin=""
  note "backing up the SQLite database to $dump"
  # Through the app's own tool (online backup): a plain cp of a live database
  # is a torn snapshot, WAL pages sit in the -wal sidecar until a checkpoint.
  # WHICH image runs it matters: this step runs BEFORE do_update pins
  # IMAGE_TAG, so a plain `compose run` in pull mode uses .env's IMAGE_TAG
  # (`latest`), which can be a pre-SQLite pull with no app.tools.backup_db.
  if backend_container_running; then
    # The container holding the file open runs the image that wrote it.
    note "snapshotting through the running backend container"
    via=(compose exec -T backend)
  else
    via=(compose run --rm -T --no-deps backend)
    if is_pull_mode "$registry"; then
      case "$version" in
        v[0-9]*)
          # The checkout's own release, for this one command. A describe past
          # its tag carries `-N-gSHA`; dropped, so the tag named is a published
          # one. A `dev`/sha describe names no tag at all, and .env stands.
          pin="${version#v}"
          pin="${pin%%-[0-9]*-g*}"
          note "backend is not running; snapshotting with the ${pin} image (the checkout's release, not .env's IMAGE_TAG)"
          ;;
      esac
    fi
    # Build mode: the local `latest` IS the checkout's build.
  fi
  # umask in a subshell so the shell's redirection CREATES the file 0600: this
  # snapshot holds every resume, application and setting in the database, and a
  # chmod after the fact leaves it world-readable for the length of the dump.
  # The IMAGE_TAG export lives and dies in that same subshell. That is the
  # intent, so the linter's "modification is local to the subshell" is silenced.
  # shellcheck disable=SC2030
  if ! ( umask 077; if [ -n "$pin" ]; then export IMAGE_TAG="$pin"; fi; "${via[@]}" python -m app.tools.backup_db --stdout | gzip > "$dump" ); then
    rm -f "$dump"
    die "sqlite backup failed"
  fi
  chmod 600 "$dump"
}

# gzip -t proves the container is intact; this proves the contents are the kind
# of database the name claims. Catches a dump that "succeeded" into the wrong
# branch's file, or a backup_db that wrote a diagnostic instead of bytes.
assert_backup_magic() {
  local dump="$1"
  local magic
  # `head -c 15`, not 16: byte 16 of the header is a NUL, which a command
  # substitution drops (with a warning on bash >= 5). `|| true` because head
  # closes the pipe as soon as it has its bytes, gunzip dies of SIGPIPE, and
  # `set -o pipefail` would report that 141 as the pipeline's status even
  # though the match succeeded.
  magic="$(gunzip -c "$dump" 2>/dev/null | head -c 15 || true)"
  [ "$magic" = "SQLite format 3" ] || die "backup is not a SQLite database: $dump"
}

wait_health() {
  local port="$1"
  local i
  note "waiting on /health (database migrations run at backend boot and can take a while after a schema change)"
  for i in $(seq 1 36); do
    if curl -fsS --max-time 3 "http://127.0.0.1:${port}/health" >/dev/null 2>&1; then
      ok "stack is healthy"
      return 0
    fi
    note "still waiting on migrations ($i/36)"
    sleep 5
  done
  warn "timed out waiting for /health"
  compose logs --tail=50 || true
  return 1
}

do_update() {
  local force="$1"
  local port registry
  local old_sha ts version dump envbak pulled=0
  local newest tag_without_v

  port="$(env_get BACKEND_HOST_PORT 8001)"
  registry="$(env_get IMAGE_REGISTRY)"

  # Before anything moves: a Postgres database that never reached the file
  # would be stranded by an update past v0.4.0.
  if legacy_import_pending; then
    warn "$(pgdata_volume) holds a Postgres database that was never imported; this update would leave it behind"
    print_import_first
    exit 1
  fi

  if [ -n "$(git -C "$REPO" status --porcelain)" ]; then
    if [ "$force" -eq 0 ]; then
      die "working tree is dirty; commit, stash, or pass --force (a pull over local edits is how a hand-edited template is lost)"
    fi
    warn "working tree is dirty; --force set, continuing"
  fi

  command -v docker >/dev/null 2>&1 || die "docker is not on PATH"
  docker compose version >/dev/null 2>&1 || die "docker compose is not available"

  mkdir -p "$REPO/backups"
  old_sha="$(git -C "$REPO" rev-parse --short HEAD)"
  ts="$(date +%Y%m%dT%H%M%S)"
  version="$(git -C "$REPO" describe --tags --always 2>/dev/null | tr '/:' '--')"

  if [ ! -s "$SQLITE_FILE" ]; then
    die "no database to back up: $SQLITE_FILE is empty or missing; a first boot creates the file"
  fi
  dump="$REPO/backups/db-${ts}-${version}.sqlite3.gz"
  backup_sqlite "$dump" "$registry" "$version"
  if [ ! -s "$dump" ]; then
    rm -f "$dump"
    die "backup is empty — gzip would otherwise hide a failed dump"
  fi
  gzip -t "$dump" || die "backup is not valid gzip"
  assert_backup_magic "$dump"
  ok "backup written: $dump ($(wc -c < "$dump" | tr -d ' ') bytes)"

  envbak="$REPO/backups/env-${ts}.bak"
  if [ -f "$REPO/.env" ]; then
    cp "$REPO/.env" "$envbak"
    ok "copied .env to $envbak"
  else
    warn "no .env to copy"
  fi
  prune_keep_last "$REPO/backups" "db-"
  prune_keep_last "$REPO/backups" "env-"
  print_restore "$dump"

  note "fetching tags from origin"
  git -C "$REPO" fetch --tags origin || die "git fetch --tags origin failed"

  newest=""
  while IFS= read -r newest; do
    break
  done < <(git -C "$REPO" tag -l 'v*' --sort=-v:refname)
  if [ -z "$newest" ]; then
    warn "pre-release tree: no v* tags on origin; fast-forwarding the current branch from origin (not a release pin)"
    git -C "$REPO" pull --ff-only origin || die "git pull --ff-only failed"
  else
    note "fast-forwarding to $newest"
    if git -C "$REPO" merge --ff-only "$newest"; then
      ok "checkout is at $newest"
    else
      die "could not fast-forward to $newest (divergent history?). Refusing to move; your backup is at $dump"
    fi
  fi

  report_env_diff

  if is_pull_mode "$registry"; then
    tag_without_v=""
    if [ -n "$newest" ]; then
      tag_without_v="${newest#v}"
      # This export is meant for the rest of the run; the backup's subshell
      # export (above) is the one kept local on purpose.
      # shellcheck disable=SC2031
      export IMAGE_TAG="$tag_without_v"
      note "pull-mode: pinning IMAGE_TAG=$IMAGE_TAG for this run (.env is not edited; IMAGE_TAG=latest stays the plain 'docker compose up' fallback)"
    fi
    note "pulling images"
    compose pull
    pulled=1
  else
    note "build-mode: IMAGE_REGISTRY is unset or local ($registry), so this will build images (TeX Live, several minutes)"
    note "To switch to prebuilt images (users, not contributors) set in .env:"
    note "  IMAGE_REGISTRY=ghcr.io/${CANONICAL}"
    note "  IMAGE_TAG=latest"
    note "Those images are published from every release. Contributors stay on --build."
    compose build
  fi

  if [ "$pulled" -eq 1 ]; then
    note "recreating the stack with the pulled images"
    compose up -d --remove-orphans --force-recreate
  else
    compose up -d --remove-orphans
  fi

  if ! wait_health "$port"; then
    print_restore "$dump"
    exit 1
  fi

  printf '\n'
  ok "update complete"
  if [ -n "$(pgdata_volume)" ] || docker image inspect postgres:16 >/dev/null 2>&1; then
    printf '\n'
    note "Postgres is no longer part of Maestro CS. Once you are satisfied, free the space it used:"
    if [ -n "$(pgdata_volume)" ]; then
      note "  docker volume rm $(pgdata_volume)      # the old database, already imported"
    fi
    note "  docker image rm postgres:16      # skip if another project of yours uses it"
  fi
  if [ "$(git -C "$REPO" rev-parse --short HEAD)" != "$old_sha" ]; then
    note "commits brought in:"
    # --no-pager: on a terminal git would open this list in `less` and wait for
    # a keypress, hiding the extension/MCP reminders printed after it.
    git --no-pager -C "$REPO" log --oneline "${old_sha}..HEAD" || true
  else
    note "Already up to date (no new commits)."
  fi
  note "Release notes: https://github.com/${CANONICAL}/releases"
  printf '\n'
  note "Two surfaces Docker cannot update:"
  note "  1. Reload the unpacked extension at chrome://extensions."
  note "     Upgrading from a version before the pinned key: Remove the extension and Load unpacked again — reloading is not enough (see extension/README.md)."
  note "  2. Restart the MCP client so it picks up new tools."
  note "     If you use MCP, re-run ./scripts/setup-mcp.sh — always, not only if config moved: the editable venv picks up code but not new dependencies."
}

main() {
  local check=0 force=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --check) check=1; shift ;;
      --force) force=1; shift ;;
      -h|--help) usage; exit 0 ;;
      *) die "unknown argument: $1 (try --help)" ;;
    esac
  done

  # A ZIP unpack cannot update: there is no history to fast-forward.
  # -e, not -d: a worktree's .git is a file.
  [ -e "$REPO/.git" ] || die "this directory is not a git clone (no .git). ZIP unpacks cannot update — clone from GitHub instead (see the README Quickstart)."

  warn_if_fork

  if [ "$check" -eq 1 ]; then
    do_check
    exit 0
  fi

  do_update "$force"
}

# One line, deliberately: step "fetch/ff" REWRITES this file mid-run, and bash
# reads scripts incrementally. Everything above is function definitions, and
# `main "$@"; exit $?` parses as one list before executing — so bash never
# returns to read another command from the (possibly rewritten) file.
main "$@"; exit $?
