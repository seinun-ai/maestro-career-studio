"""Widgets the owner's second live check showed the engine could not see or drive
(plan docs/plans/2026-10-14-companion-live-check-2.md, Batch I): a read-only
Ant Design select with an invisible input, pill button groups, a debounced search
list, an address autocomplete, URL and date formats. Every page is a fixture or
inline made-up markup copied from the live shape (fixtures/browser/README.md)."""

from tests.browser.conftest import fixture_html
from tests.browser.pages import apply, explore, inv, oracle


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
