"""P1: agent-sourced jobs require an open proposal for execute helpers."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.application import Application
from app.services import proposals as svc
from tests.test_proposals_models import _mk_job

client = TestClient(app)


def _mk_agent_app(db_session, *, with_proposal=False, status="pending_review"):
    job = _mk_job(db_session, source="agent", company="GateCo")
    app_row = Application(job_id=job.id, base_resume="hybrid", source="agent", status="draft")
    db_session.add(app_row)
    db_session.commit()
    prop = None
    if with_proposal:
        prop = svc.create_proposal(
            db_session, job_id=job.id, application_id=app_row.id,
            fit={"chosen_base": "hybrid"}, plan={},
        )
        if status != "pending_review":
            if status == "approved":
                prop.evidence_json = [{
                    "step": 1, "label": "final", "path": "evidence/fr.png",
                    "sha256": "x", "kind": "final_review",
                }]
                svc.transition(db_session, prop, "approved", consent={"channel": "chat"})
            else:
                # Direct status for gate-status tests without full transition path
                prop.status = status
                db_session.commit()
    return job, app_row, prop


def test_require_open_proposal_refuses_agent_job_without_proposal(db_session):
    _, app_row, _ = _mk_agent_app(db_session, with_proposal=False)
    with pytest.raises(svc.TransitionError, match="no open proposal for this job"):
        svc.require_open_proposal_for_application(db_session, app_row.id, op="prepare")


def test_require_open_proposal_allows_user_job_without_proposal(db_session):
    job = _mk_job(db_session, source="user", company="ManualCo")
    app_row = Application(job_id=job.id, base_resume="hybrid", source="user", status="draft")
    db_session.add(app_row)
    db_session.commit()
    assert svc.require_open_proposal_for_application(db_session, app_row.id, op="prepare") is None


def test_require_open_proposal_allows_pending_review(db_session):
    _, app_row, prop = _mk_agent_app(db_session, with_proposal=True)
    found = svc.require_open_proposal_for_application(db_session, app_row.id, op="prepare")
    assert found is not None and found.id == prop.id


def test_require_open_proposal_mark_submitted_requires_approved(db_session):
    _, app_row, _ = _mk_agent_app(db_session, with_proposal=True, status="pending_review")
    with pytest.raises(svc.TransitionError, match="no open proposal for this job"):
        svc.require_open_proposal_for_application(db_session, app_row.id, op="mark_submitted")


def test_assert_open_proposal_endpoint_409_without_proposal(db_session):
    _, app_row, _ = _mk_agent_app(db_session, with_proposal=False)
    r = client.post(f"/api/applications/{app_row.id}/assert-open-proposal", json={"op": "prepare"})
    assert r.status_code == 409
    assert "no open proposal for this job" in r.json()["detail"]


def test_assert_open_proposal_endpoint_ok_with_proposal(db_session):
    _, app_row, prop = _mk_agent_app(db_session, with_proposal=True)
    r = client.post(f"/api/applications/{app_row.id}/assert-open-proposal", json={"op": "prepare"})
    assert r.status_code == 200
    assert r.json()["proposal_id"] == str(prop.id)
