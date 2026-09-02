"""Posting identity: the ONE table, read by the backend matcher and the panel.

`job_url_match.posting_id` (backend: is this page the saved job? does this
save dedupe into an existing row?) and `shared/decisions.js` `postingId`
(extension: which remembered pick may come back on this page?) answer the
same question about the same URLs. They are two functions in two languages by
necessity — the panel decides offline, before any round trip — so this file
is what keeps them one rule: every URL below goes through both, and the
answers must agree. Add a key to one table and this goes red until the other
has it.

The second half covers the extraction side of the same SPA problem: a job
board that swaps the visible posting under a stable-looking `<head>` leaves
the first job's JSON-LD in place, so the page keeps answering with job A's
text on job B's url.
"""

import json

import pytest

from app.services.job_url_match import is_same_posting, posting_id
from tests.extension_harness import _content_source, CONTENT, SHARED, run_node
from tests.extension_panel_harness import DECISIONS_JS

URLS = [
    "https://www.linkedin.com/jobs/search/?currentJobId=4001&keywords=data",
    "https://www.linkedin.com/jobs/collections/recommended/?currentJobId=4001",
    "https://www.linkedin.com/jobs/view/4001/",
    "https://www.linkedin.com/jobs/view/data-engineer-at-acme-4001?position=1&refId=x",
    "https://www.linkedin.com/jobs/search/?currentJobId=&keywords=data",
    "https://www.linkedin.com/jobs/search/?keywords=data",
    "https://www.indeed.com/viewjob?jk=abc123&from=serp",
    "https://www.indeed.com/jobs?q=data&vjk=abc123",
    "https://acme.example/careers?gh_jid=555",
    "https://acme.example/careers",
    "https://jobs.lever.co/acme/abc?gh_src=x",
    "https://boards.greenhouse.io/acme/jobs/123",
    "https://acme.wd5.myworkdayjobs.com/en-US/careers/job/Data-Scientist",
    "https://example.com/jobs/view/4001/",
    "https://example.com/?jobId=9&currentJobId=10",
    "chrome://newtab",
    "",
    "not a url",
]

_IDENTITY_DRIVER_JS = r"""
const { postingId } = loadModules().decisions;
main(async () => {
  emit(spec.urls.map((url) => {
    try {
      const hit = postingId(url);
      return hit ? [hit.host, hit.id] : null;
    } catch (err) {
      return `THREW: ${err.constructor.name}`;
    }
  }));
});
"""


@pytest.fixture(scope="module")
def js_answers(tmp_path_factory):
    return run_node(_IDENTITY_DRIVER_JS, {"urls": URLS},
                    tmp_path_factory.mktemp("identity"), source=DECISIONS_JS)


@pytest.mark.parametrize("index", range(len(URLS)), ids=[u or "<empty>" for u in URLS])
def test_backend_and_extension_agree_on_every_posting_id(js_answers, index):
    url = URLS[index]
    py = posting_id(url)
    assert js_answers[index] == (list(py) if py else None), url


def test_the_table_exercises_both_branches():
    """A table where nothing carries an id would pass vacuously."""
    hits = [posting_id(u) for u in URLS]
    assert sum(1 for h in hits if h) >= 6
    assert sum(1 for h in hits if h is None) >= 5


# ---------- the stale JSON-LD guard in extractJobPosting ----------

_EXTRACT_DRIVER_JS = r"""
// agent.js registers its message listener at load; the front door is not
// under test here, only the extraction behind it.
global.chrome = { runtime: { id: "ext", onMessage: { addListener() {} } } };
const scripts = (spec.page.jsonLd ?? []).map((text) => ({ textContent: text }));
global.document = {
  title: spec.page.title ?? "",
  querySelectorAll: (selector) =>
    selector === 'script[type="application/ld+json"]' ? scripts : [],
  querySelector: () => null,
  createElement: () => {
    const el = { innerHTML: "" };
    Object.defineProperty(el, "innerText", {
      get: () => el.innerHTML.replace(/<[^>]+>/g, ""),
    });
    return el;
  },
  body: { innerText: spec.page.body ?? "" },
};
global.location = { href: spec.page.url, hostname: new URL(spec.page.url).hostname };
main(async () => {
  const ns = loadModules();
  emit(ns.pageHandlers.extract_job_posting());
});
"""

_EXTRACT_SOURCES = [SHARED / "decisions.js", CONTENT / "job-posting.js", CONTENT / "agent.js"]


def _extract(tmp_path, *, url, posting_url, body="Job B body text " * 40):
    posting = {
        "@context": "https://schema.org", "@type": "JobPosting",
        "title": "Job A", "description": "<p>Job A description</p>",
        "hiringOrganization": {"@type": "Organization", "name": "Acme"},
    }
    if posting_url is not None:
        posting["url"] = posting_url
    return run_node(
        _EXTRACT_DRIVER_JS,
        {"page": {"url": url, "jsonLd": [json.dumps(posting)], "body": body,
                  "title": "Job B | Board"}},
        tmp_path, source=_content_source(_EXTRACT_SOURCES))


LI_A = "https://www.linkedin.com/jobs/view/4001/"
LI_B = "https://www.linkedin.com/jobs/search/?currentJobId=4002"


def test_json_ld_for_the_job_the_user_left_is_not_the_posting(tmp_path):
    """Job A's JSON-LD is still in `<head>` while the url and the pane say job
    B. Both sides carry a posting id and they disagree, so the walk is
    refused and the visible content answers instead."""
    out = _extract(tmp_path, url=LI_B, posting_url=LI_A)
    assert out["source"] != "json-ld"
    assert "Job A" not in out["text"]
    assert out["url"] == LI_B


def test_json_ld_for_this_very_job_is_still_preferred(tmp_path):
    """Same id on both sides — the list url and the permalink — is the same
    posting, and structured data still beats a page scrape."""
    out = _extract(tmp_path, url="https://www.linkedin.com/jobs/search/?currentJobId=4001",
                   posting_url=LI_A)
    assert out["source"] == "json-ld"
    assert "Title: Job A" in out["text"]


def test_json_ld_without_a_url_is_trusted_as_before(tmp_path):
    """No `url` in the block means nothing to compare; a board we cannot
    identify keeps the structured answer rather than losing it to caution."""
    out = _extract(tmp_path, url=LI_B, posting_url=None)
    assert out["source"] == "json-ld"
    out = _extract(tmp_path, url="https://jobs.lever.co/acme/abc",
                   posting_url="https://jobs.lever.co/acme/xyz")
    assert out["source"] == "json-ld"


def test_the_backend_rule_the_guard_mirrors():
    assert is_same_posting(LI_A, LI_B) is False
    assert is_same_posting(LI_A, "https://www.linkedin.com/jobs/search/?currentJobId=4001") is True
