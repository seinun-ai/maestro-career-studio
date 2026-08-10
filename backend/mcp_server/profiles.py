"""MAESTRO_CS_MCP_PROFILE allowlists — which MCP tools register per session.

Default ``full`` keeps today's complete tool surface. Scoped profiles shrink the
listing for hunt / apply / explore / templates / career workflows so focused
sessions are not paying for unrelated definitions.
"""
from __future__ import annotations

import os

VALID_PROFILES = frozenset(
    {"full", "hunt", "apply", "explore", "templates", "career"}
)

# Job search + propose (no browser fill / PDF upload / evidence).
HUNT_TOOLS = frozenset({
    "get_job_search_brief",
    "list_referrals",
    "find_job_by_url",
    "store_extracted_jd",
    "list_jobs",
    "get_job",
    "score_ats",
    "list_base_resumes",
    "get_base_resume",
    "list_applications",
    "export_jobs",
    "propose_application",
    "list_proposals",
    "get_proposal",
    "request_decision",
    "record_decision",
    "record_triage",
    "resume_proposal",
    "report_failure",
})

# Execute applications (tailor → PDF → autofill → ledger through submit).
APPLY_TOOLS = frozenset({
    "find_job_by_url",
    "store_extracted_jd",
    "get_job",
    "list_jobs",
    "get_application",
    "list_applications",
    "list_base_resumes",
    "get_base_resume",
    "list_referrals",
    "list_qa_entries",
    "get_career_context",
    "get_autofill_profile",
    "get_job_search_brief",
    "score_ats",
    "compare_ats",
    "create_tailoring_session",
    "list_tailoring_sessions",
    "get_tailoring_session",
    "close_tailoring_session",
    "resolve_gaps",
    "tailor_session",
    "tailor_application",
    "edit_application",
    "update_application",
    "generate_qa_answers",
    "generate_cover_letter",
    "render_pdf",
    "get_rendered_pdf",
    "get_rendered_pdf_page_image",
    "prepare_application_pdf_upload",
    "run_health_check",
    "get_health_report",
    "propose_application",
    "list_proposals",
    "get_proposal",
    "record_decision",
    "record_triage",
    "request_decision",
    "resume_proposal",
    "get_final_review",
    "record_consent",
    "attach_evidence",
    "attach_evidence_file",
    "mark_submitted",
    "report_failure",
})

EXPLORE_TOOLS = frozenset({
    "explore_top_skills",
    "explore_skill_heatmap",
    "explore_role_mix_over_time",
    "explore_fit_distribution",
    "explore_gap_frequency",
    "explore_ats_over_time",
    "explore_tailoring_lift",
    "list_jobs",
    "get_job",
    "list_applications",
    "get_job_search_brief",
})

TEMPLATES_TOOLS = frozenset({
    "list_templates",
    "get_template",
    "create_template_draft",
    "update_template_draft",
    "validate_template",
    "render_pdf",
    "get_rendered_pdf",
    "get_rendered_pdf_page_image",
    "list_base_resumes",
    "get_base_resume",
    "run_health_check",
    "get_health_report",
})

# Curate the Career KB itself: read with IDs, then capture/correct. The only
# profile with KB writes — hunt/apply/explore/templates stay read-only there.
CAREER_TOOLS = frozenset({
    "get_career_context",
    "get_career_export",
    "kb_list_entities",
    "kb_get_entity",
    "kb_list_points",
    "kb_capture",
    "kb_edit_point",
    "kb_create_entity",
    "kb_edit_entity",
    "kb_edit_profile",
})

# None => register every decorated tool (today's default).
PROFILE_ALLOWLISTS: dict[str, frozenset[str] | None] = {
    "full": None,
    "hunt": HUNT_TOOLS,
    "apply": APPLY_TOOLS,
    "explore": EXPLORE_TOOLS,
    "templates": TEMPLATES_TOOLS,
    "career": CAREER_TOOLS,
}


def get_profile(name: str | None = None) -> str:
    raw = (
        name
        if name is not None
        else (
            os.environ.get("MAESTRO_CS_MCP_PROFILE")
            or os.environ.get("CAREER_STUDIO_MCP_PROFILE")
            or "full"
        )
    )
    profile = (raw or "full").strip().lower()
    if profile not in VALID_PROFILES:
        raise ValueError(
            f"Unknown MAESTRO_CS_MCP_PROFILE={profile!r}; "
            f"expected one of {sorted(VALID_PROFILES)}"
        )
    return profile


def allowed_tools(profile: str | None = None) -> frozenset[str] | None:
    """Return the allowlist for ``profile``, or None when every tool is allowed."""
    return PROFILE_ALLOWLISTS[get_profile(profile)]


def apply_profile_filter(mcp, profile: str | None = None) -> str:
    """Remove registered tools that are outside the active profile. Returns profile name."""
    active = get_profile(profile)
    allow = PROFILE_ALLOWLISTS[active]
    if allow is None:
        return active
    manager = mcp._tool_manager
    for name in list(manager._tools):
        if name not in allow:
            del manager._tools[name]
    return active
