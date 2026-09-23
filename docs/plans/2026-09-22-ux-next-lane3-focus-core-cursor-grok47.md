# UX next, wave 1 lane 3: Focus core — handoff to Cursor CLI / Grok 4.7

**Target agent/model:** Cursor CLI (`agent`), **Grok 4.7** (xhigh). If your session runs a
different model, stop and say so: the review tier depends on it.
**Tasks:** 8, 9, 10 of `docs/plans/2026-09-22-ux-next.md`, in that order.
**Branch:** `grok/ux-next-lane3-focus-core` (from `claude/ux-next-plan` at `the commit that added this doc`).
**Worktree:** `/Users/ajeyds/Projects/maestro-ux-lanes/next-lane3-focus-core` (dependencies are installed). Work only there.
**Planner/reviewer:** Claude (Opus 5.5). It reviews and merges this branch; you never merge.

## Goal Card

**Goal.** Close the older gaps that the follow-ups plan's goal critique and final browser
sweep found (its *Next plan* list). The app never loses typed text and never says "saved"
while something is pending. It never shows internal ids, edit paths or slugs. Keyboard focus
is never dropped to `<body>`, and selection, current state and contrast meet WCAG 2.2 AA
wherever they are measured.

**Principles**
- **Honesty about unsaved work outranks convenience.** If a gesture could lose typed text,
  it asks or keeps the text; the status line never says "saved" while something is pending.
- **Accessibility is not negotiable.** WCAG 2.2 AA: contrast pinned by computed tests, focus
  never dropped to `<body>`, programmatic state (`aria-current`, `aria-pressed`, `inert`).
- **Speak the user's language** in the web app, in chat and in MCP: no engine ids, no edit
  paths, no slugs.
- **No new dependencies.** Existing components, hooks and small shared helpers.
- **MCP and chat contracts are additive only.** Docstrings stay under the ~2,000-char budget.
- **Conventions change deliberately.** Each task updates `docs/frontend-conventions.md` in
  the same commit; SYSTEM.md changes are queued for the docs sweep (Task 20).

**Non-goals**
- Phase 2 of the studio direction (draft preview, three zones, job-fit chip), Phase 3
  (undo), remembering the sidebar across reloads, the extension side panel.
- The chat composer at 375px (owner: 768 only), the tabs/segments visual pass, and a
  "Save and leave" button.

**Autonomy: peer (adapt-and-advise).** Adapt *how* when a step conflicts with repo reality,
and log every deviation in this doc with one line of reason. Anything touching scope, another task's
interface or the Goal Card goes back to the planner. Never expand scope.

## Ground truth (read in this order before writing code)

1. `SYSTEM.md` at the repo root: the authoritative project reference.
2. `docs/frontend-conventions.md` and `frontend/AGENTS.md` (Next 16.3: read
   `frontend/node_modules/next/dist/docs/` before relying on any Next API).
3. The main plan `docs/plans/2026-09-22-ux-next.md`: *Goal Card*, *Owner decisions*
   (binding), *Before you start*, *Waves and lanes*, and your tasks' sections. Each task
   section is the spec: files, steps, pins, browser check and commit message.
4. The appendix sections your tasks cite: F §0, §"Shared helper", F2, F4 (the `useSingleFlight` design only; its call sites are wave 2) and F5 in `docs/plans/2026-09-22-ux-next-appendix-f-focus-and-minor.md`. They hold the exact code; their
   line numbers are from `2cce6139`, so re-locate by the quoted code.

## Your tasks

1. **Task 8**: the `### Task 8` section of the main plan.
2. **Task 9**: the `### Task 9` section of the main plan.
3. **Task 10**: the `### Task 10` section of the main plan.

Per task: add the pins and see them FAIL → implement → run the task's gates → browser check →
one commit with the plan's commit message. End every commit message with
`Assisted-by: Grok 4.7 (Cursor CLI)`. Don't amend or squash earlier commits.

## Scope

**Files this lane owns:**
- Task 8: new `frontend/lib/query-state.ts` (+ `.test.ts`), new
  `frontend/hooks/use-focus-return.ts`, `hooks/use-last-seen.ts`, `hooks/use-single-flight.ts`,
  new `backend/tests/test_frontend_focus.py`
- Task 9: `frontend/components/load-error-state.tsx`, `lib/formatting.ts` and
  `resume-editor/formatting-panel.tsx` (simplify onto the helper), and the failure branch of every
  caller in F2's inventory (`app/referrals/page.tsx`, `app/base-resumes/page.tsx`,
  `app/profile/page.tsx`, `app/applications/page.tsx`, `app/applications/[id]/page.tsx`,
  `app/templates/page.tsx`, `app/jobs/[id]/page.tsx`, `qa-tab.tsx`, `ats-score-panel.tsx`,
  `settings/setting-card.tsx`, `career/first-run-import-card.tsx`,
  `resume-health/health-report-page.tsx`, `chat/chat-page.tsx`, `setup/getting-started-card.tsx`,
  `proposals/proposals-section.tsx`, `proposals/proposal-agent-panel.tsx`), plus the four
  route-level error branches (base and tailored studio routes, the template editor, the tailor
  session page); pins in `test_frontend_query_error_states.py`, `test_frontend_studio.py`,
  `test_frontend_referrals.py`
- Task 10: the history rail and composer layout in `chat/chat-page.tsx`; a new
  `backend/tests/test_frontend_chat_layout.py` (or pins in `test_frontend_sidebar_nav.py`)
- `docs/frontend-conventions.md`: only the bullets your tasks name. Other lanes edit other
  bullets of the same file in parallel, so never reflow or reorder text you didn't change.
- This handoff doc (its logs below).

**Files other lanes change at the same time:**
- **Lane 1** swaps the `next/link` import line in 31 files (several of yours) and changes
  `app/providers.tsx`. **Lane 2** edits names/chips in `ats-score-panel.tsx`,
  `proposals-section.tsx`, `app/applications/page.tsx`, `chat/chat-page.tsx` (a list query),
  the tailor page and `app/templates/[id]/page.tsx`. In those files keep your edits to the
  failure/loading branches and the chat layout; no reformatting, no moved code.

**Never touch:**
- `SYSTEM.md` (it sits at its 1000-line cap). Write any SYSTEM.md change your task calls for
  (mostly §11 items your work closes) under *Queued for Task 20* below; Claude applies them.
- `.slop-baseline.json` files; `docs/ux/` (private, untracked); other worktrees and branches.
- The main checkout `/Users/ajeyds/Projects/maestro-career-studio`: its `data/` is the
  owner's live database, and its Docker stack on ports 3000/8001 is live. Never `cd` there,
  never run `docker compose`.
- Never use bare `git stash` / `git stash pop` (the stash stack is shared). Don't push, rebase
  or merge.

## Lane notes

- **Task 8 adds helpers only.** `useSingleFlight` is built and node/pin-tested here; its call
  sites land in wave 2 (Tasks 13–16, 19). `useFocusReturn`'s studio call sites are Task 17
  (wave 2); Task 9 uses `useFocusHandoff`.
- **`lib/*.ts` can't value-import another `lib/*.ts`** (F §0.7): `lib/formatting.ts`'s
  `unloadedLayer` keeps its own copy of the retry predicate, pinned to `lib/query-state.ts` by a
  node parity test (and a pytest pin).
- **Referrals would crash** once its error block stays mounted during a retry (F §0.3): fix the
  `.message` read in the same change.
- **Two callers treat a 404 as a state** (health report, application page): remember the last
  error with `useLastSeen`, or they flash "Couldn't load… Retrying…" on every refetch.
- **Task 10 fixes 768 only** (owner): container-gate the history rail. Don't make the composer
  wrap; §11 item 31 keeps its chat clause.
- **What the reviewer checks hardest** (from five earlier Grok 4.7 lanes): pins that can't
  catch the regression they name, and loading / error / pending / empty states nobody forced.
  Mutation-check every pin you add (break the guarded code, see exactly that pin fail, restore
  from a backup copy). In the browser, force the slow, failing and double-click paths, and seed
  richer data than the minimum.

## Environment

- Python: `/opt/anaconda3/bin/python3`. Run pytest and ruff from `/Users/ajeyds/Projects/maestro-ux-lanes/next-lane3-focus-core/backend`.
- Frontend (from `/Users/ajeyds/Projects/maestro-ux-lanes/next-lane3-focus-core/frontend`): `npx tsc --noEmit`, `npm run lint` (0 errors; 5 baseline
  warnings), `node --test lib/*.test.ts`, and `npm run build` where a task asks.
- **Browser checks** use a throwaway stack on this lane's ports:
  - scratch dir `/tmp/maestro-next-lane3`; SQLite at `/tmp/maestro-next-lane3/app.sqlite3`;
  - backend from `/Users/ajeyds/Projects/maestro-ux-lanes/next-lane3-focus-core/backend`: `DATABASE_URL=sqlite:////tmp/maestro-next-lane3/app.sqlite3`,
    every `*_DIR` variable in `backend/app/config.py` under the scratch dir,
    `ALLOWED_WEB_ORIGINS=http://127.0.0.1:3103,http://localhost:3103`,
    `PATH=/Library/TeX/texbin:$PATH`, then
    `/opt/anaconda3/bin/python3 -m uvicorn app.main:app --port 8773`;
  - frontend: run `npm run predev` if it exists (it copies Monaco; delete copied untracked
    files afterwards), then `API_PROXY_BACKEND=http://127.0.0.1:8773 npx next dev -p 3103`,
    and open `http://localhost:3103` (127.0.0.1 gets 403 on dev assets);
  - seed MADE-UP data through the API; no LLM keys are needed (a no-LLM health report
    script and a richer seed script from earlier reviews may exist under `/tmp/maestro-*`;
    read before reusing);
  - real key and pointer events (Playwright), not synthetic JS events;
  - screenshots only under the scratch dir; tear the stack down afterwards.

  If you have no browser tool, write "not run" for that check. Claude re-runs every browser
  check at merge anyway.

## Gates (per task, and all of them before you report done)

- The task's pins, plus every `backend/tests/test_frontend_*.py`.
- tsc clean; lint 0 errors; node tests pass.
- Slop ratchet from `/Users/ajeyds/Projects/maestro-ux-lanes/next-lane3-focus-core`:
  `python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check frontend` and
  `… check backend`; name both surfaces in your report.
  - **Frontend duplication ceiling for this lane: 505 duplicated lines, 42 clones** (the measured value at the branch
    point; the checked-in baseline says more). Several lanes merge into one branch, so hold
    your delta at zero or below. `slop_scan.py scan frontend --json` → `duplication`.
  - **Backend `complexity_hotspots` must stay at 424**: split a test that reaches cc 10.
  - Logic added in two places goes through a shared helper. Never reorder code to dodge the
    detector.
- `npm run build` for Task 9.

## Escalation (autonomy: peer)

You may adapt *how* when the plan conflicts with the code, and log it below. Stop and ask
the owner (write a deviation note below: planned / found / proposed / Goal Card line) when:
- a change would touch scope, a file another lane owns beyond the lines named above, or an
  interface another task depends on;
- the plan looks wrong against the Goal Card. Flagging a plan defect is welcome; pushing
  through one is not.
Never expand scope. If you finish early, stop; don't pick up another lane's task.

## Done means

All 3 tasks committed on `grok/ux-next-lane3-focus-core` (one commit each), the logs below filled
in, and this doc committed with them. Then report to the owner: the commit SHAs, the gate
table, deviations, anything queued or deferred, and any concerns.

## Deviation log

| Task | Planned | Did instead | Why (Goal Card line) |
|---|---|---|---|
| 8 | Handoff pin asserts `"useEffect(" not in body` | Strip `useLayoutEffect(` before that check | The planned assert cannot pass: `useLayoutEffect(` contains `useEffect(`. Swapping the layout effect for `useEffect` still fails the pin. Accessibility: the cleanup must run before React detaches the subtree. |
| 8 | `use-last-seen.ts` snippet has no directive | Added `"use client"`, matching every other file in `hooks/` | No new dependencies; the hook uses `useState` and the rest of the folder is a client boundary. |
| 8 | Appendix pins only the three focus asserts in `test_frontend_focus.py`; the single-flight guard pin is in wave 2's `test_frontend_single_flight.py` | Also pin `isLoadFailure`, the `unloadedLayer` copy, `useLastSeen`, and the guard flip in `test_frontend_focus.py` | Node tests are not in CI, and this lane builds the helpers with no call sites yet. The call-site parametrize stays in wave 2. |
| 8 | `lib/formatting.ts` is listed on Task 9 | The `isLoadFailure` parity comment landed in this commit | The comment is the reason the two copies exist, and the Task 8 parity pin reads it. Task 9 still owns the panel simplification. |

## Gate results

| Task | Gate | Result |
|---|---|---|
| 8 | `node --test lib/*.test.ts` | 92 passed (6 new in `query-state.test.ts`) |
| 8 | `pytest tests/test_frontend_focus.py` | 6 passed; each pin failed alone when its guarded line was broken, then restored |
| 8 | `pytest tests/test_frontend_*.py` | 291 passed |
| 8 | `tsc --noEmit` | clean |
| 8 | `npm run lint` | 0 errors, 5 baseline warnings |
| 8 | slop frontend | 505 duplicated lines, 42 clones (delta 0) |
| 8 | slop backend | `complexity_hotspots` 424 (delta 0) |

## Queued for Task 20 (SYSTEM.md changes Claude applies)

## Deferred to merge (edits left for Claude, with file:line)
