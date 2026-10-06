"""Is a job in the Agent inbox ready to send? Read-only: worked out when the inbox list is read,
never stored, so a profile edit or a new receipt shows at once.

Ready means tailored (the linked application has a PDF), no knock-out conflict, and nothing to
check in the recorded answers. Phase 4's auto-submit reads `is_ready`, so the rule lives here
once. Only open-lane rows get readiness; History rows get none.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.application_proposal import ApplicationProposal
from app.models.filled_answer import FilledAnswer
from app.models.job import Job
from app.models.types import utcnow
from app.services import eeo_consent, filled_answers, knockout
from app.services.proposals import APPLIED_MANUALLY, OPEN_STATUSES

logger = logging.getLogger(__name__)
Pair = tuple[ApplicationProposal, Job]
NEW_WINDOW = timedelta(hours=24)
WEEK = timedelta(days=7)
NEEDS_YOU = ("needs_decision", "needs_human")


def is_ready(readiness: dict[str, Any] | None) -> bool:
    if not readiness:
        return False
    return (readiness["tailored"] is True and readiness["knockout"] is None
            and readiness["to_check"] == 0)


def _pdf_ready(session: Session, pairs: list[Pair]) -> dict[UUID, bool]:
    ids = [p.application_id for p, _ in pairs if p.application_id is not None]
    if not ids:
        return {}
    rows = session.execute(select(Application.id, Application.pdf_path)
                           .where(Application.id.in_(ids))).all()
    return {app_id: bool(path) for app_id, path in rows}


def _answered(session: Session, pairs: list[Pair]) -> set[UUID]:
    ids = [job.id for _, job in pairs]
    return set(session.scalars(select(FilledAnswer.job_id)
                               .where(FilledAnswer.job_id.in_(ids)).distinct()))


def _knockout(job: Job, args: dict[str, Any]) -> str | None:
    scan = knockout.scan_job(job, **args)
    if scan["status"] != "conflict":
        return None
    return next((c["kind"] for c in scan["checks"] if c["result"] == "conflict"), None)


class _Batch:
    """What every row's readiness reads, loaded once."""

    def __init__(self, session: Session, pairs: list[Pair]):
        self.session = session
        self.scan = knockout.scan_args(session)
        self.pdfs = _pdf_ready(session, pairs)
        self.answered = _answered(session, pairs)
        self.profile = eeo_consent.disclosable_profile(session) if self.answered else None

    def row(self, prop: ApplicationProposal, job: Job) -> dict[str, Any]:
        to_check = (filled_answers.flag_count(self.session, job, self.profile)
                    if job.id in self.answered else 0)
        return {"tailored": self.pdfs.get(prop.application_id) if prop.application_id else None,
                "knockout": _knockout(job, self.scan), "to_check": to_check}


def for_proposals(session: Session, pairs: list[Pair]) -> dict[UUID, dict[str, Any] | None]:
    """Readiness per open proposal id. A row that fails is None (logged); the rest still read."""
    pairs = [(p, j) for p, j in pairs if p.status in OPEN_STATUSES]
    if not pairs:
        return {}
    try:
        batch = _Batch(session, pairs)
    except Exception:  # noqa: BLE001 - one failed batch read must not blank the inbox
        logger.warning("readiness batch skipped for %s proposals", len(pairs), exc_info=True)
        return {prop.id: None for prop, _job in pairs}
    out: dict[UUID, dict[str, Any] | None] = {}
    for prop, job in pairs:
        try:
            out[prop.id] = batch.row(prop, job)
        except Exception:  # noqa: BLE001 - one bad row must not blank the inbox
            logger.warning("readiness skipped for proposal %s", prop.id, exc_info=True)
            out[prop.id] = None
    return out


def _count(session: Session, *where) -> int:
    return session.scalar(select(func.count(ApplicationProposal.id)).where(*where)) or 0


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def summary(session: Session, since: datetime | None = None) -> dict[str, Any]:
    """The arrivals strip: new since `since` (default the last day), ready to apply, needs you,
    applied this week (submitted by an agent or applied by the user)."""
    now = utcnow()
    since = _as_utc(since) if since else now - NEW_WINDOW
    queued = session.execute(
        select(ApplicationProposal, Job)
        .join(Job, Job.id == ApplicationProposal.job_id)
        .where(ApplicationProposal.status == "accepted")
    ).all()
    applied = or_(
        ApplicationProposal.status == "submitted",
        and_(ApplicationProposal.status == "rejected",
             ApplicationProposal.reason == APPLIED_MANUALLY),
    )
    return {
        "since": since,
        "new": _count(session, ApplicationProposal.created_at > since),
        "ready": sum(is_ready(r) for r in for_proposals(session, [tuple(r) for r in queued]).values()),
        "needs_you": _count(session, ApplicationProposal.status.in_(NEEDS_YOU)),
        "applied_this_week": _count(session, applied, ApplicationProposal.updated_at >= now - WEEK),
    }
