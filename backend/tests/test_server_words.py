"""Server-written words the web app and the Companion show (appendix D §9.5–§9.6).

Each helper here decides what a user reads when the server writes the sentence
itself: a file it could not read, a resume named in a version summary or a
Career history timeline row. The words live in one place each; these pins keep
the raw error text, slugs and ids off the screen.
"""
from datetime import UTC, datetime
from types import SimpleNamespace

from app.services import career_kb
from app.services.attachment_extract import UnreadableFile, extract_text, plain_read_error
from app.services.base_resume_data import resume_label
from app.services.llm import LLMProviderError
from app.services.script_guard import UnsupportedScriptError, validate_script


def test_a_file_that_cannot_be_read_says_so_in_words():
    assert plain_read_error(UnreadableFile("This file is over 10 MB.")) == "This file is over 10 MB."
    assert plain_read_error(LLMProviderError("The AI model didn't answer (no connection).")) == (
        "The AI model didn't answer (no connection).")
    # Anything else is text for a developer: a pydantic error, a JSON offset.
    assert plain_read_error(ValueError("Expecting value: line 1 column 1 (char 0)")) == (
        "Couldn't read this file.")
    try:
        extract_text("notes.xyz", "application/x-thing", b"data")
    except UnreadableFile as exc:
        assert plain_read_error(exc) == "Use a PDF, Word, text or image file."
    else:
        raise AssertionError("an unknown type must be refused")


def test_an_unsupported_script_keeps_its_own_sentence():
    try:
        validate_script("Резюме разработчика программного обеспечения. Опыт работы 5 лет в IT.",
                        source_label="resume")
    except UnsupportedScriptError as exc:
        assert str(exc) == (
            "This resume uses Cyrillic script. Maestro CS supports English in Latin "
            "script (accented Latin letters, such as in Zürich, work).")
        assert plain_read_error(exc) == str(exc)
    else:
        raise AssertionError("Cyrillic must be refused")


def test_a_resume_is_named_by_its_display_name_never_its_slug(db_session):
    from app.models.base_resume import BaseResume

    db_session.add(BaseResume(slug="ai_ml_engineer", display_name="AI/ML Engineer", data_json={}))
    db_session.add(BaseResume(slug="data_scientist", display_name=None, data_json={}))
    db_session.flush()
    assert resume_label(db_session, "ai_ml_engineer") == "AI/ML Engineer"
    assert resume_label(db_session, "data_scientist") == "Data Scientist"
    assert resume_label(db_session, "gone-resume") == "Gone Resume"


def test_the_timeline_names_who_and_where_in_words():
    now = datetime.now(UTC)
    entity = SimpleNamespace(created_at=now, origin="chat", origin_detail=None)
    point = SimpleNamespace(created_at=now, origin="mcp", origin_detail="claude-ai",
                            text="Cut costs by 30%.", approved_at=None)
    logs = [SimpleNamespace(ported_at=now, resume_key="ds", resume_kind="base"),
            SimpleNamespace(ported_at=now, resume_key="3f2c", resume_kind="application")]
    labels = [ev.label for ev in career_kb.entity_timeline(
        entity, [point], [], logs, {"ds": "Data Scientist", "3f2c": "a tailored resume"})]
    assert "Item created by the Assistant" in labels
    assert "Added by Claude: Cut costs by 30%." in labels
    assert "Added to Data Scientist" in labels
    assert "Added to a tailored resume" in labels
    # A key the caller could not name is never printed.
    unnamed = career_kb.entity_timeline(entity, [], [], logs[:1])
    assert [ev.label for ev in unnamed if ev.type == "ported"] == ["Added to a resume"]
