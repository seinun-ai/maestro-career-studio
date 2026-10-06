"""The tracker's list rows carry a read-only ATS score (owner decision D6)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.application import Application
from app.models.ats_score import AtsScore
from app.models.base_resume import BaseResume
from app.models.job import Job


def _override_db(db_session):
    def _inner():
        yield db_session

    return _inner


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


_seq = {"n": 0}


def _job(db_session):
    _seq["n"] += 1
    job = Job(
        raw_text="Need Python",
        raw_text_hash=f"tracker-scores-{_seq['n']}",
        extracted_json={"title": "Data Scientist", "company": "Acme"},
        title="Data Scientist",
        company="Acme",
        role_category="data_scientist",
        extracted_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def _application(db_session, job, base_resume="data_scientist"):
    application = Application(job_id=job.id, base_resume=base_resume, status="draft")
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)
    return application


def _score(db_session, job, *, target_type, target_id, phase, composite, application_id=None, age=0):
    db_session.add(
        AtsScore(
            job_id=job.id, target_type=target_type, target_id=target_id, phase=phase,
            composite=composite, subscores_json={}, skill_table_json=[],
            config_version="c1", engine_version="ats-1.0.0", application_id=application_id,
            created_at=datetime.now(UTC) - timedelta(minutes=age),
        )
    )
    db_session.commit()


def _app_row(client, application):
    return next(r for r in client.get("/api/applications").json() if r["id"] == str(application.id))


def _job_row(client, job):
    rows = client.get("/api/jobs?without_application=true").json()
    return next(r for r in rows if r["id"] == str(job.id))


def test_application_summary_carries_tailored_else_base_score(client, db_session):
    job = _job(db_session)
    application = _application(db_session, job)
    assert _app_row(client, application)["ats_score"] is None
    _score(db_session, job, target_type="base_resume", target_id="data_scientist", phase="base", composite=61.0)
    # Another resume's base row for the same job is not this application's score.
    _score(db_session, job, target_type="base_resume", target_id="other", phase="base", composite=99.0)
    assert _app_row(client, application)["ats_score"] == 61.0
    _score(db_session, job, target_type="application", target_id=str(application.id),
           application_id=application.id, phase="tailored", composite=60.0, age=5)
    _score(db_session, job, target_type="application", target_id=str(application.id),
           application_id=application.id, phase="tailored", composite=67.2)
    assert _app_row(client, application)["ats_score"] == 67.2


def test_saved_job_carries_its_best_base_score(client, db_session):
    job = _job(db_session)
    _score(db_session, job, target_type="base_resume", target_id="a", phase="base", composite=55.0)
    _score(db_session, job, target_type="base_resume", target_id="b", phase="base", composite=62.5)
    assert _job_row(client, job)["best_ats_score"] == 62.5


def test_no_score_reads_null_not_zero(client, db_session):
    job = _job(db_session)
    assert _job_row(client, job)["best_ats_score"] is None


def test_listing_never_writes_scores(client, db_session):
    job = _job(db_session)
    _application(db_session, job)
    client.get("/api/applications")
    client.get("/api/jobs")
    assert db_session.query(AtsScore).count() == 0


def test_best_score_ignores_archived_bases_but_an_application_keeps_its_own(client, db_session):
    job = _job(db_session)
    saved = _job(db_session)
    application = _application(db_session, job, base_resume="old")
    for slug in ("old", "kept"):
        db_session.add(BaseResume(slug=slug, role_category="data_scientist", data_json={}))
    db_session.commit()
    _score(db_session, job, target_type="base_resume", target_id="old", phase="base", composite=72.0)
    _score(db_session, job, target_type="base_resume", target_id="kept", phase="base", composite=60.0)
    _score(db_session, saved, target_type="base_resume", target_id="old", phase="base", composite=72.0)
    _score(db_session, saved, target_type="base_resume", target_id="kept", phase="base", composite=60.0)
    db_session.query(BaseResume).filter_by(slug="old").update({"archived_at": datetime.now(UTC)})
    db_session.commit()
    assert _job_row(client, saved)["best_ats_score"] == 60.0
    # An application outlives its base: its own base row still shows.
    assert _app_row(client, application)["ats_score"] == 72.0
