"""Polarity (owner, 2026-09-27): does a question ask the SAME thing as a Yes/No
fact, or the OPPOSITE? The AI judges only that; code flips the value; the pick
that follows is literal."""

import json

import pytest

from app.services import autofill_map, autofill_polarity, llm
from app.services.autofill_polarity import NEITHER, OPPOSITE, SAME, Ask
from tests.test_autofill_choose_jev import _answer, jev_on  # noqa: F401  (fixture)

SPONSOR = "will need visa sponsorship in the future (yes/no)"
WITHOUT = "Are you authorized to work without requiring sponsorship in the future?"


def ask(fid="q", question=WITHOUT, describe=SPONSOR, policy="exact"):
    return Ask(fid=fid, question=question, describe=describe, policy=policy)


def fake_jev(monkeypatch, ways=None):
    calls = []

    def decide(questions, state, session=None):
        calls.append({"questions": questions, "state": state})
        return {k: _answer(q["criteria"], *(ways or {}).get(k, (SAME, 0.95))) for k, q in questions.items()}

    monkeypatch.setattr(autofill_polarity.jev, "decide", decide)
    return calls


def fake_llm(monkeypatch, ways=None, fail=None):
    prompts = []

    def call_openai(**kw):
        prompts.append(kw)
        if fail:
            raise fail
        return {"polarity": {k: {"key": w, "confidence": p} for k, (w, p) in (ways or {}).items()}}

    monkeypatch.setattr(autofill_polarity.llm, "call_openai", call_openai)
    return prompts


def decide(asks, db_session, budget=None):
    return autofill_polarity.decide(asks, db_session, budget or autofill_map.Budget())


# ---------- the flip is code's

@pytest.mark.parametrize("value, way, answer", [
    ("No", SAME, "No"), ("Yes", SAME, "Yes"), ("No", OPPOSITE, "Yes"), ("Yes", OPPOSITE, "No"),
    ("No, I do not have a disability", SAME, "No, I do not have a disability"),
    ("No, I do not have a disability", OPPOSITE, None),   # a wordy value is never rewritten
    ("Yes, previously", OPPOSITE, None),
    ("No", None, None), ("Yes", NEITHER, None),
])
def test_code_flips_only_a_plain_yes_or_no(value, way, answer):
    assert autofill_polarity.answer_for(value, way) == answer


# ---------- Jev first, one fast second opinion, same floors

@pytest.mark.usefixtures("jev_on")
def test_jev_decides_at_the_slots_floor(db_session, monkeypatch):
    fake_jev(monkeypatch, {"a": (OPPOSITE, 0.95), "b": (SAME, 0.92), "c": (SAME, 0.6)})
    fake_llm(monkeypatch)   # the second opinion (for c) says nothing
    got = decide([ask("a"), ask("b"), ask("c", policy="any")], db_session)
    assert {k: (p.way, p.engine) for k, p in got.items()} == {
        "a": (OPPOSITE, "jev"), "b": (SAME, "jev"), "c": (SAME, "jev")}   # any's floor is 0.5


@pytest.mark.usefixtures("jev_on")
@pytest.mark.parametrize("jev_says", [(OPPOSITE, 0.85), (NEITHER, 0.99)])
def test_when_jev_is_unsure_one_fast_second_opinion_decides(db_session, monkeypatch, jev_says):
    fake_jev(monkeypatch, {"q": jev_says, "r": (SAME, 0.95)})
    prompts = fake_llm(monkeypatch, {"q": (OPPOSITE, 0.95)})
    got = decide([ask("q"), ask("r")], db_session)
    assert (got["q"].way, got["q"].engine) == (OPPOSITE, "fast")
    assert (got["r"].way, got["r"].engine) == (SAME, "jev")
    [asked] = prompts
    assert asked["trace_name"] == "autofill-polarity-second"
    assert [f["id"] for f in json.loads(asked["prompt"].split("Fields: ", 1)[1])] == ["q"]
    assert asked["max_retries"] == 0 and asked["timeout"] <= autofill_map.SECOND_OPINION_MAX_S


@pytest.mark.usefixtures("jev_on")
@pytest.mark.parametrize("fast_says", [(OPPOSITE, 0.85), (NEITHER, 0.99), None])
def test_a_second_opinion_under_the_floor_or_neither_leaves_it_unsure(db_session, monkeypatch, fast_says):
    fake_jev(monkeypatch, {"q": (OPPOSITE, 0.5)})
    fake_llm(monkeypatch, {"q": fast_says} if fast_says else {})
    got = decide([ask("q")], db_session)["q"]
    assert (got.way, got.engine) == (None, None)


@pytest.mark.usefixtures("jev_on")
@pytest.mark.parametrize("failure", [llm.LLMProviderError("down"), ValueError("not JSON after retries")])
def test_a_failed_second_opinion_leaves_it_unsure(db_session, monkeypatch, failure):
    fake_jev(monkeypatch, {"q": (OPPOSITE, 0.5)})
    fake_llm(monkeypatch, fail=failure)
    assert decide([ask("q")], db_session)["q"].way is None


@pytest.mark.usefixtures("jev_on")
def test_no_second_opinion_once_the_budget_is_spent(db_session, monkeypatch):
    times = [0.0] + [autofill_map.OPTIONAL_PASS_BUDGET_S + 0.1]
    monkeypatch.setattr(autofill_map, "_clock", lambda: times.pop(0) if len(times) > 1 else times[0])
    fake_jev(monkeypatch, {"q": (OPPOSITE, 0.5)})
    prompts = fake_llm(monkeypatch, {"q": (OPPOSITE, 0.99)})
    assert decide([ask("q")], db_session)["q"].way is None and prompts == []


@pytest.mark.usefixtures("jev_on")
def test_a_jev_failure_leaves_the_fast_model_to_decide_at_the_same_floors(db_session, monkeypatch):
    def down(*a, **k):
        raise llm.LLMProviderError("down")

    monkeypatch.setattr(autofill_polarity.jev, "decide", down)
    prompts = fake_llm(monkeypatch, {"q": (OPPOSITE, 0.95), "r": (SAME, 0.8)})
    got = decide([ask("q"), ask("r")], db_session)
    assert {k: (p.way, p.engine) for k, p in got.items()} == {"q": (OPPOSITE, "fast"), "r": (None, None)}
    assert prompts[0]["trace_name"] == "autofill-polarity"


def test_the_fast_engine_decides_with_the_fast_model(db_session, monkeypatch):
    calls = fake_jev(monkeypatch)
    prompts = fake_llm(monkeypatch, {"q": (OPPOSITE, 0.95)})
    got = decide([ask("q")], db_session)["q"]
    assert (got.way, got.engine) == (OPPOSITE, "fast") and calls == []
    assert [p["trace_name"] for p in prompts] == ["autofill-polarity"]


# ---------- what the polarity call carries: the question and the fact's description, never a value

@pytest.mark.usefixtures("jev_on")
def test_the_polarity_call_carries_no_value(db_session, monkeypatch):
    calls = fake_jev(monkeypatch, {"q": (OPPOSITE, 0.5)})
    prompts = fake_llm(monkeypatch)
    decide([ask("q")], db_session)
    question = calls[0]["questions"]["q"]
    assert set(question["criteria"]) == {SAME, OPPOSITE, NEITHER}
    assert json.dumps(SPONSOR) in question["instructions"] and json.dumps(WITHOUT) in question["instructions"]
    assert calls[0]["state"] == {"fields": [{"id": "q", "question": WITHOUT, "fact": SPONSOR}]}
    blob = json.dumps(calls) + json.dumps(prompts)
    assert '"No"' not in blob and '"Yes"' not in blob and "value" not in blob.lower().replace("values", "")


def test_nothing_to_decide_asks_nothing(db_session, monkeypatch):
    prompts = fake_llm(monkeypatch)
    assert decide([], db_session) == {} and prompts == []
