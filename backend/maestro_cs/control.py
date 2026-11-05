"""The everyday verbs: run, start, stop, restart, status, logs, open.

`Controller` takes its collaborators (spawn, HTTP, port probe, browser, clock) as arguments so
tests drive it with fakes and a `tmp_path` home. Output goes through `say`, which is `print`:
when autostart runs `start` under pythonw, `sys.stdout` is None and `print` is then a no-op, so
nothing here writes to `sys.stdout` directly.
"""
from __future__ import annotations

import contextlib
import http.client
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psutil

from maestro_cs import detach, package_version, procs, runtime
from maestro_cs.home import (
    Ports,
    backend_env,
    child_env,
    prepare_home,
    ports_from,
    read_env_file,
    resolve_home,
    web_env,
)
from maestro_cs.supervisor import ChildSpec, Supervisor

POSIX = os.name == "posix"
WINDOWS = sys.platform == "win32"
BACKEND_TIMEOUT = 120.0
WEB_TIMEOUT = 60.0
READY_TIMEOUT = 180.0
STOP_WAIT = 30.0  # two children that ignore SIGTERM cost the supervisor 2 x (grace 10 s + 2 s)
DB_FILENAME = "maestro_cs.sqlite3"  # app.config.DB_FILENAME; `app` may not be imported here (R8)
LOG_NAMES = ("backend", "web", "supervisor", "update")
STALE = ("supervisor.json", "ready.json", "stop.request", "backend.json", "web.json")


class ControlError(Exception):
    """Something the person at the terminal can act on, phrased as one sentence."""


@dataclass(frozen=True)
class Context:
    home: Path
    settings: dict[str, str]
    ports: Ports
    environ: Mapping[str, str]
    version: str

    @property
    def run_dir(self) -> Path:
        return self.home / "run"

    @property
    def logs_dir(self) -> Path:
        return self.home / "logs"

    @property
    def web_url(self) -> str:
        return f"http://localhost:{self.ports.web}"

    @property
    def backend_url(self) -> str:
        return f"http://localhost:{self.ports.backend}"

    @property
    def mcp_url(self) -> str:
        return f"{self.backend_url}/mcp"


def load_context(environ: Mapping[str, str] | None = None) -> Context:
    environ = dict(os.environ if environ is None else environ)
    home = resolve_home(environ)
    prepare_home(home)
    settings = read_env_file(home / "maestro.env")
    return Context(home, settings, ports_from(settings, environ), environ, package_version())


# --- small system probes (swapped for fakes in tests) ---------------------------------------

def _listening(host: str, port: int, family: int) -> bool:
    try:
        with socket.socket(family, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.5)
            probe.connect((host, port))
        return True
    except OSError:
        return False


def port_free(port: int, host: str = "127.0.0.1") -> bool:
    """True when nothing listens on the port.

    POSIX binds with SO_REUSEADDR so a port in TIME_WAIT passes (the native lesson); Windows
    uses SO_EXCLUSIVEADDRUSE. Connect probes catch a listener the bind alone would allow: BSD
    lets a specific address bind next to a wildcard listener, and Node on `localhost` can hold
    only ::1, which `http://localhost:<port>` in a browser may reach.
    """
    if _listening(host, port, socket.AF_INET):
        return False
    if socket.has_ipv6 and _listening("::1", port, socket.AF_INET6):
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if POSIX:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        elif hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def http_get_json(url: str, timeout: float = 2.0) -> dict[str, Any] | None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # loopback, no proxy
    try:
        with opener.open(url, timeout=timeout) as response:
            data = json.loads(response.read(1_000_000))
    except (OSError, ValueError, http.client.HTTPException):  # e.g. an SSH banner (BadStatusLine)
        return None
    return data if isinstance(data, dict) else None


def autostart_enabled() -> bool | None:
    """Whether Maestro starts at login (None when the system can't be asked)."""
    from maestro_cs import autostart  # lazy: autostart imports ControlError from here

    return autostart.is_enabled()


def latest_version(timeout: float = 3.0) -> str | None:
    """The newest release on PyPI (None when it couldn't be read)."""
    from maestro_cs import update  # lazy: update imports this module

    return update.latest_version(timeout)


def web_cmd_override(environ: Mapping[str, str]) -> list[str] | None:
    # MAESTRO_WEB_CMD is for tests only: a JSON argv that replaces `node server.js`, so the
    # integration test can run the real backend next to a tiny fake web server.
    raw = (environ.get("MAESTRO_WEB_CMD") or "").strip()
    if not raw:
        return None
    try:
        argv = json.loads(raw)
    except ValueError:
        argv = None
    if not (isinstance(argv, list) and argv and all(isinstance(a, str) for a in argv)):
        raise ControlError("MAESTRO_WEB_CMD must be a JSON list of strings.")
    return argv


def web_bundle_missing(environ: Mapping[str, str]) -> bool:
    return web_cmd_override(environ) is None and not runtime.web_dir_ok(environ)


NO_WEB = "This copy has no web app; reinstall with `uv tool install --force maestro-career-studio`."


def build_specs(ctx: Context) -> list[ChildSpec]:
    env_web = web_env(ctx.settings, ctx.environ, ctx.ports)
    web_argv = web_cmd_override(ctx.environ)
    if web_argv is None:
        web_argv = [str(runtime.node_path(environ=ctx.environ)), "server.js"]
        web_cwd = runtime.web_dir(ctx.environ)
    else:
        web_cwd = ctx.home
    backend = ChildSpec(
        "backend",
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
         "--port", str(ctx.ports.backend), "--workers", "1", "--no-server-header", "--ws", "none"],
        backend_env(ctx.home, ctx.settings, ctx.environ, ctx.ports, ctx.version),
        ctx.home, ctx.logs_dir / "backend.log",
        f"http://127.0.0.1:{ctx.ports.backend}/health", BACKEND_TIMEOUT,
    )
    web = ChildSpec(
        "web", web_argv, env_web, web_cwd, ctx.logs_dir / "web.log",
        f"http://127.0.0.1:{ctx.ports.web}/api/version", WEB_TIMEOUT,
    )
    return [backend, web]


def running_supervisor(ctx: Context) -> psutil.Process | None:
    return procs.live_process(procs.read_json(ctx.run_dir / "supervisor.json"))


def preflight(
    ctx: Context, is_port_free: Callable[[int], bool], http_get: Callable[..., dict[str, Any] | None],
) -> None:
    """Raise a ControlError sentence when either port is held (`start` and `run` share this)."""
    ports = ctx.ports
    for port in (ports.backend, ports.web):
        if is_port_free(port):
            continue
        info = http_get(f"http://127.0.0.1:{port}/api/version")
        if info and isinstance(info.get("version"), str):
            raise ControlError(
                f"Another Maestro (version {info['version']}) is already running on port "
                f"{port}, probably the Docker install. Stop it first (`docker compose down` "
                "in its folder), then run `maestro start`."
            )
        raise ControlError(
            f"Port {port} is in use by another program. "
            f"Maestro needs ports {ports.backend} and {ports.web}."
        )


def stale_database_problem(home: Path) -> str | None:
    """A sentence when `data/` lacks the database but holds a leftover that a new one would pick up.

    A fresh database next to a stale `-wal` would replay the old database's rows into it, and a
    `.before-import` file is the database an interrupted `maestro import-docker` moved aside.
    """
    data = home / "data"
    if (data / DB_FILENAME).exists():
        return None
    for suffix in (".before-import", "-wal"):
        if (data / f"{DB_FILENAME}{suffix}").exists():
            return (f"{DB_FILENAME}{suffix} is in {data} but {DB_FILENAME} is not, so Maestro won't start: a new "
                    "database beside it could pick up old rows. If an import was interrupted, put the "
                    f".before-import files back under their names; otherwise delete {DB_FILENAME}{suffix}, or "
                    "restore a snapshot from backups/. Then run `maestro start` again.")
    return None


def run(ctx: Context) -> int:
    """`maestro run`: the foreground supervisor (autostart units run this)."""
    if running_supervisor(ctx):
        print("Maestro is already running.")
        return 0
    if web_bundle_missing(ctx.environ):
        raise ControlError(NO_WEB)
    try:
        out = open(ctx.logs_dir / "supervisor.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
    except OSError:
        out = sys.stdout
    try:
        try:
            if problem := stale_database_problem(ctx.home):
                raise ControlError(problem)
            preflight(ctx, port_free, http_get_json)
        except ControlError as exc:
            # Exit 0 on purpose: launchd (KeepAlive SuccessfulExit=false) and systemd
            # (Restart=on-failure) restart a failing `run` forever, and with another Maestro or
            # program on the port there is nothing to retry until the user acts.
            print(exc)
            if out is not sys.stdout:
                print(exc, file=out)
            return 0
        specs = build_specs(ctx)
        if web_cmd_override(ctx.environ) is None:
            runtime.clear_web_cache(ctx.environ)  # a cache from the previous version must not be served
        ready = {"backend_url": ctx.backend_url, "web_url": ctx.web_url}
        return Supervisor(ctx.run_dir, specs, ready=ready, out=out).run()
    finally:
        if out is not sys.stdout:
            out.close()


def _tail(path: Path, lines: int) -> list[str]:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return [line.rstrip("\n") for line in deque(handle, maxlen=lines)]
    except OSError:
        return []


def _replaced(path: Path, handle: Any) -> bool:
    """True when `path` is no longer the file `handle` reads, or has been cut shorter."""
    try:
        now, mine = os.stat(path), os.fstat(handle.fileno())
    except OSError:  # the supervisor is between moving the old log and creating the new one
        return False
    if now.st_ino and mine.st_ino and (now.st_dev, now.st_ino) != (mine.st_dev, mine.st_ino):
        return True  # st_ino is 0 on some Windows file systems; then only the size can tell
    return now.st_size < handle.tell()


def _rss_mb(proc: psutil.Process | None) -> float | None:
    try:
        return round(proc.memory_info().rss / (1024 * 1024), 1) if proc else None
    except psutil.Error:
        return None


class Controller:
    def __init__(
        self,
        ctx: Context,
        *,
        spawn: Callable[..., Any] = subprocess.Popen,
        http_get: Callable[..., dict[str, Any] | None] | None = None,
        is_port_free: Callable[[int], bool] | None = None,
        run_prefetch: Callable[[Context], bool] | None = None,
        open_url: Callable[[str], Any] = webbrowser.open,
        send_term: Callable[[psutil.Process], None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        say: Callable[..., None] = print,
        ready_timeout: float = READY_TIMEOUT,
        stop_wait: float = STOP_WAIT,
    ) -> None:
        # looked up here, not bound at definition, so tests can swap the module-level probes
        self.ctx, self.spawn = ctx, spawn
        self.http_get, self.is_port_free = http_get or http_get_json, is_port_free or port_free
        self.run_prefetch = run_prefetch or self._prefetch
        self.open_url, self.sleep, self.clock, self.say = open_url, sleep, clock, say
        self.send_term = send_term or self._send_term
        self.ready_timeout, self.stop_wait = ready_timeout, stop_wait

    # --- start --------------------------------------------------------------------------

    def start(self, *, no_browser: bool = False, skip_model: bool = False) -> int:
        ctx = self.ctx
        if running_supervisor(ctx):
            self.say(f"Maestro is already running at {ctx.web_url}.")
            return 0
        if problem := stale_database_problem(ctx.home):
            raise ControlError(problem)
        self._reap_recorded()  # a hard-killed supervisor can leave its servers behind
        self._clear_records()
        if web_bundle_missing(ctx.environ):
            raise ControlError(NO_WEB)
        self._preflight()
        self._seed_demo()
        cache = ctx.home / "fastembed_cache"
        if not skip_model and not any(cache.iterdir()):
            self.say("Downloading the scoring model from Hugging Face (about 100 MB, once)…")
            if not self.run_prefetch(ctx):
                self.say("The scoring model didn't download; the first score will try again.")
        proc = self._detach()
        outcome = self._wait_ready(proc)
        if outcome == "exited":
            self.say("Maestro didn't start. The end of logs/supervisor.log:")
            for line in _tail(ctx.logs_dir / "supervisor.log", 20):
                self.say(f"  {line}")
            return 1
        if outcome == "timeout":
            self.say(f"Maestro is still starting after {self.ready_timeout:g} seconds. "
                     "See `maestro logs supervisor`; `maestro stop` ends it.")
            return 1
        self.say(f"Maestro is running: {ctx.web_url}")
        self.say(f"MCP: {ctx.mcp_url}")
        if autostart_enabled() is False:  # None: the system couldn't say, so no advice
            self.say("It stops when the computer restarts. "
                     "`maestro autostart on` starts it each time you log in.")
        if not no_browser:
            try:
                opened = self.open_url(ctx.web_url)
            except Exception:  # noqa: BLE001  (a missing browser must not fail a start)
                opened = False
            if opened is False:  # webbrowser.open reports "no browser" by returning False
                self.say(f"Couldn't open a browser. Open {ctx.web_url} yourself.")
        return 0

    def _preflight(self) -> None:
        preflight(self.ctx, self.is_port_free, self.http_get)

    def _seed_demo(self) -> None:
        home = self.ctx.home
        resumes = home / "base_resumes"
        if (home / "data" / DB_FILENAME).exists() or any(resumes.glob("*.json")):
            return
        demo = runtime.demo_resume()
        if demo:
            shutil.copyfile(demo, resumes / demo.name)

    def _prefetch(self, ctx: Context) -> bool:
        env = backend_env(ctx.home, ctx.settings, ctx.environ, ctx.ports, ctx.version)
        kwargs: dict[str, Any] = {"creationflags": subprocess.CREATE_NO_WINDOW} if WINDOWS else {}
        try:
            with open(ctx.logs_dir / "prefetch.log", "wb") as log:
                done = subprocess.run(
                    [str(runtime.venv_python(windowless=False)), "-m", "maestro_cs.prefetch"],
                    cwd=ctx.home, env=env, stdin=subprocess.DEVNULL, stdout=log,
                    stderr=subprocess.STDOUT, check=False, **kwargs,
                )
        except OSError:
            return False
        return done.returncode == 0

    def _detach(self) -> Any:
        ctx = self.ctx
        # Always the console python: a GUI-subsystem (pythonw) supervisor would give each child
        # its own visible console and turn every stop into a hard kill (review of de8d215b).
        argv = [str(runtime.venv_python(windowless=False)), "-m", "maestro_cs", "run"]
        env = {**child_env(ctx.environ), "MAESTRO_HOME": str(ctx.home)}
        try:
            with open(ctx.logs_dir / "supervisor.log", "ab") as log:
                common: dict[str, Any] = {"cwd": ctx.home, "env": env, "stdin": subprocess.DEVNULL,
                                          "stdout": log, "stderr": subprocess.STDOUT}
                if WINDOWS:
                    return detach.popen_windows(
                        self.spawn, argv,
                        subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW, **common)
                return self.spawn(argv, start_new_session=True, **common)
        except OSError as exc:
            raise ControlError(f"Couldn't start Maestro: {argv[0]} could not be run "
                               f"({exc.strerror or exc}).") from None

    def _wait_ready(self, proc: Any) -> str:
        """"ready", "exited" (the supervisor died first) or "timeout"."""
        ready = self.ctx.run_dir / "ready.json"
        started = last_dot = self.clock()
        while self.clock() - started < self.ready_timeout:
            if procs.read_json(ready) is not None:
                return "ready"
            if proc.poll() is not None:
                return "exited"
            self.sleep(0.5)
            if self.clock() - last_dot >= 5:
                last_dot = self.clock()
                self.say(".")
        return "ready" if procs.read_json(ready) is not None else "timeout"

    # --- stop ---------------------------------------------------------------------------

    @staticmethod
    def _send_term(proc: psutil.Process) -> None:
        if POSIX:  # Windows has no graceful signal for a detached process; the file does it
            with contextlib.suppress(psutil.Error):  # it already exited
                proc.send_signal(signal.SIGTERM)

    def _reap_recorded(self) -> list[str]:
        """Stop servers a dead supervisor left behind. Only processes the records still match."""
        stopped = []
        for name in ("web", "backend"):
            proc = procs.live_process(procs.read_json(self.ctx.run_dir / f"{name}.json"))
            if proc:
                procs.kill_tree(proc)
                stopped.append(name)
        return stopped

    def _clear_records(self) -> None:
        for name in STALE:
            (self.ctx.run_dir / name).unlink(missing_ok=True)

    def stop(self) -> int:
        record = procs.read_json(self.ctx.run_dir / "supervisor.json")
        sup = procs.live_process(record)
        if sup is None:
            leftovers = self._reap_recorded()
            self._clear_records()
            self.say("Maestro stopped its leftover servers." if leftovers
                     else "Maestro is not running.")
            return 0
        (self.ctx.run_dir / "stop.request").write_text("stop\n", encoding="utf-8")
        self.send_term(sup)
        deadline = self.clock() + self.stop_wait
        while procs.live_process(record) and self.clock() < deadline:
            self.sleep(0.25)
        still = procs.live_process(record)
        if still:
            procs.kill_tree(still)
        self._reap_recorded()
        self._clear_records()
        self.say("Maestro stopped.")
        return 0

    def restart(self) -> int:
        self.stop()
        return self.start(no_browser=True)

    # --- status -------------------------------------------------------------------------

    def status(self, *, as_json: bool = False, offline: bool = False) -> int:
        from maestro_cs import update  # lazy: update imports this module

        ctx = self.ctx
        sup = running_supervisor(ctx)
        running = sup is not None
        backend_info = self.http_get(f"http://127.0.0.1:{ctx.ports.backend}/api/version") if running else None
        children = {
            name: procs.live_process(procs.read_json(ctx.run_dir / f"{name}.json"))
            for name in ("backend", "web")
        }
        latest = None if offline else latest_version()
        newer = update.is_newer(latest, ctx.version)  # a dev or newer local build isn't told to update
        autostart = autostart_enabled()
        report = {
            "running": running,
            "version": ctx.version,
            "urls": {"web": ctx.web_url, "backend": ctx.backend_url, "mcp": ctx.mcp_url},
            "data_dir": str(ctx.home),
            "autostart": autostart,
            "backend": {
                "version": (backend_info or {}).get("version"),
                "schema_revision": (backend_info or {}).get("schema_revision"),
                "pid": children["backend"].pid if children["backend"] else None,
                "rss_mb": _rss_mb(children["backend"]),
            },
            "web": {
                "pid": children["web"].pid if children["web"] else None,
                "rss_mb": _rss_mb(children["web"]),
            },
            "latest": latest,
            "update_available": None if latest is None else newer,
            "offline": offline,
            "checked": None if offline else "pypi.org",
        }
        if as_json:
            self.say(json.dumps(report, indent=2))
            return 0 if running else 3
        self.say("Maestro is running." if running else "Maestro is not running.")
        self.say(f"  Installed version: {ctx.version}")
        if running:
            if backend_info:
                self.say(f"  Backend: {ctx.backend_url} (version {backend_info.get('version')}, "
                         f"schema {backend_info.get('schema_revision')})")
            else:
                self.say(f"  Backend: {ctx.backend_url} (not answering yet)")
            self.say(f"  Web: {ctx.web_url}")
            self.say(f"  MCP: {ctx.mcp_url}")
        self.say(f"  Data folder: {ctx.home}")
        self.say("  Autostart: " + {True: "on", False: "off", None: "unknown"}[autostart])
        if offline:
            self.say("  Latest release: not checked (--offline)")
        elif latest is None:
            self.say("  Latest release: couldn't check pypi.org")
        elif newer:
            self.say(f"  Latest release: {latest} (checked pypi.org). Run `maestro update`.")
        else:
            self.say("  Latest release: you are up to date (checked pypi.org)")
        return 0 if running else 3

    # --- logs and open ------------------------------------------------------------------

    def logs(self, which: str = "backend", lines: int = 50, follow: bool = False) -> int:
        path = self.ctx.logs_dir / f"{which}.log"
        if not path.is_file():
            raise ControlError(f"There is no {which} log yet ({path}). Run `maestro start` first.")
        for line in _tail(path, lines):
            self.say(line)
        if not follow:
            return 0
        handle = open(path, encoding="utf-8", errors="replace")  # noqa: SIM115
        try:
            handle.seek(0, os.SEEK_END)
            while True:
                chunk = handle.readline()
                if chunk:
                    self.say(chunk.rstrip("\n"), flush=True)
                    continue
                if _replaced(path, handle):  # rotated or truncated: read the new file from the top
                    try:
                        fresh = open(path, encoding="utf-8", errors="replace")  # noqa: SIM115
                    except OSError:
                        fresh = None
                    if fresh is not None:
                        handle.close()
                        handle = fresh
                        continue
                self.sleep(0.5)
        except KeyboardInterrupt:
            return 0
        except OSError:
            return 0
        finally:
            handle.close()

    def open(self) -> int:
        if not running_supervisor(self.ctx):
            raise ControlError("Maestro isn't running. Start it with `maestro start`.")
        self.say(f"Opening {self.ctx.web_url}")
        self.open_url(self.ctx.web_url)
        return 0
