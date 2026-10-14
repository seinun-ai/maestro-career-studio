# Companion live-check fixes (Phase 2b) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Fix what the owner's first live Phase 2 runs (a Workday form and a second ATS, 2026-10-13) showed:
- a page's error is read and acted on;
- the resume is uploaded before Next;
- written history questions are answered;
- Apply shows what it is doing and lets the user choose the resume and stop between steps;
- tailored text is never written in third person.

**Architecture:** Fixes go into the existing modules and add no new subsystems:
- the queued-run driver (`extension/shared/queue-run.js`) and the page reader;
- the fill loop (`extension/shared/fill-loop.js`);
- the panel's Apply path (`extension/panel/actions/job.js`, `panel.js`);
- the backend routes and prompts.

Each task is test-first, and the tests press real buttons through the existing harnesses.

**Tech Stack:**
- Chrome MV3 extension (plain JS, node and Playwright test harnesses run from pytest);
- FastAPI + SQLAlchemy backend;
- Next.js settings UI.

**Owner decisions (2026-10-14):**
- **Worked here:** "Have you worked at X before?" answers **No** from the work history when the history lists jobs and none is at X. The answer is marked as from the work history. A match still answers Yes.
- **Veteran:** veteran status becomes **one Yes/No question** in the profile: "Are you a veteran?" (plus "I don't wish to answer").
- **Apply controls:** two switches in Settings › AI & models › Form filling:
  - "Choose the base resume for me" (default on), with a smart pick. A pick below the floor, or a lead below the margin, asks instead.
  - "Stop after each step" (default off).
  - A live checklist with Stop shows whichever way the switches are set.
- **Queue timing:** with "Stop after each step" on, the job is queued (the user's yes) at **Start filling**, not at the first press.

**Unchanged rules:**
- Submit is never clicked.
- Next is pressed only in a run the user started.
- Apply on a posting is pressed only through a plain same-tab link on the first read of a tab the run opened.
- The app repo is public, so tests use made-up names (Acme, Globex, `*.test`).

Diagnosis notes are in the session scratchpad: (local only, not in the repo).

---

## Batch A — the run reads the page (driver, page reader, upload)

### Task A1: a Next the page rejects is not a move; read the page's errors

**Problem:** Workday's "Errors Found" banner adds buttons. That changes the driver's page fingerprint, so `press` returns "moved" and `step += 1`. The card then showed "Filling page 3" on the same page, and each refill started from scratch. No error banner is read anywhere.

**Files:**
- `extension/content/page-reader.js`: new `page_errors` op, plus `summary().errors` as a count only.
- `extension/shared/queue-run.js`: `fingerprint` ~134–143, `press` ~247–251, `waitForChange` ~504–518, and the drive loop ~405–440.
- `extension/panel/actions/run.js`: new `fix` dependency.
- `extension/panel/runs.js`: copy for the new park.
- Messaging allow-lists, if the page op needs one: see `test_extension_page_messaging.py`.

**Behaviour:**
1. `page_errors` returns `{count, items: [{label, target, kind}]}`.
   - `label` is the page's own field wording. It is never a value.
   - It reads:
     - an error summary: `[role=alert]` or an `aria-live` region, or a list or region whose heading matches `/errors? found|please (fix|correct)|there (is|are) \d+ errors?/i`;
     - per-field errors: reuse `fillBase.invalid`, extended to upload boxes (the box's `aria-invalid`, an error node in its widget, or an error referenced by `aria-describedby`).
   - It strips a leading "Error - " and reduces "The field X is required…" to `X`.
2. Each error is mapped to a field, in this order:
   - the summary item's link (`href="#id"`, `aria-controls`, or the `for` of the label it names);
   - `aria-describedby`;
   - an exact, normalised label match against the field reader's question, for fill fields and for upload inputs.

   An error that matches no field keeps its label.
3. The fingerprint excludes buttons inside the error summary.
4. After a press, if the URL and step heading are unchanged and `errors > 0`, the outcome is **`rejected`**, carrying the errors. `rejected` never increments `step` and never adds to `seen`.
5. On `rejected`, the driver calls `deps.fix(record, errors)`. `fix` repairs **only** the named fields:
   - **Upload error:** attach the run's PDF to the named box. This uses Task A2's targeted attach.
   - **Field errors:** `runFill(..., {only: [fids], memory})`, from Task B1.

   It then presses Next once more.
6. If the same labels come back after one fix, or a named blocker cannot be fixed, the run parks with `why: "page_errors"` and `open` set to the error labels. The card says what the page asks for and names the fields. Other fields are never refilled.

**Tests:**
- New fixture `backend/tests/fixtures/browser/workday_errors.html`, with made-up employer Acme. It needs:
  - a footer `[data-automation-id=pageFooterNextButton]` "Save and Continue";
  - a skills multiselect preloaded with 15 pills;
  - an optional search box labelled Field of Study;
  - a required upload box labelled only "Upload a file (5MB max)", nested at least 7 levels below its section heading. The section text says "upload your resume and any additional documents";
  - Next with no file renders the "Errors Found" banner (a collapse button, and a button "Error - Upload a file (5MB max)"), sets `aria-invalid` and the "is required and must have a value" text, and keeps the step;
  - Next with a file present changes the heading.

  Add a fixture-fidelity entry for it.
- `backend/tests/browser/test_page_reader.py`:
  - `page_errors` maps the upload error to the file input, with kind `upload`;
  - a field error is mapped both by `aria-describedby` and by label;
  - `summary().errors == 1`.
- `backend/tests/test_extension_queue_run.py`:
  - a rejected press keeps `step` and `seen`, and calls `fix` with the errors;
  - the same labels after one fix park `page_errors` and name the upload;
  - the banner's buttons do not change the fingerprint.
- A panel-level test: the run card shows the `page_errors` park, naming the field.

### Task A2: the resume is attached before Next, and the card says so

**Problem:** The run's attach writes only when exactly one box classifies as `resume`. "Upload a file (5MB max)", under a deep heading, classified as unknown or other, and the skip was silent. Nothing gates Next on a required empty upload. "21 of 21" counted finished fields, not filled ones, and never counted uploads.

**Files:**
- `extension/panel/stages/fill.js`: attach ~924–970.
- `extension/content/agent.js`: `uploadBoxOf` ~286–299, `OTHER_DOC_WORDS` ~240, `SECTION_CLIMB`.
- `extension/shared/queue-run.js`: the gate before `advance`, ~410.
- `extension/panel/actions/run.js`: `fillPage` returns `report.attach = {outcome, reason, required}`.
- `extension/panel/runs.js`: the attach line, and the progress wording.

**Behaviour:**
1. A **required** upload box that is the page's only upload box counts as the resume box, unless its own label names another document (cover letter, transcript, portfolio, writing sample, other). The existing rules stay: never write over an occupied box, and re-check `resumeOnly` at write time.
2. A **targeted attach** (`attachTo(record, target)`) writes the run's PDF into a box an error named. This bypasses the "exactly one resume box" rule, because the page itself named the box. It still never writes into an occupied box or a box labelled for another document.
3. **Gate before Next:** if the page has a required upload box that is still empty after the fill, try the targeted attach. If that fails, park `why: "upload"` naming the box. Next is never pressed over a known-empty required upload.
4. The run card shows the attach outcome on the page line ("Resume attached", or "Couldn't attach the resume: …").
5. The page counter says "N of M answered" and counts only fields that ended filled, verified or kept. Upload boxes count as one field each.

**Tests:**
- `backend/tests/browser/test_upload_box.py`:
  - a lone required "Upload a file (5MB max)" box with a deep heading is attachable;
  - a lone box labelled "Cover letter" is not.
- `backend/tests/browser/test_attach.py`: the targeted attach puts the PDF in the named box (`__oracle.files`).
- `backend/tests/test_extension_queue_run.py`: a report with `attach.required && outcome !== "attached"` triggers the targeted attach, or parks `upload`, and never calls `advance`.
- A panel test: the card shows the attach line.

---

## Batch B — the fill loop keeps what it learnt

### Task B1: skip pills that are already there; give the fill loop `only` and per-record memory

**Files:** `extension/shared/fill-loop.js`: `runFill` ~426, `observe` ~1393–1440, `commitSet` ~1127–1260, `rows` ~469.

**Behaviour:**
1. In `commitSet`, before the explore at ~1188: if a normalised `f.committed` pill equals the item, mark it covered (`"matched"`) and go to the next item. `setAll`'s `holds` stays as the backstop.
2. New option `runFill(..., {only: [fids]})`. `observe` closes every field not in `only` before any map or explore, so no other field is touched.
3. New option `runFill(..., {memory})`: a per-record object keyed by the field's fingerprint (question plus kind, never a value). It carries `failedMoves`, `tried_terms` and the twice-cap counters across calls. The run record owns it (`run.js` passes `record.memory`). It is cleared when the step changes.

**Tests (`backend/tests/browser/test_fill_loop.py` and the node fill-loop tests):**
- 12 skills, 10 already present as pills: exactly 2 `fill_explore` calls, and the report is verified.
- `runFill({only: [fid]})` on the errors fixture sends no explore and no set to the skills box.
- Two `runFill` calls sharing `memory` send `search:value` for Field of Study at most twice in total.

**Interface for Task A1:** A1 calls `runFill` with `{only, memory}`. B1 owns `fill-loop.js`, and A1 must not edit it.

---

## Batch C — answers from the history (backend)

### Task C1: written history questions are written, not left blank

**Problem:** "Do you have experience with A/B testing… For how long and for which companies?" is a textarea. `/map` chose `YEARS_UNANSWERED` or `HISTORY_UNANSWERED`, which routes none, so the optional field was `left_blank`. The prose `/choose` path, which carries the career history, was never asked.

**Files:** `backend/app/services/autofill_map.py`: `_route` ~515, plus the sentinels.

**Behaviour:** a text-shape field (text, textarea, multiline) whose confident key is `YEARS_UNANSWERED` or `HISTORY_UNANSWERED` routes `free_text`. Choice fields keep today's route. The `/choose` prose rule against unsupported claims stays.

**Tests:**
- `backend/tests/test_autofill_map.py`: a textarea scripted `YEARS_UNANSWERED` routes `free_text`, while a radio with the same key routes as today.
- `backend/tests/browser/test_fill_loop.py`: an optional textarea routed `free_text` is written, not `left_blank`.

### Task C2: "Have you worked at X before?" answers No from the history

**Files:**
- `backend/app/services/autofill_catalog.py`: `_worked_here` ~399–414.
- `backend/app/services/autofill_map.py`: the `HISTORY_UNANSWERED` description ~84 and `NEVER_REASONED` ~183.
- The receipt and trace wording.

**Behaviour:**
1. When the career history lists at least one job, and no employer matches any company the question names, `derived.previously_employed_here` is "No". It is marked `inferred` ("from your work history") on the receipt and the trace.
2. A match still gives "Yes, previously".
3. With no jobs in the history, nothing changes: the question is asked.
4. A question naming several companies ("Acme, Globex, or Initech") is No only if none of them matches. Any match gives Yes.
5. Widen the `HISTORY_UNANSWERED` description so a "worked at named companies" question can reach the reasoned pass. Drop the worked-here clause from `NEVER_REASONED` only when the `WORKED_HERE` fact is absent.

**Tests (`backend/tests/test_autofill_catalog.py`, `test_autofill_map.py`):**
- No matching employer gives "No".
- A match gives "Yes, previously".
- An empty history leaves the question unanswered.
- With three companies named, one matching gives Yes.
- The receipt shows "from your work history".

### Task C3: veteran status is one Yes/No question

**Files:**
- `backend/app/services/autofill_catalog.py`: `eeo.veteran_status` values ~42 and description ~76.
- `frontend/components/settings/autofill-section.tsx`: the veteran control.
- An Alembic data migration (or a load-time mapping, if the profile is stored as JSON) for the stored value.
- Markets and setup-status code that lists the values.
- MCP `get_autofill_profile`, if it echoes the labels.

**Behaviour:**
1. Values become:
   - `no`: "No, I am not a veteran";
   - `yes`: "Yes, I am a veteran";
   - `decline`: "I don't wish to answer".

   The Settings question reads "Are you a veteran?".
2. The new description says:
   - a No also answers every "not a protected veteran" or "I am not a veteran" option exactly;
   - a Yes alone never says which protected class, so a classification question with a Yes is asked.
3. Stored values are mapped: `not_veteran` → `no`, `veteran` → `yes`, and `decline` stays.

**Tests:**
- `backend/tests/test_autofill_pick.py`: with `no`:
  - "I am not a Veteran." is picked at the exact floor;
  - "I am not a protected veteran" is picked;
  - with options "I am a Veteran, but not a Protected Veteran" / "I am not a Veteran.", the second is picked.
- With `yes`, a protected-class list is abstained (asked).
- A migration or load-mapping test.
- A settings-section test for the new question.

### Task C4: the trace names the sentinel

**Files:** the `DecisionTrace` builder in `autofill_map.py`.

**Behaviour:** the map trace step records which sentinel was chosen (its name, never a value). The trace allow-lists and the `fill_trace` script read it.

**Test:** a map trace for a `YEARS_UNANSWERED` choice carries the sentinel name.

---

## Batch D — tailoring voice (backend)

### Task D1: resume text is never third person

**Problem:** no rewrite prompt states the voice rule. They all say "the candidate", one-shot calls have no system message (for every provider), nothing checks the output, and a base summary already reads "Builds… which has shipped". Live applications contain "where he built".

**Files:**
- `backend/app/services/prompt_assembly.py`: `_skill_preamble`, which builds the VOICE line in code next to `_avoid_words_line`.
- `backend/app/prompts/`: `tailoring_skill.txt`, `gap_tailor.txt`, `resume_bullet_rewrite.txt`, `base_resume_instruct.txt`, `base_from_kb_plan.txt`, `kb_adapt.txt`, `chat_system.txt`.
- New `backend/app/services/resume_voice.py`.
- `backend/app/services/tailoring_session.py`: `_llm_customized` (the retry, like the keyword-survival retry ~1311) and the MCP `ops` path ~1403.
- `backend/app/services/health_guards.py`: the rewrite rejection.
- `backend/app/services/resume_lint.py`: the advisory.

**Behaviour:**
1. **The VOICE rule, in every rewrite prompt.** The text is the owner's own resume, written in implied first person:
   - lead with a verb;
   - no "I", "my", "he", "she", "they" or "his/her/their";
   - never the person's name.

   The code-built preamble line survives a customised `prompt.tailoring_skill` row. Reword "the candidate's X" to "the resume owner's X" where it frames the text being written.
2. **`third_person_hits(text, name)`** returns hits for:
   - third-person pronouns;
   - explicit "I" and "my";
   - the contact name's tokens, but not inside the company names on the resume;
   - "which has/built/shipped" after "Founder of…";
   - sentence openers that are third-person-singular verbs. This one is flagged, not rejected.

   It uses word boundaries, so "Heroku" and "other" are not hits.
3. **Tailoring:** a pronoun or name hit in the summary or a changed bullet triggers one retry, with a correction suffix. If the retry still fails, a deterministic repair drops or rewrites the clause ("where he built X" becomes "; built X"). A pronoun is never stored.
4. **Check wording** (`health_guards`) rejects a rewrite with a hit.
5. **MCP caller ops** containing a hit return 400, with a sentence telling the agent to write in implied first person.
6. **Health check advisory:** "This summary reads as written about someone else" for a base resume with hits.

**Tests:**
- `test_resume_voice.py`: a table of cases.
- `test_prompt_assembly.py`: the VOICE line survives a custom row, and appears in each listed prompt.
- A tailoring retry test, plus a test that a persistent failure is repaired and never stored.
- The ops path returns 400.
- The lint advisory appears.

---

## Batch E — Apply you can see and steer (panel and backend)

### Task E1: relink the open proposal to the job's newer draft; lock the resume list while Apply works

**Problem (second ATS):** Apply's first press auto-picked Business Analyst and linked that draft. The owner then tailored Data Scientist, and every later Apply tried to link the newer draft, so `/api/proposals` returned 409 "proposal already linked to an application", and kept doing so.

**Files:**
- `backend/app/routers/proposals.py`: `create_proposal` ~105–158, `_validate_and_stamp_application` ~196.
- `extension/panel/panel.js` and `stages/job.js`: the base list during `busy === "apply"`.

**Behaviour:**
1. A relink is allowed when all of these hold:
   - the request comes from the Companion (`is_companion(request)`);
   - the open proposal is `accepted`, with no approval or submit;
   - the new application exists, belongs to this job, and is a draft;
   - the currently linked application is gone or still a draft.

   The proposal's `application_id` then moves to the new draft, with a 200 response.
2. Every other mismatch is still 409.
3. `_validate_and_stamp_application` refuses an application of another job (409).
4. While Apply works, the base list is visibly locked (disabled radios, `aria-disabled`). A radio click during Apply is impossible, never silently ignored.

**Tests:**
- `test_proposals_router.py`:
  - the relink works;
  - it still returns 409 without the Companion origin, when the proposal is approved, when the old application is no longer a draft, and when the application belongs to another job.
- A panel test: the base radios are disabled during Apply.

### Task E2: a live checklist and Stop while Apply prepares

**Files:**
- `extension/panel/actions/job.js`: `prepareApply`, writing step state between awaits.
- `extension/panel/panel.js`: the store key, render, and Stop.
- `extension/panel/stages/job.js`: the checklist body.
- `extension/panel/panel.css`.

**Behaviour:**
1. Apply shows a checklist in the Job card. Each line shows a spinner while it runs, a tick when done, or a cross with a short reason:
   - Saving the job;
   - Scoring your resumes;
   - Using <base> (<score>), with the base's colour square;
   - Queueing the job;
   - Tailoring the resume (or "Using your tailored resume");
   - Making the PDF;
   - Linking the resume to the job;
   - Opening the application.

   Skipped lines are not shown. Once the run starts, the run card takes over.
2. **Stop** is shown during preparation. It stops at the next await boundary and never cancels a server call halfway. The checklist then says "Stopped after <step>". Anything already done stays done: a saved job stays saved, a tailored draft stays.
3. The lines are plain sentences and never include server text.

**Tests (`test_extension_panel_apply.py`):**
- The checklist lines appear in order with ticks.
- A skipped step is absent.
- Stop after scoring leaves no proposal and no tailoring.
- The base line shows the colour square.

### Task E3: "Choose the base resume for me" (with a smart pick) and "Stop after each step"

**Files:**
- Backend:
  - a new setting key `companion_apply` with `{auto_pick: true, stop_each_step: false}`, read in the same `/api/settings/...` call the panel makes on bind (or a new GET, if cleaner);
  - schema and route tests.
- Frontend: `frontend/components/settings/form-filling-section.tsx`, with the two switches beside the Screening answers dial and short help lines.
- Extension:
  - `panel.js`: `loadAutomation`, `cardFacts`, `renderFoot`, `loadBaseScores`/`scoreAllBases` (stop writing `baseSlug` when `auto_pick` is false);
  - `actions/job.js`: split `prepareApply` into stages;
  - `stages/job.js`: a one-line mode summary with a Settings link;
  - `shared/decisions.js`.

**Behaviour:**
1. **Auto-pick on (the default).** The panel picks the top score only when it is at least `auto_pick_floor` and leads the next by at least `auto_pick_margin`. These are the existing Auto-apply values; their label now says they apply to connected agents and the Companion. Otherwise Apply stops after scoring at "Pick a resume to apply with", with the list unlocked.
2. **Auto-pick off.** Nothing is preselected. After save and score, Apply waits for the user's pick. Before the job is saved, the footer reads **Save job**; then **Apply**, once a pick exists.
3. **Stop after each step on.** Apply becomes three presses, and the footer names the next one:
   - **Save job:** save and score, then pick (auto or yours);
   - **Tailor resume** (or **Make PDF**);
   - **Start filling:** queue (the user's yes moves here), claim, link, and run.

   Each stage is idempotent and re-reads server facts.
4. **Stop after each step off.** One press runs every stage, with the checklist from E2. Queueing stays at the start of Apply, as today.
5. The Job step shows the active mode in one line, with a link to the Settings card.

**Tests:**
- `test_extension_panel_apply.py`:
  - a close call (45 vs 44, both under 60) asks;
  - a clear lead picks;
  - with `auto_pick` off, nothing is preselected and Apply waits;
  - with step mode on, three presses happen and the queue is at the third (no `/api/proposals` call before Start filling);
  - with step mode off, behaviour is unchanged.
- The settings router test.
- The settings section test.

### Task E4: Track this counts as a pick

**Files:** `extension/panel/actions/track.js` ~177.

**Behaviour:** `trackThis` sets `claimFrom: "pick"`, so a just-tracked binding offers Apply right away. Today it only does so after a reload.

**Test:** after Track this, Apply shows without a reload.

---

## Batch F — docs and gate

### Task F1: docs

Update the following:
- `SYSTEM.md` §6 and §7. Keep it under its cap, and keep `check_system_md` passing.
- `extension/INTERNALS.md`: rejected Next, page errors, the upload gate, fill memory and `only`, the Apply checklist, the switches.
- `docs/entities/` where entities changed: the veteran values and the `companion_apply` setting.
- `CHANGELOG.md` [Unreleased]: veteran is now Yes/No (the stored value is mapped), and the new settings.
- The user guide, for the Settings switches.

### Task F2: gate

- The full backend suite with xdist.
- The extension and browser suites.
- The slop ratchet.
- `tsc` and lint.
- `check_system_md`.
- An Opus batch review per batch, and a final Opus review.

Then rebuild the wheel and update the live app (owner-approved flow). The owner's live check runs with **Options › Keep a fill log** ticked.

## Order and ownership

Batches A and B touch different files and can run in parallel:
- A owns `queue-run.js`, `page-reader.js`, `run.js`, `fill.js`, `agent.js` and `runs.js`.
- B owns `fill-loop.js`.

C, D and E are independent of A and B, and of each other, except where noted below.

| Batch | Owns |
|---|---|
| C | backend autofill files, and the autofill settings UI (veteran) |
| D | the tailoring prompts and services |
| E | `job.js`, `panel.js`, `stages/job.js`, `decisions.js`, `proposals.py`, `form-filling-section.tsx`, and the settings backend |

Shared files:
- A and E both edit `panel.js` only if the attach line needs it. A keeps its changes inside `runs.js` and `run.js`.
- E2 and E3 are done by one implementer, in sequence.
