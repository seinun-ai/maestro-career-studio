"""`python -m scripts.fill_trace last` (one stored run's decision path, field by field) and `report`
(the counters and runs aggregated).

The script runs as a subprocess against a COPY built here with `alembic upgrade head`: it opens
the copy through the same read-only guard as the eval, and the app must be imported only after.
Statuses and label sources are real ones (extension/shared/fill-loop.js header, field-reader.js).
"""

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.autofill_run import AutofillRun
from app.schemas.autofill_trace import RunTrace
from app.services.autofill_choose import CLOSEST_FLOOR
from app.services.autofill_trace import DECISIONS, parse_key, store_run
from scripts import fill_trace

BACKEND = Path(__file__).resolve().parents[1]
T0 = datetime(2026, 10, 3, 14, 2, 11, tzinfo=UTC)
TRICKY = 'He said "hi"\n[verified]  "fake"\u2028[verified]\u2029[verified]\x85[verified]'


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


def migrated(path: Path) -> str:
    """The URL of a new database file at `path`, migrated to head."""
    path.parent.mkdir()
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    url = f"sqlite:///{path}"
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    return url


def make_db(path: Path, docs: list[dict], stored: dict | None = None) -> Path:
    """A migrated database file holding `docs` as stored runs (`stored` maps a run_id to what is
    stored instead of its doc, for a trace that is not a trace)."""
    engine = create_engine(migrated(path))
    with Session(engine) as session:
        for doc in docs:
            session.add(AutofillRun(run_id=doc["run_id"], host=doc["host"],
                                    started_at=datetime.fromisoformat(doc["started_at"]),
                                    trace=(stored or {}).get(doc["run_id"], doc)))
        session.commit()
    engine.dispose()
    return path


def make_counted_db(path: Path, docs: list[dict]) -> Path:
    """A migrated database whose runs and counters were written by the real `store_run`."""
    engine = create_engine(migrated(path))
    with Session(engine) as session:
        for doc in docs:
            store_run(session, RunTrace.model_validate(doc))
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
    assert lines[1] == ('[verified]  "He said \\"hi\\"\\n[verified]  \\"fake\\"\\u2028[verified]\\u2029[verified]'
                        '\\u0085[verified]"  select  label←aria-label  f:ab12  round 1')
    assert sum(line.startswith("[verified]") for line in lines) == 1
    assert len(lines) == len(NEWEST)   # the same lines a splitlines() reader sees for an ordinary label


def test_a_trace_that_no_longer_matches_the_schema_is_one_unreadable_row(tmp_path, script):
    doc = trace("run-stale-1", "boards.example.com", T0, "x")
    doc["fields"][0]["shape"] = "radio"   # a shape the schema does not know (stored before it changed)
    done = script("--db", str(make_db(tmp_path / "t" / "t.sqlite3", [doc])), "last")
    assert done.returncode == 0, done.stderr
    [row] = done.stdout.splitlines()
    assert row.startswith("RUN run-stale-1  boards.example.com  unreadable trace at fields.0.shape")
    assert "radio" not in row   # the location, never the value


def test_a_trace_that_is_not_an_object_names_the_root(tmp_path, script):
    doc = trace("run-list-1", "boards.example.com", T0, "x")
    done = script("--db", str(make_db(tmp_path / "t" / "t.sqlite3", [doc], stored={"run-list-1": []})), "last")
    assert done.returncode == 0, done.stderr
    [row] = done.stdout.splitlines()
    assert row.startswith("RUN run-list-1  boards.example.com  unreadable trace at <root> ")


def test_a_run_started_at_another_offset_prints_in_utc(tmp_path, script):
    started = datetime(2026, 10, 3, 9, 2, 11, tzinfo=timezone(timedelta(hours=-5)))
    done = script("--db", str(make_db(tmp_path / "t" / "t.sqlite3", [trace("run-est-1", "boards.example.com",
                                                                          started, "x")])), "last")
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines()[0].startswith("RUN run-est-1  boards.example.com  2026-10-03 14:02:11Z  ")


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


# ---------- report: the section renderers, on hand-built rows (no database)


def row(key: str, **counts: int) -> fill_trace.Row:
    """A counter row as the loader gives it: the key parsed by the key module, then its counts."""
    return parse_key(key)[1], counts


def test_wasted_actions_sort_by_wasted_ms_and_an_untimed_row_shows_a_dash():
    lines = fill_trace.render_wasted([
        row("action|f:aa|set", tries=10, progress=9, no_effect=1, timed=10, ms=1000),
        row("action|f:bb|choose", tries=4, progress=1, no_effect=2, refused=1, effect_unknown=1, timed=4, ms=2000),
        row("action|-|move", tries=5, progress=1, reverted=4),   # never timed: no average, no waste
        row("action|f:cc|write", tries=3, progress=3, timed=3, ms=300),
    ])
    assert lines == [
        "family=f:bb  kind=choose  tries=4  not_progress=75%  unknown=1  avg=500ms  wasted=1.5s",
        "family=f:aa  kind=set  tries=10  not_progress=10%  unknown=0  avg=100ms  wasted=100ms",
        "family=-  kind=move  tries=5  not_progress=80%  unknown=0  avg=—  wasted=—",
        "family=f:cc  kind=write  tries=3  not_progress=0%  unknown=0  avg=100ms  wasted=0ms",
    ]


def test_wasted_actions_show_only_the_top_fifteen():
    rows = [row(f"action|f:{i:02d}|set", tries=1, no_effect=1, timed=1, ms=i) for i in range(20)]
    lines = fill_trace.render_wasted(rows)
    assert len(lines) == 15 and lines[0].startswith("family=f:19") and lines[-1].startswith("family=f:05")


def test_calibration_keeps_answer_none_and_unknown_rows_apart_in_order():
    base = "decision|pick|fast|first|0.9|0.8|"
    lines = fill_trace.render_calibration([
        row(base + "unknown", n=1, left=1),
        row("decision|pick|jev|first|0.9|0.8|answer", n=5, kept=4, failed=1),
        row("decision|map|jev|first|0.9|0.8|answer", n=3, kept=3),
        row(base + "none", n=2, left=2, rejected=1),
        row(base + "answer", n=4, kept=2, left=1, rejected=1),
        row("decision|polarity|fast|second|-|-|yes", n=2, kept=2),
        row("decision|pick|jev|first|0.9|0.7|answer", n=2, kept=2),
    ])
    head = "op={}  engine={}  by={}  floor={}  band={}  choice={}  n={}  kept={}  left={}  failed={}  rejected={}"
    assert lines == [
        head.format("map", "jev", "first", "0.9", "0.8", "answer", 3, "100%", "0%", "0%", "0%"),
        head.format("pick", "fast", "first", "0.9", "0.8", "answer", 4, "50%", "25%", "0%", "25%"),
        head.format("pick", "fast", "first", "0.9", "0.8", "none", 2, "0%", "100%", "0%", "50%"),
        head.format("pick", "fast", "first", "0.9", "0.8", "unknown", 1, "0%", "100%", "0%", "0%"),
        head.format("pick", "jev", "first", "0.9", "0.7", "answer", 2, "100%", "0%", "0%", "0%"),
        head.format("pick", "jev", "first", "0.9", "0.8", "answer", 5, "80%", "0%", "20%", "0%"),
        head.format("polarity", "fast", "second", "-", "-", "yes", 2, "100%", "0%", "0%", "0%"),
    ]


def test_second_opinion_shares_are_of_what_it_decided():
    lines = fill_trace.render_second(
        [row("first|pick|0.9|0.8", n=42, kept=41), row("first|map|0.9|0.7", n=3, kept=1, left=2)],
        [row("second|pick", asked=6, decided=4, decided_kept=3), row("second|polarity", asked=2)],
    )
    assert lines == [
        "first=map  floor=0.9  band=0.7  n=3  kept=33%",
        "first=pick  floor=0.9  band=0.8  n=42  kept=98%",
        "second=pick  asked=6  decided=4  decided_kept=75%",
        "second=polarity  asked=2  decided=0  decided_kept=—",
    ]


def test_slowest_fields_rank_by_steps_then_total_ms():
    fields_ = [("a.example", "short", 2, 9000, "verified"), ("b.example", "slow", 5, 300, "unconfirmed"),
               ("c.example", "slower", 5, 800, "needs_answer")] + [("d.example", f"f{i}", 1, i, "verified")
                                                                   for i in range(12)]
    lines = fill_trace.render_slowest(fields_)
    assert len(lines) == 10
    assert lines[:3] == [
        'host=c.example  label="slower"  steps=5  ms=800ms  outcome=needs_answer',
        'host=b.example  label="slow"  steps=5  ms=300ms  outcome=unconfirmed',
        'host=a.example  label="short"  steps=2  ms=9.0s  outcome=verified',
    ]


# ---------- report: threshold suggestions


SUGGESTED = ("pick: jev at 0.8–0.9 was confirmed and kept 41/42 — its floor 0.90 could be 0.80")


def test_a_confirmed_band_kept_below_its_floor_yields_a_suggestion():
    lines = fill_trace.render_suggestions([row("first|pick|0.9|0.8", n=42, kept=41)])
    assert lines[0] == SUGGESTED and fill_trace.SUGGESTION_NOTE in lines


@pytest.mark.parametrize("seeded", [
    row("first|pick|0.9|0.8", n=19, kept=19),                  # too few decisions
    row("first|pick|0.9|0.8", n=40, kept=37),                  # kept 92.5%
    row("first|pick|0.9|0.9", n=50, kept=50),                  # the band reaches the floor
    row(f"first|pick|{CLOSEST_FLOOR}|0.1", n=50, kept=50),     # the closest floor is not Jev's match floor
    row("first|pick|-|0.8", n=50, kept=50),                    # no floor to compare
])
def test_a_row_that_does_not_qualify_yields_no_suggestion(seeded):
    lines = fill_trace.render_suggestions([seeded])
    assert lines == [fill_trace.NO_SUGGESTION, fill_trace.SUGGESTION_NOTE]
    assert fill_trace.NO_SUGGESTION == ("no suggestion: no band has ≥20 confirmed decisions kept ≥95% "
                                        "below its floor")


def test_the_closest_floor_row_is_skipped_but_a_qualifying_one_beside_it_is_not():
    lines = fill_trace.render_suggestions([row(f"first|pick|{CLOSEST_FLOOR}|0.1", n=50, kept=50),
                                           row("first|pick|0.9|0.8", n=42, kept=41)])
    assert lines == [SUGGESTED, fill_trace.SUGGESTION_NOTE]


def test_no_counters_at_all_prints_no_data_and_still_the_note():
    assert fill_trace.render_suggestions([]) == [fill_trace.NO_DATA, fill_trace.SUGGESTION_NOTE]


# ---------- report: the script, end to end

SECTIONS = ["== Wasted actions ==", "== Calibration ==", "== First engine and second opinion ==",
            "== Slowest fields ==", "== Suggestions =="]


COUNTED_LINES = [   # one line from each section, for 21 runs of the fields() fixture
    "family=f:ab12  kind=choose  tries=21  not_progress=100%  unknown=0  avg=412ms  wasted=8.7s",
    "op=pick  engine=fast  by=second  floor=0.9  band=0.9  choice=unknown  n=21  kept=100%  left=0%  "
    "failed=0%  rejected=100%",
    "first=pick  floor=0.9  band=0.8  n=21  kept=100%",
    "second=pick  asked=0  decided=21  decided_kept=100%",
    'host=boards.example.com  label="Disability status same"  steps=3  ms=3.7s  outcome=verified',
    "pick: jev at 0.8–0.9 was confirmed and kept 21/21 — its floor 0.90 could be 0.80",
    fill_trace.SUGGESTION_NOTE,
]


def test_report_aggregates_counters_and_runs_written_by_store_run(tmp_path, script):
    docs = [trace(f"run-seed-{i:02d}", "boards.example.com", T0 + timedelta(minutes=i), "same") for i in range(21)]
    done = script("--db", str(make_counted_db(tmp_path / "c" / "c.sqlite3", docs)), "report")
    assert done.returncode == 0, done.stderr
    lines = done.stdout.splitlines()
    assert [line for line in lines if line.startswith("== ")] == SECTIONS
    assert set(COUNTED_LINES) <= set(lines)
    assert "(no data)" not in lines


def test_report_on_an_empty_database_prints_no_data_for_every_section(tmp_path, script):
    done = script("--db", str(make_db(tmp_path / "e" / "e.sqlite3", [])), "report")
    assert done.returncode == 0, done.stderr
    lines = done.stdout.splitlines()
    assert [line for line in lines if line.startswith("== ")] == SECTIONS
    assert lines.count("(no data)") == 5
    assert fill_trace.SUGGESTION_NOTE in lines
