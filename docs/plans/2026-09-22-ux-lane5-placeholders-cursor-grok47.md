# UX follow-ups, lane 5: Placeholders (wave 2) — handoff to Cursor CLI / Grok 4.7

**Target agent/model:** Cursor CLI (`agent`), **Grok 4.7** (xhigh). If your session runs a
different model, stop and say so: the review tier depends on it.
**Tasks:** 17 of `docs/plans/2026-09-22-ux-followups.md`, in that order.
**Branch:** `grok/ux-lane5-placeholders` (from `claude/ux-followups` at `BASE_SHA_PLACEHOLDER`).
**Worktree:** `/Users/ajeyds/Projects/maestro-ux-lanes/lane5-placeholders` (dependencies are installed). Work only there.
**Planner/reviewer:** Claude (Opus 5.5). It reviews and merges this branch; you never merge.

## Goal Card

**Goal.** Close every gap that the honest-studio reviews and browser pass found,
plus the leftovers from the first UX review. The app must never mislead the user
about unsaved work. It must be keyboard- and contrast-accessible wherever the
reviews measured a gap, mark selection and "current" the same way everywhere, and
speak the user's language (no engine ids, no slugs) in the web app, in chat and in
MCP.

**Principles**
- **Honesty about unsaved work outranks convenience.** If a gesture could lose
  typed text, it asks or keeps the text; the status line never says "saved" while
  something is pending.
- **Accessibility is not negotiable.** WCAG 2.2 AA: contrast pinned by computed
  tests, focus never dropped to `<body>`, programmatic state (`aria-current`,
  `aria-pressed`, `inert`).
- **No new dependencies.** Existing tokens, components and hooks, or a small
  shared helper.
- **MCP and chat contracts are additive only.** The docstring is the API (SYSTEM.md
  §7). Every docstring stays under the ~2,000-char truncation budget.
- **Conventions change deliberately.** Each task updates
  `docs/frontend-conventions.md` (and SYSTEM.md where it describes the behaviour)
  in the same commit.

**Non-goals**
- Phase 2 of the studio direction (draft preview, three zones, job-fit chip), Phase
  3 (undo), remembering the sidebar across reloads, and the extension side panel.
- The out-of-scope leaks the briefs name for §11 (raw work-mode/OPT keys on Job
  market; MCP `explore_*` tools returning role slugs). File them in §11; don't widen
  this plan.

**Autonomy: peer (adapt-and-advise).** Adapt *how* when a step conflicts with repo
reality, and log every deviation in this doc with one line of reason. Anything touching
scope, another task's interface or the Goal Card goes back to the planner. Never
expand scope.

## Ground truth (read in this order before writing code)

1. `SYSTEM.md` at the repo root: the authoritative project reference.
2. `docs/frontend-conventions.md` and `frontend/AGENTS.md`.
3. The main plan `docs/plans/2026-09-22-ux-followups.md`: *Goal Card*, *Owner decisions*
   (binding), *Before you start*, and your tasks' sections. Each task section is the spec:
   its Files, Steps, pins, browser check and commit message.
4. The appendix sections your tasks cite (A1 §n, A2 §n, B §n) in
   `docs/plans/2026-09-22-ux-followups-appendix-*.md`. They hold the exact code. Their line
   numbers are from `a3c800bb`; Tasks 1–3 moved code since, so re-locate by the quoted code.

## Your tasks

1. **Task 17** — the `### Task 17` section of the main plan.

Per task: add the pins and see them FAIL → implement → run the task's gates → browser check →
one commit with the plan's commit message. End every commit message with
`Assisted-by: Grok 4.7 (Cursor CLI)`. Don't amend or squash earlier commits.

## Scope

**Files this lane owns:**
- Every file in B §8's code-fix table (about 20 components and pages; re-locate each by
  the quoted text; lanes 1–4 have since edited several of them, e.g. `app/referrals/page.tsx`
  now owns a `ReferralForm` whose create-form placeholders already start `e.g.`)
- new `backend/tests/test_frontend_placeholders.py` (the scoped ratchet)
- `docs/frontend-conventions.md`: the *Form conventions* and *Microcopy* placeholder text
- `docs/frontend-conventions.md`: only the bullets your task names. Never reflow or reorder text you didn't change.
- This handoff doc (its logs below).

**Parallel work:**
- None run in parallel: this lane runs alone on the merged branch. Still, change only the
  placeholder, hint and `aria-describedby` wiring in each file. No restyling, no moved code,
  no refactors the task doesn't name.

**Never touch:**
- `SYSTEM.md`. It sits at its 1000-line cap and Claude grooms it in Task 18. Write any
  SYSTEM.md change your task calls for under *Queued for Task 18* below; Claude applies them.
- `.slop-baseline.json` files (don't re-baseline; see Gates).
- `docs/ux/` (private, untracked), other worktrees and branches.
- The main checkout `/Users/ajeyds/Projects/maestro-career-studio`: its `data/` is the
  owner's live database, and its Docker stack on ports 3000/8001 is live. Never `cd` there,
  never run `docker compose`.
- Never use bare `git stash` / `git stash pop` (the stash stack is shared with other
  sessions). Don't push, rebase or merge.

## Lane notes

- **Why this is wave 2:** Tasks 4–16 landed first (four lanes, reviewed and merged).
  Placeholders sit in files all four lanes touched, so the appendix's line numbers and some
  of its rows are stale. Re-verify every row against the current code before editing; if a
  row no longer applies (already fixed, or the control is gone), log it in the deviation log.
- **Owner decision 3 (binding):** examples stay as placeholders, prefixed `e.g. `; the doc
  records a scoped, deliberate deviation from GOV.UK and says why. Every non-example
  placeholder (statement, instruction, label repeat) is fixed per B §8's table.
- **The ratchet** (step 1): allow values starting `e.g. ` or `https://`, and `…`-ending
  prompts only in an allowlist of search, composer and chip add-row files; fail on anything
  else; skip `SelectValue` and image placeholders. Make it read the real attribute values
  (JSX strings, template literals, and the data-driven values B §8 lists), not a loose
  substring, and mutation-check it.
- **Don't reformat the autofill `GROUPS` header lines**: `test_autofill_groups_parity.py`
  parses them.
- **Hints below their control:** wire the two B §8 names, placing each hint between the
  label and the control with `aria-describedby`.
- **Contrast:** the `--muted-foreground` pin the deviation text cites already exists
  (`test_frontend_color_roles.py`, landed with Task 6).
- **Known review pattern for this model:** in wave 1, every lane's tests were weaker than
  claimed and error/empty states were under-examined. Mutation-check every pin you add (break
  the code, see exactly that pin fail, restore from a backup copy), and in the browser check
  look at empty and filled states of the edited forms.

## Environment

- Python: `/opt/anaconda3/bin/python3`. Run pytest and ruff from `/Users/ajeyds/Projects/maestro-ux-lanes/lane5-placeholders/backend`
  (the cwd wins on `sys.path`, so tests import this worktree's code).
- Frontend (from `/Users/ajeyds/Projects/maestro-ux-lanes/lane5-placeholders/frontend`): `npx tsc --noEmit`, `npm run lint`,
  `node --test lib/*.test.ts`, and `npm run build` where a task asks.
- **Lint has the React Compiler rules at error level** (`react-hooks/refs`,
  `set-state-in-effect`, `set-state-in-render`). Run lint after every step. Baseline:
  0 errors, 5 warnings.
- **Node tests aren't in CI.** Pair every `lib/*.ts` behaviour with a pytest source pin in
  `backend/tests/test_frontend_*.py`.
- **Browser checks** use a throwaway stack on this lane's ports:
  - scratch dir `/tmp/maestro-lane5`; SQLite at `/tmp/maestro-lane5/app.sqlite3`;
  - backend: from `/Users/ajeyds/Projects/maestro-ux-lanes/lane5-placeholders/backend`,
    `DATABASE_URL=sqlite:////tmp/maestro-lane5/app.sqlite3`, every `*_DIR` variable
    SYSTEM.md lists pointed under the scratch dir,
    `ALLOWED_WEB_ORIGINS=http://127.0.0.1:3105,http://localhost:3105`,
    `PATH=/Library/TeX/texbin:$PATH`, then
    `/opt/anaconda3/bin/python3 -m uvicorn app.main:app --port 8775` (startup runs
    alembic);
  - frontend: `API_PROXY_BACKEND=http://127.0.0.1:8775 npx next dev -p 3105`;
  - seed MADE-UP data through the API; no LLM keys are needed;
  - use real key and pointer events (a Playwright/browser tool), not synthetic JS events;
  - tear the stack down afterwards.

  If you have no browser tool, write "not run" for that check in the gate table. Claude runs
  every browser check again at merge anyway.

## Gates (per task, and all of them before you report done)

- The task's pins, plus every `backend/tests/test_frontend_*.py`.
- tsc clean; lint 0 errors; node tests pass.
- Slop ratchet, from `/Users/ajeyds/Projects/maestro-ux-lanes/lane5-placeholders`:
  `python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check frontend` and
  `… check backend`. Name both surfaces in your report.
  - **Frontend duplication ceiling for this lane: 506 duplicated lines, 42 clones** (the
    value at the branch point). Hold your delta at zero or below. Get the numbers with
    `slop_scan.py scan frontend --json` → `duplication`.
  - Logic added in two places goes through a shared helper or hook. Never reorder code to
    dodge the detector.
  - If `complexity_hotspots` rises only because you added tests, don't re-baseline: note it
    in the gate table and Claude re-baselines at merge.
- Don't run the full backend suite unless your task says to (Task 12 does).

## Escalation (autonomy: peer)

You may adapt *how* when the plan conflicts with the code, and log it below. Stop and ask
the owner (write a deviation note below: planned / found / proposed / Goal Card line) when:
- a change would touch scope, a file outside B §8's table, or an
  interface another task depends on;
- the plan looks wrong against the Goal Card. Flagging a plan defect is welcome; pushing
  through one is not.
Never expand scope. If you finish early, stop; don't pick up Task 18 or 19.

## Done means

All 1 tasks committed on `grok/ux-lane5-placeholders` (one commit each), the three logs below
filled in, and this doc committed with them. Then report to the owner: the commit SHAs, the
gate table, deviations, anything queued or deferred, and any concerns.

## Deviation log

| Task | Planned | Did instead | Why (Goal Card line) |
|---|---|---|---|

## Gate results

| Task | Gate | Result |
|---|---|---|

## Queued for Task 18 (SYSTEM.md changes Claude applies)

## Deferred to merge (edits left for Claude, with file:line)
