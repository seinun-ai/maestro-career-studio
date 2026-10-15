"""scripts/eval_reason.py: replay stored reasoning snapshots against several models and compare. Maintainer-run, never in
CI; the tests here use the scripted fake provider and never a real model."""

import json

import pytest

from app.models.autofill_run import AutofillRun
from app.schemas.autofill_trace import RunTrace
from app.services import llm
from scripts import eval_reason as ev
from tests.fake_provider import FakeProvider, install

SELECT = {"fid": "f1", "question": "How did you hear about this job?", "shape": "select", "required": True,
          "options": [{"ref": "o1", "text": "Company website"}, {"ref": "o2", "text": "Referral"}], "option_count": 2}
SNAPSHOTS = [
    {"why": "page_errors", "round": 1, "fields": [SELECT], "errors": [{"text": "Source"}],
     "buttons": [{"ref": "b1", "text": "Save and Continue", "role": "next"}]},
    {"why": "open_questions", "round": 1,
     "fields": [{"fid": "f4", "question": "Field of study", "shape": "text", "required": True}]},
    {"why": "moved_away", "round": 1, "tabs": [{"ref": "t1", "host": "jobs.acme.test"}]},
]


def say(*actions, note="Sorting it."):
    return json.dumps({"note": note, "actions": list(actions)})


GOOD = [say({"type": "choose", "fid": "f1", "basis": "default"}, {"type": "press_next", "button": "b1"}),
        say({"type": "write", "fid": "f4"}),
        say({"type": "ask_user", "fids": [], "note": "Open the application tab."})]
# Small-model-like: one reply that is not JSON, one that targets a field the page never had, one honest ask.
# Asks while it also acts: the live loop stops at an ask_user anywhere in the reply, so that is an ask.
MIXED = [say({"type": "fill", "fids": ["f1"]}, {"type": "ask_user", "fids": [], "note": "Help."}), say({"type": "write", "fid": "f4"}),
         say({"type": "ask_user", "fids": [], "note": "Open the application tab."})]
SLOPPY = ["I would press next.", say({"type": "write", "fid": "f99"}), say({"type": "ask_user", "fids": [], "note": "Help."})]


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.setattr(llm, "_log_call", lambda *a, **k: None)


def _install(monkeypatch, **scripts):
    for model, replies in scripts.items():
        install(monkeypatch, FakeProvider([[r] for r in replies], name=f"fake-{model}"), model=model)


def test_each_model_is_replayed_over_every_snapshot_and_scored_by_the_servers_own_checker(monkeypatch):
    _install(monkeypatch, strong=GOOD, small=SLOPPY)
    requests = ev.requests_from_json(SNAPSHOTS)
    stats = {m: ev.evaluate(requests, m, present=["preferences.how_heard"], level="history") for m in ("strong", "small")}
    strong, small = stats["strong"], stats["small"]
    assert (strong.n, strong.valid, strong.asked) == (3, 3, 1)
    assert strong.actions == {"choose": 1, "press_next": 1, "write": 1, "ask_user": 1}
    assert (small.n, small.valid, small.asked) == (3, 1, 3)       # a bad reply and a rejected one both end in ask_user
    assert small.rejected == {"model_error": 1, "unknown_id": 1} and (strong.parsed, small.parsed) == (3, 2)
    assert strong.input_tokens == strong.output_tokens == 3 and len(strong.latencies) == 3


def test_an_ask_user_beside_other_actions_counts_as_an_ask(monkeypatch):
    _install(monkeypatch, mixed=MIXED)
    stats = ev.evaluate(ev.requests_from_json(SNAPSHOTS), "mixed", present=[], level="history")
    assert stats.asked == 2 and stats.actions["fill"] == 1 and stats.actions["ask_user"] == 2


def test_the_report_prints_a_row_per_model_with_rates_latency_and_cost(monkeypatch):
    _install(monkeypatch, strong=GOOD, small=SLOPPY)
    requests = ev.requests_from_json(SNAPSHOTS)
    stats = [ev.evaluate(requests, m, present=[], level="history") for m in ("strong", "small")]
    lines = ev.render(stats, prices={"strong": (2.0, 10.0)}).splitlines()
    [strong] = [line for line in lines if line.startswith("strong")]
    [small] = [line for line in lines if line.startswith("small")]
    assert "valid=3/3(100%)" in strong and "ask_user=1/3(33%)" in strong and "choose=1" in strong and "tokens=3/3" in strong
    assert "cost=$" in strong and "cost=n/a" in small and "valid=1/3(33%)" in small and "ask_user=3/3(100%)" in small
    assert "parsed=2/3(67%)" in small and "model_error=1" in small and "unknown_id=1" in small


def test_the_cost_estimate_is_per_million_tokens_of_the_price_given():
    stat = ev.ModelStats("m", n=1, input_tokens=2_000_000, output_tokens=500_000)
    assert ev.cost(stat, {"m": (2.0, 10.0)}) == pytest.approx(9.0)
    assert ev.cost(stat, {}) is None


def test_snapshots_come_from_a_json_list_a_replies_fixture_or_a_trace_list():
    assert len(ev.requests_from_json(SNAPSHOTS)) == 3
    assert len(ev.requests_from_json({"snapshots": SNAPSHOTS})) == 3
    assert len(ev.requests_from_json([{"name": "x", "request": SNAPSHOTS[0]}])) == 1
    trace = {"reasoning": [{"round": 2, "why": "no_change", "snapshot": {"fields": [SELECT]}},
                           {"round": 1, "why": "wall"}, {"round": 1, "why": "loop"}]}
    [one] = ev.requests_from_json([trace])
    assert (one.why, one.round, one.fields[0].fid) == ("no_change", 2, "f1")


def test_a_stored_run_gives_back_each_round_the_model_was_shown(db_session):
    doc = {"run_id": "run-reason-0001", "host": "acme.test", "started_at": "2026-10-14T10:00:00Z",
           "ended_at": "2026-10-14T10:00:05Z", "fields": [],
           "reasoning": [{"round": 1, "why": "page_errors", "model": "m", "ms": 5, "snapshot": {"fields": [SELECT]}},
                         {"round": 2, "why": "page_errors", "stopped": "wall"}]}
    RunTrace.model_validate(doc)
    row = AutofillRun(run_id=doc["run_id"], host="acme.test", started_at=RunTrace.model_validate(doc).started_at, trace=doc)
    [one] = ev.requests_from_runs([row])
    assert (one.why, one.fields[0].question) == ("page_errors", "How did you hear about this job?")


def test_a_snapshot_the_schema_would_refuse_is_named_and_aborts_a_hand_made_file():
    bad = {"why": "page_errors", "round": 1, "fields": [{**SELECT, "value": "Mathematics"}]}
    with pytest.raises(ev.BadSnapshot, match="snapshot 2"):
        ev.requests_from_json([SNAPSHOTS[0], bad])


def test_a_snapshot_the_schema_would_refuse_is_named_and_skipped_when_a_collector_is_given():
    bad = {"why": "page_errors", "round": 1, "fields": [{**SELECT, "value": "Mathematics"}]}
    skipped = []
    kept = ev.requests_from_json([SNAPSHOTS[0], bad, SNAPSHOTS[1]], skipped=skipped)
    assert [r.why for r in kept] == ["page_errors", "open_questions"] and len(skipped) == 1 and "snapshot 2" in skipped[0]
    assert "Mathematics" not in skipped[0]


def test_stored_rounds_a_later_schema_refuses_are_skipped_and_counted_not_fatal():
    from datetime import UTC, datetime

    good = {"run_id": "run-reason-0002", "host": "acme.test", "started_at": "2026-10-14T10:00:00Z",
            "ended_at": "2026-10-14T10:00:05Z", "fields": [],
            "reasoning": [{"round": 1, "why": "page_errors", "snapshot": {"fields": [SELECT]}}]}
    old = {**good, "run_id": "run-reason-0003", "reasoning": [{"round": 1, "why": "page_errors",
                                                              "snapshot": {"fields": [{**SELECT, "question": "x" * 400}]}}]}
    rows = [AutofillRun(run_id=d["run_id"], host="acme.test", started_at=datetime(2026, 10, 14, tzinfo=UTC), trace=d)
            for d in (good, old)]
    skipped = []
    kept = ev.requests_from_runs(rows, skipped=skipped)
    assert len(kept) == 1 and len(skipped) == 1


def test_the_script_asks_for_a_source_and_models():
    with pytest.raises(SystemExit):
        ev.main(["--models", "m"])
    with pytest.raises(SystemExit):
        ev.main(["--snapshots", "x.json", "--db", "y.sqlite3", "--models", "m"])
    with pytest.raises(SystemExit):
        ev.main(["--snapshots", "x.json"])


def test_main_replays_a_file_and_prints_the_report(tmp_path, monkeypatch, capsys):
    _install(monkeypatch, strong=GOOD)
    path = tmp_path / "snaps.json"
    path.write_text(json.dumps(SNAPSHOTS))
    out = tmp_path / "out.json"
    code = ev.main(["--snapshots", str(path), "--models", "strong", "--present", "preferences.how_heard",
                    "--price", "strong=2,10", "--out", str(out)])
    text = capsys.readouterr().out
    assert code == 0 and "strong" in text and "valid=3/3(100%)" in text
    assert json.loads(out.read_text())["strong"]["n"] == 3


def _script(tmp_path, *args, **extra):
    import os
    import subprocess
    import sys
    from pathlib import Path

    env = {**os.environ, "SETTINGS_DIR": str(tmp_path), "LOGS_DIR": str(tmp_path), **extra}
    return subprocess.run([sys.executable, "-m", "scripts.eval_reason", *args], cwd=Path(__file__).resolve().parents[1],
                          capture_output=True, text=True, env=env, timeout=120)


def test_a_database_copy_with_no_reasoning_round_says_there_is_nothing_to_replay(tmp_path):
    from datetime import UTC, datetime

    from tests.test_fill_trace_script import make_db, trace

    copy = make_db(tmp_path / "copy" / "copy.sqlite3", [trace("run-plain-0001", "acme.test", datetime(2026, 10, 3, tzinfo=UTC), "x")])
    done = _script(tmp_path, "--db", str(copy), "--models", "m")
    assert done.returncode == 2 and "no snapshot to replay" in done.stderr


def test_a_database_in_a_live_data_dir_is_refused(tmp_path):
    from tests.test_fill_trace_script import make_db

    live = tmp_path / "live"
    copy = make_db(live / "maestro_cs.sqlite3", [])       # a real database file inside the directory DATA_DIR names
    done = _script(tmp_path, "--db", str(copy), "--models", "m", DATA_DIR=str(live))
    assert done.returncode == 2 and "where a live database lives" in done.stderr
