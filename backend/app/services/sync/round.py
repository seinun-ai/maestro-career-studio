"""One sync round, driven by the always-on copy (split-ownership design, Parts B and C).

``run_round`` talks to home's ``/api/sync/*`` endpoints through ``http_client.new_client`` and
works on this copy's own database in-process. Its steps: hello, pairing, ownership reconcile,
profile, push own jobs, pull home's jobs, requests both ways, handovers, run log. Each step commits
on its own and a failed step stops the round; the next round resumes from the saved state
(``status.read_state``).

Nothing here logs or stores a key, a bundle, a response body or ``str(exc)``: a failure is a status
code plus a fixed sentence, and the summary holds counts only.
"""

import threading
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.agent_run import AgentRun
from app.models.application import Application
from app.models.application_proposal import ApplicationProposal
from app.models.job import Job
from app.models.sync import SyncRequest, SyncTombstone
from app.models.types import utcnow
from app.routers import version
from app.services import http_client
from app.services.sync import duplicates, hooks, jobs_bundle, profile_bundle, status

PAGE_BYTES = 40 * 1024 * 1024  # well under home's 100 MB request cap
PUSH_JOBS = 20
PULL_JOBS = 20
OWNERSHIP_CHUNK = 500
RUN_PAGE = 200
MAX_REASON = 500
_TIMEOUT = httpx.Timeout(120.0, connect=10.0)
_LOCK = threading.Lock()

NOT_SET_UP = "Sync isn't set up."
NOT_PAIRED = "This copy isn't paired with your laptop yet; run the first sync with the pair option."
VERSION_MISMATCH = "Update Maestro on both machines to the same version."
UNREACHABLE = "Laptop unreachable."
BUSY_APPLYING = "Your bot is applying to this one; try again after its run."
_DISK = "Maestro couldn't save the files it received."
_CANT_READ = "Maestro couldn't read the files it needed to send."
_UNREADABLE = "Your laptop's answer wasn't what Maestro expected."
_PROFILE = "Maestro couldn't apply your laptop's profile."
_GENERIC = "Your laptop couldn't finish that sync request."
_NOT_HOLDING = "Your bot isn't holding this job."
_CANT_SEND_BACK = "Maestro couldn't send this job back to your laptop."
_SENTENCES = {
    401: "Sync key doesn't match.",
    404: "Sync isn't set up on your laptop.",
    413: "Your laptop refused a request as too large.",
}
_CONFLICTS = {
    "machine": "These two copies share one machine id; give the always-on copy its own data.",
    "busy": "A sync is already running on your laptop.",
}


class RoundBusy(Exception):
    """Another round is already running in this process."""


class _Skip(Exception):
    """The round can't start; nothing was changed and nothing is recorded."""


class _Stop(Exception):
    """The round stops here and is recorded as failed. Always a fixed sentence."""

    def __init__(self, sentence: str, code: int | None = None):
        super().__init__(sentence)
        self.sentence, self.code = sentence, code

    @property
    def text(self) -> str:
        return f"{self.code}: {self.sentence}" if self.code else self.sentence


@dataclass(frozen=True)
class _Options:
    force: bool
    pair: bool
    accept_profile_overwrite: bool


@dataclass
class _Ctx:
    db: Session
    http: httpx.Client
    home_id: str = ""
    summary: dict = field(default_factory=dict)
    takeovers: list = field(default_factory=list)


def _now() -> datetime:
    return utcnow()


def _endpoints():
    """Home's request appliers live with its endpoints. Imported late: that module imports this one."""
    from app.routers import sync as endpoints

    return endpoints


# ----------------------------------------------------------------------------------- the wire


def _reason_of(response: httpx.Response) -> str | None:
    try:
        reason = response.json().get("reason")
    except (ValueError, AttributeError):
        return None
    return reason if reason in ("version", *_CONFLICTS) else None


def _refusal(response: httpx.Response) -> Exception:
    """What a refused request means; the body is read for one known word and never kept."""
    code = response.status_code
    if code == 409:
        reason = _reason_of(response)
        if reason == "version":
            return _Skip(VERSION_MISMATCH)
        return _Stop(_CONFLICTS.get(reason, _GENERIC), code)
    return _Stop(_SENTENCES.get(code, _GENERIC), code)


def _call(ctx: _Ctx, method: str, path: str, *, params: dict | None = None, body=None):
    try:
        response = ctx.http.request(method, path, params=params, json=body)
    except (httpx.TransportError, httpx.InvalidURL):
        raise _Stop(UNREACHABLE) from None
    if response.status_code >= 400:
        raise _refusal(response)
    try:
        return response.json()
    except ValueError:
        raise _Stop(_UNREADABLE) from None


def _headers(db: Session, key: str) -> dict:
    revision = version.get_version(db).schema_revision
    mine = status.machine_id(db)
    db.commit()
    return {"Authorization": f"Bearer {key}",
            "X-Maestro-Sync": f"{status.SYNC_PROTOCOL}:{revision}:{mine}"}


def _chunks(items: list, size: int) -> Iterator[list]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


# --------------------------------------------------------------------------------- local helpers


def _owner_clause(db: Session):
    return or_(Job.owner_machine.is_(None), Job.owner_machine == status.machine_id(db))


def _set_owner(db: Session, job_ids: list, owner: str | None) -> None:
    """Flip who owns these jobs, clearing any handover; the guard stands aside for this."""
    with jobs_bundle._applying(db):
        for job_id in job_ids:
            job = db.get(Job, job_id)
            if job is not None:
                job.owner_machine, job.handover = owner, None


def _progressed(db: Session, job_id) -> bool:
    """An application, or a proposal past pending_review, exists for the job."""
    if db.scalar(select(Application.id).where(Application.job_id == job_id).limit(1)) is not None:
        return True
    return db.scalar(select(ApplicationProposal.id).where(
        ApplicationProposal.job_id == job_id,
        ApplicationProposal.status != "pending_review").limit(1)) is not None


def _mid_application(db: Session, job_id) -> bool:
    return db.scalar(select(ApplicationProposal.id).where(
        ApplicationProposal.job_id == job_id,
        ApplicationProposal.status.in_(("approved", "submission_uncertain"))).limit(1)) is not None


def _answer_text(value) -> str | None:
    return value[:MAX_REASON] if isinstance(value, str) and value else None


# ------------------------------------------------------------------------------- 2-3: hello, pairing


def _hello(ctx: _Ctx) -> None:
    hello = _call(ctx, "GET", "/api/sync/hello")
    mine = version.get_version(ctx.db).schema_revision
    if hello["protocol"] != status.SYNC_PROTOCOL or hello["schema_revision"] != mine:
        raise _Skip(VERSION_MISMATCH)
    ctx.home_id = str(hello["machine_id"])


def _pairing_refusal(ctx: _Ctx, accept_profile_overwrite: bool) -> str | None:
    """The sentence that stops a first round, or None to go ahead. This is where the first-round
    comparison of the two profiles is wired in; with none wired in, nothing stops a paired first
    round."""
    return None


def _ensure_paired(ctx: _Ctx, options: _Options) -> None:
    if status.read_state(ctx.db)["paired"]:
        return
    if not options.pair:
        raise _Skip(NOT_PAIRED)
    refusal = _pairing_refusal(ctx, options.accept_profile_overwrite)
    if refusal:
        raise _Skip(refusal)
    status.update_state(ctx.db, paired=True)


# ------------------------------------------------------------------------------------ 4: reconcile


def _reconcile_one(ctx: _Ctx, job_id, handover: str | None, label: str | None, counts: dict) -> None:
    if label == "remote":  # home says the job is ours: a committed offer, or a return that never landed
        _set_owner(ctx.db, [job_id], None)
        counts["owned"] += 1
    elif label == "home" and handover == "returning":  # a return that landed before the local flip
        _set_owner(ctx.db, [job_id], ctx.home_id)
        counts["replicas"] += 1
    elif label == "gone":
        jobs_bundle.apply_tombstone(ctx.db, job_id)
        counts["deleted"] += 1


def _reconcile(ctx: _Ctx) -> dict:
    counts = {"owned": 0, "replicas": 0, "deleted": 0}
    candidates = ctx.db.execute(select(Job.id, Job.handover).where(
        or_(Job.owner_machine == ctx.home_id, Job.handover == "returning"))).all()
    for chunk in _chunks(candidates, OWNERSHIP_CHUNK):
        labels = _call(ctx, "POST", "/api/sync/ownership",
                       body={"job_ids": [row.id.hex for row in chunk]})
        for row in chunk:
            _reconcile_one(ctx, row.id, row.handover, labels.get(row.id.hex), counts)
    return counts


# ------------------------------------------------------------------------------------- 5: profile


def _profile(ctx: _Ctx) -> dict:
    since = status.read_state(ctx.db)["profile_rev"]
    answer = _call(ctx, "GET", "/api/sync/profile",
                   params=None if since is None else {"since": since})
    if answer.get("unchanged"):
        return {"applied": 0}
    ctx.db.commit()  # applying a profile wants a session with nothing pending
    try:
        rev = profile_bundle.apply_profile(ctx.db, answer)
    except ValueError:
        raise _Stop(_PROFILE) from None
    status.update_state(ctx.db, profile_rev=rev)
    return {"applied": 1}


# ---------------------------------------------------------------------------------- 6: push jobs


@dataclass
class _Push:
    acked: int
    top: int
    cap: int | None = None
    counts: dict = field(default_factory=lambda: dict.fromkeys(
        ("sent", "refused", "skipped", "dropped", "kept_both", "deleted"), 0))


@dataclass
class _Page:
    bundles: list
    top: int
    skipped: int
    taken: int


def _weight(bundle: dict) -> int:
    """About how many bytes a bundle adds to a request: its files, base64, and its rows."""
    return sum(len(entry["b64"]) for entry in bundle["files"]) + len(str(bundle["rows"]))


def _export_one(db: Session, job_id) -> dict | None:
    try:
        return jobs_bundle.export_job(db, job_id, max_bytes=jobs_bundle.DEFAULT_MAX_BYTES)
    except (ValueError, LookupError):
        return None  # too large, a symlink, or gone since it was listed
    except OSError:
        raise _Stop(_CANT_READ) from None


def _take_page(db: Session, rows: list) -> _Page:
    """Bundles of the leading rows, up to PUSH_JOBS and PAGE_BYTES but never fewer than one row."""
    page, used = _Page([], 0, 0, 0), 0
    for row in rows[:PUSH_JOBS]:
        bundle = _export_one(db, row.id)
        size = _weight(bundle) if bundle else 0
        if page.taken and used + size > PAGE_BYTES:
            break
        page.taken, used = page.taken + 1, used + size
        page.top = max(page.top, bundle["sync_rev"] if bundle else row.sync_rev)
        if bundle:
            page.bundles.append(bundle)
        else:
            page.skipped += 1
    return page


def _drop_duplicate(ctx: _Ctx, job_id_hex: str, push: _Push) -> None:
    """Home keeps its own job for this text: drop ours, unless work began on it since the export."""
    job_id = _uuid(job_id_hex)
    if job_id is not None and not _progressed(ctx.db, job_id):
        jobs_bundle.apply_tombstone(ctx.db, job_id)
        push.counts["dropped"] += 1


def _uuid(raw):
    try:
        return uuid.UUID(str(raw))
    except ValueError:
        return None


def _settle_push(ctx: _Ctx, answer: dict, page: _Page, push: _Push) -> None:
    revs = {bundle["job_id"]: bundle["sync_rev"] for bundle in page.bundles}
    refused = [revs[item["job_id"]] for item in answer["refused"] if item.get("job_id") in revs]
    for rev in refused:
        push.cap = rev - 1 if push.cap is None else min(push.cap, rev - 1)
    push.counts["refused"] += len(answer["refused"])
    push.counts["sent"] += len(page.bundles) - len(refused)
    push.counts["deleted"] += len(answer.get("deleted", []))
    for item in answer["duplicates"]:
        if item.get("kept") == "laptop":
            _drop_duplicate(ctx, item["job_id"], push)
        else:
            push.counts["kept_both"] += 1


def _save_ack(ctx: _Ctx, push: _Push) -> None:
    ack = push.top if push.cap is None else min(push.top, push.cap)
    if ack > push.acked:
        status.update_state(ctx.db, acked_own=ack)
        push.acked = ack


def _send_page(ctx: _Ctx, page: _Page, tombstones: list, push: _Push) -> None:
    if page.bundles or tombstones:
        answer = _call(ctx, "POST", "/api/sync/jobs",
                       body={"bundles": page.bundles, "tombstones": tombstones})
        _settle_push(ctx, answer, page, push)
    push.counts["skipped"] += page.skipped
    push.top = max(push.top, page.top, *(item["rev"] for item in tombstones))
    _save_ack(ctx, push)


def _push(ctx: _Ctx) -> dict:
    db = ctx.db
    acked = status.read_state(db)["acked_own"]
    rows = db.execute(select(Job.id, Job.sync_rev).where(_owner_clause(db), Job.sync_rev > acked)
                      .order_by(Job.sync_rev, Job.id)).all()
    tombstones = [{"job_id": row.job_id.hex, "rev": row.rev} for row in db.scalars(
        select(SyncTombstone).where(SyncTombstone.rev > acked).order_by(SyncTombstone.rev))]
    push = _Push(acked=acked, top=acked)
    while rows or tombstones:
        page = _take_page(db, rows)
        rows = rows[page.taken:]
        _send_page(ctx, page, tombstones, push)
        tombstones = []
    return push.counts


# ---------------------------------------------------------------------------------- 7: pull jobs


def _apply_home_bundle(ctx: _Ctx, bundle: dict) -> str:
    """Store home's job as a replica. A text clash with a job of ours follows the same rule as at
    home: the laptop's job wins unless ours has progressed, then both stay under a replica hash.
    Returns applied, dropped, both, skipped (unusable) or held (try again next round)."""
    db = ctx.db
    try:
        jobs_bundle.apply_job(db, duplicates.for_stored(db, bundle), sender_machine=ctx.home_id,
                              max_bytes=jobs_bundle.DEFAULT_MAX_BYTES)
        return "applied"
    except jobs_bundle.DuplicateJob as clash:
        return _settle_clash(ctx, bundle, clash.local_id)
    except ValueError:
        return "skipped"


def _settle_clash(ctx: _Ctx, bundle: dict, local_id) -> str:
    db = ctx.db
    local = db.get(Job, local_id)
    if local is None or local.owner_machine not in (None, status.machine_id(db)):
        return "held"
    try:
        if _progressed(db, local_id):
            jobs_bundle.apply_job(db, duplicates.with_replica_hash(bundle),
                                  sender_machine=ctx.home_id,
                                  max_bytes=jobs_bundle.DEFAULT_MAX_BYTES)
            return "both"
        jobs_bundle.apply_tombstone(db, local_id)
        jobs_bundle.apply_job(db, bundle, sender_machine=ctx.home_id,
                              max_bytes=jobs_bundle.DEFAULT_MAX_BYTES)
        return "dropped"
    except (ValueError, jobs_bundle.DuplicateJob):
        return "skipped"


def _drop_deleted(ctx: _Ctx, tombstones: list) -> int:
    """Delete replicas of jobs home deleted; a job of ours is never deleted by home's say-so."""
    deleted = 0
    for item in tombstones:
        job_id = _uuid(item["job_id"])
        owner = ctx.db.scalar(select(Job.owner_machine).where(Job.id == job_id))
        if job_id is not None and owner == ctx.home_id:
            jobs_bundle.apply_tombstone(ctx.db, job_id)
            deleted += 1
    return deleted


_PULL_COUNTS = {"applied": "applied", "dropped": "dropped", "both": "kept_both",
                "skipped": "skipped", "held": "retry"}


def _apply_page(ctx: _Ctx, page: dict, counts: dict) -> bool:
    """Apply one page of home's jobs; True when one must wait for the next round."""
    counts["deleted"] += _drop_deleted(ctx, page["tombstones"])
    held = False
    for bundle in page["bundles"]:
        outcome = _apply_home_bundle(ctx, bundle)
        counts[_PULL_COUNTS[outcome]] += 1
        counts["applied"] += outcome == "dropped"
        held = held or outcome == "held"
    counts["skipped"] += int(page.get("skipped", 0))
    return held


def _pull(ctx: _Ctx) -> dict:
    counts = dict.fromkeys(("applied", "deleted", "dropped", "kept_both", "skipped", "retry"), 0)
    since = status.read_state(ctx.db)["since_home"]
    while True:
        page = _call(ctx, "GET", "/api/sync/jobs", params={"since": since, "limit": PULL_JOBS})
        if _apply_page(ctx, page, counts):
            break  # the cursor stays before this page; it is applied again next round
        following = page["next_since"]
        if not isinstance(following, str) or (page["more"] and following == since):
            raise _Stop(_UNREADABLE)
        status.update_state(ctx.db, since_home=following)
        since = following
        if not page["more"]:
            break
    return counts


# ------------------------------------------------------------------------------ 8: requests both ways


def _parse_item(raw):
    from pydantic import ValidationError

    try:
        return _endpoints()._RequestIn.model_validate(raw)
    except ValidationError:
        return None


def _answer_home_requests(ctx: _Ctx, counts: dict) -> None:
    """Answer home's unanswered requests. A repeat is answered from its local record, never applied
    again. A take-over waits for step 9, which decides it."""
    results = []
    for raw in _call(ctx, "GET", "/api/sync/requests"):
        item = _parse_item(raw)
        if item is None:
            counts["invalid"] += 1
        elif item.kind == "take_over" and ctx.db.get(SyncRequest, item.id) is None:
            ctx.takeovers.append(item)
        else:
            results.append(_endpoints()._answer(ctx.db, item))
    counts["answered"] += len(results)
    counts["refused"] += sum(result["status"] == "refused" for result in results)
    if results:
        _call(ctx, "POST", "/api/sync/request-results", body={"results": results})


def _apply_here(ctx: _Ctx, row: SyncRequest) -> str:
    """A request made while the job was home's, for a job that is ours now: apply it, don't send it."""
    rules = _endpoints()
    item = rules._RequestIn(id=row.id, kind=row.kind, job_id=row.job_id,
                            payload=row.payload_json, created_at=row.created_at)
    applier = rules._APPLIERS.get(row.kind)
    try:
        if applier is None:
            raise rules._Refusal(rules._UNKNOWN_KIND)
        if row.kind != "take_over":  # asking for a job back that is already here is moot
            applier(ctx.db, item)
        return _finish_local(ctx, row.id, "applied", None)
    except (rules._Refusal, hooks.NotOwnedHere) as refusal:
        ctx.db.rollback()
        return _finish_local(ctx, row.id, "refused", _answer_text(str(refusal)))
    except Exception:
        ctx.db.rollback()
        return _finish_local(ctx, row.id, "refused", rules._REQUEST_FAILED)


def _finish_local(ctx: _Ctx, request_id, outcome: str, reason: str | None) -> str:
    row = ctx.db.get(SyncRequest, request_id)
    row.status, row.reason, row.answered_at = outcome, reason, utcnow()
    ctx.db.commit()
    return outcome


def _wire(row: SyncRequest) -> dict:
    return {"id": row.id.hex, "kind": row.kind, "job_id": row.job_id.hex if row.job_id else None,
            "payload": row.payload_json, "created_at": row.created_at.isoformat()}


def _store_answers(ctx: _Ctx, answers: list, counts: dict) -> None:
    for answer in answers:
        row = ctx.db.get(SyncRequest, _uuid(answer["id"]))
        if row is None or row.origin != "local" or answer["status"] not in ("applied", "refused"):
            continue
        row.status, row.reason, row.answered_at = (
            answer["status"], _answer_text(answer.get("reason")), utcnow())
        counts["refused"] += answer["status"] == "refused"
    ctx.db.commit()


def _send_local_requests(ctx: _Ctx, counts: dict) -> None:
    pending = ctx.db.scalars(select(SyncRequest).where(
        SyncRequest.origin == "local", SyncRequest.status == "pending")
        .order_by(SyncRequest.created_at, SyncRequest.id)).all()
    to_send = []
    for row in pending:
        if row.job_id is not None and hooks.owned_here(ctx.db, row.job_id):
            counts["applied_here"] += _apply_here(ctx, row) == "applied"
        else:
            to_send.append(row)
    if to_send:
        answers = _call(ctx, "POST", "/api/sync/requests",
                        body={"requests": [_wire(row) for row in to_send]})
        counts["sent"] += len(to_send)
        _store_answers(ctx, answers, counts)


def _requests(ctx: _Ctx) -> dict:
    counts = dict.fromkeys(("answered", "refused", "invalid", "sent", "applied_here"), 0)
    _answer_home_requests(ctx, counts)
    _send_local_requests(ctx, counts)
    return counts


# --------------------------------------------------------------------------------- 9: handovers


def _take_offers(ctx: _Ctx, counts: dict) -> None:
    offers = _call(ctx, "GET", "/api/sync/handover/offers")
    counts["skipped"] += int(offers.get("skipped", 0))
    stored = []
    for bundle in offers["bundles"]:
        outcome = _apply_home_bundle(ctx, bundle)
        if outcome in ("applied", "dropped", "both"):
            stored.append(bundle["job_id"])
        else:
            counts["skipped"] += 1
    if not stored:
        return
    committed = _call(ctx, "POST", "/api/sync/handover/commit", body={"job_ids": stored})["job_ids"]
    ids = [_uuid(raw) for raw in committed if raw in stored]
    _set_owner(ctx.db, ids, None)
    counts["taken"] += len(ids)


def _record_decision(ctx: _Ctx, item, outcome: str, reason: str | None) -> None:
    ctx.db.add(SyncRequest(id=item.id, job_id=item.job_id, kind="take_over", payload_json={},
                           origin="remote", status=outcome, reason=reason,
                           created_at=item.created_at, answered_at=utcnow()))


def _hand_back(ctx: _Ctx, job_id) -> bool:
    """Send the job home. The job is marked returning first, so a crash leaves a state the next
    round's reconcile reads against home's answer."""
    db = ctx.db
    with jobs_bundle._applying(db):
        db.get(Job, job_id).handover = "returning"
    try:
        bundle = jobs_bundle.export_job(db, job_id, max_bytes=jobs_bundle.DEFAULT_MAX_BYTES)
    except (ValueError, LookupError, OSError):
        return False
    answer = _call(ctx, "POST", "/api/sync/handover/return", body={"bundles": [bundle]})
    return job_id.hex in answer["job_ids"]


def _decide_return(ctx: _Ctx, item) -> tuple[str, str | None]:
    """Grant or refuse one take-over; the decision is recorded in the same commit as its effect."""
    db = ctx.db
    job = db.get(Job, item.job_id) if item.job_id else None
    if job is None:
        return "refused", _NOT_HOLDING
    if job.owner_machine == ctx.home_id:  # already handed back, and the record never landed
        return "applied", None
    if job.owner_machine is not None and job.owner_machine != status.machine_id(db):
        return "refused", _NOT_HOLDING
    if _mid_application(db, job.id):
        return "refused", BUSY_APPLYING
    if _hand_back(ctx, job.id):
        return "applied", None
    return "refused", _CANT_SEND_BACK


def _return_jobs(ctx: _Ctx, counts: dict) -> None:
    results = []
    for item in ctx.takeovers:
        outcome, reason = _decide_return(ctx, item)
        with jobs_bundle._applying(ctx.db):
            _finish_return(ctx, item, outcome)
            _record_decision(ctx, item, outcome, reason)
        counts["returned" if outcome == "applied" else "refused"] += 1
        results.append({"id": item.id.hex, "status": outcome, "reason": reason})
    if results:
        _call(ctx, "POST", "/api/sync/request-results", body={"results": results})


def _finish_return(ctx: _Ctx, item, outcome: str) -> None:
    """Make the local rows match the decision: a replica of home's job, or still ours."""
    job = ctx.db.get(Job, item.job_id) if item.job_id else None
    if job is None:
        return
    if outcome == "applied":
        job.owner_machine = ctx.home_id
    job.handover = None


def _handovers(ctx: _Ctx) -> dict:
    counts = dict.fromkeys(("taken", "skipped", "returned", "refused"), 0)
    _take_offers(ctx, counts)
    _return_jobs(ctx, counts)
    return counts


# ------------------------------------------------------------------------------------- 10: runs


def _run_wire(run: AgentRun) -> dict:
    return {"id": run.id.hex, "automation": run.automation, "outcome": run.outcome,
            "agent": run.agent, "finished_at": run.finished_at.isoformat(),
            "counts": run.counts, "digest": run.digest, "job_ids": run.job_ids}


def _runs(ctx: _Ctx) -> dict:
    sent = 0
    while True:
        since = status.read_state(ctx.db)["runs_at"]
        query = select(AgentRun).where(AgentRun.machine.is_(None))
        if since:
            query = query.where(AgentRun.finished_at > datetime.fromisoformat(since))
        rows = ctx.db.scalars(query.order_by(AgentRun.finished_at, AgentRun.id)
                              .limit(RUN_PAGE)).all()
        if not rows:
            return {"sent": sent}
        _call(ctx, "POST", "/api/sync/runs", body={"runs": [_run_wire(run) for run in rows]})
        status.update_state(ctx.db, runs_at=rows[-1].finished_at.isoformat())
        sent += len(rows)


# ------------------------------------------------------------------------------- the round itself


_STEPS = (("reconcile", _reconcile), ("profile", _profile), ("push", _push), ("pull", _pull),
          ("requests", _requests), ("handovers", _handovers), ("runs", _runs))


def _waiting(state: dict) -> str | None:
    """The sentence for a round that is still inside its backoff window, or None."""
    try:
        until = datetime.fromisoformat(state["next_attempt_at"]) if state["next_attempt_at"] else None
    except ValueError:
        return None
    if until is None or _now() >= until:
        return None
    reason = state["last_error"] or "The last sync failed."
    return f"{reason} Next try at {until.isoformat()}."


def _record_failure(db: Session, stop: _Stop) -> None:
    db.rollback()
    failures = status.read_state(db)["failures"] + 1
    delay = min(30, 5 * 2 ** min(failures - 1, 5))
    status.update_state(db, failures=failures, last_error=stop.text,
                        next_attempt_at=(_now() + timedelta(minutes=delay)).isoformat())


def _guarded(ctx: _Ctx, options: _Options) -> None:
    _hello(ctx)
    _ensure_paired(ctx, options)
    for name, step in _STEPS:
        ctx.summary[name] = step(ctx)


def _attempt(db: Session, http: httpx.Client, options: _Options) -> dict:
    ctx = _Ctx(db, http)
    try:
        _guarded(ctx, options)
    except _Skip as skip:
        db.rollback()
        return {"ok": False, "skipped": str(skip)}
    except (OSError, _Stop, KeyError, TypeError, AttributeError) as failure:
        stop = failure if isinstance(failure, _Stop) else _Stop(
            _DISK if isinstance(failure, OSError) else _UNREADABLE)
        _record_failure(db, stop)
        return {"ok": False, "error": stop.text, "steps": ctx.summary}
    status.update_state(db, failures=0, next_attempt_at=None, last_error=None,
                        last_ok=_now().isoformat())
    return {"ok": True, "steps": ctx.summary}


def _locked_round(db: Session, options: _Options) -> dict:
    key = status.read_key()
    if key is None or not settings.sync_remote_url:
        return {"ok": False, "skipped": NOT_SET_UP}
    if not options.force and (wait := _waiting(status.read_state(db))):
        return {"ok": False, "skipped": wait}
    with http_client.new_client(base_url=settings.sync_remote_url, headers=_headers(db, key),
                                timeout=_TIMEOUT) as http:
        return _attempt(db, http, options)


def run_round(db: Session, *, force: bool = False, pair: bool = False,
              accept_profile_overwrite: bool = False) -> dict:
    """Run one round and return its per-step counts. ``force`` ignores the backoff window; ``pair``
    allows the first round; ``accept_profile_overwrite`` lets a first round replace this copy's
    profile. Raises RoundBusy when a round is already running here."""
    if not _LOCK.acquire(blocking=False):
        raise RoundBusy
    try:
        return _locked_round(db, _Options(force, pair, accept_profile_overwrite))
    finally:
        _LOCK.release()
