"""A field that already holds the answer is reported, not silently skipped.

The bug this file exists for: on a re-run of Autofill — the normal case on a
multi-step wizard, where the user fills page one, comes back, and presses the
button again — every control already holding the profile's value fell through
the fill loop with no list entry and no observation. The reconciliation strip
then printed "0 filled" over a form the extension itself had just filled, and
the card said "No matching fields found on this page", which is the most
confident wrong thing that surface can say.

The fix is a fourth result list, `already`: fields whose CURRENT value is the
one the profile would have written. It is rendered ("12 already filled"),
never sent — no telemetry observation is emitted for an already-correct field,
because the frozen outcome vocabulary in schemas/autofill_telemetry.py has no
value for it and a batch carrying an unknown outcome 422s whole
(`extra="forbid"`).

The EEO sections of test_extension_eeo_autofill.py pin the OTHER half of this
policy and are not repeated here: a protected-class control that already
carries an answer is the USER'S OWN answer, is never claimed anywhere — not in
`filled`, not in `eeoFilled`, and not in `already` (asserted below) — and emits
nothing.
"""

from tests.extension_harness import outcome_pairs, run_profile_fill

PROFILE = {
    "personal": {
        "first_name": "Jordan",
        "last_name": "Example",
        "email": "jordan@example.com",
        "phone": "5551234567",
        "city": "Chicago",
    },
}


def already_pairs(result: dict) -> list[tuple[str, str]]:
    return [(item["label"], item["value"]) for item in result["already"]]


# ---------- text inputs ----------


def test_a_text_field_already_holding_the_value_lands_in_already(tmp_path):
    """The re-run case: the field holds exactly what we would write."""
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": "City", "kind": "text", "value": "Chicago"}],
        profile=PROFILE,
    )
    assert result["filled"] == []
    assert already_pairs(result) == [("city", "Chicago")]
    # Rendered, never sent: no observation, so the frozen telemetry vocabulary
    # is not asked to carry an outcome it does not have.
    assert outcome_pairs(result) == []
    # And nothing was written: the value the user sees is untouched.
    assert result["events"]["City"] == []


def test_the_phone_field_equal_under_formatting_is_already_not_corrected(tmp_path):
    """"(555) 123-4567" IS the phone number we hold, rendered the site's way.

    Overwriting it would churn the field (the site reformats, we "correct" it
    back, forever) and report a correction that corrected nothing. Phone is
    the ONE identity rule with `formatTolerant`, because its punctuation is
    presentation — see the next two tests for the identity fields whose
    punctuation is the datum.
    """
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": "Phone", "kind": "text", "value": "(555) 123-4567"}],
        profile=PROFILE,
    )
    assert result["filled"] == []
    assert [label for label, _ in already_pairs(result)] == ["phone"]
    assert outcome_pairs(result) == []
    assert result["values"]["Phone"] == "(555) 123-4567"  # untouched


def test_identity_punctuation_is_semantic_and_still_corrected(tmp_path):
    """The review finding this branch was reshaped around: "OBrien" is a
    resume-parse guess at "O'Brien", not the same name rendered differently,
    and a dotted email is a different mailbox from the undotted one. The
    already bar for identity fields is norm() — the SAME bar the correction
    branch uses — so the two branches partition exactly and the stripped
    comparison can never swallow a correction."""
    result = run_profile_fill(
        tmp_path,
        fields=[
            {"label": "Last Name", "kind": "text", "value": "OBrien"},
            {"label": "Email", "kind": "text", "value": "jordanexample.com@corp.test"},
        ],
        profile={"personal": {"last_name": "O'Brien",
                              "email": "jordan.example.com@corp.test"}},
    )
    assert result["already"] == []
    assert sorted(outcome_pairs(result)) == [
        ("Email", "corrected"), ("Last Name", "corrected"),
    ]
    assert result["values"]["Last Name"] == "O'Brien"
    assert result["values"]["Email"] == "jordan.example.com@corp.test"


def test_a_byte_identical_value_in_a_script_the_strip_deletes_is_still_already(tmp_path):
    """sameIgnoringFormat strips CJK/Cyrillic to "" and refuses the match (an
    empty-strip equality would invent matches), so the already check takes
    byte equality FIRST. Without it, a re-run over the extension's own fill of
    "東京" reported "0 filled" again — the exact symptom this feature fixes,
    for exactly the users the strip comment says it must not disadvantage."""
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": "City", "kind": "text", "value": "東京"}],
        profile={"personal": {"city": "東京"}},
    )
    assert [label for label, _ in already_pairs(result)] == ["city"]
    assert outcome_pairs(result) == []
    assert result["events"]["City"] == []


def test_a_disagreeing_identity_prefill_is_still_corrected(tmp_path):
    """The already list must not swallow the corrected path: a prefill that
    DISAGREES with the profile is a resume-parse guess and still gets fixed."""
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": "First Name", "kind": "text", "value": "Jord"}],
        profile=PROFILE,
    )
    assert result["already"] == []
    assert outcome_pairs(result) == [("First Name", "corrected")]
    assert result["values"]["First Name"] == "Jordan"


def test_a_disagreeing_ordinary_prefill_stays_silent(tmp_path):
    """A non-identity field holding something ELSE is left alone, unreported —
    unchanged behaviour. `already` claims agreement, not occupancy."""
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": "City", "kind": "text", "value": "Springfield"}],
        profile=PROFILE,
    )
    assert result["already"] == []
    assert result["filled"] == []
    assert outcome_pairs(result) == []
    assert result["values"]["City"] == "Springfield"


# ---------- selects ----------


def test_a_select_already_at_the_best_option_lands_in_already(tmp_path):
    result = run_profile_fill(
        tmp_path,
        fields=[{
            "label": "City",
            "kind": "select",
            "options": [
                {"value": "chi", "textContent": "Chicago"},
                {"value": "nyc", "textContent": "New York"},
            ],
            "value": "chi",
        }],
        profile=PROFILE,
    )
    assert result["filled"] == []
    assert already_pairs(result) == [("city", "Chicago")]
    assert outcome_pairs(result) == []


def test_a_select_at_a_different_option_is_still_replaced(tmp_path):
    """Pins that the already branch did not weaken the existing correction:
    an ATS prefill the profile disagrees with still gets the profile's value
    (test_extension_eeo_autofill.py's ordinary-select case, restated beside
    the new branch that must not shadow it)."""
    result = run_profile_fill(
        tmp_path,
        fields=[{
            "label": "City",
            "kind": "select",
            "options": [
                {"value": "chi", "textContent": "Chicago"},
                {"value": "nyc", "textContent": "New York"},
            ],
            "value": "nyc",
        }],
        profile=PROFILE,
    )
    assert result["already"] == []
    assert outcome_pairs(result) == [("City", "filled")]
    assert result["values"]["City"] == "chi"


# ---------- radio groups ----------


def test_a_radio_group_already_on_the_matching_button_is_already_not_refilled(tmp_path):
    """Before the fix this path re-clicked the checked button and reported
    `filled` — so a re-run inflated the count with writes that wrote nothing.
    Now it is an `already` entry, no click, no observation."""
    result = run_profile_fill(
        tmp_path,
        fields=[{
            "label": "Are you willing to relocate?",
            "kind": "radio",
            "options": ["Yes", "No"],
            "checkedOption": "Yes",
        }],
        profile={"preferences": {"willing_to_relocate": "yes"}},
    )
    assert result["filled"] == []
    assert len(result["already"]) == 1
    assert outcome_pairs(result) == []
    # The checked button was not clicked again (a click event on a checked
    # radio is harmless, but a report built on one is not).
    assert result["events"]["Are you willing to relocate?"] == []
    assert result["values"]["Are you willing to relocate?"] == "Yes"


def test_a_radio_group_on_the_wrong_button_is_still_answered_over(tmp_path):
    """An ATS pre-answer the profile disagrees with is a guess worth
    correcting — the existing behaviour, unchanged by the already branch."""
    result = run_profile_fill(
        tmp_path,
        fields=[{
            "label": "Are you willing to relocate?",
            "kind": "radio",
            "options": ["Yes", "No"],
            "checkedOption": "No",
        }],
        profile={"preferences": {"willing_to_relocate": "yes"}},
    )
    assert result["already"] == []
    assert outcome_pairs(result) == [("Are you willing to relocate?", "filled")]
    assert result["values"]["Are you willing to relocate?"] == "Yes"


# ---------- the derived checkbox ----------


def test_an_already_ticked_current_job_box_lands_in_already(tmp_path):
    """The tickWhenYes derivation, already applied: the box arrives ticked and
    the resume says this job is current. Re-run honesty, same as the rest."""
    result = run_profile_fill(
        tmp_path,
        fields=[{
            "label": "I currently work here | workexperience-192--current",
            "kind": "checkbox",
            "checked": True,
        }],
        employment=[{"employer": "Acme", "title": "Engineer",
                     "start_date": "Jan 2022", "current": True}],
    )
    assert result["filled"] == []
    assert len(result["already"]) == 1
    assert outcome_pairs(result) == []
    assert result["checked"]["I currently work here | workexperience-192--current"] is True


def test_a_ticked_box_whose_answer_is_no_stays_out_of_already(tmp_path):
    """A PAST job's box arriving ticked is wrong, but click() toggles and the
    engine never unticks a box — it reports skipped_checkbox there, and
    `already` may not
    claim it either: the box does not hold our answer."""
    result = run_profile_fill(
        tmp_path,
        fields=[{
            "label": "I currently work here | workexperience-192--current",
            "kind": "checkbox",
            "checked": True,
        }],
        employment=[{"employer": "Acme", "title": "Engineer",
                     "start_date": "Jan 2020", "end_date": "Dec 2021",
                     "current": False}],
    )
    assert result["already"] == []


# ---------- comboboxes ----------


def test_a_combobox_already_holding_the_value_lands_in_already(tmp_path):
    """The combobox half of the feature, pinned in the positive direction:
    fill-only-if-empty stands (§11 item 8c), but a value that IS ours is
    reported rather than silently skipped — and the control is never driven
    (no focus, no keys), because there is nothing to write."""
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": "Country", "kind": "combobox", "value": "United States"}],
        profile={"personal": {"country": "United States"}},
    )
    assert [label for label, _ in already_pairs(result)] == ["country"]
    assert outcome_pairs(result) == []
    assert result["events"]["Country"] == []


def test_a_combobox_holding_a_different_value_stays_silent(tmp_path):
    """Fill-only-if-empty, unchanged: a combobox holding something else is not
    overwritten (§11 item 8c defers that) and not claimed under any heading —
    `already` claims agreement, not occupancy."""
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": "Country", "kind": "combobox", "value": "Canada"}],
        profile={"personal": {"country": "United States"}},
    )
    assert result["already"] == []
    assert result["filled"] == []
    assert outcome_pairs(result) == []
    assert result["values"]["Country"] == "Canada"


# ---------- EEO stays silent everywhere, including the new list ----------


def test_an_already_answered_eeo_control_never_lands_in_already(tmp_path):
    """An answer already on a protected-class control is the user's own.
    Claiming it under any heading — filled, eeoFilled, or the new already —
    would assert a disclosure the extension did not witness."""
    result = run_profile_fill(
        tmp_path,
        fields=[
            {
                "label": "Gender",
                "kind": "select",
                "options": [
                    {"value": "f", "textContent": "Female"},
                    {"value": "m", "textContent": "Male"},
                ],
                "value": "f",
            },
            {
                "label": "Veteran Status",
                "kind": "radio",
                "options": ["I am not a protected veteran",
                            "I identify as a veteran"],
                "checkedOption": "I am not a protected veteran",
            },
            # A combobox holding what LOOKS like our own answer. Still never
            # claimed: eeo.js owns the answer-preserving guard, and this pin
            # keeps later generic combobox reconciliation from silently
            # acquiring an EEO already-claim.
            {"label": "Gender Identity", "kind": "combobox", "value": "Female"},
        ],
        profile={"eeo": {"gender": "female", "veteran_status": "not_veteran"}},
        eeo_enabled=True,
    )
    assert result["already"] == []
    assert result["filled"] == []
    assert result["eeoFilled"] == []
    assert outcome_pairs(result) == []


# ---------- the second run, end to end ----------


def test_a_second_run_reports_already_where_the_first_reported_filled(tmp_path):
    """The scenario the bug report described, as one harness run each way:
    fields empty → filled; the same fields holding those values → already.
    The two lists name the same fields, so the strip can say "already filled"
    instead of "0 filled" over a form the extension filled itself."""
    fields = [
        {"label": "Email", "kind": "text"},
        {"label": "City", "kind": "text"},
    ]
    first = run_profile_fill(tmp_path, fields=fields, profile=PROFILE)
    assert [item["label"] for item in first["filled"]] == ["email", "city"]

    refilled = [
        {**field, "value": value}
        for field, value in zip(fields, ["jordan@example.com", "Chicago"])
    ]
    second = run_profile_fill(tmp_path, fields=refilled, profile=PROFILE)
    assert second["filled"] == []
    assert [label for label, _ in already_pairs(second)] == ["email", "city"]
    assert outcome_pairs(second) == []
