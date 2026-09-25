# Jev as the Companion's form-filling decision engine — design

Status: implemented 2026-09-25 (live check pending with the owner's key). Implementation plan:
`2026-09-25-jev-autofill.md`.

## Goal

Make the Companion's AI fill pass (`POST /api/autofill/choose`) faster and more
honest on option-bearing fields by letting **Jev** (TypeSafe AI's System One
decision model) make the judgment calls, as an **optional engine** chosen in
Settings. The fast LLM stays the default and the fallback.

Jev returns typed decisions (Noul yes/no, Choice over ≤255 options, Score 2–10
levels) with calibrated probabilities, ~100 ms, $0.042/M input. It **cannot**
generate text, extract values, look anything up, or do reliable arithmetic/date
math. So: *code looks up, Jev judges, code acts.*

## Non-goals (this build)

- The typeahead/skills loop (step 3: type token → Jev picks suggestion → click or
  clear). Follow-up; needs a `/pick` endpoint and writer changes.
- Shadow/compare mode. Dropped by the owner.
- Any change to navigation or submit (they stay human, §7).
- Jev anywhere outside autofill (health check, gap↔KB matching are later).

## Architecture — engine switch inside `/choose`

The extension keeps sending only the fields its rule pass could not settle
(`ChooseField`: qid, label, kind, options ≤30, optional `known_value`). With
engine = `jev`, `autofill_choose.choose` routes each batch:

1. **Slot mapping** (one Jev call) — for fields WITHOUT `known_value`. State =
   field labels + kinds + option lists only; **no profile values**. One Choice
   question per qid over the slot catalog (flattened autofill-profile paths, e.g.
   `education.discipline`, `work_auth.sponsorship_now`) plus `free_text` and
   `none`. A field Jev maps below the confidence floor counts as unmapped.
2. **Value lookup** (code) — slot → value from `eeo_consent.disclosable_profile`,
   so EEO values are withheld exactly as today without standing consent.
   Fields with `known_value` skip step 1 and use it directly.
3. **Option pick** (one Jev call) — for fields with options and a value. State =
   `{value, options}` per field; Choice over the options plus `none`. The
   top option's probability and Jev's confidence feed the per-slot policy:
   - `any` (preferences: how_heard, relocate, …) — best option if above floor → `matched`
   - `flag` (factual claims: degree, discipline, school) — exact-ish (high
     confidence) → `matched`; plausible but lower → `closest`; else abstain
   - `exact` (work_auth.*, eligibility.*, eeo.*) — only high confidence → `matched`, else abstain
   Text fields (no options) with a slot value → `matched` with the value itself.
4. **Fast-LLM fallback** — `free_text`, `none` and low-confidence fields, and
   every field of a Jev call that errored, go to the existing prompt path
   unchanged. That prompt also carries the Career KB, so an unmapped field is
   never answered worse than today; Jev only speeds up what it can place.
5. **Option guard unchanged** — any answer not among rendered options abstains.

Response shape is unchanged except `Choice.reason` gains `"closest"`. The
extension's runner writes `matched` AND `closest`, and the Fill report lists
closest picks under "Closest matches to check". (No new telemetry outcome: a
closest write already reports as `filled`; add one only if the data is wanted.)

## Settings

- `model_settings`: `llm.jev_api_key` (write-only; reads expose `has_key`),
  `llm.jev_base_url` (default `https://openrouter.ai/api`; alt
  `https://api.typesafe.ai`), `llm.jev_model` (default `typesafe/jev-1.13`,
  pinned; `jev-latest` allowed), `llm.autofill_engine` (`fast` | `jev`, default `fast`).
- Router: `GET/PUT /api/settings/jev`, `POST /api/settings/jev/probe` (one tiny
  Noul call). Base URL must be `http(s)` — it decides where the key is sent (§6).
- Web: Settings › AI & models gets a **Form filling** block — key + Test,
  provider/model, and **Form filling decisions: Fast model / Jev** (Jev
  disabled until a key is saved).
- Extension: no new control; "Saved answers + AI" uses whichever engine is set.

## Error handling

`services/jev.py` (httpx, no SDK): `POST {base}/v1/systemone`, Bearer key,
`{model, state, questions}` → `answers`. 401/422 → `LLMProviderError`
immediately; 429/529 → one backoff retry; total budget ~2 s. Metadata-only
call log (same rule as `llm._log_call`). Any Jev failure falls back to the
fast model for the affected fields — the user always gets a fill.

## Privacy

Jev (and OpenRouter, when used) is a model-provider recipient under
inv-eeo-standing-consent. Step 1 sends labels only; step 2 sends the one value
per field plus page options. TypeSafe does not train on user data; zero data
retention is enterprise-only, so inputs are retained by default.

## Testing

respx tests for the client (request shape, error mapping, retry); chooser tests
for routing, each policy tier, the confidence floor, known_value short-cut,
EEO withheld without consent, and fallback on either call failing; settings
router tests; extension test that `closest` is written and reported. Live check
with an OpenRouter key on a Greenhouse/Workday form — a major with no exact
option (Business Analytics → Information Systems) is the closest-match case.
