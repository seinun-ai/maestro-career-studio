"""Repeating sections and their own Add buttons (content/sections.js, through
fill-ops' `sections` and `add`) — notes §5: a section grows only by its own
Add, an added entry's fields are REQUIRED, and its Delete must never be pressed."""

import re

from tests.browser.conftest import fixture_html
from tests.browser.pages import oracle

SID = re.compile(r"^[A-Za-z0-9]+-s\d+$")


def sections(page):
    return page.evaluate("() => window.careerStudioCompanion.fillOps.sections()")


def add(page, sid, heading, entries):
    return page.evaluate("(r) => window.careerStudioCompanion.fillOps.add(r)",
                         {"sid": sid, "heading": heading, "entries": entries})


def by_heading(page):
    return {s["heading"]: s for s in sections(page)}


def test_sections_lists_repeating_groups_with_their_entries_and_add_button(page, load):
    load(page, fixture_html("workday_sections.html"))
    got = sections(page)
    assert [{k: v for k, v in s.items() if k != "sid"} for s in got] == [
        {"heading": "Work Experience", "entries": 1, "filled": [False], "held": [[]], "add": "Add Another"},
        {"heading": "Education", "entries": 1, "filled": [False], "held": [[]], "add": "Add Another"},
        {"heading": "Websites", "entries": 0, "filled": [], "held": [], "add": "Add"},
    ]
    assert all(SID.match(s["sid"]) for s in got) and len({s["sid"] for s in got}) == 3
    # Only the heading, the counts, what each entry holds and the button's words: never an element.
    assert all(set(s) == {"sid", "heading", "entries", "filled", "held", "add"} for s in got)
    # An entry holding a committed value is `filled`, and says what it holds
    # (for the local backend's reconciliation); the same section keeps its sid.
    page.fill("#Work-Experience-1-Job-Title", "Analyst")
    page.keyboard.press("Tab")
    page.fill("#Work-Experience-1-Company", "A" * 250)
    page.keyboard.press("Tab")
    again = by_heading(page)
    assert again["Work Experience"]["filled"] == [True]
    assert again["Work Experience"]["held"] == [["Analyst", "A" * 200]]
    assert again["Work Experience"]["sid"] == got[0]["sid"]
    assert again["Education"]["filled"] == [False] and again["Education"]["held"] == [[]]


def test_add_presses_only_the_sections_own_add_button_and_never_delete(page, load):
    load(page, fixture_html("workday_sections.html"))
    s = by_heading(page)
    web = s["Websites"]
    assert add(page, web["sid"], "Websites", 0) == {"sid": web["sid"], "outcome": "added", "entries": 1}
    assert oracle(page, "entries") == {"Work Experience": 1, "Education": 1, "Websites": 1}
    work = s["Work Experience"]
    assert add(page, work["sid"], "Work Experience", 1)["entries"] == 2
    assert page.locator("h4", has_text="Work Experience 2").count() == 1
    assert oracle(page, "entries") == {"Work Experience": 2, "Education": 1, "Websites": 1}
    assert oracle(page, "deleted") == 0
    after = by_heading(page)
    assert (after["Websites"]["entries"], after["Websites"]["add"]) == (1, "Add Another")
    assert after["Work Experience"]["entries"] == 2


def test_an_add_decided_on_an_older_view_never_presses(page, load):
    load(page, fixture_html("workday_sections.html"))
    work = by_heading(page)["Work Experience"]
    # The loop saw one entry; the page now has two (the user pressed Add).
    page.click("#sec-work > [data-automation-id=add-button]")
    assert add(page, work["sid"], "Work Experience", 1)["outcome"] == "stale"
    assert add(page, work["sid"], "Education", 2)["outcome"] == "stale"
    assert oracle(page, "entries")["Work Experience"] == 2
    # A sid this frame never minted is not its to answer.
    assert add(page, "zz-s1", "Work Experience", 2) is None


def test_a_latched_stop_never_presses_add(page, load):
    load(page, fixture_html("workday_sections.html"))
    web = by_heading(page)["Websites"]
    page.evaluate("() => window.careerStudioCompanion.fillOps.cancel()")
    assert add(page, web["sid"], "Websites", 0)["outcome"] == "cancelled"
    assert oracle(page, "entries")["Websites"] == 0


def test_an_add_the_page_ignores_is_not_added(page, load):
    load(page, """<div role="group" aria-labelledby="h"><h4 id="h">Certifications</h4>
      <button type="button" data-automation-id="add-button">Add</button></div>""")
    [cert] = sections(page)
    assert add(page, cert["sid"], "Certifications", 0) == {"sid": cert["sid"], "outcome": "not_added", "entries": 0}


# A section offering every button that looks like Add but is not the section's
# own: Delete/Remove/Trash by text, name or automation id, a submit, one inside
# a link, one inside an entry, and a page footer's. Every press is recorded.
DECOYS = """
<div role="group" aria-labelledby="w" id="sec">
  <h4 id="w">Websites</h4>
  <div class="entries">
    <div role="group" aria-labelledby="w1"><h4 id="w1">Websites 1</h4>
      <input aria-label="URL"><button type="button" class="in-entry">Add</button></div>
  </div>
  <button type="button" data-automation-id="delete-button">Add</button>
  <button type="button" aria-label="Remove website">Add another</button>
  <button type="button" title="Trash">Add</button>
  <button type="submit">Add</button>
  <a href="#x"><span role="button">Add</span></a>
  <button type="button" id="own">Add Another</button>
</div>
<div role="group" aria-labelledby="c"><h4 id="c">Certifications</h4>
  <button type="button" data-automation-id="add-button" aria-label="Delete certification">Add</button>
  <button type="button">Remove</button><button type="button">Trash</button>
</div>
<footer><div role="group" aria-labelledby="f"><h4 id="f">Links</h4>
  <button type="button" data-automation-id="pageFooterNextButton">Add another</button></div></footer>
<script>
  window.pressed = [];
  for (const b of document.querySelectorAll("button, [role=button]")) {
    b.addEventListener("click", (e) => { e.preventDefault(); window.pressed.push(b.id || b.className || b.textContent); });
  }
</script>"""


def test_a_delete_remove_or_trash_control_is_never_pressed(page, load):
    load(page, DECOYS)
    got = sections(page)
    # Only the section that owns a real Add is listed; its Add is its own.
    assert [(s["heading"], s["entries"], s["add"]) for s in got] == [("Websites", 1, "Add Another")]
    assert add(page, got[0]["sid"], "Websites", 1)["outcome"] == "not_added"
    assert page.evaluate("window.pressed") == ["own"]


def test_a_section_by_heading_alone_counts_entries_titled_after_it(page, load):
    load(page, """<section><h3>Education</h3>
      <div class="entry"><h4>Education 1</h4><label>School <input id="s1"></label></div>
      <div class="entry" style="display:none"><h4>Education 2</h4><label>School <input></label></div>
      <button type="button" id="more">Add another education</button></section>
    <script>
      document.getElementById("more").addEventListener("click", () => {
        const e = document.querySelector(".entry").cloneNode(true);
        e.querySelector("h4").textContent = "Education 2";
        document.getElementById("more").before(e);
      });
    </script>""")
    [edu] = sections(page)
    # A hidden (prototype) entry is not one of the page's entries.
    assert (edu["heading"], edu["entries"], edu["add"]) == ("Education", 1, "Add another education")
    assert add(page, edu["sid"], "Education", 1)["outcome"] == "added"
    assert sections(page)[0]["entries"] == 2


def test_a_labelled_section_counts_every_numbered_entry_whatever_its_words(page, load):
    """Counting one entry too few would add one too many — with required
    fields — so a labelled group's entries are its groups titled "… <n>",
    even when their words are not the heading's."""
    load(page, """<div role="group" aria-labelledby="h"><h4 id="h">Work History</h4>
      <div role="group" aria-label="Job 1"><input aria-label="Employer">
        <div role="group" aria-label="Phone 1"><input aria-label="Phone"></div></div>
      <div role="group" aria-label="Job 2" hidden><input aria-label="Employer"></div>
      <button type="button" data-automation-id="add-button">Add Another</button></div>""")
    [work] = sections(page)
    assert (work["heading"], work["entries"]) == ("Work History", 1)


def test_a_typeless_add_counts_outside_a_form_and_never_inside_one(page, load):
    """A <button> with no type is a submit only inside a form: outside one it
    is an ordinary button (Workday's Add); inside one, pressing it would send
    the form."""
    load(page, """<div role="group" aria-labelledby="a"><h4 id="a">Websites</h4><button id="free">Add</button></div>
      <form><div role="group" aria-labelledby="b"><h4 id="b">Certifications</h4><button id="sends">Add</button></div></form>""")
    assert [(s["heading"], s["add"]) for s in sections(page)] == [("Websites", "Add")]


def test_the_inventory_keeps_its_own_last_pass_for_reuse(page, load):
    """`sections` may reuse the last inventory only while nothing changed
    since it — and the inventory itself holds that pass, so a re-list
    anywhere (resolve() re-lists on its own) is the pass that is reused."""
    load(page, fixture_html("workday_sections.html"))
    listed = page.evaluate("() => window.careerStudioCompanion.fillOps.inventory({runId: 'r1'})")
    last = page.evaluate("() => window.careerStudioCompanion.fillInventory.last()")
    assert [f["fid"] for f in last] == [f["fid"] for f in listed["fields"]]
    page.click("#sec-web > [data-automation-id=add-button]")
    assert page.evaluate("() => window.careerStudioCompanion.fillInventory.last()") is None
    # A re-list (here the inventory's own) makes the NEW pass the one kept.
    relisted = page.evaluate("() => window.careerStudioCompanion.fillInventory.list().fields.map((f) => f.fid)")
    assert [f["fid"] for f in page.evaluate("() => window.careerStudioCompanion.fillInventory.last()")] == relisted
    assert by_heading(page)["Websites"]["entries"] == 1


# Two sections with no ARIA and no wrapper each: one container, headings
# and controls side by side.
FLAT = """<div id="form">
  <h3>Education</h3>
  <h4>Education 1</h4><label>School <input id="school1"></label>
  <button type="button" id="add-edu">Add another</button>
  <h3>Websites</h3>
  <h4>Websites 1</h4><label>URL <input id="url1"></label>
  <button type="button" id="add-web">Add</button>
</div>
<script>
  window.pressed = [];
  for (const b of document.querySelectorAll("button")) b.addEventListener("click", () => {
    window.pressed.push(b.id);
    const title = b.id === "add-edu" ? "Education 2" : "Websites 2";
    const h = document.createElement("h4");
    h.textContent = title;
    b.before(h);
  });
</script>"""


def test_sections_sharing_one_container_are_each_listed_with_their_own_add(page, load):
    """A heading's section runs to the next heading of its level or higher:
    its entries and its Add are the ones in that stretch, and a second
    section in the same container is its own section, never dropped."""
    load(page, FLAT)
    page.fill("#school1", "State University")
    got = sections(page)
    assert [(s["heading"], s["entries"], s["add"], s["held"]) for s in got] == [
        ("Education", 1, "Add another", [["State University"]]), ("Websites", 1, "Add", [[]])]
    assert got[0]["sid"] != got[1]["sid"]
    assert add(page, got[1]["sid"], "Websites", 1)["outcome"] == "added"
    assert page.evaluate("window.pressed") == ["add-web"]
    assert [s["entries"] for s in sections(page)] == [1, 2]


def test_step_page_and_of_numbers_are_not_entries(page, load):
    load(page, """<div role="group" aria-labelledby="h"><h4 id="h">Application</h4>
      <div role="group" aria-label="Step 2"><input aria-label="Email"></div>
      <div role="group" aria-label="Page 3"><input aria-label="Phone"></div>
      <button type="button" data-automation-id="add-button">Add</button></div>""")
    [app] = sections(page)
    assert app["entries"] == 0
    assert page.evaluate("[window.careerStudioCompanion.repeatOf('Work Experience 2'), "
                         "window.careerStudioCompanion.repeatOf('Step 2'), "
                         "window.careerStudioCompanion.repeatOf('Websites')]") == [
        {"base": "Work Experience", "n": 2}, None, None]


def test_an_add_that_hides_itself_after_the_press_still_counts_its_entry(page, load):
    """Some sections take one entry and hide their Add: the entry the press
    made is counted (the section is re-read without needing its Add), so no
    false "0 of 1 added" line."""
    load(page, """<div role="group" aria-labelledby="h"><h4 id="h">Websites</h4><div class="entries"></div>
      <button type="button" id="add" data-automation-id="add-button">Add</button></div>
    <script>
      document.getElementById("add").addEventListener("click", (e) => {
        document.querySelector(".entries").innerHTML =
          '<div role="group" aria-label="Websites 1"><input aria-label="URL"></div>';
        e.target.hidden = true;
      });
    </script>""")
    [web] = sections(page)
    assert add(page, web["sid"], "Websites", 0) == {"sid": web["sid"], "outcome": "added", "entries": 1}


def test_a_flat_section_takes_the_add_after_its_last_entry_not_one_inside_an_entry(page, load):
    """In a flat layout nothing marks where an entry ends, so an Add-like
    button inside entry 1 ("Add responsibility") would read as the section's:
    the section's Add is the last one after its last entry title."""
    load(page, """<div><h3>Work Experience</h3>
      <h4>Work Experience 1</h4><label>Job Title <input></label>
      <button type="button" id="resp1">Add responsibility</button>
      <h4>Work Experience 2</h4><label>Job Title <input></label>
      <button type="button" id="resp2">Add responsibility</button>
      <button type="button" id="own">Add another</button></div>
    <script>
      window.pressed = [];
      for (const b of document.querySelectorAll("button")) b.addEventListener("click", () => window.pressed.push(b.id));
    </script>""")
    [work] = sections(page)
    assert (work["entries"], work["add"]) == (2, "Add another")
    add(page, work["sid"], "Work Experience", 2)
    assert page.evaluate("window.pressed") == ["own"]
