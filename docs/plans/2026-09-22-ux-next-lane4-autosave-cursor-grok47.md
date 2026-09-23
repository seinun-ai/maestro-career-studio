# UX next, wave 2 lane 4: Autosave and leave prompts — handoff to Cursor CLI / Grok 4.7

**Target agent/model:** Cursor CLI (`agent`), **Grok 4.7** (xhigh). If your session runs a
different model, stop and say so: the review tier depends on it.
**Tasks:** 11, 12, 13 of `docs/plans/2026-09-22-ux-next.md`, in that order.
**Branch:** `grok/ux-next-lane4-autosave` (from `claude/ux-next-plan` at `the commit that added this doc`).
**Worktree:** `/Users/ajeyds/Projects/maestro-ux-lanes/next-lane4-autosave` (dependencies are installed). Work only there.
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
4. The appendix sections your tasks cite: U2, U4.3 and U §Owner decisions 2 in `docs/plans/2026-09-22-ux-next-appendix-u-unsaved-work.md`; F4's inventory entry for `/new`'s Extract in `docs/plans/2026-09-22-ux-next-appendix-f-focus-and-minor.md`. They hold the exact code; their
   line numbers are from `2cce6139`, so re-locate by the quoted code (wave 1 moved many of them).

## Your tasks

1. **Task 11**: the `### Task 11` section of the main plan.
2. **Task 12**: the `### Task 12` section of the main plan.
3. **Task 13**: the `### Task 13` section of the main plan.

Per task: add the pins and see them FAIL → implement → run the task's gates → browser check →
one commit with the plan's commit message. End every commit message with
`Assisted-by: Grok 4.7 (Cursor CLI)`. Don't amend or squash earlier commits.

## Scope

**Files this lane owns:**
- Task 11: `frontend/app/jobs/[id]/tailor/[sessionId]/page.tsx` (the gap page's saver, `SaveIndicator`, its `useLeaveGuard` calls)
- Task 12: `frontend/lib/use-autosave.ts`, `frontend/components/settings/autosave-status.tsx`, the settings sections that use `useAutosave` (`settings/job-preferences-section.tsx`, `settings/quick-tailor-section.tsx`) and the MCP switch U4.3 names
- Task 13: the Persona, Autofill and Prompts settings sections (one `useLeaveGuard` line each), `frontend/app/new/page.tsx` (the pasted job description's guard and its Extract button's `useSingleFlight`)
- pins in new or existing `backend/tests/test_frontend_*.py` files your tasks name
- `docs/frontend-conventions.md`: only the bullets your tasks name. Other lanes edit other
  bullets of the same file in parallel, so never reflow or reorder text you didn't change.
- This handoff doc (its logs below).

**Files other lanes change at the same time:**
- **Lane 5** (drafts) owns `qa-tab.tsx` (including the Q&A cover-letter leave prompt), the dialogs and the Career KB editors. **Lane 6** (studio focus) owns the studios, `chat-page.tsx`, `app/referrals/page.tsx` and `app/templates/page.tsx`. Don't edit those.

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

- **Wave 1 is merged into your base.** Use its pieces rather than re-inventing them:
  - `hooks/use-leave-guard.ts` → `useLeaveGuard(when, { reloadOnly })` registers unsaved work
    with the app-wide leave guard (links, Back/Forward, reload). `components/guarded-link.tsx` is
    the only allowed `next/link` import (a pin enforces it).
  - `hooks/use-single-flight.ts` → `useSingleFlight(mutation.mutate)`: one request per click.
    **Caveat (docstring):** never call `.reset()` on a guarded mutation or a bare `.mutate` on it
    elsewhere while guarded, or the lock never clears.
  - `hooks/use-focus-return.ts` (`useFocusOnNextCommit`, `useFocusHandoff`,
    `focusReturnPoint`): move focus only when it fell to `<body>`.
  - `lib/query-state.ts` `isLoadFailure(q)` is now true only when the query has NO data and has
    failed (or is retrying after failing); a failed background refresh keeps loaded content.
    `hooks/use-last-seen.ts` has `useLoadFailureError`; `hooks/use-refresh-failed-notice.ts`
    toasts in editors; `components/retry-chip.tsx`; `LoadErrorState` keeps focus on Try again.
  - `lib/describe-edit.ts` + `components/edit-words-list.tsx` describe resume edits in words;
    `hooks/use-base-resume-label.ts` names résumés (never `humanizeSlug` as a permanent name).
  - Tab panels paint their focus ring as an `after:` overlay; the picker's selection is an inside
    edge plus a Check.
- **The gap page can't use `useAutosave`** (U §0.4): its debounce keeps a mis-clicked `cannot_confirm` from becoming a durable KB record. Fix the page's own saver.
- **Task 12's failed state must keep the leave guard honest:** `useLeaveGuard(failed)` so leaving after a failed autosave asks.
- **What the reviewer checks hardest** (from five earlier Grok 4.7 lanes): pins that can't
  catch the regression they name, and loading / error / pending / empty states nobody forced.
  Mutation-check every pin you add (break the guarded code, see exactly that pin fail, restore
  from a backup copy). In the browser, force the slow, failing and double-click paths, and seed
  richer data than the minimum.

## Environment

- Python: `/opt/anaconda3/bin/python3`. Run pytest and ruff from `/Users/ajeyds/Projects/maestro-ux-lanes/next-lane4-autosave/backend`.
- Frontend (from `/Users/ajeyds/Projects/maestro-ux-lanes/next-lane4-autosave/frontend`): `npx tsc --noEmit`, `npm run lint` (0 errors; 5 baseline
  warnings), `node --test lib/*.test.ts`, and `npm run build` where a task asks.
- **Browser checks** use a throwaway stack on this lane's ports:
  - scratch dir `/tmp/maestro-next-lane4`; SQLite at `/tmp/maestro-next-lane4/app.sqlite3`;
  - backend from `/Users/ajeyds/Projects/maestro-ux-lanes/next-lane4-autosave/backend`: `DATABASE_URL=sqlite:////tmp/maestro-next-lane4/app.sqlite3`,
    every `*_DIR` variable in `backend/app/config.py` under the scratch dir,
    `ALLOWED_WEB_ORIGINS=http://127.0.0.1:3104,http://localhost:3104`,
    `PATH=/Library/TeX/texbin:$PATH`, then
    `/opt/anaconda3/bin/python3 -m uvicorn app.main:app --port 8774`;
  - frontend: run `npm run predev` if it exists (it copies Monaco; delete copied untracked
    files afterwards), then `API_PROXY_BACKEND=http://127.0.0.1:8774 npx next dev -p 3104`,
    and open `http://localhost:3104` (127.0.0.1 gets 403 on dev assets);
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
- Slop ratchet from `/Users/ajeyds/Projects/maestro-ux-lanes/next-lane4-autosave`:
  `python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check frontend` and
  `… check backend`; name both surfaces in your report.
  - **Frontend duplication ceiling for this lane: 481 duplicated lines, 40 clones** (the measured value at the branch
    point; the checked-in baseline says more). Several lanes merge into one branch, so hold
    your delta at zero or below. `slop_scan.py scan frontend --json` → `duplication`.
  - **Backend `complexity_hotspots` must stay at 424**: split a test that reaches cc 10.
  - Logic added in two places goes through a shared helper. Never reorder code to dodge the
    detector.
- `npm run build`.

## Escalation (autonomy: peer)

You may adapt *how* when the plan conflicts with the code, and log it below. Stop and ask
the owner (write a deviation note below: planned / found / proposed / Goal Card line) when:
- a change would touch scope, a file another lane owns beyond the lines named above, or an
  interface another task depends on;
- the plan looks wrong against the Goal Card. Flagging a plan defect is welcome; pushing
  through one is not.
Never expand scope. If you finish early, stop; don't pick up another lane's task.

## Done means

All 3 tasks committed on `grok/ux-next-lane4-autosave` (one commit each), the logs below filled
in, and this doc committed with them. Then report to the owner: the commit SHAs, the gate
table, deviations, anything queued or deferred, and any concerns.

## Deviation log

| Task | Planned | Did instead | Why (Goal Card line) |
|---|---|---|---|
| 11 | `readOnly` on the note textarea and `UserInputControls` | Threaded `readOnly` through `GapCard` into `UserInputControls`; the note textarea is on the page | The answer field lives in those components. Keyboard edits while tailoring would otherwise be dropped. |
| 11 | Browser check stops the backend | The failed save was a 500 on the resolutions PATCH | Same failure the page handles. The status, toast, Try again, and leave prompt all showed. |
| 12 | Browser check stops the backend | Quick-tailor and market PUTs returned 500 | Same failure. Not saved, the toast, Try again, the leave prompt, and the market revert all showed. |

## Gate results

| Task | Gate | Result |
|---|---|---|
| 11 | pins `test_frontend_gap_autosave.py` | 6 passed; each pin failed alone when its guard was broken, then restored |
| 11 | `pytest tests/test_frontend_*.py` | 446 passed |
| 11 | tsc / lint / node | tsc clean; lint 0 errors, 5 baseline warnings; node 143 passed |
| 11 | slop | frontend and backend ratchet OK; duplication 468 lines / 39 clones (ceiling 481/40) |
| 11 | `npm run build` | OK |
| 11 | browser | Saving… from the first keystroke and again on the next character; delayed PATCH stays Saving… until it ends, then Saved; reload shows beforeunload; Back and the sidebar flush the note; failed save shows Save failed, a toast, Try again, and "Leave without saving?"; Enter on Try again keeps focus off `<body>` and lands on Saved |
| 12 | pins `test_frontend_settings_autosave.py` | 4 passed; each pin failed alone when its guard was broken, then restored |
| 12 | `pytest tests/test_frontend_*.py` | 450 passed |
| 12 | tsc / lint | tsc clean; lint 0 errors, 5 baseline warnings |
| 12 | slop | frontend and backend ratchet OK; duplication still 468/39 |
| 12 | `npm run build` | OK |
| 12 | browser | Failed quick-tailor switch: Not saved, toast, Try again, leave prompt; Enter on Try again shows Saving… with focus on the button, then Saves automatically with focus on the status. Failed market pick: select reverts, Not saved, no Try again; the next successful pick clears it. |

## Queued for Task 20 (SYSTEM.md changes Claude applies)

## Deferred to merge (edits left for Claude, with file:line)
