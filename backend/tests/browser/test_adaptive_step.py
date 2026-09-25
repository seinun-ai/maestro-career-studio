"""The adaptive step (fill-core stepState/move through fill-ops), in real
Chromium: the field's state now, the moves code allows, and one move at a time
against the state it was chosen from."""

from tests.browser.conftest import fixture_html
from tests.browser.test_fill_core import POLICY_PAGE

OPS = "window.careerStudioCompanion.fillOps"
MOVE_KINDS = {"click", "search", "open", "scroll", "close", "give_up"}


def inv(page, **opts):
    return {f["question"]: f for f in page.evaluate(f"async (o) => (await {OPS}.inventory(o)).fields", opts)}


def state(page, f, value):
    return page.evaluate(f"(r) => {OPS}.stepState(r)", {"fid": f["fid"], "fp": f["fp"], "value": value})


def move(page, f, mid, value, version=None):
    if version is None:
        version = state(page, f, value)["version"]
    return page.evaluate(f"(a) => {OPS}.apply([a])", {"fid": f["fid"], "fp": f["fp"], "op": "move", "mid": mid,
                                                        "value": value, "version": version})[0]


def mids(s):
    return [c["mid"] for c in s["candidates"]]


def portal_empty(page):
    return page.evaluate("document.getElementById('portal').children.length") == 0


def test_a_category_continues_from_its_children_to_the_leaf(page, load):
    load(page, fixture_html("workday_listbox.html"))
    f = inv(page)["How did you hear about us?"]
    first = page.evaluate(f"(a) => {OPS}.apply([a])", {"fid": f["fid"], "fp": f["fp"], "op": "choose", "text": "Job Board"})[0]
    assert first["reason"] == "new_options"
    s = state(page, f, "LinkedIn")
    assert [c["describe"] for c in s["candidates"] if c["mid"].startswith("click:")] == [
        'Click the option "LinkedIn"', 'Click the option "Indeed"']
    row = move(page, f, "click:o1", "LinkedIn")
    assert (row["outcome"], row["committed"]) == ("verified", "LinkedIn")
    assert "text" not in row
    assert portal_empty(page)


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


def test_a_search_field_types_into_its_own_box_and_takes_the_query_back(page, load):
    load(page, fixture_html("workday_search.html"))
    f = inv(page)["School or University"]
    s = state(page, f, "University of Texas at Dallas")
    assert [c["describe"] for c in s["candidates"] if c["mid"].startswith("search:word:")] == [
        'Type "University" into the search box', 'Type "Texas" into the search box', 'Type "Dallas" into the search box']
    assert move(page, f, "search:word:1", "University of Texas at Dallas")["outcome"] == "progressed"
    s = state(page, f, "University of Texas at Dallas")
    assert s["popupOpen"] is True and s["complete"] is False
    click = next(c["mid"] for c in s["candidates"] if c["describe"] == 'Click the option "University of Texas at Dallas"')
    row = move(page, f, click, "University of Texas at Dallas")
    assert (row["outcome"], row["committed"]) == ("verified", "University of Texas at Dallas")
    assert page.input_value("#school") == "" and portal_empty(page)


def test_give_up_closes_everything(page, load):
    load(page, fixture_html("workday_listbox.html"))
    f = inv(page)["How did you hear about us?"]
    move(page, f, "open", "x")
    assert move(page, f, "give_up", "x")["outcome"] == "closed"
    assert portal_empty(page)


def test_give_up_takes_back_a_query_the_engine_typed(page, load):
    load(page, fixture_html("workday_search.html"))
    f = inv(page)["School or University"]
    move(page, f, "search:value", "Texas")
    assert move(page, f, "give_up", "Texas")["outcome"] == "closed"
    assert page.input_value("#school") == "" and portal_empty(page)


def test_a_state_is_consumed_by_one_move_and_a_changed_list_is_stale(page, load):
    load(page, fixture_html("workday_listbox.html"))
    f = inv(page)["How did you hear about us?"]
    move(page, f, "open", "LinkedIn")
    v = state(page, f, "LinkedIn")["version"]
    assert move(page, f, "click:o1", "LinkedIn", version=v)["outcome"] == "progressed"   # Job Board → children
    assert move(page, f, "click:o1", "LinkedIn", version=v)["outcome"] == "stale"        # consumed


def test_a_click_on_a_list_that_changed_since_the_state_is_stale(page, load):
    load(page, fixture_html("workday_listbox.html"))
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
    load(page, fixture_html("workday_listbox.html"))
    fields = inv(page)
    move(page, fields["How did you hear about us?"], "open", "x")
    assert not portal_empty(page)
    row = page.evaluate(f"(a) => {OPS}.apply([a])", {
        "fid": fields["Are you legally authorized to work in the United States?"]["fid"],
        "fp": fields["Are you legally authorized to work in the United States?"]["fp"], "op": "choose", "text": "No"})[0]
    assert row["outcome"] == "verified" and page.inner_text("#heard") == "Select One"


def test_stop_closes_a_popup_a_move_opened(page, load):
    load(page, fixture_html("workday_listbox.html"))
    f = inv(page)["How did you hear about us?"]
    move(page, f, "open", "x")
    page.evaluate(f"() => {OPS}.cancel()")
    page.wait_for_timeout(400)
    assert portal_empty(page)
    assert move(page, f, "open", "x", version=0)["outcome"] == "cancelled"


def test_a_step_on_a_stale_fingerprint_or_another_frame_is_refused(page, load):
    load(page, fixture_html("workday_listbox.html"))
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
