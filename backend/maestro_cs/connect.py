"""`maestro connect`: add Maestro to an agent app with one command.

The strings (Claude Code and Codex commands, the Cursor and VS Code links, the URL) come from
`app.services.connect.build`, the same function behind Settings › Connected agents, so there is
no second copy to drift. `app` is imported only after `apply_env` (R8), inside `_info`.

Claude Desktop is the odd one out: it has no command, so this module edits its config file. It
keeps its server list in memory and rewrites the file on routine events while it runs, which
silently erases an edit made from outside. So when Desktop is running the write is handed to a
detached waiter (`_connect-desktop-when-closed`) that waits for it to quit, then writes.

Process names recognised as Claude Desktop (an `exe` check, because Claude Code, the `claude`
CLI, also runs on every one of these systems and must never match):
  macOS    the process whose executable ends in `Claude.app/Contents/MacOS/Claude` (verified on
           this machine; Claude Code's copy inside Desktop's data folder is `claude.app/.../claude`).
  Windows  `claude.exe` run from an `AnthropicClaude` folder (Squirrel installer) or a
           `WindowsApps\\Claude_*` folder (MSIX), or a `claude.exe` whose path Windows will not
           show us. Claude Code's `claude.exe` lives elsewhere. UNVERIFIED: no Windows machine.
  Linux    there is no official app; unofficial builds run `claude-desktop`, an Electron binary
           inside a `claude-desktop` folder, or `Claude*.AppImage`. UNVERIFIED: matched
           conservatively, so an unknown build is simply not noticed and the write is immediate.
"""
from __future__ import annotations

import contextlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
import tomllib
import webbrowser
from collections.abc import Callable, Iterable, Iterator, Mapping
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import psutil

from maestro_cs import detach as detach_mod
from maestro_cs import home as home_mod
from maestro_cs import procs, runtime
from maestro_cs.control import Context, ControlError

SERVER_NAME = "maestro-career-studio"
CLIENT_IDS = ("claude-desktop", "claude-code", "codex", "cursor", "vscode", "other")
WAITER_VERB = "_connect-desktop-when-closed"
WAIT_SECONDS = 600.0
POLL_SECONDS = 2.0
SETTLE_SECONDS = 1.0  # Desktop writes its config as it quits; let it finish
COMMAND_TIMEOUT = 60.0
LABELS = {
    "claude-desktop": "Claude Desktop", "claude-code": "Claude Code", "codex": "Codex CLI",
    "cursor": "Cursor", "vscode": "VS Code", "other": "Any MCP agent",
}


def _say(*args: Any, **kwargs: Any) -> None:
    print(*args, flush=True, **kwargs)  # the waiter's stdout is a log file: no block buffering


# --- where each app keeps its config --------------------------------------------------------

def _msix_claude_dir(environ: Mapping[str, str], user_home: Path) -> Path | None:
    """The Microsoft Store build keeps Claude's files in its package folder (virtualised
    %APPDATA%). Used only when exactly one such folder exists. UNVERIFIED: no Windows machine."""
    local = Path(environ.get("LOCALAPPDATA") or user_home / "AppData" / "Local")
    try:
        found = [p for p in (local / "Packages").glob("Claude_*")
                 if (p / "LocalCache" / "Roaming" / "Claude").is_dir()]
    except OSError:
        return None
    return found[0] / "LocalCache" / "Roaming" / "Claude" if len(found) == 1 else None


def desktop_config_path(platform: str = sys.platform, environ: Mapping[str, str] = os.environ,
                        user_home: Path | None = None) -> Path:
    user_home = user_home or Path.home()
    if platform == "darwin":
        base = user_home / "Library" / "Application Support" / "Claude"
    elif platform == "win32":
        base = _msix_claude_dir(environ, user_home) or (
            Path(environ.get("APPDATA") or user_home / "AppData" / "Roaming") / "Claude")
    else:
        base = user_home / ".config" / "Claude"
    return base / "claude_desktop_config.json"


def claude_code_config_path(environ: Mapping[str, str], user_home: Path) -> Path:
    custom = (environ.get("CLAUDE_CONFIG_DIR") or "").strip()
    return Path(custom).expanduser() / ".claude.json" if custom else user_home / ".claude.json"


def codex_config_path(environ: Mapping[str, str], user_home: Path) -> Path:
    custom = (environ.get("CODEX_HOME") or "").strip()
    return (Path(custom).expanduser() if custom else user_home / ".codex") / "config.toml"


# --- is Claude Desktop running? -------------------------------------------------------------

def is_desktop_process(platform: str, name: str | None, exe: str | None,
                       cmdline: Iterable[str] | None) -> bool:
    args = list(cmdline or [])
    if platform == "darwin":
        for candidate in (exe, args[0] if args else None):
            if candidate and PurePosixPath(candidate).parts[-4:] == (
                    "Claude.app", "Contents", "MacOS", "Claude"):
                return True
        return False
    if platform == "win32":
        if (name or "").lower() != "claude.exe":
            return False
        if not exe:  # a protected app folder hides the path; Claude Code's own is readable
            return True
        path = exe.lower().replace("/", "\\")
        return "\\anthropicclaude\\" in path or "\\windowsapps\\claude_" in path
    for item in (name, exe, *args[:2]):
        if not item:
            continue
        path = PurePosixPath(item.replace("\\", "/"))
        base = path.name.lower()
        if (base.startswith("claude-desktop")
                or (base.startswith("claude") and base.endswith(".appimage"))
                or "claude-desktop" in {part.lower() for part in path.parts}):
            return True
    return False


def desktop_running(platform: str = sys.platform,
                    process_iter: Callable[..., Iterable[Any]] = psutil.process_iter) -> bool:
    with contextlib.suppress(psutil.Error, OSError):  # an unreadable process table means "not running"
        for proc in process_iter(["name", "exe", "cmdline"]):
            info = getattr(proc, "info", None) or {}
            if is_desktop_process(platform, info.get("name"), info.get("exe"), info.get("cmdline")):
                return True
    return False


# --- Claude Desktop's config file -----------------------------------------------------------

def read_desktop_config(path: Path) -> dict[str, Any]:
    """The parsed config; a missing or blank file is `{}`; anything unreadable is refused."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeDecodeError) as exc:
        reason = getattr(exc, "strerror", None) or "it is not UTF-8 text"
        raise ControlError(f"Couldn't read Claude Desktop's config ({path}): {reason}. "
                           "Maestro left it alone.") from None
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ControlError(
            f"Claude Desktop's config ({path}) isn't valid JSON ({exc}), so Maestro left it alone. "
            "Fix or remove that file, then run `maestro connect claude-desktop` again.") from None
    if not isinstance(data, dict):
        raise ControlError(f"Claude Desktop's config ({path}) isn't a JSON object, so Maestro "
                           "left it alone. Fix or remove that file, then run "
                           "`maestro connect claude-desktop` again.")
    return data


def _servers(config: dict[str, Any], path: Path) -> dict[str, Any]:
    servers = config.get("mcpServers", {})
    if not isinstance(servers, dict):
        raise ControlError(f"The mcpServers entry in {path} isn't a JSON object, so Maestro "
                           "left the file alone. Fix it, then run the command again.")
    return servers


def desktop_entry(profile: str, shim: Path, home: Path | None = None) -> dict[str, Any]:
    """The absolute launcher path: a GUI app does not have `~/.local/bin` on PATH (R10).

    `home` is given only for a custom `MAESTRO_HOME`: Desktop's environment lacks the shell's, so
    without it the bridge would read the default folder's `maestro.env` and ports.
    """
    args = ["mcp"] + ([] if profile == "full" else ["--profile", profile])
    entry: dict[str, Any] = {"command": str(shim), "args": args}
    if home is not None:
        entry["env"] = {"MAESTRO_HOME": str(home)}
    return entry


@contextlib.contextmanager
def parent_environ(original: Mapping[str, str]) -> Iterator[None]:
    """Run a child launcher (the browser opener) with the environment this command started with.

    `apply_env` put maestro.env's secrets into `os.environ` for the card's strings; an opener
    spawned meanwhile would inherit them. The applied environment comes back afterwards.
    """
    applied = dict(os.environ)
    child = home_mod.child_env(original)
    os.environ.clear()
    os.environ.update(child)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(applied)


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    """Replace `path` in one step, keeping its permissions; the old file survives any failure."""
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        with contextlib.suppress(OSError):  # a new file keeps the default mode
            shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def backup_file(path: Path, now: datetime) -> Path:
    stem = f"{path.name}.bak-{now.strftime('%Y%m%dT%H%M%SZ')}"
    target, n = path.with_name(stem), 0
    while target.exists():
        n += 1
        target = path.with_name(f"{stem}-{n}")
    shutil.copy2(path, target)
    return target


def _last_line(text: str) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    return lines[-1] if lines else ""


class Connector:
    def __init__(
        self,
        ctx: Context,
        *,
        platform: str = sys.platform,
        user_home: Path | None = None,
        which: Callable[[str], str | None] = shutil.which,
        run: Callable[..., Any] = subprocess.run,
        open_url: Callable[[str], Any] = webbrowser.open,
        running: Callable[[], bool] | None = None,
        detach: Callable[[list[str], Path], Any] | None = None,
        apply: Callable[..., None] | None = None,
        build: Callable[[str], Any] | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        say: Callable[..., None] = _say,
        shim: Callable[[], Path] = runtime.shim_path,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        settle: float = SETTLE_SECONDS,
        pid: Callable[[], int] = os.getpid,
    ) -> None:
        self.ctx, self.platform = ctx, platform
        self.user_home = user_home or Path.home()
        self.which, self.run, self.open_url = which, run, open_url
        self.running = running or (lambda: desktop_running(platform))
        self.detach = detach or self._detach
        self._apply, self._build = apply, build
        self.now, self.say, self.shim = now, say, shim
        self.sleep, self.clock, self.settle = sleep, clock, settle
        self.pid = pid

    @property
    def desktop_config(self) -> Path:
        return desktop_config_path(self.platform, self.ctx.environ, self.user_home)

    @property
    def log_file(self) -> Path:
        return self.ctx.logs_dir / "connect.log"

    @property
    def waiter_record(self) -> Path:
        return self.ctx.run_dir / "connect-waiter.json"

    def _detach(self, args: list[str], log: Path) -> Any:
        return detach_mod.spawn_detached(args, log=log, home=self.ctx.home, env=self.ctx.environ)

    def _info(self, profile: str) -> Any:
        """The card's strings for `profile`, after the install's environment is applied (R8)."""
        ctx = self.ctx
        (self._apply or home_mod.apply_env)(
            ctx.home, home_mod.backend_env(ctx.home, ctx.settings, ctx.environ, ctx.ports, ctx.version))
        if self._build is None:
            from app.services.connect import build  # noqa: PLC0415  (after apply_env, R8)
        else:
            build = self._build
        try:
            return build(profile)
        except ValueError:
            from mcp_server import profiles  # noqa: PLC0415

            raise ControlError(f"Unknown tool profile {profile!r}. Choose one of: "
                               f"{', '.join(profiles.PROFILE_ALLOWLISTS)}.") from None

    # --- entry point --------------------------------------------------------------------

    def connect(self, client: str | None, profile: str = "full", print_only: bool = False,
                now: bool = False) -> int:
        if client is None:
            return self.list_clients()
        info = self._info(profile)
        from mcp_server.profiles import PROFILE_ALIASES  # noqa: PLC0415

        profile = PROFILE_ALIASES.get(profile, profile)  # a saved config outlives the old name
        if client == "claude-desktop":
            return self._claude_desktop(profile, print_only, now)
        if client in ("claude-code", "codex"):
            return self._cli_client(client, info, print_only)
        if client in ("cursor", "vscode"):
            return self._deep_link(client, info, print_only)
        self.say(info.mcp_url)
        if not print_only:
            self.say("Paste that URL into any agent app that accepts an MCP server over HTTP. "
                     "It needs no sign-in and only works on this computer.")
        return 0

    # --- Claude Code and Codex ----------------------------------------------------------

    def _cli_client(self, client: str, info: Any, print_only: bool) -> int:
        label = LABELS[client]
        command = next(c.value for c in info.clients if c.id == client)
        binary = command.split()[0]
        exe = None if print_only else self.which(binary)
        if exe is None:
            if not print_only:
                self.say(f"`{binary}` isn't on your PATH, so run this yourself:")
            self.say(command)
            return 0
        argv = [exe, *shlex.split(command)[1:]]
        try:
            # The original environment: `apply_env` has put maestro.env's API keys in os.environ.
            done = self.run(argv, capture_output=True, text=True, timeout=COMMAND_TIMEOUT,
                            stdin=subprocess.DEVNULL, check=False, env=home_mod.child_env(self.ctx.environ))
        except subprocess.TimeoutExpired:
            raise ControlError(f"{label} didn't answer within {COMMAND_TIMEOUT:g} seconds. "
                               f"Run this yourself: {command}") from None
        except OSError as exc:
            raise ControlError(f"Couldn't run {binary}: {exc.strerror or exc}.") from None
        if done.returncode != 0:
            reason = _last_line(done.stderr) or _last_line(done.stdout) or f"exit code {done.returncode}"
            self.say(f"{label} didn't add Maestro: {reason.rstrip('.')}.")
            return 1
        where = " for every folder" if client == "claude-code" else ""
        self.say(f"Added Maestro to {label}{where}. Restart any open session to load it.")
        return 0

    # --- Cursor and VS Code -------------------------------------------------------------

    def _deep_link(self, client: str, info: Any, print_only: bool) -> int:
        link = next(c.value for c in info.clients if c.id == client)
        self.say(link)
        if print_only:
            return 0
        self.say(f"Opening {LABELS[client]}. Confirm the install there.")
        try:
            with parent_environ(self.ctx.environ):
                opened = self.open_url(link)
        except Exception:  # noqa: BLE001  (a missing handler must not fail the command)
            opened = False
        if opened is False:
            self.say("Couldn't open it. Open the link above in your browser to finish.")
        return 0

    # --- Claude Desktop -----------------------------------------------------------------

    def _claude_desktop(self, profile: str, print_only: bool, now: bool) -> int:
        path = self.desktop_config
        entry = self._entry(profile)
        if print_only:
            self.say(f"Add this under mcpServers in {path}:")
            self.say(json.dumps({"mcpServers": {SERVER_NAME: entry}}, indent=2))
            return 0
        self._stop_previous_waiter()  # any call supersedes a pending one, whatever it does next
        servers = _servers(read_desktop_config(path), path)  # a broken file is refused before any wait
        if servers.get(SERVER_NAME) == entry:
            self.say("Maestro is already in Claude Desktop's config. Open Claude Desktop to load it.")
            return 0
        if self.running() and not now:
            return self._defer(profile)
        if now and self.running():
            self.say("Claude Desktop is running and may overwrite this change. If Maestro is "
                     "missing after you restart it, quit Claude Desktop fully and run this again "
                     "without --now.")
        code = self._write_desktop(profile)
        if code == 0:
            self.say("Open Claude Desktop to load Maestro.")
            self._old_bundle_hint()
        return code

    def _entry(self, profile: str) -> dict[str, Any]:
        # The detached waiter always has MAESTRO_HOME pinned (spawn_detached), so "set" is not
        # enough: only a folder other than the default one needs to be named.
        pinned = bool((self.ctx.environ.get("MAESTRO_HOME") or "").strip())
        default = Path(os.path.abspath(
            home_mod.default_home(self.platform, self.ctx.environ, self.user_home)))
        return desktop_entry(profile, self.shim(),
                             self.ctx.home if pinned and self.ctx.home != default else None)

    def _stop_previous_waiter(self) -> None:
        """One waiter at a time: any new call replaces a live earlier one."""
        old = procs.live_process(procs.read_json(self.waiter_record))
        if old is not None and old.pid != self.pid():
            procs.kill_tree(old, grace=2.0)

    def _defer(self, profile: str) -> int:
        try:
            self.detach([WAITER_VERB, "--profile", profile], self.log_file)
        except detach_mod.DetachError as exc:
            raise ControlError(str(exc)) from None
        self.say("Claude Desktop is running, and it rewrites its config while it runs, which "
                 "would erase this change.")
        self.say("Quit Claude Desktop fully (not just close the window); Maestro will add itself "
                 "as soon as it has quit.")
        self.say(f"Progress: {self.log_file}. Then open Claude Desktop to load Maestro.")
        self._old_bundle_hint()
        return 0

    def _old_bundle_hint(self) -> None:
        extensions = self.desktop_config.parent / "Claude Extensions"
        try:
            found = any(SERVER_NAME in p.name for p in extensions.iterdir())
        except OSError:
            return
        if found:
            self.say("If Claude Desktop also lists the older Maestro extension, remove it in "
                     "Settings › Extensions.")

    def _write_desktop(self, profile: str) -> int:
        """Back up, merge, write, read back. 0 on success, 1 when the entry did not stick."""
        # A dotfiles user may symlink the config: act on the real file so the link survives.
        path = Path(os.path.realpath(self.desktop_config))
        config = read_desktop_config(path)
        servers = _servers(config, path)
        entry = self._entry(profile)
        if servers.get(SERVER_NAME) == entry:
            self.say("Maestro is already in Claude Desktop's config.")
            return 0
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.is_file():
                self.say(f"Backed up the old config to {backup_file(path, self.now()).name}.")
            write_json_atomic(path, {**config, "mcpServers": {**servers, SERVER_NAME: entry}})
        except OSError as exc:
            raise ControlError(f"Couldn't update {path}: {exc.strerror or exc}. "
                               "Claude Desktop's config is unchanged.") from None
        try:
            stored = _servers(read_desktop_config(path), path).get(SERVER_NAME)
        except ControlError:
            stored = None
        if stored != entry:
            self.say("Maestro is missing from Claude Desktop's config: it rewrote the file right "
                     "after. Next, quit Claude Desktop fully (not just close the window), then run "
                     "`maestro connect claude-desktop` again.")
            return 1
        self.say(f"Added Maestro to Claude Desktop ({path}).")
        return 0

    def wait_and_write(self, profile: str = "full", timeout: float = WAIT_SECONDS,
                       poll: float = POLL_SECONDS) -> int:
        """The detached waiter: wait for Desktop to quit, then write. Everything goes to the log."""
        def log(message: str) -> None:
            self.say(f"{self.now().strftime('%Y-%m-%d %H:%M:%SZ')} {message}")

        deadline = self.clock() + timeout
        self._claim_waiter_record()
        try:
            log(f"Waiting for Claude Desktop to quit (up to {timeout / 60:g} minutes).")
            while True:
                while self.running():
                    if self.clock() >= deadline:
                        log(f"Claude Desktop was still running after {timeout / 60:g} minutes, so "
                            "nothing was written. Quit it fully, then run "
                            "`maestro connect claude-desktop`.")
                        return 1
                    self.sleep(poll)
                if self.settle <= 0:
                    break
                self.sleep(self.settle)
                if not self.running():  # it can relaunch within the pause
                    break
                log("Claude Desktop came back; still waiting.")
            if not self._owns_waiter_record():
                log("A newer `maestro connect claude-desktop` took over; this waiter stops.")
                return 0
            log("Claude Desktop has quit.")
            try:
                return self._write_desktop(profile)
            except ControlError as exc:
                log(str(exc))
                return 1
        finally:
            if self._owns_waiter_record():
                self.waiter_record.unlink(missing_ok=True)

    def _claim_waiter_record(self) -> None:
        with contextlib.suppress(OSError, psutil.Error):  # without a record only the one-waiter guarantee is lost
            procs.write_record(self.waiter_record, self.pid())

    def _owns_waiter_record(self) -> bool:
        record = procs.read_json(self.waiter_record)
        return record is None or record.get("pid") == self.pid()  # no record: nobody replaced us

    # --- the listing --------------------------------------------------------------------

    def _desktop_status(self) -> str:
        path = self.desktop_config
        try:
            added = SERVER_NAME in _servers(read_desktop_config(path), path)
        except ControlError:
            return f"couldn't read {path.name}"
        return "added" if added else "not added yet"

    def _claude_code_status(self) -> str:
        path = claude_code_config_path(self.ctx.environ, self.user_home)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return "not added yet"
        except (OSError, ValueError):
            return f"couldn't read {path.name}"
        if not isinstance(data, dict):
            return f"couldn't read {path.name}"
        if SERVER_NAME in (data.get("mcpServers") or {}):
            return "added for every folder"
        projects = data.get("projects") or {}
        if any(isinstance(p, dict) and SERVER_NAME in (p.get("mcpServers") or {})
               for p in projects.values()):
            return "added for one project only; run `maestro connect claude-code` for every folder"
        return "not added yet"

    def _codex_status(self) -> str:
        path = codex_config_path(self.ctx.environ, self.user_home)
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return "not added yet"
        except (OSError, ValueError):
            return f"couldn't read {path.name}"
        return "added" if SERVER_NAME in (data.get("mcp_servers") or {}) else "not added yet"

    def list_clients(self) -> int:
        statuses = {
            "claude-desktop": self._desktop_status(),
            "claude-code": self._claude_code_status(),
            "codex": self._codex_status(),
            "cursor": "opens an install link",
            "vscode": "opens an install link",
            "other": "prints the URL",
        }
        self.say("Add Maestro to an agent app with `maestro connect <app>`:")
        for client in CLIENT_IDS:
            self.say(f"  {client:<15} {LABELS[client]:<15} {statuses[client]}")
        self.say("Add --profile profile (or hunt, tailor, apply, track, templates) for a smaller tool set, "
                 "and --print to see the command without running it.")
        return 0
