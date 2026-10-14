"""The generic fill mechanics (fill-core.js) through the page operations
(fill-ops.js), in real Chromium against the committed fixtures: text and date
boxes, native selects, and Workday-style popups with their committed evidence."""

import pytest

from tests.browser.conftest import fixture_html
from tests.browser.pages import (
    OPS,
    apply,
    explore,
    in_both_windows,
    inv,
    list_shown,
    oracle,
)


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


TWO_INVALID = ("<label for='a'>First</label><input id='a' value='x' aria-invalid='true'>"
               "<label for='b'>Second</label><input id='b' value='y' aria-invalid='true'>")


def test_a_sweep_given_fids_recommits_only_those(page, load):
    load(page, TWO_INVALID)
    fields = inv(page)
    assert [r["fid"] for r in page.evaluate(f"(fids) => {OPS}.sweep(fids)", [fields["First"]["fid"]])] == [fields["First"]["fid"]]
    assert sorted(r["fid"] for r in page.evaluate(f"() => {OPS}.sweep()")) == sorted(f["fid"] for f in fields.values())


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
    assert oracle(page, "degree") == "Masters"
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
    assert apply(page, f, op="choose", text="Masters")["outcome"] == "verified" and oracle(page, "degree") == "Masters"
    page.evaluate("() => { document.getElementById('degree').parentElement.querySelector('.hidden-backing').value = ''; }")
    assert {r["fid"]: r["outcome"] for r in page.evaluate(f"() => {OPS}.sweep()")}[f["fid"]] == "reverted"
