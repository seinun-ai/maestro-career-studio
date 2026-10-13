"""The reasoning route's prompt follows the Screening answers level (model_settings.get_answer_level)."""

from app.services import autofill_pick, autofill_reasoned, model_settings
from tests.test_autofill_pick import HISTORY_FACTS, fake_reasoner, reasoned

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
