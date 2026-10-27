"""A removed tool name answers with what replaced it, on stdio and on every HTTP set."""

import re

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

import mcp_server.server as srv
from mcp_server import replaced
from mcp_server.profiles import PROFILE_ALLOWLISTS, apply_profile_filter

_REMOVED = {
    "explore_top_skills", "explore_skill_heatmap", "explore_role_mix_over_time",
    "explore_fit_distribution", "explore_ats_over_time", "explore_tailoring_lift",
    "get_career_export", "attach_evidence_file", "quick_tailor", "tailor_application",
}


def test_every_removed_name_is_served_nowhere_and_every_replacement_is_registered():
    registered = set(srv.list_registered_tool_names("full"))
    assert set(replaced.REPLACED_TOOLS) == _REMOVED
    for name, replacement in replaced.REPLACED_TOOLS.items():
        assert name not in registered, name
        assert all(name not in allow for allow in PROFILE_ALLOWLISTS.values() if allow), name
        # The tools a replacement names: identifiers with an underscore, neither an argument
        # name (before "=") nor a quoted argument value.
        unquoted = re.sub(r'"[^"]*"', "", replacement)
        named = set(re.findall(r"\b[a-z]+(?:_[a-z]+)+\b(?!=)", unquoted))
        assert named and named <= registered, (name, sorted(named - registered))


def test_the_message_names_the_replacement_and_only_for_a_removed_name():
    assert replaced.replaced_message("explore_top_skills") == (
        'explore_top_skills was replaced by explore_trends(view="top_skills").'
    )
    assert replaced.replaced_message("attach_evidence_file") == (
        "attach_evidence_file was replaced by attach_evidence(file_path=...)."
    )
    assert replaced.replaced_message("list_jobs") is None
    assert replaced.replaced_message("no_such_tool") is None


@pytest.mark.parametrize("name", sorted(_REMOVED))
async def test_stdio_answers_a_removed_name_with_its_replacement(name):
    async with create_connected_server_and_client_session(srv.mcp) as session:
        result = await session.call_tool(name, {})
    assert result.isError
    assert result.content[0].text == replaced.replaced_message(name)


async def test_stdio_keeps_the_plain_error_for_a_name_never_served():
    async with create_connected_server_and_client_session(srv.mcp) as session:
        result = await session.call_tool("no_such_tool", {})
    assert result.isError
    assert result.content[0].text == "Unknown tool: no_such_tool"


async def test_a_stdio_set_answers_a_removed_name_and_keeps_the_plain_error_for_the_rest():
    stdio = srv._ServedMCP("stdio-set")

    @stdio.tool()
    def list_jobs() -> str:
        return "jobs"

    @stdio.tool()
    def create_template_draft() -> str:
        return "draft"

    apply_profile_filter(stdio, "track")
    async with create_connected_server_and_client_session(stdio) as session:
        removed = await session.call_tool("explore_top_skills", {"limit": 5})
        hidden = await session.call_tool("create_template_draft", {})
        served = await session.call_tool("list_jobs", {})
    assert removed.isError
    assert removed.content[0].text == replaced.replaced_message("explore_top_skills")
    assert hidden.isError and hidden.content[0].text == "Unknown tool: create_template_draft"
    assert not served.isError, served.content
