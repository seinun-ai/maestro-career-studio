import pytest

READ = "sel => window.careerStudioCompanion.readField(document.querySelector(sel))"


@pytest.mark.parametrize(
    "html, expected, source",
    [
        ("<label for='a'>First name</label><input id='a'>", "First name", "label-for"),
        ("<label>Last name <input id='a'></label>", "Last name", "label-wrap"),
        ("<span id='l1'>Preferred</span><span id='l2'>shift</span><input id='a' aria-labelledby='l1 l2'>",
         "Preferred shift", "labelledby"),
        ("<input id='a' aria-label='Postal code'>", "Postal code", "aria-label"),
        ("<label for='a'>Ci​ty</label><input id='a'>", "Ci ty", "label-for"),
    ],
)
def test_the_question_comes_from_the_strongest_source(page, load, html, expected, source):
    load(page, html)
    got = page.evaluate(READ, "#a")
    assert (got["question"], got["source"]) == (expected, source)


def test_a_workday_dropdown_labelled_only_by_its_value_asks_its_legend(page, load):
    q = "Are you legally authorized to work in the country where this role is located?"
    load(page, f"<fieldset><legend>{q}</legend><button id='a' aria-haspopup='listbox' "
               f"aria-label=' Select One Required'>Select One</button></fieldset>")
    assert page.evaluate(READ, "#a")["question"] == q


@pytest.mark.parametrize("label", [" Select One Required", "Select... Required", "-- Select -- Required",
                                   "Please choose an option Required"])
def test_a_static_placeholder_label_after_a_pick_still_asks_its_legend(page, load, label):
    """A widget that never updates its aria-label once a value is picked: what
    is left after the value and "Required" is placeholder text, not a question."""
    load(page, f"<fieldset><legend>Are you authorized?</legend><button id='a' aria-haspopup='listbox' "
               f"aria-label='{label}'>Yes</button></fieldset>")
    got = page.evaluate(READ, "#a")
    assert (got["question"], got["source"], got["required"]) == ("Are you authorized?", "legend", True)


def test_a_dropdown_that_names_its_question_keeps_it(page, load):
    load(page, "<fieldset><legend>Address</legend><button id='a' aria-haspopup='listbox' "
               "aria-label='State Select One Required'>Select One</button></fieldset>")
    got = page.evaluate(READ, "#a")
    assert (got["question"], got["source"], got["required"]) == ("State", "aria-label", True)


@pytest.mark.parametrize(
    "label, value, question",
    [
        ("Other languages Other Required", "Other", "Other languages"),
        ("Is a visa required to work here? Select One Required", "Select One", "Is a visa required to work here?"),
        ("Country Required", "Select One", "Country"),
        ("Country United States Required", "United States<span>▾</span>", "Country"),
    ],
)
def test_only_the_trailing_value_and_required_are_stripped_from_a_dropdown_label(page, load, label, value, question):
    load(page, f"<button id='a' aria-haspopup='listbox' aria-label='{label}'>{value}</button>")
    got = page.evaluate(READ, "#a")
    assert (got["question"], got["required"]) == (question, True)


def test_a_nearby_label_is_the_closest_one_before_the_field(page, load):
    load(page, "<div class='row'><div class='label'>Phone</div><input id='p'>"
               "<div class='label'>Email</div><input id='e'><input id='x'></div>")
    assert [page.evaluate(READ, s)["question"] for s in ("#p", "#e", "#x")] == ["Phone", "Email", ""]


def test_labelledby_resolves_inside_an_open_shadow_root(page, load):
    load(page, "<div id='host'></div>")
    page.evaluate("""() => { const r = document.getElementById('host').attachShadow({mode: 'open'});
      r.innerHTML = "<span id='q'>Years of experience</span><input id='a' aria-labelledby='q'>"; }""")
    got = page.evaluate("() => window.careerStudioCompanion.readField("
                        "document.getElementById('host').shadowRoot.getElementById('a'))")
    assert got["question"] == "Years of experience"


def test_section_repeat_index_required_and_help(page, load):
    load(page, """
      <section><h3>Work Experience 1</h3><label for='t1'>Job Title*</label><input id='t1'></section>
      <section><h3>Work Experience 2</h3><label for='t2'>Job Title</label>
        <input id='t2' aria-required='true' aria-describedby='h'><p id='h'>As on your offer letter</p></section>""")
    a, b = page.evaluate(READ, "#t1"), page.evaluate(READ, "#t2")
    assert (a["question"], a["required"], a["repeatIndex"]) == ("Job Title", True, 0)
    assert (b["section"], b["repeatIndex"], b["required"], b["help"]) == (
        "Work Experience 2", 1, True, "As on your offer letter")


def test_a_step_counter_is_not_a_repeat_number(page, load):
    load(page, """<section><h2>Step 2 of 4</h2><label for='a'>City</label><input id='a'></section>
      <section><h3>Work Experience 2</h3><label for='b'>Job Title</label><input id='b'></section>""")
    assert [page.evaluate(READ, s)["repeatIndex"] for s in ("#a", "#b")] == [0, 1]


def test_a_label_after_its_checkbox_is_read(page, load):
    load(page, "<div class='row'><div class='c'><input type='checkbox' id='a'><div class='checkbox-label'>I agree to the terms</div></div>"
               "<div class='c'><input type='checkbox' id='b'><div class='checkbox-label'>Send me updates</div></div></div>")
    assert [page.evaluate(READ, s)["question"] for s in ("#a", "#b")] == ["I agree to the terms", "Send me updates"]


def test_an_h6_sub_label_inside_an_entry_is_not_its_section(page, load):
    """Section names come from h1–h5: an <h6> sub-label ("Dates") inside
    "Work Experience 2" must not become the field's section, or its repeat
    index falls to 0 and entry 2 is paired with the first job."""
    load(page, "<div><h4>Work Experience 2</h4><h6>Dates</h6><input id='a' aria-label='From'></div>")
    got = page.evaluate(READ, "#a")
    assert (got["section"], got["repeatIndex"]) == ("Work Experience 2", 1)
