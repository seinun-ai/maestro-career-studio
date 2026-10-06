"""Requests for the other copy's jobs: stored here, sent at the next sync.

A queue, skip, status or note change on a job the other machine owns is kept as a
`SyncRequest` and answered "Sent at the next sync" instead of refused. Anything else on
such a job is still the guard's 409. A job this machine offered to the always-on copy
(`handover == "offered"`) is still this machine's job, so it is never queued: it stays
a 409 that says what to do instead.
"""

import uuid

from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.application_proposal import ApplicationProposal
from app.models.job import Job
from app.models.sync import SyncRequest
from app.schemas.proposal import ProposalBulkTransition, ProposalTransition
from app.services.sync import hooks, status

QUEUED_DETAIL = "Sent at the next sync."
# What a request may carry. Anything outside these is not forwarded, never a secret.
PROPOSAL_FIELDS = frozenset({"status", "consent", "reason"})
APPLICATION_FIELDS = frozenset({"status", "notes"})


def is_other_copys(db: Session, job_id: uuid.UUID) -> bool:
    """True when sync is on and the OTHER machine owns the job (not an offered one)."""
    if not status.enabled():
        return False
    owner = db.execute(select(Job.owner_machine).where(Job.id == job_id)).scalar_one_or_none()
    return owner is not None and owner != status.machine_id(db)


def enqueue(db: Session, kind: str, job_id: uuid.UUID, payload: dict) -> SyncRequest:
    row = SyncRequest(kind=kind, job_id=job_id, payload_json=payload,
                      origin="local", status="pending")
    db.add(row)
    db.commit()
    return row


def enqueue_take_over(db: Session, job_id: uuid.UUID) -> SyncRequest:
    """Ask the other copy to hand this job back."""
    return enqueue(db, "take_over", job_id, {})


def queued_response() -> JSONResponse:
    return JSONResponse(status_code=202, content={"queued": True, "detail": QUEUED_DETAIL})


def _refuse_or_proceed(db: Session, job_id: uuid.UUID) -> None:
    # Raises the guard's sentence for an offered job or a field we cannot forward.
    hooks.require_owned(db, job_id)


def _transition_payload(prop: ApplicationProposal, body: ProposalTransition | ProposalBulkTransition) -> dict:
    # The user's own decision and words travel so the owner can record the ConsentEvent.
    payload = {"proposal_id": str(prop.id), "to": body.status, "reason": body.reason}
    if body.consent is not None:
        payload["consent"] = body.consent.model_dump(exclude_unset=True)
    return payload


def queue_proposal_transition(
    db: Session, prop: ApplicationProposal, body: ProposalTransition,
) -> JSONResponse | None:
    """The 202 when the request was queued, None when the route should go on."""
    fields = body.model_fields_set
    if is_other_copys(db, prop.job_id) and fields and fields <= PROPOSAL_FIELDS:
        enqueue(db, "proposal_transition", prop.job_id, _transition_payload(prop, body))
        return queued_response()
    _refuse_or_proceed(db, prop.job_id)
    return None


def queue_application_patch(
    db: Session, application: Application, fields: dict,
) -> JSONResponse | None:
    """The 202 when the status/notes change was queued, None when the route should go on."""
    if is_other_copys(db, application.job_id) and fields and set(fields) <= APPLICATION_FIELDS:
        enqueue(db, "application_patch", application.job_id,
                {"application_id": str(application.id), "fields": fields})
        return queued_response()
    _refuse_or_proceed(db, application.job_id)
    return None


def bulk_row_detail(db: Session, prop: ApplicationProposal, body: ProposalBulkTransition) -> str | None:
    """Queue one bulk row for the other copy; the sentence to report, or None to apply it here."""
    if not is_other_copys(db, prop.job_id):
        _refuse_or_proceed(db, prop.job_id)
        return None
    enqueue(db, "proposal_transition", prop.job_id, _transition_payload(prop, body))
    return QUEUED_DETAIL
