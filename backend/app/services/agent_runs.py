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
from app.services import automations, proposals
from app.services.sync import hooks, request_apply
from app.services.sync import status as sync_status

MAX_RUNS = 200
# The peer can return arbitrary text. Only the fixed sentences this app itself produces may reach
# the web app, named here from the modules that write them (a test fails when one is missing).
_SAFE_REQUEST_REASONS = frozenset({
    request_apply.REQUEST_FAILED, request_apply.BUSY_APPLYING, request_apply.NOT_HOLDING,
    request_apply.CANT_SEND_BACK, request_apply.NOT_HERE_ON_HOME, request_apply.NOT_HERE_ON_REMOTE,
    request_apply.MOVING, request_apply.WRONG_JOB, request_apply.BAD_PAYLOAD,
    request_apply.NO_TAKE_OVER, request_apply.UNKNOWN_KIND, request_apply.NOT_REPEATABLE,
    hooks.RETURNING_MESSAGE, hooks.UNRESOLVED_MESSAGE, hooks.PROFILE_MESSAGE,
    hooks.ON_LAPTOP_MESSAGE, hooks.OFFERED_MESSAGE, hooks.WITH_BOT_MESSAGE,
    proposals.COMPANY_BLOCKED,
    *(proposals.not_allowed_message(status) for status in proposals.STATUS_CHIP_WORDS),
})
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
        select(SyncRequest.id, SyncRequest.job_id, SyncRequest.reason, SyncRequest.answered_at,
               Job.company, Job.title)
        .outerjoin(Job, Job.id == SyncRequest.job_id)
        .where(SyncRequest.origin == "local", SyncRequest.status == "refused")
        .order_by(SyncRequest.answered_at.desc(), SyncRequest.created_at.desc(), SyncRequest.id.desc())
        .limit(20))
    return [{"id": row.id, "job_id": row.job_id, "answered_at": row.answered_at,
             "job_company": row.company, "job_title": row.title,
             "reason": row.reason if row.reason in _SAFE_REQUEST_REASONS else request_apply.REQUEST_FAILED}
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
