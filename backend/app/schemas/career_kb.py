"""Pydantic schemas for the Career Knowledge Base."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.base_resume import BaseResumeDetail
from app.schemas.resume import (
    CORE_SECTION_KEYS,
    CORE_SECTION_TITLES,
    TITLE_COLLISION_MESSAGE,
    _SECTION_KEY_RE,
    ContactInfo,
    SkillGroup,
)

KB_KINDS = {"experience", "project", "education", "certification", "extra"}
KB_STATUSES = {"ongoing", "completed", "archived"}
KB_POINT_STATES = {"draft", "approved", "retired"}


def _validate_extra_identity(
    section_key: str | None,
    section_type: str | None,
    section_title: str | None,
) -> tuple[str, str, str]:
    if not section_key or not _SECTION_KEY_RE.match(section_key):
        raise ValueError(
            "section_key must be a lowercase slug (alphanumeric, '_' or '-'), e.g. 'publications'"
        )
    if section_key.casefold() in CORE_SECTION_KEYS:
        raise ValueError(
            f"section_key {section_key!r} collides with the core '{section_key.casefold()}' section"
        )
    if section_type not in ("entries", "bullets"):
        raise ValueError("section_type must be either 'entries' or 'bullets'")
    if not section_title or not section_title.strip():
        raise ValueError("section_title must be non-empty")
    if section_title.strip().casefold() in CORE_SECTION_TITLES:
        raise ValueError(TITLE_COLLISION_MESSAGE)
    return section_key, section_type, section_title.strip()


# --- Entity write models ---------------------------------------------------


class KBEntityCreate(BaseModel):
    kind: str
    title: str
    org: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    status: str = "completed"
    detail: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None
    section_key: str | None = None
    section_type: Literal["entries", "bullets"] | None = None
    section_title: str | None = None

    @field_validator("kind")
    @classmethod
    def _kind_valid(cls, v: str) -> str:
        if v not in KB_KINDS:
            raise ValueError(f"kind must be one of {sorted(KB_KINDS)}")
        return v

    @field_validator("status")
    @classmethod
    def _status_valid(cls, v: str) -> str:
        if v not in KB_STATUSES:
            raise ValueError(f"status must be one of {sorted(KB_STATUSES)}")
        return v

    @field_validator("title")
    @classmethod
    def _title_nonempty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("title must be non-empty")
        return stripped

    @model_validator(mode="after")
    def _validate_extra_fields(self) -> "KBEntityCreate":
        if self.kind == "extra":
            s_key = self.section_key or self.detail.get("section_key")
            s_type = self.section_type or self.detail.get("section_type")
            s_title = self.section_title or self.detail.get("section_title")
            k, t, title_ = _validate_extra_identity(s_key, s_type, s_title)
            self.section_key = k
            self.section_type = t  # type: ignore[assignment]
            self.section_title = title_
            self.detail["section_key"] = k
            self.detail["section_type"] = t
            self.detail["section_title"] = title_
        else:
            if (
                self.section_key is not None
                or self.section_type is not None
                or self.section_title is not None
            ):
                raise ValueError(
                    "section_key, section_type, and section_title are only valid when kind == 'extra'"
                )
        return self


class KBEntityPatch(BaseModel):
    kind: str | None = None
    title: str | None = None
    org: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    status: str | None = None
    detail: dict[str, Any] | None = None
    notes: str | None = None
    section_key: str | None = None
    section_type: Literal["entries", "bullets"] | None = None
    section_title: str | None = None

    @field_validator("kind")
    @classmethod
    def _kind_valid(cls, v: str | None) -> str | None:
        # Explicit null on a NOT NULL column is invalid; only omission is allowed.
        if v is None:
            raise ValueError("kind may not be null")
        if v not in KB_KINDS:
            raise ValueError(f"kind must be one of {sorted(KB_KINDS)}")
        return v

    @field_validator("status")
    @classmethod
    def _status_valid(cls, v: str | None) -> str | None:
        if v is None:
            raise ValueError("status may not be null")
        if v not in KB_STATUSES:
            raise ValueError(f"status must be one of {sorted(KB_STATUSES)}")
        return v

    @field_validator("title")
    @classmethod
    def _title_nonempty(cls, v: str | None) -> str | None:
        if v is None:
            raise ValueError("title may not be null")
        stripped = v.strip()
        if not stripped:
            raise ValueError("title must be non-empty")
        return stripped

    @model_validator(mode="after")
    def _validate_extra_patch(self) -> "KBEntityPatch":
        if self.kind is not None and self.kind != "extra":
            if (
                self.section_key is not None
                or self.section_type is not None
                or self.section_title is not None
            ):
                raise ValueError(
                    "section_key, section_type, and section_title are only valid when kind == 'extra'"
                )
        if self.section_key is not None:
            if not _SECTION_KEY_RE.match(self.section_key):
                raise ValueError("section_key must be a lowercase slug")
            if self.section_key.casefold() in CORE_SECTION_KEYS:
                raise ValueError(
                    f"section_key {self.section_key!r} collides with core section"
                )
        if self.section_type is not None and self.section_type not in ("entries", "bullets"):
            raise ValueError("section_type must be either 'entries' or 'bullets'")
        if self.section_title is not None:
            if not self.section_title.strip():
                raise ValueError("section_title must be non-empty")
            if self.section_title.strip().casefold() in CORE_SECTION_TITLES:
                raise ValueError(TITLE_COLLISION_MESSAGE)
        return self


# --- Point write models ----------------------------------------------------


class KBPointCreate(BaseModel):
    text: str
    tags: list[str] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def _text_nonempty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("text must be non-empty")
        return stripped


class KBCaptureRequest(BaseModel):
    text: str
    entity_id: UUID | None = None

    @field_validator("text")
    @classmethod
    def _text_nonempty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("text must be non-empty")
        return stripped


class KBCaptureResponse(BaseModel):
    entity_id: UUID
    entity_title: str
    point_ids: list[UUID]


class KBPointPatch(BaseModel):
    text: str | None = None
    state: str | None = None
    tags: list[str] | None = None
    entity_id: UUID | None = None

    @field_validator("state")
    @classmethod
    def _state_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in KB_POINT_STATES:
            raise ValueError(f"state must be one of {sorted(KB_POINT_STATES)}")
        return v

    @field_validator("text")
    @classmethod
    def _text_nonempty(cls, v: str | None) -> str | None:
        if v is None:
            return v
        stripped = v.strip()
        if not stripped:
            raise ValueError("text must be non-empty")
        return stripped


class KBPointBulkState(BaseModel):
    """Mass approve/retire. draft is not bulk-legal — un-reviewing in bulk
    makes no sense, same narrowness as proposals bulk-transition."""

    ids: list[UUID] = Field(min_length=1, max_length=500)
    state: Literal["approved", "retired"]


class KBPointBulkResult(BaseModel):
    id: UUID
    ok: bool
    state: str | None = None
    detail: str | None = None


class KBPointBulkResponse(BaseModel):
    results: list[KBPointBulkResult]


# --- Read models -----------------------------------------------------------


class KBUsageOut(BaseModel):
    resume_key: str
    section: str
    ported_text: str
    ported_at: datetime
    drifted: bool
    # to_resume | from_source | None (legacy rows, treated as placements)
    direction: str | None = None


class KBPointOut(BaseModel):
    id: UUID
    entity_id: UUID
    text: str
    state: str
    origin: str
    origin_detail: str | None = None
    provenance: str | None = None
    source_document_id: UUID | None = None
    tags: list[str] = Field(default_factory=list)
    merge_sources: list[Any] | None = None
    approved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    usage: list[KBUsageOut] = Field(default_factory=list)


class KBDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    mime: str | None = None
    size_bytes: int
    ingest_status: str
    ingest_summary: str | None = None
    created_at: datetime


class KBTimelineEvent(BaseModel):
    ts: datetime
    type: str
    label: str


class KBEntitySummary(BaseModel):
    id: UUID
    kind: str
    title: str
    org: str | None = None
    status: str
    origin: str | None = None
    origin_detail: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    point_count: int
    draft_count: int
    document_count: int
    last_activity: datetime
    section_key: str | None = None
    section_type: str | None = None
    section_title: str | None = None


class KBEntityDetail(KBEntitySummary):
    detail: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None
    points: list[KBPointOut] = Field(default_factory=list)
    documents: list[KBDocumentOut] = Field(default_factory=list)
    timeline: list[KBTimelineEvent] = Field(default_factory=list)


class KBEntityDuplicateHint(BaseModel):
    id: UUID
    title: str
    org: str | None = None


class KBEntityCreateResponse(KBEntityDetail):
    possible_duplicates: list[KBEntityDuplicateHint] = Field(default_factory=list)


class KBEntityMergeRequest(BaseModel):
    """Fold the path entity into `target_id`. Web-only on purpose — the MCP
    surface gains no destructive tools, so there is no `kb_merge_entities`."""

    target_id: UUID


class KBInboxPoint(KBPointOut):
    entity_title: str
    entity_kind: str


# --- Singleton profile ----------------------------------------------------


class KBProfilePatch(BaseModel):
    contact: ContactInfo | None = None
    summary: str | None = None
    skills: list[SkillGroup] | None = None
    notes: str | None = None

    @field_validator("contact", "summary", "skills", "notes")
    @classmethod
    def _not_null(cls, value):
        if value is None:
            raise ValueError("profile fields may not be null; omit unchanged fields")
        return value


class KBProfileOut(BaseModel):
    contact: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    skills: list[SkillGroup] = Field(default_factory=list)
    notes: str = ""
    updated_at: datetime


class KBDocumentIngestResponse(BaseModel):
    """Result of document-first ingest: the (matched or created) entity + doc + points."""

    entity_id: UUID
    entity_title: str
    entity_kind: str
    created_entity: bool
    point_count: int
    document: KBDocumentOut


# --- Port to base resume ---------------------------------------------------


class KBPortItem(BaseModel):
    entity_id: UUID
    point_ids: list[UUID] = Field(default_factory=list)  # empty = all approved points
    section_key: str | None = None

    @field_validator("section_key")
    @classmethod
    def _validate_section_key(cls, v: str | None) -> str | None:
        if v is not None:
            if not _SECTION_KEY_RE.match(v):
                raise ValueError("section_key must be a lowercase slug")
            if v.casefold() in CORE_SECTION_KEYS:
                raise ValueError(
                    f"section_key {v!r} collides with the core '{v.casefold()}' section"
                )
        return v


class KBPortRequest(BaseModel):
    target_slug: str
    items: list[KBPortItem] = Field(default_factory=list)
    skill_categories: list[str] = Field(default_factory=list)
    include_profile_summary: bool = False


class KBPortItemReport(BaseModel):
    entity_id: UUID
    ported_point_ids: list[UUID] = Field(default_factory=list)
    skipped_duplicate_point_ids: list[UUID] = Field(default_factory=list)
    created_entry: bool = False


class KBPortReport(BaseModel):
    items: list[KBPortItemReport] = Field(default_factory=list)
    skills_merged: list[str] = Field(default_factory=list)


class KBPortResponse(BaseModel):
    resume: BaseResumeDetail
    report: KBPortReport


# --- Adapt (AI-assisted port) ------------------------------------------------

KB_ADAPT_ACTIONS = {"kept", "rewritten", "merged", "replace"}


class KBAdaptRequest(BaseModel):
    target_slug: str
    entity_id: UUID
    point_ids: list[UUID] = Field(default_factory=list)  # empty = all approved points


class KBAdaptBullet(BaseModel):
    """One proposed resume bullet, with KB-point provenance."""

    text: str
    source_point_ids: list[UUID] = Field(default_factory=list)
    replaces_bullet_index: int | None = None  # index into the matched entry's bullets
    action: str = "kept"  # kept | rewritten | merged | replace
    reason: str | None = None


class KBAdaptDropped(BaseModel):
    point_id: UUID
    reason: str = ""


class KBAdaptProposal(BaseModel):
    """LLM proposal for adapting selected points into one base resume. Nothing persisted."""

    target_slug: str
    entity_id: UUID
    section: str
    matched_entry_index: int | None = None
    create_entry: bool = False
    existing_bullets: list[str] = Field(default_factory=list)
    bullets: list[KBAdaptBullet] = Field(default_factory=list)
    dropped: list[KBAdaptDropped] = Field(default_factory=list)


class KBAdaptApplyBullet(BaseModel):
    """A user-approved (possibly edited) bullet to apply. Provenance is mandatory."""

    text: str
    source_point_ids: list[UUID] = Field(min_length=1)
    replaces_bullet_index: int | None = None
    # Echo of the existing bullet text the client reviewed at proposal time.
    # The entry can change between adapt and apply (chat/MCP/another tab), so
    # an in-range index alone could silently overwrite an unreviewed bullet.
    replaces_text: str | None = None

    @field_validator("text")
    @classmethod
    def _strip_nonempty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("bullet text must not be empty")
        return v

    @model_validator(mode="after")
    def _replace_requires_echo(self) -> "KBAdaptApplyBullet":
        if self.replaces_bullet_index is not None and self.replaces_text is None:
            raise ValueError(
                "replaces_text is required when replaces_bullet_index is set"
            )
        return self


class KBAdaptApplyRequest(BaseModel):
    target_slug: str
    entity_id: UUID
    bullets: list[KBAdaptApplyBullet] = Field(min_length=1)


# --- Consolidation ---------------------------------------------------------


class ConsolidationReport(BaseModel):
    entities_created: int = 0
    entities_matched: int = 0
    points_approved: int = 0
    points_draft: int = 0
    duplicates_skipped: int = 0
    # CATEGORY names, one per category written. Not a skill count: two new
    # items in the same category append this once.
    skills_merged: list[str] = Field(default_factory=list)
    # The individual skills that landed in the profile — count these.
    skills_items_added: list[str] = Field(default_factory=list)
    # Entities RENAMED to a richer role title because a near-identity match said
    # the incoming entry was the fuller variant. Changing an entity the user
    # already has is a write that must be reportable, unlike the create/match
    # this path does quietly.
    #
    # RESERVED on this shape — not symmetric with the deterministic one. Only
    # experience renames, and this path resolves experience in
    # ``_resolve_family``, which cannot reach the upgrade, so consolidate()
    # leaves this empty today. The field exists so it is already here if that
    # ever changes; the shape that actually populates it is
    # DeterministicConsolidationReport.titles_upgraded.
    titles_upgraded: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ImportedBaseRead(BaseModel):
    slug: str
    display_name: str
    role_category: str
    # Free-text tag when the guess used an alias of the user's own words;
    # null means the tag IS role_category (a catalog pick).
    role_label: str | None = None
    # True = the system proposed this from resume content and the UI must ask
    # the user to confirm. False means "unknown" — undeclared, not guessed.
    proposed: bool
    render_error: str | None = None
    parse_warnings: list[str] = Field(default_factory=list)


class SkippedFileRead(BaseModel):
    filename: str
    reason: str


class ImportReport(BaseModel):
    """POST /api/kb/import — what the user must be told, plainly.

    An uploaded file becomes BOTH a base resume and Career KB content in one
    action. If the summary does not say so the KB looks like it duplicated the
    user's resumes, and trust is gone on first contact.
    """

    bases: list[ImportedBaseRead] = Field(default_factory=list)
    skipped: list[SkippedFileRead] = Field(default_factory=list)
    kb: ConsolidationReport | None = None


class ImportConsolidateRequest(BaseModel):
    """POST /api/kb/import/consolidate — optional slugs of just-minted bases.

    Omit slugs to consolidate every active base that has no port-log row yet.
    """

    slugs: list[str] | None = None


class IngestParsedSource(BaseModel):
    """One caller-parsed resume. `data` is validated as ResumeData in the
    handler so a mixed batch can return per-source 422 detail atomically."""

    # The repo's base-resume slug charset (routers/base_resumes.SLUG_RE), here
    # rather than in the handler so it shows up in OpenAPI — and so no
    # unanchored .match can let "my resume!" through.
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$")
    data: dict[str, Any]


class IngestParsedRequest(BaseModel):
    # Forbid extras for the same reason _ExtraSectionBase does: a miswired key
    # (origin_detail, say — provenance is a header now) must be a hard error,
    # not a silent drop.
    model_config = ConfigDict(extra="forbid")

    sources: list[IngestParsedSource] = Field(min_length=1, max_length=20)


class IngestParsedEntity(BaseModel):
    id: UUID
    kind: str
    title: str
    org: str | None = None
    created: bool


class IngestParsedPoint(BaseModel):
    id: UUID
    entity_id: UUID
    text: str


class IngestParsedReport(BaseModel):
    """POST /api/kb/ingest-parsed — ids-bearing, no base-resume minting.

    ``points_created`` counts DRAFT rows written; nothing on this path is
    approved. ``duplicates_skipped`` counts source bullets that did not become
    a point (collapsed in the batch, or already on the entity in any state).
    """

    entities: list[IngestParsedEntity] = Field(default_factory=list)
    points: list[IngestParsedPoint] = Field(default_factory=list)
    entities_created: int = 0
    entities_matched: int = 0
    points_created: int = 0
    duplicates_skipped: int = 0
    skills_merged: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class KBContextResponse(BaseModel):
    """GET /api/kb/context — the career grounding pair (chat's get_career_context
    over REST): composed approved-points resume + beyond-the-resume memory."""

    resume: dict[str, Any]
    memory: str


class ExtraSectionPreset(BaseModel):
    """Canonical extra section preset schema."""

    key: str
    title: str
    type: Literal["entries", "bullets"]
    match: list[str] = Field(default_factory=list)
