# Companion Fill Engine Implementation Plan (hybrid)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace Companion's label-rule fill with an AI-first engine that works on any application page: AI decides every field's meaning and option, generic code does the mechanics, and when a widget surprises the generic path, Jev picks the next move from moves code lists. Only verified fills are reported; nothing stalls.

**Architecture:** Page frames get one field reader, an inventory with element-bound ids, and one generic mechanics module (`fill-core.js`: text-like commit, choice-like explore/commit, committed-value readers per shape, adaptive-step state and moves, real cancellation). The panel runs a bounded loop: inventory → `/map` → explore → `/pick` → commit → adaptive `/step` when unexpected → sweep → re-observe. Backend adds a fact catalog and `/map`, `/pick`, `/step` on Jev with the fast model as a same-floors fallback.

**Tech stack:** Plain-JS MV3 content scripts (no build), FastAPI + Pydantic, Jev System One (`app/services/jev.py`), pytest + a new Python Playwright (Chromium) suite, Next.js settings UI.

**Design doc:** `docs/plans/2026-09-25-fill-engine-design.md` (hybrid revision). Read SYSTEM.md first, then `extension/INTERNALS.md` § "How the fill behaves".

**Goal card (for any executor):**
- Owner's goal: "the extension was not always working good … to be able to work on any kind of job filling page."
- Owner decisions: AI-first, no label rules/aliases/exact-match shortcut; hybrid mechanics (generic path + adaptive step); leftovers listed with jump-to-field; low-stakes setting default off; never stall; no interim patch to today's fill; navigation and Submit stay human.
- When the plan and reality disagree, prefer the goal and these decisions; log the deviation in the commit message and tell the owner.

**Environment (SYSTEM.md §9):**
- Backend tests: `cd backend && /opt/anaconda3/bin/python3 -m pytest tests/ -q`; browser suite: `tests/browser -q`.
- Browser tests need Python Playwright + Chromium (owner laptop has Playwright 1.49 and `~/Library/Caches/ms-playwright/chromium-1243`). They skip locally when absent and FAIL in CI.
- Frontend: `cd frontend && npx tsc --noEmit && npm run lint`.
- SYSTEM.md gate: `python3 scripts/check_system_md.py` (cap 1000; file is at 994 — Task 10 grooms first).
- Commit after each step group marked **Commit**. Never push. Owner merges to local main and tests live (extension reload + tab reload; backend changes need `docker compose up -d --build backend`).

**Jev API (verified 2026-09-25):** `POST {base}/v1/systemone` `{model, state, questions}`. Choice `{"type":"choice","instructions","criteria":{key: text}}` → `{choice, probabilities, confidence}` (validate with `jev.choice_of`). Noul `{"type":"noul","instructions"}` → `{"type":"noul","noul": p}`. ≤255 Choice options incl. sentinels.

**House rules:** content scripts are IIFEs publishing on `window.careerStudioCompanion` (`ns`) and read each other at call time; new content files go into `extension/manifest.json` before `content/agent.js`; page text is data (every model question includes `_PAGE_TEXT_IS_DATA` from `autofill_choose.py`) and models only ever choose among ids code generated; telemetry carries no values.

**Codex review fixes built in (2026-09-25):** verify runs after the final blur and treats a field error as not filled; sets are verified only when complete (else `partial`); page operations are cancellable (a late click cannot land); actions carry a field fingerprint checked before acting; the fast-model fallback returns a confidence and meets the same floors.

**Task map:** 1 corpus · 2 field reader + primitives · 3 shapes + inventory · 4 generic mechanics + page ops · 5 backend decisions · 6 adaptive step · 7 loop · 8 panel + telemetry · 9 low-stakes setting · 10 evaluate, cut over, document.

---

## Task 1: Real-browser corpus — harness, fixtures, the six research failures

**Files:**
- Modify: `backend/pyproject.toml` (`dev` += `"playwright>=1.49"`), `.github/workflows/ci.yml`
- Create: `backend/tests/browser/__init__.py`, `backend/tests/browser/conftest.py`
- Create: `backend/tests/fixtures/browser/README.md` and the fixtures below
- Create: `backend/tests/browser/test_fixture_privacy.py`, `backend/tests/browser/test_research_failures.py`

**Step 1: Harness** — `backend/tests/browser/conftest.py`:

```python
"""Real Chromium for the fill engine.

The fake-DOM harness (tests/extension_harness.py) cannot tell whether a
React-controlled box accepted a value, whether a popup belongs to the widget
that opened it, or whether a click committed. These tests load the REAL content
scripts (main world, via add_script_tag, as the research probe did) into
offline fixture pages. agent.js (the only chrome.* user) is never loaded.

Skip locally without Playwright/Chromium; FAIL in CI (tests/node_ts.py rule).
"""

import os
from pathlib import Path

import pytest

EXTENSION = Path(__file__).resolve().parents[3] / "extension"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "browser"

# Dependency order, mirrors manifest.json. Tasks append as files land.
ENGINE_SOURCES: list[str] = [
    "shared/policy.js",
]


def _unavailable(why: str):
    if os.environ.get("CI"):
        pytest.fail(why)
    pytest.skip(why)


@pytest.fixture(scope="session")
def browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        _unavailable("playwright is not installed")
    with sync_playwright() as p:
        try:
            chromium = p.chromium.launch(headless=True)
        except Exception as exc:
            _unavailable(f"chromium is not installed: {exc}")
        yield chromium
        chromium.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = context.new_page()
    yield pg
    context.close()


def fixture_html(name: str) -> str:
    return (FIXTURES / name).read_text()


@pytest.fixture
def load():
    def _load(pg, html: str, sources: list[str] | None = None):
        pg.set_content(html)
        for src in sources if sources is not None else ENGINE_SOURCES:
            pg.add_script_tag(content=(EXTENSION / src).read_text())
        return pg

    return _load
```

`ci.yml`, after the Python dependency install step:

```yaml
      - name: Install Chromium for the extension browser tests
        run: |
          cd backend
          python -m playwright install --with-deps chromium
```

**Step 2: Fixtures** — `backend/tests/fixtures/browser/`. Each reproduces a widget's BEHAVIOUR observed live, never its captured DOM, never personal data. `README.md`:

```markdown
# Browser fixtures

Hand-written offline pages that reproduce how a live ATS widget BEHAVES (what it
accepts, when it validates, where its popup renders, how it closes). Never
captured DOM; never real names, emails, phone numbers or addresses
(test_fixture_privacy.py enforces it).
```

`workday_text.html` — state takes only TRUSTED input; validates on focus-out; Postal Code starts with text Workday never accepted:

```html
<div data-automation-id="formField-city">
  <label for="city">City*</label>
  <input id="city" type="text" aria-required="true">
  <p data-automation-id="errorMessage" id="city-err" hidden>Error: The field City is required and must have a value.</p>
</div>
<div data-automation-id="formField-zip">
  <label for="zip">Postal Code*</label>
  <input id="zip" type="text" value="00000" aria-invalid="true">
  <p data-automation-id="errorMessage" id="zip-err">Error: The field Postal Code is required and must have a value.</p>
</div>
<script>
  window.committed = {};
  for (const id of ["city", "zip"]) {
    const input = document.getElementById(id);
    const err = document.getElementById(`${id}-err`);
    input.addEventListener("input", (e) => { if (e.isTrusted) window.committed[id] = input.value; });
    input.addEventListener("focusout", () => {
      const ok = Boolean(window.committed[id]) && window.committed[id] === input.value;
      err.hidden = ok;
      input.setAttribute("aria-invalid", ok ? "false" : "true");
    });
  }
</script>
```

`workday_date.html` — month/year sections; leaving the widget half-written discards the month:

```html
<fieldset><legend>From*</legend>
  <div data-automation-id="dateInputWrapper" id="from">
    <input data-automation-id="dateSectionMonth-input" aria-label="Month" id="m">
    <input data-automation-id="dateSectionYear-input" aria-label="Year" id="y">
  </div></fieldset>
<label for="n">Graduation date</label><input id="n" type="month">
<label for="p">End date</label><input id="p" placeholder="MM/YYYY">
<script>
  const box = document.getElementById("from");
  box.addEventListener("focusout", (e) => {
    if (box.contains(e.relatedTarget)) return;
    const m = document.getElementById("m"), y = document.getElementById("y");
    if (m.value && !y.value) m.value = "";
  });
</script>
```

`workday_listbox.html` — portaled popup with no ARIA link, Escape ignored, outside click closes, a category option replaces the list with its children:

```html
<fieldset><legend>How did you hear about us?</legend>
  <button id="heard" aria-haspopup="listbox" aria-label=" Select One Required">Select One</button></fieldset>
<fieldset><legend>Are you legally authorized to work in the United States?</legend>
  <button id="auth" aria-haspopup="listbox" aria-label=" Select One Required">Select One</button></fieldset>
<ul role="listbox" id="stale" style="display:none"><li role="option" id="stale-ca">Canada</li></ul>
<div id="portal"></div>
<script>
  const TREES = {
    heard: [["Job Board", ["LinkedIn", "Indeed"]], ["Social Media", ["Twitter"]], ["Employee Referral", null]],
    auth: [["Yes", null], ["No", null]],
  };
  const portal = document.getElementById("portal");
  let open = null;
  const close = () => { portal.innerHTML = ""; open = null; };
  const render = (btn, items) => {
    portal.innerHTML = "";
    const ul = document.createElement("ul");
    ul.setAttribute("role", "listbox");
    for (const [label, kids] of items) {
      const li = document.createElement("li");
      li.setAttribute("role", "option");
      li.textContent = label;
      li.addEventListener("click", (e) => {
        e.stopPropagation();
        if (kids) render(btn, kids.map((k) => [k, null]));
        else { btn.textContent = label; close(); }
      });
      ul.append(li);
    }
    portal.append(ul);
    open = btn;
  };
  for (const id of Object.keys(TREES)) {
    const btn = document.getElementById(id);
    btn.addEventListener("click", (e) => { e.stopPropagation(); render(btn, TREES[id]); });
  }
  document.body.addEventListener("click", () => { if (open) close(); });
  document.getElementById("stale-ca").addEventListener("click", () => { window.staleHit = true; });
</script>
```

`workday_search.html` — `selectinput` / `multiselectinput`: results ~300 ms after typing with a "Searching…" row first, portaled, a pick becomes a pill and clears the box, Escape ignored:

```html
<div data-automation-id="formField-school"><label id="school-l">School or University*</label>
  <div data-uxi-widget-type="selectinput"><div data-automation-id="selectedItemList" id="school-pills"></div>
  <input id="school" data-automation-id="searchBox" aria-labelledby="school-l"></div></div>
<div data-automation-id="formField-skills"><label id="skills-l">Type to Add Skills</label>
  <div data-uxi-widget-type="multiselectinput"><div data-automation-id="selectedItemList" id="skills-pills">
    <div data-automation-id="selectedItem">SQL</div></div>
  <input id="skills" data-automation-id="searchBox" aria-labelledby="skills-l"></div></div>
<div id="portal"></div>
<script>
  const DATA = {
    school: ["University of Texas at Austin", "University of Texas at Dallas", "Texas A&M University"],
    skills: ["Python", "Python (Programming Language)", "SQL", "Tableau"],
  };
  const portal = document.getElementById("portal");
  let timer = null;
  const close = () => { portal.innerHTML = ""; };
  for (const id of Object.keys(DATA)) {
    const input = document.getElementById(id);
    const pills = document.getElementById(`${id}-pills`);
    input.addEventListener("input", () => {
      clearTimeout(timer);
      portal.innerHTML = `<div role="listbox"><div role="option">Searching…</div></div>`;
      timer = setTimeout(() => {
        const q = input.value.toLowerCase();
        const hits = DATA[id].filter((o) => q && o.toLowerCase().includes(q));
        if (id === "school") hits.push("Not in List");
        portal.innerHTML = `<div role="listbox">${hits.map((h) => `<div role="option">${h}</div>`).join("")}</div>`;
        for (const opt of portal.querySelectorAll("[role=option]")) {
          opt.addEventListener("click", (e) => {
            e.stopPropagation();
            const pill = `<div data-automation-id="selectedItem">${opt.textContent}</div>`;
            if (id === "school") pills.innerHTML = pill;
            else if (![...pills.children].some((p) => p.textContent === opt.textContent)) pills.insertAdjacentHTML("beforeend", pill);
            input.value = "";
            close();
          });
        }
      }, 300);
    });
  }
  document.body.addEventListener("click", close);
</script>
```

`react_select.html` — Greenhouse React-Select: typing filters; menu portaled and linked by `aria-controls` only while open; a pick replaces the placeholder with `.select__single-value`; blur clears search text; `window.rejectClicks` makes option clicks no-ops:

```html
<label id="lbl" for="country">Country*</label>
<div class="select__container"><div class="select__control"><div class="select__value-container">
  <div class="select__placeholder">Select...</div>
  <input id="country" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-labelledby="lbl">
</div></div></div>
<div id="menu-root"></div>
<script>
  const OPTIONS = ["United States", "United Kingdom", "India", "Canada"];
  const input = document.getElementById("country");
  const menuRoot = document.getElementById("menu-root");
  const valueBox = input.parentElement;
  window.rejectClicks = false;
  const closeMenu = () => { menuRoot.innerHTML = ""; input.removeAttribute("aria-controls"); input.setAttribute("aria-expanded", "false"); };
  const pick = (text) => {
    valueBox.querySelector(".select__placeholder, .select__single-value").outerHTML = `<div class="select__single-value">${text}</div>`;
    input.value = "";
    closeMenu();
  };
  const renderMenu = () => {
    const q = input.value.toLowerCase();
    menuRoot.innerHTML = `<div id="country-menu" role="listbox">${OPTIONS.filter((o) => o.toLowerCase().includes(q))
      .map((o) => `<div role="option">${o}</div>`).join("")}</div>`;
    input.setAttribute("aria-controls", "country-menu");
    input.setAttribute("aria-expanded", "true");
    for (const opt of menuRoot.querySelectorAll("[role=option]")) {
      opt.addEventListener("mousedown", (e) => { e.preventDefault(); if (!window.rejectClicks) pick(opt.textContent); });
    }
  };
  input.addEventListener("mousedown", renderMenu);
  input.addEventListener("input", renderMenu);
  input.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMenu(); });
  input.addEventListener("blur", () => { input.value = ""; setTimeout(closeMenu, 0); });
</script>
```

`popup_with_search.html` — a button opening a popup whose options appear only after typing into the popup's own search box (iCIMS / SuccessFactors style); this is what the adaptive step exists for:

```html
<label id="fos-l">Field of study</label>
<button id="fos" aria-haspopup="dialog" aria-labelledby="fos-l">Select</button>
<div id="portal"></div>
<script>
  const ALL = ["Business Administration", "Information Systems", "Computer Science", "Statistics"];
  const btn = document.getElementById("fos");
  const portal = document.getElementById("portal");
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    portal.innerHTML = `<div role="dialog"><input aria-label="Search" id="fos-q"><div role="listbox" id="fos-list"></div></div>`;
    const q = document.getElementById("fos-q");
    q.addEventListener("click", (ev) => ev.stopPropagation());
    q.addEventListener("input", () => {
      const list = document.getElementById("fos-list");
      const hits = ALL.filter((o) => q.value && o.toLowerCase().includes(q.value.toLowerCase()));
      list.innerHTML = hits.map((h) => `<div role="option">${h}</div>`).join("");
      for (const opt of list.querySelectorAll("[role=option]")) {
        opt.addEventListener("click", (ev) => { ev.stopPropagation(); btn.textContent = opt.textContent; portal.innerHTML = ""; });
      }
    });
  });
  document.body.addEventListener("click", () => { portal.innerHTML = ""; });
</script>
```

`native.html`:

```html
<label for="deg">Highest degree</label>
<select id="deg"><option value="">Select</option><option>Bachelor's</option><option>Master's</option></select>
<label for="lang">Languages</label>
<select id="lang" multiple><option selected>English</option><option>Spanish</option><option>Hindi</option></select>
<fieldset><legend>Are you 18 or older?</legend>
  <label><input type="radio" name="age" value="y">Yes</label><label><input type="radio" name="age" value="n">No</label></fieldset>
<fieldset><legend>Willing to relocate?</legend>
  <input type="radio" name="rel" id="r1" style="position:absolute;opacity:0"><label for="r1">Yes</label>
  <input type="radio" name="rel" id="r2" style="position:absolute;opacity:0"><label for="r2">No</label></fieldset>
<fieldset><legend>Which days can you work?</legend>
  <label><input type="checkbox" name="days" value="mon" checked>Monday</label>
  <label><input type="checkbox" name="days" value="tue">Tuesday</label>
  <label><input type="checkbox" name="days" value="wed">Wednesday</label></fieldset>
<label><input type="checkbox" id="pref">I have a preferred name</label>
```

**Step 3: Privacy guard** — `test_fixture_privacy.py`:

```python
import re

import pytest

from tests.browser.conftest import FIXTURES

PII = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "email"),
    (re.compile(r"\+?\d[\d\s().-]{8,}\d"), "phone-like digits"),
    (re.compile(r"linkedin\.com/in/", re.I), "profile url"),
]


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.html")), ids=lambda p: p.name)
def test_no_fixture_carries_personal_data(path):
    text = path.read_text()
    for pattern, what in PII:
        assert not pattern.search(text), f"{path.name}: {what}"
```

**Step 4: The six research failures, written now against the engine's API.** They fail until Task 4: put `pytestmark = pytest.mark.xfail(strict=True, reason="engine lands in Tasks 2-4")` at module top and remove it in Task 4.

```python
# backend/tests/browser/test_research_failures.py
"""The six failures docs/reports/2026-09-25-extension-reliability-research.md
reproduced, asserted as the new engine must behave."""

import pytest

from tests.browser.conftest import fixture_html

NS = "window.careerStudioCompanion"


def inventory(page):
    return page.evaluate(f"() => {NS}.fillOps.inventory({{}}).fields")


def apply(page, action):
    return page.evaluate(f"(a) => {NS}.fillOps.apply([a])", action)[0]


def test_1_an_aria_labelledby_field_is_listed_with_its_question(page, load):
    load(page, "<span id='q'>First name</span><input id='f-92' aria-labelledby='q'>")
    assert [f["question"] for f in inventory(page)] == ["First name"]


def test_2_identity_is_the_element_not_joined_label_text(page, load):
    load(page, "<label for='c'>Country</label><button id='c' aria-haspopup='listbox' name='field-12'>Select One</button>")
    first = inventory(page)[0]["fid"]
    assert inventory(page)[0]["fid"] == first and "|" not in first


def test_3_an_unmatched_input_combobox_is_listed(page, load):
    load(page, "<label for='s'>What is your preferred shift?</label><input id='s' role='combobox'>")
    assert [(f["shape"], f["question"]) for f in inventory(page)] == [("search", "What is your preferred shift?")]


def test_4_a_closed_dropdown_is_explored_before_anyone_decides(page, load):
    load(page, fixture_html("workday_listbox.html"))
    fid = next(f["fid"] for f in inventory(page) if f["question"].startswith("Are you legally"))
    got = page.evaluate(f"(fid) => {NS}.fillOps.explore([{{fid}}])", fid)
    assert [o["text"] for o in got[fid]["options"]] == ["Yes", "No"]


def test_5_a_rejected_click_is_never_reported_filled(page, load):
    load(page, fixture_html("react_select.html"))
    page.evaluate("window.rejectClicks = true")
    f = inventory(page)[0]
    row = apply(page, {"fid": f["fid"], "fp": f["fp"], "op": "choose", "text": "India", "term": "ind"})
    assert row["outcome"] != "verified" and row["committed"] == ""


def test_6_a_hidden_unrelated_option_is_never_clicked(page, load):
    load(page, fixture_html("workday_listbox.html"))
    f = next(f for f in inventory(page) if f["question"].startswith("Are you legally"))
    row = apply(page, {"fid": f["fid"], "fp": f["fp"], "op": "choose", "text": "Canada"})
    assert row["outcome"] == "unexpected"
    assert page.evaluate("window.staleHit === undefined")
```

**Step 5:** Run `cd backend && /opt/anaconda3/bin/python3 -m pytest tests/browser -q` → privacy PASS, research failures XFAIL.

**Commit:** `git commit -m "test(companion): real-Chromium corpus — harness, behaviour fixtures, the six research failures"`

---

## Task 2: Field reader and page primitives (with real cancellation)

**Files:**
- Create: `extension/content/field-reader.js`, `extension/content/fill-base.js`
- Modify: `backend/tests/browser/conftest.py` — `ENGINE_SOURCES = ["shared/policy.js", "content/field-reader.js", "content/fill-base.js"]`
- Test: `backend/tests/browser/test_field_reader.py`, `backend/tests/browser/test_fill_base.py`

**Step 1: Field reader tests** — `test_field_reader.py`:

```python
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


def test_a_dropdown_that_names_its_question_keeps_it(page, load):
    load(page, "<fieldset><legend>Address</legend><button id='a' aria-haspopup='listbox' "
               "aria-label='State Select One Required'>Select One</button></fieldset>")
    assert page.evaluate(READ, "#a")["question"] == "State"


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
```

**Step 2: Implement** `content/field-reader.js`:

```js
/* Maestro CS Companion — the field reader: ONE answer to "what is this field
 * asking", with the source it came from. Strength order:
 *   label-for → label-wrap → labelledby (every id) → aria-label → legend → nearby
 * A Workday dropdown's aria-label is "<question> <value> Required"; on its
 * Application Questions step the question part is EMPTY and the real question
 * is the fieldset legend — so the button's own value and "Required" are
 * stripped, and an aria-label left empty falls through to the legend.
 * Zero-width characters are whitespace; ids resolve in the element's own root.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const ZERO_WIDTH = /[​-‍⁠﻿‎‏]/g;
  const clean = (s) => String(s ?? "").replace(ZERO_WIDTH, " ").replace(/\s+/g, " ").trim();
  const STAR = /\s*\*+\s*$/;
  const text = (el) => clean(el?.innerText || el?.textContent);
  const rootOf = (el) => (el?.getRootNode?.() instanceof ShadowRoot ? el.getRootNode() : document);
  const byId = (el, id) => rootOf(el).getElementById?.(id) ?? document.getElementById(id);
  const isPopupButton = (el) =>
    el?.tagName === "BUTTON" && /^(listbox|true|menu|dialog)$/.test(el.getAttribute("aria-haspopup") ?? "");
  const withoutControls = (node) => {
    const copy = node.cloneNode(true);
    copy.querySelectorAll("input, select, textarea, button, [role=listbox]").forEach((n) => n.remove());
    return clean(copy.textContent);
  };
  const fromIds = (el, attr) => clean((el.getAttribute(attr) ?? "").split(/\s+/).filter(Boolean)
    .map((id) => text(byId(el, id))).join(" "));
  const SOURCES = [
    ["label-for", (el) => {
      const lab = el.id && rootOf(el).querySelector?.(`label[for="${CSS.escape(el.id)}"]`);
      return lab ? withoutControls(lab) : "";
    }],
    ["label-wrap", (el) => (el.closest("label") ? withoutControls(el.closest("label")) : "")],
    ["labelledby", (el) => fromIds(el, "aria-labelledby")],
    ["aria-label", (el) => {
      let label = clean(el.getAttribute("aria-label"));
      if (label && isPopupButton(el)) {
        const own = text(el);
        if (own) label = clean(label.split(own).join(" "));
        label = clean(label.replace(/\brequired\b/gi, " "));
      }
      return label;
    }],
    ["legend", (el) => text(el.closest("fieldset")?.querySelector("legend"))],
    ["nearby", (el) => {
      let node = el.parentElement;
      for (let depth = 0; node && depth < 3; depth += 1, node = node.parentElement) {
        const cand = node.querySelector('[class*="label" i], [class*="question" i]');
        if (cand && !cand.contains(el) && !cand.querySelector("input, select, textarea, button")) {
          const t = text(cand);
          if (t) return t;
        }
      }
      return "";
    }],
  ];
  const HEADING = "h1, h2, h3, h4, h5, [role=heading]";
  const sectionOf = (el) => {
    for (let node = el.parentElement; node; node = node.parentElement) {
      const heads = [...node.querySelectorAll(HEADING)]
        .filter((h) => !h.contains(el) && (h.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING));
      if (heads.length) return text(heads.at(-1));
    }
    return "";
  };

  ns.readFieldText = clean;
  ns.readField = (el) => {
    let question = "";
    let source = null;
    for (const [name, read] of SOURCES) {
      try {
        question = read(el);
      } catch {
        question = "";
      }
      if (question) {
        source = name;
        break;
      }
    }
    const starred = STAR.test(question);
    const section = sectionOf(el);
    const m = /(\d+)\s*$/.exec(section);
    return {
      question: clean(question.replace(STAR, "")),
      source,
      help: fromIds(el, "aria-describedby"),
      section,
      repeatIndex: m ? Math.max(0, Number(m[1]) - 1) : 0,
      required: Boolean(el.required) || el.getAttribute("aria-required") === "true" || starred,
    };
  };
})();
```

Run `pytest tests/browser/test_field_reader.py -q` → PASS. **Commit:** `git commit -m "feat(companion): one field reader with every label source"`

**Step 3: Primitive tests** — `test_fill_base.py`:

```python
B = "window.careerStudioCompanion.fillBase"


def test_invalid_reads_aria_invalid_linked_errors_and_nearby_errors(page, load):
    load(page, """
      <div data-automation-id='formField-a'><input id='a' value='x'><p data-automation-id='errorMessage'>Error: required</p></div>
      <input id='b' aria-invalid='true' value='x'>
      <input id='c' aria-describedby='ce' value='x'><p id='ce'>Must be a number</p>
      <input id='d' value='x'>""")
    got = page.evaluate(f"() => ['a','b','c','d'].map(id => {B}.invalid(document.getElementById(id)))")
    assert got == [True, True, True, False]


def test_an_unlinked_popup_is_owned_only_when_it_alone_appeared(page, load):
    load(page, "<ul role='listbox' style='display:none'><li role='option'>Canada</li></ul><button id='b'>x</button><div id='p'></div>")
    one = page.evaluate(f"""() => {{ const before = {B}.popups();
      document.getElementById('p').innerHTML = "<ul role='listbox'><li role='option'>United States</li></ul>";
      return {B}.optionsOf({B}.ownedPopup(document.getElementById('b'), before)).map(o => o.text); }}""")
    assert one == ["United States"]
    two = page.evaluate(f"""() => {{ const before = {B}.popups();
      document.getElementById('p').innerHTML += "<ul role='listbox'><li role='option'>B</li></ul><ul role='listbox'><li role='option'>C</li></ul>";
      return {B}.ownedPopup(document.getElementById('b'), before); }}""")
    assert two is None


def test_aria_controls_wins_and_hidden_disabled_or_loading_options_are_dropped(page, load):
    load(page, """<input id='c' role='combobox' aria-controls='lb'>
      <ul id='lb' role='listbox'><li role='option'>Yes</li><li role='option' aria-disabled='true'>Maybe</li>
        <li role='option' style='display:none'>No</li><li role='option'>Loading…</li></ul>""")
    got = page.evaluate(f"() => {B}.optionsOf({B}.ownedPopup(document.getElementById('c'), [])).map(o => o.text)")
    assert got == ["Yes"]


def test_a_timed_out_operation_can_never_click_late(page, load):
    load(page, "<button id='x'>x</button>")
    page.evaluate("document.getElementById('x').addEventListener('click', () => window.clicks = (window.clicks || 0) + 1)")
    out = page.evaluate(f"""() => {B}.withinBudget(async (t) => {{ await {B}.sleep(150);
        {B}.press(document.getElementById('x'), t); return 'clicked'; }}, 50).catch(e => e.name)""")
    page.wait_for_timeout(250)
    assert out == "Cancelled" and page.evaluate("window.clicks === undefined")


def test_cancel_all_stops_an_operation_in_flight(page, load):
    load(page, "<button id='x'>x</button>")
    page.evaluate("document.getElementById('x').addEventListener('click', () => window.clicks = 1)")
    out = page.evaluate(f"""() => {{ const run = {B}.withinBudget(async (t) => {{ await {B}.sleep(100);
        {B}.press(document.getElementById('x'), t); }}, 5000).catch(e => e.name);
        {B}.cancelAll(); return run; }}""")
    assert out == "Cancelled" and page.evaluate("window.clicks === undefined")
```

**Step 4: Implement** `content/fill-base.js`:

```js
/* Maestro CS Companion — page primitives every fill operation shares.
 *
 * CANCELLATION IS REAL. Every operation runs under `withinBudget(fn, ms)`,
 * which hands `fn` its own token; every gesture primitive (press, typeText,
 * closePopups, settle, waitFor) checks the token FIRST and throws `Cancelled`.
 * A timed-out or stopped operation therefore cannot land a click later —
 * Promise.race alone would only stop waiting for it.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const clean = (s) => ns.readFieldText(s);

  class Cancelled extends Error {
    constructor() {
      super("cancelled");
      this.name = "Cancelled";
    }
  }
  const live = new Set();
  const check = (t) => {
    if (t?.cancelled) throw new Cancelled();
  };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const settle = async (t, ms = 120) => {
    check(t);
    await sleep(ms);
    check(t);
  };
  const withinBudget = async (fn, ms) => {
    const t = { cancelled: false };
    live.add(t);
    let timer;
    try {
      return await Promise.race([
        fn(t),
        new Promise((_, reject) => {
          timer = setTimeout(() => {
            t.cancelled = true;
            reject(new Cancelled());
          }, ms);
        }),
      ]);
    } finally {
      clearTimeout(timer);
      live.delete(t);
    }
  };
  const cancelAll = () => {
    for (const t of live) t.cancelled = true;
  };
  const waitFor = async (fn, ms, t, step = 50) => {
    const end = Date.now() + ms;
    for (;;) {
      check(t);
      const got = fn();
      if (got) return got;
      if (Date.now() > end) return null;
      await sleep(step);
    }
  };

  const visible = (el) => {
    if (!el?.isConnected || !el.getClientRects().length) return false;
    const s = getComputedStyle(el);
    return s.visibility !== "hidden" && s.display !== "none" && Number(s.opacity) !== 0;
  };

  const ERROR_NODE = '[data-automation-id="errorMessage"], [role="alert"], [class*="error" i]';
  const ERROR_WORDS = /error|required|must|invalid|enter a/i;
  const byId = (el, id) => el.getRootNode().getElementById?.(id) ?? document.getElementById(id);
  const fieldBox = (el) =>
    el.closest('[data-automation-id^="formField"], .form-group, .field, [class*="field" i]')
    ?? el.parentElement?.parentElement ?? el.parentElement;
  const invalid = (el) => {
    if (el.getAttribute("aria-invalid") === "true") return true;
    const described = (el.getAttribute("aria-describedby") ?? "").split(/\s+/).filter(Boolean)
      .map((id) => byId(el, id)).filter((n) => n && visible(n));
    if (described.some((n) => ERROR_WORDS.test(n.textContent ?? ""))) return true;
    return [...(fieldBox(el)?.querySelectorAll(ERROR_NODE) ?? [])]
      .some((n) => visible(n) && !n.contains(el) && clean(n.textContent));
  };

  const POPUP = '[role="listbox"], [role="menu"], [role="tree"], [role="grid"], [role="dialog"]';
  const popups = () => [...document.querySelectorAll(POPUP)].filter(visible);
  const ownedPopup = (el, before) => {
    const linked = ["aria-controls", "aria-owns"]
      .flatMap((a) => (el.getAttribute(a) ?? "").split(/\s+/).filter(Boolean))
      .map((id) => byId(el, id)).find((n) => n && visible(n));
    if (linked) return linked;
    const active = el.getAttribute("aria-activedescendant");
    const viaActive = active && byId(el, active)?.closest(POPUP);
    if (viaActive && visible(viaActive)) return viaActive;
    // Outermost fresh popups only: a listbox inside a new dialog is part of it.
    const fresh = popups().filter((p) => !before.includes(p) && !popups().some((q) => q !== p && !before.includes(q) && q.contains(p)));
    return fresh.length === 1 ? fresh[0] : null;
  };
  const OPTION = '[role="option"], [role="menuitem"], [role="treeitem"], [role="menuitemradio"], [role="menuitemcheckbox"]';
  const LOADING = /^(loading|searching|no (results|items|matches|options)|type to search)/i;
  const optionsOf = (popup) => (popup ? [...popup.querySelectorAll(OPTION)] : [])
    .filter((o) => visible(o) && o.getAttribute("aria-disabled") !== "true")
    .map((o, i) => ({
      oid: `o${i + 1}`,
      text: clean(o.innerText || o.textContent),
      selected: o.getAttribute("aria-selected") === "true" || o.getAttribute("aria-checked") === "true",
      el: o,
    }))
    .filter((o) => o.text && !LOADING.test(o.text));

  const press = (el, t) => {
    check(t);
    const r = el.getBoundingClientRect();
    const at = { bubbles: true, cancelable: true, composed: true, clientX: r.x + r.width / 2, clientY: r.y + r.height / 2 };
    el.dispatchEvent(new PointerEvent("pointerdown", at));
    el.dispatchEvent(new MouseEvent("mousedown", at));
    el.dispatchEvent(new PointerEvent("pointerup", at));
    el.dispatchEvent(new MouseEvent("mouseup", at));
    el.dispatchEvent(new MouseEvent("click", at));
  };
  // Workday ignores a synthetic Escape; an outside click closes its popups.
  const closePopups = async (el, t) => {
    check(t);
    el?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await sleep(60);
    if (popups().length) {
      document.body.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
      document.body.click();
      await sleep(60);
    }
  };
  const proto = (el) => (el instanceof HTMLTextAreaElement ? HTMLTextAreaElement : HTMLInputElement).prototype;
  // Typing the way a person does: the browser fires REAL input events for
  // execCommand("insertText"), which React-controlled boxes (Workday) accept
  // where a setter + synthetic event is ignored. Setter only as a fallback.
  const typeText = (el, value, t) => {
    check(t);
    el.focus({ preventScroll: true });
    el.select?.();
    const ok = document.execCommand?.("insertText", false, value);
    if (ok && el.value === value) return;
    Object.getOwnPropertyDescriptor(proto(el), "value")?.set?.call(el, value);
    el.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: value }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  };
  // Equal after folding case, accents and punctuation; both empty is NOT equal.
  const sameIgnoringFormat = (actual, wrote) => {
    const strip = (s) => String(s ?? "").normalize("NFKD").replace(/\p{M}/gu, "")
      .toLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
    const left = strip(actual);
    return left !== "" && left === strip(wrote);
  };

  ns.fillBase = {
    Cancelled, check, sleep, settle, withinBudget, cancelAll, waitFor, visible, invalid,
    popups, ownedPopup, optionsOf, press, closePopups, typeText, sameIgnoringFormat, clean,
  };
})();
```

Run `pytest tests/browser -q` → PASS. **Commit:** `git commit -m "feat(companion): page primitives — ownership, validation state, typing, real cancellation"`

**If `test_a_workday_...` style typing ever shows `execCommand` input as untrusted** (Task 4 Step 1 checks it on `workday_text.html`): stop and tell the owner — the Workday fix would then need the debugger executor (out of scope).

---

## Task 3: Shapes and the inventory

**Files:**
- Create: `extension/content/shapes.js`, `extension/content/inventory.js`
- Modify: `backend/tests/browser/conftest.py` (`ENGINE_SOURCES` += `content/shapes.js, content/inventory.js`)
- Test: `backend/tests/browser/test_inventory.py`

**Step 1: Failing tests** — `test_inventory.py`:

```python
from tests.browser.conftest import fixture_html

INV = "window.careerStudioCompanion.fillInventory"


def fields(page, consent_forms=False):
    return page.evaluate(f"(cf) => {INV}.list({{consentForms: cf}}).fields", consent_forms)


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


def test_a_fid_survives_repeat_calls_and_a_rerender(page, load):
    load(page, "<section><h3>Education 1</h3><label for='s'>School</label><input id='s'></section>")
    first = fields(page)[0]["fid"]
    page.evaluate("() => { const o = document.getElementById('s'); o.replaceWith(o.cloneNode(true)); }")
    assert fields(page)[0]["fid"] == first


def test_same_labels_in_repeated_sections_are_separate_fields(page, load):
    load(page, """<section><h3>Work Experience 1</h3><label for='a'>Job Title</label><input id='a'></section>
                  <section><h3>Work Experience 2</h3><label for='b'>Job Title</label><input id='b'></section>""")
    got = fields(page)
    assert [(f["question"], f["repeatIndex"]) for f in got] == [("Job Title", 0), ("Job Title", 1)]
    assert got[0]["fid"] != got[1]["fid"] and got[0]["fp"] != got[1]["fp"]


def test_groups_dates_and_native_options(page, load):
    load(page, fixture_html("native.html") + fixture_html("workday_date.html"))
    by_q = {f["question"]: f for f in fields(page)}
    assert [o["text"] for o in by_q["Highest degree"]["options"]] == ["Bachelor's", "Master's"]
    assert by_q["Highest degree"]["optionsComplete"] is True
    assert by_q["Which days can you work?"]["committed"] == ["Monday"] and by_q["Which days can you work?"]["multi"]
    assert by_q["I have a preferred name"]["committed"] == "No"
    assert by_q["Willing to relocate?"]["shape"] == "group"
    assert by_q["From"]["shape"] == "date"


def test_user_typing_marks_touched_and_policy_blocks_signatures(page, load):
    load(page, "<label for='a'>City</label><input id='a'><label for='s'>Signature</label><input id='s'>")
    page.type("#a", "x")
    by_q = {f["question"]: f for f in fields(page)}
    assert by_q["City"]["touched"] is True and by_q["Signature"]["policyBlocked"] is True


def test_open_shadow_roots_are_walked(page, load):
    load(page, "<div id='host'></div>")
    page.evaluate("""() => { const r = document.getElementById('host').attachShadow({mode:'open'});
        r.innerHTML = "<label for='z'>Zip</label><input id='z'>"; }""")
    assert [f["question"] for f in fields(page)] == ["Zip"]
```

(`policy.js`'s never-fill list includes signature; if its API differs from `ns.isPolicyBlocked(label, {consentForms})`, adapt the call and note it.)

**Step 2:** Run → FAIL.

**Step 3: Implement** `content/shapes.js` — a shape is only: recognise, group, question override, read what is **committed**, passive options, and how it opens (`press` / `search`). No shape acts or verifies; `fill-core.js` runs one generic path over all of them.

```js
/* Maestro CS Companion — widget shapes: recognise, group, read committed, open.
 * The committed reader is the load-bearing part: search text is never a value;
 * a single-value node, pill, chip, hidden backing input, button text or
 * checked state is. */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const b = () => ns.fillBase;
  const TEXT_TYPES = new Set(["text", "email", "tel", "url", "number", "search", ""]);
  const SEARCH_BOX = '[data-uxi-widget-type="selectinput"], [data-uxi-widget-type="multiselectinput"]';
  const DATE_SECTION = /dateSection(Month|Day|Year)-input/;
  const DATE_PATTERN = /^(mm|dd|yyyy)([/.\-](mm|dd|yyyy)){1,2}$/i;
  const PLACEHOLDER = /^(select( one)?|choose( one)?|please select|--|—|-)?$/i;
  const CHIP = '[data-automation-id="selectedItem"], [class*="multi-value__label" i], [class*="multiValue" i] [class*="label" i]';
  const SINGLE = '[class*="single-value" i], [class*="singleValue" i]';
  const GROUPER = 'fieldset, [role="radiogroup"], [role="group"]';

  const legendOf = (el) => b().clean(el.closest("fieldset")?.querySelector("legend")?.textContent).replace(/\s*\*+\s*$/, "");
  const box = (el) => el.closest(SEARCH_BOX) ?? el.closest('[class*="container" i]') ?? el.parentElement?.parentElement ?? el.parentElement;
  const chips = (el) => [...(box(el)?.querySelectorAll(CHIP) ?? [])].map((c) => b().clean(c.textContent)).filter(Boolean);

  const members = (el) => {
    if (el.name) return [...(el.form ?? el.getRootNode()).querySelectorAll(`input[type="${el.type}"][name="${CSS.escape(el.name)}"]`)];
    const c = el.closest(GROUPER);
    return c ? [...c.querySelectorAll(`input[type="${el.type}"]`)] : [el];
  };
  const lone = (el) => el.type === "checkbox" && members(el).length < 2;
  const labelOf = (input) => ns.readField(input).question;
  const realOptions = (el) => [...el.options].filter((o, i) =>
    !o.disabled && b().clean(o.text) && !(i === 0 && (o.value === "" || /^(select|choose|please select|--|—)/i.test(b().clean(o.text)))));
  const dateKind = (el) => {
    if (DATE_SECTION.test(el.getAttribute("data-automation-id") ?? "")) return "sections";
    if (el.type === "month" || el.type === "date") return el.type;
    if (DATE_PATTERN.test(el.getAttribute("placeholder") ?? "")) return "pattern";
    return null;
  };
  const dateWrapper = (el) => el.closest('[data-automation-id="dateInputWrapper"]') ?? el.parentElement;
  const dateSections = (el) => [...dateWrapper(el).querySelectorAll('input[data-automation-id^="dateSection"]')];
  const partOf = (s) => DATE_SECTION.exec(s.getAttribute("data-automation-id") ?? "")?.[1]?.toLowerCase();

  const SHAPES = [
    {
      name: "date", kind: "text",
      match: (el) => el instanceof HTMLInputElement && dateKind(el) !== null,
      groupKey: (el) => (dateKind(el) === "sections"
        ? `date:${[...document.querySelectorAll('[data-automation-id="dateInputWrapper"]')].indexOf(dateWrapper(el))}` : null),
      describe: (el) => (dateKind(el) === "sections" && legendOf(el) ? { question: legendOf(el) } : {}),
      read(el) {
        if (dateKind(el) !== "sections") return el.value;
        const got = Object.fromEntries(dateSections(el).map((s) => [partOf(s), s.value]));
        return [got.year, got.month, got.day].filter(Boolean).join("-");
      },
      dateKind, dateSections, partOf,
    },
    {
      name: "text", kind: "text",
      match: (el) => el instanceof HTMLTextAreaElement
        || (el instanceof HTMLInputElement && TEXT_TYPES.has((el.getAttribute("type") ?? "").toLowerCase())
          && el.getAttribute("role") !== "combobox" && !el.hasAttribute("aria-autocomplete") && !el.closest(SEARCH_BOX)),
      read: (el) => el.value,
    },
    {
      name: "select", kind: "choice",
      match: (el) => el instanceof HTMLSelectElement,
      multi: (el) => el.multiple,
      passive: (el) => ({ options: realOptions(el).map((o, i) => ({ oid: `o${i + 1}`, text: b().clean(o.text), selected: o.selected })), complete: true }),
      read: (el) => {
        const chosen = realOptions(el).filter((o) => o.selected).map((o) => b().clean(o.text));
        return el.multiple ? chosen : (chosen[0] ?? "");
      },
      realOptions,
    },
    {
      name: "group", kind: "choice",
      match: (el) => el instanceof HTMLInputElement && (el.type === "radio" || el.type === "checkbox"),
      multi: (el) => el.type === "checkbox" && !lone(el),
      groupKey: (el) => (lone(el) ? null : `${el.type}:${el.name || [...document.querySelectorAll(GROUPER)].indexOf(el.closest(GROUPER))}`),
      describe: (el) => (lone(el) ? {} : { question: legendOf(el) || ns.readField(el.closest(GROUPER) ?? el).question }),
      passive: (el) => (lone(el)
        ? { options: [{ oid: "yes", text: "Yes", selected: el.checked }, { oid: "no", text: "No", selected: !el.checked }], complete: true }
        : { options: members(el).map((m, i) => ({ oid: `o${i + 1}`, text: labelOf(m), selected: m.checked })), complete: true }),
      read: (el) => {
        if (lone(el)) return el.checked ? "Yes" : "No";
        const on = members(el).filter((m) => m.checked).map(labelOf);
        return el.type === "radio" ? (on[0] ?? "") : on;
      },
      members, lone, labelOf,
    },
    {
      name: "search", kind: "choice", open: "search",
      match: (el) => el instanceof HTMLInputElement
        && (el.getAttribute("role") === "combobox" || el.hasAttribute("aria-autocomplete") || el.closest(SEARCH_BOX) !== null),
      multi: (el) => el.closest('[data-uxi-widget-type="multiselectinput"]') !== null || /is-multi/.test(box(el)?.className ?? ""),
      read(el) {
        if (this.multi(el)) return chips(el);
        const single = box(el)?.querySelector(SINGLE);
        if (single) return b().clean(single.textContent);
        if (chips(el)[0]) return chips(el)[0];
        return box(el)?.querySelector('input[type="hidden"]')?.value ?? "";
      },
    },
    {
      name: "popup", kind: "choice", open: "press",
      match: (el) => (el.tagName === "BUTTON" && /^(listbox|true|menu|dialog)$/.test(el.getAttribute("aria-haspopup") ?? ""))
        || (el.getAttribute("role") === "combobox" && el.tagName !== "INPUT"),
      read: (el) => {
        const t = b().clean(el.innerText || el.textContent);
        return PLACEHOLDER.test(t) ? "" : t;
      },
    },
  ];

  ns.shapes = { list: SHAPES, of: (el) => SHAPES.find((s) => s.match(el)) ?? null, byName: (n) => SHAPES.find((s) => s.name === n) };
})();
```

**Step 4: Implement** `content/inventory.js`:

```js
/* Maestro CS Companion — every fillable control in this frame, as fields.
 * Identity is the element (WeakMap → fid `<frame>-<n>`); a fingerprint
 * (shape, question, section, repeat, name, ordinal) reacquires a re-rendered
 * node and lets an action prove it still targets the field it was decided for.
 * A field the user typed in (trusted input while the engine is not writing) is
 * `touched`. Never-fill fields (shared/policy.js) are `policyBlocked`. */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const FRAME = Math.random().toString(36).slice(2, 8);
  const CANDIDATE = 'input, select, textarea, button[aria-haspopup], [role="combobox"]:not(input)';
  const SKIP = new Set(["hidden", "submit", "button", "reset", "image", "file", "password"]);
  let counter = 0;
  const fidOf = new WeakMap();
  const registry = new Map(); // fid -> { ref, fp, shape }
  const touched = new Set();

  const walk = (root, out = []) => {
    out.push(...root.querySelectorAll(CANDIDATE));
    for (const host of root.querySelectorAll("*")) if (host.shadowRoot) walk(host.shadowRoot, out);
    return out;
  };
  const eligible = (el) => {
    if (el.tagName === "INPUT" && SKIP.has((el.getAttribute("type") ?? "").toLowerCase())) return false;
    if (el.disabled || el.readOnly || el.closest('[role="listbox"], [role="menu"], [role="dialog"]')) return false;
    const custom = el.type === "radio" || el.type === "checkbox";
    return ns.fillBase.visible(el) || (custom && ns.fillBase.visible(el.closest("label") ?? el.parentElement));
  };

  const list = ({ consentForms = false } = {}) => {
    const groups = new Set();
    const ordinals = new Map();
    const fields = [];
    for (const el of walk(document)) {
      if (!eligible(el)) continue;
      const shape = ns.shapes.of(el);
      if (!shape) continue;
      const group = shape.groupKey?.(el);
      if (group) {
        if (groups.has(group)) continue;
        groups.add(group);
      }
      const d = { ...ns.readField(el), ...(shape.describe?.(el) ?? {}) };
      const base = [shape.name, d.question, d.section, d.repeatIndex, el.getAttribute("name") ?? ""].join("|");
      const ordinal = (ordinals.get(base) ?? 0) + 1;
      ordinals.set(base, ordinal);
      const fp = `${base}|${ordinal}`;
      let fid = fidOf.get(el);
      if (!fid) {
        for (const [known, entry] of registry) {
          if (entry.fp === fp && !entry.ref.deref()?.isConnected) {
            fid = known;
            break;
          }
        }
        fid ??= `${FRAME}-${(counter += 1)}`;
        fidOf.set(el, fid);
      }
      registry.set(fid, { ref: new WeakRef(el), fp, shape: shape.name });
      const passive = shape.passive?.(el) ?? null;
      fields.push({
        fid, fp, shape: shape.name, kind: shape.kind, multi: Boolean(shape.multi?.(el)),
        question: d.question, source: d.source, section: d.section, repeatIndex: d.repeatIndex,
        required: d.required, help: d.help,
        committed: shape.read(el),
        options: passive?.options ?? null,
        optionsComplete: passive?.complete ?? false,
        invalid: ns.fillBase.invalid(el),
        touched: touched.has(fid),
        policyBlocked: Boolean(ns.isPolicyBlocked?.(d.question, { consentForms })),
      });
    }
    return { frame: FRAME, host: location.hostname, fields };
  };

  const resolve = (fid) => {
    const entry = registry.get(fid);
    if (!entry) return null;
    if (entry.ref.deref()?.isConnected) return entry.ref.deref();
    list();
    const again = registry.get(fid)?.ref.deref();
    return again?.isConnected ? again : null;
  };

  for (const type of ["input", "change"]) {
    document.addEventListener(type, (e) => {
      if (!e.isTrusted || ns.fillBusy) return;
      for (let el = e.target; el; el = el.parentElement) {
        if (fidOf.has(el)) {
          touched.add(fidOf.get(el));
          return;
        }
      }
    }, true);
  }

  ns.fillInventory = {
    list, resolve, frame: FRAME,
    fpOf: (fid) => registry.get(fid)?.fp ?? null,
    shapeOf: (fid) => ns.shapes.byName(registry.get(fid)?.shape),
  };
})();
```

Note: a radio/checkbox group's fid is its FIRST member; the `touched` walk marks it only when that member is the target — extend it to "any member of a registered group" if the touched test for groups fails (add one).

**Step 5:** Run `pytest tests/browser -q` → PASS. **Commit:** `git commit -m "feat(companion): shapes and an inventory with element-bound field ids"`

---

## Task 4: Generic mechanics (`fill-core.js`) and page operations (`fill-ops.js`)

**Files:**
- Create: `extension/content/fill-core.js`, `extension/content/fill-ops.js`
- Modify: `extension/content/agent.js` (`PAGE_HANDLERS` ~:270), `extension/sw.js` (`page_broadcast` allowlist ~:623), `extension/manifest.json` (after `shared/profile-fields.js`: `content/field-reader.js, content/fill-base.js, content/shapes.js, content/inventory.js, content/fill-core.js, content/fill-ops.js`)
- Modify: `backend/tests/browser/conftest.py` (`ENGINE_SOURCES` += `content/fill-core.js, content/fill-ops.js`), `backend/tests/test_extension_manifest.py`, `backend/tests/test_extension_sw_router.py` (pin new files and message types)
- Test: `backend/tests/browser/test_fill_core.py`; remove the `xfail` from `test_research_failures.py`

**Page operations** (JSON in and out; a frame acts only on fids it owns):

| Message | Payload | Returns |
|---|---|---|
| `fill_inventory` | `{consentForms}` | `{frame, host, fields}` |
| `fill_explore` | `requests: [{fid, fp, term?}]` | `{[fid]: {options, complete, searchable, error?}}` |
| `fill_apply` | `actions: [{fid, fp, op, value?, text?, texts?, term?}]`, `op ∈ write · choose · set · recommit · close` | `[{fid, outcome, reason?, committed, options?, added?, missing?}]` |
| `fill_sweep` | – | `[{fid, outcome}]` for text fields holding a value and showing an error |
| `fill_focus` | `{fid}` | `true` if owned |
| `fill_cancel` | – | cancels every operation in flight |

Outcomes: `verified` · `partial` (sets) · `unexpected` (with `reason`: `no_popup`, `empty_popup`, `option_missing`, `new_options`, `not_committed`) · `reverted` · `stale` (fp mismatch / node gone) · `cancelled` · `timeout`.

**Step 1: Failing tests** — `test_fill_core.py`:

```python
from tests.browser.conftest import fixture_html

OPS = "window.careerStudioCompanion.fillOps"


def inv(page):
    return {f["question"]: f for f in page.evaluate(f"() => {OPS}.inventory({{}}).fields")}


def apply(page, f, **action):
    return page.evaluate(f"(a) => {OPS}.apply([a])", {"fid": f["fid"], "fp": f["fp"], **action})[0]


def explore(page, f, term=None):
    return page.evaluate(f"(r) => {OPS}.explore([r])", {"fid": f["fid"], "fp": f["fp"], "term": term})[f["fid"]]


# --- text-like
def test_text_commits_where_the_page_only_takes_real_typing(page, load):
    load(page, fixture_html("workday_text.html"))
    row = apply(page, inv(page)["City"], op="write", value="Springfield")
    assert row["outcome"] == "verified" and page.evaluate("window.committed.city") == "Springfield"
    assert page.get_attribute("#city", "aria-invalid") == "false"


def test_sweep_recommits_text_that_shows_an_error_with_its_own_value(page, load):
    load(page, fixture_html("workday_text.html"))
    assert [r["outcome"] for r in page.evaluate(f"() => {OPS}.sweep()")] == ["verified"]
    assert page.evaluate("window.committed.zip") == "00000"


def test_a_text_the_page_clears_on_blur_is_reverted(page, load):
    load(page, "<label for='a'>Q</label><input id='a'><script>"
               "document.getElementById('a').addEventListener('focusout', e => { e.target.value = ''; });</script>")
    assert apply(page, inv(page)["Q"], op="write", value="x")["outcome"] == "reverted"


def test_workday_date_sections_are_written_before_one_blur(page, load):
    load(page, fixture_html("workday_date.html"))
    fields = inv(page)
    assert apply(page, fields["From"], op="write", value="2019-08")["outcome"] == "verified"
    assert (page.input_value("#m"), page.input_value("#y")) == ("08", "2019")
    assert apply(page, fields["End date"], op="write", value="2021-05")["outcome"] == "verified"
    assert page.input_value("#p") == "05/2021"


# --- choice-like, passive
def test_native_select_radio_hidden_radio_and_lone_checkbox(page, load):
    load(page, fixture_html("native.html"))
    f = inv(page)
    assert apply(page, f["Highest degree"], op="choose", text="Master's")["outcome"] == "verified"
    assert apply(page, f["Willing to relocate?"], op="choose", text="No")["outcome"] == "verified"
    assert page.is_checked("#r2")
    assert apply(page, f["I have a preferred name"], op="choose", text="Yes")["outcome"] == "verified"


def test_sets_keep_existing_choices_and_never_untick(page, load):
    load(page, fixture_html("native.html"))
    f = inv(page)
    assert apply(page, f["Which days can you work?"], op="set", texts=["Monday", "Wednesday"])["outcome"] == "verified"
    assert page.evaluate("[...document.querySelectorAll('input[name=days]:checked')].map(i => i.value)") == ["mon", "wed"]
    assert apply(page, f["Languages"], op="set", texts=["Hindi"])["outcome"] == "verified"


# --- choice-like, popups
def test_a_workday_dropdown_is_explored_and_closed_then_committed(page, load):
    load(page, fixture_html("workday_listbox.html"))
    f = inv(page)["Are you legally authorized to work in the United States?"]
    got = explore(page, f)
    assert [o["text"] for o in got["options"]] == ["Yes", "No"] and got["complete"]
    assert page.evaluate("document.getElementById('portal').children.length") == 0
    row = apply(page, f, op="choose", text="No")
    assert (row["outcome"], row["committed"]) == ("verified", "No")


def test_a_category_is_unexpected_with_its_children_and_the_popup_stays_open(page, load):
    load(page, fixture_html("workday_listbox.html"))
    row = apply(page, inv(page)["How did you hear about us?"], op="choose", text="Job Board")
    assert (row["outcome"], row["reason"]) == ("unexpected", "new_options")
    assert [o["text"] for o in row["options"]] == ["LinkedIn", "Indeed"]


def test_react_select_commits_and_a_rejected_click_is_not_filled(page, load):
    load(page, fixture_html("react_select.html"))
    f = inv(page)["Country"]
    assert [o["text"] for o in explore(page, f, "united")["options"]] == ["United States", "United Kingdom"]
    assert apply(page, f, op="choose", text="India", term="ind")["outcome"] == "verified"
    page.evaluate("window.rejectClicks = true")
    row = apply(page, f, op="choose", text="Canada", term="can")
    assert (row["outcome"], row["reason"], row["committed"]) == ("unexpected", "not_committed", "India")


def test_workday_search_waits_past_searching_and_commits_the_pill(page, load):
    load(page, fixture_html("workday_search.html"))
    f = inv(page)["School or University"]
    got = explore(page, f, "University of Texas")
    assert [o["text"] for o in got["options"]] == [
        "University of Texas at Austin", "University of Texas at Dallas", "Not in List"]
    assert page.input_value("#school") == ""
    row = apply(page, f, op="choose", text="University of Texas at Dallas", term="Texas")
    assert (row["outcome"], row["committed"]) == ("verified", "University of Texas at Dallas")


def test_a_search_set_keeps_existing_chips_and_reports_partial_honestly(page, load):
    load(page, fixture_html("workday_search.html"))
    f = inv(page)["Type to Add Skills"]
    row = apply(page, f, op="set", texts=["Python", "Rust"])
    assert row["outcome"] == "partial" and row["added"] == ["Python"] and row["missing"] == ["Rust"]
    assert row["committed"] == ["SQL", "Python"]


def test_an_empty_popup_that_needs_a_search_is_unexpected_not_failed(page, load):
    load(page, fixture_html("popup_with_search.html"))
    got = explore(page, inv(page)["Field of study"])
    assert got["options"] == [] and got["searchable"] is True and got["error"] == "empty_popup"


# --- safety
def test_a_changed_field_fingerprint_is_stale(page, load):
    load(page, fixture_html("native.html"))
    f = inv(page)["Highest degree"]
    assert page.evaluate(f"(a) => {OPS}.apply([a])", {"fid": f["fid"], "fp": "other", "op": "choose", "text": "Master's"})[0]["outcome"] == "stale"


def test_a_fid_from_another_frame_is_ignored(page, load):
    load(page, fixture_html("native.html"))
    assert page.evaluate(f"() => {OPS}.apply([{{fid: 'zzzzzz-1', op: 'write', value: 'x'}}])") == []


def test_cancel_stops_a_choose_before_it_clicks(page, load):
    load(page, fixture_html("workday_search.html"))
    f = inv(page)["School or University"]
    row = page.evaluate(f"""(a) => {{ const run = {OPS}.apply([a]); setTimeout(() => {OPS}.cancel(), 100); return run; }}""",
                        {"fid": f["fid"], "fp": f["fp"], "op": "choose", "text": "Texas A&M University", "term": "Texas"})[0]
    assert row["outcome"] == "cancelled"
    page.wait_for_timeout(600)
    assert page.evaluate("document.getElementById('school-pills').children.length") == 0


def test_engine_writes_do_not_mark_a_field_touched(page, load):
    load(page, fixture_html("workday_text.html"))
    apply(page, inv(page)["City"], op="write", value="Springfield")
    assert inv(page)["City"]["touched"] is False
```

**Step 2:** Run → FAIL (`fillOps` undefined).

**Step 3: Implement** `content/fill-core.js`:

```js
/* Maestro CS Companion — the generic fill mechanics.
 *
 * Two kinds of field. TEXT-LIKE: type like a person (fillBase.typeText), one
 * blur per widget (date sections are written first, then blurred once), then
 * verify. CHOICE-LIKE: passive shapes (select, radio/checkbox) act directly;
 * popup shapes OPEN (press, or type a term for search shapes), read the options
 * of the popup they OWN (scrolling long lists), and either close (explore) or
 * click one (commit: press, then click as a second gesture), blur, close, and
 * verify. Verify always runs after the final blur and treats a field error as
 * not filled. What the generic path cannot finish it reports as `unexpected`
 * with a reason; the loop's adaptive step takes it from there (Task 6).
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const b = () => ns.fillBase;
  const OPEN_MS = 2500;
  const leftOpen = new WeakMap(); // el -> { pop, before } when a commit left a popup open on purpose

  const parseDate = (v) => {
    const m = /^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$/.exec(String(v).trim());
    return m ? { year: m[1], month: m[2] ?? "", day: m[3] ?? "" } : null;
  };
  const formatPattern = (pattern, d) => pattern.replace(/yyyy/i, d.year).replace(/mm/i, d.month).replace(/dd/i, d.day);

  const verify = (el, shape, expected) => {
    if (!el.isConnected) return "stale";
    if (b().invalid(el)) return "reverted";
    const have = [shape.read(el)].flat();
    if (shape.name === "date") {
      const want = parseDate(expected);
      if (shape.dateKind(el) === "pattern") return want && el.value === formatPattern(el.getAttribute("placeholder"), want) ? "verified" : "reverted";
      const got = parseDate(have[0]);
      return got && want && got.year === want.year && (!want.month || got.month === want.month) ? "verified" : "reverted";
    }
    return [expected].flat().every((w) => have.some((h) => b().sameIgnoringFormat(h, w))) ? "verified" : "reverted";
  };

  const blurOut = async (el, t) => {
    el.blur?.();
    await b().settle(t, 150);
  };

  // ---- text-like
  async function write(el, shape, value, t) {
    if (shape.name === "date") {
      const d = parseDate(value);
      if (!d) return { outcome: "unexpected", reason: "not_a_date" };
      const kind = shape.dateKind(el);
      if (kind === "sections") {
        const parts = shape.dateSections(el);
        for (const s of parts) if (d[shape.partOf(s)]) b().typeText(s, d[shape.partOf(s)], t);
        await blurOut(parts.at(-1), t);
      } else {
        b().typeText(el, kind === "month" ? `${d.year}-${d.month}` : kind === "date" ? `${d.year}-${d.month}-${d.day || "01"}`
          : formatPattern(el.getAttribute("placeholder"), d), t);
        await blurOut(el, t);
      }
    } else {
      b().typeText(el, String(value), t);
      await blurOut(el, t);
    }
    return { outcome: verify(el, shape, value) };
  }

  // ---- choice-like: popups
  const searchBoxOf = (el, pop) => (el instanceof HTMLInputElement ? el : pop?.querySelector("input:not([type=hidden])") ?? null);
  const open = async (el, shape, term, t) => {
    const before = b().popups();
    el.focus?.({ preventScroll: true });
    b().press(el, t);
    let pop = await b().waitFor(() => b().ownedPopup(el, before), OPEN_MS, t);
    const box = searchBoxOf(el, pop);
    if (term && box) {
      b().typeText(box, term, t);
      pop = await b().waitFor(() => {
        const p = b().ownedPopup(el, before);
        return p && b().optionsOf(p).length ? p : null;
      }, OPEN_MS, t) ?? b().ownedPopup(el, before);
    } else if (pop) {
      await b().waitFor(() => b().optionsOf(pop).length > 0, OPEN_MS, t);
    }
    return { pop, before, searchable: Boolean(searchBoxOf(el, pop)) };
  };
  const readAll = async (pop, t) => {
    const seen = new Map();
    let complete = pop.scrollHeight <= pop.clientHeight + 4;
    for (let i = 0; i < 30; i += 1) {
      for (const o of b().optionsOf(pop)) if (!seen.has(o.text)) seen.set(o.text, o);
      if (complete) break;
      const top = pop.scrollTop;
      pop.scrollTop += pop.clientHeight;
      await b().settle(t, 80);
      if (pop.scrollTop === top) complete = true;
    }
    return { options: [...seen.values()].map((o, i) => ({ oid: `o${i + 1}`, text: o.text, selected: o.selected })), complete };
  };
  const tidy = async (el, t) => {
    leftOpen.delete(el);
    const box = el instanceof HTMLInputElement ? el : null;
    if (box && box.value) b().typeText(box, "", t);
    await b().closePopups(el, t);
    await blurOut(el, t);
  };

  async function explore(el, shape, { term } = {}, t) {
    if (shape.passive) return { ...shape.passive(el), searchable: false };
    let { pop, searchable } = await open(el, shape, term, t);
    let options = pop ? b().optionsOf(pop) : [];
    if (!options.length && term) {
      const word = term.split(/\s+/).find((w) => w.length > 2 && w !== term);
      if (word) {
        await tidy(el, t);
        ({ pop, searchable } = await open(el, shape, word, t));
        options = pop ? b().optionsOf(pop) : [];
      }
    }
    const got = pop && options.length ? await readAll(pop, t) : { options: [], complete: false };
    await tidy(el, t);
    if (!got.options.length) return { ...got, searchable, error: pop ? "empty_popup" : "no_popup" };
    return { ...got, complete: got.complete && !term, searchable };
  }

  async function choosePassive(el, shape, text, t) {
    if (shape.name === "select") {
      const opt = shape.realOptions(el).find((o) => b().clean(o.text) === text);
      if (!opt) return { outcome: "unexpected", reason: "option_missing" };
      el.focus({ preventScroll: true });
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value").set.call(el, opt.value);
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    } else if (shape.lone(el)) {
      if (el.checked !== (text === "Yes")) (target(el)).click();
    } else {
      const input = shape.members(el).find((m) => shape.labelOf(m) === text);
      if (!input) return { outcome: "unexpected", reason: "option_missing" };
      if (!input.checked) target(input).click();
    }
    await blurOut(el, t);
    const outcome = verify(el, shape, text);
    return outcome === "verified" ? { outcome } : { outcome: "unexpected", reason: "not_committed" };
  }
  // A hidden custom radio/checkbox is operated through its label.
  const target = (input) => (b().visible(input) ? input
    : (input.id && input.getRootNode().querySelector?.(`label[for="${CSS.escape(input.id)}"]`)) || input.closest("label") || input);

  async function choose(el, shape, { text, term }, t) {
    if (shape.passive) return choosePassive(el, shape, text, t);
    const before0 = shape.read(el);
    for (const gesture of [(o) => b().press(o, t), (o) => { b().check(t); o.click(); }]) {
      const { pop, before } = await open(el, shape, shape.open === "search" ? (term ?? text) : undefined, t);
      if (!pop) {
        await tidy(el, t);
        return { outcome: "unexpected", reason: "no_popup" };
      }
      const hits = b().optionsOf(pop).filter((o) => o.text === text);
      if (hits.length !== 1) {
        await tidy(el, t);
        return { outcome: "unexpected", reason: "option_missing" };
      }
      const shown = b().optionsOf(pop).map((o) => o.text).join("\n");
      gesture(hits[0].el);
      await b().settle(t, 200);
      const after = b().ownedPopup(el, before);
      const next = after ? b().optionsOf(after) : [];
      if (next.length && next.map((o) => o.text).join("\n") !== shown && shape.read(el) === before0) {
        leftOpen.set(el, { pop: after, before });
        return { outcome: "unexpected", reason: "new_options", options: next.map(({ oid, text: x }) => ({ oid, text: x })) };
      }
      await tidy(el, t);
      if (verify(el, shape, text) === "verified") return { outcome: "verified" };
    }
    return { outcome: "unexpected", reason: "not_committed" };
  }

  async function set(el, shape, { texts, terms = [] }, t) {
    if (shape.passive) {
      if (shape.name === "select") {
        const opts = shape.realOptions(el);
        el.focus({ preventScroll: true });
        for (const o of opts) if (texts.includes(b().clean(o.text))) o.selected = true;
        el.dispatchEvent(new Event("change", { bubbles: true }));
      } else {
        for (const text of texts) {
          const input = shape.members(el).find((m) => shape.labelOf(m) === text);
          if (input && !input.checked) {
            target(input).click();
            await b().settle(t, 60);
          }
        }
      }
      await blurOut(el, t);
    } else {
      for (const [i, text] of texts.entries()) {
        if (verify(el, shape, text) === "verified") continue;
        await choose(el, shape, { text, term: terms[i] ?? text }, t);
      }
    }
    const committed = [shape.read(el)].flat();
    const added = texts.filter((x) => committed.some((c) => b().sameIgnoringFormat(c, x)));
    const missing = texts.filter((x) => !added.includes(x));
    if (b().invalid(el)) return { outcome: "reverted", added, missing };
    return missing.length ? { outcome: "partial", added, missing } : { outcome: "verified", added, missing };
  }

  async function recommit(el, shape, t) {
    const own = shape.read(el);
    return own ? write(el, shape, own, t) : { outcome: "reverted" };
  }

  ns.fillCore = { write, explore, choose, set, recommit, verify, tidy, open, readAll, searchBoxOf, leftOpen };
})();
```

**Step 4: Implement** `content/fill-ops.js`:

```js
/* Maestro CS Companion — the page half of the fill loop.
 * The panel sends every message to every frame; a frame acts only on fids it
 * owns. Each operation runs under a budget with its own cancellation token
 * (fillBase.withinBudget) and an action whose fingerprint no longer matches the
 * field is `stale` — a decision made on an older view of the page never acts.
 * `ns.fillBusy` marks the engine's own typing so it is not taken for the user's. */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const EXPLORE_MS = 4000;
  const APPLY_MS = 6000;
  const SET_ITEM_MS = 4000;
  const inv = () => ns.fillInventory;
  const core = () => ns.fillCore;
  const mine = (fid) => typeof fid === "string" && fid.startsWith(`${inv().frame}-`);

  const run = async (fn, ms) => {
    ns.fillBusy = true;
    try {
      return await ns.fillBase.withinBudget(fn, ms);
    } catch (err) {
      if (err?.name === "Cancelled") return { outcome: "cancelled" };
      throw err;
    } finally {
      ns.fillBusy = false;
    }
  };
  const target = (fid, fp) => {
    const el = inv().resolve(fid);
    if (!el) return { stale: true };
    if (fp && inv().fpOf(fid) !== fp) return { stale: true };
    return { el, shape: inv().shapeOf(fid) };
  };
  const closeLeftOpen = async (except) => {
    // A popup deliberately left open (a category's children) is closed before
    // any other field is touched.
    for (const f of inv().list().fields) {
      if (f.fid === except) continue;
      const el = inv().resolve(f.fid);
      if (el && core().leftOpen.has(el)) await run((t) => core().tidy(el, t), 2000);
    }
  };

  const explore = async (requests) => {
    const out = {};
    for (const r of requests ?? []) {
      if (!mine(r.fid)) continue;
      await closeLeftOpen(r.fid);
      const { el, shape, stale } = target(r.fid, r.fp);
      if (stale) {
        out[r.fid] = { options: [], complete: false, error: "stale" };
        continue;
      }
      const got = await run((t) => core().explore(el, shape, { term: r.term }, t), EXPLORE_MS);
      out[r.fid] = got.options ? got : { options: [], complete: false, error: got.outcome };
    }
    return out;
  };

  const apply = async (actions) => {
    const out = [];
    for (const a of actions ?? []) {
      if (!mine(a.fid)) continue;
      await closeLeftOpen(a.fid);
      const { el, shape, stale } = target(a.fid, a.fp);
      if (stale) {
        out.push({ fid: a.fid, outcome: "stale", committed: null });
        continue;
      }
      const ms = a.op === "set" ? SET_ITEM_MS * Math.max(1, (a.texts ?? []).length) : APPLY_MS;
      const got = await run((t) => {
        if (a.op === "write") return core().write(el, shape, a.value, t);
        if (a.op === "choose") return core().choose(el, shape, { text: a.text, term: a.term }, t);
        if (a.op === "set") return core().set(el, shape, { texts: a.texts, terms: a.terms }, t);
        if (a.op === "recommit") return core().recommit(el, shape, t);
        if (a.op === "close") return core().tidy(el, t).then(() => ({ outcome: "closed" }));
        return Promise.resolve({ outcome: "unexpected", reason: "unknown_op" });
      }, ms);
      if (got.outcome === "cancelled" || got.outcome === "timeout") await run((t) => core().tidy(el, t), 2000);
      out.push({ fid: a.fid, ...got, committed: el.isConnected ? shape.read(el) : null });
    }
    return out;
  };

  const sweep = async () => {
    const out = [];
    for (const f of inv().list().fields) {
      if (f.kind !== "text" || !f.committed || !f.invalid || f.touched || f.policyBlocked) continue;
      const [row] = await apply([{ fid: f.fid, fp: f.fp, op: "recommit" }]);
      out.push({ fid: f.fid, outcome: row.outcome });
    }
    return out;
  };

  const focus = (fid) => {
    if (!mine(fid)) return false;
    const el = inv().resolve(fid);
    if (!el) return false;
    el.scrollIntoView({ block: "center" });
    el.focus({ preventScroll: true });
    return true;
  };

  ns.fillOps = {
    inventory: (opts) => inv().list(opts ?? {}),
    explore, apply, sweep, focus,
    cancel: () => ns.fillBase.cancelAll(),
  };
})();
```

`agent.js` `PAGE_HANDLERS` (each behind `frameMayReceiveUserData()` like `guided_write`; the refused frame returns an empty value of the same shape):

```js
fill_inventory: (msg) => (frameMayReceiveUserData() ? ns.fillOps.inventory({ consentForms: msg.consentForms === true }) : { frame: null, host: location.hostname, fields: [] }),
fill_explore: (msg) => (frameMayReceiveUserData() ? ns.fillOps.explore(msg.requests) : {}),
fill_apply: (msg) => (frameMayReceiveUserData() ? ns.fillOps.apply(msg.actions) : []),
fill_sweep: () => (frameMayReceiveUserData() ? ns.fillOps.sweep() : []),
fill_focus: (msg) => (frameMayReceiveUserData() ? ns.fillOps.focus(msg.fid) : false),
fill_cancel: () => { ns.fillOps.cancel(); return true; },
```

`sw.js` `page_broadcast` allowlist += `"fill_inventory","fill_explore","fill_apply","fill_sweep","fill_focus","fill_cancel"`.

**Step 5:** Run `pytest tests/browser -q` (remove the research-failures `xfail` first) and `pytest tests/ -q -k extension`. All PASS. Any failing fixture expectation is a real finding: fix the core, not the test, unless the test misreads the fixture.

**Commit:** `git commit -m "feat(companion): generic fill mechanics and page operations — verified, cancellable, fingerprinted"`

---

## Task 5: Backend decisions — fact catalog, `/map`, `/pick`

Five small commits inside one task. Tests fake Jev the way `backend/tests/test_autofill_choose_jev.py` does (`monkeypatch.setattr(<module>.jev, "decide", fake)`; reuse its `_answer(criteria, wanted, p)` and `jev_on` fixture) and fake the fast model with `monkeypatch.setattr(<module>.llm, "call_openai", ...)`.

### 5a. Move the resume feeds into a service

- Create `backend/app/services/autofill_context.py`; move `_CURRENT_TOKENS`, `_clean_line`, `_employment_blocks`, `_resume_skills` from `backend/app/routers/autofill.py` verbatim (docstrings included) as `clean_line`, `employment_blocks`, `resume_skills`; import them back into the router.
- `grep -rn "_employment_blocks\|_resume_skills\|_clean_line" backend/` and update importers.
- Run `pytest tests/test_autofill_router.py -q` → PASS.
- **Commit:** `refactor(autofill): resume feeds live in a service /map and /pick can share`

### 5b. Noul questions and a strict validator — `backend/app/services/jev.py`

Tests (`test_jev_client.py`):

```python
@pytest.mark.parametrize("answer, expected", [
    ({"type": "noul", "noul": 0.93}, 0.93), ({"noul": 0}, 0.0),
    ({"type": "noul", "noul": 1.2}, None), ({"type": "noul", "noul": True}, None),
    ({"type": "choice", "noul": 0.5}, None), ({"type": "noul"}, None), ("yes", None),
])
def test_noul_of_accepts_only_a_probability(answer, expected):
    assert jev.noul_of(answer) == expected


def test_noul_question_shape():
    assert jev.noul_question("Is it?") == {"type": "noul", "instructions": "Is it?"}
```

Implementation (after `choice_of`):

```python
def noul_question(instructions: str) -> dict[str, Any]:
    return {"type": "noul", "instructions": instructions}


def noul_of(answer: object) -> float | None:
    """P(yes) from a Noul answer ({"type": "noul", "noul": p}), or None.

    A missing `type` is tolerated; any other type, or p outside [0, 1] (or a
    bool), is refused and logged like `choice_of`'s refusals."""
    if not isinstance(answer, dict) or answer.get("type", "noul") != "noul":
        logger.warning("jev noul answer refused: not a noul answer")
        return None
    p = answer.get("noul")
    if not _unit(p):
        logger.warning("jev noul answer refused: not a probability")
        return None
    return float(p)
```

**Commit:** `feat(jev): Noul questions and a strict Noul validator`

### 5c. The fact catalog — `backend/app/services/autofill_catalog.py`

Also `autofill_slots._FLAG_SECTIONS` += `"experience", "skills", "custom"`.

Tests (`test_autofill_catalog.py`):

```python
from app.services import autofill_catalog as cat

PROFILE = {
    "personal": {"first_name": "Sample", "city": "Springfield"},
    "work_auth": {"status": "stem_opt", "sponsorship_future": True},
    "eeo": {"veteran_status": "not_veteran"},
    "preferences": {"willing_to_relocate": True, "how_heard": "LinkedIn"},
    "education": [
        {"school": "State University", "degree": "Master's", "discipline": "Business Analytics", "end_year": "2024"},
        {"school": "City College", "degree": "Bachelor's", "discipline": "Engineering", "end_year": "2019"},
    ],
    "custom": [{"question": "Do you have a clearance?", "answer": "No"}],
}
EMPLOYMENT = [
    {"employer": "Acme", "title": "Analyst", "location": "Remote", "start_date": "Aug 2021",
     "end_date": None, "current": True, "description": "Built dashboards"},
    {"employer": "Beta", "title": "Intern", "location": "", "start_date": "2020-05",
     "end_date": "08/2020", "current": False, "description": ""},
]


def facts():
    return cat.build(PROFILE, EMPLOYMENT, ["Python", "SQL"])


def test_every_education_entry_is_its_own_slots():
    f = facts()
    assert f["education.1.school"].value == "City College" and f["education.1.school"].policy == "flag"
    assert f["education.1.school"].describe == "education entry 2: school"


def test_experience_dates_normalise_and_a_current_job_has_no_end():
    f = facts()
    assert f["experience.0.start"].value == "2021-08" and "experience.0.end" not in f
    assert f["experience.0.current"].value == "Yes"
    assert (f["experience.1.start"].value, f["experience.1.end"].value) == ("2020-05", "2020-08")


def test_codes_become_words_a_form_would_show():
    f = facts()
    assert f["work_auth.status"].value == "F-1 STEM OPT extension" and f["work_auth.status"].policy == "exact"
    assert f["eeo.veteran_status"].value == "I am not a protected veteran"
    assert f["work_auth.sponsorship_future"].value == "Yes"


def test_skills_are_a_set_and_custom_answers_carry_their_question():
    f = facts()
    assert f["skills"].value == ("Python", "SQL")
    assert f["custom.0"].describe == "saved answer to: Do you have a clearance?"


def test_descriptions_never_carry_values():
    for fact in facts().values():
        if not fact.slot.startswith("custom"):
            assert str(fact.value) not in fact.describe


def test_a_legacy_single_education_object_and_the_size_cap():
    assert cat.build({"education": {"school": "Old U"}}, [], [])["education.0.school"].value == "Old U"
    assert len(cat.build(PROFILE, [dict(EMPLOYMENT[1]) for _ in range(20)], [])) <= cat.MAX_SLOTS
```

Implementation:

```python
"""Every applicant fact the fill loop may write, keyed by slot.

Built from the CONSENT-GATED profile (`eeo_consent.disclosable_profile`) plus
the selected resume's employment blocks and skills. `value` is what code types
or Pick compares against (never sent to Jev during /map); `describe` is the
label-only text /map offers; `policy` is `autofill_slots.policy_for`. Codes
become the words a form shows ("stem_opt" → "F-1 STEM OPT extension").
"""

import re
from dataclasses import dataclass
from typing import Any

from app.services.autofill_slots import Policy, _as_text, policy_for

MAX_SLOTS = 240  # Jev Choice ceiling 255 incl. sentinels
MAX_EDUCATION = 4
MAX_EXPERIENCE = 8
MAX_CUSTOM = 30

_WORDS: dict[str, dict[str, str]] = {
    "work_auth.status": {
        "citizen": "U.S. citizen", "permanent_resident": "Permanent resident (green card holder)",
        "opt": "F-1 OPT", "stem_opt": "F-1 STEM OPT extension", "h1b": "H-1B visa", "tn": "TN visa",
        "other_visa": "Another visa", "not_authorized": "Not authorized to work",
    },
    "eeo.veteran_status": {"not_veteran": "I am not a protected veteran", "veteran": "I am a protected veteran",
                           "decline": "I don't wish to answer"},
    "eeo.disability_status": {"no": "No, I do not have a disability", "yes": "Yes, I have a disability",
                              "decline": "I do not want to answer"},
    "eeo.gender": {"male": "Male", "female": "Female", "non_binary": "Non-binary", "decline": "Decline to self-identify"},
    "eeo.hispanic_latino": {"yes": "Yes", "no": "No", "decline": "Decline to self-identify"},
}
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


@dataclass(frozen=True)
class Fact:
    slot: str
    value: str | tuple[str, ...]
    describe: str
    policy: Policy


def _describe(slot: str) -> str:
    return re.sub(r"\.(\d+)\.", lambda m: f" entry {int(m.group(1)) + 1}: ", slot).replace(".", ": ").replace("_", " ")


def ym(text: str | None) -> str | None:
    """"Aug 2021" / "August 2021" / "2021-08(-01)" / "08/2021" / "2021" → "2021-08" / "2021"."""
    s = (text or "").strip().lower()
    if m := re.fullmatch(r"(\d{4})-(\d{1,2})(?:-\d{1,2})?", s):
        return f"{m[1]}-{int(m[2]):02d}"
    if m := re.fullmatch(r"(\d{1,2})/(\d{4})", s):
        return f"{m[2]}-{int(m[1]):02d}"
    if m := re.fullmatch(r"([a-z]{3})[a-z]*\.?\s+(\d{4})", s):
        month = _MONTHS.get(m[1])
        return f"{m[2]}-{month:02d}" if month else None
    return s if re.fullmatch(r"\d{4}", s) else None


def _add(out: dict[str, Fact], slot: str, value: Any, describe: str | None = None) -> None:
    if isinstance(value, tuple):
        if value:
            out[slot] = Fact(slot, value, describe or _describe(slot), policy_for(slot))
        return
    words = _WORDS.get(re.sub(r"\.\d+\.", ".", slot), {})
    text = (words.get(value) if isinstance(value, str) else None) or _as_text(value)
    if text is not None:
        out[slot] = Fact(slot, text, describe or _describe(slot), policy_for(slot))


def build(profile: dict[str, Any], employment: list[dict[str, Any]], skills: list[str]) -> dict[str, Fact]:
    out: dict[str, Fact] = {}
    profile = profile or {}
    for section in ("personal", "work_auth", "eligibility", "eeo", "preferences"):
        values = profile.get(section)
        if isinstance(values, dict):
            for key, value in values.items():
                if section == "eeo" and key == "gender" and value == "self_describe":
                    value = values.get("gender_self_describe")
                if isinstance(value, list):
                    value = tuple(str(v).strip() for v in value if str(v).strip())
                _add(out, f"{section}.{key}", value)
    education = profile.get("education")
    education = [education] if isinstance(education, dict) else (education or [])
    for i, entry in enumerate([e for e in education if isinstance(e, dict)][:MAX_EDUCATION]):
        for key, value in entry.items():
            _add(out, f"education.{i}.{key}", value)
    for i, block in enumerate((employment or [])[:MAX_EXPERIENCE]):
        for key in ("employer", "title", "location", "description"):
            _add(out, f"experience.{i}.{key}", block.get(key) or None)
        _add(out, f"experience.{i}.start", ym(block.get("start_date")))
        if not block.get("current"):
            _add(out, f"experience.{i}.end", ym(block.get("end_date")))
        _add(out, f"experience.{i}.current", bool(block.get("current")))
    _add(out, "skills", tuple(s for s in (skills or []) if s), "applicant skills (a list)")
    for i, qa in enumerate((profile.get("custom") or [])[:MAX_CUSTOM]):
        if isinstance(qa, dict) and qa.get("question"):
            _add(out, f"custom.{i}", qa.get("answer"), f"saved answer to: {qa['question']}")
    return dict(list(out.items())[:MAX_SLOTS])
```

**Commit:** `feat(autofill): fact catalog — every entry, date parts, words not codes`

### 5d. Wire schemas — `backend/app/schemas/autofill_fill.py`

```python
"""The fill loop's asks, keyed by `fid` both ways."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Shape = Literal["text", "date", "select", "group", "search", "popup"]
Route = Literal["slot", "free_text", "low_stakes", "none", "blocked"]
Reason = Literal["matched", "closest", "assumed", "abstained"]
MAX_FIELDS = 40
MAX_MAP_OPTIONS = 30
MAX_PICK_OPTIONS = 250  # Jev Choice ceiling 255 incl. `none`


class Selector(BaseModel):
    model_config = ConfigDict(extra="forbid")
    application_id: str | None = None
    base: str | None = None
    # e.g. "rec_linkedin" read from the apply page's ?source= by the extension.
    source_hint: str | None = Field(default=None, max_length=60)


class MapField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fid: str = Field(max_length=64)
    question: str = Field(max_length=300)
    section: str | None = Field(default=None, max_length=200)
    repeat_index: int = Field(default=0, ge=0, le=20)
    shape: Shape
    multi: bool = False
    required: bool = False
    options: list[str] = Field(default_factory=list, max_length=MAX_MAP_OPTIONS)


class MapRequest(Selector):
    fields: list[MapField] = Field(min_length=1, max_length=MAX_FIELDS)


class Mapped(BaseModel):
    route: Route
    slot: str | None = None
    value: str | list[str] | None = None  # to the LOCAL extension only


class MapResponse(BaseModel):
    fields: dict[str, Mapped]


class PickOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    oid: str = Field(max_length=16)
    text: str = Field(max_length=300)


class PickField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fid: str = Field(max_length=64)
    question: str = Field(max_length=300)
    route: Literal["slot", "low_stakes"]
    slot: str | None = Field(default=None, max_length=120)
    item: str | None = Field(default=None, max_length=300)  # one member of a set slot
    options: list[PickOption] = Field(min_length=1, max_length=MAX_PICK_OPTIONS)
    complete: bool = True
    multi: bool = False


class PickRequest(Selector):
    fields: list[PickField] = Field(min_length=1, max_length=MAX_FIELDS)


class Picked(BaseModel):
    oids: list[str]
    reason: Reason


class PickResponse(BaseModel):
    picks: dict[str, Picked]
```

Tests: `extra="forbid"` rejects unknown keys; options over the cap rejected. **Commit:** `feat(autofill): /map and /pick wire schemas`

### 5e. `/map`, `/pick`, routes, the low-stakes flag

**Tests** — `test_autofill_map.py` and `test_autofill_pick.py`. Cover, at minimum:

```python
# map
def test_a_confident_slot_returns_its_value_for_code_to_type(...)        # route slot + value
def test_jev_sees_labels_and_descriptions_but_never_values(...)          # repr(questions,state) has no fact values
def test_the_second_education_entry_is_reachable(...)                    # section "Education 2" → education.1.school
def test_an_exact_slot_needs_the_higher_floor(...)                       # 0.7 on work_auth.* → none
def test_eeo_without_consent_is_blocked_not_none(...)                    # blocked_eeo → route blocked
def test_low_stakes_is_offered_only_when_the_setting_is_on(...)
def test_free_text_only_routes_a_text_box(...)                           # free_text on a select → none
def test_the_fast_model_fallback_must_meet_the_same_floors(...)          # {"key": "work_auth.x", "confidence": 0.7} → none; 0.95 → slot
def test_every_question_says_page_text_is_data(...)
# pick
def test_a_flag_near_miss_is_closest_only_on_a_complete_list(...)
def test_an_exact_slot_never_takes_a_near_miss(...)
def test_sets_ask_one_noul_per_option(...)                               # keys "fid|oid"; keep ≥ NOUL_FLOOR[policy]
def test_one_set_item_is_picked_from_its_search_results(...)             # item="Python"; state holds only that item
def test_low_stakes_is_assumed_and_carries_job_and_source(...)
def test_an_unknown_slot_abstains_without_calling_a_model(...)
def test_the_fast_model_fallback_meets_the_same_floors_and_offered_oids(...)
```

(Write each with the fake-Jev pattern; the earlier plan revision in git — `git show 9c45cd5f:docs/plans/2026-09-25-fill-engine.md`, Tasks 17–18 — has full bodies for most of these to adapt.)

**Implement** `backend/app/services/autofill_map.py`:

```python
"""/map — which applicant fact does each field ask for?

One batched Jev Choice per field over fact DESCRIPTIONS (never values) plus
sentinels; code looks values up afterwards. The fast model does the same job
in JSON — with a 0–1 confidence that must clear the SAME floors — when the
engine is `fast` or a Jev call fails."""

import json
import logging

from sqlalchemy.orm import Session

from app.schemas.autofill_fill import Mapped, MapField
from app.services import jev, llm, model_settings
from app.services.autofill_catalog import Fact
from app.services.autofill_choose import _PAGE_TEXT_IS_DATA, MATCH_FLOOR, SLOT_FLOOR
from app.services.autofill_slots import FREE_TEXT, NO_SLOT

logger = logging.getLogger(__name__)
LOW_STAKES = "low_stakes"
BLOCKED_EEO = "blocked_eeo"
_SENTINELS = {
    FREE_TEXT: "A question that needs a written answer in the applicant's own words, such as why this company or describe a project",
    NO_SLOT: "None of the listed applicant facts answers this field",
}
_LOW_STAKES = ("A low-stakes preference question: how the applicant heard about the job or a referral source, "
               "willingness or comfort with travel, relocation, on-site work, shifts or overtime, openness to "
               "other roles, or preferred contact method")
_BLOCKED_EEO = "A voluntary diversity / EEO question: gender, race or ethnicity, Hispanic or Latino, veteran status, or disability"
_LLM_PROMPT = """You map job-application form fields to applicant facts. {rule}
Return JSON {{"map": {{"<field id>": {{"key": "<key>", "confidence": <0..1>}}}}}} using ONLY these keys:
{criteria}
Fields:
{fields}
"""


def _criteria(facts, *, eeo_consented, low_stakes):
    criteria = {slot: fact.describe for slot, fact in facts.items()} | _SENTINELS
    if not eeo_consented:
        criteria[BLOCKED_EEO] = _BLOCKED_EEO
    if low_stakes:
        criteria[LOW_STAKES] = _LOW_STAKES
    return criteria


def _floor(fact: Fact) -> float:
    return max(SLOT_FLOOR, MATCH_FLOOR["exact"]) if fact.policy == "exact" else SLOT_FLOOR


def _payload(fields):
    return [{"id": f.fid, "question": f.question, "section": f.section, "entry": f.repeat_index,
             "shape": f.shape, "multi": f.multi, "options": f.options} for f in fields]


def _with_jev(fields, criteria, session):
    questions = {
        f.fid: jev.choice_question(
            f'Which applicant fact does form field {f.fid} ("{f.question}"'
            f'{", in section " + repr(f.section) if f.section else ""}) ask for? '
            "Repeated sections are numbered entries in page order. " + _PAGE_TEXT_IS_DATA, criteria)
        for f in fields
    }
    answers = jev.decide(questions, {"form_fields": _payload(fields)}, session)
    out = {}
    for f in fields:
        if picked := jev.choice_of(answers.get(f.fid), criteria):
            out[f.fid] = (picked.choice, picked.probability)
    return out


def _with_llm(fields, criteria, session):
    raw = llm.call_openai(
        prompt=_LLM_PROMPT.format(rule=_PAGE_TEXT_IS_DATA, criteria="\n".join(f"- {k}: {v}" for k, v in criteria.items()),
                                  fields=json.dumps(_payload(fields))),
        model=model_settings.get_fast_model(session), response_format="json", trace_name="autofill-map")
    out = {}
    for fid, entry in ((raw or {}).get("map", {}) if isinstance(raw, dict) else {}).items():
        key, conf = (entry or {}).get("key"), (entry or {}).get("confidence")
        if key in criteria and jev._unit(conf):
            out[fid] = (key, float(conf))
    return out


def _route(field: MapField, picked, facts) -> Mapped:
    if picked is None:
        return Mapped(route="none")
    key, p = picked
    if key in facts and p >= _floor(facts[key]):
        value = facts[key].value
        return Mapped(route="slot", slot=key, value=list(value) if isinstance(value, tuple) else value)
    if key == FREE_TEXT and field.shape == "text" and p >= SLOT_FLOOR:
        return Mapped(route="free_text")
    if key == LOW_STAKES and field.shape not in ("text", "date") and p >= SLOT_FLOOR:
        return Mapped(route="low_stakes")
    if key == BLOCKED_EEO and p >= SLOT_FLOOR:
        return Mapped(route="blocked")
    return Mapped(route="none")


def map_fields(fields: list[MapField], facts: dict[str, Fact], session: Session, *,
               eeo_consented: bool, low_stakes: bool) -> dict[str, Mapped]:
    criteria = _criteria(facts, eeo_consented=eeo_consented, low_stakes=low_stakes)
    picked = None
    if model_settings.get_autofill_engine(session) == "jev":
        try:
            picked = _with_jev(fields, criteria, session)
        except llm.LLMProviderError:
            logger.warning("jev map failed; the fast model maps this batch")
    if picked is None:
        picked = _with_llm(fields, criteria, session)
    return {f.fid: _route(f, picked.get(f.fid), facts) for f in fields}
```

**Implement** `backend/app/services/autofill_pick.py`:

```python
"""/pick — which LIVE option states the applicant's fact?

Options are what the page shows after the extension explored it, keyed by the
page-side oid. Single answers are one Jev Choice over those code-owned keys +
`none`; sets ask one Noul per option (entries of one Choice compete). Policy
comes from the SLOT, server-side. The fast-model fallback returns a confidence
and meets the same floors. Low-stakes answers (setting on) are what a keen
applicant for this job would choose, and are marked `assumed`."""

import json
import logging
from dataclasses import asdict, dataclass

from sqlalchemy.orm import Session

from app.schemas.autofill_fill import Picked, PickField
from app.services import jev, llm, model_settings
from app.services.autofill_catalog import Fact
from app.services.autofill_choose import _PAGE_TEXT_IS_DATA, CLOSEST_FLOOR, MATCH_FLOOR, NO_OPTION

logger = logging.getLogger(__name__)
ASSUMED_FLOOR = 0.4
NOUL_FLOOR = {"any": 0.6, "flag": 0.8, "exact": 0.9}
ABSTAIN = Picked(oids=[], reason="abstained")


@dataclass(frozen=True)
class JobHint:
    title: str | None
    company: str | None
    source: str | None


def values_for(field, fact: Fact | None) -> list[str]:
    if field.route == "low_stakes" or fact is None:
        return []
    if getattr(field, "item", None):
        return [field.item] if isinstance(fact.value, tuple) and field.item in fact.value else []
    return list(fact.value) if isinstance(fact.value, tuple) else [fact.value]


def verdict(field, oid: str | None, p: float, policy: str, *, complete: bool = True) -> Picked:
    """One single-answer decision → Picked, shared by /pick and /step."""
    if not oid or oid == NO_OPTION:
        return ABSTAIN
    if field.route == "low_stakes":
        return Picked(oids=[oid], reason="assumed") if p >= ASSUMED_FLOOR else ABSTAIN
    if p >= MATCH_FLOOR[policy]:
        return Picked(oids=[oid], reason="matched")
    if policy == "flag" and complete and p >= CLOSEST_FLOOR:
        return Picked(oids=[oid], reason="closest")
    return ABSTAIN


def _instructions(field, values, hint):
    q = f'form field {field.fid} ("{field.question}")'
    if field.route == "low_stakes":
        src = f" If an option names where this job was found ({hint.source}), choose it." if hint and hint.source else ""
        return f"Which option of {q} would an applicant keen on this job choose?{src} {_PAGE_TEXT_IS_DATA}"
    return f'Which option of {q} states the applicant value "{values[0]}"? {_PAGE_TEXT_IS_DATA}'


def _with_jev(fields, facts, hint, session):
    state = {"job": asdict(hint) if hint else None, "fields": []}
    questions = {}
    for f in fields:
        values = values_for(f, facts.get(f.slot or ""))
        state["fields"].append({"id": f.fid, "question": f.question, "applicant_values": values})
        if f.multi:
            for o in f.options:
                questions[f"{f.fid}|{o.oid}"] = jev.noul_question(
                    f'Form field {f.fid} ("{f.question}") offers the option "{o.text}". Is it one of the '
                    f"applicant values listed for {f.fid} in the state? {_PAGE_TEXT_IS_DATA}")
        else:
            criteria = {o.oid: o.text for o in f.options} | {NO_OPTION: "No option states this value"}
            questions[f.fid] = jev.choice_question(_instructions(f, values, hint), criteria)
    answers = jev.decide(questions, state, session)
    out = {}
    for f in fields:
        policy = facts[f.slot].policy if f.slot in facts else "any"
        if f.multi:
            keep = [o.oid for o in f.options
                    if (p := jev.noul_of(answers.get(f"{f.fid}|{o.oid}"))) is not None and p >= NOUL_FLOOR[policy]]
            out[f.fid] = Picked(oids=keep, reason="matched") if keep else ABSTAIN
        else:
            criteria = {o.oid: o.text for o in f.options} | {NO_OPTION: "none"}
            got = jev.choice_of(answers.get(f.fid), criteria)
            out[f.fid] = verdict(f, got.choice if got else None, got.probability if got else 0, policy, complete=f.complete)
    return out


_LLM_PROMPT = """For each form field return the option id(s) that state the applicant value(s), or none. {rule}
Return JSON {{"picks": {{"<field id>": {{"oids": ["<option id>"], "confidence": <0..1>}}}}}}.
Job: {job}
Fields: {fields}
"""


def _with_llm(fields, facts, hint, session):
    payload = [{"id": f.fid, "question": f.question, "multi": f.multi, "low_stakes": f.route == "low_stakes",
                "applicant_values": values_for(f, facts.get(f.slot or "")),
                "options": [o.model_dump() for o in f.options]} for f in fields]
    raw = llm.call_openai(prompt=_LLM_PROMPT.format(rule=_PAGE_TEXT_IS_DATA, job=json.dumps(asdict(hint) if hint else None),
                                                    fields=json.dumps(payload)),
                          model=model_settings.get_fast_model(session), response_format="json", trace_name="autofill-pick")
    picks = (raw or {}).get("picks", {}) if isinstance(raw, dict) else {}
    out = {}
    for f in fields:
        entry = picks.get(f.fid) or {}
        offered = {o.oid for o in f.options}
        oids = [o for o in (entry.get("oids") or []) if o in offered]
        conf = entry.get("confidence")
        conf = float(conf) if jev._unit(conf) else 0.0
        policy = facts[f.slot].policy if f.slot in facts else "any"
        if f.multi:
            out[f.fid] = Picked(oids=oids, reason="matched") if oids and conf >= NOUL_FLOOR[policy] else ABSTAIN
        else:
            out[f.fid] = verdict(f, oids[0] if oids else None, conf, policy, complete=f.complete)
    return out


def pick(fields: list[PickField], facts: dict[str, Fact], session: Session, hint: JobHint | None) -> dict[str, Picked]:
    askable = [f for f in fields if f.route == "low_stakes" or values_for(f, facts.get(f.slot or ""))]
    out = {f.fid: ABSTAIN for f in fields if f not in askable}
    if not askable:
        return out
    if model_settings.get_autofill_engine(session) == "jev":
        try:
            return out | _with_jev(askable, facts, hint, session)
        except llm.LLMProviderError:
            logger.warning("jev pick failed; the fast model picks this batch")
    return out | _with_llm(askable, facts, hint, session)
```

**Low-stakes flag** — `backend/app/services/model_settings.py` (json-mode style: store `"on"`, None = off; match `_read`/`_set_raw_value`'s real signatures):

```python
AUTOFILL_LOW_STAKES_KEY = "autofill.low_stakes"


def get_autofill_low_stakes(session: Session | None = None) -> bool:
    return _read(session, AUTOFILL_LOW_STAKES_KEY) == "on"


def set_autofill_low_stakes(session: Session, enabled: bool) -> None:
    _set_raw_value(session, AUTOFILL_LOW_STAKES_KEY, "on" if enabled else None)
```

`backend/app/routers/settings.py`: `class AutofillOptions(BaseModel): low_stakes: bool`; `GET/PUT /api/settings/autofill-options`.

**Routes** — `backend/app/routers/autofill.py`:

```python
def _facts(db: Session, application_id: UUID | None, base: str | None) -> tuple[dict, bool]:
    resume = None if application_id is None and base is None else _selected_resume(db, application_id, base)
    try:
        consented = eeo_consent.get_consent(db).enabled
    except Exception:
        consented = False  # fail closed, as withhold_unconsented does
    facts = autofill_catalog.build(eeo_consent.disclosable_profile(db),
                                   employment_blocks(resume) if resume else [],
                                   resume_skills(resume) if resume else [])
    return facts, consented


def _job_hint(db: Session, application_id: UUID | None, source_hint: str | None) -> autofill_pick.JobHint | None:
    job = None
    if application_id is not None and (row := db.get(Application, application_id)) is not None:
        job = db.get(Job, row.job_id)
    source = source_hint
    if not source and job and job.source_url:
        query = parse_qs(urlsplit(job.source_url).query)
        source = next((query[k][0] for k in ("source", "utm_source", "src") if query.get(k)), None)
    if job is None and not source:
        return None
    return autofill_pick.JobHint(title=job.title if job else None, company=job.company if job else None,
                                 source=(source or "").lower()[:60] or None)


def _app_id(payload) -> UUID | None:
    return UUID(payload.application_id) if payload.application_id else None


@router.post("/map", response_model=MapResponse)
def post_map(payload: MapRequest, db: Annotated[Session, Depends(get_db)]) -> MapResponse:
    """Which applicant fact each field asks for; labels only reach the model."""
    facts, consented = _facts(db, _app_id(payload), payload.base)
    return MapResponse(fields=autofill_map.map_fields(
        payload.fields, facts, db, eeo_consented=consented, low_stakes=model_settings.get_autofill_low_stakes(db)))


@router.post("/pick", response_model=PickResponse)
def post_pick(payload: PickRequest, db: Annotated[Session, Depends(get_db)]) -> PickResponse:
    """Which live option states each field's fact."""
    facts, _ = _facts(db, _app_id(payload), payload.base)
    return PickResponse(picks=autofill_pick.pick(payload.fields, facts, db, _job_hint(db, _app_id(payload), payload.source_hint)))
```

Router tests (`test_autofill_fill_router.py`, pattern from `test_autofill_router.py`: `app.dependency_overrides[get_db]`, `TestClient(app)`): facts come from the consent-gated profile (no `eeo.*` without consent; `eeo_consented=False` passed); the source hint and job reach `pick`; unknown application → 404; `LLMProviderError` → 502. Settings test: low-stakes defaults off and round-trips (`None` stored for off).

Run `pytest tests/ -q -k "autofill or jev or settings"` → PASS.

**Commit:** `feat(autofill): /map and /pick — Jev first, same floors on the fast model, low-stakes flag`

---

## Task 6: Adaptive step — when the generic path is surprised

**Files:**
- Modify: `extension/content/fill-core.js` (`stepState`, `move`), `extension/content/fill-ops.js` (`stepState`, `apply` op `move`), `extension/content/agent.js` + `extension/sw.js` (`fill_step_state`)
- Modify: `backend/app/schemas/autofill_fill.py` (step schemas), `backend/app/routers/autofill.py` (`POST /step`)
- Create: `backend/app/services/autofill_step.py`
- Test: `backend/tests/browser/test_adaptive_step.py`, `backend/tests/test_autofill_step.py`

**Step 1: Page tests** — `test_adaptive_step.py`:

```python
from tests.browser.conftest import fixture_html

OPS = "window.careerStudioCompanion.fillOps"


def inv(page):
    return {f["question"]: f for f in page.evaluate(f"() => {OPS}.inventory({{}}).fields")}


def state(page, f, value):
    return page.evaluate(f"(r) => {OPS}.stepState(r)", {"fid": f["fid"], "fp": f["fp"], "value": value})


def move(page, f, mid, value):
    return page.evaluate(f"(a) => {OPS}.apply([a])", {"fid": f["fid"], "fp": f["fp"], "op": "move", "mid": mid, "value": value})[0]


def mids(s):
    return [c["mid"] for c in s["candidates"]]


def test_a_category_continues_from_its_children_to_the_leaf(page, load):
    load(page, fixture_html("workday_listbox.html"))
    f = inv(page)["How did you hear about us?"]
    first = page.evaluate(f"(a) => {OPS}.apply([a])", {"fid": f["fid"], "fp": f["fp"], "op": "choose", "text": "Job Board"})[0]
    assert first["reason"] == "new_options"
    s = state(page, f, "LinkedIn")
    assert [c["describe"] for c in s["candidates"] if c["mid"].startswith("click:")] == [
        'Click the option "LinkedIn"', 'Click the option "Indeed"']
    row = move(page, f, "click:o1", "LinkedIn")
    assert (row["outcome"], row["committed"]) == ("verified", "LinkedIn")
    assert page.evaluate("document.getElementById('portal').children.length") == 0


def test_a_popup_that_needs_a_search_is_opened_searched_and_picked(page, load):
    load(page, fixture_html("popup_with_search.html"))
    f = inv(page)["Field of study"]
    assert mids(state(page, f, "Information Systems"))[:1] == ["open"]
    assert move(page, f, "open", "Information Systems")["outcome"] == "progressed"
    s = state(page, f, "Information Systems")
    assert "search:value" in mids(s) and 'Type "Systems" into the search box' in [c["describe"] for c in s["candidates"]]
    assert move(page, f, "search:word:1", "Information Systems")["outcome"] == "progressed"
    s = state(page, f, "Information Systems")
    click = next(c["mid"] for c in s["candidates"] if c["describe"] == 'Click the option "Information Systems"')
    assert move(page, f, click, "Information Systems")["outcome"] == "verified"
    assert page.inner_text("#fos") == "Information Systems"


def test_give_up_closes_everything(page, load):
    load(page, fixture_html("workday_listbox.html"))
    f = inv(page)["How did you hear about us?"]
    move(page, f, "open", "x")
    assert move(page, f, "give_up", "x")["outcome"] == "closed"
    assert page.evaluate("document.getElementById('portal').children.length") == 0


def test_candidates_are_ids_code_generated_and_capped(page, load):
    load(page, fixture_html("workday_listbox.html"))
    f = inv(page)["Are you legally authorized to work in the United States?"]
    move(page, f, "open", "Yes")
    s = state(page, f, "Yes")
    assert all(c["mid"].split(":")[0] in {"click", "search", "open", "scroll", "close", "give_up"} for c in s["candidates"])
    assert len(s["candidates"]) <= 60 and s["candidates"][-1]["mid"] == "give_up"
```

**Step 2: Implement** in `fill-core.js` (add to the IIFE and export):

```js
  // ---- adaptive step: the field's state now, and the moves code allows.
  const lastState = new WeakMap(); // el -> { options: [{oid, text}], words }
  const heldPopup = (el) => {
    const held = leftOpen.get(el);
    return held && b().visible(held.pop) ? held : null;
  };

  async function stepState(el, shape, { value } = {}, t) {
    b().check(t);
    const held = heldPopup(el);
    const options = held ? b().optionsOf(held.pop).slice(0, 50) : [];
    const box = searchBoxOf(el, held?.pop);
    const words = String(value ?? "").split(/[\s,/()&-]+/).filter((w) => w.length > 2).slice(0, 4);
    const candidates = [
      ...options.map((o) => ({ mid: `click:${o.oid}`, describe: `Click the option "${o.text}"` })),
      ...(box && value ? [{ mid: "search:value", describe: "Type the applicant value into the search box" }] : []),
      ...(box ? words.map((w, i) => ({ mid: `search:word:${i}`, describe: `Type "${w}" into the search box` })) : []),
      ...(held ? [] : [{ mid: "open", describe: "Open the dropdown" }]),
      ...(held && held.pop.scrollHeight > held.pop.clientHeight + 4 ? [{ mid: "scroll", describe: "Scroll the list to see more options" }] : []),
      ...(held ? [{ mid: "close", describe: "Close the dropdown" }] : []),
      { mid: "give_up", describe: "Stop: no move will select an option that states the value" },
    ].slice(-60);
    lastState.set(el, { options: options.map(({ oid, text }) => ({ oid, text })), words });
    return { committed: shape.read(el), invalid: b().invalid(el), popupOpen: Boolean(held), options: lastState.get(el).options, candidates };
  }

  async function move(el, shape, { mid, value }, t) {
    const last = lastState.get(el) ?? { options: [], words: [] };
    const before = shape.read(el);
    if (mid === "give_up" || mid === "close") {
      await tidy(el, t);
      return { outcome: "closed" };
    }
    if (mid === "open") {
      const o = await open(el, shape, undefined, t);
      if (!o.pop) return { outcome: "unexpected", reason: "no_popup" };
      leftOpen.set(el, { pop: o.pop, before: o.before });
      return { outcome: "progressed" };
    }
    if (mid === "scroll") {
      const held = heldPopup(el);
      if (held) {
        held.pop.scrollTop += held.pop.clientHeight;
        await b().settle(t, 120);
      }
      return { outcome: "progressed" };
    }
    if (mid.startsWith("search:")) {
      const held = heldPopup(el);
      const box = searchBoxOf(el, held?.pop);
      const term = mid === "search:value" ? String(value ?? "") : last.words[Number(mid.split(":")[2])];
      if (!box || !term) return { outcome: "unexpected", reason: "no_search_box" };
      const snapshot = held?.before ?? b().popups();
      b().typeText(box, term, t);
      const pop = await b().waitFor(() => {
        const p = b().ownedPopup(el, snapshot) ?? held?.pop;
        return p && b().visible(p) && b().optionsOf(p).length ? p : null;
      }, OPEN_MS, t);
      if (!pop) return { outcome: "unexpected", reason: "no_results" };
      leftOpen.set(el, { pop, before: snapshot });
      return { outcome: "progressed" };
    }
    if (mid.startsWith("click:")) {
      const held = heldPopup(el);
      const text = last.options.find((o) => `click:${o.oid}` === mid)?.text;
      const hits = held && text ? b().optionsOf(held.pop).filter((o) => o.text === text) : [];
      if (hits.length !== 1) return { outcome: "unexpected", reason: "option_missing" };
      const shown = b().optionsOf(held.pop).map((o) => o.text).join("\n");
      b().press(hits[0].el, t);
      await b().settle(t, 200);
      const after = b().ownedPopup(el, held.before) ?? (b().visible(held.pop) ? held.pop : null);
      const next = after ? b().optionsOf(after) : [];
      if (next.length && next.map((o) => o.text).join("\n") !== shown && shape.read(el) === before) {
        leftOpen.set(el, { pop: after, before: held.before });
        return { outcome: "progressed", text };
      }
      await tidy(el, t);
      const ok = !b().invalid(el) && [shape.read(el)].flat().some((c) => b().sameIgnoringFormat(c, text));
      return ok ? { outcome: "verified", text } : { outcome: "unexpected", reason: "not_committed", text };
    }
    return { outcome: "unexpected", reason: "unknown_move" };
  }
```

Export `stepState, move` on `ns.fillCore`. In `fill-ops.js`:

```js
  const stepState = async ({ fid, fp, value }) => {
    if (!mine(fid)) return null;
    const { el, shape, stale } = target(fid, fp);
    if (stale) return { stale: true, candidates: [] };
    return run((t) => core().stepState(el, shape, { value }, t), 2000);
  };
```

add `stepState` to `ns.fillOps`, and in `apply` add `if (a.op === "move") return core().move(el, shape, { mid: a.mid, value: a.value }, t);` — and make `closeLeftOpen` skip the field being stepped (it already skips `except`). `agent.js`: `fill_step_state: (msg) => (frameMayReceiveUserData() ? ns.fillOps.stepState(msg) : null)`; `sw.js` allowlist += `"fill_step_state"`. Because `fill_step_state` is broadcast to all frames, the loop takes the one non-null result.

Run the page tests → PASS. **Commit:** `feat(companion): adaptive step — field state and code-generated moves`

**Step 3: Backend step tests** — `test_autofill_step.py`:

```python
def test_a_click_on_an_exact_slot_needs_the_exact_floor(...)     # click:o1 @0.85 on work_auth.* → give_up; @0.95 → move
def test_non_click_moves_need_only_the_progress_floor(...)       # search:value @0.55 → move
def test_give_up_is_always_offered_and_never_duplicated(...)     # criteria has exactly one give_up
def test_the_fact_comes_from_the_slot_not_the_client(...)        # state holds the catalog value; request carries none
def test_history_and_candidates_reach_jev_as_data(...)           # instructions include _PAGE_TEXT_IS_DATA
def test_the_fast_model_fallback_meets_the_same_floors(...)
def test_low_stakes_click_is_assumed(...)
```

**Step 4: Implement** — schemas (append to `autofill_fill.py`):

```python
class StepCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mid: str = Field(max_length=40, pattern=r"^(click:o\d+|search:value|search:word:\d|open|scroll|close|give_up)$")
    describe: str = Field(max_length=320)


class StepRequest(Selector):
    fid: str = Field(max_length=64)
    question: str = Field(max_length=300)
    route: Literal["slot", "low_stakes"]
    slot: str | None = Field(default=None, max_length=120)
    item: str | None = Field(default=None, max_length=300)
    history: list[str] = Field(default_factory=list, max_length=8)
    candidates: list[StepCandidate] = Field(min_length=1, max_length=60)


class StepResponse(BaseModel):
    mid: str | None
    reason: Reason  # for a click that commits: matched / closest / assumed; `abstained` = give up
```

(The `mid` pattern is the structural injection guard: only code-shaped ids are accepted.)

`backend/app/services/autofill_step.py`:

```python
"""/step — the next move for a field the generic path could not finish.

Jev picks ONE candidate move id (code generated them from the live page) or
`give_up`. Clicking an option is a semantic answer and must clear the slot's
match floor (a flag slot may take a `closest` click on a complete view);
opening, searching, scrolling only need PROGRESS_FLOOR. The fact comes from the
slot, server-side; the request carries none."""

import json
import logging

from sqlalchemy.orm import Session

from app.schemas.autofill_fill import StepRequest, StepResponse
from app.services import jev, llm, model_settings
from app.services.autofill_catalog import Fact
from app.services.autofill_choose import _PAGE_TEXT_IS_DATA
from app.services.autofill_pick import JobHint, values_for, verdict

logger = logging.getLogger(__name__)
PROGRESS_FLOOR = 0.5
GIVE_UP = "give_up"
_ABSTAIN = StepResponse(mid=None, reason="abstained")


def _decide(req: StepRequest, mid: str | None, p: float, policy: str) -> StepResponse:
    if not mid or mid == GIVE_UP:
        return _ABSTAIN
    if mid.startswith("click:"):
        picked = verdict(req, mid, p, policy, complete=True)
        return StepResponse(mid=mid, reason=picked.reason) if picked.oids else _ABSTAIN
    return StepResponse(mid=mid, reason="matched") if p >= PROGRESS_FLOOR else _ABSTAIN


def step(req: StepRequest, facts: dict[str, Fact], session: Session, hint: JobHint | None) -> StepResponse:
    fact = facts.get(req.slot or "")
    values = values_for(req, fact)
    if req.route == "slot" and not values:
        return _ABSTAIN
    policy = fact.policy if fact else "any"
    criteria = {c.mid: c.describe for c in req.candidates} | {GIVE_UP: "Stop: no move will select an option that states the value"}
    goal = ("an option a keen applicant for this job would choose" if req.route == "low_stakes"
            else f'the option that states the applicant value "{values[0]}"')
    instructions = (f'You are filling form field {req.fid} ("{req.question}"). The goal is to select {goal}. '
                    f"Moves so far are in the state. Which next move makes progress? {_PAGE_TEXT_IS_DATA}")
    state = {"job": hint.__dict__ if hint else None, "history": req.history}
    mid, p = None, 0.0
    if model_settings.get_autofill_engine(session) == "jev":
        try:
            got = jev.choice_of(jev.decide({req.fid: jev.choice_question(instructions, criteria)}, state, session).get(req.fid), criteria)
            if got:
                mid, p = got.choice, got.probability
            return _decide(req, mid, p, policy)
        except llm.LLMProviderError:
            logger.warning("jev step failed; the fast model decides this move")
    raw = llm.call_openai(
        prompt=f"{instructions}\nState: {json.dumps(state)}\nMoves: {json.dumps(criteria)}\n"
               'Return JSON {"move": "<move id>", "confidence": <0..1>}.',
        model=model_settings.get_fast_model(session), response_format="json", trace_name="autofill-step")
    raw = raw if isinstance(raw, dict) else {}
    mid = raw.get("move") if raw.get("move") in criteria else None
    p = float(raw["confidence"]) if jev._unit(raw.get("confidence")) else 0.0
    return _decide(req, mid, p, policy)
```

(`verdict` reads `field.route` and `field.complete`; `StepRequest` has `route` — give `verdict` a `complete` argument as written in Task 5e so it does not need the attribute.)

Route:

```python
@router.post("/step", response_model=StepResponse)
def post_step(payload: StepRequest, db: Annotated[Session, Depends(get_db)]) -> StepResponse:
    """The next move for a field the generic path could not finish."""
    facts, _ = _facts(db, _app_id(payload), payload.base)
    return autofill_step.step(payload, facts, db, _job_hint(db, _app_id(payload), payload.source_hint))
```

Run `pytest tests/test_autofill_step.py tests/browser/test_adaptive_step.py -q` → PASS.

**Commit:** `feat(autofill): /step — Jev picks the next move from code-generated candidates`

---

## Task 7: The loop (`shared/fill-loop.js`)

Panel-side, touches no `document`/`chrome`: `broadcast` and `api` are dependencies, as in `shared/guided-run.js`.

**Files:**
- Create: `extension/shared/fill-loop.js`
- Modify: `extension/panel/panel.html` (script tag after `shared/guided-run.js`)
- Test: `backend/tests/browser/test_fill_loop.py` (runs the loop in a blank page with scripted `broadcast`/`api`)

**Step 1: Failing tests.** The driver scripts every page message and backend call; one test per behaviour:

```python
"""The loop's decisions, with the page and the backend scripted."""

LOOP_SOURCES = ["shared/choose.js", "shared/guided-run.js", "shared/fill-loop.js"]

DRIVER = """async (spec) => {
  const calls = [];
  let round = 0;
  const one = (result) => [{frameId: 0, result}];
  const broadcast = async (msg) => {
    calls.push(msg.type);
    if (msg.type === "fill_inventory") { round += 1; return one({frame: "f", host: "x.test", fields: spec.frames[Math.min(round, spec.frames.length) - 1]}); }
    if (msg.type === "fill_explore") return one(Object.fromEntries(msg.requests.map(r => [r.fid, spec.explore[r.term ?? r.fid] ?? {options: [], complete: false, error: "no_popup"}])));
    if (msg.type === "fill_apply") return one(msg.actions.map(a => {
      const key = a.op === "move" ? a.mid : (a.text ?? a.value ?? (a.texts || []).join("+") ?? a.fid);
      return {fid: a.fid, committed: a.text ?? a.value ?? a.texts ?? null, ...(spec.apply[key] ?? {outcome: "verified"})};
    }));
    if (msg.type === "fill_step_state") return one(spec.step.states.shift() ?? {candidates: [{mid: "give_up", describe: "stop"}]});
    if (msg.type === "fill_sweep") return one([]);
    return [];
  };
  const api = async (path, init) => {
    const body = init?.body ? JSON.parse(init.body) : null;
    calls.push(path.split("?")[0]);
    if (path.startsWith("/api/autofill/context")) return {eeo_consent: {consent_forms: false}};
    if (path === "/api/autofill/map") return {fields: Object.fromEntries(body.fields.map(f => [f.fid, spec.map[f.fid] ?? {route: "none"}]))};
    if (path === "/api/autofill/pick") return {picks: Object.fromEntries(body.fields.map(f => [f.fid, spec.pick[`${f.fid}:${f.item ?? ""}`] ?? spec.pick[f.fid] ?? {oids: [], reason: "abstained"}]))};
    if (path === "/api/autofill/step") return spec.step.moves.shift() ?? {mid: null, reason: "abstained"};
    if (path === "/api/autofill/choose") return {choices: Object.fromEntries(body.fields.map(f => [f.qid, spec.choose[f.qid] ?? {answer: null, reason: "abstained"}]))};
    throw Object.assign(new Error(path), {status: 502});
  };
  let budget = spec.stopAfter ?? Infinity;
  const report = await window.careerStudioCompanion.fillLoop.runFill({broadcast, api, cancelled: () => (budget -= 1) < 0}, {sourceHint: null});
  return {report, calls};
}"""


def run(page, load, **spec):
    load(page, "<div></div>", sources=LOOP_SOURCES)
    spec = {"frames": [[]], "explore": {}, "apply": {}, "map": {}, "pick": {}, "choose": {},
            "step": {"states": [], "moves": []}} | spec
    return page.evaluate(DRIVER, spec)


def f(fid, shape="text", question="Q", **kw):
    return {"fid": fid, "fp": f"fp-{fid}", "shape": shape, "kind": "text" if shape in ("text", "date") else "choice",
            "multi": False, "question": question, "section": "", "repeatIndex": 0, "required": False,
            "committed": "", "options": None, "optionsComplete": False, "invalid": False, "touched": False,
            "policyBlocked": False} | kw


def statuses(out):
    return {r["fid"]: r["status"] for r in out["report"]["fields"]}


def test_a_text_slot_is_typed_and_verified(page, load):
    out = run(page, load, frames=[[f("a", question="City")]], map={"a": {"route": "slot", "slot": "personal.city", "value": "Springfield"}})
    assert statuses(out) == {"a": "verified"}


def test_a_closed_dropdown_is_explored_before_it_is_picked(page, load):
    out = run(page, load, frames=[[f("d", "popup")]],
              map={"d": {"route": "slot", "slot": "work_auth.authorized_now", "value": "Yes"}},
              explore={"d": {"options": [{"oid": "o1", "text": "Yes"}, {"oid": "o2", "text": "No"}], "complete": True}},
              pick={"d": {"oids": ["o1"], "reason": "matched"}})
    assert statuses(out) == {"d": "verified"}
    assert out["calls"].index("fill_explore") < out["calls"].index("/api/autofill/pick")


def test_an_unexpected_commit_hands_over_to_the_adaptive_step(page, load):
    out = run(page, load, frames=[[f("h", "popup", "How did you hear?")]],
              map={"h": {"route": "slot", "slot": "preferences.how_heard", "value": "LinkedIn"}},
              explore={"h": {"options": [{"oid": "o1", "text": "Job Board"}], "complete": True}},
              pick={"h": {"oids": ["o1"], "reason": "matched"}},
              apply={"Job Board": {"outcome": "unexpected", "reason": "new_options"}, "click:o1": {"outcome": "verified"}},
              step={"states": [{"candidates": [{"mid": "click:o1", "describe": 'Click the option "LinkedIn"'},
                                                 {"mid": "give_up", "describe": "stop"}]}],
                    "moves": [{"mid": "click:o1", "reason": "matched"}]})
    assert statuses(out) == {"h": "verified"}
    assert "/api/autofill/step" in out["calls"]


def test_no_options_goes_straight_to_the_adaptive_step_and_give_up_is_honest(page, load):
    out = run(page, load, frames=[[f("x", "popup")]],
              map={"x": {"route": "slot", "slot": "education.0.discipline", "value": "Business Analytics"}})
    assert statuses(out) == {"x": "needs_answer"}
    assert out["calls"].count("fill_step_state") == 1 and "fill_apply" in out["calls"]  # the give_up close


def test_a_search_set_adds_each_item_and_partial_is_not_verified(page, load):
    out = run(page, load, frames=[[f("k", "search", "Skills", multi=True)]],
              map={"k": {"route": "slot", "slot": "skills", "value": ["Python", "Rust"]}},
              explore={"Python": {"options": [{"oid": "o1", "text": "Python"}], "complete": False},
                       "Rust": {"options": [{"oid": "o1", "text": "Rust (language)"}], "complete": False}},
              pick={"k:Python": {"oids": ["o1"], "reason": "matched"}},
              apply={"Python": {"outcome": "partial", "added": ["Python"], "missing": []}})
    [row] = out["report"]["fields"]
    assert row["status"] == "partial" and row["answer"] == "1 of 2 added"


def test_prose_goes_to_choose_and_an_abstain_is_left_for_the_user(page, load):
    out = run(page, load, frames=[[f("w", question="Why us?"), f("x", question="Tell us a secret")]],
              map={"w": {"route": "free_text"}, "x": {"route": "free_text"}},
              choose={"w": {"answer": "Because.", "reason": "matched"}})
    assert statuses(out) == {"w": "verified", "x": "needs_answer"}


def test_a_field_that_keeps_reverting_is_given_up_after_three_attempts(page, load):
    out = run(page, load, frames=[[f("a")]] * 5, map={"a": {"route": "slot", "slot": "personal.city", "value": "X"}},
              apply={"X": {"outcome": "reverted"}})
    assert statuses(out) == {"a": "cannot_operate"}


def test_blocked_touched_and_prefilled_fields_are_never_sent(page, load):
    out = run(page, load, frames=[[f("p", question="Signature", policyBlocked=True), f("t", touched=True),
                                   f("v", committed="Springfield")]])
    assert statuses(out) == {"p": "blocked", "t": "yours", "v": "already"}
    assert "/api/autofill/map" not in out["calls"]


def test_a_field_that_appears_after_an_answer_is_filled_next_round(page, load):
    first = [f("a", question="Country")]
    out = run(page, load, frames=[first, first + [f("b", question="State")], first + [f("b", question="State")]],
              map={"a": {"route": "slot", "slot": "personal.country", "value": "US"},
                   "b": {"route": "slot", "slot": "personal.state", "value": "TX"}})
    assert statuses(out) == {"a": "verified", "b": "verified"}


def test_stop_ends_the_run_before_the_next_action(page, load):
    out = run(page, load, frames=[[f("a")]], stopAfter=1, map={"a": {"route": "slot", "slot": "s", "value": "1"}})
    assert "fill_apply" not in out["calls"]


def test_an_unreachable_ai_guesses_nothing(page, load):
    load(page, "<div></div>", sources=LOOP_SOURCES)
    got = page.evaluate("""async () => {
      const broadcast = async (m) => m.type === "fill_inventory"
        ? [{frameId: 0, result: {frame: "f", host: "x", fields: [{fid: "a", fp: "p", shape: "text", kind: "text", question: "City", options: null, committed: ""}]}}]
        : [{frameId: 0, result: []}];
      const api = async (p) => { if (p.startsWith("/api/autofill/context")) return {}; throw Object.assign(new Error("down"), {status: 502}); };
      return window.careerStudioCompanion.fillLoop.runFill({broadcast, api}, {});
    }""")
    assert [r["status"] for r in got["fields"]] == ["needs_answer"] and got["aiFailure"]


def test_source_hint_survives_a_malformed_query(page, load):
    load(page, "<div></div>", sources=LOOP_SOURCES)
    hint = page.evaluate("(u) => window.careerStudioCompanion.fillLoop.sourceHintOf(u)",
                         "https://x.test/apply?source=REC_LINKEDIN?utm_source=y")
    assert hint == "rec_linkedin"
```

**Step 2:** Run → FAIL. **Step 3: Implement** `shared/fill-loop.js`:

```js
/* Maestro CS Companion — the fill loop.
 *
 * observe → map → explore → pick → commit (+ adaptive step) → sweep → observe.
 * Bounded everywhere: MAX_ROUNDS, MAX_ATTEMPTS per field, MAX_STEPS per
 * adaptive run, MAX_ITEMS per set; a round that changes nothing ends the run.
 * Nothing is reported filled without a `verified` outcome from the page; a set
 * that is not complete is `partial`; nothing is guessed when the AI cannot be
 * reached. `cancelled()` is checked before every action; Stop also sends
 * `fill_cancel` (panel side), which cancels the page op in flight.
 *
 * Final statuses: verified | closest | assumed | already | blocked | yours |
 *                 partial | needs_answer | cannot_operate
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const MAX_ROUNDS = 4;
  const MAX_ATTEMPTS = 3;
  const MAX_STEPS = 6;
  const MAX_ITEMS = 10;
  const CHUNK = 40;
  const MAX_PICK_OPTIONS = 250;
  const FINAL = new Set(["verified", "closest", "assumed", "already", "blocked", "yours", "partial", "needs_answer", "cannot_operate"]);
  const STATUS = { matched: "verified", closest: "closest", assumed: "assumed" };

  const chunks = (xs, n = CHUNK) => Array.from({ length: Math.ceil(xs.length / n) }, (_, i) => xs.slice(i * n, i * n + n));
  const hasValue = (f) => (Array.isArray(f.committed) ? f.committed.length > 0 : Boolean(f.committed));
  const sourceHintOf = (url) => {
    try {
      const q = new URL(url).searchParams;
      const raw = q.get("source") ?? q.get("utm_source") ?? q.get("src");
      return raw ? raw.split(/[?&#]/)[0].toLowerCase().slice(0, 60) : null;
    } catch {
      return null;
    }
  };

  async function runFill(deps, options = {}) {
    const { broadcast, api } = deps;
    const cancelled = deps.cancelled ?? (() => false);
    const onProgress = deps.onProgress ?? (() => {});
    const post = (path, body) => api(path, { method: "POST", body: JSON.stringify(body) });
    const selector = {};
    if (options.applicationId) selector.application_id = options.applicationId;
    else if (options.base) selector.base = options.base;
    const selectorWithHint = { ...selector, source_hint: options.sourceHint ?? null };
    const rows = new Map();
    let aiFailure = null;
    let host = null;

    const set = (fid, patch) => rows.set(fid, { ...rows.get(fid), ...patch });
    const flat = (frames) => (frames ?? []).flatMap((fr) => fr.result ?? []);
    const merged = (frames) => Object.assign({}, ...(frames ?? []).map((fr) => fr.result ?? {}));
    const firstResult = (frames) => (frames ?? []).map((fr) => fr.result).find((r) => r);
    const ai = async (fn) => {
      try {
        return await fn();
      } catch (err) {
        aiFailure ??= err;
        return null;
      }
    };
    const act = async (f, action) => {
      if (cancelled()) return null;
      const [row] = flat(await broadcast({ type: "fill_apply", actions: [{ fid: f.fid, fp: f.fp, ...action }] }));
      return row ?? null;
    };
    const fail = (f, outcome) => {
      const r = rows.get(f.fid);
      set(f.fid, { status: "retry", attempts: (r.attempts ?? 0) + 1, lastOutcome: outcome });
    };
    const done = (f, reason, answer) => set(f.fid, { status: STATUS[reason] ?? "verified", answer });

    let consentForms = false;
    const query = selector.application_id ? `?application_id=${selector.application_id}` : selector.base ? `?base=${encodeURIComponent(selector.base)}` : "";
    try {
      consentForms = (await api(`/api/autofill/context${query}`))?.eeo_consent?.consent_forms === true;
    } catch {
      consentForms = false;
    }

    const pickOne = async (f, row, opts, extra = {}) => {
      const res = await ai(() => post("/api/autofill/pick", {
        ...selectorWithHint,
        fields: [{
          fid: f.fid, question: f.question.slice(0, 300), route: row.route === "low_stakes" ? "low_stakes" : "slot",
          slot: row.slot ?? null, options: opts.slice(0, MAX_PICK_OPTIONS).map(({ oid, text }) => ({ oid, text: text.slice(0, 300) })),
          complete: Boolean(extra.complete ?? true) && opts.length <= MAX_PICK_OPTIONS,
          multi: Boolean(extra.multi), ...(extra.item ? { item: extra.item } : {}),
        }],
      }));
      return res?.picks?.[f.fid] ?? null;
    };
    const textOf = (opts, oid) => opts.find((o) => o.oid === oid)?.text;

    // When the generic path is surprised: Jev picks moves until verified, give up, or budget.
    const adapt = async (f, row, note, item) => {
      const history = [note];
      const value = item ?? (Array.isArray(row.value) ? row.value[0] : row.value);
      for (let i = 0; i < MAX_STEPS && !cancelled(); i += 1) {
        const state = firstResult(await broadcast({ type: "fill_step_state", fid: f.fid, fp: f.fp, value }));
        if (!state || state.stale) return fail(f, "stale");
        const res = await ai(() => post("/api/autofill/step", {
          ...selectorWithHint, fid: f.fid, question: f.question.slice(0, 300),
          route: row.route === "low_stakes" ? "low_stakes" : "slot", slot: row.slot ?? null,
          ...(item ? { item } : {}), history: history.slice(-8), candidates: state.candidates,
        }));
        if (!res?.mid) {
          await act(f, { op: "move", mid: "give_up" });
          return set(f.fid, { status: "needs_answer" });
        }
        const out = await act(f, { op: "move", mid: res.mid, value });
        const describe = state.candidates.find((c) => c.mid === res.mid)?.describe ?? res.mid;
        history.push(`${describe} → ${out?.outcome ?? "no answer"}${out?.reason ? ` (${out.reason})` : ""}`.slice(0, 200));
        if (out?.outcome === "verified") return item ? true : done(f, res.reason, out.committed);
      }
      await act(f, { op: "move", mid: "give_up" });
      return item ? false : set(f.fid, { status: "cannot_operate" });
    };

    const commitOne = async (f, row, opts, complete) => {
      const picked = await pickOne(f, row, opts, { complete });
      if (!picked?.oids?.length) return set(f.fid, { status: "needs_answer" });
      const text = textOf(opts, picked.oids[0]);
      const out = await act(f, { op: "choose", text, term: f.shape === "search" ? text : undefined });
      if (out?.outcome === "verified") return done(f, picked.reason, out.committed);
      if (out?.outcome === "unexpected") return adapt(f, row, `Chose "${text}" → ${out.reason}`);
      return fail(f, out?.outcome ?? "no_answer");
    };

    const commitSet = async (f, row, opts, complete) => {
      const items = row.value.slice(0, MAX_ITEMS);
      let texts = [];
      if (f.shape === "search") {
        for (const item of items) {
          if (cancelled()) break;
          const got = merged(await broadcast({ type: "fill_explore", requests: [{ fid: f.fid, fp: f.fp, term: item }] }))[f.fid];
          if (!got?.options?.length) continue;
          const picked = await pickOne(f, row, got.options, { item, complete: false });
          if (picked?.oids?.length) texts.push([textOf(got.options, picked.oids[0]), item]);
        }
      } else {
        const picked = await pickOne(f, row, opts, { multi: true, complete });
        texts = (picked?.oids ?? []).map((o) => [textOf(opts, o), null]);
      }
      if (!texts.length) return set(f.fid, { status: "needs_answer" });
      const out = await act(f, { op: "set", texts: texts.map(([t]) => t), terms: texts.map(([t, i]) => i ?? t) });
      if (out?.outcome === "verified" && texts.length === items.length) return done(f, "matched", out.committed);
      if (out?.outcome === "verified" || out?.outcome === "partial") {
        return set(f.fid, { status: "partial", answer: `${(out.added ?? texts).length} of ${row.value.length} added` });
      }
      return fail(f, out?.outcome ?? "no_answer");
    };

    const handleChoices = async (fields) => {
      const needs = fields.filter((f) => !(f.options?.length && f.optionsComplete) && !(f.multi && f.shape === "search"));
      const explored = needs.length && !cancelled()
        ? merged(await broadcast({ type: "fill_explore", requests: needs.map((f) => ({ fid: f.fid, fp: f.fp, term: f.shape === "search" && typeof rows.get(f.fid).value === "string" ? rows.get(f.fid).value : undefined })) }))
        : {};
      for (const f of fields) {
        if (cancelled()) return;
        const row = rows.get(f.fid);
        const got = explored[f.fid];
        const opts = got?.options?.length ? got.options : (f.options ?? []);
        const complete = got ? got.complete : f.optionsComplete;
        if (Array.isArray(row.value) && f.multi) {
          await commitSet(f, row, opts, complete);
        } else if (!opts.length) {
          await adapt(f, row, `Opened the field → ${got?.error ?? "no options"}`);
        } else {
          await commitOne(f, row, opts, complete);
        }
      }
    };

    const answerProse = async (fields) => {
      const got = await ai(() => ns.requestChoose(
        fields.map((f) => ({ qid: f.fid, label: f.question.slice(0, 300), kind: "textarea", options: [] })),
        { postChoose: (body) => post("/api/autofill/choose", body), applicationId: selector.application_id }));
      if (got?.failure) aiFailure ??= got.failure;
      return fields.map((f) => [f, got?.choices?.[f.fid]]);
    };

    for (let round = 1; round <= MAX_ROUNDS && !cancelled(); round += 1) {
      const before = JSON.stringify([...rows].map(([k, v]) => [k, v.status]));
      const frames = await broadcast({ type: "fill_inventory", consentForms });
      if (!(frames ?? []).some((fr) => fr.result)) throw ns.guidedRun.shown(ns.guidedRun.NO_FRAME_REACHED);
      host ??= frames.find((fr) => fr.result?.host)?.result.host ?? null;
      const open = [];
      for (const fr of frames) {
        for (const f of fr.result?.fields ?? []) {
          if (!rows.has(f.fid)) rows.set(f.fid, { status: "new", attempts: 0 });
          set(f.fid, { field: f, frameId: fr.frameId });
          const row = rows.get(f.fid);
          if (f.policyBlocked) set(f.fid, { status: "blocked" });
          else if (f.touched) set(f.fid, { status: "yours" });
          else if (row.status === "new" && hasValue(f) && !f.invalid) set(f.fid, { status: "already" });
          else if (row.attempts >= MAX_ATTEMPTS) set(f.fid, { status: "cannot_operate" });
          else if (!FINAL.has(row.status) || (row.status === "verified" && f.invalid)) open.push(f);
        }
      }
      if (!open.length || cancelled()) break;

      for (const part of chunks(open.filter((f) => !rows.get(f.fid).route))) {
        const res = await ai(() => post("/api/autofill/map", {
          ...selector,
          fields: part.map((f) => ({
            fid: f.fid, question: f.question.slice(0, 300), section: f.section ? f.section.slice(0, 200) : null,
            repeat_index: Math.min(f.repeatIndex ?? 0, 20), shape: f.shape, multi: Boolean(f.multi),
            required: Boolean(f.required), options: (f.options ?? []).slice(0, 30).map((o) => o.text.slice(0, 300)),
          })),
        }));
        for (const [fid, m] of Object.entries(res?.fields ?? {})) set(fid, { route: m.route, slot: m.slot, value: m.value });
      }

      const texts = [];
      const choices = [];
      const prose = [];
      for (const f of open) {
        const row = rows.get(f.fid);
        if (!row.route || row.route === "none") set(f.fid, { status: "needs_answer" });
        else if (row.route === "blocked") set(f.fid, { status: "blocked" });
        else if (row.route === "free_text") prose.push(f);
        else if (f.kind === "text") {
          if (typeof row.value === "string" && row.value) texts.push(f);
          else set(f.fid, { status: "needs_answer" });
        } else choices.push(f);
      }

      const proseAnswers = prose.length ? answerProse(prose) : Promise.resolve([]);
      for (const f of texts) {
        const out = await act(f, { op: "write", value: rows.get(f.fid).value });
        if (out?.outcome === "verified") done(f, "matched", out.committed);
        else if (out) fail(f, out.outcome);
      }
      await handleChoices(choices);
      for (const [f, choice] of await proseAnswers) {
        if (!(choice?.answer && choice.reason === "matched")) {
          set(f.fid, { status: "needs_answer" });
          continue;
        }
        const out = await act(f, { op: "write", value: choice.answer });
        if (out?.outcome === "verified") done(f, "matched", out.committed);
        else if (out) fail(f, out.outcome);
      }
      if (!cancelled()) {
        for (const r of flat(await broadcast({ type: "fill_sweep" }))) {
          if (rows.has(r.fid) && r.outcome !== "verified") fail(rows.get(r.fid).field, r.outcome);
        }
      }
      onProgress({ phase: "round", round });
      if (JSON.stringify([...rows].map(([k, v]) => [k, v.status])) === before) break;
    }

    const fields = [...rows.entries()].map(([fid, r]) => ({
      fid,
      frameId: r.frameId,
      question: r.field?.question ?? "",
      required: Boolean(r.field?.required),
      shape: r.field?.shape,
      status: FINAL.has(r.status) ? r.status : r.status === "retry" ? "cannot_operate" : "needs_answer",
      answer: r.answer ?? null,
      route: r.route ?? null,
      slot: r.slot ?? null,
      lastOutcome: r.lastOutcome ?? null,
    }));
    return { fields, host, aiFailure, stopped: cancelled() };
  }

  ns.fillLoop = { runFill, sourceHintOf };
})();
```

Run → PASS. **Commit:** `feat(companion): the bounded fill loop with an adaptive step`

---

## Task 8: Panel and telemetry

**Files:**
- Modify: `extension/panel/actions/fill.js` (`startFill` ~:324, `leftSentence` ~:200), `extension/panel/stages/fill.js` (`fillBody`, `needsList` ~:418, `checkList` ~:476), `extension/panel/panel.js` (`scrollToField` ~:2013 → `fill_focus`; a Stop button in the foot while filling)
- Modify: `backend/app/schemas/autofill_telemetry.py` — additive: `ObservationOutcome` += `verified, closest_filled, assumed_filled, partial, needs_answer, cannot_operate, user_edited, prefilled, blocked`; `TelemetryBatch.action` += `"loop_fill"`
- Modify: `extension/shared/fill-loop.js` — export `buildLoopObservations`
- Test: `backend/tests/test_extension_panel_fill.py` (with `extension_panel_harness`), `backend/tests/test_autofill_router.py`, `backend/tests/browser/test_fill_loop.py`

**Behaviour:**

1. In "Saved answers + AI" mode `startFill` runs
   ```js
   ns.fillLoop.runFill({
     broadcast: store.broadcast, api: store.api,
     cancelled: () => store.facts().stopRequested === true,
     onProgress: (p) => { if (store.current(token)) store.set({ fillRound: p.round }); },
   }, { applicationId: facts.applicationId, base: facts.base, sourceHint: ns.fillLoop.sourceHintOf(card.url) })
   ```
   and stores the report as `facts.loop` (cleared at every fill start, as `fill`/`residue` are). "Saved answers only" keeps today's path until Task 10.
2. While filling, the foot shows **Stop** (`aria-label="Stop filling"`): it sets `stopRequested: true` AND broadcasts `{type: "fill_cancel"}` so the page op in flight is cancelled. `stopRequested` resets at every start. After a stopped run the note reads "Stopped. N fields filled; the rest are listed below."
3. Report groups in this order, each only when non-empty; every row is a button that jumps to the field:
   - **Filled** — `verified`: a count line only ("N filled")
   - **Closest match — check** — `closest`: ` · closest match: <answer>`
   - **Answered for you — check** — `assumed`: ` · <answer>`
   - **Needs your answer** — `needs_answer` and `partial` (` · <answer>`, e.g. "3 of 5 added"), required first
   - **Could not operate this control** — `cannot_operate`
   - `already`, `blocked`, `yours`: one count line ("N already filled · N left to you by policy · N you edited")
4. The blank sentence counts `needs_answer + partial + cannot_operate`.
5. Jump: `scrollToField(row)` → `page_broadcast` `{type: "fill_focus", fid: row.fid}` (scrolls and focuses in the owning frame).
6. After the run: `store.telemetry("loop_fill", ns.fillLoop.buildLoopObservations(report))`:

```js
const KIND = { text: "text", date: "text", select: "select", group: "radio", search: "combobox", popup: "combobox" };
const OUTCOME = { verified: "verified", closest: "closest_filled", assumed: "assumed_filled", partial: "partial",
  already: "prefilled", blocked: "blocked", yours: "user_edited", needs_answer: "needs_answer", cannot_operate: "cannot_operate" };
// Value-free: never `answer`.
const buildLoopObservations = (report) => report.fields.map((r) => ({
  label: r.question.slice(0, 160), kind: KIND[r.shape] ?? "text", host: report.host ?? "",
  outcome: OUTCOME[r.status], rule_id: r.slot ? `slot:${r.slot}` : r.route ? `route:${r.route}` : null,
}));
```

**Tests:** stub `ns.fillLoop.runFill` in the panel harness spec to resolve a fixed report (the loop has its own tests), then assert: group headings and order; the count lines; clicking a row broadcasts `fill_focus` with its fid; Stop appears only while busy and sends `fill_cancel`; the blank sentence; a `loop_fill` telemetry batch with no `answer` anywhere; the backend accepts a `loop_fill` batch with the new outcomes. Update vocabulary pins if they cover panel strings.

Run `pytest tests/test_extension_panel*.py tests/test_autofill_router.py tests/browser -q` → PASS.

**Commit:** `feat(companion): panel runs the fill loop — Stop, grouped report, focus a field, value-free telemetry`

**Checkpoint (owner):** merge to local main; `docker compose up -d --build backend`; reload the extension and tab; try the Guidehouse Workday flow and a Greenhouse form in "Saved answers + AI". Note everything in "Could not operate" or "Needs your answer" that should have filled — each becomes a fixture + failing test before it is fixed.

---

## Task 9: "Answer low-stakes questions for me" on the Autofill profile card

**Files:**
- Modify: `frontend/components/settings/autofill-section.tsx` (beside the EEO consent switches, ~:815), `frontend/lib/types.ts` (`AutofillOptions { low_stakes: boolean }`)
- Test: `backend/tests/test_frontend_settings_cards.py` (source pins)

```tsx
const options = useQuery({
  queryKey: ["settings", "autofill-options"],
  queryFn: () => apiFetch<AutofillOptions>("/api/settings/autofill-options"),
});
const saveOptions = useMutation({
  mutationFn: (next: AutofillOptions) =>
    apiFetch<AutofillOptions>("/api/settings/autofill-options", { method: "PUT", body: JSON.stringify(next) }),
  onSuccess: (result) => qc.setQueryData(["settings", "autofill-options"], result),
  onError: (err) => couldnt("save that setting", err),
});
// …
<div className="flex items-start gap-3">
  <Switch id="low-stakes" checked={options.data?.low_stakes === true}
    disabled={!options.data || saveOptions.isPending}
    onCheckedChange={(next) => saveOptions.mutate({ low_stakes: next })} />
  <div>
    <Label htmlFor="low-stakes">Answer low-stakes questions for me</Label>
    <p className="text-sm text-muted-foreground">
      When your profile has no answer, Fill picks what a keen applicant would for questions like how you heard
      about the job or whether you&apos;re open to travel. It never guesses work authorization, EEO, education,
      experience, salary or anything you&apos;d be signing. These answers are listed for you to check.
    </p>
  </div>
</div>
```

Match the file's real helpers (`couldnt`, `useSingleFlight`, hint classes) as the EEO switches use them. Pins: the switch id, the label text, the endpoint string. Gates: `cd frontend && npx tsc --noEmit && npm run lint`; `pytest tests/test_frontend_settings_cards.py tests/test_frontend_vocabulary.py -q`.

**Commit:** `feat(settings): answer low-stakes questions for me`

---

## Task 10: Evaluate, cut over, document

**Step 1: End-to-end on real widget behaviour** — `backend/tests/browser/test_fill_end_to_end.py`. Build a page from the bodies of all fixtures; load `ENGINE_SOURCES + shared/choose.js, shared/guided-run.js, shared/fill-loop.js`; `broadcast` calls `ns.fillOps` directly (`fill_inventory` → `inventory`, `fill_step_state` → `stepState`, …) and returns `[{frameId: 0, result}]`; `api` is a scripted backend keyed by question text (`/map` from a table, `/pick` by exact text equality with the fact, `/step` choosing the candidate whose description names the fact, or `search:value` when there are no options). Assert: City/Postal Code committed with no `aria-invalid="true"` left; `#auth` "Yes"; `#heard` "LinkedIn" (via Job Board, adaptive step); School pill; skills pills `["SQL", "Python", "Tableau"]`; degree "Master's"; Field of study "Information Systems" (open → search → click); the days group `needs_answer`; no popup left open; the whole run under 30 s.

**Commit:** `test(companion): the fill engine end to end on real widget behaviour`

**Step 2: Meaning evaluation (owner's Jev key, labels/options only — no values leave except each case's fact)** — `backend/scripts/eval_fill_decisions.py`:
- **Mapping agreement (diagnostic, not ground truth):** distinct `(label, kind, rule_id)` rows from `autofill_field_observations` whose `rule_id` maps to one slot (a `RULE_TO_SLOT` table built from the `id`s in `extension/content/autofill.js`'s `RULES`) → `autofill_map.map_fields`; print agreement and every disagreement (`label | rule slot | Jev slot | p`).
- **Labelled picks:** `backend/scripts/fill_pick_cases.json` — ~40 hand-written cases `{question, options, slot, fact, expected}` covering sponsorship/authorization wordings, degree levels, fields of study with no exact option, how-heard categories, yes/no/decline variants. Run `/pick` logic per case; count **wrong writes** (picked ≠ expected and not abstained), abstentions and matches separately, per policy.

Run on the live stack:

```bash
docker compose cp backend/scripts/eval_fill_decisions.py backend:/app/scripts/
docker compose cp backend/scripts/fill_pick_cases.json backend:/app/scripts/
docker compose exec -T backend python scripts/eval_fill_decisions.py
```

**Gate:** show the owner both reports. Wrong writes on exact-policy cases must be zero; any others are reviewed with the owner. Tune `autofill_catalog._describe` wording, instructions, or floors — never add label rules back.

**Commit:** `chore(autofill): evaluate mapping and picks against history and labelled cases`

**Step 3: Cut over (after the owner's go-ahead).** Ask first: with the rules gone, "Saved answers only" has nothing to run (mapping is a model call on labels only) — remove the mode switch, or keep it as "no prose, no low-stakes"? Then:
- Panel: Fill always runs the loop (per the owner's choice).
- Delete `extension/content/autofill.js`, `open-questions.js`, `eeo.js`, `shared/profile-fields.js`; `runGuidedFill`/`collectFromPage` (move `shown` and `NO_FRAME_REACHED` into `fill-loop.js`); `routeOpenQuestions`/`buildRestFillObservations` from `shared/choose.js` (keep `requestChoose`); agent.js handlers `profile_fill`, `collect_open_questions`, `fill_answers`, `guided_write`, `scroll_to_field` and their `sw.js` allowlist entries; manifest entries; `rulePass` and rule-only parts of `shared/decisions.js`; the Jev half of `autofill_choose.py` (`/choose` becomes prose-only) and `autofill_slots.flatten`/`slot_criteria` if unused.
- Keep `shared/policy.js`, detection, posting identity, resume attach. Port `pause.js`'s `submitAnswer` to `fill_apply` (`op: "write"` for text shapes; for choice shapes show the jump instead).
- Tests: delete fake-DOM files that only exercise deleted code (at least `test_extension_already_filled, block_scope, combobox, commit_ladder, current_job, date_parts, eeo_autofill, eeo_live_shapes, eligibility, guided_collect, guided_fill, guided_write, listbox_button, missing_source, rule_abstention, split_date, token_input, work_auth`, and the control-shape half of `test_extension_fixture_corpus.py` with its six JSON fixtures). Before deleting each, list its scenarios and port every one whose behaviour still exists to `tests/browser` (policy-blocked never sent, EEO blocked without consent, consent forms, never submits, skills cap). Extend `test_extension_never_submits.py`'s scan to the new files. Trim `extension_harness.py` to what remaining tests use.
- Run `cd backend && /opt/anaconda3/bin/python3 -m pytest tests/ -q` → PASS.

**Commits:** `refactor(companion): the fill engine replaces the label-rule pass` (extension), then `test: retire rule-pass tests; port surviving scenarios to the browser suite`.

**Step 4: Documentation.** SYSTEM.md is at 994/1000 — groom before adding:
1. Move §7's "Guided fill" bullet body (~:586-623) into `extension/INTERNALS.md` § "How the fill behaves", rewritten for the engine (loop, shapes, generic path, adaptive step and its moves, routes, statuses, budgets, cancellation, verify rule, Workday typing, low-stakes).
2. §7: a ≤10-line **Fill engine** bullet — loop shape; `/map`, `/pick`, `/step`, `/choose` (prose); labels-only mapping; slot-owned policy; models choose only code-generated ids; verified-only reporting; budgets; human navigation/Submit; "`extension/INTERNALS.md` owns the rest".
3. §2 repo layout (`content/field-reader.js, fill-base.js, shapes.js, inventory.js, fill-core.js, fill-ops.js`, `shared/fill-loop.js`, `backend/tests/browser/`); §9 the browser suite (skip locally / fail in CI).
4. §12 (dated 2026-09-25, ≤3 lines each): **Workday text that shows but never saved** — setter + synthetic input leaves text Workday's state never took → type with `execCommand("insertText")`, and text + a field error is not filled. **Popups that ignore Escape** — Workday closes on an outside click. **A timed-out click can still land** — `Promise.race` does not cancel; primitives check a token.
5. §11: delete items this closes; add the deferred ones (debugger executor, vision).
6. §6 invariant + `.system_md_enforcement.json` pin: "a fill is reported only when verified" → `tests/browser/test_research_failures.py`.

Run `python3 scripts/check_system_md.py` → clean. **Commit:** `docs: the fill engine in SYSTEM.md §7 and INTERNALS.md`

**Step 5: Full gate and live check.**
1. `cd backend && ruff check . && /opt/anaconda3/bin/python3 -m pytest tests/ mcp_server/tests/ -q -rs --ignore=tests/ats/test_golden.py` → PASS, browser tests RUN (not skipped).
2. `cd frontend && npx tsc --noEmit && npm run lint`.
3. `python3 scripts/check_system_md.py`.
4. Owner live check: rebuild backend, reload extension and tab; one Workday application (every step) and one Greenhouse form; the owner signs in, confirms each "Save and Continue", and never presses Submit. Record per step: counts per report group, anything in "Could not operate", adaptive steps used, wall time. Anything wrong becomes a fixture + failing test before it is fixed.
