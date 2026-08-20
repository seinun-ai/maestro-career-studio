from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.formatting import validate_formatting
from app.schemas.template import (
    TemplateCreate,
    TemplateDefaultFormatting,
    TemplateDetail,
    TemplateSummary,
    TemplateUpdate,
)
from app.services import pdf_preview
from app.services import template_registry as reg
from app.services import template_validation as tv

router = APIRouter(prefix="/api/templates", tags=["templates"])


def _with_fmt_keys(row):
    # Attach the derived fmt.* key list so from_attributes serialization picks it
    # up (it is computed from source, not stored on the model).
    row.supported_fmt_keys = reg.supported_fmt_keys(row.source or "", row.engine)
    return row


@router.get("", response_model=list[TemplateSummary])
def list_templates(
    db: Annotated[Session, Depends(get_db)],
    include_archived: bool = False,
):
    """The ONE list query behind the gallery and every template picker.

    Defaulting `include_archived` to False is what makes archiving reach all of
    them without a per-caller change — the same lever base resumes use.
    """
    # validate=False: rows only. Rendering here would COMMIT this request's
    # transaction (see ensure_seed_templates) — startup owns validation.
    reg.ensure_seed_templates(db, validate=False)
    rows = reg.list_all(db)
    if not include_archived:
        rows = [row for row in rows if row.archived_at is None]
    return [_with_fmt_keys(row) for row in rows]


@router.get("/{template_id}", response_model=TemplateDetail)
def get_template(template_id: str, db: Annotated[Session, Depends(get_db)]):
    row = reg.get(db, template_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return _with_fmt_keys(row)


@router.post("", response_model=TemplateDetail)
def create_template(
    payload: TemplateCreate,
    db: Annotated[Session, Depends(get_db)],
    validate: bool = False,
):
    try:
        row = reg.create_draft(
            db,
            id=payload.id,
            display_name=payload.display_name,
            source=payload.source,
            origin=payload.origin,
            engine=payload.engine,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if validate:
        tv.validate_template(row.id, db)
        db.refresh(row)
    return _with_fmt_keys(row)


@router.put("/{template_id}", response_model=TemplateDetail)
def update_template(
    template_id: str,
    payload: TemplateUpdate,
    db: Annotated[Session, Depends(get_db)],
    allow_default_edit: bool = False,
    validate: bool = False,
):
    row = reg.get(db, template_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found")
    if row.is_default and not allow_default_edit:
        raise HTTPException(
            status_code=403,
            detail="Editing the default template requires allow_default_edit",
        )
    if payload.engine is not None and payload.engine != row.engine:
        raise HTTPException(
            status_code=400,
            detail="engine is immutable after creation — create a new template instead",
        )
    row = reg.update_draft(
        db, template_id, source=payload.source, display_name=payload.display_name
    )
    # `validate=true` collapses the save -> validate round trip: the returned
    # row's status/last_error reflect the compile result.
    if validate:
        tv.validate_template(template_id, db)
        db.refresh(row)
    return _with_fmt_keys(row)


@router.put("/{template_id}/default-formatting", response_model=TemplateDetail)
def set_default_formatting(
    template_id: str,
    payload: TemplateDefaultFormatting,
    db: Annotated[Session, Depends(get_db)],
):
    row = reg.get(db, template_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found")
    try:
        validated = validate_formatting(payload.formatting)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    # Persist the theme's default overlay without touching status (this is a
    # knob change, not a source change, so it does not invalidate the compile).
    row.default_formatting = validated
    # Compile before commit so a successful preview can stamp validated_at in
    # the SAME transaction as the formatting write. A second commit would bump
    # updated_at again (Column.onupdate) and re-trigger the gallery stale chip.
    try:
        tv.compile_against_sample(
            row.source,
            keep_pdf_at=tv._preview_path(row.id),
            default_formatting=row.default_formatting,
            engine=row.engine,
        )
    except Exception:  # noqa: BLE001 — preview refresh is best-effort
        pass
    else:
        # Preview on disk matches source + knobs — clear the false stale chip.
        row.validated_at = datetime.now(UTC)
    db.commit()
    db.refresh(row)
    return _with_fmt_keys(row)


@router.post("/{template_id}/validate")
def validate_template_endpoint(template_id: str, db: Annotated[Session, Depends(get_db)]):
    try:
        return tv.validate_template(template_id, db)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        # A row whose id predates the registry's slug gate (see
        # validate_template_id): refusing it is correct, but it must read as a
        # 400 about the id, not an unhandled 500.
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{template_id}/preview.pdf")
def template_preview(template_id: str, db: Annotated[Session, Depends(get_db)]):
    row = reg.get(db, template_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found")
    if row.status != "ready":
        raise HTTPException(status_code=404, detail="Template not validated; no current preview")
    preview = tv._preview_path(template_id)
    if not preview.exists():
        raise HTTPException(status_code=404, detail="No preview file; validate the template first")
    return FileResponse(
        preview,
        media_type="application/pdf",
        filename=f"{template_id}.pdf",
        content_disposition_type="inline",
    )


def _ready_preview_path(template_id: str, db: Session) -> Path:
    """Resolve the on-disk preview PDF for a ready template, or raise 404."""
    row = reg.get(db, template_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found")
    if row.status != "ready":
        raise HTTPException(status_code=404, detail="Template not validated; no current preview")
    preview = tv._preview_path(template_id)
    if not preview.exists():
        raise HTTPException(status_code=404, detail="No preview file; validate the template first")
    return preview


@router.get("/{template_id}/preview/pages")
def template_preview_manifest(template_id: str, db: Annotated[Session, Depends(get_db)]):
    preview = _ready_preview_path(template_id, db)
    pages = pdf_preview.ensure_page_images(preview)
    rendered_at = datetime.fromtimestamp(preview.stat().st_mtime, tz=UTC).isoformat()
    return {"page_count": len(pages), "rendered_at": rendered_at}


@router.get("/{template_id}/preview/page/{page}")
def template_preview_page(
    template_id: str, page: int, db: Annotated[Session, Depends(get_db)]
):
    preview = _ready_preview_path(template_id, db)
    path = pdf_preview.pages_dir(preview) / f"page-{page}.png"
    if not path.exists():
        pages = pdf_preview.ensure_page_images(preview)
        if page < 1 or page > len(pages):
            raise HTTPException(status_code=404, detail="Page not found")
        path = pages[page - 1]
    return FileResponse(path, media_type="image/png")


@router.post("/{template_id}/set-default", response_model=TemplateDetail)
def set_default_endpoint(template_id: str, db: Annotated[Session, Depends(get_db)]):
    try:
        row = reg.set_default(db, template_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _with_fmt_keys(row)


def _archivable(template_id: str, db: Session):
    row = reg.get(db, template_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found")
    if row.is_default:
        # Archiving hides a template from every picker, and the default is the
        # render fallback for any resume whose template_id no longer resolves.
        # Hiding it would leave that fallback unreachable in the UI while it
        # kept being used — a state with no way back. Re-point the default
        # first, then archive this one.
        raise HTTPException(
            status_code=400,
            detail=(
                "The default template cannot be archived. Make another template "
                "the default first, then archive this one."
            ),
        )
    return row


@router.post("/{template_id}/archive", response_model=TemplateDetail)
def archive_template(template_id: str, db: Annotated[Session, Depends(get_db)]):
    """Hide from the gallery and every picker; change nothing else.

    Deliberately touches no artifact: the source, the preview PDF and the
    validation state all survive, and the template stays resolvable by id — so
    a resume already rendering with it keeps rendering. Unlike DELETE this is
    meant to be undone.
    """
    row = _archivable(template_id, db)
    row.archived_at = datetime.now(UTC)
    db.commit()
    db.refresh(row)
    return _with_fmt_keys(row)


@router.post("/{template_id}/unarchive", response_model=TemplateDetail)
def unarchive_template(template_id: str, db: Annotated[Session, Depends(get_db)]):
    row = _archivable(template_id, db)
    row.archived_at = None
    db.commit()
    db.refresh(row)
    return _with_fmt_keys(row)


@router.delete("/{template_id}", status_code=204)
def delete_template(template_id: str, db: Annotated[Session, Depends(get_db)]):
    try:
        reg.delete(db, template_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return Response(status_code=204)
