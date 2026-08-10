import copy
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import settings
from app.db import get_db
from app.main import app
from app.models.application import Application
from app.models.base_resume import BaseResume
from app.models.ats_score import AtsScore
from app.models.job import Job
from app.services.ats.config import ENGINE_VERSION, load_config
from tests.ats.fixtures import SAMPLE_JD, SAMPLE_RESUME


def _override_db(db_session):
    def _inner():
        yield db_session

    return _inner


def _seed_job(db_session, extracted_json=SAMPLE_JD):
    job = Job(raw_text="jd", raw_text_hash="router-ats-hash", extracted_json=extracted_json)
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def _seed_base(db_session, tmp_path, monkeypatch, slug="data_scientist"):
    monkeypatch.setattr(settings, "base_resumes_dir", tmp_path)
    (tmp_path / f"{slug}.json").write_text(json.dumps(SAMPLE_RESUME))
    db_session.add(BaseResume(slug=slug, data_json=SAMPLE_RESUME))
    db_session.commit()
    return slug


def test_run_ats_scores_all_bases(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    _seed_base(db_session, tmp_path, monkeypatch, "data_scientist")
    (tmp_path / "data_engineer.json").write_text(json.dumps(SAMPLE_RESUME))
    db_session.add(BaseResume(slug="data_engineer", data_json=SAMPLE_RESUME))
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post("/api/ats-scores", json={"job_id": str(job.id)})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert {row["target_id"] for row in body} == {"data_scientist", "data_engineer"}
    assert body[0]["phase"] == "base"
    assert "skill_table_json" in body[0] and body[0]["skill_table_json"]
    assert "keyword" in body[0]["subscores_json"]


def test_run_ats_scores_single_base_target_defaults_to_base_phase(
    db_session, tmp_path, monkeypatch
):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            "/api/ats-scores",
            json={"job_id": str(job.id), "target_type": "base_resume", "target_id": slug},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["target_id"] == slug
    assert body[0]["phase"] == "base"
    assert body[0]["application_id"] is None


def test_run_ats_scores_single_application_target_defaults_to_tailored_phase(
    db_session, tmp_path, monkeypatch
):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    application = Application(
        job_id=job.id, base_resume=slug, status="draft", customized_json=SAMPLE_RESUME
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            "/api/ats-scores",
            json={
                "job_id": str(job.id),
                "target_type": "application",
                "target_id": str(application.id),
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["phase"] == "tailored"
    assert body[0]["application_id"] == str(application.id)


def test_list_ats_scores(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        run = client.post("/api/ats-scores", json={"job_id": str(job.id)})
        listing = client.get(f"/api/ats-scores?job_id={job.id}")
    finally:
        app.dependency_overrides.clear()

    assert run.status_code == 200
    assert listing.status_code == 200
    body = listing.json()
    assert len(body) == 1
    assert body[0]["target_id"] == "data_scientist"
    assert body[0]["phase"] == "base"


def test_compare_endpoint(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    improved = copy.deepcopy(SAMPLE_RESUME)
    improved["skills"][0]["items"].append("Salesforce")
    improved["experience"][0]["bullets"].append("Integrated Salesforce CRM data.")
    application = Application(
        job_id=job.id, base_resume=slug, status="draft", customized_json=improved
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get(f"/api/applications/{application.id}/ats-compare")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["application_id"] == str(application.id)
    # base/tailored are AtsScore ORM rows serialized through AtsScoreRead.
    assert body["base"]["phase"] == "base"
    assert body["base"]["target_id"] == slug
    assert body["tailored"]["phase"] == "tailored"
    assert body["tailored"]["application_id"] == str(application.id)
    assert body["delta"]["composite"] > 0
    moved = [d for d in body["skill_diff"] if d["jd_skill"] == "Salesforce"]
    assert moved and moved[0]["before"]["matched"] is False and moved[0]["after"]["matched"] is True


def test_compare_endpoint_422s_for_pre_phase2_config_row(
    db_session, tmp_path, monkeypatch
):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    application = Application(
        job_id=job.id,
        base_resume=slug,
        status="draft",
        customized_json=SAMPLE_RESUME,
    )
    db_session.add(application)
    db_session.flush()
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    common = {
        "job_id": job.id,
        "composite": 50.0,
        "subscores_json": {},
        "skill_table_json": [],
        "engine_version": ENGINE_VERSION,
    }
    db_session.add_all([
        AtsScore(
            **common,
            target_type="base_resume",
            target_id=slug,
            phase="base",
            config_version="pre-phase2",
            created_at=now,
        ),
        AtsScore(
            **common,
            target_type="application",
            target_id=str(application.id),
            application_id=application.id,
            phase="tailored",
            config_version=load_config().version,
            created_at=now + timedelta(seconds=1),
        ),
    ])
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get(f"/api/applications/{application.id}/ats-compare")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "versions" in response.json()["detail"]


def test_run_ats_scores_422_without_extracted_skills(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session, extracted_json={"title": "X", "skills": []})
    _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post("/api/ats-scores", json={"job_id": str(job.id)})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "skills" in response.json()["detail"]


def test_run_ats_scores_unknown_job_returns_422(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post("/api/ats-scores", json={"job_id": str(uuid4())})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "Job not found" in response.json()["detail"]


def test_run_ats_scores_honors_explicit_phase_override(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    application = Application(
        job_id=job.id, base_resume=slug, status="draft", customized_json=SAMPLE_RESUME
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            "/api/ats-scores",
            json={
                "job_id": str(job.id),
                "target_type": "application",
                "target_id": str(application.id),
                "phase": "base",
            },
        )
    finally:
        app.dependency_overrides.clear()

    # Application targets default to "tailored"; an explicit phase must win.
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["phase"] == "base"
    assert body[0]["target_type"] == "application"


def test_run_ats_scores_invalid_application_uuid_returns_422(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            "/api/ats-scores",
            json={"job_id": str(job.id), "target_type": "application", "target_id": "not-a-uuid"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "Invalid application id" in response.json()["detail"]


def test_run_ats_scores_partial_target_returns_422(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    _seed_base(db_session, tmp_path, monkeypatch)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            "/api/ats-scores",
            json={"job_id": str(job.id), "target_type": "base_resume"},
        )
    finally:
        app.dependency_overrides.clear()

    # target_type without target_id (or vice versa) must not silently score-all.
    assert response.status_code == 422


def test_compare_unknown_application_returns_422(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get(f"/api/applications/{uuid4()}/ats-compare")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "Application not found" in response.json()["detail"]
