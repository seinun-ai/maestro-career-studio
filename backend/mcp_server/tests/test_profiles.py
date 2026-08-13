"""Scoped MCP profile allowlists and filter behavior."""
from mcp.server.fastmcp import FastMCP

from mcp_server.profiles import (
    APPLY_TOOLS,
    EXPLORE_TOOLS,
    HUNT_TOOLS,
    TEMPLATES_TOOLS,
    apply_profile_filter,
    get_profile,
)


def test_default_profile_is_full(monkeypatch):
    monkeypatch.delenv("MAESTRO_CS_MCP_PROFILE", raising=False)
    assert get_profile() == "full"


def test_unknown_profile_raises(monkeypatch):
    monkeypatch.setenv("MAESTRO_CS_MCP_PROFILE", "nope")
    try:
        get_profile()
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "Unknown MAESTRO_CS_MCP_PROFILE" in str(exc)


def test_apply_profile_filter_keeps_apply_drops_explore():
    m = FastMCP("profile-test")

    @m.tool()
    def propose_application() -> str:
        return "ok"

    @m.tool()
    def explore_top_skills() -> str:
        return "nope"

    @m.tool()
    def create_template_draft() -> str:
        return "nope"

    assert apply_profile_filter(m, "apply") == "apply"
    names = {t.name for t in m._tool_manager.list_tools()}
    assert names == {"propose_application"}


def test_full_profile_filter_is_noop():
    m = FastMCP("profile-full")

    @m.tool()
    def explore_top_skills() -> str:
        return "ok"

    apply_profile_filter(m, "full")
    assert {t.name for t in m._tool_manager.list_tools()} == {"explore_top_skills"}


def test_profile_allowlists_are_disjoint_from_unused_domains():
    assert {
        "explore_top_skills",
        "create_template_draft",
        "get_career_export",
    }.isdisjoint(APPLY_TOOLS)
    assert {"mark_submitted", "propose_application", "record_triage"} <= APPLY_TOOLS
    assert {
        "explore_top_skills",
        "mark_submitted",
        "get_career_export",
    }.isdisjoint(HUNT_TOOLS)
    assert {"propose_application", "record_triage"} <= HUNT_TOOLS
    # Triage is a hunt-and-apply decision surface; still no submit power in hunt.
    assert "get_career_export" not in EXPLORE_TOOLS
    assert "validate_template" in TEMPLATES_TOOLS
    assert {"tailor_session", "get_career_export"}.isdisjoint(TEMPLATES_TOOLS)


def test_career_profile_has_kb_writes_and_no_job_tools():
    from mcp_server.profiles import CAREER_TOOLS

    assert "kb_edit_point" in CAREER_TOOLS
    assert "kb_edit_profile" in CAREER_TOOLS
    assert "get_career_context" in CAREER_TOOLS
    assert "list_jobs" not in CAREER_TOOLS


def test_career_profile_registers_onboarding_tools_and_hunt_does_not():
    from mcp_server.profiles import CAREER_TOOLS, HUNT_TOOLS

    new_tools = {
        "kb_ingest_resume",
        "kb_approve_points",
        "create_base_resume_from_kb",
    }
    assert new_tools <= CAREER_TOOLS
    assert {"list_base_resumes", "get_base_resume"} <= CAREER_TOOLS
    assert new_tools.isdisjoint(HUNT_TOOLS)


def test_career_profile_can_finish_the_arc_it_starts():
    """Onboarding ends with a PDF in hand — a profile that composes a base but
    cannot render it dead-ends at a JSON blob. Scoring/tailoring stay out."""
    from mcp_server.profiles import CAREER_TOOLS

    assert {"render_pdf", "get_rendered_pdf"} <= CAREER_TOOLS
    assert {"score_ats", "tailor_session", "create_tailoring_session"}.isdisjoint(CAREER_TOOLS)


def test_scoped_profiles_stay_read_only_on_the_kb():
    for allowlist in (HUNT_TOOLS, APPLY_TOOLS, EXPLORE_TOOLS, TEMPLATES_TOOLS):
        assert not {tool for tool in allowlist if tool.startswith("kb_")}
