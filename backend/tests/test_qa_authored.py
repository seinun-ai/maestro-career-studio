"""Cover letters and screening answers a connected agent wrote itself.

POST /api/qa/cover-letter and POST /api/qa/answers store the caller's text with
no model call (MCP `store_cover_letter` / `store_qa_answers`), so an install
with no AI key still gets an apply package on the job's Apply step. The
store-time rules are a generated entry's: the dash scrub (§6 inv-em-dash), and
plain form text for answers.
"""

from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import settings as app_settings
from app.models.qa_entry import QAEntry
from app.routers import qa
from tests.test_qa_router import _application

MCP = {"X-Maestro-CS-Origin": "mcp", "X-Maestro-CS-Origin-Detail": "Claude"}


@pytest.fixture(autouse=True)
def _no_model(monkeypatch):
    def refuse(**kwargs):
        raise AssertionError("a caller-authored entry must not call the model")

    monkeypatch.setattr(qa.qa_service.llm, "call_openai", refuse)


@pytest.fixture
def renders(monkeypatch, tmp_path):
    """Applications under tmp_path, a known resume contact and a compile that
    writes a stand-in PDF; yields the compiled bodies."""
    monkeypatch.setattr(app_settings, "applications_dir", tmp_path)
    monkeypatch.setattr(
        qa.base_resume_data,
        "load_base_resume",
        lambda slug, session=None: {"contact": {"name": "Jane Doe", "email": "jane@example.com"}},
    )
    bodies: list[str] = []
    real_render = qa.pdf_render.render_cover_letter

    def spy_render(**kwargs):
        bodies.append(kwargs["body"])
        return real_render(**kwargs)

    def fake_compile(source, out_dir, stem="cover_letter", **kwargs):
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{stem}.pdf"
        path.write_bytes(b"%PDF test")
        return path

    monkeypatch.setattr(qa.pdf_render, "render_cover_letter", spy_render)
    monkeypatch.setattr(qa.pdf_render, "compile_cover_letter_pdf", fake_compile)
    return bodies


def _letters(db_session, application) -> list[QAEntry]:
    db_session.expire_all()
    return list(
        db_session.scalars(
            select(QAEntry).where(
                QAEntry.application_id == application.id, QAEntry.kind == "cover_letter"
            )
        )
    )


def test_a_stored_letter_replaces_the_saved_one_and_gets_its_pdf(
    db_session, tmp_path, renders, client
):
    application = _application(db_session)
    old_pdf = tmp_path / "old_cover_letter.pdf"
    old_pdf.write_bytes(b"old")
    db_session.add(
        QAEntry(application_id=application.id, kind="cover_letter", answer="old", pdf_path=str(old_pdf))
    )
    db_session.commit()

    response = client.post(
        "/api/qa/cover-letter",
        json={
            "application_id": str(application.id),
            "text": "Dear team,\n\nI led analytics — 2020–2023.\n\nJane",
        },
        headers=MCP,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "cover_letter"
    assert body["answer"] == "Dear team,\n\nI led analytics, 2020-2023.\n\nJane"
    assert body["model_used"] == "Claude"
    assert body["render_error"] is None
    assert Path(body["pdf_path"]).name == "Jane_Doe_DataAnalyst_CoverLetter.pdf"
    assert Path(body["pdf_path"]).exists()
    assert renders == [body["answer"]]
    # One letter per application: the saved one and its PDF are gone.
    assert [row.answer for row in _letters(db_session, application)] == [body["answer"]]
    assert not old_pdf.exists()
    # The Apply step reads the application's entries.
    listed = client.get("/api/qa", params={"application_id": str(application.id)}).json()
    assert [(row["kind"], row["pdf_path"]) for row in listed] == [("cover_letter", body["pdf_path"])]


def test_a_failed_pdf_keeps_the_stored_letter_and_says_why(
    db_session, renders, monkeypatch, client
):
    application = _application(db_session)

    def broken_compile(*args, **kwargs):
        raise RuntimeError("! LaTeX Error: something broke")

    monkeypatch.setattr(qa.pdf_render, "compile_cover_letter_pdf", broken_compile)

    response = client.post(
        "/api/qa/cover-letter",
        json={"application_id": str(application.id), "text": "Dear team,\n\nHello.\n\nJane"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pdf_path"] is None
    assert body["render_error"] == "! LaTeX Error: something broke"
    assert body["model_used"] is None  # no origin header: not an agent's write
    assert [row.answer for row in _letters(db_session, application)] == ["Dear team,\n\nHello.\n\nJane"]


def test_a_letter_for_no_application_is_a_404_and_a_blank_one_a_422(db_session, client):
    application = _application(db_session)
    missing = client.post(
        "/api/qa/cover-letter",
        json={"application_id": "00000000-0000-4000-8000-000000000000", "text": "Hello"},
    )
    assert missing.status_code == 404
    blank = client.post(
        "/api/qa/cover-letter", json={"application_id": str(application.id), "text": "   "}
    )
    assert blank.status_code == 422
    assert _letters(db_session, application) == []


def test_stored_answers_are_plain_form_text_and_replace_the_same_question(db_session, client):
    application = _application(db_session)
    db_session.add_all(
        [
            QAEntry(application_id=application.id, kind="question", prompt="Why us?", answer="old"),
            QAEntry(application_id=application.id, kind="question", prompt="Other?", answer="kept"),
        ]
    )
    db_session.commit()

    response = client.post(
        "/api/qa/answers",
        json={
            "application_id": str(application.id),
            "answers": [
                {"question": "  why   US? ", "answer": "**Because** of the team — and the data."},
                {"question": "Notice period?", "answer": "first draft"},
                {"question": "notice period?", "answer": "- Two weeks"},
            ],
        },
        headers={"X-Maestro-CS-Origin": "mcp"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [(row["prompt"], row["answer"]) for row in body] == [
        ("Why us?", "Because of the team, and the data."),
        ("notice period?", "Two weeks"),
    ]
    assert {row["model_used"] for row in body} == {"mcp"}
    db_session.expire_all()
    stored = {
        row.prompt: row.answer
        for row in db_session.scalars(select(QAEntry).where(QAEntry.application_id == application.id))
    }
    assert stored == {
        "Why us?": "Because of the team, and the data.",
        "Other?": "kept",
        "notice period?": "Two weeks",
    }


def test_an_answer_with_no_text_left_stores_nothing(db_session, client):
    application = _application(db_session)
    response = client.post(
        "/api/qa/answers",
        json={
            "application_id": str(application.id),
            "answers": [
                {"question": "Why us?", "answer": "Because."},
                {"question": "Anything else?", "answer": "---"},
            ],
        },
    )
    assert response.status_code == 400
    assert "Anything else?" in response.json()["detail"]
    db_session.expire_all()
    assert db_session.scalars(select(QAEntry)).all() == []


def test_answers_for_no_application_are_a_404(db_session, client):
    response = client.post(
        "/api/qa/answers",
        json={
            "application_id": "00000000-0000-4000-8000-000000000000",
            "answers": [{"question": "Why us?", "answer": "Because."}],
        },
    )
    assert response.status_code == 404
