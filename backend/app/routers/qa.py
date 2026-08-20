from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.application import Application
from app.models.job import Job
from app.models.qa_entry import QAEntry
from app.schemas.qa import (
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
    role_titles,
)


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
        return _run_qa(payload, db)
    except qa_service.BaseResumeUnavailable as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
            prior = db.scalars(
                select(QAEntry).where(
                    QAEntry.application_id == payload.application_id,
                    QAEntry.kind == "cover_letter",
                )
            ).all()
            for entry in prior:
                artifacts.cleanup_qa_entry_files(entry)
                db.delete(entry)
            db.flush()
            response.cover_letter = qa_service.generate_cover_letter(
                payload.application_id, tone, db
            )
        else:
            response.cover_letter = qa_service.generate_cover_letter_for_job(
                payload.job_id, tone, db, payload.base
            )

    return response


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


@router.patch("/{entry_id}", response_model=QAEntryRead)
def update_qa_entry(
    entry_id: UUID,
    payload: QAEntryUpdate,
    db: Annotated[Session, Depends(get_db)],
):
    entry = db.get(QAEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="QA entry not found")
    entry.answer = payload.answer
    if entry.pdf_path:
        artifacts.cleanup_qa_entry_files(entry)
        entry.pdf_path = None
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
def delete_qa_entry(entry_id: UUID, db: Annotated[Session, Depends(get_db)]):
    entry = db.get(QAEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="QA entry not found")
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
            detail="Only cover_letter entries can be rendered",
        )
    if not entry.answer:
        raise HTTPException(status_code=400, detail="Entry has no text to render")

    application = db.get(Application, entry.application_id)
    job = db.get(Job, application.job_id) if application else None
    if application is None or job is None:
        raise HTTPException(status_code=404, detail="Application or job not found")

    base_resume = base_resume_data.load_base_resume(application.base_resume, db)
    contact = base_resume.get("contact", {})
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
    stem = artifact_naming.artifact_stem(
        contact=contact,
        role=role_label,
        document_type="CoverLetter",
    )
    tex_text = pdf_render.render_cover_letter_tex(
        contact=contact,
        body=entry.answer,
        today=rendered_at.date(),
    )
    pdf_path = pdf_render.compile_cover_letter_pdf(tex_text, out_dir, stem=stem)

    entry.pdf_path = str(pdf_path)
    db.commit()
    db.refresh(entry)
    return entry


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
