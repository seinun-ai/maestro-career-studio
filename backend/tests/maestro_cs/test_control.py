"""`Controller` with fake spawn, HTTP, port probe, clock and a `tmp_path` home."""
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import psutil
import pytest

from maestro_cs import control, detach, procs, runtime
from maestro_cs.control import Context, ControlError, Controller
from maestro_cs.home import Ports

POSIX = os.name == "posix"


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def make_ctx(tmp_path, environ=None, ports=Ports(18001, 13000)):
    home = tmp_path / "home"
    for name in ("data", "base_resumes", "logs", "fastembed_cache", "run"):
        (home / name).mkdir(parents=True, exist_ok=True)
    env = {"PATH": os.environ.get("PATH", ""), **(environ or {})}
    return Context(home, {}, ports, env, "9.9.9")


class FakeProc:
    def __init__(self, code=None, pid=4242):
        self.code, self.pid = code, pid

    def poll(self):
        return self.code


class Rig:
    """A Controller wired to fakes; `printed` collects everything said."""

    def __init__(self, tmp_path, *, busy=(), versions=None, environ=None, spawn_writes_ready=True,
                 spawn_code=None, prefetch_ok=True):
        self.ctx = make_ctx(tmp_path, environ)
        self.clock = Clock()
        self.printed, self.spawned, self.opened, self.prefetched = [], [], [], []
        self.busy, self.versions = set(busy), versions or {}
        self.writes_ready, self.spawn_code, self.prefetch_ok = spawn_writes_ready, spawn_code, prefetch_ok
        self.terms = []
        self.ctl = Controller(
            self.ctx, spawn=self.spawn, http_get=self.http_get, is_port_free=lambda p: p not in self.busy,
            run_prefetch=self.prefetch, open_url=self.opened.append, send_term=self.terms.append,
            sleep=self.clock.sleep, clock=self.clock,
            say=lambda *a, **k: self.printed.append(" ".join(str(x) for x in a)),
            ready_timeout=20, stop_wait=3,
        )

    def spawn(self, argv, **kwargs):
        self.spawned.append((argv, kwargs))
        if self.writes_ready and self.spawn_code is None:
            procs.write_json(self.ctx.run_dir / "ready.json", {"backend": 1, "web": 2})
        return FakeProc(self.spawn_code)

    def http_get(self, url, timeout=2.0):
        port = int(url.split(":")[2].split("/")[0])
        return self.versions.get(port)

    def prefetch(self, ctx):
        self.prefetched.append(ctx)
        return self.prefetch_ok

    @property
    def text(self):
        return "\n".join(self.printed)


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def sleeper():
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])


def record(ctx, name, popen):
    procs.write_record(ctx.run_dir / name, popen.pid)


# --- start ---------------------------------------------------------------------------------

def test_start_detaches_the_supervisor_and_reports_the_urls(rig, monkeypatch):
    monkeypatch.setattr(runtime, "web_dir_ok", lambda environ=None: True)
    assert rig.ctl.start(no_browser=True, skip_model=True) == 0
    argv, kwargs = rig.spawned[0]
    assert argv[1:] == ["-m", "maestro_cs", "run"]
    assert kwargs["env"]["MAESTRO_HOME"] == str(rig.ctx.home)
    assert kwargs["cwd"] == rig.ctx.home
    assert kwargs["stdin"] == subprocess.DEVNULL
    assert kwargs["stderr"] == subprocess.STDOUT
    if POSIX:
        assert kwargs["start_new_session"] is True
    assert "Maestro is running: http://localhost:13000" in rig.text
    assert "http://localhost:18001/mcp" in rig.text
    assert rig.opened == []


AUTOSTART_TIP = "It stops when the computer restarts. `maestro autostart on` starts it each time you log in."


@pytest.mark.parametrize(("enabled", "tipped"), [(False, True), (True, False), (None, False)])
def test_start_names_autostart_only_while_it_is_off(rig, monkeypatch, enabled, tipped):
    """A job seeker who comes back after a restart finds nothing running. While autostart
    is off, start says how to keep it; on, or unknown to the system, it says nothing."""
    monkeypatch.setattr(runtime, "web_dir_ok", lambda environ=None: True)
    monkeypatch.setattr(control, "autostart_enabled", lambda: enabled)
    assert rig.ctl.start(no_browser=True, skip_model=True) == 0
    assert (AUTOSTART_TIP in rig.printed) is tipped


def test_start_opens_the_browser_unless_told_not_to(rig, monkeypatch):
    monkeypatch.setattr(runtime, "web_dir_ok", lambda environ=None: True)
    rig.ctl.start(skip_model=True)
    assert rig.opened == ["http://localhost:13000"]


def test_start_survives_a_browser_that_cannot_open(rig, monkeypatch):
    monkeypatch.setattr(runtime, "web_dir_ok", lambda environ=None: True)

    def boom(url):
        raise RuntimeError("no browser")

    rig.ctl.open_url = boom
    assert rig.ctl.start(skip_model=True) == 0


@pytest.mark.parametrize("failure", ["returns False", "raises"])
def test_start_says_when_no_browser_could_be_opened(rig, monkeypatch, failure):
    monkeypatch.setattr(runtime, "web_dir_ok", lambda environ=None: True)

    def no_browser(url):
        if failure == "raises":
            raise OSError("no display")
        return False

    rig.ctl.open_url = no_browser
    assert rig.ctl.start(skip_model=True) == 0
    assert "Couldn't open a browser. Open http://localhost:13000 yourself." in rig.text


def test_start_detaches_through_the_console_python(rig, monkeypatch):
    # The pythonw/python.exe rule lives in runtime.venv_python; start must ask for the console one.
    seen = []
    monkeypatch.setattr(runtime, "web_dir_ok", lambda environ=None: True)
    monkeypatch.setattr(runtime, "venv_python",
                        lambda **kw: seen.append(kw) or Path("/v/python"))
    rig.ctl.start(no_browser=True, skip_model=True)
    assert seen == [{"windowless": False}]
    assert rig.spawned[0][0][0] == str(Path("/v/python"))


def test_start_on_windows_uses_a_hidden_new_process_group(rig, monkeypatch):
    monkeypatch.setattr(runtime, "web_dir_ok", lambda environ=None: True)
    monkeypatch.setattr(control, "WINDOWS", True)
    monkeypatch.setattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200, raising=False)
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    rig.ctl.start(no_browser=True, skip_model=True)
    kwargs = rig.spawned[0][1]
    # first try leaves the parent's job object (a logon task or a terminal may kill the job's members)
    assert kwargs["creationflags"] == 0x200 | 0x08000000 | detach.CREATE_BREAKAWAY_FROM_JOB
    assert "start_new_session" not in kwargs


def test_detached_supervisor_keeps_windows_loader_variables_with_a_minimal_parent(rig, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    system = {"SYSTEMROOT": "system-root", "WINDIR": "windows-dir",
              "COMSPEC": "shell", "PATHEXT": ".EXE;.CMD"}
    for name, value in system.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("OPENAI_API_KEY", "parent-secret")
    rig.ctl._detach()
    env = rig.spawned[0][1]["env"]
    assert all(env.get(name) == value for name, value in system.items())
    assert "OPENAI_API_KEY" not in env


def test_start_on_windows_retries_without_breakaway_when_the_job_forbids_it(rig, monkeypatch):
    monkeypatch.setattr(runtime, "web_dir_ok", lambda environ=None: True)
    monkeypatch.setattr(control, "WINDOWS", True)
    monkeypatch.setattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200, raising=False)
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    plain = rig.spawn

    def strict(argv, **kwargs):
        if kwargs["creationflags"] & detach.CREATE_BREAKAWAY_FROM_JOB:
            rig.spawned.append((argv, kwargs))
            raise PermissionError(5, "Access is denied")
        return plain(argv, **kwargs)

    rig.ctl.spawn = strict
    assert rig.ctl.start(no_browser=True, skip_model=True) == 0
    flags = [kwargs["creationflags"] for _, kwargs in rig.spawned]
    assert flags == [0x200 | 0x08000000 | detach.CREATE_BREAKAWAY_FROM_JOB, 0x200 | 0x08000000]


def test_start_when_running_says_so_and_spawns_nothing(rig):
    sleeper_proc = sleeper()
    try:
        record(rig.ctx, "supervisor.json", sleeper_proc)
        assert rig.ctl.start() == 0
        assert rig.text == "Maestro is already running at http://localhost:13000."
        assert rig.spawned == []
    finally:
        sleeper_proc.kill()
        sleeper_proc.wait()


def test_start_names_a_docker_maestro_on_the_port(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "web_dir_ok", lambda environ=None: True)
    rig = Rig(tmp_path, busy={18001}, versions={18001: {"version": "0.8.0"}})
    with pytest.raises(ControlError) as err:
        rig.ctl.start()
    msg = str(err.value)
    assert "Another Maestro (version 0.8.0) is already running on port 18001" in msg
    assert "docker compose down" in msg and "maestro start" in msg
    assert rig.spawned == []


def test_start_names_an_unknown_program_on_the_web_port(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "web_dir_ok", lambda environ=None: True)
    rig = Rig(tmp_path, busy={13000})
    with pytest.raises(ControlError) as err:
        rig.ctl.start()
    assert str(err.value) == ("Port 13000 is in use by another program. "
                              "Maestro needs ports 18001 and 13000.")


def test_start_without_a_web_bundle_refuses_before_anything_else(rig, monkeypatch):
    monkeypatch.setattr(runtime, "web_dir_ok", lambda environ=None: False)
    with pytest.raises(ControlError, match="no web app"):
        rig.ctl.start()
    assert rig.spawned == [] and rig.prefetched == []


def test_first_start_copies_the_demo_resume_once(rig, monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "web_dir_ok", lambda environ=None: True)
    demo = tmp_path / "example.json"
    demo.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(runtime, "demo_resume", lambda: demo)
    resumes = rig.ctx.home / "base_resumes"
    rig.ctl.start(no_browser=True, skip_model=True)
    assert (resumes / "example.json").is_file()
    (resumes / "example.json").unlink()
    (resumes / "mine.json").write_text("{}", encoding="utf-8")
    rig.ctl.start(no_browser=True, skip_model=True)
    assert not (resumes / "example.json").exists()  # the user already has resumes


def test_no_demo_resume_when_a_database_exists(rig, monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "web_dir_ok", lambda environ=None: True)
    demo = tmp_path / "example.json"
    demo.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(runtime, "demo_resume", lambda: demo)
    (rig.ctx.home / "data" / "maestro_cs.sqlite3").write_bytes(b"")
    rig.ctl.start(no_browser=True, skip_model=True)
    assert not (rig.ctx.home / "base_resumes" / "example.json").exists()


def test_model_downloads_when_the_cache_is_empty(rig, monkeypatch):
    monkeypatch.setattr(runtime, "web_dir_ok", lambda environ=None: True)
    rig.ctl.start(no_browser=True)
    assert len(rig.prefetched) == 1
    assert "Downloading the scoring model from Hugging Face (about 100 MB, once)…" in rig.text


def test_model_download_is_skipped_by_flag_and_by_a_filled_cache(rig, monkeypatch):
    monkeypatch.setattr(runtime, "web_dir_ok", lambda environ=None: True)
    rig.ctl.start(no_browser=True, skip_model=True)
    (rig.ctx.home / "fastembed_cache" / "models").mkdir()
    rig.ctl.start(no_browser=True)
    assert rig.prefetched == []


def test_a_failed_model_download_does_not_stop_the_start(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "web_dir_ok", lambda environ=None: True)
    rig = Rig(tmp_path, prefetch_ok=False)
    assert rig.ctl.start(no_browser=True) == 0
    assert "The scoring model didn't download; the first score will try again." in rig.text
    assert "Maestro is running" in rig.text


def test_a_supervisor_that_exits_first_prints_the_log_tail(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "web_dir_ok", lambda environ=None: True)
    rig = Rig(tmp_path, spawn_code=1)
    log = rig.ctx.logs_dir / "supervisor.log"
    log.write_text("\n".join(f"line {i}" for i in range(30)) + "\n", encoding="utf-8")
    assert rig.ctl.start(no_browser=True, skip_model=True) == 1
    assert "line 29" in rig.text and "line 10" in rig.text and "line 9\n" not in rig.text + "\n"
    assert "Maestro is running" not in rig.text


def test_waiting_prints_a_dot_every_five_seconds_and_gives_up(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "web_dir_ok", lambda environ=None: True)
    rig = Rig(tmp_path, spawn_writes_ready=False)
    assert rig.ctl.start(no_browser=True, skip_model=True) == 1
    assert rig.printed.count(".") == 4  # 20 s timeout: a dot at 5, 10, 15 and 20 s
    assert "still starting after 20 seconds" in rig.text and "logs/supervisor.log" not in rig.text


def test_stale_records_do_not_count_as_ready(rig, monkeypatch):
    monkeypatch.setattr(runtime, "web_dir_ok", lambda environ=None: True)
    procs.write_json(rig.ctx.run_dir / "ready.json", {"old": 1})
    rig.writes_ready = False
    assert rig.ctl.start(no_browser=True, skip_model=True) == 1


def test_the_web_override_replaces_node_and_skips_the_bundle_check(tmp_path):
    rig = Rig(tmp_path, environ={"MAESTRO_WEB_CMD": json.dumps(["python", "fake.py"])})
    specs = control.build_specs(rig.ctx)
    assert specs[1].argv == ["python", "fake.py"] and specs[1].cwd == rig.ctx.home
    assert not control.web_bundle_missing(rig.ctx.environ)


def test_a_malformed_web_override_is_a_sentence(tmp_path):
    rig = Rig(tmp_path, environ={"MAESTRO_WEB_CMD": "{nope"})
    with pytest.raises(ControlError, match="MAESTRO_WEB_CMD"):
        control.build_specs(rig.ctx)


def test_specs_follow_the_plan(tmp_path, monkeypatch):
    web = tmp_path / "web"
    web.mkdir()
    (web / "server.js").write_text("", encoding="utf-8")
    rig = Rig(tmp_path, environ={"MAESTRO_WEB_DIR": str(web), "MAESTRO_NODE": "/n/node",
                                 "OPENAI_API_KEY": "sk-secret"})
    backend, web_spec = control.build_specs(rig.ctx)
    assert backend.argv == [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                            "--port", "18001", "--workers", "1", "--no-server-header",
                            "--ws", "none"]
    assert backend.cwd == rig.ctx.home and backend.health_timeout == 120
    assert backend.health_url == "http://127.0.0.1:18001/health"
    assert backend.env["MAESTRO_HOME"] == str(rig.ctx.home)
    assert backend.env["OPENAI_API_KEY"] == "sk-secret"
    assert web_spec.argv == [str(Path("/n/node")), "server.js"] and web_spec.cwd == web
    assert web_spec.health_url == "http://127.0.0.1:13000/api/version"
    assert web_spec.health_timeout == 60
    assert "OPENAI_API_KEY" not in web_spec.env
    assert (backend.log.name, web_spec.log.name) == ("backend.log", "web.log")


# --- stop ----------------------------------------------------------------------------------

def test_stop_when_nothing_runs_cleans_stale_records(rig):
    for name in control.STALE:
        procs.write_json(rig.ctx.run_dir / name, {"pid": 99999999, "create_time": 1.0})
    assert rig.ctl.stop() == 0
    assert rig.text == "Maestro is not running."
    assert list(rig.ctx.run_dir.iterdir()) == []


def test_stop_never_signals_a_pid_whose_record_does_not_match(rig):
    bystander = sleeper()
    try:
        procs.write_json(rig.ctx.run_dir / "supervisor.json",
                         {"pid": bystander.pid, "create_time": 1.0})
        procs.write_json(rig.ctx.run_dir / "backend.json",
                         {"pid": bystander.pid, "create_time": 1.0})
        assert rig.ctl.stop() == 0
        assert bystander.poll() is None  # still alive
        assert rig.terms == []
    finally:
        bystander.kill()
        bystander.wait()


def test_stop_reaps_recorded_children_of_a_dead_supervisor(rig):
    orphan = sleeper()
    try:
        record(rig.ctx, "backend.json", orphan)
        assert rig.ctl.stop() == 0
        assert orphan.wait(timeout=10) is not None
        assert "leftover" in rig.text
        assert not (rig.ctx.run_dir / "backend.json").exists()
    finally:
        if orphan.poll() is None:
            orphan.kill()
            orphan.wait()


def test_stop_writes_the_request_signals_and_waits(rig):
    sup = sleeper()
    try:
        record(rig.ctx, "supervisor.json", sup)

        def term(proc):
            assert (rig.ctx.run_dir / "stop.request").exists()
            rig.terms.append(proc.pid)
            sup.terminate()  # the supervisor exits on the request
            # The fake clock advances on every sleep() without real time passing, so wait for the
            # exit here: otherwise the stop loop can burn its whole budget before the process dies.
            sup.wait(timeout=10)

        rig.ctl.send_term = term
        assert rig.ctl.stop() == 0
        sup.wait(timeout=10)
        assert rig.terms == [sup.pid]
        assert rig.text == "Maestro stopped."
        assert rig.clock.now < 3  # did not run out the wait
        assert not (rig.ctx.run_dir / "stop.request").exists()
    finally:
        if sup.poll() is None:
            sup.kill()
            sup.wait()


def test_stop_kills_a_supervisor_that_ignores_the_request(rig):
    sup = sleeper()
    child = sleeper()
    try:
        record(rig.ctx, "supervisor.json", sup)
        record(rig.ctx, "web.json", child)
        rig.ctl.send_term = lambda proc: None
        assert rig.ctl.stop() == 0
        assert rig.clock.now >= 3  # waited the whole allowance first
        sup.wait(timeout=10)
        child.wait(timeout=10)
        assert rig.text == "Maestro stopped."
        assert list(rig.ctx.run_dir.iterdir()) == []
    finally:
        for p in (sup, child):
            if p.poll() is None:
                p.kill()
                p.wait()


def test_default_stop_wait_covers_two_stubborn_children():
    assert control.STOP_WAIT >= 2 * (10 + 2)  # Supervisor.grace plus its tree-kill allowance


@pytest.mark.skipif(not POSIX, reason="posix only")
def test_default_send_term_sends_sigterm():
    proc = sleeper()
    try:
        Controller._send_term(psutil.Process(proc.pid))
        assert proc.wait(timeout=10) == -signal.SIGTERM
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def test_restart_stops_then_starts_without_the_browser(rig, monkeypatch):
    monkeypatch.setattr(runtime, "web_dir_ok", lambda environ=None: True)
    (rig.ctx.home / "fastembed_cache" / "m").mkdir()
    assert rig.ctl.restart() == 0
    assert rig.printed[0] == "Maestro is not running."
    assert "Maestro is running" in rig.text and rig.opened == []


# --- status --------------------------------------------------------------------------------

def test_status_stopped_exits_3(rig):
    assert rig.ctl.status(offline=True) == 3
    assert rig.printed[0] == "Maestro is not running."
    assert "Latest release: not checked (--offline)" in rig.text


def test_status_running_reports_everything_in_json(tmp_path, monkeypatch):
    rig = Rig(tmp_path, versions={18001: {"version": "0.8.0", "schema_revision": "abc"}})
    monkeypatch.setattr(control, "latest_version", lambda timeout=3.0: "10.0.0")
    monkeypatch.setattr(control, "autostart_enabled", lambda: True)
    sup, backend = sleeper(), sleeper()
    try:
        record(rig.ctx, "supervisor.json", sup)
        record(rig.ctx, "backend.json", backend)
        assert rig.ctl.status(as_json=True) == 0
        data = json.loads(rig.text)
        assert data["running"] is True and data["version"] == "9.9.9"
        assert data["backend"]["version"] == "0.8.0" and data["backend"]["schema_revision"] == "abc"
        assert data["backend"]["pid"] == backend.pid and data["backend"]["rss_mb"] > 0
        assert data["web"] == {"pid": None, "rss_mb": None}
        assert data["urls"]["web"] == "http://localhost:13000"
        assert data["autostart"] is True
        assert data["latest"] == "10.0.0" and data["update_available"] is True
        assert data["checked"] == "pypi.org"
        assert data["data_dir"] == str(rig.ctx.home)
    finally:
        for p in (sup, backend):
            p.kill()
            p.wait()


def test_status_text_says_when_a_newer_release_exists(tmp_path, monkeypatch):
    rig = Rig(tmp_path)
    monkeypatch.setattr(control, "latest_version", lambda timeout=3.0: "10.0.0")
    rig.ctl.status()
    assert "Latest release: 10.0.0 (checked pypi.org). Run `maestro update`." in rig.text


def test_status_says_when_it_could_not_check(rig, monkeypatch):
    monkeypatch.setattr(control, "latest_version", lambda timeout=3.0: None)
    rig.ctl.status()
    assert "Latest release: couldn't check pypi.org" in rig.text


def test_a_newer_local_build_is_not_told_to_update(tmp_path, monkeypatch):
    rig = Rig(tmp_path)  # installed 9.9.9
    monkeypatch.setattr(control, "latest_version", lambda timeout=3.0: "0.9.0")
    rig.ctl.status()
    assert "you are up to date (checked pypi.org)" in rig.text and "maestro update" not in rig.text
    rig.printed.clear()
    rig.ctl.status(as_json=True)
    data = json.loads(rig.text)
    assert data["latest"] == "0.9.0" and data["update_available"] is False


def test_offline_never_calls_the_release_check(tmp_path, monkeypatch):
    rig = Rig(tmp_path)

    def boom(timeout=3.0):
        raise AssertionError("network call with --offline")

    monkeypatch.setattr(control, "latest_version", boom)
    rig.ctl.status(offline=True)
    rig.printed.clear()
    rig.ctl.status(as_json=True, offline=True)
    assert json.loads(rig.text)["checked"] is None  # no request was made, so none is named


# --- logs, open, run -----------------------------------------------------------------------

def test_logs_prints_the_tail_of_the_chosen_log(rig):
    (rig.ctx.logs_dir / "web.log").write_text("a\nb\nc\nd\n", encoding="utf-8")
    assert rig.ctl.logs("web", 2) == 0
    assert rig.printed == ["c", "d"]


def test_logs_without_a_file_is_a_sentence(rig):
    with pytest.raises(ControlError, match="no backend log yet"):
        rig.ctl.logs()


def test_logs_follow_prints_new_lines_until_interrupted(rig):
    log = rig.ctx.logs_dir / "backend.log"
    log.write_text("old\n", encoding="utf-8")
    calls = []

    def sleep(seconds):
        calls.append(seconds)
        if len(calls) == 1:
            with open(log, "a", encoding="utf-8") as handle:
                handle.write("new\n")
        else:
            raise KeyboardInterrupt

    rig.ctl.sleep = sleep
    assert rig.ctl.logs("backend", 5, follow=True) == 0
    assert rig.printed == ["old", "new"]


def test_open_says_so_when_not_running(rig):
    with pytest.raises(ControlError, match="isn't running"):
        rig.ctl.open()
    assert rig.opened == []


def test_open_opens_the_web_url_when_running(rig):
    sup = sleeper()
    try:
        record(rig.ctx, "supervisor.json", sup)
        assert rig.ctl.open() == 0
        assert rig.opened == ["http://localhost:13000"]
    finally:
        sup.kill()
        sup.wait()


def test_run_exits_zero_beside_a_live_supervisor(rig, capsys):
    sup = sleeper()
    try:
        record(rig.ctx, "supervisor.json", sup)
        assert control.run(rig.ctx) == 0
        assert capsys.readouterr().out.strip() == "Maestro is already running."
    finally:
        sup.kill()
        sup.wait()


def test_run_refuses_without_a_web_bundle(rig, monkeypatch):
    monkeypatch.setattr(runtime, "web_dir_ok", lambda environ=None: False)
    with pytest.raises(ControlError, match="uv tool install --force"):
        control.run(rig.ctx)


class NoSupervisor:
    """A Supervisor stand-in that fails the test when `run` gets as far as building children."""

    def __init__(self, *args, **kwargs):
        raise AssertionError("run spawned children although a port was busy")


def free_ports(monkeypatch, busy=(), versions=None):
    """Swap the module-level probes `run` uses; returns the list of URLs it asked."""
    asked = []
    monkeypatch.setattr(control, "port_free", lambda port, host="127.0.0.1": port not in busy)

    def fake_get(url, timeout=2.0):
        asked.append(url)
        return (versions or {}).get(int(url.split(":")[2].split("/")[0]))

    monkeypatch.setattr(control, "http_get_json", fake_get)
    return asked


def test_run_clears_the_web_cache_before_it_starts_the_web_app(tmp_path, monkeypatch):
    web = tmp_path / "web"
    cache = web / ".next" / "server" / "route-cache"
    cache.mkdir(parents=True)
    (web / "server.js").write_text("//", encoding="utf-8")
    rig = Rig(tmp_path, environ={"MAESTRO_WEB_DIR": str(web), "MAESTRO_NODE": "/n/node"})
    free_ports(monkeypatch)
    seen = {}

    class Recording:
        def __init__(self, run_dir, specs, **kwargs):
            seen["cache_there"] = cache.exists()

        def run(self):
            return 0

    monkeypatch.setattr(control, "Supervisor", Recording)
    assert control.run(rig.ctx) == 0
    assert seen == {"cache_there": False}


def test_run_with_a_docker_maestro_on_the_port_explains_and_exits_zero(rig, monkeypatch, capsys):
    # Exit 0 on purpose: launchd (KeepAlive SuccessfulExit=false) and systemd (Restart=on-failure)
    # restart a non-zero `run` forever; there is nothing to retry until the user stops the other one.
    monkeypatch.setattr(runtime, "web_dir_ok", lambda environ=None: True)
    monkeypatch.setattr(control, "Supervisor", NoSupervisor)
    free_ports(monkeypatch, busy={18001}, versions={18001: {"version": "0.8.0"}})
    assert control.run(rig.ctx) == 0
    out = capsys.readouterr().out
    assert "Another Maestro (version 0.8.0) is already running on port 18001" in out
    assert "docker compose down" in out
    assert list(rig.ctx.run_dir.iterdir()) == []  # no records left behind


def test_run_with_another_program_on_the_web_port_exits_zero(rig, monkeypatch, capsys):
    monkeypatch.setattr(runtime, "web_dir_ok", lambda environ=None: True)
    monkeypatch.setattr(control, "Supervisor", NoSupervisor)
    free_ports(monkeypatch, busy={13000})
    assert control.run(rig.ctx) == 0
    assert capsys.readouterr().out.strip() == (
        "Port 13000 is in use by another program. Maestro needs ports 18001 and 13000."
    )
    assert list(rig.ctx.run_dir.iterdir()) == []


def test_run_writes_the_busy_port_sentence_to_the_supervisor_log(rig, monkeypatch):
    # Under autostart stdout goes to launchd.log / the journal; the same sentence is in
    # logs/supervisor.log so `maestro logs supervisor` explains why nothing is running.
    monkeypatch.setattr(runtime, "web_dir_ok", lambda environ=None: True)
    monkeypatch.setattr(control, "Supervisor", NoSupervisor)
    free_ports(monkeypatch, busy={13000})
    assert control.run(rig.ctx) == 0
    assert "Port 13000 is in use by another program" in (
        rig.ctx.logs_dir / "supervisor.log").read_text(encoding="utf-8")


def test_run_with_free_ports_goes_on_to_the_supervisor(tmp_path, monkeypatch):
    rig = Rig(tmp_path, environ={"MAESTRO_WEB_CMD": '["x"]'})
    asked = free_ports(monkeypatch)
    built = []

    class FakeSupervisor:
        def __init__(self, run_dir, specs, ready, out):
            built.append(specs)

        def run(self):
            return 0

    monkeypatch.setattr(control, "Supervisor", FakeSupervisor)
    assert control.run(rig.ctx) == 0
    assert len(built) == 1 and asked == []


def test_run_logs_to_the_supervisor_log(tmp_path, monkeypatch):
    rig = Rig(tmp_path, environ={"MAESTRO_WEB_CMD": '["x"]'})
    free_ports(monkeypatch)
    seen = {}

    class FakeSupervisor:
        def __init__(self, run_dir, specs, ready, out):
            seen.update(run_dir=run_dir, specs=specs, ready=ready, out=out)

        def run(self):
            print("hello", file=seen["out"])
            return 0

    monkeypatch.setattr(control, "Supervisor", FakeSupervisor)
    assert control.run(rig.ctx) == 0
    assert "hello" in (rig.ctx.logs_dir / "supervisor.log").read_text(encoding="utf-8")
    assert seen["run_dir"] == rig.ctx.run_dir and len(seen["specs"]) == 2
    assert seen["ready"]["web_url"] == "http://localhost:13000"


# --- probes --------------------------------------------------------------------------------

def test_port_free_sees_a_listener_and_a_free_port():
    import socket

    with socket.socket() as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen()
        port = holder.getsockname()[1]
        assert control.port_free(port) is False
    assert control.port_free(port) is True  # closed again (TIME_WAIT must not count as busy)


def test_load_context_builds_the_home_and_reads_ports(tmp_path):
    home = tmp_path / "h"
    ctx = control.load_context({"MAESTRO_HOME": str(home), "MAESTRO_PORT": "18999"})
    assert ctx.home == home and (home / "run").is_dir()
    assert ctx.ports == Ports(18999, 3000)
    assert ctx.mcp_url == "http://localhost:18999/mcp"


# --- the real thing --------------------------------------------------------------------------

FAKE_WEB = """
import os, json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"version": "fake-web"}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a):
        pass

ThreadingHTTPServer(("127.0.0.1", int(os.environ["PORT"])), H).serve_forever()
"""


def _spare_port():
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.mark.integration
def test_start_status_stop_with_the_real_backend(tmp_path):
    """Real uvicorn through the real `maestro start`; only the web server is a stand-in."""
    home = tmp_path / "home"
    fake_web = tmp_path / "fake_web.py"
    fake_web.write_text(FAKE_WEB, encoding="utf-8")
    ports = (_spare_port(), _spare_port())
    # An explicit environment: never the developer's shell, keys or .env.
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(tmp_path),
        "USERPROFILE": str(tmp_path),
        "MAESTRO_HOME": str(home),
        "MAESTRO_PORT": str(ports[0]),
        "MAESTRO_WEB_PORT": str(ports[1]),
        "MAESTRO_WEB_CMD": json.dumps([sys.executable, str(fake_web)]),
    }
    if os.name == "nt":
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")

    def maestro(*args, timeout=240):
        return subprocess.run([sys.executable, "-m", "maestro_cs", *args], env=env, cwd=tmp_path,
                              capture_output=True, text=True, timeout=timeout, check=False)

    try:
        started = maestro("start", "--no-browser", "--skip-model")
        assert started.returncode == 0, started.stdout + started.stderr + _logs(home)
        assert f"Maestro is running: http://localhost:{ports[1]}" in started.stdout

        status = maestro("status", "--json", "--offline")
        assert status.returncode == 0, status.stdout + status.stderr
        data = json.loads(status.stdout)
        assert data["running"] is True
        assert data["backend"]["schema_revision"] not in (None, "unknown")
        assert data["backend"]["rss_mb"] > 0 and data["web"]["rss_mb"] > 0
        assert (home / "base_resumes").is_dir()

        pids = [data["backend"]["pid"], data["web"]["pid"]]
        stopped = maestro("stop")
        assert stopped.returncode == 0, stopped.stdout + stopped.stderr
        assert "Maestro stopped." in stopped.stdout
        assert maestro("status", "--offline").returncode == 3
        assert not any(psutil.pid_exists(pid) and psutil.Process(pid).status() != "zombie"
                       for pid in pids)
        assert all(control.port_free(port) for port in ports)
        assert list((home / "run").iterdir()) == []
    finally:
        maestro("stop")


def _logs(home):
    parts = []
    for name in ("supervisor", "backend", "web"):
        path = home / "logs" / f"{name}.log"
        if path.is_file():
            parts.append(f"--- {name}.log\n" + path.read_text(encoding="utf-8", errors="replace")[-2000:])
    return "\n".join(parts)


# --- review follow-ups -----------------------------------------------------------------------

def _banner_server():
    """A listener that is not HTTP: writes an SSH banner and hangs up."""
    import socket
    import threading

    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()

    def serve():
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                return
            conn.sendall(b"SSH-2.0-test\r\n")
            conn.close()

    threading.Thread(target=serve, daemon=True).start()
    return server, server.getsockname()[1]


def test_a_non_http_listener_is_not_a_traceback_in_start(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "web_dir_ok", lambda environ=None: True)
    server, port = _banner_server()
    try:
        assert control.http_get_json(f"http://127.0.0.1:{port}/api/version") is None
        ctx = make_ctx(tmp_path, ports=Ports(port, _spare_port()))
        ctl = Controller(ctx, say=lambda *a, **k: None)
        with pytest.raises(ControlError) as err:
            ctl.start()
        assert str(err.value).startswith(f"Port {port} is in use by another program.")
    finally:
        server.close()


def test_a_non_http_listener_is_not_healthy(tmp_path):
    from maestro_cs import supervisor

    server, port = _banner_server()
    try:
        assert supervisor.http_ok(f"http://127.0.0.1:{port}/health") is False
    finally:
        server.close()


def test_the_cli_prints_a_sentence_for_a_non_http_listener(tmp_path, monkeypatch, capsys):
    from maestro_cs import cli

    monkeypatch.setattr(runtime, "web_dir_ok", lambda environ=None: True)
    server, port = _banner_server()
    try:
        monkeypatch.setenv("MAESTRO_HOME", str(tmp_path / "h"))
        monkeypatch.setenv("MAESTRO_PORT", str(port))
        monkeypatch.setenv("MAESTRO_WEB_PORT", str(_spare_port()))
        assert cli.main(["start", "--no-browser", "--skip-model"]) == 1
        err = capsys.readouterr().err
        assert f"Port {port} is in use by another program." in err and "Traceback" not in err
    finally:
        server.close()


@pytest.mark.skipif(sys.platform == "win32", reason="Windows locks an open log against rename; rotation appends instead")
def test_logs_follow_survives_rotation_without_replaying_the_old_log(rig):
    log = rig.ctx.logs_dir / "backend.log"
    log.write_text("old1\nold2\n", encoding="utf-8")
    step = []

    def sleep(seconds):
        step.append(1)
        if len(step) == 1:  # the supervisor rotates and starts a longer new log
            os.replace(log, log.with_name("backend.log.1"))
            log.write_text("new1\nnew2\nnew3\nnew4\n", encoding="utf-8")
        elif len(step) == 3:  # and the new file keeps growing
            with open(log, "a", encoding="utf-8") as handle:
                handle.write("new5\n")
        elif len(step) == 4:
            raise KeyboardInterrupt

    rig.ctl.sleep = sleep
    assert rig.ctl.logs("backend", 5, follow=True) == 0
    assert rig.printed == ["old1", "old2", "new1", "new2", "new3", "new4", "new5"]


def test_logs_follow_survives_truncation(rig):
    log = rig.ctx.logs_dir / "backend.log"
    log.write_text("a long first line of the old log\n", encoding="utf-8")
    step = []

    def sleep(seconds):
        step.append(1)
        if len(step) == 1:
            log.write_text("new\n", encoding="utf-8")  # same file, shorter
        else:
            raise KeyboardInterrupt

    rig.ctl.sleep = sleep
    rig.ctl.logs("backend", 5, follow=True)
    assert rig.printed == ["a long first line of the old log", "new"]


@pytest.mark.skipif(sys.platform == "win32", reason="Windows locks an open log against rename; rotation appends instead")
def test_logs_follow_waits_while_the_log_is_missing_between_rotation_steps(rig):
    log = rig.ctx.logs_dir / "backend.log"
    log.write_text("x\n", encoding="utf-8")
    step = []

    def sleep(seconds):
        step.append(1)
        if len(step) == 1:
            os.replace(log, log.with_name("backend.log.1"))  # new file not created yet
        elif len(step) == 2:
            log.write_text("y\n", encoding="utf-8")
        else:
            raise KeyboardInterrupt

    rig.ctl.sleep = sleep
    rig.ctl.logs("backend", 5, follow=True)
    assert rig.printed == ["x", "y"]


def test_port_free_sees_an_ipv6_only_listener():
    import socket

    if not socket.has_ipv6:
        pytest.skip("no IPv6")
    try:
        holder = socket.socket(socket.AF_INET6)
        holder.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        holder.bind(("::1", 0))
    except OSError:
        pytest.skip("no IPv6 loopback")
    with holder:
        holder.listen()
        assert control.port_free(holder.getsockname()[1]) is False


# --- a database that is missing beside leftovers of another one ----------------------------

@pytest.mark.parametrize("leftover", ["maestro_cs.sqlite3.before-import", "maestro_cs.sqlite3-wal"])
def test_start_refuses_when_the_database_is_missing_but_a_leftover_is_not(rig, monkeypatch, leftover):
    # A fresh database beside a stale -wal would replay the old database's rows into it.
    monkeypatch.setattr(runtime, "web_dir_ok", lambda environ=None: True)
    (rig.ctx.home / "data" / leftover).write_bytes(b"x")
    with pytest.raises(ControlError, match=leftover) as info:
        rig.ctl.start(no_browser=True, skip_model=True)
    assert "\n" not in str(info.value) and rig.spawned == []


def test_start_with_a_database_and_its_wal_is_normal(rig, monkeypatch):
    monkeypatch.setattr(runtime, "web_dir_ok", lambda environ=None: True)
    for name in ("maestro_cs.sqlite3", "maestro_cs.sqlite3-wal"):
        (rig.ctx.home / "data" / name).write_bytes(b"x")
    assert rig.ctl.start(no_browser=True, skip_model=True) == 0


def test_run_says_it_and_exits_zero_so_autostart_does_not_loop(rig, monkeypatch, capsys):
    monkeypatch.setattr(runtime, "web_dir_ok", lambda environ=None: True)
    (rig.ctx.home / "data" / "maestro_cs.sqlite3.before-import").write_bytes(b"x")
    assert control.run(rig.ctx) == 0
    assert "maestro_cs.sqlite3.before-import" in capsys.readouterr().out
