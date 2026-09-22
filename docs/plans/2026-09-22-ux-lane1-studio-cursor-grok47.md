# UX follow-ups, lane 1: Studio correctness and layout — handoff to Cursor CLI / Grok 4.7

**Target agent/model:** Cursor CLI (`agent`), **Grok 4.7** (xhigh). If your session runs a
different model, stop and say so: the review tier depends on it.
**Tasks:** 4, 8, 9 of `docs/plans/2026-09-22-ux-followups.md`, in that order.
**Branch:** `grok/ux-lane1-studio` (from `claude/ux-followups` at the commit that added this doc, right after `2916d83f`).
**Worktree:** `/Users/ajeyds/Projects/maestro-ux-lanes/lane1-studio` (dependencies are installed). Work only there.
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

1. **Task 4** — the `### Task 4` section of the main plan.
2. **Task 8** — the `### Task 8` section of the main plan.
3. **Task 9** — the `### Task 9` section of the main plan.

Per task: add the pins and see them FAIL → implement → run the task's gates → browser check →
one commit with the plan's commit message. End every commit message with
`Assisted-by: Grok 4.7 (Cursor CLI)`. Don't amend or squash earlier commits.

## Scope

**Files this lane owns:**
- `frontend/components/resume-editor/tailored-resume-studio.tsx`, `editor-body.tsx`,
  `editor-shell.tsx`, `formatting-panel.tsx`, `pdf-pages-preview.tsx`, `contact-form.tsx`
- `frontend/components/templates/template-select.tsx` (home of `useTemplateDefaults`; Task 4
  adds its loaded flag)
- `frontend/app/templates/[id]/page.tsx`
- new `frontend/hooks/use-local-storage-state.ts`
- `frontend/components/chat/chat-page.tsx`: only Task 8's rail-preference adoption
- `backend/tests/test_frontend_studio.py` (no other lane edits it)
- `docs/frontend-conventions.md`: only the bullets your tasks name. Other lanes edit other
  bullets of the same file in parallel, so never reflow or reorder text you didn't change.
- This handoff doc (its logs below).

**Files other lanes change at the same time:**
- `tailored-resume-studio.tsx` and `formatting-panel.tsx`: lane 2 (Task 10) changes the tab
  count's classes, the "Customized" chip and adds `aria-pressed` to the segmented buttons.
  Leave those lines alone.
- `chat-page.tsx`: lane 2 (Task 10) restyles "New chat" and adds `aria-current` to the active
  session. Touch only the rail preference.
- `app/templates/[id]/page.tsx` and `pdf-pages-preview.tsx`: lane 2 (Task 6) swaps a few
  hand-rolled `red-*` classes for the destructive token. Don't reformat around them.

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

- **Tasks 1–3 already landed** and changed the studios since the appendices were
  written: own saves adopt in place (no remount; the adoption runs in a `useLayoutEffect`),
  `keepIfEdited` guards post-save adoption, and raw-JSON drafts count as unsaved
  (`useRawJsonDraft`). Read SYSTEM.md §12 "Studio external-edit dirty-guard" and the
  conventions *Tailored studio*, *Cmd/Ctrl+S* and *Raw JSON* bullets before editing a
  studio. Re-locate every appendix line number by the quoted code.
- **Task 4:** the plan text's "Amended by Task 1's review" paragraph is part of the spec.
  `useTemplateDefaults` lives in `components/templates/template-select.tsx`; its three
  FormattingPanel callers are the two studios and the template editor page.
- **Task 8:** `clampPreviewPct` and `parsePreviewPct` already exist in `lib/studio.ts`
  (Task 1). This task must LOWER frontend duplication.
- **Task 9:** the 768px check is the base studio's Contact block.

## Environment

- Python: `/opt/anaconda3/bin/python3`. Run pytest and ruff from `/Users/ajeyds/Projects/maestro-ux-lanes/lane1-studio/backend`
  (the cwd wins on `sys.path`, so tests import this worktree's code).
- Frontend (from `/Users/ajeyds/Projects/maestro-ux-lanes/lane1-studio/frontend`): `npx tsc --noEmit`, `npm run lint`,
  `node --test lib/*.test.ts`, and `npm run build` where a task asks.
- **Lint has the React Compiler rules at error level** (`react-hooks/refs`,
  `set-state-in-effect`, `set-state-in-render`). Run lint after every step. Baseline:
  0 errors, 5 warnings.
- **Node tests aren't in CI.** Pair every `lib/*.ts` behaviour with a pytest source pin in
  `backend/tests/test_frontend_*.py`.
- **Browser checks** use a throwaway stack on this lane's ports (other lanes use others):
  - scratch dir `/tmp/maestro-lane1`; SQLite at `/tmp/maestro-lane1/app.sqlite3`;
  - backend: from `/Users/ajeyds/Projects/maestro-ux-lanes/lane1-studio/backend`,
    `DATABASE_URL=sqlite:////tmp/maestro-lane1/app.sqlite3`, every `*_DIR` variable
    SYSTEM.md lists pointed under the scratch dir,
    `ALLOWED_WEB_ORIGINS=http://127.0.0.1:3101,http://localhost:3101`,
    `PATH=/Library/TeX/texbin:$PATH`, then
    `/opt/anaconda3/bin/python3 -m uvicorn app.main:app --port 8771` (startup runs
    alembic);
  - frontend: `API_PROXY_BACKEND=http://127.0.0.1:8771 npx next dev -p 3101`;
  - seed MADE-UP data through the API; no LLM keys are needed;
  - use real key and pointer events (a Playwright/browser tool), not synthetic JS events;
  - tear the stack down afterwards.

  If you have no browser tool, write "not run" for that check in the gate table. Claude runs
  every browser check again at merge anyway.

## Gates (per task, and all of them before you report done)

- The task's pins, plus every `backend/tests/test_frontend_*.py`.
- tsc clean; lint 0 errors; node tests pass.
- Slop ratchet, from `/Users/ajeyds/Projects/maestro-ux-lanes/lane1-studio`:
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

All 3 tasks committed on `grok/ux-lane1-studio` (one commit each), the three logs below
filled in, and this doc committed with them. Then report to the owner: the commit SHAs, the
gate table, deviations, anything queued or deferred, and any concerns.

## Deviation log

| Task | Planned | Did instead | Why (Goal Card line) |
|---|---|---|---|
| 4 | Expose a `loaded` flag from `useTemplateDefaults` and pass `defaultsLoaded` into all three FormattingPanel callers. | The panel disables every knob while `supportedKeys === undefined`. That is `useSupportedFmtKeys`' loading sentinel, and both hooks read `["templates", "all"]`. The template editor still mounts the panel only after its own query resolves and passes a concrete key list. Conventions gained a *Formatting controls* sub-bullet plus the Re-score / Generate PDF sentence on *Tailored studio* and *Empty preview*. | The amendment allows gating on the templates query. A `defaultsLoaded` prop on both studio panels extended an existing 21-line clone to 22 and put this lane over its 517-line ceiling. No new dependency; knobs stay disabled until the overlay is real (honesty). |
| 8 | A2 §6's risk note: give the chat history edge tab the same in-flow rail. The two dismiss cards were optional. | Left the chat tab absolutely positioned and did not adopt the dismiss cards. The sheet-close effect became a `matchMedia` listener so `chat-page.tsx` no longer carries a `set-state-in-effect` disable. | Handoff: chat-page is only the rail preference; lane 2 owns the rest of that file. Dismiss cards are marked optional. The listener keeps the desktop-crossing close without the disable the pin forbids. |
| Review fixes (Claude) | Task 4: disable the knobs while `supportedKeys === undefined`. Task 8/9 pins as committed. | `FormattingPanel` takes a required `FormattingBaseline` state (`loading` / `error` / `ready`) in place of the `supportedKeys?` sentinel. A failed templates fetch shows a `LoadErrorState` with a retry instead of "Loading…" forever. The tailored studio's base-resume layer is gated the same way (`overlayBaseline`). `useTemplateDefaults` + `useSupportedFmtKeys` became one `useTemplateBaseline` over one shared `useTemplatesQuery`. The Task 4 pin split per concern (backend hotspots back to 424). Added Task 8 pins for persist-on-release, shell sizing and double-click reset. Corrected the chat rail's "first frame" comment. | Honesty: a failed fetch must not read as a wait, and a knob must not be diffed against a baseline missing a layer. The required prop makes "not ready" explicit at every caller. No new dependency; frontend duplication 517 → 516 lines, 43 clones. |

## Gate results

| Task | Gate | Result |
|---|---|---|
| 4 | `test_frontend_studio.py` pins, then every `backend/tests/test_frontend_*.py` | pass |
| 4 | `npx tsc --noEmit` | clean |
| 4 | `npm run lint` | 0 errors, 5 warnings (baseline) |
| 4 | `node --test lib/*.test.ts` | 67 pass |
| 4 | slop frontend | OK. Duplication 517 lines, 43 clones (lane ceiling; delta 0) |
| 4 | slop backend | `complexity_hotspots` 424 → 425. The new pin `test_formatting_controls_wait_for_template_defaults` is CC 10 (asserts count). Not re-baselined; Claude re-baselines at merge. |
| 4 | browser | pass. With `/api/templates` held, the base studio's Formatting panel read "Loading template defaults…" and every knob was disabled. After a normal load, Experience down then up returned "All changes saved" in both studios. On the Harshibar application a 12pt edit kept Certifications in the order (no Custom sections). Saving that edit: Re-score stayed disabled through "Rendering PDF…", then the chain's own re-score ran. |
| 8 | Task 8 pins plus every `backend/tests/test_frontend_*.py` | pass |
| 8 | `npx tsc --noEmit` | clean |
| 8 | `npm run lint` | 0 errors, 5 warnings (baseline) |
| 8 | `node --test lib/*.test.ts` | 67 pass |
| 8 | slop frontend | OK. Duplication held at 517 lines, 43 clones. The three hydrate copies were under the 50-token clone threshold, so removing them did not lower the count. |
| 8 | slop backend | Still 425 hotspots from Task 4's pin (CC 10). This task added none. Not re-baselined. |
| 8 | browser | pass. Sidebar open: a pointer drag moved the divider (45% → 55%) and localStorage stayed unset until release (`55.3`), then double-click stored `45`. Widen/Narrow stepped 45 → 50 → 45. After reload the separator's first value was the stored 50%, and Fit page was already pressed. The collapsed rail did not overlap Edit contact. |
| 9 | Task 9 pin plus every `backend/tests/test_frontend_*.py` | pass (162) |
| 9 | `npx tsc --noEmit` | clean |
| 9 | `npm run lint` | 0 errors, 5 warnings (baseline) |
| 9 | `node --test lib/*.test.ts` | 67 pass |
| 9 | slop frontend | OK. Duplication 517 lines, 43 clones (delta 0) |
| 9 | slop backend | Still 425 hotspots from Task 4's pin. Not re-baselined. |
| 9 | browser | pass. At 1280×800 `/templates/harshibar` the document is 800px (no page scroll) and Knobs scrolls inside itself (715 client, 941 scroll). At 768 and 375 the base studio Contact block does not overflow (`dl` scrollWidth equals clientWidth; the email fits). |

## Queued for Task 18 (SYSTEM.md changes Claude applies)

## Deferred to merge (edits left for Claude, with file:line)

- `FullscreenEditorPage` is `h-dvh`. `VersionBanner` renders above it in `SidebarGutter` (`frontend/app/layout.tsx`), so when the banner shows the template editor overflows by the banner height. Both studios already do this (A2 §6). Not fixed here.
