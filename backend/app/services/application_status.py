"""What changing an application's status does besides storing it.

One place for the PATCH route and the sync request applier, so a status set from either side
stamps the date, links earlier answers and closes the job's open proposals the same way.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.application_proposal import ApplicationProposal
from app.services import filled_answers
from app.services import proposals as proposal_svc

# Stages that imply the application was submitted.
SUBMITTED_STAGES = ("applied", "interviewing", "offered", "accepted")


def _stamp_applied_at(application: Application, fields: set[str]) -> None:
    """Keep applied_at in sync with the status transition, unless the caller set it in this
    same change (their value wins). Any submitted stage stamps the date once if unset; dropping
    back to "draft" clears it; rejected/withdrawn keep whatever is there (they don't imply an
    application happened)."""
    if "status" not in fields or "applied_at" in fields:
        return
    if application.status in SUBMITTED_STAGES:
        if application.applied_at is None:
            application.applied_at = datetime.now(UTC)
    elif application.status == "draft":
        application.applied_at = None


def _close_open_proposals(db: Session, application: Application) -> None:
    """User override (2026-08-01): marking the application applied+ means they completed it
    themselves, so resolve any open proposal on the JOB (linked or not; one open proposal per
    job) instead of leaving it squatting in the triage/queued lanes. Closed as a posting-scoped
    decline with an honest consent event; this also releases an approved proposal's cap slot
    and, via the declined-job guard, stops the hunt re-proposing a posting already applied to.
    Rejected/withdrawn applications deliberately do NOT close proposals."""
    open_props = db.scalars(
        select(ApplicationProposal).where(
            ApplicationProposal.job_id == application.job_id,
            ApplicationProposal.status.in_(tuple(proposal_svc.OPEN_STATUSES)),
        )
    ).all()
    for prop in open_props:
        try:
            proposal_svc.transition(
                db, prop, "rejected",
                consent={"channel": "frontend", "note": "user marked the application applied"},
                reason=proposal_svc.APPLIED_MANUALLY,
            )
        except proposal_svc.TransitionError:
            # A concurrent transition beat us to a terminal state; the user's status change
            # must not fail over ledger housekeeping.
            continue


def apply_status_effects(db: Session, application: Application, fields: set[str]) -> None:
    """Everything a status change implies, after the new values are set and before the caller
    commits. ``fields`` names what this change set."""
    _stamp_applied_at(application, fields)
    if "status" in fields and application.status in SUBMITTED_STAGES:
        # Marked applied: the job's receipt rows posted before it had an application are its.
        filled_answers.link_unlinked(db, application)
        _close_open_proposals(db, application)


def apply_status_and_notes(db: Session, application: Application, values: dict) -> None:
    """A status and/or notes change queued by the other copy, applied under the same rules as the
    PATCH route, then committed."""
    for name in ("status", "notes"):
        if name in values:
            setattr(application, name, values[name])
    apply_status_effects(db, application, set(values))
    db.commit()
