# Companion fill engine rework — design

Status: approved 2026-09-25. Implementation plan: `2026-09-25-fill-engine.md`.
Research behind it: `docs/reports/2026-09-25-extension-reliability-research.md`
(local-only, with its probe script and results).

## Goal

Make Companion's Fill work on any job application page, not only the shapes its
label rules and writers already know. One press of Fill should leave every field
it can answer **verified**, and list every other field under a reason, without
ever stalling on one control.

Scope is the research report's phases 1 and 2. The Chrome-debugger executor and
AI-chosen recovery actions (phase 3) are out.

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
- **Two writer copies.** The rule pass and the guided pass have separate widget
  code that disagree (one clicks hidden options of another widget).
- **Identity.** Retries are keyed by joined label text, which the collector does
  not reproduce.
- **Stalls.** Popups that ignore Escape stay open; unanswerable fields hold the
  run.

## Decisions

| Question | Decision |
|---|---|
| Scope | Phases 1+2: correct the blind spots, then observe → decide → act → verify loop with widget adapters |
| Approach | One set of widget adapters and a bounded loop, replacing both writer copies |
| Decision engine | **Pure AI.** Jev maps every field to a slot and picks every option; no label rules, alias tables, fuzzy scoring or exact-match shortcut |
| Code keeps | Policy (EEO consent, never-fill, knockout strictness, only rendered options are written), formatting (date/phone/address parts, typing skills), verification |
| Unsettled fields | Listed by reason in the panel; clicking one scrolls to and focuses it |
| Low-stakes questions | Optional Autofill-profile setting, default off, answers them in the job's favour |
| Stalls | Per-field time and attempt budgets; skip and move on |

## Architecture

```
panel (guided-run.js)                        page frames (content scripts)
─────────────────────                        ────────────────────────────
round:
  inventory  ───────── broadcast ─────────▶  inventory.js + field-reader.js
  /map (backend)
  explore option fields ─────────────────▶  widgets/<adapter>.explore
  /choose for free_text (parallel)
  /pick (backend)
  write + verify ────────────────────────▶  widgets/<adapter>.write|choose|setSelection → verify
  sweep errored fields ──────────────────▶  widgets/text.recommit
repeat while progress, max 4 rounds
```

### Page side

**`content/field-reader.js`** — one reader for "what is this field asking".
Sources in order: `label[for]`, wrapping `<label>`, every ID in
`aria-labelledby`, `aria-label` (a listbox button's own value and "Required"
stripped; if nothing is left, the fieldset `legend`), fieldset legend, bounded
nearby text. Zero-width characters normalise to spaces. Open shadow roots are
walked. Returns question, help text, section heading, repeat index, required,
and the source of each.

**`content/inventory.js`** — lists every fillable control in the frame as
`{fid, widget, question, section, repeat_index, required, committed,
options?, options_complete, invalid}`. `fid` resolves through a local registry
to the element (WeakRef) plus a structural fingerprint, so a re-rendered node
is found again. Display text is never identity. Every supported widget shape is
listed, known or not.

**`content/widgets/*.js`** — the only code that touches widgets. Each adapter:

| Operation | Meaning |
|---|---|
| `match(el)` | Is this my widget shape |
| `read(el)` | The committed value(s) |
| `options(el)` | Options visible without interaction: `{oid, text, selected}` + `complete` |
| `explore(el, term?)` | Open/search, read the widget's **own** live options, close (outside click; Workday ignores Escape) |
| `write` / `choose(oid)` / `setSelection(oids)` | Type, pick one, or reconcile a set |
| `verify(el, expected)` | `verified`, `reverted`, `unverifiable` |

First adapters: text/textarea (with date, phone, address parts), native select
(single and multiple), radio group, checkbox group (one field with options),
ARIA input combobox (including React-Select), Workday listbox button, Workday
search-and-pick (`selectinput`/`multiselectinput`, typing, categories), skill
chips, and a generic fallback that opens an unknown combobox and reads the popup
it owns.

**Option ownership.** Options count only when linked by `aria-controls` /
`aria-owns` / `aria-activedescendant`, or when they are the single popup that
appeared after this adapter's open. Visible and enabled only. Two candidate
popups → `unverifiable`, no click.

**Verify.** Blur, settle, then read the committed state per adapter: native
`value`/`selectedOptions`, `checked`, button text, chips, hidden backing input,
`aria-selected`. Search-box text is never proof. `aria-invalid="true"` or a
linked error message means **not filled**, even with text present. `reverted`
retries with the next method (click → full mouse sequence → keyboard Enter), 3
at most, then reports.

**Text commits like typing.** Focus, select contents,
`document.execCommand("insertText")` (the browser fires real input events,
which Workday/React accept), blur. The native-setter write is the fallback. A
box with text **and** an error is re-committed with its own value, never
retyped with a different one, and never counted as already filled.

**Multi-step widgets.**
- Category menus: Jev picks the category leading to the value; re-explore; up to
  3 levels. A category alone is not completion.
- Typeahead: code types the value, then its first significant word if nothing
  returns; Jev picks from the results. "Not in list"/"Other" only as a closest
  match on non-knockout slots.
- Multi-select: one Jev yes/no per visible option against the approved set.
  Existing selections are kept, an already-selected option is never clicked, and
  the final set is verified.

### Panel side — the loop (`shared/guided-run.js`)

Per round: inventory all frames → `/map` for undecided fields → explore option
fields that mapped to a value, while `/choose` answers `free_text` fields in
parallel → `/pick` in one batch → write and verify each field → sweep any field
still showing a required/validation error → another round only if a field
appeared or changed. Stop at 4 rounds or on a round with no progress.

- **Never stall.** Per field: explore ≤ ~2.5 s, whole field ≤ ~6 s, ≤ 3
  attempts, popup always closed on leaving. No fact, no match or timeout → skip
  at once, list it, continue.
- **Stale decisions are dropped.** Each frame reports a page generation;
  navigation, re-render or a user edit invalidates in-flight decisions and the
  field is re-observed.
- **Stop** cancels between any two actions.
- Navigation and Submit stay with the user (§7).

**Panel report groups:** Filled (verified only), Closest match — check,
Answered for you — check, Needs your answer, Could not operate this control.
Clicking an entry scrolls to and focuses the field in its frame. The blank count
is computed from verified state.

## Backend

**`POST /api/autofill/map`** — in: `{fid, question, section, repeat_index,
widget, required, options?}` per field. One batched Jev Choice over the slot
catalog plus `free_text`, `low_stakes`, `none`. Out per field: route `slot`
(with the value when code types it: text fields, typeahead search terms),
`free_text`, `low_stakes`, `none`, or `blocked` (EEO without consent,
never-fill). Labels only reach Jev; values are looked up in code afterwards.
Knockout strictness and consent are derived from the slot on the server.

**`POST /api/autofill/pick`** — in: `{fid, slot | low_stakes, options: [{oid,
text}], complete, multi}`. Server looks up the value; single answer = one Choice
over code-owned option keys plus `none`; multi = one Noul per option, batched.
Policy thresholds per slot. Out: `oid` or `oids` with `matched`, `closest`,
`assumed` or `abstained`. A strict Noul validator joins `choice_of`.

**`/choose`** keeps the fast-model prose path (with the Career KB) for
`free_text` fields.

**Slot catalog** (`autofill_slots`) expands to every education and experience
entry by index, date parts (month, year, full), address parts, phone parts, and
skills as a set.

**Engine = fast** runs the same contract on the fast model (JSON). A failed Jev
batch falls back to the fast model; both failing means nothing is guessed and
the panel says the AI could not be reached.

**Low-stakes setting** ("Answer low-stakes questions for me", Autofill profile,
default off). Code-owned categories: how you heard / referral source,
willingness or comfort (travel, relocation, on-site, shifts, overtime), open to
other roles, preferred contact method. Never low-stakes: work authorization,
sponsorship, age/eligibility, background/criminal, EEO, degree, experience,
skills, certifications, clearance, salary, anything signed or agreed to. Jev
picks the option a keen applicant for this job would choose, with job title and
company in state; "how did you hear" uses the job's known source (e.g.
`source=REC_LINKEDIN`) first. Answers carry reason `assumed`.

## Privacy

Name, email and phone never leave the machine: Map sees their labels and code
types the value. Only option fields send one value to Pick, EEO values only
under standing consent (inv-eeo-standing-consent). Telemetry stays value-free
and gains route, adapter, verify outcome and time per field.

## Testing

- **Real Chromium suite** (Python Playwright, dev dependency; CI installs
  Chromium and fails without it, local runs skip). Loads the real content
  scripts into offline fixtures modelled on Workday (listbox buttons,
  search-and-pick with categories, multi-select, focus-out-validated text,
  Escape ignored), Greenhouse React-Select, iCIMS/UltiPro native selects,
  SuccessFactors/Oracle comboboxes, plus checkbox groups, chips, portaled
  popups, hidden stale options, async search, node-replacing re-renders,
  `aria-labelledby`-only labels, repeated sections, a shadow root and an iframe.
  `/map` and `/pick` are stubbed with fixed answers.
- The research report's six probe failures become regression tests.
- Backend: respx tests for map/pick, the Noul validator, policy per slot,
  consent, fallbacks, low-stakes categories.
- The fake-DOM suite stays for pure logic; tests tied to deleted rules are
  removed or rewritten.

**Accuracy check before rules are deleted.** A local script sends the labels in
`autofill_field_observations` (no values) through Jev's Map and compares with
the recorded `rule_id`. The owner reviews the agreement rate and every
disagreement before the rule catalogue goes.

## Rollout

Each slice merges to local main for live testing:

1. Field reader, inventory, adapters, verify, the Workday text commit — run
   under today's decisions.
2. `/map`, `/pick`, the expanded slot catalog, Noul validation.
3. The loop and the new panel report.
4. Accuracy check, then delete the label rules and old writers.
5. The low-stakes setting.

SYSTEM.md (§7, §12) and `extension/INTERNALS.md` are updated with each slice.

## Out of scope

Chrome debugger / Puppeteer executor, AI-chosen recovery actions, vision,
automatic wizard navigation, submitting.
