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


@pytest.mark.parametrize("market", ["us", " Us "])
def test_a_market_key_in_another_case_merges_into_that_markets_stored_answers(client, settings_dir, market):
    # The store keys a market as "US" ("uk " is "UK"); the merge reads the stored answers by that key too.
    client.put("/api/settings/autofill", json={"value": PROFILE})
    _patch(client, "autofill", {"work_auth_by_country": {market: {"sponsorship_future": False}}})
    assert _stored_profile(settings_dir)["work_auth_by_country"] == {
        "US": {"status": "citizen", "authorized_now": True, "sponsorship_future": False},
    }


def test_a_null_market_loses_its_answers_and_a_market_left_out_keeps_them(client, settings_dir):
    client.put("/api/settings/autofill", json={"value": {
        **PROFILE, "work_auth_by_country": {**PROFILE["work_auth_by_country"], "CA": {"authorized_now": False}},
    }})
    _patch(client, "autofill", {"work_auth_by_country": {"US": None}})
    assert _stored_profile(settings_dir)["work_auth_by_country"] == {"CA": {"authorized_now": False}}


# ---------- country answers and citizenships ----------


def test_answers_by_country_merge_per_market(client, settings_dir):
    client.put("/api/settings/autofill", json={"value": {
        "answers_by_country": {"IN": {"current_ctc": "1800000"}, "AE": {"in_country_now": True}}}})
    _patch(client, "autofill", {"answers_by_country": {"IN": {"expected_pay": "2400000"}}})
    stored = _stored_profile(settings_dir)["answers_by_country"]
    assert stored == {"IN": {"current_ctc": "1800000", "expected_pay": "2400000"},
                      "AE": {"in_country_now": True}}


def test_a_null_country_answer_goes_and_a_null_country_loses_them_all(client, settings_dir):
    client.put("/api/settings/autofill", json={"value": {
        "answers_by_country": {"IN": {"current_ctc": "1", "expected_pay": "2"}, "AE": {"in_country_now": True}}}})
    _patch(client, "autofill", {"answers_by_country": {"in": {"current_ctc": None}, "AE": None}})
    assert _stored_profile(settings_dir)["answers_by_country"] == {"IN": {"expected_pay": "2"}}


def test_a_put_keeps_the_country_answers_it_does_not_send(client, settings_dir):
    """As for work permits: a client that does not know a country cannot have meant to remove its
    answers, and a market it sends replaces that market's (null removes them)."""
    client.put("/api/settings/autofill", json={"value": {
        "answers_by_country": {"IN": {"current_ctc": "1"}, "AE": {"in_country_now": True}}}})
    client.put("/api/settings/autofill", json={"value": {"personal": {"first_name": "Ana"}}})
    assert _stored_profile(settings_dir)["answers_by_country"] == {
        "IN": {"current_ctc": "1"}, "AE": {"in_country_now": True}}
    client.put("/api/settings/autofill", json={"value": {
        "answers_by_country": {"ae ": {"uae_driving_licence": False}, "IN": None}}})
    assert _stored_profile(settings_dir)["answers_by_country"] == {"AE": {"uae_driving_licence": False}}


def test_an_unknown_country_answer_is_refused(client):
    r = _patch(client, "autofill", {"answers_by_country": {"DE": {"current_ctc": "1"}}})
    assert r.status_code == 422 and "current_ctc" in r.text
    assert "expected_pay" in r.text  # names what Germany asks


def test_a_null_clears_a_stale_country_answer_or_market(client, settings_dir):
    """A null only removes, so it is never refused: an answer the market no longer asks, or a market
    Maestro no longer keeps, can be cleared (the web's PUT stores what it is sent)."""
    client.put("/api/settings/autofill", json={"value": {"answers_by_country": {
        "DE": {"current_ctc": "1", "expected_pay": "2"}, "FR": {"expected_pay": "3"}}}})
    r = _patch(client, "autofill", {"answers_by_country": {"DE": {"current_ctc": None}, "FR": None}})
    assert r.status_code == 200, r.text
    assert _stored_profile(settings_dir)["answers_by_country"] == {"DE": {"expected_pay": "2"}}
    assert _patch(client, "autofill", {"answers_by_country": {"FR": {"expected_pay": None}}}).status_code == 200


def test_country_answers_are_served_keyed_by_market(client, db_session):
    """As permits are: a hand-edited "in " is India's answers."""
    from app.services import text_settings

    text_settings.set_text(autofill_profile.AUTOFILL_KEY, autofill_profile.AUTOFILL_FILE,
                           json.dumps({"answers_by_country": {"in ": {"current_ctc": "1"}, "AE": "no"}}),
                           db_session)
    served = client.get("/api/settings/autofill").json()["value"]
    assert served["answers_by_country"] == {"IN": {"current_ctc": "1"}}


def test_a_market_maestro_does_not_keep_is_refused(client):
    r = _patch(client, "autofill", {"answers_by_country": {"FR": {"expected_pay": "1"}}})
    assert r.status_code == 422 and "FR" in r.text and "DE" in r.text  # names the markets


def test_a_status_from_another_country_is_refused(client):
    r = _patch(client, "autofill", {"work_auth_by_country": {"CA": {"status": "h1b"}}})
    assert r.status_code == 422 and "open_work_permit" in r.text  # names CA's choices


def test_a_status_where_no_status_is_asked_is_refused(client):
    r = _patch(client, "autofill", {"work_auth_by_country": {"UK": {"status": "citizen"}}})
    assert r.status_code == 422 and "UK asks no status" in r.text and "CA" in r.text


def test_a_status_for_a_market_maestro_does_not_keep_says_so(client):
    r = _patch(client, "autofill", {"work_auth_by_country": {"FR": {"status": "citizen"}}})
    assert r.status_code == 422 and "FR is not a market Maestro keeps" in r.text


def test_a_status_from_the_markets_own_list_or_a_null_is_saved(client, settings_dir):
    client.put("/api/settings/autofill", json={"value": PROFILE})
    assert _patch(client, "autofill", {"work_auth_by_country": {
        "ca": {"status": "pgwp"}, "US": {"status": None}}}).status_code == 200
    stored = _stored_profile(settings_dir)["work_auth_by_country"]
    assert stored["CA"] == {"status": "pgwp"} and "status" not in stored["US"]


def test_citizenships_are_iso_codes(client, settings_dir):
    _patch(client, "autofill", {"personal": {"citizenships": ["in", "United Kingdom", "IN"]}})
    assert _stored_profile(settings_dir)["personal"]["citizenships"] == ["IN", "GB"]
    assert _patch(client, "autofill", {"personal": {"citizenships": ["Atlantis"]}}).status_code == 422


@pytest.mark.parametrize("citizenships", ["IN", [None], [3]])
def test_citizenships_take_a_list_of_countries(client, citizenships):
    r = _patch(client, "autofill", {"personal": {"citizenships": citizenships}})
    assert r.status_code == 422 and "citizenships" in r.text


def test_a_web_save_stores_citizenships_as_iso_codes_too(client, settings_dir):
    """The web sends codes from its picker; a save stores them in one form whichever writer sent
    them, and an entry that names no country is no answer."""
    client.put("/api/settings/autofill", json={"value": {"personal": {"citizenships": ["ie", "Ireland", "Narnia", "uk"]}}})
    assert _stored_profile(settings_dir)["personal"]["citizenships"] == ["IE", "GB"]


def test_an_old_profile_reads_unchanged(client):
    client.put("/api/settings/autofill", json={"value": PROFILE})
    assert client.get("/api/settings/autofill").json()["value"]["work_auth_by_country"] == \
        PROFILE["work_auth_by_country"]


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
    {"answers_by_country": {"IN": "yes"}},
    {"answers_by_country": ["IN"]},
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
    from mcp.server.mcpserver.exceptions import ToolError

    _seed_place(client)
    before = _place(client)
    with pytest.raises(ToolError, match="ISO 4217"):
        mcp_tools.set_markets(home="UK", home_currency="XYZ")
    assert _place(client) == before
    out = mcp_tools.set_markets()
    assert (out["home"], out["apply_in"], out["home_currency"]) == ("US", ["US", "CA"], "USD")


# ---------- citizenships and each country's own answers, for agents (MCP, plan Task 3.9) ----------

_COUNTRIES = {
    "personal": {"first_name": "Ana", "citizenships": ["FR"]},
    "preferences": {"desired_salary": "90000", "current_ctc": "1500000"},
    "answers_by_country": {"IN": {"current_ctc": "1800000", "expected_pay": "2400000"},
                           "NL": {"expected_pay": "4500"}},
}


def _apply_in(db_session, *markets_):
    from app.schemas.market_settings import MarketSetting

    market_settings.set_market(MarketSetting(home="IN", apply_in=list(markets_)), db_session)


def _lets_the_companion_fill_agreements(db_session):
    from app.schemas.eeo_consent import EeoConsent
    from app.services import eeo_consent
    from app.services.eeo_consent import CURRENT_POLICY_VERSION

    eeo_consent.EEO_CONSENT.set(
        EeoConsent(consent_forms=True, policy_version=CURRENT_POLICY_VERSION), db_session)


def _dutch_application(db_session) -> str:
    from app.models.application import Application
    from tests.test_proposals_models import _mk_job

    job = _mk_job(db_session, company="Acme", country_code="NL")
    application = Application(job_id=job.id, base_resume="hybrid", customized_json={"contact": {"name": "Ana"}})
    db_session.add(application)
    db_session.commit()
    return str(application.id)


def test_without_a_job_an_agent_reads_every_countrys_answers_and_no_current_pay(client, mcp_tools, db_session):
    """No job, no country to fold: the generic answers stay in their slots and every market's own answers
    come under answers_by_country, through the same gate as the rest, so current pay (flat and India's) stays
    behind the agreement permission. Citizenships read as country names."""
    _apply_in(db_session, "IN", "NL")
    client.put("/api/settings/autofill", json={"value": _COUNTRIES})

    profile = mcp_tools.get_autofill_profile()["profile"]
    assert profile["answers_by_country"] == {"IN": {"expected_pay": "2400000"}, "NL": {"expected_pay": "4500"}}
    assert profile["preferences"] == {"desired_salary": "90000"}
    assert profile["personal"]["citizenships"] == ["France"]
    assert "1800000" not in json.dumps(profile) and "1500000" not in json.dumps(profile)

    _lets_the_companion_fill_agreements(db_session)
    profile = mcp_tools.get_autofill_profile()["profile"]
    assert profile["answers_by_country"]["IN"] == {"current_ctc": "1800000", "expected_pay": "2400000"}
    assert profile["preferences"]["current_ctc"] == "1500000"


def test_with_a_job_an_agent_reads_that_countrys_view(client, mcp_tools, db_session):
    """A Dutch job's view: the Dutch pay folded over the generic slot (country_answered names it), what the
    French citizenship settles there, and no country's map of answers."""
    _apply_in(db_session, "IN", "NL")
    client.put("/api/settings/autofill", json={"value": _COUNTRIES})

    out = mcp_tools.get_autofill_profile(application_id=_dutch_application(db_session))
    profile = out["profile"]
    assert profile["preferences"]["desired_salary"] == "4500"
    assert profile["country_answered"] == ["preferences.desired_salary"]
    assert profile["work_auth_market"] == "NL" and profile["work_auth"]["authorized_now"] is True
    assert "answers_by_country" not in profile and "2400000" not in json.dumps(profile)
    assert out["questions"]["chosen"] is True
    assert out["questions"]["countries"]["NL"]["derived"]["authorized_now"] == {"value": True, "via": "FR"}


def test_an_agent_saves_citizenships_and_country_answers(client, mcp_tools, db_session, settings_dir):
    _apply_in(db_session, "IN", "AE")
    mcp_tools.set_autofill_profile(
        personal={"citizenships": ["in", "United Kingdom"]},
        preferences={"notice_days": 60, "serving_notice": True, "last_working_day": "2026-12-31"},
        eligibility={"experience_years": 7, "experience_months": 3},
        answers_by_country={"AE": {"expected_pay": "25000", "in_country_now": False}},
        languages=[{"language": "German", "cefr": "B1"}],
    )
    stored = _stored_profile(settings_dir)
    assert stored["personal"]["citizenships"] == ["IN", "GB"]
    assert stored["preferences"] == {"notice_days": 60, "serving_notice": True, "last_working_day": "2026-12-31"}
    assert stored["eligibility"] == {"experience_years": 7, "experience_months": 3}
    assert stored["answers_by_country"] == {"AE": {"expected_pay": "25000", "in_country_now": False}}
    assert stored["languages"] == [{"language": "German", "cefr": "B1"}]


def test_a_status_from_another_country_is_refused_naming_that_countrys(mcp_tools, settings_dir):
    from mcp.server.mcpserver.exceptions import ToolError

    with pytest.raises(ToolError, match="open_work_permit"):
        mcp_tools.set_autofill_profile(work_auth_by_country={"CA": {"status": "h1b"}})
    assert not (settings_dir / autofill_profile.AUTOFILL_FILE).exists()


def test_a_saved_profile_comes_back_without_current_pay_unless_the_user_lets_it(client, db_session):
    """Only agents save through the PATCH, so what it hands back goes through the consent gate as a read does."""
    client.put("/api/settings/autofill", json={"value": _COUNTRIES})
    echoed = _patch(client, "autofill", {"personal": {"city": "Pune"}}).json()["value"]
    assert echoed["personal"]["city"] == "Pune"
    assert "current_ctc" not in echoed["preferences"] and "current_ctc" not in echoed["answers_by_country"]["IN"]

    _lets_the_companion_fill_agreements(db_session)
    echoed = _patch(client, "autofill", {"personal": {"city": "Mumbai"}}).json()["value"]
    assert echoed["answers_by_country"]["IN"]["current_ctc"] == "1800000"
