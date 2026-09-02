from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.resume import ResumeData


class BaseResumeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    display_name: str | None = None
    role_category: str
    role_label: str | None = None
    updated_at: datetime
    pdf_rendered_at: datetime | None = None
    # Both drive the gallery card: render_error picks the thumbnail state,
    # archived_at the dimmed/Archived treatment.
    render_error: str | None = None
    archived_at: datetime | None = None


class BaseResumeDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    display_name: str | None = None
    role_category: str
    role_label: str | None = None
    data: ResumeData
    pdf_path: str | None = None
    tex_path: str | None = None
    pdf_rendered_at: datetime | None = None
    formatting: dict | None = None
    template_id: str | None = None
    resolved_template_id: str | None = None
    resolved_engine: str | None = None
    template_fallback: bool | None = None
    pdf_pages: int | None = None
    render_error: str | None = None
    updated_at: datetime
    archived_at: datetime | None = None
    # Present on PATCH /edits responses — which entries the ops actually touched.
    applied: list[dict] | None = None
    # Present on POST /import responses — list rows the parser had to drop
    # (see kb_consolidation._validate_with_salvage); empty means a clean parse.
    parse_warnings: list[str] | None = None


class BaseResumeCreate(BaseModel):
    slug: str
    display_name: str | None = None
    data: ResumeData
    # Optional: absent means "not declared yet" -> stored as "unknown" and shown
    # as such. An explicitly supplied value is VALIDATED (422), never coerced —
    # normalize() maps anything unrecognized to "other", which is right for LLM
    # extraction but would make a typo indistinguishable from a deliberate
    # "Other" for a human-supplied field.
    role_category: str | None = None
    role_label: str | None = None


class BaseResumeUpdate(BaseModel):
    display_name: str | None = None
    data: ResumeData
    template_id: str | None = None
    formatting: dict | None = None


class BaseResumeDuplicate(BaseModel):
    new_slug: str
    new_display_name: str | None = None


class BaseResumeFromKB(BaseModel):
    """POST /base-resumes/from-kb — build a role-targeted base from the KB.

    `slug` remains accepted for explicit callers. Suggested-base clients may
    omit it when they provide `role_category`; the server allocates a collision-
    free internal slug across active and soft-deleted rows.

    `entity_ids` is REQUIRED and may be empty. It is not optional-with-a-default
    on purpose: omitting it would have to mean "everything", and composing the
    whole knowledge base is a master view, not a targeted base — the exact
    confusion this endpoint exists to avoid.
    """

    slug: str | None = None
    display_name: str | None = None
    role_category: str | None = None
    role_label: str | None = None
    entity_ids: list[UUID]
    # The KB summary is written for the whole career; on a base aimed at one
    # role it is usually wrong. Blank-and-visible beats plausible-and-wrong, so
    # it is dropped unless asked for.
    include_summary: bool = False
    # A reviewed summary from POST /from-kb/plan. Takes precedence over
    # include_summary, which only ever carries the whole-career KB summary.
    summary: str | None = None


class BaseFromKBPlanRequest(BaseModel):
    """POST /base-resumes/from-kb/plan — propose a selection, persist nothing."""

    role_category: str
    # Free instruction: what to emphasise, what to leave off, and the tone of
    # the drafted summary. Empty means "just pick what fits the role".
    instruction: str = ""


class ExcludedEntityRead(BaseModel):
    id: UUID
    title: str
    reason: str


class BaseFromKBPlanRead(BaseModel):
    """A proposal the user reviews before anything is created.

    `include` is a starting selection, not a decision — the client presents it
    as pre-ticked checkboxes. Bullet wording is untouched by design.
    """

    include: list[UUID]
    exclude: list[ExcludedEntityRead]
    summary: str


class BaseResumeIdentity(BaseModel):
    """PATCH /{slug}/identity — metadata only.

    Deliberately separate from the full PUT, which rewrites data_json, records a
    ResumeVersion, rewrites the on-disk JSON and recompiles the PDF. Declaring a
    role must do none of that.
    """

    role_category: str | None = None
    role_label: str | None = None
    display_name: str | None = None


class BaseResumePortProject(BaseModel):
    target_slug: str
    project_index: int


class BaseResumePortProjectResult(BaseModel):
    target_slug: str
    project_index: int


class BaseResumeProposeRequest(BaseModel):
    """POST /{slug}/propose — an instruction against the resume, persist nothing."""

    instruction: str


class BaseResumeProposeRead(BaseModel):
    """A proposal the user applies (through PATCH /edits) or discards.

    `ops` is the validated, dry-run op list — applying it cannot fail for a
    reason the model could have known. `notes` carries the prose half: advice,
    pivot ideas, or the facts the model needed and would not invent.
    """

    summary: str
    notes: str
    ops: list[dict]
    ops_count: int
