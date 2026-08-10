"""Standing eligibility answers, and the labels they have to survive.

Every question here was taken from `autofill_field_observations` — the labels
below are the real ones the engine has met and reported `no_rule` for, across
six hosts. "Have you previously been employed by us" is the most common
unanswered question in the whole corpus and is worded differently on every
single host, which is why it is a structured field with one rule rather than a
custom Q&A preset the user would have to write once per employer.

Unset is the default and stays blank: an eligibility answer is a knockout
answer on a real application, so the engine reports `missing_source` and leaves
the control alone rather than guessing.
"""

import pytest

from tests.extension_harness import outcome_for, run_profile_fill


_ELIGIBLE = {"eligibility": {
    "over_18": "yes",
    "previously_employed_here": "no",
    "non_compete": "no",
}}


# Verbatim from the corpus, lower-cased the way labelFor() delivers them.
_PREVIOUSLY_EMPLOYED_LABELS = [
    # Verbatim prefixes: observe() caps a label at 160 chars, so the full
    # corpus string cannot be matched back to the field that produced it.
    "yes | candidateispreviousworker | k2vow | have you previously been employed "
    "by waystar?",
    "yes | candidateispreviousworker | uxz84 | have you worked with us before, "
    "including any company acquired by bmo financial group?*",
    "* are you currently or have you previously been employed by doosan or one "
    "of its subsidiaries?",
    "yes | 42262[] | 42262_663244 | do you currently work for pwc "
    "(pricewaterhousecoopers)?",
]


@pytest.mark.parametrize("label", _PREVIOUSLY_EMPLOYED_LABELS)
def test_every_wording_of_previously_employed_here_is_one_question(tmp_path, label):
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "radio", "options": ["Yes", "No"]}],
        profile=_ELIGIBLE,
    )
    assert outcome_for(result, label) == "filled"
    assert result["values"][label] == "No"


def test_the_work_history_tick_box_is_not_that_question(tmp_path):
    """The one that would be expensive to get wrong.

    "I currently work here" is a fact about a PAST JOB, derived per block from
    the resume's own end date. The previously-employed rule needs an employment
    word, a time marker AND a question addressed to the applicant, and this
    label has only the first two — so it cannot be captured, and the box keeps
    the answer its own rule derives.
    """
    label = "i currently work here | currentlywork here | workexperience-6--currentlyworkhere"
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "checkbox"}],
        profile=_ELIGIBLE,
        employment=[{"employer": "Acme", "title": "Analyst",
                     "start_date": "Jun 2006", "end_date": None, "current": True}],
    )
    assert result["observations"][0]["rule_id"] == "emp-current"
    assert result["checked"][label] is True, "the derived answer was displaced"


def test_the_age_question_fills_from_the_standing_answer(tmp_path):
    label = ("select one required | primaryquestionnaire--4eda80f45a37 | "
             "are you 18 years of age or older?*")
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "listboxButton",
                 "listbox": ["Select One", "Yes", "No"]}],
        profile=_ELIGIBLE,
    )
    assert outcome_for(result, label) == "filled"
    assert result["values"][label] == "Yes"


@pytest.mark.parametrize("label", [
    "18 months of relevant experience required | q18",
    "year | education-131--lastyearattended-datesectionyear-input | to (actual or expected)",
])
def test_an_18_that_is_not_an_age_is_left_alone(tmp_path, label):
    """`\\b18\\b` on its own matches an experience requirement and a date
    fragment. The age noun beside the number is what keeps this rule off every
    other field with an 18 in it."""
    result = run_profile_fill(
        tmp_path, fields=[{"label": label, "kind": "text"}], profile=_ELIGIBLE)
    assert outcome_for(result, label) != "filled" or \
        result["observations"][0]["rule_id"] != "over-18"


@pytest.mark.parametrize("label", [
    "select one required | primaryquestionnaire--4eda | i am subject to a "
    "non-compete or other restrictive employment agreement.",
    "are you subject to any restrictive covenants (e.g., non-compete or "
    "non-solicitation agreements)?* | question_6548138009",
])
def test_the_non_compete_family_is_one_rule(tmp_path, label):
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "listboxButton",
                 "listbox": ["Select One", "Yes", "No"]}],
        profile=_ELIGIBLE,
    )
    assert outcome_for(result, label) == "filled"
    assert result["values"][label] == "No"


def test_an_unset_eligibility_answer_is_reported_not_guessed(tmp_path):
    """The behaviour that was chosen deliberately over an AI fallback: these are
    legal-eligibility answers, and one the user did not give is one nobody may
    supply on their behalf."""
    label = ("select one required | primaryquestionnaire--x | "
             "are you 18 years of age or older?*")
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "listboxButton",
                 "listbox": ["Select One", "Yes", "No"]}],
        profile={"eligibility": {}},
    )
    assert outcome_for(result, label) == "missing_source"
    assert result["values"][label] == "Select One"


def test_a_salary_question_with_words_between_desired_and_salary(tmp_path):
    """From the corpus: "what is your desired annual base salary or hourly
    rate?" reported no_rule, because the pattern needed `desired` adjacent to
    `salary` and "annual base" sits between them."""
    label = "what is your desired annual base salary or hourly rate? | q21 | q21"
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "text"}],
        profile={"preferences": {"desired_salary": "$80,000"}},
    )
    assert outcome_for(result, label) == "filled"
    assert result["values"][label] == "$80,000"


def test_the_sponsorship_question_is_not_taken_by_the_new_neighbours(tmp_path):
    """The live label carries BOTH nouns: "will you now or in the future require
    sponsorship for employment work authorization to work in the united
    states". Order decides it — sponsorship-future sits above work-auth — and
    "now or" is deliberately not a `now` phrase, so sponsorship-now declines it
    too. Pinned because three rules were just inserted above all of them.
    """
    label = ("no required | primaryquestionnaire--4eda | will you now or in the "
             "future require sponsorship for employment work authorization to "
             "work in the united states?*")
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "listboxButton",
                 "listbox": ["Select One", "Yes", "No"]}],
        profile={**_ELIGIBLE, "work_auth": {
            "authorized_now": True, "sponsorship_now": False, "sponsorship_future": False}},
    )
    assert result["observations"][0]["rule_id"] == "sponsorship-future"
    assert result["values"][label] == "No", "answered with the work-auth yes"
