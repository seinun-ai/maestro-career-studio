import pytest
from pydantic import ValidationError

from app.schemas.autofill_fill import (
    MAX_FIELDS,
    MAX_MAP_OPTIONS,
    MAX_PICK_OPTIONS,
    MapField,
    MapRequest,
    PickField,
    PickRequest,
    Picked,
    StepRequest,
)


def _map_field(**kw):
    return {"fid": "a", "question": "City", "shape": "text", **kw}


def _pick_field(**kw):
    return {"fid": "a", "question": "City", "route": "slot", "slot": "personal.city",
            "options": [{"oid": "o1", "text": "Springfield"}], **kw}


def test_a_map_request_takes_every_shape_the_extension_sends():
    for shape in ("text", "date", "select", "group", "search", "popup"):
        assert MapField(**_map_field(shape=shape, multi=True)).shape == shape


@pytest.mark.parametrize("model, body", [
    (MapRequest, {"fields": [_map_field()], "surprise": 1}),
    (MapRequest, {"fields": [_map_field(value="leak")]}),
    (PickRequest, {"fields": [_pick_field(policy="any")]}),
    (PickRequest, {"fields": [_pick_field(options=[{"oid": "o1", "text": "x", "value": "y"}])]}),
])
def test_unknown_keys_are_refused(model, body):
    with pytest.raises(ValidationError):
        model(**body)


def test_a_client_cannot_send_a_policy_or_low_stakes_flag():
    """Policy comes from the slot and low-stakes from the setting, server-side."""
    for key in ("policy", "low_stakes"):
        with pytest.raises(ValidationError):
            MapRequest(fields=[_map_field()], **{key: True})
        with pytest.raises(ValidationError):
            PickRequest(fields=[_pick_field()], **{key: True})


def test_option_and_field_caps():
    with pytest.raises(ValidationError):
        MapField(**_map_field(options=["x"] * (MAX_MAP_OPTIONS + 1)))
    with pytest.raises(ValidationError):
        PickField(**_pick_field(options=[{"oid": f"o{i}", "text": "x"} for i in range(MAX_PICK_OPTIONS + 1)]))
    with pytest.raises(ValidationError):
        MapRequest(fields=[_map_field(fid=str(i)) for i in range(MAX_FIELDS + 1)])
    with pytest.raises(ValidationError):
        MapRequest(fields=[])
    with pytest.raises(ValidationError):
        PickField(**_pick_field(options=[]))


def test_a_pick_route_is_slot_or_low_stakes_only():
    with pytest.raises(ValidationError):
        PickField(**_pick_field(route="free_text"))


@pytest.mark.parametrize("url", ["https://job-boards.greenhouse.io/acme/jobs/7?gh_jid=7", "http://localhost:3000/apply",
                                 "HTTPS://ACME.example/a", "https://acme.example/" + "x" * 2000])
def test_a_page_url_is_an_http_address(url):
    assert PickRequest(fields=[_pick_field()], page_url=url).page_url == url
    assert PickRequest(fields=[_pick_field()]).page_url is None


@pytest.mark.parametrize("url", ["", "acme.example/apply", "javascript:alert(1)", "chrome://extensions", "file:///etc/passwd",
                                 "https://acme.example/a b", "https://acme.example/" + "x" * 2100])
def test_a_page_url_that_is_not_an_http_address_is_refused(url):
    with pytest.raises(ValidationError):
        PickRequest(fields=[_pick_field()], page_url=url)


def test_the_years_marker_is_echoed_on_a_pick_field_and_a_step_request():
    assert PickRequest(fields=[_pick_field()]).fields[0].years is False
    assert PickRequest(fields=[_pick_field(years=True)]).fields[0].years is True
    step = {"fid": "a", "question": "Q", "route": "low_stakes", "candidates": [{"mid": "give_up", "describe": "Stop"}]}
    assert StepRequest(**step).years is False and StepRequest(**step, years=True).years is True


def test_asked_is_a_pick_reason():
    assert Picked(oids=[], reason="asked").reason == "asked"


def test_the_source_hint_is_bounded():
    assert PickRequest(fields=[_pick_field()], source_hint="rec_linkedin").source_hint == "rec_linkedin"
    with pytest.raises(ValidationError):
        PickRequest(fields=[_pick_field()], source_hint="x" * 61)


def test_the_no_option_key_is_reserved():
    with pytest.raises(ValidationError):
        PickField(**_pick_field(options=[{"oid": "none", "text": "No"}]))
    with pytest.raises(ValidationError):
        PickField(**_pick_field(options=[{"oid": "", "text": "No"}]))


def test_selectors_and_ids_are_validated_at_the_edge():
    from uuid import UUID

    app_id = "4f1c3c0e-7d7e-4f5a-9d0a-2b1f5b3c9e11"
    assert MapRequest(fields=[_map_field()], application_id=app_id).application_id == UUID(app_id)
    with pytest.raises(ValidationError):
        MapRequest(fields=[_map_field()], application_id="not-a-uuid")
    with pytest.raises(ValidationError):
        MapRequest(fields=[_map_field()], base="x" * 201)
    with pytest.raises(ValidationError):
        MapField(**_map_field(fid=""))
    with pytest.raises(ValidationError):
        PickField(**_pick_field(fid=""))


def test_the_reserved_oid_is_the_pick_no_match_key():
    from app.schemas.autofill_fill import RESERVED_OID
    from app.services.autofill_choose import NO_OPTION

    assert RESERVED_OID == NO_OPTION


def test_field_ids_are_the_extensions_shape():
    """`<frame>-<n>` (inventory.js): letters, digits, `-` and `_` only."""
    assert MapField(**_map_field(fid="k3x9ab-12")).fid == "k3x9ab-12"
    assert PickField(**_pick_field(fid="k3x9ab-12")).fid == "k3x9ab-12"
    for fid in ("", "a b", 'f"; x', "x" * 65, "a\nb"):
        with pytest.raises(ValidationError):
            MapField(**_map_field(fid=fid))
        with pytest.raises(ValidationError):
            PickField(**_pick_field(fid=fid))


def test_a_reasoned_field_is_picked_but_never_stepped():
    """The reasoning route answers in /pick only: the adaptive step has no
    history to answer from, so it refuses the route."""
    from app.schemas.autofill_fill import StepRequest

    assert PickField(**_pick_field(route="reasoned")).route == "reasoned"
    with pytest.raises(ValidationError):
        StepRequest(fid="a", question="Q", route="reasoned", candidates=[{"mid": "open", "describe": "Open"}])
