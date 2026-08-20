"""The write → commit → verify ladder the extension uses on text fields.

`filled` is the load-bearing word in autofill telemetry, so what counts as a
successful write has to be true rather than optimistic. These tests pin the
properties a commit must have: it survives the framework's asynchronous
re-render before we call it stuck, it is still looking at a node that is on the
page, it blurs so blur-triggered validation runs, it sends the keyboard events
custom widgets listen for, and it never hangs the run.

The second half owns the readback's verdict — which of `filled`,
`filled_normalized` and `not_stuck` a given ending earns. That question lives
here rather than with the missing_source tests because it is a property of
`valueHolds`, and splitting it across two files leaves half the answer in each.
"""

import re

from tests.extension_harness import (
    extension_source,
    outcome_for,
    run_ai_fill,
    run_guided_write,
    run_profile_fill,
)


_PROFILE = {"personal": {"first_name": "Sample"}}
_PHONE = {"personal": {"phone": "5551234567"}}


def _run_scenario(tmp_path, *, fields, profile=None, pairs=None, freeze_frames=False,
                  eeo_enabled=False) -> dict:
    """Fill `fields` under Node. `pairs` switches to the AI-fill path."""
    if pairs is not None:
        return run_ai_fill(tmp_path, fields=fields, pairs=pairs)
    return run_profile_fill(
        tmp_path, fields=fields, profile=profile, freeze_frames=freeze_frames,
        eeo_enabled=eeo_enabled,
    )


def _outcomes(result: dict) -> dict:
    return {o["label"]: o["outcome"] for o in result["observations"]}


def test_value_that_reverts_on_a_later_tick_is_reported_not_stuck(tmp_path):
    """The readback must survive React's async re-render, not just the write."""
    result = _run_scenario(tmp_path, profile=_PROFILE,
                           fields=[{"label": "First Name", "kind": "text", "reverts": True}])
    assert _outcomes(result)["First Name"] == "not_stuck"


def test_value_that_holds_is_reported_filled(tmp_path):
    """The honest readback must still say `filled` when the value really stuck."""
    result = _run_scenario(tmp_path, profile=_PROFILE,
                           fields=[{"label": "First Name", "kind": "text"}])
    assert _outcomes(result)["First Name"] == "filled"
    assert result["values"]["First Name"] == "Sample"


def test_value_left_on_a_detached_node_is_reported_not_stuck(tmp_path):
    """A node the widget re-rendered away keeps our value forever — nothing is
    rendering it. Reading only `.value` would call that `filled` while the user
    sees an empty field, which is the exact lie this ladder exists to kill."""
    result = _run_scenario(tmp_path, profile=_PROFILE,
                           fields=[{"label": "First Name", "kind": "text", "detaches": True}])
    assert _outcomes(result)["First Name"] == "not_stuck"


def test_commit_blurs_the_field(tmp_path):
    """Without a blur the field stays 'untouched' and validation never runs."""
    result = _run_scenario(tmp_path, profile=_PROFILE,
                           fields=[{"label": "First Name", "kind": "text"}])
    events = result["events"]["First Name"]
    assert "input" in events and "change" in events
    assert "blur" in events, "field never blurred: validation will not run"


def test_commit_sends_keyboard_events(tmp_path):
    """Custom ATS widgets listen for keydown/keyup, not the standard input event."""
    events = _run_scenario(tmp_path, profile=_PROFILE,
                           fields=[{"label": "First Name", "kind": "text"}])["events"]["First Name"]
    assert "keydown" in events and "keyup" in events


def test_commit_focuses_without_scrolling(tmp_path):
    """focus() scrolls into view by default, so a 25-field fill would visibly
    walk the page and park on the last input."""
    events = _run_scenario(tmp_path, profile=_PROFILE,
                           fields=[{"label": "First Name", "kind": "text"}])["events"]["First Name"]
    assert "focus:preventScroll" in events
    assert "focus" not in events, "focus() without preventScroll scrolls the page"


def test_a_write_that_cannot_be_verified_does_not_hang_the_run(tmp_path):
    """requestAnimationFrame never fires in a backgrounded tab. Without a
    timeout the promise never settles and the Fill button hangs forever."""
    result = _run_scenario(tmp_path, profile=_PROFILE, freeze_frames=True,
                           fields=[{"label": "First Name", "kind": "text"}])
    assert _outcomes(result)["First Name"] == "filled_unverified"


def test_combobox_that_cannot_snap_is_blurred_and_reported_as_unfilled(tmp_path):
    """react-select/select2 clear their search box on blur. Leaving the typed
    text unblurred just defers that to the next field's focus() — so blur here
    and describe the field the user will actually find."""
    result = _run_scenario(tmp_path, profile=_PROFILE,
                           fields=[{"label": "First Name", "kind": "combobox"}])
    events = result["events"]["First Name"]
    assert "focus:preventScroll" in events and "focus" not in events
    assert "blur" in events
    assert _outcomes(result)["First Name"] == "combobox_snap_failed"
    note = result["filled"][0]["note"]
    assert "manually" in note, note


def test_eeo_combobox_that_cannot_snap_is_not_listed_as_disclosed(tmp_path):
    """The EEO list has no note field and is rendered as a bare label → value
    under an "EEO fields filled" heading, so an entry there reads as a completed
    disclosure. A snap-failed combobox is blurred and therefore definitively
    empty — listing it would be a flat lie about a protected-class field."""
    result = _run_scenario(tmp_path, eeo_enabled=True,
                           profile={"eeo": {"gender": "female"}},
                           fields=[{"label": "Gender", "kind": "combobox"}])
    assert _outcomes(result)["Gender"] == "combobox_snap_failed"
    assert result["eeoFilled"] == []
    # Still surfaced in the hedged list, so the user is told to go fix it.
    assert "manually" in result["filled"][0]["note"]


def test_ai_fill_does_not_count_a_reverted_answer_as_answered(tmp_path):
    """ai_answered rides on the same readback — it needs the same honesty."""
    result = _run_scenario(
        tmp_path,
        fields=[
            {"label": "Why here?", "kind": "textarea", "qid": "q1", "reverts": True},
            {"label": "Why now?", "kind": "textarea", "qid": "q2"},
        ],
        pairs=[
            {"qid": "q1", "answer": "Sample answer", "kind": "textarea"},
            {"qid": "q2", "answer": "Sample answer", "kind": "textarea"},
        ],
    )
    assert result["filled"] == ["q2"]


def test_ai_fill_counts_a_reformatted_answer_as_answered(tmp_path):
    """COMMIT_OK exists twice and each copy feeds a different call site.

    The profile panel's hedge covers the first; nothing else covers this one.
    Dropping filled_normalized from the AI copy would silently stop counting
    answers that landed on any site that reformats input.
    """
    result = _run_scenario(
        tmp_path,
        fields=[{
            "label": "Start date?", "kind": "text", "qid": "q1",
            "normalizesTo": "01 Mar 2026",
        }],
        pairs=[{"qid": "q1", "answer": "01Mar2026", "kind": "text"}],
    )
    assert result["filled"] == ["q1"]


def test_ai_fill_runs_the_same_ladder_rungs(tmp_path):
    """The whole risk of the duplicated ladder is one copy losing a rung."""
    events = _run_scenario(
        tmp_path,
        fields=[{"label": "Why now?", "kind": "textarea", "qid": "q2"}],
        pairs=[{"qid": "q2", "answer": "Sample answer", "kind": "textarea"}],
    )["events"]["Why now?"]
    assert "focus:preventScroll" in events and "focus" not in events
    assert "keydown" in events and "keyup" in events
    assert "blur" in events


# ---------- what the readback's verdict means ----------


def test_a_site_that_reformats_our_value_reports_filled_normalized(tmp_path):
    """A phone mask rewriting "5551234567" as "(555) 123-4567" took the value.

    The two-frame readback cannot see that verbatim, so it called every masked
    field not_stuck — a mechanical failure for a fill that worked, inflating
    the exact baseline this telemetry exists to measure. It is reported without
    a hedge, because hedging a success teaches the user to distrust the fills
    that worked.
    """
    result = _run_scenario(
        tmp_path, profile=_PHONE,
        fields=[{"label": "Phone", "kind": "text", "normalizesTo": "(555) 123-4567"}],
    )
    assert outcome_for(result, "Phone") == "filled_normalized"
    assert result["values"]["Phone"] == "(555) 123-4567"
    assert result["filled"] == [{"label": "phone", "value": "5551234567"}]


def test_normalization_ignores_case_and_punctuation(tmp_path):
    """"new york ny" and "New York, NY" are the same answer typed differently."""
    result = _run_scenario(
        tmp_path, profile={"personal": {"city": "New York, NY"}},
        fields=[{"label": "City", "kind": "text", "normalizesTo": "new york ny"}],
    )
    assert outcome_for(result, "City") == "filled_normalized"


def test_normalization_folds_accents_rather_than_dropping_them(tmp_path):
    """Diacritic-stripping is among the commonest ATS normalizations there is.

    Deleting "é" instead of folding it to "e" makes every such site a failure —
    and that error lands entirely on non-ASCII names and cities, so it is a
    measurement bias rather than noise. The metric would systematically
    under-represent exactly those users.
    """
    result = _run_scenario(
        tmp_path, profile={"personal": {"first_name": "José"}},
        fields=[{"label": "First Name", "kind": "text", "normalizesTo": "Jose"}],
    )
    assert outcome_for(result, "First Name") == "filled_normalized"


def test_a_dropped_leading_zero_stays_not_stuck(tmp_path):
    """Folding stops at case, punctuation and diacritics — on purpose.

    "8/2019" for "08/2019" reads like a reformat, but the fix generalizes
    badly: leading zeros are significant in postal codes ("01234" and "1234"
    are different places) and in employee and requisition IDs. Under-claiming
    one date is much cheaper than calling a wrong postal code a success, so
    this is pinned as a boundary rather than left as an accident.
    """
    result = _run_scenario(
        tmp_path, profile={"preferences": {"earliest_start_date": "08/2019"}},
        fields=[{"label": "Start Date", "kind": "text", "normalizesTo": "8/2019"}],
    )
    assert outcome_for(result, "Start Date") == "not_stuck"


def test_a_transliterated_umlaut_stays_not_stuck(tmp_path):
    """The other boundary: folding is not transliteration.

    "Mueller" for "Müller" is a real ATS behaviour, but ü→ue is locale-specific
    and directly contradicts the ü→u that NFKD does for every other language.
    There is no single right answer, so this one keeps under-claiming.
    """
    result = _run_scenario(
        tmp_path, profile={"personal": {"last_name": "Müller"}},
        fields=[{"label": "Last Name", "kind": "text", "normalizesTo": "Mueller"}],
    )
    assert outcome_for(result, "Last Name") == "not_stuck"


def test_a_script_with_no_ascii_form_is_not_stuck_not_a_false_match(tmp_path):
    """CJK and Cyrillic strip to "" — deliberately, and the empty guard is what
    keeps that from becoming a match between two unrelated values. Reporting
    not_stuck under-claims a fill that may have worked; inventing a success
    between 北京 and 上海 would be a lie. Under-claiming is the safe direction."""
    result = _run_scenario(
        tmp_path, profile={"personal": {"city": "北京"}},
        fields=[{"label": "City", "kind": "text", "normalizesTo": "上海"}],
    )
    assert outcome_for(result, "City") == "not_stuck"


def test_an_answer_with_no_alphanumerics_cannot_match_an_empty_field(tmp_path):
    """Stripping formatting turns a punctuation-only answer into "", and an
    emptied field strips to "" as well — so a bare equality would call a
    rejected write a success. Only the both-ends-empty case is affected, which
    is why it needs its own test rather than a phone number."""
    result = _run_scenario(
        tmp_path, profile={"preferences": {"desired_salary": "$$$"}},
        fields=[{"label": "Desired Salary", "kind": "text", "normalizesTo": ""}],
    )
    assert outcome_for(result, "Desired Salary") == "not_stuck"


def test_a_field_that_adds_digits_is_not_stuck(tmp_path):
    """Normalizing is equality after stripping, not a fuzzy match.

    A field rendering "+1 (555) 123-4567" for the number we typed has added a
    digit, so what it holds is not what we wrote. Accepting a substring here
    would wave through truncation and appending too — a field that silently
    caps at ten characters would report a success.
    """
    result = _run_scenario(
        tmp_path, profile=_PHONE,
        fields=[{"label": "Phone", "kind": "text", "normalizesTo": "+1 (555) 123-4567"}],
    )
    assert outcome_for(result, "Phone") == "not_stuck"


def test_a_detached_node_is_not_rescued_by_the_normalization_branch(tmp_path):
    """isConnected must be checked BEFORE the value comparison, not after.

    A node the widget re-rendered away keeps whatever we assigned it, so it
    also still "normalizes" to what we wrote — the normalization branch will
    happily call it filled_normalized for a field the user sees empty, which is
    the exact false success this ladder exists to kill. The plain detached case
    cannot catch the ordering (it reaches an isConnected check either way);
    only a node that detaches AND reformats can, because reformatting diverts
    it into the normalization branch first.
    """
    result = _run_scenario(
        tmp_path, profile=_PHONE,
        fields=[{
            "label": "Phone", "kind": "text",
            "detaches": True, "normalizesTo": "(555) 123-4567",
        }],
    )
    assert outcome_for(result, "Phone") == "not_stuck"


def test_every_copy_of_the_label_normaliser_stays_identical():
    """`norm` exists four times, and one CHAIN runs through three of them.

    `shared/profile-fields.js` publishes it as `ns.normLabel`;
    `collectOpenQuestions` normalises the label it stamps onto a collected
    question with its own copy; `fillFormFromProfile` normalises the label it
    matches a rule against with a third; `fillAnswersByQid` carries a fourth
    for the reason the commit ladder below carries two — it is injected and
    must be self-contained.

    THE CHAIN IS WHY THIS IS PINNED RATHER THAN LEFT ALONE. The pause row's
    learn walks it end to end: a label normalised by the collector, deduped
    against the stored `custom` list by `ns.normLabel`, matched by the engine on
    the NEXT application. A copy that drifted would not throw and would not fail
    a match loudly — it would append a near-duplicate question, and the engine
    takes the FIRST match, so the user's newer answer would be dead on arrival
    with every other test green.

    ONE SITE WAS CONVERGED rather than pinned: autofill.js's custom-rule builder
    reads `ns.normLabel` directly, because that is the site the dedup's
    correctness actually depends on. The definitions stay pinned because the
    rest of each file uses its own copy — the collector for the label it stamps,
    `fillFormFromProfile` for the one it hands `createEeoContext` — and "the
    same three transforms" is a property nothing else enforces.
    """
    src = extension_source()
    copies = re.findall(
        r'const norm = \(s\) => [^;]+;', src)
    assert len(copies) == 4, (
        f"expected four label normalisers, found {len(copies)}: a new copy "
        "needs a reason, and a deleted one needs this count updated")
    assert len(set(copies)) == 1, (
        f"the label normalisers have diverged — fix all four or none: {copies}")


def test_both_copies_of_the_commit_ladder_stay_identical():
    """The ladder exists twice: injected functions cannot close over panel
    scope, so fillAnswersByQid carries its own copy. Nothing but this test
    stops a fix from being applied to one copy and not the other.

    setNativeValue is part of the guarded run: it is the block commitValue
    calls to do the actual write and fire input/change, it is duplicated the
    same way, and it sits directly above each ladder — so it is the block most
    likely to be edited next.

    The `.*?` between the three named blocks is load-bearing, not filler:
    anything declared BETWEEN them is captured and compared too. That is why
    sameIgnoringFormat and COMMIT_OK belong there rather than above
    setNativeValue — inside the span they are covered by this test, outside it
    they would silently be free to diverge.
    """
    src = extension_source()
    copies = re.findall(
        r"const setNativeValue = \(input, value\) => \{.*?\n  \};"
        r".*?const valueHolds = \(input, value\) => new Promise\(\(resolve\) => \{.*?\n  \}\);"
        r".*?const commitValue = async \(input, value, \{ blur = true \} = \{\}\) => \{.*?\n  \};",
        src, re.S)
    assert len(copies) == 2, f"expected two commit ladders, found {len(copies)}"
    def strip(s):
        return re.sub(r"\s+", " ", re.sub(r"//[^\n]*", "", s)).strip()
    assert strip(copies[0]) == strip(copies[1]), \
        "the two commit ladders have diverged — fix both or neither"


# ---------- the commit GESTURE: the visit every other writer owes ----------
#
# The ladder above is the TEXT path, and it has focused before it blurred since
# it was written. Everything else in the engine did not, and the section below
# is that gap pinned shut.
#
# THE LIVE SYMPTOM (Workday wizard walk, 2026-08-18): fields the engine filled
# kept showing "required and must have a value" until the user clicked into each
# one and back out. The write had landed — the value was on screen — but the
# page had never seen the control VISITED, because a `<select>` set through the
# native setter and a radio driven by `element.click()` fire no focus events at
# all, and the two option writers focused to open their popup and returned on
# the success path without ever leaving.
#
# WHY THE EVENT LIST IS THE ASSERTION and not the value: every one of these
# writers already landed its value before this change, so a test that checked
# `values` would have been green on the broken engine. What was missing was a
# pair of events, so a pair of events is what is pinned.


def _events(result: dict, label: str) -> list:
    return result["events"][label]


def _visited(events: list) -> bool:
    """Did this control see a real focus/blur cycle, in that order?

    `focus:preventScroll` and not `focus`, because the option matters: focus()
    scrolls into view by default and a 25-field fill would visibly walk the
    page (see `visitControl`). A writer that focused WITHOUT it would pass a
    laxer test and fail the user.
    """
    return ("focus:preventScroll" in events
            and "blur" in events
            and events.index("focus:preventScroll") < events.index("blur"))


_COUNTRY = "country | country--country"


def test_a_select_is_visited_around_the_write_not_merely_set(tmp_path):
    """A native select set through the value setter fires input and change and
    NOTHING else — so a form that clears its required-field error on focusout
    keeps showing it over a field the user can see is full."""
    label = "state | state--state"
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "select",
                 "options": [{"value": "ca", "textContent": "California"},
                             {"value": "ny", "textContent": "New York"}]}],
        profile={"personal": {"state": "California"}},
    )
    events = _events(result, label)
    # The option's VALUE, which is what a select holds — the harness reports
    # `.value`, and the visible text is the option's.
    assert result["values"][label] == "ca"
    assert _visited(events), events
    # The ORDER against the write, not merely presence: a focus that landed
    # after `change` would be a visit the page's validation has already run
    # past, which is the same nothing.
    assert events.index("focus:preventScroll") < events.index("change") < events.index("blur")


def test_a_radio_the_engine_clicks_is_focused_and_left(tmp_path):
    """`element.click()` dispatches a click event and does NOT move focus,
    which is exactly where it differs from the gesture it stands in for."""
    label = "are you legally authorized to work in the united states?"
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "radio", "options": ["Yes", "No"]}],
        profile={"work_auth": {"authorized_now": True}},
    )
    assert result["values"][label] == "Yes"
    # The GROUP's events, flattened by the harness: the button that was clicked
    # is the one that carries the cycle.
    events = _events(result, label)
    assert _visited(events), events
    assert events.index("focus:preventScroll") < events.index("click") < events.index("blur")


def test_a_derived_checkbox_tick_takes_the_same_gesture(tmp_path):
    """The `tickWhenYes` box — the one checkbox the engine is authorized to
    tick — is clicked, and a click is not a visit."""
    label = ("i currently work here | currentlyworkhere "
             "| workexperience-192--currentlyworkhere")
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "checkbox"}],
        profile={"personal": {"first_name": "Sample"}},
        # `current: true` is what the derivation reads — see
        # test_extension_current_job.py for the shape's provenance.
        employment=[{"employer": "Northwind Traders", "title": "Senior DS",
                     "start_date": "March 2021", "end_date": None,
                     "current": True}],
    )
    assert result["checked"][label] is True
    events = _events(result, label)
    assert _visited(events), events
    assert events.index("focus:preventScroll") < events.index("click") < events.index("blur")


def test_a_radio_the_widget_re_rendered_away_is_not_reported_filled(tmp_path):
    """A STATE THE COMMIT GESTURE CREATED, and the reason these verdicts needed
    a guard they never had: before the writers blurred, a click writer could not
    trigger a re-render, so the node a verdict is read off was always the node
    that was clicked. Blur is the classic trigger — so `radio.checked` can now
    be read off a button the page has already replaced, which keeps our answer
    forever precisely because nothing is rendering it.

    `valueHolds` has taken `isConnected` FIRST since it was written, for exactly
    this reason; the click writers simply had no need of it until now.
    """
    label = "are you legally authorized to work in the united states?"
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "radio", "options": ["Yes", "No"],
                 "detaches": True}],
        profile={"work_auth": {"authorized_now": True}},
    )
    # NOTHING IS CLAIMED, which is the whole assertion: the button really was
    # checked (the detach happens on the blur, after the click), so a readback
    # that only asked `checked` would report this as filled. There is no
    # telemetry row either way — a radio that did not take emits no frozen
    # outcome, which is pre-existing and not this guard's business.
    assert result["filled"] == []


def test_a_derived_checkbox_the_widget_re_rendered_away_is_not_claimed(tmp_path):
    """The same guard on the box whose answer the engine DERIVED — the one place
    a false "filled" is a false statement about a job's end date rather than a
    miscount."""
    label = ("i currently work here | currentlyworkhere "
             "| workexperience-192--currentlyworkhere")
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "checkbox", "detaches": True}],
        profile={"personal": {"first_name": "Sample"}},
        employment=[{"employer": "Northwind Traders", "title": "Senior DS",
                     "start_date": "March 2021", "end_date": None,
                     "current": True}],
    )
    assert _outcomes(result)[label] == "not_stuck"
    assert [item["note"] for item in result["filled"]] == [
        "may not have registered, check the box"]


def test_a_listbox_button_that_committed_still_ends_blurred(tmp_path):
    """The success path was the ONLY path out of this writer that never left
    the control — so whether a Workday dropdown got validated depended on
    whether the fill happened to match an option, which is backwards."""
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": _COUNTRY, "kind": "listboxButton",
                 "listbox": ["United States", "Canada"]}],
        profile={"personal": {"country": "United States"}},
    )
    assert result["values"][_COUNTRY] == "United States"
    events = _events(result, _COUNTRY)
    assert _visited(events), events
    # The blur is LAST: it comes after the option click, so it closes the popup
    # and commits rather than interrupting the write.
    assert events[-1] == "blur", events


def test_a_combobox_that_snapped_an_option_still_ends_blurred(tmp_path):
    """The typed-search twin of the button above, and it had the same hole."""
    label = "country | phonenumber--countryphonecode"
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "text", "workdaySearch": True,
                 "listbox": ["United States", "Canada"]}],
        profile={"personal": {"country": "United States"}},
    )
    events = _events(result, label)
    assert _visited(events), events
    assert events[-1] == "blur", events


def test_an_identity_correction_is_visited_like_every_other_write(tmp_path):
    """The one text write in the rule loop that does not go through
    `commitValue`, and therefore the one that had no visit of its own. It is
    also the case that most needs one: the field arrived PREFILLED, so the
    page's own validation has already run over the value being replaced."""
    label = "first name | firstname"
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": label, "kind": "text", "value": "Jordan"}],
        profile={"personal": {"first_name": "Sample"}},
    )
    assert result["values"][label] == "Sample"
    events = _events(result, label)
    assert _visited(events), events
    assert events.index("focus:preventScroll") < events.index("change") < events.index("blur")


def test_every_field_a_run_wrote_ends_blurred(tmp_path):
    """THE RUN-LEVEL PROPERTY, and the one the Goal Card names: the last field
    written must end blurred rather than holding focus. Asserted over a mixed
    page so it is a property of the loop rather than of whichever branch a
    single-field fixture happened to take."""
    labels = {
        "text": "first name | firstname",
        "select": "state | state--state",
        "radio": "are you legally authorized to work in the united states?",
    }
    result = run_profile_fill(
        tmp_path,
        fields=[
            {"label": labels["text"], "kind": "text"},
            {"label": labels["select"], "kind": "select",
             "options": [{"value": "ca", "textContent": "California"}]},
            {"label": labels["radio"], "kind": "radio", "options": ["Yes", "No"]},
        ],
        profile={"personal": {"first_name": "Sample", "state": "California"},
                 "work_auth": {"authorized_now": True}},
    )
    for name, label in labels.items():
        events = _events(result, label)
        assert events, f"{name} wrote nothing at all"
        assert events[-1] == "blur", f"{name} ended holding focus: {events}"


# ---------- the same gesture, on the other two writers ----------


def test_the_guided_select_and_radio_writers_take_the_gesture(tmp_path):
    """`guided_write` is the second-pass writer and its non-text limbs had the
    identical gap — `guidedTextWrite` already focused and blurred, which is why
    only the others move."""
    result = run_guided_write(
        tmp_path,
        fields=[
            {"qid": "q-state", "label": "State", "kind": "select",
             "options": [{"value": "ca", "textContent": "California"}]},
            # `legend` so each button's own text is just "Yes"/"No", which is
            # what `guidedControlLabel` reads and what the model answers with.
            {"qid": "q-auth", "label": "Authorized", "kind": "radio",
             "legend": "Authorized", "options": ["Yes", "No"]},
        ],
        items=[
            {"qid": "q-state", "kind": "select", "answer": "California"},
            {"qid": "q-auth", "kind": "radio", "answer": "Yes"},
        ],
    )
    assert [row["outcome"] for row in result["results"]] == ["filled", "filled"]
    for label in ("State", "Authorized"):
        assert _visited(_events(result, label)), _events(result, label)


def test_the_guided_listbox_writer_leaves_the_control(tmp_path):
    result = run_guided_write(
        tmp_path,
        fields=[{"qid": "q-country", "label": "Country", "kind": "listboxButton",
                 "listbox": ["United States", "Canada"]}],
        items=[{"qid": "q-country", "kind": "combobox", "answer": "Canada"}],
    )
    assert [row["outcome"] for row in result["results"]] == ["filled"]
    events = _events(result, "Country")
    assert _visited(events), events
    assert events[-1] == "blur", events


def test_the_ai_paths_select_and_radio_limbs_take_the_gesture(tmp_path):
    """`fillAnswersByQid` carries its own copy of everything for the injection
    reason, so its select and radio limbs are a third place the gesture has to
    exist — and a third place it could be forgotten."""
    result = run_ai_fill(
        tmp_path,
        fields=[
            {"qid": "q-state", "label": "State", "kind": "select",
             "options": [{"value": "ca", "textContent": "California"}]},
            # `legend` so each button's own text is just "Yes"/"No", which is
            # what `guidedControlLabel` reads and what the model answers with.
            {"qid": "q-auth", "label": "Authorized", "kind": "radio",
             "legend": "Authorized", "options": ["Yes", "No"]},
        ],
        pairs=[
            {"qid": "q-state", "kind": "select", "answer": "California"},
            {"qid": "q-auth", "kind": "radio", "answer": "Yes"},
        ],
    )
    assert set(result["filled"]) == {"q-state", "q-auth"}
    for label in ("State", "Authorized"):
        assert _visited(_events(result, label)), _events(result, label)


def test_the_eeo_writers_take_the_gesture_too(tmp_path):
    """The voluntary-disclosure module writes its own select and radio limbs,
    so it is the FOURTH place the gesture has to exist — and the section a user
    is least likely to go back and re-check by hand, because it is the one they
    were never asked to fill in themselves.

    Nothing about the consent semantics moves here: this control is on screen
    at all only because the backend's standing consent said so, and the visit
    is the same two events every other control gets.
    """
    result = run_profile_fill(
        tmp_path,
        fields=[{"label": "Gender", "kind": "select",
                 "options": [{"value": "f", "textContent": "Female"},
                             {"value": "m", "textContent": "Male"}]}],
        eeo_enabled=True,
        profile={"eeo": {"gender": "female"}},
    )
    assert result["values"]["Gender"] == "f"
    events = _events(result, "Gender")
    assert _visited(events), events
    assert events.index("focus:preventScroll") < events.index("change") < events.index("blur")


# THE DEFERRED BLUR IS PINNED NEXT DOOR, deliberately not re-pinned here.
# `tests/test_extension_split_date.py` owns the one place a blur is withheld on
# purpose — `test_a_section_is_not_blurred_while_its_sibling_is_empty` and
# `test_the_last_date_on_the_page_is_still_blurred` are the two halves — and a
# second copy of that assertion in this file would be a second answer to a
# question that already has one. The visit seam above touches no text write, so
# `commitValue`'s `blur: false` and `pendingBlur` are reached exactly as before.
