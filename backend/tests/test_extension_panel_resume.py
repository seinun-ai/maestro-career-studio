"""The RESUME stage: base as-is, quick tailor, custom in Studio.

The two-level fork asks one question first and only then discloses the second
level; the base-as-is shortcut is driven end to end, from the arming on the
posting to the fill on the apply page; Custom in Studio is a link out and
never an API call; and `quickTailor` is driven through its busy, failure,
no-PDF, nothing-to-tailor, race and success paths.

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
import time

from tests.extension_fixtures import (
    LIGHTNING_APPLY_URL,
    LIGHTNING_TENANT,
    PICKED_ENTRY,
    POSTING_URL,
)
from tests.extension_harness import run_node
from tests.extension_panel_harness import (
    APP_URL,
    LIGHTNING_JOB,
    PANEL_CSS,
    PANEL_SOURCE,
    SCORE_RESUMES,
    SCORE_ROWS,
    SETTINGS_REPLY,
    _armed_entry,
    _by_class,
    _load,
    _posts,
    _PANEL_FAKES_JS,
    _rail_rows,
    _reply,
    _rows,
    _text,
    _walk,
)


# ---------- the Resume stage: base as-is, quick tailor, custom in Studio ------
#
# THE FORK IS THE STAGE. Three ways forward on two levels — arm the base and
# skip the rest, tailor here, or leave for the Studio — and they are three
# different KINDS of control on purpose: one acts and finishes the stage, one
# only discloses, one is a round trip, and one is a link out. The tests below
# are grouped that way, because "what kind of thing is this button" is the
# question the mockup's flat row of buttons could not answer.

_RESUME_STAGE_DRIVER_JS = _PANEL_FAKES_JS + r"""
loadModules();
// Every fork limb on screen, in reading order — buttons and the anchor alike,
// because what the user sees is four boxes in two rows and the difference
// between them is exactly what the tests are about.
const limbs = () => withClass(REGIONS.rail, "fork").flatMap((row) => row.children);
// Pressed BY LABEL, which is the only handle a user has. Naming a limb that is
// not on screen throws rather than passing quietly: "the second level is not
// rendered yet" and "the click did nothing" are different failures.
const press = (label) => {
  const found = limbs().find((limb) => limb.textContent === label);
  if (!found) throw new Error(`no fork limb reads "${label}"`);
  // FOCUSED, then pressed, as a browser does: where focus lands after a press
  // that rebuilds the rail is part of what the press does.
  found.focus();
  found.click();
};
main(async () => {
  await settle();
  // A base picked on the Score row first, for a page whose backend match names
  // an application (no remembered pick is restored over one).
  if (spec.pickBase !== undefined) {
    withClass(REGIONS.rail, "baserow")[spec.pickBase].click();
    await settle();
  }
  const loaded = regions();
  let opened = null;
  if (spec.open === true) {
    press("Tailor to this job");
    await settle();
    opened = regions();
  }
  let clicked = null;
  let focusedAfter = null;
  if (spec.press !== undefined || spec.pressCta === true) {
    if (spec.pressCta === true) withClass(REGIONS.foot, "cta")[0].click();
    else press(spec.press);
    // Synchronous, and deliberately: an action sets `busy` and paints before
    // its first await, so this is the surface as the user sees it while the
    // tailor is open.
    clicked = regions();
    await settle();
    focusedAfter = document.activeElement?.id ?? null;
    // …and the user is free to leave while the POST is still on the wire.
    if (spec.switchTo !== undefined) {
      await onActivated({ tabId: spec.switchTo });
      await settle();
    }
    release();
    await settle();
  }
  // …and the row the press SKIPPED, opened again from the rail. A door rather
  // than a fork limb, so it is found by the id the rail stamps: the claim's
  // whole shape on a form-less page is "the rail moved, and the way back is a
  // row above where it moved to".
  let reopened = null;
  if (spec.reopen !== undefined) {
    const door = findById(REGIONS.rail, `stg-open-${spec.reopen}`);
    if (!door) throw new Error(`no way back into the ${spec.reopen} row`);
    door.click();
    await settle();
    reopened = regions();
  }
  emit({ loaded, opened, clicked, focusedAfter, reopened, settled: regions(), sent, writes,
         limbs: limbs().map((limb) => limb.textContent) });
});
"""

# The Resume stage is "the job is in the library, a base has been picked, and
# nothing has been tailored yet" — so the fixture arrives there the way a user
# does: a pick remembered from the previous page of the wizard, which is exactly
# `PICKED_ENTRY` (imported; see the fixtures module for why it is not a copy).
# The row the compare PERSISTS for the application quick-tailor creates, which
# is what the After ring reads back — keyed on that application's id, because
# `compositeFor` matches on the target and a row for another one is not it.
QUICK_TAILORED_ROW = {"target_type": "application", "target_id": "app-quick",
                      "phase": "tailored", "composite": 84.2,
                      "engine_version": "ats-2.3.0"}
# What the quick tailor answers with, on the ordinary path.
TAILORED_REPLY = _reply({"application_id": "app-quick", "session_id": "sess-1",
                         "compare": {"before": 71.8, "after": 84.2},
                         "applied": ["mirror_wording", "keywords_into_skills"],
                         "pdf_ready": True, "nothing_to_tailor": False,
                         "health_warning": None})


# What the choices do: one short muted line under each level (2026-09-27).
FORK_LINE = "Base: your resume unchanged. Tailor: fit it to this job first."
OPTIONS_LINE = ("Quick tailor makes the PDF here. A PDF you make in Maestro CS "
                "shows up here when you select Refresh.")
# With no link to Maestro CS there is nothing to promise about it.
OPTIONS_LINE_HERE = "Quick tailor makes the PDF here."


def _resume(tmp_path, **spec):
    """Boot on a posting whose base is already picked — the Resume stage."""
    spec.setdefault("tabs", [{"id": 7, "url": POSTING_URL}])
    spec.setdefault("replies", {"read_settings": SETTINGS_REPLY})
    spec.setdefault("stored",
                    {"widget.session": {**PICKED_ENTRY, "at": int(time.time() * 1000)}})
    api = {"lightningai": _reply({"match": "exact", "job": LIGHTNING_JOB,
                                  "application": None}),
           "/api/base-resumes": _reply(SCORE_RESUMES),
           "GET /api/ats-scores": _reply(SCORE_ROWS),
           "quick-tailor": TAILORED_REPLY}
    api.update(spec.pop("api", {}))
    return run_node(_RESUME_STAGE_DRIVER_JS, {**spec, "api": api}, tmp_path,
                    source=PANEL_SOURCE)


def _limbs(region):
    return [_text(limb) for fork in _by_class(region, "fork") for limb in fork["children"]]


def test_the_fork_belongs_to_the_step_you_are_on_and_asks_one_question_first(tmp_path):
    """A body renders under the ACTIVE row and nowhere else, and this one opens
    with ONE question rather than three.

    "Do you want to tailor at all" is the question; "quick or custom" is only a
    question for the user who has answered yes. Three equal-weight buttons in a
    row would put the second question in front of someone who has not been
    asked the first — which is what the old Base/Tailored toggle did, and what
    the mockup's two-level fork replaced.
    """
    out = _resume(tmp_path)
    rows = _by_class(out["loaded"]["rail"], "stg")
    assert rows[1]["class"] == "stg active"
    # One level, two limbs, and the Job row above it carries no body of its
    # own: a done row is a tick and a summary.
    assert _limbs(out["loaded"]["rail"]) == ["Use my base resume", "Tailor to this job"]
    assert len(_by_class(out["loaded"]["rail"], "stg-body")) == 1
    assert _by_class(rows[0], "stg-body") == []
    # Nothing is pre-selected. Picking a tailoring path on the user's behalf is
    # the thing this fork exists to stop.
    assert [limb["class"] for limb in _by_class(out["loaded"]["rail"], "fork")[0]["children"]] == [
        "", ""]


def test_tailor_only_discloses_and_asks_the_backend_for_nothing(tmp_path):
    """The second level is a disclosure: it can be pressed by someone still
    making up their mind, so it must cost nothing and claim nothing."""
    out = _resume(tmp_path, open=True)
    before = len(out["sent"])
    assert out["limbs"] == ["Use my base resume", "Tailor to this job",
                            "Quick tailor", "Tailor in Maestro CS ↗"]
    # The branch the user is standing in, said in words as well as in colour.
    [_base, tailor] = _by_class(out["opened"]["rail"], "fork")[0]["children"]
    assert tailor["class"] == "sel"
    assert tailor["attrs"]["aria-expanded"] == "true"
    # …and WHAT it opened, not merely that something did. Asserted as an
    # address that RESOLVES, which is the only version of this attribute worth
    # having: an `aria-controls` naming an id nothing carries offers a jump
    # that goes nowhere. The region holds both revealed limbs AND the sentence
    # explaining one of them — a reader sent to the limbs alone would be sent
    # past the explanation.
    [region] = [found for found in _walk(out["opened"]["rail"])
                if found["id"] == tailor["attrs"]["aria-controls"]]
    assert _limbs(region) == ["Quick tailor", "Tailor in Maestro CS ↗"]
    assert [line["text"] for line in _by_class(region, "sub")] == [OPTIONS_LINE]
    # Closed, there is no region — this loop renders what is true — so the
    # button says only that it is closed. A pointer kept across the collapse
    # would be the same broken promise as a link to a guessed address.
    [_base, shut] = _by_class(out["loaded"]["rail"], "fork")[0]["children"]
    assert shut["attrs"] == {"aria-expanded": "false"}
    # Not one message, and certainly not a POST: opening a menu is not a choice.
    assert len(out["sent"]) == before
    assert _posts({"sent": out["sent"]}) == []
    # Each level says what its choices do in one short muted line: the first
    # before anything is opened, the second inside the region.
    assert [line["text"] for line in _by_class(out["loaded"]["rail"], "sub")] == [
        FORK_LINE]
    assert [line["text"] for line in _by_class(out["opened"]["rail"], "sub")] == [
        FORK_LINE, OPTIONS_LINE]


def test_custom_in_studio_is_a_link_out_and_never_an_api_call(tmp_path):
    """THE PIN on this limb, and it is about what a custom pass IS.

    The Studio's tailor route needs a tailoring SESSION, and the only way for
    the panel to hold one is to create it — a write, made on the user's behalf,
    to open a page they have not looked at yet. So this limb is a real anchor
    to the job's own page, on the tab that starts a custom pass, and the panel
    picks the result up on the next load instead. A real `<a href>` also
    middle-clicks, copies and shows its destination, which a button pretending
    to be a link does not.
    """
    out = _resume(tmp_path, open=True)
    [custom] = [limb for limb in _by_class(out["opened"]["rail"], "fork")[1]["children"]
                if limb["tag"] == "A"]
    assert custom["href"] == f"{APP_URL}/jobs/job-lightning?tab=fit"
    assert custom["attrs"] == {}
    assert custom["text"] == "Tailor in Maestro CS ↗"
    # `target`/`rel` are plain properties on the fake node, like `href`.
    assert "quick-tailor" not in json.dumps(out["sent"])


def test_a_panel_that_does_not_know_where_the_studio_is_offers_no_way_there(tmp_path):
    """No `appUrl`, no link — the header's `deepLink` refuses on the same terms.

    A link to a guessed address is the failure this project keeps naming, and
    a dead anchor styled like the button beside it is worse: it looks live and
    is not. The sentence goes with it, because it promises what happens after
    the user leaves and there is nothing to leave through.
    """
    out = _resume(tmp_path, open=True, replies={})
    assert out["limbs"] == ["Use my base resume", "Tailor to this job", "Quick tailor"]
    assert [line["text"] for line in _by_class(out["opened"]["rail"], "sub")] == [
        FORK_LINE, OPTIONS_LINE_HERE]


def _described_by(region, control):
    """The text of the one node `control`'s `aria-describedby` names."""
    [reason] = [node for node in _walk(region)
                if node["id"] and node["id"] == control["attrs"]["aria-describedby"]]
    return reason["text"]


NO_PDF_LINE = "This application's resume has no PDF yet."
BOUND_REASON = "This job already has a draft application, so it uses that resume."


def test_a_draft_whose_resume_has_no_pdf_offers_create_pdf_and_never_a_fresh_tailor(tmp_path):
    """The application's tailored resume exists and only its PDF is missing, so
    the answer is to create the PDF, never Quick tailor: that runs a fresh
    tailor ("asks to tailor again"). The base is visibly off, with one short
    sentence saying why (THE DEAD BUTTON, Task 25's first read: armed beside an
    application, the claim changed nothing). No base click first: the
    application answers the base question, so the rail opens on Resume."""
    out = _resume(tmp_path, api={
        "lightningai": _reply({"match": "exact", "job": LIGHTNING_JOB,
                               "application": {"id": "app-1", "status": "draft"}}),
        "/api/applications/app-1": _reply({"pdf_path": None, "status": "draft"})})
    loaded = out["loaded"]
    assert _rows(_rail_rows({"regions": loaded}))["resume"]["state"] == "active"
    body = _body(loaded)
    assert NO_PDF_LINE in [line["text"] for line in _by_class(body, "sub")]
    [base, link] = _by_class(body, "fork")[0]["children"]
    assert base["text"] == "Use my base resume"
    assert base["attrs"]["aria-disabled"] == "true"
    assert _described_by(loaded["rail"], base) == BOUND_REASON
    assert "Quick tailor" not in _text(loaded["rail"])
    assert FORK_LINE not in _text(loaded["rail"])
    # …and the way to tailor it, in Maestro CS, where the web app asks before
    # replacing anything.
    assert (link["tag"], link["text"]) == ("A", "Tailor in Maestro CS ↗")
    assert link["href"] == f"{APP_URL}/jobs/job-lightning?tab=fit"
    [cta] = _by_class(loaded["foot"], "cta")
    assert cta["text"] == "Create PDF"


def test_create_pdf_renders_the_applications_pdf_and_the_rail_moves_on(tmp_path):
    """`POST /api/applications/{id}/render` renders the tailored draft that is
    already stored — no tailor, no model call — and the PDF is what Resume
    was waiting on, so the rail moves to Fill."""
    out = _resume(tmp_path, pressCta=True, hold=["/render"], api={
        "lightningai": _reply({"match": "exact", "job": LIGHTNING_JOB,
                               "application": {"id": "app-1", "status": "draft"}}),
        "/api/applications/app-1/render": _reply(
            {"tex_path": "r/app-1.tex", "pdf_path": "renders/app-1.pdf"}),
        "/api/applications/app-1": _reply({"pdf_path": None, "status": "draft"})})
    [cta] = _by_class(out["clicked"]["foot"], "cta")
    assert (cta["text"], cta["class"], cta["disabled"]) == ("Create PDF", "cta spin", True)
    [post] = _posts(out)
    assert post["path"] == "/api/applications/app-1/render"
    assert "quick-tailor" not in json.dumps(out["sent"])
    settled = out["settled"]
    rows = _rows(_rail_rows({"regions": settled}))
    assert rows["resume"]["state"] == "done"
    assert rows["fill"]["state"] == "active"
    [note] = _by_class(settled["foot"], "note")
    assert note["text"] == "PDF created."
    assert out["writes"][-1]["widget.session"]["pdfReady"] is True


def test_a_create_pdf_that_lands_after_you_switch_tabs_paints_nothing(tmp_path):
    """The generation rule on the render round trip: the user may leave while
    the PDF is made, and "PDF created." (and a session entry saying so) about
    the page they left must not land on the one they are on."""
    out = _resume(tmp_path, pressCta=True, hold=["/render"], switchTo=42,
                  tabUrls={"42": "chrome://settings"}, api={
        "lightningai": _reply({"match": "exact", "job": LIGHTNING_JOB,
                               "application": {"id": "app-1", "status": "draft"}}),
        "/api/applications/app-1/render": _reply(
            {"tex_path": "r/app-1.tex", "pdf_path": "renders/app-1.pdf"}),
        "/api/applications/app-1": _reply({"pdf_path": None, "status": "draft"})})
    assert [msg["path"] for msg in _posts(out)] == ["/api/applications/app-1/render"]
    settled = out["settled"]
    assert "PDF created" not in _text(settled["foot"])
    assert [n for n in _walk(settled["foot"]) if "spin" in str(n.get("class"))] == []
    assert not any(write.get("widget.session", {}).get("pdfReady")
                   for write in out["writes"])


def test_a_create_pdf_that_fails_says_so_and_keeps_the_step(tmp_path):
    out = _resume(tmp_path, pressCta=True, api={
        "lightningai": _reply({"match": "exact", "job": LIGHTNING_JOB,
                               "application": {"id": "app-1", "status": "draft"}}),
        "/api/applications/app-1/render": {"ok": False, "error": "boom", "status": 500},
        "/api/applications/app-1": _reply({"pdf_path": None, "status": "draft"})})
    [note] = _by_class(out["settled"]["foot"], "note")
    assert note["text"] == (
        "Couldn't create the PDF. Open the application in Maestro CS to see why.")
    assert note["class"] == "note error"
    assert _rows(_rail_rows({"regions": out["settled"]}))["resume"]["state"] == "active"


def test_a_tailored_pdf_makes_the_step_done_and_reopens_onto_one_small_link(tmp_path):
    """With its PDF the step is simply done ("Tailored resume ready"). Reopened,
    it offers one small way to tailor again, in Maestro CS, where replacing a
    tailored draft asks first. No fork and no paragraph about it, and no
    footer primary: Quick tailor here would replace the draft unasked."""
    out = _resume(tmp_path, api={
        "lightningai": _reply({"match": "exact", "job": LIGHTNING_JOB,
                               "application": {"id": "app-1", "status": "draft"}}),
        "/api/applications/app-1": _reply({"pdf_path": "renders/app-1.pdf",
                                           "status": "draft"})},
        reopen="resume")
    rows = _rows(_rail_rows({"regions": out["reopened"]}))
    assert rows["resume"]["summary"] == "Resume ready"
    body = _body(out["reopened"])
    assert _by_class(body, "fork") == []
    [again] = [n for n in _walk(body) if n["tag"] == "A"]
    assert again["text"] == "Tailor in Maestro CS ↗"
    assert again["href"] == f"{APP_URL}/jobs/job-lightning?tab=fit"
    assert _text(body) == "Tailor in Maestro CS ↗"
    assert _by_class(out["reopened"]["foot"], "cta") == []


def test_use_base_as_is_skips_the_rest_visibly_and_outlives_the_page(tmp_path):
    """The shortcut, end to end: arm, skip, and remember.

    SKIPPED is not done. The Resume row greys and says why in the user's own
    words — the rail never puts a tick beside a step nobody took — and the user
    lands on Fill, which is the page in front of them.

    WRITTEN DOWN, because the arming is made on the posting and SPENT on the
    apply page: `resetPageFacts` clears `baseArmed` on every page load, so
    without the entry the shortcut would exist for exactly one page.
    """
    out = _resume(tmp_path, press="Use my base resume",
                  page={"detect_page": _reply({"tier": "A", "form": True, "score": 3})})
    rows = _rows(_rail_rows({"regions": out["settled"]}))
    assert rows["resume"]["state"] == "skipped"
    assert rows["resume"]["summary"] == "Using your base resume as is."
    assert rows["fill"]["state"] == "active"
    # …and the shortcut's own copy, under the identity where it explains what
    # the rail just skipped.
    assert "Ready to autofill from your base resume." in _text(out["settled"]["identity"])
    # One write, on the SHARED key, carrying the arming and the resume it arms.
    [write] = out["writes"]
    assert list(write) == ["widget.session"]
    assert write["widget.session"]["baseArmed"] is True
    assert write["widget.session"]["baseSlug"] == "ai_ml_engineer"
    assert write["widget.session"]["applicationId"] is None
    assert write["widget.session"]["tenant"] == LIGHTNING_TENANT
    # Nothing was asked of the backend: the answer was already in the panel.
    assert _posts({"sent": out["sent"]}) == []


def test_an_arming_made_on_the_posting_is_still_armed_on_the_apply_page(tmp_path):
    """The round trip, through the entry the panel ACTUALLY wrote.

    This is the whole point of the shortcut: the user says "use my base" on the
    posting and meets the FORM two page loads later, where the backend knows
    nothing about the url. Without the remembered arming the panel would open
    that page at Job and ask them to add a posting they had already saved.
    """
    armed = _resume(tmp_path, press="Use my base resume",
                    page={"detect_page": _reply({"tier": "A", "form": True, "score": 3})})
    out = _load(tmp_path, tabs=[{"id": 7, "url": LIGHTNING_APPLY_URL}],
                stored={"widget.session": armed["writes"][0]["widget.session"]},
                page={"detect_page": _reply({"tier": "A", "form": True, "score": 3})},
                api={"lightningai": _reply({"match": "none", "job": None,
                                            "application": None}),
                     "/api/base-resumes": _reply(SCORE_RESUMES),
                     "/api/ats-scores": _reply(SCORE_ROWS)})
    rows = _rows(_rail_rows(out))
    assert rows["fill"]["state"] == "active"
    assert rows["resume"]["state"] == "skipped"


def test_arming_a_base_on_a_page_with_no_form_moves_the_rail_and_says_where(tmp_path):
    """THE LIVE BUG (Yum, 2026-08-19), driven: base-as-is on a posting page.

    The user answers the Resume stage's question and the page in front of them
    has no form on it. What they used to get was the rail sitting exactly where
    it was — Resume still active, Fill locked, no primary — plus one sentence
    in the note slot that the next note would overwrite. A step whose question
    has been answered, still asking.

    WHAT THEY GET NOW is the shape the rest of the shortcut already had: Resume
    reads "Using your base resume as is.", the rail moves to Fill, and the FILL
    body says the true thing about this page and what to do about it. The
    sentence moved from a slot that scrolls past into the body of the step it
    is about, and there is exactly one of it.

    AND NO PRIMARY. "Start fill" here would run a pass over a page with no
    fields in it and report "0 filled" — the button the old `hasForm` gate
    existed to withhold, withheld at the button (panel.js `primaryRefused`).
    """
    out = _resume(tmp_path, press="Use my base resume")
    rows = _rows(_rail_rows({"regions": out["settled"]}))
    assert rows["resume"]["state"] == "skipped"
    assert rows["resume"]["summary"] == "Using your base resume as is."
    assert rows["fill"]["state"] == "active"
    body = next(n for n in _walk(out["settled"]["rail"])
                if n.get("id") == "stg-body-fill")
    assert _by_class(body, "sub")[0]["text"] == (
        "No application form here. Open the employer's Apply page to start "
        "filling.")
    # The pass control is gone with the pass: a segment choosing between two
    # runs that cannot happen here decides nothing.
    assert _by_class(body, "seg") == []
    assert _by_class(out["settled"]["foot"], "cta") == []
    # …and the note slot is left for what the user does NEXT, rather than
    # holding a second copy of the sentence above.
    [note] = _by_class(out["settled"]["foot"], "note")
    assert note["text"] == ""
    assert out["writes"][0]["widget.session"]["baseArmed"] is True
    # The shortcut's own copy is withheld too: "Ready to autofill from your
    # base resume" is a promise this page cannot keep.
    assert "Ready to autofill" not in _text(out["settled"]["identity"])


def test_quick_tailor_creates_the_application_and_the_rings_say_so(tmp_path):
    """The Resume stage's round trip, ported from the card's `fastTailor`: one
    POST, and the panel has an application with a rendered PDF behind it.

    THE AFTER RING is why this action re-reads the scores where `scoreAllBases`
    does not. `quick-tailor` returns its own before/after pair, and this surface
    renders `latest_scores` rows rather than numbers it was handed (design §4.2)
    — the compare it ran is PERSISTED, so the honest way to show it is to read
    the rows back.
    """
    out = _resume(tmp_path, open=True, press="Quick tailor",
                  hold=["POST /api/jobs/job-lightning/quick-tailor"],
                  api={"GET /api/ats-scores": [_reply(SCORE_ROWS),
                                               _reply([*SCORE_ROWS, QUICK_TAILORED_ROW])]})
    # While it is open: out of reach, and saying so — in the footer, which is
    # where this surface promises its one primary always is.
    [cta] = _by_class(out["clicked"]["foot"], "cta")
    assert cta["text"] == "Quick tailor"
    assert cta["disabled"] is True
    assert cta["class"] == "cta spin"
    # …and its twin in the fork, which stands directly above it wearing the
    # same word. A limb that stayed pressable would swallow the click — the
    # action guards itself, so nothing bad happens, and nothing happens
    # VISIBLY either, which is how a user comes to distrust the whole surface.
    # The two limbs that only read stay live: a disclosure claims nothing, and
    # a link to the Studio is a way out of a tailor that is taking too long.
    # `aria-disabled` and not `disabled`: the limb the user just pressed is
    # rebuilt by the render its own busy causes, and a `disabled` button
    # cannot take focus back (`withPlaceKept`), so focus would fall to the
    # document (the conventions' GapLocked rule).
    def locked(limb):
        return (limb["disabled"], limb["attrs"].get("aria-disabled"))
    assert {_text(limb): locked(limb) for limb in
            _by_class(out["clicked"]["rail"], "fork")[0]["children"]} == {
        "Use my base resume": (False, "true"), "Tailor to this job": (False, None)}
    assert {_text(limb): locked(limb) for limb in
            _by_class(out["clicked"]["rail"], "fork")[1]["children"]} == {
        "Quick tailor": (False, "true"), "Tailor in Maestro CS ↗": (False, None)}
    assert out["focusedAfter"] == "resume-quick"
    # …and it LOOKS out of reach: `.fork button` sets `background`, `color`
    # and `cursor: pointer` explicitly, so without this rule the limb renders
    # at full contrast under a pointer cursor while swallowing every click. A
    # source pin because appearance is not in the DOM.
    assert re.search(r'\.fork button\[aria-disabled="true"\][^{]*\{[^}]*opacity:\s*\.6',
                     PANEL_CSS), "a locked fork limb must not look pressable"
    # The widget's endpoint and body, unchanged — a panel that invented a route
    # would 404 in the browser and pass here.
    [post] = _posts(out)
    assert post["path"] == "/api/jobs/job-lightning/quick-tailor"
    assert json.loads(post["init"]["body"]) == {"base_resume": "ai_ml_engineer"}
    # The whole conversation, in order, extending the journey `addJob` starts.
    # The score read AFTER the POST is the After ring being earned rather than
    # asserted; the library is not re-read, because it is not a fact about a
    # page and the panel asked for it once.
    assert [f'{(msg.get("init") or {}).get("method", "GET")} {msg["path"].split("?")[0]}'
            for msg in out["sent"] if msg["type"] == "api"] == [
        "GET /api/jobs/match", "GET /api/base-resumes", "GET /api/ats-scores",
        "POST /api/jobs/job-lightning/quick-tailor", "GET /api/ats-scores"]
    settled = out["settled"]
    [note] = _by_class(settled["foot"], "note")
    assert note["text"] == "Tailored. 2 changes applied."
    assert note["class"] == "note"
    # The stage advanced because the DATA moved: an application with a PDF is
    # what `stageFor` reads as Resume-done, and nothing here said "go to Fill".
    rows = _rows(_rail_rows({"regions": settled}))
    assert rows["resume"]["state"] == "done"
    assert [ring["text"] for ring in _by_class(settled["identity"], "ring")] == ["72", "84"]
    assert _by_class(settled["identity"], "delta")[0]["text"] == "+12"
    # …and the application is remembered, so the next page of the wizard opens
    # on it rather than offering to tailor it again.
    entry = out["writes"][-1]["widget.session"]
    assert entry["applicationId"] == "app-quick"
    assert entry["pdfReady"] is True


def test_the_fork_limb_and_the_footer_primary_are_one_behaviour(tmp_path):
    """Two entry points, one action, and deliberately so: the fork is where the
    choice is made and the footer is this panel's standing promise that there
    is exactly one primary, always in the same place. One function means one
    `busy` key — pressing both cannot open two tailors — and the same words on
    both, so nobody reads them as two features."""
    out = _resume(tmp_path, open=True, pressCta=True)
    [post] = _posts(out)
    assert post["path"] == "/api/jobs/job-lightning/quick-tailor"
    assert _by_class(out["settled"]["foot"], "note")[0]["text"] == (
        "Tailored. 2 changes applied.")


def test_a_tailor_that_fails_hands_the_button_back_and_says_why(tmp_path):
    """A tailor is the longest round trip this surface makes, so a failed one
    must never leave the panel with its one control permanently pressed. The
    backend's own detail, verbatim — a heading per status code would be a claim
    about which of the 409s happened, and a health gate and an in-progress
    session share one — so the sentence sends the user to Tailor in Maestro CS
    (the job's Fit tab, which lists a gap analysis in progress and shows the
    must-fix reason when one is started), and never prints the backend's
    detail. Not "open the job to see why": the job page alone shows no reason."""
    out = _resume(tmp_path, open=True, press="Quick tailor",
                  api={"quick-tailor": {"ok": False, "error": "409: health gate",
                                        "status": 409}})
    [note] = _by_class(out["settled"]["foot"], "note")
    assert note["text"] == (
        "Couldn't tailor your resume. Use Tailor in Maestro CS to see what's in "
        "the way.")
    assert note["class"] == "note error"
    [cta] = _by_class(out["settled"]["foot"], "cta")
    assert cta["disabled"] is False
    # Nothing was claimed: no application, and the stage still asks.
    assert _rows(_rail_rows({"regions": out["settled"]}))["resume"]["state"] == "active"
    assert out["writes"] == []


def test_a_tailor_the_model_failed_points_at_the_ai_key(tmp_path):
    """A 502 is the model provider failing (app.main maps LLMProviderError to
    it), so the step is the key, not the job page."""
    out = _resume(tmp_path, open=True, press="Quick tailor",
                  api={"quick-tailor": {"ok": False, "error": "no answer",
                                        "status": 502}})
    [note] = _by_class(out["settled"]["foot"], "note")
    assert note["text"] == (
        "Couldn't tailor your resume. Check your API key in Maestro CS under "
        "Settings › AI & models.")


def test_a_tailor_with_no_api_key_says_to_add_one(tmp_path):
    """No key at all is not a refused key: the fix is to add one, and the
    server's sentence names a Settings path the panel says in its own words."""
    out = _resume(tmp_path, open=True, press="Quick tailor",
                  api={"quick-tailor": {"ok": False, "status": 502, "error":
                                        "No API key is set. Add one in Settings "
                                        "› AI & models › API keys."}})
    [note] = _by_class(out["settled"]["foot"], "note")
    assert note["text"] == (
        "Couldn't tailor your resume. Add an API key in Maestro CS under "
        "Settings › AI & models.")


def test_a_tailor_that_renders_no_pdf_says_so_and_still_keeps_the_application(tmp_path):
    """Rendering is server-side and can fail AFTER the tailor has committed, so
    this is not a failure path: the application exists either way, and losing
    it would mean offering to tailor the same job twice. The web app shows
    `render_error` and can re-render, which is what the sentence points at."""
    out = _resume(tmp_path, open=True, press="Quick tailor", api={"quick-tailor": _reply(
        {"application_id": "app-quick", "session_id": "s", "applied": [],
         "pdf_ready": False, "nothing_to_tailor": False,
         "health_warning": "Base resume health is C"})})
    [note] = _by_class(out["settled"]["foot"], "note")
    # The health warning rides the sentence rather than being said first and
    # overwritten a line later, which is what the card does with it.
    assert note["text"] == ("⚠ Base resume health is C Tailored, but couldn't "
                            "create the PDF. Select Create PDF to try again.")
    assert note["class"] == "note error"
    assert out["writes"][-1]["widget.session"]["applicationId"] == "app-quick"
    assert out["writes"][-1]["widget.session"]["pdfReady"] is False
    # Still at Resume: `stageFor` reads a PDF-less application as not done, so
    # the panel keeps offering the thing that would fix it — Create PDF, never
    # a second tailor.
    assert _rows(_rail_rows({"regions": out["settled"]}))["resume"]["state"] == "active"
    assert _text(_by_class(out["settled"]["foot"], "cta")[0]) == "Create PDF"


def test_nothing_to_tailor_claims_no_application_at_all(tmp_path):
    """A 200 that did nothing: no gap this profile is allowed to resolve. The
    backend leaves the session open for a custom pass and creates no
    application, so the panel must not invent one — `application_id` is null on
    this path and a store that took it would arm the whole surface at a row
    that does not exist."""
    out = _resume(tmp_path, open=True, press="Quick tailor", api={"quick-tailor": _reply(
        {"application_id": None, "session_id": "s", "applied": [],
         "pdf_ready": False, "nothing_to_tailor": True, "health_warning": None})})
    [note] = _by_class(out["settled"]["foot"], "note")
    assert note["text"].startswith("Quick tailor has nothing to change")
    assert "Maestro CS" in note["text"]
    assert out["writes"] == []
    # The chip still reads the LIBRARY, never an application: "In library" is
    # what this page is, and `Application · draft` would be the panel claiming
    # a row the backend explicitly did not create.
    assert [chip["text"] for chip in _by_class(out["settled"]["identity"], "chip")] == [
        "Saved"]


def test_a_tailor_that_lands_after_you_switch_tabs_paints_nothing(tmp_path):
    """The generation rule on the action that costs the most to get wrong: a
    tailor creates an APPLICATION, and an application id painted onto the tab
    the user moved to is what the header link, the status control and every
    later fill would aim at."""
    out = _resume(tmp_path, open=True, press="Quick tailor",
                  hold=["POST /api/jobs/job-lightning/quick-tailor"],
                  switchTo=42, tabUrls={"42": "chrome://settings"})
    settled = out["settled"]
    assert "app-quick" not in json.dumps(settled)
    assert "Tailored" not in _text(settled["foot"])
    assert [ring["text"] for ring in _by_class(settled["identity"], "ring")] == ["–"]
    assert _by_class(settled["rail"], "fork") == []


def test_a_tailor_that_FAILS_after_you_switch_tabs_paints_nothing_either(tmp_path):
    """`quickTailor`'s failure limb — the one the review actually caught.

    Three of three, and the reason the other two exist: a guardless failure
    ladder re-inlined HERE passed the entire suite. It is also the limb with
    the widest window, because a tailor is the longest round trip this surface
    makes — the user has the most time to leave, and a 409 about a job they are
    no longer looking at is the most confident wrong thing this action can say.
    """
    out = _resume(tmp_path, open=True, press="Quick tailor",
                  hold=["POST /api/jobs/job-lightning/quick-tailor"],
                  switchTo=42, tabUrls={"42": "chrome://settings"},
                  api={"quick-tailor": {"ok": False, "error": "409: health gate"}})
    settled = out["settled"]
    assert "409: health gate" not in json.dumps(settled)
    assert "Couldn't tailor" not in json.dumps(settled)
    # Nothing red, and nothing still spinning: `busy` belongs to the tab that
    # asked, and the early return leaves this one's render untouched.
    assert [n for n in _walk(settled["foot"]) if "error" in str(n.get("class"))] == []
    assert [n for n in _walk(settled["foot"]) if "spin" in str(n.get("class"))] == []
    # …and nothing was written on the way past, which is what makes this limb
    # worth its own driver: `card.application` is what the header link, the
    # status control and every later fill aim at.
    assert out["writes"] == []


# ---------- switching base from the reopened Score row ----------------------
#
# Standing on Resume, the user reopens Job to switch base and picks one. The
# stage does not move — Resume is still the open question, only about another
# base — so `openRow`'s "the rail moved on" limb never fires. Reported live:
# the base list stayed open under a Resume row that was active and had no way
# in, so the tailoring fork never came back.

_SWITCH_BASE_DRIVER_JS = _PANEL_FAKES_JS + r"""
loadModules();
const door = (key) => findById(REGIONS.rail, `stg-open-${key}`);
main(async () => {
  await settle();
  const loaded = regions();
  door("job").click();
  await settle();
  const reopened = regions();
  if (spec.back === true) {
    // Not picking at all: the user presses the row they are ON to go back.
    const back = door("resume");
    if (!back) throw new Error("the active Resume row is not a way back");
    back.click();
    await settle();
    emit({ loaded, reopened, back: regions(), writes });
    return;
  }
  // By the name the user reads: the fake's `textContent` is the node's own
  // text, so the name is looked for on the row's children.
  const row = withClass(REGIONS.rail, "baserow")
    .find((one) => one.children.some((child) => child.textContent === spec.pick));
  if (!row) throw new Error(`no base row reads "${spec.pick}"`);
  row.click();
  await settle();
  emit({ loaded, reopened, picked: regions(), writes });
});
"""


def _switch_base(tmp_path, pick=None, back=False):
    api = {"lightningai": _reply({"match": "exact", "job": LIGHTNING_JOB,
                                  "application": None}),
           "/api/base-resumes": _reply(SCORE_RESUMES),
           "GET /api/ats-scores": _reply(SCORE_ROWS)}
    return run_node(_SWITCH_BASE_DRIVER_JS, {
        "tabs": [{"id": 7, "url": POSTING_URL}],
        "replies": {"read_settings": SETTINGS_REPLY},
        "stored": {"widget.session": {**PICKED_ENTRY, "at": int(time.time() * 1000)}},
        "api": api,
        "pick": pick,
        "back": back,
    }, tmp_path, source=PANEL_SOURCE)


def _open_bodies(region):
    return [node["id"].removeprefix("stg-body-") for node in _by_class(region, "stg-body")]


def test_a_base_picked_from_the_reopened_job_row_returns_to_the_tailoring_fork(tmp_path):
    """The pick answers the question the Job row was reopened to ask, so the
    view closes and the body goes back to the step the user is on: the fork,
    now for the base they just chose."""
    out = _switch_base(tmp_path, "Data Scientist")
    assert _rows(_rail_rows({"regions": out["loaded"]}))["resume"]["state"] == "active"
    assert _open_bodies(out["reopened"]["rail"]) == ["job"]
    picked = out["picked"]
    assert _rows(_rail_rows({"regions": picked}))["resume"]["state"] == "active"
    assert _open_bodies(picked["rail"]) == ["resume"]
    assert _limbs(picked["rail"]) == ["Use my base resume", "Tailor to this job"]
    # The footer follows the open row, so it is the fork's primary again and
    # not a re-score of the list the user just chose from.
    assert _text(_by_class(picked["foot"], "cta")[0]) == "Quick tailor"
    assert _by_class(picked["rail"], "baserow") == []
    # …and the pick itself is what the fork now builds on, remembered for the
    # next page of the wizard.
    assert out["writes"][-1]["widget.session"]["baseSlug"] == "data_scientist"


def test_repicking_the_same_base_from_the_reopened_row_also_closes_it(tmp_path):
    """Clicking the base that was already chosen is the same answer as clicking
    another one: the user looked, confirmed, and wants the fork back."""
    out = _switch_base(tmp_path, "AI/ML Engineer")
    assert _open_bodies(out["picked"]["rail"]) == ["resume"]


def test_the_step_you_are_on_is_a_way_back_while_another_row_is_open(tmp_path):
    """Reopened Job, then changed their mind without picking: the active row
    is the natural thing to press, and before this it was not a control at
    all, so the only way back was the ▾ on the row they had opened."""
    out = _switch_base(tmp_path, back=True)
    reopened = out["reopened"]["rail"]
    door = next(node for node in _walk(reopened) if node["id"] == "stg-open-resume")
    assert door["tag"] == "BUTTON"
    assert door["attrs"]["aria-expanded"] == "false"
    back = out["back"]
    assert _open_bodies(back["rail"]) == ["resume"]
    assert _limbs(back["rail"]) == ["Use my base resume", "Tailor to this job"]
    # Back on the step it is on, the active row has no door: its body is open.
    assert [node for node in _walk(back["rail"]) if node["id"] == "stg-open-resume"] == []


# ---------- the base-as-is claim can be withdrawn ---------------------------
#
# "Use my base resume" finishes the Resume stage by SKIPPING it, and a skipped row
# was a wall: the Resume row read "Using your base resume as is." and there was no
# way back to the tailoring fork short of unbinding the whole page (reported
# live on an Itron wizard). The un-pick round already settled the grammar — a
# claim the user made is theirs to withdraw — and these tests are that grammar
# one stage down. The distinction they exist to protect is WHOSE skip it is: a
# row skipped by the user's own claim is a door, a row skipped by the path's
# arithmetic is not.

_BASE_ARMED_DRIVER_JS = _PANEL_FAKES_JS + r"""
const opener = (key) => findById(REGIONS.rail, `stg-open-${key}`);
const ns = loadModules();
main(async () => {
  await settle();
  const armed = regions();
  // Everything after the load has landed. The boot's own four round trips are
  // not what these tests are about; whether opening a body or withdrawing a
  // claim adds a fifth is exactly what they are about.
  const bootSends = sent.length;
  // Which rows offer a door AT ALL, asked of the rendered rail rather than of
  // the model: the door is a real <button> with a stable id, and "the rail
  // drew one" is the only version of this question the user can see.
  const doors = ["job", "resume", "fill", "track"]
    .filter((key) => opener(key) !== null);
  const door = opener("resume");
  if (door) door.click();
  await settle();
  if (spec.openTailor === true) {
    const tailor = withClass(REGIONS.rail, "fork")
      .flatMap((row) => row.children)
      .find((limb) => limb.textContent === "Tailor to this job");
    if (!tailor) throw new Error("the reopened body offers no Tailor limb");
    tailor.click();
    await settle();
  }
  if (spec.quickTailor === true) {
    const quick = withClass(REGIONS.rail, "fork")
      .flatMap((row) => row.children)
      .find((limb) => limb.textContent === "Quick tailor");
    if (!quick) throw new Error("the disclosed fork offers no Quick tailor limb");
    quick.click();
    await settle();
  }
  const reopened = regions();
  let withdrawn = null;
  if (spec.withdraw === true) {
    // BY LABEL as well as by class, for `press`'s reason above: a control that
    // is not on screen must fail loudly rather than leave the click unmade.
    const stop = withClass(REGIONS.rail, "unpick")
      .find((limb) => limb.textContent === "Stop using the base resume");
    if (!stop) throw new Error("the reopened body offers no way out");
    stop.click();
    await settle();
    withdrawn = regions();
  }
  const after = ns.panel.actionStore().read();
  emit({ armed, reopened, withdrawn, doors, writes,
         askedAfterBoot: sent.slice(bootSends),
         facts: {
           baseArmed: after.baseArmed === true,
           baseSlug: after.baseSlug,
           baseSelected: after.baseSelected === true,
           touched: after.touched === true,
           revisit: after.revisit,
           note: after.note,
           application: after.application,
         } });
});
"""


def _armed(tmp_path, **spec):
    """The apply page of a wizard with the base already armed — the state the
    arming was MADE for, restored off the bridge exactly as a live page does.

    `matched` is the one axis: the backend either knows this posting or does
    not, and the withdrawal lands the user on a different rung of the library
    ladder in each case.
    """
    matched = spec.pop("matched", False)
    spec.setdefault("tabs", [{"id": 7, "url": LIGHTNING_APPLY_URL}])
    spec.setdefault("replies", {"read_settings": SETTINGS_REPLY})
    spec.setdefault("stored", {"widget.session": _armed_entry()})
    spec.setdefault("page",
                    {"detect_page": _reply({"tier": "A", "form": True, "score": 3})})
    api = {"lightningai": _reply(
               {"match": "exact", "job": LIGHTNING_JOB, "application": None} if matched
               else {"match": "none", "job": None, "application": None}),
           "/api/base-resumes": _reply(SCORE_RESUMES),
           "GET /api/ats-scores": _reply(SCORE_ROWS)}
    api.update(spec.pop("api", {}))
    return run_node(_BASE_ARMED_DRIVER_JS, {**spec, "api": api}, tmp_path,
                    source=PANEL_SOURCE)


def _body(painted):
    """The Resume stage's body, by the id the rail gives whichever row is open.
    Reached by id rather than by class because "the body under the row I
    opened" is the whole subject here — `stg-body` alone would find whatever
    body happened to be rendered."""
    return next(n for n in _walk(painted["rail"]) if n.get("id") == "stg-body-resume")


def test_the_row_you_skipped_by_choice_is_a_door_and_the_ones_the_path_skipped_are_not(tmp_path):
    """THE DISTINCTION, rendered. Both Job and Resume are greyed and dashed on
    this page, and exactly one of them opens.

    The user pressed one button, and it answered the RESUME stage's own
    question ("tailor, or not?"). Job is skipped because the shortcut never
    asked the library — not a decision anybody made, so nothing to withdraw.
    A door there would be a rail offering to undo arithmetic.
    """
    out = _armed(tmp_path)
    rows = _rows(_rail_rows({"regions": out["armed"]}))
    assert [rows[key]["state"] for key in ("job", "resume")] == [
        "skipped", "skipped"]
    assert rows["fill"]["state"] == "active"
    assert out["doors"] == ["resume"]
    # …and the door says so the way every other one does, rather than by being
    # a row that happens to respond to a click.
    door = next(n for n in _walk(out["armed"]["rail"]) if n.get("id") == "stg-open-resume")
    assert door["tag"] == "BUTTON"
    assert door["attrs"]["aria-expanded"] == "false"
    assert "▸" in _text(door)


def test_the_reopened_base_as_is_row_names_the_choice_and_offers_both_ways_on(tmp_path):
    """What the door opens onto: the claim in the user's own words, the whole
    tailoring fork, and the way out.

    The "Use my base resume" limb is GONE, and that is the one edit rather than a
    trimmed-down body: pressing it would re-assert a claim already in force,
    which is a control that cannot do anything.
    """
    out = _armed(tmp_path)
    body = _body(out["reopened"])
    assert "Using AI/ML Engineer as is" in _text(body)
    assert _limbs(body) == ["Tailor to this job"]
    assert [n["text"] for n in _by_class(body, "unpick")] == ["Stop using the base resume"]
    # Nothing was asked of the backend to open a body.
    assert out["askedAfterBoot"] == []


def test_a_reopened_skipped_row_stays_skipped_and_the_rail_stays_put(tmp_path):
    """A reopened view never moves the rail, and it never earns a tick: the
    step the user is ON is a fact about their application, the body they have
    opened is a fact about what they are looking at. Reopening a row skipped by
    choice must not read as un-skipping it — the claim is still in force until
    the withdraw is pressed.
    """
    out = _armed(tmp_path)
    rows = _rows(_rail_rows({"regions": out["reopened"]}))
    assert rows["resume"]["state"] == "skipped"
    assert rows["resume"]["summary"] == "Using your base resume as is."
    assert rows["resume"]["numeral"] != "✓"
    assert rows["fill"]["state"] == "active"
    door = next(n for n in _walk(out["reopened"]["rail"])
                if n.get("id") == "stg-open-resume")
    assert door["attrs"]["aria-expanded"] == "true"
    assert door["attrs"]["aria-controls"] == "stg-body-resume"


def test_the_second_fork_level_still_discloses_under_the_reopened_claim(tmp_path):
    """The fork composes rather than being re-implemented: Tailor still
    discloses Quick tailor and Custom in Studio, and the withdraw stays last —
    it is the way OUT of the stage, not one of the ways through it."""
    body = _body(_armed(tmp_path, matched=True, openTailor=True)["reopened"])
    assert _limbs(body) == ["Tailor to this job", "Quick tailor", "Tailor in Maestro CS ↗"]
    assert _text(body["children"][-1]) == "Stop using the base resume"


def test_a_tailor_from_the_reopened_door_takes_the_claim_off_the_body(tmp_path):
    """DATA OVERRIDES THE CLAIM, and `baseArmed` alone does not say so.

    Reopen the skipped Resume row, press Quick tailor, and an application
    exists — which is exactly what `stageFor`'s `fillFromBase` requires the
    absence of, so the shortcut stops firing, the flag goes inert and Fill will
    attach the tailored PDF rather than the base. The row is `done` now, so the
    door stays open (correctly), and a body still reading "Using ⟨base⟩ as-is"
    over a withdraw that moves nothing would be a false sentence about which
    document is going into the form — beside a control that cannot do anything,
    which is the very thing this body drops the "Use my base resume" limb to avoid.
    """
    out = _armed(tmp_path, matched=True, openTailor=True, quickTailor=True,
                 api={"quick-tailor": TAILORED_REPLY})
    rows = _rows(_rail_rows({"regions": out["reopened"]}))
    assert rows["resume"]["state"] == "done"        # the door is still open
    body = _body(out["reopened"])
    assert "Using AI/ML Engineer as is" not in _text(body)
    assert _by_class(body, "unpick") == []
    # …and it is the done step's body: a resume with its PDF, and one small
    # way to tailor in Maestro CS.
    assert _text(body) == "Tailor in Maestro CS ↗"


def test_stop_using_base_as_is_returns_the_rail_to_the_ladder(tmp_path):
    """The withdrawal, from the outside: the claim is gone, the shortcut rung
    stops firing, and `stageFor` puts the user back on the library ladder at
    the rung the DATA supports — Job here, because the backend does not know
    this apply url and the shortcut was the only thing carrying them past it.

    What it does NOT touch is the point of the list: which base they picked is
    a different answer, and making them choose it again to ask for the same
    thing would be the un-pick round's mistake repeated.
    """
    out = _armed(tmp_path, withdraw=True)
    rows = _rows(_rail_rows({"regions": out["withdrawn"]}))
    assert rows["job"]["state"] == "active"
    assert rows["resume"]["state"] == "locked"
    assert rows["resume"]["summary"] == ""
    # And nothing was asked of the backend on the way out: the claim was the
    # panel's own, and so is taking it back.
    assert out["askedAfterBoot"] == []


def test_the_withdrawal_clears_the_claim_and_nothing_that_is_not_the_claim(tmp_path):
    """The write set, which is `useBaseAsIs`'s inverse and no wider.

    Which base they picked is a DIFFERENT answer, and making them choose it
    again in order to ask for the same thing is the un-pick round's mistake
    repeated. The view goes with the claim, though: the row it was opened over
    is not skipped any more, so leaving it open would be a body under a rail
    that moved.
    """
    facts = _armed(tmp_path, withdraw=True)["facts"]
    assert facts["baseArmed"] is False
    assert facts["baseSlug"] == "ai_ml_engineer"
    assert facts["baseSelected"] is True
    assert facts["application"] is None
    assert facts["revisit"] is None


def test_withdrawing_on_a_page_the_backend_knows_lands_on_the_resume_fork(tmp_path):
    """The other half of "back to the ladder", and the reason the rung is not
    hard-coded: with the job matched and a base already chosen, the ladder's
    own order puts the user at Resume — where the fork asks the question again,
    with "Use my base resume" back on it.
    """
    out = _armed(tmp_path, matched=True, withdraw=True)
    rows = _rows(_rail_rows({"regions": out["withdrawn"]}))
    assert rows["resume"]["state"] == "active"
    assert rows["job"]["state"] == "done"
    body = _body(out["withdrawn"])
    assert _limbs(body) == ["Use my base resume", "Tailor to this job"]
    assert _by_class(body, "unpick") == []
    assert "Using AI/ML Engineer as is" not in _text(body)


def test_withdrawing_stops_the_bridge_from_rearming_the_claim(tmp_path):
    """THE TRAP, and the twin of the un-pick lane's own. The arming was written
    down precisely so it would cross a page load — that is what `useBaseAsIs`
    is for — so a withdrawal that only cleared the store would be undone by the
    very next page of the wizard, which restores `baseArmed` from the bridge.
    The rewrite is not bookkeeping; it is the withdrawal.
    """
    out = _armed(tmp_path, withdraw=True)
    writes = [w for w in out["writes"] if w.get("widget.session")]
    assert writes, "the withdrawal never rewrote widget.session"
    entry = writes[-1]["widget.session"]
    assert entry["baseArmed"] is False
    # The base choice rides on, which is what makes the re-armed page honest
    # rather than empty.
    assert entry["baseSlug"] == "ai_ml_engineer"
    later = _load(tmp_path, tabs=[{"id": 7, "url": LIGHTNING_APPLY_URL}],
                  stored={"widget.session": entry},
                  page={"detect_page": _reply({"tier": "A", "form": True, "score": 3})},
                  api={"lightningai": _reply({"match": "none", "job": None,
                                              "application": None}),
                       "/api/base-resumes": _reply(SCORE_RESUMES),
                       "/api/ats-scores": _reply(SCORE_ROWS)})
    rows = _rows(_rail_rows(later))
    assert rows["resume"]["state"] != "skipped"
    assert rows["job"]["state"] == "active"
    assert "stg-open-resume" not in [n["id"] for n in _walk(later["regions"]["rail"])]


def test_choosing_the_base_hands_focus_to_the_row_it_finished(tmp_path):
    """"Use my base resume" finishes the step by skipping it, so the button
    leaves with the body. Focus goes to the Resume row's door — the way back
    to the choice — rather than falling to the document."""
    out = _resume(tmp_path, press="Use my base resume")
    assert out["focusedAfter"] == "stg-open-resume"


def test_the_arming_page_offers_the_way_out_too(tmp_path):
    """The claim is armed before any form is in front of the user, and the way
    back is the same door as everywhere else.

    IT USED TO BE A DIFFERENT SHAPE, and that is the change: the shortcut was
    gated on a form, so on a posting page the rail skipped nothing, the Resume
    row stayed ACTIVE and its body carried the withdrawal as the only way out.
    The claim now skips the same row wherever it is made, so this page gets the
    door — and the body behind it is the same body, because it is keyed on the
    CLAIM rather than on which row it is under.
    """
    out = _resume(tmp_path, press="Use my base resume", reopen="resume")
    rows = _rows(_rail_rows({"regions": out["settled"]}))
    assert rows["resume"]["state"] == "skipped"
    body = _body(out["reopened"])
    assert "Using AI/ML Engineer as is" in _text(body)
    assert [n["text"] for n in _by_class(body, "unpick")] == ["Stop using the base resume"]
    # The limb that re-asserts a claim already in force is not offered here
    # either — the reopened body drops it wherever it is opened.
    assert "Use my base resume" not in _limbs(out["reopened"]["rail"])


# ---------- a bound application answers the base question ----------
#
# THE "asks to tailor again" BUG, driven. A job tailored in the web app or over
# MCP, opened on its posting: the backend's `/api/jobs/match` binds the
# application, so no base is clicked, no session is restored and no draft is
# picked. The rail stuck on the base step in front of a tailored application
# with its PDF, and Fill stayed locked. The application's own `base_resume` is
# the answer, and it is also the base the rings compare against.

BOUND_APPLICATION = {"id": "app-1", "status": "draft", "base_resume": "data_scientist"}
BOUND_TAILORED_ROW = {"target_type": "application", "target_id": "app-1",
                      "phase": "tailored", "composite": 77.0}


def _bound(tmp_path, scores):
    tmp_path.mkdir(exist_ok=True)
    return _load(tmp_path, api={
        "lightningai": _reply({"match": "exact", "job": LIGHTNING_JOB,
                               "application": BOUND_APPLICATION}),
        "/api/base-resumes": _reply(SCORE_RESUMES),
        "/api/ats-scores": scores,
        "/api/applications/app-1": _reply({"pdf_path": "renders/app-1.pdf",
                                           "status": "draft",
                                           "base_resume": "data_scientist"}),
    })


def _journey(out):
    rows = _rows(_rail_rows(out))
    return {key: (row["state"], row["numeral"]) for key, row in rows.items()}


def test_a_bound_application_with_its_pdf_opens_at_fill_with_no_base_click(tmp_path):
    out = _bound(tmp_path, _reply([*SCORE_ROWS, BOUND_TAILORED_ROW]))
    journey = _journey(out)
    assert journey["job"] == ("done", "✓")
    assert journey["resume"] == ("done", "✓")
    assert journey["fill"][0] == "active"
    # What each done row settled: the application's base and its score, and
    # the tailored resume with its own.
    rows = _rows(_rail_rows(out))
    assert rows["job"]["summary"] == "Data Scientist · 64"
    assert rows["resume"]["summary"] == "Resume ready · 77"
    # The Base ring is the base the application was tailored from (64), not
    # the ranking's best (72), so the "+N" says what tailoring did.
    identity = out["regions"]["identity"]
    assert [ring["text"] for ring in _by_class(identity, "ring")] == ["64", "77"]
    assert _by_class(identity, "delta")[0]["text"] == "+13"


def test_the_bound_application_answers_even_when_the_scores_read_fails(tmp_path):
    failed = _bound(tmp_path / "failed", {"ok": False, "error": "boom", "status": 500})
    empty = _bound(tmp_path / "empty", _reply([]))
    for out in (failed, empty):
        journey = _journey(out)
        assert journey["job"] == ("done", "✓")
        assert journey["resume"] == ("done", "✓")
        assert journey["fill"][0] == "active"
        # No score to print, so the summaries say only what is known.
        rows = _rows(_rail_rows(out))
        assert rows["job"]["summary"] == "Data Scientist"
        assert rows["resume"]["summary"] == "Resume ready"


# ---------- the base limb acts only when it can mean something ----------

_BASE_GUARD_DRIVER_JS = _PANEL_FAKES_JS + r"""
const ns = loadModules();
const byId = (id) => findById(REGIONS.rail, id);
main(async () => {
  await settle();
  const loaded = regions();
  if (spec.tailorFirst === true) {
    byId("resume-tailor").click();
    await settle();
    byId("resume-quick").click();       // held open: the tailor is running
  }
  const writesBefore = writes.length;
  byId("resume-base").click();
  await settle();
  const facts = ns.panel.actionStore().read();
  const after = { baseArmed: facts.baseArmed === true,
                  writesDuring: writes.length - writesBefore };
  release();
  await settle();
  emit({ loaded, after });
});
"""


def test_the_base_limb_does_nothing_while_a_tailor_runs(tmp_path):
    """`actingLimb` locks with `aria-disabled` so focus survives the rebuild,
    which means the click still arrives. The action refuses while `busy`, as
    `stopUsingBaseAsIs` does, or the base would arm under a running tailor."""
    out = run_node(_BASE_GUARD_DRIVER_JS, {
        "tabs": [{"id": 7, "url": POSTING_URL}],
        "replies": {"read_settings": SETTINGS_REPLY},
        "stored": {"widget.session": {**PICKED_ENTRY, "at": int(time.time() * 1000)}},
        "hold": ["quick-tailor"],
        "tailorFirst": True,
        "api": {"lightningai": _reply({"match": "exact", "job": LIGHTNING_JOB,
                                       "application": None}),
                "/api/base-resumes": _reply(SCORE_RESUMES),
                "GET /api/ats-scores": _reply(SCORE_ROWS),
                "quick-tailor": TAILORED_REPLY},
    }, tmp_path, source=PANEL_SOURCE)
    assert out["after"] == {"baseArmed": False, "writesDuring": 0}


def test_the_base_limb_beside_an_application_is_focusable_and_does_nothing(tmp_path):
    """Off for good beside an application, so `aria-disabled` rather than
    `disabled`: a keyboard user can reach it and hear its reason. Pressed, it
    changes nothing."""
    out = run_node(_BASE_GUARD_DRIVER_JS, {
        "tabs": [{"id": 7, "url": POSTING_URL}],
        "replies": {"read_settings": SETTINGS_REPLY},
        "api": {"lightningai": _reply({"match": "exact", "job": LIGHTNING_JOB,
                                       "application": {"id": "app-1", "status": "draft"}}),
                "/api/applications/app-1": _reply({"pdf_path": None, "status": "draft"}),
                "/api/base-resumes": _reply(SCORE_RESUMES),
                "GET /api/ats-scores": _reply(SCORE_ROWS)},
    }, tmp_path, source=PANEL_SOURCE)
    base = next(n for n in _walk(out["loaded"]["rail"]) if n["id"] == "resume-base")
    assert base["disabled"] is False
    assert base["attrs"]["aria-disabled"] == "true"
    assert base["attrs"]["aria-describedby"] == "base-off-note"
    assert out["after"] == {"baseArmed": False, "writesDuring": 0}
