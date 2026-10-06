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


BACKEND = Path(__file__).resolve().parents[1]
NATIVE = BACKEND / "scripts/native"
SCRIPTS = ("common.sh", "setup.sh", "start.sh", "stop.sh", "health.sh")
HOME_DIRS = ("data", "applications", "settings", "base_resumes", "kb_documents",
             "logs", "exports", "fastembed_cache")
SENTINEL = "synthetic-secret-do-not-print"
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
import io, json, os, socket, urllib.request
from pathlib import Path
from native_test_support import record

class Response(io.BytesIO):
    status = 200

class Opener:
    def open(self, request, timeout):
        assert timeout <= 1
        url = getattr(request, "full_url", request)
        assert url.startswith("http://127.0.0.1:")
        record("get")
        if os.environ.get("NATIVE_TEST_FAIL") == "get":
            raise OSError(os.environ.get("OPENAI_API_KEY", ""))
        if url.endswith('/health'):
            ready = (Path(os.environ['NATIVE_TEST_RECORDS']) / 'uvicorn.json').exists()
            return Response(json.dumps({"status": "ok" if ready else "waiting"}).encode())
        assert url.endswith('/health/memory')
        body = os.environ.get('NATIVE_TEST_MEMORY',
            '{"rss_mb": 144.0, "peak_mb": 150.0, "platform": "linux"}')
        return Response(body.encode())

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
