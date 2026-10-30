"""The form-question catalog (services/data/form_questions.yaml): it loads, it is well formed,
every market's permit wording, packs and status list are in it, and the set resolved for any market
is the hand-written set it replaced (tests/fixtures/form_questions_today.json, dumped from
frontend/lib/autofill-options.ts), Canada's and the UAE's newer permit wordings apart."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.autofill_profile import WorkAuth
from app.schemas.form_questions import Field, Group, Option
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
    ]
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
    for field in form_questions.catalog().answers:
        assert field.fills and field.fills.count(".") == 1, field.key


def test_status_values_are_unique_per_list_and_citizen_is_first():
    for name, options in form_questions.catalog().statuses.items():
        values = [o.value for o in options]
        assert len(values) == len(set(values)), name
        assert values[0] == "citizen", name  # the own-country rule sets it (Task 3.4)


def test_the_us_status_question_offers_the_us_status_list():
    """One list: `permits.us_visa`'s status field reads `statuses.us` until Task 3.5 builds the
    status field per market."""
    cat = form_questions.catalog()
    status = next(f for f in cat.permits["us_visa"] if f.key == "status")
    assert status.options == cat.statuses["us"]


def test_statuses_that_never_expire_are_marked():
    """Each status says whether it has an expiry (Sources 11), so the expiry is asked only where
    one exists (Task 3.5)."""
    lasting = {
        name: [o.value for o in options if o.noExpiry]
        for name, options in form_questions.catalog().statuses.items()
    }
    assert lasting == {
        "us": ["citizen", "permanent_resident", "not_authorized"],
        "ca": ["citizen", "permanent_resident", "maintained_status", "no_status"],
        "au": ["citizen", "permanent_resident", "nz_citizen"],
        "ae": ["citizen", "gcc_national", "no_visa"],
    }


def test_every_wording_asks_the_three_answers_then_the_expiry():
    want = ["authorized_now", "sponsorship_now", "sponsorship_future", "authorization_expires_on"]
    for vocab, fields in form_questions.catalog().permits.items():
        keys = [f.key for f in fields]
        assert keys == (["status", *want] if vocab == "us_visa" else want), vocab


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


def test_citizenship_rules_name_iso_codes_and_markets():
    cat = form_questions.catalog()
    cit = cat.citizenship
    for members in cit.groups.values():
        assert all(countries.normalize(c) == c for c in members)
    for rule in cit.rules:
        if isinstance(rule.citizens, str):
            assert rule.citizens in cit.groups, rule.citizens
        else:
            assert all(countries.normalize(c) == c for c in rule.citizens), rule.citizens
        assert all(markets.is_supported(m) for m in rule.markets)
        assert rule.source.startswith("https://")
        if rule.status:  # a status the rule settles is one of each market's own
            for m in rule.markets:
                values = [o.value for o in cat.statuses[markets.get(m)["work_status"]]]
                assert rule.status in values, (m, rule.status)


def test_catalog_only_attributes_are_never_served():
    """Packs, fill slots and expiries are for the catalog's own readers: the served set (and so
    Phase 1's golden) never carries them."""
    cat = form_questions.catalog()
    eligibility = next(g for g in cat.groups if g.key == "eligibility")
    assert next(f for f in eligibility.fields if f.key == "over_18").pack == "us_screening"
    served = json.dumps(
        form_questions.resolve(home="US", apply_in=["US"], chosen=True).model_dump(mode="json")
    )
    assert "us_screening" not in served and '"pack"' not in served
    assert "noExpiry" not in served and '"fills"' not in served
    assert "fills" not in cat.answers[0].model_dump() and "noExpiry" not in cat.statuses["us"][0].model_dump()


def _today_groups(home: str) -> list[dict]:
    """groupFields(key, home) for every group, as autofill-options.ts did it."""
    m = markets.get(home)
    out = []
    for group in _TODAY["groups"]:
        fields = []
        for field in group["fields"]:
            if field.get("byHome"):
                field = {
                    **field,
                    "label": m["state_label"] or field["label"],
                    "optional": m["asks_state"] is False,
                }
            fields.append(field)
        out.append({**group, "fields": fields})
    return out


def _served(model) -> dict:
    return model.model_dump(exclude_defaults=True)


def _fixture(value) -> dict:
    """The fixture through the same schema, so defaults compare alike."""
    return Group.model_validate(value).model_dump(exclude_defaults=True)


@pytest.mark.parametrize("home", markets.keys())
def test_every_home_gets_todays_groups(home):
    got = form_questions.resolve(home=home, apply_in=[home], chosen=True)
    assert [_served(g) for g in got.groups] == [_fixture(g) for g in _today_groups(home)]


# Canada's `ca` and the UAE's `ae` wordings are new on purpose (Task 3.2): the golden holds the
# markets whose wording the fixture has.
@pytest.mark.parametrize(
    "market", [k for k in markets.keys() if markets.get(k)["work_auth_vocab"] in _TODAY["permits"]]
)
def test_every_market_gets_todays_permit_fields(market):
    got = form_questions.resolve(home="US", apply_in=[market], chosen=True)
    vocab = markets.get(market)["work_auth_vocab"]
    want = [
        Field.model_validate(f).model_dump(exclude_defaults=True) for f in _TODAY["permits"][vocab]
    ]
    assert [f.model_dump(exclude_defaults=True) for f in got.permits[market]] == want


def _state_line(home: str) -> Field:
    groups = form_questions.resolve(home=home, apply_in=[home], chosen=True).groups
    personal = next(g for g in groups if g.key == "personal")
    return next(f for f in personal.fields if f.key == "state")


def test_the_state_line_is_named_and_counted_by_where_you_live():
    """A UK address names a county and needs none; a US one needs its state (markets.yaml)."""
    uk, us = _state_line("UK"), _state_line("US")
    assert (uk.label, uk.optional) == ("County", True)
    assert (us.label, us.optional) == ("State", False)


def test_required_keys_leave_out_the_optional_fields():
    """What setup readiness counts: the state line only where an address there needs one."""
    def personal(home: str) -> list[str]:
        groups = form_questions.resolve(home=home, apply_in=[home], chosen=True).groups
        return form_questions.required_keys(next(g for g in groups if g.key == "personal").fields)

    assert "state" not in personal("UK") and "state" in personal("US")
    assert "address_2" not in personal("US") and "linkedin" not in personal("US")


def test_permits_are_keyed_by_market_in_apply_in_order():
    got = form_questions.resolve(home="IN", apply_in=["UK", "US", "DE"], chosen=True)
    assert list(got.permits) == ["UK", "US", "DE"]


def test_offers_eeo_follows_the_apply_in_markets():
    """Offered when any market you apply in has a checked set (US, UK today), wherever you live."""
    assert form_questions.resolve(home="IN", apply_in=["US"], chosen=True).offers_eeo is True
    assert form_questions.resolve(home="US", apply_in=["IN", "DE"], chosen=True).offers_eeo is False
    assert form_questions.resolve(home="DE", apply_in=["DE", "NL"], chosen=True).offers_eeo is False
    assert form_questions.resolve(home="DE", apply_in=["DE", "UK"], chosen=True).offers_eeo is True


def test_unchosen_resolves_no_country():
    qs = form_questions.resolve(home="US", apply_in=[], chosen=False)
    assert qs.permits == {} and qs.offers_eeo is False and qs.chosen is False


def test_unchosen_keeps_the_state_line_but_never_requires_it():
    """No country is chosen, so no address rule applies: the line keeps its catalog label."""
    groups = form_questions.resolve(home="US", apply_in=[], chosen=False).groups
    personal = next(g for g in groups if g.key == "personal")
    state = next(f for f in personal.fields if f.key == "state")
    assert (state.label, state.optional) == ("State", True)
    assert "state" not in form_questions.required_keys(personal.fields)


def test_no_apply_in_reads_as_home():
    """The market setting's rule (`MarketSetting`: empty `apply_in` reads as `[home]`)."""
    assert list(form_questions.resolve(home="UK", apply_in=[], chosen=True).permits) == ["UK"]
    assert form_questions.resolve(home="UK", apply_in=[], chosen=True).offers_eeo is True
    assert form_questions.resolve(home="IN", apply_in=[], chosen=True).offers_eeo is False
