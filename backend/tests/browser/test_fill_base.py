from tests.browser.conftest import fixture_html

B = "window.careerStudioCompanion.fillBase"


def test_invalid_reads_aria_invalid_linked_errors_and_nearby_errors(page, load):
    load(page, """
      <div data-automation-id='formField-a'><input id='a' value='x'><p data-automation-id='errorMessage'>Error: required</p></div>
      <input id='b' aria-invalid='true' value='x'>
      <input id='c' aria-describedby='ce' value='x'><p id='ce'>Must be a number</p>
      <input id='d' value='x'>""")
    got = page.evaluate(f"() => ['a','b','c','d'].map(id => {B}.invalid(document.getElementById(id)))")
    assert got == [True, True, True, False]


def test_an_unwrapped_field_reads_its_own_nearby_error_not_its_neighbours(page, load):
    load(page, """<form><div><input id='e' value='x'><span class='error'>Must be a number</span></div>
      <div><input id='f' value='x'></div></form>""")
    got = page.evaluate(f"() => ['e','f'].map(id => {B}.invalid(document.getElementById(id)))")
    assert got == [True, False]

INVALID = f"ids => ids.map(id => {B}.invalid(document.getElementById(id)))"


def test_a_wrapper_named_like_a_field_but_holding_two_fields_is_not_one_box(page, load):
    load(page, """<div class='form-fields'><div><input id='a' value='x'></div>
      <div><input id='b' value='x'><span class='error'>Must be a number</span></div></div>""")
    assert page.evaluate(INVALID, ["a", "b"]) == [False, True]


def test_a_plain_button_beside_an_input_does_not_hide_the_error_above(page, load):
    load(page, """<form><div><div><input id='a' value='x'><button type='button'>Clear</button></div>
      <span class='error'>Must be a number</span></div><div><input id='z'></div></form>""")
    assert page.evaluate(INVALID, ["a"]) == [True]


def test_an_unwrapped_radio_group_reads_its_group_error(page, load):
    load(page, """<form><div><input type='radio' id='r1' name='auth' value='y'>
      <input type='radio' id='r2' name='auth' value='n'><span class='error'>This field is required</span></div>
      <div><input id='z'></div></form>""")
    assert page.evaluate(INVALID, ["r1"]) == [True]


def test_radios_in_their_own_field_and_workday_date_sections_read_the_field_error(page, load):
    load(page, """<div class='field'><input type='radio' id='r1' name='auth'><input type='radio' id='r2' name='auth'>
        <span class='error'>Required</span></div>
      <div data-automation-id='formField-from'><div data-automation-id='dateInputWrapper'>
        <input role='spinbutton' id='m' aria-label='Month'><input role='spinbutton' id='y' aria-label='Year'></div>
        <p data-automation-id='errorMessage'>Error: The field From is required.</p></div>""")
    assert page.evaluate(INVALID, ["r1", "m"]) == [True, True]

def test_an_unlinked_popup_is_owned_only_when_it_alone_appeared(page, load):
    load(page, "<ul role='listbox' style='display:none'><li role='option'>Canada</li></ul><button id='b'>x</button><div id='p'></div>")
    one = page.evaluate(f"""() => {{ const before = {B}.popups();
      document.getElementById('p').innerHTML = "<ul role='listbox'><li role='option'>United States</li></ul>";
      return {B}.optionsOf({B}.ownedPopup(document.getElementById('b'), before)).map(o => o.text); }}""")
    assert one == ["United States"]
    two = page.evaluate(f"""() => {{ const before = {B}.popups();
      document.getElementById('p').innerHTML += "<ul role='listbox'><li role='option'>B</li></ul><ul role='listbox'><li role='option'>C</li></ul>";
      return {B}.ownedPopup(document.getElementById('b'), before); }}""")
    assert two is None


def test_a_fresh_dialog_holding_a_listbox_is_one_owned_popup(page, load):
    load(page, "<button id='b'>x</button><div id='p'></div>")
    got = page.evaluate(f"""() => {{ const before = {B}.popups();
      document.getElementById('p').innerHTML = "<div role='dialog'><ul role='listbox'><li role='option'>A</li></ul></div>";
      return {B}.ownedPopup(document.getElementById('b'), before)?.getAttribute('role'); }}""")
    assert got == "dialog"


def test_cleanup_clicks_outside_only_to_close_a_popup_the_engine_opened(page, load):
    load(page, "<input id='f'><ul id='lb' role='listbox'><li role='option'>A</li></ul>")
    page.evaluate("document.addEventListener('mousedown', () => window.outside = (window.outside || 0) + 1)")
    clicks = page.evaluate(f"""async () => {{ const t = {{cancelled: true}}; const f = document.getElementById('f');
      await {B}.closePopups(f, t, {{cleanup: true}}); const pageOwned = window.outside || 0;
      {B}.markEnginePopup(document.getElementById('lb'));
      await {B}.closePopups(f, t, {{cleanup: true}}); return [pageOwned, window.outside || 0]; }}""")
    assert clicks == [0, 1]

def test_aria_controls_wins_and_hidden_disabled_or_loading_options_are_dropped(page, load):
    load(page, """<input id='c' role='combobox' aria-controls='lb'>
      <ul id='lb' role='listbox'><li role='option'>Yes</li><li role='option' aria-disabled='true'>Maybe</li>
        <li role='option' style='display:none'>No</li><li role='option'>Loading…</li></ul>""")
    got = page.evaluate(f"() => {B}.optionsOf({B}.ownedPopup(document.getElementById('c'), [])).map(o => o.text)")
    assert got == ["Yes"]


def test_a_timed_out_operation_can_never_click_late(page, load):
    load(page, "<button id='x'>x</button>")
    page.evaluate("document.getElementById('x').addEventListener('click', () => window.clicks = (window.clicks || 0) + 1)")
    out = page.evaluate(f"""() => {B}.withinBudget(async (t) => {{ await {B}.sleep(150);
        {B}.press(document.getElementById('x'), t); return 'clicked'; }}, 50).catch(e => e.name)""")
    page.wait_for_timeout(250)
    assert out == "Cancelled" and page.evaluate("window.clicks === undefined")


def test_cancel_all_stops_an_operation_in_flight(page, load):
    load(page, "<button id='x'>x</button>")
    page.evaluate("document.getElementById('x').addEventListener('click', () => window.clicks = 1)")
    out = page.evaluate(f"""() => {{ const run = {B}.withinBudget(async (t) => {{ await {B}.sleep(100);
        {B}.press(document.getElementById('x'), t); }}, 5000).catch(e => e.name);
        {B}.cancelAll(); return run; }}""")
    assert out == "Cancelled" and page.evaluate("window.clicks === undefined")


def test_stop_is_latched_until_the_next_run(page, load):
    load(page, "<button id='x'>x</button>")
    got = page.evaluate(f"""async () => {{ {B}.cancelAll();
        const after = await {B}.withinBudget(async (t) => {{ {B}.check(t); return 'ran'; }}, 1000).catch(e => e.name);
        {B}.resume();
        const next = await {B}.withinBudget(async (t) => {{ {B}.check(t); return 'ran'; }}, 1000).catch(e => e.name);
        return [after, next]; }}""")
    assert got == ["Cancelled", "ran"]


def test_equivalence_keeps_punctuation_meaningful_except_for_phones(page, load):
    load(page, "<div></div>")
    got = page.evaluate(f"""() => [
        {B}.equivalent('C', 'C++'), {B}.equivalent('José', 'jose'),
        {B}.equivalent('(555) 010-0000', '5550100000', {{format: 'phone'}}), {B}.equivalent('(555) 010-0000', '5550100000'),
        {B}.equivalent('123456.7', '12345.67'), {B}.equivalent('a.b@x.test', 'ab@x.test'), {B}.equivalent('', '')]""")
    assert got == [False, True, True, False, False, False, False]


def test_typing_is_trusted_input_a_workday_box_commits(page, load):
    """execCommand("insertText") fires TRUSTED input events: the Workday box
    only commits isTrusted input, and a blur then clears its error. If this ever
    fails, the Workday fix needs the debugger executor (out of scope)."""
    load(page, fixture_html("workday_text.html"))
    page.evaluate(f"() => {B}.typeText(document.getElementById('city'), 'Toronto', {{}})")
    page.evaluate("() => document.getElementById('city').blur()")
    assert page.evaluate("() => window.committed.city") == "Toronto"
    assert page.get_attribute("#city", "aria-invalid") == "false"
