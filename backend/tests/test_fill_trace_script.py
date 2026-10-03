"""`python -m scripts.fill_trace last`: one stored Autofill run's decision path, field by field.

The script runs as a subprocess against a COPY built here with `alembic upgrade head`: it opens
the copy through the same read-only guard as the eval, and the app must be imported only after.
Statuses and label sources are real ones (extension/shared/fill-loop.js header, field-reader.js).
"""

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.autofill_run import AutofillRun
from app.schemas.autofill_trace import RunTrace
from app.services.autofill_trace import DECISIONS
from scripts import fill_trace

BACKEND = Path(__file__).resolve().parents[1]
T0 = datetime(2026, 10, 3, 14, 2, 11, tzinfo=UTC)
TRICKY = 'He said "hi"\n[verified]  "fake"'


def fields(tag: str) -> list[dict]:
    """Four fields ending verified, cannot_operate (failed), needs_answer (left) and already."""
    return [
        {"fid": "f1", "label": f"Disability status {tag}", "label_source": "aria-label", "shape": "select",
         "family": "f:ab12", "outcome": "verified", "round": 1,
         "steps": [{"op": "map", "route": "slot", "slot": "eeo.disability_status", "engine": "jev", "p": 0.97,
                    "floor": 0.9, "ms": 1200},
                   {"op": "pick", "option": 2, "engine": "fast", "p": 0.97, "floor": 0.9, "second": "decided",
                    "first_p": 0.82, "first_same": True, "reason": "matched", "ms": 2100},
                   {"op": "choose", "effect": "no_effect", "word": "no_effect", "ms": 412}]},
        {"fid": "f2", "label": f"Authorized to work {tag}", "shape": "group", "outcome": "cannot_operate",
         "round": 2,
         "steps": [{"op": "polarity", "way": "unsure", "engine": "fast", "p": 0.61, "second": "asked"},
                   {"op": "move", "move": "click:o3", "effect": "progress", "ms": 380}]},
        {"fid": "f3", "label": f"Pronouns {tag}", "shape": "text", "outcome": "needs_answer",
         "steps": [{"op": "map", "route": "none", "why": "unclear_job"},
                   {"op": "pick", "engine": "jev", "chose_none": True, "floor": 0.9, "reason": "abstained"}]},
        {"fid": "f4", "label": f"First name {tag}", "shape": "text", "outcome": "already", "steps": []},
    ]


def expected(run_id: str, host: str, when: str, tag: str, halted: str = "none") -> list[str]:
    """What the script prints for a run built by `trace` with the same arguments."""
    return [
        f"RUN {run_id}  {host}  {when}  fields=4 filled=1 left=1 failed=1 prefilled=1 halted={halted} rounds=2",
        f'[verified]  "Disability status {tag}"  select  label←aria-label  f:ab12  round 1',
        "  map → eeo.disability_status  jev 0.97 ≥0.90  1.2s",
        "  pick opt[2] matched  fast 0.97 ≥0.90  (decided; jev was 0.82, same choice)  2.1s",
        "  choose → no_effect (no_effect)  412ms",
        f'[cannot_operate]  "Authorized to work {tag}"  group  round 2',
        "  polarity unsure  fast 0.61  (asked)",
        "  move click:o3 → progress  380ms",
        f'[needs_answer]  "Pronouns {tag}"  text',
        "  map → route:none (unclear_job)  code",
        "  pick none abstained  jev — ≥0.90",
        f'[already]  "First name {tag}"  text',
    ]


def trace(run_id: str, host: str, started: datetime, tag: str, **extra) -> dict:
    doc = {"run_id": run_id, "host": host, "started_at": started.isoformat(),
           "ended_at": (started + timedelta(seconds=30)).isoformat(), "rounds": 2, "fields": fields(tag), **extra}
    RunTrace.model_validate(doc)   # the hand-built trace is one the extension could have sent
    return doc


def make_db(path: Path, docs: list[dict]) -> Path:
    """A migrated database file holding `docs` as stored runs."""
    path.parent.mkdir()
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    command.upgrade(cfg, "head")
    engine = create_engine(f"sqlite:///{path}")
    with Session(engine) as session:
        for doc in docs:
            session.add(AutofillRun(run_id=doc["run_id"], host=doc["host"],
                                    started_at=datetime.fromisoformat(doc["started_at"]), trace=doc))
        session.commit()
    engine.dispose()
    return path


@pytest.fixture
def copy(tmp_path) -> Path:
    """Three runs: oldest and newest on one host, the middle one (stopped) on another."""
    return make_db(tmp_path / "copy" / "copy.sqlite3", [
        trace("run-oldest-1", "boards.example.com", T0, "oldest"),
        trace("run-middle-2", "jobs.other.org", T0 + timedelta(hours=1), "middle", halted="stopped"),
        trace("run-newest-3", "boards.example.com", T0 + timedelta(hours=2), "newest"),
    ])


@pytest.fixture
def script(tmp_path):
    """Runs the script from backend/ with its settings and log dirs under tmp_path."""
    def run(*args: str, **env: str) -> subprocess.CompletedProcess:
        full = {**os.environ, "SETTINGS_DIR": str(tmp_path), "LOGS_DIR": str(tmp_path), **env}
        return subprocess.run([sys.executable, "-m", "scripts.fill_trace", *args], cwd=BACKEND,
                              capture_output=True, text=True, env=full, timeout=120)
    return run


NEWEST = expected("run-newest-3", "boards.example.com", "2026-10-03 16:02:11Z", "newest")
MIDDLE = expected("run-middle-2", "jobs.other.org", "2026-10-03 15:02:11Z", "middle", halted="stopped")


def test_last_prints_the_newest_run_in_order(copy, script):
    done = script("--db", str(copy), "last")
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == NEWEST


def test_n_prints_the_newest_runs_one_after_another(copy, script):
    done = script("--db", str(copy), "last", "--n", "2")
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == NEWEST + MIDDLE


def test_host_filters_the_runs(copy, script):
    done = script("--db", str(copy), "last", "--host", "jobs.other.org")
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == MIDDLE


def test_no_matching_run_says_so_and_exits_1(copy, script):
    done = script("--db", str(copy), "last", "--host", "nowhere.example")
    assert done.returncode == 1 and "no stored run" in done.stderr


@pytest.mark.parametrize("n", ["0", "-1", "two"])
def test_n_must_be_a_positive_number(copy, script, n):
    done = script("--db", str(copy), "last", "--n", n)
    assert done.returncode == 2 and "--n" in done.stderr and done.stdout == ""


def test_db_may_follow_the_subcommand(copy, script):
    done = script("last", "--db", str(copy))
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == NEWEST


def test_db_is_required(script):
    done = script("last")
    assert done.returncode == 2 and "--db" in done.stderr


def test_a_label_cannot_fake_a_line(tmp_path, script):
    doc = trace("run-tricky-1", "boards.example.com", T0, "x")
    doc["fields"][0]["label"] = TRICKY
    done = script("--db", str(make_db(tmp_path / "t" / "t.sqlite3", [doc])), "last")
    assert done.returncode == 0, done.stderr
    lines = done.stdout.splitlines()
    assert lines[1] == '[verified]  "He said \\"hi\\"\\n[verified]  \\"fake\\""  select  label←aria-label  f:ab12  round 1'
    assert sum(line.startswith("[verified]") for line in lines) == 1


def test_a_trace_that_no_longer_matches_the_schema_is_one_unreadable_row(tmp_path, script):
    doc = trace("run-stale-1", "boards.example.com", T0, "x")
    doc["fields"][0]["shape"] = "radio"   # a shape the schema does not know (stored before it changed)
    done = script("--db", str(make_db(tmp_path / "t" / "t.sqlite3", [doc])), "last")
    assert done.returncode == 0, done.stderr
    [row] = done.stdout.splitlines()
    assert row.startswith("RUN run-stale-1  boards.example.com  unreadable trace at fields.0.shape")
    assert "radio" not in row   # the location, never the value


def test_a_database_in_a_live_data_dir_is_refused(tmp_path, script):
    """DATA_DIR names a temp directory holding the file; nothing is opened."""
    live = tmp_path / "live"
    live.mkdir()
    db = live / "maestro_cs.sqlite3"
    db.write_bytes(b"")
    done = script("--db", str(db), "last", DATA_DIR=str(live))
    assert done.returncode == 2 and "live database" in done.stderr


def test_every_decision_op_has_a_renderer():
    assert set(fill_trace.DECISION_TARGETS) == DECISIONS


def test_importing_the_script_does_not_import_the_app():
    """The app's settings read the environment once, so open_copy must run before any app import."""
    code = "import scripts.fill_trace, sys; assert not [m for m in sys.modules if m == 'app' or m.startswith('app.')]"
    done = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
