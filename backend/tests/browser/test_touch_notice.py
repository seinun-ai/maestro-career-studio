"""The panel hears THAT you changed a field, never what you typed (`content/touch-notice.js`).

Real Chromium, real keystrokes: the trusted input events are what `inventory.js` counts as
yours, and the engine's own clicks (a radio the rule pass ticks) are exempt through
`fillBusyEl`. The message is `{type: "fields_touched", fids}`, at most one per two seconds,
and only from a frame that has earned the user's data (`ns.frameMayReceiveUserData`)."""

import pytest

from tests.browser.conftest import ENGINE_SOURCES

NS = "window.careerStudioCompanion"
INV = f"{NS}.fillInventory"
SOURCES = ["shared/choose.js", "shared/policy.js", "shared/profile-fields.js", *ENGINE_SOURCES,
           "content/eeo.js", "content/autofill.js", "content/touch-notice.js"]
FORM = ("<label for='fn'>First name</label><input id='fn'>"
        "<label for='ln'>Last name</label><input id='ln'>"
        "<fieldset><legend>Are you authorized to work in the US?</legend>"
        "<label><input type='radio' name='wa'>Yes</label><label><input type='radio' name='wa'>No</label></fieldset>")


@pytest.fixture
def started(page, load):
    def _started(gate=True):
        page.clock.install()
        load(page, FORM, SOURCES)
        page.evaluate("""(gate) => {
          window.__sent = [];
          window.chrome = { runtime: { sendMessage: (m) => { window.__sent.push(m); return Promise.resolve(); } } };
          window.careerStudioCompanion.frameMayReceiveUserData = () => gate;
        }""", gate)
        page.evaluate(f"() => {INV}.list({{}})")   # a pass has named the fields (Fill has run)
        return page
    return _started


def sent(page):
    return page.evaluate("() => window.__sent")


def type_into(page, selector, text):
    page.click(selector)
    page.keyboard.type(text)


def test_typing_sends_one_value_free_message_after_the_throttle(started):
    page = started()
    type_into(page, "#fn", "Ada")
    assert sent(page) == []                        # nothing leaves before the window closes
    page.clock.run_for(2100)
    [message] = sent(page)
    fid = page.evaluate(f"() => {INV}.list({{}}).fields[0].fid")
    assert message == {"type": "fields_touched", "fids": [fid]}
    assert "Ada" not in str(message)


def test_many_changes_in_a_window_are_one_message_and_the_next_window_another(started):
    page = started()
    type_into(page, "#fn", "Ada")
    type_into(page, "#ln", "Lovelace")
    page.clock.run_for(2100)
    assert len(sent(page)) == 1 and len(sent(page)[0]["fids"]) == 2
    type_into(page, "#fn", "x")
    page.clock.run_for(2100)
    assert len(sent(page)) == 2


def test_the_engines_own_writes_send_nothing(started):
    """The rule pass types and ticks; a radio click fires a TRUSTED change that only
    `fillBusyEl` tells apart from yours."""
    page = started()
    page.evaluate("""async () => window.careerStudioCompanion.fillFormFromProfile(
      { personal: { first_name: 'Ada', last_name: 'L' }, work_auth: { authorized_now: true } }, [], false, [], false)""")
    page.clock.run_for(5000)
    assert sent(page) == []


def test_a_frame_that_has_not_earned_the_data_says_nothing(started):
    page = started(gate=False)
    type_into(page, "#fn", "Ada")
    page.clock.run_for(5000)
    assert sent(page) == []


def test_a_page_with_no_listener_does_not_break_the_page(started):
    """`sendMessage` rejecting (no panel open) is swallowed."""
    page = started()
    page.evaluate("() => { window.chrome.runtime.sendMessage = () => Promise.reject(new Error('no receiver')); }")
    type_into(page, "#fn", "Ada")
    page.clock.run_for(2100)
    assert page.evaluate("() => document.getElementById('fn').value") == "Ada"
