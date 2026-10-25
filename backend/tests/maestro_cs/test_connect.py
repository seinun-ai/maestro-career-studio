"""`maestro connect`: config merge, the running-Desktop deferral, and the per-client strings.

Nothing here touches a real agent app: config paths live under `tmp_path`, `claude`/`codex`
and the browser are injected, the process list is a list of fakes, and the detached waiter is a
recording stub. `apply` is a no-op because the test process already imported `app` (R8 is
covered by the subprocess test at the end).
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from maestro_cs import cli, connect, control, detach
from maestro_cs.control import Context, ControlError
from maestro_cs.home import Ports

BACKEND = Path(__file__).resolve().parents[2]
FIXED_NOW = datetime(2026, 10, 10, 12, 30, 5, tzinfo=timezone.utc)
SHIM = Path(os.path.abspath("/venv/bin/maestro"))


def make_ctx(tmp_path, platform_environ=None):
    home = tmp_path / "home"
    for name in ("logs", "run"):
        (home / name).mkdir(parents=True, exist_ok=True)
    env = {"PATH": os.environ.get("PATH", ""), **(platform_environ or {})}
    return Context(home, {}, Ports(18001, 13000), env, "9.9.9")


class Recorder:
    """Collects everything the connector says, runs, opens or detaches."""

    def __init__(self, running=False, which=None, code=0, stdout="", stderr=""):
        self.said, self.ran, self.opened, self.detached = [], [], [], []
        self.running = running
        self.paths = which or {}
        self.code, self.stdout, self.stderr = code, stdout, stderr

    def say(self, *args, **kwargs):
        self.said.append(" ".join(str(a) for a in args))

    def run(self, argv, **kwargs):
        self.ran.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, self.code, stdout=self.stdout, stderr=self.stderr)

    def open_url(self, url):
        self.opened.append(url)

    def detach(self, args, log):
        self.detached.append((args, log))

    def which(self, name):
        return self.paths.get(name)

    @property
    def text(self):
        return "\n".join(self.said)


def make_connector(tmp_path, rec=None, platform="darwin", environ=None):
    ctx = make_ctx(tmp_path, environ)
    rec = rec or Recorder()
    user_home = tmp_path / "user"
    user_home.mkdir(exist_ok=True)
    conn = connect.Connector(
        ctx, platform=platform, user_home=user_home, which=rec.which, run=rec.run,
        open_url=rec.open_url, running=lambda: rec.running, detach=rec.detach,
        apply=lambda home, env: None, now=lambda: FIXED_NOW, say=rec.say,
        shim=lambda: SHIM, sleep=lambda s: None, settle=0.0,
    )
    return conn, rec


def desktop_config(conn):
    return conn.desktop_config


def write_config(conn, data):
    path = desktop_config(conn)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


ENTRY = {"command": str(SHIM), "args": ["mcp"]}


# --- Claude Desktop: where the config lives -----------------------------------------------

@pytest.mark.parametrize("platform, environ, tail", [
    ("darwin", {}, "Library/Application Support/Claude/claude_desktop_config.json"),
    ("win32", {"APPDATA": "C:/Users/me/AppData/Roaming"},
     "C:/Users/me/AppData/Roaming/Claude/claude_desktop_config.json"),
    ("linux", {}, ".config/Claude/claude_desktop_config.json"),
])
def test_desktop_config_path_per_platform(tmp_path, platform, environ, tail):
    path = connect.desktop_config_path(platform, environ, tmp_path)
    assert path.as_posix().endswith(tail)
    if platform != "win32":
        assert path.as_posix().startswith(tmp_path.as_posix())


def test_windows_without_appdata_falls_back_to_the_roaming_folder(tmp_path):
    path = connect.desktop_config_path("win32", {}, tmp_path)
    assert path == tmp_path / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"


# --- Claude Desktop: the write ------------------------------------------------------------

def test_a_missing_config_is_created_with_the_absolute_shim_path(tmp_path):
    conn, rec = make_connector(tmp_path)
    assert conn.connect("claude-desktop") == 0
    written = json.loads(desktop_config(conn).read_text(encoding="utf-8"))
    entry = written["mcpServers"]["maestro-career-studio"]
    assert entry == ENTRY
    assert Path(entry["command"]).is_absolute() and entry["command"] == str(SHIM)
    assert "Open Claude Desktop to load Maestro." in rec.text
    assert not list(desktop_config(conn).parent.glob("*.bak-*"))  # nothing existed to back up
    assert rec.detached == []


def test_the_merge_keeps_other_servers_and_other_keys(tmp_path):
    conn, rec = make_connector(tmp_path)
    original = {
        "mcpServers": {"playwright": {"command": "npx", "args": ["x"]}},
        "preferences": {"sidebarMode": "chat"},
        "coworkUserFilesPath": "/somewhere",
    }
    path = write_config(conn, original)
    assert conn.connect("claude-desktop") == 0
    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["mcpServers"]["playwright"] == original["mcpServers"]["playwright"]
    assert after["preferences"] == original["preferences"]
    assert after["coworkUserFilesPath"] == "/somewhere"
    assert after["mcpServers"]["maestro-career-studio"] == ENTRY


def test_a_backup_of_the_old_file_is_made_before_the_write(tmp_path):
    conn, rec = make_connector(tmp_path)
    original = {"mcpServers": {"kb": {"command": "k"}}}
    path = write_config(conn, original)
    before = path.read_bytes()
    conn.connect("claude-desktop")
    backups = list(path.parent.glob("claude_desktop_config.json.bak-*"))
    assert [b.name for b in backups] == ["claude_desktop_config.json.bak-20261010T123005Z"]
    assert backups[0].read_bytes() == before
    assert "claude_desktop_config.json.bak-20261010T123005Z" in rec.text


def test_a_profile_adds_the_profile_argument(tmp_path):
    conn, _ = make_connector(tmp_path)
    conn.connect("claude-desktop", profile="hunt")
    entry = json.loads(desktop_config(conn).read_text())["mcpServers"]["maestro-career-studio"]
    assert entry["args"] == ["mcp", "--profile", "hunt"]


def test_an_old_set_name_is_saved_as_its_new_name(tmp_path):
    """`career` and `explore` work for one release; a saved config must outlive the alias."""
    conn, _ = make_connector(tmp_path)
    conn.connect("claude-desktop", profile="career")
    entry = json.loads(desktop_config(conn).read_text())["mcpServers"]["maestro-career-studio"]
    assert entry["args"] == ["mcp", "--profile", "profile"]


def test_a_custom_maestro_home_is_pinned_in_the_desktop_entry(tmp_path):
    custom = tmp_path / "my maestro"
    conn, _ = make_connector(tmp_path, environ={"MAESTRO_HOME": str(custom)})
    assert conn.connect("claude-desktop") == 0
    entry = json.loads(desktop_config(conn).read_text())["mcpServers"]["maestro-career-studio"]
    assert entry == {**ENTRY, "env": {"MAESTRO_HOME": str(conn.ctx.home)}}
    assert Path(entry["env"]["MAESTRO_HOME"]).is_absolute()
    # the printed snippet shows it too
    rec_text = []
    conn.say = lambda *a, **k: rec_text.append(" ".join(map(str, a)))
    conn.connect("claude-desktop", print_only=True)
    assert "MAESTRO_HOME" in "\n".join(rec_text)


def test_the_waiters_pinned_default_folder_adds_no_env(tmp_path):
    # spawn_detached always pins MAESTRO_HOME, so the waiter must judge by the folder, not the variable.
    conn, _ = make_connector(tmp_path)
    default = Path(os.path.abspath(
        connect.home_mod.default_home("darwin", {}, conn.user_home)))
    conn.ctx = Context(default, {}, Ports(18001, 13000), {"MAESTRO_HOME": str(default)}, "9.9.9")
    assert conn._entry("full") == ENTRY


def test_the_default_install_folder_adds_no_env_to_the_desktop_entry(tmp_path):
    conn, _ = make_connector(tmp_path)
    conn.connect("claude-desktop")
    assert json.loads(desktop_config(conn).read_text())["mcpServers"]["maestro-career-studio"] == ENTRY
    assert connect.desktop_entry("full", SHIM) == ENTRY
    assert connect.desktop_entry("hunt", SHIM, Path("/h"))["env"] == {"MAESTRO_HOME": str(Path("/h"))}


def test_an_entry_that_is_already_right_is_left_alone(tmp_path):
    conn, rec = make_connector(tmp_path)
    path = write_config(conn, {"mcpServers": {"maestro-career-studio": ENTRY}})
    before = path.read_bytes()
    assert conn.connect("claude-desktop") == 0
    assert path.read_bytes() == before
    assert not list(path.parent.glob("*.bak-*"))
    assert "already" in rec.text.lower()


@pytest.mark.parametrize("content", ["{not json", "[1, 2]", '"text"'])
def test_a_config_that_is_not_a_json_object_is_never_overwritten(tmp_path, content):
    conn, rec = make_connector(tmp_path)
    path = desktop_config(conn)
    path.parent.mkdir(parents=True)
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ControlError) as caught:
        conn.connect("claude-desktop")
    assert "left it alone" in str(caught.value)
    assert path.read_text(encoding="utf-8") == content
    assert not list(path.parent.glob("*.bak-*"))
    assert rec.detached == []


def test_mcp_servers_of_the_wrong_type_is_refused_untouched(tmp_path):
    conn, _ = make_connector(tmp_path)
    path = write_config(conn, {"mcpServers": ["oops"]})
    before = path.read_bytes()
    with pytest.raises(ControlError, match="mcpServers"):
        conn.connect("claude-desktop")
    assert path.read_bytes() == before


def test_an_empty_config_file_counts_as_nothing_to_lose(tmp_path):
    conn, _ = make_connector(tmp_path)
    path = desktop_config(conn)
    path.parent.mkdir(parents=True)
    path.write_text("  \n", encoding="utf-8")
    assert conn.connect("claude-desktop") == 0
    assert json.loads(path.read_text())["mcpServers"]["maestro-career-studio"] == ENTRY


def test_a_failed_write_leaves_the_config_and_names_the_reason(tmp_path, monkeypatch):
    conn, _ = make_connector(tmp_path)
    path = write_config(conn, {"mcpServers": {}})
    before = path.read_bytes()

    def boom(src, dst):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(connect.os, "replace", boom)
    with pytest.raises(ControlError, match="Permission denied"):
        conn.connect("claude-desktop")
    assert path.read_bytes() == before
    assert not list(path.parent.glob("*.tmp*"))


def test_a_write_that_does_not_stick_is_reported(tmp_path, monkeypatch):
    conn, rec = make_connector(tmp_path)
    path = write_config(conn, {"mcpServers": {"kb": {"command": "k"}}})
    real = connect.write_json_atomic

    def lossy(target, data):  # Claude Desktop rewriting its in-memory list straight away
        real(target, {"mcpServers": {"kb": {"command": "k"}}})

    monkeypatch.setattr(connect, "write_json_atomic", lossy)
    assert conn.connect("claude-desktop") == 1
    assert "missing" in rec.text.lower()
    assert "quit Claude Desktop" in rec.text
    assert json.loads(path.read_text())["mcpServers"] == {"kb": {"command": "k"}}


def test_the_old_docker_bundle_gets_a_removal_hint_only_when_it_is_there(tmp_path):
    conn, rec = make_connector(tmp_path)
    conn.connect("claude-desktop")
    assert "Extensions" not in rec.text
    ext = desktop_config(conn).parent / "Claude Extensions" / "local.mcpb.me.maestro-career-studio"
    ext.mkdir(parents=True)
    conn2, rec2 = make_connector(tmp_path)
    write = desktop_config(conn2)
    write.unlink()
    conn2.connect("claude-desktop")
    assert "remove it in Settings › Extensions" in rec2.text


def test_print_shows_the_snippet_and_writes_nothing(tmp_path):
    conn, rec = make_connector(tmp_path)
    assert conn.connect("claude-desktop", print_only=True) == 0
    assert not desktop_config(conn).exists()
    assert '"maestro-career-studio"' in rec.text and json.dumps(str(SHIM)) in rec.text
    assert str(desktop_config(conn)) in rec.text


# --- Claude Desktop: running, so the write waits ------------------------------------------

def test_a_running_desktop_defers_the_write_to_the_detached_waiter(tmp_path):
    conn, rec = make_connector(tmp_path, Recorder(running=True))
    path = write_config(conn, {"mcpServers": {"kb": {"command": "k"}}})
    before = path.read_bytes()
    assert conn.connect("claude-desktop", profile="hunt") == 0
    assert path.read_bytes() == before  # nothing written in-process
    assert not list(path.parent.glob("*.bak-*"))
    assert rec.detached == [
        (["_connect-desktop-when-closed", "--profile", "hunt"], conn.ctx.logs_dir / "connect.log")
    ]
    assert "Quit Claude Desktop fully (not just close the window); " \
           "Maestro will add itself as soon as it has quit." in rec.text
    assert "connect.log" in rec.text


def test_a_running_desktop_with_a_broken_config_is_refused_before_waiting(tmp_path):
    conn, rec = make_connector(tmp_path, Recorder(running=True))
    path = desktop_config(conn)
    path.parent.mkdir(parents=True)
    path.write_text("{oops", encoding="utf-8")
    with pytest.raises(ControlError):
        conn.connect("claude-desktop")
    assert rec.detached == []


def test_now_writes_at_once_even_when_desktop_runs_and_warns(tmp_path):
    conn, rec = make_connector(tmp_path, Recorder(running=True))
    write_config(conn, {"mcpServers": {}})
    assert conn.connect("claude-desktop", now=True) == 0
    assert rec.detached == []
    assert json.loads(desktop_config(conn).read_text())["mcpServers"]["maestro-career-studio"] == ENTRY
    assert "may overwrite" in rec.text


def test_a_detach_failure_is_a_sentence(tmp_path):
    rec = Recorder(running=True)

    def failing(args, log):
        raise detach.DetachError("Couldn't start the background step: python could not be run.")

    rec.detach = failing
    conn, _ = make_connector(tmp_path, rec)
    with pytest.raises(ControlError, match="background step"):
        conn.connect("claude-desktop")


# --- the waiter ---------------------------------------------------------------------------

def test_the_waiter_writes_once_desktop_has_quit_and_logs_it(tmp_path):
    state = {"polls": 0}
    rec = Recorder(running=True)
    conn, _ = make_connector(tmp_path, rec)
    path = write_config(conn, {"mcpServers": {"kb": {"command": "k"}}})

    def sleeper(seconds):
        state["polls"] += 1
        if state["polls"] == 3:
            rec.running = False

    conn.sleep = sleeper
    ticks = iter(range(10_000))
    conn.clock = lambda: float(next(ticks))
    assert conn.wait_and_write("full", timeout=600.0, poll=1.0) == 0
    assert state["polls"] == 3
    after = json.loads(path.read_text())
    assert after["mcpServers"]["maestro-career-studio"] == ENTRY
    assert after["mcpServers"]["kb"] == {"command": "k"}
    assert len(list(path.parent.glob("*.bak-*"))) == 1
    assert "Added Maestro to Claude Desktop" in rec.text


def test_the_waiter_gives_up_after_its_deadline_without_writing(tmp_path):
    rec = Recorder(running=True)
    conn, _ = make_connector(tmp_path, rec)
    path = write_config(conn, {"mcpServers": {}})
    before = path.read_bytes()
    ticks = iter(range(0, 10_000, 100))
    conn.clock = lambda: float(next(ticks))
    assert conn.wait_and_write("full", timeout=600.0, poll=1.0) == 1
    assert path.read_bytes() == before
    assert "still running" in rec.text and "maestro connect claude-desktop" in rec.text


def test_the_waiter_logs_a_broken_config_instead_of_raising(tmp_path):
    rec = Recorder(running=False)
    conn, _ = make_connector(tmp_path, rec)
    path = desktop_config(conn)
    path.parent.mkdir(parents=True)
    path.write_text("{oops", encoding="utf-8")
    assert conn.wait_and_write("full", timeout=10.0, poll=1.0) == 1
    assert "left it alone" in rec.text
    assert path.read_text() == "{oops"


# --- recognising Claude Desktop -----------------------------------------------------------

@pytest.mark.parametrize("platform, name, exe, cmdline, expected", [
    # macOS: the app's main executable only.
    ("darwin", "Claude", "/Applications/Claude.app/Contents/MacOS/Claude", [], True),
    ("darwin", "Claude", "/Users/me/Applications/Claude.app/Contents/MacOS/Claude", [], True),
    ("darwin", "Claude Helper", "/Applications/Claude.app/Contents/Frameworks/Claude Helper.app/"
     "Contents/MacOS/Claude Helper", [], False),
    # Claude Code, the CLI, bundled inside Desktop's data folder and on its own:
    ("darwin", "claude", "/Users/me/Library/Application Support/Claude/claude-code/2.1.295/abc/"
     "claude.app/Contents/MacOS/claude", [], False),
    ("darwin", "claude", "/Users/me/.local/bin/claude", ["claude"], False),
    ("darwin", "node", "/usr/local/bin/node", ["node", "/x/claude-code/cli.js"], False),
    ("darwin", "Claude", None, ["/Applications/Claude.app/Contents/MacOS/Claude"], True),
    # Windows: claude.exe is both Desktop and Claude Code; only the install folder tells them apart.
    ("win32", "claude.exe", r"C:\Users\me\AppData\Local\AnthropicClaude\app-0.14.0\claude.exe", [], True),
    ("win32", "Claude.exe", r"C:\Program Files\WindowsApps\Claude_1.0.0.0_x64__pzs8sxrjxfjjc"
     r"\app\Claude.exe", [], True),
    ("win32", "claude.exe", r"C:\Users\me\.local\bin\claude.exe", [], False),
    ("win32", "claude.exe", r"C:\Users\me\AppData\Roaming\npm\claude.exe", [], False),
    ("win32", "claude.exe", None, [], True),   # exe unreadable: a protected app folder
    ("win32", "node.exe", r"C:\Program Files\nodejs\node.exe", [], False),
    # Linux: unofficial builds only; the claude CLI must never match.
    ("linux", "claude-desktop", "/usr/bin/claude-desktop", [], True),
    ("linux", "electron", "/usr/lib/claude-desktop/node_modules/electron/dist/electron",
     ["/usr/lib/claude-desktop/node_modules/electron/dist/electron", "/usr/lib/claude-desktop/app.asar"],
     True),
    ("linux", "claude", "/home/me/.local/bin/claude", ["claude"], False),
    ("linux", "node", "/usr/bin/node", ["node", "/usr/lib/node_modules/@anthropic-ai/claude-code/cli.js"],
     False),
])
def test_only_the_desktop_app_is_recognised(platform, name, exe, cmdline, expected):
    assert connect.is_desktop_process(platform, name, exe, cmdline) is expected


class FakeProc:
    def __init__(self, name, exe, cmdline, denied=False):
        self.info = {"name": name, "exe": exe, "cmdline": cmdline}
        self.denied = denied


def test_desktop_running_reads_the_process_list():
    desktop = FakeProc("Claude", "/Applications/Claude.app/Contents/MacOS/Claude", [])
    cli_proc = FakeProc("claude", "/x/claude.app/Contents/MacOS/claude", ["claude"])
    assert connect.desktop_running("darwin", lambda attrs: [cli_proc, desktop]) is True
    assert connect.desktop_running("darwin", lambda attrs: [cli_proc]) is False


def test_desktop_running_survives_unreadable_processes():
    broken = FakeProc("Claude", None, None)
    broken.info = {"name": None, "exe": None, "cmdline": None}
    assert connect.desktop_running("darwin", lambda attrs: [broken]) is False


# --- the other clients --------------------------------------------------------------------

def build_for(conn):
    from app.services import connect as card

    return card.build("full")


@pytest.mark.parametrize("client, binary, expected_lead", [
    ("claude-code", "claude", ["mcp", "add", "--scope", "user", "--transport", "http"]),
    ("codex", "codex", ["mcp", "add", "maestro-career-studio", "--url"]),
])
def test_cli_clients_run_the_command_when_the_binary_exists(tmp_path, client, binary, expected_lead):
    rec = Recorder(which={binary: f"/usr/bin/{binary}"}, stdout="Added\n")
    conn, _ = make_connector(tmp_path, rec)
    assert conn.connect(client) == 0
    argv, kwargs = rec.ran[0]
    assert argv[0] == f"/usr/bin/{binary}"
    assert argv[1:1 + len(expected_lead)] == expected_lead
    assert argv[-1] == build_for(conn).mcp_url
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert "Added Maestro" in rec.text


def test_the_claude_code_command_is_exactly_what_the_card_shows(tmp_path):
    rec = Recorder(which={"claude": "/usr/bin/claude"})
    conn, _ = make_connector(tmp_path, rec)
    conn.connect("claude-code")
    card = next(c for c in build_for(conn).clients if c.id == "claude-code")
    assert " ".join(["claude", *rec.ran[0][0][1:]]) == card.value
    assert "--scope user" in card.value


def _applying_maestro_env(monkeypatch):
    """An `apply` that puts maestro.env secrets into os.environ, as the real `apply_env` does."""
    def apply(home, env):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-from-maestro-env")
    return apply


@pytest.mark.parametrize("client, binary", [("claude-code", "claude"), ("codex", "codex")])
@pytest.mark.parametrize("platform", ["linux", "win32"])
def test_the_agent_cli_never_inherits_the_secrets_from_maestro_env(tmp_path, monkeypatch, client, binary, platform):
    monkeypatch.setattr(sys, "platform", platform)
    for name, value in {"SYSTEMROOT": "C:/Windows", "WINDIR": "C:/Windows",
                        "COMSPEC": "C:/Windows/System32/cmd.exe", "PATHEXT": ".COM;.EXE;.BAT;.CMD"}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    rec = Recorder(which={binary: f"/usr/bin/{binary}"})
    conn, _ = make_connector(tmp_path, rec, environ={"MARKER": "parent"})
    conn._apply = _applying_maestro_env(monkeypatch)
    assert conn.connect(client) == 0
    assert os.environ["OPENAI_API_KEY"] == "sk-from-maestro-env"  # apply really ran
    env = rec.ran[0][1]["env"]
    assert "OPENAI_API_KEY" not in env and env["MARKER"] == "parent"
    parent = dict(conn.ctx.environ)
    assert parent.items() <= env.items()
    allowed_additions = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT"} if platform == "win32" else set()
    assert env.keys() - parent.keys() <= allowed_additions


def test_the_browser_opener_never_inherits_the_secrets_and_the_environment_comes_back(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    rec = Recorder()
    conn, _ = make_connector(tmp_path, rec, environ={"MARKER": "parent"})
    conn._apply = _applying_maestro_env(monkeypatch)
    seen = {}

    def opener(url):
        seen["key"] = os.environ.get("OPENAI_API_KEY")
        seen["marker"] = os.environ.get("MARKER")

    conn.open_url = opener
    assert conn.connect("cursor") == 0
    assert seen == {"key": None, "marker": "parent"}
    assert os.environ["OPENAI_API_KEY"] == "sk-from-maestro-env"  # restored after the call


@pytest.mark.parametrize("client", ["claude-code", "codex"])
def test_print_never_runs_anything(tmp_path, client):
    rec = Recorder(which={"claude": "/usr/bin/claude", "codex": "/usr/bin/codex"})
    conn, _ = make_connector(tmp_path, rec)
    assert conn.connect(client, print_only=True) == 0
    assert rec.ran == []
    card = next(c for c in build_for(conn).clients if c.id == client)
    assert card.value in rec.text


@pytest.mark.parametrize("client", ["claude-code", "codex"])
def test_a_missing_binary_prints_the_command_to_run_by_hand(tmp_path, client):
    conn, rec = make_connector(tmp_path)
    assert conn.connect(client) == 0
    assert rec.ran == []
    card = next(c for c in build_for(conn).clients if c.id == client)
    assert card.value in rec.text
    assert "isn't on your PATH" in rec.text


def test_a_refusal_from_the_cli_is_one_sentence_with_exit_one(tmp_path):
    rec = Recorder(which={"claude": "/usr/bin/claude"}, code=1,
                   stderr="noise\nMCP server maestro-career-studio already exists in user config\n")
    conn, _ = make_connector(tmp_path, rec)
    assert conn.connect("claude-code") == 1
    assert "already exists in user config" in rec.text
    assert "Claude Code didn't add Maestro" in rec.text


def test_a_cli_that_cannot_be_run_is_a_sentence(tmp_path):
    rec = Recorder(which={"claude": "/usr/bin/claude"})

    def broken(argv, **kwargs):
        raise OSError(8, "Exec format error")

    rec.run = broken
    conn, _ = make_connector(tmp_path, rec)
    with pytest.raises(ControlError, match="Exec format error"):
        conn.connect("claude-code")


@pytest.mark.parametrize("client", ["cursor", "vscode"])
def test_deep_links_match_the_card_and_open_unless_printing(tmp_path, client):
    conn, rec = make_connector(tmp_path)
    card = next(c for c in build_for(conn).clients if c.id == client)
    assert conn.connect(client) == 0
    assert card.value in rec.text
    assert rec.opened == [card.value]
    rec.said.clear(), rec.opened.clear()
    assert conn.connect(client, print_only=True) == 0
    assert card.value in rec.text and rec.opened == []


def test_a_browser_that_will_not_open_a_link_is_not_an_error(tmp_path):
    conn, rec = make_connector(tmp_path)

    def broken(url):
        raise RuntimeError("no handler")

    conn.open_url = broken
    assert conn.connect("cursor") == 0
    assert "Open the link above" in rec.text


def test_other_prints_the_url_for_the_profile(tmp_path):
    conn, rec = make_connector(tmp_path)
    assert conn.connect("other", profile="hunt") == 0
    assert build_for(conn).mcp_url.rsplit("/mcp", 1)[0] + "/mcp/hunt" in rec.text


def test_an_unknown_profile_names_the_choices(tmp_path):
    conn, _ = make_connector(tmp_path)
    with pytest.raises(ControlError, match="hunt"):
        conn.connect("other", profile="nonsense")


# --- the listing --------------------------------------------------------------------------

def test_listing_reports_what_is_configured_and_runs_nothing(tmp_path):
    rec = Recorder(which={"claude": "/usr/bin/claude"})
    conn, _ = make_connector(tmp_path, rec)
    write_config(conn, {"mcpServers": {"maestro-career-studio": ENTRY}})
    user_home = conn.user_home
    (user_home / ".claude.json").write_text(json.dumps({
        "mcpServers": {},
        "projects": {"/some/project": {"mcpServers": {"maestro-career-studio": {"type": "http"}}}},
    }), encoding="utf-8")
    (user_home / ".codex").mkdir()
    (user_home / ".codex" / "config.toml").write_text(
        '[mcp_servers.maestro-career-studio]\nurl = "http://localhost:8001/mcp"\n', encoding="utf-8")
    assert conn.connect(None) == 0
    out = rec.text
    lines = {ln.split()[0]: ln for ln in out.splitlines() if ln.startswith("  ")}
    assert "added" in lines["claude-desktop"]
    assert "one project" in lines["claude-code"]
    assert "added" in lines["codex"]
    for client in ("cursor", "vscode", "other"):
        assert client in lines
    assert rec.ran == [] and rec.opened == [] and rec.detached == []


def test_listing_marks_user_scope_and_missing_configs(tmp_path):
    conn, rec = make_connector(tmp_path)
    (conn.user_home / ".claude.json").write_text(
        json.dumps({"mcpServers": {"maestro-career-studio": {"type": "http"}}}), encoding="utf-8")
    conn.connect(None)
    lines = {ln.split()[0]: ln for ln in rec.text.splitlines() if ln.startswith("  ")}
    assert "every folder" in lines["claude-code"]
    assert "not added" in lines["claude-desktop"]
    assert "not added" in lines["codex"]


def test_listing_survives_unreadable_configs(tmp_path):
    conn, rec = make_connector(tmp_path)
    path = write_config(conn, {})
    path.write_text("{oops", encoding="utf-8")
    (conn.user_home / ".claude.json").write_text("nope", encoding="utf-8")
    (conn.user_home / ".codex").mkdir()
    (conn.user_home / ".codex" / "config.toml").write_text("[[[", encoding="utf-8")
    assert conn.connect(None) == 0
    assert rec.text.count("couldn't read") == 3


def test_claude_config_dir_and_codex_home_are_honoured(tmp_path):
    custom = tmp_path / "elsewhere"
    custom.mkdir()
    (custom / ".claude.json").write_text(
        json.dumps({"mcpServers": {"maestro-career-studio": {}}}), encoding="utf-8")
    codex = tmp_path / "codexhome"
    codex.mkdir()
    (codex / "config.toml").write_text("[mcp_servers.maestro-career-studio]\nurl='u'\n", encoding="utf-8")
    conn, rec = make_connector(
        tmp_path, environ={"CLAUDE_CONFIG_DIR": str(custom), "CODEX_HOME": str(codex)})
    conn.connect(None)
    lines = {ln.split()[0]: ln for ln in rec.text.splitlines() if ln.startswith("  ")}
    assert "every folder" in lines["claude-code"] and "added" in lines["codex"]


# --- the detach helper (reused by Task 11) ------------------------------------------------

@pytest.mark.parametrize("platform, flags", [
    ("linux", {"start_new_session": True}),
    ("darwin", {"start_new_session": True}),
    ("win32", {"creationflags": detach.CREATE_NEW_PROCESS_GROUP | detach.CREATE_NO_WINDOW
               | detach.CREATE_BREAKAWAY_FROM_JOB}),
])
def test_detach_spawns_the_package_module_with_the_right_flags(tmp_path, platform, flags, monkeypatch):
    calls = []
    system = {"SYSTEMROOT": "system-root", "WINDIR": "windows-dir",
              "COMSPEC": "shell", "PATHEXT": ".EXE;.CMD"}
    for name, value in system.items():
        monkeypatch.setenv(name, value)

    def popen(argv, **kwargs):
        calls.append((argv, kwargs))
        return object()

    log = tmp_path / "logs" / "x.log"
    log.parent.mkdir()
    detach.spawn_detached(["hello", "--x"], log=log, home=tmp_path, env={"A": "1"}, popen=popen,
                          platform=platform, executable="/venv/bin/python")
    argv, kwargs = calls[0]
    assert argv[1:] == ["-m", "maestro_cs", "hello", "--x"]
    assert kwargs["cwd"] == tmp_path and kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["stderr"] is subprocess.STDOUT
    expected = {"A": "1", "MAESTRO_HOME": str(tmp_path)}
    if platform == "win32":
        expected.update(system)
    assert kwargs["env"] == expected
    for key, value in flags.items():
        assert kwargs[key] == value
    if platform != "win32":
        assert "creationflags" not in kwargs
    assert log.exists()


def test_detach_on_windows_retries_without_breakaway_when_the_job_forbids_it(tmp_path):
    calls = []

    def popen(argv, **kwargs):
        calls.append(kwargs["creationflags"])
        if kwargs["creationflags"] & detach.CREATE_BREAKAWAY_FROM_JOB:
            raise PermissionError(5, "Access is denied")
        return "child"

    got = detach.spawn_detached(["a"], log=tmp_path / "x.log", home=tmp_path, popen=popen,
                                platform="win32", executable=r"C:\v\Scripts\python.exe")
    base = detach.CREATE_NEW_PROCESS_GROUP | detach.CREATE_NO_WINDOW
    assert got == "child" and calls == [base | detach.CREATE_BREAKAWAY_FROM_JOB, base]


def test_a_failure_that_is_not_about_the_job_still_surfaces_after_the_retry(tmp_path):
    def broken(argv, **kwargs):
        raise OSError(2, "No such file or directory")

    with pytest.raises(detach.DetachError, match="No such file or directory"):
        detach.spawn_detached(["a"], log=tmp_path / "x.log", home=tmp_path, popen=broken,
                              platform="win32", executable=r"C:\nope\python.exe")


def test_detach_on_windows_uses_the_console_interpreter(tmp_path):
    calls = []
    log = tmp_path / "x.log"
    detach.spawn_detached(["a"], log=log, home=tmp_path, popen=lambda a, **k: calls.append(a),
                          platform="win32", executable=r"C:\v\Scripts\pythonw.exe")
    assert Path(calls[0][0]).name == "python.exe"


def test_detach_turns_a_spawn_failure_into_a_sentence(tmp_path):
    def broken(argv, **kwargs):
        raise OSError(2, "No such file or directory")

    with pytest.raises(detach.DetachError, match="No such file or directory"):
        detach.spawn_detached(["a"], log=tmp_path / "x.log", home=tmp_path, popen=broken,
                              platform="linux", executable="/nope/python")


# --- the command line ---------------------------------------------------------------------

class FakeConnector:
    calls = []

    def __init__(self, ctx):
        self.ctx = ctx

    def connect(self, client, profile="full", print_only=False, now=False):
        FakeConnector.calls.append(("connect", client, profile, print_only, now))
        return 0

    def wait_and_write(self, profile="full", timeout=600.0, **kwargs):
        FakeConnector.calls.append(("wait", profile, timeout))
        return 0


@pytest.fixture
def fake(monkeypatch, tmp_path):
    FakeConnector.calls = []
    monkeypatch.setenv("MAESTRO_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(connect, "Connector", FakeConnector)
    return FakeConnector


def test_connect_flags_reach_the_connector(fake):
    assert cli.main(["connect", "claude-desktop", "--profile", "hunt", "--print", "--now"]) == 0
    assert fake.calls == [("connect", "claude-desktop", "hunt", True, True)]


def test_connect_without_a_client_lists(fake):
    cli.main(["connect"])
    assert fake.calls == [("connect", None, "full", False, False)]


def test_connect_rejects_an_unknown_client(fake, capsys):
    assert cli.main(["connect", "emacs"]) == 2
    assert "invalid choice" in capsys.readouterr().err


def test_the_waiter_verb_is_hidden_but_works(fake, capsys):
    cli.main(["--help"])
    assert "_connect-desktop-when-closed" not in capsys.readouterr().out
    assert cli.main(["_connect-desktop-when-closed", "--profile", "apply", "--timeout", "5"]) == 0
    assert fake.calls == [("wait", "apply", 5.0)]


def test_a_control_error_prints_one_sentence(monkeypatch, tmp_path, capsys):
    class Failing(FakeConnector):
        def connect(self, *args, **kwargs):
            raise ControlError("Nope, because reasons.")

    monkeypatch.setenv("MAESTRO_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(connect, "Connector", Failing)
    assert cli.main(["connect", "other"]) == 1
    assert capsys.readouterr().err.strip() == "Nope, because reasons."


# --- real processes: environment order, never the developer's home ------------------------

def test_the_command_runs_in_a_fresh_process_without_the_developers_environment(tmp_path):
    home = tmp_path / "home"
    user_home = tmp_path / "user"
    user_home.mkdir()
    env = {k: v for k, v in os.environ.items()
           if k.upper() not in {"MAESTRO_HOME", "DATABASE_URL", "OPENAI_API_KEY", "GEMINI_API_KEY",
                              "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"}}
    env.update({"MAESTRO_HOME": str(home), "HOME": str(user_home), "USERPROFILE": str(user_home),
                "MAESTRO_PORT": "18911", "MAESTRO_WEB_PORT": "18912", "XDG_CONFIG_HOME": str(user_home / "c"),
                "PATH": "/nonexistent"})
    done = subprocess.run(
        [sys.executable, "-m", "maestro_cs", "connect", "other", "--profile", "hunt"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60, check=False)
    assert done.returncode == 0, done.stderr
    assert "http://localhost:18911/mcp/hunt" in done.stdout
    done = subprocess.run(
        [sys.executable, "-m", "maestro_cs", "connect", "claude-desktop", "--print"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60, check=False)
    assert done.returncode == 0, done.stderr
    assert "maestro" in done.stdout and "mcpServers" in done.stdout
    snippet = json.loads(done.stdout[done.stdout.index("{"):])
    command = snippet["mcpServers"]["maestro-career-studio"]["command"]
    assert Path(command).name.lower() == ("maestro.exe" if sys.platform == "win32" else "maestro")
    assert not list(user_home.rglob("claude_desktop_config.json"))


def test_the_card_strings_come_from_build_not_a_second_copy():
    source = (BACKEND / "maestro_cs" / "connect.py").read_text(encoding="utf-8")
    assert "cursor-deeplink" not in source and "vscode:mcp" not in source
    assert "services.connect" in source
    assert control.ControlError is ControlError


# --- review follow-ups --------------------------------------------------------------------

def test_a_symlinked_config_stays_a_symlink_and_its_target_gets_the_entry(tmp_path):
    conn, rec = make_connector(tmp_path)
    target = tmp_path / "dotfiles" / "claude_desktop_config.json"
    target.parent.mkdir()
    target.write_text(json.dumps({"mcpServers": {"kb": {"command": "k"}}}), encoding="utf-8")
    link = desktop_config(conn)
    link.parent.mkdir(parents=True)
    link.symlink_to(target)
    assert conn.connect("claude-desktop") == 0
    assert link.is_symlink() and Path(os.path.realpath(link)) == target.resolve()
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["mcpServers"]["maestro-career-studio"] == ENTRY
    assert data["mcpServers"]["kb"] == {"command": "k"}
    # backup and temp file sit beside the target, not the link
    assert len(list(target.parent.glob("claude_desktop_config.json.bak-*"))) == 1
    assert not list(link.parent.glob("*.bak-*")) and not list(target.parent.glob("*.tmp*"))


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_a_private_config_stays_private(tmp_path):
    conn, _ = make_connector(tmp_path)
    path = write_config(conn, {"mcpServers": {}})
    path.chmod(0o600)
    conn.connect("claude-desktop")
    assert path.stat().st_mode & 0o777 == 0o600
    backup = next(path.parent.glob("*.bak-*"))
    assert backup.stat().st_mode & 0o777 == 0o600


def test_a_backup_name_collision_gets_a_suffix_and_never_overwrites(tmp_path):
    conn, rec = make_connector(tmp_path)
    path = write_config(conn, {"mcpServers": {"kb": {"command": "k"}}})
    older = path.with_name("claude_desktop_config.json.bak-20261010T123005Z")
    older.write_text("older backup", encoding="utf-8")
    before = path.read_bytes()
    conn.connect("claude-desktop")
    assert older.read_text(encoding="utf-8") == "older backup"
    newer = path.with_name("claude_desktop_config.json.bak-20261010T123005Z-1")
    assert newer.read_bytes() == before
    assert "bak-20261010T123005Z-1" in rec.text


def test_msix_config_is_used_only_when_exactly_one_package_folder_has_it(tmp_path):
    local, roaming = tmp_path / "Local", tmp_path / "Roaming"
    environ = {"LOCALAPPDATA": str(local), "APPDATA": str(roaming)}
    plain = roaming / "Claude" / "claude_desktop_config.json"
    assert connect.desktop_config_path("win32", environ, tmp_path) == plain
    (local / "Packages" / "Claude_pzs8sxrjxfjjc").mkdir(parents=True)  # no LocalCache yet
    assert connect.desktop_config_path("win32", environ, tmp_path) == plain
    store = local / "Packages" / "Claude_pzs8sxrjxfjjc" / "LocalCache" / "Roaming" / "Claude"
    store.mkdir(parents=True)
    assert connect.desktop_config_path("win32", environ, tmp_path) == store / "claude_desktop_config.json"
    other = local / "Packages" / "Claude_other" / "LocalCache" / "Roaming" / "Claude"
    other.mkdir(parents=True)  # ambiguous: fall back to %APPDATA%
    assert connect.desktop_config_path("win32", environ, tmp_path) == plain
    assert connect.desktop_config_path("darwin", environ, tmp_path).parts[-3:-1] == (
        "Application Support", "Claude")


def test_the_waiter_keeps_waiting_when_desktop_relaunches_during_the_pause(tmp_path):
    rec = Recorder()
    conn, _ = make_connector(tmp_path, rec)
    conn.settle = 1.0
    path = write_config(conn, {"mcpServers": {}})
    answers = iter([True, False, True, False, False])  # quit, relaunched in the pause, quit again
    conn.running = lambda: next(answers)
    ticks = iter(range(10_000))
    conn.clock = lambda: float(next(ticks))
    assert conn.wait_and_write("full", timeout=600.0, poll=1.0) == 0
    assert "came back" in rec.text
    assert json.loads(path.read_text())["mcpServers"]["maestro-career-studio"] == ENTRY


def test_a_relaunched_desktop_still_honours_the_original_deadline(tmp_path):
    rec = Recorder()
    conn, _ = make_connector(tmp_path, rec)
    conn.settle = 1.0
    path = write_config(conn, {"mcpServers": {}})
    before = path.read_bytes()
    answers = iter([False, True] + [True] * 50)
    conn.running = lambda: next(answers)
    ticks = iter(range(0, 10_000, 100))
    conn.clock = lambda: float(next(ticks))
    assert conn.wait_and_write("full", timeout=600.0, poll=1.0) == 1
    assert path.read_bytes() == before and "still running" in rec.text


def _sleeper():
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])


def test_a_new_deferral_stops_a_live_earlier_waiter(tmp_path):
    from maestro_cs import procs

    conn, rec = make_connector(tmp_path, Recorder(running=True))
    write_config(conn, {"mcpServers": {}})
    old = _sleeper()
    try:
        procs.write_record(conn.waiter_record, old.pid)
        conn.connect("claude-desktop")
        assert old.wait(timeout=10) is not None  # terminated
        assert len(rec.detached) == 1
    finally:
        if old.poll() is None:
            old.kill()
            old.wait()


def test_a_stale_waiter_record_is_ignored(tmp_path):
    from maestro_cs import procs

    conn, rec = make_connector(tmp_path, Recorder(running=True))
    write_config(conn, {"mcpServers": {}})
    old = _sleeper()
    try:
        procs.write_json(conn.waiter_record, {"pid": old.pid, "create_time": 1.0})  # wrong start time
        conn.connect("claude-desktop")
        assert old.poll() is None  # a recycled pid is not ours to kill
    finally:
        old.kill()
        old.wait()


def test_a_waiter_that_lost_its_record_stops_without_writing(tmp_path):
    from maestro_cs import procs

    rec = Recorder(running=True)
    conn, _ = make_connector(tmp_path, rec)
    path = write_config(conn, {"mcpServers": {}})
    before = path.read_bytes()
    calls = {"n": 0}

    def sleeper(seconds):
        calls["n"] += 1
        if calls["n"] == 1:
            procs.write_json(conn.waiter_record, {"pid": 999_999, "create_time": 1.0})
        if calls["n"] == 2:
            rec.running = False

    conn.sleep = sleeper
    ticks = iter(range(10_000))
    conn.clock = lambda: float(next(ticks))
    assert conn.wait_and_write("full", timeout=600.0, poll=1.0) == 0
    assert path.read_bytes() == before
    assert "took over" in rec.text
    assert json.loads(conn.waiter_record.read_text())["pid"] == 999_999  # not ours to remove


def test_the_waiter_removes_its_record_when_it_finishes(tmp_path):
    conn, _ = make_connector(tmp_path, Recorder(running=False))
    write_config(conn, {"mcpServers": {}})
    assert conn.wait_and_write("full", timeout=10.0, poll=1.0) == 0
    assert not conn.waiter_record.exists()


@pytest.mark.parametrize("scenario", ["now", "already_configured"])
def test_any_call_stops_a_pending_waiter_not_only_a_deferral(tmp_path, scenario):
    from maestro_cs import procs

    conn, rec = make_connector(tmp_path, Recorder(running=(scenario == "now")))
    write_config(conn, {"mcpServers": {"maestro-career-studio": ENTRY} if scenario != "now" else {}})
    old = _sleeper()
    try:
        procs.write_record(conn.waiter_record, old.pid)
        assert conn.connect("claude-desktop", now=(scenario == "now")) == 0
        assert old.wait(timeout=10) is not None  # terminated
        assert rec.detached == []
    finally:
        if old.poll() is None:
            old.kill()
            old.wait()
