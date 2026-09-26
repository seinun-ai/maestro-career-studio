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
                      "touched", "policyBlocked"}
    assert (f["kind"], f["source"], f["required"], f["help"]) == ("text", "label-for", True, "As on your ID")


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
