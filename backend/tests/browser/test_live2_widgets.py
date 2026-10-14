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
    ok = page.evaluate(f"() => window.careerStudioCompanion.fillBase.equivalent('example.dev', 'sample-one-site.example.dev', {{ format: 'url' }})")
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
