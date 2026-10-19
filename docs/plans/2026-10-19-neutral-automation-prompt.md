# Neutral Automation Prompt Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the Automations page's five per-agent-app prompt versions with one app-neutral,
adaptive prompt per card, and make three skills adapt to the run instead of assuming it.

**Architecture:** The backend builds each card's finished `prompt` (one of two neutral wrappers +
the skill body) and drops the `apps` list; the page copies `card.prompt` with no picker. Skill
files change only in wording. Design: `docs/plans/2026-10-19-neutral-automation-prompt-design.md`.

**Tech Stack:** FastAPI + pydantic (backend), Next.js/React + TanStack Query (frontend), pytest.
The frontend has no test runner: its behavior is pinned from source in
`backend/tests/test_frontend_automations.py`.

**Before you start:** read `SYSTEM.md`. Test from `backend/` with the worktree venv (create once:
`python -m venv .venv && .venv/bin/python -m pip install -e ".[dev,mcp]"`). Single files run
plain; the full suite always runs with `-n auto --dist loadfile`. Never start the Docker stack.

**Goal check for every task:** the copied text must hardcode only the job's goal and a short
decision ladder. No agent app, browser product or scheduling mechanism is named in a wrapper,
and guard rails (no submit without a yes, accepted queue only) never loosen. If a step seems to
need an app-specific sentence, stop and ask instead.

---

### Task 1: Backend builds one neutral prompt per card

**Files:**
- Modify: `backend/app/services/automations.py`
- Test: `backend/tests/test_automations_service.py`, `backend/tests/test_automations_router.py`

**Step 1: Write the failing tests**

In `test_automations_service.py`, delete `test_scheduled_wrappers_leave_timing_to_the_user` and
`test_remote_only_apps_are_shown_but_unreachable` and put these in their place:

```python
def test_every_prompt_is_its_kinds_wrapper_then_its_body():
    for full_automation in (False, True):
        for card in automations.catalog(full_automation=full_automation).cards:
            wrapper = (automations.SCHEDULED_WRAPPER if card.kind == "scheduled"
                       else automations.ATTENDED_WRAPPER)
            assert card.prompt == f"{wrapper}\n\n{card.body}", card.id


def test_the_scheduled_wrapper_asks_when_then_adapts():
    wrapper = automations.SCHEDULED_WRAPPER
    for phrase in ("how often and when", "built into this app", "available on this computer",
                   "where I could run it on a schedule instead", "offer to run it once now",
                   "Schedule only the job below"):
        assert phrase in wrapper, phrase
    assert "how often" not in automations.ATTENDED_WRAPPER


@pytest.mark.parametrize("name", ["SCHEDULED_WRAPPER", "ATTENDED_WRAPPER"])
def test_each_wrapper_checks_it_can_reach_maestro(name):
    assert "tell me to connect you first and stop" in getattr(automations, name)


# Agent apps change weekly; a wrapper that names one, or a scheduler, goes stale.
_APP_SPECIFIC = ("claude", "codex", "chatgpt", "openai", "anthropic", "cursor", "gemini",
                 "cron", "launchd", "task scheduler", "systemd", "playwright")


@pytest.mark.parametrize("name", ["SCHEDULED_WRAPPER", "ATTENDED_WRAPPER"])
def test_wrappers_name_no_agent_app_or_scheduler(name):
    text = getattr(automations, name).lower()
    assert [word for word in _APP_SPECIFIC if word in text] == []


def test_the_catalog_carries_no_agent_apps():
    assert set(automations.AutomationCatalog.model_fields) == {"cards"}
```

In `test_catalog_models_are_frozen`, replace the last two lines with:

```python
    with pytest.raises(ValidationError):
        card.prompt = "changed"
```

In `test_automations_router.py`, replace `test_catalog_endpoint_shape` with:

```python
def test_catalog_endpoint_shape():
    r = client.get("/api/automations")
    assert r.status_code == 200
    data = r.json()
    assert set(data) == {"cards"}
    card = data["cards"][0]
    assert set(card) == {"id", "title", "summary", "kind", "needs", "never", "body", "prompt"}
```

and at the end of `test_catalog_apply_kind_tracks_full_automation` add:

```python
    wrapper = (automations.SCHEDULED_WRAPPER if expected_kind == "scheduled"
               else automations.ATTENDED_WRAPPER)
    assert apply["prompt"].startswith(wrapper)
```

**Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/test_automations_service.py tests/test_automations_router.py -q`
Expected: FAIL with `AttributeError: ... has no attribute 'SCHEDULED_WRAPPER'` and the shape asserts.

**Step 3: Implement**

In `backend/app/services/automations.py`:

1. Module docstring, last sentence: keep "Nothing about the user is inserted…", and add: "Every
   card's `prompt` is one app-neutral wrapper plus its body
   (docs/plans/2026-10-19-neutral-automation-prompt-design.md)."
2. Replace the two comment lines above `Kind` with:
   ```python
   # `scheduled` cards open with SCHEDULED_WRAPPER (ask when, then use whatever scheduler the
   # agent can reach); `attended` and `custom` cards open with ATTENDED_WRAPPER (do it now).
   ```
3. Delete `class AgentApp`, `_ASK`, `_REMOTE` and the whole `APPS` tuple. Add:
   ```python
   # Neither wrapper names an agent app or a scheduling mechanism: apps change weekly, so the
   # agent works out what it can do and says plainly when it can't.
   SCHEDULED_WRAPPER = (
       "Using your Maestro Career Studio connection, set the job below up to run on a schedule. "
       "First ask me how often and when. Then use whatever scheduling you can reach: one built "
       "into this app if it has one, otherwise one available on this computer. If you can't "
       "schedule it from here, tell me plainly, say where I could run it on a schedule instead, "
       "and offer to run it once now. Schedule only the job below, not this paragraph. If you "
       "can't reach Maestro's tools at all, tell me to connect you first and stop."
   )
   ATTENDED_WRAPPER = (
       "Using your Maestro Career Studio connection, do the job below with me now. If you can't "
       "reach Maestro's tools, tell me to connect you first and stop."
   )


   def _prompt(kind: Kind, body: str) -> str:
       """The text Copy puts on the clipboard: the kind's wrapper, then the skill."""
       wrapper = SCHEDULED_WRAPPER if kind == "scheduled" else ATTENDED_WRAPPER
       return f"{wrapper}\n\n{body}"
   ```
4. `AutomationCard` gains `prompt: str` after `body`. `AutomationCatalog` becomes
   `cards: list[AutomationCard]` only.
5. In `load_cards()` build each card with `prompt=_prompt(metas[skill_id].kind, body)`, holding
   the body in a local so `_card_body` runs once per card:
   ```python
   cards = []
   for skill_id in CARD_ORDER:
       meta = metas[skill_id]
       body = _card_body(skill_id, bodies, metas)
       cards.append(AutomationCard(
           id=skill_id, title=meta.title, summary=meta.summary, kind=meta.kind,
           needs=tuple(meta.needs), never=meta.never, body=body,
           prompt=_prompt(meta.kind, body)))
   cards = tuple(cards)
   ```
   Same in `_alternate()`: `body = _card_body(...)`, then `body=body, prompt=_prompt(meta.kind, body)`.
6. In `catalog()`, the attended Apply copy must refresh its prompt with its kind:
   ```python
   kind = apply_kind()
   cards.append(card.model_copy(update={"kind": kind, "prompt": _prompt(kind, card.body)}))
   ```
   and return `AutomationCatalog(cards=cards)`. Update its docstring to "The cards in designed
   order, each with its finished prompt."

`routers/automations.py` returns the catalog model, so it needs no change; confirm with
`grep -n apps backend/app/routers/automations.py` (expect nothing).

**Step 4: Run them to see them pass**

Run: `.venv/bin/python -m pytest tests/test_automations_service.py tests/test_automations_router.py tests/test_full_automation_setting.py -q`
Expected: all PASS.

**Step 5: Commit**

```bash
git add backend/app/services/automations.py backend/tests/test_automations_service.py backend/tests/test_automations_router.py
git commit -m "feat(automations): one app-neutral prompt per card, built in the backend"
```

---

### Task 2: The page copies `card.prompt`, no picker

**Files:**
- Delete: `frontend/components/automations/app-picker.tsx`
- Modify: `frontend/app/automations/page.tsx`, `frontend/components/automations/automation-card.tsx`,
  `frontend/lib/automations.ts`, `frontend/lib/types.ts:2200-2216`
- Test: `backend/tests/test_frontend_automations.py`

**Step 1: Update the source pins (failing)**

In `test_frontend_automations.py`:
- Module docstring: replace "for the chosen agent app" with "for any connected agent app", and
  "Copy is off for an app Maestro can't reach (and says why)" with "Copy is always on".
- Delete `_STORAGE` (only the deleted test below used it).
- Replace `test_copy_is_off_for_an_unreachable_app_and_says_why` with:
  ```python
  def test_one_prompt_for_every_agent_app():
      assert not (_FRONTEND / "components/automations/app-picker.tsx").exists()
      for src in (_PAGE, _CARD, _LIB):
          for word in ("AppPicker", "reachable", "AgentApp", "APP_STORE_KEY", "promptFor"):
              assert word not in src, word
      assert "focusableWhenDisabled" not in _CARD
  ```
- In `test_the_page_reads_the_catalog_and_points_at_the_connect_guide`, add:
  `assert "Apps that run only in a browser can't reach it yet." in _PAGE`
- In `test_the_card_copy`, change the first assert to
  `assert "Prompt copied. Paste it into your agent app." in _CARD`.
- Replace `test_a_scheduled_card_gets_the_wrapper_that_asks_when_to_run` with:
  ```python
  def test_the_card_copies_the_prompt_the_backend_built():
      assert "const text = card.prompt;" in _CARD
  ```
- In `test_no_cadence_picker_and_nothing_about_the_user_in_the_prompt`, delete the comment
  "promptFor reads the card and the app, nothing else." (keep the `profile` assert).
- Delete `test_the_remembered_app_is_best_effort`.

Run: `.venv/bin/python -m pytest tests/test_frontend_automations.py -q`
Expected: FAIL on the new pins.

**Step 2: Implement**

- `git rm frontend/components/automations/app-picker.tsx`
- `frontend/lib/types.ts`: add `prompt: string;` after `body: string;` in `AutomationCard`;
  delete `AgentApp`; `export type AutomationCatalog = { cards: AutomationCard[] };`
- `frontend/lib/automations.ts`: delete `promptFor` (with its doc comment), `APP_STORE_KEY`,
  `parseStoredApp`, `serializeApp` and their comment; the import becomes
  `import type { AutomationCard, AutomationNeed } from "@/lib/types";` — then drop
  `AutomationCard` from it if nothing else uses it.
- `automation-card.tsx`:
  - Drop the `app` and `disabledReasonId` props (and their types/doc lines) and the
    `AgentApp`/`promptFor` imports.
  - `const text = card.prompt;`
  - Success toast: `toast.success("Prompt copied. Paste it into your agent app.");`
  - The Copy `<Button>` loses `disabled`, `focusableWhenDisabled`, the `data-disabled` class and
    `aria-describedby` (and the comment about them).
  - Component doc: "…and the prompt to copy. A failed clipboard write opens the prompt so it can
    be selected."
- `page.tsx`:
  - Remove `AppPicker`, `useLocalStorageState`, the `@/lib/automations` import block, `useId`,
    `useState`, `noteId`, `DEFAULT_APP`, `storedApp`, `picked`, `wanted`, `app`, and the whole
    picker `<div className="flex flex-col">…</div>` (including the `aria-live` note).
  - Subtitle: `"Copy a prompt into any agent app connected to Maestro. It asks when to run, then does these jobs with Maestro."`
  - In BOTH connect-note branches, after the link add ` Apps that run only in a browser can't reach it yet.`
    as a separate sentence inside the same `<p>` (after `</NewTabLink>`).
  - `!data || !app ?` becomes `!data ?`.
  - `<AutomationCard … />` calls lose `app={app}` and `disabledReasonId={noteId}`.

**Step 3: Verify**

```bash
cd ../frontend && npm ci && npx tsc --noEmit && npm run lint
cd ../backend && .venv/bin/python -m pytest tests/test_frontend_automations.py tests/test_frontend_full_automation.py -q
```
Expected: no type or lint errors; tests PASS.

**Step 4: Commit**

```bash
git add -A frontend/ backend/tests/test_frontend_automations.py
git commit -m "feat(automations): drop the agent-app picker; Copy takes the card's prompt"
```

---

### Task 3: Make your own adapts any card, with no client-specific paths

**Files:**
- Modify: `backend/app/automations/skills/customize-job-skills/SKILL.md`
- Test: `backend/tests/test_automations_service.py` (`test_guardrails_survive_rewording` params)

**Step 1: Failing pins** — add to the `test_guardrails_survive_rewording` list:

```python
    pytest.param("customize-job-skills", "Adapting any ready-made automation",
                 id="custom-adapts-cards"),
    pytest.param("customize-job-skills", "keeps its own automation name",
                 id="custom-adapted-keeps-name"),
```

and a new test beside it:

```python
def test_make_your_own_names_no_client():
    custom = {c.id: c for c in automations.catalog().cards}["customize-job-skills"]
    assert custom.summary == (
        "Builds automations around you, or tunes any card above to your agent app and routine.")
    for word in ("Claude Code", "~/.claude", "/schedule"):
        assert word not in custom.body, word
```

Run: `.venv/bin/python -m pytest tests/test_automations_service.py -q -k "custom or rewording"` → FAIL.

**Step 2: Edit the skill**

- Frontmatter `description`: "Use when the user wants to adapt any ready-made Maestro CS
  automation to their agent app and routine, or create a new skill of their own around the app —
  batch tailoring, referral-first hunting, a weekly digest, anything the tools can do. Suggests
  ideas from what you know about the user and their data, asks a few questions, then builds it
  with whatever skill-making and scheduling this app and computer offer."
- `summary:` "Builds automations around you, or tunes any card above to your agent app and routine."
- Intro paragraph: "…either their own version of any ready-made skill (`job-hunt`,
  `mail-status`, `referral-pages`, `tailor-run`, `apply-session`; this repo:
  `backend/app/automations/skills/`, indexed at `docs/skills/README.md`), or something new…"
- Section 2: replace "The ready-made pair is always an option." with "Adapting any ready-made
  automation to this app and the user's routine is always an option."
- Section 4, replace the two bullets "Write it with the client's own…" and "For a schedule…" with:
  ```markdown
  - Write it with this app's own way of making skills if it has one; otherwise save it where
    this app loads skills from. An app without skills gets a paste-ready prompt instead.
  - For a schedule, use a scheduler built into this app if it has one, otherwise one available
    on this computer. If neither works from here, say so plainly, tell the user where they
    could run it on a schedule instead, and hand over the prompt to run.
  - An adapted ready-made automation keeps its steps, its guard rails and its own automation
    name in `record_run`, so its runs still show on its card; change only what fits this app
    and routine (sources, timing, where alerts go).
  ```

**Step 3:** rerun the Step 1 command → PASS. **Step 4: Commit**
`git commit -am "feat(automations): Make your own adapts any card and names no client"`

---

### Task 4: Apply runs reach the user however the run can

**Files:**
- Modify: `backend/app/automations/skills/apply-auto/SKILL.md` (step 7),
  `backend/app/automations/skills/apply-session/SKILL.md` (step 5)
- Test: `backend/tests/test_automations_service.py`

**Step 1: Failing pins**

Add to `test_the_automatic_apply_guardrails`'s list:
```python
    "Ask the user through whatever this run can reach",
    "If nobody can be reached now, leave it: it waits in Needs you.",
```
Add to `test_guardrails_survive_rewording`'s list:
```python
    pytest.param("apply-session", "If nobody can answer now, don't submit",
                 id="apply-session-no-answer-no-submit"),
```
Run: `.venv/bin/python -m pytest tests/test_automations_service.py -q` → FAIL.

**Step 2: Edit**

`apply-auto` step 7, first line becomes:
```markdown
7. **Everything else.** Call `report_failure` with the reason and move on.
   Ask the user through whatever this run can reach: this chat, or a channel the user set up
   for these runs. If nobody can be reached now, leave it: it waits in Needs you.
   If the user says yes:
```
(the yes path lines below stay exactly as they are — `test_the_user_yes_path_records_consent_before_submitting` pins their order).

`apply-session` step 5: after the `base_country` sentence and before "Only after their yes for
*this* application:", add:
```markdown
   Ask in this chat, or through a channel the user set up for these runs. If nobody can answer
   now, don't submit: `report_failure` with the reason `waiting for your yes` and move on to the
   next one; it waits in Needs you.
```

**Step 3:** rerun → PASS (including the ordering test). **Step 4: Commit**
`git commit -am "feat(automations): apply runs ask where the user can answer, else park"`

---

### Task 5: Lookback covers the time since the last run

**Files:**
- Modify: `backend/app/automations/skills/mail-status/SKILL.md` (step 1),
  `backend/app/automations/skills/job-hunt/SKILL.md` (step 2)
- Test: `backend/tests/test_automations_service.py`

**Step 1: Failing pins** — add to `test_guardrails_survive_rewording`:
```python
    pytest.param("mail-status", "at least the time since this automation last ran",
                 id="mail-lookback-since-last-run"),
    pytest.param("job-hunt", "at least the time since this automation last ran",
                 id="hunt-lookback-since-last-run"),
```
Run → FAIL.

**Step 2: Edit**

`mail-status` step 1:
```markdown
1. **Window.** Read job-related mail from at least the time since this automation last ran
   (its schedule's interval), or the last 7 days on a first run or when you can't tell. A
   window the user gave wins. Repeat runs are safe: statuses only move forward and notes are
   not duplicated.
```
`job-hunt` step 2, first sentence:
```markdown
2. **Source.** Pull postings from at least the time since this automation last ran (its
   schedule's interval), or roughly the last week on a first run or when you can't tell, from
   whatever job sources you can reach — job-board tools, scrapers, the brief's referral
   careers pages, or plain browsing. …
```
(rest of the step unchanged).

**Step 3:** rerun → PASS. **Step 4: Commit**
`git commit -am "feat(automations): mail and hunt look back to the last run, not a fixed week"`

---

### Task 6: Docs and changelog

**Files:**
- Modify: `docs/entities/others.md:1058-1072`, `docs/frontend-conventions.md:1492-1494`,
  `docs/skills/README.md:19`, `CHANGELOG.md` (Unreleased), `SYSTEM.md` only if
  `grep -n "Claude Desktop\|agent apps" SYSTEM.md docs/agent-surfaces.md` finds a stale line.

**Step 1: Edit**

- `others.md` Automations page bullet: replace "returns the cards and the **agent apps**: …
  works via Any MCP agent). **Copy prompt** puts the app's wrapper plus the skill body on the
  clipboard. Maestro runs NO scheduler: a scheduled card's wrapper has the agent ask the user
  when to run." with: "returns the cards, each with its finished `prompt`: the skill body under
  one of two app-neutral wrappers. A scheduled card's wrapper has the agent ask when, then use a
  scheduler it can reach (its app's, else the computer's) or say plainly where the job could run
  instead; an attended or custom card's wrapper does the job now. Both stop when Maestro's tools
  are unreachable, and neither names an agent app or scheduling mechanism
  (`test_wrappers_name_no_agent_app_or_scheduler`). **Copy prompt** copies it and is always on;
  Maestro runs NO scheduler." Keep the rest of the bullet.
- `frontend-conventions.md`: "calls the app a user runs a prompt in an **agent app** (Claude
  Desktop, Codex, Any MCP agent)" → "calls the app a user runs a prompt in an **agent app**,
  never naming one".
- `docs/skills/README.md` `customize-job-skills` row: "Adapts any ready-made automation to your
  agent app and routine, or builds something new (batch tailoring, referral-first hunting, a
  weekly digest…) from what your agent knows about you and your data in the app, with whatever
  skill-making and scheduling your app and computer offer."
- `CHANGELOG.md`, under `## [Unreleased]`:
  ```markdown
  ### Changed

  - **The Automations page has one prompt per card, for any agent app.** The agent-app picker is
    gone. The copied prompt asks when to run, then uses whatever scheduler your agent app or
    computer has, and tells you plainly where else it could run when it has none.
  - **Make your own can now adapt any automation** to your agent app and routine.
  - **Apply runs ask wherever you can answer,** and leave a job in Needs you when nobody can.
  - **Mail status and Job hunt look back to their last run** instead of a fixed week.
  ```

**Step 2:** `python scripts/check_system_md.py` (from repo root) → clean.

**Step 3: Commit** `git commit -am "docs: one neutral automation prompt per card"`

---

### Task 7: Full verification

1. `cd backend && .venv/bin/python -m pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile` → all pass.
2. `cd frontend && npx tsc --noEmit && npm run lint` → clean.
3. Fresh stack on spare ports (recipe: memory `worktree-verification-recipe`; never the live app
   or Docker). Open `/automations` in the browser pane and check: no picker; subtitle and
   connect note read as above; Copy works on every card; Show prompt starts with the scheduled
   wrapper on Job hunt and the attended one on Apply session and Make your own; with full
   automation On the Apply card's prompt starts with the scheduled wrapper.
4. Report what passed with the output, and anything not checked.
