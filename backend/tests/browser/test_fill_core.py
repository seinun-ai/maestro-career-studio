"""The generic fill mechanics (fill-core.js) through the page operations
(fill-ops.js), in real Chromium against the committed fixtures."""

import time

import pytest

from tests.browser.conftest import ENGINE_SOURCES, EXTENSION, fixture_html
from tests.browser.pages import (
    CATEGORY_POPUP,
    POLICY_PAGE,
    SELECT_ON_CLOSE,
    SINGLE_HIT_SEARCH,
    in_both_windows,
    list_shown,
    oracle,
)

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


@in_both_windows()
def test_a_native_select_choice_is_entered_and_left_once(window, request, load):
    page = request.getfixturevalue(window)
    load(page, "<label for='s'>Country</label><select id='s'><option></option><option>Canada</option></select>")
    page.evaluate("""() => { window.heard = {focus: 0, focusout: 0}; const s = document.getElementById('s');
      s.addEventListener('focus', () => heard.focus++); s.addEventListener('focusout', () => heard.focusout++); }""")
    assert apply(page, inv(page)["Country"], op="choose", text="Canada")["outcome"] == "verified"
    assert page.evaluate("window.heard") == {"focus": 1, "focusout": 1}


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


def test_popup_open_state_is_judged_by_visibility(page, load):
    """An outside click HIDES a Workday list and leaves aria-expanded="true"
    (notes §8a): the list is closed because it is not visible, so nothing
    tries to close it again and the next press opens it."""
    load(page, fixture_html("workday_listbox.html"))
    f = inv(page)["Are you legally authorized to work in the United States?"]
    explore(page, f)
    assert page.get_attribute("#auth", "aria-expanded") == "true" and not page.is_visible("#auth-list")
    assert page.evaluate("window.careerStudioCompanion.fillBase.engineOpen()") is False
    row = apply(page, f, op="choose", text="Yes")
    assert (row["outcome"], row["committed"]) == ("verified", "Yes") and oracle(page, "auth") == "Yes"


def test_a_long_popup_commits_an_option_below_the_fold(page, load):
    """Degree lists 12 options in a 5-row window; "Masters" (the 10th) is
    reached by scrolling, and the whole list is read, placeholder aside."""
    load(page, fixture_html("workday_listbox.html"))
    f = inv(page)["Degree"]
    got = explore(page, f)
    assert got["complete"] and [o["text"] for o in got["options"]] == [
        "Associates", "Bachelors", "Certificate", "College Diploma", "Doctorate", "GED", "HS Diploma", "JD",
        "Masters", "MBA", "Other"]
    row = apply(page, f, op="choose", text="Masters")
    assert (row["outcome"], row["committed"]) == ("verified", "Masters") and oracle(page, "degree") == "Masters"
    # It was below the fold: the list only shows its first rows when opened.
    page.click("#degree")
    page.evaluate("document.getElementById('degree-list').scrollTop = 0")
    assert page.evaluate("""() => { const ul = document.getElementById('degree-list');
        const li = [...ul.children].find((o) => o.textContent === 'Masters');
        return li.offsetTop >= ul.scrollTop + ul.clientHeight; }""")


# --- committed evidence (notes §8a): a popup pick shows at once, but only its
# hidden backing input says the app took it.
def backing(page, button_id):
    return page.evaluate("(id) => document.getElementById(id).parentElement.querySelector('.hidden-backing').value",
                         button_id)


@in_both_windows()
def test_popup_evidence_is_the_backing_input_changing(window, request, load):
    page = request.getfixturevalue(window)
    load(page, fixture_html("workday_listbox.html"))
    row = apply(page, inv(page)["Degree"], op="choose", text="Masters")
    assert row["outcome"] == "verified" and oracle(page, "degree") == "Masters" and backing(page, "degree")


@in_both_windows()
def test_a_popup_pick_that_shows_but_never_saves_is_unconfirmed(window, request, load):
    """adversarial_revert.html: the first pick shows its text, the backing
    input stays empty (the app never took it). Never verified, never clicked
    a second time."""
    page = request.getfixturevalue(window)
    load(page, fixture_html("adversarial_revert.html"))
    page.evaluate("""() => { window.optionClicks = 0; document.addEventListener('click', (e) => {
        if (e.target.closest('#relocate-list li')) window.optionClicks += 1; }, true); }""")
    row = apply(page, inv(page)["Are you willing to relocate?"], op="choose", text="Yes")
    assert (row["outcome"], row["committed"]) == ("unconfirmed", "Yes")
    assert page.evaluate("window.optionClicks") == 1
    assert oracle(page, "relocate") == "" and backing(page, "relocate") == ""
    # The take-back the notes saw: the display goes; the app never held it.
    assert page.evaluate("window.__revertNow()") is True
    assert page.inner_text("#relocate") == "Select One" and oracle(page, "relocate") == ""


def undo(page, button_id):
    """The engine's own undo (fillCore.choose with `undo`): no page action carries it."""
    return page.evaluate("""(id) => { const ns = window.careerStudioCompanion; const el = document.getElementById(id);
        return ns.fillBase.withinBudget((t) => ns.fillCore.choose(el, ns.shapes.of(el), {text: 'Select One', undo: true}, t), 6000); }""",
                         button_id)


def test_placeholder_pick_clears_the_evidence(page, load):
    """Choosing "Select One" is the engine's own undo: verified only when the
    popup shows nothing AND the backing input emptied."""
    load(page, fixture_html("workday_listbox.html"))
    assert apply(page, inv(page)["Degree"], op="choose", text="Masters")["outcome"] == "verified"
    assert undo(page, "degree")["outcome"] == "verified"
    assert page.inner_text("#degree") == "Select One" and oracle(page, "degree") == "" and backing(page, "degree") == ""
    # A popup that shows the placeholder while the app still holds a value is not undone.
    assert apply(page, inv(page)["Degree"], op="choose", text="Masters")["outcome"] == "verified"
    page.evaluate("""() => { const li = [...document.querySelectorAll('#degree-list li')].find((o) => o.textContent === 'Select One');
        li.replaceWith(Object.assign(li.cloneNode(true), {onclick: (e) => { e.stopPropagation();
          document.getElementById('degree').textContent = 'Select One'; document.getElementById('degree-list').style.display = 'none'; }})); }""")
    assert undo(page, "degree")["outcome"] == "unconfirmed" and oracle(page, "degree") == "Masters"


def test_an_answer_already_held_is_not_clicked_again(page, load):
    """A one-answer widget that shows AND holds the answer is left alone: a
    popup whose backing input holds it, a search box whose pill states it."""
    load(page, fixture_html("workday_listbox.html"))
    assert apply(page, inv(page)["Degree"], op="choose", text="Masters")["outcome"] == "verified"
    held = backing(page, "degree")
    page.evaluate("""() => { window.optionClicks = 0; document.addEventListener('click', (e) => {
        if (e.target.closest('#degree-list li') || e.target.id === 'degree') window.optionClicks += 1; }, true); }""")
    assert apply(page, inv(page)["Degree"], op="choose", text="Masters")["outcome"] == "verified"
    assert page.evaluate("window.optionClicks") == 0 and backing(page, "degree") == held
    load(page, fixture_html("workday_search.html"))
    row = apply(page, inv(page)["Type to Add Skills"], op="choose", text="SQL")
    assert (row["outcome"], row["committed"]) == ("verified", ["SQL"])
    assert page.input_value("#skills") == "" and oracle(page, "skills") == ["SQL"]


def test_unmoved_proof_verifies_only_an_answer_the_field_already_held(page, load):
    """verify with a pick's snapshot: the proof did not move, so the pick is
    verified only if the display already stated it before."""
    load(page, fixture_html("workday_listbox.html"))
    assert apply(page, inv(page)["Degree"], op="choose", text="Masters")["outcome"] == "verified"
    got = page.evaluate("""() => { const ns = window.careerStudioCompanion; const el = document.getElementById('degree');
        const shape = ns.shapes.of(el); const before = shape.evidence(el);
        return [ns.fillCore.verify(el, shape, 'Masters', {before}),
                ns.fillCore.verify(el, shape, 'Masters', {before: {...before, display: ''}})]; }""")
    assert got == ["verified", "unconfirmed"]


# A generic popup (not Workday) whose question wrapper also holds hidden
# inputs that are NOT its backing: proof must stay null and the display decide.
GENERIC_POPUP = """<div id='portal'></div><script>
(() => { const btn = document.getElementById('src'); const list = document.getElementById('src-list');
  btn.addEventListener('click', (e) => { e.stopPropagation(); list.style.display = list.style.display === 'none' ? 'block' : 'none'; });
  for (const li of list.querySelectorAll('li')) li.addEventListener('click', (e) => {
    e.stopPropagation(); btn.textContent = li.textContent; list.style.display = 'none'; });
  document.addEventListener('click', () => { list.style.display = 'none'; });
})();
</script>"""
OPTIONS = "<ul role='listbox' id='src-list' style='display:none'><li role='option'>Website</li><li role='option'>LinkedIn</li></ul>"


@pytest.mark.parametrize("markup", [
    # An "Other, please specify" text box, hidden, in the question's wrapper.
    f"""<div class='question'><label id='l'>How did you hear about us?</label>
      <div class='wrap'><button id='src' aria-haspopup='listbox' aria-labelledby='l' aria-controls='src-list'>Select One</button></div>
      <input type='text' style='display:none' name='other_source'></div>{OPTIONS}""",
    # A closed menu next to the button, holding its own (hidden) search box.
    """<label id='l'>How did you hear about us?</label>
      <div><button id='src' aria-haspopup='listbox' aria-labelledby='l' aria-controls='src-list'>Select One</button>
      <div role='menu' id='src-list' style='display:none'><input type='text' placeholder='Search'>
        <ul role='listbox'><li role='option'>Website</li><li role='option'>LinkedIn</li></ul></div></div>""",
], ids=["hidden-other-box-in-wrapper", "search-box-in-closed-menu"])
def test_a_hidden_input_that_is_not_beside_the_button_is_no_backing(page, load, markup):
    load(page, markup + GENERIC_POPUP)
    assert page.evaluate("""() => { const el = document.getElementById('src');
        return window.careerStudioCompanion.shapes.of(el).evidence(el).proof; }""") is None
    row = apply(page, inv(page)["How did you hear about us?"], op="choose", text="LinkedIn")
    assert (row["outcome"], row["committed"]) == ("verified", "LinkedIn")


def test_a_placeholder_option_is_never_offered_as_an_answer(page, load):
    """Live Workday lists "Select One" as an option (§3a, §8b): explore never
    returns it, nor an empty or dash-only row — and a real option that only
    mentions selecting is kept."""
    load(page, fixture_html("workday_listbox.html"))
    got = explore(page, inv(page)["Degree"])
    assert "Select One" not in [o["text"] for o in got["options"]] and len(got["options"]) == 11
    load(page, """<label id='l'>Plan</label><button id='p' aria-haspopup='listbox' aria-labelledby='l'>Select One</button>
      <div id='portal'></div><script>
      document.getElementById('p').addEventListener('click', (e) => { e.stopPropagation();
        document.getElementById('portal').innerHTML = "<ul role='listbox'><li role='option'>-- Select --</li>"
          + "<li role='option'>—</li><li role='option'>Please choose an option</li><li role='option'>Basic</li>"
          + "<li role='option'>Select Plus</li></ul>"; });
      document.addEventListener('click', () => { document.getElementById('portal').innerHTML = ''; });
      </script>""")
    got = explore(page, inv(page)["Plan"])
    assert [o["text"] for o in got["options"]] == ["Basic", "Select Plus"] and got["complete"]


def test_a_placeholder_is_never_chosen_as_an_answer(page, load):
    """Live popups list "Select One" as an option (§3a, §8b): a decision that
    names it is refused, never clicked, and never verified as an empty answer."""
    load(page, fixture_html("workday_listbox.html"))
    assert apply(page, inv(page)["Degree"], op="choose", text="Masters")["outcome"] == "verified"
    row = apply(page, inv(page)["Degree"], op="choose", text="Select One")
    assert (row["outcome"], row["reason"], row["committed"]) == ("unexpected", "placeholder", "Masters")
    assert oracle(page, "degree") == "Masters" and backing(page, "degree")


def test_the_sweep_catches_a_popup_whose_backing_input_emptied(page, load):
    """The button still shows the pick; the app no longer holds it (§8a)."""
    load(page, fixture_html("workday_listbox.html"))
    f = inv(page)["Degree"]
    assert apply(page, f, op="choose", text="Masters")["outcome"] == "verified"
    page.evaluate("() => { document.getElementById('degree').parentElement.querySelector('.hidden-backing').value = ''; }")
    assert {r["fid"]: r["outcome"] for r in page.evaluate(f"() => {OPS}.sweep()")}[f["fid"]] == "reverted"


# A generic search box whose results are checkbox rows (several answers) or
# radio rows (one): the rows are the only place single-or-several shows.
ROWS_PAGE = """<label for='k'>Skills</label><div><input id='k' role='combobox' aria-autocomplete='list' data-kind='checkbox'></div>
<label for='s'>School</label><div><input id='s' role='combobox' aria-autocomplete='list' data-kind='radio'></div>
<div id='portal'></div>
<script>
for (const input of document.querySelectorAll('input[role=combobox]')) {
  input.addEventListener('input', () => {
    document.getElementById('portal').innerHTML = input.value ? "<div role='listbox'>" + ['Python', 'Python 3']
      .map((t) => `<div role='option'><input type='${input.dataset.kind}' tabindex='-1'>${t}</div>`).join('') + '</div>' : '';
  });
}
</script>"""


def test_a_search_widgets_rows_say_one_answer_or_several(page, load):
    load(page, ROWS_PAGE)
    f = inv(page)
    assert (f["Skills"]["multi"], f["School"]["multi"]) == (None, None)   # not known before a list opened
    assert explore(page, f["Skills"], "Py")["multi"] is True
    assert explore(page, f["School"], "Py")["multi"] is False
    now = inv(page)
    assert (now["Skills"]["multi"], now["School"]["multi"]) == (True, False)


def test_a_workday_search_explore_learns_single_or_several(page, load):
    load(page, fixture_html("workday_search.html"))
    f = inv(page)
    assert explore(page, f["Type to Add Skills"], "SQL").get("multi") is True
    assert explore(page, f["School or University"], "Arlington").get("multi") is False
    now = inv(page)
    assert (now["Type to Add Skills"]["multi"], now["School or University"]["multi"]) == (True, False)
    assert now["Type to Add Skills"]["committed"] == ["SQL"] and now["School or University"]["committed"] == ""


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


def test_a_search_set_keeps_existing_chips_and_reports_partial_honestly(page, load):
    load(page, fixture_html("workday_search.html"))
    f = inv(page)["Type to Add Skills"]
    row = apply(page, f, op="set", texts=["Python", "Rust"])
    assert row["outcome"] == "partial" and row["added"] == ["Python"] and row["missing"] == ["Rust"]
    assert row["committed"] == ["SQL", "Python"] and oracle(page, "skills") == ["SQL", "Python"]


# --- the search-and-pick sequence (notes §2): press, wait for the list, type,
# Enter, wait for the results to settle, click the row's radio or checkbox.
# Every click, key and focus the page hears, in order (`window.heard`), and
# which option rows were clicked and where (`window.rowClicks`).
LISTEN = """() => {
  window.heard = [];
  for (const type of ['mousedown', 'input', 'keydown', 'keyup']) {
    document.addEventListener(type, (e) => {
      if (e.target.id) window.heard.push(`${e.target.id}:${type}${e.key ? ':' + e.key : ''}`);
    }, true);
  }
  window.rowClicks = [];
  document.addEventListener('click', (e) => {
    const row = e.target.closest('[data-automation-id=activeListContainer] [role=option]');
    if (row) window.rowClicks.push({ text: row.textContent, on: e.target.matches('input') ? e.target.type : 'row',
                                     index: Number(row.dataset.index) });
  }, true);
}"""


def listen(page):
    page.evaluate(LISTEN)


@in_both_windows()
def test_search_presses_then_types_then_enters(window, request, load):
    page = request.getfixturevalue(window)
    load(page, fixture_html("workday_search.html"))
    listen(page)
    got = explore(page, inv(page)["How Did You Hear About Us?"], "LinkedIn")
    # Two identical leaves are one option (§2 "duplicates"); nothing committed.
    assert [o["text"] for o in got["options"]] == ["LinkedIn"] and "error" not in got
    assert oracle(page, "heard") == ""
    heard = [h for h in page.evaluate("window.heard") if h.startswith("heard:")]
    assert heard[0] == "heard:mousedown"
    typed, down, up = heard.index("heard:input"), heard.index("heard:keydown:Enter"), heard.index("heard:keyup:Enter")
    assert 0 < typed < down < up
    assert page.input_value("#heard") == "" and not list_shown(page)


@in_both_windows()
def test_identical_leaves_are_one_option_and_commit_the_first(window, request, load):
    page = request.getfixturevalue(window)
    load(page, fixture_html("workday_search.html"))
    listen(page)
    row = apply(page, inv(page)["How Did You Hear About Us?"], op="choose", text="LinkedIn")
    assert (row["outcome"], row["committed"]) == ("verified", "LinkedIn") and oracle(page, "heard") == "LinkedIn"
    assert page.evaluate("window.rowClicks") == [{"text": "LinkedIn", "on": "radio", "index": 0}]


def test_same_text_under_different_categories_is_ambiguous(page, load):
    load(page, fixture_html("adversarial_same_text.html"))
    listen(page)
    row = apply(page, inv(page)["Referral Source"], op="choose", text="Other")
    assert (row["outcome"], row["reason"]) == ("unexpected", "ambiguous")
    assert [o["text"] for o in row["options"]] == ["Other", "Other"]
    assert oracle(page, "referral") == "" and page.evaluate("window.rowClicks") == []
    assert not list_shown(page)


@in_both_windows()
def test_streamed_results_are_read_after_they_settle(window, request, load):
    """"Arlington" answers in two stages: first the wrong school alone, then
    all eight (§2 rule 4). Both the read and the pick wait for the list to
    settle; the school, once its rows said radio, is a one-answer field that
    holds its one pill."""
    page = request.getfixturevalue(window)
    load(page, fixture_html("workday_search.html"))
    listen(page)
    f = inv(page)["School or University"]
    got = explore(page, f, "Arlington")
    assert len(got["options"]) == 8 and "The University of Texas at Arlington" in [o["text"] for o in got["options"]]
    row = apply(page, f, op="choose", text="The University of Texas at Arlington", term="Arlington")
    assert (row["outcome"], row["committed"]) == ("verified", "The University of Texas at Arlington")
    assert oracle(page, "school") == "The University of Texas at Arlington"
    assert [c["text"] for c in page.evaluate("window.rowClicks")] == ["The University of Texas at Arlington"]
    now = inv(page)["School or University"]
    assert (now["multi"], now["committed"], now["answered"]) == (False, "The University of Texas at Arlington", True)


def test_a_single_hit_that_enter_committed_is_verified_not_clicked_again(page, load):
    load(page, fixture_html("workday_search.html"))
    listen(page)
    row = apply(page, inv(page)["School or University"], op="choose", text="University of Houston", term="Houston")
    # Its rows never showed (the Enter committed and closed the list): not
    # known to take one answer, it reads as the list of pills it holds.
    assert (row["outcome"], row["committed"]) == ("verified", ["University of Houston"])
    assert oracle(page, "school") == "University of Houston" and page.evaluate("window.rowClicks") == []


def skill_pills(page):
    return page.evaluate("""() => [...document.getElementById('skills').closest('[data-automation-id=multiSelectContainer]')
        .querySelectorAll('[data-automation-id=selectedItem] [data-automation-id=promptOption]')].map((p) => p.textContent)""")


@in_both_windows()
def test_virtualized_results_are_scrolled_to_the_option(window, request, load):
    """Exact "SQL" is #19 of 31 results and "Python" #16 of 17, with eight rows
    in the DOM (§2 rule 6): both are scrolled to and ticked; a skill that was
    already there is kept."""
    page = request.getfixturevalue(window)
    load(page, fixture_html("workday_search.html"), sources=[])
    # The page as it was before the Companion arrived: SQL removed, Tableau
    # added (trusted input, before the engine loads — after, it is the user's).
    page.click("[data-automation-id=formField-skills] [data-automation-id=DELETE_charm]")
    page.click("#skills")
    page.wait_for_selector("[data-automation-id=activeListContainer]")
    page.fill("#skills", "Tableau")
    page.keyboard.press("Enter")
    page.wait_for_function("JSON.stringify(window.__oracle.skills) === '[\"Tableau\"]'")
    page.mouse.click(1000, 800)
    page.fill("#skills", "")
    for src in ENGINE_SOURCES:
        page.add_script_tag(content=(EXTENSION / src).read_text(encoding="utf-8"))
    listen(page)
    row = apply(page, inv(page)["Type to Add Skills"], op="set", texts=["SQL", "Python"])
    assert (row["outcome"], row["added"]) == ("verified", ["SQL", "Python"])
    assert oracle(page, "skills") == ["Tableau", "SQL", "Python"] and skill_pills(page) == ["Tableau", "SQL", "Python"]
    assert [(c["text"], c["on"], c["index"]) for c in page.evaluate("window.rowClicks")] == [
        ("SQL", "checkbox", 18), ("Python", "checkbox", 15)]
    assert page.input_value("#skills") == "" and not list_shown(page)


def test_a_tick_is_never_repeated_before_the_redraw(page, load):
    """A tick is a toggle, and the row shows it only a frame later (§2 rule 8):
    exactly one click per item, the list kept open between items and each
    next term typed over the last query (no ×, no second press)."""
    load(page, fixture_html("workday_search.html"))
    listen(page)
    row = apply(page, inv(page)["Type to Add Skills"], op="set", texts=["Python", "Excel VBA"], terms=["Python", "Excel"])
    assert row["outcome"] == "verified" and oracle(page, "skills") == ["SQL", "Python", "Excel VBA"]
    assert [c["text"] for c in page.evaluate("window.rowClicks")] == ["Python", "Excel VBA"]
    heard = [h for h in page.evaluate("window.heard") if h.startswith("skills:")]
    assert heard.count("skills:mousedown") == 1 and heard.count("skills:keyup:Enter") == 2


def test_the_row_is_never_clicked_when_it_holds_a_checkable(page, load):
    load(page, fixture_html("workday_search.html"))
    listen(page)
    f = inv(page)
    assert apply(page, f["How Did You Hear About Us?"], op="choose", text="LinkedIn")["outcome"] == "verified"
    assert apply(page, f["School or University"], op="choose", text="Texas State University", term="Texas")["outcome"] == "verified"
    row = apply(page, f["Type to Add Skills"], op="set", texts=["Microsoft Excel"], terms=["Excel"])
    assert row["outcome"] == "verified"
    clicks = page.evaluate("window.rowClicks")
    assert [c["on"] for c in clicks] == ["radio", "radio", "checkbox"]
    assert (oracle(page, "heard"), oracle(page, "school")) == ("LinkedIn", "Texas State University")


# A combobox that searches only on Enter (its typing shows nothing), beside a
# plain text box inside a <form> and the Workday boxes.
ENTER_SEARCH = """<form><label for='nm'>Preferred name</label><input id='nm'></form>
<label for='cb'>Office</label><input id='cb' role='combobox' aria-autocomplete='list' aria-controls='cb-list'>
<ul id='cb-list' role='listbox' style='display:none'></ul>
<script>
(() => {
  const cb = document.getElementById('cb'); const list = document.getElementById('cb-list');
  cb.addEventListener('keyup', (e) => {
    if (e.key !== 'Enter') return;
    list.innerHTML = ['Austin', 'Boston'].filter((o) => o.toLowerCase().includes(cb.value.toLowerCase()))
      .map((o) => `<li role='option'>${o}</li>`).join('');
    for (const li of list.children) li.addEventListener('click', () => { cb.value = li.textContent; list.style.display = 'none'; });
    list.style.display = 'block';
  });
})();
</script>"""


def test_enter_is_only_sent_to_search_widgets(page, load):
    """The search's Enter goes to a Workday box and to a combobox whose typing
    showed nothing — never to a plain text box (in a form, an Enter may submit
    it), and never to a combobox that filtered as it was typed into."""
    load(page, ENTER_SEARCH + fixture_html("workday_search.html") + fixture_html("react_select.html").replace(
        'id="portal"', 'id="portal-rs"'))
    page.evaluate("""() => { window.enters = [];
      document.addEventListener('keydown', (e) => { if (e.key === 'Enter') window.enters.push(e.target.id); }, true); }""")
    f = inv(page)
    # Every op on the plain box: a write, and the choice ops it refuses.
    name = f["Preferred name"]
    assert apply(page, name, op="write", value="Sam")["outcome"] == "verified"
    assert explore(page, name, "Sam")["error"] == "not_a_choice"
    assert apply(page, name, op="choose", text="Sam", term="Sam")["reason"] == "not_a_choice"
    assert apply(page, name, op="set", texts=["Sam"])["reason"] == "not_a_set"
    s = page.evaluate(f"(r) => {OPS}.stepState(r)", {"fid": name["fid"], "fp": name["fp"], "value": "Sam"})
    assert [c["mid"] for c in s["candidates"]] == ["give_up"]
    assert apply(page, name, op="move", mid="search:value", version=s["version"])["reason"] == "not_offered"
    assert apply(page, name, op="move", mid="give_up", version=s["version"])["outcome"] == "closed"
    assert page.evaluate("window.enters") == []
    assert apply(page, f["Country"], op="choose", text="India", term="ind")["outcome"] == "verified"
    assert apply(page, f["Office"], op="choose", text="Boston", term="bos")["outcome"] == "verified"
    assert apply(page, f["School or University"], op="choose", text="Texas A&M University", term="Texas")["outcome"] == "verified"
    assert page.evaluate("window.enters") == ["cb", "school"]
    assert page.input_value("#nm") == "Sam" and page.input_value("#cb") == "Boston"


def staged(slow_ms=None, second_ms=None, declare=None, heard_ignores_enter=False, restless=False, highlight=False):
    """workday_search.html with its result stages moved (§2 rule 4); rows that
    declare a size (aria-setsize: the full result count, `declare="total"`,
    or only the rows of the stage drawn, `"stage"`); a How Did You Hear box
    whose Enter answers with the list it already shows; results that never
    stop reordering (`restless`); or the first row keyboard-highlighted
    (aria-selected="true", `highlight`)."""
    html = fixture_html("workday_search.html")
    edits = []
    if slow_ms is not None:
        edits.append(("const STAGE_1_MS = 150;", f"const STAGE_1_MS = {slow_ms};"))
    if second_ms is not None:
        edits.append(("const STAGE_2_MS = 400;", f"const STAGE_2_MS = {second_ms};"))
    if declare == "total":
        edits.append(("const token = open.token;", "const token = open.token; open.total = results.length;"))
    if declare:
        edits.append(("row.dataset.index = String(first + i);",
                      "row.dataset.index = String(first + i); row.setAttribute('aria-setsize', String(open.total ?? items.length));"))
    if heard_ignores_enter:
        edits.append(("if (query) search(id, query);", "if (query && id !== 'heard') search(id, query);"))
    if restless:
        edits.append(("      // A search with exactly one result commits it on its own (§2 rule 5).",
                      "      setInterval(() => { if (!live()) return; open.items = [...open.items].reverse(); render(); }, 200);\n"
                      "      // A search with exactly one result commits it on its own (§2 rule 5)."))
    if highlight:
        edits.append(('row.setAttribute("aria-selected", "false");', 'row.setAttribute("aria-selected", String(first + i === 0));'))
    for old, new in edits:
        assert old in html, old
        html = html.replace(old, new)
    return html


def test_slow_results_are_waited_for_not_read_as_the_empty_list(page, load):
    """School opens EMPTY; its answer starts 700 ms after the Enter — past the
    quiet period, so an unchanged list is never taken for the answer early."""
    load(page, staged(slow_ms=700, second_ms=950))
    f = inv(page)["School or University"]
    got = explore(page, f, "Arlington")
    assert len(got["options"]) == 8 and "error" not in got
    row = apply(page, f, op="choose", text="The University of Texas at Arlington", term="Arlington")
    assert (row["outcome"], oracle(page, "school")) == ("verified", "The University of Texas at Arlington")


def test_a_search_that_answers_with_the_list_it_showed_still_resolves(page, load):
    """A search may rightly answer with the default list: taken once the long
    bound has passed with nothing new, never before it."""
    load(page, staged(heard_ignores_enter=True))
    started = time.monotonic()
    got = explore(page, inv(page)["How Did You Hear About Us?"], "Job")
    assert [o["text"] for o in got["options"]] == ["Job Board", "Social Media"] and "error" not in got
    assert time.monotonic() - started >= 2.5


def test_a_list_that_declares_its_size_is_settled_when_it_holds_that_many(page, load):
    """The first stage (1 row) and the second (5) are over a second apart —
    past the quiet period; rows that declare aria-setsize=5 hold the wait: a
    declared size is a veto on settling early."""
    load(page, staged(second_ms=1200, declare="total"))
    got = explore(page, inv(page)["School or University"], "Texas")
    assert len(got["options"]) == 5


def test_a_stage_that_declares_only_its_own_rows_still_waits_for_quiet(page, load):
    """A declared size is never a shortcut: the first stage says aria-setsize=1
    for its one row, and the second stage still lands before it is taken."""
    load(page, staged(declare="stage"))
    got = explore(page, inv(page)["School or University"], "Texas")
    assert len(got["options"]) == 5


def test_a_no_items_row_that_declares_its_size_resolves(page, load):
    """"No Items." is a row (§2 rule 9) that is no option: counted the same way
    on both sides, it settles as an honest empty answer, not a dead end."""
    load(page, staged(declare="stage"))
    started = time.monotonic()
    got = explore(page, inv(page)["School or University"], "Arlignton")
    assert (got["options"], got["error"]) == ([], "empty_popup")
    assert time.monotonic() - started < 2.5


def test_a_list_that_never_settles_is_never_picked_from(page, load):
    """Results that keep reordering are still changing when time runs out:
    not taken — `unsettled`, nothing clicked, nothing left open."""
    load(page, staged(restless=True))
    listen(page)
    f = inv(page)["School or University"]
    assert explore(page, f, "Texas")["error"] == "unsettled"
    row = apply(page, f, op="choose", text="Texas A&M University", term="Texas")
    assert (row["outcome"], row["reason"]) == ("unexpected", "unsettled")
    assert page.evaluate("window.rowClicks") == [] and oracle(page, "school") == ""
    assert not list_shown(page) and page.input_value("#school") == ""


def test_a_keyboard_highlight_is_not_a_held_option(page, load):
    """Workday's aria-selected="true" is its keyboard highlight (§2): an
    unticked highlighted row is reported not selected and is still offered."""
    load(page, staged(highlight=True))
    f = inv(page)["Type to Add Skills"]
    got = explore(page, f, "Python")
    assert (got["options"][0]["text"], got["options"][0]["selected"]) == ("Python (Programming Language)", False)
    assert apply(page, f, op="move", mid="search:value", version=page.evaluate(
        f"(r) => {OPS}.stepState(r)", {"fid": f["fid"], "fp": f["fp"], "value": "Python"})["version"])["outcome"] == "progressed"
    s = page.evaluate(f"(r) => {OPS}.stepState(r)", {"fid": f["fid"], "fp": f["fp"], "value": "Python"})
    assert (s["options"][0]["text"], s["options"][0]["selected"]) == ("Python (Programming Language)", False)
    assert 'Click the option "Python (Programming Language)"' in [c["describe"] for c in s["candidates"]]


# Options that ignore the first click; after it, every redraw puts a radio in
# each row — so a choose's second attempt meets a row with a tick and no
# second gesture.
GROWS_A_TICK = """<label for='pk'>Pick</label><input id='pk' role='combobox' aria-autocomplete='list' aria-controls='pk-list'>
<ul id='pk-list' role='listbox' style='display:none'></ul>
<script>
(() => {
  const input = document.getElementById('pk'); const list = document.getElementById('pk-list');
  let clicked = 0;
  input.addEventListener('input', () => {
    const q = input.value.toLowerCase();
    list.innerHTML = q ? ['Alpha', 'Beta'].filter((o) => o.toLowerCase().includes(q))
      .map((o) => `<li role='option'>${clicked ? "<input type='radio'>" : ''}${o}</li>`).join('') : '';
    for (const li of list.children) li.addEventListener('click', () => { clicked += 1; });
    list.style.display = list.children.length ? 'block' : 'none';
  });
  document.addEventListener('mousedown', (e) => { if (e.target !== input && !list.contains(e.target)) list.style.display = 'none'; });
})();
</script>"""


def test_a_retry_that_meets_a_row_with_a_tick_ends_without_a_second_gesture(page, load):
    load(page, GROWS_A_TICK)
    row = apply(page, inv(page)["Pick"], op="choose", text="Alpha", term="Al")
    assert (row["outcome"], row["reason"]) == ("unexpected", "not_committed")


def test_no_search_enter_while_the_box_names_a_highlighted_option(page, load):
    """aria-activedescendant on the box: an Enter would pick that option."""
    load(page, ENTER_SEARCH)
    page.evaluate("""() => { window.enters = []; document.getElementById('cb').setAttribute('aria-activedescendant', 'x');
      document.addEventListener('keydown', (e) => { if (e.key === 'Enter') window.enters.push(e.target.id); }, true); }""")
    row = apply(page, inv(page)["Office"], op="choose", text="Boston", term="bos")
    assert row["outcome"] == "unexpected" and page.evaluate("window.enters") == []


def test_a_workday_box_naming_a_highlighted_row_still_gets_its_search_enter(page, load):
    """Workday's Enter SEARCHES, it does not pick: a Workday box that names its
    list's keyboard highlight (aria-activedescendant) still gets the Enter."""
    load(page, fixture_html("workday_search.html"))
    listen(page)
    page.evaluate("""() => { const school = document.getElementById('school');
      school.addEventListener('mousedown', () => school.setAttribute('aria-activedescendant', 'hl-row')); }""")
    got = explore(page, inv(page)["School or University"], "Arlington")
    assert len(got["options"]) == 8 and "error" not in got
    assert [h for h in page.evaluate("window.heard") if h == "school:keyup:Enter"] == ["school:keyup:Enter"]


def test_the_same_query_over_the_list_it_settled_is_not_searched_again(page, load):
    """A second search:value for the same term, over the list the first one
    settled: nothing typed, no Enter, no wait for a list that cannot change."""
    load(page, fixture_html("workday_search.html"))
    listen(page)
    f = inv(page)["School or University"]

    def step():
        return page.evaluate(f"(r) => {OPS}.stepState(r)", {"fid": f["fid"], "fp": f["fp"], "value": "Texas"})

    assert apply(page, f, op="move", mid="search:value", version=step()["version"])["outcome"] == "progressed"
    started = time.monotonic()
    assert apply(page, f, op="move", mid="search:value", version=step()["version"])["outcome"] == "progressed"
    assert time.monotonic() - started < 0.4
    assert [h for h in page.evaluate("window.heard") if h == "school:keyup:Enter"] == ["school:keyup:Enter"]


# A combobox that opens its list on FOCUS and toggles it on a press (MUI-style
# Autocomplete): pressing after the focus would shut the list, and typing
# filters only an open list. `window.presses` counts presses on the box.
OPEN_ON_FOCUS = """<label for='mui'>Team</label><div class='ac-root'><input id='mui' role='combobox'
  aria-autocomplete='list' aria-expanded='false' aria-controls='mui-list'></div>
<ul id='mui-list' role='listbox' style='display:none'></ul>
<script>
(() => {
  const input = document.getElementById('mui'); const list = document.getElementById('mui-list');
  window.presses = 0;
  const OPTIONS = ['Red', 'Blue', 'Green'];
  const shown = () => list.style.display !== 'none';
  const render = () => {
    const q = input.value.toLowerCase();
    list.innerHTML = OPTIONS.filter((o) => o.toLowerCase().includes(q)).map((o) => `<li role='option'>${o}</li>`).join('');
    for (const li of list.children) li.addEventListener('click', () => { input.value = li.textContent; hide(); });
  };
  const show = () => { render(); list.style.display = 'block'; input.setAttribute('aria-expanded', 'true'); };
  const hide = () => { list.style.display = 'none'; input.setAttribute('aria-expanded', 'false'); };
  input.addEventListener('focus', show);
  input.addEventListener('mousedown', () => { window.presses += 1; if (shown()) hide(); else show(); });
  input.addEventListener('input', () => { if (shown()) render(); });
})();
</script>"""


@in_both_windows()
def test_a_list_that_opens_on_focus_is_not_pressed_shut(window, request, load):
    page = request.getfixturevalue(window)
    load(page, OPEN_ON_FOCUS)
    row = apply(page, inv(page)["Team"], op="choose", text="Blue", term="Bl")
    assert (row["outcome"], row["committed"]) == ("verified", "Blue")
    assert page.evaluate("window.presses") == 0


def test_explore_never_runs_past_the_field_clock(page, load):
    """The loop sends what the field's clock has left (`ms`): an explore that
    would outlive it times out, and leaves nothing open or typed."""
    load(page, fixture_html("workday_search.html"))
    f = inv(page)["School or University"]
    got = page.evaluate(f"(r) => {OPS}.explore([r])", {"fid": f["fid"], "fp": f["fp"], "term": "Arlington", "ms": 200})
    assert got[f["fid"]]["error"] == "timeout"
    page.wait_for_timeout(600)
    assert page.input_value("#school") == "" and not list_shown(page) and oracle(page, "school") == ""


def test_an_empty_popup_that_needs_a_search_is_unexpected_not_failed(page, load):
    load(page, fixture_html("popup_with_search.html"))
    got = explore(page, inv(page)["Field of study"])
    assert got["options"] == [] and got["searchable"] is True and got["error"] == "empty_popup"


# --- exploring can commit (notes §2 rule 5): what it commits is taken back
def pill_texts(page, input_id):
    return page.evaluate("(id) => [...document.getElementById(id).closest('.q').querySelectorAll('.multi-value__label')]"
                         ".map((p) => p.textContent)", input_id)


def test_explore_undoes_a_single_hit_the_search_committed(page, load):
    load(page, SINGLE_HIT_SEARCH)
    got = explore(page, inv(page)["Field of study"], "Analytics")
    assert [o["text"] for o in got["options"]] == ["Analytics"] and "error" not in got
    assert oracle(page, "field_of_study") == "" and pill_texts(page, "fos") == []
    assert page.input_value("#fos") == ""


def test_explore_reports_a_commit_it_could_not_undo(page, load):
    """Minor's pill has no remove control and ignores a click: the field is
    reported with what the explore left, never explored as if nothing happened."""
    load(page, SINGLE_HIT_SEARCH)
    got = explore(page, inv(page)["Minor"], "Analytics")
    assert (got["error"], got["committed"]) == ("committed_while_exploring", "Analytics")
    assert oracle(page, "minor") == "Analytics"


def test_explore_takes_back_a_popup_pick_the_page_made_on_close(page, load):
    """A popup that picks its highlighted row when its list closes: explore's
    close committed "Yes"; the engine's own undo (choose the placeholder,
    `undo: true`) empties it again — though the placeholder row is never
    among the options explore returns."""
    load(page, SELECT_ON_CLOSE)
    got = explore(page, inv(page)["Willing to move?"])
    assert [o["text"] for o in got["options"]] == ["Yes", "No"] and "error" not in got
    assert oracle(page, "move") == "" and page.inner_text("#move") == "Select One"


def test_the_undo_has_its_own_budget_after_a_slow_explore(page, load):
    """The popup reopens slowly for the undo: an explore budget that the
    explore alone fits in does not cut the undo short."""
    load(page, SELECT_ON_CLOSE)
    page.evaluate(f"() => {{ {OPS}.budgets.explore = 1200; window.slowReopen = 1500; }}")
    got = explore(page, inv(page)["Willing to move?"])
    assert "error" not in got and oracle(page, "move") == ""


def test_an_undo_that_times_out_still_reports_the_commit(page, load):
    load(page, SELECT_ON_CLOSE)
    page.evaluate(f"() => {{ {OPS}.budgets.undo = 300; window.slowReopen = 1500; }}")
    got = explore(page, inv(page)["Willing to move?"])
    assert (got["error"], got["committed"]) == ("committed_while_exploring", "Yes")
    assert oracle(page, "move") == "Yes"


def test_explore_undoes_a_pick_that_enter_committed(page, load):
    load(page, fixture_html("workday_search.html"))
    got = explore(page, inv(page)["School or University"], "Houston")
    assert [o["text"] for o in got["options"]] == ["University of Houston"] and "error" not in got
    assert oracle(page, "school") == "" and oracle(page, "skills") == ["SQL"]
    assert page.evaluate("""() => document.querySelector('[data-automation-id="formField-school"]')
        .querySelectorAll('[data-automation-id="selectedItem"]').length""") == 0


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


# A press appends a ROLE-LESS list with its first row highlighted; an Enter
# on the button would accept it. `__oracle.team` is what the fake app holds.
# A second button ignores the press and ArrowDown, and an Enter commits "Yes"
# with no list at all; nothing gives it back.
ENTER_PICKS = """<label id='l'>Team</label>
<div><button id='team' aria-haspopup='listbox' aria-labelledby='l'>Select One</button><input type='hidden' value=''></div>
<label id='m'>Relocate?</label>
<div><button id='blind' aria-haspopup='listbox' aria-labelledby='m'>Select One</button><input type='hidden' value=''></div>
<script>
(() => {
  const oracle = (window.__oracle = window.__oracle || {});
  oracle.team = ""; oracle.blind = "";
  const team = document.getElementById('team');
  window.teamKeys = [];
  team.addEventListener('keydown', (e) => window.teamKeys.push(e.key));
  team.addEventListener('click', () => {
    if (document.querySelector('.rows')) return;
    const rows = document.createElement('div');
    rows.className = 'rows'; rows.innerHTML = "<div class='hl'>Red</div><div>Blue</div>";
    document.body.append(rows);
  });
  team.addEventListener('keydown', (e) => {
    const hl = document.querySelector('.rows .hl');
    if (e.key !== 'Enter' || !hl) return;
    team.textContent = hl.textContent; team.nextElementSibling.value = hl.textContent; oracle.team = hl.textContent;
  });
  const blind = document.getElementById('blind');
  blind.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    blind.textContent = 'Yes'; blind.nextElementSibling.value = 'Yes'; oracle.blind = 'Yes';
  });
})();
</script>"""


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
