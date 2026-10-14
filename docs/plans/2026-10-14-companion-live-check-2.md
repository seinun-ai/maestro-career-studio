# Companion live check 2 fixes (Phase 2c) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Fix what the owner's second live check showed on three non-Workday sites, labelled here as ATS-D, ATS-G and ATS-O (2026-10-14):
- the run declared "Ready to submit" too early;
- whole classes of controls were invisible to the engine;
- written questions were skipped;
- resume boxes were missed or mis-picked;
- the panel hid tools and showed clutter.

**Architecture:** The fixes go into existing modules. Readiness lives in the page reader and driver. Field reading and uploads live in `field-reader.js` and `agent.js`. New widget shapes and techniques live in `inventory.js`, `shapes.js`, `fill-core.js`, `fill-ops.js` and `fill-loop.js`. Answers live in backend `autofill_*`. Panel work lives in `panel/stages/*`.

Every task is test-first. Tests use made-up fixtures that copy the real markup shape. Nothing in the repo names a real company or tenant.

**Owner decisions (2026-10-14):**
- **Name.** The profile stays as entered: First "Ajey Dhayashanker", Last "Loganathan". A first name is never split. A Middle Name box is filled only from a stored middle name, and there is none, so it stays empty. There is no new middle-name feature.
- **Dates: "low stakes are decisive decisions".**
  - A date box that needs more precision than the profile has gets the 1st of the month. If the month is also missing, it gets January.
  - These fields are reported "answered for you: check". They are never left blank and never parked.
  - The same spirit covers other format and precision gaps: a URL gets `https://`, and a dialing code comes from the country.
  - Facts are still never invented.
- **Written questions.** A required written question ("most impressive project…", "most interesting technology…") is drafted from the career history in implied first person, filled in, and listed under "Check before you submit". Submit stays the user's.
- **The Ask box** (paste a question, get an answer) returns under the run card.
- **Unchanged rules:**
  - Submit is never clicked.
  - Next is pressed only in a run the user started.
  - Apply on a posting is pressed only through a plain same-tab link.

Diagnosis notes are local only and not in the repo.

---

## Batch G: readiness, closed pages, fill-log visibility

**Owns:** `content/page-reader.js`, `shared/page-kind.js`, `shared/queue-run.js`, `panel/runs.js`, `panel/actions/run.js`, `sw.js` (the `fill_trace` reply only).

### G1: Ready only on a real review page with nothing missing

**Problem**

The ready step (`queue-run.js` ~519) ignores page errors, required empties, and *why* the page was classed `review`. `page-kind.js` returns `review` for five different reasons. `queue-run.js` ~456 also turns a page with no fields and a lone Next (at step > 0) into `review`.

What happened on each site:
- **ATS-D:** the footer Next sits outside its four `<form>`s, so it was dropped. The page then read as "fields, no Next", which counts as `review`.
- **ATS-O:** section 3 has only cards plus a NEXT button. The step-0 rule made it `review`.
- **ATS-G:** a real review page, but required textareas and the upload read as not required.

**Behaviour**
1. **`summary()` changes:**
   - Each button carries `chrome` (site header, nav or footer outside the application).
   - Stepper labels (`[class*="steps" i]`, `[class*="stepper" i]`, `[role=progressbar]`, when not a real button) never count toward `submitSeen`.
   - Add `requiredEmpty`, a count plus value-free keys. It covers every visible control (and every file input whose box is shown) that is required and empty. "Required" means any of: `readField.required`, the `required` attribute, `aria-required`, or a star or "required" in the label just before the control's own wrapper. "Empty" means any of: no text, a placeholder select, a group with nothing chosen, or an upload with no file.
   - Add a `page_required` op returning `{label, target, kind}` items, in the same style as `page_errors`.
2. **`classify` changes:**
   - When no Next is inside a form, take the single visible, enabled Next that is neither in chrome nor in the error summary.
   - `review` carries `by`, one of: `submit_button`, `submit_seen`, `submit_context`, `several_next`, `fields_no_next`.
   - Flip `test_a_next_outside_the_form_is_not_taken_as_the_forms_next` so it covers the chrome-only case.
3. **Remove the ~456 override:**
   - A page with no fields whose lone button is a plain Next ("Next", "Next step", "Save and continue/next") gets that button pressed.
   - A page with no fields whose lone button is "Continue" or "Proceed" parks as a new `confirm_page`.
4. **Ready only when all of these hold:** `by === "submit_button"` (a real Submit control and no real Next), `summary.errors === 0`, and `requiredEmpty === 0`. Otherwise:
   - **Errors:** run the existing repair. If they persist, park `page_errors`.
   - **Required empties:** run one scoped `fix` with `only`, plus the targeted attach for a lone upload. If they are still empty, park `open_questions` naming them.
   - **Any other `by`:** park `unsure_page` ("Not sure this is the last page. Check it, then press Resume or Submit yourself."). Never Ready.
5. **Value-free diagnostics:** store `readyBy` and the last classify reason word on the record.
6. **Moved on (P2):** when a ready record reads a form step that has a real Next, the card says "You moved on. Press Resume to fill this page."

**Tests**
- page_kind:
  - a Next outside every form and outside chrome becomes `form_step`;
  - a Next in chrome is never the step's Next;
  - `by` is set.
- Browser fixtures:
  - `wizard_forms_footer.html`: three forms, a stepper ending "Submit", and a footer Next. Expected: `form_step`, `submitSeen` false.
  - `label_before_box.html`: a long question in a span before `div>div>textarea`, plus a hidden file input under "Résumé *". Expected: `requiredEmpty` is 2.
- queue_run:
  - review with errors repairs and is not Ready, then a clean re-read is Ready;
  - a required empty triggers `fix(only)`, then parks `open_questions`;
  - `fields_no_next` parks `unsure_page` and never advances;
  - a field-less "Next" at step 2 advances;
  - a field-less "Continue" parks `confirm_page`.

### G2: a closed page means closed

**Problem:** `CLOSED` (`page-reader.js` ~53) matched a job description sentence ("…the level at which this position is filled"). `page-kind.js` checks closed before anything else.

**Behaviour**
- Tighten the pattern to: `this (job|position|posting|requisition) (has been|is now|is) closed | has been filled | (is )?no longer (accepting applications|available|open)`. Drop the bare "is filled".
- A page counts as `closed` only when it has nothing fillable and no Apply control.
- Add `closed` to `RESUMABLE_STOPS`, with the line "Not closed? Press Resume."

**Tests**
- A posting with the job-description sentence plus an Apply link reads as `posting`.
- "This position has been filled" with no Apply reads as `closed`.
- Flip `test_closed_is_the_closed_text`.
- Resume after a closed stop drives.

### G3: say when the fill log is off; show the attach line on Ready

**Behaviour**
- The sw's `fill_trace` replies `{posted:0, why:"off"}` when telemetry is off.
- After a run ends while the log is off, the run card shows one line: "Fill log is off. Turn it on in Options to let Maestro CS see what each field tried."
- `readyBody` shows the attach line whenever the outcome is not `attached`.

**Tests:** a panel test for each.

---

## Batch H: field reading and resume boxes

**Owns:** `content/field-reader.js`, `content/agent.js`, `panel/actions/fill.js`.

### H1: long question labels

**Problem:** `labelish` (`field-reader.js` ~112) refuses anything over 12 words or 80 characters. So ATS-G's questions (13–14 words, outside any `<label>`) were read as an empty question and not required.

**Behaviour:** for a non-choice field, `precedingLabel` accepts a candidate that ends in "?" (after unmarking) and is at most 200 characters. It returns the candidate whole, so both sentences survive and the star still marks the field required.

**Test:** `<div><span>What is the hardest bug you fixed for Acme? Why was it hard? <span>*</span></span><div><div><textarea></textarea></div></div></div>` reads with that question and required true.

### H2: upload box labels outside the widget

**Problem:** ATS-G's "Resume *" sits outside the react-dropzone widget. `readField(input)` gives up at the widget's own "Click to upload…" text, so the box reads `unknown` and not required.

**Behaviour:** in `uploadBoxOf` and `pageUploads`, when `read.question` is empty, use `ns.unmark(ns.precedingLabel(uploadWidgetOf(input) ?? input, [input]))` for both the label and `required`.

**Test:** a dropzone fixture with "Resume *" outside it reads as `kind: "resume"` and required, and the attach writes the file.

### H3: two resume inputs, one of them a parser

**Problem:** ATS-D has two hidden inputs that share the id `…files_resume`. One is "Import Resume" in the Candidate Info section, which is the site's own parser and pre-fills fields. The other is the real "Resume Upload" section. The run skipped both, silently. ATS-O's section-1 "RESUME" box was most likely a parser too: it would explain the wrong education rows, the middle name and the truncated link.

**Behaviour**
- **Parser box:** a box whose own wording or section says it imports, parses or autofills from the resume ("Import Resume", "Autofill with resume", "Apply with resume", "Upload your resume to fill") is a parser box. It is **never written**.
- **Several resume-looking boxes:** keep only the ones whose section names a resume upload, and demote the rest to `unknown`.
- Apply this in `uploadBoxes`, `pageUploads`, `theResumeBox` and `targetBox`.

**Tests**
- Two `id=files_resume` inputs: one under "Candidate Info" with an "Import Resume" button, one under "Resume Upload". Expected kinds `["parser"/"unknown", "resume"]`, and the file lands only in the second.
- A lone "Import Resume" box is never written. The run then parks `upload` only if a real required box exists.

---

## Batch I: widgets and techniques

**Owns:** `content/inventory.js`, `content/shapes.js`, `content/fill-base.js`, `content/fill-core.js`, `content/fill-ops.js`, `shared/fill-loop.js`.

### I1: read-only comboboxes with an invisible input

**Problem:** Ant Design read-only selects (Preferred Contact Method, How did you hear, Prefix, Suffix) put the input at `opacity: 0`. `fillBase.visible` treats that as hidden, and inventory `shown()` drops it.

**Behaviour:** a popup-shape input (a read-only `role=combobox` or `aria-haspopup`) counts as shown when it has client rects and its box (`shapes.box(el)` or its parent) is visible.

**Test:** an antd-like fixture: an opacity-0 read-only combobox, a selection-item span, and a portal listbox with rows Email and Mobile Phone. Expected:
- the field is listed as `popup`;
- choosing "Email" is verified;
- the selection item reads "Email".

### I2: pill button groups

**Problem:** the ATS-O `cx-select-pills` pattern is a `ul role=list aria-label=question`, where each `li` holds a `button aria-pressed`. It covers every Yes/No question and the Degree field. The inventory never sees it. Clicking an already-pressed pill un-selects it.

**Behaviour**
- Add a `pills` shape:
  - **Grouping:** buttons with `aria-pressed` that share the nearest container holding at least two of them and no other control. Also accept `role=radiogroup` / `role=radio` with `aria-checked`.
  - **Question:** the container's `aria-label`, otherwise the preceding label.
  - **Options:** the button texts.
  - **Committed:** the text of the pressed button.
  - **Answered:** any button is pressed.
- **Choose:** look first and never click a pressed button. Click once, then verify `aria-pressed="true"`.

**Test:** a fixture with "Have you worked for Globex before?" (No/Yes) and a toggle script where a second click un-selects. Expected:
- one required group with options [No, Yes];
- choosing Yes is verified;
- choosing Yes a second time does not click;
- a pill the user pressed counts as answered.

### I3: debounced search lists (JET-style combobox)

**Problem**
- `search()` sends Enter after `ANSWER_MS = 300` when nothing has shown. On a list debounced by about 500–800 ms, that Enter kills the search.
- `readSearch` treats an `oj-text-field-container` as a select-style widget and reads `""`, so a real pick comes back `not_committed`. That re-picks up to 3 times, which is the visible "flicker".

**Behaviour**
- **No Enter:** never send Enter to a box with `aria-autocomplete` list or both. Wait up to 2.5 s for the rows to appear and change, then for 300 ms of quiet.
- **Read-back:** for a box inside `oj-combobox-one`, the committed value is the input text when the element lacks `oj-has-no-value`. Generalise this: an input with `aria-autocomplete` whose own value is non-empty after a pick, with no separate value node, reads as committed.

**Tests:** a JET-like fixture with a 500 ms filter, where Enter with no list clears the query. Expected:
- explore lists the options;
- choose is verified;
- the committed text is read;
- no Enter is sent.

### I4: address autocomplete

**Behaviour**
- When the slot is `personal.address` and the box is a search box, the term is the full line-1 value, typed with no Enter (as in I3).
- Wait up to 4 s for rows. Score each row on:
  - the house number as a whole token;
  - the core street words, with suffixes treated as equal (Pl/Place, St/Street, Dr/Drive, Ave/Avenue, Rd/Road, Ln/Lane, Ct/Court, Blvd/Boulevard);
  - a bonus for city or ZIP.
- Pick the single best row only if it has both the number and the street name. Otherwise retry once with "number + street name" without the suffix.
- An address slot never gets `search:word` or `search:term` moves.
- After the pick, a City, State or ZIP value the page filled is left alone when it matches.
- If no row qualifies and the box keeps free text after blur, leave the typed line and flag it.

**Test:** rows "Allora Pl, Springfield" and "121 Allora Pl, Springfield" for the value "121 Allora PL". Expected: the second row is picked, the first never is, and no word moves happen.

### I5: URL values

**Behaviour**
- Add a `url` format for website, LinkedIn, GitHub and portfolio slots, and for any field whose value is a URL.
- Never split a URL into words or terms.
- Write the full URL with `https://`, adding it when the stored value has none.
- Refuse rather than truncate when `maxlength` is shorter than the URL.
- Compare after normalising: scheme, `www.`, trailing slash.
- A URL box that holds a different host is flagged "holds something else". It is never counted as answered.

**Tests**
- A URL slot with the value `sample-one-site.example.dev` gets no word moves and writes `https://sample-one-site.example.dev`.
- A box holding `example.dev` against the value `sample-one-site.example.dev` is flagged.

### I6: native date boxes take the 1st (owner decision)

**Behaviour**
- For a native `type=date` box, or any date widget that needs a day, given a month-only value: write day 01.
- Given a year-only value: write 01-01.
- Report the field as `assumed`, with the note "Day set to the 1st". Do not park it.
- Respect `min` and `max`.
- Replace `test_a_date_widget_asking_for_a_day_the_fact_lacks_is_left_alone` with the new rule.

**Tests**
- A start date of `2021-05` writes `2021-05-01` and is reported `assumed`.
- A year `2024` writes `2024-01-01`.
- A `max` earlier than the value refuses.

### I7: flicker visibility

**Behaviour**
- When an explore committed a value and it was taken back, the trace effect is `took_back`.
- Each field reports `changes`, the number of value changes. It is value-free.

**Test:** an explore that commits then undoes records `took_back`.

### I8: never left blank because of a missing label

**Behaviour:** in `leftBlank`, an unlabelled textarea, or an unlabelled required control, is `needs_answer`. It is never `left_blank`.

**Test:** an optional unlabelled textarea comes back `needs_answer`.

---

## Batch J: answers (backend)

**Owns:** `backend/app/services/autofill_map.py`, `autofill_catalog.py`, `autofill_choose.py`, `prompt_assembly.py`, the qa service, and any answer prompts.

### J1: never invent a middle name

**Behaviour**
- A question matching `\bmiddle\s*(name|initial)\b` routes `none` unless the fact is `personal.middle_name`. The profile has no such fact, so it never fills.
- In the extension, `content/autofill.js` gets a guard rule before `first-name`: middle name is skipped. This hunk belongs to Batch J.

**Test:** with the profile `{first_name: "Jane Marie", last_name: "Doe"}`, "Middle Name" routes `none`, and "Marie" never appears.

### J2: phone country code

**Behaviour**
- Add `derived.phone_country`, built from `personal.country`. Example: "+1 United States".
- Its description: "the phone number's country and calling code (a dialing-code picker); never the number itself".

**Tests:**
- the catalog builds the fact;
- a "Country dialing code" case maps to it (fill-map case).

### J3: draft written questions

**Behaviour**
- A required written question (a text or textarea shape routed `free_text`) whose answer `/choose` returns null gets an answer from the essay writer, `/api/qa`. The answer is:
  - drafted from the career history and the job;
  - in implied first person, with the voice rule applied;
  - at most about 120 words unless the field says otherwise.
- It is filled and reported `assumed`, with the note "Drafted from your history: read it". The panel's "Check before you submit" list shows it.
- It is never written for protected or EEO slots, or anything on the never list.
- The draft is not saved as a standing answer unless the user edits it and resumes. Existing learning rules apply.

**Tests:**
- a "What's the most impressive project you've worked on? Why?" field gets a drafted answer and status `assumed`;
- a protected question is never drafted.

---

## Batch K: panel

**Owns:** `panel/stages/fill.js`, `panel/stages/job.js`, `panel/panel.js` (only the toggles).

### K1: the Ask box returns

**Behaviour:** when a run card is shown, `fillBody` still attaches `qnaDrawer(ctx)` below it.

**Test:** with a ready run, the drawer toggle is there and `#qna-question` shows when it is opened.

### K2: hide bases that weren't scored for this job

**Behaviour**
- When at least one base is scored, the Job list shows the scored bases plus the selected one.
- A linkish "Show N more (not scored for this job)" button reveals the rest.
- When nothing is scored, all bases show, as today.

**Test:** three bases with two scored shows 2 rows and the "Show 1 more" button. Clicking it shows 3.

---

## Batch L: docs and gate

### L1: docs

Update these:
- `SYSTEM.md`: the Ready rule invariant, the parser-box rule, the low-stakes precision rule, and essay drafts flagged.
- INTERNALS: pills, JET, address and URL techniques, `requiredEmpty`, the `unsure_page` and `confirm_page` parks, and the fill-log-off line.
- CHANGELOG.
- The user guide: the Ask box, and that written answers are drafted for review.

### L2: gate

- Full suite, slop ratchet, tsc and lint, and `check_system_md`.
- Per-task Astra reviews, falling back to Opus when Astra is at its limit.
- Opus batch reviews, then a final Opus review.
- Then rebuild and update the live app.
- The owner's next live check runs with **Keep a fill log** on, and includes one Workday run.

## Order and ownership

Batches G, H, I, J and K own disjoint files and can run in parallel.

**Shared hunks:**
- J adds one guard rule in `content/autofill.js`, which no other batch owns.
- I8 lives in `fill-loop.js`, owned by I.
- G3's attach line lives in `runs.js`, owned by G.

**Interfaces:**
- G1's `requiredEmpty` relies on H1 and H2 reading `required` correctly. G must also detect required empties from star or `aria-required` on its own, so G does not block on H.
- J3 needs I8, so that a written question is never `left_blank`.

---

## Addendum: Workday live run (2026-10-14, a Workday tenant)

**Owner decision: create the account.** On known ATS hosts, the Companion creates the account with the saved job-site login. It fills the email, password and verify-password fields. It ticks only a plain account or privacy agreement checkbox when the page requires one, and then presses Create Account. Email codes and CAPTCHAs still park. This reverses the 2026-10-10 rule "account creation always parks".

### G additions

**G1+: Ready on Workday question steps**
- `content/detect.js` `fillableControls` counts popup buttons: `button[aria-haspopup]:not([aria-haspopup="false"])`, plus any non-input `[role=button][aria-haspopup]`. Search controls are excluded. G owns this hunk.
- `requiredEmpty` treats a popup button that shows a placeholder ("Select One", from `policy.js` `PLACEHOLDER`) as empty. It counts as required when its aria-label ends in "Required", or when its legend has `abbr[title=required]` or `*`.
- If the fill listed 0 fields and a re-read then shows `fillable > 0` (or a new set of field fingerprints), set `pageFilled = false` once and fill again before Next or Ready.
- Reset `record.flags` for each page (`run.js` ~414). A page whose receipt is null must not show the previous page's flags.
- Test fixture `wizard_popup_questions.html`: three Workday-style popup buttons that mount 2.5 s after the footer. Expect `fillable` to be 3, the fill to list 3 fields, and the run never to report Ready while `requiredEmpty > 0`.

**G3+:** the fill-log-off line also shows the last trace time.

**G4: create the account (owner decision)**
- `page_create_account` op, in the top frame, on known ATS hosts only, at most once per record. It runs only when the page has exactly one email box and two `new-password` boxes:
  - type the saved email, and the same saved password into both password boxes;
  - never type into a honeypot. Treat as a honeypot any control whose label or name says it is for robots, any `name="website"` on an account page, or any control with "beecatcher" or "honeypot" in its automation id;
  - tick the single account-agreement checkbox only if it is required and its label is an agreement to create the account or to the privacy notice. Never tick marketing opt-ins;
  - press only the button whose whole label is "Create Account".
- The password comes from the existing `/api/companion/job-site-login` route. It stays in a local variable only, never in a card, trace or log.
- After the press:
  - an email check parks `verify`; after Resume, the existing sign-in route signs in;
  - a password-rule or duplicate-account error parks `create_account_failed`, never retried;
  - an "Already have an account" situation leaves the existing sign-in path to handle it.
- Test: an `acme.test` fixture with the email, password and verify ids, the agreement checkbox, the honeypot, and the Create Account button. Assert the honeypot stays empty, the button is pressed once, and the next page is read.

### H addition

**H2+:**
- `sectionOf` climbs to the nearest preceding heading in the same field or section, up to about 10 levels. It still stops at FORM and at any other field.
- A lone attachable box whose section says resume or CV counts as `resume`, whether or not it is required.
- Test: the `workday_errors` shape without `aria-required` reads `resume`, and the file is written once.

### I addition

**I2+, category rows:**
- A list row counts as a group when it has no selection control, no radio and no `aria-checked`, and it has a trailing chevron icon.
- A row whose click revealed children is remembered in `memory` as progress.
- A category is never committed as the answer.

**I3 check:** Workday's search box needs Enter on keyup. The no-Enter rule must not break `workday_search.html`; key the rule on the live input attributes.

### J additions

**J4: worked-here reroute**
- In `_route`, a choice field gets `WORKED_HERE_SLOT` when both hold:
  - the map picked `history_unanswered`, `protected_unanswered` or no fact;
  - the question lists the job's own company (new helper `lists_job_company`).
- `named_employer_fact` then decides the answer.
- Test: history Hooli/Vandelay with a question listing "Acme Wireless, Globex, Initech…" answers No. Initech in the history answers Yes. "Initech Labs" gives no answer.

**J5: phone device type**
- Add `derived.phone_type = "Mobile"` when `personal.phone` exists, with the description "the kind of phone the number is (mobile, home or work)".
- Report it as `assumed`. That needs a small hunk in `autofill_pick._bar`.
- Exclude it from `differs_from_profile`.
- Add a `phone-type` skip rule before the phone rule in `content/autofill.js`.

**J6: How did you hear**
- Derive the source from the job's saved `source_url` host as well as `?source=`, for example linkedin.com → "LinkedIn".
- Add a slot goal for `preferences.how_heard`:
  - open the website, online or job-board category, otherwise "Other";
  - pick the board leaf, otherwise a job-board leaf, otherwise the company careers-site leaf;
  - report it as `assumed`.
- Test: a made-up category tree.

**J7: degree level in the flag**
- `answer_flags.py` compares `education.N.degree` by level: doctorate, master (including MBA and MS), bachelor, associate, high school.
- "Master's/Advanced Degree" against "Masters of …" is not flagged.
