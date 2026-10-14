"""The queued run in the side panel: one job, in the current tab, from its link to Ready to submit.

THE STATE MACHINE is `shared/queue-run.js` (tests/test_extension_queue_run.py); the page is
tests/browser. What these tests pin is the HOST: `panel/actions/run.js` building the driver's deps from
the panel's own doors, and `panel/runs.js` drawing a run's record as the Next card (direction C: Filling
page N, Needs you, Ready to submit, Marking applied in 8 s).

THE APPARATUS is `extension_panel_harness.py` plus a fake SITE: a list of pages the driver reads
(`page_classify`), one of which `page_advance` moves past, and a fill stub that reports instead of
touching a page (the fill engine has its own tests). Timers are collapsed by the harness; the 8 s
auto-mark is the one timer held back here, so "nothing is posted before 8 s" is askable.

THE RULES THESE PIN: Submit is never requested and no control in the card offers it; Stop sets the flag
`cancelled(record)` reads AND reaches the run's own tab; a tab switch cancels nothing; the password
appears nowhere but the one message that types it; answers a user types before Resume are always
remembered (never a prose box) and Undo puts the profile back; Skip this job sends nothing to the
server.
"""

import json

import pytest

from tests.extension_harness import run_node
from tests.extension_panel_harness import (
    BASE_RESUMES,
    PANEL_SOURCE,
    SETTINGS_REPLY,
    _PANEL_FAKES_JS,
    _by_class,
    _reply,
    _text,
    _walk,
)

START_URL = "https://jobs.acme.test/apply/step1"
SEED = {"proposalId": "prop-1", "jobId": "job-1", "applicationId": "app-1", "company": "Acme",
        "title": "Data Scientist", "baseSlug": "ai_ml_engineer", "openUrl": START_URL}
APPLICATION = {"id": "app-1", "job_id": "job-1", "status": "draft", "pdf_path": "renders/Ada.pdf",
               "base_resume": "ai_ml_engineer", "job_company": "Acme", "job_title": "Data Scientist"}

_BASE_SUMMARY = {"host": "jobs.acme.test", "stepKey": "", "applyId": None, "buttons": [], "passwordInputs": 0,
                 "confirmPassword": False, "otpInput": False, "captchaVisible": False, "fillable": 0,
                 "hasApplyLink": False, "confirmationText": False, "confirmationPhrase": None,
                 "closedText": False, "boardNative": False}


def _btn(ident, text, **extra):
    return {"id": ident, "text": text, "type": "button", "marker": "", "inForm": True, "visible": True,
            "enabled": True, **extra}


def page(kind, n=1, host="jobs.acme.test", **extra):
    """One page of the fake site: its summary (what `page_classify` answers) and its address."""
    s = {**_BASE_SUMMARY, "host": host, "stepKey": f"{kind}{n}"}
    if kind == "step":
        s.update(fillable=2, buttons=[_btn(f"next-{n}", "Next"), _btn(f"back-{n}", "Back")])
    elif kind == "review":
        s.update(fillable=2, buttons=[_btn("submit-1", "Submit application"), _btn("back-r", "Back")])
    elif kind == "captcha":
        s.update(fillable=1, captchaVisible=True)
    elif kind == "verify":
        s.update(fillable=1, otpInput=True)
    elif kind == "create_account":
        s.update(passwordInputs=2, confirmPassword=True)
    elif kind == "sign_in":
        s.update(passwordInputs=1, fillable=2, buttons=[_btn("signin-1", "Sign in")])
    elif kind == "confirmation":
        s.update(confirmationText=True, confirmationPhrase="Thank you for applying")
    elif kind == "closed":
        s.update(closedText=True)
    elif kind == "board_native":
        s.update(hasApplyLink=True, boardNative=True)
    elif kind == "unknown":
        pass
    else:
        raise ValueError(kind)
    s.update(extra)
    return {"summary": s, "url": f"https://{host}/apply/{kind}{n}"}


STEP1, STEP2, REVIEW = page("step", 1), page("step", 2), page("review", 3)


def verified(fid, question="Name", **extra):
    return {"fid": fid, "question": question, "required": True, "status": "verified", **extra}


def needs(fid, question, **extra):
    return {"fid": fid, "question": question, "required": True, "status": "needs_answer", **extra}


_RUN_DRIVER_JS = _PANEL_FAKES_JS + r"""
// ---- the fake site: pages the driver reads, one of which a press moves past ----
let at = 0;
let tabUrlOverride = null;
const site = spec.pages ?? [];
const here = () => site[Math.min(at, site.length - 1)];
const pressed = [];
const updates = [];
spec.frames = spec.frames ?? {};
Object.defineProperty(spec.frames, "page_classify", { configurable: true, enumerable: true,
  get: () => {
    if (here()?.throws) throw new Error("the tab is navigating");
    return here() ? [{ frameId: 0, url: here().url, result: { summary: here().summary, top: true } }] : [];
  } });
Object.defineProperty(spec.frames, "page_advance", { configurable: true, enumerable: true,
  get: () => { at += 1; return [{ frameId: 0, result: { clicked: true } }]; } });
// `inventoryByPage`: what the page holds, per site page (a page that holds nothing yields no receipt).
Object.defineProperty(spec.frames, "fill_inventory", { configurable: true, enumerable: true,
  get: () => {
    const byPage = spec.inventoryByPage;
    const fields = byPage ? byPage[Math.min(at, byPage.length - 1)] : (spec.inventory ?? []);
    return [{ frameId: 0, result: { fields } }];
  } });
spec.frames.fill_cancel = [{ frameId: 0, result: true }];
spec.frames.fill_focus = [{ frameId: 0, result: true }];
spec.page = spec.page ?? {};
Object.defineProperty(spec.page, "page_sign_in", { configurable: true, enumerable: true,
  get: () => { at += 1; return { ok: true, data: { signedIn: "clicked" } }; } });

// ---- time: the auto-mark's 8 s is held, everything else collapses; Date.now can be moved ----
const heldTimers = [];
const collapsed = global.setTimeout;
const realClear = global.clearTimeout;
global.setTimeout = (fn, ms, ...rest) => {
  if (ms >= 8000) { heldTimers.push({ fn, ms }); return heldTimers.length; }
  return collapsed(fn, ms, ...rest);
};
global.clearTimeout = (id) => {
  if (typeof id === "number" && heldTimers[id - 1]) { heldTimers[id - 1] = null; return; }
  realClear(id);
};
let skew = 0;
const realNow = Date.now;
Date.now = () => realNow() + skew;

// Two windows: the panel is the one with id 1, and `windowIds` moves a tab to another.
chrome.windows = { getCurrent: async () => ({ id: 1 }) };
chrome.tabs.get = async (id) => ({ id, status: "complete", windowId: (spec.windowIds ?? {})[id] ?? 1,
  url: tabUrlOverride ?? (spec.tabUrls ?? {})[id] ?? here()?.url ?? "" });
chrome.tabs.update = async (id, props) => { updates.push([id, props]); if (props.url) at = spec.afterNavigate ?? at; };

// What each save of the runs held AT THAT MOMENT (the harness keeps references, which later changes rewrite).
const queueSaves = [];
// ... and which keys each run in a save carried as it reached chrome.storage (before any serialiser runs).
const queueSaveKeys = [];
const realSessionSet = chrome.storage.session.set;
chrome.storage.session.set = async (patch) => {
  if (patch.queueRun) {
    queueSaves.push(JSON.parse(JSON.stringify(patch.queueRun)));
    queueSaveKeys.push(patch.queueRun.map((run) => Object.keys(run)));
  }
  return realSessionSet(patch);
};

// A BROWSER BLURS A REMOVED NODE: focus falls to the body when the focused control leaves the document.
const holds = (node, target) => node === target || node.children.some((kid) => holds(kid, target));
for (const root of [...Object.values(REGIONS), CONTROLS]) {
  const replace = root.replaceChildren.bind(root);
  root.replaceChildren = (...kids) => {
    if (ACTIVE && root.children.some((kid) => holds(kid, ACTIVE))) ACTIVE = null;
    replace(...kids);
  };
}
const errors = [];
console.error = (...args) => { errors.push(args.map(String).join(" ")); };
const ns = loadModules();
// How many answer receipts the run posts (a scoped repair must post none).
let receiptCalls = 0;
const realReceipt = ns.panelRecordReceipt;
ns.panelRecordReceipt = async (...args) => { receiptCalls += 1; return realReceipt(...args); };

// ---- the fill stub: reports instead of touching a page ----
const fills = [];
let gate = null;
const memoryIds = new Map();
ns.fillLoop.runFill = async (deps, options) => {
  // The run record's memory: an object per record, which the page it belongs to keeps and the next page does not.
  if (options.memory && typeof options.memory === "object" && !memoryIds.has(options.memory)) memoryIds.set(options.memory, memoryIds.size + 1);
  const call = { options, cancelledAtStart: deps.cancelled(), memoryId: memoryIds.get(options.memory) ?? null,
                 memoryJson: JSON.stringify(options.memory ?? null) };
  fills.push(call);
  const planned = (spec.reports ?? [])[fills.length - 1] ?? spec.report ?? { fields: [{ fid: "f1", question: "Name", required: true, status: "verified" }] };
  if (spec.callBeforeSweep) await deps.beforeSweep?.();
  // Each field the report holds is told as it ended, with the status it ended in.
  for (const row of planned.fields) deps.onProgress?.({ phase: "field", fid: row.fid, status: row.status });
  if (planned.hold) await new Promise((resolve) => { gate = resolve; });
  call.cancelledAtEnd = deps.cancelled();
  return { runId: "r", host: "jobs.acme.test", fields: planned.fields, aiFailure: null,
           stopped: planned.stopsWhenCancelled ? call.cancelledAtEnd : false, timedOut: false,
           consentForms: false, sections: [], ...(planned.trace ? { trace: planned.trace } : {}) };
};

const mids = [];
const snap = () => ({ focused: document.activeElement?.id ?? null, regions: regions(), runs: JSON.parse(JSON.stringify(ns.panel.actionStore().read().runs)) });
let started = null;
main(async () => {
  await settle();
  const shots = [snap()];
  for (const step of spec.steps ?? []) {
    if (step.tabUrl !== undefined) tabUrlOverride = step.tabUrl;
    if (step.page !== undefined) at = step.page;
    if (step.skew) skew += step.skew;
    if (step.dropInventory) delete spec.frames.fill_inventory;
    if (step.seed) {
      ns.panel.actionStore().write({ runs: step.seed });
      ns.panel.actionStore().render();
    }
    if (step.start) {
      started = ns.panel.startRun(step.start);
      if (!step.background) await started;
    }
    if (step.release && gate) { gate(); gate = null; }
    if (step.releaseApi) release();
    if (step.press) {
      const el = document.getElementById(step.press);
      if (!el) throw new Error(`no control #${step.press}`);
      el.click();
    }
    if (step.pressAll) {
      // Every button looked up BEFORE the first click, so a later one is a stale reference to a
      // control the first press already replaced: a double click, or a click that raced the repaint.
      const els = step.pressAll.map((id) => {
        const el = document.getElementById(id);
        if (!el) throw new Error(`no control #${id}`);
        return el;
      });
      for (const el of els) el.click();
      mids.push(snap());
    }
    if (step.focus) {
      const el = document.getElementById(step.focus);
      if (!el) throw new Error(`no control #${step.focus} to focus`);
      el.focus();
    }
    if (step.pressText) {
      const hit = (node) => (node.tagName === "BUTTON" && node.textContent === step.pressText ? node
        : node.children.map(hit).find(Boolean));
      const el = hit(REGIONS.rail);
      if (!el) throw new Error(`no button reads "${step.pressText}"`);
      el.click();
    }
    if (step.activate !== undefined) await onActivated({ tabId: step.activate });
    if (step.update) await onUpdated(step.update.tab, step.update.change);
    if (step.removed !== undefined) await onRemoved(step.removed);
    if (step.fire) {
      const due = heldTimers.splice(0).filter(Boolean);
      for (const timer of due) timer.fn();
    }
    await settle();
    if (started && step.finish) await started;
    shots.push(snap());
  }
  emit({ shots, mids, queueSaves, queueSaveKeys, fills, receiptCalls, pressed, updates, sent, writes, sessionWrites, broadcasts, held: heldTimers.filter(Boolean).length,
         profile: PROFILE, errors, warnings });
});
"""


def _run(tmp_path, steps, pages=(STEP1, REVIEW), **spec):
    spec.setdefault("tabs", [{"id": 7, "url": START_URL}])
    spec["replies"] = {"read_settings": SETTINGS_REPLY, "panel_prepare": _reply({"injected": True}),
                       "panel_frame0": _reply({"tier": "B", "form": True, "score": 2}),
                       "telemetry": _reply({"posted": 0}), **spec.get("replies", {})}
    spec["api"] = {
        "/api/jobs/match": _reply({"match": "none", "job": None, "application": None}),
        "/api/base-resumes": _reply(BASE_RESUMES),
        "/api/ats-scores": _reply([]),
        "GET /api/applications/app-1": _reply(APPLICATION),
        "POST /api/jobs/job-1/filled-answers": _reply({"flags": []}),
        **spec.get("api", {}),
    }
    return run_node(_RUN_DRIVER_JS, {"pages": list(pages), "steps": steps, **spec}, tmp_path, source=PANEL_SOURCE)


# ---------- reading what was painted ----------


def _card(shot):
    """The open Fill row: its title (the status word) and its body."""
    [row] = [one for one in _by_class(shot["regions"]["rail"], "stg") if "active" in one["class"].split()]
    name = _by_class(row, "stg-name")[0]["text"]
    bodies = _by_class(row, "stg-body")
    return {"row": row, "title": name, "body": bodies[0] if bodies else None,
            "applying": "applying" in row["class"].split()}


def _buttons(node):
    """The card's own buttons: the Ask drawer under it is not the card's (its own tests read it)."""
    return {one["id"]: _text(one) for one in _walk(node)
            if one["tag"] == "BUTTON" and one["id"] and one["id"] != "qna-toggle"}


def _body_text(shot):
    return _text(_card(shot)["body"])


def _api_calls(out, needle):
    return [msg for msg in out["sent"] if msg["type"] == "api" and needle in msg["path"]]


def _record(shot):
    [record] = shot["runs"]
    return record


def _page_messages(out, kind):
    return [msg for msg in out["broadcasts"] if msg["message"]["type"] == kind]


# ---------- the card: each status in words ----------


def _seeded(status, **extra):
    return {"id": "run-1", "proposalId": "prop-1", "jobId": "job-1", "applicationId": "app-1", "company": "Acme",
            "title": "Data Scientist", "baseSlug": "ai_ml_engineer", "openUrl": START_URL, "startTabId": 7,
            "tabId": 7, "status": status, "why": None, "open": [], "hosts": ["jobs.acme.test"], "seen": [],
            "step": 0, "yourMs": 0, "pages": [], "flags": [], "stopRequested": False, **extra}


@pytest.mark.parametrize("status,extra,title,working", [
    ("opening", {}, "Opening", True),
    ("signing_in", {}, "Signing in", True),
    ("filling", {"step": 1}, "Filling page 2", True),
    ("advancing", {"step": 0}, "Filling page 1", True),
    ("parked", {"why": "captcha"}, "Needs you", False),
    ("ready", {"readyAt": 1}, "Ready to submit", False),
    ("confirming", {"readyAt": 1}, "Marking applied", False),
    ("applied", {}, "Applied", False),
    ("stopped", {"why": "user"}, "Stopped", False),
])
def test_every_status_is_the_next_cards_title_and_only_the_working_ones_say_applying(
        tmp_path, status, extra, title, working):
    out = _run(tmp_path, [{"seed": [_seeded(status, **extra)]}])
    card = _card(out["shots"][1])
    assert (card["title"], card["applying"]) == (title, working)
    # The card is the Fill step, drawn over whatever the page's own facts would have said.
    assert _text(out["shots"][1]["regions"]["progress"]).endswith("Step 3 of 4 · Fill")
    # The footer's Autofill is out of the way: the run has its own Stop, and two fills would race.
    assert "Autofill" not in _text(out["shots"][1]["regions"]["foot"])


def test_a_parked_or_ready_run_card_keeps_the_ask_box_under_it(tmp_path):
    """The Ask drawer is about the user's own question, so a card that waits for the user keeps it."""
    for record in (_seeded("ready", readyAt=1), _seeded("parked", why="captcha")):
        out = _run(tmp_path, [{"seed": [record]}, {"pressText": "Ask"}])
        closed, opened = out["shots"][1]["regions"]["rail"], out["shots"][2]["regions"]["rail"]
        [drawer] = _by_class(closed, "qna")
        [toggle] = _by_class(drawer, "linkish")
        assert (toggle["id"], toggle["attrs"]["aria-expanded"]) == ("qna-toggle", "false")
        assert not [one for one in _walk(closed) if one["id"] == "qna-question"]
        assert [one for one in _walk(opened) if one["id"] == "qna-question"]


@pytest.mark.parametrize("status", ["opening", "signing_in", "filling", "advancing"])
def test_a_working_run_offers_no_ask_box_only_a_line_saying_when_it_opens(tmp_path, status):
    """A page turn wipes the draft and a repaint moves the caret, so the box waits for a pause."""
    out = _run(tmp_path, [{"seed": [_seeded(status)]}])
    rail = out["shots"][1]["regions"]["rail"]
    assert not _by_class(rail, "qna")
    assert not [one for one in _walk(rail) if one["tag"] == "TEXTAREA"]
    assert "Ask opens when the run pauses." in _text(rail)
    assert "run-stop" in _buttons(_card(out["shots"][1])["body"])


def test_the_stop_button_keeps_its_place_and_focus_across_repaints_of_a_working_run(tmp_path):
    out = _run(tmp_path, [{"seed": [_seeded("filling", step=1)]}, {"focus": "run-stop"},
                          {"seed": [_seeded("filling", step=1, pages=[{"n": 1, "filled": 3}])]}])
    assert out["shots"][-1]["focused"] == "run-stop"
    assert "run-stop" in _buttons(_card(out["shots"][-1])["body"])


def test_the_running_card_shows_the_pages_so_far_a_bar_stop_and_the_fixed_line(tmp_path):
    record = _seeded("filling", step=1, pages=[{"n": 1, "filled": 12}], progress={"done": 5, "total": 9})
    out = _run(tmp_path, [{"seed": [record]}])
    body = _card(out["shots"][1])["body"]
    text = _text(body)
    assert "Page 1 · 12 filled" in text and "Page 2 · 5 of 9 answered" in text
    assert "It clicks Next for you. It never clicks Submit." in text
    [bar] = _by_class(body, "run-bar")
    assert (bar["attrs"]["role"], bar["attrs"]["aria-valuenow"]) == ("progressbar", "56")
    pages = _by_class(body, "run-pages")[0]
    assert [name for node in _walk(pages) for name in [node["attrs"].get("data-icon")] if name] == ["circle-check"]
    assert _buttons(body) == {"run-stop": "Stop"}


def test_no_state_ever_draws_a_submit_control(tmp_path):
    states = [("opening", {}), ("filling", {}), ("parked", {"why": "open_questions",
                                                          "open": [{"fid": "f1", "question": "Q", "required": True}]}),
              ("parked", {"why": "captcha"}), ("ready", {"readyAt": 1, "noAutoMark": True}),
              ("confirming", {"readyAt": 1}), ("applied", {}), ("stopped", {"why": "error"})]
    for status, extra in states:
        out = _run(tmp_path, [{"seed": [_seeded(status, **extra)]}])
        offered = _buttons(_card(out["shots"][1])["body"]).values()
        assert not [label for label in offered if "submit" in label.lower()], (status, offered)


# ---------- why it needs you ----------


@pytest.mark.parametrize("why,reason,resume,skip", [
    ("open_questions", "Questions on this page", True, True),
    ("page_errors", "The page asks for more", True, True),
    ("captcha", "CAPTCHA", True, True),
    ("create_account", "Create an account", True, True),
    ("verify", "Email code", True, True),
    ("sign_in_failed", "Sign-in didn't work", True, True),
    ("sign_in_yourself", "Sign in yourself", True, True),
    ("posting", "Apply yourself", True, True),
    ("unknown_page", "Page not recognised", True, True),
    ("unsure_page", "Not sure this is the last page", True, True),
    ("confirm_page", "Check this page", True, True),
    ("already_applied", "Already sent?", True, True),
    ("moved_away", "Left the application", True, True),
    ("loop", "The same page again", True, True),
    ("no_change", "The page didn't move on", True, True),
    ("step_limit", "Too many steps", False, True),
    ("board_native", "Apply on the job board", False, True),
])
def test_every_park_has_words_and_the_resume_and_skip_it_allows(tmp_path, why, reason, resume, skip):
    open_ = [{"fid": "f1", "question": "Work authorization", "required": True}] if why == "open_questions" else []
    out = _run(tmp_path, [{"seed": [_seeded("parked", why=why, open=open_)]}])
    body = _card(out["shots"][1])["body"]
    assert reason in _text(body)
    buttons = _buttons(body)
    assert ("run-resume" in buttons) is resume and ("run-skip" in buttons) is skip
    # A wall names the others; the card never says a thing it did not park for.
    assert "Do this step in the tab, then Resume." in _text(body) or why not in ("captcha", "verify", "create_account", "sign_in_failed")


@pytest.mark.parametrize("why,reason,resume", [
    ("closed", "Position closed", True), ("bad_link", "Bad link", False),
    ("error", "Something went wrong", True), ("user", "Stopped", True),
    ("tab_closed", "Tab closed", False), ("interrupted", "Interrupted", True),
])
def test_every_stop_has_words_and_only_the_ones_a_user_can_take_back_offer_resume(tmp_path, why, reason, resume):
    out = _run(tmp_path, [{"seed": [_seeded("stopped", why=why)]}])
    body = _card(out["shots"][1])["body"]
    assert reason in _text(body)
    buttons = _buttons(body)
    assert ("run-resume" in buttons) is resume and "run-done" in buttons and "run-skip" not in buttons


def test_a_wall_names_the_other_walls_in_one_line(tmp_path):
    out = _run(tmp_path, [{"seed": [_seeded("parked", why="verify")]}])
    assert ("It also stops here for: a CAPTCHA · creating an account · a sign-in that didn't work "
            "· apply on a job board") in _body_text(out["shots"][1])


def test_open_questions_are_jump_links_to_the_field_in_the_runs_tab(tmp_path):
    record = _seeded("parked", why="open_questions", open=[
        {"fid": "f1", "question": "Work authorization", "required": True},
        {"fid": "f2", "question": "Pronouns", "required": False}])
    out = _run(tmp_path, [{"seed": [record]}])
    body = _card(out["shots"][1])["body"]
    [questions] = _by_class(body, "resid")
    assert [_text(item) for item in questions["children"]] == ["Work authorization", "Pronouns"]
    # No checkbox: answers are always remembered (owner, 2026-10-11).
    assert not [node for node in _walk(_card(out["shots"][1])["body"]) if node["tag"] == "INPUT"]
    out = _run(tmp_path, [{"seed": [record]}, {"pressText": "Pronouns"}])
    [focus] = _page_messages(out, "fill_focus")
    assert (focus["tabId"], focus["message"]["fid"]) == (7, "f2")


# ---------- driving one job in the current tab ----------


def test_a_run_started_on_the_current_tab_fills_each_page_presses_only_next_and_stops_at_review(tmp_path):
    out = _run(tmp_path, [{"start": SEED}], pages=(STEP1, STEP2, REVIEW))
    record = _record(out["shots"][1])
    assert (record["status"], record["why"], record["step"]) == ("ready", None, 2)
    assert record["tabId"] == 7 and record["startedAt"] and record["readyAt"]
    # The press goes to the frame that named the control, as a top-level field of the page message.
    presses = _page_messages(out, "page_advance")
    assert [msg["message"]["id"] for msg in presses] == ["next-1", "next-2"]
    assert all(msg["tabId"] == 7 and msg["frameId"] == 0 for msg in presses)
    assert not [msg for msg in out["broadcasts"] if "submit" in json.dumps(msg["message"]).lower()]
    # Three pages filled, each with the run's limits, the record's job and application, never the card's.
    assert len(out["fills"]) == 3
    assert out["fills"][0]["options"]["limits"] == {"FIELD_MS": 60000, "MAX_STEPS": 12, "RUN_MS": 600000}
    assert out["fills"][0]["options"]["applicationId"] == "app-1"
    assert [page["n"] for page in record["pages"]] == [1, 2, 3]
    # The answer receipt names the record's application and base, not whatever the card holds.
    receipts = [json.loads(msg["init"]["body"]) for msg in _api_calls(out, "/api/jobs/job-1/filled-answers")]
    assert receipts == [] or all(r["application_id"] == "app-1" and r["base_resume"] == "ai_ml_engineer" for r in receipts)
    card = _card(out["shots"][1])
    assert card["title"] == "Ready to submit" and not card["applying"]
    assert "press Submit in the tab" in _text(card["body"])


def test_a_run_keeps_the_tab_when_it_is_already_on_the_same_posting_and_navigates_otherwise(tmp_path):
    out = _run(tmp_path, [{"start": SEED}])
    assert out["updates"] == []
    elsewhere = {**SEED, "openUrl": "https://other.acme.test/jobs/55/apply"}
    out = _run(tmp_path, [{"start": elsewhere}], afterNavigate=0)
    assert out["updates"] == [[7, {"url": "https://other.acme.test/jobs/55/apply"}]]


def test_the_run_attaches_the_resume_in_its_own_tab_as_autofill_does_and_reports_value_free_telemetry(tmp_path):
    uploads = {"tier": "B", "form": True, "score": 2, "fileInputs": 1,
               "uploads": [{"kind": "resume", "occupied": False}]}
    out = _run(tmp_path, [{"start": SEED}], pages=(STEP1, REVIEW), callBeforeSweep=True,
               page={"detect_page": _reply(uploads)},
               replies={"attach_pdf": _reply([{"frameId": 0, "result": {"written": 1, "proven": 1}}])},
               api={"GET /api/applications/app-1": _reply(APPLICATION)})
    attach = [msg for msg in out["sent"] if msg["type"] == "attach_pdf"]
    assert attach and all(msg["tabId"] == 7 and msg["resumeOnly"] is True for msg in attach)
    assert attach[0]["path"] == "/api/applications/app-1/pdf" and attach[0]["filename"] == "Ada.pdf"
    [telemetry] = [msg for msg in out["sent"] if msg["type"] == "telemetry"][:1]
    assert (telemetry["action"], telemetry["page_host"]) == ("loop_fill", "jobs.acme.test")


def test_the_runs_first_move_is_to_prepare_its_tab_once(tmp_path):
    out = _run(tmp_path, [{"start": SEED}])
    assert [msg["tabId"] for msg in out["sent"] if msg["type"] == "panel_prepare"] == [7]


def test_the_runs_job_and_application_come_from_its_record_not_the_session_memory(tmp_path):
    """After a cross-origin Apply the session entry is refused (origin and tenant guards). The record is
    what says which job the tab is still doing, so the header keeps the job's title."""
    elsewhere = "https://careers.globex.test/step9"
    out = _run(tmp_path, [{"start": SEED, "background": True},
                          {"tabUrl": elsewhere, "update": {"tab": 7, "change": {"url": elsewhere}}}],
               reports=[{"fields": [verified("f1")], "hold": True}], tabs=[{"id": 7, "url": START_URL}])
    identity = _text(out["shots"][2]["regions"]["identity"])
    assert "Data Scientist" in identity and "Acme" in identity
    assert _card(out["shots"][2])["title"] == "Filling page 1"


def test_the_run_vouches_for_the_origin_it_read_a_form_in_even_when_the_panel_looks_at_another_tab(tmp_path):
    """A frame of the run's tab takes the fill when the panel vouches for its origin
    (`frameMayReceiveUserData`). The bound page's own flow is for the BOUND tab; the run's is what it read."""
    out = _run(tmp_path, [{"start": SEED, "background": True}, {"activate": 8}, {"release": True, "finish": True}],
               reports=[{"fields": [verified("f1")], "hold": True}], tabUrls={"8": "chrome://settings"})
    to_run_tab = [msg for msg in out["broadcasts"] if msg["tabId"] == 7 and msg["message"]["type"] == "fill_inventory"]
    assert to_run_tab and all(msg["message"].get("flowOrigin") == "https://jobs.acme.test" for msg in to_run_tab)
    # A read that carries no user data is never vouched for.
    assert all("flowOrigin" not in msg["message"] for msg in _page_messages(out, "fill_cancel"))


def test_a_tab_switch_during_a_run_cancels_nothing(tmp_path):
    out = _run(tmp_path, [{"start": SEED, "background": True}, {"activate": 8}, {"release": True, "finish": True}],
               reports=[{"fields": [verified("f1")], "hold": True}],
               tabUrls={"8": "chrome://settings"})
    assert [msg for msg in out["broadcasts"] if msg["message"]["type"] == "fill_cancel"] == []
    assert out["fills"][0]["cancelledAtEnd"] is False
    assert _record(out["shots"][-1])["status"] == "ready"


def test_stop_sets_the_flag_the_fill_reads_and_reaches_the_runs_own_tab(tmp_path):
    out = _run(tmp_path, [{"start": SEED, "background": True}, {"press": "run-stop"},
                          {"release": True, "finish": True}],
               reports=[{"fields": [verified("f1")], "hold": True, "stopsWhenCancelled": True}])
    cancels = [msg for msg in out["broadcasts"] if msg["message"]["type"] == "fill_cancel"]
    # Aimed at the run's own tab by id, whichever tab the panel is bound to.
    assert [msg["tabId"] for msg in cancels] == [7]
    assert _record(out["shots"][2])["stopRequested"] is True and "Stopping" in _body_text(out["shots"][2])
    assert out["fills"][0]["cancelledAtEnd"] is True
    record = _record(out["shots"][-1])
    assert (record["status"], record["why"]) == ("stopped", "user")
    assert out["pressed"] == [] and not _page_messages(out, "page_advance")


def test_the_run_is_saved_at_every_change_and_a_reopened_panel_shows_where_it_got_to(tmp_path):
    out = _run(tmp_path, [{"start": SEED}])
    saved = [write["queueRun"] for write in out["sessionWrites"] if "queueRun" in write]
    assert saved and saved[-1][0]["status"] == "ready"
    mid_air = _seeded("filling", step=1)
    parked = _seeded("parked", why="captcha", id="run-2")
    reopened = _run(tmp_path, [], sessionStored={"queueRun": [mid_air, parked]})
    runs = reopened["shots"][0]["runs"]
    # Nothing drives a record after a reopen: one that was mid-air says so, and its tab is not driven.
    assert [(run["status"], run["why"]) for run in runs] == [("stopped", "interrupted"), ("parked", "captcha")]


def test_a_closed_run_tab_ends_its_run(tmp_path):
    out = _run(tmp_path, [{"start": SEED, "background": True}, {"removed": 7}, {"release": True, "finish": True}],
               reports=[{"fields": [verified("f1")], "hold": True}])
    record = _record(out["shots"][-1])
    assert (record["status"], record["why"]) == ("stopped", "tab_closed")


def test_a_run_tab_that_leaves_the_runs_hosts_is_no_longer_vouched_for(tmp_path):
    """The vouch lets a subframe of the run's origin take a fill. A tab that has gone to another site
    (the user's own browsing while the run waits) must not lend that to whatever is on it now."""
    news = page("unknown", 1, host="news.example.test")
    pages = (STEP1, page("captcha", 1), news)
    out = _run(tmp_path, [{"start": SEED}, {"page": 2, "update": {"tab": 7, "change": {"url": news["url"]}}},
                          {"press": "run-resume"}], pages=pages)
    reads = _page_messages(out, "page_classify")
    # (The panel's own look at the new page may vouch for ITS origin; the run's old one is what goes.)
    assert reads[-1]["message"].get("flowOrigin") != "https://jobs.acme.test"
    assert all(msg["message"].get("flowOrigin") == "https://jobs.acme.test" for msg in reads[:-1])


def test_a_run_tab_that_stays_on_the_runs_hosts_keeps_its_vouch(tmp_path):
    pages = (STEP1, page("captcha", 1), page("step", 2))
    out = _run(tmp_path, [{"start": SEED}, {"page": 2, "update": {"tab": 7, "change": {"url": pages[2]["url"]}}},
                          {"press": "run-resume"}], pages=pages)
    assert all(msg["message"].get("flowOrigin") == "https://jobs.acme.test" for msg in _page_messages(out, "page_classify"))


# ---------- walls: Resume, and Skip this job ----------


def test_a_captcha_parks_and_resume_goes_round_again_without_learning_anything(tmp_path):
    pages = (STEP1, page("captcha", 1), STEP2, REVIEW)
    out = _run(tmp_path, [{"start": SEED}, {"page": 2}, {"press": "run-resume", "finish": False}], pages=pages)
    parked = out["shots"][1]
    assert _record(parked)["why"] == "captcha" and _card(parked)["title"] == "Needs you"
    # Skipped over the wall by the user in the tab (page 2), Resume carries on to the review.
    assert _record(out["shots"][-1])["status"] == "ready"
    assert not _api_calls(out, "/api/settings/autofill")


def test_skip_this_job_stops_the_record_and_sends_the_server_nothing(tmp_path):
    pages = (STEP1, page("captcha", 1))
    before = _run(tmp_path, [{"start": SEED}], pages=pages)
    out = _run(tmp_path, [{"start": SEED}, {"press": "run-skip"}], pages=pages)
    record = _record(out["shots"][-1])
    assert (record["status"], record["why"]) == ("stopped", "user")
    mutations = [msg for msg in out["sent"] if msg["type"] == "api"
                 and (msg.get("init") or {}).get("method") in ("POST", "PATCH", "PUT", "DELETE")]
    kept = [msg for msg in before["sent"] if msg["type"] == "api"
            and (msg.get("init") or {}).get("method") in ("POST", "PATCH", "PUT", "DELETE")]
    # Only what the fill itself posts (the answer receipt); nothing about the proposal or the job.
    assert [msg["path"] for msg in mutations] == [msg["path"] for msg in kept]
    assert not _api_calls(out, "/api/proposals")


# ---------- needs you: answers are always remembered ----------


def _field(fid, committed, **extra):
    return {"fid": fid, "fp": f"fp-{fid}", "shape": "text", "kind": "text", "multi": False,
            "question": extra.pop("question", "Q"), "section": "", "repeatIndex": 0, "required": True,
            "committed": committed, "answered": bool(committed), "options": None, "optionsComplete": False,
            "invalid": False, "touched": True, "policyBlocked": False, "multiline": False, **extra}


QUESTIONS = [needs("q1", "Have you used our product before?"), needs("q2", "Why do you want this role?")]
TYPED = [_field("q1", "Yes", question="Have you used our product before?"),
         _field("q2", "Because the work is interesting.", question="Why do you want this role?", multiline=True)]
OLD_PROFILE = {"custom": [{"question": "Have you used our product before?", "answer": "No"}],
               "preferences": {"notice_period": "2 weeks"}}


def _parked_on_questions(tmp_path, steps, **spec):
    steps = [{"start": SEED}, *steps]
    return _run(tmp_path, steps, pages=(STEP1, REVIEW),
                reports=[{"fields": QUESTIONS}, {"fields": [verified("f1")]}],
                inventory=TYPED, profileStore=json.loads(json.dumps(OLD_PROFILE)), **spec)


def test_a_page_with_unanswered_required_questions_parks_with_them_listed_by_name(tmp_path):
    out = _parked_on_questions(tmp_path, [])
    record = _record(out["shots"][1])
    assert (record["status"], record["why"]) == ("parked", "open_questions")
    assert [one["question"] for one in record["open"]] == ["Have you used our product before?", "Why do you want this role?"]
    body = _card(out["shots"][1])["body"]
    assert set(_buttons(body)) >= {"run-resume", "run-skip"}


def test_resume_posts_what_you_typed_as_yours_saves_the_answers_and_drives_on(tmp_path):
    out = _parked_on_questions(tmp_path, [{"press": "run-resume"}])
    # 1. The answer record: the fields the user typed, source `you`. The prose box is on it too.
    posted = [json.loads(msg["init"]["body"]) for msg in _api_calls(out, "/filled-answers")]
    typed = [field for body in posted for field in body["fields"] if field["source"] == "you"]
    assert {field["question"] for field in typed} == {"Have you used our product before?", "Why do you want this role?"}
    assert all(body["channel"] == "companion" for body in posted)
    # 2. Always remembered: the short answer goes to the profile; the prose box never does.
    profile = out["profile"]
    assert {"question": "Have you used our product before?", "answer": "Yes"} in profile["custom"]
    assert not [row for row in profile["custom"] if "Why do you want" in row["question"]]
    # 3. The card says so, with Undo; the run went on to the review.
    final = out["shots"][-1]
    assert _record(final)["status"] == "ready"
    assert "Saved 1 answer to your profile · Undo" in _body_text(final)
    assert len(out["fills"]) == 3   # the parked page, the same page again after Resume, the review


def test_the_learn_path_is_one_read_and_one_write_however_many_answers(tmp_path):
    out = _parked_on_questions(tmp_path, [{"press": "run-resume"}])
    reads = [m for m in _api_calls(out, "/api/settings/autofill") if (m.get("init") or {}).get("method") in (None, "GET")]
    writes = [m for m in _api_calls(out, "/api/settings/autofill") if (m.get("init") or {}).get("method") == "PUT"]
    assert (len(reads), len(writes)) == (1, 1)


def test_a_typed_key_the_question_has_a_home_for_lands_there_and_undo_puts_everything_back(tmp_path):
    typed = [_field("q1", "30 days", question="What is your notice period?")]
    out = _run(tmp_path, [{"start": SEED}, {"press": "run-resume"}, {"press": "run-undo-saved"}],
               pages=(STEP1, REVIEW), reports=[{"fields": [needs("q1", "What is your notice period?")]},
                                               {"fields": [verified("f1")]}],
               inventory=typed, profileStore=json.loads(json.dumps(OLD_PROFILE)))
    puts = [json.loads(m["init"]["body"])["value"] for m in _api_calls(out, "/api/settings/autofill")
            if (m.get("init") or {}).get("method") == "PUT"]
    assert puts[0]["preferences"]["notice_period"] == "30 days"
    # Undo: the profile as it was, key for key.
    assert out["profile"] == OLD_PROFILE
    assert "Undid 1 answer." in _body_text(out["shots"][-1])


def test_undo_restores_a_replaced_custom_answer_and_removes_a_new_one(tmp_path):
    two = [_field("q1", "Yes", question="Have you used our product before?"),
           _field("q3", "Blue", question="Favourite colour?")]
    out = _run(tmp_path, [{"start": SEED}, {"press": "run-resume"}, {"press": "run-undo-saved"}],
               pages=(STEP1, REVIEW),
               reports=[{"fields": [needs("q1", "Have you used our product before?"), needs("q3", "Favourite colour?")]},
                        {"fields": [verified("f1")]}],
               inventory=two, profileStore=json.loads(json.dumps(OLD_PROFILE)))
    assert out["profile"] == OLD_PROFILE


def test_resume_scopes_an_old_general_answer_that_names_this_jobs_company_and_undo_restores_it(tmp_path):
    friend = "Do you have a friend at Acme?"
    legacy = {"custom": [{"question": friend, "answer": "No"}]}
    out = _run(tmp_path, [{"start": SEED}, {"press": "run-resume"}], pages=(STEP1, REVIEW),
               reports=[{"fields": [needs("q1", friend)]}, {"fields": [verified("f1")]}],
               inventory=[_field("q1", "Yes", question=friend)], profileStore=json.loads(json.dumps(legacy)))
    assert out["profile"]["custom"] == [{"question": friend, "answer": "Yes", "only_for": "Acme",
                                         "only_for_kind": "company"}]
    undone = _run(tmp_path, [{"start": SEED}, {"press": "run-resume"}, {"press": "run-undo-saved"}],
                  pages=(STEP1, REVIEW), reports=[{"fields": [needs("q1", friend)]}, {"fields": [verified("f1")]}],
                  inventory=[_field("q1", "Yes", question=friend)], profileStore=json.loads(json.dumps(legacy)))
    assert undone["profile"] == legacy


def test_a_field_the_user_left_alone_or_the_policy_never_fills_is_not_learned(tmp_path):
    untouched = [_field("q1", "Yes", question="Have you used our product before?", touched=False),
                 _field("q3", "x", question="Signature", policyBlocked=True)]
    out = _run(tmp_path, [{"start": SEED}, {"press": "run-resume"}], pages=(STEP1, REVIEW),
               reports=[{"fields": [needs("q1", "Have you used our product before?"), needs("q3", "Signature")]},
                        {"fields": [verified("f1")]}],
               inventory=untouched, profileStore=json.loads(json.dumps(OLD_PROFILE)))
    assert out["profile"] == OLD_PROFILE
    assert "Saved" not in _body_text(out["shots"][-1])


def test_resume_accrues_the_users_time_from_park_to_resume(tmp_path):
    out = _parked_on_questions(tmp_path, [{"skew": 42_000}, {"press": "run-resume"}])
    assert 42_000 <= _record(out["shots"][-1])["yourMs"] < 60_000


def test_resume_shows_the_card_as_working_while_it_reads_what_you_typed(tmp_path):
    """The read of the page, the receipt and the saved answers all happen before the driver takes the
    record: the card must not look parked (Resume and Skip pressable) in that gap."""
    out = _parked_on_questions(tmp_path, [{"pressAll": ["run-resume"]}])
    during = out["mids"][0]
    assert _record(during)["status"] == "filling"
    assert set(_buttons(_card(during)["body"])) == {"run-stop"}


def test_pressing_resume_twice_posts_one_receipt_and_leaves_undo_working(tmp_path):
    once = _parked_on_questions(tmp_path, [{"press": "run-resume"}])
    out = _parked_on_questions(tmp_path, [{"pressAll": ["run-resume", "run-resume"]}, {"press": "run-undo-saved"}])
    assert len(_api_calls(out, "/filled-answers")) == len(_api_calls(once, "/filled-answers"))
    writes = [m for m in _api_calls(out, "/api/settings/autofill") if (m.get("init") or {}).get("method") == "PUT"]
    assert len(writes) == 2   # the learn, then Undo's put-back
    assert out["profile"] == OLD_PROFILE
    assert len(out["fills"]) == 3   # one drive: the parked page, the page again after Resume, the review


def test_a_skip_pressed_while_resume_reads_the_page_does_not_end_the_job_it_is_filling(tmp_path):
    out = _parked_on_questions(tmp_path, [{"pressAll": ["run-resume", "run-skip"]}])
    assert _record(out["mids"][0])["status"] == "filling"
    assert _record(out["shots"][-1])["status"] == "ready"


def test_skip_stops_any_drive_that_is_still_running(tmp_path):
    out = _run(tmp_path, [{"start": SEED}, {"press": "run-skip"}], pages=(STEP1, page("captcha", 1)))
    assert _record(out["shots"][-1])["stopRequested"] is True


# ---------- needs you: a hand fix teaches the recipe book and the known-gaps list ----------

Q1 = "Have you used our product before?"
A_FIELD = {"family": "f:abc123", "site": "s:def456"}
SHOWN = {"q1": {**A_FIELD, "gestures": ["open:keys"]}}
FIXED = [_field("q1", "Yes", question=Q1, shape="popup", touched=False)]
FIX_GAP = {"family": "abc123", "host": "jobs.acme.test", "shape": "popup", "outcome": "user_fixed"}


def _fixed(tmp_path, steps, shown=SHOWN, inventory=FIXED, gaps_reply=None, **spec):
    frames = {"fill_watch": [{"frameId": 0, "result": 1}],
              "fill_watch_report": [{"frameId": 0, "result": shown}]}
    return _run(tmp_path, [{"start": SEED}, *steps], pages=(STEP1, REVIEW),
                reports=[{"fields": [needs("q1", Q1)]}, {"fields": [verified("f1")]}],
                inventory=inventory, frames=frames, profileStore=json.loads(json.dumps(OLD_PROFILE)),
                replies={"fill_gaps": gaps_reply or _reply({"posted": 1})}, **spec)


def _gap_posts(out):
    return [msg["gaps"] for msg in out["sent"] if msg["type"] == "fill_gaps"]


def _book(out):
    """The recipe book as last written, or None when nothing was written."""
    books = [patch["fill.recipes"] for patch in out["writes"] if "fill.recipes" in patch]
    return books[-1] if books else None


def _entries(out):
    return (_book(out) or {"entries": {}})["entries"]


def test_a_park_on_questions_watches_those_fields_in_the_runs_tab_once(tmp_path):
    out = _fixed(tmp_path, [])
    watches = _page_messages(out, "fill_watch")
    assert [(msg["tabId"], msg["message"]["fids"]) for msg in watches] == [(7, ["q1"])]
    # No other park has fields to watch.
    walled = _run(tmp_path, [{"start": SEED}], pages=(STEP1, page("captcha", 1)))
    assert _page_messages(walled, "fill_watch") == []


def test_a_resume_whose_page_read_fails_still_ends_the_pages_watch(tmp_path):
    """The inventory read after Resume throws: the watch the park started is ended, not left running."""
    out = _fixed(tmp_path, [{"dropInventory": True}, {"press": "run-resume"}])
    assert [msg["message"]["fids"] for msg in _page_messages(out, "fill_watch")][-1] == []


def test_skipping_the_job_ends_the_pages_watch_and_asks_it_nothing(tmp_path):
    out = _fixed(tmp_path, [{"press": "run-skip"}])
    assert [msg["message"]["fids"] for msg in _page_messages(out, "fill_watch")] == [["q1"], []]
    assert _page_messages(out, "fill_watch_report") == [] and _gap_posts(out) == []


def test_resuming_from_a_wall_asks_the_page_nothing_about_a_fix(tmp_path):
    pages = (STEP1, page("captcha", 1), STEP2, REVIEW)
    out = _run(tmp_path, [{"start": SEED}, {"page": 2}, {"press": "run-resume", "finish": False}], pages=pages)
    assert _page_messages(out, "fill_watch_report") == [] and _gap_posts(out) == []


def test_resume_after_a_hand_fix_posts_a_user_fixed_gap_and_records_the_demonstration(tmp_path):
    out = _fixed(tmp_path, [{"press": "run-resume"}])
    [report] = _page_messages(out, "fill_watch_report")
    assert (report["tabId"], report["message"]["fids"]) == (7, ["q1"])
    # The family goes without its `f:` prefix; the host is the page's; no label or value rides along.
    assert _gap_posts(out) == [[FIX_GAP]]
    book = _book(out)
    assert book["entries"]["s:def456"] == {"moves": {"open": "keys"}, "state": "probation", "wins": 1,
                                           "seen": book["entries"]["s:def456"]["seen"]}
    assert book["entries"]["f:abc123"]["state"] == "probation"
    wire = json.dumps(_gap_posts(out)) + json.dumps(book)
    assert Q1 not in wire and "Yes" not in wire
    assert _record(out["shots"][-1])["status"] == "ready"


def test_a_fix_whose_move_the_engine_does_not_know_is_a_missing_technique(tmp_path):
    out = _fixed(tmp_path, [{"press": "run-resume"}], shown={"q1": {**A_FIELD, "gestures": []}},
                 inventory=[_field("q1", "Yes", question=Q1, shape="popup", touched=True)])
    assert _gap_posts(out) == [[FIX_GAP, {**FIX_GAP, "outcome": "missing_technique"}]]
    assert _entries(out) == {}


def test_the_generic_move_is_known_so_it_is_no_missing_technique_and_teaches_nothing(tmp_path):
    out = _fixed(tmp_path, [{"press": "run-resume"}], shown={"q1": {**A_FIELD, "gestures": ["open:press"]}})
    assert _gap_posts(out) == [[FIX_GAP]]
    assert _book(out) is None   # nothing worth teaching: the book is not even written


def test_the_recipe_book_is_taught_even_when_the_fill_log_is_off_and_the_sw_posts_nothing(tmp_path):
    """The sw gates the gap post on the fill log (its own tests); the recipe book is local and is not."""
    out = _fixed(tmp_path, [{"press": "run-resume"}], gaps_reply=_reply({"posted": 0}))
    assert _book(out)["entries"]["s:def456"]["state"] == "probation"
    assert _record(out["shots"][-1])["status"] == "ready"


def test_a_refused_gap_post_neither_blocks_the_resume_nor_is_sent_again(tmp_path):
    out = _fixed(tmp_path, [{"press": "run-resume"}],
                 gaps_reply={"ok": False, "error": "the backend is unreachable"})
    assert len(_gap_posts(out)) == 1
    assert _record(out["shots"][-1])["status"] == "ready"
    assert _book(out) is not None


def test_a_field_that_holds_nothing_after_the_fix_teaches_nothing(tmp_path):
    empty = [_field("q1", "", question=Q1, shape="popup", touched=False)]
    out = _fixed(tmp_path, [{"press": "run-resume"}], inventory=empty)
    assert _gap_posts(out) == [] and _book(out) is None


def test_a_value_nobody_touched_and_no_gesture_vouches_for_is_not_a_fix(tmp_path):
    out = _fixed(tmp_path, [{"press": "run-resume"}], shown={"q1": {**A_FIELD, "gestures": []}})
    assert _gap_posts(out) == [] and _book(out) is None


def test_a_field_without_a_family_has_nothing_to_key_a_lesson_by(tmp_path):
    out = _fixed(tmp_path, [{"press": "run-resume"}], shown={})
    assert _gap_posts(out) == [] and _book(out) is None


def test_a_touched_field_counts_as_fixed_even_when_no_gesture_was_seen(tmp_path):
    out = _fixed(tmp_path, [{"press": "run-resume"}], shown={"q1": {**A_FIELD, "gestures": []}},
                 inventory=[_field("q1", "Yes", question=Q1, shape="popup", touched=True)])
    assert [gap["outcome"] for gap in _gap_posts(out)[0]] == ["user_fixed", "missing_technique"]


def test_a_page_that_cannot_report_the_fix_does_not_stop_the_resume(tmp_path):
    """No frame answers `fill_watch_report` (a tab that lost its scripts): the answers are still
    saved, the run still goes on, and nothing is posted or taught."""
    out = _run(tmp_path, [{"start": SEED}, {"press": "run-resume"}], pages=(STEP1, REVIEW),
               reports=[{"fields": [needs("q1", Q1)]}, {"fields": [verified("f1")]}],
               inventory=FIXED, profileStore=json.loads(json.dumps(OLD_PROFILE)))
    assert _record(out["shots"][-1])["status"] == "ready" and _gap_posts(out) == [] and _book(out) is None


def test_the_leftovers_of_each_page_join_the_known_gaps_once(tmp_path):
    trace = {"host": "jobs.acme.test", "fields": [
        {"fid": "g1", "shape": "popup", "family": "f:zz99", "outcome": "cannot_operate"},
        {"fid": "g2", "shape": "search", "family": "f:yy88", "outcome": "unconfirmed"},
        {"fid": "g3", "shape": "popup", "family": "f:xx77", "outcome": "verified"},
        {"fid": "g4", "shape": "text", "outcome": "cannot_operate"}]}
    leftover = [{"fid": "g1", "question": "Pick", "required": False, "status": "cannot_operate"}]
    out = _run(tmp_path, [{"start": SEED}], pages=(STEP1, REVIEW),
               reports=[{"fields": leftover, "trace": trace}, {"fields": [verified("f1")], "trace": trace}],
               replies={"fill_gaps": _reply({"posted": 2})})
    assert _gap_posts(out) == [[
        {"family": "zz99", "host": "jobs.acme.test", "shape": "popup", "outcome": "cannot_operate"},
        {"family": "yy88", "host": "jobs.acme.test", "shape": "search", "outcome": "unconfirmed"}]]


# ---------- ready to submit, and the 8 s auto-mark ----------


CONFIRM = page("confirmation", 9)


def _ready_then_confirmation(tmp_path, steps, **spec):
    base = [{"start": SEED}, {"page": 2, "update": {"tab": 7, "change": {"url": CONFIRM["url"]}}}]
    return _run(tmp_path, [*base, *steps], pages=(STEP1, REVIEW, CONFIRM), **spec)


def test_ready_lists_the_receipts_flags_as_check_before_you_submit(tmp_path):
    flags = {"flags": [{"index": 0, "question": "Salary", "flags": [{"reason": "Not in your profile"}]}]}
    out = _run(tmp_path, [{"start": SEED}], pages=(STEP1, REVIEW),
               inventory=[_field("f1", "Ada", question="Name")],
               api={"POST /api/jobs/job-1/filled-answers": _reply(flags)})
    text = _body_text(out["shots"][1])
    assert "Check before you submit" in text and "Salary" in text and "Not in your profile" in text
    # Nothing to press in the panel: the user submits in the tab. (The flag's jump link has no id.)
    assert _buttons(_card(out["shots"][1])["body"]) == {"run-done": "Done"}


def test_a_confirmation_page_after_your_submit_starts_a_countdown_and_posts_nothing_before_it_ends(tmp_path):
    out = _ready_then_confirmation(tmp_path, [])
    shot = out["shots"][-1]
    assert _record(shot)["status"] == "confirming" and _card(shot)["title"] == "Marking applied"
    assert "Marking applied in 8 s · Undo" in _body_text(shot)
    assert out["held"] == 1
    assert not _api_calls(out, "companion-submitted")


def test_after_8_seconds_the_confirmation_words_and_nothing_else_are_posted_and_the_job_is_applied(tmp_path):
    out = _ready_then_confirmation(
        tmp_path, [{"fire": True}],
        api={"POST /api/proposals/prop-1/companion-submitted": _reply({"id": "prop-1", "status": "submitted"})})
    [post] = _api_calls(out, "companion-submitted")
    assert json.loads(post["init"]["body"]) == {"confirmation": {
        "host": "jobs.acme.test", "path": "/apply/confirmation9", "text": "Thank you for applying"}}
    shot = out["shots"][-1]
    assert (_record(shot)["status"], _card(shot)["title"]) == ("applied", "Applied")


POSTED = {"POST /api/proposals/prop-1/companion-submitted": _reply({"id": "prop-1", "status": "submitted"})}


def _confirmation_posted(out):
    return [json.loads(post["init"]["body"])["confirmation"] for post in _api_calls(out, "companion-submitted")]


def test_closing_the_tab_inside_the_8_seconds_marks_at_once_with_the_page_the_run_saw(tmp_path):
    """The user's Submit went through; closing the tab is no cancel. The mark does not wait out the
    countdown (Undo's window closes with the tab) and needs no tab to read."""
    out = _ready_then_confirmation(tmp_path, [{"tabUrl": "", "removed": 7}], api=POSTED)
    assert _confirmation_posted(out) == [{"host": "jobs.acme.test", "path": "/apply/confirmation9",
                                          "text": "Thank you for applying"}]
    assert _record(out["shots"][-1])["status"] == "applied"
    assert out["held"] == 0


def test_moving_on_inside_the_8_seconds_does_not_change_the_page_the_mark_names(tmp_path):
    away = "https://news.example.test/front-page"
    out = _ready_then_confirmation(tmp_path, [{"tabUrl": away, "update": {"tab": 7, "change": {"url": away}}},
                                              {"fire": True}], api=POSTED)
    assert _confirmation_posted(out) == [{"host": "jobs.acme.test", "path": "/apply/confirmation9",
                                          "text": "Thank you for applying"}]


def test_a_mark_that_fails_as_the_tab_closes_says_so_on_the_stopped_card(tmp_path):
    out = _ready_then_confirmation(tmp_path, [{"removed": 7}],
                                   api={"POST /api/proposals/prop-1/companion-submitted":
                                        {"ok": False, "error": "Server unavailable", "status": 500}})
    record = _record(out["shots"][-1])
    assert (record["status"], record["why"]) == ("stopped", "tab_closed")
    assert "Couldn't mark this applied" in _body_text(out["shots"][-1])


def test_a_mark_already_in_flight_that_fails_after_the_tab_closed_ends_stopped_with_its_note(tmp_path):
    """The countdown ended and the mark was on its way when the tab closed; the answer is a failure.
    A ready record on a closed tab would be invisible: it ends where the user can read why."""
    out = _ready_then_confirmation(
        tmp_path, [{"fire": True}, {"removed": 7}, {"releaseApi": True}],
        hold=["companion-submitted"],
        api={"POST /api/proposals/prop-1/companion-submitted": {"ok": False, "error": "Server unavailable", "status": 500}})
    record = _record(out["shots"][-1])
    assert (record["status"], record["why"]) == ("stopped", "tab_closed")
    assert "Couldn't mark this applied" in _body_text(out["shots"][-1])


def test_a_confirmation_page_on_a_host_the_run_never_reached_starts_no_countdown(tmp_path):
    """The user decided against Submitting and opened another employer's thank-you in the same tab."""
    other = page("confirmation", 9, host="careers.globex.test")
    out = _run(tmp_path, [{"start": SEED}, {"page": 2, "update": {"tab": 7, "change": {"url": other["url"]}}},
                          {"fire": True}], pages=(STEP1, REVIEW, other), api=POSTED)
    shot = out["shots"][-1]
    assert (_record(shot)["status"], _record(shot)["noAutoMark"]) == ("ready", True)
    assert out["held"] == 0 and not _api_calls(out, "companion-submitted")
    assert set(_buttons(_card(shot)["body"])) == {"run-mark", "run-done"}


def test_another_employers_thank_you_on_the_same_ats_host_starts_no_countdown(tmp_path):
    """Job A is Ready at /apply; the user applies to another employer's job on the same host by hand."""
    theirs = {**CONFIRM, "url": "https://jobs.acme.test/globex/thanks"}
    out = _run(tmp_path, [{"start": SEED}, {"page": 2, "update": {"tab": 7, "change": {"url": theirs["url"]}}},
                          {"fire": True}], pages=(STEP1, REVIEW, theirs), api=POSTED)
    shot = out["shots"][-1]
    assert (_record(shot)["status"], _record(shot)["noAutoMark"]) == ("ready", True)
    assert out["held"] == 0 and not _api_calls(out, "companion-submitted")


def test_a_ready_tab_that_browses_on_loses_the_auto_mark_and_a_later_thank_you_does_not_get_it_back(tmp_path):
    away = page("closed", 4)
    out = _run(tmp_path, [{"start": SEED}, {"page": 2, "update": {"tab": 7, "change": {"url": away["url"]}}},
                          {"page": 3, "update": {"tab": 7, "change": {"url": CONFIRM["url"]}}}],
               pages=(STEP1, REVIEW, away, CONFIRM), api=POSTED)
    assert _record(out["shots"][-1])["status"] == "ready" and out["held"] == 0


def test_done_on_a_ready_card_ends_the_record_writes_nothing_and_frees_the_tab(tmp_path):
    before = _run(tmp_path, [{"start": SEED}], pages=(STEP1, REVIEW))
    out = _run(tmp_path, [{"start": SEED}, {"press": "run-done"}], pages=(STEP1, REVIEW))
    assert "Done" in _buttons(_card(out["shots"][1])["body"]).values()
    assert out["shots"][-1]["runs"] == []
    posted = lambda one: [(m["path"], m["init"].get("method")) for m in one["sent"]  # noqa: E731
                          if m["type"] == "api" and (m.get("init") or {}).get("method") in ("POST", "PATCH", "PUT")]
    assert posted(out) == posted(before)
    # The tab is free: a new Apply starts a record again.
    again = _run(tmp_path, [{"start": SEED}, {"press": "run-done"}, {"start": SEED}], pages=(STEP1, REVIEW))
    assert _record(again["shots"][-1])["status"] == "ready"


def test_done_on_a_ready_card_is_not_undone_by_a_confirmation_read_in_flight(tmp_path):
    out = _run(tmp_path, [{"start": SEED}, {"press": "run-done"},
                          {"page": 2, "update": {"tab": 7, "change": {"url": CONFIRM["url"]}}}, {"fire": True}],
               pages=(STEP1, REVIEW, CONFIRM), api=POSTED)
    assert out["shots"][-1]["runs"] == [] and not _api_calls(out, "companion-submitted")


def test_a_read_that_fails_mid_submit_leaves_the_run_ready_and_never_saved_as_stopped(tmp_path):
    navigating = {"throws": True, "summary": STEP1["summary"], "url": "https://jobs.acme.test/apply/loading"}
    out = _run(tmp_path, [{"start": SEED}, {"page": 2, "update": {"tab": 7, "change": {"url": navigating["url"]}}}],
               pages=(STEP1, REVIEW, navigating))
    assert _record(out["shots"][-1])["status"] == "ready"
    saved = [runs[0]["status"] for runs in out["queueSaves"]]
    assert saved[-1] == "ready" and "stopped" not in saved


def test_undo_inside_the_8_seconds_posts_nothing_and_leaves_a_manual_mark_applied(tmp_path):
    out = _ready_then_confirmation(tmp_path, [{"press": "run-undo"}, {"fire": True}])
    assert not _api_calls(out, "companion-submitted")
    shot = out["shots"][-1]
    assert _record(shot)["status"] == "ready" and _buttons(_card(shot)["body"]) == {"run-mark": "Mark applied", "run-done": "Done"}


def test_the_manual_mark_applied_posts_to_the_same_endpoint(tmp_path):
    out = _ready_then_confirmation(
        tmp_path, [{"press": "run-undo"}, {"press": "run-mark"}],
        api={"POST /api/proposals/prop-1/companion-submitted": _reply({"id": "prop-1", "status": "submitted"})})
    assert len(_api_calls(out, "companion-submitted")) == 1
    assert _record(out["shots"][-1])["status"] == "applied"


def test_a_409_shows_the_servers_sentence_and_offers_mark_applied_through_the_application(tmp_path):
    conflict = {"ok": False, "error": "Cannot move to submitted from rejected", "status": 409}
    out = _ready_then_confirmation(
        tmp_path, [{"fire": True}, {"press": "run-mark"}],
        api={"POST /api/proposals/prop-1/companion-submitted": conflict,
             "PATCH /api/applications/app-1": _reply({**APPLICATION, "status": "applied"})})
    after_409 = out["shots"][-2]
    assert _record(after_409)["status"] == "ready"
    assert "Cannot move to submitted from rejected" in _body_text(after_409)
    assert len(_api_calls(out, "companion-submitted")) == 1
    [patch] = [msg for msg in _api_calls(out, "/api/applications/app-1") if (msg.get("init") or {}).get("method") == "PATCH"]
    assert json.loads(patch["init"]["body"]) == {"status": "applied"}
    assert _record(out["shots"][-1])["status"] == "applied"


def test_the_users_time_after_ready_stops_when_the_confirmation_is_detected(tmp_path):
    """Ready to the confirmation is the user's (checking the form, pressing Submit). The 8 s, the network
    and an Undo are not: 20 s before the page, 30 s after it, and only the first is counted."""
    posted = {"POST /api/proposals/prop-1/companion-submitted": _reply({"id": "prop-1", "status": "submitted"})}
    base = [{"start": SEED}, {"skew": 20_000}, {"page": 2, "update": {"tab": 7, "change": {"url": CONFIRM["url"]}}}]
    out = _run(tmp_path, [*base, {"skew": 30_000}, {"fire": True}], pages=(STEP1, REVIEW, CONFIRM), api=posted)
    assert 20_000 <= _record(out["shots"][-1])["yourMs"] < 30_000
    out = _run(tmp_path, [*base, {"press": "run-undo"}, {"skew": 30_000}, {"press": "run-mark"}],
               pages=(STEP1, REVIEW, CONFIRM), api=posted)
    assert 20_000 <= _record(out["shots"][-1])["yourMs"] < 30_000


def test_a_matched_application_form_on_another_origin_is_kept_not_navigated_away_from(tmp_path):
    """The posting was saved from a board; the run starts on the employer's ATS form, which the backend
    matched to the job. Progress on it is kept. On the board itself the run still moves to the link."""
    saved = {"match": "exact", "job": {"id": "job-1", "company": "Acme", "title": "Data Scientist"},
             "application": None}
    seed = {**SEED, "openUrl": "https://careers.acme.test/jobs/77/apply"}
    out = _run(tmp_path, [{"start": seed}], api={"/api/jobs/match": _reply(saved)})
    assert out["updates"] == []
    board = "https://www.linkedin.com/jobs/view/123"
    out = _run(tmp_path, [{"start": seed}], api={"/api/jobs/match": _reply(saved)},
               tabs=[{"id": 7, "url": board}], tabUrls={"7": board}, afterNavigate=0)
    assert out["updates"] == [[7, {"url": seed["openUrl"]}]]


def test_a_run_in_place_never_navigates_the_tab_and_parks_when_the_tab_is_not_the_page_it_was_for(tmp_path):
    """The user picked the job for THIS page. If the tab shows another site by the time the run reads it,
    the run does not drive that page as this job, and does not drag the tab back either."""
    in_place = {**SEED, "inPlace": True}
    out = _run(tmp_path, [{"start": in_place}])
    assert out["updates"] == []
    record = _record(out["shots"][-1])
    assert record["inPlace"] is True and record["status"] == "ready"
    board = "https://www.linkedin.com/jobs/view/123"
    out = _run(tmp_path, [{"start": in_place}], tabs=[{"id": 7, "url": board}], tabUrls={"7": board},
               afterNavigate=0)
    assert out["updates"] == []
    assert (_record(out["shots"][-1])["status"], _record(out["shots"][-1])["why"]) == ("parked", "moved_away")


def test_done_takes_a_finished_record_off_the_tab(tmp_path):
    out = _ready_then_confirmation(
        tmp_path, [{"fire": True}, {"press": "run-done"}],
        api={"POST /api/proposals/prop-1/companion-submitted": _reply({"id": "prop-1", "status": "submitted"})})
    assert out["shots"][-1]["runs"] == []
    assert "Applied" != _card(out["shots"][-1])["title"]


# ---------- the saved login ----------


def test_the_saved_password_reaches_one_message_and_nowhere_else(tmp_path):
    password = "hunter2-secret-9"
    login = page("sign_in", 1, host="acme.myworkdayjobs.com")
    seed = {**SEED, "openUrl": "https://acme.myworkdayjobs.com/en-US/apply"}
    out = _run(tmp_path, [{"start": seed}], pages=(login, STEP1, REVIEW),
               tabs=[{"id": 7, "url": "https://acme.myworkdayjobs.com/en-US/apply"}],
               api={"/api/companion/job-site-login": _reply({"email": "ada@example.test", "password": password})})
    carriers = [msg for msg in out["sent"] if password in json.dumps(msg)]
    assert [msg["type"] for msg in carriers] == ["panel_frame0"]
    assert carriers[0]["message"]["type"] == "page_sign_in"
    rest = {key: out[key] for key in ("shots", "writes", "sessionWrites", "broadcasts")}
    assert password not in json.dumps(rest)
    assert _record(out["shots"][-1])["status"] == "ready"


def test_a_site_that_is_not_a_known_ats_never_gets_the_password(tmp_path):
    login = page("sign_in", 1)
    out = _run(tmp_path, [{"start": SEED}], pages=(login,),
               api={"/api/companion/job-site-login": _reply({"email": "a@b.test", "password": "pw-never-sent"})})
    record = _record(out["shots"][-1])
    assert (record["status"], record["why"]) == ("parked", "sign_in_yourself")
    assert not _api_calls(out, "job-site-login")
    assert "Sign in yourself" in _body_text(out["shots"][-1])


# ---------- the card does not leak the app's other buttons into a run ----------


def test_while_a_run_is_live_the_footer_has_no_autofill_and_the_run_has_one_start_per_tab(tmp_path):
    out = _run(tmp_path, [{"start": SEED, "background": True}, {"start": SEED}],
               reports=[{"fields": [verified("f1")], "hold": True}])
    assert len(out["shots"][1]["runs"]) == 1
    assert "Autofill" not in _text(out["shots"][1]["regions"]["foot"])


def test_a_ready_run_a_reopened_panel_still_sees_is_marked_after_the_users_submit(tmp_path):
    ready = _seeded("ready", readyAt=1)
    out = _run(tmp_path, [{"page": 0, "update": {"tab": 7, "change": {"url": CONFIRM["url"]}}}],
               pages=(CONFIRM,), sessionStored={"queueRun": [ready]})
    assert _record(out["shots"][0])["status"] == "ready" and "Check the page" in _body_text(out["shots"][0])
    assert _record(out["shots"][-1])["status"] == "confirming" and out["held"] == 1


def test_a_ready_run_on_another_windows_tab_is_shown_but_this_panel_arms_nothing_for_it(tmp_path):
    """Every window's panel hears every tab. The one that owns the record arms the auto-mark; a second
    would post it again, and an Undo in the first would not reach its timer."""
    theirs = _seeded("ready", readyAt=1, lease="panel-of-the-other-window")
    out = _run(tmp_path, [{"page": 0, "update": {"tab": 7, "change": {"url": CONFIRM["url"]}}}],
               pages=(CONFIRM,), sessionStored={"queueRun": [theirs]}, windowIds={"7": 2})
    assert _record(out["shots"][0])["status"] == "ready" and "Check the page" in _body_text(out["shots"][0])
    assert _record(out["shots"][-1])["status"] == "ready" and out["held"] == 0


def test_a_ready_run_a_reopened_panel_finds_in_its_own_window_becomes_its_own(tmp_path):
    left_by_the_last_panel = _seeded("ready", readyAt=1, lease="panel-that-was-closed")
    out = _run(tmp_path, [{"page": 0, "update": {"tab": 7, "change": {"url": CONFIRM["url"]}}}],
               pages=(CONFIRM,), sessionStored={"queueRun": [left_by_the_last_panel]})
    assert _record(out["shots"][-1])["status"] == "confirming" and out["held"] == 1


def test_resuming_a_record_another_panel_left_makes_it_this_panels_to_arm(tmp_path):
    """An interrupted record whose tab moved into this window is shown but not adopted at boot. Resume is
    this panel taking it over: the mark after the user's Submit must have an owner."""
    theirs = _seeded("stopped", why="interrupted", lease="panel-of-the-other-window")
    out = _run(tmp_path, [{"press": "run-resume"}, {"page": 1, "update": {"tab": 7, "change": {"url": CONFIRM["url"]}}}],
               pages=(REVIEW, CONFIRM), sessionStored={"queueRun": [theirs]}, windowIds={"7": 2})
    assert _record(out["shots"][1])["status"] == "ready"
    assert _record(out["shots"][-1])["status"] == "confirming" and out["held"] == 1


def test_a_reopened_panel_gives_the_runs_tab_its_job_back_from_the_record(tmp_path):
    parked = _seeded("parked", why="captcha")
    out = _run(tmp_path, [], pages=(page("captcha", 1),), sessionStored={"queueRun": [parked]})
    assert "Data Scientist" in _text(out["shots"][0]["regions"]["identity"])
    assert _card(out["shots"][0])["title"] == "Needs you"


# ---------- a Next the page rejects: its errors are read, only the fields they name are repaired ----------

BANNER = [_btn("e-1", "Errors Found", inErrors=True), _btn("e-2", "Error - City", inErrors=True)]
# The same step, the same address, after a press the page refused: its banner is up.
STEP1_REJECTED = {"summary": {**STEP1["summary"], "errors": 1,
                              "buttons": [*STEP1["summary"]["buttons"], *BANNER]}, "url": STEP1["url"]}
CITY_ERROR = {"count": 1, "items": [{"label": "City", "target": "f-city", "kind": "field"}]}
UPLOAD_ERROR = {"count": 1, "items": [{"label": "Upload a file (5MB max)", "target": "t-up", "kind": "upload"}]}


def _rejected(tmp_path, error=CITY_ERROR, pages=(STEP1, STEP1_REJECTED, REVIEW), **spec):
    spec.setdefault("reports", [{"fields": [verified("f-city", "City")]}, {"fields": [verified("f-city", "City")]},
                                {"fields": [verified("f1")]}])
    spec["frames"] = {"page_errors": [{"frameId": 0, "result": error}], **spec.get("frames", {})}
    return _run(tmp_path, [{"start": SEED}], pages=pages, **spec)


def test_a_rejected_next_repairs_only_the_named_field_and_presses_again(tmp_path):
    out = _rejected(tmp_path)
    record = _record(out["shots"][1])
    assert (record["status"], record["step"], record["readyAt"] is not None) == ("ready", 1, True)
    # Page 1's fill, the repair of City alone, then the review page's fill.
    only = [call["options"].get("only") for call in out["fills"]]
    assert only == [None, ["f-city"], None]
    assert len(_page_messages(out, "page_advance")) == 2
    assert len(_page_messages(out, "page_errors")) == 1
    # The repair is no page: the pages list counts the page once.
    assert [page["n"] for page in record["pages"]] == [1, 2]


def test_the_page_memory_lives_through_a_repair_and_is_new_on_the_next_page(tmp_path):
    out = _rejected(tmp_path)
    first, repair, review = (call["memoryId"] for call in out["fills"])
    assert first is not None and repair == first, "the repair keeps what the page's fill learnt"
    assert review != first, "a new step starts with an empty memory"


def test_the_page_memory_is_never_written_to_storage(tmp_path):
    out = _rejected(tmp_path)
    # Serialised it is nothing (JSON.stringify gives undefined, so the key is absent), on the record too.
    assert all("memoryJson" not in call for call in out["fills"])
    assert not any(run.get("memory") for save in out["queueSaves"] for run in save)
    # Not left to a serialiser's toJSON: the key is absent from what `save` hands to chrome.storage.
    assert out["queueSaveKeys"] and not any("memory" in keys for save in out["queueSaveKeys"] for keys in save)
    # The live record still has it: the repair above read the same memory the first fill built.
    assert out["fills"][0]["memoryId"] is not None


def test_a_repair_that_leaves_the_field_open_parks_naming_it(tmp_path):
    reports = [{"fields": [verified("f1")]}, {"fields": [needs("f-city", "City")]}]
    out = _rejected(tmp_path, reports=reports)
    record = _record(out["shots"][1])
    assert (record["status"], record["why"], record["step"]) == ("parked", "page_errors", 0)
    assert record["open"] == [{"fid": "f-city", "question": "City", "required": True}]
    assert len(_page_messages(out, "page_advance")) == 1


def test_the_card_for_a_page_errors_park_names_the_field_and_the_upload(tmp_path):
    record = _seeded("parked", why="page_errors", open=[
        {"fid": "f-city", "question": "City", "required": True},
        {"fid": None, "question": "Upload a file (5MB max)", "required": True}])
    out = _run(tmp_path, [{"seed": [record]}, {"pressText": "City"}])
    body = _card(out["shots"][1])["body"]
    assert "The page asks for more" in _text(body)
    [named] = _by_class(body, "resid")
    assert [_text(item) for item in named["children"]] == ["City", "Upload a file (5MB max)"]
    # The upload has nothing in the page to jump to; the field has.
    assert [btn for btn in _walk(named) if btn["tag"] == "BUTTON"] and len([b for b in _walk(named) if b["tag"] == "BUTTON"]) == 1
    [focus] = _page_messages(out, "fill_focus")
    assert focus["message"]["fid"] == "f-city"


# ---------- the resume before Next: the attach line, the gate, the count ----------

BOX = {"label": "Upload a file (5MB max)", "target": "t-up", "required": True, "occupied": False, "kind": "unknown"}
# The box the run's own attach cannot tell is the resume's: one upload, kind unknown.
UNKNOWN_BOX = {"tier": "B", "form": True, "score": 2, "fileInputs": 1, "uploads": [{"kind": "unknown", "occupied": False}]}
ATTACHED_ONE = _reply([{"frameId": 0, "result": {"written": 1, "proven": 1}}])
ATTACHED_NONE = _reply([{"frameId": 0, "result": {"written": 0, "proven": 0}}])


def _upload_run(tmp_path, reply, boxes=(BOX,), **spec):
    spec["frames"] = {"page_uploads": [{"frameId": 0, "result": list(boxes)}], **spec.get("frames", {})}
    spec.setdefault("page", {"detect_page": _reply(UNKNOWN_BOX)})
    spec.setdefault("replies", {})["attach_pdf"] = reply
    return _run(tmp_path, [{"start": SEED}], pages=(STEP1, REVIEW), callBeforeSweep=True, **spec)


def _attach_asks(out):
    return [msg for msg in out["sent"] if msg["type"] == "attach_pdf"]


def test_a_required_empty_upload_the_run_could_not_classify_is_attached_to_by_handle_before_next(tmp_path):
    out = _upload_run(tmp_path, ATTACHED_ONE)
    asks = _attach_asks(out)
    # The run's own attach left the unclassified box (it sent nothing); the gate's targeted one named it.
    # (The fake page keeps answering that the box is empty, so its second page asks again.)
    assert [(ask["target"], ask["resumeOnly"]) for ask in asks[:1]] == [("t-up", True)]
    assert not [ask for ask in asks if ask["target"] != "t-up"]
    record = _record(out["shots"][1])
    assert record["status"] == "ready" and record["attach"]["outcome"] == "attached"
    # The first press came after the first write.
    first_press = next(i for i, msg in enumerate(out["broadcasts"]) if msg["message"]["type"] == "page_advance")
    assert first_press >= 1


def test_an_attach_the_page_does_not_take_parks_upload_naming_the_box_and_presses_nothing(tmp_path):
    out = _upload_run(tmp_path, ATTACHED_NONE)
    record = _record(out["shots"][1])
    assert (record["status"], record["why"], record["step"]) == ("parked", "upload", 0)
    assert record["open"] == [{"fid": None, "question": "Upload a file (5MB max)", "required": True}]
    assert not _page_messages(out, "page_advance")
    body = _body_text(out["shots"][1])
    assert "Upload a file (5MB max)" in body and "resume" in body.lower()


PARSER = {"label": "Import Resume", "target": "t-parser", "required": False, "occupied": False, "kind": "parser"}
REAL = {"label": "Resume Upload", "target": "t-real", "required": True, "occupied": False, "kind": "resume"}
PARSER_AND_REAL = {"tier": "B", "form": True, "score": 2, "fileInputs": 2,
                   "uploads": [{"kind": "parser", "occupied": False}, {"kind": "resume", "occupied": False}]}


def test_a_parser_box_beside_an_empty_required_resume_box_is_never_attached_to(tmp_path):
    """Live ATS-D shape: the run's own attach picks the one resume box (resume-only, two boxes counted);
    the parser (not required) is neither written nor parked on."""
    out = _upload_run(tmp_path, ATTACHED_ONE, boxes=[PARSER, REAL], page={"detect_page": _reply(PARSER_AND_REAL)})
    asks = _attach_asks(out)
    assert asks and all((ask["resumeOnly"], ask.get("expect")) == (True, 2) for ask in asks[:1])
    assert not [ask for ask in asks if ask.get("target") == "t-parser"]
    record = _record(out["shots"][1])
    assert record["status"] == "ready" and record["attach"]["outcome"] == "attached"


def test_a_parser_box_beside_a_resume_box_the_page_would_not_take_parks_naming_only_the_real_box(tmp_path):
    out = _upload_run(tmp_path, ATTACHED_NONE, boxes=[PARSER, REAL], page={"detect_page": _reply(PARSER_AND_REAL)})
    record = _record(out["shots"][1])
    assert (record["status"], record["why"]) == ("parked", "upload")
    assert record["open"] == [{"fid": None, "question": "Resume Upload", "required": True}]


def test_a_lone_required_parser_box_parks_upload_naming_it(tmp_path):
    """The Companion never writes a parser box, so a required one is the user's to attach by hand."""
    parser = {**PARSER, "required": True}
    lone = {"tier": "B", "form": True, "score": 2, "fileInputs": 1, "uploads": [{"kind": "parser", "occupied": False}]}
    out = _upload_run(tmp_path, ATTACHED_NONE, boxes=[parser], page={"detect_page": _reply(lone)})
    record = _record(out["shots"][1])
    assert (record["status"], record["why"], record["step"]) == ("parked", "upload", 0)
    assert record["open"] == [{"fid": None, "question": "Import Resume", "required": True}]
    assert not _page_messages(out, "page_advance")


def test_a_page_with_no_required_empty_upload_sends_no_targeted_attach(tmp_path):
    out = _upload_run(tmp_path, ATTACHED_ONE, boxes=[{**BOX, "required": False}])
    assert [ask for ask in _attach_asks(out) if ask.get("target")] == []
    assert _record(out["shots"][1])["status"] == "ready"


def test_a_write_the_page_may_have_taken_but_did_not_show_is_unconfirmed_not_left(tmp_path):
    """Written and not proven: the file may be on the page, so the card hedges and the run parks (it never
    writes a second copy). Not "the Companion left the upload box for you"."""
    wrote_unproven = _reply([{"frameId": 0, "result": {"written": 1, "proven": 0}}])
    out = _upload_run(tmp_path, wrote_unproven, api={"GET /api/applications/app-1": _reply(APPLICATION)})
    record = _record(out["shots"][1])
    assert (record["status"], record["why"]) == ("parked", "upload")
    assert record["attach"]["outcome"] == "unconfirmed"
    assert len([ask for ask in _attach_asks(out) if ask.get("target")]) == 1


def test_an_error_that_names_an_upload_box_is_repaired_by_attaching_to_it(tmp_path):
    rejected = {**STEP1_REJECTED}
    frames = {"page_errors": [{"frameId": 0, "result": UPLOAD_ERROR}], "page_uploads": [{"frameId": 0, "result": []}]}
    out = _run(tmp_path, [{"start": SEED}], pages=(STEP1, rejected, REVIEW), frames=frames,
               replies={"attach_pdf": ATTACHED_ONE},
               reports=[{"fields": [verified("f1")]}, {"fields": [verified("f1")]}])
    record = _record(out["shots"][1])
    assert (record["status"], record["step"]) == ("ready", 1)
    assert [(ask["target"], ask["resumeOnly"]) for ask in _attach_asks(out)] == [("t-up", True)]
    # Only the upload was repaired: the page was not filled again.
    assert [call["options"].get("only") for call in out["fills"]] == [None, None]


def test_an_upload_error_the_attach_cannot_repair_parks_page_errors(tmp_path):
    frames = {"page_errors": [{"frameId": 0, "result": UPLOAD_ERROR}], "page_uploads": [{"frameId": 0, "result": []}]}
    out = _run(tmp_path, [{"start": SEED}], pages=(STEP1, STEP1_REJECTED, REVIEW), frames=frames,
               replies={"attach_pdf": ATTACHED_NONE})
    record = _record(out["shots"][1])
    assert (record["status"], record["why"], record["step"]) == ("parked", "page_errors", 0)
    assert record["open"] == [{"fid": None, "question": "Upload a file (5MB max)", "required": True}]


@pytest.mark.parametrize("attach,line", [
    ({"outcome": "attached"}, "Resume attached"),
    ({"outcome": "skipped", "text": "The upload box isn't for a resume, so the Companion left it."},
     "Couldn't attach the resume: The upload box isn't for a resume, so the Companion left it."),
    ({"outcome": "left", "text": "The Companion left the upload box for you."},
     "Couldn't attach the resume: The Companion left the upload box for you."),
    ({"outcome": "unconfirmed", "text": "Couldn't confirm the upload. Check the upload box, and attach your resume only if it isn't listed."},
     "Couldn't confirm the upload. Check the upload box, and attach your resume only if it isn't listed."),
])
def test_the_card_says_how_the_attach_went_on_the_page_line(tmp_path, attach, line):
    out = _run(tmp_path, [{"seed": [_seeded("filling", attach=attach, progress={"done": 1, "total": 2})]}])
    assert line in _body_text(out["shots"][1])


def test_a_run_that_has_not_attached_anything_says_nothing_of_it(tmp_path):
    out = _run(tmp_path, [{"seed": [_seeded("filling", progress={"done": 1, "total": 2})]}])
    text = _body_text(out["shots"][1])
    assert "attach" not in text.lower() and "Resume attached" not in text


def test_the_page_counts_only_what_ended_answered_and_each_upload_box_as_one_field(tmp_path):
    fields = [verified("f1"), needs("f2", "Cell"), {**verified("f3"), "status": "unconfirmed"},
              {**verified("f4"), "status": "already"}, {**verified("f5"), "status": "yours"}]
    taken = {**BOX, "occupied": True}
    out = _run(tmp_path, [{"start": SEED}], pages=(STEP1, REVIEW), reports=[{"fields": fields}],
               inventory=[{"fid": f"f{n}"} for n in range(1, 6)],
               frames={"page_uploads": [{"frameId": 0, "result": [taken]}]})
    record = _record(out["shots"][1])
    assert record["why"] == "open_questions"
    # Answered: verified, already, yours (not the one the page took back, not the one still open),
    # plus the upload that holds a file. Of five fields and one upload box.
    assert record["progress"] == {"done": 4, "total": 6}


# ---------- one resume write per page, whatever the gate or a repair would like ----------

TWO_UPLOADS = {"count": 2, "items": [{"label": "Upload one", "target": "t-1", "kind": "upload"},
                                     {"label": "Upload two", "target": "t-2", "kind": "upload"}]}
RESUME_BOX = {"tier": "B", "form": True, "score": 2, "fileInputs": 1, "uploads": [{"kind": "resume", "occupied": False}]}


def test_two_upload_errors_are_never_both_the_resumes_so_the_run_parks_and_writes_nothing(tmp_path):
    frames = {"page_errors": [{"frameId": 0, "result": TWO_UPLOADS}], "page_uploads": [{"frameId": 0, "result": []}]}
    out = _run(tmp_path, [{"start": SEED}], pages=(STEP1, STEP1_REJECTED, REVIEW), frames=frames,
               replies={"attach_pdf": ATTACHED_ONE})
    record = _record(out["shots"][1])
    assert (record["status"], record["why"]) == ("parked", "page_errors")
    assert [o["question"] for o in record["open"]] == ["Upload one", "Upload two"]
    assert _attach_asks(out) == []


def test_a_cover_letter_box_is_never_written_and_the_run_parks_naming_it(tmp_path):
    cover = {**BOX, "label": "Cover letter", "kind": "other"}
    out = _upload_run(tmp_path, ATTACHED_ONE, boxes=[cover])
    record = _record(out["shots"][1])
    assert (record["status"], record["why"]) == ("parked", "upload")
    assert [o["question"] for o in record["open"]] == ["Cover letter"]
    assert [ask for ask in _attach_asks(out) if ask.get("target")] == []


def test_a_write_the_run_could_not_prove_is_not_repeated_when_the_next_is_refused_over_the_same_box(tmp_path):
    """The run's own attach wrote and could not prove it; the page then refuses Next naming the upload.
    A second copy is what the hedge is for: the run parks instead."""
    frames = {"page_errors": [{"frameId": 0, "result": UPLOAD_ERROR}],
              "page_uploads": [{"frameId": 0, "result": [{**BOX, "kind": "resume"}]}]}
    wrote_unproven = _reply([{"frameId": 0, "result": {"written": 1, "proven": 0}}])
    out = _run(tmp_path, [{"start": SEED}], pages=(STEP1, STEP1_REJECTED, REVIEW), frames=frames, callBeforeSweep=True,
               page={"detect_page": _reply(RESUME_BOX)}, replies={"attach_pdf": wrote_unproven})
    record = _record(out["shots"][1])
    assert (record["status"], record["why"]) == ("parked", "page_errors")
    assert len(_attach_asks(out)) == 1, "one write in all: the automatic one"


def test_a_resume_after_an_unconfirmed_gate_write_presses_on_and_never_writes_a_second_copy(tmp_path):
    wrote_unproven = _reply([{"frameId": 0, "result": {"written": 1, "proven": 0}}])
    out = _upload_run_steps(tmp_path, wrote_unproven, [{"start": SEED}, {"press": "run-resume"}],
                            api={"GET /api/applications/app-1": _reply(APPLICATION)})
    first = _record(out["shots"][1])
    assert (first["why"], first["attach"]["outcome"], first["attach"]["target"]) == ("upload", "unconfirmed", "t-up")
    # The box that was written is not "still empty": Next is pressed, page one is not filled again, and on
    # the review page (whose fake still shows an empty box) the gate refuses to write a second copy.
    assert len(_page_messages(out, "page_advance")) == 1 and len(out["fills"]) == 2
    record = _record(out["shots"][2])
    assert (record["status"], record["why"], record["step"]) == ("parked", "upload", 1)
    assert len(_attach_asks(out)) == 1, "one write in all"


def _upload_run_steps(tmp_path, reply, steps, boxes=(BOX,), **spec):
    spec["frames"] = {"page_uploads": [{"frameId": 0, "result": list(boxes)}], **spec.get("frames", {})}
    spec.setdefault("page", {"detect_page": _reply(UNKNOWN_BOX)})
    spec.setdefault("replies", {})["attach_pdf"] = reply
    return _run(tmp_path, steps, pages=(STEP1, REVIEW), callBeforeSweep=True, **spec)


# ---------- a Resume after a park the user fixed by hand does not refill the page ----------

def test_a_resume_after_page_errors_reads_the_errors_and_presses_when_none_remain(tmp_path):
    seeded = _seeded("parked", why="page_errors", open=[{"fid": "f-city", "question": "City", "required": True}],
                     seen=[], step=0, filled=True, wrote=True,
                     parkedPage={"where": STEP1["url"], "key": "step1"})
    out = _run(tmp_path, [{"seed": [seeded]}, {"press": "run-resume"}], pages=(STEP1, REVIEW),
               frames={"page_errors": [{"frameId": 0, "result": {"count": 0, "items": []}}]})
    record = _record(out["shots"][2])
    assert (record["status"], record["step"]) == ("ready", 1)
    # Only the review page was filled: the user fixed what was named.
    assert len(out["fills"]) == 1 and len(_page_messages(out, "page_errors")) == 1
    assert len(_page_messages(out, "page_advance")) == 1


def test_a_resume_after_page_errors_repairs_only_what_the_page_still_names(tmp_path):
    seeded = _seeded("parked", why="page_errors", open=[{"fid": "f-city", "question": "City", "required": True}],
                     seen=[], step=0, filled=True, wrote=True,
                     parkedPage={"where": STEP1["url"], "key": "step1"})
    out = _run(tmp_path, [{"seed": [seeded]}, {"press": "run-resume"}], pages=(STEP1, REVIEW),
               frames={"page_errors": [{"frameId": 0, "result": CITY_ERROR}]},
               reports=[{"fields": [verified("f-city", "City")]}, {"fields": [verified("f1")]}])
    assert [call["options"].get("only") for call in out["fills"]] == [["f-city"], None]


def test_a_scoped_repair_posts_no_answer_receipt(tmp_path):
    out = _rejected(tmp_path)
    # Three fills ran (page one, the repair of City, the review page); the repair posts no receipt.
    assert len(out["fills"]) == 3 and out["receiptCalls"] == 2


def test_the_card_does_not_call_a_box_that_already_held_a_file_a_failure(tmp_path):
    attach = {"outcome": "skipped", "reason": "occupied", "text": "A file is already attached. The Companion left it."}
    out = _run(tmp_path, [{"seed": [_seeded("filling", attach=attach, progress={"done": 1, "total": 2})]}])
    text = _body_text(out["shots"][1])
    assert "A file was already attached" in text and "Couldn't attach" not in text


# ---------- a stale upload line, and the Resume's look at where it landed ----------

def test_an_upload_error_over_a_box_that_already_holds_a_file_counts_as_repaired(tmp_path):
    """The user attached by hand; the page's banner still names the box: nothing is written, Next is pressed."""
    held = {**BOX, "occupied": True}
    frames = {"page_errors": [{"frameId": 0, "result": UPLOAD_ERROR}], "page_uploads": [{"frameId": 0, "result": [held]}]}
    out = _run(tmp_path, [{"start": SEED}], pages=(STEP1, STEP1_REJECTED, REVIEW), frames=frames,
               replies={"attach_pdf": ATTACHED_ONE})
    record = _record(out["shots"][1])
    assert (record["status"], record["step"]) == ("ready", 1)
    assert _attach_asks(out) == [] and len(_page_messages(out, "page_advance")) == 2


def _parked(why, **extra):
    return _seeded("parked", why=why, open=[{"fid": None, "question": "Upload a file (5MB max)", "required": True}],
                   seen=[], step=0, filled=True, wrote=True, **extra)


def test_a_resume_that_lands_on_another_page_fills_it_and_does_not_press_over_it(tmp_path):
    seeded = _parked("page_errors", parkedPage={"where": "https://jobs.acme.test/apply/other9", "key": "other9"})
    out = _run(tmp_path, [{"seed": [seeded]}, {"press": "run-resume"}], pages=(STEP1, REVIEW),
               frames={"page_errors": [{"frameId": 0, "result": {"count": 0, "items": []}}]})
    assert len(out["fills"]) == 2 and not _page_messages(out, "page_errors")


def test_a_resume_after_an_upload_park_with_the_box_still_empty_parks_again_and_writes_nothing(tmp_path):
    seeded = _parked("upload", parkedPage={"where": STEP1["url"], "key": "step1"})
    out = _run(tmp_path, [{"seed": [seeded]}, {"press": "run-resume"}], pages=(STEP1, REVIEW),
               frames={"page_uploads": [{"frameId": 0, "result": [BOX]}]}, replies={"attach_pdf": ATTACHED_ONE})
    record = _record(out["shots"][2])
    assert (record["status"], record["why"], record["step"]) == ("parked", "upload", 0)
    assert _attach_asks(out) == [] and not _page_messages(out, "page_advance") and out["fills"] == []


def test_a_resume_after_an_upload_park_with_the_box_filled_presses_on(tmp_path):
    seeded = _parked("upload", parkedPage={"where": STEP1["url"], "key": "step1"})
    out = _run(tmp_path, [{"seed": [seeded]}, {"press": "run-resume"}], pages=(STEP1, REVIEW),
               frames={"page_uploads": [{"frameId": 0, "result": [{**BOX, "occupied": True}]}]})
    assert _record(out["shots"][2])["step"] == 1 and len(out["fills"]) == 1


# ---------- G1: a ready tab taken back to a form step ----------

def test_a_ready_tab_taken_back_to_a_form_step_says_so_and_resume_fills_that_page(tmp_path):
    back = page("step", 4)
    final = page("review", 5)
    out = _run(tmp_path, [{"start": SEED}, {"page": 2, "update": {"tab": 7, "change": {"url": back["url"]}}}],
               pages=(STEP1, REVIEW, back, final))
    shot = out["shots"][-1]
    assert _record(shot)["status"] == "ready" and _record(shot)["movedOn"] is True
    body = _card(shot)["body"]
    assert "You moved on. Press Resume to fill this page." in _text(body)
    assert _buttons(body)["run-resume"] == "Resume"
    again = _run(tmp_path, [{"start": SEED}, {"page": 2, "update": {"tab": 7, "change": {"url": back["url"]}}},
                            {"press": "run-resume"}], pages=(STEP1, REVIEW, back, final))
    record = _record(again["shots"][-1])
    assert record["status"] == "ready" and not record.get("movedOn") and record["readyBy"] == "submit_button"


def test_a_ready_card_that_has_not_been_left_offers_no_resume_and_no_moved_on_line(tmp_path):
    out = _run(tmp_path, [{"start": SEED}], pages=(STEP1, REVIEW))
    body = _card(out["shots"][-1])["body"]
    assert "run-resume" not in _buttons(body) and "You moved on" not in _text(body)


def test_the_closed_stop_says_how_to_take_it_back_and_resume_drives_the_page(tmp_path):
    out = _run(tmp_path, [{"seed": [_seeded("stopped", why="closed", readyAt=None)]}])
    body = _card(out["shots"][1])["body"]
    assert "Not closed? Press Resume." in _text(body) and _buttons(body)["run-resume"] == "Resume"
    again = _run(tmp_path, [{"seed": [_seeded("stopped", why="closed")]}, {"press": "run-resume"}], pages=(STEP1, REVIEW))
    assert _record(again["shots"][-1])["status"] == "ready"


# ---------- G3: the fill log, and the resume line on Ready ----------

LOG_OFF = "Fill log is off. Turn it on in Options to let Maestro CS see what each field tried."
TRACE = {"host": "jobs.acme.test", "fields": []}


def test_a_run_that_ends_while_the_fill_log_is_off_says_so_on_the_card(tmp_path):
    out = _run(tmp_path, [{"start": SEED}], pages=(STEP1, REVIEW),
               reports=[{"fields": [verified("f1")], "trace": TRACE}, {"fields": [verified("f2")], "trace": TRACE}],
               replies={"fill_trace": _reply({"posted": 0, "why": "off"})})
    assert _record(out["shots"][-1])["status"] == "ready"
    assert LOG_OFF in _text(_card(out["shots"][-1])["body"])


def test_a_stopped_run_says_the_fill_log_is_off_too(tmp_path):
    record = _seeded("stopped", why="user", logOff=True)
    out = _run(tmp_path, [{"seed": [record]}])
    assert LOG_OFF in _text(_card(out["shots"][1])["body"])


def test_a_run_with_the_fill_log_on_says_nothing_about_it(tmp_path):
    out = _run(tmp_path, [{"start": SEED}], pages=(STEP1, REVIEW),
               reports=[{"fields": [verified("f1")], "trace": TRACE}, {"fields": [verified("f2")], "trace": TRACE}],
               replies={"fill_trace": _reply({"posted": 1})})
    assert "Fill log" not in _text(_card(out["shots"][-1])["body"])


@pytest.mark.parametrize("attach, said", [
    ({"outcome": "left", "reason": "no_box", "text": "no upload box took the file."}, "Couldn't attach the resume"),
    ({"outcome": "unconfirmed", "text": "Couldn't confirm the resume upload."}, "Couldn't confirm the resume upload."),
    ({"outcome": "left", "reason": "occupied"}, "A file was already attached"),
])
def test_ready_says_where_the_resume_stands_when_it_did_not_simply_attach(tmp_path, attach, said):
    out = _run(tmp_path, [{"seed": [_seeded("ready", readyAt=1, attach=attach)]}])
    assert said in _text(_card(out["shots"][1])["body"])


def test_ready_has_no_resume_line_for_a_clean_attach_or_none(tmp_path):
    for attach in ({"outcome": "attached"}, None):
        out = _run(tmp_path, [{"seed": [_seeded("ready", readyAt=1, attach=attach)]}])
        text = _text(_card(out["shots"][1])["body"])
        assert "Couldn't" not in text and "Resume attached" not in text and "already attached" not in text


def test_a_page_with_no_receipt_does_not_show_the_previous_pages_flags(tmp_path):
    """Flags are per page: the run's last page decides what "Check before you submit" lists."""
    flags = {"flags": [{"index": 0, "question": "Salary", "flags": [{"reason": "Not in your profile"}]}]}
    out = _run(tmp_path, [{"start": SEED}], pages=(STEP1, REVIEW),
               reports=[{"fields": [verified("f1")]}, {"fields": []}],
               inventoryByPage=[[_field("f1", "Ada", question="Name")], []],
               api={"POST /api/jobs/job-1/filled-answers": _reply(flags)})
    assert _record(out["shots"][-1])["status"] == "ready"
    assert _record(out["shots"][-1])["flags"] == []
    assert "Check before you submit" not in _body_text(out["shots"][-1])
    # The first page's receipt did have them: the reset is the fix, not an absence of flags.
    kept = _run(tmp_path, [{"start": SEED}], pages=(STEP1, REVIEW),
                reports=[{"fields": [verified("f1")]}, {"fields": [verified("f2")]}],
                inventoryByPage=[[_field("f1", "Ada", question="Name")]],
                api={"POST /api/jobs/job-1/filled-answers": _reply(flags)})
    assert "Salary" in _body_text(kept["shots"][-1])


def test_the_fill_log_line_also_says_when_the_log_last_recorded_a_run(tmp_path):
    reply = _reply({"posted": 0, "why": "off", "lastAt": "2026-10-13T12:00:00.000Z"})
    out = _run(tmp_path, [{"start": SEED}], pages=(STEP1, REVIEW),
               reports=[{"fields": [verified("f1")], "trace": TRACE}, {"fields": [verified("f2")], "trace": TRACE}],
               replies={"fill_trace": reply})
    text = _text(_card(out["shots"][-1])["body"])
    assert LOG_OFF in text and "Last trace: Oct 1" in text
    assert _record(out["shots"][-1])["logLast"] == "2026-10-13T12:00:00.000Z"


def test_a_log_that_never_recorded_a_run_has_no_last_trace_time(tmp_path):
    out = _run(tmp_path, [{"start": SEED}], pages=(STEP1, REVIEW),
               reports=[{"fields": [verified("f1")], "trace": TRACE}, {"fields": [verified("f2")], "trace": TRACE}],
               replies={"fill_trace": _reply({"posted": 0, "why": "off", "lastAt": None})})
    text = _text(_card(out["shots"][-1])["body"])
    assert LOG_OFF in text and "Last trace" not in text
