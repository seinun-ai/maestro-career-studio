"""Queueing a laptop job with full automation on offers it; nothing else does."""

import uuid

import pytest

from app.config import settings
from app.models.application_proposal import ApplicationProposal
from app.models.job import Job
from app.schemas.auto_apply import AutoApplySettings
from app.services import auto_apply_settings, proposals
from app.services.sync import status

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
