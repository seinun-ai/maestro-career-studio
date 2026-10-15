"""Web-component application pages (live check 8, 2026-10-15): native controls inside OPEN shadow roots.

`fixtures/browser/shadow_one_page_form.html` models a hosted one-click application whose every input, textarea, file input and
button lives in an open shadow root, whose button labels are slotted text, and which has no <form>. The fill inventory
already walked those roots; the page reader and the fillable count did not, so the page read as "nothing here" and the run
parked on "Page not recognised". These tests drive the REAL page reader on that page, one behaviour each. The Submit rule
is the one that matters most: a Submit read through a slot sorts as a Submit, and the reader's press refuses it.
"""

import json

import pytest

from tests.browser.conftest import EXTENSION, fixture_html
from tests.browser.test_page_reader import SOURCES, READER, advance, button, classify, summary

SHADOW = fixture_html("shadow_one_page_form.html")
FILLABLE = "window.careerStudioCompanion.fillableControls()"


def fill(page, fid, value):
    page.locator(f"acme-input[fid={fid}] input, acme-input[fid={fid}] textarea").fill(value)


def submits(page):
    return page.evaluate("() => window.__oracle.shadow_submits")


def test_the_fields_in_open_shadow_roots_are_fillable_controls(page, load):
    load(page, SHADOW, SOURCES)
    s = summary(page)
    assert s["fillable"] == page.evaluate(FILLABLE) == 9   # six personal boxes, the message, the parser's and the resume's file input


def test_a_shadow_buttons_slotted_label_is_what_it_shows_and_the_page_reads_as_a_review_page_with_a_submit(page, load):
    load(page, SHADOW, SOURCES)
    s = summary(page)
    assert button(s, "Submit")["inForm"] is True and s["submitSeen"] is True
    verdict = classify(page)
    assert (verdict["kind"], verdict.get("by")) == ("review", "submit_button")


def test_required_shadow_boxes_are_counted_and_the_count_drops_as_they_are_filled(page, load):
    load(page, SHADOW, SOURCES)
    assert summary(page)["requiredEmpty"] == 6
    fill(page, "first", "Sam")
    fill(page, "city", "Springfield")
    s = summary(page)
    assert s["requiredEmpty"] == 4
    assert "Sam" not in json.dumps(s) and "Springfield" not in json.dumps(s)
    items = page.evaluate(f"() => {READER}.pageRequired().items")
    assert [i["label"] for i in items] == ["Last name", "Email", "Confirm your email", "Phone number"]


def test_the_parser_box_and_the_optional_boxes_are_never_owed_an_answer(page, load):
    load(page, SHADOW, SOURCES)
    labels = [i["label"] for i in page.evaluate(f"() => {READER}.pageRequired().items")]
    assert "Let the company know about your interest working there" not in labels and len(labels) == 6


def test_a_shadow_box_the_page_marks_invalid_is_an_error_the_run_can_name(page, load):
    load(page, SHADOW, SOURCES)
    page.evaluate("() => document.querySelector('acme-input[fid=email]').shadowRoot.querySelector('input').setAttribute('aria-invalid', 'true')")
    assert summary(page)["errors"] == 1
    errors = page.evaluate(f"() => {READER}.pageErrors()")
    assert [(i["label"], i["kind"]) for i in errors["items"]] == [("Email", "field")]
    assert errors["items"][0]["target"]   # the handle a later fill finds the box by


def test_the_shadow_submit_is_never_pressed_whatever_the_reader_is_told(page, load):
    load(page, SHADOW, SOURCES)
    submit = button(summary(page), "Submit")["id"]
    assert advance(page, submit) == {"clicked": False, "why": "submit"}
    assert submits(page) == 0


def test_a_shadow_button_relabelled_to_a_submit_after_the_read_is_refused(page, load):
    load(page, SHADOW.replace("<acme-button submit>Submit</acme-button>", "<acme-button>Continue</acme-button>"), SOURCES)
    assert classify(page)["kind"] == "form_step"
    nxt = button(summary(page), "Continue")["id"]
    page.evaluate("() => { document.querySelector('acme-button').textContent = 'Submit application'; }")
    assert advance(page, nxt) == {"clicked": False, "why": "submit"}
    assert page.evaluate("() => window.__oracle.shadow_nexts") == 0


def test_a_shadow_next_is_pressed(page, load):
    load(page, SHADOW.replace("<acme-button submit>Submit</acme-button>", "<acme-button>Next</acme-button>"), SOURCES)
    verdict = classify(page)   # re-tags every button: the id it offers is the live one
    assert verdict["kind"] == "form_step" and summary(page)["submitSeen"] is False
    assert advance(page, button(summary(page), "Next")["id"]) == {"clicked": True}
    assert page.evaluate("() => window.__oracle.shadow_nexts") == 1


def test_a_shadow_button_in_the_sites_header_is_site_chrome_and_one_in_a_dialog_is_an_overlay(page, load):
    load(page, SHADOW.replace("<main>", "<header><acme-button>Continue</acme-button></header>"
                              '<div role="dialog" aria-modal="true"><p>Saved.</p><acme-button>Close</acme-button></div><main>'), SOURCES)
    s = summary(page)
    assert button(s, "Continue").get("chrome") is True
    assert button(s, "Close").get("overlay") is True


def test_a_page_with_no_shadow_roots_reads_as_before(page, load):
    load(page, "<form><label>Name <input name='n'></label><button>Next</button></form>", SOURCES)
    s = summary(page)
    assert (s["fillable"], s["submitSeen"]) == (1, False) and classify(page)["kind"] == "form_step"


def shadow_page(body):
    """The fixture's components, with `body` as the page."""
    return SHADOW.split('<button id="cookie">')[0] + body + "</body></html>"


def test_a_component_marked_as_a_submit_makes_its_inner_button_one(page, load):
    load(page, shadow_page('<main><acme-button id="submit-application">Go</acme-button>'
                           '<acme-button aria-label="Submit application">Go</acme-button></main>'), SOURCES)
    s = summary(page)
    assert s["submitSeen"] is True
    for b in s["buttons"]:
        assert advance(page, b["id"]) == {"clicked": False, "why": "submit"}
    assert page.evaluate("() => window.__oracle.shadow_nexts") == 0


def test_a_shadow_sign_in_page_is_a_sign_in_page_and_the_saved_login_is_typed_into_its_boxes(page):
    from tests.browser.test_page_reader import LOGIN, serve
    serve(page, "https://x.test/signin", shadow_page(
        '<main><h1>Sign in</h1><acme-input fid="user" label="Email" type="email"></acme-input>'
        '<acme-input fid="pw" label="Password" type="password"></acme-input><acme-button>Sign in</acme-button></main>'))
    assert (classify(page)["kind"], summary(page)["passwordInputs"]) == ("sign_in", 1)
    assert page.evaluate(f"(a) => {READER}.signIn(a)", LOGIN) == {"signedIn": "clicked"}
    assert page.input_value("acme-input[fid=user] input") == LOGIN["email"]
    assert page.evaluate("() => window.__oracle.shadow_nexts") == 1


# ---------- the two counts of a page's fields (owner's rule, live check 8) ----------
#
# The reader's `fillable` (content/detect.js `fillableControls`) and the fill inventory's own list are two walks of the page.
# They differ by design on a few shapes (a search box is listed but is no field of an application; a file input is counted
# but the fill never types into it), so what is pinned is the thing that failed live: a shadow root must not change what either
# of them says about a control. The run's guard for any other disagreement is the driver's, in test_extension_queue_run.py.

COUNTS = """async () => {
  const ns = window.careerStudioCompanion;
  const inventory = await ns.fillOps.inventory({ readOnly: true, consentForms: false, runId: "r" });
  return [ns.fillableControls(), inventory.fields.length, ns.pageReader.summary().requiredEmpty];
}"""

SNIPPETS = {
    "text": "<label>Name <input name=n></label>",
    "textarea": "<label>Why <textarea></textarea></label>",
    "select": "<label>Pick <select><option>a</option><option>b</option></select></label>",
    "checkbox": "<label><input type=checkbox> I agree</label>",
    "radios": "<fieldset><legend>Authorized?</legend><label><input type=radio name=a> Yes</label><label><input type=radio name=a> No</label></fieldset>",
    "search": "<input type=search name=q aria-label=Search>",
    "upload": "<label>Resume <input type=file name=resume></label>",
    "popup": "<fieldset><legend>Degree</legend><button type=button aria-haspopup=listbox aria-label=' Select One Required'>Select One</button></fieldset>",
    "pills": "<div role=group aria-label='Authorized to work?'><button type=button aria-pressed=false>Yes</button><button type=button aria-pressed=false>No</button></div>",
    "combobox": "<label>City <input role=combobox aria-expanded=false name=city></label>",
    "nothing": "<p>Hello</p>",
}


@pytest.mark.parametrize("name", list(SNIPPETS))
def test_a_shadow_root_changes_neither_count_of_a_control_it_holds(page, load, name):
    load(page, f"<main>{SNIPPETS[name]}</main>", SOURCES)
    in_the_light = page.evaluate(COUNTS)
    load(page, "<main><div id=host></div></main>", SOURCES)
    page.evaluate("(html) => { document.getElementById('host').attachShadow({ mode: 'open' }).innerHTML = html; }", SNIPPETS[name])
    assert page.evaluate(COUNTS) == in_the_light


def test_the_fillable_count_is_above_zero_exactly_when_the_inventory_lists_a_field_on_the_shadow_page(page, load):
    load(page, SHADOW, SOURCES)
    fillable, listed, _ = page.evaluate(COUNTS)
    assert listed == 7 and fillable == listed + 2   # the fields, and the two file inputs the count includes and the fill never types into
    load(page, shadow_page('<main><acme-button>Next</acme-button></main>'), SOURCES)
    assert page.evaluate(COUNTS)[:2] == [0, 0]


# ---------- page detection (the panel's `hasForm`) ----------

DETECT = "() => window.careerStudioCompanion.detectPage()"


def test_page_detection_sees_the_application_form_a_page_of_shadow_components_holds(page, load):
    """The panel withholds a manual Autofill on a page whose detection says there is no form; detection read only the light
    DOM, where this page has none of the file input, the name boxes or the email and phone boxes it scores on."""
    load(page, SHADOW, SOURCES)
    verdict = page.evaluate(DETECT)
    assert verdict["form"] is True and verdict["tier"] == "B"
    assert {"resume-input", "identity-cluster"} <= set(verdict["signals"])


def test_a_lone_email_box_in_a_shadow_root_is_still_no_form(page, load):
    """The gate's own rule holds in the roots: a newsletter component is one field, and three different identity fields are the floor."""
    load(page, shadow_page('<main><acme-input fid="news" label="Email" type="email"></acme-input></main>'), SOURCES)
    verdict = page.evaluate(DETECT)
    assert (verdict["form"], verdict["score"]) == (False, 0)


def test_a_page_with_no_shadow_roots_is_detected_as_before(page, load):
    load(page, "<form id='application_form'><input type='file' name='resume'><input name='first_name'><input name='last_name'>"
               "<input type='email'></form>", SOURCES)
    verdict = page.evaluate(DETECT)
    assert verdict["form"] is True and "ats-dom-marker" in verdict["signals"]
