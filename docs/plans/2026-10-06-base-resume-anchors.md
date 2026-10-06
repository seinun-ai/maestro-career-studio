# Base resume anchors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A base resume can carry four optional anchors.
- **Countries** are strict: a resume is scored, recommended and treated as
  ready only for jobs in its countries.
- **Role, company and focus** steer the AI's writing in tailoring and Ask for
  changes.

**Architecture:**
- **One new eligibility module** (`services/base_eligibility.py`) owns the
  country rule. Every reader asks it and none re-derives the rule:
  - scoring, the score read and the analytics pick;
  - readiness and final review, which are the auto-submit gate.
- **Anchors are four columns on `base_resumes`.** They are written only through
  the identity PATCH and read everywhere through one `anchors(row)` helper.
- **The prompt line** is prepended like the persona block.

**Tech Stack:** FastAPI, SQLAlchemy 2 on SQLite, alembic, pytest, FastMCP, Next.js
16 with React 19, Base UI combobox, Tailwind v4.

**Spec:** `docs/plans/2026-10-05-base-resume-anchors-design.md`. Read it whole,
including **Revisions against main (2026-10-06)**, which supersede the earlier
sections where they conflict.

## Global Constraints

- **Backend tests:** from `backend/`, run
  `pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile`. A bare
  `tests/` skips MCP. It must end green.
- **Migration:** one new revision whose `down_revision` is `7d3c1a9e5b20`. Its
  id comes from `python3 -c "import uuid;print(uuid.uuid4().hex[:12])"`. Use
  impl types only (`sa.JSON`, `sa.Text`), and never import app code
  (SYSTEM.md §12).
- **Field limits:**
  - company and focus: at most 80 characters (reuse `MAX_LABEL_CHARS`
    from `app/schemas/job_preferences.py`);
  - strip whitespace, and store `""` as NULL;
  - countries are uppercase ISO 3166-1 alpha-2 codes, de-duplicated, order
    kept.
- **No anchors means no change.** With every anchor empty, both prompts are
  byte-identical to today's, and scoring candidates equal
  `selectable_base_resume_slugs`.
- **Anchors never change a score.** Only countries filter, and only by
  dropping `skipped` slugs. Archived and deleted handling stays exactly as
  today.
- **Nothing hard-blocks.** Proposing, deciding and tailoring accept any active
  base. An explicit choice shows up in readiness and final review only.
- **LLM in tests:** fake `llm.call_openai`, never a guard (SYSTEM.md §12).
- **MCP:**
  - every tool docstring must fit within 2000 characters
    (`test_registered_tool_docstrings_fit_client_truncation_budget`);
  - no "NEVER", "MUST" or "Do NOT", and none of the `_BANNED_VOICE` phrases;
  - describe, don't instruct;
  - no tool name contains "delete".
- **UI copy:**
  - sentence case, at most 25 words a sentence, US English;
  - no "e.g.", no "evidence", no placeholder in a blank field, no semicolons;
  - errors go through `couldnt()`;
  - design tokens only (`test_frontend_design_tokens.py`).
- **SYSTEM.md** has 4 free lines (996/1000). Edits there are in-place rewords
  with no net growth; detail goes to `docs/entities/others.md`.
  `python3 scripts/check_system_md.py` must pass.
- **Commits:** one per task, conventional style. End each with the session's
  `Co-Authored-By` and `Claude-Session` lines.

## Review Focus

1. **Junk in `Job.country`.** Extraction stores whatever the LLM returns, such
   as "United States", "us", "Remote" or "". Codes in any case and English
   names must resolve. Anything else resolves to None, which means no filter
   (Task 1 tests).
2. **A base's countries change after it was scored.** Its old row must
   disappear from the default score read and from the analytics pick, then
   come back with `include_other_countries` (Task 3 tests).
3. **An application already sits on a base for another country.** This can
   come from "Score them anyway", an explicit tailor, or a stale
   `fit.chosen_base`. Readiness must mark it, and final review must say
   `eligible: false`. When no base is set for the job's country (the
   fallback), it must not be marked (Task 4 tests).
4. **Clearing over MCP.** `company=""` and `countries=[]` must clear, because
   the client drops `None`. Omitted arguments must leave anchors untouched
   (Task 6 tests).
5. **An archived base with countries** on an existing application still
   resolves its anchors. Readiness judges it by its own countries, not by
   whether it is selectable (Task 4 test).

---

### Task 1: Country list and normalizer

**Files:**
- Create: `backend/app/services/data/countries.yaml`
- Create: `backend/app/services/countries.py`
- Create: `backend/app/routers/countries.py`
- Modify: `backend/app/main.py`, adding the import (l.12-36) and
  `include_router` (l.190-212)
- Test: `backend/tests/test_countries.py`

**Interfaces:**
- Produces:
  - `countries.normalize(value: str | None) -> str | None`
  - `countries.is_valid(code: str) -> bool`
  - `countries.labels() -> dict[str, str]` (code → English name, file order)
  - `countries.name_for(code: str) -> str`
  - `GET /api/countries` → `[{code, name}]`

- [ ] **Step 1: Write the failing tests**

```python
def test_normalize_codes_aliases_and_names():
    assert countries.normalize("us") == "US"
    assert countries.normalize(" GB ") == "GB"
    assert countries.normalize("UK") == "GB"
    assert countries.normalize("United States") == "US"
    assert countries.normalize("india") == "IN"
    for junk in (None, "", "Remote", "XX", "Narnia"):
        assert countries.normalize(junk) is None

def test_list_is_iso_shaped():
    codes = list(countries.labels())
    assert len(codes) == len(set(codes)) >= 240
    assert all(len(c) == 2 and c.isupper() for c in codes)
    assert countries.name_for("IN") == "India"

def test_get_countries_route(client):  # TestClient over app, as in test_base_resume_role_category._client
    body = client.get("/api/countries").json()
    assert {"code": "GB", "name": "United Kingdom"} in body
```

- [ ] **Step 2: Run the tests and confirm they fail.** Run
  `pytest tests/test_countries.py -q`. Expected: ImportError.
- [ ] **Step 3: Write `countries.yaml`.**
  - Format: a mapping `CODE: English name`, holding all ISO 3166-1 alpha-2
    codes.
  - Use the short common names, e.g. `GB: United Kingdom`, `US: United States`,
    `KR: South Korea`.
  - The header comment names the source (ISO 3166-1) and says it is a
    vendored list, not a dependency.
- [ ] **Step 4: Write `countries.py`.** Copy `services/markets.py`'s pattern:
  `_DATA_FILE`, an `@lru_cache` `_load()`, and a casefolded name→code index
  built once. `normalize` is the only parser:
  - strip;
  - a 2-letter upper code that is in the list;
  - `UK`;
  - a casefolded name;
  - else None.
- [ ] **Step 5: Write `routers/countries.py`.** Copy `routers/role_categories.py`:
  prefix `/api/countries`, an inline `Country{code,name}` model, and
  `@router.get("")`. Register it in `main.py`.
- [ ] **Step 6: Run `pytest tests/test_countries.py -q`.** Expected: PASS.
- [ ] **Step 7: Commit:** `feat(countries): vendored ISO list, one normalizer, GET /api/countries`.

### Task 2: Anchor columns, identity PATCH, duplicate, `anchors()` and `base_anchors`

**Files:**
- Create: `backend/migrations/versions/<id>_base_resume_anchors.py`
- Modify: `backend/app/models/base_resume.py`
- Modify: `backend/app/models/tailoring_session.py`
- Modify: `backend/app/schemas/base_resume.py`, at l.9-21, l.24-56 and l.138-148
- Modify: `backend/app/schemas/tailoring_session.py:44-64`
- Modify: `backend/app/routers/base_resumes.py`: `_detail` l.164-195,
  identity l.565-608, duplicate l.749-756
- Modify: `backend/app/services/base_resume_data.py`
- Test: `backend/tests/test_base_resume_anchors.py`

**Interfaces:**
- Consumes: `countries.normalize` and `countries.is_valid` (Task 1).
- Produces:
  - **Columns:** `BaseResume.countries: list[str]` (NOT NULL, default `[]`),
    plus `company` and `focus`, both `str | None`.
  - **Anchors helper:**
    `base_resume_data.anchors(row: BaseResume | None) -> dict | None`.
    - It returns `{"countries": [...], "role": str | None, "company": str | None, "focus": str | None}`.
    - It returns None when the row is None, soft-deleted, or has all four
      empty.
    - `role` is `row.role_label`, else `role_categories.label_for(row.role_category)`.
      It is None when `role_category` is `unknown`, or `other` with no label.
  - **Session property:** `TailoringSession.base_anchors -> dict | None`. The
    model gets a viewonly relationship to `BaseResume` on
    `foreign(TailoringSession.base_resume) == BaseResume.slug`, plus
    `@property base_anchors` returning `anchors(self.base_row)`.
  - **Schema fields:**
    - `TailoringSessionRead.base_anchors: dict | None = None` (it reads the
      property through `from_attributes`);
    - `BaseResumeSummary` and `BaseResumeDetail` get
      `countries: list[str] = []`, `company`, `focus`;
    - `BaseResumeIdentity` gets `countries: list[str] | None`, `company`,
      `focus`.

- [ ] **Step 1: Write the failing tests.** They live in
  `tests/test_base_resume_anchors.py` and reuse `SAMPLE` and `_client` from
  `test_base_resume_role_category.py`.

```python
def test_identity_sets_normalizes_and_clears_anchors(db_session): ...
    # PATCH {"countries": ["in", "IN", "us"], "company": "  Example Corp ", "focus": "payments"}
    # → countries == ["IN", "US"], company == "Example Corp"
    # PATCH {"company": ""} → company is None, countries unchanged (omitted = unchanged)
    # PATCH {"countries": []} and {"countries": None} → []
def test_identity_rejects_bad_anchor_values(db_session):
    # {"countries": ["XX"]} → 422 "Unknown country code: XX."
    # {"focus": "x" * 81} → 422; nothing saved
def test_anchor_patch_leaves_role_and_document_alone(db_session):
    # role pair unchanged; no ResumeVersion row added; pdf_rendered_at unchanged
def test_role_patch_leaves_anchors_alone(db_session): ...
def test_duplicate_copies_anchors_once(db_session):
    # duplicate, then PATCH the copy's company → source unchanged
def test_anchors_helper(db_session):
    # all-empty row → None; role 'unknown' → role None; role_label wins over category label;
    # soft-deleted row → None
def test_session_read_carries_base_anchors(db_session):
    # TailoringSessionRead.model_validate(row).base_anchors == anchors(base); None after base soft-delete
def test_summary_and_detail_carry_anchors(db_session): ...
```

- [ ] **Step 2: Run them and confirm they fail.** Run
  `pytest tests/test_base_resume_anchors.py -q`.
- [ ] **Step 3: Write the migration.** It uses one
  `op.batch_alter_table("base_resumes")` and adds three columns:
  - `sa.Column("countries", sa.JSON(), server_default=sa.text("'[]'"), nullable=False)`;
  - `company` and `focus`, both `sa.Text()` and nullable.

  The downgrade drops all three. Copy the header form from
  `9a5744f9b9d9_application_proposals_proposed_by.py`.
- [ ] **Step 4: Add the model columns.** Match the migration exactly
  (`countries` follows `career_kb.tags_json`:
  `default=list, server_default=sa_text("'[]'")`). Add the viewonly
  relationship and the property. Add the schema fields.
  `_detail()` sets the three fields explicitly.
- [ ] **Step 5: Extend the identity PATCH.** Add an anchor branch beside the
  `display_name` branch. It is driven by `payload.model_fields_set` and has a
  helper `_validated_anchors(payload, fields) -> dict` that raises 422 with
  the user sentences above. The duplicate handler copies the three fields.
- [ ] **Step 6: Run the new tests and the parity tests.** Run
  `pytest tests/test_base_resume_anchors.py tests/test_migration_model_parity.py tests/test_base_resume_role_category.py -q`.
  Expected: PASS.
- [ ] **Step 7: Commit:** `feat(base-resumes): countries, company and focus anchors on the identity PATCH`.

### Task 3: Eligibility module and the scoring readers

**Files:**
- Create: `backend/app/services/base_eligibility.py`
- Modify: `backend/app/services/ats_score.py`: `score_all_bases` l.130,
  `best_base` l.158, `latest_scores` l.189
- Modify: `backend/app/services/explore_gaps.py:45-87`
- Modify: `backend/app/schemas/ats_score.py`: `AtsRunRequest` gains
  `include_other_countries: bool = False`; new
  `AtsCandidatesRead{job_country: str | None, fallback: bool, skipped: list[str]}`
- Modify: `backend/app/routers/ats.py`, at l.14-44
- Test: `backend/tests/test_base_eligibility.py`;
  `backend/tests/ats/test_ats_score_service.py` (add cases)

**Interfaces:**
- Consumes: `countries.normalize` (Task 1) and `BaseResume.countries` (Task 2).
- Produces, in `base_eligibility`:
  - `country_eligible(base_countries: list[str], job_country: str | None) -> bool`;
  - `@dataclass(frozen=True) Candidates(slugs: list[str], job_country: str | None, fallback: bool, skipped: list[str])`;
  - `candidates_for_country(session, job_country: str | None, *, include_other_countries: bool = False) -> Candidates`.
    It starts from `selectable_base_resume_slugs` and needs one query for the
    countries;
  - `candidates(session, job: Job, **kw) -> Candidates`, which normalizes
    `job.country`;
  - `is_eligible(session, job: Job, slug: str) -> bool`. It is True when that
    base's own countries pass `country_eligible`, or when
    `candidates(...).fallback` is set. It reads the row even if it is
    archived.
- Produces, in `ats_score`:
  - `score_all_bases(job_id, session=None, *, include_other_countries=False)`;
  - `latest_scores(job_id, session, *, include_other_countries=False)`.
- Produces, routes:
  - `GET /api/ats-scores?job_id=&include_other_countries=`;
  - `POST /api/ats-scores` with body `include_other_countries`;
  - `GET /api/ats-scores/candidates?job_id=` → `AtsCandidatesRead`.

- [ ] **Step 1: Write the failing tests**

```python
def test_country_eligible_table():
    assert country_eligible(["IN"], None) and country_eligible([], "US")
    assert country_eligible(["US", "CA"], "US") and not country_eligible(["IN"], "US")

def test_candidates_filters_and_falls_back(db_session):
    # bases: india[IN], us[US], anywhere[] ; job country "us"
    # → slugs == ["anywhere", "us"], skipped == ["india"], fallback False
    # only india[IN] selectable, job US → slugs == ["india"], fallback True, skipped == []
    # job country "Remote" → job_country None, all slugs, skipped []
    # include_other_countries=True → all slugs, skipped []

def test_is_eligible_uses_the_base_own_countries_even_when_archived(db_session): ...

# tests/ats/test_ats_score_service.py
def test_score_all_bases_skips_other_country_bases(...)
def test_latest_scores_hides_a_base_marked_for_another_country_after_scoring(...)
    # score india+us for a US job, then PATCH india countries=["IN"]
    # → default read has no india row; include_other_countries=True has it
def test_latest_scores_keeps_archived_and_deleted_rules(...)   # existing test still passes unchanged
def test_best_base_ignores_other_country_bases(...)
def test_best_base_gap_rows_never_pick_a_skipped_base(...)
def test_candidates_route(...)   # job_country, fallback, skipped per case
```

- [ ] **Step 2: Run the tests and confirm they fail.**
- [ ] **Step 3: Implement `base_eligibility.py`.**
- [ ] **Step 4: Wire the readers.**
  - `score_all_bases` iterates `candidates(...).slugs` instead of the selectable
    list. Keep the missing-file skip.
  - `latest_scores` loads the Job and also hides `candidates(...).skipped` for
    base rows. With no job, it does no country filtering.
  - `best_base` restricts rows to `candidates(...).slugs`.
  - `_best_base_gap_rows` also selects `Job.country` and drops rows whose
    target is in `candidates_for_country(...).skipped`, memoized per
    normalized country. It adds no other filter; its archived and deleted
    behaviour is unchanged.
  - The router passes the flag through and adds the candidates route.
- [ ] **Step 5: Run the tests.** Run
  `pytest tests/test_base_eligibility.py tests/ats/ tests/test_explore*.py -q`.
  Expected: PASS.
- [ ] **Step 6: Commit:** `feat(scoring): bases for other countries are not scored or recommended`.

### Task 4: Readiness and final review (the auto-submit gate)

**Files:**
- Modify: `backend/app/services/inbox_readiness.py`: `is_ready`, `_Batch`,
  and the module docstring
- Modify: `backend/app/schemas/proposal.py:77-82` (`ProposalReadiness`)
- Modify: `backend/app/services/proposals.py:345-430` (`get_final_review`)
- Modify: `frontend/lib/inbox-readiness.ts`
- Test: `backend/tests/test_inbox_readiness.py`,
  `backend/tests/test_proposal_state_machine.py` (final review cases),
  `frontend/lib/inbox-readiness.test.ts`. No pytest runs that file today, so
  add `test_inbox_readiness_node()` to
  `backend/tests/test_frontend_agent_dashboard.py`, calling
  `run_node_test("lib/inbox-readiness.test.ts")` as l.115 does for
  `inbox-visit`.

**Interfaces:**
- Consumes: `base_eligibility.is_eligible` and `candidates_for_country`
  (Task 3), `countries.normalize` (Task 1).
- Produces:
  - **Readiness key:** each row gains `base_country: str | None`. It is the
    job's normalized country when the linked application's `base_resume` is
    not eligible, else None. It is None with no application or no job
    country.
  - **Ready rule:** `is_ready` additionally requires
    `readiness.get("base_country") is None`.
  - **Schema:** `ProposalReadiness.base_country: str | None = None`.
  - **Final review:** gains top-level
    `"base_country": {"job_country": str | None, "base": str, "eligible": bool} | None`.
    The base is the linked application's base, else `fit.chosen_base`, else
    None.
  - **TS twin:** `Readiness.base_country?: string | null`. `isReady` also
    needs `r.base_country == null`. `readinessMarks` pushes
    `{text: "Resume for another country", tone: "warning"}`.

- [ ] **Step 1: Write the failing tests**

```python
def test_base_for_another_country_is_marked_and_not_ready(db_session):
    # job country "US"; application on base india[IN]; another selectable base us[US]
    # → readiness["base_country"] == "US"; is_ready(readiness) is False even with pdf, no knockout, 0 to check
def test_fallback_base_is_not_marked(db_session):
    # only base india[IN], job US → base_country None
def test_archived_base_judged_by_its_own_countries(db_session): ...
def test_no_job_country_no_mark(db_session): ...
def test_readiness_batch_reads_base_countries_once(db_session):  # one query for all rows, mirror scan_args batching
def test_final_review_reports_base_country_for_the_sent_base(db_session):
    # application base wins over fit.chosen_base; stale chosen_base for another country → eligible False
    # no application and no chosen_base → base_country None
```

TS, in `frontend/lib/inbox-readiness.test.ts`:
`isReady({tailored: true, knockout: null, to_check: 0, base_country: "US"}) === false`.
A missing key still reads ready. The mark text is "Resume for another country".

- [ ] **Step 2: Run the tests and confirm they fail.**
- [ ] **Step 3: Implement.**
  - `_Batch` loads `{application_id: base_resume}` and that base's countries
    in one query each.
  - It memoizes `candidates_for_country(...).fallback` per job country.
  - Update the docstring: "Ready means tailored, no knock-out conflict, the
    resume is set for the job's country, and nothing to check."
- [ ] **Step 4: Run the tests.** Run
  `pytest tests/test_inbox_readiness.py tests/test_inbox_summary.py tests/test_proposal_state_machine.py tests/test_frontend_agent_inbox.py tests/test_frontend_agent_dashboard.py -q`.
  Expected: PASS.
- [ ] **Step 5: Commit:** `feat(inbox): a resume for another country is never ready to send`.

### Task 5: The anchor line in tailoring and Ask for changes

**Files:**
- Modify: `backend/app/services/prompt_assembly.py`, beside `_persona_block`
  l.43
- Modify: `build_gap_tailor_prompt` l.84-117
- Modify: `backend/app/services/tailoring_session.py:1237-1262`
  (`_llm_customized`)
- Modify: `backend/app/services/base_resume_instruct.py`: `_ask` l.45 and
  `propose` l.97
- Test: `backend/tests/test_prompt_anchor_line.py`,
  `backend/tests/test_base_resume_instruct.py`,
  `backend/tests/test_tailoring_sessions_router.py`

**Interfaces:**
- Consumes: `base_resume_data.anchors` (Task 2) and `countries.name_for`
  (Task 1).
- Produces:
  - `prompt_assembly.anchor_block(anchors: dict | None, *, for_job: bool) -> str`;
  - `build_gap_tailor_prompt(..., anchors: dict | None = None)`;
  - `base_resume_instruct._ask(session, instruction, resume, correction, anchors=None)`.

- [ ] **Step 1: Write the failing tests**

```python
def test_anchor_block_empty_and_listed():
    assert anchor_block(None, for_job=True) == ""
    text = anchor_block({"countries": ["IN"], "role": "Data Engineer",
                         "company": "Example Corp", "focus": None}, for_job=False)
    assert text.startswith("RESUME ANCHORS: Countries: India · Role: Data Engineer · Company: Example Corp\n")
    assert "Focus" not in text and "not this application's employer" not in text
    assert "The anchor company is not this application's employer." in anchor_block(
        {"countries": [], "role": None, "company": "Example Bank", "focus": None}, for_job=True)

def test_anchor_text_stays_literal():   # company "$role_label ${x}" appears verbatim
def test_gap_tailor_prompt_without_anchors_is_unchanged():
    # build_gap_tailor_prompt(...) == build_gap_tailor_prompt(..., anchors=None) == today's string (golden from current code)
def test_tailor_sends_the_anchor_line(...)      # fake llm.call_openai, capture prompt, assert "RESUME ANCHORS:" and employer clause
def test_ask_for_changes_sends_the_anchor_line(...)  # same, no employer clause
def test_ask_for_changes_without_anchors_is_unchanged(...)
```

- [ ] **Step 2: Run the tests and confirm they fail.**
- [ ] **Step 3: Implement.** The block, with exact copy from the spec:
  - line 1: `RESUME ANCHORS: ` followed by the set anchors, joined with ` · `, in
    the order Countries, Role, Company, Focus. Countries are names, joined
    with `, `;
  - line 2: `Emphasize these where relevant. They are not evidence of experience.`;
  - when `for_job`, append ` The anchor company is not this application's employer.`
    to line 2, but only if `company` is set;
  - end with `\n\n---\n\n`.

  Prepend it after `_persona_block` in the gap prompt. In `_ask`, prepend it
  to the substituted template text. `propose` passes `anchors(row)`.
  `_llm_customized` passes
  `anchors=base_resume_data.anchors(session.get(BaseResume, tailoring.base_resume))`.
  `anchors()` already returns None for a missing or soft-deleted row.
- [ ] **Step 4: Run the tests.** Run
  `pytest tests/test_prompt_anchor_line.py tests/test_base_resume_instruct.py tests/test_tailoring_sessions_router.py tests/test_quick_tailor.py -q`.
  Expected: PASS.
- [ ] **Step 5: Commit:** `feat(prompts): tailoring and Ask for changes read the resume's anchors`.

### Task 6: MCP, agent brief and the tailor-run skill

**Files:**
- Modify: `backend/mcp_server/server.py`:
  - new tool near `update_base_resume` l.852;
  - `score_ats` l.1421-1476;
  - `create_tailoring_session` l.1488 and `get_tailoring_session` l.1595
    docstrings.
- Modify: `backend/mcp_server/client.py`: `score_ats` l.1081, plus new
  `set_base_resume_identity` and `ats_candidates` methods.
- Modify: `backend/mcp_server/tests/test_server.py`: the subset assert in
  `test_all_tools_registered` l.21-79, and `_PINNED_HINTS` l.1165.
- Modify: `backend/app/services/explore_base_summaries.py`: each row gains
  `anchors`.
- Modify: `backend/app/automations/skills/tailor-run/SKILL.md`, step 2 at
  l.25-26.
- Modify the tool count, "85 tools" → "86 tools", in:
  - SYSTEM.md:118
  - README.md:52,130,453
  - backend/mcp_server/README.md:24
  - mcpb/manifest.json:53
  - KNOWN_ISSUES.md:29
  - plugins/maestro-career-studio/README.md:84
- Test: `backend/mcp_server/tests/test_client_write.py`,
  `backend/mcp_server/tests/test_server.py`,
  `backend/tests/test_automations_service.py`,
  `backend/tests/test_explore*.py`

**Interfaces:**
- Consumes: the identity PATCH (Task 2) and `/api/ats-scores/candidates`
  (Task 3).
- Produces:
  - **New tool:**
    `set_base_resume_identity(slug: str, display_name: str | None = None, role_category: str | None = None, role_label: str | None = None, countries: list[str] | None = None, company: str | None = None, focus: str | None = None)`.
    - `None` means not sent. `""` clears company or focus, and `[]` clears
      countries.
    - Registered with `**_write(title="Set resume target", destructive=False, idempotent=True)`.
    - Full profile only: it is added to no allowlist in `profiles.py`.
  - **`score_ats`:** gains `include_other_countries: bool = False`. It returns
    `{scores, recommendation, countries: {job_country, fallback, skipped}, next}`.
    The `countries` block is omitted when a `target_id` is given.

- [ ] **Step 1: Write the failing tests**
  - **Subset assert:** includes `set_base_resume_identity`, and
    `_PINNED_HINTS` gains `(False, False, True, False)`.
  - **respx:** the identity tool sends only supplied keys. `company=""` is
    sent as `""`; `countries=[]` is sent as `[]`.
  - **`score_ats` forwarding:** it forwards `include_other_countries` only when
    true, and returns the `countries` block from the candidates GET.
  - **Docstring budget:** the existing test passes.
  - **Base summaries:** rows carry `anchors`.
  - **Automations:** a new param case asserts the tailor-run text contains
    "only while it is still among `score_ats`'s scores".
- [ ] **Step 2: Run the tests and confirm they fail.**
- [ ] **Step 3: Implement.**
  - **Identity tool docstring** (about 600 chars, fact-voiced): what each anchor
    does, that countries restrict which jobs the resume is scored for, the
    clear values, and that it never edits resume content.
  - **`score_ats` docstring:** add one sentence. "Bases set for other countries
    are not scored for this job unless `include_other_countries` is true; the
    `countries` block names them."
  - **Session tool docstrings:** add one sentence to both. "`base_anchors` are
    the base's emphasis hints (countries, role, company, focus), not evidence;
    the anchor company is not this application's employer."
  - **tailor-run step 2:** reword it to "Use `fit_json.chosen_base` only while
    it is still among `score_ats(job_id)`'s scores; otherwise take
    `recommended`; on a `close_call`, leave the job for the digest."
- [ ] **Step 4: Run the tests.** Run
  `pytest mcp_server/tests/ tests/test_automations_service.py tests/test_automations_router.py tests/test_explore*.py -q`.
  Expected: PASS. Then run `grep -rn "85 tools" . --include=*.md --include=*.json`.
  Expected: no hits.
- [ ] **Step 5: Commit:** `feat(mcp): set a resume's target; score_ats names bases skipped for country`.

### Task 7: Frontend: Target dialog, pills and the score panel

**Files:**
- Modify: `frontend/lib/types.ts`:
  - `BaseResumeSummary` l.485-500 gains `countries: string[]`,
    `company: string | null`, `focus: string | null`;
  - new `AtsCandidates`.
- Modify: `frontend/lib/api.ts` l.155-188: `runAtsScores(jobId, opts?)` and
  `listAtsScores(jobId, opts?)` take `{includeOtherCountries?: boolean}`, and
  there is a new `getAtsCandidates(jobId)`.
- Create: `frontend/components/country-picker.tsx`
- Create: `frontend/components/base-resumes/anchor-pills.tsx`
- Modify: `frontend/components/role-category-picker.tsx:197-241`
  (`RoleCategoryDialog` becomes the Target dialog)
- Modify: `frontend/components/resume-editor/editor-body.tsx:416-424`, where
  the menu label reads "Target"
- Modify: `frontend/components/base-resumes/base-resume-gallery.tsx:55-69`
- Modify: `frontend/components/ats-score-panel.tsx`: the query keys at
  l.329-375, the cards at l.217-237, and the skipped and fallback line at
  l.579-585
- Modify: `frontend/lib/ats-words.ts`
- Modify: `docs/frontend-conventions.md`, Canonical terms (l.1215-1306)
- Test: `backend/tests/test_frontend_base_resume_anchors.py` (a source-scan
  pytest, in the style of `test_frontend_agent_inbox.py`); the existing
  `test_frontend_*` suites.

**Interfaces:**
- Consumes:
  - `GET /api/countries`;
  - the identity PATCH;
  - the `include_other_countries` query and body flags;
  - `GET /api/ats-scores/candidates`.
- Produces:
  - `<CountryPicker value: string[] onChange(codes) disabled? aria-label />`;
  - `<AnchorPills resume: BaseResumeSummary />`, which renders nothing when all
    four anchors are empty;
  - in `ats-words.ts`: `skippedCountriesLine(n: number, country: string): string`
    and `noResumeForCountry(country: string): string`.

- [ ] **Step 1: Write the failing source-scan tests**
  - The dialog title is "Target". The four labels in order are Countries, Role,
    Company, Focus.
  - The Focus hint is "Such as payments platforms.", wired with
    `aria-describedby`. The Company and Focus inputs have no `placeholder=`.
  - The help text is "Used when tailoring or asking for changes. Saving here
    does not change the resume."
  - `CountryPicker` has a named input (`aria-label`) and is `readOnly` while
    saving. That matches the `test_frontend_placeholders.py` and
    `test_frontend_focus.py` rules.
  - The score panel's query key is
    `["ats-scores", jobId, { includeOtherCountries }]`. The candidates key is
    `["ats-scores", jobId, "candidates"]`.
  - `skippedCountriesLine(2, "United States")` returns "2 resumes for other
    countries weren't scored for this United States job." The link text is
    "Score them anyway".
  - `noResumeForCountry("United States")` returns "None of your resumes is set
    for United States."
- [ ] **Step 2: Run them and confirm they fail.** Run
  `pytest tests/test_frontend_base_resume_anchors.py -q`.
- [ ] **Step 3: Build `CountryPicker`.** Model it on `RolePicker`'s `multiple`
  branch (`role-picker.tsx:362-417, 425-472, 530-572`), with flat items and no
  custom-add. It reads `GET /api/countries` with a long `staleTime`, as
  `useRoleCategories` does.
- [ ] **Step 4: Build the Target dialog.**
  - It keeps the existing role picker.
  - Countries PATCH on change.
  - Company and Focus PATCH on blur when their value changed. Each PATCH sends
    only the changed key.
  - On success, update and invalidate the same queries as today (l.111-131).
  - Keep the existing `finalFocus` contract.
- [ ] **Step 5: Add `AnchorPills`.**
  - Use `Badge variant="secondary"`.
  - Countries show as codes, with `countryName` from `lib/place-name.ts` in
    `title`.
  - Show it in the gallery meta row and under the score card title.
- [ ] **Step 6: Update the score panel.**
  - Query the candidates.
  - When `skipped.length`, render `skippedCountriesLine` plus a
    "Score them anyway" button as one `text-body-small text-muted-foreground`
    line. The button re-runs and re-reads with `includeOtherCountries: true`
    for that view.
  - When `fallback`, render `noResumeForCountry`.
  - Prefix invalidations stay unchanged.
- [ ] **Step 7: Register the term.** Add **Target** to Canonical terms ("the
  base resume's dialog for countries, role, company and focus; anchors is the
  agent and code word, never on screen").
- [ ] **Step 8: Run the frontend checks.** Run
  `pytest tests/test_frontend_*.py -q` from `backend/`, then
  `cd frontend && npx tsc --noEmit && npm run build`. Expected: all pass.
- [ ] **Step 9: Verify in a fresh dev stack** (SYSTEM.md §9, not compose):
  1. Copy a base and set its countries to India.
  2. Score a job whose country is US.
  3. Check the skipped line, then "Score them anyway".
  4. Check the pills on the gallery and score cards.
- [ ] **Step 10: Commit:** `feat(web): Target dialog with countries, company and focus; skipped-for-country line`.

### Task 8: Docs and gates

**Files:**
- Modify: `docs/entities/others.md`, the BaseResume bullet l.5-63, adding:
  - the anchors and their write path;
  - the eligibility rule and its readers;
  - the two prompt readers.
- Modify: `docs/entities/agent-runs.md:64` and `docs/entities/others.md:607`,
  where the readiness rule gains the country condition.
- Modify: `UBIQUITOUS_LANGUAGE.md`: an **Anchor** row in the Resume artifacts
  table (l.25-35), and the relationship line at l.110.
- Modify: `SYSTEM.md`, as in-place rewords with no net line growth:
  - §5 step 4 (l.184-189): "auto-scores the bases set for the job's country
    (all when unknown)";
  - the §7 base-resumes sentence (l.483-486): name `set_base_resume_identity`;
  - §12's transient attrs line (l.917): add `base_anchors` as a model property,
    never a column.

- [ ] **Step 1: Make the edits.**
- [ ] **Step 2: Run the docs check.** Run `python3 scripts/check_system_md.py`.
  Expected: OK at ≤1000 lines.
- [ ] **Step 3: Run the full backend suite.** Run
  `pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile` from `backend/`.
  Expected: PASS.
- [ ] **Step 4: Run the maintainer slop scan if it is available.** Run
  `python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check backend`,
  then the same for `frontend` and `extension`. Name each surface in the
  result. If the skill is absent, say so rather than claiming a pass.
- [ ] **Step 5: Commit:** `docs: base resume anchors in SYSTEM.md, entities and glossary`.
