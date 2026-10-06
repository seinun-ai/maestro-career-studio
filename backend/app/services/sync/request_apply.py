"""Applying the other copy's requests (split-ownership design, Part B).

One place, used by home's ``POST /api/sync/requests`` and by the always-on copy's round: a request
is applied under the normal rules, and its record commits with the change itself, so a request is
never applied twice. Nothing here echoes a payload or ``str(exc)``: a refusal is a fixed sentence
or one of the rule sentences the services already use.
"""

import logging
import uuid
from typing import Any, TypeVar

from pydantic import AwareDatetime, BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.application_proposal import ApplicationProposal
from app.models.career_kb import KBPoint
from app.models.job import Job
from app.models.sync import SyncRequest
from app.models.types import utcnow
from app.schemas.application import ApplicationPatch
from app.schemas.proposal import ConsentPayload
from app.services import application_status, proposals, tailoring_session
from app.services.ats import normalize_term
from app.services.sync import hooks, status, wire

logger = logging.getLogger(__name__)

Model = TypeVar("Model", bound=BaseModel)

MAX_CLAIM = 2000
NOT_HERE_ON_HOME = "This job isn't on your laptop."
NOT_HERE_ON_REMOTE = "This job isn't on this copy."
MOVING = "This job is moving to your bot; make the change there once it arrives."
WRONG_JOB = "That doesn't belong to this job."
BAD_PAYLOAD = "This request wasn't valid."
NO_TAKE_OVER = "A job on your laptop is handed over from your laptop."
UNKNOWN_KIND = "Maestro doesn't know that kind of request."
NOT_REPEATABLE = "This request can't be repeated."
REQUEST_FAILED = "Maestro couldn't apply this request."
# The bot's own answers to a take-over (round.py); the laptop shows them in its runs panel.
BUSY_APPLYING = "Your bot is applying to this one; try again after its run."
NOT_HOLDING = "Your bot isn't holding this job."
CANT_SEND_BACK = "Maestro couldn't send this job back to your laptop."


class RequestIn(BaseModel):
    id: uuid.UUID
    kind: str
    job_id: uuid.UUID | None = None
    payload: dict[str, Any]
    created_at: AwareDatetime


class Refusal(Exception):
    """Why a request was refused; always a fixed or rule sentence."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class _TransitionPayload(BaseModel):
    proposal_id: uuid.UUID
    to: str
    reason: str | None = None
    consent: ConsentPayload | None = None


class _PatchPayload(BaseModel):
    application_id: uuid.UUID
    fields: dict[str, Any]


def _payload(model: type[Model], item: RequestIn) -> Model:
    try:
        return model.model_validate(item.payload)
    except ValidationError:
        raise Refusal(BAD_PAYLOAD) from None


def _own_job(db: Session, job_id: uuid.UUID | None) -> Job:
    """The job a request is about, when it is this copy's and not on its way out."""
    job = db.get(Job, job_id) if job_id is not None else None
    if job is None or job.owner_machine not in (None, status.machine_id(db)):
        raise Refusal(NOT_HERE_ON_REMOTE if status.is_remote() else NOT_HERE_ON_HOME)
    if job.handover == "offered":
        raise Refusal(MOVING)
    return job


def _apply_transition(db: Session, item: RequestIn) -> None:
    job = _own_job(db, item.job_id)
    body = _payload(_TransitionPayload, item)
    proposal = db.get(ApplicationProposal, body.proposal_id)
    if proposal is None or proposal.job_id != job.id:
        raise Refusal(WRONG_JOB)
    consent = body.consent.model_dump(exclude_unset=True) if body.consent else None
    try:
        if body.to == "pending_review" and proposal.status == "needs_decision":
            proposals.record_decision(db, proposal, fit={})  # as the web route does
        else:
            proposals.transition(db, proposal, body.to, consent=consent, reason=body.reason)
    except proposals.TransitionError as rule:
        raise Refusal(str(rule)) from None


def _patch_values(fields: dict) -> dict:
    try:
        patch = ApplicationPatch.model_validate(fields)
    except ValidationError:
        raise Refusal(BAD_PAYLOAD) from None
    values = {name: getattr(patch, name) for name in patch.model_fields_set}
    if not values or set(fields) - {"status", "notes"} or values.get("status", "x") is None:
        raise Refusal(BAD_PAYLOAD)
    return values


def _apply_patch(db: Session, item: RequestIn) -> None:
    job = _own_job(db, item.job_id)
    body = _payload(_PatchPayload, item)
    values = _patch_values(body.fields)
    application = db.get(Application, body.application_id)
    if application is None or application.job_id != job.id:
        raise Refusal(WRONG_JOB)
    application_status.apply_status_and_notes(db, application, values)


def _apply_addition(db: Session, item: RequestIn) -> None:
    claim = item.payload.get("claim")
    if not isinstance(claim, str) or not claim.strip() or len(claim) > MAX_CLAIM:
        raise Refusal(BAD_PAYLOAD)
    known = {normalize_term(text) for text in db.scalars(select(KBPoint.text).where(
        KBPoint.provenance == "user_cannot_confirm")) if text}
    if normalize_term(claim) in known:
        return
    holder = tailoring_session._cannot_confirm_holder(db)
    db.add(KBPoint(entity_id=holder.id, text=claim.strip(), state="retired",
                   origin="gap_elicitation", provenance="user_cannot_confirm"))


def _refuse_take_over(db: Session, item: RequestIn) -> None:
    raise Refusal(NO_TAKE_OVER)


APPLIERS = {"proposal_transition": _apply_transition, "application_patch": _apply_patch,
            "profile_addition": _apply_addition, "take_over": _refuse_take_over}


def _record(item: RequestIn, outcome: str, reason: str | None) -> SyncRequest:
    return SyncRequest(id=item.id, job_id=item.job_id, kind=item.kind[:32],
                       payload_json=item.payload, origin="remote", status=outcome, reason=reason,
                       created_at=item.created_at, answered_at=utcnow())


def _refused(db: Session, item: RequestIn, reason: str) -> tuple[str, str | None]:
    db.rollback()
    db.add(_record(item, "refused", reason))
    db.commit()
    return "refused", reason


def _reason_of(failure: Exception) -> str:
    if isinstance(failure, Refusal):
        return failure.reason
    if isinstance(failure, hooks.NotOwnedHere):
        return str(failure)
    logger.warning("A sync request couldn't be applied.")
    return REQUEST_FAILED


def settle(db: Session, item: RequestIn) -> tuple[str, str | None]:
    """Apply one request; its record commits with the change itself. A request that cannot be
    applied is refused alone, with a fixed sentence."""
    applier = APPLIERS.get(item.kind)
    try:
        if applier is None:
            raise Refusal(UNKNOWN_KIND)
        db.add(_record(item, "applied", None))
        applier(db, item)
        db.commit()
        return "applied", None
    except Exception as failure:
        return _refused(db, item, _reason_of(failure))


def answer(db: Session, item: RequestIn) -> dict:
    """The answer to one request. A resend is answered as before, applying nothing."""
    earlier = db.get(SyncRequest, item.id)
    if earlier is not None:
        mine = earlier.origin == "remote"
        outcome, reason = (earlier.status, earlier.reason) if mine else ("refused", NOT_REPEATABLE)
    else:
        outcome, reason = settle(db, item)
    return {"id": item.id.hex, "status": outcome, "reason": reason}


def parse(raw: object) -> RequestIn | None:
    try:
        return RequestIn.model_validate(raw)
    except ValidationError:
        return None


def _wire_of(row: SyncRequest) -> RequestIn:
    return RequestIn(id=row.id, kind=row.kind, job_id=row.job_id, payload=row.payload_json,
                     created_at=row.created_at)


def _refuse_stored(db: Session, request_id: uuid.UUID, reason: str) -> str:
    db.rollback()
    row = db.get(SyncRequest, request_id)
    row.status, row.reason, row.answered_at = "refused", reason[:wire.MAX_REASON] or None, utcnow()
    db.commit()
    return "refused"


def settle_stored(db: Session, row: SyncRequest) -> str:
    """Apply a request this copy stored itself, for a job that is ours now. The row's status is set
    in the same transaction as the change, so a crash leaves both or neither."""
    request_id, kind = row.id, row.kind
    applier = APPLIERS.get(kind)
    try:
        if applier is None:
            raise Refusal(UNKNOWN_KIND)
        item = _wire_of(row)
        row.status, row.reason, row.answered_at = "applied", None, utcnow()
        if kind != "take_over":  # asking for a job back that is already here is moot
            applier(db, item)
        db.commit()
        return "applied"
    except Exception as failure:
        return _refuse_stored(db, request_id, _reason_of(failure))
