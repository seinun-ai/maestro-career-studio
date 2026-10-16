"""A one-page application (fixtures/browser/greenhouse_acme_form.html) through the queued run's real page reader and driver.

Live check 7 (2026-10-15): a hosted job board whose posting, header Apply BUTTON and whole form share one page, ending in one
Submit. The page reader, the message door and `queueRun.drive` are real; the fill (and later the reasoner) are stubs, as in
test_run_reason_page.py. What this shows: the page reads as a review page that HAS fields, the run fills it at step 0, and
nothing on it is ever pressed.
"""


from tests.browser.conftest import EXTENSION, fixture_html
from tests.browser.pages import oracle
from tests.browser.test_fill_end_to_end import SOURCES as MANIFEST_SOURCES

SOURCES = [*MANIFEST_SOURCES, "shared/queue-run.js", "shared/reason-loop.js"]
URL = "https://job-boards.greenhouse.io/acme/jobs/7?gh_src=abc"

DRIVER = """async (spec) => {
  const ns = window.careerStudioCompanion;
  const calls = [];
  const asks = [];
  const fills = [];
  const deliver = (msg) => new Promise((resolve) => {
    const open = window.__pageListener(msg, { id: "t" }, (reply) => resolve(reply?.ok ? reply.data : null));
    if (open !== true) resolve(null);
  });
  const ops = ns.queueRun.pageOps({
    broadcast: async (_tab, message) => {
      if (message.type === "page_advance") calls.push(["advance", message.id]);
      return [{ frameId: 0, result: await deliver(message) }];
    },
    frame0: async () => null, api: async () => null,
    tabUrl: async () => location.href, sleep: (ms) => new Promise((r) => setTimeout(r, Math.min(ms, 20))),
    now: () => Date.now(),
  });
  const record = { jobId: "j1", proposalId: "p1", openUrl: location.href, tabId: 7, hosts: ["job-boards.greenhouse.io"],
                   step: 0, seen: [], status: "waiting", why: null, open: [], readyAt: null, flowOrigin: null };
  const deps = {
    ...ops,
    openTab: async () => 7,
    tabUrl: async () => location.href,
    sleep: (ms) => new Promise((r) => setTimeout(r, Math.min(ms, 20))),
    fill: async (rec) => {
      calls.push(["fill", rec.step]);
      return { fields: [{ fid: "x", question: "Name", required: true, status: "verified" },
                        ...(spec.reason ? [{ fid: spec.degree, question: "Degree", required: true, status: "needs_answer" }] : [])] };
    },
    fix: async () => ({ fixed: false }),
    attachTo: async () => ({ attached: false }),
    uploads: async () => await deliver({ type: "page_uploads" }),
    signIn: async () => ({ signedIn: false }),
    save: () => {},
    onUpdate: () => {},
    now: () => Date.now(),
    cancelled: () => false,
    ...(!spec.reason ? {} : {
      reason: (rec, ctx) => ns.reasonLoop.think(ctx, {
        now: () => Date.now(), cancelled: () => false, onLine: () => {},
        read: async () => {
          const [frame] = await ops.classify(7);
          const inventory = await deliver({ type: "fill_inventory", readOnly: true });
          const errors = await deliver({ type: "page_errors" });
          return { frameId: 0, url: location.href, summary: frame.result.summary, fields: inventory.fields,
                   errors: errors.items, tabs: [], lastFill: {} };
        },
        // The stub reasoner picks the Degree field by its question and, to be tested, also tries to press everything it can name.
        ask: async (body) => {
          asks.push(JSON.parse(JSON.stringify(body)));
          const degree = body.fields.find((f) => /degree/i.test(f.question));
          return { note: "Degree is empty.", rejected: [], model: "stub", ms: 1, actions: [
            { type: "choose", fid: degree.fid, basis: "default" }, { type: "press_next", button: "b1" }] };
        },
        // The fill engine has its own tests: this clicks the real list's option the way a person would.
        fill: async (fids) => {
          fills.push(fids);
          const shell = document.querySelector('[data-rs="degree--0"]');
          shell.querySelector(".select__control").dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
          [...shell.querySelectorAll("[role=option]")].find((o) => o.textContent === "Master's Degree").click();
          return { fields: fids.map((fid) => ({ fid, question: "Degree", status: "assumed", answer: "Master's Degree" })) };
        },
        dismiss: async () => { calls.push(["dismiss"]); return { clicked: false }; }, follow: async () => false,
      }),
    }),
  };
  await ns.queueRun.drive(record, deps);
  return { record: JSON.parse(JSON.stringify(record)), calls, asks, fills };
}"""


def _serve(page, name="greenhouse_acme_form.html"):
    body = fixture_html(name)
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


def test_the_page_reads_as_a_review_page_with_fields_and_no_apply_to_press(page):
    _serve(page)
    s = page.evaluate("() => window.careerStudioCompanion.pageReader.summary()")
    assert s["applyId"] is None and s["fillable"] > 0 and s["submitSeen"] is True
    verdict = page.evaluate("(s) => window.careerStudioCompanion.pageKind.classify(s)", s)
    assert (verdict["kind"], verdict.get("by")) == ("review", "submit_button")


def test_the_run_fills_the_one_page_form_at_step_zero_and_pressing_nothing_parks_on_what_is_still_empty(page):
    """The stub fill writes nothing, so the required boxes stay empty: the run parks naming them. What matters is the
    way it got there: the page was read (not "unknown"), filled once at step 0, and no Apply or Submit was pressed."""
    _serve(page)
    page.set_default_timeout(60000)
    out = page.evaluate(DRIVER, {})
    r = out["record"]
    assert (r["status"], r["why"], r["step"]) == ("parked", "open_questions", 0)
    assert {"First Name", "Degree", "Location (City)"} <= {o["question"] for o in r["open"]}
    assert out["calls"] == [["fill", 0]]          # filled once, at step 0; nothing pressed
    assert page.evaluate("() => window.__sent ?? false") is False


def test_the_reasoning_step_works_the_one_page_forms_fields_and_presses_nothing_on_it(page):
    """The seam the fakes cannot show: the snapshot is built from the real page, says it is one page and offers no button,
    the Degree list is chosen in the real widget, and neither the Submit nor the header Apply is ever pressed."""
    _serve(page)
    page.set_default_timeout(60000)
    degree = page.evaluate("""async () => {
      const inv = await new Promise((resolve) => window.__pageListener({ type: "fill_inventory", readOnly: true }, { id: "t" },
        (reply) => resolve(reply.data)));
      return inv.fields.find((f) => /degree/i.test(f.question)).fid;
    }""")
    out = page.evaluate(DRIVER, {"reason": True, "degree": degree})
    [ask] = out["asks"]
    assert ask["one_page"] is True and ask["buttons"] == [] and ask["why"] == "open_questions"
    assert out["fills"] == [[degree]] and oracle(page, "gh_degree") == "Master's Degree"
    assert [c for c in out["calls"] if c[0] in ("advance", "dismiss")] == []
    assert page.evaluate("() => window.__sent ?? false") is False


# ---------- a page the reader could not see into (live check 8) ----------


def test_a_one_click_application_built_of_shadow_components_is_filled_at_step_zero_and_its_submit_is_never_pressed(page):
    """The page has no <form>, every control in an open shadow root, a slotted Submit. The reader sees it as a review page that
    HAS fields (it used to see nothing and the run parked "Page not recognised"), the run fills it at step 0, parks naming the
    required boxes the stub fill left empty, and nothing on the page is pressed."""
    _serve(page, "shadow_one_page_form.html")
    s = page.evaluate("() => window.careerStudioCompanion.pageReader.summary()")
    verdict = page.evaluate("(s) => window.careerStudioCompanion.pageKind.classify(s)", s)
    assert s["fillable"] > 0 and (verdict["kind"], verdict.get("by")) == ("review", "submit_button")
    page.set_default_timeout(60000)
    out = page.evaluate(DRIVER, {})
    r = out["record"]
    assert (r["status"], r["why"], r["step"]) == ("parked", "open_questions", 0)
    assert {"First name", "Email", "City"} <= {o["question"] for o in r["open"]}
    assert out["calls"] == [["fill", 0]]
    assert oracle(page, "shadow_submits") == 0 and oracle(page, "shadow_nexts") == 0


def test_a_page_the_reader_counts_no_field_on_but_the_inventory_lists_one_is_filled_and_never_parked_as_unknown(page):
    """Owner's rule: "when I am there the autofill should work". A button that opens a dialog with its own search box
    (`aria-haspopup="dialog"`) is a field the fill inventory lists and the reader's count does not know, so the page reads as
    unknown; the run asks the page how many of its listed fields are an application's before it parks, and fills."""
    _serve(page, "popup_with_search.html")
    s = page.evaluate("() => window.careerStudioCompanion.pageReader.summary()")
    assert s["fillable"] == 0 and page.evaluate("(s) => window.careerStudioCompanion.pageKind.classify(s).kind", s) == "unknown"
    page.set_default_timeout(60000)
    out = page.evaluate(DRIVER, {})
    r = out["record"]
    assert r["status"] == "parked" and r["why"] in ("open_questions", "unsure_page") and r["step"] == 0
    assert out["calls"] == [["fill", 0]]


LANDING = """<!doctype html><html><head><title>Careers at Acme</title></head><body>
<header><nav><a href="/">Acme</a></nav></header>
<main><h1>Find your next role</h1>
<div role="search"><input type="search" name="q" placeholder="Search jobs"><label>Location <input name="location"></label><button>Search</button></div>
<p>We hire across many teams.</p></main></body></html>"""


def test_a_careers_landing_page_with_only_a_search_box_and_a_location_is_still_an_unknown_page_and_nothing_is_filled(page):
    """The inventory lists a search box and its Location as fields; neither is an application's. The count the run asks the
    page for leaves out what the reader's own fillable count leaves out (a [role=search] region, a search-named or search-typed
    box), so the widened rule does not fill a site's search or a newsletter box."""
    page.route("**/*", lambda route: route.fulfill(status=200, content_type="text/html", body=LANDING))
    page.goto(URL)
    page.evaluate("""() => {
      window.chrome = window.chrome || {};
      Object.defineProperty(window.chrome, "runtime", { configurable: true, value: {
        id: "t", onMessage: { addListener: (fn) => { window.__pageListener = fn; } } } });
    }""")
    for src in SOURCES:
        page.add_script_tag(content=(EXTENSION / src).read_text(encoding="utf-8"))
    inventory = page.evaluate("""async () => (await new Promise((resolve) => window.__pageListener({ type: "fill_inventory", readOnly: true },
        { id: "t" }, (reply) => resolve(reply.data)))).fields.length""")
    assert inventory == 2   # the inventory does list them
    page.set_default_timeout(60000)
    out = page.evaluate(DRIVER, {})
    assert (out["record"]["status"], out["record"]["why"]) == ("parked", "unknown_page")
    assert out["calls"] == []
