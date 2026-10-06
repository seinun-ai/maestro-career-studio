"""Polarity (owner, 2026-09-27): does a question ask the SAME thing as a Yes/No
fact, or the OPPOSITE? The AI judges only that; code flips the value; the pick
that follows is literal."""

import json

import pytest

from app.services import autofill_map, autofill_polarity, llm, model_settings
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


@pytest.fixture(autouse=True)
def _fresh_memory():
    """Each test starts with nothing remembered (the cache is per process)."""
    autofill_polarity.forget()
    yield
    autofill_polarity.forget()


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
def test_jev_decides_at_the_slots_floor_and_never_under_the_polarity_floor(db_session, monkeypatch):
    """An `any` slot (willing to relocate) is not flipped at its 0.5 match
    floor: polarity needs max(the slot's floor, POLARITY_FLOOR)."""
    fake_jev(monkeypatch, {"a": (OPPOSITE, 0.95), "b": (SAME, 0.92), "c": (SAME, 0.6), "d": (OPPOSITE, 0.8)})
    fake_llm(monkeypatch)   # the second opinion (for c) says nothing
    got = decide([ask("a"), ask("b"), ask("c", describe="preferences: willing to relocate", policy="any"),
                  ask("d", describe="preferences: willing to relocate", policy="any")], db_session)
    assert autofill_polarity.POLARITY_FLOOR == 0.8
    assert {k: (p.way, p.engine) for k, p in got.items()} == {
        "a": (OPPOSITE, "jev"), "b": (SAME, "jev"), "c": (None, None), "d": (OPPOSITE, "jev")}


@pytest.mark.usefixtures("jev_on")
def test_a_confident_jev_neither_abstains_without_a_second_opinion(db_session, monkeypatch):
    fake_jev(monkeypatch, {"q": (NEITHER, 0.95)})
    prompts = fake_llm(monkeypatch, {"q": (OPPOSITE, 0.99)})
    got = decide([ask("q")], db_session)["q"]
    assert (got.way, got.engine) == (NEITHER, "jev") and prompts == []
    assert autofill_polarity.answer_for("Yes", got.way) is None


@pytest.mark.usefixtures("jev_on")
@pytest.mark.parametrize("jev_says", [(OPPOSITE, 0.85), (NEITHER, 0.6)])
def test_when_jev_is_unsure_one_fast_second_opinion_decides(db_session, monkeypatch, jev_says):
    fake_jev(monkeypatch, {"q": jev_says, "r": (SAME, 0.95)})
    prompts = fake_llm(monkeypatch, {"q": (OPPOSITE, 0.95)})
    got = decide([ask("q"), ask("r")], db_session)
    assert (got["q"].way, got["q"].engine) == (OPPOSITE, "fast")
    assert (got["r"].way, got["r"].engine) == (SAME, "jev")
    [asked] = prompts
    assert asked["trace_name"] == "autofill-polarity-second"
    assert [f["id"] for f in json.loads(asked["prompt"].split("Fields: ", 1)[1])] == ["q"]
    assert asked["max_retries"] == 0 and asked["timeout"] <= autofill_polarity.POLARITY_MAX_S == 2.0


@pytest.mark.usefixtures("jev_on")
@pytest.mark.parametrize("fast_says, way", [((OPPOSITE, 0.85), None), ((NEITHER, 0.99), NEITHER), (None, None)])
def test_a_second_opinion_under_the_floor_or_neither_leaves_no_answer(db_session, monkeypatch, fast_says, way):
    fake_jev(monkeypatch, {"q": (OPPOSITE, 0.5)})
    fake_llm(monkeypatch, {"q": fast_says} if fast_says else {})
    got = decide([ask("q")], db_session)["q"]
    assert got.way == way and autofill_polarity.answer_for("No", got.way) is None


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


# ---------- the budget: capped at 2 s, leaving the pick, its second opinion and the reasoning call their slots


@pytest.mark.usefixtures("jev_on")
def test_the_polarity_second_opinion_leaves_the_rest_of_the_request_its_time(db_session, monkeypatch):
    """Asked 0.5 s in, it may take only what leaves Jev's pick (2 s), the
    pick's second opinion and the reasoning call (a second each) their start
    before OPTIONAL_PASS_BUDGET_S."""
    times = [0.0, 0.5]
    monkeypatch.setattr(autofill_map, "_clock", lambda: times.pop(0) if len(times) > 1 else times[0])
    fake_jev(monkeypatch, {"q": (OPPOSITE, 0.5)})
    prompts = fake_llm(monkeypatch)
    decide([ask("q")], db_session)
    expected = autofill_map.OPTIONAL_PASS_BUDGET_S - 0.5 - autofill_polarity.POLARITY_RESERVE_S
    assert prompts[0]["timeout"] == pytest.approx(expected) and 0 < expected <= autofill_polarity.POLARITY_MAX_S
    assert autofill_polarity.POLARITY_RESERVE_S == pytest.approx(2.0 + 2 * autofill_map.MIN_CALL_S)


# ---------- remembered for a while: a /step after a /pick, or a second run, does not ask again


@pytest.mark.usefixtures("jev_on")
def test_a_confident_answer_is_remembered_and_an_unsure_one_never(db_session, monkeypatch):
    calls = fake_jev(monkeypatch, {"q": (OPPOSITE, 0.95), "u": (OPPOSITE, 0.5), "n": (NEITHER, 0.95),
                                   "u2": (OPPOSITE, 0.5)})
    fake_llm(monkeypatch)
    decide([ask("q"), ask("u", question="Are you unsure?"), ask("n", question="Something else?")], db_session)
    calls.clear()
    got = decide([ask("q2"), ask("u2", question="Are you unsure?"), ask("n2", question="Something else?")],
                 db_session)
    assert (got["q2"].way, got["n2"].way, got["u2"].way) == (OPPOSITE, NEITHER, None)
    [call] = calls   # only the unsure one is asked again
    assert set(call["questions"]) == {"u2"}


def test_the_memory_is_bounded_and_forgets_after_its_time(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(autofill_polarity, "_clock", lambda: now[0])
    key = ("Q", SPONSOR, "exact")
    autofill_polarity._remember(key, autofill_polarity.Polarity(SAME, "jev"))
    assert autofill_polarity._recall(key).way == SAME
    now[0] += autofill_polarity.MEMORY_TTL_S + 1
    assert autofill_polarity._recall(key) is None
    for i in range(autofill_polarity.MEMORY_MAX + 20):
        autofill_polarity._remember((f"Q{i}", SPONSOR, "exact"), autofill_polarity.Polarity(SAME, "jev"))
    assert len(autofill_polarity._memory) == autofill_polarity.MEMORY_MAX
    assert autofill_polarity._recall(("Q0", SPONSOR, "exact")) is None   # the oldest went first


def test_the_memory_holds_no_value():
    """Keys are the question (page text), the fact's description and its policy; entries a way, an
    engine and the probability that decided it."""
    assert [f.name for f in autofill_polarity.Polarity.__dataclass_fields__.values()] == ["way", "engine", "p", "remembered"]


# ---------- the deciding probability travels with the polarity (the fill trace reads it)

@pytest.mark.usefixtures("jev_on")
def test_a_decided_polarity_carries_the_probability_that_decided_it(db_session, monkeypatch):
    fake_jev(monkeypatch, {"q": (SAME, 0.97), "r": (OPPOSITE, 0.5), "u": (OPPOSITE, 0.5)})
    fake_llm(monkeypatch, {"r": (OPPOSITE, 0.93), "u": (OPPOSITE, 0.6)})
    got = decide([ask("q"), ask("r", question="R?"), ask("u", question="U?")], db_session)
    assert (got["q"].way, got["q"].engine, got["q"].p) == (SAME, "jev", 0.97)
    assert (got["r"].way, got["r"].engine, got["r"].p) == (OPPOSITE, "fast", 0.93)
    assert got["u"] == autofill_polarity.UNSURE and got["u"].p is None


@pytest.mark.usefixtures("jev_on")
def test_a_remembered_polarity_keeps_its_probability(db_session, monkeypatch):
    fake_jev(monkeypatch, {"q": (SAME, 0.97)})
    decide([ask("q")], db_session)
    calls = fake_jev(monkeypatch)
    got = decide([ask("q2")], db_session)["q2"]   # a /step asking the same question as worded
    assert calls == []
    assert (got.way, got.engine, got.p) == (SAME, "jev", 0.97)


@pytest.mark.usefixtures("jev_on")
def test_a_recalled_polarity_is_marked_remembered_and_a_fresh_one_is_not(db_session, monkeypatch):
    fake_jev(monkeypatch, {"q": (SAME, 0.97)})
    fresh = decide([ask("q")], db_session)["q"]
    again = decide([ask("q2")], db_session)["q2"]
    assert (fresh.remembered, again.remembered) == (False, True)
    assert (again.way, again.engine, again.p) == (SAME, "jev", 0.97)
    key = autofill_polarity._key(ask("q"))
    assert autofill_polarity._recall(key).remembered is True
    assert autofill_polarity._memory[key][1].remembered is False   # the stored copy stays unmarked


# ---------- an undirected label reads as SAME (re-review of 6b90eb96)


@pytest.mark.usefixtures("jev_on")
def test_a_label_without_a_direction_of_its_own_is_offered_as_same(db_session, monkeypatch):
    """"Protected veteran status" or "Age requirement" asks about the fact
    with no direction of its own: that is SAME, never NEITHER — or the most
    common fields would be left unfilled."""
    calls = fake_jev(monkeypatch)
    decide([ask("q", question="Protected veteran status", describe="is a protected veteran")], db_session)
    criteria = calls[0]["questions"]["q"]["criteria"]
    assert "without a direction of its own" in criteria[SAME] and "status label" in criteria[SAME]
    # A terse label that does negate or reverse the fact ("Unrestricted work authorization (no sponsorship
    # required)") is not undirected: the same criterion sends it to Opposite.
    assert "do not negate or reverse the fact" in criteria[SAME] and "it is Opposite" in criteria[SAME]
    assert "reverse or a negation" in criteria[OPPOSITE]
    assert "something else" in criteria[NEITHER] and "direction" not in criteria[NEITHER]
    prompts = fake_llm(monkeypatch)
    autofill_polarity.forget()
    model_settings.set_autofill_engine(db_session, "fast")
    decide([ask("q", question="Protected veteran status", describe="is a protected veteran")], db_session)
    assert "without a direction of its own" in prompts[0]["prompt"]
