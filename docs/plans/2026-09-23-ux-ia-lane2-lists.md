# UX IA and copy, wave 1 lane 2: lists — handoff to a Claude Opus 5.5 subagent

**Tasks:** Tasks 2, 3, 4, 5 of `docs/plans/2026-09-23-ux-ia-copy.md`, in that order.
**Branch:** `claude/ux-ia-lane2-lists` (from `claude/ux-ia-copy-plan` at the commit that added this doc).
**Worktree:** `/Users/ajeyds/Projects/maestro-ux-ia/lane2-lists`. Work only there.
**Planner/reviewer:** Claude (Opus 5.5). It reviews and merges this branch; you never merge.

## Goal Card

**Goal.** A new user understands every screen on first read. The app says one plain word for each thing
on every surface (web app, Companion panel, and the server messages it shows). The Agent inbox is plainly
separate from the app's own features and names who proposed each job. Long lists keep their headers in
view and say when they are cut off. Settings and Profile are organised into tabs with one spacing rhythm.

**Principles**
- **Plain words over precise jargon.** No abbreviations (JD, KB), no internals (render, slug, endpoint,
  schema paths), no example text in blank fields, no "/" meaning "or". A term that must stay (ATS, MCP)
  is explained once, where it first appears.
- **One word per thing, everywhere.** The glossary (Appendix D0) is binding and pinned by a ratchet.
- **Honesty and safety nuance survive every cut.** Consent, "nothing is submitted without your yes",
  honesty warnings and "can't undo" are shortened, never dropped.
- **Everything from the last plan still holds.** Never lose typed text, never say "saved" while pending,
  focus never to `<body>`, WCAG 2.2 AA, one request per click.
- **No new dependencies. MCP and chat contracts are additive only** (docstrings ≤ ~2,000 chars).
- **Conventions change deliberately**, in the same commit as the code.

**Non-goals**
- Referrals / Contacts work (deferred by the owner), grouping or paginating the tracker, search and sort
  in the URL, an `X-Total-Count` header (Appendix B O3).
- Gender options and "restrictive covenant" wording (legal nuance; owner's call later).
- `keepMounted` on the job workspace tabs, a dot on a tab holding unsaved work.

**Autonomy: peer (adapt-and-advise).** Adapt *how* when a step conflicts with repo reality and log every
deviation with one line of reason. Scope, another task's interface or the Goal Card go back to the
planner. Never expand scope.

## Ground truth (read in this order before writing code)

1. `SYSTEM.md` at the repo root.
2. `docs/frontend-conventions.md` and `frontend/AGENTS.md` (read `frontend/node_modules/next/dist/docs/` before relying on any Next API).
3. The main plan `docs/plans/2026-09-23-ux-ia-copy.md`: Goal Card, *Owner decisions* and *Planner decisions* (binding — especially 15–20), *Before you start*, *Waves and lanes*, and your tasks' sections.
4. The appendix sections your tasks cite: B §2–§11, plus A §3's `components/list-search.tsx` (Task 3) and B §9's `lib/list-cap.ts` / `components/list-cap-notice.tsx` as the ONE shared version (planner decision 15). They hold the exact code; line numbers are at `8cac7cf9`, so re-locate by the quoted code.
5. **Words:** where your appendix proposes UI copy, use the D §0 glossary word instead if they differ (planner decision 19; `docs/plans/2026-09-23-ux-ia-appendix-d-copy.md` §0).

## Scope

**Files this lane owns:** `components/ui/table.tsx`, `components/empty-state.tsx` (`TableFrame` only), new `components/list-toolbar.tsx`, `components/list-search.tsx`, `lib/list-cap.ts` (+ test), `components/list-cap-notice.tsx`, `app/globals.css`, `app/applications/page.tsx` (toolbar, table, search, queries, notice), `app/referrals/page.tsx` (the `<Table>` line), `components/career/inbox-panel.tsx` (one notice line), the jobs router's `source` filter only if missing (additive, tested), `backend/tests/test_frontend_sticky_lists.py` (new), `test_frontend_placeholders.py` (the `_PROMPTS` row move), `docs/frontend-conventions.md` (list bullets only).

**Other wave-1 lanes run at the same time** (lane 1 proposed-by: backend/MCP; lane 2 lists: tables, toolbars, Applications, cap notice; lane 3 settings-tabs: the two pages, tabs, deep links, leave guard; lane 4 settings-cards: the cards). Don't edit their files. `docs/frontend-conventions.md` is shared: edit only the bullets your tasks name, never reflow other text.

**Never touch:** `SYSTEM.md` (1000/1000; queue changes below), `.slop-baseline.json` files, `docs/ux/`, other worktrees and branches, and the main checkout `/Users/ajeyds/Projects/maestro-career-studio` (live `data/` and the live Docker stack on 3000/8001: never `cd` there, never `docker compose`). Never bare `git stash`. Don't push, rebase or merge.

## Environment

- Python `/opt/anaconda3/bin/python3`; pytest and ruff from `<worktree>/backend`. Frontend from `<worktree>/frontend` (`npm ci` has been run): `npx tsc --noEmit`, `npm run lint` (0 errors, 5 baseline warnings; React Compiler rules at error level), `node --test lib/*.test.ts`, `npm run build`.
- **Browser checks:** scratch dir `/tmp/maestro-ia-lane2`; backend from `<worktree>/backend`: `/opt/anaconda3/bin/python3 -m uvicorn app.main:app --port 8812` with `DATABASE_URL=sqlite:////tmp/maestro-ia-lane2/app.sqlite3`, every `*_DIR` setting from `backend/app/config.py` under the scratch dir, `ALLOWED_WEB_ORIGINS=http://127.0.0.1:3212,http://localhost:3212`, `PATH=/Library/TeX/texbin:$PATH`, no LLM keys; frontend `API_PROXY_BACKEND=http://127.0.0.1:8812 npx next dev -p 3212` (open `http://localhost:3212`; run `npm run predev` first if it exists and delete what it copies afterwards). Seed MADE-UP data through the API (earlier seed scripts to crib: `/tmp/maestro-sweep-a/`, `/tmp/maestro-sweep-b/`, `/tmp/maestro-fix-sweep/scripts/`). Python Playwright (`from playwright.sync_api import sync_playwright`, `channel="chrome"`), real keys and pointer, light and dark, 1280/768/375; screenshots under the scratch dir; tear the stack down afterwards.

## Gates (per task, and all of them before you report done)

- The task's pins (seen FAILING first), plus every `backend/tests/test_frontend_*.py`. Mutation-check every pin you add: break the guarded code, see exactly that pin fail, restore from a backup copy (never `git stash`).
- tsc clean; lint 0 errors; node tests pass; `npm run build` (run last).
- Full backend suite `pytest tests/ mcp_server/tests/ -q` at least once before reporting (baseline at `61a4a15f`: see the plan's *Gate results*); `ruff check .`.
- Slop ratchet: frontend duplication measured on a CLEAN `git archive HEAD` export (`python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py scan <export>/frontend --json` → `duplication`) must stay ≤ **437 lines / 36 clones**; `slop_scan.py check frontend` and `check backend` OK from the export root; backend `complexity_hotspots` ≤ **424** (423 at the branch point; split a test that reaches cc 10).
- Logic added in two places goes through a shared helper.

## Commits

One per task with the plan's commit message, ending `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Don't amend or squash earlier commits. Commit this doc's filled-in logs at the end.

## Escalation (autonomy: peer)

Adapt *how* when the plan conflicts with the code and log it below. If a change needs another lane's file, scope, or a Goal Card trade-off: log a deviation note (planned / found / proposed / Goal Card line) and carry on with the rest. Never expand scope.

## Deviation log

| Task | Planned | Did instead | Why (Goal Card line) |
|---|---|---|---|
| 2 | Browser check B12 rows 1–7 before the Task 2 commit | Ran them after Task 3, on Applications and Referrals | The primitives have no call site until Task 3 adopts them; nothing to scroll before that (verification, not scope). |
| 2→3 | `tall:` = `(min-height: 40rem)`, plus `print:static` on the toolbar and header | `tall:` = `screen and (min-height: 40rem)` (CSS variant, `TALL_QUERY`, the `--list-head-h` query); `print:static` dropped; pins adapted | B12 row 12 failed in Chromium: `tall:sticky` beat `print:static` (the custom variant's rule is emitted later), so a printed tracker kept a stuck bar. Fixed in Task 3's commit (no amend). "Long lists keep their headers in view" without breaking print. |
| 2→3 | `html { scroll-padding-top: calc(...) }` (B5) | The padding sits in `html:has([data-slot="list-toolbar"] ~ * :focus, [data-slot="table-header"][data-sticky] ~ [data-slot="table-body"] :focus)`; new pin `test_only_focus_in_the_list_is_cleared` | Browser-found: on `html` the padding counts the toolbar's own height, so focusing the stuck status filter scrolled the page up ~400px and opening it (focus into the portalled listbox) ~370px more. Scoped, the Tab and Shift+Tab sweeps still never land under the chrome (0 obscured of 91 stops). "Focus never to `<body>`", WCAG 2.2 AA. |
| 2 | `ListToolbar` a `<div>` (B5), `<search>` per planner decision 17 O6 | `<search>` with no `aria-label` | One per page, so an unnamed search landmark is unambiguous; no new UI copy. |
| 4 | O4: fetch the user's saved jobs separately from agent captures | One saved-jobs query keyed by the toggle's source (`source=user`, or `source=agent` under the Agents toggle); the client-side split is gone | Same guarantee with one query; keeps `const loadFailed = isLoadFailure(apps) \|\| isLoadFailure(savedJobs);` (pinned in `test_frontend_query_error_states.py`) unchanged. The jobs router already had an additive, tested `source` filter (`tests/test_jobs_router.py:939`), so no backend change. |
| 4 | B §9 `ListCap` with a newest-first sentence | Added optional `order: "newest" \| "oldest"` | The Career history draft endpoint returns OLDEST first (`order_by(KBPoint.created_at, KBPoint.id)`), so "older ones don't appear" would be false there; its notice says "Only your 500 oldest draft bullets are loaded, so newer ones don't appear in this list." Additive: A §7 / B8 callers are unaffected. "Honesty survives every cut". |
| 4 | Inbox panel: one line | A named `KB_DRAFTS_LIMIT = 500` (pinned equal to the API's default, since `listKbDrafts` sends no limit; `lib/api.ts` is not this lane's), an import and the notice | The convention "one named limit per page, pinned to the API" needed the constant. |
| 4 | Nouns "saved jobs" for every saved-jobs cap | "jobs from connected agents" under the Agents toggle | D §0: no bare "agent"; the rows are agent captures there. |
| 5 | Conventions: the list bullets only | Also the react-query keys bullet: `["jobs","without-application", source]` | Task 4 made that key stale; conventions change with the code. |
| — | — | Extra commit `f6c462e3` splits `test_the_toolbar_publishes_its_height_and_takes_it_back` (cc 10) in two | Backend hotspots went 423 → 424; the lane doc says split a test at cc 10. Back to 423. |
| 3 | — | `ListSearch`'s label stays "Search applications" | D2.1's "Search jobs" is lane 7's (wave 3); this lane moved copy, it did not write it. |
| review | Selector `~ * :focus` → `~ :is(:focus, * :focus)` | `~ :focus-within` (`7299bc6c`, after `85830299` shipped the `:is()` form) | Browser-checked in Chromium on a static page: both `:is()` arms test the toolbar's later SIBLING, so it matched a focused lane root but nothing inside one; every row after the toolbar lost its clearance. `:focus-within` clears the sibling and its contents, and still nothing in the toolbar or outside the list. WCAG 2.2 AA. |
| review | One review-fix commit | Two (`85830299` pins and fixes, `7299bc6c` the selector) plus the docs commit | "Don't amend earlier commits"; the selector finding came after the first commit. |
| review | `listKbDrafts` sends the limit | `KB_DRAFTS_LIMIT` moved to `lib/api.ts` (exported), `inbox-panel.tsx` imports it; the pin checks it is ≤ the API's `le` instead of equal to its default | One constant for the request and the notice. `lib/api.ts` is not this lane's file; the reviewer directed it (two lines). |
| review | Prefetch the Agents list on pointerenter/focus | `SourceToggle` (shared with Analytics, not this lane's file) gains an optional `onPreview`; the tracker's saved-jobs query moves into a module-level `savedJobsQuery(savedSource)` used by both `useQuery` and `qc.prefetchQuery` | One query definition, so the prefetch fills the list's own cache entry (30s default staleTime, so repeat hovers don't refetch). Analytics passes nothing and is unchanged. |
| review | Conventions change with the code | The list bullet's "after a `ListToolbar`" → "on or in anything after a `ListToolbar` (`~ :focus-within`)" lands in the docs commit | The code commits were already made (no amend). |

## Gate results

| Task | Gate | Result |
|---|---|---|
| 0 | Baseline at `6366ec27` | full suite 4969 passed, 2 skipped; frontend dup 437 lines / 36 clones; backend hotspots 423; node 166 pass |
| 2 | New pins seen failing | 9 failed, 5 passed (the B2 scroll-chain guards pass by design, then mutation-checked) |
| 2 | Pins, `test_frontend_*.py`, tsc, lint, node, build | 14/14; 661 passed; clean; 0 errors (5 baseline warnings); 166 pass; OK (compiled CSS holds `@container table (min-width:52rem)` and the `tall:` media rules) |
| 3 | New pins seen failing | 4 sticky + 2 placeholder pins failed; later CSS pins (screen-only, scoped padding) each failed before their fix |
| 3 | Pins, `test_frontend_*.py`, tsc, lint, node, build | 19/19; 666 passed; clean; 0 errors; 166 pass; OK |
| 4 | New pins and node tests seen failing | 6 pins failed; `list-cap.test.ts` failed to import |
| 4 | Pins, `test_frontend_*.py`, tsc, lint, node, build | 25/25; 672 passed; clean; 0 errors; 170 pass; OK |
| 5 | `test_frontend_*.py`, `check_system_md.py` | 672 passed; OK, 1000/1000 |
| all | Full backend suite `pytest tests/ mcp_server/tests/ -q` (at `d7ecb741`) | 4994 passed, 2 skipped (baseline + 25 new pins); `f6c462e3` then only split one pin (sticky file 26 passed) |
| all | `ruff check .` | All checks passed |
| all | Final frontend (at `f6c462e3`): tsc, lint, node, `test_frontend_*.py`, build (last) | clean; 0 errors, 5 warnings; 170/170; 673 passed; OK |
| all | Slop, clean `git archive HEAD` export (`f6c462e3`) | frontend duplication 437 lines / 36 clones (= ceiling); `check frontend` OK; `check backend` OK; backend `complexity_hotspots` 423 |
| all | Mutation checks | 30 mutations, each failing exactly the pin it guards (two that restate a whole pinned line also fail that line's pin); node: `loaded > limit` fails 3 cases, dropping `order` fails 1 |
| review | Mutation (isolated `git archive` copy `/tmp/maestro-ia-fix2/src`, reviewer's harness `mut/run.py` + 7 new mutants) | All 16 targeted mutants and 7 new ones each fail the pin that guards them (table in the report); still surviving, not targeted: M13, M19, M22, M30 |
| review | `test_frontend_*.py`, tsc, lint, node, ruff (at `7299bc6c`) | 688 passed (673 + 15 new pins); clean; 0 errors (5 warnings); 170/170; All checks passed |
| review | Full backend suite `pytest tests/ mcp_server/tests/ -q` (at `7299bc6c`) | 5010 passed, 2 skipped (4995 + 15 new pins) |
| review | Slop, clean export at `7299bc6c` | frontend duplication 437 / 36 (= ceiling); `check frontend` / `check backend` OK; backend hotspots 423 |
| review | `npm run build` | NOT run (a browser verifier's dev server was live on 3222); the compiled selector was checked with `@tailwindcss/postcss` (optimize on) in the isolated copy: `~ :focus-within` survives as written |
| all | Browser (Chromium via Playwright `channel="chrome"`, real keys; light and dark) | B12 rows 1–10, 12–14 pass (details in the report); row 11 not verifiable on `next dev`; WebKit not installed, so Chromium only |

## Queued for Task 24 (SYSTEM.md changes Claude applies)

- §11 item 5: "Server-side pagination for the tracker (client caps at limit=500 today)." becomes
  "Server-side pagination for the tracker (client caps at 500 rows and says so)." (same length).
- §5 step 2: "Two queries (summary list with server-joined job fields + saved jobs)" is still true, but the saved
  jobs are now fetched for the toggle's source (`source=user`, or `source=agent` under the Agents toggle), so agent
  captures cannot crowd the user's own out of the 500. Suggested same-length wording: "(summary list with
  server-joined job fields + saved jobs of the toggle's source)".

## Deferred to merge (edits left for Claude, with file:line)

- `docs/frontend-conventions.md`: the two new bullets sit between "The 768–1023px band" and "`truncate` on a flex
  child" (:504–:566); the only other edits are :498 (`minWidth="52rem"`) and the react-query keys bullet (:784).
  Other lanes' conventions edits should merge around them.
- Task 13 (inbox): the focus clearance is `html:has([data-slot="list-toolbar"] ~ :focus-within, …)` in
  `frontend/app/globals.css`, so the inbox's lanes must be later siblings of its `ListToolbar` (B8 already says a
  direct child of the section root). O7's `scroll-padding-bottom` for the bulk bar belongs in a rule scoped the same
  way, not on bare `html` (same jump). `ListCapNotice` takes `total` unchanged; `order` defaults to newest.
- Task 13: a lane root that takes focus itself (`tabIndex={-1}` for focus handoff) is cleared too, because the
  selector is `~ :focus-within` (not `~ * :focus`, which missed it, nor `~ :is(:focus, * :focus)`, which drops its
  rows); keep each lane a later sibling of the `ListToolbar`. Pinned by `test_a_focused_lane_after_the_toolbar_is_cleared_too`.
- Task 13: `test_frontend_placeholders.py` `_PROMPTS` now lists `components/list-search.tsx`, not
  `app/applications/page.tsx`; don't add the inbox file (it renders `ListSearch`).
