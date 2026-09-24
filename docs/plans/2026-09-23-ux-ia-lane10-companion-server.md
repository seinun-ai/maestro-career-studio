# UX IA and copy, wave 3 lane 10: companion-server — handoff to a Claude Opus 5.5 subagent

**Tasks:** Tasks 22 and 23 of `docs/plans/2026-09-23-ux-ia-copy.md`.
**Branch:** `claude/ux-ia-lane10-companion-server` (from `claude/ux-ia-copy-plan` at the commit that added this doc; waves 1–2 and Task 16 are merged into it).
**Worktree:** `/Users/ajeyds/Projects/maestro-ux-ia/lane10-companion-server`. Work only there.
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
4. D §8 (the Companion side panel; D's lane L7) and D §9 (server-written words the UI shows; D's lane L8) including D §9.1's stable health finding ids BEFORE any health wording change in `docs/plans/2026-09-23-ux-ia-appendix-d-copy.md`, plus D §0 (glossary), D §1 (rules and shared primitives, landed in Task 16 as `lib/error-text.ts`: use `couldnt()` / `errorDetail()` for every error you rewrite), D §10 (the real bugs in your groups — fix each with its pin) and the lane docs of waves 1–2 (`docs/plans/2026-09-23-ux-ia-lane{1..6}-*.md`, *Deferred to merge* notes that name your files). D's line numbers are at `8cac7cf9`; waves 1–2 and Task 16 moved code, so re-locate by the quoted text and SKIP rows whose string no longer exists (log them).
5. MCP and agent-facing text: change only what the web UI or the Companion shows, keep machine-read strings (D §9.7), keep MCP docstrings under the budget ratchet, and never break an agent-facing meaning. The gap page matches the exact server text "No actionable resolutions to tailor" — keep it. Extension tests live in `backend/tests/test_extension_*.py`; the Companion has no build step (load-unpacked), so browser-check it by loading the unpacked extension in Chrome for Testing if you can, else say so.

## Your definition of done

- Every D row in your groups applied (or logged as dropped with a reason).
- Your ratchet pending blocks (`_PENDING_T22` (Task 23's server strings have no frontend ratchet: pin each changed message in the backend tests D §9.8 names)) in `backend/tests/test_frontend_vocabulary.py`, `test_frontend_error_words.py` and `test_frontend_placeholders.py` (there the blocks are named `_PENDING_EXAMPLES_T<n>`) driven to **zero and deleted** (the ratchets fail if a count is higher or lower than actual — lower each block as you go).
- Every pin that read an old string updated to the new one (D lists them per group); no pin weakened.

## Scope

**Files this lane owns:** D's lanes L7 and L8 in Appendix D *File ownership*, re-checked against the current tree. Shared test files: edit only your own pending blocks and your own pin functions.

**The other wave-3 lanes run at the same time** (7 copy-jobs, 8 copy-resumes, 9 copy-settings, 10 companion-server). Don't edit their files. `docs/frontend-conventions.md` is shared: edit only bullets D assigns to your groups, never reflow other text.

**Never touch:** `SYSTEM.md` (1000/1000; queue changes below), `.slop-baseline.json` files, `docs/ux/`, other worktrees and branches, and the main checkout `/Users/ajeyds/Projects/maestro-career-studio` (live `data/` and the live Docker stack on 3000/8001: never `cd` there, never `docker compose`). Never bare `git stash`. Don't push, rebase or merge.

## Environment

- Python `/opt/anaconda3/bin/python3`; pytest and ruff from `<worktree>/backend`. Frontend from `<worktree>/frontend` (`npm ci` has been run): `npx tsc --noEmit`, `npm run lint` (0 errors, 5 baseline warnings; React Compiler rules at error level), `node --test lib/*.test.ts`, `npm run build`.
- **Browser checks:** scratch dir `/tmp/maestro-ia-lane10`; backend from `<worktree>/backend`: `/opt/anaconda3/bin/python3 -m uvicorn app.main:app --port 8874` with `DATABASE_URL=sqlite:////tmp/maestro-ia-lane10/app.sqlite3`, every `*_DIR` setting from `backend/app/config.py` under the scratch dir, `ALLOWED_WEB_ORIGINS=http://127.0.0.1:3274,http://localhost:3274`, `PATH=/Library/TeX/texbin:$PATH`, no LLM keys; frontend `API_PROXY_BACKEND=http://127.0.0.1:8874 npx next dev -p 3274` (open `http://localhost:3274`; run `npm run predev` first if it exists and delete what it copies afterwards). Seed MADE-UP data through the API (earlier seed scripts to crib: `/tmp/maestro-sweep-a/`, `/tmp/maestro-sweep-b/`, `/tmp/maestro-fix-sweep/scripts/`). Python Playwright (`from playwright.sync_api import sync_playwright`, `channel="chrome"`), real keys and pointer, light and dark, 1280/768/375; screenshots under the scratch dir; tear the stack down afterwards.

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
| 22 | D8 writes a bare "Companion" in sentences ("Companion can't read this page", "Companion never fills this", "open Companion again", "Companion picks up …") | "The Companion …" in every sentence; labels keep the bare name | The Task-16 glossary (planner decision 20, Q8): a proper name in labels, "the Companion" in sentences. One word per thing |
| 22 | D8 §8.1 "per call site" sentences, "Check that Maestro CS is running." when `err.status` is undefined, else "Try again." | `duringAction(store, kind, call, failed)` with `failed` = "Couldn't <what>." or `{what, answered}`; `failureNote` in `actions/during.js` is the one place that finishes the sentence. Quick tailor's refusal and Q&A's 400 are `answered` sentences, so they apply only when the backend answered. A message the panel wrote itself passes through as `guidedRun.shown(text)` (NO_FRAME_REACHED, the attach refusals, the missing tailored PDF, the stopped fill). The 409/400 test fixtures gained `status` (the real service worker sends it) | Logic in two places goes through a shared helper; no raw error text on screen |
| 22 | D8 panel.js:1070 one sentence for any failed match | Two: no HTTP answer → "Couldn't reach Maestro CS. Check that it's running."; the backend answered with an error → "Couldn't check this page in Maestro CS. Try again." (`result.status` now rides the failed match) | Every sentence tells the truth: "check it's running" is the wrong step for a 500 |
| 22 | D8 score.js:98 "Best match: ${name} (ATS score n)." with `name` undefined | `display_name || slug`, as before: `display_name` is nullable and the slug is the only name left | Scope: D8 named no fallback |
| 22 | D8.2 "fold or delete the two engine tests" | Deleted `test_a_library_scored_by_two_engines_names_neither` (its subject is gone); the other became `test_the_count_is_of_the_rows_the_ranking_shows` (retired rows still not counted) | Its remaining claim is still worth a pin |
| 22 (new) | Not in D8 | panel.css `.seg button`: `text-wrap: balance`, line height 1.25. Found in Chrome for Testing at 320px: "Saved answers + AI" left "AI" alone on line two; now both labels read "Saved / answers …" (one line from 360px). Own commit `049c1c7d`, pinned | WCAG and first-read clarity at the panel's narrowest width |
| 23 | D9.1 "for every rule whose issue changes, pass the old text" | Every reworded ASK and NOTE finding keys on its old text (analogue, ambiguous, covered gap, C2 ask, projects-heavy, buried). Gate-type findings (S1, S2, S4, C1, C2 escalated) do not: no answer is ever saved on one (answers need an ask with a content hash; waivers key on the gate id), and their old text cannot be rebuilt from the gate dict | Saved answers are never asked again; no key that nothing reads |
| 23 | D9.2 S3 detail as one line per bad date | Joined with ", " (was "; ") | No semicolon in UI text |
| 23 | D9.2 layers flags end with a full stop; gap_analysis:195 "keep" | `gap_analysis` strips the flag's final stop before ". Fix this in the base resume." (pinned exactly) | Otherwise the gap page prints ".." |
| 23 | D9.6 llm.py "The AI model didn't answer ({short provider reason})" | Short reason = "error 429: insufficient_quota" / "no connection" / "it timed out"; the provider's full text stays on `LLMProviderError.provider_detail`, and `llm_capabilities._never_reached_the_model` reads that (it classified by the error TEXT: "error code: 401", "incorrect api key"). The no-key message's `.env` hint moved to the log | The capability probe would have stored false Nos for a bad key: never break what a check reads |
| 23 | D9.8 says `test_llm.py:210-211` and `test_llm_capabilities.py:99-102` still hold | They did not ("OPENAI_API_KEY" in the message, "configured separately"): rewritten to the exact new sentences, the env var pinned in the log via caplog | Pins read the new words; none weakened |
| 23 | D9.6 services/proposals.py:94 "This proposal is already {status label} and can't be changed." | "… already {word} and can't be changed that way.", words from the Agent inbox's chips in lower case (proposed, waiting on you, queued, approved, applied, skipped, expired) | Some refused moves start from a state that is not final |
| 23 | D9.6 routers/career_kb.py:495 drops the reason | A model's "insufficient" reason is kept: "Couldn't find anything to add in this file (…). Create the item yourself, then attach the file on its page." (an unreadable file keeps D9's sentence) | `test_ingest_insufficient_document_returns_422` pins the reason as a regression (a certificate with only a name) |
| 23 | D9.4 tailoring_session:1222 new sentence | Same sentence; the gap ids it dropped go to the log (the test's gap-id assert moved to caplog) | **Agent note:** an MCP agent no longer sees which gap ids went stale in the error; it still reads "start a new gap analysis" |
| 23 | D9.5 "who = A9's mapper" (a frontend TS function) | `app/services/agent_names.py`, the Python twin of `lib/agent-name.ts`, pinned by `tests/test_agent_names.py`, which runs the TypeScript under node's type stripping over the same names (skips if node cannot strip types) | Cross-boundary mirror gets a contract test, not a copy nobody checks |
| 23 | D9.5 "Added to {resume display name}" | Base: display name, else the slug's words title-cased (`base_resume_data.resume_label`, shared with the version summaries); application: "a tailored resume" (its key is an id) | Never a slug on screen |
| 23 (scope) | D9.6 names `kb_import.py:240`, `routers/career_kb.py:822` | Also `routers/base_resumes.py::_parse_resume_upload` (the same raw `str(exc)` class on the New base resume › Import path): "{file} isn't a resume in the Maestro CS JSON format.", `plain_read_error` for the rest, "This file is over 10 MB." | Same sentence for the same failure on both import paths |
| 23 (scope) | Not in D9 | `resume_lint` label fallback "Custom section" → "Other section"; degree warning articles agree ("an associate's") | Glossary; grammar found while rewriting the row |
| 23 (coordinator) | D9.4 layers:669 / engine:13 rewrites | Lane 7's first-read pass: the coverage warning fires when the RESUME shows under 25% of the job's skills, so it now says "Your resume shows only 1 of this job's 8 skills (13%)." (or "No skills were found in this job's description."); a years check with no readable job date says "We couldn't find readable job dates on your resume, so we can't count yours." instead of "about 0"; the stale reason is "the job details were refreshed". Fourth Task-23 commit `8402876e` | The old sentences were untrue |
| 22–23 | One commit per task (23 may be 2–3) | 22: `bab06f3a` + `049c1c7d` (the 320px fix found in the browser). 23: `a603bb5f` (D9.1 alone, as asked), `b52157f9`, `812a1b9c`, `8402876e` (coordinator follow-up) | D9.1 had to land first on its own; later findings got their own commits rather than amends |

**Rows dropped (with reason):** none of D8's or D9's change rows. Kept on purpose as D says: D8 "Kept on purpose" list; D9.4 `layers.py:700/:723` flag prefixes (routed on); D9.2 `health_zones` tier values; D9.4 `pdf_render.py:371-376` template-authoring errors; D9.5 `resume_versions.py:117`; D9.7 all.

## Gate results

| Task | Gate | Result |
|---|---|---|
| 22 | pins seen failing first | 99 panel tests failed on the old code after the D8.2 pin rewrite (list in the session), 0 after |
| 22 | extension tests | `test_extension_panel*.py` + `test_extension_guided_fill.py` 335 passed; all `test_extension_*.py` 958 passed |
| 22 | pending | `_PENDING_T22` 33 in 12 files → 0, block deleted; no T22 error-word or placeholder block existed |
| 22 | mutations | 17/17 killed (one survivor, the chip-class helper, got a positive assert and was killed; 2 ratchet re-injections killed; the 320px CSS rule killed) |
| 23 | D9.1 | `test_reworded_findings_keep_their_ids` (ids = hash of the old literal, and the issue differs), `test_a_finding_id_survives_its_issue_being_reworded` (reword every display text, ids hold); 8/8 mutations killed |
| 23 | new pins | `test_knockout_points_to_profile_autofill` + `test_knockout_messages_read_as_plain_sentences` (both failed on the old code), `test_placeholder_places_are_words_never_schema_paths`, `test_c2_says_the_claim_as_written_and_the_dates_in_whole_years`, `test_the_warning_is_a_plain_sentence_with_agreeing_articles`, `test_agent_names.py` (3), `test_server_words.py` (4), `test_a_failed_request_is_a_sentence_and_keeps_the_providers_words`, `test_a_skipped_file_is_reported_in_words`, `test_a_file_that_fails_for_a_developer_reason_is_reported_in_words`, `test_the_coverage_warning_says_what_it_measured`, `test_l4_gate_says_it_could_not_count_when_no_date_is_readable`, plus exact asserts added to 8 existing tests |
| 23 | mutations | commit 2: 13/13 (3 survivors pinned, then killed); commit 3: 16/16 (4 survivors pinned, then killed); coordinator follow-up 4/4 |
| all | full backend | `pytest tests/ mcp_server/tests/ -q`: 5336 passed, 3 skipped (Task 16: 5317 passed, 3 skipped); `test_frontend_*.py` 950; `ruff check .` clean |
| all | frontend | `tsc --noEmit` clean; lint 0 errors, 2 warnings; `node --test lib/*.test.ts` 230; `npm run build` OK (run last) |
| all | slop, clean `git archive HEAD` | frontend dup 437 lines / 36 clones; backend `complexity_hotspots` 424 (≤ 424; two new hotspots split: `set_card_state`, `agent_display_name`), backend dup 404/44 (402/44 at the branch point); extension 0 hotspots, 0 clones, 7 allowlisted (unchanged); `slop_scan.py check` backend, extension, frontend all OK |
| 22 | real Chrome | Chrome for Testing (Playwright's chromium-1243), the unpacked extension, the REAL side panel (opened with a trusted click on `sidePanel.open`, driven over CDP), backend 8874, made-up postings on 8875, 320/360/400px, light and dark: "Saved" chip, empty ring "ATS score" over "not scored yet", "Score base resumes", "Use base resume as is | Tailor", "Quick tailor | Tailor in Maestro CS ↗" + its sentence, "Skipped. Using your base resume as is.", Fill stage "Saved answers only | Saved answers + AI" and both mode sentences, "Fill this form", "Draft application" chip beside Draft/Applied, "Applied" chip + "Marked applied." after pressing Applied, backend down: "Couldn't reach Maestro CS. Check that it's running." and "Job description found (36 words)", no horizontal overflow at any width. At 320 with the Draft/Applied segment, "Score base resumes" wraps to two even lines |
| 23 | web (3274/8874) | Health report (light and dark, 1280/375): the C2 ask reads "Your summary says 10+ years, but your dates add up to about 4."; a saved answer stored under the finding's PRE-lane id rehydrates when the row opens; knock-out card "… Answer the sponsorship questions in Profile › Autofill." with no "in Settings"; Score tab of a never-read job: "This job's description hasn't been read yet. Choose Refresh details on the job page."; health run without a key: "No API key is set. Add one in Settings › AI & models › API keys. …" |

## Queued for Task 24 (SYSTEM.md changes Claude applies)

- §7 Chrome extension and Guided fill (SYSTEM.md:574, :605): the Fill primary is **Fill this form** (was "Start fill"); the footer primaries are Save job, Score base resumes, Quick tailor, Fill this form. A failed panel round trip never prints raw text: `actions/during.js`' `failureNote` ("Couldn't <what>." + next step by `err.status`), `guidedRun.shown` for the panel's own sentences.
- §7 or §12: `LLMProviderError` — `str()` is the user's sentence, `provider_detail` the provider's words; anything that classifies a provider failure by its text (the capability probe) reads `provider_detail`. §12 (≤3 lines): "2026-09-24: a user sentence replaced the provider text a probe matched on → classify on `provider_detail`, never `str(exc)`."
- §12 (D11 already queues it): "2026-09-24: rewording a health `issue` silently orphans saved ask answers → `_fid` hashes the text → pass `id_key`; the frozen keys live beside the text (`resume_lint.py`)."
- §7 (agent surfaces): `app/services/agent_names.py` is the server twin of `lib/agent-name.ts`, pinned by `tests/test_agent_names.py`; add a known client to BOTH.
- D11 docs lane (not SYSTEM.md): `extension/README.md:12` ("as-is"), `:113` ("Start fill"); `extension/INTERNALS.md:33, :66, :71, :101, :121, :128, :133, :136, :139, :152, :155-156, :226, :469` quote the old panel labels (Add job, Score all bases, Start fill, Rules only / Rules + AI assist, Custom in Studio ↗, "Skipped — using base as-is").

## Deferred to merge (edits left for Claude, with file:line)

- `backend/app/routers/proposals.py:111` (company blocklist 409) names "your Companies to skip list in Settings › Connected agents": that label is lane 9's rename of `frontend/components/settings/auto-apply-section.tsx:162` ("Company blocklist" → "Companies to skip", D6.2). Check both landed.
- `frontend/lib/types.ts:1317` doc comment says `coverage_warning` means "the engine recognised too little of the posting": it now measures how few of the job's skills the resume shows (`backend/app/services/ats/engine.py`, `_coverage_message`).
- `frontend/app/jobs/[id]/tailor/[sessionId]/page.tsx:695` composes "This analysis is out of date: {staleReason} since it was created." The server's reasons are now "the base resume was deleted", "the base resume was edited", "the job was deleted", "the job details were refreshed" (lane 7, D3, may reword the frame).
- `frontend/lib/health-report.test.ts:81-95, 119, 175, 255-261, 318-334, 344` and `backend/mcp_server/tests/test_workflow.py:49-52, 126` still carry the old backend strings as fixtures (they pass; optional refresh, D9.8).
- The health report's gate rail shows the gate `label` the server stored: reports computed before this lane keep "Parse fidelity" etc. until Check again (D9 intro: the frontend may map by gate `id`, lane 8's D4.5).
