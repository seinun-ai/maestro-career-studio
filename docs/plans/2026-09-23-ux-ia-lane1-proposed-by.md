# UX IA and copy, wave 1 lane 1: proposed-by — handoff to a Claude Opus 5.5 subagent

**Tasks:** Task 1 of `docs/plans/2026-09-23-ux-ia-copy.md`, in that order.
**Branch:** `claude/ux-ia-lane1-proposed-by` (from `claude/ux-ia-copy-plan` at the commit that added this doc).
**Worktree:** `/Users/ajeyds/Projects/maestro-ux-ia/lane1-proposed-by`. Work only there.
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
4. The appendix sections your tasks cite: A §9 (backend and MCP half only: model, schemas, routers, services, the SQLite migration and the legacy Postgres revision, MCP server and client, backend and MCP tests, `docs/entities/others.md`). They hold the exact code; line numbers are at `8cac7cf9`, so re-locate by the quoted code.
5. **Words:** where your appendix proposes UI copy, use the D §0 glossary word instead if they differ (planner decision 19; `docs/plans/2026-09-23-ux-ia-appendix-d-copy.md` §0).

## Scope

**Files this lane owns:** A's T-A1 ownership list (Appendix A, *File ownership*). Backend and MCP only: no `frontend/` file.

**Other wave-1 lanes run at the same time** (lane 1 proposed-by: backend/MCP; lane 2 lists: tables, toolbars, Applications, cap notice; lane 3 settings-tabs: the two pages, tabs, deep links, leave guard; lane 4 settings-cards: the cards). Don't edit their files. `docs/frontend-conventions.md` is shared: edit only the bullets your tasks name, never reflow other text.

**Never touch:** `SYSTEM.md` (1000/1000; queue changes below), `.slop-baseline.json` files, `docs/ux/`, other worktrees and branches, and the main checkout `/Users/ajeyds/Projects/maestro-career-studio` (live `data/` and the live Docker stack on 3000/8001: never `cd` there, never `docker compose`). Never bare `git stash`. Don't push, rebase or merge.

## Environment

- Python `/opt/anaconda3/bin/python3`; pytest and ruff from `<worktree>/backend`. Frontend from `<worktree>/frontend` (`npm ci` has been run): `npx tsc --noEmit`, `npm run lint` (0 errors, 5 baseline warnings; React Compiler rules at error level), `node --test lib/*.test.ts`, `npm run build`.
- **Browser checks:** scratch dir `/tmp/maestro-ia-lane1`; backend from `<worktree>/backend`: `/opt/anaconda3/bin/python3 -m uvicorn app.main:app --port 8811` with `DATABASE_URL=sqlite:////tmp/maestro-ia-lane1/app.sqlite3`, every `*_DIR` setting from `backend/app/config.py` under the scratch dir, `ALLOWED_WEB_ORIGINS=http://127.0.0.1:8811,http://localhost:8811`, `PATH=/Library/TeX/texbin:$PATH`, no LLM keys; no frontend needed. Seed MADE-UP data through the API (earlier seed scripts to crib: `/tmp/maestro-sweep-a/`, `/tmp/maestro-sweep-b/`, `/tmp/maestro-fix-sweep/scripts/`). Python Playwright (`from playwright.sync_api import sync_playwright`, `channel="chrome"`), real keys and pointer, light and dark, 1280/768/375; screenshots under the scratch dir; tear the stack down afterwards.

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
| 1 | Revision ids `3ac279fcc4b9` (SQLite) and `08b05599ef28` (legacy) from A §9 | Generated fresh: `9a5744f9b9d9` (SQLite) and `3a17da2f7144` (legacy), `uuid.uuid4().hex[:12]`, grep-checked for collisions | The lane doc and SYSTEM.md §9 require generated ids |
| 1 | The router takes the MCP header's detail as the filer | The rule lives in `services/proposals.proposal_filer`. An MCP client whose self-declared name is "you" in any case (`you`, `You`, ` YOU `) is stored as NULL | "An agent can never file as you". `clientInfo.name` is self-declared, so A §9's rule let a client call itself "you" and read as "Queued by you" |
| 1 | Add a third column to both newest-proposal queries in `routers/jobs.py` | Both use one `_newest_proposal_columns()` and `_stamp_newest_proposal()` | "Logic added in two places goes through a shared helper" |
| 1 | Add `proposed_by=` to both `ProposalRead(...)` field lists in `routers/proposals.py` | Separate commit `7207dc29`: one `_read_fields()` feeds the list and the detail | The field lists were a 16-line clone. The new field made it 17 lines and failed the slop ratchet (backend duplicated_lines 418 → 419). Now 402 lines, 44 clones |
| 1 | Tests only in new files and `test_proposal_tools.py` | Also `tests/tools/test_migrate_from_postgres.py`: pulled the skip-or-fail block out as `_legacy_source_url()` and added `test_the_legacy_chain_backfills_proposed_by_and_the_import_copies_it` (`legacy_postgres` marker) | CI's legacy job runs only that file with `-m legacy_postgres`, and the legacy revision's backfill needs a real Postgres to prove |
| 1 | Prove `clientInfo.name` by reading the installed package | `test_propose_application_names_the_client_its_session_declared` runs the real in-memory MCP client and server (`mcp.shared.memory`) with `clientInfo.name="claude-ai"` and no env fallback. Also run under the pinned `mcp==1.29.1` from the local uv cache, and over real stdio against a scratch backend | The task says to prove it with a test, not an assumption |
| 1 | A10's `others.md` UI words ("`/proposals` (the Agent inbox)", "Overview card titled with its filer") | Only the backend fact landed (column, header rule, backfill key, `proposal_proposed_by`) | Those UI pieces don't exist until T-A2 (wave 2). The doc would describe UI that isn't built yet |
| 1 | `mcp_server/server.py`: propose only | Also changed the first line of `_client_label`'s docstring and `client._origin_headers`' docstring so they mention proposals | They now name a proposal's filer too. Docstrings only, no behaviour change |

## Gate results

| Task | Gate | Result |
|---|---|---|
| 0 | Full backend suite at the branch point (`6366ec27`) | 4968 passed, 3 skipped (269 s) |
| 1 | New pins seen FAILING first | 18 failed before any implementation: 14 in `tests/test_proposals_proposed_by.py`, 2 in `mcp_server/tests/test_client_proposals.py`, 2 in `test_proposal_tools.py` (`passes_the_client_label` and the end-to-end session test). `keeps_ctx_out_of_its_schema` passed trivially before (no `ctx` param existed) and is mutation-checked below. The legacy Postgres test was seen failing by mutation only (`source lacks ['proposed_by']` with the revision removed, on a fresh database) |
| 1 | New pins after implementation | All pass: 14 + 2 + 3 new, plus the changed `test_propose_application_tool_calls_client` |
| 1 | Full backend suite `pytest tests/ mcp_server/tests/ -q` | 4987 passed, 4 skipped (269 s). +19 tests. The +1 skip is the new `legacy_postgres` test, which skips without a URL |
| 1 | Legacy Postgres tests (`-m legacy_postgres`, throwaway Postgres 16 cluster on :55811 under `/tmp/maestro-ia-lane1/pg`) | 2 passed: `test_export_from_real_postgres` and the new backfill-and-copy test |
| 1 | MCP suite under the pinned `mcp==1.29.1` (`PYTHONPATH` = uv cache wheel `~/.cache/uv/archive-v0/TIYCHzM2gFfXD2IJh-lRp`) | 318 passed, including the docstring budget ratchet and the end-to-end `clientInfo` test. The local anaconda has 1.26.0; that run also passes |
| 1 | Real stdio MCP round trip (scratch uvicorn :8811, `/tmp/maestro-ia-lane1/app.sqlite3`, made-up jobs), under both 1.26.0 and 1.29.1 | `claude-ai` → `"claude-ai"`; `codex-mcp-client` → `"codex-mcp-client"`; a client named `You` → null; an empty name → null; re-filing an open job as codex keeps `"claude-ai"`; a web POST with `proposed_by:"you"` → 201 `"you"`; a body with `"Claude"` → 422. List, `/api/jobs` and job detail all carry the same values. Stack torn down |
| 1 | Mutation checks (`/tmp/maestro-ia-lane1/mutate.py`, restored from backup copies each time, `git status` clean afterwards) | 12 of 12 caught. No casefold "you" guard → 3 parametrized cases fail. Body wins over the MCP header → 4 fail. Body accepts any string → `a_body_can_only_say_you`. Reads drop the field → 3 fail. The idempotent path overwrites the filer → `keeps_the_first_filer`. Jobs router doesn't set the filer → `job_reads_carry…`. No SQLite backfill → `migration_backfills…`. No legacy backfill → the legacy Postgres test. Legacy revision deleted → `legacy_chain_adds_the_column_at_its_head`, plus both Postgres tests on a fresh database. Server doesn't pass the label → 2 fail. `ctx` typed `Any` → schema test and end-to-end test. Client sends no headers → 2 fail |
| 1 | `ruff check .` | All checks passed |
| 1 | `check_system_md.py` | OK, 1000/1000 |
| 1 | Slop, backend (clean `git archive HEAD` export at `7207dc29`) | `check backend` OK. `complexity_hotspots` 423 → 423 (limit 424). Duplication 418 lines / 45 clones → 402 / 44. orphan_loc 0 |
| 1 | Slop, frontend (same export) | `check frontend` OK. Duplication 437 lines / 36 clones (ceiling 437 / 36; no frontend file changed) |
| 1 | Frontend `node --test lib/*.test.ts` | 135 of 136 pass. The one failure, `lib/studio.test.ts`, is `ERR_MODULE_NOT_FOUND @tanstack/query-core`: this worktree has no `node_modules` (the lane doc says `npm ci` had run; it hadn't) |
| 1 | Frontend tsc, lint, `npm run build` | NOT RUN: no `node_modules`. The lane touches no `frontend/` file (`git diff 6366ec27 HEAD -- frontend` is empty), so these can't have moved. `npx tsc` without the local package fetched and ran the unrelated npm package `tsc@2.0.4`, which only printed a notice. No project file changed |

## Queued for Task 24 (SYSTEM.md changes Claude applies)

- §2 `migrations/` line: "alembic: ONE SQLite baseline (see §12 …)" → "alembic: the SQLite chain, baseline
  `871d0425b64c` plus revisions (first: `9a5744f9b9d9`, `proposed_by`); see §12 for the revision-id gotcha".
- §7, the proposal-ledger clause: add "`propose_application` stamps `proposed_by` from the client's
  `clientInfo.name` (the KB writes' origin headers); an agent can never file as 'you'".
- §13 `postgres-to-sqlite`: the boxed chain now ends at `3a17da2f7144` (a mirror revision, so the import stays
  strict), not `85a1bb628e28`. The deletion list gains the two tests that exercise that revision:
  `tests/test_proposals_proposed_by.py::test_the_legacy_chain_adds_the_column_at_its_head` and
  `tests/tools/test_migrate_from_postgres.py::test_the_legacy_chain_backfills_proposed_by_and_the_import_copies_it`
  (the latter goes with the importer's tests anyway).
- §5 steps 2–3 (A10's wording on the Agent inbox, the filer in the pill, and the proposal card titled with its
  filer) belong with wave 2, when that UI exists.
- Stale text, not SYSTEM.md: the SQLite baseline's docstring (`871d0425b64c`) still says "the 54-revision
  Postgres chain (head 85a1bb628e28)". It was true when written; left alone, since it's a migration file.

## Deferred to merge (edits left for Claude, with file:line)

- `frontend/lib/api.ts:193-207` `promoteJobToAgentQueue` must send `proposed_by: "you"` in its POST body (T-A2
  owns the file). Until it does, a web "Queue for agent" filed after this migration stores NULL ("a connected
  agent"). Only rows promoted BEFORE the migration are backfilled. Keep its
  `plan: { summary: "Promoted from the tracker by the user" }`: both migrations key the backfill on that exact text.
- `frontend/lib/types.ts`: optional `proposed_by?: string | null` on the proposal type and
  `proposal_proposed_by?: string | null` on the job type (T-A2).
- `docs/entities/others.md` ApplicationProposal, "Web surface" sentence: "`/proposals` triage inbox" → "`/proposals`
  (the Agent inbox)"; "Agent proposal Overview block" → "the proposal's Overview card, titled with its filer" (A10;
  lands with T-A2's UI).
- Planner Q8 (real client names): NOT checked. The `backups/` snapshot is in the main checkout, which this lane must
  not touch. The only names used here are the synthetic `claude-ai` and `codex-mcp-client` from A §9. The
  frontend mapper (T-A2) should run the query A-Q8 gives on a backup snapshot before merge.
