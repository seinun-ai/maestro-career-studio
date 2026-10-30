"""The form-question catalog (services/data/form_questions.yaml): it loads, it is well formed, and every
market's permit wording is in it."""

from app.services import form_questions


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
    from app.services import markets

    for key in markets.keys():
        assert markets.get(key)["work_auth_vocab"] in form_questions.catalog().permits
