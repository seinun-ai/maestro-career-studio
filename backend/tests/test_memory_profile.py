"""The measuring tool's unit tests never load or download an embedding model."""

import importlib
import json
import os
from pathlib import Path
import signal
import socket
import sqlite3
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest


BACKEND = Path(__file__).resolve().parents[1]
STEPS = [
    "save_job", "score_ats", "create_application", "render_pdf",
    "post_filled_answers", "read_filled_answers", "list_proposals", "read_automations",
]


def profiler():
    return importlib.import_module("scripts.memory_profile")


def test_import_has_no_process_filesystem_http_or_environment_side_effects(tmp_path):
    code = """
import os, subprocess, tempfile, httpx, sys
def forbidden(*args, **kwargs):
    raise AssertionError('import performed work')
subprocess.Popen = subprocess.run = forbidden
tempfile.TemporaryDirectory = forbidden
httpx.Client = forbidden
before = dict(os.environ)
import scripts.memory_profile
assert dict(os.environ) == before
assert 'app.main' not in sys.modules
"""
    env = {**os.environ, "PYTHONPATH": str(BACKEND)}
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=tmp_path, env=env,
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ""
    assert list(tmp_path.iterdir()) == []


def test_build_env_isolates_all_data_and_preserves_measurement_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:////some/live.sqlite3")
    monkeypatch.setenv("TEST_DATABASE_URL", "sqlite:////some/test.sqlite3")
    env = profiler().build_env(tmp_path)
    for name in ("DATA", "APPLICATIONS", "SETTINGS", "BASE_RESUMES", "KB_DOCUMENTS", "LOGS", "EXPORTS"):
        assert env[f"{name}_DIR"] == str(tmp_path / name.lower())
    assert env["APP_ROOT"] == env["MAESTRO_HOME"] == str(tmp_path)
    assert env["DATABASE_URL"] == f"sqlite:///{tmp_path}/data/maestro_cs.sqlite3"
    assert "TEST_DATABASE_URL" not in env
    assert env["ALLOWED_HOSTS"] == "localhost,127.0.0.1"


def test_build_env_keeps_allocator_embedding_mode_and_cache_but_blanks_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("MALLOC_ARENA_MAX", "2")
    monkeypatch.setenv("EMBEDDINGS_OUT_OF_PROCESS", "1")
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", "/tmp/persistent-model-cache")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-sentinel")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "secret-sentinel")
    env = profiler().build_env(tmp_path)
    assert env["MALLOC_ARENA_MAX"] == "2"
    assert env["EMBEDDINGS_OUT_OF_PROCESS"] == "1"
    assert env["FASTEMBED_CACHE_PATH"] == "/tmp/persistent-model-cache"
    assert env["OPENAI_API_KEY"] == env["LANGFUSE_SECRET_KEY"] == ""
    assert os.environ["OPENAI_API_KEY"] == "secret-sentinel"


def test_parse_args_defaults_and_overrides(tmp_path):
    defaults = profiler().parse_args([])
    assert (defaults.port, defaults.cycles, defaults.json) == (8711, 3, None)
    output = tmp_path / "readings.json"
    args = profiler().parse_args(["--port", "9001", "--cycles", "5", "--json", str(output)])
    assert (args.port, args.cycles, args.json) == (9001, 5, output)


@pytest.mark.parametrize("argv", [
    ["--cycles", "0"], ["--cycles", "-1"],
    ["--port", "0"], ["--port", "65536"],
])
def test_parse_args_rejects_a_run_that_cannot_measure_a_cycle(argv):
    with pytest.raises(SystemExit) as error:
        profiler().parse_args(argv)
    assert error.value.code == 2


def test_prepare_home_and_migrations_use_only_the_throwaway_database(tmp_path):
    module = profiler()
    module.prepare_home(tmp_path)
    for name in ("data", "applications", "settings", "base_resumes", "kb_documents", "logs", "exports"):
        assert (tmp_path / name).is_dir()
    assert (tmp_path / "base_resumes/example.json").read_bytes() == (
        BACKEND.parent / "base_resumes/example.json"
    ).read_bytes()
    module.migrate(module.build_env(tmp_path))
    with sqlite3.connect(tmp_path / "data/maestro_cs.sqlite3") as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()
        assert db.execute("SELECT count(*) FROM jobs").fetchone() == (0,)


JOB_ID = "00000000-0000-0000-0000-000000000001"
APP_ID = "00000000-0000-0000-0000-000000000002"


def validate_ingest(body):
    from app.schemas.job import JobIngest

    job = JobIngest.model_validate(body)
    assert job.raw_text and job.extracted_json.skills and job.source == "agent"


def validate_score(body):
    from app.schemas.ats_score import AtsRunRequest

    score = AtsRunRequest.model_validate(body)
    assert str(score.job_id) == JOB_ID
    assert (score.target_type, score.target_id) == ("base_resume", "example")


def validate_application(body):
    from app.schemas.application import ApplicationFromBase

    application = ApplicationFromBase.model_validate(body)
    assert str(application.job_id) == JOB_ID and application.base_resume == "example"
    assert application.ops == []


def validate_receipt(body):
    from app.schemas.filled_answers import FilledAnswersCreate

    receipt = FilledAnswersCreate.model_validate(body)
    assert str(receipt.application_id) == APP_ID and receipt.channel == "agent"
    assert len(receipt.fields) == len({field.question for field in receipt.fields}) == 40


def cycle_transport(request):
    """Strict HTTP boundary: unknown methods, paths or invalid bodies fail the test."""
    route = (request.method, str(request.url.raw_path, "ascii"))
    validators = {
        ("POST", "/api/jobs/ingest"): validate_ingest,
        ("POST", "/api/ats-scores"): validate_score,
        ("POST", "/api/applications/from-base"): validate_application,
        ("POST", f"/api/jobs/{JOB_ID}/filled-answers"): validate_receipt,
    }
    if validate := validators.get(route):
        validate(json.loads(request.content))
    responses = {
        ("GET", "/health/memory"): {"rss_mb": 144.0, "peak_mb": 150.0, "platform": "linux"},
        ("POST", "/api/jobs/ingest"): {"id": JOB_ID},
        ("POST", "/api/ats-scores"): [],
        ("POST", "/api/applications/from-base"): {"id": APP_ID},
        ("POST", f"/api/applications/{APP_ID}/render"): {"pdf_path": "synthetic.pdf"},
        ("POST", f"/api/jobs/{JOB_ID}/filled-answers"): {
            "id": "00000000-0000-0000-0000-000000000003", "flag_count": 0, "flags": [],
        },
        ("GET", f"/api/jobs/{JOB_ID}/filled-answers"): {"job_id": JOB_ID, "pages": 1, "steps": []},
        ("GET", "/api/proposals?limit=500"): [],
        ("GET", "/api/automations"): [],
    }
    return httpx.Response(200, json=responses[route])


def assert_positive_readings(rows):
    assert all(row["rss_mb"] > 0 and row["peak_mb"] > 0 for row in rows)
    assert all(row["duration_s"] >= 0 for row in rows)


def test_cycle_samples_after_every_ai_free_step_without_a_model():
    seen = []

    def transport(request):
        seen.append((request.method, request.url.path))
        return cycle_transport(request)

    with httpx.Client(base_url="http://127.0.0.1", transport=httpx.MockTransport(transport)) as client:
        rows = profiler().run_cycle(client, 2)
    assert [(row["cycle"], row["step"], row["rss_mb"], row["peak_mb"], row["platform"]) for row in rows] == [
        (2, step, 144, 150, "linux") for step in STEPS
    ]
    assert_positive_readings(rows)
    assert len(seen) == 16
    assert [path for _, path in seen[1::2]] == ["/health/memory"] * 8


@pytest.mark.parametrize("status,body,expected", [
    (200, {"status": "ok"}, True), (503, {"status": "ok"}, False),
    (200, {"status": "wrong"}, False),
])
def test_startup_probe_returns_a_bool(status, body, expected):
    with httpx.Client(base_url="http://127.0.0.1", transport=httpx.MockTransport(
        lambda request: httpx.Response(status, json=body)
    )) as client:
        assert profiler().server_ready(client) is expected


def test_startup_probe_handles_connection_refusal():
    def refused(request):
        raise httpx.ConnectError("not ready", request=request)

    with httpx.Client(base_url="http://127.0.0.1", transport=httpx.MockTransport(refused)) as client:
        assert profiler().server_ready(client) is False


@pytest.mark.parametrize("return_code,timeout,message", [(1, 1, "exited"), (None, 0, "healthy")])
def test_startup_reports_a_dead_or_unresponsive_backend(return_code, timeout, message):
    process = SimpleNamespace(poll=lambda: return_code)
    with httpx.Client(base_url="http://127.0.0.1", transport=httpx.MockTransport(
        lambda request: httpx.Response(503)
    )) as client:
        with pytest.raises(RuntimeError, match=message):
            profiler().wait_for_startup(client, process, timeout=timeout)


def wait_for_file(path):
    deadline = time.monotonic() + 5
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert path.exists(), "test child did not start"


def test_stop_server_kills_a_lingering_helper_after_the_parent_exits(tmp_path):
    module = profiler()
    ready = tmp_path / "helper-heartbeat"
    child_code = (
        "import signal, time; from pathlib import Path; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"path = Path({str(ready)!r})\n"
        "while True:\n"
        "    with path.open('a') as heartbeat: heartbeat.write('.')\n"
        "    time.sleep(0.01)\n"
    )
    parent_code = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); time.sleep(60)"
    )
    process = subprocess.Popen([sys.executable, "-c", parent_code], start_new_session=True)
    try:
        wait_for_file(ready)
        module.stop_server(process)
        size = ready.stat().st_size
        time.sleep(0.1)
        assert ready.stat().st_size == size, "helper survived parent cleanup"
    finally:
        module.signal_server(process, signal.SIGKILL)
        process.wait(timeout=5)


@pytest.mark.parametrize("failure", [None, RuntimeError, KeyboardInterrupt])
def test_temporary_backend_reaps_the_server_and_removes_home_on_every_exit(monkeypatch, failure):
    module = profiler()
    state = {}

    def start(port, env):
        state["home"] = Path(env["MAESTRO_HOME"])
        state["process"] = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True,
        )
        return state["process"]

    monkeypatch.setattr(module, "start_server", start)
    monkeypatch.setattr(module, "migrate", lambda env: None)
    monkeypatch.setattr(module, "wait_for_startup", lambda client, process: None)

    def run():
        with module.temporary_backend(0):
            assert (state["home"] / "base_resumes/example.json").is_file()
            if failure:
                raise failure("secret-sentinel")

    if failure:
        with pytest.raises(failure):
            run()
    else:
        run()
    assert state["process"].poll() is not None
    assert not state["home"].exists()


def test_occupied_port_is_refused_before_contacting_an_existing_backend(monkeypatch):
    module = profiler()
    # Loopback binds are denied in some sandboxes; simulate the OS refusal.
    occupied = MagicMock()
    occupied.__enter__.return_value.bind.side_effect = OSError("Address already in use")
    monkeypatch.setattr(module.socket, "socket", lambda: occupied)
    with pytest.raises(RuntimeError, match="port"):
        module.run_profile(port=8711, cycles=1)


def test_main_prints_table_and_writes_only_readings(tmp_path, monkeypatch, capsys):
    module = profiler()
    rows = [{"cycle": 0, "step": "startup", "rss_mb": 144.0, "peak_mb": 150.0,
             "platform": "linux", "duration_s": 0.0}]
    monkeypatch.setattr(module, "run_profile", lambda port, cycles: rows)
    output = tmp_path / "readings.json"
    assert module.main(["--json", str(output)]) == 0
    assert json.loads(output.read_text()) == rows
    printed = capsys.readouterr()
    assert "startup" in printed.out and "rss_mb" in printed.out and "peak_mb" in printed.out
    assert printed.err == ""


@pytest.mark.parametrize("failure,exit_code", [(RuntimeError, 1), (KeyboardInterrupt, 130)])
def test_main_reports_failure_without_printing_exception_secrets(monkeypatch, capsys, failure, exit_code):
    module = profiler()

    def fail(port, cycles):
        raise failure("secret-sentinel")

    monkeypatch.setattr(module, "run_profile", fail)
    assert module.main([]) == exit_code
    printed = capsys.readouterr()
    assert printed.err and "secret-sentinel" not in printed.err + printed.out


@pytest.mark.slow
@pytest.mark.skipif(bool(os.environ.get("MAESTRO_SKIP_SLOW")), reason="MAESTRO_SKIP_SLOW is set")
def test_end_to_end_real_backend_records_startup_and_every_cycle_step(tmp_path):
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    output = tmp_path / "readings.json"
    result = subprocess.run(
        [sys.executable, "-m", "scripts.memory_profile", "--port", str(port),
         "--cycles", "1", "--json", str(output)],
        cwd=BACKEND, capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, result.stderr
    rows = json.loads(output.read_text())
    assert [row["step"] for row in rows] == ["startup", *STEPS]
    assert [row["cycle"] for row in rows] == [0, *([1] * 8)]
    assert_positive_readings(rows)
