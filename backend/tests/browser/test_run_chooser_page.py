"""The Workday start chooser (fixtures/browser/workday_chooser.html) through the queued run's real message door.

The page reader, `content/agent.js`'s `page_classify` / `page_advance` handlers and `queueRun.pageOps` are all real;
only the transport is a captured `chrome.runtime` listener. What the fakes in test_extension_queue_run.py cannot show:
the `chooser` flag survives the whole way (pageOps -> message door -> reader), the press is a navigation to the link's
own address, and the other two links on the page are never touched.
"""

import re

from playwright.sync_api import Error as PlaywrightError

from tests.browser.conftest import EXTENSION, fixture_html
from tests.browser.test_fill_end_to_end import SOURCES as MANIFEST_SOURCES

SOURCES = [*MANIFEST_SOURCES, "shared/queue-run.js"]
URL = "https://acme.wd1.myworkdayjobs.com/en-US/careers/job/Analyst_R1/apply"

OPS = """() => {
  const ns = window.careerStudioCompanion;
  const deliver = (msg) => new Promise((resolve) => {
    const open = window.__pageListener(msg, { id: "t" }, (reply) => resolve(reply?.ok ? reply.data : null));
    if (open !== true) resolve(null);
  });
  window.__ops = ns.queueRun.pageOps({
    broadcast: async (_tab, message) => [{ frameId: 0, result: await deliver(message) }],
    frame0: async () => null, api: async () => null, tabUrl: async () => location.href,
    sleep: async () => {}, now: () => Date.now(),
  });
}"""


def _serve(page):
    page.route(URL, lambda route: route.fulfill(status=200, content_type="text/html", body=fixture_html("workday_chooser.html")))
    page.route(re.compile(r"https://acme\.wd1\.myworkdayjobs\.com/.*/apply/.+"), lambda route: route.fulfill(
        status=200, content_type="text/html", body="<p>landed</p>"))
    page.goto(URL)
    page.evaluate("""() => {
      window.chrome = window.chrome || {};
      Object.defineProperty(window.chrome, "runtime", { configurable: true, value: {
        id: "t", onMessage: { addListener: (fn) => { window.__pageListener = fn; } } } });
    }""")
    for src in SOURCES:
        page.add_script_tag(content=(EXTENSION / src).read_text(encoding="utf-8"))
    assert page.evaluate("typeof window.__pageListener") == "function"
    page.evaluate(OPS)


def _chooser_id(page):
    frames = page.evaluate("() => window.__ops.classify(7)")
    return frames[0]["result"]["summary"]["chooserId"]


def test_the_chooser_flag_goes_all_the_way_and_the_press_is_a_navigation_to_apply_manually(page):
    _serve(page)
    cid = _chooser_id(page)
    assert cid
    with page.expect_navigation() as nav:
        try:
            answer = page.evaluate("(id) => window.__ops.advance(7, 0, id, { chooser: true })", cid)
        except PlaywrightError as err:
            if "context was destroyed" not in str(err):
                raise
            answer = {"clicked": True}
    assert answer == {"clicked": True}
    assert nav.value.url == "https://acme.wd1.myworkdayjobs.com/en-US/careers/job/Analyst_R1/apply/applyManually?source=Board"


def test_without_the_flag_the_same_id_is_refused_as_the_submit_it_reads_as(page):
    _serve(page)
    cid = _chooser_id(page)
    answer = page.evaluate("(id) => window.__ops.advance(7, 0, id)", cid)
    assert answer == {"clicked": False, "why": "submit"}
    assert page.url == URL
