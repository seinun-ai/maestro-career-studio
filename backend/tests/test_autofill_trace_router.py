"""POST /api/autofill/runs: store a run, keep the last 50, fold the counters, clear."""
import json
import re
import threading
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db import get_db
from app.main import app
from app.models.autofill_mechanism_stat import AutofillMechanismStat
from app.models.autofill_run import AutofillRun
from app.schemas.autofill_trace import RunTrace
from app.services import autofill_trace
from app.services.autofill_trace import FAILED, KEPT, band, fold, store_run
from tests.extension_harness import ROOT

T0 = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


def _client(db_session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    return TestClient(app)


def _decision(op="pick", **kw):
    return {"op": op, "engine": "jev", "p": 0.91, "floor": 0.8, "chose_none": False, **kw}


def _act(op="choose", effect="progress", ms=100, **kw):
    return {"op": op, "effect": effect, "ms": ms, **kw}


def _field(fid, outcome, steps, family="f:ab12"):
    return {"fid": fid, "label": "Secret label", "shape": "select", "family": family,
            "steps": steps, "outcome": outcome}


def _run(run_id="run-00000001", started=T0, fields=None, host="secret.example"):
    return {"run_id": run_id, "host": host, "started_at": started.isoformat(),
            "ended_at": started.isoformat(), "fields": fields or []}


def _trace(**kw):
    return RunTrace.model_validate(_run(**kw))


def _stats(db_session):
    db_session.expire_all()
    return {r.key: r.counts for r in db_session.scalars(select(AutofillMechanismStat))}


def _runs(db_session):
    db_session.expire_all()
    return db_session.scalars(select(AutofillRun)).all()


def test_a_post_stores_one_row_and_a_repost_replaces_it_without_folding_twice(db_session):
    client = _client(db_session)
    body = _run(fields=[_field("0-1", "verified", [_decision(), _act()])])
    try:
        assert client.post("/api/autofill/runs", json=body).status_code == 204
        once = _stats(db_session)
        assert client.post("/api/autofill/runs", json=body).status_code == 204
    finally:
        app.dependency_overrides.clear()
    assert len(_runs(db_session)) == 1
    assert _stats(db_session) == once
    assert once["decision|pick|jev|0.8|0.9|answer"] == {"n": 1, "kept": 1}


def test_a_repost_replaces_the_stored_trace(db_session):
    store_run(db_session, _trace(fields=[_field("0-1", "verified", [])]))
    store_run(db_session, _trace(fields=[_field("0-2", "left", [])]))
    (row,) = _runs(db_session)
    assert row.trace["fields"][0]["fid"] == "0-2"


def test_the_stored_trace_leaves_out_none(db_session):
    store_run(db_session, _trace(fields=[_field("0-1", "verified", [_act()])]))
    (row,) = _runs(db_session)
    assert "label_source" not in row.trace["fields"][0]
    assert "halted" not in row.trace


def test_52_posts_keep_the_50_newest_by_started_at(db_session):
    client = _client(db_session)
    try:
        # Posted newest first, so insertion order is the opposite of what survives.
        for i in range(52):
            body = _run(run_id=f"run-{51 - i:08d}", started=T0 + timedelta(minutes=51 - i))
            assert client.post("/api/autofill/runs", json=body).status_code == 204
    finally:
        app.dependency_overrides.clear()
    kept = sorted(r.run_id for r in _runs(db_session))
    assert len(kept) == 50
    assert kept == [f"run-{i:08d}" for i in range(2, 52)]


def test_band_edges():
    assert [band(p) for p in (0.93, 1.0, 0.5, 0.3, 0.7, 0.0, None)] == [
        "0.9", "0.9", "0.5", "0.3", "0.7", "0.0", None]


@pytest.fixture
def folded():
    return fold(_trace(fields=[
        _field("0-1", "verified", [
            _decision("pick", p=0.82, floor=0.9, second="decided", first_p=0.82, first_same=True),
            {"op": "move", "move": "click:o3", "effect": "no_effect", "ms": 40},
            _act("choose", "progress", 60),
        ]),
        _field("0-2", "unconfirmed", [
            _decision("step", p=0.45, floor=0.5, second="asked", first_p=0.4, first_same=False),
            _decision("map", engine="fast", p=0.3, floor=None, chose_none=True),
            {"op": "move", "move": "search:word:2", "effect": "progress", "ms": 10},
            _decision("pick", p=0.95, floor=0.9, second="decided", first_p=0.6, first_same=None),
        ], family=None),
        _field("0-3", "needs_answer", [
            {"op": "pick", "p": 0.99, "floor": 0.9},  # no engine: code decided
            _act("set", "error", 5),
        ]),
    ]))


def test_fold_counts_action_tries_effects_and_ms(folded):
    assert folded["action|f:ab12|click"] == {"tries": 1, "no_effect": 1, "ms": 40}
    assert folded["action|f:ab12|choose"] == {"tries": 1, "progress": 1, "ms": 60}
    assert folded["action|-|search"] == {"tries": 1, "progress": 1, "ms": 10}
    assert folded["action|f:ab12|set"] == {"tries": 1, "error": 1, "ms": 5}


def test_fold_counts_decisions_by_floor_band_and_final_status(folded):
    # The pick was followed by a move with no_effect; the step's next page action progressed.
    assert folded["decision|pick|jev|0.9|0.8|answer"] == {"n": 1, "kept": 1, "rejected": 1}
    assert folded["decision|step|jev|0.5|0.4|answer"] == {"n": 1, "failed": 1}
    assert folded["decision|map|fast|-|0.3|none"] == {"n": 1, "failed": 1}
    assert folded["decision|pick|jev|0.9|0.9|answer"] == {"n": 1, "failed": 1}
    assert sum(k.startswith("decision|") for k in folded) == 4  # the engine-less pick is not counted


def test_fold_counts_first_opinions_only_when_first_same_is_true(folded):
    assert folded["first|pick|0.8"] == {"n": 1, "kept": 1}
    assert [k for k in folded if k.startswith("first|")] == ["first|pick|0.8"]


def test_fold_counts_second_opinions(folded):
    assert folded["second|pick"] == {"decided": 2, "decided_kept": 1}
    assert folded["second|step"] == {"asked": 1}


def test_a_decision_with_no_later_page_action_is_not_rejected():
    got = fold(_trace(fields=[_field("0-1", "left", [_act("choose", "no_effect"), _decision()])]))
    assert got["decision|pick|jev|0.8|0.9|answer"] == {"n": 1, "left": 1}


def test_no_counter_key_or_count_holds_a_host_or_label(db_session):
    store_run(db_session, _trace(fields=[_field("0-1", "verified", [_decision(), _act()])]))
    dumped = json.dumps([[r.key, r.counts] for r in db_session.scalars(select(AutofillMechanismStat))])
    assert dumped != "[]"
    assert "secret.example" not in dumped
    assert "Secret label" not in dumped


def test_two_stores_of_different_runs_both_land_in_the_counters(db_session):
    store_run(db_session, _trace(run_id="run-00000001", fields=[_field("0-1", "verified", [_decision()])]))
    store_run(db_session, _trace(run_id="run-00000002", fields=[_field("0-1", "verified", [_decision()])]))
    assert _stats(db_session)["decision|pick|jev|0.8|0.9|answer"] == {"n": 2, "kept": 2}


def test_store_run_takes_the_write_lock_before_it_looks_the_run_up(db_session, monkeypatch):
    order = []
    real_scalar = db_session.scalar
    monkeypatch.setattr(autofill_trace, "begin_write", lambda db: order.append("lock"))
    monkeypatch.setattr(db_session, "scalar", lambda *a, **k: (order.append("lookup"), real_scalar(*a, **k))[1])
    store_run(db_session, _trace())
    assert order[:2] == ["lock", "lookup"]


def test_threaded_stores_on_separate_sessions_lose_no_increment(db_session, _test_engine):
    Session = sessionmaker(bind=_test_engine, autoflush=False, autocommit=False)
    start = threading.Barrier(4)
    errors = []

    def post(n):
        try:
            with Session() as s:
                start.wait()
                store_run(s, _trace(run_id=f"run-{n:08d}", fields=[_field("0-1", "verified", [_decision()])]))
        except Exception as exc:  # noqa: BLE001 - surfaced by the assert below
            errors.append(exc)

    threads = [threading.Thread(target=post, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert errors == []
    assert _stats(db_session)["decision|pick|jev|0.8|0.9|answer"] == {"n": 4, "kept": 4}
    assert len(_runs(db_session)) == 4


def test_clear_removes_the_runs_keeps_the_counters_and_returns_both_counts(db_session):
    client = _client(db_session)
    try:
        for n in (1, 2):
            client.post("/api/autofill/runs", json=_run(
                run_id=f"run-{n:08d}", fields=[_field("0-1", "verified", [_decision()])]))
        resp = client.delete("/api/autofill/telemetry")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json() == {"deleted": 0, "runs_deleted": 2}
    assert _runs(db_session) == []
    assert _stats(db_session)["decision|pick|jev|0.8|0.9|answer"] == {"n": 2, "kept": 2}


@pytest.mark.parametrize("bad", [{"answer": "Jane"}, {"fields": [{**_field("0-1", "verified", []), "value": "x"}]}])
def test_an_unknown_key_in_the_body_is_a_422(db_session, bad):
    client = _client(db_session)
    try:
        resp = client.post("/api/autofill/runs", json={**_run(), **bad})
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 422
    assert _runs(db_session) == []


def _report_statuses_in_the_fill_loop_header() -> set[str]:
    src = (ROOT / "extension" / "shared" / "fill-loop.js").read_text(encoding="utf-8")
    block = re.search(r"\*\s+report status\s+(.*?)\n \*\s+telemetry", src, re.S)
    assert block, "the fill loop's report-status list moved"
    text = re.sub(r"\([^)]*\)", " ", re.sub(r"\n\s*\*", " ", block.group(1)))
    return set(re.findall(r"[a-z_]{4,}", text.replace("what the panel shows", "")))


def test_the_status_sets_are_pinned_to_the_fill_loop_header():
    header = _report_statuses_in_the_fill_loop_header()
    left = {"blocked", "yours", "needs_answer"}
    assert header == KEPT | FAILED | left
