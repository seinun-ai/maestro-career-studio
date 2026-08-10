import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings as app_settings
from app.db import get_db
from app.main import app
from app.models.application import Application
from app.models.job import Job
from app.models.qa_entry import QAEntry
from app.routers import qa


def _override_db(db_session):
    def _inner():
        yield db_session

    return _inner


def _application(db_session):
    job = Job(
        raw_text="Need analytics",
        raw_text_hash="qa-router-hash",
        extracted_json={"title": "Data Analyst", "company": "Acme"},
        title="Data Analyst",
        company="Acme",
        extracted_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.flush()
    application = Application(job_id=job.id, base_resume="data_analyst", status="draft")
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)
    return application


def test_post_qa_runs_questions_for_application(db_session, monkeypatch):
    application = _application(db_session)
    monkeypatch.setattr(
        qa.qa_service,
        "answer_questions",
        lambda application_id, questions, session=None: ["Answer one"],
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            "/api/qa",
            json={"application_id": str(application.id), "questions": ["Question one?"]},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "answers": ["Answer one"],
        "cover_letter": None,
    }


def test_post_qa_rejects_cold_message_payload(db_session):
    # Cold message was removed 2026-07-21; QARequest forbids unknown fields so
    # stale callers fail loud with 422 instead of silently generating nothing.
    application = _application(db_session)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            "/api/qa",
            json={
                "application_id": str(application.id),
                "cold_message": {"instructions": "DM the recruiter"},
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_post_qa_runs_cover_letter_for_job(db_session, monkeypatch):
    application = _application(db_session)
    monkeypatch.setattr(
        qa.qa_service,
        "generate_cover_letter_for_job",
        lambda job_id, tone, session=None: f"Cover letter: {tone}",
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            "/api/qa",
            json={"job_id": str(application.job_id), "cover_letter": {"tone": "formal"}},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["cover_letter"] == "Cover letter: formal"


def test_post_qa_requires_target_and_work(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        no_target = TestClient(app).post("/api/qa", json={"questions": ["Q?"]})
        no_work = TestClient(app).post("/api/qa", json={"job_id": "00000000-0000-0000-0000-000000000000"})
    finally:
        app.dependency_overrides.clear()

    assert no_target.status_code == 400
    assert no_work.status_code == 400


def test_delete_qa_entry(db_session):
    application = _application(db_session)
    entry = QAEntry(
        application_id=application.id,
        kind="question",
        prompt="Q?",
        answer="A.",
        model_used="m",
    )
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).delete(f"/api/qa/{entry.id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert db_session.get(QAEntry, entry.id) is None


def test_patch_qa_entry_updates_answer_and_clears_pdf(db_session, tmp_path):
    application = _application(db_session)
    pdf_file = tmp_path / "cover_letter.pdf"
    pdf_file.write_bytes(b"%PDF old")
    entry = QAEntry(
        application_id=application.id,
        kind="cover_letter",
        prompt="cover letter",
        answer="old text",
        pdf_path=str(pdf_file),
    )
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).patch(
            f"/api/qa/{entry.id}",
            json={"answer": "edited cover letter"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "edited cover letter"
    assert body["pdf_path"] is None
    assert not pdf_file.exists()


def test_render_cover_letter_writes_pdf_and_sets_path(
    db_session, tmp_path, monkeypatch
):
    application = _application(db_session)
    entry = QAEntry(
        application_id=application.id,
        kind="cover_letter",
        prompt="cover letter",
        answer="Dear Hiring Manager,\n\nI'm excited.\n\nSincerely,\nJane",
    )
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)

    monkeypatch.setattr(app_settings, "applications_dir", tmp_path)
    monkeypatch.setattr(
        qa.base_resume_data,
        "load_base_resume",
        lambda slug, session=None: {
            "contact": {
                "name": "Jane Doe",
                "email": "jane@example.com",
                "location": "Austin, TX",
            }
        },
    )

    def fake_compile(tex, out_dir, stem="cover_letter"):
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{stem}.pdf"
        path.write_bytes(b"%PDF test")
        return path

    monkeypatch.setattr(qa.pdf_render, "compile_cover_letter_pdf", fake_compile)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(f"/api/qa/{entry.id}/render")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["pdf_path"].endswith(
        "Jane_Doe_DataAnalyst_CoverLetter.pdf"
    )
    assert Path(body["pdf_path"]).exists()
    db_session.refresh(application)
    assert application.artifact_dir
    assert Path(body["pdf_path"]).parent == Path(application.artifact_dir)
    assert Path(application.artifact_dir).name.endswith(f"_{application.id.hex[:8]}")


def test_get_cover_letter_pdf_streams_file(db_session, tmp_path):
    application = _application(db_session)
    pdf_file = tmp_path / "260501_Quill_Riley_DataAnalyst_TechCorp_CoverLetter.pdf"
    pdf_file.write_bytes(b"%PDF test")
    entry = QAEntry(
        application_id=application.id,
        kind="cover_letter",
        prompt="cover letter",
        answer="...",
        pdf_path=str(pdf_file),
    )
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get(f"/api/qa/{entry.id}/pdf")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="260501_Quill_Riley_DataAnalyst_TechCorp_CoverLetter.pdf"'
    )
    assert response.content.startswith(b"%PDF")


def test_get_cover_letter_pdf_404_when_missing(db_session):
    application = _application(db_session)
    entry = QAEntry(
        application_id=application.id,
        kind="cover_letter",
        prompt="cover letter",
        answer="...",
    )
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get(f"/api/qa/{entry.id}/pdf")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_generate_cover_letter_replaces_prior_entry_and_pdf(
    db_session, tmp_path, monkeypatch
):
    application = _application(db_session)
    old_pdf = tmp_path / "cover_letter.pdf"
    old_pdf.write_bytes(b"old")
    old_entry = QAEntry(
        application_id=application.id,
        kind="cover_letter",
        prompt="cover letter",
        answer="old",
        pdf_path=str(old_pdf),
    )
    db_session.add(old_entry)
    db_session.commit()

    def fake_generate(app_id, tone, session=None):
        session.add(
            QAEntry(
                application_id=app_id,
                kind="cover_letter",
                prompt=None,
                answer="fresh cover letter text",
                model_used="test-model",
            )
        )
        session.commit()
        return "fresh cover letter text"

    monkeypatch.setattr(qa.qa_service, "generate_cover_letter", fake_generate)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            "/api/qa",
            json={
                "application_id": str(application.id),
                "cover_letter": {"tone": "balanced"},
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert not old_pdf.exists()
    rows = db_session.scalars(
        select(QAEntry).where(
            QAEntry.application_id == application.id,
            QAEntry.kind == "cover_letter",
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].answer == "fresh cover letter text"


def test_regenerate_qa_entry_overwrites_answer(db_session, monkeypatch):
    application = _application(db_session)
    entry = QAEntry(
        application_id=application.id,
        kind="question",
        prompt="Q?",
        answer="old",
        model_used="m",
    )
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)

    def fake_regen(entry_id, tone=None, session=None):
        target = session.get(QAEntry, entry_id)
        target.answer = "new"
        session.commit()
        session.refresh(target)
        return target

    monkeypatch.setattr(qa.qa_service, "regenerate_entry", fake_regen)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(f"/api/qa/{entry.id}/regenerate")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["answer"] == "new"


def test_regenerate_qa_entry_unsupported_kind_returns_400(db_session):
    # Retired/unknown kinds (cold_message removed 2026-07-21) must fail as a
    # handled 4xx that names the kind — not a 500. Runs the real service so the
    # router's ValueError→400 mapping is exercised end to end; customized_json
    # is set so _application_context skips the base-resume disk load.
    job = Job(
        raw_text="Need analytics",
        raw_text_hash="qa-regen-badkind-hash",
        extracted_json={"title": "Data Analyst", "company": "Acme"},
        title="Data Analyst",
        company="Acme",
        extracted_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.flush()
    application = Application(
        job_id=job.id,
        base_resume="data_analyst",
        status="draft",
        customized_json={"summary": "x"},
    )
    db_session.add(application)
    db_session.flush()
    entry = QAEntry(
        application_id=application.id,
        kind="cold_message",
        prompt="Reach out to the recruiter",
        answer="old",
        model_used="m",
    )
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(f"/api/qa/{entry.id}/regenerate")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "cold_message" in response.json()["detail"]


def test_regenerate_qa_entry_missing_returns_404(db_session):
    # A genuinely missing entry stays a 404 — only the unsupported-kind case
    # became a 400.
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(f"/api/qa/{uuid.uuid4()}/regenerate")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_get_qa_lists_entries(db_session):
    application = _application(db_session)
    db_session.add(
        QAEntry(
            application_id=application.id,
            kind="question",
            prompt="Question?",
            answer="Answer.",
            model_used="test-model",
        )
    )
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get(f"/api/qa?application_id={application.id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["prompt"] == "Question?"
    assert body[0]["answer"] == "Answer."
