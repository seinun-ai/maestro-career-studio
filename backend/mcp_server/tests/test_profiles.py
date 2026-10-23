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
        "kb_sync_base",
        "create_base_resume_from_kb",
        "kb_groom_entity",
        "kb_combine_points",
        "kb_retire_points",
        "kb_add_points",
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


def test_apply_profile_can_store_an_apply_package_without_an_ai_key():
    """A key-less agent writes the letter and answers itself; apply carries the
    store tools beside the generate ones."""
    assert {"store_cover_letter", "store_qa_answers", "list_qa_entries"} <= APPLY_TOOLS


def test_scoped_profiles_stay_read_only_on_the_kb():
    for allowlist in (HUNT_TOOLS, APPLY_TOOLS, EXPLORE_TOOLS, TEMPLATES_TOOLS):
        assert not {tool for tool in allowlist if tool.startswith("kb_")}


def test_importing_the_server_never_deletes_tools():
    """A stdio profile env var must not shrink the shared HTTP tool registry.

    Use a subprocess because HTTP consumers hold the registry by reference.
    """
    import os
    import subprocess
    import sys
    from pathlib import Path

    import mcp_server.server as srv

    out = subprocess.run(
        [sys.executable, "-c",
         "import mcp_server.server as s; print(len(s.mcp._tool_manager.list_tools()))"],
        env={**os.environ, "MAESTRO_CS_MCP_PROFILE": "hunt"},
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert int(out) == len(srv.list_registered_tool_names("full"))


def test_the_request_profile_wins_over_the_env_for_hints(monkeypatch):
    import mcp_server.server as srv
    from mcp_server.profiles import allowed_tools

    monkeypatch.setenv("MAESTRO_CS_MCP_PROFILE", "full")
    token = srv.CURRENT_PROFILE.set("hunt")
    try:
        assert srv._active_allowed_tools() == allowed_tools("hunt")
    finally:
        srv.CURRENT_PROFILE.reset(token)
    assert srv._active_allowed_tools() == allowed_tools("full")
