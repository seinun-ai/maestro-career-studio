"""The Job step's Apply and Queue (full automation on): the user's yes, then this one tab.

THE HOST OF A RUN is `panel/actions/run.js` (tests/test_extension_panel_run.py); what these tests pin is
the Job step that STARTS one: which footer it draws (Save job as today with full automation off; Apply
and Queue beside it with it on; Apply alone for a job already queued), what a press asks the backend
for, and the rules that keep the user's own work safe:

- QUEUE is the user's yes: a proposal, then the `accepted` PATCH under the Companion's consent channel;
- APPLY queues, claims the job from the always-on copy when sync offered it away, readies the resume
  from what the SERVER holds (a PDF -> go; a draft without one -> Create PDF; nothing and no open
  custom session -> Quick tailor; an open custom session -> stop, never tailor over it), then starts a
  one-job run in the CURRENT tab: no tab, no window, and never a Submit;
- a base resume is never named without its square.

The run itself is stubbed except in the one test that drives a whole record, because the driver has its
own tests; here the question is what the Job step hands it.
"""

import json

import pytest

from tests.extension_harness import run_node
from tests.extension_panel_harness import (
    HUED_RESUMES,
    PANEL_SOURCE,
    SCORE_ROWS,
    SETTINGS_REPLY,
    _PANEL_FAKES_JS,
    _by_class,
    _reply,
    _text,
    _walk,
)
from tests.test_extension_panel_run import REVIEW, STEP1, page

APP_URL = "https://jobs.acme.test/apply/step1"
BOARD_URL = "https://board.example.test/jobs/12345"
# A job BOARD's own page: the run's move there is to the employer's link (run.js `BOARD_HOST`).
BOARD_PAGE = "https://www.linkedin.com/jobs/view/12345"
JOB = {"id": "job-1", "company": "Acme", "title": "Data Scientist"}
POSTING = _reply({"url": BOARD_URL, "title": "Data Scientist | Acme",
                  "text": "Title: Data Scientist\nCompany: Acme\nLocation: Remote\n\nBuild models.",
                  "source": "json-ld", "applyUrl": APP_URL})
AUTOMATION_ON = _reply({"key": "auto_apply", "value": {"full_automation": True}})
AUTOMATION_OFF = _reply({"key": "auto_apply", "value": {"full_automation": False}})
QUEUE_NOTE = "Queued. Apply to queued will pick it up."
FINISH_NOTE = "You're tailoring this job in Maestro. Finish it, then press Apply."
OFF_LINE = "Turn on full automation in Settings to apply from here."
PROMISE = "Apply fills every page here and stops before Submit."


def _job(**over):
    """The job as `GET /api/jobs/{id}/detail` reads it (JobRead + the newest application)."""
    job = {**JOB, "apply_url": APP_URL, "source_url": BOARD_URL, "proposal_id": None,
           "proposal_status": None, "ownership": {"owned_here": True, "owner": None,
                                                  "handover": None, "pending_requests": 0,
                                                  "can_keep_here": False}}
    application = over.pop("application", None)
    job.update(over)
    return _reply({"job": job, "application": application, "knockout": None, "has_filled_answers": False})


def _draft(pdf=True, **over):
    return {"id": "app-1", "job_id": "job-1", "base_resume": "ai_ml_engineer", "status": "draft",
            "customized_json": {"x": 1}, "pdf_path": "renders/Ada.pdf" if pdf else None, **over}


PROPOSAL = {"id": "prop-1", "status": "pending_review", "application_id": None}
ACCEPTED = {**PROPOSAL, "status": "accepted"}
TAILORED = {"application_id": "app-1", "session_id": "sess-1", "applied": ["a"], "pdf_ready": True,
            "nothing_to_tailor": False}


def _saved(**api):
    """A saved job with scores in hand and the Job step open on it (full automation keeps it open)."""
    return {
        "/api/jobs/match": _reply({"match": "exact", "job": JOB, "application": None}),
        "/api/base-resumes": _reply(HUED_RESUMES),
        "GET /api/ats-scores": _reply([
            {"target_type": "base_resume", "target_id": "ai_ml_engineer", "phase": "base", "composite": 71.8},
            {"target_type": "base_resume", "target_id": "data_scientist", "phase": "base", "composite": 63.6},
        ]),
        "/api/settings/auto-apply": AUTOMATION_ON,
        "/api/jobs/job-1/detail": _job(),
        "/api/tailoring-sessions?job_id": _reply([]),
        "POST /api/proposals": _reply(PROPOSAL),
        "PATCH /api/proposals/prop-1": _reply(ACCEPTED),
        "/quick-tailor": _reply(TAILORED),
        "/api/applications/app-1/render": _reply({"pdf_path": "renders/Ada.pdf"}),
        "POST /api/jobs/job-1/filled-answers": _reply({"flags": []}),
        **api,
    }


def _fresh(**api):
    """An unsaved posting: nothing matched, the page answers the extraction."""
    return {
        "/api/jobs/match": _reply({"match": "none", "job": None, "application": None}),
        "/api/base-resumes": _reply(HUED_RESUMES),
        "/api/settings/auto-apply": AUTOMATION_ON,
        "POST /api/ats-scores": _reply(SCORE_ROWS),
        "/api/jobs/job-1/detail": _job(),
        "/api/tailoring-sessions?job_id": _reply([]),
        "POST /api/proposals": _reply(PROPOSAL),
        "PATCH /api/proposals/prop-1": _reply(ACCEPTED),
        "/quick-tailor": _reply(TAILORED),
        "/api/applications/app-1/render": _reply({"pdf_path": "renders/Ada.pdf"}),
        "POST /api/jobs/job-1/filled-answers": _reply({"flags": []}),
        # Last: `POST /api/jobs` is a substring of every write under a job, and the first needle wins.
        "POST /api/jobs": _reply({**JOB, "already_existed": False, "extracted_json": {"skills": ["python"]}}),
        **api,
    }


_APPLY_DRIVER_JS = _PANEL_FAKES_JS + r"""
// ---- nothing may open: Apply drives THIS tab ----
const created = [];
chrome.tabs.create = async (props) => { created.push({ tab: props }); return { id: 99 }; };
chrome.windows = { create: async (props) => { created.push({ window: props }); return { id: 5 }; } };
const updates = [];
let currentUrl = (spec.tabs ?? [])[0]?.url ?? "";
let at = 0;
chrome.tabs.get = async (id) => ({ id, status: "complete", url: (spec.tabUrls ?? {})[id] ?? currentUrl });
chrome.tabs.update = async (id, props) => { updates.push([id, props]); if (props.url) { currentUrl = props.url; at = 0; } };

// ---- the fake site, for the one test that drives a whole record ----
const site = spec.site ?? [];
const here = () => site[Math.min(at, site.length - 1)];
spec.frames = spec.frames ?? {};
Object.defineProperty(spec.frames, "page_classify", { configurable: true, enumerable: true,
  get: () => (here() ? [{ frameId: 0, url: here().url, result: { summary: here().summary, top: true } }] : []) });
Object.defineProperty(spec.frames, "page_advance", { configurable: true, enumerable: true,
  get: () => { at += 1; return [{ frameId: 0, result: { clicked: true } }]; } });
spec.frames.fill_inventory = [{ frameId: 0, result: { fields: [] } }];
spec.frames.fill_cancel = [{ frameId: 0, result: true }];
spec.page = spec.page ?? {};

const ns = loadModules();
const seeds = [];
const fills = [];
if (spec.realRun) {
  ns.fillLoop.runFill = async (deps, options) => {
    fills.push(options);
    return { runId: "r", host: "jobs.acme.test", fields: [{ fid: "f1", question: "Name", required: true,
             status: "verified" }], aiFailure: null, stopped: false, timedOut: false, consentForms: false,
             sections: [] };
  };
} else {
  // The driver has its own tests: here it is a recorder.
  ns.panelActionsRun.startRun = async (store, seed) => { seeds.push(seed); return null; };
}
const errors = [];
console.error = (...args) => { errors.push(args.map(String).join(" ")); };
const actions = ns.panelActions(ns.panel.actionStore());

const hit = (node, match) => (match(node) ? node : node.children.map((kid) => hit(kid, match)).find(Boolean));
const snap = () => ({ regions: regions(), facts: JSON.parse(JSON.stringify((({ runs, fullAutomation, apply, tailorFirst,
  baseSlug }) => ({ runs, fullAutomation, apply, tailorFirst, baseSlug }))(ns.panel.actionStore().read()))) });
main(async () => {
  await settle();
  const shots = [snap()];
  for (const step of spec.steps ?? []) {
    if (step.foot !== undefined) {
      const button = hit(REGIONS.foot, (node) => node.tagName === "BUTTON" && node.allText === step.foot);
      if (!button) throw new Error(`no footer button reads "${step.foot}"`);
      button.click();
    }
    if (step.body !== undefined) {
      const button = hit(REGIONS.rail, (node) => node.tagName === "BUTTON" && node.allText === step.body);
      if (!button) throw new Error(`no button in the rail reads "${step.body}"`);
      button.click();
    }
    if (step.id !== undefined) {
      const node = document.getElementById(step.id);
      if (!node) throw new Error(`no control #${step.id}`);
      node.click();
    }
    if (step.call !== undefined) await actions[step.call]();
    if (step.activate !== undefined) await onActivated({ tabId: step.activate });
    if (step.release) release();
    for (let i = 0; i < (step.settles ?? 1); i += 1) await settle();
    shots.push(snap());
  }
  emit({ shots, sent, seeds, updates, created, fills, errors, warnings, broadcasts });
});
"""


# Phase 3 turns the Queue button on (panel.js `QUEUE_BUTTON`); its tests run with the flag flipped.
QUEUE_ON = PANEL_SOURCE.replace("const QUEUE_BUTTON = false;", "const QUEUE_BUTTON = true;")
assert QUEUE_ON != PANEL_SOURCE


def _apply(tmp_path, steps=(), api=None, queue_button=False, **spec):
    spec.setdefault("tabs", [{"id": 7, "url": BOARD_URL}])
    spec["replies"] = {"read_settings": SETTINGS_REPLY, "panel_prepare": _reply({"injected": True}),
                       "panel_frame0": _reply({"tier": "B", "form": True, "score": 2}),
                       "telemetry": _reply({"posted": 0}), **spec.get("replies", {})}
    spec.setdefault("page", {"extract_job_posting": POSTING,
                             "detect_page": _reply({"tier": "none", "form": False, "score": 0})})
    spec["api"] = api if api is not None else _fresh()
    return run_node(_APPLY_DRIVER_JS, {"steps": list(steps), **spec}, tmp_path,
                    source=QUEUE_ON if queue_button else PANEL_SOURCE)


# ---------- reading what was painted ----------


def _foot(shot):
    """The footer's buttons as `{label: class list}`, in order."""
    return [(_text(one), one["class"].split()) for one in _walk(shot["regions"]["foot"])
            if one["tag"] == "BUTTON"]


def _labels(shot):
    return [label for label, _ in _foot(shot)]


def _rail_buttons(shot):
    return [_text(one) for one in _walk(shot["regions"]["rail"]) if one["tag"] == "BUTTON"]


def _note(shot):
    [note] = _by_class(shot["regions"]["foot"], "note")
    return note["text"]


def _api(out, method, needle):
    return [msg for msg in out["sent"] if msg["type"] == "api"
            and (msg.get("init") or {}).get("method", "GET") == method and needle in msg["path"]]


def _body(msg):
    return json.loads(msg["init"]["body"])


def _order(out):
    """`METHOD path` of every backend write, in the order sent."""
    return [f"{(msg.get('init') or {}).get('method')} {msg['path'].split('?')[0]}" for msg in out["sent"]
            if msg["type"] == "api" and (msg.get("init") or {}).get("method") in {"POST", "PATCH", "PUT"}]


def _names_without_a_square(shot, names):
    """Every node whose own words hold a base resume's name but that has no square beside it."""
    bare = []
    for node in _walk(shot["regions"]["rail"]):
        own = node["text"]
        if any(name in own for name in names):
            if not any("swatch" in kid["class"].split() for kid in node["children"]):
                bare.append(own)
    return bare


# ---------- the footer ----------


def test_with_full_automation_off_the_job_step_is_save_job_and_says_where_apply_is(tmp_path):
    out = _apply(tmp_path, api=_fresh(**{"/api/settings/auto-apply": AUTOMATION_OFF}))
    shot = out["shots"][0]
    assert _labels(shot) == ["Save job"]
    assert OFF_LINE in _text(shot["regions"]["rail"])
    assert PROMISE not in _text(shot["regions"]["rail"])
    # Nothing in the rail offers to apply or queue.
    assert {"Apply", "Queue"}.isdisjoint(_rail_buttons(shot))


def test_a_setting_that_cannot_be_read_leaves_save_job_exactly_as_it_was(tmp_path):
    api = _fresh()
    del api["/api/settings/auto-apply"]
    shot = _apply(tmp_path, api=api)["shots"][0]
    assert _labels(shot) == ["Save job"]
    assert OFF_LINE not in _text(shot["regions"]["rail"])


def test_with_full_automation_on_apply_is_the_only_primary_until_the_queue_view_exists(tmp_path):
    shot = _apply(tmp_path)["shots"][0]
    assert _foot(shot) == [("Apply", ["cta"])]
    assert PROMISE in _text(shot["regions"]["rail"])
    assert "Queue" not in _rail_buttons(shot)


def test_with_the_queue_button_on_it_sits_beside_apply(tmp_path):
    shot = _apply(tmp_path, queue_button=True)["shots"][0]
    assert _foot(shot) == [("Apply", ["cta", "pair"]), ("Queue", ["cta", "pair", "alt"])]
    rail = _text(shot["regions"]["rail"])
    assert PROMISE in rail
    assert OFF_LINE not in rail


def test_a_queued_job_shows_apply_alone_and_an_applied_one_neither(tmp_path):
    queued = _saved(**{"/api/jobs/job-1/detail": _job(proposal_id="prop-1", proposal_status="accepted")})
    assert _labels(_apply(tmp_path, api=queued)["shots"][0]) == ["Apply"]
    applied = _saved(**{"/api/jobs/job-1/detail": _job(proposal_status="submitted")})
    labels = _labels(_apply(tmp_path, api=applied)["shots"][0])
    assert "Apply" not in labels and "Queue" not in labels


def test_a_saved_job_keeps_the_job_step_open_with_the_base_picker_and_two_ways_round(tmp_path):
    shot = _apply(tmp_path, api=_saved())["shots"][0]
    rail = _text(shot["regions"]["rail"])
    assert "Apply with this resume" in rail and PROMISE in rail
    assert _foot(shot)[0][0] == "Apply"
    assert {"Update scores", "Tailor first, then apply"} <= set(_rail_buttons(shot))
    # The step the user is on is Job: Resume's Quick tailor is not the primary.
    assert "Quick tailor" not in _labels(shot)


def test_tailor_first_opens_todays_resume_step_instead_of_applying(tmp_path):
    out = _apply(tmp_path, api=_saved(), steps=[{"body": "Tailor first, then apply"}])
    shot = out["shots"][1]
    assert _labels(shot) == ["Quick tailor"]
    assert out["seeds"] == [] and _order(out) == []


def test_with_full_automation_off_a_saved_scored_job_still_lands_on_resume(tmp_path):
    api = _saved(**{"/api/settings/auto-apply": AUTOMATION_OFF})
    assert _labels(_apply(tmp_path, api=api)["shots"][0]) == ["Quick tailor"]


def test_update_scores_moves_into_the_body_and_scores_again(tmp_path):
    out = _apply(tmp_path, api=_saved(**{"POST /api/ats-scores": _reply(SCORE_ROWS)}),
                 steps=[{"body": "Update scores"}])
    assert len(_api(out, "POST", "/api/ats-scores")) >= 1
    assert out["seeds"] == []


# ---------- a base is never named without its square ----------


def test_every_line_that_names_a_base_resume_keeps_its_square(tmp_path):
    # A resume with no colour yet draws no square, so only the coloured ones can be left bare.
    names = [row["display_name"] for row in HUED_RESUMES if row["color_hue"] is not None]
    sessions = _saved(**{"/api/tailoring-sessions?job_id": _reply([{"id": "sess-1", "status": "open"}])})
    for api in (_saved(), sessions):
        out = _apply(tmp_path, api=api)
        assert _names_without_a_square(out["shots"][0], names) == []
    # and a note never names one (it cannot carry a square)
    out = _apply(tmp_path, api=sessions, steps=[{"foot": "Apply"}])
    assert not any(name in _note(out["shots"][1]) for name in names)


# ---------- Queue: the user's yes ----------


def test_queue_saves_then_posts_the_proposal_then_accepts_it_as_the_companion(tmp_path):
    out = _apply(tmp_path, steps=[{"foot": "Queue"}], queue_button=True)
    assert _order(out)[:4] == ["POST /api/jobs", "POST /api/ats-scores", "POST /api/proposals",
                               "PATCH /api/proposals/prop-1"]
    [created] = _api(out, "POST", "/api/proposals")
    body = _body(created)
    assert body["job_id"] == "job-1" and body["proposed_by"] == "you"
    # The chosen base is the Job step's pick (the best match until the user picks another), scores are
    # the panel's own.
    assert body["fit"] == {"chosen_base": "ai_ml_engineer", "decided_by": "user",
                           "scores": {"data_scientist": 63.6, "ai_ml_engineer": 71.8}}
    [accepted] = _api(out, "PATCH", "/api/proposals/prop-1")
    assert _body(accepted) == {"status": "accepted", "consent": {"channel": "companion"}}
    assert _note(out["shots"][1]) == QUEUE_NOTE
    # Queue is not Apply: no resume work, no run.
    assert _api(out, "POST", "/quick-tailor") == [] and out["seeds"] == []


def test_queue_uses_the_resume_the_user_picked(tmp_path):
    out = _apply(tmp_path, api=_saved(), steps=[{"id": "base-data_scientist"}, {"foot": "Queue"}], queue_button=True)
    assert _body(_api(out, "POST", "/api/proposals")[0])["fit"]["chosen_base"] == "data_scientist"


def test_a_queued_job_is_not_queued_twice_and_a_proposal_already_accepted_is_not_patched(tmp_path):
    out = _apply(tmp_path, api=_saved(**{"POST /api/proposals": _reply(ACCEPTED)}), steps=[{"foot": "Queue"}],
                 queue_button=True)
    assert _api(out, "PATCH", "/api/proposals") == []
    assert _note(out["shots"][1]) == QUEUE_NOTE


def test_queue_says_why_when_the_server_refuses(tmp_path):
    refusal = {"ok": False, "status": 409,
               "error": "You skipped this job before. Delete the skipped proposal in the Agent inbox to queue it again."}
    out = _apply(tmp_path, api=_saved(**{"POST /api/proposals": refusal}), steps=[{"foot": "Queue"}],
                 queue_button=True)
    assert "You skipped this job before." in _note(out["shots"][1])
    assert _api(out, "PATCH", "/api/proposals") == []


# ---------- Apply: queue, ready the resume, run this tab ----------


def test_apply_on_a_fresh_posting_saves_queues_tailors_links_and_starts_one_run(tmp_path):
    out = _apply(tmp_path, steps=[{"foot": "Apply"}])
    assert _order(out) == [
        "POST /api/jobs", "POST /api/ats-scores", "POST /api/proposals", "PATCH /api/proposals/prop-1",
        "POST /api/jobs/job-1/quick-tailor", "POST /api/proposals"]
    # Quick tailor uses the pick, and the application is linked to the proposal.
    assert _body(_api(out, "POST", "/quick-tailor")[0]) == {"base_resume": "ai_ml_engineer"}
    assert _body(_api(out, "POST", "/api/proposals")[1]) == {"job_id": "job-1", "application_id": "app-1"}
    [seed] = out["seeds"]
    assert seed == {"proposalId": "prop-1", "jobId": "job-1", "applicationId": "app-1", "company": "Acme",
                    "title": "Data Scientist", "baseSlug": "ai_ml_engineer", "openUrl": APP_URL}
    assert out["created"] == []


def test_apply_on_a_job_already_queued_skips_the_queue_step(tmp_path):
    api = _saved(**{"/api/jobs/job-1/detail": _job(proposal_id="prop-1", proposal_status="accepted")})
    out = _apply(tmp_path, api=api, steps=[{"foot": "Apply"}])
    # The one proposal write left is the link to the application; nothing is created or accepted again.
    assert [_body(msg) for msg in _api(out, "POST", "/api/proposals")] == [
        {"job_id": "job-1", "application_id": "app-1"}]
    assert _api(out, "PATCH", "/api/proposals") == []
    assert out["seeds"][0]["proposalId"] == "prop-1"


def test_apply_renders_the_pdf_when_quick_tailor_could_not(tmp_path):
    api = _saved(**{"/quick-tailor": _reply({**TAILORED, "pdf_ready": False})})
    out = _apply(tmp_path, api=api, steps=[{"foot": "Apply"}])
    assert len(_api(out, "POST", "/api/applications/app-1/render")) == 1
    assert len(out["seeds"]) == 1


def test_apply_treats_a_nothing_to_tailor_answer_as_the_base_resume_and_closes_the_session_it_left(tmp_path):
    api = _saved(**{"/quick-tailor": _reply({"application_id": None, "session_id": "sess-9",
                                              "nothing_to_tailor": True, "pdf_ready": False}),
                    "POST /api/applications/from-base": _reply(_draft(pdf=False)),
                    "POST /api/tailoring-sessions/sess-9/close": _reply({"id": "sess-9", "status": "closed"})})
    out = _apply(tmp_path, api=api, steps=[{"foot": "Apply"}])
    assert _body(_api(out, "POST", "/api/applications/from-base")[0]) == {
        "job_id": "job-1", "base_resume": "ai_ml_engineer", "ops": []}
    assert len(_api(out, "POST", "/api/tailoring-sessions/sess-9/close")) == 1
    assert len(out["seeds"]) == 1 and out["seeds"][0]["applicationId"] == "app-1"


def test_apply_with_a_pdf_ready_draft_goes_straight_to_the_run(tmp_path):
    api = _saved(**{"/api/jobs/job-1/detail": _job(application=_draft())})
    out = _apply(tmp_path, api=api, steps=[{"call": "applyJob"}])
    assert _api(out, "POST", "/quick-tailor") == [] and _api(out, "POST", "/render") == []
    assert out["seeds"][0]["applicationId"] == "app-1"
    assert out["seeds"][0]["baseSlug"] == "ai_ml_engineer"


def test_apply_with_a_draft_that_has_no_pdf_creates_the_pdf_and_never_quick_tailors(tmp_path):
    api = _saved(**{"/api/jobs/job-1/detail": _job(application=_draft(pdf=False))})
    out = _apply(tmp_path, api=api, steps=[{"call": "applyJob"}])
    assert len(_api(out, "POST", "/api/applications/app-1/render")) == 1
    assert _api(out, "POST", "/quick-tailor") == []
    assert len(out["seeds"]) == 1


def test_apply_never_quick_tailors_over_an_open_custom_session(tmp_path):
    api = _saved(**{"/api/tailoring-sessions?job_id": _reply([{"id": "sess-1", "status": "open"}])})
    out = _apply(tmp_path, api=api, steps=[{"foot": "Apply"}])
    assert _api(out, "POST", "/quick-tailor") == [] and _api(out, "POST", "/render") == []
    assert _api(out, "POST", "/from-base") == [] and out["seeds"] == []
    assert _note(out["shots"][1]) == FINISH_NOTE
    # It was queued (the user's yes stands), so the next press is Apply alone.
    assert len(_api(out, "PATCH", "/api/proposals/prop-1")) == 1


def test_the_open_session_state_offers_finish_in_maestro_and_apply_with_the_base_resume(tmp_path):
    api = _saved(**{"/api/tailoring-sessions?job_id": _reply([{"id": "sess-1", "status": "open"}])})
    shot = _apply(tmp_path, api=api)["shots"][0]
    rail = _text(shot["regions"]["rail"])
    assert "Finish tailoring first" in rail
    [link] = [one for one in _walk(shot["regions"]["rail"]) if one["tag"] == "A"
              and "Finish in Maestro CS" in _text(one)]
    assert link["href"] == "http://localhost:3000/jobs/job-1/tailor/sess-1"
    assert "Apply with the base resume" in _rail_buttons(shot)


def test_apply_with_the_base_resume_never_tailors_and_leaves_the_session_open(tmp_path):
    api = _saved(**{"/api/tailoring-sessions?job_id": _reply([{"id": "sess-1", "status": "open"}]),
                    "POST /api/applications/from-base": _reply(_draft(pdf=False)),
                    "/api/applications/app-1/render": _reply({"pdf_path": "renders/Ada.pdf"})})
    out = _apply(tmp_path, api=api, steps=[{"body": "Apply with the base resume"}])
    assert _api(out, "POST", "/quick-tailor") == []
    assert _api(out, "POST", "/api/tailoring-sessions") == [] and _api(out, "PATCH", "/api/tailoring-sessions") == []
    assert _body(_api(out, "POST", "/api/applications/from-base")[0])["ops"] == []
    assert len(_api(out, "POST", "/api/applications/app-1/render")) == 1
    [seed] = out["seeds"]
    assert seed["applicationId"] == "app-1" and seed["baseSlug"] == "ai_ml_engineer"


def test_apply_on_an_applied_job_does_nothing_but_say_so(tmp_path):
    api = _saved(**{"/api/jobs/job-1/detail": _job(proposal_status="submitted")})
    out = _apply(tmp_path, api=api, steps=[{"call": "applyJob"}])
    assert out["seeds"] == [] and _order(out) == []
    assert "already applied" in _note(out["shots"][1]).lower()


# ---------- a job that already has a draft: the footer, not applyJob ----------
# `/api/jobs/match` returns the job's newest application, so a user's own tailored draft arrives bound
# on the page. These click the footer's button: calling `applyJob` directly bypassed the gate that hid
# Apply on every bound application.


def _primary(shot):
    """The footer's `cta` buttons (the Draft/Applied status chips beside them are not primaries)."""
    return [label for label, classes in _foot(shot) if "cta" in classes]


def _bound(status="draft", pdf=True, **api):
    """A saved job whose match already names its application (the backend's own, not a claim)."""
    bound = {"id": "app-1", "status": status, "base_resume": "ai_ml_engineer"}
    return _saved(**{
        "/api/jobs/match": _reply({"match": "exact", "job": JOB, "application": bound}),
        "GET /api/applications/app-1": _reply(_draft(pdf=pdf, status=status)),
        "/api/jobs/job-1/detail": _job(application=_draft(pdf=pdf, status=status),
                                       proposal_status=None if status == "draft" else "submitted"),
        **api,
    })


def test_a_draft_with_a_pdf_shows_apply_and_a_press_starts_the_run_without_tailoring(tmp_path):
    out = _apply(tmp_path, api=_bound(), steps=[{"foot": "Apply"}])
    assert _primary(out["shots"][0]) == ["Apply"]
    assert _api(out, "POST", "/quick-tailor") == [] and _api(out, "POST", "/render") == []
    assert _api(out, "POST", "/from-base") == []
    [seed] = out["seeds"]
    assert seed["applicationId"] == "app-1" and seed["baseSlug"] == "ai_ml_engineer"


def test_a_draft_without_a_pdf_renders_it_then_runs_and_never_quick_tailors(tmp_path):
    out = _apply(tmp_path, api=_bound(pdf=False), steps=[{"foot": "Apply"}])
    assert _primary(out["shots"][0]) == ["Apply"]
    assert len(_api(out, "POST", "/api/applications/app-1/render")) == 1
    assert _api(out, "POST", "/quick-tailor") == [] and _api(out, "POST", "/from-base") == []
    assert [one["applicationId"] for one in out["seeds"]] == ["app-1"]


def test_the_job_step_stays_open_on_a_draft_so_apply_is_there_without_reopening_anything(tmp_path):
    shot = _apply(tmp_path, api=_bound())["shots"][0]
    assert PROMISE in _text(shot["regions"]["rail"])
    assert _primary(shot) == ["Apply"]


def test_an_applied_application_has_no_apply(tmp_path):
    shot = _apply(tmp_path, api=_bound(status="applied"))["shots"][0]
    assert _primary(shot) == []


# ---------- where the job lives (sync) ----------


def _owned(**ownership):
    return {"owned_here": True, "owner": "laptop", "handover": None, "pending_requests": 0,
            "can_keep_here": False, **ownership}


def test_a_job_the_laptop_offered_away_is_kept_here_before_anything_is_written_to_it(tmp_path):
    offered = _owned(owned_here=False, handover="offered", can_keep_here=True)
    api = _saved(**{
        "/api/jobs/job-1/detail": _job(ownership=_owned()),
        # After queueing, the job reads offered; Keep it here claims it back.
        "GET /api/jobs/job-1": _reply({**JOB, "ownership": offered}),
        "POST /api/jobs/job-1/keep-here": _reply({**JOB, "ownership": _owned()}),
    })
    out = _apply(tmp_path, api=api, steps=[{"foot": "Apply"}])
    order = _order(out)
    assert order.index("PATCH /api/proposals/prop-1") < order.index("POST /api/jobs/job-1/keep-here") \
        < order.index("POST /api/jobs/job-1/quick-tailor")
    assert len(out["seeds"]) == 1


def test_a_job_held_by_the_always_on_copy_is_refused_with_a_clear_message_and_nothing_written(tmp_path):
    bot = _owned(owned_here=False, owner="bot")
    api = _saved(**{"/api/jobs/job-1/detail": _job(ownership=bot)})
    out = _apply(tmp_path, api=api, steps=[{"foot": "Apply"}])
    assert "bot" in _note(out["shots"][1]).lower()
    assert _order(out) == [] and out["seeds"] == []


def test_a_job_on_its_way_back_to_the_laptop_is_refused_too(tmp_path):
    returning = _owned(owned_here=False, handover="returning", owner="bot")
    api = _saved(**{"/api/jobs/job-1/detail": _job(ownership=returning)})
    out = _apply(tmp_path, api=api, steps=[{"foot": "Apply"}])
    assert "back to your laptop" in _note(out["shots"][1])
    assert _order(out) == [] and out["seeds"] == []


# ---------- the link the run opens ----------


@pytest.mark.parametrize("apply_url,source_url,expected", [
    (APP_URL, BOARD_URL, APP_URL),
    (None, BOARD_URL, BOARD_URL),
    ("javascript:alert(1)", BOARD_URL, BOARD_URL),
    ("ftp://files.example.test/apply", BOARD_URL, BOARD_URL),
    ("not a url", None, BOARD_URL),
])
def test_the_run_opens_the_apply_link_else_the_posting_and_only_ever_over_http(
        tmp_path, apply_url, source_url, expected):
    detail = _job(apply_url=apply_url, source_url=source_url)
    out = _apply(tmp_path, api=_saved(**{"/api/jobs/job-1/detail": detail}), steps=[{"foot": "Apply"}])
    assert out["seeds"][0]["openUrl"] == expected


# ---------- a whole record, in this tab ----------


def test_apply_on_a_board_posting_navigates_this_tab_to_the_apply_link_and_drives_one_record(tmp_path):
    out = _apply(tmp_path, api=_saved(), realRun=True, site=[STEP1, REVIEW], tabs=[{"id": 7, "url": BOARD_PAGE}],
                 steps=[{"foot": "Apply", "settles": 4}])
    # This tab, once, to the employer's form; no tab and no window anywhere.
    assert out["updates"] == [[7, {"url": APP_URL}]]
    assert out["created"] == []
    [record] = out["shots"][-1]["facts"]["runs"]
    assert (record["status"], record["jobId"], record["applicationId"], record["startTabId"]) == (
        "ready", "job-1", "app-1", 7)
    assert record["openUrl"] == APP_URL
    # Ready to submit is where it stops: the page was asked to advance, never to submit.
    assert len(out["fills"]) >= 1
    assert not [msg for msg in out["broadcasts"] if "submit" in msg["message"]["type"]]


def test_apply_on_the_employers_form_keeps_the_page_the_user_is_on(tmp_path):
    out = _apply(tmp_path, api=_saved(), realRun=True, site=[STEP1, REVIEW],
                 tabs=[{"id": 7, "url": "https://jobs.acme.test/apply/step2"}],
                 steps=[{"foot": "Apply", "settles": 4}])
    assert out["updates"] == []
    assert out["created"] == []
    [record] = out["shots"][-1]["facts"]["runs"]
    assert record["status"] == "ready"


@pytest.mark.parametrize("press", ["Apply", "Queue"])
def test_a_press_belongs_to_the_tab_it_was_made_on(tmp_path, press):
    """The save is still in flight when the user moves to another saved job's tab: nothing is queued
    for it, and nothing is run, on the strength of a press made somewhere else."""
    other = "https://other.example.test/jobs/2"
    api = {"other.example.test": _reply({"match": "exact", "job": {**JOB, "id": "job-2"}, "application": None}),
           "/api/jobs/job-2/detail": _job(id="job-2"), **_fresh()}
    out = _apply(tmp_path, api=api, tabs=[{"id": 7, "url": BOARD_URL}, {"id": 8, "url": other}],
                 tabUrls={"7": BOARD_URL, "8": other}, hold=["POST /api/jobs"],
                 steps=[{"foot": press}, {"activate": 8}, {"release": True, "settles": 2}],
                 queue_button=True)
    assert _order(out) == ["POST /api/jobs"]
    assert out["seeds"] == []


def test_an_unsaved_posting_that_cannot_be_read_is_not_queued_or_run(tmp_path):
    blank = _reply({"url": BOARD_URL, "title": "x", "text": "", "source": "body"})
    out = _apply(tmp_path, page={"extract_job_posting": blank,
                                 "detect_page": _reply({"tier": "none", "form": False, "score": 0})},
                 steps=[{"foot": "Apply"}])
    assert _order(out) == [] and out["seeds"] == []
    assert "Nothing to save yet" in _note(out["shots"][1])
