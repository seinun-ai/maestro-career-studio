from datetime import UTC, datetime, timedelta
import pytest

from app.config import settings
from app.models.application import Application
from app.models.base_resume import BaseResume
from app.models.consent_event import ConsentEvent
from app.models.job import Job
from app.services import proposals as svc
from tests.test_proposals_models import _mk_job


@pytest.fixture(autouse=True)
def _settings_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "settings_dir", tmp_path)


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
    with pytest.raises(svc.TransitionError) as refused:   # rejected is terminal
        svc.transition(db_session, prop, "approved", consent={"channel": "chat"})
    # The bulk toast prints this: the Agent inbox's word, never a raw status.
    assert str(refused.value) == (
        "This proposal's status is Skipped, so it can't be changed that way.")


def test_the_refusal_names_the_status_as_its_chip_does():
    """The status words are the Agent inbox's chip labels, one table in two
    languages: `PROPOSAL_STATUS_CHIP` (frontend/components/status-chip.tsx)."""
    import re
    from pathlib import Path

    chip = (Path(__file__).resolve().parents[2] / "frontend" / "components"
            / "status-chip.tsx").read_text(encoding="utf-8")
    needs_you = re.search(r'const NEEDS_YOU = \{\s*label: "([^"]+)"', chip).group(1)
    block = re.search(r"export const PROPOSAL_STATUS_CHIP: Record<.*?> = \{(.*?)\n\};",
                      chip, re.S).group(1)
    web = dict(re.findall(r'(\w+): \{ label: "([^"]+)"', block))
    web.update({key: needs_you for key in re.findall(r"(\w+): NEEDS_YOU", block)})
    assert web == svc.STATUS_CHIP_WORDS
    # Every status the ledger can hold has a word.
    assert set(svc.STATUS_CHIP_WORDS) >= set(svc.ALLOWED) | {"submitted", "rejected", "expired"}


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
    with pytest.raises(svc.TransitionError,
                       match=r"attestation \(the user's, or the agent's in full automation mode\)"):
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


def _country_review(db_session, *, app_base, chosen, job_country="US", **bases):
    for slug, countries in bases.items():
        db_session.add(BaseResume(slug=slug, data_json={}, countries=countries))
    job = _mk_job(db_session, source="agent", country=job_country)
    app_id = None
    if app_base is not None:
        app_row = Application(job_id=job.id, base_resume=app_base, source="agent", status="draft")
        db_session.add(app_row)
        db_session.flush()
        app_id = app_row.id
    prop = svc.create_proposal(db_session, job_id=job.id, application_id=app_id,
                               fit={"chosen_base": chosen}, plan={})
    return svc.get_final_review(db_session, prop)


def test_final_review_reports_base_country_for_the_sent_base(db_session):
    # the application's base wins over a stale fit.chosen_base for another country
    review = _country_review(db_session, app_base="india", chosen="us",
                             india=["IN"], us=["US"])
    assert review["base_country"] == {"job_country": "US", "base": "india", "eligible": False}
    assert review["fit"]["chosen_base"] == "us"


def test_final_review_base_country_eligible_and_free_text_country(db_session):
    review = _country_review(db_session, app_base="us", chosen="india", job_country="United States",
                             india=["IN"], us=["US"])
    assert review["base_country"] == {"job_country": "US", "base": "us", "eligible": True}


def test_final_review_base_country_uses_chosen_base_without_an_application(db_session):
    review = _country_review(db_session, app_base=None, chosen="india", india=["IN"], us=["US"])
    assert review["base_country"] == {"job_country": "US", "base": "india", "eligible": False}


def test_final_review_base_country_in_fallback_is_eligible(db_session):
    review = _country_review(db_session, app_base="india", chosen="india", india=["IN"])
    assert review["base_country"] == {"job_country": "US", "base": "india", "eligible": True}


def test_final_review_base_country_keeps_an_unknown_job_country_as_none(db_session):
    review = _country_review(db_session, app_base="india", chosen=None, job_country="Remote",
                             india=["IN"])
    assert review["base_country"] == {"job_country": None, "base": "india", "eligible": True}


def test_final_review_has_no_base_country_without_a_base(db_session):
    review = _country_review(db_session, app_base=None, chosen=None, india=["IN"])
    assert review["base_country"] is None


def test_record_decision_409_when_no_matching_application(db_session):
    prop = _mk_proposal(db_session, with_app=False)
    svc.request_decision(db_session, prop, reason="pick base")
    with pytest.raises(svc.TransitionError, match="no tailored resume to link"):
        svc.record_decision(db_session, prop, fit={"chosen_base": "hybrid"})


def test_approve_is_refused_past_the_daily_cap(db_session):
    from app.schemas.auto_apply import AutoApplySettings
    from app.services import auto_apply_settings

    auto_apply_settings.set_settings(AutoApplySettings(max_submissions_per_day=1), db_session)
    first, second = _mk_proposal(db_session), _mk_proposal(db_session)
    for prop in (first, second):
        prop.evidence_json = _final_review_evidence()
    svc.transition(db_session, first, "approved", consent={"channel": "chat", "note": "yes"})
    with pytest.raises(svc.TransitionError, match="daily submission cap reached"):
        svc.transition(db_session, second, "approved", consent={"channel": "chat", "note": "yes"})
    assert second.status == "pending_review"


def _full_automation(db_session, on):
    from app.schemas.auto_apply import AutoApplySettings
    from app.services import auto_apply_settings

    auto_apply_settings.set_settings(AutoApplySettings(full_automation=on), db_session)


def _queued_proposal(db_session):
    prop = _mk_proposal(db_session)
    svc.transition(db_session, prop, "accepted", consent={"channel": "chat", "note": "queued"})
    return prop


def test_auto_consent_is_refused_while_full_automation_is_off(db_session):
    _full_automation(db_session, False)
    prop = _queued_proposal(db_session)
    prop.evidence_json = _final_review_evidence()
    with pytest.raises(svc.TransitionError, match="full automation"):
        svc.transition(db_session, prop, "approved", consent={"channel": "auto"})
    assert prop.status == "accepted" and prop.cap_reserved_at is None
    assert db_session.query(ConsentEvent).filter_by(
        proposal_id=prop.id, action="approved").count() == 0


def test_auto_consent_approves_while_on_and_is_recorded_as_auto(db_session):
    _full_automation(db_session, True)
    prop = _queued_proposal(db_session)
    prop.evidence_json = _final_review_evidence()
    svc.transition(db_session, prop, "approved", consent={"channel": "auto", "note": "clean review"})
    event = db_session.query(ConsentEvent).filter_by(
        proposal_id=prop.id, action="approved").one()
    assert (prop.status, event.channel) == ("approved", "auto")
    assert event.action == "approved" and event.note == "clean review"
    assert event.evidence_manifest_json == _final_review_evidence()
    assert prop.cap_reserved_at is not None


@pytest.mark.parametrize("status", ["accepted", "rejected"])
def test_auto_consent_only_approves_or_confirms(db_session, status):
    _full_automation(db_session, True)
    prop = _mk_proposal(db_session)
    with pytest.raises(svc.TransitionError, match="approves a job or confirms"):
        svc.transition(db_session, prop, status, consent={"channel": "auto"})


@pytest.mark.parametrize("status", ["pending_review", "needs_human"])
def test_auto_approval_requires_the_users_queued_lane(db_session, status):
    _full_automation(db_session, True)
    prop = _mk_proposal(db_session)
    if status == "needs_human":
        svc.transition(db_session, prop, "needs_human", reason="login wall")
    prop.evidence_json = _final_review_evidence()
    with pytest.raises(svc.TransitionError, match="user-queued"):
        svc.transition(db_session, prop, "approved", consent={"channel": "auto"})
    assert prop.status == status and prop.cap_reserved_at is None


def _approved_auto(db_session):
    _full_automation(db_session, True)
    prop = _queued_proposal(db_session)
    prop.evidence_json = _final_review_evidence()
    svc.transition(db_session, prop, "approved", consent={"channel": "auto"})
    return prop


def test_in_full_automation_the_agents_word_marks_it_submitted(db_session):
    prop = _approved_auto(db_session)
    svc.transition(db_session, prop, "submitted", attested=True,
                   consent={"channel": "auto", "note": "Confirmation email: application received"})
    events = db_session.query(ConsentEvent).filter_by(proposal_id=prop.id, action="submitted").all()
    assert prop.status == "submitted" and [e.channel for e in events] == ["auto"]
    assert events[0].note == "Confirmation email: application received"
    assert events[0].evidence_manifest_json == _final_review_evidence()
    app_row = db_session.get(Application, prop.application_id)
    assert app_row.status == "applied" and app_row.applied_at is not None


@pytest.mark.parametrize("note", [None, "", "  ", "\t\n", "\u200b", "\ufeff",
                                   "\u200b\ufeff", "---"])
def test_the_agents_word_needs_a_note_naming_the_confirmation(db_session, note):
    prop = _approved_auto(db_session)
    with pytest.raises(svc.TransitionError, match="what confirmed it"):
        svc.transition(db_session, prop, "submitted", attested=True,
                       consent={"channel": "auto", "note": note})
    assert prop.status == "approved"
    assert db_session.query(ConsentEvent).filter_by(proposal_id=prop.id, action="submitted").count() == 0


def test_auto_submission_uncertain_can_be_confirmed_by_the_agents_word(db_session):
    prop = _approved_auto(db_session)
    svc.transition(db_session, prop, "submission_uncertain", reason="submission_uncertain")
    svc.transition(db_session, prop, "submitted", attested=True,
                   consent={"channel": "auto", "note": "Confirmation email received"})
    event = db_session.query(ConsentEvent).filter_by(
        proposal_id=prop.id, action="submitted").one()
    assert prop.status == "submitted" and event.channel == "auto"
    assert event.note == "Confirmation email received"


def test_the_agents_word_is_refused_once_full_automation_is_off(db_session):
    prop = _approved_auto(db_session)
    _full_automation(db_session, False)
    with pytest.raises(svc.TransitionError, match="full automation"):
        svc.transition(db_session, prop, "submitted", attested=True,
                       consent={"channel": "auto", "note": "Confirmation page"})
    assert prop.status == "approved"


@pytest.mark.parametrize("status", ["needs_human", "needs_decision"])
def test_auto_consent_cannot_accompany_other_transitions(db_session, status):
    _full_automation(db_session, True)
    prop = _mk_proposal(db_session)
    with pytest.raises(svc.TransitionError, match="approves a job or confirms"):
        svc.transition(db_session, prop, status, consent={"channel": "auto"})


def test_auto_consent_cannot_submit_without_attestation_even_with_a_receipt(db_session):
    _full_automation(db_session, True)
    prop = _mk_proposal(db_session)
    _approve(db_session, prop)
    prop.evidence_json = _final_review_evidence() + _receipt_evidence()
    with pytest.raises(svc.TransitionError, match="approves a job or confirms"):
        svc.transition(db_session, prop, "submitted",
                       consent={"channel": "auto", "note": "Confirmation page"})


def test_auto_consent_still_requires_final_review_evidence(db_session):
    _full_automation(db_session, True)
    prop = _queued_proposal(db_session)
    with pytest.raises(svc.TransitionError, match="final_review"):
        svc.transition(db_session, prop, "approved", consent={"channel": "auto"})


@pytest.mark.parametrize("status", ["applied", "interviewing", "offered", "accepted"])
def test_auto_consent_still_refuses_an_already_applied_application(db_session, status):
    _full_automation(db_session, True)
    prop = _queued_proposal(db_session)
    app_row = db_session.get(Application, prop.application_id)
    app_row.status = status
    db_session.commit()
    prop.evidence_json = _final_review_evidence()
    with pytest.raises(svc.TransitionError, match="already applied"):
        svc.transition(db_session, prop, "approved", consent={"channel": "auto"})


def test_auto_consent_still_refuses_past_the_daily_cap(db_session):
    from app.schemas.auto_apply import AutoApplySettings
    from app.services import auto_apply_settings

    auto_apply_settings.set_settings(
        AutoApplySettings(full_automation=True, max_submissions_per_day=1), db_session)
    first, second = _queued_proposal(db_session), _queued_proposal(db_session)
    for prop in (first, second):
        prop.evidence_json = _final_review_evidence()
    svc.transition(db_session, first, "approved", consent={"channel": "auto"})
    with pytest.raises(svc.TransitionError, match="daily submission cap reached"):
        svc.transition(db_session, second, "approved", consent={"channel": "auto"})
    assert second.status == "accepted" and second.cap_reserved_at is None
    assert db_session.query(ConsentEvent).filter_by(
        proposal_id=second.id, action="approved").count() == 0


def test_auto_approval_refuses_company_blocked_after_proposal_was_created(db_session):
    prop = _queued_proposal(db_session)
    from app.schemas.auto_apply import AutoApplySettings
    from app.services import auto_apply_settings

    auto_apply_settings.set_settings(
        AutoApplySettings(full_automation=True, company_blocklist=["  aCmE  "]), db_session)
    prop.evidence_json = _final_review_evidence()
    with pytest.raises(svc.TransitionError, match="Companies to skip list"):
        svc.transition(db_session, prop, "approved", consent={"channel": "auto"})
    assert prop.status == "accepted" and prop.cap_reserved_at is None
    assert db_session.query(ConsentEvent).filter_by(
        proposal_id=prop.id, action="approved").count() == 0


def test_auto_submission_is_recorded_if_company_blocked_after_approval(db_session):
    prop = _approved_auto(db_session)
    from app.schemas.auto_apply import AutoApplySettings
    from app.services import auto_apply_settings

    auto_apply_settings.set_settings(
        AutoApplySettings(full_automation=True, company_blocklist=[" AcMe "]), db_session)
    svc.transition(db_session, prop, "submitted", attested=True,
                   consent={"channel": "auto", "note": "Confirmation page"})
    event = db_session.query(ConsentEvent).filter_by(
        proposal_id=prop.id, action="submitted").one()
    app_row = db_session.get(Application, prop.application_id)
    assert prop.status == "submitted" and event.channel == "auto"
    assert event.note == "Confirmation page" and app_row.status == "applied"


def test_manual_approval_is_unchanged_by_a_later_company_block(db_session):
    prop = _mk_proposal(db_session)
    from app.schemas.auto_apply import AutoApplySettings
    from app.services import auto_apply_settings

    auto_apply_settings.set_settings(
        AutoApplySettings(company_blocklist=["  aCmE  "]), db_session)
    prop.evidence_json = _final_review_evidence()
    svc.transition(db_session, prop, "approved", consent={"channel": "chat", "note": "yes"})
    assert prop.status == "approved"


@pytest.mark.parametrize("on, expected_status", [(False, 409), (True, 200)])
def test_auto_consent_reaches_the_rest_gate(db_session, on, expected_status):
    from fastapi.testclient import TestClient
    from app.main import app

    _full_automation(db_session, on)
    prop = _queued_proposal(db_session)
    prop.evidence_json = _final_review_evidence()
    db_session.commit()
    response = TestClient(app).patch(f"/api/proposals/{prop.id}", json={
        "status": "approved", "consent": {"channel": "auto"},
    })
    assert response.status_code == expected_status, response.text
    if on:
        assert response.json()["status"] == "approved"
    else:
        assert "full automation" in response.json()["detail"]


def test_the_agents_word_can_mark_submitted_over_rest(db_session):
    from fastapi.testclient import TestClient
    from app.main import app

    prop = _approved_auto(db_session)
    response = TestClient(app).patch(f"/api/proposals/{prop.id}", json={
        "status": "submitted", "attested": True,
        "consent": {"channel": "auto", "note": "Confirmation page"},
    })
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "submitted"
    event = db_session.query(ConsentEvent).filter_by(proposal_id=prop.id, action="submitted").one()
    assert event.channel == "auto" and event.note == "Confirmation page"
