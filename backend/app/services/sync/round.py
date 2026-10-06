"""One sync round, driven by the always-on copy (split-ownership design, Parts B and C).

``run_round`` talks to home's ``/api/sync/*`` endpoints through ``http_client.new_client`` and
works on this copy's own database in-process. Its steps: hello, pairing, ownership reconcile,
profile, push own jobs, pull home's jobs, requests both ways, handovers, run log. Each step commits
on its own and a failed step stops the round; the next round resumes from the saved state
(``status.read_state``).

Nothing here logs or stores a key, a bundle, a response body or ``str(exc)``: a failure is a status
code plus a fixed sentence, and the summary holds counts only.
"""

import hashlib
import json
import threading
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx
from sqlalchemy import event, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.agent_run import AgentRun
from app.models.application import Application
from app.models.application_proposal import ApplicationProposal
from app.models.job import Job
from app.models.setting import Setting
from app.models.sync import SyncRequest, SyncTombstone
from app.models.types import utcnow
from app.services import http_client
from app.services.sync import bundle_rows, duplicates, hooks, jobs_bundle, profile_bundle, request_apply, status

PAGE_BYTES = 40 * 1024 * 1024  # well under home's 100 MB request cap
PUSH_JOBS = 20
RETRY_LIMIT = 5
FORCE_GAP = timedelta(seconds=30)
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
SYNCED_JUST_NOW = "Synced moments ago."
BUSY_APPLYING = "Your bot is applying to this one; try again after its run."
_DISK = "Maestro couldn't save the files it received."
_CANT_READ = "Maestro couldn't read the files it needed to send."
_UNREADABLE = "Your laptop's answer wasn't what Maestro expected."
_PROFILE = "Maestro couldn't apply your laptop's profile."
_GENERIC = "Your laptop couldn't finish that sync request."
_LOCAL = "Maestro couldn't finish that sync on this copy."
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
# The round's machine-readable result, for the script that drives it: ``ok``; ``transient`` (try
# again later, nobody needs to act); ``needs_person`` (a person has to fix something first).
OK, TRANSIENT, NEEDS_PERSON = "ok", "transient", "needs_person"


class RoundBusy(Exception):
    """Another round is already running in this process."""


class _Skip(Exception):
    """The round can't start; nothing was changed. ``remember`` also keeps the sentence as the
    status's last error (a version mismatch), and nothing else."""

    def __init__(self, sentence: str, outcome: str = NEEDS_PERSON, remember: bool = False):
        super().__init__(sentence)
        self.outcome, self.remember = outcome, remember


class _Stop(Exception):
    """The round stops here and is recorded as failed. Always a fixed sentence."""

    def __init__(self, sentence: str, code: int | None = None, outcome: str | None = None):
        super().__init__(sentence)
        self.sentence, self.code = sentence, code
        # Without an explicit word: no status code is a lost line, a 5xx a laptop hiccup, any
        # other refusal something the person has to fix.
        self.outcome = outcome or (TRANSIENT if code is None or code >= 500 else NEEDS_PERSON)

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
    pairing_profile: dict | None = field(default=None, repr=False)
    shared_jobs: list = field(default_factory=list)
    paired_now: bool = False


def _now() -> datetime:
    return utcnow()


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
            return _Skip(VERSION_MISMATCH, remember=True)
        return _Stop(_CONFLICTS.get(reason, _GENERIC), code,
                     TRANSIENT if reason == "busy" else None)
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
        raise _Stop(_UNREADABLE, outcome=NEEDS_PERSON) from None


def _headers(db: Session, key: str) -> dict:
    revision = status.schema_revision(db)
    mine = status.machine_id(db)
    db.commit()
    return {"Authorization": f"Bearer {key}",
            "X-Maestro-Sync": f"{status.SYNC_PROTOCOL}:{revision}:{mine}"}


def _chunks(items: list, size: int) -> Iterator[list]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


# --------------------------------------------------------------------------------- local helpers


def _set_owner(db: Session, job_ids: list, owner: str | None) -> None:
    """Flip who owns these jobs, clearing any handover; the guard stands aside for this."""
    with jobs_bundle.applying(db):
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
    mine = status.schema_revision(ctx.db)
    if hello["protocol"] != status.SYNC_PROTOCOL or hello["schema_revision"] != mine:
        raise _Skip(VERSION_MISMATCH, remember=True)
    ctx.home_id = str(hello["machine_id"])


def _profile_index(bundle: dict) -> dict:
    specs = {spec.name: spec for spec in profile_bundle.TABLES}
    return {(item["table"], bundle_rows.row_pk(specs[item["table"]], item["row"])): item["row"]
            for item in bundle["rows"]}


# Each copy stamps these itself (a seeded template is written at that install's first start and
# validated by its own engines), so two identical installs would otherwise always differ and
# every first round would need the overwrite flag. Content columns never appear here.
_LOCAL_STAMPS = frozenset({"created_at", "updated_at"})
_LOCAL_BY_TABLE = {"templates": frozenset({"validated_at", "parse_report_json", "parse_certified",
                                           "status", "last_error"})}


def _row_hash(table: str, row: dict) -> str:
    """Compare rows without retaining or exposing their values; JSON object order is immaterial
    and the columns each copy stamps for itself don't count."""
    skipped = _LOCAL_STAMPS | _LOCAL_BY_TABLE.get(table, frozenset())
    kept = {name: value for name, value in row.items() if name not in skipped}
    encoded = json.dumps(kept, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _addition_keys(remote: dict, home: dict) -> set:
    """Only new cannot-confirm points and their new holder are allowed profile additions."""
    points = {key for key, row in remote.items() if key[0] == "kb_points" and key not in home
              and row["provenance"] == "user_cannot_confirm"}
    holders = {remote[key]["entity_id"] for key in points}
    ignored = set(points)
    for key, row in remote.items():
        if key[0] != "kb_entities" or key in home or row["id"] not in holders:
            continue
        children = {pk for pk, point in remote.items()
                    if pk[0] == "kb_points" and point["entity_id"] == row["id"]}
        if (row["kind"] == "extra" and row["title"] == "Unconfirmed claims"
                and row["status"] == "archived" and row["origin"] == "gap_elicitation"
                and row["detail_json"] == {"holder": "cannot_confirm"} and children <= points):
            ignored.add(key)
    return ignored


def _empty_profile_keys(remote: dict) -> set:
    """The career profile row every copy creates lazily, still holding nothing: nothing to lose."""
    return {key for key, row in remote.items() if key[0] == "kb_profile"
            and not any(row[name] for name in ("contact_json", "summary", "skills_json", "notes"))}


def _differs(key: tuple, row: dict, theirs: dict) -> bool:
    return key not in theirs or _row_hash(key[0], row) != _row_hash(key[0], theirs[key])


def _profile_differences(remote: dict, home: dict) -> dict[str, list[str]]:
    """List remote rows that would be lost or replaced. Home-only rows are ordinary replication."""
    mine, theirs = _profile_index(remote), _profile_index(home)
    ignored = _addition_keys(mine, theirs) | _empty_profile_keys(mine)
    differences: dict[str, list[str]] = {}
    for key, row in mine.items():
        if key not in ignored and _differs(key, row, theirs):
            table, pk = key
            differences.setdefault(table, []).append("/".join(str(value) for value in pk))
    return {table: sorted(keys) for table, keys in sorted(differences.items())}


def _shared_jobs(ctx: _Ctx) -> list:
    shared = []
    ids = list(ctx.db.scalars(select(Job.id).order_by(Job.id)))
    for chunk in _chunks(ids, OWNERSHIP_CHUNK):
        labels = _call(ctx, "POST", "/api/sync/ownership",
                       body={"job_ids": [job_id.hex for job_id in chunk]})
        shared.extend(job_id for job_id in chunk if labels.get(job_id.hex) == "home")
    return shared


def _lost_bases(remote: dict, home: dict) -> list[str]:
    mine = {item["row"]["slug"] for item in remote["rows"] if item["table"] == "base_resumes"}
    theirs = {item["row"]["slug"] for item in home["rows"] if item["table"] == "base_resumes"}
    return sorted(mine - theirs)


def _affected_applications(db: Session, slugs: list[str]) -> list[str]:
    query = select(Application.id).join(Job, Job.id == Application.job_id).where(
        Application.base_resume.in_(slugs), jobs_bundle.owned_clause(db)).order_by(Application.id)
    return [application_id.hex for application_id in db.scalars(query)]


def _pairing_refusal(ctx: _Ctx, accept_profile_overwrite: bool) -> str | None:
    """Disclose only tables and keys, lost base slugs, affected applications and shared job ids.
    Accepting permits replacement, never merging. Cache the compared home snapshot for apply."""
    ctx.pairing_profile = _call(ctx, "GET", "/api/sync/profile")
    ctx.shared_jobs = _shared_jobs(ctx)
    if accept_profile_overwrite:
        return None
    remote = profile_bundle.export_profile(ctx.db)
    differences = _profile_differences(remote, ctx.pairing_profile)
    progressed = [job_id.hex for job_id in ctx.shared_jobs if _progressed(ctx.db, job_id)]
    if not differences and not progressed:
        return None
    details = [f"{table}: {', '.join(keys)}" for table, keys in differences.items()]
    lost = _lost_bases(remote, ctx.pairing_profile)
    if lost:
        details.append(f"Remote-only base resumes: {', '.join(lost)}")
        applications = _affected_applications(ctx.db, lost)
        if applications:
            details.append(f"Remote-owned applications using them: {', '.join(applications)}")
    if progressed:
        details.append(f"Shared jobs with remote progress: {', '.join(progressed)}")
    return ("Pairing would replace data on this copy. " + "; ".join(details)
            + ". Run pairing with --pair --accept-profile-overwrite to continue.")


def _apply_pairing_profile(ctx: _Ctx) -> None:
    """The first profile apply's commit also stores its revision, paired, and shared ownership.
    The listener is session-local and removed even on rollback; later mirror commits do nothing."""
    ctx.db.commit()
    staged = False

    def stage(db):
        nonlocal staged
        if staged:
            return
        state = {**status.read_state(db), "paired": True,
                 "profile_rev": ctx.pairing_profile["profile_rev"]}
        row = db.get(Setting, status.STATE_KEY)
        if row is None:
            db.add(Setting(key=status.STATE_KEY, value=json.dumps(state)))
        else:
            row.value = json.dumps(state)
        for job_id in ctx.shared_jobs:
            job = db.get(Job, job_id)
            if job is not None:  # deleted here since the pairing check
                job.owner_machine, job.handover = ctx.home_id, None
        staged = True

    event.listen(ctx.db, "before_commit", stage)
    try:
        profile_bundle.apply_profile(ctx.db, ctx.pairing_profile)
    except ValueError:
        raise _Stop(_PROFILE, outcome=NEEDS_PERSON) from None
    finally:
        event.remove(ctx.db, "before_commit", stage)
    ctx.paired_now = True
    ctx.pairing_profile = None


def _ensure_paired(ctx: _Ctx, options: _Options) -> None:
    if status.read_state(ctx.db)["paired"]:
        return
    if not options.pair:
        raise _Skip(NOT_PAIRED)
    refusal = _pairing_refusal(ctx, options.accept_profile_overwrite)
    if refusal:
        raise _Skip(refusal)
    _apply_pairing_profile(ctx)


# ------------------------------------------------------------------------------------ 4: reconcile


def _settle_gone(ctx: _Ctx, row, counts: dict) -> None:
    if row.handover == "returning" and row.owner_machine != ctx.home_id:
        _set_owner(ctx.db, [row.id], None)  # ours, mid-return: home doesn't know it, so keep it
        counts["kept"] += 1
    else:
        jobs_bundle.apply_tombstone(ctx.db, row.id)
        counts["deleted"] += 1


def _reconcile_one(ctx: _Ctx, row, label: str | None, counts: dict) -> None:
    if label == "remote":  # home says the job is ours: a committed offer, or a return that never landed
        _set_owner(ctx.db, [row.id], None)
        counts["owned"] += 1
    elif label == "home" and row.handover == "returning":  # a return that landed before the local flip
        _set_owner(ctx.db, [row.id], ctx.home_id)
        counts["replicas"] += 1
    elif label == "gone":
        _settle_gone(ctx, row, counts)


def _reconcile(ctx: _Ctx) -> dict:
    counts = {"owned": 0, "replicas": 0, "deleted": 0, "kept": 0}
    candidates = ctx.db.execute(select(Job.id, Job.handover, Job.owner_machine).where(
        or_(Job.owner_machine == ctx.home_id, Job.handover == "returning"))).all()
    for chunk in _chunks(candidates, OWNERSHIP_CHUNK):
        labels = _call(ctx, "POST", "/api/sync/ownership",
                       body={"job_ids": [row.id.hex for row in chunk]})
        for row in chunk:
            _reconcile_one(ctx, row, labels.get(row.id.hex), counts)
    return counts


# ------------------------------------------------------------------------------------- 5: profile


def _profile(ctx: _Ctx) -> dict:
    if ctx.paired_now:
        return {"applied": 1}
    since = status.read_state(ctx.db)["profile_rev"]
    answer = _call(ctx, "GET", "/api/sync/profile",
                   params=None if since is None else {"since": since})
    if answer.get("unchanged"):
        return {"applied": 0}
    ctx.db.commit()  # applying a profile wants a session with nothing pending
    try:
        rev = profile_bundle.apply_profile(ctx.db, answer)
    except ValueError:
        raise _Stop(_PROFILE, outcome=NEEDS_PERSON) from None
    status.update_state(ctx.db, profile_rev=rev)
    return {"applied": 1}


# ---------------------------------------------------------------------------------- 6: push jobs


@dataclass
class _Push:
    """One push in flight. ``retry`` maps a refused job's id to the rounds it has been refused;
    ``stuck`` maps a job refused ``RETRY_LIMIT`` times to home's sentence."""

    acked: int
    retry: dict
    stuck: dict
    top: int = 0
    counts: dict = field(default_factory=lambda: dict.fromkeys(
        ("sent", "refused", "skipped", "dropped", "kept_both", "deleted"), 0))


@dataclass
class _Page:
    bundles: list
    listed: dict  # job id (hex) -> the revision it had when the round listed it
    top: int
    skipped: int
    taken: int


def _hex(raw) -> str | None:
    job_id = _uuid(raw)
    return job_id.hex if job_id else None


def _export_one(db: Session, job_id) -> dict | None:
    try:
        return jobs_bundle.export_job(db, job_id, max_bytes=jobs_bundle.DEFAULT_MAX_BYTES)
    except (ValueError, LookupError):
        return None  # too large, a symlink, or gone since it was listed
    except OSError:
        raise _Stop(_CANT_READ, outcome=NEEDS_PERSON) from None


def _take_page(db: Session, rows: list) -> _Page:
    """Bundles of the leading rows, up to PUSH_JOBS and PAGE_BYTES but never fewer than one row.
    The page's top is the revision each row had when listed, never the exported one: a job edited
    since keeps a higher revision, so the next round sends it."""
    page, used = _Page([], {}, 0, 0, 0), 0
    for row in rows[:PUSH_JOBS]:
        bundle = _export_one(db, row.id)
        size = jobs_bundle.weight(bundle) if bundle else 0
        if page.taken and used + size > PAGE_BYTES:
            break
        page.taken, used = page.taken + 1, used + size
        page.listed[row.id.hex] = row.sync_rev
        page.top = max(page.top, row.sync_rev)
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


def _track_refusals(push: _Push, page: _Page, refused: dict) -> None:
    """A refused job is retried on later rounds and parked after RETRY_LIMIT; any job in the page
    that wasn't refused (or couldn't be sent at all) is no longer tracked."""
    for job_hex in page.listed:
        push.stuck.pop(job_hex, None)  # parked, then edited: it was tried again
        if job_hex not in refused:
            push.retry.pop(job_hex, None)
            continue
        attempts = push.retry.get(job_hex, 0) + 1
        if attempts >= RETRY_LIMIT:
            push.retry.pop(job_hex, None)
            push.stuck[job_hex] = refused[job_hex]
        else:
            push.retry[job_hex] = attempts


def _settle_push(ctx: _Ctx, answer: dict, page: _Page, push: _Push) -> None:
    refused = {_hex(item.get("job_id")): _answer_text(item.get("reason")) or _GENERIC
               for item in answer["refused"] if _hex(item.get("job_id")) in page.listed}
    _track_refusals(push, page, refused)
    push.counts["refused"] += len(answer["refused"])
    push.counts["sent"] += len(page.bundles) - len(refused)
    push.counts["deleted"] += len(answer.get("deleted", []))
    for item in answer["duplicates"]:
        if item.get("kept") == "laptop":
            _drop_duplicate(ctx, item["job_id"], push)
        else:
            push.counts["kept_both"] += 1


def _save_progress(ctx: _Ctx, push: _Push) -> None:
    push.acked = max(push.acked, push.top)
    status.update_state(ctx.db, acked_own=push.acked, retry_own=push.retry, stuck_own=push.stuck)


def _send_page(ctx: _Ctx, page: _Page, tombstones: list, push: _Push) -> None:
    if page.bundles or tombstones:
        answer = _call(ctx, "POST", "/api/sync/jobs",
                       body={"bundles": page.bundles, "tombstones": tombstones})
        _settle_push(ctx, answer, page, push)
    push.counts["skipped"] += page.skipped
    push.top = max(push.top, page.top)
    _save_progress(ctx, push)


def _still_mine(db: Session, tracked: dict) -> dict:
    """The tracked jobs that still exist here and are ours; a deleted or handed-over one is dropped."""
    ids = [job_id for job_id in map(_uuid, tracked) if job_id is not None]
    alive = {job_id.hex for job_id in db.scalars(select(Job.id).where(
        jobs_bundle.owned_clause(db), Job.id.in_(ids)))} if ids else set()
    return {job_hex: value for job_hex, value in tracked.items() if job_hex in alive}


def _listing(db: Session, push: _Push) -> list:
    """Own jobs changed since the ack, plus the refused ones waiting for another try."""
    wanted = Job.sync_rev > push.acked
    retry_ids = [job_id for job_id in map(_uuid, push.retry) if job_id is not None]
    if retry_ids:
        wanted = or_(wanted, Job.id.in_(retry_ids))
    return db.execute(select(Job.id, Job.sync_rev).where(jobs_bundle.owned_clause(db), wanted)
                      .order_by(Job.sync_rev, Job.id)).all()


def _push(ctx: _Ctx) -> dict:
    db = ctx.db
    saved = status.read_state(db)
    push = _Push(acked=saved["acked_own"], retry=_still_mine(db, saved["retry_own"]),
                 stuck=_still_mine(db, saved["stuck_own"]))
    rows = _listing(db, push)
    tombstones = [{"job_id": row.job_id.hex, "rev": row.rev} for row in db.scalars(
        select(SyncTombstone).where(SyncTombstone.rev > push.acked).order_by(SyncTombstone.rev))]
    deleted_top = max((item["rev"] for item in tombstones), default=0)
    while rows or tombstones:
        page = _take_page(db, rows)
        rows = rows[page.taken:]
        _send_page(ctx, page, tombstones, push)
        tombstones = []
    push.top = max(push.top, deleted_top)  # only now: every page before it has gone
    _save_progress(ctx, push)
    push.counts["stuck"] = len(push.stuck)
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


def _set_aside(ctx: _Ctx, job_id) -> None:
    """Park a home replica's text hash under a placeholder so another home job may take the text.
    Home's hashes are unique, so a replica that clashes holds a stale one; its own newer version
    brings the real hash when the pull reaches it."""
    with jobs_bundle.applying(ctx.db):
        ctx.db.get(Job, job_id).raw_text_hash = duplicates.stale_hash(job_id)


def _settle_clash(ctx: _Ctx, bundle: dict, local_id) -> str:
    db = ctx.db
    local = db.get(Job, local_id)
    if local is None:
        return "held"
    if local.owner_machine == ctx.home_id:
        return _replace_stale(ctx, bundle, local_id)
    if local.owner_machine not in (None, status.machine_id(db)):
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


def _replace_stale(ctx: _Ctx, bundle: dict, replica_id) -> str:
    _set_aside(ctx, replica_id)
    try:
        jobs_bundle.apply_job(ctx.db, bundle, sender_machine=ctx.home_id,
                              max_bytes=jobs_bundle.DEFAULT_MAX_BYTES)
        return "applied"
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
            raise _Stop(_UNREADABLE, outcome=NEEDS_PERSON)
        status.update_state(ctx.db, since_home=following)
        since = following
        if not page["more"]:
            break
    return counts


# ------------------------------------------------------------------------------ 8: requests both ways


def _answer_home_requests(ctx: _Ctx, counts: dict) -> None:
    """Answer home's unanswered requests. A repeat is answered from its local record, never applied
    again. A take-over waits for step 9, which decides it."""
    results = []
    for raw in _call(ctx, "GET", "/api/sync/requests"):
        item = request_apply.parse(raw)
        if item is None:
            counts["invalid"] += 1
        elif item.kind == "take_over" and ctx.db.get(SyncRequest, item.id) is None:
            ctx.takeovers.append(item)
        else:
            results.append(request_apply.answer(ctx.db, item))
    counts["answered"] += len(results)
    counts["refused"] += sum(result["status"] == "refused" for result in results)
    if results:
        _call(ctx, "POST", "/api/sync/request-results", body={"results": results})


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
            counts["applied_here"] += request_apply.settle_stored(ctx.db, row) == "applied"
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


def _set_handover(db: Session, job_id, value: str | None) -> None:
    with jobs_bundle.applying(db):
        db.get(Job, job_id).handover = value


def _hand_back(ctx: _Ctx, job_id) -> bool:
    """Send the job home. The job is already marked returning, so a failed call leaves a state the
    next round's reconcile reads against home's answer."""
    try:
        bundle = jobs_bundle.export_job(ctx.db, job_id, max_bytes=jobs_bundle.DEFAULT_MAX_BYTES)
    except (ValueError, LookupError, OSError):
        return False
    answer = _call(ctx, "POST", "/api/sync/handover/return", body={"bundles": [bundle]})
    return job_id.hex in answer["job_ids"]


def _return_refusal(ctx: _Ctx, item) -> tuple[str, str | None] | None:
    db = ctx.db
    job = db.get(Job, item.job_id) if item.job_id else None
    if job is None:
        return "refused", _NOT_HOLDING
    if job.owner_machine == ctx.home_id:  # already handed back, and the record never landed
        return "applied", None
    if job.owner_machine is not None and job.owner_machine != status.machine_id(db):
        return "refused", _NOT_HOLDING
    return None


def _decide_return(ctx: _Ctx, item) -> tuple[str, str | None]:
    """Grant or refuse one take-over; the decision is recorded in the same commit as its effect.
    The job is marked returning before the bot's own work is looked at, so no edit or run can slip
    in between the check and the hand-over."""
    settled = _return_refusal(ctx, item)
    if settled is not None:
        return settled
    _set_handover(ctx.db, item.job_id, "returning")
    if _mid_application(ctx.db, item.job_id):
        _set_handover(ctx.db, item.job_id, None)
        return "refused", BUSY_APPLYING
    if _hand_back(ctx, item.job_id):
        return "applied", None
    return "refused", _CANT_SEND_BACK


def _return_jobs(ctx: _Ctx, counts: dict) -> None:
    results = []
    for item in ctx.takeovers:
        outcome, reason = _decide_return(ctx, item)
        with jobs_bundle.applying(ctx.db):
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


def _waiting(state: dict) -> dict | None:
    """The skipped answer preserving the last failure's outcome during backoff, or None."""
    try:
        until = datetime.fromisoformat(state["next_attempt_at"]) if state["next_attempt_at"] else None
    except ValueError:
        return None
    if until is None or _now() >= until:
        return None
    reason = state["last_error"] or "The last sync failed."
    return _skipped(f"{reason} Next try at {until.isoformat()}.", state["last_outcome"] or TRANSIENT)


def _record_failure(db: Session, stop: _Stop) -> None:
    db.rollback()
    failures = status.read_state(db)["failures"] + 1
    delay = min(30, 5 * 2 ** min(failures - 1, 5))
    status.update_state(db, failures=failures, last_error=stop.text, last_outcome=stop.outcome,
                        attempted_at=_now().isoformat(),
                        next_attempt_at=(_now() + timedelta(minutes=delay)).isoformat())


def _guarded(ctx: _Ctx, options: _Options) -> None:
    _hello(ctx)
    _ensure_paired(ctx, options)
    for name, step in _STEPS:
        ctx.summary[name] = step(ctx)


def _stop_for(failure: Exception) -> _Stop:
    """The fixed sentence for a failure; what the failure said is never kept."""
    if isinstance(failure, _Stop):
        return failure
    if isinstance(failure, OSError):
        return _Stop(_DISK, outcome=NEEDS_PERSON)
    if isinstance(failure, (SQLAlchemyError, ValueError)):
        return _Stop(_LOCAL, outcome=TRANSIENT)
    return _Stop(_UNREADABLE, outcome=NEEDS_PERSON)


def _skipped(sentence: str, outcome: str) -> dict:
    return {"ok": False, "skipped": sentence, "outcome": outcome}


def _attempt(db: Session, http: httpx.Client, options: _Options) -> dict:
    ctx = _Ctx(db, http)
    try:
        _guarded(ctx, options)
    except _Skip as skip:
        db.rollback()
        if skip.remember:
            status.update_state(db, last_error=str(skip))
        return _skipped(str(skip), skip.outcome)
    except (OSError, _Stop, KeyError, TypeError, AttributeError, SQLAlchemyError,
            ValueError) as failure:
        stop = _stop_for(failure)
        try:
            _record_failure(db, stop)
        except SQLAlchemyError:
            db.rollback()
            stop = _Stop(_LOCAL, outcome=TRANSIENT)
        return {"ok": False, "outcome": stop.outcome, "error": stop.text, "steps": ctx.summary}
    status.update_state(db, failures=0, next_attempt_at=None, last_error=None, last_outcome=None,
                        last_ok=_now().isoformat(), attempted_at=_now().isoformat())
    return {"ok": True, "outcome": OK, "steps": ctx.summary}


def _just_ran(state: dict) -> bool:
    try:
        last = datetime.fromisoformat(state["attempted_at"]) if state["attempted_at"] else None
    except ValueError:
        return False
    return last is not None and timedelta(0) <= _now() - last < FORCE_GAP


def _held_off(state: dict, options: _Options) -> dict | None:
    """The skipped answer for a round that may not start yet, or None. A forced round skips the
    backoff window but not the half minute after the last attempt."""
    if options.force:
        return _skipped(SYNCED_JUST_NOW, state["last_outcome"] or TRANSIENT) if _just_ran(state) else None
    return _waiting(state)


def _locked_round(db: Session, options: _Options) -> dict:
    key = status.read_key()
    if key is None or not settings.sync_remote_url:
        return _skipped(NOT_SET_UP, NEEDS_PERSON)
    if (held := _held_off(status.read_state(db), options)) is not None:
        return held
    with http_client.new_client(base_url=settings.sync_remote_url, headers=_headers(db, key),
                                timeout=_TIMEOUT) as http:
        return _attempt(db, http, options)


def run_round(db: Session, *, force: bool = False, pair: bool = False,
              accept_profile_overwrite: bool = False) -> dict:
    """Run one round and return its per-step counts and an ``outcome`` (``ok``, ``transient`` or
    ``needs_person``). ``force`` ignores the backoff window, but not the 30 s after an attempt; ``pair``
    allows the first round; ``accept_profile_overwrite`` lets a first round replace this copy's
    profile. Raises RoundBusy when a round is already running here."""
    if not _LOCK.acquire(blocking=False):
        raise RoundBusy
    try:
        return _locked_round(db, _Options(force, pair, accept_profile_overwrite))
    finally:
        _LOCK.release()
