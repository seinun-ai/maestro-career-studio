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


def _recorded_as_applied_yourself(db_session, prop):
    """The user's own Submit is always recorded; what the cap or skip list stopped is the Companion starting it."""
    db_session.expire_all()
    row = db_session.get(ApplicationProposal, prop.id)
    app_row = db_session.get(Application, row.application_id)
    assert app_row.status == "applied" and app_row.applied_at is not None
    assert (row.status, row.reason) == ("rejected", svc.APPLIED_MANUALLY)
    assert row.cap_reserved_at is None  # no slot taken
    assert [i["kind"] for i in row.evidence_json] == ["submission_receipt"]
    assert row.evidence_json[0]["path"] == "/apply/done"
    events = db_session.query(ConsentEvent).filter_by(proposal_id=row.id).all()
    assert [e.action for e in events] == ["rejected"]  # never an "approved" or "submitted" claim


def test_a_full_day_still_records_the_users_submit_as_applied_yourself(db_session, queued):
    auto_apply_settings.set_settings(AutoApplySettings(max_submissions_per_day=1), db_session)
    other = _mk_proposal(db_session)
    other.cap_reserved_at = datetime.now(UTC)
    db_session.commit()
    r = _post(queued)
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    _recorded_as_applied_yourself(db_session, queued)


def test_a_company_skipped_after_queueing_still_records_the_users_submit(db_session, queued):
    auto_apply_settings.set_settings(AutoApplySettings(company_blocklist=["acme"]), db_session)
    r = _post(queued)
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    _recorded_as_applied_yourself(db_session, queued)


def test_the_fallback_without_a_linked_application_still_closes_the_proposal(db_session):
    prop = _mk_proposal(db_session, with_app=False)
    prop.status = "accepted"
    db_session.commit()
    auto_apply_settings.set_settings(AutoApplySettings(company_blocklist=["acme"]), db_session)
    r = _post(prop)
    assert r.status_code == 200
    db_session.expire_all()
    row = db_session.get(ApplicationProposal, prop.id)
    assert (row.status, row.reason) == ("rejected", svc.APPLIED_MANUALLY)


@pytest.mark.parametrize("status", ["submitted", "rejected", "expired"])
def test_a_closed_proposal_is_not_reopened(db_session, queued, status):
    queued.status = status
    db_session.commit()
    assert _post(queued).status_code == 409
    db_session.expire_all()
    assert db_session.get(ApplicationProposal, queued.id).status == status
    assert not db_session.get(ApplicationProposal, queued.id).evidence_json


@pytest.mark.parametrize("status", ["pending_review", "needs_human"])
def test_only_a_queued_job_is_recorded(db_session, queued, status):
    queued.status = status
    db_session.commit()
    r = _post(queued)
    assert r.status_code == 409 and "queued" in r.json()["detail"]
    db_session.expire_all()
    row = db_session.get(ApplicationProposal, queued.id)
    assert row.status == status and not row.evidence_json and row.cap_reserved_at is None
    assert db_session.query(ConsentEvent).count() == 0
    assert db_session.get(Application, row.application_id).status == "draft"


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


def _sync_on(db_session, queued, **job_fields):
    from app.models.job import Job
    from app.services.sync import status

    job = db_session.get(Job, queued.job_id)
    for name, value in job_fields.items():
        setattr(job, name, value)
    db_session.commit()
    status.create_key()


def test_a_job_owned_by_the_other_copy_is_refused_and_untouched(db_session, queued):
    _sync_on(db_session, queued, owner_machine="other-machine")
    r = _post(queued)
    assert r.status_code == 409 and r.json()["owner"] == "bot"
    _untouched(db_session, queued)


def test_a_job_offered_to_the_always_on_copy_is_refused_and_untouched(db_session, queued):
    """Task 20a claims the job (Keep it here) before a run starts; until then the other copy may take it."""
    _sync_on(db_session, queued, handover="offered")
    r = _post(queued)
    assert r.status_code == 409
    _untouched(db_session, queued)


def test_an_offered_job_is_refused_even_when_the_cap_is_full(db_session, queued):
    """Ownership is checked before the fallback, which would otherwise write the application."""
    _sync_on(db_session, queued, handover="offered")
    auto_apply_settings.set_settings(AutoApplySettings(company_blocklist=["acme"]), db_session)
    assert _post(queued).status_code == 409
    _untouched(db_session, queued)


# The channel says "the Companion asked", so it cannot be named from anywhere else.
@pytest.mark.parametrize("headers", [{}, {"Origin": "http://localhost:3000"}])
def test_the_companion_channel_is_refused_from_anywhere_else(db_session, headers):
    prop = _mk_proposal(db_session)
    r = client.patch(f"/api/proposals/{prop.id}", headers=headers,
                     json={"status": "accepted", "consent": {"channel": "companion"}})
    assert r.status_code == 403
    db_session.expire_all()
    assert db_session.get(ApplicationProposal, prop.id).status == "pending_review"
    assert db_session.query(ConsentEvent).count() == 0


@pytest.mark.parametrize("body", [
    {"status": "approved", "consent": {"channel": "companion"}},
    {"status": "submitted", "attested": True, "consent": {"channel": "companion"}},
])
def test_approving_and_submitting_with_the_companion_channel_go_through_the_endpoint(db_session, queued, body):
    r = client.patch(f"/api/proposals/{queued.id}", headers=EXT, json=body)
    assert r.status_code == 409 and "companion-submitted" in r.json()["detail"]
    _untouched(db_session, queued)


def test_bulk_changes_refuse_the_companion_channel(db_session, queued):
    r = client.post("/api/proposals/bulk-transition", headers=EXT, json={
        "ids": [str(queued.id)], "status": "rejected", "consent": {"channel": "companion"}})
    assert r.status_code == 422
    _untouched(db_session, queued)
