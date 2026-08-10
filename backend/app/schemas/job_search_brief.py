from typing import Any

from pydantic import BaseModel


class BriefWorkAuth(BaseModel):
    authorized_to_work: str | None = None
    requires_sponsorship: str | None = None


class BriefProfile(BaseModel):
    city: str | None = None
    state: str | None = None
    country: str | None = None
    willing_to_relocate: str | None = None
    work_auth: BriefWorkAuth


class BriefReferral(BaseModel):
    company: str
    careers_url: str
    has_contact: bool


class RoleCategoryCount(BaseModel):
    role_category: str
    count: int


class BriefWindows(BaseModel):
    """Provenance labels: the time window each aggregation block actually
    summarizes. The aggregations are additive siblings of the arrays they
    describe (no array reshape), so an agent can tell the all-time market
    aggregates apart from the 30-day capture ledger instead of reading them
    as equally current."""

    role_mix: str
    top_skills: str
    build_areas: str
    captured_last_30_days: str


class BriefCapStatus(BaseModel):
    max_per_day: int
    reserved_last_24h: int
    remaining: int


class BriefAutoApply(BaseModel):
    """Hunt guardrails up front (G2, 2026-08-01) so a run never burns
    extraction on a blocklisted company or discovers the caps by 409."""

    company_blocklist: list[str]
    max_proposals_per_run: int
    cap: BriefCapStatus


class JobSearchBriefResponse(BaseModel):
    """Server-composed context brief for an agentic job-search session.

    The reused aggregations (base_resumes, role_mix, top_skills, build_areas)
    keep their producing services' row shapes — those services own the schema
    and are covered by their own tests; the brief passes them through.
    job_preferences passes the typed setting through verbatim for the same
    reason (schemas/job_preferences.py owns that shape).
    """

    generated_at: str
    profile: BriefProfile
    persona: str
    job_preferences: dict[str, Any]
    auto_apply: BriefAutoApply
    base_resumes: list[dict[str, Any]]
    role_mix: list[dict[str, Any]]
    top_skills: list[dict[str, Any]]
    build_areas: list[dict[str, Any]]
    referrals: list[BriefReferral]
    captured_last_30_days: list[RoleCategoryCount]
    windows: BriefWindows
    warnings: list[str]
