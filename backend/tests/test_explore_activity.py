"""Tests for /api/explore/activity (dashboard series + pipeline totals)."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.application import Application
from app.models.job import Job


def _override_db(db_session):
    def _inner():
        yield db_session

    return _inner


def _get(db_session, path: str):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        return TestClient(app).get(path)
    finally:
        app.dependency_overrides.clear()


def _seed_job(db_session, raw_hash: str) -> Job:
    job = Job(
        raw_text=f"JD {raw_hash}",
        raw_text_hash=raw_hash,
        extracted_json={"title": raw_hash},
        title=raw_hash,
        company="Acme",
        role_category="data_scientist",
        extracted_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.flush()
    return job


def _seed_application(
    db_session,
    job: Job,
    *,
    status: str = "draft",
    applied_at: datetime | None = None,
    created_at: datetime | None = None,
) -> Application:
    application = Application(
        job_id=job.id,
        base_resume="data_scientist",
        status=status,
        applied_at=applied_at,
        created_at=created_at or datetime.now(UTC),
    )
    db_session.add(application)
    db_session.flush()
    return application


def test_activity_empty_db_zero_filled(db_session):
    resp = _get(db_session, "/api/explore/activity?granularity=day&weeks=2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["granularity"] == "day"
    assert len(body["series"]) == 14
    assert all(row["drafted"] == 0 and row["submitted"] == 0 for row in body["series"])
    assert body["totals"] == {
        "applications": 0,
        "drafted_last7": 0,
        "submitted": 0,
        "submitted_last7": 0,
        "in_flight": 0,
        "interview_rate": None,
    }
    assert body["status_counts"] == {}


def test_activity_counts_and_pipeline(db_session):
    now = datetime.now(UTC)
    job1 = _seed_job(db_session, "j1")
    job2 = _seed_job(db_session, "j2")
    job3 = _seed_job(db_session, "j3")
    job4 = _seed_job(db_session, "j4")
    # Two submitted today (one interviewing, one applied), one rejected but
    # submitted 3 days ago, one pure draft.
    _seed_application(db_session, job1, status="interviewing", applied_at=now)
    _seed_application(db_session, job2, status="applied", applied_at=now)
    _seed_application(
        db_session,
        job3,
        status="rejected",
        applied_at=now - timedelta(days=3),
        created_at=now - timedelta(days=3),
    )
    _seed_application(db_session, job4, status="draft")
    db_session.commit()

    resp = _get(db_session, "/api/explore/activity?granularity=day&weeks=1")
    assert resp.status_code == 200
    body = resp.json()
    today = now.date().isoformat()
    today_row = next(r for r in body["series"] if r["bucket_start"] == today)
    assert today_row["submitted"] == 2
    assert today_row["drafted"] == 3  # job1, job2, job4 created now

    totals = body["totals"]
    assert totals["applications"] == 4
    assert totals["submitted"] == 3  # rejected still counts as submitted
    assert totals["submitted_last7"] == 3
    assert totals["in_flight"] == 2  # applied + interviewing
    assert totals["interview_rate"] == round(1 / 3, 3)  # interviewing / 3 submitted
    assert body["status_counts"] == {
        "interviewing": 1,
        "applied": 1,
        "rejected": 1,
        "draft": 1,
    }


def test_activity_week_granularity_and_coercion(db_session):
    job = _seed_job(db_session, "j1")
    _seed_application(db_session, job, status="applied", applied_at=datetime.now(UTC))
    db_session.commit()

    resp = _get(db_session, "/api/explore/activity?granularity=week&weeks=4")
    body = resp.json()
    assert body["granularity"] == "week"
    assert len(body["series"]) == 4
    assert sum(r["submitted"] for r in body["series"]) == 1
    # Week buckets are Mondays (matches Postgres date_trunc('week')).
    for row in body["series"]:
        assert datetime.fromisoformat(row["bucket_start"]).weekday() == 0

    coerced = _get(db_session, "/api/explore/activity?granularity=hour").json()
    assert coerced["granularity"] == "day"


def test_activity_weeks_bounds_422(db_session):
    assert _get(db_session, "/api/explore/activity?weeks=0").status_code == 422
    assert _get(db_session, "/api/explore/activity?weeks=53").status_code == 422


def test_activity_filters_by_source(db_session):
    job_user = _seed_job(db_session, "src-user")
    job_agent = _seed_job(db_session, "src-agent")
    user_app = _seed_application(db_session, job_user, status="draft")
    user_app.source = "user"
    agent_app = _seed_application(db_session, job_agent, status="draft")
    agent_app.source = "agent"
    db_session.commit()

    both = _get(db_session, "/api/explore/activity?granularity=day&weeks=1")
    assert both.status_code == 200
    assert both.json()["totals"]["applications"] == 2

    agent_only = _get(
        db_session, "/api/explore/activity?granularity=day&weeks=1&source=agent"
    )
    assert agent_only.status_code == 200
    assert agent_only.json()["totals"]["applications"] == 1

    user_only = _get(
        db_session, "/api/explore/activity?granularity=day&weeks=1&source=user"
    )
    assert user_only.status_code == 200
    assert user_only.json()["totals"]["applications"] == 1

    invalid = _get(
        db_session, "/api/explore/activity?granularity=day&weeks=1&source=invalid"
    )
    assert invalid.status_code == 422
