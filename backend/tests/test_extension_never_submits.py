"""The extension never submits a form — design §8.1, engine half.

It is the first entry on the design's hard-constraints list and the promise the
widget prints on its own surface, and until now it was held up by one clause of
one expression: `isFormJunk` excludes `submit/button/image/reset` alongside
hidden, disabled and readonly controls. Nothing tested it. Narrowing that list
while chasing an unrelated bug — a readonly ATS field that ought to be filled,
say — would have taken the whole promise with it, silently, on a page where the
next thing the writer does is press keys into controls.

THIS FILE IS THE WHOLE OF THE PROMISE NOW. It used to be half: the floating
card held a selector naming every submit control on the page (for its collision
observer) and was pinned to only ever READ through it. R-C deleted the card and
the only code that knows what a submit control looks like is the engine again,
so the rule has one home and this file is it — the fill loop does not write,
click, or even focus one.

The shapes are declared as FIELD SPECS rather than captured markup, per the
corpus convention: the fixture PII guard rejects raw HTML outright, and a submit
control has no signature worth reconstructing anyway. What matters is the `type`,
which is the only thing `isFormJunk` reads.
"""

from tests.extension_harness import outcome_pairs, run_profile_fill

_PROFILE = {"personal": {"first_name": "Jordan", "last_name": "Example"}}

# Every type `isFormJunk` names for this reason, with a plausible label each.
# "Add another employer" is the one a user most wants pressed — the repeated
# blocks the writer cannot create for itself — and is exactly why the rule is
# structural rather than a judgement call about which buttons are safe.
_SUBMIT_SHAPED = [
    {"label": "Submit application", "kind": "text", "type": "submit"},
    {"label": "Add another employer", "kind": "text", "type": "button"},
    {"label": "Clear form", "kind": "text", "type": "reset"},
    {"label": "Search", "kind": "text", "type": "image"},
]


def test_no_submit_shaped_control_is_written_clicked_or_reported(tmp_path):
    """All four types, beside a field that DOES get filled.

    The live field is not decoration: without it a broken run and a correct run
    look identical, because "nothing was touched" is also what a fill that never
    reached the loop reports.
    """
    result = run_profile_fill(
        tmp_path,
        profile=_PROFILE,
        fields=[{"label": "First Name", "kind": "text"}, *_SUBMIT_SHAPED],
    )

    # The loop ran.
    assert result["values"]["First Name"] == "Jordan"

    for field in _SUBMIT_SHAPED:
        label = field["label"]
        # Not written…
        assert result["values"][label] == "", label
        # …and not activated, or even focused. `events` records click(),
        # focus() and blur() distinctly, so this covers "clicked" outright
        # rather than inferring it from an unchanged value — a click on a
        # submit control changes no value at all, which is the whole hazard.
        assert result["events"][label] == [], label

    reported = {
        entry["label"]
        for key in ("filled", "eeoFilled", "corrected", "already")
        for entry in result.get(key, [])
    }
    assert reported == {"first name"}
    # Excluded before labelling, so they never reach telemetry either — a
    # submit control has no field signature worth collecting, and counting one
    # would inflate the coverage totals with controls no rule may ever write.
    assert outcome_pairs(result) == [("First Name", "filled")]


def test_a_submit_control_a_rule_would_match_is_still_untouched(tmp_path):
    """The sharp case: the exclusion is structural, not label-driven.

    This control is labelled "First Name", which a live rule matches and holds
    an answer for. The label is chosen to collide on purpose — not because a
    page renders a submit button that way, but because it is what makes the
    assertion bite: if `isFormJunk` stops naming `submit`, this is a control the
    writer would immediately focus and type into. With a label no rule matches,
    the test would pass on `no_rule` and prove nothing.
    """
    result = run_profile_fill(
        tmp_path,
        profile=_PROFILE,
        fields=[
            {"label": "Last Name", "kind": "text"},
            {"label": "First Name", "kind": "text", "type": "submit"},
        ],
    )

    assert result["values"]["Last Name"] == "Example"
    assert result["values"]["First Name"] == ""
    assert result["events"]["First Name"] == []
    assert outcome_pairs(result) == [("Last Name", "filled")]
