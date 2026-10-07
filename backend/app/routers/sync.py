"""Home's side of the sync channel (split-ownership design, Part B).

The always-on copy drives every request; this copy only answers. Peer routes under ``/api/sync/``
(not ``/round`` or ``/enroll``) are sealed with the sync key: a bare 404 while sync is off or
this copy is remote, a bare 404 for any ``Origin`` (a browser cannot seal, and a 403 would show
that sync is on), then the seal, then the protocol check and the single-flight lock.
A failed seal is the same bare 404, including a seal stamped before this process
started. ``/round`` and ``/api/sync-setup`` keep the Origin 403.
``/enroll`` is sealed here with the one-time code, not the sync key: the header mac is
checked before anything else, and every refusal is the same bare 404. Enroll does not take
the single-flight lock; the code is claimed once, in its own transaction.
Local setup is under ``/api/sync-setup`` and is not sealed. Nothing here logs or echoes a key, a
bundle, a request body, the AI key or the job-site password: every response and stored reason is
a fixed sentence or one of the rule sentences the services already use, never ``str(exc)``.
"""

import asyncio
import json
import logging
import re
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from typing import Annotated, Any, Literal, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, ValidationError
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import ClientDisconnect

from app.config import settings
from app.db import get_db
from app.models.agent_run import AgentRun
from app.models.job import Job
from app.models.sync import SyncRequest, SyncState, SyncTombstone
from app.models.types import utcnow
from app.schemas.agent_runs import MAX_DIGEST, MAX_JOB_IDS, RunCountKey, RunOutcome
from app.services.sync import (
    duplicates,
    hooks,
    jobs_bundle,
    offers,
    pairing,
    profile_bundle,
    request_apply,
    requests,
    seal,
    status,
    wire,
)
from app.services.sync import round as sync_round

logger = logging.getLogger(__name__)

Model = TypeVar("Model", bound=BaseModel)

MAX_BODY_BYTES = 100 * 1024 * 1024
PAGE_BYTES = 50 * 1024 * 1024
_CHUNK_TIMEOUT = 30.0
_LOCK = pairing.LOCK
_MACHINE_ID = re.compile(r"[A-Za-z0-9_-]{1,32}")
_JOB_HEX = re.compile(r"[0-9a-f]{32}")
_CURSOR_END = "f" * 32
_CHUNK = 500

_NOT_FOUND = "Not Found"
_INVALID = "The request wasn't valid."
_TOO_LARGE = "That request is too large."
_BUSY = "A sync is already running."
_VERSION = "Update Maestro on both machines to the same version."
_SAME_MACHINE = "These two copies share one machine id; give the always-on copy its own data."
_NO_BROWSERS = "Browser requests can't use this."
_FAILED = "Maestro couldn't finish that sync request."
_NOT_YOURS = "This job isn't yours to send."
_OURS = "This job belongs to your laptop."
_LAPTOP_DELETED = "The laptop deleted this job."
_CANT_APPLY = "Maestro couldn't apply this job."
_UNREADABLE = "This job couldn't be read."
_NOT_HERE = "This job isn't on your laptop."
_TIMEOUT = "The request took too long to arrive."
_RETRY = "This job's text matches a job that is still changing; Maestro will try again."
_REFUSED = "A sync request was refused."
_SEAL_GAP = 60.0
_SEAL_SOURCES = 1024
_REPLAY = seal.ReplayCache()
_SEAL_LOCK = threading.Lock()
_seal_seen: OrderedDict[str, float] = OrderedDict()
# Captured once. A seal from before this process started is a replay the
# in-memory cache can no longer see. A remote clock running behind may see
# bare 404s for up to the skew after a laptop restart; its next round after
# the clock catches up works.
_STARTED_AT = time.time()


class _Refused(Exception):
    """A refusal that carries its own machine-readable reason next to the sentence."""

    def __init__(self, status_code: int, detail: str, reason: str):
        super().__init__(detail)
        self.status_code, self.detail, self.reason = status_code, detail, reason


def _refusal_reply(request: Request, refusal: _Refused | pairing.Refused) -> JSONResponse:
    content = {"detail": refusal.detail, "reason": refusal.reason}
    if request.url.path.startswith("/api/sync-setup/"):
        transient = refusal.status_code >= 500 or refusal.reason == "busy"
        content.update(ok=False, outcome="transient" if transient else "needs_person")
    return JSONResponse(status_code=refusal.status_code, content=content)


def _release_lock(request: Request) -> None:
    if getattr(request.state, "sync_lock", False):
        request.state.sync_lock = False
        _LOCK.release()


def _peer_sealed(path: str) -> bool:
    if not path.startswith("/api/sync/"):
        return False
    name = path.removeprefix("/api/sync/").split("/", 1)[0]
    return name not in {"round", "enroll"}


def _bare_404() -> Response:
    return Response(status_code=404)


def _home_key() -> str | None:
    key = status.read_key()
    if key is None or status.is_remote():
        return None
    return key


def _forwarded_source(header: str) -> str:
    """The last hop. A trusted proxy appends itself; earlier entries are the client's claim."""
    return header.rsplit(",", 1)[-1].strip()


def _remember_source(source: str, now: float) -> None:
    _seal_seen[source] = now
    _seal_seen.move_to_end(source)
    if len(_seal_seen) > _SEAL_SOURCES:
        _seal_seen.popitem(last=False)


def _due(source: str, now: float) -> bool:
    with _SEAL_LOCK:
        previous = _seal_seen.get(source)
        if previous is not None and now - previous < _SEAL_GAP:
            return False
        _remember_source(source, now)
        return True


def _note_refusal(request: Request) -> None:
    """One fixed line per forwarded source per minute. The header value is never written."""
    source = _forwarded_source(request.headers.get("x-forwarded-for", ""))
    if _due(source, time.monotonic()):
        logger.info(_REFUSED)


def _or_bare_404(request: Request, call):
    """A seal that raises anything is the same empty 404 as sync being off. Nothing is logged
    but the throttled line: the exception text can echo header bytes."""
    try:
        return call()
    except Exception:
        _note_refusal(request)
        return _bare_404()


def _seal_outgoing(key: str, rid: str, response: Response) -> Response:
    header, wire = seal.seal_response(key, rid, response.status_code, response.body)
    return Response(content=wire, status_code=response.status_code, headers={seal.HEADER: header})


def _sealed_detail(key: str, rid: str, status_code: int, detail: str) -> Response:
    body = json.dumps({"detail": detail}).encode()
    return _seal_outgoing(key, rid, Response(content=body, status_code=status_code))


def _header_ok(request: Request, key: str):
    def check():
        return seal.check_header(
            key, request.method, request.url.path, request.url.query,
            request.headers.get(seal.HEADER, ""), request.headers.get("x-maestro-sync", ""),
            replay=_REPLAY, not_before=_STARTED_AT)

    return _or_bare_404(request, check)


def _declared_too_big(request: Request) -> bool:
    declared = request.headers.get("content-length", "")
    return bool(declared.isdigit() and int(declared) > MAX_BODY_BYTES)


def _opened_body(request: Request, key: str, ok: seal.HeaderOk, wire: bytes):
    def open_body():
        return ok, seal.open_request(key, ok, wire)

    return _or_bare_404(request, open_body)


async def _capped_body(request: Request, key: str, rid: str):
    if _declared_too_big(request):
        return _sealed_detail(key, rid, 413, _TOO_LARGE)
    try:
        return await _read_body(request)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else _INVALID
        return _sealed_detail(key, rid, exc.status_code, detail)
    except ClientDisconnect:
        logger.info("A sync peer hung up.")
        return _seal_outgoing(key, rid, Response(status_code=499))


async def _unseal(request: Request, key: str):
    ok = _header_ok(request, key)
    if isinstance(ok, Response):
        return ok
    wire = await _capped_body(request, key, ok.rid)
    if isinstance(wire, Response):
        return wire
    return _opened_body(request, key, ok, wire)


async def _guarded(original, request: Request):
    try:
        return await original(request)
    except RequestValidationError:
        return JSONResponse(status_code=422, content={"detail": _INVALID})
    except (_Refused, pairing.Refused) as refusal:
        return _refusal_reply(request, refusal)
    except hooks.NotOwnedHere as exc:
        return JSONResponse(status_code=409, content={"detail": str(exc), "owner": exc.owner})
    except StarletteHTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    except ClientDisconnect:
        logger.info("A sync peer hung up.")
        return Response(status_code=499)
    except Exception:
        logger.error("A sync request failed.")
        return JSONResponse(status_code=500, content={"detail": _FAILED})


async def _run_sealed(original, request: Request):
    key = _home_key()
    if key is None:
        return _bare_404()
    if "origin" in request.headers:
        return _bare_404()
    opened = await _unseal(request, key)
    if isinstance(opened, Response):
        return opened
    ok, plain = opened
    request.state.sync_plain = plain
    request.state.sync_opened = True
    try:
        response = await _guarded(original, request)
    finally:
        _release_lock(request)
    return _seal_outgoing(key, ok.rid, response)


async def _run_plain(original, request: Request):
    try:
        return await original(request)
    except RequestValidationError:
        raise HTTPException(422, detail=_INVALID) from None
    except (_Refused, pairing.Refused) as refusal:
        return _refusal_reply(request, refusal)
    except (StarletteHTTPException, hooks.NotOwnedHere):
        raise
    except ClientDisconnect:
        logger.info("A sync peer hung up.")
        return Response(status_code=499)
    except Exception:
        logger.error("A sync request failed.")
        raise HTTPException(500, detail=_FAILED) from None
    finally:
        _release_lock(request)


class _SyncRoute(APIRoute):
    """Sanitized validation errors, fixed 500s, and the single-flight lock released before the
    response goes out. Peer routes are sealed; setup, round, and enroll are not."""

    def get_route_handler(self):
        original = super().get_route_handler()
        sealed = _peer_sealed(self.path)

        async def handler(request: Request):
            if sealed:
                return await _run_sealed(original, request)
            return await _run_plain(original, request)

        return handler


router = APIRouter(prefix="/api/sync", tags=["sync"], route_class=_SyncRoute)
setup_router = APIRouter(prefix="/api/sync-setup", tags=["sync setup"], route_class=_SyncRoute)


@dataclass(frozen=True)
class PeerInfo:
    machine_id: str


def _check_version(request: Request, db: Session) -> PeerInfo:
    parts = request.headers.get("x-maestro-sync", "").split(":")
    if len(parts) != 3 or not _MACHINE_ID.fullmatch(parts[2]):
        raise _Refused(409, _VERSION, "version")
    protocol, revision, peer_id = parts
    if protocol != str(status.SYNC_PROTOCOL) or revision != status.schema_revision(db):
        raise _Refused(409, _VERSION, "version")
    home_id = status.machine_id(db)
    db.commit()  # the first call stores this copy's id
    if peer_id == home_id:
        raise _Refused(409, _SAME_MACHINE, "machine")
    return PeerInfo(peer_id)


def _require_sync(request: Request, db: Annotated[Session, Depends(get_db)]) -> PeerInfo:
    """Version and the lock. The route class has already unsealed a peer request."""
    if not getattr(request.state, "sync_opened", False):
        raise HTTPException(404, detail=_NOT_FOUND)
    peer = _check_version(request, db)
    if not _LOCK.acquire(blocking=False):
        raise _Refused(409, _BUSY, "busy")
    request.state.sync_lock = True
    return peer


Peer = Annotated[PeerInfo, Depends(_require_sync)]
DB = Annotated[Session, Depends(get_db)]


def _take_lock(request: Request) -> None:
    if not _LOCK.acquire(blocking=False):
        raise _Refused(409, _BUSY, "busy")
    request.state.sync_lock = True


def _mac_ok(request: Request, secret: str | None):
    """The enroll header mac, before a lock, a key read, or the body."""
    try:
        ok = seal.check_header(
            secret or pairing._STAND_IN, request.method, request.url.path, request.url.query,
            request.headers.get(seal.HEADER, ""), request.headers.get("x-maestro-sync", ""),
            replay=None, label=seal.ENROLL_TO_HOME, not_before=_STARTED_AT)
    except seal.Broken:
        return _bare_404()
    if pairing.seen_enroll(ok.rid, request.headers.get(seal.HEADER, "")):
        return _bare_404()
    return ok


def _enrollment_key(request: Request):
    path = status.key_path()
    if not path.is_file() or path.is_symlink():
        return _bare_404()
    if "origin" in request.headers:
        return _bare_404()
    key = status.read_key()
    if key is None or settings.sync_remote_url:
        return _bare_404()
    return key


def _require_enrollment(request: Request, db: DB):
    secret = pairing.live_digest(db)
    opened = _mac_ok(request, secret)
    if isinstance(opened, Response):
        return opened
    key = _enrollment_key(request)
    if isinstance(key, Response):
        return key
    request.state.enroll_header = opened
    request.state.enroll_secret = secret
    request.state.enroll_key = key
    return key


async def _enroll_body(request: Request, gate: Annotated[str | Response, Depends(_require_enrollment)]):
    if not isinstance(gate, str):
        return gate
    try:
        return await _read_body(request)
    except (HTTPException, ClientDisconnect):
        return _bare_404()


def _opened_enroll(db: DB, secret: str, ok: seal.HeaderOk, wire: bytes) -> bool:
    try:
        seal.open_request(secret, ok, wire, label=seal.ENROLL_TO_HOME)
    except seal.Broken:
        return False
    return pairing.complete_pairing(db, secret)


def _enroll_answer(secret: str, rid: str, key: str) -> Response:
    body = json.dumps({"key": key}).encode()
    header, wire = seal.seal_response(secret, rid, 200, body, label=seal.ENROLL_TO_REMOTE)
    return Response(content=wire, status_code=200, headers={seal.HEADER: header})


def _finish_enroll(request: Request, db: Session, wire: bytes) -> Response:
    secret = request.state.enroll_secret
    opened = request.state.enroll_header
    if not isinstance(secret, str) or not isinstance(opened, seal.HeaderOk):
        return _bare_404()
    if not _opened_enroll(db, secret, opened, wire):
        return _bare_404()
    logger.info("A copy fetched the sync key.")
    return _enroll_answer(secret, opened.rid, request.state.enroll_key)


@router.post("/enroll")
def post_enroll(request: Request, db: DB, wire: Annotated[bytes | Response, Depends(_enroll_body)]):
    if isinstance(wire, Response):
        return wire
    return _finish_enroll(request, db, wire)


def _require_setup_caller(request: Request) -> None:
    if "origin" in request.headers:
        raise HTTPException(403, detail=_NO_BROWSERS)
    if not settings.sync_remote_url:
        raise HTTPException(404, detail=_NOT_FOUND)
    _take_lock(request)


def _setup_refusal(refusal: pairing.Refused) -> JSONResponse:
    return JSONResponse(status_code=refusal.status_code, content={
        "ok": False, "detail": refusal.detail, "outcome": refusal.outcome})


def _code_from(raw: bytes) -> str:
    try:
        body = json.loads(raw) if raw else None
    except (ValueError, UnicodeError):
        raise pairing.Refused(422, "The request wasn't valid.") from None
    code = body.get("code") if isinstance(body, dict) else None
    if not isinstance(code, str) or len(code) > 64:
        raise pairing.Refused(422, "The request wasn't valid.")
    return code


async def _submitted_body(request: Request) -> bytes:
    return await request.body()


@setup_router.post("/enroll", dependencies=[Depends(_require_setup_caller)])
def post_setup_enroll(db: DB, raw: Annotated[bytes, Depends(_submitted_body)]):
    """Sync, so the blocking call to the laptop runs in the threadpool."""
    try:
        pairing.prepare_enroll()
        return pairing.enroll_here(db, _code_from(raw))
    except pairing.Refused as refusal:
        return _setup_refusal(refusal)


async def _read_body(request: Request) -> bytes:
    """The body in chunks; a peer that stalls between chunks is a 408, so it can't hold the lock."""
    chunks, total = [], 0
    stream = request.stream().__aiter__()
    while True:
        try:
            chunk = await asyncio.wait_for(stream.__anext__(), _CHUNK_TIMEOUT)
        except StopAsyncIteration:
            return b"".join(chunks)
        except TimeoutError:
            raise HTTPException(408, detail=_TIMEOUT) from None
        total += len(chunk)
        if total > MAX_BODY_BYTES:
            raise HTTPException(413, detail=_TOO_LARGE)
        chunks.append(chunk)


def _plaintext(request: Request) -> bytes | None:
    raw = getattr(request.state, "sync_plain", None)
    return raw if isinstance(raw, bytes) else None


async def _json_body(request: Request, _peer: Peer) -> dict:
    raw = _plaintext(request)
    if raw is None:
        if _declared_too_big(request):
            raise HTTPException(413, detail=_TOO_LARGE)
        raw = await _read_body(request)
    try:
        value = json.loads(raw)
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
    parsed = wire.uuid_of(raw)
    if parsed is None:
        raise HTTPException(422, detail=_INVALID)
    return parsed


def _profile_rev(db: Session) -> int:
    return db.scalar(select(SyncState.value).where(SyncState.name == "profile_rev")) or 0


def _disk_error() -> HTTPException:
    logger.warning("A sync request couldn't save the files it received.")
    return HTTPException(500, detail=wire.DISK)


# ------------------------------------------------------------------------------ read routes


@router.get("/hello")
def hello(peer: Peer, db: DB):
    return {"protocol": status.SYNC_PROTOCOL, "schema_revision": status.schema_revision(db),
            "machine_id": status.machine_id(db), "profile_rev": _profile_rev(db)}


@router.get("/profile")
def get_profile(peer: Peer, db: DB, since: Annotated[int | None, Query(ge=0)] = None):
    """The profile bundle, or ``unchanged``. Without ``since`` the peer has never applied one."""
    if since is not None and _profile_rev(db) <= since:
        return {"unchanged": True}
    try:
        return profile_bundle.export_profile(db)
    except (ValueError, OSError):
        raise HTTPException(500, detail=wire.CANT_READ) from None


def _export(db: Session, job_ids: list[uuid.UUID]) -> tuple[list[dict], int]:
    """Bundles of the jobs that can be sent, and how many could not (too large, a symlink)."""
    bundles, skipped = [], 0
    for job_id in job_ids:
        try:
            bundles.append(jobs_bundle.export_job(db, job_id))
        except (ValueError, LookupError):
            skipped += 1
        except OSError:
            raise HTTPException(500, detail=wire.CANT_READ) from None
    return bundles, skipped


def _export_page(db: Session, rows: list, limit: int) -> tuple[list[dict], int, int]:
    """Bundles of the leading rows, up to ``limit`` and the byte budget but never fewer than one
    row. Returns them, how many could not be sent, and how many rows were taken."""
    bundles, skipped, used, taken = [], 0, 0, 0
    for row in rows[:limit]:
        found, left_out = _export(db, [row.id])
        size = jobs_bundle.weight(found[0]) if found else 0
        if taken and used + size > PAGE_BYTES:
            break
        bundles.extend(found)
        skipped, used, taken = skipped + left_out, used + size, taken + 1
    return bundles, skipped, taken


def _tombstones(db: Session, since: int, upto: int | None) -> list[dict]:
    query = select(SyncTombstone).where(SyncTombstone.rev > since).order_by(SyncTombstone.rev)
    if upto is not None:
        query = query.where(SyncTombstone.rev <= upto)
    return [{"job_id": row.job_id.hex, "rev": row.rev} for row in db.scalars(query)]


def _parse_cursor(raw: str) -> tuple[int, str]:
    """``rev`` or ``rev:jobid``: the position after which the next page starts."""
    rev, _, ident = raw.partition(":")
    if not (rev.isdigit() and len(rev) <= 18) or (ident and not _JOB_HEX.fullmatch(ident)):
        raise HTTPException(422, detail=_INVALID)
    return int(rev), ident


def _cursor(rev: int, ident: str) -> str:
    return f"{rev}:{ident}" if ident else str(rev)


def _jobs_after(db: Session, rev: int, ident: str, limit: int) -> list:
    after = Job.sync_rev > rev
    if ident:
        after = or_(after, and_(Job.sync_rev == rev, Job.id > uuid.UUID(ident)))
    return db.execute(select(Job.id, Job.sync_rev).where(jobs_bundle.owned_clause(db), after)
                      .order_by(Job.sync_rev, Job.id).limit(limit + 1)).all()


@router.get("/jobs")
def get_jobs(peer: Peer, db: DB, since: Annotated[str, Query(max_length=64)] = "0",
             limit: Annotated[int, Query(ge=1, le=100)] = 20):
    """One page of this copy's jobs after the ``since`` cursor (``rev:jobid``, or a bare revision),
    in (revision, id) order, up to ``limit`` and ``PAGE_BYTES``. ``next_since`` is the cursor for
    the following page; tombstones ride the page that reaches their revision."""
    since_rev, ident = _parse_cursor(since)
    if hooks.stamp_unsynced_jobs(db):
        db.commit()  # release the write lock before the export reads the page
    rev = since_rev
    rows = _jobs_after(db, rev, ident, limit)
    bundles, skipped, taken = _export_page(db, rows, limit)
    more = taken < len(rows)
    if taken:
        rev, ident = rows[taken - 1].sync_rev, rows[taken - 1].id.hex
    tombstones = _tombstones(db, since_rev, rev if more else None)
    if not more and tombstones and tombstones[-1]["rev"] > rev:
        rev, ident = tombstones[-1]["rev"], _CURSOR_END
    return {"bundles": bundles, "tombstones": tombstones, "next_since": _cursor(rev, ident),
            "more": more, "skipped": skipped}


# ------------------------------------------------------------------------------- POST /jobs


class _TombstoneIn(BaseModel):
    job_id: uuid.UUID
    rev: StrictInt


class _JobsPush(BaseModel):
    bundles: list[dict[str, Any]] = []
    tombstones: list[_TombstoneIn] = []


def _deleted_here(db: Session, job_id: uuid.UUID, owner) -> bool:
    """A tombstone with no live row: the laptop deleted this id and has not saved it again."""
    return owner is None and db.get(SyncTombstone, job_id) is not None


def _refusal_of(db: Session, peer: PeerInfo, bundle: dict, job_id: uuid.UUID | None) -> str | None:
    """Why this bundle may not be stored here, or None."""
    if job_id is None:
        return _UNREADABLE
    if bundle.get("owner") != peer.machine_id:
        return _NOT_YOURS
    owner = db.execute(select(Job.owner_machine).where(Job.id == job_id)).one_or_none()
    if _deleted_here(db, job_id, owner):
        return _LAPTOP_DELETED
    if owner is not None and owner[0] != peer.machine_id:
        return _OURS
    return None


def _apply_one(db: Session, peer: PeerInfo, bundle: dict,
               job_id: uuid.UUID | None) -> tuple[duplicates.Outcome | None, str | None]:
    """The outcome of storing one bundle, or the sentence for refusing it."""
    reason = _refusal_of(db, peer, bundle, job_id)
    if reason is not None:
        return None, reason
    try:
        return duplicates.apply_replica(db, bundle, sender_machine=peer.machine_id,
                                        max_bytes=jobs_bundle.DEFAULT_MAX_BYTES), None
    except duplicates.ReplicaClash:
        return None, _RETRY
    except ValueError:
        return None, _CANT_APPLY
    except OSError:
        db.rollback()
        raise _disk_error() from None


def _store(db: Session, peer: PeerInfo, bundle: dict, found: dict) -> None:
    job_id = wire.bundle_job_id(bundle)
    shown = job_id.hex if job_id else None
    outcome, reason = _apply_one(db, peer, bundle, job_id)
    if outcome is None:
        found["refused"].append({"job_id": shown, "reason": reason})
        if reason == _LAPTOP_DELETED and shown is not None:
            found["gone"].append({"job_id": shown})
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
    # Deletions first: a job deleted and re-saved with the same text in one round must not clash
    # with its own stale copy.
    found: dict[str, list] = {"applied": [], "duplicates": [], "refused": [], "gone": []}
    deleted = [t.job_id.hex for t in push.tombstones if _drop_replica(db, peer, t.job_id)]
    for bundle in push.bundles:
        _store(db, peer, bundle, found)
    return {**found, "deleted": deleted}


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


@router.get("/requests")
def get_requests(peer: Peer, db: DB):
    """This copy's unanswered requests for jobs the peer owns, marked sent. A sent one is served
    again until the peer answers it (request-results); the peer dedupes by request id."""
    rows = db.scalars(
        select(SyncRequest).join(Job, Job.id == SyncRequest.job_id)
        .where(SyncRequest.origin == "local", SyncRequest.status.in_(("pending", "sent")),
               Job.owner_machine == peer.machine_id)
        .order_by(SyncRequest.created_at, SyncRequest.id)).all()
    shown = [wire.shown(row) for row in rows]
    for row in rows:
        row.status = "sent"
    db.commit()
    return shown


class _RequestsPush(BaseModel):
    requests: list[request_apply.RequestIn]


@router.post("/requests")
def post_requests(peer: Peer, db: DB, body: Body):
    """Apply the peer's requests in the order they were made, under the normal rules."""
    items = sorted(_parse(_RequestsPush, body).requests, key=lambda i: (i.created_at, i.id))
    return [request_apply.answer(db, item) for item in items]


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
        row.reason = (result.reason or "")[:wire.MAX_REASON] or None
        updated += 1
    db.commit()
    return {"updated": updated}


# ------------------------------------------------------------------------------- handovers


@router.get("/handover/offers")
def get_offers(peer: Peer, db: DB):
    if not offers.offers_open(db):
        return {"bundles": [], "skipped": 0}
    ids = list(db.scalars(select(Job.id).where(
        jobs_bundle.owned_clause(db), Job.handover == "offered").order_by(Job.sync_rev, Job.id)))
    bundles, skipped = _export(db, ids)
    return {"bundles": bundles, "skipped": skipped}


@router.post("/handover/commit")
def post_commit(peer: Peer, db: DB, body: Body):
    asked = [_uuid(raw) for raw in _parse(_JobIds, body).job_ids]
    home_id = status.machine_id(db)
    committed = []
    with hooks.standing_aside(db):
        for job in (db.get(Job, job_id) for job_id in asked):
            if job is not None and job.handover == "offered" and job.owner_machine in (None, home_id):
                job.owner_machine, job.handover = peer.machine_id, None
                committed.append(job.id.hex)
        db.commit()
    return {"job_ids": committed}


class _BundlesPush(BaseModel):
    bundles: list[dict[str, Any]]


def _take_back(db: Session, peer: PeerInfo, bundle: dict, found: dict) -> None:
    job_id = wire.bundle_job_id(bundle)
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
        jobs_bundle.apply_job(db, duplicates.for_stored(db, bundle),
                              sender_machine=status.machine_id(db),
                              max_bytes=jobs_bundle.DEFAULT_MAX_BYTES)
    except (ValueError, jobs_bundle.DuplicateJob):
        return _CANT_APPLY
    except OSError:
        db.rollback()
        raise _disk_error() from None
    with hooks.standing_aside(db):
        job = db.get(Job, job_id)
        job.owner_machine, job.handover = None, None
        requests.settle_take_overs(db, job_id)  # a lost reply must not leave the request at "sent"
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
    counts: dict[RunCountKey, Annotated[StrictInt, Field(ge=0)]] = {}
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


# ------------------------------------------------------------------------------------ the round


class _RoundBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    force: bool = False
    pair: bool = False
    accept_profile_overwrite: bool = False


def _require_round_caller(request: Request) -> None:
    """Only the always-on copy runs rounds; its own loopback is the whole trust boundary, so no
    key, but a browser's request is refused."""
    if not status.is_remote():
        raise HTTPException(404, detail=_NOT_FOUND)
    if "origin" in request.headers:
        raise HTTPException(403, detail=_NO_BROWSERS)


@router.post("/round", dependencies=[Depends(_require_round_caller)])
def post_round(db: DB, body: _RoundBody | None = None):
    """Run one round now and return its per-step counts (never contents) and its ``outcome``."""
    options = body or _RoundBody()
    try:
        return sync_round.run_round(db, force=options.force, pair=options.pair,
                                    accept_profile_overwrite=options.accept_profile_overwrite)
    except sync_round.RoundBusy:
        return JSONResponse(status_code=409, content={"detail": _BUSY, "outcome": "transient"})
