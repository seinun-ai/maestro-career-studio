"""Server-written words the web app and the Companion show (appendix D §9.5–§9.6).

Each helper here decides what a user reads when the server writes the sentence
itself: a file it could not read, a resume named in a version summary or a
Career history timeline row. The words live in one place each; these pins keep
the raw error text, slugs and ids off the screen.
"""
import re
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


# ---------- every server sentence the web app shows passes its own rule ----------
#
# The web app shows a thrown message only when `isPlainSentence`
# (frontend/lib/error-text.ts) passes it; anything else is replaced by "Try
# again." So a sentence rewritten for users that fails the rule is a sentence
# nobody reads. `_is_plain_sentence` is the rule ported; the parity test runs
# the TypeScript itself over the same cases (tests/node_ts.py).

_PLAIN = re.compile(r"^[A-Z][^{}\[\]<>_`|\\]*[.!?]$")


def _is_plain_sentence(text: str) -> bool:
    t = text.strip()
    return 0 < len(t) <= 240 and bool(_PLAIN.match(t))


_RULE_CASES = [
    "Couldn't read this file. Try again.",
    "john_doe_resume.json isn't a resume in the Maestro CS JSON format.",
    "gpt-4o is your Fast, Smart or Assistant model. Pick another model for that first.",
    "The AI model didn't answer (error 429: insufficient_quota). Try again.",
    "The model qwen2.5:7b can't use tools. Pick a different model in Settings › AI & models.",
    "Unknown gate id: S9",
    "x" * 250 + ".",
    "",
    "Line one {json}.",
]


def test_the_ported_rule_is_the_web_apps():
    from tests.node_ts import ts_map

    assert [_is_plain_sentence(c) for c in _RULE_CASES] == ts_map(
        "./lib/error-text.ts", "isPlainSentence", _RULE_CASES)


def _provider_messages() -> list[str]:
    import openai

    from app.services import llm

    class _Status(openai.APIStatusError):
        def __init__(self, status, code):  # no response needed for the reason
            self.status_code, self.code = status, code

    reasons = [llm._openai_reason(_Status(s, c)) for s, c in [
        (401, "invalid_api_key"), (429, "insufficient_quota"), (404, "model_not_found"),
        (429, "rate_limit_exceeded"), (500, None), (403, "unsupported_country")]]
    reasons += [llm._openai_reason(openai.APIConnectionError(request=None)),
                llm._status_reason(429), llm._status_reason(503)]
    return [str(llm._no_answer(r, "detail")) for r in reasons] + [
        llm.NO_KEY_MESSAGE, llm.NO_GEMINI_KEY_MESSAGE]


def _model_messages(db_session) -> list[str]:
    from app.services import llm_capabilities, model_settings

    out = []
    for model in ("qwen2.5:7b", "gpt-4o-mini"):
        llm_capabilities.save(db_session, llm_capabilities.CapabilityReport(
            model=model, text=False, json=False, tools=False,
            errors={"tools": "The AI model didn't answer (error 404: model_not_found)."}))
        for capability in ("text", "json", "tools"):
            try:
                llm_capabilities.require(db_session, model, capability)
            except llm_capabilities.CapabilityMissing as exc:
                out.append(str(exc))
    model_settings.add_extra_model(db_session, "gpt-custom", "openai")
    model_settings.set_models("gpt-custom", "gpt-5.6-luna", db_session)
    try:
        model_settings.remove_extra_model(db_session, "gpt-custom")
    except ValueError as exc:
        out.append(str(exc))
    else:
        raise AssertionError("a model in use must not be removable")
    return out


def _file_messages() -> list[str]:
    from app.services import kb_import
    from app.services.attachment_extract import (
        NO_TEXT,
        NOT_AN_IMAGE,
        UPLOAD_UNREADABLE,
        UnreadableFile,
    )

    out = [NOT_AN_IMAGE, NO_TEXT, UPLOAD_UNREADABLE, kb_import.NOT_RESUME_JSON]
    for name, blob in [("my_cv.png", b"not an image"), ("empty_notes.txt", b"   ")]:
        try:
            extract_text(name, None, blob)
        except UnreadableFile as exc:
            out.append(str(exc))
    try:
        kb_import.parse_resume_json(b"{not json")
    except UnreadableFile as exc:
        out.append(str(exc))
    return out


def _health_and_score_messages() -> list[str]:
    from app.services import pdf_render, proposals
    from app.services.ats import layers
    from app.services.ats.engine import _coverage_message
    from app.services.tailoring_session import _must_fix_message

    dated = SimpleNamespace(section="experience", date_parse_ok=True)
    out = [layers._years_warning(5, SimpleNamespace(entries=[dated], total_experience_years=y))
           for y in (4.6, 0.4, 0.0, 2.2)]
    out += [_coverage_message(m, n) for m, n in [(0, 8), (1, 8), (0, 1), (0, 0)]]
    out += [pdf_render.TEX_MISSING_NO_TYPST, pdf_render.tex_fallback_note("Classic", "Modern")]
    out += [_must_fix_message([{"id": "S1"}]), _must_fix_message([{"id": "S1"}, {"id": "S2"}])]
    out += [f"This proposal's status is {word}, so it can't be changed that way."
            for word in proposals.STATUS_CHIP_WORDS.values()]
    return out


def test_every_rewritten_server_sentence_passes_the_web_apps_rule(db_session):
    messages = (_provider_messages() + _model_messages(db_session) + _file_messages()
                + _health_and_score_messages())
    hidden = [m for m in messages if not _is_plain_sentence(m)]
    assert hidden == []
    # None names a file: the dialogs print the name beside the reason.
    assert not [m for m in messages if re.search(r"\w\.(pdf|png|json|txt|docx)\b", m)]


def test_a_refused_proposal_move_reads_as_a_sentence(db_session):
    """The real refusal, not a copy of its f-string."""
    from app.services import proposals

    prop = SimpleNamespace(status="needs_human")
    try:
        proposals.transition(db_session, prop, "submitted")
    except proposals.TransitionError as exc:
        assert str(exc) == "This proposal's status is Needs you, so it can't be changed that way."
        assert _is_plain_sentence(str(exc))
    else:
        raise AssertionError("needs_human cannot go straight to submitted")


def test_a_missing_model_capability_keeps_its_own_sentence():
    from app.services.llm_capabilities import CapabilityMissing

    exc = CapabilityMissing("The model qwen2.5:7b can't use tools. Pick a different model.")
    assert plain_read_error(exc) == str(exc)


def test_a_role_slug_is_named_by_its_role():
    """A base resume with no display name whose slug is a role key reads as the
    role's own label, never the title-cased slug ("Ai Ml Engineer")."""
    from unittest.mock import patch

    from app.services import base_resume_data

    with patch.object(base_resume_data, "display_name_of", return_value=None):
        assert resume_label(None, "ai_ml_engineer") == "AI/ML Engineer"
        assert resume_label(None, "llmops_engineer") == "LLMOps Engineer"
        assert resume_label(None, "my-custom_resume") == "My Custom Resume"
