"""Who owns each job, as the viewer reads it: the wire view behind every `ownership` field."""

from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.job import Job
from app.models.sync import SyncRequest
from app.schemas.job import JobOwnership
from app.services.sync import status


def stamp(db: Session, jobs: Iterable[Job]) -> None:
    """Set `job.ownership` on every row from the rows' own columns.

    The key file, the machine id and the pending-request counts are each read once per call,
    whatever the number of jobs; `hooks.owned_here` is the same rule asked of one job at a time.
    """
    rows = list(jobs)
    if not rows:
        return
    mode = status.mode()
    if mode == "off":
        for job in rows:
            job.ownership = JobOwnership()
        return
    remote = mode == "remote"
    local_id = status.machine_id(db)
    refused = "returning" if remote else "offered"
    pending = dict(db.execute(
        select(SyncRequest.job_id, func.count(SyncRequest.id))
        .where(SyncRequest.job_id.in_({job.id for job in rows}), SyncRequest.origin == "local",
               SyncRequest.status.in_(("pending", "sent")))
        .group_by(SyncRequest.job_id)).all())
    for job in rows:
        local = job.owner_machine in (None, local_id)
        job.ownership = JobOwnership(
            owned_here=local and job.handover != refused,
            owner="bot" if local == remote else "laptop",
            handover=job.handover, pending_requests=pending.get(job.id, 0),
            can_keep_here=not remote and local and job.handover == "offered")
