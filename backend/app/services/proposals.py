"""Proposal ledger state machine. Every transition guard lives here so a buggy
or adversarial MCP caller cannot record a submission without consent: entering
approved/rejected writes a ConsentEvent in the same transaction, and submitted
additionally requires evidence. Expiry is lazy (expire_stale on reads) — this
system deliberately has no scheduler."""
import unicodedata
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.application_proposal import ApplicationProposal
from app.models.consent_event import ConsentEvent
from app.models.job import Job
from app.services import auto_apply_settings, filled_answers, job_site_login


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
    # One attested-only edge (guarded in transition()): after an uncertain
    # submit, the user or an agent in full automation confirms it went through.
    # Never resumable, never re-clickable — that stays absolute.
    "submission_uncertain": {"submitted"},
    # submitted / rejected / expired are terminal
}

# A proposal status as the Agent inbox's chip reads it (`PROPOSAL_STATUS_CHIP`
# in frontend/components/status-chip.tsx, pinned equal by
# test_proposal_state_machine.py): the bulk toast prints this refusal. The keys
# stay what agents and the API use.
STATUS_CHIP_WORDS = {
    "pending_review": "Proposed", "needs_decision": "Needs you",
    "needs_human": "Needs you", "accepted": "Queued", "approved": "Approved",
    "submitted": "Applied", "submission_uncertain": "Check if sent",
    "rejected": "Skipped", "expired": "Expired",
}

CONSENT_REQUIRED = {"accepted", "approved", "rejected"}
CONSENT_CHANNELS = ("chat", "slack", "frontend", "mcp", "auto")

# Full automation mode (phase 4): the agent's own yes, and its own word that a job went
# through, labelled so the ledger can tell them from the user's. The server checks only the
# switch (and that a confirmation is named); eligibility is the agent's prompt.
AUTO_CHANNEL = "auto"

LOGIN_STATUSES = frozenset({"accepted", "approved"})


def share_job_site_login(session: Session, prop: ApplicationProposal,
                         agent: str | None) -> dict[str, str]:
    """{email, password} for an open job in full automation mode; one audit row per call
    (never the value). SYSTEM.md {#inv-job-site-password-local}."""
    if not auto_apply_settings.get_settings(session).full_automation:
        raise TransitionError("the job-site login needs full automation turned on in Settings")
    if prop.status not in LOGIN_STATUSES:
        raise TransitionError("the job-site login is for a queued or approved job")
    email, password = job_site_login.read()
    if not email or not password:
        raise LookupError("No job-site login is saved in Settings")
    session.add(ConsentEvent(proposal_id=prop.id, action="login_shared", channel="mcp", note=agent))
    session.commit()
    return {"email": email, "password": password}


def _company_is_blocked(session: Session, prop: ApplicationProposal,
                        company_blocklist: list[str]) -> bool:
    job = session.get(Job, prop.job_id)
    company = (job.company or "").strip().lower() if job else ""
    blocked = {name.strip().lower() for name in company_blocklist}
    return bool(company and company in blocked)


def _auto_approval_is_blocked(session: Session, prop: ApplicationProposal,
                              new_status: str, company_blocklist: list[str]) -> bool:
    return new_status == "approved" and _company_is_blocked(session, prop, company_blocklist)


def _has_alphanumeric_confirmation(note: str | None) -> bool:
    return any(char.isalnum() for char in note or "")


def _auto_transition_supported(new_status: str, attested: bool) -> bool:
    return new_status == "approved" or (new_status == "submitted" and attested)


def _check_auto_consent(session: Session, prop: ApplicationProposal, new_status: str,
                        consent: dict, attested: bool) -> None:
    if not _auto_transition_supported(new_status, attested):
        raise TransitionError("the auto channel only approves a job or confirms it went through")
    if new_status == "approved" and prop.status != "accepted":
        raise TransitionError("the auto channel can only approve a user-queued proposal")
    if new_status == "submitted" and not _has_alphanumeric_confirmation(consent.get("note")):
        raise TransitionError("an automatic submit needs a note saying what confirmed it")
    cfg = auto_apply_settings.get_settings(session)
    if not cfg.full_automation:
        raise TransitionError("the auto channel needs full automation turned on in Settings")
    if _auto_approval_is_blocked(session, prop, new_status, cfg.company_blocklist):
        raise TransitionError("This company is on your Companies to skip list in Settings › Connected agents")

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


# What the web app's own queue records as the filer (ProposalCreate.proposed_by).
FILED_BY_YOU = "you"

# The reason a proposal closes with when the user applied to its job themselves
# (routers/applications.py); the inbox's History shows it as Applied yourself.
APPLIED_MANUALLY = "applied manually"


def _visible_letters(name: str) -> str:
    """The name as a reader sees it: NFKC (fullwidth "ｙｏｕ" is "you"), without
    whitespace or invisible format characters (BOM, zero-width), casefolded."""
    return "".join(
        c for c in unicodedata.normalize("NFKC", name)
        if not c.isspace() and unicodedata.category(c) != "Cf"
    ).casefold()


def proposal_filer(origin: str | None, detail: str | None, claimed: str | None) -> str | None:
    """Who is filing a new proposal. A connected agent (origin "mcp") is named
    by its client's self-declared name and never by the body, so it cannot file
    as "you": a client that DECLARES itself "you", however disguised, or whose
    name shows nothing at all, reads as unknown instead."""
    if origin == "mcp":
        seen = _visible_letters(detail or "")
        return None if seen in ("", FILED_BY_YOU) else detail
    return claimed


def create_proposal(session, *, job_id: UUID, application_id: UUID | None = None,
                    referral_id: UUID | None = None,
                    fit=None, plan=None, proposed_by: str | None = None) -> ApplicationProposal:
    cfg = auto_apply_settings.get_settings(session)
    prop = ApplicationProposal(
        job_id=job_id, application_id=application_id, referral_id=referral_id,
        status="pending_review", fit_json=fit, plan_json=plan, proposed_by=proposed_by,
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
        raise TransitionError(
            f"This proposal's status is {STATUS_CHIP_WORDS.get(prop.status, prop.status)}, "
            "so it can't be changed that way.")
    if new_status in CONSENT_REQUIRED:
        if not consent or consent.get("channel") not in CONSENT_CHANNELS:
            raise TransitionError(f"{new_status} requires consent with a valid channel")
    if consent and consent.get("channel") == AUTO_CHANNEL:
        _check_auto_consent(session, prop, new_status, consent, attested)
    if new_status == "approved" and not _evidence_has_kind(prop, "final_review"):
        raise TransitionError("approved requires final_review evidence")
    if new_status == "submitted":
        # Receipt is the agent-verified path; attestation may be the user's own
        # word or an agent's named confirmation while full automation is On.
        if prop.status == "submission_uncertain" and not attested:
            raise TransitionError(
                "submission_uncertain -> submitted requires attestation "
                "(the user's, or the agent's in full automation mode)")
        if not attested and not _evidence_has_kind(prop, "submission_receipt"):
            raise TransitionError(
                "submitted requires submission_receipt evidence or attestation "
                "(the user's, or the agent's in full automation mode)")
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
            filled_answers.link_unlinked(session, app_row)

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


# The 409 when a decision has nothing to link: the web app's Keep it shows it, and an
# agent reads it as "tailor first" (docs/playbooks/agent-apply.md), so it is one sentence.
NO_APPLICATION_TO_LINK = (
    "This job has no tailored resume to link yet. Tailor one first, then try again."
)


def record_decision(session: Session, prop: ApplicationProposal, *, fit: dict,
                    application_id: UUID | None = None) -> ApplicationProposal:
    if application_id is None and prop.application_id is None:
        chosen = (fit or {}).get("chosen_base")
        if not chosen:
            raise TransitionError(NO_APPLICATION_TO_LINK)
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
            raise TransitionError(NO_APPLICATION_TO_LINK)
        application_id = app_row.id

    if application_id is not None:
        if prop.application_id is not None and prop.application_id != application_id:
            raise TransitionError("proposal already linked to an application")
        app_row = session.get(Application, application_id)
        if app_row is None:
            raise TransitionError("That application no longer exists.")
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
    from app.services import knockout

    return knockout.scan_for(session, job)


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
        # The recorded form answers worth a second look before "Submit now?" (warn only).
        # EEO entries carry `eeo_answered`, never a value.
        "flags": filled_answers.agent_flags(session, job),
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
