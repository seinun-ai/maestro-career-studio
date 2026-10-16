"""One ladder behind every job: the rung the Jobs list and the job page show as Next step.
Read-only; computed per request from rows that already exist (SYSTEM.md §5 step 2)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, load_only

from app.models.application import Application
from app.models.job import Job
from app.models.tailoring_session import TailoringSession
from app.schemas.stage import RUNGS, Rung  # noqa: F401  (RUNGS re-exported for callers)
from app.services import ats_score
from app.services.application_status import SUBMITTED_STAGES

# An application in one of these is over without being applied to: nothing to do next.
_CLOSED_STATUSES = ("rejected", "withdrawn")


@dataclass(frozen=True)
class Stage:
    """`open_session_id`, `gaps_done` and `gaps_total` are set only on the `gaps` rung."""

    rung: Rung
    open_session_id: UUID | None = None
    gaps_done: int = 0
    gaps_total: int = 0


def _gap_counts(session: TailoringSession) -> tuple[int, int]:
    """Answered plus skipped over every listed gap: the gap page's own count
    (frontend/lib/gap-counts.ts). A resolution for a gap the analysis no longer
    lists counts for nothing."""
    ids = {
        g.get("gap_id")
        for c in (session.gaps_json or {}).get("categories", [])
        for g in c.get("gaps", [])
    } - {None}
    resolved = {r.get("gap_id") for r in (session.resolutions_json or [])}
    return len(ids & resolved), len(ids)


def _open_sessions(db: Session, job_ids: list[UUID]) -> dict[UUID, TailoringSession]:
    newest: dict[UUID, TailoringSession] = {}
    for s in db.scalars(
        select(TailoringSession)
        .where(TailoringSession.job_id.in_(job_ids), TailoringSession.status == "open")
        # An open session on an archived base still counts as gaps: the user can finish it.
        # id: stable tie-break only.
        .order_by(TailoringSession.created_at.desc(), TailoringSession.id.desc())
    ):
        newest.setdefault(s.job_id, s)
    return newest


def _before_draft(
    job_id: UUID, open_by_job: dict[UUID, TailoringSession], scored: set[UUID]
) -> Stage:
    s = open_by_job.get(job_id)
    if s is not None:
        done, total = _gap_counts(s)
        return Stage("gaps", s.id, done, total)
    return Stage("scored" if job_id in scored else "saved")


def for_jobs(db: Session, jobs: list[Job]) -> dict[UUID, Stage]:
    """Jobs with no application: the saved-jobs list; never returns tailored/pdf_ready/applied/closed.
    Two queries for the page (open sessions, best base scores); none for an empty list."""
    ids = [j.id for j in jobs]
    if not ids:
        return {}
    open_by_job = _open_sessions(db, ids)
    scored = set(ats_score.best_base_scores(db, ids))
    return {j.id: _before_draft(j.id, open_by_job, scored) for j in jobs}


def _rate(app: Application, open_by_job: dict[UUID, TailoringSession], scored: set[UUID]) -> Stage:
    """One application's rung; falls back to the job's session or score when there is no draft."""
    newer = open_by_job.get(app.job_id)
    if newer is not None and newer.created_at <= app.updated_at:
        newer = None  # the session is older than the draft: the draft is the later work
    if (app.status or "") in _CLOSED_STATUSES:
        return Stage("closed")
    if app.applied_at is not None or (app.status or "") in SUBMITTED_STAGES:
        return Stage("applied")
    if newer is not None and (app.pdf_path or app.customized_json):
        # Re-analyzing gaps made a session after this draft: the list offers Continue gaps.
        done, total = _gap_counts(newer)
        return Stage("gaps", newer.id, done, total)
    if app.pdf_path:
        return Stage("pdf_ready")
    if app.customized_json:
        return Stage("tailored")
    return _before_draft(app.job_id, open_by_job, scored)


def for_applications(db: Session, apps: list[Application]) -> dict[UUID, Stage]:
    """Application rows, keyed by application id. Two queries for the page (open sessions, best
    base scores); none for an empty list."""
    if not apps:
        return {}
    job_ids = list({a.job_id for a in apps})
    open_by_job = _open_sessions(db, job_ids)
    scored = set(ats_score.best_base_scores(db, job_ids))
    return {a.id: _rate(a, open_by_job, scored) for a in apps}


# What _rate reads, plus the ordering column. Everything else on the row stays unloaded.
_RATING_COLUMNS = (
    Application.id,
    Application.job_id,
    Application.status,
    Application.applied_at,
    Application.created_at,
    Application.updated_at,
    Application.pdf_path,
    Application.customized_json,  # read for truthiness only, same rule as for_applications
)


def newest_applications(db: Session, job_ids: list[UUID]) -> dict[UUID, Application]:
    """Each job's newest application (`created_at desc, id desc`), keyed by job id; jobs with none
    are absent. One query: a ranked column subquery picks the winners, so only one row per job is
    loaded, and only the columns `_rate` reads (the other columns load lazily if touched)."""
    if not job_ids:
        return {}
    ranked = (
        select(
            Application.id,
            func.row_number()
            .over(
                partition_by=Application.job_id,
                # id: stable tie-break only, the same order the job detail reads
                order_by=(Application.created_at.desc(), Application.id.desc()),
            )
            .label("rn"),
        )
        .where(Application.job_id.in_(job_ids))
        .subquery()
    )
    rows = db.scalars(
        select(Application)
        .join(ranked, ranked.c.id == Application.id)
        .where(ranked.c.rn == 1)
        .options(load_only(*_RATING_COLUMNS))
    )
    return {a.job_id: a for a in rows}


def for_job_rows(
    db: Session, jobs: list[Job], *, scored: set[UUID] | None = None
) -> dict[UUID, Stage]:
    """One rung per job, keyed by job id: its newest application's (rated as `for_applications`
    would), else the job's own (as `for_jobs`). `scored` is the set of job ids with a best base
    score when the caller already has it (`ats_score.best_base_scores`). Three queries for the
    page (newest applications, open sessions, best base scores), two when `scored` is passed;
    none for an empty list."""
    ids = [j.id for j in jobs]
    if not ids:
        return {}
    newest = newest_applications(db, ids)
    open_by_job = _open_sessions(db, ids)
    if scored is None:
        scored = set(ats_score.best_base_scores(db, ids))
    return {
        jid: _rate(newest[jid], open_by_job, scored)
        if jid in newest
        else _before_draft(jid, open_by_job, scored)
        for jid in ids
    }
