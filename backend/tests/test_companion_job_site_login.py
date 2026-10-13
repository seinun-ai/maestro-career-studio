"""POST /api/companion/job-site-login: the saved login for the Companion's sign-in step.

Same gates as the agent hand-off (full automation, Queued/approved, company off the skip
list) but admitted by the Companion's exact extension origin instead of the MCP header. The
password reaches nothing but this one response (SYSTEM.md inv-job-site-password-local).
"""

import logging
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.db import Base
from app.main import app
from app.models.consent_event import ConsentEvent
from app.schemas.auto_apply import AutoApplySettings
from app.services import auto_apply_settings, job_site_login
from tests.test_proposal_state_machine import _mk_proposal

client = TestClient(app)
# conftest pins MAESTRO_CS_EXTENSION_IDS to this made-up id.
EXT = {"Origin": "chrome-extension://abcdefghijklmnopabcdefghijklmnop"}
SECRET = "pw-one-long"
URL = "/api/companion/job-site-login"


@pytest.fixture(autouse=True)
def _settings_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    job_site_login.write("ada@example.com", SECRET)


def _full_automation(db_session, on=True, **fields):
    auto_apply_settings.set_settings(AutoApplySettings(full_automation=on, **fields), db_session)


@pytest.fixture
def queued(db_session):
    _full_automation(db_session)
    prop = _mk_proposal(db_session)
    prop.status = "accepted"
    db_session.commit()
    return prop


def _post(prop, headers=EXT):
    return client.post(URL, json={"proposal_id": str(prop.id)}, headers=headers)


def _events(db_session, prop):
    db_session.expire_all()
    return db_session.query(ConsentEvent).filter_by(proposal_id=prop.id).all()


def test_the_companion_gets_the_login_for_a_queued_job_and_it_is_audited(db_session, queued):
    r = _post(queued)
    assert r.status_code == 200 and r.json() == {"email": "ada@example.com", "password": SECRET}
    (event,) = _events(db_session, queued)
    assert (event.action, event.channel) == ("login_shared", "companion")
    assert event.evidence_manifest_json is None
    assert SECRET not in (event.note or "") + str(event.evidence_manifest_json)
    db_session.refresh(queued)
    assert (queued.status, queued.cap_reserved_at) == ("accepted", None)


def test_an_approved_job_gets_it_too(db_session, queued):
    queued.status = "approved"
    db_session.commit()
    assert _post(queued).status_code == 200


@pytest.mark.parametrize("headers", [
    {},
    {"Origin": "http://localhost:3000"},
    {"Origin": "chrome-extension://someoneelse"},
    # The agent's MCP header does not stand in for the Companion's origin.
    {"X-Maestro-CS-Origin": "mcp", "X-Maestro-CS-Origin-Detail": "claude-ai"},
])
def test_no_extension_origin_means_no_login(db_session, queued, headers):
    r = _post(queued, headers)
    assert r.status_code == 403
    assert SECRET not in r.text
    assert _events(db_session, queued) == []


def test_refused_while_full_automation_is_off(db_session, queued):
    _full_automation(db_session, on=False)
    r = _post(queued)
    assert r.status_code == 409 and "full automation" in r.json()["detail"]
    assert SECRET not in r.text
    assert _events(db_session, queued) == []


def test_refused_for_a_company_on_the_skip_list(db_session, queued):
    _full_automation(db_session, company_blocklist=["Acme"])
    r = _post(queued)
    assert r.status_code == 409 and "skip list" in r.json()["detail"]
    assert SECRET not in r.text
    assert _events(db_session, queued) == []


@pytest.mark.parametrize("status", [
    "pending_review", "needs_decision", "needs_human", "submitted",
    "submission_uncertain", "rejected", "expired",
])
def test_refused_for_a_proposal_that_is_not_queued(db_session, queued, status):
    queued.status = status
    db_session.commit()
    r = _post(queued)
    assert r.status_code == 409
    assert SECRET not in r.text
    assert _events(db_session, queued) == []


@pytest.mark.parametrize(("email", "password"), [
    (None, None), (None, SECRET), ("ada@example.com", None), ("", SECRET), ("ada@example.com", ""),
])
def test_no_complete_login_saved_is_a_404_without_an_audit(db_session, queued, email, password):
    job_site_login.clear()
    job_site_login.write(email, password)
    r = _post(queued)
    assert r.status_code == 404
    assert SECRET not in r.text
    assert _events(db_session, queued) == []


def test_an_unknown_proposal_is_a_404(db_session, queued):
    r = client.post(URL, json={"proposal_id": str(uuid4())}, headers=EXT)
    assert r.status_code == 404 and r.json()["detail"] == "Proposal not found"
    assert db_session.query(ConsentEvent).count() == 0


@pytest.mark.parametrize("body", [
    {}, {"proposal_id": "not-a-uuid"},
    {"proposal_id": "00000000-0000-0000-0000-000000000000", "password": SECRET},
])
def test_a_bad_body_is_a_422_that_echoes_nothing(db_session, queued, body):
    r = client.post(URL, json=body, headers=EXT)
    assert r.status_code == 422
    assert r.json() == {"detail": "The job-site login request is invalid."}
    assert SECRET not in r.text


def test_every_hand_off_is_audited(db_session, queued):
    for _ in range(2):
        assert _post(queued).status_code == 200
    assert len(_events(db_session, queued)) == 2


def test_the_hand_off_never_logs_or_persists_the_password(db_session, queued, caplog):
    with caplog.at_level(logging.DEBUG):
        r = _post(queued)
    assert r.status_code == 200 and r.json()["password"] == SECRET
    assert caplog.records  # HTTP request metadata confirms capture is active.
    assert SECRET not in caplog.text
    for table in Base.metadata.sorted_tables:
        assert SECRET not in repr(db_session.execute(select(table)).all()), table.name
