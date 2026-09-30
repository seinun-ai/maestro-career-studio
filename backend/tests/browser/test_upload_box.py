"""What `detect_page` says about a page's upload boxes, in real Chromium.

The count (`fileInputs`) is what the panel's attach offer is made from. These
tests reach `detect_page` through `agent.js`'s message door, the way the panel
does, on real layout: whether a hidden file input counts depends on
`offsetWidth`/`getClientRects`, which a fake DOM does not have.
"""

import pytest

from tests.browser.conftest import EXTENSION, fixture_html
from tests.browser.test_fill_end_to_end import SOURCES


def _load(page, html):
    page.set_content(html)
    page.evaluate("""() => {
      window.chrome = window.chrome || {};
      Object.defineProperty(window.chrome, "runtime", { configurable: true, value: {
        id: "t", onMessage: { addListener: (fn) => { window.__pageListener = fn; } } } });
    }""")
    for src in SOURCES:
        page.add_script_tag(content=(EXTENSION / src).read_text(encoding="utf-8"))


def _detect(page):
    reply = page.evaluate("""() => new Promise((resolve) => {
      if (window.__pageListener({ type: "detect_page" }, { id: "t" }, resolve) !== true) resolve(null);
    })""")
    assert reply["ok"] is True, reply
    return reply["data"]


@pytest.fixture
def blank(page):
    page.set_default_timeout(20000)
    return page


def test_workdays_hidden_input_in_a_visible_uploader_is_counted(blank):
    """The CarMax report's first question: is Workday's `display:none`
    `file-upload-input-ref` counted at all? It is: the uploader around it is on
    screen, which is `attachableFileInputs`' rule for a drag-and-drop box."""
    _load(blank, fixture_html("workday_upload.html"))
    assert _detect(blank)["fileInputs"] == 1


def test_a_step_with_no_uploader_counts_none(blank):
    _load(blank, "<h3>Voluntary Disclosures</h3><label>Gender <select><option>Male</option></select></label>")
    assert _detect(blank)["fileInputs"] == 0
