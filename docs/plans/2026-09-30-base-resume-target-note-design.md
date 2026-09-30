# Base resume Target note — design

Status: draft for owner review (brainstormed in chat 2026-09-28/30). No plan yet.
Scope: `backend/` (model, migration, schemas, base-resume router, tailoring-session
read, prompt assembly and five LLM call sites, chat context), `backend/mcp_server/`
(one new tool, three widened), `frontend/` (identity dialog, new-base dialog,
gallery card), docs (`docs/entities/others.md`, `UBIQUITOUS_LANGUAGE.md`, SYSTEM.md §7).

## Goal Card

**Goal:** A base resume can say, in the user's own words, who it is for, such as
"UK fintech, Monzo/Revolut, senior IC, British spelling, 2 pages". Every LLM that
writes or edits that resume's content then honours it, in-house and over MCP.

**Why:** Today a base is anchored to a role and nothing else. Research
(chat, 2026-09-28) found other axes that matter:
- country or region, which changes page count, spelling, date format, photo and
  the work-authorization line;
- employer type, such as US federal or academic;
- target companies;
- industry and seniority.

It also found that the role anchor is barely load-bearing. Nothing in ATS
scoring, base ranking or any tailoring, Q&A or cover-letter prompt reads it. One
free-text note, delivered to the LLMs, covers every axis without new vocabulary
to maintain.

**Principles** (how to decide when this doc is ambiguous or wrong):
- **The note is instruction, never evidence.** It shapes emphasis, voice,
  spelling and length. It is never a source of claims about the candidate. The
  honesty invariant (`{#inv-honesty}`) and the server-side evidence gates are
  unchanged: "target Kubernetes roles" does not make an absent skill present.
- **An empty note changes nothing.** With no note set, every prompt is
  byte-identical to today's. Existing tests and calibration hold as they are.
- **LLMs are the readers, not code.** No deterministic path (ATS engine,
  ranking, rendering, analytics) parses the note. Machine-readable targeting is
  a later, separate decision (see Future).
- **Role stays.** `role_category` / `role_label` keep every current job: slug,
  coverage, the from-KB plan, artifact naming. The note sits beside the role and
  does not replace it.
- **Metadata, like the role.** Setting the note records no ResumeVersion,
  rewrites no JSON, triggers no render and invalidates no score.

**Non-goals:**
- typed Country, Company or Industry fields;
- ranking bases by target;
- market-driven render defaults such as A4, date format or page limit;
- free-form tags and gallery grouping;
- showing the note in the Companion;
- analytics on it.

## What exists today

- **The persona pattern.** `prompt_assembly._persona_block` is the model to
  copy. It prepends user-wide context to `gap_tailor`, `qa` and `cover_letter`.
  It prepends rather than using a `$placeholder` because seeded prompt rows
  never gain new placeholders and `safe_substitute` would drop them silently.
  Its label says "never as a source of factual claims".
- **The per-session note.** `TailoringSession.user_prompt` is a one-off
  instruction for a single tailoring. It is more specific than a base-level
  note and wins on conflict.
- **The identity endpoint.** `PATCH /api/base-resumes/{slug}/identity`
  (`BaseResumeIdentity`) is the metadata-only write for role and display name.
  It has no MCP tool; an agent cannot change a base's role after creation.
- **How LLM call sites reach the base:**
  - `TailoringSession.base_resume` and `Application.base_resume` are slugs.
  - `base_resume_instruct.propose` and `kb_adapt` hold the target `BaseResume`
    row.
  - `base_from_kb_plan` runs before the base exists.

## Design

### Data

- **Column:** `BaseResume.target_note: Text | None`. NULL means no note. One
  new SQLite-chain alembic revision (id from `uuid.uuid4().hex[:12]`, SYSTEM.md
  §9), adding a nullable column with no backfill.
- **Normalization (server side):** strip whitespace, and store `""` as NULL.
  Over **500 characters** is a **422** with a sentence ("Keep the target under
  500 characters."). The cap keeps the prompt cost bounded and nudges toward a
  brief, not a second resume.
- **Not in `data_json`,** so it never renders into the PDF and never reaches the
  ATS engine.

### REST

`target_note: str | None` is added to:

| Schema | Behaviour |
|---|---|
| `BaseResumeSummary`, `BaseResumeDetail` | Read. Every picker, the gallery and MCP `list_base_resumes`/`get_base_resume` get it for free. |
| `BaseResumeCreate`, `BaseResumeFromKB`, `POST /import` form | Optional at creation. |
| `BaseFromKBPlanRequest` | Optional. Fed to the plan prompt (below); the client passes the same text on to `POST /from-kb`, which persists it. |
| `BaseResumeIdentity` | Uses the same omitted-vs-null shape as `display_name`: omitted means unchanged; `null` or `""` clears it; a value is validated and set. Independent of the role fields: changing the note never demotes a role mapping. |

- **Duplicate** inherits the note, as it already inherits the role pair.
- **Seeding** (dropped-in JSON) leaves it NULL.
- **`TailoringSessionRead`** gains `base_target_note: str | None`. It is
  transient and read-time: the router joins it from the session's base, the
  same way `health_warning` is set after refresh (never a column, SYSTEM.md
  §12). This is how an MCP agent that writes its own ops sees the note without
  a second call.

### Prompt delivery

**One helper** in `prompt_assembly`:

```text
_target_block(note) -> "" when empty, else:

RESUME TARGET (who this particular resume is for — country or region,
companies, industry, seniority, spelling, length, style. Use it to decide
emphasis, wording, spelling and length. It is NEVER evidence: do not add or
imply any skill, experience, employer, metric or date because the target
mentions it. A USER PROMPT below, when present, is more specific and wins
on conflict):
<note>

---
```

**Order,** broadest to most specific:
1. skill preamble
2. persona
3. target
4. template body, whose `USER PROMPT` section stays where it is

It is **prepended**, not a `$placeholder`, for the persona's reason.

**Readers.** A reader is an LLM call that writes content for a resume that has a
base.

| # | Call site | How it gets the note |
|---|---|---|
| 1 | `tailoring_session._llm_customized` → `build_gap_tailor_prompt(…, target_note=)` | load `BaseResume` by `tailoring.base_resume` |
| 2 | `base_resume_instruct._ask` | `row.target_note` (prepend to the rendered template) |
| 3 | `base_from_kb_plan._ask` | the request's `target_note` (the base does not exist yet) |
| 4 | `kb_adapt` (rewrite KB points into the target resume's voice) | the target row |
| 5 | `qa`: `build_qa_prompt` and `build_cover_letter_prompt` at every call site | `application.base_resume` → row. Job-level answers with no application (`context_from_job`) use the named base when one is given, else none. |

**Deliberately not readers:**
- JD extraction and gap enrichment, which describe the job, not the resume;
- the coherence check, which is a read-only lint;
- autofill `/choose`, which answers form fields from the profile;
- the ATS engine;
- ranking.

A **missing base row** (soft-deleted base, or the `hybrid` fallback) gives an
empty block, never an error.

**The Assistant (in-app chat):** `chat_agent._context_block` appends
`Resume target: <note>` when the pinned target resolves to a base resume, or to
an application through its base. The chat tool `list_base_resumes` also returns
`target_note`, so the Assistant can pick a base by what it is for.

### MCP

- **New tool `set_base_resume_identity(slug, display_name?, role_category?,
  role_label?, target_note?)`** → `PATCH …/identity`, sending only the arguments
  that were given. The docstring must say that omitted means unchanged and an
  empty string clears the note.
  - It also closes the existing gap that agents cannot fix a base's role.
  - It contains no "delete" (`{#inv-mcp-controls}`).
  - It registers in every profile that registers `update_base_resume`, and is
    added to the subset assert in `mcp_server/tests/test_server.py`.
- **`create_base_resume_from_kb`** gains an optional `target_note`.
- **Reads:**
  - `list_base_resumes` and `get_base_resume` carry the note through the schema.
  - `create_tailoring_session`, `quick_tailor` and `get_tailoring_session`
    carry `base_target_note`.
- **Docstrings** of `quick_tailor` and `tailor_session` (caller-authored ops)
  gain one line: "Honour `base_target_note` for emphasis, spelling and length;
  it is never evidence." Both must stay inside the ~2048-char truncation budget
  (`test_registered_tool_docstrings_fit_client_truncation_budget`).
- **Workflow hints** (`workflow.py`) are unchanged. The note travels in the
  payload, not as a hint option.

### Frontend

- **Identity dialog.** `RoleCategoryDialog` ("Target role") becomes **Target**:
  - the existing role picker, then an optional textarea labelled **"What else
    is this resume aimed at?"** with help text "Country, companies, industry,
    seniority, spelling, length. The AI follows it when writing or editing
    this resume; it never adds claims.";
  - a live character count against 500;
  - one PATCH with only the changed fields.

  The editor's overflow-menu item keeps opening this dialog.
- **New base resume dialog:** the same optional textarea in every mode. In
  "From career history" it is sent to the plan call and then to the create call.
- **Gallery card:** when a note is set, show it as a one-line truncated
  subtitle, with the full text in the existing tooltip.
- **Copy** follows `docs/frontend-conventions.md`; add "Target" to the
  canonical terms if the vocabulary test requires it.

## Error handling

| Case | Result |
|---|---|
| Over 500 chars on any write path | 422 with a user sentence; nothing saved |
| Note on a soft-deleted base | Identity PATCH is 404 (existing behaviour) |
| Base row missing at prompt time | Empty block; the call proceeds as today |
| Note text contains `$` or template syntax | Safe: the block is prepended as plain text, never passed through `Template` |

## Testing

- **Unit, `prompt_assembly`:**
  - empty or whitespace note gives `""`;
  - a set note appears once, after the persona and before the body, and
    carries the "NEVER evidence" sentence.
- **No-note equality:** for each of the five readers, the prompt with a NULL
  note equals the prompt built by today's code path (the empty-note principle).
- **Per reader (1–5):** fake `llm.call_openai`, never the guard (SYSTEM.md
  §12), capture the prompt, and assert the note is present.
- **Router:**
  - create, from-kb and import persist the note;
  - duplicate inherits it;
  - identity PATCH covers set, clear with `null`, clear with `""`, and omitted
    (unchanged);
  - a note-only PATCH leaves the role pair untouched;
  - 501 characters gives 422;
  - no ResumeVersion row is written and no render is triggered.
- **Tailoring session read:** `base_target_note` is present, and is NULL for a
  missing base.
- **Migration:** the existing model↔migration parity test passes.
- **MCP:**
  - the new tool is registered (subset assert);
  - respx confirms only the given fields reach PATCH;
  - the docstring budget test passes.
- **Frontend:** the vocabulary and plain-words tests pass. Verify the dialog
  once in a fresh dev stack, not the compose stack (SYSTEM.md §9).

## Docs to update in the same change

- `docs/entities/others.md` (BaseResume): the note's semantics, readers and
  metadata-only writes.
- `UBIQUITOUS_LANGUAGE.md`:
  - a **Target note** row ("the user's own words for who a base resume is
    for; instruction to the AI, never evidence");
  - the relationship line becomes "declares exactly one Role Category and
    optionally a Target note".
- SYSTEM.md §7 (MCP coverage): the new identity tool.

## Future (not this change)

If a deterministic reader is ever needed, add a typed field then. Examples:
- auto-picking the UK base for a UK job;
- A4 and date-format defaults;
- a Getting Started suggestion for a missing market.

A typed `market` (ISO country) is the likely first. It can be proposed from the
note by the LLM and confirmed by the user, the same way role is proposed on
import. The note does not block that path.

## Open questions for the owner

1. **Naming:** on screen **"Target"**, in code `target_note`. Keep, or prefer
   another word?
2. **Cap:** 500 characters. Enough?
3. **Q&A and cover letters** read the note (reader 5). Keep, or limit the note
   to resume content only?
