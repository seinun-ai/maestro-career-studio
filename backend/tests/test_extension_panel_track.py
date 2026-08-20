"""The TRACK stage: status, evidence, the journey's end.

The status control is the FOOTER's and the body renders none — one writer for
one field, which is the claim the driver below builds into `press()` rather
than into an assertion nobody would remember to make. The evidence line says
what this application has to show for itself and says nothing when it has
nothing. `setStatus` is the one PATCH this extension makes, driven through its
busy, refusal, failure, race and success paths.

WHAT THIS FILE DOES NOT PIN, because another one already does: `stageFor`'s
`done.track` and `nudge` table lives in `test_extension_panel.py`'s first
section, driven over the decision directly. Here they are only ever observed
as RENDER — the segment that appears, the sentence that changes — which is the
half that would otherwise be tested nowhere.

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
import time

import pytest

from tests.extension_fixtures import (
    LIGHTNING_APPLY_URL,
    LIGHTNING_TENANT,
    entry,
)
from tests.extension_harness import run_node
from tests.extension_panel_harness import (
    PANEL_SOURCE,
    SCORE_RESUMES,
    SCORE_ROWS,
    SETTINGS_REPLY,
    _armed_entry,
    _by_class,
    _PANEL_FAKES_JS,
    _posts,
    _rail_rows,
    _reply,
    _rows,
    _text,
    _walk,
)


# ---------- the Track stage: status, evidence, the journey's end ----------
#
# THREE SEPARABLE THINGS, and the file is grouped by them: what the body SHOWS
# (a status in words, and the evidence when there is any), where the one status
# WRITER lives (the footer, and nowhere else), and what the PATCH behind it
# does — including the two presses that are deliberately not round trips.

_TRACK_STAGE_DRIVER_JS = _PANEL_FAKES_JS + r"""
const ns = loadModules();
// Every status button on the WHOLE surface, not just the footer's — which is
// the single-writer claim built into the driver rather than left to a test
// somebody has to remember to write. If the Track body ever grew a second
// Draft/Applied pair, `press` below would refuse instead of quietly pressing
// the first one it found.
const statusButtons = () => Object.values(REGIONS)
  .flatMap((region) => withClass(region, "status-seg"))
  .flatMap((seg) => seg.children);
const allButtons = (node) => [
  ...(node.tagName === "BUTTON" ? [node] : []),
  ...node.children.flatMap(allButtons),
];
const press = (label) => {
  const found = statusButtons().filter((button) => button.textContent === label);
  if (found.length !== 1) {
    throw new Error(`${found.length} status controls read "${label}"`);
  }
  found[0].click();
};
const pressTrack = () => {
  const found = allButtons(REGIONS.rail).filter(
    (button) => button.textContent === "Track this application");
  if (found.length !== 1) {
    throw new Error(`${found.length} track-this controls`);
  }
  found[0].click();
};
main(async () => {
  await settle();
  const loaded = regions();
  let clicked = null;
  if (spec.press !== undefined || spec.track === true) {
    if (spec.track === true) pressTrack();
    else press(spec.press);
    // Synchronous, and deliberately: an action paints `busy` before its first
    // await, so this is the surface as the user sees it while the write is on
    // the wire.
    clicked = regions();
    await settle();
    // …and the user is free to leave while it is still open.
    if (spec.switchTo !== undefined) {
      await onActivated({ tabId: spec.switchTo });
      await settle();
    }
    release();
    await settle();
  }
  const facts = ns.panel.actionStore().read();
  emit({ loaded, clicked, settled: regions(), sent, writes,
         statuses: statusButtons().map((button) => button.textContent),
         facts: {
           claimed: facts.claimed === true,
           applicationId: facts.application?.id ?? null,
           match: facts.match,
           jobId: facts.job?.id ?? null,
           baseSlug: facts.baseSlug,
         } });
});
"""

# The application detail, in the two states the panel writes between. The pdf
# path is a SERVER path with directories on it, because that is what the column
# holds and stripping them is `evidenceFrom`'s job rather than the fixture's.
DRAFT_DETAIL = {"id": "app-remembered", "status": "draft", "applied_at": None,
                "pdf_path": "renders/app-remembered/tailored-resume.pdf"}
APPLIED_DETAIL = {"id": "app-remembered", "status": "applied",
                  "applied_at": "2026-08-18T14:32:11+00:00",
                  "pdf_path": "renders/app-remembered/tailored-resume.pdf"}
# What the PATCH answers with: the whole `ApplicationRead`, `applied_at`
# included, which is what makes the evidence line true at the moment of the
# press rather than after the next page load.
PATCHED_APPLIED = _reply(APPLIED_DETAIL)


def _track(tmp_path, detail=DRAFT_DETAIL, **spec):
    """Boot on the apply page of a job whose application is already tailored —
    the Track stage, reached the way a user reaches it.

    ON THE APPLY URL AND FROM THE MEMORY, which is not an incidental choice.
    The rail only reaches Track with `touched` set, and `touched` is restored
    from the session entry — which `loadContext` reads ONLY when the backend
    did not name an application for the page. On the posting the backend names
    it and the restore never runs; on the apply url it names nothing, which is
    exactly the page the memory exists for and exactly the page the user
    presses "Applied" on.
    """
    spec.setdefault("tabs", [{"id": 7, "url": LIGHTNING_APPLY_URL}])
    spec.setdefault("replies", {"read_settings": SETTINGS_REPLY})
    spec.setdefault("stored", {"widget.session": entry(
        touched=True, status=detail["status"], at=int(time.time() * 1000))})
    api = {"lightningai": _reply({"match": "none", "job": None, "application": None}),
           "/api/base-resumes": _reply(SCORE_RESUMES),
           "GET /api/ats-scores": _reply(SCORE_ROWS),
           "GET /api/applications/app-remembered": _reply(detail),
           "PATCH /api/applications/app-remembered": PATCHED_APPLIED}
    api.update(spec.pop("api", {}))
    return run_node(_TRACK_STAGE_DRIVER_JS, {**spec, "api": api}, tmp_path,
                    source=PANEL_SOURCE)


def _patches(out):
    """Every status write the panel made, in order."""
    return [msg for msg in out["sent"]
            if msg["type"] == "api" and (msg.get("init") or {}).get("method") == "PATCH"]


def _track_body(regions):
    """The Track row's body, or None when the row has none."""
    rows = _by_class(regions["rail"], "stg")
    bodies = _by_class(rows[4], "stg-body")
    return bodies[0] if bodies else None


# ---------- what the body shows ----------


@pytest.fixture(scope="module")
def drafted(tmp_path_factory):
    return _track(tmp_path_factory.mktemp("panel_track_draft"))


def test_the_journey_ends_on_the_track_row_and_the_body_says_where_you_are(drafted):
    """The rail's last row is the active one, and the body under it answers the
    only question left: is this application marked as sent?

    The sentence is the STATUS in words, not a repeat of the control beside it.
    The footer's segment says which button is pressed; this says what the state
    MEANS and where the control is, which is the difference between a label and
    an answer.
    """
    rows = _rows(_rail_rows({"regions": drafted["loaded"]}))
    assert rows["track"]["state"] == "active"
    for done in ("job", "score", "resume", "fill"):
        assert rows[done]["state"] == "done", done
    body = _track_body(drafted["loaded"])
    assert "Still a draft" in _text(body)
    assert "mark it Applied below" in _text(body)


def test_the_evidence_line_is_what_the_application_has_to_show_for_itself(drafted):
    """`pdf_path` and `applied_at`, and the two of them are the whole of it.

    "rendered" and not "attached", which is the one word the mockup used that
    this body would not repeat: nothing attached that PDF to anything, it
    exists because a tailor rendered it. The panel says what is true of the
    record it is reading.

    The directories are gone because a server path is not a thing the user has
    any use for — `evidenceFrom` takes the last segment, the widget's own idiom
    where it attaches the same file.
    """
    [line] = _by_class(drafted["loaded"]["rail"], "evi")
    assert _text(line) == "📎 tailored-resume.pdf rendered"
    # The paperclip is decoration and says so: an emoji reaches nobody using a
    # screen reader, so the text beside it has to carry the line on its own —
    # and it does.
    assert line["children"][0]["attrs"]["aria-hidden"] == "true"


def test_an_applied_application_carries_the_day_it_went_out(tmp_path):
    """The second fact, and the one the whole stage is about.

    Sliced from the ISO timestamp rather than formatted: `toLocaleDateString`
    would read the user's locale into one date inside an English sentence, and
    parsing it into a `Date` would be this panel taking a position on a
    timezone the backend already resolved.
    """
    out = _track(tmp_path, detail=APPLIED_DETAIL)
    [line] = _by_class(out["loaded"]["rail"], "evi")
    assert _text(line) == "📎 tailored-resume.pdf rendered · applied 2026-08-18"
    assert "Marked applied" in _text(_track_body(out["loaded"]))


def test_an_application_that_was_never_tailored_shows_only_the_day_it_went_out(
        tmp_path):
    """The shell's `applied_no_pdf` state, rendered: an application attached
    through "track this" and then marked applied has no tailored PDF at all.

    ONE FACT, so one part — and NO PAPERCLIP, because the glyph belongs to the
    document and there is no document. A decoration that stayed put over a line
    about a date would be reporting an attachment that does not exist.
    """
    out = _track(tmp_path, detail={**APPLIED_DETAIL, "pdf_path": None})
    [line] = _by_class(out["loaded"]["rail"], "evi")
    assert _text(line) == "applied 2026-08-18"
    assert len(line["children"]) == 1


def test_an_application_with_nothing_to_show_gets_no_line_at_all(tmp_path):
    """HONEST ABSENCE, and it is the point of the line rather than an edge case.

    "📎 —" under a step about whether the application went out is a row
    reporting its own emptiness as a fact, so there is no row: the status
    sentence stands alone.

    The record is reachable rather than invented: `PATCH` respects a caller's
    own `applied_at` when it is supplied in the same body
    (`patch_application`), so an application marked applied with an explicit
    null — and never tailored, so never rendered — carries neither fact.
    """
    out = _track(tmp_path, detail={**APPLIED_DETAIL, "pdf_path": None,
                                   "applied_at": None})
    assert _by_class(out["loaded"]["rail"], "evi") == []
    assert "Marked applied" in _text(_track_body(out["loaded"]))


def test_a_page_filled_from_the_base_says_nothing_was_written_down(tmp_path):
    """The OTHER way the rail reaches Track: a fill that finished from the base
    resume, with no application behind it.

    `stageFor` calls that `track-this`. There is no status to be draft ABOUT,
    so the footer renders no segment — and a stage body that showed one anyway
    would be naming a thing that does not exist. The from-base route needs a
    `job_id`; this fixture never saved the posting, so the body still says
    what happened and where to finish it rather than offering a button whose
    POST would 404. The header's "Open in Maestro CS ↗" is that route.
    """
    out = _track(tmp_path, stored={"widget.session": {**_armed_entry(),
                                                      "touched": True}},
                 page={"detect_page": _reply({"form": True})})
    rows = _rows(_rail_rows({"regions": out["loaded"]}))
    assert rows["track"]["state"] == "active"
    body = _track_body(out["loaded"])
    assert "filled from your base resume" in _text(body)
    assert "Open Maestro CS" in _text(body)
    # No application, so no control: the footer's segment is gated on the
    # decision, and this decision's nudge is not `mark-applied`.
    assert out["statuses"] == []


def test_a_status_this_panel_cannot_write_is_not_offered_a_two_value_control(tmp_path):
    """`ALLOWED_STATUSES` has seven and this surface writes two.

    An application moved to `interviewing` in the web app would render with
    NEITHER button checked, and pressing Draft would walk the record backwards
    past three states — so the segment is withheld rather than shown wrong. The
    identity chip still names the status and the body's own sentence says where
    to change it, so nothing is hidden; what is withheld is a two-value control
    over a seven-value field.
    """
    out = _track(tmp_path, detail={**DRAFT_DETAIL, "status": "interviewing"})
    assert out["statuses"] == []
    assert _by_class(out["loaded"]["identity"], "chip")[0]["text"] == (
        "Application · interviewing")
    assert "Status: interviewing" in _text(_track_body(out["loaded"]))


# ---------- one control writes the status, and it is in the footer ----------


def test_the_status_control_is_the_footers_and_the_body_builds_no_second_one(drafted):
    """THE SINGLE-WRITER PIN, and the reason this stage is arranged the way it
    is.

    Design §Footer put the status segment in the footer permanently — "the
    mark-applied nudge lives here permanently, no more hunting" — so the Track
    body is the richer view BESIDE it rather than a second copy of it. Two
    Draft/Applied pairs on one screen are two writers for one field, and the
    user cannot tell which one they pressed.

    Asserted over the whole document rather than over the footer, because the
    failure this pins is a control appearing somewhere it should not.
    """
    assert drafted["statuses"] == ["Draft", "Applied"]
    assert len(_by_class(drafted["loaded"]["foot"], "status-seg")) == 1
    assert _by_class(drafted["loaded"]["rail"], "status-seg") == []
    # And the body offers no control of ANY kind — the rule rather than the
    # shape. Walked by tag over the whole subtree, because the failure this
    # pins is a button that does not look like the footer's: an unclassed
    # "Mark applied" wired straight to `setStatus` is a second writer, and a
    # query narrowed to `status-seg` would never see it.
    body = _track_body(drafted["loaded"])
    assert [node["tag"] for node in _walk(body) if node["tag"] == "BUTTON"] == []


def test_the_segment_says_which_state_it_is_in_to_something_that_cannot_see_it(drafted):
    """A radiogroup on real buttons, `baseRow`'s and `modeControl`'s shape — so
    `aria-checked` rather than the tint alone, because "is this application
    marked applied" is exactly the thing a user must not have to infer from a
    background colour."""
    [segment] = _by_class(drafted["loaded"]["foot"], "status-seg")
    assert segment["attrs"]["role"] == "radiogroup"
    assert segment["attrs"]["aria-label"] == "Application status"
    assert [button["attrs"]["aria-checked"] for button in segment["children"]] == [
        "true", "false"]
    # The two tints are two different states, not one class reused: a draft is
    # unfinished business, an applied one is the end of the journey.
    assert [button["class"] for button in segment["children"]] == ["draft-on", ""]


def test_an_applied_application_keeps_the_control_that_the_nudge_no_longer_asks_for(
        tmp_path):
    """The footer honours `stageFor().nudge` WITH the control, and this is the
    half of that wiring the draft case cannot show.

    A draft carries `nudge: "mark-applied"` and that is what puts the segment
    there. Once it is applied the nudge is gone — there is nothing left to
    prompt — and the segment stays because `done.track` is true: the control is
    also how the state is READ, and how a mis-press is taken back.
    """
    out = _track(tmp_path, detail=APPLIED_DETAIL)
    [segment] = _by_class(out["loaded"]["foot"], "status-seg")
    assert [button["attrs"]["aria-checked"] for button in segment["children"]] == [
        "false", "true"]
    assert [button["class"] for button in segment["children"]] == ["", "on"]


def test_the_journeys_end_offers_no_footer_primary_at_all(drafted, tmp_path):
    """`STAGE_LABELS` has no `track`, and that is the whole of it.

    The way onward from here is a LINK, and it is already in the header, where
    `deepLink` labels itself from the most specific thing we know. A footer
    primary could not do that — the map holds constant strings — so it would
    read "Open application" on the one state that has no application. The
    footer is not empty: the status segment is its control.
    """
    assert _by_class(drafted["loaded"]["foot"], "cta") == []
    assert _by_class(drafted["loaded"]["identity"], "linkish")[0]["text"] == (
        "Open application ↗")
    applied = _track(tmp_path, detail=APPLIED_DETAIL)
    assert _by_class(applied["loaded"]["foot"], "cta") == []
    assert len(_by_class(applied["loaded"]["foot"], "status-seg")) == 1


def test_the_track_this_state_is_not_contradicted_by_the_footer(tmp_path):
    """THE STATE THAT MADE THE PLACEHOLDER A LIE, named: a fill finished from
    the base resume, with no application behind it.

    The body says nothing has been written down for this page. A footer button
    reading "Open application" six pixels under that sentence contradicts it —
    and, pressed, said "lands in the next change" about a change that is not
    coming. Neither the button nor the status segment is rendered here, so the
    body's sentence stands, and the header's link says where to go in the words
    that fit the state ("Open in Maestro CS ↗", because there is no application
    to open).
    """
    out = _track(tmp_path, stored={"widget.session": {**_armed_entry(),
                                                      "touched": True}},
                 page={"detect_page": _reply({"form": True})})
    loaded_rows = _rows(_rail_rows({"regions": out["loaded"]}))
    assert loaded_rows["track"]["state"] == "active"
    # …and NOT ticked: a draft is on the Track step with the press still ahead
    # of it, which is what stops the tick from being "Track is always done".
    assert loaded_rows["track"]["numeral"] == "5"
    assert "nothing has been written down" in _text(_track_body(out["loaded"]))
    assert _by_class(out["loaded"]["foot"], "cta") == []
    assert out["statuses"] == []
    assert _by_class(out["loaded"]["identity"], "linkish")[0]["text"] == (
        "Open in Maestro CS ↗")


def test_marking_it_applied_ends_the_rail(tmp_path):
    """The other half of "the whole surface moves", and the half it used to get
    wrong: before `railModel` grew `ticked` the Track row kept its blue "5"
    forever, so finishing the entire journey looked like stopping half-way
    through the last step.

    FIVE TICKS AND THE ROW IS STILL THE ONE THE USER IS ON. The state did not
    move — `active` still outranks `done` for placement, `aria-current` is still
    on this row, the border is still blue — the NUMERAL did, because the tick
    answers "is this finished" and that is `done`'s question.
    """
    settled = _track(tmp_path, press="Applied")["settled"]
    rows = _rows(_rail_rows({"regions": settled}))
    assert [rows[key]["numeral"] for key in
            ("job", "score", "resume", "fill", "track")] == ["✓"] * 5
    assert rows["track"]["state"] == "active"


# ---------- the one PATCH this extension makes ----------


def test_marking_it_applied_is_one_patch_and_the_whole_surface_moves(tmp_path):
    """The end of the journey, through the real render driver.

    The wire is the card's: one PATCH to the application with a one-key body.
    What follows is everything the decision moves — the chip, the segment, the
    body's sentence and the evidence line — and the sentence is the widget's own
    words, because two surfaces describing one recorded fact in two ways is how
    a user comes to believe there are two things being recorded.
    """
    out = _track(tmp_path, press="Applied")
    [patch] = _patches(out)
    assert patch["path"] == "/api/applications/app-remembered"
    assert patch["init"]["body"] == '{"status":"applied"}'

    settled = out["settled"]
    assert _by_class(settled["identity"], "chip")[0]["text"] == "Application · applied"
    [segment] = _by_class(settled["foot"], "status-seg")
    assert [button["attrs"]["aria-checked"] for button in segment["children"]] == [
        "false", "true"]
    assert "Marked applied" in _text(_track_body(settled))
    # THE RAIL ENDING is the next test's, deliberately: it is its own claim
    # about its own region, and this one is already the longest walk in the file.
    # The sentence lives in the BODY alone: the footer note is silent on a
    # successful applied press (the same string in both slots at once on a
    # 400px rail reads as a rendering bug, and the note slot's job is
    # failures and transients — gate sweep item 5, Round B).
    assert _by_class(settled["foot"], "note")[0]["text"] == ""
    # THE EVIDENCE IS TRUE AT THE PRESS, not after the next page load: the PATCH
    # answers with the whole record, `applied_at` included, and it is folded
    # through the same `evidenceFrom` the GET is.
    assert _text(_by_class(settled["rail"], "evi")[0]) == (
        "📎 tailored-resume.pdf rendered · applied 2026-08-18")


def test_the_store_carries_the_servers_word_and_never_the_one_we_sent(tmp_path):
    """`out.status ?? status`, and the order is the claim.

    The route is free to answer with something other than what was sent — a
    normalisation, or simply a record another writer has moved on since this
    press. Echoing the ARGUMENT back into the store would be the panel
    reporting its own request as the state of the world, which is the confident
    wrong thing this surface keeps refusing to say. Here the answer is
    `interviewing`: the chip says so, the body says so, and the segment
    withdraws because that is not a status this panel writes.
    """
    out = _track(tmp_path, press="Applied", api={
        "PATCH /api/applications/app-remembered": _reply(
            {**APPLIED_DETAIL, "status": "interviewing"})})
    settled = out["settled"]
    assert _by_class(settled["identity"], "chip")[0]["text"] == (
        "Application · interviewing")
    assert "Status: interviewing" in _text(_track_body(settled))
    assert _by_class(settled["foot"], "status-seg") == []
    # …and the memory carries it too, so the next page of the wizard restores
    # the server's word rather than ours.
    [written] = [write["widget.session"] for write in out["writes"]
                 if write.get("widget.session")]
    assert written["status"] == "interviewing"


def test_the_new_status_is_remembered_so_the_next_page_does_not_say_draft(tmp_path):
    """The entry both surfaces read carries `status`, so a pick remembered on
    one page of the wizard and restored on the next must not still say "draft"
    after this. The widget's own `setStatus` remembers for the same reason."""
    out = _track(tmp_path, press="Applied")
    [written] = [write["widget.session"] for write in out["writes"]
                 if write.get("widget.session")]
    assert written["status"] == "applied"
    assert written["applicationId"] == "app-remembered"
    assert written["tenant"] == LIGHTNING_TENANT


def test_pressing_the_status_it_already_has_is_not_a_round_trip(drafted, tmp_path):
    """A radiogroup keeps its checked option pressable, so this press is one a
    user makes by accident — and a PATCH that sets `applied` to `applied` is a
    write with nothing to write: harmless server-side, and still a spinner and
    a sentence about an event that did not happen."""
    out = _track(tmp_path, press="Draft")
    assert _patches(out) == []
    assert out["settled"]["foot"]["children"][0]["text"] == ""


def test_nothing_else_can_be_started_while_the_status_write_is_open(tmp_path):
    """`busy` is keyed on the stage, and the status segment is out of reach for
    the length of its own write — both buttons, not just the one pressed.

    Both buttons and not just the pressed one, because the segment is the whole
    control: a live "Draft" beside an open "Applied" write is the broken/busy
    confusion this surface keeps naming. (There is no footer primary on this
    stage to grey out beside them — see the no-primary test above.)
    """
    out = _track(tmp_path, press="Applied",
                 hold=["PATCH /api/applications/app-remembered"])
    clicked = out["clicked"]
    [segment] = _by_class(clicked["foot"], "status-seg")
    assert [button["disabled"] for button in segment["children"]] == [True, True]
    # …and released, everything is pressable again.
    [settled] = _by_class(out["settled"]["foot"], "status-seg")
    assert [button["disabled"] for button in settled["children"]] == [False, False]


def test_a_status_write_that_fails_hands_the_control_back_and_says_why(tmp_path):
    """The failure is the note slot's, in red, and the status does not move: a
    panel that painted "applied" over a PATCH the backend refused would be
    claiming a record that does not exist."""
    out = _track(tmp_path, press="Applied", api={
        "PATCH /api/applications/app-remembered": {
            "ok": False, "error": "the tracker is unreachable"}})
    settled = out["settled"]
    note = _by_class(settled["foot"], "note")[0]
    assert note["text"] == "the tracker is unreachable"
    assert note["class"] == "note error"
    [segment] = _by_class(settled["foot"], "status-seg")
    assert [button["attrs"]["aria-checked"] for button in segment["children"]] == [
        "true", "false"]
    assert [button["disabled"] for button in segment["children"]] == [False, False]


def test_a_status_change_that_lands_after_you_switch_tabs_paints_nothing(tmp_path):
    """The generation rule, on the last action in the journey.

    The user presses Applied, then changes tabs while the PATCH is open. The
    answer belongs to a page they have left — and "Marked applied" in the note
    slot of the tab they are on now is a sentence about somebody else's
    application.
    """
    out = _track(tmp_path, press="Applied", switchTo=42,
                 tabUrls={"42": "chrome://settings"},
                 hold=["PATCH /api/applications/app-remembered"])
    settled = out["settled"]
    assert _by_class(settled["foot"], "note")[0]["text"] == ""
    # The whole page is gone, chip and rail alike — `resetPageFacts` ran and
    # nothing from the tab that was left was allowed to paint over it.
    assert _by_class(settled["identity"], "chip") == []
    assert _by_class(settled["foot"], "status-seg") == []
    assert _rows(_rail_rows({"regions": settled}))["job"]["state"] == "active"


# ---------- what an application has to show for itself, as a table ----------

_EVIDENCE_DRIVER_JS = _PANEL_FAKES_JS + r"""
const ns = loadModules();
main(async () => {
  emit({ out: spec.details.map((detail) => ns.panel.evidenceFrom(detail)) });
});
"""


@pytest.fixture(scope="module")
def evidence(tmp_path_factory):
    details = {
        "both": {"pdf_path": "renders/app-1/tailored-resume.pdf",
                 "applied_at": "2026-08-18T14:32:11+00:00"},
        # A tailored draft: the document exists, it has not gone out.
        "pdf_only": {"pdf_path": "renders/app-1/tailored-resume.pdf",
                     "applied_at": None},
        # Marked applied on an application built by "track this" — no tailor,
        # so no render, and the date is all there is.
        "date_only": {"pdf_path": None, "applied_at": "2026-08-18T14:32:11+00:00"},
        "neither": {"pdf_path": None, "applied_at": None},
        # A read that failed, or a route that answered something else entirely.
        # `null` is not a detail and must not become an evidence line.
        "nothing": None,
        # Windows separators, because `pdf_path` is whatever the server's
        # filesystem wrote and the panel is not the place to have an opinion
        # about which one it used.
        "windows": {"pdf_path": "renders\\\\app-1\\\\tailored.pdf", "applied_at": None},
        # NOT an ISO timestamp. The regex is what makes the slice safe: a value
        # this panel cannot read produces no date rather than five characters of
        # whatever arrived.
        "unparseable_date": {"pdf_path": None, "applied_at": "last Tuesday"},
        # A bare date with no time is still a date.
        "date_only_no_time": {"pdf_path": None, "applied_at": "2026-08-18"},
    }
    names = list(details)
    out = run_node(_EVIDENCE_DRIVER_JS, {"details": [details[n] for n in names]},
                   tmp_path_factory.mktemp("panel_evidence"), source=PANEL_SOURCE)
    return dict(zip(names, out["out"], strict=True))


def test_the_two_facts_the_endpoint_carries_are_the_two_it_reports(evidence):
    assert evidence["both"] == {"pdfName": "tailored-resume.pdf",
                                "appliedOn": "2026-08-18"}
    assert evidence["pdf_only"] == {"pdfName": "tailored-resume.pdf",
                                    "appliedOn": None}
    assert evidence["date_only"] == {"pdfName": None, "appliedOn": "2026-08-18"}
    assert evidence["date_only_no_time"] == {"pdfName": None,
                                             "appliedOn": "2026-08-18"}


def test_nothing_to_show_is_null_rather_than_an_empty_line(evidence):
    """The honest absence, decided HERE so the body has one thing to test and
    never a second opinion about what counts as evidence."""
    assert evidence["neither"] is None
    assert evidence["nothing"] is None
    assert evidence["unparseable_date"] is None


def test_the_filename_is_the_last_segment_whichever_separator_wrote_it(evidence):
    assert evidence["windows"] == {"pdfName": "tailored.pdf", "appliedOn": None}


# ---------- track-this: one press writes the draft down ----------
#
# The nudge is already `stageFor`'s. This section is the ACTION that answers
# it: `POST /api/applications/from-base` with the job and base the panel
# already holds, then the same claim semantics a pick writes — `claimed`,
# `match: "exact"`, the session bridge — so the next wizard page still knows
# and the Job row's un-pick door works.

TRACKED_DETAIL = {"id": "app-tracked", "status": "draft", "applied_at": None,
                  "job_id": "job-lightning", "base_resume": "ai_ml_engineer",
                  "pdf_path": None}


def _trackable_entry():
    """Filled from the base, the job already in the library, no application.

    Restore puts the remembered job back on an apply URL the matcher cannot
    name — which is how a user arrives at track-this with a `job_id` the
    from-base route will accept."""
    return {**_armed_entry(), "touched": True,
            "jobId": "job-lightning", "company": "Lightning AI",
            "title": "Research Engineer"}


def _track_this(tmp_path, **spec):
    spec.setdefault("stored", {"widget.session": _trackable_entry()})
    spec.setdefault("page", {"detect_page": _reply({"form": True})})
    spec.setdefault("track", True)
    api = {"POST /api/applications/from-base": _reply(TRACKED_DETAIL)}
    api.update(spec.pop("api", {}))
    return _track(tmp_path, api=api, **spec)


def test_track_this_is_one_post_and_the_page_is_the_users_claim(tmp_path):
    """One press turns page work into a tracked draft.

    The wire is the card's: `POST /api/applications/from-base` with the job
    and the base, nothing else — no ops (the route defaults them), no view
    state, no `claimed`. What follows is a pick's write-set for a claim the
    user just made: the application the response named, `match: "exact"`,
    `claimed`, and a session entry the next wizard page can restore.
    """
    out = _track_this(tmp_path)
    [post] = [msg for msg in _posts(out)
              if msg["path"] == "/api/applications/from-base"]
    assert json.loads(post["init"]["body"]) == {
        "job_id": "job-lightning", "base_resume": "ai_ml_engineer"}
    assert out["facts"]["applicationId"] == "app-tracked"
    assert out["facts"]["claimed"] is True
    assert out["facts"]["match"] == "exact"
    assert "Tracked" in _by_class(out["settled"]["foot"], "note")[0]["text"]
    writes = [write["widget.session"] for write in out["writes"]
              if write.get("widget.session")]
    assert writes, "track-this never wrote widget.session"
    written = writes[-1]
    assert written["applicationId"] == "app-tracked"
    # NOT a `claimed` key: R-C dropped it from the entry on purpose —
    # `restoreSession` infers the claim from `applicationId` (the inference
    # is pinned by the legacy-entry tests in test_extension_panel_job.py).
    # This lane was written against the pre-R-C shape; the rebase resolved
    # toward the shape with fewer keys.
    assert "claimed" not in written
    assert written["jobId"] == "job-lightning"
    assert written["tenant"] == LIGHTNING_TENANT
    assert written["status"] == "draft"


def test_the_track_this_button_is_offered_when_the_job_is_already_in_the_library(
        tmp_path):
    """The affordance, before the press: a job_id the route will accept, a
    base the page was filled from, and one button whose label is the card's."""
    out = _track_this(tmp_path, track=False)
    body = _track_body(out["loaded"])
    buttons = [node for node in _walk(body) if node["tag"] == "BUTTON"]
    assert [button["text"] for button in buttons] == ["Track this application"]
    assert buttons[0]["disabled"] is False
    assert "filled from your base resume" in _text(body)
    assert "Open Maestro CS" not in _text(body)


def test_track_this_never_puts_claimed_or_revisit_on_the_wire(tmp_path):
    """Provenance and view state stay off the POST. `claimed` is a panel
    binding fact; `revisit` is which body is open. Neither is a field the
    backend has, and echoing either would be this surface inventing a
    contract."""
    out = _track_this(tmp_path)
    for msg in out["sent"]:
        body = (msg.get("init") or {}).get("body") or ""
        assert "claimed" not in str(body)
        assert "revisit" not in str(body)
        assert "claimed" not in str(msg.get("path") or "")


def test_a_tracked_this_binding_opens_the_job_rows_unpick_door(tmp_path):
    """A track-this IS a claim. The Job row's door is `claimed === true` on a
    done Job row — the same predicate a pick writes — so a user who tracked
    the wrong page can take it back the same way they would a mis-pick."""
    out = _track_this(tmp_path)
    assert out["facts"]["claimed"] is True
    assert "stg-open-job" in [n.get("id") for n in _walk(out["settled"]["rail"])]


def test_nothing_else_can_be_started_while_track_this_is_open(tmp_path):
    """`busy` is keyed on the stage. The body's own button is out of reach for
    the length of its write — `actingLimb`'s rule, the same one Attach resume
    follows: a live twin while the POST is open is the broken/busy confusion
    this surface keeps naming."""
    out = _track_this(tmp_path, hold=["POST /api/applications/from-base"])
    body = _track_body(out["clicked"])
    [button] = [node for node in _walk(body) if node["tag"] == "BUTTON"]
    assert button["disabled"] is True
    assert button["text"] == "Track this application"


def test_a_track_this_that_fails_hands_the_control_back_and_says_why(tmp_path):
    """The failure is the note slot's, in red, and nothing is claimed: a panel
    that painted a draft over a POST the backend refused would be naming a
    record that does not exist."""
    out = _track_this(tmp_path, api={
        "POST /api/applications/from-base": {
            "ok": False, "error": "the tracker is unreachable"}})
    settled = out["settled"]
    note = _by_class(settled["foot"], "note")[0]
    assert note["text"] == "the tracker is unreachable"
    assert note["class"] == "note error"
    assert out["facts"]["applicationId"] is None
    assert out["facts"]["claimed"] is False
    body = _track_body(settled)
    [button] = [node for node in _walk(body) if node["tag"] == "BUTTON"]
    assert button["disabled"] is False


def test_a_track_this_that_lands_after_you_switch_tabs_paints_nothing(tmp_path):
    """The generation rule. The user presses Track this, then changes tabs
    while the POST is open. The answer belongs to a page they have left —
    and "Tracked" in the note slot of the tab they are on now is a sentence
    about somebody else's application."""
    out = _track_this(tmp_path, switchTo=42,
                      tabUrls={"42": "chrome://settings"},
                      hold=["POST /api/applications/from-base"])
    settled = out["settled"]
    assert _by_class(settled["foot"], "note")[0]["text"] == ""
    assert _by_class(settled["identity"], "chip") == []
    assert out["facts"]["applicationId"] is None
    assert _rows(_rail_rows({"regions": settled}))["job"]["state"] == "active"
