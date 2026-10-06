"""Track local job/profile revisions on every ORM flush; the ownership guard is off."""

import uuid
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_dirty

from app.db import Base
from app.models.job import Job
from app.models.sync import SyncState, SyncTombstone
from app.models.types import utcnow
from app.services.sync import registry


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
    """Collect every modified subtree and keep unresolved rows for the future guard."""
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
    _clear_touches(session)
    session.info.pop("sync_unresolved", None)


def _before_flush(session: Session, flush_context, instances) -> None:
    with session.no_autoflush:
        for obj in session.new:
            if isinstance(obj, Job) and obj.id is None:
                obj.id = uuid.uuid4()
        parents = registry.pending_parents(session)
        touched = collect_touched(session, parents)
        session.info["sync_unresolved"] = touched.unresolved
        if touched.jobs or touched.profile:
            rev = _advance_clock(session)
            _stamp_jobs(session, touched, rev)
            if touched.profile:
                _stamp_profile(session, rev)
        _clear_touches(session)
