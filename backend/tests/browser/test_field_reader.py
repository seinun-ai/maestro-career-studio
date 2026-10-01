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


# The "preceding" source: the last resort, for a box nothing names (Gem, live
# 2026-09-27 — fixtures/browser/gem_form.html): the text just before the box's
# wrapper chain, whatever its classes.
def wrapped(inner, n=3):
    return "<div class='a1x'>" * n + inner + "</div>" * n


def test_an_unassociated_sibling_span_three_wrappers_up_is_the_label(page, load):
    load(page, f"<div class='flex-30'><span class='bodyImportant-47'>First name<span class='req-76'>*</span></span>"
               f"{wrapped('<input id=a type=text>')}</div>")
    got = page.evaluate(READ, "#a")
    assert (got["question"], got["source"], got["required"]) == ("First name", "preceding", True)


def test_hidden_preceding_text_is_never_the_label(page, load):
    load(page, "<div><span class='t-1'>Last name</span><span class='e-2' style='display:none'>This field is required</span>"
               f"{wrapped('<input id=a>')}</div>"
               "<div><span class='t-1' style='visibility:hidden'>Hidden helper</span>"
               f"{wrapped('<input id=b>')}</div>")
    assert [page.evaluate(READ, s)["question"] for s in ("#a", "#b")] == ["Last name", ""]


def test_a_preceding_sibling_holding_another_control_ends_the_search(page, load):
    load(page, f"<div><span class='t-1'>Phone</span><div><input id=o></div>{wrapped('<input id=a>', 2)}</div>")
    assert page.evaluate(READ, "#a")["question"] == ""


def test_the_climb_stops_at_an_ancestor_holding_another_field(page, load):
    load(page, f"<span class='t-1'>Name</span><div>{wrapped('<input id=a>', 2)}<input id=b></div>")
    assert page.evaluate(READ, "#a")["question"] == ""


@pytest.mark.parametrize("heading", ["<h3>Contact</h3>", "<div class='hdr-9'><h3>Contact information</h3></div>"],
                         ids=["direct", "wrapped"])
def test_a_heading_before_the_box_is_neither_its_label_nor_a_way_past(page, load, heading):
    """A section heading is no field's label, and the text above it belongs to
    something else (a job description, the previous section) — wrapped in a
    div or not."""
    load(page, f"<span class='x'>Your details</span><section>{heading}{wrapped('<input id=a placeholder=Phone>')}</section>")
    assert page.evaluate(READ, "#a")["question"] == ""


def test_every_other_source_still_comes_first(page, load):
    load(page, "<div><span class='t-1'>Preceding text</span><div><div class='field-label'>Nearby label</div>"
               "<input id=a></div></div>"
               "<div><span class='t-1'>Preceding text</span><div><input id=b aria-label='Own label'></div></div>")
    got = [page.evaluate(READ, s) for s in ("#a", "#b")]
    assert [(g["question"], g["source"]) for g in got] == [("Nearby label", "nearby"), ("Own label", "aria-label")]


# Review of the first cut (reviewer probes, 2026-09-28): what the preceding
# text must NOT become.
@pytest.mark.parametrize("html", [
    "<p>Intro to the application</p><input type=radio name=q id=a><span>Yes</span>",
    "<div><p>By applying you agree we may run a background check.</p>"
    "<div><input type=checkbox id=a><span>Send me job alerts</span></div></div>",
], ids=["radio", "lone-checkbox"])
def test_a_choice_never_takes_the_text_before_it(page, load, html):
    """A radio's or checkbox's own label follows it; the text before it is a
    neighbour's (the previous option's, a paragraph)."""
    load(page, html)
    assert page.evaluate(READ, "#a")["question"] == ""


@pytest.mark.parametrize("html", [
    "<div><input id=a><span class=c1>First name</span><input id=b><span class=c1>Last name</span></div>",
    "<div><p>Tell us about you</p><div class=x1><input id=a><label class=x2>First name</label></div>"
    "<div class=x1><input id=b><label class=x2>Last name</label></div></div>",
], ids=["flat", "wrapped"])
def test_boxes_labelled_after_them_never_take_the_text_before(page, load, html):
    """A label AFTER each box: the text before the second box is the first
    box's label, and the text before the first box is an intro."""
    load(page, html)
    assert [page.evaluate(READ, s)["question"] for s in ("#a", "#b")] == ["", ""]


@pytest.mark.parametrize("html", [
    # an instruction paragraph: a sentence, not a label
    "<div><h3>Contact</h3><p>We will use this to reach you about your application.</p>"
    "<div><input id=a placeholder='Phone number'></div></div>",
    # the previous field's error message
    "<div><div><label for=e>Email</label><input id=e></div><span class=msg>Please enter a valid email address</span>"
    "<div><input id=a placeholder='Phone'></div></div>",
    # helper text between the real label and the box: which one is the label?
    "<div><span>Phone</span><span>Include country code</span><div><input id=a></div></div>",
    # a table's header row
    "<table><tr><th>Company</th><th>Title</th></tr><tr><td><input id=a></td></tr></table>",
    # screen-reader-only text
    "<div><span style='position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)'>Loading</span>"
    "<div><input id=a placeholder='Search'></div></div>",
    "<style>.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}</style>"
    "<div><span class='sr-only'>Loading</span><div><input id=a placeholder='Search'></div></div>",
    # a live region and an alert
    "<div><span aria-live='polite'>Saved</span><div><input id=a></div></div>",
    "<div><div role='alert'><span>Check this field</span></div><div><input id=a></div></div>",
    # a label AFTER the box's wrapper, below an intro
    "<div><p>Section intro text</p><div class=w><input id=a role=combobox placeholder='Select...'></div>"
    "<span class=z>Country</span></div>",
    # too long for a label
    "<div><span>Tell us in your own words what excites you about this role and our team</span><div><input id=a></div></div>",
], ids=["instructions", "previous-error", "helper-between", "table-header", "clipped", "sr-only-class", "live-region",
        "alert", "label-after-wrapper", "too-long"])
def test_text_that_is_not_a_label_is_never_read_as_one(page, load, html):
    load(page, html)
    assert page.evaluate(READ, "#a")["question"] == ""


def test_a_cell_before_the_box_in_its_own_row_is_its_label(page, load):
    """The climb never leaves the box's table row (a header row names columns,
    not this box), but a cell beside it in the row is its label."""
    load(page, "<table><tr><td>Company</td><td><input id=a></td></tr></table>")
    assert page.evaluate(READ, "#a")["question"] == "Company"


@pytest.mark.parametrize("before, question", [("<span>Willing to relocate?</span>", "Willing to relocate?"),
                                              ("<p>Please answer every question below honestly.</p>", "")])
def test_a_group_container_named_only_by_the_text_before_it(page, load, before, question):
    """readField(container) — a nameless radiogroup's question — reads the
    preceding text only when it passes the label test."""
    load(page, f"{before}<div role=radiogroup id=g><label><input type=radio name=q>Yes</label>"
               "<label><input type=radio name=q>No</label></div>")
    got = page.evaluate(READ, "#g")
    assert (got["question"], got["source"]) == (question, "preceding" if question else None)


def test_a_label_under_a_heading_is_still_the_label(page, load):
    """A heading BEFORE the candidate ends the look-back, not the answer."""
    load(page, f"<section><h3>Contact</h3><span class='b-47'>Phone</span>{wrapped('<input id=a>')}</section>")
    assert page.evaluate(READ, "#a")["question"] == "Phone"


# A label that names only a PART of a field ("Month", "Type") asks nothing on
# its own (iCIMS, live 2026-10-01 — fixtures/browser/icims_profile.html): the
# group's question goes before it, so /map can tell a start from an end and a
# phone type from a phone number. The part a date control holds is reported.
def test_icims_bare_part_labels_carry_their_groups_question(page, load):
    from tests.browser.conftest import fixture_html

    load(page, fixture_html("icims_profile.html"))
    ids = ["icims_0_startdate_month", "icims_0_startdate_date", "icims_0_startdate_year", "icims_0_enddate_year",
           "icims_0_phonetype", "icims_0_phonenumber", "icims_0_addresstype", "icims_0_addressstreet1"]
    got = [page.evaluate(READ, f"#{i}") for i in ids]
    assert [(g["question"], g["part"]) for g in got] == [
        ("Start Date (Month / Day / Year): Month", "month"), ("Start Date (Month / Day / Year): Day", "day"),
        ("Start Date (Month / Day / Year): Year", "year"), ("End Date (if applicable) (Month / Day / Year): Year", "year"),
        ("Enter in your mobile number: Type", None), ("Enter in your mobile number: Number", None),
        ("Enter your full address: Type", None), ("Address", None)]
    assert got[0]["source"] == "label-for"


@pytest.mark.parametrize("html, question, part", [
    # a fieldset's legend is the group's question
    ("<fieldset><legend>Date of birth</legend><label for=a>Year</label><input id=a>"
     "<label for=m>Month</label><input id=m></fieldset>", "Date of birth: Year", "year"),
    # a group no text names keeps the bare word
    ("<div><label for=a>Year</label><input id=a><label for=m>Month</label><input id=m></div>", "Year", "year"),
    # a field alone keeps it too, and an id naming the part still says which
    ("<p>Intro to the application</p><div><label for=a>Year</label><input id=a></div>", "Year", "year"),
    ("<label for=a>Start year</label><input id=a name=edu_startdate_year>", "Start year", "year"),
    # a word that is a question on its own is never prefixed
    ("<div><span>Contact</span><div><label for=a>City</label><input id=a><label for=b>Zip</label>"
     "<input id=b></div></div>", "City", None),
], ids=["legend", "no-group-text", "alone", "id-part", "not-a-part"])
def test_a_part_label_takes_its_group_question_only_where_one_is_named(page, load, html, question, part):
    load(page, html)
    got = page.evaluate(READ, "#a")
    assert (got["question"], got["part"]) == (question, part)


def test_a_radio_option_named_like_a_part_is_never_prefixed(page, load):
    load(page, "<span>Preferred contact</span><div><label><input type=radio name=q id=a>Type</label>"
               "<label><input type=radio name=q id=b>Number</label></div>")
    assert [page.evaluate(READ, s)["question"] for s in ("#a", "#b")] == ["Type", "Number"]
