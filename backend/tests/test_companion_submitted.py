"""POST /api/proposals/{id}/companion-submitted: the Companion records a Submit the USER pressed.

It never clicks anything. `submitted` is terminal, so there is no undo here; the panel's
8-second "Marking applied" delay is the only take-back (plan Adjustment 3).
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models.application import Application
from app.models.application_proposal import ApplicationProposal
from app.models.consent_event import ConsentEvent
from app.schemas.auto_apply import AutoApplySettings
from app.services import auto_apply_settings
from app.services import proposals as svc
from tests.test_proposal_state_machine import _mk_proposal

client = TestClient(app)
EXT = {"Origin": "chrome-extension://abcdefghijklmnopabcdefghijklmnop"}
BODY = {"confirmation": {"host": "acme.example", "path": "/apply/done", "text": "Thank you for applying"}}


@pytest.fixture(autouse=True)
def _settings_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "settings_dir", tmp_path)


@pytest.fixture
def queued(db_session):
    prop = _mk_proposal(db_session)
    prop.status = "accepted"
    db_session.commit()
    return prop


def _post(prop, body=BODY, headers=EXT):
    return client.post(f"/api/proposals/{prop.id}/companion-submitted", json=body, headers=headers)


def _untouched(db_session, prop):
    db_session.expire_all()
    row = db_session.get(ApplicationProposal, prop.id)
    assert row.status == "accepted"
    assert not row.evidence_json
    assert row.cap_reserved_at is None
    assert db_session.query(ConsentEvent).count() == 0
    assert db_session.get(Application, row.application_id).status == "draft"


def test_a_confirmation_after_the_users_submit_records_the_job_applied(db_session, queued):
    r = _post(queued)
    assert r.status_code == 200 and r.json()["status"] == "submitted"

    db_session.expire_all()
    prop = db_session.get(ApplicationProposal, queued.id)
    assert db_session.get(Application, prop.application_id).status == "applied"
    assert prop.cap_reserved_at is not None  # reserved once, at the approve step

    events = db_session.query(ConsentEvent).filter_by(proposal_id=prop.id).order_by(ConsentEvent.created_at).all()
    assert sorted(e.action for e in events) == ["approved", "submitted"]
    assert {e.channel for e in events} == {"companion"}

    kinds = [item["kind"] for item in prop.evidence_json]
    assert kinds == ["final_review", "submission_receipt"]
    receipt = prop.evidence_json[1]
    assert (receipt["host"], receipt["path"], receipt["text"]) == (
        "acme.example", "/apply/done", "Thank you for applying")
    # no file behind either row: the Agent inbox draws only rows whose path is under evidence/
    assert prop.evidence_json[0]["path"] == ""
    # the approved event carries the final review, the submitted one both rows
    approved = next(e for e in events if e.action == "approved")
    assert [i["kind"] for i in approved.evidence_manifest_json] == ["final_review"]


def test_only_the_companion_may_record_it(db_session, queued):
    for headers in (
        {},
        {"X-Maestro-CS-Origin": "mcp"},
        {"Origin": "http://localhost:3000"},
        {"Origin": "chrome-extension://someoneelseidsomeoneelseid"},
    ):
        assert _post(queued, headers=headers).status_code == 403
    _untouched(db_session, queued)


def test_an_unknown_proposal_is_a_404(db_session):
    r = client.post("/api/proposals/00000000-0000-4000-8000-000000000000/companion-submitted",
                    json=BODY, headers=EXT)
    assert r.status_code == 404


def test_it_respects_the_cap(db_session, queued):
    auto_apply_settings.set_settings(AutoApplySettings(max_submissions_per_day=1), db_session)
    other = _mk_proposal(db_session)
    other.cap_reserved_at = datetime.now(UTC)
    db_session.commit()
    r = _post(queued)
    assert r.status_code == 409 and "cap" in r.json()["detail"]
    _untouched(db_session, queued)


def test_it_respects_the_skip_list_set_after_queueing(db_session, queued):
    auto_apply_settings.set_settings(AutoApplySettings(company_blocklist=["acme"]), db_session)
    r = _post(queued)
    assert r.status_code == 409 and r.json()["detail"] == svc.COMPANY_BLOCKED
    _untouched(db_session, queued)


@pytest.mark.parametrize("status", ["submitted", "rejected", "expired"])
def test_a_closed_proposal_is_not_reopened(db_session, queued, status):
    queued.status = status
    db_session.commit()
    assert _post(queued).status_code == 409
    db_session.expire_all()
    assert db_session.get(ApplicationProposal, queued.id).status == status
    assert not db_session.get(ApplicationProposal, queued.id).evidence_json


def test_a_job_the_user_already_marked_applied_is_refused(db_session, queued):
    db_session.get(Application, queued.application_id).status = "applied"
    db_session.commit()
    r = _post(queued)
    assert r.status_code == 409 and "already applied" in r.json()["detail"]
    db_session.expire_all()
    assert db_session.get(ApplicationProposal, queued.id).status == "accepted"
    assert db_session.query(ConsentEvent).count() == 0


def test_a_failed_submit_step_leaves_nothing_approved(db_session, queued, monkeypatch):
    real = svc.transition

    def flaky(session, prop, new_status, **kw):
        if new_status == "submitted":
            raise svc.TransitionError("boom")
        return real(session, prop, new_status, **kw)

    monkeypatch.setattr(svc, "transition", flaky)
    r = _post(queued)
    assert r.status_code == 409 and r.json()["detail"] == "boom"
    _untouched(db_session, queued)


@pytest.mark.parametrize("confirmation", [
    {"host": "acme.example", "path": "/apply/done", "text": "x" * 301},
    {"host": "h" * 256, "path": "/apply/done", "text": "ok"},
    {"host": "acme.example", "path": "/" + "p" * 2048, "text": "ok"},
    {"host": "acme.example", "text": "ok"},
    {"path": "/apply/done", "text": "ok"},
    {"host": "acme.example", "path": "/apply/done", "text": "ok", "html": "<p>page</p>"},
])
def test_the_confirmation_is_bounded(db_session, queued, confirmation):
    assert _post(queued, {"confirmation": confirmation}).status_code == 422
    _untouched(db_session, queued)


def test_the_queueing_patch_may_name_the_companion_channel(db_session):
    """Task 20a queues from the Job step with this channel; the schema has to let it through."""
    prop = _mk_proposal(db_session)
    r = client.patch(f"/api/proposals/{prop.id}", headers=EXT,
                     json={"status": "accepted", "consent": {"channel": "companion"}})
    assert r.status_code == 200 and r.json()["status"] == "accepted"


def test_a_job_owned_by_the_other_copy_is_refused_and_untouched(db_session, queued):
    from app.models.job import Job
    from app.services.sync import status

    db_session.get(Job, queued.job_id).owner_machine = "other-machine"
    db_session.commit()
    status.create_key()
    r = _post(queued)
    assert r.status_code == 409 and r.json()["owner"] == "bot"
    _untouched(db_session, queued)


def test_the_companion_channel_is_a_consent_channel():
    assert "companion" in svc.CONSENT_CHANNELS
