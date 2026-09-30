# Base resume Target note — design

Status: revised draft for owner review, 2026-09-30. Review fixes applied: two
prompt-block variants (base / job), the recommendation-wording change moved out
of scope, and a concrete note-resolution rule. Incorporates independent
copies, country/region, role and company targets, and scoring all active bases.
No implementation plan or product changes in this document revision.

Scope: `backend/` (model, migration, schemas, base-resume router,
tailoring-session read, prompt assembly and five reader groups, chat context),
`backend/mcp_server/` (identity tool, targeting arguments and caller guidance),
`frontend/` (identity dialog, new-base dialog, gallery and scored-base cards),
docs (`docs/entities/others.md`, `UBIQUITOUS_LANGUAGE.md`, SYSTEM.md §5 and §7).

## Goal Card

**Goal:** Make it easy to prepare reusable specialized base resumes for a
country or region, a role, a company, or a combination of those targets. Keep
the target available to later AI edits and job-specific tailoring.

Examples: "UK, backend engineering, Monzo; British spelling" or "Germany,
data engineering". The existing role picker represents the role; an optional
free-text note supplies the other targeting details and preferences.

**User experience:** Copy an existing base when a separate version is wanted,
set its target, and use the existing **Ask for changes** action to specialize
its content. The copy is an independent base resume. Later, score all active
bases against a job, choose one, and tailor the application as usual.

**Why:** A resume's intended audience and its actual match to a job are
different things. A resume prepared for another country, company or role may
contain the strongest relevant evidence. Targeting should help explain and
adapt that starting point without hiding it or distorting its score.

**Principles** (how to decide when this doc is ambiguous or wrong):
- **Copies are independent.** Duplication copies content, role and target
  metadata once. There is no parent-child relationship, synchronization,
  propagation of later edits, or drift-management feature.
- **The note is instruction, never evidence.** It shapes emphasis, wording,
  spelling and desired length. It cannot establish skills, experience,
  employers, metrics, dates, location, or work authorization. The honesty
  invariant (`{#inv-honesty}`) and existing evidence gates remain unchanged.
- **The current application takes precedence.** When writing for a job, its
  actual employer, role and stated requirements, together with the user's
  application-specific instructions, override conflicting base preferences.
  Neither a job requirement nor an instruction changes candidate facts.
- **Score content across all active bases.** Preserve existing selectable-base
  rules, ATS scoring and deterministic ranking. Country, company and role
  targets introduce no new exclusions, bonuses or penalties.
- **An empty note changes nothing in prompts.** With no note set, every
  generated prompt is byte-identical to today's. Display-copy changes are
  separate; existing scoring calibration remains unchanged.
- **LLMs interpret the note; scoring code does not.** Code stores, validates
  and displays it, but deterministic scoring, ranking, rendering and analytics
  do not parse it. Automatic target-mismatch detection is outside this change.
- **Role stays.** `role_category` / `role_label` retain their existing jobs:
  slug, coverage, the from-KB plan and artifact naming. The note sits beside
  the role and does not replace it or introduce another role vocabulary.
- **Saving a target does not specialize content.** Setting the note records
  no ResumeVersion, rewrites no JSON, triggers no render and invalidates no
  score. Content changes still use the existing reviewed-edit workflow.
- **Prompt preferences are not render guarantees.** "Two pages" is a writing
  preference until checked against the rendered PDF. A target alone does not
  certify formatting, market suitability or application readiness.

**Non-goals:**
- linked variants, parent bases, automatic synchronization or drift tracking;
- a new specialization wizard, readiness status, approval stage or resume type;
- typed Country, Company or Industry fields;
- target-based ranking, filtering, automatic routing or mismatch warnings;
- market-driven render defaults such as A4, date format or page limits;
- free-form tags and gallery grouping;
- showing the note in the Companion;
- analytics on targets or an ATS score increase merely from setting one;
- rewording the score recommendation ("Best match" in `ats-score-panel.tsx`,
  "best match first" in the Companion's Score stage). That wording reaches
  beyond targeting, so it gets its own change if wanted.

## What exists today

- **Independent duplication.** `POST /base-resumes/{slug}/duplicate` creates
  a separate base. This remains the way to make a specialized copy.
- **Instruction → reviewed edits.** `POST /{slug}/propose` returns proposed
  edits without persisting them. **Ask for changes** applies approved edits
  through the normal `/edits` path. Supplying a target improves the context
  for this existing action; no new content-writing action is needed.
- **Creation from career history.** `/from-kb/plan` proposes entries and a
  summary for review; `/from-kb` composes approved points. Rewriting those
  points remains `kb_adapt`'s job. Adding a target does not silently turn
  composition into a full rewrite.
- **The persona pattern.** `prompt_assembly._persona_block` prepends user-wide
  context to `gap_tailor`, `qa` and `cover_letter`. It prepends rather than
  relying on a new `$placeholder`, because seeded prompts may lack one. Its
  label says "never as a source of factual claims".
- **The per-session note.** `TailoringSession.user_prompt` is a one-off
  instruction for a single tailoring and overrides conflicting base
  preferences within the factual constraints above.
- **The identity endpoint.** `PATCH /api/base-resumes/{slug}/identity`
  (`BaseResumeIdentity`) is the metadata-only write for role and display name.
  It has no MCP tool; an agent cannot change a base's role after creation.
- **How readers reach the base:** `TailoringSession.base_resume` and
  `Application.base_resume` are slugs; `base_resume_instruct.propose` and
  `kb_adapt` hold the target row; `base_from_kb_plan` runs before a base exists.

## Design

### User flow

1. Use the existing copy action when another version is wanted. The source
   remains unchanged and the new base initially inherits its role and note.
2. Open **Target**, keep or change the role, and optionally describe the
   country/region, company and writing preferences. Editing an existing base
   directly remains supported; copying is not mandatory.
3. Use **Ask for changes** to request specialization, review the proposal,
   and apply it through the existing editor. Saving the target alone only
   saves instructions for future writing.
4. On a job, score all selectable bases using the current workflow. Show each
   base's target with its score so a surprising result is understandable.
5. Choose a base and tailor the application. Job-specific adaptation writes
   the application draft and leaves every base unchanged.

No extra wizard, mandatory checkpoint or target confirmation is added.

### Data

- **Column:** `BaseResume.target_note: Text | None`. NULL means no note. One
  new SQLite-chain alembic revision (id from `uuid.uuid4().hex[:12]`, SYSTEM.md
  §9), adding a nullable column with no backfill.
- **Normalization:** strip whitespace, store `""` as NULL, then enforce the
  **500-character** cap. Over the cap gives **422** with "Keep the target to
  500 characters or fewer." Apply this consistently to every input path,
  including the non-persisting plan request.
- **Not in `data_json`:** the note itself never renders into the PDF or
  reaches the ATS engine. AI edits influenced by it remain ordinary resume
  content and are scored normally after they are applied.
- **No lineage fields:** copying creates no parent id, synchronization state
  or shared targeting record. Each base owns its own nullable note.

### REST

`target_note: str | None` is added to:

| Schema | Behaviour |
|---|---|
| `BaseResumeSummary`, `BaseResumeDetail` | Read. Exposes the note to gallery/picker consumers and MCP reads. UI consumers still need explicit display wiring. |
| `BaseResumeCreate`, `BaseResumeFromKB`, `POST /import` form | Optional at creation. Import stores it without silently rewriting imported content. |
| `BaseFromKBPlanRequest` | Optional; supplied to the plan prompt. The client passes the same note to `/from-kb` for persistence. |
| `BaseResumeIdentity` | Omitted means unchanged; `null` or `""` clears it; a supplied value is normalized and validated. A note-only write leaves the role pair unchanged. |

- **Duplicate** inherits the note once, as it inherits the role pair. Later
  edits to either base do not affect the other.
- **Seeding** from dropped-in JSON leaves the note NULL.
- **`TailoringSessionRead`** gains `base_target_note: str | None`, populated
  at read time from the session's base, like the transient `health_warning`.
  It is not a column or snapshot. This gives caller-authored MCP tailoring
  access to the note without a second call. Changing the note affects future
  generation; it does not rewrite an existing application or its artifacts.

### Scoring and selection

Keep the current ATS engine, active/selectable-base rules, score ordering,
tie handling and close-call behaviour. Do not restrict candidates by their
target country, company or role, and do not change scores using target metadata.

| Example | Behaviour |
|---|---|
| UK-targeted base leads for a US opening | Keep it in its scored position. If selected, adapt conflicting preferences for the current application; do not infer relocation or authorization. |
| Monzo-targeted base leads for Stripe | Preserve useful evidence and fintech emphasis. Replace or omit Monzo as the intended employer, while preserving any real historical employment or project facts. |
| Data-engineering base leads for a backend opening | Allow selection normally. Use its relevant evidence and adapt the application emphasis to the current role. |

Keep the existing recommendation wording ("Best match") and close-call choices
unchanged; rewording it is a separate change (see Non-goals). Show targets for
all scored bases with notes, not only for presumed mismatches; no automatic
mismatch interpretation is needed.

Use the existing base list/detail data to associate notes with score cards by
slug. Target metadata does not become an ATS feature or score payload field.

### Prompt delivery and precedence

**One helper** in `prompt_assembly`, `_target_block(note, *, for_job: bool)`.
It returns `""` when the note is empty. Otherwise it returns one of two
variants, so a prompt with no job never carries job rules it cannot apply.

**Base variant** (`for_job=False`): Ask for changes, from-KB plan, `kb_adapt`.

```text
RESUME TARGET (reusable preferences for this base resume):
<note>

Use these preferences for emphasis, wording, spelling and desired length. They
are NEVER evidence: do not add or imply skills, experience, employers, metrics,
dates, location or work authorization from them. The user's current request
overrides a conflicting preference, never the facts.

---
```

**Job variant** (`for_job=True`): tailoring, Q&A, cover letter. It is the base
variant plus exactly these rules, appended before the `---`:

```text
This document is for the job below: its employer, role and stated requirements,
and the user's application instructions, override conflicting preferences. A
requirement does not prove the candidate meets it. Never present a company named
in the target as this application's employer; keep true historical employers and
projects. Apply only preferences that fit this document: resume page limits and
section instructions do not govern a cover letter or a Q&A answer.
```

**Assembly order:** skill preamble → persona → target block → template body.
The body retains its existing job context and `USER PROMPT` section. Precedence
comes from explicit instructions, not merely from the order of text blocks.
The helper prepends plain text rather than using a new template placeholder.

**Readers:**

| # | Call site | Variant | How it gets the note |
|---|---|---|---|
| 1 | `tailoring_session._llm_customized` → `build_gap_tailor_prompt(..., target_note=)` | job | `target_note(tailoring.base_resume)` |
| 2 | `base_resume_instruct._ask` | base | the row it already holds (`row.target_note`) |
| 3 | `base_from_kb_plan._ask` | base | the request's note (the base does not exist yet) |
| 4 | `kb_adapt` | base | the target row it already holds |
| 5 | `qa`: `build_qa_prompt` and `build_cover_letter_prompt`, at every call site | job | `target_note(application.base_resume)`; job-level answers use the named base when supplied, otherwise none |

**Not readers:** JD extraction, gap enrichment, coherence lint, autofill
`/choose`, ATS scoring and deterministic ranking. These retain their existing
responsibilities.

**Resolving the note by slug:** add one helper,
`base_resume_data.target_note(slug, session) -> str | None`. It selects
`BaseResume.target_note` where `slug` matches and composes `active_filter()`,
the same resolution gate that `load_base_resume` uses. The results follow from
that gate, and no new policy is added:

| Base state | Note used |
|---|---|
| Active | The row's note. |
| Archived | The row's note. Archive removes a base from menus, never from the system (`docs/entities/others.md`). |
| Soft-deleted | None, so the block is empty. This holds even when an application still renders from its own `customized_json`. |
| No row (e.g. `hybrid`) | None, so the block is empty. |

A lookup that finds nothing never raises; the call proceeds exactly as today.

**Assistant:** `chat_agent._context_block` includes the target block when its
pin resolves to a base (base variant) or to an application through its base (job
variant, with the application's job named in the same context so the precedence
rule has something to apply to). It never injects the raw note unlabeled. Its
`list_base_resumes` tool returns `target_note`; the Assistant may explain a
selection using it but must not silently exclude other scored bases.

These are generation instructions, not a new server-side semantic guarantee.
Existing evidence gates and review paths remain in force.

### MCP

- **New tool `set_base_resume_identity(slug, display_name?, role_category?,
  role_label?, target_note?)`** calls `PATCH .../identity`, sending only
  supplied arguments. Document omission versus clearing and that saving the
  note does not edit resume content.
  - Closes the existing role-editing gap as well.
  - Contains no "delete" (`{#inv-mcp-controls}`).
  - Registers wherever `update_base_resume` registers; update the registration
    subset assertion in `mcp_server/tests/test_server.py`.
- **`create_base_resume_from_kb`** gains optional `target_note`.
- **Reads:** list/get base resume return `target_note`; create/get tailoring
  session and `quick_tailor` return `base_target_note`.
- **Caller-authored ops:** `quick_tailor` and `tailor_session` docstrings state:
  "Use `base_target_note` as reusable preferences, never evidence. The current
  job and application instructions override conflicts; inherit only relevant
  preferences and never a former target employer. Edit the application only."
  Keep docstrings inside the tested ~2048-character truncation budget.
- **Workflow hints:** preserve options, ranking, close-call behaviour and
  workflow shape, including recommendation prose. Notes travel in payloads,
  not new hint options. No new copy/specialization tool or workflow is introduced.

### Frontend

- **Identity dialog:** `RoleCategoryDialog` ("Target role") becomes **Target**.
  Keep the existing role picker, followed by one optional textarea labelled
  **What else is this resume aimed at?** Help text: "Country or region,
  company, and writing preferences. Saved for future AI edits; this does not
  change the resume." Placeholder: "UK, Monzo; British spelling."
  Show a live count against 500 and PATCH only changed fields.
- **Existing copy action:** continue creating an independent base. The user
  can rename it and change its target through existing controls. Do not add a
  wizard, a parent link, synchronization controls or another resume category.
- **Ask for changes:** keep the existing action and review flow. The saved
  target is included automatically when the user requests a content change.
- **New base dialog:** include the same optional textarea in every mode.
  From career history sends the note to both plan and create. No extra step.
- **Gallery and scored-base cards:** when a note exists, show a one-line
  truncated subtitle, with its full text available in the existing tooltip
  pattern. Preserve the visible role. Do not show empty placeholders or
  mismatch badges.
- **Copy conventions:** follow `docs/frontend-conventions.md` and register
  canonical terms where the vocabulary tests require it.

## Error handling

| Case | Result |
|---|---|
| Normalized note over 500 characters on any input path | 422 with the user sentence; nothing saved. |
| Identity PATCH on a soft-deleted base | 404, preserving existing behaviour. |
| Base soft-deleted or has no row at prompt time | `target_note()` returns None; empty block; the call proceeds as today. |
| Note contains `$` or template syntax | Insert as plain text after template substitution. This avoids template evaluation; it does not establish factual trust. |
| Target differs from the current job | Normal supported selection; apply the precedence rules during generation. No error or extra confirmation. |

## Testing and acceptance

- **Prompt helper:** empty/whitespace returns `""` for both variants. A note
  appears once, after persona and before the body. The base variant carries the
  evidence rule and none of the job rules. The job variant carries both, with
  the precedence, employer and document-scope rules. Template-like text remains
  literal. Each reader uses the variant its row in the readers table names.
- **No-note equality:** for all five reader groups and Assistant context,
  absent-note construction equals the existing prompt/context path.
- **Reader wiring:** fake `llm.call_openai`, never the guard (SYSTEM.md §12),
  capture each prompt and verify the note and relevant job/user context arrive.
- **Conflict scenarios:** verify prompt construction for a UK base used on a
  US job, a Monzo base used on a Stripe job, a different-role base, an explicit
  edit overriding a preference, and a resume page limit alongside a short Q&A
  answer. These tests prove delivery of rules, not semantic model compliance.
  Review representative generated outputs for correct employer, preserved
  historical facts and artifact-appropriate preferences before shipping.
- **Persistence:** create/from-kb/import persist the note; duplicate copies it
  once. Changing either copy's content or note leaves the other unchanged.
  Cover identity set, null/empty clear and omission; note-only PATCH preserves
  the role pair and creates no version, render or score invalidation.
- **Validation:** test whitespace normalization and the 500/501-character
  boundary consistently, including `/from-kb/plan` and identity updates.
- **Scoring:** changing only a note leaves scores and ordering unchanged.
  Bases aimed at other countries, companies or roles remain candidates under
  existing selectable-base rules; ordinary close-call behaviour is preserved.
- **Application isolation:** tailoring with a different target changes only
  the application draft, not the selected base or its source copy.
- **Resolution:** `target_note()` returns the note for an active and for an
  archived base. It returns None for a soft-deleted base and for a slug with no
  row. `base_target_note` on session reads follows the same four cases.
- **Migration:** model/migration parity passes.
- **MCP:** registration subset, supplied-fields-only identity PATCH, note
  round-trips and docstring-budget tests pass; workflow semantics stay intact.
- **Frontend:** vocabulary/plain-words tests pass. Verify copy → target edit
  → Ask for changes and scored-card subtitles in a fresh dev stack (SYSTEM.md
  §9), including a differently targeted top scorer and a close call. Check
  the actual rendered PDF before claiming any requested page limit is met.

## Documentation to update with implementation

- `docs/entities/others.md`: independent-copy semantics, target-note storage,
  metadata-only writes, readers and generation precedence.
- `UBIQUITOUS_LANGUAGE.md`: **Target note** means "the user's words for the
  intended audience and preferences of a base resume; instruction to the AI,
  never evidence". Preserve the existing Role Category relationship and add
  the optional note.
- SYSTEM.md §5: visible targets alongside unchanged all-base scoring and
  application-specific tailoring. §7: identity tool and caller guidance.

This revision changes a proposed design only. Update the living system
reference when implementation changes actual behaviour, not in anticipation.

## Decisions retained for this version

- On screen: **Target**. Stored field: `target_note`.
- One existing role picker plus one optional note, capped at 500 characters.
- Primary targeting dimensions: country/region, role and company. Other
  writing preferences remain expressible in the same note.
- Q&A and cover letters inherit relevant preferences, scoped to their artifact
  and actual job. Resume layout instructions do not carry over wholesale.
- Specialized bases are ordinary independent bases. No new lifecycle.
- All active/selectable bases continue to be scored. Target metadata does not
  change numeric ranking or require an additional confirmation.

## Future (not this change)

Only add structured targeting if a concrete deterministic consumer needs it,
such as a user-requested market selector or render setting. Any automatic
selection policy needs its own design and must preserve the possibility that
a differently targeted resume is the stronger starting point. No typed market
field, automatic filtering or targeting hierarchy is required by this design.
