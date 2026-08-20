"""EEO autofill is opt-in AND requires a control the user can actually see.

Standing consent is backend-owned (`eeo_consent.enabled` from
`/api/autofill/context`). The panel's Fill stage maps that flag onto the
`eeoEnabled` argument exercised here, and it holds no control that could set it
— `chrome.storage.sync.eeoAutofillEnabled` is legacy and is not the source of
truth for any fill decision.

Protected-class disclosures are the one place where filling a hidden field is a
harm rather than a convenience, so the visibility bar is higher here than for
ordinary fields: every CSS trick a select2-style widget uses to hide the native
control has to count as hidden.

The second half of this module covers race/ethnicity, which is the one answer a
person can hold more than one of. US forms ask it as "select all that apply" —
one checkbox per category — so it is also the one place a checkbox may be
ticked at all. Every test there is guarding the same rule: a wrong answer to a
protected-class question is worse than a blank one, so the value must come from
an exact category the user supplied, or nothing is written.
"""

import re

from tests.extension_harness import (
    CONTENT,
    FORM_MODULE_SOURCES,
    js_code,
    outcome_for,
    outcome_pairs,
    run_node,
    run_profile_fill,
)


_DRIVER_JS = r"""
const { fillFormFromProfile } = loadModules();

const profile = {
  personal: { country: "United States" },
  eeo: {
    veteran_status: "not_veteran",
    disability_status: "no",
    hispanic_latino: "no",
    gender: "female",
    race_ethnicity: "Asian",
  },
};
const eeoCases = [
  ["Veteran status", "not-veteran", "I am not a protected veteran"],
  ["Disability status", "no", "No, I don't have a disability"],
  ["Are you Hispanic or Latino?", "no", "No"],
  ["Gender", "female", "Female"],
  ["Race or ethnicity", "asian", "Asian"],
];

async function run(
  label,
  visible,
  eeoEnabled,
  selectOptions,
  activeProfile = profile,
  visibilityMode = "normal",
) {
  const input = new HTMLSelectElement({
    label,
    visible,
    options: selectOptions,
    visibilityMode,
  });
  setElements([input]);
  const result = await fillFormFromProfile(activeProfile, [], eeoEnabled);
  return { value: input.value, result };
}

main(async () => {
  const genderOptions = [{ value: "female", textContent: "Female" }];
  const off = await run("Gender", true, undefined, genderOptions);
  const visibleEeo = [];
  const hiddenEeo = [];
  for (const [label, value, textContent] of eeoCases) {
    const selectOptions = [{ value, textContent }];
    visibleEeo.push(await run(label, true, true, selectOptions));
    hiddenEeo.push(await run(label, false, true, selectOptions));
  }
  const styledHiddenEeo = [];
  for (const visibilityMode of [
    "clipped",
    "tinyBounds",
    "visibilityHidden",
    "transparent",
    "clipPath",
    "ancestorHidden",
  ]) {
    for (const [label, value, textContent] of eeoCases) {
      styledHiddenEeo.push({
        visibilityMode,
        scenario: await run(
          label,
          true,
          true,
          [{ value, textContent }],
          profile,
          visibilityMode,
        ),
      });
    }
  }
  const hiddenCountry = await run(
    "Country",
    false,
    true,
    [{ value: "us", textContent: "United States" }],
  );
  const customOnlyProfile = {
    personal: { country: "United States" },
    eeo: {},
    custom: [{ question: "gender", answer: "female" }],
  };
  const customOff = await run(
    "Gender",
    true,
    false,
    genderOptions,
    customOnlyProfile,
  );
  const customHidden = await run(
    "Gender",
    false,
    true,
    genderOptions,
    customOnlyProfile,
  );
  emit({
    off,
    visibleEeo,
    hiddenEeo,
    styledHiddenEeo,
    hiddenCountry,
    customOff,
    customHidden,
  });
});
"""


def test_eeo_fill_requires_opt_in_and_visible_control(tmp_path):
    scenarios = run_node(
        _DRIVER_JS, {}, tmp_path,
        source="\n".join(path.read_text(encoding="utf-8")
                         for path in FORM_MODULE_SOURCES),
    )

    assert scenarios["off"]["value"] == ""
    assert scenarios["off"]["result"]["filled"] == []

    assert [case["result"]["eeoFilled"][0]["field"] for case in scenarios["visibleEeo"]] == [
        "veteran",
        "disability",
        "hispanic-latino",
        "gender",
        "race-ethnicity",
    ]
    assert all(case["value"] for case in scenarios["visibleEeo"])

    for case in scenarios["hiddenEeo"]:
        assert case["value"] == ""
        assert case["result"]["eeoFilled"] == []
        assert any(
            observation["rule_id"] is not None
            and observation["outcome"] == "hidden"
            for observation in case["result"]["observations"]
        )

    for case in scenarios["styledHiddenEeo"]:
        assert case["scenario"]["value"] == "", case["visibilityMode"]
        assert case["scenario"]["result"]["eeoFilled"] == []

    assert scenarios["customOff"]["value"] == ""
    assert scenarios["customOff"]["result"]["filled"] == []
    assert scenarios["customHidden"]["value"] == ""
    assert scenarios["customHidden"]["result"]["filled"] == []

    assert scenarios["hiddenCountry"]["value"] == "us"


# A "select all that apply" race block, labelled the way labelFor() actually
# sees it. labelFor joins up to eight sources with " | ", so the box's own text
# is one SEGMENT of the label and never the whole of it — the live failing
# signature is "american indian or alaska native | dq-option-7", and a form
# built with a <fieldset> adds the legend on the end. A writer that compares an
# option name to the joined label matches nothing on any real page.
_RACE_LEGEND = "Race/Ethnicity (select all that apply)"


def _race_box(option: str, index: int, **flags) -> dict:
    return {
        "label": f"{option} | dq-option-{index} | {_RACE_LEGEND}",
        "kind": "checkbox",
        **flags,
    }


def _ticked(result: dict) -> set[str]:
    return {label for label, on in result["checked"].items() if on}


def test_multi_race_ticks_each_matching_option_and_only_those(tmp_path):
    """One person, several categories, one box each — the shape a scalar
    `race_ethnicity` could not express and the checkbox writer exists for."""
    boxes = [
        _race_box("American Indian or Alaska Native", 7),
        _race_box("Asian", 3),
        _race_box("White", 6),
    ]
    result = run_profile_fill(
        tmp_path,
        fields=boxes,
        eeo_enabled=True,
        profile={"eeo": {
            "race_ethnicity": ["American Indian or Alaska Native", "Asian"],
        }},
    )

    assert _ticked(result) == {boxes[0]["label"], boxes[1]["label"]}
    # The disclosure is reported per category, in the user's own words.
    assert [entry["value"] for entry in result["eeoFilled"]] == [
        "American Indian or Alaska Native", "Asian",
    ]
    assert {entry["field"] for entry in result["eeoFilled"]} == {"race-ethnicity"}
    assert outcome_for(result, boxes[0]["label"]) == "filled"
    assert outcome_for(result, boxes[2]["label"]) == "skipped_checkbox"


def test_a_legacy_scalar_race_still_ticks_its_option(tmp_path):
    """The extension updates out-of-band, so a profile written before the list
    shape existed has to keep working forever."""
    boxes = [_race_box("Asian", 3), _race_box("White", 6)]
    result = run_profile_fill(
        tmp_path,
        fields=boxes,
        eeo_enabled=True,
        profile={"eeo": {"race_ethnicity": "Asian"}},
    )

    assert _ticked(result) == {boxes[0]["label"]}


def test_only_an_exactly_equal_option_name_is_ticked(tmp_path):
    """Never fuzzy. "Asian Indian" is a different category from "Asian", and
    "Asian (Not Hispanic or Latino)" additionally asserts something about
    hispanic_latino that the user did not say here — matching either would put
    a claim on a protected-class question that the profile does not support.
    Both stay blank, which is the correct failure."""
    boxes = [
        _race_box("Asian Indian", 4),
        _race_box("Asian (Not Hispanic or Latino)", 5),
    ]
    result = run_profile_fill(
        tmp_path,
        fields=boxes,
        eeo_enabled=True,
        profile={"eeo": {"race_ethnicity": "Asian"}},
    )

    assert _ticked(result) == set()
    assert result["eeoFilled"] == []


def test_an_already_ticked_option_is_never_cleared(tmp_path):
    """click() TOGGLES. A box the page already carries is the user's own answer
    — a saved application, or their own click before pressing Fill — and
    clicking it would erase a disclosure and then report it as filled."""
    box = _race_box("Asian", 3, checked=True)
    result = run_profile_fill(
        tmp_path,
        fields=[box],
        eeo_enabled=True,
        profile={"eeo": {"race_ethnicity": ["Asian"]}},
    )

    assert _ticked(result) == {box["label"]}
    assert result["events"][box["label"]] == []
    # We did not write it, so we do not claim it.
    assert result["eeoFilled"] == []


def test_an_option_with_no_question_text_in_its_label_is_still_untouched(tmp_path):
    """KNOWN GAP, pinned deliberately. The live failing signature carries the
    option text and an opaque id and nothing else — that page states the
    question somewhere labelFor() cannot reach, so nothing in the label says
    "race" and the field is not recognised as EEO at all.

    It stays `no_rule` until a writer can see the group a control belongs to.
    Recognising it from the category name alone is NOT the fix: the short names
    ("Asian", "White") are not EEO-specific, and half-recognising a group would
    tick some of a person's categories and miss the rest — which on "select all
    that apply" is a false answer, not an incomplete one."""
    box = {
        "label": "American Indian or Alaska Native | dq-option-7",
        "kind": "checkbox",
    }
    result = run_profile_fill(
        tmp_path,
        fields=[box],
        eeo_enabled=True,
        profile={"eeo": {"race_ethnicity": ["American Indian or Alaska Native"]}},
    )

    assert _ticked(result) == set()
    assert outcome_for(result, box["label"]) == "no_rule"


def test_an_option_whose_click_is_cancelled_claims_no_disclosure(tmp_path):
    """A framework that calls preventDefault() on the click leaves the box
    exactly as it was. Dispatching a click is not the same as ticking a box,
    and the EEO list may only ever report the second."""
    box = _race_box("Asian", 3, clickCancelled=True)
    result = run_profile_fill(
        tmp_path,
        fields=[box],
        eeo_enabled=True,
        profile={"eeo": {"race_ethnicity": ["Asian"]}},
    )

    assert _ticked(result) == set()
    assert outcome_for(result, box["label"]) == "not_stuck"
    assert result["eeoFilled"] == []
    assert "check the box" in result["filled"][0]["note"]


def test_race_options_are_untouched_without_the_opt_in(tmp_path):
    box = _race_box("Asian", 3)
    result = run_profile_fill(
        tmp_path,
        fields=[box],
        profile={"eeo": {"race_ethnicity": ["Asian"]}},
    )

    assert _ticked(result) == set()
    assert outcome_for(result, box["label"]) == "eeo_disabled"


def test_ticking_stays_narrow_to_eeo_options(tmp_path):
    """The never-guess-a-checkbox default still holds everywhere else — for an
    ordinary question, and for an EEO question whose answer is not a list of
    form options to match against."""
    relocate = {"label": "Willing to relocate?", "kind": "checkbox"}
    gender = {"label": "Female | gender", "kind": "checkbox"}
    race = _race_box("Asian", 3)
    result = run_profile_fill(
        tmp_path,
        fields=[relocate, gender, race],
        eeo_enabled=True,
        profile={
            "eeo": {"gender": "female", "race_ethnicity": ["Asian"]},
            "preferences": {"willing_to_relocate": "yes"},
        },
    )

    assert _ticked(result) == {race["label"]}
    assert outcome_for(result, relocate["label"]) == "skipped_checkbox"
    assert outcome_for(result, gender["label"]) == "skipped_checkbox"


def test_the_combined_question_answers_hispanic_from_its_own_field(tmp_path):
    """OMB's 2024 revision of SPD 15 folds Hispanic or Latino into the race
    question as one more "select all that apply" category. The same profile
    field answers both shapes: the yes/no of the legacy question, and this
    option on a combined list."""
    hispanic, white, asian = (
        _race_box("Hispanic or Latino", 1),
        _race_box("White", 6),
        _race_box("Asian", 3),
    )
    fields = [hispanic, white, asian]
    profile = {"eeo": {"hispanic_latino": "yes", "race_ethnicity": ["White"]}}

    yes = run_profile_fill(
        tmp_path, fields=fields, eeo_enabled=True, profile=profile
    )
    assert _ticked(yes) == {hispanic["label"], white["label"]}
    assert {entry["field"] for entry in yes["eeoFilled"]} == {
        "hispanic-latino", "race-ethnicity",
    }

    no = run_profile_fill(
        tmp_path,
        fields=fields,
        eeo_enabled=True,
        profile={"eeo": {"hispanic_latino": "no", "race_ethnicity": ["White"]}},
    )
    assert _ticked(no) == {white["label"]}


def test_neither_half_of_the_race_question_is_inferred_from_the_other(tmp_path):
    """HR-4. A supplied race says nothing about Hispanic/Latino, and a Hispanic
    yes says nothing about race — an unanswered half is reported and left
    blank, in both directions."""
    hispanic, white = _race_box("Hispanic or Latino", 1), _race_box("White", 6)

    # Boolean on purpose: a hand-edited profile stores yes/no as one, and an
    # unrecognised `true` would leave a real answer unticked.
    only_hispanic = run_profile_fill(
        tmp_path,
        fields=[hispanic, white],
        eeo_enabled=True,
        profile={"eeo": {"hispanic_latino": True}},
    )
    assert _ticked(only_hispanic) == {hispanic["label"]}
    assert outcome_for(only_hispanic, white["label"]) == "missing_source"

    only_race = run_profile_fill(
        tmp_path,
        fields=[hispanic, white],
        eeo_enabled=True,
        profile={"eeo": {"race_ethnicity": ["White"]}},
    )
    assert _ticked(only_race) == {white["label"]}
    assert [entry["field"] for entry in only_race["eeoFilled"]] == ["race-ethnicity"]


def test_a_multi_race_answer_is_never_squeezed_into_a_single_select(tmp_path):
    """A single-value control cannot carry a multi-category answer: picking one
    of them states ONE race for a person who supplied several, which on a
    protected-class question is a false statement, not a partial one."""
    field = {
        "label": "Race/Ethnicity",
        "kind": "select",
        "options": [
            {"value": "asian", "textContent": "Asian"},
            {"value": "white", "textContent": "White"},
            {"value": "two", "textContent": "Two or More Races"},
        ],
    }
    result = run_profile_fill(
        tmp_path,
        fields=[field],
        eeo_enabled=True,
        profile={"eeo": {"race_ethnicity": ["Asian", "White"]}},
    )

    assert result["values"]["Race/Ethnicity"] == ""
    assert result["eeoFilled"] == []
    assert outcome_for(result, "Race/Ethnicity") == "skip_rule"

    # A blank entry is not a second category. The settings page writes this
    # field as free text today, so the list it eventually splits into can carry
    # one — and a blank must not cost the user the answer they did give.
    one_real = run_profile_fill(
        tmp_path,
        fields=[field],
        eeo_enabled=True,
        profile={"eeo": {"race_ethnicity": ["Asian", ""]}},
    )
    assert one_real["values"]["Race/Ethnicity"] == "asian"


# ---------- an answer already on the page is the user's own ----------
#
# The checkbox branch has always known this: click() toggles, so a ticked box
# has to be left alone. The reason it gives is not about toggling — "a box the
# page already carries ticked is the user's own answer, a saved application or
# their own click before pressing Fill" — and it applies to every control
# shape. A select and a radio group carry the same answer just as durably, and
# overwriting one replaces a disclosure the user made with one they did not,
# then prints it back to them under "EEO fields filled".

_GENDER_SELECT_OPTIONS = [
    {"value": "f", "textContent": "Female"},
    {"value": "m", "textContent": "Male"},
    {"value": "decline", "textContent": "Decline to self-identify"},
]
# The radio cases use the ethnicity question rather than gender, because that
# is the group shape the live corpus actually carries — and because a gender
# radio group is unreachable anyway: OPTION_WORDS.female is /^female$/i, and
# labelFor() gives every radio button a COMPOSITE label ("female | gender"), so
# the anchored pattern can only ever match a select's bare option text. Using
# gender here would make these tests pass without exercising anything.
_ETHNICITY_LABEL = "Are you Hispanic or Latino?"
_ETHNICITY_OPTIONS = ["Yes", "No", "I prefer not to answer"]


def test_an_already_answered_eeo_select_is_never_overwritten(tmp_path):
    """A resumed application where the user chose "Decline to self-identify".
    Rewriting it to "Female" states a protected characteristic they declined to
    state, and reports the substitution as a completed disclosure."""
    field = {
        "label": "Gender",
        "kind": "select",
        "options": _GENDER_SELECT_OPTIONS,
        "value": "decline",
    }
    result = run_profile_fill(
        tmp_path,
        fields=[field],
        eeo_enabled=True,
        profile={"eeo": {"gender": "female"}},
    )

    assert result["values"]["Gender"] == "decline"
    assert result["eeoFilled"] == []
    assert result["filled"] == []
    # Nothing was written, so nothing is claimed — including in telemetry,
    # which follows the select branch's already-set convention of emitting no
    # outcome at all.
    assert outcome_pairs(result) == []


def test_an_already_answered_eeo_radio_group_is_never_overwritten(tmp_path):
    """Same decline, rendered as buttons. The radio branch never looked at
    `checked` on any member of the group, so it clicked over the top of one."""
    field = {
        "label": _ETHNICITY_LABEL,
        "kind": "radio",
        "options": _ETHNICITY_OPTIONS,
        "checkedOption": "I prefer not to answer",
    }
    result = run_profile_fill(
        tmp_path,
        fields=[field],
        eeo_enabled=True,
        profile={"eeo": {"hispanic_latino": "no"}},
    )

    assert result["values"][_ETHNICITY_LABEL] == "I prefer not to answer"
    assert result["eeoFilled"] == []
    assert result["filled"] == []
    assert result["events"][_ETHNICITY_LABEL] == []
    assert outcome_pairs(result) == []


def test_an_eeo_control_already_holding_our_own_answer_is_still_not_claimed(
    tmp_path,
):
    """The user answered "Female" themselves. We did not write it, so we do not
    list it under "EEO fields filled" — the same reason the ticked checkbox is
    left out of that list."""
    select = run_profile_fill(
        tmp_path,
        fields=[{
            "label": "Gender",
            "kind": "select",
            "options": _GENDER_SELECT_OPTIONS,
            "value": "f",
        }],
        eeo_enabled=True,
        profile={"eeo": {"gender": "female"}},
    )
    assert select["values"]["Gender"] == "f"
    assert select["eeoFilled"] == []

    radio = run_profile_fill(
        tmp_path,
        fields=[{
            "label": _ETHNICITY_LABEL,
            "kind": "radio",
            "options": _ETHNICITY_OPTIONS,
            "checkedOption": "No",
        }],
        eeo_enabled=True,
        profile={"eeo": {"hispanic_latino": "no"}},
    )
    assert radio["values"][_ETHNICITY_LABEL] == "No"
    assert radio["eeoFilled"] == []
    assert radio["events"][_ETHNICITY_LABEL] == []


def test_an_already_answered_eeo_combobox_is_never_touched(tmp_path):
    """The fourth control shape, and the one where the protection used to be an
    accident.

    The select and radio branches test `isEeoField` explicitly. This branch had
    only the blanket `if (input.value) continue` that every combobox shares —
    and SYSTEM.md §11 item 8c proposes identity-combobox reconciliation, which
    is precisely the change that relaxes that line so a disagreeing value CAN be
    overwritten. Measured by deleting it: the answered EEO control was focused,
    mouse-sequenced, keyed and blurred, and reported under `filled`. Nothing
    else stopped it.

    So this test is the tripwire for that future change, and it holds whichever
    way the branch is rewritten — what it pins is that the control is not
    driven, not which line does the stopping.
    """
    field = {
        "label": "Gender",
        "kind": "combobox",
        "value": "Decline to self-identify",
    }
    result = run_profile_fill(
        tmp_path,
        fields=[field],
        eeo_enabled=True,
        profile={"eeo": {"gender": "female"}},
    )

    assert result["values"]["Gender"] == "Decline to self-identify"
    # No focus, no mouse sequence, no keystroke, no blur. A combobox this
    # writer merely TOUCHES is one it may have emptied: fillCombobox blurs on
    # the failure path, and react-select and select2 clear on blur.
    assert result["events"]["Gender"] == []
    assert result["filled"] == []
    assert result["eeoFilled"] == []
    assert outcome_pairs(result) == []

    # …and the guard is "already answered", not "never write". An EMPTY EEO
    # combobox is still engaged — without this half, `if (isEeoField) continue`
    # would pass everything above while quietly dropping the shape from the
    # writer altogether.
    empty = run_profile_fill(
        tmp_path,
        fields=[{"label": "Gender", "kind": "combobox"}],
        eeo_enabled=True,
        profile={"eeo": {"gender": "female"}},
    )
    assert "focus:preventScroll" in empty["events"]["Gender"]
    assert outcome_pairs(empty) == [("Gender", "combobox_snap_failed")]


def test_an_eeo_combobox_is_untouched_without_the_opt_in(tmp_path):
    """EEO autofill is off by default, and "off" has to mean the control is
    never driven — not merely that the result goes unreported.

    Reported as `eeo_disabled` rather than silently skipped, which is the same
    contract the other three shapes follow: the user is told the field was
    recognised and deliberately left alone.
    """
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": "Gender", "kind": "combobox"}],
        eeo_enabled=False,
        profile={"eeo": {"gender": "female"}},
    )

    assert result["values"]["Gender"] == ""
    assert result["events"]["Gender"] == []
    assert result["filled"] == []
    assert result["eeoFilled"] == []
    assert outcome_pairs(result) == [("Gender", "eeo_disabled")]


def test_an_unanswered_eeo_control_is_still_filled(tmp_path):
    """The guard is "already answered", not "never write" — an empty select and
    an untouched radio group are exactly what the EEO writer is for."""
    select = run_profile_fill(
        tmp_path,
        fields=[{
            "label": "Gender", "kind": "select", "options": _GENDER_SELECT_OPTIONS,
        }],
        eeo_enabled=True,
        profile={"eeo": {"gender": "female"}},
    )
    assert select["values"]["Gender"] == "f"
    assert [entry["value"] for entry in select["eeoFilled"]] == ["Female"]

    radio = run_profile_fill(
        tmp_path,
        fields=[{
            "label": _ETHNICITY_LABEL, "kind": "radio",
            "options": _ETHNICITY_OPTIONS,
        }],
        eeo_enabled=True,
        profile={"eeo": {"hispanic_latino": "no"}},
    )
    assert radio["values"][_ETHNICITY_LABEL] == "No"
    assert {entry["field"] for entry in radio["eeoFilled"]} == {"hispanic-latino"}


# ---------- exact, or nothing ----------
#
# The policy is already written down in the eeoOptionFor block: segments are
# compared for EQUALITY, never containment, because "Asian" is a different
# statement from "Asian Indian" and a near miss on a protected-class question
# is a false answer rather than an approximate one. It was enforced for
# checkboxes only. The scorer behind selects and comboboxes has a floor of 40
# out of 100 — it is a near-miss engine by construction — and the radio branch
# matched on a bare /Asian/i.

_RACE_LABEL = "Race/Ethnicity"
_NO_EXACT_RACE = ["Asian Indian", "Asian or Pacific Islander", "White"]


def test_a_supplied_race_is_never_widened_by_a_select(tmp_path):
    """"Asian" scores 72.5 against "Asian Indian" — a prefix match, well over
    the floor. The user meets a combined option list that does not carry their
    category, and the honest outcome is a blank they fill in themselves."""
    field = {
        "label": _RACE_LABEL,
        "kind": "select",
        "options": [
            {"value": "ai", "textContent": "Asian Indian"},
            {"value": "api", "textContent": "Asian or Pacific Islander"},
            {"value": "w", "textContent": "White"},
        ],
    }
    result = run_profile_fill(
        tmp_path,
        fields=[field],
        eeo_enabled=True,
        profile={"eeo": {"race_ethnicity": ["Asian"]}},
    )

    assert result["values"][_RACE_LABEL] == ""
    assert result["eeoFilled"] == []
    assert result["filled"] == []


def test_a_supplied_race_is_never_widened_by_a_radio_group(tmp_path):
    """Same list as buttons. `optionWordsFor` has no keyword set for a category
    name, so it falls back to a bare substring regex — /Asian/i, which matches
    "Asian Indian"."""
    field = {"label": _RACE_LABEL, "kind": "radio", "options": _NO_EXACT_RACE}
    result = run_profile_fill(
        tmp_path,
        fields=[field],
        eeo_enabled=True,
        profile={"eeo": {"race_ethnicity": ["Asian"]}},
    )

    assert result["values"][_RACE_LABEL] == ""
    assert result["eeoFilled"] == []
    assert result["events"][_RACE_LABEL] == []


def test_an_exactly_named_category_is_still_written(tmp_path):
    """The positive control for both branches: exactness is the bar, not
    silence. A list that carries the user's own category still gets it."""
    select = run_profile_fill(
        tmp_path,
        fields=[{
            "label": _RACE_LABEL,
            "kind": "select",
            "options": [
                {"value": "ai", "textContent": "Asian Indian"},
                {"value": "a", "textContent": "Asian"},
                {"value": "w", "textContent": "White"},
            ],
        }],
        eeo_enabled=True,
        profile={"eeo": {"race_ethnicity": ["Asian"]}},
    )
    assert select["values"][_RACE_LABEL] == "a"
    assert [entry["value"] for entry in select["eeoFilled"]] == ["Asian"]

    radio = run_profile_fill(
        tmp_path,
        fields=[{
            "label": _RACE_LABEL,
            "kind": "radio",
            "options": ["Asian Indian", "Asian", "White"],
        }],
        eeo_enabled=True,
        profile={"eeo": {"race_ethnicity": ["Asian"]}},
    )
    assert radio["values"][_RACE_LABEL] == "Asian"
    assert [entry["field"] for entry in radio["eeoFilled"]] == ["race-ethnicity"]


def test_a_typed_eeo_answer_still_matches_its_spelled_out_option(tmp_path):
    """Exactness applies to a CATEGORY answer, which has no keyword set behind
    it. A typed one does: OPTION_WORDS is a lookup table written per canonical
    value, and it is what lets "no" find "No, I do not have a disability and
    have not had one in the past" — the live wording on the Oracle radio group
    this reproduces. Requiring equality here would silently stop answering
    every EEO question whose options are written as sentences."""
    label = "Disability status"
    result = run_profile_fill(
        tmp_path,
        fields=[{
            "label": label,
            "kind": "radio",
            "options": [
                "Yes, I have a disability, or have had one in the past",
                "No, I do not have a disability and have not had one in the past",
                "I do not want to answer",
            ],
        }],
        eeo_enabled=True,
        profile={"eeo": {"disability_status": "no"}},
    )

    assert result["values"][label] == (
        "No, I do not have a disability and have not had one in the past"
    )
    assert [entry["field"] for entry in result["eeoFilled"]] == ["disability"]


def test_a_hispanic_yes_no_answer_is_never_written_into_a_race_select(tmp_path):
    """Found by replaying the live telemetry corpus, not constructed.

    This signature is verbatim: the label carries BOTH "race" and "hispanic or
    latino", so the hispanic-latino rule wins it and arrives holding a yes/no
    answer. The option list is the SPD-15 categories, none of which is a
    yes/no, so no keyword set matches — and the scorer then found "no" inside
    the word "not" of "I prefer not to answer" and scored it 47. The corpus
    records this signature as `filled`: a decline-to-answer the user never made
    has already been written onto a real application."""
    label = (
        "race - if you are not hispanic or latino * | 43009 | 43009 | "
        "diversity survey | race - if you are not hispanic or latino *"
    )
    field = {
        "label": label,
        "kind": "select",
        "options": [
            {"value": "1", "textContent": "American Indian or Alaska Native"},
            {"value": "2", "textContent": "Asian"},
            {"value": "3", "textContent": "Black or African American"},
            {"value": "4",
             "textContent": "Native Hawaiian or Other Pacific Islander"},
            {"value": "5", "textContent": "White"},
            {"value": "6", "textContent": "Two or More Races"},
            {"value": "7", "textContent": "I prefer not to answer"},
        ],
    }
    result = run_profile_fill(
        tmp_path,
        fields=[field],
        eeo_enabled=True,
        profile={"eeo": {"hispanic_latino": "no", "race_ethnicity": ["Asian"]}},
    )

    assert result["values"][label] == ""
    assert result["eeoFilled"] == []


# ---------- the ordinary paths keep their tolerance ----------
#
# Exactness is a rule about protected-class answers, not about option matching
# in general. `bestOption` and `scoreOption` serve most of the rule table, and
# the whole point of the scorer's tolerance is that "United States" should find
# "United States of America". Tightening that everywhere would be a different,
# larger change — and would break the deliberate correction of a wrong ATS
# prefill, which is the one place overwriting is the right answer.


def test_an_ordinary_select_still_takes_a_near_match(tmp_path):
    result = run_profile_fill(
        tmp_path,
        fields=[{
            "label": "Country",
            "kind": "select",
            "options": [
                {"value": "usmoi",
                 "textContent": "United States Minor Outlying Islands"},
                {"value": "usa", "textContent": "United States of America"},
            ],
        }],
        profile={"personal": {"country": "United States"}},
    )
    assert result["values"]["Country"] == "usa"


def test_an_ordinary_select_still_replaces_a_value_it_disagrees_with(tmp_path):
    """The `corrected` reasoning, one control over: a select the ATS prefilled
    from a resume parse is a guess, and the profile is the source of truth."""
    result = run_profile_fill(
        tmp_path,
        fields=[{
            "label": "State",
            "kind": "select",
            "value": "ny",
            "options": [
                {"value": "ny", "textContent": "New York"},
                {"value": "il", "textContent": "Illinois"},
            ],
        }],
        profile={"personal": {"state": "Illinois"}},
    )
    assert result["values"]["State"] == "il"
    assert outcome_for(result, "State") == "filled"


def test_an_ordinary_radio_group_still_takes_a_spelled_out_option(tmp_path):
    """The knockout question, worded the way ATSs actually word it. A yes/no
    rule finds it through OPTION_WORDS, and an untyped one through the
    substring regex `optionWordsFor` falls back to — neither is equality, and
    neither may be tightened by a rule about protected-class answers."""
    knockout = (
        "Will you now or in the future require sponsorship for employment "
        "visa status?"
    )
    heard = "How did you hear about us?"
    result = run_profile_fill(
        tmp_path,
        fields=[
            {"label": knockout, "kind": "radio",
             "options": ["Yes, I will require sponsorship",
                         "No, I will not require sponsorship"]},
            {"label": heard, "kind": "radio",
             "options": ["Company website (careers page)", "LinkedIn"]},
        ],
        profile={
            "work_auth": {"sponsorship_future": False},
            "preferences": {"how_heard": "Company website"},
        },
    )

    assert result["values"][knockout] == "No, I will not require sponsorship"
    assert result["values"][heard] == "Company website (careers page)"


def test_an_ordinary_radio_group_still_answers_over_a_prefill(tmp_path):
    """A knockout question the ATS pre-answered wrongly still gets the profile's
    answer. Nothing here is a protected characteristic."""
    label = "Are you legally authorized to work in the United States?"
    result = run_profile_fill(
        tmp_path,
        fields=[{
            "label": label,
            "kind": "radio",
            "options": ["Yes", "No"],
            "checkedOption": "No",
        }],
        profile={"work_auth": {"authorized_now": True}},
    )
    assert result["values"][label] == "Yes"
    assert outcome_for(result, label) == "filled"


def test_an_eeo_text_field_that_does_not_stick_claims_no_disclosure(tmp_path):
    """Same rule the snap-failed combobox follows: the EEO list is rendered as
    a bare label → value with no hedge available, so it may only ever list a
    field that actually holds the value."""
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": "Gender", "kind": "text", "reverts": True}],
        eeo_enabled=True,
        profile={"eeo": {"gender": "female"}},
    )

    assert outcome_for(result, "Gender") == "not_stuck"
    assert result["eeoFilled"] == []
    # Still surfaced in the hedged list, so the user is told to go fix it.
    assert "check the field" in result["filled"][0]["note"]


def test_a_token_rule_with_an_eeo_word_in_its_composite_label_stays_tokens(tmp_path):
    """An EEO-looking container label must not scalarize a token-valued rule."""
    label = "Skills | Gender"
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "text", "tokenizes": True}],
        profile={"eeo": {"gender": "female"}},
        skills=["Python"],
        eeo_enabled=True,
    )

    assert result["values"][label] == ""
    assert result["tokens"][label] == ["Python"]
    assert result["eeoFilled"] == []
    assert all(item["value"] != "undefined" for item in result["filled"])


# ---------- the ownership seam: who is allowed to know about EEO ------------
#
# ORPHANED BY R-C AND RE-HOMED HERE. This was pinned in
# `test_extension_widget.py`, and a reviewer proved what that cost: re-inlining
# the EEO orchestration back into `autofill.js` left the suite green at 875,
# because every behavioural test above drives `fillFormFromProfile` and does not
# care WHICH file answered.
#
# WHY THE SEAM IS WORTH A TEST OF ITS OWN, when the behaviour is already covered
# thirty times over: `content/eeo.js` is a small file that one reviewer can hold
# in their head, and `content/autofill.js` is two thousand lines of general
# field matching. Protected-class disclosures are the one place in this codebase
# where a wrong answer is a legal statement about a person, so the rule is that
# they live somewhere a human will actually re-read. A merge back into the
# engine does not change one outcome and destroys that property silently.

EEO_JS = (CONTENT / "eeo.js").read_text(encoding="utf-8")
AUTOFILL_JS_SRC = (CONTENT / "autofill.js").read_text(encoding="utf-8")

# The three doors, and there are exactly three: build the context, decide
# whether to touch a control at all, and drive one.
EEO_SEAM = ("createEeoContext", "shouldSkipEeoControl", "handleEeoControl")


def test_every_eeo_decision_is_defined_in_eeo_js_and_published_once():
    for name in EEO_SEAM:
        assert len(re.findall(rf"\bfunction {name}\(", EEO_JS)) == 1, name
        assert f"ns.{name} = {name};" in EEO_JS, name


def test_the_engine_reaches_eeo_only_through_the_namespace():
    """`autofill.js` may CALL the seam and may not re-implement it.

    EXPLOIT THIS PIN EXISTS FOR: moving `handleEeoControl`'s body back into
    `autofill.js` left the suite green. Nothing behavioural notices, because the
    answers are identical — which is exactly why the boundary needs a pin rather
    than trusting a test to feel it.
    """
    engine = js_code(AUTOFILL_JS_SRC)
    for name in EEO_SEAM:
        assert f"ns.{name}(" in engine, f"{name} is no longer reached at all"
        assert not re.search(rf"\bfunction {name}\(", engine), (
            f"{name} was re-implemented inside autofill.js")
    # One call site each: the engine asks once per fill (context), once per
    # candidate field (skip), and once per EEO field (handle). A second call
    # site for any of them is a second place that decides what EEO means.
    assert engine.count("ns.handleEeoControl(") == 1


def test_the_protected_class_vocabulary_never_leaks_into_the_engine():
    """The category names and the answer-matching patterns are eeo.js's alone.

    This is the half a re-inline would take first and the half that matters
    most: `/not a protected veteran/` unanchored is what once had the extension
    declare a user a veteran who had said they were not (deluxe.wd5,
    2026-08-08). A pattern like that living in the general field matcher is one
    nobody will re-read with the care it needs.

    Through `js_code`, because `autofill.js` legitimately QUOTES a Workday
    option label in a comment ("3-Asian (Not Hispanic or Latino) …") while
    explaining an unrelated numbering quirk. A raw scan would fail a file that
    is exactly right.
    """
    engine = js_code(AUTOFILL_JS_SRC)
    for term in ("Hispanic", "Latino", "veteran", "disability", "protected"):
        assert term.lower() not in engine.lower(), (
            f"the engine grew its own idea of {term!r} — EEO vocabulary "
            "belongs in content/eeo.js")
    # …and it really is in the file that owns it, so the assertion above cannot
    # pass by the vocabulary having been deleted everywhere.
    for term in ("veteran", "disability"):
        assert term in js_code(EEO_JS), term
