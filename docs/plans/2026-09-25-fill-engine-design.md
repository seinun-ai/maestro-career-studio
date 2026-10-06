# Companion fill engine rework — design

Status: approved 2026-09-25; revised the same day to the **hybrid** shape (a
generic path per field, plus an AI-chosen next step when the page surprises it)
after a second opinion from Codex (GPT-6 Astra). Implementation plan:
`2026-09-25-fill-engine.md`. Research behind it:
`docs/reports/2026-09-25-extension-reliability-research.md` (local-only, with
its probe script and results).

## Goal

Make Companion's Fill work on any job application page, not only the shapes its
label rules and writers already know. One press of Fill should leave every field
it can answer **verified**, and list every other field under a reason, without
ever stalling on one control. Adapt to unfamiliar widgets instead of needing new
code for each one.

## Why the current engine falls short

- **Labels.** `labelFor` and `questionTextFor` skip `aria-labelledby`, and the
  Workday questionnaire dropdowns carry their question only in a fieldset
  legend. Those fields reach no rule and no model.
- **Coverage.** Label regex rules decide which profile value goes where. Every
  unfamiliar wording is a `no_rule` (126 on Workday, 55 on iCIMS in local
  telemetry). An unmatched input combobox is never even collected.
- **Timing.** `/choose` decides before a closed dropdown's options exist, so the
  model sees `options: null`.
- **Proof.** A combobox write can report `filled` while the control is empty. A
  Workday text box can hold text Workday's own state never took ("required and
  must have a value"), and the next run counts it as already filled.
- **Two writer copies** that disagree (one clicks hidden options of another
  widget), and **identity** keyed by joined label text.
- **Stalls.** Popups that ignore Escape stay open; unanswerable fields hold the
  run.

## Decisions

| Question | Decision |
|---|---|
| Approach | **Hybrid.** One generic path per field; when it ends somewhere unexpected, a bounded **adaptive step** loop where Jev picks the next move from moves code lists |
| Decision engine | **Pure AI** for meaning: Jev maps every field to a fact and picks every option. No label rules, alias tables, fuzzy scoring or exact-match shortcut |
| Code keeps | Boundaries (frames, consent, never-fill, user edits, human navigation/Submit), observation and targeting, execution primitives, formatting, verification |
| Unsettled fields | Listed by reason in the panel; clicking one scrolls to and focuses it |
| Low-stakes questions | Optional Autofill-profile setting, default off, answers them in the job's favour |
| Stalls | Per-field time, attempt and step budgets; skip and move on |
| Rollout | No interim patch to today's fill; the new engine replaces it after evaluation |

Why not AI for every click: each decision is a round trip (20 fields × 4
decisions × ~200 ms ≈ 16 s before the page's own waits), and Jev can only choose
among options code shows it — code has to observe the page and execute anyway.
So AI decides meaning always, and mechanics only when the generic path fails.

## Architecture

```
panel: shared/fill-loop.js                    page frames: content scripts
──────────────────────────                    ─────────────────────────────
round:
  observe ─────────── fill_inventory ───────▶ field-reader.js + inventory.js
  POST /api/autofill/map   (labels only)
  explore option fields ─ fill_explore ─────▶ fill-core.js  open → read owned options → close
  POST /api/autofill/choose (prose, parallel)
  POST /api/autofill/pick  (live options)
  commit ───────────────── fill_apply ──────▶ fill-core.js  act → blur → read committed + errors
  if the commit ended somewhere unexpected:
    ┌ fill_step_state ──────────────────────▶ candidate moves for this field now
    │ POST /api/autofill/step (Jev picks one move)
    └ fill_apply {move} ────────────────────▶ execute, verify     (≤ 6 steps, 25 s per field)
  sweep ────────────────── fill_sweep ──────▶ re-commit text showing an error
repeat while progress, max 4 rounds
```

### Page side

**`content/field-reader.js`** — one reader for "what is this field asking":
`label[for]`, wrapping `<label>`, every ID in `aria-labelledby`, `aria-label`
(a listbox button's own value and "Required" stripped; empty → fieldset legend),
legend, bounded nearby text. Zero-width characters are spaces; open shadow roots
work. Returns question, help, section, repeat index, required, and the source.

**`content/inventory.js`** — every fillable control in the frame, grouped (radio
by name, checkbox groups, date sections) into fields
`{fid, fp, shape, question, section, repeatIndex, required, committed, answered,
options?, optionsComplete, invalid, touched, policyBlocked}`. Modal application
forms are walked; only popups the engine itself opened are skipped. A control no
shape recognises is still listed (`unknown`) so the report can name it.
`answered` is stricter than "has a value": an unchecked lone checkbox or a set
with some chips is not finished. `fid` is bound to the
element (WeakMap) with a fingerprint for reacquiring a re-rendered node. Display
text is never identity. Fields the user typed in are `touched` and left alone.

**`content/fill-core.js`** — the generic mechanics, replacing per-widget
adapters. Two kinds of field:
- **Text-like** (text, textarea, date parts): focus, select, `execCommand
  ("insertText")` (real input events Workday/React accept; setter fallback),
  one blur per widget, then verify.
- **Choice-like** (native select, radio/checkbox groups, lone checkbox, popup
  buttons, input comboboxes, search-and-pick, chips): `explore` opens the
  control (press; type a search term for search shapes), reads the options of
  the popup it **owns** (ARIA link, or the single popup that appeared), scrolls
  long lists, and closes with Escape then an outside click. `commit` re-opens,
  re-finds the option by text (fresh target), clicks it (press → click →
  Enter), blurs, closes, and verifies.

Shape-specific knowledge is only a **committed-value reader** per shape (native
`value`/`selectedOptions`, `checked`, button text, single-value node, pill/chip
set, hidden backing input, `aria-selected`) and **how to open** it. Verify always
runs after the final blur and treats a visible field error / `aria-invalid` as
not filled. Search-box text is never proof. Equality keeps punctuation (only
phone numbers compare by digits); dates never gain precision the fact lacks;
the sweep also catches a verified value the page reverted later.

**Cancellation is real.** Every page operation carries an op token; when its
budget runs out or the user presses Stop the token is cancelled, and every
primitive (press, type, click) checks it first, so a late click cannot land.

### Adaptive step

When a commit ends `unexpected` — a sub-menu replaced the options, a search box
appeared, no owned popup opened, the value did not stick — the loop asks the page
for the field's **current state and candidate moves** (`fill_step_state`), each
a code-generated id binding an operation, a target and a value reference:

`click:<oid>` (a visible owned option) · `search:value` / `search:word:<n>` (type
the fact or one of its words into an owned search box) · `open` · `scroll` ·
`close` · `give_up`

`POST /api/autofill/step` sends the field's question, the fact (looked up
server-side from the slot), the last moves and their outcomes, and the candidate
descriptions; Jev returns one move id (Choice with `give_up` as abstention; a
probability floor per slot policy). The page executes it and reports the new
state. At most 6 steps within the field's 25 s deadline; `give_up` or the budget → "Needs your
answer" or "Could not operate". This one loop replaces hand-written category
descent, typeahead fallbacks and retry ladders. Models never emit selectors,
code or free text here.

### Panel side — the loop (`shared/fill-loop.js`)

Per round: inventory → `/map` for undecided fields → explore choice fields that
mapped to a value (prose goes to `/choose` in parallel) → `/pick` in one batch →
commit each → adaptive step for `unexpected` commits → sweep → next round only
if something changed. Max 4 rounds.

- **Sets** (skills, multi-selects): one pick per approved item — over the
  visible options, or search-and-pick for search widgets — so every chosen
  option maps back to the item it stands for. Verified only when every approved item
  is committed; otherwise reported as partial ("3 of 5 added") under Needs your
  answer.
- **Stale decisions are dropped:** an action carries the field fingerprint and
  option text (adaptive moves also the state version); the page re-checks them
  — and whether the user edited the field or policy now blocks it — at
  execution time.
- **An honest abstain over a popup goes to the adaptive step** (the fact may sit
  under a category or behind a search), not straight to "Needs your answer".
- **Deadlines:** every model call (10 s), field (25 s) and run (3 min) has a
  clock; a late answer is ignored.
- Stop is latched for the run: it cancels the in-flight op token and every
  later operation until the next run starts.
- Navigation and Submit stay with the user.

**Panel report groups:** Filled (verified), Closest match — check, Answered for
you — check, Needs your answer, Could not operate this control; jump-to-field on
each. The blank count comes from verified state.

## Backend

- **Fact catalog** (`autofill_catalog`): every profile fact by slot, every
  education and experience entry, date parts, skills as a set, saved custom
  answers; codes turned into the words forms show; built from the consent-gated
  profile plus the selected resume.
- **`POST /api/autofill/map`** — one Jev Choice per field over fact
  *descriptions* (never values) plus `free_text`, `none`, `blocked_eeo` (no
  consent). Returns route + slot + value (to the local extension). With the
  low-stakes setting on, a **second pass** asks (Noul) only about choice fields
  no fact answered — so a real profile answer always wins.
- **`POST /api/autofill/pick`** — Choice over live option ids + `none`; sets
  are picked one approved item per question; policy thresholds from the slot.
  Categories are handled by the adaptive step.
- **`POST /api/autofill/step`** — Choice over candidate move ids + `give_up`;
  a click needs the slot's match floor, and a closest click needs the page to
  report every option in view. `/pick` and `/step` re-check the low-stakes
  setting server-side.
- **Both engines, same floors.** With engine = fast (or a failed Jev batch) the
  fast model returns a key **and a 0–1 confidence**, and the same per-policy
  floors apply; exact-policy facts are never written on a low-confidence answer.
- `/choose` stays for prose (`free_text`) with the Career KB.

**Low-stakes setting** ("Answer low-stakes questions for me", default off).
Code-owned categories: how you heard / referral source, willingness or comfort
(travel, relocation, on-site, shifts, overtime), open to other roles, preferred
contact. Never: work authorization, sponsorship, eligibility, background, EEO,
education, experience, skills, certifications, clearance, salary, anything
signed. A real profile answer always wins. Uses the job title/company and the
page's `?source=` hint; answers are `assumed` and listed to check.

## Privacy and safety

Name, email and phone never leave the machine (Map sees labels). Pick and Step
send one fact per field; EEO only under standing consent. Page text is data:
every model question says so, and enforcement is structural — models choose
among ids code generated, so a hostile label cannot add targets, values or
operations. Telemetry stays value-free (route, shape, outcome, steps used).

## Evaluation

Two separate questions, measured separately:
1. **Mechanics** — real-Chromium fixtures reproducing Workday (listbox with
   categories, search-and-pick with async results and chips, focus-out-validated
   text, date sections, Escape ignored), Greenhouse React-Select, native
   controls, portaled popups, hidden stale options, rerenders, shadow roots,
   iframes, and the research's six failures. Backend calls stubbed.
2. **Meaning** — mapping agreement against the rule history in telemetry
   (diagnostic, not ground truth) plus a small hand-labelled set of option
   picks (sponsorship, degree, how heard…), run against the real Jev key.
   Wrong writes and false completions are counted separately from coverage.

## Rollout

Build the engine beside today's fill; the panel's AI mode switches to it once
the end-to-end fixture run passes; the owner tests live; the old rule pass and
writers are deleted after the evaluation is reviewed. SYSTEM.md is groomed
before it is updated.

## Out of scope

Chrome debugger / Puppeteer executor, vision, automatic wizard navigation,
submitting.

## Revision 2026-09-26 — live Workday findings

The owner ran Tasks 1–8 on Guidehouse (Workday) and reported, page by page,
what failed. Claude then probed a second Workday tenant (Home Depot) live,
step by step, with the same synthetic events the extension sends. Field notes,
with the DOM and every experiment: `docs/reports/2026-09-26-workday-field-interactions.md`
(local-only). Most failures were **mechanics and proof**, not meaning: moves the
engine did not have, and verification reading the wrong place, so a correct
action still looked failed and the adaptive step never got a usable state.

### Mechanics (page side)

| Change | Where | Why (notes §) |
|---|---|---|
| **Enter a field:** `focus()`, then dispatch `focus`/`focusin` only if the browser did not fire them. **Leave a field:** blur `document.activeElement` if it is inside the field's widget, THEN dispatch `blur` + `focusout` only if the browser did not (no double handlers in a focused window). One helper, used by every writer | fill-base `typeText`/`leave` | `el.focus()/blur()` fire nothing in an unfocused window; Workday moves focus inside a date by itself; its blur check reads where focus is now (§1, §6) |
| **Key press** = `keydown` + `keyup` | fill-base | Field of Study searched only on key-up (§2) |
| **Search widget sequence:** press → wait for the list container → snapshot the committed value → type → Enter → wait until the list settles (busy gone and option text unchanged for a short quiet period — NOT "differs from before", a search can legitimately return the default list) → read pills (Enter may already have committed) → re-find by text → click → wait for the redraw → verify | fill-core `open`/`choose` | Workday needs a press before typing and Enter to search; reuses rows; streams results; auto-commits a single hit (§2) |
| **Click the checkable inside an option** (radio/checkbox) when there is one; else the option | fill-core gestures | A row click only highlights (§2) |
| **Identical option texts are one option** — take the first, but only when they also share the same visible category/path; identical text under different categories is ambiguous and goes to the adaptive step | fill-core `match` | Two identical "LinkedIn" leaves → "option missing" (§2) |
| **Search-widget box = the widget container, never the input itself;** pills from `[data-uxi-widget-type="multiselect"]` / `formField-*`; multi = that container | shapes `box`/`chips`/`searchMulti` | The marker is on the input; pills read "" so no pick could verify (§2) |
| **Popup-button committed value = its hidden input CHANGED from its pre-pick value** (and cleared by a placeholder pick), text only as display | shapes popup `read`/verify | Four picks showed Yes/No, then reverted; the hidden input tells saved from shown (§8a) |
| **Open/closed by visibility,** not `aria-expanded` or DOM presence | fill-base `engineOpen` | An outside click hides the list but leaves `aria-expanded="true"` (§8a) |
| **Errors:** `aria-invalid` on any part + a visible "Error:" text in the field box, not only `errorMessage`. An error is proof of failure; its absence is never proof of success | fill-base `invalid` | Workday's date error is a plain span (§6) |
| **Money compares as a number** (parsed, keeping decimals and sign; currency symbols and thousands separators ignored), chosen by the fact's type, like phone | fill-base `equivalent` | "$80,000" is kept as "80000" (§8a) |
| **Toggles:** never click a multi option twice without re-reading the pills after a redraw | fill-core `set` | A second click removed "SQL" (§2) |
| **Order inside a section:** a "currently" checkbox before the dates; re-inventory after any commit that adds or removes fields | loop | Ticking it removes the To date (§4) |

### New capabilities

1. **Add entries.** Per repeating section (Work Experience, Education, Websites,
   Languages, Certifications): **reconcile** the page's entries with the
   profile's (an entry already holding a job/school is matched to it, an empty
   one is used first), then press the section's own Add button only for
   profile entries left over that have the facts the entry requires. Never
   more than the profile can fill (Add makes the fields required); never
   Delete.
2. **Attach, verified by the page.** Proof is the uploaded file's row showing
   the filename, not `input.files` (Workday empties it after a successful
   upload). Attach stays its own button; its false "No upload box took the
   file" is fixed.

### Meaning (backend)

- **Derived facts:** `full_name`, `today`, US citizen / sponsorship answers from
  work-authorization status, "immediately" availability → today's date.
- **Closest-option picks** where the fact's words never appear: "Masters of
  Business analytics" → "Masters"; "no" → "Not Applicable"; "Asian" →
  "Asian (Not Hispanic or Latino) (United States of America)". `/pick` already
  does this; the fixes above let it see and commit the options.
- **Salary** "requirements/compensation" wording joins the salary fact.
- **Reasoning route** for choice questions derivable from the resume/KB
  (government employment, clearance): the fast model with resume context,
  answers marked "check it". It answers only from positive evidence — silence
  in the resume is not "No" (e.g. no clearance is never inferred from absence);
  derived work-authorization answers carry their provenance.
- **Model routing:** Jev first, one fast-model fallback, same floors. No
  smart-model tier (owner decision).
- **Low-stakes scope (owner, widened):** willingness (relocate, travel, drug
  test), how heard, contact preference, "related to / previously employed
  here" style Nos, SMS/marketing contact consents, and job-description
  self-assessment yes/no questions. Still never: factual education/experience
  entries, work authorization, sponsorship, EEO, background, clearance,
  salary, legal attestations.
- **Consent-forms rule (owner, 2026-09-26, replaces the never-fill list):**
  with the standing consent-forms permission on, NOTHING is refused by label —
  signatures and typed-name attestations, initials, consents, terms, salary
  "requirements" are all fillable when a fact exists. Only moving to the next
  page and Submit stay the user's, always. Without the permission, today's
  refusals stand. (`shared/policy.js`, SYSTEM.md `inv-policy-deny-list-single-source`.)
- **Languages in the profile (in scope, owner 2026-09-26):** languages with
  read / speak / write level, and "native" and "fluent" as separate flags, edited on the web
  app's Autofill profile, served in the fact catalog as one entry per
  language; Workday requires Language 1.

### One field controller (from the second review, 2026-09-26)

The generic path, the adaptive step and recipes are not three executors: they
are three ways of proposing the NEXT MOVE to one controller per field —
observe → propose → check preconditions → execute → leave → verify → keep or
recover. Consequences:
- **Exploration can commit.** Typing a search and pressing Enter committed a
  single hit live. Every move snapshots the committed value first; an
  unintended commit is undone (remove the pill it added) before the next move,
  and if it cannot be undone the field stops and is reported.
- **Deliberate writes are never experiments:** Add, consent ticks and
  signatures run once, on a decision, not as trials.
- **One budget per field** shared by every source (generic, recipe, adaptive,
  re-commit); a state + move pair that failed is not retried.
- **Outcomes:** verified · closest/assumed (check) · **unconfirmed** (evidence
  missing or conflicting — never shown as Filled) · needs your answer · could
  not operate · **unsupported** (the widget ignored every synthetic input;
  said plainly, since the engine has no trusted input).
- **Reverts:** a final sweep after a short quiet period re-reads every
  engine-verified field's committed evidence; a field the engine wrote that
  reverted gets **one** re-commit per run, then is reported unstable.

### Tests

Fixtures keep their own **application-state oracle** (the value the page
really holds, invisible to the engine), so a test fails on any false "filled"
or wrong write. Workday fixtures are rebuilt from the live DOM in the field notes (marker on
the input, press-to-open, Enter-to-search on key-up, streamed and reused rows,
radio/checkbox inside rows, virtualized lists, duplicate leaves, hidden-input
commit, wrapper-level date blur with focus moving between parts, file input
emptied after upload, Add sections). A behaviour the notes did not observe live
is not modelled as Workday — labelled adversarial fixtures (delayed rollback,
identical options in different categories, trusted-input-only widgets, recipe
poisoning) are added as their own set. Then held-out widgets/tenants with cold
and warm recipes, then live checks on several vendors. No corpus proves "any
page"; the promise is bounded progress and honest reporting.

### Remember what worked (in scope, owner 2026-09-26)

A value-free, local **recipe** per widget FAMILY signature: structural marker
names (`data-automation-id` / `data-uxi-widget-type`), roles, control
topology, popup ownership, single/multi, the kind of commit evidence, and the
engine version — never GUIDs, labels, values or option text. An origin-level
override sits under the family key. A recipe stores parameterised moves with
their pre/postconditions (e.g. "press; wait for list; type ⟨term⟩; Enter; click
the checkable in ⟨option⟩"), not selectors or answers. It is a **shortcut
proposal to the field controller**, never a separate executor, and never
relaxes verification. Lifecycle: one success → probationary; promoted after
independent successes that also survived the final sweep; cross-tenant use
starts as a candidate that must verify fresh; demoted at once on a
contradiction, quarantined on a structural mismatch, confidence expires with
age. Local, bounded, clearable, no URLs.
