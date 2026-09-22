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
| 14 | Pin "passes `mark=`" and alt mentions "sample", no test file named | New `backend/tests/test_frontend_template_preview.py`. The alt pin matches the alt template literal, and the shell must render `mark` at `top-1.5 right-1.5` | A file-wide "sample" substring already passes: the component comment says "sample resume". No owned pin file covered thumbnails (conventions change with a pin CI actually runs) |
| 15 | Comment only in `studio-toolbar.tsx` | Same sentence also sits on `const kind = "base"` in `health-report-page.tsx` | The prop is gone; the constant is the only thing stopping a later reader from threading `kind` back in (honesty: the page is base-only, MCP is not) |
| 16 | Focus the new header button inside `onCreated` | A ref flag set before the cache update, then `useEffect` focuses the button once `populated` is true | The button does not exist until that commit. Focusing in the success handler lands on nothing (accessibility: focus must not drop to `<body>`) |
| 16 | Hardcoded `referral-*` field ids | `useId()` per field | The form can mount in the empty-state card and in the dialog; conventions say ids come from `useId()` |
| 14, 16 (review) | Task 16 pinned by its one `_QUERY_SURFACES` entry; Task 14 pinned by `\bmark=`; the add dialog's fields live in `ReferralForm` | New `test_frontend_referrals.py` (error state, `initialFocus`, confirmed delete, focus after the first create, header action only beside the table, `<Label optional>`, `useId()`, grid rows, the draft). Task 14 pins `mark="Sample"` and the `showImage &&` gate. The draft moved up to `ReferralsPage` and clears only after a create succeeds; the dialog gained a `DialogDescription`; the no-op `useMemo` in `health-report-page.tsx` is gone. Each pin was mutation-checked | Review showed the old pins passed with every one of those behaviours broken. Planner decision: Esc or an overlay click unmounted `DialogContent` and lost the typed text ("if a gesture could lose typed text, it asks or keeps the text") |
| 16 | B §5 leaves the create-form placeholders unprefixed; edit rows unchanged | New `ReferralForm` placeholders are `e.g. …`. Edit-row placeholders stay `Jane Doe` / `Met at the AWS meetup` | Lane note: new referral UI follows owner decision 3. B §5 says the edit rows are unchanged, so Task 17 still owns those two |
| 16 (review) | The create `useMutation` lives in `ReferralForm`, with the draft on `ReferralsPage` | `ReferralsPage` owns the one create and hands both forms `adding={create.isPending}` and `onAdd={create.mutate}`; `canSubmit` ends `&& !adding`, and success clears the draft, closes the dialog and raises the focus flag only when the cache was empty. Two new pins, two adjusted (focus flag, draft clear); each mutation-checked | Browser: with the POST delayed, Esc then reopen showed the kept draft with an enabled submit, and a second submit made two identical rows. "If a gesture could lose typed text, it asks or keeps the text" kept the text but not the request behind it |

## Gate results

| Task | Gate | Result |
|---|---|---|
| 14 | `test_frontend_template_preview.py` + every `test_frontend_*.py` | 158 passed |
| 14 | tsc / lint / `node --test lib/*.test.ts` | clean / 0 errors, 5 warnings / 67/67 |
| 14 | slop `check frontend` / `check backend` | OK / OK. Duplication 517 lines, 43 clones (ceiling) |
| 14 | browser | `/templates`: 6 "Sample" marks, top-right (6px/6px). Picker dialog: 6, same corner. Base resume "Lane Four" thumbnail: 0 Sample marks, alt "Lane Four preview". Stale chip tooltip not reachable (see Deferred) |
| 15 | health pins (`test_frontend_health_report.py`, `test_frontend_color_roles.py`, `test_frontend_query_error_states.py`) + every `test_frontend_*.py` | 158 passed |
| 15 | `test_get_application_lint_404_without_a_report` | passed. GET `/api/resume-lint/application/{id}` is 404 "No health report yet" with no stored report. The endpoint already behaved this way; the test locks it |
| 15 | tsc / lint / node / `npm run build` | clean / 0 errors, 5 warnings / 67/67 / build OK. Route table has `/base-resumes/[slug]/health` and no `/applications/[id]/health` |
| 15 | slop `check frontend` / `check backend` | OK / OK. Duplication still 517 lines, 43 clones |
| 15 | browser | `/base-resumes/lane4_sample/health` renders "Resume health report" / "Lane Four" / "No health report yet." `/applications/00000000-0000-4000-8000-000000000001/health` renders "Page not found" |
| 16 | referrals pin + every `test_frontend_*.py` | 159 passed |
| 16 | tsc / lint / node | clean / 0 errors, 5 warnings / 67/67 |
| 16 | slop `check frontend` / `check backend` | OK / OK. Duplication still 517 lines, 43 clones |
| 16 | browser 768 and 375 | Empty page is the "Add your first referral" form (768). First create moves focus to the header "Add referral" button (`activeElement` is that button, not `<body>`), then the table. Dialog opens with initial focus on Company. At 768 the first two fields are side by side and the dialog fits (512px). At 375 the dialog fits (16px inset, not clipped, fields stacked). Delete button is on the row; `ReferralViewRow` still `await confirm(...)` before delete. The confirm click itself was not completed |

## Queued for Task 18 (SYSTEM.md changes Claude applies)

Task 15: none. SYSTEM.md does not describe a web tailored-health route. MCP health tools already document `kind='application'` (§7); that surface stays.

Found in review, not fixed on this branch (candidates for §11):
- Referrals: focus drops to `<body>` only after deleting the LAST row (the table unmounts for the empty-state form). Other deletes land on the header "Add referral" button (browser-verified).
- `/base-resumes/<unknown>/health` shows a skeleton for ~7s before "Couldn't load this resume.": the 404 goes through React Query's default 3 retries (1s + 2s + 4s backoff; `app/providers.tsx` sets no `retry`).
- Studio template button reads "Template: Default" while the picker's first row says "Use the default template" beside the resolved name ("Classic"). The picker names the resolution on purpose (comment at `components/templates/template-select.tsx` ~165); the button's `label` (~135) just maps `DEFAULT_TEMPLATE` to "Default", with no comment saying why. Looks like an omission; note only, lane 1 owns the file.
- `NewEntityDialog` (`components/career/new-entity-dialog.tsx`) has the gap the referral dialog had: its `onOpenChange` calls `reset()` on every close, so Esc or an overlay click loses typed text.
- The stale-chip tooltip on `/templates` can't be reached: `GalleryCard`'s stretched link is `absolute inset-0 z-10` and the chip sits under it (see *Deferred to merge*).

## Deferred to merge (edits left for Claude, with file:line)

- ~~`frontend/components/templates/template-select.tsx:163` (DialogTitle "Choose a template"): skipped the optional `<DialogDescription>Previews show a sample resume, not yours.</DialogDescription>`. Lane 1 owns this file.~~ Applied at merge by Claude.
- Stale-chip tooltip, not fixed (Task 14 step 3). On `/templates`, `elementFromPoint` at the centre of Harshibar's "needs re-validation" chip hits the stretched card link (`aria-label="Open Harshibar layout"`), not the chip. The `title` is set; hover cannot reach it because `GalleryCard`'s link is `absolute inset-0 z-10` and the chip is not lifted to z-20. Picker mode has no stretched link, so that page is the one that hides the tooltip.
- ~~Picker card accessible names omit "Sample" (not changed). B §6 hides the mark (`aria-hidden`) and puts "sample" in the image alt. In the picker the card is a button, and the a11y-tree names were "Carlito Dense ready latex" with no "sample". Manage-mode links are named "Open {template}". The alt is on the `<img>`, which is a separate node from that link.~~ Withdrawn: a reviewer verified that the `<img>` alt is part of the picker button's accessible name.
