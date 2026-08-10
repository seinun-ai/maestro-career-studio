from datetime import UTC, datetime

import pytest

from app.models.application import Application
from app.models.job import Job
from app.models.qa_entry import QAEntry
from app.models.referral import Referral
from app.services import qa


def _application(db_session):
    job = Job(
        raw_text="Need analytics",
        raw_text_hash="qa-hash",
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
        customized_json={"summary": "Analyst", "contact": {"name": "Sample", "email": "x@y.com"}},
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)
    return application


def _patch_context(monkeypatch):
    monkeypatch.setattr(qa.career_kb, "compose_context", lambda session=None: "memory")
    monkeypatch.setattr(qa.persona, "get_persona", lambda session=None: "persona")


def test_answer_questions_persists_entries(db_session, monkeypatch):
    application = _application(db_session)
    _patch_context(monkeypatch)
    monkeypatch.setattr(
        qa.prompt_assembly,
        "build_qa_prompt",
        lambda resume_json, jd_json, memory, questions, persona="", referral=None: "qa prompt",
    )
    monkeypatch.setattr(
        qa.llm,
        "call_openai",
        lambda **kwargs: "1. I use SQL daily.\n2. I build dashboards.",
    )

    answers = qa.answer_questions(
        application.id,
        ["Tell me about SQL.", "Tell me about dashboards."],
        db_session,
    )

    assert answers == ["I use SQL daily.", "I build dashboards."]
    entries = db_session.query(QAEntry).order_by(QAEntry.created_at).all()
    assert len(entries) == 2
    assert entries[0].kind == "question"
    assert entries[0].prompt == "Tell me about SQL."


def test_answer_questions_numbered_reply_splits_to_matching_answers(db_session, monkeypatch):
    # Pipeline coherence for the reworded QA output contract (fix B1): a numbered
    # multi-question reply must split into one answer per question, not collapse
    # into a single blob.
    application = _application(db_session)
    _patch_context(monkeypatch)
    monkeypatch.setattr(
        qa.prompt_assembly,
        "build_qa_prompt",
        lambda resume_json, jd_json, memory, questions, persona="", referral=None: "qa prompt",
    )
    monkeypatch.setattr(
        qa.llm,
        "call_openai",
        lambda **kwargs: "1. Yes, remote works.\n2. Two weeks notice.",
    )

    answers = qa.answer_questions(
        application.id,
        ["Are you open to remote?", "What is your notice period?"],
        db_session,
    )

    assert answers == ["Yes, remote works.", "Two weeks notice."]
    assert db_session.query(QAEntry).count() == 2


def test_unsplittable_reply_returns_one_answer_not_one_per_question(
    db_session, monkeypatch
):
    """`answer_questions` does NOT promise one answer per question.

    When the model's reply carries no numbering and no per-question line
    structure, `_split_numbered_answers` falls back to `[text.strip()]` — a
    ONE-element list — regardless of how many questions were asked.

    So any consumer MUST length-check before zipping answers onto questions by
    index. `questions[i] -> answers[i]` over a 1-element list writes the entire
    combined reply into the FIRST field and silently reports the other N-1 as
    unanswered, which is a data-corruption bug at the form, not a display one.
    The extension's ai-fill guard exists because of this return value; this test
    is what keeps the guard necessary rather than cargo.

    Nothing is lost by refusing to fill: the merged reply is still persisted, as
    a single entry keyed by the joined prompts, so it is recoverable from the
    application's Q&A history.
    """
    application = _application(db_session)
    _patch_context(monkeypatch)
    monkeypatch.setattr(
        qa.prompt_assembly,
        "build_qa_prompt",
        lambda resume_json, jd_json, memory, questions, persona="", referral=None: "qa prompt",
    )
    blob = (
        "I have shipped production forecasting models for six years, "
        "I am available on two weeks' notice, and I am happy to work hybrid."
    )
    monkeypatch.setattr(qa.llm, "call_openai", lambda **kwargs: blob)

    questions = [
        "Tell me about your experience.",
        "What is your notice period?",
        "Are you open to hybrid?",
    ]
    answers = qa.answer_questions(application.id, questions, db_session)

    assert len(answers) == 1
    assert answers[0] == blob
    entry = db_session.query(QAEntry).one()
    assert entry.prompt == "\n".join(questions)
    assert entry.answer == blob


def test_empty_reply_also_returns_one_answer_but_a_blank_one(db_session, monkeypatch):
    """The 1-element fallback covers TWO different failures, and they differ.

    `_split_numbered_answers` returns `[text.strip()]` whatever the text is, so
    a model that answers nothing yields `[""]` — length 1, exactly like the
    unsplittable-prose case above. A consumer that only length-checks cannot
    tell "it answered, we cannot map the answer" from "it answered nothing".

    The distinction is not cosmetic: the extension reports the first as
    `ai_unaligned` (neutral — the fill path declined) and the second as
    `ai_unanswered` (a failure outcome, and honestly so). Blaming the fill path
    for a model that returned nothing, or excusing it when the model did
    answer, both corrupt the coverage card. Raw blankness is the discriminator,
    so this test pins that a blank reply survives as a blank answer rather than
    being dropped or coerced.
    """
    application = _application(db_session)
    _patch_context(monkeypatch)
    monkeypatch.setattr(
        qa.prompt_assembly,
        "build_qa_prompt",
        lambda resume_json, jd_json, memory, questions, persona="", referral=None: "qa prompt",
    )
    monkeypatch.setattr(qa.llm, "call_openai", lambda **kwargs: "   \n  ")

    answers = qa.answer_questions(
        application.id,
        ["Why us?", "Why now?", "Why this team?"],
        db_session,
    )

    assert answers == [""]
    assert not answers[0].strip()


def test_generate_cover_letter_persists_entry(db_session, monkeypatch):
    application = _application(db_session)
    _patch_context(monkeypatch)
    monkeypatch.setattr(
        qa.prompt_assembly,
        "build_cover_letter_prompt",
        lambda resume_json, jd_json, memory, tone, persona="": f"cover prompt {tone}",
    )
    monkeypatch.setattr(qa.llm, "call_openai", lambda **kwargs: "Dear Acme...")

    result = qa.generate_cover_letter(application.id, "formal", db_session)

    assert result == "Dear Acme..."
    entry = db_session.query(QAEntry).one()
    assert entry.kind == "cover_letter"
    assert entry.prompt is None
    assert entry.answer == "Dear Acme..."


def test_qa_answer_uses_composed_context(db_session, monkeypatch):
    # Proves the swap: qa feeds career_kb.compose_context (not memory) into the
    # QA prompt. No build_qa_prompt monkeypatch — the real template renders the
    # composed context, and we assert the sentinel survives into the prompt.
    application = _application(db_session)
    monkeypatch.setattr(qa.career_kb, "compose_context", lambda session=None: "SENTINEL_CTX_7")
    monkeypatch.setattr(qa.persona, "get_persona", lambda session=None: "persona")
    captured = {}

    def fake_call(**kwargs):
        captured["prompt"] = kwargs.get("prompt")
        return "1. answer"

    monkeypatch.setattr(qa.llm, "call_openai", fake_call)

    qa.answer_questions(application.id, ["Tell me about SQL."], db_session)

    assert "SENTINEL_CTX_7" in captured["prompt"]


def test_job_only_question_generation_does_not_persist(db_session, monkeypatch):
    application = _application(db_session)
    _patch_context(monkeypatch)
    monkeypatch.setattr(
        qa.prompt_assembly,
        "build_qa_prompt",
        lambda resume_json, jd_json, memory, questions, persona="": "qa prompt",
    )
    # Job-level QA uses the generic "hybrid" resume, which bypasses the table
    # gate and reads disk directly via _read_base_resume_data.
    monkeypatch.setattr(qa.base_resume_data, "_read_base_resume_data", lambda slug: {"summary": "Hybrid"})
    monkeypatch.setattr(qa.llm, "call_openai", lambda **kwargs: "1. Yes.")

    answers = qa.answer_questions_for_job(
        application.job_id,
        ["Can you work hybrid?"],
        db_session,
    )

    assert answers == ["Yes."]
    assert db_session.query(QAEntry).count() == 0


def test_answer_questions_passes_referral_context(db_session, monkeypatch):
    application = _application(db_session)
    referral = Referral(
        company="Acme", careers_url="https://acme.example/careers", contact_name="Sam Lee"
    )
    db_session.add(referral)
    db_session.flush()
    application.referral_id = referral.id
    db_session.commit()

    _patch_context(monkeypatch)
    seen = {}

    def fake_build(**kwargs):
        seen.update(kwargs)
        return "qa prompt"

    monkeypatch.setattr(qa.prompt_assembly, "build_qa_prompt", fake_build)
    monkeypatch.setattr(qa.llm, "call_openai", lambda **kwargs: "1. Sure.")

    qa.answer_questions(
        application.id, ["Write a short LinkedIn DM to my contact."], db_session
    )

    assert seen["referral"]["company"] == "Acme"
    assert seen["referral"]["contact_name"] == "Sam Lee"


def test_regenerate_unknown_kind_raises(db_session):
    application = _application(db_session)
    entry = QAEntry(
        application_id=application.id,
        kind="cold_message",  # any retired/unknown kind
        prompt="Keep it under 100 words",
        answer="old",
    )
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)

    with pytest.raises(ValueError, match="Unsupported QA entry kind"):
        qa.regenerate_entry(entry.id, session=db_session)


MARKDOWN_ANSWER = (
    "## Message to Hiring Team\n\n"
    "**I am** a `data scientist` with **production** experience.\n\n\n\n"
    "- Shipped forecasting models\n"
    "* Reduced costs 20%\n"
    "• Led a team of 3\n"
    "---\n"
    "Second paragraph stays separate."
)
PLAIN_ANSWER = (
    "Message to Hiring Team\n\n"
    "I am a data scientist with production experience.\n\n"
    "Shipped forecasting models\n"
    "Reduced costs 20%\n"
    "Led a team of 3\n"
    "Second paragraph stays separate."
)


def test_plain_text_strips_markdown_preserving_line_breaks():
    assert qa._plain_text(MARKDOWN_ANSWER) == PLAIN_ANSWER


def test_plain_text_is_idempotent_and_noop_on_plain_text():
    once = qa._plain_text(MARKDOWN_ANSWER)
    assert qa._plain_text(once) == once
    plain = "I use SQL daily.\nI build dashboards for execs."
    assert qa._plain_text(plain) == plain


def test_plain_text_preserves_double_underscore_identifiers():
    # Dunder identifiers in technical answers must survive intact: the old
    # __(.+?)__ emphasis rule corrupted "__init__" -> "init" (fix B4).
    text = "Override __init__ and __repr__ in the class."
    assert qa._plain_text(text) == text


def test_plain_text_still_strips_bold_and_is_idempotent_on_dunders():
    assert qa._plain_text("This is **bold** text.") == "This is bold text."
    dunder = "Define __init__, __repr__, and __eq__."
    assert qa._plain_text(qa._plain_text(dunder)) == dunder


def test_answer_questions_persists_normalized_plain_text(db_session, monkeypatch):
    application = _application(db_session)
    _patch_context(monkeypatch)
    monkeypatch.setattr(
        qa.prompt_assembly,
        "build_qa_prompt",
        lambda resume_json, jd_json, memory, questions, persona="", referral=None: "qa prompt",
    )
    monkeypatch.setattr(
        qa.llm,
        "call_openai",
        lambda **kwargs: "1. **I use SQL** daily.\n2. - I build `dashboards`.",
    )

    answers = qa.answer_questions(
        application.id,
        ["Tell me about SQL.", "Tell me about dashboards."],
        db_session,
    )

    assert answers == ["I use SQL daily.", "I build dashboards."]
    stored = {e.prompt: e.answer for e in db_session.query(QAEntry).all()}
    assert stored["Tell me about SQL."] == "I use SQL daily."
    assert stored["Tell me about dashboards."] == "I build dashboards."
