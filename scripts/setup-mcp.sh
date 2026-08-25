#!/usr/bin/env bash
#
# Register the Maestro CS MCP server with your assistant.
#
# This exists because every MCP client wants an ABSOLUTE path to the server
# binary, and GUI clients (Claude Desktop, the ChatGPT desktop app) do not
# inherit your shell PATH, so "just use the console script" is not an option
# for them. Rather than have each user hand-substitute <MAESTRO_CS_MCP>,
# <REPO>, <HOME> and <NODE> into a JSON file, this resolves all four and either
# registers the server (Claude Code) or prints a block you can paste verbatim.
#
#   ./scripts/setup-mcp.sh                     # venv + Claude Code + print the rest
#   ./scripts/setup-mcp.sh --profile hunt      # register a scoped profile instead
#   ./scripts/setup-mcp.sh --print-only        # change nothing, just show the config
#   ./scripts/setup-mcp.sh --backend-url http://localhost:8000
#
# Nothing here touches the backend or the database. The only thing it can
# modify outside the repo is your Claude Code MCP registration, and only when
# --print-only is absent.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$REPO/backend"
VENV="$BACKEND/.venv"

PROFILE="full"
BACKEND_URL=""
PRINT_ONLY=0
SKIP_INSTALL=0

die() { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }
note() { printf '\033[36m→\033[0m %s\n' "$*"; }
ok()   { printf '\033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!\033[0m %s\n' "$*" >&2; }

while [ $# -gt 0 ]; do
  case "$1" in
    --profile)      PROFILE="${2:-}"; shift 2 ;;
    --backend-url)  BACKEND_URL="${2:-}"; shift 2 ;;
    --print-only)   PRINT_ONLY=1; shift ;;
    --skip-install) SKIP_INSTALL=1; shift ;;
    -h|--help)      sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)              die "unknown argument: $1 (try --help)" ;;
  esac
done

case "$PROFILE" in
  full|hunt|apply|explore|templates|career) ;;
  *) die "unknown profile '$PROFILE' (full, hunt, apply, explore, templates, career)" ;;
esac

# ---------------------------------------------------------------------------
# 1. Backend URL — the host port compose publishes, NOT the container's 8000.
# ---------------------------------------------------------------------------
if [ -z "$BACKEND_URL" ]; then
  port=8001
  if [ -f "$REPO/.env" ]; then
    # Take the last uncommented assignment, matching how a shell would source it.
    from_env="$(grep -E '^[[:space:]]*BACKEND_HOST_PORT=' "$REPO/.env" | tail -1 | cut -d= -f2- | tr -d ' "'"'"'' || true)"
    [ -n "$from_env" ] && port="$from_env"
  fi
  BACKEND_URL="http://localhost:$port"
fi
note "backend url: $BACKEND_URL"

# ---------------------------------------------------------------------------
# 2. Python environment. The MCP server runs on the HOST as a subprocess of the
#    assistant, so it needs its own venv even though the app runs in Docker.
# ---------------------------------------------------------------------------
py_remedy() {
  # A fresh macOS ships python 3.9; say exactly how to get a 3.12, per OS,
  # instead of leaving the user (or their agent) to rediscover it.
  warn "the MCP server runs on the HOST as your assistant's subprocess, so it"
  warn "needs a host Python >= 3.12 even though the app itself runs in Docker."
  case "$(uname -s)" in
    Darwin) warn "get one with:  brew install python@3.12    then re-run this script" ;;
    Linux)  warn "get one with:  sudo apt install python3.12 python3.12-venv    (or your distro's equivalent)" ;;
    *)      warn "install Python 3.12+ from https://www.python.org/downloads/ and re-run" ;;
  esac
}

if [ "$SKIP_INSTALL" -eq 0 ]; then
  if [ ! -d "$VENV" ]; then
    py="$(command -v python3.12 || command -v python3.13 || command -v python3.14 || command -v python3 || true)"
    if [ -z "$py" ]; then py_remedy; die "no python3 on PATH; the MCP server needs Python >= 3.12"; fi
    # Compare numerically. A glob like 3.[2-9]* reads as ">= 3.2" and happily
    # accepts python 3.9, which then fails much later on syntax.
    ver="$("$py" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
    "$py" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 12) else 1)' \
      || { py_remedy; die "python $ver is too old; the MCP server needs >= 3.12 (found at $py)"; }
    note "creating venv at $VENV (python $ver)"
    "$py" -m venv "$VENV"
  fi
  note "installing the mcp extra (quiet; this can take a minute on a cold venv)"
  "$VENV/bin/pip" install -q --upgrade pip
  ( cd "$BACKEND" && "$VENV/bin/pip" install -q -e ".[mcp]" )
fi

MCP_BIN="$VENV/bin/maestro-career-studio-mcp"
[ -x "$MCP_BIN" ] || die "expected the console script at $MCP_BIN but it is missing or not executable — re-run without --skip-install"
ok "server binary: $MCP_BIN"

# ---------------------------------------------------------------------------
# 3. Claude Code — two routes, belt and braces.
#
#    (a) A repo-level .mcp.json (project scope): any Claude Code session opened
#        IN this repo offers the server automatically — no CLI, no config edit.
#        Written every run because it is machine-specific (absolute venv path)
#        and gitignored. This is also the route that works when this script is
#        run BY an agent, since `claude` refuses to run nested inside a session
#        and an agent's permission mode may not let it edit ~/.claude.json.
#    (b) `claude mcp add` for sessions outside the repo, when the CLI can run.
# ---------------------------------------------------------------------------
SERVER_NAME="maestro-career-studio"
[ "$PROFILE" = "full" ] || SERVER_NAME="maestro-career-studio-$PROFILE"

if [ "$PRINT_ONLY" -eq 1 ]; then
  note "--print-only: skipping Claude Code registration and .mcp.json"
else
  "$VENV/bin/python" - "$REPO/.mcp.json" "$SERVER_NAME" "$MCP_BIN" "$BACKEND_URL" "$PROFILE" <<'PYEOF'
import json, sys
path, name, bin_, url, profile = sys.argv[1:6]
try:
    with open(path) as f:
        data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    data = {}
data.setdefault("mcpServers", {})[name] = {
    "command": bin_,
    "env": {"BACKEND_URL": url, "MAESTRO_CS_MCP_PROFILE": profile},
}
with open(path, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PYEOF
  ok "wrote $REPO/.mcp.json — Claude Code sessions opened in this repo will offer '$SERVER_NAME' (approve when prompted)"

  if [ -n "${CLAUDECODE:-}" ]; then
    warn "running inside a Claude Code session — the 'claude' CLI cannot run nested."
    warn "The .mcp.json above covers sessions in this repo. For a user-wide"
    warn "registration, run this later in a plain terminal:"
    printf '    claude mcp add %s -e BACKEND_URL=%s -e MAESTRO_CS_MCP_PROFILE=%s -- %s\n' \
      "$SERVER_NAME" "$BACKEND_URL" "$PROFILE" "$MCP_BIN"
  elif command -v claude >/dev/null 2>&1; then
    if claude mcp get "$SERVER_NAME" >/dev/null 2>&1; then
      warn "'$SERVER_NAME' is already registered with Claude Code — leaving it alone."
      warn "Remove it first if you want to re-register: claude mcp remove $SERVER_NAME"
    else
      claude mcp add "$SERVER_NAME" \
        -e "BACKEND_URL=$BACKEND_URL" \
        -e "MAESTRO_CS_MCP_PROFILE=$PROFILE" \
        -- "$MCP_BIN"
      ok "registered '$SERVER_NAME' with Claude Code"
    fi
  else
    warn "the 'claude' CLI is not on PATH — the .mcp.json above still covers sessions opened in this repo"
  fi
fi

# ---------------------------------------------------------------------------
# 4. GUI clients — print a block with every placeholder already resolved.
#    These are printed rather than written because both files are shared with
#    your other servers, and silently rewriting someone's assistant config is
#    not a thing an install script should do.
# ---------------------------------------------------------------------------
cat <<EOF

────────────────────────────────────────────────────────────────────────
Claude Desktop — FIRST fully quit Claude Desktop (Cmd+Q — a window close is
not enough): the running app rewrites this file from its own memory on exit
and will silently drop an edit made while it is open. Then merge into the
"mcpServers" object of
  ~/Library/Application Support/Claude/claude_desktop_config.json
and reopen the app.

    "$SERVER_NAME": {
      "command": "$MCP_BIN",
      "env": {
        "BACKEND_URL": "$BACKEND_URL",
        "MAESTRO_CS_MCP_PROFILE": "$PROFILE",
        "MAESTRO_CS_MCP_CLIENT": "Claude Desktop"
      }
    }

────────────────────────────────────────────────────────────────────────
ChatGPT desktop app / Codex CLI — append to ~/.codex/config.toml
(both share this file):

[mcp_servers.$SERVER_NAME]
command = "$MCP_BIN"

[mcp_servers.$SERVER_NAME.env]
BACKEND_URL = "$BACKEND_URL"
MAESTRO_CS_MCP_PROFILE = "$PROFILE"

────────────────────────────────────────────────────────────────────────
EOF

# ---------------------------------------------------------------------------
# 5. Is the backend actually up? Not fatal — the server starts either way and
#    the failure would otherwise surface as a confusing tool error mid-chat.
# ---------------------------------------------------------------------------
if command -v curl >/dev/null 2>&1; then
  if curl -fsS --max-time 3 "$BACKEND_URL/health" >/dev/null 2>&1; then
    ok "backend is reachable at $BACKEND_URL"
  else
    warn "no backend answered at $BACKEND_URL/health."
    warn "Start it with 'docker compose up -d', then check the published port"
    warn "with 'docker compose ps' — the container listens on 8000 internally"
    warn "but compose maps it to $BACKEND_URL on the host."
  fi
fi

if [ "$PRINT_ONLY" -eq 1 ]; then
  printf "Nothing was registered (--print-only). "
fi
cat <<EOF
Server name for profile '$PROFILE' is '$SERVER_NAME'.
Enable ONE profile per chat: running 'full' alongside a scoped profile
registers the same tool twice and the model has to guess which to call.

Keep the transport STDIO. The HTTP option means exposing a deliberately
unauthenticated backend that holds your full employment history.
EOF
