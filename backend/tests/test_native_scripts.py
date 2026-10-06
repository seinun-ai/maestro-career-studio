"""Native commands: hermetic shell integration plus an opt-in real install."""

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from scripts import sync_key


BACKEND = Path(__file__).resolve().parents[1]
NATIVE = BACKEND / "scripts/native"
SCRIPTS = ("common.sh", "setup.sh", "start.sh", "stop.sh", "health.sh", "sync.sh")
HOME_DIRS = ("data", "applications", "settings", "base_resumes", "kb_documents",
             "logs", "exports", "fastembed_cache")
SENTINEL = "synthetic-secret-do-not-print"
SYNC_KEY = "synthetic-sync-key-do-not-print"
READOUT = {"rss_mb": 144.0, "peak_mb": 150.0, "platform": "linux"}

# These modules replace only dependencies at the subprocess boundary. The
# actual bash commands, permissions, sessions, pidfile and urllib GET run.
FAKE_SUPPORT = '''
import json, os, sys
from pathlib import Path

def record(kind):
    path = Path(os.environ["NATIVE_TEST_RECORDS"]) / (kind + ".json")
    previous = json.loads(path.read_text()) if path.exists() else {"calls": 0}
    names = ("MAESTRO_HOME", "APP_ROOT", "DATA_DIR", "DATABASE_URL",
             "APPLICATIONS_DIR", "SETTINGS_DIR", "BASE_RESUMES_DIR",
             "KB_DOCUMENTS_DIR", "LOGS_DIR", "EXPORTS_DIR", "MALLOC_ARENA_MAX",
             "EMBEDDINGS_OUT_OF_PROCESS", "FASTEMBED_CACHE_PATH", "ALLOWED_HOSTS",
             "TEST_DATABASE_URL", "OPENAI_API_KEY")
    path.write_text(json.dumps({"calls": previous["calls"] + 1, "args": sys.argv[1:],
        "cwd": os.getcwd(), "pid": os.getpid(), "umask": os.umask(0o077),
        "env": {key: os.environ.get(key) for key in names}}))

def dependency(kind):
    record(kind)
    if os.environ.get("NATIVE_TEST_FAIL") == kind:
        print(os.environ.get("OPENAI_API_KEY", ""), file=sys.stderr)
        raise SystemExit(17)
'''

FAKE_VENV = '''
import sys
from pathlib import Path
from native_test_support import record
record("venv")
target = Path(sys.argv[-1]) / "bin/python"
target.parent.mkdir(parents=True)
target.symlink_to(sys.executable)  # argv[0] stays the venv path, as in a real venv
'''

FAKE_UVICORN = '''
import os, signal, subprocess, sys, time
from pathlib import Path
from native_test_support import record
if os.environ.get("NATIVE_TEST_FAIL") == "uvicorn":
    raise SystemExit(17)
if os.environ.get("NATIVE_TEST_HELPER"):
    child = """import os, signal, time
from pathlib import Path
signal.signal(signal.SIGTERM, signal.SIG_IGN)
path = Path(os.environ['NATIVE_TEST_RECORDS']) / 'heartbeat'
while True:
    with path.open('a') as output: output.write('.')
    time.sleep(0.02)
"""
    child_process = subprocess.Popen([sys.executable, "-c", child])
    (Path(os.environ['NATIVE_TEST_RECORDS']) / 'helper.pid').write_text(str(child_process.pid))
record("uvicorn")
while True:
    time.sleep(0.02)
'''

FAKE_HTTP = '''
import io, json, os, socket, urllib.error, urllib.request
from pathlib import Path
from native_test_support import record

class Response(io.BytesIO):
    status = 200

class Opener:
    def open(self, request, timeout):
        url = getattr(request, "full_url", request)
        assert url.startswith("http://127.0.0.1:")
        if getattr(request, "data", None) is not None:
            return self.post(request, url)
        assert timeout <= 1
        record("get")
        if os.environ.get("NATIVE_TEST_FAIL") == "get":
            raise OSError(os.environ.get("OPENAI_API_KEY", ""))
        if url.endswith('/health'):
            # Ready only once THIS launch's fake uvicorn has recorded itself: a record left by an
            # earlier run (stop, then start) must not answer for a launch that has not exec'd yet.
            record_path = Path(os.environ['NATIVE_TEST_RECORDS']) / 'uvicorn.json'
            pidfile = Path(os.environ['MAESTRO_HOME']) / 'backend.pid'
            ready = (record_path.exists() and pidfile.exists()
                     and json.loads(record_path.read_text())['pid'] == int(pidfile.read_text()))
            return Response(json.dumps({"status": "ok" if ready else "waiting"}).encode())
        assert url.endswith('/health/memory')
        body = os.environ.get('NATIVE_TEST_MEMORY',
            '{"rss_mb": 144.0, "peak_mb": 150.0, "platform": "linux"}')
        return Response(body.encode())

    def post(self, request, url):
        records = Path(os.environ["NATIVE_TEST_RECORDS"])
        path = records / "round.json"
        calls = json.loads(path.read_text())["calls"] + 1 if path.exists() else 1
        path.write_text(json.dumps({"calls": calls, "url": url, "method": request.get_method(),
            "body": json.loads(request.data), "content_type": request.get_header("Content-type"),
            "has_auth": request.has_header("Authorization")}))
        if os.environ.get("NATIVE_TEST_FAIL") == "post":
            raise OSError(os.environ.get("OPENAI_API_KEY", ""))
        status = int(os.environ.get("NATIVE_TEST_ROUND_STATUS", "200"))
        body = os.environ.get("NATIVE_TEST_ROUND",
            '{"ok": true, "outcome": "ok", "steps": {}}').encode()
        if status != 200:
            raise urllib.error.HTTPError(url, status, "x", {}, io.BytesIO(body))
        return Response(body)

def build_opener(*handlers):
    assert len(handlers) == 1 and handlers[0].proxies == {}
    return Opener()

class PortProbe:
    options = ()
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def setsockopt(self, level, name, value):
        self.options += ((level, name, value),)
    def bind(self, address):
        assert address[0] == '127.0.0.1' and 0 < address[1] <= 65535
        assert (socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) in self.options
        record('port')
        if os.environ.get('NATIVE_TEST_FAIL') == 'port':
            raise OSError(os.environ.get('OPENAI_API_KEY', ''))

urllib.request.build_opener = build_opener
socket.socket = lambda *args, **kwargs: PortProbe()
'''


FAKE_PS = '''
import json, os, sys
from pathlib import Path

def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False

if sys.argv[1:3] == ['-o', 'stat=']:
    if not alive(int(sys.argv[-1])):
        raise SystemExit(1)
    print('S')
elif sys.argv[1:3] == ['-o', 'args=']:
    import subprocess
    real = subprocess.run(['/bin/ps', *sys.argv[1:]], capture_output=True, text=True)
    sys.stdout.write(real.stdout)
    raise SystemExit(real.returncode)
else:
    assert sys.argv[1:] == ['-eo', 'pgid=,stat=']
    records = Path(os.environ['NATIVE_TEST_RECORDS'])
    parent, helper = records / 'uvicorn.json', records / 'helper.pid'
    pids = [json.loads(parent.read_text())['pid']] if parent.exists() else []
    if helper.exists():
        pids.append(int(helper.read_text()))
    for pid in pids:
        if alive(pid):
            print(os.getpgid(pid), 'S')
'''


def run_script(name, env, timeout=45):
    return subprocess.run(["bash", str(NATIVE / name)], cwd="/", env=env,
                          capture_output=True, text=True, timeout=timeout)


def read_record(ctx, name):
    return json.loads((ctx.records / f"{name}.json").read_text())


def assert_safe(result, ctx):
    output = result.stdout + result.stderr
    log = ctx.home / "logs/backend.log"
    if log.exists():
        output += log.read_text()
    assert SENTINEL not in output


def wait_for_file(path):
    deadline = time.monotonic() + 5
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert path.exists(), "fake backend did not start"


@pytest.fixture
def native_home(tmp_path):
    modules, records = tmp_path / "modules", tmp_path / "records"
    modules.mkdir()
    records.mkdir()
    modules.joinpath("native_test_support.py").write_text(FAKE_SUPPORT)
    modules.joinpath("venv.py").write_text(FAKE_VENV)
    modules.joinpath("uvicorn.py").write_text(FAKE_UVICORN)
    modules.joinpath("sitecustomize.py").write_text(FAKE_HTTP)
    modules.joinpath("native_test_ps.py").write_text(FAKE_PS)
    modules.joinpath("ps").write_text(
        f'#!/bin/bash\nexec {shlex.quote(sys.executable)} -m native_test_ps "$@"\n')
    modules.joinpath("ps").chmod(0o700)
    for name in ("pip", "alembic"):
        modules.joinpath(f"{name}.py").write_text(
            f"from native_test_support import dependency\ndependency({name!r})\n")
    home = tmp_path / "native home with spaces"
    env = {"PATH": f"{modules}:{os.defpath}", "HOME": str(tmp_path), "MAESTRO_HOME": str(home),
           "PYTHON": sys.executable, "PYTHONPATH": str(modules),
           "NATIVE_TEST_RECORDS": str(records), "TEST_DATABASE_URL": "must-be-cleared",
           "OPENAI_API_KEY": SENTINEL}
    ctx = SimpleNamespace(home=home, env=env, records=records)
    yield ctx
    record = records / "uvicorn.json"
    if record.exists():
        pid = json.loads(record.read_text())["pid"]
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            return  # already reaped by stop.sh


def setup_home(ctx):
    result = run_script("setup.sh", ctx.env)
    assert result.returncode == 0, result.stderr
    assert_safe(result, ctx)
    return result


def start_home(ctx):
    setup_home(ctx)
    result = run_script("start.sh", ctx.env)
    assert result.returncode == 0, result.stderr
    wait_for_file(ctx.records / "uvicorn.json")
    assert_safe(result, ctx)
    return result


def assert_private_layout(ctx):
    assert ctx.home.stat().st_mode & 0o777 == 0o700
    assert (ctx.home / "maestro.env").stat().st_mode & 0o777 == 0o600
    for name in HOME_DIRS:
        assert (ctx.home / name).is_dir()


def assert_editable_install(ctx):
    assert read_record(ctx, "venv")["calls"] == 1
    pip = read_record(ctx, "pip")
    assert pip["args"] == ["install", "-e", f"{BACKEND}[mcp]"]
    assert pip["umask"] == 0o077


def assert_migration(ctx):
    migration = read_record(ctx, "alembic")
    assert migration["args"] == ["upgrade", "head"]
    assert migration["cwd"] == str(BACKEND)
    assert migration["env"]["DATABASE_URL"] == f"sqlite:///{ctx.home}/data/maestro_cs.sqlite3"
    assert migration["env"]["TEST_DATABASE_URL"] is None
    assert migration["umask"] == 0o077


def assert_worker(ctx, backend):
    assert backend["args"] == ["app.main:app", "--host", "127.0.0.1",
                               "--port", "8741", "--workers", "1"]
    assert backend["cwd"] == str(BACKEND)
    assert backend["umask"] == 0o077
    assert (ctx.home / "backend.pid").read_text().strip() == str(backend["pid"])


def assert_runtime_paths(env, home):
    expected = {f"{name.upper()}_DIR": str(home / name) for name in HOME_DIRS[:-1]}
    expected.update(APP_ROOT=str(home), DATABASE_URL=f"sqlite:///{home}/data/maestro_cs.sqlite3",
                    TEST_DATABASE_URL=None)
    assert {key: env[key] for key in expected} == expected


def assert_pilot_settings(env, home):
    expected = {"EMBEDDINGS_OUT_OF_PROCESS": "1", "MALLOC_ARENA_MAX": "2",
                "ALLOWED_HOSTS": "localhost,127.0.0.1", "OPENAI_API_KEY": SENTINEL,
                "FASTEMBED_CACHE_PATH": str(home / "fastembed_cache")}
    assert {key: env[key] for key in expected} == expected


def assert_live_commands(ctx):
    again = run_script("start.sh", ctx.env)
    assert again.returncode == 1 and "running" in again.stderr
    assert read_record(ctx, "uvicorn")["calls"] == 1
    healthy = run_script("health.sh", ctx.env)
    assert healthy.returncode == 0 and json.loads(healthy.stdout) == READOUT


@pytest.mark.parametrize("name", (*SCRIPTS, "maestro.env.example"))
def test_native_files_exist(name):
    assert (NATIVE / name).is_file()


@pytest.mark.parametrize("name", SCRIPTS)
def test_native_scripts_are_valid_bash(name):
    result = subprocess.run(["bash", "-n", str(NATIVE / name)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(not shutil.which("shellcheck"), reason="shellcheck is not installed")
def test_native_scripts_pass_shellcheck():
    result = subprocess.run(["shellcheck", "--external-sources", "--source-path=SCRIPTDIR",
                             *(str(NATIVE / name) for name in SCRIPTS)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_native_scripts_never_enable_xtrace():
    for name in SCRIPTS:
        text = (NATIVE / name).read_text()
        assert not re.search(r"\bset\s+(?:-\w*x\w*|-o\s+xtrace)\b", text), name
        assert "bash -x" not in text and "#!/bin/bash -x" not in text


def test_env_example_comments_keys_and_names_the_local_secret_store():
    text = (NATIVE / "maestro.env.example").read_text()
    for key in ("OPENAI_API_KEY", "GEMINI_API_KEY"):
        assert re.search(rf"^#\s*{key}=", text, re.MULTILINE)
        assert not re.search(rf"^\s*{key}=", text, re.MULTILINE)
    assert "secret store" in text and "never" in text and "chat" in text


def test_setup_is_private_idempotent_and_installs_editable_mcp(native_home):
    ctx = native_home
    setup_home(ctx)
    assert_private_layout(ctx)
    env_file = ctx.home / "maestro.env"
    env_file.write_text(f"OPENAI_API_KEY='{SENTINEL}'\nMAESTRO_PORT=8741\n")
    env_file.chmod(0o644)
    ctx.home.chmod(0o755)
    setup_home(ctx)
    assert env_file.read_text() == f"OPENAI_API_KEY='{SENTINEL}'\nMAESTRO_PORT=8741\n"
    assert_private_layout(ctx)
    assert_editable_install(ctx)
    assert_migration(ctx)


@pytest.mark.parametrize("dependency", ["pip", "alembic"])
def test_setup_failure_never_prints_dependency_output(native_home, dependency):
    ctx = native_home
    ctx.env["NATIVE_TEST_FAIL"] = dependency
    result = run_script("setup.sh", ctx.env)
    assert result.returncode == 1 and result.stderr
    assert_safe(result, ctx)


def test_start_enforces_pilot_settings_and_stop_is_idempotent(native_home):
    ctx = native_home
    setup_home(ctx)
    (ctx.home / "maestro.env").write_text(
        f"OPENAI_API_KEY='{SENTINEL}'\nMAESTRO_PORT=8741\n"
        "EMBEDDINGS_OUT_OF_PROCESS=0\nMALLOC_ARENA_MAX=8\nDATA_DIR=/wrong\n"
        "FASTEMBED_CACHE_PATH=/wrong\nALLOWED_HOSTS='*'\n"
        f"printf '%s' '{SENTINEL}'\nprintf '%s' '{SENTINEL}' >&2\n")
    result = run_script("start.sh", ctx.env)
    assert result.returncode == 0, result.stderr
    wait_for_file(ctx.records / "uvicorn.json")
    backend = read_record(ctx, "uvicorn")
    assert_worker(ctx, backend)
    assert_runtime_paths(backend["env"], ctx.home)
    assert_pilot_settings(backend["env"], ctx.home)
    assert_safe(result, ctx)
    assert_live_commands(ctx)
    for name in ("stop.sh", "stop.sh", "health.sh"):
        result = run_script(name, ctx.env)
        assert result.returncode == (1 if name == "health.sh" else 0)
        assert_safe(result, ctx)
    assert not (ctx.home / "backend.pid").exists()


@pytest.mark.parametrize("pid", ["-1", "0", "garbage", "999999999999999999999999"])
def test_bad_pidfiles_cannot_signal_a_process_group(native_home, pid):
    ctx = native_home
    setup_home(ctx)
    (ctx.home / "backend.pid").write_text(pid + "\n")
    assert run_script("health.sh", ctx.env).returncode == 1
    assert run_script("stop.sh", ctx.env).returncode == 0
    assert not (ctx.home / "backend.pid").exists()


@pytest.mark.parametrize("pid", ["2147483648", "4294967295", "9999999999"])
def test_pid_probe_rejects_numbers_that_overflow_a_signed_pid(native_home, pid):
    # Probe only: sending a signal with an overflowing PID can target a group.
    ctx = native_home
    setup_home(ctx)
    (ctx.home / "backend.pid").write_text(pid + "\n")
    result = subprocess.run(
        ["bash", "-c", 'source "$1"; native_read_pid', "native-pid-probe",
         str(NATIVE / "common.sh")], env=ctx.env, capture_output=True, text=True)
    assert result.returncode == 1


def test_stale_pidfile_is_replaced_on_start(native_home):
    ctx = native_home
    setup_home(ctx)
    (ctx.home / "backend.pid").write_text("2147483647\n")
    result = run_script("start.sh", ctx.env)
    assert result.returncode == 0, result.stderr
    wait_for_file(ctx.records / "uvicorn.json")
    assert (ctx.home / "backend.pid").read_text().strip() == str(read_record(ctx, "uvicorn")["pid"])


def time_wait_port():
    """A loopback port with no listener whose last connection sits in TIME_WAIT."""
    with socket.socket() as server:
        # Like uvicorn: Linux only lets a rebind reuse TIME_WAIT left by a SO_REUSEADDR listener.
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen()
        port = server.getsockname()[1]
        client = socket.create_connection(("127.0.0.1", port))
        accepted, _ = server.accept()
        accepted.close()
        client.recv(1)
        client.close()
    return port


def probe_free_port(port):
    env = {"PATH": os.defpath, "HOME": str(NATIVE), "MAESTRO_PORT": str(port),
           "NATIVE_PYTHON": sys.executable}
    return subprocess.run(
        ["bash", "-c", 'source "$1"; native_free_port', "native-port-probe", str(NATIVE / "common.sh")],
        env=env, capture_output=True, text=True).returncode


def test_free_port_check_ignores_time_wait_but_still_sees_a_live_listener():
    assert probe_free_port(time_wait_port()) == 0
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        assert probe_free_port(listener.getsockname()[1]) == 1


@pytest.fixture
def unrelated_process():
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                               start_new_session=True)
    yield process
    process.kill()
    process.wait()


def test_start_treats_a_reused_pid_as_stale_and_leaves_that_process_alone(native_home, unrelated_process):
    ctx = native_home
    setup_home(ctx)
    (ctx.home / "backend.pid").write_text(f"{unrelated_process.pid}\n")
    result = run_script("start.sh", ctx.env)
    assert result.returncode == 0, result.stderr
    wait_for_file(ctx.records / "uvicorn.json")
    assert (ctx.home / "backend.pid").read_text().strip() == str(read_record(ctx, "uvicorn")["pid"])
    assert unrelated_process.poll() is None


def test_stop_and_health_never_signal_a_reused_pid(native_home, unrelated_process):
    ctx = native_home
    setup_home(ctx)
    pidfile = ctx.home / "backend.pid"
    pidfile.write_text(f"{unrelated_process.pid}\n")
    assert run_script("health.sh", ctx.env).returncode == 1
    assert not pidfile.exists(), "health.sh must drop a pidfile that is not ours"
    pidfile.write_text(f"{unrelated_process.pid}\n")
    assert run_script("stop.sh", ctx.env).returncode == 0
    assert not pidfile.exists()
    assert unrelated_process.poll() is None  # neither the process nor its group was signalled


@pytest.mark.skipif(Path("/proc").exists(), reason="/proc supplies the command line without ps")
def test_missing_ps_without_proc_fails_with_a_clear_message(native_home, tmp_path):
    ctx = native_home
    setup_home(ctx)
    (ctx.home / "backend.pid").write_text(f"{os.getpid()}\n")
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "dirname").symlink_to(shutil.which("dirname"))
    env = {**ctx.env, "PATH": str(tools)}
    result = subprocess.run([shutil.which("bash"), str(NATIVE / "health.sh")], env=env,
                            capture_output=True, text=True)
    assert result.returncode == 1 and "ps" in result.stderr


def test_start_keeps_the_previous_log_as_backend_log_1(native_home):
    ctx = native_home
    setup_home(ctx)
    log = ctx.home / "logs/backend.log"
    log.write_text("Traceback: previous crash\n")
    result = run_script("start.sh", ctx.env)
    assert result.returncode == 0, result.stderr
    wait_for_file(ctx.records / "uvicorn.json")
    assert (ctx.home / "logs/backend.log.1").read_text() == "Traceback: previous crash\n"
    assert "previous crash" not in log.read_text()
    assert log.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("failure", ["uvicorn", "port"])
def test_start_failure_cleans_pidfile_and_never_contacts_a_squatted_port(native_home, failure):
    ctx = native_home
    setup_home(ctx)
    ctx.env["NATIVE_TEST_FAIL"] = failure
    result = run_script("start.sh", ctx.env)
    assert result.returncode == 1 and result.stderr
    assert not (ctx.home / "backend.pid").exists()
    if failure == "port":
        assert not (ctx.records / "get.json").exists()
        assert not (ctx.records / "uvicorn.json").exists()
    assert_safe(result, ctx)


@pytest.mark.parametrize("body", ["not json", '{"rss_mb": "secret", "peak_mb": 1}',
                                  '{"rss_mb": -1, "peak_mb": 2, "platform": "linux"}'])
def test_health_rejects_unhealthy_responses_without_printing_them(native_home, body):
    ctx = native_home
    start_home(ctx)
    ctx.env["NATIVE_TEST_MEMORY"] = body.replace("secret", SENTINEL)
    result = run_script("health.sh", ctx.env)
    assert result.returncode == 1 and not result.stdout
    assert_safe(result, ctx)


def test_health_connection_error_is_secret_safe(native_home):
    ctx = native_home
    start_home(ctx)
    ctx.env["NATIVE_TEST_FAIL"] = "get"
    result = run_script("health.sh", ctx.env)
    assert result.returncode == 1 and not result.stdout
    assert_safe(result, ctx)


def test_stop_kills_a_helper_that_outlives_its_parent(native_home):
    ctx = native_home
    ctx.env["NATIVE_TEST_HELPER"] = "1"
    start_home(ctx)
    heartbeat = ctx.records / "heartbeat"
    wait_for_file(heartbeat)
    result = run_script("stop.sh", ctx.env)
    assert result.returncode == 0, result.stderr
    size = heartbeat.stat().st_size
    time.sleep(0.1)
    assert heartbeat.stat().st_size == size, "embedding helper survived stop.sh"
    assert not (ctx.home / "backend.pid").exists()


def test_default_home_and_port_work_without_overrides(native_home):
    ctx = native_home
    ctx.env.pop("MAESTRO_HOME")
    ctx.home = Path(ctx.env["HOME"]) / "maestro"
    start_home(ctx)
    backend = read_record(ctx, "uvicorn")
    assert backend["args"] == ["app.main:app", "--host", "127.0.0.1",
                               "--port", "8001", "--workers", "1"]
    assert_runtime_paths(backend["env"], ctx.home)
    assert_private_layout(ctx)


@pytest.mark.parametrize("port", ["0", "65536", SENTINEL, "8001; echo bad"])
def test_invalid_port_from_env_fails_without_echoing_it(native_home, port):
    ctx = native_home
    setup_home(ctx)
    (ctx.home / "maestro.env").write_text(f"MAESTRO_PORT='{port}'\n")
    result = run_script("start.sh", ctx.env)
    assert result.returncode == 1 and "MAESTRO_PORT" in result.stderr
    assert not (ctx.records / "uvicorn.json").exists()
    assert_safe(result, ctx)


def test_env_syntax_errors_do_not_expose_key_values(native_home):
    ctx = native_home
    setup_home(ctx)
    (ctx.home / "maestro.env").write_text(f"OPENAI_API_KEY='{SENTINEL}\n")
    result = run_script("start.sh", ctx.env)
    assert result.returncode == 1 and result.stderr
    assert_safe(result, ctx)


def run_native(command, env):
    """Run a shell line as a supervisor would; the scripts are reached by absolute path."""
    return subprocess.run(["bash", "-c", command, "watchdog", str(NATIVE)], cwd="/", env=env,
                          capture_output=True, text=True, timeout=45)


WATCHDOG = '"$1/health.sh" >/dev/null 2>&1 || "$1/start.sh" --watchdog'


def pause_marker(ctx):
    return ctx.home / "maintenance"


def test_stop_writes_a_private_maintenance_marker_with_the_utc_time(native_home):
    ctx = native_home
    start_home(ctx)
    result = run_script("stop.sh", ctx.env)
    assert result.returncode == 0, result.stderr
    marker = pause_marker(ctx)
    assert marker.stat().st_mode & 0o777 == 0o600
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\n", marker.read_text())
    assert_safe(result, ctx)


def test_stop_no_pause_leaves_no_marker_and_unknown_flags_are_rejected(native_home):
    ctx = native_home
    start_home(ctx)
    bad = subprocess.run(["bash", str(NATIVE / "stop.sh"), "--bogus"], cwd="/", env=ctx.env,
                         capture_output=True, text=True)
    assert bad.returncode == 1 and "Usage" in bad.stderr
    assert (ctx.home / "backend.pid").exists() and not pause_marker(ctx).exists()
    result = subprocess.run(["bash", str(NATIVE / "stop.sh"), "--no-pause"], cwd="/",
                            env=ctx.env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert not pause_marker(ctx).exists() and not (ctx.home / "backend.pid").exists()


def test_start_watchdog_declines_while_paused_and_exits_zero(native_home):
    ctx = native_home
    setup_home(ctx)
    pause_marker(ctx).write_text("2026-10-06T01:02:03Z\n")
    result = subprocess.run(["bash", str(NATIVE / "start.sh"), "--watchdog"], cwd="/",
                            env=ctx.env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ("Maestro is paused for maintenance since 2026-10-06T01:02:03Z; "
                             "not starting. Run start.sh to resume.\n")
    assert not (ctx.records / "uvicorn.json").exists()
    assert not (ctx.home / "backend.pid").exists()
    assert pause_marker(ctx).exists()
    assert_safe(result, ctx)


def test_start_watchdog_starts_when_not_paused(native_home):
    ctx = native_home
    setup_home(ctx)
    result = subprocess.run(["bash", str(NATIVE / "start.sh"), "--watchdog"], cwd="/",
                            env=ctx.env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    wait_for_file(ctx.records / "uvicorn.json")
    assert (ctx.home / "backend.pid").exists()


def test_plain_start_removes_the_marker_and_starts(native_home):
    ctx = native_home
    start_home(ctx)
    assert run_script("stop.sh", ctx.env).returncode == 0
    assert pause_marker(ctx).exists()
    (ctx.records / "uvicorn.json").unlink()
    result = run_script("start.sh", ctx.env)
    assert result.returncode == 0, result.stderr
    wait_for_file(ctx.records / "uvicorn.json")
    assert not pause_marker(ctx).exists()
    assert (ctx.home / "backend.pid").read_text().strip() == str(read_record(ctx, "uvicorn")["pid"])


def test_a_resume_that_fails_before_the_pidfile_keeps_the_pause(native_home):
    ctx = native_home
    setup_home(ctx)
    pause_marker(ctx).write_text("2026-10-06T01:02:03Z\n")
    (ctx.home / "maestro.env").write_text("MAESTRO_PORT='0'\n")
    result = run_script("start.sh", ctx.env)
    assert result.returncode == 1
    assert pause_marker(ctx).exists()  # the watchdog must not take over a failed resume


def test_a_resume_racing_the_watchdog_starts_one_backend(native_home):
    ctx = native_home
    start_home(ctx)
    for _ in range(3):
        assert run_script("stop.sh", ctx.env).returncode == 0
        calls = read_record(ctx, "uvicorn")["calls"]
        resume = subprocess.Popen(["bash", str(NATIVE / "start.sh")], cwd="/", env=ctx.env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        ticks = [run_native(WATCHDOG, ctx.env) for _ in range(5)]
        out, err = resume.communicate(timeout=45)
        assert resume.returncode == 0, err
        assert all(tick.returncode in (0, 1) for tick in ticks)
        backend = read_record(ctx, "uvicorn")
        assert backend["calls"] == calls + 1
        assert (ctx.home / "backend.pid").read_text().strip() == str(backend["pid"])
        assert not pause_marker(ctx).exists()


def test_a_health_check_during_the_launch_keeps_the_pidfile(native_home):
    """start.sh's pid is the launcher until it exec's into uvicorn. A health.sh or watchdog tick
    in that window used to call it stale and delete the pidfile the launch had just written,
    leaving a backend that stop.sh and the watchdog could not find."""
    ctx = native_home
    setup_home(ctx)
    launcher = subprocess.run(
        ["bash", "-c", 'source "$1/common.sh" && printf %s "$NATIVE_LAUNCHER"', "x", str(NATIVE)],
        capture_output=True, text=True, check=True).stdout
    home = ctx.home.resolve()
    # argv[0] carries the launcher's command line, exactly what ps and /proc show for the real one
    launching = subprocess.Popen(
        ["bash", "-c", 'exec -a "$0" sleep 60', f"{home}/venv/bin/python -c {launcher} app.main:app"])
    try:
        (ctx.home / "backend.pid").write_text(f"{launching.pid}\n")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and "venv/bin/python" not in subprocess.run(
                ["ps", "-o", "args=", "-p", str(launching.pid)], capture_output=True, text=True).stdout:
            time.sleep(0.02)
        health = run_script("health.sh", ctx.env)
        assert "not running" not in health.stderr
        assert (ctx.home / "backend.pid").read_text().strip() == str(launching.pid)
    finally:
        launching.kill()
        launching.wait()


def test_stop_without_a_home_does_not_claim_a_pause(native_home):
    ctx = native_home
    env = {**ctx.env, "MAESTRO_HOME": str(ctx.home / "absent")}
    result = run_script("stop.sh", env)
    assert result.returncode == 0, result.stderr
    assert "paused" not in result.stdout


def test_start_rejects_unknown_flags(native_home):
    ctx = native_home
    setup_home(ctx)
    result = subprocess.run(["bash", str(NATIVE / "start.sh"), "--bogus"], cwd="/", env=ctx.env,
                            capture_output=True, text=True)
    assert result.returncode == 1 and "Usage" in result.stderr
    assert not (ctx.records / "uvicorn.json").exists()


def test_health_says_paused_and_still_exits_one(native_home):
    ctx = native_home
    start_home(ctx)
    assert run_script("stop.sh", ctx.env).returncode == 0
    since = pause_marker(ctx).read_text().strip()
    result = run_script("health.sh", ctx.env)
    assert result.returncode == 1 and not result.stdout
    assert "paused for maintenance" in result.stderr and since in result.stderr
    pause_marker(ctx).unlink()
    plain = run_script("health.sh", ctx.env)
    assert plain.returncode == 1 and "paused" not in plain.stderr


def test_watchdog_does_not_restart_a_paused_backend(native_home):
    ctx = native_home
    start_home(ctx)
    first_pid = read_record(ctx, "uvicorn")["pid"]
    assert run_script("stop.sh", ctx.env).returncode == 0
    tick = run_native(f"{WATCHDOG}; {WATCHDOG}", ctx.env)
    assert tick.returncode == 0 and "paused for maintenance" in tick.stdout
    assert read_record(ctx, "uvicorn") == {**read_record(ctx, "uvicorn"), "pid": first_pid, "calls": 1}
    assert not (ctx.home / "backend.pid").exists()


def test_start_after_a_pause_resumes_and_the_watchdog_then_has_nothing_to_do(native_home):
    ctx = native_home
    start_home(ctx)
    assert run_script("stop.sh", ctx.env).returncode == 0
    assert run_script("start.sh", ctx.env).returncode == 0
    assert read_record(ctx, "uvicorn")["calls"] == 2
    assert run_native(WATCHDOG, ctx.env).stdout == ""
    assert read_record(ctx, "uvicorn")["calls"] == 2


def test_stop_no_pause_then_start_restarts_and_the_watchdog_recovers_a_plain_stop(native_home):
    ctx = native_home
    start_home(ctx)
    stopped = subprocess.run(["bash", str(NATIVE / "stop.sh"), "--no-pause"], cwd="/",
                             env=ctx.env, capture_output=True, text=True)
    assert stopped.returncode == 0
    tick = run_native(WATCHDOG, ctx.env)
    assert tick.returncode == 0, tick.stderr
    wait_for_file(ctx.records / "uvicorn.json")
    assert read_record(ctx, "uvicorn")["calls"] == 2


def test_a_marker_that_is_not_a_time_is_never_echoed(native_home):
    ctx = native_home
    setup_home(ctx)
    pause_marker(ctx).write_text(f"{SENTINEL}\n")
    watchdog = subprocess.run(["bash", str(NATIVE / "start.sh"), "--watchdog"], cwd="/",
                              env=ctx.env, capture_output=True, text=True)
    health = run_script("health.sh", ctx.env)
    assert watchdog.returncode == 0 and "unknown time" in watchdog.stdout
    assert health.returncode == 1 and "paused for maintenance" in health.stderr
    assert_safe(watchdog, ctx)
    assert_safe(health, ctx)


# ------------------------------------------------------------------ sync.sh and the key CLI


def run_sync(ctx, *args, round_status=None, round_body=None, fail=None):
    env = dict(ctx.env)
    if round_status is not None:
        env["NATIVE_TEST_ROUND_STATUS"] = str(round_status)
    if round_body is not None:
        env["NATIVE_TEST_ROUND"] = json.dumps(round_body)
    if fail:
        env["NATIVE_TEST_FAIL"] = fail
    return subprocess.run(["bash", str(NATIVE / "sync.sh"), *args], cwd="/", env=env,
                          capture_output=True, text=True, timeout=45)


def posted_round(ctx):
    return read_record(ctx, "round")


def assert_sync_safe(result, ctx):
    assert_safe(result, ctx)
    assert SYNC_KEY not in result.stdout + result.stderr


def test_sync_posts_one_plain_round_to_the_loopback_backend(native_home):
    ctx = native_home
    setup_home(ctx)
    (ctx.home / "maestro.env").write_text("MAESTRO_PORT=8741\n")
    steps = {"reconcile": {"claimed": 0}, "pull": {"jobs": 2}}
    result = run_sync(ctx, round_body={"ok": True, "outcome": "ok", "steps": steps})
    assert result.returncode == 0, result.stderr
    sent = posted_round(ctx)
    assert sent["calls"] == 1 and sent["method"] == "POST"
    assert sent["url"] == "http://127.0.0.1:8741/api/sync/round"
    assert sent["content_type"] == "application/json" and not sent["has_auth"]
    assert sent["body"] == {"force": False, "pair": False, "accept_profile_overwrite": False}
    assert json.loads(result.stdout[result.stdout.index("{"):]) == {"ok": True, "steps": steps}
    assert_sync_safe(result, ctx)


def test_sync_now_forces_a_round_without_pairing(native_home):
    ctx = native_home
    setup_home(ctx)
    assert run_sync(ctx, "--now").returncode == 0
    assert posted_round(ctx)["body"] == {"force": True, "pair": False, "accept_profile_overwrite": False}


def test_sync_passes_pairing_through_and_forces_past_the_backoff(native_home):
    ctx = native_home
    setup_home(ctx)
    assert run_sync(ctx, "--pair").returncode == 0
    assert posted_round(ctx)["body"] == {"force": True, "pair": True, "accept_profile_overwrite": False}
    assert run_sync(ctx, "--pair", "--accept-profile-overwrite").returncode == 0
    assert posted_round(ctx)["body"] == {"force": True, "pair": True, "accept_profile_overwrite": True}


@pytest.mark.parametrize("args", [("--bogus",), ("--accept-profile-overwrite",), ("--pair", "extra"),
                                  ("--pair", "--bogus"), ("pair",), ("--now", "--accept-profile-overwrite")])
def test_sync_rejects_unknown_flags_with_usage_and_posts_nothing(native_home, args):
    ctx = native_home
    setup_home(ctx)
    result = run_sync(ctx, *args)
    assert result.returncode == 1 and "Usage: sync.sh [--now | --pair [--accept-profile-overwrite]]" in result.stderr
    assert not (ctx.records / "round.json").exists()


def test_sync_declines_while_maintenance_is_paused(native_home):
    ctx = native_home
    setup_home(ctx)
    pause_marker(ctx).write_text("2026-10-06T10:11:12Z\n")
    result = run_sync(ctx)
    assert result.returncode == 0 and "2026-10-06T10:11:12Z" in result.stdout
    assert "paused" in result.stdout and len(result.stdout.strip().splitlines()) == 1
    assert not (ctx.records / "round.json").exists()
    pause_marker(ctx).write_text(f"{SENTINEL}\n")
    odd = run_sync(ctx, "--pair")
    assert odd.returncode == 0 and "unknown time" in odd.stdout
    assert_safe(odd, ctx)
    assert not (ctx.records / "round.json").exists()


BACKOFF = {"ok": False, "outcome": "transient",
           "skipped": "The last sync failed. Next try at 2026-10-06T11:00:00+00:00."}


@pytest.mark.parametrize(("status", "body", "code", "words"), [
    (200, {"ok": True, "outcome": "ok", "steps": {"pull": {"jobs": 1}}}, 0, "Synced"),
    (200, {"ok": False, "outcome": "needs_person", "skipped": "Sync isn't set up."},
     1, "Sync isn't set up."),
    (200, BACKOFF, 0, BACKOFF["skipped"]),
    (409, {"outcome": "transient", "detail": "A sync is already running."},
     0, "A sync is already running."),
    (200, {"ok": False, "outcome": "transient", "error": "502: Your laptop didn't answer.",
           "steps": {"push": {"sent": 0}}}, 0, "Sync didn't run: 502: Your laptop didn't answer."),
    (200, {"ok": False, "outcome": "transient", "error": "Laptop unreachable."},
     0, "Sync didn't run: Laptop unreachable. It will try again."),
    (200, {"ok": False, "outcome": "transient", "error": "Your laptop couldn't finish that sync request."},
     0, "Sync didn't run: Your laptop couldn't finish that sync request."),
    (200, {"ok": False, "outcome": "transient", "skipped": "Synced moments ago."},
     0, "Synced moments ago."),
    (200, {"ok": False, "outcome": "transient", "error": "A sync is already running on your laptop."},
     0, "Sync didn't run: A sync is already running on your laptop."),
    (200, {"ok": False, "outcome": "needs_person", "error": "401: Sync key doesn't match."},
     1, "Sync failed: 401: Sync key doesn't match."),
    (200, {"ok": False, "outcome": "needs_person",
           "skipped": "Update Maestro on both machines to the same version."},
     1, "Update Maestro on both machines to the same version."),
    (200, {"ok": False, "outcome": "needs_person",
           "skipped": "This copy isn't paired with your laptop yet; run the first sync with the pair option."},
     1, "This copy isn't paired with your laptop yet; run the first sync with the pair option."),
    (200, {"ok": False, "outcome": "needs_person",
           "error": "413: Your laptop refused a request as too large."},
     1, "413: Your laptop refused a request as too large."),
    (409, {"outcome": "needs_person", "detail": "The backend refused the request."},
     1, "The backend refused the request."),
    (409, {"detail": "A sync is already running."}, 1, "unreadable"),
    (404, {"detail": "Not Found"}, 1, "always-on copy"),
    (403, {"detail": "Browser requests can't use this."}, 1, "refused"),
    (500, {"detail": "boom"}, 1, "500"),
    (503, {"outcome": "transient", "error": "Try again later."}, 1, "503"),
    (200, "not an object", 1, "unreadable"),
    (200, {"ok": True, "steps": {}}, 1, "unreadable"),
    (200, {"ok": True, "outcome": "unknown"}, 1, "unreadable"),
    (200, {"ok": False, "outcome": []}, 1, "unreadable"),
    (200, {"outcome": "ok"}, 1, "unreadable"),
])
def test_sync_exit_codes_and_one_line_report(native_home, status, body, code, words):
    ctx = native_home
    setup_home(ctx)
    result = run_sync(ctx, round_status=status, round_body=body)
    assert result.returncode == code, result.stderr
    assert words in result.stdout + result.stderr
    assert_sync_safe(result, ctx)


def test_sync_failure_to_reach_the_backend_is_exit_one_and_silent_about_why(native_home):
    ctx = native_home
    setup_home(ctx)
    result = run_sync(ctx, fail="post")
    assert result.returncode == 1 and "not reachable" in result.stderr
    assert_sync_safe(result, ctx)


@pytest.mark.parametrize("status", [200, 409])
def test_sync_unreadable_backend_reply_is_exit_one_without_echoing_it(native_home, status):
    ctx = native_home
    setup_home(ctx)
    ctx.env["NATIVE_TEST_ROUND"] = f"<html>{SENTINEL} {SYNC_KEY}</html>"
    result = run_sync(ctx, round_status=status)
    assert result.returncode == 1 and "unreadable" in result.stderr
    assert_sync_safe(result, ctx)


def test_sync_reports_only_the_round_summary_and_message(native_home):
    ctx = native_home
    setup_home(ctx)
    result = run_sync(ctx, round_body={
        "ok": True, "outcome": "ok", "steps": {}, "key": SYNC_KEY,
        "bundle": {"password": SENTINEL}, "request_body": SENTINEL,
    })
    assert result.returncode == 0 and "Synced" in result.stdout
    assert_sync_safe(result, ctx)


def test_sync_without_a_venv_is_a_plain_error(native_home):
    ctx = native_home
    setup_home(ctx)
    shutil.rmtree(ctx.home / "venv")
    result = run_sync(ctx)
    assert result.returncode == 1 and "run setup.sh" in result.stderr


def test_sync_never_prints_a_key_in_the_key_file(native_home):
    ctx = native_home
    setup_home(ctx)
    (ctx.home / "sync-key").write_text(SYNC_KEY + "\n")
    (ctx.home / "sync-key").chmod(0o600)
    for status, body in ((200, {"ok": True, "outcome": "ok", "steps": {}}),
                         (200, {"ok": False, "outcome": "needs_person", "error": "x"}),
                         (500, {"detail": "boom"})):
        result = run_sync(ctx, "--pair", round_status=status, round_body=body)
        assert_sync_safe(result, ctx)
    assert_sync_safe(run_sync(ctx, fail="post"), ctx)
    assert_sync_safe(run_sync(ctx, "--bogus"), ctx)


def exported_sync_key_file(ctx):
    result = subprocess.run(
        ["bash", "-c", 'source "$1"; native_load_env; printf %s "${SYNC_KEY_FILE-unset}"',
         "probe", str(NATIVE / "common.sh")], cwd="/", env=ctx.env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_common_always_exports_the_key_file_path(native_home):
    ctx = native_home
    setup_home(ctx)
    expected = str(ctx.home.resolve() / "sync-key")
    # a key created after start must be found without a restart, so the path is set before it exists
    assert not (ctx.home / "sync-key").exists()  # setup writes no key
    assert exported_sync_key_file(ctx) == expected
    (ctx.home / "sync-key").write_text(SYNC_KEY + "\n")
    assert exported_sync_key_file(ctx) == expected
    (ctx.home / "sync-key").unlink()
    (ctx.home / "sync-key").symlink_to(ctx.home / "elsewhere")
    assert exported_sync_key_file(ctx) == expected  # the backend refuses a symlink and treats it as off


def test_env_example_has_the_commented_remote_url_and_key_file_note():
    text = (NATIVE / "maestro.env.example").read_text()
    assert re.search(r"^#SYNC_REMOTE_URL=http://127\.0\.0\.1:8101$", text, re.MULTILINE)
    assert not re.search(r"^\s*SYNC_REMOTE_URL=", text, re.MULTILINE)
    assert "sync-key" in text


def run_key_cli(tmp_path, *args, key_file="default"):
    env = {key: value for key, value in os.environ.items() if key != "SYNC_KEY_FILE"}
    env["SETTINGS_DIR"] = str(tmp_path / "settings")
    if key_file != "default":
        env["SYNC_KEY_FILE"] = str(key_file)
    return subprocess.run([sys.executable, "-m", "scripts.sync_key", *args], cwd=BACKEND, env=env,
                          capture_output=True, text=True, timeout=60)


def test_sync_key_create_writes_a_private_key_and_prints_only_its_path(tmp_path):
    path = tmp_path / "vault" / "sync-key"
    result = run_key_cli(tmp_path, "create", key_file=path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"{path}\n" and result.stderr == ""
    key = path.read_text().strip()
    assert len(key) >= 32 and key not in result.stdout
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700


def test_sync_key_main_creates_a_private_key_in_process(tmp_path, monkeypatch, capsys):
    path = tmp_path / "native home with spaces" / "sync-key"
    monkeypatch.setattr(sync_key.status.settings, "sync_key_file", path)
    assert sync_key.main(["create"]) == 0
    output = capsys.readouterr()
    assert (output.out, output.err) == (f"{path}\n", "")
    assert len(path.read_text().strip()) >= 32
    permissions = (path.stat().st_mode & 0o777, path.parent.stat().st_mode & 0o777)
    assert permissions == (0o600, 0o700)
    assert sync_key.main(["create"]) == 1
    refusal = capsys.readouterr()
    assert refusal.out == "" and "already exists" in refusal.err
    assert path.read_text().strip() not in output.out + output.err + refusal.out + refusal.err


def test_sync_key_create_refuses_to_overwrite(tmp_path):
    path = tmp_path / "sync-key"
    path.write_text(SYNC_KEY + "\n")
    result = run_key_cli(tmp_path, "create", key_file=path)
    assert result.returncode == 1 and result.stdout == ""
    assert "already exists" in result.stderr and "Traceback" not in result.stderr
    assert SYNC_KEY not in result.stderr
    assert path.read_text() == SYNC_KEY + "\n"


def test_sync_key_show_prints_the_key_and_nothing_else(tmp_path):
    path = tmp_path / "sync-key"
    path.write_text(SYNC_KEY + "\n")
    result = run_key_cli(tmp_path, "show", key_file=path)
    assert result.returncode == 0 and result.stdout == SYNC_KEY + "\n" and result.stderr == ""


def test_sync_key_show_without_a_key_says_so_and_prints_no_key(tmp_path):
    result = run_key_cli(tmp_path, "show", key_file=tmp_path / "none")
    assert result.returncode == 1 and result.stdout == ""
    assert "No sync key" in result.stderr and "create" in result.stderr


def test_sync_key_path_prints_the_path_whether_or_not_a_key_exists(tmp_path):
    path = tmp_path / "sync-key"
    result = run_key_cli(tmp_path, "path", key_file=path)
    assert result.returncode == 0 and result.stdout == f"{path}\n" and not path.exists()
    path.write_text(SYNC_KEY + "\n")
    again = run_key_cli(tmp_path, "path", key_file=path)
    assert again.stdout == f"{path}\n" and SYNC_KEY not in again.stdout + again.stderr


def test_sync_key_defaults_to_the_settings_secrets_directory(tmp_path):
    result = run_key_cli(tmp_path, "create")
    expected = tmp_path / "settings" / "secrets" / "sync-key"
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"{expected}\n" and expected.is_file()


def test_sync_key_help_says_show_is_for_your_own_terminal(tmp_path):
    result = run_key_cli(tmp_path, "show", "--help")
    text = " ".join(result.stdout.split())
    assert result.returncode == 0
    assert "your own terminal" in text and "vault" in text and "never" in text and "chat" in text


def test_sync_key_needs_a_subcommand(tmp_path):
    assert run_key_cli(tmp_path).returncode != 0
    assert run_key_cli(tmp_path, "bogus").returncode != 0


def assert_real_backend_lifecycle(env):
    assert run_script("start.sh", env).returncode == 0
    health = run_script("health.sh", env)
    assert health.returncode == 0, health.stderr
    body = json.loads(health.stdout)
    assert set(body) == {"rss_mb", "peak_mb", "platform"}
    assert body["rss_mb"] > 0 and body["peak_mb"] > 0
    assert run_script("start.sh", env).returncode == 1


@pytest.mark.slow
@pytest.mark.skipif(bool(os.environ.get("MAESTRO_SKIP_SLOW")), reason="MAESTRO_SKIP_SLOW is set")
def test_full_setup_start_health_stop_with_real_venv(tmp_path):
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    env = os.environ.copy()
    env.update(MAESTRO_HOME=str(tmp_path / "maestro"), MAESTRO_PORT=str(port),
               PYTHON=sys.executable, OPENAI_API_KEY="", GEMINI_API_KEY="")
    try:
        setup = run_script("setup.sh", env, timeout=600)
        assert setup.returncode == 0, setup.stderr
        assert_real_backend_lifecycle(env)
    finally:
        assert run_script("stop.sh", env).returncode == 0
    assert run_script("health.sh", env).returncode == 1
