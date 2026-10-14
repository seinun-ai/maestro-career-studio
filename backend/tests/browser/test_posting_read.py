"""Reading a posting that has no JSON-LD: the heading-anchored description and the recorded Darwinbox page.

`content/agent.js` `extractJobPosting` is driven through its real message door (`pageHandlers.extract_job_posting`) in
real Chromium, over `fixtures/browser/darwinbox_posting.html` (an Angular candidate portal: no JSON-LD, no `main`, no
`article`, no `h1`, a hidden duplicate description) and over small inline pages for the generic rules. Visibility is
the point of several of these, so they need layout, which the fake-DOM node harness does not have. The header lines
the reader writes are then pushed through the panel's real `previewFrom` (node, `PANEL_SOURCE`) to show the three
boxes fill and the description keeps its first line.
"""

import pytest

from tests.browser.conftest import EXTENSION, fixture_html
from tests.browser.test_fill_end_to_end import SOURCES
from tests.extension_harness import run_node
from tests.extension_panel_harness import PANEL_SOURCE, _PANEL_FAKES_JS

DARWINBOX = "https://acme.darwinbox.in/ms/candidatev2/main/careers/jobDetails/a0000000000001?src=Linkedin"
ELSEWHERE = "https://careers.acme.test/jobs/data-analyst"
FILLER = "The team builds reliable data systems and reports for the whole plant. " * 6  # about 400 characters

READ = "() => window.careerStudioCompanion.pageHandlers.extract_job_posting()"
DESCRIBES = "(p) => window.careerStudioCompanion.decisions.describesJob(p)"


def _open(page, url, html):
    page.route(url, lambda route: route.fulfill(status=200, content_type="text/html", body=html))
    page.goto(url)
    page.evaluate("""() => {
      window.chrome = window.chrome || {};
      Object.defineProperty(window.chrome, "runtime", { configurable: true, value: {
        id: "t", onMessage: { addListener: () => {} } } });
    }""")
    for src in SOURCES:
        page.add_script_tag(content=(EXTENSION / src).read_text(encoding="utf-8"))


def _read(page):
    return page.evaluate(READ)


def _darwinbox(page, url=DARWINBOX, meta=None):
    html = fixture_html("darwinbox_posting.html")
    if meta is not None:
        html = html.replace('content="Job Title | Acme Robotics"', f'content="{meta}"')
    _open(page, url, html)
    return _read(page)


def _generic(page, body):
    _open(page, ELSEWHERE, f"<!doctype html><title>Careers</title><body>{body}</body>")
    return _read(page)


# ---------- P1: the description under its own heading, visible only ----------


def test_a_posting_with_no_json_ld_reads_as_content_and_leaves_the_page_around_it_out(page):
    out = _darwinbox(page)
    assert out["source"] == "content"
    assert page.evaluate(DESCRIBES, out) is True
    assert "Key Responsibilities" in out["text"] and "scripting language" in out["text"]
    for chrome in ("Sign In", "Job Snapshot", "Share the opportunity", "View Similar Jobs"):
        assert chrome not in out["text"], chrome


def test_a_longer_hidden_copy_of_the_description_is_never_the_answer(page):
    out = _darwinbox(page)
    assert "THE HIDDEN COPY ONLY" not in out["text"]
    # The hidden copy is the longer of the two, and `innerText` of a hidden node still returns its text.
    hidden = page.evaluate("() => document.querySelector('.mobile-view-jd .jd').innerText.length")
    assert hidden > len(out["text"].split("Job Description", 1)[-1].strip())


def test_a_hidden_job_description_container_is_not_a_description(page):
    out = _generic(page, f'<div class="job-description" style="display:none">{FILLER}</div><p>Hello.</p>')
    assert out["source"] == "body"
    assert not page.evaluate(DESCRIBES, out)


@pytest.mark.parametrize("heading", [
    "About the role", "About the job", "About the position", "Job Description", "job summary:",
    "Role Overview", "Role description", "Position summary", "Position Description",
])
def test_a_generic_page_with_a_description_heading_reads_as_content(page, heading):
    out = _generic(page, f"<div><h2>{heading}</h2><p>{FILLER}</p></div><div>Unrelated page text</div>")
    assert out["source"] == "content"
    assert FILLER.strip() in out["text"]
    assert "Unrelated page text" not in out["text"]


def test_a_heading_only_counts_when_it_is_the_whole_text_of_its_element(page):
    out = _generic(page, f"<div><p>We wrote a note about the role and the job description.</p><p>{FILLER}</p></div>")
    assert out["source"] == "body"


def test_a_climb_that_reaches_a_form_control_is_abandoned(page):
    out = _generic(page, f'<div><h2>About the role</h2><p>{FILLER}</p><label>Email <input name="email"></label></div>')
    assert out["source"] == "body"
    assert not page.evaluate(DESCRIBES, out)


@pytest.mark.parametrize("chrome", ["nav", "footer", "header"])
def test_a_heading_inside_site_chrome_is_not_a_description(page, chrome):
    out = _generic(page, f"<{chrome}><h2>About the role</h2><p>{FILLER}</p></{chrome}>")
    assert out["source"] == "body"


def test_the_climb_stops_at_main_and_article(page):
    """A heading whose first long ancestor would be `<main>` is the whole page's text, and that is `page`."""
    out = _generic(page, f"<main><h2>About the role</h2><p>{FILLER}</p></main>")
    assert out["source"] == "page"
    out = _generic(page, f"<article><h2>About the role</h2><p>{FILLER}</p></article>")
    assert out["source"] == "page"


def test_a_section_under_300_characters_is_not_a_description(page):
    out = _generic(page, "<div><section><h2>About the role</h2><p>Short and sweet.</p></section></div>")
    assert out["source"] == "body"


# ---------- P2: the recorded Darwinbox page and the header lines ----------

_PREVIEW_DRIVER_JS = _PANEL_FAKES_JS + r"""
const ns = loadModules();
main(async () => {
  await settle();
  emit(ns.panel.previewFrom(spec.posting));
});
"""


def _preview(tmp_path, posting):
    return run_node(_PREVIEW_DRIVER_JS, {"posting": posting}, tmp_path, source=PANEL_SOURCE)


def _header(out):
    head = out["text"].split("\n\n", 1)[0]
    return head.split("\n") if head.startswith(("Title: ", "Company: ", "Location: ")) else []


def test_the_darwinbox_page_writes_the_header_lines_and_previewfrom_fills_the_boxes(page, tmp_path):
    out = _darwinbox(page)
    assert _header(out) == ["Title: Data Analyst", "Company: Acme Robotics",
                            "Location: Pune, Maharashtra, India"]
    assert out["source"] == "content"
    preview = _preview(tmp_path, out)
    assert (preview["title"], preview["company"], preview["location"]) == (
        "Data Analyst", "Acme Robotics", "Pune, Maharashtra, India")
    # The round trip is the identity: the description keeps its first line, header lines out of it.
    assert preview["text"].startswith("Job Description")
    assert "Title:" not in preview["text"] and "Company:" not in preview["text"]
    assert out["text"] == (
        "Title: Data Analyst\nCompany: Acme Robotics\nLocation: Pune, Maharashtra, India\n\n" + preview["text"])


@pytest.mark.parametrize("meta", ["Job Title | mainPage.companyName", "Job Title | jobDetails.page_title.x",
                                  "Careers", "Job Title | "])
def test_an_untranslated_or_missing_company_gives_no_company_line(page, meta):
    out = _darwinbox(page, meta=meta)
    assert _header(out) == ["Title: Data Analyst", "Location: Pune, Maharashtra, India"]


@pytest.mark.parametrize("url", [
    "https://acme.darwinbox.in/ms/candidatev2/main/careers/allJobs",
    "https://acme.darwinbox.in.attacker.test/ms/candidatev2/main/careers/jobDetails/a0000000000001",
    "https://notdarwinbox.in/ms/candidatev2/main/careers/jobDetails/a0000000000001",
    "https://acme.darwinbox.in/other/careers/jobDetails/a0000000000001",
])
def test_the_adapter_does_not_fire_off_a_darwinbox_job_page(page, url):
    out = _darwinbox(page, url=url)
    assert _header(out) == []
    assert out["source"] == "content"  # the heading rule still reads the description
    assert out["text"].startswith("Job Description")


def test_the_adapter_also_fires_on_the_dot_com_host(page):
    out = _darwinbox(page, url=DARWINBOX.replace("acme.darwinbox.in", "acme.darwinbox.com"))
    assert _header(out)[0] == "Title: Data Analyst"


def test_a_snapshot_location_that_is_not_shown_is_not_read(page):
    html = fixture_html("darwinbox_posting.html").replace(
        '<div class="grid-item"><div class="label">Location</div>',
        '<div class="grid-item" style="display:none"><div class="label">Location</div>')
    _open(page, DARWINBOX, html)
    assert _header(_read(page)) == ["Title: Data Analyst", "Company: Acme Robotics"]


def test_a_visible_h1_outside_site_chrome_gives_the_title(page, tmp_path):
    out = _generic(page, f"<div><h1>  Data   Analyst </h1><div><h2>About the role</h2><p>{FILLER}</p></div></div>")
    assert _header(out) == ["Title: Data Analyst"]
    assert _preview(tmp_path, out)["title"] == "Data Analyst"


def test_the_adapters_title_beats_the_h1(page):
    html = fixture_html("darwinbox_posting.html").replace(
        '<div class="navigation">', '<h1>Careers at Acme</h1><div class="navigation">')
    _open(page, DARWINBOX, html)
    assert _header(_read(page))[0] == "Title: Data Analyst"


@pytest.mark.parametrize("chrome", ["header", "nav", "footer"])
def test_an_h1_inside_site_chrome_is_not_a_title(page, chrome):
    out = _generic(page, f"<{chrome}><h1>Acme Careers</h1></{chrome}><div><h2>About the role</h2><p>{FILLER}</p></div>")
    assert out["source"] == "content"
    assert _header(out) == []


def test_a_hidden_h1_and_an_h1_on_a_page_that_is_not_a_posting_give_no_title(page):
    out = _generic(page, f'<h1 style="display:none">Hidden</h1><div><h2>About the role</h2><p>{FILLER}</p></div>')
    assert _header(out) == []
    out = _generic(page, f"<h1>A recipe for soup</h1><p>{FILLER}</p>")
    assert out["source"] == "body"
    assert out["text"].startswith("A recipe for soup")
    assert _header(out) == []
