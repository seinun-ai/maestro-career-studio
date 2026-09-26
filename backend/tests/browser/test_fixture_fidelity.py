"""The fixtures behave as the live probe saw Workday behave.

Each test drives a fixture with Playwright's TRUSTED input (no engine loaded)
and checks the fixture's `window.__oracle` — the value the fake app really
holds. If one of these fails, the fixture no longer reproduces the field notes
(docs/reports/2026-09-26-workday-field-interactions.md, § numbers below), and
every engine test built on it proves nothing.
"""

from tests.browser.conftest import fixture_html

LIST = "[data-automation-id=activeListContainer]"
ROWS = f"{LIST} [role=option]"


def oracle(page, key):
    return page.evaluate("(k) => window.__oracle[k]", key)


def row_texts(page):
    return page.locator(f"{ROWS} [data-automation-id=promptOption]").all_inner_texts()


def pills(page, input_id):
    return page.evaluate("""(id) => [...document.getElementById(id).closest('[data-automation-id=multiSelectContainer]')
        .querySelectorAll('[data-automation-id=selectedItem] [data-automation-id=promptOption]')].map((p) => p.textContent)""",
                         input_id)


def wait_rows(page, texts):
    """Wait until the open list's option texts are exactly `texts` (a search
    settles in two stages; waiting on the texts, not a clock, keeps this steady)."""
    page.wait_for_function("""(want) => JSON.stringify([...document.querySelectorAll(
        '[data-automation-id=activeListContainer] [role=option] [data-automation-id=promptOption]')]
        .map((p) => p.textContent)) === JSON.stringify(want)""", arg=texts)


def search(page, input_id, term, rows=None):
    """What a person does (§2): press, wait for the list, type, Enter; then
    wait for the rows the search settles on (or, with none given, its second stage)."""
    page.click(f"#{input_id}")
    page.wait_for_selector(LIST)
    page.fill(f"#{input_id}", term)
    page.keyboard.press("Enter")
    if rows is None:
        page.wait_for_timeout(600)
    else:
        wait_rows(page, rows)


# --- workday_search.html (§2)
def test_search_needs_press_then_enter_and_commits_only_via_the_radio(page, load):
    load(page, fixture_html("workday_search.html"), sources=[])
    page.click("#heard")
    page.wait_for_selector(ROWS)   # the default list is drawn
    page.type("#heard", "LinkedIn")
    page.keyboard.press("Enter")
    wait_rows(page, ["LinkedIn", "LinkedIn"])
    rows = page.locator(ROWS)
    assert rows.count() == 2 and rows.nth(0).inner_text() == rows.nth(1).inner_text() == "LinkedIn"
    rows.nth(0).locator("[data-automation-id=promptOption]").click()   # the row text: highlight only
    assert rows.nth(0).get_attribute("aria-selected") == "true"
    assert oracle(page, "heard") == ""
    rows.nth(0).locator("input[type=radio][data-automation-id=radioBtn]").click()
    assert oracle(page, "heard") == "LinkedIn"
    # Single select: pill, list closed, search text cleared.
    assert pills(page, "heard") == ["LinkedIn"]
    assert page.evaluate("document.getElementById('portal').children.length") == 0
    assert page.input_value("#heard") == ""


def test_the_widget_marker_is_on_the_input_and_the_pills_in_the_multiselect_container(page, load):
    load(page, fixture_html("workday_search.html"), sources=[])
    assert page.get_attribute("#school", "data-uxi-widget-type") == "selectinput"
    assert page.evaluate("""() => { const box = document.getElementById('skills')
        .closest('[data-automation-id=multiSelectContainer]');
      return [box.dataset.uxiWidgetType, box.closest('[data-automation-id]').dataset.automationId === 'multiSelectContainer',
              box.closest('[data-automation-id^=formField-]').dataset.automationId]; }""") == [
        "multiselect", True, "formField-skills"]
    pill = page.locator("[data-automation-id=selectedItem]")
    assert pill.get_attribute("aria-label") == "SQL, press delete to clear value."
    assert pills(page, "skills") == ["SQL"] and oracle(page, "skills") == ["SQL"]


def test_press_opens_the_list_on_the_next_frame_and_typing_alone_opens_nothing(page, load):
    load(page, fixture_html("workday_search.html"), sources=[])
    # Typing without a press: nothing opens, and Enter does nothing.
    page.focus("#school")
    page.keyboard.type("Arlington")
    page.keyboard.press("Enter")
    page.wait_for_timeout(500)
    assert page.locator(LIST).count() == 0
    # A press: nothing in the same task, the list on the next frame.
    assert page.evaluate("""() => { const i = document.getElementById('heard');
      i.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
      return document.querySelector('[data-automation-id=activeListContainer]') === null; }""")
    page.wait_for_selector(f"{LIST}[role=listbox]")
    # The default list: the categories, with no leaf node and no radio.
    assert row_texts(page) == ["Job Board", "Social Media"]
    assert page.locator(f"{ROWS} [data-automation-id=promptLeafNode]").count() == 0
    # School opens EMPTY (§2 rule 9).
    page.click("#school")
    page.wait_for_selector(LIST)
    page.wait_for_timeout(50)
    assert page.locator(ROWS).count() == 0


def test_enter_is_ignored_before_the_list_exists_and_searches_on_key_up(page, load):
    load(page, fixture_html("workday_search.html"), sources=[])
    # Press and Enter in the same task: the list is not drawn yet, Enter is lost.
    page.evaluate("""() => { const i = document.getElementById('school'); i.value = 'Arlington';
      i.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
      i.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}));
      i.dispatchEvent(new KeyboardEvent('keyup', {key: 'Enter', bubbles: true})); }""")
    page.wait_for_timeout(500)
    assert page.locator(ROWS).count() == 0
    # With the list open, key-DOWN alone does not search (§2 rule 1)…
    page.evaluate("document.getElementById('school').dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}))")
    page.wait_for_timeout(500)
    assert page.locator(ROWS).count() == 0
    # …key-up does.
    page.evaluate("document.getElementById('school').dispatchEvent(new KeyboardEvent('keyup', {key: 'Enter', bubbles: true}))")
    page.wait_for_function("document.querySelectorAll('[data-automation-id=activeListContainer] [role=option]').length === 8")


def test_results_arrive_in_two_stages_in_reused_row_nodes(page, load):
    load(page, fixture_html("workday_search.html"), sources=[])
    page.click("#school")
    page.wait_for_selector(LIST)
    page.fill("#school", "Arlington")
    page.keyboard.press("Enter")
    # Stage one, as first drawn: a single row — the wrong school, if clicked now.
    first_seen = page.wait_for_function("""() => { const r = [...document.querySelectorAll(
        '[data-automation-id=activeListContainer] [role=option] [data-automation-id=promptOption]')];
      return r.length ? r.map((p) => p.textContent) : null; }""", polling="raf").json_value()
    assert first_seen == ["Arlington Baptist College"]
    page.evaluate("window.firstRow = document.querySelector('[data-automation-id=activeListContainer] [role=option]')")
    page.wait_for_function("document.querySelectorAll('[data-automation-id=activeListContainer] [role=option]').length === 8")
    texts = row_texts(page)
    assert len(texts) == 8 and "The University of Texas at Arlington" in texts
    # The first row is the SAME node, not a fresh one (§2 rule 3).
    assert page.evaluate("window.firstRow === document.querySelector('[data-automation-id=activeListContainer] [role=option]')")
    # A search that replaces results reuses the nodes and swaps their text.
    page.fill("#school", "Texas")
    page.keyboard.press("Enter")
    wait_rows(page, ["The University of Texas at Arlington", "The University of Texas at Austin",
                     "The University of Texas at Dallas", "Texas A&M University", "Texas State University"])
    assert page.evaluate("window.firstRow.isConnected")
    # Row structure: menuItem > promptLeafNode > radioBtn + promptOption.
    assert page.locator(f"{ROWS}[data-automation-id=menuItem] > [data-automation-id=promptLeafNode] > "
                        "input[type=radio][data-automation-id=radioBtn] + [data-automation-id=promptOption]").count() == 5


def test_a_single_result_commits_on_enter_with_no_click(page, load):
    load(page, fixture_html("workday_search.html"), sources=[])
    search(page, "school", "Dallas")
    page.wait_for_function("window.__oracle.school !== ''")
    assert oracle(page, "school") == "The University of Texas at Dallas"
    assert pills(page, "school") == ["The University of Texas at Dallas"]


def test_a_misspelt_name_finds_no_items_and_one_right_word_finds_the_school(page, load):
    load(page, fixture_html("workday_search.html"), sources=[])
    search(page, "school", "University of Texas at Arlignton", rows=["No Items."])
    assert page.locator(f"{ROWS} input").count() == 0
    page.fill("#school", "Arlington")
    page.keyboard.press("Enter")
    page.wait_for_function("document.querySelectorAll('[data-automation-id=activeListContainer] [role=option]').length === 8")
    page.locator(ROWS, has_text="The University of Texas at Arlington").locator("input").click()
    assert oracle(page, "school") == "The University of Texas at Arlington"


def test_a_category_opens_its_leaves(page, load):
    load(page, fixture_html("workday_search.html"), sources=[])
    page.click("#heard")
    page.wait_for_selector(ROWS)
    page.locator(ROWS, has_text="Job Board").click()
    assert row_texts(page) == ["Indeed", "LinkedIn", "Glassdoor"]
    page.locator(ROWS, has_text="Indeed").locator("input").click()
    assert oracle(page, "heard") == "Indeed"


def test_a_multi_select_tick_toggles_a_pill_keeps_the_list_and_redraws_a_frame_later(page, load):
    load(page, fixture_html("workday_search.html"), sources=[])
    search(page, "skills", "Excel", rows=["Microsoft Excel", "Excel VBA"])
    tick = page.locator(ROWS, has_text="Microsoft Excel").locator("input[type=checkbox][data-automation-id=radioBtn]")
    # Read in the same task as the click, the box is still unticked (§2 rule 8).
    assert page.evaluate("""() => { const box = [...document.querySelectorAll(
        '[data-automation-id=activeListContainer] [role=option]')].find((r) => r.textContent === 'Microsoft Excel')
        .querySelector('input'); box.click(); return box.checked; }""") is False
    page.wait_for_function("""() => [...document.querySelectorAll('[data-automation-id=activeListContainer] [role=option]')]
        .find((r) => r.textContent === 'Microsoft Excel').querySelector('input').checked""")
    assert oracle(page, "skills") == ["SQL", "Microsoft Excel"]
    # The list stays open with the query still typed (§2 rule 7).
    assert page.locator(LIST).count() == 1 and page.input_value("#skills") == "Excel"
    # A second tick removes it again.
    tick.click()
    assert oracle(page, "skills") == ["SQL"]
    page.wait_for_function("""() => ![...document.querySelectorAll('[data-automation-id=activeListContainer] [role=option]')]
        .find((r) => r.textContent === 'Microsoft Excel').querySelector('input').checked""")


def test_skills_results_are_virtualized_and_scrolling_renders_the_rest(page, load):
    load(page, fixture_html("workday_search.html"), sources=[])
    search(page, "skills", "SQL")
    page.wait_for_function("document.querySelector('[data-automation-id=activeListContainer] [data-spacer]')"
                           ".style.height === '930px'")
    assert page.locator(ROWS).count() == 8
    assert "SQL" not in row_texts(page)
    assert page.evaluate("document.querySelector('[data-automation-id=activeListContainer] [data-spacer]')"
                         ".style.height") == f"{31 * 30}px"
    page.evaluate("document.querySelector('[data-automation-id=activeListContainer]').scrollTop = 18 * 30")
    page.wait_for_timeout(50)
    assert page.locator(ROWS).count() == 8
    exact = page.locator(ROWS).filter(has=page.locator("[data-automation-id=promptOption]", has_text="SQL")).filter(
        has_text="SQL").all()
    exact = [r for r in exact if r.inner_text() == "SQL"]
    assert len(exact) == 1 and exact[0].get_attribute("data-index") == "18"   # #19
    # The pre-existing pill shows as ticked; ticking it again would remove it.
    assert exact[0].locator("input").is_checked()


def test_the_delete_charm_removes_a_pill(page, load):
    load(page, fixture_html("workday_search.html"), sources=[])
    page.click("[data-automation-id=selectedItem] [data-automation-id=DELETE_charm]")
    assert pills(page, "skills") == [] and oracle(page, "skills") == []


def test_a_press_outside_closes_the_search_list(page, load):
    load(page, fixture_html("workday_search.html"), sources=[])
    page.click("#heard")
    page.wait_for_selector(LIST)
    page.mouse.click(1200, 880)
    assert page.locator(LIST).count() == 0


# --- workday_listbox.html (§3, §8a)
def test_a_popup_pick_updates_the_button_and_the_backing_input(page, load):
    load(page, fixture_html("workday_listbox.html"), sources=[])
    page.click("#degree")
    options = page.locator("#degree-list > li[role=option]")
    assert options.count() == 12
    assert page.get_attribute("#degree", "aria-controls") == "degree-list"
    assert page.get_attribute("#degree", "aria-expanded") == "true"
    # All in the DOM, the list scrolls, and Masters is below the fold.
    assert page.evaluate("(() => { const u = document.getElementById('degree-list'); return u.scrollHeight > u.clientHeight; })()")
    masters = options.filter(has_text="Masters")
    assert page.evaluate("""() => { const u = document.getElementById('degree-list');
      const li = [...u.children].find((o) => o.textContent === 'Masters');
      return li.offsetTop >= u.scrollTop + u.clientHeight; }""")
    masters.click()
    assert page.inner_text("#degree") == "Masters"
    assert page.get_attribute("#degree", "aria-label") == " Masters Required"
    backing = page.evaluate("document.getElementById('degree').parentElement.querySelector('.hidden-backing').value")
    assert len(backing) == 32 and all(c in "0123456789abcdef" for c in backing)
    assert oracle(page, "degree") == "Masters"
    assert page.get_attribute("#degree", "aria-expanded") == "false"
    # Reopened, the list jumps to the current value.
    page.click("#degree")
    assert page.evaluate("""() => { const u = document.getElementById('degree-list');
      const li = u.querySelector('[aria-selected=true]'); return [li.textContent, u.scrollTop > 0]; }""") == ["Masters", True]
    # "Select One" clears the backing and the app's value.
    page.locator("#degree-list > li", has_text="Select One").click()
    assert page.evaluate("document.getElementById('degree').parentElement.querySelector('.hidden-backing').value") == ""
    assert oracle(page, "degree") == "" and page.inner_text("#degree") == "Select One"


def test_the_popup_question_is_the_rich_text_legend_not_the_aria_label(page, load):
    load(page, fixture_html("workday_listbox.html"), sources=[])
    assert page.get_attribute("#auth", "aria-label") == " Select One Required"
    assert page.inner_text("[data-automation-id=formField-authorized] legend [data-automation-id=richText] p") == (
        "Are you legally authorized to work in the United States?")
    assert page.inner_text("[data-automation-id=formField-authorized] legend abbr") == "*"


def test_an_outside_click_hides_the_list_but_leaves_aria_expanded_true(page, load):
    load(page, fixture_html("workday_listbox.html"), sources=[])
    page.click("#auth")
    assert page.is_visible("#auth-list")
    page.mouse.click(1200, 880)
    assert not page.is_visible("#auth-list")
    assert page.get_attribute("#auth", "aria-expanded") == "true"
    assert page.locator("#auth-list").count() == 1   # still in the DOM


def test_one_list_opens_upward_above_its_button(page, load):
    load(page, fixture_html("workday_listbox.html"), sources=[])
    page.click("#auth")
    button, ul = page.locator("#auth").bounding_box(), page.locator("#auth-list").bounding_box()
    assert ul["y"] + ul["height"] <= button["y"] + 1
    page.click("#degree")
    button, ul = page.locator("#degree").bounding_box(), page.locator("#degree-list").bounding_box()
    assert ul["y"] >= button["y"] + button["height"] - 1


def test_the_stale_hidden_listbox_is_a_trap(page, load):
    load(page, fixture_html("workday_listbox.html"), sources=[])
    page.evaluate("document.getElementById('stale-ca').click()")
    assert page.evaluate("window.staleHit") is True


# --- workday_text.html (§1)
def test_text_is_committed_only_when_focus_really_leaves(page, load):
    load(page, fixture_html("workday_text.html"), sources=[])
    page.click("#city")
    page.keyboard.type("Springfield")
    assert oracle(page, "city") is None
    # A focusout sent while the box still has focus is ignored.
    page.evaluate("document.getElementById('city').dispatchEvent(new FocusEvent('focusout', {bubbles: true}))")
    assert oracle(page, "city") is None
    page.keyboard.press("Tab")
    assert oracle(page, "city") == "Springfield"
    assert page.is_hidden("#city-err") and page.get_attribute("#city", "aria-invalid") == "false"


def test_text_typed_by_exec_command_counts_and_leaving_empty_shows_the_error(page, load):
    load(page, fixture_html("workday_text.html"), sources=[])
    page.evaluate("""() => { const c = document.getElementById('city'); c.focus();
      document.execCommand('insertText', false, 'Austin'); c.blur(); }""")
    assert oracle(page, "city") == "Austin"
    page.fill("#city", "")
    page.keyboard.press("Tab")
    assert oracle(page, "city") == ""
    assert page.is_visible("#city-err") and page.get_attribute("#city", "aria-invalid") == "true"
    assert page.get_attribute("#city-err", "data-automation-id") == "errorMessage"


def test_postal_code_shows_a_value_the_app_never_took(page, load):
    load(page, fixture_html("workday_text.html"), sources=[])
    assert page.input_value("#zip") == "00000" and oracle(page, "zip") is None
    assert page.is_visible("#zip-err")
    # Leaving without typing commits nothing: the error stays.
    page.click("#zip")
    page.keyboard.press("Tab")
    assert oracle(page, "zip") == "" and page.is_visible("#zip-err")
    page.fill("#zip", "12345")
    page.keyboard.press("Tab")
    assert oracle(page, "zip") == "12345" and page.is_hidden("#zip-err")


# --- workday_date.html (§6)
def test_a_full_year_moves_focus_to_month_and_blurring_the_year_commits_nothing(page, load):
    load(page, fixture_html("workday_date.html"), sources=[])
    page.click("#m")
    page.keyboard.type("06")
    page.click("#y")
    page.keyboard.type("2026")
    assert page.evaluate("document.activeElement.id") == "m"
    # Blurring the box that was typed in does nothing: it no longer has focus.
    page.evaluate("document.getElementById('y').blur()")
    page.wait_for_timeout(50)
    assert oracle(page, "from") == ""
    # A focusout while a part still has focus is ignored too.
    page.evaluate("document.getElementById('m').dispatchEvent(new FocusEvent('focusout', {bubbles: true}))")
    page.wait_for_timeout(50)
    assert oracle(page, "from") == ""
    # The live sequence: blur what has focus NOW, then the events (§6).
    page.evaluate("""() => { const a = document.activeElement; a.blur();
      a.dispatchEvent(new FocusEvent('blur')); a.dispatchEvent(new FocusEvent('focusout', {bubbles: true})); }""")
    page.wait_for_timeout(50)
    assert oracle(page, "from") == "2026-06"
    assert page.locator("text=Error:").count() == 0


def test_month_06_shows_06_but_holds_6(page, load):
    load(page, fixture_html("workday_date.html"), sources=[])
    page.click("#m")
    page.keyboard.type("06")
    assert page.input_value("#m") == "6"
    assert page.inner_text("[data-automation-id=dateSectionMonth-display] >> nth=0") == "06"


def test_an_incomplete_date_shows_a_plain_error_span_and_marks_the_empty_part(page, load):
    load(page, fixture_html("workday_date.html"), sources=[])
    page.click("#m")
    page.keyboard.type("06")
    page.mouse.click(1200, 880)
    page.wait_for_timeout(50)
    error = page.locator("#from + span")
    assert error.inner_text() == "Error: The field From is required and must have a value."
    assert error.get_attribute("data-automation-id") is None
    assert page.get_attribute("#y", "aria-invalid") == "true" and page.get_attribute("#m", "aria-invalid") is None
    assert oracle(page, "from") == ""
    # Completing it and leaving clears the error.
    page.click("#y")
    page.keyboard.type("2026")
    page.mouse.click(1200, 880)
    page.wait_for_timeout(50)
    assert page.locator("#from + span").count() == 0 and page.get_attribute("#y", "aria-invalid") is None
    assert oracle(page, "from") == "2026-06"


def test_the_self_identify_date_has_a_day_part(page, load):
    load(page, fixture_html("workday_date.html"), sources=[])
    assert page.evaluate("[...document.querySelectorAll('#signed input')].map((i) => i.getAttribute('aria-label'))") == [
        "Month", "Day", "Year"]
    for part, value in (("#sm", "09"), ("#sd", "26"), ("#sy", "2026")):
        page.click(part)
        page.keyboard.type(value)
    page.mouse.click(1200, 880)
    page.wait_for_timeout(50)
    assert oracle(page, "signed") == "2026-09-26"


# --- workday_upload.html (§7)
def test_an_upload_shows_its_row_while_the_input_is_emptied_at_once(page, load):
    load(page, fixture_html("workday_upload.html"), sources=[])
    box = page.locator("[data-automation-id=attachments-FileUpload] input[type=file][data-automation-id=file-upload-input-ref]")
    assert box.is_hidden() and page.is_visible("[data-automation-id=attachments-FileUpload]")
    box.set_input_files({"name": "resume.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-1.4"})
    assert page.evaluate("document.querySelector('[data-automation-id=file-upload-input-ref]').files.length") == 0
    assert oracle(page, "files") == []
    page.wait_for_selector("[data-automation-id=file-upload-item]")
    assert page.inner_text("[data-automation-id=file-upload-item-name]") == "resume.pdf"
    assert "Successfully Uploaded!" in page.inner_text("[data-automation-id=file-upload-item]")
    assert oracle(page, "files") == ["resume.pdf"]


# --- workday_sections.html (§5, §4)
def test_sections_list_their_entries_and_add_appends_a_numbered_required_entry(page, load):
    load(page, fixture_html("workday_sections.html"), sources=[])
    assert oracle(page, "entries") == {"Work Experience": 1, "Education": 1, "Websites": 0}
    web = page.locator("div[role=group][aria-labelledby=Websites-section]")
    assert web.locator("[data-automation-id=add-button]").inner_text() == "Add"
    assert page.inner_text("[aria-labelledby=Work-Experience-section] > [data-automation-id=add-button]") == "Add Another"
    web.locator("[data-automation-id=add-button]").click()
    assert oracle(page, "entries")["Websites"] == 1
    assert web.locator("[data-automation-id=add-button]").inner_text() == "Add Another"
    entry = web.locator("div[role=group]", has_text="Websites 1")
    assert entry.locator("[data-automation-id=formField-url] input[aria-required=true]").count() == 1
    # The entry's Delete button has no accessible name.
    delete = entry.locator("button").first
    assert delete.inner_text() == "" and delete.get_attribute("aria-label") is None
    delete.click()
    assert oracle(page, "entries")["Websites"] == 0 and oracle(page, "deleted") == 1
    work = page.locator("div[role=group][aria-labelledby=Work-Experience-section]")
    work.locator("> [data-automation-id=add-button]").click()
    assert work.locator("h4", has_text="Work Experience 2").count() == 1
    assert oracle(page, "entries")["Work Experience"] == 2


def test_ticking_currently_work_here_removes_the_to_date_a_frame_later(page, load):
    load(page, fixture_html("workday_sections.html"), sources=[])
    entry = page.locator("div[role=group][aria-labelledby=Work-Experience-1-panel]")
    assert entry.locator("legend", has_text="To").count() == 1
    removed_at_once = page.evaluate("""() => { document.querySelector('label[for=Work-Experience-1-current]').click();
      return document.querySelector('[aria-labelledby=Work-Experience-1-panel] [data-automation-id=formField-endDate]') === null; }""")
    assert removed_at_once is False
    page.wait_for_timeout(50)
    assert entry.locator("[data-automation-id=formField-endDate]").count() == 0
    assert oracle(page, "Work Experience 1/I currently work here") is True
    # The rest of the entry commits the §1/§6 way.
    page.fill("#Work-Experience-1-Job-Title", "Analyst")
    page.keyboard.press("Tab")
    assert oracle(page, "Work Experience 1/Job Title") == "Analyst"


# --- adversarial
def test_adversarial_revert_shows_the_first_pick_then_takes_it_back(page, load):
    load(page, fixture_html("adversarial_revert.html"), sources=[])
    page.click("#relocate")
    page.click("#relocate-list > li:has-text('Yes')")
    assert page.inner_text("#relocate") == "Yes"
    assert page.evaluate("document.querySelector('.hidden-backing').value") == "" and oracle(page, "relocate") == ""
    page.wait_for_timeout(600)
    assert page.inner_text("#relocate") == "Select One"
    page.click("#relocate")
    page.click("#relocate-list > li:has-text('Yes')")
    page.wait_for_timeout(600)
    assert page.inner_text("#relocate") == "Yes" and oracle(page, "relocate") == "Yes"
    assert len(page.evaluate("document.querySelector('.hidden-backing').value")) == 32


def test_adversarial_same_text_has_two_others_under_different_visible_categories(page, load):
    load(page, fixture_html("adversarial_same_text.html"), sources=[])
    search(page, "referral", "Other", rows=["Other", "Other"])
    groups = page.locator(f"{LIST} [role=group]")
    assert groups.count() == 2
    assert [groups.nth(i).locator(".category-header").inner_text() for i in range(2)] == ["Job Board", "Social Media"]
    assert row_texts(page) == ["Other", "Other"]
    assert oracle(page, "referral") == ""
    groups.nth(1).locator("input[type=radio]").click()
    assert oracle(page, "referral") == "Social Media / Other"
