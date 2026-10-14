"""The page reader (queued-run plan Task 13): DOM in, a plain summary out; and the one click.

`content/page-reader.js` turns the page into the summary `shared/page-kind.js` classifies, and
`advance(id)` is the ONLY place in the extension that presses a navigation button. THE ONE RULE
these tests hold: a button carrying a Submit word is never clicked through it, at any wording, any
element type, any label source, and any id (including a stale one, or one that was a Next when the
panel last looked). Every refusal is a returned reason, never a throw.

The Submit pin builds its page inline (`page.set_content`), one button per page, so a click can only
have come from `advance`.
"""

import json
import re

import pytest
from playwright.sync_api import Error as PlaywrightError

from tests.browser.conftest import ENGINE_SOURCES, EXTENSION, fixture_html
from tests.browser.pages import oracle
from tests.test_extension_page_kind import SUBMIT

READER = "window.careerStudioCompanion.pageReader"
KIND = "window.careerStudioCompanion.pageKind"
SOURCES = ENGINE_SOURCES + ["content/detect.js", "shared/ats-hosts.js", "shared/ats-buttons.js", "shared/page-kind.js",
                           "content/page-reader.js", "shared/queue-run.js"]


def summary(page):
    return page.evaluate(f"() => {READER}.summary()")


def classify(page):
    return page.evaluate(f"() => {KIND}.classify({READER}.summary())")


def advance(page, button_id):
    return page.evaluate(f"(id) => {READER}.advance(id)", button_id)


def advance_apply(page, button_id):
    return page.evaluate(f"(id) => {READER}.advance(id, {{apply: true}})", button_id)


def landing(page, press):
    """Run `press` (an Apply press) and wait for the tab to navigate; return (result, new url).
    The route answers any request to the test hosts, so the landing page exists. A navigation can
    destroy the page's context before `evaluate` answers, so a press that did navigate and lost
    its answer reads as the click it was (the navigation is the evidence)."""
    page.route(re.compile(r"https://(jobs|careers)\.acme\.test/.*"), lambda route: route.fulfill(
        status=200, content_type="text/html", body="<p>landed</p>"))
    with page.expect_navigation() as nav:
        try:
            result = press()
        except PlaywrightError as err:
            if "context was destroyed" not in str(err):
                raise
            result = {"clicked": True}
    return result, nav.value.url


def button(s, text):
    return next(b for b in s["buttons"] if b["text"] == text)


@pytest.mark.parametrize("name, kind", [
    ("wizard_step1.html", "form_step"),
    ("wizard_step2.html", "form_step"),
    ("wizard_review.html", "review"),
    ("wizard_confirmation.html", "confirmation"),
    ("signin.html", "sign_in"),
    ("create_account.html", "create_account"),
    ("verify_code.html", "verify"),
    ("captcha.html", "captcha"),
    ("posting_external.html", "posting"),
    ("closed.html", "closed"),
])
def test_each_fixture_classifies_to_its_kind(page, load, name, kind):
    load(page, fixture_html(name), SOURCES)
    assert classify(page)["kind"] == kind


def test_a_posting_on_a_job_board_is_board_native(page, load):
    """`boardNative` reads the hostname, so the fixture is served under a board's. The route only
    answers the page request; nothing leaves the machine (the context is offline)."""
    body = fixture_html("posting_board_native.html")
    page.route("https://www.linkedin.com/jobs/view/1", lambda route: route.fulfill(
        status=200, content_type="text/html", body=body))
    page.goto("https://www.linkedin.com/jobs/view/1")
    for src in SOURCES:
        page.add_script_tag(content=(EXTENSION / src).read_text(encoding="utf-8"))
    s = summary(page)
    assert (s["boardNative"], s["hasApplyLink"]) == (True, True)
    assert classify(page)["kind"] == "board_native"


def test_an_apply_button_on_a_posting_counts_like_an_apply_link(page, load):
    """A posting with an Apply <button> must not read as a stuck review page."""
    load(page, "<h1>Analyst at Acme</h1><p>Join us.</p><button>Apply now</button>", SOURCES)
    assert summary(page)["hasApplyLink"] is True
    assert classify(page)["kind"] == "posting"


def test_a_page_without_an_apply_control_has_no_apply_link(page, load):
    load(page, "<h1>Analyst at Acme</h1><a href='#'>Applications FAQ</a><a href='#'>Reapply</a>", SOURCES)
    assert summary(page)["hasApplyLink"] is False


# ---------- the summary ----------

def test_the_summary_is_counts_texts_and_booleans_and_never_a_value(page, load):
    load(page, """<form><label for='a'>First name</label><input id='a' value='Zelda-Secret-9'>
      <label for='b'>Notes</label><textarea id='b'>Zelda-Secret-9 again</textarea>
      <select id='c'><option selected>Zelda-Secret-9</option></select>
      <input type='password' value='Zelda-Secret-9'><button>Next</button></form>""", SOURCES)
    s = summary(page)
    assert "Zelda-Secret-9" not in json.dumps(s)
    assert set(s) == {"host", "stepKey", "applyId", "buttons", "passwordInputs", "confirmPassword", "otpInput", "captchaVisible",
                      "fillable", "hasApplyLink", "confirmationText", "confirmationPhrase", "closedText", "boardNative",
                      "submitSeen", "submitContext", "errors", "errorKeys", "requiredEmpty", "requiredKeys"}
    assert s["errors"] == 0
    assert set(s["buttons"][0]) == {"id", "text", "inForm", "visible", "enabled"}
    assert (s["passwordInputs"], s["fillable"]) == (1, 3)


def test_a_button_is_read_by_visible_text_value_or_aria_label_and_clipped(page, load):
    load(page, f"""<button id='t'>  Save   and Continue </button>
      <input type='submit' id='v' value='Next'><a role='button' aria-label='Go back' href='#'>«</a>
      <button id='long'>{'x' * 100}</button>""", SOURCES)
    s = summary(page)
    assert [b["text"] for b in s["buttons"]][:3] == ["Save and Continue", "Next", "«"]
    assert max(len(b["text"]) for b in s["buttons"]) <= 80


def test_the_state_of_each_button_is_read_not_assumed(page, load):
    load(page, """<button id='ok'>Next</button><button id='off' disabled>Continue</button>
      <button id='aria' aria-disabled='true'>Proceed</button>
      <button id='hid' style='visibility:hidden'>Review</button>
      <button id='gone' style='display:none'>Next step</button>
      <fieldset disabled><button id='fs'>Save and Continue</button></fieldset>""", SOURCES)
    s = summary(page)
    state = {b["text"]: (b["visible"], b["enabled"]) for b in s["buttons"]}
    assert state == {"Next": (True, True), "Continue": (True, False), "Proceed": (True, False),
                     "Review": (False, True), "Next step": (False, True), "Save and Continue": (True, False)}


def test_each_button_is_tagged_with_its_id(page, load):
    load(page, "<button>Next</button><button>Back</button>", SOURCES)
    ids = [b["id"] for b in summary(page)["buttons"]]
    assert len(set(ids)) == 2
    tagged = page.evaluate("() => [...document.querySelectorAll('[data-maestro-btn]')].map((n) => n.textContent)")
    assert tagged == ["Next", "Back"]
    assert page.evaluate("(id) => document.querySelector(`[data-maestro-btn='${id}']`).textContent", ids[1]) == "Back"


def test_ids_differ_between_frames(page, load):
    """The panel broadcasts one id to every frame; a number two frames both hand out would click
    in both. Each frame's ids carry a tag of its own, so the other frame answers not_next."""
    load(page, "<button>Next</button>", SOURCES)
    other = page.context.new_page()
    load(other, "<button>Next</button>", SOURCES)
    a, b = summary(page)["buttons"][0]["id"], summary(other)["buttons"][0]["id"]
    assert a != b
    assert advance(other, a) == {"clicked": False, "why": "not_next"}


def test_a_later_summary_retires_the_ids_of_an_earlier_one(page, load):
    load(page, "<button>Next</button>", SOURCES)
    old = summary(page)["buttons"][0]["id"]
    new = summary(page)["buttons"][0]["id"]
    assert old != new
    assert advance(page, old) == {"clicked": False, "why": "not_next"}


def test_confirmation_and_closed_text(page, load):
    load(page, "<p>We've received your application.</p>", SOURCES)
    assert summary(page)["confirmationText"] is True
    assert summary(page)["confirmationPhrase"] == "We've received your application"
    load(page, "<p>This position has been filled.</p>", SOURCES)
    assert summary(page)["closedText"] is True
    load(page, "<p>Tell us about yourself.</p>", SOURCES)
    s = summary(page)
    assert (s["confirmationText"], s["closedText"]) == (False, False)
    assert s["confirmationPhrase"] is None


@pytest.mark.parametrize("words", [
    "This job has been closed.", "This position is now closed", "This posting is closed", "This requisition has been closed",
    "The role has been filled.", "This job is no longer accepting applications.", "This position is no longer available",
    "No longer open for applications", "No longer accepting applications",
])
def test_every_closed_wording_reads_as_closed(page, load, words):
    load(page, f"<h1>Analyst</h1><p>{words}</p>", SOURCES)
    assert summary(page)["closedText"] is True
    assert classify(page)["kind"] == "closed"


@pytest.mark.parametrize("prose", [
    "Hires are made at the level at which this position is filled.",
    "Applications are reviewed until the job is filled by a candidate.",
    "Our teams are always open to new ideas.",
])
def test_job_description_prose_is_not_a_closed_notice(page, load, prose):
    load(page, f"<h1>Analyst</h1><p>{prose}</p><a href='/apply'>Apply</a>", SOURCES)
    assert summary(page)["closedText"] is False
    assert classify(page)["kind"] == "posting"


def test_a_posting_with_the_closed_sentence_in_its_description_and_an_apply_link_is_a_posting(page, load):
    load(page, "<h1>Analyst</h1><p>Pay is set at the level at which this position has been filled before.</p>"
               "<a href='https://jobs.acme.test/apply'>Apply now</a>", SOURCES)
    assert classify(page)["kind"] == "posting"


def test_this_position_has_been_filled_with_no_apply_is_closed(page, load):
    load(page, "<h1>Analyst</h1><p>This position has been filled.</p>", SOURCES)
    assert classify(page)["kind"] == "closed"


def test_the_confirmation_phrase_is_the_match_and_none_of_the_page_around_it(page, load):
    load(page, "<p>Hi Zelda-Secret-9, thank you for applying to Acme. Your reference is 4471.</p>", SOURCES)
    s = summary(page)
    assert s["confirmationPhrase"] == "thank you for applying"
    assert "Zelda-Secret-9" not in json.dumps(s)


def test_password_and_code_inputs(page, load):
    load(page, "<input type='password' autocomplete='current-password'>", SOURCES)
    s = summary(page)
    assert (s["passwordInputs"], s["confirmPassword"], s["otpInput"]) == (1, False, False)
    load(page, "<input type='password' style='display:none'><input type='text'>", SOURCES)
    assert summary(page)["passwordInputs"] == 0   # a hidden one is not on the page
    load(page, "<input type='password'><input type='password' placeholder='Re-enter password'>", SOURCES)
    s = summary(page)
    assert (s["passwordInputs"], s["confirmPassword"]) == (2, True)
    load(page, "<input type='password' autocomplete='new-password'>", SOURCES)
    assert summary(page)["confirmPassword"] is True   # a lone new-password is a sign-up, which parks
    load(page, "<label>Enter the OTP <input name='x'></label>", SOURCES)
    assert summary(page)["otpInput"] is True
    load(page, "<label>Enter the 6-digit code <input name='otp'></label>", SOURCES)
    assert summary(page)["otpInput"] is True
    load(page, "<input name='c' autocomplete='one-time-code'>", SOURCES)
    assert summary(page)["otpInput"] is True


@pytest.mark.parametrize("label", ["One-time relocation bonus expected?", "Card security code"])
def test_one_time_or_security_code_words_alone_are_not_a_code_box(page, load, label):
    load(page, f"<label>{label} <input name='q1'></label><label>First name <input name='fn'></label>"
               "<button>Next</button>", SOURCES)
    assert summary(page)["otpInput"] is False
    assert classify(page)["kind"] == "form_step"


# ---------- captcha ----------

def test_an_invisible_recaptcha_badge_alone_is_not_a_captcha(page, load):
    load(page, """<h1>Apply</h1><label for='n'>Name</label><input id='n'>
      <div class='grecaptcha-badge' style='width:256px;height:60px'>
        <iframe src='about:blank#recaptcha/api2/anchor?size=invisible' style='width:256px;height:60px;border:0'></iframe>
      </div><button>Next</button>""", SOURCES)
    assert summary(page)["captchaVisible"] is False
    assert classify(page)["kind"] == "form_step"


@pytest.mark.parametrize("src", [
    "about:blank#recaptcha/api2/bframe",
    "about:blank#newassets.hcaptcha.com/captcha/challenge",
    "about:blank#challenges.cloudflare.com/turnstile",
])
def test_a_visible_challenge_frame_is_a_captcha(page, load, src):
    load(page, f"<p>Check</p><iframe src='{src}' style='width:300px;height:300px'></iframe>", SOURCES)
    assert summary(page)["captchaVisible"] is True


def test_a_visible_recaptcha_checkbox_is_a_captcha_but_a_tiny_hcaptcha_frame_is_not(page, load):
    load(page, "<iframe src='about:blank#recaptcha/api2/anchor?size=normal' style='width:304px;height:78px'></iframe>", SOURCES)
    assert summary(page)["captchaVisible"] is True
    load(page, "<iframe src='about:blank#hcaptcha.com/captcha' style='width:40px;height:40px'></iframe>", SOURCES)
    assert summary(page)["captchaVisible"] is False


@pytest.mark.parametrize("hide", [
    "display:none", "visibility:hidden", "opacity:0", "position:absolute;left:-10000px;top:0",
])
def test_a_challenge_frame_that_is_parked_out_of_sight_is_not_a_captcha(page, load, hide):
    load(page, f"<div style='{hide}'><iframe src='about:blank#recaptcha/api2/bframe' "
               "style='width:400px;height:580px'></iframe></div>", SOURCES)
    assert summary(page)["captchaVisible"] is False


# ---------- Workday-shaped pages: no <form> at all ----------

NO_FORM_PAGE = """
<header><button>Sign in</button><button>Search</button><button>Continue</button></header>
<main>
  <h1>My Information</h1>
  <label for='fn'>First name*</label><input id='fn'>
  <label for='ln'>Last name*</label><input id='ln'>
</main>
<div class='footer-bar'><button>Back</button><button>Save and Continue</button></div>
"""


def test_a_page_with_no_form_element_is_a_form_step_through_its_footer_bar(page, load):
    """Some application wizards render no <form>: their Next lives in a footer bar of plain
    elements. `inForm` must still hold there, or the run parks on every such step. The site
    header's own buttons stay out, so a header "Continue" is not taken for the step's."""
    load(page, NO_FORM_PAGE, SOURCES)
    s = summary(page)
    assert page.evaluate("() => document.querySelectorAll('form, [role=form]').length") == 0
    in_form = {b["text"]: b["inForm"] for b in s["buttons"]}
    assert in_form == {"Sign in": False, "Search": False, "Continue": False, "Back": True, "Save and Continue": True}
    verdict = classify(page)
    assert verdict["kind"] == "form_step"
    named = page.evaluate("(id) => document.querySelector(`[data-maestro-btn='${id}']`).textContent", verdict["next"])
    assert named == "Save and Continue"


@pytest.mark.parametrize("hide", [
    "", "style='display:none'", "style='visibility:hidden'", "style='position:absolute;left:-10000px'",
])
def test_a_form_of_unseen_controls_does_not_turn_off_the_no_form_footer_path(page, load, hide):
    """A tracking or CSRF form with only hidden, display:none or parked controls is not the
    page's form: counting it would make the real footer Next inForm:false and park the step."""
    unseen = "<input type='hidden' name='t'>" if not hide else f"<input name='t' {hide}>"
    load(page, NO_FORM_PAGE + f"<form action='#'>{unseen}</form>", SOURCES)
    in_form = {b["text"]: b["inForm"] for b in summary(page)["buttons"]}
    assert in_form["Save and Continue"] is True and in_form["Continue"] is False
    assert classify(page)["kind"] == "form_step"


def test_a_nav_landmark_button_is_never_the_steps_next(page, load):
    load(page, """<nav role='navigation'><button>Next</button></nav>
      <label for='a'>Name</label><input id='a'>""", SOURCES)
    assert classify(page)["kind"] != "form_step"


def test_when_the_fields_sit_in_a_form_only_its_buttons_are_in_the_form(page, load):
    load(page, """<form><label for='a'>Name</label><input id='a'><button type='button'>Back</button>
      <button>Next</button></form><button>Continue</button>""", SOURCES)
    in_form = {b["text"]: b["inForm"] for b in summary(page)["buttons"]}
    assert in_form == {"Back": True, "Next": True, "Continue": False}


def test_a_button_tied_to_the_form_by_its_form_attribute_is_in_the_form(page, load):
    load(page, """<form id='f'><label for='a'>Name</label><input id='a'></form>
      <div><button form='f'>Next</button></div>""", SOURCES)
    assert summary(page)["buttons"][0]["inForm"] is True


# ---------- G1: a Next outside every form, a stepper that says Submit, a chrome flag ----------

def test_a_next_in_a_bar_outside_every_form_is_the_step_and_a_stepper_label_is_no_submit(page, load):
    """Dayforce: four <form>s, the Next in an affix bar outside them, a stepper whose last step is
    called "Submit" (a role=button span and a link inside it). The stepper's words are labels."""
    load(page, fixture_html("wizard_forms_footer.html"), SOURCES)
    s = summary(page)
    assert s["submitSeen"] is False
    assert button(s, "Next")["inForm"] is False and "chrome" not in button(s, "Next")
    verdict = classify(page)
    assert verdict["kind"] == "form_step"
    assert page.evaluate("(id) => document.querySelector(`[data-maestro-btn='${id}']`).textContent", verdict["next"]) == "Next"
    assert advance(page, verdict["next"]) == {"clicked": True}
    assert oracle(page, "advanced") is True


def test_a_real_submit_button_in_a_stepper_still_counts(page, load):
    """The stepper exemption is for labels: a real <button> that says Submit is a Submit wherever it sits."""
    load(page, """<div class='stepper'><button type='button'>Submit</button></div>
      <label for='a'>Name</label><input id='a'>""", SOURCES)
    assert summary(page)["submitSeen"] is True


@pytest.mark.parametrize("holder", ["<div class='steps'>{x}</div>", "<ol class='my-stepper'>{x}</ol>",
                                    "<div role='progressbar'>{x}</div>"])
def test_stepper_labels_are_not_a_submit_seen(page, load, holder):
    x = "<span role='button'>Submit</span><a href='#s'>Submit</a>"
    load(page, holder.format(x=x) + "<label for='a'>Name</label><input id='a'><button>Next</button>", SOURCES)
    assert summary(page)["submitSeen"] is False


def test_a_div_button_outside_a_stepper_that_says_submit_is_still_seen(page, load):
    load(page, "<div role='button'>Submit</div><label for='a'>Name</label><input id='a'>", SOURCES)
    assert summary(page)["submitSeen"] is True


def test_a_button_in_site_chrome_carries_the_chrome_flag(page, load):
    load(page, """<header><button>Continue</button></header>
      <main><label for='a'>Name</label><input id='a'><button>Next</button></main>
      <footer><button>Subscribe</button></footer>""", SOURCES)
    flags = {b["text"]: b.get("chrome") for b in summary(page)["buttons"]}
    assert flags == {"Continue": True, "Next": None, "Subscribe": True}
    assert classify(page)["kind"] == "form_step"


def test_a_next_in_the_site_header_alone_is_never_the_step(page, load):
    load(page, "<header><button>Next</button></header><label for='a'>Name</label><input id='a'>", SOURCES)
    verdict = classify(page)
    assert verdict == {"kind": "review", "by": "fields_no_next"}


def test_a_sites_submit_in_chrome_stops_but_is_not_the_applications_submit(page, load):
    load(page, "<header><button>Apply now</button></header><label for='a'>Name</label><input id='a'>", SOURCES)
    assert classify(page) == {"kind": "review", "by": "submit_seen"}


# ---------- G1: required and empty ----------

def required(page):
    return page.evaluate(f"() => {READER}.pageRequired()")


def test_a_required_box_is_counted_while_empty_and_not_after(page, load):
    load(page, "<label for='a'>Name</label><input id='a' required><label for='b'>Notes</label><input id='b'>", SOURCES)
    s = summary(page)
    assert (s["requiredEmpty"], len(s["requiredKeys"])) == (1, 1)
    page.fill("#a", "Zelda-Secret-9")
    assert summary(page)["requiredEmpty"] == 0
    assert "Zelda-Secret-9" not in json.dumps(summary(page))


@pytest.mark.parametrize("control", [
    "<input id='a' aria-required='true'>",
    "<input id='a' required>",
    "<textarea id='a' required></textarea>",
    "<input id='a' type='email' required>",
])
def test_required_by_attribute_or_aria_is_counted_with_no_label_at_all(page, load, control):
    """Whatever the field reader makes of the label, the attribute alone says required."""
    load(page, f"<div>{control}</div>", SOURCES)
    assert summary(page)["requiredEmpty"] == 1


def test_a_star_in_the_label_makes_an_empty_box_required(page, load):
    load(page, "<label for='a'>First name*</label><input id='a'><label for='b'>Nickname</label><input id='b'>", SOURCES)
    assert summary(page)["requiredEmpty"] == 1


def test_a_long_question_before_the_box_and_a_hidden_upload_under_a_star_are_required(page, load):
    """ATS-G: the question is a sentence in a span before div>div>textarea, the resume box a hidden file
    input; neither reads as a labelled, required field to the field reader."""
    load(page, fixture_html("label_before_box.html"), SOURCES)
    s = summary(page)
    assert s["requiredEmpty"] == 2
    items = required(page)["items"]
    assert [i["kind"] for i in items] == ["field", "upload"]
    assert required(page)["count"] == 2
    assert all(i["target"] for i in items)
    assert items[0]["label"].startswith("What is the most impressive project")
    page.fill("textarea >> nth=0", "An answer")
    assert summary(page)["requiredEmpty"] == 1
    page.set_input_files("input[type=file]", files=[{"name": "resume.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-1.4"}])
    assert summary(page)["requiredEmpty"] == 0


def test_a_standing_hint_is_not_a_star_on_the_first_field(page, load):
    load(page, "<p>Fields marked * are required.</p><div><div><input id='a'></div></div>", SOURCES)
    assert summary(page)["requiredEmpty"] == 0


def test_the_previous_fields_error_text_does_not_make_the_next_field_required(page, load):
    load(page, """<label for='a'>Email</label><input id='a' value='sam'><p role='alert'>Email is required</p>
      <div><div><input id='b'></div></div>""", SOURCES)
    assert summary(page)["requiredEmpty"] == 0


def test_an_optional_empty_box_and_hidden_required_ones_are_not_counted(page, load):
    load(page, """<label for='a'>Notes</label><input id='a'>
      <input id='b' required style='display:none'><input id='c' required type='hidden'>
      <input id='d' required disabled><div style='visibility:hidden'><input id='e' required></div>""", SOURCES)
    assert summary(page)["requiredEmpty"] == 0


def test_a_required_select_on_its_placeholder_is_empty_until_picked(page, load):
    load(page, """<label for='a'>Country*</label><select id='a'>
      <option value=''>Select one</option><option value='us'>United States</option></select>""", SOURCES)
    assert summary(page)["requiredEmpty"] == 1
    page.select_option("#a", "us")
    assert summary(page)["requiredEmpty"] == 0


def test_a_required_radio_group_with_nothing_chosen_is_one_empty_item(page, load):
    load(page, """<fieldset><legend>Are you over 18?*</legend>
      <label><input type='radio' name='age'> Yes</label><label><input type='radio' name='age'> No</label></fieldset>""", SOURCES)
    assert summary(page)["requiredEmpty"] == 1
    assert [i["kind"] for i in required(page)["items"]] == ["field"]
    page.check("input >> nth=1")
    assert summary(page)["requiredEmpty"] == 0


def test_a_nameless_radio_pair_under_a_starred_question_is_required(page, load):
    """The Gem shape: no name, no fieldset; the question sits in a sibling of the radios' wrapper."""
    load(page, """<div class='row'><div><span>Are you graduating in 2027?<span>*</span></span></div>
      <div><div><div><div><input type='radio' id='y'><label for='y'>Yes</label></div>
      <div><input type='radio' id='n'><label for='n'>No</label></div></div></div></div></div>""", SOURCES)
    assert summary(page)["requiredEmpty"] == 1
    page.check("#y")
    assert summary(page)["requiredEmpty"] == 0


def test_a_required_lone_checkbox_is_empty_until_ticked(page, load):
    load(page, "<label><input type='checkbox' id='a' required> I agree to the terms</label>", SOURCES)
    assert summary(page)["requiredEmpty"] == 1
    page.check("#a")
    assert summary(page)["requiredEmpty"] == 0


def test_a_required_upload_with_a_file_row_or_a_file_is_not_empty(page, load):
    load(page, """<div><span>Resume*</span><div class='zone'><input type='file' style='display:none'>
      <div class='row'>resume.pdf <button type='button' aria-label='Remove file'>x</button></div></div></div>""", SOURCES)
    assert summary(page)["requiredEmpty"] == 0
    load(page, """<div><span>Resume*</span><div class='zone'><input type='file' style='display:none'>
      <p>Drop a file</p></div></div>""", SOURCES)
    assert summary(page)["requiredEmpty"] == 1


# ---------- G1+: Workday's question step, whose popup buttons mount late ----------

FILLABLE = "window.careerStudioCompanion.fillableControls()"


def test_workday_popup_buttons_are_fillable_controls_and_required_empties_until_picked(page, load):
    load(page, fixture_html("wizard_popup_questions.html"), SOURCES)
    assert page.evaluate(FILLABLE) == 0 and summary(page)["requiredEmpty"] == 0
    page.wait_for_function("window.__oracle.mounted === true")
    assert page.evaluate(FILLABLE) == 3
    s = summary(page)
    assert (s["fillable"], s["requiredEmpty"]) == (3, 3)
    assert [i["label"] for i in required(page)["items"]][0] == "Degree"
    page.evaluate("""() => { const b = document.querySelector('#q0'); b.textContent = 'Bachelor'; b.setAttribute('aria-label', 'Bachelor Required'); }""")
    assert summary(page)["requiredEmpty"] == 2


def test_a_popup_button_is_required_by_its_aria_name_alone_or_by_its_legends_star_alone(page, load):
    load(page, """<fieldset><legend>Question one</legend>
      <button type='button' aria-haspopup='listbox' aria-label=' Select One Required'>Select One</button></fieldset>
      <fieldset><legend>Question two <abbr title='required'>*</abbr></legend>
      <button type='button' aria-haspopup='listbox' aria-label=' Select One'>Select One</button></fieldset>
      <fieldset><legend>Question three</legend>
      <button type='button' aria-haspopup='listbox' aria-label=' Select One'>Select One</button></fieldset>""", SOURCES)
    assert (page.evaluate(FILLABLE), summary(page)["requiredEmpty"]) == (3, 2)


def test_a_popup_whose_question_says_are_required_is_still_required_by_its_aria_name(page, load):
    load(page, """<button type='button' aria-haspopup='listbox'
      aria-label='What skills are required for this role? Select One Required'>Select One</button>""", SOURCES)
    assert summary(page)["requiredEmpty"] == 1


def test_a_popup_with_a_pick_showing_is_not_empty(page, load):
    load(page, """<fieldset><legend>Degree *</legend>
      <button type='button' aria-haspopup='listbox' aria-label='Bachelor Required'>Bachelor</button></fieldset>""", SOURCES)
    assert summary(page)["requiredEmpty"] == 0


def test_a_sites_menu_button_and_a_search_popup_are_not_fillable_controls(page, load):
    load(page, """<header><button aria-haspopup='listbox' type='button'>English</button></header>
      <nav><button aria-haspopup='true' type='button'>Menu</button></nav>
      <div><button aria-haspopup='menu' type='button'>More</button><button aria-haspopup='false' type='button'>No</button>
      <button aria-haspopup='listbox' type='button' aria-label='Search jobs'>Search</button></div>""", SOURCES)
    assert page.evaluate(FILLABLE) == 0


def test_a_popup_button_is_counted_like_a_combobox(page, load):
    load(page, "<div role='button' aria-haspopup='listbox'>Pick</div><button aria-haspopup='listbox' type='button'>Select One</button>", SOURCES)
    assert page.evaluate(FILLABLE) == 2


POPUP_DRIVE = """async ({record, mount}) => {
  const ns = window.careerStudioCompanion;
  let clock = 1000, fills = [];
  const reads = () => ns.pageReader.summary();
  const deps = {
    openTab: async () => 1,
    classify: async () => [{frameId: 0, result: {summary: reads(), top: true}}],
    tabUrl: async () => location.href,
    advance: async (tabId, frameId, id) => ns.pageReader.advance(id),
    // The first fill finds no fields (the questions mount while it runs); later ones list what is visible.
    fill: async () => {
      const seen = ns.fillableControls();
      fills.push(seen);
      if (fills.length === 1 && mount) window.__mountQuestions();
      return {fields: [], stopped: false};
    },
    signIn: async () => ({signedIn: false}),
    waitForChange: async () => ({changed: false}),
    pageErrors: async () => ns.pageReader.pageErrors(),
    pageRequired: async () => ns.pageReader.pageRequired(),
    fix: async () => ({fixed: false}),
    attachTo: async () => ({attached: false}), uploads: async () => [],
    sleep: async () => {}, save() {}, onUpdate() {}, now: () => (clock += 1000), cancelled: () => false,
  };
  await ns.queueRun.drive(record, deps);
  return {status: record.status, why: record.why, fills, open: (record.open || []).map((o) => o.question), readyAt: record.readyAt};
}"""


def _popup_drive(page, html, **record):
    load_html = html.replace("setTimeout(window.__mountQuestions, 2500);", "")
    page.set_content(load_html)
    for src in SOURCES:
        page.add_script_tag(content=(EXTENSION / src).read_text(encoding="utf-8"))
    base = {"openUrl": "https://jobs.acme.test/apply", "tabId": None, "hosts": [], "seen": [], "step": 0}
    return page.evaluate(POPUP_DRIVE, {"record": {**base, **record}, "mount": True})


def test_a_question_step_that_mounts_after_the_footer_is_filled_again_once_the_popups_are_there(page):
    out = _popup_drive(page, fixture_html("wizard_popup_questions.html"))
    assert out["fills"][0] == 0 and out["fills"][1] == 3, "the second fill saw the three popup buttons"
    assert out["why"] != "unknown_page"


def test_a_review_step_with_popup_questions_still_empty_is_never_ready(page):
    html = fixture_html("wizard_popup_questions.html").replace("Save and Continue", "Submit application")
    out = _popup_drive(page, html, step=1, wrote=True)
    assert out["fills"][:2] == [0, 3]
    assert (out["status"], out["why"]) == ("parked", "open_questions")
    assert out["readyAt"] is None and len(out["open"]) == 3 and out["open"][0] == "Degree"


def test_a_parser_upload_box_is_never_a_required_empty(page):
    """The site's own import-from-resume box (H's `parser` kind) is not a box the run owes a file, even
    marked required; the real resume box beside it still is."""
    from tests.browser.test_upload_box import _load
    _load(page, """<form><section><h3>Candidate Info</h3><div class='up'><span>Resume*</span>
      <button type='button'>Import Resume</button><input type='file' id='r1' style='display:none' required></div></section>
      <section><h3>Resume Upload</h3><div class='up'><span>Resume*</span><p>Drag your resume here</p>
      <input type='file' id='r2' style='display:none' required></div></section></form>""")
    items = page.evaluate(f"() => {READER}.pageRequired()")["items"]
    assert [i["kind"] for i in items] == ["upload"] and page.evaluate(f"() => {READER}.summary().requiredEmpty") == 1
    tag = page.evaluate("() => document.querySelector('#r2').getAttribute('data-maestro-up')")
    assert items[0]["target"] == tag


def test_page_required_names_words_and_handles_never_values(page, load):
    load(page, "<label for='a'>Name</label><input id='a' required><label for='b'>Phone</label><input id='b' required value='555-0100'>", SOURCES)
    out = required(page)
    assert out["count"] == 1 and out["items"][0]["label"] == "Name"
    assert out["items"][0]["kind"] == "field" and isinstance(out["items"][0]["target"], str)
    assert "555" not in json.dumps(out)
    assert set(out) == {"count", "items"}


# ---------- advance: the Next click ----------

def test_advance_clicks_the_one_next_of_a_form_step(page, load):
    load(page, fixture_html("wizard_step1.html"), SOURCES)
    page.fill("#first", "Ada")   # filling is not this module's job; a required box blocks a real submit
    verdict = classify(page)
    assert verdict["kind"] == "form_step"
    assert oracle(page, "advanced") is False
    assert advance(page, verdict["next"]) == {"clicked": True}
    assert oracle(page, "advanced") is True


def test_advance_clicks_a_plain_button_labelled_save_and_continue(page, load):
    load(page, fixture_html("wizard_step2.html"), SOURCES)
    verdict = classify(page)
    assert advance(page, verdict["next"]) == {"clicked": True}
    assert oracle(page, "advancedStep2") is True


def test_advance_clicks_nothing_on_the_review_page(page, load):
    load(page, fixture_html("wizard_review.html"), SOURCES)
    s = summary(page)
    for b in s["buttons"]:
        assert advance(page, b["id"])["clicked"] is False
    assert oracle(page, "submitted") is False


def test_advance_refuses_an_id_that_is_not_a_next_button(page, load):
    load(page, "<button>Next</button><button>Back</button><button>Go</button><a href='#x' id='lnk'>Next</a>", SOURCES)
    s = summary(page)
    refusals = [advance(page, button(s, "Back")["id"]), advance(page, button(s, "Go")["id"]),
                advance(page, "nope"), advance(page, ""), advance(page, None), advance(page, 3)]
    assert all(r == {"clicked": False, "why": "not_next"} for r in refusals)


def test_advance_refuses_a_hidden_or_disabled_next(page, load):
    load(page, "<button disabled>Next</button><button style='visibility:hidden'>Continue</button>"
               "<button aria-disabled='true'>Proceed</button>", SOURCES)
    s = summary(page)
    assert [advance(page, b["id"]) for b in s["buttons"]] == [{"clicked": False, "why": "not_next"}] * 3


def test_advance_cannot_be_aimed_at_an_element_the_summary_never_tagged(page, load):
    """A page can write the attribute itself; it still only reaches buttons the reader would list."""
    load(page, """<div data-maestro-btn='evil-1' id='d' onclick='window.hit = true'>Next</div>
      <button>Next</button>""", SOURCES)
    summary(page)
    page.evaluate("() => document.getElementById('d').setAttribute('data-maestro-btn', 'evil-1')")
    assert advance(page, "evil-1") == {"clicked": False, "why": "not_next"}
    assert page.evaluate("() => window.hit === true") is False


def test_a_next_relabelled_to_submit_between_classify_and_advance_is_refused(page, load):
    load(page, """<button id='b' onclick='window.hit = true'>Next</button>""", SOURCES)
    verdict = page.evaluate(f"() => {KIND}.classify({{...{READER}.summary(), fillable: 1}})")
    assert verdict["kind"] == "form_step"
    page.evaluate("() => { document.getElementById('b').textContent = 'Submit application'; }")
    assert advance(page, verdict["next"]) == {"clicked": False, "why": "submit"}
    assert page.evaluate("() => window.hit === true") is False


def test_a_submit_word_in_any_label_source_beats_a_next_text(page, load):
    """The visible text says Next; the accessible name, value or title says otherwise. The summary
    carries the Submit-worded one, and advance refuses on it."""
    load(page, """<button aria-label='Submit application' onclick='window.hit = true'>Next</button>
      <input type='button' value='Next' title='Send my application' onclick='window.hit = true'>
      <button onclick='window.hit = true'>Next<span style='display:none'> and finish</span></button>""", SOURCES)
    s = summary(page)
    sorts = page.evaluate(f"(bs) => bs.map((b) => {KIND}.sortButton(b))", s["buttons"])
    assert sorts == ["submit", "submit", "submit"]
    assert [advance(page, b["id"])["why"] for b in s["buttons"]] == ["submit"] * 3
    assert page.evaluate("() => window.hit === true") is False


def test_a_submit_word_past_the_clip_still_sorts_as_submit(page, load):
    load(page, f"<button onclick='window.hit = true'>{'Next ' + 'x' * 90} submit</button>", SOURCES)
    s = summary(page)
    assert len(s["buttons"][0]["text"]) <= 80
    assert page.evaluate(f"(b) => {KIND}.sortButton(b)", s["buttons"][0]) == "submit"
    assert advance(page, s["buttons"][0]["id"])["clicked"] is False


# ---------- the never-submit pin ----------

PIN_WORDS = SUBMIT + [
    "Reapply", "Resend", "Incomplete", "SUBMIT", "submit_application", "SubmitApplication", "Apply-now",
    "Submit­", "Finalize", "Review and submit", "Next: Review & Submit", "Sent", "Applying…",
]
FLAVOURS = {
    "button": "<button id='t'>{w}</button>",
    "submit input": "<input type='submit' id='t' value='{w}'>",
    "button input": "<input type='button' id='t' value='{w}'>",
    "link button": "<a role='button' id='t' href='#'>{w}</a>",
    "aria label": "<button id='t' aria-label='{w}'>Next</button>",
    "nested": "<button id='t'><span>{w}</span></button>",
}


@pytest.mark.parametrize("flavour", sorted(FLAVOURS))
@pytest.mark.parametrize("word", PIN_WORDS)
def test_a_submit_worded_button_is_never_clicked_through_advance(page, load, word, flavour):
    load(page, "<label for='a'>Name</label><input id='a'>" + FLAVOURS[flavour].format(w=word), SOURCES)
    page.evaluate("""() => {
      window.hit = 0;
      document.getElementById('t').addEventListener('click', (e) => { e.preventDefault(); window.hit += 1; });
    }""")
    s = summary(page)
    ids = [b["id"] for b in s["buttons"]] + ["unknown-id", ""]
    for button_id in ids:
        result = advance(page, button_id)
        assert result["clicked"] is False
    assert advance(page, s["buttons"][0]["id"]) == {"clicked": False, "why": "submit"}
    assert page.evaluate("() => window.hit") == 0
    assert classify(page)["kind"] == "review"


def test_the_pin_covers_a_submit_that_is_disabled_or_hidden_too(page, load):
    load(page, "<button disabled onclick='window.hit = 1'>Submit</button>"
               "<button style='visibility:hidden' onclick='window.hit = 1'>Apply</button>", SOURCES)
    for b in summary(page)["buttons"]:
        assert advance(page, b["id"])["clicked"] is False
    assert page.evaluate("() => window.hit === 1") is False


# ---------- what the page says about submitting (batch-4 review) ----------

def test_a_dialog_that_asks_about_submitting_is_a_submit_context(page, load):
    load(page, """<h1>Your details</h1><div role='dialog' aria-labelledby='t'><h2 id='t'>Submit your application?</h2>
      <button>Proceed</button><button>Cancel</button></div>""", SOURCES)
    assert summary(page)["submitContext"] is True
    assert classify(page)["kind"] == "review"


def test_a_native_open_dialog_and_an_aria_modal_count_too(page, load):
    load(page, "<dialog open><p>Are you ready to submit?</p><button>Proceed</button></dialog>", SOURCES)
    assert summary(page)["submitContext"] is True
    load(page, "<div aria-modal='true'><h3>Review and submit</h3><button>Continue</button></div>", SOURCES)
    assert summary(page)["submitContext"] is True


def test_the_steps_own_heading_can_be_the_submit_context(page, load):
    load(page, "<h1>Review and submit</h1><button>Continue</button>", SOURCES)
    assert summary(page)["submitContext"] is True
    assert classify(page)["kind"] == "review"


@pytest.mark.parametrize("dialog", [
    "<div aria-modal='true'><h2>Are you sure you want to apply?</h2><button>Continue</button></div>",
    "<div role='alertdialog' aria-label='Finish your application?'><button>Proceed</button></div>",
    "<div role='dialog'><p>Ready to send? Your details go to Acme.</p><button>Continue</button></div>",
    "<dialog open aria-labelledby='t'><span id='t'>Confirm and apply</span><button>Continue</button></dialog>",
    "<div role='dialog'><p>Your application will be submitted.</p><button>Continue</button></div>",
    "<div role='dialog'><p>By continuing you will submit your application.</p><button>Proceed</button></div>",
])
def test_a_dialog_with_any_submit_word_in_its_question_is_a_submit_context(page, load, dialog):
    """Dialogs are judged by the full button sort, not the narrow step-heading words; the lone
    Continue is never offered as the step."""
    load(page, dialog, SOURCES)
    assert summary(page)["submitContext"] is True
    assert classify(page) == {"kind": "review", "by": "submit_context"}


@pytest.mark.parametrize("html", [
    "<h1>Apply to Acme: Data Analyst</h1><label for='a'>Name</label><input id='a'><button>Next</button>",
    "<h1>Complete your profile</h1><label for='a'>Name</label><input id='a'><button>Next</button>",
    "<h1>Your details</h1><div role='dialog'><h2>Cookie preferences</h2><button>Accept</button></div><button>Next</button>",
    "<h1>Your details</h1><div role='dialog' style='display:none'><h2>Submit your application?</h2></div><button>Next</button>",
])
def test_an_ordinary_heading_or_a_hidden_dialog_is_no_submit_context(page, load, html):
    load(page, html, SOURCES)
    assert summary(page)["submitContext"] is False


@pytest.mark.parametrize("control", [
    "<div role='button'>Submit application</div>",
    "<span role='button'>Send my application</span>",
    "<input type='image' alt='Submit application' src='data:image/gif;base64,R0lGODlhAQABAAAAACw='>",
    "<a href='/finish'>Submit application</a>",
    "<button id='submit-btn'>Done</button>",
    "<button name='submitForm'>Go</button>",
    "<button data-qa='btn-submit'>Done</button>",
    "<button data-automation-id='submitApp'>Done</button>",
    "<input type='button' value='Go' formaction='/apply/submit'>",
])
def test_a_submit_the_button_list_cannot_see_still_stops_the_step(page, load, control):
    load(page, f"<label for='a'>Name</label><input id='a'><button>Next</button>{control}", SOURCES)
    assert summary(page)["submitSeen"] is True
    assert classify(page)["kind"] == "review"


@pytest.mark.parametrize("control", [
    "<div role='button' style='display:none'>Submit application</div>",
    "<header><a href='/jobs'>Submit your CV</a></header>",
    "<footer><a href='/feedback'>Send feedback</a></footer>",
    "<a href='/faq'>Frequently asked questions</a>",
])
def test_an_unseen_or_chrome_extra_is_no_submit_signal(page, load, control):
    load(page, f"<label for='a'>Name</label><input id='a'><button>Next</button>{control}", SOURCES)
    assert summary(page)["submitSeen"] is False
    assert classify(page)["kind"] == "form_step"


def test_a_next_whose_id_says_submit_is_never_pressed(page, load):
    load(page, "<button id='submit_step' onclick='window.hit = 1'>Next</button>", SOURCES)
    b = summary(page)["buttons"][0]
    assert advance(page, b["id"]) == {"clicked": False, "why": "submit"}
    assert page.evaluate("() => window.hit === 1") is False


# ---------- passwords, footers and boards ----------

@pytest.mark.parametrize("label", ["Create a password", "Choose a password", "New password", "Set your password",
                                   "createPassword"])
def test_a_single_sign_up_password_box_is_not_a_sign_in(page, load, label):
    load(page, f"<label>{label} <input type='password' name='pw'></label>", SOURCES)
    s = summary(page)
    assert (s["passwordInputs"], s["confirmPassword"]) == (1, True)
    assert classify(page)["kind"] == "create_account"


def test_a_plain_password_box_is_still_a_sign_in(page, load):
    load(page, "<label>Password <input type='password' name='pw'></label>", SOURCES)
    assert classify(page)["kind"] == "sign_in"


def test_a_toggled_password_box_counts_as_a_password(page, load):
    """A show-password toggle makes it type=text; its autocomplete token still says what it is
    (one definition with the inventory, which never lists one)."""
    load(page, "<input type='text' autocomplete='current-password' name='pw'>", SOURCES)
    assert summary(page)["passwordInputs"] == 1
    assert page.evaluate("() => window.careerStudioCompanion.fillBase.isPasswordBox(document.querySelector('input'))")
    assert page.evaluate("() => window.careerStudioCompanion.fillInventory.list({}).fields.length") == 0


def test_a_footer_in_the_applications_own_content_keeps_its_next(page, load):
    """A wizard's own footer action bar (inside main, a form or a section) is not site chrome."""
    load(page, """<main><label for='a'>Name</label><input id='a'>
      <footer><button>Back</button><button>Save and Continue</button></footer></main>""", SOURCES)
    assert {b["text"]: b["inForm"] for b in summary(page)["buttons"]}["Save and Continue"] is True
    assert classify(page)["kind"] == "form_step"
    load(page, """<form><label for='a'>Name</label><input id='a'><footer><button>Next</button></footer></form>""", SOURCES)
    assert classify(page)["kind"] == "form_step"
    load(page, """<label for='a'>Name</label><input id='a'><footer><button>Next</button></footer>""", SOURCES)
    assert summary(page)["buttons"][0]["inForm"] is False   # the page's own bottom footer is the site's


def test_a_footer_newsletter_form_is_not_the_pages_form(page, load):
    load(page, NO_FORM_PAGE + "<footer><form><label for='em'>Email</label><input id='em'>"
                              "<button type='button'>Subscribe</button></form></footer>", SOURCES)
    in_form = {b["text"]: b["inForm"] for b in summary(page)["buttons"]}
    assert in_form["Save and Continue"] is True and in_form["Subscribe"] is False
    assert classify(page)["kind"] == "form_step"


def test_the_summary_carries_no_button_type_or_marker(page, load):
    load(page, "<button data-automation-id='someMarker with page text'>Next</button>", SOURCES)
    assert "someMarker" not in json.dumps(summary(page))


def test_a_boards_easy_apply_page_with_a_stray_control_is_board_native(page, load):
    body = "<h1>Data Analyst</h1><label for='s'>Salary</label><input id='s'><button>Easy Apply</button>"
    page.route("https://www.linkedin.com/jobs/view/2", lambda route: route.fulfill(
        status=200, content_type="text/html", body=body))
    page.goto("https://www.linkedin.com/jobs/view/2")
    for src in SOURCES:
        page.add_script_tag(content=(EXTENSION / src).read_text(encoding="utf-8"))
    assert classify(page)["kind"] == "board_native"


# ---------- the posting's Apply: the one narrow exception ----------

CLICK = "onclick='window.hit = (window.hit || 0) + 1; return false;'"


@pytest.mark.parametrize("html", [
    f"<h1>Analyst</h1><a href='https://jobs.acme.test/jobs/9/apply' {CLICK}>Apply</a>",
    f"<h1>Analyst</h1><a href='https://jobs.acme.test/jobs/9/apply' {CLICK}>Apply now</a>",
    f"<h1>Analyst</h1><a href='https://jobs.acme.test/jobs/9/apply' {CLICK}>Apply for this job</a>",
    f"<h1>Analyst</h1><a href='https://jobs.acme.test/jobs/9/apply' role='button' {CLICK}>  APPLY  </a>",
    f"<h1>Analyst</h1><a href='https://jobs.acme.test/jobs/9/apply' {CLICK} aria-label='Apply for Staff Engineer at Acme'>Apply</a>",
    f"<h1>Analyst</h1><a href='https://jobs.acme.test/jobs/9/apply' {CLICK} title='Apply to this role'>Apply now</a>",
])
def test_the_postings_plain_apply_is_named_and_pressed_only_by_the_apply_call(page, load, html):
    load(page, html, SOURCES)
    assert classify(page)["kind"] == "posting"
    s = summary(page)   # after classify, which reads the page too and retires the ids before it
    assert s["applyId"]
    # Without the flag it is the Submit word it always was (a bare link is no button at all).
    assert advance(page, s["applyId"])["clicked"] is False
    assert page.evaluate("() => window.hit || 0") == 0
    result, url = landing(page, lambda: advance_apply(page, s["applyId"]))
    assert result == {"clicked": True}
    # The tab went to the link's address. Its own handler (which would have recorded a hit and
    # cancelled the navigation) never ran: the press is a navigation, not a click.
    assert url.startswith("https://jobs.acme.test/jobs/9/apply")


@pytest.mark.parametrize("html", [
    f"<h1>Analyst</h1><button {CLICK}>Apply</button>",
    f"<h1>Analyst</h1><button {CLICK}>Apply now</button>",
    f"<h1>Analyst</h1><input type='button' value='Apply now' {CLICK}>",
    f"<h1>Analyst</h1><button {CLICK} aria-label='Apply for Staff Engineer at Acme'>Apply</button>",
])
def test_a_form_less_apply_button_is_neither_named_nor_pressed(page, load, html):
    """Owner decision (batch-4 review): only a real navigation link is ever pressed. A button is page
    script (a quick-apply, a form-less draft review) that may record or send a submission."""
    load(page, html + "<script>window.submitted = 0; for (const el of document.querySelectorAll('button,input,div'))"
                      " el.addEventListener('click', () => { window.submitted += 1; });</script>", SOURCES)
    s = summary(page)
    assert s["applyId"] is None
    for b in s["buttons"]:
        assert advance_apply(page, b["id"])["clicked"] is False
        assert advance(page, b["id"])["clicked"] is False
    assert page.evaluate("() => [window.hit || 0, window.submitted]") == [0, 0]
    assert classify(page)["kind"] == "posting"


@pytest.mark.parametrize("html", [
    f"<h1>A</h1><button {CLICK}>Submit application</button>",
    f"<h1>A</h1><button {CLICK}>Apply and submit</button>",
    f"<h1>A</h1><button {CLICK}>Reapply</button>",
    f"<h1>A</h1><button {CLICK}>Apply-now</button>",
    f"<h1>A</h1><button {CLICK} aria-label='Apply and submit my application'>Apply</button>",
    f"<h1>A</h1><button {CLICK} aria-label='Apply for the role and submit'>Apply</button>",
    f"<h1>A</h1><button {CLICK} title='Send my application'>Apply</button>",
    f"<h1>A</h1><button {CLICK} aria-label='Submit'>Apply</button>",
    f"<h1>A</h1><button {CLICK} aria-label='Apply'>Next</button>",
    f"<h1>A</h1><button {CLICK}>Apply on the company site</button>",
    f"<h1>A</h1><button {CLICK}>Next</button>",
])
def test_nothing_but_a_plain_apply_is_ever_named_or_pressed_as_one(page, load, html):
    load(page, html, SOURCES)
    s = summary(page)
    assert s["applyId"] is None
    for b in s["buttons"]:
        assert advance_apply(page, b["id"])["clicked"] is False
    assert page.evaluate("() => window.hit || 0") == 0


def test_the_apply_call_refuses_a_page_that_has_fields(page, load):
    """An Apply-worded button beside a fillable control is a form's Submit, not a posting's link."""
    load(page, f"<label for='a'>Name</label><input id='a'><a href='https://jobs.acme.test/9' {CLICK}>Apply</a>", SOURCES)
    s = summary(page)
    assert advance_apply(page, s["applyId"]) == {"clicked": False, "why": "not_posting"}
    assert page.evaluate("() => window.hit || 0") == 0


def test_the_apply_call_refuses_a_stale_hidden_or_untagged_target(page, load):
    load(page, f"<h1>A</h1><a id='b' href='https://jobs.acme.test/9' {CLICK}>Apply</a><button id='n' {CLICK}>Next</button>", SOURCES)
    old = summary(page)["applyId"]
    fresh = summary(page)["applyId"]
    assert old != fresh
    assert advance_apply(page, old) == {"clicked": False, "why": "not_apply"}
    for target in ("nope", "", None, 3):
        assert advance_apply(page, target) == {"clicked": False, "why": "not_apply"}
    # A Next button is not an Apply, whatever the caller says.
    next_id = next(b["id"] for b in summary(page)["buttons"] if b["text"] == "Next")
    assert advance_apply(page, next_id) == {"clicked": False, "why": "not_apply"}
    page.evaluate("() => { document.getElementById('b').style.visibility = 'hidden'; }")
    assert advance_apply(page, fresh) == {"clicked": False, "why": "not_apply"}
    assert page.evaluate("() => window.hit || 0") == 0


def test_an_apply_relabelled_between_the_summary_and_the_press_is_refused(page, load):
    load(page, f"<h1>A</h1><a id='b' href='https://jobs.acme.test/9' {CLICK}>Apply</a>", SOURCES)
    apply_id = summary(page)["applyId"]
    page.evaluate("() => { document.getElementById('b').textContent = 'Submit application'; }")
    assert advance_apply(page, apply_id) == {"clicked": False, "why": "not_apply"}
    assert page.evaluate("() => window.hit || 0") == 0


def test_a_review_like_page_with_no_fields_is_a_posting_to_the_page_and_the_drivers_filled_flag_decides(page, load):
    """After a fill, a field-less page with an Apply-worded button reads as a posting to the page
    (it has no way to know). The driver's `filled` flag is what makes it the review page; this pins
    that the page itself reports it as an Apply it WOULD press, so that flag is load-bearing."""
    load(page, f"<h1>Review</h1><button {CLICK}>Apply</button>", SOURCES)
    assert classify(page)["kind"] == "posting"


@pytest.mark.parametrize("word", PIN_WORDS)
@pytest.mark.parametrize("flavour", sorted(FLAVOURS))
def test_the_apply_call_presses_no_button_flavour_at_any_wording(page, load, word, flavour):
    load(page, FLAVOURS[flavour].format(w=word), SOURCES)
    page.evaluate("""() => {
      window.hit = 0;
      document.getElementById('t').addEventListener('click', (e) => { e.preventDefault(); window.hit += 1; });
    }""")
    s = summary(page)
    # None of these is a real link (the "link button" is `<a href='#'>`, which goes nowhere): the
    # apply call presses nothing, whatever the wording.
    ids = [b["id"] for b in s["buttons"]] + ["unknown-id", ""]
    assert [advance_apply(page, i)["clicked"] for i in ids].count(True) == 0
    assert page.evaluate("() => window.hit") == 0
    assert s["applyId"] is None


def test_the_step_key_tells_steps_apart_and_never_carries_the_heading(page, load):
    load(page, "<h1>Your contact details</h1><button>Next</button>", SOURCES)
    one = summary(page)["stepKey"]
    again = summary(page)["stepKey"]
    load(page, "<h1>Work history</h1><button>Next</button>", SOURCES)
    two = summary(page)["stepKey"]
    assert one and one == again and one != two
    assert "contact" not in one.lower() and "work" not in two.lower()
    load(page, "<nav><h2>Site menu</h2></nav><p>no heading</p>", SOURCES)
    assert summary(page)["stepKey"] == ""


# What would submit a form is never pressed as an Apply, whatever the page shows around it.

FORM_APPLY = [
    "<form><input type='hidden' name='draft' value='1'><button {c}>Apply</button></form>",
    "<form><input type='hidden' name='draft' value='1'><button type='button' {c}>Apply</button></form>",
    "<form><input type='hidden' name='draft' value='1'><input type='submit' value='Apply' {c}></form>",
    "<form><input type='hidden' name='draft' value='1'><input type='button' value='Apply' {c}></form>",
    "<form id='f'><input type='hidden' name='draft'></form><button form='f' {c}>Apply</button>",
    "<form><input type='file' style='display:none'><input readonly value='x'><button {c}>Apply now</button></form>",
]


@pytest.mark.parametrize("html", FORM_APPLY)
def test_an_apply_that_belongs_to_a_form_is_neither_named_nor_pressed(page, load, html):
    load(page, "<h1>Review</h1>" + html.format(c=CLICK), SOURCES)
    s = summary(page)
    assert s["fillable"] == 0 and s["hasApplyLink"] is True and s["applyId"] is None
    for b in s["buttons"]:
        assert advance_apply(page, b["id"])["clicked"] is False
    assert page.evaluate("() => window.hit || 0") == 0


def test_the_apply_call_names_the_link_beside_a_forms_apply_button_not_the_button(page, load):
    load(page, f"<form><button {CLICK}>Apply</button></form><a href='https://jobs.acme.test/jobs/9/apply' {CLICK}>Apply</a>", SOURCES)
    s = summary(page)
    result, url = landing(page, lambda: advance_apply(page, s["applyId"]))
    assert result == {"clicked": True} and url.startswith("https://jobs.acme.test/jobs/9/apply")


@pytest.mark.parametrize("href, target", [
    ("#", None), ("#apply", None), ("", None),
    ("javascript:void(0)", None), (" JavaScript:go()", None), ("JAVASCRIPT:go()", None),
    ("java&#10;script:go()", None), ("java&#9;script:go()", None), ("jav&#x61;script:go()", None),
    ("data:text/html,hi", None), ("mailto:jobs@acme.test", None), ("ftp://acme.test/apply", None),
    ("/jobs/9/apply", "_blank"), ("/jobs/9/apply", "_BLANK"), ("/jobs/9/apply", " _Blank "),
    ("/jobs/9/apply", "applywin"), ("/jobs/9/apply", "_top"), ("/jobs/9/apply", "_parent"),
])
def test_a_link_that_goes_nowhere_or_opens_a_tab_is_not_an_apply_the_run_presses(page, load, href, target):
    attr = f" target='{target}'" if target else ""
    load(page, f"<h1>A</h1><a href='{href}'{attr} {CLICK}>Apply</a>", SOURCES)
    s = summary(page)
    assert s["applyId"] is None
    assert page.evaluate("() => window.hit || 0") == 0


@pytest.mark.parametrize("attr", ["", " target='_self'", " target='_SELF'", " target=''"])
def test_a_same_tab_http_link_is_pressable_whatever_the_case_of_self(page, load, attr):
    load(page, f"<h1>A</h1><a href='https://jobs.acme.test/jobs/9/apply'{attr} {CLICK}>Apply</a>", SOURCES)
    s = summary(page)
    assert s["applyId"]
    result, url = landing(page, lambda: advance_apply(page, s["applyId"]))
    assert result == {"clicked": True} and url.startswith("https://jobs.acme.test/jobs/9/apply")


def test_an_absolute_https_link_is_pressable(page, load):
    load(page, f"<h1>A</h1><a href='https://careers.acme.test/9' {CLICK}>Apply</a>", SOURCES)
    assert summary(page)["applyId"]


def test_a_base_target_that_opens_a_tab_makes_a_targetless_link_unpressable(page, load):
    load(page, f"<base target='_blank'><h1>A</h1><a href='https://jobs.acme.test/jobs/9/apply' {CLICK}>Apply</a>", SOURCES)
    assert summary(page)["applyId"] is None
    load(page, f"<base target='_blank'><h1>A</h1><a href='https://jobs.acme.test/jobs/9/apply' target='_self' {CLICK}>Apply</a>", SOURCES)
    assert summary(page)["applyId"]


def test_the_press_re_checks_the_link_if_the_page_rewrites_it_after_naming(page, load):
    load(page, f"<h1>A</h1><a id='a' href='https://jobs.acme.test/jobs/9/apply' {CLICK}>Apply</a>", SOURCES)
    apply_id = summary(page)["applyId"]
    page.evaluate("() => document.getElementById('a').setAttribute('target', 'applywin')")
    assert advance_apply(page, apply_id) == {"clicked": False, "why": "would_submit"}
    page.evaluate("() => { const a = document.getElementById('a'); a.removeAttribute('target'); a.setAttribute('href', 'java&#10;script:go()'.replace('&#10;', String.fromCharCode(10))); }")
    assert advance_apply(page, apply_id) == {"clicked": False, "why": "would_submit"}
    assert page.evaluate("() => window.hit || 0") == 0


def test_the_apply_call_re_checks_that_it_is_still_a_link_at_press_time(page, load):
    """Named while it was a link; the page then swaps it for a button of the same id and text."""
    load(page, f"<h1>A</h1><a id='b' href='https://jobs.acme.test/9'>Apply</a>", SOURCES)
    apply_id = summary(page)["applyId"]
    assert apply_id
    page.evaluate("""() => { const b = document.createElement('button'); b.id = 'b2'; b.textContent = 'Apply';
      b.onclick = () => { window.hit = 1; }; const a = document.getElementById('b');
      b.setAttribute('data-maestro-btn', a.getAttribute('data-maestro-btn')); a.replaceWith(b); }""")
    assert advance_apply(page, apply_id) == {"clicked": False, "why": "would_submit"}
    assert page.evaluate("() => window.hit || 0") == 0


# ---------- the driver against the REAL page reader (the Apply exception's four scenarios) ----------

DRIVE = """async ({record, swap, signIn}) => {
  const ns = window.careerStudioCompanion;
  const calls = [];
  let clock = 0;   // every read of the clock moves it, so a wait for a page can reach its cap
  const deps = {
    openTab: async () => 1,
    classify: async () => [{frameId: 0, result: {summary: ns.pageReader.summary(), top: true}}],
    tabUrl: async () => location.href,
    advance: async (tabId, frameId, id, opts) => {
      calls.push(["advance", opts?.apply === true]);
      return ns.pageReader.advance(id, opts);
    },
    fill: async () => ({fields: []}),
    signIn: async () => { calls.push(["signIn"]); document.body.innerHTML = swap; return {signedIn: true}; },
    waitForChange: async () => ({changed: Boolean(signIn)}),
    pageErrors: async () => ({count: 0, items: []}), pageRequired: async () => ({count: 0, items: []}), fix: async () => ({fixed: false}),
    attachTo: async () => ({attached: false}),
    uploads: async () => [],
    sleep: async () => {}, save() {}, onUpdate() {}, now: () => (clock += 1000), cancelled: () => false,
  };
  await ns.queueRun.drive(record, deps);
  return {status: record.status, why: record.why, calls, hit: window.hit || 0};
}"""

APPLY_URL = "https://jobs.acme.test/apply"
WORKDAY_URL = "https://acme.wd5.myworkdayjobs.com/apply"   # the saved login is typed only on a known ATS host
DRAFT_REVIEW = f"<h1>Review your draft</h1><form><input type='hidden' name='d' value='1'><button {CLICK}>Apply</button></form>"


def run_driver(page, *, swap="", signIn=False, **record):
    base = {"openUrl": "https://jobs.acme.test/apply", "tabId": None, "hosts": [], "seen": [], "step": 0}
    return page.evaluate(DRIVE, {"record": {**base, **record}, "swap": swap, "signIn": signIn})


def test_a_fresh_run_whose_first_page_has_an_apply_link_presses_it(page, load):
    serve(page, APPLY_URL, f"<h1>Analyst at Acme</h1><a href='https://jobs.acme.test/jobs/9/apply' {CLICK}>Apply</a>")
    # The navigation can destroy the evaluate's context first; the landing address is the evidence.
    page.route(re.compile(r"https://jobs\.acme\.test/jobs/.*"), lambda route: route.fulfill(
        status=200, content_type="text/html", body="<p>landed</p>"))
    with page.expect_navigation() as nav:
        try:
            out = run_driver(page)
            assert out["calls"] == [["advance", True]] and out["hit"] == 0
        except PlaywrightError as err:
            if "context was destroyed" not in str(err):
                raise
    assert nav.value.url == "https://jobs.acme.test/jobs/9/apply"


def test_a_draft_review_page_with_only_hidden_inputs_and_an_apply_submit_is_never_pressed(page, load):
    serve(page, APPLY_URL, DRAFT_REVIEW)
    out = run_driver(page)
    assert out["hit"] == 0 and out["calls"] == [] and (out["status"], out["why"]) == ("parked", "posting")


def test_the_same_page_reached_after_a_sign_in_is_never_pressed(page, load):
    serve(page, WORKDAY_URL, "<h1>Sign in</h1><form><label for='e'>Email</label><input id='e' type='email'>"
                           "<input type='password'><button type='button'>Sign in</button></form>")
    out = run_driver(page, swap=DRAFT_REVIEW, signIn=True, openUrl=WORKDAY_URL)
    assert out["calls"] == [["signIn"]] and out["hit"] == 0
    assert (out["status"], out["why"]) == ("parked", "posting")


def test_a_resume_onto_a_posting_looking_page_is_never_pressed(page, load):
    serve(page, APPLY_URL, f"<h1>Analyst at Acme</h1><a href='https://jobs.acme.test/jobs/9/apply' {CLICK}>Apply</a>")
    out = run_driver(page, tabId=7, status="parked", why="captcha", hosts=["jobs.acme.test"])
    assert out["calls"] == [] and out["hit"] == 0 and out["why"] == "posting"


# ---------- the ATS table's verdicts (Task 14) ----------

ATS = "window.careerStudioCompanion.atsButtons"


def serve(page, url, body):
    """Serve `body` at `url` (the route answers the page request; the context is offline) and load
    the extension on it, so `location.hostname` is the vendor's."""
    page.route(url, lambda route: route.fulfill(status=200, content_type="text/html", body=body))
    page.goto(url)
    for src in SOURCES:
        page.add_script_tag(content=(EXTENSION / src).read_text(encoding="utf-8"))


ODD_SUBMIT_STEP = """<form><label for='a'>Name</label><input id='a'>
  <button type='button'>Back</button>
  <input type='submit' id='submit_app' value='Done' onclick='window.hit = 1; return false;'></form>"""


SUBMIT_ENTRY = """() => {
  window.careerStudioCompanion.atsButtons.HOSTS.acmeats = /^ats\\.acme-example\\.test$/;
  window.careerStudioCompanion.atsButtons.RULES.push(
    { vendor: "acmeats", buttons: [{ id: "submit_app", verdict: "submit" }] });
}"""


def test_a_table_submit_is_a_submit_even_when_it_reads_done(page):
    """The wiring for a verdict of "submit", with an entry no shipped table has (a made-up vendor
    added for this test only). The sort alone calls "Done" unclear and would offer no Submit at
    all; the marker says it is one. The page stops, and nothing is clicked."""
    serve(page, "https://ats.acme-example.test/apply", ODD_SUBMIT_STEP)
    page.evaluate(SUBMIT_ENTRY)
    assert classify(page)["kind"] == "review"   # classify re-tags the buttons, so read ids after it
    s = summary(page)
    done = button(s, "Done")
    assert done["known"] == "submit"
    assert "known" not in button(s, "Back")
    assert advance(page, done["id"]) == {"clicked": False, "why": "submit"}
    assert page.evaluate("() => window.hit === 1") is False


def test_a_marker_looking_id_on_a_host_with_no_rows_has_no_verdict(page):
    """The shipped table has no row for this host, so the summary carries no `known` key at all.
    The text ("Done") is unclear, but the control's own id is a Submit signal."""
    serve(page, "https://careers.acme-example.test/jobs/1", ODD_SUBMIT_STEP)
    s = summary(page)
    assert all("known" not in b for b in s["buttons"])
    # The id says submit, and a page names its Submit that way when the label is "Done": it stops.
    assert advance(page, button(s, "Done")["id"]) == {"clicked": False, "why": "submit"}
    assert classify(page)["kind"] == "review"


NEXT_ENTRY = """() => {
  window.careerStudioCompanion.atsButtons.HOSTS.acmeats = /^ats\\.acme-example\\.test$/;
  window.careerStudioCompanion.atsButtons.RULES.push(
    { vendor: "acmeats", buttons: [{ automationId: "go-on", verdict: "next" }] });
}"""
NEXT_PAGE = """<form><label for='a'>Name</label><input id='a'>
  <button type='button' data-automation-id='go-on' onclick='window.hit = 1'>{text}</button></form>"""


def test_a_table_next_makes_an_odd_label_the_step_and_advance_clicks_it(page):
    """The wiring for a verdict of "next", with an entry no shipped table has (a made-up vendor
    added for this test only): summary carries it, classify offers the button, advance presses it."""
    serve(page, "https://ats.acme-example.test/apply", NEXT_PAGE.format(text="Go"))
    page.evaluate(NEXT_ENTRY)
    offered = classify(page)
    assert offered["kind"] == "form_step"
    go = page.evaluate(f"() => {READER}.summary().buttons[0]")   # ids are re-minted on every read
    assert go["known"] == "next"
    assert advance(page, go["id"]) == {"clicked": True}
    assert page.evaluate("() => window.hit === 1")


def test_advance_rederives_the_verdict_and_never_trusts_the_summary(page):
    """An id the summary offered as a table Next stops being one the moment the table no longer
    says so: nothing the panel was told earlier reaches the click."""
    serve(page, "https://ats.acme-example.test/apply", NEXT_PAGE.format(text="Go"))
    page.evaluate(NEXT_ENTRY)
    go = summary(page)["buttons"][0]
    assert go["known"] == "next"
    page.evaluate("() => window.careerStudioCompanion.atsButtons.RULES.pop()")
    assert advance(page, go["id"]) == {"clicked": False, "why": "not_next"}
    assert page.evaluate("() => window.hit === 1") is False


def test_a_submit_word_beats_a_table_next_at_click_time(page):
    """Relabelled after the summary, a table-Next button that now says Submit is refused as one."""
    serve(page, "https://ats.acme-example.test/apply", NEXT_PAGE.format(text="Go"))
    page.evaluate(NEXT_ENTRY)
    go = summary(page)["buttons"][0]
    page.evaluate("() => { document.querySelector('[data-automation-id=go-on]').textContent = 'Submit application'; }")
    assert advance(page, go["id"]) == {"clicked": False, "why": "submit"}
    assert page.evaluate("() => window.hit === 1") is False
    assert classify(page)["kind"] == "review"


# ---------- sign-in with the saved login (Task 15) ----------

# Made-up credentials: this repo is public, and these never leave the test page.
LOGIN = {"email": "ada@acme.test", "password": "Pw-Zelda-9-not-real", "allowedHost": "x.test"}


def sign_in(page, **over):
    return page.evaluate(f"(a) => {READER}.signIn(a)", {**LOGIN, **over})


def serve_signin(page, name="signin.html", url="https://x.test/signin"):
    serve(page, url, fixture_html(name))


def test_sign_in_types_both_values_and_clicks_sign_in(page):
    serve_signin(page)
    result = sign_in(page)
    assert result == {"signedIn": "clicked"}
    assert oracle(page, "typed") == {"email": LOGIN["email"], "password": LOGIN["password"]}
    assert oracle(page, "signedIn") is True
    # Nothing in what comes back carries either value.
    assert LOGIN["password"] not in json.dumps(result) and LOGIN["email"] not in json.dumps(result)


def test_sign_in_never_writes_the_password_to_the_console(page):
    seen = []
    page.on("console", lambda m: seen.append(m.text))
    serve_signin(page)
    sign_in(page)
    assert LOGIN["password"] not in " ".join(seen)


@pytest.mark.parametrize("allowed", ["y.test", "x.test.evil.example", "evil-x.test", "www.x.test"])
def test_a_host_mismatch_types_nothing(page, allowed):
    serve_signin(page)
    assert sign_in(page, allowedHost=allowed) == {"signedIn": False, "why": "host"}
    assert oracle(page, "typed") == {"email": "", "password": ""}
    assert oracle(page, "signedIn") is False


def test_a_missing_host_or_credential_types_nothing(page):
    serve_signin(page)
    for over in ({"allowedHost": None}, {"password": ""}, {"password": None}, {"email": ""}, {"email": 3}):
        assert sign_in(page, **over)["signedIn"] is False, over
    assert oracle(page, "typed") == {"email": "", "password": ""}


def test_the_host_comparison_ignores_case(page):
    serve_signin(page)
    assert sign_in(page, allowedHost="X.Test") == {"signedIn": "clicked"}


def _frame_with_signin(page, srcdoc_name="signin.html"):
    """A top page on x.test whose only sign-in form is inside an iframe, with the engine loaded in
    BOTH frames (the manifest runs it in every frame)."""
    import html
    body = f"<h1>Careers</h1><iframe id='f' srcdoc=\"{html.escape(fixture_html(srcdoc_name))}\"></iframe>"
    serve(page, "https://x.test/careers", body)
    page.wait_for_function("() => document.getElementById('f').contentDocument?.getElementById('pw')")
    child = next(f for f in page.frames if f != page.main_frame)
    for src in SOURCES:
        child.add_script_tag(content=(EXTENSION / src).read_text(encoding="utf-8"))
    return child


def test_a_sign_in_form_inside_an_iframe_is_never_filled(page):
    child = _frame_with_signin(page)
    # Asked inside the subframe, it refuses before looking at anything else (even with the host right).
    got = child.evaluate(f"(a) => {READER}.signIn(a)", {**LOGIN, "allowedHost": ""})
    assert got == {"signedIn": False, "why": "frame"}
    # Asked of the top document, the form it cannot see is not there to fill.
    assert sign_in(page)["signedIn"] is False
    typed = child.evaluate("() => window.__oracle.typed")
    assert typed == {"email": "", "password": ""}
    assert child.evaluate("() => window.__oracle.signedIn") is False


def test_a_create_account_page_is_refused_with_nothing_typed(page):
    serve_signin(page, "create_account.html")
    assert sign_in(page) == {"signedIn": False, "why": "create_account"}
    assert page.evaluate("() => [...document.querySelectorAll('input')].map((i) => i.value)") == ["", "", ""]


def test_a_lone_new_password_box_is_a_sign_up_too(page):
    serve(page, "https://x.test/join", "<input type='email'><input type='password' autocomplete='new-password'>"
                                      "<button>Continue</button>")
    assert sign_in(page) == {"signedIn": False, "why": "create_account"}


def test_a_visible_captcha_parks_a_sign_in_page(page):
    body = (fixture_html("signin.html").replace(
        "</main>", "<iframe src='about:blank#recaptcha/api2/bframe' style='width:400px;height:580px'></iframe></main>"))
    serve(page, "https://x.test/signin", body)
    assert sign_in(page) == {"signedIn": False, "why": "captcha"}
    assert oracle(page, "typed") == {"email": "", "password": ""}


def test_an_email_code_page_is_not_a_sign_in(page):
    serve_signin(page, "verify_code.html")
    assert sign_in(page) == {"signedIn": False, "why": "no_form"}


def test_a_code_box_beside_the_password_parks(page):
    serve(page, "https://x.test/signin", "<input type='email'><input type='password'>"
          "<label>Verification code <input name='code' autocomplete='one-time-code'></label><button>Sign in</button>")
    assert sign_in(page) == {"signedIn": False, "why": "verify"}


@pytest.mark.parametrize("buttons", [
    "<button>Submit application</button>",
    "<button>Sign in and submit</button>",
    "<button>Sign in with Google</button>",
    "<button aria-label='Submit application'>Sign in</button>",
    "<button style='display:none'>Sign in</button>",
    "",
])
def test_without_a_plain_sign_in_button_nothing_is_typed(page, buttons):
    """The button is found BEFORE anything is typed, so a page with no safe button never holds
    the password. A Submit-worded label (any source) is never the sign-in button."""
    serve(page, "https://x.test/signin", f"<form><input type='email'><input type='password'>{buttons}</form>")
    assert sign_in(page) == {"signedIn": False, "why": "no_button"}
    assert page.evaluate("() => [...document.querySelectorAll('input')].map((i) => i.value)") == ["", ""]


ENABLE_ON_INPUT = """<form onsubmit='return false'><input id='e' type='email'><input id='p' type='password'>
  <button id='b' disabled onclick='window.hit = 1'>Sign in</button></form><script>
  const [e, p, b] = ['e', 'p', 'b'].map((id) => document.getElementById(id));
  const sync = () => { b.disabled = {rule}; };
  e.addEventListener('input', sync); p.addEventListener('input', sync);</script>"""


def test_a_sign_in_button_that_enables_after_both_boxes_are_filled_still_signs_in(page):
    serve(page, "https://x.test/signin", ENABLE_ON_INPUT.replace("{rule}", "!(e.value && p.value)"))
    assert sign_in(page) == {"signedIn": "clicked"}
    assert page.evaluate("() => window.hit") == 1


def test_a_sign_in_button_that_stays_disabled_after_typing_is_not_clicked(page):
    serve(page, "https://x.test/signin", ENABLE_ON_INPUT.replace("{rule}", "true"))
    assert sign_in(page) == {"signedIn": False, "why": "button"}
    assert page.evaluate("() => window.hit === 1") is False


@pytest.mark.parametrize("label", ["Sign in", "Log in", "LOGIN", "Continue", "Next", "  sign   in "])
def test_the_sign_in_button_is_any_of_the_plain_wordings(page, label):
    serve(page, "https://x.test/signin", f"<form><input type='email'><input type='password'>"
          f"<button type='button' onclick='window.hit = 1'>{label}</button></form>")
    assert sign_in(page) == {"signedIn": "clicked"}
    assert page.evaluate("() => window.hit") == 1


def test_the_email_box_is_found_by_type_then_autocomplete_then_label(page):
    password = "<input type='password'><button>Sign in</button>"
    for markup, expected in [
        ("<input type='text' id='a'><input type='email' id='b'>", "b"),
        ("<input type='text' id='a'><input type='text' autocomplete='username' id='b'>", "b"),
        ("<label>Username <input id='b'></label><input id='a'>", "b"),
        ("<label>Work e-mail <input id='b'></label><input id='a'>", "b"),
    ]:
        serve(page, "https://x.test/signin", f"<form onsubmit='return false'>{markup}{password}</form>")
        assert sign_in(page) == {"signedIn": "clicked"}
        assert page.evaluate("(id) => document.getElementById(id).value", expected) == LOGIN["email"]
        assert page.evaluate("() => document.getElementById('a').value") == ""


def test_a_sign_in_page_with_no_email_box_types_nothing(page):
    serve(page, "https://x.test/signin", "<form><input type='text' aria-label='Search'><input type='password'>"
                                         "<button>Sign in</button></form>")
    assert sign_in(page) == {"signedIn": False, "why": "no_email"}
    assert page.evaluate("() => [...document.querySelectorAll('input')].map((i) => i.value)") == ["", ""]


@pytest.mark.parametrize("window", ["page", "page_unfocused"])
def test_a_react_style_controlled_box_takes_the_typing(window, request):
    """The values arrive as real input events, so a framework that only listens to them sees both,
    and each box hears focus and blur like a person's visit (a validating form commits on blur),
    in a focused window and in one that fires no focus events of its own."""
    page = request.getfixturevalue(window)
    serve(page, "https://x.test/signin", """<form id='f' onsubmit='return false'><input id='e' type='email'><input id='p' type='password'>
      <button>Sign in</button></form><script>
      window.state = {e: '', p: ''}; window.heard = [];
      for (const id of ['e', 'p']) {
        const box = document.getElementById(id);
        box.addEventListener('input', (ev) => { window.state[id] = ev.target.value; });
        for (const t of ['focus', 'blur']) box.addEventListener(t, () => window.heard.push(id + ':' + t));
      }
      </script>""")
    assert sign_in(page) == {"signedIn": "clicked"}
    assert page.evaluate("() => window.state") == {"e": LOGIN["email"], "p": LOGIN["password"]}
    assert page.evaluate("() => window.heard") == ["e:focus", "e:blur", "p:focus", "p:blur"]


# ---------- sign-in never leaks an error, re-checks its button, and spots a sign-up form ----------

def test_a_click_that_throws_the_password_leaks_none_of_it(page):
    """Listener exceptions never propagate out of click(), so the throw is modelled where the page
    can make one propagate: an own `click` on the button (this harness shares the page's world)."""
    serve(page, "https://x.test/signin", """<form onsubmit='return false'><input id='e' type='email'><input id='p' type='password'>
      <button id='b'>Sign in</button></form><script>
      document.getElementById('b').click = () => { throw new Error('bad ' + document.getElementById('p').value); };
      </script>""")
    result = sign_in(page)
    assert result == {"signedIn": False, "why": "click"}
    assert LOGIN["password"] not in json.dumps(result)


def test_a_throw_while_typing_is_a_fixed_word_not_the_message(page):
    serve(page, "https://x.test/signin", """<form onsubmit='return false'><input id='e' type='email'><input id='p' type='password'>
      <button>Sign in</button></form><script>
      const p = document.getElementById('p');
      p.select = () => { throw new Error('leak ' + p.value + document.getElementById('e').value); };
      </script>""")
    result = sign_in(page)
    assert result["signedIn"] is False
    assert LOGIN["password"] not in json.dumps(result) and LOGIN["email"] not in json.dumps(result)


def test_a_button_relabelled_while_typing_is_not_clicked(page):
    """The button was judged before typing; the page's input handler turns it into a Submit."""
    serve(page, "https://x.test/signin", """<form onsubmit='return false'><input id='e' type='email'><input id='p' type='password'>
      <button id='b' onclick='window.hit = 1'>Sign in</button></form><script>
      document.getElementById('e').addEventListener('input', () => { document.getElementById('b').textContent = 'Submit application'; });
      </script>""")
    assert sign_in(page) == {"signedIn": False, "why": "button"}
    assert page.evaluate("() => window.hit === 1") is False


@pytest.mark.parametrize("change", [
    "b.disabled = true", "b.style.display = 'none'", "b.remove()", "b.textContent = 'Apply now'",
])
def test_a_button_that_stops_being_a_plain_sign_in_while_typing_is_not_clicked(page, change):
    serve(page, "https://x.test/signin", f"""<form onsubmit='return false'><input id='e' type='email'><input id='p' type='password'>
      <button id='b' onclick='window.hit = 1'>Sign in</button></form><script>
      document.getElementById('e').addEventListener('input', () => {{ const b = document.getElementById('b'); {change}; }});
      </script>""")
    assert sign_in(page) == {"signedIn": False, "why": "button"}
    assert page.evaluate("() => window.hit === 1") is False


@pytest.mark.parametrize("token", ["new-password", "section-signup new-password", "NEW-PASSWORD billing"])
def test_a_new_password_token_in_a_list_is_a_sign_up(page, token):
    serve(page, "https://x.test/join", f"<form onsubmit='return false'><input type='email'>"
          f"<input type='password' autocomplete='{token}'><button>Continue</button></form>")
    assert sign_in(page) == {"signedIn": False, "why": "create_account"}
    assert page.evaluate("() => [...document.querySelectorAll('input')].map((i) => i.value)") == ["", ""]


def test_an_autocomplete_list_with_current_password_is_still_a_sign_in(page):
    serve(page, "https://x.test/signin", "<form onsubmit='return false'><input type='email'>"
          "<input type='password' autocomplete='section-login current-password'><button>Sign in</button></form>")
    assert sign_in(page) == {"signedIn": "clicked"}


@pytest.mark.parametrize("attrs, box", [("disabled", "password"), ("readonly", "password"),
                                        ("disabled", "email"), ("readonly", "email")])
def test_a_disabled_or_read_only_box_parks_before_anything_is_typed(page, attrs, box):
    email = f"<input type='email' {attrs if box == 'email' else ''}>"
    password = f"<input type='password' {attrs if box == 'password' else ''}>"
    serve(page, "https://x.test/signin", f"<form onsubmit='return false'>{email}{password}<button>Sign in</button></form>")
    result = sign_in(page)
    assert result["signedIn"] is False and result["why"] in ("locked", "no_email")
    assert page.evaluate("() => [...document.querySelectorAll('input')].map((i) => i.value)") == ["", ""]


# ---------- the ordinary fill never lists a password input ----------

def _inventory(page, **opts):
    return page.evaluate(f"async (o) => (await window.careerStudioCompanion.fillOps.inventory(o)).fields", opts)


@pytest.mark.parametrize("name", ["signin.html", "create_account.html"])
def test_the_fill_inventory_never_lists_a_password_input_even_with_consent(page, load, name):
    """`consentForms: true` lifts every LABEL refusal; a password is refused by its SHAPE, so no
    setting reaches it. The listed questions are the email box at most."""
    load(page, fixture_html(name), SOURCES)
    for opts in ({}, {"consentForms": True, "runId": "r1"}):
        fields = _inventory(page, **opts)
        assert all("assword" not in f["question"] for f in fields), fields
        assert page.evaluate("() => [...document.querySelectorAll('input[type=password]')].length") >= 1


def test_the_inventory_lists_no_password_even_when_the_box_is_labelled_like_a_plain_field(page, load):
    load(page, "<label>Email <input type='password' autocomplete='new-password'></label>"
               "<label>Full name <input type='password' name='name'></label>", SOURCES)
    assert _inventory(page, consentForms=True, runId="r1") == []


def test_the_inventory_lists_no_box_that_declares_itself_a_password_by_autocomplete(page, load):
    """A show-password toggle turns a password box into type=text: its autocomplete token still says
    what it is, and that is a shape, not a label."""
    load(page, "<label>Choose a password <input type='text' autocomplete='new-password'></label>"
               "<label>Current <input autocomplete='current-password'></label>"
               "<label>Nickname <input autocomplete='nickname'></label>", SOURCES)
    assert [f["question"] for f in _inventory(page, consentForms=True, runId="r1")] == ["Nickname"]


def test_a_text_box_that_says_new_password_only_to_stop_autofill_is_an_ordinary_field(page, load):
    """Forms put autocomplete=new-password on any text box to stop the browser's autofill. Only a
    box whose own name, id, label or placeholder says password counts as one."""
    load(page, "<label>City <input type='text' name='city' autocomplete='new-password'></label>"
               "<button>Next</button>", SOURCES)
    s = summary(page)
    assert (s["passwordInputs"], s["confirmPassword"]) == (0, False)
    assert classify(page)["kind"] == "form_step"
    assert [f["question"] for f in _inventory(page, consentForms=True, runId="r1")] == ["City"]
    load(page, "<input type='text' name='password' autocomplete='new-password'>", SOURCES)
    assert summary(page)["passwordInputs"] == 1
    load(page, "<label>Pass phrase <input type='text' autocomplete='new-password'></label>", SOURCES)
    assert summary(page)["passwordInputs"] == 1
    assert _inventory(page, consentForms=True, runId="r1") == []


# ---------- the employer's apply link (queued-run plan Task 16) ----------

def apply_link(page):
    return page.evaluate(f"() => {READER}.applyLink()")


def _served(page, host, html):
    """The page served under `host`, so "off the site" has a site to be off (the context is
    offline: the route only answers the page request)."""
    page.route(f"https://{host}/job", lambda route: route.fulfill(
        status=200, content_type="text/html", body=html))
    page.goto(f"https://{host}/job")
    for src in SOURCES:
        page.add_script_tag(content=(EXTENSION / src).read_text(encoding="utf-8"))


@pytest.mark.parametrize("label", ["Apply on company site", "Apply on the company's website",
                                   "Apply on employer site", "Apply now", "Apply"])
def test_an_absolute_link_to_another_site_worded_as_apply_is_the_employers(page, label):
    _served(page, "www.linkedin.com",
            f'<h1>Analyst</h1><a href="https://careers.acme.example/apply/9?src=li">{label}</a>')
    assert apply_link(page) == "https://careers.acme.example/apply/9?src=li"


def test_an_apply_link_that_stays_on_the_board_is_not_one(page):
    """LinkedIn / Indeed's own Apply: same host, so no employer link."""
    _served(page, "www.indeed.com",
            '<a href="https://www.indeed.com/applystart?jk=1">Apply now</a>'
            '<a href="/applystart?jk=1">Apply</a>')
    assert apply_link(page) is None


@pytest.mark.parametrize("href", ["javascript:void(0)", "/apply", "apply", "#apply", "mailto:a@b.test",
                                  "ftp://careers.acme.example/x", "http://", "https:///apply"])
def test_a_script_relative_or_non_http_apply_href_is_not_a_link(page, href):
    _served(page, "www.linkedin.com", f'<a href="{href}">Apply now</a>')
    assert apply_link(page) is None


def test_only_a_visible_link_worded_as_apply_counts(page):
    _served(page, "www.linkedin.com",
            '<a href="https://tracker.example/x">Read more</a>'
            '<a href="https://careers.acme.example/hidden" style="display:none">Apply now</a>'
            '<a href="https://careers.acme.example/real">Apply now</a>')
    assert apply_link(page) == "https://careers.acme.example/real"


def test_a_button_has_no_href_to_read(page):
    _served(page, "www.linkedin.com", "<button>Apply now</button>")
    assert apply_link(page) is None


def _safety_go(url, path="/safety/go/", host="www.linkedin.com"):
    from urllib.parse import quote
    return f"https://{host}{path}" + ("" if url is None else f"?url={quote(url, safe='')}")


EMPLOYER_SITE = "https://careers.acme.example/apply/9?src=li&x=a b".replace(" ", "%20")


@pytest.mark.parametrize("path", ["/safety/go/", "/safety/go"])
def test_linkedins_safety_redirect_is_read_through_to_the_employers_address(page, path):
    _served(page, "www.linkedin.com",
            f'<a href="{_safety_go(EMPLOYER_SITE, path)}">Apply on company website</a>')
    assert apply_link(page) == EMPLOYER_SITE


@pytest.mark.parametrize("carried", [
    "https://www.linkedin.com/jobs/view/1", "javascript:alert(1)", "/apply", "http://", None,
    "https://" + "a" * 2048 + ".example/x",
    # one level only: a redirect carrying a redirect is not unwrapped twice
    "https://www.linkedin.com/safety/go/?url=https%3A%2F%2Fcareers.acme.example%2Fx",
])
def test_a_safety_redirect_carrying_nothing_usable_is_no_link(page, carried):
    _served(page, "www.linkedin.com",
            f'<a href="{_safety_go(carried)}">Apply now</a>')
    assert apply_link(page) is None


@pytest.mark.parametrize("href", [
    "https://www.linkedin.com/jobs/view/1/apply?url=https%3A%2F%2Fcareers.acme.example%2Fx",
    "https://www.linkedin.com/safety/gone/?url=https%3A%2F%2Fcareers.acme.example%2Fx",
])
def test_only_linkedins_own_safety_redirect_is_unwrapped(page, href):
    _served(page, "www.linkedin.com", f'<a href="{href}">Apply now</a>')
    assert apply_link(page) is None


def test_another_hosts_lookalike_redirect_is_just_an_off_site_link_not_unwrapped(page):
    """`notlinkedin.com` is not dot-bounded `linkedin.com`: the link is that other site's, as written."""
    href = "https://notlinkedin.com/safety/go/?url=https%3A%2F%2Fcareers.acme.example%2Fx"
    _served(page, "www.linkedin.com", f'<a href="{href}">Apply now</a>')
    assert apply_link(page) == href


# ---------- Workday's footer button: known navigation, its text decides (Task 14 follow-up) ----------

# Modelled on the apply page test_extension_detection.py records (`_WORKDAY_MY_INFORMATION`): no
# <form> around the step's fields, the footer button data-automation-id="pageFooterNextButton"
# reading "Save and Continue". The newsletter form is added here: a site-wide footer form is the
# only form with a field, so without the marker the nav button counts as outside "the form".
WORKDAY_FOOTER_PAGE = """<div data-automation-id='applyFlowMyInfoPage'>
  <label for='fn'>First Name</label><input id='fn' type='text'></div>
<div class='newsletter'><form><label for='em'>Email</label><input id='em' type='text'>
  <button type='button'>Subscribe</button></form></div>
<button type='button' data-automation-id='pageFooterNextButton'
  onclick='window.hit = 1'>{text}</button>"""
WORKDAY_URL = "https://acme.wd5.myworkdayjobs.com/en-US/careers/job/Analyst_R1/apply/applyManually"


def test_workdays_footer_button_is_the_step_and_its_text_decides_next(page):
    serve(page, WORKDAY_URL, WORKDAY_FOOTER_PAGE.format(text="Save and Continue"))
    nav = button(summary(page), "Save and Continue")
    assert nav["inForm"] is True and "known" not in nav    # the text, not the table, says Next
    assert classify(page)["kind"] == "form_step"
    go = button(summary(page), "Save and Continue")
    assert advance(page, go["id"]) == {"clicked": True}
    assert page.evaluate("() => window.hit === 1")


def test_workdays_footer_button_relabelled_submit_is_a_submit_and_never_pressed(page):
    serve(page, WORKDAY_URL, WORKDAY_FOOTER_PAGE.format(text="Save and Continue"))
    stale = button(summary(page), "Save and Continue")["id"]
    page.evaluate("() => { document.querySelector('[data-automation-id=pageFooterNextButton]').textContent = 'Submit'; }")
    assert advance(page, stale) == {"clicked": False, "why": "submit"}
    nav = button(summary(page), "Submit")
    assert nav["inForm"] is True
    assert classify(page)["kind"] == "review"
    assert advance(page, button(summary(page), "Submit")["id"]) == {"clicked": False, "why": "submit"}
    assert page.evaluate("() => window.hit === 1") is False


def test_the_workday_marker_means_nothing_on_another_host(page):
    """On any host but Workday's the button is outside the only form like any other button: the
    marker earns it no `inForm` and no `known`. It is still the one Next anywhere in the application
    outside site chrome, so the page reads as a step through the classifier's fallback."""
    serve(page, "https://careers.acme-example.test/apply", WORKDAY_FOOTER_PAGE.format(text="Save and Continue"))
    nav = button(summary(page), "Save and Continue")
    assert nav["inForm"] is False and "known" not in nav
    assert classify(page)["kind"] == "form_step"
    serve(page, "https://careers.acme-example.test/apply2", WORKDAY_FOOTER_PAGE.format(text="Submit"))
    assert classify(page) == {"kind": "review", "by": "submit_button"}


# ---------- a board's own hosts, and the ceiling on what is stored ----------

def _target(page, href):
    return page.evaluate(f"(h) => {READER}.applyTarget(h)", href)


@pytest.mark.parametrize("host, same_board", [
    ("www.linkedin.com", "https://uk.linkedin.com/jobs/view/1"),
    ("www.linkedin.com", "https://linkedin.com/jobs/view/1"),
    ("www.indeed.com", "https://smartapply.indeed.com/beta/indeedapply/form/1"),
])
def test_another_host_of_the_same_board_is_still_the_board(page, host, same_board):
    _served(page, host, "<h1>Analyst</h1>")
    assert _target(page, same_board) is None


def test_a_different_board_or_a_non_board_page_keeps_the_link(page):
    _served(page, "www.linkedin.com", "<h1>Analyst</h1>")
    assert _target(page, "https://www.indeed.com/viewjob?jk=1") == "https://www.indeed.com/viewjob?jk=1"
    other = "https://uk.linkedin.com/jobs/view/1"
    _served(page, "careers.acme.example", "<h1>Analyst</h1>")
    assert _target(page, other) == other


def test_a_sibling_board_host_in_the_structured_data_does_not_hide_the_real_apply_link(page):
    """`applyTarget` returning a string would stop the `??` from ever reaching the anchor."""
    _served(page, "www.linkedin.com",
            '<a href="https://careers.acme.example/apply/9">Apply on company website</a>')
    posting = {"url": "https://uk.linkedin.com/jobs/view/4001/"}
    assert page.evaluate(f"(p) => {READER}.applyUrl(p)", posting) == "https://careers.acme.example/apply/9"


def test_the_ceiling_is_on_the_unwrapped_address_not_on_linkedins_wrapper(page):
    """A long tracking tail on the wrapper must not cost a short employer address."""
    _served(page, "www.linkedin.com", "<h1>Analyst</h1>")
    wrapped = _safety_go("https://careers.acme.example/apply/9") + "&trk=" + "t" * 2100
    assert len(wrapped) > 2048
    assert _target(page, wrapped) == "https://careers.acme.example/apply/9"
    # …and the other direction: a long address inside a short wrapper is still too long.
    assert _target(page, _safety_go("https://careers.acme.example/" + "a" * 2048)) is None


# ---------- the page's own complaints (page_errors) ----------
#
# A Next the page rejects draws an error banner, marks the box invalid and says so in words. The
# driver needs those words (never a value), a handle for the field each one names, and the banner's
# own buttons kept out of what it compares pages by.

ERRORS_PAGE = fixture_html("workday_errors.html")


def page_errors(page):
    return page.evaluate(f"() => {READER}.pageErrors()")


def press_next(page):
    page.click("[data-automation-id=pageFooterNextButton]")


def element_id(page, attr, target):
    return page.evaluate("([a, t]) => document.querySelector(`[${a}='${t}']`)?.id ?? null", [attr, target])


def test_a_page_with_no_complaint_has_no_errors(page, load):
    load(page, ERRORS_PAGE, SOURCES)
    assert page_errors(page) == {"count": 0, "items": []}
    assert summary(page)["errors"] == 0


def test_a_rejected_next_is_read_as_one_error_naming_the_upload_box(page, load):
    load(page, ERRORS_PAGE, SOURCES)
    press_next(page)
    errors = page_errors(page)
    assert errors["count"] == 1
    (item,) = errors["items"]
    # The page's own words for the field, with the banner's "Error - " lead cut, and never a value.
    assert (item["label"], item["kind"]) == ("Upload a file (5MB max)", "upload")
    assert element_id(page, "data-maestro-up", item["target"]) == "upload-input"
    assert summary(page)["errors"] == 1


def test_the_banner_and_the_boxs_own_complaint_are_one_error_not_two(page, load):
    load(page, ERRORS_PAGE, SOURCES)
    press_next(page)
    assert page.evaluate("document.getElementById('upload-error').hidden") is False
    assert page_errors(page)["count"] == 1


def test_the_banners_buttons_are_marked_so_the_fingerprint_can_leave_them_out(page, load):
    load(page, ERRORS_PAGE, SOURCES)
    before = summary(page)
    shown = lambda s, **kw: sorted(b["text"] for b in s["buttons"] if b["visible"] and bool(b.get("inErrors")) == kw["errors"])
    assert shown(before, errors=True) == []
    press_next(page)
    after = summary(page)
    assert shown(after, errors=True) == ["Error - Upload a file (5MB max)", "Errors Found"]
    # What is left is the step's own buttons, exactly as before the banner.
    assert shown(after, errors=False) == shown(before, errors=False)


def test_a_field_error_is_mapped_by_its_describedby_to_the_field(page, load):
    load(page, """<h2>Contact</h2><label for="phone">Phone Number</label>
      <input id="phone" aria-invalid="true" aria-describedby="e-phone">
      <div id="e-phone" data-automation-id="errorMessage">The field Phone Number is required and must have a value.</div>
      <label for="city">City</label><input id="city">""", SOURCES)
    (item,) = page_errors(page)["items"]
    assert (item["label"], item["kind"]) == ("Phone Number", "field")
    fid = page.evaluate(f"() => window.careerStudioCompanion.fillInventory.fidFor(document.getElementById('phone'))")
    assert item["target"] == fid


def test_a_summary_item_with_no_link_is_mapped_by_its_exact_label(page, load):
    load(page, """<div role="alert"><h3>Errors Found</h3><ul><li>Error - City</li></ul></div>
      <label for="phone">Phone Number</label><input id="phone">
      <label for="city">City*</label><input id="city" aria-required="true">""", SOURCES)
    (item,) = page_errors(page)["items"]
    assert (item["label"], item["kind"]) == ("City", "field")
    fid = page.evaluate(f"() => window.careerStudioCompanion.fillInventory.fidFor(document.getElementById('city'))")
    assert item["target"] == fid


def test_a_summary_link_to_a_field_names_that_field_whatever_its_label(page, load):
    load(page, """<div role="alert"><h3>Please fix the following</h3>
      <ul><li><a href="#c2">Error - the second box</a></li></ul></div>
      <label for="c1">Name</label><input id="c1"><label for="c2">Anything</label><input id="c2">""", SOURCES)
    (item,) = page_errors(page)["items"]
    assert item["kind"] == "field"
    fid = page.evaluate(f"() => window.careerStudioCompanion.fillInventory.fidFor(document.getElementById('c2'))")
    assert item["target"] == fid


def test_an_error_that_matches_no_field_keeps_its_label(page, load):
    load(page, """<div role="alert"><h3>Errors Found</h3><ul><li>Error - Security Question</li></ul></div>
      <label for="c1">Name</label><input id="c1">""", SOURCES)
    (item,) = page_errors(page)["items"]
    assert item == {"label": "Security Question", "target": None, "kind": "unknown"}


def test_a_polite_status_message_is_not_an_error(page, load):
    load(page, """<div role="alert">Successfully Uploaded!</div><div aria-live="polite">Saving…</div>
      <label for="c1">Name</label><input id="c1">""", SOURCES)
    assert page_errors(page) == {"count": 0, "items": []}


def test_the_errors_are_words_never_values(page, load):
    load(page, """<div role="alert"><h3>Errors Found</h3><ul><li>Error - Phone Number</li></ul></div>
      <label for="phone">Phone Number</label><input id="phone" value="Zelda-Secret-9" aria-invalid="true">""", SOURCES)
    out = page_errors(page)
    assert "Zelda-Secret-9" not in json.dumps(out) and out["count"] == 1
    assert "Zelda-Secret-9" not in json.dumps(summary(page))


# ---------- a real Submit is never swallowed by a region that only looks like an error summary ----------

CONTINUE_ELSEWHERE = "<main><h1>Review</h1><div><button type='button'>Continue</button></div>{block}</main>"


@pytest.mark.parametrize("block", [
    # A static hint beside the Submit, matching the 'please correct' heading words.
    "<div><p>Please correct any errors before submitting.</p><button type='button'>Submit application</button></div>",
    # The same under a live wrapper.
    "<div aria-live='polite'><p>Please correct any errors before submitting.</p><button type='button'>Submit application</button></div>",
    "<div role='alert'><p>You must fix any error first.</p><button type='button'>Submit application</button></div>",
], ids=["plain", "aria-live", "alert"])
def test_a_submit_beside_error_words_is_still_the_review_pages_and_never_a_continue_beside_it(page, load, block):
    load(page, CONTINUE_ELSEWHERE.format(block=block), SOURCES)
    s = summary(page)
    assert not [b for b in s["buttons"] if b["text"] == "Submit application" and b.get("inErrors")]
    assert classify(page)["kind"] == "review"


BANNER_PAGE = """<div role="alert"><h3>Errors Found</h3><ul><li>{line}</li></ul></div><h2>My Experience</h2>
  <label for="c">City</label><input id="c"><button type="button">Save and Continue</button>"""


def test_a_banner_line_that_only_talks_of_submitting_is_neither_next_nor_submit(page, load):
    load(page, BANNER_PAGE.format(line="<button type='button'>Error - Please submit a resume</button>"), SOURCES)
    assert summary(page)["submitSeen"] is False
    assert classify(page)["kind"] == "form_step"


@pytest.mark.parametrize("button", [
    # Not an Error lead: a real Submit that happens to sit in a live region.
    "<button type='button'>Submit application</button>",
    "<button type='button'>Error review: Submit application</button>",
    # An Error lead, but the button is marked as a submit by the page itself.
    "<button type='button' data-automation-id='bottom-navigation-submit'>Error - Please submit</button>",
    "<button type='button' id='submit-btn'>Error - Please submit</button>",
])
def test_a_real_submit_in_the_banner_is_still_counted(page, load, button):
    load(page, BANNER_PAGE.format(line=button), SOURCES)
    assert classify(page)["kind"] == "review"


def test_a_live_region_marked_off_is_no_error_summary(page, load):
    load(page, """<div aria-live="off"><ul><li>Error - City</li></ul></div>
      <label for="city">City</label><input id="city">""", SOURCES)
    assert page_errors(page) == {"count": 0, "items": []}


def test_an_error_line_button_is_marked_but_a_next_beside_the_banner_is_not(page, load):
    load(page, """<div role="alert"><h3>Errors Found</h3><ul><li><button type="button">Error - City</button></li></ul></div>
      <label for="city">City</label><input id="city"><button type="button">Next</button>""", SOURCES)
    marked = {b["text"]: bool(b.get("inErrors")) for b in summary(page)["buttons"]}
    assert marked == {"Error - City": True, "Next": False}
    assert classify(page)["kind"] == "form_step"


# ---------- an upload's complaint is its own box's, never a neighbour's ----------

def test_an_invalid_fieldset_around_a_field_and_an_optional_upload_does_not_report_the_upload(page, load):
    load(page, """<h2>Documents</h2><form><fieldset aria-invalid="true"><label for="c">City</label>
      <input id="c" aria-invalid="true"><div><label for="f">Upload a file</label><input type="file" id="f"></div></fieldset>
      <button type="button">Next</button></form>""", SOURCES)
    items = page_errors(page)["items"]
    assert [(i["label"], i["kind"]) for i in items] == [("City", "field")]


# ---------- the words are the page's, never the user's ----------

def test_a_mapped_item_is_worded_by_the_fields_question_not_by_the_error_line(page, load):
    load(page, """<div role="alert"><h3>Errors Found</h3><ul><li><a href="#ph">Error - Phone Number, which must be 10 digits</a></li></ul></div>
      <label for="ph">Phone</label><input id="ph" aria-invalid="true">""", SOURCES)
    (item,) = page_errors(page)["items"]
    assert (item["label"], item["kind"]) == ("Phone", "field")


@pytest.mark.parametrize("line", [
    "Error: Ada_Lovelace_Resume.pdf must be under 5MB",
    "Error: ada@example is invalid",
    "Error: \"Ada Lovelace\" is not a number",
])
def test_an_unmapped_line_that_carries_a_file_name_an_address_or_a_quoted_string_is_not_repeated(page, load, line):
    load(page, f"""<div role="alert"><h3>Errors Found</h3><ul><li>{line}</li></ul></div>
      <label for="e">Email</label><input id="e" value="ada@example">""", SOURCES)
    out = page_errors(page)
    assert out["items"] == [{"label": "Something the page names", "target": None, "kind": "unknown"}]
    blob = json.dumps([out, summary(page)])
    assert "Ada" not in blob and "ada@example" not in blob and "Lovelace" not in blob


def test_an_unmapped_line_that_echoes_a_pill_or_a_typed_value_is_not_repeated(page, load):
    load(page, """<div role="alert"><h3>Errors Found</h3><ul><li>Error: Python is required</li><li>Error: Springfield Heights is required</li></ul></div>
      <ul><li data-automation-id="selectedItem"><p data-automation-id="promptOption">Python</p></li></ul>
      <label for="c">Town</label><input id="c" value="Springfield Heights">""", SOURCES)
    out = page_errors(page)
    assert [i["label"] for i in out["items"]] == ["Something the page names"]
    assert "Python" not in json.dumps(out) and "Springfield" not in json.dumps(out)


def test_a_live_region_that_is_not_an_error_line_is_never_used_as_a_label(page, load):
    load(page, """<div aria-live="polite">Python selected. Required field. 3 of 15 chosen: Python, SQL, Go</div>
      <label for="s">Skills</label><input id="s" role="combobox">""", SOURCES)
    out = page_errors(page)
    assert out == {"count": 0, "items": []}
    assert "Python" not in json.dumps(summary(page))


def test_a_standing_hint_about_required_fields_is_not_an_error(page, load):
    load(page, """<main><h1>Engineer at Acme</h1><p aria-live="polite">Fields marked * are required</p>
      <label for="a">City *</label><input id="a"><button type="button">Next</button></main>""", SOURCES)
    assert page_errors(page) == {"count": 0, "items": []}
    assert summary(page)["errors"] == 0


@pytest.mark.parametrize("line", ["Phone Number is required", "Phone Number can't be blank", "Phone Number: This field is required",
                                  "The field Phone Number is required and must have a value."])
def test_the_usual_ways_a_page_words_a_missing_field_all_name_it(page, load, line):
    load(page, f"""<div role="alert"><ul><li>{line}</li></ul></div>
      <label for="ph">Phone Number</label><input id="ph">""", SOURCES)
    (item,) = page_errors(page)["items"]
    assert (item["label"], item["kind"]) == ("Phone Number", "field")


def test_an_unmapped_line_that_only_repeats_a_mapped_label_is_dropped(page, load):
    load(page, """<div role="alert"><h3>Errors Found</h3><ul><li><a href="#c">Error - City</a></li><li>Error - City field</li></ul></div>
      <label for="c">City</label><input id="c" aria-invalid="true">""", SOURCES)
    assert [i["label"] for i in page_errors(page)["items"]] == ["City"]


# ---------- the step heading is the step's ----------

def test_an_error_summarys_heading_is_not_the_steps_heading(page, load):
    clean = "<main><h2>Contact details</h2><label for='a'>Full name</label><input id='a'><button type='button'>Next</button></main>"
    load(page, clean, SOURCES)
    before = summary(page)["stepKey"]
    for banner in ("<div role='alert'><h2>Please correct the errors below</h2><ul><li>Error - Full name</li></ul></div>",
                   "<div role='alert'><h2>Problems with your answers</h2><ul><li>Error - Full name</li></ul></div>"):
        load(page, "<main>" + banner + clean[len("<main>"):], SOURCES)
        assert summary(page)["stepKey"] == before and before != ""


# ---------- the cheap read stays cheap ----------

def test_a_page_with_no_complaint_reads_no_field_questions(page, load):
    controls = "".join(f"<label for='i{n}'>Question {n}</label><input id='i{n}'>" for n in range(40))
    load(page, f"<h2>Questions</h2>{controls}<button type='button'>Next</button>", SOURCES)
    page.evaluate("""() => { const ns = window.careerStudioCompanion; window.__reads = 0; const real = ns.readField;
      ns.readField = (el) => { window.__reads += 1; return real(el); }; }""")
    summary(page)
    assert page.evaluate("window.__reads") == 0


def test_two_steps_inside_a_live_main_have_different_step_keys(page, load):
    step = "<main aria-live='polite'><h1>{h}</h1><label for='a'>Q</label><input id='a'><button type='button'>Next</button></main>"
    load(page, step.format(h="Your details"), SOURCES)
    first = summary(page)["stepKey"]
    load(page, step.format(h="Your experience"), SOURCES)
    second = summary(page)["stepKey"]
    assert first != "" and second != "" and first != second
