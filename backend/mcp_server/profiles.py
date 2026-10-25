"""The tool sets: which MCP tools each /mcp/{set} endpoint (or MAESTRO_CS_MCP_PROFILE) lists.

Each set is one job in the user's own words, in journey order: profile, hunt, tailor,
apply, track, templates, and full (every tool). A focused session pays only for the
definitions its job needs; what each set holds is in mcp_server.orientation.
"""
from __future__ import annotations

import os

# You, set up and kept current: career history (the only KB writes), base resumes with
# their anchors, edits and undo, the health check, rendering, and every fact Setup asks
# for. Onboarding finishes here without tailoring or job tools.
PROFILE_TOOLS = frozenset({
    "get_setup_status",
    "get_career_context",
    "get_career_export",
    "get_job_search_brief",
    "kb_ingest_resume",
    "kb_add_points",
    "kb_capture",
    "kb_approve_points",
    "kb_retire_points",
    "kb_combine_points",
    "kb_groom_entity",
    "kb_create_entity",
    "kb_edit_entity",
    "kb_edit_point",
    "kb_edit_profile",
    "kb_get_entity",
    "kb_list_entities",
    "kb_list_points",
    "kb_sync_base",
    "list_base_resumes",
    "get_base_resume",
    "create_base_resume_from_kb",
    "set_base_resume_identity",
    "edit_base_resume",
    "archive_base_resume",
    "unarchive_base_resume",
    "list_resume_versions",
    "restore_resume_version",
    "render_pdf",
    "get_rendered_pdf",
    "run_health_check",
    "get_health_report",
    "judge_health_bullets",
    "waive_health_gate",
    "get_autofill_profile",
    "set_autofill_profile",
    "set_job_preferences",
    "set_markets",
    "set_persona",
})

# Finding jobs: the brief, capture, scoring and proposals; no tailoring, no submit power.
HUNT_TOOLS = frozenset({
    "get_setup_status",
    "get_job_search_brief",
    "sync_now",
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
    "record_run",
    "request_decision",
    "record_decision",
    "record_triage",
    "resume_proposal",
    "report_failure",
})

# From a saved job to its tailored resume and PDF: gaps, the tailor, the health check,
# undo. tailor_application is full-only: it skips the session's checks.
TAILOR_TOOLS = frozenset({
    "get_setup_status",
    "get_tailoring_options",
    "get_career_context",
    "list_base_resumes",
    "get_base_resume",
    "store_extracted_jd",
    "find_job_by_url",
    "get_job",
    "list_jobs",
    "score_ats",
    "compare_ats",
    "create_tailoring_session",
    "quick_tailor",
    "get_tailoring_session",
    "list_tailoring_sessions",
    "resolve_gaps",
    "close_tailoring_session",
    "tailor_session",
    "edit_application",
    "get_application",
    "render_pdf",
    "get_rendered_pdf",
    "get_rendered_pdf_page_image",
    "run_health_check",
    "get_health_report",
    "judge_health_bullets",
    "waive_health_gate",
    "list_resume_versions",
    "restore_resume_version",
    "list_proposals",
    "propose_application",
    "record_run",
})

# From the finished PDF to a submitted application: the apply package, form answers,
# the proposal ledger, evidence, the user's yes, submit, and the status that follows.
APPLY_TOOLS = frozenset({
    "get_setup_status",
    "get_career_context",
    "list_proposals",
    "get_proposal",
    "get_final_review",
    "propose_application",
    "record_decision",
    "request_decision",
    "resume_proposal",
    "record_triage",
    "report_failure",
    "record_consent",
    "mark_submitted",
    "attach_evidence",
    "attach_evidence_file",
    "record_filled_answers",
    "get_job_site_login",
    "get_autofill_profile",
    "set_autofill_profile",
    "prepare_application_pdf_upload",
    "get_rendered_pdf",
    "get_rendered_pdf_page_image",
    "generate_cover_letter",
    "store_cover_letter",
    "generate_qa_answers",
    "store_qa_answers",
    "list_qa_entries",
    "edit_application",
    "get_application",
    "update_application",
    "get_job",
    "list_referrals",
    "record_run",
    "sync_now",
})

# After applying, and how the search is going: statuses, referrals, the charts.
TRACK_TOOLS = frozenset({
    "get_setup_status",
    "list_applications",
    "get_application",
    "update_application",
    "list_jobs",
    "get_job",
    "export_jobs",
    "list_proposals",
    "list_referrals",
    "get_job_search_brief",
    "explore_top_skills",
    "explore_skill_heatmap",
    "explore_role_mix_over_time",
    "explore_fit_distribution",
    "explore_gap_frequency",
    "explore_ats_over_time",
    "explore_tailoring_lift",
    "record_run",
})

# Resume designs: draft, validate, preview against a base.
TEMPLATES_TOOLS = frozenset({
    "list_base_resumes",
    "get_base_resume",
    "render_pdf",
    "get_rendered_pdf",
    "get_rendered_pdf_page_image",
    "run_health_check",
    "get_health_report",
    "judge_health_bullets",
    "list_templates",
    "get_template",
    "create_template_draft",
    "update_template_draft",
    "validate_template",
})

# The names an agent or user meets, in journey order (mcp_server.orientation.SETS).
# None => every registered tool.
PROFILE_ALLOWLISTS: dict[str, frozenset[str] | None] = {
    "profile": PROFILE_TOOLS,
    "hunt": HUNT_TOOLS,
    "tailor": TAILOR_TOOLS,
    "apply": APPLY_TOOLS,
    "track": TRACK_TOOLS,
    "templates": TEMPLATES_TOOLS,
    "full": None,
}

# Old names, served for one release so a saved connection keeps working.
PROFILE_ALIASES: dict[str, str] = {"career": "profile", "explore": "track"}
# Importers that still say the old names.
CAREER_TOOLS = PROFILE_TOOLS
EXPLORE_TOOLS = TRACK_TOOLS

VALID_PROFILES = frozenset(PROFILE_ALLOWLISTS) | frozenset(PROFILE_ALIASES)


def get_profile(name: str | None = None) -> str:
    """The set a name selects: an old name (career, explore) maps to its set."""
    raw = name if name is not None else os.environ.get("MAESTRO_CS_MCP_PROFILE", "full")
    profile = (raw or "full").strip().lower()
    if profile not in VALID_PROFILES:
        raise ValueError(
            f"Unknown MAESTRO_CS_MCP_PROFILE={profile!r}; "
            f"expected one of {sorted(VALID_PROFILES)}"
        )
    return PROFILE_ALIASES.get(profile, profile)


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
