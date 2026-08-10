"""The three voluntary-disclosure defects found on a live Workday form.

All three were read off deluxe.wd5 on 2026-08-08, with the EEO opt-in ON and a
profile that answers every one of these questions. Two of them left the field
blank; the first stated the OPPOSITE of the user's answer.
"""

from tests.extension_harness import outcome_for, run_profile_fill


# Workday's real veteran list, in its real order. The order is the defect.
_VETERAN_OPTIONS = [
    "Select One",
    "I identify as one or more of the classifications of protected veterans listed above",
    "I identify as a veteran, just not a protected veteran",
    "I am not a veteran",
    "I don't wish to answer",
]

# …and its real race list, decorated the way Workday decorates it.
_RACE_OPTIONS = [
    "Select One",
    "1-Hispanic or Latino (United States of America)",
    "2-American Indian or Alaska Native (Not Hispanic or Latino) (United States of America)",
    "3-Asian (Not Hispanic or Latino) (United States of America)",
    "4-Black or African American (Not Hispanic or Latino) (United States of America)",
    "7-White (Not Hispanic or Latino) (United States of America)",
    "8-I don't wish to answer. (United States of America)",
]


def _run(tmp_path, label, options, eeo):
    return run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "listboxButton", "listbox": options}],
        profile={"eeo": eeo},
        eeo_enabled=True,
    )


def test_not_a_veteran_is_never_answered_as_a_veteran(tmp_path):
    """The worst defect in this round, and the reason the patterns are anchored.

    `/not a protected veteran/` matched "I identify as a veteran, just not a
    protected veteran", which sits ABOVE "I am not a veteran" in Workday's list
    — and the matcher takes the first option matching any pattern. A user who
    answered "I am not a veteran" had the extension declare them one, on a
    protected-class question, on a form the employer keeps.
    """
    label = "veterans status: select one required | personalinfous--veteranstatus"
    result = _run(tmp_path, label, _VETERAN_OPTIONS, {"veteran_status": "not_veteran"})

    assert result["values"][label] == "I am not a veteran"
    assert "identify as a veteran" not in result["values"][label]
    assert outcome_for(result, label) == "filled"


def test_a_veteran_still_matches_an_affirmative(tmp_path):
    """Anchoring the negatives must not cost the positive answer."""
    label = "veterans status: select one required | personalinfous--veteranstatus"
    result = _run(tmp_path, label, _VETERAN_OPTIONS, {"veteran_status": "veteran"})
    assert "identify as" in result["values"][label]


def test_declining_still_finds_the_decline_option(tmp_path):
    label = "veterans status: select one required | personalinfous--veteranstatus"
    result = _run(tmp_path, label, _VETERAN_OPTIONS, {"veteran_status": "decline"})
    assert result["values"][label] == "I don't wish to answer"


def test_a_decorated_race_option_is_matched_on_its_category(tmp_path):
    """Workday spells "Asian" as "3-Asian (Not Hispanic or Latino) (United
    States of America)". The EEO bar is exact equality, so every option was
    refused and the field stayed blank with the opt-in ON."""
    label = "race/ethnicity: select one required | personalinfous--ethnicity"
    result = _run(tmp_path, label, _RACE_OPTIONS, {"race_ethnicity": "Asian"})

    assert result["values"][label] == "3-Asian (Not Hispanic or Latino) (United States of America)"
    assert outcome_for(result, label) == "filled"
    assert result["eeoFilled"][0]["field"] == "race-ethnicity"


def test_stripping_the_decoration_does_not_loosen_the_bar(tmp_path):
    """The property the exact bar exists for, restated against the new
    canonical form: "Asian" is a different statement from "Asian Indian", and
    picking one for the other is a false disclosure, not an approximation."""
    label = "race/ethnicity: select one required | personalinfous--ethnicity"
    result = _run(
        tmp_path, label,
        ["Select One", "1-Asian Indian (Not Hispanic or Latino) (United States of America)"],
        {"race_ethnicity": "Asian"},
    )
    assert result["values"][label] == "Select One"
    assert result["eeoFilled"] == []


# Workday's disability self-ID: three checkboxes behaving like radios, each
# labelled with the whole answer and sharing an id suffix (waystar.wd1).
def _disability_boxes(checked=None):
    answers = [
        ("yes, i have a disability, or have had one in the past", "aaaa1111"),
        ("no, i do not have a disability and have not had one in the past", "bbbb2222"),
        ("i do not want to answer", "cccc3333"),
    ]
    return [
        {"label": f"{text} | {prefix}-disabilitystatus", "kind": "checkbox",
         "id": f"{prefix}-disabilitystatus", "checked": text == checked}
        for text, prefix in answers
    ]


def test_the_disability_checkbox_group_ticks_the_right_one(tmp_path):
    """These carry a `kind` and no `optionList`, so the checkbox branch found
    nothing to match and reported skipped_checkbox for all three."""
    result = run_profile_fill(
        tmp_path, fields=_disability_boxes(),
        profile={"eeo": {"disability_status": "no"}}, eeo_enabled=True)

    checked = [label for label, was in result["checked"].items() if was]
    assert len(checked) == 1, f"expected exactly one box ticked, got {checked}"
    assert checked[0].startswith("no, i do not have a disability")


def test_an_answer_already_on_the_page_is_left_alone(tmp_path):
    """A checkbox group has no browser-enforced exclusivity, so ticking ours
    beside an existing answer would submit two contradictory disclosures."""
    result = run_profile_fill(
        tmp_path,
        fields=_disability_boxes(checked="i do not want to answer"),
        profile={"eeo": {"disability_status": "no"}}, eeo_enabled=True)

    checked = [label for label, was in result["checked"].items() if was]
    assert len(checked) == 1
    assert checked[0].startswith("i do not want to answer"), "the user's answer was displaced"


def test_the_group_is_untouched_while_the_opt_in_is_off(tmp_path):
    result = run_profile_fill(
        tmp_path, fields=_disability_boxes(),
        profile={"eeo": {"disability_status": "no"}}, eeo_enabled=False)
    assert [label for label, was in result["checked"].items() if was] == []
