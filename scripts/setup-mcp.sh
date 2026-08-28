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
#   ./scripts/setup-mcp.sh --write-desktop-config   # also merge into Claude Desktop
#   ./scripts/setup-mcp.sh --print-only        # register nothing; still builds the venv
#   ./scripts/setup-mcp.sh --print-only --skip-install   # a true no-op: just show the config
#   ./scripts/setup-mcp.sh --backend-url http://localhost:8000
#
# Nothing here touches the backend or the database. The only thing it can
# modify outside the repo is your Claude Code MCP registration, and only when
# --print-only is absent, plus Claude Desktop's config when you pass
# --write-desktop-config. Inside the repo it owns exactly one file, the
# gitignored .mcp.json, and keeps it to a SINGLE profile (--keep-other-profiles
# opts out) so no session is offered two copies of the same tool.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$REPO/backend"
VENV="$BACKEND/.venv"

PROFILE="full"
BACKEND_URL=""
PRINT_ONLY=0
SKIP_INSTALL=0
PRUNE_SIBLINGS=1
WRITE_DESKTOP=0

die() { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }
note() { printf '\033[36m→\033[0m %s\n' "$*"; }
ok()   { printf '\033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!\033[0m %s\n' "$*" >&2; }

# `shift 2` on a flag given without its value aborts under `set -e` with bash's
# own terse message and no hint about which flag was wrong — check first.
need_value() { [ "$2" -ge 2 ] || die "$1 needs a value (try --help)"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --profile)      need_value "$1" $#; PROFILE="$2"; shift 2 ;;
    --backend-url)  need_value "$1" $#; BACKEND_URL="$2"; shift 2 ;;
    --print-only)   PRINT_ONLY=1; shift ;;
    --skip-install) SKIP_INSTALL=1; shift ;;
    --keep-other-profiles) PRUNE_SIBLINGS=0; shift ;;
    --write-desktop-config) WRITE_DESKTOP=1; shift ;;
    -h|--help)      sed -n '2,23p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)              die "unknown argument: $1 (try --help)" ;;
  esac
done

if [ "$PRINT_ONLY" -eq 1 ] && [ "$WRITE_DESKTOP" -eq 1 ]; then
  die "--print-only and --write-desktop-config contradict each other"
fi

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

# Compare numerically. A glob like 3.[2-9]* reads as ">= 3.2" and happily
# accepts python 3.9, which then fails much later on syntax.
py_version()    { "$1" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true; }
py_new_enough() { "$1" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 12) else 1)' 2>/dev/null; }

if [ "$SKIP_INSTALL" -eq 0 ]; then
  if [ -d "$VENV" ]; then
    # An existing venv is NOT proof of a usable one. It may predate the 3.12
    # floor (easy to create: a fresh macOS python3 is 3.9 and `python3 -m venv`
    # is happy to build one), or its base interpreter may have been removed by
    # a `brew upgrade`. Either way `pip install -e` below fails later with an
    # error that names neither the venv nor the version, so check it HERE.
    ver="$(py_version "$VENV/bin/python")"
    if [ -z "$ver" ]; then
      die "the venv at $VENV cannot run its own python — its base interpreter is
       probably gone. Delete it and re-run:  rm -rf \"$VENV\""
    fi
    if ! py_new_enough "$VENV/bin/python"; then
      py_remedy
      die "the existing venv at $VENV was built with python $ver, below the
       required 3.12. Delete it and re-run:  rm -rf \"$VENV\""
    fi
    note "reusing venv at $VENV (python $ver)"
  else
    py="$(command -v python3.12 || command -v python3.13 || command -v python3.14 || command -v python3 || true)"
    if [ -z "$py" ]; then py_remedy; die "no python3 on PATH; the MCP server needs Python >= 3.12"; fi
    ver="$(py_version "$py")"
    py_new_enough "$py" \
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
# 3. Claude Code — two routes, belt and braces. They are INDEPENDENT: each
#    writes a different file, and a session can be served by either.
#
#    (a) A repo-level .mcp.json (PROJECT scope): any Claude Code session opened
#        IN this repo is offered the server — no CLI, no config edit. Written
#        every run because it is machine-specific (absolute venv path) and
#        gitignored. Project scope is approval-gated: the offer appears in the
#        NEXT session started here, not the one running this script, and stays
#        inert until accepted (the answer is recorded in the project's
#        `enabledMcpjsonServers`). This is the route that survives being run BY
#        an agent, whose permission mode may not extend to ~/.claude.json.
#    (b) `claude mcp add --scope user` for sessions in ANY directory. The scope
#        flag is load-bearing: the CLI's default is `local`, which is private
#        to the current project and therefore does NOT do what (b) is for.
# ---------------------------------------------------------------------------
SERVER_NAME="maestro-career-studio"
[ "$PROFILE" = "full" ] || SERVER_NAME="maestro-career-studio-$PROFILE"

# Every name this script can write. Used to prune stale siblings from .mcp.json:
# entries there are offered to every session in the repo, so leaving `full`
# beside `hunt` silently produces the exact double-registration the closing
# message warns against — and nothing ever asks the user which they meant.
ALL_SERVER_NAMES=(
  maestro-career-studio
  maestro-career-studio-hunt
  maestro-career-studio-apply
  maestro-career-studio-explore
  maestro-career-studio-templates
  maestro-career-studio-career
)

if [ "$PRINT_ONLY" -eq 1 ]; then
  note "--print-only: skipping Claude Code registration and .mcp.json"
else
  dropped="$("$VENV/bin/python" - "$REPO/.mcp.json" "$SERVER_NAME" "$MCP_BIN" \
      "$BACKEND_URL" "$PROFILE" "$PRUNE_SIBLINGS" "${ALL_SERVER_NAMES[@]}" <<'PYEOF'
import json, sys
path, name, bin_, url, profile, prune = sys.argv[1:7]
known = sys.argv[7:]
try:
    with open(path) as f:
        data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    data = {}
servers = data.setdefault("mcpServers", {})
# Only ever drop names this script itself writes. A hand-added server of
# any other name belongs to whoever put it there; leave it.
# (NB: no apostrophes anywhere in this heredoc — bash 3.2, which is what
# /usr/bin/env bash resolves to on stock macOS, scans the body of a heredoc
# nested in $( ) for quotes and dies on an unmatched one.)
dropped = [k for k in known if k != name and k in servers] if prune == "1" else []
for k in dropped:
    del servers[k]
servers[name] = {
    "command": bin_,
    "env": {"BACKEND_URL": url, "MAESTRO_CS_MCP_PROFILE": profile},
}
with open(path, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
print(" ".join(dropped))
PYEOF
)"
  ok "wrote $REPO/.mcp.json — it now offers exactly one server, '$SERVER_NAME'"
  [ -z "$dropped" ] || warn "dropped stale sibling profile(s) from it: $dropped (one profile per chat; --keep-other-profiles overrides)"
  note "that offer reaches the NEXT Claude Code session started in this repo — not"
  note "this one — and you approve it once, per project. Until then it is inert:"
  note "if tools already work here, a 'claude mcp add' registration is serving them."

  if [ -n "${CLAUDECODE:-}" ]; then
    # `claude mcp` subcommands run fine inside a session; what stops us here is
    # consent, not capability. This route writes to your user config, outside
    # the repo, and a script an agent is running should not do that for you.
    warn "running inside a Claude Code session — not editing your user config from here."
    warn "The .mcp.json above covers sessions opened in this repo. To reach the"
    warn "server from EVERY directory, run this yourself in a plain terminal:"
    printf '    claude mcp add --scope user %s -e BACKEND_URL=%s -e MAESTRO_CS_MCP_PROFILE=%s -- %s\n' \
      "$SERVER_NAME" "$BACKEND_URL" "$PROFILE" "$MCP_BIN"
  elif command -v claude >/dev/null 2>&1; then
    if claude mcp get "$SERVER_NAME" >/dev/null 2>&1; then
      # Say WHICH scope holds it. "Already registered" without the scope leaves
      # the real question open when tools appear in one directory and not another.
      scope="$(claude mcp get "$SERVER_NAME" 2>/dev/null | sed -n 's/^ *Scope: *//p' | head -1 || true)"
      warn "'$SERVER_NAME' is already registered with Claude Code — leaving it alone."
      [ -z "$scope" ] || warn "  it lives in: $scope"
      warn "Remove it first if you want to re-register: claude mcp remove $SERVER_NAME"
    else
      # --scope user, NOT the CLI's `local` default, which is private to
      # whichever directory this happens to be run from.
      claude mcp add --scope user "$SERVER_NAME" \
        -e "BACKEND_URL=$BACKEND_URL" \
        -e "MAESTRO_CS_MCP_PROFILE=$PROFILE" \
        -- "$MCP_BIN"
      ok "registered '$SERVER_NAME' with Claude Code at user scope (every directory)"
    fi
  else
    warn "the 'claude' CLI is not on PATH — the .mcp.json above still covers sessions opened in this repo"
  fi
fi

# ---------------------------------------------------------------------------
# 4. Claude Desktop (opt-in). It is a SEPARATE surface from Claude Code —
#    nothing registered above reaches it. Its config is an ordinary JSON file
#    and this script can merge into it, but only when asked: that file is
#    shared with your other MCP servers, and an install script that silently
#    rewrites an assistant config is a bad neighbour. So: opt in, back up,
#    merge one key, and refuse to run while the app is open.
# ---------------------------------------------------------------------------
desktop_config_path() {
  case "$(uname -s)" in
    Darwin) printf '%s/Library/Application Support/Claude/claude_desktop_config.json' "$HOME" ;;
    Linux)  printf '%s/.config/Claude/claude_desktop_config.json' "$HOME" ;;
    *)      return 1 ;;
  esac
}

# shellcheck disable=SC2009  # pgrep is the usual advice; it does not work here, see below
desktop_is_running() {
  # `pgrep -f` does not reliably see this argv on macOS, but the full
  # executable path out of ps does — and it cannot be confused with Claude
  # CODE, whose own bundle is a lowercase claude.app under Application Support.
  case "$(uname -s)" in
    Darwin) ps -Ao comm= | grep -qx '/Applications/Claude.app/Contents/MacOS/Claude' ;;
    *)      return 1 ;;
  esac
}

DESKTOP_CFG=""
DESKTOP_ACTION=""
if [ "$WRITE_DESKTOP" -eq 1 ]; then
  DESKTOP_CFG="$(desktop_config_path)" \
    || die "--write-desktop-config is implemented for macOS and Linux only; use the block printed below"
  if desktop_is_running; then
    die "Claude Desktop is running. Quit it fully (Cmd+Q — closing the window is
       not enough) and re-run. The app writes this file too, so an edit made
       while it is open can be discarded when it exits."
  fi
  mkdir -p "$(dirname "$DESKTOP_CFG")"
  if [ -f "$DESKTOP_CFG" ]; then
    backup="$DESKTOP_CFG.bak-$(date +%Y%m%d-%H%M%S)"
    cp "$DESKTOP_CFG" "$backup"
    note "backed up your Desktop config to $(basename "$backup")"
  fi
  DESKTOP_ACTION="$("$VENV/bin/python" - "$DESKTOP_CFG" "$SERVER_NAME" "$MCP_BIN" \
      "$BACKEND_URL" "$PROFILE" <<'PYEOF'
import json, os, sys
path, name, bin_, url, profile = sys.argv[1:6]
try:
    with open(path) as f:
        data = json.load(f)
except FileNotFoundError:
    data = {}
except json.JSONDecodeError as exc:
    raise SystemExit("refusing to touch %s — it is not valid JSON (%s)" % (path, exc))
servers = data.setdefault("mcpServers", {})
existed = name in servers
# Merge ONE key. Every other server in this file, and every other top-level
# key, belongs to the app or to somebody else. Never rebuild it from scratch.
servers[name] = {
    "command": bin_,
    "env": {
        "BACKEND_URL": url,
        "MAESTRO_CS_MCP_PROFILE": profile,
        "MAESTRO_CS_MCP_CLIENT": "Claude Desktop",
    },
}
tmp = path + ".tmp"
with open(tmp, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
with open(tmp) as f:      # parse what we are about to install, before installing it
    json.load(f)
os.replace(tmp, path)
siblings = sorted(k for k in servers if k.startswith("maestro-career-studio") and k != name)
print(("updated" if existed else "added") + "\t" + " ".join(siblings))
PYEOF
)"
  IFS="$(printf '\t')" read -r action siblings <<< "$DESKTOP_ACTION"
  ok "$action '$SERVER_NAME' in $DESKTOP_CFG (other servers left untouched)"
  [ -z "$siblings" ] || note "other Maestro profiles already in that file: $siblings — left alone; Claude Desktop can toggle servers per chat"
fi

# ---------------------------------------------------------------------------
# 5. GUI clients — print a block with every placeholder already resolved.
#    The Codex block is printed rather than written because that file is
#    shared with your other servers; Claude Desktop has --write-desktop-config
#    (section 4) for the same job, opt-in for the same reason.
# ---------------------------------------------------------------------------
if [ -n "$DESKTOP_CFG" ]; then
  cat <<EOF

────────────────────────────────────────────────────────────────────────
Claude Desktop — already done: '$SERVER_NAME' was merged into
  $DESKTOP_CFG
Start the app and confirm it under Settings → Connectors. If it is not there,
your backup is beside that file and the paste-by-hand block is available with
  ./scripts/setup-mcp.sh --print-only --skip-install
EOF
else
  cat <<EOF

────────────────────────────────────────────────────────────────────────
Claude Desktop is a SEPARATE surface: what this script registered above gives
tools to Claude Code only, and does nothing for Desktop chats. Three ways in,
easiest first:

  1. Re-run this script with --write-desktop-config (quit the app first — it
     backs the file up, merges one key, and leaves your other servers alone).
  2. The app's own UI: Settings → Connectors → Add custom connector (older
     builds put this under Settings → Developer), with
       Command:  $MCP_BIN
       Env:      BACKEND_URL=$BACKEND_URL
                 MAESTRO_CS_MCP_PROFILE=$PROFILE
                 MAESTRO_CS_MCP_CLIENT=Claude Desktop
  3. By hand: FULLY quit the app first (Cmd+Q — closing the window is not
     enough; the app writes this file too and can discard an edit made while
     it is open), merge the block below into the "mcpServers" object of
       ~/Library/Application Support/Claude/claude_desktop_config.json
     then reopen and check Settings → Connectors that it took.

    "$SERVER_NAME": {
      "command": "$MCP_BIN",
      "env": {
        "BACKEND_URL": "$BACKEND_URL",
        "MAESTRO_CS_MCP_PROFILE": "$PROFILE",
        "MAESTRO_CS_MCP_CLIENT": "Claude Desktop"
      }
    }
EOF
fi

cat <<EOF

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
# 6. Is the backend actually up? Not fatal — the server starts either way and
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
This script keeps .mcp.json to a single profile, but registrations made with
'claude mcp add' are yours to manage — list them with 'claude mcp list' and
drop the extras with 'claude mcp remove <name>'.

Keep the transport STDIO. The HTTP option means exposing a deliberately
unauthenticated backend that holds your full employment history.
EOF
