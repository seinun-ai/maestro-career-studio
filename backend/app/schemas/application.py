from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import AliasChoices, AwareDatetime, BaseModel, Field, field_validator

from app.schemas.job import JobOwnership, JobRead
from app.schemas.resume_edit import ResumeEdit
from app.schemas.stage import Rung

# The one status vocabulary. The frontend renders exactly these; PATCH rejects
# anything else so no writer (web, MCP, raw REST) can invent a status the
# tracker cannot display or filter.
ALLOWED_STATUSES = (
    "draft",
    "applied",
    "interviewing",
    "offered",
    "accepted",
    "rejected",
    "withdrawn",
)


class ApplicationFromBase(BaseModel):
    job_id: UUID
    base_resume: str
    ops: list[ResumeEdit] = []
    user_prompt: str | None = None
    application_id: UUID | None = None


class ApplicationPatch(BaseModel):
    customized_json: Any = None
    status: str | None = None
    # AwareDatetime, not datetime: the column is UTCDateTime, which refuses a
    # naive value at flush (a 500). Refusing it here makes it a 422 instead.
    applied_at: AwareDatetime | None = None
    notes: str | None = None
    referral_id: UUID | None = None
    formatting: dict[str, Any] | None = None
    template_id: str | None = None
    # The row's updated_at the caller computed its edit from (a revert from the diff). When given and the row has
    # moved since, the PATCH is refused with a 409 and writes nothing. Never stored.
    expected_updated_at: AwareDatetime | None = None
    # Who said the status changed when it is not the caller: "mail" when an agent read it from the user's job
    # email (MCP update_application from_email). Recorded on the status event only; never a column.
    status_source: Literal["mail"] | None = None

    @field_validator("status")
    @classmethod
    def _known_status(cls, value: str | None) -> str | None:
        if value is not None and value not in ALLOWED_STATUSES:
            raise ValueError(
                f"Unknown status {value!r}; allowed: {', '.join(ALLOWED_STATUSES)}"
            )
        return value


class ResumeDiffRead(BaseModel):
    """GET /applications/{id}/resume-diff: the hunks, the gap analysis they were attributed from, and the
    application's updated_at the diff was computed against (a revert sends it back as expected_updated_at)."""

    hunks: list[dict[str, Any]]
    session_id: str | None
    updated_at: datetime


class ApplicationSummary(BaseModel):
    """Thin application projection for the list endpoint — no customized_json.
    Detail keeps ApplicationDetail. Job display fields are joined in by the
    router so the tracker needs no second query."""

    id: UUID
    job_id: UUID
    base_resume: str
    source: str = "user"
    status: str | None = None
    applied_at: datetime | None = None
    referral_id: UUID | None = None
    created_at: datetime
    job_title: str | None = None
    job_company: str | None = None
    job_location: str | None = None
    # The job's ownership as the viewer reads it, in the job list's shape; sync off is unmarked.
    ownership: JobOwnership = Field(default_factory=JobOwnership)
    # The base resume's own name, joined like the job fields. Archived and
    # soft-deleted rows are included, since the application outlives both.
    # Null when it has none.
    base_resume_name: str | None = None
    # List-endpoint-only, read-only: the newest tailored score, else the base
    # row for this resume; null when neither exists (never scored on read).
    ats_score: float | None = None
    # List-endpoint-only, read-only (services/stage.py): the rung this application sits on,
    # the open session behind a `gaps` rung with its resolved/listed counts, and whether a
    # draft or a PDF exists, so the wire needs no customized_json to tell.
    has_draft: bool = False
    has_pdf: bool = False
    stage: Rung = "saved"
    open_session_id: UUID | None = None
    gaps_done: int = 0
    gaps_total: int = 0
    # List-endpoint-only, read-only (`application_status.status_since`): when the current status began, from the
    # status log; null when the log holds no change into it (a status older than the log).
    status_since: datetime | None = None

    model_config = {"from_attributes": True}


class ApplicationRead(BaseModel):
    id: UUID
    job_id: UUID
    base_resume: str
    status: str | None = None
    applied_at: datetime | None = None
    notes: str | None = None
    customized_json: dict[str, Any] | None = None
    pdf_path: str | None = None
    tex_path: str | None = None
    artifact_dir: str | None = None
    referral_id: UUID | None = None
    user_prompt: str | None = None
    # Serialized as `formatting`, read from the ORM `formatting_json` column.
    formatting: dict[str, Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("formatting", "formatting_json"),
    )
    template_id: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class ApplicationDetail(ApplicationRead):
    job: JobRead | None = None
    # The base resume's own name, joined like the job fields. Archived and
    # soft-deleted rows are included, since the application outlives both.
    # Null when it has none.
    base_resume_name: str | None = None
    # Present on PATCH /edits responses: per-op echo of which full-array entries
    # were touched (index includes enabled:false rows omitted from PDF render).
    applied: list[dict[str, Any]] | None = None


class RenderResult(BaseModel):
    tex_path: str
    pdf_path: str
    resolved_template_id: str | None = None
    resolved_engine: str | None = None
    # True only when an EXPLICIT template_id was passed and the resolved id
    # differs (stale id → default, or TeX absent → Typst). A substitution of the
    # resume's/application's PERSISTED choice does not set it: render_note is
    # the only signal on that path.
    template_fallback: bool | None = None
    # Non-null ONLY when the engine was substituted because TeX is absent;
    # says why, in the words the user sees.
    render_note: str | None = None
    # Where the visible copy of the PDF sits in the resumes folder; null when there is none.
    copy_path: str | None = None
