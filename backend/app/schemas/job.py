from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import AfterValidator, BaseModel, Field

from app.schemas.job_extraction import JobExtraction
from app.schemas.stage import Rung

APPLY_URL_MAX = 2048


def _http_url(value: str) -> str:
    """The apply link is opened in a tab by the Companion, so only a real http(s) URL may be stored
    (never javascript:, data: or a scheme-relative path)."""
    value = value.strip()
    if len(value) > APPLY_URL_MAX:
        raise ValueError(f"must be at most {APPLY_URL_MAX} characters")
    try:
        parts = urlsplit(value)
        host = parts.hostname
    except ValueError as exc:
        raise ValueError("must be an http(s) URL") from exc
    if parts.scheme.lower() not in ("http", "https") or not host:
        raise ValueError("must be an http(s) URL")
    return value


HttpUrlStr = Annotated[str, AfterValidator(_http_url)]


class JobCreate(BaseModel):
    raw_text: str
    source_url: str | None = None
    apply_url: HttpUrlStr | None = None


class JobPatch(BaseModel):
    source_url: str | None = None
    # The Companion saves the page it ran an application on, so the next visit matches the job.
    apply_url: HttpUrlStr | None = None


class JobIngest(BaseModel):
    extracted_json: JobExtraction
    raw_text: str | None = None
    source_url: str | None = None
    apply_url: HttpUrlStr | None = None
    source: Literal["user", "agent"] = "user"


class JobOwnership(BaseModel):
    """Viewer-relative ownership; sync off is unmarked and writable."""

    owned_here: bool = True
    owner: Literal["laptop", "bot"] | None = None
    handover: str | None = None
    pending_requests: int = 0
    # True only on your laptop, for a job it offered and still holds: the one place Keep it here
    # works. Your bot sees the same offer but cannot cancel it.
    can_keep_here: bool = False


class JobRead(BaseModel):
    id: UUID
    ownership: JobOwnership = Field(default_factory=JobOwnership)
    raw_text: str
    raw_text_hash: str
    source_url: str | None = None
    apply_url: str | None = None
    # Provenance lane — the tracker's Saved-lane rule filters on it; dropping
    # it from the projection makes that rule silently no-op.
    source: str = "user"
    # Derived newest-proposal status (transient attr; list + detail routes) —
    # drives the tracker's Saved chips and the job page's queue/promote action.
    proposal_status: str | None = None
    # Newest proposal id (same query as proposal_status) so the job page can
    # load / triage without a proposals-list round-trip.
    proposal_id: UUID | None = None
    # Who filed the newest proposal (same query): "you", an MCP client's name,
    # or None. The tracker's agent mark and the job page's pill name them.
    proposal_proposed_by: str | None = None
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
    ownership: JobOwnership = Field(default_factory=JobOwnership)
    source_url: str | None = None
    apply_url: str | None = None
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
    proposal_proposed_by: str | None = None
    # Derived, list-endpoint-only: the best base-resume score, read-only
    # (null when the job has never been scored).
    best_ats_score: float | None = None
    # Derived, list-endpoint-only (services/stage.py): the rung the job sits on (its newest
    # application's, else the job's own), plus the open session behind a `gaps` rung with
    # its resolved/listed counts.
    stage: Rung = "saved"
    open_session_id: UUID | None = None
    gaps_done: int = 0
    gaps_total: int = 0
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
