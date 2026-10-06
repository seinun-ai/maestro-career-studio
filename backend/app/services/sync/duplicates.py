"""The same job text on both copies (design Part A, duplicates).

`jobs.raw_text_hash` is unique, so a job whose text another local job already holds cannot be
stored as it is. The laptop's job wins: when the other side's job has no work on it, it is dropped
(``laptop``). When it has progressed, both are kept and the replica's hash is rewritten to one
derived from its own id (``both``). That rewrite must be repeated before every later apply of the
same job, or the unique index refuses it again.
"""

import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.job import Job
from app.services.sync import jobs_bundle, status, wire


def replica_hash(job_id: uuid.UUID) -> str:
    return hashlib.sha256(f"replica:{job_id.hex}".encode()).hexdigest()


def stale_hash(job_id: uuid.UUID) -> str:
    """A placeholder text hash, distinct from ``replica_hash``, for a replica whose own hash
    another job of the sender has taken."""
    return hashlib.sha256(f"stale:{job_id.hex}".encode()).hexdigest()


class ReplicaClash(Exception):
    """The text belongs to a replica of the sender's own: that job is on its way out or in; retry."""


@dataclass(frozen=True)
class Outcome:
    """``applied`` (stored), ``laptop`` (dropped, the other job kept) or ``both`` (stored under a
    rewritten hash). ``local_id`` is the other job for the last two."""

    kind: str
    local_id: uuid.UUID | None = None


def has_progressed(bundle: dict) -> bool:
    """An application, or a proposal past pending_review, exists for the job."""
    for item in bundle["rows"]:
        if item["table"] == "applications":
            return True
        if item["table"] == "application_proposals" and item["row"]["status"] != "pending_review":
            return True
    return False


def with_replica_hash(bundle: dict) -> dict:
    """A copy of the bundle whose job row carries the replica hash; the argument is untouched."""
    job_id = uuid.UUID(bundle["job_id"])
    rows = [{**item, "row": {**item["row"], "raw_text_hash": replica_hash(job_id)}}
            if item["table"] == "jobs" else item for item in bundle["rows"]]
    return {**bundle, "rows": rows}


def _stored_with_replica_hash(db: Session, job_id: uuid.UUID) -> bool:
    return db.scalar(select(Job.raw_text_hash).where(Job.id == job_id)) == replica_hash(job_id)


def for_stored(db: Session, bundle: dict) -> dict:
    """The bundle as it must be applied here: with the replica hash when the job is stored under it."""
    job_id = wire.bundle_job_id(bundle)
    if job_id is not None and _stored_with_replica_hash(db, job_id):
        return with_replica_hash(bundle)
    return bundle


def _owned_here(db: Session, job_id: uuid.UUID) -> bool:
    owner = db.scalar(select(Job.owner_machine).where(Job.id == job_id))
    return owner is None or owner == status.machine_id(db)


def apply_replica(db: Session, bundle: dict, *, sender_machine: str, max_bytes: int) -> Outcome:
    """Apply a bundle as a replica, settling a text clash by the rule above. Raises what
    ``jobs_bundle.apply_job`` raises, except DuplicateJob; raises ReplicaClash when the clashing job
    is a replica of a machine's own rather than this copy's."""
    bundle = for_stored(db, bundle)
    try:
        jobs_bundle.apply_job(db, bundle, sender_machine=sender_machine, max_bytes=max_bytes)
    except jobs_bundle.DuplicateJob as clash:
        if not _owned_here(db, clash.local_id):
            raise ReplicaClash from None
        if not has_progressed(bundle):
            return Outcome("laptop", clash.local_id)
        jobs_bundle.apply_job(db, with_replica_hash(bundle), sender_machine=sender_machine,
                              max_bytes=max_bytes)
        return Outcome("both", clash.local_id)
    return Outcome("applied")
