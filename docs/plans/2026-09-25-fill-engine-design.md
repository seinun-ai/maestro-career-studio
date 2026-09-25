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

- **Sets** (skills, multi-selects): Noul membership over visible options, or per
  item search-and-pick for search widgets. Verified only when every approved item
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
- **`POST /api/autofill/pick`** — Choice over live option ids + `none`; Noul
  per option for sets; `category` step; policy thresholds from the slot.
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
