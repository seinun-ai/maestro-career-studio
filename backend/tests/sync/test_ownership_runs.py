"""Task 13: run location and refused requests over browser HTTP."""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import get_db
from app.main import app
from app.models.agent_run import AgentRun
from app.models.sync import SyncRequest
from app.models.types import utcnow


@pytest.fixture
def client(db_session):
    def override():
        yield db_session

    app.dependency_overrides[get_db] = override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _run(db, machine):
    row = AgentRun(automation="job-hunt", outcome="ok", machine=machine,
                   counts={}, digest="", job_ids=[])
    db.add(row)
    db.commit()
    return row


def test_bot_run_with_no_jobs_has_a_location_over_http(client, db_session, sync_on):
    _run(db_session, "always-on-copy")
    response = client.get("/api/agent-runs/latest")
    assert response.status_code == 200
    assert response.json()["items"][0]["on_bot"] is True


def test_local_run_has_no_bot_mark(client, db_session, sync_on):
    _run(db_session, None)
    response = client.get("/api/agent-runs/latest")
    assert response.status_code == 200
    assert response.json()["items"][0]["on_bot"] is False


def test_only_local_refusals_are_visible_without_request_payloads(client, db_session, sync_on):
    row = SyncRequest(kind="take_over", payload_json={"notes": "Private note"},
                      origin="local", status="refused", reason="Your bot is applying to this one; try again after its run.",
                      answered_at=utcnow())
    db_session.add_all([row, SyncRequest(kind="take_over", payload_json={},
                                        origin="peer", status="refused", reason="Peer only")])
    db_session.commit()
    response = client.get("/api/agent-runs/refused-requests")
    assert response.status_code == 200
    assert response.json() == [{"id": str(row.id), "job_id": None, "reason": row.reason,
                                "answered_at": row.answered_at.isoformat().replace("+00:00", "Z")}]


def test_sync_off_hides_stored_bot_marks_and_refusals(client, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sync_key_file", tmp_path / "absent-key")
    _run(db_session, "always-on-copy")
    db_session.add(SyncRequest(kind="take_over", payload_json={}, origin="local",
                               status="refused", reason="Old refusal"))
    db_session.commit()
    assert client.get("/api/agent-runs/latest").json()["items"][0]["on_bot"] is False
    assert client.get("/api/agent-runs/refused-requests").json() == []


@pytest.mark.parametrize("reason", ["Private note", "cannot go secret-value -> accepted", None])
def test_unknown_refusal_text_never_reaches_browser(client, db_session, sync_on, reason):
    db_session.add(SyncRequest(kind="take_over", payload_json={"notes": "Private note"},
                               origin="local", status="refused", reason=reason))
    db_session.commit()
    response = client.get("/api/agent-runs/refused-requests")
    assert response.status_code == 200
    assert response.json()[0]["reason"] == "Maestro couldn't apply this request."
    assert "payload_json" not in response.json()[0]


def test_a_fixed_state_machine_refusal_keeps_its_reason(client, db_session, sync_on):
    reason = "This proposal's status is Applied, so it can't be changed that way."
    db_session.add(SyncRequest(kind="proposal_transition", payload_json={},
                               origin="local", status="refused", reason=reason))
    db_session.commit()
    response = client.get("/api/agent-runs/refused-requests")
    assert response.status_code == 200 and response.json()[0]["reason"] == reason
