"""Work-permit answers per country (owner decision D9, plan Task 3.6).

A form gets the answers of the country its question names; a question that
names none gets the job's country's; a job with no country gets none, so the
answer is unknown and the Companion asks once on that job. Never another
country's answers, never a default. Answers are stored per MARKET key ("UK",
not "GB") under `work_auth_by_country`; the old single `work_auth` is the home
market's, mapped when read and kept as written until the user saves.
"""

import json
from pathlib import Path

import pytest

from app.schemas.market_settings import MarketSetting
from app.services import autofill_country, autofill_profile, countries, market_settings, text_settings
from app.services.autofill_country import country_in_question, work_auth_for

REPO = Path(__file__).resolve().parents[2]

TWO = {"work_auth_by_country": {
    "DE": {"authorized_now": True, "sponsorship_now": False},
    "UK": {"authorized_now": False, "sponsorship_now": True},
}}


@pytest.fixture(autouse=True)
def _isolated_settings_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(text_settings.settings, "settings_dir", tmp_path)


# --- which country a question names ------------------------------------------------------------

def test_the_country_the_question_names_wins():
    q = "Are you legally authorised to work in the United Kingdom?"
    assert country_in_question(q, ["DE", "UK", "US"]) == "UK"
    assert work_auth_for(TWO, question=q, job_country="DE").authorized_now is False


@pytest.mark.parametrize("question, market", [
    ("Are you authorized to work in the US?", "US"),
    ("Are you authorized to work in the U.S.?", "US"),
    ("Are you authorized to work in the U.S?", "US"),
    ("Can you work in the UK without sponsorship?", "UK"),
    ("Do you have the right to work in England?", "UK"),
    ("Are you eligible to work in Northern Ireland?", "UK"),
    ("Are you eligible to work in Ireland?", "IE"),
    ("Do you need a visa to work in the Netherlands?", "NL"),
    ("Arbeitserlaubnis für Deutschland? (Germany)", "DE"),
])
def test_a_question_names_a_country_by_its_name_an_alias_or_a_capital_code(question, market):
    assert country_in_question(question, ["US", "UK", "IE", "NL", "DE"]) == market


@pytest.mark.parametrize("question", [
    "Tell us about yourself",                         # "us" is a word, only "US" in capitals is the code
    "Are you willing to relocate to San Francisco, CA?",   # CA is California as often as Canada
    "Are you authorized to work in Latin America?",   # not the United States
    "Do you live in New Mexico?",                      # a US state, not Mexico
    "Are you authorized to work here?",
    "",
])
def test_a_question_that_names_no_country_names_none(question):
    assert country_in_question(question, ["US", "UK", "CA", "DE", "IN", "AU"]) is None


def test_two_countries_named_is_no_one_country():
    q = "Are you authorized to work in the United States or Canada?"
    assert country_in_question(q, ["US", "CA"]) is None
    # Neither is answered for: "or" with a Yes in one and a No in the other has no one true answer.
    both = {"work_auth_by_country": {"US": {"authorized_now": False}, "CA": {"authorized_now": True}}}
    assert work_auth_for(both, question=q, job_country="US").authorized_now is None


def test_a_named_country_without_answers_is_unknown_not_the_job_country():
    """A German job asking about France gets no German answer: that would be a guess."""
    q = "Are you authorized to work in France?"
    assert work_auth_for(TWO, question=q, job_country="DE").authorized_now is None
    assert work_auth_for(TWO, question="Are you authorized to work in Australia?",
                         job_country="DE").authorized_now is None


def test_mentioned_in_is_the_one_parser_of_a_sentence():
    assert countries.mentioned_in("Work in Germany or the Netherlands?") == {"DE", "NL"}
    assert countries.mentioned_in("Côte d’Ivoire office") == {"CI"}
    assert countries.mentioned_in("New South Wales, Australia") == {"AU"}
    assert countries.mentioned_in("No country here") == set()


def test_aliases_for_lists_the_input_variants_of_a_code():
    assert "uk" in countries.aliases_for("GB") and "northern ireland" in countries.aliases_for("GB")
    assert countries.aliases_for("FR") == []


# --- the job's country, then nothing -----------------------------------------------------------

def test_no_country_in_the_question_uses_the_job_country_then_asks():
    profile = {"work_auth_by_country": {"DE": {"authorized_now": True}}}
    assert work_auth_for(profile, question="Authorized to work here?", job_country="DE").authorized_now is True
    assert work_auth_for(profile, question="Authorized to work here?", job_country=None).authorized_now is None


def test_a_job_country_is_iso_and_maps_to_its_market():
    """A job stores "GB"; the answers are stored under the market key "UK"."""
    assert work_auth_for(TWO, question="", job_country="GB").sponsorship_now is True
    assert autofill_country.market_for_job_country("GB") == "UK"
    assert autofill_country.market_for_job_country("FR") is None


def test_a_legacy_single_work_auth_belongs_to_the_home_market():
    legacy = {"work_auth": {"authorized_now": True}}
    assert work_auth_for(legacy, question="", job_country="US", home="US").authorized_now is True
    assert work_auth_for(legacy, question="", job_country="GB", home="US").authorized_now is None


def test_countries_authorized_is_derived_from_the_answers():
    profile = {"work_auth_by_country": {
        "US": {"authorized_now": True}, "UK": {"authorized_now": False}, "DE": {"authorized_now": True}}}
    got = work_auth_for(profile, question="", job_country="DE")
    assert got.countries_authorized == ["United States", "Germany"]
    # A list the user wrote keeps its own entries; a country it already names is not added twice.
    profile["work_auth_by_country"]["DE"]["countries_authorized"] = ["US", "CH"]
    assert work_auth_for(profile, question="", job_country="DE").countries_authorized == ["US", "CH", "Germany"]


# --- storage: per market, the legacy shape mapped when read ------------------------------------

def _stored(tmp_path) -> dict:
    return json.loads((tmp_path / "autofill.json").read_text())


def _write(db_session, profile: dict) -> None:
    text_settings.set_text(autofill_profile.AUTOFILL_KEY, autofill_profile.AUTOFILL_FILE,
                           json.dumps(profile), db_session)


def test_a_legacy_profile_reads_as_the_home_market_and_stays_as_written(db_session, tmp_path):
    market_settings.set_market(MarketSetting(home="UK", apply_in=["UK", "DE"]), db_session)
    _write(db_session, {"work_auth": {"authorized_now": True, "sponsorship_now": False}})
    view = autofill_profile.get_profile(db_session)
    assert view["work_auth_by_country"] == {"UK": {"authorized_now": True, "sponsorship_now": False}}
    assert view["work_auth"] == {"authorized_now": True, "sponsorship_now": False}  # the home set, as before
    assert _stored(tmp_path) == {"work_auth": {"authorized_now": True, "sponsorship_now": False}}
    assert autofill_profile.get_work_auth(db_session, "DE").authorized_now is None
    assert autofill_profile.get_work_auth(db_session).authorized_now is True


def test_an_editor_that_knows_one_set_saves_it_as_the_home_market(db_session, tmp_path):
    """The Settings editor and the Companion's pause row write `work_auth`: it is the home set."""
    market_settings.set_market(MarketSetting(home="UK", apply_in=["UK", "DE"]), db_session)
    autofill_profile.set_profile(TWO, db_session)
    view = autofill_profile.get_profile(db_session)
    view["work_auth"] = {**view["work_auth"], "sponsorship_now": False}   # edited in the old field only
    saved = autofill_profile.set_profile(view, db_session)
    stored = _stored(tmp_path)
    assert "work_auth" not in stored
    assert stored["work_auth_by_country"] == {"DE": TWO["work_auth_by_country"]["DE"],
                                              "UK": {"authorized_now": False, "sponsorship_now": False}}
    assert saved["work_auth"] == {"authorized_now": False, "sponsorship_now": False}


def test_an_editor_that_knows_every_country_wins_when_the_old_field_is_unchanged(db_session, tmp_path):
    market_settings.set_market(MarketSetting(home="UK", apply_in=["UK", "DE"]), db_session)
    autofill_profile.set_profile(TWO, db_session)
    view = autofill_profile.get_profile(db_session)
    view["work_auth_by_country"]["UK"] = {"authorized_now": True, "sponsorship_now": False}
    autofill_profile.set_profile(view, db_session)
    assert _stored(tmp_path)["work_auth_by_country"]["UK"] == {"authorized_now": True, "sponsorship_now": False}


def test_a_typed_reader_per_market_drops_unusable_answers(db_session):
    autofill_profile.set_profile({"work_auth_by_country": {"US": {"status": "OPT", "authorized_now": True},
                                                           "DE": "garbage"}}, db_session)
    assert autofill_profile.get_work_auth(db_session, "US").status is None
    assert autofill_profile.get_work_auth(db_session, "US").authorized_now is True
    assert autofill_profile.get_work_auth(db_session, "DE").authorized_now is None


# --- the fill: profile_for_job, the slot lookup, the extension ---------------------------------

def test_profile_for_job_resolves_work_auth_to_the_job_country(db_session):
    from app.models.application import Application
    from app.services import autofill_job
    from tests.test_proposals_models import _mk_job

    job = _mk_job(db_session, company="Acme", country_code="GB")
    app = Application(job_id=job.id, base_resume="hybrid")
    db_session.add(app)
    db_session.commit()
    resolved = autofill_job.profile_for_job(db_session, TWO, app.id)
    assert resolved["work_auth"]["sponsorship_now"] is True
    # No job: no country's answers, only the cross-country list of where you may work.
    assert autofill_job.profile_for_job(db_session, TWO, None)["work_auth"] == {"countries_authorized": ["Germany"]}


def test_the_fill_loop_answers_each_question_from_its_own_country(db_session, client, monkeypatch):
    """/map files both questions under the same slot; the value each gets is its own country's."""
    from app.services import autofill_map

    market_settings.set_market(MarketSetting(home="DE", apply_in=["DE", "UK"]), db_session)
    autofill_profile.set_profile(TWO, db_session)

    def fake_map(fields, facts, session, **_kw):
        return {f.fid: autofill_map.Mapped(route="slot", slot="work_auth.authorized_now",
                                           value=getattr(facts.get("work_auth.authorized_now"), "value", None))
                if "work_auth.authorized_now" in facts else autofill_map.Mapped(route="none")
                for f in fields}

    monkeypatch.setattr(autofill_map, "map_fields", fake_map)
    body = client.post("/api/autofill/map", json={"fields": [
        {"fid": "a", "question": "Are you authorised to work in the United Kingdom?", "shape": "select", "options": ["Yes", "No"]},
        {"fid": "b", "question": "Are you authorised to work in Germany?", "shape": "select", "options": ["Yes", "No"]},
        {"fid": "c", "question": "Are you authorised to work here?", "shape": "select", "options": ["Yes", "No"]},
    ]}).json()["fields"]
    assert body["a"]["value"] == "No"
    assert body["b"]["value"] == "Yes"
    assert body["c"]["route"] == "none"   # no job, no country named: asked, never guessed


def test_the_same_answers_in_another_country_are_read_as_that_countrys(db_session, client, monkeypatch):
    """A Canadian citizen's "citizen" is no US citizenship: a question naming the US gets the
    US-citizen fact, one naming Canada does not, though both countries hold the same answers (the
    fill's catalog is built per market, never shared by equal answers)."""
    from app.services import autofill_map

    market_settings.set_market(MarketSetting(home="US", apply_in=["US", "CA"]), db_session)
    autofill_profile.set_profile({"work_auth_by_country": {
        "US": {"status": "citizen"}, "CA": {"status": "citizen"}}}, db_session)

    def fake_map(fields, facts, session, **_kw):
        fact = facts.get("derived.us_citizen")
        return {f.fid: autofill_map.Mapped(route="slot", slot="derived.us_citizen", value=fact.value)
                if fact else autofill_map.Mapped(route="none") for f in fields}

    monkeypatch.setattr(autofill_map, "map_fields", fake_map)
    body = client.post("/api/autofill/map", json={"fields": [
        {"fid": "us", "question": "Are you a citizen of the United States?", "shape": "select", "options": ["Yes", "No"]},
        {"fid": "ca", "question": "Are you a citizen of Canada?", "shape": "select", "options": ["Yes", "No"]},
    ]}).json()["fields"]
    assert body["us"]["value"] == "Yes"
    assert body["ca"]["route"] == "none"


def test_equal_answers_in_another_key_order_share_one_model_call(db_session, client, monkeypatch):
    """Two countries whose facts match are one group in `split`, however their answers were stored:
    the US's and Canada's same answers in another key order (a save sorts keys; a profile synced
    or written by hand need not) take one /map model call."""
    from app.models.application import Application
    from app.services import autofill_map
    from tests.test_proposals_models import _mk_job

    market_settings.set_market(MarketSetting(home="US", apply_in=["US", "CA"]), db_session)
    text_settings.set_text(autofill_profile.AUTOFILL_KEY, autofill_profile.AUTOFILL_FILE, json.dumps(
        {"work_auth_by_country": {
            "US": {"authorized_now": True, "sponsorship_now": False},
            "CA": {"sponsorship_now": False, "authorized_now": True},
        }}), db_session)
    job = _mk_job(db_session, company="Acme", country_code="US")
    application = Application(job_id=job.id, base_resume="hybrid", customized_json={"contact": {"name": "Ada"}})
    db_session.add(application)
    db_session.commit()
    calls = []

    def fake_map(fields, facts, session, **_kw):
        calls.append([f.fid for f in fields])
        return {f.fid: autofill_map.Mapped(route="none") for f in fields}

    monkeypatch.setattr(autofill_map, "map_fields", fake_map)
    response = client.post("/api/autofill/map", json={"application_id": str(application.id), "fields": [
        {"fid": "ca", "question": "Are you authorised to work in Canada?", "shape": "select", "options": ["Yes", "No"]},
        {"fid": "job", "question": "Are you authorised to work here?", "shape": "select", "options": ["Yes", "No"]},
    ]})
    assert response.status_code == 200, response.text
    assert calls == [["ca", "job"]]


def test_the_extension_reads_only_the_resolved_work_auth():
    """The Companion never picks a country itself: it fills from `profile.work_auth` off /context, which the
    server resolved to the job's country (`profile_for_job`). The one file that names the per-country map is
    the pause row, which learns an answer into the entry /context names for its question
    (`work_auth_market`) and never into one it chose."""
    pause = REPO / "extension/panel/actions/pause.js"
    for path in sorted((REPO / "extension").rglob("*.js")):
        if "node_modules" in path.parts or path == pause:
            continue
        assert "work_auth_by_country" not in path.read_text(encoding="utf-8"), path
    fill = (REPO / "extension/content/autofill.js").read_text(encoding="utf-8")
    assert "profile.work_auth" in fill
    learn = pause.read_text(encoding="utf-8")
    assert 'const BY_COUNTRY = "work_auth_by_country";' in learn
    assert "await store.api(`/api/autofill/context?${params}`)" in learn
    assert "context?.profile?.work_auth_market" in learn
    assert "work_auth: BY_COUNTRY" in learn  # the table's `work_auth.*` is learned into the map…
    assert "path: [BY_MARKET[target.path[0]], market, ...target.path.slice(1)]" in learn  # …at that market


def test_the_knockout_scan_reads_the_job_countrys_answers(db_session):
    """A UK job is screened with the UK answers; a job that names no country with the home ones."""
    from app.services import knockout
    from tests.test_proposals_models import _mk_job

    market_settings.set_market(MarketSetting(home="US", apply_in=["US", "UK"]), db_session)
    autofill_profile.set_profile({"work_auth_by_country": {
        "US": {"status": "citizen", "sponsorship_now": False, "sponsorship_future": False},
        "UK": {"sponsorship_now": True, "sponsorship_future": True},
    }}, db_session)

    def verdict(**kw):
        job = _mk_job(db_session, work_authorization="no_sponsorship", **kw)
        return next(c["result"] for c in knockout.scan_for(db_session, job)["checks"]
                    if c["kind"] == "work_authorization")

    assert verdict(country_code="GB") == "conflict"
    assert verdict(country_code="US") == "pass"
    assert verdict() == "pass"
    assert verdict(country_code="FR") == "profile_missing"   # no market: no answers, never the home ones


# --- country answers: each job reads its own country's (Task 3.7) --------------------------------

def test_a_uae_job_reads_uae_answers_and_none_of_germanys():
    profile = {"preferences": {"desired_salary": "90000"},
               "answers_by_country": {"AE": {"expected_pay": "25000", "in_country_now": True},
                                      "DE": {"expected_pay": "70000"}}}
    folded = autofill_country.with_country_answers(profile, "AE")
    assert folded["preferences"]["desired_salary"] == "25000"
    assert folded["eligibility"]["in_country_now"] is True
    assert "answers_by_country" not in folded
    assert "70000" not in json.dumps(folded)
    # The input is not changed: the generic answer is still the stored one.
    assert profile["preferences"]["desired_salary"] == "90000"


def test_without_a_country_answer_the_generic_one_stays():
    profile = {"preferences": {"desired_salary": "90000"}, "answers_by_country": {"DE": {}}}
    assert autofill_country.with_country_answers(profile, "DE")["preferences"]["desired_salary"] == "90000"


def test_a_blank_answer_and_a_key_the_country_does_not_ask_fill_nothing():
    """Only a set value fills its slot, and only a key the market asks now (`form_questions.answer_keys`):
    India's current CTC stored under Germany, hand-edited or from before a pack moved, is no German answer."""
    profile = {"preferences": {"desired_salary": "90000"},
               "answers_by_country": {"DE": {"expected_pay": "  ", "current_ctc": "1800000", "made_up": "x"}}}
    folded = autofill_country.with_country_answers(profile, "DE")
    assert folded["preferences"] == {"desired_salary": "90000"}
    assert folded[autofill_country.COUNTRY_ANSWERED] == []   # still a job's view, so never saved
    assert "1800000" not in json.dumps(folded)


def test_no_market_folds_nothing_and_drops_every_countrys_answers():
    profile = {"preferences": {"desired_salary": "90000"}, "answers_by_country": {"IN": {"expected_pay": "1"}}}
    for market in (None, "FR"):
        folded = autofill_country.with_country_answers(profile, market)
        assert folded == {"preferences": {"desired_salary": "90000"}, autofill_country.COUNTRY_ANSWERED: []}, market


def test_the_fill_view_holds_no_countrys_map_and_takes_answers_as_a_form_does():
    """`for_market` is the one view every fill reads: no per-country map at all, citizenships as country
    names, and no notice answer that no longer holds."""
    from datetime import date

    profile = {"personal": {"citizenships": ["IN", "GB"]},
               "preferences": {"serving_notice": True, "last_working_day": "2026-01-31"},
               "work_auth_by_country": {"US": {"authorized_now": True}},
               "answers_by_country": {"IN": {"current_ctc": "1800000"}}}
    view = autofill_country.for_market(profile, "IN", today=date(2026, 2, 1))
    assert "work_auth_by_country" not in view and "answers_by_country" not in view
    assert view["personal"]["citizenships"] == ["India", "United Kingdom"]
    assert view["preferences"] == {"current_ctc": "1800000"}   # the notice ended yesterday
    assert view["work_auth"]["authorized_now"] is True          # India settled by the citizenship
    # with_work_auth alone leaves the map (it is the work-permit rule, not the view).
    assert "work_auth_by_country" in autofill_country.with_work_auth(profile, "IN")


def test_a_folded_answer_is_named_beside_the_profile():
    """The slots the job's country's own answers fill ride beside `work_auth_market`, so the catalog can
    describe a figure in its country's own terms only when it is that country's answer."""
    profile = {"answers_by_country": {"NL": {"expected_pay": "4500"}}}
    assert autofill_country.with_country_answers(profile, "NL")[autofill_country.COUNTRY_ANSWERED] == [
        "preferences.desired_salary"]


def test_a_citizenship_answers_the_permit_questions_on_the_job():
    profile = {"personal": {"citizenships": ["FR"]}}
    folded = autofill_country.with_work_auth(profile, "NL")
    assert folded["work_auth"]["authorized_now"] is True
    assert folded["work_auth"]["sponsorship_now"] is False
    # Never another country's: a French citizen's UK answers are unknown.
    assert "authorized_now" not in autofill_country.with_work_auth(profile, "UK")["work_auth"]


def test_a_given_answer_still_wins_over_a_citizenship_on_the_job():
    profile = {"personal": {"citizenships": ["FR"]}, "work_auth_by_country": {"DE": {"authorized_now": False}}}
    assert work_auth_for(profile, question="", job_country="DE").authorized_now is False
    assert work_auth_for(profile, question="", job_country="DE").sponsorship_now is None


def test_countries_authorized_lists_the_markets_a_citizenship_settles():
    profile = {"personal": {"citizenships": ["FR"]}}
    assert work_auth_for(profile, question="", job_country="DE").countries_authorized == [
        "Ireland", "Germany", "Netherlands"]
    # A stored Yes keeps its place first; a settled market the answers already name is listed once.
    profile["work_auth_by_country"] = {"US": {"authorized_now": True}, "NL": {"authorized_now": True}}
    assert work_auth_for(profile, question="", job_country="DE").countries_authorized == [
        "United States", "Netherlands", "Ireland", "Germany"]
    # A given No turns the rule off there, so that country is not listed.
    profile["work_auth_by_country"]["IE"] = {"authorized_now": False}
    assert "Ireland" not in work_auth_for(profile, question="", job_country="DE").countries_authorized


def test_a_question_naming_germany_on_a_uae_job_gets_germanys_country_answers(db_session):
    from app.models.application import Application
    from app.services import autofill_job
    from tests.test_proposals_models import _mk_job

    job = _mk_job(db_session, company="Acme", country_code="AE")
    app = Application(job_id=job.id, base_resume="hybrid")
    db_session.add(app)
    db_session.commit()
    profile = {"preferences": {"desired_salary": "90000"},
               "answers_by_country": {"AE": {"expected_pay": "25000", "in_country_now": True},
                                      "DE": {"expected_pay": "70000"}}}

    named = autofill_job.profile_for_job(db_session, profile, app.id,
                                         question="What is your expected salary in Germany?")
    assert named["preferences"]["desired_salary"] == "70000"
    assert "25000" not in json.dumps(named) and "in_country_now" not in json.dumps(named)

    on_the_job = autofill_job.profile_for_job(db_session, profile, app.id)
    assert on_the_job["preferences"]["desired_salary"] == "25000"
    assert on_the_job["eligibility"]["in_country_now"] is True
    assert "70000" not in json.dumps(on_the_job)
    # No job: no country, so the generic answer and no country's.
    no_job = autofill_job.profile_for_job(db_session, profile, None)
    assert no_job["preferences"]["desired_salary"] == "90000" and "answers_by_country" not in no_job


def test_the_fill_loop_reads_each_questions_own_countrys_answers(db_session, client, monkeypatch):
    """/map's catalog for a UAE job holds the UAE's pay; a question that names Germany is decided against
    Germany's, and neither group sees the other's figure."""
    from app.models.application import Application
    from app.services import autofill_map
    from tests.test_proposals_models import _mk_job

    market_settings.set_market(MarketSetting(home="IN", apply_in=["AE", "DE"]), db_session)
    autofill_profile.set_profile({"preferences": {"desired_salary": "90000"}, "answers_by_country": {
        "AE": {"expected_pay": "25000"}, "DE": {"expected_pay": "70000"}}}, db_session)
    job = _mk_job(db_session, company="Acme", country_code="AE")
    application = Application(job_id=job.id, base_resume="hybrid", customized_json={"contact": {"name": "Ada"}})
    db_session.add(application)
    db_session.commit()
    seen = []

    def fake_map(fields, facts, session, **_kw):
        seen.append(json.dumps({s: f.value for s, f in facts.items()}))
        pay = facts.get("preferences.desired_salary")
        return {f.fid: autofill_map.Mapped(route="slot", slot="preferences.desired_salary", value=pay.value)
                for f in fields}

    monkeypatch.setattr(autofill_map, "map_fields", fake_map)
    body = client.post("/api/autofill/map", json={"application_id": str(application.id), "fields": [
        {"fid": "job", "question": "Expected monthly salary?", "shape": "text"},
        {"fid": "de", "question": "Expected salary in Germany?", "shape": "text"},
    ]}).json()["fields"]
    assert (body["job"]["value"], body["de"]["value"]) == ("25000", "70000")
    assert len(seen) == 2 and not ("70000" in seen[0] and "25000" in seen[0])


def test_the_answer_flags_read_the_jobs_country_answers(db_session):
    from app.services import filled_answers
    from tests.test_proposals_models import _mk_job

    job = _mk_job(db_session, company="Acme", country_code="AE")
    facts, _ = filled_answers.flag_context(db_session, job, {
        "personal": {"citizenships": ["SA"]},
        "answers_by_country": {"AE": {"in_country_now": False}, "DE": {"expected_pay": "70000"}}})
    assert facts["eligibility.in_country_now"].value == "No"
    assert facts["work_auth.status"].value == "GCC national"   # the UAE's own words, from the citizenship
    assert "70000" not in json.dumps({s: f.value for s, f in facts.items()})


def test_the_knockout_scan_reads_a_citizenship(db_session):
    """A French citizen's German job is authorized, with nothing stored for Germany; a UK job (no rule)
    stays unknown."""
    from app.services import knockout
    from tests.test_proposals_models import _mk_job

    market_settings.set_market(MarketSetting(home="IN", apply_in=["DE"]), db_session)
    autofill_profile.set_profile({"personal": {"citizenships": ["FR"]}}, db_session)

    def verdict(**kw):
        job = _mk_job(db_session, work_authorization="no_sponsorship", **kw)
        return next(c["result"] for c in knockout.scan_for(db_session, job)["checks"]
                    if c["kind"] == "work_authorization")

    assert verdict(country_code="DE") == "pass"
    assert verdict(country_code="IE") == "pass"   # settled though not applied in
    assert verdict(country_code="GB") == "profile_missing"


def test_the_knockout_salary_check_reads_the_generic_desired_salary(db_session):
    """Pay stays out of the country fold there: `_salary_check` compares a yearly figure, and the Dutch
    answer is a monthly one."""
    from decimal import Decimal

    from app.services import knockout
    from tests.test_proposals_models import _mk_job

    market_settings.set_market(MarketSetting(home="NL", apply_in=["NL"]), db_session)
    autofill_profile.set_profile({"preferences": {"desired_salary": "EUR 60000"},
                                  "answers_by_country": {"NL": {"expected_pay": "EUR 5000"}}}, db_session)
    job = _mk_job(db_session, country_code="NL", salary_max=Decimal(70000), salary_period="year",
                  salary_currency="EUR")
    salary = next(c for c in knockout.scan_for(db_session, job)["checks"] if c["kind"] == "salary")
    assert "60" in salary["profile_value"] and "5,000" not in salary["profile_value"]
    assert salary["result"] == "pass"


def test_the_trace_redaction_holds_every_countrys_answers(db_session):
    from app.routers.autofill import _redaction_facts

    market_settings.set_market(MarketSetting(home="IN", apply_in=["IN", "AE"]), db_session)
    autofill_profile.set_profile({"preferences": {"desired_salary": "90000"}, "answers_by_country": {
        "IN": {"current_ctc": "1800000"}, "AE": {"expected_pay": "25000"}}}, db_session)
    facts = _redaction_facts(db_session)
    assert facts["preferences.current_ctc#IN"].value == "1800000"
    assert facts["preferences.desired_salary#AE"].value == "25000"
    assert facts["preferences.desired_salary"].value == "90000"


def _nl_job_view(db_session, client, **params) -> dict:
    from app.models.application import Application
    from tests.test_proposals_models import _mk_job

    job = _mk_job(db_session, company="Acme", country_code="NL")
    application = Application(job_id=job.id, base_resume="hybrid", customized_json={"contact": {"name": "Ada"}})
    db_session.add(application)
    db_session.commit()
    return client.get("/api/autofill/context", params={"application_id": str(application.id), **params}).json()["profile"]


def test_a_job_view_is_never_saved(db_session, tmp_path, client):
    """A /context profile is one country's view: its pay is the Dutch monthly figure in the generic slot and its
    permits include what the French citizenship settles. A save of it (PUT, or an agent's PATCH carrying the
    marker) is refused and stores nothing: save from GET /api/settings/autofill."""
    market_settings.set_market(MarketSetting(home="US", apply_in=["US", "NL"]), db_session)
    autofill_profile.set_profile({"personal": {"citizenships": ["FR"]}, "preferences": {"desired_salary": "150000"},
                                  "answers_by_country": {"NL": {"expected_pay": "4500"}}}, db_session)
    before = _stored(tmp_path)
    view = _nl_job_view(db_session, client, question="Are you authorised to work in the Netherlands?")
    assert view[autofill_country.COUNTRY_ANSWERED] == ["preferences.desired_salary"]
    assert view[autofill_country.WORK_AUTH_COUNTRY] == "Netherlands"
    assert view["preferences"]["desired_salary"] == "4500" and view["work_auth"]["authorized_now"] is True

    put = client.put("/api/settings/autofill", json={"value": view})
    assert put.status_code == 422 and "GET /api/settings/autofill" in put.json()["detail"]
    patch = client.patch("/api/settings/autofill", json={"value": {
        "preferences": {"notice_period": "2 weeks"}, autofill_country.COUNTRY_ANSWERED: []}})
    assert patch.status_code == 422 and "GET /api/settings/autofill" in patch.json()["detail"]
    stored = _stored(tmp_path)
    assert stored == before
    assert stored["preferences"] == {"desired_salary": "150000"} and "work_auth_by_country" not in stored

    # Even a view with nothing folded is a job's view.
    assert _nl_job_view(db_session, client)[autofill_country.COUNTRY_ANSWERED] == ["preferences.desired_salary"]
    autofill_profile.set_profile({"answers_by_country": {"NL": None}}, db_session)
    assert _nl_job_view(db_session, client)[autofill_country.COUNTRY_ANSWERED] == []


def test_only_a_profile_read_with_no_job_carries_every_countrys_answers(db_session, client):
    """With no application and no question there is no country to fold, so /context keeps the generic slots
    and hands every market's own answers along (agents read them so); a job's view, or one question's,
    holds one country's and no map. Every view carries every market's permits."""
    market_settings.set_market(MarketSetting(home="US", apply_in=["US", "NL"]), db_session)
    autofill_profile.set_profile({"preferences": {"desired_salary": "150000"},
                                  "work_auth_by_country": {"US": {"authorized_now": True}},
                                  "answers_by_country": {"NL": {"expected_pay": "4500"}}}, db_session)

    no_job = client.get("/api/autofill/context").json()["profile"]
    assert no_job["answers_by_country"] == {"NL": {"expected_pay": "4500"}}
    assert no_job["preferences"]["desired_salary"] == "150000"
    assert no_job[autofill_country.COUNTRY_ANSWERED] == []

    one_question = client.get("/api/autofill/context",
                              params={"question": "Expected salary in the Netherlands?"}).json()["profile"]
    assert "answers_by_country" not in one_question
    assert one_question["preferences"]["desired_salary"] == "4500"

    job = _nl_job_view(db_session, client)
    assert "answers_by_country" not in job
    for view in (no_job, one_question, job):
        assert view["work_auth_by_country"] == {"US": {"authorized_now": True}}


def test_a_setting_read_saves_back_as_it_was(db_session, tmp_path, client):
    """The read the Companion's pause row and the web send back is no job's view."""
    market_settings.set_market(MarketSetting(home="US", apply_in=["US", "NL"]), db_session)
    autofill_profile.set_profile({"preferences": {"desired_salary": "150000"}}, db_session)
    read = client.get("/api/settings/autofill").json()["value"]
    assert autofill_country.COUNTRY_ANSWERED not in read
    assert client.put("/api/settings/autofill", json={"value": read}).status_code == 200


def test_a_stored_view_marker_never_blocks_a_save(db_session, tmp_path, client):
    """A hand-edited autofill.json holding a job view's keys: the read leaves them out, so the read the
    Companion and Profile send back saves, an agent's merge saves, and the next save drops them."""
    market_settings.set_market(MarketSetting(home="US", apply_in=["US", "NL"]), db_session)
    (tmp_path / "autofill.json").write_text(json.dumps({
        "preferences": {"desired_salary": "150000"},
        autofill_country.COUNTRY_ANSWERED: ["preferences.desired_salary"],
        autofill_country.WORK_AUTH_COUNTRY: "Netherlands",
    }))
    read = client.get("/api/settings/autofill").json()["value"]
    assert autofill_country.COUNTRY_ANSWERED not in read and autofill_country.WORK_AUTH_COUNTRY not in read
    assert read["preferences"] == {"desired_salary": "150000"}

    assert client.put("/api/settings/autofill", json={"value": read}).status_code == 200
    _write(db_session, {**_stored(tmp_path), autofill_country.COUNTRY_ANSWERED: []})
    patch = client.patch("/api/settings/autofill", json={"value": {"preferences": {"notice_period": "2 weeks"}}})
    assert patch.status_code == 200
    stored = _stored(tmp_path)
    assert autofill_country.COUNTRY_ANSWERED not in stored and autofill_country.WORK_AUTH_COUNTRY not in stored
    assert stored["preferences"] == {"desired_salary": "150000", "notice_period": "2 weeks"}
