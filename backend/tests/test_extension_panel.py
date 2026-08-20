"""The side panel's SHELL: stage inference, the document, the loads, the guard.

`extension/panel/` renders the journey; `extension/shared/decisions.js` owns
the pure decisions the panel renders from. Tests here run the real functions
via the node harness, under this repo's standing rule for extension tests:
behavioural tables over source pins wherever the code can be executed.

THE SUBJECT IS NOW SIX FILES, and this docstring is the map of all of them. A
section that is not on this list is a section the next author will not find.

THIS FILE — everything that is true before any one stage is:

 1. `stageFor` — the whole stage table, driven through `loadModules()`;
 2. `sessionTenant` — the tenant scope, which nothing used to execute;
 3. the panel DOCUMENT — its load order, the tab binding that is the panel's
    own guard, and the render loop, driven through `loadModules()` against a
    faked `chrome` and a faked document tree;
 4. `railModel` — the four rail states over real `stageFor` decisions;
 5. `resetPageFacts` — which facts a page change clears, handed over whole;
 6. what the panel LOADS, and for which tab — `applyMatch`, the four round
    trips, and what each degrades to;
 7. the tab binding with real loads in flight — the generation guard, in the
    two shapes that have actually gone wrong (a late match, a late score read);
 8. the remembered pick, read from the store the widget writes;
 9. `detect_page` — does the page in front of the user hold a form, asked
    without injecting anything to find out;
10. THE SESSION KEY, the panel's half — one key read, and the one it retired
    swept on the way past;
11. THE REOPENED DONE ROW — the rail's other half and the one thing here a
    CLICK decides: which body is open (`card.revisit`), that the rail's own
    state does not follow it, that the footer's primary does, and the two ways
    the data takes the view back. It is item 4's twin and sits at the end of
    the file rather than beside it because it is DRIVEN — every claim is a real
    press through the real render loop — where `railModel`'s section is a table.

THE STAGE FILES — one per rail stage, each holding the body AND the actions
behind it, because a body and the round trip it fires are two halves of one
claim:

  `test_extension_panel_job.py`     the posting read off the page, edited in
                                    the store, and saved; plus the application
                                    picker (form + no match → recent drafts,
                                    one pick arms the rail and the session);
  `test_extension_panel_score.py`   the ranked list, the pick, the entry the
                                    two surfaces share, and `scoreAllBases`;
  `test_extension_panel_resume.py`  the two-level fork, the base-as-is
                                    shortcut end to end, and `quickTailor`;
  `test_extension_panel_fill.py`    the pass, the report, the pause row and
                                    the QnA drawer — three sections of ONE
                                    subject, because `fillBody` renders all of
                                    it;
  `test_extension_panel_track.py`   the status in words, the evidence line and
                                    its honest absence, and the one PATCH this
                                    extension makes.

THE APPARATUS IS `tests/extension_panel_harness.py`, and it is what the split
was waiting on rather than a by-product of it: `_load`, `_rail_rows`,
`_by_class`, `_reply` and the fakes are ONE apparatus every file calls, so a
per-stage split that duplicated them would be five copies of a fake that has
to agree with panel.js about what a render leaves behind — disagreeing
silently, with every file green. Its header carries the rule for what belongs
in it.

The service worker's half of this feature — the toolbar-click registration,
`fanoutTab`, the two panel doors and the `sender.id` check — is in
`test_extension_sw_router.py`: same trust boundary, seen from the side that
decides whether to believe the panel at all.

THE SESSION KEY'S SECOND HALF left at Task 13 — this file's FIRST split — for
the floating card's own guarded restore. R-C deleted that file with the card;
the guard it tested lives on in `restoreSession` here, where it is now the
condition of writing an application-less entry at all.

THE SECOND SPLIT, TAKEN AT TASK 15 (forecast at Task 9, trigger fired and
recorded unfollowed at Task 12, tightened at Task 13 and again at Task 14).
The trigger was "the Track section landing at all" and the seam was
pre-chosen: per-stage files, joined by nothing, because they share only the
drivers. What the trigger named as the blocker was exactly right and is what
this split had to answer FIRST — the shared apparatus is a harness MODULE,
decided before the cut rather than during it.

WHAT THE TWO SPLITS HAVE IN COMMON, because it is the lesson rather than the
history: both were blocked on a shared thing rather than on a boundary, and
both were resolved by naming where the shared thing lives rather than by
duplicating it. Task 13's was the session entry (`tests/extension_fixtures.py`
— the SUBJECT of both files, so two copies drifting is precisely the failure
the two sides exist to catch); Task 15's is the panel's document apparatus.
Duplication is the right call for an incidental constant and the wrong one for
the contract under test.

WHEN THESE FILES SPLIT AGAIN. A stage is the unit, so they do not: a sixth
rail stage would be a sixth file. The live question is a FILE growing past its
stage, of which `test_extension_panel_fill.py` (~2270 lines, three sections)
is the only candidate — and it is deliberately NOT cut today, because the
pause row and the drawer are rendered by `fillBody` and tested through the
same driver. TRIGGER for cutting it: a fill sub-concern with its OWN driver.
"""

import json
import re
import time

import pytest

from tests.extension_fixtures import (
    COHERE_TENANT,
    LIGHTNING_APPLY_URL,
    PICKED_ENTRY,
    POSTING_URL,
    entry,
)
from tests.extension_harness import js_code, run_node
from tests.extension_panel_harness import (
    ACME_JOB,
    APP_URL,
    APPLY_URL,
    BASE_RESUMES,
    DECISIONS_JS,
    EXTENSION,
    LIGHTNING_JOB,
    NOTHING_TO_SAVE,
    OTHER_URL,
    PANEL_CODE,
    PANEL_CSS,
    PANEL_HTML,
    PANEL_OWN_SRCS,
    PANEL_SCRIPT_SRCS,
    PANEL_SOURCE,
    SCORE_RESUMES,
    SCORE_ROWS,
    SCORES,
    SETTINGS_REPLY,
    _armed_entry,
    _by_class,
    _load,
    _PANEL_FAKES_JS,
    _panel_script,
    _rail_rows,
    _reply,
    _rows,
    _text,
    _walk,
)


# Read for ONE assertion, section 16's: the injected copy of `sanitizeAnswer`
# that `fillAnswersByQid` has to carry, pinned identical to the shared one.
OPEN_QUESTIONS_JS = (
    EXTENSION / "content" / "open-questions.js").read_text(encoding="utf-8")
# Read for ONE assertion, section 11's: that the ranked list is fed by the
# SHARED ranking rather than by a second copy that happened to arrive sorted.
SCORE_BODY_CODE = js_code(_panel_script("stages/score.js"))


# `loadModules()` runs the real file — the IIFE, the namespace join, the
# `ns.decisions` publication — rather than slicing one function out of the text
# with `extract`. A module that never publishes itself, or that throws on load,
# therefore fails here instead of being invisible to a source slice.
_STAGE_DRIVER_JS = r"""
const { stageFor } = loadModules().decisions;
main(async () => {
  const out = {};
  for (const [name, card] of Object.entries(spec.cards)) out[name] = stageFor(card);
  emit(out);
});
"""


_CARDS = {
    # match null = backend never asked / unreachable: NEVER claims the job
    # exists (resolvePrimary's rule, with the rung order preserved).
    "unreachable": {"match": None, "hasApplication": False, "pdfReady": False,
                    "status": None, "touched": False, "hasForm": True,
                    "baseArmed": False, "hasScores": False, "baseSelected": False},
    "fresh_posting": {"match": "none", "hasApplication": False, "pdfReady": False,
                      "status": None, "touched": False, "hasForm": False,
                      "baseArmed": False, "hasScores": False, "baseSelected": False},
    "in_library_unscored": {"match": "exact", "hasApplication": False, "pdfReady": False,
                            "status": None, "touched": False, "hasForm": False,
                            "baseArmed": False, "hasScores": False, "baseSelected": False},
    "scored_and_picked": {"match": "exact", "hasApplication": False, "pdfReady": False,
                          "status": None, "touched": False, "hasForm": False,
                          "baseArmed": False, "hasScores": True, "baseSelected": True},
    # Score needs BOTH halves — the scores exist AND a base is chosen. Each
    # half alone leaves the stage at Score.
    "scored_unpicked": {"match": "exact", "hasApplication": False, "pdfReady": False,
                        "status": None, "touched": False, "hasForm": False,
                        "baseArmed": False, "hasScores": True, "baseSelected": False},
    "picked_unscored": {"match": "exact", "hasApplication": False, "pdfReady": False,
                        "status": None, "touched": False, "hasForm": False,
                        "baseArmed": False, "hasScores": False, "baseSelected": True},
    "tailored_pdf_ready": {"match": "exact", "hasApplication": True, "pdfReady": True,
                           "status": "draft", "touched": False, "hasForm": True,
                           "baseArmed": False, "hasScores": True, "baseSelected": True},
    "filled_here": {"match": "exact", "hasApplication": True, "pdfReady": True,
                    "status": "draft", "touched": True, "hasForm": True,
                    "baseArmed": False, "hasScores": True, "baseSelected": True},
    "applied": {"match": "exact", "hasApplication": True, "pdfReady": True,
                "status": "applied", "touched": False, "hasForm": True,
                "baseArmed": False, "hasScores": True, "baseSelected": True},
    # Attached via track-this, then marked applied — an application that
    # was never tailored, so it has no PDF. The record says the journey is
    # over; the ladder must not send it back to Resume.
    "applied_no_pdf": {"match": "exact", "hasApplication": True, "pdfReady": False,
                       "status": "applied", "touched": False, "hasForm": True,
                       "baseArmed": False, "hasScores": True, "baseSelected": True},
    # The base-resume shortcut: form + base armed + no application skips
    # Score/Resume visibly rather than hiding them.
    "base_shortcut": {"match": "exact", "hasApplication": False, "pdfReady": False,
                      "status": None, "touched": False, "hasForm": True,
                      "baseArmed": True, "hasScores": False, "baseSelected": False},
    "base_shortcut_filled": {"match": "exact", "hasApplication": False, "pdfReady": False,
                             "status": None, "touched": True, "hasForm": True,
                             "baseArmed": True, "hasScores": False, "baseSelected": False},
    # THE LIVE ONE (Yum, 2026-08-19): the claim is made on a posting page and
    # there is no form on it. The user has answered the Resume stage's
    # question, so the rail must not sit on Resume — it goes where the
    # remaining work is, and the FILL stage is what says the work cannot start
    # here. `baseArmed` rides the tenant session across pages, so it also shows
    # up on a page whose application is already closed, which is the one guard
    # the shortcut still has.
    "armed_no_form": {"match": "exact", "hasApplication": False, "pdfReady": False,
                      "status": None, "touched": False, "hasForm": False,
                      "baseArmed": True, "hasScores": False, "baseSelected": False},
    "armed_but_applied": {"match": "exact", "hasApplication": True, "pdfReady": True,
                          "status": "applied", "touched": False, "hasForm": True,
                          "baseArmed": True, "hasScores": True, "baseSelected": True},
    # The escape hatch: base armed over a form, job NOT in the library (or the
    # backend unreachable). The page can still be filled; the library must not
    # gate it (widget.js:800-810). Job is skipped-not-done: the rail re-asks.
    "base_shortcut_unmatched": {"match": None, "hasApplication": False, "pdfReady": False,
                                "status": None, "touched": False, "hasForm": True,
                                "baseArmed": True, "hasScores": False, "baseSelected": False},
}


@pytest.fixture(scope="module")
def stages(tmp_path_factory):
    return run_node(_STAGE_DRIVER_JS, {"cards": _CARDS},
                    tmp_path_factory.mktemp("stages"), source=DECISIONS_JS)


@pytest.fixture(scope="module")
def flipped(tmp_path_factory):
    """THE SAME TABLE WITH THE FORM VERDICT INVERTED, card for card.

    The rung walk, executed rather than argued. `hasForm` is a fact about the
    PAGE and stopped being an input to the stage on 2026-08-19; the only way to
    hold that is to run every rung of the ladder both ways and compare, because
    a gate re-introduced anywhere in `stageFor` — the shortcut, a `done` flag,
    the skip list — moves at least one of these cards and nothing else would
    say so.

    Built from `_CARDS` rather than written out, so a card added to the table
    is walked both ways whether or not its author thought about the form.
    """
    both = {name: {**card, "hasForm": not card["hasForm"]}
            for name, card in _CARDS.items()}
    return run_node(_STAGE_DRIVER_JS, {"cards": both},
                    tmp_path_factory.mktemp("flipped"), source=DECISIONS_JS)


SHORTCUT_NOTE = "Ready to autofill from your base resume."


def test_the_return_contract_is_the_whole_of_what_a_renderer_reads(stages):
    # Pinned so deleting or renaming a key dies here rather than as a silently
    # blank row in whichever stage view happens to read it.
    assert set(stages["applied"]) == {
        "stage", "done", "skipped", "choiceSkipped", "fillFromBase",
        "shortcutNote", "nudge"}
    assert set(stages["applied"]["done"]) == {
        "job", "score", "resume", "fill", "track"}


def test_the_journey_opens_where_the_data_says(stages):
    assert stages["unreachable"]["stage"] == "job"      # re-asks; never lies
    assert stages["fresh_posting"]["stage"] == "job"
    assert stages["in_library_unscored"]["stage"] == "score"
    assert stages["scored_and_picked"]["stage"] == "resume"
    assert stages["tailored_pdf_ready"]["stage"] == "fill"
    assert stages["filled_here"]["stage"] == "track"
    assert stages["applied"]["stage"] == "track"


def test_score_needs_both_the_scores_and_a_chosen_base(stages):
    assert stages["scored_unpicked"]["stage"] == "score"
    assert stages["scored_unpicked"]["done"]["score"] is False
    assert stages["picked_unscored"]["stage"] == "score"
    assert stages["picked_unscored"]["done"]["score"] is False
    assert stages["scored_and_picked"]["done"]["score"] is True


def test_done_marks_only_the_steps_the_data_supports(stages):
    ready = stages["tailored_pdf_ready"]["done"]
    assert ready["job"] is True
    assert ready["resume"] is True
    assert ready["track"] is False          # a draft is not an applied job
    assert stages["applied"]["done"]["track"] is True
    assert stages["in_library_unscored"]["done"]["resume"] is False
    assert stages["unreachable"]["done"]["job"] is False


def test_the_base_shortcut_skips_visibly_not_secretly(stages):
    short = stages["base_shortcut"]
    assert short["stage"] == "fill"
    assert short["fillFromBase"] is True
    assert short["skipped"] == ["score", "resume"]
    assert short["shortcutNote"] == SHORTCUT_NOTE
    # Filling from base then landing on track offers to write it down.
    assert stages["base_shortcut_filled"]["stage"] == "track"
    assert stages["base_shortcut_filled"]["nudge"] == "track-this"
    # The note is the FILL stage's copy, so it goes away once fill is behind us.
    assert stages["base_shortcut_filled"]["shortcutNote"] is None
    for name in ("unreachable", "in_library_unscored", "tailored_pdf_ready", "applied"):
        assert stages[name]["shortcutNote"] is None, name
        assert stages[name]["skipped"] == [], name


def test_a_skip_the_user_chose_is_told_apart_from_a_skip_the_path_computed(stages):
    """WHOSE skip it is, which is the only question `choiceSkipped` answers.

    `baseArmed` is a claim — the user pressed "use base as-is" — and a claim is
    theirs to withdraw, so the row that holds it is a door back (panel.js
    `isReopenable`). The rest of the short rail is arithmetic: Score is skipped
    because nothing needs a ranking when nothing is being tailored, Job because
    the shortcut is a page-and-session fact that never asked the library.
    Nobody chose either, so there is nothing there to take back.

    RESUME AND ONLY RESUME, because the claim answered the RESUME stage's own
    question. Naming the whole skipped list here would put a withdraw door on
    three rows for one claim.
    """
    assert stages["base_shortcut"]["choiceSkipped"] == ["resume"]
    # Even when the shortcut is also carrying the user past Job.
    assert stages["base_shortcut_unmatched"]["skipped"] == ["job", "score", "resume"]
    assert stages["base_shortcut_unmatched"]["choiceSkipped"] == ["resume"]
    for name, out in stages.items():
        # A subset of `skipped`, always: a row that is not being skipped cannot
        # be a row skipped by choice, whatever else is true of the card.
        assert set(out["choiceSkipped"]) <= set(out["skipped"]), name
        # And it is empty wherever the shortcut is not firing.
        if not out["fillFromBase"]:
            assert out["choiceSkipped"] == [], name
    # THE FORM-LESS PAGE IS A DOOR TOO, and this line is the one that turned
    # over on 2026-08-19. It used to read `== []` — the claim was armed, no row
    # was skipped by it, and the user was left on a Resume row whose question
    # they had answered with no way past it. The claim skips the same row
    # wherever it is made, so the withdraw door is on the same row too.
    assert stages["armed_no_form"]["choiceSkipped"] == ["resume"]


def test_the_shortcut_guards_keep_it_off_the_pages_it_must_not_take_over(stages):
    # ONE GUARD LEFT, and it is the one that is about DATA: an application
    # overtakes the claim, so an armed session on a job already applied to
    # belongs at Track and never at Fill.
    closed = stages["armed_but_applied"]
    assert closed["fillFromBase"] is False
    assert closed["stage"] == "track"


def test_an_armed_claim_on_a_form_less_page_is_still_a_finished_choice(stages):
    """THE LIVE BUG (Yum, 2026-08-19), as the stage table sees it.

    The user pressed "use base as-is" on a posting page. That answers the
    Resume stage's question whether or not a form is in front of them, so the
    rail moves off Resume — which used to be the whole complaint: it stayed
    there, with Fill locked, no primary and no sentence, and the one thing the
    panel knew (this page has no form) was the one thing it did not say.

    THE FORM GATE DID NOT DISAPPEAR, it moved to the button. `stageFor` says
    where the user IS; panel.js's `primaryRefused` and the Fill body say what
    can happen here. The only trace of it left in this function is the
    shortcut's copy — see the note test below.
    """
    no_form = stages["armed_no_form"]
    assert no_form["fillFromBase"] is True
    assert no_form["stage"] == "fill"
    assert no_form["skipped"] == ["score", "resume"]
    assert no_form["done"]["fill"] is False


def test_the_form_verdict_cannot_move_a_single_rung_of_the_ladder(stages, flipped):
    """THE RUNG WALK, executed: every card in the table, both form verdicts.

    `hasForm` is a fact about the page and the stage is a fact about which
    question is still open. After 2026-08-19 the two are separate, and the way
    to keep them separate is to run the whole ladder both ways rather than to
    reason about the one rung that changed — the shortcut's gate was itself a
    reasonable-looking line that quietly decided a stage from a page.

    THE ONE PERMITTED DIFFERENCE is `shortcutNote`, which is copy rather than
    inference: "Ready to autofill from your base resume" is a promise about the
    page, so it is withheld where the page cannot keep it.
    """
    assert set(stages) == set(flipped)
    for name in stages:
        with_form = {key: value for key, value in stages[name].items()
                     if key != "shortcutNote"}
        without = {key: value for key, value in flipped[name].items()
                   if key != "shortcutNote"}
        assert with_form == without, name


def test_the_shortcut_copy_is_the_one_thing_the_form_still_decides(stages, flipped):
    """A promise about the page, kept only where the page can keep it.

    "Ready to autofill from your base resume" over a posting page is the same
    false promise as "Application ready" over a job nobody tracked — one page
    earlier. The Fill body says the true thing instead ("No application form on
    this page — open the employer's Apply page"), which is why there is no
    second sentence here: one fact, one copy, and it lives where the user is
    already looking.
    """
    # `base_shortcut` has a form in the table; its flipped twin does not.
    assert stages["base_shortcut"]["shortcutNote"] == SHORTCUT_NOTE
    assert flipped["base_shortcut"]["shortcutNote"] is None
    # …and `armed_no_form` is the same pair read from the other end.
    assert stages["armed_no_form"]["shortcutNote"] is None
    assert flipped["armed_no_form"]["shortcutNote"] == SHORTCUT_NOTE


def test_the_library_never_gates_filling_the_page_in_front_of_you(stages):
    # widget.js:800-810: filling a form is a question about the PAGE and the
    # session. A job we cannot look up (unreachable backend, or simply not in
    # the library) must not take away the fill the user already armed a base
    # resume for.
    hatch = stages["base_shortcut_unmatched"]
    assert hatch["stage"] == "fill"
    assert hatch["shortcutNote"] == SHORTCUT_NOTE
    # Job is SKIPPED, never done — the rail still shows Add job and re-asks.
    assert hatch["skipped"] == ["job", "score", "resume"]
    assert hatch["done"]["job"] is False


def test_track_this_still_requires_having_touched_the_page(stages):
    # Nothing was filled or attached here, so there is nothing to write down.
    assert stages["fresh_posting"]["nudge"] is None


def test_a_closed_application_never_reopens_earlier_stages(stages):
    # An applied application with no tailored PDF used to land on "resume",
    # asking the user to tailor for a job they had already applied to.
    assert stages["applied_no_pdf"]["stage"] == "track"
    # …and the stage ladder is what refuses to go backwards, NOT `done.fill`,
    # which keeps meaning "this widget filled or attached HERE".
    assert stages["applied_no_pdf"]["done"]["fill"] is False
    assert stages["applied"]["done"]["fill"] is False
    assert stages["filled_here"]["done"]["fill"] is True


def test_mark_applied_never_requires_touched(stages):
    # The 2026-08-16 lesson: the nudge exists from the moment an application
    # is a draft — including on a page this widget never filled.
    assert stages["tailored_pdf_ready"]["nudge"] == "mark-applied"
    assert stages["applied"]["nudge"] is None


# ---------- the tenant scope, which nothing used to execute ----------

# A throw is REPORTED rather than allowed to kill the run, because totality is
# the property under test: `sessionTenant` answering null and `sessionTenant`
# dying are two different things, and a driver that died on the first bad url
# would fail every row at once and name none of them.
_TENANT_DRIVER_JS = r"""
const { sessionTenant } = loadModules().decisions;
main(async () => {
  const out = {};
  for (const [name, url] of Object.entries(spec.urls)) {
    try {
      out[name] = sessionTenant(url);
    } catch (err) {
      out[name] = `THREW: ${err.constructor.name}`;
    }
  }
  emit(out);
});
"""


@pytest.fixture(scope="module")
def tenants(tmp_path_factory):
    """Real posting and apply URLs, in the shapes the memory has to tell apart."""
    urls = {
        # One origin, two companies: the live 2026-08-16 bleed.
        "greenhouse_cohere": "https://job-boards.greenhouse.io/cohere/jobs/1234",
        "greenhouse_lightning": "https://job-boards.greenhouse.io/lightningai/jobs/99",
        # The same company's board, two steps of one wizard — what the memory
        # exists for, and the reason the URL itself cannot be the key. Workday
        # keeps the company in the SUBDOMAIN, so the first segment here is a
        # locale slug; it costs nothing (one tenant per locale, and a user does
        # not change locale mid-application) and the segment is what the shared
        # boards need.
        "workday_posting":
            "https://acme.wd5.myworkdayjobs.com/en-US/careers/job/Data-Scientist",
        "workday_apply":
            "https://acme.wd5.myworkdayjobs.com/en-US/careers/apply/applyManually",
        # A query string is part of the step, never part of the tenant.
        "lever_with_query": "https://jobs.lever.co/acme/abc-123?lever-source=x",
        # A site with no path at all still has to produce something stable.
        "bare_origin": "https://careers.acme.test",
        # The accepted cost of the rule: a company's own careers site whose
        # wizard moves OFF the first segment.
        "own_site_posting": "https://careers.acme.test/jobs/data-scientist",
        "own_site_apply": "https://careers.acme.test/apply/step-1",
        # No tenant identity at all. The panel evaluates whatever a tab holds,
        # and a tab that has not committed a url yet holds none of this.
        "empty": "",
        "unparseable": "not a url at all",
        # A browser page parses rather than throwing, and scopes to itself.
        # Recorded so the distinction stays deliberate: only what `new URL`
        # REFUSES becomes null.
        "browser_page": "chrome://newtab",
    }
    return run_node(_TENANT_DRIVER_JS, {"urls": urls},
                    tmp_path_factory.mktemp("tenants"), source=DECISIONS_JS)


def test_one_origin_two_companies_are_two_tenants(tenants):
    """The bug this is the fix for: job-boards.greenhouse.io serves thousands of
    companies from ONE origin, so a scope of origin alone restored a Cohere pick
    onto a Lightning posting and called it "Application ready"."""
    assert tenants["greenhouse_cohere"] == "https://job-boards.greenhouse.io/cohere"
    assert tenants["greenhouse_lightning"] == "https://job-boards.greenhouse.io/lightningai"
    assert tenants["greenhouse_cohere"] != tenants["greenhouse_lightning"]


def test_the_steps_of_one_wizard_share_a_tenant(tenants):
    """…and the other half: an ATS wizard is six page loads, so a scope that
    changed with the URL would forget the pick on the first of them."""
    assert tenants["workday_posting"] == tenants["workday_apply"]
    assert tenants["workday_posting"] == "https://acme.wd5.myworkdayjobs.com/en-US"


def test_the_scope_is_the_path_segment_only(tenants):
    # A query string identifies the step, the referrer, the search — never the
    # company, so it cannot be allowed to make two tenants out of one.
    assert tenants["lever_with_query"] == "https://jobs.lever.co/acme"
    # No path: still a tenant, and still origin-scoped rather than empty.
    assert tenants["bare_origin"] == "https://careers.acme.test/"


def test_a_url_with_no_tenant_identity_is_null(tenants):
    """`new URL("")` throws, and the panel asks this about whatever a TAB holds
    — a new tab, a chrome:// page, a url read before the tab committed one. So
    the function is total, and `null` is its answer for "no tenant identity
    here". `restorableSession` is what turns that into a refusal: a pick made
    on a real board carries a real tenant string and can never equal null."""
    assert tenants["empty"] is None
    assert tenants["unparseable"] is None
    # Only what `new URL` REFUSES is null. A browser page parses, and scoping
    # it to its own opaque origin costs nothing — no pick is made on one.
    assert tenants["browser_page"] == "null/"


def test_a_wizard_that_leaves_the_first_segment_forgets_the_pick(tenants):
    """The accepted limit, stated rather than discovered later.

    On a company's own careers site — one company per origin, so the segment
    buys nothing — a wizard that moves from /jobs/… to /apply/… reads as two
    tenants and the remembered pick does not survive the step. The cost is one
    re-pick on single-tenant sites; the alternative is the 2026-08-16 bleed on
    the multi-tenant boards, which is a wrong answer rather than a lost one.
    """
    assert tenants["own_site_posting"] == "https://careers.acme.test/jobs"
    assert tenants["own_site_apply"] == "https://careers.acme.test/apply"
    assert tenants["own_site_posting"] != tenants["own_site_apply"]


# ---------- the panel document: load order, tab binding, render loop ----------
#
# `loadModules()` again, and here it earns its keep twice over: panel.js binds
# to the active tab AT LOAD, so a module that throws while wiring itself — a
# renamed `ns.decisions`, a typo in the binding — fails here rather than as a
# panel that opens blank in a browser no test can drive.
#
# That same property is why the fakes below exist. The panel is a DOCUMENT and
# it talks to `chrome`; neither is optional at load, and the harness's own fake
# DOM models a FORM (`querySelector` answers `[data-rt-qid]` and little else),
# not a tree you can append regions to. So this section brings its own two
# seams and nothing more: a `chrome` that records what it was asked and replays
# what the spec says, and a document tree that remembers what was put in it.
# Neither decides anything the panel should decide.


def test_the_panel_document_is_self_contained_and_joins_the_namespace():
    # Comment-stripped throughout, which is `js_code`'s rule in HTML's
    # spelling: the document explains its own load order in prose directly
    # above the script tags, and a pin that the prose can satisfy — or, as
    # happened here, BREAK — pins nothing about the markup.
    markup = re.sub(r"<!--.*?-->", "", PANEL_HTML, flags=re.S)
    # Load order, and it is the document's whole dependency graph. Every one of
    # these is read at LOAD — by the roster that gathers it, or by panel.js —
    # so a tag out of order, or a tag missing, is a panel that fails on boot
    # rather than one that renders a rail with nothing under its active row, or
    # one whose every primary throws on the first click.
    #
    # DERIVED FROM THE TAG LIST rather than naming files, which is what makes
    # this survive the next stage: a `stages/track.js` added to the document
    # gets the "before its roster" rule for free, and one added to the
    # DIRECTORY without a tag is caught by the roster's own throw at boot.
    at = {src: markup.index(f'src="{src}"') for src in PANEL_SCRIPT_SRCS}
    # EVERY FILE IN THE TWO DIRECTORIES HAS A TAG, which is the one thing the
    # derived map above cannot see: a list read off the document agrees with
    # itself no matter which tag was dropped. The rosters throw loudly at boot
    # for a missing part — that is what makes the mutation fail everywhere
    # rather than nowhere — and this is the assertion that NAMES the file
    # instead of reporting it as every panel test dying at once.
    for family in ("stages", "actions"):
        on_disk = {f"{family}/{path.name}"
                   for path in (EXTENSION / "panel" / family).glob("*.js")}
        assert on_disk <= set(at), (
            f"panel.html has no <script> tag for {sorted(on_disk - set(at))}")
        # AND THE DELETION DIRECTION, named rather than left to a collection
        # error: a tag for a file that no longer exists would otherwise first
        # surface as `_panel_script`'s FileNotFoundError while building
        # PANEL_SOURCE — the least legible failure shape, and R-C is a
        # DELETION round, so this is the direction that will actually fire.
        tagged = {src for src in at if src.startswith(f"{family}/")}
        assert tagged <= on_disk, (
            f"panel.html still tags deleted file(s) {sorted(tagged - on_disk)}")
    assert at["../shared/decisions.js"] == min(at.values())
    assert at["panel.js"] == max(at.values())
    for src, index in at.items():
        # Each part before the roster that gathers it, and both rosters before
        # the controller that reads what they publish.
        if src.startswith("stages/"):
            assert index < at["stages.js"], src
        if src.startswith("actions/"):
            assert index < at["actions.js"], src
    assert at["stages.js"] < at["panel.js"]
    assert at["actions.js"] < at["panel.js"]
    # `duringAction` FIRST inside its family, and that one is a real load
    # constraint: every concern file destructures `ns.panelDuringAction` at the
    # top of its IIFE, so a tag after them binds `undefined` and every action
    # throws on its first press.
    assert at["actions/during.js"] == min(
        index for src, index in at.items() if src.startswith("actions/"))
    # `fill.js` before `pause.js` is a READING order and pinned as one: the
    # pause row reads `ns.panelFillFinished` when it RUNS, so the two would
    # work either way round. The document states the order so that the file
    # publishing the predicate is read before the file that converges on it.
    assert at["actions/fill.js"] < at["actions/pause.js"]
    # `pick.js` after `job.js` is a READING order: the picker is a Job-stage
    # concern, and the document states it next to Add job so the two writers
    # of that stage sit together.
    assert at["actions/job.js"] < at["actions/pick.js"]
    assert "http" not in markup
    # Every file the panel owns joins the ONE namespace — a module that built
    # its own object would publish into a room nobody else is in.
    for src in PANEL_OWN_SRCS:
        assert "window.careerStudioCompanion" in _panel_script(src), src
    # The single-fetch-site rule (sw.js's own comment names this panel as the
    # surface that must not break it). A panel is an extension page, so it CAN
    # fetch — nothing but this stops it. Over the WHOLE document rather than
    # one of its files: the rule is about the surface, and the splits spread it
    # across a dozen of them.
    assert "fetch(" not in js_code(PANEL_SOURCE)


def test_the_panel_follows_the_active_tab():
    # Comment-stripped, for the reason `js_code` gives: panel.js explains its
    # binding in prose, and a pin that a comment can satisfy pins nothing.
    for fragment in ("chrome.tabs.onActivated.addListener",
                     "chrome.tabs.onUpdated.addListener",
                     "lastFocusedWindow: true"):
        assert fragment in PANEL_CODE



_PANEL_BOOT_DRIVER_JS = _PANEL_FAKES_JS + r"""
loadModules();
// A listener the panel never registered is a MISSING listener, not a broken
// harness: firing null would kill the run and report "TypeError" for what is
// really "the panel stopped following the tab". The assertions below get to
// say that instead.
const fire = async (listener, ...args) => { if (listener) await listener(...args); };
main(async () => {
  await settle();
  const opened = regions();
  // The user switches tabs. A panel outlives page loads — that is the point —
  // so these two events are its only signal that the page changed.
  await fire(onActivated, { tabId: spec.switchTo });
  await settle();
  const switched = regions();
  await fire(onUpdated, spec.otherTab, { url: spec.otherUrl });
  await settle();
  const someoneElseNavigated = regions();
  await fire(onUpdated, spec.switchTo, { status: "complete" });
  await settle();
  const noUrlChange = regions();
  await fire(onUpdated, spec.switchTo, { url: spec.navigatedUrl });
  await settle();
  const navigated = regions();
  const sentBeforeClick = sent.length;
  const cta = withClass(REGIONS.foot, "cta")[0];
  cta.click();
  await settle();
  const clicked = regions();
  const sentAfterClick = sent.length;
  // …and away again. What the note said was about the page we just left.
  await fire(onActivated, { tabId: spec.switchTo });
  await settle();
  emit({
    queries, listeners, sent,
    opened, switched, someoneElseNavigated, noUrlChange, navigated,
    clicked, leftThePage: regions(), sentBeforeClick, sentAfterClick,
  });
});
"""





@pytest.fixture(scope="module")
def booted(tmp_path_factory):
    return run_node(_PANEL_BOOT_DRIVER_JS, {
        "tabs": [{"id": 7, "url": POSTING_URL}],
        "switchTo": 42,
        "otherTab": 7,
        "otherUrl": OTHER_URL,
        "navigatedUrl": POSTING_URL,
        "tabUrls": {"42": APPLY_URL},
        "replies": {"read_settings": SETTINGS_REPLY},
    }, tmp_path_factory.mktemp("panel_boot"), source=PANEL_SOURCE)


def test_the_panel_binds_to_the_active_tab_and_stays_bound(booted):
    """The binding is the panel's own guard, and nothing else can be it.

    `fanoutTab` verifies WHO may name a tab, never WHICH — a service worker
    cannot know which tab the user is looking at. So a `card.tabId` left stale
    across a tab switch would aim a fill, or a PDF attach, at the wrong tab and
    the SW would pass it. These three listeners are that guard.
    """
    assert booted["queries"] == [{"active": True, "lastFocusedWindow": True}]
    assert booted["listeners"] == ["onActivated", "onUpdated"]
    # The url is the only fact the panel has about a page it has not asked the
    # backend about yet, so it is what the identity line shows — which makes it
    # the visible proof of which tab the panel is bound to.
    assert "job-boards.greenhouse.io" in _text(booted["opened"]["identity"])
    assert "acme.wd5.myworkdayjobs.com" in _text(booted["switched"]["identity"])


def test_a_navigation_in_another_tab_never_moves_the_bound_one(booted):
    # `onUpdated` fires for every tab in the window. Acting on one the panel is
    # not bound to is the stale-tabId bug from the other direction: the panel
    # would show, and then act on, a page the user is not looking at.
    assert "acme.wd5.myworkdayjobs.com" in _text(booted["someoneElseNavigated"]["identity"])
    assert "boards.other.test" not in _text(booted["someoneElseNavigated"]["identity"])
    # An update with no url is a title, a favicon, a load state — not a page.
    assert "acme.wd5.myworkdayjobs.com" in _text(booted["noUrlChange"]["identity"])
    # …and a real same-tab navigation IS one. This is the SPA/wizard case: the
    # panel survives the load, so the event is all it gets.
    assert "job-boards.greenhouse.io" in _text(booted["navigated"]["identity"])


def test_the_header_link_points_at_the_web_app_and_never_at_nothing(booted):
    """Ported from the card's header rule (widget.js:1473-1492): the most
    specific thing we know wins, and `appUrl` is asked of the SW rather than
    kept here — DEFAULTS lives in one place."""
    assert {"type": "read_settings"} in booted["sent"]
    [link] = _by_class(booted["opened"]["identity"], "linkish")
    # No job and no application yet, so the link can only offer the app itself.
    assert link["href"] == APP_URL
    assert link["text"] == "Open in Maestro CS ↗"
    # The accessible name says the destination in full. Beside a job title this
    # matters more than it did beside the deleted wordmark.
    assert link["attrs"]["aria-label"] == "Open in Maestro CS"


def test_the_panel_says_its_own_name_nowhere_because_chrome_already_does(booted):
    """THE BRAND ROW IS GONE, and this is what keeps it gone.

    Chrome draws a side-panel title bar above this document carrying the
    extension's name; the panel then drew a mark, the words "Maestro CS" and
    the deep link directly beneath it. Same name twice, in the first 50px of a
    400px-wide surface, before a word about the page.

    Two assertions, because the deletion has two halves and either alone would
    pass while the other regressed: the header renders the product's name only
    as a DESTINATION, and the document no longer has the region that rendered
    it as chrome. The `linkish` exemption is the point rather than a hole —
    "Open in Maestro CS ↗" names where the link goes, which is the one honest
    use of the name here and the whole reason the row's link outlived the row.

    SCOPED TO THE HEADER, deliberately: the rail and the footer say "Maestro
    CS" in PROSE — the Track body sends you there, the unreachable note names
    it — and those are sentences about the app, not a title bar.

    The STYLESHEET's half of the same deletion is the test below.
    """
    for node in _walk(booted["opened"]["identity"]):
        if "Maestro CS" in node["text"]:
            assert "linkish" in node["class"].split(), node
    assert 'id="head"' not in PANEL_HTML


def test_the_deleted_bands_styles_went_with_it_and_the_link_got_its_own_line():
    """The stylesheet half, and a separate test rather than four more asserts
    on the one above: that one is about what the panel RENDERS and this is
    about what panel.css still declares, which are two failures with two fixes.

    A `.p-head` rule left behind styles nothing and reads as a region that
    exists — which is how the row comes back: the next hand to add a header
    finds a ready-made band waiting for it. `.mark` was that row's logo tile
    and had no other user.
    """
    assert not re.search(r"^\.p-head\b", PANEL_CSS, re.M), "the deleted band still has rules"
    assert not re.search(r"^\.mark\s*\{", PANEL_CSS, re.M), "the deleted logo tile still has rules"
    # The link's own line — the placement the measurement bought, and the one
    # part of it that lives in CSS rather than in DOM order: an `auto` left
    # margin on a fit-content block is what right-aligns it, and without it the
    # link would sit inline under the job title's first letter.
    block = re.search(r"\.identity \.linkish\s*\{([^}]+)\}", PANEL_CSS)
    assert block, "the identity link has no rule of its own"
    assert "display: block" in block.group(1)
    assert "0 auto" in block.group(1)


def test_the_rail_renders_five_stages_and_marks_the_one_you_are_on(booted):
    rows = _by_class(booted["opened"]["rail"], "stg")
    # The ROW line, not the whole `<li>`: since Task 7 the active row also
    # carries a stage body, and reading the subtree whole would make this
    # assertion about the Job preview's labels as well.
    assert [_text(_by_class(row, "stg-row")[0]) for row in rows] == [
        "1 Job", "2 Score", "3 Resume", "4 Fill", "5 Track"]
    assert [row["class"] for row in rows] == [
        "stg active", "stg locked", "stg locked", "stg locked", "stg locked"]
    # Five steps in order, so the rail is a LIST — the position and the count
    # are then announced without the render loop having to say them.
    assert booted["opened"]["rail"]["tag"] == "OL"
    assert {row["tag"] for row in rows} == {"LI"}
    # Announced as a step, not merely coloured: the rail is the whole of "where
    # am I", and a screen reader gets none of the border.
    assert [row["attrs"].get("aria-current") for row in rows] == [
        "step", None, None, None, None]
    # …and the tick, the numeral and the greying carry their state in words.
    assert [_by_class(row, "stg-num")[0]["attrs"].get("aria-label") for row in rows] == [
        "current step", "not yet", "not yet", "not yet", "not yet"]


def test_the_footer_carries_one_primary_and_it_refuses_an_empty_page(booted):
    """The primary is REAL from Task 7 — this fixture reaches neither the
    backend nor the page, so the panel has nothing to save and says so.

    Sending it anyway is the failure this pins: an empty `raw_text` spends an
    LLM extraction on nothing and leaves a nameless row in the library, and the
    user's evidence that it happened would be a job called "None"."""
    [cta] = _by_class(booted["opened"]["foot"], "cta")
    assert cta["text"] == "Add job"          # STAGE_LABELS["job"]
    # No application, so no status control: a Draft/Applied pair with nothing
    # to be draft ABOUT is a control naming a thing that does not exist.
    assert _by_class(booted["opened"]["foot"], "status-seg") == []
    assert NOTHING_TO_SAVE in _text(booted["clicked"]["foot"])
    assert booted["sentAfterClick"] == booted["sentBeforeClick"]


def test_the_note_is_a_live_region_that_renders_survive(booted):
    """The one slot the panel has for saying what happened, and every CTA's
    only feedback — so it is announced. That only works if the NODE outlives
    the change: a live region created fresh on each render is a new region
    every time, and a new region announces nothing.
    """
    # The attribute is pinned in the MARKUP, which is the point rather than a
    # shortcut: it belongs to a node the render loop never creates, so a driver
    # assertion here would be reading it off the fake document that mirrors
    # panel.html — the fake asserting itself.
    assert 'id="note" class="note" aria-live="polite"' in PANEL_HTML
    before = _by_class(booted["opened"]["foot"], "note")
    after = _by_class(booted["clicked"]["foot"], "note")
    # Same node, rewritten — not a replacement wearing the same class.
    assert before[0]["uid"] == after[0]["uid"]
    assert NOTHING_TO_SAVE in after[0]["text"]
    # Ordinary news, not an alarm: the error styling belongs to a real failure,
    # and "there is no posting on this page" is a fact about the page rather
    # than something that went wrong.
    assert after[0]["class"] == "note"


def test_what_the_panel_said_about_a_page_does_not_follow_you_off_it(booted):
    """`resetPageFacts` from the outside. The render loop's full rebuild
    protects the DOM, not the store — a sentence about the page you just left,
    re-rendered faithfully, is still a sentence about the wrong page."""
    assert NOTHING_TO_SAVE in _text(booted["clicked"]["foot"])
    assert NOTHING_TO_SAVE not in _text(booted["leftThePage"]["foot"])


@pytest.fixture(scope="module")
def booted_without_settings(tmp_path_factory):
    """The SW answers `{ok: false}` to everything — the backend is down, or
    storage was not readable. The panel still opens; it just knows less.

    `tabUrls` is what makes the tab switch land on a real page: the panel
    re-binds and asks about it, which is where the unreachable sentence comes
    from now that the settings ask does not write one (see `readSettings`).
    Without it the switched phase is a tab with no url, where the panel
    deliberately asks nothing at all.
    """
    return run_node(_PANEL_BOOT_DRIVER_JS, {
        "tabs": [{"id": 7, "url": POSTING_URL}],
        "switchTo": 7, "otherTab": 7, "otherUrl": OTHER_URL,
        "tabUrls": {"7": POSTING_URL},
        "navigatedUrl": POSTING_URL, "replies": {},
    }, tmp_path_factory.mktemp("panel_no_settings"), source=PANEL_SOURCE)


def test_a_panel_that_does_not_know_where_the_web_app_is_shows_no_link(booted_without_settings):
    """A link that resolves to nothing is the failure this project keeps
    naming, and guessing `localhost:3000` when the user has moved the app is
    the same failure with a wrong answer instead of a missing one."""
    identity = booted_without_settings["opened"]["identity"]
    assert _by_class(identity, "linkish") == []
    # …and the header is still a header: the tab's host, which is what the panel
    # honestly knows about this page and the proof of which tab it is bound to.
    # This used to read "Maestro CS is still in the header", i.e. the panel
    # identifies ITSELF — the brand row's claim, deleted with the brand row.
    assert "job-boards.greenhouse.io" in _text(identity)
    # And the footer says what is actually wrong, in the words of a question the
    # user asked: this fixture fails the MATCH too, so `applyMatch` writes its
    # page note. The missing link is not narrated on its own — nothing the user
    # can act on follows from "we could not read the settings", and the raw
    # message that used to land here was addressed to whoever wrote panel.js.
    [note] = _by_class(booted_without_settings["opened"]["foot"], "note")
    assert note["text"].startswith("Maestro CS is not reachable")
    # In the slot's OTHER voice: a failure the user can act on must not read
    # like the inert-button chatter that shares the slot.
    assert note["class"] == "note error"


def test_a_settings_ask_that_answers_nothing_boots_the_panel_on_defaults(tmp_path):
    """THE POSTURE, and it is a reversal: this case used to print the ask's
    exception into the footer.

    A mid-update mixed-version window is how it was found live — the panel had
    reloaded and the service worker had not, so `read_settings` answered
    nothing and the footer read "no answer to read_settings" in red. That
    string is `ask`'s own words for a reply it cannot parse; it is addressed to
    whoever wrote this file, and it took the panel's ONE line about what the
    user just did.

    So: defaults and a `console.warn`, which is `readStore`'s posture for the
    same kind of failure. The settings ask buys a link and a remembered fill
    mode, and both already have a rule for not having it. The backend answers
    perfectly here, which is what separates this from the fixture above — no
    page note is produced, so an empty slot is the whole claim.
    """
    out = _load(tmp_path, replies={}, api={
        "lightningai": _reply({"match": "none", "job": None, "application": None}),
        "/api/base-resumes": _reply(BASE_RESUMES),
    })
    [note] = _by_class(out["regions"]["foot"], "note")
    assert note["text"] == ""
    assert note["class"] == "note"
    # The panel is USABLE, which is what "boots on defaults" has to mean: the
    # page loaded, the rail is live, and the fill mode narrowed to the assist
    # pass rather than to nothing.
    assert _by_class(out["regions"]["identity"], "chip")[0]["text"] == "New"
    assert _rows(_rail_rows(out))["job"]["state"] == "active"
    # No appUrl, so no link — the one thing the failed ask actually costs, and
    # it is already an absence rather than a sentence.
    assert _by_class(out["regions"]["identity"], "linkish") == []


def test_a_backend_that_is_down_says_so_again_on_every_page_it_is_asked_about(booted_without_settings):
    """A note is about the page and dies with it — so a standing failure has to
    be re-made on the next page, and `applyMatch` is what re-makes it. A user
    who saw "not reachable" once and never again, on a panel that is still
    broken, would be left with an empty footer and no idea why nothing works.

    THE FAULT SLOT IS NOT WHAT DOES THIS ANY MORE, which is why the fixture had
    to grow a url for the tab it switches to: the settings ask no longer writes
    one, and the sentence the user sees comes from the question they asked
    about the page in front of them.
    """
    for phase in ("opened", "switched", "leftThePage"):
        assert "not reachable" in _text(booted_without_settings[phase]["foot"]), phase


def test_a_panel_that_could_not_bind_to_a_tab_says_so_and_keeps_saying_it(tmp_path):
    """The fault slot's one remaining tenant, pinned so the slot does not
    quietly become dead code.

    `bindActiveTab` is what binds this panel to a tab at all, and its query can
    reject (no focused window, a profile shutting down). Nothing else narrates
    that: there is no page, so there is no page note, and the user is left
    looking at a rail nothing will ever move. It survives `resetPageFacts` for
    the same reason — it is about this panel, not about any page.
    """
    out = _load(tmp_path, tabsThrow=True)
    [note] = _by_class(out["regions"]["foot"], "note")
    assert note["text"] == "no window is focused"
    assert note["class"] == "note error"


_RAIL_MODEL_DRIVER_JS = _PANEL_FAKES_JS + r"""
const ns = loadModules();
const { stageFor } = ns.decisions;
const { railModel } = ns.panel;
main(async () => {
  await settle();
  const out = {};
  // Real decisions, not hand-written ones: the rail's job is to render what
  // `stageFor` actually returns for a card, so the table starts at the card.
  for (const [name, card] of Object.entries(spec.cards)) {
    const decision = stageFor(card);
    // The DECISION travels beside the rows, because the tick's whole claim is
    // "this is `done`, rendered" — and a test that re-stated which stages are
    // done would be asserting its own copy of `stageFor`.
    out[name] = { rows: railModel(decision), done: decision.done,
                  // The provenance travels beside the rows for `done`'s reason:
                  // the row's `skipChoice` claim is "this is `choiceSkipped`,
                  // rendered", and a test restating which skips were chosen
                  // would be grading the rail against its own second opinion.
                  choiceSkipped: decision.choiceSkipped,
                  stage: decision.stage };
  }
  emit(out);
});
"""


@pytest.fixture(scope="module")
def rail(tmp_path_factory):
    cards = {
        "fresh_posting": {"match": "none", "hasApplication": False, "pdfReady": False,
                          "status": None, "touched": False, "hasForm": False,
                          "baseArmed": False, "hasScores": False, "baseSelected": False},
        "scored_and_picked": {"match": "exact", "hasApplication": False, "pdfReady": False,
                              "status": None, "touched": False, "hasForm": False,
                              "baseArmed": False, "hasScores": True, "baseSelected": True},
        "base_shortcut": {"match": "exact", "hasApplication": False, "pdfReady": False,
                          "status": None, "touched": False, "hasForm": True,
                          "baseArmed": True, "hasScores": False, "baseSelected": False},
        "base_shortcut_unmatched": {"match": None, "hasApplication": False, "pdfReady": False,
                                    "status": None, "touched": False, "hasForm": True,
                                    "baseArmed": True, "hasScores": False, "baseSelected": False},
        "applied": {"match": "exact", "hasApplication": True, "pdfReady": True,
                    "status": "applied", "touched": True, "hasForm": True,
                    "baseArmed": False, "hasScores": True, "baseSelected": True},
        # THE DISCRIMINATOR for the tick, and the reason it is a card rather
        # than an assertion: everything is finished EXCEPT the applied press,
        # so Track is the active row with `done.track` false. Without it "the
        # tick comes from done" and "Track is always ticked" are the same test.
        "filled_not_applied": {"match": "exact", "hasApplication": True,
                               "pdfReady": True, "status": "draft",
                               "touched": True, "hasForm": True,
                               "baseArmed": False, "hasScores": True,
                               "baseSelected": True},
    }
    return run_node(_RAIL_MODEL_DRIVER_JS, {"cards": cards},
                    tmp_path_factory.mktemp("panel_rail"), source=PANEL_SOURCE)




def _model(rail, name):
    return rail[name]["rows"]


def _every_row(rail):
    return [row for out in rail.values() for row in out["rows"]]


def _states(rail):
    return {row["state"] for row in _every_row(rail)}


def _plain_labels(rail):
    """Every row's state-to-label pairing EXCEPT the one row that is two states
    at once. That row's label is asserted on its own below, because folding it
    into this map would make the map a two-answer table and hide which of the
    four plain labels had gone missing."""
    return {row["state"]: row["stateLabel"] for row in _every_row(rail)
            if not (row["state"] == "active" and row["ticked"])}


def test_every_stage_is_on_the_rail_whatever_the_card_says(rail):
    for name, out in rail.items():
        rows = out["rows"]
        assert [row["key"] for row in rows] == [
            "job", "score", "resume", "fill", "track"], name
        assert [row["n"] for row in rows] == [1, 2, 3, 4, 5], name


def test_the_rail_marks_exactly_one_stage_active(rail):
    for name, out in rail.items():
        active = [row["key"] for row in out["rows"] if row["state"] == "active"]
        assert len(active) == 1, f"{name}: {active}"
    assert _rows(_model(rail, "fresh_posting"))["job"]["state"] == "active"
    assert _rows(_model(rail, "scored_and_picked"))["resume"]["state"] == "active"


def test_where_you_are_outranks_what_is_behind_you(rail):
    # `applied` has done.track true AND stage "track". A row that reported
    # "done" there would leave the panel with no active stage at all — the
    # terminal state is where the user IS, not merely a thing they finished.
    rows = _rows(_model(rail, "applied"))
    assert rows["track"]["state"] == "active"
    assert rows["job"]["state"] == "done"
    assert rows["fill"]["state"] == "done"
    # AND IT IS STILL TRUE with the tick on it. The precedence did not move —
    # `ticked` is a second answer to a second question, so the terminal row is
    # allowed to be both without either fact being taken away from it.
    assert rows["track"]["ticked"] is True


def test_skipped_is_rendered_as_skipped_and_never_as_done(rail):
    """`done` and `skipped` are two different claims and the rail may not blur
    them: "not required on the path you took" is not "we did it"."""
    rows = _rows(_model(rail, "base_shortcut"))
    assert rows["fill"]["state"] == "active"
    assert rows["score"]["state"] == "skipped"
    assert rows["resume"]["state"] == "skipped"
    assert rows["score"]["summary"] == "Skipped — using base as-is"
    # A done row carries no invented summary; the stage bodies (Tasks 7-9) are
    # what will fill those in from real data.
    assert rows["job"]["state"] == "done"
    assert rows["job"]["summary"] == ""
    # The escape hatch: no library entry at all, so Job is SKIPPED — greyed and
    # still re-askable — rather than ticked or locked out.
    # The skipped row's TICK is not asserted here: it is covered for every card
    # and every stage by `test_the_tick_is_read_from_done_for_every_stage_on_
    # every_card`, and a second copy would be this test's subject drifting from
    # "skipped is not done" to "and here is everything else about the row".
    hatch = _rows(_model(rail, "base_shortcut_unmatched"))
    assert hatch["job"]["state"] == "skipped"
    assert hatch["fill"]["state"] == "active"


def test_the_rail_carries_which_skip_was_a_choice_and_never_invents_one(rail):
    """`skipChoice` is `stageFor`'s `choiceSkipped`, rendered — the fact
    `isReopenable` turns into a door on a row that carries no tick.

    CARRIED, NOT RECOMPUTED, which is what this pins: the provenance is the
    decision's answer and the rail has no business having a second opinion
    about it. And it is false on every row that is not skipped, because the
    question is about a skip — a done or active row has not been skipped by
    anybody, least of all on purpose.
    """
    for name, out in rail.items():
        for row in out["rows"]:
            expected = (row["state"] == "skipped"
                        and row["key"] in out["choiceSkipped"])
            assert row["skipChoice"] is expected, f"{name}/{row['key']}"
    short = _rows(_model(rail, "base_shortcut"))
    assert short["resume"]["skipChoice"] is True
    assert short["score"]["skipChoice"] is False
    hatch = _rows(_model(rail, "base_shortcut_unmatched"))
    assert hatch["job"]["skipChoice"] is False
    assert hatch["resume"]["skipChoice"] is True


def test_the_tick_is_read_from_done_for_every_stage_on_every_card(rail):
    """THE RULE, over the whole table rather than over the row it was written
    for. The tick used to be read off `state`, where `active` had already won,
    so the ONE row that is both never got one: an application marked applied sat
    on a blue "5" and the whole journey looked unfinished at the end of it.

    Asserted against `stageFor`'s own `done` map — the rail's claim is "this is
    `done`, rendered", and a test carrying its own list of which stages are
    finished would be grading the rail against a second opinion.
    """
    for name, out in rail.items():
        for row in out["rows"]:
            assert row["ticked"] == (out["done"][row["key"]] is True), \
                f"{name}/{row['key']}: ticked {row['ticked']}, done {out['done']}"


def test_the_finished_rail_ticks_every_row_including_the_one_you_are_on(rail):
    """The end of the journey: five ticks and nothing left asking."""
    applied = _model(rail, "applied")
    assert [row["ticked"] for row in applied] == [True] * 5
    assert [row["key"] for row in applied if row["state"] == "active"] == ["track"]


def test_a_track_row_reached_but_not_applied_carries_its_numeral(rail):
    """The discriminator, and what stops the fix from being "always tick Track".
    A filled application that has not been marked applied is ON the Track step
    with work still to do there, so the row shows its number."""
    rows = _rows(_model(rail, "filled_not_applied"))
    assert rows["track"]["state"] == "active"
    assert rows["track"]["ticked"] is False
    assert rows["track"]["stateLabel"] == "current step"
    # …and the four behind it are ticked, so the difference really is the last
    # row rather than a card that finished nothing.
    assert [rows[key]["ticked"] for key in ("job", "score", "resume", "fill")] == [True] * 4


def test_no_stage_but_track_can_be_active_and_done_at_once(rail):
    """WHY THIS IS A GENERAL RULE AND NOT A TRACK SPECIAL CASE, pinned rather
    than argued: every other rung of `stageFor`'s ladder is guarded by the
    negation of its own done-ness (`!jobDone ? "job"`, `!scoreDone ? "score"`,
    and so on, plus `fillFromBase`'s `fillDone ? "track" : "fill"`), so reading
    the tick from `done` cannot change any row but the terminal one. If a future
    stage becomes reachable while done, it ticks — which is the answer this rule
    already gives rather than one someone has to remember to add.
    """
    both = {(name, out["stage"]) for name, out in rail.items()
            if out["done"][out["stage"]] is True}
    assert {stage for _, stage in both} <= {"track"}, both


def test_every_rail_state_says_itself_in_words(rail):
    # The tick, the border and the opacity are the whole of the visual answer,
    # and none of them reaches a screen reader.
    assert _states(rail) == {"active", "done", "skipped", "locked"}
    assert _plain_labels(rail) == {
        "active": "current step", "done": "done",
        "skipped": "skipped", "locked": "not yet",
    }
    # BOTH WORDS on the one row that is both, because a reader told only
    # "current step" hears an unfinished last step and a reader told only
    # "done" is not told where they are.
    assert _rows(_model(rail, "applied"))["track"]["stateLabel"] == "current step, done"


_WRITE_DOOR_DRIVER_JS = _PANEL_FAKES_JS + r"""
const ns = loadModules();
main(async () => {
  await settle();
  // The FACTORY is what is published, so `card` stays private either way: this
  // gets the same handle the actions roster hands each concern file at load.
  const store = ns.panel.actionStore();
  let refused = null;
  try { store.write({ nope: 1 }); } catch (err) { refused = String(err.message); }
  store.write({ note: { text: "a real field" } });
  emit({ refused, note: store.read().note, leaked: "nope" in store.read() });
});
"""


def test_the_write_door_refuses_a_key_the_store_does_not_have(tmp_path):
    """THE ONE ENFORCED PROPERTY of the actions seam, pinned.

    The cut's whole claim is that `card` never leaves panel.js and that one
    named function is the only way anything changes it. `write` refusing an
    unknown key is what turns that from an arrangement into a guard: without
    it, a typo in any `panel/actions/*.js` concern file becomes a field of the store that
    `resetPageFacts` never clears, `cardFacts` never reads and no render ever
    paints — a write that looks like it worked, on the surface whose whole
    design rule is that nothing may look live and not be.

    Nothing else reaches it. Every action goes through this door, so deleting
    the refusal leaves the entire suite green — measured — which is exactly the
    shape a safety property has to be pinned against directly.
    """
    out = run_node(_WRITE_DOOR_DRIVER_JS, {"tabs": []}, tmp_path, source=PANEL_SOURCE)
    # Named, because "a write failed" without the key is a bug report nobody
    # can act on.
    assert out["refused"] == 'panel store has no field "nope"'
    assert out["leaked"] is False
    # …and the door still opens for a field the store has, which is what makes
    # the refusal a guard rather than a wall.
    assert out["note"] == {"text": "a real field"}


_RESET_DRIVER_JS = _PANEL_FAKES_JS + r"""
const ns = loadModules();
main(async () => {
  await settle();
  const store = { ...spec.store };
  ns.panel.resetPageFacts(store);
  emit(store);
});
"""


def test_a_page_change_clears_every_fact_that_was_about_the_page(tmp_path):
    """The list itself, handed to a test whole.

    Everything below is a claim about ONE posting: the backend's verdict on the
    url, the job it matched, the application, its PDF, whether we filled here,
    whether the page even has a form, the base picked for it, its scores. From
    Task 6 a failed round trip leaves all of them untouched, and a faithful
    re-render of the previous job's title, chip and rings is a confident lie
    about the page in front of the user rather than a blank one.
    """
    populated = {
        "match": "exact", "job": {"id": "j1", "title": "ML Engineer"},
        "application": {"id": "a1", "status": "draft"}, "pdfReady": True,
        # The Track stage's evidence, which is the sharpest thing on this list:
        # a PDF filename and an applied date carried to the next tab would be
        # one employer's receipt shown under another employer's posting.
        "evidence": {"pdfName": "tailored.pdf", "appliedOn": "2026-08-18"},
        "touched": True, "hasForm": True, "baseSlug": "ai_ml_engineer",
        # The attach's two, and both are about ONE document: how many upload
        # boxes that page reported, and what this panel put in one of them. The
        # first would offer an attach on a page with no box; the second would
        # show one employer's filename under another employer's posting, which
        # is `evidence`'s failure by a second route.
        "fileInputs": 2, "attached": {"filename": "tailored.pdf", "count": 1},
        "baseSelected": True, "baseArmed": True, "scores": [{"composite": 72}],
        "busy": "tailor", "note": {"text": "Tailored — 84"},
        # A disclosure rather than a claim, and still the page's: the fork the
        # user opened on one posting must not be open on the next.
        "tailorOpen": True,
        # The other disclosure, and the one whose survival would be loudest: a
        # reopened done row holds a BODY open, so a `revisit` carried across the
        # tab would show the previous posting's Fill report under a rail that
        # has just reset to Job.
        "revisit": {"row": "fill", "over": "track"},
        # The most page-shaped fact there is: it was READ OFF the page.
        "preview": {"title": "ML Engineer", "company": "Lightning AI",
                    "location": "Remote", "text": "a whole JD", "source": "json-ld"},
        # And the flag that protects it from the posting re-ask. Carried across
        # a tab it is the SPA bug turned over: `landPosting` refuses every
        # extraction while it stands, so the next page would be stuck at three
        # empty boxes over a full JD because someone typed on the LAST one.
        "previewTyped": True,
        # The one injection this page was allowed. Carried across, the next tab
        # would be treated as already prepared and the orphaned-scripts rung
        # would be spent on a page the user has left.
        "prepared": True,
        # Everything the Fill stage learned, and every word of it is about ONE
        # page — carried to the next tab it would report a Workday form's
        # residue over a Greenhouse posting.
        "fill": {"counts": {"filled": 12}}, "writeResults": [{"qid": "q1"}],
        # A half-typed pause-row answer. A qid is a per-frame token the collect
        # stamped into THAT page's DOM, so a draft that outlived its page
        # addresses a control nothing can find.
        "answers": {"q2": {"text": "6 weeks", "learn": True}},
        "residue": [{"qid": "q2", "label": "Preferred shift"}],
        "essays": [{"qid": "q3", "label": "Why this role?"}],
        "eeoConsent": {"enabled": True, "consent_forms": False},
        # The QnA drawer, both halves. The question was asked about this posting
        # and the answer is grounded in this application, so a drawer that
        # survived the tab would offer a paragraph about a job the user has left
        # — ready to be copied into a different employer's form.
        "qna": {"open": True, "question": "Why us?", "answered": "Why us?",
                "answer": "Because…", "copied": True},
        # Not about the posting, and so not cleared: where the app is, which
        # tab we are bound to, the resume library — and `fillMode`, which is a
        # standing choice about HOW to fill rather than a fact about what was.
        "settings": {"appUrl": APP_URL}, "tabId": 7, "url": POSTING_URL,
        "resumes": [{"slug": "ai_ml_engineer"}], "fillMode": "rules",
        "fault": {"text": "the backend is unreachable", "error": True},
        # Tab-independent, like `resumes`: the recent-drafts list is not a fact
        # about a posting, and re-fetching it on every tab switch is the
        # always-on cost the picker loader exists to refuse.
        "applications": [{"id": "app-1", "status": "draft"}],
        # A pick's provenance: it is a fact about THIS page's binding, so a
        # claimed arming carried to the next tab would open a Job door on a
        # posting the user never claimed.
        "claimed": True,
    }
    out = run_node(_RESET_DRIVER_JS, {"store": populated}, tmp_path,
                   source=PANEL_SOURCE)
    assert out == {
        "match": None, "job": None, "application": None, "pdfReady": False,
        "claimed": False,
        "evidence": None, "touched": False, "hasForm": False,
        "fileInputs": 0, "attached": None, "baseSlug": None,
        "baseSelected": False, "baseArmed": False, "scores": None,
        "busy": None, "note": None, "preview": None, "previewTyped": False,
        "prepared": False, "tailorOpen": False,
        "revisit": None,
        "fill": None, "writeResults": None, "residue": None, "essays": None,
        "eeoConsent": None, "answers": {},
        "qna": {"open": False, "question": "", "answered": None, "answer": None,
                "copied": False},
        "settings": {"appUrl": APP_URL}, "tabId": 7, "url": POSTING_URL,
        "resumes": [{"slug": "ai_ml_engineer"}], "fillMode": "rules",
        "fault": {"text": "the backend is unreachable", "error": True},
        "applications": [{"id": "app-1", "status": "draft"}],
    }


# ---------- what the panel loads, and for which tab ----------
#
# Task 6 gave the panel four round trips (the match, the remembered session,
# the scores, the application detail) and one page read (`detect_page`). Every
# one of them lands into ONE store, asynchronously, while the user is free to
# change tabs — so the tests below are about two things: what each answer is
# allowed to write, and whose answer is allowed to write at all.

_APPLY_MATCH_DRIVER_JS = _PANEL_FAKES_JS + r"""
const ns = loadModules();
main(async () => {
  await settle();
  const out = {};
  for (const [name, c] of Object.entries(spec.cases)) {
    // Every case starts from a POPULATED store — the previous posting's facts,
    // which is the state the SPA bug was found in.
    const store = { ...spec.populated, settings: c.settings ?? null };
    out[name] = { returned: ns.panel.applyMatch(c.result, store), store };
  }
  emit(out);
});
"""

STALE = {
    "match": "exact",
    "job": {"id": "old-job", "company": "Cohere", "title": "Member of Technical Staff"},
    "application": {"id": "old-app", "status": "draft"},
    "pdfReady": True,
    # Leftover from a pick on the previous posting. The backend's answer is
    # not a user claim; applyMatch must not leave this standing.
    "claimed": True,
}


@pytest.fixture(scope="module")
def applied_match(tmp_path_factory):
    cases = {
        "exact": {"result": {
            "match": "exact",
            # Extra keys on purpose: the projection is what keeps the store's
            # shape the panel's own rather than the endpoint's.
            "job": {"id": "j9", "company": "Lightning AI", "title": "Research Engineer",
                    "description": "a whole posting nobody asked for"},
            "application": {"id": "a9", "status": "draft"}}},
        "none": {"result": {"match": "none", "job": None, "application": None}},
        "exact_no_application": {"result": {
            "match": "exact", "job": {"id": "j9", "company": "Lightning AI",
                                      "title": "Research Engineer"}}},
        "error": {"result": {"error": "Failed to fetch"},
                  "settings": {"backendUrl": "http://localhost:8001"}},
        "error_before_settings": {"result": {"error": "Failed to fetch"}},
    }
    return run_node(_APPLY_MATCH_DRIVER_JS, {"cases": cases, "populated": STALE},
                    tmp_path_factory.mktemp("panel_match"), source=PANEL_SOURCE)


def test_a_match_writes_the_panels_own_shape_and_not_the_endpoints(applied_match):
    store = applied_match["exact"]["store"]
    assert store["match"] == "exact"
    # Three keys, projected — never the row the endpoint happened to return.
    assert store["job"] == {"id": "j9", "company": "Lightning AI", "title": "Research Engineer"}
    assert store["application"] == {"id": "a9", "status": "draft"}
    # The backend named this page. That is not a claim the user made, so the
    # Job row gets no un-pick door. A leftover `claimed` from the previous
    # posting would open one on a match the user cannot withdraw.
    assert store["claimed"] is False
    # A match with no application in it CLEARS the one that was there: the
    # backend's answer is the whole answer, not a patch over the last one.
    assert applied_match["exact_no_application"]["store"]["application"] is None
    assert applied_match["exact_no_application"]["store"]["claimed"] is False
    assert applied_match["none"]["store"] == {**STALE, "match": "none", "job": None,
                                             "application": None, "claimed": False,
                                             "settings": None}


def test_an_unreachable_backend_clears_every_fact_it_could_no_longer_vouch_for(applied_match):
    """The SPA-stale-match bug, ported with its fix.

    On a route change the ask can fail while the PREVIOUS posting's match is
    still in the store, and a panel that left it there would offer to autofill
    the application belonging to the job the user just navigated away from.
    All four go, `pdfReady` included — it is a claim about the application that
    is no longer there.
    """
    store = applied_match["error"]["store"]
    assert store["match"] is None
    assert store["job"] is None
    assert store["application"] is None
    assert store["pdfReady"] is False


def test_the_unreachable_line_names_the_configured_url_and_is_never_login_shaped(applied_match):
    """SYSTEM.md §11.4: one line, naming the configured URL. There is no account
    to log in to, so a sentence that reads like a sign-in prompt would send the
    user looking for a password that does not exist."""
    note = applied_match["error"]["store"]["note"]
    assert note["text"] == (
        "Maestro CS is not reachable at http://localhost:8001: Failed to fetch")
    assert note["error"] is True
    for forbidden in ("sign in", "log in", "login", "password", "account"):
        assert forbidden not in note["text"].lower()
    # Before the settings ask has answered we do not know where the backend is,
    # so the sentence says less rather than guessing a default.
    assert applied_match["error_before_settings"]["store"]["note"]["text"] == (
        "Maestro CS is not reachable: Failed to fetch")
    # A note, not a fault: this is the answer to "what is this page?", asked
    # about ONE url, so it dies with the page. `fault` is the other lifetime —
    # the panel's own plumbing — and applyMatch never touches it.
    assert applied_match["error"]["store"].get("fault") is None










def test_a_loaded_page_renders_as_itself_from_end_to_end(tmp_path):
    """The whole load, through the real render driver: the match names the job,
    the library supplies the default base, `latest_scores` supplies both rings,
    and the application detail supplies the status the rings sit under."""
    out = _load(tmp_path, api={
        "lightningai": _reply({"match": "exact", "job": LIGHTNING_JOB,
                               "application": {"id": "app-1", "status": "draft"}}),
        "/api/base-resumes": _reply(BASE_RESUMES),
        "/api/ats-scores": _reply(SCORES),
        "/api/applications/app-1": _reply({"pdf_path": "renders/app-1.pdf",
                                           "status": "draft"}),
    }, replies={"read_settings": SETTINGS_REPLY,
                "panel_frame0": _reply({"tier": "A", "form": True, "score": 3})})
    identity = out["regions"]["identity"]
    assert _by_class(identity, "title")[0]["text"] == "Research Engineer"
    assert _by_class(identity, "co")[0]["text"] == "Lightning AI"
    # The application outranks the library chip: the most specific truth wins.
    assert _by_class(identity, "chip")[0]["text"] == "Application · draft"
    # Before → After, both READ from latest_scores rows. The base is the best
    # ranked one rather than the first in the library.
    assert [ring["text"] for ring in _by_class(identity, "ring")] == ["72", "84"]
    assert _by_class(identity, "delta")[0]["text"] == "+12"
    # …and the header link now has something more specific than the job. It
    # lives in the identity block since the brand row's deletion — LAST, on a
    # line of its own.
    [link] = _by_class(out["regions"]["identity"], "linkish")
    assert link["href"] == f"{APP_URL}/applications/app-1"
    assert link["text"] == "Open application ↗"
    # The visible label is short; the accessible name is not allowed to be, and
    # this is the state where it does the work. Beside a job title and a
    # company, "Open application" alone reads as the POSTING'S apply page —
    # the one destination this link never has.
    assert link["attrs"]["aria-label"] == "Open this application in Maestro CS"
    # ITS OWN LINE, and this is the assertion that keeps it off `row1`. Beside
    # the chip was the first home and a measured mistake: `.who` and a nowrap
    # link share one axis there, so at 400px — a NORMAL side-panel width — the
    # job title was cut to 104px and wrapped five times to buy the link its
    # 129. Last child of the block, alone, competing with nothing.
    assert identity["children"][-1]["class"] == "linkish"
    [row1] = _by_class(identity, "row1")
    assert [kid["class"] for kid in row1["children"]] == ["who", "chip app"]
    # Every endpoint is the widget's, unchanged — a panel that invented a route
    # would 404 in the browser and pass here.
    paths = [msg["path"] for msg in out["sent"] if msg["type"] == "api"]
    assert paths[0] == (
        "/api/jobs/match?url=https%3A%2F%2Fjob-boards.greenhouse.io%2Flightningai%2Fjobs%2F99")
    assert set(paths[1:]) == {"/api/base-resumes", "/api/ats-scores?job_id=job-lightning",
                              "/api/applications/app-1"}


def test_a_tab_that_is_not_a_web_page_costs_no_round_trip(tmp_path):
    """The panel is open across the whole browser and the user tabs through
    settings pages, the new-tab page and PDF viewers constantly. Asking the
    backend about a `chrome://` url is a request per glance for an answer that
    can only be "no" — the same always-on cost `loadHasForm` refuses to pay.

    It still resets and repaints: keeping the previous posting's title while
    the user looks at their settings is the confident lie, and a blank honest
    panel is the alternative.
    """
    out = _load(tmp_path, tabs=[{"id": 7, "url": "chrome://settings"}], api={
        "lightningai": _reply({"match": "exact", "job": LIGHTNING_JOB,
                               "application": None})})
    assert [msg for msg in out["sent"] if msg["type"] == "api"] == []
    assert [msg for msg in out["sent"] if msg["type"] == "panel_frame0"] == []
    # Rendered, not dead: five rail rows and nothing claimed about the page.
    assert len(_by_class(out["regions"]["rail"], "stg")) == 5
    assert _by_class(out["regions"]["identity"], "chip") == []
    assert _text(out["regions"]["foot"]).strip() == "Add job"


def test_a_load_that_fails_leaves_a_rendered_panel_rather_than_a_dead_one(tmp_path):
    """Every load degrades to honesty. The match failing is the only one the
    user hears about; the rest cost a ranking or a detail, and a panel that
    stopped rendering because a score read failed would be a blank surface with
    no way back."""
    out = _load(tmp_path, api={})       # nothing answers
    [note] = _by_class(out["regions"]["foot"], "note")
    assert "not reachable" in note["text"]
    assert note["class"] == "note error"
    # Still a whole panel: five rail rows, an identity line, a primary.
    assert len(_by_class(out["regions"]["rail"], "stg")) == 5
    assert "job-boards.greenhouse.io" in _text(out["regions"]["identity"])
    assert _by_class(out["regions"]["foot"], "cta")[0]["text"] == "Add job"


# ---------- the tab binding, with real loads in flight ----------

_PANEL_RACE_DRIVER_JS = _PANEL_FAKES_JS + r"""
loadModules();
main(async () => {
  // Tab A's match is on the wire and HELD: the panel is mid-load.
  await settle();
  const midLoad = regions();
  // The user switches tabs. Tab B answers immediately and paints.
  await onActivated({ tabId: spec.switchTo });
  await settle();
  const onTabB = regions();
  // …and only now does tab A's answer come back.
  release();
  await settle();
  const afterTheLateReply = regions();
  // THEN a repaint the user causes, and this is not decoration: a late write
  // that lands after the last render is invisible in the DOM until something
  // renders again. The store is what was corrupted; the next click is when the
  // user finds out. Any control does — what this one DOES is beside the point,
  // and on a tab with nothing read from it Add job only refuses out loud.
  withClass(REGIONS.foot, "cta")[0].click();
  await settle();
  emit({ midLoad, onTabB, afterTheLateReply, afterARepaint: regions(), sent });
});
"""


@pytest.fixture(scope="module")
def raced(tmp_path_factory):
    return run_node(_PANEL_RACE_DRIVER_JS, {
        "tabs": [{"id": 7, "url": POSTING_URL}],
        "switchTo": 42,
        "tabUrls": {"42": APPLY_URL},
        "hold": ["lightningai"],
        "replies": {"read_settings": SETTINGS_REPLY},
        "api": {
            "lightningai": _reply({"match": "exact", "job": LIGHTNING_JOB,
                                   "application": {"id": "app-lightning",
                                                   "status": "draft"}}),
            "myworkdayjobs": _reply({"match": "exact", "job": ACME_JOB,
                                     "application": None}),
            "/api/base-resumes": _reply(BASE_RESUMES),
            "/api/ats-scores": _reply(SCORES),
        },
    }, tmp_path_factory.mktemp("panel_race"), source=PANEL_SOURCE)


def test_a_late_answer_for_the_tab_you_left_never_paints_the_tab_you_are_on(raced):
    """THE test of this change, and the concrete form of "the binding is the
    guard".

    `fanoutTab` verifies WHO may name a tab, never WHICH — a service worker
    cannot know which tab the user is looking at. So everything about aiming
    this panel at the right tab is the panel's own, and a round trip is where
    that gets hard: the user switches tabs while tab A's match is still on the
    wire, and there is exactly ONE store for it to land in. Without a
    generation token, tab A's job title, chip, rings and application id
    overwrite tab B's — and the panel then offers a fill and a PDF attach for a
    job the user is not looking at, which the SW would pass.
    """
    # Mid-load: nothing but the tab's own host, which is the honest picture.
    assert "job-boards.greenhouse.io" in _text(raced["midLoad"]["identity"])
    assert "Lightning AI" not in _text(raced["midLoad"]["identity"])
    # Tab B loaded fully while A hung.
    assert _by_class(raced["onTabB"]["identity"], "title")[0]["text"] == "Data Scientist"
    assert _by_class(raced["onTabB"]["identity"], "co")[0]["text"] == "Acme"
    # THE ASSERTION: A's answer arrives late and is discarded, not painted.
    late = raced["afterTheLateReply"]
    assert _by_class(late["identity"], "title")[0]["text"] == "Data Scientist"
    assert _by_class(late["identity"], "co")[0]["text"] == "Acme"
    assert "Lightning AI" not in _text(late["identity"])
    assert "Research Engineer" not in _text(late["identity"])
    # …including the parts of A's answer that are not the title: the chip and
    # the header link are where a stale application id would aim a real action.
    assert "app-lightning" not in json.dumps(late)


@pytest.fixture(scope="module")
def raced_scores(tmp_path_factory):
    """The same race, one loader deeper: tab A's MATCH lands, and its scores
    read is what is still on the wire when the user switches."""
    return run_node(_PANEL_RACE_DRIVER_JS, {
        "tabs": [{"id": 7, "url": POSTING_URL}],
        "switchTo": 42,
        "tabUrls": {"42": APPLY_URL},
        "hold": ["/api/ats-scores?job_id=job-lightning"],
        "replies": {"read_settings": SETTINGS_REPLY},
        "api": {
            "lightningai": _reply({"match": "exact", "job": LIGHTNING_JOB,
                                   "application": None}),
            # Tab B's job is not in the library, so tab B has NO scores of its
            # own — every number it could show would be tab A's.
            "myworkdayjobs": _reply({"match": "none", "job": None,
                                     "application": None}),
            "/api/base-resumes": _reply(BASE_RESUMES),
            "/api/ats-scores?job_id=job-lightning": _reply(SCORES),
        },
    }, tmp_path_factory.mktemp("panel_race_scores"), source=PANEL_SOURCE)


def test_a_late_score_read_never_becomes_the_next_tabs_number(raced_scores):
    """The guard hole a settle-time write leaves, and why every loader lands in
    a local first.

    `card.scores = await api(…)` assigns the moment the promise settles, which
    is BEFORE any generation check can run. The rows do not even look wrong:
    `compositeFor` keys a base row on the resume SLUG, which is job-independent,
    so tab A's rows resolve happily against tab B's default base and render as
    tab B's "Before" number. Worse than a wrong number, `cardFacts` reads the
    same array for `hasScores`, so a stage tab B never reached reports itself
    complete.

    Asserted AFTER a repaint, which is the only way to see it: the bad write
    lands when nothing is rendering, so the DOM stays innocent until the user's
    next click — at which point tab A's number appears on tab B with nothing
    on screen to explain it.
    """
    late = raced_scores["afterARepaint"]
    # The empty ring — "not scored yet", which is not a low score and is
    # certainly not another posting's score.
    assert [ring["text"] for ring in _by_class(late["identity"], "ring")] == ["–"]
    assert _by_class(late["identity"], "ring")[0]["class"] == "ring empty"
    # …and the rail did not move: tab B's job is not in the library, so it is
    # still at Job, whatever tab A's scores would have implied about Score.
    rows = _rows(_rail_rows({"regions": late}))
    assert rows["job"]["state"] == "active"
    assert rows["score"]["state"] == "locked"


# ---------- the remembered pick, read from the store the widget writes ----------
#
# The shape itself is `tests/extension_fixtures.py`'s — imported at the top of
# this file, alongside the origin and tenant it is scoped to. It became a module
# at Task 13 so two files could read the SAME object rather than each carrying a
# copy that could drift while both stayed green. One file reads it today; the
# module stays because the reason was never the count.


_SESSION_API = {
    "/api/base-resumes": _reply(BASE_RESUMES),
    "/api/ats-scores": _reply(SCORES),
    "/api/applications/app-remembered": _reply({"pdf_path": "renders/r.pdf",
                                                "status": "draft"}),
}


def _restored(out):
    """The application id the panel is armed with, read off the header link —
    which is also the one place a wrong one would send the user. `None` when
    the link is the plain "Open in Maestro CS" one, i.e. nothing was armed."""
    for link in _by_class(out["regions"]["identity"], "linkish"):
        before, sep, app_id = link["href"].partition(f"{APP_URL}/applications/")
        if sep and not before:
            return app_id
    return None


def test_a_pick_made_on_this_tenant_comes_back_after_the_page_reloads(tmp_path):
    """An ATS wizard is six page loads; without this the pick made on step 1 is
    gone by step 2. The panel outlives those loads, but the STORE is where the
    pick lives — the widget writes it, and both surfaces read the same key."""
    out = _load(tmp_path, api={"lightningai": _reply(
        {"match": "none", "job": None, "application": None}), **_SESSION_API},
        stored={"widget.session": entry()})
    assert _restored(out) == "app-remembered"
    assert _by_class(out["regions"]["identity"], "chip")[0]["text"] == "Application · draft"
    # What the page itself could not say: which job this is. The entry carries
    # it, so the identity line stops being a hostname.
    assert _by_class(out["regions"]["identity"], "title")[0]["text"] == "Research Engineer"
    # The forced "exact": the user chose this target by hand, and a rail that
    # read `match: "none"` would put Add job over the top of it.
    assert _rows(_rail_rows(out))["job"]["state"] == "done"
    # THE PICK ITSELF, which is the half of "remembered" that is easy to lose.
    # 68 is `ai_ml_engineer`, the slug in the entry. 72 is `data_scientist` —
    # both the library's first row AND the better-scoring one, so it is what
    # appears if the default assignment overwrites the restored slug, if the
    # ranking moves off it, or if the restore never marked it as the user's
    # choice. Three guards, one number.
    assert _by_class(out["regions"]["identity"], "ring")[0]["text"] == "68"
    # …and the pdf the entry claimed, confirmed by the re-read, is what puts
    # the rail past Resume.
    assert _rows(_rail_rows(out))["fill"]["state"] == "active"


def test_a_failed_application_read_never_claims_the_pdf_is_rendered(tmp_path):
    """The entry says the PDF was rendered; the entry is a cache. When the
    re-read cannot confirm it, unknown reads as NOT-ready — the panel offers to
    tailor again, which costs a click, where the other way round offers a Fill
    whose attachment does not exist."""
    out = _load(tmp_path, api={
        "lightningai": _reply({"match": "none", "job": None, "application": None}),
        "/api/base-resumes": _reply(BASE_RESUMES),
        "/api/ats-scores": _reply(SCORES),
        # …and `/api/applications/app-remembered` deliberately absent.
    }, stored={"widget.session": entry()})
    rows = _rows(_rail_rows(out))
    assert rows["resume"]["state"] == "active"
    assert rows["fill"]["state"] == "locked"


def test_a_page_this_extension_already_filled_is_remembered_as_filled(tmp_path):
    """`touched` is the one bit that outlives the page, and it is what puts the
    "mark as applied" nudge in reach: the user filled step 3 of a wizard, and
    the panel must not treat step 4 as a form it has never seen."""
    out = _load(tmp_path, api={"lightningai": _reply(
        {"match": "none", "job": None, "application": None}), **_SESSION_API},
        stored={"widget.session": entry(touched=True)})
    rows = _rows(_rail_rows(out))
    assert rows["fill"]["state"] == "done"
    assert rows["track"]["state"] == "active"


def test_a_pick_made_on_another_company_is_refused_on_this_one(tmp_path):
    """job-boards.greenhouse.io serves thousands of companies from ONE origin.
    A Cohere pick restored onto a Lightning posting is the 2026-08-16 live bleed
    — same origin, different company, "Application ready" about an application
    that belongs to another job."""
    out = _load(tmp_path, api={"lightningai": _reply(
        {"match": "none", "job": None, "application": None}), **_SESSION_API},
        stored={"widget.session": entry(tenant=COHERE_TENANT)})
    assert _restored(out) is None
    # And the panel says what the backend said instead: a new posting.
    assert _by_class(out["regions"]["identity"], "chip")[0]["text"] == "New"


def test_a_tab_with_no_url_restores_nothing_and_does_not_die_trying(tmp_path):
    """`sessionTenant` is total because the panel asks it about whatever a TAB
    holds — and a tab that has not committed a url holds nothing. Both guards
    refuse here (there is no origin either), and neither is load-bearing alone;
    what this pins is that the panel reaches the refusal instead of throwing on
    `new URL("")` before it gets there."""
    out = _load(tmp_path, tabs=[{"id": 7, "url": ""}],
                api=_SESSION_API, stored={"widget.session": entry()})
    assert _restored(out) is None
    # A whole panel, rendered: the failure mode this guards against is a load
    # that throws and leaves the surface half-painted.
    assert len(_by_class(out["regions"]["rail"], "stg")) == 5


def test_the_backend_always_wins_over_the_memory(tmp_path):
    """The memory is a cache of a CHOICE, not a claim about a job. When the
    backend recognises this page and names an application on it, that is the
    application — the remembered one is not consulted at all."""
    out = _load(tmp_path, api={
        "lightningai": _reply({"match": "exact", "job": LIGHTNING_JOB,
                               "application": {"id": "app-from-backend",
                                               "status": "applied"}}),
        "/api/applications/app-from-backend": _reply({"pdf_path": "r.pdf",
                                                      "status": "applied"}),
        **_SESSION_API,
    }, stored={"widget.session": entry()})
    assert _restored(out) == "app-from-backend"
    # The status is the ROW's, re-read after the match — the memory would have
    # said "draft" here.
    assert _by_class(out["regions"]["identity"], "chip")[0]["text"] == "Application · applied"


# ---------- does the page in front of the user hold a form? ----------




def test_the_panel_asks_the_page_whether_it_has_a_form_and_never_injects_to_do_it(tmp_path):
    """The panel cannot run detection itself — it is in no page — so it asks
    frame 0 for `detectPage()`'s verdict.

    WITHOUT `panel_prepare`. Preparing injects the content scripts into every
    frame of the tab, and doing that on every tab switch is the always-on cost
    the detection gate exists to avoid. Scripts are already in every page loaded
    since the extension started, which is the ordinary case; injection stays
    reserved for an explicit user action.
    """
    out = _load(tmp_path, api={"lightningai": _reply(
        {"match": "none", "job": None, "application": None}), **_SESSION_API},
        stored={"widget.session": _armed_entry()},
        replies={"read_settings": SETTINGS_REPLY,
                 "panel_frame0": _reply({"tier": "B", "form": True, "score": 2})})
    [asked] = [msg for msg in out["sent"] if msg["type"] == "panel_frame0"]
    assert asked["message"] == {"type": "detect_page"}
    assert asked["tabId"] == 7                     # the bound tab, named
    assert [msg for msg in out["sent"] if msg["type"] == "panel_prepare"] == []
    # The verdict is used: a form plus an armed base is the shortcut, and the
    # rail is where that shows.
    rows = _rows(_rail_rows(out))
    assert rows["fill"]["state"] == "active"
    assert rows["score"]["state"] == "skipped"


def test_a_tab_the_scripts_never_reached_reports_no_form_rather_than_a_failure(tmp_path):
    """A tab whose scripts answer nothing reads as `hasForm: false` in the
    moment, which is the honest rendering of "we do not know whether this page
    has a form". It is not a note: the panel's one sentence is for what the user
    just did, and our own reach into a tab is not something they can act on.

    WHAT THIS USED TO ALSO ASSERT — that no injection is ever made from a load —
    is deliberately reversed, and the reversal is the fix for the orphaned-
    scripts bug. Here the injection is fired ONCE, because a silence is the one
    failure on this path the panel can do something about; `panel_prepare` is
    unanswered in this fixture, so it changes nothing else about what is
    painted. What survives unchanged is the QUIET: a page we could not read is
    never reported to the user as a fault.

    ONE INJECTION, TWO ASKERS. It used to come from the posting path alone,
    which this armed page no longer reaches — the claim puts it at Fill — so
    `askDetectPrepared` is what spends it here. The count is the assertion that
    keeps them from spending one each.
    """
    out = _load(tmp_path, api={"lightningai": _reply(
        {"match": "none", "job": None, "application": None}), **_SESSION_API},
        stored={"widget.session": _armed_entry()},
        replies={"read_settings": SETTINGS_REPLY})   # panel_frame0 fails
    # ONE, and aimed at the bound tab. More than one would be a load that
    # re-injects per ask, which is the always-on cost this path refuses.
    assert [msg["tabId"] for msg in out["sent"]
            if msg["type"] == "panel_prepare"] == [7]
    # ON THE FIRST ASK, not one second into the retry schedule. Both ladders go
    # through the prepared ask, so a cure that only the retries carried would
    # still arrive — a whole rung later, with the panel meanwhile telling the
    # user this page has no form on it. The sequence is the claim: ask, put the
    # scripts there, ask again, and only then start the schedule.
    # An injection carries no inner message, so its own type is the fallback —
    # which is what puts both kinds of ask on one readable line.
    frame0 = [msg.get("message", {}).get("type", "panel_prepare")
              for msg in out["sent"]
              if msg["type"] in ("panel_frame0", "panel_prepare")]
    assert frame0[:3] == ["detect_page", "panel_prepare", "detect_page"]
    # A SILENCE READS ALL THE WAY THROUGH as "no form here": the claim puts the
    # user at Fill, and the body says the page cannot answer it rather than
    # offering a pass that would find nothing.
    rows = _rows(_rail_rows(out))
    assert rows["fill"]["state"] == "active"
    assert _by_class(out["regions"]["foot"], "cta") == []
    [note] = _by_class(out["regions"]["foot"], "note")
    assert "detect" not in note["text"]
    assert "no reply from the page" not in note["text"]


# ---------- local storage: one key read, four swept -------------------------
#
# THE DOCUMENTED SET. `widget.session` is the only key this panel reads, and
# `ORPHAN_KEYS` is every key the extension has ever written to
# `chrome.storage.local` and no longer does — Task 8's second session key, plus
# the three the floating card left in every user's profile when R-C deleted it.
# The entry shape is `tests/extension_fixtures.py`'s, imported rather than
# restated.


def test_the_panel_reads_one_key_and_ignores_the_one_it_retired(tmp_path):
    """The collapse back to one session key, tested where it could still bite.

    Task 8's `panel.pick` may still hold an entry in a profile that ran a panel
    built between then and now. Nothing reads it — one key cannot shadow
    itself, which is the whole reason the recency tie-break that split needed
    was never written.

    The entry planted here is FRESHER and names a different base than the one
    on the shared key, so a panel that still read it would show `ai_ml_engineer`
    at 72 rather than the shared entry's `data_scientist` at 64. That number is
    the assertion: it fails on a READ of the retired key, which a sweep
    assertion alone would not catch.
    """
    out = _load(tmp_path, tabs=[{"id": 7, "url": LIGHTNING_APPLY_URL}], stored={
        "widget.session": {**PICKED_ENTRY, "at": int(time.time() * 1000),
                           "baseSlug": "data_scientist"},
        "panel.pick": {**PICKED_ENTRY, "at": int(time.time() * 1000) + 60_000,
                       "baseSlug": "ai_ml_engineer"},
    }, api={"lightningai": _reply({"match": "none", "job": None, "application": None}),
            "/api/base-resumes": _reply(SCORE_RESUMES),
            "/api/ats-scores": _reply(SCORE_ROWS)})
    # 64 is `data_scientist`; 72 is what the retired key — and, equally, the
    # ranking — would have shown.
    assert _by_class(out["regions"]["identity"], "ring")[0]["text"] == "64"


def test_the_boot_sweeps_every_orphan_key_it_finds(tmp_path):
    """R-C's storage pass, and the gap it closes.

    THE SWEEP USED TO RIDE `restoreSession`, which `loadContext` only reaches
    when the backend did NOT name an application for the page — so a user whose
    pages always match an application never ran it and kept their orphans
    forever. It runs at BOOT now, before anything can decide not to.

    All four keys in one planting, because the three `widget.*` ones are what
    the floating card left behind and they are exactly the rows a user who
    never re-picks would otherwise carry for good.

    THE BACKEND NAMES AN APPLICATION HERE, and that is the whole point of the
    fixture rather than incidental colour: `loadContext` calls `restoreSession`
    only `if (!card.application)`, so on THIS page the old rider-sweep never
    ran at all. Give the match a null application and the test passes whether
    the sweep is at boot or back on the rider — measured, not assumed.
    """
    out = _load(tmp_path, tabs=[{"id": 7, "url": LIGHTNING_APPLY_URL}], stored={
        "widget.session": {**PICKED_ENTRY, "at": int(time.time() * 1000)},
        "panel.pick": {"origin": "https://job-boards.greenhouse.io"},
        "widget.dock": {"side": "right", "offset": 120},
        "widget.hiddenOrigins": {"https://acme.example": True},
        "widget.hiddenGlobally": True,
    }, api={"lightningai": _reply({"match": "exact", "job": LIGHTNING_JOB,
                                   "application": {"id": "app-1",
                                                   "status": "draft"}}),
            "GET /api/applications/app-1": _reply(
                {"id": "app-1", "pdf_path": "r.pdf", "status": "draft"}),
            "/api/base-resumes": _reply(SCORE_RESUMES),
            "/api/ats-scores": _reply(SCORE_ROWS)})
    # A REMOVE, not a `set(key, null)`. The second leaves the key present
    # holding null, which is a row that survives every future sweep because it
    # is no longer `undefined`.
    assert out["removals"] == [[
        "panel.pick", "widget.dock", "widget.hiddenOrigins",
        "widget.hiddenGlobally",
    ]], out["removals"]
    # …and the live key is NOT among them.
    for removed in out["removals"]:
        assert "widget.session" not in removed


def test_a_profile_with_no_orphans_is_not_written_to(tmp_path):
    """The second boot, and every boot after it. The sweep reads a fixed key
    list and removes only what it found, so a clean profile costs one read and
    no write at all — which is what makes running it on every panel open
    acceptable rather than housekeeping the user pays for repeatedly.
    """
    out = _load(tmp_path, tabs=[{"id": 7, "url": LIGHTNING_APPLY_URL}], stored={
        "widget.session": {**PICKED_ENTRY, "at": int(time.time() * 1000)},
    }, api={"lightningai": _reply({"match": "exact", "job": LIGHTNING_JOB,
                                   "application": None}),
            "/api/base-resumes": _reply(SCORE_RESUMES),
            "/api/ats-scores": _reply(SCORE_ROWS)})
    assert out["removals"] == []


# ---------- the reopened done row: a view over the rail, never a stage -------
#
# The rail's other half, and the one thing on this surface that a CLICK decides.
# `stageFor` still owns which row is ACTIVE; what a press owns is which row's
# body is on screen — normally the active one's, and otherwise a done
# Score/Resume/Fill row the user reopened (`card.revisit`). Everything below is
# about keeping those two apart: the view may follow the click, the rail may not.
#
# DRIVEN, not sliced. Every test here presses real controls in the real render
# loop, because the interesting failures are all interactions between a press
# and a repaint — a body that opens under the wrong row, a tick that a reopen
# quietly rewinds, a focus that the rebuild eats, a `revisit` that outlives the
# facts it was opened over. None of them is visible in a function's return.


def _revisit_api():
    """A page with everything behind it: a matched job, a draft application with
    a rendered PDF, the library and its scores. Nothing is picked yet, so the
    journey opens at Score and ONE press (a base row) completes three steps at
    once — which is what puts done rows on the rail to reopen."""
    return {
        "lightningai": _reply({"match": "exact", "job": LIGHTNING_JOB,
                               "application": {"id": "app-1", "status": "draft"}}),
        "/api/base-resumes": _reply(BASE_RESUMES),
        "/api/ats-scores": _reply(SCORES),
        # A LIST: the first read is the load's, the second is the status PATCH's
        # answer, and they must differ or "the rail moved on" is unaskable.
        "/api/applications/app-1": [
            _reply({"pdf_path": "renders/app-1.pdf", "status": "draft"}),
            _reply({"pdf_path": "renders/app-1.pdf", "status": "applied"}),
        ],
    }


_REVISIT_DRIVER_JS = _PANEL_FAKES_JS + r"""
loadModules();
const opener = (key) => findById(REGIONS.rail, `stg-open-${key}`);
const press = (key) => {
  const button = opener(key);
  if (!button) throw new Error(`no reopen control on the ${key} row`);
  // FOCUSED, then pressed. That is what a browser does on a click and what a
  // keyboard does on Enter — the control the user acts through is the control
  // they are IN — and it is the only way the focus restore is askable at all:
  // this fake moves focus for `focus()` and for nothing else.
  button.focus();
  button.click();
  // The node as it was BEFORE the press, which is the only way to tell a
  // restore that found the rebuilt control from one that never let go of the
  // old one — they read identically by id.
  return button;
};
main(async () => {
  await settle();
  const atScore = regions();
  // The user picks a base. The ordinary way the Score step completes, and it
  // completes Resume with it — the application already has its PDF.
  withClass(REGIONS.rail, "baserow")[0].click();
  await settle();
  const atFill = regions();
  // …and goes back to Score. The rail is scrolled, because a done row is
  // halfway down a list that scrolls and the press rebuilds all of it.
  REGIONS.rail.scrollTop = 137;
  const pressed = press("score");
  await settle();
  const scoreOpen = regions();
  const kept = {
    scrollTop: REGIONS.rail.scrollTop,
    focusedId: document.activeElement ? document.activeElement.id : null,
    // What the restore ASKED FOR. A browser scrolls a scrollable ancestor to
    // reveal a control it judges out of view, which would throw away the
    // scrollTop restored a statement earlier — this fake has no layout and so
    // records the request rather than guessing when it would fire.
    focusOptions: document.activeElement ? document.activeElement.focusOptions : null,
    // The node the user pressed is GONE — every element is replaced — so focus
    // has to have landed on the REBUILT control. Both halves are needed: the id
    // alone cannot tell a restore that found the new node from one that never
    // let go of the old one.
    focusedIsFresh: document.activeElement === opener("score")
      && document.activeElement.uid !== pressed.uid,
  };
  press("score");
  await settle();
  const scoreClosed = regions();
  press("resume");
  await settle();
  const resumeOpen = regions();
  press("score");
  await settle();
  const swapped = regions();
  // AN ACTION STARTED FROM THE REOPENED ROW, with its round trip HELD open —
  // which is the only moment in which "every door is shut" can be observed.
  // TWO doors exist here (Score reopened, Resume done beside it), and that is
  // the point: a guard written as "the open one" leaves the other live.
  withClass(REGIONS.foot, "cta")[0].click();
  const duringRun = regions();
  release();
  await settle();
  const afterRun = regions();
  // NOTHING FOCUSED, which is the other half of the rule: a render must give
  // focus back and must never take it. The clicks below move nothing, because
  // this fake focuses on `focus()` alone.
  ACTIVE = null;
  opener("score").click();
  await settle();
  const unfocused = document.activeElement;
  emit({ atScore, atFill, scoreOpen, scoreClosed, resumeOpen, swapped, kept,
         duringRun, afterRun,
         unfocusedAfterRender: unfocused === null, writes, sent });
});
"""


@pytest.fixture(scope="module")
def revisited(tmp_path_factory):
    return run_node(_REVISIT_DRIVER_JS, {
        "tabs": [{"id": 7, "url": POSTING_URL}],
        "replies": {"read_settings": SETTINGS_REPLY,
                    "panel_frame0": _reply({"tier": "A", "form": True, "score": 3})},
        "api": _revisit_api(),
        # The re-score's POST only, so the load's GET of the same path still
        # lands: "while an action is open" is a state the driver has to be able
        # to stand in, and a held reply is the only way to stand in it.
        "hold": ["POST /api/ats-scores"],
    }, tmp_path_factory.mktemp("panel_revisit"), source=PANEL_SOURCE)


def _openers(regions_):
    """Every reopen control on the rail, by the stage it belongs to."""
    return {node["id"].removeprefix("stg-open-"): node
            for node in _walk(regions_["rail"])
            if str(node["id"] or "").startswith("stg-open-")}


def _open_body(regions_):
    """Which row's body is on screen — the id `renderRail` stamps on it — and
    a raise if there are two, because "exactly one" is the claim."""
    bodies = [node for node in _by_class(regions_["rail"], "stg-body")]
    assert len(bodies) <= 1, [node["id"] for node in bodies]
    return bodies[0]["id"].removeprefix("stg-body-") if bodies else None


def test_the_journey_reaches_a_rail_with_done_rows_on_it(revisited):
    """The fixture's own premise, pinned before anything is asked of it.

    One press on a base row completes Score AND Resume — the application's PDF
    was already rendered — so the rail this section reopens rows on is real
    rather than arranged: three done rows, one active, and the body under the
    active one.
    """
    assert _rows(_rail_rows({"regions": revisited["atScore"]}))["score"]["state"] == "active"
    rows = _rows(_rail_rows({"regions": revisited["atFill"]}))
    assert [rows[key]["state"] for key in ("job", "score", "resume", "fill", "track")] == [
        "done", "done", "done", "active", "locked"]
    assert _open_body(revisited["atFill"]) == "fill"


def test_a_done_row_is_a_door_and_only_for_the_three_stages_that_have_one(revisited):
    """Score, Resume, Fill — and never Job, on a backend match.

    This fixture's Job row is done because the backend named the posting, not
    because the user claimed a draft. A claimed binding is a different door
    (pinned in test_extension_panel_job.py); a backend exact-match is the page
    being that posting, and the web app is where a wrong JD gets fixed. Track
    is absent for a duller reason — it is never done while you are standing on
    it, so the control could not render even if it existed.
    """
    at_fill = _openers(revisited["atFill"])
    assert sorted(at_fill) == ["resume", "score"]
    # …and the row that is DONE but not reopenable carries no control at all,
    # rather than a disabled one: a door that is drawn and refuses is worse
    # than a wall.
    assert "job" not in at_fill
    job_row = _by_class(revisited["atFill"]["rail"], "stg")[0]
    assert [node["tag"] for node in _walk(job_row) if node["tag"] == "BUTTON"] == []
    # Fill is the third, and it appears the moment Fill is done rather than
    # being special: here it is the ACTIVE row, which is its own body already.
    assert "fill" not in at_fill


def test_reopening_shows_that_stages_body_without_moving_the_rail(revisited):
    """THE WHOLE FEATURE, and the whole of what it may not do.

    The body under the reopened row is that stage's own — the Score body's
    ranked list, not a summary of it — and the rail is untouched: Fill is still
    the active row, still `aria-current`, still bordered. The step the user is
    ON is a fact about their application; the body they are LOOKING AT is not,
    and a rail that moved its active mark to follow the view would be reporting
    the second as the first.
    """
    opened = revisited["scoreOpen"]
    assert _open_body(opened) == "score"
    # The real body, from the real roster: the ranked library with a row per
    # base resume.
    assert len(_by_class(opened["rail"], "baserow")) == len(BASE_RESUMES)
    rows = _rows(_rail_rows({"regions": opened}))
    assert rows["fill"]["state"] == "active"
    assert rows["score"]["state"] == "done"
    rail_rows = _by_class(opened["rail"], "stg")
    assert [row["attrs"].get("aria-current") for row in rail_rows] == [
        None, None, None, "step", None]
    # …and the tick did not move either. Reopening is not rewinding: nothing
    # about the application changed because the user looked at a step again.
    assert [_by_class(row, "stg-num")[0]["text"] for row in rail_rows] == [
        "✓", "✓", "✓", "4", "5"]


def test_pressing_an_open_header_again_closes_it(revisited):
    """A disclosure, so it discloses both ways. Without this the only way back
    to the inferred view is a page change, which is the panel deciding when the
    user is finished looking."""
    assert _open_body(revisited["scoreClosed"]) == "fill"
    assert _openers(revisited["scoreClosed"])["score"]["attrs"]["aria-expanded"] == "false"


def test_exactly_one_body_is_open_at_a_time(revisited):
    """Opening Resume closes Score; opening Score closes Resume. Two bodies on a
    400px rail is a surface where the footer's single primary sits under one of
    them and belongs to the other — `_open_body` asserts the count for every
    phase this file reads."""
    assert _open_body(revisited["resumeOpen"]) == "resume"
    assert _open_body(revisited["swapped"]) == "score"
    # The one that lost the press says so, rather than being left expanded with
    # nothing under it.
    assert _openers(revisited["swapped"])["resume"]["attrs"]["aria-expanded"] == "false"
    assert _openers(revisited["swapped"])["score"]["attrs"]["aria-expanded"] == "true"


def test_the_reopen_control_is_a_real_button_that_names_what_it_opened(revisited):
    """Keyboard-reachable, and announced.

    A click handler on the row would be a control no keyboard can reach and no
    screen reader can describe — the rail is the whole of "where am I", and a
    step the user can go back to is part of that. `aria-controls` names the
    region ONLY while it exists (the Tailor fork's rule): an id nothing carries
    offers a jump that goes nowhere.
    """
    button = _openers(revisited["scoreOpen"])["score"]
    assert button["tag"] == "BUTTON"
    assert button["attrs"]["aria-expanded"] == "true"
    assert button["attrs"]["aria-controls"] == "stg-body-score"
    assert [node["id"] for node in _by_class(revisited["scoreOpen"]["rail"], "stg-body")] == [
        "stg-body-score"]
    # Closed: the state is the whole story, and the address is withheld because
    # there is nothing at it.
    closed = _openers(revisited["scoreClosed"])["score"]
    assert closed["attrs"]["aria-expanded"] == "false"
    assert "aria-controls" not in closed["attrs"]
    # The row still reads as the row: the numeral, its state in words, and the
    # name are inside the button rather than replaced by it.
    assert _text(button).startswith("✓ Score")
    assert _by_class(button, "stg-num")[0]["attrs"]["aria-label"] == "done"
    # And the state is VISIBLE too, because `aria-expanded` reaches nobody
    # looking at the screen: a done row that opens looks exactly like one that
    # does not until a mark says so, and "hover to find out" is not something a
    # keyboard can do. Hidden from the reader, which has the attribute — the
    # better version of the same sentence.
    assert _by_class(button, "stg-caret")[0]["text"] == "▾"
    assert _by_class(closed, "stg-caret")[0]["text"] == "▸"
    assert _by_class(button, "stg-caret")[0]["attrs"]["aria-hidden"] == "true"


def test_a_reopened_row_brings_its_primary_with_it(revisited):
    """THE FOOTER FOLLOWS THE OPEN ROW, and without it this feature is a door
    onto a wall.

    The design's promise is one primary at a time and always in the same place,
    so the Fill body a user reopens on page 3 of a wizard has to have its Start
    fill in the footer where every other stage's primary has always been. Keyed
    on the inferred stage instead, a reopened body would be a report with no way
    to act on it — and the alternative, a second Start fill inside the body, is
    the two-writers-for-one-behaviour that footer exists to prevent.
    """
    assert _by_class(revisited["atFill"]["foot"], "cta")[0]["text"] == "Start fill"
    assert _by_class(revisited["scoreOpen"]["foot"], "cta")[0]["text"] == "Score all bases"
    assert _by_class(revisited["resumeOpen"]["foot"], "cta")[0]["text"] == "Quick tailor"
    # Closing gives it back to the data — the two are the same answer whenever
    # nothing is reopened.
    assert _by_class(revisited["scoreClosed"]["foot"], "cta")[0]["text"] == "Start fill"
    # The status segment is NOT the primary and does not move with it: it
    # belongs to the application, which is the same application either way.
    assert len(_by_class(revisited["scoreOpen"]["foot"], "status-seg")) == 1


def test_the_rail_keeps_your_place_across_the_rebuild_your_press_caused(revisited):
    """THE RENDER-COST DEBT, paid where it said it would be.

    Every element is replaced on every render, so the press that opens a row
    destroys the button that was pressed: without the capture the user lands on
    `document.body`, scrolled back to the top, at the exact moment the body they
    asked for appears below. The restore travels as an ID because the node
    itself is what the rebuild throws away.
    """
    assert revisited["kept"]["scrollTop"] == 137
    # WHICH OF THESE TWO BITES, named because the answer is not the obvious one
    # and a tidy-up that dropped the wrong line would unguard the whole rider.
    # The id alone is INERT: the fake keeps `activeElement` pointing at the
    # detached node the rebuild discarded, and that node's `id` still reads
    # `stg-open-score`, so this line passes with the restore deleted. It stays
    # because it names WHICH control the user was in; the line under it is the
    # one that fails, because only a restore that went looking for the id can
    # land on the node the rebuild built.
    assert revisited["kept"]["focusedId"] == "stg-open-score"
    assert revisited["kept"]["focusedIsFresh"] is True
    # …and it asked NOT to scroll. Without that, focusing a control the browser
    # judges out of view scrolls the rail to reveal it and throws away the
    # position restored one statement earlier — the two halves of the fix would
    # fight, invisibly, and the assertion above would still pass.
    assert revisited["kept"]["focusOptions"] == {"preventScroll": True}
    # AND IT NEVER TAKES FOCUS. With nothing focused, a render leaves it that
    # way — a loop that pulled focus into the rail on every landing load would
    # fight the user for the address bar.
    assert revisited["unfocusedAfterRender"] is True


def test_the_door_looks_like_what_it_is_in_both_states_the_dom_cannot_show(revisited):
    """Two stylesheet claims the document cannot carry, and both are about a
    control that LOOKS wrong rather than behaves wrong.

    - DISABLED HAS TO LOOK DISABLED. This block sets `background`, `color` and
      `cursor: pointer` explicitly, and an author declaration beats the UA
      stylesheet's disabled defaults — so without the rule the door renders at
      full contrast under a pointer cursor while swallowing every click, which
      is the fourth time this file has had to say so.
    - FOCUS HAS TO BE VISIBLE. `.stg` is `overflow: hidden` with no padding, so
      a full-width button's border box coincides with the card's padding box and
      the global ring — drawn at `outline-offset: 2px` — falls wholly outside
      the clip. A keyboard user tabbing onto a done row would see NOTHING: a
      WCAG 2.4.7 failure on this feature's own headline control. The negative
      offset puts the same ring on the visible side of the same edge.

    Asserted against the stylesheet because the fake document has no layout and
    no cascade; a driver assertion here would be reading the fake.
    """
    assert "button.stg-row:disabled" in PANEL_CSS
    assert re.search(r"button\.stg-row:focus-visible\s*\{[^}]*outline-offset:\s*-2px",
                     PANEL_CSS), PANEL_CSS[-400:]
    # The control the rules are about is real, and is the one this fixture
    # presses — so the pair above cannot drift into styling nothing.
    assert _openers(revisited["atFill"])["score"]["class"] == "stg-row"


def test_the_rail_numeral_is_centered_without_a_clipped_line_box():
    """The numbered pills sat low and slightly clipped.

    `.stg-num` is a 22px circle. `display:grid; place-items:center` plus
    `font: 700 11px/1` is a known offender: line-height 1 sizes the inline
    box to the font-size, and some font stacks sit the glyph low in that
    box so it clips against `.stg { overflow: hidden }` and against the
    circle itself. Matching line-height to the box and flex-centering
    the glyph is the CSS reason, not a pixel nudge. The caret sits on the
    same `.stg-row` flex line (`align-items: center`), so the numeral
    and the ▸ stay on one axis.
    """
    block = re.search(r"\.stg-num\s*\{([^}]+)\}", PANEL_CSS)
    assert block, "the .stg-num rule moved"
    rule = block.group(1)
    assert "place-items" not in rule
    assert re.search(r"font:\s*[^;]*/1\b", rule) is None
    assert re.search(r"display:\s*flex", rule)
    assert re.search(r"align-items:\s*center", rule)
    assert re.search(r"justify-content:\s*center", rule)
    assert re.search(r"line-height:\s*22px", rule)
    # The row the caret shares, so a numeral that recenters in its circle
    # does not drift off the ▸ beside it.
    assert re.search(r"\.stg-row\s*\{[^}]*align-items:\s*center", PANEL_CSS)
    # And the pill is still what the rail paints — the CSS cannot drift
    # onto a class nothing uses.
    assert "stg-num" in PANEL_SOURCE


_TYPING_DRIVER_JS = _PANEL_FAKES_JS + r"""
loadModules();
main(async () => {
  // The drafts read is HELD, so the boot settles with the Job body on screen
  // and one load still in flight — which is the ordinary way a render arrives
  // while a user is typing. Nothing about it is the user's doing.
  await settle();
  const input = findById(REGIONS.rail, "preview-title");
  if (!input) throw new Error("the Job body has no preview title field");
  input.focus();
  input.value = "Staff Research Engineer";
  input.dispatch("input");
  const before = input.uid;
  release();
  await settle();
  const after = findById(REGIONS.rail, "preview-title");
  emit({
    settled: regions(),
    focusedId: document.activeElement ? document.activeElement.id : null,
    focusedIsFresh: document.activeElement === after
      && document.activeElement.uid !== before,
    focusOptions: document.activeElement ? document.activeElement.focusOptions : null,
    value: after ? after.value : null,
  });
});
"""


def test_a_load_landing_while_you_type_does_not_take_the_field_away(tmp_path):
    """THE OTHER HALF OF THE RIDER, and the half its own commit message claims:
    the restore is by id, so it serves every stable id on this surface, not just
    the rail openers this section presses.

    A body input is the case that matters most and the one no test reached. The
    render here is NOT a click — it is the recent-drafts read landing, one of
    four loads that arrive whenever they arrive — so the user is typing into a
    field that a repaint replaces underneath them. `card.preview` already kept
    the CHARACTERS (Task 7); what this pins is that the user is still IN the
    field afterwards, which is what makes the characters worth keeping.
    """
    out = run_node(_TYPING_DRIVER_JS, {
        "tabs": [{"id": 7, "url": POSTING_URL}],
        "replies": {"read_settings": SETTINGS_REPLY},
        "api": {"lightningai": _reply({"match": "none", "job": None,
                                       "application": None}),
                "/api/applications": _reply([{"id": "app-9", "status": "draft",
                                              "job_company": "Acme",
                                              "job_title": "Data Scientist"}])},
        "hold": ["GET /api/applications"],
    }, tmp_path, source=PANEL_SOURCE)
    # The load really did repaint — the picker it fetched is on screen — so this
    # is a rebuilt rail and not a render that never happened.
    assert "Acme" in _text(out["settled"]["rail"])
    assert out["focusedId"] == "preview-title"
    # The identity clause is the one that bites, for the reason the opener's
    # test spells out: the id survives on the discarded node.
    assert out["focusedIsFresh"] is True
    assert out["focusOptions"] == {"preventScroll": True}
    # And the characters came back with the caret, from the store rather than
    # from the element the repaint destroyed.
    assert out["value"] == "Staff Research Engineer"


def test_which_body_is_open_is_never_written_down(revisited):
    """`revisit` is view state, and the session entry is what the OTHER surface
    reads: a card restoring "the user was looking at Score" would be the panel
    telling the floating card where to point its attention."""
    assert revisited["writes"], "the pick should have written a session entry"
    assert "revisit" not in json.dumps(revisited["writes"])
    # AND NOT OVER THE WIRE EITHER, which is the same rule aimed at the other
    # destination. `sent` is every message this panel put on the SW's door,
    # request bodies included, so a view field folded into any POST — a score
    # run, a status PATCH, an ingest — shows up here. The non-empty guard is not
    # ceremony: an assertion that "revisit" is absent from nothing passes on a
    # driver that sent nothing at all.
    assert [msg for msg in revisited["sent"] if msg["type"] == "api"], (
        "the drive should have reached the backend at all")
    assert "revisit" not in json.dumps(revisited["sent"])


def test_nothing_can_be_started_from_a_door_while_an_action_is_open(revisited):
    """EVERY door, not the open one.

    The reopen is `statusSegment`'s rule applied to a new control: every control
    on this surface reads `busy`, because a round trip that some control does
    not know about is one the user can interrupt. The failure a narrower guard
    allows is specific — reopen Score at Fill, press Score-all, then press the
    RESUME door beside it — and what it does is swap the body out from under a
    running action, replacing the progress the user is waiting on with another
    stage's step while the action is still writing.

    So the claim is over the whole rail: with a run open, no door is pressable.
    Two of them exist in this fixture, which is what makes the "open one" answer
    and the "every one" answer different assertions.
    """
    doors = _openers(revisited["duringRun"])
    assert sorted(doors) == ["resume", "score"]
    assert {key: door["disabled"] for key, door in doors.items()} == {
        "score": True, "resume": True}
    # The footer's own primary greys with them — one action at a time is the
    # rule they are all reading.
    assert _by_class(revisited["duringRun"]["foot"], "cta")[0]["disabled"] is True
    # …and they come back when the round trip lands, rather than staying shut.
    assert {key: door["disabled"] for key, door in _openers(revisited["afterRun"]).items()} == {
        "score": False, "resume": False}
    # The run was the reopened row's, and the view it was started from survived
    # it: the report lands under the body the user opened.
    assert _open_body(revisited["afterRun"]) == "score"


# ---- and the two ways the data takes the view back ----
#
# Both are the same rule — the view may not outlive the facts it was opened over
# — and they are two tests because they are two different things going stale:
# the STAGE the row was opened beside, and the row's own doneness. Each is
# reached by changing a real fact through a real control, because a `revisit`
# cleared by a driver's own store write would pin the clearing and not the rule.


_MOVED_ON_DRIVER_JS = _PANEL_FAKES_JS + r"""
loadModules();
const opener = (key) => findById(REGIONS.rail, `stg-open-${key}`);
const statusButton = (label) => withClass(REGIONS.foot, "status-seg")
  .flatMap((segment) => segment.children)
  .filter((button) => button.textContent === label)[0];
main(async () => {
  await settle();
  withClass(REGIONS.rail, "baserow")[0].click();
  await settle();
  opener("resume").click();
  await settle();
  const reopened = regions();
  // The user marks the application applied — the ONE status write this panel
  // makes — and the journey's last step becomes the one they are on.
  statusButton("Applied").click();
  await settle();
  const movedOn = regions();
  // …and the user goes back to Resume, on the rail as it is NOW. This is the
  // press that tells "the stale view was dropped" from "the stale view was
  // merely ignored": a `revisit` still sitting in the store names this row, so
  // the toggle reads the press as a CLOSE and nothing opens.
  opener("resume").click();
  await settle();
  emit({ reopened, movedOn, reopenedAgain: regions() });
});
"""


@pytest.fixture(scope="module")
def moved_on(tmp_path_factory):
    return run_node(_MOVED_ON_DRIVER_JS, {
        "tabs": [{"id": 7, "url": POSTING_URL}],
        "replies": {"read_settings": SETTINGS_REPLY,
                    "panel_frame0": _reply({"tier": "A", "form": True, "score": 3})},
        "api": _revisit_api(),
    }, tmp_path_factory.mktemp("panel_revisit_moved"), source=PANEL_SOURCE)


def test_a_reopened_row_yields_when_the_rail_moves_on(moved_on):
    """DATA WINS, and this is the shape it wins in.

    The user reopened Resume while standing at Fill; marking the application
    applied moves the journey to Track. The reopened view is dropped rather than
    kept, because it was opened over a rail that no longer exists — a body left
    standing there is the panel showing a step the user chose two facts ago,
    with a footer primary belonging to neither the step nor the view.

    `over` is the whole of how that is noticed. The Resume row is STILL done and
    still reopenable; nothing about it changed. What changed is the stage beside
    it, and a `revisit` holding only a row key could not tell.
    """
    assert _open_body(moved_on["reopened"]) == "resume"
    assert _rows(_rail_rows({"regions": moved_on["reopened"]}))["fill"]["state"] == "active"
    # The rail moved, so the view went with it: Track is where the user is, and
    # the Track body is what is open.
    rows = _rows(_rail_rows({"regions": moved_on["movedOn"]}))
    assert rows["track"]["state"] == "active"
    assert _open_body(moved_on["movedOn"]) == "track"
    # The row that was open is closed and says so — not left expanded over
    # nothing.
    assert _openers(moved_on["movedOn"])["resume"]["attrs"]["aria-expanded"] == "false"
    # …and the footer's primary is the inferred stage's again. Track has none,
    # which is the state that would look most like a bug if the view had stuck:
    # a "Quick tailor" button under an applied application.
    assert _by_class(moved_on["movedOn"]["foot"], "cta") == []


def test_a_view_the_data_took_back_is_dropped_and_not_merely_ignored(moved_on):
    """The store has to AGREE with what was painted, and this is the press that
    proves it does.

    A `revisit` left in the store while the render ignores it is not a harmless
    leftover: the toggle reads the next press on that row as a CLOSE — the row
    it names is already "open" as far as the store is concerned — so the user
    presses the door and nothing happens, once, for no reason they can see. It
    is the second home for "which body is open" that the store's own header
    refuses, arrived at by omission.
    """
    assert _open_body(moved_on["movedOn"]) == "track"
    assert _open_body(moved_on["reopenedAgain"]) == "resume"
    assert _openers(moved_on["reopenedAgain"])["resume"]["attrs"]["aria-expanded"] == "true"
    # Opened over the rail as it is NOW — Track is still the active row, which
    # is what makes this a fresh view rather than the old one resurfacing.
    assert _rows(_rail_rows({"regions": moved_on["reopenedAgain"]}))["track"]["state"] == "active"


_UNDONE_DRIVER_JS = _PANEL_FAKES_JS + r"""
loadModules();
const opener = (key) => findById(REGIONS.rail, `stg-open-${key}`);
main(async () => {
  await settle();
  const armed = regions();
  opener("score").click();
  await settle();
  const reopened = regions();
  // Re-scored from the reopened body's own primary, and the scorer comes back
  // with nothing it can rank. `done.score` falls; the STAGE does not move,
  // because the base-resume shortcut pins it.
  withClass(REGIONS.foot, "cta")[0].click();
  await settle();
  emit({ armed, reopened, rescored: regions(),
         posts: sent.filter((msg) => (msg.init || {}).method === "POST") });
});
"""


@pytest.fixture(scope="module")
def undone(tmp_path_factory):
    """The base-resume shortcut, with a base picked before it: `fillFromBase`
    pins the stage to Fill whatever Score and Resume say, which is the one state
    where a done row can stop being done while the rail stands still."""
    return run_node(_UNDONE_DRIVER_JS, {
        "tabs": [{"id": 7, "url": POSTING_URL}],
        "stored": {"widget.session": _armed_entry()},
        "replies": {"read_settings": SETTINGS_REPLY,
                    "panel_frame0": _reply({"tier": "A", "form": True, "score": 3})},
        "api": {
            "lightningai": _reply({"match": "exact", "job": LIGHTNING_JOB,
                                   "application": None}),
            "/api/base-resumes": _reply(BASE_RESUMES),
            # Base rows only, so a re-score that ranks nothing empties the
            # array outright — `scoreAllBases` MERGES, and a tailored row left
            # in it would keep `hasScores` true for a reason this test is not
            # about.
            "/api/ats-scores": [_reply(SCORE_ROWS), _reply([])],
        },
    }, tmp_path_factory.mktemp("panel_revisit_undone"), source=PANEL_SOURCE)


def test_a_row_that_stops_being_done_takes_its_body_with_it(undone):
    """THE NARROW LIMB, and it is reachable rather than defensive.

    Under the shortcut the stage is pinned by `fillFromBase`, so `done.score`
    can fall — a re-score that ranks nothing — while the stage sits exactly
    where it was and `over` still matches. Without the doneness check the rail
    would then render the Score body under a row it has just re-drawn as
    SKIPPED, which is the un-skip feature arriving by accident rather than by
    decision.
    """
    armed = _rows(_rail_rows({"regions": undone["armed"]}))
    assert armed["fill"]["state"] == "active"
    assert armed["score"]["state"] == "done"
    assert _open_body(undone["reopened"]) == "score"
    rescored = _rows(_rail_rows({"regions": undone["rescored"]}))
    # The stage did not move — which is what makes this the doneness limb and
    # not the `over` one.
    assert rescored["fill"]["state"] == "active"
    assert rescored["score"]["state"] == "skipped"
    assert _open_body(undone["rescored"]) == "fill"
    assert "score" not in _openers(undone["rescored"])


def test_the_reopened_bodys_primary_is_the_one_that_actually_runs(undone):
    """The other half of the footer's move, and the half a label cannot show:
    pressing it sends the OPEN row's round trip. A footer that read "Score all
    bases" and ran the Fill stage's runner would pass every assertion about the
    text on it."""
    assert _by_class(undone["reopened"]["foot"], "cta")[0]["text"] == "Score all bases"
    assert [msg["path"] for msg in undone["posts"]] == ["/api/ats-scores"]
    assert json.loads(undone["posts"][0]["init"]["body"]) == {"job_id": "job-lightning"}

