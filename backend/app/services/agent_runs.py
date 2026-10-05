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
from app.models.types import utcnow
from app.schemas.agent_runs import MAX_DIGEST, AgentRunCreate
from app.services import automations

MAX_RUNS = 200
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
    return [{"id": run.id, "automation": run.automation,
             "title": titles.get(run.automation, run.automation), "outcome": run.outcome,
             "agent": run.agent, "finished_at": run.finished_at, "counts": run.counts,
             "digest": run.digest,
             "jobs": [{"id": job.id, "title": job.title, "company": job.company}
                      for job in (jobs.get(UUID(i)) for i in run.job_ids) if job is not None]}
            for run in runs]


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
