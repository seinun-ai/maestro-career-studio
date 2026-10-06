"""Queueing a job with full automation on offers it to the always-on copy at the next round.

Switching full automation off withdraws every offer that has not moved yet.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.application_proposal import ApplicationProposal
from app.models.job import Job
from app.services import auto_apply_settings
from app.services.sync import hooks, jobs_bundle, status


def mark_when_queued(db: Session, prop: ApplicationProposal) -> None:
    """Flag the proposal's job `offered` on the laptop; the commit that saves the queue saves this.

    Only the laptop offers, only a job it still owns outright, and only with the user's
    full-automation switch on. Keep it here clears the flag; the next round hands the job over.
    """
    if prop.status != "accepted" or not status.enabled() or status.is_remote():
        return
    if not offers_open(db):
        return
    job = db.get(Job, prop.job_id)
    if job is None or job.handover is not None:
        return
    if job.owner_machine in (None, status.machine_id(db)):
        job.handover = "offered"


def offers_open(db: Session) -> bool:
    """Whether this copy may hand jobs over: the user's switch is on."""
    return auto_apply_settings.peek_settings(db).full_automation


@contextmanager
def withdrawing(db: Session) -> Iterator[None]:
    """Clear `offered` on this copy's own jobs; the caller's commit saves the switch with them.

    The ownership guard stands aside for the commit (an offered job is otherwise read-only), and
    the normal hook still bumps each job's rev so the withdrawal syncs.
    """
    if not status.enabled() or status.is_remote():
        yield
        return
    with hooks.standing_aside(db):
        for job in db.scalars(select(Job).where(jobs_bundle.owned_clause(db),
                                                Job.handover == "offered")):
            job.handover = None
        yield
