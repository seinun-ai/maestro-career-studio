# Maestro CS — System Reference

> **This is a living document.** If you are an agent (or human) making changes
> to this repo: **update this file after your change** whenever it alters an
> entity, lifecycle, endpoint, invariant, workflow step, or convention described
> here. The next agent starts from this file; stale docs cost more than no docs.
>
> **1. Integrate, don't append.** When your change alters described behavior,
> REWRITE the affected description in present tense — do not add a dated
> paragraph below it. Dates and change narratives belong in `git log`, not
> in §1–§10. Dated entries are legal ONLY in §11–§13 (the ledgers).
> **2. Ledgers must shrink.** §11: delete items when shipped (git remembers).
> §13: cut the row when the migration completes. If your change supersedes
> something without deleting it, add a §13 row — and cut the prose it replaces.
> **3. Log what you paid for.** After a session, append genuinely new lessons
> to §12 (dated, symptom → cause → rule, ≤3 lines) and deliberately-not-fixed
> observations to §11. Not a diary — only what would have saved you time.
> **4. Cover what you touched.** Working in an area this file does not
> describe? Add the section for it.
> **5. Caps are earned.** The size cap moves only immediately after a grooming
> pass that failed to get under it — prove incompressibility before buying
> budget. `scripts/check_system_md.py` records every movement with its reason.
>
> **Section numbers are frozen.** §1–§13 keep their numbers permanently; new
> sections append at the end. Code, migrations, and handoff docs cite "§N" from
> ~129 places, and the last renumbering silently invalidated every one of them.
> Invariants in §6 additionally carry stable ids (`{#inv-slug}`) — cite those
> from code in preference to a section number, since they survive any grooming.
> **Two tiers.** This file is the ORIENTATION tier and stays whole. Pure
> reference — entity lifecycles (`docs/entities/`) and frontend conventions
> (`docs/frontend-conventions.md`) — is extracted, indexed from §4 and §8, and
> carries this same contract. When the cap is hit, extract more reference; never
> split orientation content.
> **Style rule:** every rule bullet in §6 and in `docs/entities/` opens with a
> **bolded subject** naming what the rule governs, so the section scans by lead
> terms. Every §6 invariant states its enforcement point — the test or module
> that fails if it breaks — and is pinned in `.system_md_enforcement.json`.
> **Do not accrete "Prior:" entries in this header** — REPLACE the latest
> entry per line; older change history lives in `git log SYSTEM.md`.
> Last full revision: 2026-08-20, moved to the repo root, reference tier
> extracted, invariants given ids and enforcement pins. §13 is machine-checked
> via `.slopledger.json`; the whole file via `scripts/check_system_md.py`.

**Contents**
- [§1 What this is](#1-what-this-is) — the product in one paragraph
- [§2 Repo layout](#2-repo-layout) — directory map with one-line roles
- [§3 Architecture at a glance](#3-architecture-at-a-glance) — data-flow diagram, where state lives
- [§4 Core entities and their lifecycles](#4-core-entities-and-their-lifecycles) — INDEX into `docs/entities/`: per-model rules, state machines, scoring semantics
- [§5 The application workflow, end to end (web)](#5-the-application-workflow-end-to-end-web) — the nine user-facing steps
- [§6 Cross-cutting invariants (do not break these)](#6-cross-cutting-invariants-do-not-break-these) — rules that must never break, with enforcement points
- [§7 Agent surfaces](#7-agent-surfaces) — MCP server, in-app chat, extension
- [§8 Frontend conventions](#8-frontend-conventions) — INDEX into `docs/frontend-conventions.md`: layout, a11y, naming, copy rules
- [§9 Dev & test environment](#9-dev--test-environment) — interpreter, DBs, calibration, deploy, gates
- [§10 Design-decision record](#10-design-decision-record) — lineage of superseding decisions
- [§11 Known deferred items](#11-known-deferred-items-priority-order) — ledger of work not yet built
- [§12 Gotchas that have bitten before](#12-gotchas-that-have-bitten-before) — dated symptom → cause → rule entries
- [§13 Active migrations & deprecation ledger](#13-active-migrations--deprecation-ledger) — built-twice rows with removal triggers

## 1. What this is

A single-user job-application copilot: capture job descriptions, score base
resumes against them with a deterministic ATS engine, walk a gap-analysis
workflow, LLM-tailor the resume, render a LaTeX PDF, generate the apply package
(cover letter, screening answers), and track every application
from Saved to Accepted. Three surfaces drive the same backend: a Next.js web
app, an MCP server (Claude Desktop et al.), and an in-app chat agent.

## 2. Repo layout

```
backend/
  app/
    main.py            FastAPI app; routers mounted under /api/*
    config.py          settings; data-dir paths (container-absolute by default —
                       override BASE_RESUMES_DIR/APPLICATIONS_DIR/SETTINGS_DIR/LOGS_DIR locally)
    db.py              SQLAlchemy; sessions use autoflush=False (see §12)
    models/            ORM (application, job, tailoring_session, ats_score,
                       resume_version, base_resume, template, career_kb, qa_entry, …)
    schemas/           Pydantic request/response models
    routers/           HTTP endpoints (applications, jobs, tailoring_sessions,
                       ats, base_resumes, templates, qa, resume_versions,
                       resume_lint, career_kb, exports, chat, explore, referrals, settings)
    services/          business logic (ats/, tailoring_session, gap_analysis,
                       role_categories, kb_import, exports, gap_enrichment,
                       placement_targets, ats_score, application_writes,
                       artifacts, application_render,
                       pdf_render (dual-engine: pdflatex + typst), pdf_preview,
                       jd_extraction, resume_lint, health_*, career_kb,
                       chat_agent, chat_tools, …)
    templates/         bundled .tex.j2 sources and typst_classic.typ
  mcp_server/          FastMCP server (server.py tools → client.py httpx → REST)
  migrations/          alembic (see §12 for the revision-id gotcha)
  tests/               pytest vs the test DB; mcp_server/tests/ uses respx (no DB)
frontend/              Next.js 16 (App Router) + React 19 + Tailwind v4 +
                       Base UI-flavored shadcn. AGENTS.md: read
                       node_modules/next/dist/docs before writing code.
base_resumes/          on-disk resume data (<slug>.json) + rendered tex/pdf output
applications/          rendered per-application artifacts (Company_Role_YYYYMMDD_<idprefix>/)
extension/             browser-capture extension (posts pre-extracted JDs)
```

## 3. Architecture at a glance

```
 paste JD ─┐                          ┌─ web UI (Next 16, react-query)
 extension ─┼→ jobs router → Job row  ├─ MCP server (34+ tools, thin REST wrappers)
 MCP ingest┘        │                 └─ chat agent (chat_tools.py — separate toolset)
                    ▼
        ATS engine (deterministic, LLM-free)  →  AtsScore rows (base upsert / tailored append)
                    ▼
        TailoringSession (frozen gaps → resolutions → LLM tailor ops)
                    ▼
        Application (customized_json draft) → LaTeX render → PDF + preview PNGs
                    ▼                              ▼
        status tracking (StatusChip)        QA router (cover letter / answers)
```

Postgres holds all state except resume file data (`base_resumes/<slug>.json` on
disk — DB `base_resumes` row + file must both exist) and rendered artifacts.

## 4. Core entities and their lifecycles

Reference tier: consulted per task, not read for orientation, so it lives
in `docs/entities/` and the root file stays orientation-sized. Every file
there carries the same contract as this one. Code citing "§4" lands here;
the table says which file to open.

| Entity | File | Scope |
|---|---|---|
| Job (`models/job.py`) | [`docs/entities/job.md`](docs/entities/job.md) | raw JD text + sha256 dedup; has no status of its own |
| Application (`models/application.py`) | [`docs/entities/application.md`](docs/entities/application.md) | one per (job, base resume); status vocabulary, tailored draft, render artifacts |
| TailoringSession (`models/tailoring_session.py`) | [`docs/entities/tailoring-session.md`](docs/entities/tailoring-session.md) | the open → tailored | superseded | abandoned machine; frozen gaps |
| AtsScore (`models/ats_score.py`) | [`docs/entities/ats-score.md`](docs/entities/ats-score.md) | base upsert-singletons vs appended tailored history; deterministic engine |
| ResumeVersion (`models/resume_version.py`) | [`docs/entities/resume-version.md`](docs/entities/resume-version.md) | append-only snapshots on every write path — the undo story |
| Others | [`docs/entities/others.md`](docs/entities/others.md) | BaseResume, and the secondary entities that need rules but not a file each |

## 5. The application workflow, end to end (web)

1. **Capture** — `/new`: paste JD → `POST /api/jobs` (LLM extract, dedup) →
   summary card ("Already tracked" banner on dedup). Or extension/MCP
   `store_extracted_jd` → `POST /api/jobs/ingest` (pre-extracted; Claude is
   the extractor by design).
2. **Track** — `/applications`: the tracker. Two queries (summary list with
   server-joined job fields + saved jobs), a grouped status `Select` with
   counts, inline `StatusChip` per row (PATCHes directly), search, sort, and
   an All/You/Agent provenance `SourceToggle` (counts follow the toggle;
   `?source=` deep-linkable). "Saved" = job with no application —
   agent-captured jobs stay out unless the toggle is `Agent` (hunt inventory
   lives on `/proposals`). The filter's three groups are All/Saved, **Your
   applications** (`APPLICATION_STATUSES`) and **Agent lane**
   (`proposed`/`queued`/`needs_you`/`skipped`, derived from the newest
   `proposal_status` via `rowFilterKey`); `FILTERS` derives from those groups,
   so a key can never filter rows yet never appear as an option. **Empty
   buckets are hidden** — an option renders iff
   `count > 0 || f === "all" || f === filter`, the trailing clause so the
   active filter can never vanish under the user who picked it (re-check if
   the control changes again). `skipped` absorbs proposal `rejected` AND
   `expired`, while the ROW chip still says Expired (row-level truth). An
   unknown `?status=` falls back to `all` via the `FILTERS.includes` guard.
3. **Workspace** — `/jobs/[id]`: identity header (monogram, meta line,
   inline StatusChip + Details menu; proposal pill + Accept/Skip when a
   proposal exists), tabs Overview / Score & Tailor / Resume / Q&A (tab URL
   values stay jd/fit/output/qa for deep-link compatibility).
   `?from=proposals` flips Back + prev/next onto `cs-proposals-seq`;
   otherwise they use `cs-tracker-seq`. Overview mounts an Agent proposal
   block when `proposal_id` is present; job list/detail derive
   `proposal_status`/`proposal_id` from the newest proposal. Overview also
   renders the **knock-out pre-scan** (`services/knockout.scan_job`, embedded
   in `GET /jobs/{id}/detail` and in `get_final_review` as `knockout`):
   stated JD requirements (work auth, OPT policy, salary) vs the autofill
   profile, recomputed on every read. Verdicts are `conflict` /
   `clear` / `incomplete_profile` / `unstated` — unstated is NEVER a pass,
   and salary only warns (pay is negotiable). Informational like G11 tier 2:
   it flags; the consent/submit decision stays human.
4. **Score** — Score & Tailor tab auto-scores all active bases on first visit;
   per-base cards → "Analyze gaps & tailor" creates a session.
5. **Gap analysis** — `/jobs/[id]/tailor/[sessionId]`: per-gap resolutions
   (add_keyword / user_input / attach_project / skip + enable_entry /
   port_kb_point — see §4; plus cannot_confirm on claim-asking gaps: skip for
   the document + a durable `user_cannot_confirm` KB record written at SAVE
   time, so the claim is never re-asked — see §6 inv-provenance-no-decay)
   autosaved debounced with replace=true semantics
   (omitted gap_ids are deleted server-side); KB-auto-resolved gaps arrive
   pre-selected with provenance + Undo and a counting banner; optional
   per-session note (`user_prompt`, falls back into tailor()). "Use base
   resume as-is" (visible at 0 addressed) → from-base + closes the session;
   confirms first if it would replace an existing tailored draft.
6. **Tailor** — `POST /tailoring-sessions/{id}/tailor`: deterministic
   pre-ops first (enable_entry → toggle_entry, port_kb_point → add_bullet +
   KBPortLog row; deduped per point/entry), then remaining non-skip
   resolutions → smart-model LLM → typed edit ops → apply → keyword-survival
   check (one retry, then add_skill_item fallback — LLM path only) →
   reuse-or-insert application → version row → draft-KBPoint write-back of
   substantive user_input answers (origin=gap_elicitation; every skipped
   write-back returns on the response as `kb_writeback_skips` with a reason —
   too_short / wrong_section / no_entity_match / duplicate — and the gap page
   toasts a quiet note, so flywheel drops are never silent) → session
   `tailored` → tailored score — one transaction (tailor() commits once at
   its end; score_target stages on the same session). A pre-op-only session tailors with zero LLM calls; MCP can
   pass caller ops to skip the backend LLM. Post-tailor the UI lands in
   review mode (`?review=1`): provenance-labeled structural diff
   (`GET /applications/{id}/resume-diff`, hunks attributed kb_auto/user/llm),
   revert-per-hunk through the normal edit path, and an on-demand read-only
   coherence lint (`POST .../coherence-check`).
7. **Output** — Resume tab: the ONE before/after compare panel + PDF card;
   **Generate PDF** renders the tailored draft and shows the shared rasterized
   page preview inline (Regenerate refreshes it); download/open actions become
   available immediately. "Edit resume" → the studio
   (`/applications/[id]/resume`) where Save chains render → re-score
   automatically.
8. **Apply package** — Q&A tab: questions, cover letter (tone). Outreach/cold
   messages are asked as free-form questions (there is no dedicated cold-message
   generator); the QA prompt injects the application's linked referral contact.
9. **Track to terminal** — StatusChip anywhere (tracker row or job header):
   draft → applied → interviewing → offered → accepted / rejected / withdrawn.
   A base résumé grown past the Career KB shows a `Sync to KB (N)` toolbar pill
   (N excludes already-recorded drift); its **Sync now** drafts new and drifted
   items with no LLM, near-matching entities instead of forking duplicates.

## 6. Cross-cutting invariants (do not break these)

- **The browser is the attacker; six controls are the whole boundary.** `{#inv-browser-boundary}`
  The API has no authentication, so
  binding to `127.0.0.1` proves nothing on its own — the user's own browser is
  already inside the boundary and can be aimed at it.
  1. **Host allowlist, on BOTH listening servers.** `TrustedHostMiddleware`
     rejects any Host not in `settings.allowed_hosts` (`conftest` adds
     `testserver`; production does not); without it DNS rebinding makes an
     attacker page SAME-ORIGIN and CORS is never consulted. The backend check
     alone guards nothing users touch: the browser hits Next on :3000, whose
     `/api` catch-all rebuilds the request and drops the inbound Host.
     `frontend/proxy.ts` checks first — the NAME is load-bearing, since Next 16
     renamed `middleware` and a `middleware.ts` is ignored in silence — and the
     `/api` route repeats it, because this must not rest on one filename. ONE
     definition: `lib/allowed-hosts.mjs`, plain ESM so `node` runs it in tests.
  2. **Origin gate** (`app/origin_guard.py`). CORS governs what may be READ,
     this what may RUN: a form/multipart POST needs no preflight, so the side
     effect lands and only the reply is withheld. Present-but-unlisted `Origin`
     → refused before routing; ABSENT → allowed (httpx MCP and the healthcheck
     send none, and are not browsers). Raw ASGI, never `BaseHTTPMiddleware`,
     which wraps the SSE chat body. **Host → Origin → CORS** falls out of
     `add_middleware` PREPENDING, so `main.py` reads in reverse (pinned by test);
     `ALLOWED_ORIGINS` is ONE list, read by CORS and gate.
  3. **Extension origins are exact ids**, never a pattern:
     `settings.maestro_cs_extension_ids` → `chrome-extension://<id>` entries in
     `allow_origins` (a regex trusts EVERY installed extension). Unset = no
     extension may call the API, logged at startup. Extension-side half of §11
     item 19's "CORS must never admit untrusted origins".
  4. **Template source is data, not code.** `pdf_render._environment()` is a
     `SandboxedEnvironment` — `Template.source` comes from the web editor, chat
     and MCP, and a plain `Environment` turns any of those into arbitrary Python
     (`((( x.__init__.__globals__ )))`). The `(((`/`((*` delimiters are
     ergonomics, not a control.
  5. **The compiler can neither execute nor read.** `-no-shell-escape` is
     unconditional, and `compile_cover_letter_pdf` stays a thin alias of
     `compile_pdf` (the flag was their only difference). It covers `\write18`
     only — `\input`/`\verbatiminput` open anything the process can, past Jinja's
     sandbox because they live in the .tex Jinja already produced. So
     `_compile_env` adds kpathsea paranoid mode (`openin_any`/`openout_any=p`):
     no dotfiles, no parent traversal, no absolute path outside `TEXMFOUTPUT` —
     which MUST be the staging dir, since `_pdflatex_argv` passes an absolute
     `\input`. BOUNDS the damage; the render worker is the fix (KNOWN_ISSUES).
  6. **A template id is a slug, enforced in the REGISTRY.** `validate_template_id`
     (`schemas/template.py`, importing nothing from `app`) gates `create_draft`,
     `duplicate` and `_preview_path` — not just `TemplateCreate`, since chat and
     MCP reach the registry directly and `Template.id` is a bare `Text` PK.
     `_preview_path` ALSO resolve-then-`relative_to`s: two gates, either leaks.
  All six pinned in `tests/test_security_boundaries.py`,
  `test_frontend_host_guard.py`, `test_template_id_containment.py`. Related:
  `model_settings.set_base_url` rejects non-`http(s)` schemes — that value
  decides **where the stored API key is sent** (`llm._client`); both containers
  run non-root `APP_UID` over the PII mounts; and `llm._log_call` keeps
  metadata only unless `llm_log_content` is set (0600 either way).

- **An empty environment variable means UNSET.** `{#inv-empty-env-unset}`
  `config.scrub_empty_env()` deletes every empty/whitespace env var at import,
  before any SDK client is constructed (`config.SCRUBBED_ENV` records what
  went). `docker-compose.yml` writes `VAR: ${VAR:-}` for optional settings —
  an EMPTY STRING, not an omission — and third-party SDKs read `os.environ`
  directly (the OpenAI SDK adopts an empty `OPENAI_BASE_URL` and every request
  loses its scheme, surfacing as a misleading `APIConnectionError`). App-level
  `or None` guards cannot help, so the rule is enforced once at the
  environment boundary. Do not "simplify" it away, and do not add a `${VAR:-}`
  line believing the app will cope. Pinned by `tests/test_config.py` (the
  import-time case runs in a SUBPROCESS — reloading `app.config` in-process
  poisons later tests with `/app` paths). Related: `llm._get_client` raises a
  named error when there is no key AND no custom endpoint; Langfuse tracing
  requires an explicit `LANGFUSE_HOST` alongside both keys (opt-in by
  DESTINATION — keys without a host fall back to Langfuse Cloud and would ship
  resume text to a third party); compose does not forward the Langfuse vars.
- **Staged artifact removal** `{#inv-staged-artifact-removal}`: NEVER delete rendered files inside a
  transaction that can still roll back. Every `customized_json` write goes
  through `services/application_writes.stage_resume_update` (sets draft, clears
  artifact refs, records version, returns stale paths); the caller commits,
  THEN calls `artifacts.remove_files(stale)` (also removes the `<pdf>.pages/`
  dir and prunes emptied folders). Chat edits and version-restore follow the
  same pattern; there is no "immediate unlink" helper — don't reintroduce one.
- **Stable per-application `artifact_dir`** `{#inv-stable-artifact-dir}`: one folder per application,
  `applications/Company_Role_YYYYMMDD_<idprefix>/`, allocated once via
  `services/application_artifacts.get_dir`, persisted on
  `Application.artifact_dir`; resume/source/PDF, previews, cover letters and
  proposal `evidence/` colocate there. Playwright upload constraint: a folder
  grant on `applications/` does **not** expand `browser_file_upload` — stage a
  disposable copy via MCP `prepare_application_pdf_upload` under
  `.playwright-mcp/uploads/` (or `$MAESTRO_CS_UPLOAD_DIR`), pair Playwright
  `--output-dir` with the parent `.playwright-mcp` tree, and pass the returned
  `upload_path` to the file chooser — never copy/move with shell or filesystem
  tools. Details: `docs/playbooks/agent-apply.md`,
  `backend/mcp_server/README.md`.
- **Honesty invariant** `{#inv-honesty}`: an `add_keyword` on a skill the engine found NO
  evidence of (`fix_hint == "absent"`) may only land in the skills section —
  never as a fabricated experience/project bullet. Enforced server-side in
  `save_resolutions` (guards MCP/API callers, not just the UI).
- **Placement validation twins** `{#inv-placement-validation-twins}`: `_validate_placement_target`
  (tailoring_session, raises) and `placement_targets.coerce` (scrubs LLM
  output) both call the pure `placement_targets.canonicalize` —
  `services/placement_targets.py` owns the placement-target contract, and the
  frontend's `buildPlacementTargets` hand-mirrors its targets shape. Extra targets require `section="extra"`, a stable
  `section_key`, and either an enabled entry's original index or, for a flat
  bullets section, the same stable key as `index_or_category`.
- **MCP control invariants** `{#inv-mcp-controls}`: no MCP tool name contains "delete"; no
  set-default-template tool. Registration is pinned by a subset assert in
  `mcp_server/tests/test_server.py` — add new tools there.
- **`tailor_application` vs `edit_application`** `{#inv-tailor-vs-edit}` (MCP): the former REPLACES
  `customized_json` wholesale from the BASE resume; the latter applies ops to
  the CURRENT draft — docstrings lead with this; keep them unmistakable. Edit
  indices are **0-based into the full JSON section array**, including
  `enabled: false` rows (PDF render omits those — never display ordinals).
  Successful PATCH `/edits` responses echo `applied[]`.
- **Autofill telemetry carries no VALUES.** `{#inv-autofill-telemetry-no-values}` `POST /api/autofill/telemetry`
  stores label, kind, rule id, option texts, outcome, host — never what was
  typed, what was there before, or any AI answer. Structural: no value column,
  `extra="forbid"` (an extra key 422s the batch), sw re-filters to six keys.
  `host` + `first_seen_at` still make the TABLE a record of where you applied
  and when, so `DELETE /telemetry` clears it (count in body) and deliberately
  does NOT touch the capture toggle. Field list/toggle/default-on decision:
  `extension/README.md`; `…/telemetry/summary` ranks failures + saturation.
- **A frame must EARN the user's data.** `{#inv-frame-earns-data}` `sw.js` authorizes a broadcast at
  the sender, but `broadcastToFrames` targets every frame — a job page carries
  ad/analytics/chat iframes, and the ISOLATED world protects the message in
  transit, NOT the DOM written into: a frame owns its DOM, so a profile value
  in a third-party frame's input is readable by that frame's script. `agent.js`
  gates all four fan-out handlers (`profile_fill`, `collect_open_questions`,
  `fill_answers`, `attach_resume_pdf`) on `frameMayReceiveUserData()`: the TOP
  frame always passes, a SUBFRAME must show `detectPage().form`, and a frame
  whose detection throws is refused. A refused frame returns the handler's
  EMPTY shape, never a throw (a throw reads as "didn't stick" in the
  reconciliation strip). Attach additionally requires a VISIBLE input —
  `input.files` is readable with no submit and no gesture, so an off-screen
  input is a résumé collector. Pinned by `tests/test_extension_frame_gate.py`.
- **The policy deny-list is single-source.** `{#inv-policy-deny-list-single-source}` `POLICY_BLOCKED` (signatures,
  attestations, consent, credentials, government IDs) lives in
  `extension/shared/policy.js` (in `shared/`, not `content/`, since the side
  panel consults it too). FOUR consumers across THREE surfaces:
  `fillFormFromProfile` ahead of rule matching and `collectOpenQuestions` ahead
  of EXCLUDE and the per-type ladder — so a consent question rendered as a
  select/radio is never offered to the model or tagged `data-rt-qid` — plus the
  panel's PAIR, which is the half a reader would not guess: the pause row's
  body renders no input for a blocked label AND `submitAnswer` refuses one
  again, because the first is a decision about what to draw and the second is
  the one that touches the page. Salary history/current/CTC and unqualified
  salary/wage/compensation mentions are also blocked; explicit salary
  expectations are allowed only AFTER the deny-list check, so an expectation
  phrase cannot bypass a signature/consent/credential/government-ID match.
  `test_both_copies_of_the_policy_deny_list_stay_identical` asserts exactly
  one `POLICY_BLOCKED` declaration; only the page-INJECTED commit ladder stays
  deliberately duplicated (`…commit_ladder_stay_identical`).
- **One label-pattern table, two readers** `{#inv-one-label-pattern-table}` (`extension/shared/profile-fields.js`).
  The eight patterns naming a TYPED home in the autofill profile
  (`eligibility.*`, `preferences.*`) are read by `content/autofill.js`'s rule
  table, which FILLS those fields, and by the panel's `saveTargetFor`, which
  decides where a pause-row answer is LEARNED. They must be one table: an answer
  learned into `profile.custom` for a field the rules fill from
  `preferences.notice_period` lands where the rules do not look, so the same
  question pauses on every later application with nothing failing. **The learn
  store is the autofill profile, never `qa_entries`** — that table is
  application-scoped and no reader feeds it back into a fill, so "pause once,
  learn forever" is only true of `profile.custom` (matched by the deterministic
  rule pass on every later form) and the typed keys. Wiring faults are made
  loud rather than left silent: `profile-fields.js` throws at load if
  `shared/policy.js` has not run (it borrows `salaryExpectationRe`), and
  `autofill.js`'s `pf()` throws on an unknown id — an undefined pattern does not
  error, it just never matches.
- **Em-dash rule** `{#inv-em-dash}`: generated Q&A answers and cover letters are
  scrubbed of U+2014/U+2013 at store time (`qa.scrub_typographic_dashes`);
  rendered PDFs must not contain em-dashes (ATS parsers). The MCP client's
  slim `get_rendered_pdf` scan remains a resume-PDF backstop (metadata + page
  paths; no `page_images_b64` — use `get_rendered_pdf_page_image` for one page).
- **EEO standing consent is enforced at the ENDPOINT.** `{#inv-eeo-standing-consent}` Profile standing
  consent (`settings/eeo_consent.json`; `eeo_consent` on
  `/api/autofill/context`) authorizes EEO fill. `GET /api/autofill/context`
  strips `profile.eeo` unless consent is enabled and fails CLOSED when the
  consent section cannot be computed; the MCP client keeps its OWN strip — two
  gates, not a relocated one. Which client asks must never decide whether
  protected-class data is served. No inference or invented EEO answers; never
  solicit pasted demographic answers in chat when consented values are in
  Profile. WOTC/public-assistance, signatures, penalties-of-perjury, terms,
  credentials, and certifications remain human-only (direct handoff).
- **PDF word-spacing** `{#inv-pdf-word-spacing}`: pdflatex+XCharter joins words for strict extractors;
  `pdfinterwordspaceon` + the parse_certified gate protect this — see the
  shared header partial `_header.tex.j2`, which BOTH resume and cover-letter
  templates include (format/scanner changes must handle both).
- **`user_cannot_confirm` is durable.** `{#inv-provenance-no-decay}` No code
  path upgrades that provenance to anything else — including the gap flow that
  writes it: a "cannot confirm" gap outcome stores a retired
  `user_cannot_confirm` point (on the entity its placement names, else the
  archived "Unconfirmed claims" holder) and future sessions pre-resolve the
  claim instead of re-asking (normalized-text match, evidence autos win).
  Base-sync of the same claim drafts a NEW `user_authored` point and leaves
  the record untouched — new first-party evidence beats an old "don't know";
  the draft queue is where the user reconciles. Pinned by
  `tests/test_kb_provenance_stamping.py`
  (`test_no_writer_flips_user_cannot_confirm`) and
  `tests/test_gap_cannot_confirm.py`
  (`test_nothing_upgrades_user_cannot_confirm`).

## 7. Agent surfaces

- **MCP server** (`backend/mcp_server/`): thin wrappers (`@_guard` →
  `ToolError`) over REST via httpx (`BACKEND_URL`, default localhost:8000;
  compose maps host 8001). **The docstring is the API** — per-tool parameter
  traps live in the tools' own docstrings, not here. A fact an agent needs
  must survive ~2048-dedented-char client truncation or live in a param
  `Field(description=…)` (`_EDIT_OPS_FIELD` precedent); ratchet
  `test_registered_tool_docstrings_fit_client_truncation_budget`. Coverage:
  jobs (ingest/list/get/export; `get_job_search_brief` with verbatim work-auth,
  typed `job_preferences` and the `auto_apply` guardrail block;
  `find_job_by_url` posting-equality lookup; `store_extracted_jd` takes
  `source="agent"`; playbook in docs/agentic-job-search.md, capture-and-score
  only), the proposal-ledger family (consent-gated propose/decide/triage/
  resume/final-review/evidence/mark_submitted/report_failure;
  `record_consent` is called ONLY after the user actually said yes/no), base
  resumes (`list_resume_versions`/`get_resume_version`/`restore_resume_version`
  — kind is REST `base`|`application`, a restore is a new version;
  `archive_base_resume`/`unarchive_base_resume` hide from `list_base_resumes`
  without deleting; those five are **full-profile only** this round), health
  (run/get + waivers), the full tailoring workflow (session tools take
  **`tailoring_session_id`** — breaking rename, no legacy alias;
  `resolve_gaps`' evidence-carrying actions are gated server-side — §4;
  `quick_tailor` is the profile-driven fast path), render + slim PDF
  inspection (`get_rendered_pdf` has **no** `page_images_b64`;
  `get_rendered_pdf_page_image` is the opt-in one-page visual,
  `max_dimension_px` default 1024 with a ~1MB encoded cap;
  `prepare_application_pdf_upload` stages a disposable Playwright copy under
  `.playwright-mcp/uploads/`), application tracking, the apply package,
  templates (draft/validate only; Typst constraints in
  `create_template_draft`'s docstring, `fmt.*` knobs on `get_template`),
  explore analytics,
  `get_autofill_profile` (`profile.eeo` consent-gated), and
  `get_career_context` (read-only; anti-fabrication rule in the docstring).
  The Career KB is writable via MCP: reads carry IDs the context prose does
  not; entity/profile writes land directly, but POINTS go through the user's
  gate — ingest lands drafts, `kb_sync_base` drafts new/drifted base-resume
  items (no LLM, no auto-approve), and `kb_approve_points` is the ONE approval
  path (`approved|retired`), its gate a DOCSTRING convention, not server
  enforcement — call ONLY after the user explicitly approved the listed
  points (`record_consent` precedent). `kb_edit_point` has no `state` param;
  a text change forces `state="draft"`. No delete tool; document upload stays
  web-only. **Scoped profiles** (`MAESTRO_CS_MCP_PROFILE`, default `full`):
  one binary, filtered tool sets — `hunt` / `apply` / `explore` / `templates`
  / `career`; allowlists in `mcp_server/profiles.py`; enable ONE profile per
  chat (`full` already carries the KB writes). Config examples for both stdio
  clients live in `mcp_server/` (`claude_desktop_config.example.json`,
  `codex_config.example.toml`); ChatGPT.com cannot be a client — `mcp.run()`
  is stdio only. **Apply executor:** Playwright MCP with headed real Chrome —
  prefer `--extension` so the Companion can autofill/attach; direct MCP +
  browser fill/upload is the supported fallback. Never headless / stealth /
  CAPTCHA bypass.
- **Guided tailoring workflow** (`mcp_server/workflow.py`): wrapped tools carry a
  `next` envelope (`state`/`blocking`/`offer`/`ask_user`/`options`/`call`) that
  walks §5's arc — score all bases → recommend → quick|custom → tailor → render
  → apply readiness — unnarrated. `workflow.py` is PURE (no httpx/DB/LLM), a
  **deliberate exception to the thin-wrapper rule**: the sequence must live
  somewhere and FastMCP `instructions=` is surfaced inconsistently across
  clients; purity is what keeps it testable under DB-free `mcp_server/tests`.
  - **Server ranks, agent narrates.** `rank_bases` is deterministic (composite
    desc, slug tie-break), so identical scores always yield the same pick and
    only prose differs. `close_call` (< `CLOSE_CALL_MARGIN` 3.0) means present a
    CHOICE, not a verdict — NOT `auto_apply.auto_pick_margin`, which means "pick
    without asking" in the hunt lane. `coverage_warning` comes off the
    RECOMMENDED row, not the table: `_calc_coverage_signal` compares each
    resume's OWN matched ratio, so bases can disagree; only
    `extracted_count == 0` is uniform.
  - **`offer` ≠ `ask_user`.** `score_ats` emits only a non-blocking `offer` —
    mass JD capture scores twenty postings in a loop and a question on each
    would derail it; `ask_user` appears only mid-arc, after the user commits.
    **A hint never names a tool the active profile did not register** (`hunt`
    has `score_ats`, no tailoring tools) — options filter through
    `profiles.allowed_tools()`.
  - **Two controls.** `mcp_workflow` `{hints: bool}` (`GET/PUT
    /api/settings/mcp-workflow` + Settings card) is the USER's master switch;
    `brief=true` on `score_ats` is the AGENT's, for triage loops, checked FIRST
    so a loop pays no settings read. Tools **always wrap** (`next: null` when
    suppressed) — one tool must not return two shapes per runtime flag.
  - **LLM-free arc.** MCP `create_tailoring_session` defaults `enrich=False`;
    `quick_tailor` = create + `POST .../apply-profile` (deterministic fill) →
    agent authors ops → `tailor_session(ops=…)` skips the backend LLM pass.
    Filling precedes authoring so saved resolutions and applied ops cannot
    disagree (§11 item 13). `apply-profile` discards
    `fill_checkpoint_session`'s standing-instruction return (persisting it would
    break the web path's transience), so the hint carries it as the
    `tailor_session` option's `user_prompt`, ONLY when the session has no note
    of its own — else quick tailor over MCP ignores a setting the web obeys.
    **The caller-ops honesty rule is enforced by DOCSTRING, not the server**:
    `apply_edits` has no honesty gate, keyword-survival is LLM-path only. The
    server-side evidence gates (`save_resolutions` re-running
    `enable_entry`/`port_kb_point`) still hold.
  - **Apply readiness** reads `setup/status`'s `autofill` block. There is no
    cross-server introspection, so the server cannot know whether the client
    holds Playwright — the offer is conditional and points at the playbook
    rather than asserting a capability.
- **Onboarding workflow** (`workflow.py`): `kb_ingest_resume` (drafts) →
  `kb_approve_points` (the user's gate) → `create_base_resume_from_kb` →
  `render_pdf` walks ingest-several → KB → role-targeted bases with zero
  in-house LLM (the client agent parses/authors; ingest the CURRENT resume
  first — over single-source MCP calls `_seed_profile` is first-write-wins).
  Ingest hints are offer-only (multi-resume loop, same mass-capture lesson as
  `score_ats`); `brief=true` suppresses before any settings read. Hint options
  carry only verbatim-callable args or none at all, offer prose is derived
  from the filtered options, and composers take the requested state explicitly
  rather than inferring intent from results. Scoring is mentioned in prose,
  never as an option — it needs a `job_id` no composer can know.
- **In-app chat** (`services/chat_agent.py` + `chat_tools.py`): a distinct
  toolset (resume edit, KB capture, template admin including the mutations MCP
  deliberately lacks). Its resume-edit tool runs the SAME pipeline as the REST
  endpoints (`services/resume_ops.py`); scope checks and ToolError mapping
  remain chat-side. **Chat interaction model** ("chips in, cards out"):
  assistant prose renders Markdown (content passed to tools stays plain);
  `propose_edits` stages ANY typed-op set as an approval card (`proposal_ops` —
  validated + scope-checked at propose time, applied via the standard `/edits`
  PATCH); proposal cards persist their resolution via `PATCH
  /api/chat/messages/{id}/card-state` (`meta_json.card_state`, 409 on
  conflicting re-stamp) and card SSE events carry `message_id` (tool row
  persists before the card event); `ChatSelection` is kind-tagged (`resume` |
  `kb_entity`, missing=resume) — KB chips pin context and never constrain the
  resume scope guard; three read-only analytics tools (`analytics_activity`,
  `analytics_gap_frequency` incl. build-areas, `analytics_base_summaries`)
  answer job-search questions in chat. **Pinned-resume resolution**: the pin is
  a HINT, not a guard — it reaches the model as one line of the ephemeral
  context block; the enforced guard is `check_ops_in_scope` over selection
  PATHS (which needs a pin only because the scope picker is fed the pinned
  resume). The composer resolves it once per session — session
  `context_json.target_key` if stored, else the most recently updated base
  resume — and must READ `context_json` back on reopen, not only write it on
  send (write-only silently dropped the pin). The pin FOLLOWS whichever base
  actually changed via both landing paths: the streamed `change_card` and an
  applied `propose_edits` card (which PATCHes directly and emits no stream
  event — `EditProposalCard` takes `onApplied`). Selections drop on a real
  switch: they are paths into the resume they came from. **Social posts**: chat
  drafts LinkedIn/social posts as copy-out markdown — no card, no persistence,
  the transcript is the history — grounded via read-only `get_career_context`;
  conventions live in chat_system.txt. Prompt-file changes need the DB
  `prompt.chat_system` Setting row reset to take effect (settings page → reset,
  or delete the row); untouched rows are resynced by migration on deploy
  (86ac8658395f precedent).
- **Persona draft** (`POST /api/settings/persona/draft`): one smart-model
  proposal grounded in the whole-KB compose/context + typed job preferences.
  Returns `{draft}` and persists **nothing** — Profile puts it into the
  persona editor as a dirty edit; only `PUT /api/settings/persona` saves; an
  empty Career KB 422s with an import-first message.
- **Chrome extension** (`extension/`): MV3; the **side panel** (`panel/`) is the
  ONE surface — toolbar icon (`openPanelOnActionClick`) and hotkey
  (Alt+Shift+J → `sidePanel.open`, guarded: that method is Chrome 116 and the
  minimum is 114) both open it. Five-stage rail — Job → Score → Resume →
  Fill → Track — whose active stage is INFERRED from the store by
  `ns.decisions.stageFor` every render, never set by what was clicked. A stage
  is "which question is still open", so `hasForm` is NOT one of its inputs:
  the base-as-is claim skips Score/Resume on a posting page too,
  and whether filling can happen HERE is decided at the Fill body (it says to
  open the employer's Apply page) and at the footer (`primaryRefused` — no
  Start fill without a form; a late detect yes gives it back, moving no stage).
  ONE row
  shows a body: the active one, or a row the user reopened — DONE Score/Resume/
  Fill always, DONE Job only for the user's own pick (`claimed`; un-pick/switch
  live there), and a row skipped by a CLAIM (`choiceSkipped` — base-as-is'
  Resume row names the choice and carries its withdraw; a skip the path computed
  is no door) — via `card.revisit` (view state, never persisted, dropped when
  the stage moves or the page facts reset); it rewinds no tick, the active row
  keeps its styling, the footer's one primary follows the OPEN row.
  The panel document is a family of scripts (panel.html owns roster and order):
  `panel.js` owns the store, the loaders and the generation guard; per-STAGE
  bodies (`panel/stages/*.js`) get a per-render SNAPSHOT (`stageContext`),
  per-CONCERN actions (`panel/actions/*.js`) a HANDLE with one `write(patch)`
  door (`actionStore` refuses a key the store lacks; `actions/during.js` is the
  one `busy` span they all read). `card` is never published, and each family's
  roster (`stages.js`/`actions.js`) THROWS at boot naming any part whose script
  tag is missing. `shared/` is what both worlds load: `decisions.js` (pure
  decisions — and since R-C the ONE home of every rule the card once duplicated),
  `choose.js` (routing, the /choose batch, `rest_fill` shaping, `QUESTIONY`'s ONE
  definition) and `guided-run.js` (the runner, transport injected).
  **Sender model:** a panel has no `sender.tab` (that is the
  discriminator) and NAMES its bound tab, so sw.js's `sender.id !==
  chrome.runtime.id` is the WHOLE of provenance for a tab-less sender;
  `detect_page` joins `extract_job_posting` as a frame-0 read because the panel
  runs in no page. Content scripts are the fill engine and the field work and
  NOTHING else since R-C deleted the floating card, so `fanoutTab`'s
  content-script branch is a written rule with no caller. Two engine rules hold
  across every writer: the COMMIT GESTURE (`visitControl`/`leaveControl` + the
  `guided`-prefixed and injected copies) wraps everything that is not a text
  commit, because a `<select>` set through the native setter and a radio driven
  by `click()` fire no focus events, so Workday's required-field validation
  never ran; and `agent.js`'s `attachableFileInputs` is ONE definition of "a box
  a résumé could go into", read by `attachResumePdf` AND `detect_page`'s
  `fileInputs` count, which is what lets the panel offer an attach it can
  honour. The bridge storage key `widget.session` must NOT be renamed — that
  drops every live entry — and `restoreSession`'s `if (entry.applicationId)`
  guard is the condition of writing an application-less entry at all. Orphan
  keys are swept once on panel boot. **`extension/README.md` owns the rest.**
- **Guided fill** (design: `docs/plans/2026-08-16-guided-apply-design.md`):
  the panel's **Fill** stage — "Start fill" → `panel_prepare` (the
  gesture-backed injection; `preparePage` is the only other injector) → the
  runner. The mode control picks `aiAssist` (`fillMode` in
  `storage.sync`, default assist); its progress rows are `reconcileFill`'s
  buckets plus the run's own writeResults-minus-residue, and the EEO row is the
  BACKEND's standing consent, never a local toggle. It claims `done.fill`
  (`touched`) only when a run both wrote something and left nothing open — a
  tick takes the open-fields list off screen, so a partial fill keeps the user
  on the step; a wizard's LATER pages are reached by REOPENING the ticked row,
  and `startFill`'s per-run clear keeps that re-run's report its own. Per stage
  ONE runner (`ns.guidedRun.runGuidedFill(deps, {aiAssist,
  applicationId})`; `aiAssist: false` skips `/choose` and residues the whole
  remainder) runs rule pass → collect → one batched `POST
  /api/autofill/choose` (fast model, qid-keyed, ≤40/call; the option guard
  lives SERVER-side only — any answer not among rendered options, invented qid,
  or skipped qid collapses to abstain) → `ns.guidedWrite` sequenced by widget
  shape with ONE bounded retry. EXCLUDE'd controls a rule tried and missed
  become RETRYABLES (`ns.lastRuleAttempts`, in-memory per run) routed straight
  to `guidedWrite` — identity data never reaches `/choose`. Readback is
  timer-sampled and never defaults to failure: unconfirmable is
  `filled_unverified`, not `not_stuck`. Navigation and submit stay human.
- **Streaming chat** needs the OpenAI streaming tool-call wire shape (OpenAI,
  or Gemini via the OpenAI-compat URL); eligibility is the tools probe.

## 8. Frontend conventions

Reference tier, like §4: consulted while working in `frontend/`, not read
for orientation. Lives in
[`docs/frontend-conventions.md`](docs/frontend-conventions.md) — layout and
sidebar-gutter rules, Tailwind v4 tokens, a11y and focus behaviour, naming,
and the copy rules, each with the failure mode that bought it. Code citing
"§8" lands here.

## 9. Dev & test environment

- Use the Python interpreter from the backend's virtual environment; backend installed editable
  (`pip install -e ".[dev,mcp]"` — beware the stale-`.pth` gotcha: it can pin
  `app`/`mcp_server` to an OLD worktree for anything run outside a repo dir,
  including the Claude Desktop MCP server; reinstall + restart client to fix).
- Postgres runs in the compose stack's `postgres` service on host port
  **55432**; nothing on 5432 (the non-default port is deliberate, to dodge any
  locally installed PostgreSQL). The compose-default dev DB is `maestro_cs`
  (`POSTGRES_DB` in `.env`); create `maestro_cs_test` beside it for the test
  suite. If more than one stack or checkout runs on a machine, they differ by
  host ports (`*_HOST_PORT` in each `.env`) — go by the port, not the name.
- **ATS calibration** — the engine is corpus-tunable, so measure, don't
  argue. `scripts/ats_snapshot.py` prints a ranking table;
  `scripts/ats_calibration.py` writes a machine-readable snapshot and diffs
  two (`DATABASE_URL=…55432/maestro_cs BASE_RESUMES_DIR=<main-checkout>/
  base_resumes python -m scripts.ats_calibration snapshot before.json`). It
  pins `as_of` and groups contribution drops by match-form transition: a
  CHANGED form is a deliberate reclassification, an UNCHANGED one is the shape
  a real regression takes (exit 1). Base-resume JSON is gitignored PII living
  only in the main checkout — a worktree run needs `BASE_RESUMES_DIR`;
  snapshots store JD skill names only, never resume text.
  `python -m scripts.ats_calibration monotonicity` (same env) asserts "adding
  true evidence never lowers the score" over the whole corpus — run it after
  ANY matcher or tier change, not just a scoring-weight one.
- Backend tests: `TEST_DATABASE_URL=postgresql://app:app@127.0.0.1:55432/maestro_cs_test`
  then `python -m pytest tests/ -q` from `backend/`. Suite must stay green.
- **Deploying = rebuilding BOTH images** (from the MAIN checkout): `docker
  build -t maestro-career-studio-backend backend/` AND `…-frontend frontend/`,
  then `docker compose up -d --no-build --force-recreate backend frontend`. A
  frontend-only change still needs the frontend image rebuilt — a stale image
  once made fixed UI look broken for a whole review.
- Never verify new code against the docker-compose stack (old images). Launch
  fresh: uvicorn on a free port with data-dir env overrides +
  `/Library/TeX/texbin` on PATH; frontend `API_PROXY_BACKEND=... npm run dev`.
  The maintainer keeps the full recipe in a local `verify` skill (not shipped
  in this repo); the browser-pane gotchas worth knowing: DPR mismatch → use
  ref clicks; toasts overlay the send button.
- **Two dependency sources, on purpose.** `pyproject.toml` keeps `>=` floors
  (what `pip install -e ".[dev,mcp]"` resolves); `backend/requirements.lock`
  is hash-pinned and is what the **container image** installs, so a published
  image is reproducible. After changing a dependency, regenerate the lock **on
  the target platform** (command in `backend/Dockerfile`; pip-compile on
  macOS/3.13 produces wrong pins). CI's `dependency-audit` runs `pip-audit`
  against the lock — a new advisory failing an unrelated PR is intended.
- **No Langfuse stack ships here** (the bundled compose file had fixed
  default secrets). `services/tracing.py` and the three `LANGFUSE_*` settings
  stay: tracing points at any instance the user runs; `langfuse_host` defaults
  to empty (the SDK falls back to Cloud).
- Alembic revision ids are hand-written fake-hex and COLLIDE easily — generate
  with `uuid.uuid4().hex[:12]`.
- **SYSTEM.md gate**: `python3 scripts/check_system_md.py` (CI `docs-gate` job)
  enforces this file's header contract and FAILS (not warns) on: the size
  ceiling; a `(YYYY-MM-DD` date in §1–§10 or in any reference-tier file; a
  shipped item left in §11; a section over its line budget; and any §6
  invariant whose enforcement pin in `.system_md_enforcement.json` has lost its
  file or its symbol — the "docs promise what the code no longer does" class.
  Re-baselining requires `--update-baselines --reason "<text>"`, recorded in
  `.slopledger.json`. It anchors on the repo root as the script's own parent
  directory, deliberately: a walk-up search finds the MAIN checkout's copy when
  run from a worktree and validates the wrong file.
- **On merge, re-verify the doc.** Two lanes each update the sections they know
  about, and the merge can produce a file describing neither branch — this file
  is least accurate exactly when the most agents are reading it. After any
  non-trivial merge, list the SYSTEM.md sections whose subject files changed on
  BOTH sides and re-read each. The enforcement pins catch the worst subclass
  mechanically; nothing catches the rest but this checklist.
- **Slop ratchet.** Per-surface `.slopconfig.json` + committed
  `.slop-baseline.json` in `backend/`, `frontend/`, `extension/`. After
  changing a surface, the maintainer runs `python3
  ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check <surface>` from
  the repo root (maintainer tooling, not shipped here — contributors are not
  expected to run it; see CONTRIBUTING) — non-zero exit means a metric
  regressed past baseline; fix or re-baseline deliberately with a reason. **RUN EVERY SURFACE YOU TOUCHED AND
  NAME EACH ONE IN THE CLAIM.** A change to one surface moves another's numbers
  routinely — the extension's tests live in `backend/`, so an extension feature
  is a backend ratchet event — and an unnamed "slop ratchet OK" is the shape of
  the 2026-08-17 false green: three commit bodies claimed it having checked
  `extension/` alone while `backend/` was red throughout. **`complexity_hotspots` is a COUNT,
  and counts move for reasons that are not decay — re-baseline it rather than
  chasing it.** A function is a hotspot if `cc >= 10` OR `>50 source lines` OR
  too many params, so the count rises when the codebase GROWS, when you ADD
  TESTS (`gate_test_loc:false` exempts test LOC but nothing exempts test
  complexity), and — the trap — when you DECOMPOSE a monster: splitting one
  cc=46 function into named pieces can move the count UP. Judge erosion by
  hotspot density per KLOC and the worst offender's cc, not by the count; the
  count's job is to make you look, not to be driven to zero. The other metrics
  are honest ratchets — orphan LOC and duplication only move when something
  really regressed. Scan a SURFACE dir, never the repo root: the analyzer roots
  module names at the scan path, so a root scan can't resolve `app.*` imports
  and reports the whole backend as orphaned. jscpd is optional; without it the
  duplication metric is skipped, the rest still gates. The extension's
  allowlisted clones are the
  documented injected twins — R-C removed the four widget→panel pairs, so a NEW
  clone there is a real finding. Read
  the reason strings before trusting a green: the matcher pairs FILE NAMES by
  substring, so a rule naming a file on either side also hides that file's own
  SELF-clones. `allowlisted_clones` is PRINTED, never gated — a new clone
  landing inside an allowlisted pair raises that number silently while
  `clone_count` stays 0, so check it by eye. Optional graph signals read
  `graphify-out/graph.json` (gitignored): regenerate with `graphify extract .
  --no-cluster --code-only` (PyPI `graphifyy`).

## 10. Design-decision record

**The dated design docs are NOT published.** They live in the upstream private
repository; this file is the public record of what they decided (they are agent
handoff scripts — publishing them would ship instructions for a machine no
reader has). This section carries the lineage: which decision superseded which.

Key lineage: 2026-04-22 greenfield → 2026-05-29 jobs/applications consolidation
→ 2026-07-06 deterministic ATS gap workflow (fit_scores deprecated; dropped in
migration `09265240aade`) → 2026-07-08 tailoring refinements → 2026-07-12/14
health gates → 2026-07-14 career KB (sidecar) → **2026-07-15 applications
workflow simplification + UI changeover** (D1–D13; the audit findings C# and
review fixes referenced throughout this file) → 2026-07-15 parallel delegation
tasks (MCP apply-package tools; health-check-v2 override UI) → 2026-07-16 UI
polish (Career KB + extension Q&A) → **2026-07-16 custom resume sections
(`extra_sections`) phases 1-2** (fixed-core-plus-typed-extras, then versioned
ATS evidence + stable-key gap placement) → MCP guided tailoring (caller-authored
ops, hint envelope) → MCP onboarding: reversed "approving from MCP is
unrepresentable" — a draft gate needs an approver wherever review happens, and
agent transcription is NOT the verbatim-file exception, so ingest lands drafts
and consent-gated `kb_approve_points` is the one approval path from MCP.

## 11. Known deferred items (priority order)

**Item numbers are stable, not positional.** Code and migrations cite
"§11 item N" from a dozen places, so new items APPEND here and shipped
items are deleted in place — renumbering silently invalidates every
citation. Priority lives in the item text, not in the ordinal.

1. Extra-section op **payloads** stay loosely typed. Op *kinds* are a single
   source (`schemas/resume_edit.py`: 16-kind discriminated union with
   `op_kinds()` / `op_scope()` / `render_ops_brief()` / `render_ops_shapes()`;
   chat imports those, MCP builds `edit_base_resume` from `render_ops_shapes()`
   at import, parity tests in `test_resume_edit_reference.py`). Residual:
   `add_extra_section` / `replace_extra_section` `value` is `dict[str, Any]`
   and ExtraSection validation lives in the service
   (`resume_edit._validate_extra_section`), same pattern as `AddEntry` — a bad
   extras payload is a 400, not a schema 422. Nested extra-section
   entry/bullet ops remain item 20.
2. One post-render readiness pipeline ("Ready to apply" gate: health, em-dash,
   pages, contact checks on the exact rendered artifact), consuming the shared
   rasterized preview + slim MCP `get_rendered_pdf` metadata. (The JD-level
   half — stated requirements vs profile — shipped as the knock-out pre-scan,
   §5 step 3; this item is now only the post-render artifact pipeline.)
3. Base-score staleness on from-base: re-score only when the base resume's
   updated_at is newer than the score row — never unconditional re-scoring.
4. JD promoted-field correction before gap freezing (today only source_url is
   editable) + score provenance (engine/config version) surfaced in the UI.
5. Server-side pagination for the tracker (client caps at limit=500 today).
6. Chat KB document provenance: `ChatAttachment` stores extracted text only, so
   a chat-added document never becomes a KB source document — persist bytes, or
   hand chat a `kb_ingest_document` tool.
7. Contact URLs in the shared `_header.tex.j2` still go through `latex_escape`
   (the `~` corruption class, needs `latex_escape_url`); the fix touches BOTH
   templates, so it needs cover-letter regression tests.
8. Agentic job-search phase 2: JobBoard registry (kind/tags/last_checked),
   SavedSearch model, Job triage state, cross-session search-run logging.
10. Work-auth warning CODES: `services/job_search_brief` still reads the two
    legacy keys and pattern-matches loose strings in `warnings[]`; it should
    understand the typed `WorkAuth` shape.
12. Extension identity-combobox reconciliation (ARIA-widget overwrite is
    riskier), and block-scoped education-vs-employment rule matching (`not:`
    label guards miss unheaded education containers).
13. Quick-tailor: derive `applied` from the committed resume DIFF, not planned
    intent; employment-blocks v2; typed `quick_tailor_profile` validation.
14. Telemetry v2: option-set fingerprint + normalization; capture-session
    record for per-site/per-kind saturation; failure-count ranking + Analytics
    drill-down/export; label/option-text redaction; summary pagination.
15. Typst phase 2 (the LaTeX retirement itself is §13): `typst query` AST
    introspection over source-text capability heuristics; web engine picker;
    in-product .tex→Typst conversion (expose `scripts/template_parity.py
    --compare` as a backend tool).
16. Onboarding intake: entity resolution ACROSS kinds (a certificate merges
    into its experience entity, not a sibling); a re-runnable "import more";
    bounding LLM cost (file cap of 10 in `services/kb_import`).
17. ATS follow-ups: (a) alias/adjacency vocabulary via an OFFLINE human-gated
    miner over stored `extracted_json`, guarded by
    `SkillMatcher._tokens_contained` — until then the JD side is unenforced;
    (b) education-as-evidence stays OFF pending a dot-stripping degree
    normalizer (school + graduation year stay out of score and prompt either
    way); (c) lexical-vs-semantic cert attribution, 1 row in 6,993 — re-check
    if it grows; (d) stamp `as_of` + `jd_extraction_hash` on `AtsScore` and
    add both to `compare()`'s guard.
19. Auto-apply follow-ups: `source` threading through the explore builders;
    Telegram consent channel (rejected for v1); extension-less CDP fill (HARD
    constraint: backend CORS must never admit ATS/web origins).
20. `extra_sections` remainder: calibrate the `extra_only` multiplier; nested
    extra-section entry/bullet ops are still unbuilt.
21. MCP onboarding follow-ups: `near_duplicate_of` hints in the ingest report
    (normalized-distance vs existing points, so the agent can retire one copy
    without the LLM clusterer); a batch `sources` variant of
    `kb_ingest_resume` (single-source calls make profile seeding
    order-dependent); a consent story for `_seed_profile`/`_merge_skills` —
    profile contact and skills have no draft state yet compose onto EVERY
    base; `enabled: false` entries still ingest (LLM-path parity, revisit).
22. Guided Apply follow-ups (design doc has R2 stepper + R3 vault): checkbox
    collection needs its own safe design (group-level collection, legend-level
    policy screening, mirroring radios; `skipped_checkbox` holds until then);
    auto-advance toggle; per-ATS selector blueprints; the essay path onto
    qid-keyed `/choose`; `guidedIsListboxButton` stays looser than the two
    pinned strict discriminators (it rechecks vetted elements only).
23. **Five §6 invariants have no enforcement pin** — `inv-honesty`,
   `inv-tailor-vs-edit`, `inv-autofill-telemetry-no-values`,
   `inv-eeo-standing-consent`, `inv-pdf-word-spacing` (listed under `unpinned`
   in `.system_md_enforcement.json`). Each is a rule the gate cannot defend:
   it survives only as long as everyone remembers it. When next working in one
   of those areas, either add the pin or demote the rule to a convention note.
24. Surface enum-coercion warnings from `schemas/job_extraction._coerce_enum`
   through the jobs-ingest response, so `store_extracted_jd` callers see that
   input X was stored as `unstated` (audit 2026-08-22, finding A1).

## 12. Gotchas that have bitten before

- **`autoflush=False` sessions**: two `session.merge`s that canonicalize to the
  same PK in one flush both INSERT (no dedup) → IntegrityError. Dedupe in
  Python first (see `_insert_skills`).
- **Pydantic error mapping order**: `ValidationError` subclasses `ValueError` —
  catch it FIRST or 422s silently become 400s (render endpoint comment).
- **Transient response attrs**: `already_existed` (Job) and `health_warning`
  (TailoringSession) are instance attributes set after refresh, never columns —
  don't "fix" them into the ORM.
- **score_target(result=...)**: passes a precomputed engine result to persist;
  the double-run it replaced was audit finding C18 — don't re-add a second run.
- **Studio external-edit dirty-guard**: StudioEditor keys on the *adopted*
  server snapshot, not live `customized_json`; external edits auto-adopt only
  when clean, and Save flags the next server key so Save→render→re-score
  adopts banner-free.
- **An expanded hit target can cover its own label**: `after:-inset-2` inside
  an `h-5` chip put the remove target over the chip's own text, so clicking to
  open cleared instead. Expanded targets need room around them, not just
  under them.
- **MCP clients truncate tool descriptions at ~2048 dedented chars**: keep
  `__doc__` ≤2000 (ratchet test) or put the fact on a param
  `Field(description=…)`.
- **Worktree subagents**: agents may edit the MAIN checkout instead of the
  worktree — always hand them absolute worktree paths and verify with
  `git -C <worktree> status`.
- **Ports**: 8000/8001 may be squatted by unrelated apps or stale servers —
  verify identity via `GET /openapi.json` `info.title == "Maestro CS API"`.
- **Model catalog is seeds ∪ extras** (`MODEL_OPTIONS` ∪ `llm.extra_models`):
  `GET /api/settings/openai` returns the merge; deleting an id a role still
  uses is 400; hosted chat is probe-gated (stored tools=false blocks; unprobed
  is allowed through, matching `require()`).
- **JSON mode is capability-gated**: `response_format=json_object` goes out
  only when `llm._json_mode_supported()` (other servers may hard-400 on the
  field); `llm._extract_json_object` salvages fenced JSON.
- **Check model capability in the ROUTER, never inside `run_turn`**: `run_turn`
  is a generator — anything it raises fires after the SSE headers are out and
  reaches the browser as a truncated stream. Capabilities are probed on save
  (`llm_capabilities.probe()`); `require()` raises `CapabilityMissing`;
  unprobed models are never blocked.
- **A probe must issue the SAME call as the surface it measures**: same client
  (`llm.get_chat_client`) and the same per-model kwargs from
  `llm.completion_extras` (the one site for such rules). A probe that
  re-implements the call measures one the app never makes, and its stored row
  then SHADOWS reality — a false tools=No once 422'd every chat message.
- **LLM provider outages are ONE exception type**: `llm.py` normalizes them to
  `llm.LLMProviderError`; `app.main` maps it to 502 + the provider's message
  for every router. Never catch `openai.*` in routers; plain `RuntimeError`
  means a LOCAL render/compile failure and must stay a 500.
- **Explore charts live under Analytics**: `/explore` is a 307 to `/analytics`;
  the charts live in `frontend/components/charts/` and `…/analytics/`, not an
  `app/explore/` route.
- **`delete-orphan` cascade vs bulk re-point**: a bulk `update()` that moves
  children off a parent does not refresh the parent's already-loaded
  collection, so a following `session.delete(parent)` cascades away the rows
  just moved — expire the parent between the two (`career_kb.merge_entities`).

## 13. Active migrations & deprecation ledger

**The rule.** A row is born the moment work lands that SUPERSEDES something
without deleting it; it dies when the old path is removed. Every row names a
**removal trigger** — the observable condition under which the old path gets
deleted. If you cannot state one, it is not a migration but two ways of doing
the same thing: a design bug to fix, not a row to file.

**Not §11.** §11 = work NOT YET BUILT. §13 = work built TWICE, where one copy
must die. A §11 item that turns out to be a removal plan belongs here.

**Machine-checked.** Rows with executable triggers are mirrored in
`.slopledger.json`; the maintainer runs `python3
~/.claude/skills/ai-slop-detector/scripts/ledger_check.py . --strict` (same
maintainer tooling as the slop ratchet, not shipped here) to detect drift. Keep row ids identical in both places; rows without predicates
are verify-by-hand. That file mirrors TRIGGERS only — the why and the traps
stay here.

**This section exists so SYSTEM.md can shrink.** When a row lands here, CUT
the superseded prose from its home section and leave a one-line pointer
("migration state: §13 `<id>`"). Delete the row when the old path is gone —
never leave green rows.

Status: `both-live` (both reachable, old still default) · `new-is-default` (new
path is canonical, old survives as fallback/backup) · `blocked` (trigger cannot
be evaluated until a named prerequisite lands) · `ready-to-cut` (trigger met).

**Re-verify triggers on a schedule** — a stale `ready-to-cut` is worse than no
row, because it claims a deletion is safe without evidence. `.slopledger.json`
+ `ledger_check.py --strict` do the mechanical part. Cut rows and their
evidence live in `git log SYSTEM.md`, not here.

| id | old → new | status | removal trigger | effort |
|---|---|---|---|---|
| `typst-default-flip` | seed `default` (LaTeX Classic) → seed `typst-classic` | both-live | **HELD by owner 2026-08-09: LaTeX stays, both engines remain first-class.** This is a longer park than 2026-08-02's, not a cancellation — the row survives because the trigger is still reachable, but nothing is waiting on it and `latex-render-path`/`texlive-layer` stay blocked behind it indefinitely. Header defects fixed (Typst `ulink()`; LaTeX separator space), DB rows re-synced. **The CLEAN 8/8 parity corpus predates 2026-08-08's extractor swap** (PyMuPDF→pypdfium2, forced by the Apache relicence), so those numbers were taken with a different measuring tape — re-run the corpus before acting on them. Then repoint `_bootstrap_default` (template_registry.py:131); a runtime `set-default` is NOT enough, seeding re-mints the LaTeX default on every fresh install. | medium |
| `latex-render-path` | `pdf_render` latex branch + `*.tex.j2` → typst branch + `typst_classic.typ` | blocked | `select count(*) from templates where engine='latex'` = 0 **and still 0 after `GET /api/templates`** (which re-runs `ensure_seed_templates`); cover letters ported off `compile_cover_letter_pdf`; no surface (web, chat, MCP, STARTER_SOURCE) can mint a latex row. Blocked on `typst-default-flip`. | large |
| `texlive-layer` | minimal TeX Live layer (`backend/Dockerfile`) → `typst==0.15.0` in-process | blocked | Layer is already slim (install-tl `scheme-basic` + 18 tlmgr packages) and XCharter is vendored at `backend/app/assets/fonts/xcharter/` (keep the Bitstream Charter notice alongside; `settings.typst_font_paths` defaults there, so typst no longer reaches into texlive). The remaining FULL cut requires only: `grep -rn pdflatex backend/app` returns only comments. Blocked on `latex-render-path`. | medium |
| `chat-selection-kind` | untagged resume chips → `ChatSelection.kind` (`resume`\|`kb_entity`) | both-live | All three scope-picker constructors emit `kind:"resume"`, THEN zero `chat_messages.meta_json->'selections'` elements lack a `kind` key. | small |
| `autofill-education-shape` | single-object `education`, coerced in 2 clients → list, normalized server-side | new-is-default | `GET /api/settings/autofill` returns `education` absent or an array for a pre-normalization profile. Cut the frontend coercion first, the extension one release later. | small |
| `autofill-work-auth-shape` | `work_auth.authorized_to_work` + `requires_sponsorship` (two timeless booleans, stored "yes"/"no") → typed `WorkAuth` (`schemas/autofill_profile.py`: `status`, `authorized_now`, `sponsorship_now`, `sponsorship_future`, `authorization_expires_on`, `countries_authorized`) | both-live | Delete when no raw-profile reader uses either legacy key. Today's storage readers are `services/autofill_profile.py`'s legacy branch, the Settings editor's legacy-on-edit bridge, and the extension's own copy of the dual-read (`content/autofill.js:51,56` in the profile normalizer; moved from agent.js at the phase-2 split). `job_search_brief`'s identically named response fields are a frozen outward compatibility projection from typed `authorized_now` / `sponsorship_future`, not a legacy reader, and do not block removal. ALSO `GET /api/settings/autofill` must return a `work_auth` carrying neither legacy key. Then delete the legacy branch of BOTH `autofill_profile.get_work_auth` and the extension's `w` binding. Per `autofill-education-shape`: cut the frontend first, the extension one release later. | small |
| `job-location-raw` | `jobs.location` (dual-written) → `location_raw` + city/state/country | both-live | Stage 1 (schema shim + `.location` property) already met. Stage 2: no reader of `jobs.location` remains, then `op.drop_column`. | small |
| `explore-redirect` | `frontend/app/explore/page.tsx` → `/analytics` | ready-to-cut | Owner overrules the recorded keep-decision. Safe: it is a 307, not a 308 — no browser cached the mapping. | trivial |

**Row notes** (only where the trigger hides a trap):

- `typst-*`: strictly ordered flip → delete-latex → drop-texlive (the font is
  vendored, so the old drop-the-layer-changes-the-font trap is closed).
- `latex-render-path`: alembic `9a0404101e5f` reads `resume.tex.j2` off disk
  during `upgrade()`. Deleting the file breaks first boot on a fresh clone.
- `chat-selection-kind`: inverted today — the branch four comments call "legacy"
  is the only form the frontend emits, and `kind:"resume"` is unreachable. Until
  stage 1 ships, those comments are actively misleading.
- `autofill-work-auth-shape`: two traps. (1) `sponsorship_now` has NO legacy
  source and stays `None` on purpose — defaulting it from
  `requires_sponsorship` answers the OPT case wrong (no sponsorship NOW,
  needed later); unknown must stay unknown. (2) `job_search_brief`'s public
  legacy-named response fields are a frozen projection of the typed reader,
  not a storage-migration blocker.
- `job-location-raw`: `JobSummary` exposes ONLY the old field (no `location_raw`),
  so the list endpoint is the hardest blocker to dropping the column.
- `explore-redirect`: contradicts a recorded decision to keep it. Needs an
  explicit overrule, not a silent delete.

**Not migrations — do not re-file these here** (each was proposed as a row and
rejected): the 4-way application-status vocabulary and the 3-way
`quick_tailor_profile` shape are hand-synced by design; the `/api/explore`
prefix and 7 MCP tool names are a deliberately frozen public surface after the UI
rename; the typed-op vocabulary lives in `schemas/resume_edit.py` (item 1 tracks
only the extras-payload residual) and is not a migration. Cross-boundary duplication (a Python enum and its TypeScript
mirror) is never a ledger row — it needs a contract test, not a deletion. The two
seniority lists are NOT a subset relation and must not be merged — see §4
AtsScore, "Rank markers are domain data"; merging them would be a scoring bug.
