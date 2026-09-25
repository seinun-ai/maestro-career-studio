"""The generic fill mechanics (fill-core.js) through the page operations
(fill-ops.js), in real Chromium against the committed fixtures."""

from tests.browser.conftest import fixture_html

OPS = "window.careerStudioCompanion.fillOps"


def inv(page, **opts):
    return {f["question"]: f for f in page.evaluate(f"(o) => {OPS}.inventory(o).fields", opts)}


def apply(page, f, **action):
    return page.evaluate(f"(a) => {OPS}.apply([a])", {"fid": f["fid"], "fp": f["fp"], **action})[0]


def explore(page, f, term=None):
    return page.evaluate(f"(r) => {OPS}.explore([r])", {"fid": f["fid"], "fp": f["fp"], "term": term})[f["fid"]]


# --- text-like
def test_text_commits_where_the_page_only_takes_real_typing(page, load):
    load(page, fixture_html("workday_text.html"))
    row = apply(page, inv(page)["City"], op="write", value="Springfield")
    assert row["outcome"] == "verified" and page.evaluate("window.committed.city") == "Springfield"
    assert page.get_attribute("#city", "aria-invalid") == "false"


def test_sweep_recommits_text_that_shows_an_error_with_its_own_value(page, load):
    load(page, fixture_html("workday_text.html"))
    assert [r["outcome"] for r in page.evaluate(f"() => {OPS}.sweep()")] == ["verified"]
    assert page.evaluate("window.committed.zip") == "00000"


def test_a_text_the_page_clears_on_blur_is_reverted(page, load):
    load(page, "<label for='a'>Q</label><input id='a'><script>"
               "document.getElementById('a').addEventListener('focusout', e => { e.target.value = ''; });</script>")
    assert apply(page, inv(page)["Q"], op="write", value="x")["outcome"] == "reverted"


def test_workday_date_sections_are_written_before_one_blur(page, load):
    load(page, fixture_html("workday_date.html"))
    fields = inv(page)
    assert apply(page, fields["From"], op="write", value="2019-08")["outcome"] == "verified"
    assert (page.input_value("#m"), page.input_value("#y")) == ("08", "2019")
    assert apply(page, fields["End date"], op="write", value="2021-05")["outcome"] == "verified"
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
def test_a_workday_dropdown_is_explored_and_closed_then_committed(page, load):
    load(page, fixture_html("workday_listbox.html"))
    f = inv(page)["Are you legally authorized to work in the United States?"]
    got = explore(page, f)
    assert [o["text"] for o in got["options"]] == ["Yes", "No"] and got["complete"]
    assert page.evaluate("document.getElementById('portal').children.length") == 0
    row = apply(page, f, op="choose", text="No")
    assert (row["outcome"], row["committed"]) == ("verified", "No")


def test_a_category_is_unexpected_with_its_children_and_the_popup_stays_open(page, load):
    load(page, fixture_html("workday_listbox.html"))
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


def test_workday_search_waits_past_searching_and_commits_the_pill(page, load):
    load(page, fixture_html("workday_search.html"))
    f = inv(page)["School or University"]
    got = explore(page, f, "University of Texas")
    assert [o["text"] for o in got["options"]] == [
        "University of Texas at Austin", "University of Texas at Dallas", "Not in List"]
    assert page.input_value("#school") == ""
    row = apply(page, f, op="choose", text="University of Texas at Dallas", term="Texas")
    assert (row["outcome"], row["committed"]) == ("verified", "University of Texas at Dallas")


def test_a_search_set_keeps_existing_chips_and_reports_partial_honestly(page, load):
    load(page, fixture_html("workday_search.html"))
    f = inv(page)["Type to Add Skills"]
    row = apply(page, f, op="set", texts=["Python", "Rust"])
    assert row["outcome"] == "partial" and row["added"] == ["Python"] and row["missing"] == ["Rust"]
    assert row["committed"] == ["SQL", "Python"]


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
    assert page.evaluate("document.getElementById('school-pills').children.length") == 0


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
def test_explore_leaves_no_menu_open_even_when_the_widget_rerenders_it(page, load):
    load(page, fixture_html("react_select.html"))
    explore(page, inv(page)["Country"], "united")
    assert page.evaluate("document.getElementById('menu-root').children.length") == 0
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


POLICY_PAGE = """
<fieldset><legend>Before you continue</legend>
  <label><input type='radio' name='c' value='a'>Email me updates</label>
  <label><input type='radio' name='c' value='b'>I certify that the above is true</label></fieldset>
<fieldset><legend>Topics</legend>
  <label><input type='checkbox' name='t' value='1'>Data</label>
  <label><input type='checkbox' name='t' value='2'>I agree to the privacy policy</label></fieldset>
<label id='src-l'>Where did you find us?</label>
<button id='src' aria-haspopup='listbox' aria-labelledby='src-l'>Select One</button>
<div id='portal'></div>
<script>
(() => {
  const btn = document.getElementById('src');
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    document.getElementById('portal').innerHTML =
      "<ul role='listbox'><li role='option'>Website</li><li role='option'>I consent to the terms of use</li></ul>";
    for (const li of document.querySelectorAll('#portal li')) {
      li.addEventListener('click', (ev) => { ev.stopPropagation(); btn.textContent = li.textContent; document.getElementById('portal').innerHTML = ''; });
    }
  });
  document.addEventListener('click', () => { document.getElementById('portal').innerHTML = ''; });
})();
</script>"""


def test_a_policy_blocked_option_is_never_chosen_or_ticked(page, load):
    load(page, POLICY_PAGE)
    f = inv(page)
    assert f["Before you continue"]["policyBlocked"] is False
    assert apply(page, f["Before you continue"], op="choose", text="I certify that the above is true")["outcome"] == "blocked"
    assert page.is_checked("input[value=b]") is False
    row = apply(page, f["Topics"], op="set", texts=["Data", "I agree to the privacy policy"])
    assert (row["outcome"], row["missing"]) == ("partial", ["I agree to the privacy policy"])
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
    assert page.evaluate("document.getElementById('school-pills').children.length") == 0
    page.evaluate("window.careerStudioCompanion.fillOps.budgets.apply = 6000")
    assert apply(page, f, op="choose", text="Texas A&M University", term="Texas")["outcome"] == "verified"


def test_focus_scrolls_to_an_owned_field_only(page, load):
    load(page, fixture_html("native.html"))
    f = inv(page)["Highest degree"]
    assert page.evaluate(f"(fid) => {OPS}.focus(fid)", f["fid"]) is True
    assert page.evaluate("document.activeElement.id") == "deg"
    assert page.evaluate(f"() => {OPS}.focus('zzzzzz-1')") is False
