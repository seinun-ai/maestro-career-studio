# UX IA and copy, wave 3 lane 8: copy-resumes — handoff to a Claude Opus 5.5 subagent

**Tasks:** Tasks 19 and 20 of `docs/plans/2026-09-23-ux-ia-copy.md`.
**Branch:** `claude/ux-ia-lane8-copy-resumes` (from `claude/ux-ia-copy-plan` at the commit that added this doc; waves 1–2 and Task 16 are merged into it).
**Worktree:** `/Users/ajeyds/Projects/maestro-ux-ia/lane8-copy-resumes`. Work only there.
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
4. D §4 (resumes, studios, health, templates; D's lanes L3a and L3b) and D §5 (Career history; D's lane L4) in `docs/plans/2026-09-23-ux-ia-appendix-d-copy.md`, plus D §0 (glossary), D §1 (rules and shared primitives, landed in Task 16 as `lib/error-text.ts`: use `couldnt()` / `errorDetail()` for every error you rewrite), D §10 (the real bugs in your groups — fix each with its pin) and the lane docs of waves 1–2 (`docs/plans/2026-09-23-ux-ia-lane{1..6}-*.md`, *Deferred to merge* notes that name your files). D's line numbers are at `8cac7cf9`; waves 1–2 and Task 16 moved code, so re-locate by the quoted text and SKIP rows whose string no longer exists (log them).
5. Career history: records are items, their lines are **bullets** (owner decision 13 — NOT "points"); the Career KB page, sidebar item and "Sync to KB" pill become Career history. Do NOT change health finding TEXT that the server writes (Task 23 owns `resume_lint.py` etc. and D §9.1's stable ids); change only frontend strings.

## Your definition of done

- Every D row in your groups applied (or logged as dropped with a reason).
- Your ratchet pending blocks (`_PENDING_T19` and `_PENDING_T20`) in `backend/tests/test_frontend_vocabulary.py`, `test_frontend_error_words.py` and `test_frontend_placeholders.py` (there the blocks are named `_PENDING_EXAMPLES_T<n>`) driven to **zero and deleted** (the ratchets fail if a count is higher or lower than actual — lower each block as you go).
- Every pin that read an old string updated to the new one (D lists them per group); no pin weakened.

## Scope

**Files this lane owns:** D's lanes L3a, L3b and L4 in Appendix D *File ownership*, re-checked against the current tree. Shared test files: edit only your own pending blocks and your own pin functions.

**The other wave-3 lanes run at the same time** (7 copy-jobs, 8 copy-resumes, 9 copy-settings, 10 companion-server). Don't edit their files. `docs/frontend-conventions.md` is shared: edit only bullets D assigns to your groups, never reflow other text.

**Never touch:** `SYSTEM.md` (1000/1000; queue changes below), `.slop-baseline.json` files, `docs/ux/`, other worktrees and branches, and the main checkout `/Users/ajeyds/Projects/maestro-career-studio` (live `data/` and the live Docker stack on 3000/8001: never `cd` there, never `docker compose`). Never bare `git stash`. Don't push, rebase or merge.

## Environment

- Python `/opt/anaconda3/bin/python3`; pytest and ruff from `<worktree>/backend`. Frontend from `<worktree>/frontend` (`npm ci` has been run): `npx tsc --noEmit`, `npm run lint` (0 errors, 5 baseline warnings; React Compiler rules at error level), `node --test lib/*.test.ts`, `npm run build`.
- **Browser checks:** scratch dir `/tmp/maestro-ia-lane8`; backend from `<worktree>/backend`: `/opt/anaconda3/bin/python3 -m uvicorn app.main:app --port 8872` with `DATABASE_URL=sqlite:////tmp/maestro-ia-lane8/app.sqlite3`, every `*_DIR` setting from `backend/app/config.py` under the scratch dir, `ALLOWED_WEB_ORIGINS=http://127.0.0.1:3272,http://localhost:3272`, `PATH=/Library/TeX/texbin:$PATH`, no LLM keys; frontend `API_PROXY_BACKEND=http://127.0.0.1:8872 npx next dev -p 3272` (open `http://localhost:3272`; run `npm run predev` first if it exists and delete what it copies afterwards). Seed MADE-UP data through the API (earlier seed scripts to crib: `/tmp/maestro-sweep-a/`, `/tmp/maestro-sweep-b/`, `/tmp/maestro-fix-sweep/scripts/`). Python Playwright (`from playwright.sync_api import sync_playwright`, `channel="chrome"`), real keys and pointer, light and dark, 1280/768/375; screenshots under the scratch dir; tear the stack down afterwards.

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
| 19, 20 (rows dropped) | D4.2 :775 and D5 new-entity :424: the dialogs' "Close" → "Cancel" | Kept "Close" | Both dialogs keep the draft across close, and `test_frontend_dialog_drafts.py` pins "Close" with "Cancel" absent: Cancel would promise a discard that does not happen (never lose typed text; honest words) |
| 19, 20 (rows dropped) | D4.3 kb-import-drawer :194 tab "Basics" → "Summary and skills"; D5 app/career :106 "Basics" → "Profile" | Kept "Basics" on both | `test_frontend_analytics.py` pins one name for the one section on both screens and bans ">Profile<" there: "Profile" already names the /profile page (one word per thing) |
| 19 | D4.3 pdf-pages-preview "…then save again"; lib/render-note "Save again to retry." | "…Check your last change, then update the PDF." and "Update the PDF to try again." | Save is dirty-gated, so with nothing to save it is disabled; `test_frontend_studio.py` and the conventions' base-studio rule forbid "save again" (every sentence tells the truth) |
| 19 | editable-title.tsx fallback "Untitled resume" | `value \|\| baseResumeLabel(slug)` (the slug's words) | The gallery card names an unnamed resume the same way; two names for one resume on two screens (one word per thing). Allowed by `_BARE` as the fallback half of `\|\|` |
| 19 | project-port-dialog description "It's added hidden, so you can check it before showing it." (the title says the rest) | "**{project}** is added hidden, so you can check it before showing it." | The title no longer names the project, so the sentence does (plain words) |
| 19 | D4.3 "Some fields need fixing: {section words}" from `describe-edit`'s section words | New pure helpers `describeFieldPath` / `fieldsNeedFixing` in `lib/describe-edit.ts` (node test + pytest pin); places joined as sentences, at most three, "And N more" | The existing section words cover only three sections; a path must never reach the screen, and two studios share the helper (logic in two places goes through one helper) |
| 19 | health `toastRewriteError` → `couldnt("apply the change")` | It takes a `what` (default "apply the change"); the three draft paths pass "write new wording" | A failed draft said "Couldn't apply the change" (every sentence tells the truth) |
| 19 | (not in D) | `lib/resume-schema.ts` TITLE_COLLISION_MESSAGE changed per D, the backend twin left (lane 10's file) | See *Deferred to merge* |
| 19 | (duplication gate) | `HiddenBadge` and `BulletsRead` in `editor-scaffold.tsx`, `Field` reused in `project-editor.tsx` (its `ProjField` deleted) | The copy made three read cards and the hinted Link field identical: duplication went 437/36 → 465/39 until they shared one component (now 390/35) |
| 20 | new-entity-dialog title label "Job title" for every non-extra kind; org label "Organization" | Per kind: Job title, Project name, Degree, Certification, Heading; org: Organization, School (education), Issued by (certification, other section) | "Job title" misnames a degree, and the glossary says School, never Institution |
| 20 | merge dialog "Combine {source} with another {kind}." / "…another {kind} that isn't archived." | "…another {kind} item." / "…another {kind} item that isn't archived." | For an other section the kind is the section's title ("another Awards" read wrong) |
| 20 | kb-sync-pill toast "Added {n} new bullets to your career history. Review drafts" | The same, plus "Noted N wording changes." and "Added N skills." when nonzero | The sync also files drift notes and skills; saying only bullets under-reports what changed (honesty) |
| 20 | D5.2 check 5 expects the capture toast "Added to {title}. 2 bullets to review." | Followed D5's row :37: "2 draft bullets added to {title}" (the document toast reads "Added to {title}. N bullets to review.") | D's row and its browser check disagree; the row names the drafts it made |
| 20 | (not in D) | One table for item kinds and statuses, `components/career/career-labels.ts`, read by five surfaces; `kbStatusLabel` never prints a stored key | Five files each carried the kind map, one printed `entity.status` raw (logic in two places goes through one helper) |
| 20 | (ratchet) | Removed the vocabulary `_ALLOWED` row (documents-panel, "KB"): it was only satisfied by "Career KB"; the kilobyte " KB" chunk is not prose | `test_allowlist_is_current` fails a stale row; the list only shrinks |
| 19, 20 (other lanes' pin files) | Edit only my pins | Updated the rows that read my strings: `test_frontend_color_roles.py` (picker aria-label, the engine chip gone from the gallery), `test_frontend_agent_words.py` (instruct-sheet present string), `test_frontend_query_error_states.py` (my rows, plus version-history-sheet's new failure branch) | Every pin that read an old string follows the new one; none weakened |
| review | (review and first-read of `e7e6a12a`) | Fixed per the fix list; each row below is a deviation from the reviewer's or first reader's words, or a plan defect | |
| review (plan defect, D4.4) | D's "Has errors. Open to fix." on every draft template with a `last_error` | Shown only when `templateHasErrors` (`lib/template-status.ts`): `REQUIRES_TEX_REASON` (pinned equal to `template_validation.REQUIRES_TEX`) is Needs setup alone; the editor says "This template needs TeX…" instead of "The template has an error" | A LaTeX draft on a computer without TeX has nothing to fix (review C1) |
| review (plan defect, D4.4) | D's Needs setup tooltip "Resumes using it use a similar template for now." | "…Until it is, resumes that use it are made with another ready template that doesn't need TeX." | `pdf_render.resolve_render_template` takes the first ready Typst template, not a similar one; none, no PDF |
| review (plan defect, D4.3) | D's "Score limited to {n} by one must-fix problem" for any cap, and "N must fix" from the server's `counts.gate` | `scoreCompositionLine(score, breakdown, gates)` names the count and tier; `healthCounts` counts `gate` = failed fatal only, `serious` separately, everywhere (chips, studio link, "left to fix" = checks + fixes + questions); the checks group is "Checks" (report and Review changes) | `gate_cap_tier`: one serious check caps at 69 and is not a must-fix; `counts.gate` counts serious checks too (planner decision) |
| review (plan defect, D5.1) | D's pill toast "Added {n} new bullets…" and title "Not yet in your career history" | `syncResultSentence` words draft bullets, items, skills and noted rewordings; the server returns a new additive `items_added` (`kb_base_sync.apply`, `SyncResult`); title "Ready to add to your career history"; breakdown lines per section ("6 experience bullets") add up to the pill | An education/certification add writes an item, no bullet (`entity_only`): "Added 0 new bullets" (review I1, I2) |
| review (plan defect, D5.3) | D's document toast "Document added. New bullets are ready to review." and chip failed → "Couldn't read" | `lib/document-words.ts`: counted drafts from this document (refetched item), "Couldn't suggest bullets" when text was read (new additive `KBDocumentOut.has_text`, a model property) | `ingest_status` "failed" covers an unreadable file and a failed suggestion step (no model key) (review I8) |
| review (plan defect, D5.2) | D's provenance "You wrote it" and "Not confirmed" | "From your own material", "You couldn't confirm this"; manual + "You said it" shows once; an agent's bullet "From Claude" (`agentDisplayName`); the hover by-line pin stays | Document- and resume-drafted bullets carry `user_authored` (review minor) |
| review (plan defect, D4.8) | D's base delete "This deletes the resume and its PDF." | "This removes the resume from your base resumes. You can't undo this." and no archive advice for an archived one | A soft delete; its files stay (`delete_base_resume`); nothing restores it |
| review | First read: "Counts more" → "Bigger effect" | "Higher priority" | The zone sets severity and the fix-list order; `health_score` never weights by zone, so "Bigger effect" claims a score effect that doesn't exist |
| review | First read: "Entries with dates" / "Simple list" | "Items with dates" / "Simple list" (one table, `SECTION_TYPE_LABELS`, read by Add item and the resume editor) | The glossary says item, never entry (vocabulary ratchet) |
| review | First read: "Copy resume ID" → "Copy resume name" | "Copy ID for connected agents"; toast "ID copied. Connected agents find this resume by it." | It copies the slug, not the name (verified) |
| review | Reviewer I5: usage chip | "On N resumes", "Still on N resumes" for a retired bullet; the hover names a tailored resume "Tailored resume for {title} at {company}" (`components/career/use-resume-key-label.ts`, the tracker's own query) | Usage rows store an application's id; it was humanized into "E4b214c9 B123" |
| review | First read: "From career history counts only approved bullets" | New base resume counts `point_count - draft_count` | Not exact: the list endpoint has no approved count and `services/career_kb.py` is lane 10's (see Deferred to merge) |
| review | First read: "Answer the number questions (2)" | "Add numbers to 2 bullets" on the button and the dialog title (`addNumbersLabel`) | |
| review | Reviewer 11/12 lists | Also guarded and focus-kept: Apply suggestion, Restore (a version), Check template; a status-chip menu no longer disables its trigger natively; Approve all hands focus to the panel | Same bug class, same files (one request per click; focus never to body) |
| review | Item 13 (health rows) | Also `/career` at 375: an auto grid track grew to 317px in a 271px column (scrollWidth 397, pre-existing); `grid-cols-[minmax(0,1fr)]` and wrapping capture buttons | No horizontal scroll at 375 |
| review | Item 15 "Role: AI/ML Engineer" slash | Not changed: the label is the server's (`ats/data/role_categories.yaml`) | Server words: lane 10 / Task 23 (Deferred to merge) |
| review | Item 15 "carries no number" | Not changed: `resume_lint.py:66` finding text (server) | Task 23 owns finding text (Deferred to merge) |
| review | Item 15 AI chip | Hidden when attribution is unknown (`provenance === "llm"`, the server's default for any change it can't match) | `resume_diff.attribute` labels unattributed changes "llm" (Deferred to merge) |

## Gate results

| Task | Gate | Result |
|---|---|---|
| 19 | new pins seen failing | `test_frontend_plain_words.py`: 5 new pins all FAIL against HEAD `787c81a1`, pass after |
| 19 | mutation checks | 8 on the new pins (bullet label, summary hint, both undo claims, failed-save paths, describeFieldPath ordinal, count nouns ×2): each killed by exactly its pin. 10 on changed pins (empty-preview words, metric labels, experience hint, template short name, version-history failure branch, "Too little to grade", Needs setup contrast label, New base resume placeholder, the entry-card pencil ref, code-edits confirm): each killed by its pin |
| 19 | ratchets | vocabulary, error-words, placeholders: T19 blocks 128/46/17 → 0, deleted |
| 20 | new pins seen failing | 5 new pins all FAIL against HEAD `ae184c99`, pass after |
| 20 | mutation checks | 7 on the new pins (Independent line, Metric plural, Add files, merge kind word, kbStatusLabel fallback, drawer status, pill label): each killed by exactly its pin. 7 on changed pins (Add now, Add to drafts, Nothing to review, item dialog placeholder, item date hint, notes hint, Unknown source): each killed by its pin |
| 20 | ratchets | T20 blocks 85/32/17 → 0, deleted |
| both | `test_frontend_*.py` + `test_kb_sync_frontend.py` | 976 passed |
| both | full backend `pytest tests/ mcp_server/tests/ -q` | 5328 passed, 3 skipped (baseline at Task 16: 5317 passed, 3 skipped) |
| both | `ruff check .` | All checks passed |
| both | `npx tsc --noEmit` | clean |
| both | `npm run lint` | 0 errors, 2 warnings (the 2 at Task 16) |
| both | `node --test lib/*.test.ts` | 231 passed (230 at Task 16, +1 describeFieldPath) |
| both | `npm run build` | OK |
| both | slop, clean `git archive HEAD` at `e7e6a12a` | frontend duplication 390 lines / 35 clones (ceiling 437/36); backend complexity_hotspots 424 (ceiling 424); `slop_scan.py check frontend` OK, `check backend` OK |
| 19 | browser (D4.10), scratch stack 8872/3272, made-up seed | 1280 light+dark, 375 dark: list title/subtitle, switch named by its label, delete dialog names the resume; studio ⋯ has Add from career history…, Version history, Copy resume ID, Update PDF, Edit as code (advanced); "Bullet 2 of 5", "Move bullet 2 up", "Delete bullet 2"; start-date hint, no placeholder; Hidden badge, "1 shown · 1 hidden"; Bullet style hint, Dot and Dash named; Item spacing, Spacing and margins; tailored Start over names Version history, and after an edit + Start over, Version 2 is listed and restorable (the claim is true); health: Health report, Check again, tier "Experienced", Must fix card, Fixes/Questions/Notes, "1 must fix, 3 critical, 6 questions, 3 notes", Mark as OK → "(marked OK)" + Undo → "Check turned back on", a number question with Number/Unit/Time period labels and no placeholder; templates gallery shows no LaTeX/Typst chip (only in names), editor tabs Formatting and Code, "Unsaved changes", Update preview → "Preview updated"; New base resume at 375 dark: four tabs named, the last scrolls into view, no page overflow. Script misses, each checked by hand: two menu counts raced the popup (a probe lists the items); a Start over over unchanged content records no new version, so the check re-ran after an edit; "LaTeX" and "Typst" appear only inside template names; the Update preview toast was read after it faded (re-read: "Preview updated") |
| 20 | browser (D5.2) | 1280 light+dark, 375 light+dark: title Career history, Add files and Add item, Quick capture label visible with no placeholder, Drafts to review; a no-org, no-date card has no second line and reads "1 bullet", "1 document"; Add files opens the dialog with Resumes and Other documents tabs (its title is lane 9's); capture toast (endpoint mocked); item page: Career history back link, Add to a resume, Bullets, "Status: Ongoing. Change status", origin "You", Stop using → Not used → Use again; send dialog "Add to a resume" with Add as is and Adapt and preview, in view at 375 dark; studio pill "Add to career history (14)", popover "Not yet in your career history", Open career history, Add now → "Added 6 new bullets to your career history. Added 5 skills. Review drafts", then "Career history up to date"; no page overflow at 375. 41/41 |
| review | new pins seen failing | `test_frontend_resume_review.py` (new): 47 of its first 59 FAIL against `8520f38f` (the 12 that passed are consequence sentences that were already true, then mutation-checked); new node tests in `template-status`, `kb-sync-words`, `document-words`, `describe-edit`, `health-report`, `formatting`, `studio` |
| review | mutation checks (`/tmp/maestro-ia-lane8/r2/mut.py`, backup-copy restore) | 51 mutants, 51 killed, each by the named pin: C1 ×4 (gallery guard, helper, editor branch, tooltip), I1, I2 ×4 (items dropped, "Added 0", backend `items_added`, raw toast), Add now unguarded, I3, I4, I5 ×3, I6 ×2, item 14 ×4 (raw path, "is missing", JSON line, unit preset), I7 ×7, I8 ×3 (incl. backend `has_text`), minor ×5 (archived delete, Subheading, Updating…, tailored name, agent name), item 15 ×3, item 11 ×3, item 12 ×3, item 13 ×2, M2, M24, M25. Three survived the first run (tailored name, gate land focus, row wrap) and their pins were tightened, then killed |
| review | `test_frontend_*.py` + `test_kb_sync_frontend.py` | 1056 passed |
| review | full backend `pytest tests/ mcp_server/tests/ -q` | 5409 passed, 3 skipped |
| review | `ruff check .`, `npx tsc --noEmit`, `npm run lint`, `node --test lib/*.test.ts`, `npm run build` | all passed; lint 0 errors, 2 warnings (the 2 baseline); node 246 passed; build OK (run last) |
| review | slop, clean `git archive HEAD` | frontend duplication 388 lines / 34 clones (ceiling 437/36); backend complexity_hotspots 424 (ceiling 424; the long copy pin split into five, two health pins, and one sync assert folded); `check frontend` and `check backend` OK |
| review | browser, scratch stack 8872/3272 (`/tmp/maestro-ia-lane8/r2`), made-up seed | Health (1280 light, dark): jordan_ml "1 serious problem", jordan_ds "1 must fix, 1 serious problem", "9 left to fix · Version N", jump list "Checks", h2 Checks, studio health link says the same counts; Mark as OK… → focus in the reason box; Mark as OK double click → 1 waive + 1 run, focus on Undo; Undo double click → 1 DELETE + 1 run, focus on Mark as OK…; Check again double click → 1 run, focus kept; Answer → focus in the number field; Review → focus in New wording; Apply double click → 1 PATCH, focus on "Applied"; 375: scrollWidth 375. Drafts: 6 alternating Approve/Discard double clicks → 1 request each, focus on the next draft's Approve, the last to the panel. Item page: Approve bullet double click → 1 PATCH, focus on Stop using; Stop using → "Won't be offered again", focus on Use again, hint "Stop offering this bullet. Resumes that have it keep it."; "Still on 2 resumes" with hover "Jordan ML Engineer, Tailored resume for ML Engineer at Quarry Labs"; "From Claude"; manual "You" once; documents "Couldn't suggest bullets" / "Couldn't read"; upload toast "Document added. Couldn't suggest bullets from it. Try Read again." Merge double click → 1 POST, focus on the surviving item's card. Studio: pill (16) = 7+1+1+1+1+5 lines under "Ready to add…", Add now double click → 1 POST, toast "Added 8 draft bullets, 6 items and 5 skills to your career history."; "Template: Classic (default)"; ⋯ "Copy ID for connected agents"; Add selected double click → 1 port, toast "Added 7 bullets from 1 item."; Restore → focus on the new Version row; Edit as code: "Couldn't apply: Contact, Email must be text. Experience, item 1, Company is missing. Fix them and choose Apply again." and "Couldn't read the code at line 3…". Tailored: Update score double click → 1 POST, focus kept; Start over text as pinned. Templates with `MAESTRO_CS_PDFLATEX=/nonexistent`: a LaTeX draft shows Draft + Needs setup only, a broken one also "Has errors. Open to fix."; the editor says "This template needs TeX…", Update preview double click → 1 validate, focus kept. Base list delete: archived resume without the archive sentence. New base resume (dark): each tab names what Create needs, `aria-describedby` wired. 375 dark: /career (after the fix), an item, a studio, templates, tailored, health all scrollWidth 375 |

## Queued for Task 24 (SYSTEM.md changes Claude applies)

- §5 step 9 (`:211-214`): "a `Sync to KB (N)` toolbar pill … its **Sync now**" → "an `Add to career history (N)` toolbar pill … its **Add now**"; "grown past the Career KB" → "grown past your career history".
- §5 step 7 (`:202-206`): the studio's words are Create PDF / Update PDF now (the job page's Resume tab is lane 7's; D11 queues the sentence).
- §11 item 30 (`:832-833`): cut "the base-résumé delete dialog names the slug, the KB inbox prints `resume_key`, the KB import drawer a raw `status`" (Task 19 and 20 fixed all three).
- §11 item 32 (`:844`): cut "the template editor's compile toast says "LaTeX error" for Typst too" (now "The template has an error. See the preview for details.").
- §11 item 31 (`:835`): the New base resume dialog's tab row scrolls at 375 (Task 9; confirmed here in dark mode) — cut that clause if Task 9 did not queue it.

## Deferred to merge (edits left for Claude, with file:line)

- `backend/app/schemas/resume.py:115-116` (lane 10's file): `TITLE_COLLISION_MESSAGE` should read "A section with this name already exists. Choose another name.", the words `frontend/lib/resume-schema.ts:86-88` now shows (the two are twins; `test_kb_extra_sections.py:112` imports the constant, so both sides move together).
- `frontend/components/setup/upload-dialog.tsx:160` (lane 9, D7.2 / D10.6): the dialog title "Add your documents" → "Add files", then add `"Add files"` as the dialog-title assert to `test_frontend_plain_words.py::test_add_files_names_what_it_opens` (this lane pins the button only).
- `docs/frontend-conventions.md`, lines this lane left because another lane edits the same line: `:644` "Add career item" → "Add item" (lane 7 renames "Extract job" on it); `:647` "the tailored studio's Build draft" → "Create draft"; `:817-818` "the tailored studio's Build draft and Rebuild" → "Create draft and Start over" (lane 7's "Extract" on `:817`); the sidebar bullet `:920-921` "Career KB" → "Career history", "Base Resumes" → "Base resumes" (lane 9's D7.1 code), and `:899` "(a studio under Base Resumes)".
- `backend/tests/test_frontend_plain_words.py`: lanes 7, 9 and 10 append to the same file end; keep every section.
- Server words still on these screens (Task 23, D9): the item timeline's "Entity created" (D9.5), a document's `ingest_summary` ("mint failed: No OpenAI API key configured…", printed as is in the Documents card, D9.4), and New base resume's parse warnings ("dropped N unparseable experience item(s)", joined after "Imported. Some parts need checking:").
- The sidebar still says Career KB, Base Resumes and New application (lane 9, D7.1).
- **Lane 8 review, server words or files owned elsewhere:** (a) `backend/app/services/career_kb.py` `entity_summary` (lane 10): add `approved_count` to `KBEntitySummary` so New base resume counts approved bullets exactly (it shows `point_count - draft_count`, which still counts Not used ones); (b) `ats/data/role_categories.yaml` labels such as "AI/ML Engineer" (a "/" meaning "or"); (c) `resume_lint.py:66` "Specific, but carries no number." → "…has no number" (Task 23); (d) `resume_diff.attribute` defaults an unmatched change to `"llm"`: the Review changes chip is hidden for it now; a real "unknown"/"base" value would let the chip return; (e) the server's version summaries "Ported 1 item(s) from Career KB" and the health placeholder detail "experience[1].bullet[1]" (lane 10 / Task 23); (f) a document's `ingest_summary` still prints the server's "mint failed: …" under the new chip (lane 10 rewrote it).
- `backend/tests/test_frontend_single_flight.py` `_SITES` and `test_frontend_color_roles.py` `_AMBER_LABELS`: this lane appended rows / renamed its own row; other lanes may touch the same lists.

## Not verified

- A real model: lint classification was seeded into the classification cache, and the capture endpoint, a failing gate and the "experienced" tier were mocked with Playwright routes; Adapt and preview was not run.
- Screen readers: names were read from Chrome's accessibility tree only. WebKit/Safari not run.
- 768px: not checked (D4.10/D5.2 ask for 1280 and 375).
- Review pass: the health report was produced in-process with made-up classifications and a stubbed verifier (`/tmp/maestro-ia-lane8/r2/lint.py`), routed in for POST `/run`; "Write new wording" and the ATS toast were not seen succeeding (no model key). The capped-score line was checked by node tests only (the seed's scores were never capped).
