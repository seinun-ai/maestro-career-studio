from datetime import UTC, datetime, timedelta
import pytest

from app.models.application import Application
from app.models.consent_event import ConsentEvent
from app.models.job import Job
from app.services import proposals as svc
from tests.test_proposals_models import _mk_job


def _mk_proposal(db_session, status="pending_review", with_app=True, **kw):
    job = _mk_job(db_session, source="agent", company=kw.pop("company", "Acme"))
    app_row = None
    if with_app:
        app_row = Application(job_id=job.id, base_resume="hybrid", source="agent", status="draft")
        db_session.add(app_row)
        db_session.flush()
    return svc.create_proposal(
        db_session, job_id=job.id,
        application_id=app_row.id if app_row else None,
        fit={"chosen_base": "hybrid", "decided_by": "auto"}, plan={}, **kw)


def _final_review_evidence():
    return [{
        "step": 99, "label": "final review", "path": "evidence/fr.png",
        "sha256": "fr", "kind": "final_review",
    }]


def _receipt_evidence():
    return [{
        "step": 100, "label": "receipt", "path": "evidence/rcpt.png",
        "sha256": "rc", "kind": "submission_receipt",
    }]


def test_approve_requires_consent(db_session):
    prop = _mk_proposal(db_session)
    prop.evidence_json = _final_review_evidence()
    with pytest.raises(svc.TransitionError):
        svc.transition(db_session, prop, "approved", consent=None)
    svc.transition(db_session, prop, "approved",
                   consent={"channel": "chat", "note": "yes"})
    assert prop.status == "approved"
    assert db_session.query(ConsentEvent).filter_by(
        proposal_id=prop.id, action="approved").count() == 1


def test_submit_requires_approved_and_evidence(db_session):
    prop = _mk_proposal(db_session)
    with pytest.raises(svc.TransitionError):   # not approved yet
        svc.transition(db_session, prop, "submitted")
    prop.evidence_json = _final_review_evidence()
    svc.transition(db_session, prop, "approved", consent={"channel": "chat"})
    with pytest.raises(svc.TransitionError):   # approved but no receipt
        svc.transition(db_session, prop, "submitted")
    prop.evidence_json = _final_review_evidence() + _receipt_evidence()
    svc.transition(db_session, prop, "submitted")
    assert prop.status == "submitted"


def test_submit_marks_application_applied_and_stamps_applied_at(db_session):
    prop = _mk_proposal(db_session)
    prop.evidence_json = _final_review_evidence()
    svc.transition(db_session, prop, "approved", consent={"channel": "chat"})
    prop.evidence_json = _final_review_evidence() + _receipt_evidence()
    svc.transition(db_session, prop, "submitted")
    app_row = db_session.get(Application, prop.application_id)
    assert app_row.status == "applied"
    assert app_row.applied_at is not None


def test_illegal_transitions_rejected(db_session):
    prop = _mk_proposal(db_session)
    svc.transition(db_session, prop, "rejected",
                   consent={"channel": "chat", "note": "not a fit"}, reason="not a fit")
    with pytest.raises(svc.TransitionError):   # rejected is terminal
        svc.transition(db_session, prop, "approved", consent={"channel": "chat"})


def test_needs_human_can_return_to_approved(db_session):
    prop = _mk_proposal(db_session)
    prop.evidence_json = _final_review_evidence()
    svc.transition(db_session, prop, "approved", consent={"channel": "chat"})
    svc.transition(db_session, prop, "needs_human", reason="captcha wall")
    # Legacy path: fresh consent from needs_human -> approved (no resume required)
    prop.evidence_json = _final_review_evidence()
    svc.transition(db_session, prop, "approved", consent={"channel": "chat", "note": "retry"})
    assert prop.status == "approved"


def test_lazy_expiry(db_session):
    prop = _mk_proposal(db_session)
    prop.expires_at = datetime.now(UTC) - timedelta(days=1)
    db_session.commit()
    svc.expire_stale(db_session)
    db_session.refresh(prop)
    assert prop.status == "expired"


def test_pending_review_can_go_needs_human(db_session):
    prop = _mk_proposal(db_session)
    svc.transition(db_session, prop, "needs_human", reason="captcha")
    assert prop.status == "needs_human"


def test_resume_proposal_needs_human_to_pending_review(db_session):
    prop = _mk_proposal(db_session)
    svc.transition(db_session, prop, "needs_human", reason="login wall")
    svc.resume_proposal(db_session, prop)
    assert prop.status == "pending_review"


def test_resume_proposal_rejects_submission_uncertain(db_session):
    prop = _mk_proposal(db_session)
    prop.evidence_json = _final_review_evidence()
    svc.transition(db_session, prop, "approved", consent={"channel": "chat"})
    svc.transition(db_session, prop, "submission_uncertain", reason="submission_uncertain")
    with pytest.raises(svc.TransitionError):
        svc.resume_proposal(db_session, prop)


def test_request_decision_idempotent(db_session):
    prop = _mk_proposal(db_session, with_app=False)
    svc.request_decision(db_session, prop, reason="ambiguous base")
    assert prop.status == "needs_decision"
    svc.request_decision(db_session, prop, reason="ambiguous base again")
    assert prop.status == "needs_decision"
    assert prop.reason == "ambiguous base again"


def test_approve_requires_final_review_evidence(db_session):
    prop = _mk_proposal(db_session)
    with pytest.raises(svc.TransitionError, match="final_review"):
        svc.transition(db_session, prop, "approved", consent={"channel": "chat"})
    prop.evidence_json = _final_review_evidence()
    svc.transition(db_session, prop, "approved", consent={"channel": "chat"})
    assert prop.status == "approved"
    assert prop.cap_reserved_at is not None


def test_submit_requires_submission_receipt(db_session):
    prop = _mk_proposal(db_session)
    prop.evidence_json = _final_review_evidence()
    svc.transition(db_session, prop, "approved", consent={"channel": "chat"})
    with pytest.raises(svc.TransitionError, match="submission_receipt"):
        svc.transition(db_session, prop, "submitted")
    prop.evidence_json = _final_review_evidence() + _receipt_evidence()
    svc.transition(db_session, prop, "submitted")
    assert prop.status == "submitted"
    assert prop.cap_reserved_at is not None


def test_resume_releases_cap_reservation(db_session):
    prop = _mk_proposal(db_session)
    prop.evidence_json = _final_review_evidence()
    svc.transition(db_session, prop, "approved", consent={"channel": "chat"})
    assert prop.cap_reserved_at is not None
    svc.transition(db_session, prop, "needs_human", reason="interrupted")
    svc.resume_proposal(db_session, prop)
    assert prop.status == "pending_review"
    assert prop.cap_reserved_at is None


def test_rejection_releases_cap_reservation(db_session):
    prop = _mk_proposal(db_session)
    prop.evidence_json = _final_review_evidence()
    svc.transition(db_session, prop, "approved", consent={"channel": "chat"})
    svc.transition(db_session, prop, "rejected", consent={"channel": "chat"}, reason="no")
    assert prop.cap_reserved_at is None


def test_submission_uncertain_keeps_cap_consumed(db_session):
    prop = _mk_proposal(db_session)
    prop.evidence_json = _final_review_evidence()
    svc.transition(db_session, prop, "approved", consent={"channel": "chat"})
    reserved_at = prop.cap_reserved_at
    svc.transition(db_session, prop, "submission_uncertain", reason="submission_uncertain")
    assert prop.status == "submission_uncertain"
    assert prop.cap_reserved_at == reserved_at


def test_record_decision_auto_links_newest_matching_application(db_session):
    prop = _mk_proposal(db_session, with_app=False)
    svc.request_decision(db_session, prop, reason="pick base")
    older = Application(job_id=prop.job_id, base_resume="hybrid", source="agent", status="draft")
    newer = Application(job_id=prop.job_id, base_resume="hybrid", source="agent", status="draft")
    db_session.add_all([older, newer])
    db_session.flush()
    older.created_at = datetime.now(UTC) - timedelta(hours=1)
    newer.created_at = datetime.now(UTC)
    db_session.commit()
    svc.record_decision(db_session, prop, fit={"chosen_base": "hybrid"})
    assert prop.status == "pending_review"
    assert prop.application_id == newer.id


def test_pending_review_to_accepted_requires_consent(db_session):
    prop = _mk_proposal(db_session)
    with pytest.raises(svc.TransitionError):
        svc.transition(db_session, prop, "accepted")


def test_accept_writes_consent_event_and_reserves_no_cap(db_session):
    prop = _mk_proposal(db_session)
    svc.transition(db_session, prop, "accepted", consent={"channel": "frontend"})
    assert prop.status == "accepted"
    assert prop.cap_reserved_at is None  # triage acceptance is pre-consent
    assert db_session.query(ConsentEvent).filter_by(
        proposal_id=prop.id, action="accepted").count() == 1


def test_accepted_allows_approve_reject_and_needs_human(db_session):
    a = _mk_proposal(db_session)
    svc.transition(db_session, a, "accepted", consent={"channel": "mcp"})
    a.evidence_json = _final_review_evidence()
    svc.transition(db_session, a, "approved", consent={"channel": "chat"})
    assert a.status == "approved"

    b = _mk_proposal(db_session)
    svc.transition(db_session, b, "accepted", consent={"channel": "mcp"})
    svc.transition(db_session, b, "rejected",
                   consent={"channel": "frontend"}, reason="duplicate")
    assert b.status == "rejected"

    c = _mk_proposal(db_session)
    svc.transition(db_session, c, "accepted", consent={"channel": "mcp"})
    svc.transition(db_session, c, "needs_human", reason="login wall")
    assert c.status == "needs_human"


def test_accepted_is_excluded_from_lazy_expiry(db_session):
    prop = _mk_proposal(db_session)
    svc.transition(db_session, prop, "accepted", consent={"channel": "mcp"})
    prop.expires_at = datetime.now(UTC) - timedelta(days=1)
    db_session.commit()
    assert svc.expire_stale(db_session) == 0
    db_session.refresh(prop)
    assert prop.status == "accepted"


def _approve(db_session, prop):
    prop.evidence_json = _final_review_evidence()
    svc.transition(db_session, prop, "approved", consent={"channel": "chat"})


def test_attested_submit_requires_consent_channel(db_session):
    prop = _mk_proposal(db_session)
    _approve(db_session, prop)
    with pytest.raises(svc.TransitionError, match="valid channel"):
        svc.transition(db_session, prop, "submitted", attested=True)


def test_attested_submit_writes_consent_event_and_flips_application(db_session):
    prop = _mk_proposal(db_session)
    _approve(db_session, prop)
    svc.transition(db_session, prop, "submitted", attested=True,
                   consent={"channel": "chat", "note": "user says they submitted it"})
    assert prop.status == "submitted"
    app_row = db_session.get(Application, prop.application_id)
    assert app_row.status == "applied"
    assert app_row.applied_at is not None
    assert db_session.query(ConsentEvent).filter_by(
        proposal_id=prop.id, action="submitted").count() == 1


def test_receipt_submit_writes_no_submitted_consent_event(db_session):
    prop = _mk_proposal(db_session)
    _approve(db_session, prop)
    prop.evidence_json = _final_review_evidence() + _receipt_evidence()
    svc.transition(db_session, prop, "submitted")
    assert db_session.query(ConsentEvent).filter_by(
        proposal_id=prop.id, action="submitted").count() == 0


def test_uncertain_to_submitted_requires_attestation(db_session):
    prop = _mk_proposal(db_session)
    _approve(db_session, prop)
    svc.transition(db_session, prop, "submission_uncertain", reason="submission_uncertain")
    # Even WITH receipt-grade evidence, the uncertain edge demands attestation.
    with pytest.raises(svc.TransitionError, match="attestation"):
        svc.transition(db_session, prop, "submitted", consent={"channel": "chat"})
    svc.transition(db_session, prop, "submitted", attested=True,
                   consent={"channel": "chat", "note": "confirmation email arrived"})
    assert prop.status == "submitted"


def test_approve_refused_when_linked_application_already_applied(db_session):
    # G7: user applied manually (web StatusChip or on-site) while the proposal
    # sat queued — the agent must never consent-to-submit over it again.
    prop = _mk_proposal(db_session)
    app_row = db_session.get(Application, prop.application_id)
    app_row.status = "applied"
    db_session.commit()
    prop.evidence_json = _final_review_evidence()
    with pytest.raises(svc.TransitionError, match="already applied"):
        svc.transition(db_session, prop, "approved", consent={"channel": "chat"})


def test_approve_fine_when_linked_application_still_draft(db_session):
    prop = _mk_proposal(db_session)
    prop.evidence_json = _final_review_evidence()
    svc.transition(db_session, prop, "approved", consent={"channel": "chat"})
    assert prop.status == "approved"


def test_final_review_flags_duplicate_submitted_company_title(db_session):
    # G11 tier 2: before the user consents, final review must say loudly that
    # a same-company+title proposal was already submitted.
    first = _mk_proposal(db_session)
    job1 = db_session.get(Job, first.job_id)
    job1.title = "Data Scientist"
    db_session.commit()
    _approve(db_session, first)
    first.evidence_json = _final_review_evidence() + _receipt_evidence()
    svc.transition(db_session, first, "submitted")

    second = _mk_proposal(db_session)  # same company factory default ("Acme")
    job2 = db_session.get(Job, second.job_id)
    job2.title = "data scientist"  # case-insensitive match
    db_session.commit()
    review = svc.get_final_review(db_session, second)
    assert review["duplicate_submitted"] is True

    third = _mk_proposal(db_session)
    job3 = db_session.get(Job, third.job_id)
    job3.title = "Analytics Engineer"
    db_session.commit()
    assert svc.get_final_review(db_session, third)["duplicate_submitted"] is False


def test_record_decision_409_when_no_matching_application(db_session):
    prop = _mk_proposal(db_session, with_app=False)
    svc.request_decision(db_session, prop, reason="pick base")
    with pytest.raises(svc.TransitionError, match="no matching application"):
        svc.record_decision(db_session, prop, fit={"chosen_base": "hybrid"})
