# Companion live check 3 fixes (Phase 2d) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Fix what the owner's third live check (a Workday tenant, 2026-10-14) showed:
- the "Start Your Application" chooser stopped the run;
- an account that was created was reported as not created;
- "How did you hear about us?" failed again;
- a normal form step was called "maybe the last page", and was never filled;
- Resume on that page filled nothing;
- the error list ran two lines together;
- questions with no fact in the profile were left for the user even though a safe answer exists.

**Architecture:** Page-reading fixes go in `content/page-reader.js` and `shared/page-kind.js`. Run-flow fixes go in `shared/queue-run.js` and the card copy in `panel/runs.js`. Answer fixes go in backend `autofill_step.py`, `autofill_map.py` and `autofill_catalog.py`. Every task is test-first with made-up fixtures (Acme, Globex, Initech, `*.test`, `acme.wd1.myworkdayjobs.com`). No real tenant or employer is named in the repo.

**Owner decisions (2026-10-14):**
- **Safe default when the profile has no fact** (owner's words: "N/A, No, for most of the questions. And yes if it is for checking like 'Are you ready to do this?', 'Do you have this?'"):
  - a yes/no about a status, affiliation or circumstance the profile does not record and that would only add something (tribal, union or association membership, relatives or household at the company, a referral) → **No**, or **Not applicable** when offered;
  - willingness, readiness or consent to a standard pre-employment step (background check, drug test, reference check, I-9/E-Verify, providing documents) and basic means (reliable transportation, internet access) → **Yes**;
  - these answers are listed under "Check before you submit";
  - it applies from the "history" answer level up, like every low-stakes answer; "Facts only" stays strict.
- **Still never defaulted:** work authorization and sponsorship, age, EEO/voluntary self-identification (safe answer there is "decline", never No), criminal or background *history*, security clearance, salary, legal attestations and signatures, factual education or experience claims, and licences or certifications (a Yes there is a verifiable claim; coordinator call, the owner can overturn).
- **Skills sections are optional**: a skills box that is not required stays empty (already the rule; nothing new to build).
- **Unchanged:** Submit is never clicked; Next is pressed only in a run the user started; Apply is pressed only through a plain same-tab link; "Autofill with Resume" and "Use My Last Application" are never pressed.

Diagnosis notes are local only and not in the repo.

---

## Batch M: page reading and run flow (extension)

**Owns:** `content/page-reader.js`, `shared/page-kind.js`, `shared/queue-run.js`, `shared/ats-buttons.js` (or a sibling recorded-marker table), `panel/runs.js`, `panel/actions/run.js`, new fixtures under `backend/tests/fixtures/browser/`, extension tests.

### M1: a field's own control is never an action; the Workday footer decides

**Problem.** A Workday question popup carries the question in its aria-label ("…would you be willing to submit to a background check? Select One Required"). The reader sorts buttons by label, so the popup sorted as a Submit, and a page with a real Next read as "maybe the last page" (`several_next`).

**Fix.**
- In `summary()` and `submitSeen`, leave out of the Submit/Next sort: popup buttons (`aria-haspopup` listbox/true, the same rule `fillableControls` uses), pill members, and controls inside `[data-automation-id^="formField"]`, `fieldset` or `[role=group]`, unless `type=submit` or `submitMarked`.
- A visible, enabled `[data-automation-id="pageFooterNextButton"]` whose own text sorts as Next makes the page a `form_step`. If its text sorts as Submit, it stays a Submit.

**Tests.** Browser: footer "Save and Continue" + popup labelled "Acme runs a background check. Would you be willing to submit to one? Select One Required" → `form_step`. The same page with a real `<button>Submit application</button>` → review.

### M2: fill before judging; settle an unsure read; honest wording

**Problem.** The Application Questions page was never filled: the refill guard only fires when the pre-fill read counted no controls. Then one unsure read parked the run.

**Fix.**
- Refill guard: a fill that listed nothing while the page reports fillable controls gets one more fill (`listed === 0 && (summary.fillable ?? 0) > 0 && !refilled`).
- A review whose `by` is not `submit_button` must hold for `LONE_STABLE` reads before `unsure_page`. A page with required fields empty gets its fill or scoped fix before any unsure verdict.
- Card wording (`runs.js`): never "last page" while a real Next is visible. `several_next` gets its own line; `submit_seen` / `submit_context`: "This page may send the application…"; `fields_no_next`: "No Next button found…".

**Tests.** Driver: a page whose pre-fill read has `fillable: 3` and whose fill lists 0 → a second fill. A `fields_only` review flickering for 2 reads, then a step → no `unsure_page`. Card copy per `by`.

### M3: Resume on an unsure page still fills

**Problem.** Resume on a parked unsure page marked it filled and vouched, whatever it now read as, so nothing was answered.

**Fix.**
- Resume on an `unsure_page` park fills the page (the fill never overwrites an answered field). The vouch only feeds the Ready judgement.
- If the Resume read is a `form_step`, the vouch is void: fill, then press Next.
- Vouch only when the parked `lastBy` is `submit_seen`, `submit_context` or `fields_no_next`.

**Tests.** Driver: parked unsure record, Resume on a step with needs → one fill before any advance. A `submit_seen` review with needs → fill, then Ready with `readyBy: "user"`. The old "goes ready without a refill" test becomes "fills, then ready".

### M4: one error line, one name

**Problem.** Workday's error list puts the "Error - Q" button and "The field Q is required and must have a value." in one `li` with no space between them, so the name ran both together, was cut at 160 characters, and matched no field.

**Fix.** For each error line, prefer a descendant button or link whose own text starts with the error lead and read its linked control; else the first non-empty line of `innerText`. Match names per line or sentence, never across. If the lead name maps to nothing, try the X in "The field X is required". Compare long names after the same 160-character clip.

**Tests.** A `workday_errors` variant with the joined `li` → label without "The field", `kind: "field"`, an fid target. A question over 160 characters still maps.

### M5: account settle

**Problem.** After Create Account, the run re-read as soon as the button changed, while Workday still showed the sign-up form, and called it failed. Errorish text that was already on the page also counted as a fresh error.

**Fix.** Replace the single wait with a settle: poll every `POLL_MS` for up to about 20 s with the pre-press error keys as the baseline.
- Success: the page reads as anything other than `create_account` or `unknown`, or a Workday read where the Sign In header button is gone, fewer than two password boxes remain and there is a form step.
- `verify` / `captcha` → existing parks; `sign_in` → the existing one sign-in.
- Failure: still `create_account` with a fresh error held for `REJECT_HOLD_MS`, or still the sign-up form at the timeout.
- The "seen again" rule applies only to a later read after a settled success.

**Tests.** Driver: sign-up that lingers for two reads, then a step → ready path, one `createAccount`, no failed park. A fresh error that holds → `create_account_failed`. A standing error before the press, then the page moves → not failed. The existing "does not move" test stays failed.

### M6: the Workday chooser

**Problem.** "Start Your Application" offers three links (Autofill with Resume, Apply Manually, Use My Last Application). "Apply Manually" sorted as a Submit and the run stopped on "Page not recognised".

**Fix.**
- A recorded-marker row (beside `ats-buttons.js`) citing a new fixture `workday_chooser.html`, allowing exactly one link: host `(^|\.)myworkdayjobs\.com$`, `data-automation-id="applyManually"`, text exactly "Apply Manually", href path ending `/apply/applyManually`.
- `summary()` adds `chooserId` only when the page has no fillable controls, the one link matches the row, it is a plain same-tab http(s) link on the page's own host, and not submit-marked.
- `advance(id, {chooser: true})` → `pressChooser` re-checks everything and calls `location.assign(href)`; it never clicks.
- `page-kind`: `chooserId` and no fillable controls → `{kind: "chooser"}`, before the posting and Submit checks.
- `queue-run`: press it on the first read of a tab the run opened, or on the one read right after the run's own Apply press moved the page; only at step 0, not after sign-in, not on Resume, not in an in-place run, not once the record is filled. Otherwise park `chooser`: "Press Apply Manually in the tab, then Resume."

**Tests.** Browser (fixture routed on `https://acme.wd1.myworkdayjobs.com/...`): `chooserId` names Apply Manually; the press assigns its href; a forged id on Autofill with Resume refuses; an added input refuses; `target=_blank` refuses. Driver: posting → chooser → step → review presses Apply then the chooser; a chooser at step > 0, after sign-in, on Resume or in place parks `chooser` with no advance.

---

## Batch N: answers (backend)

**Owns:** `backend/app/services/autofill_step.py`, `autofill_map.py`, `autofill_catalog.py`, `autofill_pick.py` (only if `keen()` lives there), `routers/autofill.py` (read only unless needed), backend tests, `workday_source_search.html` fixture.

### N1: "How did you hear" searches the board first

**Problem.** The step goal hard-coded the category path ("website, online or job-board category… otherwise Other"). On this tenant LinkedIn sits under Social Media, the model could not back out of a wrong category, and the search card searched the saved words ("Job board").

**Fix.** In `step()`, before the model, for the how-heard slot with kind `board`: take the board name from the page's `source` hint matched against the known board names, else a board named in the saved value.
- A non-group option whose text equals the board → click it, `assumed`.
- Else, if a search move is offered and that board was not tried → search the board's name, traced as code's call.
- Else the model, with a rewritten goal: search the board's name first; else open the category most likely to hold it (job boards and social sites sit under names like Job Board, Online, Internet, Website, Social Media or Other); if it is not there, try the next.

**Tests.** `step()` with the model patched to raise: six groups + search, hint "linkedin" → search "LinkedIn"; next state with a "LinkedIn" leaf → click, `assumed`; board already tried and no leaf → model called; the goal no longer says `otherwise "Other"`. Browser fixture `workday_source_search.html`: LinkedIn under Social Media, found through search → filled.

### N2: the owner's safe-default rule

**Fix.**
- Narrow the protected sentinel's "background-check question" to background or criminal *history* (a record, a conviction, a pending charge), so willingness becomes a no-fact low-stakes candidate.
- Add the two owner kinds (No / Not applicable; Yes for willingness and basic means) to the low-stakes template and to `keen()`'s wording, both directions stated outright.
- Keep the never-list from the owner decisions above; add licences and certifications.
- Answers made this way are reported `inferred` (shown under "Check before you submit"). A tribal-membership question gets No; it is never inferred from EEO data, and an enrollment-number box stays blank.

**Tests.** `low_stakes_scope({})` text includes the willingness Yes and the No kinds; the never-list still names criminal history, salary, EEO, attestation, signature and licence; the sentinel no longer says "background-check question".

### N3: "Currently employed by <brand>" takes the history's No

**Problem.** The page names the brand, the job record holds the legal entity, so the worked-here reroute did not fire.

**Fix.** A worked-here-shaped question that names a company in neither the history nor the job record, with a derived "No" and no named-employer fact, takes the derived No.

**Tests.** "Are you currently employed by Initrode?" on an Acme job with a Globex history → `derived.previously_employed_here` "No". A question naming a history employer still answers from the history.

---

## Batch O: docs and gate

- INTERNALS "Queued run" and Known limits, SYSTEM.md §7, CHANGELOG (Unreleased). "A Workday tenant", Acme names only.
- Gate: backend suite with xdist, slop ratchet on `extension`, `npx tsc --noEmit` in `frontend/`, `check_system_md`, single alembic head.

## Order and ownership

Batch M (one implementer, M1 → M6 in order) and Batch N (one implementer, N1 → N3) run at the same time; their files do not overlap. Batch O after both pass review.
