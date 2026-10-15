"""The generic fill mechanics (fill-core.js) through the page operations
(fill-ops.js), in real Chromium against the committed fixtures: search-and-pick
widgets, settling results, and exploring without leaving a commit behind."""

import time

from tests.browser.conftest import ENGINE_SOURCES, EXTENSION, fixture_html
from tests.browser.pages import (
    CATEGORY_POPUP,
    OPS,
    SELECT_ON_CLOSE,
    SINGLE_HIT_SEARCH,
    apply,
    explore,
    in_both_windows,
    inv,
    list_shown,
    oracle,
)


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
    assert oracle(page, "country") == "India"
    page.evaluate("window.rejectClicks = true")
    row = apply(page, f, op="choose", text="Canada", term="can")
    assert (row["outcome"], row["reason"], row["committed"]) == ("unexpected", "not_committed", "India")
    assert oracle(page, "country") == "India"


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
    assert oracle(page, "school") == "Texas A&M University"
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


# ---------- a list field's items are committed one at a time (Task 28), on workday_misses.html

def test_a_kept_explore_list_is_committed_in_without_a_second_search(page, load):
    """The item's explore leaves its settled list up (`keep`) and its one-item
    set clicks the row in it: one search per item, not two (the owner's skills
    list timed out searching every item twice)."""
    load(page, fixture_html("workday_misses.html"))
    listen(page)
    skills = inv(page)["Type to Add Skills"]
    got = explore(page, skills, "SQL", keep=True)
    assert [o["text"] for o in got["options"]] == ["SQL", "SQL Server"] and "kept" not in got
    assert list_shown(page) and oracle(page, "slowSkills") == []
    row = apply(page, skills, op="set", texts=["SQL"], terms=["SQL"])
    assert (row["outcome"], row["added"], row["missing"]) == ("verified", ["SQL"], [])
    assert oracle(page, "slowSkills") == ["SQL"] and not list_shown(page) and page.input_value("#skills") == ""
    heard = [h for h in page.evaluate("window.heard") if h.startswith("skills:")]
    assert heard.count("skills:keyup:Enter") == 1   # explore's search; the set typed and pressed nothing


def test_a_kept_list_is_closed_by_anything_but_its_own_set(page, load):
    load(page, fixture_html("workday_misses.html"))
    f = inv(page)
    explore(page, f["Type to Add Skills"], "SQL", keep=True)
    assert list_shown(page)
    row = apply(page, f["Phone Extension"], op="write", value="12")   # another field's operation closes it first
    assert row["outcome"] == "verified" and not list_shown(page)
    explore(page, f["Type to Add Skills"], "SQL", keep=True)
    assert list_shown(page)
    page.evaluate(f"() => {OPS}.cancel()")   # a Stop closes it too
    page.wait_for_function("() => !document.querySelector('[data-automation-id=activeListContainer]')")
    assert page.input_value("#skills") == ""


def test_a_click_the_page_loses_to_a_redraw_is_made_again_on_the_fresh_row(page, load):
    """The first Pandas click is dropped and the list's rows are new nodes. The
    set item waits for its pill, finds the row again and clicks it once more —
    one click per try, never two before the page shows the first took."""
    load(page, fixture_html("workday_misses.html"))
    listen(page)
    row = apply(page, inv(page)["Type to Add Skills"], op="set", texts=["Pandas"], terms=["Pandas"])
    assert (row["outcome"], row["added"]) == ("verified", ["Pandas"])
    assert oracle(page, "slowSkills") == ["Pandas"]
    assert [(c["text"], c["on"]) for c in page.evaluate("window.rowClicks")] == [("Pandas", "checkbox")] * 2


def test_an_item_the_list_never_shows_is_missing_and_the_next_one_still_lands(page, load):
    load(page, fixture_html("workday_misses.html"))
    skills = inv(page)["Type to Add Skills"]
    row = apply(page, skills, op="set", texts=["Rust"], terms=["Rust"])
    assert (row["outcome"], row["missing"]) == ("partial", ["Rust"]) and oracle(page, "slowSkills") == []
    row = apply(page, skills, op="set", texts=["SQL"], terms=["SQL"])
    assert row["outcome"] == "verified" and oracle(page, "slowSkills") == ["SQL"]


# ---------- a redrawn section is typed once (Task 32), on workday_misses.html

def test_writes_started_inside_a_redraw_gap_land_on_the_new_boxes(page, load):
    """Choosing Country makes the page redraw Address, City and Postal Code as new
    nodes 400 ms later, with nothing changing in between, and the new boxes show
    what the app holds, so a draft typed on an old node is lost. The three writes
    start straight after the choice, inside that gap on purpose: each waits for
    the page to stop changing and lands on the node that is there then."""
    load(page, fixture_html("workday_misses.html"))
    f = inv(page)
    assert apply(page, f["Country"], op="choose", text="Canada")["outcome"] == "verified"
    page.evaluate("""() => { window.typed = [];
      document.addEventListener('input', (e) => window.typed.push(e.target.id), true); }""")
    old = page.evaluate("[...document.querySelectorAll('#address-section input')].map((i) => i.id)")
    rows = [apply(page, f[q], op="write", value=v)
            for q, v in (("Address", "1 Main St"), ("City", "Toronto"), ("Postal Code", "M5V 2T6"))]
    assert [(r["outcome"], r["committed"]) for r in rows] == [
        ("verified", "1 Main St"), ("verified", "Toronto"), ("verified", "M5V 2T6")]
    assert page.evaluate("[...document.querySelectorAll('#address-section input')].map((i) => i.id)") == old
    assert page.evaluate("window.typed") == old   # each box typed into once: no draft lost to an old node
    assert [oracle(page, k) for k in ("addressLine", "cityName", "postalCode")] == ["1 Main St", "Toronto", "M5V 2T6"]
    assert page.evaluate("[...document.querySelectorAll('#address-section input')].map((i) => i.value)") \
        == ["1 Main St", "Toronto", "M5V 2T6"]


REPLACED_MID_WRITE = """<label for='a'>Address</label><input id='a' name='addr'>
<script>
// The first keystroke makes the page draw the box again: the typed draft stays on the old node.
window.draws = 0;
document.getElementById('a').addEventListener('input', (e) => {
  if (window.draws++) return;
  const fresh = document.createElement('input');
  for (const a of e.target.attributes) fresh.setAttribute(a.name, a.value);
  e.target.replaceWith(fresh);
}, { once: true });
</script>"""


def test_a_write_whose_box_is_replaced_mid_write_is_made_again_on_the_new_one(page, load):
    """A box redrawn while it is typed into loses the draft with the old node.
    The field is found again by its fingerprint and written once more, in the same
    apply: one row, verified, on the node that is on the page now."""
    load(page, REPLACED_MID_WRITE)
    f = inv(page)["Address"]
    row = apply(page, f, op="write", value="1 Main St")
    assert (row["outcome"], row["committed"]) == ("verified", "1 Main St")
    assert page.input_value("#a") == "1 Main St" and page.evaluate("document.querySelectorAll('#a').length") == 1


def _form_of_text_boxes(n, animator_inside):
    """`n` labelled boxes in a form, and a box moving every frame: in the same
    field group as the text boxes, or somewhere else on the page."""
    boxes = "".join(f"<div><label for='f{i}'>Field {i}</label><input id='f{i}'></div>" for i in range(n))
    spinner = "<div id='spin'></div>"
    group = f"<div data-automation-id='formField-group'>{spinner}{boxes}</div>" if animator_inside else boxes
    return f"""{'' if animator_inside else spinner}<form>{group}</form>
<script>let n = 0; setInterval(() => {{ spin.style.left = (n++ % 50) + 'px'; }}, 16);</script>"""


def _write_all(page, count):
    """Each write's seconds, in order."""
    f = inv(page)
    took = []
    for i in range(count):
        start = time.monotonic()
        assert apply(page, f[f"Field {i}"], op="write", value=f"v{i}")["outcome"] == "verified"
        took.append(time.monotonic() - start)
    return took


def test_a_page_animating_elsewhere_does_not_hold_every_write_to_the_cap(page, load):
    """A carousel or badge changes the page every frame, so the whole page never
    holds still. Each write waits only on its own section, which does: no write
    runs to the 2 s cap, and ten fields fit well inside ten seconds."""
    load(page, _form_of_text_boxes(10, animator_inside=False))
    took = _write_all(page, 10)
    assert max(took) < 1.5 and sum(took) < 10, took


def test_a_page_that_never_holds_still_costs_one_capped_wait_then_is_left_alone(page, load):
    """The animation sits in the very section being written to, so the first write
    runs to the cap; the page is then noisy and the other nine do not wait."""
    load(page, _form_of_text_boxes(10, animator_inside=True))
    took = _write_all(page, 10)
    slow = [t for t in took if t > 1.8]   # which write meets the page first is not fixed
    assert len(slow) == 1 and sorted(took)[-2] < 1.0 and sum(took) < 6, took   # unmarked: 10 x 2 s


# ---------- a pick the box shows differently from its option (live check 9) ----------
#
# A phone-country picker lists "Acmeland +1" and shows only "+1" once it is picked, so the text of the option is nowhere on the
# box. The widget still says what it holds: its reopened list marks the held option. That second proof is read only when the
# box changed on the click, and only by an option that is the one chosen (or equals the value).

def _country(page, load, mark="class", **flags):
    load(page, fixture_html("acme_phone_country.html"))
    page.evaluate("(f) => Object.assign(window, f)", {"__mark": mark, **flags})
    return inv(page)["Country"]


def test_a_pick_the_box_shows_as_a_dial_code_is_verified_by_the_option_the_list_marks_held(page, load):
    f = _country(page, load)
    row = apply(page, f, op="choose", text="Acmeland +1", term="Acme")
    assert row["outcome"] == "verified", row
    assert oracle(page, "country") == "Acmeland +1"
    assert page.inner_text(".acme__single-value").strip().endswith("+1")
    assert not list_shown(page, "menu-root")


def test_the_marked_option_is_read_from_aria_selected_too(page, load):
    f = _country(page, load, mark="aria")
    assert apply(page, f, op="choose", text="Acmeland +1", term="Acme")["outcome"] == "verified"


def test_a_pick_whose_reopened_list_marks_nothing_is_still_not_committed(page, load):
    f = _country(page, load, __forget=True)
    row = apply(page, f, op="choose", text="Acmeland +1", term="Acme")
    assert (row["outcome"], row["reason"]) == ("unexpected", "not_committed")


def test_a_pick_the_page_made_into_another_option_is_not_verified(page, load):
    """The box changed, and the list marks Betaland: not the option chosen."""
    f = _country(page, load, __wrongPick="Betaland +2")
    row = apply(page, f, op="choose", text="Acmeland +1", term="Acme")
    assert row["outcome"] != "verified", row
    assert oracle(page, "country") == "Betaland +2"
