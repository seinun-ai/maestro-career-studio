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

import pytest

from tests.browser.conftest import ENGINE_SOURCES, EXTENSION, fixture_html
from tests.browser.pages import oracle
from tests.test_extension_page_kind import SUBMIT

READER = "window.careerStudioCompanion.pageReader"
KIND = "window.careerStudioCompanion.pageKind"
SOURCES = ENGINE_SOURCES + ["content/detect.js", "shared/ats-buttons.js", "shared/page-kind.js",
                           "content/page-reader.js"]


def summary(page):
    return page.evaluate(f"() => {READER}.summary()")


def classify(page):
    return page.evaluate(f"() => {KIND}.classify({READER}.summary())")


def advance(page, button_id):
    return page.evaluate(f"(id) => {READER}.advance(id)", button_id)


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
    assert set(s) == {"host", "buttons", "passwordInputs", "confirmPassword", "otpInput", "captchaVisible",
                      "fillable", "hasApplyLink", "confirmationText", "closedText", "boardNative"}
    assert set(s["buttons"][0]) == {"id", "text", "type", "marker", "inForm", "visible", "enabled"}
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
    load(page, "<p>This position has been filled.</p>", SOURCES)
    assert summary(page)["closedText"] is True
    load(page, "<p>Tell us about yourself.</p>", SOURCES)
    s = summary(page)
    assert (s["confirmationText"], s["closedText"]) == (False, False)


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
    load(page, "<label>Enter the 6-digit code <input name='otp'></label>", SOURCES)
    assert summary(page)["otpInput"] is True


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


# ---------- the ATS table's verdicts (Task 14) ----------

ATS = "window.careerStudioCompanion.atsButtons"


def serve(page, url, body):
    """Serve `body` at `url` (the route answers the page request; the context is offline) and load
    the extension on it, so `location.hostname` is the vendor's."""
    page.route(url, lambda route: route.fulfill(status=200, content_type="text/html", body=body))
    page.goto(url)
    for src in SOURCES:
        page.add_script_tag(content=(EXTENSION / src).read_text(encoding="utf-8"))


GREENHOUSE_STEP = """<form><label for='a'>Name</label><input id='a'>
  <button type='button'>Back</button>
  <input type='submit' id='submit_app' value='Done' onclick='window.hit = 1; return false;'></form>"""


def test_greenhouses_submit_control_is_a_submit_even_when_it_reads_done(page):
    """The case the text cannot catch: the sort alone calls "Done" unclear and would offer no
    Submit at all; the vendor's own id says it is one. The page stops, and nothing is clicked."""
    serve(page, "https://boards.greenhouse.io/acme/jobs/1", GREENHOUSE_STEP)
    assert classify(page)["kind"] == "review"   # classify re-tags the buttons, so read ids after it
    s = summary(page)
    done = button(s, "Done")
    assert done["known"] == "submit"
    assert "known" not in button(s, "Back")
    assert advance(page, done["id"]) == {"clicked": False, "why": "submit"}
    assert page.evaluate("() => window.hit === 1") is False


def test_the_same_control_on_an_unlisted_host_has_no_verdict(page):
    """A marker is the vendor's only on the vendor's host: on any other host "Done" is the text's
    to judge (unclear), and the summary carries no `known` key at all."""
    serve(page, "https://careers.acme-example.test/jobs/1", GREENHOUSE_STEP)
    s = summary(page)
    assert all("known" not in b for b in s["buttons"])
    assert advance(page, button(s, "Done")["id"]) == {"clicked": False, "why": "not_next"}


def test_levers_submit_control_is_known_by_its_data_qa(page):
    serve(page, "https://jobs.lever.co/acme/1", """<form><label for='a'>Name</label><input id='a'>
      <button type='button' data-qa='btn-submit' onclick='window.hit = 1'>Go</button></form>""")
    assert classify(page)["kind"] == "review"
    s = summary(page)
    assert s["buttons"][0]["known"] == "submit"
    assert advance(page, s["buttons"][0]["id"]) == {"clicked": False, "why": "submit"}
    assert page.evaluate("() => window.hit === 1") is False


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
