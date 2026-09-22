# UX follow-ups, lane 2: Accessibility and visual consistency — handoff to Cursor CLI / Grok 4.7

**Target agent/model:** Cursor CLI (`agent`), **Grok 4.7** (xhigh). If your session runs a
different model, stop and say so: the review tier depends on it.
**Tasks:** 5, 6, 7, 10 of `docs/plans/2026-09-22-ux-followups.md`, in that order.
**Branch:** `grok/ux-lane2-a11y` (from `claude/ux-followups` at the commit that added this doc, right after `2916d83f`).
**Worktree:** `/Users/ajeyds/Projects/maestro-ux-lanes/lane2-a11y` (dependencies are installed). Work only there.
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

1. **Task 5** — the `### Task 5` section of the main plan.
2. **Task 6** — the `### Task 6` section of the main plan.
3. **Task 7** — the `### Task 7` section of the main plan.
4. **Task 10** — the `### Task 10` section of the main plan.

Per task: add the pins and see them FAIL → implement → run the task's gates → browser check →
one commit with the plan's commit message. End every commit message with
`Assisted-by: Grok 4.7 (Cursor CLI)`. Don't amend or squash earlier commits.

## Scope

**Files this lane owns:**
- `frontend/app/globals.css`
- `backend/tests/test_frontend_color_roles.py`, `test_frontend_first_run.py`,
  `test_frontend_sidebar_nav.py`
- `frontend/components/ats-score-panel.tsx`, `frontend/components/setup/upload-dialog.tsx`
- `frontend/components/ui/sidebar.tsx`, `frontend/components/sidebar-reveal-trigger.tsx`,
  `frontend/components/app-sidebar.tsx`, `frontend/lib/nav.ts`, `frontend/lib/nav.test.ts`
- Task 10's files: `source-toggle.tsx`, `proposals/proposals-section.tsx`,
  `setup/setup-status-strip.tsx`, `setup/dropzone.tsx`, `charts/top-skills-chart.tsx`,
  `career/new-entity-dialog.tsx`
- Task 6's hand-rolled `red-*` sites (A2 §3)
- `docs/frontend-conventions.md`: only the bullets your tasks name. Other lanes edit other
  bullets of the same file in parallel, so never reflow or reorder text you didn't change.
- This handoff doc (its logs below).

**Files other lanes change at the same time:**
- **Lane 1 owns** `tailored-resume-studio.tsx`, `editor-body.tsx`, `editor-shell.tsx`,
  `formatting-panel.tsx`, `pdf-pages-preview.tsx`, `chat-page.tsx` and
  `app/templates/[id]/page.tsx`. In them, make only the exact class or attribute edits your
  task names (Task 10: the tab count, the "Customized" chip, `aria-pressed`, "New chat" and
  `aria-current`; Task 6: `red-*` → destructive token). No reformatting, no moved code.
- **Lane 3 owns** `app/career/page.tsx`, `status-chip.tsx` and `role-category-picker.tsx`.
  Same rule for Task 6's `red-*` swaps there.
- **Task 6's optional fold-in of translucent `ring-ring/50` / `outline-ring/60` sites:** do
  it only in files you own. List every site in another lane's file under *Deferred to
  merge* below; Claude folds them in after merging.

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

- **Task 5:** keep every existing first-run and query-error pin green.
- **Task 6:** owner decision 2 fixes the dark destructive value. The `--muted-foreground`
  pin is for Task 17 (wave 2), so it must land here.
- **Task 7:** `useSearchParams` needs a Suspense boundary. Read
  `frontend/node_modules/next/dist/docs/` on it first, and run `npm run build` (the build
  fails without the boundary; the dev server doesn't).
- **Task 10:** owner decision 5 is binding. Keep `test_frontend_query_error_states.py`'s
  copy anchors intact (you don't own that file; don't edit it).

## Environment

- Python: `/opt/anaconda3/bin/python3`. Run pytest and ruff from `/Users/ajeyds/Projects/maestro-ux-lanes/lane2-a11y/backend`
  (the cwd wins on `sys.path`, so tests import this worktree's code).
- Frontend (from `/Users/ajeyds/Projects/maestro-ux-lanes/lane2-a11y/frontend`): `npx tsc --noEmit`, `npm run lint`,
  `node --test lib/*.test.ts`, and `npm run build` where a task asks.
- **Lint has the React Compiler rules at error level** (`react-hooks/refs`,
  `set-state-in-effect`, `set-state-in-render`). Run lint after every step. Baseline:
  0 errors, 5 warnings.
- **Node tests aren't in CI.** Pair every `lib/*.ts` behaviour with a pytest source pin in
  `backend/tests/test_frontend_*.py`.
- **Browser checks** use a throwaway stack on this lane's ports (other lanes use others):
  - scratch dir `/tmp/maestro-lane2`; SQLite at `/tmp/maestro-lane2/app.sqlite3`;
  - backend: from `/Users/ajeyds/Projects/maestro-ux-lanes/lane2-a11y/backend`,
    `DATABASE_URL=sqlite:////tmp/maestro-lane2/app.sqlite3`, every `*_DIR` variable
    SYSTEM.md lists pointed under the scratch dir,
    `ALLOWED_WEB_ORIGINS=http://127.0.0.1:3102,http://localhost:3102`,
    `PATH=/Library/TeX/texbin:$PATH`, then
    `/opt/anaconda3/bin/python3 -m uvicorn app.main:app --port 8772` (startup runs
    alembic);
  - frontend: `API_PROXY_BACKEND=http://127.0.0.1:8772 npx next dev -p 3102`;
  - seed MADE-UP data through the API; no LLM keys are needed;
  - use real key and pointer events (a Playwright/browser tool), not synthetic JS events;
  - tear the stack down afterwards.

  If you have no browser tool, write "not run" for that check in the gate table. Claude runs
  every browser check again at merge anyway.

## Gates (per task, and all of them before you report done)

- The task's pins, plus every `backend/tests/test_frontend_*.py`.
- tsc clean; lint 0 errors; node tests pass.
- Slop ratchet, from `/Users/ajeyds/Projects/maestro-ux-lanes/lane2-a11y`:
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

All 4 tasks committed on `grok/ux-lane2-a11y` (one commit each), the three logs below
filled in, and this doc committed with them. Then report to the owner: the commit SHAs, the
gate table, deviations, anything queued or deferred, and any concerns.

## Deviation log

| Task | Planned | Did instead | Why (Goal Card line) |
|---|---|---|---|
| 5–10 | Main plan trailer `Co-Authored-By: Claude Opus 5` | `Assisted-by: Grok 4.7 (Cursor CLI)` | This handoff's commit contract. The session is Grok 4.7; a Claude trailer would mis-attribute the work. |
| 5 | A1 §5 comments quote the empty-state copy | Comments say "empty-state frame"; the user-facing string is the only occurrence | `test_frontend_query_error_states.py` anchors the first occurrence of that copy, and this lane must not edit that file. Accessibility pins stay green. |
| 6 | `--muted-foreground` pin fails with the new ring and destructive pins | The pin was added and was already green | The token already clears 4.5:1 on `--background` and `--card`. It still lands here because Task 17 cites it. The ring and destructive pins failed first. |
| 6 | Fold A2 §2's translucent `ring-ring/50` and `outline-ring/60` sites into the solid ring | Left every listed site; see Deferred | None of those files belong to this lane. Lane 3 owns `status-chip.tsx` and `role-category-picker.tsx`. The base-layer outline and the 1px `border-ring` now carry the 3:1; the leftover halos are not on the canvas. |
| 7 | Pins listed in the task only | Also pinned `from === "proposals" ? "/proposals" : "/applications"` in `nav.ts` | Node tests are not in CI. The mapping has to fail a pytest pin or a later edit can drop it silently. |

## Gate results

| Task | Gate | Result |
|---|---|---|
| 5 | New pin failed first, then `test_frontend_first_run.py` + `test_frontend_query_error_states.py` | 48 passed |
| 5 | `tests/test_frontend_*.py` | 157 passed |
| 5 | tsc | clean |
| 5 | lint | 0 errors, 5 warnings (baseline) |
| 5 | `node --test lib/*.test.ts` | 67 passed |
| 5 | slop `check frontend` | OK. scan: 517 duplicated lines, 43 clones (ceiling) |
| 5 | slop `check backend` | OK |
| 5 | Browser: import → Done on a job with zero bases | No "No ATS scores yet." in a MutationObserver across the close; cards rendered (Best match, Re-score); `document.activeElement` is the wrapper `div` (`tabindex=-1`, `outline-none`) |
| 6 | New contrast pins failed first, then `test_frontend_color_roles.py` | Passed, including muted-foreground (already green before the token change) |
| 6 | `tests/test_frontend_*.py` | 164 passed |
| 6 | tsc | clean |
| 6 | lint | 0 errors, 5 warnings (baseline) |
| 6 | slop `check frontend` / `check backend` | Both OK. Frontend scan: 517 duplicated lines, 43 clones |
| 6 | Browser, light and dark | Tab to the 100% zoom preset: `outline-style: auto`, 1px, color `rgb(78, 119, 184)` (`#4e77b8`, the new light ring). Shift-Tab to Open PDF: 1px border the same color, plus the button's 3px `/50` halo. Dark mode: Open PDF border, the zoom outline, and the Agent SourceToggle outline all match `.dark`'s `--ring`. Light SourceToggle outline matches `#4e77b8`. Render-error banner and "JD asks for…" badge were not on this fixture (render succeeded, no gate warning); their contrast is the computed pin. |
| 7 | Sidebar pins failed first, then `test_frontend_sidebar_nav.py` + first-run | Passed |
| 7 | `tests/test_frontend_*.py` | 166 passed |
| 7 | `node --test lib/*.test.ts` | 71 passed (nav job-page cases included) |
| 7 | tsc / lint | tsc clean; lint 0 errors, 5 warnings |
| 7 | `npm run build` | Passed. Static pages generated; no missing-Suspense error |
| 7 | slop `check frontend` / `check backend` | Both OK. Frontend scan: 517 duplicated lines, 43 clones |
| 7 | Browser | Collapse: container `inert`, focus on the reveal pill (not inside the sidebar). Eight Tabs stay in the page (New application, search, filters) and never enter the sidebar. `/new` FAB background equals `--primary` with `aria-current="page"`; elsewhere it equals `--primary-container` and omits `aria-current`. `/jobs/{id}` marks Applications `true`; `?from=proposals` marks Agent Proposals `true` instead. At 375px the desktop container is absent and the trigger opens the sheet (`data-mobile="true"`). |

## Queued for Task 18 (SYSTEM.md changes Claude applies)

- §12: `useSearchParams()` under the root layout needs a Suspense boundary whose fallback is the same UI, or `next build` fails and every static route loses the component. The sidebar's main nav is that case (`app-sidebar.tsx`).

## Deferred to merge (edits left for Claude, with file:line)

Task 6, A2 §2 translucent focus halos (drop the alpha). Not edited: the first two are lane 3's files; the rest are not this lane's.

- `frontend/components/status-chip.tsx:66` `focus-visible:outline-ring/60` (lane 3)
- `frontend/components/role-category-picker.tsx:149` `focus-within:ring-ring/50` (lane 3)
- `frontend/components/role-picker.tsx:350` `focus-within:ring-ring/50`
- `frontend/components/ui/chip-input.tsx:105` `focus-within:ring-ring/50`
- `frontend/components/career/points-list.tsx:368` `focus-visible:outline-ring/60`
- `frontend/components/career/entity-detail.tsx:417` `focus-visible:outline-ring/60`
