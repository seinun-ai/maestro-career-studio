"""The highest education level completed is a derived fact, and a list of education thresholds is answered from it in
code: the highest threshold met, never "None of the above", and nothing when none is met."""

from datetime import date

import pytest

from app.schemas.autofill_fill import PickField, PickOption, StepRequest
from app.schemas.autofill_reason import REPLY, ReasonRequest
from app.services import autofill_catalog, autofill_education, autofill_pick, autofill_reason, autofill_step
from app.services.autofill_education import SLOT

TODAY = date(2026, 10, 15)
THRESHOLDS = ["Bachelor's degree or higher", "Combination of relevant education, experience, and training",
              "None of the above"]


def facts_of(*degrees, **entry):
    education = [{"school": "Acme University", "degree": d, "end_year": y} for d, y in degrees] or None
    profile = {"education": education} if education else {}
    return autofill_catalog.build(profile, [], [], today=TODAY)


def opts(*texts):
    return [PickOption(oid=f"o{i}", text=t) for i, t in enumerate(texts, start=1)]


def field(options, **kw):
    return PickField(fid="e", question="Which best describes your education?", route="slot", slot=SLOT,
                     options=options, **kw)


def pick(facts, options, session, **kw):
    return autofill_pick.pick([field(options, **kw)], facts, session, None)["e"]


@pytest.fixture(autouse=True)
def _no_model(monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("a model was asked")
    monkeypatch.setattr(autofill_pick.jev, "decide", boom)
    monkeypatch.setattr(autofill_pick.llm, "call_openai", boom)


# ---------- the fact

def test_the_fact_is_the_highest_level_completed_and_an_exact_policy():
    fact = facts_of(("Master's", "2024"), ("Bachelor's", "2019"))[SLOT]
    assert fact.value == "Master's degree" and fact.policy == "exact" and not fact.yes_no
    assert "education" in fact.describe and "higher" in fact.describe


@pytest.mark.parametrize(("degree", "value"), [
    ("Masters of Business analytics", "Master's degree"), ("MBA", "Master's degree"), ("B.S.", "Bachelor's degree"),
    ("PhD", "Doctorate"), ("Associate of Arts", "Associate degree"), ("High School Diploma", "High school diploma")])
def test_each_level_is_read_from_the_profiles_degree_words(degree, value):
    assert facts_of((degree, "2020"))[SLOT].value == value


def test_the_level_is_not_inferred_when_the_profile_names_none():
    assert SLOT not in facts_of()
    assert SLOT not in facts_of(("Certificate in Data", "2020"))
    assert SLOT not in facts_of(("", "2020"))


def test_a_degree_not_finished_yet_does_not_count():
    got = facts_of(("Master's", "2028"), ("Bachelor's", "2019"))
    assert got[SLOT].value == "Bachelor's degree"
    assert SLOT not in facts_of(("Master's", "2028"))


def test_a_degree_with_no_year_counts_and_the_highest_of_several_wins():
    assert facts_of(("Bachelor's", ""), ("Master's", None), ("Associate", "2015"))[SLOT].value == "Master's degree"


# ---------- the threshold, picked in code

def test_a_masters_holder_takes_bachelors_or_higher_not_none_of_the_above(db_session):
    got = pick(facts_of(("Master's", "2024")), opts(*THRESHOLDS), db_session)
    assert (got.oids, got.reason) == (["o1"], "matched")


def test_an_associate_alone_meets_no_threshold_and_abstains(db_session):
    got = pick(facts_of(("Associate", "2020")), opts(*THRESHOLDS), db_session)
    assert got.oids == [] and got.reason == "abstained"


def test_none_of_the_above_and_a_combination_are_never_picked(db_session):
    got = pick(facts_of(("Master's", "2024")), opts("Combination of relevant education, experience, and training",
                                                    "None of the above"), db_session)
    assert got.oids == []


def test_the_highest_threshold_met_wins_and_a_higher_one_is_not_claimed(db_session):
    options = opts("High school diploma or higher", "Associate degree or higher", "Bachelor's degree or higher",
                   "Master's degree or higher", "Doctorate")
    assert pick(facts_of(("Master's", "2024")), options, db_session).oids == ["o4"]
    assert pick(facts_of(("Bachelor's", "2024")), options, db_session).oids == ["o3"]
    assert pick(facts_of(("PhD", "2024")), options, db_session).oids == ["o5"]


def test_a_plain_list_of_levels_picks_the_applicants_own_level_as_a_match(db_session):
    options = opts("High school", "Associate's degree", "Bachelor's degree", "Master's degree", "Doctorate")
    got = pick(facts_of(("Master's", "2024")), options, db_session)
    assert (got.oids, got.reason) == (["o4"], "matched")


def test_a_list_missing_the_applicants_level_takes_the_nearest_below_as_closest(db_session):
    options = opts("High school", "Associate's degree", "Bachelor's degree")
    got = pick(facts_of(("Master's", "2024")), options, db_session)
    assert (got.oids, got.reason) == (["o3"], "closest")
    # A partial view of the list is a guess: left to the user.
    assert pick(facts_of(("Master's", "2024")), options, db_session, complete=False).oids == []


@pytest.mark.parametrize("text", ["Some college, no degree", "Less than high school", "Bachelor's degree (in progress)",
                                  "Currently pursuing a Master's degree", "Yes", "No"])
def test_options_that_are_not_a_completed_level_are_never_picked(db_session, text):
    assert pick(facts_of(("Master's", "2024")), opts(text, "None of the above"), db_session).oids == []


def test_a_field_with_this_slot_is_decided_without_asking_a_model(db_session):
    """The autouse fixture makes any model call fail; one field in a batch with others is decided in code too."""
    other = PickField(fid="x", question="Gender", route="slot", slot="eeo.gender", options=opts("Female", "Male"))
    facts = facts_of(("Master's", "2024"))
    out = autofill_pick.pick([field(opts(*THRESHOLDS)), other], facts, db_session, None)
    assert out["e"].oids == ["o1"] and out["x"].oids == []


# ---------- /step

def test_the_step_clicks_the_threshold_the_page_lists_and_gives_up_when_none_is_met(db_session):
    def candidates(*texts):
        return [{"mid": f"click:o{i}", "describe": f'Click the option "{t}"'} for i, t in enumerate(texts, start=1)] + [
            {"mid": "give_up", "describe": "Stop"}]

    def step(degree, *texts):
        req = StepRequest(fid="e", question="Which best describes your education?", route="slot", slot=SLOT,
                          candidates=candidates(*texts))
        return autofill_step.step(req, facts_of((degree, "2024")), db_session, None)

    got = step("Master's", *THRESHOLDS)
    assert (got.mid, got.reason) == ("click:o1", "matched")
    got = step("Associate", *THRESHOLDS)
    assert got.mid is None and got.reason == "abstained"


def test_a_step_over_a_partial_list_never_settles_for_the_nearest_level(db_session):
    texts = ["High school", "Bachelor's degree"]
    cands = [{"mid": f"click:o{i}", "describe": f'Click the option "{t}"'} for i, t in enumerate(texts, start=1)]
    req = StepRequest(fid="e", question="Highest level of education", route="slot", slot=SLOT, candidates=cands)
    assert autofill_step.step(req, facts_of(("Master's", "2024")), db_session, None).mid is None
    got = autofill_step.step(req.model_copy(update={"complete": True}), facts_of(("Master's", "2024")), db_session, None)
    assert (got.mid, got.reason) == ("click:o2", "closest")


# ---------- the reasoning step may point a choice at it

def test_the_reasoning_step_may_answer_a_choice_from_the_education_level():
    facts = facts_of(("Master's", "2024"))
    assert SLOT in autofill_reason.present_slots(facts) and not autofill_catalog.PROTECTED_SLOT.match(SLOT)
    request = ReasonRequest.model_validate({
        "why": "open_questions", "round": 1,
        "fields": [{"fid": "f1", "question": "Which best describes your education?", "shape": "select",
                    "required": True, "options": [{"ref": "o1", "text": "Bachelor's degree or higher"}],
                    "option_count": 1}]})
    reply = REPLY.validate_python({"note": "x", "actions": [{"type": "answer_from", "fid": "f1", "slot": SLOT}]})
    assert autofill_reason.check(reply, request, present=set(autofill_reason.present_slots(facts)),
                                 level="history")[1] == []


# ---------- review: negations, degrees in progress, degree-type and field-tied lists, several levels, dates, B.E./M.Tech

def chosen(value, options, complete=True):
    got = autofill_education.decide(value, [(f"o{i}", t) for i, t in enumerate(options)], complete=complete)
    return dict((f"o{i}", t) for i, t in enumerate(options)).get(got.oid)


B, M = "Bachelor's degree", "Master's degree"


@pytest.mark.parametrize(("value", "options", "expected"), [
    (B, ["I do not have a Bachelor's degree", "I have a Bachelor's degree or higher"], "I have a Bachelor's degree or higher"),
    (B, ["Without a bachelor's degree", "Bachelor's degree"], "Bachelor's degree"),
    (M, ["Do not have a master's degree", "Have a master's degree"], "Have a master's degree"),
    (M, ["No Bachelor's degree", "Bachelor's degree"], "Bachelor's degree"),
    (M, ["I don't have a degree", "Haven't finished a Bachelor's", "Master's degree"], "Master's degree"),
    (M, ["Never completed a Bachelor's degree", "Bachelor's degree or higher"], "Bachelor's degree or higher")])
def test_an_option_that_denies_a_level_is_never_picked(value, options, expected):
    assert chosen(value, options) == expected


@pytest.mark.parametrize("option", ["Without a bachelor's degree", "Do not have a master's degree", "No Bachelor's degree",
                                    "I do not have a Bachelor's degree"])
def test_a_denial_alone_is_not_a_level_to_claim(option):
    assert chosen(M, [option, "None of the above"]) is None


@pytest.mark.parametrize("degree", ["PhD candidate", "Bachelor's (in progress)", "Pursuing Master's", "Master's student",
                                    "MBA, expected 2027", "Currently enrolled in a Master's"])
def test_a_degree_still_in_progress_is_not_completed(degree):
    assert SLOT not in facts_of((degree, "2020"))
    kept = facts_of((degree, "2020"), ("Bachelor's", "2018"))
    assert kept[SLOT].value == "Bachelor's degree"


@pytest.mark.parametrize("options", [
    ["BA", "BS", "MA", "MS", "MBA", "PhD"],
    ["Bachelor of Arts", "Bachelor of Science", "Master of Arts", "Master of Science", "MBA"],
    ["Master's degree in Computer Science or related field", "None of the above"],
    ["Bachelor's degree or above in a STEM field", "Other"],
    ["Bachelor's degree in Computer Science", "Bachelor's degree in Engineering", "Master's degree in Business"],
    ["Master's degree (MS, MA, MBA) or higher", "Bachelor's degree"],
    ["Master's degree", "Master's degree or higher", "Bachelor's degree"]])
def test_a_degree_type_or_field_tied_list_is_not_claimed(options):
    assert chosen(M, options) is None


def test_a_field_tied_option_above_the_winner_still_stops_the_answer():
    """The list is about fields, so the lower plain option is not a fair answer for a Master's holder."""
    assert chosen(M, ["Bachelor's degree", "Master of Science"]) is None


def test_an_option_naming_a_level_and_plain_filler_words_is_still_a_level():
    options = ["High school diploma/GED", "Associate's or higher", "Bachelor's degree or higher",
               "Master's degree or equivalent experience"]
    assert chosen(M, options) == "Master's degree or equivalent experience"
    assert chosen("Doctorate", ["Doctorate", "Master's degree"]) == "Doctorate"


def test_an_option_naming_two_levels_is_met_at_the_lowest_it_names():
    assert chosen(M, ["Master's or PhD", "Bachelor's degree or higher"]) == "Master's or PhD"
    assert chosen(B, ["Master's or PhD", "Bachelor's degree or higher"]) == "Bachelor's degree or higher"
    assert chosen("Doctorate", ["Associate degree", "Master's or PhD"]) == "Master's or PhD"


@pytest.mark.parametrize("text", ["Undergraduate student", "Graduate student", "Current student", "Less than a Bachelor's",
                                  "Up to an associate degree"])
def test_a_student_or_a_ceiling_is_never_a_completed_level(text):
    assert chosen(M, [text, "None of the above"]) is None


def test_a_degree_ending_later_this_year_is_not_completed_yet():
    assert SLOT not in autofill_catalog.build({"education": [{"degree": "Master's", "end_date": "2026-12"}]}, [], [], today=TODAY)
    assert SLOT not in autofill_catalog.build({"education": [{"degree": "Master's", "end_date": "Dec 2026"}]}, [], [], today=TODAY)
    done = autofill_catalog.build({"education": [{"degree": "Master's", "end_date": "2026-05"}]}, [], [], today=TODAY)
    assert done[SLOT].value == "Master's degree"
    # A year alone cannot say: this year counts.
    assert autofill_catalog.build({"education": [{"degree": "Master's", "end_year": "2026"}]}, [], [], today=TODAY)[SLOT]


@pytest.mark.parametrize("end", ["Present", "Current", "Ongoing"])
def test_a_degree_that_has_no_end_yet_is_not_completed(end):
    assert SLOT not in autofill_catalog.build({"education": [{"degree": "Master's", "end_date": end}]}, [], [], today=TODAY)


@pytest.mark.parametrize(("degree", "value"), [
    ("B.E.", "Bachelor's degree"), ("BE Computer Science", "Bachelor's degree"), ("B.Tech", "Bachelor's degree"),
    ("BTech", "Bachelor's degree"), ("M.Tech", "Master's degree"), ("MTech in VLSI", "Master's degree"),
    ("M.E.", "Master's degree"), ("ME Structural Engineering", "Master's degree")])
def test_engineering_degree_abbreviations_are_read(degree, value):
    assert facts_of((degree, "2020"))[SLOT].value == value


@pytest.mark.parametrize("degree", ["be", "To be decided", "Me", "Certificate of Merit"])
def test_ordinary_words_are_no_degree(degree):
    assert SLOT not in facts_of((degree, "2020"))
