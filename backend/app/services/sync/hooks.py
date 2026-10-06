"""Track revisions and enforce one writer per job/profile on every ORM flush."""

import uuid
from dataclasses import dataclass, field

from sqlalchemy import event, inspect, select, text
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_dirty

from app.db import Base
from app.models.job import Job
from app.models.career_kb import KBEntity, KBPoint
from app.models.setting import Setting
from app.models.sync import SyncRequest, SyncState, SyncTombstone
from app.models.types import utcnow
from app.services.sync import registry, status

UNRESOLVED_MESSAGE = "Maestro couldn't tell which job this change belongs to, so it wasn't saved."
PROFILE_MESSAGE = "Your laptop keeps your profile. Change it there."


class NotOwnedHere(Exception):
    """A write belongs to the other copy; never carries row contents."""

    def __init__(self, message: str, owner: str | None = None):
        super().__init__(message)
        self.owner = owner or ("laptop" if status.is_remote() else "bot")


def _job_of(session: Session, job_id: uuid.UUID) -> Job | None:
    return next((row for row in session.new if isinstance(row, Job) and row.id == job_id),
                None) or session.get(Job, job_id)


def _ownership(session: Session, job: Job) -> tuple[str | None, str | None]:
    # Check persisted ownership too: editing owner_machine must not unlock a replica.
    if job in session.new:
        return job.owner_machine, job.handover
    return tuple(session.execute(select(Job.owner_machine, Job.handover)
                                 .where(Job.id == job.id)).one())


def owned_here(session: Session, job_id: uuid.UUID) -> bool:
    """Reads that write skip replicas and offers; sync off admits every job."""
    if not status.enabled():
        return True
    with session.no_autoflush:
        job = _job_of(session, job_id)
        if job is None:
            return False
        owner, handover = _ownership(session, job)
        return (owner is None or owner == status.machine_id(session)) and (
            status.is_remote() or handover != "offered")


def require_owned(session: Session, job_id: uuid.UUID) -> None:
    """Check before a route writes files; the flush hook checks again at commit."""
    if not status.enabled() or session.info.get("sync_apply"):
        return
    if _job_of(session, job_id) is None:
        raise NotOwnedHere(UNRESOLVED_MESSAGE)
    if not owned_here(session, job_id):
        message = ("This job is on your laptop; work on it there." if status.is_remote()
                   else "This job is with your bot; ask for it back with Work on it here.")
        raise NotOwnedHere(message)


def require_profile_writable(session: Session) -> None:
    """Refuse remote profile file writes before any disk side effect."""
    if status.is_remote() and not session.info.get("sync_apply"):
        raise NotOwnedHere(PROFILE_MESSAGE, "laptop")


def seed_setting(session: Session, row: Setting) -> None:
    """Commit one first-read default with a row-specific, scoped exception."""
    enabled = status.enabled()
    if enabled:
        session.info["setting_seed"] = True
        session.info["sync_guard_setting_rows"] = {row}
    try:
        session.add(row)
        session.commit()
    finally:
        if enabled:
            session.info.pop("setting_seed", None)
            session.info.pop("sync_guard_setting_rows", None)


@dataclass
class TouchedRows:
    jobs: set[uuid.UUID] = field(default_factory=set)
    profile: bool = False
    unresolved: list[Base] = field(default_factory=list)


def _ensure_clock(session: Session) -> None:
    session.execute(text(
        "INSERT INTO sync_state (name, value) VALUES ('clock', 0) "
        "ON CONFLICT(name) DO NOTHING"
    ))


def _expire_state(session: Session, name: str) -> None:
    row = session.identity_map.get((SyncState, (name,), None))
    if row is not None:
        session.expire(row, ["value"])


def _advance_clock(session: Session) -> int:
    _ensure_clock(session)
    value = session.execute(text(
        "UPDATE sync_state SET value = value + 1 WHERE name='clock' RETURNING value"
    )).scalar_one()
    _expire_state(session, "clock")
    return value


def _stamp_profile(session: Session, rev: int) -> None:
    session.execute(text(
        "INSERT INTO sync_state (name, value) VALUES ('profile_rev', :rev) "
        "ON CONFLICT(name) DO UPDATE SET value=excluded.value"
    ), {"rev": rev})
    _expire_state(session, "profile_rev")


def _force_flush(session: Session) -> None:
    # before_flush does not run for an otherwise clean session after a Core write.
    with session.no_autoflush:
        _ensure_clock(session)
        flag_dirty(session.get(SyncState, "clock"))


def touch_job(session: Session, job_id: uuid.UUID) -> None:
    """Include a Core writer's job in the next flush, even without ORM changes."""
    session.info.setdefault("sync_touch_jobs", set()).add(job_id)
    _force_flush(session)


def touch_profile(session: Session) -> None:
    """Include a Core profile write in the next flush, even without ORM changes."""
    session.info["sync_touch_profile"] = True
    _force_flush(session)


def collect_touched(session: Session, parents: dict) -> TouchedRows:
    """Collect every modified subtree and keep unresolved rows for the guard."""
    touched = TouchedRows(set(session.info.get("sync_touch_jobs", ())),
                          bool(session.info.get("sync_touch_profile")))
    rows = (session.new | session.deleted).union(
        obj for obj in session.dirty if session.is_modified(obj)
    )
    for obj in rows:
        classification = registry.TABLES.get(obj.__table__.name)
        if registry.is_profile_row(obj):
            touched.profile = True
        if classification not in (registry.JOB, "by_kind"):
            continue
        touched.jobs.update(registry.job_ids_of(session, obj, parents))
        if not registry.is_profile_row(obj) and registry.job_id_of(session, obj, parents) is None:
            touched.unresolved.append(obj)
    return touched


def _tombstone(session: Session, job_id: uuid.UUID, rev: int) -> None:
    row = session.get(SyncTombstone, job_id)
    if row is None:
        session.add(SyncTombstone(job_id=job_id, rev=rev))
    else:
        row.rev, row.deleted_at = rev, utcnow()


def _stamp_jobs(session: Session, touched: TouchedRows, rev: int) -> None:
    jobs = {obj.id: obj for obj in session.new | session.dirty | session.deleted
            if isinstance(obj, Job)}
    for job_id in touched.jobs:
        job = jobs.get(job_id)
        if job is None:
            job = session.get(Job, job_id)
        if job in session.deleted:
            _tombstone(session, job_id, rev)
        elif job is not None:
            job.sync_rev = rev


def _clear_touches(session: Session) -> None:
    session.info.pop("sync_touch_jobs", None)
    session.info.pop("sync_touch_profile", None)


def _after_rollback(session: Session) -> None:
    for key in list(session.info):
        if key.startswith(("sync_touch_", "sync_guard_")) or key == "sync_unresolved":
            session.info.pop(key, None)


@event.listens_for(Session, "after_transaction_end")
def _after_transaction_end(session: Session, transaction) -> None:
    if transaction.parent is None:
        _after_rollback(session)


def _changed_rows(session: Session) -> set:
    return set(session.new | session.deleted).union(
        row for row in session.dirty if session.is_modified(row))


def _only_cancel_offer(session: Session, job: Job) -> bool:
    if session.info.get("sync_touch_jobs") or session.info.get("sync_touch_profile"):
        return False
    if job in session.new or job in session.deleted or job.handover is not None:
        return False
    changed = {attr.key for attr in inspect(job).attrs if attr.history.has_changes()}
    return _changed_rows(session) == {job} and changed == {"handover"}


def _guard_jobs(session: Session, touched: TouchedRows) -> None:
    if touched.unresolved:
        raise NotOwnedHere(UNRESOLVED_MESSAGE)
    for job_id in touched.jobs:
        job = _job_of(session, job_id)
        if job is not None:
            owner, handover = _ownership(session, job)
            if owner in (None, status.machine_id(session)) and handover == "offered":
                if not status.is_remote() and _only_cancel_offer(session, job):
                    continue
        require_owned(session, job_id)


def _is_holder(row: Base) -> bool:
    return isinstance(row, KBEntity) and (
        row.kind == "extra" and row.title == "Unconfirmed claims" and row.status == "archived"
        and row.origin == "gap_elicitation" and row.detail_json == {"holder": "cannot_confirm"})


def _profile_before_change(session: Session, row: Base) -> bool:
    if registry.is_profile_row(row):
        return True
    if row not in session.dirty:
        return False
    table = row.__table__.name
    if registry.TABLES.get(table) == "by_kind":
        return "base" in registry._previous_values(session, row, "resume_kind")
    if isinstance(row, Setting):
        return any(isinstance(key, str) and not key.startswith(registry.LOCAL_SETTING_PREFIXES)
                   for key in registry._previous_values(session, row, "key"))
    return False


def _allowed_profile_insert(session: Session, row: Base) -> bool:
    if row not in session.new:
        return False
    if isinstance(row, Setting):
        return bool(session.info.get("setting_seed")) and row in session.info.get(
            "sync_guard_setting_rows", ())
    return _is_holder(row) or (isinstance(row, KBPoint) and row.provenance == "user_cannot_confirm")


def _queue_addition(session: Session, point: KBPoint) -> None:
    queued = session.info.setdefault("sync_guard_additions", set())
    if point in queued:
        return
    holder = point.entity or session.get(KBEntity, point.entity_id)
    payload = None
    if _is_holder(holder):
        payload = {key: getattr(holder, key) for key in
                   ("kind", "title", "status", "origin", "detail_json")}
    session.add(SyncRequest(kind="profile_addition", origin="local",
                            payload_json={"claim": point.text, "holder": payload}))
    queued.add(point)


def _guard_profile(session: Session, touched: TouchedRows) -> None:
    if not status.is_remote():
        return
    rows = [row for row in _changed_rows(session) if _profile_before_change(session, row)]
    if session.info.get("sync_touch_profile"):
        raise NotOwnedHere(PROFILE_MESSAGE, "laptop")
    for row in rows:
        if not _allowed_profile_insert(session, row):
            raise NotOwnedHere(PROFILE_MESSAGE, "laptop")
    for row in rows:
        if isinstance(row, KBPoint):
            _queue_addition(session, row)


def _guard(session: Session, touched: TouchedRows) -> None:
    if not status.enabled() or session.info.get("sync_apply"):
        return
    _guard_jobs(session, touched)
    _guard_profile(session, touched)


def _before_flush(session: Session, flush_context, instances) -> None:
    with session.no_autoflush:
        for obj in session.new:
            if isinstance(obj, Job) and obj.id is None:
                obj.id = uuid.uuid4()
        parents = registry.pending_parents(session)
        touched = collect_touched(session, parents)
        session.info["sync_unresolved"] = touched.unresolved
        _guard(session, touched)
        if touched.jobs or touched.profile:
            rev = _advance_clock(session)
            _stamp_jobs(session, touched, rev)
            if touched.profile:
                _stamp_profile(session, rev)
        _clear_touches(session)
