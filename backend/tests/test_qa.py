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


def test_job_answers_are_written_from_the_base_the_caller_names(db_session, monkeypatch):
    """`base` is threaded to the READ, which is the whole of the fix.

    The job path used to hardcode the generic "hybrid" resume, so a job-level
    answer was written from a document the caller never picked — and the side
    panel's own sentence about it ("Answered from your base resume and this
    posting") was false. A named slug goes through `load_base_resume`, so the
    base_resumes table gate applies exactly as it does everywhere else.
    """
    application = _application(db_session)
    _patch_context(monkeypatch)
    monkeypatch.setattr(
        qa.prompt_assembly,
        "build_qa_prompt",
        lambda resume_json, jd_json, memory, questions, persona="": f"qa {resume_json}",
    )
    read = {}

    def fake_load(slug, session=None):
        read["gated"] = slug
        return {"summary": "Picked"}

    monkeypatch.setattr(qa.base_resume_data, "load_base_resume", fake_load)
    # The DEFAULT read must not happen at all when a slug was named — a fallback
    # that still fired would ground the answer on the resume this fixes away.
    monkeypatch.setattr(
        qa.base_resume_data, "_read_base_resume_data",
        lambda slug: pytest.fail(f"the default {slug} resume was read anyway"))
    captured = {}

    def fake_call(**kwargs):
        captured["prompt"] = kwargs.get("prompt")
        return "1. Yes."

    monkeypatch.setattr(qa.llm, "call_openai", fake_call)

    answers = qa.answer_questions_for_job(
        application.job_id, ["Can you work hybrid?"], db_session, "data_scientist")

    assert answers == ["Yes."]
    assert read["gated"] == "data_scientist"
    assert "Picked" in captured["prompt"]


def test_a_job_answer_with_no_base_named_still_uses_the_default(db_session, monkeypatch):
    """The absent-`base` path is unchanged behaviour, pinned because the fix
    could have moved it: every caller that never sends a slug — the web app, an
    agent over MCP — keeps the generic default it has always had."""
    application = _application(db_session)
    _patch_context(monkeypatch)
    monkeypatch.setattr(
        qa.prompt_assembly,
        "build_qa_prompt",
        lambda resume_json, jd_json, memory, questions, persona="": "qa prompt",
    )
    read = {}

    def fake_default(slug):
        read["slug"] = slug
        return {"summary": "Hybrid"}

    monkeypatch.setattr(qa.base_resume_data, "_read_base_resume_data", fake_default)
    monkeypatch.setattr(qa.llm, "call_openai", lambda **kwargs: "1. Yes.")

    assert qa.answer_questions_for_job(
        application.job_id, ["Can you work hybrid?"], db_session) == ["Yes."]
    assert read["slug"] == qa.DEFAULT_JOB_RESUME_SLUG


def test_a_resume_that_cannot_be_read_is_a_caller_error_and_never_a_crash(db_session):
    """BOTH reads can fail on an ordinary install, and neither may be a 500.

    The default is the likelier one: this repo ships a single example base
    resume, so `hybrid.json` need not exist at all — and the disk read behind it
    bypasses the table gate, which is why nothing else was catching it. The
    named slug fails through `load_base_resume`'s own ValueError. Both arrive as
    `BaseResumeUnavailable`, and the message names the slug and never the path.
    """
    application = _application(db_session)
    with pytest.raises(qa.BaseResumeUnavailable) as missing_default:
        qa.context_from_job(db_session, application.job_id)
    assert qa.DEFAULT_JOB_RESUME_SLUG in str(missing_default.value)
    assert "/" not in str(missing_default.value)

    with pytest.raises(qa.BaseResumeUnavailable) as unknown_slug:
        qa.context_from_job(db_session, application.job_id, "no_such_resume")
    assert "no_such_resume" in str(unknown_slug.value)

    # A ValueError either way, so a caller that only knows the old contract
    # still fails loudly rather than silently answering from nothing.
    assert issubclass(qa.BaseResumeUnavailable, ValueError)


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


def test_scrub_typographic_dashes_turns_clause_dashes_into_commas():
    # Spaced em/en dashes are clause breaks, not ranges.
    assert (
        qa.scrub_typographic_dashes("I shipped the model — then we scaled it.")
        == "I shipped the model, then we scaled it."
    )
    assert (
        qa.scrub_typographic_dashes("I shipped the model – then we scaled it.")
        == "I shipped the model, then we scaled it."
    )


def test_scrub_typographic_dashes_turns_range_dashes_into_hyphens():
    assert qa.scrub_typographic_dashes("2020–2023") == "2020-2023"
    assert qa.scrub_typographic_dashes("client—server") == "client-server"


def test_scrub_typographic_dashes_is_idempotent_on_ascii():
    plain = "I shipped the model, then we scaled it in 2020-2023."
    assert qa.scrub_typographic_dashes(plain) == plain
    dashed = "Shipped — 2020–2023"
    once = qa.scrub_typographic_dashes(dashed)
    assert qa.scrub_typographic_dashes(once) == once
    assert "—" not in once and "–" not in once


def test_plain_text_scrubs_typographic_dashes():
    assert (
        qa._plain_text("I use SQL — daily, years 2020–2023.")
        == "I use SQL, daily, years 2020-2023."
    )


def test_generate_cover_letter_scrubs_dashes_before_store(db_session, monkeypatch):
    application = _application(db_session)
    _patch_context(monkeypatch)
    monkeypatch.setattr(
        qa.prompt_assembly,
        "build_cover_letter_prompt",
        lambda resume_json, jd_json, memory, tone, persona="": f"cover prompt {tone}",
    )
    monkeypatch.setattr(
        qa.llm,
        "call_openai",
        lambda **kwargs: "I led the team — then we shipped 2020–2023.",
    )

    result = qa.generate_cover_letter(application.id, "balanced", db_session)

    assert result == "I led the team, then we shipped 2020-2023."
    assert db_session.query(QAEntry).one().answer == result
    assert "—" not in result and "–" not in result


def test_regenerate_cover_letter_scrubs_dashes(db_session, monkeypatch):
    application = _application(db_session)
    entry = QAEntry(
        application_id=application.id,
        kind="cover_letter",
        prompt=None,
        answer="old letter",
    )
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)
    _patch_context(monkeypatch)
    monkeypatch.setattr(
        qa.prompt_assembly,
        "build_cover_letter_prompt",
        lambda resume_json, jd_json, memory, tone, persona="": "cover prompt",
    )
    monkeypatch.setattr(
        qa.llm,
        "call_openai",
        lambda **kwargs: "Excited to join — years 2019–2021.",
    )

    updated = qa.regenerate_entry(entry.id, tone="formal", session=db_session)

    assert updated.answer == "Excited to join, years 2019-2021."
    assert "—" not in updated.answer and "–" not in updated.answer


def test_job_only_cover_letter_scrubs_dashes(db_session, monkeypatch):
    application = _application(db_session)
    _patch_context(monkeypatch)
    monkeypatch.setattr(
        qa.prompt_assembly,
        "build_cover_letter_prompt",
        lambda resume_json, jd_json, memory, tone, persona="": "cover prompt",
    )
    monkeypatch.setattr(
        qa.base_resume_data, "_read_base_resume_data", lambda slug: {"summary": "Hybrid"}
    )
    monkeypatch.setattr(
        qa.llm,
        "call_openai",
        lambda **kwargs: "I built the pipeline — 2021–2024.",
    )

    result = qa.generate_cover_letter_for_job(
        application.job_id, "balanced", db_session
    )

    assert result == "I built the pipeline, 2021-2024."
    assert "—" not in result and "–" not in result
