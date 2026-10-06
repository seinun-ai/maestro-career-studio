"""Queueing a job with full automation on offers it to the always-on copy at the next round."""

from sqlalchemy.orm import Session

from app.models.application_proposal import ApplicationProposal
from app.models.job import Job
from app.services import auto_apply_settings
from app.services.sync import status


def mark_when_queued(db: Session, prop: ApplicationProposal) -> None:
    """Flag the proposal's job `offered` on the laptop; the commit that saves the queue saves this.

    Only the laptop offers, only a job it still owns outright, and only with the user's
    full-automation switch on. Keep it here clears the flag; the next round hands the job over.
    """
    if prop.status != "accepted" or not status.enabled() or status.is_remote():
        return
    if not auto_apply_settings.peek_settings(db).full_automation:
        return
    job = db.get(Job, prop.job_id)
    if job is None or job.handover is not None:
        return
    if job.owner_machine in (None, status.machine_id(db)):
        job.handover = "offered"
