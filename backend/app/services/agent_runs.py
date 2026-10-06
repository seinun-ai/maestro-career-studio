"""The run log: what each automation run reported (MCP `record_run`), for the Agent inbox's
Recent runs panel and the Automations page's Last ran line.

Maestro runs no scheduler and cannot tell a late run from a skipped one, so nothing here says
"overdue". The digest is the agent's own text: Maestro cannot check it holds no email text
(docs/entities/agent-runs.md).
"""

from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.agent_run import AgentRun
from app.models.job import Job
from app.models.sync import SyncRequest
from app.models.types import utcnow
from app.schemas.agent_runs import MAX_DIGEST, AgentRunCreate
from app.services import automations
from app.services.sync import status as sync_status

MAX_RUNS = 200
_REQUEST_FAILED = "Maestro couldn't apply this request."
# The peer can return arbitrary text. Only these complete, fixed sentences may reach the web app.
_SAFE_REQUEST_REASONS = frozenset({
    _REQUEST_FAILED,
    "Your bot is applying to this one; try again after its run.",
    "This job isn't on your laptop.",
    "This job isn't on this copy.",
    "This job is moving to your bot; make the change there once it arrives.",
    "That doesn't belong to this job.",
    "This request wasn't valid.",
    "A job on your laptop is handed over from your laptop.",
    "Maestro doesn't know that kind of request.",
    "This request can't be repeated.",
    "This job is on your laptop; work on it there.",
    "This job is with your bot; ask for it back with Work on it here.",
    "This job is on its way to your bot. Use Keep it here to keep working on it.",
    "This job has no tailored resume to link yet. Tailor one first, then try again.",
    "That application no longer exists.",
    "This job is going back to your laptop. Make the change there after the next sync.",
    "This company is on your Companies to skip list in Settings › Connected agents",
})
_SAFE_REQUEST_REASONS |= frozenset(
    f"This proposal's status is {word}, so it can't be changed that way."
    for word in ("Proposed", "Needs you", "Queued", "Approved", "Applied", "Check if sent", "Skipped", "Expired")
)
__all__ = ["MAX_DIGEST", "MAX_RUNS", "latest", "recent", "record", "read_one"]


def _known(session: Session, ids: list[UUID]) -> set[UUID]:
    if not ids:
        return set()
    return set(session.scalars(select(Job.id).where(Job.id.in_(ids))))


def _prune(session: Session, keep_id: UUID) -> None:
    keep = (select(AgentRun.id).where(AgentRun.id != keep_id)
            .order_by(AgentRun.finished_at.desc(), AgentRun.id.desc())
            .limit(max(0, MAX_RUNS - 1)))
    session.execute(delete(AgentRun).where(AgentRun.id != keep_id, AgentRun.id.not_in(keep)))


def record(session: Session, payload: AgentRunCreate, agent: str | None) -> AgentRun:
    known = _known(session, payload.job_ids)
    run = AgentRun(automation=payload.automation, outcome=payload.outcome, agent=agent,
                   finished_at=utcnow(), counts=dict(payload.counts), digest=payload.digest,
                   job_ids=[str(i) for i in payload.job_ids if i in known])
    session.add(run)
    session.flush()
    _prune(session, run.id)
    session.commit()
    session.refresh(run)
    return run


def _newest(session: Session, limit: int) -> list[AgentRun]:
    return list(session.scalars(
        select(AgentRun).order_by(AgentRun.finished_at.desc(), AgentRun.id.desc()).limit(limit)))


def _jobs_by_id(session: Session, runs: list[AgentRun]) -> dict[UUID, Job]:
    ids = {UUID(i) for run in runs for i in run.job_ids}
    if not ids:
        return {}
    return {job.id: job for job in session.scalars(select(Job).where(Job.id.in_(ids)))}


def _read(runs: list[AgentRun], session: Session) -> list[dict[str, Any]]:
    titles = {card.id: card.title for card in automations.catalog().cards}
    jobs = _jobs_by_id(session, runs)
    sync_enabled = sync_status.enabled()
    return [{"id": run.id, "automation": run.automation,
             "title": titles.get(run.automation, run.automation), "outcome": run.outcome,
             "agent": run.agent, "on_bot": sync_enabled and run.machine is not None,
             "finished_at": run.finished_at, "counts": run.counts,
             "digest": run.digest,
             "jobs": [{"id": job.id, "title": job.title, "company": job.company}
                      for job in (jobs.get(UUID(i)) for i in run.job_ids) if job is not None]}
            for run in runs]


def refused_requests(session: Session) -> list[dict[str, Any]]:
    """Recent refusals of this viewer's requests, without opening the peer sync channel."""
    if not sync_status.enabled():
        return []
    rows = session.execute(
        select(SyncRequest.id, SyncRequest.job_id, SyncRequest.reason, SyncRequest.answered_at)
        .where(SyncRequest.origin == "local", SyncRequest.status == "refused")
        .order_by(SyncRequest.answered_at.desc(), SyncRequest.created_at.desc(), SyncRequest.id.desc())
        .limit(20))
    return [{"id": row.id, "job_id": row.job_id, "answered_at": row.answered_at,
             "reason": row.reason if row.reason in _SAFE_REQUEST_REASONS else _REQUEST_FAILED}
            for row in rows]


def recent(session: Session, limit: int = 20) -> list[dict[str, Any]]:
    return _read(_newest(session, limit), session)


def latest(session: Session) -> list[dict[str, Any]]:
    """The newest run of each automation, newest first (the table holds at most MAX_RUNS)."""
    seen: dict[str, AgentRun] = {}
    for run in _newest(session, MAX_RUNS):
        seen.setdefault(run.automation, run)
    return _read(list(seen.values()), session)


def read_one(session: Session, run: AgentRun) -> dict[str, Any]:
    return _read([run], session)[0]
