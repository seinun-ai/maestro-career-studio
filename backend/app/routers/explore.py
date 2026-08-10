from collections import defaultdict
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Date, case, distinct, func, not_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.ats_score import AtsScore
from app.models.base_resume import BaseResume
from app.models.job import Job
from app.models.job_skill import JobSkill
from app.schemas.explore import ExploreOverviewResponse, TopSkillsResponse
from app.services import (
    base_resume_data,
    explore_activity,
    explore_base_summaries,
    explore_build_areas,
    explore_gaps,
    explore_overview,
)
from app.services.explore_skills import TOP_TIER_FRACTION, classify_skill_rows


router = APIRouter(prefix="/api/explore", tags=["explore"])


def job_filters(
    role_category: str | None = Query(None),
    level: str | None = Query(None),
    employment_type: str | None = Query(None),
    country: str | None = Query(None),
    salary_currency: str | None = Query(None),
) -> explore_overview.JobFilters:
    return explore_overview.JobFilters(
        role_category=role_category,
        level=level,
        employment_type=employment_type,
        country=country,
        salary_currency=salary_currency,
    )


def _apply_job_filters(stmt: Any, filters: explore_overview.JobFilters):
    return explore_overview._apply(stmt, filters)


def _count_filtered_jobs(db: Session, filters: explore_overview.JobFilters) -> int:
    stmt = select(func.count()).select_from(Job)
    return int(db.scalar(_apply_job_filters(stmt, filters)) or 0)


def _skill_count_stmt(filters: explore_overview.JobFilters):
    stmt = (
        select(
            JobSkill.skill_name,
            func.count(distinct(JobSkill.job_id)).label("n"),
            func.count(
                distinct(
                    case(
                        (JobSkill.requirement_level == "required", JobSkill.job_id),
                        else_=None,
                    )
                )
            ).label("n_required"),
            func.count(
                distinct(
                    case(
                        (JobSkill.requirement_level == "preferred", JobSkill.job_id),
                        else_=None,
                    )
                )
            ).label("n_preferred"),
            func.count(
                distinct(
                    case(
                        (JobSkill.requirement_level == "mentioned", JobSkill.job_id),
                        else_=None,
                    )
                )
            ).label("n_mentioned"),
        )
        .join(Job, Job.id == JobSkill.job_id)
        .group_by(JobSkill.skill_name)
        .order_by(func.count(distinct(JobSkill.job_id)).desc(), JobSkill.skill_name)
    )
    return _apply_job_filters(stmt, filters)


def _skill_category_tags(db: Session, filters: explore_overview.JobFilters) -> dict[str, str]:
    """Map canonical skill_name -> category tag (most-frequent, then alphabetical)."""
    stmt = (
        select(
            JobSkill.skill_name,
            JobSkill.skill_category,
            func.count(distinct(JobSkill.job_id)).label("n"),
        )
        .join(Job, Job.id == JobSkill.job_id)
        .group_by(JobSkill.skill_name, JobSkill.skill_category)
    )
    stmt = _apply_job_filters(stmt, filters)
    best: dict[str, tuple[int, str]] = {}
    for name, category, n in db.execute(stmt).all():
        rank = (-int(n), category)  # most-frequent first, then alphabetical
        if name not in best or rank < (-best[name][0], best[name][1]):
            best[name] = (int(n), category)
    return {name: category for name, (_, category) in best.items()}


@router.get("/overview", response_model=ExploreOverviewResponse)
def overview(
    db: Annotated[Session, Depends(get_db)],
    filters: Annotated[explore_overview.JobFilters, Depends(job_filters)],
):
    data = explore_overview.build_overview(db, filters)
    return ExploreOverviewResponse.model_validate(data)


@router.get("/top-skills", response_model=TopSkillsResponse)
def top_skills(
    db: Annotated[Session, Depends(get_db)],
    filters: Annotated[explore_overview.JobFilters, Depends(job_filters)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    bucket: str | None = None,
):
    total_jobs = _count_filtered_jobs(db, filters)
    tags = _skill_category_tags(db, filters)
    raw_rows = [
        {
            "skill_name": row.skill_name,
            "skill_category": tags.get(row.skill_name),
            "n": row.n,
            "n_required": row.n_required,
            "n_preferred": row.n_preferred,
            "n_mentioned": row.n_mentioned,
        }
        for row in db.execute(_skill_count_stmt(filters))
    ]

    classified = classify_skill_rows(raw_rows, total_jobs=total_jobs)

    if bucket in {"core", "preferred_top", "below_threshold"}:
        classified = [row for row in classified if row["bucket"] == bucket]

    return TopSkillsResponse.from_classified(
        classified,
        total_jobs=total_jobs,
        top_tier_fraction=TOP_TIER_FRACTION,
        limit=limit,
    )


@router.get("/heatmap")
def heatmap(
    db: Annotated[Session, Depends(get_db)],
    filters: Annotated[explore_overview.JobFilters, Depends(job_filters)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    top_tier_only: bool = False,
):
    total_jobs = _count_filtered_jobs(db, filters)
    tags = _skill_category_tags(db, filters)
    raw_rows = [
        {
            "skill_name": row.skill_name,
            "skill_category": tags.get(row.skill_name),
            "n": row.n,
            "n_required": row.n_required,
            "n_preferred": row.n_preferred,
            "n_mentioned": row.n_mentioned,
        }
        for row in db.execute(_skill_count_stmt(filters))
    ]
    classified = classify_skill_rows(raw_rows, total_jobs=total_jobs)

    if top_tier_only:
        skill_rows = [row for row in classified if row["tier"] == "top"]
    else:
        skill_rows = classified

    top_skill_names = [row["skill_name"] for row in skill_rows[:limit]]
    if not top_skill_names:
        return []

    role_stmt = select(Job.role_category, func.count(distinct(Job.id))).where(
        Job.role_category.is_not(None)
    )
    role_stmt = _apply_job_filters(role_stmt, filters)
    role_stmt = role_stmt.group_by(Job.role_category)
    role_totals = dict(db.execute(role_stmt).all())

    rows = db.execute(
        select(
            JobSkill.skill_name,
            Job.role_category,
            func.count(distinct(JobSkill.job_id)).label("n"),
        )
        .join(Job, Job.id == JobSkill.job_id)
        .where(JobSkill.skill_name.in_(top_skill_names), Job.role_category.is_not(None))
        .group_by(JobSkill.skill_name, Job.role_category)
        .order_by(JobSkill.skill_name, Job.role_category)
    ).all()

    filtered_rows = rows
    if filters.role_category:
        filtered_rows = [row for row in rows if row.role_category == filters.role_category]

    return [
        {
            "skill_name": row.skill_name,
            "role_category": row.role_category,
            "pct_jobs": round((row.n / role_totals[row.role_category]) * 100, 2)
            if role_totals.get(row.role_category)
            else 0.0,
        }
        for row in filtered_rows
    ]


@router.get("/fit-distribution")
def fit_distribution(db: Annotated[Session, Depends(get_db)]):
    """Distribution of ATS composites (deterministic engine) per base resume.

    Reads base-phase ats_scores rows (one per job/slug — base phase upserts).
    """
    bucket_expr = case(
        (AtsScore.composite < 20, "0-20"),
        (AtsScore.composite < 40, "20-40"),
        (AtsScore.composite < 60, "40-60"),
        (AtsScore.composite < 80, "60-80"),
        else_="80-100",
    )
    deleted_slugs = select(BaseResume.slug).where(not_(base_resume_data.active_filter()))
    rows = db.execute(
        select(AtsScore.target_id.label("base_resume"), bucket_expr.label("bucket"), func.count().label("n"))
        .where(AtsScore.phase == "base", AtsScore.target_type == "base_resume")
        .where(AtsScore.target_id.not_in(deleted_slugs))
        .group_by(AtsScore.target_id, bucket_expr)
        .order_by(AtsScore.target_id)
    ).all()

    buckets_by_resume: dict[str, dict[str, int]] = defaultdict(
        lambda: {"0-20": 0, "20-40": 0, "40-60": 0, "60-80": 0, "80-100": 0}
    )
    for row in rows:
        buckets_by_resume[row.base_resume][row.bucket] = row.n

    return [
        {"base_resume": base_resume, "buckets": buckets}
        for base_resume, buckets in sorted(buckets_by_resume.items())
    ]


@router.get("/role-mix-over-time")
def role_mix_over_time(
    db: Annotated[Session, Depends(get_db)],
    window: str = "week",
):
    if window != "week":
        window = "week"

    week_start = func.date_trunc("week", Job.created_at).cast(Date).label("week_start")
    rows = db.execute(
        select(week_start, Job.role_category, func.count().label("count"))
        .where(Job.role_category.is_not(None))
        .group_by(week_start, Job.role_category)
        .order_by(week_start, Job.role_category)
    ).all()

    return [
        {
            "week_start": row.week_start.isoformat(),
            "role_category": row.role_category,
            "count": row.count,
        }
        for row in rows
    ]


@router.get("/gap-frequency")
def gap_frequency(
    db: Annotated[Session, Depends(get_db)],
    role_category: str | None = None,
    level: str | None = None,
    employment_type: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
):
    return explore_gaps.gap_frequency(
        db, role_category, level, employment_type, limit=limit
    )


@router.get("/ats-over-time")
def ats_over_time(
    db: Annotated[Session, Depends(get_db)],
    role_category: str | None = None,
    level: str | None = None,
    employment_type: str | None = None,
):
    return explore_gaps.ats_over_time(db, role_category, level, employment_type)


@router.get("/tailoring-lift")
def tailoring_lift(
    db: Annotated[Session, Depends(get_db)],
    role_category: str | None = None,
    level: str | None = None,
    employment_type: str | None = None,
):
    return explore_gaps.tailoring_lift(db, role_category, level, employment_type)


@router.get("/activity")
def activity(
    db: Annotated[Session, Depends(get_db)],
    granularity: str = "day",
    weeks: Annotated[int, Query(ge=1, le=52)] = 8,
    source: Literal["user", "agent"] | None = Query(default=None),
):
    """Drafted/submitted application series + pipeline totals for the dashboard."""
    return explore_activity.activity(
        db, granularity=granularity, weeks=weeks, source=source
    )


@router.get("/base-summaries")
def base_summaries(db: Annotated[Session, Depends(get_db)]):
    """One performance summary row per active base resume."""
    return explore_base_summaries.base_summaries(db)


@router.get("/build-areas")
def build_areas(
    db: Annotated[Session, Depends(get_db)],
    role_category: str | None = None,
    level: str | None = None,
    employment_type: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
):
    """Frequent skill gaps tiered by what would fix them (build/surface/wording)."""
    return explore_build_areas.build_areas(
        db, role_category, level, employment_type, limit=limit
    )
