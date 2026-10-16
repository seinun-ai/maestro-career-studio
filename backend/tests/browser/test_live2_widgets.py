"""Widgets the owner's second live check showed the engine could not see or drive
(plan docs/plans/2026-10-14-companion-live-check-2.md, Batch I): a read-only
Ant Design select with an invisible input, pill button groups, a debounced search
list, an address autocomplete, URL and date formats. Every page is a fixture or
inline made-up markup copied from the live shape (fixtures/browser/README.md)."""

from tests.browser.conftest import fixture_html
from tests.browser.pages import OPS, apply, explore, inv, oracle


# --- I1: a read-only combobox whose input is opacity 0
def test_a_readonly_antd_select_with_an_invisible_input_is_a_popup_field(page, load):
    load(page, fixture_html("antd_readonly_select.html"))
    f = inv(page)["Preferred Contact Method"]
    assert (f["shape"], f["required"], f["answered"], f["committed"]) == ("popup", True, False, "")


def test_choosing_in_a_readonly_antd_select_is_verified_and_reads_the_selection_item(page, load):
    load(page, fixture_html("antd_readonly_select.html"))
    f = inv(page)["Preferred Contact Method"]
    got = explore(page, f)
    assert [o["text"] for o in got["options"]] == ["Email", "Mobile Phone", "Home Phone"] and "error" not in got
    assert oracle(page, "antd_contact") == ""   # exploring commits nothing
    row = apply(page, inv(page)["Preferred Contact Method"], op="choose", text="Email")
    assert (row["outcome"], row["committed"]) == ("verified", "Email")
    assert oracle(page, "antd_contact") == "Email"
    after = inv(page)["Preferred Contact Method"]
    assert (after["committed"], after["answered"]) == ("Email", True)
    assert page.inner_text(".ant-select-selection-item") == "Email"


def test_a_hidden_readonly_combobox_is_still_not_listed(page, load):
    """Only opacity is forgiven: display:none, visibility:hidden and an empty box stay hidden."""
    load(page, "<label for='a'>A</label><input id='a' readonly role='combobox' aria-haspopup='listbox' style='display:none'>"
               "<label for='b'>B</label><div><input id='b' readonly role='combobox' aria-haspopup='listbox' style='visibility:hidden'></div>"
               "<div style='display:none'><label for='c'>C</label><div><input id='c' readonly role='combobox' aria-haspopup='listbox' style='opacity:0'></div></div>")
    assert inv(page) == {}


# --- I2: pill button groups
def pill_fields(page):
    """The pill groups. The engine's shape is `pills`; a field is listed as `group` (the loop and the backend know six shapes)."""
    kinds = page.evaluate("(fids) => fids.map((f) => window.careerStudioCompanion.fillInventory.shapeOf(f).name)",
                          [f["fid"] for f in inv(page).values()])
    return {q: f for (q, f), name in zip(inv(page).items(), kinds, strict=True) if name == "pills"}


def test_pill_groups_are_one_field_each_with_their_question_and_options(page, load):
    load(page, fixture_html("pill_buttons.html"))
    fields = pill_fields(page)
    assert list(fields) == ["Have you worked for Globex before?", "Highest degree"]
    prior = fields["Have you worked for Globex before?"]
    assert (prior["kind"], prior["multi"], prior["required"], prior["answered"], prior["committed"]) == ("choice", False, True, False, "")
    assert [o["text"] for o in prior["options"]] == ["No", "Yes"] and prior["optionsComplete"]
    degree = fields["Highest degree"]
    assert (degree["required"], [o["text"] for o in degree["options"]]) == (False, ["Associate", "Bachelor's", "Master's"])
    assert inv(page)["City"]["shape"] == "text"   # the form's own text box is not part of either group


def test_choosing_a_pill_clicks_once_and_is_verified(page, load):
    load(page, fixture_html("pill_buttons.html"))
    row = apply(page, pill_fields(page)["Have you worked for Globex before?"], op="choose", text="Yes")
    assert (row["outcome"], row["committed"]) == ("verified", "Yes")
    assert oracle(page, "pills_prior") == "Yes" and oracle(page, "pills_clicks") == 1
    now = pill_fields(page)["Have you worked for Globex before?"]
    assert (now["committed"], now["answered"]) == ("Yes", True)


def test_a_pressed_pill_is_never_clicked_again(page, load):
    """A second click would un-select it (ATS-O)."""
    load(page, fixture_html("pill_buttons.html"))
    apply(page, pill_fields(page)["Have you worked for Globex before?"], op="choose", text="Yes")
    row = apply(page, pill_fields(page)["Have you worked for Globex before?"], op="choose", text="Yes")
    assert row["outcome"] == "verified"
    assert oracle(page, "pills_prior") == "Yes" and oracle(page, "pills_clicks") == 1


def test_choosing_the_other_pill_replaces_the_pick(page, load):
    load(page, fixture_html("pill_buttons.html"))
    apply(page, pill_fields(page)["Have you worked for Globex before?"], op="choose", text="Yes")
    row = apply(page, pill_fields(page)["Have you worked for Globex before?"], op="choose", text="No")
    assert (row["outcome"], row["committed"]) == ("verified", "No") and oracle(page, "pills_prior") == "No"


def test_a_pill_the_user_pressed_counts_as_answered(page, load):
    load(page, fixture_html("pill_buttons.html"))
    page.click("button:has-text('Master')")
    degree = pill_fields(page)["Highest degree"]
    assert (degree["committed"], degree["answered"]) == ("Master's", True)


def test_an_option_the_group_does_not_have_is_missing_and_nothing_is_clicked(page, load):
    load(page, fixture_html("pill_buttons.html"))
    row = apply(page, pill_fields(page)["Have you worked for Globex before?"], op="choose", text="Maybe")
    assert (row["outcome"], row["reason"]) == ("unexpected", "option_missing") and oracle(page, "pills_clicks") == 0


def test_an_aria_radiogroup_of_div_radios_is_a_pill_group_too(page, load):
    load(page, "<div role='radiogroup' aria-label='Are you over 18?'>"
               "<div role='radio' aria-checked='false' tabindex='0' id='r1'>Yes</div>"
               "<div role='radio' aria-checked='false' tabindex='0' id='r2'>No</div></div>"
               "<script>for (const r of document.querySelectorAll('[role=radio]')) r.addEventListener('click', () => {"
               "for (const o of document.querySelectorAll('[role=radio]')) o.setAttribute('aria-checked', String(o === r)); });</script>")
    f = inv(page)["Are you over 18?"]
    assert (f["shape"], [o["text"] for o in f["options"]]) == ("group", ["Yes", "No"])
    assert apply(page, f, op="choose", text="No")["outcome"] == "verified"
    assert page.get_attribute("#r2", "aria-checked") == "true" and page.get_attribute("#r1", "aria-checked") == "false"


def test_a_toolbar_of_toggle_buttons_and_a_lone_toggle_are_not_fields(page, load):
    load(page, "<div role='toolbar' aria-label='Format'><button aria-pressed='false'>Bold</button>"
               "<button aria-pressed='false'>Italic</button></div><button aria-pressed='false'>Star this job</button>")
    assert inv(page) == {}


def test_a_list_holding_back_and_submit_buttons_is_not_a_field(page, load):
    """A labelled list of button-only items is a pill group only when no button moves the form on (the I-2 regression)."""
    load(page, "<ul role='list' aria-label='Form actions'><li><button type='button'>Back</button></li>"
               "<li><button type='button'>Submit application</button></li></ul>")
    assert inv(page) == {}
    assert page.evaluate("(el) => window.careerStudioCompanion.shapes.of(el)", page.query_selector("button")) is None


def test_an_aria_pressed_next_and_back_pair_is_not_a_field(page, load):
    load(page, "<fieldset><legend>Navigation</legend><button type='button' aria-pressed='false'>Back</button>"
               "<button type='button' aria-pressed='false'>Next</button></fieldset>")
    assert inv(page) == {}


def test_a_group_with_a_submit_typed_or_submit_marked_member_is_not_a_field(page, load):
    load(page, "<ul role='list' aria-label='Choices'><li><button type='submit'>Option A</button></li>"
               "<li><button type='button'>Option B</button></li></ul>"
               "<ul role='list' aria-label='Others'><li><button type='button' id='btn-submit'>Option C</button></li>"
               "<li><button type='button'>Option D</button></li></ul>"
               "<ul role='list' aria-label='Marked'><li><button type='button' data-qa='submit'>Option E</button></li>"
               "<li><button type='button'>Option F</button></li></ul>")
    assert inv(page) == {}


def test_a_yes_no_group_still_works_beside_a_form_actions_list(page, load):
    load(page, "<label>Are you over 18?</label><ul role='list' aria-label='Are you over 18?'>"
               "<li><button type='button' aria-pressed='false'>Yes</button></li>"
               "<li><button type='button' aria-pressed='false'>No</button></li></ul>"
               "<ul role='list' aria-label='Form actions'><li><button type='button'>Back</button></li>"
               "<li><button type='button'>Submit application</button></li></ul>")
    assert list(pill_fields(page)) == ["Are you over 18?"]


def test_the_engine_never_presses_a_pill_that_sorts_as_submit_or_next(page, load):
    """Defence in depth: even where a group were wrongly read, choose refuses to click a Submit or Next."""
    load(page, "<ul role='list' aria-label='Are you over 18?'><li><button type='button' aria-pressed='false'>Yes</button></li>"
               "<li><button type='button' aria-pressed='false'>No</button></li></ul>"
               "<button type='button' id='real-next' onclick='window.__clicks = (window.__clicks || 0) + 1'>Next</button>"
               "<button type='button' id='real-submit' onclick='window.__clicks = (window.__clicks || 0) + 1'>Submit application</button>")
    got = page.evaluate("""async () => {
      const ns = window.careerStudioCompanion;
      const el = document.querySelector("button[aria-pressed]");
      const base = ns.shapes.of(el);
      const out = [];
      for (const id of ["real-next", "real-submit"]) {
        const btn = document.getElementById(id);
        const shape = { ...base, passive: () => ({ options: [{ oid: "o1", text: btn.textContent, selected: false }], complete: true }),
          members: () => [btn], labelOf: (m) => m.textContent, pressed: () => false };
        out.push(await ns.fillBase.withinBudget((t) => ns.fillCore.choose(el, shape, { text: btn.textContent }, t), 4000));
      }
      return out;
    }""")
    assert [(g["outcome"], g["reason"]) for g in got] == [("unexpected", "submit_like")] * 2
    assert page.evaluate("window.__clicks || 0") == 0


def test_a_pill_group_multiple_is_added_to_never_unpressed(page, load):
    """A multi-select pill group (the vendor's class says so) takes a set of items; a pill already on stays on."""
    load(page, "<div class='input-row--multiselect cx-multi-select-pills'><ul role='list' aria-label='Which tools do you use?'>"
               + "".join(f"<li><button type='button' aria-pressed='false'>{t}</button></li>" for t in ("Git", "SQL", "Docker"))
               + "</ul></div><script>for (const b of document.querySelectorAll('button')) b.addEventListener('click', () =>"
                 "b.setAttribute('aria-pressed', String(b.getAttribute('aria-pressed') !== 'true')));</script>")
    f = inv(page)["Which tools do you use?"]
    assert (f["shape"], f["multi"], f["answered"]) == ("group", True, False)
    page.click("button:has-text('SQL')")
    got = page.evaluate(f"(a) => {OPS}.apply([a])", {"fid": f["fid"], "fp": f["fp"], "op": "set", "texts": ["Git", "SQL"], "terms": []})[0]
    assert got["outcome"] == "verified"
    assert page.evaluate("[...document.querySelectorAll('[aria-pressed=true]')].map((b) => b.textContent)") == ["Git", "SQL"]


def test_the_loop_fills_a_pill_group_like_any_other_choice(page):
    from tests.browser.test_fill_end_to_end import _run
    out = _run(page, html=fixture_html("pill_buttons.html"), map={
        "Have you worked for Globex before?": {"route": "slot", "slot": "work_history.worked_here", "value": "No"},
        "Highest degree": {"route": "slot", "slot": "education.0.degree", "value": "Master's"},
        "City": {"route": "none"}})
    assert {q: out["by_question"][q]["status"] for q in ("Have you worked for Globex before?", "Highest degree")} == {
        "Have you worked for Globex before?": "verified", "Highest degree": "verified"}
    assert (oracle(page, "pills_prior"), oracle(page, "pills_degree")) == ("No", "Master's")
    assert oracle(page, "pills_clicks") == 2
    # A second run finds both answered and presses nothing.
    again = _run(page, fresh=False, map={"Have you worked for Globex before?": {"route": "slot", "slot": "work_history.worked_here", "value": "No"}})
    assert again["by_question"]["Have you worked for Globex before?"]["status"] == "already"
    assert oracle(page, "pills_clicks") == 2


# --- I3: debounced search lists (JET-style combobox)
JET_PICK = "Washington, DC, United States"


def test_a_debounced_list_is_waited_for_and_no_enter_is_sent(page, load):
    """The list shows 500 ms after the last keystroke; an Enter before it clears the query (ATS-O)."""
    load(page, fixture_html("jet_combobox.html"))
    f = inv(page)["City or state"]
    assert (f["shape"], f["answered"], f["committed"]) == ("search", False, "")
    got = explore(page, f, "Washington")
    assert [o["text"] for o in got["options"]] == [JET_PICK, "Washington, Tyne and Wear, United Kingdom"] and "error" not in got
    assert oracle(page, "jet_enters") == 0 and oracle(page, "jet_city") == ""
    assert page.input_value("[id='location|input']") == ""   # the engine's query is taken back


def test_a_jet_pick_is_verified_once_and_read_back_as_the_inputs_own_text(page, load):
    load(page, fixture_html("jet_combobox.html"))
    f = inv(page)["City or state"]
    row = apply(page, f, op="choose", text=JET_PICK, term="Washington")
    assert (row["outcome"], row["committed"]) == ("verified", JET_PICK)
    assert (oracle(page, "jet_city"), oracle(page, "jet_picks"), oracle(page, "jet_enters")) == (JET_PICK, 1, 0)
    now = inv(page)["City or state"]
    assert (now["committed"], now["answered"]) == (JET_PICK, True)
    # Already there: nothing is typed or clicked again.
    assert apply(page, now, op="choose", text=JET_PICK, term="Washington")["outcome"] == "verified"
    assert oracle(page, "jet_picks") == 1


def test_a_query_typed_into_a_select_style_box_is_not_its_value(page, load):
    load(page, fixture_html("jet_combobox.html"))
    page.click("[id='location|input']")
    page.keyboard.type("Wash")
    assert inv(page)["City or state"]["committed"] == ""   # list pending or open: the text is a query


def test_an_autocomplete_with_no_value_node_reads_its_own_text_once_the_list_is_closed(page, load):
    """No JET marker: a select-style wrapper, the pick lands as the input's text, and the box is at rest."""
    load(page, "<label for='c'>Country</label><div class='combo-container'><input id='c' role='combobox' aria-autocomplete='list' "
               "aria-expanded='false'></div><div id='drop' role='listbox' style='display:none'><div role='option'>Canada</div></div>"
               "<script>const i = document.getElementById('c'), d = document.getElementById('drop');"
               "i.addEventListener('input', () => { d.style.display = ''; i.setAttribute('aria-expanded', 'true'); });"
               "d.firstChild.addEventListener('click', () => { i.value = 'Canada'; d.style.display = 'none'; i.setAttribute('aria-expanded', 'false'); });"
               "i.setAttribute('aria-controls', 'drop');</script>")
    f = inv(page)["Country"]
    row = apply(page, f, op="choose", text="Canada", term="Can")
    assert (row["outcome"], row["committed"]) == ("verified", "Canada")


# --- I5: URL values
URL_BOX = "<label for='u'>Website</label><input id='u'{attrs}>"


def test_a_url_is_written_whole_and_compared_after_normalising_scheme_www_and_slash(page, load):
    load(page, URL_BOX.format(attrs=""))
    f = inv(page)["Website"]
    row = apply(page, f, op="write", value="https://sample-one-site.example.dev", format="url")
    assert (row["outcome"], row["committed"]) == ("verified", "https://sample-one-site.example.dev")
    # The page re-writes it as it likes: the same site is still the same value.
    page.evaluate("document.getElementById('u').value = 'http://www.Sample-One-Site.example.dev/'")   # the page's own rewrite
    assert apply(page, inv(page)["Website"], op="write", value="https://sample-one-site.example.dev", format="url")["outcome"] == "verified"


def test_a_url_box_shorter_than_the_url_is_refused_not_truncated(page, load):
    load(page, URL_BOX.format(attrs=" maxlength='20'"))
    row = apply(page, inv(page)["Website"], op="write", value="https://sample-one-site.example.dev", format="url")
    assert (row["outcome"], row["reason"]) == ("unexpected", "too_long") and page.input_value("#u") == ""


def test_a_different_host_is_not_the_same_url(page, load):
    load(page, URL_BOX.format(attrs=""))
    f = inv(page)["Website"]
    apply(page, f, op="write", value="https://example.dev", format="url")
    assert page.input_value("#u") == "https://example.dev"
    # Verifying a different site against what the box holds is a revert, never a match.
    ok = page.evaluate("() => window.careerStudioCompanion.fillBase.equivalent('example.dev', 'sample-one-site.example.dev', { format: 'url' })")
    assert ok is False


URL_SEARCH = ("<label for='q'>Portfolio link</label><div class='wrap'><input id='q' role='combobox' aria-autocomplete='list' "
              "aria-controls='ql'></div><ul id='ql' role='listbox' hidden></ul>"
              "<script>window.typed = []; const q = document.getElementById('q');"
              "q.addEventListener('input', () => window.typed.push(q.value));</script>")


def test_a_url_is_never_searched_by_its_words(page, load):
    """ATS-O truncated a link to its last words (a search:word move): a URL has no words to search."""
    load(page, URL_SEARCH)
    f = inv(page)["Portfolio link"]
    url = "https://sample-one-site.example.dev/work"
    s = page.evaluate(f"(r) => {OPS}.stepState(r)", {"fid": f["fid"], "fp": f["fp"], "value": url})
    assert not [c for c in s["candidates"] if c["mid"].startswith("search:word")]
    explore(page, f, url)
    assert set(page.evaluate("window.typed")) <= {url, ""}   # the whole URL, never "sample-one-site.example.dev/work" pieces


# --- I7: flicker visibility
def test_an_explore_that_committed_and_took_it_back_says_so_and_counts_the_changes(page, load):
    from tests.browser.pages import SINGLE_HIT_SEARCH
    load(page, SINGLE_HIT_SEARCH)
    got = explore(page, inv(page)["Field of study"], "Analytics")
    assert got["tookBack"] is True and "error" not in got
    assert got["changes"] == 2   # the pill the search added, and its removal
    assert oracle(page, "field_of_study") == ""


def test_an_explore_that_changed_nothing_has_no_took_back_and_no_changes(page, load):
    load(page, fixture_html("workday_search.html"))
    got = explore(page, inv(page)["School or University"], "Arlington")
    assert "tookBack" not in got and got["changes"] == 0


def test_a_commit_that_could_not_be_taken_back_is_not_took_back(page, load):
    from tests.browser.pages import SINGLE_HIT_SEARCH
    load(page, SINGLE_HIT_SEARCH)
    got = explore(page, inv(page)["Minor"], "Analytics")
    assert got["error"] == "committed_while_exploring" and "tookBack" not in got and got["changes"] == 1


def test_an_applied_choice_counts_one_change_and_a_repeat_none(page, load):
    load(page, fixture_html("pill_buttons.html"))
    f = pill_fields(page)["Have you worked for Globex before?"]
    assert apply(page, f, op="choose", text="Yes")["changes"] == 1
    assert apply(page, pill_fields(page)["Have you worked for Globex before?"], op="choose", text="Yes")["changes"] == 1


# --- review follow-ups: a box that keeps its pick as its own text (no value node, no JET marker)
STRICT = ("<label for='c'>Country</label><div class='combo-container'>{hidden}<input id='c' role='combobox' aria-autocomplete='list' "
          "aria-expanded='false' aria-controls='drop'></div><div id='drop' role='listbox' style='display:none'><div role='option'>Canada</div></div>"
          "<script>window.picks = 0; const i = document.getElementById('c'), d = document.getElementById('drop');"
          "i.addEventListener('input', () => { const on = i.value !== ''; d.style.display = on ? '' : 'none'; i.setAttribute('aria-expanded', String(on)); });"
          "d.firstChild.addEventListener('click', () => { window.picks++; {onclick} d.style.display = 'none'; i.setAttribute('aria-expanded', 'false'); });"
          "</script>")
BACKING = "<input type='hidden' name='country' value=''>"


def strict(page, load, hidden="", onclick=""):
    load(page, STRICT.replace("{hidden}", hidden).replace("{onclick}", onclick))
    return inv(page)["Country"]


def test_an_empty_backing_input_means_not_committed_whatever_the_box_shows(page, load):
    strict(page, load, hidden=BACKING)
    page.fill("#c", "Canad")
    page.evaluate("document.getElementById('drop').style.display = 'none'; document.getElementById('c').setAttribute('aria-expanded', 'false');"
                  "document.activeElement.blur()")
    f = inv(page)["Country"]
    assert (f["committed"], f["answered"]) == ("", False)


def test_a_filled_backing_input_is_the_committed_value(page, load):
    strict(page, load, hidden=BACKING)
    page.evaluate("document.querySelector('[name=country]').value = 'CA'")
    assert inv(page)["Country"]["committed"] == "CA"


def test_a_pick_the_page_rejected_is_never_a_commit_on_a_box_that_proves_only_by_its_text(page, load):
    """The widget closes its list on the click and commits nothing (Ep). The engine types a PREFIX of the
    option's text, so the rejected box keeps "Canad" and cannot look like the pick "Canada"."""
    f = strict(page, load, onclick="i.blur();")
    row = apply(page, f, op="choose", text="Canada")
    assert row["outcome"] != "verified" and row.get("committed") != "Canada", row
    assert page.evaluate("window.picks") >= 1


def test_a_text_too_short_for_a_prefix_is_typed_whole_and_a_rejected_pick_is_unconfirmed(page, load):
    load(page, STRICT.replace("{hidden}", "").replace("{onclick}", "i.blur();").replace("Canada", "UK"))
    row = apply(page, inv(page)["Country"], op="choose", text="UK")
    assert row["outcome"] == "unconfirmed", row


def test_a_correct_pick_that_blurs_is_verified_with_the_prefix_term(page, load):
    f = strict(page, load, onclick="i.value = 'Canada'; i.blur();")   # H
    row = apply(page, f, op="choose", text="Canada")
    assert (row["outcome"], row["committed"]) == ("verified", "Canada"), row
    assert page.evaluate("document.getElementById('c').value") == "Canada"


def test_a_correct_pick_that_keeps_focus_is_verified_with_the_prefix_term(page, load):
    f = strict(page, load, onclick="i.value = 'Canada'; i.focus();")   # G2p
    row = apply(page, f, op="choose", text="Canada")
    assert (row["outcome"], row["committed"]) == ("verified", "Canada"), row


def test_the_prefix_is_not_typed_into_boxes_with_real_proof(page, load):
    """JET (its marker), a backing input and a Workday box are typed the term as given."""
    load(page, fixture_html("jet_combobox.html"))
    f = inv(page)["City or state"]
    explore(page, f, "Washington")
    row = apply(page, f, op="choose", text="Washington, DC, United States", term="Washington, DC, United States")
    assert (row["outcome"], row["committed"]) == ("verified", "Washington, DC, United States")
    assert page.evaluate("window.__oracle.jet_picks") == 1


def test_a_rejected_pick_over_an_empty_backing_input_is_not_committed(page, load):
    f = strict(page, load, hidden=BACKING, onclick="i.blur();")   # F
    row = apply(page, f, op="choose", text="Canada")
    assert row["outcome"] == "unexpected" and row["reason"] == "not_committed", row


def test_a_pick_typed_with_a_shorter_term_still_verifies_when_the_text_changed(page, load):
    f = strict(page, load, onclick="i.value = 'Canada';")
    row = apply(page, f, op="choose", text="Canada", term="Can")
    assert (row["outcome"], row["committed"]) == ("verified", "Canada")


# --- review follow-ups: pill groups and learned categories
def test_a_multi_select_is_told_by_its_tag_name_too(page, load):
    load(page, "<cx-multi-select><ul role='list' aria-label='Which tools do you use?'>"
               + "".join(f"<li><button type='button' aria-pressed='false'>{t}</button></li>" for t in ("Git", "SQL"))
               + "</ul></cx-multi-select>")
    assert inv(page)["Which tools do you use?"]["multi"] is True


NO_ARIA_PILLS = ("<ul role='list' aria-label='Do you hold a clearance?'>"
                 "<li><button type='button' class='pill'><span class='icon'></span><span>No</span></button></li>"
                 "<li><button type='button' class='pill pill--selected'><span class='icon'></span><span>Yes</span></button></li></ul>"
                 "<script>for (const b of document.querySelectorAll('.pill')) b.addEventListener('click', () => {"
                 "for (const o of document.querySelectorAll('.pill')) o.classList.toggle('pill--selected', o === b); });</script>")


def test_a_list_of_button_only_items_is_a_pill_group_even_with_no_aria_pressed(page, load):
    load(page, NO_ARIA_PILLS)
    f = inv(page)["Do you hold a clearance?"]
    assert (f["shape"], [o["text"] for o in f["options"]], f["committed"], f["answered"]) == ("group", ["No", "Yes"], "Yes", True)
    assert apply(page, f, op="choose", text="No")["outcome"] == "verified"
    assert page.get_attribute("button:has-text('No')", "class") == "pill pill--selected"


def test_a_pagination_list_or_a_menu_of_buttons_is_not_a_pill_group(page, load):
    load(page, "<ul role='list' aria-label='Pages'><li><button type='button' aria-current='page'>1</button></li>"
               "<li><button type='button'>2</button></li></ul>"
               "<ul role='list' aria-label='Sort by'><li><button type='button' aria-haspopup='menu'>Date</button></li>"
               "<li><button type='button' aria-expanded='false'>Title</button></li></ul>")
    assert [q for q, f in inv(page).items() if f["shape"] == "group"] == []


CHECKED_ROWS = ("<label id='l'>Skills</label><button id='b' aria-haspopup='listbox' aria-labelledby='l'>Select One</button><div id='portal'></div>"
                "<script>const b = document.getElementById('b'), p = document.getElementById('portal');"
                "const show = (rows) => { p.innerHTML = \"<ul role='listbox'>\" + rows.map((r) => `<li role='option' aria-checked='false'>${r}</li>`).join('') + '</ul>';"
                " p.querySelector('li').addEventListener('click', (e) => { e.stopPropagation(); show(['More A', 'More B']); }); };"
                "b.addEventListener('click', (e) => { e.stopPropagation(); show(['Alpha', 'Beta']); });"
                "document.addEventListener('click', () => { p.innerHTML = ''; });</script>")


def test_a_row_with_aria_checked_is_never_learned_as_a_category(page, load):
    from tests.browser.test_adaptive_step import _clicks, move, state
    load(page, CHECKED_ROWS)
    f = inv(page)["Skills"]
    move(page, f, "open", "Alpha")
    assert move(page, f, "click:o1", "Alpha")["outcome"] == "progressed"   # its list changed, so the step moved on
    move(page, f, "close", "Alpha")
    move(page, f, "open", "Alpha")
    assert _clicks(state(page, f, "Alpha"))[0] == 'Click the option "Alpha"'   # a selectable row stays an option


def test_a_default_port_is_not_a_different_site(page, load):
    load(page, "<div></div>")
    same = lambda a, b: page.evaluate("([a, b]) => window.careerStudioCompanion.fillBase.equivalent(a, b, { format: 'url' })", [a, b])  # noqa: E731
    assert same("https://example.dev:443/", "example.dev") and same("http://EXAMPLE.dev:80", "https://www.example.dev/")
    assert not same("example.dev:8080", "example.dev")


# --- a list of buttons is a pill group only when each item is the button and nothing else
def groups(page):
    return [q for q, f in inv(page).items() if f["shape"] == "group"]


def test_a_list_of_uploaded_files_with_remove_buttons_is_not_a_pill_group(page, load):
    load(page, "<ul role='list' aria-label='Uploaded files'><li><span>resume.pdf</span><button type='button'>Remove</button></li>"
               "<li><span>letter.pdf</span><button type='button'>Remove</button></li></ul>")
    assert groups(page) == []


def test_a_list_of_profiles_with_edit_buttons_is_not_a_pill_group(page, load):
    load(page, "<ul role='list' aria-label='Your profiles'><li><button type='button'>Edit</button></li>"
               "<li><button type='button'>Edit</button></li></ul>")
    assert groups(page) == []


def test_an_item_whose_text_is_more_than_its_button_is_not_a_pill(page, load):
    load(page, "<ul role='list' aria-label='Offers'><li>Offer one <button type='button'>Yes</button></li>"
               "<li>Offer two <button type='button'>No</button></li></ul>")
    assert groups(page) == []


def test_the_real_pill_list_is_still_a_group(page, load):
    load(page, NO_ARIA_PILLS)
    assert groups(page) == ["Do you hold a clearance?"]
