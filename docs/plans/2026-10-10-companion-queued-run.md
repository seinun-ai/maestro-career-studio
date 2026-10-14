# Companion Queued Run Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or
> superpowers:subagent-driven-development in the planning session) to implement this plan task by task.

**Goal:** The Companion takes the user's Queued jobs, fills them a few tabs at a time, clicks Next
through every page, and stops on each review page so the user only presses Submit.

**Architecture:** A host-agnostic runner (`extension/shared/queue-run.js`) hosted by the side panel
drives one run record per tab through open → sign in → fill → advance → … → ready to submit. Page
work (classify, advance, sign in) is new content-script operations behind the existing service-worker
fan-out and frame gate. The backend gains a Queued-run list, a Companion sign-in hand-off, a
Companion "submitted" recorder, an `apply_url` on jobs, and a three-level "Screening answers" dial
that replaces the low-stakes switch.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic (SQLite), pytest (+ xdist, Playwright Chromium, node
harness), Chrome MV3 extension (plain JS IIFEs on `window.careerStudioCompanion`), Next.js 16 / React 19.

**Design:** `docs/plans/2026-10-10-companion-queued-run-design.md` (approved 2026-10-10; Job step
buttons, park less and Part 8 added 2026-10-11). Read it first.

**Panel look:** direction C ("one next step"), per the design's "Panel look" decision. The panel
tasks (19, 20, 20a) render the run states into C's single Next card; ask the planner for the canvas
mockups before starting them.

Where this plan and the design differ, this plan says so under "Adjustments" and why.

## Phases (owner, 2026-10-11): slow down, one phase at a time

The owner re-cut this plan into three phases, each built, checked live and documented before the
next starts. Task numbers stay as written below (other docs cite them); this section decides WHEN
each runs. Each phase ends with its own slice of Task 22 (docs for what that phase shipped) and of
Task 23 (gate plus the owner's live check). Main must be merged in before Phase 1 starts.

**Done:** Task 1 (spike, 21245658) and Task 1a (engine fills hidden tabs, 06f00226).

**Re-checked against main 547bbf6e (2026-10-13).** The branch was fast-forwarded to local main (38
commits: base resume colours and their square in the Companion, the Jobs Where column, the fill log
off by default). File references, the migration head (now `abd275b457d8`), the fill-log gate and the
resume-square rule were brought up to date in the tasks below. Phase 1 is done (its own plan).

**Phase 1: the new panel look (direction C), no behavior change.** Today's four steps redrawn
as C's one-next-step card with the four-segment progress bar; same features. Its own plan:
`docs/plans/2026-10-11-companion-panel-c.md`. No task below belongs to Phase 1.

**Phase 2: one job at a time, moving through the pages by itself, in the current tab.**
- Answers: Tasks 2, 3, 4, 5 (Screening answers dial).
- Apply link and sign-in: Tasks 6, 7, 15, 16.
- Recording the user's submit: Task 9.
- Page reading and Next: Tasks 12, 13, 14.
- The driver, ONE record in the current tab: Task 17's `drive()` only (its `next()` scheduler and
  the record list wait for Phase 3).
- Per-tab job memory: Task 18. Try harder: Task 18a.
- The one-job panel states from Task 20: running card, Needs you with Resume, always-remembered
  answers with Undo, walls with Skip this job, Ready to submit, the 8 s auto-mark. (The Queue view,
  run list and run log are Phase 3.)
- Task 20a's **Apply** only (queue as the user's yes, then drive this tab). **Queue** is Phase 3.
- Learn from the fix and the known-gaps list: Tasks 10a, 20b.
- The fill agent (design Part 9, added 2026-10-13 after the owner's live Workday run): the
  recorded test form (24), never touch a robot trap (25), already there (26), leave empty
  optional fields alone (27), check every action in a list field (28), don't go round in
  circles (29), the agent's own search term (30), technique cards and what worked here (31),
  let the page settle (32).
- Remembering (added 2026-10-13): Task 20 saves every typed answer; 20c keeps an answer that names
  the job's company or city for that job only; Task 5 shows when more than 30 saved answers exist
  (only the first 30 are used until Task 33).
- Phase 2 order: 24 → 25 first (filling a robot trap can get an application flagged as a bot), then
  2 → 3 → 4 → 5 → 6 → 7 → 9 → 10a → 12 → 13 → 14 → 15 → 16 → 17 (drive) → 18 → 18a → 26 → 27 →
  28 → 29 → 30 → 31 → 32 → 20 (one-job parts) → 20a (Apply) → 20b → 20c → docs → gate and live check.
  The live check re-runs a Workday application like the 2026-10-13 one and compares its traces.
  Before it, tick **Keep a fill log** in the Companion's Options: since 6695ee40 the fill log and
  run traces are off by default and the service worker posts them only when
  `telemetryEnabled === true`.

**Phase 3: the queue and parallel applications.** Task 33 first (use every saved answer, not
the first 30: queued runs pile up saved answers fastest), then Tasks 8 (queue-run list), 10 (run log counts),
11 (Prepare queued jobs), 17's `next()` and record list, 19 (Queue view, run window, pacing), the
Queue-view and run-log parts of 20, 20a's **Queue** button, then (21) if Phase 2's live check asks
for it, docs, gate and live check.

---

## Goal Card

Goal: Turn the Companion into the user's applying agent. It takes the jobs the user queued, fills
them several tabs at a time, moves through every page by itself and stops on the review page, so the
user only presses Submit. It asks the user only when it must, in the tab it is working in, and
otherwise gives the safer answer. Lowering the friction the user hit with the external bot ("it keeps
stopping for small things") is part of the goal.

Principles:
- **Submit is never clicked, at any setting.** When unsure whether a button is Next or Submit, stop.
  This beats every friction concern.
- **Stop only for the protected list or a wall** (CAPTCHA, email code, account creation). Anything
  else is answered, marked, and shown on the review page. Don't add confirmation steps.
- **Never overwrite the user's custom tailoring** (an open tailoring session or a tailored draft).
- **Passwords never reach a model, a trace, a receipt or telemetry.**

Non-goals:
- Runs that survive closing the panel or Chrome, schedules, or a cloud runner.
- Per-ATS fill procedures. Filling stays the generic AI-first loop; only Next/Submit buttons get a
  per-ATS table.
- Board-native apply (LinkedIn Easy Apply, Indeed Apply).

Autonomy: **peer** (Sonnet 5.5 implements, Opus 5.5 reviews, planned by Opus 5.5). You may adapt
*how* when the repo disagrees with this plan; log each deviation in the task's commit message body
as `Deviation: <planned> → <did>, because <reason>`. Anything that changes scope, a cross-task
interface named here, or the Goal Card goes back to the planner as a short deviation note. Never
widen scope.

---

## Adjustments to the design (planner's, made while planning)

1. **Parked questions are answered in the page itself, not in a new panel input.** Loop mode has
   no pause rows today (its report rows only jump to the field). A parked tab is left with the
   field focused; the panel lists the page's open questions (jump links) and a **Resume** button.
   Resume re-reads the page, ALWAYS learns the typed answers through the existing `learnAnswer`
   (`panel/actions/pause.js`; owner 2026-10-11: no checkbox), says "Saved N answers to your
   profile · Undo", and continues the run.
   This is the user's original "need you in the application itself", and avoids building a second
   answer widget for every field shape.
2. **The confirmation is recorded with consent channel `companion`,** not `frontend`, so the audit
   trail says the Companion observed it after the user's own Submit. `CONSENT_CHANNELS` gains it.
3. **Auto-mark's undo is a delay, not a reversal.** `submitted` is terminal in the proposal state
   machine, so the row shows "Marking applied in 8 s · Undo" and posts only after 8 s.
4. **Missing profile facts on the Queue view link to Settings › Profile** in the web app instead
   of an inline editor. They're still asked once and saved there.
5. **Dial migration:** the low-stakes switch stores no row when off, so "explicitly off" and "never
   touched" can't be told apart. Every install without a new dial row reads the default, **Backed by
   your history**. That turns on low-stakes answers for installs that had them off. Call it out in
   the CHANGELOG.
6. **Unclear buttons stop the run in v1** (treated as review). The model-picked `/api/autofill/page`
   is Task 21, behind the live check: build it only if the live check shows unclear buttons are a
   real source of stops.
7. **Technique cards are widget craft, not per-ATS procedures** (added 2026-10-13). The Goal Card's
   non-goal "Per-ATS fill procedures" stands: Task 31's cards are keyed by widget kind (search box,
   multi-pick list, dropdown, group, select, date), never by site. What worked on a given site
   stays in the recipe book, which already learns it from evidence.

---

## Conventions for every task

- Run Python from `backend/` with the backend venv. Backend suite: `pytest tests/ mcp_server/tests/
  -q -n auto --dist loadfile`. Extension tests alone: `pytest tests/test_extension_*.py tests/browser
  -q -rs -n auto --dist loadfile`. Browser tests need `python -m playwright install chromium`.
- Extension tests are Python in `backend/tests/`: node harness (`tests/extension_harness.py`
  `run_node`), panel harness (`tests/extension_panel_harness.py`), Playwright (`tests/browser/`).
  No JS test files exist in `extension/`.
- New content script → update `extension/manifest.json`,
  `tests/test_extension_manifest.py::test_the_content_script_is_the_split_modules_in_dependency_order`,
  `tests/extension_harness.py` (`PAGE_RUNTIME_SOURCES` or `FILL_ENGINE_SOURCES`, manifest order),
  and `tests/browser/conftest.py::ENGINE_SOURCES` if the engine needs it.
- New panel script → `extension/panel/panel.html` `<script>` tag (order rules in
  `tests/test_extension_panel.py::test_the_panel_document_is_self_contained_and_joins_the_namespace`;
  `fill-loop.js` must stay right after `guided-run.js`), plus the `actions.js` roster for an action
  file. A new `shared/` caller file → add to `tests/test_extension_page_messaging.py`'s file list.
- New page message type → `extension/sw.js` `BROADCASTABLE` (pinned exactly by
  `tests/test_extension_sw_router.py::test_the_broadcast_allow_list_is_pinned_and_not_the_harmless_ones`),
  and a handler in `content/agent.js` `PAGE_HANDLERS`.
- New `card` field → declare it in `panel.js`'s `card` literal, or `actionStore().write` throws.
- Public repo: test data uses made-up employers (Acme, Globex) and generic questions only.
- Commit after each task with a conventional message ending in
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (or the executing model's name).
- Don't touch SYSTEM.md until Task 22. It is at its line cap.

---

## Phase 0 — Measure first

### Task 1: Background-tab throttling spike

The default of 3 parallel tabs, and whether run tabs must take turns in the foreground, depends on
how much Chrome slows a fill in a background tab. This task writes a measurement script, runs it,
and records the numbers. It ships no product code.

**Files:**
- Create: `backend/scripts/spike_background_fill.py`
- Modify: `docs/plans/2026-10-10-companion-queued-run.md` (append a "Spike result" section at the end)

**Step 1: Write the script.** Headed Playwright Chromium (`headless=False`; headless does not
throttle like Chrome). Three pages in ONE browser context/window, loaded with
`tests/fixtures/browser/workday_text.html`, `workday_listbox.html` and `workday_date.html` and the
engine sources (`tests/browser/conftest.py::ENGINE_SOURCES`, injected with `add_script_tag` as the
`load` fixture does). For each page, time a sequence of `window.careerStudioCompanion.fillOps`
calls that mirror the existing browser tests: `inventory`, then `apply` with `op:"write"` on each
text field and `op:"pick"` on the listbox (copy the call shapes from `tests/browser/pages.py`
`inv`/`apply`). Measure three cases and print a table (median of 5 runs, ms):
1. the page in front (`page.bring_to_front()` before timing);
2. the page behind another page in the same window, timed immediately;
3. the same, after the page has sat in the background for 6 minutes (Chrome's intensive throttling
   starts after about 5). Use `time.sleep(370)` between bring-to-front of another page and timing.

```python
"""Spike: how much slower is a Companion fill in a background tab?

Run from backend/: python -m scripts.spike_background_fill
Needs a display (headed Chromium). Prints medians in ms; ships nothing.
"""
import statistics
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
EXT = ROOT / "extension"
FIX = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "browser"
SOURCES = ["shared/policy.js", "content/field-reader.js", "content/fill-base.js", "content/shapes.js",
           "content/recipes.js", "content/inventory.js", "content/fill-core.js", "content/fill-ops.js",
           "content/sections.js"]
FILL_JS = """async () => {
  const ops = window.careerStudioCompanion.fillOps;
  const t0 = performance.now();
  const inv = await ops.inventory({consentForms: false, runId: 'spike'});
  for (const f of inv.fields) {
    if (f.shape === 'text') await ops.apply([{fid: f.fid, op: 'write', value: 'Springfield'}]);
  }
  return performance.now() - t0;
}"""
# Adjust FILL_JS to the real inventory/apply signatures in tests/browser/pages.py before running.


def load(page, name):
    page.set_content((FIX / name).read_text(encoding="utf-8"))
    for src in SOURCES:
        page.add_script_tag(content=(EXT / src).read_text(encoding="utf-8"))


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        pages = [ctx.new_page() for _ in range(3)]
        rows = []
        for case, settle in (("front", None), ("background", 0), ("background 6 min", 370)):
            times = []
            for _ in range(5):
                for i, name in enumerate(["workday_text.html", "workday_listbox.html", "workday_date.html"]):
                    load(pages[i], name)
                target = pages[0]
                if case == "front":
                    target.bring_to_front()
                else:
                    pages[1].bring_to_front()
                    if settle:
                        time.sleep(settle)
                times.append(target.evaluate(FILL_JS))
            rows.append((case, statistics.median(times)))
        for case, ms in rows:
            print(f"{case:20s} {ms:8.0f} ms")
        browser.close()


if __name__ == "__main__":
    main()
```

**Step 2: Run it** from `backend/`: `python -m scripts.spike_background_fill` (about 35 minutes
because of the 6-minute case; run it with `run_in_background`). Expected: three rows of medians.

**Step 3: Record the decision** in a "Spike result" section at the end of this plan, using this
rule:
- background ≤ 1.5× front, even after 6 min → **default 3 parallel tabs, all in the background**;
- otherwise → **take turns**: the runner keeps the run window's ACTIVE tab on the tab currently
  filling (`chrome.tabs.update(tabId, {active: true})` inside the run window only; the user's own
  window is never touched). Parallel then means "others wait or idle while one fills", and the
  default becomes 1 filling + up to 10 waiting at Ready to submit.
Task 19 reads this section.

**Step 4: Commit** `chore(spike): measure Companion fill time in background tabs`.

### Task 1a: The fill engine works in hidden tabs

Owner decision (B), 2026-10-11, after the spike. Today a background (hidden, or covered-window) tab
runs text and date fills about 6.5× slower and fails every dropdown ("could not explore Degree").
The engine already bounds its animation-frame waits with a timer (`content/fill-core.js` `frame()`,
`content/fill-ops.js` inventory peek), so diagnose before fixing.

**Files:** `extension/content/fill-core.js`, `extension/content/fill-ops.js`, `extension/content/fill-base.js`
(whichever the diagnosis names); `backend/scripts/spike_background_fill.py` (harness fix);
`backend/tests/browser/` (new tests).

**Step 1: Diagnose.** Run the spike with an extra in-page trace (a debug flag in the driver, not
shipped behavior) that logs each fill-core/fill-ops wait in the listbox fill: which wait, asked ms,
actual ms. Name the wait(s) that blow a budget or never resolve in a hidden tab: a throttled
`setTimeout` (≥1 s per wait while hidden, about 1/min for chained timers after 5 min), the fixture
app's own rendering, or a budget (`ITEM_MS`, `FIELD_MS`) exceeded by stretched waits. Record the
finding in the commit body.

**Step 2: Failing tests.** In `tests/browser/`, a test page that simulates a hidden tab:
`add_init_script` sets `document.hidden = true`, `visibilityState = "hidden"`, makes
`requestAnimationFrame` never fire, and wraps `setTimeout` so any delay is at least 1000 ms (the
hidden-tab clamp). On `workday_listbox.html` the listbox `choose` must commit (oracle), and text and
date writes must commit, each within its field budget. Expected now: the listbox test FAILS.

**Step 3: Implement** the smallest engine change that passes, for example a wait helper in
`fill-base.js` that, while `document.hidden`, waits on wall-clock time through `MessageChannel`
messages (not throttled like timers) instead of `setTimeout`, and is used by the waits Step 1
named. Keep visible-tab behavior byte-for-byte: every existing browser test must pass unchanged.

**Step 4: Harness fix.** Make the spike's 6-minute case reliable (a lone fixture tab must stay
behind the holder tab: re-activate the holder after the last `/json/new`, and verify before the
scheduled start). Then run the full spike (about 35 min) and append the new table under "Spike
result" as "After Task 1a".

**Acceptance:** background (immediate AND after 6 min) shows 5/5 on all three fixtures, with
medians within 2× of the front tab. If the 6-minute case can't get within 2×, record the numbers and
stop for the planner: parallel stays at 1.

**Step 5: Commit** `fix(fill): the engine fills hidden tabs (queued-run parallel runs)`.

---

## Phase 1 — Backend

### Task 2: The "Screening answers" level (storage + settings API)

**Files:**
- Modify: `backend/app/services/model_settings.py` (after `AUTOFILL_LOW_STAKES_KEY`, line 273)
- Modify: `backend/app/routers/settings.py:77-81` (`AutofillOptions`) and `:625-634` (routes)
- Test: `backend/tests/test_settings_autofill_options.py` (rewrite its three tests)

**Step 1: Write the failing tests** (replace the file's tests):

```python
from app.services import model_settings


def test_the_answer_level_defaults_to_backed_by_history(db_session):
    assert model_settings.get_answer_level(db_session) == "history"
    assert model_settings.get_autofill_low_stakes(db_session) is True


def test_each_level_round_trips_and_facts_only_turns_low_stakes_off(db_session):
    for level in ("facts", "history", "queued"):
        model_settings.set_answer_level(db_session, level)
        assert model_settings.get_answer_level(db_session) == level
    model_settings.set_answer_level(db_session, "facts")
    assert model_settings.get_autofill_low_stakes(db_session) is False


def test_the_options_endpoint_reads_and_writes_the_level(client):
    assert client.get("/api/settings/autofill-options").json() == {"answer_level": "history"}
    response = client.put("/api/settings/autofill-options", json={"answer_level": "queued"})
    assert response.status_code == 200 and response.json() == {"answer_level": "queued"}


def test_the_options_endpoint_refuses_an_unknown_level_or_the_old_key(client):
    assert client.put("/api/settings/autofill-options", json={"answer_level": "yolo"}).status_code == 422
    assert client.put("/api/settings/autofill-options", json={"low_stakes": True}).status_code == 422
```

**Step 2: Run** `pytest tests/test_settings_autofill_options.py -v`. Expected: FAIL
(`get_answer_level` is not defined).

**Step 3: Implement.** In `model_settings.py`:

```python
ANSWER_LEVEL_KEY = "autofill.answer_level"
AnswerLevel = Literal["facts", "history", "queued"]
ANSWER_LEVELS: tuple[str, ...] = ("facts", "history", "queued")
DEFAULT_ANSWER_LEVEL: AnswerLevel = "history"


def get_answer_level(session: Session | None = None) -> AnswerLevel:
    """How far a fill answers without asking (docs/plans/2026-10-10-companion-queued-run-design.md
    Part 3). Read by the server on every /map, /pick and /step; never taken from the client.
    facts: saved answers and career history only. history (default): plus the low-stakes kinds
    and history-backed "N years of a skill" Yes. queued: plus every requirement question on a
    job the user queued. The protected list sits outside every level."""
    value = _read(session, ANSWER_LEVEL_KEY)
    return value if value in ANSWER_LEVELS else DEFAULT_ANSWER_LEVEL


def set_answer_level(session: Session, level: AnswerLevel) -> None:
    if level not in ANSWER_LEVELS:
        raise ValueError(f"unknown answer level {level!r}")
    _set_raw_value(session, ANSWER_LEVEL_KEY, level)
    # The old switch is derived from the level now; drop its row so nothing reads a stale one.
    _set_raw_value(session, AUTOFILL_LOW_STAKES_KEY, None)
```

Then make the old reader derived, so `/map`, `autofill_pick.pick` and `autofill_step.step` keep
working unchanged:

```python
def get_autofill_low_stakes(session: Session | None = None) -> bool:
    """Low-stakes answers are on at every level but "facts" (derived from the answer level)."""
    return get_answer_level(session) != "facts"
```

Delete `set_autofill_low_stakes`, then grep for its callers and move them to `set_answer_level`
(`set_answer_level(db, "history" if on else "facts")`). In `routers/settings.py`:

```python
class AutofillOptions(BaseModel):
    """GET/PUT /api/settings/autofill-options — how far a fill answers without asking."""
    model_config = ConfigDict(extra="forbid")
    answer_level: Literal["facts", "history", "queued"]
```

GET returns `AutofillOptions(answer_level=model_settings.get_answer_level(db))`; PUT calls
`set_answer_level(db, payload.answer_level)` and returns the GET.

**Step 4: Run** the new tests, then `pytest tests/test_autofill_map.py tests/test_autofill_pick.py
tests/test_autofill_step.py tests/test_autofill_fill_router.py -q`. Fix any test that seeded the
switch through `set_autofill_low_stakes(db, True)` by seeding `set_answer_level(db, "history")`, and
`False` by `"facts"`. Tests that relied on "off by default" now need an explicit `"facts"` seed.
Expected: PASS.

**Step 5: Commit** `feat(settings): a three-level Screening answers setting replaces the low-stakes switch`.

### Task 3: The answer level reaches the map, the reasoned pass and pick

Level 2 adds "N years of a skill: Yes when the history shows the skill and does not contradict the
years". Level 3 adds "every requirement or experience question on a Queued job: Yes". Neither ever
covers the protected list: work authorization, sponsorship, age/eligibility, EEO, background or
criminal history, clearance, salary, legal attestation or signature.

**Files:**
- Modify: `backend/app/services/autofill_map.py` (`map_fields`, `low_stakes_scope`,
  `_NEVER_LOW_STAKES_TEMPLATE`, `_LOW_STAKES_TEMPLATE`)
- Modify: `backend/app/services/autofill_reasoned.py` (`reason`, its prompt)
- Modify: `backend/app/routers/autofill.py` (`post_map` ~403, `_facts` ~345: compute `queued`)
- Modify: `backend/app/services/autofill_pick.py` (`_LOW_STAKES_PARAGRAPH` :65, formatted at :279-280; pass the level through where `keen` is used)
- Test: `backend/tests/test_autofill_map.py`, `backend/tests/test_autofill_reasoned.py` (create it if
  absent), `backend/tests/test_autofill_fill_router.py`

**Step 1: Write failing tests.** Use the existing `run(fields, db_session, *, eeo_consented=True,
low_stakes=False)` helper in `test_autofill_map.py:69`. Extend it with
`level: str = "facts"` and `queued: bool = False`, mapping `low_stakes = level != "facts"`. Mirror
how neighbouring tests stub the engines (look at
`test_low_stakes_is_asked_only_when_on_and_only_for_fields_no_fact_answers` at line 146 for the
fake-engine pattern).

```python
def test_years_with_a_skill_stays_on_the_never_list_below_the_queued_level(db_session):
    scope, never = autofill_map.low_stakes_scope({}, level="history", queued=True)
    assert "number of years of experience" in never


def test_the_queued_level_moves_requirement_questions_into_scope_only_for_a_queued_job(db_session):
    scope, never = autofill_map.low_stakes_scope({}, level="queued", queued=True)
    assert "number of years of experience" not in never
    assert "requirement" in scope and "years" in scope
    assert "work authorization" in never and "sponsorship" in never and "salary" in never
    _, never_not_queued = autofill_map.low_stakes_scope({}, level="queued", queued=False)
    assert "number of years of experience" in never_not_queued


def test_the_protected_list_survives_every_level():
    for level in ("facts", "history", "queued"):
        _, never = autofill_map.low_stakes_scope({}, level=level, queued=True)
        for protected in ("work authorization", "sponsorship", "EEO", "criminal history",
                          "security clearance", "salary", "legal attestation"):
            assert protected in never, (level, protected)
```

In `test_autofill_reasoned.py`, pin the level-2 rule in the reasoning prompt the way existing
reasoned tests pin wording (find them with `grep -rn "autofill_reasoned" backend/tests`):

```python
def test_history_level_lets_a_years_question_be_yes_when_the_history_shows_the_skill(monkeypatch, db_session):
    prompt = autofill_reasoned.prompt_rules(level="history")
    assert "shows the skill" in prompt and "does not contradict" in prompt


def test_facts_level_keeps_years_questions_to_computed_years_only(db_session):
    prompt = autofill_reasoned.prompt_rules(level="facts")
    assert "shows the skill" not in prompt
```

In `test_autofill_fill_router.py`, a request on an application whose job has an `accepted` proposal
reaches `map_fields` with `queued=True` (monkeypatch `autofill_map.map_fields` to capture kwargs).
Without a proposal, `queued=False`.

**Step 2: Run** them. Expected: FAIL.

**Step 3: Implement.**
- `low_stakes_scope(facts, *, level="history", queued=False)`. When `level == "queued" and queued`:
  remove the clause `a number of years of experience with a specific skill or tool, such as …` from
  the never-list, and append to the scope: `"; any requirement, qualification or experience
  self-assessment for this job, including years with a named skill or tool (answered Yes)"`. Keep
  the module-level `_LOW_STAKES, _NEVER_LOW_STAKES = low_stakes_scope({})` defaults (level "history").
- `map_fields(..., low_stakes: bool, level: str = "history", queued: bool = False)` passes both
  through to `_low_stakes` → `low_stakes_scope`.
- `autofill_reasoned`: add `prompt_rules(level: str) -> str` returning today's rules, plus, when
  `level in ("history", "queued")`, the sentence: `"A yes/no question asking for at least N years
  with a skill or tool: answer Yes when the work history shows that skill and nothing in it
  contradicts N years (for example the total years of work cover N); answer none when the history
  clearly shows fewer years."` `reason(...)` takes `level` and builds its prompt with `prompt_rules`.
- `routers/autofill.py`: a helper `_queued(db, application_id) -> bool` is True when the
  application's job has an `ApplicationProposal` with status `accepted` or `approved`.
  `post_map` passes `level=model_settings.get_answer_level(db), queued=_queued(db, payload.application_id)`.
  Pass `level` into the reasoned pass the same way at its call site (`autofill_pick.py:389`).
- `autofill_pick.py` `_LOW_STAKES_PARAGRAPH` (:65, formatted at :279-280): the low-stakes paragraph uses the same `low_stakes_scope(facts, level=,
  queued=)` so /pick and /map state the same scope.

**Step 4: Run** `pytest tests/test_autofill_map.py tests/test_autofill_pick.py
tests/test_autofill_reasoned.py tests/test_autofill_fill_router.py tests/test_autofill_step.py -q`.
Expected: PASS.

**Step 5: Commit** `feat(autofill): the answer level widens low-stakes and reasoned answers; the protected list never moves`.

**Batch-2 review amendments (2026-10-13, owner decision on years):** clearance and organization-kind
questions keep their own sentinel and never reach the low-stakes judge; only a `YEARS_UNANSWERED`
sentinel widens at level 3. At level 3 a years question asks the reasoned pass first: enough → Yes;
the history clearly shows fewer → asked; the history is silent → the low-stakes Yes. `_queued` also
requires the request's `page_host` to match the job's apply_url or source_url host. /step states
the same level as /map and /pick. The eval harness patches `get_answer_level`.

### Task 4: The Job Search Brief carries the answer level

**Files:**
- Modify: `backend/app/services/job_search_brief.py` (`build_brief`, line 101; `_auto_apply_block` at 85)
- Modify: `backend/app/schemas/job_search_brief.py` (`JobSearchBriefResponse`, ~line 72)
- Modify: `backend/mcp_server/server.py:439-441` (`get_job_search_brief` docstring: mention `applying.answer_level`)
- Test: `backend/tests/test_job_search_brief.py`

**Step 1: Failing test:**

```python
def test_the_brief_carries_the_answer_level(client, db_session):
    model_settings.set_answer_level(db_session, "queued")
    assert client.get("/api/jobs/search-brief").json()["applying"] == {"answer_level": "queued"}
```

**Step 2: Run.** Expected: FAIL (KeyError).

**Step 3: Implement** `_applying_block(db) -> {"answer_level": model_settings.get_answer_level(db)}`.
Add `"applying": _applying_block(db)` next to `"auto_apply"`, and a schema
`BriefApplying(answer_level: Literal["facts","history","queued"])` with `applying: BriefApplying` on the
response. Keep the MCP docstring under the truncation ratchet
(`test_registered_tool_docstrings_fit_client_truncation_budget`): one short clause.

**Step 4: Run** `pytest tests/test_job_search_brief.py mcp_server/tests -q`. Expected: PASS.

**Step 5: Commit** `feat(brief): agents read the Screening answers level`.

### Task 5: The Settings dial replaces the switch

**Files:**
- Modify: `frontend/components/settings/autofill-section.tsx:1264` and `:1276-1345` (`LowStakesSwitch`)
- Modify: `frontend/lib/types.ts:336-338` (`AutofillOptions`)
- Test: `backend/tests/test_frontend_settings_cards.py`, `backend/tests/test_frontend_settings_assistant_words.py`

**Step 1: Update the wording tests first.**
`test_frontend_settings_assistant_words.py::test_the_consent_words_keep_every_promise` and
`::test_the_consent_switches_keep_their_promises` pin "It never moves to the next page and never
submits." / "It never moves to the next page or submits." Change both pins to the new promise,
which is exact text in the component:
`"It never submits. Only during a run of your queued jobs does it move to the next page."`
Add a pin in `test_frontend_settings_cards.py` that the card renders the three level labels
`Facts only`, `Backed by your history`, `Queued means I qualify`, and that `low_stakes` no longer
appears in `autofill-section.tsx`.

**Step 2: Run** `pytest tests/test_frontend_settings_cards.py tests/test_frontend_settings_assistant_words.py -q`.
Expected: FAIL.

**Step 3: Implement.** `AutofillOptions` becomes `{ answer_level: "facts" | "history" | "queued" }`.
Rename `LowStakesSwitch` to `ScreeningAnswers`: the same query/mutation, a radio group (the repo's
Base UI `RadioGroup`; copy the pattern from another settings radio group, `grep -rn RadioGroup
frontend/components/settings`). Label "Screening answers", one short line under each option:
- **Facts only**: "Only your saved answers and career history. Anything else waits for you."
- **Backed by your history** (default): "Also answers low-stakes questions in the job's favor, and
  years-with-a-skill questions when your history shows the skill."
- **Queued means I qualify**: "On jobs you queued, also says yes to every requirement question."
Under the group, one line: "Work authorization, sponsorship, salary, EEO, background, clearance and
legal statements always wait for a saved answer." Toast: `Screening answers: <label>`. Don't
give the dial's mutation a TanStack `scope` (a scoped mutation stalls in a hidden tab; SYSTEM.md
§12); use `lib/in-order.ts` if saves must be ordered. Keep the
copy rules (`docs/frontend-conventions.md`; ratchets `test_frontend_vocabulary.py`,
`test_frontend_sentence_length.py`). Replace the old promise sentence with the new one from Step 1.

**Saved answers in use (added 2026-10-13).** In the same file's "Your own questions" fieldset,
under its description: when `custom.length > 30`, one line, "Only the first 30 are used when
filling for now. Remove the ones you no longer need." (`autofill_catalog.MAX_CUSTOM`; Task 33
removes the line once every saved answer can be used). Pin it in `test_frontend_settings_cards.py`
(shown for 31 rows, absent for 30).

**Step 4: Run** the two test files plus `test_frontend_vocabulary.py test_frontend_sentence_length.py`,
then `cd frontend && npx tsc --noEmit && npm run lint`. Expected: PASS.

**Step 5: Commit** `feat(settings): Screening answers dial`.

### Task 6: Jobs remember the employer's apply link

**Files:**
- Create: `backend/migrations/versions/<12-hex>_jobs_apply_url.py` (generate the id with
  `python -c "import uuid; print(uuid.uuid4().hex[:12])"`; `down_revision = "abd275b457d8"`
  (base_resume_color_hue), the head at 547bbf6e; confirm with `alembic heads` first)
- Modify: `backend/app/models/job.py` (beside `source_url`, line 24)
- Modify: `backend/app/schemas/job.py` (`JobCreate`, `JobIngest`, `JobSummary`)
- Modify: `backend/app/routers/jobs.py` (`create_job` ~300, `_persist_job` ~252)
- No sync change: the sync serializers are column-generic. Add an `apply_url` round-trip case to
  `backend/tests/sync/test_jobs_bundle.py` (as 547bbf6e did for `color_hue` in
  `test_profile_bundle.py`)
- Test: `backend/tests/test_jobs_apply_url.py` (new)

**Step 1: Failing tests:**

```python
def test_saving_a_job_keeps_the_employer_apply_link(client, monkeypatch):
    _stub_extraction(monkeypatch)  # copy the jd_extraction stub used by tests/test_jobs_router.py
    body = {"raw_text": "Title: Data Engineer\nCompany: Acme", "source_url": "https://board.example/jobs/1",
            "apply_url": "https://acme.example/careers/apply/1"}
    job = client.post("/api/jobs", json=body).json()
    assert job["apply_url"] == "https://acme.example/careers/apply/1"


def test_an_apply_link_must_be_http(client, monkeypatch):
    _stub_extraction(monkeypatch)
    body = {"raw_text": "x", "apply_url": "javascript:alert(1)"}
    assert client.post("/api/jobs", json=body).status_code == 422


def test_a_saved_again_job_gains_an_apply_link_it_lacked(client, monkeypatch):
    ...  # second POST with the same text and an apply_url fills a NULL apply_url; never overwrites one
```

**Step 2: Run.** Expected: FAIL.

**Step 3: Implement.** Column `apply_url: Mapped[str | None] = mapped_column(Text)`. The migration
uses `op.batch_alter_table("jobs")` → `add_column(sa.Column("apply_url", sa.Text(), nullable=True))`
(style: `559244b575bc_base_resume_anchors.py`). Schemas: `apply_url: HttpUrlStr | None = None` with a
validator that accepts only `http(s)://` and caps at 2048 characters. Add it to `JobCreate`,
`JobIngest` and `JobSummary`. `_persist_job` writes it on create; on dedup it fills only a NULL.

**Step 4: Run** the new tests, `pytest tests/test_jobs_router.py tests/sync -q`, and
`alembic upgrade head` against a scratch SQLite file. Expected: PASS.

**Step 5: Commit** `feat(jobs): remember the employer's apply link`.

### Task 7: Companion sign-in hand-off

**Files:**
- Create: `backend/app/companion_origin.py`
- Modify: `backend/app/services/proposals.py:71-87` (`share_job_site_login` gains a `channel` argument)
- Create: `backend/app/routers/companion.py` (prefix `/api/companion`); mount it in `backend/app/main.py`
- Test: `backend/tests/test_companion_job_site_login.py` (new)

**Step 1: Failing tests.** Seed full automation, a job-site login file (`monkeypatch.setattr(settings,
"settings_dir", tmp_path)` then `job_site_login.write(...)`, as `tests/test_job_site_login_handoff.py`
does), and an `accepted` proposal.

```python
EXT = {"Origin": "chrome-extension://pjmfonfapjdabkoicnelpflpjojdjgan"}


def test_the_companion_gets_the_login_for_a_queued_job_and_it_is_audited(client, queued):
    r = client.post("/api/companion/job-site-login", json={"proposal_id": str(queued.id)}, headers=EXT)
    assert r.status_code == 200 and set(r.json()) == {"email", "password"}
    event = latest_consent_event(queued.id)
    assert (event.action, event.channel) == ("login_shared", "companion")
    assert "password" not in (event.note or "")


def test_no_extension_origin_means_no_login(client, queued):
    for headers in ({}, {"Origin": "http://localhost:3000"}, {"Origin": "chrome-extension://someoneelse"}):
        r = client.post("/api/companion/job-site-login", json={"proposal_id": str(queued.id)}, headers=headers)
        assert r.status_code == 403


def test_the_same_gates_as_the_agent_hand_off(client, queued, db_session):
    ...  # full automation off → 409; company blocked → 409; proposal pending_review → 409; no login saved → 404
```

The test client's Host must pass `TrustedHostMiddleware` (`conftest` adds `testserver`), and the
origin guard refuses unlisted origins before routing, which is what the `someoneelse` case checks.

**Step 2: Run.** Expected: FAIL (404 route).

**Step 3: Implement.**

```python
# backend/app/companion_origin.py
"""Is this request from the configured Companion? An exact chrome-extension:// origin, never a
pattern (SYSTEM.md inv-browser-boundary item 3)."""
from fastapi import Request

from app.config import settings


def is_companion(request: Request) -> bool:
    origin = request.headers.get("origin", "")
    return origin in {f"chrome-extension://{ext_id}" for ext_id in settings.maestro_cs_extension_ids}
```

`share_job_site_login(session, prop, agent, *, channel="mcp")` writes `ConsentEvent(...,
channel=channel, note=agent)`. The new router:

```python
router = APIRouter(prefix="/api/companion", tags=["companion"])


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposal_id: UUID


@router.post("/job-site-login")
def companion_job_site_login(payload: LoginRequest, request: Request, db: ...):
    """The saved job-site login for a Queued job, for the Companion's sign-in step only.
    Never reaches a model: the Companion types it into the job's own sign-in page."""
    if not is_companion(request):
        raise HTTPException(403, detail="Only the Companion can ask for the job-site login here.")
    prop = db.get(ApplicationProposal, payload.proposal_id)
    if prop is None:
        raise HTTPException(404, detail="Proposal not found")
    try:
        return proposals.share_job_site_login(db, prop, "companion", channel="companion")
    except proposals.TransitionError as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
```

Clean the 422 the same way `routers/settings.py:242-254` (`_JobSiteLoginRoute`) does. The body never carries the password,
but keep it uniform.

**Step 4: Run** the new test plus `tests/test_job_site_login_handoff.py tests/test_security_boundaries.py -q`.
Expected: PASS.

**Step 5: Commit** `feat(companion): the saved job-site login for the Companion's sign-in step`.

### Task 8: `GET /api/autofill/queue-run`

One read that returns what a run needs, with every server-side gate already applied.

**Files:**
- Create: `backend/app/services/queue_run.py`
- Modify: `backend/app/routers/autofill.py` (new route)
- Modify: `backend/app/schemas/autofill_fill.py` (response models)
- Test: `backend/tests/test_queue_run.py` (new)

**Response shape:**

```python
class QueueRunItem(BaseModel):
    proposal_id: UUID
    job_id: UUID
    company: str | None
    title: str | None
    open_url: str | None              # apply_url, else source_url; None → the item is skipped
    application_id: UUID | None
    base_resume: str | None           # the application's base, else the best-scored base for the job
    pdf_ready: bool                   # Application.pdf_path is set
    has_draft: bool                   # application.customized_json is not None
    tailoring_open: bool              # an open TailoringSession for (job, base_resume)
    knockout: Literal["conflict", "incomplete_profile", "clear", "unstated"]
    knockout_kinds: list[str]         # kinds of the conflicting / incomplete checks
    board_native: bool                # open_url host is linkedin.com / indeed.com AND apply_url is None


class QueueRunResponse(BaseModel):
    items: list[QueueRunItem]
    cap_left: int
    skipped: list[dict]               # [{proposal_id, why}] why ∈ blocked | applied | no_link | cap | not_here
```

**Step 1: Failing tests** (seed with `tests/test_proposals_models.py::_mk_job` plus proposals):
- 409 with `detail` naming full automation when the switch is off;
- only `accepted` proposals appear, oldest first;
- a blocked company, an already-applied application (`Application.status == "applied"`) and a job
  with no url each land in `skipped` with their `why`;
- with sync on, a job this install doesn't own (offered to or held by another writer,
  `offers.mark_when_queued`, `{#inv-one-writer-ownership}`; the PATCH route already calls
  `hooks.require_owned`) lands in `skipped` with `why == "not_here"`;
- with `max_submissions_per_day=2` and one reservation in the last 24 h (`cap_status`), only 1 item is
  returned and the rest are `skipped` with `why == "cap"`;
- `open_url` prefers `apply_url`;
- `base_resume` comes from the application, else the highest-composite base `AtsScore` for the job
  (find the base-score query used by `services/ats_score.py`; reuse it rather than writing SQL), else None;
- `tailoring_open`, `has_draft` and `pdf_ready` reflect the seeded rows;
- `knockout` uses `knockout.scan_for(db, job)` (read once per job; `scan_args` once per request).

**Step 2: Run.** Expected: FAIL.

**Step 3: Implement** `queue_run.build(session) -> QueueRunResponse`. Reuse:
`auto_apply_settings.get_settings`, `proposals._company_is_blocked` (rename it to public
`company_is_blocked` and update its callers), `proposals.cap_status`, `proposals.expire_stale`
(call it first, as `list_proposals` does), and `knockout.scan_args` / `scan_job`. The route is
`@router.get("/queue-run", response_model=QueueRunResponse)`, and a `TransitionError`-like guard →
409 when full automation is off.

**Step 4: Run** `pytest tests/test_queue_run.py -q`. Expected: PASS.

**Step 5: Commit** `feat(autofill): the Queued-run list with every gate applied`.

### Task 9: `POST /api/proposals/{id}/companion-submitted`

**Files:**
- Modify: `backend/app/services/proposals.py` (`CONSENT_CHANNELS` gains `"companion"`; new
  `record_companion_submit`)
- Modify: `backend/app/routers/proposals.py`
- Test: `backend/tests/test_companion_submitted.py` (new)

**Step 1: Failing tests:**

```python
def test_a_confirmation_after_the_users_submit_records_the_job_applied(client, queued):
    body = {"confirmation": {"host": "acme.example", "path": "/apply/done", "text": "Thank you for applying"}}
    r = client.post(f"/api/proposals/{queued.id}/companion-submitted", json=body, headers=EXT)
    assert r.status_code == 200 and r.json()["status"] == "submitted"
    # application flips to applied; two ConsentEvents (approved, submitted) with channel companion;
    # evidence holds a final_review row and a submission_receipt row; cap reserved once


def test_only_the_companion_may_record_it(client, queued):
    assert client.post(..., headers={}).status_code == 403


def test_it_respects_the_cap_and_the_skip_list(client, queued, db_session):
    ...  # cap used → 409; company blocked after queueing → 409 (the approve step re-checks it)


def test_the_confirmation_text_is_bounded(client, queued):
    ...  # text > 300 chars → 422; host/path required
```

**Step 2: Run.** Expected: FAIL.

**Step 3: Implement** `record_companion_submit(session, prop, confirmation: dict) ->
ApplicationProposal`. In one transaction:
1. add a `final_review` evidence row from `get_final_review(session, prop)`, using the shape the
   `POST /{id}/evidence` route stores, so the approved gate passes;
2. `transition(session, prop, "approved", consent={"channel": "companion", "note": "Queued run: user submitted"})`;
3. add a `submission_receipt` evidence row `{"kind": "submission_receipt", "host", "path", "text"}`;
4. `transition(session, prop, "submitted", consent={"channel": "companion", "note": ...})`.

Read `transition` (line 200) first: if it commits per call, wrap the four steps so a failure on
step 4 rolls back step 2 (it must not leave a job approved without a submit). Route: Companion
origin required (`is_companion`), body `{confirmation: {host: str≤255, path: str≤2048, text: str≤300}}`,
`TransitionError` → 409.

**Step 4: Run** the new test plus `tests/test_proposal_state_machine.py tests/test_proposals_router.py -q`.
Expected: PASS.

**Step 5: Commit** `feat(proposals): the Companion records a submit the user made`.

### Task 10: Run log counts and the run log from the Companion

**Files:**
- Modify: `backend/app/schemas/agent_runs.py` (`RunCountKey`)
- Test: `backend/tests/test_agent_runs_router.py`

**Step 1: Failing test:** posting `{"automation": "queued-run", "outcome": "ok", "counts": {"ready": 3,
"needs_you": 1, "applied": 2, "stopped": 0, "median_run_s": 140, "median_your_s": 25}}` with the
Companion Origin header returns 201, `agent` is None, and the counts round-trip.

**Step 2: Run.** Expected: FAIL (422 on unknown keys).

**Step 3: Implement.** Add `"ready", "applied", "stopped", "median_run_s", "median_your_s"` to
`RunCountKey`. Give `"queued-run"` the title "Queued run" wherever `AgentRunRead.title` resolves names
outside the catalog (read `services/agent_runs.py`; add a small `EXTRA_TITLES = {"queued-run": "Queued run"}`
if titles come only from `automations.catalog()`). Check the web Recent runs list renders the new
count keys: find its count-word map in `frontend/` (`grep -rn needs_you frontend/components`) and
add words for each new key.

**Step 4: Run** `pytest tests/test_agent_runs_router.py tests/test_agent_runs_service.py -q`, plus the
frontend type check. Expected: PASS.

**Step 5: Commit** `feat(agent-runs): Queued run counts`.

### Task 11: "Prepare queued jobs" (optional, off by default)

**Files:**
- Modify: `backend/app/schemas/auto_apply.py` (`prepare_queued: StrictBool = False`)
- Create: `backend/app/services/prepare_queued.py`
- Modify: `backend/app/routers/proposals.py` (the PATCH and bulk-transition routes schedule it on → `accepted`)
- Modify: `frontend/components/settings/auto-apply-section.tsx` (one switch, "Prepare queued jobs":
  "Quick-tailors and makes a PDF as soon as you queue a job. Skips jobs you are tailoring yourself.")
- Test: `backend/tests/test_prepare_queued.py` (new)

**Step 1: Failing tests:**
- setting off → queueing calls nothing (monkeypatch `quick_tailor.run_for_job` to record calls);
- setting on → queueing a job with no application and a best base calls `run_for_job(job_id, base)`,
  then `application_render.render_resume`;
- **never** called when the job has an open `TailoringSession` for that base, or an application
  whose `customized_json is not None` (the "don't sabotage custom tailoring" rule; one test each);
- a failure inside prepare is logged and never fails the PATCH (the user's queue action wins).

**Step 2: Run.** Expected: FAIL.

**Step 3: Implement** `prepare_queued.run(job_id: UUID) -> None` with its own `SessionLocal`
session (it runs after the response, via FastAPI `BackgroundTasks`). Inside: re-read the setting;
resolve the base the same way Task 8 does (move that helper into `queue_run.py` and import it);
skip on open session or draft; `quick_tailor.run_for_job(...)`; render. Catch `InProgressSessionError`
and `HealthGateBlockedError`, plus `Exception` with `logger.exception`. Respect the sync write guard:
call `require_owned` before writing, as other job writers do (SYSTEM.md inv-flush-guard).

**Step 4: Run** the new test plus `tests/test_proposals_router.py tests/test_full_automation_setting.py -q`.
Expected: PASS.

**Step 5: Commit** `feat(auto-apply): optionally prepare a job's resume when it is queued`.

---

### Task 10a: The known-gaps list (backend)

Design Part 8.3. A durable, value-free table of widgets the engine could not operate or that the
user fixed by hand, so the engine's to-do list survives the 50-run trace limit.

**Files:**
- Create: `backend/app/models/autofill_widget_gap.py` (+ export from `models/__init__.py`)
- Create: `backend/migrations/versions/<12-hex>_autofill_widget_gaps.py` (down_revision = Task 6's revision, which itself chains from abd275b457d8;
  revision; table-creation style: `7d3c1a9e5b20_agent_runs.py`)
- Modify: `backend/app/routers/autofill.py` (`POST /api/autofill/gaps`, `GET /api/autofill/gaps/summary`;
  `DELETE /api/autofill/telemetry` also clears gaps)
- Modify: `backend/scripts/fill_trace.py` (a `gaps` section in `report`)
- Modify: `frontend/components/settings/autofill-section.tsx` (one diagnostics line under Form filling:
  "Fields the Companion couldn't operate: N kinds on M sites, N fixed by you." With no gap rows, the
  line uses the Analytics coverage card's empty wording (`autofill-coverage-card.tsx`): the fill
  log is off unless turned on in the Companion's Options. With no list of hosts
  in the UI)
- Test: `backend/tests/test_autofill_gaps.py` (new)

**Row:** `family` (`^[0-9a-z]{1,24}$`, the recipe-book family hash from `content/recipes.js`), `host`
(≤253), `shape` (the inventory shape enum), `outcome` (`cannot_operate | unconfirmed | user_fixed |
missing_technique`), `count`, `first_seen_at`, `last_seen_at`; unique on (family, host, shape, outcome).
No label, no value, no option text.

**Step 1: Failing tests:**
- POST `{gaps: [{family, host, shape, outcome}]}` upserts and increments `count`, with
  `extra="forbid"` (a `label` or `value` key → 422);
- at most 40 gaps per post;
- the summary ranks by `count` desc and returns `{kinds, sites, user_fixed, top: [{family, shape,
  outcome, count, sites}]}` (no hosts in `top`);
- `DELETE /api/autofill/telemetry` clears the table (it holds hosts, like telemetry rows);
- `fill_trace.py report` prints the gaps section from a DB copy (reuse its existing DB-copy loader).

**Step 2: Run.** Expected: FAIL. **Step 3: Implement.** **Step 4: Run**
`pytest tests/test_autofill_gaps.py tests/test_autofill_telemetry*.py -q`. Expected: PASS.

**Step 5: Commit** `feat(autofill): a durable, value-free known-gaps list`.

## Phase 2 — Page operations (content world)

### Task 12: Pure page-kind classifier and button sort

Pure functions on a plain-data page summary, so node can test them without a DOM.

**Files:**
- Create: `extension/shared/page-kind.js`
- Modify: `extension/manifest.json` (content_scripts: after `shared/profile-fields.js`)
- Modify: `extension/panel/panel.html` (after `../shared/profile-fields.js`; the runner reads the
  verdict words too)
- Modify: the roster pins listed under Conventions
- Test: `backend/tests/test_extension_page_kind.py` (new; node harness)

**The summary** (built by Task 13 in the page):
`{ host, buttons: [{id, text, type, marker, inForm, visible, enabled}], passwordInputs, confirmPassword,
otpInput, captchaVisible, fillable, hasApplyLink, confirmationText, closedText, boardNative }`

**Step 1: Write failing node tests**, modelled on `tests/test_extension_never_submits.py`: build the
source with `run_node(driver, spec, tmp_path, source=<page-kind.js text>)` and a driver that calls
`ns.pageKind.classify(spec.summary)` and `ns.pageKind.sortButton(spec.button)`. Cases:

```python
NEXT = ["Next", "Continue", "Save and Continue", "Save & continue", "Review", "Review application", "Proceed", "Next step"]
SUBMIT = ["Submit", "Submit application", "Apply", "Apply now", "Send application", "Finish", "Complete",
          "Confirm", "Continue to submit", "Submit and continue", "Review and submit"]

@pytest.mark.parametrize("text", NEXT)
def test_next_words_sort_as_next(tmp_path, text): assert sort(tmp_path, text) == "next"

@pytest.mark.parametrize("text", SUBMIT)
def test_any_submit_word_sorts_as_submit_even_beside_a_next_word(tmp_path, text):
    assert sort(tmp_path, text) == "submit"

def test_a_submit_type_button_is_submit_whatever_its_text(tmp_path):
    assert sort(tmp_path, "Next", type="submit") == "next"  # see the note below

def test_unlabelled_or_odd_buttons_are_unclear(tmp_path):
    for text in ["", "Go", "Save", "Done", "→"]:
        assert sort(tmp_path, text) == "unclear"
```

Note on `type=submit`: many wizards use `<button type="submit">Next</button>` for every step
(`tests/browser/test_inventory.py:24` has one). The text decides; `type` alone does not make it
Submit. Any SUBMIT word always wins.

Page kinds, one test each: `captcha` (captchaVisible) beats everything; `create_account`
(confirmPassword); `verify` (otpInput); `sign_in` (exactly one password input, no confirm);
`confirmation` (confirmationText and fillable == 0); `closed`; `posting` (hasApplyLink and
fillable == 0); `form_step` (fillable > 0 and a visible enabled `next` button in the form and no
visible `submit` button); `review` (a visible `submit` button and no `next` one, or an `unclear`
advance button only); `unknown` (nothing). Also: `boardNative` + posting → `board_native`.

**Step 2: Run** `pytest tests/test_extension_page_kind.py -v`. Expected: FAIL (file missing).

**Step 3: Implement:**

```js
/* Maestro CS Companion — what kind of page is this, and which button moves on?
 *
 * Pure: reads a plain summary built in the page (content/page-reader.js), never the DOM, so
 * node tests it and both worlds load it. THE ONE RULE: a button carrying any Submit word is
 * "submit" and is never clicked, at any setting; when in doubt the page is "review" and the
 * queued run stops there (docs/plans/2026-10-10-companion-queued-run-design.md Part 2).
 *
 * WHAT THIS FILE PUBLISHES: ns.pageKind = { classify, sortButton, KINDS }.
 */
(() => {
  const ns = (window.careerStudioCompanion ??= {});
  const SUBMIT_WORDS = /\b(submit|apply|send|finish|complete|confirm)\b/i;
  const NEXT_WORDS = /^\s*(next( step)?|continue|save\s*(and|&)\s*continue|proceed|review( (application|your application))?)\s*$/i;

  function sortButton({ text = "" } = {}) {
    const words = String(text).replace(/\s+/g, " ").trim();
    if (SUBMIT_WORDS.test(words)) return "submit";
    if (NEXT_WORDS.test(words)) return "next";
    return "unclear";
  }

  function classify(s) {
    if (s.captchaVisible) return { kind: "captcha" };
    if (s.confirmPassword) return { kind: "create_account" };
    if (s.otpInput) return { kind: "verify" };
    if (s.passwordInputs === 1) return { kind: "sign_in" };
    if (s.confirmationText && !s.fillable) return { kind: "confirmation" };
    if (s.closedText) return { kind: "closed" };
    if (s.hasApplyLink && !s.fillable) return { kind: s.boardNative ? "board_native" : "posting" };
    const live = (s.buttons ?? []).filter((b) => b.visible && b.enabled);
    const sorted = live.map((b) => ({ ...b, sort: b.known ?? sortButton(b) }));
    const submit = sorted.some((b) => b.sort === "submit");
    const next = sorted.filter((b) => b.sort === "next" && b.inForm !== false);
    if (s.fillable > 0 || next.length || submit) {
      if (!submit && next.length === 1) return { kind: "form_step", next: next[0].id };
      return { kind: "review" };   // a Submit, several Nexts, or nothing sure: stop
    }
    return { kind: "unknown" };
  }

  ns.pageKind = { classify, sortButton, KINDS: ["captcha", "create_account", "verify", "sign_in",
    "confirmation", "closed", "posting", "board_native", "form_step", "review", "unknown"] };
})();
```

`b.known` is filled by Task 14's table. When it says `"submit"` or `"next"` for a marker, that beats
the text sort, except that a SUBMIT word in the text still forces `"submit"`. Add that rule and its
test in Task 14.

**Step 4: Run** the new tests plus the roster pins (`tests/test_extension_manifest.py
tests/test_extension_panel.py tests/test_extension_policy_blocked.py tests/test_extension_detection.py -q`).
Expected: PASS.

**Step 5: Commit** `feat(companion): a pure page-kind classifier where any Submit word stops the run`.

### Task 13: Read the page, and click Next (content script)

**Files:**
- Create: `extension/content/page-reader.js` (DOM → summary, and the advance op)
- Modify: `extension/content/agent.js` (`PAGE_HANDLERS`: `page_classify`, `page_advance`)
- Modify: `extension/sw.js` (`BROADCASTABLE` += `"page_classify", "page_advance"`)
- Modify: `extension/manifest.json` (after `content/detect.js`, before `content/agent.js`), and the pins
- Create: `backend/tests/fixtures/browser/wizard_step1.html`, `wizard_step2.html`, `wizard_review.html`,
  `wizard_confirmation.html`, `signin.html`, `create_account.html`, `verify_code.html`, `captcha.html`,
  `posting_external.html`, `posting_board_native.html`, `closed.html`. Follow the fixture rule in
  `backend/tests/fixtures/browser/README.md`; made-up employer "Acme".
- Test: `backend/tests/browser/test_page_reader.py` (new), `backend/tests/test_extension_sw_router.py`
  (update the pinned list)

**Step 1: Write failing browser tests** (`load(page, fixture_html(...), sources=ENGINE_SOURCES +
["shared/page-kind.js", "content/page-reader.js"])`). Call
`window.careerStudioCompanion.pageReader.summary()` and `pageKind.classify(...)`:
- each fixture classifies to its kind;
- `wizard_step1.html` (a required text field plus `<button type="submit">Next</button>`) →
  `form_step`, and `pageReader.advance(next)` clicks it: the fixture's `window.__oracle.advanced`
  becomes true;
- **never-submit pin:** for every SUBMIT word from Task 12, a fixture page built inline
  (`page.set_content`) with that one button: `advance()` with any id returns
  `{clicked: false, why: "submit"}` and the button's click listener never fires;
- `advance(id)` refuses an id that is not a currently visible, enabled `next` button
  (`{clicked: false, why: "not_next"}`), so a stale id from the panel cannot click anything else;
- `advance` re-sorts the button's CURRENT text at click time (a page that relabels Next to Submit
  between classify and advance is refused);
- an invisible reCAPTCHA badge alone (`.grecaptcha-badge`) is not `captchaVisible`; a visible
  challenge iframe (`iframe[src*="recaptcha/api2/bframe"]`, `iframe[src*="hcaptcha.com"]` with a box
  over 50×50 px, `iframe[src*="challenges.cloudflare.com"]`) is.

**Step 2: Run** `pytest tests/browser/test_page_reader.py -v`. Expected: FAIL.

**Step 3: Implement** `content/page-reader.js`, publishing `ns.pageReader = { summary, advance }`:
- `summary()` collects buttons from `button, input[type=submit], input[type=button], a[role=button]`.
  Use `ns.fillableControls()` for `fillable` (from detect.js). `visible` means a non-zero rect and not
  `visibility:hidden`. `inForm` means inside a `form`, `[role=form]`, or the same container as the
  first fillable control. Give each button a stable `id` per call: set
  `data-maestro-btn="<n>"` on it, the same tagging idea as `data-rt-qid`.
  - Texts: `textContent` / `value` / `aria-label`, trimmed, ≤80 chars.
  - `confirmationText`: `/thank you for (applying|your application)|application (was )?(submitted|received)|we('ve| have) received your application/i`
    on `document.body.innerText`, sliced to 20k.
  - `closedText`: `/no longer (accepting applications|available)|this (job|position) (has been|is) (closed|filled)/i`.
  - `hasApplyLink`: a visible link or button whose text matches `/^\s*apply( now| for this job)?\s*$/i`.
  - `boardNative`: `location.hostname` ends with `linkedin.com` or `indeed.com`.
  - Never read input VALUES (inv-autofill-telemetry-no-values spirit). The summary holds counts,
    button texts and booleans.
- `advance(id)`: find `[data-maestro-btn="<id>"]`, re-run `ns.pageKind.sortButton` on its current
  text, refuse unless it is `"next"`, visible and enabled, then `fillBase`-style click (reuse
  `ns.fillBase` click helpers if they exist; else `el.click()`). Return `{clicked: true}`.
- `agent.js` handlers, both GATED with `frameMayReceiveUserData(msg)` like `fill_inventory`. The
  refused shape is `{summary: null}` / `{clicked: false, why: "gate"}`:
  ```js
  page_classify: (msg) => (frameMayReceiveUserData(msg)
    ? { summary: ns.pageReader.summary(), top: window.top === window.self }
    : { summary: null }),
  page_advance: (msg) => (frameMayReceiveUserData(msg)
    ? ns.pageReader.advance(msg.id)
    : { clicked: false, why: "gate" }),
  ```
- Update `policy.js`'s header comment: Next is now clicked only by `page_advance` during a queued
  run; Submit never. Leave the deny-lists themselves unchanged.
- Keep `content/sections.js` `NAV_ID` and `fill-core.js` `keyable` unchanged. The fill engine still
  never touches navigation; only `page_advance` does.

**Step 4: Run** `pytest tests/browser/test_page_reader.py tests/test_extension_sw_router.py
tests/test_extension_manifest.py tests/test_extension_never_submits.py tests/browser/test_inventory.py -q`.
Expected: PASS.

**Step 5: Commit** `feat(companion): read the page kind and click Next, never Submit`.

### Task 14: Known Next/Submit buttons per ATS

**Files:**
- Create: `extension/shared/ats-buttons.js` (`ns.atsButtons = { knownSort(host, buttonAttrs) }`)
- Modify: `extension/content/page-reader.js` (`summary()` sets `known` on each button)
- Modify: `extension/shared/page-kind.js` (a SUBMIT word still beats `known: "next"`)
- Modify: manifest + pins (before `shared/page-kind.js`)
- Test: `backend/tests/test_extension_ats_buttons.py` (node) and cases in `tests/browser/test_page_reader.py`

**Step 1: Find real markers, don't guess.** Grep the existing fixtures for footer and advance buttons:
`grep -l "data-automation-id" backend/tests/fixtures/browser/*.html` and read the button markup in
the Workday and iCIMS fixtures. Add a table entry ONLY for a marker you can see in a fixture or a
recorded page, and cite it in a comment. Expected starting entries (verify each one):
- Workday: the footer advance button's `data-automation-id` (its text reads "Next" on steps, then
  "Submit" on review, so the entry marks it as THE advance control and lets the text decide; it
  never maps it to `"next"` unconditionally);
- Greenhouse: `#submit_app` → `"submit"`;
- Lever: `button[data-qa="btn-submit"]` or `#btn-submit` → `"submit"`;
- Ashby and iCIMS: only if a fixture shows them.

Untabled hosts use the generic sort.

**Step 2: Failing tests:**
- Greenhouse's submit marker with the odd text "Done" → `submit`;
- a SUBMIT word on a `known: "next"` marker → `submit`;
- an unknown host → no `known` key.

**Step 3: Implement**, with entries keyed by the `ATS_HOSTS` vendor regexes from `content/detect.js`.
Copy the regexes rather than importing them (detect.js publishes no table), and add a test that the
two tables list the same hosts for the vendors present.

**Step 4: Run** the new and existing page-reader tests. Expected: PASS.

**Step 5: Commit** `feat(companion): known ATS advance buttons`.

**As built (planner, 2026-10-13):** the table holds only markers recorded in the repo's fixtures:
Workday's footer button (`data-automation-id="pageFooterNextButton"`, from
`test_extension_detection.py`) with a `"text"` verdict — known navigation (counted in the form even
beside a site-wide footer form) whose own label decides Next or Submit, so no `known` is passed to the
sort. Greenhouse/Lever rows and their tests were withdrawn: there is no recorded markup for them, and
their buttons read "Submit Application", which the Submit-word rule already stops on. A test-only
injected row proves the submit wiring. A row is added only from a recorded page (live check).

### Task 15: Sign in with the saved login (top frame only)

**Files:**
- Modify: `extension/content/page-reader.js` (`signIn({email, password, allowedHost})`)
- Modify: `extension/content/agent.js` (`page_sign_in` handler)
- Modify: `extension/sw.js` (`panel_frame0` `ALLOWED` += `"page_sign_in"`; NOT `BROADCASTABLE`)
- Test: `backend/tests/browser/test_page_reader.py`, `backend/tests/test_extension_sw_router.py`

**Step 1: Failing tests:**
- `signin.html`: `signIn({email, password, allowedHost: "x.test"})` on a page whose host is `x.test`
  types both values (assert through the oracle), clicks the sign-in button, returns `{signedIn: "clicked"}`;
- a host mismatch returns `{signedIn: false, why: "host"}` and types nothing;
- in a subframe (`window.top !== window.self`) it returns `{signedIn: false, why: "frame"}`;
- a page with a confirm-password field returns `{signedIn: false, why: "create_account"}`;
- the sw router test: `page_sign_in` is accepted through `panel_frame0` and refused through
  `page_broadcast`.
- **password pin:** with `consentForms: true` (which lifts every label refusal), `fill_inventory`
  on a page holding `input[type=password]` and `input[autocomplete=new-password]` never lists either
  (browser test on `signin.html` and `create_account.html`). If the inventory lists one today, exclude
  `type=password` in `content/inventory.js` by SHAPE, not by label, so no consent setting can lift it.

**Step 2: Run.** Expected: FAIL.

**Step 3: Implement.** Find the email box by `input[type=email]`, else
`input[autocomplete=username]`, else a text input whose label matches `/e-?mail|user ?name/i`; find
the password box by `input[type=password]`. Type through `ns.fillBase` (`visitControl`/`leaveControl`
wrappers so React and Workday see real input). Find the button with
`/^\s*(sign in|log in|login|continue|next)\s*$/i`. Pressing "Continue" on a sign-in page is allowed:
it is not a submit of the application. Never keep the values in any variable outside the call, and
never log them. The handler:

```js
page_sign_in: (msg) => (window.top === window.self
  ? ns.pageReader.signIn({ email: msg.email, password: msg.password, allowedHost: msg.allowedHost })
  : { signedIn: false, why: "frame" }),
```

**Step 4: Run** the tests. Expected: PASS.

**Step 5: Commit** `feat(companion): sign in with the saved job-site login, top frame only`.

### Task 16: Save job records the employer's apply link

**Files:**
- Modify: `extension/content/agent.js` (`extractJobPosting` result gains `applyUrl`)
- Modify: `extension/panel/panel.js` (`ingestBodyFrom` ~1354, comment at 1334, and its "TWO KEYS AND NO MORE" comment;
  `panel/actions/job.js:94` posts the body)
- Test: `backend/tests/test_extension_panel_job.py`, `backend/tests/test_extension_posting_identity.py`
  or a new node test for the extraction

**Step 1: Failing tests:**
- a JSON-LD `JobPosting` with `"url"` pointing off the board, or a visible "Apply on company site"
  link with an absolute `https://` href to another host → `applyUrl` is that href;
- a LinkedIn/Indeed posting whose apply link stays on the board → `applyUrl` null;
- `javascript:` and relative hrefs → null;
- the panel's POST `/api/jobs` body carries `apply_url` when present and omits the key otherwise
  (assert through the panel harness `spec.api` capture, as the existing Save job tests do).

**Step 2: Run.** Expected: FAIL.

**Step 3: Implement.** Read only the page the user is viewing. Never `fetch` a board page in the
background with the user's cookies. Rewrite the `ingestBodyFrom` comment to "THREE KEYS AND NO MORE"
and say why the third exists.

**Step 4: Run** `pytest tests/test_extension_panel_job.py -q` and the new test. Expected: PASS.

**Step 5: Commit** `feat(companion): Save job keeps the employer's apply link`.

---

## The fill agent: context, tools, ideas (design Part 9, added 2026-10-13)

The owner's live Workday run (2026-10-13; five stored run traces, read with `scripts/fill_trace.py
last`) showed the loop is short of things to try, not of time. These tasks give the fill agent what
a normal AI agent has: **context** (what it knows when stuck), **tools** (moves it can make),
**ideas** (how to choose the next try), plus the checks that keep it honest. Every task here is
generic widget craft; none is a per-site procedure (Adjustment 7).

What the traces showed, so each task's test reproduces it:
- A text box labelled "Enter website. This input is for robots only, do not enter if you're
  human." was filled with the website (`map → personal.website jev 0.78`).
- Skills: about 19 `pick — matched`, then ONE `set → late (timeout) 20.2s`. The loop explores and
  picks every item first, then one `set` action searches and clicks every item AGAIN
  (`fill-loop.js` `commitSet` 1005-1133; `fill-core.js` `setAll` 1267-1316) under the page budget
  `min(setMax 20000, setItem 4000 × n)` (`fill-ops.js:29,183`). Twenty items cannot fit 20 s, so
  the batch timed out after 5 pills. A plain-row click is confirmed only by a 200 ms settle
  (`fill-core.js` `afterClick` 1109-1113); a checkbox row waits for the pill.
- Field of Study: `search:value → progressed` eight times, then `cannot_operate`. A `progressed`
  outcome is never added to `failedMoves` (`fill-loop.js` 873, 938), and the only other search the
  page offers is `search:word:N`, the value's own words (`fill-core.js` `wordsOf` 1349-1352).
- Country Phone Code showed "United States of America (+1)" but was asked: a Workday search box
  with one pill and unknown multiplicity reads `answered: false` (`shapes.js` `searchAnswered`
  185-189), /map routes it `none`, and `routed()` makes it `needs_answer` (`fill-loop.js`
  1404-1425).
- Phone Extension (optional, no fact) was asked: `routed()` never reads `required`.
- Nine text fields each logged `write → error (stale)` then `write → progress (verified)`: a choice
  redrew the section, and the write went to the old node. Nothing waits for the page to stop
  changing before a write (`fill-base.js` `settle` is a fixed sleep).

### Task 24: A recorded test form for the 2026-10-13 misses

**Files:**
- Create: `backend/tests/fixtures/browser/workday_misses.html`
- Modify: `backend/tests/fixtures/browser/README.md` (one entry; source: "owner's live run
  2026-10-13, run traces + screenshots", the observed behaviours below)
- Test: `backend/tests/browser/test_fixture_fidelity.py`

The page (made-up employer Acme, no real names; keeps `window.__oracle` per the README):
1. **Robot trap:** `<label for='hp'>Enter website. This input is for robots only, do not enter if
   you're human.</label><input id='hp' name='website'>`, visible, next to a real `Website` box.
   A second trap positioned offscreen (`position:absolute; left:-9999px`) labelled "Leave this
   field blank". A real `Middle name (leave blank if none)` box (NOT a trap).
2. **Phone code:** a `selectinput` in a `multiselect` container already holding one pill
   "United States of America (+1)" (`__oracle.phoneCode` set at load).
3. **Optional extension:** `Phone Extension`, not required, empty.
4. **Slow skills:** a `multiselect` skills box. A search answers in two stages (1 row at 300 ms,
   the full list at 700 ms: the gap stays under the engine's `QUIET_MS`, 500 ms). A row click adds its pill 600 ms later; the FIRST click on "Pandas"
   is ignored (the live "click landed during a redraw" case), the second works. A click on the
   row's text commits like its checkbox (on Workday the text is the checkbox's label).
5. **Field of Study (required):** a search box whose list holds "Statistics", "Computer Science",
   "Mathematics" only (word-prefix matching). Searching the full value "Data Science and
   Analytics" lists nothing, and so does its word "Data"; "Science" lists "Computer Science" (a
   plausible wrong match); "Statistics" lists one row. Only a term the agent chooses (Task 30)
   reaches the right answer. (Planner, 2026-10-13: the earlier "or Data lists matches"
   contradicted "only" and was withdrawn.)
6. **Redraw:** choosing a `Country` popup option replaces the `Address`, `City` and `Postal Code`
   inputs with new nodes (same labels) 400 ms later.

**Step 1:** Write the fidelity tests (they drive the page by hand, no engine): the delayed pill
appears 600 ms after a click; the first "Pandas" click adds nothing; the full Field of Study value
lists nothing and "Statistics" lists one row; the Country choice swaps the three inputs' nodes.
**Step 2:** Run `pytest tests/browser/test_fixture_fidelity.py -k misses -v`. Expected: FAIL (no
fixture). **Step 3:** Write the fixture. **Step 4:** Run again. Expected: PASS; also
`pytest tests/browser/test_fixture_privacy.py -q`. **Step 5:** Commit
`test(fixtures): a recorded form for the 2026-10-13 Workday misses`.

### Task 25: Never touch a robot trap

A trap is never filled, never listed, never asked about, and never counted as missing. Both fill
paths skip it: the fill loop (via the inventory) and the saved-answers fill
(`autofill.js` `fillFormFromProfile`, still reachable from `agent.js:585`).

**Files:**
- Modify: `extension/content/fill-base.js` (new `robotTrap(el, labelText)`, exported on
  `ns.fillBase`)
- Modify: `extension/content/inventory.js` (`eligible()` 84-102: `false` for a trap; read the label
  with `ns.shapes.readField(el)`, memoised per pass)
- Modify: `extension/content/autofill.js` (the control loop at 1397/1418: `continue` on a trap)
- Test: `backend/tests/browser/test_inventory.py`, `backend/tests/browser/test_fill_loop.py`,
  `backend/tests/test_extension_*` (the legacy path's node-harness test that covers
  `fillFormFromProfile`; grep `fillFormFromProfile` in `backend/tests/`)

**The rule** (a trap if ANY holds):
```js
// Phrases a honeypot uses to tell humans to stay out. "Bots" alone is not one
// ("Have you built bots?" is a real question), and "leave blank if none" is an
// optional field's hint, not a trap.
const TRAP_WORDS = /\bhoney ?pot\b|\bfor (?:spam ?)?(?:ro)?bots only\b|\bif you(?:'|\u2019)?(?:re| are) (?:a )?human\b|\b(?:do not|don(?:'|\u2019)t) (?:fill|enter|complete|type)(?: in)? (?:this|it)\b|^leave (?:this|it) (?:field |input |box )?(?:blank|empty)[.!]?$/i;
const robotTrap = (el, labelText) => {
  const words = [labelText, el.getAttribute("aria-label"), el.getAttribute("placeholder")]
    .filter(Boolean).map((s) => s.trim());
  if (words.some((s) => TRAP_WORDS.test(s))) return true;
  // Drawn wholly outside the page (a classic honeypot), though `visible` passes it.
  // Text boxes only: a widget library may hide a native <select> (or a checkbox)
  // off-page and drive it from a visible box (planner, 2026-10-13).
  if (!isTextLike(el)) return false;
  const r = el.getBoundingClientRect();
  return r.right + window.scrollX <= 0 || r.bottom + window.scrollY <= 0;
};
```

**Step 1: Failing tests:**
- `test_a_robot_trap_is_never_a_field`: on `workday_misses.html` neither trap is listed; `Website`
  and `Middle name (leave blank if none)` are. Parametrize the wording over "This input is for
  robots only", "If you are human, leave this blank", "Do not fill this field", "Leave this field
  blank", and an `aria-label`-only trap. Negative cases stay fields: "Have you built bots or
  automation tools?", "Middle name (leave blank if none)", "Do not include your country code".
- `test_a_run_never_writes_a_robot_trap`: a fill loop run with a profile holding a website leaves
  both traps empty (`__oracle` unset and `.value === ""`), and the run report lists neither.
- The legacy fill leaves the trap empty with the same profile.

**Step 2: Run** `pytest tests/browser/test_inventory.py -k trap tests/browser/test_fill_loop.py -k
trap -v`. Expected: FAIL (the trap is filled). **Step 3: Implement.** **Step 4: Run** the same,
then all of `tests/browser/test_inventory.py`. Expected: PASS, including
`test_a_visible_select_marked_aria_hidden_is_still_a_field` (aria-hidden alone is still not a
trap). **Step 5: Commit** `fix(fill): never fill a robot trap`.

### Task 26: A field that already holds an answer is "already there"

**Files:**
- Modify: `extension/shared/fill-loop.js` (`routed()` 1404-1425)
- Test: `backend/tests/browser/test_fill_loop.py`

**Rule:** a SEARCH field /map routes `none` (no fact, no safe answer) whose inventory record
already holds a pill (`committed` is a non-empty list, and `!f.invalid`) finishes `already` instead
of `needs_answer`. Only pills count: a popup's `committed` can be its placeholder ("Select One"),
which `answered` already handles. A mapped field keeps today's path (it may still need to add or change).
Don't change `searchAnswered`: `test_search_pills_are_read_from_the_multiselect_container` pins
it, and a skills box with one pill must still be filled.

**Step 1: Failing test** `test_a_held_value_with_no_fact_is_already_there`: on
`workday_misses.html`, Phone Country Code reports `already`, not `needs_answer`; an EMPTY box with
no fact still reports `needs_answer` (Field of Study, required and empty, with no fact). **Step 2: Run** `-k held_value`. Expected: FAIL. **Step 3:
Implement.** **Step 4: Run** all of `test_fill_loop.py`. Expected: PASS. **Step 5: Commit**
`fix(fill-loop): a field that already holds an answer is not asked`.

### Task 27: Leave an empty optional field alone

**Files:**
- Modify: `extension/shared/fill-loop.js` (`routed()`: route `none`, `!f.required`, nothing
  committed, `!f.invalid` → `finish(f, "left_blank")`)
- Modify: `extension/panel/stages/fill.js` (the summary line near 640: "N optional fields left
  blank", never under Needs your answer)
- Modify: `backend/app/schemas/autofill_telemetry.py` (add `left_blank` to the loop's statuses,
  108-127, with a comment: an optional field nothing answered, left empty on purpose). No
  trace or sw change: statuses there are a generic `WORD`
- Test: `backend/tests/browser/test_fill_loop.py`, `backend/tests/test_extension_panel.py`,
  `backend/tests/test_autofill_telemetry*.py`

A field the page marks invalid (after Next, Task 13 reads errors) is never `left_blank`: it goes
to Needs your answer. If Workday's required star is ever missed, that path catches it.

**Step 1: Failing tests:** Phone Extension reports `left_blank`; a required empty field with no
fact still reports `needs_answer`; an optional field with `invalid` reports `needs_answer`; the
panel shows "1 optional field left blank" and no link for it; the telemetry schema accepts
`left_blank`. **Step 2: Run.** Expected: FAIL. **Step 3: Implement.** **Step 4: Run**
`pytest tests/browser/test_fill_loop.py tests/test_extension_panel.py tests/test_autofill_telemetry*.py
-q`. Expected: PASS. **Step 5: Commit** `feat(fill-loop): optional fields with no answer are left
blank, not asked`.

### Task 28: Check every action in a list field

Each item is committed and confirmed right after its pick, in the list its explore already
settled (the search reuses it: `fill-core.js` `settledFor`, 532-536), so an item is searched once,
not twice, and a slow item costs only itself.

**Files:**
- Modify: `extension/shared/fill-loop.js` (`commitSet`: per item explore → pick → a one-item `set`
  → read `missing`; the batch `set` after all picks goes)
- Modify: `extension/content/fill-core.js` (`afterClick` 1109-1113: wait for `holds()` up to
  `OPEN_MS` after ANY row click in a set, not only a checkbox row; `chooseOne` in a set: one
  re-click when the pill did not appear and the row is still listed)
- Modify: `extension/content/fill-ops.js` (one-item `set` budget `setItem: 6000`; `setMax` only
  caps a batch, which no caller sends any more; keep it for safety)
- Test: `backend/tests/browser/test_fill_core_search.py`, `backend/tests/browser/test_fill_loop.py`

**Step 1: Failing tests** on `workday_misses.html` with 12 skills in the profile:
- all 12 pills land (`__oracle.slowSkills` holds 12), "Pandas" on its second click;
- the trace has one `set` step per item, each `verified`, and no `late`;
- an item the list never offers is reported missing while the other 11 still land;
- `test_a_search_set_keeps_existing_chips_and_reports_partial_honestly` still passes.

**Step 2: Run** `-k "skills or set"`. Expected: FAIL (the batch times out or Pandas is missing).
**Step 3: Implement.** **Step 4: Run** `tests/browser/test_fill_core_search.py
tests/browser/test_fill_loop.py -q`. Expected: PASS. **Step 5: Commit** `fix(fill): a list field
commits and confirms each item as it goes`.

### Task 29: Don't go round in circles

**Files:**
- Modify: `extension/shared/fill-loop.js` (`adapt()` 873-950)
- Test: `backend/tests/browser/test_adaptive_step.py`

**Rule:**
- A move whose outcome is `progressed` but whose NEXT state shows the same options it showed the
  last time that same move ran (same move id, same value) is a failed move: add the earlier state
  key to `failedMoves` and push `<mid> -> no_change` to the history.
- Any one move id runs at most twice per field and value, whatever its outcome (a third proposal
  is refused like an already-failed one).
- Add `no_change` to the outcomes `HISTORY_ENTRY` accepts (`backend/app/schemas/autofill_fill.py`
  187; it already allows any `[a-z_]+`, so only the test changes).

**Step 1: Failing test** `test_the_same_search_is_never_sent_three_times`: a scripted step model
that always answers `search:value` on the Field of Study box; the page sees `search:value` at most
twice, the model hears `no_change`, and the field ends in at most 4 steps, not 8. **Step 2: Run.**
Expected: FAIL (8 sends). **Step 3: Implement.** **Step 4: Run** all of
`test_adaptive_step.py`. Expected: PASS. **Step 5: Commit** `fix(fill-loop): a move that changed
nothing is not repeated`.

**As built (planner, 2026-10-13):** `scroll` is exempt from the twice-per-move cap (a long list needs
one scroll per window); a scroll that shows the same options is still `no_change`, and the page
refuses one past the list's end. The `no_change` check compares the options shown, not the whole
state.

### Task 30: Tools: the agent writes its own search term

A new move, `search:term`: type a term the AGENT chose (a shorter word, a synonym, the category),
not the value. Typing a search is never an answer: the answer is still a `click:oN` that clears
the slot's match floor (`verdict`), exactly as today.

**Files:**
- Modify: `extension/content/fill-core.js` (`stepState` 1427-1434: offer `{mid: "search:term",
  describe: "Type a search term you choose (a shorter word, a synonym or the category) into the
  search box"}` wherever `search:value` is offered; `move()` 1459-1580: `search:term` types
  `action.term`)
- Modify: `extension/shared/fill-loop.js` (`adapt()`: pass `res.term` with the move; keep the
  terms tried for this field in `rows` and send them as `tried_terms`)
- Modify: `backend/app/schemas/autofill_fill.py` (`MOVE_ID` and `HISTORY_ENTRY` gain
  `search:term`; `StepRequest.tried_terms: list[str]` ≤ 6, each ≤ 40; `StepResponse.term: str |
  None`, pattern `^[\w .&+/#-]{1,40}$`)
- Modify: `backend/app/services/autofill_step.py` (Jev only picks among ids, so when the chosen
  move is `search:term`, ONE fast-model call writes the term: "Write one search term of 1 to 3
  words likely to list the goal's answer. Not one of: <tried_terms>. Return JSON {"term": ...}";
  invalid, repeated or out of time → treat as `give_up` for this step)
- Modify: `extension/sw.js` `TRACE_MOVE` (:268) += `search:term`, or `scrubTrace` drops the step
  (`app/schemas/autofill_trace.py` imports `MOVE_ID`, so the schema edit above covers the server).
  The trace records `search:term`, never the term: a term can carry the value
  (`{#inv-autofill-telemetry-no-values}`). Test through `test_extension_sw_router.py` `_post_trace`
  (defaults to `OPTED_IN`)
- Test: `backend/tests/test_autofill_step.py`, `backend/tests/browser/test_adaptive_step.py`

**Step 1: Failing tests:**
- backend: a request offering `search:term` where the scripted model picks it returns a valid
  `term`; a term repeating `tried_terms` or failing the pattern returns `abstained`; a
  `search:term` with no `term` from the page is never executed;
- browser: on `workday_misses.html` Field of Study, after `search:value` lists nothing the loop
  sends `search:term` "Statistics" (scripted), then `click:oN` on "Statistics" with reason
  `closest`, and the field ends `closest_filled` (flag slot, complete list);
- the report's trace (`trace_of(out)`) and its `scrubTrace`d copy hold `search:term` and no term
  text.

**Step 2: Run.** Expected: FAIL. **Step 3: Implement.** **Step 4: Run**
`pytest tests/test_autofill_step.py tests/browser/test_adaptive_step.py -q`. Expected: PASS.
**Step 5: Commit** `feat(fill): the step agent can search with its own term`.

### Task 31: Ideas: a technique card per widget kind, and what worked here

**Files:**
- Create: `backend/app/services/autofill_techniques.py` (`CARDS: dict[str, str]`, one per kind)
- Modify: `backend/app/schemas/autofill_fill.py` (`StepRequest.kind: Literal["popup", "search",
  "multi", "group", "select", "date"] | None`; `StepRequest.worked_here: list[str]` ≤ 4, each
  matching `MOVE_ID`)
- Modify: `backend/app/services/autofill_step.py` (`_instructions` 110-132 appends
  "Techniques for this kind of widget: <card>" and, when `worked_here`, "On this site these moves
  worked before: <ids>")
- Modify: `extension/shared/fill-loop.js` (`adapt()`'s POST 903-909: `kind` from the field's
  shape and `multi`; `worked_here` from the recipe book's lesson for `f.recipe`, ids only)
- Test: `backend/tests/test_autofill_step.py`, `backend/tests/test_autofill_techniques.py` (new)

The cards (each ≤ 700 characters, so a step's prompt stays small):
- `search`: "Results can arrive in stages; wait for the list, don't search again at once. If the full
  answer lists nothing, search one distinctive word of it, then a synonym or the broader category
  (search:term). Prefer an exact option; take the closest only when the list is complete. Never
  repeat a search that changed nothing."
- `multi`: "Each item is its own search and click; a pill appearing is the proof. If an item's pill
  doesn't appear, click its row once more. An item the list never offers is skipped, never
  replaced with an unrelated one."
- `popup`: "Open the list first. Long lists scroll: scroll before deciding the answer is missing.
  A row that opens a group leads to sub-options; open it only if the answer is inside."
- `group`: "Click the option whose text answers the question as worded. A lone checkbox is yes
  when ticked."
- `select`: "Choose the option whose text answers the question; never the placeholder."
- `date`: "Fill the parts the page shows (month, day, year) in its own format."

**Step 1: Failing tests:** every `CARDS` value ≤ 700 characters and every `kind` has a card; the
prompt for `kind: "search"` contains the search card; `worked_here: ["open"]` adds the line; an
unknown `kind` or a `worked_here` id outside `MOVE_ID` is a 422; the loop's request carries `kind`
and `worked_here` for a field with a recipe. **Step 2: Run.** Expected: FAIL. **Step 3:
Implement.** **Step 4: Run** `pytest tests/test_autofill_step.py tests/test_autofill_techniques.py
tests/browser/test_adaptive_step.py -q`. Expected: PASS. **Step 5: Commit** `feat(fill): the step
agent gets a technique card and what worked on this site`.

The known-gaps list (Task 10a) is where the next cards come from: a `cannot_operate` or
`missing_technique` kind that keeps recurring is a card (or a move) to write, each with a recorded
test form.

### Task 32: Let the page settle before typing

**Files:**
- Modify: `extension/content/fill-base.js` (new `quiet(t, {ms = 300, max = 2000})`: resolves once
  `document.body` has had no mutations for `ms`, or after `max`; uses `sleep`, so a hidden tab
  works (Task 1a))
- Modify: `extension/content/fill-ops.js` (`run()`: before a `write`, `await quiet()` when the
  page changed in the last 300 ms; the inventory observer's `generation` counter tells; AND after
  any choice commit, the next write waits `quiet({ms: 600})`: a redraw can start up to ~400 ms after
  a choice with nothing changing in between (the recorded form's Country redraw), so a 300 ms quiet
  alone would let a write start inside that gap. A write whose node is replaced mid-write re-finds
  the field by its fingerprint and writes once more in the SAME round, never the next. (Planner,
  2026-10-13, after the batch-1 review.))
- Test: `backend/tests/browser/test_fill_loop.py`

**Step 1: Failing test** `test_a_redrawn_section_is_typed_once`: on `workday_misses.html`, choose
Country and START the Address, City and Postal Code writes as soon as the choice's click returns
(inside the 400 ms gap, on purpose, so the test can't pass by timing); each lands on the NEW node,
the oracle holds all three values, and the trace shows one `write` per field, no `stale`. **Step 2: Run.** Expected: FAIL (`write → error (stale)`).
**Step 3: Implement.** **Step 4: Run** all of `test_fill_loop.py`; also
`tests/browser/test_fill_hidden.py`. Expected: PASS. **Step 5: Commit** `fix(fill): wait for a
redrawn section before typing`.

### Watch in the Phase 2 live check (no task yet)

- The sponsorship text box and residency-permit question on the same form routed `none` at
  0.88 and 0.62 against a 0.90 floor, while "work permit" mapped at 0.91 to `work_auth`. If the
  live check shows protected questions with a saved fact still parking, lower the map's floor for
  those slots on evidence (`scripts/fill_trace.py report` suggestions), not by guess.

## Phase 3 — The runner and the panel

### Task 33: Use every saved answer, not the first 30 (Phase 3, first task; added 2026-10-13)

`autofill_catalog._custom` offers only the first `MAX_CUSTOM = 30` saved answers, in the order
saved. Once runs remember every answer (Task 20), a user passes 30 after roughly ten applications,
and every newer answer would silently stop being used. Raising the cap isn't the fix: all facts
share `MAX_SLOTS = 240`, the decision model's choice ceiling. Instead each request offers the 30
saved answers CLOSEST in meaning to the page's own questions.

**Files:**
- Modify: `backend/app/services/autofill_catalog.py` (`build(..., questions=None, keep=())`;
  `_custom`: with `questions`, rank every row by its best cosine similarity to any of them
  (`app.services.ats.embeddings.embed_texts` / `cosine`, the app's local model) and offer the top
  `MAX_CUSTOM`; when embeddings fail, rank by shared words instead (never fail the fill); without
  `questions`, today's first 30. A row keeps its slot `custom.<original index>`, and any slot in
  `keep` is always offered)
- Modify: `backend/app/routers/autofill.py` (`/map` passes its fields' questions; `/pick`, `/step`
  and the reasoned pass pass `keep={payload.slot}` so a `custom.<i>` that /map chose is still there
  on the next call)
- Modify: `frontend/components/settings/autofill-section.tsx` (remove the "Only the first 30…"
  line Task 5 added)
- Test: `backend/tests/test_autofill_catalog.py`, `backend/tests/test_autofill_fill_router.py`,
  `backend/tests/test_frontend_settings_cards.py`

**Step 1: Failing tests:**
- 40 saved answers where #35 is "Is a relative a government official?": a build with the page
  question "Do any of your family members hold public office?" offers `custom.35` (embedding stubbed
  with a fake that scores that pair highest; one test with the real local model, marked like the
  other embedding tests);
- with `keep={"custom.35"}` and unrelated questions, `custom.35` is still offered;
- an embedding failure (stub raises) falls back to word overlap and still offers ≤ 30;
- no request ever offers more than `MAX_CUSTOM` saved answers or more than `MAX_SLOTS` facts.

**Step 2: Run.** Expected: FAIL. **Step 3: Implement.** **Step 4: Run** `pytest
tests/test_autofill_catalog.py tests/test_autofill_fill_router.py tests/test_autofill_step.py
tests/test_autofill_pick.py -q`. Expected: PASS. **Step 5: Commit** `feat(autofill): offer the
saved answers closest to the page, not the first 30`.


### Task 17: `shared/queue-run.js`, the runner (pure, deps injected)

The heart of the feature. One run record per job; a pure async driver; every browser and panel
effect injected, so node can test the whole state machine with fakes.

**Files:**
- Create: `extension/shared/queue-run.js` (panel-only; add to `panel.html` after
  `../shared/fill-loop.js`'s block, keeping `fill-loop.js` directly after `guided-run.js`)
- Modify: `backend/tests/test_extension_page_messaging.py` (add the new shared caller file)
- Test: `backend/tests/test_extension_queue_run.py` (new; node harness with fake deps, like
  `test_extension_guided_fill.py`'s `_RUNNER_DRIVER`)

**Record shape** (plain JSON; saved at every page boundary):

```js
{ jobId, proposalId, applicationId, base, company, title, openUrl,
  tabId: null, hosts: [], step: 0, fingerprint: null, seen: [],
  status: "waiting" | "opening" | "signing_in" | "filling" | "advancing" | "parked" | "ready"
        | "confirming" | "applied" | "stopped",
  why: null,              // a short reason word when parked/stopped: captcha | create_account | verify
                          // | sign_in_failed | board_native | closed | open_questions | no_change
                          // | loop | step_limit | error | user
  open: [],               // parked page's open questions: [{fid, question, required}]
  startedAt, readyAt, yourMs: 0, flowOrigin: null }
```

**Deps** (all required except where noted; throw `TypeError("queue-run: missing dep X")` like
fill-loop):
`openTab(url) → tabId`, `classify(tabId) → [{frameId, result:{summary, top}}]`,
`advance(tabId, frameId, id) → {clicked, why}`, `fill(record) → fill-loop report`, `signIn(record) →
{signedIn, why}`, `waitForChange(tabId, before, ms) → {changed, url}`, `save(records)`,
`onUpdate(record)`, `now()`, `sleep(ms)`, `random()`, `cancelled(record)`.

**Exports:** `ns.queueRun = { drive(record, deps), next(records, limits), LIMITS }`, where `LIMITS =
{ parallel: 3, waitingMax: 10, stepMax: 15, changeMs: 15000, paceMs: [2000, 6000] }`, plus
`HIDDEN_TABS_OK = true` (Task 1a's acceptance passed; see "Spike result").

**`drive(record, deps)`, the per-tab loop:**
1. `opening`: `tabId = openTab(openUrl)`.
2. Loop until a terminal state, checking `cancelled(record)` before every step:
   - `classify` → the first frame result whose `summary` is not null, preferring `top: true`, then
     the frame with the most `fillable`. `kind = ns.pageKind.classify(summary)`.
   - `captcha | create_account | verify | board_native` → `parked` with `why = kind`. Return.
   - `closed` → `stopped`, `why: "closed"`. Return.
   - `confirmation` → only after `ready`: status `confirming` (Task 20 records it). Before ready,
     treat as `review`.
   - `sign_in` → if `record.signedIn` is already true → `parked` `why: "sign_in_failed"` (no
     retry, to avoid a lockout). Else `signing_in`, `signIn(record)`, set `record.signedIn = true`,
     `waitForChange`, continue.
   - `posting` → click its Apply through `advance`. "Apply" is a Submit word, so this is the ONE
     narrow exception, and it holds only when ALL of these are true: `classify` said `posting`
     (no fillable control on the page), `record.step === 0`, nothing has been filled in this
     record yet (`record.filled !== true`), and the tab's host is `openUrl`'s host. Add
     `advance(tabId, frameId, id, {apply: true})` to Task 13's `advance`: it re-checks on the page
     that no fillable control exists and that the text matches the apply-link regex
     `/^\s*apply( now| for this job)?\s*$/i` exactly. Add those cases to Task 13's tests while
     implementing here (log the deviation): including a review-like page with no fields and an
     "Apply" button reached AFTER a fill, which must NOT be clicked (the record's `filled` flag
     makes it `review`). Then `waitForChange`, continue. Set `record.filled = true` after any
     `fill(record)`.
   - `form_step` or `review` → `filling`: `report = await fill(record)`. Open questions =
     `report.fields.filter(f => f.required && ["needs_answer","cannot_operate"].includes(f.status))`.
     `unconfirmed` does NOT park (owner, 2026-10-11, "park less"): the advance below and the page's
     own validation decide, and the no-change path refills once before parking.
     If any → `parked`, `why: "open_questions"`, `open = [...]`. Return (Resume re-enters `drive`).
   - After a clean fill: `review` → `ready`, `readyAt = now()`. Return. `form_step` → `advancing`:
     record the fingerprint (url + step heading + sorted button texts + fillable count, joined); if
     it is already in `seen` → `parked`, `why: "loop"`; if `step >= stepMax` → `parked`,
     `why: "step_limit"`; else `advance(...)`, `waitForChange(tabId, fingerprint, changeMs)`. If not
     changed → `fill(record)` once more (the page may show errors the fill can fix), advance once
     more; still unchanged → `parked`, `why: "no_change"`. Else `step += 1`, continue.
   - `unknown` → `parked`, `why: "unknown_page"`.
3. Every status change calls `onUpdate(record)` then `save(records)`.

**`next(records, limits)`:** the scheduler.
- Count `filling`-like statuses (`opening | signing_in | filling | advancing`), and waiting
  `parked | ready`.
- Return the next `waiting` record when filling < parallel and waiting < waitingMax, else null.
- The host sleeps `paceMs` (random in range) between opens.

**Step 1: Failing node tests**, one per transition, with scripted fakes (`classify` returns a queue
of summaries, `fill` a queue of reports):
- step1 → step2 → review ends `ready` after two advances, no submit ever requested (assert that the
  `advance` fake only ever saw ids the summary marked `next`);
- a review page with a Submit button ends `ready` without calling `advance`;
- a captcha → `parked/captcha`; a create-account page → `parked/create_account`;
- sign_in → signIn called once → still sign_in → `parked/sign_in_failed` (signIn not called twice);
- an open required field → `parked/open_questions` with `open` listing it;
- a required field reported `unconfirmed` does NOT park: the driver advances; if the page then does
  not change, it refills once and parks with `why: "no_change"`;
- the same fingerprint twice → `parked/loop`; no change after advance + refill → `parked/no_change`;
- 15 steps → `parked/step_limit`;
- `cancelled()` true mid-run → `stopped/user`, and no deps are called after it;
- `next()`: 3 filling → null; 10 parked/ready → null; else the oldest waiting.

**Step 2: Run** `pytest tests/test_extension_queue_run.py -v`. Expected: FAIL.

**Step 3: Implement** to pass. Keep it free of `chrome.*`, `document` and `fetch`
(`test_extension_panel.py` forbids `fetch(` in panel files).

**Step 4: Run** the tests plus `tests/test_extension_panel.py tests/test_extension_page_messaging.py -q`.
Expected: PASS.

**Step 5: Commit** `feat(companion): the queued-run driver`.

### Task 18: Per-tab job memory (replaces the 30-minute single key)

**Files:**
- Modify: `extension/shared/decisions.js:334` (`restorableSession`: no `ttlMs`; origin, tenant and
  backend-wins guards stay)
- Modify: `extension/panel/panel.js` (`KEY`, `SESSION_TTL_MS`, `rememberSession` 2212,
  `restoreSession` 3201, `refreshPage` comment 2953-2961, the KEY comment block 131-177; `KEY` 178,
  `SESSION_TTL_MS` 186)
- Modify: `extension/INTERNALS.md` (the `widget.session` paragraphs 1527-1532 and 467-478)
- Test: `backend/tests/test_extension_panel*.py` and `tests/extension_fixtures.py` (session fixtures),
  plus the decisions tests that pass `ttlMs`

**Behaviour:**
- Entries live in `chrome.storage.session` under `widget.sessions`, a map `{[tabId]: entry}`.
  `rememberSession` writes `card.tabId`'s entry; `restoreSession` reads `card.tabId`'s.
- `chrome.tabs.onRemoved` deletes the entry.
- Migration: on panel boot, read the old `chrome.storage.local["widget.session"]` once. If it is
  under 30 minutes old, adopt it for the active tab (all guards still apply). Then
  `chrome.storage.local.remove("widget.session")`. Comment why the rename is safe now.
- No TTL: an entry lives while its tab is open. The tenant and backend-wins guards still drop it
  when the tab moves to another employer or the server matches a different job.

**Step 1: Failing tests** (panel harness; the stub already has `storage.session`):
- a pick made in tab 1, then 40 minutes later (inject `Date.now`), a wizard page in tab 1 restores it;
- a pick in tab 2 does not overwrite tab 1's;
- closing tab 1 removes its entry;
- an old `widget.session` local entry is migrated once and removed;
- a tenant change in the same tab still drops it (existing guard tests keep passing).

**Step 2: Run.** Expected: FAIL.

**Step 3: Implement.** Update every `restorableSession` caller and test that passed `ttlMs`.

**Step 4: Run** `pytest tests/test_extension_panel*.py tests/test_extension_posting_identity.py -q`.
Expected: PASS.

**Step 5: Commit** `feat(companion): remember each tab's job while the tab is open`.

### Task 18a: Per-run fill limits ("try harder in runs")

Design Part 8.1. Today `ns.fillLoop.limits` is one shared mutable object (tests reassign it).
Parallel runs and the user's own Autofill must not share a changed budget.

**Files:**
- Modify: `extension/shared/fill-loop.js` (`runFill(deps, options)`: `options.limits` merged over the
  module defaults for THIS run only; every read of `limits.X` inside the run reads the merged copy)
- Test: `backend/tests/browser/test_fill_loop.py`

**Step 1: Failing tests:**
- a run with `options.limits = {FIELD_MS: 60000, MAX_STEPS: 12}` lets a scripted field take 10
  adaptive steps where the default run gives up at 8;
- a second run started without `options.limits` in the same page still stops at 8 (the module
  object is unchanged after the first run).

**Step 2: Run** `pytest tests/browser/test_fill_loop.py -k limits -v`. Expected: FAIL.

**Step 3: Implement.** Add `const RUN_LIMITS = {FIELD_MS: 60000, MAX_STEPS: 12}` to
`shared/queue-run.js` (Task 17); Task 19's `fill` dep passes it.

**Step 4: Run** the whole `tests/browser/test_fill_loop.py`. Expected: PASS.

**Step 5: Commit** `feat(fill-loop): per-run limits; queued runs try harder`.

### Task 19: Panel host: the Queue view, start a run, tabs, sign-in, stop

**Files:**
- Create: `extension/panel/actions/run.js` (`ns.panelActionsRun = { loadQueue, startRun, stopRun,
  stopAll, resumeRun, focusRun, setRunChoice, setView }`)
- Modify: `extension/panel/actions.js` (roster: `need("actions/run.js", ns.panelActionsRun)` plus the
  bindings), `extension/panel/panel.html` (after `actions/track.js`)
- Modify: `extension/panel/panel.js`:
  - new `card` fields `view: "page" | "queue"`, `queue: null`, `runs: []`, `runWindowId: null`,
    `runParallel: 3` (Task 1a passed);
  - `render()` draws the **This page | Queue (N)** switch at the top (a tablist; N = queued count)
    and either today's rail (`page`) or the Queue view (`queue`, Task 20's `panel/runs.js`);
  - fresh-open view rule: `view = "queue"` when a run is active or the active tab has neither a
    matched job nor a detected form; otherwise `"page"`. A user switch sticks until the panel closes;
  - `actionStore()` gains `tabBroadcast(tabId, message)` = `ask("page_broadcast", {tabId, message})`
    and `tabFrame0(tabId, message)`;
  - `withFlowOrigin` reads a run record's `flowOrigin` when `payload.tabId` belongs to a run (the
    current `flowFor` returns null unless `tabId === card.tabId`);
  - `onTab` must NOT send `fill_cancel` to a run tab, and must not cancel a run when the user
    switches tabs.
- Test: `backend/tests/test_extension_panel_run.py` (new; panel harness)

**Behaviour:**
- **The Queue view** shows only when `GET /api/settings/auto-apply` says `full_automation` (else
  the switch is hidden and the panel is today's). Opening it → `loadQueue` →
  `GET /api/autofill/queue-run` → `card.queue = {items, skipped, cap_left, choices}`, re-read on
  every switch to Queue and after every run. The list itself is the pre-run step; there is no
  separate sheet. **Apply to N** (N = ticked rows) starts the run.
- **Per-row choices on the Queue view:**
  - `knockout === "conflict"` → unticked, "Apply anyway" toggle;
  - `board_native` → listed, unticked, "Opens on the job board; apply there yourself";
  - `pdf_ready` → nothing to choose;
  - `!pdf_ready && has_draft` → "Create PDF" (render the existing draft; never quick tailor);
  - `!pdf_ready && !has_draft && tailoring_open` → default **Skip** ("You're tailoring this one;
    finish it first"), with no quick tailor option;
  - `!pdf_ready && !has_draft && !tailoring_open && base_resume` → **Quick tailor** (default) |
    Use base resume | Skip;
  - `!base_resume` → Skip ("Score this job first").
  - `knockout === "incomplete_profile"` → one line per kind with a link to the web app's profile
    settings (`card.settings` holds the web app URL; reuse the deep-link builder in `renderIdentity`).
- **startRun:**
  - Records are built from ticked items.
  - Window: `chrome.windows.create({url: "about:blank", focused: false})` → `runWindowId`.
  - Resume prep: for items needing it, run quick tailor (`POST /api/jobs/{id}/quick-tailor {base_resume}`)
    or render (`POST /api/applications/{id}/render`) ONE AT A TIME, sequentially in the background,
    each before its record becomes `waiting`. Use base resume → `POST /api/applications/from-base`
    `{job_id, base_resume}` then render. A 409 from quick tailor (an open session) → that record
    `stopped`, `why: "tailoring_open"`.
  - Scheduler: `while` `ns.queueRun.next(...)` yields a record → `drive(record, deps)` without
    awaiting it, then `sleep(pace)`. Re-check every 2 s and after every record update.
- **Deps for drive:**
  - `openTab`: `chrome.tabs.create({windowId, url, active: false})`. Adopt tabs opened from it:
    `chrome.tabs.onCreated` with `openerTabId === record.tabId` swaps `record.tabId`.
  - `classify`: `tabBroadcast(tabId, {type: "page_classify", flowOrigin})`.
  - `advance`: `tabBroadcast` with a frame target. Add `frameId` support to `page_broadcast`
    (`sw.js` `fanoutTab`: when `msg.frameId` is an integer, send to that frame only) and pin it in
    `test_extension_sw_router.py`.
  - `fill`: `ns.fillLoop.runFill` with
    `{broadcast: (m) => tabBroadcast(record.tabId, m), api, recipes, cancelled: () => cancelled(record), beforeSweep: autoAttach for record}`
    and `{applicationId, sourceHint}`, then `ns.panelRecordReceipt` for that record's tab. Generalize
    `recordReceipt`'s `store`/`facts` reads to take `{tabId, jobId, applicationId, base}` explicitly
    rather than `card`. Move the shared part into a helper both callers use.
  - `signIn`: `POST /api/companion/job-site-login {proposal_id}` →
    `tabFrame0(tabId, {type: "page_sign_in", email, password, allowedHost})`. The credentials live
    only in that function's locals and are never written to `card`, a record, a trace or a note.
    `allowedHost` is the tab's current host and must be in `record.hosts` (every host the run reached
    from `openUrl` by its own Apply/Next clicks, appended after each `waitForChange`).
  - `waitForChange`: poll `chrome.tabs.get(tabId).url` plus `page_classify` every 500 ms up to `ms`,
    comparing fingerprints.
  - `save`: `chrome.storage.session.set({queueRun: records})`. On panel boot, read it and show the
    records (status only; a reopened panel does not resume driving, per the design).
  - `cancelled`: `record.stopRequested || card.runStopAll`.
- **Spike result (Task 1): take turns.** `fill` first calls `chrome.tabs.update(record.tabId,
  {active: true})` inside the run window, and the scheduler keeps `parallel` at 1. `parallel` above 1
  (the 1 to 5 control) is shown only when Task 1a's acceptance passed (a constant in
  `shared/queue-run.js`, `HIDDEN_TABS_OK`, set true by Task 1a's final commit). While filling, if the
  run tab reports `document.hidden` (the window is covered) and `HIDDEN_TABS_OK` is false, the run
  pauses that tab with "Keep the run window visible" and resumes when it is visible again.
- **stopRun / stopAll:** set flags, send `fill_cancel` to the record's tab.

**Step 1: Failing panel-harness tests.** Extend the stub with `windows.create`, `tabs.create`,
`tabs.onCreated`, `tabs.onRemoved` and `tabs.update`, recording calls:
- the button is hidden when full automation is off;
- the switch is hidden with full automation off; the fresh-open rule picks `queue` on a page with no job
  and no form, and `page` on a posting; the Queue view's defaults: a conflict is unticked; a tailoring-open job defaults to Skip with no quick
  tailor offered; a draft offers only Create PDF;
- startRun opens ONE window, never focuses it, and opens at most 3 tabs with gaps
  (`sleep` fake records the pace);
- `quick-tailor` is never called for a job with `tailoring_open` or `has_draft`, whatever the user
  clicked (guard inside `startRun`, not only in the Queue view's rows);
- sign-in: the credentials never appear in `card`, `sessionWrites`, `writes`, telemetry or trace
  sends (scan every recorded message for the password string);
- a tab switch during a run sends no `fill_cancel` to run tabs;
- stopAll sends `fill_cancel` to every running tab.

**Step 2: Run.** Expected: FAIL.

**Step 3: Implement.**

**Step 4: Run** `pytest tests/test_extension_panel*.py tests/test_extension_sw_router.py
tests/test_extension_queue_run.py -q`. Expected: PASS.

**Step 5: Commit** `feat(companion): the Queue view, run window, pacing, sign-in`.

### Task 20: Run list, Needs you, Resume, auto-mark applied, run log

**Files:**
- Create: `extension/panel/runs.js` (`ns.panelRuns = { render(ctx) }`; add to `panel.html` before
  `panel.js`)
- Modify: `extension/panel/panel.html` (a `<section id="runs">` region between `#identity` and `#rail`)
- Modify: `extension/panel/panel.js` (`render()` calls `region("runs").replaceChildren(ns.panelRuns.render(...))`)
- Modify: `extension/panel/actions/run.js` (`resumeRun`, confirmation watch, undo, run log, timing)
- Modify: `extension/panel/panel.css` (follow the existing tokens; no emoji or text glyphs, icons via
  `ns.icon`; `test_extension_panel_icons.py` scans this)
- Test: `backend/tests/test_extension_panel_run.py`

**Behaviour:**
- **Run list** (shown when `card.runs.length`): header "Queued run · N ready · N need you" with
  **Stop all**. One row per record: company · title · status word · step. Status words: Waiting,
  Opening, Signing in, Filling page N, Needs you, Ready to submit, Marking applied, Applied,
  Stopped. A `why` word appears as a short reason ("CAPTCHA", "Create an account", "Email code",
  "Sign-in didn't work", "Apply on the job board", "Position closed", "Questions on this page",
  "The page didn't move on", "Too many steps").
- Clicking a row: `chrome.tabs.update(tabId, {active: true})` and
  `chrome.windows.update(runWindowId, {focused: true})`.
- **Needs you (open_questions):** the row expands to list `open` questions as jump links
  (`fill_focus` to that tab) and **Resume**. No checkbox: answers are always remembered.
  Resume:
  1. `fill_inventory {peek: true, readOnly: true}` on the tab, then build the receipt with
     `ns.receipt.fromEdits` (values the user typed) and post it (source `you`);
  2. `learnAnswer(store, {label: question}, answer)` for each answered open question that is not
     long free text (the `textarea` shape is never learned), using the same `saveTargetFor` path as
     pause rows (move `learnAnswer` to accept a plain label). Keep each target's PREVIOUS value; the
     panel shows "Saved N answers to your profile · Undo", and Undo writes the previous values back;
  3. re-enter `drive(record, deps)`, which refills, then advances or reaches ready.
  Walls (captcha / verify / create_account / sign_in_failed) also show **Resume** after "Do this
  step in the tab, then Resume", plus **Skip this job**: it stops that record (`why: "user"`) and
  leaves the job Queued, never skipped or rejected on the server. Below, one line names the other
  walls ("It also stops here for: a CAPTCHA · creating an account · a sign-in that didn't work ·
  apply on a job board").
- **Running card (This page, Fill):** eyebrow "Applying", title "Filling page N", a progress bar,
  a page-by-page list (finished pages with a tick and their filled count, the current page with
  "k of n"), **Stop**, and the fixed line "It clicks Next for you. It never clicks Submit." 
- **Ready to submit:** a row with "Check before you submit" flags (the receipt flags from the
  record's last receipt post). Nothing to press in the panel; the user submits in the tab.
- **Confirmation watch:** for `ready` records, `chrome.tabs.onUpdated` (url change) on that tab →
  `classify`. On `confirmation`:
  1. the row shows "Marking applied in 8 s · Undo";
  2. after 8 s with no Undo → `POST /api/proposals/{proposalId}/companion-submitted` with
     `{confirmation: {host, path, text}}`, where `text` is the matched confirmation phrase only
     (≤300 chars, never page prose beyond it) → `applied`;
  3. Undo → back to `ready`, with a manual **Mark applied** button calling the same endpoint.
  A 409 (cap or skip list) shows the server's sentence through `failureNote`.
- **Timing:** `yourMs` accrues from park to Resume and from `readyAt` to confirmation.
- **Queue view rows outside the run:** unticked jobs stay in the list as "Queued · Not in this run".
- **Run finished:** a summary card above the remaining rows: Applied, Needs you, your time per job
  (median `yourMs`), run time; **Done** posts the run log and clears the summary. Applied jobs leave
  the queue (the next `loadQueue` no longer returns them); the remaining rows keep their reason.
- **Run log:** when no record is active (all applied, parked, ready or stopped) and the user
  presses **Done** (or every record is terminal), POST `/api/agent-runs`
  `{automation: "queued-run", outcome: "ok"|"partial", counts: {ready, needs_you, applied, stopped,
  median_run_s, median_your_s}, job_ids}` once per run.

**Step 1: Failing panel-harness tests:**
- the rows render each status word;
- Resume posts a `you`-source receipt, always calls the learn path (never for a textarea), shows the
  "Saved N answers" line, Undo restores the previous profile values, then re-drives;
- confirmation → nothing posted before 8 s (fake timers) → posted after; Undo within 8 s → nothing
  posted, Mark applied shows;
- the run log posts once with medians;
- no row ever shows a Submit control;
- Skip this job leaves the proposal `accepted` (no PATCH sent);
- unticked jobs render "Not in this run"; the finished summary shows the four numbers and Done
  posts the run log once.

**Step 2: Run.** Expected: FAIL.

**Step 3: Implement.**

Every new text-on-fill colour pair (e.g. Needs you on the warn tone) joins `_TEXT_PAIRS` in
`tests/test_extension_panel_contrast.py` (the panel's colours are the app's since 75408302).

**Step 4: Run** `pytest tests/test_extension_panel*.py tests/test_extension_panel_icons.py
tests/test_extension_panel_contrast.py tests/test_extension_status_roles.py -q`.
Expected: PASS.

**Step 5: Commit** `feat(companion): run list, Needs you with Resume, auto-mark after your Submit`.

**Phase 2 host wiring for a one-record run (planner, 2026-10-13, after the batch-5 review).** Task 19
is Phase 3, but a one-job run in the CURRENT tab needs its driver deps now. Task 20 (one-job parts)
owns them, in `extension/panel/actions/run.js` (created here, extended by Task 19 later):
- `openTab(url, stop)`: for a run started on the current tab, returns that tab WITHOUT navigating
  when it is on the same posting (`samePosting`, or the backend's job match — a user part-way through
  the form, e.g. on /apply/step2, keeps their progress), else `chrome.tabs.update` and resolves once
  the page is readable, honouring `stop`. The driver records the hosts it reaches itself.
- `fill`: pinned to `record.tabId`, using the record's job and application, forwarding `opts.limits`
  as runFill's `options.limits`, and `cancelled: () => cancelled(record)` NOT tied to the panel's tab
  generation.
- `tabBroadcast`: `ask("page_broadcast", {tabId, message, frameId})` (frameId at the top level).
- Stop: sets the flag `cancelled(record)` reads AND sends `fill_cancel` to `record.tabId`.
- `onTab` and generation changes do NOT end or cancel a run (today `onTab` sends fill_cancel to the
  tab being left, panel.js ~2973-2985; the panel fill is tied to the generation, actions/fill.js
  ~435-441); `withFlowOrigin`/`flowFor` vouch for the run tab, not only `card.tabId`.
- Run tabs bind through their run record (design Part 6): for a tab with a live run record, the card,
  Resume's receipt and the fill facts take the job and application from the record, not from
  `restoreSession` (whose origin/tenant guard drops the job after a cross-origin Apply); optionally
  rewrite that tab's `widget.sessions` entry from the record at each page boundary.
- Copy and a Resume/Skip rule for every driver `why`: sign_in_yourself, sign_in_failed, posting,
  unknown_page, already_applied, moved_away, loop ("go to the next page yourself, then Resume"),
  step_limit (no Resume), no_change, open_questions, captcha, create_account, verify, board_native,
  bad_link, closed, error, user; status `confirming` reads "Marking applied".

### Task 20a: Job step: Apply and Queue

Design "Job step buttons". With full automation on, the Job step's footer primary becomes **Apply**,
with **Queue** beside it; with it off, **Save job** exactly as today.

**Files:**
- Modify: `extension/panel/actions/job.js` (`addJob` stays; new `queueJob`, `applyJob`)
- Modify: `extension/panel/actions.js` (roster bindings), `extension/panel/panel.js` (`renderFoot`'s
  Job-stage primary; `card.settings` must carry `full_automation`: read
  `GET /api/settings/auto-apply` in `loadContext` once per bind, or reuse Task 19's read)
- Modify: `extension/panel/actions/run.js` (`startRun` accepts a one-record run in the CURRENT tab)
- Test: `backend/tests/test_extension_panel_job.py`, `backend/tests/test_extension_panel_run.py`

**Behaviour:**
- **Queue:** `addJob` (save, extract and score as today), then `POST /api/proposals` with `{job_id,
  fit}` built like `frontend/lib/api.ts` `promoteJobToAgentQueue` (chosen base = the Job step's pick;
  scores from the panel's `card.scores`), then `PATCH /api/proposals/{id}` with
  `{status: "accepted", consent: {channel: "companion"}}` (Task 9 adds the channel). The note says
  "Queued. Apply to queued will pick it up."
- **Apply:** Queue, then resume readiness by the same rules as the Queue view's rows (Task 19)
  for this one job: a PDF is ready → go; a draft without a PDF → Create PDF; nothing tailored and no
  open custom session → Quick tailor with the picked base; an open custom session → stop with "You're
  tailoring this job in Maestro. Finish it, then press Apply." (never quick-tailor over it). Then a
  one-record run whose `openTab` reuses the current tab: when the page is a posting on a job board
  and the job has an `apply_url`, navigate this tab to it (`chrome.tabs.update(tabId, {url})`); when
  the page is already the employer's form, start at classify.
- Hidden when the job is already applied, or its proposal is already queued (then the footer shows
  **Apply** only, which skips the queue step).
- **Canvas details:** with full automation off, Save job carries one line, "Turn on full automation
  in Settings to apply from here." With it on, the base picker's card reads "Apply with this
  resume", Apply and Queue sit side by side, one line says "Apply fills every page here and stops
  before Submit.", and below are **Update scores** and **Tailor first, then apply** (opens today's
  Resume step instead of applying). The open-custom-session state ("Finish tailoring first") offers
  **Finish in Maestro CS** (the web app's tailoring session) and **Apply with the base resume**
  (`POST /api/applications/from-base` then render, then the one-job run; the open session is left
  untouched).
- **A base resume is never named without its square** (SYSTEM.md §6 `inv-resume-color-identity`,
  INTERNALS 265-269): the "Apply with this resume" card and every line naming a base keep
  `swatch(color_hue)`, built like the Job step's base rows (`stages/job.js` `rowText({node, attach,
  swatch})`, ~286).

**Step 1: Failing panel-harness tests:**
- full automation off → only Save job;
- on → Apply primary and Queue secondary;
- Queue posts the proposal then the accepted PATCH with channel `companion`;
- Apply with an open custom session never calls quick-tailor and shows the finish-first note;
- Apply on a board posting with `apply_url` navigates the current tab and drives one record;
- "Apply with the base resume" never calls quick-tailor and leaves the open session `open`;
- no new tab or window opens for Apply.

**Step 2: Run.** Expected: FAIL. **Step 3: Implement.** **Step 4: Run**
`pytest tests/test_extension_panel*.py -q`. Expected: PASS.

**Step 5: Commit** `feat(companion): Apply and Queue on the Job step`.

### Task 20b: Learn from the user's fix

Design Part 8.2. When a parked field is fixed by hand and the user presses Resume, teach the recipe
book the move the user used, and note techniques the engine lacks.

**Files:**
- Modify: `extension/content/recipes.js` (a gesture watcher per field: `watch(fid)` / `report(fid)`)
- Modify: `extension/content/agent.js` (`fill_watch {fids}` starts watching parked fields;
  `fill_watch_report {fids}` returns `{fid: {family, site, gestures: [...]}}`), `extension/sw.js`
  (`BROADCASTABLE` += both, pin updated; the panel→sw handler `fill_gaps`, NOT broadcastable)
- Modify: `extension/shared/recipe-book.js` (`recordDemonstration(lesson)`: a known move enters at
  `probation` for that site only; never `trusted` from one demonstration; a family lesson needs the
  usual two sites)
- Modify: `extension/panel/actions/run.js` (on park: `fill_watch`; on Resume: `fill_watch_report`,
  then for each field now holding a value (from the receipt's `fromEdits`): a known move →
  `recipes.recordDemonstration`; no known move → POST `/api/autofill/gaps` with
  `outcome: "missing_technique"`; every fixed field → a `user_fixed` gap; every run's leftover
  `cannot_operate`/`unconfirmed` fields → their gap rows. Gap posts go through a new sw handler
  `fill_gaps` (POST `/api/autofill/gaps`, keys whitelisted to family/host/shape/outcome), gated
  like `telemetry`/`fill_trace`: it posts only when `telemetryEnabled === true` (off by default;
  Options › Keep a fill log).)
- Test: `backend/tests/browser/test_recipes.py`, `backend/tests/test_extension_panel_run.py`

**Gesture vocabulary** (value-free; the engine's own axes from `recipe-book.js` `AXES`):
`open:press` (a pointer press opened it), `open:keys` (ArrowDown, Enter or Space opened it),
`search:enter` (typing followed by Enter committed it), `search:debounce` (typing, then a pause,
then a pointer pick). Record event TYPES and key NAMES from a fixed allowlist (`ArrowDown`, `ArrowUp`,
`Enter`, `Space`, `Tab`, `Escape`) only, never `key` for printable characters and never `value`.

**Step 1: Failing tests:**
- browser: on `workday_listbox.html` and `react_select.html`, simulate the user opening with the
  keyboard and picking → `report` says `open:keys`; typing "Spr" then Enter → `search:enter`; the
  report contains no typed character (assert "S", "p" and "r" never appear in the JSON);
- recipe-book (node): one demonstration → `probation` at `s:<site>`, not trusted; a second
  demonstration on another site → the family is `trusted` (same lifecycle as engine wins);
- panel: Resume after a hand fix posts a `user_fixed` gap and records the demonstration; with
  the fill log off (stored `{}`, `false`, `"true"`, `1`, as
  `test_telemetry_is_off_until_the_user_turns_it_on` does) the sw posts no gap, and the
  demonstration is STILL recorded: the recipe book is local and was never gated by the fill log
  (planner's call 2026-10-13; gating it would leave Learn from the fix off for nearly everyone).
  The panel harness `SETTINGS_REPLY` has `telemetryEnabled: True`; sw tests use `OPTED_IN`.

**Step 2: Run.** Expected: FAIL. **Step 3: Implement.** **Step 4: Run**
`pytest tests/browser/test_recipes.py tests/test_extension_panel_run.py tests/test_extension_sw_router.py -q`.
Expected: PASS.

**Step 5: Commit** `feat(companion): a hand fix teaches the recipe book; misses join the known-gaps list`.

### Task 20c: A remembered answer that names this job stays with this job (added 2026-10-13)

Task 20 saves every answer typed before Resume to the `custom` saved answers
(`panel/actions/pause.js` `learnAnswer` → `withCustomAnswer`), and /map offers each one as a fact
(`autofill_catalog._custom`, "saved answer to: <question>"), matched by meaning. Some answers only
hold for the job they were given on: "Are you willing to relocate to Austin?", "Have you worked at
Acme before?". Reused at the next company, they would be wrong while looking like a normal filled
answer. So a saved answer whose question names THIS job's company or city is scoped to it.

**Files:**
- Modify: `extension/panel/actions/pause.js` (`withCustomAnswer(custom, question, answer, job)`:
  when the normalized question contains the job's company, or the city of its location (each ≥ 3
  characters), the row gets `only_for: "<that company or city>"`; `learnAnswer` passes the card's
  job `{company, location}`)
- Modify: `backend/app/services/autofill_catalog.py` (`build(..., location=None)`; `_custom(out,
  custom, company, location)`: a row with `only_for` is offered only when `only_for` is contained,
  case-insensitively, in this job's company or location; with no job it is never offered. A row
  keeps its slot `custom.<i>` either way, so the indices other rows use don't move)
- Modify: `backend/app/routers/autofill.py` (`_facts`: pass `location=job.location if job else None`
  beside `company=`)
- Modify: `frontend/components/settings/autofill-section.tsx` ("Your own questions": a row with
  `only_for` shows one muted line, "Only for <only_for>"; editing a row keeps `only_for`)
- Test: `backend/tests/test_autofill_catalog.py`, `backend/tests/test_extension_panel_fill.py`
  (it covers `withCustomAnswer` today), `backend/tests/test_frontend_settings_cards.py`

**Step 1: Failing tests:**
```python
def test_a_saved_answer_naming_a_company_is_offered_only_for_that_company():
    profile = {"custom": [
        {"question": "Have you worked at Acme before?", "answer": "No", "only_for": "Acme"},
        {"question": "Is a relative a government official?", "answer": "No"}]}
    at_acme = cat.build(profile, [], [], company="Acme Corp")
    at_globex = cat.build(profile, [], [], company="Globex")
    assert "custom.0" in at_acme and "custom.1" in at_acme
    assert "custom.0" not in at_globex and "custom.1" in at_globex
    assert "custom.0" not in cat.build(profile, [], [])          # no job: a scoped answer is never offered


def test_a_saved_answer_naming_a_city_is_offered_only_there():
    profile = {"custom": [{"question": "Willing to relocate to Austin?", "answer": "Yes", "only_for": "Austin"}]}
    assert "custom.0" in cat.build(profile, [], [], company="Globex", location="Austin, TX")
    assert "custom.0" not in cat.build(profile, [], [], company="Globex", location="Denver, CO")
```
In the panel test: `withCustomAnswer([], "Have you worked at Acme before?", "No", {company: "Acme",
location: "Austin, TX"})` gives `only_for: "Acme"`; "Willing to relocate to Austin?" gives
`only_for: "Austin"`; "Is a relative a government official?" gives no `only_for`; updating an
existing row keeps its `only_for`. In the settings test: the card renders "Only for" for a scoped
row.

**Step 2: Run** `pytest tests/test_autofill_catalog.py -k saved_answer tests/test_extension_panel_fill.py
tests/test_frontend_settings_cards.py -q`. Expected: FAIL. **Step 3: Implement.** **Step 4: Run**
the same files in full, plus `tests/test_autofill_fill_router.py`. Expected: PASS.
**Step 5: Commit** `feat(autofill): an answer that names a job's company or city is kept for that job`.

Dates ("Can you start on 1 November?") are not scoped in v1: the live check says whether they need to be.

### Task 21 (conditional): `/api/autofill/page` for unclear buttons

Build only if the owner's live check (Task 23) shows "Ready to submit" landing on pages that are
really mid-wizard because the advance button was unclear. Shape it like `/api/autofill/step`
(`schemas/autofill_fill.py:184`):
- request `{buttons: [{id, text}], heading, step_texts}` (button texts only, no page prose);
- response `{choice: id | "none"}`.

The server refuses any id whose text the Python twin of `sortButton` calls `submit` (write that twin
and a parity test, as `test_both_copies_of_the_policy_deny_list_stay_identical` does for policy).
The runner sends only `unclear` buttons, and only when there is no `submit` button on the page.
Ask the planner before starting.

---

## Phase 4 — Rules, docs, verification

### Task 22: Change the rules on purpose, and document

**Files:**
- `SYSTEM.md`: first groom to make room (`python3 scripts/check_system_md.py` must pass; never drop a
  rule-bearing clause), then:
  - §6 `inv-policy-deny-list-single-source` and `inv-eeo-standing-consent`: "Next/Submit stay the
    user's" becomes "Submit stays the user's at every setting; Next is clicked only by
    `page_advance` during a queued run with full automation on";
  - `inv-job-site-password-local`: the Companion route, top-frame typing, never a model;
  - `inv-autofill-telemetry-no-values`: the known-gaps table (value-free, posted only while the fill log is on
    (`telemetryEnabled === true`, default off), cleared by `DELETE /telemetry`) and the gesture report (event types and allowlisted key names only);
  - `inv-auto-consent-gated`: the `companion` channel and `companion-submitted`;
  - §7 Chrome extension + Guided fill: the queued run, per-tab memory, the Screening answers dial;
  - update pins in `.system_md_enforcement.json` for any new symbols named in §6.
- `extension/INTERNALS.md` ("never advances", "Mark applied is never automatic", session key notes,
  a new "Queued run" section), `extension/README.md:60`, `extension/shared/policy.js` header,
  `backend/app/schemas/eeo_consent.py:53-54` wording, CONTRIBUTING refusal #1 (the queued run is
  queued-only, capped, Submit stays human).
- `docs/plans/2026-10-05-full-automation-design.md`: one line under Owner decisions pointing to the
  queued-run design.
- `docs/entities/others.md`: the Form-filling section names the answer level; the auto-apply
  section names `prepare_queued`.
- A coverage table in `extension/README.md`: Workday / Greenhouse / Lever / Ashby / iCIMS → deep,
  generic or untested, from Task 14's fixtures.
- `CHANGELOG.md`: the queued run; the dial (and that installs with the old switch off now default to
  Backed by your history); per-tab memory; `apply_url`.

**Verify:** `python3 scripts/check_system_md.py` passes. Commit
`docs: the Companion's queued run — Submit stays yours, Next during a queued run`.

### Task 23: Full gate and the owner's live check

**Step 1:** From `backend/`: `pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile`. Expected:
all pass. Report the count.

**Step 2:** Frontend: `cd frontend && npx tsc --noEmit && npm run lint`.

**Step 3:** Slop ratchet, EVERY surface touched, named in the claim:
`python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check backend`, `... check frontend`,
`... check extension` (from the repo root). Re-baseline `complexity_hotspots` with a reason if only
that moved.

**Step 4:** Fresh stack per SYSTEM.md §9: uvicorn on a free port with its own SQLite file, plus
`API_PROXY_BACKEND=... npm run dev`. Check the Settings dial and the auto-apply switch in the
browser pane at 1280 and 1024 widths. Never verify against the docker-compose stack.

**Step 5: Owner live check** (the owner does this; write the checklist into the PR description):
load the unpacked extension; in its Options tick **Keep a fill log** (off by default; without it
no run trace or known-gap row is stored, and `fill_trace.py last|report` has nothing to compare);
full automation on; queue five real jobs across Workday, Greenhouse,
Lever, Ashby and iCIMS; Apply to queued. For each: did it reach the real review page and stop?
Was Submit ever clicked (must be no)? What parked, and why? Seconds of your time per job (from the
run log). Then decide on Task 21.

---

## Spike result

Measured 2026-10-11 on the owner's Mac (Playwright's Chromium, launched standalone with no automation
attached; tabs switched over the DevTools HTTP endpoints; 5 attempts per cell; median of successes).

| Fixture | Front tab | Background tab (immediate) |
|---|---|---|
| workday_text.html | 5/5, 309 ms | 5/5, 2000 ms (6.5×) |
| workday_listbox.html | 5/5, 1681 ms | **0/5**: "could not explore Degree"; requestAnimationFrame never fired within 1 s |
| workday_date.html | 5/5, 619 ms | 5/5, 4001 ms (6.5×) |

The 6-minute case (Chrome's intensive throttling) did not complete: a harness quirk left a lone
fixture tab in front. Task 1a fixes the harness and measures it.

Findings that change the design:
- **Any Playwright attachment makes every tab report `visible`** (launch or `connect_over_cdp`, with
  focus emulation off and no viewport). Background-tab measurements must run unattached, as
  `scripts/spike_background_fill.py` does. Worth a §12 gotcha (Task 22).
- **A covered window hides every tab in it** (macOS occlusion), the active one included, so a run
  window behind another app behaves like a background tab.
- **Rule outcome: take turns.** Background is far over 1.5×, and dropdowns fail outright. The runner
  fills ONE tab at a time, made active in the run window (`chrome.tabs.update(tabId, {active: true})`
  inside the run window only); others wait or sit at Ready to submit. `LIMITS.parallel` defaults to
  1. Owner decision (B): Task 1a makes the engine work in hidden and covered tabs; only once Task
  1a's acceptance passes may `parallel` go above 1 (Task 19 reads `ns.queueRun.LIMITS.parallel`).

**After Task 1a** (measured 2026-10-11, same setup, full run including the 6-minute case):

| Fixture | Front tab | Background (immediate) | Background after 6 min |
|---|---|---|---|
| workday_text.html | 5/5, 308 ms | 5/5, 306 ms | 5/5, 306 ms |
| workday_listbox.html | 5/5, 1670 ms | 5/5, 2644 ms (1.6×) | 5/5, 2635 ms (1.6×) |
| workday_date.html | 5/5, 619 ms | 5/5, 615 ms | 5/5, 615 ms |

**Acceptance passed** (5/5 everywhere, every median within 2× of the front tab). So: Task 17 sets
`HIDDEN_TABS_OK = true` and `LIMITS.parallel` defaults to **3** (the 1 to 5 control shows); the
"Keep the run window visible" pause in Task 19 is not built. The runner still never focuses the run
window. Cost to watch: the hidden-tab wait is a MessageChannel loop, so a background tab keeps one
CPU core busy while it waits; acceptable for a fill's length, and the run log's timings will show
if it hurts.
