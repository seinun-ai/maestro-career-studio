# Fill Engine — Live Workday Revision Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or subagent-driven-development) to implement this plan task-by-task.

**Goal:** Make the fill engine operate and PROVE real Workday fields the way the live probe showed they work, add the missing abilities (Add sections, attach proof, derived facts, languages, recipe memory), and finish the original Tasks 9–10 — so one press of Fill completes what it can on any application page and never reports a false fill.

**Architecture:** Same hybrid engine (Tasks 1–8 of `2026-09-25-fill-engine.md`, merged to main at e1ace88d). This revision (a) replaces the page-side primitives for entering/leaving fields, pressing keys and waiting with the live-proven ones; (b) moves verification from "what the box shows" to each widget's committed evidence; (c) makes the loop behave as one controller per field (shared budget, snapshot/undo, one re-commit, honest `unconfirmed`/`unsupported` outcomes); (d) adds Add-section reconciliation, attach proof, derived facts, a fast-model reasoning route, widened low-stakes, profile languages and value-free recipe memory; (e) evaluates, cuts over and documents.

**Tech stack:** Plain-JS MV3 content scripts (no build), FastAPI + Pydantic, Jev System One + one fast-model fallback, pytest + Python Playwright (Chromium) browser suite, Next.js settings UI.

**Design:** `docs/plans/2026-09-25-fill-engine-design.md`, section **"Revision 2026-09-26 — live Workday findings"** (read it whole). **Evidence:** `docs/reports/2026-09-26-workday-field-interactions.md` (local-only, in this worktree; read "Rules that hold across every Workday field" first). Read SYSTEM.md first, then `extension/INTERNALS.md` § "How the fill behaves".

**Goal card (for any executor):**
- Owner's goal: Fill works on any job-application page; adapts instead of needing per-site code; never stalls; never claims a field is filled when the page did not take it.
- Settled owner decisions (2026-09-25/26): AI decides meaning (Jev picks among code-generated ids; no label rules / fuzzy matching); fallback is ONE fast model with the same floors, no smart-model tier; no debugger executor, no vision; Next/Save/Submit are never clicked; with the consent-forms permission ON nothing is refused by label (already implemented by the policy commit that precedes this plan — verify it is on the branch); low-stakes scope widened (see Task 9); recipe memory and profile languages are in scope.
- When this plan and reality disagree, prefer the goal and these decisions; log the deviation in the commit message and tell the owner.
- **Fixture rule:** a fixture reproduces a behaviour the field notes observed live, or is labelled adversarial (`adversarial_*.html`). Never model Workday from memory.

**Environment:**
- Backend tests: `cd backend && /opt/anaconda3/bin/python3 -m pytest tests/ -q`; browser suite: `cd backend && /opt/anaconda3/bin/python3 -m pytest tests/browser -q -rs` (Playwright 1.63.0 + cached chromium-1243; a SKIP is not a pass).
- `tests/browser` stays synchronous. Helpers: `fixture_html`, `load` (conftest); `inv`/`apply`/`explore` (`test_fill_core.py:6-19`); loop driver `run`/`f`/`opt`/`statuses`/`bodies` (`test_fill_loop.py:18-121`); end-to-end driver through real `agent.js` handlers (`test_fill_end_to_end.py`).
- A new page message type must be added to `agent.js` `PAGE_HANDLERS` AND `sw.js` `BROADCASTABLE` (pinned by `test_every_page_message_the_loop_sends_is_a_page_handler`).
- Frontend: `cd frontend && npx tsc --noEmit && npm run lint`. SYSTEM.md gate: `python3 scripts/check_system_md.py` (cap 1000 — Task 13 grooms before adding).
- Telemetry outcomes are additive-only (`backend/app/schemas/autofill_telemetry.py` `ObservationOutcome`, `extra="forbid"`).
- Commit after each task (message given). Never push. The owner merges and tests live.

**Task map:** 1 live-shaped fixtures with oracles · 2 enter/leave/keys/errors/money · 3 committed evidence · 4 one controller per field (loop) · 5 search-and-pick sequence · 6 popups, checkboxes, dependencies · 7 Add sections · 8 attach proof · 9 meaning: derived facts, reasoning route, low-stakes (+ old Task 9 UI) · 10 profile languages · 11 recipe memory · 12 evaluation · 13 cut over, docs, gate, live check.

Order matters: Tasks 2–6 make verification trustworthy BEFORE Task 11 learns from it.

---

## Task 1: Live-shaped Workday fixtures with a state oracle

Rebuild the Workday fixtures from the field notes and give every fixture an **oracle** — `window.__oracle[<field>]`, the value the fake app really holds, never read by the engine. Tests assert on the oracle, so a false "verified" fails.

**Files:**
- Rewrite: `backend/tests/fixtures/browser/workday_search.html`, `workday_listbox.html`, `workday_text.html`, `workday_date.html`
- Create: `backend/tests/fixtures/browser/workday_upload.html`, `workday_sections.html`, `adversarial_revert.html`, `adversarial_same_text.html`
- Modify: `backend/tests/fixtures/browser/README.md` (fixture rule + oracle convention)
- Create: `backend/tests/browser/test_fixture_fidelity.py`
- Existing tests that pinned the OLD fixture shapes (`test_fill_core.py`, `test_research_failures.py`, `test_fill_end_to_end.py`, `test_adaptive_step.py`): mark the ones the new shapes break `@pytest.mark.xfail(strict=True, reason="Task N: <what>")` naming the task that fixes them — do not delete them.

**Fixture behaviours (each from the notes; § = notes section):**

`workday_search.html` (§2) — three widgets, each:
```html
<div data-automation-id="formField-school"><label for="school">School or University*</label>
  <div data-automation-id="multiSelectContainer" data-uxi-widget-type="multiselect">
    <ul data-automation-id="selectedItemList" role="listbox"></ul>
    <div data-automation-id="multiselectInputContainer"><div>
      <input id="school" type="text" data-uxi-widget-type="selectinput"></div></div>
  </div></div>
```
- `#heard` (single; default list = categories "Job Board", "Social Media"), `#school` (single; default list EMPTY), `#skills` (multi; pre-existing pill "SQL").
- Pill: `<li><div data-automation-id="selectedItem" role="option" aria-label="X, press delete to clear value."><div data-automation-id="DELETE_charm"></div><p data-automation-id="promptOption">X</p></div></li>` inside `selectedItemList`. `DELETE_charm` click removes it.
- Press (mousedown on the input) opens `#portal` > `div[data-automation-id=activeListContainer][role=listbox]` — rendered on the next `requestAnimationFrame`.
- Typing alone does NOT search. **`keyup` Enter** with the list open searches; Enter before the list exists is ignored.
- Results REUSE row nodes (update `textContent` of existing rows, append/remove the rest) and arrive in two stages (first row at 100 ms, the rest at 400 ms).
- Row: `div[role=option][data-automation-id=menuItem]` > `[data-automation-id=promptLeafNode]` > `input[type=radio|checkbox][data-automation-id=radioBtn]` + `[data-automation-id=promptOption]` text. A click on the row only sets `aria-selected="true"`. A click on the radio/checkbox commits: single → replace pill, close list, clear input; multi → toggle pill (a second click removes it), list stays open, query stays.
- A search with exactly ONE result commits it on Enter (§2 rule 5). "LinkedIn" returns two identical leaves. School search for "Arlington" returns 8 rows incl. "The University of Texas at Arlington"; a misspelt full name returns a single "No Items." row.
- Skills results are virtualized: 31 results for "SQL", only 8 rows in the DOM; `scroll` on the container re-renders the window; exact "SQL" is #19.
- Oracle: `__oracle.heard|school` = string, `__oracle.skills` = array — set by the radio/checkbox handler only.

`workday_listbox.html` (§3, §8a) — `fieldset > legend(rich text p + abbr*)` + `button[aria-haspopup=listbox][aria-label=" Select One Required"]` + sibling `<input type="text" class="hidden-backing" style="display:none">`; `aria-controls` → `ul[role=listbox] > li[role=option]` (all in DOM, scrollable, 12 degree options incl. "Masters", list opens upward for one field). `li` click: button text + `aria-label` update, backing input gets a 32-char id, oracle set. "Select One" clears the backing and the oracle. An outside click hides the list but leaves `aria-expanded="true"` (§8a).

`workday_text.html` (§1) — `#city`, `#zip` as now, but commit rule = live: `input` events (incl. `execCommand`) update a draft; the value is committed to `__oracle` only on `focusout` when `document.activeElement` is NOT the input; error `<p data-automation-id="errorMessage">` shows when required and not committed.

`workday_date.html` (§6) — `div[data-automation-id=dateInputWrapper][role=group]` with Month/Year spinbutton inputs and display divs. After a Year value is typed the widget moves focus to Month by itself. Validation runs on the WRAPPER's `focusout` only if `document.activeElement` is outside the wrapper: complete → commit to oracle, remove error; incomplete → show `<span>Error: The field From is required and must have a value.</span>` (plain span, no automation id) and set `aria-invalid="true"` on the empty part. Also an MM/DD/YYYY variant with a Day part (Self-Identify).

`workday_upload.html` (§7) — hidden `input[type=file][data-automation-id=file-upload-input-ref]` inside `[data-automation-id=attachments-FileUpload]`; on `change`, after 200 ms render `[data-automation-id=file-upload-item]` with `file-upload-item-name` = filename and "Successfully Uploaded!", then CLEAR the input (`value = ""`). Oracle: `__oracle.files`.

`workday_sections.html` (§5, §4) — sections `div[role=group][aria-labelledby=<h4>]`: "Work Experience" (1 entry "Work Experience 1": Job Title*, Company*, "I currently work here" checkbox with `label[for]`, From*/To* date sections; `[data-automation-id=add-button]` "Add Another"), "Education" (1 entry), "Websites" (0 entries, button "Add"). Add appends "<Section> N" with its required inputs and an unnamed Delete button. Ticking "I currently work here" removes the To field on the next frame.

`adversarial_revert.html` — a popup whose `li` click shows the text but leaves the backing empty on the FIRST pick and reverts the text after 500 ms (models §8a's unexplained revert). `adversarial_same_text.html` — two "Other" options under different visible categories.

**Step 1 — fidelity tests (they drive the fixtures with Playwright's TRUSTED input, proving each fixture behaves as the notes say):** `test_fixture_fidelity.py`, e.g.
```python
def test_search_needs_press_then_enter_and_commits_only_via_the_radio(page, load):
    load(page, fixture_html("workday_search.html"), sources=[])
    page.click("#heard"); page.type("#heard", "LinkedIn"); page.keyboard.press("Enter")
    page.wait_for_selector("[data-automation-id=activeListContainer] [role=option]")
    rows = page.locator("[data-automation-id=activeListContainer] [role=option]")
    assert rows.count() == 2 and rows.nth(0).inner_text() == rows.nth(1).inner_text() == "LinkedIn"
    rows.nth(0).locator("[data-automation-id=promptOption]").click()   # the row text: highlight only
    assert page.evaluate("window.__oracle.heard") in (None, "")
    rows.nth(0).locator("input").click()
    assert page.evaluate("window.__oracle.heard") == "LinkedIn"
```
One such test per behaviour listed above (≈15). Run → PASS (they test the fixtures).

**Step 2:** run the whole browser suite; mark newly failing engine tests xfail-strict with the fixing task. `pytest tests/browser -q -rs` → PASS/XFAIL only.

**Commit:** `test(fill): Workday fixtures rebuilt from the live probe, with state oracles`

---

## Task 2: Enter, leave, key press, errors, money

**Files:** Modify `extension/content/fill-base.js` (`typeText` :214, `invalid` :130, `equivalent` :245, exports :276); `extension/content/fill-core.js` (`blurOut` :90, `write` :97 to use them). Test: `backend/tests/browser/test_fill_base.py`, `test_fill_core.py`.

**Step 1: failing tests**
- `test_text_commits_only_after_leaving_the_field` (workday_text: `apply(op="write")` → `__oracle.city == value`, no error).
- `test_date_leave_blurs_the_part_the_widget_moved_focus_to` (workday_date: write 2026-06 → oracle set, no "Error:" span, `document.activeElement` outside the wrapper).
- `test_leave_does_not_double_fire_when_the_window_has_focus` (count `focusout` listener calls on a plain input with the page focused: exactly 1).
- `test_invalid_sees_a_plain_error_span_and_aria_invalid_on_any_part`.
- `test_money_compares_as_numbers`: `equivalent("80000", "$80,000", {format:"money"})` true; `("80000.50","$80,000.5")` true; `("8000050","$80,000.50")` false; `("80,000","80000")` without format → false (punctuation still meaningful).
Run → FAIL.

**Step 2: implement** (fill-base):
```js
  // Whether the browser itself fired `type` while fn ran (a focused window does).
  const fired = (el, type, fn) => {
    let hit = false;
    const h = () => { hit = true; };
    el.addEventListener(type, h, { capture: true, once: true });
    try { fn(); } finally { el.removeEventListener(type, h, { capture: true }); }
    return hit;
  };
  const activeIn = (el) => el.getRootNode().activeElement ?? document.activeElement;
  // ENTER: real focus, plus the events an unfocused window does not fire.
  const enter = (el, t) => {
    check(t);
    const native = fired(el, "focus", () => el.focus({ preventScroll: true }));
    if (activeIn(el) !== el) throw new Unfocusable();
    if (!native) {
      el.dispatchEvent(new FocusEvent("focus"));
      el.dispatchEvent(new FocusEvent("focusin", { bubbles: true, composed: true }));
    }
  };
  // LEAVE: blur whatever inside the widget holds focus NOW (the page may have
  // moved it), THEN — only if the browser did not — tell the page focus left.
  const leave = (el, widget = el) => {
    const a = activeIn(el);
    const who = a && a !== document.body && widget.contains(a) ? a : el;
    const native = fired(who, "blur", () => who.blur?.());
    if (!native) {
      who.dispatchEvent(new FocusEvent("blur"));
      who.dispatchEvent(new FocusEvent("focusout", { bubbles: true, composed: true, relatedTarget: null }));
    }
  };
  const KEYS = { Enter: 13, Escape: 27, ArrowDown: 40 };
  const keyPress = (el, key, t) => {
    check(t);
    const init = { key, code: key, keyCode: KEYS[key] ?? 0, which: KEYS[key] ?? 0, bubbles: true, cancelable: true, composed: true };
    el.dispatchEvent(new KeyboardEvent("keydown", init));
    el.dispatchEvent(new KeyboardEvent("keyup", init));
  };
  const amount = (s) => {
    const m = /-?\d[\d,]*(?:\.\d+)?/.exec(String(s ?? "").replace(/\s/g, ""));
    return m ? Number(m[0].replace(/,/g, "")) : NaN;
  };
```
- `typeText` calls `enter` instead of `el.focus`; `equivalent` gains `if (format === "money") return Number.isFinite(amount(actual)) && amount(actual) === amount(wrote);`.
- `invalid(el)`: also true when any control in `fieldBox(el)` has `aria-invalid="true"`, or a visible leaf element in `fieldBox(el)` whose text starts with `Error` (`/^error\b/i`).
- `fill-core` `blurOut(el, t)` → `b().leave(el, widgetOf(el))` then `settle(t, 150)`, where `widgetOf` = the date wrapper for date parts, the search box for search shapes, else the element.
- Export `enter, leave, keyPress, amount`.
Run → PASS; un-xfail the Task 2 tests.

**Step 3:** loop passes `format: "money"` for salary slots: `fill-loop.js:757` becomes a `formatOf(slot)` helper (`/phone/i` → phone, `/salary|compensation|pay/i` on the slot name → money). Loop test `test_salary_slots_write_with_money_format`.

**Commit:** `fix(companion): enter and leave fields the way Workday commits them; money and error proof`

---

## Task 3: Committed evidence per shape

**Files:** Modify `extension/content/shapes.js` (`box` :97, `widgetRoot` :110, `backing` :117, `chips` :118, `searchMulti` :119, popup `read` :305); `extension/content/fill-core.js` (`verify` :73, `choose` :327). Test: `test_inventory.py`, `test_fill_core.py`.

**Step 1: failing tests**
- `test_search_pills_are_read_from_the_multiselect_container` (workday_search, pre-existing "SQL" → inventory `committed == ["SQL"]`, `multi` true for skills, false for school).
- `test_popup_evidence_is_the_backing_input_changing` — choose "Masters" on the degree popup → verified; on `adversarial_revert.html` the first pick → `outcome == "unconfirmed"` (text shows, backing unchanged), and `__oracle` empty.
- `test_placeholder_pick_clears_the_evidence`.
Run → FAIL.

**Step 2: implement**
- `SEARCH_BOX` += `[data-uxi-widget-type="multiselect"]`; `box(el)` = `el.parentElement?.closest(SEARCH_BOX)` (never the element itself) else the existing ancestor walk; `searchMulti` true when the box is `multiselect` AND its `selectedItemList` allows several — decide from the fixture: `#skills` has `aria-multiselectable` or pre-existing pills >1; if unknown, read the widget: multi when a tick leaves the list open (record in `lastState`). Keep it simple: treat `multiselect` as multi only when the inventory's field question/section or the popup rows hold checkboxes (rows with `input[type=checkbox]` ⇒ multi). Document the rule in a comment.
- New `shape.evidence(el)` → `{ display, proof }`: search → `{display: pills, proof: pills}`; popup → `{display: button text, proof: backingOf(el)?.value ?? null}` where `backingOf` = a non-visible `input` in the button's parent or the field box with no other control; text/date → `{display: value, proof: value}`; group → checked state.
- `choose` snapshots `before = shape.evidence(el)` before its gesture. `verify(el, shape, expected, {before})`: display must match expected (existing rules) AND, when `proof` is non-null, proof must be non-empty and different from `before.proof` (unless it already matched). Display matches but proof did not change → `"unconfirmed"` (new verify result). Page rows carry it as `outcome: "unconfirmed"`.
Run → PASS.

**Commit:** `fix(companion): verify by each widget's committed evidence, not by what it shows`

---

## Task 4: One controller per field (loop)

**Files:** Modify `extension/shared/fill-loop.js` (header vocab :43-61, `limits` :70-80, `FINAL`/`DONE` :89-91, `done`/`fail` :174-190, `adapt` :349, `settle` :400, `commitOne` :414, `sweep` :670, `settledDone` :686, telemetry :805-839); `extension/content/fill-ops.js` (`sweep` :170, `explore` :98); `extension/content/fill-core.js` (`explore` :241); `extension/panel/stages/fill.js` (:500-507) and `panel/actions/fill.js` (:197-198); `backend/app/schemas/autofill_telemetry.py` (+ `unconfirmed`, `unsupported`); `backend/app/services/autofill_telemetry.py` (`FAILURE_OUTCOMES`). Tests: `test_fill_loop.py`, `test_fill_core.py`, `test_autofill_telemetry_summary.py`, `test_extension_panel_fill.py`.

**Step 1: failing tests**
- Loop: `test_an_unconfirmed_commit_is_reported_as_unconfirmed_never_filled` (apply → `{outcome:"unconfirmed"}` → report status `unconfirmed`).
- `test_a_reverted_field_gets_exactly_one_recommit` (sweep reports the field reverted twice → one extra `fill_apply` for it, final status `unconfirmed`, reason `unstable`).
- `test_every_proposal_source_shares_the_field_budget` (a field whose commit and 8 adaptive steps would exceed `FIELD_MS` stops at the deadline with `cannot_operate/timeout`).
- `test_a_failed_state_move_pair_is_not_retried` (step proposes the same `mid` on the same state version twice → the second is not executed; history carries `already_failed`).
- `test_a_widget_that_ignores_every_input_is_unsupported` (all attempts return `reason:"no_effect"` → status `unsupported`).
- Page: `test_explore_undoes_a_pick_that_enter_committed` (workday_search school "Analytics"-style single hit: explore returns options, `__oracle.school` back to empty, pills unchanged) and `test_explore_reports_a_commit_it_could_not_undo`.
- Telemetry: new outcomes accepted and partitioned (unconfirmed, unsupported → FAILURE).
Run → FAIL.

**Step 2: implement**
- Statuses: add `unconfirmed` and `unsupported` to `FINAL`; neither is in `DONE`. Report groups: `unconfirmed` → "Filled but not confirmed — check" (list with jump), `unsupported` → joins "Couldn't operate these controls" with the sub-reason "doesn't accept automated input".
- Row gets `recommits` (0/1). `sweep()`: a reverted DONE row with `recommits === 0` → `retry` with `recommits = 1`; a second revert → `done(f, "unstable")` → `unconfirmed`. `settledDone` waits a quiet period (`limits.QUIET_MS = 600`) before the final sweep.
- Row keeps `failedMoves: Set("<version>:<mid>")`; `adapt` skips a candidate already failed on the same version and appends history `already_failed`.
- Page ops return `reason: "no_effect"` when after every gesture neither the evidence, nor the popup set, nor the input value changed; two consecutive `no_effect` rows for one field → `unsupported`.
- `fill-core.explore`: `const before = shape.evidence(el)` at start; after `tidy`, if `evidence.proof` changed, undo: click the new pill's `[data-automation-id=DELETE_charm]`, else an element inside the new pill whose `aria-label`/`data-automation-id` matches `/delete|remove|clear/i`, else the pill itself (pills that un-pick on click); re-read; if still changed return `{ ..., error: "committed_while_exploring", committed }` and the loop finishes the field `needs_answer` with that reason.
- Telemetry: `TELEMETRY_OUTCOME.unconfirmed = "unconfirmed"`, `.unsupported = "unsupported"`; schema Literal + `FAILURE_OUTCOMES`; update `extension/INTERNALS.md:508` vocabulary list.
Run → PASS.

**Commit:** `feat(companion): one controller per field — shared budget, undo, one re-commit, honest outcomes`

---

## Task 5: The search-and-pick sequence

**Files:** Modify `extension/content/fill-core.js` (`open` :160, `typeQuery` :154, `waitOptions` :138, `readAll` :181, `findOption` :196, `match` :62, `GESTURES` :315, `choose` :327, `set` :383, `stepState`/`move` search moves :506-641). Test: `test_fill_core.py`, `test_adaptive_step.py`, `test_research_failures.py` (un-xfail).

**Step 1: failing tests** (all on the rebuilt `workday_search.html`, asserting the ORACLE):
- `test_search_presses_then_types_then_enters` (heard: explore "LinkedIn" → options `["LinkedIn"]` after identical collapse, oracle still empty).
- `test_identical_leaves_are_one_option_and_commit_the_first` (choose "LinkedIn" → oracle "LinkedIn").
- `test_same_text_under_different_categories_is_ambiguous` (adversarial_same_text → `unexpected/ambiguous`, nothing committed).
- `test_streamed_results_are_read_after_they_settle` (school "Arlington" → all 8, choose "The University of Texas at Arlington" → oracle exact; never "Arlington Baptist College").
- `test_a_single_hit_that_enter_committed_is_verified_not_clicked_again`.
- `test_virtualized_results_are_scrolled_to_the_option` (skills "SQL" → oracle contains "SQL" exactly once; "Python" added the same way; pre-existing kept).
- `test_a_tick_is_never_repeated_before_the_redraw` (instrument checkbox clicks: exactly one per item).
- `test_the_row_is_never_clicked_when_it_holds_a_checkable` (count row-level clicks = 0).
- `test_enter_is_only_sent_to_search_widgets` (a plain text input inside a `<form>` never receives keydown Enter from any op).
Run → FAIL.

**Step 2: implement**
- `open` for `shape.open === "search"`: `enter(el)`; `press(el)`; `waitFor(list container owned by el, OPEN_MS)`; `typeText(el, term)`; `keyPress(el, "Enter")`; then `waitSettled(pop)`:
```js
  // Settled: nothing busy and the option texts unchanged for QUIET_MS.
  const waitSettled = async (el, before, t) => {
    let last = null; let since = Date.now();
    return b().waitFor(() => {
      const p = own(el, before);
      if (!p || busy(p)) { last = null; since = Date.now(); return null; }
      const sig = b().optionsOf(p).map((o) => o.text).join("\n");
      if (sig !== last) { last = sig; since = Date.now(); return null; }
      return Date.now() - since >= QUIET_MS ? p : null;
    }, OPEN_MS, t);
  };
```
  (`QUIET_MS = 250`; `EMPTY_MS` path kept for an honest empty list.) The old "type into a search box inside the popup" path (react-select, `popup_with_search.html`) is kept: the Enter is sent only when the widget is a Workday `selectinput` OR the typed box has `role="combobox"`/`aria-autocomplete`, and never to a plain text input.
- After Enter: re-read `shape.evidence(el)`; if it now equals the wanted text → `verified` without clicking.
- `match`: identical texts collapse to the first ONLY when every hit shares the same visible category path (ancestor group label / `aria-level` / preceding group header); otherwise return `ambiguous`.
- Gesture: `const target = o.querySelector('input[type=radio], input[type=checkbox]') ?? o;` then `target.click()` (the existing `press` stays the fallback for options without a checkable). Re-find by text immediately before clicking.
- `findOption`/`readAll`: scroll the list container (`scrollerOf`) and wait for a frame (`await new Promise(requestAnimationFrame)` then `settle`) between reads.
- `set`: per item — type over the query (no ×), Enter, settle, re-find, click the checkbox once, then `waitFor` the pill to appear (≤ OPEN_MS) before the next item; never click an item whose checkbox is checked or whose pill exists.
- Adaptive `search:value`/`search:word:n` moves use the same helper.
Run → PASS; remove the Task 5 xfails, drop `WITHOUT_SEARCH` in `test_fill_end_to_end.py` so every e2e test composes all `FIXTURES` again, and restore the commented Stop assert (`grep -rn "Task 5: restore" backend/tests/browser` finds every spot).

**Commit:** `fix(companion): Workday search-and-pick — press, Enter, settle, click the checkable`

---

## Task 6: Popups, checkboxes and dependencies

**Files:** Modify `extension/content/fill-base.js` (`engineOpen` :264, `closePopups` :187); `extension/content/fill-core.js` (`choose` popup path); `extension/shared/fill-loop.js` (round body :699-776). Test: `test_fill_core.py`, `test_fill_loop.py`, `test_fill_end_to_end.py`.

**Step 1: failing tests**
- `test_popup_open_state_is_judged_by_visibility` (after an outside click on workday_listbox, `engineOpen()` false although `aria-expanded="true"`).
- `test_a_long_popup_commits_an_option_below_the_fold` (degree "Masters").
- `test_currently_employed_is_ticked_before_the_dates` (workday_sections: map gives `experience.0.current = Yes` and start/end dates → the checkbox is committed first; the To field disappears; no write is attempted to it; report has no `stale` row for it).
- `test_fields_added_or_removed_by_a_commit_are_re_observed_before_continuing` (after the tick, the loop re-inventories before the next field of that section).
- `test_a_placeholder_option_is_never_offered_as_an_answer` — live Workday lists "Select One" as an option (§3a, §8b): `explore`, `stepState` candidates and the options sent to `/pick` drop every option for which `ns.isPlaceholderText(text)` is true; choosing "Select One" stays possible only as the engine's own undo. Un-xfails the three Task 1 xfails attributed to Task 6.
- `test_the_category_path_runs_end_to_end` — extend `test_fill_end_to_end.py` with the generic `CATEGORY_POPUP` page (`tests/browser/pages.py`) so the category descent through the real `/api/autofill/step` driver is covered again with both halves running.
Run → FAIL.

**Step 2: implement**
- `engineOpen`/`closePopups`: open ⇔ `visible(p)`; ignore `aria-expanded`.
- Placeholder options: filter `ns.isPlaceholderText` options out of `optionsOf` results used for explore/pick/step (keep them reachable for undo).
- Loop ordering: within a round, sort choice fields so a lone checkbox whose mapped slot ends in `.current` precedes text/date fields of the same `section`+`repeatIndex`. After any commit, compare the frame's field-id set (a cheap `fill_inventory` with `{peek:true}` returning fids only); if it changed, re-observe before the next field.
Run → PASS.

**Commit:** `fix(companion): popups by visibility; tick "currently" before dates; re-observe after structural commits`

---

## Task 7: Add sections

**Files:** Create `extension/content/sections.js` (add to `manifest.json` before `agent.js`, and to `ENGINE_SOURCES` in `tests/browser/conftest.py`); modify `extension/content/fill-ops.js` (+ `sections()`, `add(sid)`), `extension/content/agent.js` (+ `fill_sections`, `fill_add` handlers), `extension/sw.js` (`BROADCASTABLE`), `extension/shared/fill-loop.js` (a pre-pass); backend `backend/app/routers/autofill.py` + `backend/app/services/autofill_sections.py` + schema in `backend/app/schemas/autofill_fill.py`. Tests: `backend/tests/browser/test_sections.py`, `test_fill_loop.py`, `backend/tests/test_autofill_sections.py`.

**Step 1: failing tests**
- Page: `test_sections_lists_repeating_groups_with_their_entries_and_add_button` (workday_sections → `[{sid, heading:"Work Experience", entries:1, filled:[…], add:"Add Another"}, {heading:"Education",…}, {heading:"Websites", entries:0, add:"Add"}]`).
- Page: `test_add_presses_only_the_sections_own_add_button_and_never_delete`.
- Backend: `test_sections_maps_headings_to_profile_lists` (Jev choice per heading over kinds `experience | education | languages | websites | certifications | none`, fast fallback) and returns `wanted` = count of profile entries with the facts their required fields need (websites: `personal.website`, `personal.github`; the LinkedIn box is not a section).
- Loop: `test_the_loop_adds_entries_the_profile_can_fill_then_fills_them` (2 jobs in profile, 1 entry on page → one `fill_add`, re-inventory, both entries filled) and `test_an_entry_already_holding_data_is_reconciled_not_duplicated` and `test_add_never_exceeds_what_the_profile_can_fill`.
Run → FAIL.

**Step 2: implement**
- `sections.js`: a section = an element with `role=group` + `aria-labelledby` heading, or a heading followed by entries titled "<Heading> <n>", that owns a button whose text is /^add( another)?\b/i (or `data-automation-id=add-button`). Entries = child groups titled "<Heading> <n>"; `filled` = which entries hold any committed value. Never returns a Delete/Remove control.
- `POST /api/autofill/sections` `{sections:[{sid, heading, entries, filled}]}` → `{sid: {kind, wanted}}` (labels only; counts from the fact catalog).
- Loop pre-pass (each round, before `/map`): `add = max(0, wanted - entries)`; press `fill_add` `add` times (one at a time, re-inventory after each; stop if the entry count did not grow). Entries are matched to profile entries in order (empty entries first, entries already holding data keep theirs — the map sees `repeatIndex` and the catalog's `experience.<i>` descriptions).
Run → PASS.

**Commit:** `feat(companion): add repeating entries the profile can fill`

---

## Task 8: Attach proof

**Files:** Modify `extension/content/agent.js` (`attachResumePdf` :190). Test: extend `backend/tests/browser/test_fill_end_to_end.py` or a new `test_attach.py` using the real `agent.js` handler route and `workday_upload.html`.

**Step 1: failing test** `test_an_upload_the_page_accepted_counts_even_after_it_cleared_its_input` (attach → returns 1, oracle holds the file; and `test_an_upload_the_page_refused_still_counts_zero` with a variant that removes the file row).

**Step 2: implement** — after the existing settle, an input counts when `input.files?.length === 1` OR, within its upload widget (nearest ancestor holding the input and ≤ 3 levels up), an element whose text contains the filename appeared after the write (snapshot the widget's text before). Keep the `expect` refusal and the detached-node rule; update the long comment to say why `files` alone under-counts on Workday.

**Commit:** `fix(companion): count an upload by the page's own file row`

---

## Task 9: Meaning — derived facts, money, reasoning route, low-stakes (+ original Task 9 UI)

**Files:** `backend/app/services/autofill_catalog.py` (`_DESCRIBES` :37, `build` :140); `backend/app/services/autofill_map.py` (`_LOW_STAKES` :45, `_NEVER_LOW_STAKES` :48, `_route` :145, `map_fields` :168); `backend/app/services/autofill_pick.py`; `backend/app/schemas/autofill_fill.py` (`Route` + `reasoned`, `Mapped.format`); `extension/shared/fill-loop.js` (`formatOf` from Task 2 → prefer `mapped.format`); `frontend/components/settings/autofill-section.tsx` (`CompanionPermissions` :1042), `frontend/lib/types.ts`. Tests: `backend/tests/test_autofill_catalog.py`, `test_autofill_map.py`, `test_autofill_pick.py`, `test_frontend_settings_cards.py`, `test_fill_loop.py`.

**Step 1: failing tests**
- Catalog: `derived.full_name` ("<first> <last>"), `derived.today` (ISO date, injectable clock), `derived.us_citizen` from `work_auth.status` ("citizen" → Yes; any visa/OPT/green card → No; unknown → absent) with describe "derived from your work-authorization status", `preferences.earliest_start_date` = today when the stored value reads as immediate (`/immediate|asap|now|immediet/i`), `preferences.desired_salary` describe includes "desired salary, compensation or salary requirements".
- Map: `Mapped.format` = `phone` for phone slots, `money` for salary slots, else null.
- Reasoning route: a choice field with route `none` whose question the fast model judges answerable from the resume (government employment, clearance, relevant experience years) → route `reasoned`; `/pick` for `reasoned` uses the fast model with the employment blocks and returns `assumed` only on POSITIVE evidence (test: no clearance in resume → abstain, not "No"; TCS/Seinun + "employed by a US government agency in the last 5 years" → "No" with reason `assumed`).
- Low-stakes: `_LOW_STAKES` gains relocation/travel/drug-test willingness, SMS/marketing contact consent, "related to / previously employed here", and job-description self-assessment yes/no ("do you have the required experience", "meet the educational requirement"); `_NEVER_LOW_STAKES` becomes: factual education/experience entries, work authorization, sponsorship, EEO, background/criminal, clearance, salary, legal attestations/signatures. A profile fact always wins.
- Frontend (old Task 9): switch `id="low-stakes"`, label "Answer low-stakes questions for me", GET/PUT `/api/settings/autofill-options`, help text listing the widened examples and the never list. Pins in `test_frontend_settings_cards.py`.
Run → FAIL.

**Step 2: implement** as specified; keep derived facts in their own `derived.*` section so the map describes them honestly. The reasoning route is a single fast-model call per round for all `reasoned` fields (`fast_json`), same floors, answers `assumed` (listed to check).

**Commit:** `feat(autofill): derived facts, money format, reasoning route, wider low-stakes and its switch`

---

## Task 10: Languages in the profile

**Files:** `frontend/components/settings/autofill-section.tsx` (+ `LANGUAGE_FIELDS`, a Languages fieldset modelled on Education :898-945), `frontend/lib/types.ts`; `backend/app/services/autofill_catalog.py` (`_languages`); schema docs if any. Tests: `backend/tests/test_autofill_catalog.py`, `test_frontend_settings_cards.py`, loop test with a Languages section (Task 7 kinds).

**Step 1: failing tests** — catalog emits `languages.<i>.{language, read, speak, write, native, fluent}` (levels as the words forms show: Basic / Intermediate / Fluent; `native` and `fluent` separate Yes/No); the editor renders "Languages" with Add/Remove like Education and saves under `languages` in the same PUT `/api/settings/autofill` body.

**Step 2: implement.** Profile JSON is loose, so no migration; `languages` is a list of dicts, most important first.

**Commit:** `feat(profile): languages with read/speak/write levels`

---

## Task 11: Recipe memory (value-free)

**Files:** Create `extension/content/recipes.js` (signature), modify `extension/content/fill-core.js` (`choose`/`set`/`write` accept a `variant` order and report the variant that verified), `extension/content/fill-ops.js` (pass through), `extension/shared/fill-loop.js` (consult/update via `deps.recipes`), `extension/panel/panel.js` (`KEY`, `STORE_DEFAULTS`, `readStore`/`writeStore`, a "Forget learned widget moves" control; document the key per the file's storage rule), `extension/INTERNALS.md`. Tests: `backend/tests/browser/test_recipes.py`, `test_fill_loop.py`, a panel source pin.

**Variants the engine knows** (the generic order first): `open: press|type`, `search: enter|debounce`, `click: checkable|row`, `leave: active|self`. A recipe is an ordering of these per widget family, plus lifecycle counters.

**Signature** (`recipes.js`): hash of shape name + tag + role + the NAMES of `data-automation-id` / `data-uxi-widget-type` values on the element and ancestors up to the field box (GUID-like tokens `/[0-9a-f]{16,}/i` stripped) + whether it has `aria-controls` + popup kind + single/multi + evidence kind + `ENGINE_VERSION`. Never labels, values, option text, URLs. Origin override key = signature + a hash of the origin.

**Lifecycle** (panel-side store `fill.recipes`, bounded to 200 entries LRU): first verified success → `probation`; promoted to `trusted` after 2 successes that survived the final sweep on one origin; family-level `trusted` needs successes on ≥2 origins; any contradiction (the recipe's variant produced unconfirmed/reverted) → `demoted` (not used) and a structural mismatch → `quarantined`; entries unused for 60 days expire. A recipe only REORDERS variants; verification is unchanged.

**Step 1: failing tests** — `test_a_verified_variant_is_learned_and_tried_first_next_time` (warm run tries the learned variant first: fewer gestures), `test_a_lucky_false_verify_is_not_learned` (a success that the final sweep found reverted never promotes), `test_recipes_hold_no_values_labels_or_urls` (serialize the store; assert none of the fixture's labels/values/host appear), `test_forget_clears_the_store`.

**Step 2: implement.**

**Commit:** `feat(companion): remember which moves worked per widget family (value-free, clearable)`

---

## Task 12: Evaluation

Carries the original Task 10 Step 2 unchanged (mapping agreement, ~40 labelled picks, ~20 labelled steps, both engines reported separately, zero wrong writes on exact-policy cases) PLUS:
1. **Oracle gate:** `pytest tests/browser -q -rs` — every fixture test asserts on `__oracle`; zero false "verified", zero wrong writes; every run terminates within `RUN_MS`.
2. **Adversarial set:** `adversarial_*.html` (revert, same text, a widget that ignores synthetic input → `unsupported`, recipe poisoning).
3. **Cold vs warm:** run the end-to-end fixture twice with a shared recipe store; report gestures and wall time per run.
4. Labelled cases add: "Masters of Business analytics"→"Masters", "no"→"Not Applicable", "Asian"→"Asian (Not Hispanic or Latino) (United States of America)", government-employment reasoning, JD self-assessment (low-stakes on/off).
**Gate:** show the owner the reports. **Commit:** `chore(autofill): evaluate the revised engine`

---

## Task 13: Cut over, document, gate, live check

Carries the original Task 10 Steps 3–5 (ask about the "Saved answers only" mode first; delete the rule-pass files and tests after porting surviving scenarios; SYSTEM.md grooming at the cap, INTERNALS, §12 gotchas; full gate; live check) with these additions:
- SYSTEM.md §12 gotchas (≤3 lines each, dated 2026-09-26): **Leaving a Workday field** (blur the focused element inside the widget first, then the events); **Workday search needs a press and a key-up Enter; the row is not the control**; **A popup pick shows before it saves** (backing input is the proof); **Workday empties the file input after a good upload**.
- §6 invariant + `.system_md_enforcement.json`: "a fill is reported only when its committed evidence changed" → `tests/browser/test_fixture_fidelity.py` + the oracle tests.
- INTERNALS: the controller, outcomes (`unconfirmed`, `unsupported`), Add pre-pass, recipes (storage key, lifecycle, clear control).
- Live check (owner): Workday (every step, incl. a tenant with Self-Identify) and one Greenhouse form, cold then warm (recipes); record per step the report groups, `unconfirmed`/`unsupported` rows, adds, gestures and wall time. Anything wrong becomes a fixture + failing test before it is fixed.

**Commits:** as in the original Task 10.
