"""The adaptive step (fill-core stepState/move through fill-ops), in real
Chromium: the field's state now, the moves code allows, and one move at a time
against the state it was chosen from."""

import pytest

from tests.browser.conftest import fixture_html
from tests.browser.pages import CATEGORY_POPUP, POLICY_PAGE, list_shown, oracle

OPS = "window.careerStudioCompanion.fillOps"
MOVE_KINDS = {"click", "search", "open", "scroll", "give_up"}


def inv(page, **opts):
    return {f["question"]: f for f in page.evaluate(f"async (o) => (await {OPS}.inventory(o)).fields", opts)}


def state(page, f, value):
    return page.evaluate(f"(r) => {OPS}.stepState(r)", {"fid": f["fid"], "fp": f["fp"], "value": value})


def move(page, f, mid, value, version=None, **extra):
    if version is None:
        version = state(page, f, value)["version"]
    return page.evaluate(f"(a) => {OPS}.apply([a])", {"fid": f["fid"], "fp": f["fp"], "op": "move", "mid": mid,
                                                        "value": value, "version": version, **extra})[0]


def mids(s):
    return [c["mid"] for c in s["candidates"]]


def test_a_category_continues_from_its_children_to_the_leaf(page, load):
    load(page, CATEGORY_POPUP)
    f = inv(page)["How did you hear about us?"]
    first = page.evaluate(f"(a) => {OPS}.apply([a])", {"fid": f["fid"], "fp": f["fp"], "op": "choose", "text": "Job Board"})[0]
    assert first["reason"] == "new_options"
    s = state(page, f, "LinkedIn")
    assert [c["describe"] for c in s["candidates"] if c["mid"].startswith("click:")] == [
        'Click the option "LinkedIn"', 'Click the option "Indeed"']
    row = move(page, f, "click:o1", "LinkedIn")
    assert (row["outcome"], row["committed"]) == ("verified", "LinkedIn")
    assert "text" not in row
    assert not list_shown(page)


def test_a_placeholder_row_is_never_clicked_as_an_answer(page, load):
    load(page, fixture_html("workday_listbox.html"))
    f = inv(page)["Degree"]
    assert move(page, f, "open", "Masters")["outcome"] == "progressed"
    s = state(page, f, "Masters")
    mid = next(c["mid"] for c in s["candidates"] if c["describe"] == 'Click the option "Select One"')
    row = move(page, f, mid, "Masters", version=s["version"])
    assert (row["outcome"], row["reason"]) == ("unexpected", "placeholder")
    assert oracle(page, "degree") == "" and page.inner_text("#degree") == "Select One"


def test_a_popup_that_needs_a_search_is_opened_searched_and_picked(page, load):
    load(page, fixture_html("popup_with_search.html"))
    f = inv(page)["Field of study"]
    assert mids(state(page, f, "Information Systems"))[:1] == ["open"]
    assert move(page, f, "open", "Information Systems")["outcome"] == "progressed"
    s = state(page, f, "Information Systems")
    assert "search:value" in mids(s) and 'Type "Systems" into the search box' in [c["describe"] for c in s["candidates"]]
    assert move(page, f, "search:word:1", "Information Systems")["outcome"] == "progressed"
    s = state(page, f, "Information Systems")
    click = next(c["mid"] for c in s["candidates"] if c["describe"] == 'Click the option "Information Systems"')
    assert move(page, f, click, "Information Systems")["outcome"] == "verified"
    assert page.inner_text("#fos") == "Information Systems"


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="Task 5: search moves press, type, Enter (key-up) and settle; the click "
                          "move ticks the row's radio")
def test_a_search_field_types_into_its_own_box_and_takes_the_query_back(page, load):
    load(page, fixture_html("workday_search.html"))
    f = inv(page)["School or University"]
    school = "The University of Texas at Arlington"
    s = state(page, f, school)
    assert [c["describe"] for c in s["candidates"] if c["mid"].startswith("search:word:")] == [
        'Type "The" into the search box', 'Type "University" into the search box',
        'Type "Texas" into the search box', 'Type "Arlington" into the search box']
    assert move(page, f, "search:word:3", school)["outcome"] == "progressed"
    s = state(page, f, school)
    assert s["popupOpen"] is True and s["complete"] is False
    click = next(c["mid"] for c in s["candidates"] if c["describe"] == f'Click the option "{school}"')
    row = move(page, f, click, school)
    assert (row["outcome"], row["committed"]) == ("verified", school) and oracle(page, "school") == school
    assert page.input_value("#school") == "" and not list_shown(page)


def test_give_up_closes_everything(page, load):
    load(page, CATEGORY_POPUP)
    f = inv(page)["How did you hear about us?"]
    move(page, f, "open", "x")
    assert move(page, f, "give_up", "x")["outcome"] == "closed"
    assert not list_shown(page)


def test_give_up_takes_back_a_query_the_engine_typed(page, load):
    load(page, fixture_html("workday_search.html"))
    f = inv(page)["School or University"]
    move(page, f, "search:value", "Texas")
    assert move(page, f, "give_up", "Texas")["outcome"] == "closed"
    assert page.input_value("#school") == "" and not list_shown(page)


def test_a_state_is_consumed_by_one_move_and_a_changed_list_is_stale(page, load):
    load(page, CATEGORY_POPUP)
    f = inv(page)["How did you hear about us?"]
    move(page, f, "open", "LinkedIn")
    v = state(page, f, "LinkedIn")["version"]
    assert move(page, f, "click:o1", "LinkedIn", version=v)["outcome"] == "progressed"   # Job Board → children
    assert move(page, f, "click:o1", "LinkedIn", version=v)["outcome"] == "stale"        # consumed


def test_a_click_on_a_list_that_changed_since_the_state_is_stale(page, load):
    load(page, CATEGORY_POPUP)
    f = inv(page)["How did you hear about us?"]
    move(page, f, "open", "LinkedIn")
    v = state(page, f, "LinkedIn")["version"]
    # The page re-renders its list under the decision.
    page.evaluate("document.querySelector('#portal li').textContent = 'Recruiter'")
    assert move(page, f, "click:o1", "LinkedIn", version=v)["outcome"] == "stale"
    assert page.inner_text("#heard") == "Select One"


def test_a_filtered_search_view_is_never_complete(page, load):
    load(page, fixture_html("popup_with_search.html"))
    f = inv(page)["Field of study"]
    move(page, f, "open", "Information Systems")
    move(page, f, "search:value", "Information Systems")
    assert state(page, f, "Information Systems")["complete"] is False


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="Task 6: the live popup lists its 'Select One' placeholder as an option; "
                          "it must not be offered as an answer")
def test_an_unfiltered_short_list_is_complete(page, load):
    load(page, fixture_html("workday_listbox.html"))
    f = inv(page)["Are you legally authorized to work in the United States?"]
    assert state(page, f, "Yes")["complete"] is False  # nothing in view yet
    move(page, f, "open", "Yes")
    s = state(page, f, "Yes")
    assert s["complete"] is True and s["popupOpen"] is True
    assert [o["text"] for o in s["options"]] == ["Yes", "No"]


def test_a_move_chosen_from_an_older_state_is_stale(page, load):
    load(page, fixture_html("workday_listbox.html"))
    f = inv(page)["Are you legally authorized to work in the United States?"]
    old = state(page, f, "Yes")["version"]
    move(page, f, "open", "Yes")
    assert move(page, f, "click:o1", "Yes", version=old)["outcome"] == "stale"


def test_a_move_the_state_did_not_offer_is_refused(page, load):
    load(page, fixture_html("workday_listbox.html"))
    f = inv(page)["Are you legally authorized to work in the United States?"]
    v = state(page, f, "Yes")["version"]  # no popup: no click is offered
    row = move(page, f, "click:o1", "Yes", version=v)
    assert (row["outcome"], row["reason"]) == ("unexpected", "not_offered")
    assert page.inner_text("#auth") == "Select One"


def test_candidates_are_ids_code_generated_and_capped(page, load):
    load(page, fixture_html("workday_listbox.html"))
    f = inv(page)["Are you legally authorized to work in the United States?"]
    move(page, f, "open", "Yes")
    s = state(page, f, "Yes")
    assert all(c["mid"].split(":")[0] in MOVE_KINDS for c in s["candidates"])
    assert len(s["candidates"]) <= 60 and s["candidates"][-1]["mid"] == "give_up"
    assert "close" not in mids(s)  # give_up closes; close stays a cleanup move only
    assert move(page, f, "close", "Yes")["outcome"] == "closed" and not list_shown(page)


LONG_LIST = """<label id='l'>Country</label>
<button id='c' aria-haspopup='listbox' aria-labelledby='l'>Select One</button>
<div id='portal'></div>
<script>
(() => {
  const btn = document.getElementById('c'), portal = document.getElementById('portal');
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    portal.innerHTML = "<ul role='listbox' style='max-height:80px;overflow:auto;margin:0'>"
      + Array.from({ length: 70 }, (_, i) => `<li role='option' style='height:20px'>Country ${i + 1}</li>`).join('') + "</ul>";
  });
  document.addEventListener('click', () => { portal.innerHTML = ''; });
})();
</script>"""


def test_a_long_list_is_offered_a_window_at_a_time_down_to_its_last_option(page, load):
    load(page, LONG_LIST)
    f = inv(page)["Country"]
    move(page, f, "open", "Country 70")
    for _ in range(6):
        s = state(page, f, "Country 70")
        if 'Click the option "Country 70"' in [c["describe"] for c in s["candidates"]]:
            break
        assert "scroll" in mids(s)
        assert move(page, f, "scroll", "Country 70", version=s["version"])["outcome"] == "progressed"
    else:
        raise AssertionError("Country 70 was never offered")
    clicks = [c for c in s["candidates"] if c["mid"].startswith("click:")]
    # Still capped, and oids still number the FULL list.
    assert len(clicks) == 50 and clicks[-1]["mid"] == "click:o70"
    assert "scroll" not in mids(s) and s["complete"] is False
    assert [o["text"] for o in s["options"]][-1] == "Country 70"
    # A scroll chosen on an older view of a list the page has since scrolled
    # to its end moves nothing.
    load(page, LONG_LIST)
    f = inv(page)["Country"]
    move(page, f, "open", "x")
    v = state(page, f, "x")["version"]
    page.evaluate("(() => { const u = document.querySelector('#portal ul'); u.scrollTop = u.scrollHeight; })()")
    row = move(page, f, "scroll", "x", version=v)
    assert (row["outcome"], row["reason"]) == ("unexpected", "list_end")


def test_a_long_list_is_capped_scrollable_and_never_complete(page, load):
    load(page, LONG_LIST)
    f = inv(page)["Country"]
    move(page, f, "open", "Country 70")
    s = state(page, f, "Country 70")
    clicks = [m for m in mids(s) if m.startswith("click:")]
    assert len(clicks) == 50 and len(s["candidates"]) <= 60
    assert "scroll" in mids(s) and s["complete"] is False
    assert move(page, f, "scroll", "Country 70")["outcome"] == "progressed"
    assert page.evaluate("document.querySelector('#portal ul').scrollTop") > 0


def test_a_policy_blocked_option_is_never_a_click_move(page, load):
    load(page, POLICY_PAGE)
    f = inv(page)["Where did you find us?"]
    move(page, f, "open", "x")
    s = state(page, f, "x")
    assert [c["describe"] for c in s["candidates"] if c["mid"].startswith("click:")] == ['Click the option "Website"']
    assert [(o["text"], o["policyBlocked"]) for o in s["options"]] == [
        ("Website", False), ("I consent to the terms of use", True)]
    row = move(page, f, "click:o2", "x")
    assert (row["outcome"], row["reason"]) == ("unexpected", "not_offered")
    assert page.inner_text("#src") == "Select One"


def test_standing_consent_offers_consent_options(page, load):
    load(page, POLICY_PAGE)
    f = inv(page, consentForms=True)["Where did you find us?"]
    move(page, f, "open", "x")
    assert "click:o2" in mids(state(page, f, "x"))


def test_another_field_closes_a_popup_a_move_left_open(page, load):
    load(page, CATEGORY_POPUP)
    fields = inv(page)
    move(page, fields["How did you hear about us?"], "open", "x")
    assert list_shown(page)
    row = page.evaluate(f"(a) => {OPS}.apply([a])", {
        "fid": fields["Are you legally authorized to work in the United States?"]["fid"],
        "fp": fields["Are you legally authorized to work in the United States?"]["fp"], "op": "choose", "text": "No"})[0]
    assert row["outcome"] == "verified" and page.inner_text("#heard") == "Select One"


def test_stop_closes_a_popup_a_move_opened(page, load):
    load(page, CATEGORY_POPUP)
    f = inv(page)["How did you hear about us?"]
    move(page, f, "open", "x")
    page.evaluate(f"() => {OPS}.cancel()")
    page.wait_for_timeout(400)
    assert not list_shown(page)
    assert move(page, f, "open", "x", version=0)["outcome"] == "cancelled"


def test_a_step_on_a_stale_fingerprint_or_another_frame_is_refused(page, load):
    load(page, CATEGORY_POPUP)
    f = inv(page)["How did you hear about us?"]
    assert page.evaluate(f"(r) => {OPS}.stepState(r)", {"fid": f["fid"], "fp": "other", "value": "x"}) == {
        "error": "stale", "version": None, "candidates": []}
    assert page.evaluate(f"(r) => {OPS}.stepState(r)", {"fid": "zzzzzz-1", "fp": "p", "value": "x"}) is None
    row = page.evaluate(f"(a) => {OPS}.apply([a])", {"fid": f["fid"], "fp": "other", "op": "move", "mid": "open",
                                                      "value": "x", "version": 1})[0]
    assert row["outcome"] == "stale"


def test_a_passive_field_offers_only_give_up(page, load):
    load(page, fixture_html("native.html"))
    s = state(page, inv(page)["Highest degree"], "Master's")
    assert mids(s) == ["give_up"] and s["popupOpen"] is False


SILENT_SEARCH = """<label id='l'>City</label>
<input id='city' role='combobox' aria-autocomplete='list' aria-labelledby='l'>"""


def test_a_search_that_opens_nothing_takes_its_query_back(page, load):
    load(page, SILENT_SEARCH)
    f = inv(page)["City"]
    row = move(page, f, "search:value", "Austin")
    assert (row["outcome"], row["reason"]) == ("unexpected", "no_popup")
    assert page.input_value("#city") == ""


GROUPS = """<label id='l'>How did you hear about us?</label>
<button id='h' aria-haspopup='listbox' aria-labelledby='l'>Select One</button>
<div id='portal'></div>
<script>
(() => {
  const btn = document.getElementById('h'), portal = document.getElementById('portal');
  const render = (html) => { portal.innerHTML = "<ul role='listbox'>" + html + "</ul>"; };
  const top = () => render("<li role='option' aria-expanded='false' id='jb'>Job Board</li>"
    + "<li role='option' aria-haspopup='true' id='ref'>Referral</li><li role='option' id='q'>Say \\"hi\\"</li>");
  btn.addEventListener('click', (e) => { e.stopPropagation(); top(); });
  portal.addEventListener('click', (e) => {
    e.stopPropagation();
    const li = e.target.closest('li');
    if (!li) return;
    if (li.id === 'jb') render("<li role='option'>LinkedIn</li><li role='option'>Indeed</li>");
    else { btn.textContent = li.textContent; portal.innerHTML = ''; }  // Referral: a "group" that commits
  });
  document.addEventListener('click', () => { portal.innerHTML = ''; });
})();
</script>"""


def test_group_options_are_described_as_groups_and_open_to_their_children(page, load):
    load(page, GROUPS)
    f = inv(page)["How did you hear about us?"]
    move(page, f, "open", "LinkedIn")
    s = state(page, f, "LinkedIn")
    assert [c["describe"] for c in s["candidates"] if c["mid"].startswith("click:")] == [
        'Open the group "Job Board"', 'Open the group "Referral"', 'Click the option "Say \\"hi\\""']
    assert move(page, f, "click:o1", "LinkedIn")["outcome"] == "progressed"
    assert move(page, f, "click:o1", "LinkedIn")["outcome"] == "verified"
    assert page.inner_text("#h") == "LinkedIn"


def test_a_group_that_commits_a_value_is_never_verified(page, load):
    load(page, GROUPS)
    f = inv(page)["How did you hear about us?"]
    move(page, f, "open", "LinkedIn")
    row = move(page, f, "click:o2", "LinkedIn")
    assert (row["outcome"], row["reason"]) == ("unexpected", "group_committed")
    assert not list_shown(page)


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="Task 5: a search move presses Enter and reads a virtualized list "
                          "(\"SQL\" is #19 of 31) by scrolling it")
def test_chips_a_multi_widget_already_holds_are_never_click_moves(page, load):
    load(page, fixture_html("workday_search.html"))
    f = inv(page)["Type to Add Skills"]
    assert move(page, f, "search:value", "SQL")["outcome"] == "progressed"
    for _ in range(6):
        s = state(page, f, "SQL")
        if "SQL" in [o["text"] for o in s["options"]] or "scroll" not in mids(s):
            break
        move(page, f, "scroll", "SQL", version=s["version"])
    assert "SQL" in [o["text"] for o in s["options"]]
    assert 'Click the option "SQL"' not in [c["describe"] for c in s["candidates"]]
    assert oracle(page, "skills") == ["SQL"]


def test_a_click_the_widget_ignores_has_no_effect(page, load):
    """Both click gestures changed nothing — not the value, not the list, not
    the box: the move says so (no_effect), which the loop counts toward
    "doesn't accept automated input"."""
    load(page, fixture_html("react_select.html"))
    f = inv(page)["Country"]
    page.evaluate("window.rejectClicks = true")
    assert move(page, f, "search:value", "India")["outcome"] == "progressed"
    row = move(page, f, "click:o1", "India")
    assert (row["outcome"], row["reason"], row["committed"]) == ("unexpected", "no_effect", "")


def test_a_menu_the_widget_re_renders_is_found_again_and_still_closed(page, load):
    load(page, fixture_html("react_select.html"))
    f = inv(page)["Country"]
    assert move(page, f, "open", "India")["outcome"] == "progressed"
    first = page.evaluate("document.getElementById('country-menu') !== null")
    page.evaluate("document.getElementById('menu-root').innerHTML = document.getElementById('menu-root').innerHTML")
    s = state(page, f, "India")  # the menu node was swapped under the held popup
    assert first and s["popupOpen"] is True and "click:o3" in mids(s)
    page.evaluate("document.getElementById('menu-root').innerHTML = document.getElementById('menu-root').innerHTML")
    assert move(page, f, "give_up", "India")["outcome"] == "closed"
    assert page.evaluate("document.getElementById('menu-root').innerHTML") == ""


def test_an_unmarked_category_is_clicked_as_progress_then_its_leaf_as_the_answer(page, load):
    """Workday: "Job Board" carries no ARIA marker; it is clicked as an answer."""
    load(page, CATEGORY_POPUP)
    f = inv(page)["How did you hear about us?"]
    assert move(page, f, "open", "LinkedIn")["outcome"] == "progressed"
    s = state(page, f, "LinkedIn")
    assert [c["describe"] for c in s["candidates"] if c["mid"].startswith("click:")] == [
        'Click the option "Job Board"', 'Click the option "Social Media"', 'Click the option "Employee Referral"']
    # /step judges it an answer click (complete view); the page reports the
    # children it revealed.
    assert move(page, f, "click:o1", "LinkedIn")["outcome"] == "progressed"
    s = state(page, f, "LinkedIn")
    assert [o["text"] for o in s["options"]] == ["LinkedIn", "Indeed"]
    row = move(page, f, "click:o1", "LinkedIn")
    assert (row["outcome"], row["committed"]) == ("verified", "LinkedIn")


def test_a_plain_option_sent_as_progress_is_refused_without_a_click(page, load):
    load(page, CATEGORY_POPUP)
    f = inv(page)["How did you hear about us?"]
    move(page, f, "open", "LinkedIn")
    row = move(page, f, "click:o3", "LinkedIn", **{"as": "progress"})  # "Employee Referral" is a leaf
    assert (row["outcome"], row["reason"], row["committed"]) == ("unexpected", "not_a_group", "")
    assert page.inner_text("#heard") == "Select One"


def test_a_group_sent_as_progress_that_commits_is_never_verified(page, load):
    load(page, GROUPS)
    f = inv(page)["How did you hear about us?"]
    move(page, f, "open", "LinkedIn")
    row = move(page, f, "click:o2", "LinkedIn", **{"as": "progress"})  # "Referral": marked, but commits
    assert (row["outcome"], row["reason"], row["committed"]) == ("unexpected", "group_committed", "Referral")
