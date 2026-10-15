"""A "what type of sponsorship" question with a saved No picks the option that means none / not applicable, in code.
Owner decision 2026-10-15: the saved No is used even when the question counts OPT or STEM OPT as sponsorship."""

import pytest

from app.schemas.autofill_fill import PickField, PickOption, StepRequest
from app.services import autofill_catalog, autofill_pick, autofill_sponsorship, autofill_step
from tests.test_autofill_choose_jev import jev_on  # noqa: F401  (fixture)
from tests.test_autofill_pick import fake_jev, polarity_reply

NOW = "What type of sponsorship will you need now to work in the U.S?"
FUTURE = "What type of sponsorship will you need in the future to work in the U.S?"
TYPES = ["H-1B", "TN", "Not applicable"]


def facts_of(now=False, future=False):
    return autofill_catalog.build({"work_auth": {"sponsorship_now": now, "sponsorship_future": future}}, [], [])


def field(question, options, slot="work_auth.sponsorship_now"):
    return PickField(fid="s", question=question, route="slot", slot=slot,
                     options=[PickOption(oid=f"o{i}", text=t) for i, t in enumerate(options, start=1)])


def pick(session, question, options, facts=None, slot="work_auth.sponsorship_now"):
    return autofill_pick.pick([field(question, options, slot)], facts or facts_of(), session, None)["s"]


@pytest.fixture(autouse=True)
def _no_model(monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("a model was asked")
    monkeypatch.setattr(autofill_pick.jev, "decide", boom)
    monkeypatch.setattr(autofill_pick.llm, "call_openai", boom)


@pytest.mark.parametrize("question", [
    NOW, FUTURE, "Which type of visa sponsorship do you require?", "Sponsorship type", "What kind of sponsorship would you need?",
    "What type of sponsorship will you need in the future to work in the U.S? (H-1B, TN, F-1 STEM OPT)"])
def test_a_type_of_sponsorship_question_is_recognised(question):
    assert autofill_sponsorship.asks_type(question)


@pytest.mark.parametrize("question", [
    "Will you now or in the future require sponsorship?", "Do you require visa sponsorship?",
    "Are you legally authorized to work in the U.S.?", "What type of laptop do you prefer?", "Type your name"])
def test_a_yes_no_sponsorship_question_is_not_a_type_question(question):
    assert not autofill_sponsorship.asks_type(question)


@pytest.mark.parametrize("none", ["Not applicable", "N/A", "None", "No sponsorship required", "Not Applicable - I do not need sponsorship",
                                  "I do not require sponsorship"])
def test_a_false_sponsorship_fact_picks_the_option_that_means_none(db_session, none):
    got = pick(db_session, NOW, ["H-1B", "TN", none])
    assert (got.oids, got.reason) == (["o3"], "matched")


@pytest.mark.parametrize(("slot", "facts"), [
    ("work_auth.sponsorship_future", facts_of()), ("derived.sponsorship_now_or_future", facts_of())])
def test_the_future_and_the_either_fact_do_the_same(db_session, slot, facts):
    assert pick(db_session, FUTURE, TYPES, facts, slot).oids == ["o3"]


def test_no_option_that_means_none_leaves_the_question_to_the_user(db_session):
    got = pick(db_session, NOW, ["H-1B", "TN", "O-1", "Other"])
    assert got.oids == [] and got.reason == "abstained"
    assert pick(db_session, NOW, ["H-1B", "TN", "None of the above"]).oids == []


def test_the_saved_no_is_used_even_when_the_question_counts_opt_as_sponsorship(db_session):
    question = "What type of sponsorship will you need now (H-1B, TN, F-1 STEM OPT, AOS Portability)?"
    assert pick(db_session, question, ["H-1B", "TN", "F-1 STEM OPT", "Not applicable"]).oids == ["o4"]


@pytest.mark.usefixtures("jev_on")
def test_a_saved_yes_never_takes_this_rule(db_session, monkeypatch):
    calls = fake_jev(monkeypatch)
    monkeypatch.setattr(autofill_pick.llm, "call_openai", lambda **kw: polarity_reply(kw) if kw["trace_name"].startswith(
        "autofill-polarity") else {})
    got = autofill_pick.pick([field(NOW, TYPES)], facts_of(now=True), db_session, None)["s"]
    assert got.oids == [] and calls   # the ordinary path asked the model, and the model chose none


@pytest.mark.usefixtures("jev_on")
def test_a_yes_no_question_keeps_the_polarity_path(db_session, monkeypatch):
    calls = fake_jev(monkeypatch, {"s": ("o2", 0.95)})
    got = autofill_pick.pick([field("Will you require visa sponsorship now?", ["Yes", "No"])], facts_of(), db_session, None)["s"]
    assert calls and got.oids == ["o2"]


def test_the_step_clicks_the_none_option_and_gives_up_without_one(db_session):
    def step(*texts):
        cands = [{"mid": f"click:o{i}", "describe": f'Click the option "{t}"'} for i, t in enumerate(texts, start=1)]
        req = StepRequest(fid="s", question=NOW, route="slot", slot="work_auth.sponsorship_now",
                          candidates=[*cands, {"mid": "give_up", "describe": "Stop"}])
        return autofill_step.step(req, facts_of(), db_session, None)

    got = step(*TYPES)
    assert (got.mid, got.reason) == ("click:o3", "matched")
    got = step("H-1B", "TN")
    assert got.mid is None and got.reason == "abstained"


def test_the_step_opens_a_closed_list_before_reading_its_options(db_session):
    req = StepRequest(fid="s", question=NOW, route="slot", slot="work_auth.sponsorship_now",
                      candidates=[{"mid": "open", "describe": "Open the list"}, {"mid": "give_up", "describe": "Stop"}])
    got = autofill_step.step(req, facts_of(), db_session, None)
    assert (got.mid, got.reason) == ("open", "progress")
