"""The queued run's driver (queued-run plan Task 17): `shared/queue-run.js`.

A pure module with every browser and panel effect injected, so node runs the whole state machine
against a FAKE SITE: a list of pages, one `advance` moves to the next, and the fakes record every
call in order. What is under test is the sequencing and the rules, not the page (that is
tests/browser/test_page_reader.py) and not the fill (tests/browser/test_fill_loop*.py).

THE RULES THESE PIN: Submit is never requested (the advance fake only ever sees ids a summary named
as the Next); Stop is honoured with nothing called after it; a failed sign-in is never retried; the
password never reaches the driver, the record or any result; the posting's Apply is pressed under
its narrow conditions only; `openUrl` is re-checked for scheme before any navigation.
"""

import re

import pytest

from tests.extension_harness import ROOT, js_code, run_node

QUEUE_RUN_JS = (ROOT / "extension" / "shared" / "queue-run.js").read_text(encoding="utf-8")
PAGE_KIND_JS = (ROOT / "extension" / "shared" / "page-kind.js").read_text(encoding="utf-8")
ATS_HOSTS_JS = (ROOT / "extension" / "shared" / "ats-hosts.js").read_text(encoding="utf-8")
SOURCE = ATS_HOSTS_JS + "\n" + PAGE_KIND_JS + "\n" + QUEUE_RUN_JS

_DRIVER = r"""
const ns = loadModules();

const base = { host: "jobs.acme.test", stepKey: "", applyId: null, buttons: [], passwordInputs: 0,
  confirmPassword: false, otpInput: false, captchaVisible: false, fillable: 0, hasApplyLink: false,
  confirmationText: false, closedText: false, boardNative: false };
const btn = (id, text, extra = {}) => ({ id, text, type: "button", marker: "", inForm: true,
  visible: true, enabled: true, ...extra });

// A page descriptor -> the summary the page reader would give.
const summaryOf = (p) => {
  const s = { ...base, host: p.host ?? base.host, stepKey: p.key ?? `${p.t}${p.n ?? ""}` };
  switch (p.t) {
    case "step": s.fillable = p.fillable ?? 2; s.buttons = [btn(`next-${p.n}`, "Next"), btn(`back-${p.n}`, "Back")]; break;
    case "review": s.fillable = 2; s.buttons = [btn("submit-1", p.submitText ?? "Submit application"), btn("back-r", "Back")]; break;
    case "captcha": s.fillable = 1; s.captchaVisible = true; break;
    case "create_account": s.passwordInputs = 2; s.confirmPassword = true; break;
    case "verify": s.fillable = 1; s.otpInput = true; break;
    case "sign_in": s.passwordInputs = 1; s.fillable = 2; s.buttons = [btn("signin-1", "Sign in")]; break;
    case "confirmation": s.confirmationText = true; break;
    case "closed": s.closedText = true; break;
    case "board_native": s.hasApplyLink = true; s.boardNative = true; break;
    case "posting": s.hasApplyLink = true; s.applyId = p.applyId === undefined ? "apply-1" : p.applyId;
      s.buttons = [btn("apply-1", "Apply now", { inForm: false })]; break;
    case "chooser": s.fillable = p.fillable ?? 0;
      s.buttons = ["Autofill with Resume", "Apply Manually", "Use My Last Application"].map((t, i) => btn(`ch-${i}`, t)); break;
    case "alert_posting": s.fillable = 1; s.hasApplyLink = true;
      s.buttons = [btn("alert-1", "Subscribe", { inForm: false }), btn("apply-1", "Apply now", { inForm: false })]; break;
    case "unseen_submit": s.fillable = 2; s.buttons = [btn(`n-${p.n ?? 0}`, "Next")]; s.submitSeen = true; break;
    case "submit_dialog": s.fillable = 2; s.buttons = [btn(`n-${p.n ?? 0}`, "Next")]; s.submitContext = true; break;
    case "unknown": break;
    default: throw new Error(`no page type ${p.t}`);
  }
  return s;
};

const pages = spec.pages;
let at = 0;
let moved = false;
const presses = {};
const calls = [];          // page-facing deps, in order: [name, ...args]
const pressed = [];        // every id advance saw
const events = [];         // "update:<status>" / "save", in order
let cancelFlag = spec.cancelAfter === 0;   // 0: Stop was already pressed when the run began
let callsWhenCancelled = cancelFlag ? 0 : null;
const current = () => pages[Math.min(at, pages.length - 1)];

const tick = (name, ...args) => {
  calls.push([name, ...args]);
  if (spec.cancelAfter != null && calls.length >= spec.cancelAfter && !cancelFlag) {
    cancelFlag = true;
    callsWhenCancelled = calls.length;
  }
};
const earlyReads = {};
let fillCalls = 0;
let clock = 1000;

const deps = {
  openTab: async (url, stop) => { tick("openTab", url, typeof stop); return 7; },
  sleep: async (ms) => { tick("sleep", ms); clock += ms; },
  classify: async (tabId) => {
    tick("classify", tabId);
    if (spec.classifyThrows) throw new Error("the tab is navigating");
    // A page not drawn yet: `early` reads (consumed once per page) or `always` (never settles) show
    // another descriptor first; {"t": "none"} is a tab no content script has answered from.
    const base = current();
    const early = (earlyReads[at] ??= [...(base.early ?? [])]);
    const p = base.always ?? (early.length ? early.shift() : base);
    if (p.t === "none") return [];
    if (p.frames) return p.frames.map((f) => ({ frameId: f.frameId, result: f.page ? { summary: summaryOf(f.page), top: Boolean(f.top) } : { summary: null } }));
    return [{ frameId: 0, result: { summary: summaryOf(p), top: true } }];
  },
  tabUrl: async () => {
    tick("tabUrl");
    const p = current();
    return `https://${p.urlHost ?? p.host ?? "jobs.acme.test"}${p.url ?? `/p/${at}`}#frag`;
  },
  advance: async (tabId, frameId, id, opts) => {
    tick("advance", frameId, id, opts ?? null);
    pressed.push(id);
    const p = current();
    if (p.refuse) return { clicked: false, why: "submit" };
    presses[at] = (presses[at] ?? 0) + 1;
    if (presses[at] > (p.stuck ?? 0)) { at += 1; moved = true; }
    return { clicked: true };
  },
  waitForChange: async (tabId, before, ms, stop) => {
    tick("waitForChange", ms, typeof stop);
    const c = moved;
    moved = false;
    return { changed: c, url: "ignored" };
  },
  fill: async (record, options) => {
    tick("fill", options ?? null);
    fillCalls += 1;
    // By default a fill writes one field, as a real page's does; `fills` says otherwise.
    const fields = (spec.fills ?? [])[fillCalls - 1] ?? [{ fid: "fdef", question: "Name", required: true, status: "verified" }];
    if (spec.cancelOnFill === fillCalls) { cancelFlag = true; callsWhenCancelled = calls.length; }
    if (spec.fillReturns === "nothing") return undefined;
    if (spec.fillThrows) throw new Error("secret-token-xyz exploded");
    return { fields, stopped: spec.fillStopped === fillCalls };
  },
  signIn: async (...args) => {
    tick("signIn", args.length, Object.keys(args[1] ?? {}), args[1]?.allowedHost);
    if (spec.signInMoves) { at += 1; moved = true; }
    return spec.signIn ?? { signedIn: true };
  },
  save: (...args) => { events.push(`save:${args.length}`); },
  onUpdate: (record) => { events.push(`update:${record.status}`); },
  now: () => (clock += 10),
  cancelled: () => cancelFlag,
};
if (spec.omitDep) delete deps[spec.omitDep];

const record = { jobId: "j1", proposalId: "p1", applicationId: "a1", base: "Base", company: "Acme",
  title: "Analyst", openUrl: "https://jobs.acme.test/apply", tabId: null, hosts: [], step: 0,
  fingerprint: null, seen: [], status: "waiting", why: null, open: [], startedAt: null, readyAt: null,
  yourMs: 0, flowOrigin: null, ...(spec.record ?? {}) };

main(async () => {
  let threw = null;
  try {
    await ns.queueRun.drive(record, deps, spec.options ?? {});
    // Later reads of the same record (a ready tab is watched by one drive per read): page indexes.
    for (const next of spec.then ?? []) {
      at = next;
      await ns.queueRun.drive(record, deps, spec.options ?? {});
    }
  } catch (err) {
    threw = `${err.name}: ${err.message}`;
  }
  emit({ record, calls, pressed, events, threw, fillCalls, callsWhenCancelled, at });
});
"""


def _drive(tmp_path, pages, **spec):
    return run_node(_DRIVER, {"pages": pages, **spec}, tmp_path, source=SOURCE)


def step(n, **extra):
    return {"t": "step", "n": n, **extra}


REVIEW = {"t": "review"}
# The saved password is typed only on a known ATS host, so the sign-in tests run on one.
WD = "acme.wd5.myworkdayjobs.com"
SIGN_IN = {"t": "sign_in", "host": WD}
ON_WD = {"openUrl": f"https://{WD}/apply"}


def names(out, name):
    return [c for c in out["calls"] if c[0] == name]


def statuses(out):
    return [e.split(":", 1)[1] for e in out["events"] if e.startswith("update:")]


def needs(fid, question="Question", required=True, status="needs_answer", invalid=False):
    return {"fid": fid, "question": question, "required": required, "status": status, "invalid": invalid}


# ---------- the happy path ----------

def test_two_steps_and_a_review_end_ready_after_two_advances_and_no_submit_is_ever_requested(tmp_path):
    out = _drive(tmp_path, [step(1), step(2), REVIEW])
    r = out["record"]
    assert (r["status"], r["why"], r["step"]) == ("ready", None, 2)
    assert r["readyAt"] is not None and r["startedAt"] is not None and r["tabId"] == 7
    # Only the ids a summary marked as the Next were ever pressed; never "submit-1" nor a Back.
    assert out["pressed"] == ["next-1", "next-2"]
    assert not [c for c in names(out, "advance") if c[3] is not None], "a plain Next carries no options"
    assert out["fillCalls"] == 3
    assert statuses(out)[0] == "opening" and statuses(out)[-1] == "ready"


def test_a_review_page_with_a_submit_button_ends_ready_without_calling_advance(tmp_path):
    out = _drive(tmp_path, [REVIEW])
    assert out["record"]["status"] == "ready"
    assert names(out, "advance") == []


@pytest.mark.parametrize("wording", ["Submit", "Submit application", "Apply", "Send my application", "Finish"])
def test_no_submit_wording_on_a_review_page_is_ever_pressed(tmp_path, wording):
    out = _drive(tmp_path, [step(1), {"t": "review", "submitText": wording}])
    assert out["record"]["status"] == "ready"
    assert out["pressed"] == ["next-1"]


def test_the_page_is_read_again_after_the_fill_so_a_next_enabled_by_the_fill_is_the_one_pressed(tmp_path):
    """The fake mints a distinct id per read; pressing the PRE-fill id would be a stale click."""
    out = _drive(tmp_path, [step(1), REVIEW])
    order = [c[0] for c in out["calls"]]
    assert order[:6] == ["openTab", "classify", "tabUrl", "fill", "classify", "tabUrl"]


# ---------- walls ----------

@pytest.mark.parametrize("kind", ["captcha", "create_account", "verify", "board_native"])
def test_a_wall_parks_with_its_own_kind_and_presses_nothing(tmp_path, kind):
    out = _drive(tmp_path, [{"t": kind}])
    assert (out["record"]["status"], out["record"]["why"]) == ("parked", kind)
    assert names(out, "advance") == [] and names(out, "fill") == []


def test_a_closed_posting_stops_the_run(tmp_path):
    out = _drive(tmp_path, [{"t": "closed"}])
    assert (out["record"]["status"], out["record"]["why"]) == ("stopped", "closed")


def test_a_page_it_cannot_read_parks(tmp_path):
    for pages in ([{"t": "unknown"}], [{"t": "step", "n": 1, "frames": [{"frameId": 0}]}]):
        out = _drive(tmp_path, pages)
        assert (out["record"]["status"], out["record"]["why"]) == ("parked", "unknown_page")
        assert names(out, "advance") == []


def test_a_captcha_after_a_step_parks_the_run_where_it_stands(tmp_path):
    out = _drive(tmp_path, [step(1), {"t": "captcha"}])
    assert (out["record"]["status"], out["record"]["why"], out["record"]["step"]) == ("parked", "captcha", 1)


# ---------- sign-in ----------

def test_sign_in_is_tried_once_and_a_page_that_still_asks_parks_it(tmp_path):
    out = _drive(tmp_path, [SIGN_IN], record=ON_WD)   # signIn "works" but the page never moves on
    assert (out["record"]["status"], out["record"]["why"]) == ("parked", "sign_in_failed")
    assert len(names(out, "signIn")) == 1


def test_sign_in_that_works_carries_on_with_the_form(tmp_path):
    out = _drive(tmp_path, [SIGN_IN, step(1), REVIEW], signInMoves=True, record=ON_WD)
    assert out["record"]["status"] == "ready" and len(names(out, "signIn")) == 1


def test_a_refused_sign_in_parks_at_once_without_waiting_for_the_page(tmp_path):
    out = _drive(tmp_path, [SIGN_IN], signIn={"signedIn": False, "why": "host"}, record=ON_WD)
    assert (out["record"]["status"], out["record"]["why"]) == ("parked", "sign_in_failed")
    assert names(out, "waitForChange") == []


@pytest.mark.parametrize("host", ["boards.greenhouse.io", "acme.wd5.myworkdayjobs.com", "jobs.lever.co", "acme.icims.com"])
def test_a_known_ats_host_gets_the_saved_login(tmp_path, host):
    out = _drive(tmp_path, [{"t": "sign_in", "host": host}], signInMoves=True,
                 record={"openUrl": f"https://{host}/apply"})
    assert len(names(out, "signIn")) == 1 and out["record"]["signedIn"] is True


@pytest.mark.parametrize("host", ["careers.acme.test", "greenhouse.io.attacker.test", "login.sso-example.test"])
def test_an_unknown_host_is_the_users_to_sign_in_to_and_nothing_is_fetched(tmp_path, host):
    out = _drive(tmp_path, [{"t": "sign_in", "host": host}], signInMoves=True,
                 record={"openUrl": f"https://{host}/apply"})
    assert (out["record"]["status"], out["record"]["why"]) == ("parked", "sign_in_yourself")
    assert names(out, "signIn") == [] and names(out, "waitForChange") == []
    # Not marked as tried: the user signs in, presses Resume, and a page that no longer asks goes on.
    assert out["record"].get("signedIn") is not True


def test_after_the_user_signs_in_by_hand_a_resume_carries_on(tmp_path):
    parked = {"tabId": 7, "status": "parked", "why": "sign_in_yourself", "hosts": ["careers.acme.test"]}
    out = _drive(tmp_path, [step(1), REVIEW], record=parked)
    assert out["record"]["status"] == "ready" and names(out, "signIn") == []


def test_a_resumed_record_that_already_tried_the_login_never_tries_it_again(tmp_path):
    out = _drive(tmp_path, [SIGN_IN], record={"signedIn": True, "tabId": 7})
    assert names(out, "signIn") == []
    assert (out["record"]["status"], out["record"]["why"]) == ("parked", "sign_in_failed")


def test_the_driver_hands_the_sign_in_a_record_and_a_host_and_nothing_secret(tmp_path):
    out = _drive(tmp_path, [SIGN_IN], signInMoves=True, record=ON_WD)
    (call,) = names(out, "signIn")
    assert call[1:] == [2, ["allowedHost", "stop"], WD]
    assert "password" not in str(out["record"]).lower()


def test_the_sign_in_host_is_the_one_the_run_navigated_to_not_the_pages_own_claim(tmp_path):
    """The apply link led to the careers host; the page then CLAIMS another host in its summary."""
    liar = {"t": "sign_in", "host": "evil.example.test", "urlHost": WD}
    out = _drive(tmp_path, [liar], signInMoves=True, record=ON_WD)
    (call,) = names(out, "signIn")
    assert call[3] == WD
    assert out["record"]["hosts"] == [WD]


def test_a_host_reached_by_the_runs_own_navigation_is_remembered_in_order(tmp_path):
    other = "acme.myworkdayjobs.com"
    pages = [step(1, urlHost=WD), {"t": "sign_in", "urlHost": other}]
    out = _drive(tmp_path, pages, signInMoves=True, record=ON_WD)
    assert out["record"]["hosts"] == [WD, other]
    assert names(out, "signIn")[0][3] == other


def test_a_page_that_redirects_on_its_own_does_not_become_a_trusted_host(tmp_path):
    """Hosts are noted only after something the run did (open, a press, a sign-in); a fill is not one."""
    pages = [{"t": "step", "n": 1, "urlHost": "jobs.acme.test"}]
    out = _drive(tmp_path, pages)
    assert out["record"]["hosts"] == ["jobs.acme.test"]


# ---------- the fill and its open questions ----------

def test_an_open_required_field_parks_the_page_with_the_list(tmp_path):
    fills = [[needs("f1", "Work authorization"), needs("f2", "Cell", status="cannot_operate"),
              needs("f3", "Nickname", required=False), needs("f4", "Done", status="verified")]]
    out = _drive(tmp_path, [step(1), REVIEW], fills=fills)
    r = out["record"]
    assert (r["status"], r["why"]) == ("parked", "open_questions")
    assert r["open"] == [{"fid": "f1", "question": "Work authorization", "required": True},
                         {"fid": "f2", "question": "Cell", "required": True}]
    assert names(out, "advance") == []


def test_a_field_the_page_flags_invalid_parks_by_name_though_the_reader_missed_its_star(tmp_path):
    """A required field the reader did not see as required (no star, no aria-required) is the page's
    to complain about: after a Next that did nothing it shows invalid. Parking on it names the field;
    without this the run would refill and then stop as `no_change`, saying nothing about which field."""
    fills = [[needs("f1", "Pronouns", required=False, invalid=True),
              needs("f2", "Nickname", required=False),
              needs("f3", "Cell", required=False, status="cannot_operate", invalid=True)]]
    out = _drive(tmp_path, [step(1), REVIEW], fills=fills)
    r = out["record"]
    assert (r["status"], r["why"]) == ("parked", "open_questions")
    assert r["open"] == [{"fid": "f1", "question": "Pronouns", "required": False}]


def test_an_optional_open_field_does_not_park(tmp_path):
    out = _drive(tmp_path, [REVIEW], fills=[[needs("f1", required=False), needs("f2", status="verified")]])
    assert out["record"]["status"] == "ready"


def test_a_required_field_that_shows_a_value_the_engine_could_not_prove_does_not_park(tmp_path):
    out = _drive(tmp_path, [step(1), REVIEW], fills=[[needs("f1", status="unconfirmed")]])
    assert out["record"]["status"] == "ready" and out["pressed"] == ["next-1"]


def test_an_unconfirmed_field_on_a_page_that_does_not_move_is_refilled_once_then_parks_no_change(tmp_path):
    out = _drive(tmp_path, [step(1, stuck=9)], fills=[[needs("f1", status="unconfirmed")]] * 3)
    r = out["record"]
    assert (r["status"], r["why"]) == ("parked", "no_change")
    assert out["fillCalls"] == 2 and len(out["pressed"]) == 2


def test_a_refill_that_finds_the_page_open_questions_parks_with_them_not_no_change(tmp_path):
    fills = [[], [needs("f9", "Which office?")]]
    out = _drive(tmp_path, [step(1, stuck=9)], fills=fills)
    r = out["record"]
    assert (r["status"], r["why"]) == ("parked", "open_questions")
    assert r["open"][0]["fid"] == "f9" and len(out["pressed"]) == 1


def test_a_page_that_moves_on_the_second_press_is_a_step_not_a_failure(tmp_path):
    out = _drive(tmp_path, [step(1, stuck=1), REVIEW])
    assert out["record"]["status"] == "ready" and out["record"]["step"] == 1
    assert out["fillCalls"] == 3   # page 1, its refill, the review


def test_a_resume_reads_the_page_again_and_keeps_the_open_tab(tmp_path):
    parked = {"tabId": 7, "status": "parked", "why": "open_questions", "step": 1, "hosts": ["jobs.acme.test"],
              "open": [{"fid": "f1", "question": "Q", "required": True}], "filled": True}
    out = _drive(tmp_path, [REVIEW], record=parked)
    assert names(out, "openTab") == []
    assert (out["record"]["status"], out["record"]["why"], out["record"]["open"]) == ("ready", None, [])


def test_the_fill_limits_layer_over_the_runs_defaults_and_a_run_defaults_to_trying_harder(tmp_path):
    out = _drive(tmp_path, [REVIEW], options={"fillLimits": {"FIELD_MS": 5000}})
    assert names(out, "fill") == [["fill", {"limits": {"FIELD_MS": 5000, "MAX_STEPS": 12, "RUN_MS": 600000}}]]
    plain = _drive(tmp_path, [REVIEW])
    assert names(plain, "fill") == [["fill", {"limits": {"FIELD_MS": 60000, "MAX_STEPS": 12, "RUN_MS": 600000}}]]


# ---------- loops and limits ----------

def test_the_same_page_twice_parks_as_a_loop(tmp_path):
    again = {"url": "/same", "key": "same"}
    out = _drive(tmp_path, [step(1, **again), step(2), step(1, **again), REVIEW])
    assert (out["record"]["status"], out["record"]["why"]) == ("parked", "loop")
    assert out["pressed"] == ["next-1", "next-2"]


def test_a_press_that_never_moves_the_page_parks_no_change_after_one_refill(tmp_path):
    out = _drive(tmp_path, [step(1, stuck=99)])
    assert (out["record"]["status"], out["record"]["why"]) == ("parked", "no_change")
    assert out["fillCalls"] == 2 and out["pressed"] == ["next-1", "next-1"]


def test_a_refused_press_is_a_page_that_did_not_change(tmp_path):
    out = _drive(tmp_path, [step(1, refuse=True)])
    assert (out["record"]["status"], out["record"]["why"]) == ("parked", "no_change")
    assert names(out, "waitForChange") == []


def test_fifteen_steps_then_the_sixteenth_page_parks_as_the_step_limit(tmp_path):
    out = _drive(tmp_path, [step(n) for n in range(1, 18)])
    r = out["record"]
    assert (r["status"], r["why"], r["step"]) == ("parked", "step_limit", 15)
    assert len(out["pressed"]) == 15


def test_fifteen_steps_and_a_review_still_end_ready(tmp_path):
    out = _drive(tmp_path, [step(n) for n in range(1, 16)] + [REVIEW])
    assert (out["record"]["status"], out["record"]["step"]) == ("ready", 15)


# ---------- the posting's Apply ----------

def test_a_posting_is_followed_through_its_apply_once_with_the_apply_flag(tmp_path):
    out = _drive(tmp_path, [{"t": "posting"}, step(1), REVIEW])
    assert out["record"]["status"] == "ready" and out["record"]["step"] == 1
    first, second = names(out, "advance")
    assert first[1:] == [0, "apply-1", {"apply": True}] and second[3] is None


def test_a_posting_after_the_first_apply_is_not_pressed_a_second_time(tmp_path):
    out = _drive(tmp_path, [{"t": "posting", "url": "/a"}, {"t": "posting", "url": "/b", "key": "b"}])
    assert (out["record"]["status"], out["record"]["why"]) == ("parked", "posting")
    assert len(names(out, "advance")) == 1


def test_a_posting_on_another_host_than_the_apply_link_is_not_pressed(tmp_path):
    out = _drive(tmp_path, [{"t": "posting", "host": "other.example.test", "urlHost": "other.example.test"}])
    assert (out["record"]["status"], out["record"]["why"]) == ("parked", "posting")
    assert names(out, "advance") == []


def test_a_posting_whose_page_host_claims_otherwise_is_not_pressed(tmp_path):
    out = _drive(tmp_path, [{"t": "posting", "host": "other.example.test", "urlHost": "jobs.acme.test"}])
    assert out["record"]["why"] == "posting" and names(out, "advance") == []


def test_www_does_not_make_a_different_host(tmp_path):
    out = _drive(tmp_path, [{"t": "posting", "host": "www.jobs.acme.test", "urlHost": "www.jobs.acme.test"}, step(1), REVIEW])
    assert out["record"]["status"] == "ready"


def test_a_posting_without_an_apply_the_page_named_is_not_pressed(tmp_path):
    out = _drive(tmp_path, [{"t": "posting", "applyId": None}])
    assert out["record"]["why"] == "posting" and names(out, "advance") == []


@pytest.mark.parametrize("record", [{"filled": True, "wrote": True}, {"step": 1}])
def test_a_field_less_page_with_an_apply_button_after_a_fill_or_a_step_is_the_review_page(tmp_path, record):
    """Never pressed: with the record's `filled` (or a step behind it) the Apply-worded button is a
    Submit, and the run stops there as Ready to submit."""
    out = _drive(tmp_path, [{"t": "posting"}], record=record)
    assert out["record"]["status"] == "ready"
    assert names(out, "advance") == []


def test_a_fill_that_wrote_nothing_is_no_evidence_the_page_was_the_application(tmp_path):
    out = _drive(tmp_path, [{"t": "posting"}], record={"filled": True})
    assert (out["record"]["status"], out["record"]["why"]) == ("parked", "unknown_page")
    assert names(out, "advance") == [] and names(out, "fill") == []


def test_a_review_like_page_reached_after_a_real_fill_is_never_pressed_either(tmp_path):
    out = _drive(tmp_path, [step(1), {"t": "posting", "key": "last"}])
    assert out["record"]["status"] == "ready"
    assert [c[3] for c in names(out, "advance")] == [None]   # only the step's Next, never the apply flag


def test_a_refused_apply_press_parks_the_posting(tmp_path):
    out = _drive(tmp_path, [{"t": "posting", "refuse": True}])
    assert (out["record"]["status"], out["record"]["why"]) == ("parked", "posting")


def test_an_apply_that_leaves_the_page_unchanged_parks_no_change(tmp_path):
    out = _drive(tmp_path, [{"t": "posting", "stuck": 9}])
    assert (out["record"]["status"], out["record"]["why"]) == ("parked", "no_change")
    assert len(names(out, "advance")) == 1


def test_apply_is_never_pressed_after_a_sign_in_even_on_a_page_that_looks_like_a_posting(tmp_path):
    """A site that restores a saved draft after sign-in lands on its review page: no fillable
    control, and one "Apply" that is really a Submit."""
    out = _drive(tmp_path, [SIGN_IN, {"t": "posting", "host": WD}], signInMoves=True, record=ON_WD)
    assert (out["record"]["status"], out["record"]["why"]) == ("parked", "posting")
    assert names(out, "advance") == []


@pytest.mark.parametrize("record", [
    {"tabId": 7, "status": "parked", "why": "captcha", "hosts": ["jobs.acme.test"]},
    {"tabId": 7, "status": "parked", "why": "unknown_page", "hosts": ["jobs.acme.test"]},
    {"tabId": 7, "status": "stopped", "why": "user", "hosts": ["jobs.acme.test"]},
])
def test_apply_is_never_pressed_on_a_resume(tmp_path, record):
    """The user may have walked the tab to a field-less review page by hand since the park."""
    out = _drive(tmp_path, [{"t": "posting"}], record=record)
    assert (out["record"]["status"], out["record"]["why"]) == ("parked", "posting")
    assert names(out, "advance") == []


def test_apply_is_pressed_on_the_first_read_of_a_tab_the_call_opened_and_not_on_the_second(tmp_path):
    out = _drive(tmp_path, [{"t": "posting", "url": "/a"}, {"t": "posting", "url": "/b", "key": "b"}])
    assert [c[3] for c in names(out, "advance")] == [{"apply": True}]


def test_filled_is_set_before_the_fill_so_a_fill_that_throws_still_counts(tmp_path):
    out = _drive(tmp_path, [step(1)], fillThrows=True)
    assert out["record"]["filled"] is True and out["record"]["why"] == "error"


def test_a_resume_after_no_change_can_move_when_the_page_now_does(tmp_path):
    """The fingerprint is remembered only once a press MOVED the page, so a Resume on the page
    that would not move is not mistaken for coming back to it."""
    first = _drive(tmp_path, [step(1, stuck=99, url="/s", key="k")])
    assert (first["record"]["status"], first["record"]["why"]) == ("parked", "no_change")
    assert first["record"]["seen"] == []
    second = _drive(tmp_path, [step(1, url="/s", key="k"), REVIEW], record=first["record"])
    assert second["record"]["status"] == "ready" and second["record"]["step"] == 1
    assert len(second["record"]["seen"]) == 1


def test_a_page_seen_after_it_moved_is_still_a_loop_when_it_comes_back(tmp_path):
    again = {"url": "/same", "key": "same"}
    out = _drive(tmp_path, [step(1, **again), step(2), step(1, **again), REVIEW])
    assert out["record"]["why"] == "loop" and len(out["record"]["seen"]) == 2


# ---------- "ready" needs evidence it was the application ----------

def test_a_start_chooser_with_nothing_to_fill_is_not_filled_and_not_ready(tmp_path):
    """Workday's "Autofill with Resume / Apply Manually / Use My Last Application" page."""
    out = _drive(tmp_path, [{"t": "chooser"}])
    assert (out["record"]["status"], out["record"]["why"]) == ("parked", "unknown_page")
    assert out["record"]["readyAt"] is None and names(out, "fill") == [] and names(out, "advance") == []


@pytest.mark.parametrize("page", [{"t": "chooser", "fillable": 1}, {"t": "alert_posting"}])
def test_a_page_with_a_stray_control_whose_fill_wrote_nothing_is_not_ready(tmp_path, page):
    """A chooser with one stray radio, or a posting with a job-alert box and a location select:
    they classify as review, and the fill writes none of the profile into them."""
    out = _drive(tmp_path, [page], fills=[[needs("loc", "Location", required=False)]])
    assert (out["record"]["status"], out["record"]["why"]) == ("parked", "unknown_page")
    assert out["record"]["readyAt"] is None and names(out, "advance") == []
    assert out["fillCalls"] == 1 and not out["record"].get("wrote")


def test_a_one_page_application_is_ready_when_its_fill_wrote_a_field(tmp_path):
    out = _drive(tmp_path, [REVIEW], fills=[[needs("f1", status="already")]])
    assert out["record"]["status"] == "ready" and out["record"]["wrote"] is True


@pytest.mark.parametrize("status", ["unconfirmed", "yours", "blocked", "needs_answer", "cannot_operate"])
def test_a_field_the_fill_did_not_write_or_confirm_is_no_evidence(tmp_path, status):
    out = _drive(tmp_path, [REVIEW], fills=[[needs("f1", required=False, status=status)]])
    assert out["record"]["why"] == "unknown_page"


def test_a_review_page_behind_a_step_is_ready_even_when_its_fill_wrote_nothing(tmp_path):
    out = _drive(tmp_path, [step(1), REVIEW], fills=[[], []])
    assert out["record"]["status"] == "ready"


def test_a_resume_remembers_that_a_field_was_written_before_the_park(tmp_path):
    parked = {"tabId": 7, "status": "parked", "why": "open_questions", "wrote": True, "filled": True}
    out = _drive(tmp_path, [REVIEW], record=parked, fills=[[]])
    assert out["record"]["status"] == "ready"


# ---------- when unsure whether a button is Next or Submit, stop ----------

def test_a_fieldless_page_with_a_lone_next_after_the_first_step_is_treated_as_review_and_not_pressed(tmp_path):
    out = _drive(tmp_path, [step(1), step(2, fillable=0), step(3)])
    assert out["record"]["status"] == "ready" and out["record"]["step"] == 1
    assert out["pressed"] == ["next-1"]


def test_an_intro_page_at_the_first_step_still_advances(tmp_path):
    out = _drive(tmp_path, [step(1, fillable=0), REVIEW])
    assert out["record"]["status"] == "ready" and out["pressed"] == ["next-1"]


# ---------- settling: a page just arrived at is often not drawn yet ----------

NONE = {"t": "none"}


def test_a_tab_no_content_script_has_answered_from_yet_is_waited_for_not_parked(tmp_path):
    out = _drive(tmp_path, [{**REVIEW, "early": [NONE, NONE, NONE]}])
    assert out["record"]["status"] == "ready" and out["fillCalls"] == 1
    assert len(names(out, "sleep")) == 3 and names(out, "sleep")[0][1] == 500


def test_a_skeleton_that_classes_unknown_is_waited_for_until_the_form_appears(tmp_path):
    out = _drive(tmp_path, [{**step(1), "early": [{"t": "unknown"}, {"t": "unknown", "key": "b"}]}, REVIEW])
    assert out["record"]["status"] == "ready" and out["pressed"] == ["next-1"]


def test_the_page_after_a_press_is_settled_too(tmp_path):
    out = _drive(tmp_path, [step(1), {**step(2), "early": [NONE, {"t": "unknown"}]}, REVIEW])
    assert out["record"]["status"] == "ready" and out["pressed"] == ["next-1", "next-2"]


def test_a_half_drawn_step_is_not_mistaken_for_a_final_page_and_the_full_step_advances(tmp_path):
    """One Next and nothing fillable looks exactly like an "are you sure" page: it is re-read."""
    half = step(2, fillable=0)
    out = _drive(tmp_path, [step(1), {**step(2), "early": [half]}, REVIEW])
    assert out["record"]["status"] == "ready" and out["pressed"] == ["next-1", "next-2"]
    assert out["record"]["step"] == 2


def test_a_lone_next_page_that_stays_that_way_is_the_final_page_after_four_agreeing_reads(tmp_path):
    out = _drive(tmp_path, [step(1), step(2, fillable=0)])
    assert out["record"]["status"] == "ready" and out["pressed"] == ["next-1"]
    assert len(names(out, "sleep")) == 3, "four identical reads in a row (about 2 s) before it is judged final"


def test_a_page_that_never_draws_parks_after_the_cap(tmp_path):
    out = _drive(tmp_path, [{**REVIEW, "always": NONE}])
    assert (out["record"]["status"], out["record"]["why"]) == ("parked", "unknown_page")
    slept = sum(c[1] for c in names(out, "sleep"))
    assert 15000 <= slept <= 15500 and names(out, "fill") == []


def test_a_skeleton_that_repeats_for_several_reads_is_waited_out_not_parked(tmp_path):
    """A Workday spinner can hold for seconds: a matching pair 500 ms apart proves nothing."""
    out = _drive(tmp_path, [{**step(1), "early": [{"t": "unknown"}] * 3 + [NONE, NONE]}, REVIEW])
    assert out["record"]["status"] == "ready" and out["pressed"] == ["next-1"]
    assert len(names(out, "sleep")) == 5


def test_an_unknown_page_that_never_changes_is_judged_only_when_the_cap_runs_out(tmp_path):
    out = _drive(tmp_path, [{"t": "unknown"}])
    assert (out["record"]["status"], out["record"]["why"]) == ("parked", "unknown_page")
    assert 15000 <= sum(c[1] for c in names(out, "sleep")) <= 15500


def test_a_step_whose_fields_arrive_after_a_second_is_not_mistaken_for_a_final_page(tmp_path):
    """The same field-less lone-Next read twice (and three times) is still a step half drawn."""
    half = step(2, fillable=0)
    out = _drive(tmp_path, [step(1), {**step(2), "early": [half, half, half]}, REVIEW])
    assert out["record"]["status"] == "ready" and out["pressed"] == ["next-1", "next-2"]


def test_a_resume_does_not_wait_for_a_page_the_run_did_not_just_arrive_at(tmp_path):
    parked = {"tabId": 7, "status": "parked", "why": "open_questions", "hosts": ["jobs.acme.test"]}
    out = _drive(tmp_path, [{"t": "unknown"}], record=parked)
    assert out["record"]["why"] == "unknown_page" and names(out, "sleep") == []


def test_a_stop_while_waiting_for_a_page_ends_the_run_with_no_further_call(tmp_path):
    out = _drive(tmp_path, [{**REVIEW, "always": NONE}], cancelAfter=5)
    assert (out["record"]["status"], out["record"]["why"]) == ("stopped", "user")
    assert len(out["calls"]) == out["callsWhenCancelled"]


# ---------- a ready tab is only watched ----------

def test_re_entering_a_ready_record_whose_page_cannot_be_read_yet_leaves_it_ready(tmp_path):
    """The confirmation watch re-enters on tabs.onUpdated, before document_idle."""
    ready = {"tabId": 7, "status": "ready", "readyAt": 5, "filled": True}
    out = _drive(tmp_path, [NONE], record=ready)
    assert (out["record"]["status"], out["record"]["why"], out["record"]["readyAt"]) == ("ready", None, 5)
    assert out["events"] == [] and names(out, "sleep") == []


# ---------- a Resume must find the tab where the run left it ----------

def test_a_resume_on_a_host_the_run_never_navigated_to_parks_moved_away_and_fills_nothing(tmp_path):
    parked = {"tabId": 7, "status": "parked", "why": "open_questions", "hosts": ["jobs.acme.test"], "filled": True}
    out = _drive(tmp_path, [step(1, urlHost="mail.example.test")], record=parked)
    assert (out["record"]["status"], out["record"]["why"]) == ("parked", "moved_away")
    assert names(out, "fill") == [] and names(out, "advance") == []


@pytest.mark.parametrize("why", ["sign_in_yourself", "verify", "posting", "unknown_page"])
def test_a_park_that_asked_the_user_to_navigate_may_resume_on_a_new_host(tmp_path, why):
    parked = {"tabId": 7, "status": "parked", "why": why, "hosts": ["careers.acme.test"]}
    out = _drive(tmp_path, [REVIEW], record=parked)
    assert out["record"]["status"] == "ready"


@pytest.mark.parametrize("why", ["posting", "unknown_page"])
def test_a_resume_from_apply_yourself_on_the_ats_fills_the_form_and_remembers_its_host(tmp_path, why):
    """The card says "open the application form in the tab": that is usually another host (the ATS)."""
    parked = {"tabId": 7, "status": "parked", "why": why, "hosts": ["careers.acme.test"]}
    out = _drive(tmp_path, [step(1, urlHost=WD), {**REVIEW, "urlHost": WD}], record=parked)
    r = out["record"]
    assert r["status"] == "ready" and out["fillCalls"] == 2 and out["pressed"] == ["next-1"]
    assert r["hosts"] == ["careers.acme.test", WD]
    # A confirmation on the ATS host is then the run's own, and one on a host it never saw is not.
    confirmed = _drive(tmp_path, [{"t": "confirmation", "urlHost": WD}], record={**r, "status": "ready"})
    assert confirmed["record"]["status"] == "confirming"


def test_a_resume_that_stays_on_the_same_host_does_not_repeat_it_in_the_host_list(tmp_path):
    parked = {"tabId": 7, "status": "parked", "why": "posting", "hosts": ["jobs.acme.test"]}
    out = _drive(tmp_path, [REVIEW], record=parked)
    assert out["record"]["hosts"] == ["jobs.acme.test"]


def test_a_resume_after_a_different_park_still_parks_moved_away_on_a_new_host(tmp_path):
    parked = {"tabId": 7, "status": "parked", "why": "no_change", "hosts": ["jobs.acme.test"], "filled": True}
    out = _drive(tmp_path, [step(1, urlHost=WD)], record=parked)
    assert out["record"]["why"] == "moved_away" and out["record"]["hosts"] == ["jobs.acme.test"]


def test_a_resume_on_a_host_the_run_did_reach_goes_on(tmp_path):
    parked = {"tabId": 7, "status": "parked", "why": "open_questions", "hosts": ["id.acme.test", "jobs.acme.test"]}
    out = _drive(tmp_path, [REVIEW], record=parked)
    assert out["record"]["status"] == "ready"


# ---------- the confirmation, and a finished run ----------

def test_a_confirmation_page_before_ready_parks_as_already_applied_never_ready(tmp_path):
    """A "thank you" page the run did not reach by its own Submit is an application someone else
    sent (a draft this session already submitted); calling it ready would invite a second one."""
    out = _drive(tmp_path, [{"t": "confirmation"}])
    assert (out["record"]["status"], out["record"]["why"]) == ("parked", "already_applied")
    assert out["record"]["readyAt"] is None and names(out, "advance") == [] and names(out, "fill") == []


def test_a_ready_tab_that_shows_the_confirmation_becomes_confirming(tmp_path):
    ready = {"tabId": 7, "status": "ready", "readyAt": 5, "filled": True, "hosts": ["jobs.acme.test"]}
    out = _drive(tmp_path, [{"t": "confirmation"}], record=ready)
    assert out["record"]["status"] == "confirming" and out["record"]["readyAt"] == 5
    assert names(out, "fill") == [] and names(out, "advance") == []


def test_a_ready_tab_still_on_its_review_page_is_left_alone(tmp_path):
    ready = {"tabId": 7, "status": "ready", "readyAt": 5, "filled": True, "hosts": ["jobs.acme.test"]}
    out = _drive(tmp_path, [REVIEW], record=ready)
    assert (out["record"]["status"], out["record"]["readyAt"]) == ("ready", 5)
    assert names(out, "fill") == [] and names(out, "advance") == [] and out["events"] == []


READY = {"tabId": 7, "status": "ready", "readyAt": 5, "filled": True, "hosts": ["jobs.acme.test"]}


def test_a_confirmation_on_a_host_the_run_never_reached_is_not_auto_marked(tmp_path):
    """Another employer's thank-you, or a candidate portal's "Application received", opened in the same
    tab is not this job's Submit."""
    elsewhere = {"t": "confirmation", "host": "careers.globex.test"}
    out = _drive(tmp_path, [elsewhere], record=READY)
    assert (out["record"]["status"], out["record"]["noAutoMark"]) == ("ready", True)


def test_a_confirmation_on_the_runs_own_host_straight_after_the_review_is_auto_marked(tmp_path):
    out = _drive(tmp_path, [{"t": "confirmation"}], record=READY)
    assert (out["record"]["status"], out["record"].get("noAutoMark")) == ("confirming", None)


def test_a_confirmation_after_the_tab_left_the_review_page_is_not_auto_marked(tmp_path):
    """Review, then some other page (the user decided against it and browsed on), then a page that reads
    as a confirmation, even on the run's own host: only the manual Mark applied is left."""
    pages = [REVIEW, {"t": "closed"}, {"t": "confirmation"}]
    out = _drive(tmp_path, pages, record=READY, **{"then": [1, 2]})
    assert (out["record"]["status"], out["record"]["noAutoMark"]) == ("ready", True)


def test_a_ready_tab_that_moves_to_a_page_that_is_neither_review_nor_confirmation_loses_the_auto_mark(tmp_path):
    out = _drive(tmp_path, [{"t": "closed"}], record=READY)
    assert (out["record"]["status"], out["record"]["noAutoMark"]) == ("ready", True)


def test_a_ready_tab_back_on_the_review_page_keeps_the_auto_mark(tmp_path):
    """A Submit that came back with errors is still the review page, and a confirmation after it counts."""
    out = _drive(tmp_path, [REVIEW, {"t": "confirmation"}], record=READY, **{"then": [1]})
    assert out["record"]["status"] == "confirming"


def test_a_read_that_fails_on_a_ready_tab_leaves_it_ready_and_changes_nothing(tmp_path):
    """The tab is mid-navigation in the middle of the user's own Submit: not a failed run."""
    out = _drive(tmp_path, [REVIEW], record=READY, classifyThrows=True)
    assert (out["record"]["status"], out["record"]["why"]) == ("ready", None)
    assert out["events"] == []


def test_a_read_that_fails_before_ready_is_still_an_error(tmp_path):
    out = _drive(tmp_path, [REVIEW], classifyThrows=True)
    assert (out["record"]["status"], out["record"]["why"]) == ("stopped", "error")


# ---------- frames ----------

def test_the_top_frame_is_the_one_judged_and_pressed(tmp_path):
    frames = [{"frameId": 5, "page": step(1, fillable=9, key="sub")},
              {"frameId": 0, "top": True, "page": step(2, fillable=1)}]
    out = _drive(tmp_path, [{"t": "step", "n": 0, "frames": frames}])
    assert names(out, "advance")[0][1:3] == [0, "next-2"]


def test_without_a_top_summary_the_frame_with_the_most_fillable_controls_wins_and_null_ones_are_skipped(tmp_path):
    frames = [{"frameId": 1}, {"frameId": 2, "page": step(1, fillable=1)}, {"frameId": 3, "page": step(2, fillable=4)}]
    out = _drive(tmp_path, [{"t": "step", "n": 0, "frames": frames}])
    assert names(out, "advance")[0][1:3] == [3, "next-2"]


def test_a_top_frame_that_is_a_bare_posting_or_unreadable_yields_to_the_subframe_holding_the_form(tmp_path):
    """A careers page embedding the ATS form in an iframe: the page around it has an Apply and no fields."""
    for top in ({"t": "posting"}, {"t": "unknown"}):
        frames = [{"frameId": 0, "top": True, "page": top}, {"frameId": 4, "page": step(1, fillable=3)}]
        out = _drive(tmp_path, [{"t": "step", "n": 0, "frames": frames}])
        assert names(out, "advance")[0][1:3] == [4, "next-1"], top


def test_a_top_frame_that_says_something_definite_is_not_overruled_by_a_fuller_subframe(tmp_path):
    frames = [{"frameId": 0, "top": True, "page": {"t": "captcha"}}, {"frameId": 4, "page": step(1, fillable=9)}]
    out = _drive(tmp_path, [{"t": "step", "n": 0, "frames": frames}])
    assert (out["record"]["why"], names(out, "advance")) == ("captcha", [])


def test_a_lone_posting_top_frame_is_still_judged_so_its_apply_can_be_followed(tmp_path):
    frames = [{"frameId": 0, "top": True, "page": {"t": "posting"}}, {"frameId": 4}]
    out = _drive(tmp_path, [{"t": "step", "n": 0, "frames": frames}, REVIEW])
    assert names(out, "advance")[0][1:] == [0, "apply-1", {"apply": True}]


def test_a_carousel_next_at_the_top_does_not_outvote_the_form_in_an_embedded_frame(tmp_path):
    frames = [{"frameId": 0, "top": True, "page": step(0, fillable=0)}, {"frameId": 4, "page": step(1, fillable=3)}]
    out = _drive(tmp_path, [{"t": "step", "n": 0, "frames": frames}, REVIEW])
    assert names(out, "advance")[0][1:3] == [4, "next-1"]


def test_a_visible_submit_in_a_subframe_makes_the_tab_the_review_page(tmp_path):
    for top in (step(0, fillable=0), step(0, fillable=2), {"t": "posting"}):
        frames = [{"frameId": 0, "top": True, "page": top}, {"frameId": 4, "page": REVIEW}]
        out = _drive(tmp_path, [{"t": "step", "n": 0, "frames": frames}])
        assert out["record"]["status"] == "ready" and names(out, "advance") == [], top


@pytest.mark.parametrize("sub", [{"t": "unseen_submit"}, {"t": "submit_dialog"}])
def test_a_subframe_whose_only_submit_signal_is_unseen_or_a_dialog_makes_the_tab_review(tmp_path, sub):
    """A div role=button Submit (submitSeen) or a "submit your application?" dialog (submitContext)
    is not in the button list, yet it is enough to stop: the top frame's Next is not pressed."""
    for top in (step(0, fillable=0), step(0, fillable=2)):
        frames = [{"frameId": 0, "top": True, "page": top}, {"frameId": 4, "page": sub}]
        out = _drive(tmp_path, [{"t": "step", "n": 0, "frames": frames}])
        assert out["record"]["status"] == "ready" and names(out, "advance") == [], top


def test_a_wall_in_any_frame_and_a_sign_in_at_the_top_still_win(tmp_path):
    sub_captcha = [{"frameId": 0, "top": True, "page": step(0, fillable=2)}, {"frameId": 4, "page": {"t": "captcha"}}]
    out = _drive(tmp_path, [{"t": "step", "n": 0, "frames": sub_captcha}])
    assert out["record"]["why"] == "captcha" and names(out, "advance") == []
    sign_in = [{"frameId": 0, "top": True, "page": {"t": "sign_in", "host": WD}}, {"frameId": 4, "page": step(1, fillable=5)}]
    out = _drive(tmp_path, [{"t": "step", "n": 0, "host": WD, "frames": sign_in}], record=ON_WD, signInMoves=True)
    assert len(names(out, "signIn")) == 1


# ---------- Stop ----------

def test_a_stop_before_anything_ends_the_run_with_no_page_call_at_all(tmp_path):
    out = _drive(tmp_path, [step(1)], cancelAfter=0)
    assert (out["record"]["status"], out["record"]["why"]) == ("stopped", "user")
    assert out["calls"] == []


@pytest.mark.parametrize("after", [1, 2, 3, 4, 5, 6, 7, 8])
def test_a_stop_at_any_point_ends_stopped_user_and_nothing_page_facing_is_called_after_it(tmp_path, after):
    out = _drive(tmp_path, [step(1), step(2), REVIEW], cancelAfter=after)
    assert (out["record"]["status"], out["record"]["why"]) == ("stopped", "user")
    assert len(out["calls"]) == out["callsWhenCancelled"]


def test_a_stop_during_the_fill_never_reaches_the_advance(tmp_path):
    out = _drive(tmp_path, [step(1), REVIEW], cancelOnFill=1)
    assert out["record"]["why"] == "user" and names(out, "advance") == []


def test_a_stop_during_a_sign_in_never_reaches_the_wait_or_another_sign_in(tmp_path):
    out = _drive(tmp_path, [SIGN_IN], cancelAfter=4, record=ON_WD)   # openTab, classify, tabUrl, signIn
    assert out["record"]["why"] == "user"
    assert len(names(out, "signIn")) == 1 and names(out, "waitForChange") == []


def test_a_fill_that_reports_it_was_stopped_is_a_stopped_run(tmp_path):
    out = _drive(tmp_path, [step(1), REVIEW], fillStopped=1)
    assert (out["record"]["status"], out["record"]["why"]) == ("stopped", "user")
    assert names(out, "advance") == []


def test_the_wait_is_given_the_stop_check(tmp_path):
    out = _drive(tmp_path, [step(1), REVIEW])
    assert names(out, "waitForChange")[0][1:] == [15000, "function"]


# ---------- links, errors, records ----------

@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///etc/passwd", "chrome://settings", "ftp://x.test/a",
                                 "data:text/html,hi", "not a url", "", None, "//jobs.acme.test/x"])
def test_an_apply_link_that_is_not_http_or_https_is_never_opened(tmp_path, url):
    out = _drive(tmp_path, [step(1)], record={"openUrl": url})
    assert (out["record"]["status"], out["record"]["why"]) == ("stopped", "bad_link")
    assert out["calls"] == []


@pytest.mark.parametrize("url", ["https://jobs.acme.test/a?b=1#c", "HTTP://Jobs.Acme.test/a"])
def test_an_http_or_https_link_is_opened(tmp_path, url):
    out = _drive(tmp_path, [REVIEW], record={"openUrl": url})
    assert names(out, "openTab") == [["openTab", url, "function"]], "the Stop check rides to openTab"


def test_a_dependency_that_throws_stops_the_run_with_a_fixed_word_never_its_text(tmp_path):
    out = _drive(tmp_path, [step(1)], fillThrows=True)
    assert (out["record"]["status"], out["record"]["why"]) == ("stopped", "error")
    assert "secret-token-xyz" not in str(out)


def test_a_fill_that_returns_no_report_is_an_error_not_a_clean_page(tmp_path):
    out = _drive(tmp_path, [step(1), REVIEW], fillReturns="nothing")
    assert (out["record"]["why"], names(out, "advance")) == ("error", [])


@pytest.mark.parametrize("dep", ["openTab", "classify", "advance", "fill", "signIn", "waitForChange",
                                 "tabUrl", "sleep", "save", "onUpdate", "now", "cancelled"])
def test_a_missing_dependency_is_a_type_error_before_anything_runs(tmp_path, dep):
    out = _drive(tmp_path, [step(1)], omitDep=dep)
    assert out["threw"] == f"TypeError: queue-run: missing dep {dep}"
    assert out["calls"] == [] and out["events"] == []


def test_every_status_change_calls_onupdate_then_save_with_the_record(tmp_path):
    out = _drive(tmp_path, [step(1), REVIEW])
    events = out["events"]
    assert events and events[0].startswith("update:") and events[1] == "save:1"
    pairs = list(zip(events[0::2], events[1::2]))
    assert all(u.startswith("update:") and s == "save:1" for u, s in pairs) and len(events) % 2 == 0
    assert statuses(out)[-1] == "ready"


def test_the_record_stays_plain_json_and_value_free(tmp_path):
    out = _drive(tmp_path, [step(1), REVIEW], fills=[[needs("f1", status="verified")]])
    r = out["record"]
    assert set(r) >= {"jobId", "proposalId", "status", "why", "open", "hosts", "step", "seen", "fingerprint"}
    assert all(isinstance(f, str) for f in r["seen"])
    assert r["fingerprint"].startswith("https://jobs.acme.test/p/0")


# ---------- the module's own shape ----------

def test_the_runner_touches_no_browser_api_and_no_password():
    code = js_code(QUEUE_RUN_JS)
    for forbidden in ("chrome.", "document.", "fetch(", "localStorage", "console."):
        assert forbidden not in code, forbidden
    # The driver holds no credential: the one place a password is named is pageOps.signIn.
    assert len(re.findall(r"password", code)) == 3, "the password may appear only in pageOps().signIn"


# ---------- pageOps: the page-facing deps, over a fake transport ----------

_OPS_DRIVER = r"""
const ns = loadModules();
const sent = [];
const logged = [];
const realLog = console.log;
console.log = (...a) => logged.push(a.join(" "));
console.warn = console.error = console.info = console.log;
let t = 0;
let pollN = 0;
const t0 = { summary: { host: "x", fillable: 2, stepKey: "a", buttons: [{ text: "Next", visible: true }] }, top: true };
const t1 = { summary: { host: "x", fillable: 2, stepKey: "b", buttons: [{ text: "Next", visible: true }] }, top: true };

const ops = ns.queueRun.pageOps({
  broadcast: async (tabId, message, ...only) => {
    sent.push(only.length ? ["broadcast", tabId, message, only[0]] : ["broadcast", tabId, message]);
    if (message.type === "page_classify") pollN += 1;
    if (spec.broadcastThrows) throw new Error("tab gone");
    if (message.type === "page_classify") {
      const pages = spec.polls ?? [t0];
      const p = pages[Math.min(pollN - 1, pages.length - 1)];
      return p === null ? [{ frameId: 0, result: { summary: null } }] : [{ frameId: 0, result: p === "t1" ? t1 : t0 }];
    }
    return spec.advanceFrames ?? [{ frameId: 0, result: { clicked: true } }];
  },
  frame0: async (tabId, message) => {
    sent.push(["frame0", tabId, { ...message, password: message.password === undefined ? undefined : "<present>" }]);
    if (spec.frame0Throws) throw new Error(`could not reach with ${message.password}`);
    return "frame0Result" in spec ? spec.frame0Result : { signedIn: "clicked" };
  },
  api: async (path, init) => {
    sent.push(["api", path, JSON.parse(init.body)]);
    if (spec.apiThrows) throw new Error("409 conflict with the-password-9");
    return "login" in spec ? spec.login : { email: "ada@acme.test", password: "the-password-9" };
  },
  tabUrl: async () => (spec.urls ?? ["https://jobs.acme.test/a"])[Math.min(pollN, (spec.urls ?? [1]).length - 1)] ?? "https://jobs.acme.test/a",
  sleep: async (ms) => { t += ms; },
  now: () => t,
});

main(async () => {
  let result;
  if (spec.op === "classify") result = await ops.classify(4);
  if (spec.op === "advance") result = await ops.advance(4, spec.frameId ?? 0, "tag-1", spec.advanceOptions);
  if (spec.op === "signIn") {
    result = await ops.signIn({ proposalId: "p1", tabId: 4 },
      { allowedHost: "jobs.acme.test", ...(spec.stopAfterFetch ? { stop: () => true } : {}) });
  }
  if (spec.op === "wait") {
    const before = ns.queueRun.fingerprint(spec.beforeUrl ?? "https://jobs.acme.test/a", t0.summary);
    result = await ops.waitForChange(4, before, spec.ms ?? 3000, spec.stop ? () => true : undefined);
  }
  emit({ result, sent, logged, polls: pollN, slept: t });
});
"""


def _ops(tmp_path, op, **spec):
    return run_node(_OPS_DRIVER, {"op": op, **spec}, tmp_path, source=SOURCE)


def test_classify_asks_every_frame_of_the_named_tab_for_the_page_summary(tmp_path):
    out = _ops(tmp_path, "classify")
    assert out["sent"] == [["broadcast", 4, {"type": "page_classify"}]]
    assert out["result"][0]["frameId"] == 0


@pytest.mark.parametrize("options, message", [
    (None, {"type": "page_advance", "id": "tag-1"}),
    ({}, {"type": "page_advance", "id": "tag-1"}),
    ({"apply": False}, {"type": "page_advance", "id": "tag-1"}),
    ({"apply": "yes"}, {"type": "page_advance", "id": "tag-1"}),
    ({"apply": True}, {"type": "page_advance", "id": "tag-1", "apply": True}),
])
def test_advance_sends_the_id_and_the_apply_flag_only_when_it_is_exactly_true(tmp_path, options, message):
    out = _ops(tmp_path, "advance", advanceOptions=options)
    assert out["sent"] == [["broadcast", 4, message, 0]]
    assert out["result"] == {"clicked": True}


def test_every_press_goes_to_the_one_frame_that_named_the_button(tmp_path):
    apply = _ops(tmp_path, "advance", frameId=3, advanceOptions={"apply": True})
    assert apply["sent"] == [["broadcast", 4, {"type": "page_advance", "id": "tag-1", "apply": True}, 3]]
    plain = _ops(tmp_path, "advance", frameId=3)
    assert plain["sent"] == [["broadcast", 4, {"type": "page_advance", "id": "tag-1"}, 3]]


def test_a_stop_during_the_login_fetch_types_nothing_and_presses_nothing(tmp_path):
    out = _ops(tmp_path, "signIn", stopAfterFetch=True)
    assert out["result"] == {"signedIn": False, "why": "stopped"}
    assert [s[0] for s in out["sent"]] == ["api"], "frame 0 was never asked: no password was sent"
    assert "the-password-9" not in str(out["result"]) and "the-password-9" not in str(out["logged"])


def test_advance_answers_with_the_named_frames_result_only(tmp_path):
    frames = [{"frameId": 0, "result": {"clicked": False, "why": "not_next"}},
              {"frameId": 3, "result": {"clicked": True}}]
    assert _ops(tmp_path, "advance", advanceFrames=frames, frameId=3)["result"] == {"clicked": True}
    assert _ops(tmp_path, "advance", advanceFrames=frames, frameId=0)["result"] == {"clicked": False, "why": "not_next"}
    assert _ops(tmp_path, "advance", advanceFrames=frames, frameId=9)["result"] == {"clicked": False, "why": "gate"}


def test_sign_in_fetches_the_login_for_the_record_and_sends_it_to_frame_zero_only(tmp_path):
    out = _ops(tmp_path, "signIn")
    assert out["sent"][0] == ["api", "/api/companion/job-site-login", {"proposal_id": "p1"}]
    kind, tab, message = out["sent"][1]
    assert (kind, tab) == ("frame0", 4)
    assert message == {"type": "page_sign_in", "email": "ada@acme.test", "password": "<present>",
                       "allowedHost": "jobs.acme.test"}
    assert len(out["sent"]) == 2 and out["result"] == {"signedIn": True}


@pytest.mark.parametrize("spec, why", [
    ({"apiThrows": True}, "login_unavailable"),
    ({"login": {"email": "a@b.test"}}, "login_unavailable"),
    ({"login": None}, "login_unavailable"),
    ({"frame0Throws": True}, "unreachable"),
    ({"frame0Result": {"signedIn": False, "why": "host"}}, "host"),
    ({"frame0Result": {"signedIn": False}}, "refused"),
    ({"frame0Result": None}, "refused"),
])
def test_a_failed_sign_in_is_a_fixed_word_and_the_password_never_leaves(tmp_path, spec, why):
    out = _ops(tmp_path, "signIn", **spec)
    assert out["result"] == {"signedIn": False, "why": why}
    assert "the-password-9" not in str(out["result"]) and "the-password-9" not in str(out["logged"])
    if "login" in spec or spec.get("apiThrows"):
        assert [s[0] for s in out["sent"]] == ["api"], "no page is asked without a login"


def test_wait_for_change_returns_as_soon_as_the_fingerprint_differs(tmp_path):
    out = _ops(tmp_path, "wait", polls=[None, "t0", "t1"], urls=["https://jobs.acme.test/a"])
    assert out["result"]["changed"] is True and out["polls"] == 3


def test_wait_for_change_with_an_unreadable_page_counts_a_new_address(tmp_path):
    out = _ops(tmp_path, "wait", polls=[None], urls=["https://jobs.acme.test/a", "https://jobs.acme.test/b"])
    assert out["result"]["changed"] is True and out["result"]["url"] == "https://jobs.acme.test/b"


def test_wait_for_change_gives_up_at_the_deadline_with_changed_false(tmp_path):
    out = _ops(tmp_path, "wait", polls=["t0"], ms=2000)
    assert out["result"]["changed"] is False
    assert 2000 <= out["slept"] <= 2500


def test_wait_for_change_stops_at_once_when_asked_to(tmp_path):
    out = _ops(tmp_path, "wait", polls=["t0"], ms=60000, stop=True)
    assert out["result"]["changed"] is False and out["polls"] == 1 and out["slept"] == 0


def test_wait_for_change_survives_a_transport_that_throws_mid_navigation(tmp_path):
    out = _ops(tmp_path, "wait", broadcastThrows=True, ms=1000, urls=["https://jobs.acme.test/a", "https://jobs.acme.test/z"])
    assert out["result"]["changed"] is True


def test_the_fingerprint_is_the_address_without_the_hash_the_step_key_the_sorted_buttons_and_the_count(tmp_path):
    driver = r"""
    const ns = loadModules();
    const f = ns.queueRun.fingerprint;
    const s = { stepKey: "k1", fillable: 3, buttons: [{ text: "Next", visible: true }, { text: "Back", visible: true }, { text: "Hidden", visible: false }] };
    emit({ a: f("https://x.test/p?q=1#top", s), b: f("https://x.test/p?q=1#other", s), c: f("https://x.test/p?q=2", s),
           d: f("https://x.test/p?q=1", { ...s, stepKey: "k2" }), e: f("not a url", s), g: f("https://x.test/p?q=1", { ...s, fillable: 4 }) });
    """
    out = run_node(driver, {}, tmp_path, source=SOURCE)
    assert out["a"] == out["b"] == "https://x.test/p?q=1\nk1\nBack,Next\n3"
    assert len({out["a"], out["c"], out["d"], out["g"]}) == 4 and out["e"].startswith("\nk1")


def test_the_run_limits_cannot_be_changed_by_a_caller(tmp_path):
    driver = """const ns = loadModules(); try { ns.queueRun.RUN_LIMITS.FIELD_MS = 1; } catch {}
      emit({ run: ns.queueRun.RUN_LIMITS, frozen: Object.isFrozen(ns.queueRun.RUN_LIMITS) });"""
    out = run_node(driver, {}, tmp_path, source=SOURCE)
    assert out["run"]["FIELD_MS"] == 60000 and out["frozen"] is True


def test_the_limits_and_the_hidden_tab_finding_are_published(tmp_path):
    driver = "const ns = loadModules(); emit({ limits: ns.queueRun.LIMITS, run: ns.queueRun.RUN_LIMITS, hidden: ns.queueRun.HIDDEN_TABS_OK, keys: Object.keys(ns.queueRun).sort() });"
    out = run_node(driver, {}, tmp_path, source=SOURCE)
    assert out["limits"] == {"parallel": 3, "waitingMax": 10, "stepMax": 15, "changeMs": 15000, "paceMs": [2000, 6000]}
    assert out["run"] == {"FIELD_MS": 60000, "MAX_STEPS": 12, "RUN_MS": 600000}
    assert out["hidden"] is True
    assert "next" not in out["keys"], "the scheduler is Phase 3"
