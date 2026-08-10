"""Lifecycle fixes from the 2026-07-15 applications-workflow audit (design D1-D11).

Covers: applied_at preservation across post-applied statuses, the unified
from-base reuse policy, tailoring-session supersede/close terminal states,
re-extract guard for capture-path jobs, source_url dedup + already_existed,
the server-side summary join, and post-commit artifact removal incl. preview
pages directories.
"""
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import settings
from app.db import get_db
from app.main import app
from app.models.application import Application
from app.models.base_resume import BaseResume
from app.models.job import Job
from app.models.tailoring_session import TailoringSession
from app.services import artifacts, ats_score, tailoring_session
from tests.ats.fixtures import SAMPLE_JD, SAMPLE_RESUME

# The ingest endpoint validates against JobExtraction (strict literals); the
# engine fixture uses looser display values, so patch the enum fields.
INGEST_JD = {**SAMPLE_JD, "role_category": "data_scientist"}


def _hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def _override_db(db_session):
    def _inner():
        yield db_session

    return _inner


def _client(db_session) -> TestClient:
    app.dependency_overrides[get_db] = _override_db(db_session)
    return TestClient(app)


def _seed_job(db_session, *, raw_text="jd text", raw_hash="lifecycle-hash", source_url=None):
    job = Job(
        raw_text=raw_text,
        raw_text_hash=raw_hash,
        source_url=source_url,
        extracted_json=SAMPLE_JD,
        title="Data Scientist",
        company="Acme",
        location="Remote",
        extracted_at=datetime.now(UTC),
    )
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


def _seed_application(db_session, job, **kwargs):
    application = Application(job_id=job.id, base_resume="data_scientist", **kwargs)
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)
    return application


# --- D2: applied_at across status transitions -------------------------------


def test_status_past_applied_preserves_applied_at(db_session):
    job = _seed_job(db_session)
    applied_on = datetime(2026, 3, 1, tzinfo=UTC)
    application = _seed_application(
        db_session, job, status="applied", applied_at=applied_on
    )
    client = _client(db_session)
    try:
        for status in ("interviewing", "offered", "accepted", "rejected", "withdrawn"):
            response = client.patch(
                f"/api/applications/{application.id}", json={"status": status}
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["status"] == status
            assert body["applied_at"] is not None, (
                f"applied_at erased on transition to {status}"
            )
    finally:
        app.dependency_overrides.clear()


def test_status_back_to_draft_clears_applied_at(db_session):
    job = _seed_job(db_session)
    application = _seed_application(
        db_session, job, status="applied", applied_at=datetime(2026, 3, 1, tzinfo=UTC)
    )
    client = _client(db_session)
    try:
        response = client.patch(
            f"/api/applications/{application.id}", json={"status": "draft"}
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["applied_at"] is None


def test_jump_to_interviewing_stamps_applied_at(db_session):
    """Skipping the 'applied' step still implies you applied: entering any
    post-applied pipeline stage stamps the date if unset (review finding)."""
    job = _seed_job(db_session)
    application = _seed_application(db_session, job, status="draft")
    client = _client(db_session)
    try:
        response = client.patch(
            f"/api/applications/{application.id}", json={"status": "interviewing"}
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["applied_at"] is not None


def test_withdrawn_from_draft_has_no_applied_at(db_session):
    job = _seed_job(db_session)
    application = _seed_application(db_session, job, status="draft")
    client = _client(db_session)
    try:
        response = client.patch(
            f"/api/applications/{application.id}", json={"status": "withdrawn"}
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["applied_at"] is None


# --- D3: from-base reuse policy ----------------------------------------------


def test_from_base_reuses_existing_application(db_session, tmp_path, monkeypatch):
    """Without application_id, from-base updates the job's newest application
    for that base instead of inserting an unreachable duplicate (audit C2)."""
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    existing = _seed_application(
        db_session,
        job,
        status="applied",
        applied_at=datetime(2026, 3, 1, tzinfo=UTC),
        notes="keep me",
        customized_json=SAMPLE_RESUME,
    )

    client = _client(db_session)
    try:
        response = client.post(
            "/api/applications/from-base",
            json={"job_id": str(job.id), "base_resume": slug, "ops": []},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    assert response.json()["id"] == str(existing.id)
    count = len(
        db_session.query(Application).filter(Application.job_id == job.id).all()
    )
    assert count == 1
    db_session.refresh(existing)
    assert existing.status == "applied"
    assert existing.notes == "keep me"
    assert existing.applied_at is not None


def test_from_base_creates_when_none_exists(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    client = _client(db_session)
    try:
        response = client.post(
            "/api/applications/from-base",
            json={"job_id": str(job.id), "base_resume": slug, "ops": []},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "draft"


def test_from_base_skips_base_rescore_when_row_exists(db_session, tmp_path, monkeypatch):
    """The base row is an upsert singleton — from-base must not re-run the
    engine for it when it already exists (audit C20)."""
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    ats_score.score_target(job.id, "base_resume", slug, phase="base", session=db_session)

    phases: list[str] = []
    real = ats_score.score_target

    def counting(*args, **kwargs):
        phases.append(kwargs.get("phase"))
        return real(*args, **kwargs)

    from app.routers import applications as applications_router

    monkeypatch.setattr(applications_router.ats_score, "score_target", counting)

    client = _client(db_session)
    try:
        response = client.post(
            "/api/applications/from-base",
            json={"job_id": str(job.id), "base_resume": slug, "ops": []},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    assert phases == ["tailored"]


# --- D4: session supersede + close -------------------------------------------


def test_create_session_supersedes_prior_open(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)

    first = tailoring_session.create_session(job.id, slug, enrich=False, session=db_session)
    second = tailoring_session.create_session(job.id, slug, enrich=False, session=db_session)

    db_session.refresh(first)
    assert first.status == "superseded"
    assert second.status == "open"


def test_create_session_leaves_tailored_sessions_alone(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    done = TailoringSession(
        job_id=job.id, base_resume=slug, status="tailored", gaps_json={"categories": []}
    )
    db_session.add(done)
    db_session.commit()

    tailoring_session.create_session(job.id, slug, enrich=False, session=db_session)
    db_session.refresh(done)
    assert done.status == "tailored"


def test_close_session_endpoint(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    session_row = tailoring_session.create_session(
        job.id, slug, enrich=False, session=db_session
    )

    client = _client(db_session)
    try:
        response = client.post(f"/api/tailoring-sessions/{session_row.id}/close")
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "abandoned"
        # closing again -> 409 (not open anymore)
        again = client.post(f"/api/tailoring-sessions/{session_row.id}/close")
        assert again.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_close_tailored_session_409(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    done = TailoringSession(
        job_id=job.id, base_resume=slug, status="tailored", gaps_json={"categories": []}
    )
    db_session.add(done)
    db_session.commit()
    db_session.refresh(done)

    client = _client(db_session)
    try:
        response = client.post(f"/api/tailoring-sessions/{done.id}/close")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 409


# --- D7/D8: jobs ingest guards -----------------------------------------------


def test_re_extract_400_for_capture_path_job(db_session):
    job = _seed_job(db_session, raw_text="", raw_hash="capture-hash")
    client = _client(db_session)
    try:
        response = client.post(f"/api/jobs/{job.id}/re-extract")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 400
    assert "re-ingest" in response.json()["detail"]


def test_create_job_with_different_text_at_reused_url_is_a_new_job(db_session, monkeypatch):
    """Paste-path dedup is hash-only: careers pages reuse URLs across postings,
    so different raw text at a known URL is a DIFFERENT job (review finding —
    a URL fallback here silently swallowed new postings)."""
    url = "https://boards.example.com/acme/123"
    existing = _seed_job(
        db_session, raw_text="original text", raw_hash="url-dedup", source_url=url
    )

    from app.routers import jobs as jobs_router

    monkeypatch.setattr(
        jobs_router.jd_extraction,
        "extract_jd",
        lambda raw_text, db: {"title": "New Role", "company": "Acme", "skills": []},
    )

    client = _client(db_session)
    try:
        response = client.post(
            "/api/jobs",
            json={"raw_text": "a genuinely different posting", "source_url": url},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    assert response.json()["id"] != str(existing.id)
    assert response.json()["already_existed"] is False


def test_create_job_same_text_still_dedupes_before_llm(db_session, monkeypatch):
    _seed_job(db_session, raw_text="verbatim text", raw_hash=_hash("verbatim text"))

    from app.routers import jobs as jobs_router

    def no_llm(*args, **kwargs):  # dedup must short-circuit BEFORE extraction
        raise AssertionError("extract_jd must not be called on a dedup hit")

    monkeypatch.setattr(jobs_router.jd_extraction, "extract_jd", no_llm)

    client = _client(db_session)
    try:
        response = client.post("/api/jobs", json={"raw_text": "verbatim text"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    assert response.json()["already_existed"] is True


def test_ingest_dedupes_by_source_url_without_raw_text(db_session):
    """Capture-path dedup: the extraction-JSON hash is unstable across LLM runs;
    the URL is the stable identifier (audit C15)."""
    url = "https://boards.example.com/acme/456"
    existing = _seed_job(
        db_session, raw_text="", raw_hash="capture-ingest", source_url=url
    )

    client = _client(db_session)
    try:
        response = client.post(
            "/api/jobs/ingest",
            json={"extracted_json": INGEST_JD, "source_url": url},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    assert response.json()["id"] == str(existing.id)
    assert response.json()["already_existed"] is True


def test_fresh_job_reports_already_existed_false(db_session):
    client = _client(db_session)
    try:
        response = client.post(
            "/api/jobs/ingest",
            json={"extracted_json": INGEST_JD, "raw_text": "fresh capture text"},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    assert response.json()["already_existed"] is False


# --- D11: summary join --------------------------------------------------------


def test_list_applications_includes_job_fields(db_session):
    job = _seed_job(db_session)
    _seed_application(db_session, job, status="draft")
    client = _client(db_session)
    try:
        response = client.get("/api/applications")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    row = response.json()[0]
    assert row["job_title"] == "Data Scientist"
    assert row["job_company"] == "Acme"
    assert row["job_location"] == "Remote"


# --- D10: artifact removal includes preview pages dir -------------------------


def test_remove_files_takes_preview_pages_dir(tmp_path):
    pdf = tmp_path / "out" / "resume.pdf"
    pdf.parent.mkdir()
    pdf.write_bytes(b"%PDF-1.4")
    pages = Path(str(pdf.with_suffix(".pages")))
    pages.mkdir()
    (pages / "page-1.png").write_bytes(b"png")

    artifacts.remove_files([pdf])

    assert not pdf.exists()
    assert not pages.exists()
    # the emptied parent folder is pruned too
    assert not pdf.parent.exists()


def test_stage_resume_artifact_removal_defers_disk_io(db_session, tmp_path):
    job = _seed_job(db_session)
    pdf = tmp_path / "keep" / "resume.pdf"
    pdf.parent.mkdir()
    pdf.write_bytes(b"%PDF-1.4")
    application = _seed_application(
        db_session, job, status="draft", pdf_path=str(pdf)
    )

    stale = artifacts.stage_resume_artifact_removal(application)

    assert application.pdf_path is None
    assert pdf.exists(), "staging must not touch the disk"
    artifacts.remove_files(stale)
    assert not pdf.exists()


# --- Stale-session detection (SYSTEM.md §11 item 1) ---------------------------


def _make_session(db_session, tmp_path, monkeypatch):
    job = _seed_job(db_session)
    slug = _seed_base(db_session, tmp_path, monkeypatch)
    row = tailoring_session.create_session(job.id, slug, enrich=False, session=db_session)
    return job, slug, row


def test_create_session_freezes_content_hashes(db_session, tmp_path, monkeypatch):
    _, _, row = _make_session(db_session, tmp_path, monkeypatch)
    assert row.base_content_hash
    assert row.jd_extraction_hash


def test_fresh_session_reports_no_stale_reason(db_session, tmp_path, monkeypatch):
    _, _, row = _make_session(db_session, tmp_path, monkeypatch)
    assert tailoring_session.staleness_reason(row, db_session) is None


def test_base_edit_makes_session_stale(db_session, tmp_path, monkeypatch):
    _, slug, row = _make_session(db_session, tmp_path, monkeypatch)
    edited = {**SAMPLE_RESUME, "summary": "Edited after the session froze."}
    (tmp_path / f"{slug}.json").write_text(json.dumps(edited))
    db_session.query(BaseResume).filter_by(slug=slug).update({"data_json": edited})
    db_session.commit()

    reason = tailoring_session.staleness_reason(row, db_session)
    assert reason and "base resume" in reason

    client = _client(db_session)
    try:
        resp = client.patch(
            f"/api/tailoring-sessions/{row.id}",
            json={"resolutions": [], "replace": False},
        )
        assert resp.status_code == 409
        assert "stale" in resp.json()["detail"]
        tailor_resp = client.post(f"/api/tailoring-sessions/{row.id}/tailor", json={})
        assert tailor_resp.status_code == 409
        get_resp = client.get(f"/api/tailoring-sessions/{row.id}")
        assert get_resp.json()["stale_reason"]
    finally:
        app.dependency_overrides.clear()


def test_jd_reextract_makes_session_stale(db_session, tmp_path, monkeypatch):
    job, _, row = _make_session(db_session, tmp_path, monkeypatch)
    job.extracted_json = {**SAMPLE_JD, "title": "Re-extracted Title"}
    db_session.commit()

    reason = tailoring_session.staleness_reason(row, db_session)
    assert reason and "job description" in reason


def test_legacy_session_without_hashes_is_treated_fresh(db_session, tmp_path, monkeypatch):
    _, _, row = _make_session(db_session, tmp_path, monkeypatch)
    row.base_content_hash = None
    row.jd_extraction_hash = None
    db_session.commit()
    assert tailoring_session.staleness_reason(row, db_session) is None
