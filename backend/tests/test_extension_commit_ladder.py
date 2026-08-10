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
    assert _outcomes(result)["First Name"] == "not_stuck"


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
