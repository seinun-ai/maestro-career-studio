from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import AliasChoices, BaseModel, Field, field_validator

from app.schemas.job import JobRead
from app.schemas.resume_edit import ResumeEdit

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
    applied_at: datetime | None = None
    notes: str | None = None
    referral_id: UUID | None = None
    formatting: dict[str, Any] | None = None
    template_id: str | None = None

    @field_validator("status")
    @classmethod
    def _known_status(cls, value: str | None) -> str | None:
        if value is not None and value not in ALLOWED_STATUSES:
            raise ValueError(
                f"Unknown status {value!r}; allowed: {', '.join(ALLOWED_STATUSES)}"
            )
        return value


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
    # Present on PATCH /edits responses: per-op echo of which full-array entries
    # were touched (index includes enabled:false rows omitted from PDF render).
    applied: list[dict[str, Any]] | None = None


class RenderResult(BaseModel):
    tex_path: str
    pdf_path: str
