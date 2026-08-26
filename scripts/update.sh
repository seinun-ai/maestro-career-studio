#!/usr/bin/env bash
#
# Update an installed Maestro CS to the newest v* release.
#
# Why this exists: an install IS a git checkout. The unpacked extension loads
# from extension/ and the MCP venv sits over backend/, so checkout and images
# must move together. `docker compose pull` alone updates two surfaces of four.
# This also backs up the database before the one irreversible step (migrations,
# which run themselves at backend boot) and reports .env drift without editing
# it.
#
#   ./scripts/update.sh            # backup → ff-to-tag → pull/build → up
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
  local port describe newest newest_sha head remote_tags
  port="$(env_get BACKEND_HOST_PORT 8001)"
  note "checkout: $REPO"
  probe_backend "$port"

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
  local user="$2"
  local db="$3"
  note "restore this dump:  gunzip -c $dump | docker compose --project-directory \"$REPO\" exec -T postgres psql -U $user $db"
  note "Rollback is one recipe: old git ref + old images + this dump. Never restore a dump into a newer schema."
  note "This dump guards the migration. base_resumes/, applications/, settings/, kb_documents/ are on disk and no step here touches them."
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

wait_postgres() {
  local user="$1"
  local db="$2"
  local i
  note "waiting for postgres to be healthy"
  for i in $(seq 1 60); do
    if compose exec -T postgres pg_isready -U "$user" -d "$db" >/dev/null 2>&1; then
      ok "postgres is up"
      return 0
    fi
    if [ $((i % 5)) -eq 0 ]; then
      note "still waiting for postgres ($i/60)"
    fi
    sleep 2
  done
  die "postgres did not become healthy"
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
  local port user db registry
  local old_sha ts version dump envbak pulled=0
  local newest tag_without_v

  port="$(env_get BACKEND_HOST_PORT 8001)"
  user="$(env_get POSTGRES_USER app)"
  db="$(env_get POSTGRES_DB maestro_cs)"
  registry="$(env_get IMAGE_REGISTRY)"

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

  note "starting postgres so there is a database to back up"
  compose up -d postgres
  wait_postgres "$user" "$db"

  dump="$REPO/backups/db-${ts}-${version}.sql.gz"
  note "backing up database to $dump"
  # --clean --if-exists so the printed restore command works into a database
  # that already has the schema (a plain dump errors on every duplicate table).
  if ! compose exec -T postgres pg_dump --clean --if-exists -U "$user" "$db" | gzip > "$dump"; then
    rm -f "$dump"
    die "pg_dump failed"
  fi
  if [ ! -s "$dump" ]; then
    rm -f "$dump"
    die "backup is empty — gzip would otherwise hide a failed dump"
  fi
  gzip -t "$dump" || die "backup is not valid gzip"
  ok "backup written ($(wc -c < "$dump" | tr -d ' ') bytes)"

  envbak="$REPO/backups/env-${ts}.bak"
  if [ -f "$REPO/.env" ]; then
    cp "$REPO/.env" "$envbak"
    ok "copied .env to $envbak"
  else
    warn "no .env to copy"
  fi
  prune_keep_last "$REPO/backups" "db-"
  prune_keep_last "$REPO/backups" "env-"
  print_restore "$dump" "$user" "$db"

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
    note "Only after those images have been published. Contributors stay on --build."
    compose build
  fi

  if [ "$pulled" -eq 1 ]; then
    note "recreating the stack with the pulled images"
    compose up -d --remove-orphans --force-recreate
  else
    compose up -d --remove-orphans
  fi

  if ! wait_health "$port"; then
    print_restore "$dump" "$user" "$db"
    exit 1
  fi

  printf '\n'
  ok "update complete"
  if [ "$(git -C "$REPO" rev-parse --short HEAD)" != "$old_sha" ]; then
    note "commits brought in:"
    git -C "$REPO" log --oneline "${old_sha}..HEAD" || true
  else
    note "Already up to date (no new commits)."
  fi
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
