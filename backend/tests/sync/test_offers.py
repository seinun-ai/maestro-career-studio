"""Queueing a laptop job with full automation on offers it; nothing else does."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import get_db
from app.main import app
from app.models.application_proposal import ApplicationProposal
from app.models.job import Job
from app.schemas.auto_apply import AutoApplySettings
from app.services import auto_apply_settings, proposals
from app.services.sync import hooks, status

CONSENT = {"channel": "frontend"}


def _job(db, owner=None, handover=None):
    row = Job(id=uuid.uuid4(), raw_text="Example role", raw_text_hash=uuid.uuid4().hex,
              title="Engineer", company="Example employer", owner_machine=owner, handover=handover)
    db.info["sync_apply"] = True
    try:
        db.add(row)
        db.commit()
    finally:
        db.info.pop("sync_apply", None)
    return row


def _queue(db, job):
    proposal = proposals.create_proposal(db, job_id=job.id)
    proposals.transition(db, proposal, "accepted", consent=CONSENT)
    db.refresh(job)
    return job.handover


def _automation(db, on):
    auto_apply_settings.set_settings(AutoApplySettings(full_automation=on), db)


def test_queueing_with_full_automation_offers_the_job(db_session, sync_on):
    _automation(db_session, True)
    assert _queue(db_session, _job(db_session)) == "offered"


def test_a_job_already_owned_by_this_copy_is_offered(db_session, sync_on):
    _automation(db_session, True)
    assert _queue(db_session, _job(db_session, owner=status.machine_id(db_session))) == "offered"


def test_nothing_is_offered_without_the_switch(db_session, sync_on):
    _automation(db_session, False)
    assert _queue(db_session, _job(db_session)) is None


def test_nothing_is_offered_with_sync_off(db_session):
    _automation(db_session, True)
    assert _queue(db_session, _job(db_session)) is None


def test_the_always_on_copy_never_offers(db_session, sync_on, monkeypatch):
    _automation(db_session, True)  # synced from the laptop; the copy itself can't write it
    monkeypatch.setattr(settings, "sync_remote_url", "http://127.0.0.1:8101")
    assert _queue(db_session, _job(db_session)) is None


def test_a_job_the_other_copy_owns_is_not_offered(db_session, sync_on):
    _automation(db_session, True)
    job = _job(db_session, owner="other-copy")
    db_session.info["sync_apply"] = True  # the other copy's replica: the proposal arrives by sync
    try:
        row = ApplicationProposal(job_id=job.id, status="pending_review")
        db_session.add(row)
        db_session.commit()
        proposals.transition(db_session, row, "accepted", consent=CONSENT)
    finally:
        db_session.info.pop("sync_apply", None)
    db_session.refresh(job)
    assert job.handover is None


@pytest.mark.parametrize("to", ["rejected", "approved"])
def test_only_queueing_offers(db_session, sync_on, to):
    _automation(db_session, True)
    job = _job(db_session)
    proposal = proposals.create_proposal(db_session, job_id=job.id)
    proposal.evidence_json = [{"kind": "final_review"}]
    proposals.transition(db_session, proposal, to, consent=CONSENT)
    db_session.refresh(job)
    assert job.handover is None


@pytest.fixture
def client(db_session):
    def override():
        yield db_session
    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def _switch(client, on):
    response = client.put("/api/settings/full-automation", json={"value": on})
    assert response.status_code == 200 and response.json()["value"]["full_automation"] is on


def test_switching_full_automation_on_then_queueing_offers_the_job(client, db_session, sync_on):
    _switch(client, True)
    assert _queue(db_session, _job(db_session)) == "offered"


def test_switching_full_automation_off_withdraws_the_offer(client, db_session, sync_on):
    _switch(client, True)
    job = _job(db_session)
    assert _queue(db_session, job) == "offered"
    with pytest.raises(hooks.NotOwnedHere):
        hooks.require_owned(db_session, job.id)
    before = job.sync_rev

    _switch(client, False)

    db_session.refresh(job)
    assert job.handover is None and job.owner_machine is None
    assert job.sync_rev > before
    hooks.require_owned(db_session, job.id)  # editable again
    assert "sync_apply" not in db_session.info
    assert auto_apply_settings.peek_settings(db_session).full_automation is False


def test_switching_off_leaves_unoffered_jobs_alone(client, db_session, sync_on):
    _switch(client, True)
    plain, offered = _job(db_session), _job(db_session)
    _queue(db_session, offered)
    before = plain.sync_rev

    _switch(client, False)

    db_session.refresh(plain)
    assert (plain.handover, plain.sync_rev) == (None, before)


def test_switching_off_with_sync_off_changes_nothing_else(client, db_session):
    _switch(client, True)
    _switch(client, False)
