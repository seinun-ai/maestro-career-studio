"""The FILL stage: the pass, the report, the pause row, the QnA drawer.

THREE SECTIONS OF ONE SUBJECT, which is why they are one file. `fillBody`
renders all of it — the mode control, the three progress rows gated on the
three sources that arrive independently, the still-open list with its inline
pause rows, and the composer at the foot — so a test about a pause row and a
test about a progress row are two claims about the same render.

 1. the STAGE — the mode control, the progress rows, the residue list, and
    `startFill`'s busy, failure, partial, race and finished paths;
 2. the PAUSE ROW — the inline answer, where it is LEARNED (the router as a
    table over the engine's own patterns), the two refusals that render no
    input at all, and submit's failure, race and finished paths;
 3. the QnA DRAWER — `sanitizeAnswer`'s table at its shared home, the
    composer's wire (the card's body, one question), the essay handoff out of
    the still-open list, the clipboard, and the ask's busy and race paths.

THE APPARATUS IS `tests/extension_panel_harness.py` — the faked `chrome`, the
faked document tree, the DOM readers and the spec starters every stage driver
builds on. It is a MODULE rather than a copy per file because a fake that has
to agree with panel.js about what a render leaves behind must not exist five
times; read its header before adding to it.

THE MAP IS `test_extension_panel.py`'s docstring, which lists every file this
subject is now spread across. A section that is not on that list is a section
the next author will not find.
"""
import json
import re

import pytest

from tests.extension_fixtures import (
    LIGHTNING_APPLY_URL,
    LIGHTNING_TENANT,
    entry,
)
from tests.extension_harness import run_node, run_profile_fill
from tests.extension_panel_harness import (
    BASE_RESUMES,
    DECISIONS_JS,
    EXTENSION,
    OTHER_URL,
    PANEL_SOURCE,
    SCORES,
    SETTINGS_REPLY,
    _armed_entry,
    _by_class,
    _jump_label,
    _PANEL_FAKES_JS,
    _rail_rows,
    _reply,
    _rows,
    _text,
    _walk,
)

# Read for ONE assertion, the drawer's: the injected copy of `sanitizeAnswer`
# that `fillAnswersByQid` has to carry, pinned identical to the shared one.
OPEN_QUESTIONS_JS = (
    EXTENSION / "content" / "open-questions.js").read_text(encoding="utf-8")


# ---------- the Fill stage: choose the pass, run it, read what it did -------
#
# THE RUN IS THE STAGE. Everything under this row is either the choice the user
# makes before it (rules only, or rules plus the model) or the report of what
# one produced — and the report is the honest half: a fill that answered eleven
# fields and left three open has to say both numbers, because the category's
# guidance for a wrong value is to eyeball the form.
#
# The fixtures arrive at Fill through the base-as-is SHORTCUT — a remembered
# arming plus a form on the page — because it is the entry that needs no clicks
# to reach and no application to exist. The library ladder's route to the same
# stage (job → scored → picked → tailored) is the Resume section's business and
# lands on this identical body.

_FILL_STAGE_DRIVER_JS = _PANEL_FAKES_JS + r"""
loadModules();
const segments = () => withClass(REGIONS.rail, "seg").flatMap((seg) => seg.children);
// Pressed BY LABEL, the fork's rule: naming a control that is not on screen
// throws rather than passing quietly, because "the body did not render it" and
// "the click did nothing" are different failures.
const press = (label) => {
  const found = segments().find((one) => one.textContent === label);
  if (!found) throw new Error(`no fill mode reads "${label}"`);
  found.click();
};
const residueRows = () =>
  withClass(REGIONS.rail, "resid").flatMap((list) => list.children)
    .map((item) => item.children[0]);
// One pause row's three controls, found by the ids the body stamps rather than
// by position: the box holds an input, an optional option list, an optional
// learn label and a button, so an index would move the day a row grows a line.
//
// `findById` IS THE HARNESS'S NOW. It had two copies in this file — this one
// and the drawer's, forty rows apart and identical — and the panel's own focus
// restore needs the same search, so it moved to `_PANEL_FAKES_JS` under the
// rule its header states: a helper that grows a second caller lives with the
// apparatus. Nothing about the search changed.
const pauseRow = (qid) => {
  const input = findById(REGIONS.rail, `answer-${qid}`);
  if (!input) throw new Error(`no pause row for ${qid}`);
  const box = withClass(REGIONS.rail, "needs")
    .find((one) => one.children.includes(input));
  return {
    input,
    learn: findById(box, `learn-${qid}`),
    save: withClass(box, "save")[0],
  };
};
/** Answer one row the way a user does: type, maybe untick, press.
 *
 * The typing is a real `input` dispatch rather than a store poke, because the
 * characters living in the store instead of in the element is the thing that
 * makes a pause row survive a repaint — a test that wrote `card.answers`
 * directly would pass with that wiring removed. */
/** `answerRow` where the row may legitimately be gone.
 *
 * The two-row driver presses the second row twice — once while the first row's
 * learn is open, once after it lands — because WHICH of those gets through is
 * the behaviour under test rather than a fact the fixture knows. A hard
 * `answerRow` would crash the run on the difference, and a mutation would then
 * be killed by a harness error instead of by the assertion about the profile,
 * which is a weaker signal wearing a passing test's clothes. */
const tryAnswerRow = (spec_) => {
  const input = findById(REGIONS.rail, `answer-${spec_.qid}`);
  if (!input) return false;
  answerRow(spec_);
  return true;
};
const answerRow = ({ qid, text, learn, via }) => {
  const row = pauseRow(qid);
  if (text !== undefined) {
    row.input.value = text;
    row.input.dispatch("input");
  }
  if (learn !== undefined) {
    row.learn.checked = learn;
    row.learn.dispatch("change", { target: { checked: learn } });
  }
  // The two ways to send one answer. `via: "enter"` presses the key in the box
  // rather than the button beside it, which is the path a browser gives no
  // input outside a <form> for free — and nothing on this surface is in one.
  if (via === "enter") row.input.dispatch("keydown", { key: "Enter" });
  else row.save.click();
};

main(async () => {
  await settle();
  const loaded = regions();
  if (spec.mode !== undefined) {
    press(spec.mode);
    await settle();
  }
  const chosen = regions();
  let clicked = null;
  if (spec.start === true) {
    withClass(REGIONS.foot, "cta")[0].click();
    // Synchronous, and deliberately: the action sets `busy` and paints before
    // its first await, so this is the surface as the user sees it while the
    // fill is open.
    clicked = regions();
    await settle();
    // …and the user is free to leave while the run is still on the wire.
    if (spec.switchTo !== undefined) {
      await onActivated({ tabId: spec.switchTo });
      await settle();
    }
    release();
    await settle();
  }
  // A SECOND PRESS on the same page, which is the ordinary way a fill is
  // finished: the first run leaves fields open, the user answers some by hand,
  // and presses again. The page has MOVED between the two — that is the whole
  // point — so the fixture's replies are mutated in place before the second
  // click rather than being one canned world for both runs. `spec.api` and
  // `spec.frames` are read at call time by the fakes, so assigning over them
  // is what "the page is different now" looks like from here.
  let first = null;
  let againClicked = null;
  if (spec.again !== undefined) {
    first = regions();
    Object.assign(spec.frames, spec.again.frames ?? {});
    Object.assign(spec.api, spec.again.api ?? {});
    // A run that FINISHED took the rail to Track and the Start fill with it,
    // which is a wizard's second page in one line: the form is still in front
    // of the user and the panel has ticked the step. So the user REOPENS the
    // ticked Fill row, and the primary comes back with the body.
    if (spec.again.reopen === true) {
      const door = findById(REGIONS.rail, "stg-open-fill");
      if (!door) throw new Error("the ticked Fill row has no way back into it");
      door.click();
      await settle();
    }
    withClass(REGIONS.foot, "cta")[0].click();
    // Synchronous, like the first run's `clicked`: the action paints `busy`
    // before its first await, so this is the rail as the user sees it while the
    // re-run is open.
    againClicked = regions();
    await settle();
    release();
    await settle();
  }
  if (spec.scrollRow !== undefined) {
    residueRows()[spec.scrollRow].click();
    await settle();
  }
  // THE PAUSE ROW. Answered after the run has settled, which is the only state
  // in which one exists — the rows are rendered from the residue the run
  // reported.
  let answered = null;
  let answering = null;
  // Typed and NOT submitted, with something unrelated landing in between: the
  // draft has to live in the store, because the render that lands rebuilds
  // every element in the rail including the one being typed into.
  if (spec.typeOnly !== undefined) {
    const row = pauseRow(spec.typeOnly.qid);
    row.input.value = spec.typeOnly.text;
    row.input.dispatch("input");
    release();
    await settle();
  }
  // TWO ROWS, one after the other, with the profile round trip HELD. The
  // second press lands while the first row's learn is still open, which is
  // exactly the moment the serialization rule is about: the page write has
  // returned and the profile write has not.
  let midLearn = null;
  let afterPoke = null;
  if (spec.answerBoth !== undefined) {
    answerRow(spec.answerBoth[0]);
    await settle();
    midLearn = regions();
    // Poked WHILE the learn is open: a mode segment repaints the rail, and the
    // footer's primary starts a whole second fill. Both must be refused for as
    // long as anything this action is doing is still on the wire.
    if (spec.pokeDuringLearn === true) {
      // NOTE the fake dispatches a click at a DISABLED control, where a browser
      // swallows it (this harness models no default actions — see its own list
      // of what it does not do). That is what makes the poke useful rather than
      // circular: the segment handler runs, the rail REPAINTS, and the repaint
      // is the thing the bug rode in on.
      segments()[0].click();
      await settle();
      withClass(REGIONS.foot, "cta")[0].click();
      await settle();
      afterPoke = regions();
    }
    tryAnswerRow(spec.answerBoth[1]);
    await settle();
    release();
    await settle();
    // …and once the first has landed the second is free to go, which is the
    // half that keeps this from passing by refusing everything. Skipped if the
    // press above already got through — that is a state difference, not a
    // broken run, and it is exactly the state a regression produces.
    tryAnswerRow(spec.answerBoth[1]);
    await settle();
    release();
    await settle();
  }
  if (spec.answer !== undefined) {
    answerRow(spec.answer);
    // Synchronous: the action paints `busy` before its first await, so this is
    // the row as the user sees it while the write is open.
    answering = regions();
    // A SECOND press WHILE THE FIRST IS STILL OPEN, which is what a user does
    // when a held write looks like it did nothing. After the release the row is
    // gone, so pressing then would be pressing a control that is not there —
    // a different (and uninteresting) test.
    if (spec.answerAgain === true) answerRow(spec.answer);
    await settle();
    // …and the user is free to leave while the write, or the learn behind it,
    // is still on the wire.
    if (spec.switchAfterAnswer !== undefined) {
      await onActivated({ tabId: spec.switchAfterAnswer });
      await settle();
    }
    release();
    await settle();
    answered = regions();
  }
  emit({ loaded, chosen, clicked, first, againClicked, answering, answered,
         midLearn, afterPoke,
         settled: regions(), sent, writes, syncWrites, broadcasts,
         profile: PROFILE,
         modes: segments().map((one) => one.textContent) });
});
"""

# What `/api/autofill/context` answers: a profile, one employment block, skills,
# and the standing EEO consent record. The panel decides none of it — the two
# EEO flags are the backend's, which is the whole of design §R1's rule.
FILL_CONTEXT = {
    "profile": {"first_name": "Ada", "email": "ada@example.test"},
    "employment": [{"employer": "Lightning AI", "title": "Research Engineer"}],
    "skills": ["python", "pytorch"],
    "eeo_consent": {"enabled": False, "consent_forms": False,
                    "acknowledged_at": None, "policy_version": ""},
}
# What the rule pass's fan-out reports back, in `fillFormFromProfile`'s shape —
# which is what `reconcileFill` buckets. Two filled, one already holding the
# right value, and one control the write did not stick to.
PROFILE_FRAMES = [{"frameId": 0, "result": {
    "filled": [{"label": "first name", "value": "Ada"},
               {"label": "email", "value": "ada@example.test"}],
    "corrected": [], "eeoFilled": [], "already": [{"label": "country"}],
    "seen": 4,
    "observations": [
        {"label": "first name", "kind": "text", "outcome": "filled", "rule_id": "first_name"},
        {"label": "email", "kind": "text", "outcome": "filled", "rule_id": "email"},
        {"label": "phone", "kind": "text", "outcome": "not_stuck", "rule_id": "phone"},
        {"label": "referral", "kind": "text", "outcome": "no_rule", "rule_id": None},
    ],
}}]
# What the collector finds after the rules have run: two ChooseFields, one
# essay, and a retryable the rules knew the answer to but could not land.
COLLECT_FRAMES = [{"frameId": 0, "result": {
    "host": "job-boards.greenhouse.io",
    "questions": [
        {"qid": "q1", "label": "preferred shift", "kind": "select",
         "options": ["Day", "Night"]},
        {"qid": "q2", "label": "how did you hear about us?", "kind": "select",
         "options": ["LinkedIn", "A friend"]},
        {"qid": "q3", "label": "why do you want this role?", "kind": "textarea",
         "options": []},
    ],
    "retryables": [{"qid": "r1", "label": "country", "kind": "combobox",
                    "known_value": "United States"}],
}}]
CHOOSE_REPLY = _reply({"choices": {
    "q1": {"answer": "Day", "reason": "matched"},
    "q2": {"answer": None, "reason": "abstained"},
}})
# A page the run can FINISH: both questions answered, no essay, so nothing is
# left for the user. It is a separate fixture rather than the default because
# the ordinary ATS page is the one above — an abstain and an essay are what a
# form of any size produces — and the two states are read differently by the
# rail: only the finished one may tick Fill off.
CLEAN_COLLECT_FRAMES = [{"frameId": 0, "result": {
    **COLLECT_FRAMES[0]["result"],
    "questions": [q for q in COLLECT_FRAMES[0]["result"]["questions"]
                  if q["kind"] != "textarea"],
}}]
CLEAN_CHOOSE_REPLY = _reply({"choices": {
    "q1": {"answer": "Day", "reason": "matched"},
    "q2": {"answer": "LinkedIn", "reason": "matched"},
}})


def _fill(tmp_path, driver=_FILL_STAGE_DRIVER_JS, **spec):
    """Boot on an apply page with a base-as-is arming remembered — the Fill
    stage, reached the way a user reaches it from the previous wizard step.

    `driver` is a parameter so the QnA drawer's own section, below, can reach
    the same stage
    without a second copy of these four fixture dicts. The world is what this
    function knows; what is DONE to it is the driver's, and the two are
    genuinely separate — the drawer's driver presses controls the fill driver
    has never heard of, and both need an apply page with a form on it.
    """
    spec.setdefault("tabs", [{"id": 7, "url": LIGHTNING_APPLY_URL}])
    spec.setdefault("stored", {"widget.session": _armed_entry()})
    replies = {"read_settings": SETTINGS_REPLY,
               "panel_frame0": _reply({"tier": "B", "form": True, "score": 2}),
               "panel_prepare": _reply({"injected": True}),
               "telemetry": _reply({"posted": 0})}
    replies.update(spec.pop("replies", {}))
    api = {"lightningai": _reply({"match": "none", "job": None, "application": None}),
           "/api/autofill/context": _reply(FILL_CONTEXT),
           "/api/autofill/choose": CHOOSE_REPLY,
           "/api/base-resumes": _reply(BASE_RESUMES),
           "/api/ats-scores": _reply(SCORES)}
    api.update(spec.pop("api", {}))
    frames = {"profile_fill": PROFILE_FRAMES,
              "collect_open_questions": COLLECT_FRAMES,
              "guided_write": True}
    frames.update(spec.pop("frames", {}))
    return run_node(driver,
                    {**spec, "api": api, "replies": replies, "frames": frames},
                    tmp_path, source=PANEL_SOURCE)


def _rows_of(region):
    """Every progress row, as `(name, counts)` — what the user reads across."""
    return [(_text(row["children"][1]), _text(row["children"][2]))
            for row in _by_class(region, "prog")]


def _marks(region):
    return [_by_class(row, "st")[0]["text"] for row in _by_class(region, "prog")]


def _choose_calls(out):
    return [msg for msg in out["sent"] if msg["type"] == "api"
            and "/api/autofill/choose" in msg["path"]]


def _broadcast_types(out):
    return [msg["message"]["type"] for msg in out["broadcasts"]]


def _page_message(out, kind):
    """The ONE fan-out message of `kind` the run sent, asserting there is one.

    A helper rather than a comprehension at each site: eight assertions across
    this section reach for a single broadcast by type, and the filtered
    comprehension that does it is both the duplication and — repeated three
    times inside one test — most of that test's branching.
    """
    found = [msg for msg in out["broadcasts"] if msg["message"]["type"] == kind]
    assert len(found) == 1, f"expected one {kind} broadcast, got {len(found)}"
    return found[0]


def test_before_a_fill_the_stage_offers_a_choice_and_reports_nothing(tmp_path):
    """A row reading "0 filled" over a form nobody has touched is the panel
    narrating a fill that has not happened.

    So the body before a run is the mode control and one sentence about what
    the button will do — and the button is the FOOTER's, which is where every
    primary on this surface lives. The sentence is the mode's, because the two
    passes differ in the thing a user would want to know before pressing:
    whether anything leaves the browser.
    """
    out = _fill(tmp_path)
    rows = _rows(_rail_rows({"regions": out["loaded"]}))
    assert rows["fill"]["state"] == "active"
    assert out["modes"] == ["Rules only", "Rules + AI assist"]
    assert _by_class(out["loaded"]["rail"], "prog") == []
    assert _by_class(out["loaded"]["rail"], "resid") == []
    assert _by_class(out["loaded"]["rail"], "sub")[0]["text"].endswith(
        "then asks for the rest. Identity fields are never sent.")
    # One primary, in the one place, and it says what it starts.
    [cta] = _by_class(out["loaded"]["foot"], "cta")
    assert cta["text"] == "Start fill"
    assert cta["disabled"] is False
    # Nothing has been injected and nothing has been asked of the page: the
    # panel prepares a tab when the user asks for something that needs it.
    assert [msg for msg in out["sent"] if msg["type"] == "panel_prepare"] == []


def test_the_stage_on_a_page_with_no_form_says_where_filling_happens(tmp_path):
    """THE OTHER WAY INTO THIS STAGE, and until 2026-08-19 it was silent.

    The claim ("use base as-is") is a page-and-session fact and it answers the
    Resume stage's question wherever it is made — so a user who armed a base on
    a POSTING page stands here, on the one step with work left in it, in front
    of a page that cannot host that work. The body's whole job is to say so and
    to say what to do instead: open the employer's Apply page, where filling
    starts.

    THREE THINGS ARE WITHHELD, and each would be a control that cannot do what
    it says:

    - the primary. THE PROBE: a Start fill offered here runs a pass over a page
      with no fields in it and reports "0 filled" — which is the failure the
      old `hasForm` stage gate was really about, kept at the button where it
      belongs;
    - the mode segment, which chooses between two passes that cannot run;
    - the shortcut's "Ready to autofill from your base resume", a promise about
      a page that has no form on it.

    THE DRAWER STAYS, because it is not part of the run: a question pasted from
    the posting in front of the user is exactly what it is for, and a JD page is
    where a user has one.
    """
    out = _fill(tmp_path, replies={"panel_frame0": _reply(
        {"tier": "A", "form": False, "score": 0})})
    rail = out["loaded"]["rail"]
    assert _rows(_rail_rows({"regions": out["loaded"]}))["fill"]["state"] == "active"
    assert _by_class(rail, "sub")[0]["text"] == (
        "No application form on this page — open the employer's Apply page; "
        "filling starts there.")
    assert _by_class(out["loaded"]["foot"], "cta") == []
    assert _by_class(rail, "seg") == []
    assert "Ready to autofill" not in _text(out["loaded"]["identity"])
    # …and nothing is reported about a run that has not happened.
    assert _by_class(rail, "prog") == []
    assert _by_class(rail, "resid") == []
    # The composer is still offered, closed, with its one line about what it is.
    [drawer] = _by_class(rail, "qna")
    assert "Paste any question" in _text(drawer)


def test_a_form_that_arrives_late_gives_the_stage_its_primary_back(tmp_path):
    """THE LADDER'S SECOND LOOK, from the Fill stage's side.

    An SPA that had not rendered its form when the panel bound to it answers
    yes a second later. The user has not moved — the stage never read the form
    verdict — so what the late yes changes is what this step OFFERS: the
    sentence becomes the mode control and the footer gets Start fill.

    THE PROBE: a late `form: true` that failed to reach the render leaves a
    user standing over a filled-in form being told there is no form on the
    page, with no way to run it.
    """
    out = _fill(tmp_path, page={"detect_page": [
        _reply({"tier": "A", "form": False, "score": 0}),
        _reply({"tier": "B", "form": True, "score": 2})]})
    rail = out["loaded"]["rail"]
    assert _rows(_rail_rows({"regions": out["loaded"]}))["fill"]["state"] == "active"
    assert out["modes"] == ["Rules only", "Rules + AI assist"]
    [cta] = _by_class(out["loaded"]["foot"], "cta")
    assert cta["text"] == "Start fill"
    assert cta["disabled"] is False
    assert "No application form on this page" not in _text(rail)


def test_the_default_mode_is_assist_and_the_choice_is_remembered_for_the_profile(tmp_path):
    """The mode is a SETTING, not a page fact.

    It arrives through `read_settings` — the one settings path, so sw.js's
    `DEFAULTS` stays the single place a default lives — and it is written back
    to `chrome.storage.sync`, which is the store that follows the profile. A
    user who turns the model off wants it off on the next posting and in the
    next browser, not until their next tab switch.
    """
    out = _fill(tmp_path, mode="Rules only")
    [rules, assist] = _by_class(out["loaded"]["rail"], "seg")[0]["children"]
    # Before: assist, from the settings default, and said in words as well as
    # in the tint — "which pass is about to run" must not have to be inferred
    # from a background colour.
    assert (rules["class"], assist["class"]) == ("", "on")
    assert assist["attrs"]["aria-checked"] == "true"
    assert rules["attrs"]["aria-checked"] == "false"
    # After: the other one, and the sentence under it changes with it.
    [rules, assist] = _by_class(out["chosen"]["rail"], "seg")[0]["children"]
    assert (rules["class"], assist["class"]) == ("on", "")
    assert _by_class(out["chosen"]["rail"], "sub")[0]["text"] == (
        "Fills what your profile answers for. Nothing is sent to a model.")
    # SYNC, not local: the session key and a preference are different kinds of
    # thing, and the panel writes them to different stores.
    assert out["syncWrites"] == [{"fillMode": "rules"}]
    assert out["writes"] == []


def test_a_stored_rules_only_choice_comes_back_as_the_mode(tmp_path):
    """The read half, through the settings message rather than a second copy
    of the key. Anything but `"rules"` is the assist pass — a missing key, or a
    value from an older build, is not a user who chose the narrower run."""
    out = _fill(tmp_path, replies={"read_settings": {"ok": True, "data": {
        **SETTINGS_REPLY["data"], "fillMode": "rules"}}})
    [rules, assist] = _by_class(out["loaded"]["rail"], "seg")[0]["children"]
    assert (rules["class"], assist["class"]) == ("on", "")


def test_start_fill_runs_the_rules_then_the_model_and_reports_both(tmp_path):
    """The whole pass, end to end, in the order the runner sequences it.

    `panel_prepare` FIRST, because it is the sanctioned injection moment: a
    click is a user gesture, and a tab that was already open when the extension
    last reloaded has no content scripts at all until this runs. Then the rule
    pass through the same `profile_fill` fan-out the card uses, then one
    `/choose` batch for the remainder, then ONE `guided_write` for everything
    that has an answer.
    """
    out = _fill(tmp_path, start=True)
    # The injection is the first thing the click does, and it happens once.
    assert [msg["tabId"] for msg in out["sent"]
            if msg["type"] == "panel_prepare"] == [7]
    # The page conversation, in order. One write, always: the single bounded
    # retry of a control that will not take a value is the ENGINE's.
    assert _broadcast_types(out) == [
        "profile_fill", "collect_open_questions", "guided_write"]
    # The rule pass carries the backend's own consent flags and nothing local.
    rules = _page_message(out, "profile_fill")["message"]
    assert rules["eeoEnabled"] is False
    assert rules["consentForms"] is False
    assert rules["skills"] == ["python", "pytorch"]
    # The retryable leads the write and never reaches the model: a value a rule
    # already knows is not the model's to answer.
    write = _page_message(out, "guided_write")["message"]
    assert [pair["qid"] for pair in write["pairs"]] == ["r1", "q1"]
    posted = json.dumps(_choose_calls(out))
    assert "United States" not in posted
    assert "r1" not in posted
    # …and the essay is on neither list: `/api/qa` is a different feature.
    assert "q3" not in posted


def test_the_progress_rows_are_the_runs_own_report(tmp_path):
    """Three rows, and every number in them comes off THIS run.

    The profile row is `reconcileFill`'s buckets — the shared table both
    surfaces read, so nothing is re-derived here. The questions row is the
    engine's answered qids MINUS the ones the runner residued, which is the
    run's own reconciliation rather than a second reading of the outcome
    vocabulary. The disclosures row is the backend's consent and nothing else.
    """
    out = _fill(tmp_path, start=True)
    settled = out["settled"]
    assert _rows_of(settled["rail"]) == [
        # filled + already + the one that would not stick, each its own count:
        # "0 filled" over a visibly full form was a lie on a re-run.
        ("Profile fields", "2 filled · 1 already filled · 1 didn’t stick"),
        # r1 and q1 were written; q2 abstained and q3 is an essay, so two are
        # still open.
        ("Application questions", "2 filled · 2 need you"),
        ("Voluntary disclosures", "skipped — EEO off"),
    ]
    # The marks carry the state in WORDS as well, because an emoji reaches
    # nobody using a screen reader.
    assert _marks(settled["rail"]) == ["🟡", "🟡", "⏸"]
    assert [row["children"][0]["attrs"]["aria-label"]
            for row in _by_class(settled["rail"], "prog")] == [
        "needs you", "needs you", "skipped"]
    # And the still-open list is the residue plus the essay, each row naming
    # the field it jumps to.
    # The JUMP LABEL specifically — since Task 13 an answerable row also carries
    # a pause box, and `_text` over the whole `<li>` would fold the input's
    # option list and buttons into the name of the field.
    assert [_jump_label(item) for item in
            _by_class(settled["rail"], "resid")[0]["children"]] == [
        "how did you hear about us?", "why do you want this role? · written answer"]
    [note] = _by_class(settled["foot"], "note")
    assert note["text"] == "2 fields still need you."


def test_the_progress_rows_move_with_what_the_writer_actually_did(tmp_path):
    """The other half of "the run's own report": change what the ENGINE says
    and the rows change with it.

    A control the value did not stick to is residue, never a rewrite — the
    runner decided that — so it leaves the filled count and joins the list.
    Pinned as a second scenario rather than as a source read, because the way
    this breaks is a body that counts `writeResults.length` and calls it filled.
    """
    out = _fill(tmp_path, start=True, frames={"guided_write": {"q1": "not_stuck"}})
    rows = dict(_rows_of(out["settled"]["rail"]))
    assert rows["Application questions"] == "1 filled · 3 need you"
    # The runner's own order — the abstains it collected first, then the writes
    # that did not stick — and the essays after both, because they are a
    # different list joined at the render.
    assert [_jump_label(item) for item in
            _by_class(out["settled"]["rail"], "resid")[0]["children"]] == [
        "how did you hear about us?", "preferred shift",
        "why do you want this role? · written answer"]


def test_rules_only_asks_the_model_nothing_at_all(tmp_path):
    """THE BEHAVIOURAL PIN on the mode control, and it is behavioural for a
    reason: `aiAssist: mode === "assist"` is one expression, it fails silently
    in both directions, and a source pin would pass on an inverted one.

    So the assertion is what a rules-only run DOES: zero `/choose` calls. The
    residue is then everything the rules could not answer, which is the honest
    report of a narrower pass rather than a shorter list that would read as a
    better result.
    """
    rules_only = _fill(tmp_path, mode="Rules only", start=True)
    assert _choose_calls(rules_only) == []
    # Nothing was asked, so nothing was answered: only the retryable — whose
    # value a RULE knew — is written, and all three questions are open.
    write = _page_message(rules_only, "guided_write")["message"]
    assert [pair["qid"] for pair in write["pairs"]] == ["r1"]
    assert dict(_rows_of(rules_only["settled"]["rail"]))[
        "Application questions"] == "1 filled · 3 need you"

    # …and the same fixture with the default mode does ask, which is what makes
    # the emptiness above a decision rather than a broken wire.
    assisted = _fill(tmp_path, start=True)
    assert len(_choose_calls(assisted)) == 1


def test_the_eeo_row_says_what_the_backend_consented_to_and_never_a_local_toggle(tmp_path):
    """THREE consent states, three different sentences.

    Granted is a count. Withheld is "skipped — EEO off", which explains a
    silence that would otherwise read as a fill that missed a whole section.
    And an endpoint that said NOTHING about consent is "not asked" — reporting
    that as "off" would be this surface deciding a question design §R1 says it
    may not.

    The panel has no control that could change any of it, which is the point:
    the only opt-in that may turn protected-characteristic fill on is the
    backend's standing record.
    """
    granted = _fill(tmp_path, start=True, api={"/api/autofill/context": _reply({
        **FILL_CONTEXT,
        "eeo_consent": {"enabled": True, "consent_forms": True,
                        "acknowledged_at": "2026-08-01T00:00:00Z",
                        "policy_version": "1"}})},
        frames={"profile_fill": [{"frameId": 0, "result": {
            **PROFILE_FRAMES[0]["result"],
            "eeoFilled": [{"label": "gender"}, {"label": "veteran status"}]}}]})
    assert dict(_rows_of(granted["settled"]["rail"]))[
        "Voluntary disclosures"] == "2 filled"
    # …and the consent reached the ENGINE as two separate permissions, because
    # disclosing a protected characteristic and ticking the application's own
    # agreement boxes are different things to be asked for.
    rules = _page_message(granted, "profile_fill")["message"]
    assert (rules["eeoEnabled"], rules["consentForms"]) == (True, True)

    silent = _fill(tmp_path, start=True, api={"/api/autofill/context": _reply(
        {k: v for k, v in FILL_CONTEXT.items() if k != "eeo_consent"})})
    assert dict(_rows_of(silent["settled"]["rail"]))[
        "Voluntary disclosures"] == "not asked"
    rules = _page_message(silent, "profile_fill")["message"]
    assert (rules["eeoEnabled"], rules["consentForms"]) == (False, False)


def test_a_residue_row_jumps_to_its_field_and_carries_only_the_qid(tmp_path):
    """The row is a jump, and the jump is a fan-out.

    The control can be in the application's subframe — which is where
    Greenhouse and Lever put the whole form — so frame 0 is the wrong door.
    What travels is the qid: our own token, stamped by our own collector on a
    frame that already passed the fan-out gate, so a frame that never answered
    a collect holds none and scrolls nothing. A label or a value added here
    would be user data delivered to every ad iframe on the posting.
    """
    out = _fill(tmp_path, start=True, scrollRow=0)
    jump = _page_message(out, "scroll_to_field")
    assert jump["message"] == {"type": "scroll_to_field", "qid": "q2"}
    assert jump["tabId"] == 7


def test_the_primary_is_out_of_reach_while_the_fill_runs(tmp_path):
    """A fill is the longest thing this surface does and it walks a form the
    user is watching, so a second one started on top of the first is the worst
    version of the double-click this rule exists for. The mode control goes
    with it: the mode is read once, at the top of the run, so a segment pressed
    mid-fill would change the label and not the run."""
    out = _fill(tmp_path, start=True, hold=["/api/autofill/choose"])
    [cta] = _by_class(out["clicked"]["foot"], "cta")
    assert cta["disabled"] is True
    assert cta["class"] == "cta spin"
    assert [one["disabled"] for one in
            _by_class(out["clicked"]["rail"], "seg")[0]["children"]] == [True, True]


def test_a_fill_that_lands_after_you_switch_tabs_paints_nothing(tmp_path):
    """The generation rule, on the action that is most likely to meet it: a
    guided fill is four round trips deep, so a user switching tabs part-way
    through is the ORDINARY case here rather than the unlucky one.

    Nothing about tab A's form may reach tab B — not the counts, not the list
    of what is still open, and not the sentence.
    """
    out = _fill(tmp_path, start=True, hold=["/api/autofill/choose"], switchTo=42,
                tabUrls={"42": "chrome://settings"})
    settled = out["settled"]
    assert _by_class(settled["rail"], "prog") == []
    assert _by_class(settled["rail"], "resid") == []
    assert "still need you" not in _text(settled["foot"])
    assert "preferred shift" not in json.dumps(settled)
    # Nothing still spinning, either: `busy` belongs to the tab that asked.
    assert [n for n in _walk(settled["foot"]) if "spin" in str(n.get("class"))] == []
    # …and the arming was not written down against the settings tab.
    assert out["writes"] == []


def test_progress_from_a_fill_on_another_tab_never_paints_this_one(tmp_path):
    """`onProgress` SPECIFICALLY, because it is the one store-writing function
    in this feature that the surrounding guards do not cover.

    `duringAction` checks the generation on both of its limbs — but that is
    after the run RETURNS, and `onProgress` fires from INSIDE it, twice, at the
    exact moments the runner has something to hand over. So the callback
    carries the check itself.

    THE SWITCH IS TO THE NEXT STEP OF THE SAME WIZARD, and the test is vacuous
    without that. A settings tab is not on the Fill stage, so its rail has no
    Fill body and a late residue write would sit in the store painting nothing —
    measured: with the token check deleted, the settings-tab version of this
    test still passed. The tab that can SHOW the bug is one that is itself at
    Fill: same tenant, so the arming restores, a form on the page, and a body
    waiting to render a list. Without the check it renders the previous page's
    open questions as this page's.

    The choose wire is held until after the switch, which puts the second
    `onProgress` — the residue — strictly on the far side of it.
    """
    next_step = f"{LIGHTNING_APPLY_URL}/step2"
    out = _fill(tmp_path, start=True, hold=["/api/autofill/choose"], switchTo=42,
                tabUrls={"42": next_step})
    settled = out["settled"]
    # Tab B is at Fill and its body is the pre-run offer: a mode control, and
    # no report of a fill that happened somewhere else.
    assert _rows(_rail_rows({"regions": settled}))["fill"]["state"] == "active"
    assert len(_by_class(settled["rail"], "seg")) == 1
    assert _by_class(settled["rail"], "prog") == []
    assert _by_class(settled["rail"], "resid") == []
    # The essay phase fires BEFORE /choose, so it landed while tab A was still
    # bound and was cleared by the page change; the residue phase fires after,
    # and the token check is the only thing that can stop it.
    assert "why do you want this role?" not in json.dumps(settled)
    assert "how did you hear about us?" not in json.dumps(settled)


def test_a_collect_that_reaches_nobody_never_erases_the_rule_pass(tmp_path):
    """THE HONESTY GAP, and it was in this file's own fixture before it was
    caught.

    The fill is a SEQUENCE, so a throw at the collect leaves the rule pass's
    work standing — two of the user's fields are IN THE FORM. This test used to
    assert `prog == []` for exactly this fixture, which pinned the bug: the
    panel rendered no report at all and said "Can't reach this page. Reload the
    tab" about a page it had just written into. Reloading is the one action
    that throws that work away.

    So the report survives the failure, and the sentence names what actually
    failed. The unreachable claim is reserved for the run that reached nothing,
    which is the twin below.
    """
    out = _fill(tmp_path, start=True, frames={"collect_open_questions": [{"frameId": 0}]})
    settled = out["settled"]
    # The rule pass's rows are on screen, because the rule pass happened.
    assert _rows_of(settled["rail"]) == [
        ("Profile fields", "2 filled · 1 already filled · 1 didn’t stick"),
        ("Voluntary disclosures", "skipped — EEO off"),
    ]
    # …and NOT a questions row: the collect never ran, so a row reading
    # "0 filled" there would report zeros about a step that did not happen.
    assert "Application questions" not in _text(settled["rail"])
    [note] = _by_class(settled["foot"], "note")
    assert note["text"] == (
        "The rules ran; the page stopped answering before the questions could "
        "be collected. What they filled is below — reload the tab to finish "
        "the rest.")
    assert note["class"] == "note error"
    [cta] = _by_class(settled["foot"], "cta")
    assert cta["disabled"] is False
    # Still not finished, so still no claim: `touched` needs the run to have
    # left nothing open, and this one does not even know what is open.
    assert out["writes"] == []
    assert _rows(_rail_rows({"regions": settled}))["fill"]["state"] == "active"


# The rule pass of a SECOND run, reporting one field where the first reported
# four. Different on purpose: "run 2's rows" and "run 1's rows" have to be
# distinguishable, or a test that asserts rows survive cannot tell which run's
# survived.
SECOND_PROFILE_FRAMES = [{"frameId": 0, "result": {
    "filled": [{"label": "phone", "value": "555"}],
    "corrected": [], "eeoFilled": [], "already": [], "seen": 1,
    "observations": [{"label": "phone", "kind": "text", "outcome": "filled",
                      "rule_id": "phone"}],
}}]


def test_a_second_press_reports_the_second_run_and_never_the_first(tmp_path):
    """THE RE-RUN DEFECT, and it is the ordinary path rather than an edge.

    A first run leaves fields open, the user answers some by hand, and presses
    again — that is how a fill on a real form gets finished. Nothing cleared
    the report between the two: only `resetPageFacts` did, and that runs on a
    TAB CHANGE. So a second run whose collect failed painted run 2's counts
    over run 1's still-open list, offering to jump to fields the user had
    already answered, under a sentence saying "what they filled is below".

    Run 2 here fills one field and then loses the page, which is exactly the
    state that used to mix: its own profile row, its own failure sentence, and
    nothing at all from run 1.
    """
    out = _fill(tmp_path, start=True, again={
        "frames": {"profile_fill": SECOND_PROFILE_FRAMES,
                   "collect_open_questions": [{"frameId": 0}]}})
    # Run 1 did what it always does: four fields reconciled, two still open.
    assert dict(_rows_of(out["first"]["rail"]))["Profile fields"] == (
        "2 filled · 1 already filled · 1 didn’t stick")
    assert len(_by_class(out["first"]["rail"], "resid")[0]["children"]) == 2

    settled = out["settled"]
    # Run 2's rows, and only run 2's.
    assert _rows_of(settled["rail"]) == [
        ("Profile fields", "1 filled"),
        ("Voluntary disclosures", "skipped — EEO off"),
    ]
    # Run 1's still-open list is GONE rather than restated: it described a page
    # the user has been working on since, and the second run never collected.
    assert _by_class(settled["rail"], "resid") == []
    assert "preferred shift" not in json.dumps(settled)
    assert "why do you want this role?" not in json.dumps(settled)
    [note] = _by_class(settled["foot"], "note")
    assert note["text"].startswith("The rules ran;")


def test_a_finished_fill_is_reopened_for_the_wizards_next_page(tmp_path):
    """THE CASE THE REOPENABLE ROW EXISTS FOR, end to end.

    Run 1 finishes cleanly, so Fill is ticked and the rail moves to Track —
    which, before the row became a door, took the Start fill off the surface
    entirely: `first` below has NO primary in its footer while a wizard's next
    page of form sits in front of the user. The reopen brings the body and its
    primary back, and run 2 goes out at the page that is there now.

    THREE CLAIMS, and they are the three halves of "revisiting is not
    rewinding":

    - the report is run 2's alone. That is `startFill`'s existing per-run clear
      doing its job through a path it had not been driven from — the second
      press used to be possible only while Fill was still the ACTIVE stage.
    - the TICK stands. Page 1 was filled, and page 2 having questions does not
      unmake that: `touched` is written true and never false, so Fill stays done
      and Track stays where the user is.
    - the view survives its own run. Run 2 leaves fields open, which moves no
      stage (the tick is what `stageFor` reads), so `over` still matches and the
      body the user opened is the body the report lands in.
    """
    out = _fill(tmp_path, start=True,
                frames={"collect_open_questions": CLEAN_COLLECT_FRAMES},
                api={"/api/autofill/choose": CLEAN_CHOOSE_REPLY},
                again={"reopen": True,
                       "frames": {"profile_fill": SECOND_PROFILE_FRAMES,
                                  "collect_open_questions": COLLECT_FRAMES},
                       "api": {"/api/autofill/choose": CHOOSE_REPLY}})
    # Run 1 ticked the step and the rail moved on — the state this feature is
    # about, pinned before it is escaped.
    first_rows = _rows(_rail_rows({"regions": out["first"]}))
    assert first_rows["fill"]["state"] == "done"
    assert first_rows["track"]["state"] == "active"
    assert _by_class(out["first"]["foot"], "cta") == []
    assert "Fill finished" in _by_class(out["first"]["foot"], "note")[0]["text"]

    settled = out["settled"]
    # Run 2's rows, and only run 2's: one field where run 1 reported four.
    assert _rows_of(settled["rail"]) == [
        ("Profile fields", "1 filled"),
        ("Application questions", "2 filled · 2 need you"),
        ("Voluntary disclosures", "skipped — EEO off"),
    ]
    assert "2 filled · 1 already filled" not in _text(settled["rail"])
    # The still-open list is this page's, under a row that is still ticked.
    assert [_jump_label(item) for item in
            _by_class(settled["rail"], "resid")[0]["children"]] == [
        "how did you hear about us?", "why do you want this role? · written answer"]
    rows = _rows(_rail_rows({"regions": settled}))
    assert rows["fill"]["state"] == "done"
    assert rows["track"]["state"] == "active"
    # …and the report is INSIDE the reopened Fill row rather than under Track,
    # which is the whole difference between a body that follows the view and one
    # that follows the stage.
    [body] = _by_class(settled["rail"], "stg-body")
    assert body["id"] == "stg-body-fill"
    assert _by_class(settled["foot"], "note")[0]["text"] == "2 fields still need you."
    # WHILE THE RE-RUN IS OPEN the door is shut, `statusSegment`'s rule and its
    # reason: every control on this surface reads `busy`, and a reopen that
    # stayed live would swap the body out from under a fill the user is
    # watching — the progress they are waiting on, replaced by another stage's
    # step, with the run still writing into the page behind it.
    [door] = [node for node in _walk(out["againClicked"]["rail"])
              if node["id"] == "stg-open-fill"]
    assert door["disabled"] is True
    assert _by_class(out["againClicked"]["foot"], "cta")[0]["disabled"] is True


def test_a_second_run_whose_rules_never_ran_says_so(tmp_path):
    """THE DISCRIMINATOR, which the defect above falsified with its own
    predecessor.

    The catch in `startFill` reads `fill` to decide whether the rules reached
    THIS page on THIS run — and an uncleared `fill` from run 1 answered "yes"
    for a run whose rule pass threw before touching anything. The panel then
    suppressed the correct unreachable sentence and told the user their fields
    were filled and below.

    Run 2 here loses the backend AND the page: the context read fails, so the
    rule pass throws inside the runner's swallow, and the collect reaches
    nobody. Nothing ran, so the sentence is the one for a page nobody read.
    """
    out = _fill(tmp_path, start=True, again={
        "api": {"/api/autofill/context": {"ok": False, "error": "backend is down"}},
        "frames": {"collect_open_questions": [{"frameId": 0}]}})
    settled = out["settled"]
    [note] = _by_class(settled["foot"], "note")
    assert note["text"].startswith("Can't reach this page.")
    assert "The rules ran" not in note["text"]
    # …and nothing of either run is being reported.
    assert _by_class(settled["rail"], "prog") == []
    assert _by_class(settled["rail"], "resid") == []


def test_a_page_that_answers_nothing_at_all_is_the_only_unreachable_claim(tmp_path):
    """The twin, and the reason the sentence above is not simply the runner's.

    Here NO frame answers anything — not the rule pass's fan-out, not the
    collect — so there is no report to keep and nothing this panel may say
    about the page except that it never read it. That is the project's one
    sentence for the condition, the same one the card says, and reloading the
    tab IS the remedy this time.
    """
    out = _fill(tmp_path, start=True,
                frames={"profile_fill": [{"frameId": 0}],
                        "collect_open_questions": [{"frameId": 0}]})
    settled = out["settled"]
    [note] = _by_class(settled["foot"], "note")
    assert note["text"].startswith("Can't reach this page.")
    assert note["class"] == "note error"
    assert _by_class(settled["rail"], "prog") == []
    assert _by_class(settled["rail"], "resid") == []
    # The body falls back to the pre-run offer, which is the truthful rendering
    # of "nothing has happened on this page yet".
    assert len(_by_class(settled["rail"], "seg")) == 1
    assert out["writes"] == []


def test_a_run_that_wrote_nothing_does_not_tick_the_step_off(tmp_path):
    """`touched` is a CLAIM, and half of it is that something was written.

    `stageFor` reads it as `done.fill`, so a run that answered nothing must
    leave the rail on Fill and the session unremembered. The page here matches
    no rule and the model abstains on everything: the honest report is a list,
    not a tick.
    """
    out = _fill(tmp_path, start=True,
                api={"/api/autofill/choose": _reply({"choices": {
                    "q1": {"answer": None, "reason": "abstained"},
                    "q2": {"answer": None, "reason": "abstained"}}})},
                frames={"profile_fill": [{"frameId": 0, "result": {
                    "filled": [], "corrected": [], "eeoFilled": [], "already": [],
                    "seen": 0, "observations": []}}],
                        "collect_open_questions": [{"frameId": 0, "result": {
                            **COLLECT_FRAMES[0]["result"], "retryables": []}}]})
    settled = out["settled"]
    assert dict(_rows_of(settled["rail"]))["Application questions"] == "0 filled · 3 need you"
    assert _rows(_rail_rows({"regions": settled}))["fill"]["state"] == "active"
    assert out["writes"] == []


def test_a_fill_with_fields_still_open_keeps_the_user_on_the_step(tmp_path):
    """THE OTHER HALF of the claim, and it is the one that bites.

    A tick on this rail puts Track under it and takes the Fill body — the list
    of what is still open — OFF THE SCREEN, on the page it is about. So a run
    that wrote eleven fields and left two has not finished, whatever it
    achieved, and the panel says so by staying where the work is. The default
    fixture IS this case, because an abstain and an essay are what a form of
    any size produces.
    """
    out = _fill(tmp_path, start=True)
    settled = out["settled"]
    assert _rows(_rail_rows({"regions": settled}))["fill"]["state"] == "active"
    # The report is still on screen, which is the whole reason for the rule.
    assert len(_by_class(settled["rail"], "prog")) == 3
    assert len(_by_class(settled["rail"], "resid")[0]["children"]) == 2
    # And nothing was remembered: `touched` rides the session entry to the next
    # page of the wizard, and this page is not done.
    assert out["writes"] == []


def test_a_released_field_reaches_choose_without_its_profile_value(tmp_path):
    """Panel wire pin: release makes an ordinary value-free ChooseField.

    The profile in the same run carries the value that the rule rejected for
    this Yes/No control. The raw /choose body may carry the question and its
    rendered options, but never that rejected profile value.
    """
    label = "are you legally authorized to work in this country?"
    context = {
        **FILL_CONTEXT,
        "profile": {"personal": {"country": "United States"}},
    }
    released = [{"frameId": 0, "result": {
        "host": "job-boards.greenhouse.io",
        "questions": [{
            "qid": "released-auth",
            "label": label,
            "kind": "select",
            "options": ["Yes", "No"],
        }],
        "retryables": [],
    }}]
    out = _fill(
        tmp_path,
        start=True,
        api={
            "/api/autofill/context": _reply(context),
            "/api/autofill/choose": _reply({"choices": {
                "released-auth": {"answer": None, "reason": "abstained"},
            }}),
        },
        frames={"collect_open_questions": released},
    )

    [call] = _choose_calls(out)
    body = json.loads(call["init"]["body"])
    assert body["fields"] == [{
        "qid": "released-auth",
        "label": label,
        "kind": "select",
        "options": ["Yes", "No"],
    }]
    assert "United States" not in json.dumps(body)


def test_a_finished_fill_ticks_the_step_and_is_remembered(tmp_path):
    """A run that wrote something AND left nothing open, which is the only
    shape that may claim the step.

    `touched` is the bit that outlives this page: an ATS wizard is six page
    loads and `resetPageFacts` clears the store on every one of them, so
    without the write the rail would ask for the fill again on the next step of
    a form this extension has already finished.
    """
    out = _fill(tmp_path, start=True,
                api={"/api/autofill/choose": CLEAN_CHOOSE_REPLY},
                frames={"collect_open_questions": CLEAN_COLLECT_FRAMES})
    [write] = out["writes"]
    assert list(write) == ["widget.session"]
    assert write["widget.session"]["touched"] is True
    assert write["widget.session"]["tenant"] == LIGHTNING_TENANT
    settled = out["settled"]
    assert _rows(_rail_rows({"regions": settled}))["fill"]["state"] == "done"
    assert _rows(_rail_rows({"regions": settled}))["track"]["state"] == "active"
    [note] = _by_class(settled["foot"], "note")
    assert note["text"] == "Fill finished. Review before you submit."


_ACTION_DIRECT_DRIVER_JS = _PANEL_FAKES_JS + r"""
// The store handle by hand, which is the ONE place in this file that builds
// one. Everywhere else drives `actionStore()` through the real document, and
// that is the right default — a fake handle is a second copy of a contract.
// This test cannot: the refusal it pins is unreachable from the surface by
// design, because the body declines to render an input for the rows it is
// about. So the handle is a stand-in for exactly one call, it asserts nothing
// about itself, and its keys are `actionStore()`'s own (panel.js).
const ns = loadModules();
main(async () => {
  const broadcastsFor = [];
  const putsFor = [];
  const notes = [];
  for (const row of spec.rows) {
    const seen = [];
    let puts = 0;
    const card = {
      busy: null, note: null, residue: [row], writeResults: [], essays: [],
      answers: { [row.qid]: { text: "an answer", learn: true } },
      fill: { counts: { filled: 1, corrected: 0 } }, touched: false,
    };
    const store = {
      read: () => ({ ...card }),
      write: (patch) => Object.assign(card, patch),
      render: () => {},
      token: () => 1,
      current: () => true,
      api: async (path, init) => {
        if (init?.method === "PUT") { puts += 1; return {}; }
        return { key: "autofill_profile", value: {} };
      },
      broadcast: async (message) => {
        seen.push(message.type);
        return [{ frameId: 0, result: [row.qid] }];
      },
      remember: () => {},
      build: { plural: (n, word) => `${n} ${word}${n === 1 ? "" : "s"}` },
    };
    await ns.panelActions(store).submitAnswer(row.qid);
    broadcastsFor.push(seen);
    putsFor.push(puts);
    notes.push(card.note?.text ?? null);
  }
  emit({ broadcastsFor, putsFor, notes });
});
"""

_ROUTER_DRIVER_JS = _PANEL_FAKES_JS + r"""
// `loadModules()` and not a slice: `saveTargetFor` reads `ns.profileFieldFor`
// off the namespace at call time, and the whole claim under test is that it
// routes on the ENGINE's own patterns — a sliced copy would be answering with
// whichever table the slice happened to carry.
const ns = loadModules();
main(async () => {
  emit({
    targets: spec.questions.map((question) => {
      const target = ns.saveTargetFor(question);
      return [target.store, target.path ? target.path.join(".") : null];
    }),
  });
});
"""

_CUSTOM_DRIVER_JS = _PANEL_FAKES_JS + r"""
const ns = loadModules();
main(async () => {
  emit({
    lists: spec.cases.map(([custom, question, answer]) =>
      ns.withCustomAnswer(custom, question, answer)),
  });
});
"""


# ---------- the pause row: answer inline, learn forever ----------
#
# TASK 13, and the feature Guided Apply is named for. A residue row is not just
# a jump link any more: type the answer into the rail, the field is written on
# the page, and — unless the user unticks it — the same question never pauses
# another application.
#
# THE STORE THE ANSWER IS LEARNED INTO IS THE DECISION under test as much as the
# rendering is. `qa_entries` cannot deliver "learn forever": it is
# application-scoped and nothing reads it back into a later fill, so an answer
# saved there would pause again on the next application with every test green.
# `profile.custom` is matched by the DETERMINISTIC rule pass on every later
# form, so that is where a general answer goes; a question with a declared key
# goes to the key, because that is where the rules already look.


def _profile_put(out):
    """Every `PUT /api/settings/autofill` the run made, bodies parsed.

    A helper rather than a comprehension per test because eight assertions want
    it, and because the ASSERTION THAT THERE IS NONE is half of them — a pin on
    the checkbox is a pin on this list being empty.
    """
    return [json.loads(msg["init"]["body"]) for msg in out["sent"]
            if msg["type"] == "api" and msg["path"] == "/api/settings/autofill"
            and msg.get("init", {}).get("method") == "PUT"]


# The profile the learn path reads before it writes. Deliberately NOT empty and
# deliberately holding a custom row already: "append to a list that exists" and
# "create the list" are different code paths, and the dedup below needs
# something to collide with.
STORED_PROFILE = _reply({"key": "autofill_profile", "value": {
    "first_name": "Ada",
    "preferences": {"desired_salary": "$180,000"},
    # Worded EXACTLY as the fixture's `q1` label, so the row the pause row
    # learns collides with one already in the list — which is the case the
    # dedup exists for and the one an append-only path passes anyway.
    "custom": [{"question": "preferred shift", "answer": "Day"}],
}})


def _answer(tmp_path, **spec):
    """A settled fill with one pause row answered."""
    spec.setdefault("start", True)
    api = {"/api/settings/autofill": STORED_PROFILE}
    api.update(spec.pop("api", {}))
    frames = {"fill_answers": True}
    frames.update(spec.pop("frames", {}))
    return _fill(tmp_path, api=api, frames=frames, **spec)


def test_the_router_sends_a_typed_question_to_its_key_and_the_rest_to_custom(tmp_path):
    """`saveTargetFor` as a table, over the ENGINE's own patterns.

    The split is design §R2's and the reason it matters is narrow: the fill
    engine reads `preferences.notice_period` for a notice-period field, so an
    answer learned into the `custom` list instead lands where that rule does not
    look — filled from one place, learned into another, and pausing forever with
    nothing to see.

    NULL IS THE ORDINARY ANSWER, and `custom` is the ordinary destination. Most
    application questions have no typed key at all, which is why the last four
    rows are here: a router that reached for a key too eagerly would write "how
    many years of Kubernetes?" into `preferences` and break the profile's shape.
    """
    out = run_node(_ROUTER_DRIVER_JS, {"questions": [
        # The five preferences and three eligibility answers the engine has
        # declared keys for, in the wordings the corpus actually shows.
        "What is your desired annual base salary or hourly rate?",
        "What is your notice period?",
        "Are you willing to relocate?",
        "How did you hear about us?",
        "Are you 18 years of age or older?",
        "Have you previously been employed by Doosan?",
        "Are you subject to a non-compete agreement?",
        # …and the general case, which is most of a real form.
        "How many years of Kubernetes do you have?",
        "Describe a system you designed end to end.",
        "Which office would you prefer?",
        # Salary HISTORY is not a preference and never a key: the policy admits
        # the expectation question and refuses this one, and the router reads
        # the policy's own pattern rather than a second copy of it. It lands in
        # `custom` here only because nothing else claims it — the row that
        # actually protects the user is the policy pin below, which stops it
        # being offered an input at all.
        "What is your current salary?",
    ]}, tmp_path, source=PANEL_SOURCE)
    assert out["targets"] == [
        ["profile", "preferences.desired_salary"],
        ["profile", "preferences.notice_period"],
        ["profile", "preferences.willing_to_relocate"],
        ["profile", "preferences.how_heard"],
        ["profile", "eligibility.over_18"],
        ["profile", "eligibility.previously_employed_here"],
        ["profile", "eligibility.non_compete"],
        ["custom", None],
        ["custom", None],
        ["custom", None],
        ["custom", None],
    ]


def test_a_typed_answer_is_written_to_the_one_field_it_names(tmp_path):
    """The whole of the happy path, from the keystroke to the page.

    ONE PAIR in the message, and that is the point of the assertion rather than
    a detail of it: a broadcast reaches every frame of the tab, so a payload
    carrying more than the qid the user answered would be this row writing over
    controls nobody touched.
    """
    out = _answer(tmp_path, answer={"qid": "q2", "text": "LinkedIn"})
    [message] = [msg["message"] for msg in out["broadcasts"]
                 if msg["message"]["type"] == "fill_answers"]
    assert message["pairs"] == [{"qid": "q2", "answer": "LinkedIn", "kind": "select"}]
    # The row is gone from the list, because it is not open any more.
    assert [_jump_label(item) for item in
            _by_class(out["answered"]["rail"], "resid")[0]["children"]] == [
        "why do you want this role? · written answer"]
    # …and the count moved WITH it. A qid that was pure residue — q2 abstained,
    # so it is in no `guided_write` result — would otherwise leave the open
    # count by one and the filled count by none.
    assert dict(_rows_of(out["answered"]["rail"]))["Application questions"] == (
        "3 filled · 1 needs you")
    [note] = _by_class(out["answered"]["foot"], "note")
    # "Saved to your profile", because this question HAS a declared key — the
    # sentence names which of the two things happened.
    assert note["text"] == (
        "Filled “how did you hear about us?”. Saved to your profile. "
        "1 field still needs you.")


def test_the_answer_is_remembered_in_the_profile_the_rules_actually_read(tmp_path):
    """The learn, and the shape it lands in.

    `custom` because "how did you hear about us?" HAS a declared key
    (`preferences.how_heard`) — no. That is exactly the trap this test exists to
    close, and the assertion below is the one that catches a router wired to the
    wrong branch: it goes to the KEY, and the custom list is left as it was.
    """
    out = _answer(tmp_path, answer={"qid": "q2", "text": "LinkedIn"})
    [body] = _profile_put(out)
    assert body["value"]["preferences"]["how_heard"] == "LinkedIn"
    # Everything else survives, which is what "read, modify, write" has to mean
    # when the route takes a whole object: a PUT that dropped the rest of the
    # profile would pass every assertion about the new key.
    assert body["value"]["preferences"]["desired_salary"] == "$180,000"
    assert body["value"]["first_name"] == "Ada"
    assert body["value"]["custom"] == [{"question": "preferred shift", "answer": "Day"}]


def test_a_typed_work_auth_learn_carries_legacy_answers_forward(tmp_path):
    """The first typed learn must not orphan the legacy authorization pair."""
    label = "Do you currently require sponsorship?"
    frames = {"collect_open_questions": [{"frameId": 0, "result": {
        "host": "job-boards.greenhouse.io",
        "questions": [{"qid": "wa1", "label": label, "kind": "select",
                       "options": ["Yes", "No"]}],
        "retryables": [],
    }}]}
    legacy = _reply({"key": "autofill_profile", "value": {
        "work_auth": {
            "authorized_to_work": True,
            "requires_sponsorship": False,
        },
    }})
    out = _answer(
        tmp_path,
        answer={"qid": "wa1", "text": "Yes"},
        api={"/api/settings/autofill": legacy},
        frames=frames,
    )
    [body] = _profile_put(out)

    next_fill = run_profile_fill(
        tmp_path,
        fields=[
            {"label": "Are you authorized to work in the United States?",
             "kind": "select", "options": [
                 {"value": "yes", "textContent": "Yes"},
                 {"value": "no", "textContent": "No"},
             ]},
            {"label": "Will you require sponsorship in the future?",
             "kind": "select", "options": [
                 {"value": "yes", "textContent": "Yes"},
                 {"value": "no", "textContent": "No"},
             ]},
        ],
        profile=body["value"],
    )
    assert next_fill["values"] == {
        "Are you authorized to work in the United States?": "yes",
        "Will you require sponsorship in the future?": "no",
    }


def test_a_question_with_no_typed_key_is_learned_into_the_custom_list(tmp_path):
    """The other branch, and the one most real questions take.

    The engine turns every `{question, answer}` here into a rule matched by
    label substring, which is the whole mechanism behind "pause once, learn
    forever" — so an answer that lands anywhere else is an answer the next
    application cannot use.

    "preferred shift" has no declared key, so it goes to the list — and the row
    already there for it is UPDATED rather than appended beside, because the
    engine takes the first match and a near-duplicate would leave the older
    answer winning forever while the list grew on every application. The
    normalisation behind that is a table of its own below.
    """
    out = _answer(tmp_path, answer={"qid": "q1", "text": "Night"},
                  frames={"guided_write": {"q1": "not_stuck"}})
    [body] = _profile_put(out)
    assert body["value"]["custom"] == [{"question": "preferred shift", "answer": "Night"}]
    # …and no typed key was invented for it. A router that reached too eagerly
    # would put a shift preference into `preferences` and change the shape the
    # Settings form reads.
    assert body["value"]["preferences"] == {"desired_salary": "$180,000"}


def test_a_question_already_in_the_list_is_updated_and_not_duplicated(tmp_path):
    """The dedup, driven as a table over the normalisation both sides use.

    `content/autofill.js` builds its custom rules with `norm(c.question)`, so the
    list is deduped on the same function — anything else and a question whose
    casing or whitespace shifted between two ATSs is appended a second time, the
    engine keeps matching the first, and the user's newer answer is dead on
    arrival.
    """
    out = run_node(_CUSTOM_DRIVER_JS, {"cases": [
        # Same question, new answer: one row, the new answer, and the STORED
        # wording kept — a shorter question the user trimmed by hand in Settings
        # matches more labels, and replacing it with this page's longer label
        # would silently narrow a rule the user widened.
        [[{"question": "Preferred shift", "answer": "Day"}], "Preferred shift", "Night"],
        # The same question through a different ATS's whitespace and casing.
        [[{"question": "Preferred shift", "answer": "Day"}], "  preferred   SHIFT ", "Night"],
        # A genuinely different question appends.
        [[{"question": "Preferred shift", "answer": "Day"}], "Preferred office", "Berlin"],
        # No list yet: the first learn creates one rather than throwing.
        [None, "Preferred shift", "Day"],
    ]}, tmp_path, source=PANEL_SOURCE)
    assert out["lists"] == [
        [{"question": "Preferred shift", "answer": "Night"}],
        [{"question": "Preferred shift", "answer": "Night"}],
        [{"question": "Preferred shift", "answer": "Day"},
         {"question": "Preferred office", "answer": "Berlin"}],
        [{"question": "Preferred shift", "answer": "Day"}],
    ]


def test_remember_unticked_fills_the_field_and_writes_nothing(tmp_path):
    """The checkbox, and it is a real switch rather than a decoration.

    Default ON is the feature — pausing once is only worth anything if it is the
    last time — and OFF is a real choice: a one-off answer this employer asked
    for and nobody else will. What must not happen is the panel learning it
    anyway, which is a silent write to the user's profile from a control they
    turned off.
    """
    out = _answer(tmp_path, answer={"qid": "q2", "text": "LinkedIn", "learn": False})
    # The field is filled…
    assert [msg["message"]["pairs"] for msg in out["broadcasts"]
            if msg["message"]["type"] == "fill_answers"] == [
        [{"qid": "q2", "answer": "LinkedIn", "kind": "select"}]]
    # …and NOTHING was written. Not the PUT, and not the GET that precedes it:
    # a read of the profile the user declined to change is a round trip nobody
    # asked for.
    assert _profile_put(out) == []
    assert [msg for msg in out["sent"] if msg["type"] == "api"
            and msg["path"] == "/api/settings/autofill"] == []
    [note] = _by_class(out["answered"]["foot"], "note")
    assert "Remembered" not in note["text"]
    assert "profile" not in note["text"]


def test_a_policy_blocked_row_is_offered_no_way_to_answer_it(tmp_path):
    """THE RULE THAT MUST NOT BEND, from both sides of it.

    `shared/policy.js` is the single source for what is never filled — a
    signature, a password, a government identifier — and a pause row is a fill
    by another route. An input under "enter your Social Security number" would
    be this surface asking for the one thing the whole deny list exists to
    refuse, and the answer would then travel to a page AND into the profile.

    It is belt and braces: collection already refuses these on both paths, ahead
    of EXCLUDE. That is precisely why it is pinned here — a gate that holds only
    because an earlier gate held is a gate that disappears the day the earlier
    one narrows, and nothing would fail.

    The row still RENDERS, and it still jumps: the field is open and saying so
    is honest. What it does not get is a way for this panel to answer it.
    """
    blocked = [{"frameId": 0, "result": {
        **COLLECT_FRAMES[0]["result"],
        "questions": [
            {"qid": "q9", "label": "please type your social security number",
             "kind": "text", "options": []},
            {"qid": "q8", "label": "enter your e-signature", "kind": "text",
             "options": []},
            {"qid": "q7", "label": "what was your last drawn salary?",
             "kind": "text", "options": []},
        ],
        "retryables": [],
    }}]
    out = _fill(tmp_path, start=True,
                frames={"collect_open_questions": blocked, "fill_answers": True},
                api={"/api/autofill/choose": _reply({"choices": {}}),
                     "/api/settings/autofill": STORED_PROFILE})
    rail = out["settled"]["rail"]
    # All three are listed and all three jump…
    assert [_jump_label(item) for item in _by_class(rail, "resid")[0]["children"]] == [
        "please type your social security number", "enter your e-signature",
        "what was your last drawn salary?"]
    # …and not one of them has a box to type into.
    assert _by_class(rail, "needs") == []
    assert [n for n in _walk(rail) if n["tag"] == "INPUT"] == []


def test_a_combobox_row_is_not_offered_an_input_it_could_not_write(tmp_path):
    """The capability refusal, which is a different rule from the policy one and
    worth its own pin.

    `fillAnswersByQid` has three limbs — match an option for a select, click a
    labelled radio, commit a value for everything else — and a combobox is a
    `<button aria-haspopup="listbox">`. The third limb would set `.value` on a
    button, so the write would report nothing stuck and the user would have
    typed into a box for no reason. Saying nothing is the honest offer; the jump
    button sends them to the control, which does work.
    """
    out = _answer(tmp_path, frames={"guided_write": {"r1": "not_stuck"}})
    rows = _by_class(out["settled"]["rail"], "resid")[0]["children"]
    labelled = {_jump_label(item): item for item in rows}
    assert "country" in labelled, "the retryable did not reach the residue"
    assert _by_class(labelled["country"], "needs") == []
    # …while the select beside it does get one, so this is a rule about the
    # KIND rather than a body that rendered nothing at all.
    assert _by_class(labelled["how did you hear about us?"], "needs") != []


def test_a_row_the_rules_already_knew_the_answer_to_asks_you_to_confirm_it(tmp_path):
    """A retryable is a control that refused a value the profile already holds.

    So the honest ask is "confirm this", not "type it again": the box arrives
    holding `known_value`. And there is nothing to learn from putting a profile
    value back into the profile, so the row offers no checkbox — with a line
    that says why, because a control that silently fails to render reads as a
    bug rather than as a decision.
    """
    retryable = [{"frameId": 0, "result": {
        **COLLECT_FRAMES[0]["result"],
        "questions": [],
        "retryables": [{"qid": "r2", "label": "which country do you live in?",
                        "kind": "text", "known_value": "United States"}],
    }}]
    frames = {"collect_open_questions": retryable, "guided_write": {"r2": "not_stuck"}}
    # TWO runs, because the two halves are true at different moments: the box is
    # only on screen before the submit, and the message only exists after it.
    resting = _answer(tmp_path, frames=frames)
    [box] = _by_class(resting["settled"]["rail"], "needs")
    [input_] = [n for n in _walk(box) if n["tag"] == "INPUT"]
    assert input_["value"] == "United States"
    # No checkbox, and a sentence instead of one — a control that silently
    # failed to render reads as a bug rather than as a decision.
    assert [n for n in _walk(box) if n["id"] == "learn-r2"] == []
    assert _text(_by_class(box, "learn")[0]) == (
        "Already in your profile — the field refused the write, not the answer.")

    out = _answer(tmp_path, frames=frames, answer={"qid": "r2"})
    # The write went out with the known value, because the user pressed — never
    # because it was there. The rule pass already tried exactly this and the
    # page said no; re-sending it unasked would be a second retry the engine
    # deliberately does not make.
    [message] = [msg["message"] for msg in out["broadcasts"]
                 if msg["message"]["type"] == "fill_answers"]
    assert message["pairs"] == [
        {"qid": "r2", "answer": "United States", "kind": "text"}]
    assert _profile_put(out) == []


def test_a_value_the_page_refuses_keeps_the_row_and_says_what_happened(tmp_path):
    """The page was reached and the field did not take it.

    Two things must not happen. The row must not leave the list — it is still
    open, and a panel that quietly dropped it would take the only pointer to an
    unanswered field off the screen. And the sentence must not blame the
    connection: "can't reach this page" is the message for a page nobody
    reached, and this one answered.
    """
    out = _answer(tmp_path, answer={"qid": "q2", "text": "Carrier pigeon"},
                  frames={"fill_answers": []})
    assert [_jump_label(item) for item in
            _by_class(out["answered"]["rail"], "resid")[0]["children"]] == [
        "how did you hear about us?", "why do you want this role? · written answer"]
    [note] = _by_class(out["answered"]["foot"], "note")
    assert note["text"] == (
        "That answer didn’t match any of the options — try one of them verbatim.")
    assert note["class"] == "note error"
    # And nothing was learned: an answer the form would not take is not an
    # answer worth teaching the rules.
    assert _profile_put(out) == []


def test_a_page_that_stopped_answering_says_so_and_changes_nothing(tmp_path):
    """The frame is gone — a wizard step navigated under the panel, or a tab
    reloaded — so the qid addresses a control in a document that no longer
    exists. One sentence, the runner's own, and the row stays."""
    out = _answer(tmp_path, answer={"qid": "q2", "text": "LinkedIn"},
                  frames={"fill_answers": "gone"})
    [note] = _by_class(out["answered"]["foot"], "note")
    assert note["text"].startswith("Can't reach this page.")
    assert note["class"] == "note error"
    assert len(_by_class(out["answered"]["rail"], "resid")[0]["children"]) == 2
    assert _profile_put(out) == []


def test_a_learn_that_fails_leaves_the_field_filled_and_says_both(tmp_path):
    """THE INDEPENDENCE RULE, and it is the one a rollback would feel tidy
    about.

    Writing the field is a message to a page; learning the answer is a write to
    the profile. They fail separately, so they are reported separately — and the
    field STAYS filled, because emptying a box the user is looking at over a
    setting that did not save is worse than the setting not saving. The row is
    gone from the list too: it is answered, whatever the profile thinks.
    """
    out = _answer(tmp_path, answer={"qid": "q2", "text": "LinkedIn"},
                  api={"/api/settings/autofill": {"ok": False,
                                                  "error": "500: settings unavailable"}})
    assert [_jump_label(item) for item in
            _by_class(out["answered"]["rail"], "resid")[0]["children"]] == [
        "why do you want this role? · written answer"]
    [note] = _by_class(out["answered"]["foot"], "note")
    # BOTH facts in one sentence, in the order they happened.
    assert note["text"] == (
        "Filled “how did you hear about us?”. Filled, but not remembered: "
        "500: settings unavailable 1 field still needs you.")


def test_the_last_open_field_finishes_the_fill_exactly_as_a_clean_run_would(tmp_path):
    """CONVERGENCE with `startFill`, which is the half of this feature that
    could most easily have forked.

    `touched` is the claim the rail renders as a tick with Track active beneath
    it, and it is written only when the page BOTH wrote something and has
    nothing left open. A submit path with its own predicate — one written over
    "the run's residue", say — would have said no forever, because a run's
    residue never changes after the run. `fillFinished` is one function read by
    both, over the store's own fields.
    """
    out = _answer(tmp_path, answer={"qid": "q2", "text": "LinkedIn"},
                  frames={"collect_open_questions": CLEAN_COLLECT_FRAMES,
                          "fill_answers": True},
                  api={"/api/autofill/choose": _reply({"choices": {
                      "q1": {"answer": "Day", "reason": "matched"},
                      "q2": {"answer": None, "reason": "abstained"}}}),
                       "/api/settings/autofill": STORED_PROFILE})
    settled = out["answered"]
    rows = _rows(_rail_rows({"regions": settled}))
    assert rows["fill"]["state"] == "done"
    assert rows["track"]["state"] == "active"
    [note] = _by_class(settled["foot"], "note")
    assert note["text"].endswith("Fill finished. Review before you submit.")
    # …and it OUTLIVES the page, which is the point of the write: an ATS wizard
    # is six page loads and `resetPageFacts` clears the store on every one.
    [write] = [w for w in out["writes"] if "widget.session" in w]
    assert write["widget.session"]["touched"] is True


def test_two_answers_in_a_row_do_not_erase_each_other(tmp_path):
    """THE LOST UPDATE, and it is the reason `busy` now covers the learn.

    `PUT /api/settings/autofill` takes a WHOLE object, so a learn is a
    read-modify-write. While the learn ran outside the `busy` span, two rows
    answered quickly interleaved as GET, GET, PUT, PUT — and the second PUT,
    built from a profile read before the first one landed, erased the first
    row's key. The user had already been told it was saved.

    The profile is modelled as STATE here rather than as a canned reply, which
    is the whole reason this test can see anything: a canned GET answers with
    the original object whatever the panel does, so the lost update and the
    correct behaviour would produce identical bodies.

    ASSERTED ON THE CONTENT, not on the call pattern. Serializing, merging or
    re-reading are all legitimate fixes and a pin on "GET, PUT, GET, PUT" would
    outlaw two of them; what may never happen is an answer the panel said it
    saved not being in the profile afterwards.
    """
    out = _answer(
        tmp_path,
        profileStore={"first_name": "Ada", "preferences": {"desired_salary": "$180,000"}},
        # HELD, so the second press lands while the first row's profile write is
        # still open — the exact window the bug lived in.
        hold=["GET /api/settings/autofill"],
        frames={"guided_write": {"q1": "not_stuck"}},
        answerBoth=[{"qid": "q2", "text": "LinkedIn"}, {"qid": "q1", "text": "Night"}])
    # Both landed, and neither took the other's place.
    assert out["profile"]["preferences"]["how_heard"] == "LinkedIn"
    assert out["profile"]["custom"] == [{"question": "preferred shift", "answer": "Night"}]
    # …and nothing else in the profile was lost on the way through two whole-
    # object writes.
    assert out["profile"]["first_name"] == "Ada"
    assert out["profile"]["preferences"]["desired_salary"] == "$180,000"


def test_nothing_else_can_be_started_while_an_answer_is_being_learned(tmp_path):
    """The other half of the same rule, on the controls that read `busy`.

    The learn is a round trip the user cannot see, and while it was outside the
    span the footer's primary re-enabled underneath it — so a press started a
    whole second fill while a profile write was open, and the generation token
    could not catch it because the token moves on a TAB CHANGE and this is the
    same tab. The mode segments are the same story from the other side: pressing
    one repaints the rail, and the repaint was what re-enabled the button.

    So this drives both: mid-learn, read what the controls look like, then press
    them and check that nothing happened.
    """
    out = _answer(
        tmp_path,
        profileStore={"first_name": "Ada"},
        hold=["GET /api/settings/autofill"],
        frames={"guided_write": {"q1": "not_stuck"}},
        pokeDuringLearn=True,
        answerBoth=[{"qid": "q2", "text": "LinkedIn"}, {"qid": "q1", "text": "Night"}])
    mid = out["midLearn"]
    # OUT OF REACH, and it has to be visible as well as true: a user cannot tell
    # a broken control from a busy one, which is the failure this surface keeps
    # naming.
    assert [one["disabled"] for one in _by_class(mid["rail"], "seg")[0]["children"]] == [
        True, True]
    assert _by_class(mid["foot"], "cta")[0]["disabled"] is True
    # And pressing them anyway starts nothing. TWO rule passes would mean the
    # run below had launched under an open profile write; there is one, from the
    # original fill.
    assert _broadcast_types(out).count("profile_fill") == 1
    # AND THE REPAINT DID NOT RE-ENABLE THEM, which is the regression itself
    # rather than a restatement of the first assertion. The segment handler runs
    # and re-renders the rail; while the learn sat outside the `busy` span that
    # render read `busy: null` and drew a live primary over an open profile
    # write. (The mode itself moving is a harness artifact — this fake fires a
    # click at a disabled control where a browser swallows it — so what is
    # asserted is the state the browser actually honours.)
    poked = out["afterPoke"]
    assert [one["disabled"] for one in _by_class(poked["rail"], "seg")[0]["children"]] == [
        True, True]
    assert _by_class(poked["foot"], "cta")[0]["disabled"] is True


def test_the_action_refuses_a_policy_blocked_row_even_reached_directly(tmp_path):
    """THE CREDENTIALS RULE at the layer that touches the page.

    The body renders no input for a policy-blocked row, so this refusal is
    unreachable through today's UI — which is exactly why it is pinned. The
    render gate is a decision about what to draw; THIS one is the decision about
    what to send to a form, and a later row source (a re-collect, a restored
    residue, Task 15's own body) that reached the action without passing the
    renderer would otherwise type a password into a page and then save it.

    Driven against the action DIRECTLY, through the store handle contract
    `actionStore()` documents, because there is no way in from the surface — and
    that is the point rather than a shortcut. The handle here is a stand-in;
    every other test in this section drives the real one through the document.
    """
    out = run_node(_ACTION_DIRECT_DRIVER_JS, {"rows": [
        {"qid": "p1", "label": "please type your social security number", "kind": "text"},
        {"qid": "p2", "label": "enter your e-signature", "kind": "text"},
        {"qid": "p3", "label": "what was your last drawn salary?", "kind": "text"},
        # The control case, and the reason this is a table: a row the policy has
        # nothing to say about goes through, so the refusal is about the LABEL
        # rather than about a direct call being refused on principle.
        {"qid": "ok", "label": "preferred shift", "kind": "text"},
    ]}, tmp_path, source=PANEL_SOURCE)
    assert out["broadcastsFor"] == [[], [], [], ["fill_answers"]]
    # No learn either. A refused answer that still reached the profile would be
    # the deny list holding on the page and not in the store.
    assert out["putsFor"] == [0, 0, 0, 1]
    assert out["notes"][:3] == [
        "This one is never filled from here — signatures, passwords and "
        "government IDs are yours to type."] * 3


def test_enter_in_the_box_sends_the_answer_the_button_would(tmp_path):
    """One answer, two ways, and the same write.

    The box is not inside a `<form>` — nothing on this surface is, because a
    form in a panel whose whole promise is that it never submits an application
    is a shape with the wrong meaning on it — so the browser gives Enter to this
    input nowhere. A single-line box the user has just finished typing into is
    exactly where the key is expected, and a row that ignored it would read as a
    control that swallowed the answer.
    """
    out = _answer(tmp_path, answer={"qid": "q2", "text": "LinkedIn", "via": "enter"})
    [message] = [msg["message"] for msg in out["broadcasts"]
                 if msg["message"]["type"] == "fill_answers"]
    assert message["pairs"] == [{"qid": "q2", "answer": "LinkedIn", "kind": "select"}]
    # …and the whole action ran, not just the broadcast: the row left the list
    # and the answer was learned.
    assert [_jump_label(item) for item in
            _by_class(out["answered"]["rail"], "resid")[0]["children"]] == [
        "why do you want this role? · written answer"]
    assert _profile_put(out)[0]["value"]["preferences"]["how_heard"] == "LinkedIn"


def test_the_box_says_what_it_is_for_to_something_that_cannot_see_it(tmp_path):
    """`aria-describedby`, on both of the lines a pause row can carry.

    The option list is not decoration: the writer matches the typed answer
    against those exact strings, so a user who cannot see them is guessing at a
    closed menu. The already-in-your-profile sentence is the other one — it is
    why there is no checkbox. Proximity carries neither, and the two never
    collide over the id because only a `text`-kind retryable reaches the second
    branch and a text kind has no options to print.
    """
    out = _answer(tmp_path)
    [box] = [one for one in _by_class(out["settled"]["rail"], "needs")
             if [n for n in _walk(one) if n["id"] == "answer-q2"]]
    [field] = [n for n in _walk(box) if n["id"] == "answer-q2"]
    described = field["attrs"]["aria-describedby"]
    [note] = [n for n in _walk(box) if n["id"] == described]
    assert note["text"] == "one of: LinkedIn · A friend"

    # The retryable's branch, where the same id lands on the sentence that
    # replaces the checkbox.
    retryable = [{"frameId": 0, "result": {
        **COLLECT_FRAMES[0]["result"],
        "questions": [],
        "retryables": [{"qid": "r2", "label": "which country do you live in?",
                        "kind": "text", "known_value": "United States"}],
    }}]
    other = _answer(tmp_path, frames={"collect_open_questions": retryable,
                                      "guided_write": {"r2": "not_stuck"}})
    [box2] = _by_class(other["settled"]["rail"], "needs")
    [field2] = [n for n in _walk(box2) if n["id"] == "answer-r2"]
    [note2] = [n for n in _walk(box2) if n["id"] == field2["attrs"]["aria-describedby"]]
    assert note2["text"].startswith("Already in your profile")


def test_a_submit_that_lands_after_you_switch_tabs_paints_nothing(tmp_path):
    """The generation rule on an async store-writing action, which is what this
    one is.

    A submit is two round trips — the page write, then the learn — and the user
    is free to leave across either. Painted onto the tab they moved to, the note
    would name a field that tab does not have and the residue list would lose a
    row belonging to a page they are no longer looking at.

    DRIVEN WITH THE CHECKBOX OFF, and that is the whole design of this test
    rather than an incidental setting. With it on, the learn's OWN guard —
    `store.current` before its sentence — returns first and the run paints
    nothing whether or not `duringAction` guarded the write. It passed under a
    mutation that removed the write's guard entirely, which is the vacuous shape
    this project keeps finding. Off, the note is the first thing written after
    the fan-out returns, so it is the guard under test that stops it.
    """
    out = _answer(tmp_path, answer={"qid": "q2", "text": "LinkedIn", "learn": False},
                  hold=["page_broadcast:fill_answers"],
                  switchAfterAnswer=42, tabUrls={"42": "chrome://settings"})
    settled = out["settled"]
    assert "how did you hear about us" not in json.dumps(settled)
    assert "Filled" not in _text(settled["foot"])
    assert [n for n in _walk(settled["foot"]) if "spin" in str(n.get("class"))] == []
    # And the session key was not written either: `touched` and `remember()` are
    # claims about a page, and the page they would be about is gone.
    assert [w for w in out["writes"] if "widget.session" in w] == []


def test_a_second_press_while_the_first_is_open_is_not_a_second_write(tmp_path):
    """The twin rule, on a control that sits above a busy footer.

    Every control in a pause row goes out of reach while an action runs — the
    input, the checkbox and the button — because the row stands directly above a
    footer primary that greys and spins. A button that stayed pressable would
    send a second write into a page the first one is still walking, and the
    guard is what makes the second press cost nothing rather than merely look
    ignored.
    """
    out = _answer(tmp_path, answer={"qid": "q2", "text": "LinkedIn"},
                  hold=["page_broadcast:fill_answers"], answerAgain=True)
    # ONE write, from two presses.
    assert len([msg for msg in out["broadcasts"]
                if msg["message"]["type"] == "fill_answers"]) == 1
    # And the row LOOKED unavailable while it ran, which is the half a `busy`
    # guard alone does not buy: a user cannot tell a broken control from a busy
    # one (the Jobscan failure this surface keeps naming).
    box = _by_class(out["answering"]["rail"], "needs")[0]
    assert [n["disabled"] for n in _walk(box) if n["tag"] in ("INPUT", "BUTTON")] == [
        True, True, True]


def test_the_characters_survive_a_repaint_they_did_not_ask_for(tmp_path):
    """`card.preview`'s rule, on the rail's other set of inputs.

    Every render rebuilds the rail from the store, so an input holding its own
    characters loses them the moment ANYTHING else repaints — another row
    submitting, a note landing, a late score read. The draft therefore lives in
    the store and the element is rendered FROM it, which is what this drives:
    type, let something unrelated land, and read the box back.
    """
    out = _answer(tmp_path, typeOnly={"qid": "q2", "text": "A friend"})
    [box] = [n for n in _walk(out["settled"]["rail"]) if n["id"] == "answer-q2"]
    assert box["value"] == "A friend"


def test_an_empty_box_is_not_an_answer(tmp_path):
    """Pressing with nothing typed asks the page for nothing. A blank written
    into a form is a worse outcome than an unanswered field: it looks answered
    to the user and to the ATS, and the residue list would drop the only pointer
    back to it."""
    out = _answer(tmp_path, answer={"qid": "q2", "text": "   "})
    assert [msg for msg in out["broadcasts"]
            if msg["message"]["type"] == "fill_answers"] == []
    [note] = _by_class(out["answered"]["foot"], "note")
    assert note["text"] == "Type an answer first."
    assert len(_by_class(out["answered"]["rail"], "resid")[0]["children"]) == 2




# ---------- the QnA drawer: paste a question, copy the answer ----------------
#
# TWO SUBJECTS IN ONE SECTION, and they belong together: `sanitizeAnswer` is the
# function this drawer renders THROUGH, and Task 14 moved it into
# `shared/decisions.js` so that both surfaces paste from one copy of it. Its
# table is driven at the new home through `loadModules()` — the real file, the
# real publication — and the drawer's own tests then read what it produced.
#
# WHY A SOURCE PIN AND NOT ONLY A BEHAVIOURAL ONE: a local re-implementation
# written beneath the destructure compiles and ships, and nothing executed here
# would notice — the drawer would go on producing right answers from the wrong
# copy until the two drifted.

_SANITIZE_DRIVER_JS = r"""
const { sanitizeAnswer } = loadModules().decisions;
main(async () => {
  emit(Object.fromEntries(
    Object.entries(spec.cases).map(([name, text]) => [name, sanitizeAnswer(text)])));
});
"""


@pytest.fixture(scope="module")
def sanitized(tmp_path_factory):
    """One case per marker the function strips, plus what it must NOT touch.

    The cases are the comments' own claims made executable: each line of that
    chain names a thing a model writes for a chat window and an ATS renders as
    literal punctuation, so each gets a case — and the ones that assert
    SURVIVAL are as load-bearing as the ones that assert removal. A "sanitizer"
    that flattened the paragraph breaks would pass every strip case here and
    hand the user a wall of text to paste into a cover-letter box.
    """
    cases = {
        "heading": "## Why this role\nI build data systems.",
        "bold": "I led **three** migrations.",
        "code": "I use `pytest` and ```ruff``` daily.",
        "bullets": "- built it\n* shipped it\n1. measured it\n2) kept it",
        # A dash rule and a bullet share a character; only the RULE line goes.
        "rule": "First.\n\n---\n\nSecond.",
        # The one case where a paragraph break does NOT survive, pinned because
        # it is easy to read as a bug: the bullet pattern's leading `\s*` starts
        # matching at the blank line and takes that newline with the marker. It
        # is the shipped behaviour of the function the card has always used, and
        # it is left alone — a list that has moved up against the sentence
        # introducing it still reads.
        "list_after_a_paragraph": "I did three things:\n\n- one\n- two",
        "spacing": "One.\n\n\n\nTwo.",
        "edges": "\n\n  Answer.  \n\n",
        # Not markdown, and the commonest thing in an honest answer: a hyphen
        # inside a sentence, an asterisk that pairs with nothing, a paragraph
        # break. Stripping any of these would be the function editing the text
        # rather than unformatting it.
        "prose": "I am a full-stack engineer.\n\nI * really * mean it.",
        # KNOWN RESIDUE, pinned rather than fixed: the bold pattern takes the
        # inner pair of `***both***` and `[^*]+` cannot reach across the third,
        # so one asterisk survives on each side. A greedier pattern would start
        # eating the lone asterisks in the case above, and one stray character
        # in a box the user reads before submitting is the cheaper error.
        "triple_emphasis": "I ***owned*** it.",
        # `String(null)` prints "null" into a cover-letter box; the guard is
        # what the widget's own copy had, kept.
        "nothing": None,
    }
    return run_node(_SANITIZE_DRIVER_JS, {"cases": cases},
                    tmp_path_factory.mktemp("sanitize"), source=DECISIONS_JS)


def test_the_markdown_a_form_field_cannot_render_is_stripped(sanitized):
    """Every marker goes and its content stays — the posture the docstring
    states: nothing here decides an answer is wrong, only that a plain textarea
    cannot show it."""
    assert sanitized["heading"] == "Why this role\nI build data systems."
    assert sanitized["bold"] == "I led three migrations."
    assert sanitized["code"] == "I use pytest and ruff daily."
    assert sanitized["bullets"] == "built it\nshipped it\nmeasured it\nkept it"
    assert sanitized["rule"] == "First.\n\nSecond."
    assert sanitized["list_after_a_paragraph"] == "I did three things:\none\ntwo"


def test_what_the_reader_needs_survives_and_what_the_backend_omits_is_empty(sanitized):
    """The half a strip-only test would let rot.

    Paragraph breaks are how an essay answer reads, so they survive; triple
    spacing does not, because that is formatting rather than structure. Ordinary
    punctuation is untouched — a hyphenated word is not a bullet — and a missing
    answer is an empty string rather than the word "null".
    """
    assert sanitized["spacing"] == "One.\n\nTwo."
    assert sanitized["edges"] == "Answer."
    assert sanitized["prose"] == "I am a full-stack engineer.\n\nI * really * mean it."
    assert sanitized["nothing"] == ""
    # The residue the docstring names, visible rather than discovered live.
    assert sanitized["triple_emphasis"] == "I *owned* it."


def test_the_injected_copy_of_the_sanitizer_stays_identical_to_the_shared_one():
    """The ONE copy of this function that is allowed to exist, and the pin that
    keeps it honest.

    `fillAnswersByQid` (content/open-questions.js) is INJECTED into the page,
    where `window.careerStudioCompanion` does not exist — so it cannot read the
    shared module and carries its own copy, exactly as it carries its own commit
    ladder and for the same reason. That copy is registered in
    `extension/.slopconfig.json` rather than hidden by a re-baseline.

    What a registration cannot do is notice the two drifting, and this chain is
    six `.replace` calls: a fix applied to one copy leaves the other stripping
    five markers out of six, and the answers it writes into the page keep the
    sixth. So they are compared, comments and whitespace ignored —
    `test_both_copies_of_the_commit_ladder_stay_identical`'s shape, for the
    other block in the same injected function.
    """
    chain = r'String\(text \?\? ""\)(?:\s*\.replace\([^\n]*\))+\s*\.trim\(\);'
    copies = re.findall(chain, DECISIONS_JS + OPEN_QUESTIONS_JS, re.S)
    assert len(copies) == 2, f"expected two sanitizers, found {len(copies)}"

    def strip(text):
        return re.sub(r"\s+", " ", re.sub(r"//[^\n]*", "", text)).strip()

    assert strip(copies[0]) == strip(copies[1]), (
        "the shared sanitizer and its injected copy have diverged — fix both "
        "or neither")


_QNA_DRIVER_JS = _PANEL_FAKES_JS + r"""
loadModules();
const drawer = () => {
  const found = withClass(REGIONS.rail, "qna")[0];
  if (!found) throw new Error("the Fill stage rendered no QnA drawer");
  return found;
};
// The trigger is the drawer's ONE `linkish`; the Copy button carries its own
// class for exactly this reason — two controls found by one class is how a
// press lands on the wrong one and the test still passes.
const trigger = () => withClass(drawer(), "linkish")[0];
// `findById` is the harness's — see the pause driver's note on why the two
// copies this file used to carry became one.
const box = () => {
  const found = findById(REGIONS.rail, "qna-question");
  if (!found) throw new Error("the drawer is not open");
  return found;
};
const askButton = () => withClass(drawer(), "save")[0];
const copyButton = () => withClass(drawer(), "copy")[0];
// The essay row's handoff, pressed by the question it names rather than by
// position: the list holds the residue first and the essays after it, and an
// index would move the day a run residues one more field.
const essayAsk = (label) => {
  const item = withClass(REGIONS.rail, "resid").flatMap((list) => list.children)
    .find((row) => row.children[0].textContent === label);
  if (!item) throw new Error(`no open-field row reads "${label}"`);
  const ask = withClass(item, "ask")[0];
  if (!ask) throw new Error(`the row for "${label}" offers no Ask`);
  ask.click();
};

main(async () => {
  await settle();
  const loaded = regions();
  if (spec.start === true) {
    withClass(REGIONS.foot, "cta")[0].click();
    await settle();
    release();
    await settle();
  }
  const afterRun = regions();
  // Two ways in: the drawer's own trigger, or an essay row handing its question
  // over. They are the same drawer and the second is the whole of Task 14's
  // essay handoff, so both are driven here rather than in two fixtures.
  if (spec.essay !== undefined) essayAsk(spec.essay);
  else if (spec.open === true) trigger().click();
  await settle();
  const opened = regions();
  if (spec.question !== undefined) {
    box().value = spec.question;
    // A real `input` dispatch and not a store poke: the characters living in
    // the store rather than in the element is what makes a pasted question
    // survive a repaint, and a test that wrote `card.qna` would pass with that
    // wiring removed.
    box().dispatch("input");
  }
  // Something unrelated lands between the typing and the press — a note, a
  // load — which is the repaint the draft has to survive.
  if (spec.repaintBeforeAsk === true) {
    withClass(REGIONS.rail, "seg")[0].children[0].click();
    await settle();
  }
  const typed = regions();
  let asking = null;
  if (spec.ask === true) {
    askButton().click();
    // Synchronous: the action paints `busy` before its first await, so this is
    // the surface as the user sees it while the question is on the wire.
    asking = regions();
    // A SECOND press while the first is still open, which is what a user does
    // when a held round trip looks like it did nothing.
    if (spec.askAgain === true) askButton().click();
    await settle();
    // FOLDED AWAY while the question is on the wire. The trigger is the one
    // control here that is NOT disabled during an ask — it discloses, it claims
    // nothing, and reading the residue list under it is free — so this is a
    // real thing a user does, and it is the only way `card.qna` can change
    // between the action's snapshot and its write.
    if (spec.closeDuringAsk === true) {
      trigger().click();
      await settle();
    }
    // …and the user is free to leave while the answer is still on the wire.
    if (spec.switchTo !== undefined) {
      await onActivated({ tabId: spec.switchTo });
      await settle();
    }
    release();
    await settle();
  }
  const answered = regions();
  if (spec.copy === true) {
    copyButton().click();
    await settle();
  }
  if (spec.close === true) {
    trigger().click();
    await settle();
  }
  emit({ loaded, afterRun, opened, typed, asking, answered,
         settled: regions(), sent, copies, broadcasts });
});
"""

# An essay the runner routes to this drawer: a QUESTIONY textarea, which is
# `routeOpenQuestions`' own definition of one. It is the third question in the
# shared collect fixture, so a run over `_fill`'s default world produces exactly
# this row in the still-open list.
ESSAY_LABEL = "why do you want this role?"
# What `/api/qa` answers, with the markdown a model reaches for still in it —
# because what the drawer renders is what `sanitizeAnswer` left behind, and an
# already-clean fixture could not tell the two apart.
QA_REPLY = _reply({"answers": [
    "## Why this role\nI have led **three** platform migrations.\n\n"
    "- shipped the ingest\n- halved the p99"]})
# The blank line before the list is NOT in it, and that is the shipped
# behaviour rather than a typo here: the bullet pattern's leading `\s*` starts
# matching at the empty line and eats the newline along with the marker. Pinned
# as its own case in the table above (`list_after_a_paragraph`), so it is a
# decision anyone can see rather than a surprise this fixture absorbs.
QA_ANSWER = ("Why this role\nI have led three platform migrations.\n"
             "shipped the ingest\nhalved the p99")
# An application on this page, with a rendered PDF behind it: Resume is done, so
# the rail's active stage is Fill and the drawer's grounding is the application.
# `_fill`'s own default is the base-as-is arming, which has no application at
# all — that path is the `job_id` test below.
def _with_application(**spec):
    api = {"/api/applications/": _reply({"pdf_path": "a.pdf", "status": "draft"}),
           "/api/qa": QA_REPLY}
    api.update(spec.pop("api", {}))
    return {"stored": {"widget.session": entry()}, "api": api, **spec}


def _qna(tmp_path, **spec):
    return _fill(tmp_path, driver=_QNA_DRIVER_JS, **spec)


def _qa_posts(out):
    return [json.loads(msg["init"]["body"]) for msg in out["sent"]
            if msg["type"] == "api" and msg["path"] == "/api/qa"]


def _drawer(region):
    [found] = _by_class(region, "qna")
    return found


def test_the_drawer_is_offered_on_the_fill_stage_and_starts_closed(tmp_path):
    """The mockup's `.qna` line, and the reason it is one line.

    The Fill stage's subject is the form. A composer standing open under it
    would compete with the list of fields that still need answering, so the
    closed state is a sentence saying what is behind the trigger — nobody has
    to press it to find out — and the box arrives only when asked for.

    OFFERED BEFORE A RUN as well, which is not the same claim: the question a
    user pastes here is usually the one in front of them on the page rather than
    one this extension found, so gating the composer on a fill having happened
    would withhold it from the person who opened the panel to answer one
    question.
    """
    out = _qna(tmp_path, **_with_application())
    drawer = _drawer(out["loaded"]["rail"])
    # "Ask", NOT "Ask ↗": on this surface the arrow means the control LEAVES
    # (the header's deep link, the Resume fork's Custom in Studio), and this one
    # discloses a region directly below it. The mockup drew the glyph on its
    # teaser; the panel's own convention wins over it.
    assert _text(drawer) == "Paste any question for a grounded answer Ask"
    # Nothing is disclosed yet, and it says so where a screen reader hears it —
    # and says ONLY that. The Tailor fork's rule, reused whole: closed, there is
    # no region, so a kept `aria-controls` would offer a jump that goes nowhere,
    # which is the same broken promise as a link to a guessed address. Asserted
    # as the WHOLE attribute map, because "no aria-controls" is the claim.
    [toggle] = _by_class(drawer, "linkish")
    assert toggle["attrs"] == {"aria-expanded": "false"}
    assert _by_class(drawer, "ans") == []
    assert [one for one in _walk(drawer) if one["tag"] == "TEXTAREA"] == []
    # …and no round trip was spent to render any of it.
    assert _qa_posts(out) == []


def test_the_open_drawer_names_what_it_disclosed_and_the_name_resolves(tmp_path):
    """The other half of the Tailor fork's disclosure pattern.

    `aria-expanded` says a region appeared; `aria-controls` says WHICH — and the
    only version of that attribute worth having is one that RESOLVES, because an
    id nothing carries offers a jump that goes nowhere. ONE region, so there is
    one thing to point at: the box, the button that sends it and the answer that
    comes back are one disclosure, and a reader sent to the box alone would be
    sent past the answer.
    """
    out = _qna(tmp_path, open=True, question="Why us?", ask=True,
               **_with_application())
    drawer = _drawer(out["answered"]["rail"])
    [toggle] = _by_class(drawer, "linkish")
    assert toggle["attrs"]["aria-expanded"] == "true"
    [region] = [found for found in _walk(drawer)
                if found["id"] == toggle["attrs"]["aria-controls"]]
    # All three parts of the disclosure are inside the one region.
    assert [one["tag"] for one in _walk(region) if one["tag"] == "TEXTAREA"] == ["TEXTAREA"]
    assert _by_class(region, "save")[0]["text"] == "Ask"
    assert _by_class(region, "a")[0]["text"] == QA_ANSWER


def test_a_question_reaches_the_backend_exactly_as_the_card_sends_one(tmp_path):
    """WIRE FIDELITY, which is the whole of this test.

    `askOneQuestion` (widget.js) posts `/api/qa` with the application it is
    grounded in and a ONE-element `questions` array. This drawer sends the same
    body to the same path — not a batch, because the panel answers "fill the
    remaining questions" with the guided runner and a second batch path here
    would be a second pipeline for a job `shared/guided-run.js` already owns.

    The answer is then SANITIZED, which is this surface's one delta from the
    card's ask and follows from what it is for: the paragraph is going to be
    copied into a plain textarea on an ATS, where `**bold**` is two literal
    asterisks.
    """
    out = _qna(tmp_path, open=True, question="  Why do you want to work here?  ",
               ask=True, **_with_application())
    # ONE post, one question, and the body is the card's two keys.
    assert _qa_posts(out) == [{"application_id": "app-remembered",
                               "questions": ["Why do you want to work here?"]}]
    drawer = _drawer(out["answered"]["rail"])
    [answer] = _by_class(drawer, "a")
    assert answer["text"] == QA_ANSWER
    # The question it was given for is printed with it, so the paragraph stays a
    # true statement however the box above is retyped.
    [asked] = _by_class(drawer, "q")
    assert asked["text"] == "“Why do you want to work here?”"
    [note] = _by_class(out["answered"]["foot"], "note")
    assert note["text"] == "Saved to this application’s Q&A history."


def test_an_ask_with_no_application_is_grounded_in_the_job(tmp_path):
    """The rung the card does not have, and why this surface needs it.

    "Use base as-is" arms a fill with a job and NO application — that is what
    the shortcut is — and the essays that land in this drawer come out of
    exactly those runs. The card refuses without an application ("Pick an
    application first."), which would be a dead control here. `POST /api/qa`
    takes either key, so the drawer sends the most specific grounding it holds:
    `resumeQuery`'s rungs, in `resumeQuery`'s order.
    """
    out = _qna(tmp_path, open=True, question="Tell us about a hard project.",
               ask=True,
               stored={"widget.session": entry(applicationId=None, baseArmed=True,
                                               pdfReady=False)},
               api={"/api/qa": QA_REPLY})
    # `base` IS THE FIX, not decoration: without it the route grounds a
    # job-level answer on its own generic default resume — one the user never
    # picked, and one this repo's own installs need not carry — so the note
    # below ("your base resume") would be a claim about a document the answer
    # was not written from.
    assert _qa_posts(out) == [{"job_id": "job-lightning", "base": "ai_ml_engineer",
                               "questions": ["Tell us about a hard project."]}]
    [note] = _by_class(out["answered"]["foot"], "note")
    assert note["text"] == "Answered from your base resume and this posting."


def test_a_page_with_nothing_to_ground_an_answer_in_says_so(tmp_path):
    """No application and no job: the route would 400, and calling that an
    outage would blame the backend for a state this panel can see."""
    out = _qna(tmp_path, open=True, question="Why us?", ask=True,
               api={"/api/qa": QA_REPLY})
    assert _qa_posts(out) == []
    [note] = _by_class(out["answered"]["foot"], "note")
    assert note["text"].startswith("Add the job first")


def test_a_job_with_no_base_picked_is_not_asked_from_a_default_nobody_chose(tmp_path):
    """The other way to reach the refusal, and the one the fix created.

    A job-level answer is written FROM a resume. With an empty library there is
    no base to name, and sending the job alone would have the route ground on
    its own generic default — a document the user never picked, on an install
    that need not even carry one. So the drawer declines, in `useBaseAsIs`'s own
    words for the same state.
    """
    out = _qna(tmp_path, open=True, question="Why us?", ask=True,
               stored={"widget.session": entry(applicationId=None, baseArmed=True,
                                               pdfReady=False, baseSlug=None)},
               api={"/api/qa": QA_REPLY, "/api/base-resumes": _reply([])})
    assert _qa_posts(out) == []
    [note] = _by_class(out["answered"]["foot"], "note")
    assert note["text"] == "No base resume yet — build one in Maestro CS."


def test_a_refused_ask_reads_as_what_the_backend_said(tmp_path):
    """The guard's other end, driven from the surface that shows it.

    `run_qa` answers an unreadable base resume with a 400 and a detail naming
    the slug; sw.js lifts `detail` out of the body and it arrives here as the
    error's message. What the user must NOT see is the shape this replaced —
    an unexplained 500, which reads as "the product is broken" for what is
    really "that resume has no data file".
    """
    detail = ("Base resume 'ai_ml_engineer' is active but has no data file")
    out = _qna(tmp_path, open=True, question="Why us?", ask=True,
               stored={"widget.session": entry(applicationId=None, baseArmed=True,
                                               pdfReady=False)},
               api={"/api/qa": {"ok": False, "error": detail}})
    # It was asked — this is the backend declining, not the panel refusing.
    assert len(_qa_posts(out)) == 1
    [note] = _by_class(out["answered"]["foot"], "note")
    assert note["text"] == detail
    assert note["class"] == "note error"
    # Nothing is claimed about an answer that never came.
    assert _by_class(out["answered"]["rail"], "ans") == []


def test_an_empty_box_is_not_a_question(tmp_path):
    """The pause row's rule, one control over: pressing Ask with nothing typed
    spends a round trip to have a model answer an empty string."""
    out = _qna(tmp_path, open=True, question="   ", ask=True, **_with_application())
    assert _qa_posts(out) == []
    [note] = _by_class(out["answered"]["foot"], "note")
    assert note["text"] == "Paste a question first."


def test_an_essay_from_the_run_fills_the_composer_in_one_press(tmp_path):
    """THE HANDOFF. The runner routes a QUESTIONY textarea to the essay lane
    precisely because it wants a written answer rather than a control on the
    page, and hands the queue over early — so the drawer is where it lands.

    ONE LIST, not two: the essay keeps its place among the fields that are still
    open, because "what is still open" is the user's question and an unanswered
    essay is exactly as open as an abstained dropdown. What it gains is a second
    button that fills the box below with its own question — no retyping a
    paragraph-long prompt into a composer six lines under it.
    """
    out = _qna(tmp_path, start=True, essay=ESSAY_LABEL, ask=True,
               **_with_application())
    # The row is where it was, with its jump intact: the user still has to reach
    # the box on the page to paste into.
    [item] = [row for row in _by_class(out["afterRun"]["rail"], "resid")[0]["children"]
              if ESSAY_LABEL in _jump_label(row)]
    assert _jump_label(item) == f"{ESSAY_LABEL} · written answer"
    # …and the handoff beside it, saying which question it will ask — "Ask" on
    # every essay row is what a screen reader hears out of context.
    [ask] = _by_class(item, "ask")
    assert ask["attrs"]["aria-label"] == f"Ask about {ESSAY_LABEL}"
    # One press, and the question is in the box — the drawer opened with it.
    box = [one for one in _walk(_drawer(out["opened"]["rail"]))
           if one["tag"] == "TEXTAREA"]
    assert [one["value"] for one in box] == [ESSAY_LABEL]
    # …and the ask that follows carries that question verbatim.
    assert _qa_posts(out) == [{"application_id": "app-remembered",
                               "questions": [ESSAY_LABEL]}]


def test_the_answer_goes_to_the_clipboard_and_the_button_says_so(tmp_path):
    """Copy is the point of this drawer: the panel deliberately does not write
    an essay into the page, because it is the one thing on an application a
    person should read before it is submitted in their name.

    IT SAYS WHAT IT DID IN THE CONTROL THAT DID IT. The footer's note slot holds
    one sentence about the page; "Copied" is feedback about a press, and
    spending the page's sentence on it would overwrite what the ask just said.
    """
    out = _qna(tmp_path, open=True, question="Why us?", ask=True, copy=True,
               **_with_application())
    # What was copied is what was READ — the sanitized paragraph, not the raw
    # reply the backend sent.
    assert out["copies"] == [QA_ANSWER]
    [copy] = _by_class(_drawer(out["settled"]["rail"]), "copy")
    assert copy["text"] == "Copied"
    # The ask's own sentence is still the note: no copy spam in the one slot.
    [note] = _by_class(out["settled"]["foot"], "note")
    assert note["text"] == "Saved to this application’s Q&A history."


def test_a_clipboard_that_refuses_says_so_rather_than_looking_ignored(tmp_path):
    """A Copy that silently did nothing is the Jobscan failure this surface
    keeps naming — the user cannot tell a broken control from a slow one. The
    refusal is real (a document that lost focus), so the sentence is too."""
    out = _qna(tmp_path, open=True, question="Why us?", ask=True, copy=True,
               clipboardThrows=True, **_with_application())
    assert out["copies"] == []
    [note] = _by_class(out["settled"]["foot"], "note")
    assert note["text"].startswith("Could not copy:")
    assert note["class"] == "note error"
    # The button never claims the copy it did not make.
    [copy] = _by_class(_drawer(out["settled"]["rail"]), "copy")
    assert copy["text"] == "Copy"


def test_nothing_else_can_be_started_while_a_question_is_open(tmp_path):
    """Task 13's rule, one control over: `busy` covers everything an action
    writes, and every control on the surface reads it to decide whether it may
    be pressed.

    The ask takes the FILL stage's busy — which is where the drawer lives — so
    the footer's primary, the mode segments and the box itself are all out of
    reach for the length of the round trip. A second Ask underneath the first is
    a second POST nobody asked for, and the answer that came back second would
    win.
    """
    out = _qna(tmp_path, start=True, open=True, question="Why us?", ask=True,
               askAgain=True, hold=["/api/qa"], **_with_application())
    asking = out["asking"]
    [cta] = _by_class(asking["foot"], "cta")
    assert cta["disabled"] is True
    assert [one["disabled"] for one in _by_class(asking["rail"], "seg")[0]["children"]] \
        == [True, True]
    drawer = _drawer(asking["rail"])
    assert [one["disabled"] for one in _walk(drawer) if one["tag"] == "TEXTAREA"] == [True]
    assert _by_class(drawer, "save")[0]["disabled"] is True
    # The essay rows' own Ask with them. It is the VISIBLE half of a refusal the
    # action already makes (`askQuestion` returns on `busy`), and a live control
    # that swallows the click is the broken/busy confusion this surface names.
    assert [one["disabled"] for one in _by_class(asking["rail"], "ask")] == [True]
    # …and the second press was not a second question.
    assert len(_qa_posts(out)) == 1


def test_an_answer_that_lands_after_you_switch_tabs_paints_nothing(tmp_path):
    """THE GENERATION RULE, on the newest round trip in the file.

    An answer is grounded in the posting it was asked about, so one that painted
    after a tab switch would offer a paragraph about a job the user has left —
    ready to be copied into a different employer's form, which is the worst
    version of that mistake. The drawer is cleared by `resetPageFacts` and the
    late answer is discarded by `duringAction`'s guard on both limbs.
    """
    out = _qna(tmp_path, open=True, question="Why us?", ask=True, switchTo=42,
               hold=["/api/qa"], tabUrls={"42": OTHER_URL}, **_with_application())
    # The question was asked — this is a race, not a refusal.
    assert len(_qa_posts(out)) == 1
    # …and nothing about it reached the tab the user is now on.
    settled = out["settled"]
    assert _by_class(settled["rail"], "ans") == []
    [note] = _by_class(settled["foot"], "note")
    assert "Q&A history" not in note["text"]


def test_an_answer_lands_on_the_drawer_as_it_is_now_and_not_as_it_was(tmp_path):
    """THE RE-READ PAST THE GUARD, pinned through the one thing that can move.

    `askQuestion` snapshots the store before the POST and writes the answer
    after it, so the write has to be built from a FRESH read — the handle's own
    rule, because the four loaders are writing to this store for the length of
    any round trip. What makes it observable here is the trigger: it is the one
    control the drawer does NOT grey during an ask (a disclosure claims nothing,
    and reading the still-open list under it is free), so a user can fold the
    composer away while their question is on the wire.

    Spread from the stale snapshot, the answer would arrive carrying `open:
    true` and the drawer would pop itself back open — a panel undoing something
    the user did, seconds later, for no reason they can see.

    NOT DRIVEN BY TYPING, which was the obvious shape and is unreachable: the
    box IS disabled during an ask (see the busy test), so there are no
    characters to keep. The property is the same one; this is the observable
    that exists.
    """
    out = _qna(tmp_path, open=True, question="Why us?", ask=True,
               closeDuringAsk=True, hold=["/api/qa"], **_with_application())
    # It was asked and it was answered — this is about where the answer landed.
    assert len(_qa_posts(out)) == 1
    drawer = _drawer(out["answered"]["rail"])
    assert _by_class(drawer, "linkish")[0]["attrs"] == {"aria-expanded": "false"}
    assert [one for one in _walk(drawer) if one["tag"] == "TEXTAREA"] == []
    # …and nothing was lost by closing: the answer is there on reopening.
    reopened = _qna(tmp_path, open=True, question="Why us?", ask=True,
                    closeDuringAsk=True, hold=["/api/qa"], close=True,
                    **_with_application())
    [answer] = _by_class(_drawer(reopened["settled"]["rail"]), "a")
    assert answer["text"] == QA_ANSWER


def test_a_pasted_question_survives_a_repaint_it_did_not_ask_for(tmp_path):
    """The Job preview's rule, and it bites harder here: this box holds a
    paragraph. Every render rebuilds the rail, so characters kept in the element
    are lost to any repaint — a note landing, a mode segment pressed, a load
    returning."""
    out = _qna(tmp_path, open=True, question="Tell us about a hard project.",
               repaintBeforeAsk=True, **_with_application())
    box = [one for one in _walk(_drawer(out["typed"]["rail"]))
           if one["tag"] == "TEXTAREA"]
    assert [one["value"] for one in box] == ["Tell us about a hard project."]


def test_folding_the_drawer_away_is_not_withdrawing_the_question(tmp_path):
    """A drawer, not a reset button: a user who folds the composer away to read
    the still-open list under it has not taken their question back. Only a page
    change clears it, which is a different event with a different meaning."""
    out = _qna(tmp_path, open=True, question="Why us?", ask=True, close=True,
               **_with_application())
    settled = out["settled"]
    drawer = _drawer(settled["rail"])
    # Closed: no box, no answer on screen.
    assert [one for one in _walk(drawer) if one["tag"] == "TEXTAREA"] == []
    assert _by_class(drawer, "ans") == []
    assert _by_class(drawer, "linkish")[0]["attrs"]["aria-expanded"] == "false"


# ---------- the attach: the tailored PDF into the page's upload box ----------
#
# THE GAP THIS CLOSES was found on a live Workday wizard: the panel filled the
# form and the tailored résumé never reached the page's upload box, so the user
# attached it by hand. The engine could always do it — `attach_pdf` (sw.js) and
# `attachResumePdf` (content/agent.js) are the floating card's, and have been
# since it was written. What did not exist was a way to ASK for it from this
# surface.
#
# OFFERED, NEVER TAKEN, which is what most of this section is about. A fill
# writes text a user can read back at a glance; an upload is a whole document
# going to an employer. So the press is the whole of the decision, the offer is
# absent when there is nothing to attach or nowhere to put it, and an ambiguous
# page is refused with a sentence rather than resolved by picking a box.

_ATTACH_DRIVER_JS = _PANEL_FAKES_JS + r"""
loadModules();
const attachBox = () => withClass(REGIONS.rail, "attach")[0] ?? null;
const attachButton = () => {
  const box = attachBox();
  return box ? withClass(box, "save")[0] : null;
};
main(async () => {
  await settle();
  // A FILL FIRST, when the fixture asks for one. It is the ordinary order —
  // fill the page, then attach the résumé to it — and it is also what lets the
  // attach finish the step: an attach is evidence about the upload box and not
  // about the form, so the tick waits for something to have LOOKED at the form.
  if (spec.fillFirst === true) {
    withClass(REGIONS.foot, "cta")[0].click();
    await settle();
    release();
    await settle();
  }
  const loaded = regions();
  let clicked = null;
  if (spec.press === true) {
    const button = attachButton();
    if (!button) throw new Error("no attach control on the Fill body");
    button.click();
    // Synchronous, the file's rule: the action paints `busy` before its first
    // await, so this is the surface as the user sees it while the attach is
    // open.
    clicked = regions();
    await settle();
    if (spec.switchTo !== undefined) {
      await onActivated({ tabId: spec.switchTo });
      await settle();
    }
    release(spec.releaseOrder);
    await settle();
  }
  // A POKE AFTER THE RUN, which is `pokeDuringLearn`'s technique and its
  // reason: a stale write that lands with nothing repainting afterwards is
  // INVISIBLE until the user next touches the surface, and `duringAction`'s
  // catch deliberately does not render on a stale generation. A mode segment
  // repaints the rail, and the repaint is what the bug rides in on — so
  // without this a test about a late write asserts over the DOM that was
  // painted before the write existed, and passes whatever the store holds.
  if (spec.pokeAfter === true) {
    withClass(REGIONS.rail, "seg")[0].children[0].click();
    await settle();
  }
  emit({ loaded, clicked, settled: regions(), sent, writes,
         offered: attachBox() !== null,
         disabled: attachButton()?.disabled ?? null });
});
"""

# What `attach_pdf` answers: the SW's per-frame array, whose `result` is how
# many boxes in that frame really took the file (`attachResumePdf` re-reads
# `input.files`). One frame, one box.
ATTACH_ONE = _reply([{"frameId": 0, "result": 1}])
# The page answered and had nowhere to put it — a FINDING about the page.
ATTACH_NONE = _reply([{"frameId": 0, "result": 0}])
# Nobody answered at all — a fact about our reach, and a different sentence.
ATTACH_UNREACHED = _reply([{"frameId": 0, "error": "Could not establish connection"}])

_TAILORED_DETAIL = {"id": "app-remembered", "status": "draft", "applied_at": None,
                    "pdf_path": "renders/app-remembered/tailored-resume.pdf"}


def _attach(tmp_path, *, file_inputs=1, detail=None, attach_reply=ATTACH_ONE, **spec):
    """Boot on the apply page of a job whose application is already tailored,
    with the page reporting `file_inputs` upload boxes.

    The entry carries an application and `pdfReady`, which is what puts the
    offer on screen at all — the two gates are "there is a document" and "there
    is somewhere to put it", and this fixture varies the second.
    """
    spec.setdefault("tabs", [{"id": 7, "url": LIGHTNING_APPLY_URL}])
    spec.setdefault("stored", {"widget.session": entry(touched=False)})
    spec.setdefault("page", {"detect_page": _reply(
        {"tier": "B", "form": True, "score": 2, "fileInputs": file_inputs})})
    replies = {"read_settings": SETTINGS_REPLY,
               "panel_prepare": _reply({"injected": True}),
               "attach_pdf": attach_reply,
               "telemetry": _reply({"posted": 0})}
    # A run that leaves NOTHING open, which is the only run an attach can
    # finish the step on top of — the point under test is the attach, not the
    # residue, and `CLEAN_COLLECT_FRAMES` is this file's own fixture for it.
    spec.setdefault("frames", {"profile_fill": PROFILE_FRAMES,
                               "collect_open_questions": CLEAN_COLLECT_FRAMES,
                               "guided_write": True})
    replies.update(spec.pop("replies", {}))
    # THE APPLICATION DETAIL MAY BE A LIST, consumed in order with the last
    # repeating (the harness's own shape). That is what lets one fixture model
    # the race the re-read exists for: the PDF was there when the panel loaded
    # and gone by the time the user pressed.
    api = {"lightningai": _reply({"match": "none", "job": None, "application": None}),
           "/api/base-resumes": _reply(BASE_RESUMES),
           "/api/ats-scores": _reply(SCORES),
           "/api/autofill/context": _reply(FILL_CONTEXT),
           "/api/autofill/choose": CLEAN_CHOOSE_REPLY,
           "GET /api/applications/app-remembered":
               detail if isinstance(detail, list) else _reply(detail or _TAILORED_DETAIL)}
    api.update(spec.pop("api", {}))
    return run_node(_ATTACH_DRIVER_JS, {**spec, "api": api, "replies": replies},
                    tmp_path, source=PANEL_SOURCE)


def _attach_text(regions):
    """The offer's whole line, out of the rail region it lives in."""
    box = _by_class(regions["rail"], "attach")
    return _text(box[0]) if box else ""


def test_one_upload_box_is_offered_an_attach_that_names_the_file(tmp_path):
    """The ordinary case, and the whole point of the round. The filename is the
    application's own `pdf_path`, split the way `evidenceFrom` splits it — the
    user has a specific name for this document and the offer uses it rather than
    saying "your resume" about it."""
    out = _attach(tmp_path)
    assert out["offered"] is True
    assert out["disabled"] is False
    assert "tailored-resume.pdf" in _attach_text(out["loaded"])


def test_a_tracked_application_on_a_form_less_page_is_refused_its_primary(tmp_path):
    """The refusal is APPLICATION-AGNOSTIC, and this is the pin that keeps it
    so. Every other test of the no-form refusal arms the base-as-is shortcut;
    this one reaches Fill the ladder's way — a remembered application with a
    tailored PDF — on a page that answers `form: false`. Before 2026-08-19 the
    ladder's own fill rung never consulted the form verdict at all, so exactly
    this state offered "Start fill" into nothing. A later "only the shortcut
    needs the gate" simplification (`fillFromBase && !hasForm`) would reopen
    that hole; this test is what goes red when it does.
    """
    out = _attach(tmp_path, file_inputs=0, page={"detect_page": _reply(
        {"tier": "A", "form": False, "score": 0, "fileInputs": 0})})
    assert _by_class(out["loaded"]["foot"], "cta") == []
    assert _by_class(out["loaded"]["rail"], "sub")[0]["text"] == (
        "No application form on this page — open the employer's Apply page; "
        "filling starts there.")


def test_a_page_with_no_upload_box_is_offered_nothing_at_all(tmp_path):
    """Not a disabled button. A control that can never become pressable on this
    page is furniture that asks the user to work out why, and "this page has no
    upload box" is the ordinary case for most of the web."""
    out = _attach(tmp_path, file_inputs=0)
    assert out["offered"] is False


def test_several_upload_boxes_are_refused_with_a_sentence(tmp_path):
    """AMBIGUITY IS REPORTED, NOT RESOLVED. The panel cannot tell a résumé box
    from a cover-letter box from a transcript box, and putting the résumé in the
    wrong one is worse than not offering: the page would look like it worked.

    The button stays rendered and dead here, unlike the zero case, because there
    IS something to attach and the user needs the reason.
    """
    out = _attach(tmp_path, file_inputs=3)
    assert out["offered"] is True
    assert out["disabled"] is True
    assert "3 upload boxes" in _attach_text(out["loaded"])
    # Nothing was asked of the page — the refusal is a render, not a round trip.
    assert [msg for msg in out["sent"] if msg["type"] == "attach_pdf"] == []


def test_nothing_is_offered_without_a_rendered_pdf(tmp_path):
    """The other gate. An offer to attach a document that has not been rendered
    is an offer that resolves to an error message."""
    out = _attach(tmp_path, detail={"id": "app-remembered", "status": "draft",
                                    "applied_at": None, "pdf_path": None})
    assert out["offered"] is False


def test_the_press_is_the_whole_of_the_decision(tmp_path):
    """NOTHING IS ATTACHED WITHOUT ONE. A load, a detect and a render all happen
    before the user has decided anything, and an upload that rode one of them
    would be this extension sending a document to an employer on its own."""
    out = _attach(tmp_path)
    assert [msg for msg in out["sent"] if msg["type"] == "attach_pdf"] == []


def test_pressing_it_re_reads_the_pdf_then_fans_the_bytes_out_from_the_sw(tmp_path):
    """The wire, in order. The application detail is re-read rather than assumed
    — `pdfReady` was true when the panel last loaded, and a re-render since then
    would make this a 404 with a worse message — and the fan-out is a message,
    so the bytes never touch this document."""
    out = _attach(tmp_path, press=True)
    [ask] = [msg for msg in out["sent"] if msg["type"] == "attach_pdf"]
    assert ask["path"] == "/api/applications/app-remembered/pdf"
    assert ask["filename"] == "tailored-resume.pdf"
    # The tab is bound by the panel and never named by the action.
    assert ask["tabId"] == 7
    # The panel injects before it asks, the same door `startFill` uses: a tab
    # open since before the extension reloaded has no content scripts.
    assert [msg["type"] for msg in out["sent"]].count("panel_prepare") == 1


def test_the_press_states_the_count_the_offer_was_made_on(tmp_path):
    """THE REFUSAL TRAVELS WITH THE WRITE. The offer's whole three-way decision
    rests on frame 0's box count taken at DETECT time, and the write happens at
    PRESS time across every gated frame — so the panel sends what it believed
    and the engine refuses any frame that no longer agrees. Without this the
    refusal is decoration: the page grows a cover-letter box, the offer still
    says "one", and the résumé goes into both."""
    out = _attach(tmp_path, press=True)
    [ask] = [msg for msg in out["sent"] if msg["type"] == "attach_pdf"]
    assert ask["expect"] == 1


def test_a_page_that_grew_a_box_since_the_offer_attaches_nothing_and_says_why(tmp_path):
    """The panel half of the refusal, end to end.

    Zero attached has TWO causes and they are different news — the boxes refused
    the file, or the page grew one and the engine refused the write — so the
    panel asks the page again rather than guessing. The fresh count is WRITTEN
    BACK, which is what makes the row itself say why: it flips to the
    several-boxes refusal, in the same words the offer would have used had the
    page looked like this when we first asked.

    The detect replies are ordered: one box at bind, two at the re-ask.
    """
    out = _attach(tmp_path, press=True, attach_reply=ATTACH_NONE,
                  page={"detect_page": [
                      _reply({"tier": "B", "form": True, "score": 2, "fileInputs": 1}),
                      _reply({"tier": "B", "form": True, "score": 2, "fileInputs": 2})]})
    settled = out["settled"]
    assert "upload boxes changed while you were pressing" in (
        _by_class(settled["foot"], "note")[0]["text"])
    # Nothing is claimed…
    assert "Resume attached" not in dict(_rows_of(settled["rail"]))
    # …and the row now carries the reason, with the page's real count in it.
    assert "This page has 2 upload boxes" in _attach_text(settled)
    assert _by_class(settled["rail"], "save")[0]["disabled"] is True


def test_a_page_whose_boxes_simply_refused_keeps_its_own_sentence(tmp_path):
    """The other branch of the same zero, and what stops the message above from
    being printed over every failure: the re-ask agrees with what we sent, so
    the boxes are the same boxes and they turned the file down."""
    out = _attach(tmp_path, press=True, attach_reply=ATTACH_NONE)
    note = _by_class(out["settled"]["foot"], "note")[0]["text"]
    assert "No upload box on this page took the file" in note
    assert "changed while you were pressing" not in note


def test_an_attach_that_landed_is_reported_as_what_it_is(tmp_path):
    """The offer becomes a report row — the file, and how many boxes really hold
    it. The count is the engine's readback rather than the number of frames
    asked, so "1 upload box" is a box that took the file."""
    out = _attach(tmp_path, press=True)
    settled = out["settled"]
    rows = dict(_rows_of(settled["rail"]))
    assert "Resume attached" in rows
    assert rows["Resume attached"] == "tailored-resume.pdf · 1 upload box"
    # …and the offer is gone: there is no second press, because the interesting
    # failure is an attach that went somewhere unexpected and offering to repeat
    # it is how a user ends up with two.
    assert _by_class(settled["foot"], "note")[0]["text"] == (
        "Attached tailored-resume.pdf. Check the upload before you submit.")


def test_an_attach_alone_does_not_tick_a_form_nobody_looked_at(tmp_path):
    """An attach is evidence about the upload box, not about the form. Without
    this, a Workday page with twenty empty fields would tick Fill the moment the
    résumé landed — "wrote something, left nothing open", the second half true
    only because nothing had ever looked — and a done row has no body, so the
    tick would take the attach's own report off screen with it."""
    out = _attach(tmp_path, press=True)
    rows = _rows(_rail_rows({"regions": out["settled"]}))
    assert rows["fill"]["state"] == "active"
    # The report is on screen precisely BECAUSE the step did not tick.
    assert "Resume attached" in dict(_rows_of(out["settled"]["rail"]))


# THE UPLOAD-ONLY PAGE, which is the case the attach's tick is really about: an
# ATS step whose whole content is "upload your résumé". A run there reaches the
# page and honestly writes nothing, so the fill alone can never finish the step
# — and the attach is the work.
UPLOAD_ONLY_PROFILE_FRAMES = [{"frameId": 0, "result": {
    "filled": [], "corrected": [], "eeoFilled": [], "already": [],
    "seen": 0, "observations": [],
}}]
UPLOAD_ONLY_COLLECT_FRAMES = [{"frameId": 0, "result": {
    "host": "lightningai.wd5.myworkdayjobs.com",
    "questions": [], "retryables": [],
}}]


def test_the_attach_finishes_an_upload_only_step_and_is_remembered(tmp_path):
    """`done.fill` is documented in decisions.js as this extension's claim that
    it "filled OR ATTACHED here", and until this round there was no attach on
    this surface for that clause to describe. On a step whose whole content is
    an upload box, the fill writes nothing — honestly — and the attach is the
    entire work, so it is what finishes the step.

    THE OTHER HALF is pinned by the test above: the attach may only do this
    once a run has looked at the form. Here one has, and it found nothing to
    fill, which is a different thing from nobody having looked.

    REMEMBERED for `startFill`'s reason: an ATS wizard is six page loads and
    `resetPageFacts` clears the store on every one of them.
    """
    out = _attach(tmp_path, press=True, fillFirst=True,
                  frames={"profile_fill": UPLOAD_ONLY_PROFILE_FRAMES,
                          "collect_open_questions": UPLOAD_ONLY_COLLECT_FRAMES,
                          "guided_write": True})
    rows = _rows(_rail_rows({"regions": out["settled"]}))
    assert rows["fill"]["state"] == "done"
    assert rows["track"]["state"] == "active"
    assert any(write.get("widget.session", {}).get("touched") is True
               for write in out["writes"]), out["writes"]


def test_a_page_that_answered_and_had_nowhere_to_put_it_says_so(tmp_path):
    """A FINDING about the page, and it must not be reported when no frame was
    looked at — the same distinction the fill path makes."""
    out = _attach(tmp_path, press=True, attach_reply=ATTACH_NONE)
    note = _by_class(out["settled"]["foot"], "note")[0]
    assert "No upload box on this page took the file" in note["text"]
    # Nothing is claimed: no report row, and the step is not ticked.
    assert "Resume attached" not in dict(_rows_of(out["settled"]["rail"]))
    assert _rows(_rail_rows({"regions": out["settled"]}))["fill"]["state"] != "done"


def test_a_page_nobody_reached_gets_the_other_sentence(tmp_path):
    """"No box here" and "we could not talk to this tab" are different bugs, and
    the second is the one whose fix is reloading the tab."""
    out = _attach(tmp_path, press=True, attach_reply=ATTACH_UNREACHED)
    note = _by_class(out["settled"]["foot"], "note")[0]
    assert "No upload box" not in note["text"]
    assert note["text"] != ""


def test_a_pdf_that_is_gone_takes_the_offer_away_with_the_message(tmp_path):
    """The re-read's whole reason. `pdfReady` is what put the control on screen,
    so leaving it true would keep offering an attach for a document that is not
    there — and the user would press it again."""
    gone = {"id": "app-remembered", "status": "draft", "applied_at": None,
            "pdf_path": None}
    out = _attach(tmp_path, press=True,
                  detail=[_reply(_TAILORED_DETAIL), _reply(gone)])
    assert "not rendered anymore" in _by_class(out["settled"]["foot"], "note")[0]["text"]
    assert _by_class(out["settled"]["rail"], "attach") == []
    assert [msg for msg in out["sent"] if msg["type"] == "attach_pdf"] == []


def test_a_gone_pdf_answered_after_a_tab_switch_never_stamps_the_new_page(tmp_path):
    """THE WRITE INSIDE THE RUN, which `duringAction`'s own guard cannot cover.

    `duringAction` checks the generation on both its limbs, but that is after
    the run RETURNS — and the "this PDF is gone" correction fires from INSIDE
    it, past two awaits (`prepare`, then the detail GET). Without its own check
    the answer about the application the user LEFT is stamped onto the one they
    are now looking at: tab B's `pdfReady` goes false, its Resume stage re-offers
    a tailor for an application whose PDF is fine, and its attach offer vanishes.

    THE SWITCH IS TO THE NEXT STEP OF THE SAME WIZARD, the trap two tests below
    this one: a non-tenant page is at Job, renders no Fill body, and would make
    the assertion vacuous. Tab B is at Fill with a good PDF of its own, so the
    stamp is a thing that can be SEEN.

    THE REPLIES DRAIN NEWEST FIRST, and that is the only ordering the browser
    produces here: tab A's read has already been in flight when the user
    switches, and the load tab B starts after the switch is issued last and
    answers first. Draining oldest-first instead lets tab B's own load land
    after the stale write and repair it — the write is then erased by the very
    load it is racing, and a deleted guard survives. Measured, both ways.

    AND THE SURFACE IS POKED AFTERWARDS, without which this is vacuous a third
    way: `duringAction`'s catch does not render on a stale generation, so the
    bad write sits in the store painting nothing until the user next touches
    the panel. Both of those were measured — with the guard deleted, the
    version without them still passed.
    """
    gone = {"id": "app-remembered", "status": "draft", "applied_at": None,
            "pdf_path": None}
    next_step = f"{LIGHTNING_APPLY_URL}/step2"
    out = _attach(tmp_path, press=True, switchTo=9,
                  hold=["/api/applications/app-remembered"],
                  tabs=[{"id": 7, "url": LIGHTNING_APPLY_URL}],
                  tabUrls={"9": next_step}, pokeAfter=True, releaseOrder="newest",
                  detail=[_reply(_TAILORED_DETAIL), _reply(gone),
                          _reply(_TAILORED_DETAIL)])
    settled = out["settled"]
    # Tab B still has its document, so it still has its offer. Without the guard
    # this is empty and the sentence below is on screen.
    assert _by_class(settled["rail"], "attach") != []
    assert "not rendered anymore" not in json.dumps(settled)


def test_the_control_is_out_of_reach_while_the_attach_is_open(tmp_path):
    """`actingLimb`'s rule: a control that stayed live would send a second
    document into a page the first ask is still walking."""
    out = _attach(tmp_path, press=True, hold=["/api/applications/app-remembered"])
    [button] = _by_class(out["clicked"]["rail"], "save")
    assert button["attrs"].get("disabled") is True or button.get("disabled") is True


def test_an_attach_that_lands_on_a_tab_the_user_left_changes_nothing(tmp_path):
    """The generation rule, over the longest round trip this action has. A user
    who switches tabs mid-attach is the ordinary case, not the unlucky one.

    THIS TEST WAS VACUOUS TWICE OVER when it was first written, and both halves
    are the trap `test_progress_from_a_fill_on_another_tab_never_paints_this_one`
    documents twenty rows up — which is what makes writing it wrong here worth
    recording rather than quietly fixing:

    - NO HOLD, so the whole attach completed before `onActivated` ever fired.
      There was no round trip open for the generation guard to catch, so the
      test could not have been about the guard whatever else it did.
    - `tab_urls` IS NOT A KEY. The harness reads `tabUrls`, so the switch target
      had no url at all — a non-tenant page, whose rail is at Job and renders no
      Fill body, so the assertion was "Resume attached" not in `{}`. It passed
      over an empty dict.

    Measured: with the token check deleted from `during.js` outright, the
    original version stayed green.

    THE SWITCH IS TO THE NEXT STEP OF THE SAME WIZARD, for that test's reason:
    same tenant, so the arming restores and tab B is itself at Fill with a body
    waiting to render. That is the tab that can SHOW the bug — a late write
    would paint tab A's attach as tab B's.
    """
    next_step = f"{LIGHTNING_APPLY_URL}/step2"
    out = _attach(tmp_path, press=True, switchTo=9,
                  hold=["/api/applications/app-remembered"],
                  tabs=[{"id": 7, "url": LIGHTNING_APPLY_URL}],
                  tabUrls={"9": next_step})
    settled = out["settled"]
    # Tab B is at Fill and its body is the pre-run offer, carrying no report of
    # an attach that happened on a page the user has left.
    assert _rows(_rail_rows({"regions": settled}))["fill"]["state"] == "active"
    assert "Resume attached" not in dict(_rows_of(settled["rail"]))
    # …and the footer says nothing either: the note is the OTHER thing this
    # action writes, and a sentence naming tab A's filename over tab B's form is
    # the same lie in the other slot.
    assert _by_class(settled["foot"], "note")[0]["text"] == ""
