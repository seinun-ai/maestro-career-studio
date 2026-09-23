# UX next, wave 1 lane 2: Plain words and measured visuals — handoff to Cursor CLI / Grok 4.7

**Target agent/model:** Cursor CLI (`agent`), **Grok 4.7** (xhigh). If your session runs a
different model, stop and say so: the review tier depends on it.
**Tasks:** 3, 4, 5, 6, 7 of `docs/plans/2026-09-22-ux-next.md`, in that order.
**Branch:** `grok/ux-next-lane2-words` (from `claude/ux-next-plan` at `the commit that added this doc`).
**Worktree:** `/Users/ajeyds/Projects/maestro-ux-lanes/next-lane2-words` (dependencies are installed). Work only there.
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
4. The appendix sections your tasks cite: W1–W5 in `docs/plans/2026-09-22-ux-next-appendix-w-words-and-visuals.md` (its *Global constraints* and *Suggested task split* too). They hold the exact code; their
   line numbers are from `2cce6139`, so re-locate by the quoted code.

## Your tasks

1. **Task 3**: the `### Task 3` section of the main plan.
2. **Task 4**: the `### Task 4` section of the main plan.
3. **Task 5**: the `### Task 5` section of the main plan.
4. **Task 6**: the `### Task 6` section of the main plan.
5. **Task 7**: the `### Task 7` section of the main plan.

Per task: add the pins and see them FAIL → implement → run the task's gates → browser check →
one commit with the plan's commit message. End every commit message with
`Assisted-by: Grok 4.7 (Cursor CLI)`. Don't amend or squash earlier commits.

## Scope

**Files this lane owns:**
- Task 3: new `frontend/lib/describe-edit.ts` (+ `.test.ts`), new
  `frontend/components/edit-words-list.tsx`, `chat/edit-proposal-card.tsx`,
  `resume-editor/instruct-sheet.tsx`, one prop in `resume-editor/editor-body.tsx`, new
  `backend/tests/test_frontend_plain_words.py`
- Task 4: new `frontend/hooks/use-base-resume-label.ts`, `frontend/lib/types.ts`, the name call
  sites W2 lists (chat cards, `application-panel.tsx`, `ats-score-panel.tsx`,
  `proposals/proposals-section.tsx`, `app/jobs/[id]/tailor/[sessionId]/page.tsx`,
  `app/applications/page.tsx`, `resume-editor/project-port-dialog.tsx`,
  `app/base-resumes/page.tsx`, `chat/chat-page.tsx` and `career/send-to-resume-dialog.tsx` for
  the list-query copies), backend `app/schemas/application.py`, `app/routers/applications.py`,
  `docs/entities/application.md`, backend tests for the field, one pin in
  `test_frontend_analytics.py`
- Task 5: `frontend/components/ui/tabs.tsx`
- Task 6: `status-chip.tsx`, `career/entity-card.tsx`, `templates/requires-tex-badge.tsx` and the
  other amber-600 labels W3 names, `backend/tests/test_frontend_color_roles.py`
- Task 7: `settings/job-preferences-section.tsx`, `career/new-entity-dialog.tsx` (section
  presets only), `gap-analysis/resolution-controls.tsx`, `templates/template-gallery.tsx`,
  `templates/template-select.tsx`, the engine/status words in `app/templates/[id]/page.tsx`
- `docs/frontend-conventions.md`: only the bullets your tasks name. Other lanes edit other
  bullets of the same file in parallel, so never reflow or reorder text you didn't change.
- This handoff doc (its logs below).

**Files other lanes change at the same time:**
- **Lane 1** swaps the `next/link` import line in 31 files (several of yours) and adds
  leave-guard registration calls in the studios and the template editor. Don't edit import
  blocks you don't need to; keep your changes away from the registration calls.
- **Lane 3** edits the `LoadErrorState` branches in `ats-score-panel.tsx`,
  `proposals-section.tsx`, `app/applications/page.tsx`, `chat/chat-page.tsx`, `qa-tab.tsx`,
  `app/templates/page.tsx` and others, plus `app/templates/[id]/page.tsx`'s route-level error.
  Keep your edits in those files to the name/label/chip lines your task needs.

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

- **Task order inside this lane:** 3 then 4 (both edit `edit-proposal-card.tsx`), then 5, 6, 7.
- **Task 4 changes a backend response** (additive `base_resume_name`). Run the FULL backend
  suite for it (`pytest tests/ mcp_server/tests/ -q`, ~4 min): the MCP docstring budget ratchet
  and REST passthrough tests live there. Slop `check backend` too.
- **The Tailwind v4 trap** (W §Global constraints): `outline-none` next to `outline-2` paints
  nothing. Task 5 must verify the ring in a real browser.
- Contrast numbers must come from the computed pin (`test_frontend_color_roles.py` helpers),
  not from eyeballing.
- **What the reviewer checks hardest** (from five earlier Grok 4.7 lanes): pins that can't
  catch the regression they name, and loading / error / pending / empty states nobody forced.
  Mutation-check every pin you add (break the guarded code, see exactly that pin fail, restore
  from a backup copy). In the browser, force the slow, failing and double-click paths, and seed
  richer data than the minimum.

## Environment

- Python: `/opt/anaconda3/bin/python3`. Run pytest and ruff from `/Users/ajeyds/Projects/maestro-ux-lanes/next-lane2-words/backend`.
- Frontend (from `/Users/ajeyds/Projects/maestro-ux-lanes/next-lane2-words/frontend`): `npx tsc --noEmit`, `npm run lint` (0 errors; 5 baseline
  warnings), `node --test lib/*.test.ts`, and `npm run build` where a task asks.
- **Browser checks** use a throwaway stack on this lane's ports:
  - scratch dir `/tmp/maestro-next-lane2`; SQLite at `/tmp/maestro-next-lane2/app.sqlite3`;
  - backend from `/Users/ajeyds/Projects/maestro-ux-lanes/next-lane2-words/backend`: `DATABASE_URL=sqlite:////tmp/maestro-next-lane2/app.sqlite3`,
    every `*_DIR` variable in `backend/app/config.py` under the scratch dir,
    `ALLOWED_WEB_ORIGINS=http://127.0.0.1:3102,http://localhost:3102`,
    `PATH=/Library/TeX/texbin:$PATH`, then
    `/opt/anaconda3/bin/python3 -m uvicorn app.main:app --port 8772`;
  - frontend: run `npm run predev` if it exists (it copies Monaco; delete copied untracked
    files afterwards), then `API_PROXY_BACKEND=http://127.0.0.1:8772 npx next dev -p 3102`,
    and open `http://localhost:3102` (127.0.0.1 gets 403 on dev assets);
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
- Slop ratchet from `/Users/ajeyds/Projects/maestro-ux-lanes/next-lane2-words`:
  `python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check frontend` and
  `… check backend`; name both surfaces in your report.
  - **Frontend duplication ceiling for this lane: 505 duplicated lines, 42 clones** (the measured value at the branch
    point; the checked-in baseline says more). Several lanes merge into one branch, so hold
    your delta at zero or below. `slop_scan.py scan frontend --json` → `duplication`.
  - **Backend `complexity_hotspots` must stay at 424**: split a test that reaches cc 10.
  - Logic added in two places goes through a shared helper. Never reorder code to dodge the
    detector.
- Task 4: the full backend suite and `ruff check .`.

## Escalation (autonomy: peer)

You may adapt *how* when the plan conflicts with the code, and log it below. Stop and ask
the owner (write a deviation note below: planned / found / proposed / Goal Card line) when:
- a change would touch scope, a file another lane owns beyond the lines named above, or an
  interface another task depends on;
- the plan looks wrong against the Goal Card. Flagging a plan defect is welcome; pushing
  through one is not.
Never expand scope. If you finish early, stop; don't pick up another lane's task.

## Done means

All 5 tasks committed on `grok/ux-next-lane2-words` (one commit each), the logs below filled
in, and this doc committed with them. Then report to the owner: the commit SHAs, the gate
table, deviations, anything queued or deferred, and any concerns.

## Deviation log

| Task | Planned | Did instead | Why (Goal Card line) |
|---|---|---|---|
| 3 | Assign `doc` with no cast | Cast `customized_json` to `ResumeLike` at the assignment | The field is `Record<string, unknown>`; tsc rejects it as `ResumeLike`. Pin strings are unchanged. Speak the user's language. |

## Gate results

| Task | Gate | Result |
|---|---|---|
| 3 | pins `test_frontend_plain_words.py` | 4 passed; each pin failed alone under mutation, then restored |
| 3 | node `lib/*.test.ts` | 92 passed (6 new) |
| 3 | tsc / lint | tsc clean; lint 0 errors, 5 baseline warnings |
| 3 | `test_frontend_*.py` | 289 passed |
| 3 | slop frontend | OK; 495 duplicated lines, 41 clones (ceiling 505/42) |
| 3 | browser | slow load, failed apply, one-of-two clicks, reload section words, sheet propose-fail then sentence, apply closes. Light 1280 and dark 375. |

## Queued for Task 20 (SYSTEM.md changes Claude applies)

## Deferred to merge (edits left for Claude, with file:line)
