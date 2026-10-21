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
    assert "path: [BY_COUNTRY, market, ...target.path.slice(1)]" in learn


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
