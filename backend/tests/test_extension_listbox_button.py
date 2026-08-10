"""Workday's dropdowns are buttons, and the engine now walks them.

Verified live twice (homedepot.wd5 2026-08-06, bah.wd1 2026-08-08): Workday
renders every dropdown as `<button aria-haspopup="listbox" type="button">`
whose visible text is the committed value ("Select One" until one commits).
Neither writer walked buttons, so Country, State, Phone Type, every
work-authorization question and every EEO dropdown on a Workday tenant was
unfillable AND emitted no telemetry observation in any outcome — absent from
the evidence rather than under-counted in it.

The walk's discriminator is from the same live dump: a form dropdown carries
aria-haspopup="listbox", type="button" and NO data-automation-id; the header's
utility chrome (Settings, the account menu) carries haspopup too but always an
automation id and type="submit". Walking those would put "Settings" into
telemetry as a no_rule row on every page.
"""

from tests.extension_harness import outcome_for, outcome_pairs, run_profile_fill


_WORK_AUTH_PROFILE = {
    "work_auth": {
        "status": "opt",
        "authorized_now": True,
        "sponsorship_now": False,
        "sponsorship_future": False,
    }
}


def test_a_country_button_snaps_to_the_profile_country(tmp_path):
    label = "country united states of america required | country--country"
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "listboxButton",
                 "listbox": ["United States of America", "Canada", "Mexico"]}],
        profile={"personal": {"country": "United States"}},
    )
    assert outcome_for(result, label) == "filled"
    assert result["observations"][0]["kind"] == "combobox"
    assert result["values"][label] == "United States of America"


def test_a_work_authorization_button_answers_yes_from_the_typed_profile(tmp_path):
    """The reported bug: work-authorization dropdowns on Workday never filled
    despite the profile carrying the typed answers."""
    label = ("are you legally authorized to work in the united states?* | "
             "primaryquestionnaire--legallyauthorized")
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "listboxButton",
                 "listbox": ["Yes", "No"]}],
        profile=_WORK_AUTH_PROFILE,
    )
    assert outcome_for(result, label) == "filled"
    assert result["values"][label] == "Yes"


def test_a_button_already_showing_the_answer_is_reported_already(tmp_path):
    """Fill-only-if-empty, like every identity combobox: a committed value is
    an answer — the user's or a prior run's — and is never re-driven."""
    label = "country united states of america required | country--country"
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "listboxButton",
                 "value": "United States of America",
                 "listbox": ["United States of America", "Canada"]}],
        profile={"personal": {"country": "United States"}},
    )
    assert outcome_pairs(result) == []
    assert result["already"] == [
        {"label": label, "value": "United States of America"}]


def test_utility_chrome_buttons_are_never_walked(tmp_path):
    """The header's Settings/account menus carry aria-haspopup too. The
    discriminator is the automation id + submit type they always carry
    (live dump, bah.wd1 2026-08-08): walking them would print "Settings" into
    telemetry as a no_rule row on every Workday page."""
    result = run_profile_fill(
        tmp_path,
        fields=[
            {"label": "Settings", "kind": "listboxButton", "type": "submit",
             "automationId": "utilityMenuButton", "listbox": ["Sign Out"]},
        ],
        profile={"personal": {"country": "United States"}},
    )
    assert outcome_pairs(result) == []
    assert result["values"]["Settings"] == "Select One"


def test_a_button_no_rule_claims_is_observed_as_no_rule(tmp_path):
    """The blind-spot half of the fix: an unfillable button now at least
    EXISTS in telemetry, which is what makes the next evidence pass honest."""
    label = "preferred shift | scheduling--shiftpreference"
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "listboxButton",
                 "listbox": ["Day", "Night"]}],
        profile={"personal": {"country": "United States"}},
    )
    assert outcome_for(result, label) == "no_rule"


def test_a_gender_button_fills_only_under_the_eeo_opt_in(tmp_path):
    """Workday renders the voluntary-disclosure dropdowns as the same buttons.
    The consent gate and the exact-match bar both apply unchanged."""
    label = "gender select one required | personalinfoperson--gender"
    fields = [{"label": label, "kind": "listboxButton",
               "listbox": ["Male", "Female", "I do not wish to answer"]}]
    profile = {"eeo": {"gender": "male"}}

    off = run_profile_fill(tmp_path, fields=fields, profile=profile)
    assert outcome_for(off, label) == "eeo_disabled"
    assert off["values"][label] == "Select One"

    on = run_profile_fill(tmp_path, fields=fields, profile=profile,
                          eeo_enabled=True)
    assert outcome_for(on, label) == "filled"
    assert on["values"][label] == "Male"
    assert on["eeoFilled"] == [
        {"field": "gender", "label": label[:60], "value": "Male"}]


def test_a_how_heard_button_takes_the_preference(tmp_path):
    """The 'job dropdown not selecting' bug: How Did You Hear About Us is a
    listbox popup on Workday, answered from preferences.how_heard."""
    label = "how did you hear about us?* | source--source"
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "listboxButton",
                 "listbox": ["Job Board", "LinkedIn", "Employee Referral"]}],
        profile={"preferences": {"how_heard": "Job board"}},
    )
    assert outcome_for(result, label) == "filled"
    assert result["values"][label] == "Job Board"


def test_a_button_whose_options_never_match_reports_snap_failed(tmp_path):
    label = "country select one required | country--country"
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "listboxButton",
                 "listbox": ["Andorra", "Bhutan"]}],
        profile={"personal": {"country": "United States"}},
    )
    assert outcome_for(result, label) == "combobox_snap_failed"
    assert result["values"][label] == "Select One"


def test_a_snap_failure_records_what_the_page_offered(tmp_path):
    """A dropdown that could not be matched is unfixable without knowing what
    its options said, and a button popup's options exist nowhere else in the
    payload. Captured only while the popup is already open — a telemetry read
    may not drive the page."""
    label = "country select one required | country--country"
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "listboxButton",
                 "listbox": ["Andorra", "Bhutan"]}],
        profile={"personal": {"country": "United States"}},
    )
    assert outcome_for(result, label) == "combobox_snap_failed"
    assert result["observations"][0]["options"] == ["Andorra", "Bhutan"]


def test_a_placeholder_row_is_never_chosen(tmp_path):
    """Workday's popups carry their own "Select One" row. Picking it writes the
    placeholder back as though it were an answer — the control then looks
    filled while the form still refuses it."""
    label = "how did you hear about us?* | source--source"
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "listboxButton",
                 "listbox": ["Select One", "LinkedIn"]}],
        profile={"preferences": {"how_heard": "Select One"}},
    )
    assert outcome_for(result, label) == "combobox_snap_failed"
    assert result["values"][label] == "Select One"  # untouched placeholder


def test_another_widgets_committed_chip_is_never_clicked(tmp_path):
    """`[role="option"]` is document-wide, so the unscoped fallback sees every
    open popup AND every multiselect's committed chips — measured live, one
    open dropdown returned 62 nodes, one belonging to a widget three fields
    away. Clicking a chip un-picks a value the user already committed."""
    label = "country select one required | country--country"
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "listboxButton", "listbox": [
            {"text": "United States of America (+1)", "chosenChip": True},
            "Canada"]}],
        profile={"personal": {"country": "United States"}},
    )
    # The chip scores highest for "United States" and is the ONLY thing that
    # could have matched — refusing it leaves the field honestly unfilled.
    assert outcome_for(result, label) == "combobox_snap_failed"
    assert result["values"][label] == "Select One"


def test_a_custom_qa_preset_answers_a_button_dropdown(tmp_path):
    """The route for a question no rule can derive — "Are you 18 years of age
    or older?" being the live example (deluxe.wd5, 2026-08-08).

    Nothing in the profile can answer it: there is no date of birth, and
    inferring an age answer from the work history would be the extension
    stating something about the user they never told it. So it belongs to the
    custom Q&A presets, which the user writes once — and the matcher is
    substring-on-the-label, so the trailing required marker does not defeat it.

    What made this reachable at all is the button walk: before it, a custom
    preset could not answer ANY Workday dropdown, because none of them was a
    control the engine looked at.
    """
    label = ("no required | 4eda80f45a37 | primaryquestionnaire--4eda80f45a37 "
             "| are you 18 years of age or older?*")
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "listboxButton",
                 "listbox": ["Select One", "Yes", "No"]}],
        profile={"custom": [
            {"question": "Are you 18 years of age or older?", "answer": "Yes"}]},
    )
    assert outcome_for(result, label) == "filled"
    assert result["values"][label] == "Yes", "the placeholder or No was chosen"


def test_a_committed_answer_is_never_overwritten_by_a_preset(tmp_path):
    """The other half, and the one that protects the user's own answer.

    A button already showing a choice holds an answer — theirs, or one the ATS
    remembered from a previous application. A preset does not get to overrule
    it, for the same reason an identity combobox is fill-only-if-empty: the
    value on the page was put there by a person, and this fill was not asked to
    change anyone's mind.
    """
    label = ("no required | primaryquestionnaire--x | are you 18 years of age or older?*")
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "listboxButton", "value": "No",
                 "listbox": ["Select One", "Yes", "No"]}],
        profile={"custom": [
            {"question": "Are you 18 years of age or older?", "answer": "Yes"}]},
    )
    assert result["values"][label] == "No", "the user's own answer was overwritten"
    assert result["already"] == [{"label": label[:60], "value": "No"}]
