# UX IA and copy, wave 2 lane 6: agent-words — handoff to a Claude Opus 5.5 subagent

**Tasks:** Task 15 of `docs/plans/2026-09-23-ux-ia-copy.md`.
**Branch:** `claude/ux-ia-lane6-agent-words` (from `claude/ux-ia-copy-plan` at the commit that added this doc; wave 1 is merged into it).
**Worktree:** `/Users/ajeyds/Projects/maestro-ux-ia/lane6-agent-words`. Work only there.
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
4. Appendix A §5 (every inventory row EXCEPT the tracker page, the sidebar, the inbox/proposal files and `agent-pipeline-card.tsx`, which lane 5 owns) and §8 (the Connected agents card), planner decisions 16 (Q3, Q13), 18 (Q2), 19, 20. Lane 3's deferred note: replace the comment in `app/settings/page.tsx` with `<ConnectedAgentsCard />` and extend `test_connected_agents_keeps_its_order_and_a_place_for_the_explainer`; then drop `connected-agents` from `_RESERVED_CARD_IDS` in `backend/tests/test_frontend_settings_pages.py` so the equality pin covers it. Line numbers in the appendices are at `8cac7cf9`; wave 1 moved code, so re-locate by the quoted code.
5. **Words:** use the D §0 glossary (`docs/plans/2026-09-23-ux-ia-appendix-d-copy.md` §0) wherever you write UI copy. Use D §0 words (planner decision 19): "Companion" (not "the Companion browser extension"), the button is "Quick tailor" (not "Fast tailor"). The Connected agents card links the skills README and the README's "Going all the way: agent applications" section (compute anchors from local README/doc headings, pinned) and never implies the app itself hunts or applies.

## Scope

**Files this lane owns:** A's T-A4 ownership list MINUS `app/applications/page.tsx`, `components/app-sidebar.tsx` and `components/analytics/agent-pipeline-card.tsx` (lane 5 owns those): `components/source-toggle.tsx` (segment "Agents"; keep lane 2's `onPreview`), `components/career/points-list.tsx`, `components/settings/llm-endpoint.tsx` (only the "the chat agent" words — lane 4 rewrote this card; touch only A §5's rows), `components/settings/mcp-workflow-section.tsx`, `components/settings/auto-apply-section.tsx`, `components/settings/quick-tailor-section.tsx`, `components/settings/autofill-section.tsx` (A §5 rows only), `components/analytics/autofill-coverage-card.tsx`, `components/ats-score-panel.tsx`, `components/chat/proposal-card.tsx`, `components/chat/edit-proposal-card.tsx`, `components/resume-editor/instruct-sheet.tsx`, `backend/tests/test_frontend_dialog_drafts.py` (the one sentence), new `components/settings/connected-agents-card.tsx`, `app/settings/page.tsx` (the mount only), `backend/tests/test_frontend_settings_pages.py` (the order pin and `_RESERVED_CARD_IDS`), new `backend/tests/test_frontend_agent_words.py`, `README.md` and `docs/GETTING_STARTED.md` (A §5/§8 rows only).

**The other wave-2 lane runs at the same time** (lane 5 inbox / lane 6 agent words). Don't edit its files. `docs/frontend-conventions.md` is shared: edit only the bullets your tasks name, never reflow other text.

**Never touch:** `SYSTEM.md` (1000/1000; queue changes below), `.slop-baseline.json` files, `docs/ux/`, other worktrees and branches, and the main checkout `/Users/ajeyds/Projects/maestro-career-studio` (live `data/` and the live Docker stack on 3000/8001: never `cd` there, never `docker compose`). Never bare `git stash`. Don't push, rebase or merge.

## Environment

- Python `/opt/anaconda3/bin/python3`; pytest and ruff from `<worktree>/backend`. Frontend from `<worktree>/frontend` (`npm ci` has been run): `npx tsc --noEmit`, `npm run lint` (0 errors, 5 baseline warnings; React Compiler rules at error level), `node --test lib/*.test.ts`, `npm run build`.
- **Browser checks:** scratch dir `/tmp/maestro-ia-lane6`; backend from `<worktree>/backend`: `/opt/anaconda3/bin/python3 -m uvicorn app.main:app --port 8852` with `DATABASE_URL=sqlite:////tmp/maestro-ia-lane6/app.sqlite3`, every `*_DIR` setting from `backend/app/config.py` under the scratch dir, `ALLOWED_WEB_ORIGINS=http://127.0.0.1:3252,http://localhost:3252`, `PATH=/Library/TeX/texbin:$PATH`, no LLM keys; frontend `API_PROXY_BACKEND=http://127.0.0.1:8852 npx next dev -p 3252` (open `http://localhost:3252`; run `npm run predev` first if it exists and delete what it copies afterwards). Seed MADE-UP data through the API (earlier seed scripts to crib: `/tmp/maestro-sweep-a/`, `/tmp/maestro-sweep-b/`, `/tmp/maestro-fix-sweep/scripts/`). Python Playwright (`from playwright.sync_api import sync_playwright`, `channel="chrome"`), real keys and pointer, light and dark, 1280/768/375; screenshots under the scratch dir; tear the stack down afterwards.

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
