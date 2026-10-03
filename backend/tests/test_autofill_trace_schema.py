"""The stored run trace: strict shapes that keep a value out, and its two tables."""
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.autofill_mechanism_stat import AutofillMechanismStat
from app.models.autofill_run import AutofillRun
from app.schemas.autofill_trace import RunTrace, TraceField, TraceStep
from app.services import autofill_catalog

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


def _step(**kw):
    return {"op": "pick", "ms": 120, "engine": "jev", "p": 0.91, "floor": 0.8, "second": "asked",
            "first_p": 0.4, "first_same": True, "chose_none": False, "option": 3,
            "reason": "matched", **kw}


def _field(**kw):
    return {"fid": "0-12", "label": "Are you authorized to work?", "label_source": "aria-label",
            "shape": "select", "section": "Eligibility", "required": True,
            "options": ["Yes", "No"], "option_count": 2, "family": "f:ab12cd",
            "steps": [_step(), {"op": "move", "move": "click:o3", "effect": "progress", "word": "ok"}],
            "outcome": "filled", "round": 1, **kw}


def _run(**kw):
    return {"run_id": "run-12345678", "host": "jobs.example.com", "started_at": NOW, "ended_at": NOW,
            "halted": "stopped", "rounds": 2, "fields": [_field()], **kw}


def test_a_valid_run_round_trips():
    run = RunTrace.model_validate(_run())
    assert run.mode == "assist"
    assert RunTrace.model_validate(run.model_dump(mode="json")) == run


def test_an_unknown_key_raises_at_every_level():
    for bad in (_run(answer="Jane"),
                _run(fields=[_field(value="Jane")]),
                _run(fields=[_field(steps=[_step(text="Jane")])])):
        with pytest.raises(ValidationError):
            RunTrace.model_validate(bad)


def test_the_size_caps_hold():
    with pytest.raises(ValidationError):
        TraceField.model_validate(_field(label="x" * 201))
    with pytest.raises(ValidationError):
        TraceField.model_validate(_field(steps=[_step()] * 41))
    TraceField.model_validate(_field(steps=[_step()] * 40))
    with pytest.raises(ValidationError):
        RunTrace.model_validate(_run(fields=[_field()] * 201))
    with pytest.raises(ValidationError):
        TraceStep.model_validate(_step(option=251))
    TraceStep.model_validate(_step(option=250))


def test_word_and_outcome_are_lowercase_words_only():
    TraceStep.model_validate({"op": "write", "word": "no_change"})
    for bad in ("No, I do not", "Jane", "jane doe", "x" * 41):
        with pytest.raises(ValidationError):
            TraceStep.model_validate({"op": "write", "word": bad})
        with pytest.raises(ValidationError):
            TraceField.model_validate(_field(outcome=bad))


REAL_SLOTS = ("personal.phone", "custom.3", "experience.0.start", "derived.sponsorship_now_or_future",
              "eeo.disability_status", "skills", "derived.agrees_to_terms")


@pytest.mark.parametrize("slot", REAL_SLOTS)
def test_slot_accepts_a_real_fact_name(slot):
    assert TraceStep.model_validate({"op": "map", "slot": slot}).slot == slot


@pytest.mark.parametrize("slot", ("Jane Doe", "jane@x.com", "Personal.phone", "a-b", ""))
def test_slot_rejects_anything_else(slot):
    with pytest.raises(ValidationError):
        TraceStep.model_validate({"op": "map", "slot": slot})


def test_every_slot_the_catalog_builds_is_accepted():
    facts = autofill_catalog.build(
        {"personal": {"phone": "1", "city": "x"}, "eeo": {"disability_status": "no", "gender": "male"},
         "work_auth": {"sponsorship_now": False}, "preferences": {"how_heard": "x"},
         "education": [{"school": "S"}], "languages": [{"language": "French", "level": "native"}],
         "custom": [{"question": "q", "answer": "a"}]},
        [{"employer": "Acme", "title": "A", "start_date": "Aug 2021", "current": True}], ["Python"],
        company="Acme")
    assert facts
    for slot in facts:
        assert TraceStep.model_validate({"op": "map", "slot": slot}).slot == slot


@pytest.mark.parametrize("move", ("click:o3", "search:value", "search:word:2", "open", "scroll", "give_up"))
def test_move_accepts_the_step_ids(move):
    assert TraceStep.model_validate({"op": "move", "move": move}).move == move


@pytest.mark.parametrize("move", ("click:Jane", "click:o", "type:Jane"))
def test_move_rejects_free_text(move):
    with pytest.raises(ValidationError):
        TraceStep.model_validate({"op": "move", "move": move})


def test_family_is_a_hash():
    with pytest.raises(ValidationError):
        TraceField.model_validate(_field(family="Acme Corp"))


def test_the_two_tables_exist_after_migration(db_session):
    db_session.add(AutofillRun(run_id="run-12345678", host="jobs.example.com", started_at=NOW,
                               trace=RunTrace.model_validate(_run()).model_dump(mode="json")))
    db_session.add(AutofillMechanismStat(key="pick|jev|matched", counts={"n": 1}))
    db_session.commit()
    run = db_session.query(AutofillRun).one()
    assert run.trace["fields"][0]["fid"] == "0-12" and run.created_at is not None
    assert db_session.get(AutofillMechanismStat, "pick|jev|matched").counts == {"n": 1}
