"""The four profile-fact tools: what an agent over MCP may write (the facts Setup and
Profile ask for) and what stays the user's (diversity answers, consent, the job-site
login and every Settings switch)."""

import json
import pathlib
import re

import httpx
import pytest
import respx
from mcp.server.fastmcp.exceptions import ToolError

import mcp_server.server as srv
from app.services import markets
from mcp_server.client import BackendClient, BackendError

TOOLS = ("set_autofill_profile", "set_job_preferences", "set_markets", "set_persona")
BASE = "http://test-backend"


async def _tool(name):
    return next(tool for tool in await srv.mcp.list_tools() if tool.name == name)


async def test_the_four_writes_are_registered_as_local_writes():
    tools = {tool.name: tool for tool in await srv.mcp.list_tools()}
    for name in TOOLS:
        ann = tools[name].annotations
        assert ann.readOnlyHint is False, name
        assert ann.openWorldHint is False, name
        assert ann.idempotentHint is True, name


async def test_the_autofill_write_has_no_eeo_field_and_refuses_unknown_keys():
    schema = (await _tool("set_autofill_profile")).inputSchema
    assert "eeo" not in schema["properties"]
    assert set(schema["properties"]) == {
        "personal", "eligibility", "preferences", "work_auth_by_country",
        "education", "languages", "custom",
    }
    for shape in ("PersonalAnswers", "WorkPermitAnswers", "SavedAnswer"):
        assert schema["$defs"][shape]["additionalProperties"] is False, shape


async def test_work_permit_keys_are_the_market_list():
    schema = (await _tool("set_autofill_profile")).inputSchema
    assert json.dumps(markets.keys()) in json.dumps(schema)
    for name in ("home", "apply_in"):
        assert json.dumps(markets.keys()) in json.dumps((await _tool("set_markets")).inputSchema), name


@pytest.mark.parametrize("args", [
    {"work_auth_by_country": {"GB": {"authorized_now": True}}},
    {"personal": {"favourite_colour": "teal"}},
    {"work_auth_by_country": {"UK": {"authorized_now": "maybe"}}},
    {"custom": [{"question": "Q"}]},
])
async def test_a_bad_shape_writes_nothing(monkeypatch, args):
    monkeypatch.setattr(srv, "_client", BackendClient(BASE))
    with respx.mock:
        patch = respx.patch(f"{BASE}/api/settings/autofill").mock(
            return_value=httpx.Response(200, json={"key": "autofill_profile", "value": {}}))
        with pytest.raises(ToolError, match="validation error"):
            await srv.mcp.call_tool("set_autofill_profile", args)
    assert not patch.called


async def test_diversity_answers_alone_are_refused_and_nothing_is_written(monkeypatch):
    # FastMCP drops an argument the tool does not declare, so `eeo` arrives as no change
    # at all; a write with nothing to save is refused rather than sent back unchanged.
    monkeypatch.setattr(srv, "_client", BackendClient(BASE))
    with respx.mock:
        patch = respx.patch(f"{BASE}/api/settings/autofill").mock(
            return_value=httpx.Response(200, json={"key": "autofill_profile", "value": {}}))
        with pytest.raises(ToolError, match="Diversity"):
            await srv.mcp.call_tool("set_autofill_profile", {"eeo": {"gender": "male"}})
    assert not patch.called


def test_an_empty_preferences_write_is_refused(monkeypatch):
    monkeypatch.setattr(srv._client, "set_job_preferences", lambda changes: pytest.fail("wrote"))
    with pytest.raises(ToolError, match="Nothing to save"):
        srv.set_job_preferences()


def test_set_autofill_profile_sends_only_the_sections_given_and_reads_readiness(monkeypatch):
    seen = {}

    def write(changes):
        seen["changes"] = changes
        return {"personal": {"city": "Leeds"}}

    monkeypatch.setattr(srv._client, "set_autofill_profile", write)
    monkeypatch.setattr(srv._client, "get_setup_status", lambda: {"autofill": {"readiness": 0.4}})
    out = srv.set_autofill_profile(
        personal={"city": "Leeds"}, work_auth_by_country={"UK": {"authorized_now": True}}
    )
    assert seen["changes"] == {
        "personal": {"city": "Leeds"}, "work_auth_by_country": {"UK": {"authorized_now": True}},
    }
    assert out == {"profile": {"personal": {"city": "Leeds"}}, "setup": {"readiness": 0.4}}


def test_a_landed_write_reports_no_setup_when_the_status_read_fails(monkeypatch):
    def fail():
        raise BackendError("down")

    monkeypatch.setattr(srv._client, "set_autofill_profile", lambda changes: {"personal": {}})
    monkeypatch.setattr(srv._client, "get_setup_status", fail)
    assert srv.set_autofill_profile(personal={"city": "Leeds"})["setup"] is None


def test_set_job_preferences_forwards_only_the_fields_given(monkeypatch):
    seen = {}
    monkeypatch.setattr(srv._client, "set_job_preferences", lambda changes: seen.setdefault("c", changes))
    srv.set_job_preferences(remote="remote", locations=[])
    assert seen["c"] == {"remote": "remote", "locations": []}


def test_set_markets_forwards_and_adds_readiness(monkeypatch):
    seen = {}

    def write(**kw):
        seen.update(kw)
        return {"home": "UK", "apply_in": ["UK"], "home_currency": "GBP"}

    monkeypatch.setattr(srv._client, "set_markets", write)
    monkeypatch.setattr(srv._client, "get_setup_status", lambda: {"autofill": {"blocking": ["work_auth"]}})
    out = srv.set_markets(home="UK", apply_in=["UK"])
    assert seen == {"home": "UK", "apply_in": ["UK"], "home_currency": None}
    assert out["setup"] == {"blocking": ["work_auth"]}
    assert out["home_currency"] == "GBP"


def test_set_persona_forwards_the_text(monkeypatch):
    monkeypatch.setattr(srv._client, "set_persona", lambda text: {"key": "persona", "value": text})
    assert srv.set_persona("Calm under pressure.") == {"key": "persona", "value": "Calm under pressure."}


# The human-only boundary, pinned where it would break: the client is the only way an MCP
# tool reaches the backend, so the settings it can write are exactly these four. The money
# setting's currency rides on the market save (`PATCH /api/settings/market` takes `home_currency`
# and no other money field). Another (full automation, auto-apply, EEO consent, the job-site
# login, the Screening answers dial, the hints switch, model keys and picks, prompts, quick
# tailor) is a deliberate change here.
_MCP_WRITABLE_SETTINGS = {"autofill", "job-preferences", "market", "persona"}


def test_mcp_writes_only_the_settings_setup_and_profile_ask_for():
    source = (pathlib.Path(srv.__file__).parent / "client.py").read_text()
    written = set(re.findall(
        r'"(?:PUT|POST|PATCH|DELETE)",\s*f?"/api/settings/([a-z0-9-]+)', source
    ))
    assert written == _MCP_WRITABLE_SETTINGS
