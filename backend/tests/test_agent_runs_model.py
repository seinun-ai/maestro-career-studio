"""The run log's table (docs/plans/2026-10-05-agent-dashboard-design.md, Part 2)."""

import uuid
from datetime import timedelta

import pytest

from app.models.agent_run import AgentRun


def test_a_run_round_trips_with_its_defaults(db_session):
    run = AgentRun(automation="job-hunt", outcome="ok")
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    assert run.finished_at is not None
    assert (run.counts, run.digest, run.job_ids, run.agent) == ({}, "", [], None)
    assert isinstance(run.id, uuid.UUID)
    assert run.finished_at.utcoffset() == timedelta(0)


@pytest.mark.parametrize("outcome", ["partial", "failed"])
def test_reported_run_fields_round_trip(db_session, outcome):
    job_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    run = AgentRun(
        automation="custom-hunt",
        outcome=outcome,
        agent="Agent café",
        counts={"found": 12, "needs_you": 1},
        digest="Résumé ready for Café: check the details.",
        job_ids=job_ids,
    )
    db_session.add(run)
    db_session.commit()
    run_id = run.id
    db_session.expunge_all()

    saved = db_session.get(AgentRun, run_id)
    assert saved is not None
    assert (saved.automation, saved.outcome, saved.agent) == (
        "custom-hunt", outcome, "Agent café"
    )
    assert saved.counts == {"found": 12, "needs_you": 1}
    assert saved.digest == "Résumé ready for Café: check the details."
    assert saved.job_ids == job_ids
