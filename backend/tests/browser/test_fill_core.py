"""The generic fill mechanics (fill-core.js) through the page operations
(fill-ops.js), in real Chromium against the committed fixtures."""

import pytest

from tests.browser.conftest import fixture_html
from tests.browser.pages import CATEGORY_POPUP, POLICY_PAGE, in_both_windows, list_shown, oracle

OPS = "window.careerStudioCompanion.fillOps"


def inv(page, **opts):
    return {f["question"]: f for f in page.evaluate(f"async (o) => (await {OPS}.inventory(o)).fields", opts)}


def apply(page, f, **action):
    return page.evaluate(f"(a) => {OPS}.apply([a])", {"fid": f["fid"], "fp": f["fp"], **action})[0]


def explore(page, f, term=None):
    return page.evaluate(f"(r) => {OPS}.explore([r])", {"fid": f["fid"], "fp": f["fp"], "term": term})[f["fid"]]


# --- text-like
@in_both_windows()
def test_text_commits_where_the_page_only_takes_real_typing(window, request, load):
    page = request.getfixturevalue(window)
    load(page, fixture_html("workday_text.html"))
    row = apply(page, inv(page)["City"], op="write", value="Springfield")
    assert row["outcome"] == "verified" and oracle(page, "city") == "Springfield"
    assert page.get_attribute("#city", "aria-invalid") == "false"


@in_both_windows()
def test_text_commits_only_after_leaving_the_field(window, request, load):
    """Postal Code shows a value the app never took, with its error: a write
    commits the new value only by leaving the box, and the error goes."""
    page = request.getfixturevalue(window)
    load(page, fixture_html("workday_text.html"))
    row = apply(page, inv(page)["Postal Code"], op="write", value="12345")
    assert row["outcome"] == "verified" and oracle(page, "zip") == "12345"
    assert page.is_hidden("#zip-err") and page.get_attribute("#zip", "aria-invalid") == "false"
    assert page.evaluate("document.activeElement === document.body")


def test_sweep_recommits_text_that_shows_an_error_with_its_own_value(page, load):
    load(page, fixture_html("workday_text.html"))
    assert [r["outcome"] for r in page.evaluate(f"() => {OPS}.sweep()")] == ["verified"]
    assert oracle(page, "zip") == "00000"


def test_a_text_the_page_clears_on_blur_is_reverted(page, load):
    load(page, "<label for='a'>Q</label><input id='a'><script>"
               "document.getElementById('a').addEventListener('focusout', e => { e.target.value = ''; });</script>")
    assert apply(page, inv(page)["Q"], op="write", value="x")["outcome"] == "reverted"


@in_both_windows()
def test_workday_date_sections_are_written_before_one_blur(window, request, load):
    page = request.getfixturevalue(window)
    load(page, fixture_html("workday_date.html"))
    fields = inv(page)
    assert apply(page, fields["From"], op="write", value="2019-08")["outcome"] == "verified"
    # Live Workday shows "08" but holds "8" (notes §6); the app's value is the proof.
    assert (page.input_value("#m"), page.input_value("#y")) == ("8", "2019")
    assert oracle(page, "from") == "2019-08"
    assert page.locator("text=Error:").count() == 0


@in_both_windows()
def test_date_leave_blurs_the_part_the_widget_moved_focus_to(window, request, load):
    """After the Year the widget moves focus to Month by itself; leaving the
    date blurs Month (not the Year typed in), so the wrapper validates."""
    page = request.getfixturevalue(window)
    load(page, fixture_html("workday_date.html"))
    assert apply(page, inv(page)["From"], op="write", value="2026-06")["outcome"] == "verified"
    assert oracle(page, "from") == "2026-06"
    assert page.locator("text=Error:").count() == 0
    assert page.evaluate("document.getElementById('from').contains(document.activeElement)") is False


def test_a_plain_date_box_is_written_in_its_placeholder_format(page, load):
    load(page, fixture_html("workday_date.html"))
    assert apply(page, inv(page)["End date"], op="write", value="2021-05")["outcome"] == "verified"
    assert page.input_value("#p") == "05/2021"


def test_a_date_widget_asking_for_a_day_the_fact_lacks_is_left_alone(page, load):
    load(page, "<label for='d'>Start date</label><input id='d' type='date'>")
    row = apply(page, inv(page)["Start date"], op="write", value="2021-05")
    assert (row["outcome"], row["reason"]) == ("unexpected", "needs_more_date_precision")
    assert page.input_value("#d") == ""


# --- choice-like, passive
def test_native_select_radio_hidden_radio_and_lone_checkbox(page, load):
    load(page, fixture_html("native.html"))
    f = inv(page)
    assert apply(page, f["Highest degree"], op="choose", text="Master's")["outcome"] == "verified"
    assert apply(page, f["Willing to relocate?"], op="choose", text="No")["outcome"] == "verified"
    assert page.is_checked("#r2")
    assert apply(page, f["I have a preferred name"], op="choose", text="Yes")["outcome"] == "verified"


def test_sets_keep_existing_choices_and_never_untick(page, load):
    load(page, fixture_html("native.html"))
    f = inv(page)
    assert apply(page, f["Which days can you work?"], op="set", texts=["Monday", "Wednesday"])["outcome"] == "verified"
    assert page.evaluate("[...document.querySelectorAll('input[name=days]:checked')].map(i => i.value)") == ["mon", "wed"]
    assert apply(page, f["Languages"], op="set", texts=["Hindi"])["outcome"] == "verified"


# --- choice-like, popups
@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="Task 6: the live popup lists its 'Select One' placeholder as an option; "
                          "it must not be offered as an answer")
def test_a_workday_dropdown_is_explored_and_closed_then_committed(page, load):
    load(page, fixture_html("workday_listbox.html"))
    f = inv(page)["Are you legally authorized to work in the United States?"]
    got = explore(page, f)
    assert [o["text"] for o in got["options"]] == ["Yes", "No"] and got["complete"]
    assert not list_shown(page)
    row = apply(page, f, op="choose", text="No")
    assert (row["outcome"], row["committed"]) == ("verified", "No") and oracle(page, "auth") == "No"


def test_a_workday_dropdown_pick_is_explored_closed_and_committed_to_the_app(page, load):
    load(page, fixture_html("workday_listbox.html"))
    f = inv(page)["Degree"]
    assert "Masters" in [o["text"] for o in explore(page, f)["options"]]
    assert not list_shown(page)
    row = apply(page, f, op="choose", text="Masters")   # below the fold of a 12-option list
    assert (row["outcome"], row["committed"]) == ("verified", "Masters") and oracle(page, "degree") == "Masters"


def test_a_category_is_unexpected_with_its_children_and_the_popup_stays_open(page, load):
    load(page, CATEGORY_POPUP)
    row = apply(page, inv(page)["How did you hear about us?"], op="choose", text="Job Board")
    assert (row["outcome"], row["reason"]) == ("unexpected", "new_options")
    assert [o["text"] for o in row["options"]] == ["LinkedIn", "Indeed"]


def test_react_select_commits_and_a_rejected_click_is_not_filled(page, load):
    load(page, fixture_html("react_select.html"))
    f = inv(page)["Country"]
    assert [o["text"] for o in explore(page, f, "united")["options"]] == ["United States", "United Kingdom"]
    assert apply(page, f, op="choose", text="India", term="ind")["outcome"] == "verified"
    page.evaluate("window.rejectClicks = true")
    row = apply(page, f, op="choose", text="Canada", term="can")
    assert (row["outcome"], row["reason"], row["committed"]) == ("unexpected", "not_committed", "India")


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="Task 5: search is press, type, Enter (key-up), wait for the staged "
                          "results to settle, click the row's radio")
def test_workday_search_waits_past_searching_and_commits_the_pill(page, load):
    load(page, fixture_html("workday_search.html"))
    f = inv(page)["School or University"]
    got = explore(page, f, "Arlington")
    texts = [o["text"] for o in got["options"]]
    assert len(texts) == 8 and "The University of Texas at Arlington" in texts
    assert page.input_value("#school") == "" and oracle(page, "school") == ""
    row = apply(page, f, op="choose", text="The University of Texas at Arlington", term="Arlington")
    assert (row["outcome"], row["committed"]) == ("verified", "The University of Texas at Arlington")
    assert oracle(page, "school") == "The University of Texas at Arlington"


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="Task 5: a multi search ticks the checkbox in a virtualized result list "
                          "(Python is #16), read back from the pills (Task 3)")
def test_a_search_set_keeps_existing_chips_and_reports_partial_honestly(page, load):
    load(page, fixture_html("workday_search.html"))
    f = inv(page)["Type to Add Skills"]
    row = apply(page, f, op="set", texts=["Python", "Rust"])
    assert row["outcome"] == "partial" and row["added"] == ["Python"] and row["missing"] == ["Rust"]
    assert row["committed"] == ["SQL", "Python"] and oracle(page, "skills") == ["SQL", "Python"]


def test_an_empty_popup_that_needs_a_search_is_unexpected_not_failed(page, load):
    load(page, fixture_html("popup_with_search.html"))
    got = explore(page, inv(page)["Field of study"])
    assert got["options"] == [] and got["searchable"] is True and got["error"] == "empty_popup"


# --- safety
def test_a_changed_field_fingerprint_is_stale(page, load):
    load(page, fixture_html("native.html"))
    f = inv(page)["Highest degree"]
    assert page.evaluate(f"(a) => {OPS}.apply([a])", {"fid": f["fid"], "fp": "other", "op": "choose", "text": "Master's"})[0]["outcome"] == "stale"


def test_a_fid_from_another_frame_is_ignored(page, load):
    load(page, fixture_html("native.html"))
    assert page.evaluate(f"() => {OPS}.apply([{{fid: 'zzzzzz-1', op: 'write', value: 'x'}}])") == []


def test_cancel_stops_a_choose_before_it_clicks(page, load):
    load(page, fixture_html("workday_search.html"))
    f = inv(page)["School or University"]
    row = page.evaluate(f"""(a) => {{ const run = {OPS}.apply([a]); setTimeout(() => {OPS}.cancel(), 100); return run; }}""",
                        {"fid": f["fid"], "fp": f["fp"], "op": "choose", "text": "Texas A&M University", "term": "Texas"})[0]
    assert row["outcome"] == "cancelled"
    page.wait_for_timeout(600)
    assert oracle(page, "school") == ""
    # The engine's own query is taken back and no late search result is left open.
    assert page.input_value("#school") == ""
    assert not list_shown(page)
    assert page.evaluate("document.activeElement.id") != "school"  # focus is not left in the engine's box


def test_a_field_the_user_edits_while_the_model_decides_is_never_written(page, load):
    load(page, fixture_html("workday_text.html"))
    f = inv(page)["City"]
    page.type("#city", "Mine")
    row = apply(page, f, op="write", value="Springfield")
    assert row["outcome"] == "yours" and page.input_value("#city") == "Mine"


def test_an_action_without_a_fingerprint_is_refused(page, load):
    load(page, fixture_html("native.html"))
    f = inv(page)["Highest degree"]
    got = page.evaluate(f"(a) => {OPS}.apply([a])", {"fid": f["fid"], "op": "choose", "text": "Master's"})[0]
    assert got["outcome"] == "stale"


def test_stop_is_latched_between_fields_until_the_next_run(page, load):
    load(page, fixture_html("native.html"))
    f = inv(page)
    page.evaluate(f"() => {OPS}.cancel()")
    assert apply(page, f["Highest degree"], op="choose", text="Master's")["outcome"] == "cancelled"
    assert apply(page, f["I have a preferred name"], op="choose", text="Yes")["outcome"] == "cancelled"
    # Cancelled means NOTHING changed — not "reported cancelled after writing".
    assert page.evaluate("document.getElementById('deg').value") == ""
    assert page.is_checked("#pref") is False
    page.evaluate(f"() => {OPS}.inventory({{runId: 'next'}})")
    assert apply(page, f["Highest degree"], op="choose", text="Master's")["outcome"] == "verified"


def test_cancel_cleanup_never_wipes_a_text_value(page, load):
    load(page, fixture_html("workday_text.html"))
    f = inv(page)["City"]
    apply(page, f, op="write", value="Springfield")
    page.evaluate(f"() => {OPS}.cancel()")
    apply(page, f, op="write", value="Other")
    assert page.input_value("#city") == "Springfield"


def test_the_sweep_catches_a_value_the_page_reverts_later(page, load):
    load(page, "<label for='a'>Q</label><input id='a'><script>document.getElementById('a').addEventListener("
               "'focusout', e => setTimeout(() => { e.target.value = ''; }, 400));</script>")
    f = inv(page)["Q"]
    assert apply(page, f, op="write", value="x")["outcome"] == "verified"
    page.wait_for_timeout(500)
    assert {r["fid"]: r["outcome"] for r in page.evaluate(f"() => {OPS}.sweep()")}[f["fid"]] == "reverted"


def test_engine_writes_do_not_mark_a_field_touched(page, load):
    load(page, fixture_html("workday_text.html"))
    apply(page, inv(page)["City"], op="write", value="Springfield")
    assert inv(page)["City"]["touched"] is False


# --- review carry-overs: popups the engine opens are closed, policy per
# option, typing refusals are outcomes, busy exemption covers clicks, and a
# popup that will not close is not clicked at forever.
def test_explore_leaves_no_menu_open_when_the_widget_rerenders_it_per_keystroke(page, load):
    load(page, fixture_html("react_select.html"))
    explore(page, inv(page)["Country"], "united")
    assert page.evaluate("document.getElementById('menu-root').children.length") == 0


def test_explore_leaves_no_results_open_after_a_debounced_search(page, load):
    load(page, fixture_html("workday_search.html"))
    explore(page, inv(page)["School or University"], "University of Texas")
    page.wait_for_timeout(500)  # past the widget's search debounce
    assert page.evaluate("document.getElementById('portal').children.length") == 0


def test_an_engine_click_on_a_radio_does_not_mark_the_field_touched(page, load):
    load(page, fixture_html("native.html"))
    f = inv(page)
    assert apply(page, f["Willing to relocate?"], op="choose", text="No")["outcome"] == "verified"
    assert apply(page, f["Which days can you work?"], op="set", texts=["Tuesday"])["outcome"] == "verified"
    now = inv(page)
    assert now["Willing to relocate?"]["touched"] is False and now["Which days can you work?"]["touched"] is False


def test_a_policy_blocked_option_is_never_chosen_or_ticked(page, load):
    load(page, POLICY_PAGE)
    f = inv(page)
    assert f["Before you continue"]["policyBlocked"] is False
    assert apply(page, f["Before you continue"], op="choose", text="I certify that the above is true")["outcome"] == "blocked"
    assert page.is_checked("input[value=b]") is False
    row = apply(page, f["Topics"], op="set", texts=["Data", "I agree to the privacy policy"])
    # Policy is told apart from not-found: blocked items are their own list.
    assert (row["outcome"], row["added"], row["missing"], row["blocked"]) == (
        "partial", ["Data"], [], ["I agree to the privacy policy"])
    row = apply(page, inv(page)["Topics"], op="set", texts=["I agree to the privacy policy"])
    assert (row["outcome"], row["missing"], row["blocked"]) == ("blocked", [], ["I agree to the privacy policy"])
    row = apply(page, inv(page)["Topics"], op="set", texts=["Data", "Nope"])
    assert (row["outcome"], row["missing"], row["blocked"]) == ("partial", ["Nope"], [])
    assert page.is_checked("input[value='2']") is False
    got = explore(page, f["Where did you find us?"])
    assert [(o["text"], o["policyBlocked"]) for o in got["options"]] == [
        ("Website", False), ("I consent to the terms of use", True)]
    row = apply(page, f["Where did you find us?"], op="choose", text="I consent to the terms of use")
    assert row["outcome"] == "blocked" and page.inner_text("#src") == "Select One"
    assert page.evaluate("document.getElementById('portal').children.length") == 0


def test_standing_consent_unlocks_consent_options(page, load):
    load(page, POLICY_PAGE)
    f = inv(page, consentForms=True)
    row = apply(page, f["Where did you find us?"], op="choose", text="I consent to the terms of use")
    assert row["outcome"] == "verified"


def test_a_field_that_cannot_take_focus_is_an_outcome_not_an_exception(page, load):
    load(page, "<label for='a'>Q</label><input id='a'>")
    f = inv(page)["Q"]
    page.evaluate("document.getElementById('a').disabled = true")
    row = apply(page, f, op="write", value="x")
    assert (row["outcome"], row["reason"]) == ("unexpected", "unfocusable")


def test_a_popup_that_will_not_close_is_not_clicked_at_forever(page, load):
    load(page, """<label id='l'>Pick</label><button id='b' aria-haspopup='listbox' aria-controls='pop' aria-labelledby='l'>Select One</button>
      <div id='host'></div><script>
      window.outside = 0;
      document.body.addEventListener('click', (e) => { if (e.target === document.body) window.outside += 1; });
      document.getElementById('b').addEventListener('click', (e) => {
        e.stopPropagation();
        if (!document.getElementById('pop')) document.getElementById('host').innerHTML = "<ul role='listbox' id='pop'><li role='option'>A</li></ul>";
      });</script>""")
    f = inv(page)["Pick"]
    for _ in range(4):
        assert [o["text"] for o in explore(page, f)["options"]] == ["A"]
    assert page.evaluate("window.outside") == 2


def test_a_timeout_is_reported_as_timeout_not_cancelled(page, load):
    load(page, fixture_html("workday_search.html"))
    f = inv(page)["School or University"]
    page.evaluate("window.careerStudioCompanion.fillOps.budgets.apply = 150")
    row = apply(page, f, op="choose", text="Texas A&M University", term="Texas")
    assert row["outcome"] == "timeout"
    page.wait_for_timeout(600)
    assert oracle(page, "school") == ""
    assert page.input_value("#school") == ""
    assert not list_shown(page)


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="Task 5: after a timeout, a full-budget choose on the live search "
                          "sequence (press, Enter, radio) verifies")
def test_a_choose_after_a_timeout_starts_clean_and_verifies(page, load):
    load(page, fixture_html("workday_search.html"))
    f = inv(page)["School or University"]
    page.evaluate("window.careerStudioCompanion.fillOps.budgets.apply = 150")
    assert apply(page, f, op="choose", text="Texas A&M University", term="Texas")["outcome"] == "timeout"
    page.wait_for_timeout(600)
    page.evaluate("window.careerStudioCompanion.fillOps.budgets.apply = 6000")
    assert apply(page, f, op="choose", text="Texas A&M University", term="Texas")["outcome"] == "verified"
    assert oracle(page, "school") == "Texas A&M University"


def test_focus_scrolls_to_an_owned_field_only(page, load):
    load(page, fixture_html("native.html"))
    f = inv(page)["Highest degree"]
    assert page.evaluate(f"(fid) => {OPS}.focus(fid)", f["fid"]) is True
    assert page.evaluate("document.activeElement.id") == "deg"
    assert page.evaluate(f"() => {OPS}.focus('zzzzzz-1')") is False


def test_a_popup_that_closes_a_little_late_is_still_closed_every_time(page, load):
    """Only a popup that NEVER closes stops being clicked at: one that closes
    after an exit transition is closed on every operation."""
    load(page, """<label id='l'>Pick</label><button id='b' aria-haspopup='listbox' aria-controls='pop' aria-labelledby='l'>Select One</button>
      <ul role='listbox' id='pop' style='display:none'><li role='option'>A</li><li role='option'>B</li></ul><script>
      const pop = document.getElementById('pop');
      document.getElementById('b').addEventListener('click', (e) => { e.stopPropagation(); pop.style.display = 'block'; });
      document.addEventListener('click', () => setTimeout(() => { pop.style.display = 'none'; }, 120));</script>""")
    f = inv(page)["Pick"]
    for _ in range(4):
        assert [o["text"] for o in explore(page, f)["options"]] == ["A", "B"]
        page.wait_for_timeout(200)
        assert page.evaluate("getComputedStyle(document.getElementById('pop')).display") == "none"


def test_a_passive_option_that_vanished_is_option_missing_not_an_error(page, load):
    load(page, fixture_html("native.html"))
    f = inv(page)
    page.evaluate("""() => { const s = window.careerStudioCompanion.shapes.byName('select'); const real = s.passive;
      s.passive = (el) => { const p = real(el); return { ...p, options: [...p.options, { oid: 'x', text: 'Ghost' }] }; }; }""")
    row = apply(page, f["Highest degree"], op="choose", text="Ghost")
    assert (row["outcome"], row["reason"]) == ("unexpected", "option_missing")
    page.evaluate("""() => { const s = window.careerStudioCompanion.shapes.byName('group'); const real = s.passive;
      s.passive = (el) => { const p = real(el); return { ...p, options: [...p.options, { oid: 'x', text: 'Maybe' }] }; }; }""")
    row = apply(page, f["Willing to relocate?"], op="choose", text="Maybe")
    assert (row["outcome"], row["reason"]) == ("unexpected", "option_missing")


def test_an_editable_box_that_refuses_typing_is_an_outcome(page, load):
    # Chrome does not let a page cancel execCommand's input, so the browser's
    # refusal (an editor that swallows insertText) is simulated directly.
    load(page, "<div contenteditable='true' id='a' aria-label='Summary'></div>"
               "<script>document.execCommand = () => false;</script>")
    row = apply(page, inv(page)["Summary"], op="write", value="x")
    assert (row["outcome"], row["reason"]) == ("unexpected", "page_error")


def test_a_field_removed_mid_operation_is_stale(page, load):
    load(page, "<div><label for='a'>Q</label><input id='a'></div><div><label for='b'>R</label><input id='b'></div><script>"
               "document.getElementById('a').addEventListener('input', (e) => e.target.remove());"
               "document.getElementById('b').addEventListener('focus', (e) => e.target.remove());</script>")
    f = inv(page)
    assert apply(page, f["Q"], op="write", value="x")["outcome"] == "stale"
    assert apply(page, f["R"], op="write", value="x")["outcome"] == "stale"


# --- code-quality review: re-injection, serialization, and commit edge cases
ENGINE = ["content/field-reader.js", "content/fill-base.js", "content/shapes.js",
          "content/inventory.js", "content/fill-core.js", "content/fill-ops.js"]


def _reinject(page, files):
    from tests.browser.conftest import EXTENSION
    for src in files:
        page.add_script_tag(content=(EXTENSION / src).read_text(encoding="utf-8"))


def test_reinjecting_the_engine_keeps_its_state(page, load):
    """panel_prepare re-runs every content script in the same isolated world:
    the user's edits, the Stop latch and the field ids must survive it."""
    load(page, fixture_html("workday_text.html"))
    f = inv(page)["City"]
    page.type("#city", "Mine")
    page.evaluate(f"() => {OPS}.cancel()")
    _reinject(page, ENGINE)
    g = inv(page)["City"]
    assert g["fid"] == f["fid"] and g["touched"] is True
    assert apply(page, g, op="write", value="Springfield")["outcome"] in ("yours", "cancelled")
    assert page.input_value("#city") == "Mine"
    page.evaluate(f"() => {OPS}.inventory({{runId: 'r2'}})")
    zip_ = inv(page)["Postal Code"]
    page.evaluate(f"() => {OPS}.cancel()")
    _reinject(page, ENGINE)
    assert apply(page, zip_, op="write", value="12345")["outcome"] == "cancelled"


def test_a_reinjected_agent_answers_a_message_once(page, load):
    load(page, fixture_html("workday_text.html"))
    page.evaluate("""() => {
      window.chrome = window.chrome || {};
      window.__listeners = [];
      Object.defineProperty(window.chrome, 'runtime', { configurable: true, value: {
        id: 'ext', onMessage: { addListener: (cb) => window.__listeners.push(cb) } } });
      window.__writes = 0;
      document.getElementById('city').addEventListener('focus', () => { window.__writes += 1; });
    }""")
    _reinject(page, ["content/agent.js", "content/agent.js"])
    assert page.evaluate("window.__listeners.length") == 1
    # A listener registered by a dead extension context (reloaded under the
    # page) does not stop a live one from registering.
    page.evaluate("""() => { window.careerStudioCompanion.listenerRuntime = { get id() { throw new Error('invalidated'); } }; }""")
    _reinject(page, ["content/agent.js"])
    assert page.evaluate("window.__listeners.length") == 2
    page.evaluate("window.__listeners.shift()")
    f = inv(page)["City"]
    reply = page.evaluate("""(a) => new Promise((resolve) => {
      for (const cb of window.__listeners) cb({ type: 'fill_apply', actions: [a] }, { id: 'ext' }, resolve);
    })""", {"fid": f["fid"], "fp": f["fp"], "op": "write", "value": "Springfield"})
    assert reply["ok"] and reply["data"][0]["outcome"] == "verified"
    assert page.evaluate("window.__writes") == 1


def test_concurrent_operations_run_one_at_a_time(page, load):
    load(page, fixture_html("workday_text.html"))
    f = inv(page)
    page.evaluate("""() => { window.__log = [];
      for (const id of ['city', 'zip']) for (const ev of ['focus', 'blur'])
        document.getElementById(id).addEventListener(ev, () => window.__log.push(id + ':' + ev)); }""")
    rows = page.evaluate(f"""(p) => Promise.all([
        {OPS}.apply([p[0]]).then((r) => {{ window.__log.push('city:done'); return r; }}),
        {OPS}.apply([p[1]]).then((r) => {{ window.__log.push('zip:done'); return r; }})])""", [
        {"fid": f["City"]["fid"], "fp": f["City"]["fp"], "op": "write", "value": "Springfield"},
        {"fid": f["Postal Code"]["fid"], "fp": f["Postal Code"]["fp"], "op": "write", "value": "12345"}])
    assert [r[0]["outcome"] for r in rows] == ["verified", "verified"]
    assert page.evaluate("window.__log") == ["city:focus", "city:blur", "city:done", "zip:focus", "zip:blur", "zip:done"]


FREE_TEXT = """<label for='loc'>Location (City)</label>
<input id='loc' role='combobox' aria-autocomplete='list' aria-controls='lb'>
<ul id='lb' role='listbox' style='display:none'></ul>
<script>
(() => {
  const i = document.getElementById('loc'), lb = document.getElementById('lb');
  const DATA = ['Springfield', 'Springfield, IL', 'Spring Hill'];
  i.addEventListener('input', () => setTimeout(() => {
    const q = i.value.toLowerCase();
    lb.innerHTML = '';
    for (const d of DATA.filter((x) => q && x.toLowerCase().startsWith(q))) {
      const li = document.createElement('li'); li.setAttribute('role', 'option'); li.textContent = d;
      li.addEventListener('click', () => { i.value = d; lb.style.display = 'none'; });
      lb.append(li);
    }
    lb.style.display = lb.children.length ? 'block' : 'none';
  }, 50));
  document.addEventListener('click', (e) => { if (!lb.contains(e.target) && e.target !== i) lb.style.display = 'none'; });
})();
</script>"""


def test_a_free_text_pick_equal_to_the_typed_query_is_kept(page, load):
    load(page, FREE_TEXT)
    f = inv(page)["Location (City)"]
    row = apply(page, f, op="choose", text="Springfield")
    assert (row["outcome"], row["committed"]) == ("verified", "Springfield")
    assert page.input_value("#loc") == "Springfield"


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="Task 5: a multi search ticks each missing item's checkbox once and "
                          "never an item it already holds, read back from the pills (Task 3)")
def test_a_set_never_clicks_an_item_that_is_already_there(page, load):
    """The multiselect toggles (a second tick un-picks) and shows an error: SQL
    is kept (never re-ticked) and Python is added."""
    html = fixture_html("workday_search.html").replace(
        '<input id="skills"', '<p data-automation-id="errorMessage">Please fix</p><input id="skills"')
    assert html != fixture_html("workday_search.html")
    load(page, html)
    page.evaluate("""() => { window.clicks = [];
      document.getElementById('portal').addEventListener('click', (e) => {
        if (e.target.matches('input[type=checkbox]')) window.clicks.push(e.target.closest('[role=option]').textContent);
      }, true); }""")
    row = apply(page, inv(page)["Type to Add Skills"], op="set", texts=["SQL", "Python"])
    assert row["committed"] == ["SQL", "Python"] and row["added"] == ["Python"]
    assert oracle(page, "skills") == ["SQL", "Python"]
    assert page.evaluate("window.clicks") == ["Python"]


def test_stop_closes_a_category_popup_left_open(page, load):
    load(page, CATEGORY_POPUP)
    row = apply(page, inv(page)["How did you hear about us?"], op="choose", text="Job Board")
    assert row["reason"] == "new_options"
    page.evaluate(f"() => {OPS}.cancel()")
    page.wait_for_timeout(400)
    assert page.evaluate("document.getElementById('portal').children.length") == 0


def test_choose_on_a_multiple_select_keeps_the_other_selections(page, load):
    load(page, fixture_html("native.html"))
    row = apply(page, inv(page)["Languages"], op="choose", text="Hindi")
    assert row["outcome"] == "verified"
    assert page.evaluate("[...document.getElementById('lang').selectedOptions].map(o => o.text)") == ["English", "Hindi"]


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="Task 5: search commits through the row's radio; the engine then "
                          "takes back a query the widget left")
def test_a_query_left_in_the_box_beside_a_committed_pill_is_taken_back(page, load):
    html = fixture_html("workday_search.html").replace(
        "      inputOf(id).value = \"\";\n      close();", "      close();")
    assert html != fixture_html("workday_search.html")
    load(page, html)
    row = apply(page, inv(page)["School or University"], op="choose", text="The University of Texas at Dallas",
                term="Texas")
    assert (row["outcome"], row["committed"]) == ("verified", "The University of Texas at Dallas")
    assert oracle(page, "school") == "The University of Texas at Dallas"
    assert page.input_value("#school") == ""


def test_a_new_run_waits_for_the_operation_in_flight(page, load):
    """A new runId releases the Stop latch — never under an operation that
    was queued before it and must still start cancelled."""
    load(page, fixture_html("workday_text.html"))
    f = inv(page)
    page.evaluate(f"() => {OPS}.cancel()")
    rows = page.evaluate(f"""(p) => {{
      const queued = {OPS}.apply([p]);
      {OPS}.inventory({{runId: 'fresh'}});
      return queued; }}""", {"fid": f["City"]["fid"], "fp": f["City"]["fp"], "op": "write", "value": "Springfield"})
    assert rows[0]["outcome"] == "cancelled" and page.input_value("#city") == ""
