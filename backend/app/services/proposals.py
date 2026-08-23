"""Proposal ledger state machine. Every transition guard lives here so a buggy
or adversarial MCP caller cannot record a submission without consent: entering
approved/rejected writes a ConsentEvent in the same transaction, and submitted
additionally requires evidence. Expiry is lazy (expire_stale on reads) — this
system deliberately has no scheduler."""
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.application_proposal import ApplicationProposal
from app.models.consent_event import ConsentEvent
from app.models.job import Job
from app.services import auto_apply_settings


class TransitionError(Exception):
    """Illegal transition or missing precondition; routers map this to 409."""


ALLOWED = {
    "pending_review": {"accepted", "approved", "rejected", "needs_decision", "needs_human", "expired"},
    "needs_decision": {"pending_review", "rejected", "expired"},
    # Triage acceptance (design 2026-07-31): the user queued this posting for
    # the next apply run. Pre-consent — no cap reservation, no final_review
    # requirement; the approved gate downstream is unchanged.
    "accepted": {"approved", "rejected", "needs_human"},
    "approved": {"submitted", "needs_human", "rejected", "submission_uncertain"},
    "needs_human": {"approved", "rejected", "pending_review"},
    # One attested-only edge (guarded in transition()): the user later confirms
    # an uncertain submit went through (confirmation email / portal check).
    # Never resumable, never re-clickable — that stays absolute.
    "submission_uncertain": {"submitted"},
    # submitted / rejected / expired are terminal
}

CONSENT_REQUIRED = {"accepted", "approved", "rejected"}
CONSENT_CHANNELS = ("chat", "slack", "frontend", "mcp")

EVIDENCE_KINDS = frozenset({"step", "final_review", "submission_receipt"})

# Status sets for the agent-job execute gate (P1).
OP_ALLOWED_STATUSES: dict[str, frozenset[str]] = {
    "prepare": frozenset({"pending_review", "accepted", "approved"}),
    "attach_evidence": frozenset({"pending_review", "accepted", "needs_human", "approved"}),
    "record_consent": frozenset({"pending_review", "accepted", "needs_human"}),
    "mark_submitted": frozenset({"approved", "submission_uncertain"}),
}

OPEN_STATUSES = frozenset({
    "pending_review", "needs_decision", "accepted", "approved", "needs_human",
})


def create_proposal(session, *, job_id, application_id=None, referral_id=None,
                    fit=None, plan=None) -> ApplicationProposal:
    cfg = auto_apply_settings.get_settings(session)
    prop = ApplicationProposal(
        job_id=job_id, application_id=application_id, referral_id=referral_id,
        status="pending_review", fit_json=fit, plan_json=plan,
        expires_at=datetime.now(UTC) + timedelta(days=cfg.proposal_expiry_days),
    )
    session.add(prop)
    session.commit()
    return prop


def _evidence_has_kind(prop: ApplicationProposal, kind: str) -> bool:
    return any(
        isinstance(item, dict) and item.get("kind") == kind
        for item in (prop.evidence_json or [])
    )


def _release_cap(prop: ApplicationProposal) -> None:
    prop.cap_reserved_at = None


def _reserve_cap(session: Session, prop: ApplicationProposal) -> None:
    if prop.cap_reserved_at is not None:
        return
    _enforce_daily_cap(session)
    prop.cap_reserved_at = datetime.now(UTC)


def transition(session: Session, prop: ApplicationProposal, new_status: str,
               *, consent: dict | None = None, reason: str | None = None,
               intervention: dict | None = None,
               attested: bool = False) -> ApplicationProposal:
    if new_status not in ALLOWED.get(prop.status, set()):
        raise TransitionError(f"cannot go {prop.status} -> {new_status}")
    if new_status in CONSENT_REQUIRED:
        if not consent or consent.get("channel") not in CONSENT_CHANNELS:
            raise TransitionError(f"{new_status} requires consent with a valid channel")
    if new_status == "approved" and not _evidence_has_kind(prop, "final_review"):
        raise TransitionError("approved requires final_review evidence")
    if new_status == "submitted":
        # Receipt is the agent-verified path; attestation is the user saying
        # so themselves (design §4, 2026-08-01). The agent alone can never
        # self-certify a submit: no receipt and no user statement -> refused.
        if prop.status == "submission_uncertain" and not attested:
            raise TransitionError(
                "submission_uncertain -> submitted requires user attestation")
        if not attested and not _evidence_has_kind(prop, "submission_receipt"):
            raise TransitionError(
                "submitted requires submission_receipt evidence or user attestation")
        if attested and (not consent or consent.get("channel") not in CONSENT_CHANNELS):
            raise TransitionError("attested submit requires consent with a valid channel")

    if new_status == "approved" and prop.application_id is not None:
        # G7 (design 2026-08-01): the user may have applied manually (web
        # StatusChip is ungated) while this proposal sat queued — never
        # consent-to-submit the same application twice.
        linked = session.get(Application, prop.application_id)
        if linked is not None and (linked.status or "draft") in (
            "applied", "interviewing", "offered", "accepted",
        ):
            raise TransitionError(
                "linked application already applied — decline or delete this proposal")

    if new_status == "approved":
        _reserve_cap(session, prop)
    if new_status == "rejected" and prop.cap_reserved_at is not None:
        _release_cap(prop)

    if new_status in CONSENT_REQUIRED or (new_status == "submitted" and attested):
        session.add(ConsentEvent(
            proposal_id=prop.id, action=new_status, channel=consent["channel"],
            note=consent.get("note"),
            evidence_manifest_json=prop.evidence_json,
        ))
    if reason is not None:
        prop.reason = reason
    if intervention is not None:
        prop.intervention_json = intervention
    prop.status = new_status

    if new_status == "submitted" and prop.application_id is not None:
        app_row = session.get(Application, prop.application_id)
        if app_row is not None:
            # Same stamping rule as PATCH /api/applications (routers/applications.py):
            # entering applied stamps applied_at once if unset.
            app_row.status = "applied"
            if app_row.applied_at is None:
                app_row.applied_at = datetime.now(UTC)

    session.commit()
    return prop


def request_decision(session: Session, prop: ApplicationProposal,
                     *, reason: str | None = None) -> ApplicationProposal:
    if prop.status == "needs_decision":
        if reason is not None:
            prop.reason = reason
            session.commit()
        return prop
    return transition(session, prop, "needs_decision", reason=reason)


def resume_proposal(session: Session, prop: ApplicationProposal) -> ApplicationProposal:
    if prop.status == "submission_uncertain":
        raise TransitionError("cannot resume submission_uncertain")
    if prop.status != "needs_human":
        raise TransitionError(f"cannot resume from {prop.status}")
    _release_cap(prop)
    return transition(session, prop, "pending_review")


def report_failure(session: Session, prop: ApplicationProposal, *, reason: str,
                   intervention: dict | None = None) -> ApplicationProposal:
    if reason == "submission_uncertain":
        return transition(
            session, prop, "submission_uncertain",
            reason=reason, intervention=intervention,
        )
    return transition(
        session, prop, "needs_human",
        reason=reason, intervention=intervention,
    )


def record_decision(session: Session, prop: ApplicationProposal, *, fit: dict,
                    application_id: UUID | None = None) -> ApplicationProposal:
    if application_id is None and prop.application_id is None:
        chosen = (fit or {}).get("chosen_base")
        if not chosen:
            raise TransitionError("no matching application for decision")
        app_row = session.scalar(
            select(Application)
            .where(
                Application.job_id == prop.job_id,
                Application.base_resume == chosen,
            )
            .order_by(Application.created_at.desc())
            .limit(1)
        )
        if app_row is None:
            raise TransitionError("no matching application for decision")
        application_id = app_row.id

    if application_id is not None:
        if prop.application_id is not None and prop.application_id != application_id:
            raise TransitionError("proposal already linked to an application")
        app_row = session.get(Application, application_id)
        if app_row is None:
            raise TransitionError("no matching application for decision")
        app_row.source = "agent"
        prop.application_id = application_id

    merged = dict(prop.fit_json or {})
    merged.update(fit or {})
    merged["decided_by"] = "user"
    prop.fit_json = merged
    return transition(session, prop, "pending_review")


def require_open_proposal_for_application(
    session: Session,
    application_id: UUID,
    *,
    op: str,
) -> ApplicationProposal | None:
    """Gate execute helpers for agent-sourced jobs.

    Manual/user-driven apply (Job.source != 'agent') is ungated and returns None.
    Agent jobs require a linked open proposal in the status set for ``op``.
    """
    allowed = OP_ALLOWED_STATUSES.get(op)
    if allowed is None:
        raise TransitionError(f"unknown proposal gate op: {op}")

    app_row = session.get(Application, application_id)
    if app_row is None:
        raise TransitionError("application not found")
    job = session.get(Job, app_row.job_id)
    if job is None:
        raise TransitionError("job not found")
    if job.source != "agent":
        return None

    prop = session.scalar(
        select(ApplicationProposal)
        .where(
            ApplicationProposal.job_id == job.id,
            ApplicationProposal.status.in_(tuple(allowed)),
            or_(
                ApplicationProposal.application_id == application_id,
                ApplicationProposal.application_id.is_(None),
            ),
        )
        .order_by(ApplicationProposal.created_at.desc())
        .limit(1)
    )
    if prop is None:
        raise TransitionError("no open proposal for this job")
    # Prefer a proposal already linked to this application when both exist.
    if prop.application_id is not None and prop.application_id != application_id:
        raise TransitionError("no open proposal for this job")
    return prop


def require_open_proposal(
    session: Session,
    prop: ApplicationProposal,
    *,
    op: str,
) -> ApplicationProposal:
    """Gate proposal-id execute helpers (evidence / consent / submit)."""
    allowed = OP_ALLOWED_STATUSES.get(op)
    if allowed is None:
        raise TransitionError(f"unknown proposal gate op: {op}")
    job = session.get(Job, prop.job_id)
    if job is not None and job.source != "agent":
        return prop
    if prop.status not in allowed:
        raise TransitionError("no open proposal for this job")
    return prop


def _knockout_scan(session: Session, job: Job | None) -> dict | None:
    """Stated-JD-requirements vs profile — the loud check the user (or agent)
    must see BEFORE consenting. Informational like G11 tier 2: it flags, the
    consent gate stays with the human."""
    if job is None:
        return None
    from app.services import autofill_profile, job_preferences, knockout

    return knockout.scan_job(
        job,
        autofill_profile.get_work_auth(session),
        autofill_profile.get_profile(session).get("preferences"),
        years_experience=job_preferences.get_preferences(session).years_experience,
    )


def get_final_review(session: Session, prop: ApplicationProposal) -> dict:
    from pathlib import Path

    from app.models.qa_entry import QAEntry

    job = session.get(Job, prop.job_id)
    app_row = session.get(Application, prop.application_id) if prop.application_id else None
    qa_rows = []
    if app_row is not None:
        qa_rows = session.scalars(
            select(QAEntry).where(QAEntry.application_id == app_row.id)
        ).all()

    pdf = {"ready": False, "filename": None}
    if app_row is not None and app_row.pdf_path:
        pdf = {"ready": True, "filename": Path(app_row.pdf_path).name}

    consent_recorded = session.scalar(
        select(ConsentEvent.id).where(
            ConsentEvent.proposal_id == prop.id,
            ConsentEvent.action == "approved",
        ).limit(1)
    ) is not None

    plan = prop.plan_json or {}
    intervention = prop.intervention_json or {}
    fit = prop.fit_json or {}
    scores = fit.get("scores") or {}
    chosen = fit.get("chosen_base")
    ats_delta = None
    if chosen and isinstance(scores, dict) and len(scores) >= 2:
        ordered = sorted(
            ((k, v) for k, v in scores.items() if isinstance(v, (int, float))),
            key=lambda kv: kv[1],
            reverse=True,
        )
        if len(ordered) >= 2:
            ats_delta = ordered[0][1] - ordered[1][1]

    # G11 tier 2: a same-company+title proposal already submitted is the loud
    # warning the user must see BEFORE consenting — company+title is a soft
    # identity (teams legitimately post near-identical roles), so this flags
    # rather than blocks.
    duplicate_submitted = False
    if job is not None and job.company and job.title:
        duplicate_submitted = session.scalar(
            select(ApplicationProposal.id)
            .join(Job, Job.id == ApplicationProposal.job_id)
            .where(
                ApplicationProposal.id != prop.id,
                ApplicationProposal.status.in_(("submitted", "submission_uncertain")),
                func.lower(Job.company) == job.company.lower(),
                func.lower(Job.title) == job.title.lower(),
            )
            .limit(1)
        ) is not None

    return {
        "proposal_id": str(prop.id),
        "status": prop.status,
        "duplicate_submitted": duplicate_submitted,
        "job": {
            "id": str(job.id) if job else None,
            "company": job.company if job else None,
            "title": job.title if job else None,
        },
        "knockout": _knockout_scan(session, job),
        "fit": {
            "chosen_base": chosen,
            "scores": scores or None,
            "ats_delta": ats_delta,
            "decided_by": fit.get("decided_by"),
        },
        "pdf": pdf,
        "qa_entries": [
            {
                "id": str(q.id),
                "kind": q.kind,
                "prompt": q.prompt,
                "answer": q.answer,
            }
            for q in qa_rows
        ],
        "eeo": {"consent_recorded": consent_recorded},
        "blocked_items": plan.get("blocked_items") or intervention.get("blocked_items") or [],
        "manual_items": plan.get("manual_items") or intervention.get("manual_items") or [],
        "intervention": intervention or None,
        "evidence": list(prop.evidence_json or []),
    }


def cap_status(session: Session) -> dict:
    """Daily-cap readout (G5): lets an apply run size itself instead of
    discovering the cap by 409 mid-batch. Cap slots are consumed while
    reserved (cap_reserved_at set); release clears the flag; submitted /
    submission_uncertain keep it set."""
    cfg = auto_apply_settings.get_settings(session)
    since = datetime.now(UTC) - timedelta(days=1)
    reserved = len(session.scalars(select(ApplicationProposal.id).where(
        ApplicationProposal.cap_reserved_at.is_not(None),
        ApplicationProposal.cap_reserved_at >= since,
    )).all())
    return {
        "max_per_day": cfg.max_submissions_per_day,
        "reserved_last_24h": reserved,
        "remaining": max(0, cfg.max_submissions_per_day - reserved),
    }


def _enforce_daily_cap(session: Session) -> None:
    cap = cap_status(session)
    if cap["remaining"] <= 0:
        raise TransitionError(
            f"daily submission cap reached ({cap['reserved_last_24h']}/{cap['max_per_day']})")


def expire_stale(session: Session) -> int:
    now = datetime.now(UTC)
    stale = session.scalars(select(ApplicationProposal).where(
        ApplicationProposal.status.in_(("pending_review", "needs_decision")),
        ApplicationProposal.expires_at.is_not(None),
        ApplicationProposal.expires_at < now)).all()
    for prop in stale:
        prop.status = "expired"
        prop.reason = prop.reason or "expired unreviewed"
    if stale:
        session.commit()
    return len(stale)
