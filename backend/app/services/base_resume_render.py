from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.models.base_resume import BaseResume
from app.services import pdf_preview, pdf_render


def _paths(slug: str) -> tuple[Path, Path]:
    base = Path(settings.base_resumes_dir)
    tex_path = base / "tex" / f"{slug}.tex"
    pdf_path = base / "pdfs" / f"{slug}.pdf"
    return tex_path, pdf_path


def render_base_resume(slug: str, db: Session, *, template_id: str | None = None) -> BaseResume:
    row = db.get(BaseResume, slug)
    if row is None:
        raise LookupError(f"Base resume not found: {slug}")

    # Clear FIRST, set only on success: the row is a session-identity object and
    # `render_note` is an unmapped attribute, so neither rollback nor refresh
    # clears it. Without this, a failed re-render (resume_ops.edit_base persists
    # render_error and returns this same object) would still carry the note from
    # an earlier successful render in the same session.
    row.render_note = None

    # No explicit template -> use the resume's persisted choice (None -> default).
    if template_id is None:
        template_id = row.template_id

    tex_path, pdf_path = _paths(slug)
    source_path, doc = pdf_render.render_and_compile(
        row.data_json,
        tex_path,
        pdf_path,
        template_id=template_id,
        session=db,
        formatting=row.formatting_json,
    )

    row.tex_path = str(source_path)
    row.pdf_path = str(pdf_path)
    row.pdf_rendered_at = datetime.now(UTC)
    row.pdf_pages = len(pdf_preview.ensure_page_images(pdf_path))
    row.render_error = None
    db.commit()
    db.refresh(row)
    row.resolved_template_id = doc.resolved_template_id
    row.resolved_engine = doc.engine
    row.render_note = doc.render_note
    return row


def record_render_error(db: Session, slug: str, message: str) -> BaseResume:
    """Persist a POST-COMMIT render failure on the row; return it refreshed.

    Every re-render of a base resume runs AFTER its data write committed
    (resume_ops.edit_base, career_kb._persist_port, the project port, the
    version restore), so a render failure must not fail the request: it would
    report failure for a change that landed and invite a retry that applies an
    additive write twice. This is the shared tail — roll the failed render's
    session state back, record `render_error` (what the UI's stale-PDF banner
    reads), keep the data write. `render_note` stays None: a failed render
    substituted nothing, and `render_base_resume` already cleared it.
    """
    db.rollback()
    row = db.get(BaseResume, slug)
    row.render_error = pdf_render.extract_render_error(message)
    db.commit()
    db.refresh(row)
    return row
