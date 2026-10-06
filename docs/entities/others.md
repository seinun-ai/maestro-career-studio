# Others

> Reference tier, extracted from [SYSTEM.md](../../SYSTEM.md) (§4 Core entities). The header contract there governs this file too: integrate don't append, present tense, no dates outside the ledgers, update in the same change that alters the behaviour described.

- **BaseResume**: DB row + `base_resumes/<slug>.json` on disk; soft-deleted
  rows still serve on GET-by-slug but are excluded from lists. Renders like
  applications do. **Archive** (`archived_at`) is a SEPARATE axis from
  `deleted_at`: it hides a stale career track from every place you PICK one,
  and is meant to be undone (`POST …/archive` · `/unarchive`;
  `?include_archived=true` opts back in). **The invariant: archive removes a
  base from MENUS, never from the SYSTEM** — editor, version history, PDF and
  referencing applications keep working. Hence `base_resume_data`'s TWO
  predicates, never to be merged: `active_filter()` (not deleted) is the
  RESOLUTION gate — behind `active_base_resume_slugs` and `load_base_resume` —
  and `selectable_filter()` (not deleted, not archived) is the CHOICE set;
  filtering archived rows out of the former would 404 an archived resume's own
  editor. Every direct table query COMPOSES these (or a `not_()` inverse:
  `ats_score.latest_scores`, explore's deleted-slugs subquery) — the predicate
  is defined once. The ONE list query behind the pickers is
  `GET /api/base-resumes` (web grid, five in-app selectors, extension dock,
  MCP `list_base_resumes`). Score rows outlive the base they scored;
  `latest_scores` filters only `base_resume` targets, never `application` ones.
  **`role_category`** (NOT NULL, default `'unknown'`) is the role the resume
  targets, drawn from the SAME 25-family, industry-wide vocabulary as
  `Job.role_category` (`services/role_categories` ←
  `ats/data/role_categories.yaml`), so the axes cross-tab with `=`. The family
  expansion is additive: existing keys remain stable. Optional one-line
  descriptions clarify ambiguous/emerging families; nested roles are
  picker/search aliases only, never storable or in `adjacent:`.
  **`role_label`** (nullable) holds a free-text tag's words, `role_category`
  becoming its projection — mapping, `other` if unmapped, `unknown` untagged
  (still the visible "Role not set" state). Catalog text typed verbatim
  collapses to the pick; coverage matches free-text tags to free-text favored
  roles by casefolded label with an alias bridge. Insert sites: REST create
  (**422** on invalid or contradicting explicit values), duplicate (**inherits
  the pair**), seeding (a slug that IS a category key), `POST /import` (one
  uploaded file → the KB import's parse half, `extract_text` →
  `kb_consolidation.parse_resume_text`, JSON validated as-is → the SAME create
  pipeline; the user's `display_name`/`slug`/role win, else the file stem
  names it and a free slug is derived; **writes nothing to the Career KB** —
  that is `POST /api/kb/import`'s job — and returns `parse_warnings` for
  salvaged rows; the "From file" tab of the New base resume dialog), and
  `POST /from-kb`. **Instruction → proposal**: `POST /{slug}/propose`
  (`services/base_resume_instruct`, prompt `base_resume_instruct`) turns a free
  instruction into `{summary, notes, ops}` — ops validated against the op
  schema AND dry-run with `apply_edits` before they reach the client, one
  corrective retry, then 422; an ideas/question instruction answers in `notes`
  with empty ops. Persists nothing; the editor's "Ask for changes" sheet applies
  through `PATCH /edits` like every other surface, so it is disabled while the
  form holds unsaved edits (the KB-import rule). Human input is
  VALIDATED, never `normalize()`d (its unrecognized→`other` is right for LLM
  extraction, wrong for a typo). Deliberately no required create field: the documented onboarding path
  drops JSON into `base_resumes/` and reaches `seeding.py` without touching the
  API, so a REST-only validator would not hold. `PATCH
  /api/base-resumes/{slug}/identity` sets role/display_name and the anchors below WITHOUT rewriting
  `data_json`, recording a version, rewriting the disk file, or recompiling the
  PDF — unlike the full PUT. Artifact filenames resolve their role label from
  this column (`base_resume_data.declared_role` →
  `role_titles.generic_role_title`), never from the slug. No slug is reserved
  (the pre-KB `master` profile is gone): every base resume is listable,
  editable, portable and tailorable. `last_kb_synced_at` stamps the last
  successful one-click base→KB sync (`GET/POST
  /api/base-resumes/{slug}/kb-sync-status` / `kb-sync`; MCP `kb_sync_base`; on
  screen the studio's **Add to career history (N)** pill and its **Add now**).

  **Anchors** say what a base is written for: `countries` (upper-case ISO 3166-1 codes, NOT NULL,
  default `[]` = anywhere), `company` and `focus` (free text, at most 80 characters), plus the role pair
  above. They are written ONLY by `PATCH /api/base-resumes/{slug}/identity` (MCP
  `set_base_resume_identity`): an omitted field is unchanged, `null`/`""`/`[]` clear, and every value is
  validated before any lands, so a 422 saves none. `services/countries.normalize` is the one parser
  (codes in any case, English short names with or without accents, and common variants such as "UK",
  "USA", "Holland", "Ivory Coast" and "Viet Nam"; anything else is unknown); the list is vendored in
  `services/data/countries.yaml` and served by `GET /api/countries`. Create, import, `from-kb`, PUT and
  edits never take anchors; duplicate copies `countries`, `company` and `focus` once, like the role pair.
  Anchors are metadata like role: no ResumeVersion, no disk rewrite, no render, no score change.
  `base_resume_data.anchors(row)` returns `{countries, role, company, focus}` (role is `role_label`, else
  the category's label, null when undeclared) or null for no row, a soft-deleted row or all four empty;
  it feeds `TailoringSession.base_anchors` (a model property over a viewonly `base_row`, on every session
  response, null for a soft-deleted base) and the base summaries in the hunt brief (`anchors`).
  **Only countries decide anything.** `services/base_eligibility.py` owns the rule: a job whose country
  is unknown (`countries.normalize` finds no code, "Remote" included) keeps every selectable base; a
  known country keeps the bases listing it plus those with no countries; when none qualify every
  selectable base stays and `fallback` is true; `include_other_countries` keeps all.
  `candidates`/`candidates_for_country` return `slugs`, `job_country`, `fallback` and `skipped` (the
  selectable bases the country dropped). Readers drop only `skipped`: `ats_score.score_all_bases`,
  `latest_scores` and `best_base`, `explore_gaps._best_base_gap_rows`, `GET /api/ats-scores/candidates`
  and the `include_other_countries` flag on GET/POST `/api/ats-scores`. `is_eligible(job, slug)` (own
  countries pass, OR fallback, OR no row; an unknown job country passes) gates final review's
  `base_country`, and inbox readiness applies the same rule batched; both call `eligible_given`.
  Role, company and focus never filter or rank. Two prompts read the anchors,
  as a `RESUME ANCHORS` line from `prompt_assembly.anchor_block` placed after the persona: gap tailoring
  (the job variant adds that the anchor company is the resume's own target and may differ from the employer) and Ask for changes
  (`base_resume_instruct`). They are emphasis hints, never evidence; with none set both prompts are
  unchanged.
- **Resume edit ops** are one source (`schemas/resume_edit.py`: a 16-kind discriminated union with
  `op_kinds()` / `op_scope()` / `render_ops_brief()` / `render_ops_shapes()`); chat imports those, MCP builds
  `edit_base_resume` from `render_ops_shapes()` at import, and `test_resume_edit_reference.py` holds the
  parity. Only the extras payload stays loosely typed (SYSTEM.md §11 item 1).
- **ResumeData `extra_sections`** (on screen **Other sections**): the resume is fixed core
  (contact/summary/skills/experience/projects/education/certifications) PLUS an
  ordered `extra_sections` list — a discriminated union on `type`: `entries`
  (structured) or `bullets` (flat); never both. Two core fields are optional by
  design: `ExperienceEntry.start_date` and `EducationEntry.degree` — an undated
  role earns no recency credit, fails no S3 gate, and enters no employment-gap
  math (only a non-empty unparseable date is a defect); both bundled templates
  guard the empty cases. The canonical common-section vocabulary (publications,
  licenses, clearance, …) is `services/extra_section_presets.py` — the ONE
  catalog, substituted into the `kb_resume_parse` prompt as
  `$extra_section_presets` BEFORE `$resume_text` (resume text is data and must
  not be able to inject the catalog position; order pinned by test). `key` is the stable slug
  identity (references pass `section_key`; unique case-insensitively; must not
  shadow a core field name), `title` is editable display text; list order is
  render order. Every write path normalizes through `ResumeData` so base PUT,
  application PATCH, and typed edits store identical canonical JSON (unknown
  keys dropped; missing `extra_sections` reads as `[]`). Typed ops:
  add/replace/remove/move_extra_section (replace may not change the key;
  entry/bullet ops are deferred behind op consolidation). Rendered after
  Projects, before Technical Skills; a template whose source never references
  `resume.extra_sections` HARD-FAILS an extras-bearing render (never silently
  drops content), gated by the certification report's
  `extra_sections_supported` flag. **ATS/gap semantics:** enabled headings,
  subheadings, and bullets enter `ResumeIndex.entries` as the `extra_only`
  evidence tier (YAML `0.8`, deliberately conservative and uncalibrated);
  dates, section titles, locations, and links do not. Extra evidence may
  affect lexical, semantic, placement, responsibility-coverage, and
  skills-item corroboration scoring — never recent role, employment years,
  date recency, or section-presence checks. Disabled sections/entries
  contribute nothing. Gap placement identifies extras by stable `section_key`;
  entry sections add the original entry index, bullet sections use the key as
  their section-level sentinel.
- **Template**: resume templates with `default_formatting` and an `engine`
  column (`'latex'` default | `'typst'`, **immutable after creation** — 400 on
  change); status draft→ready via validation, which dispatches by engine but
  runs the SAME pdfplumber certification gate on the produced PDF; the validate
  response and `TemplateDetail.parse_report` carry the full probe report
  (`missing`, `headers_missing`, `extra_sections_supported/missing`) so a
  failing gate is actionable through web, chat, and MCP alike. LaTeX:
  Jinja source → pdflatex subprocess (incl. the interword-space pre-input).
  Typst: the `source` IS the .typ text — no Jinja/escape layer; data flows via
  typst-py `sys_inputs` as JSON strings, compile is in-process,
  `fmt.date_format` applied server-side before serialization. Either way the
  source artifact is written beside the PDF, `tex_path` stores whichever the
  engine produced, and compile errors surface through the same RuntimeError
  contract. `template_id` persists per base resume AND per application; render
  falls back tolerantly when stale. Formatting is a 4-layer merge: template
  default ← base-resume partial ← application partial ← render call. Bundled
  templates render a non-empty start plus blank end as `Present` without
  mutating resume JSON. Untouched stored seed sources are resynced at seed time
  (`template_registry.SUPERSEDED_SEED_DIGESTS`, every boot); the pre-SQLite
  chain's migration `c84a19d2e7f0` did it once, before v0.5.0 removed that chain.
  `ResumeFormatting` has 14 knobs. The newest is **`section_order`**
  (`list[str] | None`): every bundled template defines its own native list and
  dispatches through it, so **absent/None = that template's order, byte-for-byte
  what it rendered before the knob existed**. A partial list orders its members
  first and the template APPENDS its remaining native sections — the rule that
  stops a stale stored list from silently dropping a section. Order is
  presentation: `ResumeData` and stored resumes are untouched. Tokens are
  `summary, experience, projects, extra_sections, skills, education,
  certifications`; a template simply omits from its native list what it does not
  render standalone (`certifications` is a section only in harshibar, which
  therefore ships an explicit `default_formatting.section_order`; carlito has no
  extras block). **Render is tolerant and the WRITE GATE is strict**: the model's
  field validator silently drops unknown/duplicate tokens so stored data written
  by another version still renders, while `validate_formatting` rejects them
  (400, the same as any invalid override) so a typo cannot be saved. Extras keep
  their documented anchor as a *default* position; `section_order` moves the
  whole extras run, `move_extra_section` orders them among themselves.
  The four live user templates are bundled at
  `app/templates/user/`; `scripts/apply_template_sources` is their update
  path, and seed-time `SUPERSEDED_SEED_DIGESTS` is what reaches installed
  rows.
  **Pre-change template sources are frozen per migration** at
  `tests/fixtures/templates_pre_section_order/`: reconstructing old bytes from
  the LIVE templates (what the date-resync test did) breaks on the next template
  edit, and did. Engine migration state: **§13** `typst-default-flip` /
  `latex-render-path` / `texlive-layer`.
- **QAEntry**: per-application Q&A / cover letter rows (+ PDFs).
- **Model settings** (`services/model_settings.py`, `services/llm_capabilities.py`; on screen Settings ›
  AI & models, roles Fast, Smart and Assistant): the catalog is seeds ∪ extras (`MODEL_OPTIONS` ∪
  `llm.extra_models`); `GET /api/settings/openai` returns the merge, and deleting an id a role still uses is
  400. Capabilities are probed on Test and stored per model; `require()` blocks only on a stored No, so an
  unprobed model passes (the Assistant is gated on tools this way). JSON mode is capability-gated:
  `response_format=json_object` goes out only when `llm._json_mode_supported()` (other servers may hard-400
  on the field), and `llm._extract_json_object` salvages fenced JSON.
- **Form-filling engines (`/choose`)**: two engines, `fast` and `jev` (`llm.autofill_engine`, Settings › AI & models › **Form filling**,
  `GET/PUT /api/settings/jev` + `/jev/probe`; `jev` only while a Jev key exists; a new endpoint HOST
  forgets the key, which is never sent to another company). `fast` is the batched prompt SYSTEM.md §7 (Guided
  fill) describes. `jev`
  (`autofill_choose._choose_with_jev`): one Jev call maps each field's LABEL to an `autofill_slots`
  slot (no values sent), code reads the value, a second call picks the option that states it; the
  slot's policy (`exact` work_auth/eligibility/eeo/a language's name, `flag` `_FLAG_SECTIONS` facts,
  `any` the rest) makes it `matched`, `closest` (flag only, never from a list at the 30-option cap:
  written, then named in the finished note and listed under **Closest matches to check**) or abstain.
  Free-text, unmapped, shakily-mapped (an `exact` slot maps only at its write floor), `exact`-slot
  text boxes (codes) and failed-call fields go to the fast prompt unchanged; if THAT fails, Jev's
  answers are kept. `jev.choice_of` accepts only a distribution over exactly the offered keys (choice
  offered and most probable, every key present, numbers in [0, 1], sum ≈ 1) — anything else places
  nothing. Options are offered under code-owned keys (`o1…`, `none`), never page text, and every
  question says page text is data. One pooled `httpx.Client` serves every call (a TLS handshake per
  call costs about Jev's whole answer); 429/503/529 retry with doubling backoff inside the 2 s budget.
- **Persona draft** (`POST /api/settings/persona/draft`): one smart-model proposal grounded in the whole-KB
  compose/context + typed job preferences. Returns `{draft}` and persists **nothing** — Profile puts it into the
  persona editor as a dirty edit; only `PUT /api/settings/persona` saves; an empty Career KB 422s with an
  import-first message.
- **In-app chat: pinned-resume resolution** (SYSTEM.md §7): the pin is a HINT, not a guard — it reaches the model as one line of the
  ephemeral context block; the enforced guard is `check_ops_in_scope` over selection PATHS (which needs a
  pin only because the scope picker is fed the pinned resume). The composer resolves it once per session —
  session `context_json.target_key` if stored, else the most recently updated base resume — and must READ
  `context_json` back on reopen, not only write it on send (write-only silently dropped the pin). The pin
  FOLLOWS whichever base actually changed via both landing paths: the streamed `change_card` and an applied
  `propose_edits` card (which PATCHes directly and emits no stream event — `EditProposalCard` takes
  `onApplied`). Selections drop on a real switch: they are paths into the resume they came from.
- **Setup status** (`GET /api/setup/status`): a derived, **read-only**
  six-step onboarding view — no wizard-progress state; guidance is
  dismissible and recomputed from existing data (the `FirstRunImportCard`
  doctrine). Its service uses non-mutating `peek_*` reads, so a status request
  never lazy-seeds a Setting row or file mirror. The steps span three surfaces
  — `model_key` → Settings' AI & models tab (`#api-keys`), `import_resumes` →
  `/career`, autofill/job-preferences/persona → Profile's Autofill and About you
  tabs, `template` → `/templates` (the template step's detail names the default
  as `default_template_name`); a link into Settings or Profile goes through
  `lib/settings-tabs.ts` `anchorHref`, which picks the tab that holds the anchor;
  readiness is app-wide, not Profile-scoped. `model_key` is `bool(stored key or
  env key)` for either provider: whether a key WORKS is what the capability
  probe answers, and storing that verdict would break the derived-only rule. Autofill readiness spans the
  required personal, work-auth, EEO, and preferences groups and means
  **answerable**, not merely filled: `decline` is an answer, optional fields
  are excluded. Work authorization reads typed `WorkAuth`; its four-answer
  knockout core is `status`, `authorized_now`, `sponsorship_now`,
  `sponsorship_future` — status never implies current authorization, and an
  incomplete core is blocking. The backend's required field lists deliberately
  hand-mirror the frontend autofill groups; update both sides together —
  `tests/test_autofill_groups_parity.py` fails when they drift, per the §11
  rule that cross-boundary duplication needs a contract test, not a deletion.
- **`job_preferences` setting**: fully typed, file-mirrored at
  `settings/job_preferences.json` (`GET/PUT /api/settings/job-preferences`):
  `favored_roles` (a catalog key, coarse OR specific, or free text),
  `years_experience` (one number, comparable to extracted JD year bounds),
  employment types, locations, remote, salary, notes. Catalog labels are
  DERIVED and **`role_categories` is a COMPUTED PROJECTION** of the parents, so
  consumers needed no change. Writes 422 invalid keys, never `normalize()`ing
  them; reads degrade a stale favored-role per item to label-preserving free
  text (or skip it when no usable label exists), preserving every other valid
  preference field. Setup status uses it for missing-role suggestions (an
  unmapped custom role drives none); persona drafting uses it as a goals signal.
- **Career KB** (`models/career_kb.py`, `/career` pages; on screen **Career history**, its entities
  **items** and its points **bullets**): the durable record
  of experience/projects/education/certs + facts; deliberately a sidecar —
  tailoring does NOT read KB context. Its web UI is view-first: profile/entity
  metadata, points, and notes render as readable content until an on-demand
  editor is opened; status/state changes remain available through compact
  inline chips. **Document-first entity creation**: `POST
  /api/kb/documents/ingest` (multipart, no entity id) — one smart-model call
  (`kb_document_ingest` prompt) matches an existing entity or proposes a new
  one (new entities default status `completed`), stores the document via the
  shared `kb_ingest.store_document` helper, and mints draft points in the same
  call. 422 when no text extracts (no orphan rows), 400 bad LLM output, 502
  provider outage. UI: the Quick capture card is dual-intake. **Vision fallback
  for image-based documents**: certificate PDFs are often one full-page raster
  whose only text layer is the recipient's name (which once minted an
  `experience` entity titled with the user's name).
  `attachment_extract.extract_text` detects sparse PDFs (< 150 text chars AND
  embedded images), rasterizes up to 5 pages, and appends a fast-model vision
  transcription under a `[Transcribed from document images]` marker; standalone
  images work the same way. Transcription failures degrade to the raw text
  layer. The fix lives at the extraction layer so it covers ALL intakes (KB
  doc-first ingest, per-entity uploads, chat attachments). Defense in depth:
  the ingest prompt may return `{"insufficient": "<reason>"}` instead of
  inventing an entity (→ 422), and it is instructed that a title is never a
  person's name. **Onboarding import** (`POST /api/kb/import`): uploaded files
  become base resumes AND Career KB content in one action. **Resumable, NOT
  atomic** — minting a base is three writes and two commit independently, and
  rollback would mean deleting rendered artifacts, which §6 forbids. Contract:
  each base commits as it is minted, render is best-effort (`render_error` in
  the report), a failed file is skipped with a reason, and a re-run is a merge,
  not a 409 storm. `.json` short-circuits to `ResumeData` validation (no LLM).
  The parse prompt is extras-aware: non-core sections route into
  `extra_sections` (preset catalog keys when a heading matches) and are never
  silently dropped; validation failures salvage per-entry — only the rejected
  list rows are dropped (never contact/summary errors), each drop reported in
  `parse_warnings`. The consolidation source key is the MINTED SLUG, not the
  filename — `KBPortLog.resume_key` means a slug everywhere else. Slug
  collisions append a counter (REST create 409s permanently on a soft-deleted
  slug). A successful import sets `kb.seeded`. Role is proposed
  DETERMINISTICALLY by a priority cascade — display name (filename), then
  summary, then the two most recent titles, each independently, word-boundary
  matched (`role_categories.propose_from_resume`). The first signal that names
  exactly one family wins; a signal naming two or more falls through; only
  when every signal is empty or ambiguous does it return `unknown` ("a visible
  blank beats a plausible wrong answer"). `ImportedBaseRead.role_label` carries
  an alias's own words when the guess used one. The web UI imports one file
  per `POST /api/kb/import?consolidate=false` (per-row progress) then
  `POST /api/kb/import/consolidate` over the minted slugs. Default
  `consolidate=true` keeps the batched contract for MCP and external callers.
  Imported
  points keep auto-approve — a documented exception to the review-first rule,
  because they are verbatim from a file the user already wrote.
  **Caller-parsed ingest** (`POST /api/kb/ingest-parsed`): JSON
  `{sources:[{key,data}]}`, provenance via the standard write-origin headers —
  atomic `ResumeData` validation (any failure 422s the batch in FastAPI's
  `{loc,msg,type}` shape, nothing persisted; ≤20 sources, unique slug keys),
  then `consolidate_deterministic` (identity-key entity match — with the
  near-identity second pass below — verbatim one point per bullet with port-log
  rows, no LLM), no base minting. Points land
  as DRAFTS (`origin="mcp"`) — agent transcription is NOT the verbatim-file
  exception; `kb_approve_points` is the review gate. Re-runs merge, but only
  within this path: the LLM resolver may canonicalize names this path matches
  literally. Retired text is never resurrected; archived-entity landings surface in `warnings`;
  extra sections ingest into `kind="extra"` entities; `kb.seeded` is set only when
  content actually landed. `consolidate_deterministic` is a NEW entry point;
  `consolidate()` (LLM resolve+cluster) is unchanged for import/seed. **Batch
  point state** (`POST /api/kb/points/bulk-state`): `{ids, state:
  approved|retired}` (deduped, 1–500) → per-id `{id, ok, state, detail}`;
  unknown ids do not abort the rest; `approved_at` mirrors single PATCH. The
  `/career` draft inbox has a confirm-gated "Approve all shown" over the
  listed set (unsaved row edits are excluded, never silently approved). `seed_career_kb` EXCLUDES the shipped `example`
  base: `_seed_profile` is non-clobbering, so seeding the demo would make the
  demo person the user's permanent KBProfile contact. **This seed is the
  ONBOARDING path, not migration scaffolding.** `kb_consolidation.consolidate`
  is generic over any `(resume_key, ResumeData)` list; `seed_career_kb` feeds
  it every active base behind the one-shot `kb.seeded` flag. A candidate for
  EXTENSION, never for removal. `_seed_profile` takes contact/summary from the
  LAST source (sources are ordered oldest-updated first, so the newest resume
  wins). `compose_resume_data(session, *,
  entity_ids=None)`: `None` composes the WHOLE KB (`/kb/compose`,
  `/kb/context`, chat grounding); a list narrows it for `POST
  /api/base-resumes/from-kb`. The check is `is not None` — an EMPTY selection
  is legitimate and falsy, so truthiness would silently compose everything.
  Only experience/projects/education/certifications come from entities;
  `contact` and `skills` live on `KBProfile` and arrive in full. The KB summary
  is dropped unless `include_summary` (a whole-career summary on a
  role-targeted resume is usually wrong). Explicit callers may supply `slug`;
  the onboarding flow omits it and supplies a validated `role_category`, so the
  server allocates the role slug across active AND soft-deleted rows instead of
  retrying a tombstoned identifier forever. **KB→resume porting** has two
  modes: verbatim (`POST /api/kb/port`) and AI-adapted (`POST
  /api/kb/port/adapt` proposes, `…/adapt/apply` applies after user review —
  never auto-applied; `services/kb_adapt.py`). Apply re-validates server-side
  and reuses the port pipeline (`_persist_port`); certification entities are
  adapt-rejected (verbatim only). Drift semantics: `KBPortLog.source_text`
  snapshots the point at port time for adapted ports; `drifted` compares
  `coalesce(source_text, ported_text)` to the current point, so an adapted
  rewrite is NOT drift but a later KB point edit is. **Local Markdown Career
  Export** (`services/exports.py`, `routers/exports.py`): the database stays
  authoritative; `career.md` is derived, deterministic, LLM-free, cached
  atomically under `EXPORTS_DIR`. REST: `GET /api/exports`, `GET
  /api/exports/career`, `POST /api/exports/career/refresh`. Reads auto-repair
  missing/stale cache; KB mutations attempt best-effort refresh. The cache key
  is source data AND `RENDERER_VERSION` — **bump it whenever `_render_markdown`
  changes**, or an unchanged KB serves the old renderer's output forever. Disk
  failures degrade to fresh rendered responses without rolling back KB writes;
  composition failures propagate; `best_effort_refresh` rolls the session back
  on failure (callers build their response off that same session).
  `compose_context` is a prompt block whose `##` entity headers are demoted one
  level on splice, so "Beyond the Resume" nests instead of flattening the
  outline. MCP: read-only `get_career_export()` in the full profile;
  `get_career_context()` remains structured grounding. Out of scope: Autofill,
  EEO, analytics, re-importing `career.md`, backend tailoring prompt
  consumption.   **Write provenance**: `KBPoint.origin` is a closed set including `mcp` and
  `base_sync`; `kb_points` and `kb_entities` carry a nullable `origin_detail`
  naming the MCP client. It arrives on `X-Maestro-CS-Origin` /
  `-Origin-Detail` headers (`app/write_origin.py`, allowlisted so a header
  cannot invent an origin; the detail is percent-encoded by `encode_detail`,
  since a header value must be ASCII, and decoded without control characters,
  ≤120 chars). NULL origin means web-written or predates the
  header — no backfill, because inventing an origin for historic rows would
  fabricate an audit trail. **Groundedness** is a separate nullable column
  `KBPoint.provenance`
  (`user_authored|user_stated|derived_unverified|user_cannot_confirm`); NULL
  renders as "unlabeled", is never a trusted UI state, and is never backfilled.
  Verbatim user text is `user_authored` or `user_stated`; machine-merged
  wording is `derived_unverified`. `KBPortLog.direction` is
  `to_resume|from_source` (NULL = legacy; `from_source` is excluded from
  usage). **Base→KB sync** classifies without an LLM and drafts new bullets
  (`origin=base_sync`, `provenance=user_authored`). `classify` loads the same
  recorded-drift seen-set `apply` does, so drift the KB already documents
  classifies as tier `recorded` (`counts.recorded_drift`) and is never
  actionable; the toolbar pill's N is new + `skills_new` + UNRECORDED drift.
  Apply reports `skills_added` (item-level, not categories), `renamed` and
  `titles_upgraded`, and stamps `last_kb_synced_at`.
  **Near-identity entity matching** (`kb_consolidation.find_near_identity`,
  shared by `consolidate`, `consolidate_deterministic` and sync) runs ONLY
  after an exact identity-key miss and is deliberately conservative — a false
  merge loses evidence, a false fork costs one manual merge. Experience: same
  company AND a PRESENT, equal `start_date` AND one role's token set contained
  in the other's (dateless never matches). Certifications: token-set EQUALITY
  after stripping noise words, a LEADING vendor token and code-shaped
  parentheticals; a named issuer on both sides that disagrees vetoes, and an
  exam code must carry a hyphen, so code-shaped issuers (ISC2, 3M, O2) stay
  identity. Projects: containment within `PROJECT_MAX_EXTRA_TOKENS` extra
  tokens. Education and extra sections are exact-only. Two distinct candidates
  matching is ambiguity → None. Write paths upgrade a stored role title to a
  strictly richer incoming one (`upgrade_experience_title`); the LLM
  `consolidate` path applies near-identity to certs only, because experience
  goes through `_resolve_family`, which never renames. **Manual merge** (`POST
  /api/kb/entities/{id}/merge` `{target_id}`, web-only — no MCP tool, per the
  MCP no-destructive-surface rule): re-points points/documents/port-logs onto
  the target, absorbs only fields the target left empty, deletes the source.
  Guards: same kind, same extra-section key, no archived target, an ongoing
  target keeps its open end date, 409 on a concurrent race.
  `entity_timeline` emits `point_captured` **only** for `mcp`/`chat` points (a
  hand-typed KB grows no timeline entry per bullet). `patch_point` clears
  `approved_at` when a point leaves `approved`.
- **ResumeLintReport** (health check): the [health rubric](../health-check-rubric.md) says what each
  level, flag and word-bank default means and why; this entry is the code's contract. Gates are `tier:
  "fatal"|"serious"` × `status: "pass"|"fail"|"not_assessed"` (`health_gates.py:3`), scored by
  `health_score.py` (the plain mean of experience, project and custom-section bullet levels; the
  summary is judged, never scored); a failing fatal, unwaived gate BLOCKS tailoring-session creation
  — but only a FRESH one: a stale report (its `resume_version_number` no longer the latest version)
  counts as NO report for the block and only sets a re-analyze `health_warning`. Report reads carry
  `stale`, `insufficient_evidence` (fewer scoreable bullets than `MIN_SCOREABLE_ITEMS = 4` — grade
  withheld in the UI), `score_breakdown` (`raw_score`/`e_hot`/`n_scoreable`/`capped_by`, from
  `features_json`) and `next_grade` (`{grade, points}` to the next band's floor; null at A, and when
  a failed gate's cap sits below that floor, so a raw 50 under the fatal 54 cap gets no "5 points to C"). Every ask and fix on a scored bullet carries `gain`: the points one
  level up is worth (`100 × step / n_scored`), never a promised jump to full credit; summary asks and
  every note carry 0.
- **The health evaluator** (`bullet_classify.py`, prompt `resume_bullet_classify`) judges; code
  validates and does all arithmetic. One batched smart-model call for the texts nothing stored
  answers returns, per text, a level, 1–3 `evidence` quotes, one `question`, `ask_kind`
  (`measure`|`detail`), `measure_target`, `alt_question`, up to three `language` slips
  (`{span, fix}`), a reason and a confidence. `_validate` is STRUCTURAL: a quote must be verbatim
  (case, whitespace, curly quotes, dashes and any wrapping quote marks aside) and at least three words, and `analogue`/`direct` without one drops to
  `adjacent`; a `measure` ask survives only when its target names the bullet's own words (half its
  content words, as whole words) AND its alternative asks for no number — otherwise it becomes a
  detail ask carrying that alternative (or none, and the report falls back to static per-level copy,
  `FALLBACK_QUESTION`); a detail question that demands a number is swapped the same way; `direct`
  asks nothing; a slip's span must occur verbatim. A text the model skips reads `implied` + uncertain
  and is not stored. Results cache on `bullet_classifications` by `content_hash` and are reused only
  under the current `RUBRIC_VERSION` AND smart model, so a prompt-contract change bumps the version
  (SYSTEM.md §12); overrides survive both. Findings carry `ask_kind` (`reword` on a fix, and on the
  ask a ≤0.30 bullet gets when no safe rewrite exists), `measure_target` and `alt_question` (measure
  asks only), verbatim `evidence`, `classification_source` (which of override, dispute or evaluation
  rated it) and the question itself, which also reaches every rewrite of that bullet as context
  (`guarded_rewrite(question=)`). `evaluate_uncached` never touches the cache: disputes and
  `scripts/health_golden.py` (the rubric's pilot gate, run by hand) rely on that.
- **Health disputes** (`health_disputes.py`; `POST /{kind}/{key}/dispute`, `GET /{kind}/{key}/disputes`,
  `DELETE /disputes/{content_hash}`) are the **Not right?** control: the evaluator re-run uncached on
  one bullet with the user's note (≤1000 chars). The note changes how the text is READ; the level
  may not rise without a verbatim quote (`dispute` keeps the earlier reading, whatever `_validate`
  allowed). A fact the note adds comes back only as a `guarded_rewrite` `suggestion`, dropped when the
  model's `new_fact` carries a number neither the note nor the bullet gave ("Add it to the bullet in
  your own words."). The reply is written in code from the before/after comparison, quoting the UI's
  level labels. One `bullet_disputes` row per text, never on `bullet_classifications`;
  `classify_items` precedence is **override > dispute (same rubric version and model) > evaluation**,
  and a disputed finding says `classification_source="dispute"`. `metric_unavailable` ("no number
  exists") persists: later disputes keep it, and it demotes number asks at READ time on every
  evaluation of that text (`without_number_ask`), whatever the model or rubric, until DELETE
  reopens it. Errors: 409 for changed text (the `expected_content_hash` guard, including a vanished
  bullet) and for a hand-set rating ("You set this rating yourself. Set it back to automatic first.",
  before any model call); 422 for a blank note or no text; 502 when the answer fails validation
  (nothing stored) or the provider is down. Custom-section (`extra:`) bullets are disputable, their
  text read with `_text_at`. GET lists disputes whose text is still in the resume, one row per
  location; DELETE is 204 and idempotent. The write lock is taken only after every model call.
- **`evidence.no_numbers`** is a zero-score `note` at `{"section": "resume"}` (no index), from
  `_shape_notes`: it fires when 4+ scored bullets exist and none has a number (`_has_metric`, which
  ignores versions and years); a highlighted flag, never a penalty or a quota.
- **Wording notes** are `language.cliche` / `language.filler` (code-matched against the user's word
  bank, `health_wording.py`, from `_advisories`, so `rule_notes` and the coherence check carry them)
  and `language.slip` (the stored `language` field, built in `assemble`; not in the coherence check),
  over the summary and every scored bullet: one note per location and word or span, zero score, never
  skipped under a ladder ask, with `subject` (the word or span) and the ORIGINAL text's
  `content_hash`. A cliché never has a `suggestion` (a rewrite by hand); a filler's is the text with
  every whole-word occurrence cut, and a slip's the fix swapped in only when the span occurs once —
  each only when `health_wording` finds the seam clean (the Remove safety net: rubric, "Remove and
  Apply") and `guard_violations` is empty. The bank is two `Setting` rows: `health.word_bank`
  (absent = defaults; reset deletes it) and `health.ignored_words` (Never flag, which also silences a
  slip; reset keeps it), edited through `GET`/`PUT /api/resume-lint/wording` and `POST
  /wording/reset`, all three answering `{cliche, filler, ignored, defaults}`; entries are trimmed,
  lower-cased and deduped (1–40 chars, ≤200 per list, else 422) and an unreadable row reads as the
  default. Tailoring avoids the same words: `prompt_assembly._skill_preamble` appends one "Never use
  these words: …" line (clichés then filler, minus Never flag).
- **Health finding ids are frozen keys**: `_fid` hashes the finding's type, location and issue text,
  and saved ask answers key on that id, so a finding whose `issue` is reworded passes its OLD text as
  `id_key` (`LADDER_COPY`'s and `ASK_ISSUE`'s `id_key`, the `_ID_KEY_*` constants and `_id_key_*`
  builders in `resume_lint.py`); never edit one, or every saved answer is orphaned. Which asks kept
  their keys: SYSTEM.md §12.
- **Health rewrites and answers**: `replace_bullet`/`replace_summary` ops accept `expected_content_hash`
  (the classifier hash of the text being replaced); a mismatch — or a vanished target when a hash was
  sent — is 409 "content changed since analysis", and ask-answer applies the same guard. C2 escalates
  ask→fail only when the resume CHANGED since the prior report, and `guarded_rewrite` permits numbers
  the candidate's answer supplies (`guard_violations(..., supplied=)`). Unattended (context="")
  strengthen rewrites are cached on `bullet_rewrites` by `content_hash` — a row with NULL text is
  "tried, ask", absence is "never tried"; answered rewrites persist on `health_ask_answers` (written
  before the LLM call; `GET /api/resume-lint/{kind}/{key}/answers` rehydrates). `POST
  .../draft-rewrite` is the generic guarded-draft path (`objective=strengthen|condense`, optional
  `expected_content_hash`, always returns the hash of the text drafted FROM). Base `PATCH /edits`
  answers with `version_number`, the version it left latest (the question pass's Undo:
  [resume-version.md](resume-version.md)). `skills.undemonstrated` is a token-boundary match
  (alphanumeric lookarounds, not `\\b`, so C++ still matches; ≤2-char tokens cannot hit inside "for").
- **Health gates and waivers**: gate words are one table, `health_gates.GATE_LABELS`, re-stamped on
  every READ (`with_current_labels`), so a relabel needs no re-run and no frontend map. **The
  `HealthGateWaiver` table is the authority on waivers**, never a stored report's statuses: waiving
  writes a row and nothing else, so a snapshot says `fail` until the next RUN folds waivers in. Readers
  go through `resume_lint.gate_waivers(db, kind, key)` — reading statuses kept MCP's
  `waive_health_gate` escape hatch shut (waive → retry → same 409), and only the web's re-run after
  waiving hid it. Each gate carries backend-owned static `why` and `fix_hint` separately from factual
  per-run `detail`; failed and waived cards disclose that coaching, and waived gates include the
  stored reason when available. Static gate findings remain for verbatim MCP report consumers.
  Bullet classification overrides (with reason, `POST /classification-override`) let the user
  overrule a level from the report.
- **Health coverage and attention zones**: the evidence ladder covers summary +
  experience/projects/**custom-section** bullets (locations `extra:<key>`), so an extras-heavy resume
  (academic CV, licenses) scores on its real content instead of 0/F; extras are never hot zones and
  never get rewrite suggestions — no bullet-scoped `/edits` op exists for them (SYSTEM.md §11 item
  20), so every extras suggestion (fix, dispute, wording) renders copy-only. Stale `extra:` locations
  (section renamed/deleted between runs) degrade to empty text, never raise. **Attention zones govern
  severity, ordering and C1; the score is a plain mean.** `health_zones.hot_locations` returns the
  summary plus whichever ONE section carries that candidate's evidence — the most recent enabled
  ROLE for `experienced`/`unknown`, the first enabled PROJECT for `early` (with no employment history
  the projects ARE the experience). One choice, never both: marking both made most of a junior
  document hot, and `cost()` can only order the fix list if some content is cold. There is no
  three-bullet cap — an entry's bullets are one unit of evidence. A strong (`analogue`) cold bullet
  gets no ask. Editors render no amber zone wash and make no "read first by a recruiter" claim (a
  fixed positional heuristic must not be stated as fact about a reader); the marker survives ONLY on
  the health report, labelled `Higher priority`. `lib/health-zones.ts` mirrors the Python; update both
  together.
- **ApplicationProposal + ConsentEvent** (auto-apply ledger; migrations
  `56ade310b259` + `11b61fe1ace9`, lifecycle fields `0c677ba4cbcb`, filer
  `9a5744f9b9d9`, the one revision after the SQLite baseline): the
  agent-hunted apply lane. `Job.source` / `Application.source`
  (`'user'|'agent'`, default user) are the provenance dimension — never a
  parallel category taxonomy. State machine (`services/proposals.py`, ALL
  guards live there; routers map `TransitionError` → 409): `pending_review →
  {accepted, approved, rejected, needs_decision, needs_human, expired}`,
  `needs_decision → {pending_review, rejected, expired}`, `accepted →
  {approved, rejected, needs_human}`, `approved → {submitted, needs_human,
  rejected, submission_uncertain}`, `needs_human → {approved, rejected,
  pending_review}`, `submission_uncertain → submitted` (attested-only);
  submitted/rejected/expired terminal. **`pending_review` is staging**, not an
  immediate user prompt — tailor, render, fill, and collect evidence without
  per-page confirmation. **`accepted` is the user-triaged queue**:
  consent-evented (`ConsentEvent action="accepted"`), no cap reservation, no
  final_review requirement, excluded from lazy expiry; batch apply runs execute
  `status="accepted"` proposals ONLY (contract in `list_proposals`'s docstring
  + the apply playbook). Bulk triage: `POST /api/proposals/bulk-transition` —
  accepted|rejected are the ONLY bulk-legal statuses; mass-approve/submit stay
  impossible. **Skips are posting-scoped** (owner decision; the UI says Skip,
  the stored status stays `rejected` — §8 Naming): create_proposal 409s "job
  was declined" when a rejected proposal exists for THAT job;
  `company_blocklist` is the only company-level gate (`cooldown_days` is
  deprecated-but-kept in `AutoApplySettings` — extra=forbid would reset
  hand-edited files). Deleting the rejected proposal is the re-propose reset.
  **Attested submit**: `submitted` requires `submission_receipt` evidence OR
  `attested=true` + consent payload: the user's own statement, or the agent's
  confirmation with channel `auto` while full automation is On. Auto attestation
  needs a note naming what confirmed submission, containing at least one letter
  or digit; a receipt is optional. `submission_uncertain → submitted` demands
  attestation even with receipt evidence, and never permits another submit click.
  **Automatic consent**: channel `auto` is legal only for `approved` or attested
  `submitted`, and only while full automation is On. Auto approval requires
  `accepted` (the user's Queued lane), `final_review` evidence, a daily-cap slot,
  and the G7 already-applied guard; it re-checks the current `company_blocklist`
  (trimmed, case-insensitive exact company match). A company blocked after approval
  still has its submit recorded: the ledger must record what already happened.
  The `apply-auto` prompt judges whether the final review is clean; the server
  does not evaluate those eligibility checks. **G7 guard**: `approved` 409s when the linked
  application is already applied/interviewing/offered/accepted. **Manual-apply
  auto-close**: the application PATCH route, on a status entering applied+,
  transitions every OPEN proposal on that job to `rejected` (reason `applied
  manually`, channel frontend) — clears the triage/queued lanes, releases any
  cap reservation, and the declined-job guard then stops the hunt re-proposing;
  application rejected/withdrawn deliberately close nothing. **DELETE
  `/api/proposals/{id}`** (web-only; MCP keeps the no-delete invariant): 409
  for submitted/submission_uncertain (they ARE the machine-submission audit
  trail); otherwise staged-removal deletes row + consent events, then evidence
  files. List takes `?status=` (comma multi), `limit/offset`, returns `total`;
  funnel adds `accepted` + `cap` (`services/proposals.cap_status`, shared with
  `_enforce_daily_cap`). `get_final_review` adds `duplicate_submitted` — a
  same-company+title proposal already submitted/uncertain (G11 tier 2, surfaced
  before consent). **`needs_human` ↔ `pending_review`** is the resumable
  intervention loop (`resume_proposal`; `intervention_json` records
  page/step/reason without field values). **`submission_uncertain`** is
  terminal after an unverified browser submit click — never resume or click
  submit again. **Single final consent**: `record_consent(approved)` at the ATS
  submit boundary (same-turn, single-use) requires `final_review` evidence and
  idempotently reserves one daily-cap slot (`cap_reserved_at`); `submitted` /
  `submission_uncertain` keep it; pre-click reject or `resume_proposal`
  releases it. Entering approved/rejected writes an append-only `ConsentEvent`
  (channel ∈ chat|slack|frontend|mcp|auto) in the same transaction; `auto` is
  approval-only here. `submitted` requires receipt evidence or the attestation
  described above and flips the linked
  Application to `applied` with the PATCH route's `applied_at` stamping rule.
  Expiry is lazy (`expire_stale` on reads) — no scheduler exists, on purpose.
  **MCP proposal filer:** `propose_application` stamps `proposed_by` from the client's `clientInfo.name`, sent on the KB writes'
  origin headers, percent-encoded so any name files, and an agent can never file as "you"; a create takes SQLite's
  write lock, `db.begin_write`, so a job keeps one open proposal. `app/services/agent_names.py` is the server twin of
  `lib/agent-name.ts`, pinned by `tests/test_agent_names.py`: add a known client to BOTH.
  **Who filed it** (`proposed_by`): `'you'` from the web app's queue (a body
  field that accepts only `'you'`), the MCP client's self-declared
  `clientInfo.name` from the `X-Maestro-CS-Origin-Detail` header
  (percent-encoded on the wire, so any name files; it wins over the body; a
  client declaring itself "you", in any case, spacing, width or with invisible
  characters, reads as unknown, so an agent can never file as you), else NULL. A label, not an identity. The migration
  backfills `'you'` onto promotions written by older frontends, which sent no
  filer, by the plan summary they carry ("Promoted from the tracker by the
  user", `promoteJobToAgentQueue`). That text has never changed, and changing
  it now can't reach those rows: the queue sends `proposed_by: "you"` itself.
  Every job read (list, `GET /api/jobs/{id}`, its PATCH and re-extract replies, `/detail`)
  exposes the newest proposal's filer as `proposal_proposed_by`, beside
  `proposal_status`/`proposal_id` (`routers/jobs._with_newest_proposal`).
  The web app words it through `frontend/lib/agent-name.ts` ("Proposed by
  Claude", "Queued by you", "Proposed by a connected agent"), never raw. A web
  Queue on a job whose open proposal an agent filed keeps that agent as the
  filer (the dedup below), and the Queue's toast says so.
  Dedup at `POST /api/proposals`: an **open** proposal for the job returns that
  proposal (HTTP 200, idempotent, keeping the first filer). **Check and insert are one step**:
  nothing in the schema says one open proposal per job, and pysqlite opens a transaction only
  at the first write, so two creates that both checked before either inserted both inserted
  (a double click filed two accepted proposals). The route takes the write lock first
  (`app.db.begin_write`, `BEGIN IMMEDIATE`), so the second waits and returns the first's row;
  pinned by `test_two_concurrent_creates_for_one_job_leave_one_open_proposal`. A partial unique
  index was rejected: a database v0.4.0 imported from Postgres may already hold rows that break
  it, so creating it would fail the migration. If the caller also passes `application_id`
  and the proposal is unlinked, late-link it (never relink to a different
  application — 409). Company blocklist stays hard 409. Agent-sourced jobs gate
  execute helpers (`prepare` / `attach_evidence` / `record_consent` /
  `mark_submitted`) on an open proposal in the allowed status set — 409 `no
  open proposal for this job`; user- sourced jobs stay ungated. Evidence kinds
  are exactly `step|final_review|submission_receipt` (`POST/GET
  /api/proposals/{id}/evidence[/{name}]` → `<artifact_dir>/evidence/`,
  gitignored PII — never publish); manifest on `evidence_json` with sha256s;
  attach refuses unlinked proposals. Late application linking also via
  `ProposalTransition.application_id` / `record_decision` (only while
  unlinked); linking stamps the application `source='agent'`.
  **Auto-apply settings**: the `Setting("auto_apply")` DB row is the truth
  (`services/auto_apply_settings.py`, `JsonSetting`; local JSON at
  `settings/auto_apply.json`). GET `/api/settings/auto-apply` returns caps,
  expiry, auto-pick margin/floor, blocklist and `full_automation` (Off by default).
  PUT `/api/settings/auto-apply` saves the knobs while preserving the stored
  switch. Only PUT `/api/settings/full-automation` with `{value: bool}` writes
  the switch; `StrictBool` rejects strings/numbers. Both writers take the SQLite
  write lock before reading the stored value. `get_job_search_brief` reports it
  in `auto_apply.full_automation`. Settings › Connected agents has the
  **Auto-apply** card (deprecated `cooldown_days` hidden but preserved on save;
  the model is extra=forbid) and a **Full automation** card whose On switch
  asks for confirmation. Turning it Off refuses auto consent and login hand-offs.
  **Web surface**: `/proposals` (the Agent inbox) — summary
  rows link to `/jobs/[id]?from=proposals`; Queue/Skip on a row and in bulk
  (channel `frontend`) stay on the list, and the lanes are one table
  (`frontend/lib/inbox-lanes.ts`: `INBOX_LANES`, `laneOf`, `NEEDS_YOU_STATUSES`); a
  Queue accepts only a Proposed proposal and otherwise says which lane it is in;
  the job page mirrors Queue/Skip and
  shows the proposal pill + the proposal's Overview card, titled with its filer; prev/next walks
  `cs-proposals-seq`. Delete on non-submitted rows; still NO browser execution
  from the web — execution only happens in a live agent session holding a
  browser, and final submit consent stays in that session. Funnel: `GET
  /api/proposals/funnel` (declared before `/{proposal_id}` — path shadowing).
  Playbook: `docs/playbooks/agent-apply.md`; execution skill:
  `backend/app/automations/skills/agent-apply-execution/SKILL.md`; consent-gated constraint in
  `docs/agentic-job-search.md`.

  **PDF tools:** render + slim PDF inspection (`get_rendered_pdf` has **no** `page_images_b64`;
  `get_rendered_pdf_page_image` is the opt-in one-page visual, `max_dimension_px` default 1024 with a ~1MB encoded cap;
  `prepare_application_pdf_upload` stages a disposable Playwright copy under `.playwright-mcp/uploads/`).
  **PDF upload staging:** Playwright upload constraint: a folder
  grant on `applications/` does **not** expand `browser_file_upload` — stage a
  disposable copy via MCP `prepare_application_pdf_upload` under
  `.playwright-mcp/uploads/` (or `$MAESTRO_CS_UPLOAD_DIR`), pair Playwright
  `--output-dir` with the parent `.playwright-mcp` tree, and pass the returned `upload_path` to the file chooser —
  never copy/move with shell or filesystem tools. Details: `docs/playbooks/agent-apply.md`, `backend/mcp_server/README.md`.
  **Attended executor:** Playwright MCP with headed real Chrome — prefer `--extension` so the Companion can
  autofill/attach; direct MCP + browser fill/upload is the supported fallback. The agent calls
  `record_filled_answers` per page, which replaces per-page screenshots; `final_review` and `submission_receipt`
  evidence stay, and every flag goes into the "Submit now?" question. Never headless / stealth / CAPTCHA
  bypass.

  **Unattended executor**: the `apply-auto` prompt replaces the per-application
  yes, job-site sign-in, submission proof and the user's presence at submit;
  the execution skill points to those four exceptions. It works only Queued
  (`accepted`) jobs, in the order and batches the user agrees with their agent.
  It records each page's answers, checks `get_final_review` (PDF ready, no
  knock-out conflict, the resume set for the job's country (`base_country.eligible` not false), no flags,
  no duplicate, no blocked/manual items, every
  screening answer naming its saved fact `slot`), attaches `final_review`
  evidence, records approval with channel `auto`, submits once, then calls
  `mark_submitted(channel="auto", note=confirmation)`. Blocked jobs go to
  **Needs you** through `report_failure`; the agent asks and moves on. A user's
  yes follows: attach `final_review` evidence → `record_consent(channel="chat",
  action="approved", note=user's words)` → submit once → `mark_submitted`
  with channel `auto` and a confirmation note. A later automatic run requires
  the user to queue a Needs-you job again. Unknown submit success means
  `report_failure(reason="submission_uncertain")`, never a retry. Runs record
  `automation="apply-session"`; Maestro sets neither order nor schedule.

  **Job-site login**: Settings › Connected agents shows the login editor while
  full automation is On. `settings/secrets/job-site-login.json` is a local
  cleartext file, mode 0600 in a 0700 directory, never DB, exports, telemetry
  or logs. Writes serialize read/update/replace under a lock and use a unique
  0600 temporary file per write; damaged JSON or a non-object file reads as
  empty, and a save repairs it. GET `/api/settings/job-site-login` returns only
  `{email, password_set}`. PUT sets either field (missing/null keeps the old
  field; password length 8–200); DELETE clears both. Validation failures use
  sanitized errors that never echo rejected credentials. The editor never
  receives a saved password and clears the new password after saving.
  **Login hand-off**: MCP `get_job_site_login(proposal_id)` (full/apply profiles)
  calls POST `/api/proposals/{id}/job-site-login`, which refuses ANY `Origin`
  header, requires `X-Maestro-CS-Origin: mcp`, full automation On, an `accepted`
  or `approved` proposal and a company off the current skip list. An incomplete
  login or unknown proposal is 404; browser/non-MCP requests are 403; switch,
  status or company refusals are 409. Each successful call returns
  `{email, password}` and writes a `ConsentEvent(action="login_shared",
  channel="mcp", note=client name)`, never the value and never a cap reservation.
  MCP maps errors by status (unreachable, 403, 404, 409, 422, generic failure)
  to fixed messages, never retaining or surfacing the response body; unreadable
  success JSON is also sanitized. The value passes through the agent's AI
  provider; use this login only for job-site accounts.

  **Inbox readiness**: `GET /api/proposals` computes `readiness` at read time, never stores
  it, and only marks open rows (`pending_review`, `needs_decision`, `accepted`, `approved`,
  `needs_human`); History rows receive null. `services/inbox_readiness.py` reads the scan
  profile once per batch and shares a consent-gated answer profile for jobs with receipts.
  `tailored` is the linked application's `bool(pdf_path)`, or null when the application
  is unlinked or gone. `knockout` is the first conflicting check's kind only when the scan
  status is `conflict`, otherwise null. `to_check` counts latest receipt fields carrying
  any flag (one count per field, even with several flags), or 0 without recorded answers.
  `base_country` is the job's country code when the linked application's base resume is not
  eligible for it (`base_eligibility.eligible_given`, batched; final review calls `is_eligible`), otherwise null: also null for no
  application, no job country, a base with no row, or a job in `fallback`.
  A row failure is logged and gives that row null; a batch-level read failure gives every
  open row null while the list still returns. `inbox_readiness.is_ready` is phase 4's shared
  rule: `tailored is True`, `knockout is None`, `to_check == 0`, `base_country is None`; null
  readiness is not ready. `get_final_review` carries the same check as `base_country:
  {job_country, base, eligible}` on the resume that would be sent (the application's, else the fit's
  `chosen_base`; null without a job or a base).
  Frontend twin `lib/inbox-readiness.ts`: a ready row shows **Ready**; any other a three-step meter (tailored;
  nothing blocks it, meaning no knock-out and no resume for another country; answers checked), **Not tailored**
  when it is not, and chips **Knock-out: …** (error), **Resume for another country** and **N to check**
  (warning). Ready rows sort first in Queued (`accepted`), keeping
  the user's chosen sort within each group. Marks and sorting do not move rows between lanes.

  **Arrivals summary**: `GET /api/proposals/summary?since=` returns `since` and four counts
  across the ledger, independently of the list's pagination or filters: `new` counts all
  proposals with `created_at > since` (default last 24 hours); `ready` counts Queued
  (`accepted`) rows satisfying `inbox_readiness.is_ready`; `needs_you` counts
  `needs_decision` plus `needs_human`, the sidebar badge's same statuses; `applied_this_week`
  counts `submitted` or `rejected` with reason `applied manually`, where `updated_at` is
  within the last 7 days, including the boundary. Naive `since` is interpreted as UTC.
  The browser remembers the previous visit in `cs-inbox-last-visit`, reads it once on mount,
  then stores now; absent, invalid or blocked storage falls back to the last 24 hours.
  Rows created strictly after that visit get a **New** dot. The four tiles above Recent runs
  and the lanes read **New since your last visit**, **Ready to apply**, **Needs you**,
  **Applied this week**, and jump to their lanes. Recent runs reads the newest run per
  automation ([agent-runs.md](agent-runs.md)), not every record in the run log.

  **Applied yourself in History**: `rejected` with reason `applied manually` reads
  **Applied yourself**, uses the Applied badge and counts/filters under Applied. This is
  label and grouping only; the stored status, transition guards and consent rules stay unchanged.

  **Phase 4 limits**: the readiness PDF mark does not check that the file is on disk;
  auto-submit must check before uploading. `incomplete_profile` and `warning` knock-out
  scans count as no knock-out; this dashboard rule cannot establish a complete profile.
  The run digest is unverified agent text, including the prompt's claim that it has no email
  text. There is no overdue logic because Maestro does not know the user's schedule.

- **Automations page** (`/automations`, sidebar after Agent inbox): copy-only. `GET /api/automations` reads only the full-automation switch
  (`services/automations.py` parses `app/automations/skills/<name>/SKILL.md`; card-only fields sit under frontmatter
  `metadata:`) returns the cards and the **agent apps**: Claude Desktop, Codex, Any MCP agent, plus Claude web and
  ChatGPT web, shown unreachable because MCP here is local-only (the ChatGPT desktop app works via Any MCP agent).
  **Copy prompt** puts the app's wrapper plus the skill body on the clipboard. Maestro runs NO scheduler: a scheduled
  card's wrapper has the agent ask the user when to run. The setting read is
  `auto_apply_settings.peek_settings`, never seeds or writes. Off serves the
  attended **Apply session**; On serves scheduled **Apply automatically** from
  `apply-auto`, keeping card/run id `apply-session`. `load_cards()` is strict
  and runs at startup, including the alternate `apply-auto` body and includes,
  so a broken alternate fails boot even while full automation is Off.
  Each run prompt ends with MCP `record_run`. Cards read `GET /api/agent-runs/latest` and
  show **Last ran** or **Not run yet** after data arrives; a read that never produced data
  shows no line, while a failed background refetch keeps the cached line ([agent-runs.md](agent-runs.md)). A
  ran card also wears its newest run's outcome chip; until a card has run, the connect-your-agent note is a callout.
