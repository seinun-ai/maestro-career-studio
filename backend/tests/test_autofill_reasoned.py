"""The reasoning route's prompt follows the Screening answers level (model_settings.get_answer_level)."""

import pytest

from app.services import autofill_catalog, autofill_pick, autofill_reasoned, llm, model_settings
from tests.test_autofill_pick import HISTORY_FACTS, fake_reasoner, opts, pf, reasoned

YEARS = "Do you have at least 5 years of experience with SQL?"


def test_history_level_lets_a_years_question_be_yes_when_the_history_shows_the_skill():
    rules = autofill_reasoned.prompt_rules(level="history")
    assert "shows the skill" in rules and "does not contradict" in rules
    assert "answer none when the history clearly shows fewer years" in rules


def test_the_queued_level_keeps_the_same_history_backed_years_rule():
    # "Queued means I qualify" is /map's: a years question it routes `reasoned` is still history-backed here.
    assert autofill_reasoned.prompt_rules(level="queued") == autofill_reasoned.prompt_rules(level="history")


def test_facts_level_keeps_years_questions_to_computed_years_only():
    rules = autofill_reasoned.prompt_rules(level="facts")
    assert "shows the skill" not in rules
    assert "Count years of experience from the dates" in rules


def test_the_protected_list_stays_in_the_reasoned_prompt_at_every_level():
    for level in ("facts", "history", "queued"):
        assert autofill_reasoned.NEVER_REASONED in autofill_reasoned.prompt_rules(level=level), level


def test_the_reasoned_pass_asks_with_the_answer_level_the_setting_holds(db_session, monkeypatch):
    for level, expect in (("facts", False), ("history", True), ("queued", True)):
        model_settings.set_answer_level(db_session, level)
        prompts = fake_reasoner(monkeypatch)
        autofill_pick.pick([reasoned("y", YEARS, "Yes", "No")], HISTORY_FACTS, db_session, None)
        [asked] = [p for p in prompts if p["trace_name"] == "autofill-reasoned-pick"]
        assert ("shows the skill" in asked["prompt"]) is expect, level


# ---------- level "queued" on a queued job: the history is asked FIRST; the keen Yes only when it is silent

QUEUED_YEARS = "Do you have at least 5 years of experience with SQL?"
ENOUGH = {"oid": "o1", "confidence": 0.95, "shown_by": ["j1", "j2"], "years": "enough"}


def fake_models(monkeypatch, years_entry, keen_oid="o1"):
    """The reasoning call answers `years_entry` for field y; the keen pick says `keen_oid`."""
    calls = []

    def call_openai(**kw):
        calls.append(kw)
        if kw["trace_name"] == "autofill-reasoned-pick":
            return {"answers": {"y": years_entry} if years_entry is not None else {}}
        return {"picks": {"y": {"oids": [keen_oid], "confidence": 0.9}}}

    monkeypatch.setattr(autofill_pick.llm, "call_openai", call_openai)
    return calls


def years_pick(db_session, *, level="queued", queued=True, question=QUEUED_YEARS, facts=HISTORY_FACTS):
    model_settings.set_answer_level(db_session, level)
    return autofill_pick.pick([pf("y", question=question, route="low_stakes", options=opts("Yes", "No"))],
                              facts, db_session, None, queued=queued)["y"]


def test_enough_years_in_the_history_is_its_yes_and_no_keen_pick_is_made(db_session, monkeypatch):
    calls = fake_models(monkeypatch, ENOUGH)
    got = years_pick(db_session)
    assert (got.oids, got.reason) == (["o1"], "assumed")
    assert [c["trace_name"] for c in calls] == ["autofill-reasoned-pick"]
    assert "also return \"years\"" in calls[0]["prompt"]


def test_fewer_years_than_asked_is_left_to_the_user_never_a_keen_yes(db_session, monkeypatch):
    calls = fake_models(monkeypatch, {"oid": "o2", "confidence": 0.95, "shown_by": ["j1"], "years": "fewer"})
    got = years_pick(db_session)
    # "asked", not "abstained": the loop finishes the field and never hands it to /step.
    assert (got.oids, got.reason) == ([], "asked")
    assert [c["trace_name"] for c in calls] == ["autofill-reasoned-pick"]


def test_a_history_silent_about_the_skill_gets_the_keen_yes(db_session, monkeypatch):
    calls = fake_models(monkeypatch, {"oid": "none", "confidence": 0.9, "shown_by": [], "years": "silent"})
    got = years_pick(db_session)
    assert got.oids == ["o1"] and got.reason == "assumed"
    keen_prompt = [c for c in calls if c["trace_name"] == "autofill-pick"][0]["prompt"]
    assert "(answered Yes)" in keen_prompt and "work authorization" in keen_prompt


@pytest.mark.parametrize("entry", [
    None,  # no readable answer
    {"oid": "none", "confidence": 0.9, "shown_by": ["j1"], "years": "silent"},  # "silent" yet cites a job
    {"oid": "o1", "confidence": 0.9, "shown_by": ["j1"]},  # no coverage word
    {"oid": "o1", "confidence": 0.9, "shown_by": ["j1"], "years": "plenty"},
    {"oid": "o2", "confidence": 0.95, "shown_by": ["j1"], "years": "enough"},  # enough, but a No
    {"oid": "o1", "confidence": 0.95, "shown_by": ["j9"], "years": "enough"},  # cites a job that is not there
])
def test_anything_but_a_clear_enough_or_silent_is_left_to_the_user(db_session, monkeypatch, entry):
    calls = fake_models(monkeypatch, entry)
    got = years_pick(db_session)
    assert got.oids == [] and got.reason == "asked"
    assert "autofill-pick" not in [c["trace_name"] for c in calls]


def test_an_applicant_with_no_history_is_silent_so_the_keen_yes_stands(db_session, monkeypatch):
    calls = fake_models(monkeypatch, None)
    got = years_pick(db_session, facts=autofill_catalog.build({}, [], ["SQL"]))
    assert got.oids == ["o1"]
    assert [c["trace_name"] for c in calls] == ["autofill-pick"]


def test_a_failed_reasoning_call_leaves_the_years_question_to_the_user(db_session, monkeypatch):
    def down(**kw):
        raise llm.LLMProviderError("down")

    monkeypatch.setattr(autofill_pick.llm, "call_openai", down)
    got = years_pick(db_session)
    assert (got.oids, got.reason) == ([], "asked")


def test_a_keen_pick_that_names_no_option_is_asked_too(db_session, monkeypatch):
    def call_openai(**kw):
        if kw["trace_name"] == "autofill-reasoned-pick":
            return {"answers": {"y": {"oid": "none", "confidence": 0.9, "shown_by": [], "years": "silent"}}}
        return {"picks": {"y": {"oids": [], "confidence": 0.9}}}

    monkeypatch.setattr(autofill_pick.llm, "call_openai", call_openai)
    assert years_pick(db_session).reason == "asked"


@pytest.mark.parametrize("question, marked", [
    ("Do you have 5+ YOE with SQL?", False), ("Do you have a decade of Java?", False),
    ("5+yrs of Rust?", False), ("Are you proficient in SQL?", True)])
def test_a_years_question_is_found_by_its_wording_or_by_the_maps_marker(db_session, monkeypatch, question, marked):
    calls = fake_models(monkeypatch, ENOUGH)
    model_settings.set_answer_level(db_session, "queued")
    got = autofill_pick.pick([pf("y", question=question, route="low_stakes", options=opts("Yes", "No"), years=marked)],
                             HISTORY_FACTS, db_session, None, queued=True)["y"]
    assert [c["trace_name"] for c in calls] == ["autofill-reasoned-pick"] and got.oids == ["o1"]


def test_a_requirement_question_that_is_no_years_question_is_picked_directly(db_session, monkeypatch):
    calls = fake_models(monkeypatch, ENOUGH)
    years_pick(db_session, question="Do you meet the listed requirements?")
    assert [c["trace_name"] for c in calls] == ["autofill-pick"]


@pytest.mark.parametrize("level, queued", [("history", True), ("queued", False)])
def test_below_the_queued_level_or_off_a_queued_job_the_history_is_not_asked_first(
        db_session, monkeypatch, level, queued):
    calls = fake_models(monkeypatch, ENOUGH)
    got = years_pick(db_session, level=level, queued=queued)
    assert [c["trace_name"] for c in calls] == ["autofill-pick"] and got.oids == ["o1"]


def test_only_a_question_naming_years_asks_the_history_first(db_session, monkeypatch):
    calls = fake_models(monkeypatch, ENOUGH)
    years_pick(db_session, question="Are you willing to travel?")
    assert [c["trace_name"] for c in calls] == ["autofill-pick"]


def test_the_years_rule_counts_from_the_jobs_that_show_the_skill():
    rule = autofill_reasoned.prompt_rules(level="queued")
    assert "count the years from the jobs that show the skill" in rule
    assert "Only a general question about years of experience, with no skill named" in rule
