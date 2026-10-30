"""The form-question catalog (services/data/form_questions.yaml): it loads, it is well formed,
every market's permit wording is in it, and the set resolved for any market is the hand-written
set it replaced (tests/fixtures/form_questions_today.json, dumped from
frontend/lib/autofill-options.ts)."""

import json
from pathlib import Path

import pytest

from app.schemas.form_questions import Field, Group
from app.services import form_questions, markets

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


def test_every_market_has_permit_wording():
    for key in markets.keys():
        assert markets.get(key)["work_auth_vocab"] in form_questions.catalog().permits


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
    got = form_questions.resolve(home=home, apply_in=[home])
    assert [_served(g) for g in got.groups] == [_fixture(g) for g in _today_groups(home)]


@pytest.mark.parametrize("market", markets.keys())
def test_every_market_gets_todays_permit_fields(market):
    got = form_questions.resolve(home="US", apply_in=[market])
    vocab = markets.get(market)["work_auth_vocab"]
    want = [
        Field.model_validate(f).model_dump(exclude_defaults=True) for f in _TODAY["permits"][vocab]
    ]
    assert [f.model_dump(exclude_defaults=True) for f in got.permits[market]] == want


def test_permits_are_keyed_by_market_in_apply_in_order():
    got = form_questions.resolve(home="IN", apply_in=["UK", "US", "DE"])
    assert list(got.permits) == ["UK", "US", "DE"]


def test_offers_eeo_follows_the_apply_in_markets():
    assert form_questions.resolve(home="IN", apply_in=["US"]).offers_eeo is True
    assert form_questions.resolve(home="US", apply_in=["IN", "DE"]).offers_eeo is False


def test_no_apply_in_reads_as_home():
    """The market setting's rule (`MarketSetting`: empty `apply_in` reads as `[home]`)."""
    assert list(form_questions.resolve(home="UK", apply_in=[]).permits) == ["UK"]
    assert form_questions.resolve(home="UK", apply_in=[]).offers_eeo is True
    assert form_questions.resolve(home="IN", apply_in=[]).offers_eeo is False
