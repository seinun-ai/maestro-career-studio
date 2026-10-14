"""The queued run's driver against the errors page (fixtures/browser/workday_errors.html), in real Chromium.

The driver (`shared/queue-run.js`) runs in the page with the REAL page reader and message door, so the
one thing the fakes cannot show is shown here: a Next the page refuses is read as a rejection, its
banner buttons change nothing, the error is read in the page's own words, the upload box it names is
written to, and the second Next is the one that moves. The fill is a stub (the fill engine has its own
tests); the resume bytes are a few bytes of PDF.

The page is served from a made-up Workday-style host (the route only answers the page request, the
context is offline), because the driver parks a Resume on a host the run never reached.
"""

import json

import pytest

from tests.browser.conftest import EXTENSION, fixture_html
from tests.browser.pages import oracle
from tests.browser.test_fill_end_to_end import SOURCES as MANIFEST_SOURCES

SOURCES = [*MANIFEST_SOURCES, "shared/queue-run.js"]
URL = "https://careers.acme.test/apply/my-experience"
PDF = "JVBERi0xLjQKJSVFT0YK"

DRIVER = """async (spec) => {
  const ns = window.careerStudioCompanion;
  const calls = [];
  const deliver = (msg) => new Promise((resolve) => {
    const open = window.__pageListener(msg, { id: "t" }, (reply) =>
      resolve(reply?.ok ? reply.data : null));
    if (open !== true) resolve(null);
  });
  const ops = ns.queueRun.pageOps({
    broadcast: async (_tab, message) => [{ frameId: 0, result: await deliver(message) }],
    frame0: async () => null, api: async () => null,
    tabUrl: async () => location.href, sleep: (ms) => new Promise((r) => setTimeout(r, Math.min(ms, 20))),
    now: () => Date.now(),
  });
  let stop = false;
  const record = { jobId: "j1", proposalId: "p1", openUrl: URL, tabId: 7, hosts: ["careers.acme.test"],
                   step: 0, seen: [], status: "waiting", why: null, open: [], readyAt: null, flowOrigin: null,
                   filled: true, wrote: true };
  const attachTo = async (rec, box) => {
    calls.push(["attachTo", box.target]);
    const reply = await deliver({ type: "attach_resume_pdf", b64: spec.pdf, filename: "Ada.pdf", resumeOnly: true, target: box.target });
    return { attached: (reply?.proven ?? 0) > 0 };
  };
  const deps = {
    ...ops,
    openTab: async () => 7,
    tabUrl: async () => location.href,
    sleep: (ms) => new Promise((r) => setTimeout(r, Math.min(ms, 20))),
    fill: async (rec) => {
      calls.push(["fill"]);
      const attach = spec.gate ? await (async () => {
        const boxes = (await deliver({ type: "page_uploads" })).filter((b) => b.required && !b.occupied);
        return { outcome: null, reason: null, required: boxes.length > 0, boxes: boxes.map(({ label, target, kind }) => ({ label, target, kind, written: false })) };
      })() : undefined;
      return { fields: [{ fid: "x", question: "Skills", required: true, status: "verified" }], ...(attach ? { attach } : {}) };
    },
    fix: async (rec, errors) => {
      calls.push(["fix", errors.map((e) => [e.label, e.kind]), rec.step, rec.seen.length]);
      if (spec.repair === "lie") return { fixed: true };   // claims a repair it did not make
      if (!spec.repair) return { fixed: false };
      for (const e of errors) if (e.kind === "upload" && !(await attachTo(rec, e)).attached) return { fixed: false };
      return { fixed: true };
    },
    attachTo,
    uploads: async () => await deliver({ type: "page_uploads" }),
    signIn: async () => ({ signedIn: false }),
    save: () => {},
    onUpdate: (rec) => { if (rec.step >= 1) stop = true; },   // the first real move ends the test run
    now: () => Date.now(),
    cancelled: () => stop,
  };
  await ns.queueRun.drive(record, deps);
  return { record: JSON.parse(JSON.stringify(record)), calls };
}"""


def _serve(page):
    body = fixture_html("workday_errors.html")
    page.route("**/*", lambda route: route.fulfill(status=200, content_type="text/html", body=body))
    page.goto(URL)
    page.evaluate("""() => {
      window.chrome = window.chrome || {};
      Object.defineProperty(window.chrome, "runtime", { configurable: true, value: {
        id: "t", onMessage: { addListener: (fn) => { window.__pageListener = fn; } } } });
    }""")
    for src in SOURCES:
        page.add_script_tag(content=(EXTENSION / src).read_text(encoding="utf-8"))
    assert page.evaluate("typeof window.__pageListener") == "function"


def _drive(page, **spec):
    page.set_default_timeout(60000)
    _serve(page)
    return page.evaluate(DRIVER.replace("URL", json.dumps(URL)), {"pdf": PDF, **spec})


def test_a_rejected_next_is_read_repaired_by_attaching_to_the_named_box_and_the_second_next_moves(page):
    out = _drive(page, repair=True)
    r = out["record"]
    # Exactly one move, and only after the second press: the first was the page's refusal.
    assert (r["step"], len(r["seen"])) == (1, 1)
    assert oracle(page, "nexts") == 2 and oracle(page, "step") == "Application Questions"
    assert oracle(page, "files") == ["Ada.pdf"]
    # The fix was handed the page's own words and kind, before any step was counted.
    assert [c for c in out["calls"] if c[0] == "fix"] == [["fix", [["Upload a file (5MB max)", "upload"]], 0, 0]]
    # The page was filled once; the repair is not a refill.
    assert [c[0] for c in out["calls"]].count("fill") == 1


def test_a_rejection_that_cannot_be_repaired_parks_naming_the_upload_and_presses_once(page):
    out = _drive(page, repair=False)
    r = out["record"]
    assert (r["status"], r["why"], r["step"], r["seen"]) == ("parked", "page_errors", 0, [])
    assert r["open"] == [{"fid": None, "question": "Upload a file (5MB max)", "required": True}]
    assert oracle(page, "nexts") == 1 and oracle(page, "step") == "My Experience"


def test_the_same_error_after_a_repair_that_changed_nothing_parks_after_one_more_press(page):
    out = _drive(page, repair="lie")
    r = out["record"]
    assert (r["status"], r["why"], r["step"], r["seen"]) == ("parked", "page_errors", 0, [])
    assert oracle(page, "nexts") == 2 and len([c for c in out["calls"] if c[0] == "fix"]) == 1


def test_the_gate_attaches_to_the_required_upload_before_the_first_next_so_nothing_is_ever_rejected(page):
    out = _drive(page, gate=True, repair=True)
    r = out["record"]
    assert (r["step"], len(r["seen"])) == (1, 1)
    assert oracle(page, "nexts") == 1, "the page never had a Next to refuse"
    assert [c[0] for c in out["calls"]] == ["fill", "attachTo"]
    assert oracle(page, "files") == ["Ada.pdf"]


def test_a_lone_required_box_labelled_for_a_cover_letter_is_never_written_the_run_parks_naming_it(page):
    page.set_default_timeout(60000)
    body = fixture_html("workday_errors.html").replace("Upload a file (5MB max)</span>", "Cover letter</span>")
    page.route("**/*", lambda route: route.fulfill(status=200, content_type="text/html", body=body))
    page.goto(URL)
    page.evaluate("""() => {
      window.chrome = window.chrome || {};
      Object.defineProperty(window.chrome, "runtime", { configurable: true, value: {
        id: "t", onMessage: { addListener: (fn) => { window.__pageListener = fn; } } } });
    }""")
    for src in SOURCES:
        page.add_script_tag(content=(EXTENSION / src).read_text(encoding="utf-8"))
    out = page.evaluate(DRIVER.replace("URL", json.dumps(URL)), {"pdf": PDF, "gate": True, "repair": True})
    r = out["record"]
    assert (r["status"], r["why"]) == ("parked", "upload")
    assert [o["question"] for o in r["open"]] == ["Cover letter"]
    assert oracle(page, "files") == [] and oracle(page, "nexts") == 0
    assert [c[0] for c in out["calls"]] == ["fill"]
