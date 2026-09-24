# UX IA and copy, wave 2 lane 5: inbox — handoff to a Claude Opus 5.5 subagent

**Tasks:** Tasks 13 and 14 of `docs/plans/2026-09-23-ux-ia-copy.md`.
**Branch:** `claude/ux-ia-lane5-inbox` (from `claude/ux-ia-copy-plan` at the commit that added this doc; wave 1 is merged into it).
**Worktree:** `/Users/ajeyds/Projects/maestro-ux-ia/lane5-inbox`. Work only there.
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
2. `docs/frontend-conventions.md` (wave 1 added list, tabs, card-header and leave-guard bullets) and `frontend/AGENTS.md` (read `frontend/node_modules/next/dist/docs/` before relying on any Next API).
3. The main plan `docs/plans/2026-09-23-ux-ia-copy.md`: Goal Card, *Owner decisions*, *Planner decisions* (binding, esp. 15–20), *Before you start*, *Waves and lanes*, and your tasks' sections.
4. Appendix A §1, §2, §3, §4, §6, §7, §9 (UI half) and §10's `docs/entities/others.md` sentence; planner decisions 15–17, 19, 20. Also the wave-1 lane docs' *Deferred to merge* notes for Task 13 (lane 1: types, the first-filer note, others.md; lane 2: lanes stay later siblings of `ListToolbar`, bulk-bar `scroll-padding-bottom` scoped the same way, `_PROMPTS` already lists `list-search.tsx`, `ListCapNotice` takes `total`). Line numbers in the appendices are at `8cac7cf9`; wave 1 moved code, so re-locate by the quoted code.
5. **Words:** use the D §0 glossary (`docs/plans/2026-09-23-ux-ia-appendix-d-copy.md` §0) wherever you write UI copy. Inbox lanes are **Needs you · To review · Queued · Applying · History** (planner decision 20); chips Proposed → Queued → Approved → Applied / Skipped; Accept's toast says Queued, not Accepted (decision 19). A web Queue on an agent-filed open proposal keeps the agent as filer — say so where the by-line shows. Planner Q8: map `claude-ai`/`Claude`, `codex-mcp-client`/`Codex`, a ChatGPT client name if you can find it in the MCP spec or client docs; unknown → title-cased words, never a slug; non-ASCII names display as sent.

## Scope

**Files this lane owns:** A's T-A2 and T-A3 ownership lists, plus these moves (planner, wave 2): **`frontend/app/applications/page.tsx`** (A §5 rows for the tracker, A §9's "Proposed by …" by-line; the `keepPreviousData` fix and the single-flight Queue for agent entry points already landed in wave 1's integration fixes `1f039066`/`49dc41dc` — keep them); **`frontend/components/app-sidebar.tsx`** (the count, the "Agent inbox" label, AND the "Chat" → "Assistant" item from A §5 / decision 5); `frontend/lib/types.ts` (the optional `proposed_by` / `proposal_proposed_by` fields); `frontend/components/analytics/agent-pipeline-card.tsx` (hook swap and its two strings); `app/jobs/[id]/page.tsx` (proposal pill and Overview card strings); `docs/entities/others.md` (A §10 sentence). New files: `lib/needs-you.ts`, `lib/agent-name.ts`, `lib/agent-links.ts`, `lib/inbox-filter.ts` (+ tests), `hooks/use-needs-you-count.ts`, `hooks/use-proposal-funnel.ts`, `components/proposals/cap-today.tsx`, `backend/tests/test_frontend_agent_inbox.py`. Deletes `components/proposals/funnel-strip.tsx`. REUSE wave 1's `ListToolbar`, `ListSearch`, `ListCapNotice` / `lib/list-cap.ts` — don't fork them (planner decision 15).

**The other wave-2 lane runs at the same time** (lane 5 inbox / lane 6 agent words). Don't edit its files. `docs/frontend-conventions.md` is shared: edit only the bullets your tasks name, never reflow other text.

**Never touch:** `SYSTEM.md` (1000/1000; queue changes below), `.slop-baseline.json` files, `docs/ux/`, other worktrees and branches, and the main checkout `/Users/ajeyds/Projects/maestro-career-studio` (live `data/` and the live Docker stack on 3000/8001: never `cd` there, never `docker compose`). Never bare `git stash`. Don't push, rebase or merge.

## Environment

- Python `/opt/anaconda3/bin/python3`; pytest and ruff from `<worktree>/backend`. Frontend from `<worktree>/frontend` (`npm ci` has been run): `npx tsc --noEmit`, `npm run lint` (0 errors, 5 baseline warnings; React Compiler rules at error level), `node --test lib/*.test.ts`, `npm run build`.
- **Browser checks:** scratch dir `/tmp/maestro-ia-lane5`; backend from `<worktree>/backend`: `/opt/anaconda3/bin/python3 -m uvicorn app.main:app --port 8851` with `DATABASE_URL=sqlite:////tmp/maestro-ia-lane5/app.sqlite3`, every `*_DIR` setting from `backend/app/config.py` under the scratch dir, `ALLOWED_WEB_ORIGINS=http://127.0.0.1:3251,http://localhost:3251`, `PATH=/Library/TeX/texbin:$PATH`, no LLM keys; frontend `API_PROXY_BACKEND=http://127.0.0.1:8851 npx next dev -p 3251` (open `http://localhost:3251`; run `npm run predev` first if it exists and delete what it copies afterwards). Seed MADE-UP data through the API (earlier seed scripts to crib: `/tmp/maestro-sweep-a/`, `/tmp/maestro-sweep-b/`, `/tmp/maestro-fix-sweep/scripts/`). Python Playwright (`from playwright.sync_api import sync_playwright`, `channel="chrome"`), real keys and pointer, light and dark, 1280/768/375; screenshots under the scratch dir; tear the stack down afterwards.

## Gates (per task, and all of them before you report done)

- The task's pins (seen FAILING first), plus every `backend/tests/test_frontend_*.py`. Mutation-check every pin you add: break the guarded code, see exactly that pin fail, restore from a backup copy (never `git stash`).
- tsc clean; lint 0 errors; node tests pass; `npm run build` (run last).
- Full backend suite `pytest tests/ mcp_server/tests/ -q` at least once before reporting (baseline at `61a4a15f`: see the plan's *Gate results*); `ruff check .`.
- Slop ratchet: frontend duplication measured on a CLEAN `git archive HEAD` export (`python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py scan <export>/frontend --json` → `duplication`) must stay ≤ **437 lines / 36 clones**; `slop_scan.py check frontend` and `check backend` OK from the export root; backend `complexity_hotspots` ≤ **424** (424 at the branch point: NO headroom, so split any new test or function that reaches cc 10 or 50 lines).
- Logic added in two places goes through a shared helper.

## Commits

One per task with the plan's commit message, ending `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Don't amend or squash earlier commits. Commit this doc's filled-in logs at the end.

## Escalation (autonomy: peer)

Adapt *how* when the plan conflicts with the code and log it below. If a change needs another lane's file, scope, or a Goal Card trade-off: log a deviation note (planned / found / proposed / Goal Card line) and carry on with the rest. Never expand scope.

## Deviation log

| Task | Planned | Did instead | Why (Goal Card line) |
|---|---|---|---|
| 13 | A7's `listCap(items.length, data?.total)` + `ListCapNotice state=` | Wave 1's API: `const PROPOSALS_LIMIT = 500` and `<ListCapNotice loaded={items.length} limit={PROPOSALS_LIMIT} total={data?.total} noun="proposals" />` (B8); B8's pin added to `test_frontend_sticky_lists.py` | Planner decision 15: reuse, don't fork |
| 13 | A's lane names (Triage, In flight) and A5's "Accepted." / bulk "could not be accepted" | Needs you · To review · Queued · Applying · History, "Nothing to review."; job-header Accept toast "Queued. A connected agent can apply to it now."; bulk toast verb "queued" | Decisions 19 and 20 (D wins on words) |
| 13 | "Say so where the by-line shows" (a web Queue that joins an agent's open proposal keeps the agent) | `queuedToast()` in `lib/agent-name.ts`: "Queued in your Agent inbox. Claude proposed it first." `promoteJobToAgentQueue` now returns the proposal's `proposed_by` (`undefined` from an older backend, which then claims nothing). Pins moved with it: `test_frontend_proposed_by.py` (the POST's type string) and `test_frontend_single_flight.py::test_a_queue_race_never_accepts_twice` (a guarded PATCH block instead of an early `return;`) | One word per thing: the by-line and the toast must not disagree without a reason given where the user acted |
| 13 | A9's mapper capitalises every word's first letter | A word the client already cased ("iPhone", "Café", "クロード", Cyrillic) is kept as sent; only all-lower-case words are capitalised, acronyms upper-cased | Planner Q8: non-ASCII names display as sent |
| 13 | Map ChatGPT's client name "if you can find it" | `/chatgpt\|openai/i` → "ChatGPT"; the real `clientInfo.name` is NOT verified (a web search found no primary source) | Planner Q8; left as a comment in the mapper |
| 13 | ProposalRow layout unchanged (only the by-line added) | The row's link wraps (`flex-wrap`, text `grow basis-[10rem]`, `p-3 sm:p-4`), the decorative monogram hides below `sm`; pinned by `test_a_narrow_row_wraps_instead_of_hiding_its_title` | Browser-found, pre-existing: in To review the title and by-line shrank to 2–3 letters at 768 and to nothing at 375 (shrink-0 base chip, badge and hover actions beside a basis-0 text block). "A new user understands every screen on first read"; A9 check 6 |
| 13 | O7: `html:has([data-slot="bulk-bar"]) { scroll-padding-bottom: 5rem }` | `html:has([data-slot="bulk-bar"]):has([data-slot="list-toolbar"] ~ :focus-within)`; `BulkBar` renders `data-slot="bulk-bar"`; `bulk-bar` joins `_SLOT_OWNERS` in `test_frontend_sticky_lists.py` | Lane 2's note: scoped like the toolbar's clearance (bare `html` jumps the page). Tab sweep: 0 of 25 stops under the bar |
| 13 | A6 defines `CONNECT_AGENT_GUIDE_URL` and its pin checks GETTING_STARTED §5 | Not added | Nothing renders it; an unused export and its pin would be dead code |
| 13 | A5 rows for `agent-pipeline-card.tsx` | Only rows 31 and 32 (description, Accepted → Queued) and the hook swap. D2.7's "Captured" → "Found", "Submitted" → "Applied" and its cap line stay for Task 17 | Scope: those rows are wave 3's |
| 13 | The sidebar's "Agent inbox" label in Task 13 (A1's pin) | Landed with Task 14 (the lane doc puts both sidebar labels in Task 14); A1's pin minus the sidebar is in Task 13 | Lane doc task split |
| 14 | An sr-only ", 3 need you" span completes the link's name (A4) | The link's `aria-label` is `${item.label}, ${badge.spoken}` when a badge shows; the pill stays `aria-hidden` | Browser-found in Chrome's AX tree (CDP `getFullAXTree`): the sr-only span, as a flex item and then inside the label (absolutely positioned either way), gave "Agent inbox , 3 need you". Label in Name (2.5.3) still holds |
| 14 | — | `lib/nav.test.ts`: one test title "…marks Agent Proposals instead" → "…marks it instead" (not on the ownership list) | It named the renamed item |
| 13 | — | Split `test_the_old_names_are_gone` and `test_a_bulk_queue_that_partly_fails_says_queued` out of two tests that reached cc 11 | Zero hotspot headroom (424) |

## Gate results

| Task | Gate | Result |
|---|---|---|
| 13 | new pins seen failing first | 23 failed, 1 passed (the frozen-URL pin, already true) before implementing |
| 13 | mutation checks | 37 mutations, each fails its own pin (harness: backup copy, mutate, pytest, restore). Two pins were weak on first try and were tightened: the lanes-after-toolbar pin (lanes inside the toolbar, or wrapped in a div, now fail it) and the row-wrap pin (it matched an inner `flex-wrap`; it now reads the link's own classes). Node tests: 3 lib mutations each fail 1 node test |
| 14 | new pins seen failing first | 6 failed (4 agent-inbox, 2 colour-role modes) |
| 14 | mutation checks | 12 mutations fail their pin; the contrast half proven separately: dark text orange-400 (source and pin) → "dark: needs-you badge on secondary-container-hover is 3.88:1"; 2 node mutations fail |
| 13+14 | `pytest tests/test_frontend_*.py` | 815 passed |
| 13+14 | full backend `pytest tests/ mcp_server/tests/ -q` | 5182 passed, 3 skipped (baseline after wave 1: 5149 passed, 3 skipped) |
| 13+14 | `ruff check .` | All checks passed |
| 13+14 | `node --test lib/*.test.ts` | 217 passed (was 200) |
| 13+14 | `npx tsc --noEmit` / `npm run lint` | clean / 0 errors, 5 warnings (baseline 5) |
| 13+14 | `npm run build` (last, stack stopped) | OK |
| 13, 14 | frontend duplication (clean export of the tree, `scan … --json`) | 437 lines / 36 clones (ceiling 437/36), after each task |
| 13, 14 | backend `complexity_hotspots` | 424 after each task (426 before splitting two cc-11 tests) |
| 13, 14 | `slop_scan.py check frontend` / `check backend` from the export root | OK / OK |
| 13 | browser (Chrome, Playwright, 1280/768/375, light and dark) | 54 + 37 checks pass: A1 names, Cap today + sr text, no funnel, toolbar (4 pill triggers 32px, one row at 1280, values, role labels, search acme/zzz with focus kept, Score 70+, Tab order, Enter/Arrow/Enter pick), lanes, by-lines for claude-ai, codex-mcp-client, "Café Agent", "クロード", unnamed, my-hunter_bot, job page (Back/prev/next labels, card title, Date fact, pill name "Proposed by Claude, status Proposed"), Accept toast, Queue (you) toast/card/pill, the race toast, tracker marks and group label, Analytics card words, empty state (links, targets, Tab order, lands on Settings › Connected agents, wraps at 375), failure + cap retry (focus not body), cap notice "…of your 812 proposals…" after History and under a filtered empty state, bulk bar clearance, no horizontal scroll at any width. Screenshots: `/tmp/maestro-ia-lane5/shots/t13-*` |
| 14 | browser | 14 checks pass: name "Agent inbox, 3 need you" (Chrome AX tree), pill "3", Assistant item, current row, two Skips → "1 needs you" with no reload, a Delete → plain "Agent inbox", an agent's request-decision appears in 60 s with no click, collapse hands focus to the reveal pill (no count), 375 sheet shows the badge without truncating the label; row states light and dark zoomed (`t14-states.png`) |

## Queued for Task 24 (SYSTEM.md changes Claude applies)

- §5 step 2: "(hunt inventory lives on `/proposals`)" → "(agent inventory lives in the Agent inbox, `/proposals`)"; "**Agent lane**" → "**Agent inbox**" (the tracker's filter group label).
- §5 step 3: "proposal pill" → "proposal pill (its filer in its name and on hover)"; "Agent proposal block" → "the proposal's Overview card, titled with its filer (`proposed_by`, worded by `lib/agent-name.ts`)".
- §12 candidate (2026-09-24): an sr-only span beside or inside a flex item is out of flow, and Chrome joins it into the accessible name with a space ("Agent inbox , 3 need you") → put a count that must read as one phrase in the control's `aria-label`; check names in Chrome's AX tree, not only Playwright's.
- §11 candidates (found, not fixed; out of this lane's scope):
  - A link rendered through `Button nativeButton={false} render={<a>}` gets `role="button"` (22 files, the Settings page's "Getting started guide" and this lane's empty-state links among them): screen readers announce links as buttons.
  - Focus lands on `<body>` after any client-side link navigation (the job page's Back to Agent inbox and Back to applications alike); A1 browser check 2 expected otherwise.
  - A "found by reading" items 2 (a selection survives a filter change, so the bulk bar acts on hidden rows) and 3 ("Expires" shows on queued proposals) are still open.
  - Until Task 17 (D2.7), the row icon and the bulk bar still say "Accept" while the result and its toast say Queued.

## Deferred to merge (edits left for Claude, with file:line)

- `docs/frontend-conventions.md` (shared with lane 6): this lane edited :53 (the Agent inbox's history filter), :551–:555 (the bulk bar's bottom clearance, inside lane 2's sticky bullet), :897 (the Agent inbox when `?from=proposals`), :917–:925 (sidebar groups: Agent inbox, Assistant, and the Needs-you count sentence) and :928 (Tracker filter: Agent inbox). The "Naming" bullet (A10's "one word per kind of agent") is lane 6's.
- Lane 6's `components/career/points-list.tsx` (A5 row 21) imports `agentDisplayName` from `lib/agent-name.ts`, which this lane creates; it resolves once both merge. Its `test_frontend_agent_words.py` sweep ("Found by agent", "Agent lane") passes on this lane's tracker (`app/applications/page.tsx:538`, `:643`, `:735`).
- README.md and `docs/GETTING_STARTED.md` still say "Agent Proposals" (lane 6's rows).
- The empty state's two GitHub links (`frontend/lib/agent-links.ts`) resolve only once local main is pushed; the anchor is checked against the local README by `test_the_empty_state_links_point_at_real_headings`.
- Planner Q8 not run: real client names from a `backups/` snapshot (`SELECT DISTINCT origin_detail FROM kb_points WHERE origin = 'mcp';`) need the main checkout, which this lane must not touch.
- Not verified here: WebKit/Safari; a real Claude Desktop or Codex session filing a proposal (seeded over REST with the MCP origin headers instead, including a percent-encoded non-ASCII name); a screen reader (names read from Chrome's AX tree).
