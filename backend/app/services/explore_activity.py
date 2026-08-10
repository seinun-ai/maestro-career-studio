"""Application activity: drafted/submitted per day or week + pipeline totals.

Drafted = Application.created_at (a draft came into existence). Submitted =
Application.applied_at (stamped by the status rules; rejected/withdrawn keep
it, so "submitted" is a fact about the past, not the current status).
"""
from datetime import UTC, datetime, time, timedelta
from typing import Any

from sqlalchemy import Date, func, select
from sqlalchemy.orm import Session

from app.models.application import Application

# Current statuses meaning "submitted and still moving".
IN_FLIGHT_STATUSES = ("applied", "interviewing", "offered")
# Current statuses at interview stage or beyond. NOTE: this is point-in-time —
# an application that interviewed and was later rejected leaves this set, so
# interview_rate means "currently at interview+ per submitted", not "ever
# reached an interview" (no status history exists; a first_interview_at stamp
# would be needed for funnel semantics — recorded as deferred in the design).
INTERVIEW_PLUS_STATUSES = ("interviewing", "offered", "accepted")


def _bucket_starts(granularity: str, weeks: int) -> list:
    """Bucket start dates from the window start through today, oldest first.

    Week buckets start on Monday to match Postgres date_trunc('week').
    """
    today = datetime.now(UTC).date()
    if granularity == "week":
        this_monday = today - timedelta(days=today.weekday())
        return [this_monday - timedelta(weeks=i) for i in reversed(range(weeks))]
    start = today - timedelta(days=weeks * 7 - 1)
    return [start + timedelta(days=i) for i in range(weeks * 7)]


def activity(
    db: Session,
    *,
    granularity: str = "day",
    weeks: int = 8,
    source: str | None = None,
) -> dict[str, Any]:
    """Zero-filled drafted/submitted series + pipeline totals and status counts."""
    if granularity not in ("day", "week"):
        granularity = "day"
    buckets = _bucket_starts(granularity, weeks)
    window_start = datetime.combine(buckets[0], time.min, tzinfo=UTC)

    def _series(column) -> dict[str, int]:
        bucket = func.date_trunc(granularity, column).cast(Date).label("bucket")
        stmt = (
            select(bucket, func.count().label("n"))
            .where(column.is_not(None), column >= window_start)
            .group_by(bucket)
        )
        if source:
            stmt = stmt.where(Application.source == source)
        return {row.bucket.isoformat(): int(row.n) for row in db.execute(stmt).all()}

    drafted = _series(Application.created_at)
    submitted = _series(Application.applied_at)
    series = [
        {
            "bucket_start": day.isoformat(),
            "drafted": drafted.get(day.isoformat(), 0),
            "submitted": submitted.get(day.isoformat(), 0),
        }
        for day in buckets
    ]

    # Build the coalesce ONCE and group by the same clause — two separate
    # func.coalesce(...) calls render as different bind params and Postgres
    # then rejects the GROUP BY.
    status_expr = func.coalesce(Application.status, "draft").label("status")
    status_stmt = select(
        status_expr,
        func.count().label("n"),
        func.count(Application.applied_at).label("n_submitted"),
    ).group_by(status_expr)
    if source:
        status_stmt = status_stmt.where(Application.source == source)
    status_rows = db.execute(status_stmt).all()
    status_counts = {row.status: int(row.n) for row in status_rows}
    total = sum(status_counts.values())
    total_submitted = sum(int(row.n_submitted) for row in status_rows)
    interview_plus = sum(
        status_counts.get(status, 0) for status in INTERVIEW_PLUS_STATUSES
    )
    in_flight = sum(status_counts.get(status, 0) for status in IN_FLIGHT_STATUSES)

    last7 = datetime.now(UTC) - timedelta(days=7)
    drafted_last7_stmt = select(func.count()).where(Application.created_at >= last7)
    submitted_last7_stmt = select(func.count()).where(
        Application.applied_at.is_not(None), Application.applied_at >= last7
    )
    if source:
        drafted_last7_stmt = drafted_last7_stmt.where(Application.source == source)
        submitted_last7_stmt = submitted_last7_stmt.where(Application.source == source)
    drafted_last7 = int(db.scalar(drafted_last7_stmt) or 0)
    submitted_last7 = int(db.scalar(submitted_last7_stmt) or 0)

    return {
        "granularity": granularity,
        "series": series,
        "totals": {
            "applications": total,
            "drafted_last7": drafted_last7,
            "submitted": total_submitted,
            "submitted_last7": submitted_last7,
            "in_flight": in_flight,
            "interview_rate": round(interview_plus / total_submitted, 3)
            if total_submitted
            else None,
        },
        "status_counts": status_counts,
    }
