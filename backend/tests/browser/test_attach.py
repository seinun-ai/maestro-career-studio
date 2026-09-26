"""Attach resume, on a page that uploads the way live Workday does (notes §7).

Workday takes the file — "Successfully Uploaded!" and a row naming it — and
empties `input.files` in the same tick, so a readback of `files` alone reports
"No upload box took the file" over a page where it worked. The proof is the
page's own file row: a NEW element naming the file inside this input's upload
widget. These tests drive the real content scripts in the manifest's order and
reach `attachResumePdf` through `agent.js`'s message door (`PAGE_HANDLERS`, via
the captured `window.__pageListener`), as the panel's fan-out does.

The refusal variants stop the fixture's own change handler at the window, in
capture, so the page can answer the write its own way: nothing at all, an
error, or a row it takes back.
"""

import base64

import pytest

from tests.browser.conftest import EXTENSION, fixture_html
from tests.browser.pages import oracle
from tests.browser.test_fill_end_to_end import SOURCES

NAME = "Jane_Doe_Resume.pdf"
PDF = base64.b64encode(b"%PDF-1.4\n%%EOF\n").decode()
INPUT = "[data-automation-id=file-upload-input-ref]"
ROW = "[data-automation-id=file-upload-item]"

# The page refuses: the change never reaches the uploader, the input is
# emptied as Workday empties it, and `then` (a function body, `widget` in
# scope) is what the page shows instead, 200 ms later like the real row.
REFUSE = """(then) => {
  window.addEventListener("change", (e) => {
    if (!e.target.matches?.('[data-automation-id="file-upload-input-ref"]')) return;
    e.stopImmediatePropagation();
    e.target.value = "";
    const widget = e.target.closest('[data-automation-id="attachments-FileUpload"]');
    setTimeout(() => new Function("widget", then)(widget), 200);
  }, true);
}"""


def _load(page, html):
    page.set_content(html)
    page.evaluate("""() => {
      window.chrome = window.chrome || {};
      Object.defineProperty(window.chrome, "runtime", { configurable: true, value: {
        id: "t", onMessage: { addListener: (fn) => { window.__pageListener = fn; } } } });
    }""")
    for src in SOURCES:
        page.add_script_tag(content=(EXTENSION / src).read_text(encoding="utf-8"))
    assert page.evaluate("typeof window.__pageListener") == "function"


def _attach(page, expect=1, name=NAME):
    """The panel's press, through the real handler: the frame's reply."""
    return page.evaluate("""([b64, filename, expect]) => new Promise((resolve) => {
      const msg = { type: "attach_resume_pdf", b64, filename, ...(expect === null ? {} : { expect }) };
      if (window.__pageListener(msg, { id: "t" }, resolve) !== true) resolve(null);
    })""", [PDF, name, expect])


def _seed_previous_upload(page):
    """A résumé of the same name already uploaded, by hand, before the press."""
    page.set_input_files(INPUT, {"name": NAME, "mimeType": "application/pdf", "buffer": b"%PDF-1.4"})
    page.wait_for_selector(ROW)
    assert oracle(page, "files") == [NAME]


@pytest.fixture
def upload_page(page):
    page.set_default_timeout(20000)
    _load(page, fixture_html("workday_upload.html"))
    return page


def test_an_upload_the_page_accepted_counts_even_after_it_cleared_its_input(upload_page):
    page = upload_page
    assert _attach(page) == {"ok": True, "data": 1}
    assert oracle(page, "files") == [NAME]
    # The input the old readback trusted is empty: the row is what counted.
    assert page.evaluate(f"document.querySelector('{INPUT}').files.length") == 0
    assert page.inner_text("[data-automation-id=file-upload-item-name]") == NAME


def test_an_upload_the_page_refused_still_counts_zero(upload_page):
    """No row, an emptied input: nothing proves the write, and the panel keeps
    its honest "No upload box took the file"."""
    page = upload_page
    page.evaluate(REFUSE, "")
    assert _attach(page) == {"ok": True, "data": 0}
    assert oracle(page, "files") == []


def test_an_error_naming_the_file_is_not_a_row(upload_page):
    """An error sentence carries the filename too. A NEW error in the widget
    voids the row proof, so "resume.pdf could not be uploaded" is not read as
    the page holding resume.pdf."""
    page = upload_page
    page.evaluate(REFUSE, f"""const p = document.createElement("p");
      p.setAttribute("role", "alert");
      p.textContent = "{NAME} could not be uploaded. Try again.";
      widget.append(p);""")
    assert _attach(page) == {"ok": True, "data": 0}
    # The error did show, naming the file, before the count was taken.
    assert NAME in page.inner_text("[data-automation-id=attachments-FileUpload] [role=alert]")


def test_a_row_the_page_takes_back_counts_zero(upload_page):
    """The page shows the row and then withdraws it for an error: the proof
    has to still hold when the count is taken, not merely have flickered."""
    page = upload_page
    page.evaluate("""() => {
      const input = document.querySelector('[data-automation-id="file-upload-input-ref"]');
      input.addEventListener("change", () => setTimeout(() => {
        document.getElementById("uploaded").replaceChildren();
        const p = document.createElement("p");
        p.textContent = "Upload failed.";
        document.getElementById("uploaded").append(p);
      }, 400));
    }""")
    assert _attach(page) == {"ok": True, "data": 0}


def test_a_row_already_there_is_not_proof_of_this_write(upload_page):
    """The same résumé uploaded before the press shows the same name. That row
    says nothing about THIS write, so a page that takes the file silently
    (no new row, emptied input) counts zero — the user sees the earlier row and
    is told to check, the safe direction."""
    page = upload_page
    _seed_previous_upload(page)
    page.evaluate(REFUSE, "")
    assert _attach(page) == {"ok": True, "data": 0}
    assert page.locator(ROW).count() == 1


def test_a_second_row_for_the_same_name_is_proof(upload_page):
    """Workday's uploader is `multiple`: the same file again adds a row. The
    proof is MORE rows naming the file than before the write."""
    page = upload_page
    _seed_previous_upload(page)
    assert _attach(page) == {"ok": True, "data": 1}
    assert oracle(page, "files") == [NAME, NAME]


def test_a_row_in_another_uploader_does_not_prove_this_ones_write(page):
    """The widget is this input's alone: the climb stops below an ancestor that
    holds another file input, so the cover-letter box's row cannot vouch for
    the résumé box. Unchecked (`expect` absent) so both boxes are written."""
    page.set_default_timeout(20000)
    _load(page, """
      <section>
        <div id="resume-box"><p>Resume</p><input type="file" id="resume" style="display:none"></div>
        <div id="cover-box"><p>Cover letter</p><input type="file" id="cover"><div id="cover-rows"></div></div>
      </section>
      <script>
        // The résumé box empties itself and (wrongly) lists the file under the
        // cover letter; the cover box keeps its file like a plain input.
        document.getElementById("resume").addEventListener("change", (e) => {
          const names = [...e.target.files].map((f) => f.name);
          e.target.value = "";
          setTimeout(() => { for (const n of names) {
            const d = document.createElement("div"); d.textContent = n;
            document.getElementById("cover-rows").append(d);
          } }, 200);
        });
      </script>""")
    assert _attach(page, expect=None) == {"ok": True, "data": 1}
    assert page.evaluate("document.getElementById('cover').files.length") == 1


def test_an_input_the_page_re_rendered_counts_by_its_row(upload_page):
    """A DETACHED input counts only by its widget's row. Workday may replace its
    own input after taking the file; the old node's `files` is no evidence, but
    a new row naming the file in the (still connected) widget is."""
    page = upload_page
    page.evaluate("""() => {
      const input = document.querySelector('[data-automation-id="file-upload-input-ref"]');
      input.addEventListener("change", () => input.replaceWith(input.cloneNode()));
    }""")
    assert _attach(page) == {"ok": True, "data": 1}
    assert oracle(page, "files") == [NAME]
