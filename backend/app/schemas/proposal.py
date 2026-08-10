from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.job import JobSummary


class ProposalCreate(BaseModel):
    job_id: UUID
    application_id: UUID | None = None
    referral_id: UUID | None = None
    fit: dict[str, Any] | None = None
    plan: dict[str, Any] | None = None


class ConsentPayload(BaseModel):
    channel: Literal["chat", "slack", "frontend", "mcp"]
    note: str | None = None


class ProposalTransition(BaseModel):
    status: Literal[
        "pending_review", "needs_decision", "accepted", "approved", "submitted",
        "rejected", "needs_human", "submission_uncertain",
    ]
    consent: ConsentPayload | None = None
    # True when the USER stated the submission happened (no receipt evidence);
    # required for the submission_uncertain -> submitted edge. Recorded as an
    # append-only ConsentEvent(action="submitted") so the ledger distinguishes
    # attested from receipt-verified submits.
    attested: bool = False
    reason: str | None = None
    fit: dict[str, Any] | None = None
    # Late application linking: proposals filed before tailoring (needs_decision
    # lane) have no application yet; the decision round supplies it. Only
    # accepted while the proposal has none — never a relink.
    application_id: UUID | None = None
    intervention: dict[str, Any] | None = None


class ProposalBulkTransition(BaseModel):
    """Mass triage (design §3b). Only accepted|rejected are bulk-legal —
    mass-approve/mass-submit must stay impossible; the final per-application
    consent boundary is untouched."""

    ids: list[UUID]
    status: Literal["accepted", "rejected"]
    consent: ConsentPayload
    reason: str | None = None


class ProposalBulkResult(BaseModel):
    id: UUID
    ok: bool
    status: str | None = None
    detail: str | None = None


class ProposalBulkResponse(BaseModel):
    results: list[ProposalBulkResult]


class ProposalReasonBody(BaseModel):
    reason: str | None = None
    intervention: dict[str, Any] | None = None


class AssertOpenProposalBody(BaseModel):
    op: Literal["prepare", "attach_evidence", "record_consent", "mark_submitted"] = "prepare"


class ProposalRead(BaseModel):
    id: UUID
    job_id: UUID
    application_id: UUID | None = None
    referral_id: UUID | None = None
    status: str
    fit_json: dict[str, Any] | None = None
    plan_json: dict[str, Any] | None = None
    evidence_json: list[dict[str, Any]] | None = None
    intervention_json: dict[str, Any] | None = None
    reason: str | None = None
    expires_at: datetime | None = None
    cap_reserved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    job: JobSummary

    model_config = {"from_attributes": True}


class ProposalListResponse(BaseModel):
    items: list[ProposalRead]
    # Count over the full filtered set, before limit/offset (0 pre-pagination
    # responses never carried it, so it defaults rather than requires).
    total: int = 0


class ApplicationSummaryForProposal(BaseModel):
    id: UUID
    status: str | None = None
    pdf_ready: bool = False

    model_config = {"from_attributes": True}


class ProposalDetail(ProposalRead):
    application: ApplicationSummaryForProposal | None = None
    qa_entries: list[dict[str, Any]] = []

    model_config = {"from_attributes": True}


class ProposalCapStatus(BaseModel):
    max_per_day: int
    reserved_last_24h: int
    remaining: int


class ProposalFunnelResponse(BaseModel):
    captured: int = 0
    proposed: int = 0
    accepted: int = 0
    approved: int = 0
    cap: ProposalCapStatus | None = None
    submitted: int = 0
    interviewing: int = 0
    rejected_proposals: int = 0
    needs_human: int = 0
    expired: int = 0
