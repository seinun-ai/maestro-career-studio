import pytest
from pydantic import ValidationError

from app.schemas.autofill_choose import ChooseField, ChooseRequest


def test_a_field_with_options_keeps_them_verbatim():
    field = ChooseField(
        qid="ab12-3",
        label="Are you willing to relocate?",
        kind="radio",
        options=["Yes", "No", "Prefer not to say"],
    )
    assert field.options == ["Yes", "No", "Prefer not to say"]


def test_known_value_is_optional_and_defaults_to_none():
    """Present only when the profile held an answer the page rejected. Its
    absence is the ordinary case: the field is being asked about because
    nothing answered it."""
    assert ChooseField(qid="a-0", label="Notice period", kind="text").known_value is None


def test_an_unknown_kind_is_refused():
    """The kind vocabulary is the same six shapes telemetry knows. A seventh
    would reach the prompt as an unhandled branch and be answered anyway."""
    with pytest.raises(ValidationError):
        ChooseField(qid="a-0", label="x", kind="canvas")


def test_the_batch_is_capped():
    """A page with 200 open fields must not become one 200-field prompt."""
    with pytest.raises(ValidationError):
        ChooseRequest(
            fields=[
                ChooseField(qid=f"a-{i}", label="q", kind="text") for i in range(41)
            ]
        )
