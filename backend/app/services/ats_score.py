from typing import Any
from uuid import UUID

from sqlalchemy import not_, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.application import Application
from app.models.ats_score import AtsScore
from app.models.base_resume import BaseResume
from app.models.job import Job
from app.services import gap_analysis
from app.services.ats import score_resume
from app.services.ats.jd_normalizer import normalize_jd
from app.services import base_resume_data
from app.services.base_resume_data import (
    base_resume_path,
    load_base_resume,
    selectable_base_resume_slugs,
)


def get_scorable_job(session: Session, job_id: UUID) -> Job:
    """The job, validated for scoring (exists + has extracted_json); ValueError otherwise."""
    job = session.get(Job, job_id)
    if job is None:
        raise ValueError(f"Job not found: {job_id}")
    if not job.extracted_json:
        raise ValueError(f"Job has no extracted_json: {job_id}")
    return job


def _resolve_resume_data(session: Session, target_type: str, target_id: str) -> tuple[dict, UUID | None]:
    if target_type == "base_resume":
        return load_base_resume(target_id, session), None
    if target_type == "application":
        try:
            application_uuid = UUID(target_id)
        except ValueError as exc:
            raise ValueError(f"Invalid application id: {target_id}") from exc
        application = session.get(Application, application_uuid)
        if application is None:
            raise ValueError(f"Application not found: {target_id}")
        if not application.customized_json:
            raise ValueError("Application has no customized_json to score (materialize it first)")
        return application.customized_json, application.id
    raise ValueError(f"Unknown target_type: {target_type}")


def score_target(
    job_id: UUID,
    target_type: str,
    target_id: str,
    *,
    phase: str,
    session: Session | None = None,
    result: Any | None = None,
) -> AtsScore:
    """Score one target and persist. phase='base' upserts; phase='tailored' appends.

    ``result`` lets a caller that already ran the engine (and needs the AtsResult
    itself, e.g. session creation building gaps from it) persist that run instead
    of paying for an identical second one. The target is still resolved so the
    application_id stamp and validation behave the same.

    Transaction ownership: commits only when it OWNS the session (session=None).
    On a caller's session the row is flushed and refreshed on the caller's
    transaction and the CALLER commits — create_session and tailor() stage
    their whole write-set (score row included) and commit once at their end.
    """
    owns_session = session is None
    session = session or SessionLocal()
    try:
        job = get_scorable_job(session, job_id)
        resume_data, resolved_app_id = _resolve_resume_data(session, target_type, target_id)
        if result is None:
            result = score_resume(resume_data, job.extracted_json)

        values: dict[str, Any] = {
            "composite": result.composite,
            "subscores_json": {
                **result.subscores,
                "title_tier": result.title_tier,
                "gate_warnings": result.gate_warnings,
                "format_flags": result.format_flags,
                "jd_skills_extracted_count": result.jd_skills_extracted_count,
                "jd_skills_matched_count": result.jd_skills_matched_count,
                "coverage_ratio": result.coverage_ratio,
                "coverage_warning": result.coverage_warning,
            },
            "skill_table_json": result.skill_table,
            "gaps_json": gap_analysis.build_gaps(result),
            "config_version": result.config_version,
            "engine_version": result.engine_version,
            # Set only for target_type == "application": base rows are shared per
            # (job, slug) and must not be stamped with a triggering application.
            "application_id": resolved_app_id,
        }

        row: AtsScore | None = None
        if phase == "base":
            row = session.scalar(
                select(AtsScore).where(
                    AtsScore.job_id == job_id,
                    AtsScore.target_type == target_type,
                    AtsScore.target_id == target_id,
                    AtsScore.phase == "base",
                )
            )
        if row is None:
            row = AtsScore(
                job_id=job_id, target_type=target_type, target_id=target_id, phase=phase, **values
            )
            session.add(row)
        else:
            for key, value in values.items():
                setattr(row, key, value)
        session.flush()
        if owns_session:
            session.commit()
        session.refresh(row)
        return row
    finally:
        if owns_session:
            session.close()


def score_all_bases(job_id: UUID, session: Session | None = None) -> list[AtsScore]:
    owns_session = session is None
    session = session or SessionLocal()
    try:
        # Validate the job ONCE up front: a job-level problem (missing job, no
        # extracted_json, or an empty extracted skills list -> normalize_jd
        # raises) would otherwise fail identically for every slug and be
        # swallowed into a silently-empty result. Job errors must propagate.
        job = get_scorable_job(session, job_id)
        normalize_jd(job.extracted_json)

        rows: list[AtsScore] = []
        for slug in selectable_base_resume_slugs(session):
            # Per-slug, only a MISSING data file is skippable (fileless-but-active
            # slug, skipping active slugs with no on-disk file). Everything else —
            # including a corrupt-but-present file — propagates from score_target,
            # matching direct-call behavior; the job was already validated above.
            if not base_resume_path(slug).exists():
                continue
            rows.append(score_target(job_id, "base_resume", slug, phase="base", session=session))
        if owns_session:
            session.commit()
        return rows
    finally:
        if owns_session:
            session.close()


def best_base(job_id: UUID, session: Session | None = None) -> str:
    """Slug of the base resume with the highest base-phase ATS composite.

    Reads persisted base rows (one per slug — base phase upserts); if none
    exist yet, scores every active base first (pure engine, no LLM).
    """
    owns_session = session is None
    session = session or SessionLocal()
    try:
        rows = list(session.scalars(
            select(AtsScore).where(
                AtsScore.job_id == job_id,
                AtsScore.target_type == "base_resume",
                AtsScore.phase == "base",
            )
        ))
        if not rows:
            # Same read-that-writes contract as compare: an on-demand scoring
            # pass is committed here so it persists on a caller's session too.
            rows = score_all_bases(job_id, session)
            if rows:
                session.commit()
        if not rows:
            raise ValueError("No base resumes could be scored for this job")
        # alphabetical slug tie-break keeps the pick deterministic
        return max(rows, key=lambda r: (float(r.composite), r.target_id)).target_id
    finally:
        if owns_session:
            session.close()


def latest_scores(job_id: UUID, session: Session) -> list[AtsScore]:
    """Latest row per (target_type, target_id), base phase first, composite desc.

    Base rows for archived or soft-deleted resumes are dropped: this feeds the
    ATS panel, which is a PICK surface — every row it returns becomes a card
    offering "Analyze gaps & tailor". Score rows outlive the base they scored,
    so without this an archived base stays tailorable forever. Application rows
    are untouched; only base_resume targets can be archived.
    """
    hidden = set(
        session.scalars(
            select(BaseResume.slug).where(
                # NOT selectable — the inverse of the canonical predicate
                not_(base_resume_data.selectable_filter())
            )
        )
    )
    rows = list(session.scalars(
        select(AtsScore)
        .where(AtsScore.job_id == job_id)
        # id desc is a deterministic tiebreak for same-transaction timestamps
        # (uuid4 is random, so it guarantees determinism, not recency).
        .order_by(AtsScore.created_at.desc(), AtsScore.id.desc())
    ))
    seen: set[tuple[str, str]] = set()
    latest: list[AtsScore] = []
    for row in rows:
        if row.target_type == "base_resume" and row.target_id in hidden:
            continue
        key = (row.target_type, row.target_id)
        if key not in seen:
            seen.add(key)
            latest.append(row)
    return sorted(latest, key=lambda r: (r.phase != "base", -float(r.composite)))


def _latest_row(session: Session, application: Application, phase: str) -> AtsScore | None:
    return session.scalar(
        select(AtsScore)
        .where(AtsScore.application_id == application.id, AtsScore.phase == phase)
        # id desc is a deterministic tiebreak for same-transaction timestamps
        # (uuid4 is random, so it guarantees determinism, not recency).
        .order_by(AtsScore.created_at.desc(), AtsScore.id.desc())
        .limit(1)
    )


def compare(application_id: UUID, session: Session | None = None) -> dict[str, Any]:
    """Before/after for an application; computes missing rows on demand.

    A read that may WRITE: missing rows are backfilled, and the backfill is
    committed here (even on a caller's session) so an on-demand row survives a
    GET whose dependency never commits. Callers therefore must not invoke
    compare with uncommitted staged state of their own — every current caller
    runs it after their own commit."""
    owns_session = session is None
    session = session or SessionLocal()
    try:
        application = session.get(Application, application_id)
        if application is None:
            raise ValueError(f"Application not found: {application_id}")

        backfilled = False
        base_row = session.scalars(
            select(AtsScore)
            .where(
                AtsScore.job_id == application.job_id,
                AtsScore.target_type == "base_resume",
                AtsScore.target_id == application.base_resume,
                AtsScore.phase == "base",
            )
            # The partial unique index guarantees a single base row; ordering is
            # cheap insurance that the pick stays deterministic regardless.
            .order_by(AtsScore.created_at.desc(), AtsScore.id.desc())
            .limit(1)
        ).first()
        if base_row is None:
            base_row = score_target(
                application.job_id, "base_resume", application.base_resume,
                phase="base", session=session,
            )
            backfilled = True
        tailored_row = _latest_row(session, application, "tailored")
        if tailored_row is None:
            tailored_row = score_target(
                application.job_id, "application", str(application.id),
                phase="tailored", session=session,
            )
            backfilled = True
        # Before the version guard below: a backfilled row must persist even
        # when the comparison itself then fails (matching prior behavior).
        if backfilled:
            session.commit()

        if (base_row.engine_version, base_row.config_version) != (
            tailored_row.engine_version, tailored_row.config_version
        ):
            raise ValueError(
                "Scores were produced by different engine/config versions; re-run scoring "
                "for both phases before comparing"
            )

        before = {r["jd_skill"]: r for r in base_row.skill_table_json}
        after = {r["jd_skill"]: r for r in tailored_row.skill_table_json}
        skill_diff = [
            {"jd_skill": name, "before": before.get(name), "after": after.get(name)}
            for name in sorted(set(before) | set(after))
            if before.get(name) != after.get(name)
        ]
        return {
            "application_id": str(application_id),
            "base": base_row,
            "tailored": tailored_row,
            "delta": {
                "composite": round(float(tailored_row.composite) - float(base_row.composite), 1),
                "subscores": {
                    k: round(tailored_row.subscores_json[k] - base_row.subscores_json[k], 4)
                    for k in ("keyword", "placement_recency", "semantic_fit", "title", "format")
                },
            },
            "skill_diff": skill_diff,
        }
    finally:
        if owns_session:
            session.close()
