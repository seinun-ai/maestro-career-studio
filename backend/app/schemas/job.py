from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.job_extraction import JobExtraction


class JobCreate(BaseModel):
    raw_text: str
    source_url: str | None = None


class JobPatch(BaseModel):
    source_url: str | None = None


class JobIngest(BaseModel):
    extracted_json: JobExtraction
    raw_text: str | None = None
    source_url: str | None = None
    source: Literal["user", "agent"] = "user"


class JobRead(BaseModel):
    id: UUID
    raw_text: str
    raw_text_hash: str
    source_url: str | None = None
    # Provenance lane — the tracker's Saved-lane rule filters on it; dropping
    # it from the projection makes that rule silently no-op.
    source: str = "user"
    # Derived newest-proposal status (transient attr; list + detail routes) —
    # drives the tracker's Saved chips and the job page's queue/promote action.
    proposal_status: str | None = None
    # Newest proposal id (same query as proposal_status) so the job page can
    # load / triage without a proposals-list round-trip.
    proposal_id: UUID | None = None
    extracted_json: dict[str, Any] | None = None
    title: str | None = None
    company: str | None = None
    requisition_id: str | None = None
    role_category: str | None = None
    level: str | None = None
    employment_type: str | None = None
    work_mode: str | None = None
    location: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    location_raw: str | None = None
    salary_min: Decimal | None = None
    salary_max: Decimal | None = None
    salary_period: str | None = None
    salary_currency: str | None = None
    salary_source_url: str | None = None
    work_authorization: str | None = None
    opt_accepted: str | None = None
    years_experience_min: int | None = None
    years_experience_max: int | None = None
    disqualifying_for_opt: bool | None = None
    extracted_at: datetime | None = None
    created_at: datetime
    # Transient (never a column): set by create/ingest when dedup returned an
    # existing row, so the UI can say "already tracked" instead of pretending a
    # fresh extraction happened.
    already_existed: bool = False

    model_config = {"from_attributes": True}


class JobSummary(BaseModel):
    """Thin job projection for list endpoints — direct ORM column projection,
    no raw_text / extracted_json. Detail/export keep JobRead / JobExportRow."""

    id: UUID
    source_url: str | None = None
    # Provenance lane — the tracker's Saved-lane rule filters on it; dropping
    # it from the list projection makes that rule silently no-op.
    source: str = "user"
    company: str | None = None
    title: str | None = None
    requisition_id: str | None = None
    # Derived, list-endpoint-only (transient attr, like Job.already_existed):
    # the job's NEWEST proposal status, so the tracker's Saved lane can show
    # Declined/Queued/Proposed instead of a flat "Saved" for hunted jobs.
    proposal_status: str | None = None
    proposal_id: UUID | None = None
    role_category: str | None = None
    level: str | None = None
    employment_type: str | None = None
    work_mode: str | None = None
    location: str | None = None
    country: str | None = None
    salary_min: Decimal | None = None
    salary_max: Decimal | None = None
    salary_period: str | None = None
    salary_currency: str | None = None
    salary_source_url: str | None = None
    work_authorization: str | None = None
    opt_accepted: str | None = None
    disqualifying_for_opt: bool | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class JobSkillRead(BaseModel):
    skill_name: str
    skill_category: str
    requirement_level: str
    model_config = {"from_attributes": True}


class JobExportRow(JobRead):
    skills: list[JobSkillRead] = []


class QuickTailorRequest(BaseModel):
    base_resume: str


class QuickTailorCompare(BaseModel):
    before: float
    after: float


class QuickTailorResponse(BaseModel):
    application_id: UUID | None = None
    session_id: UUID
    compare: QuickTailorCompare | None = None
    applied: list[str] = []
    pdf_ready: bool = False
    nothing_to_tailor: bool = False
    health_warning: str | None = None
