import re
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.application import Application
from app.models.job import Job
from app.models.qa_entry import QAEntry
from app.models.referral import Referral
from app.services import (
    base_resume_data,
    career_kb,
    llm,
    model_settings,
    persona,
    prompt_assembly,
)


class UnsupportedQAEntryKind(ValueError):
    """Regenerate was requested for a QA entry whose kind cannot be regenerated
    (e.g. a retired ``cold_message``). Subclasses ValueError so the fail-loud
    intent stands, but lets the router map it to a 400 (the entry exists; the
    operation just doesn't apply to it) while genuine not-found stays a 404."""


def _application_context(
    session: Session, application_id: UUID
) -> tuple[Application, Job, dict[str, Any]]:
    application = session.get(Application, application_id)
    if application is None:
        raise ValueError(f"Application not found: {application_id}")

    job = session.get(Job, application.job_id)
    if job is None or not job.extracted_json:
        raise ValueError(f"Application has no extracted job data: {application_id}")

    resume_json = application.customized_json or base_resume_data.load_base_resume(
        application.base_resume, session
    )
    return application, job, resume_json


def context_from_job(session: Session, job_id: UUID) -> tuple[Job, dict[str, Any]]:
    job = session.get(Job, job_id)
    if job is None or not job.extracted_json:
        raise ValueError(f"Job not found or missing extracted data: {job_id}")
    # Job-level QA/cover-letter uses the generic "hybrid" resume as a default.
    # `hybrid` is not a tailorable/scoreable base (no base_resumes row), so it
    # bypasses the table gate and reads its disk data directly.
    return job, base_resume_data._read_base_resume_data("hybrid")


def _referral_context(session: Session, application: Application) -> dict[str, Any] | None:
    if application.referral_id is None:
        return None
    referral = session.get(Referral, application.referral_id)
    if referral is None:
        return None
    return {
        "company": referral.company,
        "contact_name": referral.contact_name,
        "notes": referral.notes,
    }


def _split_numbered_answers(text: str, expected: int) -> list[str]:
    parts = [
        part.strip()
        for part in re.split(r"(?:^|\n)\s*\d+[\).\s-]+", text)
        if part.strip()
    ]
    if len(parts) == expected:
        return parts
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines if len(lines) == expected else [text.strip()]


_HR_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_HEADING_RE = re.compile(r"^\s*#{1,6}\s+")
_BULLET_RE = re.compile(r"^(\s*)[-*•]\s+")


def _plain_text(text: str) -> str:
    """Normalize an LLM answer to form-field-safe plain text: strip markdown
    bold/heading/backtick syntax, leading bullet markers, and horizontal rules;
    collapse 3+ newlines to a blank line; PRESERVE genuine line breaks.
    Idempotent — safe to run over already-plain stored answers.

    Deliberately does NOT strip __double-underscore__ emphasis: LLM bold is **,
    __ emphasis is rare, and stripping it corrupts dunder identifiers like
    __init__ / __repr__ in technical answers (fix B4)."""
    lines = []
    for line in text.splitlines():
        if _HR_RE.match(line):
            continue
        line = _HEADING_RE.sub("", line)
        line = _BULLET_RE.sub(r"\1", line)
        lines.append(line)
    out = "\n".join(lines)
    out = re.sub(r"\*\*(.+?)\*\*", r"\1", out, flags=re.DOTALL)
    out = out.replace("`", "")
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def answer_questions(
    application_id: UUID,
    questions: list[str],
    session: Session | None = None,
) -> list[str]:
    owns_session = session is None
    session = session or SessionLocal()
    try:
        application, job, resume_json = _application_context(session, application_id)
        prompt = prompt_assembly.build_qa_prompt(
            resume_json=resume_json,
            jd_json=job.extracted_json or {},
            memory=career_kb.compose_context(session),
            questions=questions,
            persona=persona.get_persona(session),
            referral=_referral_context(session, application),
        )
        model = model_settings.get_smart_model(session)
        response = llm.call_openai(
            prompt=prompt,
            model=model,
            response_format="text",
            trace_name="qa-answer",
        )
        answers = [
            _plain_text(answer)
            for answer in _split_numbered_answers(str(response), len(questions))
        ]
        if len(answers) == len(questions):
            for question, answer in zip(questions, answers, strict=True):
                session.add(
                    QAEntry(
                        application_id=application_id,
                        kind="question",
                        prompt=question,
                        answer=answer,
                        model_used=model,
                    )
                )
        else:
            session.add(
                QAEntry(
                    application_id=application_id,
                    kind="question",
                    prompt="\n".join(questions),
                    answer=_plain_text(str(response)),
                    model_used=model,
                )
            )
        session.commit()
        return answers
    finally:
        if owns_session:
            session.close()


def generate_cover_letter(
    application_id: UUID,
    tone: str = "balanced",
    session: Session | None = None,
) -> str:
    owns_session = session is None
    session = session or SessionLocal()
    try:
        _application, job, resume_json = _application_context(session, application_id)
        prompt = prompt_assembly.build_cover_letter_prompt(
            resume_json=resume_json,
            jd_json=job.extracted_json or {},
            memory=career_kb.compose_context(session),
            tone=tone,
            persona=persona.get_persona(session),
        )
        model = model_settings.get_smart_model(session)
        response = str(
            llm.call_openai(
                prompt=prompt,
                model=model,
                response_format="text",
                trace_name="cover-letter",
            )
        )
        session.add(
            QAEntry(
                application_id=application_id,
                kind="cover_letter",
                prompt=None,
                answer=response,
                model_used=model,
            )
        )
        session.commit()
        return response
    finally:
        if owns_session:
            session.close()


def answer_questions_for_job(
    job_id: UUID,
    questions: list[str],
    session: Session,
) -> list[str]:
    job, resume_json = context_from_job(session, job_id)
    prompt = prompt_assembly.build_qa_prompt(
        resume_json=resume_json,
        jd_json=job.extracted_json or {},
        memory=career_kb.compose_context(session),
        questions=questions,
        persona=persona.get_persona(session),
    )
    response = llm.call_openai(
        prompt=prompt,
        model=model_settings.get_smart_model(session),
        response_format="text",
        trace_name="qa-answer",
    )
    return [
        _plain_text(answer)
        for answer in _split_numbered_answers(str(response), len(questions))
    ]


def regenerate_entry(
    entry_id: UUID,
    tone: str | None = None,
    session: Session | None = None,
) -> QAEntry:
    owns_session = session is None
    session = session or SessionLocal()
    try:
        entry = session.get(QAEntry, entry_id)
        if entry is None:
            raise ValueError(f"QA entry not found: {entry_id}")

        application, job, resume_json = _application_context(session, entry.application_id)
        if entry.kind == "cover_letter":
            prompt = prompt_assembly.build_cover_letter_prompt(
                resume_json=resume_json,
                jd_json=job.extracted_json or {},
                memory=career_kb.compose_context(session),
                tone=tone or "balanced",
                persona=persona.get_persona(session),
            )
        elif entry.kind == "question":
            if not entry.prompt:
                raise ValueError("QA entry has no prompt to regenerate from")
            prompt = prompt_assembly.build_qa_prompt(
                resume_json=resume_json,
                jd_json=job.extracted_json or {},
                memory=career_kb.compose_context(session),
                questions=[entry.prompt],
                persona=persona.get_persona(session),
                referral=_referral_context(session, application),
            )
        else:
            # Fail loud on retired/unknown kinds (cold_message removed 2026-07-21;
            # the dev DB held zero rows, so no data migration). Distinct subclass
            # so the router answers 400, not 404 or 500.
            raise UnsupportedQAEntryKind(f"Unsupported QA entry kind: {entry.kind}")

        model = model_settings.get_smart_model(session)
        response = str(
            llm.call_openai(
                prompt=prompt,
                model=model,
                response_format="text",
                trace_name="qa-regenerate",
            )
        )
        if entry.kind == "question":
            answers = _split_numbered_answers(response, expected=1)
            response = answers[0] if answers else response
            response = _plain_text(response)

        entry.answer = response
        if entry.pdf_path:
            from app.services import artifacts

            artifacts.cleanup_qa_entry_files(entry)
            entry.pdf_path = None
        entry.model_used = model
        session.commit()
        session.refresh(entry)
        return entry
    finally:
        if owns_session:
            session.close()


def generate_cover_letter_for_job(job_id: UUID, tone: str, session: Session) -> str:
    job, resume_json = context_from_job(session, job_id)
    prompt = prompt_assembly.build_cover_letter_prompt(
        resume_json=resume_json,
        jd_json=job.extracted_json or {},
        memory=career_kb.compose_context(session),
        tone=tone,
        persona=persona.get_persona(session),
    )
    return str(
        llm.call_openai(
            prompt=prompt,
            model=model_settings.get_smart_model(session),
            response_format="text",
            trace_name="cover-letter",
        )
    )
