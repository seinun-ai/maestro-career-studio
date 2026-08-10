"""Tests for /api/explore/base-summaries (per-base performance rows)."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.application import Application
from app.models.ats_score import AtsScore
from app.models.base_resume import BaseResume
from app.models.job import Job
from app.models.resume_lint_report import ResumeLintReport
from app.services.explore_base_summaries import base_summaries

SAMPLE_DATA = {
    "contact": {"name": "A", "email": "a@example.com"},
    "summary": "",
    "skills": [],
    "experience": [],
    "projects": [],
    "education": [],
    "certifications": [],
}


def _override_db(db_session):
    def _inner():
        yield db_session

    return _inner


def _get(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        return TestClient(app).get("/api/explore/base-summaries")
    finally:
        app.dependency_overrides.clear()


def _seed_base(db_session, slug: str, *, deleted_at=None) -> BaseResume:
    row = BaseResume(
        slug=slug,
        display_name=slug.replace("_", " ").title(),
        data_json=SAMPLE_DATA,
        deleted_at=deleted_at,
    )
    db_session.add(row)
    db_session.flush()
    return row


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


def test_base_summaries_full_row(db_session):
    _seed_base(db_session, "data_scientist")
    _seed_base(db_session, "old_one", deleted_at=datetime.now(UTC))  # soft-deleted
    job1 = _seed_job(db_session, "j1")
    job2 = _seed_job(db_session, "j2")

    # Base-phase scores: 60 and 70 -> avg 65.0 over 2 jobs.
    for job, composite in ((job1, 60.0), (job2, 70.0)):
        db_session.add(
            AtsScore(
                job_id=job.id,
                target_type="base_resume",
                target_id="data_scientist",
                phase="base",
                composite=composite,
                subscores_json={},
            skill_table_json=[],
            config_version="c1",
            engine_version="ats-1.0.0",
            )
        )
    # One application on job1, submitted and interviewing; tailored 72 (lift 12).
    application = Application(
        job_id=job1.id,
        base_resume="data_scientist",
        status="interviewing",
        applied_at=datetime.now(UTC),
    )
    db_session.add(application)
    db_session.flush()
    db_session.add(
        AtsScore(
            job_id=job1.id,
            target_type="application",
            target_id=str(application.id),
            application_id=application.id,
            phase="tailored",
            composite=72.0,
            subscores_json={},
            skill_table_json=[],
            config_version="c1",
            engine_version="ats-1.0.0",
        )
    )
    db_session.add(
        ResumeLintReport(
            resume_kind="base",
            resume_key="data_scientist",
            report_json={"score": 78, "grade": "B", "tier": "good"},
        )
    )
    db_session.commit()

    resp = _get(db_session)
    assert resp.status_code == 200
    rows = resp.json()
    assert [row["slug"] for row in rows] == ["data_scientist"]
    row = rows[0]
    assert row["display_name"] == "Data Scientist"
    assert row["health_score"] == 78
    assert row["health_grade"] == "B"
    assert row["avg_base_ats"] == 65.0
    assert row["n_scored"] == 2
    assert row["avg_lift"] == 12.0
    assert row["n_tailored"] == 1
    assert row["applications_total"] == 1
    assert row["applications_submitted"] == 1
    assert row["in_flight"] == 1
    assert row["last_activity"] is not None


def test_base_summaries_latest_tailored_row_wins(db_session):
    _seed_base(db_session, "data_scientist")
    job = _seed_job(db_session, "j1")
    db_session.add(
        AtsScore(
            job_id=job.id,
            target_type="base_resume",
            target_id="data_scientist",
            phase="base",
            composite=50.0,
            subscores_json={},
            skill_table_json=[],
            config_version="c1",
            engine_version="ats-1.0.0",
        )
    )
    application = Application(job_id=job.id, base_resume="data_scientist", status="draft")
    db_session.add(application)
    db_session.flush()
    # Older tailored row 55, newer 65 -> lift uses ONLY the newest (15.0).
    older = AtsScore(
        job_id=job.id,
        target_type="application",
        target_id=str(application.id),
        application_id=application.id,
        phase="tailored",
        composite=55.0,
        subscores_json={},
            skill_table_json=[],
            config_version="c1",
            engine_version="ats-1.0.0",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    newer = AtsScore(
        job_id=job.id,
        target_type="application",
        target_id=str(application.id),
        application_id=application.id,
        phase="tailored",
        composite=65.0,
        subscores_json={},
            skill_table_json=[],
            config_version="c1",
            engine_version="ats-1.0.0",
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
    )
    db_session.add_all([older, newer])
    db_session.commit()

    row = _get(db_session).json()[0]
    assert row["avg_lift"] == 15.0
    assert row["n_tailored"] == 1


def test_base_summaries_empty_signals_are_null(db_session):
    _seed_base(db_session, "data_engineer")
    db_session.commit()
    row = _get(db_session).json()[0]
    assert row["health_score"] is None
    assert row["health_grade"] is None
    assert row["avg_base_ats"] is None
    assert row["avg_lift"] is None
    assert row["applications_total"] == 0
    assert row["in_flight"] == 0
    assert row["last_activity"] is not None  # base row's own timestamps


def test_base_summaries_omits_archived(db_session):
    from datetime import UTC, datetime

    from app.models.base_resume import BaseResume

    db_session.add(BaseResume(slug="kept", data_json={}))
    db_session.add(
        BaseResume(slug="stale_track", data_json={}, archived_at=datetime.now(UTC))
    )
    db_session.commit()

    assert [s["slug"] for s in base_summaries(db_session)] == ["kept"]
