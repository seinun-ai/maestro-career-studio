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

**Files this lane owns:** A's T-A2 and T-A3 ownership lists, plus these moves (planner, wave 2): **`frontend/app/applications/page.tsx`** (A §5 rows for the tracker, A §9's "Proposed by …" by-line, and keep the previous rows on screen while the other source's list loads — `placeholderData: keepPreviousData` on the saved-jobs query — so the first switch to Agents never flashes a skeleton or snaps the scroll); **`frontend/components/app-sidebar.tsx`** (the count, the "Agent inbox" label, AND the "Chat" → "Assistant" item from A §5 / decision 5); `frontend/lib/types.ts` (the optional `proposed_by` / `proposal_proposed_by` fields); `frontend/components/analytics/agent-pipeline-card.tsx` (hook swap and its two strings); `app/jobs/[id]/page.tsx` (proposal pill and Overview card strings); `docs/entities/others.md` (A §10 sentence). New files: `lib/needs-you.ts`, `lib/agent-name.ts`, `lib/agent-links.ts`, `lib/inbox-filter.ts` (+ tests), `hooks/use-needs-you-count.ts`, `hooks/use-proposal-funnel.ts`, `components/proposals/cap-today.tsx`, `backend/tests/test_frontend_agent_inbox.py`. Deletes `components/proposals/funnel-strip.tsx`. REUSE wave 1's `ListToolbar`, `ListSearch`, `ListCapNotice` / `lib/list-cap.ts` — don't fork them (planner decision 15).

**The other wave-2 lane runs at the same time** (lane 5 inbox / lane 6 agent words). Don't edit its files. `docs/frontend-conventions.md` is shared: edit only the bullets your tasks name, never reflow other text.

**Never touch:** `SYSTEM.md` (1000/1000; queue changes below), `.slop-baseline.json` files, `docs/ux/`, other worktrees and branches, and the main checkout `/Users/ajeyds/Projects/maestro-career-studio` (live `data/` and the live Docker stack on 3000/8001: never `cd` there, never `docker compose`). Never bare `git stash`. Don't push, rebase or merge.

## Environment

- Python `/opt/anaconda3/bin/python3`; pytest and ruff from `<worktree>/backend`. Frontend from `<worktree>/frontend` (`npm ci` has been run): `npx tsc --noEmit`, `npm run lint` (0 errors, 5 baseline warnings; React Compiler rules at error level), `node --test lib/*.test.ts`, `npm run build`.
- **Browser checks:** scratch dir `/tmp/maestro-ia-lane5`; backend from `<worktree>/backend`: `/opt/anaconda3/bin/python3 -m uvicorn app.main:app --port 8851` with `DATABASE_URL=sqlite:////tmp/maestro-ia-lane5/app.sqlite3`, every `*_DIR` setting from `backend/app/config.py` under the scratch dir, `ALLOWED_WEB_ORIGINS=http://127.0.0.1:3251,http://localhost:3251`, `PATH=/Library/TeX/texbin:$PATH`, no LLM keys; frontend `API_PROXY_BACKEND=http://127.0.0.1:8851 npx next dev -p 3251` (open `http://localhost:3251`; run `npm run predev` first if it exists and delete what it copies afterwards). Seed MADE-UP data through the API (earlier seed scripts to crib: `/tmp/maestro-sweep-a/`, `/tmp/maestro-sweep-b/`, `/tmp/maestro-fix-sweep/scripts/`). Python Playwright (`from playwright.sync_api import sync_playwright`, `channel="chrome"`), real keys and pointer, light and dark, 1280/768/375; screenshots under the scratch dir; tear the stack down afterwards.

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

## Gate results

| Task | Gate | Result |
|---|---|---|

## Queued for Task 24 (SYSTEM.md changes Claude applies)

## Deferred to merge (edits left for Claude, with file:line)
