import copy
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings  # noqa: F401 — shared settings object kept as the router test seam
from app.db import get_db
from app.models.base_resume import BaseResume
from app.schemas.base_resume import (
    BaseFromKBPlanRead,
    BaseFromKBPlanRequest,
    BaseResumeFromKB,
    BaseResumeIdentity,
    BaseResumeCreate,
    BaseResumeDetail,
    BaseResumeDuplicate,
    BaseResumePortProject,
    BaseResumePortProjectResult,
    BaseResumeSummary,
    BaseResumeUpdate,
    ExcludedEntityRead,
)
from app.schemas.formatting import validate_formatting
from app.schemas.resume import ResumeData
from app.schemas.resume_edit import ResumeEditRequest
from app.services import (
    base_from_kb_plan,
    base_resume_data,
    base_resume_render,
    career_kb,
    pdf_preview,
    role_categories,
)
from app.services import resume_ops
from app.services.resume_versions import record_version


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/base-resumes", tags=["base-resumes"])


SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")


def _validated_role(value: str | None) -> str:
    """Validate a HUMAN-supplied role, or default to "unknown".

    Deliberately not `role_categories.normalize()`: that maps anything
    unrecognized to "other", which is correct for LLM job extraction but would
    turn a typo like "data_scientistt" into a silent, plausible "Other" here.
    A person supplying a value gets a 422 instead.
    """
    if value is None:
        return role_categories.UNKNOWN
    if value not in role_categories.all_keys():
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown role_category {value!r}. Valid values: "
                f"{', '.join(role_categories.all_keys())}"
            ),
        )
    return value


def _validate_slug(slug: str) -> None:
    if not SLUG_RE.match(slug):
        raise HTTPException(
            status_code=400,
            detail="slug must be lowercase alphanumeric with underscores",
        )


def _next_role_slug(role_category: str, db: Session) -> str:
    """Allocate from every historical slug, including soft-deleted rows."""
    taken = set(db.scalars(select(BaseResume.slug)).all())
    if role_category not in taken:
        return role_category

    suffix = 2
    while f"{role_category}_{suffix}" in taken:
        suffix += 1
    return f"{role_category}_{suffix}"


def _detail(row: BaseResume, *, applied: list[dict] | None = None) -> BaseResumeDetail:
    return BaseResumeDetail(
        slug=row.slug,
        display_name=row.display_name,
        role_category=row.role_category,
        data=ResumeData.model_validate(row.data_json),
        pdf_path=row.pdf_path,
        tex_path=row.tex_path,
        pdf_rendered_at=row.pdf_rendered_at,
        formatting=row.formatting_json,
        template_id=row.template_id,
        pdf_pages=row.pdf_pages,
        render_error=row.render_error,
        updated_at=row.updated_at,
        archived_at=row.archived_at,
        applied=applied,
    )


def _write_json_file(slug: str, data: dict) -> None:
    from app.services.base_resume_data import write_base_resume_json

    write_base_resume_json(slug, data)


@router.get("", response_model=list[BaseResumeSummary])
def list_base_resumes(
    db: Annotated[Session, Depends(get_db)],
    include_archived: bool = False,
):
    """The ONE list query behind every base-resume picker in the app — the web
    grid, five in-app selectors, the extension dock and MCP list_base_resumes.
    Defaulting `include_archived` to False is therefore what makes archiving
    reach all of them without a per-caller change."""
    stmt = select(BaseResume).where(
        base_resume_data.active_filter()
        if include_archived
        else base_resume_data.selectable_filter()
    )
    rows = list(db.scalars(stmt.order_by(BaseResume.slug)))
    return [BaseResumeSummary.model_validate(row) for row in rows]


@router.get("/{slug}", response_model=BaseResumeDetail)
def get_base_resume(slug: str, db: Annotated[Session, Depends(get_db)]):
    row = db.get(BaseResume, slug)
    if row is None:
        raise HTTPException(status_code=404, detail="Base resume not found")
    return _detail(row)


@router.post("", response_model=BaseResumeDetail)
def create_base_resume(
    payload: BaseResumeCreate, db: Annotated[Session, Depends(get_db)]
):
    _validate_slug(payload.slug)
    existing = db.get(BaseResume, payload.slug)
    if existing is not None:
        if existing.deleted_at is not None:
            raise HTTPException(
                status_code=409,
                detail="A base resume with this slug was deleted; choose a different slug to preserve history",
            )
        raise HTTPException(status_code=409, detail="Base resume already exists")

    data_dict = payload.data.model_dump(mode="json")
    row = BaseResume(
        slug=payload.slug,
        display_name=payload.display_name,
        data_json=data_dict,
        role_category=_validated_role(payload.role_category),
    )
    db.add(row)
    record_version(db, "base", payload.slug, data_dict, source="create")
    db.commit()
    db.refresh(row)

    _write_json_file(payload.slug, data_dict)
    base_resume_render.render_base_resume(payload.slug, db)
    db.refresh(row)
    return _detail(row)


@router.put("/{slug}", response_model=BaseResumeDetail)
def update_base_resume(
    slug: str,
    payload: BaseResumeUpdate,
    db: Annotated[Session, Depends(get_db)],
):
    row = db.get(BaseResume, slug)
    if row is None:
        raise HTTPException(status_code=404, detail="Base resume not found")

    data_dict = payload.data.model_dump(mode="json")
    row.data_json = data_dict
    if "display_name" in payload.model_fields_set:
        row.display_name = payload.display_name
    # Template: omitted -> unchanged; explicit null -> reset to default; value -> set.
    if "template_id" in payload.model_fields_set:
        row.template_id = payload.template_id
    # Formatting: omitted -> unchanged; explicit null -> clear; value -> set.
    if "formatting" in payload.model_fields_set:
        try:
            row.formatting_json = validate_formatting(payload.formatting)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    record_version(db, "base", slug, data_dict, source="form_edit")
    db.commit()
    db.refresh(row)

    _write_json_file(slug, data_dict)
    try:
        base_resume_render.render_base_resume(
            slug, db, template_id=payload.template_id
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    db.refresh(row)
    return _detail(row)


@router.patch("/{slug}/edits", response_model=BaseResumeDetail)
def edit_base_resume(
    slug: str,
    payload: ResumeEditRequest,
    db: Annotated[Session, Depends(get_db)],
    template_id: str | None = None,
):
    """Apply typed edit ops to a base resume server-side.

    The server reads the stored data, applies only the supplied ops, validates,
    persists, and re-renders. Unlike PUT, the caller never resends untouched
    fields. Out-of-range indices / unknown skills categories -> 400.
    """
    row = db.get(BaseResume, slug)
    if row is None:
        raise HTTPException(status_code=404, detail="Base resume not found")

    # The shared pipeline (services/resume_ops.py) owns persist + version +
    # file write + tolerant re-render — post-commit render failures (incl. an
    # extras-incompatible template) degrade to a persisted render_error, NEVER
    # a 4xx that would push clients to retry already-applied ops.
    try:
        row, _, _, applied = resume_ops.edit_base(
            db, row, payload.ops, source="edit_ops", template_id=template_id
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _detail(row, applied=applied)


@router.post("/from-kb/plan", response_model=BaseFromKBPlanRead)
def plan_from_kb(
    payload: BaseFromKBPlanRequest, db: Annotated[Session, Depends(get_db)]
):
    """Propose which Career KB entries belong on a new role-targeted resume.

    Persists NOTHING — the client shows the selection and the drafted summary
    for review, then calls POST /from-kb to create. Bullet wording is never
    touched here: approved points compose verbatim, and proposing rewrites is
    `kb_adapt`'s job, where every change carries provenance and needs approval.
    """
    role = _validated_role(payload.role_category)
    try:
        result = base_from_kb_plan.plan(db, role, payload.instruction)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except RuntimeError as e:  # provider unavailable
        raise HTTPException(status_code=502, detail=str(e)) from e
    return BaseFromKBPlanRead(
        include=result.include,
        exclude=[
            ExcludedEntityRead(id=x.id, title=x.title, reason=x.reason)
            for x in result.exclude
        ],
        summary=result.summary,
    )


@router.post("/from-kb", response_model=BaseResumeDetail)
def create_from_kb(
    payload: BaseResumeFromKB, db: Annotated[Session, Depends(get_db)]
):
    """Compose a new base resume from selected Career KB entities.

    The ground-up path for a NEW role: pick the role, pick what belongs on it.
    Deliberately reuses the standard create pipeline below (slug validation,
    reserved-slug guard, 409s, version row, disk write, render) — a bare INSERT
    would skip the disk write, which SYSTEM.md §3 makes an invariant.

    Scope caveat, surfaced rather than hidden: only experience / projects /
    education / certifications come from the selected entities. `contact` and
    `skills` come from the KB profile and arrive in full, because the KB has no
    per-entity skill data to filter by — narrowing them would mean guessing.
    The summary is dropped unless `include_summary`, since a whole-career
    summary on a role-targeted resume is usually wrong.
    """
    slug = payload.slug
    role_category = payload.role_category
    if slug is None:
        if role_category is None:
            raise HTTPException(
                status_code=422,
                detail="role_category is required when slug is omitted",
            )
        role_category = _validated_role(role_category)
        slug = _next_role_slug(role_category, db)

    composed = career_kb.compose_resume_data(db, entity_ids=payload.entity_ids)

    # ResumeData only requires `contact`, so a selection matching nothing would
    # otherwise mint a contact-only resume with no error at all.
    if not any(
        composed.get(section)
        for section in ("experience", "projects", "education", "certifications")
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "The selected entities produced no resume content. Pick at least "
                "one experience, project, education entry, or certification that "
                "has approved points."
            ),
        )

    if payload.summary is not None:
        # A summary reviewed by the user in the plan step. Blank means they
        # cleared it, which is a decision — honour it rather than falling back
        # to the whole-career KB summary.
        composed["summary"] = payload.summary.strip() or None
    elif not payload.include_summary:
        composed["summary"] = None

    return create_base_resume(
        BaseResumeCreate(
            slug=slug,
            display_name=payload.display_name,
            data=ResumeData.model_validate(composed),
            role_category=role_category,
        ),
        db,
    )


@router.patch("/{slug}/identity", response_model=BaseResumeDetail)
def update_base_resume_identity(
    slug: str,
    payload: BaseResumeIdentity,
    db: Annotated[Session, Depends(get_db)],
):
    """Set a base resume's role and/or display name.

    Deliberately NOT the full PUT: that rewrites data_json, records a
    ResumeVersion, rewrites the on-disk JSON and recompiles the PDF. Declaring a
    role is metadata and must not touch the document or its artifacts.
    """
    row = db.get(BaseResume, slug)
    if row is None or row.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Base resume not found")

    fields = payload.model_fields_set
    if "role_category" in fields:
        # An explicit null clears the declaration back to the visible
        # "unknown" state; a value is validated, never coerced.
        row.role_category = _validated_role(payload.role_category)
    if "display_name" in fields:
        row.display_name = payload.display_name

    db.commit()
    db.refresh(row)
    return _detail(row)


@router.delete("/{slug}", status_code=204)
def delete_base_resume(slug: str, db: Annotated[Session, Depends(get_db)]):
    row = db.get(BaseResume, slug)
    if row is None:
        raise HTTPException(status_code=404, detail="Base resume not found")

    # Preserve-history policy: soft-delete the row and KEEP on-disk JSON/PDF/TEX.
    row.deleted_at = datetime.now(UTC)
    db.commit()


def _archivable(slug: str, db: Session) -> BaseResume:
    row = db.get(BaseResume, slug)
    if row is None or row.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Base resume not found")
    return row


@router.post("/{slug}/archive", response_model=BaseResumeDetail)
def archive_base_resume(slug: str, db: Annotated[Session, Depends(get_db)]):
    """Hide from pickers, keep everything else working.

    Deliberately touches no artifact: the JSON, PDF, TEX and version history
    are all untouched, and the resume stays resolvable by slug. Unlike DELETE
    this is meant to be undone.
    """
    row = _archivable(slug, db)
    row.archived_at = datetime.now(UTC)
    db.commit()
    db.refresh(row)
    return _detail(row)


@router.post("/{slug}/unarchive", response_model=BaseResumeDetail)
def unarchive_base_resume(slug: str, db: Annotated[Session, Depends(get_db)]):
    row = _archivable(slug, db)
    row.archived_at = None
    db.commit()
    db.refresh(row)
    return _detail(row)


@router.post("/{slug}/port-project", response_model=BaseResumePortProjectResult)
def port_project_to_base_resume(
    slug: str,
    payload: BaseResumePortProject,
    db: Annotated[Session, Depends(get_db)],
):
    if slug == payload.target_slug:
        raise HTTPException(
            status_code=400, detail="Cannot port a project to the same base resume"
        )
    source = db.get(BaseResume, slug)
    if source is None:
        raise HTTPException(status_code=404, detail="Source base resume not found")

    target = db.get(BaseResume, payload.target_slug)
    if target is None:
        raise HTTPException(status_code=404, detail="Target base resume not found")

    projects = source.data_json.get("projects") or []
    if payload.project_index < 0 or payload.project_index >= len(projects):
        raise HTTPException(status_code=400, detail="project_index out of range")

    ported = copy.deepcopy(projects[payload.project_index])
    ported["enabled"] = False

    target_data = copy.deepcopy(target.data_json)
    target_projects = list(target_data.get("projects") or [])
    target_projects.append(ported)
    target_data["projects"] = target_projects

    ResumeData.model_validate(target_data)
    target.data_json = target_data
    record_version(
        db,
        "base",
        payload.target_slug,
        target_data,
        source="import",
        summary=f"Ported project from {slug}",
    )
    db.commit()
    db.refresh(target)

    _write_json_file(payload.target_slug, target_data)
    base_resume_render.render_base_resume(payload.target_slug, db)

    return BaseResumePortProjectResult(
        target_slug=payload.target_slug,
        project_index=len(target_projects) - 1,
    )


@router.post("/{slug}/duplicate", response_model=BaseResumeDetail)
def duplicate_base_resume(
    slug: str,
    payload: BaseResumeDuplicate,
    db: Annotated[Session, Depends(get_db)],
):
    _validate_slug(payload.new_slug)
    source = db.get(BaseResume, slug)
    if source is None:
        raise HTTPException(status_code=404, detail="Base resume not found")
    existing = db.get(BaseResume, payload.new_slug)
    if existing is not None:
        if existing.deleted_at is not None:
            raise HTTPException(
                status_code=409,
                detail="A base resume with this slug was deleted; choose a different slug to preserve history",
            )
        raise HTTPException(status_code=409, detail="Target slug already exists")

    import copy

    data_copy = copy.deepcopy(source.data_json)
    row = BaseResume(
        slug=payload.new_slug,
        display_name=payload.new_display_name or source.display_name,
        data_json=data_copy,
        # A duplicate targets the same role by definition.
        role_category=source.role_category,
    )
    db.add(row)
    record_version(
        db,
        "base",
        payload.new_slug,
        data_copy,
        source="create",
        summary=f"Duplicated from {slug}",
    )
    db.commit()
    db.refresh(row)

    _write_json_file(payload.new_slug, data_copy)
    base_resume_render.render_base_resume(payload.new_slug, db)
    db.refresh(row)
    return _detail(row)


@router.get("/{slug}/pdf")
def get_base_resume_pdf(
    slug: str,
    db: Annotated[Session, Depends(get_db)],
    download: bool = False,
):
    row = db.get(BaseResume, slug)
    if row is None:
        raise HTTPException(status_code=404, detail="Base resume not found")
    if not row.pdf_path or not Path(row.pdf_path).exists():
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(
        row.pdf_path,
        media_type="application/pdf",
        filename=f"{slug}.pdf",
        content_disposition_type="attachment" if download else "inline",
    )


@router.get("/{slug}/preview/pages")
def get_preview_manifest(slug: str, db: Annotated[Session, Depends(get_db)]):
    row = db.get(BaseResume, slug)
    if row is None or not row.pdf_path or not Path(row.pdf_path).exists():
        raise HTTPException(status_code=404, detail="PDF not found")
    pages = pdf_preview.ensure_page_images(Path(row.pdf_path))
    return {
        "page_count": len(pages),
        "rendered_at": row.pdf_rendered_at,
        "render_error": row.render_error,
    }


@router.get("/{slug}/preview/page/{page}")
def get_preview_page(slug: str, page: int, db: Annotated[Session, Depends(get_db)]):
    row = db.get(BaseResume, slug)
    if row is None or not row.pdf_path or not Path(row.pdf_path).exists():
        raise HTTPException(status_code=404, detail="PDF not found")
    path = pdf_preview.pages_dir(Path(row.pdf_path)) / f"page-{page}.png"
    if not path.exists():
        pages = pdf_preview.ensure_page_images(Path(row.pdf_path))
        if page < 1 or page > len(pages):
            raise HTTPException(status_code=404, detail="Page not found")
        path = pages[page - 1]
    return FileResponse(path, media_type="image/png")


@router.post("/{slug}/render", response_model=BaseResumeDetail)
def render_base_resume_endpoint(
    slug: str,
    db: Annotated[Session, Depends(get_db)],
    template_id: str | None = None,
):
    row = db.get(BaseResume, slug)
    if row is None:
        raise HTTPException(status_code=404, detail="Base resume not found")
    try:
        base_resume_render.render_base_resume(slug, db, template_id=template_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    db.refresh(row)
    return _detail(row)
