"""The MCP client's profile-fact writes: each sends only what the tool was given, in one PATCH, and
the server merges it into the setting stored at write time (app/services/autofill_profile.py,
job_preferences.py, market_settings.py; tests/test_settings_agent_patch.py pins the merge). The client
never reads a setting to write it back, so a save another writer made meanwhile is not erased.
EEO answers are never written by an agent and never come back to one."""

import json

import httpx
import pytest
import respx

from mcp_server.client import BackendClient, BackendError

BASE = "http://test-backend"

_SAVED = {
    "personal": {"first_name": "Ana", "city": "Leeds"},
    "eeo": {"gender": "female"},
    "work_auth_by_country": {"US": {"status": "citizen", "authorized_now": True}},
    "work_auth": {"status": "citizen", "authorized_now": True},
    "work_auth_market": "US",
}


def _sent(route):
    return json.loads(route.calls.last.request.read())["value"]


def _no_whole_setting_writes():
    """The old read-then-PUT path: any GET or PUT of a profile setting fails the test."""
    for name in ("autofill", "job-preferences", "market", "money"):
        respx.get(f"{BASE}/api/settings/{name}").mock(side_effect=AssertionError(f"read {name}"))
        respx.put(f"{BASE}/api/settings/{name}").mock(side_effect=AssertionError(f"PUT {name}"))


def _mock_autofill(echo=_SAVED):
    _no_whole_setting_writes()
    return respx.patch(f"{BASE}/api/settings/autofill").mock(
        return_value=httpx.Response(200, json={"key": "autofill_profile", "value": echo})
    )


@respx.mock
def test_set_autofill_profile_sends_only_the_changes_in_one_patch():
    patch = _mock_autofill()
    changes = {
        "personal": {"city": "Leeds", "phone": None},
        "work_auth_by_country": {"UK": {"authorized_now": True}, "US": None},
        "custom": [{"question": "Q2", "answer": "A2"}],
    }
    BackendClient(BASE).set_autofill_profile(changes)
    assert patch.call_count == 1
    assert _sent(patch) == changes
    assert patch.calls.last.request.headers["X-Maestro-CS-Origin"] == "mcp"


@respx.mock
@pytest.mark.parametrize("section", ["eeo", "stale_answers", "work_auth"])
def test_a_section_outside_the_list_is_refused_and_nothing_is_written(section):
    patch = _mock_autofill()
    with pytest.raises(BackendError, match=section):
        BackendClient(BASE).set_autofill_profile({section: {"gender": "male"}})
    assert not patch.called


@respx.mock
def test_the_response_never_carries_eeo_even_when_the_server_echoes_it():
    _mock_autofill()
    out = BackendClient(BASE).set_autofill_profile({"personal": {"city": "Leeds"}})
    assert "eeo" not in out
    assert out["personal"] == {"first_name": "Ana", "city": "Leeds"}


@respx.mock
def test_job_preferences_send_only_the_fields_passed():
    _no_whole_setting_writes()
    patch = respx.patch(f"{BASE}/api/settings/job-preferences").mock(
        side_effect=lambda request: httpx.Response(200, json={"key": "job_preferences", "value": {
            "favored_roles": [], "role_categories": [], **json.loads(request.read())["value"],
        }})
    )
    out = BackendClient(BASE).set_job_preferences({"remote": "remote", "notes": ""})
    assert _sent(patch) == {"remote": "remote", "notes": ""}
    assert out["remote"] == "remote"


def _mock_market():
    _no_whole_setting_writes()
    return respx.patch(f"{BASE}/api/settings/market").mock(
        return_value=httpx.Response(200, json={
            "key": "market", "value": {"home": "UK", "apply_in": ["US", "CA"], "market": "UK"},
            "home": "UK", "apply_in": ["US", "CA"], "currency": "GBP", "offers_eeo": True,
            "home_currency": "EUR",
        })
    )


@respx.mock
def test_set_markets_is_one_patch_of_the_fields_passed():
    patch = _mock_market()
    out = BackendClient(BASE).set_markets(home="UK", home_currency="EUR")
    assert patch.call_count == 1
    assert _sent(patch) == {"home": "UK", "home_currency": "EUR"}
    assert out == {"home": "UK", "apply_in": ["US", "CA"], "home_currency": "EUR"}


@respx.mock
def test_an_empty_currency_and_an_empty_apply_in_are_sent_as_given():
    patch = _mock_market()
    BackendClient(BASE).set_markets(apply_in=[], home_currency="")
    assert _sent(patch) == {"apply_in": [], "home_currency": ""}


@respx.mock
def test_no_field_sends_an_empty_patch_that_reads_the_current_values():
    patch = _mock_market()
    BackendClient(BASE).set_markets()
    assert _sent(patch) == {}


@respx.mock
def test_set_persona_replaces_the_text():
    put = respx.put(f"{BASE}/api/settings/persona").mock(
        return_value=httpx.Response(200, json={"key": "persona", "value": "Builds calm teams."})
    )
    out = BackendClient(BASE).set_persona("Builds calm teams.")
    assert json.loads(put.calls.last.request.read()) == {"value": "Builds calm teams."}
    assert out == {"key": "persona", "value": "Builds calm teams."}
