"""The generic fill mechanics (fill-core.js) through the page operations
(fill-ops.js), in real Chromium against the committed fixtures: keyboard-only
and deaf widgets, safety and lifecycle edges, and engine re-injection."""

from tests.browser.conftest import fixture_html
from tests.browser.pages import (
    CATEGORY_POPUP,
    ENTER_PICKS,
    OPS,
    POLICY_PAGE,
    SINGLE_HIT_SEARCH,
    apply,
    explore,
    inv,
    list_shown,
    oracle,
)


# --- a widget that ignores the engine's gestures says so (no_effect)
DEAF = """<label id='l'>Pick one</label><div><button id='deaf' aria-haspopup='listbox' aria-labelledby='l'>Select One</button></div>
<label for='t'>Code</label><input id='t'>
<script>document.getElementById('t').addEventListener('input', (e) => { e.target.value = ''; });</script>"""


def test_a_widget_that_ignores_every_gesture_reports_no_effect(page, load):
    """With the kinds of gesture it tried: a press and then the keyboard for
    the button; typing (insertText and its setter fallback: one gesture) for
    the box."""
    load(page, DEAF)
    f = inv(page)
    got = explore(page, f["Pick one"])
    assert (got["error"], sorted(got["gestures"])) == ("no_effect", ["keyboard", "pointer"])
    row = apply(page, f["Pick one"], op="choose", text="Yes")
    assert (row["outcome"], row["reason"], sorted(row["gestures"])) == ("unexpected", "no_effect", ["keyboard", "pointer"])
    row = apply(page, f["Code"], op="write", value="ABC")
    assert (row["outcome"], row["reason"], row["gestures"]) == ("reverted", "no_effect", ["type"])


def test_a_number_box_given_text_refuses_the_value_in_one_gesture(page, load):
    load(page, "<label for='n'>Years</label><input id='n' type='number'>")
    row = apply(page, inv(page)["Years"], op="write", value="ten")
    assert (row["outcome"], row["reason"], row["gestures"]) == ("reverted", "no_effect", ["type"])


# A popup that ignores a press and opens from the keyboard (ArrowDown), with
# a backing input beside it; and one whose press appends a ROLE-LESS list to
# <body> — a reaction the engine cannot read as a popup, but a reaction.
KEYBOARD_ONLY = """<label id='l'>Willing to travel?</label>
<div><button id='kb' aria-haspopup='listbox' aria-labelledby='l'>Select One</button><input type='hidden' value=''></div>
<label id='m'>Shift</label><div><button id='bare' aria-haspopup='listbox' aria-labelledby='m'>Select One</button></div>
<script>
(() => {
  window.bareKeys = [];
  document.getElementById('bare').addEventListener('keydown', (e) => window.bareKeys.push(e.key));
  const btn = document.getElementById('kb');
  btn.addEventListener('keydown', (e) => {
    if (e.key !== 'ArrowDown' || document.getElementById('kb-list')) return;
    const ul = document.createElement('ul');
    ul.id = 'kb-list'; ul.setAttribute('role', 'listbox');
    ul.innerHTML = "<li role='option'>Yes</li><li role='option'>No</li>";
    for (const li of ul.children) li.addEventListener('click', (ev) => {
      ev.stopPropagation(); btn.textContent = li.textContent; btn.nextElementSibling.value = li.textContent; ul.remove(); });
    document.body.append(ul);
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') document.getElementById('kb-list')?.remove(); });
  document.getElementById('bare').addEventListener('click', () => {
    const menu = document.createElement('div');
    menu.className = 'menu'; menu.innerHTML = '<div>Day</div><div>Night</div>';
    document.body.append(menu);
  });
})();
</script>"""


def test_a_popup_that_opens_only_from_the_keyboard_is_filled(page, load):
    load(page, KEYBOARD_ONLY)
    f = inv(page)["Willing to travel?"]
    assert [o["text"] for o in explore(page, f)["options"]] == ["Yes", "No"]
    row = apply(page, f, op="choose", text="No")
    assert (row["outcome"], row["committed"]) == ("verified", "No")


def test_a_press_that_opens_a_role_less_list_had_an_effect(page, load):
    """…so no key follows it: not ArrowDown, and never an Enter."""
    load(page, KEYBOARD_ONLY)
    f = inv(page)["Shift"]
    got = explore(page, f)
    assert got["error"] == "no_popup" and "gestures" not in got
    assert apply(page, f, op="choose", text="Day")["reason"] == "no_popup"
    assert page.evaluate("window.bareKeys") == []


def test_no_enter_follows_a_press_that_opened_a_role_less_list(page, load):
    load(page, ENTER_PICKS)
    apply(page, inv(page)["Team"], op="choose", text="Blue")
    assert oracle(page, "team") == "" and page.evaluate("window.teamKeys") == []


def test_a_press_that_reacted_once_is_never_followed_by_keys(page, load):
    """Explore's press opened the role-less list, which stays up; choose's
    press on the SAME page then changes nothing — the list is still open, so
    a key would act on it. No key is sent, the undo's own open included."""
    load(page, ENTER_PICKS)
    f = inv(page)["Team"]
    explore(page, f)
    apply(page, f, op="choose", text="Blue")
    assert oracle(page, "team") == "" and page.inner_text("#team") == "Select One"
    assert page.evaluate("window.teamKeys") == []


# A press does nothing; ArrowDown renders role-less rows into a portal that
# was already on the page (not a new <body> child), the first highlighted —
# and, once they are up, only moves the highlight (a class change); an Enter
# would accept the highlighted row.
PORTAL_ENTER = """<label id='l'>Team</label>
<div><button id='pb' aria-haspopup='listbox' aria-labelledby='l'>Select One</button><input type='hidden' value=''></div>
<div id='portal'><div class='host'></div></div>
<script>
(() => {
  const oracle = (window.__oracle = window.__oracle || {});
  oracle.pb = "";
  window.pbKeys = [];
  const pb = document.getElementById('pb');
  const host = document.querySelector('#portal .host');
  pb.addEventListener('keydown', (e) => {
    window.pbKeys.push(e.key);
    if (e.key === 'ArrowDown' && !host.children.length) host.innerHTML = "<div class='hl'>Red</div><div>Blue</div>";
    else if (e.key === 'ArrowDown') for (const r of host.children) r.classList.toggle('hl');
    const hl = host.querySelector('.hl');
    if (e.key === 'Enter' && hl) { pb.textContent = hl.textContent; pb.nextElementSibling.value = hl.textContent; oracle.pb = hl.textContent; }
  });
})();
</script>"""


def test_no_enter_follows_an_arrow_down_that_filled_a_portal(page, load):
    load(page, PORTAL_ENTER)
    row = apply(page, inv(page)["Team"], op="choose", text="Blue")
    assert row["reason"] == "no_popup"   # it reacted: never no_effect
    assert oracle(page, "pb") == "" and page.evaluate("window.pbKeys") == ["ArrowDown"]


def test_a_list_the_keyboard_opened_blocks_keys_on_the_next_open(page, load):
    """Explore's ArrowDown opened a role-less list (no Enter followed). On
    the same page a later choose's press changes nothing and an ArrowDown
    would only move the highlight: no key is sent at all."""
    load(page, PORTAL_ENTER)
    f = inv(page)["Team"]
    explore(page, f)
    apply(page, f, op="choose", text="Blue")
    assert oracle(page, "pb") == "" and page.evaluate("window.pbKeys") == ["ArrowDown"]


def test_a_deaf_control_that_cannot_take_focus_reports_no_effect(page, load):
    load(page, "<label id='l'>Pick</label><div><div id='dd' role='button' aria-haspopup='listbox' "
               "aria-labelledby='l'>Select One</div></div>")
    got = explore(page, inv(page)["Pick"])
    assert (got["error"], got["gestures"]) == ("no_effect", ["pointer"])


def test_a_pill_removal_that_takes_a_moment_is_not_reported_as_stuck(page, load):
    load(page, SINGLE_HIT_SEARCH)
    page.evaluate("window.slowRemove = 400")
    got = explore(page, inv(page)["Field of study"], "Analytics")
    assert "error" not in got and oracle(page, "field_of_study") == ""


def test_a_value_the_keyboard_committed_is_reported_never_silent(page, load):
    load(page, ENTER_PICKS)
    f = inv(page)["Relocate?"]
    row = apply(page, f, op="choose", text="No")
    assert (row["outcome"], row["reason"], row["committed"]) == ("unexpected", "committed_while_opening", "Yes")
    assert oracle(page, "blind") == "Yes"
    load(page, ENTER_PICKS)
    got = explore(page, inv(page)["Relocate?"])
    assert (got["error"], got["committed"]) == ("committed_while_exploring", "Yes")


def test_a_gesture_that_changed_something_is_never_no_effect(page, load):
    """react-select with its clicks refused: the typing opened its menu, so the
    widget answers input — the pick is not committed, not unsupported."""
    load(page, fixture_html("react_select.html"))
    page.evaluate("window.rejectClicks = true")
    row = apply(page, inv(page)["Country"], op="choose", text="Canada", term="can")
    assert (row["outcome"], row["reason"]) == ("unexpected", "not_committed")
    assert oracle(page, "country") == ""


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
    assert oracle(page, "city") is None   # the user's typing never left the box: nothing committed


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
    assert page.input_value("#city") == "Springfield" and oracle(page, "city") == "Springfield"


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
    assert inv(page)["City"]["touched"] is False and oracle(page, "city") == "Springfield"


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


def test_a_search_choose_has_the_searchs_own_settle_on_top_of_the_apply_budget(page, load):
    """Live 2026-10-15: the choose re-types the term the explore already waited ~3.5 s on, and 6 s was not enough for both."""
    load(page, fixture_html("workday_search.html"))
    f = inv(page)["School or University"]
    page.evaluate("window.careerStudioCompanion.fillOps.budgets.apply = 150")
    assert apply(page, f, op="choose", text="Texas A&M University", term="Texas")["outcome"] == "verified"
    assert oracle(page, "school") == "Texas A&M University"


def test_a_choose_with_no_search_term_keeps_the_plain_apply_budget(page, load):
    load(page, fixture_html("workday_listbox.html"))
    f = inv(page)["Degree"]
    page.evaluate("window.careerStudioCompanion.fillOps.budgets.apply = 1")
    assert apply(page, f, op="choose", text="Masters")["outcome"] == "timeout"


def test_a_timeout_is_reported_as_timeout_not_cancelled(page, load):
    load(page, fixture_html("workday_search.html"))
    f = inv(page)["School or University"]
    page.evaluate("window.careerStudioCompanion.fillOps.budgets.apply = 150; window.careerStudioCompanion.fillOps.budgets.searchSettle = 0")
    row = apply(page, f, op="choose", text="Texas A&M University", term="Texas")
    assert row["outcome"] == "timeout"
    page.wait_for_timeout(600)
    assert oracle(page, "school") == ""
    assert page.input_value("#school") == ""
    assert not list_shown(page)


def test_a_choose_after_a_timeout_starts_clean_and_verifies(page, load):
    load(page, fixture_html("workday_search.html"))
    f = inv(page)["School or University"]
    page.evaluate("window.careerStudioCompanion.fillOps.budgets.apply = 150; window.careerStudioCompanion.fillOps.budgets.searchSettle = 0")
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
    assert page.input_value("#city") == "Mine" and oracle(page, "city") is None
    page.evaluate(f"() => {OPS}.inventory({{runId: 'r2'}})")
    zip_ = inv(page)["Postal Code"]
    page.evaluate(f"() => {OPS}.cancel()")
    _reinject(page, ENGINE)
    assert apply(page, zip_, op="write", value="12345")["outcome"] == "cancelled"
    assert oracle(page, "zip") is None


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
    assert page.evaluate("window.__writes") == 1 and oracle(page, "city") == "Springfield"


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
    assert (oracle(page, "city"), oracle(page, "zip")) == ("Springfield", "12345")
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
