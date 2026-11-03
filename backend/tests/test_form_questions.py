"""The form-question catalog (services/data/form_questions.yaml): it loads, it is well formed,
every market's permit wording, packs and status list are in it, and the set resolved for any market
is the hand-written set it replaced (tests/fixtures/form_questions_today.json, dumped from
frontend/lib/autofill-options.ts) apart from the changes the country questions make on purpose
(Task 3.5 of docs/plans/2026-10-30-country-form-questions.md): a chosen US user's set is today's."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.autofill_profile import WorkAuth
from app.schemas.form_questions import Field, Option
from app.services import countries, form_questions, markets

_TODAY = json.loads(
    (Path(__file__).parent / "fixtures" / "form_questions_today.json").read_text(encoding="utf-8")
)


def test_catalog_loads_and_every_group_has_fields():
    catalog = form_questions.catalog()
    assert [g.key for g in catalog.groups] == ["personal", "eeo", "eligibility", "preferences"]
    assert all(g.fields for g in catalog.groups)


def test_keys_are_unique_within_a_group():
    for group in form_questions.catalog().groups:
        keys = [f.key for f in group.fields]
        assert len(keys) == len(set(keys)), group.key


def test_a_shown_when_names_a_field_of_its_group():
    for group in form_questions.catalog().groups:
        keys = {f.key for f in group.fields}
        for field in group.fields:
            if field.when:
                assert field.when[0] in keys, (group.key, field.key)


def test_every_select_offers_options():
    catalog = form_questions.catalog()
    fields = [f for g in catalog.groups for f in g.fields] + [
        f for wording in catalog.permits.values() for f in wording
    ] + [*catalog.answers, *catalog.language_fields]
    for field in fields:
        if field.type == "select":
            assert field.options, field.key


def test_the_shared_catalog_cannot_be_changed_in_place():
    """`resolve` hands every caller the cached catalog's own objects, so none may be edited."""
    field = form_questions.catalog().groups[0].fields[0]
    with pytest.raises(ValidationError):
        field.label = "Changed"


def test_a_key_the_catalog_does_not_know_is_refused():
    """A misspelt attribute in the YAML fails the load instead of being dropped."""
    with pytest.raises(ValidationError):
        Option(value="yes", label="Yes", hint="not an option's")


def test_every_market_has_permit_wording():
    for key in markets.keys():
        assert markets.get(key)["work_auth_vocab"] in form_questions.catalog().permits


def test_every_permit_question_is_a_stored_work_permit_answer():
    """Readiness reads each permit answer off the typed `WorkAuth` by its key: a key only the YAML
    knows would fail setup status, and one with a default other than None would count as answered
    before the user says anything."""
    for vocab, fields in form_questions.catalog().permits.items():
        for field in fields:
            assert field.key in WorkAuth.model_fields, (vocab, field.key)
            assert WorkAuth.model_fields[field.key].default is None, (vocab, field.key)


# ------------------------------------------------ packs, statuses, country answers, citizenship


def _tagged(cat) -> set[str]:
    """Every pack some catalog field is tagged with."""
    fields = [f for g in cat.groups for f in g.fields] + [*cat.answers, *cat.language_fields]
    return {f.pack for f in fields if f.pack}


def test_every_market_names_packs_and_lists_that_exist():
    cat = form_questions.catalog()
    tagged = _tagged(cat)
    for key in markets.keys():
        m = markets.get(key)
        assert set(m["packs"]) <= tagged, key
        assert m["work_status"] is None or m["work_status"] in cat.statuses, key
        assert m["work_auth_vocab"] in cat.permits, key
        assert m["pay"]["label"], key


def test_every_tagged_pack_is_named_by_a_market():
    named = {p for k in markets.keys() for p in markets.get(k)["packs"]}
    assert _tagged(form_questions.catalog()) <= named


def test_a_key_appears_once_across_groups_and_answers():
    cat = form_questions.catalog()
    keys = [f.key for g in cat.groups for f in g.fields] + [f.key for f in cat.answers]
    assert len(keys) == len(set(keys))


def test_every_country_answer_says_where_it_fills():
    """A `section.key` slot in one of the profile's sections, which Task 3.7 writes on that
    country's jobs."""
    cat = form_questions.catalog()
    sections = {g.key for g in cat.groups}
    for field in cat.answers:
        assert field.fills and field.fills.count(".") == 1, field.key
        assert field.fills.split(".")[0] in sections, field.key


def test_status_values_are_unique_per_list_and_citizen_is_first():
    for name, statuses in form_questions.catalog().statuses.items():
        values = [o.value for o in statuses.options]
        assert len(values) == len(set(values)), name
        assert values[0] == "citizen", name  # the own-country rule sets it (Task 3.4)


def test_each_status_list_words_its_question():
    """Data, like the rest of a country's questions: the US keeps today's words and is counted;
    every other list is optional, so no existing count drops (Decision 6)."""
    words = {
        name: (statuses.label, statuses.required)
        for name, statuses in form_questions.catalog().statuses.items()
    }
    assert words == {
        "us": ("Work authorization status", True),
        "ca": ("Immigration status", False),
        "au": ("Immigration status", False),
        "ae": ("Immigration status", False),
    }


def test_each_market_with_a_status_list_asks_it_first():
    """Served per market from its `statuses` list, in its words: the US's required, as always;
    every other list's "Immigration status" and optional. A market with no list (the UK) asks
    none."""
    cat = form_questions.catalog()
    for key in markets.keys():
        m = markets.get(key)
        permits = form_questions.resolve(home=key, apply_in=[key], chosen=True, profile=None).countries[0].permits
        if m["work_status"] is None:
            assert "status" not in [f.key for f in permits], key
            continue
        status = permits[0]
        assert (status.key, status.type) == ("status", "select")
        assert status.options == cat.statuses[m["work_status"]].options
        want = ("Work authorization status", False) if key == "US" else ("Immigration status", True)
        assert (status.label, status.optional) == want, key


def test_statuses_that_never_expire_are_marked():
    """Each status says whether it has an expiry (Sources 11), so the expiry is asked only where
    one exists (Task 3.5)."""
    lasting = {
        name: [o.value for o in statuses.options if o.noExpiry]
        for name, statuses in form_questions.catalog().statuses.items()
    }
    assert lasting == {
        "us": ["citizen", "permanent_resident", "not_authorized"],
        "ca": ["citizen", "permanent_resident", "maintained_status", "no_status"],
        "au": ["citizen", "permanent_resident", "nz_citizen"],
        "ae": ["citizen", "gcc_national", "no_visa"],
    }


def test_status_values_are_a_markets_own_list():
    """What a save takes and the typed reader keeps for a market's `status` (autofill_profile)."""
    assert form_questions.status_values("US")[:2] == ["citizen", "permanent_resident"]
    assert "h1b" in form_questions.status_values("US")
    assert "pgwp" in form_questions.status_values("ca ")
    assert "golden_visa" in form_questions.status_values("AE")
    # No list, or no market: never the default market's.
    assert form_questions.status_values("UK") == []
    assert form_questions.status_values("FR") == []
    assert form_questions.status_values(None) == []


def test_all_status_values_join_every_list():
    every = {o.value for s in form_questions.catalog().statuses.values() for o in s.options}
    assert form_questions.all_status_values() == every
    assert {"h1b", "pgwp", "nz_citizen", "golden_visa"} <= every


def test_answer_keys_follow_a_markets_packs():
    assert form_questions.answer_keys("US") == ["expected_pay"]
    assert form_questions.answer_keys("DE") == ["expected_pay"]
    assert form_questions.answer_keys("IN") == ["expected_pay", "current_ctc"]
    assert form_questions.answer_keys("ae") == ["expected_pay", "in_country_now", "uae_driving_licence"]
    assert form_questions.answer_keys("FR") == []


def test_every_wording_asks_the_three_answers_then_the_expiry():
    """No wording carries the status: each market's is built from its `statuses` list."""
    want = ["authorized_now", "sponsorship_now", "sponsorship_future", "authorization_expires_on"]
    for vocab, fields in form_questions.catalog().permits.items():
        assert [f.key for f in fields] == want, vocab


def test_canada_asks_the_generic_questions_and_explains_sponsorship():
    """IRCC never says "sponsor" for a work permit (Sources 12): the two sponsorship questions say
    what it means there, and nothing else changes."""
    permits = form_questions.catalog().permits
    for ca, generic in zip(permits["ca"], permits["generic"], strict=True):
        if ca.key.startswith("sponsorship_"):
            assert "employer-specific work permit" in ca.hint, ca.key
            ca = ca.model_copy(update={"hint": None})
        assert ca == generic, ca.key


def test_the_uae_asks_whether_an_employer_sponsors_your_residence_visa():
    """Every UAE hire needs the employer's work permit, so "authorized" there means no residence
    visa to sponsor (Sources 9)."""
    labels = {f.key: f.label for f in form_questions.catalog().permits["ae"]}
    assert all("residence visa" in labels[k] for k in ("authorized_now", "sponsorship_now",
                                                         "sponsorship_future"))


def test_a_rule_covers_its_groups_codes_or_its_own():
    cit = form_questions.catalog().citizenship
    by_markets = {tuple(rule.markets): rule for rule in cit.rules}
    assert cit.members(by_markets[("AE",)]) == ["BH", "KW", "OM", "QA", "SA"]
    assert cit.members(by_markets[("IE",)]) == ["GB"]
    assert "NO" in cit.members(by_markets[("DE", "NL", "IE")])  # Norway, never YAML's false


def test_citizenship_rules_name_iso_codes_and_markets():
    cat = form_questions.catalog()
    cit = cat.citizenship
    for members in cit.groups.values():
        assert all(countries.normalize(c) == c for c in members)
    for rule in cit.rules:
        assert isinstance(rule.citizens, list) or rule.citizens in cit.groups, rule.citizens
        assert all(countries.normalize(c) == c for c in cit.members(rule)), rule.citizens
        assert all(markets.is_supported(m) for m in rule.markets)
        assert rule.source.startswith("https://")
        if rule.status:  # a status the rule settles is one of each market's own
            for m in rule.markets:
                values = [o.value for o in cat.statuses[markets.get(m)["work_status"]].options]
                assert rule.status in values, (m, rule.status)


def test_catalog_only_attributes_are_never_served():
    """Packs, fill slots and expiries are for the catalog's own readers: the served set (and so
    Phase 1's golden) never carries them."""
    cat = form_questions.catalog()
    eligibility = next(g for g in cat.groups if g.key == "eligibility")
    assert next(f for f in eligibility.fields if f.key == "over_18").pack == "us_screening"
    served = json.dumps(
        form_questions.resolve(home="US", apply_in=["US"], chosen=True, profile=None).model_dump(mode="json")
    )
    assert "us_screening" not in served and '"pack"' not in served
    assert "noExpiry" not in served and '"fills"' not in served
    assert "fills" not in cat.answers[0].model_dump()
    assert "noExpiry" not in cat.statuses["us"].options[0].model_dump()


# The fields the country questions show only where a pack is named, on purpose: the US screening
# pair, which today's set asked everyone, and India's basics, which are new. Each says who asks it.
_US_SCREENING = {"over_18", "non_compete"}
_US_ASKS = "Asked by forms in the United States."
_INDIA = {
    "eligibility": ["experience_years", "experience_months"],
    "preferences": ["serving_notice", "last_working_day", "preferred_locations"],
}

# Start and pay (docs/plans/2026-11-02-start-and-pay.md): notice is one answer in days for everyone,
# read from today's text until given, in today's place; and the desired salary is the home country's
# pay, asked in its set wherever the home is applied in, as it is in every golden here.
_NOTICE_DAYS = {
    "key": "notice_days", "label": "Notice period (days)",
    "hint": "0 if you can start now. Forms that offer fixed choices get the next one up.",
    "type": "number", "legacy": "notice_period",
}


def _start_and_pay(field: dict) -> dict | None:
    """Today's field as Start and pay asks it now, for a home that is applied in."""
    if field["key"] == "notice_period":
        return _NOTICE_DAYS
    return None if field["key"] == "desired_salary" else field


# The one question the country questions add to everyone's set (Task 3.6), counted (Decision 6):
# citizenship, after the country you live in. Profile's Country answers asks it (Task 3.10).
_CITIZENSHIP = {"key": "citizenships", "label": "Citizen of", "type": "countries"}


def _keys(fields) -> list[str]:
    return [f.key for f in fields]


def _today_fields(group: dict) -> list[dict]:
    """A fixture group's fields through today's schema (`_field`) for a US home applying there:
    citizenship added after the country, the US screening pair saying who asks it, and Start and
    pay's changes."""
    fields = []
    for raw in group["fields"]:
        field = _start_and_pay(_field(raw))
        if field is None:
            continue
        fields.append({**field, "askedBy": _US_ASKS} if field["key"] in _US_SCREENING else field)
        if raw["key"] == "country":
            fields.append(_CITIZENSHIP)
    return fields


def _field(raw: dict) -> dict:
    """A fixture field through today's schema, so defaults compare alike; its `byHome` was a bool,
    and the address lines are compared without it."""
    return Field.model_validate({k: v for k, v in raw.items() if k != "byHome"}).model_dump(
        exclude_defaults=True
    )


def _served_field(field: Field, *leave_out: str) -> dict:
    return field.model_dump(exclude_defaults=True, exclude=set(leave_out))


def _today_groups(home: str) -> list[dict]:
    """groupFields(key, home) for every group, as autofill-options.ts did it, with the changes made
    since: the US screening pair only for a US home (each home applies in itself here), saying who
    asks it, the address lines' `byHome` named, no postal code counted for a UAE home, citizenship,
    and Start and pay's."""
    m = markets.get(home)
    out = []
    for group in _TODAY["groups"]:
        fields = []
        for field in group["fields"]:
            if field["key"] in _US_SCREENING and home != "US":
                continue
            field = _start_and_pay(_field(field))
            if field is None:
                continue
            if field["key"] in _US_SCREENING:
                field = {**field, "askedBy": _US_ASKS}
            if field["key"] == "state":
                field = {**field, "byHome": "state", "label": m["state_label"] or field["label"]}
                field.update({"optional": True} if m["asks_state"] is False else {})
            elif field["key"] == "postal_code":
                field = {**field, "byHome": "postcode", **({"optional": True} if home == "AE" else {})}
            fields.append(field)
            if field["key"] == "country":
                fields.append(_CITIZENSHIP)
        out.append({"key": group["key"], "title": group["title"], "fields": fields})
    return out


def _without_india(group, apply_in: list[str]) -> dict:
    """The group with India's basics left out where India is applied in (they are pinned on their
    own); anywhere else they stay in, so a leak fails the comparison with today's set."""
    added = _INDIA.get(group.key, []) if "IN" in apply_in else []
    return {
        "key": group.key,
        "title": group.title,
        "fields": [_served_field(f) for f in group.fields if f.key not in added],
    }


def test_a_chosen_us_user_sees_todays_set():
    """Labels, options, hints and counted keys as the Phase 1 fixture; only the new attributes
    differ (byHome's value, the expiry's `unless`, who asks the US screening pair), citizenship is
    asked, and Start and pay's changes: notice in days, the desired salary asked in the US's set."""
    qs = form_questions.resolve(home="US", apply_in=["US"], chosen=True, profile=None)
    assert [(g.key, g.title) for g in qs.groups] == [(g["key"], g["title"]) for g in _TODAY["groups"]]
    got = [[_served_field(f, "byHome") for f in g.fields] for g in qs.groups]
    assert got == [_today_fields(g) for g in _TODAY["groups"]]
    us = qs.countries[0]
    assert (us.market, us.label) == ("US", "United States")
    assert [_served_field(f, "unless") for f in us.permits] == [
        _field(f) for f in _TODAY["permits"]["us_visa"]
    ]
    assert _keys(us.answers) == ["expected_pay"] and us.derived == {}
    assert us.home is True and us.answers[0].optional is False
    assert qs.language_fields == []


@pytest.mark.parametrize("home", markets.keys())
def test_every_home_gets_todays_groups(home):
    got = form_questions.resolve(home=home, apply_in=[home], chosen=True, profile=None)
    assert [_without_india(g, [home]) for g in got.groups] == _today_groups(home)
    india = {k for keys in _INDIA.values() for k in keys}
    asked = {f.key for g in got.groups for f in g.fields}
    assert (india <= asked) if home == "IN" else not (india & asked)


def test_india_asks_its_basics_beside_the_questions_they_go_with():
    """Sources 20-22: experience in years and months, serving notice, the last working day and
    preferred locations, all optional and saying India asks them; only while India is applied in.
    Notice in days is everyone's now."""
    def groups(apply_in):
        resolved = form_questions.resolve(home="DE", apply_in=apply_in, chosen=True, profile=None).groups
        return {g.key: g.fields for g in resolved}

    india = groups(["DE", "IN"])
    assert _keys(india["eligibility"]) == ["previously_employed_here", *_INDIA["eligibility"]]
    assert _keys(india["preferences"]) == [
        "notice_days", "serving_notice", "last_working_day",
        "earliest_start_date", "willing_to_relocate", "how_heard", "preferred_locations",
    ]
    added = {f.key: f for key, keys in _INDIA.items() for f in india[key] if f.key in keys}
    assert all(f.optional and f.askedBy == "Asked by forms in India." for f in added.values())
    assert [added[k].type for k in ("experience_years", "experience_months")] == ["number"] * 2
    assert added["serving_notice"].boolean is True
    # A yes/no is stored as `true` and `when` compares the raw value, so the date has no `when`.
    assert (added["last_working_day"].type, added["last_working_day"].when) == ("date", None)
    germany = groups(["DE"])
    assert not set(added) & {f.key for fields in germany.values() for f in fields}


# Canada's `ca` and the UAE's `ae` wordings are new on purpose (Task 3.2): the golden holds the
# markets whose wording the fixture has.
_TODAYS_WORDING = [
    k for k in markets.keys() if markets.get(k)["work_auth_vocab"] in _TODAY["permits"]
]


def test_the_permit_golden_leaves_out_only_canada_and_the_uae():
    """So a market moved to a new wording is a decision here, not a silent drop from the golden."""
    assert set(markets.keys()) - set(_TODAYS_WORDING) == {"CA", "AE"}


@pytest.mark.parametrize("market", _TODAYS_WORDING)
def test_every_market_gets_todays_permit_fields(market):
    """Today's wording, apart from this phase's changes: a status list's question ahead of it
    outside the US (Australia's), and the expiry's `unless`."""
    permits = form_questions.resolve(home="US", apply_in=[market], chosen=True, profile=None).countries[0].permits
    got = [_served_field(f, "unless") for f in permits if market == "US" or f.key != "status"]
    vocab = markets.get(market)["work_auth_vocab"]
    assert got == [_field(f) for f in _TODAY["permits"][vocab]]


def test_permits_are_served_only_per_country():
    """Phase 1's market-keyed `permits` is gone now Profile and Setup read `countries`: each
    country's permit list rides on its own entry, and nowhere else."""
    qs = form_questions.resolve(home="IN", apply_in=["US", "AE", "DE"], chosen=True, profile=None)
    assert "permits" not in qs.model_dump()
    assert [c.market for c in qs.countries] == ["US", "AE", "DE"]
    assert all(c.permits for c in qs.countries)


def _state_line(home: str) -> Field:
    groups = form_questions.resolve(home=home, apply_in=[home], chosen=True, profile=None).groups
    personal = next(g for g in groups if g.key == "personal")
    return next(f for f in personal.fields if f.key == "state")


def test_the_state_line_is_named_and_counted_by_where_you_live():
    """A UK address names a county and needs none; a US one needs its state (markets.yaml)."""
    uk, us = _state_line("UK"), _state_line("US")
    assert (uk.label, uk.optional) == ("County", True)
    assert (us.label, us.optional) == ("State", False)


@pytest.mark.parametrize("chosen", [True, False])
def test_citizenship_is_asked_once_and_counted_wherever_you_live(chosen):
    """Decision 6: the one new required answer, a list of countries, whatever your countries."""
    for home in markets.keys():
        groups = form_questions.resolve(home=home, apply_in=[home], chosen=chosen, profile=None).groups
        asked = [(g.key, f) for g in groups for f in g.fields if f.key == "citizenships"]
        assert [(key, f.type, f.optional) for key, f in asked] == [("personal", "countries", False)], home
        personal = next(g for g in groups if g.key == "personal")
        assert "citizenships" in form_questions.required_keys(personal.fields)


def test_required_keys_leave_out_the_optional_fields():
    """What setup readiness counts: the state line only where an address there needs one."""
    def personal(home: str) -> list[str]:
        groups = form_questions.resolve(home=home, apply_in=[home], chosen=True, profile=None).groups
        return form_questions.required_keys(next(g for g in groups if g.key == "personal").fields)

    assert "state" not in personal("UK") and "state" in personal("US")
    assert "address_2" not in personal("US") and "linkedin" not in personal("US")


def test_countries_are_in_apply_in_order():
    got = form_questions.resolve(home="IN", apply_in=["UK", "US", "DE"], chosen=True, profile=None)
    assert [c.market for c in got.countries] == ["UK", "US", "DE"]


def test_offers_eeo_follows_the_apply_in_markets():
    """Offered when any market you apply in has a checked set (US, UK today), wherever you live."""
    assert form_questions.resolve(home="IN", apply_in=["US"], chosen=True, profile=None).offers_eeo is True
    assert form_questions.resolve(home="US", apply_in=["IN", "DE"], chosen=True, profile=None).offers_eeo is False
    assert form_questions.resolve(home="DE", apply_in=["DE", "NL"], chosen=True, profile=None).offers_eeo is False
    assert form_questions.resolve(home="DE", apply_in=["DE", "UK"], chosen=True, profile=None).offers_eeo is True


def test_unchosen_resolves_no_country():
    qs = form_questions.resolve(home="US", apply_in=[], chosen=False, profile=None)
    assert qs.countries == [] and qs.offers_eeo is False and qs.chosen is False


def test_unchosen_keeps_the_state_line_but_never_requires_it():
    """No country is chosen, so no address rule applies: the line keeps its catalog label."""
    groups = form_questions.resolve(home="US", apply_in=[], chosen=False, profile=None).groups
    personal = next(g for g in groups if g.key == "personal")
    state = next(f for f in personal.fields if f.key == "state")
    assert (state.label, state.optional) == ("State", True)
    assert "state" not in form_questions.required_keys(personal.fields)


def test_no_apply_in_reads_as_home():
    """The market setting's rule (`MarketSetting`: empty `apply_in` reads as `[home]`)."""
    got = form_questions.resolve(home="UK", apply_in=[], chosen=True, profile=None)
    assert [c.market for c in got.countries] == ["UK"]
    assert form_questions.resolve(home="UK", apply_in=[], chosen=True, profile=None).offers_eeo is True
    assert form_questions.resolve(home="IN", apply_in=[], chosen=True, profile=None).offers_eeo is False


# ------------------------------------------------------------- countries, packs and citizenship


def _citizen_of(*codes: str, **answers) -> dict:
    """Form answers as a read view holds them: citizenships, and permit answers by market."""
    return {"personal": {"citizenships": list(codes)}, "work_auth_by_country": answers}


def test_each_question_once_for_india_uae_germany_and_the_netherlands():
    qs = form_questions.resolve(
        home="IN", apply_in=["IN", "AE", "DE", "NL"], chosen=True, profile=_citizen_of("IN")
    )
    you = [f.key for g in qs.groups for f in g.fields]
    assert len(you) == len(set(you))
    assert {"notice_days", "experience_years", "preferred_locations"} <= set(you)
    assert not {"over_18", "non_compete"} & set(you)
    by = {c.market: c for c in qs.countries}
    assert [c.market for c in qs.countries] == ["IN", "AE", "DE", "NL"]
    assert [c.label for c in qs.countries] == ["India", "United Arab Emirates", "Germany", "Netherlands"]
    assert _keys(by["IN"].answers) == ["expected_pay", "current_ctc"]
    assert _keys(by["AE"].answers) == ["expected_pay", "in_country_now", "uae_driving_licence"]
    assert _keys(by["DE"].answers) == ["expected_pay"]
    assert by["AE"].permits[0].key == "status" and by["DE"].permits[0].key == "authorized_now"
    assert by["NL"].answers[0].label.startswith("Expected gross monthly salary")
    assert _keys(qs.language_fields) == ["cefr"]
    assert set(by["IN"].derived) == {"authorized_now", "sponsorship_now", "sponsorship_future"}
    assert by["IN"].derived["authorized_now"].via == "IN"
    assert by["DE"].derived == {}


def test_expected_pay_is_worded_and_hinted_by_each_market():
    """markets.yaml `pay`: the label everywhere, the hint where the basis needs one (the UAE)."""
    qs = form_questions.resolve(home="US", apply_in=["US", "AE"], chosen=True, profile=None)
    us, ae = (c.answers[0] for c in qs.countries)
    assert (us.label, us.hint) == ("Expected salary (USD)", None)
    assert (ae.label, ae.hint) == ("Expected total monthly salary (AED)", "Basic pay plus allowances, per month.")


def test_eu_citizens_see_germany_and_the_netherlands_settled():
    qs = form_questions.resolve(home="IN", apply_in=["DE", "NL"], chosen=True, profile=_citizen_of("FR"))
    assert all(c.derived["authorized_now"].via == "FR" for c in qs.countries)


def test_a_given_answer_that_differs_turns_the_derived_ones_off_in_that_country():
    """Profile shows "From your citizenship" only where the fill uses it
    (`autofill_derive.derived_in_effect`): an FR citizen who said they may not work in Germany sees
    no derived German answer; the Netherlands stays settled."""
    profile = _citizen_of("FR", DE={"authorized_now": False})
    by = {c.market: c for c in form_questions.resolve(
        home="IN", apply_in=["DE", "NL"], chosen=True, profile=profile
    ).countries}
    assert by["DE"].derived == {}
    assert by["NL"].derived["authorized_now"].value is True


def test_without_a_profile_nothing_is_derived():
    qs = form_questions.resolve(home="IN", apply_in=["IN"], chosen=True, profile=None)
    assert qs.countries[0].derived == {}


def test_a_caller_that_forgets_the_profile_fails():
    """Like `chosen`: forgetting it would serve every country with nothing derived."""
    with pytest.raises(TypeError):
        form_questions.resolve(home="IN", apply_in=["IN"], chosen=True)


def test_the_expiry_hides_for_statuses_that_never_expire():
    ae = form_questions.resolve(home="AE", apply_in=["AE"], chosen=True, profile=None).countries[0]
    expiry = next(f for f in ae.permits if f.key == "authorization_expires_on")
    assert expiry.unless == ("status", ["citizen", "gcc_national", "no_visa"])
    # No status list, no `unless`: the catalog's own expiry, unchanged.
    uk = form_questions.resolve(home="UK", apply_in=["UK"], chosen=True, profile=None).countries[0]
    assert next(f for f in uk.permits if f.key == "authorization_expires_on").unless is None


def test_a_uae_home_counts_no_postcode_and_calls_the_state_line_emirate():
    personal = form_questions.resolve(home="AE", apply_in=["AE"], chosen=True, profile=None).groups[0]
    by_key = {f.key: f for f in personal.fields}
    assert by_key["postal_code"].optional is True and by_key["postal_code"].label == "Postal code"
    assert by_key["state"].label == "Emirate" and by_key["state"].optional is False
    assert "postal_code" not in form_questions.required_keys(personal.fields)


def test_a_pack_follows_every_country_you_apply_in():
    """A US screening question is asked once someone applies in the US, wherever they live."""
    def eligibility(apply_in):
        groups = form_questions.resolve(home="DE", apply_in=apply_in, chosen=True, profile=None).groups
        return _keys(next(g for g in groups if g.key == "eligibility").fields)

    assert "over_18" not in eligibility(["DE"])
    assert {"over_18", "non_compete"} <= set(eligibility(["DE", "US"]))
    assert form_questions.resolve(home="DE", apply_in=["UK"], chosen=True, profile=None).language_fields == []
    assert _keys(form_questions.resolve(home="UK", apply_in=["NL"], chosen=True, profile=None).language_fields) == ["cefr"]


def test_unchosen_asks_no_country_and_no_us_screening():
    qs = form_questions.resolve(home="US", apply_in=[], chosen=False, profile=None)
    assert qs.countries == [] and qs.language_fields == []
    assert not {f.key for g in qs.groups for f in g.fields} & {"over_18", "non_compete"}


def test_unchosen_is_the_same_set_wherever_you_live():
    """No country chosen means no address rule, so the generic set reads no home: one served
    fixture (`lives-none`) holds it."""
    sets = {
        home: form_questions.resolve(home=home, apply_in=[], chosen=False, profile=None).model_dump()
        for home in markets.keys()
    }
    assert all(s == sets["US"] for s in sets.values())


# ----------------------------------------- Start and pay: home pay, notice in days, who asks a pack's


def _group_of(qs, key: str):
    """The served group `key`."""
    return next(g for g in qs.groups if g.key == key)


def _field_of(qs, group: str, key: str) -> Field:
    """The served field `key` of the group `group`."""
    return next(f for f in _group_of(qs, group).fields if f.key == key)


def test_home_pay_is_the_home_sets_and_required():
    """The home country's pay is the desired salary, asked in its set and counted; every other
    country's is optional, and Start and pay no longer asks it (docs/plans/2026-11-02-start-and-pay.md)."""
    qs = form_questions.resolve(home="US", apply_in=["US", "IN", "IE"], chosen=True, profile=None)
    us, india, ireland = qs.countries
    assert (us.home, india.home, ireland.home) == (True, False, False)
    pay = {c.market: next(f for f in c.answers if f.key == "expected_pay") for c in qs.countries}
    assert pay["US"].optional is False and pay["IN"].optional and pay["IE"].optional
    assert "desired_salary" not in [f.key for f in _group_of(qs, "preferences").fields]


@pytest.mark.parametrize("home", markets.keys())
def test_the_one_required_own_answer_is_the_homes_pay(home):
    """Wherever you live and apply, the only required answer of a country's own is the home's pay:
    every other country's own answers are optional. Setup readiness counts the home set's required
    answers (`home_pay`) and Profile every country's (`countryAnswersOpen`), and they agree because
    of this; a catalog change that makes another own answer required decides both again."""
    qs = form_questions.resolve(home=home, apply_in=markets.keys(), chosen=True, profile=None)
    required = {c.market: form_questions.required_keys(c.answers) for c in qs.countries}
    assert required == {m: (["expected_pay"] if m == home else []) for m in markets.keys()}


def test_desired_salary_stays_in_start_and_pay_while_unchosen_or_home_not_applied():
    """Unchosen it is the one figure, as today; a home you do not apply in has no set, and the figure
    is read only for a job whose country can't be told, so it stays, optional, saying so."""
    unchosen = form_questions.resolve(home="US", apply_in=[], chosen=False, profile=None)
    assert _field_of(unchosen, "preferences", "desired_salary").optional is False
    abroad = form_questions.resolve(home="US", apply_in=["IN"], chosen=True, profile=None)
    field = _field_of(abroad, "preferences", "desired_salary")
    assert field.optional and field.hint == "For jobs whose country Maestro can't tell."
    assert abroad.countries[0].home is False


def test_notice_is_one_answer_in_days_for_everyone():
    """Counted, read from the old text until days are given (`legacy`), and no pack's."""
    for qs in (form_questions.resolve(home="US", apply_in=[], chosen=False, profile=None),
               form_questions.resolve(home="IN", apply_in=["IN"], chosen=True, profile=None)):
        keys = [f.key for f in _group_of(qs, "preferences").fields]
        assert "notice_period" not in keys and keys.count("notice_days") == 1
        days = _field_of(qs, "preferences", "notice_days")
        assert days.optional is False and days.legacy == "notice_period" and days.askedBy is None
        # The label carries the unit: the box takes a number, and a blank one must say of what.
        assert (days.label, days.type) == ("Notice period (days)", "number")


def test_pack_fields_say_who_asks():
    """A pack's question names the countries you apply in whose forms ask it, in apply-in order;
    a question everyone is asked, or one in a country's own set, names none."""
    qs = form_questions.resolve(home="US", apply_in=["US", "IN", "DE", "NL"], chosen=True, profile=None)
    assert _field_of(qs, "preferences", "serving_notice").askedBy == "Asked by forms in India."
    assert _field_of(qs, "eligibility", "over_18").askedBy == "Asked by forms in the United States."
    cefr = next(f for f in qs.language_fields if f.key == "cefr")
    assert cefr.askedBy == "Asked by forms in Germany and the Netherlands."
    assert _field_of(qs, "preferences", "willing_to_relocate").askedBy is None
    assert all(f.askedBy is None for c in qs.countries for f in (*c.permits, *c.answers))


def test_names_join_as_a_list_reads_them():
    """In apply-in order, "A and B", "A, B and C"; three names are checked through `_joined`, since
    only `cefr` is a pack two markets share today."""
    qs = form_questions.resolve(home="UK", apply_in=["NL", "UK", "DE", "AE"], chosen=True, profile=None)
    cefr = next(f for f in qs.language_fields if f.key == "cefr")
    assert cefr.askedBy == "Asked by forms in the Netherlands and Germany."
    assert form_questions._joined(["the Netherlands", "Germany", "the United Arab Emirates"]) == (
        "the Netherlands, Germany and the United Arab Emirates")


def test_the_catalog_writes_no_asked_by_of_its_own():
    """`askedBy` is the served sentence, composed for where you apply; the catalog never sets it."""
    cat = form_questions.catalog()
    fields = [f for g in cat.groups for f in g.fields] + [*cat.answers, *cat.language_fields] + [
        f for wording in cat.permits.values() for f in wording
    ]
    assert all(f.askedBy is None for f in fields)
    assert [f.key for f in fields if f.legacy] == ["notice_days"]
