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
- Slop ratchet: frontend duplication measured on a CLEAN `git archive HEAD` export (`python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py scan <export>/frontend --json` → `duplication`) must stay ≤ **437 lines / 36 clones**; `slop_scan.py check frontend` and `check backend` OK from the export root; backend `complexity_hotspots` ≤ **424** (424 at the branch point: NO headroom, so split any new test or function that reaches cc 10 or 50 lines).
- Logic added in two places goes through a shared helper.

## Commits

One per task with the plan's commit message, ending `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Don't amend or squash earlier commits. Commit this doc's filled-in logs at the end.

## Escalation (autonomy: peer)

Adapt *how* when the plan conflicts with the code and log it below. If a change needs another lane's file, scope, or a Goal Card trade-off: log a deviation note (planned / found / proposed / Goal Card line) and carry on with the rest. Never expand scope.

## Deviation log

| Task | Planned | Did instead | Why (Goal Card line) |
|---|---|---|---|
| 15 | A8 card links the guide §5 and the skills README; this doc says the skills README and the README's agent-applications section | All three: "How to connect an agent", "Ready-made skills", "How agent applications work"; anchors pinned against the local headings | A Connected agents tab with no "how to connect" is a dead end; both specs hold |
| 15 | A8 guide links as `Button nativeButton={false} render={<a>}` | `<a className={buttonVariants({ variant: "outline", size: "sm" })}>` | Base UI gives that `<a>` `role="button"` (seen in the browser): a link announced as a button (WCAG 2.2 AA) |
| 15 | A8 sub-heads as `<p>`; `sm:grid-cols-2`; `mb-1.5`, `space-y-1` | `<h3>` naming each list; `CardContent @container/setting` + `@lg/setting:grid-cols-2`; grid gaps | Card titles are level-2 headings since wave 1; the rhythm pin refuses viewport columns and margins |
| 15 | A8 copy ("career record", "job postings", "daily submission cap below", "This web app never submits anything") | D0 words: career history, jobs, MCP spelled out once, "Apply to more jobs a day than you allow below.", "Maestro CS itself never looks for jobs or submits an application." Added one paragraph naming the Assistant and Companion ("Companion, the Maestro CS browser extension") | Planner decision 19; D0 puts the one Companion sentence on this tab; this doc: never imply the app hunts or applies |
| 15 | A8 imports the URLs from `lib/agent-links.ts` | Local constants in the card; the pin allows exactly one definition across the card and that lib | `lib/agent-links.ts` is lane 5's file (deferred to merge below) |
| 15 | A5 row 21 (`Written by` through `agentDisplayName`) | Not done | Needs lane 5's `lib/agent-name.ts` (deferred to merge below) |
| 15 | A5 row 23 (`llm-endpoint.tsx` "the chat agent") | No edit | Lane 4 already moved it to `models-section.tsx` as `gates: "the Assistant"` |
| 15 | A5 rows 40–47 and 30 as written | "Quick tailor", not "Fast tailor"; "Companion" bare in labels ("Allow Companion to …"), "the Companion" in sentences; "Skipping one job", not "posting" | Planner decisions 19 and 20 |
| 15 | A §5 sweep pin over every file | Skips `app/applications/page.tsx` and `agent-pipeline-card.tsx` | Lane 5 rewrites those words in the same wave (deferred to merge below) |
| 15 | Drop `connected-agents` from `_RESERVED_CARD_IDS` | Removed the set and its use | It would have been empty |
| 15 | — | `auto-apply-section.tsx` comment: "The Agent inbox and Analytics' Agent pipeline read the cap." (A2's row in this lane's file); README "decline" → "skip" beside the A10 rename | The funnel strip it named goes in lane 5; "Skip" is the app's verb (conventions, Naming) |
| 15 | — (unlogged at `16cc4373`) | `docs/frontend-conventions.md`, Settings-card bullet: "Appearance is the one exemption" became "Appearance and the Connected agents explainer (`connected-agents-card.tsx`) are the exemptions: they fetch nothing." | The card is a second fetch-nothing card; the bullet would have been wrong the day it landed (conventions change with the code) |
| 15 | A5 row 30: "A connected agent never saves or proposes these companies. Skipping one posting …" (unlogged at `16cc4373`) | Shipped "… never saves or proposes jobs at these companies. Skipping one job …"; the review fix below replaces it | "proposes these companies" reads as proposing a company; "job" per planner decision 20 |
| 15 review | **Plan defect (A §8):** the card text said agents can't "delete your career record" and listed only save/score/tailor/read/propose, and the lane shipped the same shape | "They can": Find jobs and file them in your Agent inbox for you to accept or skip · Read your career history and job preferences · Add to and change your career history (new or reworded bullets arrive as drafts; an item's dates, your summary, skills and contact details change at once) · Create, edit and tailor your resumes · Fill in and submit applications you accepted, after your yes. "They can't": Go past the daily limit below · Delete an item or a bullet from your career history · Connect from claude.ai or chatgpt.com in a browser. Paragraph adds "The daily limit below counts those yeses over the last 24 hours." and "stay with the agent while it applies" replaces "run apply sessions while you watch". The card's doc comment cites the MCP tools behind each line | Review I1 (planner decision): agents also write career history with no draft step (`kb_create_entity`, `kb_edit_entity`, `kb_edit_profile`), edit and create resumes, and submit; a new user was misled. Planner's example "Read and add to your career history, and change your summary, skills and contact details" left out `kb_edit_entity` (an item's dates and title) and `kb_edit_point`, so the line says "add to and change"; "Create" added for `create_base_resume`/`duplicate_base_resume` |
| 15 review | **Plan defect:** A5 row 45 (and D's row for `autofill-coverage-card.tsx:98-101`, which keeps it) wrote "Turn it off in the Companion's ⋯ menu." into the Clear confirm | "… It cannot be undone. Clearing removes what's recorded so far. Capture continues while the Companion runs." | Review I4 (planner decision): the Companion has no ⋯ menu and no capture switch (`extension/README.md:74-80`); "can't undo" kept The D row's rewrite must drop its "Turn it off in Companion's ⋯ menu." too (the pin refuses "⋯ menu" in this file) |
| 15 review | A5 row 30 (above) | "Connected agents can't propose jobs at these companies. Skipping one job does not block its company." | Review: the server refuses only the proposal (`routers/proposals.py:110`, case-insensitive exact name); an agent can still save the job |
| 15 review | A5 row 40 kept "one-shot tailoring" | Quick tailor description: "What Quick tailor may change on your resume, on the gap analysis page and in the Companion." | D0 bans "one-shot tailoring"; D6's row says "here and in Companion", but Quick tailor doesn't run in Settings, so the page is named |
| 15 review | A5 row 35 changed only the chat card's badge | The Ask-for-changes badge also reads `Suggested ${ops_count === 1 ? "edit" : "edits"}` | Plurals agree (D §0); the two cards say the same thing |
| 15 review | Queued for §11 (outline focus in dark) | Fixed in `components/ui/button.tsx`: the outline variant adds `dark:focus-visible:border-ring`; conventions' focus bullet says why; two pins in `test_frontend_color_roles.py` (a variant with its own dark border sets the ring on focus; the ring clears 3:1 against the outline's dark fills, rest and hover, on page, card, popover, sidebar, canvas and muted) | Review (WCAG 1.4.11): only the /50 halo showed (~2.16:1). secondary-container is left out of the outline surfaces: the ring on outline's fill there is 2.92:1, and no outline button sits on a tonal chip |
| 15 review | — | Auto-apply's leave guard also holds while the blocklist field has text: `useLeaveGuard(draft !== null \|\| blockInput.trim() !== "")`; the pin in `test_frontend_settings_cards.py` (not this lane's file; one assertion) now names it | Never lose typed text: a company typed but not added was dropped on leave without asking |

## Gate results

| Task | Gate | Result |
|---|---|---|
| 15 | new pins seen failing first | 34 failed (31 in `test_frontend_agent_words.py`, 2 settings-pages, 1 dialog-drafts), 50 passed |
| 15 | mutation checks | 47 mutations (every word row, the sweep, the preview, 15 card mutations incl. a duplicate constant in `lib/agent-links.ts` and a renamed README heading, mount removed and reordered, both guides, the stale note): each failed exactly its pin; removing the card's id or its mount also failed the tab-table equality pin, as intended |
| 15 | `test_frontend_*.py` | 816 passed |
| 15 | full backend `pytest tests/ mcp_server/tests/ -q` (on `16cc4373`) | 5183 passed, 3 skipped (5149 + the 34 new) |
| 15 | `ruff check .` | All checks passed |
| 15 | tsc / lint / node | clean / 0 errors, 5 baseline warnings / 200 passed |
| 15 | `npm run build` (last) | OK |
| 15 | slop, clean export of the committed tree (`868842fe`) | frontend duplication 437 lines / 36 clones; `check frontend` OK; `check backend` OK; backend hotspots 424 |
| 15 | `check_system_md.py` | OK, 1000/1000 |
| 15 | browser (8852/3252, light and dark) | Connected agents tab by mouse and keyboard at 1280/768/375: order explainer → hints → Auto-apply; two columns at 1280, stacked at 768 and 375; no page overflow; lists named "They can" / "They can't"; Tab order panel → Agent inbox → the three guides → Auto-apply fields, each with a visible ring; Agent inbox by click and by Enter opens `/proposals` in place; each guide opens a new tab with no opener; `/settings#connected-agents` and `?tab=agents#connected-agents` select the tab and ring the card. Every changed string seen in both themes: hints and Auto-apply cards, Quick tailor, Profile › Autofill, Analytics coverage card and its Clear confirm, All · You · Agents on Analytics and the tracker, Career history chips (origins mocked), chat Suggested edit / edits / project (session mocked), the Applied-with-base confirm, Ask for changes (Suggest edits → Suggest again, No edits suggested, and the stale note after a studio Save) |
| 15 review | new pins seen failing first | 12 failed before the fix (the "can" and "can't" lists, the honesty paragraph, 7 word rows, the outline dark-border pin, the leave-guard pin); the ids, headings, label-with-URL, `REPO`, stale-note and outline-contrast pins passed on the old code and were proved by mutation |
| 15 review | mutation checks (`775caf68`'s tree, every `test_frontend_*.py`) | 23 mutations, each failing exactly its pin: "after your yes" dropped, "Submit applications for you." swapped in, the resumes line dropped, "apply at once" → "wait for your approval" (can list); "Delete anything", "Apply to more jobs a day…" (can't list); the M1 sentence, the daily-limit sentence, "run apply sessions" back (honesty); two guide labels swapped (label with URL); `REPO` owner changed (`REPO` vs CITATION.cff); `cantId = canId` and the "They can't" heading renamed (headings/ids); the stale note's second sentence dropped (dialog drafts); "⋯ menu" back, the new Clear sentence dropped, "It cannot be undone." dropped (word rows); Quick tailor and blocklist copy reverted (their two word rows each, the gone and the present); the badge reverted; `dark:focus-visible:border-ring` dropped (dark-border pin); `dark:hover:bg-input/100` (outline contrast pin: 2.56:1 on muted); the leave guard reverted (settings cards) |
| 15 review | `test_frontend_*.py` | 824 passed |
| 15 review | full backend `pytest tests/ mcp_server/tests/ -q` (tree of `775caf68`) | 5191 passed, 3 skipped (5183 + 8 new) |
| 15 review | `ruff check .` / tsc / lint / node | All checks passed / clean / 0 errors, 5 baseline warnings / 200 passed |
| 15 review | slop, clean export of `775caf68` | frontend duplication 437 lines / 36 clones; `check frontend` OK; `check backend` OK; backend hotspots 424 |
| 15 review | `npm run build` (last) | OK |
| 15 review | browser (8852/3252, fresh `.next/dev`) | Card at 1280 and 375, light and dark: the five "can" and three "can't" items read as pinned, headings name distinct lists, two columns at 1280 and stacked at 375, no page overflow, guides link where their labels say. Dark focus by keyboard: the three guides, Settings' "Getting started guide" and Auto-apply's "Add" each show a solid 1px ring border (4.3 to 5.0:1 against the fill, 4.8 to 5.4:1 against the surface) plus the halo. Blocklist: "Made Up Staffing Co" typed, not added, then the Analytics link: "Leave without saving?" asks; Stay keeps the text; a blank field leaves freely. Clear confirm reads "… It cannot be undone. Clearing removes what's recorded so far. Capture continues while the Companion runs." (light and dark). Ask for changes: one op "Suggested edit", two ops "Suggested edits" (mocked, light and dark) |

## Queued for Task 24 (SYSTEM.md changes Claude applies)

- §7 vocabulary: the in-app chat is the **Assistant**, MCP clients are **connected agents** (Settings › Connected agents opens with the explainer card), the extension is **Companion**.
- Task 16's vocabulary ratchet: add `("frontend/components/settings/connected-agents-card.tsx", "browser extension")` to `_ALLOWED` (D0's one Companion sentence lives in this card), and let "MCP" stand in that card only.
- §11 candidates (pre-existing, not fixed here): (a) fixed in the review round (outline Button's dark focus border, see the deviation log), so no §11 item; (b) about 40 `Button nativeButton={false} render={<a …>}` sites are announced as buttons (`role="button"` on the `<a>`), including Settings' "Getting started guide" and the About card's releases link.
- README and `docs/GETTING_STARTED.md` beyond A10's rows: the guide's "Words used in this guide" still says "Career record (Career KB)" and §4 "The browser extension".

## Deferred to merge (edits left for Claude, with file:line)

- **Lane 5's `frontend/lib/agent-links.ts` lacks `CONNECT_AGENT_GUIDE_URL`.** At merge it gains it (`${REPO}/docs/GETTING_STARTED.md#5-connect-your-ai-assistant-optional`, `REPO` = `https://github.com/seinun-ai/maestro-career-studio/blob/main`), lane 5's pin gets its getting-started heading assertion back, and this lane's duplicate `_github_slug` and heading checks in `test_the_card_links_point_at_real_headings` go, keeping one pin (with the `REPO`-equals-CITATION.cff check). The controller does this at merge.
- `frontend/components/settings/connected-agents-card.tsx:16-21`: delete `REPO` and the three URL constants; `import { AGENT_APPLICATIONS_URL, CONNECT_AGENT_GUIDE_URL, JOB_HUNT_SKILL_URL } from "@/lib/agent-links";` (lane 5's file). `test_the_card_links_point_at_real_headings` fails while both files define them, by design.
- `frontend/components/career/points-list.tsx:315`: A5 row 21, ``title={point.origin_detail ? `Written by ${agentDisplayName(point.origin_detail) ?? point.origin_detail}` : undefined}`` with `import { agentDisplayName } from "@/lib/agent-name";`, plus a row in `_WORDS` (`test_frontend_agent_words.py`). The browser showed "Written by claude-ai" until then.
- `backend/tests/test_frontend_agent_words.py:87-89,96-97`: delete `_INBOX_LANE_FILES` and its skip once lane 5's tracker and Agent pipeline words are in.
- `docs/frontend-conventions.md`, Naming bullet ("One word per kind of agent"): append A10's "A filer is named through `lib/agent-name.ts`, never printed raw." if lane 5 did not.
- `frontend/lib/settings-tabs.ts:26`: the comment "`connected-agents` is the explainer card wave 2 mounts first in this tab" can drop "wave 2" (not this lane's file).
