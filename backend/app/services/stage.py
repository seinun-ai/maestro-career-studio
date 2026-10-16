"""One ladder behind every job: the rung the Jobs list and the job page show as Next step.
Read-only; computed per request from rows that already exist (SYSTEM.md §5 step 2)."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.job import Job
from app.models.tailoring_session import TailoringSession
from app.services import ats_score
from app.services.application_status import SUBMITTED_STAGES

RUNGS = ("saved", "scored", "gaps", "tailored", "pdf_ready", "applied")


@dataclass(frozen=True)
class Stage:
    rung: str
    open_session_id: UUID | None = None
    gaps_done: int = 0
    gaps_total: int = 0


def _gap_counts(session: TailoringSession) -> tuple[int, int]:
    """Answered plus skipped over every listed gap: the gap page's own count
    (frontend/lib/gap-counts.ts). A resolution for a gap the analysis no longer
    lists counts for nothing."""
    ids = {
        g["gap_id"]
        for c in (session.gaps_json or {}).get("categories", [])
        for g in c.get("gaps", [])
    }
    resolved = {r.get("gap_id") for r in (session.resolutions_json or [])}
    return len(ids & resolved), len(ids)


def _open_sessions(db: Session, job_ids: list[UUID]) -> dict[UUID, TailoringSession]:
    newest: dict[UUID, TailoringSession] = {}
    for s in db.scalars(
        select(TailoringSession)
        .where(TailoringSession.job_id.in_(job_ids), TailoringSession.status == "open")
        .order_by(TailoringSession.created_at.desc(), TailoringSession.id.desc())
    ):
        newest.setdefault(s.job_id, s)
    return newest


def _gaps_or(job_id: UUID, open_by_job: dict[UUID, TailoringSession], scored: set[UUID]) -> Stage:
    s = open_by_job.get(job_id)
    if s is not None:
        done, total = _gap_counts(s)
        return Stage("gaps", s.id, done, total)
    return Stage("scored" if job_id in scored else "saved")


def for_jobs(db: Session, jobs: list[Job]) -> dict[UUID, Stage]:
    ids = [j.id for j in jobs]
    if not ids:
        return {}
    open_by_job = _open_sessions(db, ids)
    scored = set(ats_score.best_base_scores(db, ids))
    return {j.id: _gaps_or(j.id, open_by_job, scored) for j in jobs}


def for_applications(db: Session, apps: list[Application]) -> dict[UUID, Stage]:
    if not apps:
        return {}
    job_ids = list({a.job_id for a in apps})
    open_by_job = _open_sessions(db, job_ids)
    scored = set(ats_score.best_base_scores(db, job_ids))
    out: dict[UUID, Stage] = {}
    for a in apps:
        if a.applied_at is not None or (a.status or "") in SUBMITTED_STAGES:
            out[a.id] = Stage("applied")
        elif a.pdf_path:
            out[a.id] = Stage("pdf_ready")
        elif a.customized_json:
            out[a.id] = Stage("tailored")
        else:
            out[a.id] = _gaps_or(a.job_id, open_by_job, scored)
    return out
