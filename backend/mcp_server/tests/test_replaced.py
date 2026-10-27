"""A removed tool name answers with what replaced it, on stdio and on every HTTP set."""

import re

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

import mcp_server.server as srv
from mcp_server import replaced
from mcp_server.profiles import PROFILE_ALLOWLISTS

_REMOVED = {
    "explore_top_skills", "explore_skill_heatmap", "explore_role_mix_over_time",
    "explore_fit_distribution", "explore_ats_over_time", "explore_tailoring_lift",
    "get_career_export", "attach_evidence_file", "quick_tailor", "tailor_application",
}


def _enum(prop: dict) -> list:
    return prop.get("enum") or [v for branch in prop.get("anyOf", []) for v in branch.get("enum", [])]


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


def test_every_argument_a_replacement_writes_out_is_one_its_tool_takes():
    """`tool(arg=value)`: the tool takes arg, a quoted value is one arg's enum lists, and a
    bare true or false goes to a boolean."""
    calls = 0
    for name, replacement in replaced.REPLACED_TOOLS.items():
        for tool, args in re.findall(r"\b([a-z]+(?:_[a-z]+)+)\(([^)]*)\)", replacement):
            props = srv.mcp._tool_manager.get_tool(tool).parameters["properties"]
            for arg in filter(None, (a.strip() for a in args.split(","))):
                key, _, value = arg.partition("=")
                assert key in props, (name, tool, key)
                if value.startswith('"'):
                    assert value.strip('"') in _enum(props[key]), (name, tool, arg)
                elif value in ("true", "false"):
                    assert props[key].get("type") == "boolean", (name, tool, arg)
                calls += 1
    assert calls >= 9  # six views, a format, a file_path and use_presets


def test_the_message_names_the_replacement_and_only_for_a_removed_name():
    assert replaced.replaced_message("explore_top_skills") == (
        'explore_top_skills was replaced by explore_trends(view="top_skills").'
    )
    assert replaced.replaced_message("attach_evidence_file") == (
        "attach_evidence_file was replaced by attach_evidence(file_path=...)."
    )
    assert replaced.replaced_message("list_jobs") is None
    assert replaced.replaced_message("no_such_tool") is None


def test_the_message_says_which_set_serves_the_replacement_when_this_one_does_not():
    from mcp_server.profiles import APPLY_TOOLS, HUNT_TOOLS, TRACK_TOOLS

    assert replaced.replaced_message("explore_top_skills", served=TRACK_TOOLS) == (
        'explore_top_skills was replaced by explore_trends(view="top_skills").'
    )
    assert replaced.replaced_message("explore_top_skills", served=HUNT_TOOLS) == (
        'explore_top_skills was replaced by explore_trends(view="top_skills"), in the track set.'
    )
    assert replaced.replaced_message("get_career_export", served=HUNT_TOOLS) == (
        'get_career_export was replaced by get_career_context(format="markdown"), in the '
        "profile, tailor and apply sets."
    )
    # Every tool a replacement names must be served there: the session tools sit in tailor.
    assert replaced.replaced_message("tailor_application", served=APPLY_TOOLS).endswith(
        "edit_application for the current draft, in the tailor set."
    )


def test_every_replacement_is_served_whole_by_some_scoped_set():
    for name in replaced.REPLACED_TOOLS:
        for set_name, allow in PROFILE_ALLOWLISTS.items():
            if allow:
                message = replaced.replaced_message(name, served=allow)
                assert message.endswith(".") and ", in the full set" not in message, (name, set_name)


@pytest.mark.parametrize("name", sorted(_REMOVED))
async def test_stdio_answers_a_removed_name_with_its_replacement(name):
    async with create_connected_server_and_client_session(srv.build_set("full")) as session:
        result = await session.call_tool(name, {})
    assert result.isError
    assert result.content[0].text == replaced.replaced_message(name)


async def test_stdio_keeps_the_plain_error_for_a_name_never_served():
    async with create_connected_server_and_client_session(srv.build_set("full")) as session:
        result = await session.call_tool("no_such_tool", {})
    assert result.isError
    assert result.content[0].text == "Unknown tool: no_such_tool"


async def test_a_stdio_set_answers_a_removed_name_and_keeps_the_plain_error_for_the_rest(monkeypatch):
    monkeypatch.setattr(srv._client, "list_jobs", lambda **_: [])

    async with create_connected_server_and_client_session(srv.build_set("track")) as session:
        removed = await session.call_tool("explore_top_skills", {"limit": 5})
        hidden = await session.call_tool("create_template_draft", {})
        served = await session.call_tool("list_jobs", {})
    assert removed.isError
    assert removed.content[0].text == replaced.replaced_message("explore_top_skills")
    assert hidden.isError and hidden.content[0].text == "Unknown tool: create_template_draft"
    assert not served.isError, served.content

    async with create_connected_server_and_client_session(srv.build_set("hunt")) as session:
        elsewhere = await session.call_tool("explore_top_skills", {})
    assert elsewhere.content[0].text.endswith('explore_trends(view="top_skills"), in the track set.')
