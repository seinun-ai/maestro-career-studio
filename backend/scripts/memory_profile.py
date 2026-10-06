"""Measure a throwaway backend: python -m scripts.memory_profile [--cycles 3].

No AI provider is called. ATS uses the real embedding model, downloading it on
first use; set FASTEMBED_CACHE_PATH to reuse a disk-backed cache between runs.
For a backend image, mount the example resume with
``-v <repo>/base_resumes:/base_resumes:ro``; the profiler checks that path when
the checkout copy is absent. Override it with ``--base-resume PATH``.
Only memory readings and step durations are printed or written. Subprocess
output is discarded so inherited secrets cannot appear in diagnostics.
"""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

import httpx


BACKEND = Path(__file__).resolve().parents[1]
HOME_DIRS = ("data", "applications", "settings", "base_resumes", "kb_documents", "logs", "exports")
JOB_TEXT = (
    "Example Data Workshop seeks a Data Engineer with five years of experience. "
    "Build reliable Python and SQL data pipelines, distributed data processing "
    "with Apache Spark, and observable analytics platforms. Partner with analysts "
    "to maintain data quality, document contracts, and improve pipeline reliability."
)
CONTAINER_BASE_RESUME = Path("/base_resumes/example.json")


class ProfileError(RuntimeError):
    """A safe, operator-facing error that contains no subprocess or response data."""


def default_base_resume() -> Path:
    checkout_resume = BACKEND.parent / "base_resumes/example.json"
    if checkout_resume.is_file():
        return checkout_resume
    if CONTAINER_BASE_RESUME.is_file():
        return CONTAINER_BASE_RESUME
    return checkout_resume


def build_env(home: Path) -> dict[str, str]:
    """Isolate files without changing the caller's allocator or embedding mode."""
    home = home.resolve()
    env = os.environ.copy()
    env.pop("TEST_DATABASE_URL", None)  # it overrides DATABASE_URL in app.db and alembic
    env.update({f"{name.upper()}_DIR": str(home / name) for name in HOME_DIRS})
    env.update(
        MAESTRO_HOME=str(home), APP_ROOT=str(home),
        DATABASE_URL=f"sqlite:///{home / 'data' / 'maestro_cs.sqlite3'}",
        ALLOWED_HOSTS="localhost,127.0.0.1", LLM_LOG_CONTENT="false",
    )
    # Explicit blanks override .env too; do not give this synthetic run provider credentials.
    for name in ("OPENAI_API_KEY", "GEMINI_API_KEY", "OPENAI_BASE_URL",
                 "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"):
        env[name] = ""
    return env


def prepare_home(home: Path, base_resume: Path) -> None:
    for name in HOME_DIRS:
        (home / name).mkdir(parents=True, exist_ok=True)
    if not base_resume.is_file():
        raise ProfileError(f"example base resume not found at {base_resume}")
    shutil.copyfile(base_resume, home / "base_resumes/example.json")


def migrate(env: dict[str, str]) -> None:
    try:
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=60,
        )
    except subprocess.CalledProcessError as exc:
        raise ProfileError(f"Database migration failed (exit code {exc.returncode}).") from None
    except subprocess.TimeoutExpired:
        raise ProfileError("Database migration timed out.") from None


def start_server(port: int, env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
         "--workers", "1", "--port", str(port)],
        cwd=BACKEND, env=env, start_new_session=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def server_ready(client: httpx.Client) -> bool:
    """A refused connection is normal during startup, never a hidden success."""
    try:
        response = client.get("/health", timeout=1)
        return response.status_code == 200 and response.json() == {"status": "ok"}
    except (httpx.HTTPError, ValueError):
        return False


def wait_for_startup(client: httpx.Client, process: subprocess.Popen, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ProfileError("The profiling backend exited during startup.")
        if server_ready(client):
            return
        time.sleep(0.1)
    raise ProfileError("The profiling backend did not become healthy in time.")


def signal_server(process: subprocess.Popen, sig: signal.Signals) -> None:
    # Include render/helper descendants, even if the backend has already exited.
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        return


def stop_server(process: subprocess.Popen) -> None:
    signal_server(process, signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        signal_server(process, signal.SIGKILL)
        process.wait()
    signal_server(process, signal.SIGKILL)  # a helper can outlive an already-reaped parent


@contextmanager
def temporary_backend(port: int, base_resume: Path):
    with tempfile.TemporaryDirectory(prefix="maestro-memory-") as directory:
        home = Path(directory)
        prepare_home(home, base_resume)
        env = build_env(home)
        migrate(env)
        process = start_server(port, env)
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=120, trust_env=False) as client:
                wait_for_startup(client, process)
                yield client
        finally:
            stop_server(process)


def require_free_port(port: int) -> None:
    """Refuse to profile or mutate an unrelated backend already on this port."""
    with socket.socket() as probe:
        # A just-stopped backend leaves TIME_WAIT sockets; a live listener still fails.
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            raise ProfileError("Profiling port unavailable; choose another --port.") from None


def request_json(
    client: httpx.Client, step: str, method: str, path: str, body: dict | None,
) -> httpx.Response:
    try:
        response = client.request(method, path, json=body)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ProfileError(f"{step}: HTTP {exc.response.status_code}.") from None
    except httpx.HTTPError:
        raise ProfileError(f"{step}: HTTP request failed (status unavailable).") from None
    return response


def sample(client: httpx.Client, step: str, cycle: int, duration: float = 0.0) -> dict:
    response = request_json(client, "health_memory", "GET", "/health/memory", None)
    memory = response.json()
    return {"cycle": cycle, "step": step, "rss_mb": memory["rss_mb"],
            "peak_mb": memory["peak_mb"], "platform": memory["platform"],
            "duration_s": round(duration, 3)}


def measured_request(client: httpx.Client, rows: list[dict], step: str, cycle: int, request: tuple):
    method, path, body = request
    started = time.monotonic()
    response = request_json(client, step, method, path, body)
    duration = time.monotonic() - started
    rows.append(sample(client, step, cycle, duration))
    return response.json()


def job_payload(cycle: int) -> dict:
    cycle_skill = f"synthetic cycle {cycle} marker"
    cycle_responsibility = f"Measure fresh ATS embeddings for synthetic cycle {cycle}."
    return {
        "raw_text": f"{JOB_TEXT} Synthetic profiling cycle {cycle}.", "source": "agent",
        "extracted_json": {
            "company": "Example Data Workshop", "title": "Data Engineer",
            "role_category": "data_engineer", "years_experience_min": 5,
            "skills": [
                {"skill_name": name, "skill_category": "technical", "requirement_level": "required"}
                for name in ("Python", "SQL", "Apache Spark", "data pipelines", "data quality", cycle_skill)
            ],
            "responsibilities": [
                "Build reliable data pipelines and maintain analytics data quality.",
                cycle_responsibility,
            ],
        },
    }


def receipt_payload(application_id: str) -> dict:
    return {
        "channel": "agent", "application_id": application_id, "base_resume": "example",
        "step": "Synthetic screening", "host": "jobs.example",
        "fields": [
            {"question": f"Describe synthetic project {index + 1}", "section": "Screening",
             "answer": "Built reliable Python and SQL data pipelines with documented quality checks.",
             "source": "resume", "required": True}
            for index in range(40)
        ],
    }


def run_cycle(client: httpx.Client, cycle: int) -> list[dict]:
    rows = []
    job = measured_request(client, rows, "save_job", cycle,
                           ("POST", "/api/jobs/ingest", job_payload(cycle)))
    job_id = job["id"]
    measured_request(client, rows, "score_ats", cycle, ("POST", "/api/ats-scores", {
        "job_id": job_id, "target_type": "base_resume", "target_id": "example",
    }))
    application = measured_request(client, rows, "create_application", cycle,
                                   ("POST", "/api/applications/from-base", {
                                       "job_id": job_id, "base_resume": "example", "ops": [],
                                   }))
    application_id = application["id"]
    measured_request(client, rows, "render_pdf", cycle,
                     ("POST", f"/api/applications/{application_id}/render", None))
    measured_request(client, rows, "post_filled_answers", cycle,
                     ("POST", f"/api/jobs/{job_id}/filled-answers", receipt_payload(application_id)))
    measured_request(client, rows, "read_filled_answers", cycle,
                     ("GET", f"/api/jobs/{job_id}/filled-answers", None))
    measured_request(client, rows, "list_proposals", cycle,
                     ("GET", "/api/proposals?limit=500", None))
    measured_request(client, rows, "read_automations", cycle, ("GET", "/api/automations", None))
    return rows


def run_profile(
    port: int = 8711, cycles: int = 3, base_resume: Path | None = None,
) -> list[dict]:
    require_free_port(port)
    with temporary_backend(port, base_resume or default_base_resume()) as client:
        rows = [sample(client, "startup", 0)]
        for cycle in range(1, cycles + 1):
            rows.extend(run_cycle(client, cycle))
    return rows


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a positive integer") from None
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def port_number(value: str) -> int:
    port = positive_int(value)
    if port > 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=port_number, default=8711)
    parser.add_argument("--cycles", type=positive_int, default=3)
    parser.add_argument("--json", type=Path, help="write the readings as a JSON array")
    parser.add_argument("--base-resume", type=Path, default=default_base_resume(),
                        help="path to example.json (checkout or /base_resumes/example.json)")
    return parser.parse_args(argv)


def print_table(rows: list[dict]) -> None:
    print(f"{'cycle':>5}  {'step':<24} {'rss_mb':>9} {'peak_mb':>9} {'seconds':>9}")
    for row in rows:
        print(f"{row['cycle']:>5}  {row['step']:<24} {row['rss_mb']:>9.1f} "
              f"{row['peak_mb']:>9.1f} {row['duration_s']:>9.3f}")


def _handle_sigterm(_signum, _frame) -> None:
    raise KeyboardInterrupt


def _run(args: argparse.Namespace) -> int:
    try:
        rows = run_profile(port=args.port, cycles=args.cycles, base_resume=args.base_resume)
        print_table(rows)
        if args.json is not None:
            args.json.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    except KeyboardInterrupt:
        print("Memory profiling interrupted; the temporary backend was cleaned up.", file=sys.stderr)
        return 130
    except ProfileError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        # Unexpected exception text, command arguments, and subprocess diagnostics can contain secrets.
        print(type(exc).__name__, file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    previous_handler = signal.signal(signal.SIGTERM, _handle_sigterm)
    try:
        return _run(args)
    finally:
        signal.signal(signal.SIGTERM, previous_handler)


if __name__ == "__main__":
    raise SystemExit(main())
