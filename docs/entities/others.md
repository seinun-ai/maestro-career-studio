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
  the pair**), seeding (a slug that IS a category key). Human input is
  VALIDATED, never `normalize()`d (its unrecognized→`other` is right for LLM
  extraction, wrong for a typo). Deliberately no required create field: the documented onboarding path
  drops JSON into `base_resumes/` and reaches `seeding.py` without touching the
  API, so a REST-only validator would not hold. `PATCH
  /api/base-resumes/{slug}/identity` sets role/display_name WITHOUT rewriting
  `data_json`, recording a version, rewriting the disk file, or recompiling the
  PDF — unlike the full PUT. Artifact filenames resolve their role label from
  this column (`base_resume_data.declared_role` →
  `role_titles.generic_role_title`), never from the slug. No slug is reserved
  (the pre-KB `master` profile is gone): every base resume is listable,
  editable, portable and tailorable.
- **ResumeData `extra_sections`** (custom sections): the resume is fixed core
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
  mutating resume JSON; migration `c84a19d2e7f0` resyncs only untouched stored
  seed sources.
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
  path, and a hash-guarded migration is what reaches installed rows.
  **Pre-change template sources are frozen per migration** at
  `tests/fixtures/templates_pre_section_order/`: reconstructing old bytes from
  the LIVE templates (what the date-resync test did) breaks on the next template
  edit, and did. Engine migration state: **§13** `typst-default-flip` /
  `latex-render-path` / `texlive-layer`.
- **QAEntry**: per-application Q&A / cover letter rows (+ PDFs).
- **Setup status** (`GET /api/setup/status`): a derived, **read-only**
  five-step onboarding view — no wizard-progress state; guidance is
  dismissible and recomputed from existing data (the `FirstRunImportCard`
  doctrine). Its service uses non-mutating `peek_*` reads, so a status request
  never lazy-seeds a Setting row or file mirror. Autofill readiness spans the
  required personal, work-auth, EEO, and preferences groups and means
  **answerable**, not merely filled: `decline` is an answer, optional fields
  are excluded. Work authorization reads typed `WorkAuth`; its four-answer
  knockout core is `status`, `authorized_now`, `sponsorship_now`,
  `sponsorship_future` — status never implies current authorization, and an
  incomplete core is blocking. The backend's required field lists deliberately
  hand-mirror the frontend autofill groups; update both sides together.
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
- **Career KB** (`models/career_kb.py`, `/career` pages): the durable record
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
  then `consolidate_deterministic` (identity-key entity match, verbatim one
  point per bullet with port-log rows, no LLM), no base minting. Points land
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
  Export** (`services/exports.py`, `routers/exports.py`): postgres stays
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
  consumption. **Write provenance**: `KBPoint.origin` includes `mcp`;
  `kb_points` and `kb_entities` carry a nullable `origin_detail` naming the MCP
  client. It arrives on `X-Maestro-CS-Origin` / `-Origin-Detail` headers
  (`app/write_origin.py`, allowlisted so a header cannot invent an origin).
  NULL means web-written or predates provenance — no backfill, because
  inventing an origin for historic rows would fabricate an audit trail.
  `entity_timeline` emits `point_captured` **only** for `mcp`/`chat` points (a
  hand-typed KB grows no timeline entry per bullet). `patch_point` clears
  `approved_at` when a point leaves `approved`.
- **ResumeLintReport** (health check, framework v2): gates are `tier:
  "fatal"|"serious"` × `status: "pass"|"fail"|"not_assessed"`
  (`health_gates.py:3`), scored by `health_score.py`; a failing fatal, unwaived
  gate BLOCKS tailoring-session creation. **The `HealthGateWaiver` table is the
  authority on waivers**, never a stored report's statuses: waiving writes a row
  and nothing else, so a snapshot says `fail` until the next RUN folds waivers
  in. Readers go through `resume_lint.gate_waivers(db, kind, key)` — reading
  statuses kept MCP's `waive_health_gate` escape hatch shut (waive → retry →
  same 409), and only the web's re-run after waiving hid it. The evidence ladder covers summary +
  experience/projects/**custom-section** bullets (locations `extra:<key>`), so
  an extras-heavy resume (academic CV, licenses) scores on its real content
  instead of 0/F; extras are never hot zones and never get rewrite
  suggestions — no bullet-scoped `/edits` op exists for them (§11 item 20), so
  both frontend cards render extras suggestions copy-only. Stale `extra:`
  locations (section renamed/deleted between runs) degrade to empty text, never
  raise. Each gate carries backend-owned static `why` and `fix_hint` separately
  from factual per-run `detail`; failed and waived cards disclose that coaching,
  and waived gates include the stored reason when available. Static gate
  findings remain for verbatim MCP report consumers. Bullet classification overrides (with
  reason) let the user overrule an evidence tier from the health report page.
  **Attention zones are a SCORING input, not a UI layer** (owner decision).
  `health_zones.hot_locations` returns the summary plus whichever ONE section
  carries that candidate's evidence — the most recent enabled ROLE for
  `experienced`/`unknown`, the first enabled PROJECT for `early` (with no
  employment history the projects ARE the experience). One choice, never both:
  marking both made most of a junior document hot, and `cost()` can only order
  the fix list if some content is cold. There is no three-bullet cap — an
  entry's bullets are one unit of evidence. Editors render no amber zone wash
  and make no "read first by a recruiter" claim (a fixed positional heuristic
  must not be stated as fact about a reader); the marker survives ONLY on the
  health report, labelled `weighted higher` — which is what it actually is.
  `lib/health-zones.ts` mirrors the Python; update both together.
- **ApplicationProposal + ConsentEvent** (auto-apply ledger; migrations
  `56ade310b259` + `11b61fe1ace9`, lifecycle fields `0c677ba4cbcb`): the
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
  `attested=true` + consent payload (the user's own statement — the agent can
  never self-certify); `submission_uncertain → submitted` demands attestation
  even with receipt evidence. **G7 guard**: `approved` 409s when the linked
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
  (channel ∈ chat|slack|frontend|mcp) in the same transaction; `submitted`
  additionally requires `submission_receipt` evidence and flips the linked
  Application to `applied` with the PATCH route's `applied_at` stamping rule.
  Expiry is lazy (`expire_stale` on reads) — no scheduler exists, on purpose.
  Dedup at `POST /api/proposals`: an **open** proposal for the job returns that
  proposal (HTTP 200, idempotent); if the caller also passes `application_id`
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
  unlinked); linking stamps the application `source='agent'`. Knobs:
  `settings/auto_apply.json` (`GET/PUT /api/settings/auto-apply`) — caps,
  expiry, auto-pick margin/floor, blocklist; editable via the Settings
  "Auto-apply" card (deprecated `cooldown_days` hidden but preserved on save —
  the model is extra=forbid). Web surface: `/proposals` triage inbox — summary
  rows link to `/jobs/[id]?from=proposals`; hover Accept/Skip (single + mass,
  channel `frontend`) stay on the list; the job page mirrors Accept/Skip and
  shows the proposal pill + Agent proposal Overview block; prev/next walks
  `cs-proposals-seq`. Delete on non-submitted rows; still NO browser execution
  from the web — execution only happens in a live agent session holding a
  browser, and final submit consent stays in that session. Funnel: `GET
  /api/proposals/funnel` (declared before `/{proposal_id}` — path shadowing).
  Playbook: `docs/playbooks/agent-apply.md`; execution skill:
  `docs/skills/agent-apply-execution/SKILL.md`; consent-gated constraint in
  `docs/agentic-job-search.md`.

