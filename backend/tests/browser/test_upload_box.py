"""What `detect_page` says about a page's upload boxes, in real Chromium.

The count (`fileInputs`) is what the panel's attach offer is made from. These
tests reach `detect_page` through `agent.js`'s message door, the way the panel
does, on real layout: whether a hidden file input counts depends on
`offsetWidth`/`getClientRects`, which a fake DOM does not have.
"""

import pytest

from tests.browser.conftest import EXTENSION, fixture_html
from tests.browser.pages import oracle
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


# ---------- what kind of box it is, and whether it already holds a file ----------
#
# `uploads` rides the same detect answer: one `{kind, occupied}` per counted
# box, which is what Autofill's own attach decides with. `kind` is "resume",
# "other" or "unknown", from the box's OWN label first (the field reader's
# question, its aria labels, its name and id), then its uploader's text, then
# its section heading. `occupied` is any file row already in the uploader.

WORKDAY = fixture_html("workday_upload.html")
# A Greenhouse-shaped form: one section, two boxes, each labelled, each
# printing the chosen file's name beside it as the live board does.
GREENHOUSE = """<h2>Apply for this job</h2><form>
  <div><label for="resume">Resume/CV</label><input type="file" id="resume" name="resume"></div>
  <div><label for="cover_letter">Cover Letter</label>
       <input type="file" id="cover_letter" name="cover_letter"></div></form>
<script>
for (const input of document.querySelectorAll("input[type=file]")) {
  input.addEventListener("change", () => {
    const row = document.createElement("span");
    row.textContent = [...input.files].map((f) => f.name).join(", ");
    input.parentElement.append(row);
  });
}
</script>"""
# A drag-and-drop uploader that keeps the file in its HIDDEN input and never
# prints a row: the page has not shown that it took anything.
SILENT = """<h4>Resume</h4><div class="uploader"><p>Drop a file here</p>
  <input type="file" name="resume" style="display:none"></div>"""
# A visible native file input in a wrapper: the browser's own control shows
# the chosen file, so holding it is the proof.
NATIVE = """<h4>Resume</h4><div class="field"><p>PDF only</p>
  <input type="file" name="resume"></div>"""
# A bare input straight in a form: holding the file IS the upload.
BARE = """<form><input type="file" name="resume"></form>"""
PDF = "JVBERi0xLjQKJSVFT0YK"  # %PDF-1.4 %%EOF


def _uploads(page):
    return _detect(page)["uploads"]


def _attach(page, resume_only=True, expect=1):
    reply = page.evaluate("""([b64, expect, resumeOnly]) => new Promise((resolve) => {
      const msg = { type: "attach_resume_pdf", b64, filename: "Jane_Doe_Resume.pdf", expect, resumeOnly };
      if (window.__pageListener(msg, { id: "t" }, resolve) !== true) resolve(null);
    })""", [PDF, expect, resume_only])
    assert reply["ok"] is True, reply
    return reply["data"]


def _proven(reply):
    """How many boxes the resume-only write proved: it answers
    `{written, proven}`, the button's write a bare count."""
    return reply["proven"] if isinstance(reply, dict) else reply


def test_workdays_resume_cv_box_is_a_resume_box_and_empty(blank):
    _load(blank, WORKDAY)
    assert _uploads(blank) == [{"kind": "resume", "occupied": False}]


def test_a_box_that_already_lists_a_file_is_occupied(blank):
    _load(blank, WORKDAY)
    blank.set_input_files("[data-automation-id=file-upload-input-ref]",
                          {"name": "Old_Resume.pdf", "mimeType": "application/pdf",
                           "buffer": b"%PDF-1.4"})
    blank.wait_for_selector("[data-automation-id=file-upload-item]")
    assert _uploads(blank) == [{"kind": "resume", "occupied": True}]


def test_standing_help_text_naming_file_types_is_not_a_file(blank):
    _load(blank, WORKDAY.replace("<p>Drop file here</p>",
                                 "<p>Drop file here (.pdf, .docx, 5MB max)</p>"))
    assert _uploads(blank) == [{"kind": "resume", "occupied": False}]


@pytest.mark.parametrize("heading", ["Cover Letter", "Additional Documents", "Transcript"])
def test_a_box_for_another_document_is_other(blank, heading):
    _load(blank, WORKDAY.replace("Resume/CV", heading))
    assert _uploads(blank) == [{"kind": "other", "occupied": False}]


def test_a_box_whose_label_names_both_is_not_a_resume_box(blank):
    _load(blank, WORKDAY.replace("Resume/CV", "Resume or cover letter"))
    assert _uploads(blank)[0]["kind"] == "other"


def test_a_box_nothing_names_is_unknown(blank):
    _load(blank, WORKDAY.replace('<h4 id="resume-heading">Resume/CV</h4>', "")
          .replace(' aria-labelledby="resume-heading"', "")
          .replace("formField-resume", "formField-upload"))
    assert _uploads(blank)[0]["kind"] == "unknown"


def test_the_uploaders_automation_id_names_it(blank):
    """Workday's field wrapper (`formField-resume`) is the box's own name."""
    _load(blank, WORKDAY.replace('<h4 id="resume-heading">Resume/CV</h4>', "")
          .replace(' aria-labelledby="resume-heading"', ""))
    assert _uploads(blank)[0]["kind"] == "resume"


def test_the_boxes_own_label_outranks_its_section(blank):
    _load(blank, GREENHOUSE)
    assert [box["kind"] for box in _uploads(blank)] == ["resume", "other"]


def _held(page, selector):
    return page.evaluate("(s) => [...document.querySelector(s).files].map((f) => f.name)", selector)


def test_beside_a_cover_letter_box_only_the_resume_box_is_written(blank):
    _load(blank, GREENHOUSE)
    assert _attach(blank, expect=2) == {"written": 1, "proven": 1}
    assert _held(blank, "#resume") == ["Jane_Doe_Resume.pdf"]
    assert _held(blank, "#cover_letter") == []


def test_two_boxes_neither_named_a_resume_box_take_nothing(blank):
    _load(blank, GREENHOUSE.replace("Resume/CV", "Portfolio"))
    assert _attach(blank, expect=2) == {"written": 0, "proven": 0}
    assert _held(blank, "#resume") == []


def test_a_box_named_only_by_its_attributes_is_read_by_them(blank):
    _load(blank, '<div><input type="file" name="candidate_cv"></div>')
    assert _uploads(blank)[0]["kind"] == "resume"


def test_the_resume_only_write_attaches_to_an_empty_resume_box(blank):
    _load(blank, WORKDAY)
    assert _attach(blank) == {"written": 1, "proven": 1}
    assert oracle(blank, "files") == ["Jane_Doe_Resume.pdf"]


def test_the_resume_only_write_never_replaces_a_listed_file(blank):
    _load(blank, WORKDAY)
    blank.set_input_files("[data-automation-id=file-upload-input-ref]",
                          {"name": "Old_Resume.pdf", "mimeType": "application/pdf",
                           "buffer": b"%PDF-1.4"})
    blank.wait_for_selector("[data-automation-id=file-upload-item]")
    assert _attach(blank) == {"written": 0, "proven": 0}
    assert oracle(blank, "files") == ["Old_Resume.pdf"]


def test_the_resume_only_write_never_touches_a_cover_letter_box(blank):
    _load(blank, WORKDAY.replace("Resume/CV", "Cover Letter"))
    assert _attach(blank) == {"written": 0, "proven": 0}
    assert oracle(blank, "files") == []


def test_the_button_write_is_unchanged_by_the_kind(blank):
    """The press is the user's decision: the button's write reads no kind."""
    _load(blank, WORKDAY.replace("Resume/CV", "Cover Letter"))
    assert _attach(blank, resume_only=False) == 1


# ---------- review round: what counts as a file, a proof, a word ----------

@pytest.mark.parametrize("name", ["Resume (1).pdf", "Resume_(final).pdf", "résumé(1).pdf"])
def test_a_listed_file_whose_name_has_brackets_is_a_file(blank, name):
    """"Resume (1).pdf" is the browser's own name for a second download."""
    _load(blank, WORKDAY)
    blank.set_input_files("[data-automation-id=file-upload-input-ref]",
                          {"name": name, "mimeType": "application/pdf", "buffer": b"%PDF-1.4"})
    blank.wait_for_selector("[data-automation-id=file-upload-item]")
    assert _uploads(blank) == [{"kind": "resume", "occupied": True}]
    assert _attach(blank) == {"written": 0, "proven": 0}
    assert oracle(blank, "files") == [name]


@pytest.mark.parametrize("control", [
    '<button type="button">Remove</button>',
    '<span role="button" aria-label="Delete file">×</span>',
    '<button type="button">Replace</button>',
])
def test_a_row_holding_only_a_remove_control_is_a_file(blank, control):
    _load(blank, WORKDAY.replace('<div id="uploaded"></div>', f'<div id="uploaded">{control}</div>'))
    assert _uploads(blank) == [{"kind": "resume", "occupied": True}]


def test_a_file_held_but_never_shown_is_not_proof_for_autofill(blank):
    """An uploader with its own widget must SHOW the file: holding it in the
    input says nothing about whether the page took it."""
    _load(blank, SILENT)
    assert _attach(blank) == {"written": 1, "proven": 0}


def test_the_button_write_still_counts_a_held_file(blank):
    _load(blank, SILENT)
    assert _attach(blank, resume_only=False) == 1


def test_a_visible_native_input_in_a_wrapper_holding_the_file_is_the_upload(blank):
    _load(blank, NATIVE)
    assert _attach(blank) == {"written": 1, "proven": 1}


def test_a_bare_input_holding_the_file_is_the_upload(blank):
    _load(blank, BARE)
    assert _attach(blank) == {"written": 1, "proven": 1}


@pytest.mark.parametrize("heading", ["Résumé", "resumé", "Upload your Résumé"])
def test_accented_resume_words_name_a_resume_box(blank, heading):
    # The wrapper's automation id would name it on its own: renamed away.
    _load(blank, WORKDAY.replace("Resume/CV", heading).replace("formField-resume", "formField-x"))
    assert _uploads(blank)[0]["kind"] == "resume"


def test_the_postings_title_never_names_a_box(blank):
    """A posting's h1 is the page's title, not the uploader's section."""
    _load(blank, """<h1>Computer Vision (CV) Engineer</h1><main><form>
      <div class="field"><input type="file" name="upload_1"></div></form></main>""")
    assert _uploads(blank)[0]["kind"] == "unknown"


def test_a_heading_outside_the_uploaders_form_never_names_it(blank):
    _load(blank, """<h2>Resume tips</h2><form>
      <div class="field"><input type="file" name="upload_1"></div></form>""")
    assert _uploads(blank)[0]["kind"] == "unknown"
