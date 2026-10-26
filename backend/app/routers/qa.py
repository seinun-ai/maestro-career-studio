import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import agent_writer
from app.db import get_db
from app.services.sync import hooks
from app.models.application import Application
from app.models.job import Job
from app.models.qa_entry import QAEntry
from app.schemas.qa import (
    AuthoredAnswers,
    AuthoredCoverLetter,
    AuthoredCoverLetterRead,
    QAEntryRead,
    QAEntryUpdate,
    QARegenerateRequest,
    QARequest,
    QAResponse,
)
from app.services import (
    application_artifacts,
    artifact_naming,
    artifacts,
    base_resume_data,
    pdf_render,
    qa as qa_service,
    resumes_folder,
    role_titles,
)
from app.write_origin import WriteOrigin, get_write_origin


router = APIRouter(prefix="/api/qa", tags=["qa"])


@router.post("", response_model=QAResponse)
def run_qa(payload: QARequest, db: Annotated[Session, Depends(get_db)]):
    if payload.application_id is None and payload.job_id is None:
        raise HTTPException(status_code=400, detail="application_id or job_id is required")
    if not payload.questions and payload.cover_letter is None:
        raise HTTPException(
            status_code=400,
            detail="questions or cover_letter is required",
        )

    # Two shapes of "the caller named something unusable", mapped like
    # `regenerate_entry` below — ORDER IS THE CONTRACT (§12): the narrow
    # subclass first, the generic ValueError second, and ValidationError (also a
    # ValueError) never reaches here because nothing in `_run_qa` validates a
    # model.
    #
    # 400: the resume a JOB-level answer is written from could not be read — an
    # unknown `base`, or an install with no data file for the default. What
    # shipped was a bare FileNotFoundError out of the disk read.
    #
    # 404: the id resolved to no row ("Application not found", "Job not found or
    # missing extracted data"). That left this handler as an unexplained 500
    # while the sibling answered the same shape with a 404.
    try:
        if not agent_writer.maestro_writes():
            # An agent app is told an id is unknown (404) before it is told to write the text
            # itself. The web's request goes straight on: _run_qa looks the target up anyway.
            _require_target(payload, db)
        agent_writer.refuse_unless_maestro_writes(_write_it_yourself(payload))
        return _run_qa(payload, db)
    except qa_service.BaseResumeUnavailable as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _require_target(payload: QARequest, db: Session) -> None:
    """The lookup `_run_qa` starts with, by the same rule (an application when one is named,
    else the job), raising what it raises."""
    if payload.application_id is not None:
        qa_service.application_context(db, payload.application_id)
    else:
        qa_service.context_from_job(db, payload.job_id, payload.base)


def _write_it_yourself(payload: QARequest) -> str:
    """The tools an agent app saves its own text with, for what this request asked for."""
    if payload.questions and payload.cover_letter is not None:
        return ("Write the answers and the letter yourself and save them with store_qa_answers "
                "and store_cover_letter.")
    if payload.questions:
        return "Write the answers yourself and save them with store_qa_answers."
    return "Write the letter yourself and save it with store_cover_letter."


def _run_qa(payload: QARequest, db: Session) -> QAResponse:
    response = QAResponse()
    if payload.questions:
        if payload.application_id is not None:
            response.answers = qa_service.answer_questions(
                payload.application_id, payload.questions, db
            )
        else:
            response.answers = qa_service.answer_questions_for_job(
                payload.job_id, payload.questions, db, payload.base
            )

    if payload.cover_letter is not None:
        tone = payload.cover_letter.tone
        if payload.application_id is not None:
            # The saved letter goes only once its replacement exists: a failed
            # generation (provider down, a bad key) keeps it. The ids are read
            # first and that read transaction is ENDED before the call, so no
            # lock or snapshot is held across the LLM's whole run (tens of
            # seconds; design §3.2) — nothing was written, so this commit
            # writes nothing. `generate_cover_letter` commits the new row.
            prior_ids = list(
                db.scalars(
                    select(QAEntry.id).where(
                        QAEntry.application_id == payload.application_id,
                        QAEntry.kind == "cover_letter",
                    )
                )
            )
            db.commit()
            response.cover_letter = qa_service.generate_cover_letter(
                payload.application_id, tone, db
            )
            _remove_entries(db, prior_ids)
        else:
            response.cover_letter = qa_service.generate_cover_letter_for_job(
                payload.job_id, tone, db, payload.base
            )

    return response


@router.post("/cover-letter", response_model=AuthoredCoverLetterRead)
def store_cover_letter(
    payload: AuthoredCoverLetter,
    db: Annotated[Session, Depends(get_db)],
    write_origin: Annotated[WriteOrigin, Depends(get_write_origin)],
):
    """A cover letter the caller wrote (MCP `store_cover_letter`; no model call):
    it replaces the application's letter like a generated one does, then its PDF
    is made. The letter stays stored when the PDF fails; `render_error` says why."""
    application = db.get(Application, payload.application_id)
    job = db.get(Job, application.job_id) if application else None
    if application is None or job is None:
        raise HTTPException(status_code=404, detail="Application not found")
    hooks.require_owned(db, job.id)
    prior_ids = list(
        db.scalars(
            select(QAEntry.id).where(
                QAEntry.application_id == application.id,
                QAEntry.kind == "cover_letter",
            )
        )
    )
    try:
        entry = qa_service.store_cover_letter(
            application.id, payload.text, db, author=write_origin.detail or write_origin.origin
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _remove_entries(db, prior_ids)
    try:
        render_note = _render_letter(db, entry, application, job)
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        db.rollback()
        db.refresh(entry)
        entry.render_error = (
            pdf_render.extract_render_error(str(exc)) or "The PDF could not be made."
        )
        return entry
    entry.render_note = render_note
    return entry


@router.post("/answers", response_model=list[QAEntryRead])
def store_answers(
    payload: AuthoredAnswers,
    db: Annotated[Session, Depends(get_db)],
    write_origin: Annotated[WriteOrigin, Depends(get_write_origin)],
):
    """Screening answers the caller wrote (MCP `store_qa_answers`; no model call)."""
    application = db.get(Application, payload.application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    hooks.require_owned(db, application.job_id)
    try:
        return qa_service.store_answers(
            application.id,
            [(item.question, item.answer) for item in payload.answers],
            db,
            author=write_origin.detail or write_origin.origin,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _remove_entries(db: Session, ids: list[UUID]) -> None:
    """Delete these entries, COMMIT, then remove their rendered files.

    §6 {#inv-staged-artifact-removal}: a rendered file is never removed inside
    a transaction that can still roll back, or a rollback leaves rows whose
    pdf_path names a deleted file. The rows are re-read here, so a PDF rendered
    while the replacement was being generated goes with its row.
    """
    if not ids:
        return
    rows = db.scalars(select(QAEntry).where(QAEntry.id.in_(ids))).all()
    stale = [Path(entry.pdf_path) for entry in rows if entry.pdf_path]
    for entry in rows:
        db.delete(entry)
    db.commit()
    artifacts.remove_files(stale)


@router.get("", response_model=list[QAEntryRead])
def list_qa_entries(
    db: Annotated[Session, Depends(get_db)],
    application_id: Annotated[UUID, Query()],
):
    return list(
        db.scalars(
            select(QAEntry)
            .where(QAEntry.application_id == application_id)
            .order_by(QAEntry.created_at.desc())
        )
    )


def _entry_for_write(db: Session, entry_id: UUID) -> QAEntry:
    entry = db.get(QAEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="QA entry not found")
    application = db.get(Application, entry.application_id)
    hooks.require_owned(db, application.job_id if application else None)
    return entry


@router.patch("/{entry_id}", response_model=QAEntryRead)
def update_qa_entry(
    entry_id: UUID,
    payload: QAEntryUpdate,
    db: Annotated[Session, Depends(get_db)],
):
    entry = _entry_for_write(db, entry_id)
    entry.answer = payload.answer
    if entry.pdf_path:
        artifacts.cleanup_qa_entry_files(entry)
        entry.pdf_path = None
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
def delete_qa_entry(entry_id: UUID, db: Annotated[Session, Depends(get_db)]):
    entry = _entry_for_write(db, entry_id)
    artifacts.cleanup_qa_entry_files(entry)
    db.delete(entry)
    db.commit()


@router.post("/{entry_id}/render", response_model=QAEntryRead)
def render_cover_letter(entry_id: UUID, db: Annotated[Session, Depends(get_db)]):
    entry = db.get(QAEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="QA entry not found")
    if entry.kind != "cover_letter":
        raise HTTPException(
            status_code=400,
            detail="Only cover letters can be made into a PDF.",
        )
    if not entry.answer:
        raise HTTPException(status_code=400, detail="This cover letter is empty.")

    application = db.get(Application, entry.application_id)
    job = db.get(Job, application.job_id) if application else None
    if application is None or job is None:
        raise HTTPException(status_code=404, detail="Application or job not found")

    hooks.require_owned(db, job.id)
    try:
        render_note = _render_letter(db, entry, application, job)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    # Transient, unmapped (QAEntryRead.render_note): lives on the row, never in it.
    entry.render_note = render_note
    return entry


def _render_letter(db: Session, entry: QAEntry, application: Application, job: Job) -> str | None:
    """Make the cover letter's PDF, record it on the entry, commit; returns the
    render note. Raises ValueError for a template that cannot render it (and a
    resume that cannot be read), RuntimeError for a failed compile and
    subprocess.TimeoutExpired for a hung one. The caller checks ownership first:
    this writes to disk."""
    base_resume = base_resume_data.load_base_resume(application.base_resume, db)
    contact = base_resume.get("contact", {})
    # The cover letter follows the RESUME's engine: resolve the application's
    # template exactly as application_render.render_resume does (None → the
    # default), fallback rule included. Resolved BEFORE get_dir so a 400 never
    # allocates (and persists) an empty artifact directory.
    tmpl, render_note = pdf_render.resolve_render_template(application.template_id, db)
    rendered_at = datetime.now(UTC)
    role_label = role_titles.generic_role_title(
        role_category=job.role_category,
        base_resume_role=base_resume_data.declared_role(db, application.base_resume),
        title=job.title,
    )
    out_dir = application_artifacts.get_dir(
        db,
        application,
        company=job.company,
        role_label=role_label,
        when=rendered_at.date(),
    )
    # Allocating can move a legacy application's files on disk; committed now,
    # so a failed compile's rollback never points the rows back at the old place.
    db.commit()
    stem = artifact_naming.artifact_stem(
        contact=contact,
        role=role_label,
        document_type="CoverLetter",
    )
    doc = pdf_render.render_cover_letter(
        engine=tmpl.engine, contact=contact, body=entry.answer, today=rendered_at.date()
    )
    pdf_path = pdf_render.compile_cover_letter_pdf(
        doc.source_text, out_dir, stem=stem, engine=doc.engine, sys_inputs=doc.sys_inputs
    )

    entry.pdf_path = str(pdf_path)
    db.commit()
    db.refresh(entry)
    resumes_folder.copy_application(application.id)  # never raises
    return render_note


@router.get("/{entry_id}/pdf")
def get_qa_entry_pdf(entry_id: UUID, db: Annotated[Session, Depends(get_db)]):
    entry = db.get(QAEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="QA entry not found")
    if not entry.pdf_path or not Path(entry.pdf_path).exists():
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(
        entry.pdf_path,
        media_type="application/pdf",
        filename=Path(entry.pdf_path).name,
    )


@router.post("/{entry_id}/regenerate", response_model=QAEntryRead)
def regenerate_qa_entry(
    entry_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    payload: QARegenerateRequest | None = None,
):
    try:
        entry = qa_service.regenerate_entry(
            entry_id,
            tone=payload.tone if payload else None,
            session=db,
        )
    except qa_service.UnsupportedQAEntryKind as exc:
        # Entry exists but its kind can't be regenerated (retired kind) — 400,
        # not 404/500. Caught before the generic ValueError (§12 ordering).
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return entry
