"""The JOB stage: read the posting off the page, edit it, save it.

The posting preview belongs to the step the user is on; `previewFrom` and
`ingestBodyFrom` are driven as a table in both directions (the extraction
writes labelled header lines, the ingest writes them back, and the round trip
is the identity on an unedited posting); the characters survive a render
nobody asked for; and `addJob` is driven through its busy, failure, race and
success paths. When a page has a form but no job match, the Job body also
offers recent draft applications — one pick arms the rail and writes the
tenant-scoped session entry both surfaces read.

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

from tests.extension_fixtures import LIGHTNING_APPLY_URL, POSTING_URL, entry
from tests.extension_harness import run_node
from tests.extension_panel_harness import (
    APPLY_URL,
    APP_URL,
    BASE_RESUMES,
    LIGHTNING_JOB,
    PANEL_SOURCE,
    SCORES,
    SETTINGS_REPLY,
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


# ---------- the Job stage: read the posting, edit it, save it ----------
#
# The panel's first real action and its first stage body. Three separable
# things: what the page is READ into (`previewFrom`), what a save SENDS
# (`ingestBodyFrom`), and what the action does to the store while it is open.

# `extractJobPosting`'s own output shape for a described posting (agent.js:15):
# ONE text blob whose first lines are the labelled title, company and location.
# The panel's preview is those lines lifted back out, which is why the two
# functions are tested as a round trip rather than separately.
POSTING_TEXT = "\n".join([
    "Title: Machine Learning Engineer",
    "Company: Lightning AI",
    "Location: Remote, US",
    "",
    "We are hiring an ML engineer to work on distributed training.",
])
POSTING_REPLY = _reply({"url": POSTING_URL, "title": "ML Engineer | Lightning AI",
                        "text": POSTING_TEXT, "source": "json-ld"})
# The url a real board hands out: a click id, a campaign, a source. Every one of
# them survives to the backend — see the unstripped test for why.
TRACKED_URL = f"{POSTING_URL}?gh_src=4d2&utm_campaign=spring&utm_source=linkedin"
SAVED_JOB = {"id": "job-just-saved", "company": "Lightning AI, Inc.",
             "title": "Machine Learning Engineer",
             "extracted_json": {"skills": ["pytorch", "ray", "cuda"]}}


def _preview_inputs(region):
    """The three preview fields as `{key: value}`, read off what was rendered."""
    return {node["id"].removeprefix("preview-"): node["value"]
            for node in _walk(region) if node["tag"] == "INPUT"}


_JOB_STAGE_DRIVER_JS = _PANEL_FAKES_JS + r"""
loadModules();

// A user typing. The characters go where a browser puts them — on the element —
// and the panel learns about them ONLY through the event, which is the whole
// question: an implementation that read the input back at save time would pass
// a test that set `card.preview` directly.
const type = (edits) => {
  const inputs = {};
  const walk = (node) => {
    if (node.tagName === "INPUT" && String(node.id).startsWith("preview-")) {
      inputs[node.id.slice("preview-".length)] = node;
    }
    for (const kid of node.children) walk(kid);
  };
  walk(REGIONS.rail);
  for (const [key, text] of Object.entries(edits)) {
    if (!inputs[key]) throw new Error(`no preview input for "${key}"`);
    inputs[key].value = text;
    inputs[key].dispatch("input");
  }
};

main(async () => {
  await settle();
  const loaded = regions();
  type(spec.type ?? {});
  // Something unrelated comes back and repaints. Every element in the rail is
  // REPLACED, the input the user is in among them.
  release();
  await settle();
  const afterALateLanding = regions();
  if (spec.click !== true) { emit({ loaded, afterALateLanding, sent }); return; }
  withClass(REGIONS.foot, "cta")[0].click();
  // Synchronous, and deliberately: `addJob` sets `busy` and paints before its
  // first await, so this is the surface as the user sees it mid-save.
  const clicked = regions();
  await settle();
  // …and the user is free to leave while the POST is still open.
  if (spec.switchTo !== undefined) {
    await onActivated({ tabId: spec.switchTo });
    await settle();
  }
  release();
  await settle();
  emit({ loaded, afterALateLanding, clicked, settled: regions(), sent });
});
"""


def _job_stage(tmp_path, **spec):
    """Boot on a fresh posting, with the page answering the extraction."""
    spec.setdefault("tabs", [{"id": 7, "url": TRACKED_URL}])
    spec.setdefault("replies", {"read_settings": SETTINGS_REPLY})
    spec.setdefault("page", {"extract_job_posting": POSTING_REPLY})
    spec.setdefault("api", {"job-boards": _reply(
        {"match": "none", "job": None, "application": None})})
    return run_node(_JOB_STAGE_DRIVER_JS, spec, tmp_path,
                    source=PANEL_SOURCE)


def test_the_job_preview_belongs_to_the_step_you_are_on(tmp_path):
    """A body renders under the ACTIVE row and nowhere else.

    The rail's grammar is the reason: a done row is a tick and a summary. A Job
    preview under a row that already reads "in library" would be the panel
    offering to add a job one line under its own claim that the job is added —
    and the reading is not cosmetic, because that body carries a button that
    would create a SECOND row for the same posting.
    """
    fresh = _load(tmp_path, page={"extract_job_posting": POSTING_REPLY}, api={
        "lightningai": _reply({"match": "none", "job": None, "application": None})})
    rows = _by_class(fresh["regions"]["rail"], "stg")
    assert rows[0]["class"] == "stg active"
    assert _preview_inputs(rows[0]) == {
        "title": "Machine Learning Engineer",
        "company": "Lightning AI",
        "location": "Remote, US",
    }
    # …and the sub line says where that came from, with the size of what was
    # read: three filled boxes over an empty description would otherwise look
    # exactly like a successful grab.
    assert _by_class(rows[0], "sub")[0]["text"] == "JD grabbed from this page · 11 words"
    assert len(_by_class(fresh["regions"]["rail"], "stg-body")) == 1

    known = _load(tmp_path, page={"extract_job_posting": POSTING_REPLY}, api={
        "lightningai": _reply({"match": "exact", "job": LIGHTNING_JOB,
                               "application": None}),
        "/api/base-resumes": _reply(BASE_RESUMES), "/api/ats-scores": _reply(SCORES)})
    assert _rows(_rail_rows(known))["job"]["state"] == "done"
    # The Job row carries NO body — the one that renders belongs to Score, the
    # row the user is actually on. (This used to assert no body anywhere, which
    # stopped being the same claim the moment a second stage grew one.)
    known_rows = _by_class(known["regions"]["rail"], "stg")
    assert _by_class(known_rows[0], "stg-body") == []
    assert _by_class(known["regions"]["rail"], "kv") == []
    # Not merely unrendered — never asked for. Reading a posting off a page
    # whose stage is Score is a page round trip for something nobody can see.
    assert [msg for msg in known["sent"]
            if (msg.get("message") or {}).get("type") == "extract_job_posting"] == []


NO_POSTING_HERE = _reply({"url": POSTING_URL, "title": "Some page",
                          "text": "", "source": "body"})


def test_a_page_with_no_posting_on_it_renders_an_empty_form_and_no_apology(tmp_path):
    """Most pages are not job postings, and the panel is open across all of
    them. An empty form the user can type into IS the honest rendering of "we
    found nothing" — and it stays out of the note slot, which is reserved for
    what the user just asked for.

    THE PAGE ANSWERS HERE, and that is the whole of what separates this from the
    orphaned-tab test below: this page was read and had no posting on it, so the
    sentence is a claim about the page and the panel is entitled to it. Nothing
    is injected for a page that answered — the injection rung reads SILENCE, not
    emptiness, and a fixture that could not tell the two apart would let that
    discriminator be deleted.
    """
    out = _load(tmp_path, replies={"read_settings": SETTINGS_REPLY},
                # BOTH frame-0 asks answered, which is what makes the claim
                # above a claim: a page that answers the extraction and is
                # SILENT to the detection is a half-orphaned tab, and the
                # detect's own injection rung would fire on it (`loadHasForm`).
                # Leaving it undeclared would test that rung, not this one.
                page={"extract_job_posting": NO_POSTING_HERE,
                      "detect_page": _reply({"tier": "A", "form": False,
                                             "score": 0})},
                api={"lightningai": _reply({"match": "none", "job": None,
                                            "application": None})})
    assert _preview_inputs(out["regions"]["rail"]) == {
        "title": "", "company": "", "location": ""}
    assert _by_class(out["regions"]["rail"], "sub")[0]["text"] == (
        "No job description found on this page.")
    assert [msg for msg in out["sent"] if msg["type"] == "panel_prepare"] == []
    [note] = _by_class(out["regions"]["foot"], "note")
    assert note["text"] == ""


_INGEST_DRIVER_JS = _PANEL_FAKES_JS + r"""
const ns = loadModules();
main(async () => {
  await settle();
  const out = {};
  for (const [name, c] of Object.entries(spec.cases)) {
    // Through `previewFrom` when the case names a POSTING, so the pair is
    // exercised as the round trip it is; from a literal preview otherwise,
    // which is what an EDITED one is.
    const preview = c.posting !== undefined
      ? ns.panel.previewFrom(c.posting) : c.preview;
    out[name] = { preview, body: ns.panel.ingestBodyFrom(preview, c.url) };
  }
  emit(out);
});
"""


@pytest.fixture(scope="module")
def ingested(tmp_path_factory):
    cases = {
        "extracted": {"posting": POSTING_REPLY["data"], "url": TRACKED_URL},
        # A page with no described posting: no labelled lines, so nothing is
        # lifted and the whole blob is the description.
        "plain_page": {"posting": {"text": "Plain text about a job.\nSecond line.",
                                   "source": "content"},
                       "url": POSTING_URL},
        "edited": {"preview": {"title": "Staff ML Engineer", "company": "Lightning AI",
                               "location": "", "text": "the description"},
                   "url": POSTING_URL},
        "whitespace": {"preview": {"title": "  Staff ML Engineer  ", "company": "",
                                   "location": "", "text": "  the description  "},
                       "url": POSTING_URL},
        "nothing": {"preview": {"title": "", "company": "", "location": "", "text": ""},
                    "url": POSTING_URL},
        # A page with no described posting whose own text happens to read
        # label-shaped, with no blank line anywhere to stop the lift. The
        # extractor writes each header line at most ONCE, so a repeat is the
        # page's own words — and the page's own words are what the backend
        # extracts from.
        "repeated_label": {
            "posting": {"source": "content", "text": "\n".join([
                "Title: Machine Learning Engineer",
                "Title: Senior, Remote",
                "We are hiring an ML engineer.",
            ])},
            "url": POSTING_URL},
    }
    return run_node(_INGEST_DRIVER_JS, {"cases": cases},
                    tmp_path_factory.mktemp("panel_ingest"),
                    source=PANEL_SOURCE)


def test_the_url_reaches_the_backend_exactly_as_the_tab_holds_it(ingested):
    """UNSTRIPPED, tracking parameters and all.

    Whether two urls are the same posting is the SERVER's question
    (`is_same_posting`, SYSTEM.md §4 Job), and a client that quietly trimmed
    a query string would be answering it — differently from the server, and
    wrongly on every board where the query string IS the job id.
    """
    assert ingested["extracted"]["body"]["source_url"] == TRACKED_URL
    assert "utm_campaign=spring" in ingested["extracted"]["body"]["source_url"]
    # Even with nothing to save, the url is reported as it is: this function
    # does not decide what a url means.
    assert ingested["nothing"]["body"]["source_url"] == POSTING_URL


def test_an_unedited_posting_reaches_the_backend_exactly_as_the_page_wrote_it(ingested):
    """The round trip is the identity. `extractJobPosting` prefixes a described
    posting's text with `Title:` / `Company:` / `Location:` lines; the preview
    lifts them out so they are editable; this puts them back. Prefixing a second
    time — the obvious wrong implementation — would send the extraction step two
    of each and let it pick."""
    assert ingested["extracted"]["preview"] == {
        "title": "Machine Learning Engineer", "company": "Lightning AI",
        "location": "Remote, US", "source": "json-ld",
        "text": "We are hiring an ML engineer to work on distributed training.",
    }
    assert ingested["extracted"]["body"]["raw_text"] == POSTING_TEXT
    # A page with no described posting keeps its text whole rather than losing
    # its first line to a header parse.
    assert ingested["plain_page"]["preview"]["title"] == ""
    assert ingested["plain_page"]["body"]["raw_text"] == (
        "Plain text about a job.\nSecond line.")


def test_a_repeated_label_stays_in_the_text_instead_of_overwriting_the_field(ingested):
    """The lift takes the FIRST of each label and stops there.

    The blank line agent.js always writes ends the header on the JSON-LD path;
    this is the other path, where there is no header and no blank — a page
    whose text simply reads label-shaped. A lift with no repeat guard would
    take the second `Title:` line as well: the field ends up holding the
    page's prose, and the line it came from is CONSUMED, so it never reaches
    the backend at all. What that costs is invisible — the job saves fine, one
    line shorter than the page it came from.
    """
    case = ingested["repeated_label"]
    assert case["preview"]["title"] == "Machine Learning Engineer"
    # The repeat stayed where the page put it, at the head of the text…
    assert case["preview"]["text"] == (
        "Title: Senior, Remote\nWe are hiring an ML engineer.")
    # …and NOTHING the page said is missing from what is sent. This is the
    # property the guard exists for: the fields are a convenience, the text is
    # the evidence.
    for line in ("Title: Machine Learning Engineer", "Title: Senior, Remote",
                 "We are hiring an ML engineer."):
        assert line in case["body"]["raw_text"], line


def test_what_the_user_typed_is_what_the_backend_extracts_from(ingested):
    """The whole point of an editable preview: a title the user corrected has to
    be the title the extraction step reads. An empty field contributes no line
    at all — mirroring `extractJobPosting`'s own `if (posting.title)` guards,
    because `Location: ` with nothing after it is a claim that the posting has
    an empty location."""
    assert ingested["edited"]["body"]["raw_text"] == (
        "Title: Staff ML Engineer\nCompany: Lightning AI\n\nthe description")
    assert ingested["whitespace"]["body"]["raw_text"] == (
        "Title: Staff ML Engineer\n\nthe description")
    # Nothing read and nothing typed: an empty body, which `addJob` refuses to
    # send rather than spending an extraction on an empty string.
    assert ingested["nothing"]["body"]["raw_text"] == ""


def test_a_character_typed_into_the_preview_survives_a_render_it_did_not_ask_for(tmp_path):
    """THE reason `card.preview` exists, driven end to end.

    Renders are not click-driven: four loads land asynchronously and each one
    repaints the whole rail. An input holding its value in the DOM therefore
    loses whatever was typed the moment a base-resume list comes back — the
    element is REPLACED, and the store is the only thing a rebuild reads.
    """
    out = _job_stage(tmp_path, hold=["/api/base-resumes"],
                     type={"title": "Staff ML Engineer"}, api={
        "job-boards": _reply({"match": "none", "job": None, "application": None}),
        "/api/base-resumes": _reply(BASE_RESUMES)})
    before = [n for n in _walk(out["loaded"]["rail"]) if n["tag"] == "INPUT"]
    after = [n for n in _walk(out["afterALateLanding"]["rail"]) if n["tag"] == "INPUT"]
    # The elements really were thrown away — without this the assertion below
    # would pass on a panel that simply never re-rendered.
    assert {n["uid"] for n in before}.isdisjoint({n["uid"] for n in after})
    assert _preview_inputs(out["afterALateLanding"]["rail"]) == {
        "title": "Staff ML Engineer",       # the user's characters
        "company": "Lightning AI",          # …and the extraction's, untouched
        "location": "Remote, US",
    }


def test_the_primary_is_out_of_reach_while_the_save_is_open(tmp_path):
    """A POST that takes a second is a second in which the only thing saying so
    is the button. Disabled AND spinning: disabled is the guard — a second POST
    of the same posting is the "you saved this last week" path at best — and the
    spinner is why the user is not clicking again."""
    out = _job_stage(tmp_path, click=True, hold=["POST /api/jobs"])
    [cta] = _by_class(out["clicked"]["foot"], "cta")
    assert cta["disabled"] is True
    assert cta["class"] == "cta spin"
    # …and the failure hands it back rather than leaving the panel frozen with
    # the one control it has permanently pressed.
    [note] = _by_class(out["settled"]["foot"], "note")
    assert note["text"] == "the backend is unreachable"
    assert note["class"] == "note error"
    [after] = _by_class(out["settled"]["foot"], "cta")
    assert after["disabled"] is False
    assert after["class"] == "cta"
    # Still on Job, with the preview still holding what was read: a failed save
    # must not cost the user the form they were about to send again.
    assert _preview_inputs(out["settled"]["rail"])["title"] == "Machine Learning Engineer"


def test_a_save_that_lands_after_you_switch_tabs_paints_nothing(tmp_path):
    """The generation rule applied to an ACTION, which is where it is easiest to
    forget: a POST looks like something the user is waiting for rather than a
    round trip like any other. It is not. The user is free to leave while it is
    open, and there is exactly one store for its answer to land in — so a save
    made on a posting would otherwise name that job, force `match: "exact"` and
    put "Saved with 3 skills extracted" on a tab that never asked for anything.
    """
    out = _job_stage(tmp_path, click=True, hold=["POST /api/jobs"], switchTo=42,
                     tabUrls={"42": "chrome://settings"}, api={
        "job-boards": _reply({"match": "none", "job": None, "application": None}),
        "POST /api/jobs": _reply(SAVED_JOB)})
    # The save really was sent — the race is between two real things.
    assert len(_posts(out)) == 1
    settled = out["settled"]
    assert "Saved" not in _text(settled["foot"])
    assert "job-just-saved" not in json.dumps(settled)
    # No chip, because nothing is claimed about a settings tab — and certainly
    # not that the job we just saved is in it.
    assert _by_class(settled["identity"], "chip") == []
    # A settings tab is at Job like anything else the backend cannot name — and
    # its preview is EMPTY. Tab A's posting reaching those boxes would be the
    # same bug wearing a form: an offer to save one page under another's url.
    assert _preview_inputs(settled["rail"]) == {
        "title": "", "company": "", "location": ""}


def test_a_save_that_FAILS_after_you_switch_tabs_paints_nothing_either(tmp_path):
    """The same rule on the other limb, and it was the untested one.

    Found by mutation at the Round A gate: deleting the generation check from
    the FAILURE limb of the action ladder left all 91 panel tests green, where
    deleting it from the success limb killed three. The two limbs are not
    symmetric in how easy they are to believe — a failure feels like something
    the user is owed, so it is the one that gets written without the guard —
    and the wrong answer is identical: a red sentence about a page they left,
    in the note slot of a tab that never asked for anything.

    ONE OF THREE, and deliberately not one for all three. The gate first wrote
    this as a single pin on the strength of "the ladder is one function now" —
    and the review proved that claim STRUCTURAL: re-inlining a guardless
    failure ladder into `quickTailor` alone left the whole suite green, because
    nothing drove that action's failure limb. Task 12 moved the actions into
    their own module and Task 15 cut that into seven, which is exactly when a
    structural claim stops holding without saying so. The twins for
    `scoreAllBases` and `quickTailor` are in this file's siblings.
    """
    out = _job_stage(tmp_path, click=True, hold=["POST /api/jobs"], switchTo=42,
                     tabUrls={"42": "chrome://settings"}, api={
        "job-boards": _reply({"match": "none", "job": None, "application": None}),
        "POST /api/jobs": {"ok": False, "error": "the save came apart"}})
    # The save really was sent and really did fail — the race is between two
    # real things, not between one real thing and an assertion.
    assert len(_posts(out)) == 1
    settled = out["settled"]
    assert "the save came apart" not in json.dumps(settled)
    # Nothing red anywhere on a settings tab, and nothing still spinning: the
    # early return leaves this tab's own render untouched rather than half-lit.
    assert [n for n in _walk(settled["foot"]) if "error" in str(n.get("class"))] == []
    assert [n for n in _walk(settled["foot"]) if "spin" in str(n.get("class"))] == []


def test_a_saved_job_is_sent_as_edited_and_the_stage_advances_on_the_reload(tmp_path):
    """The whole action, end to end: what goes out, and what moves the rail.

    The stage advances because the DATA moved — the second match read is the
    backend recognising the url we just handed it — never because `addJob` said
    so. That is the design's "stage inference, not stage navigation", and it is
    what keeps a tick from appearing beside a button that still asks for the
    same thing.
    """
    out = _job_stage(tmp_path, click=True, type={"company": "Lightning AI, Inc."}, api={
        "job-boards": [
            _reply({"match": "none", "job": None, "application": None}),
            _reply({"match": "exact", "job": SAVED_JOB, "application": None}),
        ],
        "POST /api/jobs": _reply(SAVED_JOB),
        "/api/base-resumes": _reply(BASE_RESUMES),
        "/api/ats-scores": _reply([]),
    })
    [post] = _posts(out)
    assert post["path"] == "/api/jobs"
    assert json.loads(post["init"]["body"]) == {
        "raw_text": POSTING_TEXT.replace("Lightning AI", "Lightning AI, Inc."),
        "source_url": TRACKED_URL,
    }
    # The whole conversation, in order. The second match read is `loadContext`
    # re-run, and the scores read after it is the proof that the reload found a
    # job where the first pass found none — the panel only asks for the scores
    # of a job it has.
    #
    # THE APPLICATIONS READ IS THE PRICE OF THE PICKER'S NEW GATE, and it is
    # here on purpose rather than filtered out: an unmatched page now asks for
    # the drafts whether or not it holds a form, so an ordinary posting spends
    # one extra round trip per PANEL (the latch, not per page). The reload does
    # not repeat it — by then the backend has named the job, and a matched page
    # is not offered a picker.
    assert [f'{(msg.get("init") or {}).get("method", "GET")} {msg["path"].split("?")[0]}'
            for msg in out["sent"] if msg["type"] == "api"] == [
        "GET /api/jobs/match", "GET /api/applications", "GET /api/base-resumes",
        "POST /api/jobs", "GET /api/jobs/match", "GET /api/ats-scores"]
    settled = out["settled"]
    [note] = _by_class(settled["foot"], "note")
    assert note["text"] == "Saved with 3 skills extracted."
    assert note["class"] == "note"
    rows = _rows(_rail_rows({"regions": settled}))
    assert rows["job"]["state"] == "done"
    assert rows["score"]["state"] == "active"
    # The body went with the step: nothing offers to add this job again.
    assert _by_class(settled["rail"], "kv") == []


def test_a_posting_already_in_the_library_says_so_rather_than_claiming_a_save(tmp_path):
    """`already_existed` is a transient attribute rather than a column (design
    §8.14), and it is the difference between "saved" and "you saved this last
    week" — which is the whole reason the capture card had two states. Ported
    with the widget's own sentence."""
    out = _job_stage(tmp_path, click=True, api={
        "job-boards": _reply({"match": "none", "job": None, "application": None}),
        "POST /api/jobs": _reply({**SAVED_JOB, "already_existed": True}),
        "/api/base-resumes": _reply(BASE_RESUMES),
    })
    [note] = _by_class(out["settled"]["foot"], "note")
    assert note["text"] == "Already tracked. This posting was saved earlier."


# ---------- the application picker: no match, and the user's drafts ----------
#
# Workday's posting→apply split is two origins, so `/api/jobs/match` is silent
# on the apply page of a job the user already tailored. The floating card had
# a manual picker; the panel did not. This is that picker, under the Job
# preview, and only in the state where guessing would be the alternative.
#
# THE FORM CLAUSE IS GONE FROM THAT STATE (2026-08-18). It used to read "a
# form, no match, and the user's drafts", and the form half was field-falsified
# on the very flow the picker exists for: a Workday wizard gives every step its
# own url (so nothing matches, ever), carries the JD in the DOM of steps that
# have no form, and reports `hasForm: false` at bind-time anyway — late SPA
# render, a login step, or a form that appears with no url change to re-bind
# on. The picker was therefore invisible on Workday and perfectly visible on
# the fast ATSes that never needed it.
#
# WHAT THE TESTS BELOW NOW PIN, in the order they appear: the offer stands on
# any unmatched page the panel is bound to, form or no form and whatever
# detection says; it still never stands on a page something is armed on; and it
# still never stands on a tab the extension has no business on.

# The next page of the SAME Workday tenant — different path, same first
# segment, which is `sessionTenant`'s whole scope. A pick made on APPLY_URL
# has to come back here without another click; that is the goal's second half.
APPLY_NEXT_URL = "https://acme.wd5.myworkdayjobs.com/en-US/careers/apply/review"
# A different company's Workday host. Origin differs, so tenant differs; a
# pick scoped to Acme must not restore here.
GLOBEX_APPLY_URL = (
    "https://globex.wd1.myworkdayjobs.com/en-US/careers/apply/applyManually")
ACME_TENANT = "https://acme.wd5.myworkdayjobs.com/en-US"

HAS_FORM = {"detect_page": _reply({"tier": "B", "form": True, "score": 2})}
# What a REACHABLE page with no job description on it answers. `agent.js`'s
# extraction always returns an object — it falls back to `document.body.innerText`
# — so this, and not silence, is what an apply page says about itself.
#
# The distinction is load-bearing since the injection rung: silence means our
# content scripts are not in that tab (an extension reload orphans them), which
# now fires ONE `panel_prepare`, and it renders a different sentence. A fixture
# that stayed silent would put every apply-page test into the orphaned-tab case
# by accident.
NO_JD_HERE = {"extract_job_posting": _reply(
    {"url": APPLY_URL, "title": "Apply — Acme", "text": "", "source": "body"})}


def _by_tag(node, tag):
    return [found for found in _walk(node) if found["tag"] == tag.upper()]


def _picker(node):
    """The draft <select>, or None when the offer is absent."""
    found = _by_tag(node, "SELECT")
    return found[0] if found else None


def _draft_options(select):
    """Real drafts, skipping the disabled placeholder."""
    if select is None:
        return []
    return [opt for opt in select["children"] if opt.get("value")]


def _draft(i, **overrides):
    """One `ApplicationSummary` row, newest-first as the list endpoint orders."""
    return {"id": f"app-{i}", "job_id": f"job-{i}",
            "base_resume": "ai_ml_engineer", "status": "draft",
            "job_company": f"Acme {i}", "job_title": f"Research Engineer {i}",
            **overrides}


def _drafts(n=6):
    return [_draft(i) for i in range(1, n + 1)]


def _picker_api(drafts=None, **extra):
    """Match-none on a Workday apply URL, plus the list the picker reads.

    The list needle is `GET /api/applications?` so it cannot collide with a
    detail read (`GET /api/applications/app-1`) — the same method-qualified
    trick the harness header documents for POST `/api/jobs`.
    """
    drafts = _drafts() if drafts is None else drafts
    return {
        "myworkdayjobs": _reply({"match": "none", "job": None,
                                 "application": None}),
        "GET /api/applications?": _reply(drafts),
        "/api/base-resumes": _reply(BASE_RESUMES),
        "/api/ats-scores": _reply(SCORES),
        "GET /api/applications/app-1": _reply({
            "id": "app-1", "pdf_path": "renders/app-1.pdf", "status": "draft",
        }),
        **extra,
    }


def _list_gets(out):
    """Every applications-list GET. Detail paths have no `?`."""
    return [msg for msg in out["sent"]
            if msg["type"] == "api"
            and "/api/applications" in msg["path"]
            and "?" in msg["path"]]


def _on_apply(**spec):
    spec.setdefault("tabs", [{"id": 7, "url": APPLY_URL}])
    # MERGED rather than replaced, so a caller that has something to say about
    # one of the two frame-0 asks still gets a truthful answer to the other. An
    # apply page is reachable and carries no JD; leaving the extraction
    # undeclared would model a tab our scripts never reached, which is a
    # different page and a different sentence.
    spec["page"] = {**HAS_FORM, **NO_JD_HERE, **spec.pop("page", {})}
    spec.setdefault("api", _picker_api())
    spec.setdefault("replies", {"read_settings": SETTINGS_REPLY})
    return spec


def test_the_picker_renders_on_an_unmatched_page_with_candidates(tmp_path):
    """The exact state: a page the backend is silent about, drafts to offer.

    Company · title · status, newest first, in a native select so a long list
    scrolls instead of overflowing the Job body. A sixth exists so the old
    five-row cap cannot silently return: every draft the list returned is
    an option.

    This one boots with a form because that is the ATS that always worked; the
    form-less and never-detected shapes are the two tests below it.
    """
    out = _load(tmp_path, **_on_apply())
    select = _picker(out["regions"]["rail"])
    assert select is not None
    options = _draft_options(select)
    assert len(options) == 6
    shown = _text(options[0])
    assert "Acme 1" in shown
    assert "Research Engineer 1" in shown
    assert "draft" in shown.lower()
    assert "Acme 6" in _text(options[-1])
    # Placeholder first, disabled, not a draft.
    placeholder = select["children"][0]
    assert placeholder["value"] in (None, "")
    assert placeholder["disabled"] is True
    assert "choose" in placeholder["text"].lower()
    # Label wired to the select — no dead options, no unlabelled control.
    label = next(n for n in _walk(out["regions"]["rail"]) if n["tag"] == "LABEL"
                 and "draft" in _text(n).lower())
    assert label["attrs"].get("for") == select["id"]
    assert select["id"]


def test_the_list_get_asks_for_drafts_and_the_label_says_what_a_pick_does(tmp_path):
    """The wire and the sentence. `status=draft` is a delta from the widget's
    `?limit=100` — the server already filters, and this picker is drafts-only.
    The label is the offer in words, not a cap line: a select scrolls natively.
    """
    out = _load(tmp_path, **_on_apply())
    labels = " ".join(n["text"] for n in _by_tag(out["regions"]["rail"], "LABEL"))
    assert "Recent drafts — pick one to work on here" in labels
    [list_get] = _list_gets(out)
    assert "status=draft" in list_get["path"]
    assert "limit=" in list_get["path"]


def test_an_empty_list_renders_no_picker_at_all(tmp_path):
    """Honest absence: nothing to offer is nothing rendered — not an empty
    list, not a 'no applications' sentence occupying the Job body."""
    out = _load(tmp_path, **_on_apply(api=_picker_api(drafts=[])))
    assert _picker(out["regions"]["rail"]) is None
    assert "recent" not in _text(out["regions"]["rail"]).lower()
    assert "application" not in _text(out["regions"]["rail"]).lower()


def test_a_matched_page_never_offers_the_picker(tmp_path):
    """The backend already named this page. Offering a second application on
    top of that is the panel arguing with the match, which is the one thing
    a pick must never do — `restoreSession` yields to the backend for the
    same reason."""
    out = _load(tmp_path, tabs=[{"id": 7, "url": APPLY_URL}], page=HAS_FORM, api={
        "myworkdayjobs": _reply({"match": "exact", "job": LIGHTNING_JOB,
                                 "application": {"id": "app-from-backend",
                                                 "status": "draft"}}),
        "GET /api/applications?": _reply(_drafts()),
        "/api/base-resumes": _reply(BASE_RESUMES),
        "/api/ats-scores": _reply(SCORES),
        "GET /api/applications/app-from-backend": _reply(
            {"pdf_path": "r.pdf", "status": "draft"}),
    })
    assert _picker(out["regions"]["rail"]) is None
    # And it never asked: a matched page is not the lazy-load's trigger.
    assert _list_gets(out) == []


def test_a_page_with_no_form_on_it_is_offered_the_drafts_anyway(tmp_path):
    """THE ROUND, at its smallest. No `page` fixture at all, so the detection
    door answers "no frame answered" — the honest shape of a Workday step whose
    scripts never loaded, or a login step, or an SPA that has not painted. The
    panel therefore knows nothing about a form here, and the offer stands.

    THE INVERSE OF WHAT THIS FILE USED TO ASSERT. The old test said a page
    without a form must not even fetch the list, on the always-on-cost rule.
    That rule bought one round trip per panel (the list is latched) and cost
    the picker on every Workday wizard step there is — the trade the live
    session reversed.
    """
    out = _load(tmp_path, tabs=[{"id": 7, "url": APPLY_URL}], api=_picker_api())
    assert len(_list_gets(out)) == 1
    assert len(_draft_options(_picker(out["regions"]["rail"]))) == 6


def test_a_page_that_answers_no_form_forever_is_offered_the_drafts(tmp_path):
    """THE WORKDAY SHAPE, end to end and with the page insisting.

    Detection answers — four times, the first look and all three retries — and
    every answer is `form: false`. Nothing about the picker may depend on that
    verdict ever turning true: the drafts are offered from the first paint and
    are still there after the schedule has run itself out.

    The sibling above is the same claim with the page saying nothing at all;
    together they are "no detection dependency" from both sides.
    """
    out = _load(tmp_path, tabs=[{"id": 7, "url": APPLY_URL}],
                page={"detect_page": NO_FORM}, api=_picker_api())
    assert len(_detects(out)) == 4, "the page was not asked the way it thinks"
    assert len(_draft_options(_picker(out["regions"]["rail"]))) == 6
    assert len(_list_gets(out)) == 1


_PICK_DRIVER_JS = _PANEL_FAKES_JS + r"""
const findTag = (node, tag) => [
  ...(node.tagName === tag ? [node] : []),
  ...node.children.flatMap((kid) => findTag(kid, tag)),
];
loadModules();
main(async () => {
  await settle();
  const loaded = regions();
  const sel = findTag(REGIONS.rail, "SELECT")[0];
  let clicked = null;
  if (sel) {
    const drafts = sel.children.filter((opt) => opt.value);
    const chosen = drafts[spec.pick ?? 0];
    if (chosen) {
      sel.value = chosen.value;
      sel.dispatch("change");
      clicked = regions();
    }
  }
  if (spec.switchTo !== undefined) {
    await onActivated({ tabId: spec.switchTo });
    await settle();
  }
  release();
  await settle();
  emit({ loaded, clicked, settled: regions(), sent, writes });
});
"""


def _session_writes(out):
    return [w for w in out["writes"] if w.get("widget.session")]


def _pick(tmp_path, **spec):
    spec = _on_apply(**spec)
    spec.setdefault("pick", 0)
    return run_node(_PICK_DRIVER_JS, spec, tmp_path, source=PANEL_SOURCE)


def test_picking_an_application_arms_the_rail_and_writes_this_pages_tenant(tmp_path):
    """One click, and afterwards the pick is indistinguishable from a backend
    match: identity chip, deep-link, Fill reachable — all by data, never by a
    hand-set stage.
    """
    out = _pick(tmp_path)
    assert out["clicked"] is not None, "the picker never rendered a row to click"
    settled = out["settled"]
    assert _by_class(settled["identity"], "chip")[0]["text"] == "Application · draft"
    [link] = [n for n in _by_class(settled["identity"], "linkish")
              if "/applications/" in (n.get("href") or "")]
    assert link["href"] == f"{APP_URL}/applications/app-1"
    rows = _rows(_rail_rows({"regions": settled}))
    assert rows["job"]["state"] == "done"
    assert rows["fill"]["state"] == "active"
    assert _picker(settled["rail"]) is None


def test_a_pick_writes_widget_session_scoped_to_this_pages_tenant(tmp_path):
    """The session entry is scoped to THIS url's tenant — the apply origin,
    not the posting the user came from. Both surfaces read `widget.session`.
    """
    writes = _session_writes(_pick(tmp_path))
    assert writes, "the pick never wrote widget.session"
    entry = writes[-1]["widget.session"]
    assert list(writes[-1]) == ["widget.session"]
    assert entry["tenant"] == ACME_TENANT
    assert entry["origin"] == "https://acme.wd5.myworkdayjobs.com"
    assert entry["applicationId"] == "app-1"
    assert entry["jobId"] == "job-1"
    assert entry["company"] == "Acme 1"
    assert entry["title"] == "Research Engineer 1"
    # PROVENANCE IS NOT A FIELD HERE, and that is the design rather than an
    # omission: `applicationId` already carries it. The backend's own match
    # runs before restore and wins, so an entry that names an application is
    # one the USER created — `restoreSession` re-derives `claimed` from that,
    # pinned by `test_a_restored_pick_is_still_a_claim`. A stored flag would
    # be a second source for one fact, free to disagree with the first.
    assert "claimed" not in entry, (
        "the bridge grew a `claimed` field again — see sessionEntryFrom")


def test_the_bridge_survives_a_detail_get_that_fails(tmp_path):
    """The reason `remember()` sits BEFORE the first await, pinned.

    The hazard of a post-await remember is a LOST bridge, not a mis-addressed
    one: `duringAction` returns null once the generation moves, so a late
    remember never runs at all — and it equally never runs when the detail
    GET merely fails. The user's pick must teach the session whatever happens
    to that GET, or the next wizard page pauses again and the pick taught
    nothing. (Moving the remember after the await makes exactly this test
    fail: the failing GET aborts the action before the bridge is written.)
    """
    api = _picker_api()
    # REPLACE the fixture's success needle, don't add a second: the api map
    # matches by substring in INSERTION order, so an appended failing key
    # never fires — this test's first draft did exactly that and passed on a
    # successful GET (green for the wrong reason; the probe caught it).
    assert "GET /api/applications/app-1" in api
    api["GET /api/applications/app-1"] = {
        "ok": False, "error": "the backend is unreachable"}
    out = _pick(tmp_path, api=api)
    writes = _session_writes(out)
    assert writes, "a failed detail GET cost the user the bridge"
    entry = writes[-1]["widget.session"]
    assert entry["applicationId"] == "app-1"
    assert entry["tenant"] == ACME_TENANT
    # The failure is said (duringAction's catch) while the pick STANDS (the
    # chip claims only what the pick itself established). The action returned
    # before loadBaseScores, so the rail degrades to the earliest stage whose
    # data is missing — Score, whose own CTA re-earns the ranking — rather
    # than claiming a readiness nothing read. Everything downstream recovers
    # on the next load or the next press; the bridge is the one thing that
    # must not wait for either.
    [note] = _by_class(out["settled"]["foot"], "note")
    assert note["text"] == "the backend is unreachable"
    assert _by_class(out["settled"]["identity"], "chip")[0]["text"] == (
        "Application · draft")
    rows = _rows(_rail_rows({"regions": out["settled"]}))
    assert rows["score"]["state"] == "active"
    assert rows["resume"]["state"] == "locked"


def test_a_pick_on_the_apply_page_restores_on_the_next_wizard_step(tmp_path):
    """The goal's second half. Page A is the apply origin; page B is the next
    path of the same tenant. No second pick: `restoreSession` reads the entry
    the first pick wrote, under `widget.session`, and forces `match: "exact"`
    so Add job does not cover it.
    """
    picked = _pick(tmp_path)
    writes = _session_writes(picked)
    assert writes, "the pick never wrote widget.session"
    out = _load(tmp_path, tabs=[{"id": 7, "url": APPLY_NEXT_URL}], page=HAS_FORM,
                stored={"widget.session": writes[-1]["widget.session"]},
                api=_picker_api())
    assert _by_class(out["regions"]["identity"], "chip")[0]["text"] == (
        "Application · draft")
    [link] = [n for n in _by_class(out["regions"]["identity"], "linkish")
              if "/applications/" in (n.get("href") or "")]
    assert link["href"] == f"{APP_URL}/applications/app-1"
    assert _rows(_rail_rows(out))["job"]["state"] == "done"
    # Restored, so the picker has nothing to offer — the question is answered.
    # THE ARMED HALF of both gates, and the half the dropped form gate must not
    # be allowed to take with it: an armed page neither paints the offer nor
    # spends the round trip behind it. (`test_a_matched_page_never_offers_the_
    # picker` is the same pair for a page the BACKEND named.)
    assert _picker(out["regions"]["rail"]) is None
    assert _list_gets(out) == []


def test_a_pick_never_puts_claimed_on_the_wire(tmp_path):
    """Provenance is a panel fact. The backend's application row has no such
    field, and a body that sent one would be a silent no-op or a 422 depending
    on extra-forbid — either way it is not the backend's to store.
    """
    out = _pick(tmp_path)
    bodies = [msg.get("init", {}).get("body") for msg in out["sent"]
              if isinstance(msg.get("init"), dict)]
    for body in bodies:
        if not body:
            continue
        assert "claimed" not in body
    for msg in out["sent"]:
        assert "claimed" not in str(msg.get("path") or "")


_CLAIMED_RESTORE_JS = _PANEL_FAKES_JS + r"""
const ns = loadModules();
main(async () => {
  await settle();
  const facts = ns.panel.actionStore().read();
  emit({ claimed: facts.claimed === true, applicationId: facts.application?.id ?? null });
});
"""


def test_a_restored_pick_is_still_a_claim(tmp_path):
    """A bridge-restored arming is the same claim, carried forward — and it
    is carried by INFERENCE, which is the whole of R-C's bridge decision.

    Page 2 of a wizard has no picker on screen. The only thing that tells it
    this binding was the user's is `restoreSession` setting `claimed` when
    it arms from an entry that names an application. THE ENTRY ITSELF SAYS
    NOTHING about provenance — `sessionEntryFrom` deliberately does not
    write the field — so this test is what proves the inference is
    sufficient rather than a stored flag being quietly missed. Without the
    write, the rail arms and the Job row is a wall.
    """
    picked = _pick(tmp_path)
    writes = _session_writes(picked)
    assert writes, "the pick never wrote widget.session"
    out = run_node(_CLAIMED_RESTORE_JS, {
        "tabs": [{"id": 7, "url": APPLY_NEXT_URL}],
        "page": HAS_FORM,
        "stored": {"widget.session": writes[-1]["widget.session"]},
        "api": _picker_api(),
        "replies": {"read_settings": SETTINGS_REPLY},
    }, tmp_path, source=PANEL_SOURCE)
    assert out["applicationId"] == "app-1"
    assert out["claimed"] is True


# ---------- the entry a PRE-R-C panel left on disk ---------------------------
#
# EVERY OTHER RESTORE TEST ROUND-TRIPS AN ENTRY THE CURRENT WRITER PRODUCED,
# which means none of them can see the one shape that actually exists in the
# wild: R-C dropped `claimed`, `attachedBase` and `guidedArmed` from
# `sessionEntryFrom`, and every profile that ran a build before it still has an
# entry carrying all three. Restoring from that is not a hypothetical — it is
# what the first open after the update does.
#
# The three cases below are the ones that could bite, and they are the reason
# `extension_fixtures.py` deliberately keeps the OLD keys in its shared entry
# (see the label there): the fixture is this suite's only on-disk sample of the
# pre-R-C writer, and it is kept to be restored FROM.


def _legacy_entry(**over):
    """The entry the pre-R-C `sessionEntryFrom` wrote, field for field.

    Written out here rather than derived from the current writer, which is the
    whole point: a helper that built this by adding keys to today's output
    would go stale in exactly the way that hides the bug.
    """
    return {
        "origin": "https://acme.wd5.myworkdayjobs.com",
        "tenant": ACME_TENANT,
        "at": int(time.time() * 1000),
        "applicationId": "app-1",
        "status": "draft",
        "jobId": "job-acme",
        "company": "Acme",
        "title": "Staff Engineer",
        "pdfReady": True,
        "touched": True,
        # The three R-C dropped.
        "attachedBase": None,
        "guidedArmed": False,
        "claimed": True,
        "baseSlug": "ai_ml_engineer",
        "baseArmed": True,
        **over,
    }


def test_an_entry_written_before_r_c_still_restores(tmp_path):
    """The upgrade path. `restorableSession` and `restoreSession` both read by
    NAME, so the three extra keys are ignored rather than tripping anything —
    but "ignored" is a claim about code that changed, and this is the only test
    that can make it.
    """
    out = run_node(_CLAIMED_RESTORE_JS, {
        "tabs": [{"id": 7, "url": APPLY_NEXT_URL}],
        "page": HAS_FORM,
        "stored": {"widget.session": _legacy_entry()},
        "api": _picker_api(),
        "replies": {"read_settings": SETTINGS_REPLY},
    }, tmp_path, source=PANEL_SOURCE)
    assert out["applicationId"] == "app-1", out
    assert out["claimed"] is True, out


def test_a_legacy_claimed_false_is_still_restored_as_a_claim(tmp_path):
    """THE ONE THAT WOULD HAVE BEEN A REGRESSION, and the reason dropping the
    field beat keeping it.

    An old entry can carry `claimed: false` honestly — the pre-R-C writer wrote
    that whenever the store's flag was unset, which included a backend-matched
    save. If `restoreSession` had been "fixed" to read the stored flag instead
    of inferring, those users would arm the rail with a Job row that is a wall:
    no door back, because the panel would believe it had not been their pick.

    The inference reads `applicationId` and nothing else, so the stale flag is
    inert. That is the design, not a happy accident — `sessionEntryFrom`'s note
    says why, and this is what holds it.
    """
    out = run_node(_CLAIMED_RESTORE_JS, {
        "tabs": [{"id": 7, "url": APPLY_NEXT_URL}],
        "page": HAS_FORM,
        "stored": {"widget.session": _legacy_entry(claimed=False)},
        "api": _picker_api(),
        "replies": {"read_settings": SETTINGS_REPLY},
    }, tmp_path, source=PANEL_SOURCE)
    assert out["claimed"] is True, out


_RESTORE_THEN_REMEMBER_JS = _PANEL_FAKES_JS + r"""
const ns = loadModules();
main(async () => {
  await settle();
  const facts = ns.panel.actionStore().read();
  ns.panel.actionStore().remember();
  await settle();
  emit({ claimed: facts.claimed === true,
         applicationId: facts.application?.id ?? null,
         writes });
});
"""


def test_the_next_write_does_not_launder_the_dead_keys_back_in(tmp_path):
    """The other half of the upgrade: a profile is only clean once it has been
    WRITTEN again.

    A restore reads by name and a `remember()` builds from the store, so the old
    keys should die at the first write on that origin rather than being copied
    forward. The failure this catches is the obvious "fix" — a writer that
    spreads the restored entry (`{...entry, ...fields}`) to be safe, which would
    keep all three alive on disk for as long as the user keeps applying.
    """
    out = run_node(_RESTORE_THEN_REMEMBER_JS, {
        "tabs": [{"id": 7, "url": APPLY_NEXT_URL}],
        "page": HAS_FORM,
        "stored": {"widget.session": _legacy_entry()},
        "api": _picker_api(),
        "replies": {"read_settings": SETTINGS_REPLY},
    }, tmp_path, source=PANEL_SOURCE)
    assert out["claimed"] is True, out
    writes = _session_writes(out)
    assert writes, "remember() wrote nothing"
    entry = writes[-1]["widget.session"]
    for dead in ("claimed", "attachedBase", "guidedArmed"):
        assert dead not in entry, (dead, entry)
    assert entry["applicationId"] == "app-1", entry


def test_a_pick_on_one_workday_tenant_is_refused_on_another(tmp_path):
    """Acme's apply origin is not Globex's. A remembered pick that travelled
    would autofill the wrong company's form, which is the 2026-08-16 bleed
    wearing Workday clothes. The tenant on the entry is the guard; drop it
    (or take it from a hardcoded posting url) and this restores."""
    picked = _pick(tmp_path)
    writes = _session_writes(picked)
    assert writes, "the pick never wrote widget.session"
    out = _load(tmp_path, tabs=[{"id": 7, "url": GLOBEX_APPLY_URL}],
                page=HAS_FORM,
                stored={"widget.session": writes[-1]["widget.session"]},
                api=_picker_api())
    assert _by_class(out["regions"]["identity"], "chip")[0]["text"] == "New"
    assert _rows(_rail_rows(out))["job"]["state"] == "active"
    hrefs = [n.get("href") or "" for n in _by_class(out["regions"]["identity"], "linkish")]
    assert all("/applications/app-1" not in href for href in hrefs)


_LIST_RACE_DRIVER_JS = _PANEL_FAKES_JS + r"""
loadModules();
main(async () => {
  await settle();
  const held = regions();
  await onActivated({ tabId: spec.switchTo });
  await settle();
  release();
  await settle();
  emit({ held, settled: regions(), sent, writes });
});
"""


def test_a_list_that_lands_after_you_switch_tabs_paints_nothing(tmp_path):
    """The generation rule applied to the load, held at the applications GET.

    Tab A is the apply page that asked; tab B is a settings page that never
    did. A list landing after the switch must not draw a picker on a tab the
    extension has no business on — and must not arm an application nobody
    picked.
    """
    spec = _on_apply(hold=["GET /api/applications?"], switchTo=42,
                     tabUrls={"42": "chrome://settings"})
    out = run_node(_LIST_RACE_DRIVER_JS, spec, tmp_path, source=PANEL_SOURCE)
    assert _list_gets(out), "the list GET never went out — the race is fake"
    settled = out["settled"]
    assert _picker(settled["rail"]) is None
    assert _by_class(settled["identity"], "chip") == []
    assert [w for w in out["writes"] if w.get("widget.session")] == []


def test_the_list_is_not_fetched_again_on_a_tab_switch(tmp_path):
    """The latch, like `resumesRequest`. Two apply pages that both qualify
    for the picker spend one round trip, not one per glance.

    The TRIGGER (do not ask at all) is the matched-page, armed-page and
    chrome:// tests: those never qualify, so a `loadApplications()` on every
    `loadContext` fetches on them. This test is the other half: once asked, do
    not ask again — which is what makes "offer on every unmatched page" cost
    one round trip per panel rather than one per page.
    """
    spec = _on_apply(switchTo=42, tabUrls={"42": APPLY_NEXT_URL})
    out = run_node(_LIST_RACE_DRIVER_JS, spec, tmp_path, source=PANEL_SOURCE)
    assert len(_list_gets(out)) == 1


def test_a_loaded_list_paints_a_picker_on_the_next_page_form_or_not(tmp_path):
    """The list is tab-independent, and since 2026-08-18 so is the OFFER.

    Tab A is the apply page that fetched the drafts; tab B is a posting with no
    form that nothing matched either. The list is already in hand, so the
    second page costs nothing and gets the same offer — which is the whole
    point on Workday, where the step the user is standing on is as likely to be
    the form-less one as not.

    This test is the exact inverse of what it asserted before the form gate
    came out; the `assert` on tab A is kept so a picker that stopped rendering
    everywhere could not pass it.
    """
    spec = _on_apply(
        page={"detect_page": [
            _reply({"tier": "B", "form": True, "score": 2}),
            _reply({"tier": "A", "form": False, "score": 0}),
        ]},
        switchTo=42, tabUrls={"42": POSTING_URL},
        api={**_picker_api(),
             "lightningai": _reply({"match": "none", "job": None,
                                    "application": None})})
    out = run_node(_LIST_RACE_DRIVER_JS, spec, tmp_path, source=PANEL_SOURCE)
    assert _picker(out["held"]["rail"]), "picker never showed on the apply page"
    assert _picker(out["settled"]["rail"]), "the form-less page was refused"
    # And the second page did not re-ask for what the first one already holds.
    assert len(_list_gets(out)) == 1


def test_a_chrome_page_is_offered_nothing_and_asks_for_nothing(tmp_path):
    """THE NON-WEB GUARD, both halves, and the one the dropped form gate was
    incidentally doing.

    Tab A is the apply page that fetched the drafts; tab B is `chrome://
    settings`. The list SURVIVES the switch (it is not a fact about a posting),
    and `onTab` repaints on arrival — so with nothing refusing it the panel
    would offer five drafts on a settings screen, and a pick there would arm
    the rail against a tab that has no tenant to scope it to and no form to
    fill. `isWebPage` is the refusal, on both the load side (no second GET) and
    the paint side (no rows).
    """
    spec = _on_apply(switchTo=42, tabUrls={"42": "chrome://settings"})
    out = run_node(_LIST_RACE_DRIVER_JS, spec, tmp_path, source=PANEL_SOURCE)
    assert _picker(out["held"]["rail"]), "picker never showed on the apply page"
    assert _picker(out["settled"]["rail"]) is None
    assert len(_list_gets(out)) == 1, "a chrome:// tab asked the backend for drafts"


def test_a_greenhouse_pick_is_refused_on_a_sibling_tenant(tmp_path):
    """job-boards.greenhouse.io serves both companies from ONE origin, so
    origin cannot scope this memory. A hardcoded tenant, or one taken from a
    different posting, restores here — the 2026-08-16 bleed. Workday hosts
    differ by company (the Globex test's origin guard does that work); this
    is the case where tenant is the only guard that can.
    """
    picked = _pick(tmp_path, tabs=[{"id": 7, "url": LIGHTNING_APPLY_URL}], api={
        "lightningai": _reply({"match": "none", "job": None, "application": None}),
        "GET /api/applications?": _reply(_drafts()),
        "/api/base-resumes": _reply(BASE_RESUMES),
        "/api/ats-scores": _reply(SCORES),
        "GET /api/applications/app-1": _reply({
            "id": "app-1", "pdf_path": "renders/app-1.pdf", "status": "draft",
        }),
    })
    writes = _session_writes(picked)
    assert writes, "the pick never wrote widget.session"
    out = _load(
        tmp_path,
        tabs=[{"id": 7,
               "url": "https://job-boards.greenhouse.io/cohere/jobs/99/apply"}],
        page=HAS_FORM,
        stored={"widget.session": writes[-1]["widget.session"]},
        api={
            "cohere": _reply({"match": "none", "job": None, "application": None}),
            "GET /api/applications?": _reply(_drafts()),
            "/api/base-resumes": _reply(BASE_RESUMES),
            "/api/ats-scores": _reply(SCORES),
        })
    assert _by_class(out["regions"]["identity"], "chip")[0]["text"] == "New"
    hrefs = [n.get("href") or "" for n in _by_class(out["regions"]["identity"], "linkish")]
    assert all("/applications/app-1" not in href for href in hrefs)


# ---------- the late form: a bounded re-ask, and what a yes has to reach ----------
#
# Detection ran ONCE, at tab-bind. A Workday apply page has not rendered its
# form at that moment, so the verdict froze at false for as long as the panel
# stayed bound (elevancehealth.wd1, console-verified 2026-08-18: a full visible
# form reading `hasForm: false`).
#
# WHAT A LATE YES REACHES, now that the picker does not wait for one: the FILL
# stage. `hasForm` feeds exactly one reader — `stageFor`'s `fillFromBase` — so
# a user who has armed a base resume is standing at Job until the form appears
# and at Fill afterwards, and the re-ask is the only thing that ever moves
# them. The picker's own tests are above and deliberately do not appear here.
#
# TIMERS ARE COLLAPSED by the harness and the requested delays recorded in
# `delays` — see its note. The claims here are the sequence, the count and the
# schedule's shape; none of them is a wall-clock claim.

NO_FORM = _reply({"tier": "A", "form": False, "score": 0})
A_FORM = _reply({"tier": "B", "form": True, "score": 2})


def _detects(out):
    """Every detection ask, in order. One per attempt, first and retries alike."""
    return [msg for msg in out["sent"]
            if msg["type"] == "panel_frame0"
            and (msg.get("message") or {}).get("type") == "detect_page"]


# Snapshots the tree at the moment each detection answer arrives, BEFORE the
# panel has reacted to it. That ordering is the cascade's evidence: the picker
# is absent in the frame the late `form: true` lands in and present after it,
# with nothing in between but the panel's own reaction — this driver never
# clicks anything, never fires a navigation and never switches tabs.
_DETECT_DRIVER_JS = _PANEL_FAKES_JS + r"""
const snaps = [];
const innerSend = chrome.runtime.sendMessage;
chrome.runtime.sendMessage = async (msg) => {
  const reply = await innerSend(msg);
  if (msg.type === "panel_frame0" && msg.message?.type === "detect_page") {
    snaps.push(regions());
  }
  return reply;
};
loadModules();
main(async () => {
  await settle();
  emit({ regions: regions(), snaps, delays, sent, writes });
});
"""


def _detect(tmp_path, **spec):
    return run_node(_DETECT_DRIVER_JS, _on_apply(**spec), tmp_path,
                    source=PANEL_SOURCE)


# A base resume armed on THIS tenant and no application behind it — the state
# the shortcut rung exists for. Acme's own origin and tenant, because
# `restorableSession` refuses an entry from anywhere else and a refused entry
# would leave `baseArmed` false, which is the fact this section drives.
def _armed_on_acme():
    return entry(applicationId=None, baseArmed=True, pdfReady=False,
                 jobId=None, company=None, title=None,
                 origin="https://acme.wd5.myworkdayjobs.com",
                 tenant=ACME_TENANT)


def test_a_workday_form_that_renders_late_still_reaches_the_fill_stage(tmp_path):
    """THE LIVE BUG, whole. The apply page answers no while the SPA is still
    fetching, then yes once the form is up. A user with a base armed has to end
    where a page that answered yes at once puts them: at Fill, ready to
    autofill from that base, rather than parked at Job in front of a form the
    panel refuses to admit exists.
    """
    out = _detect(tmp_path, page={"detect_page": [NO_FORM, A_FORM]},
                  stored={"widget.session": _armed_on_acme()})
    assert len(_detects(out)) == 2, "the second look never happened"
    assert _rows(_rail_rows({"regions": out["regions"]}))["fill"]["state"] == "active"


def test_the_late_yes_alone_arms_the_primary_and_moves_no_stage(tmp_path):
    """THE FLIP, with nothing else in the frame — and since 2026-08-19 it is
    the FOOTER that flips, not the rail.

    `snaps` is the tree as each detection answer arrived, taken before the
    panel had reacted to it. An armed base puts the user at Fill from the
    first paint now, because the stage is decided by whose question is still
    open and a page's form is not that; what the late `form: true` changes is
    what the step can DO. So the Fill row is active in every frame, the footer
    has no Start fill while the page has no form, and the button appears at the
    end — with nothing in between but the panel reading its own answer: this
    driver issues no click, no reload and no tab switch.

    THE STAGE NOT MOVING IS HALF THE CLAIM. A late verdict that shifted the
    rail would be stage navigation by accident, which is the one thing this
    design says it never does — and it is exactly what the old shape did on a
    page whose form arrived a second late.

    THE PICKER IS NOT WHAT THIS WATCHES ANY MORE, twice over. The old gate read
    `hasForm`, so a late yes had to reach the list LOADER; that gate went, and
    the offer now stands on any unmatched page whose stage is Job — which this
    one is not, because an armed base is a Fill-stage fact from the first
    paint. The drafts' independence from the form verdict is its own pair of
    tests above (`…_is_offered_the_drafts`), on a page with nothing armed.
    """
    out = _detect(tmp_path, page={"detect_page": [NO_FORM, A_FORM]},
                  stored={"widget.session": _armed_on_acme()})
    assert len(out["snaps"]) == 2
    # THE FRAME THE LATE YES LANDED IN, which is the one this test is about:
    # the rail is already at Fill (the first verdict's paint put it there,
    # because the arming alone did), and the footer is empty. THE PROBE: a
    # primary offered here would run a pass over a page with no fields in it.
    at_yes = out["snaps"][-1]
    assert _rows(_rail_rows({"regions": at_yes}))["fill"]["state"] == "active"
    assert _by_class(at_yes["foot"], "cta") == []
    assert _rows(_rail_rows({"regions": out["regions"]}))["fill"]["state"] == "active"
    [cta] = _by_class(out["regions"]["foot"], "cta")
    assert cta["text"] == "Start fill"
    assert cta["disabled"] is False
    # And no injection got us there: the page ANSWERED both times, and the
    # detect's injection rung reads a silence rather than a no.
    assert [m for m in out["sent"] if m["type"] == "panel_prepare"] == []


def test_a_page_that_never_grows_a_form_stops_asking(tmp_path):
    """THE BOUND, counted. Three retries on top of the first look and then it
    stops: a page still form-less seven seconds after it was bound is a
    posting, and an extension that kept asking would be the background poller
    the one-shot was written to refuse.

    The delays are the schedule's SHAPE — growing, over seconds rather than
    frames — and not its exact milliseconds, which are a judgement call this
    test has no business freezing.

    `delays` IS BOTH LADDERS' SLEEPS since the posting re-ask: the two draw from
    one constant (`PAGE_RETRY_MS`) and this page is at the Job stage, so the
    posting ladder runs beside the form one. It runs its schedule OUT here
    rather than stopping early, and that is the deliberate part: this apply page
    answers with no JD, and while nothing real has landed a repeated empty
    answer is a page that has not rendered rather than a page with nothing on
    it. Two full ladders, six wake-ups, three distinct values — asserted whole
    rather than filtered, because a merged list that grew would be a ladder that
    stopped stopping.
    """
    out = _detect(tmp_path, page={"detect_page": [NO_FORM]})
    assert len(_detects(out)) == 4, "the re-ask is unbounded"
    delays = out["delays"]
    assert len(delays) == 6              # two ladders, three rungs each
    assert len(set(delays)) == 3
    assert delays == sorted(delays)
    assert sum(delays) <= 20_000         # ≤10s per ladder, and they overlap


def test_a_page_that_never_grows_a_form_says_nothing_about_it(tmp_path):
    """AND IT COSTS THE USER NOTHING TO SAY SO. Most of the web has no form,
    so a schedule that ran out has nothing to report: the note slot is empty
    and the rail is where it was.

    "We asked four times and the page never grew a form" is a fact about our
    own looking, which is `loadHasForm`'s standing rule for what does not
    become a sentence.

    THE LIST IS NO LONGER PART OF THE QUIET. This used to assert that nothing
    was fetched, because a form-less page was not allowed to want the drafts;
    the offer now stands here and the fetch with it (see
    `test_a_page_that_answers_no_form_forever_is_offered_the_drafts`). What is
    still true is that a page which never grew a form is never TOLD so.
    """
    out = _detect(tmp_path, page={"detect_page": [NO_FORM]})
    assert _rows(_rail_rows({"regions": out["regions"]}))["job"]["state"] == "active"
    [note] = _by_class(out["regions"]["foot"], "note")
    assert note["text"] == ""
    assert note["class"] == "note"


def test_a_form_seen_at_once_is_never_asked_about_twice(tmp_path):
    """No retry chatter on a healthy page. Greenhouse renders its form in the
    first paint, so the answer arrives complete and the schedule never starts —
    the one round trip this cost before the retry existed."""
    out = _detect(tmp_path, stored={"widget.session": _armed_on_acme()})
    assert len(_detects(out)) == 1
    assert out["delays"] == []
    # The yes was believed on the spot: an armed base plus a form is Fill.
    assert _rows(_rail_rows({"regions": out["regions"]}))["fill"]["state"] == "active"


# The retry's answer, HELD. `spec.hold` cannot reach it — it names api paths
# and `page_broadcast` inner types — and holding the door itself would stall
# the FIRST ask, which is the one that has to answer before a retry is ever
# scheduled. So the hold is on the SECOND detection and no earlier.
_DETECT_RACE_DRIVER_JS = _PANEL_FAKES_JS + r"""
let releaseDetect = null;
let asked = 0;
const innerSend = chrome.runtime.sendMessage;
chrome.runtime.sendMessage = async (msg) => {
  if (!(msg.type === "panel_frame0" && msg.message?.type === "detect_page")) {
    return innerSend(msg);
  }
  asked += 1;
  const reply = await innerSend(msg);
  if (asked < 2) return reply;
  return new Promise((resolve) => { releaseDetect = () => resolve(reply); });
};
loadModules();
main(async () => {
  await settle();
  const held = regions();
  await onActivated({ tabId: spec.switchTo });
  await settle();
  // Named rather than crashed on: with no retry there is nothing held, and a
  // bare TypeError here reads as a broken harness instead of the absent
  // behaviour it actually is.
  if (!releaseDetect) throw new Error("no retry ask was held — the race never armed");
  releaseDetect();
  await settle();
  emit({ held, regions: regions(), sent, writes });
});
"""


def test_a_form_verdict_that_lands_after_you_switch_tabs_paints_nothing(tmp_path):
    """THE RACE, on the widest window this file has: seven seconds between the
    ask and its answer is the answer most likely to come back to a tab the user
    has left.

    Tab A is the Workday apply page whose form appears late, with a base armed
    on it; tab B is a settings page that has no form and never asked. Tab A's
    yes must not flip `hasForm` on tab B — which would hand a settings screen a
    Start fill for a page the extension cannot even reach — and must not draw a
    picker or fetch a list there.

    NOTHING FETCHES THE DRAFTS in this run, and that is a consequence of the
    stage change rather than a claim about tab B alone: an armed base puts tab
    A at Fill from the first paint, and the picker is a Job-stage cost. Any GET
    here would therefore be a list nobody's stage asked for.
    """
    spec = _on_apply(page={"detect_page": [NO_FORM, A_FORM]},
                     stored={"widget.session": _armed_on_acme()},
                     switchTo=42, tabUrls={"42": "chrome://settings"})
    out = run_node(_DETECT_RACE_DRIVER_JS, spec, tmp_path, source=PANEL_SOURCE)
    assert len(_detects(out)) == 2, "the retry never went out — the race is fake"
    assert _rows(_rail_rows({"regions": out["regions"]}))["job"]["state"] == "active"
    assert _picker(out["regions"]["rail"]) is None
    # THE PROBE this test exists for: tab A's late yes landing on tab B would
    # put a Start fill under a `chrome://` page. Tab B's own primary — Add job,
    # over an empty Job stage nothing ever loaded — is what belongs there.
    assert [cta["text"] for cta in _by_class(out["regions"]["foot"], "cta")] == [
        "Add job"]
    assert _list_gets(out) == []


# Switches tabs at the FIRST macrotask boundary — the whole boot is a chain of
# microtasks, so this lands with the backoff's first sleep still pending and
# nothing else in flight. `realSetTimeout` and not `settle`, which would drain
# the schedule before the switch could race it.
_DETECT_ABANDON_DRIVER_JS = _PANEL_FAKES_JS + r"""
loadModules();
main(async () => {
  await new Promise((resolve) => realSetTimeout(resolve, 0));
  await onActivated({ tabId: spec.switchTo });
  await settle();
  emit({ regions: regions(), sent, writes });
});
"""


def test_a_tab_you_have_left_is_not_asked_again(tmp_path):
    """The other half of the guard, and the one that costs messages rather
    than paint: `askDetect` names `card.tabId`, which the switch has already
    moved. A retry that woke up without checking would aim tab A's schedule at
    whatever tab the user landed on — three extra page reads per tab passed
    through, which is the always-on cost this whole path is written around.

    Tab B is a settings page, which asks nothing of its own — so every
    detection ask in the log must name tab 7, and one naming 42 could only be
    tab A's abandoned schedule.
    """
    spec = _on_apply(page={"detect_page": [NO_FORM]},
                     switchTo=42, tabUrls={"42": "chrome://settings"})
    out = run_node(_DETECT_ABANDON_DRIVER_JS, spec, tmp_path, source=PANEL_SOURCE)
    asked = _detects(out)
    assert asked, "nothing was detected at all — the driver switched too early"
    assert [msg["tabId"] for msg in asked if msg["tabId"] != 7] == []


# ---------- the late posting: the same re-ask, and whose characters win ----------
#
# THE THIRD ONE-SHOT-READ-AT-BIND BUG, and the same cure. Extraction ran ONCE,
# at tab-bind, and the empty answer a still-rendering SPA gave was then locked
# in by a guard that could not tell "the user has typed here" from "extraction
# has answered" (itron.wd5, live 2026-08-19: a full JD on screen under three
# empty boxes, and an Add job that refused to save them).
#
# TWO CAUSES, and the ladder alone only covers one of them. The other is an
# extension RELOAD, which orphans the content scripts in every already-open tab:
# the page is long since rendered, every ask comes back silent, and no schedule
# can out-wait a script that is not running (elevancehealth.wd1 and philips.wd3,
# live the same day, on pages that had extracted correctly earlier). That is
# what the injection rung is for, and why the tests below are careful about the
# difference between a page that answered EMPTY and a page that did not answer.
#
# WHAT EACH TEST WOULD CATCH is named in its docstring, because five separable
# guards live in ~40 lines here: the ladder, the user-edit discriminator, the
# better-replaces-worse rule, the two token checks, and the once-per-page
# injection bound.

# The page as a slow SPA answers it: reachable, rendered enough to talk, with
# nothing on it yet. NOT silence — that is the orphan case below, and the whole
# point of these two fixtures is that they are different states.
SHELL_POSTING = _reply({"url": POSTING_URL, "title": "Careers",
                        "text": "Loading…", "source": "body"})
# What `panel_frame0` answers when nothing in the tab is listening.
NO_ANSWER = {"ok": False, "error": "no frame answered"}
PREPARED = _reply({"injected": True})
RELOAD_LINE = "The companion cannot see this page — reload the tab."


def _extracts(out):
    """Every extraction ask, in order — first attempt, injection re-ask and
    retries alike."""
    return [msg for msg in out["sent"]
            if msg["type"] == "panel_frame0"
            and (msg.get("message") or {}).get("type") == "extract_job_posting"]


def _prepares(out):
    return [msg for msg in out["sent"] if msg["type"] == "panel_prepare"]


def _sub(out):
    """The one line under the preview."""
    return _by_class(out["regions"]["rail"], "sub")[0]["text"]


_POSTING_LADDER_DRIVER_JS = _PANEL_FAKES_JS + r"""
loadModules();
main(async () => {
  await settle();
  emit({ regions: regions(), delays, sent });
});
"""


def _posting_page(**spec):
    """A posting URL the backend does not recognise, with the form question
    already answered so the only schedule running is the posting's own.

    `detect_page` says YES deliberately: a no would start the FORM ladder too,
    and `delays` cannot tell two ladders' sleeps apart. A form with no base
    armed still leaves the user at the Job stage, which is where the preview is.
    """
    spec.setdefault("tabs", [{"id": 7, "url": POSTING_URL}])
    spec.setdefault("replies", {"read_settings": SETTINGS_REPLY,
                                "panel_prepare": PREPARED})
    spec["page"] = {"detect_page": A_FORM, **spec.pop("page", {})}
    spec.setdefault("api", {"lightningai": _reply(
        {"match": "none", "job": None, "application": None})})
    return spec


def _posting(tmp_path, **spec):
    return run_node(_POSTING_LADDER_DRIVER_JS, _posting_page(**spec), tmp_path,
                    source=PANEL_SOURCE)


def test_a_workday_posting_that_renders_late_still_fills_the_preview(tmp_path):
    """THE LIVE BUG, whole. The page answers with its own shell while the SPA is
    still fetching the description, then with the posting once it is up. The
    user does nothing, and the preview has to end where a page that answered
    completely at once puts it: three filled boxes over a real word count, and
    an Add job that has something to save.

    The early answer is NOT empty, which is the detail that decides the design:
    `extractJobPosting` falls back to `document.body.innerText`, so a page
    caught mid-render answers with a small WRONG posting rather than with none.
    A rule that only replaced an empty preview would leave this exactly as
    broken as it was.
    """
    out = _posting(tmp_path,
                   page={"extract_job_posting": [SHELL_POSTING, POSTING_REPLY]})
    assert len(_extracts(out)) >= 2, "the second look never happened"
    assert _preview_inputs(out["regions"]["rail"]) == {
        "title": "Machine Learning Engineer",
        "company": "Lightning AI",
        "location": "Remote, US",
    }
    assert _sub(out) == "JD grabbed from this page · 11 words"


EMPTY_ANSWER = _reply({"url": POSTING_URL, "title": "Careers",
                       "text": "", "source": "body"})


def test_a_page_that_answers_empty_is_re_asked_and_never_injected_into(tmp_path):
    """THE DISCRIMINATOR, in the direction that is easiest to collapse.

    This is the Workday case as it was finally measured live (philips.wd3,
    2026-08-19): the content scripts were alive and answering, the JD simply was
    not on the page yet, so the bind-time read came back ANSWERED-EMPTY. The
    ladder is the whole cure for it.

    Injection is not, and must not fire: the page is talking to us. A rung that
    read an empty answer as "our scripts are missing" would inject into every
    ordinary non-posting page on the web — the always-on cost this path is
    written around — and would tell the user to reload a tab that is working.
    """
    out = _posting(tmp_path,
                   page={"extract_job_posting": [EMPTY_ANSWER, POSTING_REPLY]})
    assert _prepares(out) == [], "an answered page was injected into"
    assert _preview_inputs(out["regions"]["rail"])["title"] == (
        "Machine Learning Engineer")
    assert _sub(out) == "JD grabbed from this page · 11 words"


def test_a_posting_that_arrives_two_rungs_late_still_lands(tmp_path):
    """THE LIVE TIMELINE, and the reason the ladder does not stop at the first
    answer that failed to improve.

    The page answers empty at bind AND at the 1s rung, and renders its JD
    somewhere before 2s. Under a ladder that read two identical empties as "the
    page has settled", the schedule ended at 1s and the preview stayed empty —
    the Itron failure, unchanged, with a re-ask in front of it. A page that has
    given us NOTHING has not settled; it has not rendered.

    Four asks over three sleeps are the evidence that the second rung was
    reached at all: with the early stop this is `EXTRACTS: 2, DELAYS: [1000]`.
    The fourth is the rung after the landing, which comes back no better and
    stops the schedule — the same one extra read a page that answered at once
    costs.
    """
    out = _posting(tmp_path, page={"extract_job_posting": [
        EMPTY_ANSWER, EMPTY_ANSWER, POSTING_REPLY]})
    assert len(_extracts(out)) == 4, "the ladder quit before its second rung"
    assert len(out["delays"]) == 3   # the schedule ran to its last rung
    assert _preview_inputs(out["regions"]["rail"]) == {
        "title": "Machine Learning Engineer",
        "company": "Lightning AI",
        "location": "Remote, US",
    }
    assert _sub(out) == "JD grabbed from this page · 11 words"


# The same page read the other way: no JSON-LD found this time, so the
# extraction falls through to `document.body.innerText` — the posting PLUS the
# nav, the cookie bar and the footer. LONGER than the described posting and
# strictly worse.
BODY_NOISE = _reply({"url": POSTING_URL, "title": "Careers", "source": "body",
                     "text": "Home Jobs Login Cookies " + ("noise " * 200)})


def test_a_heavier_answer_from_a_worse_source_never_replaces_the_described_posting(
        tmp_path):
    """PROVENANCE OUTRANKS SIZE, and this is a race the reviewer built rather
    than a hypothetical: same url, same page, one rung apart.

    `extractJobPosting` prefers a schema.org JobPosting and falls back to the
    visible content. When the JSON-LD read wins first and a retry falls through
    to the body, the second answer is several times longer and made of nav — so
    a size-only rule takes the three filled header boxes back out, replaces a
    real JD with chrome, and reports it as a successful grab.
    """
    out = _posting(tmp_path,
                   page={"extract_job_posting": [POSTING_REPLY, BODY_NOISE]})
    assert _preview_inputs(out["regions"]["rail"]) == {
        "title": "Machine Learning Engineer",
        "company": "Lightning AI",
        "location": "Remote, US",
    }
    assert _sub(out) == "JD grabbed from this page · 11 words"


def test_a_page_that_starts_answering_takes_back_the_reload_sentence(tmp_path):
    """THE OTHER HALF OF `unreachable`, and it is a dead end without this: an
    unreachable preview weighs nothing, so an ANSWER that also found nothing
    could never replace it under a size rule (0 is not more than 0) and the
    panel would go on telling the user to reload a tab that had started talking
    to it.

    A page that answers has told us at least one thing — that we can reach it —
    and that is a fact `sourceRank` carries: any source outranks no source.

    THE UNREACHABLE PREVIEW HAS TO LAND FIRST, which is what the third fixture
    entry buys: silence at bind AND after the injection is what WRITES the
    reload sentence, and only then can a later answer be tested against it. With
    two entries the injection re-ask answered before anything had landed, the
    preview went straight from null to the answer, and the rule under test was
    never consulted — the whole assertion passed with the rank compare deleted.
    """
    out = _posting(tmp_path, page={"extract_job_posting": [
        NO_ANSWER, NO_ANSWER, EMPTY_ANSWER]})
    assert [msg["tabId"] for msg in _prepares(out)] == [7]
    assert _by_class(out["regions"]["rail"], "sub")[0]["text"] != RELOAD_LINE
    assert _sub(out) == "No job description found on this page."


def test_a_posting_read_completely_at_once_is_asked_about_once_more_and_no_further(
        tmp_path):
    """THE BOUND, and the cost of running the ladder on every Job-stage page.

    A page that answered completely says the same thing a second later, so the
    rung after the first answer comes back no better and the schedule stops
    there: one extra page read, one sleep. It does not stop at the FIRST answer
    the way the form ladder does — "it answered" and "it answered with the
    posting" are different facts for an extraction — and that judgement is what
    this test freezes, in both directions.
    """
    out = _posting(tmp_path, page={"extract_job_posting": [POSTING_REPLY]})
    assert len(_extracts(out)) == 2
    assert len(out["delays"]) == 1
    assert _preview_inputs(out["regions"]["rail"])["title"] == (
        "Machine Learning Engineer")


def test_a_worse_answer_arriving_late_replaces_nothing(tmp_path):
    """The other direction, and the one that would be a REGRESSION rather than a
    missing fix: a page that has already given up its posting and then answers
    with a shell — an SPA navigating away under the ladder, a frame mid-teardown
    — must not blank a preview that was already right.

    The ladder stops on that answer too: an answer that did not improve is the
    signal that the page has said what it has to say."""
    out = _posting(tmp_path,
                   page={"extract_job_posting": [POSTING_REPLY, SHELL_POSTING]})
    assert _preview_inputs(out["regions"]["rail"]) == {
        "title": "Machine Learning Engineer",
        "company": "Lightning AI",
        "location": "Remote, US",
    }
    assert _sub(out) == "JD grabbed from this page · 11 words"
    assert len(_extracts(out)) == 2, "the ladder went on after a worse answer"


# The user types while the SECOND extraction is IN FLIGHT: the answer is already
# on its way back when the first character lands, which is the moment the old
# `card.preview !== null` guard could not see and the one the fix has to survive.
_POSTING_TYPING_DRIVER_JS = _PANEL_FAKES_JS + r"""
const type = (edits) => {
  const inputs = {};
  const walk = (node) => {
    if (node.tagName === "INPUT" && String(node.id).startsWith("preview-")) {
      inputs[node.id.slice("preview-".length)] = node;
    }
    for (const kid of node.children) walk(kid);
  };
  walk(REGIONS.rail);
  for (const [key, text] of Object.entries(edits)) {
    if (!inputs[key]) throw new Error(`no preview input for "${key}"`);
    inputs[key].value = text;
    inputs[key].dispatch("input");
  }
};
let asked = 0;
const innerSend = chrome.runtime.sendMessage;
chrome.runtime.sendMessage = async (msg) => {
  const extract = msg.type === "panel_frame0"
                  && msg.message?.type === "extract_job_posting";
  const reply = await innerSend(msg);
  if (extract && (asked += 1) === spec.typeOnAsk) type(spec.type);
  return reply;
};
loadModules();
main(async () => {
  await settle();
  emit({ regions: regions(), sent, delays });
});
"""


def test_a_late_answer_never_takes_back_a_character_you_typed(tmp_path):
    """THE USER-EDIT DISCRIMINATOR, pinned at the only moment it matters.

    The first answer is a shell, so the boxes are empty and correcting them by
    hand is exactly what a user would do; the good answer is already in flight
    when they start. It must not land — not the title they are typing over, and
    not the two boxes they have not reached yet, because a partial merge would
    rewrite the fields around the cursor while someone is working in it.

    AND THE LADDER STOPS. Every later write is refused once this flag is set, so
    a schedule that kept asking would be spending page reads on answers it has
    already decided to throw away.
    """
    spec = _posting_page(page={"extract_job_posting": [SHELL_POSTING, POSTING_REPLY]},
                         typeOnAsk=2, type={"title": "Staff ML Engineer"})
    out = run_node(_POSTING_TYPING_DRIVER_JS, spec, tmp_path, source=PANEL_SOURCE)
    assert len(_extracts(out)) == 2, "the answer that races the typing never came"
    assert _preview_inputs(out["regions"]["rail"]) == {
        "title": "Staff ML Engineer", "company": "", "location": ""}


# The retry's answer, HELD: `spec.hold` names api paths and `page_broadcast`
# types, and holding the door itself would stall the FIRST ask — the one that
# has to answer before a retry is ever scheduled. `_DETECT_RACE_DRIVER_JS`'s
# shape, aimed at the other frame-0 question.
_POSTING_RACE_DRIVER_JS = _PANEL_FAKES_JS + r"""
let releaseExtract = null;
let asked = 0;
const innerSend = chrome.runtime.sendMessage;
chrome.runtime.sendMessage = async (msg) => {
  if (!(msg.type === "panel_frame0" && msg.message?.type === "extract_job_posting")) {
    return innerSend(msg);
  }
  asked += 1;
  const reply = await innerSend(msg);
  if (asked < 2) return reply;
  return new Promise((resolve) => { releaseExtract = () => resolve(reply); });
};
loadModules();
main(async () => {
  await settle();
  await onActivated({ tabId: spec.switchTo });
  await settle();
  if (!releaseExtract) throw new Error("no retry ask was held — the race never armed");
  releaseExtract();
  await settle();
  emit({ regions: regions(), sent });
});
"""


def test_a_posting_that_lands_after_you_switch_tabs_paints_nothing(tmp_path):
    """THE TOKEN CHECK BEFORE THE WRITE. Tab A is a job posting whose good
    answer is still in flight; tab B is a settings page, which reads nothing and
    has no posting of its own. Tab A's answer must not land there — a settings
    screen showing "Machine Learning Engineer · Lightning AI" over an Add job
    button is the confident lie about the page in front of the user that
    `resetPageFacts` exists to prevent, and it would be SAVED under tab B's url.
    """
    spec = _posting_page(page={"extract_job_posting": [SHELL_POSTING, POSTING_REPLY]},
                         switchTo=42, tabUrls={"42": "chrome://settings"})
    out = run_node(_POSTING_RACE_DRIVER_JS, spec, tmp_path, source=PANEL_SOURCE)
    assert len(_extracts(out)) == 2, "the retry never went out — the race is fake"
    assert _preview_inputs(out["regions"]["rail"]) == {
        "title": "", "company": "", "location": ""}


def test_a_tab_you_have_left_is_not_asked_for_its_posting_again(tmp_path):
    """THE TOKEN CHECK BEFORE THE ASK, which costs messages rather than paint:
    `askPosting` names `card.tabId` and the switch has already moved it, so a
    rung that woke up unchecked would read the page the user just landed on —
    and, on a tab that has no scripts, inject into it as well."""
    spec = _posting_page(page={"extract_job_posting": [SHELL_POSTING]},
                         switchTo=42, tabUrls={"42": "chrome://settings"})
    out = run_node(_DETECT_ABANDON_DRIVER_JS, spec, tmp_path, source=PANEL_SOURCE)
    asked = _extracts(out)
    assert asked, "nothing was extracted at all — the driver switched too early"
    assert [msg["tabId"] for msg in asked if msg["tabId"] != 7] == []
    assert [msg["tabId"] for msg in _prepares(out) if msg["tabId"] != 7] == []


def test_a_tab_whose_scripts_were_orphaned_is_prepared_once_and_then_answers(
        tmp_path):
    """THE SECOND LIVE CAUSE. An extension reload leaves every open tab with no
    listener in it, so the ask comes back silent on a page that is fully
    rendered and plainly a posting. No schedule fixes that — nothing is running
    to answer the next question either — so the panel spends this page's one
    injection and asks again.

    Without the rung the user's only cure is reloading a tab they have no reason
    to suspect, which is the whole reason this is not left to the ladder.
    """
    out = _posting(tmp_path,
                   page={"extract_job_posting": [NO_ANSWER, POSTING_REPLY]})
    assert [msg["tabId"] for msg in _prepares(out)] == [7]
    assert _preview_inputs(out["regions"]["rail"])["company"] == "Lightning AI"
    assert _sub(out) == "JD grabbed from this page · 11 words"


def test_a_page_that_never_answers_is_injected_into_once_and_told_the_truth(
        tmp_path):
    """WHAT IS LEFT WHEN THE CURE DOES NOT WORK — a `file://` page, a tab we
    have no host permission for, a viewer with no document to inject into.

    TWO CLAIMS, and they are the two halves of the honesty rule. The sentence
    says what the panel actually knows: it could not read this page. "No job
    description found on this page" is a claim ABOUT THE PAGE and would be a
    guess here — the same page in a reloaded tab has a full JD on it — and it
    sends the user looking for a posting problem that does not exist.

    And the injection stays at ONE. Every ask on this page comes back silent, so
    a rung that prepared per attempt would re-inject on each of them; the bound
    lives in `preparePage` rather than at its call site precisely so a second
    caller cannot lose it.
    """
    out = _posting(tmp_path, page={"extract_job_posting": [NO_ANSWER]})
    assert len(_extracts(out)) > 1, "nothing re-asked — the bound is untested"
    assert [msg["tabId"] for msg in _prepares(out)] == [7]
    assert _sub(out) == RELOAD_LINE
    # Still not a fault: the note slot is for what the user just asked for.
    [note] = _by_class(out["regions"]["foot"], "note")
    assert note["text"] == ""


# The user does what the sentence asked: they reload the tab. Chrome sends
# `changeInfo.url` only when the ADDRESS changes, so a same-url reload arrives
# as a bare status pair — `{status: "loading"}` and then `{status: "complete"}` —
# and the panel's url-shaped listener never saw either. The fixture is swapped
# between the two loads because that is what the reload changes: the same page,
# now with our content scripts in it.
_RELOAD_DRIVER_JS = _PANEL_FAKES_JS + r"""
loadModules();
main(async () => {
  await settle();
  const before = regions();
  const askedBefore = sent.filter(
    (m) => m.type === "panel_frame0" && m.message?.type === "extract_job_posting").length;
  if (spec.afterReload) spec.page.extract_job_posting = spec.afterReload;
  for (const changeInfo of spec.updates) await onUpdated(spec.onTab ?? 7, changeInfo);
  await settle();
  emit({ before, askedBefore, regions: regions(), sent, delays });
});
"""


def _reload(tmp_path, updates, **spec):
    spec = _posting_page(**spec)
    spec["updates"] = updates
    return run_node(_RELOAD_DRIVER_JS, spec, tmp_path, source=PANEL_SOURCE)


def test_reloading_the_tab_the_panel_asked_you_to_reload_reads_the_posting_again(
        tmp_path):
    """THE ADVICE, FOLLOWED. Without this the sentence is a dead end: the reload
    changes no url, so `onTab` never runs; the ladder ran out seconds ago; and
    the fresh content scripts sit in the page with nobody asking them anything.
    The user did exactly what they were told and the panel goes on saying it
    cannot see the page.

    `{status: "complete"}` on the BOUND tab is the whole trigger, and the load
    that follows is the ordinary one — same ladder, same guards.
    """
    out = _reload(tmp_path, [{"status": "loading"}, {"status": "complete"}],
                  page={"extract_job_posting": [NO_ANSWER]},
                  afterReload=POSTING_REPLY)
    assert out["before"]["rail"] and _by_class(
        out["before"]["rail"], "sub")[0]["text"] == RELOAD_LINE
    assert _preview_inputs(out["regions"]["rail"])["company"] == "Lightning AI"
    assert _sub(out) == "JD grabbed from this page · 11 words"


def test_a_page_that_answered_is_not_re_read_every_time_a_load_completes(tmp_path):
    """THE BOUND ON THE HEALING, and it is what keeps this from being a cost on
    every navigation. `complete` also arrives at the end of a load `onTab` has
    already handled, and most of the web answers with a posting-less page — so a
    trigger of "the preview is empty" would run a second full ladder on every
    ordinary page the user visits.

    Only a page that told us NOTHING gets re-read. This one answered — it simply
    had no posting on it — so the completed load costs nothing at all.
    """
    out = _reload(tmp_path, [{"status": "complete"}],
                  page={"extract_job_posting": [EMPTY_ANSWER]})
    assert len(_extracts(out)) == out["askedBefore"], "the page was re-read for nothing"
    assert _sub(out) == "No job description found on this page."


def test_a_load_completing_in_a_tab_you_are_not_bound_to_is_not_read(tmp_path):
    """`onUpdated` fires for every tab in the window. A completed load in a tab
    the panel is not bound to must not start a read — the ask would name
    `card.tabId`, so it would be this tab's schedule pointed at another tab's
    page, and the answer would land in the bound tab's preview."""
    out = _reload(tmp_path, [{"status": "complete"}], onTab=99,
                  page={"extract_job_posting": [NO_ANSWER]},
                  afterReload=POSTING_REPLY)
    assert len(_extracts(out)) == out["askedBefore"]
    assert _sub(out) == RELOAD_LINE


# ---------- what a re-pick has to let go of ----------

_REPICK_DRIVER_JS = _PANEL_FAKES_JS + r"""
const ns = loadModules();
main(async () => {
  await settle();
  // THE ACTION, DRIVEN DIRECTLY over the same handle the roster hands it, and
  // deliberately not through the rail: picking an application moves the stage
  // off Job, so the picker that made the pick is no longer on screen — there is
  // no rendered route from "an attach happened" back to a second pick, and a
  // test built on one would be testing a path the panel does not have. What is
  // under test is the action's WRITE SET, which is where the bug lives.
  const store = ns.panel.actionStore();
  const actions = ns.panelActions(store);
  store.write({
    applications: spec.drafts,
    // The state a completed attach leaves behind on this page.
    attached: { filename: "app-1-tailored.pdf", count: 1 },
    fileInputs: 1,
  });
  await actions.pickApplication(spec.pick);
  await settle();
  const after = store.read();
  emit({ attached: after.attached, fileInputs: after.fileInputs,
         application: after.application });
});
"""


def test_picking_a_different_application_lets_go_of_the_attach(tmp_path):
    """The attach belonged to the application being replaced.

    Left standing, the Fill row goes on reporting the OLD application's filename
    as attached to this page — and because the offer disappears once something
    is attached, the newly picked application's PDF cannot be attached at all
    without reloading the page.

    `fileInputs` DELIBERATELY SURVIVES, and the split is the whole point: how
    many upload boxes this page has is a fact about the PAGE, which has not
    changed. Clearing it would hide the offer the user now needs.
    """
    out = run_node(_REPICK_DRIVER_JS,
                   {"tabs": [{"id": 7, "url": APPLY_URL}], "page": HAS_FORM,
                    "api": _picker_api(), "replies": {"read_settings": SETTINGS_REPLY},
                    "drafts": _drafts(), "pick": "app-1"},
                   tmp_path, source=PANEL_SOURCE)
    assert out["application"]["id"] == "app-1"
    assert out["attached"] is None
    assert out["fileInputs"] == 1


# ---------- un-pick / re-pick: a claim can be withdrawn ----------
#
# A pick arms the rail and the session bridge. Without a door back, picking the
# wrong draft is a trap: the picker never re-offers, and every later page of
# the wizard re-arms the mistake. Un-picking is not un-saving — the draft
# stays in the backend; only this panel's binding to this page changes.

_UNPICK_DRIVER_JS = _PANEL_FAKES_JS + r"""
const findTag = (node, tag) => [
  ...(node.tagName === tag ? [node] : []),
  ...node.children.flatMap((kid) => findTag(kid, tag)),
];
const opener = (key) => findById(REGIONS.rail, `stg-open-${key}`);
const ns = loadModules();
main(async () => {
  await settle();
  const loaded = regions();
  const sel = findTag(REGIONS.rail, "SELECT")[0];
  const drafts = sel ? sel.children.filter((opt) => opt.value) : [];
  if (drafts[0]) {
    sel.value = drafts[0].value;
    sel.dispatch("change");
  }
  await settle();
  const armed = regions();
  const armedFacts = ns.panel.actionStore().read();
  const door = opener("job");
  if (door) door.click();
  await settle();
  const reopened = regions();
  if (spec.switchDraft) {
    const again = findTag(REGIONS.rail, "SELECT")[0];
    const next = (again ? again.children.filter((opt) => opt.value) : [])
      .find((opt) => opt.value === spec.switchDraft);
    if (next) {
      again.value = next.value;
      again.dispatch("change");
    }
    await settle();
    emit({ loaded, armed, reopened, switched: regions(), writes, sent });
    return;
  }
  const stop = withClass(REGIONS.rail, "unpick")[0];
  if (stop) stop.click();
  await settle();
  const unbound = regions();
  const unboundFacts = ns.panel.actionStore().read();
  emit({ loaded, armed, reopened, unbound, writes, sent,
         armedFacts: {
           claimed: armedFacts.claimed === true,
           applicationId: armedFacts.application?.id ?? null,
           baseSlug: armedFacts.baseSlug,
           match: armedFacts.match,
         },
         unboundFacts: {
           claimed: unboundFacts.claimed === true,
           application: unboundFacts.application,
           job: unboundFacts.job,
           match: unboundFacts.match,
           pdfReady: unboundFacts.pdfReady,
           evidence: unboundFacts.evidence,
           scores: unboundFacts.scores,
           baseSlug: unboundFacts.baseSlug,
           baseSelected: unboundFacts.baseSelected,
           attached: unboundFacts.attached,
           fileInputs: unboundFacts.fileInputs,
           preview: unboundFacts.preview,
         } });
});
"""


def _unpick(tmp_path, **spec):
    spec = _on_apply(**spec)
    return run_node(_UNPICK_DRIVER_JS, spec, tmp_path, source=PANEL_SOURCE)


def test_a_claimed_job_row_is_a_door_a_backend_match_is_not(tmp_path):
    """The reopen door is for a CLAIM, not for every done Job row.

    A pick the user made is theirs to withdraw. A backend exact-match is the
    page being that posting — the web app is where a wrong JD gets fixed, and
    this row gets no door.
    """
    picked = _unpick(tmp_path)
    assert "stg-open-job" in [n["id"] for n in _walk(picked["armed"]["rail"])]
    matched = _load(tmp_path, tabs=[{"id": 7, "url": APPLY_URL}], page=HAS_FORM, api={
        "myworkdayjobs": _reply({"match": "exact", "job": LIGHTNING_JOB,
                                 "application": {"id": "app-from-backend",
                                                 "status": "draft"}}),
        "GET /api/applications?": _reply(_drafts()),
        "/api/base-resumes": _reply(BASE_RESUMES),
        "/api/ats-scores": _reply(SCORES),
        "GET /api/applications/app-from-backend": _reply(
            {"pdf_path": "r.pdf", "status": "draft"}),
    })
    assert "stg-open-job" not in [n["id"] for n in _walk(matched["regions"]["rail"])]


def test_reopening_a_claimed_job_shows_the_binding_the_picker_and_a_way_out(tmp_path):
    """The reopened body is how you take the claim back, not the preview
    inputs — those are meaningless over a draft already saved elsewhere.
    """
    out = _unpick(tmp_path)
    body = next(n for n in _walk(out["reopened"]["rail"]) if n.get("id") == "stg-body-job")
    shown = _text(body)
    assert "Acme 1" in shown
    assert "Research Engineer 1" in shown
    assert "draft" in shown.lower()
    assert "Stop using this draft" in shown
    assert _picker(body) is not None
    # Preview fields belong to unmatched Job, not to a claimed binding.
    assert [n for n in _walk(body) if n["tag"] == "INPUT"] == []
    # The footer's Add job would offer to save a job the row has just ticked.
    assert _by_class(out["reopened"]["foot"], "cta") == []


def test_stop_using_this_draft_unbinds_the_page_and_rewrites_the_bridge(tmp_path):
    """Un-pick is a store-and-bridge operation: the draft is untouched in
    the backend; this page is no longer bound to it. The rail falls back to
    unmatched Job with the picker offered, and the session entry is
    application-less so the next page load cannot re-arm the withdrawn claim.
    """
    out = _unpick(tmp_path)
    facts = out["unboundFacts"]
    assert facts["application"] is None
    assert facts["job"] is None
    assert facts["claimed"] is False
    assert facts["match"] != "exact"
    assert facts["pdfReady"] is False
    assert facts["evidence"] is None
    # The rankings go with them, and this line arrived with the shared
    # write-set: the scores on screen were computed against the job this claim
    # named, so a ranking left behind is a number about a posting the panel is
    # no longer bound to. (Dropping `scores` from `UNBOUND` in actions/pick.js
    # is invisible without it — the driver has always emitted the field and
    # nothing read it.)
    assert facts["scores"] is None
    # Page facts and the base choice survive: un-picking is not un-saving
    # and not forgetting which resume they already picked for this posting.
    assert facts["baseSlug"] == "ai_ml_engineer"
    assert facts["baseSelected"] is True
    rows = _rows(_rail_rows({"regions": out["unbound"]}))
    assert rows["job"]["state"] == "active"
    assert _picker(out["unbound"]["rail"]) is not None
    writes = _session_writes(out)
    assert writes, "un-pick never rewrote widget.session"
    entry = writes[-1]["widget.session"]
    # `applicationId: null` IS the withdrawal, and it is the whole of it: the
    # entry carries no provenance field, so nothing else has to be cleared
    # and nothing else can contradict this.
    assert entry["applicationId"] is None
    assert "claimed" not in entry
    # Provenance stays off the wire on the way out too.
    for msg in out["sent"]:
        body = (msg.get("init") or {}).get("body") or ""
        assert "claimed" not in str(body)


def test_unpicking_stops_the_bridge_from_rearming_the_withdrawn_claim(tmp_path):
    """THE TRAP. Un-pick, then the next wizard step: restoreSession must not
    put the withdrawn draft back. An application-less entry is already legal
    and already carries the base choice.
    """
    unbound = _unpick(tmp_path)
    writes = _session_writes(unbound)
    assert writes[-1]["widget.session"]["applicationId"] is None
    out = _load(tmp_path, tabs=[{"id": 7, "url": APPLY_NEXT_URL}], page=HAS_FORM,
                stored={"widget.session": writes[-1]["widget.session"]},
                api=_picker_api())
    chips = [n["text"] for n in _by_class(out["regions"]["identity"], "chip")]
    assert chips == [] or all("Application" not in c for c in chips)
    assert _rows(_rail_rows(out))["job"]["state"] == "active"
    assert _picker(out["regions"]["rail"]) is not None


def test_switching_to_a_different_draft_from_the_reopened_job_is_a_pick(tmp_path):
    """Switch = the existing pickApplication on the new id. It already
    re-remembers, so the bridge follows the new claim.
    """
    api = _picker_api()
    api["GET /api/applications/app-2"] = _reply({
        "id": "app-2", "pdf_path": "renders/app-2.pdf", "status": "draft",
    })
    out = _unpick(tmp_path, switchDraft="app-2", api=api)
    writes = _session_writes(out)
    assert writes[-1]["widget.session"]["applicationId"] == "app-2"
    assert writes[-1]["widget.session"]["company"] == "Acme 2"
    chip = _by_class(out["switched"]["identity"], "chip")[0]["text"]
    assert chip == "Application · draft"



# ---------- the referent can die: a bridge that never re-validated ----------
#
# THE LIVE FINDING (2026-08-19): a draft deleted in the web app went on being
# shown by the panel — "Application · draft", the armed rail, an
# Open-application link landing on "This application no longer exists" —
# because `restoreSession` reads disk and asks nothing, and the detail GET that
# runs right after it swallowed every failure identically. What follows pins
# the whole discrimination, in both directions, at both sites.
#
# WHY BOTH DIRECTIONS ARE ONE SUBJECT: the bridge's tolerance of a failed read
# is deliberate — a wizard is six page loads and a flaky connection must not
# cost the user their pick — so the fix is not "verify harder", it is "know
# what a 404 means and what everything else does not". A test file that only
# pinned the forgetting would be one that welcomes a panel which forgets a real
# application every time the backend hiccups.


def _deleted_detail(api, application_id="app-1"):
    """Turn the detail GET for one draft into the backend's own 404.

    REPLACES the fixture's success needle rather than adding a second, for
    `test_the_bridge_survives_a_detail_get_that_fails`'s reason: the api map
    matches by substring in INSERTION order, so an appended key never fires.
    """
    needle = f"GET /api/applications/{application_id}"
    assert needle in api, "the fixture stopped answering this detail GET"
    api[needle] = {"ok": False, "error": "Application not found", "status": 404}
    return api


def _unreachable_detail(api, application_id="app-1"):
    """The same read failing with NOTHING to say — no HTTP answer, no status.

    This is what a sleeping service worker, a stopped backend and a dropped
    connection all look like by the time they reach the panel, and it is the
    shape the bridge is designed to survive.
    """
    needle = f"GET /api/applications/{application_id}"
    assert needle in api, "the fixture stopped answering this detail GET"
    api[needle] = {"ok": False, "error": "the backend is unreachable"}
    return api


def _acme_entry(**over):
    """The bridge entry a pick on the Acme apply page leaves behind.

    Built from the shared fixture (so the pre-R-C keys ride along and the
    upgrade path is exercised for free) with this file's tenant and this
    file's draft — `_picker_api`'s `app-1`, whose detail GET is the read every
    test below turns into one failure or another.
    """
    return entry(origin="https://acme.wd5.myworkdayjobs.com",
                 tenant=ACME_TENANT, applicationId="app-1", jobId="job-1",
                 company="Acme 1", title="Research Engineer 1", **over)


def _note(out_regions):
    [note] = _by_class(out_regions["foot"], "note")
    return note["text"]


def _claims_an_application(regions):
    """Does the identity strip still say this page is bound to a draft?

    BOTH HALVES, because the ghost had two and losing either one would leave
    the other lying on its own: the chip ("Application · draft") and the deep
    link, which is the half that actually took the user to the web app's
    "this application no longer exists".
    """
    chips = [node["text"] for node in _by_class(regions["identity"], "chip")]
    links = [node.get("href") or ""
             for node in _by_class(regions["identity"], "linkish")]
    return (any("Application" in chip for chip in chips)
            or any("/applications/" in href for href in links))


def _offered(regions):
    """The draft ids the picker is offering on this render, in its order."""
    return [option["value"] for option in _draft_options(_picker(regions["rail"]))]


DELETED_NOTE = "That draft no longer exists in Maestro CS."
# The list as it stands AFTER `app-1` is deleted in the web app. Named because
# three tests read the same world, and a list built inline in each of them is
# three chances to disagree about which draft went away.
SURVIVING_DRAFTS = [_draft(i) for i in range(2, 7)]


def test_a_restored_binding_whose_draft_was_deleted_is_let_go_of(tmp_path):
    """THE GOAL, end to end. Page 2 of the wizard restores the pick from the
    bridge; the detail GET the panel was making anyway comes back 404; the
    binding goes, the sentence is said once, and the rail falls back to
    unmatched Job with a freshly-read picker.

    The list is read here because THIS PAGE NEVER LOADED ONE — a first read,
    not a re-read (`card.applications === null` on a page restored from the
    bridge alone). A page that already holds a list keeps it, with the dead
    row FILTERED out by the drop; the cache is deliberately not dropped —
    the sibling test at the filter's own site pins that direction.
    """
    api = _deleted_detail(_picker_api())
    api["GET /api/applications?"] = _reply(SURVIVING_DRAFTS)
    out = _load(tmp_path, tabs=[{"id": 7, "url": APPLY_NEXT_URL}], page=HAS_FORM,
                stored={"widget.session": _acme_entry()}, api=api)
    assert not _claims_an_application(out["regions"]), (
        "the panel still claims an application the backend says is gone")
    assert _note(out["regions"]) == DELETED_NOTE
    rows = _rows(_rail_rows(out))
    assert rows["job"]["state"] == "active"
    assert rows["fill"]["state"] == "locked"
    # The way back is offered, and it offers what still exists.
    offered = _offered(out["regions"])
    assert offered, "the user was unbound and handed nothing to bind to"
    assert "app-1" not in offered


def test_the_deleted_draft_cannot_re_arm_itself_on_the_page_after(tmp_path):
    """THE TRAP, and the probe the `remember()` in the unbind exists for.

    Clearing the store alone leaves the entry naming the dead application on
    disk, and the very next wizard page restores it — the ghost is back, with
    its chip and its dead link, and this time nothing re-reads it because the
    panel has already spent its one detail GET on the page before.

    (Drop `store.remember()` from `dropDeletedApplication` and this test fails
    while every other one in this section still passes.)
    """
    api = _deleted_detail(_picker_api())
    api["GET /api/applications?"] = _reply(SURVIVING_DRAFTS)
    dropped = _load(tmp_path, tabs=[{"id": 7, "url": APPLY_NEXT_URL}],
                    page=HAS_FORM, stored={"widget.session": _acme_entry()}, api=api)
    writes = _session_writes(dropped)
    assert writes, "the unbind never rewrote the bridge"
    rewritten = writes[-1]["widget.session"]
    assert rewritten["applicationId"] is None
    # The page facts and the base choice survive the unbinding, exactly as
    # they do for a hand-made withdrawal: this is not un-saving anything.
    assert rewritten["tenant"] == ACME_TENANT
    assert rewritten["baseSlug"] == _acme_entry()["baseSlug"]

    # …and the next page, reading that entry, arms nothing.
    after = _load(tmp_path, tabs=[{"id": 7, "url": APPLY_URL}], page=HAS_FORM,
                  stored={"widget.session": rewritten}, api=_picker_api())
    assert not _claims_an_application(after["regions"])
    assert _rows(_rail_rows(after))["job"]["state"] == "active"


def test_a_restore_that_cannot_reach_the_backend_keeps_the_binding(tmp_path):
    """THE OPPOSITE MISTAKE, pinned as hard as the first one.

    The backend is not answering. That says NOTHING about whether the draft
    exists, and the bridge's whole reason for being is the user who keeps
    their pick across six wizard pages on a connection that drops. A panel
    that unbound here would forget a perfectly good application — silently,
    and precisely when the user can do least about it.

    (Widen the unbind to `if (err)` and this test fails immediately.)
    """
    out = _load(tmp_path, tabs=[{"id": 7, "url": APPLY_NEXT_URL}], page=HAS_FORM,
                stored={"widget.session": _acme_entry()},
                api=_unreachable_detail(_picker_api()))
    assert _by_class(out["regions"]["identity"], "chip")[0]["text"] == (
        "Application · draft")
    assert _note(out["regions"]) != DELETED_NOTE
    assert _session_writes(out) == [], (
        "an unreachable backend rewrote the bridge")
    # Still armed, so nothing offers a picker and nothing spends the list GET.
    assert _picker(out["regions"]["rail"]) is None
    assert _list_gets(out) == []


def test_a_server_error_on_the_restore_read_keeps_the_binding_too(tmp_path):
    """A 500 is the backend failing, not the application being gone. The panel
    tests the NUMBER rather than "the read failed", and this is the row that
    says so — a 5xx carries a status like a 404 does, and only one of them is
    an answer about the resource.
    """
    api = _picker_api()
    api["GET /api/applications/app-1"] = {
        "ok": False, "error": "Internal Server Error", "status": 500}
    out = _load(tmp_path, tabs=[{"id": 7, "url": APPLY_NEXT_URL}], page=HAS_FORM,
                stored={"widget.session": _acme_entry()}, api=api)
    assert _by_class(out["regions"]["identity"], "chip")[0]["text"] == (
        "Application · draft")
    assert _session_writes(out) == []


def test_picking_a_draft_the_list_no_longer_has_arms_nothing(tmp_path):
    """The second site: the list was read before somebody deleted a row, and
    the user picks that row.

    The bridge is still written BEFORE the await — that trade is unchanged and
    `test_the_bridge_survives_a_detail_get_that_fails` still pins it for every
    other failure — and then the 404 takes it back out, because an entry naming
    a deleted application is not a bridge, it is the ghost the next page arms
    from. The dead row leaves the picker with it, so the same pick cannot be
    made twice.
    """
    out = _pick(tmp_path, api=_deleted_detail(_picker_api()))
    writes = _session_writes(out)
    assert len(writes) >= 2, "the pick never wrote, or never took back, a bridge"
    assert writes[0]["widget.session"]["applicationId"] == "app-1", (
        "the pre-await remember stopped happening — that is a different trade")
    assert writes[-1]["widget.session"]["applicationId"] is None
    settled = out["settled"]
    assert _note(settled) == DELETED_NOTE
    assert not _claims_an_application(settled)
    assert _rows(_rail_rows({"regions": settled}))["job"]["state"] == "active"
    offered = _offered(settled)
    assert offered, "the picker vanished along with the row that failed"
    assert "app-1" not in offered, "the picker still offers the deleted draft"


def test_a_pick_the_user_walked_away_from_never_unbinds_the_page_they_moved_to(
        tmp_path):
    """THE GENERATION RULE, on the new limb, driven where it can actually
    fail.

    Tab A's 404 lands after the user has moved to tab B — and tab B has a claim
    of its own, restored from its own tenant's entry. That is what makes the
    guard observable: `resetPageFacts` clears `claimed` on a tab switch, so a
    stale drop aimed at an EMPTY page no-ops by accident and proves nothing.
    Aimed at a page that is bound, an unguarded drop unbinds an application the
    answer was never about and prints the deletion sentence over it.

    (Drop `store.current(token)` from the 404 limb and this test fails: tab B
    loses its binding to a 404 about tab A's draft.)
    """
    spec = _on_apply(api=_deleted_detail(_picker_api()),
                     hold=["GET /api/applications/app-1"],
                     switchTo=9, tabUrls={"9": LIGHTNING_APPLY_URL})
    # Tab B's own memory. A different origin, so tab A refuses it outright
    # (`restorableSession`'s first guard) and the pick there is uncontested.
    spec["stored"] = {"widget.session": entry()}
    # Tab B's page: nothing matched, and its own draft's detail read simply
    # fails — no status, so its binding survives on its own terms.
    spec["api"]["lightningai"] = _reply(
        {"match": "none", "job": None, "application": None})
    out = run_node(_PICK_DRIVER_JS, spec, tmp_path, source=PANEL_SOURCE)
    settled = out["settled"]
    assert _by_class(settled["identity"], "chip")[0]["text"] == (
        "Application · draft"), "tab B lost its binding to tab A's answer"
    assert _note(settled) != DELETED_NOTE
    # The bridge write that stands is tab A's pick, made before the switch;
    # nothing withdrew it on the strength of an answer nobody may paint.
    writes = _session_writes(out)
    assert writes[-1]["widget.session"]["applicationId"] == "app-1"


# ---------- the switcher never displays a choice nobody made ----------
#
# A `<select>` shows its FIRST option when no option is selected, and a
# disabled placeholder is not thereby a selected one. So a bound id absent from
# the rows made the reopened Job body display another draft's name as if the
# user had picked it — the second dishonesty in the same screenshot as the
# ghost, and the more dangerous of the two: the panel was naming a specific,
# plausible application nobody had chosen.

_REOPEN_DRIVER_JS = _PANEL_FAKES_JS + r"""
const opener = (key) => findById(REGIONS.rail, `stg-open-${key}`);
loadModules();
main(async () => {
  await settle();
  const armed = regions();
  const door = opener("job");
  if (door) door.click();
  await settle();
  emit({ armed, reopened: regions(), opened: Boolean(door), sent });
});
"""


def _reopened_picker(tmp_path, drafts):
    """A RESTORED claim on page 2, with its Job row reopened.

    The detail read fails without a status, so the binding survives (see the
    unreachable-backend test above) — which is what puts a bound application on
    screen while the list beside it is read fresh. `toggleRevisit` is what
    fetches that list: a restored pick never went through
    `shouldLoadApplications`, so the switcher's rows arrive only when the user
    opens the row.
    """
    api = _unreachable_detail(_picker_api())
    api["GET /api/applications?"] = _reply(drafts)
    out = run_node(_REOPEN_DRIVER_JS, {
        "tabs": [{"id": 7, "url": APPLY_NEXT_URL}],
        "page": HAS_FORM,
        "stored": {"widget.session": _acme_entry()},
        "api": api,
        "replies": {"read_settings": SETTINGS_REPLY},
    }, tmp_path, source=PANEL_SOURCE)
    assert out["opened"], "the claimed Job row offered no door to reopen"
    select = _picker(out["reopened"]["rail"])
    assert select is not None, "the reopened Job body rendered no switcher"
    return select


def _placeholder(select):
    [found] = [opt for opt in select["children"] if not opt.get("value")]
    return found


def test_a_binding_the_list_does_not_hold_shows_the_placeholder(tmp_path):
    """THE DEFECT ITSELF. The bound draft is not among the rows — deleted,
    older than the list's window, or listed before the pick was made — and the
    switcher must say "Choose a draft application…", which is true, rather than
    display the newest draft's name, which is a claim nobody made.

    (Revert to `if (!currentId) placeholder.selected = true;` and this fails:
    no option matches, so nothing is selected and the browser shows the first.)
    """
    select = _reopened_picker(tmp_path, [_draft(i) for i in range(2, 7)])
    assert _placeholder(select)["selected"] is True
    chosen = [opt["value"] for opt in _draft_options(select) if opt["selected"]]
    assert chosen == [], f"the switcher displayed {chosen} as chosen"


def test_a_binding_the_list_does_hold_is_shown_as_the_one_chosen(tmp_path):
    """The other direction, and the reason the fix is a membership test rather
    than "always select the placeholder": when the bound draft IS on the list,
    the switcher is where the user reads which one they are working on, and a
    placeholder there would hide a real answer.
    """
    select = _reopened_picker(tmp_path, _drafts())
    assert _placeholder(select)["selected"] is False
    chosen = [opt["value"] for opt in _draft_options(select) if opt["selected"]]
    assert chosen == ["app-1"]


def test_the_backends_own_match_is_not_unbound_by_one_application_read(tmp_path):
    """THE NARROWING, pinned where it can be seen.

    `dropDeletedApplication` refuses anything that is not a CLAIM, and the
    reason is what this page is: `/api/jobs/match` has just named this url's
    job, so the job and the match are the backend's own answer about the page
    and they outlive whatever happened to one application row. Unbinding here
    would clear `match` — and a rail that then offers Add job for a posting
    already in the library invites a duplicate job, which is a worse lie than
    the one being fixed.

    So the deletion sentence is not said and the library facts stand. What the
    round deliberately did NOT decide is what such a page should do about the
    application the backend named and then 404'd on; it is a contradiction
    between two backend answers rather than a stale memory, it has never been
    observed, and inventing a third write-set for it was left out of scope.

    (Drop the `claimed !== true` guard and this test fails: the match goes with
    the application.)
    """
    api = {
        "myworkdayjobs": _reply({"match": "exact", "job": LIGHTNING_JOB,
                                 "application": {"id": "app-from-backend",
                                                 "status": "draft"}}),
        "GET /api/applications?": _reply(_drafts()),
        "/api/base-resumes": _reply(BASE_RESUMES),
        "/api/ats-scores": _reply(SCORES),
        "GET /api/applications/app-from-backend": {
            "ok": False, "error": "Application not found", "status": 404},
    }
    out = _load(tmp_path, tabs=[{"id": 7, "url": APPLY_URL}], page=HAS_FORM,
                api=api)
    assert _note(out["regions"]) != DELETED_NOTE
    # The library facts the match established are untouched: the Job row is
    # done, so nothing offers to save this posting a second time.
    assert _rows(_rail_rows(out))["job"]["state"] in {"done", "active"}
    assert _by_class(out["regions"]["foot"], "cta") == [] or (
        "Add job" not in _text(out["regions"]["foot"]))
    # And the bridge is not rewritten on the strength of it.
    assert _session_writes(out) == []


_DELETED_ACROSS_PAGES_DRIVER_JS = _PANEL_FAKES_JS + r"""
loadModules();
main(async () => {
  await settle();
  const first = regions();
  await onActivated({ tabId: spec.switchTo });
  await settle();
  emit({ first, second: regions(), sent, writes });
});
"""


def test_a_list_read_on_an_earlier_page_stops_offering_the_deleted_draft(tmp_path):
    """The drafts list is cached for the LIFE OF THE PANEL — deliberately, so a
    tab switch does not re-fetch it — and it therefore outlives the page that
    read it. That is what makes the unbind's filter load-bearing rather than
    cosmetic: page one reads a list holding `app-1`, page two learns `app-1` is
    gone, and without the filter the picker offered right after the unbind is
    the very list that still holds it — one click from the same 404.

    NO SECOND READ, and that is the other half of the claim. The panel has
    learned exactly one thing about that list; asking the backend to recite the
    rest of it again is a round trip nobody asked for.

    (Drop the `applications` filter from `dropDeletedApplication` and this
    fails: the deleted draft is back on the menu.)
    """
    api = _deleted_detail(_picker_api())
    out = run_node(_DELETED_ACROSS_PAGES_DRIVER_JS, _on_apply(
        api=api,
        stored={"widget.session": _acme_entry()},
        switchTo=9,
        tabUrls={"9": APPLY_NEXT_URL},
    ), tmp_path, source=PANEL_SOURCE)
    # Page one: the offer, from the list as it stood.
    assert "app-1" in _offered(out["first"])
    assert len(_list_gets(out)) == 1, "the cached list was read a second time"
    offered = _offered(out["second"])
    assert offered, "the unbound page offered nothing to bind to"
    assert "app-1" not in offered, "the picker still offers the deleted draft"
