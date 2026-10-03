"""`python -m scripts.fill_trace last`: one stored Autofill run's decision path, field by field.

The script runs as a subprocess against a COPY built here with `alembic upgrade head`: it opens
the copy through the same read-only guard as the eval, and the app must be imported only after.
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

BACKEND = Path(__file__).resolve().parents[1]
T0 = datetime(2026, 10, 3, 14, 2, 11, tzinfo=UTC)

FIELDS = [
    {"fid": "f1", "label": "Disability status", "label_source": "aria", "shape": "select", "family": "f:ab12",
     "outcome": "verified", "round": 1,
     "steps": [{"op": "map", "route": "slot", "slot": "eeo.disability_status", "engine": "jev", "p": 0.97,
                "floor": 0.9, "ms": 1200},
               {"op": "pick", "option": 2, "engine": "fast", "p": 0.97, "floor": 0.9, "second": "decided",
                "first_p": 0.82, "first_same": True, "reason": "matched", "ms": 2100},
               {"op": "choose", "effect": "no_effect", "word": "no_effect", "ms": 412}]},
    {"fid": "f2", "label": "Are you authorized to work?", "shape": "group", "outcome": "unconfirmed", "round": 2,
     "steps": [{"op": "polarity", "way": "unsure", "engine": "fast", "p": 0.61, "second": "asked"},
               {"op": "move", "move": "click:o3", "effect": "progress", "ms": 380}]},
    {"fid": "f3", "label": "Pronouns", "shape": "text", "outcome": "left",
     "steps": [{"op": "pick", "engine": "jev", "chose_none": True, "floor": 0.9, "reason": "abstained"}]},
    {"fid": "f4", "label": "First name", "shape": "text", "outcome": "already", "steps": []},
]


def trace(run_id: str, host: str, started: datetime, **extra) -> dict:
    doc = {"run_id": run_id, "host": host, "started_at": started.isoformat(),
           "ended_at": (started + timedelta(seconds=30)).isoformat(), "rounds": 2, "fields": FIELDS, **extra}
    RunTrace.model_validate(doc)   # the hand-built trace is one the extension could have sent
    return doc


@pytest.fixture
def copy(tmp_path) -> Path:
    """A migrated database file with three runs: two on one host, one on another."""
    path = tmp_path / "copy" / "copy.sqlite3"
    path.parent.mkdir()
    ini = BACKEND / "alembic.ini"
    cfg = Config(str(ini))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    command.upgrade(cfg, "head")
    engine = create_engine(f"sqlite:///{path}")
    with Session(engine) as session:
        for run_id, host, hours, extra in [("run-oldest-1", "boards.example.com", 0, {}),
                                           ("run-middle-2", "jobs.other.org", 1, {"halted": "stopped"}),
                                           ("run-newest-3", "boards.example.com", 2, {})]:
            doc = trace(run_id, host, T0 + timedelta(hours=hours), **extra)
            session.add(AutofillRun(run_id=run_id, host=host, started_at=T0 + timedelta(hours=hours), trace=doc))
        session.commit()
    engine.dispose()
    return path


def run_script(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "scripts.fill_trace", *args], cwd=BACKEND,
                          capture_output=True, text=True, env=env, timeout=120)


def test_last_prints_the_newest_run_with_its_counts(copy):
    done = run_script("--db", str(copy), "last")
    assert done.returncode == 0, done.stderr
    head = done.stdout.splitlines()[0]
    assert head.startswith("RUN run-newest-3  boards.example.com  2026-10-03 16:02:11Z  ")
    assert head.endswith("fields=4 filled=1 left=2 prefilled=1 halted=none rounds=2")
    assert "run-oldest-1" not in done.stdout


def test_last_prints_each_field_and_its_steps(copy):
    lines = set(run_script("--db", str(copy), "last").stdout.splitlines())
    assert lines >= {
        '[verified]  "Disability status"  select  label←aria  f:ab12  round 1',
        "  map → eeo.disability_status  jev 0.97 ≥0.90  1.2s",
        "  pick #2 matched  fast 0.97 ≥0.90  (decided; jev was 0.82, same choice)  2.1s",
        "  choose → no_effect (no_effect)  412ms",
        '[unconfirmed]  "Are you authorized to work?"  group  round 2',
        "  polarity unsure  fast 0.61  (asked)",
        "  move click:o3 → progress  380ms",
        '[already]  "First name"  text',
    }


def test_a_none_choice_and_an_unreadable_p_are_marked(copy):
    out = run_script("--db", str(copy), "last").stdout.splitlines()
    assert "  pick none abstained  jev — ≥0.90" in out


def test_host_filters_and_n_takes_the_newest_runs(copy):
    one = run_script("--db", str(copy), "last", "--host", "jobs.other.org")
    assert one.returncode == 0, one.stderr
    assert "jobs.other.org" in one.stdout and "boards.example.com" not in one.stdout
    assert "halted=stopped" in one.stdout
    two = run_script("--db", str(copy), "last", "--n", "2")
    heads = [line for line in two.stdout.splitlines() if line.startswith("RUN ")]
    assert [h.split()[1] for h in heads] == ["run-newest-3", "run-middle-2"]


def test_no_matching_run_says_so_and_exits_1(copy):
    done = run_script("--db", str(copy), "last", "--host", "nowhere.example")
    assert done.returncode == 1 and "no stored run" in done.stderr


def test_a_database_in_a_live_data_dir_is_refused(tmp_path):
    """DATA_DIR names a temp directory holding the file; nothing is opened."""
    live = tmp_path / "live"
    live.mkdir()
    db = live / "maestro_cs.sqlite3"
    db.write_bytes(b"")
    done = run_script("--db", str(db), "last", env={**os.environ, "DATA_DIR": str(live)})
    assert done.returncode == 2 and "live database" in done.stderr
