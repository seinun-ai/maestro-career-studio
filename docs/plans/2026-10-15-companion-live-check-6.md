# Companion live check 6 fixes (Phase 2g) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Fix what the first live run with the reasoning step showed (a Workday tenant, 2026-10-15, fill log on): a Resume on Workday pressed unfilled steps; "How did you hear" never reached the step agent; a leftover upload line stopped the run after the page moved; an education threshold select had no route; sponsorship-type questions stayed empty; the reasoning note read like the model's plan.

**Architecture:** Run flow and reading in `content/page-reader.js`, `shared/queue-run.js`, `panel/actions/run.js`, `shared/sections.js`; fill engine in `shared/fill-loop.js` (+ `content/fill-ops.js` budgets); reasoning in `shared/reason-loop.js`, `panel/runs.js`, `backend/app/services/autofill_reason.py`; answers in `autofill_catalog.py`, `autofill_step.py`, `autofill_pick.py`, `routers/autofill.py`, jobs capture. Test-first; made-up fixtures (Acme, `acme.wd1.myworkdayjobs.com`).

**Owner decisions (2026-10-15):**
- "How did you hear": when the saved answer is generic ("Job board") and the job records no board, pick LinkedIn, or any specific job board the list offers, as an assumed answer listed under "Check before you submit".
- Sponsorship: use the saved No even when a question counts OPT or STEM OPT as sponsorship (no extra guard).

Diagnosis notes are local only.

---

## Batch V: run flow and reading (extension)

### V1: tell Workday steps apart
`stepHeading` prefers the step's own heading (inside the form or main region, or the progress list's `aria-current="step"`), skipping the error banner heading and a constant job-title header. A Resume after a park counts the parked page as matched only when the whole fingerprint (buttons + fillable count) also matches or the parked error items still exist; otherwise the page is filled. The pressed-only-if-filled guard uses the same comparison. `sections.js` skips the error-banner heading as a section name.
Tests: browser fixture with a constant job-title `<h2>` above each step's `<h2>` → keys differ; driver Resume after `page_errors` with same path + key but different fillable/buttons → fill before any press; sections never "Errors Found".

### V2: a refused press re-reads before parking
`repair` re-reads before parking; a fingerprint that differs from the pressed page counts as moved (step + 1, fill). `fixPage` treats an upload error whose box no longer exists as stale. A reasoning exit with no model call still posts a trace row (`stopped: no_read | wall`).
Tests: rejected press whose only error is a vanished upload box → fill of the new page; model-less exit → trace row.

### V3: tree questions go to the step agent
In `fill-loop.js` a single-value search choose that times out hands over to `adapt()` (history `choose -> timeout`), as the multi-value path already does. A how-heard field on popup/search shapes goes straight to `adapt()`. A search-shape choose gets a budget covering the explore settle (or reuses the list explore left open). Reasoning `retry` gains `step_by_step` (forces `adapt`); the backend allows it.
Tests: node fill-loop timeout → `/api/autofill/step` with `choose -> timeout`, no second choose; how-heard field → no generic choose; browser fixture `workday_source_search` Acme variant (Acme Website / Career Fair / Job Board / Other; Job Board opens a long list with LinkedIn below the fold; saved "Job board", no board hint) → assumed LinkedIn leaf.

### V4: the card speaks to the user
Parked without an ask: the card builds the sentence in code from the open items and outcomes ("It tried How Did You Hear About Us? a second way; it didn't take. Choose it in the page, then press Resume."). The model's note shows only on the live Thinking line and in the fill log. `triedOf` drops the leading verb and shows each outcome. The trace keeps the retry technique and the choose basis.
Tests: parked card with no ask shows the code sentence, not the model note; Tried line wording.

## Batch W: answers (backend)

### W1: board choice for "How did you hear"
`_board_move` / the how-heard goal: when the saved answer is generic ("Job board"/"job site"/similar) and no board is known, the board name is LinkedIn if the list offers it (search or leaf), else the first specific job board the list offers; reported `assumed` (owner decision). When a job is saved after visiting a known board page (e.g. Built In), store that board on the job so `board_of` uses it.
Tests: generic saved answer + no hint + LinkedIn leaf → click LinkedIn assumed; no LinkedIn → another named board assumed; stored referrer board feeds `board_of`.

### W2: education threshold
Derived fact `derived.education_level` from the degree level (`answer_flags.degree_level`), exact policy, described as the highest level completed with "X or higher" met by any level above X. Threshold options picked in code: the highest threshold met, never "None of the above"; abstain when none met.
Tests: Master's vs [Bachelor's degree or higher / Combination of relevant education, experience, and training / None of the above] → Bachelor's or higher; associate only → abstain.

### W3: sponsorship type
A "what type of sponsorship (now / in the future)" question with a false sponsorship fact picks the option meaning none / not applicable (code rule); abstains when there is none. Saved No is used even when a question counts OPT/STEM OPT as sponsorship (owner decision).
Tests: [H-1B, TN, Not applicable] with false fact → Not applicable; no such option → abstain; a true fact → never this rule.

### W4: the model's note is about the page, not its plan
Prompt: `note` is written to the applicant in the present tense and says what is wrong ("How Did You Hear About Us? is still empty."), never a plan; the checker-rejection fallback never turns a plan into the ask.
Tests: prompt text pins; rejection fallback uses the code note.

## Batch X: docs and gate
INTERNALS (V1–V4, W1–W4), SYSTEM.md §7, CHANGELOG. Gate as before.

## Order and ownership
Batch V (extension) and Batch W (backend) run in parallel; V3's `step_by_step` needs W's checker change — W adds `step_by_step` to the allowed retry techniques first thing. Batch X after both pass review.
