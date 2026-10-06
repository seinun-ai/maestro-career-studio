"""Home's side of the sync channel (split-ownership design, Part B).

The always-on copy drives every request; this copy only answers. Every route first runs
``_require_sync``: 404 while sync is off (or on the always-on copy), 403 for any request carrying
an ``Origin``, 401 unless the bearer key matches, 409 when the peer's protocol or schema differs,
and 409 while another request is running. Nothing here logs or echoes a key, a bundle, a request
body, the AI key or the job-site password: every response and stored reason is a fixed sentence
or one of the rule sentences the services already use, never ``str(exc)``.
"""

import hmac
import json
import logging
import re
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Annotated, Any, Literal, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.db import get_db
from app.models.agent_run import AgentRun
from app.models.application import Application
from app.models.application_proposal import ApplicationProposal
from app.models.career_kb import KBPoint
from app.models.job import Job
from app.models.sync import SyncRequest, SyncState, SyncTombstone
from app.models.types import utcnow
from app.routers import version
from app.schemas.agent_runs import MAX_DIGEST, MAX_JOB_IDS, RunOutcome
from app.schemas.application import ApplicationPatch
from app.schemas.proposal import ConsentPayload
from app.services import application_status, proposals, tailoring_session
from app.services.ats import normalize_term
from app.services.sync import duplicates, hooks, jobs_bundle, profile_bundle, status

logger = logging.getLogger(__name__)

Model = TypeVar("Model", bound=BaseModel)

MAX_BODY_BYTES = 100 * 1024 * 1024
_LOCK = threading.Lock()
_MACHINE_ID = re.compile(r"[A-Za-z0-9_-]{1,32}")
_CHUNK = 500
_MAX_CLAIM = 2000
_MAX_REASON = 500

_NOT_FOUND = "Not Found"
_INVALID = "The request wasn't valid."
_TOO_LARGE = "That request is too large."
_BUSY = "A sync is already running."
_VERSION = "Update Maestro on both machines to the same version."
_SAME_MACHINE = "These two copies share one machine id; give the always-on copy its own data."
_NO_KEY = "A sync key is needed."
_NO_BROWSERS = "Browser requests can't use this."
_DISK = "Maestro couldn't save the files it received."
_CANT_READ = "Maestro couldn't read the files it needed to send."
_FAILED = "Maestro couldn't finish that sync request."
_NOT_YOURS = "This job isn't yours to send."
_OURS = "This job belongs to your laptop."
_CANT_APPLY = "Maestro couldn't apply this job."
_UNREADABLE = "This job couldn't be read."
_NOT_HERE = "This job isn't on your laptop."
_MOVING = "This job is moving to your bot; make the change there once it arrives."
_WRONG_JOB = "That doesn't belong to this job."
_BAD_PAYLOAD = "This request wasn't valid."
_NO_TAKE_OVER = "A job on your laptop is handed over from your laptop."
_UNKNOWN_KIND = "Maestro doesn't know that kind of request."
_NOT_REPEATABLE = "This request can't be repeated."


class _Refused(Exception):
    """A refusal that carries its own machine-readable reason next to the sentence."""

    def __init__(self, status_code: int, detail: str, reason: str):
        super().__init__(detail)
        self.status_code, self.detail, self.reason = status_code, detail, reason


class _SyncRoute(APIRoute):
    """Sanitized validation errors, fixed 500s, and the single-flight lock released before the
    response goes out."""

    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            try:
                return await original(request)
            except RequestValidationError:
                raise HTTPException(422, detail=_INVALID) from None
            except _Refused as refusal:
                return JSONResponse(status_code=refusal.status_code,
                                    content={"detail": refusal.detail, "reason": refusal.reason})
            except (StarletteHTTPException, hooks.NotOwnedHere):
                raise
            except Exception:
                logger.error("A sync request failed.")
                raise HTTPException(500, detail=_FAILED) from None
            finally:
                if getattr(request.state, "sync_lock", False):
                    request.state.sync_lock = False
                    _LOCK.release()

        return handler


router = APIRouter(prefix="/api/sync", tags=["sync"], route_class=_SyncRoute)


@dataclass(frozen=True)
class PeerInfo:
    machine_id: str


def _check_key(request: Request, key: str) -> None:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    supplied = token if scheme.lower() == "bearer" else ""
    if not hmac.compare_digest(supplied.encode(), key.encode()):
        raise HTTPException(401, detail=_NO_KEY, headers={"WWW-Authenticate": "Bearer"})


def _check_version(request: Request, db: Session) -> PeerInfo:
    parts = request.headers.get("x-maestro-sync", "").split(":")
    if len(parts) != 3 or not _MACHINE_ID.fullmatch(parts[2]):
        raise _Refused(409, _VERSION, "version")
    protocol, revision, peer_id = parts
    if protocol != str(status.SYNC_PROTOCOL) or revision != version.get_version(db).schema_revision:
        raise _Refused(409, _VERSION, "version")
    home_id = status.machine_id(db)
    db.commit()  # the first call stores this copy's id
    if peer_id == home_id:
        raise _Refused(409, _SAME_MACHINE, "machine")
    return PeerInfo(peer_id)


def _require_sync(request: Request, db: Annotated[Session, Depends(get_db)]) -> PeerInfo:
    key = status.read_key()
    if key is None or status.is_remote():
        raise HTTPException(404, detail=_NOT_FOUND)
    if "origin" in request.headers:
        raise HTTPException(403, detail=_NO_BROWSERS)
    _check_key(request, key)
    peer = _check_version(request, db)
    if not _LOCK.acquire(blocking=False):
        raise _Refused(409, _BUSY, "busy")
    request.state.sync_lock = True
    return peer


Peer = Annotated[PeerInfo, Depends(_require_sync)]
DB = Annotated[Session, Depends(get_db)]


async def _json_body(request: Request, _peer: Peer) -> dict:
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise HTTPException(413, detail=_TOO_LARGE)
    chunks, total = [], 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_BODY_BYTES:
            raise HTTPException(413, detail=_TOO_LARGE)
        chunks.append(chunk)
    try:
        value = json.loads(b"".join(chunks))
    except (ValueError, RecursionError):
        raise HTTPException(422, detail=_INVALID) from None
    if not isinstance(value, dict):
        raise HTTPException(422, detail=_INVALID)
    return value


Body = Annotated[dict, Depends(_json_body)]


def _parse(model: type[Model], body: object) -> Model:
    try:
        return model.model_validate(body)
    except ValidationError:
        raise HTTPException(422, detail=_INVALID) from None


def _uuid(raw: object) -> uuid.UUID:
    try:
        return uuid.UUID(str(raw))
    except ValueError:
        raise HTTPException(422, detail=_INVALID) from None


@contextmanager
def _as_sync_apply(db: Session) -> Iterator[None]:
    """Writes that move ownership are the sync's own: the guard stands aside inside."""
    previous = db.info.get("sync_apply")
    db.info["sync_apply"] = True
    try:
        yield
    finally:
        if previous is None:
            db.info.pop("sync_apply", None)
        else:
            db.info["sync_apply"] = previous


def _profile_rev(db: Session) -> int:
    return db.scalar(select(SyncState.value).where(SyncState.name == "profile_rev")) or 0


def _owned_here_clause(db: Session):
    return or_(Job.owner_machine.is_(None), Job.owner_machine == status.machine_id(db))


def _disk_error() -> HTTPException:
    logger.warning("A sync request couldn't save the files it received.")
    return HTTPException(500, detail=_DISK)


# ------------------------------------------------------------------------------ read routes


@router.get("/hello")
def hello(peer: Peer, db: DB):
    return {"protocol": status.SYNC_PROTOCOL, "schema_revision": version.get_version(db).schema_revision,
            "machine_id": status.machine_id(db), "profile_rev": _profile_rev(db)}


@router.get("/profile")
def get_profile(peer: Peer, db: DB, since: Annotated[int | None, Query(ge=0)] = None):
    """The profile bundle, or ``unchanged``. Without ``since`` the peer has never applied one."""
    if since is not None and _profile_rev(db) <= since:
        return {"unchanged": True}
    try:
        return profile_bundle.export_profile(db)
    except (ValueError, OSError):
        raise HTTPException(500, detail=_CANT_READ) from None


def _export(db: Session, job_ids: list[uuid.UUID]) -> tuple[list[dict], int]:
    """Bundles of the jobs that can be sent, and how many could not (too large, a symlink)."""
    bundles, skipped = [], 0
    for job_id in job_ids:
        try:
            bundles.append(jobs_bundle.export_job(db, job_id))
        except (ValueError, LookupError):
            skipped += 1
        except OSError:
            raise HTTPException(500, detail=_CANT_READ) from None
    return bundles, skipped


def _page(rows: list, limit: int) -> tuple[list, bool]:
    """The first ``limit`` rows, extended to the end of the last revision they share: one flush
    stamps several jobs alike, and ``since`` skips a whole revision."""
    end = min(limit, len(rows))
    while 0 < end < len(rows) and rows[end].sync_rev == rows[end - 1].sync_rev:
        end += 1
    return rows[:end], end < len(rows)


def _tombstones(db: Session, since: int, upto: int | None) -> list[dict]:
    query = select(SyncTombstone).where(SyncTombstone.rev > since).order_by(SyncTombstone.rev)
    if upto is not None:
        query = query.where(SyncTombstone.rev <= upto)
    return [{"job_id": row.job_id.hex, "rev": row.rev} for row in db.scalars(query)]


@router.get("/jobs")
def get_jobs(peer: Peer, db: DB, since: Annotated[int, Query(ge=0)] = 0,
             limit: Annotated[int, Query(ge=1, le=100)] = 20):
    rows = db.execute(select(Job.id, Job.sync_rev).where(
        _owned_here_clause(db), Job.sync_rev > since).order_by(Job.sync_rev, Job.id)).all()
    page, more = _page(rows, limit)
    bundles, skipped = _export(db, [row.id for row in page])
    next_since = page[-1].sync_rev if page else since
    tombstones = _tombstones(db, since, next_since if more else None)
    if not more and tombstones:
        next_since = max(next_since, tombstones[-1]["rev"])
    return {"bundles": bundles, "tombstones": tombstones, "next_since": next_since, "more": more,
            "skipped": skipped}


# ------------------------------------------------------------------------------- POST /jobs


class _TombstoneIn(BaseModel):
    job_id: uuid.UUID
    rev: StrictInt


class _JobsPush(BaseModel):
    bundles: list[dict[str, Any]] = []
    tombstones: list[_TombstoneIn] = []


def _bundle_job_id(bundle: dict) -> uuid.UUID | None:
    try:
        return uuid.UUID(bundle["job_id"])
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def _refusal_of(db: Session, peer: PeerInfo, bundle: dict, job_id: uuid.UUID | None) -> str | None:
    """Why this bundle may not be stored here, or None."""
    if job_id is None:
        return _UNREADABLE
    if bundle.get("owner") != peer.machine_id:
        return _NOT_YOURS
    owner = db.execute(select(Job.owner_machine).where(Job.id == job_id)).one_or_none()
    if owner is not None and owner[0] != peer.machine_id:
        return _OURS
    return None


def _store(db: Session, peer: PeerInfo, bundle: dict, found: dict) -> None:
    job_id = _bundle_job_id(bundle)
    shown = job_id.hex if job_id else None
    reason = _refusal_of(db, peer, bundle, job_id)
    outcome = None
    if reason is None:
        try:
            outcome = duplicates.apply_replica(
                db, bundle, sender_machine=peer.machine_id,
                max_bytes=jobs_bundle.DEFAULT_MAX_BYTES)
        except ValueError:
            reason = _CANT_APPLY
        except OSError:
            db.rollback()
            raise _disk_error() from None
    if outcome is None:
        found["refused"].append({"job_id": shown, "reason": reason})
        return
    if outcome.kind != "laptop":
        found["applied"].append(shown)
    if outcome.kind != "applied":
        found["duplicates"].append({"job_id": shown, "kept": outcome.kind,
                                    "local_id": outcome.local_id.hex})


def _drop_replica(db: Session, peer: PeerInfo, job_id: uuid.UUID) -> bool:
    owner = db.execute(select(Job.owner_machine).where(Job.id == job_id)).one_or_none()
    if owner is None or owner[0] != peer.machine_id:
        return False  # only the sender's own jobs can be deleted by the sender
    jobs_bundle.apply_tombstone(db, job_id)
    return True


@router.post("/jobs")
def post_jobs(peer: Peer, db: DB, body: Body):
    push = _parse(_JobsPush, body)
    found: dict[str, list] = {"applied": [], "duplicates": [], "refused": []}
    for bundle in push.bundles:
        _store(db, peer, bundle, found)
    found["deleted"] = [t.job_id.hex for t in push.tombstones if _drop_replica(db, peer, t.job_id)]
    return found


# --------------------------------------------------------------------------- POST /ownership


class _JobIds(BaseModel):
    job_ids: list[str]


@router.post("/ownership")
def post_ownership(peer: Peer, db: DB, body: Body):
    asked = {raw: _uuid(raw) for raw in _parse(_JobIds, body).job_ids}
    owners: dict[uuid.UUID, str | None] = {}
    ids = list(set(asked.values()))
    for start in range(0, len(ids), _CHUNK):
        owners.update(db.execute(select(Job.id, Job.owner_machine)
                                 .where(Job.id.in_(ids[start:start + _CHUNK]))).tuples().all())
    home_id = status.machine_id(db)
    return {raw: _label(owners, job_id, home_id) for raw, job_id in asked.items()}


def _label(owners: dict, job_id: uuid.UUID, home_id: str) -> str:
    if job_id not in owners:
        return "gone"
    return "home" if owners[job_id] in (None, home_id) else "remote"


# ------------------------------------------------------------------------------- requests


def _shown(row: SyncRequest) -> dict:
    return {"id": row.id.hex, "kind": row.kind, "job_id": row.job_id.hex if row.job_id else None,
            "payload": row.payload_json, "created_at": row.created_at.isoformat()}


@router.get("/requests")
def get_requests(peer: Peer, db: DB):
    """This copy's pending requests for jobs the peer owns, marked sent."""
    rows = db.scalars(
        select(SyncRequest).join(Job, Job.id == SyncRequest.job_id)
        .where(SyncRequest.origin == "local", SyncRequest.status == "pending",
               Job.owner_machine == peer.machine_id)
        .order_by(SyncRequest.created_at, SyncRequest.id)).all()
    shown = [_shown(row) for row in rows]
    for row in rows:
        row.status = "sent"
    db.commit()
    return shown


class _RequestIn(BaseModel):
    id: uuid.UUID
    kind: str
    job_id: uuid.UUID | None = None
    payload: dict[str, Any]
    created_at: AwareDatetime


class _RequestsPush(BaseModel):
    requests: list[_RequestIn]


class _Refusal(Exception):
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


def _payload(model: type[Model], item: _RequestIn) -> Model:
    try:
        return model.model_validate(item.payload)
    except ValidationError:
        raise _Refusal(_BAD_PAYLOAD) from None


def _own_job(db: Session, job_id: uuid.UUID | None) -> Job:
    """The job a request is about, when it is this copy's and not on its way out."""
    job = db.get(Job, job_id) if job_id is not None else None
    if job is None or job.owner_machine not in (None, status.machine_id(db)):
        raise _Refusal(_NOT_HERE)
    if job.handover == "offered":
        raise _Refusal(_MOVING)
    return job


def _apply_transition(db: Session, item: _RequestIn) -> None:
    job = _own_job(db, item.job_id)
    body = _payload(_TransitionPayload, item)
    proposal = db.get(ApplicationProposal, body.proposal_id)
    if proposal is None or proposal.job_id != job.id:
        raise _Refusal(_WRONG_JOB)
    consent = body.consent.model_dump(exclude_unset=True) if body.consent else None
    try:
        proposals.transition(db, proposal, body.to, consent=consent, reason=body.reason)
    except proposals.TransitionError as rule:
        raise _Refusal(str(rule)) from None


def _patch_values(fields: dict) -> dict:
    try:
        patch = ApplicationPatch.model_validate(fields)
    except ValidationError:
        raise _Refusal(_BAD_PAYLOAD) from None
    values = {name: getattr(patch, name) for name in patch.model_fields_set}
    if not values or set(fields) - {"status", "notes"} or values.get("status", "x") is None:
        raise _Refusal(_BAD_PAYLOAD)
    return values


def _apply_patch(db: Session, item: _RequestIn) -> None:
    job = _own_job(db, item.job_id)
    body = _payload(_PatchPayload, item)
    values = _patch_values(body.fields)
    application = db.get(Application, body.application_id)
    if application is None or application.job_id != job.id:
        raise _Refusal(_WRONG_JOB)
    application_status.apply_status_and_notes(db, application, values)


def _apply_addition(db: Session, item: _RequestIn) -> None:
    claim = item.payload.get("claim")
    if not isinstance(claim, str) or not claim.strip() or len(claim) > _MAX_CLAIM:
        raise _Refusal(_BAD_PAYLOAD)
    known = {normalize_term(text) for text in db.scalars(select(KBPoint.text).where(
        KBPoint.provenance == "user_cannot_confirm")) if text}
    if normalize_term(claim) in known:
        return
    holder = tailoring_session._cannot_confirm_holder(db)
    db.add(KBPoint(entity_id=holder.id, text=claim.strip(), state="retired",
                   origin="gap_elicitation", provenance="user_cannot_confirm"))


def _refuse_take_over(db: Session, item: _RequestIn) -> None:
    raise _Refusal(_NO_TAKE_OVER)


_APPLIERS = {"proposal_transition": _apply_transition, "application_patch": _apply_patch,
             "profile_addition": _apply_addition, "take_over": _refuse_take_over}


def _record(item: _RequestIn, outcome: str, reason: str | None) -> SyncRequest:
    return SyncRequest(id=item.id, job_id=item.job_id, kind=item.kind[:32],
                       payload_json=item.payload, origin="remote", status=outcome, reason=reason,
                       created_at=item.created_at, answered_at=utcnow())


def _settle(db: Session, item: _RequestIn) -> tuple[str, str | None]:
    """Apply one request; its record commits with the change itself."""
    applier = _APPLIERS.get(item.kind)
    try:
        if applier is None:
            raise _Refusal(_UNKNOWN_KIND)
        db.add(_record(item, "applied", None))
        applier(db, item)
        db.commit()
        return "applied", None
    except (_Refusal, hooks.NotOwnedHere) as refusal:
        db.rollback()
        reason = refusal.reason if isinstance(refusal, _Refusal) else str(refusal)
        db.add(_record(item, "refused", reason))
        db.commit()
        return "refused", reason


def _answer(db: Session, item: _RequestIn) -> dict:
    earlier = db.get(SyncRequest, item.id)
    if earlier is not None:  # a resend: answer as before, apply nothing
        mine = earlier.origin == "remote"
        outcome, reason = (earlier.status, earlier.reason) if mine else ("refused", _NOT_REPEATABLE)
    else:
        outcome, reason = _settle(db, item)
    return {"id": item.id.hex, "status": outcome, "reason": reason}


@router.post("/requests")
def post_requests(peer: Peer, db: DB, body: Body):
    """Apply the peer's requests in the order they were made, under the normal rules."""
    items = sorted(_parse(_RequestsPush, body).requests, key=lambda i: (i.created_at, i.id))
    return [_answer(db, item) for item in items]


class _ResultIn(BaseModel):
    id: uuid.UUID
    status: Literal["applied", "refused"]
    reason: str | None = None


class _ResultsPush(BaseModel):
    results: list[_ResultIn]


@router.post("/request-results")
def post_request_results(peer: Peer, db: DB, body: Body):
    updated = 0
    for result in _parse(_ResultsPush, body).results:
        row = db.get(SyncRequest, result.id)
        if row is None or row.origin != "local" or row.status != "sent":
            continue
        row.status, row.answered_at = result.status, utcnow()
        row.reason = (result.reason or "")[:_MAX_REASON] or None
        updated += 1
    db.commit()
    return {"updated": updated}


# ------------------------------------------------------------------------------- handovers


@router.get("/handover/offers")
def get_offers(peer: Peer, db: DB):
    ids = list(db.scalars(select(Job.id).where(
        _owned_here_clause(db), Job.handover == "offered").order_by(Job.sync_rev, Job.id)))
    bundles, skipped = _export(db, ids)
    return {"bundles": bundles, "skipped": skipped}


@router.post("/handover/commit")
def post_commit(peer: Peer, db: DB, body: Body):
    asked = [_uuid(raw) for raw in _parse(_JobIds, body).job_ids]
    home_id = status.machine_id(db)
    committed = []
    with _as_sync_apply(db):
        for job in (db.get(Job, job_id) for job_id in asked):
            if job is not None and job.handover == "offered" and job.owner_machine in (None, home_id):
                job.owner_machine, job.handover = peer.machine_id, None
                committed.append(job.id.hex)
        db.commit()
    return {"job_ids": committed}


class _BundlesPush(BaseModel):
    bundles: list[dict[str, Any]]


def _take_back(db: Session, peer: PeerInfo, bundle: dict, found: dict) -> None:
    job_id = _bundle_job_id(bundle)
    shown = job_id.hex if job_id else None
    reason = _refusal_of(db, peer, bundle, job_id)
    if reason is None and db.get(Job, job_id) is None:
        reason = _NOT_HERE
    if reason is None:
        reason = _store_returned(db, peer, bundle, job_id)
    if reason is None:
        found["job_ids"].append(shown)
    else:
        found["refused"].append({"job_id": shown, "reason": reason})


def _store_returned(db: Session, peer: PeerInfo, bundle: dict, job_id: uuid.UUID) -> str | None:
    try:
        jobs_bundle.apply_job(db, bundle, sender_machine=status.machine_id(db),
                              max_bytes=jobs_bundle.DEFAULT_MAX_BYTES)
    except (ValueError, jobs_bundle.DuplicateJob):
        return _CANT_APPLY
    except OSError:
        db.rollback()
        raise _disk_error() from None
    with _as_sync_apply(db):
        job = db.get(Job, job_id)
        job.owner_machine, job.handover = None, None
        db.commit()
    return None


@router.post("/handover/return")
def post_return(peer: Peer, db: DB, body: Body):
    found: dict[str, list] = {"job_ids": [], "refused": []}
    for bundle in _parse(_BundlesPush, body).bundles:
        _take_back(db, peer, bundle, found)
    return found


# ------------------------------------------------------------------------------------ runs


class _RunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    automation: str = Field(min_length=1, max_length=40)
    outcome: RunOutcome
    agent: str | None = None
    finished_at: AwareDatetime
    counts: dict[str, Annotated[StrictInt, Field(ge=0)]] = {}
    digest: str = ""
    job_ids: list[uuid.UUID] = Field(default=[], max_length=MAX_JOB_IDS)


class _RunsPush(BaseModel):
    runs: list[_RunIn]


def _keep_run(db: Session, peer: PeerInfo, run: _RunIn) -> bool:
    row = db.get(AgentRun, run.id)
    if row is not None and row.machine != peer.machine_id:
        return False  # a run that happened here is never overwritten
    row = row or AgentRun(id=run.id, machine=peer.machine_id)
    row.automation, row.outcome, row.agent = run.automation, run.outcome, run.agent
    row.finished_at, row.counts = run.finished_at, dict(run.counts)
    row.digest, row.job_ids = run.digest.strip()[:MAX_DIGEST], [str(i) for i in run.job_ids]
    db.add(row)
    return True


@router.post("/runs")
def post_runs(peer: Peer, db: DB, body: Body):
    """Add or refresh the peer's run log rows; never deletes, never prunes."""
    kept = [run.id.hex for run in _parse(_RunsPush, body).runs if _keep_run(db, peer, run)]
    db.commit()
    return {"ids": kept}
