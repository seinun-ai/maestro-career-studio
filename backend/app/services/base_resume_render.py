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

    # No explicit template -> use the resume's persisted choice (None -> default).
    if template_id is None:
        template_id = row.template_id

    tex_path, pdf_path = _paths(slug)
    source_path = pdf_render.render_and_compile(
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
    return row
