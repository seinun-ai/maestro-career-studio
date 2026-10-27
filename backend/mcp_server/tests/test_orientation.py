"""Per-set server instructions: what this set does, what it leaves out, where the rest is."""

import re

import pytest

from mcp_server import orientation
from mcp_server.profiles import PROFILE_ALLOWLISTS
from mcp_server.server import list_registered_tool_names

TOOLS = set(list_registered_tool_names("full"))


@pytest.mark.parametrize("profile", orientation.SET_NAMES)
def test_instructions_fit_claude_codes_cut(profile):
    assert 0 < len(orientation.instructions_for(profile)) <= 4096


@pytest.mark.parametrize("profile", orientation.SET_NAMES)
def test_instructions_name_every_other_set(profile):
    text = orientation.instructions_for(profile)
    for other in orientation.SET_NAMES:
        assert re.search(rf"\b{other}\b", text), (profile, other)


@pytest.mark.parametrize("profile", [p for p in orientation.SET_NAMES if p != "templates"])
def test_instructions_start_an_agent_at_setup_status(profile):
    assert "get_setup_status" in orientation.instructions_for(profile)


@pytest.mark.parametrize("profile", orientation.SET_NAMES)
def test_instructions_name_no_tool_the_set_lacks(profile):
    allow = PROFILE_ALLOWLISTS[profile]
    named = set(re.findall(r"[a-z_]+", orientation.instructions_for(profile))) & TOOLS
    assert allow is None or named <= allow, named - set(allow or ())


@pytest.mark.parametrize("profile", [p for p in orientation.SET_NAMES if p != "templates"])
def test_instructions_say_setup_status_names_who_writes(profile):
    text = orientation.instructions_for(profile)
    assert "writer says who writes: you, the agent app" in text
    assert "Maestro's AI" in text
    assert "your agent app" not in text.lower()  # the reader is the agent app


def test_a_scoped_set_says_what_it_is_for():
    text = orientation.instructions_for("tailor")
    assert "This is the tailor set" in text
    assert "tailor my resume for this job" in text


def test_hunt_says_it_holds_the_referrals_it_lists_and_saves():
    hunt = next(s for s in orientation.SETS if s.name == "hunt")
    assert "referral" in hunt.holds
    assert {"list_referrals", "save_referral"} <= PROFILE_ALLOWLISTS["hunt"]
