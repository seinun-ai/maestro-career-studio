"""The rule pass names the FIELD it wrote, not just a label (the answer receipt's source of truth).

`filled[i].fid` is the inventory's fid for the control a rule wrote, so the panel reads that
field's question, value and options from the inventory instead of from the label text a rule
matched on (for a radio or a checkbox that text is the OPTION: "Yes", "Asian"). And a click
the rule pass makes on a radio or a checkbox is the engine's, never the user's: the field it
lands on is not `touched`."""

import json

import pytest

from tests.browser.conftest import ENGINE_SOURCES

NS = "window.careerStudioCompanion"
INV = f"{NS}.fillInventory"
SOURCES = ["shared/choose.js", "shared/policy.js", "shared/profile-fields.js", *ENGINE_SOURCES,
           "content/eeo.js", "content/autofill.js"]

WORK_AUTH = """<fieldset><legend>Are you authorized to work in the US?</legend>
  <label><input type='radio' name='wa' value='y'>Yes</label>
  <label><input type='radio' name='wa' value='n'>No</label></fieldset>"""
RACE = """<fieldset><legend>Race (select all that apply)</legend>
  <label><input type='checkbox' name='r' value='a'>Asian</label>
  <label><input type='checkbox' name='r' value='w'>White</label>
  <label><input type='checkbox' name='r' value='b'>Black or African American</label></fieldset>"""
FIRST = "<label for='fn'>First name *</label><input id='fn'>"
PROFILE = {"personal": {"first_name": "Ada"}, "work_auth": {"authorized_now": True},
           "eeo": {"race_ethnicity": "Asian"}}


@pytest.fixture
def ran(page, load):
    def _ran(html, profile=PROFILE, eeo=True):
        load(page, html, SOURCES)
        result = page.evaluate(
            "async (a) => window.careerStudioCompanion.fillFormFromProfile(a.profile, [], a.eeo, [], false)",
            {"profile": profile, "eeo": eeo})
        fields = page.evaluate(f"() => {INV}.list({{}}).fields")
        return result, {field["fid"]: field for field in fields}
    return _ran


def test_a_radio_write_names_the_group_not_the_option(ran):
    result, fields = ran(WORK_AUTH)
    [item] = result["filled"]
    assert item["rule"] == "work-auth"
    field = fields[item["fid"]]
    assert (field["question"], field["committed"]) == ("Are you authorized to work in the US?", "Yes")


def test_a_checkbox_group_write_is_one_field_with_a_list_answer(ran):
    result, fields = ran(RACE)
    assert {item["fid"] for item in result["filled"]} == {result["filled"][0]["fid"]}
    field = fields[result["filled"][0]["fid"]]
    assert field["question"] == "Race (select all that apply)"
    assert field["committed"] == ["Asian"] and field["multi"] is True
    assert len(field["options"]) == 3


def test_a_label_with_an_asterisk_is_the_same_field(ran):
    result, fields = ran(FIRST)
    [item] = result["filled"]
    assert fields[item["fid"]]["question"] == "First name"
    assert fields[item["fid"]]["committed"] == "Ada"


def test_the_rule_passs_own_clicks_do_not_mark_a_field_touched(ran):
    """A radio or checkbox click fires a trusted change; the engine named the control busy."""
    result, fields = ran(WORK_AUTH + RACE + FIRST)
    assert result["filled"] and all(item["fid"] for item in result["filled"])
    assert [field["touched"] for field in fields.values()] == [False, False, False]


def test_a_real_user_click_still_marks_the_field_touched(page, load):
    load(page, WORK_AUTH, SOURCES)
    page.evaluate(f"() => {INV}.list({{}})")
    page.click("input[value='n']")
    [field] = page.evaluate(f"() => {INV}.list({{}}).fields")
    assert (field["touched"], field["committed"]) == (True, "No")


def test_fid_for_names_a_control_no_pass_has_listed_yet(page, load):
    load(page, FIRST, SOURCES)
    fid = page.evaluate(f"() => {INV}.fidFor(document.getElementById('fn'))")
    assert fid == page.evaluate(f"() => {INV}.list({{}}).fields[0].fid")
    assert page.evaluate(f"() => {INV}.fidFor(document.body, {{relist: false}})") is None


def test_a_read_only_listing_leaves_the_standing_consent_alone(page, load):
    """The receipt's post-run read lists under the run's consent; a later re-list on behalf
    of `resolve` still uses the consent the run's own inventory set."""
    load(page, FIRST, SOURCES)
    page.evaluate(f"() => {INV}.list({{consentForms: true}})")
    page.evaluate(f"() => {INV}.list({{consentForms: false, keep: true}})")
    assert page.evaluate(f"() => {INV}.isBlocked('nope')") is False
    got = page.evaluate(f"""() => {{
      const el = document.getElementById('fn'); const fid = {INV}.fidFor(el);
      const sig = document.createElement('input'); sig.id = 's';
      document.body.insertAdjacentHTML('beforeend', "<label for='s2'>I agree to the terms *</label><input type='checkbox' id='s2'>");
      return {INV}.list({{}}).fields.length; }}""")
    assert got >= 1


def test_a_typed_id_number_is_absent_from_the_receipt_under_standing_consent(page, load):
    """Real fields, real keystrokes: with `consentForms` the inventory says "not blocked" for the
    SSN box, and the panel's builder (the real `shared/receipt.js`) still leaves it out."""
    load(page, "<label for='s'>Social Security Number</label><input id='s'>"
               "<label for='f'>First name</label><input id='f'>",
         [*SOURCES, "shared/receipt.js"])
    for selector, text in (("#s", "000-00-0000"), ("#f", "Ada")):
        page.click(selector)
        page.keyboard.type(text)
    fields = page.evaluate(f"() => {INV}.list({{consentForms: true}}).fields")
    ssn = next(field for field in fields if field["question"] == "Social Security Number")
    assert (ssn["touched"], ssn["policyBlocked"]) == (True, False)
    built = page.evaluate(f"(fields) => {NS}.receipt.fromEdits([{{result: {{fields}}}}], {{}})", fields)
    assert [(f["question"], f["answer"]) for f in built["fields"]] == [("First name", "Ada")]
    assert "000-00-0000" not in json.dumps(built)
