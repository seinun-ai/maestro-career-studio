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
        ("popup", "How did you hear about us?", ""),
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
    assert by_q["Type to Add Skills"]["committed"] == ["SQL"]
    assert by_q["Highest degree"]["answered"] is False
    assert by_q["Are you 18 or older?"]["answered"] is False
    assert by_q["School or University"]["committed"] == ""


def test_an_aria_1_1_combobox_wrapper_is_its_input_not_a_second_field(page, load):
    load(page, """<label id='l'>Office</label>
      <div role='combobox' aria-labelledby='l'><input aria-labelledby='l'></div>""")
    assert [(f["shape"], f["question"]) for f in fields(page)] == [("search", "Office")]
