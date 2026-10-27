"""Scoped MCP profile allowlists and filter behavior."""
from mcp.server.fastmcp import FastMCP

from mcp_server import orientation
from mcp_server.profiles import (
    APPLY_TOOLS,
    HUNT_TOOLS,
    PROFILE_ALIASES,
    PROFILE_ALLOWLISTS,
    PROFILE_TOOLS,
    TAILOR_TOOLS,
    TEMPLATES_TOOLS,
    TRACK_TOOLS,
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
    def explore_trends() -> str:
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
    def explore_trends() -> str:
        return "ok"

    apply_profile_filter(m, "full")
    assert {t.name for t in m._tool_manager.list_tools()} == {"explore_trends"}


def test_a_stdio_set_says_what_it_holds_not_what_full_holds():
    """A stdio process serves one set: its instructions must name no tool that set lacks
    (templates has no get_setup_status), as each HTTP set's do."""
    for name, active in (("templates", "templates"), ("career", "profile")):
        m = FastMCP("profile-instructions", instructions=orientation.instructions_for("full"))
        assert apply_profile_filter(m, name) == active
        assert m.instructions == orientation.instructions_for(active)
        assert ("get_setup_status" in m.instructions) == (active != "templates")


def test_profile_allowlists_are_disjoint_from_unused_domains():
    assert {"explore_trends", "create_template_draft"}.isdisjoint(APPLY_TOOLS)
    assert {"mark_submitted", "propose_application", "record_triage"} <= APPLY_TOOLS
    assert {"explore_trends", "mark_submitted", "get_career_context"}.isdisjoint(HUNT_TOOLS)
    assert {"propose_application", "record_triage"} <= HUNT_TOOLS
    # Triage is a hunt-and-apply decision surface; still no submit power in hunt.
    assert "get_career_context" not in TRACK_TOOLS
    assert {"mark_submitted", "explore_trends", "kb_edit_point"}.isdisjoint(TAILOR_TOOLS)
    assert "validate_template" in TEMPLATES_TOOLS
    assert {"tailor_session", "get_career_context"}.isdisjoint(TEMPLATES_TOOLS)


def test_profile_set_has_kb_writes_and_no_job_tools():
    assert {"kb_edit_point", "kb_edit_profile", "get_career_context"} <= PROFILE_TOOLS
    assert "list_jobs" not in PROFILE_TOOLS


def test_profile_set_registers_onboarding_tools_and_hunt_does_not():
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
    assert new_tools <= PROFILE_TOOLS
    assert {"list_base_resumes", "get_base_resume"} <= PROFILE_TOOLS
    assert new_tools.isdisjoint(HUNT_TOOLS)


def test_profile_set_can_finish_onboarding_on_its_own():
    """Onboarding ends with a checked base resume and the form answers: compose, set
    its anchors, fix it, render it, judge it, and read what is saved before a write."""
    assert {
        "render_pdf", "get_rendered_pdf", "set_base_resume_identity", "edit_base_resume",
        "run_health_check", "judge_health_bullets", "waive_health_gate",
        "get_autofill_profile", "list_resume_versions", "restore_resume_version",
    } <= PROFILE_TOOLS
    assert {"score_ats", "tailor_session", "create_tailoring_session"}.isdisjoint(PROFILE_TOOLS)


def test_apply_profile_can_store_an_apply_package_without_an_ai_key():
    """A key-less agent writes the letter and answers itself; apply carries the
    store tools beside the generate ones."""
    assert {"store_cover_letter", "store_qa_answers", "list_qa_entries"} <= APPLY_TOOLS


def test_profile_fact_writes_reach_apply_and_profile_but_not_hunt():
    """The profile set runs onboarding, so it writes every fact Setup asks for; apply saves a
    form answer learned mid-application once; the others write none."""
    writes = {"set_autofill_profile", "set_job_preferences", "set_markets", "set_persona"}
    assert writes <= PROFILE_TOOLS
    assert APPLY_TOOLS & writes == {"set_autofill_profile"}
    for allowlist in (HUNT_TOOLS, TAILOR_TOOLS, TRACK_TOOLS, TEMPLATES_TOOLS):
        assert writes.isdisjoint(allowlist)


def test_scoped_profiles_stay_read_only_on_the_kb():
    for allowlist in (HUNT_TOOLS, TAILOR_TOOLS, APPLY_TOOLS, TRACK_TOOLS, TEMPLATES_TOOLS):
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


def test_the_sets_follow_the_journey_and_every_one_is_served():
    assert [s.name for s in orientation.SETS] == [
        "profile", "hunt", "tailor", "apply", "track", "templates", "full"]
    assert set(PROFILE_ALLOWLISTS) == {s.name for s in orientation.SETS}


def test_old_names_still_resolve_for_one_release():
    assert PROFILE_ALIASES == {"career": "profile", "explore": "track"}
    assert get_profile("career") == "profile" and get_profile("explore") == "track"


def test_every_scoped_set_but_templates_opens_with_setup_status():
    for name, allow in PROFILE_ALLOWLISTS.items():
        if allow is not None and name != "templates":
            assert "get_setup_status" in allow, name


def test_tailoring_options_sit_with_tailoring():
    assert "get_tailoring_options" in TAILOR_TOOLS


def test_tailor_application_is_registered_nowhere():
    """It rebuilt a draft without the session's checks; a tailoring session, or
    edit_application on the draft, does that work now."""
    import mcp_server.server as srv

    assert "tailor_application" not in srv.list_registered_tool_names("full")
    assert all("tailor_application" not in allow for allow in PROFILE_ALLOWLISTS.values() if allow)


def test_set_sizes_stay_near_the_line():
    sizes = {n: len(a) for n, a in PROFILE_ALLOWLISTS.items() if a is not None}
    assert sizes == {"profile": 38, "hunt": 22, "tailor": 31, "apply": 35, "track": 13, "templates": 13}


def test_every_allowlisted_tool_is_registered():
    import mcp_server.server as srv

    registered = set(srv.list_registered_tool_names("full"))
    for name, allow in PROFILE_ALLOWLISTS.items():
        assert not (set(allow or ()) - registered), name
