"""The decision traces /map, /pick and /step return beside each answer: value-free by
construction (enums and numbers only), and optional."""
import pytest
from pydantic import ValidationError

from app.schemas.autofill_fill import DecisionTrace, Mapped, Picked, PolarityTrace, StepResponse


def test_a_decision_trace_holds_only_enums_and_numbers():
    t = DecisionTrace(engine="fast", p=0.93, floor=0.9, second="decided", first_p=0.82)
    assert t.model_dump() == {"engine": "fast", "p": 0.93, "floor": 0.9, "second": "decided", "first_p": 0.82}
    for bad in ({"engine": "gpt"}, {"second": "maybe"}, {"p": 1.5}, {"first_p": -0.1}, {"note": "x"}):
        with pytest.raises(ValidationError):
            DecisionTrace(**bad)


def test_answers_carry_an_optional_trace_and_polarity():
    assert Mapped(route="none").trace is None
    assert Picked(oids=[], reason="abstained").trace is None
    assert Picked(oids=[], reason="abstained").polarity is None
    assert StepResponse(mid=None, reason="abstained").trace is None
    assert StepResponse(mid=None, reason="abstained").polarity is None
    assert PolarityTrace(way="unsure").model_dump() == {"way": "unsure", "engine": None, "p": None}
