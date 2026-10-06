"""The agent's job-site login hand-off: full automation only, MCP only, audited."""

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
MCP = {"X-Maestro-CS-Origin": "mcp", "X-Maestro-CS-Origin-Detail": "claude-ai"}
SECRET = "pw-one-long"


@pytest.fixture(autouse=True)
def _settings_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    job_site_login.write("ada@example.com", SECRET)


def _on(db_session, on=True):
    auto_apply_settings.set_settings(AutoApplySettings(full_automation=on), db_session)


def _proposal(db_session, status="accepted"):
    # The existing fixture accepts status but does not pass it to create_proposal.
    prop = _mk_proposal(db_session)
    prop.status = status
    db_session.commit()
    return prop


def _post(prop, headers=MCP):
    return client.post(f"/api/proposals/{prop.id}/job-site-login", headers=headers)


def _no_audit(db_session):
    assert db_session.query(ConsentEvent).count() == 0


def test_refused_while_full_automation_is_off(db_session):
    _on(db_session, False)
    response = _post(_proposal(db_session))
    assert response.status_code == 409
    assert "full automation" in response.json()["detail"]
    assert SECRET not in response.text
    _no_audit(db_session)


@pytest.mark.parametrize("headers", [
    {},
    {"X-Maestro-CS-Origin-Detail": "claude-ai"},
    {"X-Maestro-CS-Origin": "frontend"},
    {"X-Maestro-CS-Origin": "extension"},
    {"X-Maestro-CS-Origin": "auto"},
])
def test_refused_without_the_mcp_origin(db_session, headers):
    _on(db_session)
    response = _post(_proposal(db_session), headers=headers)
    assert response.status_code == 403
    assert SECRET not in response.text
    _no_audit(db_session)


@pytest.mark.parametrize("status", ["accepted", "approved"])
def test_handed_over_and_audited_without_the_value(db_session, status):
    _on(db_session)
    prop = _proposal(db_session, status)
    response = _post(prop)
    assert response.status_code == 200
    assert response.json() == {"email": "ada@example.com", "password": SECRET}
    event = db_session.query(ConsentEvent).filter_by(proposal_id=prop.id).one()
    assert (event.action, event.channel, event.note) == ("login_shared", "mcp", "claude-ai")
    assert event.created_at is not None
    assert event.evidence_manifest_json is None
    assert SECRET not in (event.note or "") + str(event.evidence_manifest_json)
    db_session.refresh(prop)
    assert (prop.status, prop.cap_reserved_at) == (status, None)


@pytest.mark.parametrize("status", [
    "pending_review", "needs_decision", "needs_human", "submitted",
    "submission_uncertain", "rejected", "expired",
])
def test_refused_for_a_closed_proposal(db_session, status):
    _on(db_session)
    response = _post(_proposal(db_session, status))
    assert response.status_code == 409
    assert SECRET not in response.text
    _no_audit(db_session)


def test_404_when_no_password_is_set(db_session):
    _on(db_session)
    job_site_login.clear()
    assert _post(_proposal(db_session)).status_code == 404
    _no_audit(db_session)


@pytest.mark.parametrize(("email", "password"), [
    (None, SECRET), ("ada@example.com", None), ("", SECRET), ("ada@example.com", ""),
])
def test_an_incomplete_login_is_refused_without_an_audit(db_session, email, password):
    _on(db_session)
    job_site_login.clear()
    job_site_login.write(email, password)
    response = _post(_proposal(db_session))
    assert response.status_code == 404
    assert SECRET not in response.text
    _no_audit(db_session)


def test_unknown_proposal_is_refused_without_an_audit(db_session):
    _on(db_session)
    response = client.post(f"/api/proposals/{uuid4()}/job-site-login", headers=MCP)
    assert response.status_code == 404
    assert response.json()["detail"] == "Proposal not found"
    _no_audit(db_session)


def test_each_hand_off_is_audited_even_for_an_unnamed_client(db_session):
    _on(db_session)
    prop = _proposal(db_session)
    for _ in range(2):
        assert _post(prop, {"X-Maestro-CS-Origin": "mcp"}).status_code == 200
    events = db_session.query(ConsentEvent).filter_by(proposal_id=prop.id).all()
    assert len(events) == 2
    assert all(event.note is None and event.action == "login_shared" for event in events)


def test_handoff_never_logs_or_persists_the_password(db_session, caplog):
    _on(db_session)
    prop = _proposal(db_session)
    with caplog.at_level(logging.DEBUG):
        response = _post(prop)
    assert response.status_code == 200
    assert response.json()["password"] == SECRET
    assert caplog.records  # HTTP request metadata confirms capture is active.
    assert SECRET not in caplog.text
    for table in Base.metadata.sorted_tables:
        assert SECRET not in repr(db_session.execute(select(table)).all()), table.name
