import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import settings as app_settings
from app.db import SessionLocal, get_db
from app.main import app
from app.models.application import Application
from app.models.job import Job
from app.models.qa_entry import QAEntry
from app.models.template import Template
from app.routers import qa
from app.services import engines
from app.services import template_registry as reg


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
        lambda job_id, tone, session=None, base_slug=None: f"Cover letter: {tone}",
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


def test_post_qa_threads_the_named_base_to_the_job_answer(db_session, monkeypatch):
    """`base` is a request key, so the route has to carry it — a schema field
    the handler drops is the half-wired API this repo pins against."""
    application = _application(db_session)
    seen = {}

    def fake_answers(job_id, questions, session=None, base_slug=None):
        seen["base"] = base_slug
        return ["Answered."]

    monkeypatch.setattr(qa.qa_service, "answer_questions_for_job", fake_answers)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            "/api/qa",
            json={"job_id": str(application.job_id), "questions": ["Why us?"],
                  "base": "data_scientist"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert seen["base"] == "data_scientist"


def test_post_qa_threads_the_named_base_to_the_job_cover_letter_too(db_session, monkeypatch):
    """The twin of the test above, and it earns its place rather than mirroring
    it for symmetry's sake.

    `base` is ONE request key, and `run_qa` has TWO job branches. A key honoured
    on the questions branch and silently dropped on the cover-letter one is the
    half-wired API this repo pins against — the caller names a resume, gets an
    answer written from a different one, and nothing anywhere says so. Both
    branches ground on the same read, so both carry it.
    """
    application = _application(db_session)
    seen = {}

    def fake_cover(job_id, tone, session=None, base_slug=None):
        seen["base"] = base_slug
        return "Cover letter."

    monkeypatch.setattr(qa.qa_service, "generate_cover_letter_for_job", fake_cover)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            "/api/qa",
            json={"job_id": str(application.job_id), "cover_letter": {"tone": "warm"},
                  "base": "data_scientist"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert seen["base"] == "data_scientist"


def test_post_qa_answers_an_unreadable_base_with_a_reason_not_a_500(db_session, monkeypatch):
    """The guard's outward face.

    What shipped was a bare `FileNotFoundError` out of the disk read — an
    unexplained 500 for what is really "that resume has no data file", on an
    install that need not carry the default at all. The caller gets a 400 and a
    detail naming the slug, which is what the side panel renders in its note.
    """
    application = _application(db_session)

    def refuse(job_id, questions, session=None, base_slug=None):
        raise qa.qa_service.BaseResumeUnavailable("Base resume 'ghost' has no data file")

    monkeypatch.setattr(qa.qa_service, "answer_questions_for_job", refuse)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            "/api/qa",
            json={"job_id": str(application.job_id), "questions": ["Why us?"],
                  "base": "ghost"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["detail"] == "Base resume 'ghost' has no data file"


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

    def fake_compile(source, out_dir, stem="cover_letter", **kwargs):
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


def test_prior_cover_letter_delete_is_committed_before_generation(
    db_session, tmp_path, monkeypatch
):
    """The replace-DELETE must land before the LLM call, not sit flushed across it.

    A flushed-but-uncommitted DELETE holds SQLite's write lock for the whole
    generation (tens of seconds), so every other writer waits out the 30 s
    busy_timeout and then fails with "database is locked" (design §3.2). The
    observer below reads on ANOTHER connection: under WAL it sees the last
    COMMITTED state, so a still-open transaction shows up as the prior row
    still being there.
    """
    application = _application(db_session)
    old_pdf = tmp_path / "cover_letter.pdf"
    old_pdf.write_bytes(b"old")
    db_session.add(
        QAEntry(
            application_id=application.id,
            kind="cover_letter",
            prompt="cover letter",
            answer="old",
            pdf_path=str(old_pdf),
        )
    )
    db_session.commit()

    seen_by_other_connection: list[int] = []

    def fake_generate(app_id, tone, session):
        with SessionLocal() as observer:
            seen_by_other_connection.append(
                observer.scalar(
                    select(func.count())
                    .select_from(QAEntry)
                    .where(
                        QAEntry.application_id == app_id,
                        QAEntry.kind == "cover_letter",
                    )
                )
            )
        session.add(
            QAEntry(
                application_id=app_id,
                kind="cover_letter",
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
    assert seen_by_other_connection == [0]
    # Staged removal (§6 {#inv-staged-artifact-removal}): the file goes after
    # the commit, never before it — but it does go.
    assert not old_pdf.exists()


def test_failed_generation_leaves_no_prior_row_and_no_prior_file(
    db_session, tmp_path, monkeypatch
):
    """Rows and files stay consistent when generation blows up mid-request.

    The replace DELETE is committed before the call, so a failure cannot put
    the prior entries back — and because their PDFs are removed AFTER that
    commit, it cannot leave a surviving row pointing at a deleted file either.
    Both halves are gone, which is the state the next request can work from.
    """
    application = _application(db_session)
    old_pdf = tmp_path / "cover_letter.pdf"
    old_pdf.write_bytes(b"old")
    db_session.add(
        QAEntry(
            application_id=application.id,
            kind="cover_letter",
            answer="old",
            pdf_path=str(old_pdf),
        )
    )
    db_session.commit()

    def boom(app_id, tone, session):
        raise RuntimeError("provider down")

    monkeypatch.setattr(qa.qa_service, "generate_cover_letter", boom)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        with pytest.raises(RuntimeError, match="provider down"):
            TestClient(app).post(
                "/api/qa",
                json={
                    "application_id": str(application.id),
                    "cover_letter": {"tone": "balanced"},
                },
            )
    finally:
        app.dependency_overrides.clear()

    # Read the rows on ANOTHER connection: the request's own session would show
    # a merely-flushed DELETE as gone too, and it is the COMMIT that has to have
    # happened for the file removal below to be legitimate.
    with SessionLocal() as observer:
        survivors = observer.scalar(
            select(func.count())
            .select_from(QAEntry)
            .where(
                QAEntry.application_id == application.id,
                QAEntry.kind == "cover_letter",
            )
        )
    assert survivors == 0
    assert not old_pdf.exists()


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


def test_post_qa_answers_an_unknown_application_id_with_404_not_500(db_session):
    """A wrong id is "not found", not "the server broke".

    `answer_questions` raises a plain `ValueError` for an id that resolves to no
    row. Only `BaseResumeUnavailable` (its SUBCLASS) was mapped, so the id case
    fell through as an unexplained 500 while the sibling `regenerate_entry`
    answered the same shape with a 404. The detail carries the service's own
    message so the caller can see WHICH id missed.
    """
    missing = uuid.uuid4()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            "/api/qa",
            json={"application_id": str(missing), "questions": ["Why us?"]},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert str(missing) in response.json()["detail"]


# --- The cover letter follows the resume's engine (design 2026-09-19 §2.3) ---


def _seed_templates(db_session, *, typst_ready: bool) -> None:
    """Every seed as a draft row (no compile); optionally mark typst-classic ready."""
    reg.reset_seed_validation_attempts()
    reg.ensure_seed_templates(db_session, validate=False)
    if typst_ready:
        db_session.get(Template, reg.TYPST_CLASSIC_ID).status = "ready"
        db_session.commit()


def _cover_letter_entry(db_session, application) -> QAEntry:
    entry = QAEntry(
        application_id=application.id,
        kind="cover_letter",
        prompt="cover letter",
        answer="Dear team,\n\nHello.\n\nJane",
    )
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)
    return entry


def test_render_cover_letter_follows_the_resume_engine_without_tex(
    db_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(engines, "pdflatex_available", lambda: False)
    _seed_templates(db_session, typst_ready=True)

    application = _application(db_session)
    entry = _cover_letter_entry(db_session, application)
    monkeypatch.setattr(app_settings, "applications_dir", tmp_path)
    monkeypatch.setattr(
        qa.base_resume_data,
        "load_base_resume",
        lambda slug, session=None: {"contact": {"name": "Jane Doe", "email": "jane@example.com"}},
    )
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(f"/api/qa/{entry.id}/render")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    body = response.json()
    assert Path(body["pdf_path"]).exists()
    assert "TeX is not installed" in body["render_note"]


def test_render_cover_letter_without_tex_or_typst_is_400_and_allocates_nothing(
    db_session, tmp_path, monkeypatch
):
    """The resolver runs BEFORE application_artifacts.get_dir, so a 400 never
    leaves an empty artifact directory (or a persisted artifact_dir) behind."""
    monkeypatch.setattr(engines, "pdflatex_available", lambda: False)
    _seed_templates(db_session, typst_ready=False)

    application = _application(db_session)
    entry = _cover_letter_entry(db_session, application)
    monkeypatch.setattr(app_settings, "applications_dir", tmp_path)
    monkeypatch.setattr(
        qa.base_resume_data,
        "load_base_resume",
        lambda slug, session=None: {"contact": {"name": "Jane Doe", "email": "jane@example.com"}},
    )
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(f"/api/qa/{entry.id}/render")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 400, response.text
    assert "needs TeX" in response.json()["detail"]
    assert not any(tmp_path.iterdir())
    db_session.refresh(application)
    assert application.artifact_dir is None
