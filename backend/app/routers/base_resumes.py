import copy
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
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
    BaseResumeProposeRead,
    BaseResumeProposeRequest,
    BaseResumeSummary,
    BaseResumeUpdate,
    ExcludedEntityRead,
)
from app.schemas.formatting import validate_formatting
from app.schemas.job_preferences import MAX_LABEL_CHARS
from app.schemas.kb_sync import SyncResult, SyncStatus
from app.schemas.resume import ResumeData
from app.schemas.resume_edit import ResumeEditRequest
from app.services import (
    base_from_kb_plan,
    base_resume_data,
    base_resume_instruct,
    base_resume_render,
    career_kb,
    kb_base_sync,
    kb_consolidation,
    kb_import,
    pdf_preview,
    role_categories,
)
from app.services.attachment_extract import extract_text
from app.services import resume_ops
from app.services.resume_edit import ContentChangedError
from app.services.resume_versions import record_version


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/base-resumes", tags=["base-resumes"])


SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")


def _truncate_detail(text: str, limit: int = 12000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...(truncated)"


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


def _resolved_tag(
    role_label: str | None, role_category: str | None
) -> tuple[str | None, str]:
    """The FavoredRole mechanics, on a column pair. Returns (label, category).

    A missing category on free text is completed (`other` — the YAML's "a real
    role that matches no category"); a CONTRADICTING one would need the label's
    parent to disagree, and free text has no parent, so any explicit valid
    category is accepted as the user's confirmed mapping. Typing exactly a
    catalog entry is a PICK: label collapses to NULL and the key is stored, so
    one role cannot exist in two shapes.
    """
    if role_label is None:
        return None, _validated_role(role_category)
    cleaned = " ".join(role_label.split())
    if not cleaned or len(cleaned) > MAX_LABEL_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"role_label must be 1-{MAX_LABEL_CHARS} characters",
        )
    match = role_categories.match_free_text(cleaned)
    if match["confidence"] == "exact":
        # A catalog entry typed verbatim; store as the pick it is. An explicit
        # category that CONTRADICTS the pick 422s — the design's
        # validate-never-normalize rule, and what FavoredRole does for the
        # same shape. (Review fix: the first draft silently kept the pick and
        # dropped the contradiction.)
        parent = role_categories.parent_of(match["role"])
        if role_category is not None and _validated_role(role_category) != parent:
            raise HTTPException(
                status_code=422,
                detail=f"role_label {cleaned!r} is the catalog entry "
                f"{match['role']!r} under {parent!r}, not {role_category!r}",
            )
        return None, parent
    # An ALIAS hit ("cv engineer", "Sr. Data Scientist") is deliberately NOT a
    # collapse: match_free_text's own contract says an alias is a suggestion
    # the user confirms. The words are kept; the matched category applies only
    # when the client sends it explicitly — that explicit send IS the
    # confirmation. A bare alias therefore lands at (words, other).
    if role_category is not None:
        return cleaned, _validated_role(role_category)
    return cleaned, role_categories.OTHER


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


def _detail(
    row: BaseResume,
    *,
    applied: list[dict] | None = None,
    resolved_template_id: str | None = None,
    resolved_engine: str | None = None,
    template_fallback: bool | None = None,
) -> BaseResumeDetail:
    return BaseResumeDetail(
        slug=row.slug,
        display_name=row.display_name,
        role_category=row.role_category,
        role_label=row.role_label,
        data=ResumeData.model_validate(row.data_json),
        pdf_path=row.pdf_path,
        tex_path=row.tex_path,
        pdf_rendered_at=row.pdf_rendered_at,
        formatting=row.formatting_json,
        template_id=row.template_id,
        resolved_template_id=resolved_template_id,
        resolved_engine=resolved_engine,
        template_fallback=template_fallback,
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
    role_label, role_category = _resolved_tag(
        payload.role_label, payload.role_category
    )
    row = BaseResume(
        slug=payload.slug,
        display_name=payload.display_name,
        data_json=data_dict,
        role_category=role_category,
        role_label=role_label,
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
    except ContentChangedError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
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
    role_label, role_category = _resolved_tag(
        payload.role_label, payload.role_category
    )
    if slug is None:
        if payload.role_label is None and payload.role_category is None:
            raise HTTPException(
                status_code=422,
                detail="role_category is required when slug is omitted",
            )
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
            role_label=role_label,
        ),
        db,
    )


IMPORT_MAX_BYTES = kb_import.MAX_BYTES


def _parse_resume_upload(db: Session, file: UploadFile) -> tuple[str, dict, list[str]]:
    """(safe filename, ResumeData dict, salvage warnings) for one upload.

    The parsing half of the KB import, with its error contract mapped to HTTP:
    413 over the cap, 422 for a file the extractor or parser cannot use, 502
    when the model is unreachable. JSON is validated as-is with no model call.
    """
    safe_name = Path(file.filename or "upload").name or "upload"
    try:
        blob = file.file.read()
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"{safe_name}: could not read upload") from exc
    if len(blob) > IMPORT_MAX_BYTES:
        raise HTTPException(status_code=413, detail="file exceeds the 10 MB limit")

    if kb_import._is_json(safe_name, file.content_type):
        try:
            return safe_name, ResumeData.model_validate_json(blob).model_dump(mode="json"), []
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"{safe_name}: {exc}") from exc
    try:
        text = extract_text(safe_name, file.content_type, blob)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # Resolve the prompt and model BEFORE anything joins the session:
    # get_prompt commits its file default on first use (kb_import's rule).
    kb_consolidation.prefetch_prompts(db)
    try:
        parsed, warnings = kb_consolidation.parse_resume_text(db, text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:  # provider unavailable
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return safe_name, parsed, warnings


@router.post("/import", response_model=BaseResumeDetail)
def import_base_resume(
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
    slug: Annotated[str | None, Form()] = None,
    display_name: Annotated[str | None, Form()] = None,
    role_category: Annotated[str | None, Form()] = None,
    role_label: Annotated[str | None, Form()] = None,
):
    """Parse ONE uploaded resume file straight into a NEW base resume.

    The base-resume lane of the "New base resume" dialog, beside From Career KB
    / From existing / Blank. It reuses the KB import's parsing half — JSON is
    validated as-is, anything else goes extract_text → parse_resume_text (the
    smart model, into the ResumeData shape) — and then the standard create
    pipeline above (slug validation, 409s, version row, disk write, render).

    What it deliberately does NOT do: touch the Career KB. `POST /api/kb/import`
    is the onboarding action that mints bases AND consolidates them into the
    KB; this is the user saying "make me a base from this file" and nothing
    more, so no entity, point or port-log row is written. The KB sync pill on
    the resulting resume offers the KB half later, on request.

    Naming is the user's: `display_name` and `slug` win when given; otherwise
    the file's stem names the resume and a free slug is derived from that.
    """
    safe_name, parsed, parse_warnings = _parse_resume_upload(db, file)

    display = (display_name or "").strip() or (
        Path(safe_name).stem.replace("_", " ").strip() or "Imported resume"
    )
    if slug is None or not slug.strip():
        slug = kb_import._free_slug(db, kb_import._slugify(display))

    detail = create_base_resume(
        BaseResumeCreate(
            slug=slug.strip(),
            display_name=display,
            data=ResumeData.model_validate(parsed),
            role_category=role_category or None,
            role_label=role_label or None,
        ),
        db,
    )
    detail.parse_warnings = parse_warnings
    return detail


@router.post("/{slug}/propose", response_model=BaseResumeProposeRead)
def propose_base_resume_edits(
    slug: str,
    payload: BaseResumeProposeRequest,
    db: Annotated[Session, Depends(get_db)],
):
    """Propose edits (and/or advice) for a base resume from a free instruction.

    Persists NOTHING — the propose-then-approve shape of `/from-kb/plan` and of
    chat's `propose_edits`. The client shows the ops for review and applies
    them through `PATCH /{slug}/edits`, the one typed-op door every surface
    uses, so provenance, versioning and render all happen there. An
    ideas-only instruction ("what could this pivot to?") answers in `notes`
    with an empty op list.
    """
    row = db.get(BaseResume, slug)
    if row is None or row.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Base resume not found")
    try:
        proposal = base_resume_instruct.propose(db, row, payload.instruction)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except RuntimeError as e:  # provider unavailable
        raise HTTPException(status_code=502, detail=str(e)) from e
    return BaseResumeProposeRead(
        summary=proposal.summary,
        notes=proposal.notes,
        ops=[op.model_dump(mode="json") for op in proposal.ops],
        ops_count=len(proposal.ops),
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
    if "role_label" in fields:
        # An explicit null clears the declaration back to the visible
        # "unknown" state; a value is validated, never coerced.
        #
        # A label-only patch on a MAPPED row deliberately demotes the category
        # to `other`: the confirmation was for the OLD words, and new words are
        # a new role claim — a stale mapping must not silently transfer to
        # text it never confirmed. Clients keeping the mapping send the pair.
        # (Same omitted-vs-null shape as the branch below, decided the same
        # direction: what the user did not restate does not survive.)
        row.role_label, row.role_category = _resolved_tag(
            payload.role_label,
            payload.role_category if "role_category" in fields else None,
        )
    elif "role_category" in fields:
        # Omitted and explicit null are distinct: a category-only patch maps an
        # existing custom label, while null clears the whole declaration.
        row.role_label, row.role_category = _resolved_tag(
            row.role_label if payload.role_category is not None else None,
            payload.role_category,
        )
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
        role_label=source.role_label,
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
        rendered = base_resume_render.render_base_resume(
            slug, db, template_id=template_id
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=_truncate_detail(str(e))) from e
    db.refresh(row)
    resolved_template_id = getattr(rendered, "resolved_template_id", None)
    return _detail(
        row,
        resolved_template_id=resolved_template_id,
        resolved_engine=getattr(rendered, "resolved_engine", None),
        template_fallback=(
            template_id is not None and resolved_template_id != template_id
        ),
    )


@router.get("/{slug}/kb-sync-status", response_model=SyncStatus)
def kb_sync_status(slug: str, db: Annotated[Session, Depends(get_db)]):
    try:
        report = kb_base_sync.classify(db, slug)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return SyncStatus(
        items=[
            {
                "tier": item.tier,
                "section": item.section,
                "entity_id": item.entity_id,
                "entity_proposal": item.entity_proposal,
                "matched_point_id": item.matched_point_id,
                "text": item.text,
            }
            for item in report["items"]
        ],
        skills_new=report["skills_new"],
        counts=report["counts"],
        last_kb_synced_at=report["last_kb_synced_at"],
    )


@router.post("/{slug}/kb-sync", response_model=SyncResult)
def kb_sync_apply(slug: str, db: Annotated[Session, Depends(get_db)]):
    try:
        result = kb_base_sync.apply(db, slug)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    db.commit()
    return result
