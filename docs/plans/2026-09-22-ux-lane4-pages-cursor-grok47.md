# UX follow-ups, lane 4: Templates, health page and referrals — handoff to Cursor CLI / Grok 4.7

**Target agent/model:** Cursor CLI (`agent`), **Grok 4.7** (xhigh). If your session runs a
different model, stop and say so: the review tier depends on it.
**Tasks:** 14, 15, 16 of `docs/plans/2026-09-22-ux-followups.md`, in that order.
**Branch:** `grok/ux-lane4-pages` (from `claude/ux-followups` at the commit that added this doc, right after `2916d83f`).
**Worktree:** `/Users/ajeyds/Projects/maestro-ux-lanes/lane4-pages` (dependencies are installed). Work only there.
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

1. **Task 14** — the `### Task 14` section of the main plan.
2. **Task 15** — the `### Task 15` section of the main plan.
3. **Task 16** — the `### Task 16` section of the main plan.

Per task: add the pins and see them FAIL → implement → run the task's gates → browser check →
one commit with the plan's commit message. End every commit message with
`Assisted-by: Grok 4.7 (Cursor CLI)`. Don't amend or squash earlier commits.

## Scope

**Files this lane owns:**
- `frontend/components/gallery/preview-thumbnail.tsx`,
  `frontend/components/templates/template-thumbnail.tsx`
- delete `frontend/app/applications/[id]/health/page.tsx`;
  `frontend/components/resume-health/health-report-page.tsx`;
  `frontend/app/base-resumes/[slug]/health/page.tsx`;
  `frontend/components/resume-editor/studio-toolbar.tsx` (a comment only)
- `frontend/app/referrals/page.tsx`
- `backend/tests/test_frontend_query_error_states.py` (Task 16's one entry)
- optional new router test for Task 15
- `docs/frontend-conventions.md`: only the bullets your tasks name. Other lanes edit other
  bullets of the same file in parallel, so never reflow or reorder text you didn't change.
- This handoff doc (its logs below).

**Files other lanes change at the same time:**
- **`components/templates/template-select.tsx` belongs to lane 1** (Task 4 changes
  `useTemplateDefaults` there). Skip Task 14's optional `DialogDescription` edit and note it
  under *Deferred to merge*.
- Lane 2 (Task 6) may swap `red-*` classes in `resume-health/*` files. Don't reformat those.

**Never touch:**
- `SYSTEM.md`. It sits at its 1000-line cap and four lanes would collide there. Write any
  SYSTEM.md change your task calls for under *Queued for Task 18* below; Claude applies them.
- `.slop-baseline.json` files (don't re-baseline; see Gates).
- `docs/ux/` (private, untracked), other lanes' worktrees and branches.
- The main checkout `/Users/ajeyds/Projects/maestro-career-studio`: its `data/` is the
  owner's live database, and its Docker stack on ports 3000/8001 is live. Never `cd` there,
  never run `docker compose`.
- Never use bare `git stash` / `git stash pop` (the stash stack is shared with other
  sessions). Don't push, rebase or merge.

## Lane notes

- **Task 15:** keep every backend endpoint (MCP uses `kind='application'`). Its step 3
  ("tell the controller") means: say so in your final report.
- **Task 16:** the referral form is new UI; follow `docs/frontend-conventions.md` form
  conventions (labels above controls, `<Label optional>`). Placeholders hold only examples
  prefixed `e.g.` (owner decision 3; Task 17 adds a ratchet for it later).

## Environment

- Python: `/opt/anaconda3/bin/python3`. Run pytest and ruff from `/Users/ajeyds/Projects/maestro-ux-lanes/lane4-pages/backend`
  (the cwd wins on `sys.path`, so tests import this worktree's code).
- Frontend (from `/Users/ajeyds/Projects/maestro-ux-lanes/lane4-pages/frontend`): `npx tsc --noEmit`, `npm run lint`,
  `node --test lib/*.test.ts`, and `npm run build` where a task asks.
- **Lint has the React Compiler rules at error level** (`react-hooks/refs`,
  `set-state-in-effect`, `set-state-in-render`). Run lint after every step. Baseline:
  0 errors, 5 warnings.
- **Node tests aren't in CI.** Pair every `lib/*.ts` behaviour with a pytest source pin in
  `backend/tests/test_frontend_*.py`.
- **Browser checks** use a throwaway stack on this lane's ports (other lanes use others):
  - scratch dir `/tmp/maestro-lane4`; SQLite at `/tmp/maestro-lane4/app.sqlite3`;
  - backend: from `/Users/ajeyds/Projects/maestro-ux-lanes/lane4-pages/backend`,
    `DATABASE_URL=sqlite:////tmp/maestro-lane4/app.sqlite3`, every `*_DIR` variable
    SYSTEM.md lists pointed under the scratch dir,
    `ALLOWED_WEB_ORIGINS=http://127.0.0.1:3104,http://localhost:3104`,
    `PATH=/Library/TeX/texbin:$PATH`, then
    `/opt/anaconda3/bin/python3 -m uvicorn app.main:app --port 8774` (startup runs
    alembic);
  - frontend: `API_PROXY_BACKEND=http://127.0.0.1:8774 npx next dev -p 3104`;
  - seed MADE-UP data through the API; no LLM keys are needed;
  - use real key and pointer events (a Playwright/browser tool), not synthetic JS events;
  - tear the stack down afterwards.

  If you have no browser tool, write "not run" for that check in the gate table. Claude runs
  every browser check again at merge anyway.

## Gates (per task, and all of them before you report done)

- The task's pins, plus every `backend/tests/test_frontend_*.py`.
- tsc clean; lint 0 errors; node tests pass.
- Slop ratchet, from `/Users/ajeyds/Projects/maestro-ux-lanes/lane4-pages`:
  `python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check frontend` and
  `… check backend`. Name both surfaces in your report.
  - **Frontend duplication ceiling for this lane: 517 duplicated lines, 43 clones** (the
    value at the branch point; the checked-in baseline says 518). Four lanes merge into one
    branch, so each must hold its own delta at zero or below. Get the numbers with
    `slop_scan.py scan frontend --json` → `duplication`.
  - Logic added in two places goes through a shared helper or hook. Never reorder code to
    dodge the detector.
  - If `complexity_hotspots` rises only because you added tests, don't re-baseline: note it
    in the gate table and Claude re-baselines at merge.
- Don't run the full backend suite unless your task says to (Task 12 does).

## Escalation (autonomy: peer)

You may adapt *how* when the plan conflicts with the code, and log it below. Stop and ask
the owner (write a deviation note below: planned / found / proposed / Goal Card line) when:
- a change would touch scope, a file another lane owns beyond the lines named above, or an
  interface another task depends on;
- the plan looks wrong against the Goal Card. Flagging a plan defect is welcome; pushing
  through one is not.
Never expand scope. If you finish early, stop; don't pick up another lane's task.

## Done means

All 3 tasks committed on `grok/ux-lane4-pages` (one commit each), the three logs below
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
