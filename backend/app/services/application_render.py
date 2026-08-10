"""Render orchestration for one application's resume PDF.

Extracted from the applications router so both callers — the render endpoint
and Quick Tailor — share one pipeline instead of one router importing the
other's endpoint function. On any render failure the service persists
``application.render_error`` (rollback → refetch → commit) and re-raises the
ORIGINAL exception; mapping exceptions to HTTP statuses stays with the routers.

Missing application/job raise ``LookupError`` from the lookup phase, before the
persisting try-block — there is nothing meaningful to persist for those.
"""
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.base_resume import BaseResume
from app.models.job import Job
from app.schemas.formatting import overlay
from app.services import (
    application_artifacts,
    artifact_naming,
    base_resume_data,
    pdf_preview,
    pdf_render,
    role_titles,
)


def _persist_render_error(db: Session, application_id: UUID, exc: Exception) -> None:
    """Roll back the failed render transaction, refetch the application, and
    record the failure so the editor / quick-tailor can surface a stale-PDF
    reason. Called for EVERY render failure (422/400/404/500 alike at the HTTP
    layer) so a non-500 failure never leaves pdf_ready=false with no readable
    cause."""
    db.rollback()
    application = db.get(Application, application_id)
    if application is not None:
        application.render_error = str(exc)[:2000]
        db.commit()


def render_resume(
    db: Session, application_id: UUID, *, template_id: str | None = None
) -> tuple[Path, Path]:
    """Render the application's tailored draft (or its base, when no draft is
    stored yet) to PDF and persist the artifact paths. Returns
    ``(source_path, pdf_path)``; commits on success."""
    application = db.get(Application, application_id)
    if application is None:
        raise LookupError("Application not found")

    job = db.get(Job, application.job_id)
    if job is None:
        raise LookupError("Job not found")

    # No explicit choice from the caller -> use the application's persisted
    # choice (None -> default template).
    if template_id is None:
        template_id = application.template_id

    try:
        if application.customized_json is not None:
            customized = deepcopy(application.customized_json)
        else:
            # No tailored draft stored: render straight from the base resume
            # (and persist the snapshot so later edits start from it).
            customized = base_resume_data.load_base_resume(application.base_resume, db)
            application.customized_json = customized

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
            contact=customized.get("contact", {}),
            role=role_label,
            document_type="Resume",
        )
        # Formatting: raw partial overlay (base-resume diffs, then application-level
        # knobs). Kept as partials — NOT a full dict — so the template's
        # default_formatting still shows through in render_tex where nothing overrides.
        base_row = db.get(BaseResume, application.base_resume)
        formatting = overlay(
            base_row.formatting_json if base_row else None,
            application.formatting_json,
        )

        # Engine dispatch: render_document resolves the template + engine;
        # compile_document writes the source artifact (stem.tex or stem.typ)
        # beside the PDF. tex_path stores whichever source the engine produced.
        doc = pdf_render.render_document(
            customized, template_id=template_id, session=db, formatting=formatting
        )
        source_path, pdf_path = pdf_render.compile_document(doc, out_dir, stem=stem)

        application.tex_path = str(source_path)
        application.pdf_path = str(pdf_path)
        application.pdf_pages = len(pdf_preview.ensure_page_images(pdf_path))
        application.render_error = None
        db.commit()

        return source_path, pdf_path
    except Exception as e:
        _persist_render_error(db, application_id, e)
        raise
