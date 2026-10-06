# Base resume anchors — design

Status: draft for owner review, 2026-10-05. Replaces the 2026-09-30 "Target
note" drafts (free-text note fed to five prompt readers), which the owner cut
down to this scope. No implementation plan yet.

Scope:
- `backend/`: model, migration, schemas, identity PATCH, the
  all-bases scoring entry point and its score read, analytics best-base pick,
  two prompt builders;
- `backend/mcp_server/`: one new tool, two widened, one parameter;
- `frontend/`: the Target dialog, gallery and score cards, the score panel's
  skipped line;
- docs: `docs/entities/others.md`, `UBIQUITOUS_LANGUAGE.md`, SYSTEM.md §5/§7.

## Goal Card

**Goal:** A base resume can carry up to four optional **anchors**:

| Anchor | Shape | What it does |
|---|---|---|
| **Countries** | Multi-select of ISO countries | **Strict.** Decides which jobs the resume is scored for. |
| **Role** | The existing role picker | Describes. Unchanged. |
| **Company** | Short text | Describes. |
| **Focus** | Short text: the kind of jobs this resume is aimed at | Describes. |

**Why country is different:**
- **Country is a knock-out.** An India resume carries an Indian location and
  India-specific points. Sent to a US job it is rejected outright, so it should
  not be scored there at all.
- **Role, company and focus are interchangeable.** A resume aimed at one
  company or role often scores well for a similar one and can be swapped in.
  They only steer how the AI writes.

**Principles** (how to decide when this doc is ambiguous or wrong):
- **Every anchor is optional, and none set means "use anywhere".** A resume
  with no countries is eligible for every job. Existing resumes behave exactly
  as today.
- **Only country filters.** Role, company and focus never exclude a resume,
  never change a score and never change ranking.
- **Unknown job country means no filter.** When the job's country is missing
  or unrecognized, every selectable resume is scored and the user chooses.
- **The filter never leaves you with nothing.** If no resume is eligible for a
  known country, every resume is scored and the panel says so.
- **Anchors are instructions to the AI, never evidence.** They feed exactly two
  prompts, tailoring and Ask for changes, as one line. The honesty invariant
  (`{#inv-honesty}`) and the evidence gates are unchanged.
- **No anchors, no change.** With no anchors set, both prompts are
  byte-identical to today's, and scoring candidates are exactly today's
  selectable set.
- **Anchors are metadata, like role.** Setting them records no ResumeVersion,
  rewrites no JSON, triggers no render and changes no score.

**Non-goals:**
- feeding anchors to Q&A, cover letters, autofill (`/choose`, Jev), the
  Assistant, `kb_adapt` or the from-career-history plan. The resume's content
  already carries what those need;
- matching company, role or focus against the job;
- anchors in the new-base dialogs (set them in Target after creating or
  copying);
- editing a job's detected country (§11 item 4 covers job-field correction);
- a scoring override in the Companion;
- market-driven render defaults, tags, gallery grouping, analytics by anchor;
- rewording "Best match".

## Data

`BaseResume` gains three columns in one new SQLite-chain alembic revision (id
from `uuid.uuid4().hex[:12]`, SYSTEM.md §9). All are nullable or default empty,
so there is no backfill.

| Column | Type | Rules |
|---|---|---|
| `countries` | `JSONDoc` list of strings, default `[]` | Each value is uppercased and must be an ISO 3166-1 alpha-2 code from the vendored list (below). Duplicates are dropped; order is kept. An unknown code gives **422** ("Unknown country code: XX."). |
| `company` | `Text`, nullable | Stripped. `""` is stored as NULL. Max 80 characters, else 422. |
| `focus` | `Text`, nullable | Same rules as `company`. |

Role keeps `role_category` / `role_label` exactly as they are. "Role not set"
(`unknown`) is already its empty state, so role is already optional.

**One country list.** Vendor the ISO 3166-1 alpha-2 codes with English names as
`backend/app/services/data/countries.yaml`. A small `services/countries.py`
loads it and offers `is_valid(code)`, `normalize(code)` and `labels()`.

`normalize` uppercases the code and maps the one common non-ISO alias, `UK`, to
`GB`. Anything else that is not in the list returns None. Do not add a
dependency for this.

`GET /api/countries` returns `[{code, name}]` for the dropdown.

## Writing anchors

- **REST:** `BaseResumeIdentity` (`PATCH /api/base-resumes/{slug}/identity`)
  gains `countries`, `company` and `focus`. Each follows the same omitted vs
  null shape as `display_name`:
  - omitted means unchanged;
  - `null` clears it (for `countries`, `[]` also clears);
  - a value is normalized and validated.

  Anchor fields never touch the role pair, and a role change never touches the
  anchors.
- **Reads:** `BaseResumeSummary` and `BaseResumeDetail` carry all three.
- **Duplicate** copies the anchors once, like the role pair. After that the two
  copies are independent: there is no link, no sync and no drift tracking.
- **Not set elsewhere:** create, import, from-KB and seeding leave anchors
  empty.

## Scoring: which resumes are candidates

**One pure function** in `services/ats_score.py`:

```python
def country_eligible(base_countries: list[str], job_country: str | None) -> bool:
    c = countries.normalize(job_country)  # None when missing or unrecognized
    return c is None or not base_countries or c in base_countries
```

`Job.country` comes from JD extraction as a best-effort ISO code, or null when
ambiguous (`prompts/extract_jd.txt`). It is stored unvalidated
(`routers/jobs.py:120`), so it is always read through `normalize`. An
unrecognized value means unknown, which is the safe direction.

**Candidate set for a job:**
1. Start from `selectable_base_resume_slugs` (unchanged: active, not archived).
2. Keep the bases that are `country_eligible`.
3. If that leaves none while the job country is known, fall back to all of step
   1 and mark the result `fallback`.

| Case | Scored |
|---|---|
| Job country unknown | all selectable bases |
| Job country C, some bases eligible | bases listing C, plus bases with no countries |
| Job country C, no base eligible | all selectable bases, with the note "None of your resumes is set for {country name}." |

**Where it applies.** It runs both when scoring and when reading scores,
because score rows outlive a change to a base's countries:
- `ats_score.score_all_bases` scores the candidate set only.
- `ats_score.latest_scores` already drops archived and deleted bases' rows
  because the panel is a pick surface. It also drops rows for bases outside the
  candidate set, with the same rule in the same place.
- `explore_gaps._best_base_gap_rows`, analytics' "the base you would actually
  send", picks only among candidate bases.
- MCP `score_ats` ranks whatever the POST returns, and the Companion merges the
  POST's rows. Both inherit the filter with no code of their own.
- Proposal `chosen_base` (`frontend/lib/api.ts`) reads the filtered list.

**Override for a wrongly detected country.** `POST /api/ats-scores`
(all-bases form) and `GET /api/ats-scores` gain
`include_other_countries: bool = False`. When it is true, both use step 1 with
no country step.

**What the response reports.** The all-bases response stays a list, so its
shape is unchanged for every client. A new
`GET /api/ats-scores/candidates?job_id=` reports how candidates were chosen:

```json
{"job_country": "US", "fallback": false, "skipped": ["india_de"]}
```

`job_country` is the normalized code or null; `skipped` holds the slugs
excluded by country.

MCP `score_ats` gains the same `include_other_countries` parameter. Its
docstring says that bases for other countries are not scored unless this is
true.

## Prompt line

**One helper** in `prompt_assembly`:

```text
anchor_line(countries, role_display, company, focus, *, for_job) -> str
```

It returns `""` when all four are empty, and an unset role counts as empty.
Otherwise it returns one plain-text block:

```text
RESUME ANCHORS: Countries: India · Role: Data Engineer · Company: Example Corp · Focus: payments platforms
Emphasize these where relevant. They are not evidence of experience.
```

Only the set anchors are listed, using country names and the role's display
label. With `for_job=True` it adds one clause:

```text
The anchor company is not this application's employer.
```

That clause stops a resume anchored to one company from naming it as the
employer when it is tailored for another.

**Readers (exactly two):**

| Call site | `for_job` | Placement |
|---|---|---|
| `tailoring_session._llm_customized` → `build_gap_tailor_prompt(…, anchors=)` | True | Prepended after the persona block, before the template body, like `_persona_block`. Prepended rather than a `$placeholder`, because seeded prompt rows never gain new placeholders. |
| `base_resume_instruct._ask` (Ask for changes) | False | Prepended to the rendered template |

**Loading the anchors.** Tailoring loads the base by `tailoring.base_resume`
through `active_filter()`, the same gate `load_base_resume` uses. A missing row
gives `""`. Ask for changes already holds the row.

**MCP caller-authored tailoring.** `TailoringSessionRead` gains a transient
`base_anchors` (`{countries, role, company, focus}` or null), set at read time
the way `health_warning` is. The `quick_tailor` and `tailor_session` docstrings
gain one line: "Honour `base_anchors` for emphasis; they are not evidence, and
the anchor company is not this application's employer."

## MCP

- **New tool `set_base_resume_identity(slug, display_name?, role_category?,
  role_label?, countries?, company?, focus?)`.** It calls the identity PATCH and
  sends only the arguments supplied.
  - It closes today's gap where an agent cannot change a base's role.
  - It contains no "delete" (`{#inv-mcp-controls}`).
  - It registers wherever `update_base_resume` does, and is added to the subset
    assert in `mcp_server/tests/test_server.py`.
- **Widened:**
  - `list_base_resumes` and `get_base_resume` return the anchors through the
    schema;
  - the session tools return `base_anchors`;
  - `score_ats` gains `include_other_countries`.
- Every docstring stays inside the ~2048-character budget
  (`test_registered_tool_docstrings_fit_client_truncation_budget`).

## Frontend

- **Target dialog.** `RoleCategoryDialog` ("Target role") becomes **Target**,
  with four optional controls in this order:
  1. **Countries:** a searchable multi-select from `GET /api/countries`. Help
     text: "Only scored for jobs in these countries. Leave empty to use
     anywhere."
  2. **Role:** the existing picker.
  3. **Company:** text, 80 characters max.
  4. **Focus:** text, 80 characters max, no placeholder (a blank field shows
     none, per the conventions); hint "Such as payments platforms."

  Help text under the dialog: "Used when tailoring or asking for changes. This
  does not change the resume." The dialog sends one PATCH with only the changed
  fields. The editor's overflow-menu item opens it.
- **Pills.** Gallery cards and score cards show the set anchors as small pills:
  country codes, role label, company, focus. They show nothing when none are
  set.
- **Score panel.**
  - When `skipped` is non-empty, show one line: "2 resumes for other countries
    weren't scored for this United States job." plus a "Score them anyway" button. The link
    re-scores and re-reads with `include_other_countries=true` for that view.
  - When `fallback` is true, show the "None of your resumes is set for…" note.
- **Copy:** follow `docs/frontend-conventions.md`. Register "Target" and
  "anchor" in the canonical terms if the vocabulary test requires it.

## Error handling

| Case | Result |
|---|---|
| Unknown country code, or company/focus over 80 chars | 422 with a user sentence; nothing saved |
| Identity PATCH on a soft-deleted base | 404 (existing) |
| Job country missing or unrecognized | No country filter |
| No base eligible for a known country | All bases scored; `fallback: true`; note shown |
| Base missing at tailor time | Empty anchor line; tailoring proceeds as today |
| Anchor text contains `$` or template syntax | Prepended as plain text after substitution, never passed through `Template` |

## Testing

- **`countries`:**
  - `normalize`: case, `UK`→`GB`, unknown → None;
  - every code in the YAML is two uppercase letters, and the list has no
    duplicates.
- **`country_eligible`:** the three cases in the table, plus an unrecognized
  job country.
- **`score_all_bases`:**
  - a filtered set;
  - the empty-set fallback;
  - `include_other_countries`;
  - a base with no countries is always a candidate.
- **`latest_scores`:** a base scored for a US job and then marked India
  disappears from the default read, and returns with `include_other_countries`.
  Existing archived and deleted filtering is unchanged.
- **Analytics:** `_best_base_gap_rows` never picks an ineligible base.
- **`/candidates`:** `job_country`, `fallback` and `skipped` for each case.
- **Identity PATCH:**
  - set, clear and omit each anchor;
  - anchors and role are independent;
  - no ResumeVersion or render is written;
  - 422 on an invalid code and on 81 characters;
  - duplicate copies the anchors, and editing one copy leaves the other
    unchanged.
- **Prompt line:**
  - empty anchors give `""`;
  - only the set anchors are listed, with country names;
  - the employer clause appears only when `for_job` is set;
  - template-like text stays literal.
- **No-anchor equality:** both readers' prompts with no anchors equal today's.
- **Reader wiring:** fake `llm.call_openai`, never the guard (SYSTEM.md §12).
  Capture the tailoring and Ask for changes prompts and assert the line is
  present.
- **Migration:** the model↔migration parity test passes.
- **MCP:**
  - the subset assert;
  - respx shows the identity tool sends only the supplied fields;
  - `score_ats` forwards `include_other_countries`;
  - the docstring budget test passes.
- **Frontend:**
  - the vocabulary and plain-words tests pass;
  - in a fresh dev stack (SYSTEM.md §9): set countries on a copy, score a job
    in another country, check the skipped line, then use "Score them anyway".

## Docs to update with the implementation

- `docs/entities/others.md` (BaseResume): the anchors, the country eligibility
  rule, metadata-only writes, and the two prompt readers.
- `UBIQUITOUS_LANGUAGE.md`:
  - an **Anchor** row: "an optional label on a base resume. Countries
    restrict which jobs it is scored for; role, company and focus steer the
    AI";
  - the relationship line gains the optional anchors.
- SYSTEM.md:
  - §5 step 4: scoring covers country-eligible bases;
  - §7: the identity tool, `base_anchors`, and `include_other_countries`.

## Revisions against main (2026-10-06)

Main moved about 470 commits after this design was written. The automation
track also landed: the Automations page, answer receipts, the agent dashboard
and its readiness marks. Its next phase is a Settings switch for auto-submit,
which reads `inbox_readiness.is_ready` and final review as its last gate. These
revisions supersede the sections above where they conflict.

1. **One eligibility module, `services/base_eligibility.py`.** It holds the
   country rule, the candidate set (`slugs`, `job_country`, `fallback`,
   `skipped`) and `is_eligible(job, slug)`.
   - Readers: scoring, the score read, the analytics pick, `best_base`,
     `/candidates`, readiness and final review. None re-derives the rule.
   - The score read and the analytics pick drop exactly the `skipped` slugs,
     and nothing else. Their archived and deleted handling stays as it is.
2. **Readiness gains `base_country`.** Its value is the job's country code
   when the linked application's base is not eligible for it, else null.
   - `is_ready` requires it to be null. The TS twin gains the same key and a
     warning mark, "Resume for another country".
   - The fallback (no base set for the country) counts as eligible.
   - This changes the readiness rule that auto-submit will read, on purpose. It
     is the gate that stops an India resume from being sent to a US job, even
     when the base was chosen explicitly, through "Score them anyway", or
     through a stale `fit.chosen_base`.
3. **Final review gains `base_country`:** `{job_country, base, eligible}` for
   the base actually being sent. That is the linked application's base, else
   `fit.chosen_base`, else null.
   - Nothing hard-blocks proposing, deciding or tailoring. An explicit choice
     still works, and readiness and final review are where it shows.
4. **Automation and agent paths:**
   - MCP `score_ats` returns a `countries` block (`job_country`, `fallback`,
     `skipped`) beside `scores`, so an agent can say why a base was not scored.
   - The hunt brief's base summaries carry each base's anchors.
   - The `tailor-run` skill uses `fit_json.chosen_base` only while it is still
     among `score_ats`'s scores.
5. **MCP limits on current main:**
   - The identity tool is full-profile only, as `update_base_resume` is.
   - It clears a text anchor with `""` and countries with `[]`, because the
     MCP client drops `None` arguments.
   - `quick_tailor` and `tailor_session` are at their docstring budget. The
     `base_anchors` fact goes in `create_tailoring_session` and
     `get_tailoring_session` instead, worded as a fact rather than an
     instruction ("emphasis hints, not evidence").
   - `base_anchors` is a model property, so all seven routes that return a
     session carry it. It is null for a soft-deleted base.
6. **Country input.** `countries.normalize` accepts an ISO code in any case,
   `UK`, or an English country name. Anything else is None, which means
   unknown and therefore no filter. Knock-out's private `_country` is not
   migrated in this change.
7. **Copy rules on current main.** UI text never uses "e.g." or "evidence", and
   a blank field shows no placeholder. The dialog's help text reads "Used when
   tailoring or asking for changes. Saving here does not change the resume."

## Future (not this change)

- Editing a job's detected country (with §11 item 4).
- A Companion override for skipped resumes.
- Region groups such as "EU".
- Feeding anchors to further prompts, if real use shows tailoring and Ask for
  changes are not enough.
