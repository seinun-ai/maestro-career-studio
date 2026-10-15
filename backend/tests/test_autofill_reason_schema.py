"""The reasoning step's request and reply (design 2026-10-14 §1–§2): value-free and capped by schema."""

import re

import pytest
from pydantic import ValidationError

from app.schemas.autofill_reason import (
    ACTION_TYPES, MAX_FIELDS, MAX_HISTORY, MAX_OPTIONS, REPLY, ReasonRequest, signature,
)
from app.services import autofill_catalog
from tests.extension_harness import ROOT


def _field(fid="f1", **kw):
    return {"fid": fid, "question": "Degree", "shape": "select", "required": True, "filled": False, **kw}


def _req(**kw):
    return {"why": "page_errors", "round": 1, "fields": [_field()], **kw}


def test_a_snapshot_field_has_no_place_for_a_value():
    for key in ("value", "committed", "answer"):
        with pytest.raises(ValidationError):
            ReasonRequest.model_validate(_req(fields=[_field(**{key: "Ada Lovelace"})]))


def test_the_caps_hold():
    with pytest.raises(ValidationError):
        ReasonRequest.model_validate(_req(fields=[_field(f"f{i}") for i in range(MAX_FIELDS + 1)]))
    opts = [{"ref": f"o{i}", "text": "x"} for i in range(1, MAX_OPTIONS + 2)]
    with pytest.raises(ValidationError):
        ReasonRequest.model_validate(_req(fields=[_field(options=opts)]))
    with pytest.raises(ValidationError):
        ReasonRequest.model_validate(_req(history=["fill:f1 -> no_effect"] * (MAX_HISTORY + 1)))
    with pytest.raises(ValidationError):   # a history line is words and ids, never page text
        ReasonRequest.model_validate(_req(history=["fill:f1 -> typed Ada"]))


def test_a_reply_is_one_to_three_known_actions_and_a_short_note():
    ok = REPLY.validate_python({"note": "Degree is empty.", "actions": [{"type": "fill", "fids": ["f1"]}]})
    assert ok.actions[0].type == "fill"
    for bad in ({"note": "x", "actions": []},
                {"note": "x", "actions": [{"type": "fill", "fids": ["f1"]}] * 4},
                {"note": "x" * 201, "actions": [{"type": "fill", "fids": ["f1"]}]},
                {"note": "x", "actions": [{"type": "submit", "button": "b1"}]},
                {"note": "x", "actions": [{"type": "choose", "fid": "f1", "option": "o2"}]}):
        with pytest.raises(ValidationError):
            REPLY.validate_python(bad)


def test_every_action_type_is_listed_and_signs_by_its_target():
    assert set(ACTION_TYPES) == {"fill", "answer_from", "write", "choose", "retry", "redo", "close_dialog",
                                 "press_next", "follow_tab", "ask_user"}
    reply = REPLY.validate_python({"note": "", "actions": [
        {"type": "write", "fid": "f2"}, {"type": "press_next", "button": "b1"}, {"type": "fill", "fids": ["f3", "f4"]}]})
    assert [signature(a) for a in reply.actions] == ["write:f2", "press_next:b1", "fill:f3"]


def test_the_backends_protected_slots_are_the_drivers():
    js = (ROOT / "extension" / "shared" / "queue-run.js").read_text(encoding="utf-8")
    source = re.search(r"const PROTECTED_SLOT = /(.*)/;", js).group(1)
    assert autofill_catalog.PROTECTED_SLOT.pattern == source
