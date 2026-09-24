# UX IA and copy, wave 3 lane 9: copy-settings — handoff to a Claude Opus 5.5 subagent

**Tasks:** Task 21 of `docs/plans/2026-09-23-ux-ia-copy.md`.
**Branch:** `claude/ux-ia-lane9-copy-settings` (from `claude/ux-ia-copy-plan` at the commit that added this doc; waves 1–2 and Task 16 are merged into it).
**Worktree:** `/Users/ajeyds/Projects/maestro-ux-ia/lane9-copy-settings`. Work only there.
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
2. `docs/frontend-conventions.md` — Task 16 rewrote the Microcopy rules: the **glossary**, errors, separators, toasts, "(optional)", the placeholder rule (no example values in blank fields). They are binding. `frontend/AGENTS.md`.
3. The main plan `docs/plans/2026-09-23-ux-ia-copy.md`: Goal Card, *Owner decisions* (esp. 13–14), *Planner decisions* (esp. 19–20), the **Deviation log** (what waves 1–2 already changed, plan defects to avoid), and your tasks.
4. D §6 (Settings and Profile cards; D's lane L5) and D §7 (Assistant, shell, errors, setup; D's lane L6) in `docs/plans/2026-09-23-ux-ia-appendix-d-copy.md`, plus D §0 (glossary), D §1 (rules and shared primitives, landed in Task 16 as `lib/error-text.ts`: use `couldnt()` / `errorDetail()` for every error you rewrite), D §10 (the real bugs in your groups — fix each with its pin) and the lane docs of waves 1–2 (`docs/plans/2026-09-23-ux-ia-lane{1..6}-*.md`, *Deferred to merge* notes that name your files). D's line numbers are at `8cac7cf9`; waves 1–2 and Task 16 moved code, so re-locate by the quoted text and SKIP rows whose string no longer exists (log them).
5. Lane 4 already did D §6.1's model-card rows (its lane doc *Deferred to merge* lists what is done and what is left); lane 6 did the Connected agents card and A §5's settings rows — do only the deltas. Persona keeps its name (owner decision 13). The sidebar's "Agent inbox" and "Assistant" items are done (lane 5); D §7.1's remaining sidebar words (Career history, Add job) are yours.

## Also yours (found by the waves 1+2 integrated browser pass)

- `components/settings/connected-agents-card.tsx:~81,~90`: "for you to accept or skip" and "applications you accepted" → the inbox verb is **Queue** ("for you to queue or skip", "applications you queued"); keep the honesty nuance and update the card's exact-item pins.
- Profile › Autofill "Save autofill profile": a double-click sends two PUTs and two toasts → route through `useSingleFlight` (like Auto-apply and Persona) and add it to `test_frontend_single_flight.py` `_SITES`.
- Assistant "New chat" (`components/chat/chat-page.tsx`): a double-click creates two chat sessions → `useSingleFlight`, `_SITES` row.
Browser-verify each (one request per double-click; focus never on <body>).

## Your definition of done

- Every D row in your groups applied (or logged as dropped with a reason).
- Your ratchet pending blocks (`_PENDING_T21`) in `backend/tests/test_frontend_vocabulary.py`, `test_frontend_error_words.py` and `test_frontend_placeholders.py` (there the blocks are named `_PENDING_EXAMPLES_T<n>`) driven to **zero and deleted** (the ratchets fail if a count is higher or lower than actual — lower each block as you go).
- Every pin that read an old string updated to the new one (D lists them per group); no pin weakened.

## Scope

**Files this lane owns:** D's lanes L5 and L6 in Appendix D *File ownership*, re-checked against the current tree. Shared test files: edit only your own pending blocks and your own pin functions.

**The other wave-3 lanes run at the same time** (7 copy-jobs, 8 copy-resumes, 9 copy-settings, 10 companion-server). Don't edit their files. `docs/frontend-conventions.md` is shared: edit only bullets D assigns to your groups, never reflow other text.

**Never touch:** `SYSTEM.md` (1000/1000; queue changes below), `.slop-baseline.json` files, `docs/ux/`, other worktrees and branches, and the main checkout `/Users/ajeyds/Projects/maestro-career-studio` (live `data/` and the live Docker stack on 3000/8001: never `cd` there, never `docker compose`). Never bare `git stash`. Don't push, rebase or merge.

## Environment

- Python `/opt/anaconda3/bin/python3`; pytest and ruff from `<worktree>/backend`. Frontend from `<worktree>/frontend` (`npm ci` has been run): `npx tsc --noEmit`, `npm run lint` (0 errors, 5 baseline warnings; React Compiler rules at error level), `node --test lib/*.test.ts`, `npm run build`.
- **Browser checks:** scratch dir `/tmp/maestro-ia-lane9`; backend from `<worktree>/backend`: `/opt/anaconda3/bin/python3 -m uvicorn app.main:app --port 8873` with `DATABASE_URL=sqlite:////tmp/maestro-ia-lane9/app.sqlite3`, every `*_DIR` setting from `backend/app/config.py` under the scratch dir, `ALLOWED_WEB_ORIGINS=http://127.0.0.1:3273,http://localhost:3273`, `PATH=/Library/TeX/texbin:$PATH`, no LLM keys; frontend `API_PROXY_BACKEND=http://127.0.0.1:8873 npx next dev -p 3273` (open `http://localhost:3273`; run `npm run predev` first if it exists and delete what it copies afterwards). Seed MADE-UP data through the API (earlier seed scripts to crib: `/tmp/maestro-sweep-a/`, `/tmp/maestro-sweep-b/`, `/tmp/maestro-fix-sweep/scripts/`). Python Playwright (`from playwright.sync_api import sync_playwright`, `channel="chrome"`), real keys and pointer, light and dark, 1280/768/375; screenshots under the scratch dir; tear the stack down afterwards.

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
| 21 (pin homes) | D's new pins in `test_frontend_plain_words.py` and `test_frontend_error_words.py` (and the role-model pin in `test_frontend_settings_pages.py`) | One new file, `backend/tests/test_frontend_settings_assistant_words.py` (13 pins); the sidebar pins in `test_frontend_sidebar_nav.py` (L6's own file) | Lanes 7 and 8 append to the same shared files at the same time; a file of its own never conflicts (lane 4's precedent) |
| 21 (D6.2 row :50) | Quick tailor description "…here and in Companion." | Kept lane 6's reviewed "…on the gap analysis page and in the Companion." | Quick tailor doesn't run in Settings (lane 6's logged review fix; planner decision 20 for "the Companion" in a sentence) |
| 21 (D6.1 row :77) | Hint ends "Leave empty to use OpenAI." | "Leave empty to use OpenAI and Gemini." | With no address, Gemini models run on Gemini's API too; the card's own status line says "OpenAI and Gemini APIs" |
| 21 (D6.1 row :393) | FreeTextModel's hint "The model name your server uses." | The role hint plus "Type the model name your server uses." | The field already carries its role hint (Fast, Smart, Assistant); both stay in one `aria-describedby` |
| 21 (D6.1 row :169) | "The key stays as a small secondary line only for keys the map lacks" | A key `PROMPT_TITLES` lacks is the title itself (mono, wraps); titled prompts, the four curated ones included, no longer print their key | No raw key on screen for any known prompt; lane 4's wrap pin now also refuses the secondary key line. A pin checks every `backend/app/prompts/*.txt` has words |
| 21 (D7.2 row :152) | "Default: {template name}" | Additive `default_template_name` in `services/setup_status.py` (`getattr`, no new branch) + a `test_setup_status.py` test; the step reads it, fallback "Default template chosen" | The status carried only the id; the plan's contract rule allows an additive field |
| 21 (D7.2 row :126) | "40% done. Personal details are missing." built from the group label | `GROUP_MISSING`: one whole sentence per group (incl. the new eligibility group) | Subject-verb agreement per group ("Work authorization is", "Preferences are") without string surgery |
| 21 (D7.2 strip) | Pill "Autofill: 40% done" | Also the strip's accessible name joins label and state with a comma ("Autofill: 40% done, not finished") | Two colons read badly aloud |
| 21 (D7.2 dropzone) | "This file type isn't supported. Use PDF, Word, Markdown or text." | As written; `acceptExtensions` in `lib/upload-accept.ts`, its one caller gone, is deleted | No dead helper left behind |
| 21 (D7.3 rows :287-:296, :823) | Toasts and a confirm | Also: after a confirmed delete, focus moves to the next chat's row (`focusSuccessor` + an effect that waits for the row to leave the list, the catalog's pattern); the rows sit in their own wrapper so a neighbour is never the "Recent" heading | Focus never to `<body>` (browser-verified at 1280 and 375) |
| 21 (D7.4 scope picker) | `LoadErrorState` with Try again | Failure branch first (`isLoadFailure`), rows added to `_FAILURE_BRANCHES` and `_LOADING_GATES` in `test_frontend_query_error_states.py` | The query-state convention: a retry must not fall into the loading line |
| 21 (D7.4 cards) | "For {target}" | Tailored targets read "For the tailored resume…"; change card's dialog "Changes in version N of the tailored resume" | "For tailored resume for…" read broken |
| 21 (D6.4 toast) | "Filled {n} fields from your career history" | Count and noun agree ("1 field") | Toasts rule |
| 21 (prompt toasts) | not in D | "{name} instructions saved" / "…reset to default" | "Assistant saved" named the wrong thing once the card is "AI instructions" |
| 21 (conventions) | D1.1 f | f applied (sidebar bullet: Career history, Base resumes, Add job, Hide and Show sidebar), plus the Assistant page bullet (resume picker, `TOOL_PHRASES`, delete confirm, single-flight New chat), the prompts bullet (More instructions, `PROMPT_TITLES`), Settings vs Profile (AI instructions, Where you apply). g and h left to lane 7 (see Deferred) | Conventions change with the code they describe; g and h quote lane 7's strings |

## Gate results

| Task | Gate | Result |
|---|---|---|
| 21 | pending blocks | words 50 in 17 files → 0; raw errors 30 in 18 → 0; placeholders 15 → 0; `_PENDING_T21` (vocabulary, error words) and `_PENDING_EXAMPLES_T21` deleted, plus the autofill `_PASS_THROUGH` row |
| 21 | pins seen failing first | all 26 new or changed pins fail with HEAD's code swapped in (32 failures) |
| 21 | mutation checks | 26 mutations, each killed by exactly its pin (M11, deleting the `if (!ok) return;` gate, survived once: the delete pin now also orders the gate) |
| 21 | `test_frontend_*.py` | 973 passed (+ `test_setup_status.py`) |
| 21 | full backend | `pytest tests/ mcp_server/tests/ -q`: 5337 passed, 3 skipped; `ruff check .` clean |
| 21 | frontend | tsc clean; lint 0 errors, 2 warnings (baseline); node 230 pass; `npm run build` OK |
| 21 | slop (clean `git archive HEAD` of `0dc754c8`) | frontend duplication 437 lines / 36 clones; backend `complexity_hotspots` 424; `check frontend` and `check backend` OK |
| 21 | browser (1280 and 375, light and dark) | 202 scripted checks passed (plus a saved key reading "Saved" and, with the backend stopped, the load error reading "Maestro CS isn't responding…" with no docker, curl or port): D6.6 1–6, D7.6 1–6, connected agents "queue or skip", Save answers double-click (one PUT, one toast, focus kept), New chat double-click (one POST), chat delete confirm (Cancel keeps it with focus on Delete, Delete removes it, focus to the next chat) |

## Queued for Task 24 (SYSTEM.md changes Claude applies)

- §7 (in-app chat): the page and sidebar item are **Assistant**; its working chips are words (`TOOL_PHRASES`), deleting a chat asks first.
- §5 or §7 wherever "Prompts" or "Advanced prompts" appears: the card is **AI instructions**, the disclosure **More instructions**.
- `GET /api/setup/status` template detail gains `default_template_name` (additive), if §5 or `docs/entities/others.md` lists that payload.
- §11 candidate (not fixed, pre-existing): the Settings header's "Setup guide" is a Base UI `Button render={<a>}`, so a screen reader hears a button that navigates (lane 6 fixed the same shape on the Connected agents card with `buttonVariants` on a plain `<a>`).

## Deferred to merge (edits left for Claude, with file:line)

- `frontend/components/analytics/gap-tiers-panel.tsx:221` (lane 7): quotes the old switch name "Mirror JD wording"; it is now "Use the job description's wording when your experience backs it up" (`quick-tailor-section.tsx`). The backend's matching title is `backend/tests/test_explore_gaps.py:104` / the explore service (lane 10, D2.9/D9).
- `frontend/components/proposals/cap-today.tsx:42` (lane 7): "Daily submission cap: …" names a setting now called **Applications per day** (Settings › Connected agents › Auto-apply).
- `docs/frontend-conventions.md`, sidebar bullet: "The empty tracker's ghost New application" stays until lane 7 renames that button to Add job; D1.1 g (Naming bullet, Add job and the inbox words) and h (setup guidance: Save job, Score my resumes) quote lane 7's strings and were left to lane 7.
- `backend/tests/test_frontend_single_flight.py`: this lane appended two `_SITES` rows after the model-catalog rows; `test_frontend_query_error_states.py` gained one `_FAILURE_BRANCHES` and one `_LOADING_GATES` row (scope picker); `test_frontend_vocabulary.py`, `test_frontend_error_words.py` and `test_frontend_placeholders.py` lost the T21 block and its `_BLOCKS` / `_EXAMPLE_BLOCKS` entry: adjacent-line conflicts with lanes 7 and 8 are expected there.
- Not verified: the capability row "Writing · Structured answers · Assistant" (D6.6 1) needs a real model test (no LLM keys on this stack); the words are lane 4's and pinned there. D6.6 5 was checked through the dialog's text and accessible name, not a real screen reader.
