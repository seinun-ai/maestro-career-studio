# UX next, wave 1 lane 1: Leave guard — handoff to Cursor CLI / Grok 4.7

**Target agent/model:** Cursor CLI (`agent`), **Grok 4.7** (xhigh). If your session runs a
different model, stop and say so: the review tier depends on it.
**Tasks:** 1, 2 of `docs/plans/2026-09-22-ux-next.md`, in that order.
**Branch:** `grok/ux-next-lane1-leave-guard` (from `claude/ux-next-plan` at `the commit that added this doc`).
**Worktree:** `/Users/ajeyds/Projects/maestro-ux-lanes/next-lane1-leave-guard` (dependencies are installed). Work only there.
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
4. The appendix sections your tasks cite: U1 (all of it, including §Back/Forward) in `docs/plans/2026-09-22-ux-next-appendix-u-unsaved-work.md`. They hold the exact code; their
   line numbers are from `2cce6139`, so re-locate by the quoted code.

## Your tasks

1. **Task 1**: the `### Task 1` section of the main plan.
2. **Task 2**: the `### Task 2` section of the main plan.

Per task: add the pins and see them FAIL → implement → run the task's gates → browser check →
one commit with the plan's commit message. End every commit message with
`Assisted-by: Grok 4.7 (Cursor CLI)`. Don't amend or squash earlier commits.

## Scope

**Files this lane owns:**
- new `frontend/lib/leave-guard.ts` (+ `.test.ts`), `frontend/hooks/use-leave-guard.ts`,
  `frontend/components/guarded-link.tsx`; delete `frontend/hooks/use-unsaved-changes-warning.ts`
- `frontend/app/providers.tsx`
- the `next/link` import line (and only that line, plus the JSX tag name if the wrapper needs it)
  in the 31 files that import it today:
  `app/error.tsx`, `app/not-found.tsx`, `app/base-resumes/[slug]/page.tsx`, `app/new/page.tsx`,
  `app/applications/[id]/resume/page.tsx`, `app/applications/[id]/page.tsx`,
  `app/applications/page.tsx`, `app/templates/[id]/page.tsx`, `app/jobs/[id]/page.tsx`,
  `app/jobs/[id]/tailor/[sessionId]/page.tsx`, and in `components/`: `job-knockout-card`,
  `kb-sync-pill`, `app-sidebar`, `ats-score-panel`, `job-extraction-summary`,
  `career/entity-detail`, `career/inbox-panel`, `resume-health/health-badges`,
  `resume-health/health-report-page`, `setup/setup-status-strip`, `chat/kb-capture-card`,
  `resume-health/finding-cards`, `setup/upload-dialog`, `gallery/gallery-card`,
  `setup/getting-started-card`, `resume-editor/tailored-resume-studio`,
  `resume-editor/editor-body`, `analytics/base-summary-cards`, `proposals/proposal-agent-panel`,
  `proposals/proposals-section`, `analytics/gap-tiers-panel`
- the leave-guard registration lines in `resume-editor/editor-body.tsx`,
  `resume-editor/tailored-resume-studio.tsx` and `app/templates/[id]/page.tsx` (where they call the
  old `useUnsavedChangesWarning` today)
- new `backend/tests/test_frontend_leave_guard.py`
- `docs/frontend-conventions.md`: only the bullets your tasks name. Other lanes edit other
  bullets of the same file in parallel, so never reflow or reorder text you didn't change.
- This handoff doc (its logs below).

**Files other lanes change at the same time:**
- **Lane 2** (words and visuals) edits `ats-score-panel.tsx`, `application-panel.tsx`,
  `proposals-section.tsx`, `app/applications/page.tsx`, `app/templates/[id]/page.tsx`,
  `editor-body.tsx` (one prop) and the chat cards. **Lane 3** (focus core) edits the
  `LoadErrorState` callers, including `app/applications/[id]/page.tsx`, `app/jobs/[id]/page.tsx`,
  `ats-score-panel.tsx`, `proposals-section.tsx`, `proposal-agent-panel.tsx`,
  `health-report-page.tsx`, `getting-started-card.tsx`, and the four route-level error screens.
  In those files touch only the import line, the `<Link` tag name if needed, and the
  registration call; nothing else. Claude resolves import-line conflicts at merge.

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

- **`onNavigate` is synchronous** (U §0.1): the guard cancels first, asks with the repo's
  `useConfirm`, and replays the navigation through the router on Leave. Read
  `frontend/node_modules/next/dist/client/app-dir/link.js` and the Link docs before coding.
- **The tailored studio registers `unsaved`**, not `dirty` (Back right after a Save must not ask).
- **Task 2 depends on a Next internal** (U1 §Back/Forward). Name it in a code comment and in the
  conventions bullet, and pin the listener so an upgrade that breaks it fails loudly.
- Decision 6 fixes the prompt copy and buttons (Stay has initial focus).
- **What the reviewer checks hardest** (from five earlier Grok 4.7 lanes): pins that can't
  catch the regression they name, and loading / error / pending / empty states nobody forced.
  Mutation-check every pin you add (break the guarded code, see exactly that pin fail, restore
  from a backup copy). In the browser, force the slow, failing and double-click paths, and seed
  richer data than the minimum.

## Environment

- Python: `/opt/anaconda3/bin/python3`. Run pytest and ruff from `/Users/ajeyds/Projects/maestro-ux-lanes/next-lane1-leave-guard/backend`.
- Frontend (from `/Users/ajeyds/Projects/maestro-ux-lanes/next-lane1-leave-guard/frontend`): `npx tsc --noEmit`, `npm run lint` (0 errors; 5 baseline
  warnings), `node --test lib/*.test.ts`, and `npm run build` where a task asks.
- **Browser checks** use a throwaway stack on this lane's ports:
  - scratch dir `/tmp/maestro-next-lane1`; SQLite at `/tmp/maestro-next-lane1/app.sqlite3`;
  - backend from `/Users/ajeyds/Projects/maestro-ux-lanes/next-lane1-leave-guard/backend`: `DATABASE_URL=sqlite:////tmp/maestro-next-lane1/app.sqlite3`,
    every `*_DIR` variable in `backend/app/config.py` under the scratch dir,
    `ALLOWED_WEB_ORIGINS=http://127.0.0.1:3101,http://localhost:3101`,
    `PATH=/Library/TeX/texbin:$PATH`, then
    `/opt/anaconda3/bin/python3 -m uvicorn app.main:app --port 8771`;
  - frontend: run `npm run predev` if it exists (it copies Monaco; delete copied untracked
    files afterwards), then `API_PROXY_BACKEND=http://127.0.0.1:8771 npx next dev -p 3101`,
    and open `http://localhost:3101` (127.0.0.1 gets 403 on dev assets);
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
- Slop ratchet from `/Users/ajeyds/Projects/maestro-ux-lanes/next-lane1-leave-guard`:
  `python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check frontend` and
  `… check backend`; name both surfaces in your report.
  - **Frontend duplication ceiling for this lane: 505 duplicated lines, 42 clones** (the measured value at the branch
    point; the checked-in baseline says more). Several lanes merge into one branch, so hold
    your delta at zero or below. `slop_scan.py scan frontend --json` → `duplication`.
  - **Backend `complexity_hotspots` must stay at 424**: split a test that reaches cc 10.
  - Logic added in two places goes through a shared helper. Never reorder code to dodge the
    detector.
- `npm run build` for both tasks (the provider change and 31 import swaps).

## Escalation (autonomy: peer)

You may adapt *how* when the plan conflicts with the code, and log it below. Stop and ask
the owner (write a deviation note below: planned / found / proposed / Goal Card line) when:
- a change would touch scope, a file another lane owns beyond the lines named above, or an
  interface another task depends on;
- the plan looks wrong against the Goal Card. Flagging a plan defect is welcome; pushing
  through one is not.
Never expand scope. If you finish early, stop; don't pick up another lane's task.

## Done means

All 2 tasks committed on `grok/ux-next-lane1-leave-guard` (one commit each), the logs below filled
in, and this doc committed with them. Then report to the owner: the commit SHAs, the gate
table, deviations, anything queued or deferred, and any concerns.

## Deviation log

| Task | Planned | Did instead | Why (Goal Card line) |
|---|---|---|---|
| 1 | `leave-guard.ts` comment names `beforeunload` | Comment says "page unload" | The one-listener pin counts that word. A comment is not a second listener, and the pin stays strict. |
| 1 | Hook comment quotes "Leave without saving?" | Comment says "ask before leaving" | The copy pin requires that sentence once, in `useConfirmLeave`. |
| 1 | Pin matches `from "next/link"` only | Also matches single quotes, and `\bawait\b` rather than the substring | A quote swap would miss the pin. The appendix comment says "awaited" before `preventDefault`, which is not the keyword. |
| 1 | Conventions bullet covers Back/Forward in Task 1 | Task 1 bullet covers links, reload, and `useConfirmLeave`. Task 2 adds the Back/Forward sentences to that same bullet | Don't document a guard this commit does not implement. |
| 1 | Handoff file list stops at `providers.tsx` | Added `components/leave-guard-listeners.tsx` | The pin and U1 name that file as the one `beforeunload` listener. |
| 1 | Leave the tailored comment that the leave warning reads `dirty` | Comment now says the leave guard reads `unsaved` | The sentence would be false once the call moved below `unsaved`. |
| 2 | The appendix snippet only | Also count Back presses while the dialog is open, undo them with `history.go`, then apply Stay or Leave | U1's edge table and browser check 8. A second Back otherwise renders that page under the dialog. Honesty about unsaved work. |
| 2 | Call `history.back()` from inside the `popstate` handler | `setTimeout(0)` before that call | Chrome ignores `history.back()` dispatched during `popstate`. |
| 2 | Browser check drives Back with the keyboard shortcut as well as `page.goBack()` | `page.goBack()` passed, including a second Back. `Meta+[`, `Alt+Left`, and `Meta+Left` did not invoke Chrome's Back command | Playwright delivers those chords to the page. Chrome handles them in the browser chrome. `goBack` is the traversal those shortcuts perform. |

## Gate results

| Task | Gate | Result |
|---|---|---|
| 1 | pins | 8 passed. Each pin failed alone when its guarded line was broken, then restored from a backup copy |
| 1 | `node --test lib/*.test.ts` | 92 passed (6 new) |
| 1 | `tsc --noEmit` | clean |
| 1 | `npm run lint` | 0 errors, 5 baseline warnings |
| 1 | `pytest tests/test_frontend_*.py` | 293 passed |
| 1 | slop frontend | check OK; duplication 505 lines / 42 clones |
| 1 | slop backend | check OK; `complexity_hotspots` 424 |
| 1 | `npm run build` | passed |
| 1 | browser U1 1–6 plus slow save, failed save, double-click | 15/15 passed. Playwright on Chrome, `http://localhost:3101`, made-up River Hale data. Stay took initial focus and returned to the link (including the 375px sheet). Leave did not raise `beforeunload`. Save-then-Back on the tailored studio did not ask while the refetch was held. Template reload raised one `beforeunload`; Save then Back did not ask |
| 2 | sentinel pin | passed. Failed alone when capture was removed, when the `__NA` spread was removed, and when `onSentinel()` no longer selected `router.replace`. Restored from backup copies |
| 2 | `node --test lib/leave-guard.test.ts` | 6 passed |
| 2 | `tsc --noEmit` | clean |
| 2 | `npm run lint` | 0 errors, 5 baseline warnings |
| 2 | `pytest tests/test_frontend_*.py` | 294 passed (9 in the leave-guard file) |
| 2 | slop frontend | check OK; duplication 505 lines / 42 clones |
| 2 | slop backend | check OK; `complexity_hotspots` 424 |
| 2 | `npm run build` | passed |
| 2 | browser U1 7–8 | Passed with `page.goBack()`. Clean studio: one Back, no prompt. Dirty: Back asks, Stay keeps the URL and the edit, Leave goes back one entry. Save, then Back: one press, no prompt, sentinel already popped. Two client-side Backs while the dialog is open: Stay returns to the studio with the edit. A full `page.goto` history entry cannot be stopped (the document unloads); the check used link clicks |

## Queued for Task 20 (SYSTEM.md changes Claude applies)

## Deferred to merge (edits left for Claude, with file:line)
