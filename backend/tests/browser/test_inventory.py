import pytest

from tests.browser.conftest import fixture_html

NS = "window.careerStudioCompanion"
INV = f"{NS}.fillInventory"


def fields(page, consent_forms=False):
    return page.evaluate(f"(cf) => {INV}.list({{consentForms: cf}}).fields", consent_forms)


def by_question(page):
    return {f["question"]: f for f in fields(page)}


def test_every_shape_is_listed_once_with_its_question(page, load):
    load(page, """
      <label for='fn'>First name*</label><input id='fn'>
      <fieldset><legend>Are you 18 or older?</legend>
        <label><input type='radio' name='age'>Yes</label><label><input type='radio' name='age'>No</label></fieldset>
      <label for='shift'>What is your preferred shift?</label><input id='shift' role='combobox'>
      <fieldset><legend>State</legend><button aria-haspopup='listbox'>Select One</button></fieldset>
      <input type='hidden' value='x'><input type='file'><button type='submit'>Next</button>""")
    assert [(f["shape"], f["question"]) for f in fields(page)] == [
        ("text", "First name"), ("group", "Are you 18 or older?"),
        ("search", "What is your preferred shift?"), ("popup", "State")]
    shift = by_question(page)["What is your preferred shift?"]
    assert (shift["committed"], shift["answered"]) == ("", False)  # the page's hidden input is not its value


def test_a_field_record_carries_every_key_later_tasks_read(page, load):
    load(page, "<label for='fn'>First name*</label><input id='fn' aria-describedby='h'><p id='h'>As on your ID</p>")
    f = fields(page)[0]
    assert set(f) == {"fid", "fp", "shape", "kind", "multi", "question", "source", "section", "repeatIndex",
                      "required", "help", "committed", "answered", "options", "optionsComplete", "invalid",
                      "touched", "policyBlocked", "recipe", "part"}
    assert (f["kind"], f["source"], f["required"], f["help"]) == ("text", "label-for", True, "As on your ID")
    assert f["recipe"] is None   # a text box has no move to learn (content/recipes.js)
    assert f["part"] is None     # no date part: the field reader's `part`


def test_a_date_part_control_says_which_part_it_holds(page, load):
    """iCIMS (live 2026-10-01): a Month list, a Day list and a Year box are
    three fields of one date; each says its part so the loop writes only that."""
    load(page, fixture_html("icims_profile.html"))
    got = {f["question"]: (f["shape"], f["part"]) for f in fields(page)}
    start = "Start Date (Month / Day / Year)"
    assert [got[f"{start}: {p}"] for p in ("Month", "Day", "Year")] == [
        ("select", "month"), ("select", "day"), ("text", "year")]
    assert got["Enter in your mobile number: Type"] == ("select", None)


def test_a_fid_survives_repeat_calls_and_a_rerender(page, load):
    load(page, "<section><h3>Education 1</h3><label for='s'>School</label><input id='s'></section>")
    first = fields(page)[0]["fid"]
    assert fields(page)[0]["fid"] == first
    page.evaluate("() => { const o = document.getElementById('s'); o.replaceWith(o.cloneNode(true)); }")
    assert fields(page)[0]["fid"] == first


def test_resolve_reacquires_a_rerendered_node_and_live_fp_matches(page, load):
    load(page, "<label for='s'>School</label><input id='s'>")
    f = fields(page)[0]
    page.evaluate("() => { const o = document.getElementById('s'); const n = o.cloneNode(true); n.dataset.fresh = '1'; o.replaceWith(n); }")
    got = page.evaluate(f"(fid) => [{INV}.resolve(fid)?.dataset.fresh, {INV}.liveFp(fid), {INV}.fpOf(fid)]", f["fid"])
    assert got == ["1", f["fp"], f["fp"]]
    assert page.evaluate(f"() => {INV}.resolve('nope')") is None


def test_live_fp_changes_when_the_question_does(page, load):
    load(page, "<label for='s' id='l'>School</label><input id='s'>")
    f = fields(page)[0]
    page.evaluate("() => { document.getElementById('l').textContent = 'Employer'; }")
    assert page.evaluate(f"(fid) => {INV}.liveFp(fid)", f["fid"]) != f["fp"]


def test_same_labels_in_repeated_sections_are_separate_fields(page, load):
    load(page, """<section><h3>Work Experience 1</h3><label for='a'>Job Title</label><input id='a'></section>
                  <section><h3>Work Experience 2</h3><label for='b'>Job Title</label><input id='b'></section>""")
    got = fields(page)
    assert [(f["question"], f["repeatIndex"]) for f in got] == [("Job Title", 0), ("Job Title", 1)]
    assert got[0]["fid"] != got[1]["fid"] and got[0]["fp"] != got[1]["fp"]


def test_groups_dates_and_native_options(page, load):
    load(page, fixture_html("native.html") + fixture_html("workday_date.html"))
    by_q = by_question(page)
    assert [o["text"] for o in by_q["Highest degree"]["options"]] == ["Bachelor's", "Master's"]
    assert by_q["Highest degree"]["optionsComplete"] is True
    assert by_q["Which days can you work?"]["committed"] == ["Monday"] and by_q["Which days can you work?"]["multi"]
    assert by_q["I have a preferred name"]["committed"] == "No"
    assert by_q["Willing to relocate?"]["shape"] == "group"
    assert [o["text"] for o in by_q["Willing to relocate?"]["options"]] == ["Yes", "No"]
    assert by_q["Languages"]["committed"] == ["English"] and by_q["Languages"]["multi"]
    assert (by_q["From"]["shape"], by_q["From"]["source"]) == ("date", "legend")
    assert by_q["Graduation date"]["shape"] == "date" and by_q["End date"]["shape"] == "date"
    # The two date sections are ONE field, like a radio group's members.
    assert [f["question"] for f in fields(page)].count("From") == 1
    assert "Month" not in by_q and "Year" not in by_q


def test_date_sections_read_as_one_iso_value(page, load):
    load(page, fixture_html("workday_date.html"))
    page.evaluate("() => { document.getElementById('m').value = '05'; document.getElementById('y').value = '2021'; }")
    assert by_question(page)["From"]["committed"] == "2021-05"


def test_react_select_is_a_search_reading_its_single_value(page, load):
    load(page, fixture_html("react_select.html"))
    assert [(f["shape"], f["question"], f["committed"], f["required"]) for f in fields(page)] == [
        ("search", "Country", "", True)]
    page.click("#country")
    page.click("text=India")
    assert fields(page)[0]["committed"] == "India"


def test_workday_listbox_buttons_are_popups_asking_their_legend(page, load):
    load(page, fixture_html("workday_listbox.html"))
    assert [(f["shape"], f["question"], f["committed"]) for f in fields(page)] == [
        ("popup", "Degree", ""),
        ("popup", "Are you legally authorized to work in the United States?", "")]


def test_a_popup_button_with_a_search_dialog_is_a_popup(page, load):
    load(page, fixture_html("popup_with_search.html"))
    assert [(f["shape"], f["question"]) for f in fields(page)] == [("popup", "Field of study")]


def test_a_radio_group_without_a_legend_takes_its_group_label(page, load):
    load(page, """<span id='g'>Do you need sponsorship?</span>
      <div role='radiogroup' aria-labelledby='g'>
        <label><input type='radio' name='sp'>Yes</label><label><input type='radio' name='sp'>No</label></div>""")
    assert [(f["shape"], f["question"]) for f in fields(page)] == [("group", "Do you need sponsorship?")]


def test_contenteditable_is_a_text_field(page, load):
    load(page, "<label id='l'>Cover note</label><div contenteditable='true' aria-labelledby='l'>Hello  <b>there</b></div>")
    assert [(f["shape"], f["kind"], f["question"], f["committed"], f["answered"]) for f in fields(page)] == [
        ("text", "text", "Cover note", "Hello there", True)]


def test_user_typing_marks_touched_and_policy_blocks_signatures(page, load):
    load(page, "<label for='a'>City</label><input id='a'><label for='s'>Signature</label><input id='s'>")
    page.type("#a", "x")  # before any inventory: remembered by element
    by_q = by_question(page)
    assert by_q["City"]["touched"] is True and by_q["Signature"]["policyBlocked"] is True
    assert by_q["Signature"]["touched"] is False and by_q["City"]["policyBlocked"] is False
    assert page.evaluate(f"(fid) => [{INV}.isTouched(fid), {INV}.isBlocked(fid)]", by_q["Signature"]["fid"]) == [
        False, True]


def test_consent_forms_unlock_only_when_the_run_says_so(page, load):
    load(page, "<label><input type='checkbox' id='c'>I certify that the above is true</label>")
    assert fields(page)[0]["policyBlocked"] is True
    fid = fields(page, consent_forms=True)[0]["fid"]
    assert fields(page, consent_forms=True)[0]["policyBlocked"] is False
    assert page.evaluate(f"(fid) => {INV}.isBlocked(fid)", fid) is False


def test_consent_forms_unlock_every_label_and_only_consent_does(page, load):
    """With the standing permission nothing is refused by its label: a
    signature, a typed-name attestation, initials, a salary requirement. Without
    it the same fields are the policy's, as they always were."""
    load(page, """<label for='s'>Signature</label><input id='s'>
      <label for='n'>Please type your full name to sign</label><input id='n'>
      <label for='i'>Initials</label><input id='i'>
      <label for='p'>Password</label><input id='p'>
      <label for='w'>What are your annual salary requirements</label><input id='w'>
      <label><input type='checkbox'>I willingly accept the Terms and Conditions</label>""")
    assert [f["policyBlocked"] for f in fields(page)] == [True] * 6
    assert [f["policyBlocked"] for f in fields(page, consent_forms=True)] == [False] * 6
    assert page.evaluate(f"() => {INV}.list().fields.map((f) => f.policyBlocked)") == [True] * 6


def test_touching_any_member_of_a_group_marks_the_group(page, load):
    load(page, """<fieldset><legend>Are you 18 or older?</legend>
        <label><input type='radio' name='age' id='y'>Yes</label><label><input type='radio' name='age' id='n'>No</label></fieldset>
      <fieldset><legend>From</legend><div data-automation-id='dateInputWrapper'>
        <input data-automation-id='dateSectionMonth-input' role='spinbutton' aria-label='Month' id='m'>
        <input data-automation-id='dateSectionYear-input' role='spinbutton' aria-label='Year' id='yr'></div></fieldset>""")
    assert not any(f["touched"] for f in fields(page))
    page.click("text=No")
    page.type("#yr", "2021")
    assert [(f["question"], f["touched"]) for f in fields(page)] == [("Are you 18 or older?", True), ("From", True)]


def test_only_the_element_the_engine_is_typing_into_is_exempt(page, load):
    load(page, "<label for='a'>City</label><input id='a'><label for='b'>Zip</label><input id='b'>")
    fields(page)
    page.evaluate(f"() => {{ {NS}.fillBusyEl = document.getElementById('a'); }}")
    page.type("#a", "x")
    page.type("#b", "1")
    assert [(f["question"], f["touched"]) for f in fields(page)] == [("City", False), ("Zip", True)]


def test_scripted_input_is_not_the_user(page, load):
    load(page, "<label for='a'>City</label><input id='a'>")
    fields(page)
    page.evaluate("() => { const a = document.getElementById('a'); a.value = 'x'; a.dispatchEvent(new Event('input', {bubbles: true})); }")
    assert fields(page)[0]["touched"] is False


def test_open_shadow_roots_are_walked(page, load):
    load(page, "<div id='host'></div>")
    page.evaluate("""() => { const r = document.getElementById('host').attachShadow({mode:'open'});
        r.innerHTML = "<label for='z'>Zip</label><input id='z'>"; }""")
    assert [f["question"] for f in fields(page)] == ["Zip"]
    page.type("#host >> #z", "1")
    assert fields(page)[0]["touched"] is True


def test_a_modal_application_form_is_walked(page, load):
    load(page, "<div role='dialog' aria-modal='true'><label for='e'>Email</label><input id='e'></div>")
    assert [f["question"] for f in fields(page)] == ["Email"]


def test_a_popup_the_engine_opened_is_not_inventoried(page, load):
    load(page, fixture_html("popup_with_search.html"))
    page.click("#fos")
    assert [f["question"] for f in fields(page)] == ["Field of study", "Search"]  # the page's own dialog
    page.evaluate(f"() => {NS}.fillBase.markEnginePopup(document.querySelector('[role=dialog]'))")
    assert [f["question"] for f in fields(page)] == ["Field of study"]


def test_an_unrecognised_control_is_listed_as_unknown_not_dropped(page, load):
    load(page, "<span id='q'>Rate your SQL</span><div role='slider' aria-labelledby='q' tabindex='0'></div>")
    assert [(f["shape"], f["kind"], f["question"]) for f in fields(page)] == [("unknown", "unknown", "Rate your SQL")]


def test_aria_radios_no_shape_claims_are_one_unknown_field(page, load):
    load(page, """<span id='g'>Preferred contact</span><div role='radiogroup' aria-labelledby='g'>
      <div role='radio' aria-checked='false' tabindex='0'>Email</div><div role='radio' aria-checked='false'>Phone</div></div>""")
    assert [(f["shape"], f["question"]) for f in fields(page)] == [("unknown", "Preferred contact")]


def test_disabled_readonly_and_invisible_controls_are_skipped(page, load):
    load(page, """<label for='a'>A</label><input id='a' disabled><label for='b'>B</label><input id='b' readonly>
      <div style='display:none'><label for='c'>C</label><input id='c'></div><label for='d'>D</label><input id='d'>""")
    assert [f["question"] for f in fields(page)] == ["D"]


def test_answered_is_stricter_than_has_a_value(page, load):
    load(page, fixture_html("native.html") + fixture_html("workday_search.html"))
    by_q = by_question(page)
    assert by_q["I have a preferred name"]["answered"] is False       # unchecked reads "No"
    assert by_q["Type to Add Skills"]["answered"] is False            # one chip is not a finished set
    assert by_q["Highest degree"]["answered"] is False
    assert by_q["Are you 18 or older?"]["answered"] is False
    assert by_q["School or University"]["committed"] == ""


def test_a_search_widgets_existing_pill_is_its_committed_value(page, load):
    load(page, fixture_html("workday_search.html"))
    assert by_question(page)["Type to Add Skills"]["committed"] == ["SQL"]


def test_search_pills_are_read_from_the_multiselect_container(page, load):
    """Live Workday marks the INPUT `selectinput`; its pills are in the ancestor
    `multiselect` container. School and Skills share that markup, so one pill
    does not yet say single or several (only the open list's rows do): the pill
    reads as a list, neither field is `answered`, and `multi` is null (unknown)."""
    load(page, fixture_html("workday_search.html"))
    by_q = by_question(page)
    skills, school = by_q["Type to Add Skills"], by_q["School or University"]
    assert (skills["committed"], skills["multi"], skills["answered"]) == (["SQL"], None, False)
    assert (school["committed"], school["multi"], school["answered"]) == ("", None, False)
    page.evaluate("""() => { const p = document.querySelector('#skills').closest('[data-uxi-widget-type=multiselect]')
        .querySelector('[data-automation-id=selectedItem]'); p.closest('ul').append(p.parentElement.cloneNode(true)); }""")
    assert by_question(page)["Type to Add Skills"]["multi"] is True   # two pills: several


def test_an_aria_1_1_combobox_wrapper_is_its_input_not_a_second_field(page, load):
    load(page, """<label id='l'>Office</label>
      <div role='combobox' aria-labelledby='l'><input aria-labelledby='l'></div>""")
    assert [(f["shape"], f["question"]) for f in fields(page)] == [("search", "Office")]


def test_a_search_box_never_reads_an_unrelated_hidden_input(page, load):
    load(page, """<form><input type='hidden' name='csrf' value='TOKEN'>
      <div><div><label for='s'>Shift</label><input id='s' role='combobox'></div></div></form>""")
    assert [(f["question"], f["committed"]) for f in fields(page)] == [("Shift", "")]


def test_a_search_box_does_not_read_a_neighbours_single_value(page, load):
    load(page, """<div class='row'><label for='a'>A</label><input id='a' role='combobox'>
      <div class='x__single-value'>Z</div><label for='b'>B</label><input id='b' value='bee'></div>""")
    assert by_question(page)["A"]["committed"] == ""


def test_a_hidden_input_inside_the_widget_is_its_value(page, load):
    load(page, """<label id='l'>Office</label><div class='sel__container'>
      <div><input role='combobox' aria-labelledby='l'></div><input type='hidden' name='office' value='Austin'></div>""")
    assert fields(page)[0]["committed"] == "Austin"


def test_fields_inside_a_grid_are_listed(page, load):
    load(page, "<div role='grid'><div role='row'><div role='gridcell'><label for='c'>Company</label><input id='c'></div></div></div>")
    assert [f["question"] for f in fields(page)] == ["Company"]


def test_named_radios_without_a_container_ask_the_text_before_them(page, load):
    load(page, """<p class='question-label'>Are you 18?</p>
      <label><input type='radio' name='a'>Yes</label><label><input type='radio' name='a'>No</label>""")
    assert [(f["shape"], f["question"]) for f in fields(page)] == [("group", "Are you 18?")]


def test_named_radios_take_plain_preceding_text_and_never_an_option_label(page, load):
    load(page, """<label for='x'>City</label><input id='x'>
      <div><p>Do you need sponsorship?*</p>
        <div><input type='radio' name='sp' id='y'><label for='y'>Yes</label></div>
        <div><input type='radio' name='sp' id='n'><label for='n'>No</label></div></div>
      <div><label><input type='radio' name='q'>Yes</label><label><input type='radio' name='q'>No</label></div>""")
    got = fields(page)
    assert [(f["question"], f["required"]) for f in got[1:]] == [("Do you need sponsorship?", True), ("", False)]


def test_an_unknown_control_is_never_answered(page, load):
    load(page, "<span id='q'>Rate</span><div role='slider' aria-labelledby='q' aria-valuenow='3' tabindex='0'></div>")
    assert [(f["shape"], f["committed"], f["answered"]) for f in fields(page)] == [("unknown", "3", False)]


# ---------- code-quality review fixes ----------


def test_an_engine_click_on_another_member_of_the_busy_group_is_not_the_user(page, load):
    # A synthetic click on a radio fires a TRUSTED change: the exemption is per field.
    load(page, """<fieldset><legend>Q</legend><label><input type='radio' name='q' id='y'>Yes</label>
        <label for='n'>No</label><input type='radio' name='q' id='n'></fieldset>
      <label for='c'>City</label><input id='c'>""")
    fields(page)
    page.evaluate(f"""() => {{ {NS}.fillBusyEl = document.getElementById('y');
        document.querySelector("label[for='n']").dispatchEvent(new MouseEvent('click', {{bubbles: true, cancelable: true}})); }}""")
    page.type("#c", "x")
    assert [(f["question"], f["committed"], f["touched"]) for f in fields(page)] == [
        ("Q", "No", False), ("City", "x", True)]


def test_popup_placeholders_are_not_committed_values(page, load):
    texts = ["Select...", "Select an option", "-- Select --", "Please choose", "Select One ▾", "Choose one…"]
    load(page, "".join(f"<label id='l{i}'>Q{i}</label><button aria-haspopup='listbox' aria-labelledby='l{i}'>{t}</button>"
                       for i, t in enumerate(texts)) + "<label id='v'>Q9</label><button aria-haspopup='listbox' aria-labelledby='v'>Texas ▾</button>")
    got = [(f["committed"], f["answered"]) for f in fields(page)]
    assert got == [("", False)] * len(texts) + [("Texas", True)]


@pytest.mark.parametrize("text, placeholder", [
    # Live iCIMS, 2026-10-01: these showed in boxes Fill read as answered.
    ("— Make a Selection —", True), ("Make a selection", True), ("Please make a selection...", True),
    ("Please select a country", True), ("Select your state", True), ("Choose an option", True),
    ("Select a State/Province", True), ("-- Choose your country --", True), ("… Select …", True),
    ("Select One", True), ("Select...", True), ("", True), ("—", True),
    # A deliberate trade-off: "an article or your, then one or two words" is
    # shape, so these real-sounding answers read as prompts too (rare as an
    # option, and a prompt read as an answer is the worse mistake).
    ("Choose your own adventure", True), ("Select a Plan", True),
    # Real answers that happen to begin with the words.
    ("Select Medical", False), ("Choose Health", False), ("Selective Service", False),
    ("Make a Wish Foundation", False), ("Select Medical Holdings Corporation", False),
    ("Selection committee", False), ("Pick n Save", False), ("Select a career in nursing today", False),
])
def test_the_placeholder_test_knows_a_choose_something_prompt_from_an_answer(page, load, text, placeholder):
    load(page, "<p></p>", sources=["shared/policy.js"])
    assert page.evaluate(f"(t) => {NS}.isPlaceholderText(t)", text) is placeholder


def test_a_select2_box_over_an_empty_hidden_select_is_unanswered_whatever_it_shows(page, load):
    """iCIMS (live 2026-10-01): the shown text is the widget's, the hidden
    select is the app's. A box that shows any words while its select holds
    nothing (or a disabled or valueless option) is not answered."""
    def widget(i, shown, options):
        return (f"<div><label id='l{i}' for='s{i}'>Q{i}</label><select id='s{i}' style='display:none'>{options}</select>"
                f"<span><span role='combobox' aria-haspopup='true' aria-labelledby='l{i}' tabindex='0'>"
                f"<span>{shown}</span></span></span></div>")
    load(page, widget(0, "— Make a Selection —", "<option value=''>— Make a Selection —</option><option value='b'>BS</option>")
         + widget(1, "Nothing yet", "<option value=''>Nothing yet</option><option value='b'>BS</option>")
         + widget(2, "Pick later", "<option value='x' disabled selected>Pick later</option><option value='b'>BS</option>")
         + widget(3, "BS", "<option value=''>—</option><option value='b' selected>BS</option>"))
    got = [(f["shape"], f["question"], f["committed"], f["answered"]) for f in fields(page)]
    assert got == [("popup", "Q0", "", False), ("popup", "Q1", "Nothing yet", False),
                   ("popup", "Q2", "Pick later", False), ("popup", "Q3", "BS", True)]


@pytest.mark.parametrize("value", ["value='-1'", "value='0'", ""], ids=["minus-one", "zero", "no-value-attribute"])
def test_a_backing_select_on_its_placeholder_row_holds_nothing_whatever_its_value(page, load, value):
    """A placeholder row whose value is not empty ("-1", "0", or its text when
    it has no value attribute) is still no answer."""
    load(page, f"<div><label id='l' for='s'>Degree</label><select id='s' style='display:none'>"
               f"<option {value}>Select a degree</option><option value='b'>BS</option></select>"
               "<span><span role='combobox' aria-haspopup='true' aria-labelledby='l' tabindex='0'>"
               "<span>Make your pick</span></span></span></div>")
    assert [(f["committed"], f["answered"]) for f in fields(page)] == [("Make your pick", False)]


# Review of the first cut (2026-10-01): a hidden select counts as a box's
# backing ONLY when the page ties it to the box, never because it is nearby.
def test_a_workday_popup_with_a_backing_input_ignores_a_hidden_follow_up_select(page, load):
    load(page, """<div class='q'><label id='l'>Authorized to work?</label>
      <div><button aria-haspopup='listbox' aria-labelledby='l'>Yes</button><input style='display:none' value='yes-id'></div>
      <div style='display:none'><label>Which visa?</label><select><option value=''>Choose</option>
        <option value='h1'>H1B</option></select></div></div>""")
    assert [(f["committed"], f["answered"]) for f in fields(page)] == [("Yes", True)]


@pytest.mark.parametrize("hidden", ["<div style='display:none'><select>{opts}</select></div>",
                                    "<select style='display:none'>{opts}</select>"],
                         ids=["inside-a-hidden-block", "hidden-itself-but-not-tied"])
def test_a_popup_showing_an_answer_beside_an_unrelated_hidden_select_is_answered(page, load, hidden):
    opts = "<option value=''></option><option value='x'>Other</option>"
    load(page, f"<div class='q'><label id='l'>Degree</label>"
               f"<div><button aria-haspopup='listbox' aria-labelledby='l'>Bachelor's</button></div>"
               f"{hidden.format(opts=opts)}</div>")
    assert [(f["committed"], f["answered"]) for f in fields(page)] == [("Bachelor's", True)]


def test_the_previous_questions_hidden_select_never_backs_the_next_questions_box(page, load):
    """Re-review probe: a select right before the NEXT question's wrapper is
    not that wrapper's widget (it holds its own label): its box keeps its answer."""
    opts = "<option value=''></option><option value='x'>Other</option>"
    load(page, f"""<div class='form'>
      <label>Visa type</label><select id='v' style='display:none'>{opts}</select>
      <div class='q2'><label id='l'>Degree</label><div><button aria-haspopup='listbox' aria-labelledby='l'>Bachelor's</button></div></div>
      </div>""")
    assert [(f["question"], f["committed"], f["answered"]) for f in fields(page)] == [("Degree", "Bachelor's", True)]


def test_a_visible_select_marked_aria_hidden_is_still_a_field(page, load):
    """aria-hidden alone hides nothing on screen: a usable select beside a
    popup stays a field of its own, and the popup's answer stands."""
    load(page, """<div><label for='s'>Country</label><select id='s' aria-hidden='true'>
      <option value=''></option><option value='x'>Other</option></select>
      <span><button aria-haspopup='listbox' aria-label='State'>Texas</button></span></div>""")
    assert [(f["shape"], f["question"], f["committed"], f["answered"]) for f in fields(page)] == [
        ("select", "Country", "", False), ("popup", "State", "Texas", True)]


def test_real_select2_hiding_is_one_field_not_two(page, load):
    """select2 hides its select with a 1px clip (`select2-hidden-accessible`),
    which counts as visible: tied to the box, it is the box's backing, never a
    field of its own (two fields would be two writes)."""
    load(page, """<div><label id='l' for='s'>Degree</label>
      <select id='s' class='select2-hidden-accessible' aria-hidden='true' tabindex='-1'
        style='border:0;clip:rect(0 0 0 0);height:1px;margin:-1px;overflow:hidden;padding:0;position:absolute;width:1px'>
        <option value=''>— Make a Selection —</option><option value='b'>BS</option></select>
      <span class='select2-container'><span role='combobox' aria-haspopup='true' aria-labelledby='l' tabindex='0'>
        <span>— Make a Selection —</span></span></span></div>""")
    assert [(f["shape"], f["question"], f["committed"], f["answered"]) for f in fields(page)] == [
        ("popup", "Degree", "", False)]
    page.evaluate("() => { document.getElementById('s').value = 'b'; }")
    assert [f["answered"] for f in fields(page)] == [True]


def test_a_clipped_select_no_box_names_is_still_a_field(page, load):
    load(page, """<label for='s'>Degree</label><select id='s' aria-hidden='true'
        style='clip:rect(0 0 0 0);height:1px;overflow:hidden;position:absolute;width:1px'>
        <option value=''></option><option value='b'>BS</option></select>""")
    assert [(f["shape"], f["question"]) for f in fields(page)] == [("select", "Degree")]


def test_a_rerendered_field_never_takes_a_deleted_fields_fid(page, load):
    load(page, """<div class='job'><h3>Job</h3><label for='a'>Job Title</label><input id='a'></div>
       <div class='job'><h3>Job</h3><label for='b'>Job Title</label><input id='b'></div>""")
    first, second = (f["fid"] for f in fields(page))
    page.evaluate("() => document.querySelector('.job').remove()")
    assert [f["fid"] for f in fields(page)] == [second]
    page.evaluate("() => { const o = document.getElementById('b'); o.replaceWith(o.cloneNode(true)); }")
    assert [f["fid"] for f in fields(page)] == [second]
    assert page.evaluate(f"(fid) => {INV}.resolve(fid)", first) is None


def test_two_fields_never_share_a_fid_in_one_pass(page, load):
    load(page, """<div><fieldset id='fs'><legend>Pick</legend><label><input type='checkbox'>Alpha</label>
      <label><input type='checkbox'>Beta</label></fieldset></div>""")
    assert len(fields(page)) == 1
    page.evaluate("() => { const fs = document.getElementById('fs'); fs.querySelector('legend').remove(); fs.replaceWith(...fs.childNodes); }")
    got = fields(page)
    assert [f["question"] for f in got] == ["Alpha", "Beta"] and got[0]["fid"] != got[1]["fid"]


def test_resolve_relists_at_most_once_per_dom_change_and_remembers_dead_fids(page, load):
    load(page, "".join(f"<label for='t{i}'>T{i}</label><input id='t{i}'>" for i in range(10)))
    fids = [f["fid"] for f in fields(page)]
    page.evaluate(f"""() => {{ window.calls = 0; const inv = {INV}; const real = inv.list;
        inv.list = (...a) => {{ window.calls += 1; return real(...a); }}; }}""")
    page.evaluate("() => document.querySelectorAll('input').forEach((i) => i.remove())")
    assert page.evaluate(f"(fids) => fids.map((f) => {INV}.resolve(f))", fids) == [None] * 10
    assert page.evaluate("window.calls") == 1
    assert page.evaluate(f"(fids) => fids.map((f) => {INV}.resolve(f))", fids) == [None] * 10
    assert page.evaluate("window.calls") == 1


def test_consent_options_are_flagged_and_an_all_consent_group_is_blocked(page, load):
    load(page, """<fieldset><legend>Acknowledgements</legend>
      <label><input type='checkbox' name='ack'>I certify that my answers are true</label>
      <label><input type='checkbox' name='ack'>I agree to the privacy policy</label></fieldset>
      <fieldset><legend>Final step</legend>
      <label><input type='checkbox'>I agree to the terms of service</label>
      <label><input type='checkbox'>Send me job alerts</label></fieldset>""")
    ack, final = fields(page)
    assert [o["policyBlocked"] for o in ack["options"]] == [True, True] and ack["policyBlocked"] is True
    assert page.evaluate(f"(fid) => {INV}.isBlocked(fid)", ack["fid"]) is True
    assert [o["policyBlocked"] for o in final["options"]] == [True, False] and final["policyBlocked"] is False
    ack, final = fields(page, consent_forms=True)
    assert ack["policyBlocked"] is False and not any(o["policyBlocked"] for o in final["options"])


def test_a_readonly_combobox_input_is_a_popup(page, load):
    load(page, """<label for='x'>Degree</label><div class='ant-select'><div class='ant-select-selector'>
      <input id='x' role='combobox' readonly aria-haspopup='listbox' aria-expanded='false'>
      <span class='ant-select-selection-placeholder'>Select</span></div></div>""")
    assert [(f["shape"], f["question"], f["committed"]) for f in fields(page)] == [("popup", "Degree", "")]
    assert page.evaluate(f"(fid) => {INV}.shapeOf(fid).open", fields(page)[0]["fid"]) == "press"


def test_a_div_button_with_a_popup_is_a_popup(page, load):
    load(page, """<label id='lab'>Degree</label><div role='button' aria-haspopup='listbox' aria-labelledby='lab' tabindex='0'>&#8203;</div>
      <input aria-hidden='true' tabindex='-1' style='opacity:0;position:absolute' value=''>""")
    assert [(f["shape"], f["question"], f["answered"]) for f in fields(page)] == [("popup", "Degree", False)]


def test_a_select_without_a_placeholder_is_answered_only_when_chosen(page, load):
    load(page, """<label for='s'>How did you hear about us?</label><select id='s'><option>Career fair</option><option>LinkedIn</option></select>
      <label for='t'>Referral source</label><select id='t'><option selected>Career fair</option><option>LinkedIn</option></select>
      <label for='u'>Other source</label><select id='u'><option>Career fair</option><option>LinkedIn</option></select>""")
    page.select_option("#u", "LinkedIn")
    assert [f["answered"] for f in fields(page)] == [False, True, True]


def test_a_date_is_answered_only_when_every_section_is_there(page, load):
    load(page, """<fieldset><legend>From</legend><div data-automation-id='dateInputWrapper'>
        <input data-automation-id='dateSectionMonth-input' role='spinbutton' aria-label='Month' id='m' value='5'>
        <input data-automation-id='dateSectionYear-input' role='spinbutton' aria-label='Year' id='y'></div></fieldset>""")
    assert fields(page)[0]["answered"] is False
    page.evaluate("() => { document.getElementById('y').value = '2021'; }")
    assert [(f["committed"], f["answered"]) for f in fields(page)] == [("2021-05", True)]


def test_consent_forms_default_to_off_on_every_list(page, load):
    load(page, "<label><input type='checkbox'>I certify that the above is true</label>")
    assert fields(page, consent_forms=True)[0]["policyBlocked"] is False
    assert page.evaluate(f"() => {INV}.list().fields[0].policyBlocked") is True


def test_header_and_nav_controls_are_not_fields(page, load):
    load(page, """<header><button aria-haspopup='menu' aria-label='Account menu'></button></header>
      <nav><button aria-haspopup='true'>English</button></nav><div role='banner'><input aria-label='Search jobs'></div>
      <main><label for='n'>Name</label><input id='n'></main>""")
    assert [f["question"] for f in fields(page)] == ["Name"]


def test_a_headless_ui_combobox_is_one_search_field(page, load):
    load(page, """<label id='cl'>Office</label><div><input role='combobox' aria-labelledby='cl' aria-controls='lb' aria-expanded='false'>
      <button aria-haspopup='listbox' aria-labelledby='cl' aria-expanded='false'>v</button></div>""")
    assert [(f["shape"], f["question"]) for f in fields(page)] == [("search", "Office")]


def test_autocomplete_none_is_text_and_free_text_autocomplete_reads_its_value(page, load):
    load(page, """<label for='t'>Nickname</label><input id='t' aria-autocomplete='none' value='Bob'>
      <label for='loc'>Location (City)</label><input id='loc' aria-autocomplete='list' role='combobox' value='Austin, TX'>""")
    assert [(f["shape"], f["committed"]) for f in fields(page)] == [("text", "Bob"), ("search", "Austin, TX")]


def test_fields_come_in_document_order_with_shadow_fields_in_place(page, load):
    load(page, "<label for='a'>A</label><input id='a'><div id='host'></div><label for='c'>C</label><input id='c'>")
    page.evaluate("""() => { document.getElementById('host').attachShadow({mode: 'open'})
        .innerHTML = "<label for='b'>B</label><input id='b'>"; }""")
    assert [f["question"] for f in fields(page)] == ["A", "B", "C"]


def test_two_unwrapped_date_widgets_under_one_parent_stay_two_fields(page, load):
    load(page, """<div><label for='m'>From</label>
      <input data-automation-id='dateSectionMonth-input' id='m' value='01'><input data-automation-id='dateSectionYear-input' value='2020'>
      <input data-automation-id='dateSectionMonth-input' aria-label='To month' value='12'><input data-automation-id='dateSectionYear-input' value='2022'></div>""")
    assert [(f["shape"], f["committed"]) for f in fields(page)] == [("date", "2020-01"), ("date", "2022-12")]


def test_shape_readers_do_not_depend_on_this(page, load):
    load(page, fixture_html("workday_search.html"))
    got = page.evaluate(f"""() => {{ const read = {NS}.shapes.byName('search').read;
        return read(document.getElementById('skills')); }}""")
    assert got == ["SQL"]


def test_aria_haspopup_noise_is_not_listed(page, load):
    load(page, """<label for='n'>Name</label><input id='n'>
      <span aria-haspopup='dialog' tabindex='0'>?</span><a href='#h' aria-haspopup='true'>Help</a>
      <div role='button' aria-haspopup='false' tabindex='0'>More</div>
      <label id='d'>Degree</label><div role='button' aria-haspopup='listbox' aria-labelledby='d' tabindex='0'>Select</div>""")
    assert [(f["shape"], f["question"]) for f in fields(page)] == [("text", "Name"), ("popup", "Degree")]


# The peek after a commit (inventory.peek) must name exactly the fids a full
# pass lists, or every commit on such a page would cost a needless re-inventory.
ARIA_RADIOS = """<span id='g'>Preferred contact</span><div role='radiogroup' aria-labelledby='g'>
  <div role='radio' aria-checked='false' tabindex='0'>Email</div><div role='radio' aria-checked='false'>Phone</div></div>"""


@pytest.mark.parametrize("html", [
    *(fixture_html(n) for n in ("workday_sections.html", "workday_listbox.html", "native.html", "workday_date.html",
                                "workday_search.html", "react_select.html", "popup_with_search.html",
                                "workday_text.html")),
    ARIA_RADIOS,
], ids=["sections", "listbox", "native-radios", "date", "search", "react-select", "popup-search", "text", "aria-radios"])
def test_a_peek_names_the_fids_a_full_pass_lists_on_an_unchanged_page(page, load, html):
    load(page, html)
    listed = sorted(f["fid"] for f in fields(page))
    assert listed and sorted(page.evaluate(f"() => {INV}.peek()")) == listed


def test_a_placeholder_row_does_not_hide_that_every_answer_is_never_fill(page, load):
    """Every real option is an attestation; a dash row among them is no answer,
    so it cannot make the field look fillable."""
    load(page, """<label for='s'>Your statement</label><select id='s'>
      <option>I certify that the above is true</option><option>—</option></select>""")
    assert by_question(page)["Your statement"]["policyBlocked"] is True


def test_gem_fields_read_their_questions_and_group_nameless_radios(page, load):
    """Live Gem (jobs.gem.com, 2026-09-27; fixtures/browser/gem_form.html): a
    bare text box labelled by a hashed-class span above its wrappers, and
    Yes/No radios with no name and no container, asked by a span five
    ancestors up."""
    load(page, fixture_html("gem_form.html"))
    got = fields(page)
    assert [(f["shape"], f["question"], f["required"]) for f in got] == [
        ("text", "First name", True), ("text", "Last name", True), ("text", "Email", True),
        ("text", "LinkedIn URL", False),
        ("group", "Are you graduating in 2027?", True),
        ("group", "Is your degree in Computer Science?", True)]
    assert [[o["text"] for o in f["options"]] for f in got[4:]] == [["Yes", "No"], ["Yes", "No"]]


def test_nameless_radios_outside_any_container_are_one_group(page, load):
    load(page, "<div><p class='q-1'>Willing to travel?</p><div><div><input type='radio' id='y'><label for='y'>Yes</label></div>"
               "<div><input type='radio' id='n'><label for='n'>No</label></div></div></div>")
    got = fields(page)
    assert [(f["shape"], f["question"], [o["text"] for o in f["options"]]) for f in got] == [
        ("group", "Willing to travel?", ["Yes", "No"])]


def test_nameless_radios_beside_another_kind_of_field_are_not_pulled_into_a_group(page, load):
    """The group is the nearest ancestor holding nameless radios and nothing
    else: a text box between two questions keeps them apart."""
    load(page, "<div><div><p>Relocate?</p><input type='radio' id='r'><label for='r'>Yes</label></div>"
               "<label for='t'>City</label><input id='t'>"
               "<div><p>Travel?</p><input type='radio' id='v'><label for='v'>Yes</label></div></div>")
    assert [(f["shape"], f["question"]) for f in fields(page)] == [
        ("group", "Relocate?"), ("text", "City"), ("group", "Travel?")]


def test_nameless_checkboxes_stay_lone(page, load):
    """Only radios group by their container: two nameless boxes are two
    yes/no answers, each asking its own label."""
    load(page, "<div><div><input type='checkbox' id='a'><label for='a'>Email me updates</label></div>"
               "<div><input type='checkbox' id='b'><label for='b'>Text me updates</label></div></div>")
    assert [(f["question"], f["multi"]) for f in fields(page)] == [
        ("Email me updates", False), ("Text me updates", False)]



# Review of the first cut (reviewer probes, 2026-09-28).
def summary(page):
    return [(f["question"], [o["text"] for o in f["options"]]) for f in fields(page)]


@pytest.mark.parametrize("html, want", [
    ("<p>Intro to the application</p><div role=radiogroup aria-label='Willing to relocate?'>"
     "<input type=radio name=q id=y><span>Yes</span><input type=radio name=q id=n><span>No</span></div>",
     [("Willing to relocate?", ["", ""])]),
    ("<span id=qq>Willing to relocate?</span><div role=radiogroup aria-labelledby=qq><div><input type=radio name=q>"
     "<span>Yes</span></div><div><input type=radio name=q><span>No</span></div></div>",
     [("Willing to relocate?", ["", ""])]),
    ("<div><span>Willing to relocate?</span><input type=radio name=q id=y><span>Yes</span>"
     "<input type=radio name=q id=n><span>No</span></div>",
     [("Willing to relocate?", ["", ""])]),
    ("<div><p>Willing to relocate?</p><div><input type=radio name=q id=y><span>Yes</span></div>"
     "<div><input type=radio name=q id=n><span>No</span></div></div>",
     [("Willing to relocate?", ["", ""])]),
    ("<div><span>Languages</span><input type=checkbox name=l><span>Python</span>"
     "<input type=checkbox name=l><span>Java</span><input type=checkbox name=l><span>Go</span></div>",
     [("Languages", ["", "", ""])]),
    ("<div><p>By applying you agree we may run a background check.</p>"
     "<div><input type=checkbox id=c><span>Send me job alerts</span></div></div>",
     [("", ["Yes", "No"])]),
], ids=["radiogroup", "labelledby-group", "flat-radios", "wrapped-radios", "flat-checkboxes", "lone-checkbox"])
def test_options_labelled_after_them_are_never_shifted_onto_their_neighbours_text(page, load, html, want):
    """An option whose label is an unassociated span AFTER it reads no text —
    never the text before it (the question, or the previous option's label)."""
    load(page, html)
    assert summary(page) == want


def test_two_nameless_questions_under_one_wrapper_are_two_groups(page, load):
    load(page, "<div><span>Need sponsorship?</span>"
               "<div><input type=radio id=a><label for=a>Yes</label></div><div><input type=radio id=b><label for=b>No</label></div>"
               "<span>Over 18?</span>"
               "<div><input type=radio id=c><label for=c>Yes</label></div><div><input type=radio id=d><label for=d>No</label></div></div>")
    assert summary(page) == [("Need sponsorship?", ["Yes", "No"]), ("Over 18?", ["Yes", "No"])]


def test_nameless_radios_with_repeated_option_texts_are_never_merged(page, load):
    """Nothing but the repeat tells the two questions apart: no group may
    hold two options that read the same."""
    load(page, "<div><span>Questions</span>" + "".join(
        f"<div><input type=radio id={i}><label for={i}>{t}</label></div>"
        for i, t in (("a", "Yes"), ("b", "No"), ("c", "Yes"), ("d", "No"))) + "</div>")
    for _, options in summary(page):
        assert len(options) == len(set(options)), options


def test_a_group_deep_under_an_intro_paragraph_asks_nothing(page, load):
    """A named group with no container, six wrappers under a heading and an
    intro sentence: the sentence is no question."""
    load(page, "<div><h2>Voluntary Self-Identification</h2><p>Completion of this form is voluntary and will not "
               "affect your application.</p>" + "<div>" * 6 + "<label><input type=radio name=v>I am a protected veteran"
               "</label><label><input type=radio name=v>I am not a protected veteran</label>" + "</div>" * 7)
    assert [(f["question"], f["source"]) for f in fields(page)] == [("", None)]


def test_a_group_asked_by_the_text_before_it_reports_the_preceding_source(page, load):
    load(page, fixture_html("gem_form.html"))
    assert {f["source"] for f in fields(page) if f["shape"] == "group"} == {"preceding"}


def _work_entry(n, hidden=False):
    return (f"<div role=group aria-labelledby=we{n}{' hidden' if hidden else ''}><h4 id=we{n}>Work Experience {n}</h4>"
            f"<label for=t{n}>Job Title</label><input id=t{n}>"
            f"<div><input type=checkbox name=currentlyWorkHere id=c{n}><label for=c{n}>I currently work here</label>"
            "</div></div>")


@pytest.mark.parametrize("prototype", [False, True], ids=["two-entries", "hidden-prototype"])
def test_same_name_checkboxes_in_separate_entries_are_each_their_own_box(page, load, prototype):
    """Live Workday (CarMax, 2026-09-30) names every entry's "I currently work
    here" box `currentlyWorkHere`: a checkbox's same-name members are its own
    group's, never a set spanning entries asked by the entry's title."""
    load(page, "<div role=group aria-label='Work Experience'>" + (_work_entry(0, hidden=True) if prototype else "")
         + _work_entry(1) + _work_entry(2) + "</div>")
    boxes = [f for f in fields(page) if f["shape"] == "group"]
    assert [(f["question"], [o["text"] for o in f["options"]], f["multi"], f["repeatIndex"]) for f in boxes] == [
        ("I currently work here", ["Yes", "No"], False, 0), ("I currently work here", ["Yes", "No"], False, 1)]


def test_a_named_set_whose_boxes_each_sit_in_their_own_group_splits_into_lone_boxes(page, load):
    """KNOWN LIMIT, pinned as it stands: a checkbox's same-name members stop at
    its nearest grouping container (for Workday's per-entry "I currently work
    here"), so a named multi-select whose every box is wrapped in its own
    role=group reads as one lone yes/no box per option, not one set."""
    load(page, "<fieldset><legend>Which days can you work?</legend>" + "".join(
        f"<div role=group><input type=checkbox name=days id={d}><label for={d}>{d}</label></div>"
        for d in ("Monday", "Tuesday")) + "</fieldset>")
    assert [(f["question"], f["multi"], [o["text"] for o in f["options"]]) for f in fields(page)] == [
        ("Monday", False, ["Yes", "No"]), ("Tuesday", False, ["Yes", "No"])]


# ---------- a group asked by the paragraph before it (iCIMS VEVRAA, 2026-10-01) ----------
#
# The veteran self-identification block asks in a numbered paragraph ("2. If
# you believe you belong to … please indicate by checking the appropriate box
# below. As a Government contractor …") and then lists three radios. A
# paragraph is no label, so the group read as "A field with no label" and was
# left. The paragraph's sentence that ASKS for the choice below is the
# question; an intro that asks nothing is still none.

VEVRAA_ASK = ("If you believe you belong to any of the categories of protected veterans listed above, "
              "please indicate by checking the appropriate box below.")


def test_a_radio_group_asked_by_the_paragraph_before_it_takes_that_sentence(page, load):
    load(page, f"""<p>Protected veterans may have additional rights under USERRA.</p>
      <p>2. {VEVRAA_ASK} As a Government contractor subject to VEVRAA, we request this information.</p>
      <input type='radio' name='v' id='v1'><label for='v1'>I IDENTIFY AS ONE OR MORE OF THE CLASSIFICATIONS</label>
      <input type='radio' name='v' id='v2'><label for='v2'>I AM NOT A PROTECTED VETERAN</label>
      <input type='radio' name='v' id='v3'><label for='v3'>I DON'T WISH TO ANSWER</label>""")
    assert [(f["shape"], f["question"]) for f in fields(page)] == [("group", VEVRAA_ASK)]


@pytest.mark.parametrize("paragraph", [
    "Please answer every question below honestly.",
    "Submission of this information is voluntary and refusal will not subject you to adverse treatment.",
])
def test_a_paragraph_that_asks_for_no_choice_is_still_no_question(page, load, paragraph):
    load(page, f"""<p>{paragraph}</p>
      <label><input type='radio' name='a'>Yes</label><label><input type='radio' name='a'>No</label>""")
    assert [f["question"] for f in fields(page)] == [""]


# ---------- a follow-up box carries the question it follows ----------
#
# "If applicable, please provide info." under "How did you hear about this
# opportunity?" (iCIMS, 2026-10-01) asks nothing alone, so /map sent it to
# free text and it was left. The question before it, and the answer the page
# shows for it, go in front.

@pytest.mark.parametrize("html, question", [
    # the question and its shown answer are text, not a control
    ("<p>How did you hear about this opportunity?</p><p>Job Board (Indeed/Glassdoor)</p>"
     "<label for=a>If applicable, please provide info.</label><input id=a>",
     "How did you hear about this opportunity? Job Board (Indeed/Glassdoor) — If applicable, please provide info."),
    # the question is the previous field's
    ("<label for=h>How did you hear about us?</label><select id=h><option>Other</option></select>"
     "<label for=a>If other, please specify</label><input id=a>",
     "How did you hear about us? — If other, please specify"),
    # a label that asks on its own is left as it is
    ("<p>How did you hear about this opportunity?</p><label for=a>Referrer's name</label><input id=a>",
     "Referrer's name"),
], ids=["shown-answer", "previous-field", "not-a-follow-up"])
def test_a_follow_up_box_carries_the_question_it_follows(page, load, html, question):
    load(page, html)
    got = page.evaluate("sel => window.careerStudioCompanion.readField(document.querySelector(sel))", "#a")
    assert got["question"] == question


# iCIMS's VEVRAA form as it is really built (live, 2026-10-02): text and <br>
# straight in a table cell. The question and every option's label are BARE
# TEXT NODES beside the controls, so the group read as no question with three
# blank options.
ICIMS_VEVRAA = f"""<form><table><tbody><tr><td><span style='font-size: 13px'>
  <span style='font-size: 13px'>Protected veterans may have additional rights under USERRA. For more
  information, call the U.S. Department of Labor.</span>
  <span style='font-size: 13px'><br>2. {VEVRAA_ASK} As a Government contractor subject to VEVRAA, we request this
  information in order to measure the effectiveness of the outreach.<br><br>
  <span class='iCIMS_Forms_RadioGroup form-control'><input type='radio' name='v' value='1'></span>
  I IDENTIFY AS ONE OR MORE OF THE CLASSIFICATIONS OF PROTECTED VETERAN LISTED ABOVE<br><br>
  <span class='iCIMS_Forms_RadioGroup form-control'><input type='radio' name='v' value='2'></span>
  I AM NOT A PROTECTED VETERAN<br><br>
  <span class='iCIMS_Forms_RadioGroup form-control'><input type='radio' name='v' value='3'></span>
  I DON'T WISH TO ANSWER<br><br></span>
</span></td></tr></tbody></table></form>"""


def test_icims_vevraa_bare_text_question_and_options_are_read(page, load):
    load(page, ICIMS_VEVRAA)
    [group] = fields(page)
    assert (group["shape"], group["question"]) == ("group", VEVRAA_ASK)
    assert [o["text"] if isinstance(o, dict) else o for o in group["options"]] == [
        "I IDENTIFY AS ONE OR MORE OF THE CLASSIFICATIONS OF PROTECTED VETERAN LISTED ABOVE",
        "I AM NOT A PROTECTED VETERAN", "I DON'T WISH TO ANSWER"]


@pytest.mark.parametrize("html", [
    # an element after the box is not bare text: nothing new is read
    "<p>Intro to the application</p><input type=radio name=q id=a><span>Yes</span>",
    # bare text after a box that is not a choice is no option label
    "<div><input id=a> per hour</div>",
], ids=["element-after", "not-a-choice"])
def test_bare_text_is_read_only_beside_a_choice(page, load, html):
    load(page, html)
    got = page.evaluate("sel => window.careerStudioCompanion.readField(document.querySelector(sel))", "#a")
    assert got["question"] == ""


# iCIMS's disability form (CC-305, live 2026-10-02): a one-column layout table
# whose question, "Please check one of the boxes below:", is the ROW ABOVE the
# radios' row. A layout row's question may be the nearest earlier one-cell row
# with text and no field; a grid's header row never is.
DISABILITY_OPTIONS = ["Yes, I have a disability, or have had one in the past",
                      "No, I do not have a disability and have not had one in the past",
                      "I do not want to answer"]
ICIMS_CC305 = f"""<form><table style='width: 100%' cellspacing='0' cellpadding='5'><tbody>
  <tr><td colspan='3'><b>How do you know if you have a disability?</b></td></tr>
  <tr><td colspan='3'>A disability is a condition that substantially limits one or more major life activities.
    <ul><li>Diabetes</li><li>Epilepsy</li></ul></td></tr>
  <tr><td colspan='3'><hr></td></tr>
  <tr><td colspan='3'><b>Please check one of the boxes below:</b></td></tr>
  <tr><td colspan='3' valign='top' width='100%'>
    <span style='font-size: 13px'><span class='iCIMS_Forms_RadioGroup'><input type='radio' name='d' value='1'></span>
      {DISABILITY_OPTIONS[0]}<br></span>
    <span style='font-size: 13px'><span class='iCIMS_Forms_RadioGroup'><input type='radio' name='d' value='2'></span>
      {DISABILITY_OPTIONS[1]}<br></span>
    <span style='font-size: 13px'><span class='iCIMS_Forms_RadioGroup'><input type='radio' name='d' value='3'></span>
      {DISABILITY_OPTIONS[2]}<br><br>PUBLIC BURDEN STATEMENT: According to the Paperwork Reduction Act of 1995 no
      persons are required to respond.<br></span>
  </td></tr>
</tbody></table></form>"""


def test_icims_cc305_group_takes_the_layout_row_above(page, load):
    load(page, ICIMS_CC305)
    [group] = fields(page)
    assert (group["shape"], group["question"]) == ("group", "Please check one of the boxes below:")
    assert [o["text"] if isinstance(o, dict) else o for o in group["options"]] == DISABILITY_OPTIONS


def test_a_grid_header_row_is_never_a_groups_question(page, load):
    load(page, """<table><tr><th>Shift</th><th>Choice</th></tr>
      <tr><td colspan='2'><label><input type='radio' name='s'>Yes</label>
      <label><input type='radio' name='s'>No</label></td></tr></table>""")
    assert [f["question"] for f in fields(page)] == [""]
