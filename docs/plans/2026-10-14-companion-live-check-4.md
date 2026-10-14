# Companion live check 4 fixes (Phase 2e) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Fix what the owner's fourth live check showed (a Workday tenant reached from the employer's own career site, 2026-10-14, fill log on):
- the run stayed on the career-site posting instead of opening the saved application link;
- it could not follow the user into the tab the career site opened ("Running in another tab");
- after a press that the page refused, the next page was pressed without being filled;
- a field the run filled by searching (Field of Study) parked as a question;
- several answerable questions had no route (veteran "currently or ever served", spouse's service, dealer, contractor);
- optional Skills boxes cost minutes;
- hand answers on a page-errors park were not learned.

**Architecture:** Run flow in `panel/actions/run.js`, `panel/actions/job.js`, `shared/queue-run.js`; reading in `content/page-reader.js`; answers in backend `autofill_map.py` / `autofill_catalog.py`. Test-first, made-up fixtures (Acme, `careers.acme.test`, `acme.wd1.myworkdayjobs.com`). No real company named in the repo.

**Owner decisions (2026-10-14):**
- Spouse or domestic partner's military service, no fact in the profile → **No** (or "I don't wish to answer" when offered), listed under "Check before you submit". Same treatment as relatives at the company.
- Skills sections are optional: a skills box that is not required stays empty in a run.
- A run moved to a new tab waits for one press ("Continue here"); it never resumes by itself.

Diagnosis notes are local only.

---

## Batch Q: run flow (extension)

### Q1: open the saved application link instead of staying on the posting
`openTab` keeps the tab only when it is not the job's saved posting, or the job has no separate `apply_url`: `stays = inPlace || samePosting(url, here) || (matched && !(applyUrl && !samePosting(applyUrl, here) && samePosting(sourceUrl, here)))`. Pass `sourceUrl` in the seed.
Tests: tab on `https://careers.acme.test/job/123` (the job's source) with `apply_url` on `acme.wd1.myworkdayjobs.com` → navigates to the apply link; tab already on `…/apply/applyManually` → stays; job with no `apply_url` on its posting → stays.

### Q2: a posting's Apply that opens a new tab is pressed in the same tab
`applyPressable` allows `target=_blank` for the Apply press only (the press already uses `location.assign`; the chooser keeps its stricter rule). A cross-host Apply is allowed when its href is the record's `openUrl` posting or its host is a known ATS host.
Tests: fixture `posting_blank_apply.html` on `careers.acme.test` with two `_blank` Apply links to `acme.wd1.myworkdayjobs.com/…/apply` → `applyId`, the press assigns the href, no new tab; a `_blank` Apply to a non-ATS host is refused.

### Q3: a parked run follows the user into the tab they opened
A record parked on a park that sends the user elsewhere (posting, chooser, unknown_page, sign_in_yourself, verify) moves to a new tab when the new tab's `openerTabId` is the record's tab, or the new tab's page matches the same job on the apply host or a known ATS host. The move rebinds `tabId`/`startTabId`, unvouches the old tab, adds the host, keeps the park; the card offers **Continue here** (= Resume). `prepareApply` offers "Move the run to this tab" instead of "Running in another tab" when the other record is parked on one of those parks (never while it is driving).
Tests: parked posting on tab 1 + new tab 2 (opener 1, Workday URL) → record on tab 2, still parked; Continue here drives tab 2. A filling/advancing record never moves. A new tab with no opener on another job → nothing moves. `prepareApply` with the other record parked on posting → move offer.

### Q4: never press a page the run did not fill
Remember `filledPage = {where, key, fieldSet}` at each fill. Before any press (and after every repair), if the current read is a different page, count it as moved (step + 1) and fill it first. A repair that wrote nothing (only stale upload boxes) is not "fixed": re-read and decide by the same rule. `fixPage` works the items it can map and parks naming only the rest; on a page never filled it runs a full fill.
Tests: step A filled → press refused, error list = one occupied upload → fix → next read is step B → fill on B before any press on B. A refused press whose re-read shows another step → fill, step + 1. `fixPage` with [mapped field, unknown] → fills the field, parks naming only the unknown.

### Q5: a field the run filled by searching does not park
In `openQuestions`, a required `needs_answer` whose last outcome landed a value (`group_committed`, `search_committed`, `committed_while_*`) does not park; it goes to `assumedRows` ("Searching picked "…". Check it."). An abstained field still parks.

### Q6: skip optional skills boxes in a run
A skills-type field (multiselect or tag box whose question names skills) that is not required is skipped in a run (status `skipped`, no `/step` calls). Required ones are filled as today.
Tests: optional skills multiselect → no step calls, `skipped`; required → filled.

### Q7: learn hand answers after any park
`afterTyping` runs for `page_errors` and `upload` parks too, over the record's open items with fids. Test: parked page_errors record with touched open fields → answers learned and a receipt posted.

### Q8: fill-log labels
Label blanking in the trace blanks a label only when the value is at least 4 characters and is not a common option word (Yes/No/Mobile/Home/Work/Other…), and matches as a whole token. Test: answer "Mobile" leaves "Have you worked for Acme-Mobile?" readable; an email value still blanks.

## Batch R: answers (backend)

### R1: veteran "currently or ever served"
`eeo.veteran_status` "no" answers "Do you currently or have you ever served in the U.S. Military?" with the never-served option. The protected-class guard stays (status categories, disability, etc.).
### R2: spouse or domestic partner's service → safe-default No (owner)
Add to the closed No list in the low-stakes template and `keen()`: a spouse's or household member's military service → No, or "I don't wish to answer" when offered.
### R3: dealer and contractor questions
`asks_worked_here_of_other` / the worked-here shapes cover "employed with an authorized dealer of <company>" and "worked as a contractor for <company>" → the history's No (reported assumed for the other-company path). A long "previously DIRECTLY employed with <X> AG or <Y>? (paycheck/W-2)" question reroutes reliably (not at p 0.63).
Tests: Acme job, Globex history: dealer → No; contractor → No; "DIRECTLY employed with Acme Holdings AG or Initech? (i.e. paycheck or W-2)" → No; veteran "no" with options [Yes / No, I have never served] → never served; long sponsorship text with H-1B/OPT/EAD/I-485 → derived sponsorship No.

## Batch S: docs and gate
INTERNALS Queued run (Q1–Q8), SYSTEM.md §7 (follow-the-tab, never press an unfilled page, safe defaults), CHANGELOG. Gate as before.

## Order and ownership
Batch Q (extension, one implementer, Q1 → Q8) and Batch R (backend, one implementer) run in parallel. Batch S after both pass review.
