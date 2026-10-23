"""The MCP client's profile-fact writes: each reads its setting, merges in what the tool
was given and writes the whole setting back, because every PUT replaces its setting.
EEO answers are never written by an agent and never come back to one."""

import json

import httpx
import pytest
import respx

from mcp_server.client import BackendClient, BackendError

BASE = "http://test-backend"

_STORED = {
    "personal": {"first_name": "Ana", "city": "Lyon"},
    "preferences": {"notice_period": "2 weeks"},
    "eeo": {"gender": "female"},
    "custom": [{"question": "Q", "answer": "A"}],
    "work_auth_by_country": {"US": {"status": "citizen", "authorized_now": True}},
    # The read view's projection of the home set: never sent back.
    "work_auth": {"status": "citizen", "authorized_now": True},
    "work_auth_market": "US",
}


def _mock_autofill(stored=_STORED, echo=None):
    respx.get(f"{BASE}/api/settings/autofill").mock(
        return_value=httpx.Response(200, json={"key": "autofill_profile", "value": stored})
    )
    put = respx.put(f"{BASE}/api/settings/autofill").mock(
        side_effect=lambda request: httpx.Response(
            200,
            json={"key": "autofill_profile", "value": echo or json.loads(request.read())["value"]},
        )
    )
    return put


def _sent(route):
    return json.loads(route.calls.last.request.read())["value"]


@respx.mock
def test_personal_merges_by_key_and_other_sections_stay_as_stored():
    put = _mock_autofill()
    BackendClient(BASE).set_autofill_profile({"personal": {"city": "Leeds", "phone": "+44 1"}})
    sent = _sent(put)
    assert sent["personal"] == {"first_name": "Ana", "city": "Leeds", "phone": "+44 1"}
    assert sent["preferences"] == _STORED["preferences"]
    assert sent["custom"] == _STORED["custom"]
    assert sent["eeo"] == _STORED["eeo"]


@respx.mock
def test_a_null_removes_that_key():
    put = _mock_autofill()
    BackendClient(BASE).set_autofill_profile({"personal": {"city": None}})
    assert _sent(put)["personal"] == {"first_name": "Ana"}


@respx.mock
def test_work_permits_merge_by_market_and_by_answer_and_send_only_the_map():
    put = _mock_autofill()
    BackendClient(BASE).set_autofill_profile({
        "work_auth_by_country": {
            "UK": {"authorized_now": True, "sponsorship_now": False},
            "US": {"sponsorship_future": False},
        }
    })
    sent = _sent(put)
    assert sent["work_auth_by_country"] == {
        "US": {"status": "citizen", "authorized_now": True, "sponsorship_future": False},
        "UK": {"authorized_now": True, "sponsorship_now": False},
    }
    assert "work_auth" not in sent
    assert "work_auth_market" not in sent


@respx.mock
def test_a_null_market_is_sent_as_null_so_the_server_removes_it():
    put = _mock_autofill()
    BackendClient(BASE).set_autofill_profile({"work_auth_by_country": {"US": None}})
    assert _sent(put)["work_auth_by_country"] == {"US": None}


@respx.mock
def test_lists_replace_the_stored_list_whole():
    put = _mock_autofill()
    BackendClient(BASE).set_autofill_profile({
        "custom": [{"question": "Q2", "answer": "A2"}],
        "languages": [{"language": "French", "native": True}],
        "education": [],
    })
    sent = _sent(put)
    assert sent["custom"] == [{"question": "Q2", "answer": "A2"}]
    assert sent["languages"] == [{"language": "French", "native": True}]
    assert sent["education"] == []


@respx.mock
@pytest.mark.parametrize("section", ["eeo", "stale_answers", "work_auth"])
def test_a_section_outside_the_list_is_refused_and_nothing_is_written(section):
    put = _mock_autofill()
    with pytest.raises(BackendError, match=section):
        BackendClient(BASE).set_autofill_profile({section: {"gender": "male"}})
    assert not put.called


@respx.mock
def test_the_response_never_carries_eeo_even_when_the_server_echoes_it():
    _mock_autofill(echo={**_STORED, "personal": {"first_name": "Ana"}})
    out = BackendClient(BASE).set_autofill_profile({"personal": {"city": None}})
    assert "eeo" not in out
    assert out["personal"] == {"first_name": "Ana"}


@respx.mock
def test_job_preferences_change_only_the_fields_passed():
    respx.get(f"{BASE}/api/settings/job-preferences").mock(
        return_value=httpx.Response(200, json={"key": "job_preferences", "value": {
            "favored_roles": [{"role": None, "label": "Nurse", "category": None}],
            "role_categories": [],
            "locations": ["Lyon"], "remote": "hybrid", "notes": "n",
            "years_experience": 4, "employment_types": [], "min_salary": None,
        }})
    )
    put = respx.put(f"{BASE}/api/settings/job-preferences").mock(
        side_effect=lambda request: httpx.Response(
            200, json={"key": "job_preferences", "value": json.loads(request.read())["value"]})
    )
    out = BackendClient(BASE).set_job_preferences({"remote": "remote", "notes": ""})
    sent = _sent(put)
    assert sent["remote"] == "remote"
    assert sent["notes"] == ""
    assert sent["locations"] == ["Lyon"]
    assert sent["favored_roles"] == [{"role": None, "label": "Nurse", "category": None}]
    assert "role_categories" not in sent  # derived on the server, never sent
    assert out["remote"] == "remote"


def _mock_market():
    respx.get(f"{BASE}/api/settings/market").mock(
        return_value=httpx.Response(200, json={"key": "market", "home": "US", "apply_in": ["US", "CA"]})
    )
    return respx.put(f"{BASE}/api/settings/market").mock(
        side_effect=lambda request: httpx.Response(200, json={
            "key": "market", **json.loads(request.read())["value"], "currency": "GBP",
        })
    )


def _mock_money():
    respx.get(f"{BASE}/api/settings/money").mock(
        return_value=httpx.Response(200, json={"key": "money", "home_currency": "USD", "value": {
            "home_currency": None, "period": "month", "show_posted": False, "hours_per_year": 1900,
        }})
    )
    return respx.put(f"{BASE}/api/settings/money").mock(
        side_effect=lambda request: httpx.Response(200, json={
            "key": "money",
            "value": json.loads(request.read())["value"],
            "home_currency": json.loads(request.read())["value"]["home_currency"] or "GBP",
        })
    )


@respx.mock
def test_set_markets_moves_home_and_keeps_apply_in_and_money_untouched():
    market_put = _mock_market()
    money_put = _mock_money()
    out = BackendClient(BASE).set_markets(home="UK")
    assert _sent(market_put) == {"home": "UK", "apply_in": ["US", "CA"]}
    assert not money_put.called
    assert out == {"home": "UK", "apply_in": ["US", "CA"], "home_currency": "USD"}


@respx.mock
def test_set_markets_writes_only_the_currency_and_keeps_every_other_money_field():
    market_put = _mock_market()
    money_put = _mock_money()
    out = BackendClient(BASE).set_markets(home_currency="EUR")
    assert not market_put.called
    assert _sent(money_put) == {
        "home_currency": "EUR", "period": "month", "show_posted": False, "hours_per_year": 1900,
    }
    assert out == {"home": "US", "apply_in": ["US", "CA"], "home_currency": "EUR"}


@respx.mock
def test_an_empty_currency_follows_where_you_live():
    _mock_market()
    money_put = _mock_money()
    BackendClient(BASE).set_markets(home_currency="")
    assert _sent(money_put)["home_currency"] is None


@respx.mock
def test_set_persona_replaces_the_text():
    put = respx.put(f"{BASE}/api/settings/persona").mock(
        return_value=httpx.Response(200, json={"key": "persona", "value": "Builds calm teams."})
    )
    out = BackendClient(BASE).set_persona("Builds calm teams.")
    assert json.loads(put.calls.last.request.read()) == {"value": "Builds calm teams."}
    assert out == {"key": "persona", "value": "Builds calm teams."}
