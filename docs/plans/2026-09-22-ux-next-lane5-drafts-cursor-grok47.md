# UX next, wave 2 lane 5: Dialogs, Q&A and KB editors keep text — handoff to Cursor CLI / Grok 4.7

**Target agent/model:** written for Cursor CLI (`agent`), Grok 4.7 (xhigh). **Executed by a
Claude Opus 5.5 subagent**: the owner stopped Cursor, so the controller handed this lane to Claude
(commit trailers say `Co-Authored-By: Claude Opus 5.5`, and the duplication ceiling is the
post-lane-4 468 lines / 39 clones).
**Tasks:** 14, 15, 16 of `docs/plans/2026-09-22-ux-next.md`, in that order.
**Branch:** `grok/ux-next-lane5-drafts` (from `claude/ux-next-plan` at `the commit that added this doc`).
**Worktree:** `/Users/ajeyds/Projects/maestro-ux-lanes/next-lane5-drafts` (dependencies are installed). Work only there.
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
4. The appendix sections your tasks cite: U3 (all five dialogs), U4.1 and U4.2 in `docs/plans/2026-09-22-ux-next-appendix-u-unsaved-work.md`; F4's inventory entries for these dialogs, Q&A generation and the capture box in `docs/plans/2026-09-22-ux-next-appendix-f-focus-and-minor.md`. They hold the exact code; their
   line numbers are from `2cce6139`, so re-locate by the quoted code (wave 1 moved many of them).

## Your tasks

1. **Task 14**: the `### Task 14` section of the main plan.
2. **Task 15**: the `### Task 15` section of the main plan.
3. **Task 16**: the `### Task 16` section of the main plan.

Per task: add the pins and see them FAIL → implement → run the task's gates → browser check →
one commit with the plan's commit message. End every commit message with
`Assisted-by: Grok 4.7 (Cursor CLI)`. Don't amend or squash earlier commits.

## Scope

**Files this lane owns:**
- Task 14: `components/base-resumes/new-base-resume-dialog.tsx` and its getting-started caller, `components/career/new-entity-dialog.tsx` (keep Task 7's preset code), `components/resume-editor/instruct-sheet.tsx` (keep Task 3's `EditWordsList`), `components/resume-health/demonstrate-skill-dialog.tsx`, `components/career/send-to-resume-dialog.tsx`, `components/career/entity-detail.tsx`, the `keepMounted` change in the dialog primitive
- Task 15: `components/qa-tab.tsx`
- Task 16: the `useConfirmDiscard` helper (where U4.2 puts it), `components/career/notes-editor.tsx`, the point editor and inbox draft editor U4.2 names, `components/career/capture-box.tsx`
- pins in new or existing `backend/tests/test_frontend_*.py` files your tasks name
- `docs/frontend-conventions.md`: only the bullets your tasks name. Other lanes edit other
  bullets of the same file in parallel, so never reflow or reorder text you didn't change.
- This handoff doc (its logs below).

**Files other lanes change at the same time:**
- **Lane 4** owns the gap page, the settings sections and `app/new/page.tsx`. **Lane 6** owns the studios (including `editor-body.tsx`, `studio-overflow.tsx`, `confirm-dialog.tsx`), `chat-page.tsx`, `app/referrals/page.tsx` and `app/templates/page.tsx`. Don't edit those. If `keepMounted` needs a change in a shared UI primitive (`components/ui/dialog.tsx` / `sheet.tsx`), make it additive (an opt-in prop) so lane 6's dialogs are unaffected.

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
- **`keepMounted` on `send-to-resume-dialog` makes its `useBaseResumes()` query fetch on every KB entity page** (it now mounts with the page). Gate the query on `open` (the hook takes no enabled flag today: add an optional one, or pass `enabled` through) so the list isn't fetched until the dialog opens.
- **"Ask for changes" keeps its proposal only with the basis stamp** (U3.2; decision 8): a kept proposal applied after the résumé changed must refuse, with a plain message.
- **Decision 10:** Regenerate over any saved cover letter asks "Replace your cover letter?".
- **Decision 8's wording:** the dismiss button reads **Close**; only New base résumé gets **Start over** (no confirm).
- **What the reviewer checks hardest** (from five earlier Grok 4.7 lanes): pins that can't
  catch the regression they name, and loading / error / pending / empty states nobody forced.
  Mutation-check every pin you add (break the guarded code, see exactly that pin fail, restore
  from a backup copy). In the browser, force the slow, failing and double-click paths, and seed
  richer data than the minimum.

## Environment

- Python: `/opt/anaconda3/bin/python3`. Run pytest and ruff from `/Users/ajeyds/Projects/maestro-ux-lanes/next-lane5-drafts/backend`.
- Frontend (from `/Users/ajeyds/Projects/maestro-ux-lanes/next-lane5-drafts/frontend`): `npx tsc --noEmit`, `npm run lint` (0 errors; 5 baseline
  warnings), `node --test lib/*.test.ts`, and `npm run build` where a task asks.
- **Browser checks** use a throwaway stack on this lane's ports:
  - scratch dir `/tmp/maestro-next-lane5`; SQLite at `/tmp/maestro-next-lane5/app.sqlite3`;
  - backend from `/Users/ajeyds/Projects/maestro-ux-lanes/next-lane5-drafts/backend`: `DATABASE_URL=sqlite:////tmp/maestro-next-lane5/app.sqlite3`,
    every `*_DIR` variable in `backend/app/config.py` under the scratch dir,
    `ALLOWED_WEB_ORIGINS=http://127.0.0.1:3105,http://localhost:3105`,
    `PATH=/Library/TeX/texbin:$PATH`, then
    `/opt/anaconda3/bin/python3 -m uvicorn app.main:app --port 8775`;
  - frontend: run `npm run predev` if it exists (it copies Monaco; delete copied untracked
    files afterwards), then `API_PROXY_BACKEND=http://127.0.0.1:8775 npx next dev -p 3105`,
    and open `http://localhost:3105` (127.0.0.1 gets 403 on dev assets);
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
- Slop ratchet from `/Users/ajeyds/Projects/maestro-ux-lanes/next-lane5-drafts`:
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

All 3 tasks committed on `grok/ux-next-lane5-drafts` (one commit each), the logs below filled
in, and this doc committed with them. Then report to the owner: the commit SHAs, the gate
table, deviations, anything queued or deferred, and any concerns.

## Deviation log

| Task | Planned | Did instead | Why (Goal Card line) |
|---|---|---|---|
| 14 | `InstructSheet` takes a `basis` prop; `editor-body.tsx` passes `basis={serverKey(live.data)}` | The sheet computes `serverKey(resume)` from the `resume={live?.data}` prop it already gets (lane 2); `editor-body.tsx` is untouched | The same saved copy, and no edit in lane 6's file |
| 14 | Proposal state `{ result, basis }` read as `proposal.result.*` | State `kept`, with `const proposal = kept?.result ?? null`; a stale proposal is described with `describeEdits(proposal.ops, stale ? null : resume)`; lane 2's pin in `test_frontend_plain_words.py` updated to that | Words computed against the moved copy would name the wrong bullet ("never mislead") |
| 14 | New base résumé keeps its fixed `nbr_*` ids | Ids from `useId` (`ids.name`, …); `test_frontend_placeholders.py`'s hint-order pin follows, and its `_named` helper accepts a `useId` expression id | Getting started now keeps several forms mounted: a fixed id named the first (hidden) form's field, so the open form's label and hint pointed at nothing (a11y). Closes §11 item 32's `nbr_name_hint` clause |
| 14 | Start over clears the form | …and moves focus to the new form's first field (`useFocusOnNextCommit` on the popup) | The pressed button unmounts with the old form; focus is never dropped to `<body>` |
| 14 | Files named in the lane doc | Also edited the two callers the appendix names: `resume-health/finding-cards.tsx` (U3.3, one dialog per skill) and `app/career/page.tsx` (U3.5, drop `key`) | No other lane owns them; the fix needs the caller |
| 15 | Decision 10: Regenerate over a saved letter asks | Generate cover letter asks the same question when a saved letter exists | `routers/qa.py` deletes every saved cover letter before generating a new one, so Generate loses the edited letter too ("if a gesture could lose typed text, it asks") |
| 15 | Single-flight on Answer questions and Generate | Also Regenerate (one entry at a time: every Regenerate is disabled while one runs), and Regenerate waits while the letter is open for editing | "Every create and generate button"; a regenerate landing under an open draft would be overwritten by the next Save |
| 15 | Save gets `focusableWhenDisabled` | Answer questions, Generate cover letter and Regenerate too | They disable themselves on click, which dropped focus to `<body>` |
| 16 | `useConfirmDiscard` beside `useConfirm` in `components/confirm-dialog.tsx` | New `hooks/use-confirm-discard.ts` with `useConfirmDiscard` and `useDiscardableEditor(editing)` (`requestCancel(changed, close)`, `cancelOnEscape(event, changed, close)`, `returnFocus`, `editRef`), used by all three editors | `confirm-dialog.tsx` is lane 6's; one hook keeps the three editors from cloning the Escape and focus code (duplication stays at 468/39) |
| 16 | Focus return | Unconditional `editRef.current?.focus()` once `editing` turns false (the appendix's shape), not `focusIfDropped` | After Discard focus sits in the closing confirm, so an "only from `<body>`" check misses the drop |
| 16 | Capture box: single-flight only | Also `readOnly` textarea and a focusable Add to inbox while capturing; the point and draft Save arm the focus return on the unchanged-text close too | Focus never dropped to `<body>` |
| all | — | Extra commit `98c0b260` splits two Task 14 pins (cc 10 and 11) | Backend `complexity_hotspots` had moved 424 → 426 |

## Gate results

| Task | Gate | Result |
|---|---|---|
| base `8878731d` | pins / full backend / node / lint / duplication | 479 / 4780 passed, 2 skipped / 143 / 0 errors, 5 warnings / 468 lines, 39 clones |
| 14 `622275e1` | new pins | `test_frontend_dialog_drafts.py` 16 tests (18 after the split) seen to FAIL first; 35 mutants, each killed by exactly its pin (incl. lane 2's plain-words pin and the placeholders pin for ids) |
| 14 | tsc / lint / node / pins / slop | clean / 0 errors, 5 warnings / 143 pass / 495 pass / frontend 467 lines, 39 clones |
| 14 | browser | see *Browser checks* below: all pass |
| 15 `70cb7011` | new pins | `test_frontend_qa_tab.py` 11 tests seen to FAIL first; 18 mutants killed, each by its pin |
| 15 | tsc / lint / pins / slop | clean / 0 errors, 5 warnings / 506 pass / frontend 467 lines, 39 clones |
| 16 `f5723b07` | new pins | `test_frontend_kb_editors.py` 20 tests seen to FAIL first; 28 mutants killed, each by its pin |
| 16 | tsc / lint / pins / slop | clean / 0 errors, 5 warnings / 526 pass / frontend 468 lines, 39 clones (476/40 before the Escape handler moved into the hook) |
| final | full backend `pytest tests/ mcp_server/tests/ -q` (on `98c0b260`) | 4829 passed, 2 skipped (base 4780 + 49 new pins); pins 528 |
| final | `slop_scan.py check frontend` / `check backend` | ratchet OK / ratchet OK (hotspots 424 after `98c0b260`); frontend measured 468 lines, 39 clones on a clean tree before the build |
| final | ruff (new and edited pin files) / `npm run build` / `check_system_md.py` | All checks passed / OK / OK, 999/1000 (SYSTEM.md untouched) |

**Browser checks** (Playwright, headless Chrome, real keys and pointer, throwaway stack on 8775/3105, made-up seed; LLM
endpoints answered by a fetch wrapper with made-up bodies and forced delays/failures; `MAESTRO_CS_PDFLATEX=/nonexistent`
because every base résumé create 500'd on pdflatex here, see *Deferred*):
- **14 New base résumé:** the kept popup is in the DOM `hidden`/`display:none`; opening it adds no KB fetch of its own (the one
  on `/base-resumes` is `FirstRunImportCard`'s). Name + role + instruction, Suggest (2.5 s), Esc mid-"Suggesting": reopened,
  the name and instruction are kept and the plan landed into the closed form (Summary, Left off, pre-ticked entry). Overlay
  click: kept. Start over (keyboard): cleared, focus on the new Name field. Same-task double click on Create: one
  `POST /from-kb`, studio opened. The Name label names the visible input.
- **14 Getting started** (tracker faked empty, two faked suggestions): A typed, Esc (focus back on Compose), B opens empty,
  B typed, Close, A reopens with A's text, B with B's; label association holds with two forms mounted.
- **14 Ask for changes:** Propose from the keyboard keeps focus on the button ("Thinking…"), the textarea is read-only;
  Esc and reopen keep instruction + proposal; after a studio Save the note shows, words drop to "Rewrite a bullet in
  Experience", Apply is disabled and a forced click sends no PATCH; Propose again applies (server bullet changed); reopening
  after Apply is empty.
- **14 Demonstrate skill** (no-LLM health report): draft for Kubernetes, Esc, Terraform opens fresh, typed, Close;
  Kubernetes reopens with prose and draft, Apply lands (real content hash), chip "· done"; Terraform keeps its prose.
- **14 Send to résumé:** zero résumé-list fetches before opening; a point retired on the page drops out of the selection and
  a restored one is pre-selected (3/3); Adapt, edit a row, Esc, reopen keeps the review step and the edit; Esc during a 2.5 s
  Apply and reopen shows "Applying…" disabled with one request; after success reopening starts fresh.
- **14 New career item:** Projects draft kept through Esc and overlay, opened from Education it stays Project; an emptied
  form follows the tab (Experience, Education); same-task double click creates one entity; a forced 500 keeps the draft and the
  retry creates one.
- **15 Q&A:** Regenerate disabled while editing; forced 500 on Save: "Saving…" keeps focus, then the editor stays open with
  the text and focus on Save; a sidebar link asks "Leave without saving?" and Stay keeps it; the real Save shows the new letter
  with no frame of the old one (frames: EDITOR → NEW), focus on Edit; Regenerate and Generate on a saved letter ask "Replace
  your cover letter?" (Cancel focused) and Cancel sends nothing; a question's Regenerate double click and Answer questions
  double click each send one request.
- **16 KB editors:** notes: unchanged Esc closes at once (focus on Edit); changed Esc asks with Keep editing focused; Keep
  editing returns to the textarea with the text; Discard closes with focus on Edit and nothing saved; Cancel asks too; a
  keyboard Save keeps focus while saving (textarea read-only) and lands focus on Edit; a forced 500 keeps editor and text.
  Point editor: Cancel over a change asks, Discard focuses Edit point; an unchanged Save closes onto Edit point. Inbox draft:
  Esc asks, Keep editing keeps the text, Discard focuses Edit draft. Quick capture: same-task double click sends one capture
  and focus stays on the button; two file picks in one task send one ingest.
- Not run: light/dark and 375 px passes (no layout or colour changed), a real LLM.

## Queued for Task 20 (SYSTEM.md changes Claude applies)

- §11 item 32: delete the clause "`NewEntityDialog` calls `reset()` on close, so Esc or an overlay click loses typed text
  (Referrals keeps its draft);" (Task 14), and drop `nbr_name_hint` from the hardcoded-ids list ("four hint/control
  pairs" becomes three: `new_id_hint`/`new_id_error`, `kb-profile-notes-hint`, `job-preferences-locations-hint`).
- §11 candidates found in passing (not fixed, backend, out of this lane's scope): (a) `POST /api/base-resumes` and
  `POST /api/base-resumes/from-kb` return **500** "pdflatex failed" (`LaTeX Error: There's no line here to end`) on this
  machine's TeX for a blank and a KB-composed résumé, yet the row is created: §6 inv-render-fallback-explained says a
  committed write degrades to a persisted `render_error`, never a 500. (b) `POST /api/qa` with `cover_letter` deletes and
  commits every saved cover letter BEFORE the LLM call (`routers/qa.py`), so a failed generation loses the saved letter;
  the new confirm names the loss, but the order is still lossy.

## Deferred to merge (edits left for Claude, with file:line)

- Lane 6 (Task 17, F1 §C) wants `finalFocus={overflowRef}` on `InstructSheet`, which takes no such prop: add
  `finalFocus?: RefObject<HTMLElement | null>` and pass it to `<SheetContent>` at
  `frontend/components/resume-editor/instruct-sheet.tsx:110`; `editor-body.tsx:606` then passes it.
- `docs/frontend-conventions.md:543` ("A dialog keeps what the user typed, or paid for, across close") now carries F4's
  `useSingleFlight` sentence for dialog forms; lane 6's Task 19 (Referrals) may add the same sentence to the old bullet it
  replaced. Keep one.
- `useConfirmDiscard` lives in `frontend/hooks/use-confirm-discard.ts`, not `components/confirm-dialog.tsx` (lane 6's), so
  there is no conflict there; if lane 6 wants it beside `useConfirm`, move it at merge.
