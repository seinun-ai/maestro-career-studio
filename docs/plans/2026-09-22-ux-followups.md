# UX follow-ups (after the honest studio) — implementation plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or
> superpowers:subagent-driven-development) to implement this plan task-by-task.

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
reality, and log every deviation below with one line of reason. Anything touching
scope, another task's interface or the Goal Card goes back to the planner. Never
expand scope.

## How this plan is organised

The code-level design for every task is in three appendices, each written read-only
against `a3c800bb` by a research agent. The main plan fixes the order, the owner
decisions, the tests and the gates. The appendices hold the exact code. Where an
appendix offers options, **Owner decisions** below is binding.

- `docs/plans/2026-09-22-ux-followups-appendix-a1-studio.md`: studio correctness
- `docs/plans/2026-09-22-ux-followups-appendix-a2-a11y-visual.md`: accessibility and visual consistency
- `docs/plans/2026-09-22-ux-followups-appendix-b-review-items.md`: earlier UX review items

Cite them as **A1 §n**, **A2 §n**, **B §n**. The line numbers in them are at
`a3c800bb`, and earlier tasks move them, so re-locate by the quoted code before editing.

## Owner decisions (2026-09-22, binding)

1. **FAB on `/new`** (A2 §9): when current, it renders with the `default` (primary)
   variant, keeping its FAB geometry. It stays `fab` everywhere else. The optional
   resting-tone change is NOT taken.
2. **Dark destructive** (A2 §3): Material error tone 80, `oklch(0.838 0.089 26.76)`
   (`#ffb4ab`). Light is `oklch(0.49 0.185 27.3)`.
3. **Placeholders** (B §8): option B. Examples stay, prefixed `e.g.`; the doc records
   a scoped, deliberate deviation from GOV.UK and says why. Every non-example
   placeholder is fixed, and a ratchet test keeps the rule scoped.
4. **Raw JSON** (A1 §4): Save / Cmd+Ctrl+S apply a pending valid draft first and then
   save. An invalid draft saves nothing and shows its error. Cancel confirms before
   discarding. "Form view" behaves like Apply.
5. **Top-skills Top-30% chips** (A2 §8, §11; planner's call per the brief's
   recommendation): these move to the neutral secondary-container pair, and the rank
   label moves to `text-on-secondary-container/80`.
6. **Brief recommendations adopted as written unless a task says otherwise:**
   - Tailored own saves adopt IN PLACE, compared by a sorted-key `serverKey` (A1 §1–3).
   - "Needs you" is one orange object (B §4c).
   - The KB tab value AND label become `basics` / "Basics" (B §1).
   - `category_label` is owned by the server, and the frontend drops its map (B §2).
   - The ATS-over-time chart shows the top 4 roles and excludes the tail, while
     role mix sums its tail into "More roles" (B §3).
   - Referrals: a dialog when the list is populated, an inline form when it is empty
     (B §5).
   - Template thumbnails get a top-right "Sample" mark (B §6).
   - The orphan health route is deleted and its backend endpoints are kept (B §7).
   - `/jobs/*` maps to Applications, or to Proposals when `?from=proposals`, through
     a Suspense-wrapped `useSearchParams` (A2 §10).

---

## Before you start

- **Where to work:** the worktree `.claude/worktrees/seinun-resume-update-45a8c0`,
  branch `claude/ux-followups` (from `main` at `a3c800bb`). Never `cd` to the main
  checkout.
  - The **live Docker stack now runs from the main checkout** on 3000/8001 against
    `data/maestro_cs.sqlite3`. Never touch it.
  - Browser checks use a throwaway stack on spare ports: uvicorn from `<worktree>/backend`
    with its own SQLite file and every `*_DIR` under a scratch dir, plus `next dev -p <spare>`
    with `API_PROXY_BACKEND`. Seed made-up data through the API. Tear it all down
    afterwards.
- **Read** `SYSTEM.md`, `docs/frontend-conventions.md` and `frontend/AGENTS.md`.
  Before touching a Next API (Task 7's `useSearchParams`), read
  `frontend/node_modules/next/dist/docs/`.
- **Python:** `/opt/anaconda3/bin/python3`, with pytest and ruff run from `<worktree>/backend`.
  **Frontend:** `node_modules` is installed in the worktree.
- **Lint has the React Compiler rules at error level** (A1 "Global constraints"). Run
  `npm run lint` after every step. Prefer event handlers over effects for new
  setState. `ref.current` must not be read during render.
- **Frontend duplication ratchet is at 518/518.**
  - Logic added to both studios goes through a shared helper or hook.
  - Run `python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check frontend`
    and `… check backend` from the worktree root after each task, naming both surfaces.
  - Never reorder code to dodge the detector.
  - Re-baseline only a *count* metric that moved for a non-decay reason
    (`complexity_hotspots`), with `--reason`.
- **SYSTEM.md is at 999/1000 lines.** Any §12 addition needs an equal cut: compress
  an older entry, or move reference-tier detail to `docs/frontend-conventions.md`.
  Run `python3 scripts/check_system_md.py`.
- **Node unit tests are not in CI.** Pair every behaviour in `lib/*.ts` with a pytest
  source pin in `backend/tests/test_frontend_*.py`, which CI runs.
- **Every commit ends with** `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
  Don't commit `docs/ux/`.
- **Baseline** (record it in *Gate results*):
  - `pytest tests/ mcp_server/tests/ -q`: 4432 passed, 2 skipped at `a3c800bb`.
  - `node --test lib/*.test.ts`: 40/40.
  - tsc clean; lint 0 errors and 5 warnings.

---

# Phase A — review follow-ups

## A1 · Studio correctness (highest priority)

### Task 1: Pure helpers, test-first

**Code:** A1 §1 (`serverKey`, `adoptServerKey`), A1 §2 (`keepIfEdited`), A1 §4
(`jsonDraftDiffers`), A1 §7 (`shownSectionOrder` and the `diffFrom` change), A2 §5
(`clampPreviewPct`) and A2 §12 (`parsePreviewPct`).

**Files:**
- `frontend/lib/studio.ts`, `frontend/lib/studio.test.ts`
- `frontend/lib/formatting.ts`, new `frontend/lib/formatting.test.ts`
- `frontend/components/resume-editor/formatting-panel.tsx`: one line (`order = shownSectionOrder(…)`).

**Steps**
1. Write the node tests listed in A1 §1, §2, §4 and §7 and A2 §5 and §12. They include
   the regression test named in A1 §1 ("a formatting-only save arms nothing…") and the
   `replaceEqualDeep` key-order test, which imports `@tanstack/query-core`.
2. Run `cd frontend && node --test lib/*.test.ts`: the new cases FAIL.
3. Implement the helpers exactly as in the appendices.
4. Run the node tests, then tsc and lint. All pass (40 + the new cases).
5. Add a pytest pin in `backend/tests/test_frontend_studio.py` that `formatting-panel.tsx`
   uses `shownSectionOrder(`. Run it.
6. Commit: `feat(studio): server-key, adoption, draft and section-order helpers`.

### Task 2: Own saves adopt in place; no edits lost; Save keeps focus

**Code:** A1 §1 (parent), A1 §2 (option C, tailored child, and the base twin) and
A1 §3 (`focusableWhenDisabled`).

**Files:**
- `frontend/components/resume-editor/tailored-resume-studio.tsx`
- `frontend/components/resume-editor/editor-body.tsx`
- `frontend/components/resume-editor/studio-save-button.tsx`
- `backend/tests/test_frontend_studio.py`
- `SYSTEM.md` §12
- `docs/frontend-conventions.md`

**Steps**
1. Add the pins from A1 §1 and §2:
   - `adoptNextServerKey` is absent;
   - `serverKey(application.customized_json)`, `onSaved(serverKey(result.customized_json))`,
     `key={editorGen}` and `adoptServerKey(` are present;
   - `keepIfEdited(` is in both studios;
   - `sentData` is absent.

   Add the pins from A1 §3: `focusableWhenDisabled` and `data-disabled:opacity-50` in the
   save button. Run them: they FAIL.
2. Implement A1 §1 and §2 in the tailored studio and A1 §2's base twin. Factor the base
   snapshot builder into one local function, as A1 §2 says, for the ratchet.
3. Implement A1 §3 in `StudioSaveButton`.
4. Rewrite the comments A1 §2 names, since they describe the remount.
5. Docs:
   - Rewrite the SYSTEM.md §12 bullet "Studio external-edit dirty-guard" with A1's
     proposed text, and add the key-order gotcha. Make room by grooming, per
     *Before you start*.
   - Rewrite the conventions *Tailored studio* sub-bullet.
6. Run the pins, node tests, tsc, lint, both slop checks and `check_system_md.py`.
7. **Browser check (both studios)**, as listed in A1 §2 and §3:
   - Type during a Save: the text stays and reads "Unsaved changes".
   - The tab, Formatting panel, scroll and preview width all survive a content save.
   - Enter on Save keeps focus on Save.
   - Cmd/Ctrl+S from Summary keeps focus in Summary.
   - A formatting-only save followed by a foreign edit over unsaved edits shows the banner.
   - Rebuild while there are unsaved edits replaces the editor.
8. Commit: `fix(studio): own saves adopt in place; no edits lost; Save keeps focus`.

### Task 3: Raw-JSON drafts count as unsaved

**Code:** A1 §4. Decision 4 is binding (apply-then-save).

**Files:**
- `frontend/components/resume-editor/raw-json-toggle.tsx`
- both studios
- `backend/tests/test_frontend_studio.py`
- `docs/frontend-conventions.md`: add a *Raw JSON* sub-bullet, and a sentence on
  apply-then-save in *Cmd/Ctrl+S*.

**Steps**
1. Add A1 §4's pins; they FAIL.
2. Implement `useRawJsonDraft` and the `RawJsonToggle` handle, then wire both studios.
   The base adoption effect gains `!raw.pending`.
3. Run the pins, node tests, tsc, lint and slop checks.
4. **Browser check:**
   - A pending draft reads "Unsaved changes".
   - Cmd/Ctrl+S applies and saves.
   - Invalid JSON saves nothing and shows its error.
   - Cancel confirms.
   - The unload warning fires.
   - In Monaco, Cmd/Ctrl+S isn't claimed by the editor.
5. Commit: `fix(studio): raw-JSON drafts count as unsaved; Save applies them first`.

### Task 4: Re-score and Generate PDF gates; section order stores null when unchanged

**Code:** A1 §6 and A1 §7 (the panel line landed in Task 1).

**Files:** `tailored-resume-studio.tsx` and `test_frontend_studio.py`.

**Steps**
1. Update `test_tailored_rescore_hint_reads_unsaved` and add the ⋯ Generate PDF gate
   pin (A1 §6). They FAIL.
2. Change both gates to `busy || render.isPending || unsaved`, and pass
   `DiffReviewPanel dirty={unsaved}`. Don't add `render.isPending` to `busy`.
3. Run the pins, tsc and lint.
4. **Browser check:**
   - Re-score stays disabled through "Rendering PDF…".
   - In both studios, moving Experience down and back up returns to "All changes saved".
5. Commit: `fix(studio): no re-score or regenerate mid-render; section order undo stores nothing`.

### Task 5: Score-tab import keeps focus and never flashes "No ATS scores yet."

**Code:** A1 §5.

**Files:**
- `frontend/components/ats-score-panel.tsx`
- `frontend/components/setup/upload-dialog.tsx` (the optional `finalFocus` prop)
- `backend/tests/test_frontend_first_run.py`

**Steps**
1. Add A1 §5's pins, keeping every existing first-run and query-error pin. They FAIL.
2. Implement:
   - return the invalidation from `run.onSuccess`;
   - `onImportOpenChange`;
   - `renderBody()` with a hoisted `UploadDialog` and `finalFocus={rootRef}`;
   - the optional first-visit skeleton condition.
3. Run the pins, tsc and lint.
4. **Browser check:** a job with zero base résumés → import → Done. You see the skeleton
   then the cards, with no "No ATS scores yet." frame, and focus is on the wrapper.
5. Commit: `fix(score): import keeps focus; no empty-state flash around the rescore`.

## A2 · Accessibility

### Task 6: Focus ring, browser outline and destructive tokens

**Code:** A2 §2 and A2 §3. Decision 2 is binding.

**Files:**
- `frontend/app/globals.css`
- `backend/tests/test_frontend_color_roles.py`
- The nine hand-rolled `red-*` sites in A2 §3 (→ `bg-destructive/10 text-destructive`)
- `docs/frontend-conventions.md` (colour roles)

**Steps**
1. Add pins:
   - `test_focus_ring_meets_non_text_contrast`, `test_browser_focus_outline_is_the_solid_ring`
     and `test_destructive_text_on_its_tints_meets_aa` (A2 §2, §3);
   - **plus** `--muted-foreground` on `--background` and on `--card` ≥ 4.5:1 in both
     modes (B §8 needs this pin for the placeholder deviation).

   Run them: they FAIL.
2. Set:
   - light `--ring: oklch(0.57 0.11 259)`;
   - the base layer `outline-ring` (not `/50`);
   - light `--destructive: oklch(0.49 0.185 27.3)`;
   - dark `--destructive: oklch(0.838 0.089 26.76)`.
3. Move the hand-rolled red pairs to the token. Leave `status-chip.tsx`'s red, which is
   status vocabulary and already passes. Fold in the translucent `ring-ring/50` and
   `outline-ring/60` sites A2 §2 lists (drop the alpha), or log them as deviations.
4. Run the pins, tsc, lint and slop checks.
5. **Browser check (light and dark):**
   - A Tab-focused zoom preset, SourceToggle segment and "Open PDF" link each show a
     visible ring on the canvas.
   - The render-error banner and the "JD asks for…" badge are readable.
6. Commit: `fix(ui): focus ring and destructive meet contrast; browser outline is solid`.

### Task 7: Sidebar — inert when hidden, FAB current state, the job-page section

**Code:** A2 §1 (inert plus the focus hand-off), A2 §9 (decision 1) and A2 §10
(`navSection`, Suspense).

**Files:**
- `frontend/components/ui/sidebar.tsx`, `frontend/components/sidebar-reveal-trigger.tsx`
- `frontend/components/app-sidebar.tsx`
- `frontend/lib/nav.ts`, `frontend/lib/nav.test.ts`
- `backend/tests/test_frontend_sidebar_nav.py`
- `docs/frontend-conventions.md` (sidebar)

**Steps**
1. Tests:
   - the node cases for `navSection`/`navCurrent` (A2 §10);
   - pins: `inert={offcanvasHidden}` sits between the container and inner slots;
     `<Suspense` and `useSearchParams()` are in `app-sidebar.tsx`;
   - update `test_create_action_is_the_fab_variant` to the ternary (A2 §9).

   They FAIL.
2. Implement A2 §1, §9 and §10. Read the Next docs on `useSearchParams` first; `next build`
   must pass.
3. Run the node tests, pins, tsc, lint and `npm run build`.
4. **Browser check:**
   - With the sidebar collapsed, Tab never enters it, and focus moves to the reveal pill.
   - `/new` shows the solid FAB.
   - `/jobs/x` marks Applications, and `?from=proposals` marks Agent Proposals.
   - The mobile sheet is unchanged.
5. Commit: `fix(ui): hidden sidebar is inert; FAB shows current on /new; job pages mark their section`.

### Task 8: One localStorage preference hook; the divider done right; the edge rail

**Code:**
- A2 §12: `useLocalStorageState`, plus adopting it in EditorShell, PdfPagesPreview and the
  chat rail. The two dismiss cards are optional.
- A2 §5: pointer capture, sizing from the shell, and persisting on release.
- A2 §4: Widen/Narrow buttons, and double-click to reset.
- A2 §6: the edge rail in normal flow.

**Files:**
- new `frontend/hooks/use-local-storage-state.ts`
- `frontend/components/resume-editor/editor-shell.tsx`
- `frontend/components/resume-editor/pdf-pages-preview.tsx`
- `frontend/components/chat/chat-page.tsx`
- `backend/tests/test_frontend_studio.py`
- `docs/frontend-conventions.md` (divider, PdfPagesPreview)

**Steps**
1. Pins:
   - `test_divider_has_a_pointer_alternative`;
   - `onPointerCancel=` and `setPointerCapture(` are present, and `window.innerWidth` is not;
   - `aria-label="Show PDF preview"` is not inside an `absolute`-positioned button;
   - no `set-state-in-effect` disable remains in the three adopted files.

   Keep `test_divider_is_keyboard_operable`'s `/>` slice valid: the separator stays
   self-closing. The pins FAIL.
2. Implement.
   - Delete the `hydrated` flags, the three hydrate effects and their eslint disables.
   - Name in the commit body the behaviour change: preferences now sync across tabs.
3. Run the pins, node tests (`clampPreviewPct`, `parsePreviewPct` from Task 1), tsc, lint and
   slop checks. This task should LOWER duplication.
4. **Browser check:**
   - The divider tracks the pointer with the sidebar open.
   - Widen/Narrow step by 5%.
   - Double-click resets.
   - Stored width and zoom paint with no default frame.
   - The collapsed rail doesn't cover any control or the scrollbar.
5. Commit: `refactor(studio): one localStorage preference hook; divider tracks the pointer and has a click path`.

### Task 9: Template editor fills the viewport; the Contact grid fits narrow panes

**Code:** A2 §6 (page wrapper) and A2 §7.

**Files:**
- `frontend/app/templates/[id]/page.tsx`
- `frontend/components/resume-editor/contact-form.tsx`
- `backend/tests/test_frontend_studio.py`
- `docs/frontend-conventions.md` (the 768 band worked case)

**Steps**
1. Pins: `<FullscreenEditorPage>` is in the template page; `minmax(0,1fr)` and
   `wrap-anywhere` are in contact-form, and `grid-cols-[8rem_1fr]` is not. They FAIL.
2. Implement both changes.
3. Run the pins, tsc and lint.
4. **Browser check:**
   - At 1280×800 the template editor doesn't scroll the page, and Knobs scrolls inside itself.
   - At 768px the base studio's Contact block has no horizontal overflow. Check at 375px too.
5. Commit: `fix(ui): template editor fills the viewport; contact details fit narrow panes`.

## A3 · Visual consistency

### Task 10: One rule for selected, current and create states

**Code:** A2 §8 (the rule and the per-site table), plus A2 §11 including the
`ring-offset-background` fix. Decision 5 is binding.

**Files:**
- `source-toggle.tsx`
- `proposals/proposals-section.tsx`
- `chat/chat-page.tsx`: "New chat" becomes `tonal`, and the active session gets
  `aria-current`. Keep the two New-chat strings identical or extract one component.
- `setup/setup-status-strip.tsx`, `setup/dropzone.tsx`
- `charts/top-skills-chart.tsx`: the chips and the rank label
- `tailored-resume-studio.tsx`: the tab count
- `formatting-panel.tsx`: the "Customized" chip, plus `aria-pressed` on the segmented buttons
- `career/new-entity-dialog.tsx`: `aria-pressed`
- `backend/tests/test_frontend_color_roles.py`
- `docs/frontend-conventions.md`: replace the "known inconsistency" sentence with the rule

**Steps**
1. Pins:
   - extend `test_selected_tonal_toggles_show_a_check` to SourceToggle and the proposals
     filters;
   - `aria-current` on the active chat session;
   - `aria-pressed` on the formatting segmented buttons and on new-entity cards;
   - optional ratchet: the count of `bg-primary/10 text-primary` in `components/` must
     not rise.

   Keep the `test_frontend_query_error_states.py` copy anchors. The pins FAIL.
2. Apply the table. Leave the callout containers and the decorative avatars (A2 §8 lists
   them).
3. Run the pins, tsc, lint and slop checks.
4. **Browser check (light and dark):**
   - Selected segments show a check.
   - The dark-mode hover now visibly changes the setup pill and the top-skills chips.
   - There's no white ring-offset band in dark mode.
5. Commit: `fix(ui): one rule for selected, current and create states`.

---

# Phase B — earlier UX review items

### Task 11: Words, not keys: KB "Basics", "Needs you", titles, insight copy

**Code:** B §1 and B §4 (4a, 4c, 4d, 4e; 4b lands in Task 13).

**Files:**
- `frontend/app/career/page.tsx`
- `frontend/components/explore/explore-overview.tsx`
- `frontend/components/status-chip.tsx`
- `frontend/app/templates/page.tsx`
- `backend/app/services/explore_overview.py`
- `backend/tests/test_explore_router.py`
- `docs/frontend-conventions.md` (optional naming note)

**Steps**
1. Tests:
   - `test_overview_signal_copy_has_no_em_dash` (B §4e);
   - keep `test_overview_signals`'s OPT/Texas/Python title pins.

   It FAILS.
2. Apply B §1: the KB tab value and label become `basics` / "Basics".
3. Apply B §4: the tile case, the single `NEEDS_YOU` object in orange, the Templates
   subtitle "The look of the PDF.", and the rewritten insight details. Drop the unsourced
   jurisdiction percentages.
4. Run pytest (explore router), tsc and lint.
5. Commit: `fix(copy): Basics tab, one Needs-you colour, sentence-case tiles, plain insight copy`.

### Task 12: Gap categories speak plain words everywhere

**Code:** B §2 (the server-owned `category_label`).

**Files:**
- `backend/app/services/explore_gaps.py`, `backend/app/services/explore_build_areas.py`
- `backend/mcp_server/server.py` (two docstrings)
- `backend/app/services/chat_tools.py` (tool spec), `backend/app/prompts/chat_system.txt`
- `frontend/lib/types.ts`, `frontend/components/analytics/gap-tiers-panel.tsx`
- `docs/agentic-job-search.md`, `docs/frontend-conventions.md` (Analytics)
- Tests: `test_explore_gaps.py`, `test_explore_build_areas.py`,
  `mcp_server/tests/test_server.py`, `test_chat_upgrades.py`

**Steps**
1. Tests (B §2's five): the label set equals `_HINT_TO_CATEGORY.values()`, the row labels,
   `category_label is None` on wording rows, the docstrings mention `category_label`, and
   the chat spec mentions it. They FAIL.
2. Implement the backend constant and `category_label()`, and add the rows. The frontend
   reads `row.category_label` and deletes `CATEGORY_LABEL`. Add the agent-facing text AFTER
   the tier content.
3. Run the full backend suite, including the docstring budget ratchet, then tsc and lint.
4. Commit: `feat(analytics): server-owned category_label; chat and MCP speak plain words`.

### Task 13: Role names everywhere in Analytics; charts never cycle colours

**Code:** B §3, including 4b ("Any").

**Files:**
- `frontend/components/role-category-picker.tsx` (`useRoleLabel`)
- delete `frontend/lib/format.ts`
- new `frontend/lib/analytics-series.ts` and its `.test.ts`
- `frontend/components/charts/{ats-over-time,role-mix,tailoring-lift,heatmap}-chart.tsx`
- `frontend/components/explore/explore-overview.tsx`
- `frontend/app/analytics/page.tsx`
- `backend/app/services/explore_overview.py`, `backend/tests/test_explore_router.py`
- `docs/frontend-conventions.md` (Analytics)
- §11 entries for the out-of-scope leaks

**Steps**
1. Tests:
   - `analytics-series.test.ts` (B §3);
   - `test_best_paying_signal_uses_role_label`, including the reserved-role case.

   They FAIL.
2. Implement:
   - `useRoleLabel` at every raw-slug site in B §3's table;
   - `filterSelect` gets a `format` argument, "Any", and role options sorted by label;
   - `MAX_ROLE_SERIES = 4` on ATS-over-time, which excludes the tail and names the hidden
     count in the caption;
   - role mix sums its tail into "More roles";
   - the backend insight uses the label and skips reserved roles.
3. Run pytest, the node tests, tsc, lint and slop checks.
4. **Browser check:** Job market, Resume fit and Gaps show no slugs, the legends have at
   most 8 lines, and the colours don't repeat.
5. Commit: `fix(analytics): role labels everywhere; line charts cap roles instead of cycling colours`.

### Task 14: Template previews say they're a sample

**Code:** B §6.

**Files:**
- `frontend/components/gallery/preview-thumbnail.tsx` (the `mark` slot)
- `frontend/components/templates/template-thumbnail.tsx` (`mark="Sample"` and the alt text)
- optionally the `DialogDescription` in `templates/template-select.tsx`
- `docs/frontend-conventions.md` (Card galleries: the second slot)

**Steps**
1. Pin: `template-thumbnail.tsx` passes `mark=`, and its alt text mentions "sample". It FAILS.
2. Implement.
3. **Browser check:**
   - `/templates` and the picker dialog show "Sample" top-right.
   - Base-resume thumbnails don't.
   - Report whether the stale chip's tooltip is reachable under the card link. Log a
     follow-up if it isn't; don't fix it here.
4. Commit: `feat(templates): previews are marked as a sample resume`.

### Task 15: Delete the orphaned tailored health page

**Code:** B §7. Keep every backend endpoint, because MCP uses `kind='application'`.

**Files:**
- delete `frontend/app/applications/[id]/health/page.tsx`
- narrow `frontend/components/resume-health/health-report-page.tsx` to base
- `frontend/app/base-resumes/[slug]/health/page.tsx`
- `frontend/components/resume-editor/studio-toolbar.tsx` (comment)
- optional router test: `GET /api/resume-lint/application/{id}` returns 404 without a report

**Steps**
1. Delete the page, then narrow `HealthReportPage` exactly per B §7's deletion set. Leave
   the `kind` unions in `lib/api.ts` and the child components.
2. Run the health pins (`test_frontend_health_report.py`, color_roles, query_error_states),
   tsc, lint and `npm run build`. Orphan LOC should drop.
3. Close the pending "Resolve orphaned tailored-resume health route" task chip, if it is
   still open, as done by this task.
4. Commit: `chore(health): remove the unreachable tailored health page; MCP keeps the endpoints`.

### Task 16: Referrals: the table is the page; adding opens a form

**Code:** B §5.

**Files:**
- `frontend/app/referrals/page.tsx`
- `backend/tests/test_frontend_query_error_states.py`: add
  `("app/referrals/page.tsx", "Add your first referral")`
- `docs/frontend-conventions.md`, if a rule changes

**Steps**
1. Add the query-surface entry. It FAILS (the page has no `LoadErrorState` yet).
2. Implement:
   - `ReferralForm`, `FirstReferralCard` and `ReferralsTable`;
   - the header "Add referral" opens the dialog with `initialFocus`;
   - the error branch uses `LoadErrorState`;
   - use `<Label optional>` and `grid gap-1.5` rows;
   - after the first inline create, move focus to the header button.
3. Run the pins, tsc and lint.
4. **Browser check at 768px and 375px:** empty → form, populated → table plus dialog;
   delete still confirms; no focus drop after the first create.
5. Commit: `fix(referrals): table first; adding a referral opens a form`.

### Task 17: Placeholders — a recorded, scoped deviation, and every misuse fixed

**Code:** B §8. Decision 3 is binding (option B).

**Files:**
- `docs/frontend-conventions.md`: Form conventions and Microcopy, with the proposed text
- about 20 component files from B §8's code-fix table
- new `backend/tests/test_frontend_placeholders.py` (the scoped ratchet)

**Steps**
1. Write the placeholder ratchet:
   - allow values starting `e.g. ` or `https://`, and `…`-ending prompts from an allowlist
     of search, composer and chip add-row files;
   - fail on anything else;
   - skip `SelectValue` and image placeholders.

   It FAILS on today's statements, instructions and label repeats.
2. Apply B §8's fix table:
   - wire the two hints that sit below their control, placing them between the label and
     the control with `aria-describedby`;
   - don't reformat the autofill `GROUPS` header lines (`test_autofill_groups_parity.py`
     parses them).
3. Update the conventions text (the deviation, scoped and cited). The muted-foreground
   contrast pin it cites landed in Task 6.
4. Run the pins, tsc and lint. Browser-check at 768px that the entry cards didn't grow badly.
5. Commit: `fix(copy): placeholders hold only examples; the GOV.UK deviation is recorded`.

---

# Wrap-up

### Task 18: Docs sweep

- Re-read every `docs/frontend-conventions.md` bullet touched by Tasks 1–17 against the
  code, and fix anything stale.
- `SYSTEM.md`:
  - the §12 changes from Task 2;
  - §11 items for the out-of-scope leaks (B §3 risks);
  - the `useSearchParams` Suspense gotcha from A2's docs section, if not already added;
  - stay at or under the cap by grooming.
- In `docs/plans/2026-09-22-honest-studio.md`, replace the follow-up bullets this plan
  shipped with one line pointing here.
- Run `python3 scripts/check_system_md.py`.
- Commit: `docs: conventions and SYSTEM.md match the follow-ups`.

### Task 19: Verification and goal critique

1. **Gates:**
   - `pytest tests/ mcp_server/tests/ -q`;
   - `ruff check .`;
   - `node --test lib/*.test.ts`;
   - `npx tsc --noEmit`, `npm run lint`, `npm run build`;
   - both slop checks, named;
   - `check_system_md.py`.

   Record them in *Gate results*.
2. **Browser pass:** throwaway stack, light and dark, at 1280/768/375. Cover every
   "Browser check" above, plus a regression sweep of the honest-studio features: status
   walk, stale strip, Cmd/Ctrl+S, divider, zoom and the first-run path.
3. **Goal critique:** check the landed branch against the Goal Card, not the plan. Default
   to approve; a finding names the Goal Card line it violates.
4. Then use superpowers:finishing-a-development-branch.

---

## Deviation log

| Task | Planned | Did instead | Why (Goal Card line) |
|---|---|---|---|

## Gate results

| When | Gate | Result |
|---|---|---|
| Baseline (`a3c800bb`) | full backend suite / node / tsc / lint | 4432 passed, 2 skipped / 40/40 / clean / 0 errors, 5 warnings |
