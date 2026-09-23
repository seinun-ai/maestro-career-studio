# UX next, wave 2 lane 6: Studio focus, Cmd/Ctrl+S and one submit per click — handoff to Cursor CLI / Grok 4.7

**Target agent/model:** written for Cursor CLI (`agent`), Grok 4.7 (xhigh). **Executed by a
Claude Opus 5.5 subagent** after the owner stopped Cursor; commits carry a
`Co-Authored-By: Claude Opus 5.5` trailer instead of `Assisted-by: Grok 4.7`.
**Tasks:** 17, 18, 19 of `docs/plans/2026-09-22-ux-next.md`, in that order.
**Branch:** `grok/ux-next-lane6-studio-focus` (from `claude/ux-next-plan` at `the commit that added this doc`).
**Worktree:** `/Users/ajeyds/Projects/maestro-ux-lanes/next-lane6-studio-focus` (dependencies are installed). Work only there.
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
4. The appendix sections your tasks cite: F1 (including §"Also found by reading" and §C's diagnosis of "Edit raw JSON"), F3 and F4 in `docs/plans/2026-09-22-ux-next-appendix-f-focus-and-minor.md`. They hold the exact code; their
   line numbers are from `2cce6139`, so re-locate by the quoted code (wave 1 moved many of them).

## Your tasks

1. **Task 17**: the `### Task 17` section of the main plan.
2. **Task 18**: the `### Task 18` section of the main plan.
3. **Task 19**: the `### Task 19` section of the main plan.

Per task: add the pins and see them FAIL → implement → run the task's gates → browser check →
one commit with the plan's commit message. End every commit message with
`Assisted-by: Grok 4.7 (Cursor CLI)`. Don't amend or squash earlier commits.

## Scope

**Files this lane owns:**
- Task 17: `components/resume-editor/editor-shell.tsx`, `components/resume-editor/fullscreen-editor-page.tsx`, the contact / summary / certification editors, `components/resume-editor/studio-overflow.tsx` and the overlays it opens, `components/confirm-dialog.tsx`, Rebuild's `returnFocus` in `tailored-resume-studio.tsx`, the raw JSON pane's exits, `components/resume-editor/editable-card.tsx`, the chat rail toggles in `components/chat/chat-page.tsx`, the referral rows and last-row delete in `app/referrals/page.tsx`
- Task 18: `frontend/hooks/use-save-shortcut.ts`, `components/ui/chip-input.tsx`, the section-rename path, `components/resume-editor/editable-title.tsx`
- Task 19: `app/referrals/page.tsx` (create), `app/templates/page.tsx` (create), the studios' Save (`components/resume-editor/studio-save-button.tsx` or its callers)
- pins in `backend/tests/test_frontend_focus.py`, `test_frontend_studio.py`, `test_frontend_referrals.py` and any new `test_frontend_*.py` your tasks name
- `docs/frontend-conventions.md`: only the bullets your tasks name. Other lanes edit other
  bullets of the same file in parallel, so never reflow or reorder text you didn't change.
- This handoff doc (its logs below).

**Files other lanes change at the same time:**
- **Lane 4** owns the gap page, settings and `app/new/page.tsx`. **Lane 5** owns the dialogs (new base résumé, new career item, Ask for changes, demonstrate skill, send to résumé), `entity-detail.tsx`, `qa-tab.tsx` and the Career KB editors. Don't edit those. `instruct-sheet.tsx` (Ask for changes) is lane 5's even though ⋯ opens it: give it a return target from the ⋯ side (`finalFocus` on the caller) without editing its file, or note it under *Deferred to merge*.

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
- **Decision 11:** after a studio remount (Load latest, Rebuild, foreign adoption) focus lands on `FullscreenEditorPage`'s `<main tabIndex={-1}>`; after ⋯ → "Edit raw JSON" it returns to the ⋯ button.
- **Diagnose "Edit raw JSON" before fixing it** (F1 §C): record the focus events you observed in the deviation log.
- **F3's fix is `flushSync` + synchronous refocus**, not a key buffer; the "never saves less than the button would" rule stays (a chip or rename draft still commits before the save).
- **Studio Save gets `useSingleFlight` too** (decision 2).
- **What the reviewer checks hardest** (from five earlier Grok 4.7 lanes): pins that can't
  catch the regression they name, and loading / error / pending / empty states nobody forced.
  Mutation-check every pin you add (break the guarded code, see exactly that pin fail, restore
  from a backup copy). In the browser, force the slow, failing and double-click paths, and seed
  richer data than the minimum.

## Environment

- Python: `/opt/anaconda3/bin/python3`. Run pytest and ruff from `/Users/ajeyds/Projects/maestro-ux-lanes/next-lane6-studio-focus/backend`.
- Frontend (from `/Users/ajeyds/Projects/maestro-ux-lanes/next-lane6-studio-focus/frontend`): `npx tsc --noEmit`, `npm run lint` (0 errors; 5 baseline
  warnings), `node --test lib/*.test.ts`, and `npm run build` where a task asks.
- **Browser checks** use a throwaway stack on this lane's ports:
  - scratch dir `/tmp/maestro-next-lane6`; SQLite at `/tmp/maestro-next-lane6/app.sqlite3`;
  - backend from `/Users/ajeyds/Projects/maestro-ux-lanes/next-lane6-studio-focus/backend`: `DATABASE_URL=sqlite:////tmp/maestro-next-lane6/app.sqlite3`,
    every `*_DIR` variable in `backend/app/config.py` under the scratch dir,
    `ALLOWED_WEB_ORIGINS=http://127.0.0.1:3106,http://localhost:3106`,
    `PATH=/Library/TeX/texbin:$PATH`, then
    `/opt/anaconda3/bin/python3 -m uvicorn app.main:app --port 8776`;
  - frontend: run `npm run predev` if it exists (it copies Monaco; delete copied untracked
    files afterwards), then `API_PROXY_BACKEND=http://127.0.0.1:8776 npx next dev -p 3106`,
    and open `http://localhost:3106` (127.0.0.1 gets 403 on dev assets);
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
- Slop ratchet from `/Users/ajeyds/Projects/maestro-ux-lanes/next-lane6-studio-focus`:
  `python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check frontend` and
  `… check backend`; name both surfaces in your report.
  - **Frontend duplication ceiling for this lane: 481 duplicated lines, 40 clones** (the measured value at the branch
    point; the checked-in baseline says more). Several lanes merge into one branch, so hold
    your delta at zero or below. `slop_scan.py scan frontend --json` → `duplication`.
  - **Backend `complexity_hotspots` must stay at 424**: split a test that reaches cc 10.
  - Logic added in two places goes through a shared helper. Never reorder code to dodge the
    detector.
- `npm run build`.
- Real key events for Cmd/Ctrl+S (`keyboard.down("Meta")`, press, up) and a same-instant typing test.

## Escalation (autonomy: peer)

You may adapt *how* when the plan conflicts with the code, and log it below. Stop and ask
the owner (write a deviation note below: planned / found / proposed / Goal Card line) when:
- a change would touch scope, a file another lane owns beyond the lines named above, or an
  interface another task depends on;
- the plan looks wrong against the Goal Card. Flagging a plan defect is welcome; pushing
  through one is not.
Never expand scope. If you finish early, stop; don't pick up another lane's task.

## Done means

All 3 tasks committed on `grok/ux-next-lane6-studio-focus` (one commit each), the logs below filled
in, and this doc committed with them. Then report to the owner: the commit SHAs, the gate
table, deviations, anything queued or deferred, and any concerns.

## Deviation log

| Task | Planned | Did instead | Why (Goal Card line) |
|---|---|---|---|
| 17 | Diagnose "Edit raw JSON" (F1 §C) | Observed with focusin/focusout logging in Playwright (headless Chrome), both studios, before any change. **Keyboard** (⋯, Enter, ArrowDown, Enter): the trigger got `focusin` ~200 ms after the item's `focusout` and kept it for 6 s, so no drop. **Click**: the trigger never got `focusin`; the item's `focusout` fired with `relatedTarget: null` when the popup unmounted and focus stayed on BODY. Instrumenting `HTMLElement.prototype.focus` showed Base UI's focus-outside handler refocusing the (disappearing) popup and no call on the trigger | Focus never dropped to `<body>` |
| 17 | `finalFocus={triggerRef}` on the ⋯ menu | No `finalFocus` on the menu; `onOpenChangeComplete(false)` schedules `focusIfDropped(trigger)` on a zero-delay timeout. The explicit `finalFocus` did not fix the click path (still BODY) and it also overrode an overlay's initial focus: keyboard ⋯ → History opened with focus back on ⋯, outside the modal sheet. `onOpenChangeComplete` fires just before the popup unmounts (logged: focus still on the item), hence the timeout. The click path shows BODY for one ~30 ms sample before ⋯ | Focus never dropped to `<body>`; don't break initial focus |
| 17 | Confirm `finalFocus={() => opts?.returnFocus?.() ?? returnPoint.current() ?? true}` | Same resolution through a `returnTo` helper: a `tabIndex={-1}` target is focused by us (microtask, `focusIfDropped`) and Base UI gets `false`. Base UI focuses a container's first tabbable child, so Load latest landed on "Back to application", not `<main>` (decision 11) | Decision 11 |
| 17 | Studio `onClose` arms `focusNext(overflowRef)` for the raw pane's Apply and Cancel | Also a new optional `exitFocus` prop on `RawJsonToggle`, passed as the discard confirm's `returnFocus` (Cancel while it is still connected, else ⋯). Cancel with a pending draft confirms first, and the pane unmounts behind the dialog, so the studio's arming ran while focus was still in the dialog and the dialog then returned to `<main>` | Every exit lands on ⋯ |
| 17 | `useFocusOnNextCommit` inside `EditableCard`'s setter | Same, plus a small local `EditPane` component: `edit(close)` is called during render, and a closure over the focus refs passed into it fails the React Compiler `refs` lint; as a prop of a child component it passes | Lint at error level |
| 17 | `useEditToggle` as `toggle.*` | Destructured at every caller, and the hook takes a type parameter for the edit view (`<tr>` for a referral row). The lint reads `toggle.editRef` as a ref read during render | Lint at error level |
| 17 | `useFocusHandoff` on `ReferralsTable` for the LAST delete | Also: `focusableWhenDisabled` on each row's Delete and Save, a handoff on each view row, and a `tabIndex={-1}` wrapper around the table as the row's return target. The probe before any change showed a slow DELETE on a MIDDLE row also dropping focus to BODY (the confirm returned to a Delete button that had disabled itself) | Focus never dropped to `<body>` (same class, same file) |
| 17 | `finalFocus={overflowRef}` on `InstructSheet` (4 overlays in the base studio) | Not passed: `instruct-sheet.tsx` is lane 5's. Pin asserts 3. In the browser Escape from Ask for changes returned to ⋯ by Base UI's default on both paths (key and click). See *Deferred to merge* | Scope: lane 5 owns the file |
| 18 | Arm `focusNext` in the rename's `commitRename` and Escape | Also `e.preventDefault()` in the rename input's Enter branch. Focus now moves to the rename button inside Enter's keydown, and Enter's activation then pressed that button and reopened the rename (seen in the browser; the chip edit and the title already prevented default) | Focus lands somewhere sensible; no surprise reopen |
| 18 | Browser: `keyboard.down("Meta")`, press, up, then type | Both that and a burst (the chord and the keys sent over CDP without waiting between them, so they queue behind the chord). A/B against the old hook: it lost the typed keys in every case (Playwright sequence: `abc` kept, `xyz` lost; burst, mid-caret and Ctrl+S too); the new hook kept all of them | Never lose typed text |
| 19 | F4's pin `f"{name}.mutate(" not in …` | `f"{name}.mutate" not in …` (no parenthesis), plus no `.reset(`. The mutation check showed the call-only form missing `onAdd={create.mutate}` (a guarded mutation handed on unguarded) | Pins that catch the regression they name |
| 19 | New `test_frontend_single_flight.py` with F4's full `_SITES` | This lane's four sites only (Referrals, Templates, both studios' Save); lane 5 owns the other five. See *Deferred to merge* | Scope |

## Gate results

| Task | Gate | Result |
|---|---|---|
| 17 | pins | `test_frontend_focus.py` 20 passed (12 new, seen failing first: 11 failed before the code); every `test_frontend_*.py` 491 passed |
| 17 | mutation check | 28 mutants, 28 killed, each by exactly the pin that names it (`/tmp/maestro-next-lane6/muts17.json`) |
| 17 | tsc / lint / node | clean / 0 errors, 5 baseline warnings / 143 of 143 |
| 17 | build | `npm run build` OK |
| 17 | slop | frontend OK, duplication 448 lines / 37 clones, down from 468/39 (the ceiling; clean `git archive` export); backend OK, `complexity_hotspots` 424 (one new pin reached cc 13 and was split) |
| 17 | browser | Playwright (headless Chrome, real keys and clicks), both studios, light and dark: every control in F1's list lands on a named target, never BODY (see report) |
| 18 | pins | `test_frontend_studio.py` 60 passed (4 new, seen failing first); every `test_frontend_*.py` 495 passed |
| 18 | mutation check | 14 mutants, 14 killed by the pin that names them (`muts18.json`, `muts18b.json`) |
| 18 | tsc / lint / node / build | clean / 0 errors, 5 warnings / 143 of 143 / OK |
| 18 | slop | frontend OK, 448/37 (clean export); backend OK, hotspots 424 |
| 18 | browser | Playwright, real key events: Summary (tailored) and a contact field keep every key typed with the chord (end and mid-text caret), Ctrl+S too; the chip add row's `Kafka` is saved and `Flink` lands in the add row; an inline chip edit, a section rename and the title save and hand focus to the add row, the rename button, the pencil; two chords 50 ms apart made one PUT |
| 19 | pins | `test_frontend_single_flight.py` 8 passed (new, 8 failed first), `test_frontend_referrals.py` updated; every `test_frontend_*.py` 503 passed |
| 19 | mutation check | 6 mutants, 6 killed by the pins that name them (`muts19.json`) |
| 19 | tsc / lint / node / build | clean / 0 errors, 5 warnings / 143 of 143 / OK |
| 19 | slop | frontend OK, 448/37 (clean export); backend OK, hotspots 424 |
| 19 | browser | Before the fix: a same-task double click, a real `dblclick` and Enter twice each made two referral rows; Templates made a 200 then a 409; each studio's Save made two writes. After: one request each; a forced 500 then a retry makes exactly one row / one save (the guard clears on error) |
| all | full backend | `pytest tests/ mcp_server/tests/ -q`: 4804 passed, 2 skipped (base 4780 + 24 new pins) |
| all | ruff / SYSTEM.md gate | `ruff check` on the three pin files: clean / `check_system_md.py` OK, 999/1000 |

## Queued for Task 20 (SYSTEM.md changes Claude applies)

- **§11 item 29** (Task 17): deleting the last referral now hands focus to `#main-content`
  (and any other delete to the table). Narrow the item to: "Focus lands on `<body>`: Escape on
  the <768px sidebar sheet (which also stays open after a nav link is tapped)."
- **§11 candidate, not this lane's scope (owner's call)**: the throwaway backend segfaulted
  twice during these checks inside `libpdfium` (`FPDF_LoadPage`, crash reports
  `~/Library/Logs/DiagnosticReports/python3.13-2026-09-23-*.ips`) while `/templates` fired its
  gallery previews in parallel. `app/services/pdf_preview.py` calls `pypdfium2` with no lock,
  and PDFium is not thread-safe; FastAPI runs those sync handlers on a thread pool.

## Deferred to merge (edits left for Claude, with file:line)

- **Task 17, `InstructSheet` return target** (lane 5 owns the file): add
  `finalFocus?: RefObject<HTMLElement | null>` to `InstructSheet` and pass it to its
  `<SheetContent>` (`frontend/components/resume-editor/instruct-sheet.tsx:110` at `8878731d`);
  pass `finalFocus={overflowRef}` at the base studio's `<InstructSheet`
  (`frontend/components/resume-editor/editor-body.tsx:618` on this branch); bump the count in
  `backend/tests/test_frontend_focus.py::test_every_overlay_the_menu_opens_takes_a_return_target`
  from 3 to 4. Today Escape returns to ⋯ through Base UI's default (verified by key and click),
  so this makes it deterministic rather than fixing a live drop.

- **Task 19, lane 5's single-flight sites**: this lane created
  `backend/tests/test_frontend_single_flight.py` with its own four sites in `_SITES`. If lane 5
  also creates that file (F4 names it), merge the two `_SITES` lists into one parametrized
  test (add-add conflict). Then widen the conventions sentence in the dialog-draft bullet
  ("So do the Templates Create, `/new`'s Extract and both studios' Save") to lane 5's sites
  (New career item, Capture/Read document, New base résumé, the Q&A generate buttons).
