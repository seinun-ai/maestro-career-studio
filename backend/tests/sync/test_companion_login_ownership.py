"""The Companion's login hand-off refuses a job this copy doesn't own, before the secret is read."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.application_proposal import ApplicationProposal
from app.models.consent_event import ConsentEvent
from app.models.job import Job
from app.schemas.auto_apply import AutoApplySettings
from app.services import auto_apply_settings, job_site_login, proposals
from app.services.sync import status

client = TestClient(app)
EXT = {"Origin": "chrome-extension://abcdefghijklmnopabcdefghijklmnop"}
URL = "/api/companion/job-site-login"


@pytest.fixture(autouse=True)
def _login(sync_on, db_session, monkeypatch):
    job_site_login.write("ada@example.com", "pw-one-long")
    auto_apply_settings.set_settings(AutoApplySettings(full_automation=True), db_session)
    status.machine_id(db_session)  # seed the id now: the route's own session must not write it
    db_session.commit()

    def _never_read():
        raise AssertionError("the secret file was read for a job this copy doesn't own")

    monkeypatch.setattr(job_site_login, "read", _never_read)


def _job(db, owner=None):
    row = Job(id=uuid.uuid4(), raw_text="Example role", raw_text_hash=uuid.uuid4().hex,
              title="Engineer", company="Example employer", owner_machine=owner)
    db.info["sync_apply"] = True
    try:
        db.add(row)
        db.commit()
    finally:
        db.info.pop("sync_apply", None)
    return row


def _refused(db, prop):
    r = client.post(URL, json={"proposal_id": str(prop.id)}, headers=EXT)
    assert r.status_code == 409
    assert "pw-one-long" not in r.text
    assert db.query(ConsentEvent).filter_by(proposal_id=prop.id, action="login_shared").count() == 0
    return r


def test_an_offered_job_is_refused(db_session):
    job = _job(db_session)
    prop = proposals.create_proposal(db_session, job_id=job.id)
    proposals.transition(db_session, prop, "accepted", consent={"channel": "frontend"})
    db_session.refresh(job)
    assert job.handover == "offered"
    assert _refused(db_session, prop).json()["owner"] == "laptop"


def test_a_replica_is_refused(db_session):
    job = _job(db_session, owner="other-copy")
    db_session.info["sync_apply"] = True  # the other copy's proposal arrives by sync
    try:
        prop = ApplicationProposal(job_id=job.id, status="accepted")
        db_session.add(prop)
        db_session.commit()
    finally:
        db_session.info.pop("sync_apply", None)
    assert status.machine_id(db_session) != "other-copy"
    _refused(db_session, prop)
