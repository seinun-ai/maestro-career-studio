# UX IA and copy, wave 3 lane 7: copy-jobs — handoff to a Claude Opus 5.5 subagent

**Tasks:** Tasks 17 and 18 of `docs/plans/2026-09-23-ux-ia-copy.md`.
**Branch:** `claude/ux-ia-lane7-copy-jobs` (from `claude/ux-ia-copy-plan` at the commit that added this doc; waves 1–2 and Task 16 are merged into it).
**Worktree:** `/Users/ajeyds/Projects/maestro-ux-ia/lane7-copy-jobs`. Work only there.
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
4. D §2 (jobs and tracking; D's lane L1) and D §3 (gap page; D's lane L2) in `docs/plans/2026-09-23-ux-ia-appendix-d-copy.md`, plus D §0 (glossary), D §1 (rules and shared primitives, landed in Task 16 as `lib/error-text.ts`: use `couldnt()` / `errorDetail()` for every error you rewrite), D §10 (the real bugs in your groups — fix each with its pin) and the lane docs of waves 1–2 (`docs/plans/2026-09-23-ux-ia-lane{1..6}-*.md`, *Deferred to merge* notes that name your files). D's line numbers are at `8cac7cf9`; waves 1–2 and Task 16 moved code, so re-locate by the quoted text and SKIP rows whose string no longer exists (log them).
5. D §2.7's inbox words are mostly done by lane 5 (Queue, Applied, Found, lanes, chips; Deviation log) — do only what's left. The Autofill coverage Clear confirm must NOT reintroduce the "⋯ menu" sentence (Deviation log; lane 6 wrote the correct text).

## Your definition of done

- Every D row in your groups applied (or logged as dropped with a reason).
- Your ratchet pending blocks (`_PENDING_T17` and `_PENDING_T18`) in `backend/tests/test_frontend_vocabulary.py`, `test_frontend_error_words.py` and `test_frontend_placeholders.py` (there the blocks are named `_PENDING_EXAMPLES_T<n>`) driven to **zero and deleted** (the ratchets fail if a count is higher or lower than actual — lower each block as you go).
- Every pin that read an old string updated to the new one (D lists them per group); no pin weakened.

## Scope

**Files this lane owns:** D's lanes L1 and L2 in Appendix D *File ownership*, re-checked against the current tree. Shared test files: edit only your own pending blocks and your own pin functions.

**The other wave-3 lanes run at the same time** (7 copy-jobs, 8 copy-resumes, 9 copy-settings, 10 companion-server). Don't edit their files. `docs/frontend-conventions.md` is shared: edit only bullets D assigns to your groups, never reflow other text.

**Never touch:** `SYSTEM.md` (1000/1000; queue changes below), `.slop-baseline.json` files, `docs/ux/`, other worktrees and branches, and the main checkout `/Users/ajeyds/Projects/maestro-career-studio` (live `data/` and the live Docker stack on 3000/8001: never `cd` there, never `docker compose`). Never bare `git stash`. Don't push, rebase or merge.

## Environment

- Python `/opt/anaconda3/bin/python3`; pytest and ruff from `<worktree>/backend`. Frontend from `<worktree>/frontend` (`npm ci` has been run): `npx tsc --noEmit`, `npm run lint` (0 errors, 5 baseline warnings; React Compiler rules at error level), `node --test lib/*.test.ts`, `npm run build`.
- **Browser checks:** scratch dir `/tmp/maestro-ia-lane7`; backend from `<worktree>/backend`: `/opt/anaconda3/bin/python3 -m uvicorn app.main:app --port 8871` with `DATABASE_URL=sqlite:////tmp/maestro-ia-lane7/app.sqlite3`, every `*_DIR` setting from `backend/app/config.py` under the scratch dir, `ALLOWED_WEB_ORIGINS=http://127.0.0.1:3271,http://localhost:3271`, `PATH=/Library/TeX/texbin:$PATH`, no LLM keys; frontend `API_PROXY_BACKEND=http://127.0.0.1:8871 npx next dev -p 3271` (open `http://localhost:3271`; run `npm run predev` first if it exists and delete what it copies afterwards). Seed MADE-UP data through the API (earlier seed scripts to crib: `/tmp/maestro-sweep-a/`, `/tmp/maestro-sweep-b/`, `/tmp/maestro-fix-sweep/scripts/`). Python Playwright (`from playwright.sync_api import sync_playwright`, `channel="chrome"`), real keys and pointer, light and dark, 1280/768/375; screenshots under the scratch dir; tear the stack down afterwards.

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
| 17 | D2.9 autofill kinds: text, select and radio → Choice, checkbox, file, date | The real `ObservationKind` keys (`schemas/autofill_telemetry.py`): text → Text, textarea → Long text, select → Dropdown, radio → Multiple choice, checkbox → Checkbox, combobox → Searchable list, else Other | `file` and `date` are not kinds; the chart draws a bar per kind, so two kinds under one word read as a repeat |
| 17 | D2.9 coverage confirm/empty text with bare "Companion"; the confirm drops "including which sites" | "the Companion" in sentences; no ⋯ menu sentence (plan Deviation log); keeps "including which sites they were on and when" and "You can't undo this." | Planner decision 20 (Q8); consent: the sites count is the stake the comment names |
| 17 | D2.7 bulk toast `errorDetail(sample)`, fallback "already closed" | `sample` is a string, so `isPlainSentence(sample) ? sample : "Try again."`; the fallback row merges into it | errorDetail reads an Error; D9 (lane 10) makes the server details plain |
| 17 | D2.9 overview errors "Couldn't load this." | Named titles through `LoadErrorState` with Try again ("Couldn't load your activity." …), the failure branch before the skeleton; the same for base-summary-cards and gap-tiers-panel (raw sites in the Task 17 block) and top-skills/explore-overview (D rows). Pinned in `_FAILURE_BRANCHES` and `_LOADING_GATES` | Errors say what failed; a retry must not unmount the focused Try again |
| 17 | D2.3/D2.4 two `SUBSCORE_LABELS`, placement and fix-hint maps "in `lib/`" | One `lib/ats-words.ts` (+ node test, pytest pin): `SUBSCORE_LABELS`, `placementLabel`, `fixHintLabel` (plus the engine's `adjacent_available`, `credential_only`, which D missed), `requirementLabel` (tracker gap tiers and the gap card) | Logic in two places goes through one helper (dup 437→427 lines, 36→35 clones) |
| 17 | D2.7 cap line "Cap today {a}/{b}" | The pipeline card renders `<CapToday className=… />` (new `className` prop) | One implementation of the line and its spoken text |
| 17 | D2 rows only | Also, by the same rules: Q&A "Regenerated" → "New version ready"; the activity chart's legend and description say Applied, its tooltip date reads "Sep 14"; the Score tab's 422 "unscorable" text goes through `couldnt` (the ratchet cannot see `? err.message : null`); `ChartCard`'s error through `couldnt("load this chart", …)`; "Back to applications" on `/applications/[id]` | A toast names its object; one word per thing; never raw server text |
| 17 | Edit only my own pin functions | Updated one assertion each in other lanes' pins that read my strings: `test_frontend_sticky_lists.py` (Search jobs), `test_frontend_focus.py` (Edit referral; the status PATCH `onError`; a "# Save job" comment), `test_frontend_agent_inbox.py` (the bulk toast pin, renamed `…_says_queue`), `test_frontend_agent_words.py` (the four coverage-card rows) | Every pin that read an old string moves to the new one; none weakened |
| 17 | D1.1 f (sidebar bullet) | Only the tracker's two sentences (Add job); the FAB sentence and group names stay for Task 21 (`app-sidebar.tsx` is lane 9's) | Conventions change in the same commit as the code they describe |
| 18 | D3 `<Label optional>` "Where did you do this?" | A `Label` with an id naming a `role="group"` of chips, no `htmlFor` | The chips are the control; a label points at nothing else |
| 18 | "Start new analysis" button (no D row) | "Start new gap analysis" (conventions' autosave bullet too) | Glossary bans "analysis" alone; matches D9's server sentence |
| 18 | D3 gap-card :193 arrow → "to" | The add-keyword summary's "→ label" too | The arrow is read aloud |
| 18 | — | Browser-found at 375 (commit `7e6ec8e2`): the gap footer wraps (counts one line, actions below); the Resume tab's compare header wraps | "{a} done · {s} skipped · {o} open" squeezed into a column; the longer title ran one word per line (D3.2 check 6) |
| 18 | — | `test_the_gap_page_says_done_and_gap_analysis` split in two (commit `6a16fbc3`) | It reached cc 10: hotspots 425 against the 424 ceiling |
| review | D2.3 / D2.4 "Update scores" and "Update score" made one form | Kept both; the glossary now says the noun follows the count (Score and tailor scores every base resume, the compare card one) | One verb, true number; "Update score" on a button that scores five resumes undersells it |
| review | "Resume for this job" only when the draft came from the base | Always "Resume for this job" | The application carries no flag telling a from-base draft apart; the title is true for both |
| review | The ATS lead's planner sentence on every surface | Job surfaces use it verbatim (`ATS_SCORE_LEAD`); Analytics › Resume fit, which spans jobs, says "…would rate a resume for a job." (`ATS_SCORE_LEAD_ALL_JOBS`), above its first card; "ATS score over time" drops its second explanation | "for this job" is false on a page about every job; explained once per surface |
| review | Single-flight for Update scores, Create PDF, Find gaps and tailor, Use resume as is | Also Mark applied without tailoring (`appliedAsIs`), the same from-base POST that made two applications | One request per click |
| review | Focus hand-off for Skip, I can't confirm this, Undo | Also Edit (both rows), Done and the two library chips that apply directly: every control in `GapCard` that swaps its view | Focus never to `<body>` |
| review | Locations "California (4)", "Remote, US" | A state or province code reads by name; a country-only key reads "United States (no city)"; Countries by name (`lib/place-name.ts`) | The location key is state, else city, else country (`explore_overview`): it cannot tell a remote job from one with no city |
| review | Entry labels "Northwind Retail, Data Scientist (current)" | The comma, no "(current)" | The chip already shows its end date ("Present") and a Recent tag |
| review | Matched chips "Found in your skills list. Could also go in:" | "Mentioned in:" before the chips; the placement word ("Skills list only") stays | Plan defect: `evidence_entries` are the entries the engine FOUND the skill in (`ats/layers.py:49`, `:404`), not suggestions |
| review | Cap line "Applied in the last 24 hours: 0 of 10 allowed" | "Applications per day: 0 of 10 used in the last 24 hours", seen and spoken as one line (no sr-only twin) | A slot is reserved while an agent submits, not only once applied (`proposals.cap_status`); uses lane 9's setting name |
| review | OPT explained at first use | Overview's stat reads "OPT (US student work permit) accepted"; the Job market tile "OPT (US student work permit)"; the inbox chip "May not accept OPT" with the explanation as its title | The first place each surface shows it |
| review | Edit only my own pin functions | One assertion each in `test_frontend_agent_inbox.py` (cap line, empty-state sentence, the proposal date line), `test_frontend_first_run.py` (`runOnce();`), `test_frontend_qa_tab.py` (the Write a new version button); five `_SITES` rows in `test_frontend_single_flight.py` | Every pin that read an old string moves to the new one; none weakened |

## Plan defects found in review (Appendix D rewrites the code does not back)

Each was verified against the code named, fixed, and pinned (`test_frontend_jobs_honest_words.py`, `test_frontend_jobs_honest_analytics.py`).

| D row | D wrote | What the code does | Now |
|---|---|---|---|
| D §0, D2.3 `ats-score-panel.tsx:~416`, D2.9 analytics `:230` | "how an applicant tracking system rates a resume" | `services/ats` is the app's own engine: an estimate | Planner decision: "…is our estimate of how an applicant tracking system would rate each resume for this job." (glossary, `lib/ats-words.ts`) |
| D2 `job-knockout-card.tsx:21` | "You meet the listed requirements" / "…match what the job lists" | `clear` is any pass OR warning (`knockout.py:~243`); omitted checks are silent | "Nothing rules you out" / "Nothing the job lists conflicts with your profile." |
| D2 `job-knockout-card.tsx:35` | "No requirements listed … doesn't mention … pay or experience" | The salary and experience checks are OMITTED when the profile lacks a desired salary or years (`_salary_check`, `_experience_check`) | "Not checked yet: Can't check pay or experience yet: add your desired salary and years of experience to your profile." with a link per field; "Nothing here to check. That doesn't mean you qualify." only when nothing is listed |
| D3 tailor page:584 | "Fills every open gap from your Quick tailor settings" | The server fills only what the profile allows (a 400 when nothing) | "Fills the open gaps your Quick tailor settings allow, then tailors." |
| D3 tailor page:833 | "replaces this job's tailored resume and its PDF" | from-base deletes the stale PDF (`artifacts.remove_files`) | "…and removes its PDF. Version history keeps the old one." |
| D2 `ats-compare-panel.tsx:89` | absent → "Add it" | The skill is not on the resume; adding it is only honest if you have it | "Not on your resume" |
| D2 `ats-score-panel.tsx:40` | semantic_fit → "Overall match" | JD requirement lines covered by resume prose (`l6_semantic_fit_coverage`) | "Job duties covered" |
| D2 (lane's `lib/ats-words.ts`) | fix hints without `extra_only` | `_fix_hint` returns it (`layers.py:~231`) | "Show it in your experience"; a pytest reads every engine key |
| D2 `analytics-overview.tsx:100` | "Reached interviews" | `interview_rate` is applications CURRENTLY at interview or later (`explore_activity.py:19`) | "At interview or later" / "now, of {n} applications" |
| D2 `new/page.tsx:69`, `job-extraction-summary.tsx:52` | "You already saved this job." | Dedup also matches a job an agent saved | "This job is already saved." |
| D2 `explore-overview.tsx:211` | Level "As written in each job." | `level` is the extraction's category | "Sorted from each job description into one of these levels." |
| D2 `gap-tiers-panel.tsx:217` | quotes "Use the job description's wording" | Lane 9's switch is "…when your experience backs it up" | The full label |
| D2.7 agent pipeline `:68` (A2) | "Cap today {a}/{b}" | A rolling 24 hours (`cap_status`) | "Applications per day: {a} of {b} used in the last 24 hours" |
| D3 gap counts (lane's) | "{a} done" footer; category "{done} of {n}" (skips counted as done); Score tab "({resolutions_json.length} done)" | Stored resolutions include skips and gaps the analysis no longer lists | One helper, `lib/gap-counts.ts`: "{a} answered · {s} skipped · {o} open", badge "{o} open", Score tab "({a} answered)" |
| D2 locked tabs (lane's) | "Unlocks after you tailor a resume for this job" (tooltip only) | Use resume as is and Mark applied also create the application | A visible, true reason beside the tabs, and a panel on a direct `?tab=output`/`?tab=qa` link |
| D3 auto-fill banner | "filled in from your resumes and career history" | `wording_auto` fills from the job's own words | Names each source that applies |

## Gate results

| Task | Gate | Result |
|---|---|---|
| 17, 18 | ratchet pending blocks | Task 17: words 95 in 23 files, raw errors 45 in 18, placeholders 10 in 8 rows → 0, blocks deleted. Task 18: 47 in 3, 6 in 1, 5 in 4 → 0, blocks deleted |
| 17, 18 | pins seen failing first | new and changed pins run against the pre-change tree: 39 failures (Task 17 files), 8 (Task 18) |
| 17, 18 | mutation checks | 58 mutations, 58 killed (Task 17: 36; Task 18: 17; wraps: 2; the split: 3); restored from backups |
| all | `test_frontend_*.py` | 977 passed |
| all | full backend `pytest tests/ mcp_server/tests/ -q` | 5343 passed, 3 skipped |
| all | ruff / tsc / lint / node | clean / clean / 0 errors, 2 warnings / 239 passed |
| all | duplication (clean `git archive HEAD`) | 427 lines, 35 clones (ceiling 437 / 36) |
| all | backend hotspots / slop check frontend, backend | 424 (ceiling 424) / OK, OK (extension untouched, not scanned) |
| all | `npm run build` (last) | OK |
| all | browser (1280 and 375, light and dark) | 250 scripted checks pass (D2.11 1–6, D3.2 1–4, 6), plus the stale banner (D3.2 5) in light 1280 and dark 375; screenshots in `/tmp/maestro-ia-lane7/shots` |
| review | pins seen failing first | the two new pin files and the five `_SITES` rows run against `502eab3e`: 48 failures (the rest guard sentences that already held, and the engine keys) |
| review | mutation checks | 83 mutations over the new and tightened pins, 83 killed (`/tmp/maestro-ia-lane7/mut-review.json`); a first pass found 6 survivors, each fixed by a stricter pin; the gap-count split re-checked (4 of 4) |
| review | `test_frontend_*.py` | 1047 passed |
| review | full backend `pytest tests/ mcp_server/tests/ -q` | 5413 passed, 3 skipped |
| review | ruff / tsc / lint / node | clean / clean / 0 errors, 2 warnings / 251 passed |
| review | duplication (clean `git archive HEAD` at `a2e55ec6`) | 427 lines, 35 clones (ceiling 437 / 36) |
| review | backend hotspots / slop check frontend, backend | 424 (ceiling 424; `test_gap_counts_come_from_one_helper` reached cc 11 and was split) / OK, OK |
| review | `npm run build` (last) | OK |
| review | browser, 8871/3271 (`/tmp/maestro-ia-lane7/v2/verify.py`, `verify2.py`) | 60 of 60 checks, plus the Score tab and gap footer agreeing at "1 answered"; light and dark at 1280 and 375 for the job Overview, Score and tailor, gap page, a locked tab, Job market, Resume fit and the inbox with no horizontal scroll; screenshots in `/tmp/maestro-ia-lane7/shots2` |

## Queued for Task 24 (SYSTEM.md changes Claude applies)

- §11 item 30: cut "Job market's work-mode, OPT, sponsorship and level bars (`toBars` …)" and "the Analytics Employment and Level filters (`full_time`, `mid`)": both print words now (`toEnumBars`, `enumLabel`).
- §11 item 31: cut "the tailor page's "Tailor resume" run off-screen": the gap footer wraps at 375.
- §5 step 1: `/new` is "Add a job" and its submit Save job ("paste JD" → "paste a job description"). Step 3: the tab is Score and tailor. Step 4: "Analyze gaps & tailor" → "Find gaps and tailor". Step 5: "Use base resume as-is" → "Use resume as is". Step 7: "Generate PDF … (Regenerate refreshes it)" → "Create PDF … (Update PDF refreshes it)" (D11 queues it too).

## Queued for the owner

- **Naming: "Applications".** The page and its sidebar item list saved jobs and Agent inbox proposals too, while the glossary says a job becomes an application only when you tailor or apply. Rename both to "Jobs"? Not renamed here; the subtitle now also says "Jobs a connected agent found are under Agents."

## Deferred to merge (edits left for Claude, with file:line)

- `backend/tests/test_frontend_{vocabulary,error_words,placeholders}.py`: my blocks are deleted, so the `_BLOCKS = (…)` / `_EXAMPLE_BLOCKS` lines conflict with every lane's; keep only the blocks still present (the last lane deletes `_PENDING`).
- `backend/tests/test_frontend_plain_words.py`: my pins are appended at the end (a "Jobs and tracking" and a "gap page" section); other lanes append there too, keep both.
- `backend/tests/test_frontend_query_error_states.py`: my rows sit after `proposal-agent-panel.tsx` in `_FAILURE_BRANCHES` and after `ats-score-panel.tsx` in `_LOADING_GATES`.
- `docs/frontend-conventions.md` sidebar bullet (~:887-:919): "It is the one Add job per screen" and "tracker's ghost Add job" are mine; the FAB sentence ("New application is M3's extended FAB") and the groups line ("Career KB, Base Resumes") are Task 21's and Task 20's. Naming bullet (~:942-:970): "Not interested" and the add-a-job/inbox sentence appended. Also edited: the Q&A bullet (~:381-:389, Write cover letter), the single-flight bullets (~:643, :816, :837, Save job), the autosave bullet (~:1193, Not saved, Start new gap analysis), Derived setup guidance (~:1212-:1215), Analytics (~:1260, Skill gaps).
- `backend/tests/test_frontend_focus.py` (lane 8's): three one-line edits (:358 "Edit referral", :629 the status `onError`, :409 comment).
- Lane 9 (Task 21): the sidebar FAB still reads "New application" and the item "Career KB" (seen in every screenshot).
- Lane 10 (Task 23), server words still on my screens: the gap page's category descriptions and details ("JD skills with no evidence on the resume", "Resume title/headline does not directly match the JD title", "Refresh the summary as a JD-aligned value proposition", "JD asks for 3+ years; dated entries show 0.0", which the Score tab also shows as a gate badge), "Title & structure", the stale reasons, and the compare 422 and "unscorable" 422 sentences (those two go through `couldnt`, so they read "…Try again." until D9 makes them plain). The browser check filters exactly these lines.
- Review round, other lanes' pins with one assertion moved each: `test_frontend_agent_inbox.py` (`test_the_header_keeps_only_cap_today`, `test_an_empty_inbox_says_where_proposals_come_from`, `test_every_proposal_surface_names_who_filed_it`), `test_frontend_first_run.py` (`runOnce();`), `test_frontend_qa_tab.py` (`_regenerate_button`), and five rows at the end of `_SITES` in `test_frontend_single_flight.py`. My new pins are in two new files, `test_frontend_jobs_honest_{words,analytics}.py`, so nothing else conflicts.
- `docs/frontend-conventions.md` review round: the glossary's ATS score sentence (~:1066) and the Update score clause (~:1078).
- Lane 9: `cap-today.tsx` quotes lane 9's "Applications per day"; `gap-tiers-panel.tsx` quotes its switch label in full. Both are lane 9's words, so a later rename there moves these two.
- Lane 10 (server words), found in review: Job market's insight cards (`explore_overview.py:58-109`: "JDs", "Top location: US (5)", "Top required skill: python", "about 214k USD"), Skill gaps' category label "needs corroborating" (`explore_gaps.GAP_CATEGORY_LABELS`), and the knock-out rows' messages ("Posting requires …", "set your work authorization in Settings"). The frontend now cases skill names, names places and prints money one way; these server lines still don't.
- The gap page's segmented control wraps "Add keyword" onto two lines at 375 (pre-existing, not changed).
- Pre-existing, not changed: Base UI renders the tracker's "Add job" `<a>` with `role="button"` (lane 6 noted the same); a gap card's entry chip ("Harbor Loop Logistics — Senior ML Engin…") clips at 375.

## Not verified

- Save job against a real model: no LLM key in the stack, so `/new`'s save was checked with `POST /api/jobs` mocked (the toast, the summary) and the no-key state for real.
- 768px (checks ran at 1280 and 375), WebKit, a real screen reader (descriptions read from `aria-describedby`), Create PDF (no render was run).
- D3.2 check 3 used a routed network failure for the PATCH, not DevTools offline.
- Review round: the knock-out's "incomplete_profile" and "conflict" cards with the new unchecked line (no seeded profile answers; the unstated and clear cases ran for real), the stale banner (pinned, not re-run), the Q&A button (no Q&A entries seeded; pinned), 768px, and the double clicks with a real 1.2 s delay injected on the route rather than a slow backend.
