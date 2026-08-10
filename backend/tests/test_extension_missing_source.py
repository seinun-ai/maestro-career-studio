"""Telling "no answer in the profile" apart from "no rule for this label".

Both used to arrive as `no_rule` — see the ObservationOutcome Literal in
`app/schemas/autofill_telemetry.py` for why that mattered. These tests pin the
split in BOTH directions: a known field with an empty answer must not report
no_rule, and an unrecognised label must not report missing_source.

What a successful write is worth (`filled` vs `filled_normalized` vs
`not_stuck`) belongs to `test_extension_commit_ladder.py`.
"""

from tests.extension_harness import outcome_for, outcome_pairs, run_profile_fill


_SAMPLE = {"personal": {"first_name": "Sample"}}


# ---------- missing_source vs no_rule ----------


def test_rule_with_no_profile_value_reports_missing_source(tmp_path):
    """A known field with an empty profile answer must be distinguishable.

    rule_id is asserted because it is what names the profile field worth
    adding — and because on the outcome alone this stays green when the branch
    is deleted, since the field then gets written the literal "undefined".
    """
    result = run_profile_fill(
        tmp_path,
        profile=_SAMPLE,  # no preferences at all
        fields=[{"label": "Desired Salary", "kind": "text"}],
    )
    assert outcome_for(result, "Desired Salary") == "missing_source"
    assert result["observations"][0]["rule_id"] == "salary"
    assert result["filled"] == [], "a field with no answer must never be written"
    assert result["values"]["Desired Salary"] == ""


def test_label_nothing_matches_still_reports_no_rule(tmp_path):
    """The other direction: retaining valueless rules must not swallow the
    genuine coverage gaps that no_rule exists to collect."""
    result = run_profile_fill(
        tmp_path,
        profile=_SAMPLE,
        fields=[{"label": "Favourite Fictional Beverage", "kind": "text"}],
    )
    assert outcome_for(result, "Favourite Fictional Beverage") == "no_rule"


def test_a_rule_with_a_value_still_fills(tmp_path):
    """The retained-rule change must not disturb the ordinary path."""
    result = run_profile_fill(
        tmp_path, profile=_SAMPLE, fields=[{"label": "First Name", "kind": "text"}]
    )
    assert outcome_for(result, "First Name") == "filled"
    assert result["values"]["First Name"] == "Sample"


# ---------- rule ordering: a retained rule must not shadow a later one ----------


def test_valueless_rule_does_not_shadow_a_later_rule_that_can_fill(tmp_path):
    """THE regression risk in retaining valueless rules.

    `salary` sits above the custom Q&A rules and matches "expected salary".
    When it was filtered out for having no value, a custom question worded the
    same way won the field and filled it. Keeping it in the table must not turn
    that working fill into a missing_source report — a rule with nothing behind
    it only wins when nothing else can answer.
    """
    result = run_profile_fill(
        tmp_path,
        profile={
            "personal": {"first_name": "Sample"},
            "custom": [{"question": "Expected salary", "answer": "150000"}],
        },
        fields=[{"label": "Expected salary", "kind": "text"}],
    )
    assert outcome_for(result, "Expected salary") == "filled"
    assert result["values"]["Expected salary"] == "150000"


def test_a_skip_rule_still_wins_over_the_rules_below_it(tmp_path):
    """`phone-ext-fax` guards the broad /phone/ rule. It is retained as a skip,
    never as a missing source, so it must keep short-circuiting the match."""
    result = run_profile_fill(
        tmp_path,
        profile={"personal": {"phone": "5551234567"}},
        fields=[{"label": "Phone Extension", "kind": "text"}],
    )
    assert outcome_for(result, "Phone Extension") == "skip_rule"
    assert result["values"]["Phone Extension"] == "", "the extension got the phone number"


def test_first_matching_valueless_rule_is_the_one_reported(tmp_path):
    """When nothing can fill, the report names the rule that matched FIRST.

    "Phone Country Code" is matched by three rules in table order —
    `phone-country-code`, `phone`, then the generic `country` — and an empty
    profile leaves all three valueless. Table order is the rule set's only
    statement of specificity, so the remembered candidate has to be the first
    one; taking the last would name `country` for a field the rules describe
    more precisely, and rule_id is what tells the user which field to go add.
    """
    result = run_profile_fill(
        tmp_path, profile={}, fields=[{"label": "Phone Country Code", "kind": "text"}]
    )
    assert outcome_for(result, "Phone Country Code") == "missing_source"
    assert result["observations"][0]["rule_id"] == "phone-country-code"


# ---------- list rules (repeated blocks) ----------


def test_list_rule_with_an_empty_list_reports_missing_source(tmp_path):
    """No education entries at all is the same gap as an empty scalar field."""
    result = run_profile_fill(
        tmp_path,
        profile={"personal": {"first_name": "Sample"}, "education": []},
        fields=[{"label": "School", "kind": "text"}],
    )
    assert outcome_for(result, "School") == "missing_source"


def test_a_block_past_the_end_of_the_list_reports_nothing(tmp_path):
    """The surface symmetry with an empty rule is a trap, so it is pinned.

    missing_source answers "would filling in the profile help?". A form with
    five pre-rendered employment blocks is not three gaps for a user who has
    held two jobs — reporting them would scale the metric with the FORM instead
    of the profile, and that metric is what later work prioritizes on. "The
    form has more slots than you have history" is a real signal; it is not
    this one.
    """
    result = run_profile_fill(
        tmp_path,
        profile={"education": [{"school": "State University"}]},
        fields=[
            {"label": "School", "kind": "text"},
            {"label": "School", "kind": "text"},
        ],
    )
    assert outcome_pairs(result) == [("School", "filled")]


# ---------- hidden fields ----------


def test_a_hidden_field_with_no_answer_is_not_logged_at_all(tmp_path):
    """`hidden` means "we had an answer and could not reach the field". Every
    page carries invisible clone junk; a field we could not have filled anyway
    is noise, and it logged nothing here before the rules were retained — so
    this exclusion preserves the status quo rather than changing it."""
    result = run_profile_fill(
        tmp_path,
        profile=_SAMPLE,
        fields=[{"label": "Desired Salary", "kind": "text", "hidden": True}],
    )
    assert result["observations"] == []


def test_a_hidden_field_we_could_have_filled_is_still_logged(tmp_path):
    """The other half of that guard — don't silence the interesting case."""
    result = run_profile_fill(
        tmp_path,
        profile=_SAMPLE,
        fields=[{"label": "First Name", "kind": "text", "hidden": True}],
    )
    assert outcome_for(result, "First Name") == "hidden"
