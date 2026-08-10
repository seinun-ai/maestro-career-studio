"""Per-base-resume performance summaries for the Analytics "Resume fit" tab.

One row per active base resume: latest health report, average base-phase ATS
across scored jobs, average tailored lift (latest tailored row per
application, same join as explore_gaps.tailoring_lift), application counts,
and last activity.
"""
from collections import defaultdict
from typing import Any

from sqlalchemy import func, select

from app.services import base_resume_data
from sqlalchemy.orm import Session, aliased

from app.models.application import Application
from app.models.ats_score import AtsScore
from app.models.base_resume import BaseResume
from app.services.explore_activity import IN_FLIGHT_STATUSES
from app.services.resume_lint import latest_report


def base_summaries(db: Session) -> list[dict[str, Any]]:
    bases = db.scalars(
        select(BaseResume)
        .where(base_resume_data.selectable_filter())
        .order_by(BaseResume.display_name, BaseResume.slug)
    ).all()
    slugs = [base.slug for base in bases]
    if not slugs:
        return []

    ats_rows = db.execute(
        select(
            AtsScore.target_id,
            func.avg(AtsScore.composite).label("avg_composite"),
            func.count().label("n"),
        )
        .where(
            AtsScore.phase == "base",
            AtsScore.target_type == "base_resume",
            AtsScore.target_id.in_(slugs),
        )
        .group_by(AtsScore.target_id)
    ).all()
    avg_ats = {
        row.target_id: (round(float(row.avg_composite), 1), int(row.n))
        for row in ats_rows
    }

    # Latest tailored row per application joined to its base row (the
    # tailoring_lift pattern, grouped by base slug instead of role).
    ranked = (
        select(
            AtsScore.application_id.label("application_id"),
            AtsScore.composite.label("tailored_composite"),
            func.row_number()
            .over(
                partition_by=AtsScore.application_id,
                order_by=(AtsScore.created_at.desc(), AtsScore.id.desc()),
            )
            .label("rn"),
        )
        .where(AtsScore.phase == "tailored", AtsScore.application_id.is_not(None))
        .subquery()
    )
    base_score = aliased(AtsScore)
    lift_rows = db.execute(
        select(
            Application.base_resume,
            base_score.composite.label("base_composite"),
            ranked.c.tailored_composite,
        )
        .select_from(ranked)
        .join(Application, Application.id == ranked.c.application_id)
        .join(
            base_score,
            (base_score.job_id == Application.job_id)
            & (base_score.target_id == Application.base_resume)
            & (base_score.phase == "base")
            & (base_score.target_type == "base_resume"),
        )
        .where(ranked.c.rn == 1, Application.base_resume.in_(slugs))
    ).all()
    lifts: dict[str, list[float]] = defaultdict(list)
    for slug, base_composite, tailored_composite in lift_rows:
        lifts[slug].append(float(tailored_composite) - float(base_composite))

    # Single coalesce clause reused in GROUP BY (separate builds render as
    # distinct bind params and Postgres rejects the grouping).
    status_expr = func.coalesce(Application.status, "draft").label("status")
    app_rows = db.execute(
        select(
            Application.base_resume,
            status_expr,
            func.count().label("n"),
            func.count(Application.applied_at).label("n_submitted"),
            func.max(func.coalesce(Application.updated_at, Application.created_at)).label(
                "last_touch"
            ),
        )
        .where(Application.base_resume.in_(slugs))
        .group_by(Application.base_resume, status_expr)
    ).all()
    app_totals: dict[str, int] = defaultdict(int)
    app_submitted: dict[str, int] = defaultdict(int)
    app_in_flight: dict[str, int] = defaultdict(int)
    app_last_touch: dict[str, Any] = {}
    for row in app_rows:
        app_totals[row.base_resume] += int(row.n)
        app_submitted[row.base_resume] += int(row.n_submitted)
        if row.status in IN_FLIGHT_STATUSES:
            app_in_flight[row.base_resume] += int(row.n)
        prior = app_last_touch.get(row.base_resume)
        if prior is None or (row.last_touch and row.last_touch > prior):
            app_last_touch[row.base_resume] = row.last_touch

    summaries = []
    for base in bases:
        report = latest_report(db, "base", base.slug)
        report_json = report.report_json if report else None
        ats = avg_ats.get(base.slug)
        slug_lifts = lifts.get(base.slug) or []
        last_activity = app_last_touch.get(base.slug)
        for candidate in (base.updated_at, base.created_at):
            if candidate and (last_activity is None or candidate > last_activity):
                last_activity = candidate
        summaries.append(
            {
                "slug": base.slug,
                "display_name": base.display_name,
                "health_score": (report_json or {}).get("score"),
                "health_grade": (report_json or {}).get("grade"),
                "avg_base_ats": ats[0] if ats else None,
                "n_scored": ats[1] if ats else 0,
                "avg_lift": round(sum(slug_lifts) / len(slug_lifts), 1)
                if slug_lifts
                else None,
                "n_tailored": len(slug_lifts),
                "applications_total": app_totals.get(base.slug, 0),
                "applications_submitted": app_submitted.get(base.slug, 0),
                "in_flight": app_in_flight.get(base.slug, 0),
                "last_activity": last_activity.isoformat() if last_activity else None,
            }
        )
    return summaries
