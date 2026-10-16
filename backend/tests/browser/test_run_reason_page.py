"""The reasoning step against a Workday-style error the repair cannot map (fixtures/browser/workday_reason.html), in real Chromium.

The driver (`shared/queue-run.js`) runs in the page with the REAL page reader and message door, and the REAL reasoning loop
(`shared/reason-loop.js`) with a stub reasoner in place of the backend. The page refuses its Next with "Error - Source", a name
no field carries; the error repair maps nothing; the run asks the reasoner once. The stub answers the way the backend's checked
reply would: it names the select by its id and the page's own Next button by its ref, and never a value. The fill is a stub too
(the fill engine has its own tests): it sets the select the way /pick's safe default would. What this shows is the seam the fakes
cannot: the snapshot is built from the real page's reads, the Next pressed is the real button, and the page moves on.

Served from a made-up Workday-style host, as test_run_errors_page.py is.
"""

import json

from tests.browser.conftest import EXTENSION, fixture_html
from tests.browser.pages import oracle
from tests.browser.test_fill_end_to_end import SOURCES as MANIFEST_SOURCES

SOURCES = [*MANIFEST_SOURCES, "shared/queue-run.js", "shared/reason-loop.js"]
URL = "https://careers.acme.test/apply/application-questions"

DRIVER = """async (spec) => {
  const ns = window.careerStudioCompanion;
  const asks = [];
  const fills = [];
  const lines = [];
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
  const record = { jobId: "j1", proposalId: "p1", openUrl: location.href, tabId: 7, hosts: ["careers.acme.test"],
                   step: 0, seen: [], status: "waiting", why: null, open: [], readyAt: null, flowOrigin: null,
                   filled: true, wrote: true };
  const deps = {
    ...ops,
    openTab: async () => 7,
    tabUrl: async () => location.href,
    sleep: (ms) => new Promise((r) => setTimeout(r, Math.min(ms, 20))),
    fill: async () => ({ fields: [{ fid: "x", question: "Skills", required: true, status: "verified" }] }),
    // The error repair maps an error to a field by its words: "Source" is no field's, so it fixes nothing.
    fix: async () => ({ fixed: false }),
    attachTo: async () => ({ attached: false }),
    uploads: async () => await deliver({ type: "page_uploads" }),
    signIn: async () => ({ signedIn: false }),
    save: () => {},
    onUpdate: (rec) => { if (rec.step >= 1) stop = true; },   // the first real move ends the test run
    now: () => Date.now(),
    cancelled: () => stop,
    ...(spec.reason === false ? {} : {
      reason: (rec, ctx) => ns.reasonLoop.think(ctx, {
        now: () => Date.now(), cancelled: () => false, onLine: (text) => lines.push(text),
        read: async () => {
          const [frame] = await ops.classify(7);
          const inventory = await deliver({ type: "fill_inventory", readOnly: true });
          const errors = await deliver({ type: "page_errors" });
          return { frameId: 0, url: location.href, summary: frame.result.summary, fields: inventory.fields,
                   errors: errors.items, tabs: [], lastFill: {} };
        },
        // The stub reasoner: the snapshot's own ids, never a value.
        ask: async (body) => {
          asks.push(JSON.parse(JSON.stringify(body)));
          const source = body.fields.find((f) => /hear about/i.test(f.question));
          const next = body.buttons.find((b) => b.role === "next");
          return { note: "The error names Source; the select asks how you heard about the job.", rejected: [],
                   model: "stub", ms: 1, actions: [{ type: "choose", fid: source.fid, basis: "default" },
                                                   { type: "press_next", button: next.ref }] };
        },
        // The fill engine has its own tests: this sets the select the way /pick's safe default would.
        fill: async (fids, scope) => {
          fills.push(JSON.parse(JSON.stringify(scope)));
          const el = document.querySelector("select");
          el.value = "Company website";
          el.dispatchEvent(new Event("change", { bubbles: true }));
          return { fields: fids.map((fid) => ({ fid, question: "How did you hear about this job?", status: "assumed",
                                                answer: "Company website" })) };
        },
        dismiss: async () => ({ clicked: false }), follow: async () => false,
      }),
    }),
  };
  await ns.queueRun.drive(record, deps);
  return { record: JSON.parse(JSON.stringify(record)), asks, fills, lines };
}"""


def _serve(page):
    body = fixture_html("workday_reason.html")
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
    return page.evaluate(DRIVER, spec)


def test_an_error_the_repair_cannot_map_is_answered_by_the_stub_reasoner_and_the_page_moves_on(page):
    out = _drive(page)
    r = out["record"]
    assert (r["step"], len(r["seen"])) == (1, 1)
    assert oracle(page, "step") == "Review" and oracle(page, "nexts") == 2      # refused once, then the thought's press
    assert oracle(page, "hear") == "Company website"
    [ask] = out["asks"]
    [source] = [f for f in ask["fields"] if "hear about" in f["question"]]
    assert ask["why"] == "page_errors" and source["filled"] is False and source["required"] is True
    assert [o["text"] for o in source["options"]] == ["Company website", "Referral"]    # "Select One" is no choice
    assert [e["text"] for e in ask["errors"]] == ["Source"]
    assert [b["role"] for b in ask["buttons"]] == ["next"]
    # Value-free: the chosen option is a word on the page, and nothing outside the page's own fields repeats it.
    assert "Company website" not in json.dumps({k: v for k, v in ask.items() if k != "fields"})
    assert out["fills"] == [{"routes": {source["fid"]: "low_stakes"}, "reasoned": "choose"}]
    assert any(line.startswith("Thinking") for line in out["lines"])


def test_without_the_reasoner_the_same_page_parks_page_errors(page):
    out = _drive(page, reason=False)
    r = out["record"]
    assert (r["status"], r["why"], r["step"]) == ("parked", "page_errors", 0)
    assert oracle(page, "step") == "Application Questions" and oracle(page, "nexts") == 1
