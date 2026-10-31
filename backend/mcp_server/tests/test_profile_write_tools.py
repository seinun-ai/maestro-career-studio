"""The four profile-fact tools: what an agent over MCP may write (the facts Setup and
Profile ask for) and what stays the user's (diversity answers, consent, the job-site
login and every Settings switch)."""

import json
import pathlib
import re

import httpx
import pytest
import respx
from mcp.server.mcpserver.exceptions import ToolError

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
        assert ann.read_only_hint is False, name
        assert ann.open_world_hint is False, name
        assert ann.idempotent_hint is True, name


async def test_the_autofill_write_has_no_eeo_field_and_refuses_unknown_keys():
    schema = (await _tool("set_autofill_profile")).input_schema
    assert "eeo" not in schema["properties"]
    assert set(schema["properties"]) == {
        "personal", "eligibility", "preferences", "work_auth_by_country", "answers_by_country",
        "education", "languages", "custom",
    }
    for shape in ("PersonalAnswers", "EligibilityAnswers", "PreferenceAnswers", "WorkPermitAnswers",
                  "CountryAnswers", "LanguageEntry", "SavedAnswer"):
        assert schema["$defs"][shape]["additionalProperties"] is False, shape


async def test_country_answers_are_the_catalogs_and_each_market_is_a_market_key():
    """A country answer added to form_questions.yaml is writable with no code change, typed as asked."""
    from app.services import form_questions

    schema = (await _tool("set_autofill_profile")).input_schema
    answers = schema["$defs"]["CountryAnswers"]["properties"]
    assert list(answers) == [f.key for f in form_questions.catalog().answers]
    assert answers["in_country_now"]["anyOf"][0] == {"type": "boolean"}
    assert answers["expected_pay"]["anyOf"][0] == {"type": "string"}
    by_market = schema["properties"]["answers_by_country"]["anyOf"][0]
    assert by_market["propertyNames"]["enum"] == markets.keys()
    assert "preferences" in schema["properties"]["answers_by_country"]["description"]


def test_a_catalog_without_cefr_levels_fails_by_name(monkeypatch):
    """The server's schema reads the catalog at import, so a broken one fails the app's boot: with a
    sentence naming the file, not a bare error from building an empty Literal."""
    from app.services import form_questions

    stripped = form_questions.catalog().model_copy(update={"language_fields": []})
    monkeypatch.setattr(form_questions, "catalog", lambda: stripped)
    with pytest.raises(RuntimeError, match="form_questions.yaml: the cefr language field lists no levels"):
        srv._cefr_levels()


async def test_a_status_is_any_text_and_says_where_each_markets_list_is():
    """Each market has its own statuses, so the schema takes a string and names where they are listed;
    the backend refuses one outside the market's list."""
    work_permit = (await _tool("set_autofill_profile")).input_schema["$defs"]["WorkPermitAnswers"]
    assert work_permit["properties"]["status"]["anyOf"][0] == {"type": "string"}
    assert "get_autofill_profile's questions" in work_permit["description"]


@pytest.mark.parametrize("args", [
    {"personal": {"citizenships": ["IN", "United Kingdom"]}},
    {"eligibility": {"experience_years": 6}},
    {"eligibility": {"experience_months": 11}},
    {"preferences": {"notice_days": 45}},
    {"preferences": {"serving_notice": True}},
    {"preferences": {"last_working_day": "2026-12-01"}},
    {"preferences": {"preferred_locations": "Bengaluru, Pune"}},
    {"languages": [{"language": "German", "cefr": "B2"}]},
    {"answers_by_country": {"IN": {"expected_pay": "2400000", "current_ctc": "1800000"}}},
    {"answers_by_country": {"AE": {"in_country_now": True, "uae_driving_licence": False}, "DE": None}},
], ids=["citizenships", "experience_years", "experience_months", "notice_days", "serving_notice",
        "last_working_day", "preferred_locations", "cefr", "country_answers", "country_yes_no"])
async def test_each_new_answer_is_written_as_given(monkeypatch, args):
    monkeypatch.setattr(srv, "_client", BackendClient(BASE))
    with respx.mock:
        patch = respx.patch(f"{BASE}/api/settings/autofill").mock(
            return_value=httpx.Response(200, json={"key": "autofill_profile", "value": {}}))
        respx.get(f"{BASE}/api/setup/status").mock(return_value=httpx.Response(200, json={}))
        await srv.mcp.call_tool("set_autofill_profile", args)
    assert json.loads(patch.calls.last.request.read())["value"] == args


@pytest.mark.parametrize("args", [
    {"languages": [{"language": "German", "cefr": "B3"}]},
    {"eligibility": {"experience_months": 12}},
    {"preferences": {"notice_days": -1}},
    {"personal": {"citizenships": "IN"}},
    {"answers_by_country": {"AE": {"favourite_emirate": "Dubai"}}},
    {"answers_by_country": {"FR": {"expected_pay": "1"}}},
    {"answers_by_country": {"AE": {"in_country_now": "maybe"}}},
])
async def test_a_bad_new_answer_writes_nothing(monkeypatch, args):
    monkeypatch.setattr(srv, "_client", BackendClient(BASE))
    with respx.mock:
        patch = respx.patch(f"{BASE}/api/settings/autofill").mock(
            return_value=httpx.Response(200, json={"key": "autofill_profile", "value": {}}))
        with pytest.raises(ToolError, match="validation error"):
            await srv.mcp.call_tool("set_autofill_profile", args)
    assert not patch.called


async def test_a_status_from_another_country_comes_back_as_the_backends_refusal(monkeypatch):
    """The schema cannot know Canada's list from the US one; the backend's 422 names Canada's statuses,
    and that sentence is what the agent reads."""
    from app.services import autofill_profile

    args = {"work_auth_by_country": {"CA": {"status": "h1b"}}}
    refusal = autofill_profile._refusal(args)
    assert refusal and "open_work_permit" in refusal
    monkeypatch.setattr(srv, "_client", BackendClient(BASE))
    with respx.mock:
        respx.patch(f"{BASE}/api/settings/autofill").mock(
            return_value=httpx.Response(422, json={"detail": refusal}))
        with pytest.raises(ToolError) as caught:
            await srv.mcp.call_tool("set_autofill_profile", args)
    assert refusal in str(caught.value)


async def test_the_autofill_write_says_saved_answers_are_added_or_replaced_never_removed():
    doc = " ".join(((await _tool("set_autofill_profile")).description or "").split())
    assert "education and languages replace the stored list whole" in doc
    for words in ("same question", "case and spacing ignored", "only_for", "is added",
                  "never removed", "Companion learned"):
        assert words in doc, words
    # The key is the question with both halves of its scope (`only_for`, `only_for_kind`).
    assert "the same only_for and only_for_kind" in doc
    assert "as get_autofill_profile shows them" in doc
    assert "custom replace" not in doc


async def test_work_permit_keys_are_the_market_list():
    schema = (await _tool("set_autofill_profile")).input_schema
    assert json.dumps(markets.keys()) in json.dumps(schema)
    for name in ("home", "apply_in"):
        assert json.dumps(markets.keys()) in json.dumps((await _tool("set_markets")).input_schema), name


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
    # MCPServer drops an argument the tool does not declare, so `eeo` arrives as no change
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
