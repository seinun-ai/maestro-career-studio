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


def test_the_button_never_writes_a_box_for_another_document(blank):
    """The press is the user's decision, but a cover letter box is not where the resume goes: a lone
    "Cover letter" box (or one per frame) takes nothing from the button either."""
    _load(blank, WORKDAY.replace("Resume/CV", "Cover Letter"))
    assert _attach(blank, resume_only=False) == 0
    assert oracle(blank, "files") == []


def test_the_button_still_writes_a_box_nothing_names(blank):
    """Unknown is the button's case (the user decides): only `other` and `parser` are refused."""
    _load(blank, WORKDAY.replace('<h4 id="resume-heading">Resume/CV</h4>', "")
          .replace(' aria-labelledby="resume-heading"', "")
          .replace("formField-resume", "formField-upload"))
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


# ---------- a lone required box is the resume box ----------
#
# Workday's live upload was labelled only "Upload a file (5MB max)", seven levels below the heading
# that says "resume". Nothing in reach named a document, the box read as unknown, and the run's
# attach left it alone: silently. A required box that is the page's only upload box is the resume
# box, unless its own words name another document.

ERRORS = fixture_html("workday_errors.html")


def _page_uploads(page):
    reply = page.evaluate("""() => new Promise((resolve) => {
      if (window.__pageListener({ type: "page_uploads" }, { id: "t" }, resolve) !== true) resolve(null);
    })""")
    assert reply["ok"] is True, reply
    return reply["data"]


def test_a_lone_required_box_with_no_word_of_its_own_and_a_far_heading_is_the_resume_box(blank):
    _load(blank, ERRORS)
    assert _uploads(blank) == [{"kind": "resume", "occupied": False}]
    assert _proven(_attach(blank)) == 1
    assert oracle(blank, "files") == ["Jane_Doe_Resume.pdf"]


def test_a_lone_box_that_is_not_required_but_sits_under_a_resume_heading_is_the_resume_box(blank):
    """Workday again (live check 2): the same shape without `aria-required`. The heading that says
    "Resume/CV" is seven levels up, in the box's own section, and nothing else is a field there."""
    _load(blank, ERRORS.replace('aria-required="true"', ""))
    assert _uploads(blank) == [{"kind": "resume", "occupied": False}]
    assert _proven(_attach(blank)) == 1
    assert oracle(blank, "files") == ["Jane_Doe_Resume.pdf"]


def test_a_lone_box_with_no_resume_heading_in_its_section_stays_unknown(blank):
    _load(blank, ERRORS.replace('aria-required="true"', "").replace("Resume/CV", "Documents")
          .replace("upload your resume and", "upload your"))
    assert _uploads(blank) == [{"kind": "unknown", "occupied": False}]
    assert _proven(_attach(blank)) == 0


def test_the_climb_to_a_heading_stops_at_an_ancestor_holding_another_field(blank):
    """A far heading belongs to the section it heads: past an ancestor that holds another field, it
    heads that field's section as well, and names neither."""
    _load(blank, """<form><h3>Resume</h3><div><div><div><div><div><div><div>
      <input aria-label="Name"><div class="up"><input type="file" name="upload_1"></div>
    </div></div></div></div></div></div></div></form>""")
    assert _uploads(blank)[0]["kind"] == "unknown"


def test_a_lone_required_box_labelled_cover_letter_is_not_a_resume_box(blank):
    _load(blank, ERRORS.replace("Upload a file (5MB max)</span>", "Cover letter</span>"))
    assert _uploads(blank) == [{"kind": "other", "occupied": False}]
    assert _proven(_attach(blank)) == 0
    assert oracle(blank, "files") == []


def test_a_required_box_among_several_is_not_taken_for_the_resume_box(blank):
    # Required alone names no document: the section's resume heading is taken out so only that is tested.
    two = (ERRORS.replace("Resume/CV", "Documents").replace("upload your resume and", "upload your")
           + '<div><label for="x2">Attachment</label><input type="file" id="x2"></div>')
    _load(blank, two)
    assert [box["kind"] for box in _uploads(blank)] == ["unknown", "unknown"]


def test_a_box_in_its_own_resume_section_is_a_resume_box_among_several(blank):
    two = ERRORS + '<div><label for="x2">Attachment</label><input type="file" id="x2"></div>'
    _load(blank, two)
    assert [box["kind"] for box in _uploads(blank)] == ["resume", "unknown"]


def test_page_uploads_names_each_box_in_the_pages_words_with_a_handle_and_its_state(blank):
    _load(blank, ERRORS)
    [box] = _page_uploads(blank)
    assert (box["label"], box["required"], box["occupied"], box["kind"]) == ("Upload a file (5MB max)", True, False, "resume")
    assert blank.evaluate("(t) => document.querySelector(`[data-maestro-up='${t}']`).id", box["target"]) == "upload-input"
    assert set(box) == {"label", "target", "required", "occupied", "kind"}


def test_page_uploads_marks_a_box_that_holds_a_file(blank):
    _load(blank, ERRORS)
    blank.set_input_files("#upload-input", {"name": "Old.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-1.4"})
    blank.wait_for_selector("[data-automation-id=file-upload-item]")
    assert _page_uploads(blank)[0]["occupied"] is True


def test_page_uploads_on_a_page_with_no_upload_is_empty(blank):
    _load(blank, "<h2>Questions</h2><input aria-label='City'>")
    assert _page_uploads(blank) == []


# ---------- live check 2: a box whose label sits outside its widget ----------
#
# A react-dropzone box keeps its input hidden inside a widget that prints its own "Click to upload"
# text; the box's name ("Resume *") is a sibling of the WIDGET. The field reader gives up at the
# widget's text, so the box read as unknown and not required, and the run neither wrote nor parked.

DROPZONE = """<form><div class="grp"><span class="lbl">LABEL <span>*</span></span>
  <div class="w1"><div class="w2"><div class="dz" role="presentation"><input type="file" id="dz" style="display:none">
    <p>Click to upload or drag and drop</p></div></div></div></div></form>
<script>
document.querySelector("#dz").addEventListener("change", (e) => {
  const row = document.createElement("span");
  row.textContent = [...e.target.files].map((f) => f.name).join(", ");
  e.target.parentElement.append(row);
});
</script>"""


def test_a_dropzone_labelled_outside_its_widget_is_a_required_resume_box(blank):
    _load(blank, DROPZONE.replace("LABEL", "Resume"))
    assert _uploads(blank) == [{"kind": "resume", "occupied": False}]
    [box] = _page_uploads(blank)
    assert (box["label"], box["required"], box["kind"]) == ("Resume", True, "resume")


def test_autofills_write_attaches_to_the_dropzone_box(blank):
    _load(blank, DROPZONE.replace("LABEL", "Resume"))
    assert _attach(blank) == {"written": 1, "proven": 1}
    assert _held(blank, "#dz") == ["Jane_Doe_Resume.pdf"]


def test_the_runs_targeted_write_attaches_to_the_dropzone_box(blank):
    _load(blank, DROPZONE.replace("LABEL", "Resume"))
    [box] = _page_uploads(blank)
    reply = blank.evaluate("""([b64, target]) => new Promise((resolve) => {
      const msg = { type: "attach_resume_pdf", b64, filename: "Jane_Doe_Resume.pdf", resumeOnly: true, target };
      if (window.__pageListener(msg, { id: "t" }, resolve) !== true) resolve(null);
    })""", [PDF, box["target"]])
    assert reply["data"]["written"] == 1
    assert _held(blank, "#dz") == ["Jane_Doe_Resume.pdf"]


def test_a_dropzone_labelled_cover_letter_outside_its_widget_is_another_document(blank):
    _load(blank, DROPZONE.replace("LABEL", "Cover letter"))
    assert _uploads(blank) == [{"kind": "other", "occupied": False}]
    assert _page_uploads(blank)[0]["required"] is True
    assert _proven(_attach(blank)) == 0


# ---------- live check 2: a resume box that is the site's own PARSER ----------
#
# ATS-D has two hidden inputs with one id. One is "Import Resume" in Candidate Info (the site's
# parser, which pre-fills the form from the file), the other the real "Resume Upload" section.
# A parser box is never written; of several resume-looking boxes only those whose section names a
# resume upload stay resume boxes.

TWO_RESUMES = """<form>
<section><h3>Candidate Info</h3>
  <div class="up"><button type="button">{import_text}</button>
    <input type="file" id="files_resume" style="display:none"></div></section>
<section><h3>{second_heading}</h3>
  <div class="up"><p>{second_text}</p>
    <input type="file" id="files_resume" style="display:none"></div></section></form>"""
BOTH = TWO_RESUMES.format(import_text="Import Resume", second_heading="Resume Upload", second_text="Drag your resume here")


def _held_nth(page, n):
    return page.evaluate("(n) => [...document.querySelectorAll('input[type=file]')[n].files].map((f) => f.name)", n)


def test_of_two_resume_inputs_the_import_one_is_a_parser_and_the_upload_one_a_resume(blank):
    _load(blank, BOTH)
    assert [box["kind"] for box in _uploads(blank)] == ["parser", "resume"]


@pytest.mark.parametrize("resume_only", [True, False], ids=["autofill", "button"])
def test_the_file_lands_only_in_the_real_resume_box(blank, resume_only):
    _load(blank, BOTH)
    _attach(blank, resume_only=resume_only, expect=2)
    assert _held_nth(blank, 0) == []
    assert _held_nth(blank, 1) == ["Jane_Doe_Resume.pdf"]


def test_page_uploads_reports_the_parsers_real_required_state_and_never_writes_it(blank):
    _load(blank, BOTH.replace('id="files_resume" style="display:none"></div></section>\n<section>',
                              'id="files_resume" style="display:none" required></div></section>\n<section>'))
    parser, real = _page_uploads(blank)
    # Truthful: a required parser box parks the run, naming it, so the user attaches it by hand.
    assert (parser["kind"], parser["required"]) == ("parser", True)
    assert real["kind"] == "resume"
    reply = blank.evaluate("""([b64, target]) => new Promise((resolve) => {
      const msg = { type: "attach_resume_pdf", b64, filename: "Jane_Doe_Resume.pdf", target };
      if (window.__pageListener(msg, { id: "t" }, resolve) !== true) resolve(null);
    })""", [PDF, parser["target"]])
    assert reply["data"]["written"] == 0
    assert _held_nth(blank, 0) == []


@pytest.mark.parametrize("wording", [
    "Import Resume", "Autofill with resume", "Apply with resume", "Autofill from resume",
    "Auto-fill application from CV", "Parse my resume", "Import your resume",
])
def test_a_lone_box_that_imports_parses_or_autofills_from_the_resume_is_never_written(blank, wording):
    _load(blank, f'<form><h3>Candidate Info</h3><div class="up"><button type="button">{wording}</button>'
                 f'<input type="file" id="p" style="display:none" required></div></form>')
    assert _uploads(blank) == [{"kind": "parser", "occupied": False}]
    assert _proven(_attach(blank)) == 0
    assert _proven(_attach(blank, resume_only=False, expect=1)) == 0
    assert _held(blank, "#p") == []
    [box] = _page_uploads(blank)
    assert (box["kind"], box["required"]) == ("parser", True)


@pytest.mark.parametrize("label", ["Resume (we'll use it to fill your profile)", "Upload your resume to fill in the form"])
def test_a_combined_box_that_is_the_only_resume_box_is_a_resume_box(blank, label):
    """Live ruling: one box that takes the resume AND fills from it is the resume box."""
    _load(blank, f'<form><h3>Application</h3><div class="up"><p>{label}</p>'
                 f'<input type="file" id="c" style="display:none"></div></form>')
    assert _uploads(blank) == [{"kind": "resume", "occupied": False}]
    assert _attach(blank)["written"] == 1
    assert _held(blank, "#c") == ["Jane_Doe_Resume.pdf"]


def test_a_combined_box_beside_a_separate_resume_box_is_a_parser(blank):
    _load(blank, TWO_RESUMES.format(import_text="Upload your resume to fill your profile",
                                    second_heading="Resume Upload", second_text="Drag your resume here"))
    assert [box["kind"] for box in _uploads(blank)] == ["parser", "resume"]


def test_import_from_a_cloud_drive_is_no_parser(blank):
    """"Import from" is a file source; the resume noun must be the verb's object."""
    _load(blank, '<form><h3>Application</h3><div class="up"><p>Import from Dropbox or Google Drive</p>'
                 '<p>No resume attached</p><input type="file" id="d" style="display:none"></div></form>')
    assert _uploads(blank) == [{"kind": "resume", "occupied": False}]


# Live ATS-D, re-pinned: the REAL "Resume Upload" box carries an "Import Resume" button too.
LIVE = """<form>
<section><h3>Candidate Info</h3>
  <div class="up"><p>Click Import Resume to add this information from your resume</p>
    <button type="button">Import Resume</button>
    <input type="file" id="files_resume" style="display:none"></div></section>
<section><h3>Resume Upload</h3>
  <div class="up"><span>Attachment:</span><button type="button">Import Resume</button>
    <input type="file" id="files_resume" style="display:none"></div></section>
<section><h3>Cover Letter</h3>
  <div class="up"><button type="button">Add Cover Letter</button>
    <input type="file" id="files_coverLetter" style="display:none"></div></section></form>"""


def test_a_resume_upload_section_outranks_its_buttons_import_resume(blank):
    _load(blank, LIVE)
    assert [box["kind"] for box in _uploads(blank)] == ["parser", "resume", "other"]


@pytest.mark.parametrize("resume_only", [True, False], ids=["autofill", "button"])
def test_on_the_live_shape_the_file_lands_once_in_the_resume_upload_box(blank, resume_only):
    _load(blank, LIVE)
    _attach(blank, resume_only=resume_only, expect=3)
    assert [_held_nth(blank, n) for n in (0, 1)] == [[], ["Jane_Doe_Resume.pdf"]]
    assert _held_nth(blank, 2) == []  # nor does the button write a cover letter box


@pytest.mark.parametrize("heading", ["Resume", "Resume/CV", "Attach resume"])
def test_any_plain_resume_heading_outranks_a_buttons_import_words(blank, heading):
    _load(blank, TWO_RESUMES.format(import_text="Import Resume", second_heading=heading, second_text="x")
          .replace("<h3>Candidate Info</h3>", "<h3>Candidate Info</h3><p>Autofill from resume</p>"))
    assert [box["kind"] for box in _uploads(blank)] == ["parser", "resume"]


def test_a_label_taken_from_inside_the_boxs_own_widget_is_the_uploaders_word(blank):
    """The field reader names a box by the button right beside its input; that is the uploader's text,
    not the box's own label, so a "Resume Upload" section outranks it."""
    _load(blank, '<form><h3>Resume Upload</h3><span><button type="button">Import Resume</button>'
                 '<input type="file" id="b" style="display:none"></span></form>')
    assert _uploads(blank) == [{"kind": "resume", "occupied": False}]
    assert _attach(blank)["written"] == 1


def test_a_label_inside_the_widget_still_makes_a_parser_where_no_section_names_a_resume(blank):
    _load(blank, '<form><h3>Candidate Info</h3><span><button type="button">Import Resume</button>'
                 '<input type="file" id="b" style="display:none"></span></form>')
    assert _uploads(blank) == [{"kind": "parser", "occupied": False}]


def test_a_section_that_describes_filling_from_the_resume_makes_its_box_a_parser(blank):
    _load(blank, '<form><h3>Autofill from resume</h3><div class="up"><input type="file" id="s" '
                 'style="display:none"><p>PDF only</p></div></form>')
    assert [box["kind"] for box in _uploads(blank)] == ["parser"]


def test_a_parser_worded_section_never_overrides_a_box_that_names_a_plain_resume(blank):
    _load(blank, '<form><h3>Autofill from resume</h3><div class="up"><p>Drop your resume here</p>'
                 '<input type="file" id="s" style="display:none"></div></form>')
    assert [box["kind"] for box in _uploads(blank)] == ["resume"]


# Ashby-like: an "Autofill from resume" block, then a "Resume" dropzone, no heading between them.
ASHBY = """<form><div class="autofill"><p>Autofill from resume</p>
  <div class="dz"><input type="file" id="af" style="display:none"><p>Click to upload</p></div></div>
<div class="grp"><span>Resume <span>*</span></span><div class="w1"><div class="w2"><div class="dz">
  <input type="file" id="res" style="display:none"><p>Drop file</p></div></div></div></div></form>"""


def test_a_resume_dropzone_after_an_autofill_block_is_the_resume_box(blank):
    _load(blank, ASHBY)
    assert [box["kind"] for box in _uploads(blank)] == ["parser", "resume"]
    assert _attach(blank, expect=2)["written"] == 1
    assert _held(blank, "#af") == [] and _held(blank, "#res") == ["Jane_Doe_Resume.pdf"]


def test_a_name_that_is_a_file_row_is_no_label(blank):
    """The text before a widget can be a stray file name; it is never used as the box's name."""
    _load(blank, DROPZONE.replace("LABEL", "Jane_Doe_Resume.pdf"))
    assert _page_uploads(blank)[0]["label"] == ""


def test_the_button_write_skips_a_box_whose_read_failed(blank):
    _load(blank, GREENHOUSE)
    blank.evaluate("""() => {
      const read = window.careerStudioCompanion.readField;
      window.careerStudioCompanion.readField = (el) => { if (el.id === "cover_letter") throw new Error("x"); return read(el); };
    }""")
    _attach(blank, resume_only=False, expect=2)
    assert _held(blank, "#resume") == ["Jane_Doe_Resume.pdf"]
    assert _held(blank, "#cover_letter") == []


def test_a_box_that_only_asks_for_a_resume_is_still_a_resume_box(blank):
    _load(blank, '<form><h3>Application</h3><div class="up"><p>Upload your resume (PDF)</p>'
                 '<input type="file" id="r" style="display:none"></div></form>')
    assert _uploads(blank) == [{"kind": "resume", "occupied": False}]


def test_of_several_resume_looking_boxes_only_those_in_a_resume_section_stay_resume(blank):
    _load(blank, TWO_RESUMES.format(import_text="Attach your CV", second_heading="Resume Upload",
                                    second_text="Drag your resume here"))
    assert [box["kind"] for box in _uploads(blank)] == ["unknown", "resume"]
    assert _attach(blank, expect=2)["written"] == 1
    assert _held_nth(blank, 0) == []
    assert _held_nth(blank, 1) == ["Jane_Doe_Resume.pdf"]


def test_several_resume_boxes_none_in_a_resume_section_are_all_kept(blank):
    _load(blank, TWO_RESUMES.format(import_text="Attach your CV", second_heading="Documents",
                                    second_text="Drag your resume here"))
    assert [box["kind"] for box in _uploads(blank)] == ["resume", "resume"]
    assert _attach(blank, expect=2)["written"] == 0
    assert _held_nth(blank, 0) == _held_nth(blank, 1) == []


# ---------- upload boxes in open shadow roots (live check 8) ----------
#
# A hosted one-click application draws its dropzones inside web components: the file input sits in an open shadow root, the
# parser's "fill this form from your resume" box is in the vendor's easy-apply container and the real resume box in its
# resume-upload container. Both are found through the shadow roots; the parser box is never written.

SHADOW = fixture_html("shadow_one_page_form.html")


def _shadow_files(page, fid):
    return page.evaluate("(fid) => [...document.querySelector(`acme-dropzone[fid=${fid}]`).shadowRoot"
                         ".querySelector('input').files].map((f) => f.name)", fid)


def test_dropzones_in_shadow_roots_are_counted_and_the_vendors_easy_apply_box_is_a_parser(blank):
    _load(blank, SHADOW)
    detected = _detect(blank)
    assert detected["fileInputs"] == 2
    assert [box["kind"] for box in detected["uploads"]] == ["parser", "resume"]


def test_the_markers_alone_name_the_boxes_whatever_the_page_says_around_them(blank):
    _load(blank, SHADOW.replace("<h2>Easy Apply</h2>", "<h2>Quick start</h2>").replace("<h2>Resume</h2>", "<h2>Your documents</h2>")
          .replace("Upload your resume to fill in the form automatically", "Choose a file"))
    assert [box["kind"] for box in _uploads(blank)] == ["parser", "resume"]


def test_a_resume_box_in_the_vendors_resume_container_is_the_resume_even_beside_an_unnamed_neighbour(blank):
    _load(blank, SHADOW.replace('<oc-easy-apply>', "<div>").replace("</oc-easy-apply>", "</div>")
          .replace(' data-test="easy-apply-container"', "").replace("<h2>Easy Apply</h2>", "<h2>Quick start</h2>")
          .replace("Upload your resume to fill in the form automatically", "Choose a file"))
    assert [box["kind"] for box in _uploads(blank)] == ["unknown", "resume"]


def test_the_resume_only_write_attaches_to_the_shadow_resume_box_and_never_to_the_parser(blank):
    _load(blank, SHADOW)
    assert _attach(blank, expect=2) == {"written": 1, "proven": 1}
    assert _shadow_files(blank, "resume") == ["Jane_Doe_Resume.pdf"]
    assert _shadow_files(blank, "parser") == []
    assert oracle(blank, "shadow_files") == [["resume", "Jane_Doe_Resume.pdf"]]


def test_the_button_write_skips_the_parser_box_too(blank):
    _load(blank, SHADOW)
    assert _proven(_attach(blank, resume_only=False, expect=2)) == 1
    assert _shadow_files(blank, "parser") == []
    assert _shadow_files(blank, "resume") == ["Jane_Doe_Resume.pdf"]


def test_a_shadow_resume_box_that_already_shows_its_file_is_occupied_and_not_written_again(blank):
    _load(blank, SHADOW)
    blank.set_input_files("acme-dropzone[fid=resume] input", {"name": "Old_Resume.pdf", "mimeType": "application/pdf",
                                                              "buffer": b"%PDF-1.4"})
    assert [box["occupied"] for box in _uploads(blank)] == [False, True]
    assert _attach(blank, expect=2) == {"written": 0, "proven": 0}
    assert _shadow_files(blank, "resume") == ["Old_Resume.pdf"]


def test_the_panels_detect_answer_for_a_shadow_form_says_form_and_counts_its_fields(blank):
    """What the panel's `hasForm` is made from (`detect_page`): a form, the fields the page has, the two boxes."""
    _load(blank, SHADOW)
    detected = _detect(blank)
    assert (detected["form"], detected["tier"], detected["controls"], detected["fileInputs"]) == (True, "B", 9, 2)


def test_a_shadow_dropzone_named_by_a_label_in_its_own_shadow_root_is_that_documents_box(blank):
    """`aria-labelledby` names an element in the input's own tree: looked up in the document alone it named nothing."""
    _load(blank, '<script>customElements.define("x-drop", class extends HTMLElement { connectedCallback() {'
                 'this.attachShadow({mode: "open"}).innerHTML = this.getAttribute("tpl"); } });</script>'
                 '<main><x-drop tpl=\'<span id="lbl">Cover letter</span><div><input type="file" aria-labelledby="lbl" style="opacity:0;width:1px;height:1px"></div>\'></x-drop></main>')
    assert [box["kind"] for box in _uploads(blank)] == ["other"]


# A component that takes the file, empties its own input and shows the file's name in a row INSIDE its shadow root (Workday's
# uploader does this in the light DOM): the row is the only proof the file went in, and it is in text no textContent reads.
CLEARING = SHADOW.replace('<acme-dropzone fid="resume">', '<acme-dropzone fid="resume" hidden-input clears required>')


def test_a_shadow_uploader_that_empties_its_input_and_shows_a_row_in_its_shadow_root_is_written_and_proven(blank):
    _load(blank, CLEARING)
    assert _attach(blank, expect=2) == {"written": 1, "proven": 1}
    assert oracle(blank, "shadow_files") == [["resume", "Jane_Doe_Resume.pdf"]]


def test_the_row_in_the_shadow_root_makes_the_box_occupied_and_no_longer_a_required_empty(blank):
    _load(blank, CLEARING)
    assert [box["occupied"] for box in _uploads(blank)] == [False, False]
    assert blank.evaluate("() => window.careerStudioCompanion.pageReader.summary().requiredEmpty") == 7   # six fields and the box
    _attach(blank, expect=2)
    assert [box["occupied"] for box in _uploads(blank)] == [False, True]
    assert blank.evaluate("() => window.careerStudioCompanion.pageReader.summary().requiredEmpty") == 6


def test_an_error_the_shadow_uploader_prints_beside_its_row_voids_the_proof(blank):
    """The row proof is a difference with no new error: an error inside the shadow root counts, as it does in the light DOM."""
    _load(blank, CLEARING.replace('row.textContent = f.name;', 'row.textContent = f.name + " could not be uploaded";'))
    assert _attach(blank, expect=2) == {"written": 1, "proven": 0}
