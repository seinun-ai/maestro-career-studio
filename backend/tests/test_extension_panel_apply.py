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

// A BROWSER BLURS A REMOVED NODE: focus falls to the body when the focused control leaves the document (the
// shared fake models no removal, and the Refresh driver patches it the same way).
const holds = (node, target) => node === target || node.children.some((kid) => holds(kid, target));
for (const root of [...Object.values(REGIONS), CONTROLS]) {
  const replace = root.replaceChildren.bind(root);
  root.replaceChildren = (...kids) => {
    if (ACTIVE && root.children.some((kid) => holds(kid, ACTIVE))) ACTIVE = null;
    replace(...kids);
  };
}
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
const snap = () => ({ focused: document.activeElement?.id ?? null, regions: regions(), facts: JSON.parse(JSON.stringify((({ runs, fullAutomation, apply, tailorFirst,
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
    if (step.pick !== undefined) {
      const select = document.getElementById("draft-pick");
      if (!select) throw new Error("no draft picker on screen");
      select.value = step.pick;
      select.dispatch("change");
    }
    if (step.focus !== undefined) {
      const node = document.getElementById(step.focus);
      if (!node) throw new Error(`no control #${step.focus} to focus`);
      node.focus();
    }
    if (step.write) {
      ns.panel.actionStore().write(step.write);
      ns.panel.actionStore().render();
    }
    if (step.seed) {
      ns.panel.actionStore().write({ runs: step.seed });
      ns.panel.actionStore().render();
    }
    if (step.call !== undefined) await actions[step.call]();
    if (step.activate !== undefined) await onActivated({ tabId: step.activate });
    if (step.release) release();
    for (let i = 0; i < (step.settles ?? 1); i += 1) await settle();
    shots.push(snap());
  }
  emit({ shots, sent, seeds, updates, created, fills, errors, warnings, broadcasts, writes });
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
                    "location": None, "title": "Data Scientist", "baseSlug": "ai_ml_engineer", "openUrl": APP_URL}
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


def _run_record(tab, status="filling", **extra):
    return {"id": "run-1", "proposalId": "prop-0", "jobId": "job-0", "applicationId": "app-0", "company": "Globex",
            "openUrl": APP_URL, "startTabId": tab, "tabId": tab, "status": status, "why": None, "open": [],
            "hosts": ["jobs.acme.test"], "seen": [], "step": 0, "pages": [], "flags": [], **extra}


def test_apply_on_a_tab_with_a_live_run_says_so_and_writes_nothing(tmp_path):
    """A second Apply would queue, tailor and link a job, and only then find the tab taken."""
    for status in ("filling", "parked", "ready", "confirming"):
        out = _apply(tmp_path, api=_saved(), steps=[{"seed": [_run_record(7, status)], "call": "applyJob"}])
        assert out["seeds"] == [] and _order(out) == [], status
        assert "A run is already going in this tab." in _text(out["shots"][1]["regions"]["foot"]), status


def test_a_run_that_is_over_or_in_another_tab_does_not_stop_apply(tmp_path):
    for record in (_run_record(7, "stopped", why="user"), _run_record(7, "applied"), _run_record(8, "filling")):
        out = _apply(tmp_path, api=_saved(), steps=[{"seed": [record], "call": "applyJob"}])
        assert len(out["seeds"]) == 1, record["status"]


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


# ---------- a job the user picked by hand: Apply runs in THIS tab ----------
# The user opened the employer's own form (a different site from the saved link, so the backend's match
# is silent), and named the job's draft in the picker. That pick says this page IS the job's application,
# so Apply runs here and never opens or navigates to the job's saved links.

FORM_HOST = "forms.globex.test"
FORM_URL = f"https://{FORM_HOST}/jobs/JR1043/apply/step1"
PICKED = {"id": "app-1", "job_id": "job-1", "base_resume": "ai_ml_engineer", "status": "draft",
          "job_company": "Acme", "job_title": "Data Scientist"}
FORM_PAGE = {"extract_job_posting": _reply({"url": FORM_URL, "title": "Apply", "text": "", "source": "body"}),
             "detect_page": _reply({"tier": "B", "form": True, "score": 2})}


def _picked(status="draft", **api):
    """An unmatched employer form with the user's draft on the picker's list, and a saved job that has no
    apply link yet (it was saved from a board)."""
    detail = _job(application=_draft(status=status), apply_url=None,
                  proposal_status=None if status == "draft" else "submitted")
    return _saved(**{
        "/api/jobs/match": _reply({"match": "none", "job": None, "application": None}),
        "GET /api/applications?": _reply([PICKED]),
        "GET /api/applications/app-1": _reply(_draft(status=status)),
        "/api/jobs/job-1/detail": detail,
        "PATCH /api/jobs/job-1": _reply({**JOB, "apply_url": FORM_URL}),
        **api,
    })


def _on_form(tmp_path, steps, api=None, url=FORM_URL, **spec):
    spec.setdefault("page", FORM_PAGE)
    return _apply(tmp_path, api=api or _picked(), tabs=[{"id": 7, "url": url}],
                  steps=[{"pick": "app-1", "settles": 4}, *steps], **spec)


def test_a_picked_draft_with_full_automation_on_shows_apply(tmp_path):
    out = _on_form(tmp_path, [])
    shot = out["shots"][-1]
    assert _primary(shot) == ["Apply"]
    assert PROMISE in _text(shot["regions"]["rail"])
    # The unmatched page offered the pick, and nothing was written by making it.
    assert _order(out) == []


def test_a_picked_draft_with_full_automation_off_shows_no_apply(tmp_path):
    out = _on_form(tmp_path, [], api=_picked(**{"/api/settings/auto-apply": AUTOMATION_OFF}))
    assert "Apply" not in _labels(out["shots"][-1])


@pytest.mark.parametrize("status", ["applied", "interview"])
def test_a_picked_application_that_is_already_applied_shows_no_apply(tmp_path, status):
    out = _on_form(tmp_path, [], api=_picked(status=status))
    assert "Apply" not in _labels(out["shots"][-1])


def test_a_picked_job_already_submitted_shows_no_apply(tmp_path):
    api = _picked(**{"/api/jobs/job-1/detail": _job(application=_draft(), apply_url=None,
                                                    proposal_status="submitted")})
    assert "Apply" not in _labels(_on_form(tmp_path, [], api=api)["shots"][-1])


def test_a_picked_job_that_is_queued_shows_apply_alone(tmp_path):
    api = _picked(**{"/api/jobs/job-1/detail": _job(application=_draft(), apply_url=None,
                                                    proposal_id="prop-1", proposal_status="accepted")})
    assert _primary(_on_form(tmp_path, [], api=api, queue_button=True)["shots"][-1]) == ["Apply"]


def test_a_refresh_after_a_pick_still_knows_the_picked_job_is_queued(tmp_path):
    """The pick comes back from the browser's memory on a reload (a wizard's next page): the facts Apply
    needs are read for it again, not only when the pick was made."""
    api = _picked(**{"/api/jobs/job-1/detail": _job(application=_draft(), apply_url=None,
                                                    proposal_id="prop-1", proposal_status="accepted")})
    out = _on_form(tmp_path, [{"id": "refresh-page", "settles": 4}], api=api, queue_button=True)
    assert out["shots"][-1]["facts"]["apply"]["queued"] is True
    assert _primary(out["shots"][-1]) == ["Apply"]


def test_apply_on_a_picked_draft_runs_in_this_tab_and_never_opens_the_jobs_links(tmp_path):
    out = _on_form(tmp_path, [{"foot": "Apply"}])
    [seed] = out["seeds"]
    assert seed["openUrl"] == FORM_URL and seed["inPlace"] is True
    assert (seed["jobId"], seed["applicationId"], seed["baseSlug"]) == ("job-1", "app-1", "ai_ml_engineer")
    assert out["updates"] == [] and out["created"] == []
    # The draft is the user's own: nothing is tailored, rendered or made.
    assert _api(out, "POST", "/quick-tailor") == [] and _api(out, "POST", "/from-base") == []
    assert _api(out, "POST", "/render") == []
    assert [one for one in _order(out) if "/api/jobs" in one] == ["PATCH /api/jobs/job-1"]


def test_a_picked_draft_runs_a_whole_record_here_on_this_pages_host(tmp_path):
    site = [page("step", 1, host=FORM_HOST), page("review", 2, host=FORM_HOST)]
    out = _on_form(tmp_path, [{"foot": "Apply", "settles": 5}], realRun=True, site=site)
    assert out["updates"] == [] and out["created"] == []
    [record] = out["shots"][-1]["facts"]["runs"]
    assert (record["status"], record["startTabId"], record["jobId"]) == ("ready", 7, "job-1")
    assert record["hosts"][0] == FORM_HOST and record["openUrl"] == FORM_URL
    assert len(out["fills"]) >= 1
    assert not [msg for msg in out["broadcasts"] if "submit" in msg["message"]["type"]]


def test_a_run_here_does_not_press_a_postings_apply_link(tmp_path):
    """The press rule is for a tab the run opened. This tab was the user's, so a posting page parks."""
    posting = {**page("step", 1, host=FORM_HOST), "summary": {**page("step", 1, host=FORM_HOST)["summary"],
               "fillable": 0, "hasApplyLink": True, "applyId": "apply-1", "buttons": []}}
    out = _on_form(tmp_path, [{"foot": "Apply", "settles": 4}], realRun=True, site=[posting, STEP1])
    [record] = out["shots"][-1]["facts"]["runs"]
    assert (record["status"], record["why"]) == ("parked", "posting")
    assert not [msg for msg in out["broadcasts"] if msg["message"].get("type") == "page_advance"]


def test_the_page_is_saved_as_the_jobs_apply_link_without_its_fragment_or_tokens(tmp_path):
    out = _on_form(tmp_path, [{"foot": "Apply"}], url=f"{FORM_URL}?token=abc123&utm_source=x#section-2")
    [patch] = _api(out, "PATCH", "/api/jobs/job-1")
    assert _body(patch) == {"apply_url": FORM_URL}
    # The run still reads the page as it is.
    assert out["seeds"][0]["openUrl"] == f"{FORM_URL}?token=abc123&utm_source=x#section-2"


def test_the_one_query_key_that_names_a_posting_is_kept_in_the_saved_link(tmp_path):
    page_url = f"https://{FORM_HOST}/careers?token=abc&gh_jid=555&utm_source=x"
    out = _on_form(tmp_path, [{"foot": "Apply"}], url=page_url)
    [patch] = _api(out, "PATCH", "/api/jobs/job-1")
    assert _body(patch) == {"apply_url": f"https://{FORM_HOST}/careers?gh_jid=555"}


WD_FORM = "https://acme.wd5.myworkdayjobs.com/en-US/careers/job/Remote/Data-Scientist_JR1234/apply/applyManually"


@pytest.mark.parametrize("url", [
    f"https://{FORM_HOST}/careers/apply",
    f"https://{FORM_HOST}/careers/apply/step2",
    "https://jobs.shared.test/apply?org=acme",
    "https://acme.wd5.myworkdayjobs.com/en-US/careers/login",
    "https://www.linkedin.com/jobs/view/4001/apply",
], ids=["no-id", "wizard-step", "tenant-in-query", "sign-in-page", "job-board"])
def test_a_page_that_names_no_posting_is_never_saved_as_the_apply_link(tmp_path, url):
    out = _on_form(tmp_path, [{"foot": "Apply"}], url=url)
    assert _api(out, "PATCH", "/api/jobs/job-1") == []
    # Apply itself still runs here.
    assert len(out["seeds"]) == 1 and out["seeds"][0]["inPlace"] is True


def test_a_workday_style_apply_page_is_saved(tmp_path):
    out = _on_form(tmp_path, [{"foot": "Apply"}], url=WD_FORM)
    [patch] = _api(out, "PATCH", "/api/jobs/job-1")
    assert _body(patch) == {"apply_url": WD_FORM}


def test_apply_uses_the_draft_the_user_picked_not_the_jobs_newest_application(tmp_path):
    newest = _draft(id="app-2")
    api = _picked(**{
        "/api/jobs/job-1/detail": _job(application=newest, apply_url=None),
        "GET /api/applications/app-2": _reply(newest),
        "POST /api/proposals": _reply(PROPOSAL),
    })
    out = _on_form(tmp_path, [{"foot": "Apply"}], api=api)
    [seed] = out["seeds"]
    assert (seed["applicationId"], seed["baseSlug"]) == ("app-1", "ai_ml_engineer")
    link = [msg for msg in _api(out, "POST", "/api/proposals") if "application_id" in _body(msg)]
    assert [_body(msg)["application_id"] for msg in link] == ["app-1"]
    assert _api(out, "POST", "/quick-tailor") == [] and _api(out, "POST", "/from-base") == []


def test_the_picked_drafts_own_pdf_decides_whether_it_is_rendered(tmp_path):
    api = _picked(**{"GET /api/applications/app-1": _reply(_draft(pdf=False)),
                     "/api/jobs/job-1/detail": _job(application=_draft(id="app-2"), apply_url=None)})
    out = _on_form(tmp_path, [{"foot": "Apply"}], api=api)
    assert len(_api(out, "POST", "/api/applications/app-1/render")) == 1
    assert out["seeds"][0]["applicationId"] == "app-1"


@pytest.mark.parametrize("draft", [_draft(job_id="job-9"), _draft(status="applied")],
                         ids=["another-jobs-draft", "no-longer-a-draft"])
def test_a_picked_draft_that_is_not_this_jobs_open_draft_stops_before_anything_is_written(tmp_path, draft):
    # By the call: the draft may have been applied in the web app since the footer was drawn.
    out = _on_form(tmp_path, [{"call": "applyJob", "settles": 2}],
                   api=_picked(**{"GET /api/applications/app-1": _reply(draft)}))
    assert out["seeds"] == [] and _order(out) == []
    assert "Pick it again" in _note(out["shots"][-1])


def test_a_deleted_picked_draft_stops_the_same_way(tmp_path):
    gone = {"ok": False, "status": 404, "error": "Application not found"}
    # The pick read it fine; it was deleted in the web app before the press.
    out = _on_form(tmp_path, [{"foot": "Apply"}],
                   api=_picked(**{"GET /api/applications/app-1": [_reply(_draft()), gone]}))
    assert out["seeds"] == [] and _order(out) == []
    # The reload that follows the stop reads the draft again and says the panel's own sentence.
    assert "no longer exists" in _note(out["shots"][-1])


def test_a_binding_taken_from_a_run_record_offers_no_apply_on_whatever_page_the_tab_shows(tmp_path):
    """Skip job A, browse to job B's form: the run's claim on the tab is not a pick for this page."""
    record = _run_record(7, "stopped", why="user", jobId="job-0", applicationId="app-0")
    out = _apply(tmp_path, api=_picked(), tabs=[{"id": 7, "url": FORM_URL}], page=FORM_PAGE,
                 sessionStored={"queueRun": [record]},
                 # Refresh remembers a claim; and a press that got through would find the page unpicked.
                 steps=[{"id": "refresh-page", "settles": 4}, {"call": "applyJob", "settles": 2}])
    assert out["seeds"] == [] and _order(out) == []
    shot = out["shots"][-1]
    assert "Apply" not in _labels(shot)
    assert PROMISE not in _text(shot["regions"]["rail"])
    # And the claim is not written down as a pick that a later load would restore.
    assert not [write for write in out["writes"] if "widget.session" in write]
    # Nothing is read for a job the page was never picked for.
    assert not [msg for msg in out["sent"] if msg["type"] == "api" and "/api/jobs/job-0" in msg["path"]]


def test_the_promise_line_is_only_where_the_apply_button_is(tmp_path):
    for api in (_picked(status="applied"),
                _picked(**{"/api/jobs/job-1/detail": _job(application=_draft(), apply_url=None,
                                                          proposal_status="submitted")})):
        rail = _text(_on_form(tmp_path, [], api=api)["shots"][-1]["regions"]["rail"])
        assert PROMISE not in rail


def test_a_job_that_has_an_apply_link_keeps_it(tmp_path):
    api = _picked(**{"/api/jobs/job-1/detail": _job(application=_draft(), apply_url=APP_URL)})
    out = _on_form(tmp_path, [{"foot": "Apply"}], api=api)
    assert _api(out, "PATCH", "/api/jobs/job-1") == []
    assert len(out["seeds"]) == 1 and out["seeds"][0]["openUrl"] == FORM_URL


def test_a_refused_link_save_still_runs(tmp_path):
    refusal = {"ok": False, "status": 409, "error": "This job is with your bot."}
    out = _on_form(tmp_path, [{"foot": "Apply"}], api=_picked(**{"PATCH /api/jobs/job-1": refusal}))
    assert len(_api(out, "PATCH", "/api/jobs/job-1")) == 1
    assert len(out["seeds"]) == 1


def test_an_exact_match_apply_is_unchanged_and_saves_no_link(tmp_path):
    out = _apply(tmp_path, api=_bound(), steps=[{"foot": "Apply"}])
    [seed] = out["seeds"]
    assert not seed.get("inPlace") and seed["openUrl"] == APP_URL
    assert _api(out, "PATCH", "/api/jobs/job-1") == []


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


# ---------- the Apply checklist, its Stop, and the locked base list ----------
# Apply is several round trips; the Job card shows each step as it happens (a spinner, a tick, or a mark and
# a short reason), the footer says each one through its live note, and Stop ends the press between steps.

NO_MATCH = _reply({"match": "none", "job": None, "application": None})
SAVED_MATCH = _reply({"match": "exact", "job": JOB, "application": None})
PICK_NOTE = "Pick a resume to apply with."


def _rows(ai, ds):
    return [{"target_type": "base_resume", "target_id": "ai_ml_engineer", "phase": "base", "composite": ai},
            {"target_type": "base_resume", "target_id": "data_scientist", "phase": "base", "composite": ds}]


def _flow(rows=None, **api):
    """An unsaved posting that becomes a saved one: the match says none, then (the panel re-reads it after the
    save) exact; the scorer answers the same rows to the POST and to the later read."""
    rows = SCORE_ROWS if rows is None else rows
    return _fresh(**{"/api/jobs/match": [NO_MATCH, SAVED_MATCH], "GET /api/ats-scores": _reply(rows),
                     "POST /api/ats-scores": _reply(rows), **api})


def _companion(auto_pick=True, stop_each_step=False):
    return {"/api/settings/companion-apply": _reply(
        {"key": "companion_apply", "value": {"auto_pick": auto_pick, "stop_each_step": stop_each_step}})}


def _lines(shot):
    """The checklist as painted: `[(state, words)]` in order. The words are the line's own text."""
    lists = _by_class(shot["regions"]["rail"], "apply-steps")
    if not lists:
        return []
    return [(item["class"], _by_class(item, "what")[0]["text"]) for item in lists[0]["children"]]


def _buttons(shot, region="foot"):
    return [one for one in _walk(shot["regions"][region]) if one["tag"] == "BUTTON"]


def _stop_button(shot):
    return [one for one in _buttons(shot) if "stop" in one["class"].split()]


def _rows_in_rail(shot):
    return [one for one in _walk(shot["regions"]["rail"])
            if one["tag"] == "BUTTON" and one["attrs"].get("role") == "radio"]


def test_the_checklist_lists_each_step_in_order_with_a_tick_and_a_square_on_the_resume(tmp_path):
    out = _apply(tmp_path, api=_fresh(), hold=["POST /api/proposals"], holdSkip=1,
                 steps=[{"foot": "Apply"}, {"release": True, "settles": 2}])
    mid, end = out["shots"][1], out["shots"][-1]
    assert _lines(mid) == [
        ("done", "Saving the job"), ("done", "Scoring your resumes"), ("done", "Using AI/ML Engineer (72)"),
        ("done", "Queueing the job"), ("done", "Tailoring the resume"), ("run", "Linking the resume to the job")]
    # The resume's square is on its line; a name is never bare.
    [using] = [item for item in _by_class(mid["regions"]["rail"], "what") if item["text"].startswith("Using ")]
    assert [kid["class"] for kid in using["children"]] == ["swatch"]
    assert _names_without_a_square(mid, [row["display_name"] for row in HUED_RESUMES if row["color_hue"]]) == []
    # The run takes over: the checklist is gone and the list is the user's again.
    assert _lines(end) == [] and len(out["seeds"]) == 1
    assert not any(one["disabled"] for one in _rows_in_rail(end))


def test_a_step_that_was_not_needed_is_not_listed(tmp_path):
    api = _saved(**{"/api/jobs/job-1/detail": _job(proposal_id="prop-1", proposal_status="accepted",
                                                   application=_draft())})
    out = _apply(tmp_path, api=api, hold=["POST /api/proposals"], steps=[{"foot": "Apply"}])
    assert _lines(out["shots"][1]) == [
        ("done", "Using AI/ML Engineer (72)"), ("done", "Using your resume for this job"),
        ("run", "Linking the resume to the job")]


def test_a_draft_without_a_pdf_adds_the_pdf_step(tmp_path):
    api = _saved(**{"/api/jobs/job-1/detail": _job(application=_draft(pdf=False)),
                    "POST /api/applications/app-1/render": _reply({"pdf_path": "renders/Ada.pdf"})})
    out = _apply(tmp_path, api=api, hold=["/api/applications/app-1/render"], steps=[{"foot": "Apply"}])
    assert _lines(out["shots"][1])[-1] == ("run", "Making the PDF")


def test_the_footer_note_says_each_step_and_the_checklist_is_a_labelled_list(tmp_path):
    out = _apply(tmp_path, api=_fresh(), hold=["POST /api/proposals"], holdSkip=1, steps=[{"foot": "Apply"}])
    mid = out["shots"][1]
    # The note is the panel's one persistent live region (the rail is rebuilt on every paint).
    [note] = _by_class(mid["regions"]["foot"], "note")
    assert note["attrs"]["aria-live"] == "polite"
    assert note["text"] == "Linking the resume to the job…"
    [checklist] = _by_class(mid["regions"]["rail"], "apply-steps")
    assert checklist["tag"] == "OL" and checklist["attrs"]["aria-label"] == "Preparing to apply"
    # A state is a word as well as a shape.
    [tick, *_] = checklist["children"]
    assert _by_class(tick, "vh")[0]["text"] == "Done: "
    assert _by_class(checklist["children"][-1], "vh")[0]["text"] == "In progress: "


def test_stop_is_a_button_with_a_clear_name_while_apply_prepares(tmp_path):
    out = _apply(tmp_path, api=_fresh(), hold=["POST /api/proposals"], holdSkip=1,
                 steps=[{"foot": "Apply"}, {"release": True, "settles": 2}])
    [stop] = _stop_button(out["shots"][1])
    assert _text(stop) == "Stop" and stop["attrs"]["aria-label"] == "Stop preparing to apply"
    assert not stop["disabled"]
    assert _stop_button(out["shots"][0]) == [] and _stop_button(out["shots"][-1]) == []


def test_stop_after_scoring_leaves_no_proposal_and_no_tailoring(tmp_path):
    out = _apply(tmp_path, api=_flow(), hold=["POST /api/ats-scores"],
                 steps=[{"foot": "Apply"}, {"foot": "Stop"}, {"release": True, "settles": 3}])
    # Held mid-score: the first save is done, scoring is running, and Stop has been heard.
    assert _lines(out["shots"][1]) == [("done", "Saving the job"), ("run", "Scoring your resumes")]
    [pressed] = _stop_button(out["shots"][2])
    assert _text(pressed) == "Stopping…" and pressed["attrs"]["aria-disabled"] == "true"
    end = out["shots"][-1]
    assert _order(out) == ["POST /api/jobs", "POST /api/ats-scores"]
    assert out["seeds"] == []
    assert _lines(end) == [("done", "Saving the job"), ("done", "Scoring your resumes"),
                           ("stop-line", "Stopped after scoring your resumes.")]
    assert _note(end) == "Stopped after scoring your resumes."
    # What was done stays done, and Apply is there to press again.
    assert _stop_button(end) == [] and _labels(end) == ["Apply"]
    assert not [one for one in _buttons(end) if one["disabled"] and _text(one) == "Apply"]


def test_stop_between_steps_ends_the_press_without_cancelling_a_call_already_sent(tmp_path):
    # Held at the quick tailor: the call is sent, Stop is pressed, and it still completes and is kept.
    out = _apply(tmp_path, api=_fresh(), hold=["/quick-tailor"],
                 steps=[{"foot": "Apply"}, {"foot": "Stop"}, {"release": True, "settles": 3}])
    assert len(_api(out, "POST", "/quick-tailor")) == 1
    end = out["shots"][-1]
    assert _lines(end)[-2:] == [("done", "Tailoring the resume"), ("stop-line", "Stopped after tailoring the resume.")]
    assert _api(out, "POST", "/render") == [] and out["seeds"] == []
    # Linking is a write after the queue: it was never sent.
    assert [msg for msg in _api(out, "POST", "/api/proposals") if "application_id" in _body(msg)] == []


def test_a_step_that_fails_is_crossed_with_a_short_reason_and_no_server_words(tmp_path):
    api = _fresh(**{"/quick-tailor": {"ok": False, "status": 500, "error": "Traceback secret-detail-9"}})
    out = _apply(tmp_path, api=api, steps=[{"foot": "Apply"}])
    shot = out["shots"][1]
    assert _lines(shot)[-1] == ("fail", "Tailoring the resume")
    [failed] = [item for item in _by_class(shot["regions"]["rail"], "apply-steps")[0]["children"]
                if item["class"] == "fail"]
    assert _by_class(failed, "why")[0]["text"] == "Couldn't tailor"
    assert _by_class(failed, "vh")[0]["text"] == "Didn't finish: "
    assert "secret-detail-9" not in _text(shot["regions"]["rail"]) + _text(shot["regions"]["foot"])
    assert _stop_button(shot) == []
    assert out["seeds"] == []


def test_the_base_list_is_locked_while_apply_works_and_a_click_changes_nothing(tmp_path):
    api = _saved()
    out = _apply(tmp_path, api=api, hold=["POST /api/proposals"], holdSkip=1,
                 steps=[{"foot": "Apply"}, {"id": "base-data_scientist"}, {"release": True, "settles": 2}])
    before, during, after = out["shots"][0], out["shots"][2], out["shots"][-1]
    rows = _rows_in_rail(before)
    assert len(rows) == 3 and not any(row["disabled"] for row in rows)
    rows = _rows_in_rail(during)
    assert len(rows) == 3 and all(row["disabled"] and row["attrs"]["aria-disabled"] == "true" for row in rows)
    [group] = [one for one in _walk(during["regions"]["rail"]) if one["attrs"].get("role") == "radiogroup"]
    assert group["attrs"]["aria-disabled"] == "true"
    # The click on a locked row (the harness fires it even though a browser would not) is refused.
    assert during["facts"]["baseSlug"] == "ai_ml_engineer"
    assert [row["attrs"]["aria-checked"] for row in rows if row["id"] == "base-ai_ml_engineer"] == ["true"]
    assert not any(row["disabled"] for row in _rows_in_rail(after))
    # The two ways round are locked with it.
    assert all(one["disabled"] for one in _buttons(during, "rail"))


# ---------- the pick: only on a clear win ----------


@pytest.mark.parametrize("ai,ds,picked", [
    (71.8, 63.6, "ai_ml_engineer"),   # clear: above the floor, ahead by more than the margin
    (60, 55, "ai_ml_engineer"),       # exactly the floor, exactly the margin
    (45, 44, None),                    # a close call, both under the floor
    (80, 77, None),                    # high, but the lead is under the margin
    (50, 20, None),                    # a big lead, but under the floor
    (65, None, "ai_ml_engineer"),     # a lone scored base has no rival to lead
], ids=["clear", "at-the-limits", "close-call", "thin-lead", "low-top", "lone"])
def test_the_panel_preselects_a_resume_only_on_a_clear_win(tmp_path, ai, ds, picked):
    rows = [row for row in _rows(ai, ds or 0) if not (ds is None and row["target_id"] == "data_scientist")]
    shot = _apply(tmp_path, api=_saved(**{"GET /api/ats-scores": _reply(rows)}))["shots"][0]
    assert shot["facts"]["baseSlug"] == picked
    checked = [row["id"] for row in _rows_in_rail(shot) if row["attrs"]["aria-checked"] == "true"]
    assert checked == ([f"base-{picked}"] if picked else [])
    assert [PICK_NOTE.rstrip(".") in _text(shot["regions"]["rail"]),
            _buttons(shot)[-1]["disabled"]] == [picked is None] * 2


def test_the_pick_uses_the_users_floor_and_margin_from_auto_apply(tmp_path):
    settings = _reply({"key": "auto_apply", "value": {"full_automation": True, "auto_pick_floor": 40,
                                                         "auto_pick_margin": 0.5}})
    api = _saved(**{"GET /api/ats-scores": _reply(_rows(45, 44)), "/api/settings/auto-apply": settings})
    assert _apply(tmp_path, api=api)["shots"][0]["facts"]["baseSlug"] == "ai_ml_engineer"


def test_a_close_call_stops_apply_after_scoring_and_asks_with_the_list_unlocked(tmp_path):
    out = _apply(tmp_path, api=_flow(_rows(45, 44)), steps=[{"foot": "Apply", "settles": 3}])
    end = out["shots"][-1]
    assert _order(out) == ["POST /api/jobs", "POST /api/ats-scores"]
    assert out["seeds"] == []
    assert _lines(end) == [("done", "Saving the job"), ("done", "Scoring your resumes"), ("wait", "Waiting for your pick")]
    assert _note(end) == PICK_NOTE
    rows = _rows_in_rail(end)
    assert len(rows) == 3 and not any(row["disabled"] for row in rows)
    assert [row["attrs"]["aria-checked"] for row in rows] == ["false"] * 3
    assert _foot(end)[-1][0] == "Apply" and _buttons(end)[-1]["disabled"]


def test_picking_after_the_ask_lets_apply_go_on_with_that_resume(tmp_path):
    out = _apply(tmp_path, api=_flow(_rows(45, 44)),
                 steps=[{"foot": "Apply", "settles": 3}, {"id": "base-data_scientist", "settles": 2},
                        {"foot": "Apply", "settles": 3}])
    picked = out["shots"][2]
    # A new pick starts the next press: the old checklist is gone and Apply is live.
    assert _lines(picked) == []
    assert not _buttons(picked)[-1]["disabled"]
    assert _body(_api(out, "POST", "/quick-tailor")[0]) == {"base_resume": "data_scientist"}
    assert out["seeds"][0]["baseSlug"] == "data_scientist"
    assert [_lines(out["shots"][3])] == [[]]


def test_with_choose_for_me_off_nothing_is_preselected_and_an_unsaved_posting_offers_save_job(tmp_path):
    api = _flow(**_companion(auto_pick=False))
    out = _apply(tmp_path, api=api, steps=[{"foot": "Save job", "settles": 3}])
    first, end = out["shots"][0], out["shots"][-1]
    assert _labels(first) == ["Save job"] and _order(out) == ["POST /api/jobs", "POST /api/ats-scores"]
    # Saved and scored; the best match is named, but nothing is chosen, and Apply waits for the user.
    assert end["facts"]["baseSlug"] is None and out["seeds"] == []
    assert [row["attrs"]["aria-checked"] for row in _rows_in_rail(end)] == ["false"] * 3
    assert _foot(end)[-1][0] == "Apply" and _buttons(end)[-1]["disabled"]
    assert _lines(end)[-1] == ("wait", "Waiting for your pick")


def test_with_choose_for_me_off_a_saved_job_waits_for_the_users_pick_then_applies_with_it(tmp_path):
    api = _saved(**_companion(auto_pick=False))
    out = _apply(tmp_path, api=api, steps=[{"id": "base-data_scientist"}, {"foot": "Apply"}])
    first, picked = out["shots"][0], out["shots"][1]
    assert first["facts"]["baseSlug"] is None and _buttons(first)[-1]["disabled"]
    assert PICK_NOTE.rstrip(".") in _text(first["regions"]["rail"])
    assert not _buttons(picked)[-1]["disabled"]
    assert _body(_api(out, "POST", "/quick-tailor")[0]) == {"base_resume": "data_scientist"}


def test_a_picked_resume_survives_a_rescore_and_is_not_replaced_by_the_best(tmp_path):
    api = _saved(**_companion(auto_pick=False), **{"POST /api/ats-scores": _reply(SCORE_ROWS)})
    out = _apply(tmp_path, api=api, steps=[{"id": "base-data_scientist"}, {"body": "Update scores", "settles": 2}])
    assert out["shots"][-1]["facts"]["baseSlug"] == "data_scientist"


# ---------- "Stop after each step": three presses, the yes at the third ----------


def _stepwise(**api):
    return {**_companion(stop_each_step=True), **api}


def test_save_job_is_the_first_press_and_saves_and_scores_without_queueing(tmp_path):
    out = _apply(tmp_path, api=_flow(**_stepwise()), steps=[{"foot": "Save job", "settles": 3}])
    assert _labels(out["shots"][0]) == ["Save job"]
    assert _order(out) == ["POST /api/jobs", "POST /api/ats-scores"]
    end = out["shots"][-1]
    assert _lines(end) == [("done", "Saving the job"), ("done", "Scoring your resumes"),
                           ("done", "Using AI/ML Engineer (72)")]
    # The next press is named for what it does.
    assert _labels(end) == ["Tailor resume"]
    assert out["seeds"] == []


def test_tailor_resume_makes_the_resume_and_stops_before_the_queue_and_the_run(tmp_path):
    out = _apply(tmp_path, api=_saved(**_stepwise()), steps=[{"foot": "Tailor resume", "settles": 3}])
    assert _labels(out["shots"][0]) == ["Tailor resume"]
    assert _order(out) == ["POST /api/jobs/job-1/quick-tailor"]
    assert _api(out, "POST", "/api/proposals") == [] and _api(out, "PATCH", "/api/proposals") == []
    assert out["seeds"] == []
    assert "Press Start filling" in _note(out["shots"][-1])


def test_make_pdf_renders_the_draft_and_stops(tmp_path):
    bound = _bound(pdf=False, **_stepwise())
    out = _apply(tmp_path, api=bound, steps=[{"foot": "Make PDF", "settles": 3}])
    assert _primary(out["shots"][0]) == ["Make PDF"]
    assert _order(out) == ["POST /api/applications/app-1/render"]
    assert out["seeds"] == []


def test_start_filling_is_where_the_yes_is_given_and_the_run_starts(tmp_path):
    out = _apply(tmp_path, api=_bound(**_stepwise()), steps=[{"foot": "Start filling", "settles": 3}])
    assert _primary(out["shots"][0]) == ["Start filling"]
    assert _order(out) == ["POST /api/proposals", "PATCH /api/proposals/prop-1", "POST /api/proposals"]
    [accepted] = _api(out, "PATCH", "/api/proposals/prop-1")
    assert _body(accepted) == {"status": "accepted", "consent": {"channel": "companion"}}
    assert len(out["seeds"]) == 1 and out["seeds"][0]["applicationId"] == "app-1"


def test_the_three_presses_in_a_row_queue_nothing_before_the_third(tmp_path):
    # The match reads: no job, the saved job, then the saved job with its new draft (and the draft has a PDF).
    bound = {"match": "exact", "job": JOB, "application": {"id": "app-1", "status": "draft",
                                                           "base_resume": "ai_ml_engineer"}}
    api = _flow(**_stepwise(), **{
        "/api/jobs/match": [NO_MATCH, SAVED_MATCH, _reply(bound)],
        "GET /api/applications/app-1": _reply(_draft()),
        "/api/jobs/job-1/detail": [_job(), _job(), _job(), _job(application=_draft()),
                                   _job(application=_draft())]})
    out = _apply(tmp_path, api=api, steps=[{"foot": "Save job", "settles": 3}, {"foot": "Tailor resume", "settles": 3},
                                           {"foot": "Start filling", "settles": 3}])
    assert [_primary(shot) for shot in out["shots"][:3]] == [["Save job"], ["Tailor resume"], ["Start filling"]]
    order = _order(out)
    assert order[:3] == ["POST /api/jobs", "POST /api/ats-scores", "POST /api/jobs/job-1/quick-tailor"]
    assert "POST /api/proposals" not in order[:3] and len(out["seeds"]) == 1


def test_a_stepwise_footer_never_names_a_press_the_job_cannot_take(tmp_path):
    # A draft the user made in the web app: the first press this panel offers is the PDF or the run.
    assert _primary(_apply(tmp_path, api=_bound(pdf=True, **_stepwise()))["shots"][0]) == ["Start filling"]
    assert _primary(_apply(tmp_path, api=_bound(pdf=False, **_stepwise()))["shots"][0]) == ["Make PDF"]


# ---------- how Apply is set, in one line ----------


@pytest.mark.parametrize("pick,stop,words", [
    (True, False, "Apply picks the resume and runs every step."),
    (True, True, "Apply picks the resume and stops after each step."),
    (False, False, "You pick the resume. Apply runs every step."),
    (False, True, "You pick the resume. Apply stops after each step."),
])
def test_the_job_step_says_how_apply_is_set_with_a_link_to_the_switches(tmp_path, pick, stop, words):
    for api in (_saved(**_companion(pick, stop)), _fresh(**_companion(pick, stop))):
        shot = _apply(tmp_path, api=api)["shots"][0]
        [line] = [one for one in _by_class(shot["regions"]["rail"], "sub") if words in one["text"]]
        [link] = [one for one in line["children"] if one["tag"] == "A"]
        assert link["href"] == "http://localhost:3000/settings#form-filling"
        assert link["attrs"]["aria-label"] == "Change in Settings (opens in a new tab)"
        assert PROMISE in _text(shot["regions"]["rail"])


def test_a_setting_the_panel_cannot_read_leaves_apply_picking_and_running_every_step(tmp_path):
    shot = _apply(tmp_path, api=_saved())["shots"][0]
    assert "Apply picks the resume and runs every step." in _text(shot["regions"]["rail"])
    assert _labels(shot) == ["Apply"]


# ---------- the review's fixes ----------


def test_a_stop_pressed_before_a_rebind_still_ends_the_press(tmp_path):
    """The rebind resets the page's facts, Stop flag included; the press from the tab left behind must
    still count as stopped rather than carry on to render, link and run."""
    other = "https://other.example.test/jobs/2"
    api = {"other.example.test": NO_MATCH, **_fresh(**{"/quick-tailor": _reply({**TAILORED, "pdf_ready": False})})}
    out = _apply(tmp_path, api=api, tabs=[{"id": 7, "url": BOARD_URL}, {"id": 8, "url": other}],
                 tabUrls={"7": BOARD_URL, "8": other}, hold=["/quick-tailor"],
                 steps=[{"foot": "Apply"}, {"foot": "Stop"}, {"activate": 8}, {"release": True, "settles": 3}])
    assert len(_api(out, "POST", "/quick-tailor")) == 1
    assert _api(out, "POST", "/render") == []
    assert [msg for msg in _api(out, "POST", "/api/proposals") if "application_id" in _body(msg)] == []
    assert out["seeds"] == []


def test_focus_on_stop_survives_a_step_repaint(tmp_path):
    out = _apply(tmp_path, api=_fresh(), hold=["POST /api/proposals", "/quick-tailor"], holdSkip=1,
                 steps=[{"foot": "Apply"}, {"focus": "apply-stop"}, {"release": True}])
    before, after = out["shots"][1], out["shots"][-1]
    assert _lines(before)[-1] == ("run", "Tailoring the resume")
    assert _lines(after)[-1] == ("run", "Linking the resume to the job")
    assert after["focused"] == "apply-stop"
    assert [one["id"] for one in _stop_button(after)] == ["apply-stop"]


def test_a_stop_that_has_been_pressed_keeps_focus_and_says_so_without_going_disabled(tmp_path):
    out = _apply(tmp_path, api=_flow(), hold=["POST /api/ats-scores"],
                 steps=[{"foot": "Apply"}, {"focus": "apply-stop"}, {"id": "apply-stop"}])
    [pressed] = _stop_button(out["shots"][-1])
    assert _text(pressed) == "Stopping…" and pressed["attrs"]["aria-disabled"] == "true"
    assert not pressed["disabled"] and out["shots"][-1]["focused"] == "apply-stop"


def test_the_fill_stop_has_a_stable_id_too():
    assert 'stop.id = "fill-stop";' in PANEL_SOURCE


def test_save_job_works_after_a_session_restore_set_a_job_the_backend_did_not_match(tmp_path):
    """A remembered pick names a job (so `card.job` is set) on a page the backend does not match: the
    footer says Save job and the press must save, not do nothing."""
    entry = {"origin": "https://board.example.test", "tenant": "https://board.example.test/jobs",
             "at": 1, "jobId": "job-1", "company": "Acme", "title": "Data Scientist",
             "baseSlug": "ai_ml_engineer", "baseArmed": False}
    api = _flow(**_companion(auto_pick=True, stop_each_step=True))
    api["/api/jobs/match"] = [NO_MATCH, SAVED_MATCH]
    out = _apply(tmp_path, api=api, stored={"widget.session": entry}, steps=[{"foot": "Save job", "settles": 3}])
    assert _labels(out["shots"][0]) == ["Save job"]
    assert _order(out)[:2] == ["POST /api/jobs", "POST /api/ats-scores"]


def test_stop_between_saving_and_scoring_ends_before_the_score_is_asked(tmp_path):
    out = _apply(tmp_path, api=_flow(), hold=["POST /api/jobs"],
                 steps=[{"foot": "Apply"}, {"foot": "Stop"}, {"release": True, "settles": 3}])
    assert _order(out) == ["POST /api/jobs"]
    end = out["shots"][-1]
    assert _lines(end) == [("done", "Saving the job"), ("stop-line", "Stopped after saving the job.")]


def test_apply_does_nothing_while_a_checklist_is_live(tmp_path):
    live = {"applySteps": {"live": True, "stopped": None, "lines": []}}
    out = _apply(tmp_path, api=_saved(), steps=[{"write": live}, {"call": "applyJob", "settles": 2}])
    assert _order(out) == [] and out["seeds"] == []


def test_stop_is_gone_while_the_press_re_reads_the_page_it_ended_on(tmp_path):
    # Stopped at the tailoring, which is inside the span that ends in a reload; the reload is held.
    out = _apply(tmp_path, api=_fresh(), hold=["/quick-tailor", "/api/jobs/match"], holdSkip=1,
                 steps=[{"foot": "Apply"}, {"foot": "Stop"}, {"release": True, "settles": 2}])
    assert _stop_button(out["shots"][-1]) == []
    assert _lines(out["shots"][-1])[-1] == ("stop-line", "Stopped after tailoring the resume.")


def test_the_stops_that_crossed_nothing_now_cross_a_line(tmp_path):
    bot = _owned(owned_here=False, owner="bot")
    held = _apply(tmp_path, api=_saved(**{"/api/jobs/job-1/detail": _job(ownership=bot)}), steps=[{"foot": "Apply"}])
    assert _lines(held["shots"][1])[-1] == ("fail", "Using this copy of the job")
    sessions = _saved(**{"/api/tailoring-sessions?job_id": _reply([{"id": "sess-1", "status": "open"}])})
    first = _apply(tmp_path, api=sessions, steps=[{"foot": "Apply"}])
    assert _lines(first["shots"][1])[-1] == ("fail", "Tailoring the resume")
    detail = _job(apply_url=None, source_url=None, application=_draft())
    # A page the panel has no address for (the tab went away between the read and the press).
    nolink = _apply(tmp_path, api=_saved(**{"/api/jobs/job-1/detail": detail}),
                    steps=[{"write": {"url": ""}}, {"call": "applyJob", "settles": 2}])
    assert _lines(nolink["shots"][-1])[-1] == ("fail", "Opening the application")


def test_the_resume_line_does_not_claim_a_tailoring_the_panel_cannot_see(tmp_path):
    api = _saved(**{"/api/jobs/job-1/detail": _job(proposal_id="prop-1", proposal_status="accepted",
                                                   application=_draft())})
    out = _apply(tmp_path, api=api, hold=["POST /api/proposals"], steps=[{"foot": "Apply"}])
    assert ("done", "Using your resume for this job") in _lines(out["shots"][1])
    assert "tailored" not in str(_lines(out["shots"][1]))


def test_the_header_ring_asks_for_a_pick_when_scores_exist_and_nothing_is_picked(tmp_path):
    shot = _apply(tmp_path, api=_saved(**{"GET /api/ats-scores": _reply(_rows(45, 44))}))["shots"][0]
    assert "Pick a resume." in _text(shot["regions"]["identity"])
    assert "Not scored yet." not in _text(shot["regions"]["identity"])


def test_the_switches_are_fetched_with_the_automation_setting_and_ignored_when_it_is_off(tmp_path):
    api = _saved(**{"/api/settings/auto-apply": AUTOMATION_OFF, "GET /api/ats-scores": _reply(_rows(45, 44)),
                    **_companion(auto_pick=False)})
    out = _apply(tmp_path, api=api)
    paths = [msg["path"] for msg in out["sent"] if msg["type"] == "api"]
    assert paths.index("/api/settings/companion-apply") == paths.index("/api/settings/auto-apply") + 1
    # With automation off the best match is preselected as it always was, whatever the switch says.
    assert out["shots"][0]["facts"]["baseSlug"] == "ai_ml_engineer"


def test_a_disabled_apply_points_at_the_line_that_says_why(tmp_path):
    shot = _apply(tmp_path, api=_saved(**{"GET /api/ats-scores": _reply(_rows(45, 44))}))["shots"][0]
    [apply] = [one for one in _buttons(shot) if _text(one) == "Apply"]
    assert apply["disabled"] and apply["attrs"]["aria-describedby"] == "pick-prompt"
    [prompt] = [one for one in _walk(shot["regions"]["rail"]) if one["id"] == "pick-prompt"]
    assert PICK_NOTE.rstrip(".") in _text(prompt)


def test_apply_will_not_move_a_job_another_tab_is_running(tmp_path):
    """A second Apply (the user tailored a newer draft) would relink the proposal under the other tab's run."""
    api = _saved(**{"/api/jobs/job-1/detail": _job(proposal_id="prop-1", proposal_status="accepted",
                                                   application=_draft())})
    other = {**_run_record(8, "filling"), "proposalId": "prop-1"}
    out = _apply(tmp_path, api=api, tabs=[{"id": 7, "url": BOARD_URL}, {"id": 8, "url": APP_URL}],
                 steps=[{"seed": [other], "call": "applyJob", "settles": 2}])
    assert out["seeds"] == [] and _order(out) == []
    assert "Another tab" in _note(out["shots"][-1])
    # A run that is over does not hold the job.
    done = _apply(tmp_path, api=api, steps=[{"seed": [{**other, "status": "stopped"}], "call": "applyJob"}])
    assert len(done["seeds"]) == 1


def test_apply_shows_after_the_real_track_this_button_is_pressed_and_the_job_row_reopened(tmp_path):
    """From the Track stage (armed base, filled): the button the user presses, then the Job row's door."""
    entry = {"origin": "https://board.example.test", "tenant": "https://board.example.test/jobs",
             "at": 1, "jobId": "job-1", "company": "Acme", "title": "Data Scientist", "touched": True,
             "baseSlug": "ai_ml_engineer", "baseArmed": True}
    api = _saved(**{"POST /api/applications/from-base": _reply(_draft(pdf=False))})
    out = _apply(tmp_path, api=api, stored={"widget.session": entry},
                 steps=[{"body": "Track this application", "settles": 3}, {"id": "stg-open-job", "settles": 2}])
    assert _primary(out["shots"][-1]) == ["Apply"]
