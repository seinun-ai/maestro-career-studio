"""An agent's profile saves (MCP set_autofill_profile, set_job_preferences, set_markets) merge on the
server: `PATCH /api/settings/{autofill,job-preferences,market}` read the setting, lay the changes over
it and write it back in one transaction, so a save made by another writer (a Companion learn, a web
edit) between an agent's read and its write is never erased. The web's and the Companion's PUTs are
unchanged: they still replace the whole setting."""

import json
import threading

import pytest

from app.config import settings
from app.db import SessionLocal
from app.services import autofill_profile, market_settings, money_settings

PROFILE = {
    "personal": {"first_name": "Ana", "city": "Lyon"},
    "preferences": {"notice_period": "2 weeks"},
    "eeo": {"gender": "female"},
    "custom": [{"question": "Q", "answer": "A"}],
    "work_auth_by_country": {"US": {"status": "citizen", "authorized_now": True}},
}


@pytest.fixture(autouse=True)
def settings_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "settings_dir", tmp_path)
    return tmp_path


def _stored_profile(settings_dir):
    return json.loads((settings_dir / autofill_profile.AUTOFILL_FILE).read_text())


def _patch(client, route, value):
    return client.patch(f"/api/settings/{route}", json={"value": value})


# ---------- form answers ----------


def test_answers_merge_key_by_key_and_other_sections_stay_as_stored(client, settings_dir):
    client.put("/api/settings/autofill", json={"value": PROFILE})
    saved = _patch(client, "autofill", {"personal": {"city": "Leeds", "phone": "+44 1"}})
    assert saved.status_code == 200, saved.text
    stored = _stored_profile(settings_dir)
    assert stored["personal"] == {"first_name": "Ana", "city": "Leeds", "phone": "+44 1"}
    assert stored["preferences"] == PROFILE["preferences"]
    assert stored["custom"] == PROFILE["custom"]
    assert stored["eeo"] == PROFILE["eeo"]  # the user's, written back as it was
    # The read view's projection of the home set is never stored as a second copy.
    assert "work_auth" not in stored and "work_auth_market" not in stored
    assert stored["work_auth_by_country"] == PROFILE["work_auth_by_country"]
    assert saved.json()["key"] == "autofill_profile"
    assert saved.json()["value"]["personal"]["city"] == "Leeds"


def test_a_null_removes_that_key(client, settings_dir):
    client.put("/api/settings/autofill", json={"value": PROFILE})
    _patch(client, "autofill", {"personal": {"city": None}})
    assert _stored_profile(settings_dir)["personal"] == {"first_name": "Ana"}


def test_work_permits_merge_by_market_and_by_answer(client, settings_dir):
    client.put("/api/settings/autofill", json={"value": PROFILE})
    _patch(client, "autofill", {"work_auth_by_country": {
        "UK": {"authorized_now": True, "sponsorship_now": False},
        "US": {"sponsorship_future": False},
    }})
    assert _stored_profile(settings_dir)["work_auth_by_country"] == {
        "US": {"status": "citizen", "authorized_now": True, "sponsorship_future": False},
        "UK": {"authorized_now": True, "sponsorship_now": False},
    }


def test_a_null_market_loses_its_answers_and_a_market_left_out_keeps_them(client, settings_dir):
    client.put("/api/settings/autofill", json={"value": {
        **PROFILE, "work_auth_by_country": {**PROFILE["work_auth_by_country"], "CA": {"authorized_now": False}},
    }})
    _patch(client, "autofill", {"work_auth_by_country": {"US": None}})
    assert _stored_profile(settings_dir)["work_auth_by_country"] == {"CA": {"authorized_now": False}}


def test_education_and_languages_replace_the_stored_list_whole(client, settings_dir):
    client.put("/api/settings/autofill", json={"value": {
        **PROFILE, "languages": [{"language": "Portuguese", "fluent": True}],
        "education": [{"school": "Example college"}],
    }})
    _patch(client, "autofill", {"languages": [{"language": "French", "native": True}], "education": []})
    stored = _stored_profile(settings_dir)
    assert stored["languages"] == [{"language": "French", "native": True}]
    assert stored["education"] == []


# `custom` is the Companion's learn store ("pause once, learn forever"), so an agent's save adds or
# replaces saved answers by question and never drops one it did not name: a whole-list replace built
# from a read taken before a learn would erase the learned answer. Deleting one stays the user's.
_NOTICE = {"question": "Notice period?", "answer": "2 weeks"}


def _custom_after(client, settings_dir, stored, sent):
    client.put("/api/settings/autofill", json={"value": {**PROFILE, "custom": stored}})
    saved = _patch(client, "autofill", {"custom": sent})
    assert saved.status_code == 200, saved.text
    return _stored_profile(settings_dir)["custom"]


def test_a_saved_answer_to_the_same_question_is_replaced_in_place(client, settings_dir):
    """The question key is the Companion's (`ns.normLabel`: case and runs of spaces ignored)."""
    sent = {"question": "  notice   PERIOD? ", "answer": "1 month"}
    assert _custom_after(client, settings_dir, [_NOTICE, {"question": "Q", "answer": "A"}], [sent]) == [
        sent, {"question": "Q", "answer": "A"},
    ]


def test_a_new_question_is_added_and_every_other_saved_answer_stays(client, settings_dir):
    sent = [{"question": "Q2", "answer": "A2"}]
    assert _custom_after(client, settings_dir, [_NOTICE], sent) == [_NOTICE, *sent]


def test_an_empty_list_removes_nothing(client, settings_dir):
    assert _custom_after(client, settings_dir, [_NOTICE], []) == [_NOTICE]


def test_an_answer_held_for_one_company_or_city_is_its_own_entry(client, settings_dir):
    """The Companion keeps an answer that names this job's company or city apart from the general
    one (`only_for`, `only_for_kind`); the key carries that scope."""
    porto = {"question": "Willing to relocate to Porto?", "answer": "Yes",
             "only_for": "Porto", "only_for_kind": "city"}
    general = {"question": "Willing to relocate to Porto?", "answer": "No"}
    assert _custom_after(client, settings_dir, [porto], [general]) == [porto, general]
    again = {**porto, "answer": "Only with support"}
    assert _custom_after(client, settings_dir, [porto, general], [again]) == [again, general]


def test_an_entry_without_a_question_is_added(client, settings_dir):
    sent = [{"answer": "An answer with no question"}, {"question": "  ", "answer": "Blank"}]
    assert _custom_after(client, settings_dir, [_NOTICE], sent) == [_NOTICE, *sent]


def test_a_companion_learn_between_an_agents_read_and_its_custom_save_is_kept(client, settings_dir):
    """The agent reads custom = [A], the Companion learns B, the agent sends [A, C]: B stays."""
    a, c = {"question": "Q", "answer": "A"}, {"question": "Q3", "answer": "C"}
    client.put("/api/settings/autofill", json={"value": {**PROFILE, "custom": [a]}})
    agents_read = client.get("/api/settings/autofill").json()["value"]

    current = client.get("/api/settings/autofill").json()["value"]
    learned = {"question": "Notice period at your current job?", "answer": "One month"}
    client.put("/api/settings/autofill", json={"value": {**current, "custom": [*current["custom"], learned]}})

    # The old flow PUT its stale read with the list replaced whole: the learn is gone.
    assert learned not in {**agents_read, "custom": [a, c]}["custom"]

    assert _patch(client, "autofill", {"custom": [a, c]}).status_code == 200
    assert _stored_profile(settings_dir)["custom"] == [a, learned, c]


@pytest.mark.parametrize("changes", [
    {"eeo": {"gender": "male"}},
    {"stale_answers": ["eeo.veteran_status"]},
    {"work_auth": {"authorized_now": True}},
    {"personal": ["not", "answers"]},
    {"custom": {"question": "Q"}},
    {"work_auth_by_country": {"UK": "yes"}},
])
def test_a_section_outside_the_list_or_of_the_wrong_shape_writes_nothing(client, settings_dir, changes):
    client.put("/api/settings/autofill", json={"value": PROFILE})
    before = _stored_profile(settings_dir)
    refused = _patch(client, "autofill", changes)
    assert refused.status_code == 422, refused.text
    assert _stored_profile(settings_dir) == before


def test_the_diversity_refusal_names_where_those_answers_live(client):
    refused = _patch(client, "autofill", {"eeo": {"gender": "male"}})
    assert "eeo" in refused.json()["detail"] and "Profile" in refused.json()["detail"]


def test_the_web_put_still_replaces_the_whole_profile(client, settings_dir):
    """The web's own save is unchanged: a PUT without custom drops custom (its editor sends the
    whole profile)."""
    client.put("/api/settings/autofill", json={"value": PROFILE})
    client.put("/api/settings/autofill", json={"value": {"personal": {"first_name": "Ana"}}})
    stored = _stored_profile(settings_dir)
    assert "custom" not in stored and "preferences" not in stored


def test_a_companion_learn_between_an_agents_read_and_write_is_kept(client, settings_dir):
    """The race the old client had: it read the profile, merged, and PUT the whole thing back, so an
    answer the Companion learned into `custom` between the read and the PUT was erased. The PATCH
    merges against the value stored when it writes."""
    client.put("/api/settings/autofill", json={"value": PROFILE})
    agents_read = client.get("/api/settings/autofill").json()["value"]

    # The Companion's pause row learns an answer: read the profile, add the row, PUT it back.
    current = client.get("/api/settings/autofill").json()["value"]
    learned = {"question": "Notice period at your current job?", "answer": "One month"}
    client.put("/api/settings/autofill", json={"value": {**current, "custom": [*current["custom"], learned]}})

    changes = {"personal": {"city": "Porto"}}
    # Under the old flow the agent PUT its stale read with the change laid over: the learn is gone.
    old_body = autofill_profile.merged_profile(agents_read, changes)
    assert learned not in old_body["custom"]

    assert _patch(client, "autofill", changes).status_code == 200
    stored = _stored_profile(settings_dir)
    assert learned in stored["custom"]
    assert stored["personal"]["city"] == "Porto"


def test_another_save_cannot_land_between_a_patchs_read_and_its_write(db_session, monkeypatch):
    """The read, the merge and the write are one transaction under SQLite's write lock: a second
    save that starts while the first is merging waits, then merges onto the first's result, so
    both land. Without the lock the second save would land in the gap and the first, writing its
    stale merge, would erase it."""
    autofill_profile.set_profile({"personal": {"first_name": "Sam"}}, db_session)
    real_merge = autofill_profile.merged_profile
    second_done = threading.Event()
    errors: list[BaseException] = []

    def second_save():
        try:
            with SessionLocal() as session:
                autofill_profile.patch_profile({"preferences": {"notice_period": "1 month"}}, session)
        except BaseException as exc:  # surfaced below: an assertion in a thread is lost otherwise
            errors.append(exc)
        finally:
            second_done.set()

    worker = threading.Thread(target=second_save)

    def merge_while_another_save_tries(stored, changes):
        if not worker.is_alive() and not second_done.is_set():
            worker.start()
            # Every chance for the second save to land between this save's read and write.
            second_done.wait(timeout=0.5)
        return real_merge(stored, changes)

    monkeypatch.setattr(autofill_profile, "merged_profile", merge_while_another_save_tries)
    with SessionLocal() as session:
        autofill_profile.patch_profile({"personal": {"city": "Porto"}}, session)
    worker.join(timeout=35)
    assert not errors, errors
    db_session.expire_all()
    stored = autofill_profile.peek_profile(db_session)
    assert stored["personal"] == {"first_name": "Sam", "city": "Porto"}
    assert stored["preferences"] == {"notice_period": "1 month"}


# ---------- job preferences ----------


def _prefs(client):
    return client.get("/api/settings/job-preferences").json()["value"]


def test_preferences_change_only_the_fields_passed(client):
    client.put("/api/settings/job-preferences", json={"value": {
        "favored_roles": [{"label": "Pastry chef"}], "locations": ["Lyon"], "remote": "hybrid",
        "notes": "n", "years_experience": 4,
    }})
    saved = _patch(client, "job-preferences", {"remote": "remote", "notes": ""})
    assert saved.status_code == 200, saved.text
    value = _prefs(client)
    assert value["remote"] == "remote" and value["notes"] == ""
    assert value["locations"] == ["Lyon"] and value["years_experience"] == 4
    assert value["favored_roles"] == [{"role": None, "label": "Pastry chef", "category": None}]
    assert saved.json()["value"]["remote"] == "remote"


def test_an_empty_list_clears_it_and_roles_project_their_categories(client):
    client.put("/api/settings/job-preferences", json={"value": {"locations": ["Lyon"]}})
    saved = _patch(client, "job-preferences", {
        "locations": [], "favored_roles": [{"role": "product_manager"}],
    }).json()["value"]
    assert saved["locations"] == []
    assert saved["role_categories"] == ["product_manager"]


def test_a_web_edit_between_an_agents_read_and_write_is_kept(client):
    client.put("/api/settings/job-preferences", json={"value": {"locations": ["Lyon"]}})
    client.put("/api/settings/job-preferences", json={"value": {
        "locations": ["Lyon"], "favored_roles": [{"label": "Pastry chef"}],
    }})
    _patch(client, "job-preferences", {"remote": "onsite"})
    value = _prefs(client)
    assert value["favored_roles"] == [{"role": None, "label": "Pastry chef", "category": None}]
    assert value["remote"] == "onsite"


def test_an_unknown_role_is_a_422_naming_the_closest_and_saves_nothing(client):
    client.put("/api/settings/job-preferences", json={"value": {"notes": "kept"}})
    refused = _patch(client, "job-preferences", {"favored_roles": [{"role": "product_manger"}], "notes": "x"})
    assert refused.status_code == 422, refused.text
    assert "closest" in json.dumps(refused.json()) and "product_manager" in json.dumps(refused.json())
    assert _prefs(client)["notes"] == "kept"


@pytest.mark.parametrize("field", ["role_categories", "seniority"])
def test_a_field_that_is_not_a_preference_is_refused(client, field):
    refused = _patch(client, "job-preferences", {field: ["product_manager"]})
    assert refused.status_code == 422, refused.text
    assert field in refused.json()["detail"]


# ---------- where you live and apply, and the currency pay reads in ----------


def _place(client):
    market = client.get("/api/settings/market").json()
    money = client.get("/api/settings/money").json()
    return market["home"], market["apply_in"], money["value"]


def _seed_place(client):
    client.put("/api/settings/market", json={"value": {"home": "US", "apply_in": ["US", "CA"]}})
    client.put("/api/settings/money", json={"value": {
        "home_currency": None, "period": "month", "show_posted": False, "hours_per_year": 1900,
    }})


def test_home_alone_keeps_apply_in_and_money_as_stored(client):
    _seed_place(client)
    saved = _patch(client, "market", {"home": "UK"})
    assert saved.status_code == 200, saved.text
    home, apply_in, money = _place(client)
    assert (home, apply_in) == ("UK", ["US", "CA"])
    assert money == {"home_currency": None, "period": "month", "show_posted": False, "hours_per_year": 1900}
    body = saved.json()
    assert (body["home"], body["apply_in"], body["home_currency"]) == ("UK", ["US", "CA"], "GBP")


def test_the_currency_alone_keeps_every_other_money_field_and_the_market(client):
    _seed_place(client)
    saved = _patch(client, "market", {"home_currency": "eur"}).json()
    home, apply_in, money = _place(client)
    assert (home, apply_in) == ("US", ["US", "CA"])
    assert money == {"home_currency": "EUR", "period": "month", "show_posted": False, "hours_per_year": 1900}
    assert saved["home_currency"] == "EUR"


def test_an_empty_currency_follows_where_you_live_again(client):
    _seed_place(client)
    _patch(client, "market", {"home_currency": "EUR"})
    saved = _patch(client, "market", {"home_currency": ""}).json()
    assert _place(client)[2]["home_currency"] is None
    assert saved["home_currency"] == "USD"


def test_no_field_reads_the_current_values_and_writes_nothing(client, settings_dir):
    _seed_place(client)
    mirrors = {p.name: p.read_text() for p in settings_dir.iterdir()}
    body = _patch(client, "market", {}).json()
    assert (body["home"], body["apply_in"], body["home_currency"]) == ("US", ["US", "CA"], "USD")
    assert {p.name: p.read_text() for p in settings_dir.iterdir()} == mirrors


@pytest.mark.parametrize("changes,words", [
    ({"home": "UK", "home_currency": "XYZ"}, "home_currency must be an ISO 4217 code"),
    ({"home": "ZZ", "home_currency": "EUR"}, "market must be one of"),
    ({"apply_in": ["UK", "ZZ"], "home_currency": "EUR"}, "market must be one of"),
])
def test_a_bad_field_is_a_422_with_the_same_words_and_nothing_lands(client, changes, words):
    """The old client wrote the market, then the money: a bad currency after a home move reported an
    error though the move had landed. Both are checked before either is written."""
    _seed_place(client)
    before = _place(client)
    refused = _patch(client, "market", changes)
    assert refused.status_code == 422, refused.text
    assert words in json.dumps(refused.json())
    assert _place(client) == before


def test_market_and_money_are_one_transaction(client, monkeypatch):
    """A failure writing the money after the market rolls the market back too."""
    _seed_place(client)
    before = _place(client)

    def fail(*args, **kwargs):
        raise RuntimeError("the disk is full")

    monkeypatch.setattr(money_settings, "set_settings", fail)
    with pytest.raises(RuntimeError, match="disk is full"):
        _patch(client, "market", {"home": "UK", "home_currency": "EUR"})
    assert _place(client) == before


def test_a_home_move_still_pins_a_one_set_permit_answer_to_the_old_home(client, settings_dir, db_session):
    """set_market's own rule rides along: a legacy top-level `work_auth` is pinned to the home it
    was read as before the home moves, in the same transaction."""
    from app.services import text_settings

    _seed_place(client)
    text_settings.set_text(autofill_profile.AUTOFILL_KEY, autofill_profile.AUTOFILL_FILE,
                           json.dumps({"work_auth": {"authorized_now": True}}), db_session)
    _patch(client, "market", {"home": "UK"})
    assert _stored_profile(settings_dir) == {"work_auth_by_country": {"US": {"authorized_now": True}}}
    assert market_settings.peek_market(db_session).home == "UK"


# ---------- through the MCP tools, against these routes ----------


def test_set_autofill_profile_adds_saved_answers_beside_a_companion_learn(client, mcp_tools, settings_dir):
    client.put("/api/settings/autofill", json={"value": PROFILE})
    current = client.get("/api/settings/autofill").json()["value"]
    learned = {"question": "Notice period at your current job?", "answer": "One month"}
    client.put("/api/settings/autofill", json={"value": {**current, "custom": [*current["custom"], learned]}})

    mcp_tools.set_autofill_profile(custom=[{"question": "q", "answer": "A, edited"}])
    assert _stored_profile(settings_dir)["custom"] == [{"question": "q", "answer": "A, edited"}, learned]


def test_set_autofill_profile_keeps_a_companion_learn_and_never_returns_eeo(client, mcp_tools, settings_dir):
    client.put("/api/settings/autofill", json={"value": PROFILE})
    current = client.get("/api/settings/autofill").json()["value"]
    learned = {"question": "Notice period at your current job?", "answer": "One month"}
    client.put("/api/settings/autofill", json={"value": {**current, "custom": [*current["custom"], learned]}})

    out = mcp_tools.set_autofill_profile(personal={"city": "Porto"})
    assert "eeo" not in out["profile"]
    assert out["profile"]["personal"]["city"] == "Porto"
    stored = _stored_profile(settings_dir)
    assert learned in stored["custom"] and stored["eeo"] == PROFILE["eeo"]


def test_set_job_preferences_changes_one_field(client, mcp_tools):
    client.put("/api/settings/job-preferences", json={"value": {"locations": ["Lyon"]}})
    assert mcp_tools.set_job_preferences(remote="onsite")["remote"] == "onsite"
    assert _prefs(client)["locations"] == ["Lyon"]


def test_set_markets_with_a_bad_currency_moves_nothing(client, mcp_tools):
    from mcp.server.fastmcp.exceptions import ToolError

    _seed_place(client)
    before = _place(client)
    with pytest.raises(ToolError, match="ISO 4217"):
        mcp_tools.set_markets(home="UK", home_currency="XYZ")
    assert _place(client) == before
    out = mcp_tools.set_markets()
    assert (out["home"], out["apply_in"], out["home_currency"]) == ("US", ["US", "CA"], "USD")
