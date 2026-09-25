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


def test_the_source_hint_is_bounded():
    assert PickRequest(fields=[_pick_field()], source_hint="rec_linkedin").source_hint == "rec_linkedin"
    with pytest.raises(ValidationError):
        PickRequest(fields=[_pick_field()], source_hint="x" * 61)
