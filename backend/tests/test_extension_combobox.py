"""The combobox writer against a listbox that actually renders.

Until the harness could render `[role="option"]` nodes, `fillCombobox`'s poll
loop had never run against a populated list in any test — every combobox test
exercised only the timeout path. These tests are the positive control for the
whole combobox surface: the Workday routing fix (isCombobox learning the
`data-uxi-widget-type` shape) and the listbox-button writer are both defined by
what that loop finds, so "a rendered list can be snapped to" has to be pinned
before either is expressible.
"""

from tests.extension_harness import (
    collected_labels,
    outcome_for,
    run_open_questions,
    run_profile_fill,
)


def test_a_rendered_listbox_lets_the_profile_pass_snap(tmp_path):
    """The positive control. Without it the two failure tests below prove
    nothing — a snap that never works also never fails informatively."""
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": "Country", "kind": "combobox",
                 "listbox": ["United States", "Canada"]}],
        profile={"personal": {"country": "United States"}},
    )
    assert outcome_for(result, "Country") == "filled"


def test_a_listbox_that_never_renders_is_a_snap_failure(tmp_path):
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": "Country", "kind": "combobox"}],
        profile={"personal": {"country": "United States"}},
    )
    assert outcome_for(result, "Country") == "combobox_snap_failed"


def test_a_listbox_whose_options_do_not_match_is_released(tmp_path):
    """Visible non-matching options make this an abstention, not a retry."""
    result = run_open_questions(
        tmp_path,
        fields=[{"label": "Country", "kind": "combobox",
                 "listbox": ["USA (US)", "United Kingdom (UK)"]}],
        profile={"personal": {"country": "United States"}},
    )
    assert collected_labels(result) == ["country"]
    assert result["collected"]["retryables"] == []


def test_options_that_arrive_late_are_still_found(tmp_path):
    """Remote school and location lists load async — the poll loop exists for
    exactly this and had never been exercised."""
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": "Country", "kind": "combobox",
                 "listbox": ["United States"], "listboxDelay": 400}],
        profile={"personal": {"country": "United States"}},
    )
    assert outcome_for(result, "Country") == "filled"


def test_options_are_reachable_through_aria_controls(tmp_path):
    """listboxOptions tries aria-controls/aria-owns BEFORE the bare
    [role="option"] query. A harness that only answered the fallback would let
    the attribute branch rot unexercised."""
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": "Country", "kind": "combobox",
                 "listbox": ["United States"], "listboxVia": "aria-controls"}],
        profile={"personal": {"country": "United States"}},
    )
    assert outcome_for(result, "Country") == "filled"


# ---------- the Workday search shape ----------


def test_a_workday_search_input_is_recognised_as_a_combobox(tmp_path):
    """`kind` is what telemetry records, so the flip from text to combobox IS
    the observable behaviour — assert it directly rather than inferring it.

    The signal is the vendor's own widget-type attribute, read off a live form
    (bah.wd1.myworkdayjobs.com, 2026-08-08): the phone-country-code control is
    `<input data-uxi-widget-type="selectinput" placeholder="Search">` with no
    combobox ARIA anywhere on it — which is why isCombobox() said no and the
    profile's answer was typed into a box that takes no free text (the 55
    not_stuck events that carried a rule_id).
    """
    label = "field of study | search | education-197--fieldofstudy"
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "combobox", "workdaySearch": True,
                 "listbox": ["Computer Science", "Mathematics"]}],
        profile={"education": [{"discipline": "Computer Science"}]},
    )
    assert outcome_for(result, label) == "filled"
    assert result["observations"][0]["kind"] == "combobox"


def test_an_ordinary_text_input_is_still_not_a_combobox(tmp_path):
    """The regression guard, and why the signal is a DOM attribute rather than
    the `| search |` label segment. Fields that fill through the plain-text
    writer today must keep doing so; a broadened isCombobox that swallowed one
    would trade a working fill for a snap failure."""
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": "City", "kind": "text"}],
        profile={"personal": {"city": "Austin"}},
    )
    assert outcome_for(result, "City") == "filled"
    assert result["observations"][0]["kind"] == "text"
