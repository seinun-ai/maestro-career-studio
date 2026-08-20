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


class BaseResumeUnavailable(ValueError):
    """A job-level answer was asked for and the resume to write it FROM could
    not be read — an unknown slug, or a slug whose data file is not on disk.

    Subclasses ValueError so the fail-loud intent stands, and exists so the
    router can map it to a 400 (the caller named something we do not have, or
    the install is missing its default resume data) rather than letting a
    FileNotFoundError out as a 500. `UnsupportedQAEntryKind` below is the same
    pattern for the same reason; where a handler catches the generic ValueError
    too, both must be caught BEFORE it (§12 ordering).
    """


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


#: What a job-level answer is grounded in when the caller names no base resume.
#: `hybrid` is not a tailorable/scoreable base (no `base_resumes` row), so it
#: bypasses the table gate and reads its disk data directly — which is also why
#: an install without that file gets the guarded 400 below rather than a 500.
DEFAULT_JOB_RESUME_SLUG = "hybrid"


def context_from_job(
    session: Session, job_id: UUID, base_slug: str | None = None
) -> tuple[Job, dict[str, Any]]:
    """The job and the resume a job-level answer is written FROM.

    `base_slug` is the caller's own pick — the side panel sends the base the
    Score stage selected, which is the same resume its fill would have used —
    and it goes through `load_base_resume`, so the table gate applies exactly as
    it does everywhere else. Without one, the generic default above stands.

    EITHER READ CAN FAIL ON AN ORDINARY INSTALL, which is why both are guarded
    and neither is allowed to be a 500: an unknown slug is a caller error, and a
    missing data file is a configuration the user can fix — this repo ships one
    example base resume, so the DEFAULT is the read most likely to be absent.
    The detail names the slug and never the path (`load_base_resume`'s rule).

    ONE ASYMMETRY, KNOWN: a file that EXISTS but holds broken JSON raises
    `json.JSONDecodeError` from the same two reads, and only the named-slug path
    turns it into a 400 (it is a ValueError subclass, so `load_base_resume`'s
    `except ValueError` above already catches it); the default path lets it out
    as a 500. Left as it is — a corrupt file the user hand-edited is a different
    failure from one they never had, and widening the default's `except` to
    ValueError would swallow whatever else that read grows.
    """
    job = session.get(Job, job_id)
    if job is None or not job.extracted_json:
        raise ValueError(f"Job not found or missing extracted data: {job_id}")
    if base_slug:
        try:
            return job, base_resume_data.load_base_resume(base_slug, session)
        except ValueError as exc:
            raise BaseResumeUnavailable(str(exc)) from exc
    try:
        return job, base_resume_data._read_base_resume_data(DEFAULT_JOB_RESUME_SLUG)
    except FileNotFoundError as exc:
        raise BaseResumeUnavailable(
            f"No resume data for job-level answers: this install has no "
            f"'{DEFAULT_JOB_RESUME_SLUG}' base resume. Name one with `base`, or "
            f"add its data file."
        ) from exc


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
    base_slug: str | None = None,
) -> list[str]:
    job, resume_json = context_from_job(session, job_id, base_slug)
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


def generate_cover_letter_for_job(
    job_id: UUID, tone: str, session: Session, base_slug: str | None = None
) -> str:
    # Threaded here too, though today's only sender of `base` is the panel's QnA
    # drawer (questions, not cover letters). One request key honoured on one
    # branch of `run_qa` and silently dropped on the other is the half-wired API
    # this repo pins against — and both branches ground on the same read.
    job, resume_json = context_from_job(session, job_id, base_slug)
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
