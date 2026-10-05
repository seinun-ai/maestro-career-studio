"""The run log's service: trim, drop, prune, latest per automation."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.models.agent_run import AgentRun
from app.schemas.agent_runs import AgentRunCreate, AgentRunList, AgentRunRead
from app.services import agent_runs
from tests.test_proposals_models import _mk_job


def _run(db_session, automation="job-hunt", **report):
    payload = AgentRunCreate(automation=automation, outcome="ok", **report)
    return agent_runs.record(db_session, payload, agent="claude-ai")


def test_a_long_digest_and_job_list_are_trimmed_not_refused(db_session):
    jobs = [_mk_job(db_session) for _ in range(3)]
    run = _run(db_session, digest="x" * 2500,
               job_ids=[j.id for j in jobs] + [uuid.uuid4() for _ in range(60)])
    assert len(run.digest) == agent_runs.MAX_DIGEST and run.digest.endswith("…")
    assert run.job_ids == [str(j.id) for j in jobs]


@pytest.mark.parametrize("counts", [{"found": -1}, {"applied": 3}],
                         ids=["negative", "unknown-key"])
def test_bad_counts_are_refused(counts):
    with pytest.raises(ValidationError):
        AgentRunCreate(automation="job-hunt", outcome="ok", counts=counts)


@pytest.mark.parametrize("count", [True, 1.0, 1.5], ids=["boolean", "whole-float", "fraction"])
def test_counts_must_be_strict_non_negative_integers(count):
    with pytest.raises(ValidationError):
        AgentRunCreate(automation="job-hunt", outcome="ok", counts={"found": count})


@pytest.mark.parametrize("automation", ["", "   ", "x" * 41],
                         ids=["empty", "blank", "too-long"])
def test_the_automation_has_a_name_of_at_most_40_characters(automation):
    with pytest.raises(ValidationError):
        AgentRunCreate(automation=automation, outcome="ok")


def test_only_the_newest_runs_are_kept(db_session, monkeypatch):
    monkeypatch.setattr(agent_runs, "MAX_RUNS", 3)
    for n in range(5):
        _run(db_session, digest=str(n))
    kept = db_session.query(AgentRun).order_by(AgentRun.finished_at).all()
    assert [r.digest for r in kept] == ["2", "3", "4"]


def test_pruning_never_deletes_the_run_just_recorded(db_session, monkeypatch):
    monkeypatch.setattr(agent_runs, "MAX_RUNS", 1)
    existing = AgentRun(automation="job-hunt", outcome="ok", digest="future",
                        finished_at=datetime.now(timezone.utc) + timedelta(minutes=5))
    db_session.add(existing)
    db_session.commit()

    recorded = _run(db_session, digest="just recorded")

    kept = db_session.query(AgentRun).all()
    assert len(kept) == 1 and kept[0].id == recorded.id
    assert recorded.digest == "just recorded"


def test_latest_is_one_run_per_automation_with_titles_and_jobs(db_session):
    job = _mk_job(db_session, title="Data Scientist", company="Acme")
    _run(db_session, digest="old")
    _run(db_session, digest="new", job_ids=[job.id])
    _run(db_session, automation="weekly-pipeline")
    latest = {r["automation"]: r for r in agent_runs.latest(db_session)}
    assert latest["job-hunt"]["digest"] == "new"
    assert latest["job-hunt"]["title"] == "Job hunt"
    assert latest["job-hunt"]["jobs"] == [
        {"id": job.id, "title": "Data Scientist", "company": "Acme"}]
    assert latest["weekly-pipeline"]["title"] == "weekly-pipeline"


@pytest.mark.parametrize("outcome", ["ok", "partial", "failed"])
def test_a_report_round_trips_in_the_read_shapes(db_session, outcome):
    payload = AgentRunCreate(automation="  custom run  ", outcome=outcome,
                            counts={"found": 0, "proposed": 1, "skipped": 2,
                                    "tailored": 3, "updated": 4, "needs_you": 5},
                            digest="  Finished.  ")
    run = agent_runs.record(db_session, payload, agent="Codex")
    result = AgentRunRead.model_validate(agent_runs.read_one(db_session, run))
    assert (result.id, result.automation, result.title) == (run.id, "custom run", "custom run")
    assert (result.outcome, result.agent, result.counts) == (outcome, "Codex", payload.counts)
    assert result.digest == "Finished." and result.jobs == []
    assert result.finished_at.utcoffset().total_seconds() == 0
    page = AgentRunList(items=agent_runs.recent(db_session))
    assert page.items == [result]


@pytest.mark.parametrize("report", [
    {"outcome": "success"},
    {"job_ids": ["not-a-uuid"]},
    {"extra": "not allowed"},
], ids=["unknown-outcome", "invalid-job-id", "extra-field"])
def test_invalid_report_shapes_are_refused(report):
    payload = {"automation": "job-hunt", "outcome": "ok", **report}
    with pytest.raises(ValidationError):
        AgentRunCreate.model_validate(payload)


@pytest.mark.parametrize("length", [1999, 2000, 2001])
def test_the_digest_cap_counts_characters_after_stripping(length):
    digest = "é" * length
    payload = AgentRunCreate(automation="x" * 40, outcome="ok", digest=f"  {digest}\n")
    expected = digest if length <= 2000 else digest[:1999] + "…"
    assert payload.digest == expected


def test_job_ids_are_trimmed_before_unknown_ids_are_dropped(db_session):
    job = _mk_job(db_session)
    ids = [uuid.uuid4() for _ in range(50)] + [job.id]
    payload = AgentRunCreate(automation="job-hunt", outcome="ok", job_ids=ids)
    assert payload.job_ids == ids[:50]
    run = agent_runs.record(db_session, payload, agent=None)
    assert run.job_ids == [] and run.agent is None


def test_job_ids_are_deduplicated_in_order_before_the_limit(db_session):
    first = _mk_job(db_session)
    second = _mk_job(db_session)
    job_ids = [first.id] * 50 + [second.id]
    payload = AgentRunCreate(automation="job-hunt", outcome="ok", job_ids=job_ids)

    assert payload.job_ids == [first.id, second.id]
    assert agent_runs.record(db_session, payload, agent=None).job_ids == [
        str(first.id), str(second.id)]


def test_a_deleted_job_does_not_break_the_run_log(db_session):
    job = _mk_job(db_session, title="Data Scientist", company="Acme")
    run = _run(db_session, job_ids=[job.id], digest="Found one job.")
    db_session.delete(job)
    db_session.commit()
    result = agent_runs.read_one(db_session, run)
    assert result["jobs"] == [] and result["digest"] == "Found one job."
    assert agent_runs.latest(db_session) == [result]
    assert agent_runs.recent(db_session) == [result]


def test_latest_and_recent_use_newest_first_with_uuid_tie_break(db_session):
    finished_at = datetime(2026, 10, 5, tzinfo=timezone.utc)
    runs = [AgentRun(id=uuid.UUID(int=n), automation=automation, outcome="ok",
                     finished_at=finished_at, digest=str(n))
            for n, automation in [(1, "job-hunt"), (2, "weekly-pipeline"), (3, "job-hunt")]]
    db_session.add_all(runs)
    db_session.commit()
    assert [r["digest"] for r in agent_runs.recent(db_session, limit=2)] == ["3", "2"]
    assert [r["digest"] for r in agent_runs.latest(db_session)] == ["3", "2"]


def test_an_empty_run_log_reads_as_empty(db_session):
    assert agent_runs.recent(db_session) == []
    assert agent_runs.latest(db_session) == []
