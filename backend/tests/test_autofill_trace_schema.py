"""The stored run trace: strict shapes that keep a value out, and its two tables."""
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.models.autofill_mechanism_stat import AutofillMechanismStat
from app.models.autofill_run import AutofillRun
from app.schemas.autofill_trace import RunTrace, TraceField, TraceStep
from app.services import autofill_catalog

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


def _step(**kw):
    return {"op": "pick", "ms": 120, "engine": "jev", "p": 0.91, "floor": 0.8, "second": "asked",
            "first_p": 0.4, "first_same": True, "chose_none": False, "option": 3,
            "reason": "matched", **kw}


def test_a_map_step_may_name_a_sentinel_and_nothing_else_of_that_shape():
    step = TraceStep.model_validate({"op": "map", "route": "none", "sentinel": "years_unanswered"})
    assert step.sentinel == "years_unanswered"
    for bad in ("personal.city", "Jane Doe", "", "YEARS_UNANSWERED"):
        with pytest.raises(ValidationError):
            TraceStep.model_validate({"op": "map", "sentinel": bad})


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
    TraceStep.model_validate(_step(option=249))
    with pytest.raises(ValidationError):
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


def test_a_naive_timestamp_raises():
    with pytest.raises(ValidationError):
        RunTrace.model_validate(_run(started_at=datetime(2026, 10, 3, 12, 0)))
    with pytest.raises(ValidationError):
        RunTrace.model_validate(_run(ended_at="2026-10-03T12:00:00"))


@pytest.mark.parametrize("host", ("Jane Doe 555-0100", "Jobs.Example.com", "a b.com", "", "x.com/path"))
def test_host_is_a_hostname(host):
    with pytest.raises(ValidationError):
        RunTrace.model_validate(_run(host=host))


def test_host_may_carry_a_port():
    assert RunTrace.model_validate(_run(host="localhost:8080")).host == "localhost:8080"


@pytest.mark.parametrize("run_id", ("RUN-12345678", "run 12345678", "short", "run_12345678", "x" * 65))
def test_run_id_is_lowercase_and_dashed(run_id):
    with pytest.raises(ValidationError):
        RunTrace.model_validate(_run(run_id=run_id))


@pytest.mark.parametrize("source", ("Jane Doe", "LABEL", "aria label", "label_1"))
def test_label_source_rejects_anything_but_a_lowercase_word(source):
    with pytest.raises(ValidationError):
        TraceField.model_validate(_field(label_source=source))


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


def test_a_run_id_is_stored_once(db_session):
    for _ in range(2):
        db_session.add(AutofillRun(run_id="run-12345678", host="jobs.example.com", started_at=NOW, trace={}))
    with pytest.raises(IntegrityError):
        db_session.flush()


def _round(**kw):
    return {"round": 1, "why": "page_errors", "model": "claude-sonnet-5-5", "ms": 4200,
            "note": "The error names Source, which no field is called.",
            "actions": [{"type": "fill", "target": "f1", "outcome": "progress"},
                        {"type": "write", "target": "f4", "outcome": "progress", "written": 42},
                        {"type": "press_next", "target": "b1", "outcome": "moved"}],
            "rejected": [], "stopped": "moved", **kw}


def _snapshot(**kw):
    return {"fields": [{"fid": "f1", "question": "Field of study", "shape": "text", "required": True,
                        "options": [{"ref": "o1", "text": "Maths"}], "option_count": 1}],
            "buttons": [{"ref": "b1", "text": "Save and Continue", "role": "next"}],
            "errors": [{"text": "Source", "fid": "f1"}], "tabs": [{"ref": "t1", "host": "jobs.acme.test"}],
            "history": ["fill:f1 -> progress"], "excluded": ["write:f4"], **kw}


def test_a_reasoning_step_is_a_run_with_no_fields_and_its_rounds():
    run = RunTrace.model_validate(_run(fields=[], reasoning=[_round(snapshot=_snapshot())]))
    assert run.reasoning[0].actions[1].written == 42 and run.reasoning[0].snapshot.fields[0].question == "Field of study"
    assert RunTrace.model_validate(run.model_dump(mode="json")) == run


def test_a_round_that_never_asked_has_no_model_and_no_snapshot():
    run = RunTrace.model_validate(_run(fields=[], reasoning=[_round(model=None, actions=[], stopped="wall")]))
    assert run.reasoning[0].model is None and run.reasoning[0].snapshot is None


def test_a_reasoning_round_has_no_place_for_a_value():
    for bad in (_round(actions=[{"type": "write", "target": "f4", "outcome": "progress", "value": "BSc"}]),
                _round(note="x" * 201), _round(model="Claude Sonnet!"), _round(round=4), _round(round=0),
                _round(actions=[{"type": "submit", "target": "b1", "outcome": "moved"}]),
                _round(actions=[{"type": "write", "target": "Mathematics degree", "outcome": "progress"}]),
                _round(rejected=["Mathematics"]), _round(stopped="Mathematics"),
                _round(snapshot=_snapshot(value="BSc")),
                _round(snapshot=_snapshot(fields=[{"fid": "f1", "question": "q", "shape": "text", "value": "BSc"}])),
                _round(snapshot=_snapshot(history=["typed Mathematics"]))):
        with pytest.raises(ValidationError):
            RunTrace.model_validate(_run(reasoning=[bad]))


def test_a_run_holds_at_most_three_rounds_and_a_snapshot_stays_capped():
    with pytest.raises(ValidationError):
        RunTrace.model_validate(_run(reasoning=[_round()] * 4))
    big = _snapshot(fields=[{"fid": f"f{i}", "question": "q" * 300, "shape": "select",
                             "options": [{"ref": f"o{j}", "text": "t" * 300} for j in range(1, 21)], "option_count": 20}
                            for i in range(60)])
    with pytest.raises(ValidationError):
        RunTrace.model_validate(_run(reasoning=[_round(snapshot=big)]))
