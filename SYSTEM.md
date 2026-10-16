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
> Last full revision: 2026-08-28, doc↔code audit (§6 consent invariants, counts, paths,
> §13 work-auth readers). §13 is machine-checked via `.slopledger.json`; the whole file via
> `scripts/check_system_md.py`.

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

A single-user job-application copilot: capture job descriptions, score base resumes against them with a
deterministic ATS engine, walk a gap-analysis workflow, LLM-tailor the resume, render a LaTeX PDF, generate the
apply package (cover letter, screening answers), and track every application from Saved to Accepted. Three
surfaces drive the same backend: a Next.js web app, an MCP server (Claude Desktop et al.; on screen its clients
are **connected agents**), and an in-app chat agent (the **Assistant**); the Chrome extension (the **Companion**)
captures and fills from job pages. The web app is desktop-only (1024px and up; checked at 1280 and 1024, never
at phone widths; §8's reference file says what stays best-effort below that).

## 2. Repo layout

```
backend/
  app/
    main.py            FastAPI app; REST under /api/*, MCP at /mcp and /mcp/{profile}
    config.py          settings; data-dir paths (container-absolute; override *_DIR locally)
    db.py              SQLAlchemy; sessions use autoflush=False (see §12)
    models/            ORM (application, job, tailoring_session, ats_score, resume_version, base_resume, …)
    schemas/           Pydantic request/response models
    routers/           HTTP endpoints, one module per resource (applications, jobs, tailoring_sessions, ats,
                       base_resumes, templates, qa, career_kb, chat, autofill, proposals, settings, …)
    services/          business logic (ats/, tailoring_session, gap_analysis, kb_import, application_writes,
                       engines (the ONE probe), pdf_render (dual-engine: pdflatex + typst), jd_extraction,
                       resume_lint, resume_voice, health_*, chat_agent + chat_tools, transcript (chat rows as
                       neutral parts; NULL `parts` = legacy row), llm_providers/ (neutral LLM types, errors,
                       registry (model id to provider), OpenAI-compatible, Gemini and Claude adapters),
                       attachment_extract (bounded DOCX/PPTX + notes; decks are documents),
                       autofill_choose + autofill_slots + jev (Companion fill), resumes_folder (visible PDF copies), …)
    automations/skills/  the agent prompts, one <name>/SKILL.md each: the Automations
                       source of the Automations page; indexed by docs/skills/README.md
    templates/         six seeded resume designs + both cover-letter sources (licenses: THIRD_PARTY_NOTICES.md)
    tools/             operator tools, `python -m app.tools.<name>`: backup_db
  mcp_server/          FastMCP registry + http.py per-profile ASGI endpoint; client.py httpx → REST
  maestro_cs/          the `maestro` command (uv install, §9): CLI, supervisor, home layout, update, connect, stdio bridge
  migrations/          alembic: the SQLite chain, baseline 871d0425b64c + revisions (ids: §9; §12 has the revision-id gotcha)
  tests/               pytest on a throwaway SQLite file, no service; mcp_server/tests/ uses respx (no DB)
  scripts/             calibration + parity tooling (ats_*, template_parity, health_golden, fill_trace), run from backend/
frontend/              Next.js 16 (App Router) + React 19 + Tailwind v4 + Base UI-flavored
                       shadcn. AGENTS.md: read node_modules/next/dist/docs before writing code.
data/                  the database: maestro_cs.sqlite3 + its -wal/-shm sidecars (bind-mounted, PII)
base_resumes/          on-disk resume data (<slug>.json) + rendered tex/pdf output
applications/          rendered per-application artifacts (Company_Role_YYYYMMDD_<idprefix>/)
extension/             browser-capture extension (posts pre-extracted JDs)
scripts/               setup-mcp.sh (deprecated stdio, §13), update.sh (Docker update, §9), build_wheel/check_wheel + uv smoke/upgrade checks (§9)
.claude/settings.json  shared Claude Code settings (enables the Superpowers plugin); the only tracked file under .claude/
```

## 3. Architecture at a glance

```
 paste JD ─┐                          ┌─ web UI (Next 16, react-query)
 extension ─┼→ jobs router → Job row  ├─ MCP /mcp inside FastAPI (88 REST wrappers)
 MCP ingest┘        │                 └─ chat agent (chat_tools.py — separate toolset)
                    ▼ ATS engine (deterministic, LLM-free)  →  AtsScore rows (base upsert / tailored append)
                    ▼ TailoringSession (frozen gaps → resolutions → LLM tailor ops)
                    ▼ Application (customized_json draft) → LaTeX render → PDF + preview PNGs
                    ▼                              ▼
        status tracking (StatusChip)        QA router (cover letter / answers)
```

`data/maestro_cs.sqlite3` (SQLite, WAL) holds rows and local sync clocks; ORM flushes stamp jobs/profile, including imports and both sides of moves. A job still at revision 0 is stamped from that clock when this copy pushes or lists its jobs. Deleted jobs leave tombstones; Core writers touch their subtree (`services/sync/hooks.py`; the write guard is §6
inv-flush-guard). Resume JSON/rendered files stay on disk (`base_resumes` row + file required); job-site login: `settings/secrets/` (§6). A uv install keeps all of it in one per-user folder (inv-one-home). **LLM calls** go through the front door `llm.py` (`call_openai`, key getters; four keys, env keys as fallback). `llm_providers/registry.resolve` routes a model id by catalog tag, then keys/prefix, to an adapter (OpenAI-compatible incl. custom servers and the privacy-locked OpenRouter preset, Claude, Gemini); chat streams through the same adapters.

**Sync** is optional, on only while a key file exists (`docs/sync-setup.md`): the laptop owns the profile, each job has one owner
(docs/entities/job.md), nothing merges (inv-one-writer-ownership). The always-on copy drives: `sync.sh` (cron; `--now` forces a round) or MCP `sync_now` asks its
backend for a round (`POST /api/sync/round`, `services/sync/round.py`), which calls the laptop's `/api/sync/*` on the sealed channel
(inv-sync-channel), one transaction per step; failures back off 5 to 30 minutes. Changes to the other copy's job wait as `sync_requests`;
a laptop job is offered only when queued `accepted` on the laptop with full automation on (`offers.mark_when_queued`); switching it off withdraws offers.

## 4. Core entities and their lifecycles

Reference tier: consulted per task, not read for orientation, in `docs/entities/`, keeping the root orientation-sized; each file carries
this contract. Code citing "§4" lands here; the table says which file to open.

| Entity | File | Scope |
|---|---|---|
| Job (`models/job.py`) | [`docs/entities/job.md`](docs/entities/job.md) | raw JD text + sha256 dedup; has no status of its own |
| Application (`models/application.py`) | [`docs/entities/application.md`](docs/entities/application.md) | one per job (its base resume moves with a tailor); status vocabulary, tailored draft, render artifacts |
| TailoringSession (`models/tailoring_session.py`) | [`docs/entities/tailoring-session.md`](docs/entities/tailoring-session.md) | the open → tailored | superseded | abandoned machine; frozen gaps |
| AtsScore (`models/ats_score.py`) | [`docs/entities/ats-score.md`](docs/entities/ats-score.md) | base upsert-singletons vs appended tailored history; deterministic engine |
| ResumeVersion (`models/resume_version.py`) | [`docs/entities/resume-version.md`](docs/entities/resume-version.md) | append-only snapshots on every write path — the undo story |
| FilledAnswer (`models/filled_answer.py`) | [`docs/entities/filled-answers.md`](docs/entities/filled-answers.md) | the answer receipt: what each form page run filled, each answer's source, the warn-only flags, the EEO lifecycle |
| AgentRun (`models/agent_run.py`) | [`docs/entities/agent-runs.md`](docs/entities/agent-runs.md) | finished automation reports; Recent runs, Last ran, retention and phase 4 limits |
| Health rubric | [docs/health-check-rubric.md](docs/health-check-rubric.md) | what the check judges and why: levels, questions, flags, word bank, disputes (the report's code contract: Others, ResumeLintReport) |
| Others | [`docs/entities/others.md`](docs/entities/others.md) | BaseResume, the settings endpoints (model settings, form-filling engines, persona draft, setup status), the uv install (`maestro`) and the secondary entities that need rules but not a file each |

## 5. The application workflow, end to end (web)

1. **Capture** — `/new` (**Add job**): paste a job description → **Save job** → `POST /api/jobs` (LLM extract, dedup) → summary
   card ("This job is already saved." on dedup). Or Companion/MCP `store_extracted_jd` → `POST /api/jobs/ingest` (pre-extracted;
   the client agent is the extractor by design). Both save paths score a new job against every selectable base after its commit
   (`_persist_job` → `score_all_bases`, inline); a failure rolls back only the scores, and a dedup hit is not re-scored.
2. **Track** — **Jobs** (`/applications`; the URL, `?status=`/`?source=` and `cs-tracker-*` keep their names): the tracker.
   Columns Role, Match score, Status, Where, Applied, Next step and Added, with search, sort, a grouped status `Select` and a
   Tracked/Yours/Agents `SourceToggle`; Next step and the quick filters read the server's stage (`services/stage.py`,
   docs/entities/job.md). "Saved" = job with no application; agent-captured jobs stay out unless the toggle is `Agents`, so the
   default reads Tracked, not All. Filter groups: All/Saved, **Your applications** and **Agent inbox**
   (`proposed`/`queued`/`needs_you`/`skipped`). Rows, options and the Agent inbox page (`/proposals`): frontend-conventions,
   "Jobs row" and "Tracker filter".
3. **Workspace** — `/jobs/[id]`: identity header (monogram, meta line, ONE status: the application's inline StatusChip, else the
   proposal's pill worded like History (`headerProposalPill`), naming its filer, + Queue/Skip; a score pill, **Resume match**
   (tailored) or **Best base resume**; a Needs-you question adds **Keep it**, PATCH `pending_review`, linking the job's application
   when the proposal has none; the job link; a ⋯ **More actions**: Queue in Agent inbox, Refresh details, Delete job). Under it
   four numbered steps replace tabs (`components/job-steps.tsx`, `lib/job-steps.ts`): **Job**, **Resume and gaps**, **Tailored
   resume**, **Apply**, each with one line (a done step's receipt, a later step's hint). The stage's step opens, set once on load
   (step 1 while a proposal waits on you). A step with something to show is a button (3: a draft or PDF; 4: an application),
   one with nothing plain text, never locked. `?tab=` keeps jd/fit/output/qa/submitted so deep links land. Step 1: the
   proposal's card, titled with its filer (`proposed_by`, worded by `lib/agent-name.ts`), only when it carries something
   (`proposalHasContent`), then a receipt row whose **View details** shows the **knock-out pre-scan** (`services/knockout.scan_for`:
   stated JD requirements vs the profile, flagged; the decision stays yours (or your agent's); verdicts and chips:
   docs/entities/job.md, "Knock-out pre-scan"), the job details and tracking link. Step 4's line, when it is current, is **Where
   this stands** (`lib/job-standing.ts`); it shows View PDF, the Details menu and, once the job has filled answers, **What was
   submitted**: the answer receipt, latest per question, source pills and warn-only flags (docs/entities/filled-answers.md).
   `?from=proposals` flips Back + prev/next onto `cs-proposals-seq`, else `cs-tracker-seq`. Every job read derives
   `proposal_status`/`proposal_id` from the newest proposal.
4. **Score** — Score and tailor shows the bases set for the job's country (all when unknown), scored at save; the auto-run on the
   first visit of step 2 is the fallback for a job saved before any base resume existed or whose save-time scoring failed; per-base
   cards → **Analyze gaps** creates a session (one filled button, on the best match; Restart gap analysis and Mark applied without
   tailoring sit in each card's ⋯). When every card draws the low-coverage warning, or the same gate warning, one banner says it
   instead; the lowest subscore of a card wears a Weakest word. With no base resume the tab offers Import resumes and documents
   instead, and scores once that dialog closes.
5. **Gap analysis** — `/jobs/[id]/tailor/[sessionId]`: per-gap resolutions (add_keyword / user_input / attach_project / skip +
   enable_entry / port_kb_point — see §4; plus cannot_confirm on claim-asking gaps: skip for the document + a durable
   `user_cannot_confirm` KB record written at SAVE time, so the claim is never re-asked — see §6 inv-provenance-no-decay)
   autosaved debounced with replace=true semantics (omitted gap_ids are deleted server-side); KB-auto-resolved gaps arrive
   pre-selected with provenance + Undo and a counting banner; optional per-session note (`user_prompt`, falls back into tailor()).
   **Use resume as is** (visible at 0 addressed) → from-base + closes the session; confirms first if it would replace an existing
   tailored draft.
6. **Tailor** — `POST /tailoring-sessions/{id}/tailor`: deterministic pre-ops → smart-model edit ops → keyword-survival and voice
   checks (§6 inv-resume-voice) → application + version row → draft-KBPoint write-back → session `tailored` → tailored score, one
   transaction (tailor() commits once at its end). The UI then lands in review mode (`?review=1`). Internals:
   docs/entities/tailoring-session.md, "The tailor pipeline".
7. **Output** — Resume tab: the ONE before/after compare panel + PDF card; **Create PDF** renders the tailored draft and shows the
   shared rasterized page preview inline (**Update PDF** refreshes it); download/open actions become available immediately, and a
   copy lands in the visible resumes folder (**Show in Finder**; §6 inv-resumes-folder-one-way). "Edit resume" → the studio
   (`/applications/[id]/resume`), where Save chains render → re-score automatically.
8. **Apply package** — Q&A tab: questions, cover letter (tone). Outreach/cold messages are asked as free-form questions (no
   dedicated cold-message generator); the QA prompt injects the application's linked referral contact.
9. **Track to terminal** — StatusChip anywhere (tracker row or job header): draft → applied → interviewing → offered → accepted /
   rejected / withdrawn. A base resume grown past your career history shows an "Add N things to career history" toolbar pill (N
   excludes already-recorded drift); its **Add now** drafts new and drifted items with no LLM, near-matching entities instead of
   forking duplicates.

## 6. Cross-cutting invariants (do not break these)

- **The browser is the attacker; six controls are the whole boundary.** `{#inv-browser-boundary}` The API has no authentication; the user's browser
  is inside the boundary and can be aimed at `127.0.0.1`. (1) **Host allowlist on BOTH servers:** `TrustedHostMiddleware` rejects any Host not in
  `settings.allowed_hosts` (without it DNS rebinding makes an attacker page same-origin), and `frontend/proxy.ts` plus the `/api` route repeat it from ONE
  definition, `lib/allowed-hosts.mjs`. (2) **Origin gate** (`app/origin_guard.py`): a present-but-unlisted `Origin` is refused before routing, an absent
  one allowed; raw ASGI, never `BaseHTTPMiddleware`. (3) **Extension origins are exact ids** (`settings.maestro_cs_extension_ids`), never a pattern.
  (4) **Template source is data, not code:** `pdf_render._environment()` is a `SandboxedEnvironment`. (5) **The compiler can neither execute, read siblings
  nor download:** `-no-shell-escape` unconditional, kpathsea paranoid mode, a fresh temp folder per run, Typst proxies pointed at a dead address.
  (6) **A template id is a slug, enforced in the REGISTRY** (`validate_template_id`; `_preview_path` also resolves then `relative_to`s). Why each exists, the
  middleware order and the bounds: `docs/entities/others.md`, "Browser boundary details". All six pinned in `tests/test_security_boundaries.py`,
  `test_frontend_host_guard.py`, `test_template_id_containment.py`. Related: `model_settings.set_base_url` rejects non-`http(s)` schemes (it decides where
  the stored API key is sent); both containers run non-root `APP_UID`; `llm._log_call` keeps metadata only unless `llm_log_content` is set (0600 either way).
- **An empty environment variable means UNSET.** `{#inv-empty-env-unset}` `config.scrub_empty_env()` deletes every empty/whitespace env var
  at import, before any SDK client is constructed (`config.SCRUBBED_ENV` records what went). `docker-compose.yml` writes `VAR: ${VAR:-}` for
  optional settings — an EMPTY STRING, not an omission — and third-party SDKs read `os.environ` directly (the OpenAI SDK adopts an empty
  `OPENAI_BASE_URL` and every request loses its scheme, surfacing as a misleading `APIConnectionError`). App-level `or None` guards cannot
  help, so the rule is enforced once at the environment boundary. Do not "simplify" it away, and do not add a `${VAR:-}` line believing the
  app will cope. Pinned by `tests/test_config.py` (the import-time case runs in a SUBPROCESS — reloading `app.config` in-process poisons
  later tests with `/app` paths). Related: `llm._get_client` raises a named error when there is no key AND no custom endpoint; Langfuse
  tracing requires an explicit `LANGFUSE_HOST` alongside both keys (opt-in by DESTINATION — keys without a host fall back to Langfuse Cloud
  and would ship resume text to a third party); compose does not forward the Langfuse vars.
- **Staged artifact removal** `{#inv-staged-artifact-removal}`: NEVER delete rendered files in a transaction that can
  roll back. Every `customized_json` write uses `services/application_writes.stage_resume_update` (sets draft, clears
  refs, records version, returns stale paths); callers commit, THEN call `artifacts.remove_files(stale)` to remove
  files/PDF previews and prune empty folders. Unlink failures warn with tracebacks; missing files and failed folder
  pruning stay quiet. Chat edits and version restores follow this pattern; never reintroduce an immediate unlink helper.
- **Stable per-application `artifact_dir`** `{#inv-stable-artifact-dir}`: one folder per application,
  `applications/Company_Role_YYYYMMDD_<idprefix>/`, allocated once via `services/application_artifacts.get_dir`,
  persisted on `Application.artifact_dir`; resume/source/PDF, previews, cover letters and proposal `evidence/` colocate
  there. Upload constraints: `docs/entities/others.md`, "PDF upload staging".
- **Resumes folder copies go one way.** `{#inv-resumes-folder-one-way}` After the commit, each finished PDF is copied into the
  resumes folder (Documents by default), never read back or deleted there; a copy failure never fails the caller;
  `resumes_folder.*` is machine-local, off without `RESUMES_FOLDER_DEFAULT` and on the always-on copy. Pinned by `tests/test_resumes_folder.py`.
- **Honesty invariant** `{#inv-honesty}`: an `add_keyword` on a skill the engine found NO evidence of (`fix_hint ==
  "absent"`) may only land in the skills section, never as a fabricated experience/project bullet. Enforced server-side
  in `save_resolutions` (guards MCP/API callers, not just the UI).
- **Placement validation twins** `{#inv-placement-validation-twins}`: `_validate_placement_target` (tailoring_session,
  raises) and `placement_targets.coerce` (scrubs LLM output) both call the pure `placement_targets.canonicalize` —
  `services/placement_targets.py` owns the placement-target contract, and the frontend's `buildPlacementTargets`
  hand-mirrors its targets shape. Extra targets require `section="extra"`, a stable `section_key`, and either an enabled
  entry's original index or, for a flat bullets section, the same stable key as `index_or_category`.
- **MCP control invariants** `{#inv-mcp-controls}`: no tool name contains "delete"; no set-default-template tool (`mcp_server/tests/test_server.py`).
- **MCP lives inside the app.** `{#inv-mcp-inside-the-app}` `/mcp` and `/mcp/{profile}` are routed inside FastAPI behind
  REST's SyncPublicHost → Host → Origin → CORS stack; SDK DNS-rebinding protection is OFF so that stack stays the one
  definition; never a second port or `/api/sync` route. Pins: `tests/test_mcp_http_boundary.py`, `mcp_server/tests/test_http.py`.
- **MCP tools run off the event loop.** `{#inv-tools-off-loop}` Every registered MCP tool runs on a worker thread
  through `mcp_server.http`'s own limiter; module functions stay sync (`tests/test_mcp_http_loopback.py`, `mcp_server/tests/test_http.py`).
- **`tailor_application` vs `edit_application`** `{#inv-tailor-vs-edit}` (MCP): the former REPLACES `customized_json`
  wholesale from the BASE resume; the latter applies ops to the CURRENT draft — docstrings lead with this; keep them
  unmistakable. Edit indices are **0-based into the full JSON array**, including `enabled: false` rows omitted from PDF; PATCH `/edits` echoes `applied[]`.
- **Autofill telemetry and run traces carry no VALUES.** `{#inv-autofill-telemetry-no-values}` `POST /api/autofill/telemetry` stores label, kind, rule
  id, option texts, outcome, host — never what was typed, was there before, or any AI answer: no value column, `extra="forbid"`, sw re-filters to six
  keys. `POST /runs` stores one strict `RunTrace` (newest 50 kept): a label or section holding a value the run wrote, was answered, left or found
  committed is blanked (`fill-loop.js` `rowKeys`/`siblingKeys`, which a scoped `only` fill still feeds from the fields it left alone; the exact rule, with its
  option-word exceptions: INTERNALS, "Run trace"); the page's option texts and the chosen option's index are kept on every field, EEO too, except a text holding another
  TYPED field's value; the rest is enums and numbers (a /map step names its sentinel from a fixed list, `TRACE_SENTINELS`, in `fill-loop.js` and `sw.js`), never a typed or profile string in a free-text slot.
  `sw.js` `scrubTrace` whitelists against the schema; nothing posts unless `telemetryEnabled` is `true` (default off; Options › Keep a fill log). Runs
  fold into host/label-free `autofill_mechanism_stats`. Rows carry `host` + `first_seen_at`, runs `host` + `started_at`, so `DELETE /telemetry` clears
  rows, runs and gaps, keeps counters, never the capture toggle (`extension/INTERNALS.md`; `scripts/fill_trace.py last|report` reads a DB copy). The
  **known-gaps table** (`autofill_widget_gap`, `POST /api/autofill/gaps`, `extra="forbid"`, closed enums) holds only a widget family hash, host, field
  shape, outcome and counts, posted only while `telemetryEnabled === true`; the **gesture report** behind the recipe book (`content/recipes.js`) holds
  event types and a few allowlisted key names, never `value`, and stays local with the fill log off too. With the log off the worker answers a run's
  trace with `why: "off"` and `lastAt`, the time of the last trace this device posted (an ISO time and nothing else), and the run card says so.
- **Filled-answer values stay in the receipt table.** `{#inv-filled-answers-local}` What the Companion or an agent filled into an
  application form (`POST /api/jobs/{id}/filled-answers`, MCP `record_filled_answers`) lives only in the local `filled_answers` table
  (`services/filled_answers.py`; `docs/entities/filled-answers.md`): one row per page run, linked to the job's application (by base on a legacy multi-application job). It
  never enters telemetry, run traces, Langfuse or exports. An EEO value is stored only under recorded EEO consent (the fill's own gate,
  `eeo_consent.withhold_unconsented`, asked at write; without it the row keeps the question with `answer: null`); withdrawing consent clears
  stored EEO answers (`eeo_answered` stays true) and reads are gated again as a second guard. No agent read returns an EEO value, marked or
  not (the server classifies by question words too): `get_final_review`'s `flags` carry `eeo_answered`, the MCP client strips again, and no
  MCP path reads `GET /api/jobs/{id}/filled-answers`, which serves EEO values to the web UI. The Companion panel (`shared/receipt.js`,
  `panel/actions/fill.js` `recordReceipt`) posts the receipt through the generic `api` door, never `telemetry`/`fill_trace`, so it works with
  telemetry off; it reads only frames that earn the data (inv-frame-earns-data), records no never-fill field even under standing consent
  (`ns.isNeverFilled`), and its values never reach the run-trace builders. Pinned by `tests/test_filled_answers_invariant.py`, `test_extension_panel_receipt.py`,
  `test_filled_answers_api.py`, `test_filled_answers_agent.py` and `mcp_server/tests/test_client_filled_answers.py`.
- **A frame must EARN the user's data.** `{#inv-frame-earns-data}` `sw.js` authorizes a broadcast at the sender, but `broadcastToFrames`
  targets every frame — a job page carries ad/analytics/chat iframes, and the ISOLATED world protects the message in transit, NOT the DOM
  written into: a frame owns its DOM, so a profile value in a third-party frame's input is readable by that frame's script. `agent.js` gates
  every fan-out write (`profile_fill`, the `fill_*` ops, attach…) on `frameMayReceiveUserData(msg)`: the TOP frame passes; a SUBFRAME must
  show `detectPage().form`, OR sit on exactly the http(s) `flowOrigin` the panel vouches for — whose frame held a confirmed form in this
  tab, same employer, within the hour (panel.js `withFlowOrigin`; iCIMS EEO steps score 0). Detection throwing refuses. A refused frame
  returns the handler's EMPTY shape, never a throw. Attach also requires a VISIBLE input (`input.files` is readable with no gesture). Pinned by `tests/test_extension_frame_gate.py`.
- **The policy deny-list is single-source, and it is TWO lists.** `{#inv-policy-deny-list-single-source}` `extension/shared/policy.js` (in
  `shared/`, since the panel consults it too) declares each exactly once: `NEVER_FILLED` (signatures/initials, passwords, government IDs) and
  `CONSENT_FORMS` (the application's OWN certify/acknowledge/attest/terms/arbitration/waiver boxes). WITHOUT the standing `consent_forms`
  permission (inv-eeo-standing-consent) both lists and the salary rule refuse; WITH it `isPolicyBlocked(label, {consentForms: true})` refuses NO
  label (the user's application, recorded revocable consent); Submit stays the user's at every setting, and Next is clicked only by
  `page_advance` in a run the user started with Apply, full automation On (§7). It DEFAULTS to false and only a literal `true` counts; only
  `fillFormFromProfile` and the fill loop's inventory pass it. FOUR consumers across THREE surfaces: `fillFormFromProfile` ahead of rule
  matching and `collectOpenQuestions` ahead of EXCLUDE and the per-type ladder — so a consent question rendered as a select/radio is never
  offered to the model or tagged `data-rt-qid` — plus the panel's PAIR: the pause row renders no input for a blocked label AND `submitAnswer`
  refuses one again (the first decides what to draw, the second touches the page). Salary history/current/CTC and unqualified
  salary/wage/compensation mentions are also blocked without consent; explicit salary expectations are allowed only AFTER both lists.
  `test_both_copies_of_the_policy_deny_list_stay_identical` asserts exactly one declaration of EACH list; only the commit ladder stays a
  deliberate, pinned-identical twin (`…commit_ladder_stay_identical`).
- **One label-pattern table, two readers** `{#inv-one-label-pattern-table}` (`extension/shared/profile-fields.js`). The eleven patterns
  naming a TYPED home in the autofill profile (`eligibility.*`, `work_auth.*`, `preferences.*`) are read by `content/autofill.js`'s rule
  table, which FILLS those fields, and by the panel's `saveTargetFor`, which decides where a pause-row answer is LEARNED. They must be one
  table: an answer learned into `profile.custom` for a field the rules fill from `preferences.notice_period` lands where the rules do not
  look, so the same question pauses on every later application with nothing failing. **The learn store is the autofill profile, never
  `qa_entries`** — that table is application-scoped and no reader feeds it back into a fill, so "pause once, learn forever" is only true of
  `profile.custom` (matched by the deterministic rule pass on every later form) and the typed keys. Wiring faults are made loud rather than
  left silent: `profile-fields.js` throws at load if `shared/policy.js` has not run (it borrows `salaryExpectationRe`), and `autofill.js`'s
  `pf()` throws on an unknown id — an undefined pattern does not error, it just never matches.
- **Em-dash rule** `{#inv-em-dash}`: generated Q&A answers and cover letters are scrubbed of U+2014/U+2013 at store time
  (`qa.scrub_typographic_dashes`); rendered PDFs must not contain em-dashes (ATS parsers). The MCP client's slim `get_rendered_pdf` scan
  remains a resume-PDF backstop (metadata + page paths; no `page_images_b64` — use `get_rendered_pdf_page_image` for one page).
- **EEO standing consent is enforced at the ENDPOINT.** `{#inv-eeo-standing-consent}` One record (`settings/eeo_consent.json`,
  `schemas/eeo_consent.py`; `eeo_consent` on `/api/autofill/context`), TWO permissions kept apart on purpose: `enabled` authorizes
  disclosing protected characteristics, `consent_forms` lifts the label policy (inv-policy-deny-list-single-source), only if agreed under
  policy ≥ 2 (an older yes is served off, `consent_forms_lapsed`). The server owns the stamp (`acknowledged_at`, `policy_version`);
  `consent_forms` turns on only on its own yes carrying the current policy (`agreed_policy`; `test_eeo_consent.py`). One flag for both would
  make an EEO yes agree to terms. ONE gate, `eeo_consent.withhold_unconsented`, strips `profile.eeo` unless `enabled` for every outward
  reader: `GET /api/autofill/context`, the `/choose` prompt AND the Jev engine's slot catalog (model providers — OpenAI, Gemini, Claude,
  OpenRouter, Jev — are recipients too); it fails CLOSED when consent cannot be computed. The MCP client keeps its OWN strip — two gates,
  not a relocated one. Which path asks never decides whether protected-class data is served. Pins (router, `/choose`, Jev):
  `.system_md_enforcement.json`. No inference or invented EEO answers; never solicit pasted demographic answers in chat when consented
  values are in Profile. Human-only at ANY setting is Submit and nothing wider (Next belongs to the run, per inv-policy-deny-list-single-source); `consent_forms` lifts
  every label refusal for the callers that pass it (the fill loop, a model included; never the old collector/pause rows), and only it, as
  served (lapsed or unreadable: absent), adds `derived.agrees_to_terms`.
- **Provider data** `{#inv-provider-tagged-meta}`: opaque blocks (`ProviderMeta`: Claude thinking signatures, Gemini thought
  signatures) carry their provider and reach only that provider; `replay.for_provider` strips them for any other, so a model
  switch mid-chat never leaks one vendor's blocks to another. Pinned by `tests/test_replay.py`.
- **PDF word-spacing** `{#inv-pdf-word-spacing}`: pdflatex+XCharter joins words for strict extractors; `pdfinterwordspaceon` + the
  parse_certified gate protect this — see the shared header partial `_header.tex.j2`, which BOTH resume and cover-letter templates include
  (format/scanner changes must handle both). pdfTeX 1.40.27 misplaces that space for many Type 1 fonts (e.g. Helvetica, Charter, Garamond,
  Fira) → overprinted words that still extract cleanly; `template_validation.text_overprints` refuses such a LaTeX sample and `engines`
  warns on that build, where boot re-validates ready LaTeX templates once (`template_registry.recheck_ready_latex_for_engine_warning`). A uv
  install uses the HOST's TeX, not Docker's TL 2026 — a PDF's `PTEX.Fullbanner` names the pdfTeX that made it.
- **A render never changes engine silently** `{#inv-render-fallback-explained}`: `services/engines` is the ONE probe; `MAESTRO_CS_PDFLATEX`
  overrides and fails CLOSED. Without `pdflatex`, `pdf_render.resolve_render_template` uses the first ready Typst template for LaTeX
  resumes, bases and cover letters; `render_note` names both. VALIDATION never substitutes. `base_resume_render.record_render_error`:
  committed writes persist `render_error`; render-only requests return 400, never 500. Startup validates seed templates before rendering
  bases; seed-render failures persist `render_error`, warn with tracebacks and leave the base usable; its first save retries. Call sites:
  `tests/test_render_note_coverage.py`. Pins: `tests/test_render_fallback.py`, `tests/test_seeding.py`.
- **`user_cannot_confirm` is durable.** `{#inv-provenance-no-decay}` No code path upgrades that provenance to anything else — including the
  gap flow that writes it: a "cannot confirm" gap outcome stores a retired `user_cannot_confirm` point (on the entity its placement names,
  else the archived "Unconfirmed claims" holder) and future sessions pre-resolve the claim instead of re-asking (normalized-text match,
  evidence autos win). Base-sync of the same claim drafts a NEW `user_authored` point and leaves the record untouched — new first-party
  evidence beats an old "don't know"; the draft queue is where the user reconciles. Pinned by `tests/test_kb_provenance_stamping.py`
  (`test_no_writer_flips_user_cannot_confirm`) and `tests/test_gap_cannot_confirm.py` (`test_nothing_upgrades_user_cannot_confirm`).
- **Column types come from ONE module.** `{#inv-single-dialect}` SQLite is the only runtime database. `app/models/types.py` (`JSONDoc`,
  `UUIDType`, `UTCDateTime`) is the only place a column type is chosen, and nothing under `app/` imports `sqlalchemy.dialects`.
  `UTCDateTime` is the whole timezone story: aware in Python, naive UTC on disk, and a NAIVE bind raises; the APP writes every timestamp
  (`default=utcnow`, `onupdate=utcnow`) so one format lands on disk. Pinned by `tests/test_db_portability.py`.
- **Job-site passwords stay in their local file.** `{#inv-job-site-password-local}` `settings/secrets/job-site-login.json` is 0600
  (directory 0700); writes serialize and replace from unique temp files; damaged JSON/non-object files read empty. Never DB, exports,
  telemetry or logs. Settings GET/PUT return only `{email, password_set}`; validation errors are sanitized. TWO routes hand it out, both
  needing full automation On, a Queued/approved proposal and a company off the skip list, each recording
  `ConsentEvent(action="login_shared")`, never the value. POST `/api/proposals/{id}/job-site-login` requires NO `Origin` (MCP origin;
  channel `mcp`, note = client name) and the login passes through the agent's AI provider. POST `/api/companion/job-site-login`
  (`{proposal_id}`; channel `companion`) is admitted only for the Companion extension's origin: `page_sign_in` types it in the TOP frame
  alone, only on a known ATS host (`shared/ats-hosts.js`; elsewhere the run parks `sign_in_yourself`), once (a failure parks, never
  retried), and the password never reaches a model, run record, card, receipt, trace, telemetry or error. **Account creation** (owner decision, reversing
  "it always parks"): `page_create_account`, the same route, top frame and host rule, on a page with one email box and two new-password boxes and no code box
  or CAPTCHA, once; it ticks only a REQUIRED box that agrees to create the account or to the privacy notice, never a marketing box, and presses only
  "Create Account"; an email check, CAPTCHA or refusal parks (`verify`, `create_account_failed`), never retried. Pins: `tests/test_job_site_login*.py`,
  `test_companion_job_site_login.py`, `mcp_server/tests/test_client_job_site_login.py` (symbols in `.system_md_enforcement.json`).
- **Automatic consent is gated by the user's switch.** `{#inv-auto-consent-gated}` Off by default; only PUT `/api/settings/full-automation` (`{value: bool}`, StrictBool)
  writes it; PUT `/api/settings/auto-apply` preserves it. Channel `auto` approves only `accepted` (Queued), requires `final_review` evidence, re-checks the company
  blocklist, and keeps the daily-cap/already-applied gates. An auto-attested submit, including from `submission_uncertain`, needs a note with at least one letter or digit;
  both auto paths require full automation On. A company blocked after approval still has its submit recorded. Eligibility is the agent's `apply-auto` prompt, not a
  server-side review judgment. Channel `companion` is the Companion's own and only its exact extension origin may name it: PATCH uses it for the user's Apply (Queued only);
  `POST /api/proposals` moves an `accepted` proposal to a newer draft of its job only for that origin, when the yes came on channel `companion`, no final review exists and
  the old draft is gone or still a draft (every other mismatch stays a 409, and an application of another job is refused on every linking route); the user's real Submit,
  seen as a confirmation page, is recorded only by `POST /api/proposals/{id}/companion-submitted` (approved then attested submitted, host/path/text as the receipt), which
  clicks nothing and, past the daily cap or skip list, files an applied-yourself record. A skipped (rejected) proposal blocks queuing its job again, except an "applied manually" one, which blocks only while an application of the job is still applied. Pins: `tests/test_full_automation_setting.py`, `test_proposal_state_machine.py`,
  `test_companion_submitted.py`, `test_proposals_router.py` (symbols in `.system_md_enforcement.json`).
- **One writer per job; the laptop owns the profile.** `{#inv-one-writer-ownership}` With sync on (a key file exists) every job has one owner
  machine (`jobs.owner_machine`, NULL = this one) and the other copy holds a read-only replica; the laptop owns the whole profile, which
  the always-on copy replaces on every round and never merges. A queue, skip, status or note change on the other copy's job is a
  `sync_requests` row ("Sent at the next sync") the OWNER applies under the normal rules (state machine, forward-only statuses, daily cap);
  anything else on it is refused. Only a handover moves ownership: `offered` (laptop to bot; set by `offers.mark_when_queued` when a job is
  queued with full automation on, cancelled by **Keep it here** or by switching full automation off; `GET /api/sync/handover/offers` is empty while it is off) or `returning` (bot to laptop on **Work on it here**, refused while the job
  is `approved` or `submission_uncertain`). The same JD text on both copies keeps the laptop's job (`duplicates.py`). Without a key every
  job is owned here and every `/api/sync/*` route is a 404. Pinned by `tests/sync/test_guard.py` and `tests/sync/test_home_endpoints.py`.
- **The flush guard is the ownership check, and it runs before disk.** `{#inv-flush-guard}` One SQLAlchemy `before_flush` hook
  (`services/sync/hooks.py`) guards EVERY write path (web, MCP, Companion, the Assistant's in-process writes): it raises `NotOwnedHere` (a
  409) for a replica, an offered job (laptop), a returning job (bot), a row it cannot tie to a job, and any profile row on the always-on
  copy, except scoped seeds and "cannot confirm" additions (sent home as `profile_addition` requests). A route that writes files or calls a
  model calls `require_owned`/`require_profile_writable` BEFORE the disk or the model, so a refusal deletes nothing; reads that write skip
  replicas (`owned_here`); a Core writer touches its job or the profile itself (`touch_job`/`touch_profile`); the sync's own writes pass
  inside `hooks.standing_aside(db)` (it sets `session.info["sync_apply"]` and restores the earlier value); a missing previous parent allows repair; no key allows every write; transaction end and rollback
  clear the hook's state. Pinned by `tests/sync/test_guard.py`.
- **Every sync message is sealed; the key never travels.** `{#inv-sync-channel}` Peer routes and `/api/sync/enroll` are AES-256-GCM,
  with HKDF-SHA256 keys derived from the sync key or the one-time pairing code; a header MAC is checked before any body. An unsealed
  request, a failed seal, or an `Origin` on a sealed route is a bare 404, byte-identical to sync being off (a 403 would show that sync
  is on); with no key file every `/api/sync/*` route is that 404 and the always-on copy serves no home routes. Only `/api/sync` may be
  published (Tailscale Funnel); while `SYNC_PUBLIC_HOST` is set every response on it is sealed or the bare 404, whatever Host says, and
  the public name stays refused off that tree. The profile, the AI key and the job-site login ride only this channel, and no key,
  pairing code, seal plaintext, bundle value or local path reaches a log or an error (fixed sentences). `POST /api/sync/round` is the
  always-on copy's own loopback call (404 on the laptop, 403 for an `Origin`, as is `/api/sync-setup/*`). The post-seal checks (protocol,
  one request at a time, body cap, chunk timeout), replay refusal, path rules, the proxy rule for `SYNC_REMOTE_URL`, artifact-folder
  containment and the pairing code's life: `docs/entities/others.md`, "Sync channel details". Pinned by `tests/sync/test_seal.py`,
  `test_sealed_home.py`, `test_public_host.py`, `test_pairing.py` and `test_two_machines.py`.
- **One data folder per user; nothing writes into the install.** `{#inv-one-home}` A uv install's `MAESTRO_HOME` defaults to
  `~/Library/Application Support/Maestro Career Studio` (macOS), `%APPDATA%\Maestro Career Studio` (Windows) or
  `$XDG_DATA_HOME/maestro-career-studio` (Linux), the folder the future desktop app uses, so its data needs no import.
  `home.backend_env` points every writable path (data, applications, settings, logs, uploads, model cache) into it, so nothing
  lands under site-packages; its `maestro.env` is the only settings file. Pinned by `tests/maestro_cs/test_home.py`.
- **The install's environment is applied before `app` is imported.** `{#inv-env-before-app}` `app.config.settings` reads the
  environment at import, and its `env_file=".env"` would read a Docker checkout's file from the caller's folder. One-shot verbs
  (`check`, `migrate`, `connect`) call `home.apply_env()` first, which also `chdir`s into the home; servers get it as child env
  with cwd = home; `maestro mcp` imports no `app` module. Pinned by `tests/maestro_cs/test_maintenance.py` and `test_bridge.py`.
- **Base resume colour is identity, never state.** `{#inv-resume-color-identity}` One hue per base resume, drawn as a square beside its
  name, never as status; the recipe lives once in `globals.css` and the presets are mirrored across backend, frontend and extension.
  Pinned by `tests/test_frontend_resume_colors.py` and `test_resume_color_parity.py`.
- **Resume text is the owner's own, in implied first person.** `{#inv-resume-voice}` Every rewrite prompt carries the VOICE rule (built in code, so a
  customised row keeps it); `services/resume_voice.py` finds the shapes about the owner. Model and caller text NEVER stores a blocking third-person
  hit (one retry, then repair, then drop); the owner's base lines get only mechanical repairs and are never dropped. Ambiguous shapes are flagged
  (health advisory `voice.third_person`), never rewritten. MCP ops with a hit get a 400; the tailor response lists repaired paths as `voice_repairs`. Pinned by `tests/test_resume_voice.py`, `test_tailoring_voice.py`.
- **A Next the page rejects is not a move, and only a page the run filled is pressed.** `{#inv-rejected-next}` A press that leaves address and step heading while the
  page shows errors keeps `step` and `seen`; the driver reads `page_errors` (the page's own words, never a value), repairs ONLY the fields they name (`fix`,
  `runFill({only})`) in at most `MAX_FIX_ROUNDS`, each error once, then presses again; a repeat or an error it cannot work parks `page_errors` naming only what is left.
  Next is pressed only on the page last filled (`filledPage`: path and step key, query ignored): a refused press or repair that ends on another page counts as a step
  (`step_limit`, `loop`) and that page is filled first. A posting's Apply is pressed as a same-tab link even if it asks for a new tab, only to the queued link or a known
  ATS host (address re-checked), and the first read after it must be on the link's host, the queued host or a known ATS, else `moved_away` before any fill. Pinned by
  `tests/test_extension_queue_run.py`, `tests/browser/test_page_reader.py`.
- **The resume is written once per page, to a lone resume box, before Next.** `{#inv-one-resume-write}` Only a page's one required upload box whose own words
  name no other document counts as the resume's (or a lone box under a resume heading, or the box a page error named, an opaque tag); never over a file
  already there, and never a second write after an `unconfirmed` one. **A parser box is never written** (the site's own import or fill-from-resume; the
  nearest name decides, `uploadBoxOf`), nor one for another document, by any press, the Attach button included. A required box still empty after the fill, a
  required parser or other-document box, or a choice among several, parks `upload` before `page_advance`; a Resume never attaches.
  Pinned by `tests/test_extension_queue_run.py` and `tests/browser/test_upload_box.py`.
- **A worked-here No is never wrong.** `{#inv-worked-here-no}` The history answers No to "Have you worked at X?" only when it lists jobs and no employer is among the companies
  the question names (the whole history, any wording); a match is Yes. ASKED instead (`autofill_catalog.named_employer_fact`, read by /pick, /step and /map): a parent,
  subsidiary or alias of an employer (`_ALIASES`), a name whose initials spell an acronym employer, a list beside one, an employer's name standing in the question as
  capitalised words. Only an ALLOWLIST of question shapes about the applicant's own employment, the company directly after the phrase, is rerouted to it (`asks_worked_here`,
  backed by an exclusion list): never eligibility, willingness, relatives, referrals, applications, a competitor, a public body beside the company or a time window. OTHER
  companies are rerouted too (`asks_worked_here_of_other`): employment verbs only, up to 4 proper names (no group, generic noun, public body, pronoun phrase or "its
  affiliates"), none in the history, no history entry that is no company; so is a dealer or contractor of a company (the job's own included). Those are reported `assumed`
  (`derived.previously_employed_here#other`, `ASSUMED_SLOTS`). An unsure map on "worked with X" (no employment verb) is the user's. Pinned by `tests/test_autofill_{catalog,map}.py`.
- **Veteran status is one Yes/No.** `{#inv-veteran-yes-no}` A No settles every "not a (protected) veteran" option and "currently or ever served" (the never-served
  option, reported `assumed`: `veteran_inferred`); a Yes, and any other saved Yes/No fact, never picks or answers a protected class, and a Yes never claims CURRENT
  service (a question about it alone, or an option that says so, is asked: `veteran_overreach`) (/pick, /step, /map and `content/eeo.js`). Legacy `veteran` reads as
  yes; legacy `not_veteran` reads as UNANSWERED and the profile lists it under `stale_answers`. Pinned by `tests/test_autofill_pick.py`.
- **Ready means a real review page with nothing missing.** `{#inv-ready-real-review}` The run reports Ready to submit only when the page is a review whose
  `by` is `submit_button` (a real Submit control inside the application and no real Next), shows no errors and has no required box empty (`requiredEmpty`:
  one scoped fix, then `open_questions`). Any other reason a page reads as a review (a Submit the reader could not see, a dialog about submitting, several
  Nexts, fields and no Next) parks `unsure_page` only after the same read held for 4 reads (a page with errors or empties gets its fix first); a field-less page with only a bare Continue or Proceed parks `confirm_page`; a plain Next is pressed. A
  Resume on an `unsure_page` FILLS the page; the user's word feeds Ready (`readyBy` "user", errors and empties still checked) only for `submit_seen`, `submit_context` and `fields_no_next`, and is void once the read shows a Next. The one resume the run already wrote on the page excuses ONE required resume box, never a second. Closed means closed: a strict
  notice, nothing fillable and no Apply, and resumable. Pinned by `tests/test_extension_queue_run.py`, `test_extension_page_kind.py` and `tests/browser/test_page_reader.py`.
- **Low stakes are decisive; a draft is read, not trusted.** `{#inv-drafted-answers}` A low-stakes gap is filled and reported `assumed` with a fixed note, never
  left blank and never invented as a fact: a date box asking for more than the fact has takes the 1st (January for a year), https goes on a host, a phone type
  is Mobile, a dialing-code picker takes the profile country's code. The owner's No/Yes safe defaults are in the §7 dial. A middle name is never made from the first name; the name is used as stored. `/choose`
  DRAFTS only a REQUIRED text or textarea that `/map` filed as `free_text` or `years_unanswered`, with an application, never at **Careful**, never when the
  never-list matches (protected, EEO, work authorization, money, background, signatures, logistics, public service, employment here), in the owner's voice,
  about 120 words or the label's stated limit, `""` when the history cannot answer; it returns `assumed` with "Drafted from your history: read it" and saves nothing. Pinned by `tests/test_autofill_choose.py`, `test_autofill_map.py` and `tests/browser/test_fill_core_fields.py`.

## 7. Agent surfaces

- **MCP server** (`backend/mcp_server/`; on screen **connected agents**, Settings › Connected agents): thin REST wrappers
  (`@_guard` → `ToolError`) via httpx (`BACKEND_URL`, default localhost:8000; compose host 8001). Loopback bypasses proxies; other hosts honor them (`mcp_server/tests/test_client_loopback.py`).
  **The docstring is the API**: behavior, records and requirements, never instructions (directory policy).
  `test_server.py` ratchets `title`, four `ToolAnnotations` (`_read`/`_write`) and ~2048-dedented-char docstrings;
  overflow facts live in param `Field(description=…)` (`_EDIT_OPS_FIELD`). Lists page with bounded defaults;
  `_best_effort_hint` returns `next: null` on a failed lookup after a landed write.
  Coverage: [docs/entities/others.md](docs/entities/others.md), "MCP tool coverage".
  **Scoped profiles**:
  `profiles.py` owns `full` / `hunt` / `apply` / `explore` / `templates` / `career` (88 tools); `/mcp` = `full`, `/mcp/{profile}` = its allowlist.
  Lifespans run fresh stateful JSON sessions; tools use `http.py`'s eight-worker limiter (§6 inv-tools-off-loop).
  Stdio filters `MAESTRO_CS_MCP_PROFILE` (default `full`; migration state: §13 `mcp-stdio-venv`).
  Hints use request `CURRENT_PROFILE`, else env (pins: `mcp_server/tests/test_profiles.py`, `test_server.py`, `test_http.py`).
  Enable ONE profile per chat (`full` carries KB writes); `MAESTRO_CS_*` has no legacy fallback. **Apply executor:** headed Chrome (`docs/entities/others.md`, "Attended executor"; apply playbook, "Unattended (full automation)").
  **Plugin:** `plugins/maestro-career-studio/`: Claude Code's `.mcp.json` and Codex's `.codex-mcp.json` connect by URL; Codex prompts for durable decisions, login/upload, health-gate waivers, restores, KB approval and sync. Claude installs use a tagged local checkout; Codex uses a release-tag Git ref and sparse paths `.agents/plugins` + `plugins`; policy `PRIVACY.md`.
  Settings › Connected agents' **Connect an agent app** (`connect-assistant`) selects a tool set and copies commands/URLs, opens install links or downloads the Claude Desktop bundle.
  `GET /api/setup/connect?profile=full` composes values from `MAESTRO_CS_PUBLIC_BACKEND_URL` (default localhost:8000; compose host port unless overridden); `/api/setup/connect/bundle` serves `MCPB_BUNDLE_PATH` (compose read-only mount; `tests/test_setup_connect.py`).
  The dependency-free Node ≥18 `.mcpb` bridges stdio↔HTTP with no assistant-side Docker/Python: `MAESTRO_CS_BACKEND_URL`
  defaults to localhost:8001; `MAESTRO_CS_MCP_PROFILE` selects `/mcp` or `/mcp/{profile}` (no trailing slash).
  Requests are ordered; stale sessions replay initialize + initialized before one retry, preserving `clientInfo`
  (`mcpb/tests/bridge.test.js`). HTTP `serverInfo.version` reads `APP_VERSION`, else `dev` (`mcp_server/tests/test_http.py`).
- **Guided tailoring workflow** (`mcp_server/workflow.py`): wrapped tools carry a `next` envelope
  (`state`/`blocking`/`offer`/`ask_user`/`options`/`call`) that walks §5's arc — score all bases → recommend →
  quick|custom → tailor → render → apply readiness — unnarrated. `workflow.py` is PURE (no httpx/DB/LLM), a
  **deliberate exception to the thin-wrapper rule**: the sequence must live somewhere and FastMCP
  `instructions=` is surfaced inconsistently across clients; purity is what keeps it testable under DB-free
  `mcp_server/tests`.
  - **Server ranks, agent narrates.** `rank_bases` is deterministic (composite desc, slug tie-break), so
    identical scores always yield the same pick and only prose differs. `close_call` (< `CLOSE_CALL_MARGIN`
    3.0) means present a CHOICE, not a verdict — NOT `auto_apply.auto_pick_margin`, which means "pick without
    asking" in the hunt lane. `coverage_warning` comes off the RECOMMENDED row, not the table:
    `_calc_coverage_signal` compares each resume's OWN matched ratio, so bases can disagree; only
    `extracted_count == 0` is uniform.
  - **`offer` ≠ `ask_user`.** `score_ats` emits only a non-blocking `offer` — mass JD capture scores twenty
    postings in a loop and a question on each would derail it; `ask_user` appears only mid-arc, after the user
    commits. **A hint never names a tool the active profile did not register** (`hunt` has no tailoring tools):
    options AND prose filter via `_active_allowed_tools()`; prose states facts, never commands (`test_workflow.py`).
  - **Two controls.** `mcp_workflow` `{hints: bool}` (`GET/PUT /api/settings/mcp-workflow` + its card in
    Settings › Connected agents) is the USER's master switch; `brief=true` on `score_ats` is the AGENT's, for
    triage loops, checked FIRST so a loop pays no settings read. Tools **always wrap** (`next: null` when
    suppressed) — one tool must not return two shapes per runtime flag.
  - **LLM-free arc.** MCP `create_tailoring_session` defaults `enrich=False`; `quick_tailor` = create + `POST
    .../apply-profile` (deterministic fill) → agent authors ops → `tailor_session(ops=…)` skips the backend
    LLM pass. Filling precedes authoring so saved resolutions and applied ops cannot disagree (§11 item 13).
    `apply-profile` discards `fill_checkpoint_session`'s standing-instruction return (persisting it would
    break the web path's transience), so the hint carries it as the `tailor_session` option's `user_prompt`,
    ONLY when the session has no note of its own — else quick tailor over MCP ignores a setting the web obeys.
    **The caller-ops honesty rule is enforced by DOCSTRING, not the server**: `apply_edits` has no honesty
    gate, keyword-survival is LLM-path only. The server-side evidence gates (`save_resolutions` re-running
    `enable_entry`/`port_kb_point`) still hold.
  - **Apply readiness** reads `setup/status`'s `autofill` block; the server cannot see whether the client holds
    browser tools, so the render offer says the handoff needs them rather than asserting the capability.
- **Onboarding workflow** (`workflow.py`): `kb_ingest_resume` (drafts) → `kb_approve_points` (the user's gate) →
  `create_base_resume_from_kb` → `render_pdf` (an application render returns a nullable `copy_path`, the visible copy) walks ingest-several
  → KB → role-targeted bases with zero in-house LLM (the client agent parses/authors; ingest the CURRENT resume first — over single-source
  MCP calls `_seed_profile` is first-write-wins). Ingest hints are offer-only (multi-resume loop, same mass-capture lesson as `score_ats`);
  `brief=true` suppresses before any settings read. Hint options carry only verbatim-callable args or none at all, offer prose is derived
  from the filtered options, and composers take the requested state explicitly rather than inferring intent from results. Scoring is
  mentioned in prose, never as an option — it needs a `job_id` no composer can know.
- **Automations page** (`/automations`, sidebar after Agent inbox): **Copy prompt** hands work to the user's agent;
  Maestro runs NO scheduler. Each run prompt ends with MCP `record_run`; cards show Last ran.
  Catalog, wrappers and startup rules: [docs/entities/others.md](docs/entities/others.md), "Automations page".
- **In-app chat**, on screen the **Assistant** (`services/chat_agent.py` + `chat_tools.py`): a distinct toolset (resume edit, KB capture,
  template admin including the mutations MCP deliberately lacks). Its resume-edit tool runs the SAME pipeline as the REST endpoints
  (`services/resume_ops.py`); scope checks and ToolError mapping remain chat-side. Cards, selections and the analytics tools:
  `docs/entities/others.md`, "In-app chat: interaction model". **Pinned-resume resolution**: the pin is a HINT, not a guard (the enforced
  guard is `check_ops_in_scope` over selection PATHS); how it resolves, reloads and follows a changed base is reference tier:
  `docs/entities/others.md`, "In-app chat: pinned-resume resolution". **Social posts**: chat drafts LinkedIn/social posts as copy-out
  markdown — no card, no persistence, the transcript is the history — grounded via read-only `get_career_context`; conventions live in
  chat_system.txt. The router checks the Assistant's key before the capability check (no key → a 422 "The Assistant needs an API key…");
  `run_turn` streams through the adapter; working chips are words (`TOOL_PHRASES`), and deleting a chat asks first. Prompt rows seed at
  startup. `prompts.get_prompt` lazy-seeds only with a caller's session; its own session reads the file default without writing when a row
  is absent. Prompt-file changes need the DB `prompt.chat_system` row reset (Settings › AI & models › AI instructions → Reset to default, or
  delete the row); a deploy uses a SQLite-chain migration that deletes the row only while it still equals the previous default
  (`4022b54933e6` did it for `chat_system`; `tests/test_prompt_sync_guard.py` explains the mechanic).
- **Chrome extension** (`extension/`; on screen **the Companion**): MV3; the **side panel** (`panel/`) runs capture and fill; toolbar icon
  (`openPanelOnActionClick`) and hotkey (Alt+Shift+J → `sidePanel.open`, guarded: that method is Chrome 116 and the minimum is 114) both
  open it. Four-stage rail — Job → Resume → Fill → Track — INFERRED from the store by `ns.decisions.stageFor` every render, never set by a
  click. Job = saved AND a base chosen (a pick, the scored best preselected, or a bound application's own `base_resume`); Save job scores
  the bases in the same press, and an unscored saved job is scored once when Job opens. `hasForm` is NOT a stage input. ONE row shows a body
  (the active one, or a DONE row reopened as view state; the active row is the way back). Painted as direction C: a `#progress` bar ("Step N
  of 4", from the active row), the active row as a "Next" card, done rows as compact lines, locked rows hidden by CSS (still in the DOM);
  `scripts/panel_preview.py` renders each state. The footer's one primary follows the OPEN row: Save job (then Update scores), Quick tailor
  (Create PDF when an application lacks its PDF), Autofill; with full automation On the Job step's primary is Apply (below; **Add job**, the Save job press, sits beside it on an unsaved page). The panel document is a family of scripts (panel.html owns roster and order):
  `panel.js` owns the store, the loaders and the generation guard; per-STAGE bodies (`panel/stages/*.js`) get a per-render snapshot,
  per-CONCERN actions (`panel/actions/*.js`) a handle with one `write(patch)` door, and each roster THROWS at boot naming a missing script.
  `panel/icons.js` (`ns.icon`, inline Lucide svg) draws every icon; no emoji or text glyph (`test_extension_panel_icons.py`).
  `shared/status-roles.js` is the application status table the web `StatusChip` shares (`test_extension_status_roles.py`);
  `shared/resume-color.js` the base resume presets (`swatch`; §6 inv-resume-color-identity). `shared/` is what both worlds load: `decisions.js`
  (the ONE home of panel rules), `choose.js` (routing, /choose batch, `rest_fill` shaping, `QUESTIONY`). `guided-run.js` is panel-only.
  Failure copy (never server text; `failureNote`), revisit rules, sender model, COMMIT GESTURE and the ONE `attachableFileInputs`
  definition: `extension/INTERNALS.md`. Never rename bridge storage key `widget.sessions` (tab id → job entry) — that drops every live entry. **Posting identity
  is ONE table in two languages** — `job_url_match.posting_id` ↔ `decisions.postingId` (LinkedIn `currentJobId` / `/jobs/view/<id>`, Indeed
  `jk`/`vjk`, embedded Greenhouse `gh_jid`), pinned by `test_extension_posting_identity.py`; add a key to BOTH. Options (`options.html`,
  `options.js`) read `read_settings`, save `backendUrl`/`appUrl` in `storage.sync` and test `/health`. `scripts/pack_extension.py` gates
  matching versions; store upload and key handoff: `docs/RELEASING.md`. Rest: `extension/INTERNALS.md`.
- **Guided fill** (design doc `2026-08-16-guided-apply-design`, unpublished — §10): the panel's **Fill** stage — **Autofill** →
  `panel_prepare` (the gesture-backed injection; `preparePage` is the only other) → a run. `fillMode` (`storage.sync`): "Saved
  answers + AI" (default) runs the fill loop (`shared/fill-loop.js`: Stop, report grouped by status, jump via `fill_focus`, `loop_fill`
  telemetry); "Saved answers only" runs the rule pass below; its rows are `reconcileFill`'s buckets plus the run's own
  writeResults-minus-residue, and the EEO row is the BACKEND's standing consent, never a local toggle. It claims `done.fill` (`touched`)
  only when a run both wrote something and left nothing open (a tick hides the open-fields list); a wizard's LATER pages are reached by
  REOPENING the ticked row, and `startFill`'s per-run clear keeps that re-run's report its own. Per stage ONE runner (`ns.guidedRun.runGuidedFill(deps, {aiAssist, applicationId})`; `aiAssist: false` skips `/choose` and
  residues the whole remainder) runs rule pass → collect → one batched `POST /api/autofill/choose` (qid-keyed, ≤40/call; the option guard
  lives SERVER-side only — any answer not among rendered options, invented qid, or skipped qid collapses to abstain) → `ns.guidedWrite`
  sequenced by widget shape with ONE bounded retry. EXCLUDE'd controls a rule tried and missed become RETRYABLES (`ns.lastRuleAttempts`,
  in-memory per run) routed straight to `guidedWrite`, so their identity VALUES never reach `/choose`; its prompt does carry the saved
  answers (EEO only under inv-eeo-standing-consent) and the career history. Readback is timer-sampled and never defaults to failure:
  unconfirmable is `filled_unverified`, not `not_stuck`. Submit stays human at every setting; Next only in the run below. After each run the panel posts the page's answer receipt
  (`shared/receipt.js`) and lists its flags under **Check before you submit**; a matched job's knock-out heads Fill.
  The loop never fills a robot trap (`fillBase.robotTrap`), leaves an optional field with no fact blank (`left_blank`, listed, not asked), reads pills,
  category rows, slow autocompletes, addresses, URLs and split dates as widgets of their own, commits and confirms each item of a list field (up to 20;
  never a closest pick), repeats no move that changed nothing (a run record's `memory` keeps what failed; `only` limits a call to named fields) and
  waits for the page to settle before typing (`extension/INTERNALS.md`, "The fill agent's rules").
  **`/choose` has two engines**, `fast` and `jev` (`llm.autofill_engine`; Settings › AI & models › **Form filling**): `docs/entities/others.md`, "Form-filling engines".
- **Queued run, one job (Apply)** (`shared/queue-run.js` driver, pure with injected deps; host `panel/actions/run.js`; card `panel/runs.js`; `extension/INTERNALS.md`, "Queued
  run"): with full automation On the Job step offers **Apply**: save, score, pick the resume (never overwriting a tailored draft or an open session), queue as the user's yes
  (consent channel `companion`), then drive THIS tab from the job's apply link (`apply_url`, else `source_url`; http(s) only; started on the job's saved posting it opens the
  saved link; on a job the user picked by hand, THIS page, saved as its `apply_url` if it has none, and `/api/jobs/match` reads both links) through sign-in, fill and Next to
  **Ready to submit**. While it prepares, a live checklist with Stop (taken between steps; what was done stays) shows each step and the base list is locked. Two switches,
  Settings › Form filling (`companion_apply`, `GET/PUT /api/settings/companion-apply`, synced, read only with full automation On): **Choose the base resume for me** (default
  On: pick only when the top score reaches Auto-apply's floor and margin, else ask) and **Stop after each step** (default Off: three presses, the yes at Start filling).
  **Submit is never clicked, at any setting**: `shared/page-kind.js` treats any Submit word, a dialog about submitting or an unseen Submit as the review page (Ready only on a
  real Submit: §6 inv-ready-real-review), and Next is pressed only by `page_advance` (`content/page-reader.js`), which re-sorts the button's labels at click time. A posting's
  Apply (a career site's too, even asking for a new tab: §6 inv-press-filled-page), and a Workday start chooser's Apply Manually link alone, are followed only as a same-tab
  http(s) link (no click handlers) on the first read of a tab the run opened. CAPTCHA, email code, an account on a site it does not know (on a known ATS it creates the account
  itself, §6 inv-job-site-password-local), a job board's own apply, a review page that is not plainly the end, any other start chooser and any unrecognised page PARK (Needs
  you), as does a required field it could not answer, once per page, a refused Next it cannot repair (inv-rejected-next) and a required upload it cannot fill
  (inv-one-resume-write); a required field a search or click landed a value on is listed under **Check before you submit** instead (never a protected one), and an optional
  skills box stays empty. The user answers in the page and presses **Resume**: every typed answer is remembered (Undo; long written ones never; also over a page-errors or
  upload park); one naming the job's company or city is held for that job only (`only_for` + `only_for_kind`, whole word, by `autofill_job.profile_for_job` for both `/context`
  and `/choose`; Settings has Use for every job). The hand fix teaches the recipe book (§6 gesture report). A run parked on a step the user does by hand (posting, chooser,
  unknown page, sign-in, code) follows them into the tab they open, only to the application itself (under the saved link or the posting's Apply link, a leading locale segment
  such as /en-US/ ignored) or a page the backend matches to the job, never drives, and waits for one press, **Continue here**; the Job step's **Move the run to this tab** does
  the same from the other side; a driving run never moves. The user's own Submit is recorded only from a confirmation page on a host the run reached at the same employer,
  straight from the application's own pages, after an 8 s Undo (a tab closed during it marks at once); any other page sets `noAutoMark`, leaving the manual Mark applied, and
  Done on the Ready card ends the record writing nothing (per-run limits, leases and Apply on a live tab: INTERNALS). The Ask box (QnA drawer) sits under the run card only
  while the run is paused. The job memory is per tab (`chrome.storage.session` `widget.sessions`, no clock; origin, tenant, sibling-posting and backend-wins guards).
- **Screening answers dial** (Settings › Form filling; `autofill.answer_level`, default **Balanced**, so an install that had
  the old low-stakes switch off now answers low-stakes questions; the one setting for the Companion, `/map` `/pick` `/step` and agents, via
  the brief's `applying.answer_level`; stored `facts`/`history`/`queued`, shown as the levels below): **Careful** (saved answers and history), **Balanced** (also low-stakes kinds in the
  job's favour, and "N years of a skill" Yes when the history shows it), **Confident** (also every requirement question Yes,
  and a years question Yes only when the history is silent or shows enough, else asked; only for the job's own posting: accepted/approved
  proposal plus `page_url` `is_same_posting` against `apply_url`/`source_url`). The protected list sits outside every level and parks unless
  a saved fact answers it: work authorization and sponsorship, salary, EEO (unless consented), criminal or background history, termination,
  agreements, debarment, clearance and agency employment (never a keen guess), signatures, attestations and authorization boxes (unless Agreements
  consent), licences, unsupported education or experience claims, the applicant's own military service. **Safe defaults** (owner; History level up): a status the profile lacks and that only
  adds something (tribal, union or association membership, a referral, a relative or household member at the company, a spouse's or household member's military
  service) is No (Not applicable, or "I don't wish to answer", if offered);
  willingness or consent to a standard pre-employment step (background check, drug test, references, I-9/E-Verify, documents) and basic means
  (transport, internet) is Yes. Every dial answer is marked on the receipt, so defaults are listed under **Check before you submit**; written drafts: §6 inv-drafted-answers.
- **Streaming chat** runs through `llm_providers` on any provider; eligibility is the tools probe.

## 8. Frontend conventions

Reference tier, like §4: consulted while working in `frontend/`, not read for orientation. Lives in
[`docs/frontend-conventions.md`](docs/frontend-conventions.md): layout and sidebar rules, Tailwind v4 tokens and
M3 colour roles, the studios' save and preview model, a11y and focus behaviour, naming, the copy rules and the one
glossary (the app calls its fixed-rules score **Match score**; *Canonical terms*; ratchets `test_frontend_vocabulary.py`, `test_frontend_sentence_length.py`), each
with the failure mode that bought it. Code citing "§8" lands here.

## 9. Dev & test environment

- Use the backend venv's Python, installed editable (`pip install -e ".[dev,mcp]"`); run from `backend/`.
  A stale `.pth` can pin `app`/`mcp_server` to an old worktree outside that cwd; reinstall and restart the process.
- **MCP loopback and public URL:** `BACKEND_URL` targets REST inside this backend (`http://localhost:8000` in Docker;
  native exports `http://127.0.0.1:$MAESTRO_PORT`). `MAESTRO_CS_PUBLIC_BACKEND_URL` is the assistant-facing local address
  used by Connect an agent app (compose host port, default 8001; native exports its port). Neither publishes `/mcp`.
- **The database is a file.** `data/maestro_cs.sqlite3` (compose bind-mounts `./data` to `/app/data`), WAL, pragmas set per connection by
  `app/db.make_engine` — the ONE engine constructor (app, tests, tools); `prepare_sqlite_file` mints it 0600 and `migrations/env.py` calls
  it too, so a first boot creates the file through alembic. **`env.py` then builds a PLAIN `create_engine` on purpose** — SQLite's batch
  ALTER recipe must run with `foreign_keys` OFF and `make_engine` turns it ON — so do not "fix" it to `make_engine`; it is the one
  exception. Never open the container's file from the host while the backend runs: WAL needs shared memory the Docker Desktop mount does not
  promise — stop the stack or read a `backups/` snapshot. `SQLITE_JOURNAL_MODE=DELETE` (forwarded by compose, commented in `.env.example`)
  is the escape hatch for a filesystem WAL cannot trust. There is no Postgres: v0.4.0 was the one release that imported a pre-SQLite install
  (see the update bullet below). If more than one stack or checkout runs on a machine, they differ by host ports (`*_HOST_PORT` in each
  `.env`) and by `data/` directory — go by those, not by a database name.
- **ATS calibration** — the engine is corpus-tunable, so measure, don't argue. `backend/scripts/ats_snapshot.py` prints a ranking table;
  `backend/scripts/ats_calibration.py` writes a machine-readable snapshot, diffs two (stack stopped:
  `DATABASE_URL=sqlite:///<main-checkout>/data/maestro_cs.sqlite3 BASE_RESUMES_DIR=<main-checkout>/base_resumes python -m
  scripts.ats_calibration snapshot before.json`). It pins `as_of` and groups contribution drops by match-form transition: a CHANGED form is
  a deliberate reclassification, an UNCHANGED one is the shape a real regression takes (exit 1). Base-resume JSON is gitignored PII living
  only in the main checkout — a worktree run needs `BASE_RESUMES_DIR`; snapshots store JD skill names only, never resume text. `python -m
  scripts.ats_calibration monotonicity` (same env) asserts "adding true evidence never lowers the score" over the whole corpus — run it
  after ANY matcher or tier change, not just a scoring-weight one.
- Backend tests: `pytest tests/ mcp_server/tests/ -q -n auto --dist loadfile` from `backend/`; bare `tests/` skips MCP.
  CI cold-installs `.[mcp]`, checks six stdio profiles and `/mcp` + `/mcp/hunt` over HTTP. xdist (~15 → ~3.5 min)
  uses `loadfile` to keep browser tests per file. conftest makes a SQLite file per process/worker (`TEST_DATABASE_URL` may name another,
  never under `data/` or with `-n`) and blanks the four provider keys (`OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`): a worker's `load_dotenv()` finds the
  nearest `.env`, so unstubbed tests made billed calls. Parity tests (`tests/node_ts.py`) need node 24: skip locally, FAIL in `CI`.
- **Deploying a local change = rebuilding BOTH images** (MAINTAINER path, MAIN checkout): `docker build -t maestro-career-studio-backend
  backend/` AND `…-frontend frontend/`, then `docker compose up -d --no-build --force-recreate backend frontend`. A frontend-only change
  still needs the frontend image rebuilt — a stale image once made fixed UI look broken for a whole review.
- **A USER updates instead** — `./scripts/update.sh`: online SQLite snapshot
  (`app.tools.backup_db --stdout` through the running backend container, else the checkout's own image tag —
  `.env`'s `latest` can predate the tool; 0600, magic-byte checked) → ff-only to the newest `v*` tag → images pinned to that tag →
  health poll → extension/MCP reminders (only legacy stdio re-runs setup-mcp.sh; an old Docker `.mcpb` is reinstalled once; README "Updating"). Checkout and images
  move TOGETHER: a bare `docker compose pull` skews an install. Contributors build. The pre-v0.4.0 guard (a `<project>_pgdata` volume with no
  `data/.migrated-from-postgres.json`) and recovery steps: docs/UPDATING.md.
- **Windows = WSL for Docker; the uv install runs natively.** Docker needs Desktop's WSL 2 engine with the clone in the WSL home, never
  `/mnt/c` (SQLite WAL over the Windows share is untrusted; the scripts are bash). `.gitattributes` forces LF
  so a clone cannot CRLF scripts or `.env`; `setup-mcp.sh` is not a Windows route. The `.mcpb` uses HTTP on macOS, Windows and Linux without Docker on the assistant's side.
  The upload host root is `${PWD}` (compose cwd; `update.sh` pins it to the repo) unless `MAESTRO_CS_UPLOAD_HOST_ROOT` overrides it; Windows joins with `\`.
- **uv install (B′, `maestro`)** — `uv tool install --python 3.12 maestro-career-studio`: a `py3-none-any` PyPI wheel of `backend/`
  (version = `backend/pyproject.toml`) plus the Next standalone bundle (`maestro_cs/web/`; `scripts/build_wheel.py`, gated by
  `check_wheel.py`, including root legal files in PEP 639 `dist-info/licenses/`) and Node from `nodejs-wheel-binaries`.
  `maestro start` detaches `maestro run`, a foreground supervisor owning
  uvicorn (127.0.0.1:8001) and `node server.js` (:3000); stop = `run/stop.request` + a signal; process identity = pid + psutil
  create_time. `maestro update` = verified snapshot → stop → `uv tool install --force …==NEW` (Windows: a detached `cmd` script) → start. The web
  process gets no API keys (`home._WEB_STRIPPED`). CI: `maestro-cli`, `uv-wheel`, `uv-smoke`, `uv-upgrade`; `pypi.yml` publishes on
  `v*` tags. `maestro import-docker` copies a Docker checkout's data in once (the checkout is read, never written). Detail: `docs/entities/others.md`, "The uv install".
- **Native run (no Docker)** — `docs/native-install.md`: `backend/scripts/native/` runs one loopback worker under `$MAESTRO_HOME`; URLs follow the MCP rule above, `MCPB_BUNDLE_PATH` uses the checkout's `mcpb/maestro-career-studio.mcpb` (`tests/test_native_scripts.py`).
  `slow` tests skip with `MAESTRO_SKIP_SLOW` (CI); `integration` MCP loopback and `tests/sync/test_two_machines.py`
  run in CI ON PURPOSE, never `slow`: no downloads. With `EMBEDDINGS_OUT_OF_PROCESS` at most ONE embedding
  helper runs per process (`embeddings._HELPER_LOCK`); two ~290 MB helpers OOM. `GET /health/memory` reports memory.
- **Version identity**: the tag bakes into both images as `APP_VERSION`, served by `GET /api/version` with
  the live alembic revision; the frontend warns when its baked copy disagrees, unless either side STARTS
  WITH `dev` (local or dispatch build) = do not compare — which also keeps it off contributors.
- Never verify new code against the docker-compose stack (old images). Launch fresh: uvicorn on a free port with data-dir env overrides (its
  own sqlite file, never `data/`); frontend `API_PROXY_BACKEND=... npm run dev`. TeX is optional (`services/engines` searches the TeX homes
  itself, and `MAESTRO_CS_PDFLATEX=/nonexistent` simulates a TeX-less host). Full recipe: the maintainer's local `verify` skill (not
  shipped). Browser-pane gotchas: DPR mismatch → use ref clicks; toasts overlay the send button.
- **Two dependency sources, on purpose.** `pyproject.toml` keeps `>=` floors for editable/dev installs
  (`pip install -e ".[dev,mcp]"`, also CI); the container installs hash-pinned `backend/requirements.lock`.
  Regenerate that lock with **`mcp` + `tracing` only, on Linux/Python 3.12** (command in `backend/Dockerfile`;
  macOS/3.13 gives wrong pins). CI's `dependency-audit` (`pip-audit` on the lock) failing on a new advisory is intended.
- **No Langfuse stack ships here** (the bundled compose file had fixed default secrets).
  The SDK is the `tracing` extra (included in Docker and native; uv and the desktop build omit it); `services/tracing.py` requires
  all three `LANGFUSE_*` settings. Tracing points at the user's host; `langfuse_host` defaults to empty.
- Alembic revision ids are hand-written fake-hex and COLLIDE easily — generate with `uuid.uuid4().hex[:12]`.
- **SYSTEM.md gate**: `python3 scripts/check_system_md.py` (CI `docs-gate` job) enforces this file's header contract and FAILS (not warns)
  on: the size ceiling; a `(YYYY-MM-DD` date in §1–§10 or any reference-tier file; a shipped item left in §11; a section over its line
  budget; and any §6 invariant whose enforcement pin in `.system_md_enforcement.json` has lost its file or symbol — the "docs promise what
  the code no longer does" class. Re-baselining requires `--update-baselines --reason "<text>"`, recorded in `.slopledger.json`. It anchors
  the repo root on the script's own parent directory, deliberately: a walk-up search finds the MAIN checkout's copy from a worktree and
  validates the wrong file.
- **On merge, re-verify the doc.** Two lanes each update the sections they know about, and the merge can produce a file describing neither
  branch — least accurate exactly when the most agents are reading it. After any non-trivial merge, list the SYSTEM.md sections whose
  subject files changed on BOTH sides and re-read each. The pins catch the worst subclass; nothing catches the rest but this checklist.
- **Slop ratchet.** Per-surface `.slopconfig.json` + committed `.slop-baseline.json` in `backend/`, `frontend/`, `extension/`; the
  maintainer runs `python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check <surface>` from the repo root (not shipped; see
  CONTRIBUTING); non-zero means a metric regressed — fix, or re-baseline with a reason. **RUN EVERY SURFACE YOU TOUCHED AND NAME EACH ONE IN
  THE CLAIM** (the extension's tests live in `backend/`; an unnamed "slop ratchet OK" was the 2026-08-17 false green).
  **`complexity_hotspots` is a COUNT — re-baseline it rather than chasing it**: adding code, adding tests or decomposing a monster all raise
  it; judge erosion by hotspot density per KLOC and the worst cc. Orphan LOC and duplication are honest ratchets. Scan a SURFACE dir, never
  the repo root (it orphans the whole backend); jscpd is optional. The extension's allowlisted clones are the documented commit-ladder twin,
  but the matcher pairs FILE NAMES by substring and `allowlisted_clones` is PRINTED, not gated: check it by eye. Graph signals read the
  gitignored `graphify-out/graph.json` (`graphify extract . --no-cluster --code-only`, PyPI `graphifyy`).

## 10. Design-decision record

**The dated design docs are NOT published.** They live in the upstream private repository; this file is the
public record of what they decided (they are agent handoff scripts — publishing them would ship instructions for
a machine no reader has). This section carries the lineage: which decision superseded which.

Key lineage: 2026-04-22 greenfield → 2026-05-29 jobs/applications consolidation → 2026-07-06 deterministic ATS
gap workflow (fit_scores deprecated; dropped in migration `09265240aade`) → 2026-07-08 tailoring refinements →
2026-07-12/14 health gates → 2026-07-14 career KB (sidecar) → **2026-07-15 applications workflow simplification
+ UI changeover** (D1–D13; the audit findings C# and review fixes referenced throughout this file) → 2026-07-15
parallel delegation tasks (MCP apply-package tools; health-check-v2 override UI) → 2026-07-16 UI polish (Career
KB + extension Q&A) → **2026-07-16 custom resume sections (`extra_sections`) phases 1-2**
(fixed-core-plus-typed-extras, then versioned ATS evidence + stable-key gap placement) → MCP guided tailoring
(caller-authored ops, hint envelope) → MCP onboarding: reversed "approving from MCP is unrepresentable" — a
draft gate needs an approver wherever review happens, and agent transcription is NOT the verbatim-file
exception, so ingest lands drafts and consent-gated `kb_approve_points` is the one approval path from MCP. →
Health check v3: a concrete result stated in words earns full credit (no number quota), and the evaluator asks
each bullet its own question, a number only where one is natural.

## 11. Known deferred items (priority order)

**Item numbers are stable, not positional.** Code and migrations cite "§11 item N" from a dozen places,
so new items APPEND here and shipped items are deleted in place — renumbering silently invalidates every
citation. Priority lives in the item text, not in the ordinal.

1. Extra-section op **payloads** stay loosely typed: `add_extra_section` / `replace_extra_section` `value` is `dict[str, Any]`, validated in
   the service (`resume_edit._validate_extra_section`, like `AddEntry`), so a bad one is a 400, not a 422.
2. One post-render readiness pipeline (a "Ready to apply" gate: health, em-dash, page and contact checks on the exact rendered PDF), on the
   shared rasterized preview + slim MCP `get_rendered_pdf` metadata. Its JD-level half is the knock-out pre-scan (docs/entities/job.md).
3. Base-score staleness on from-base: re-score only when the base's updated_at is newer than the score row — never unconditionally.
4. JD promoted-field correction before gap freezing (today only source_url and apply_url are editable) + score provenance
   (engine/config version) surfaced in the UI.
5. Server-side pagination for the tracker (client caps at 500 rows and says so).
6. Chat KB document provenance: `ChatAttachment` stores extracted text only, so a chat-added document never becomes a
   KB source document — persist bytes, or hand chat a `kb_ingest_document` tool.
8. Agentic job-search phase 2: JobBoard registry (kind/tags/last_checked), SavedSearch model, Job triage state,
   cross-session search-run logging.
10. Work-auth warning CODES: `services/job_search_brief` still reads the two legacy keys and pattern-matches loose
    strings in `warnings[]`; it should understand the typed `WorkAuth` shape.
12. Extension identity-combobox reconciliation (ARIA-widget overwrite is riskier), and block-scoped
    education-vs-employment rule matching (`not:` label guards miss unheaded education containers).
13. Quick-tailor: derive `applied` from the committed resume DIFF, not planned intent; employment-blocks v2.
14. Telemetry v2: option-set fingerprint + normalization; capture-session record for per-site/per-kind saturation;
    failure-count ranking + Analytics drill-down/export; label/option-text redaction; summary pagination.
15. Typst phase 2 (the LaTeX retirement itself is §13): `typst query` AST introspection over source-text capability heuristics; web engine
    picker; in-product .tex→Typst conversion (expose `backend/scripts/template_parity.py --compare` as a backend tool).
16. Onboarding intake: entity resolution ACROSS kinds (a certificate merges into its experience entity, not a
    sibling); a re-runnable "import more"; bounding LLM cost (file cap of 10 in `services/kb_import`).
17. ATS follow-ups: (a) alias/adjacency vocabulary via an OFFLINE human-gated miner over stored `extracted_json`,
    guarded by `SkillMatcher._tokens_contained`; (b) education-as-evidence stays OFF pending a dot-stripping degree
    normalizer; (c) lexical-vs-semantic cert attribution, 1 row in 6,993 — re-check if it grows; (d) stamp `as_of` +
    `jd_extraction_hash` on `AtsScore` and add both to `compare()`'s guard.
19. Auto-apply follow-ups: `source` threading through the explore builders; Telegram consent channel (rejected for
    v1); extension-less CDP fill (HARD constraint: backend CORS must never admit ATS/web origins).
20. `extra_sections` remainder: calibrate the `extra_only` multiplier; nested extra-section entry/bullet ops are
    unbuilt (a bullet op would make the health check's custom-section suggestions appliable, not copy-only).
21. MCP onboarding follow-ups: `near_duplicate_of` hints in the ingest report (normalized-distance vs existing points, so the agent can
    retire one copy without the LLM clusterer); a batch `sources` variant of `kb_ingest_resume` (single-source calls make profile seeding
    order-dependent); a consent story for `_seed_profile`/`_merge_skills` — profile contact and skills have no draft state yet compose onto
    EVERY base; `enabled: false` entries still ingest (LLM-path parity, revisit).
22. Guided Apply follow-ups (design doc has R2 stepper + R3 vault): checkbox collection needs its own safe design (group-level collection,
    legend-level policy screening, mirroring radios; `skipped_checkbox` holds until then); per-ATS selector blueprints; the essay path onto
    qid-keyed `/choose`; `guidedIsListboxButton` stays looser than the two pinned strict discriminators (it rechecks vetted elements only).
23. **Some §6 invariants have no enforcement pin** (`unpinned` in `.system_md_enforcement.json`): when next working in
    one of those areas, add the pin or demote the rule to a convention note.
24. Surface `schemas/job_extraction._coerce_enum` warnings through the jobs-ingest response, so `store_extracted_jd`
    callers see that input X was stored as `unstated` (audit 2026-08-22, finding A1).
25. SQLite has one write lock, and two transactions hold it across LLM calls: `kb_consolidation.consolidate` (flush, one LLM call per
    entity, one commit — `seeding.seed_career_kb` relies on that via `commit=False`) and `tailoring_session.create_session` with enrichment
    (score flush + supersede UPDATE, then the call). A concurrent writer waits `busy_timeout` (30 s), then fails "database is locked". Fix:
    compute every LLM result first, then write in one short transaction, keeping the seeder's `commit=False` contract.
26. `TailoredResumeStudio` adoption gaps: (a) two Saves in one refetch window, the second returning to adopted content, read as foreign
    (`onSaved` queues no key equal to `adoptedKey`): a false "changed outside the editor" banner; (b) the parent-held `templateId` never
    re-syncs from the server, so it survives Rebuild and Load latest, and a foreign template-only change reads as an unsaved local edit.
27. `FullscreenEditorPage` is `h-dvh` (both studios, the template editor), and `VersionBanner` renders above it in
    `SidebarGutter`, so the page overflows by the banner's height whenever the banner shows.
28. Dark `--ring` on `--primary-container` (the FAB) is 2.88:1, so that surface is not in `_RING_SURFACES` (1.4.11).
29. Focus lands on `<body>` on Escape from the <768px sidebar sheet (which stays open after a nav tap) and after any
    client-side link navigation. `Button nativeButton={false} render={<a>}` announces a link as a button (~40 sites,
    21 files): use `buttonVariants` on a plain `<a>` or `GuardedLink`, the sidebar's pattern.
30. Raw keys or jargon still reach the user or an agent: MCP `explore_*` results carry role slugs with no `role_label`; the Assistant's
    Edited and project cards call an application target only "tailored resume"; `resume_diff.attribute` labels any unmatched change `"llm"`
    (the Review changes chip is hidden for it; an `"unknown"` value would change the endpoint's response).
32. Small UI gaps: `/base-resumes/<unknown>/health` shows a skeleton ~7 s before its error (the 404 takes react-query's three default
    retries; `app/providers.tsx` sets no `retry`); `/templates`' stale-chip tooltip sits under `GalleryCard`'s `z-10` stretched link; three
    hint/control pairs hardcode ids (`new_id_hint`/`new_id_error`, `kb-profile-notes-hint`, `job-preferences-locations-hint`); Escape from
    the job Details date field blur-saves `applied_at: null`; an Assistant edit card's Discard works while Apply runs; a failing settings
    autosave toasts once per keystroke; a failed send in a NEW chat leaves an "Untitled chat" (the session is made before the message).
33. inv-render-fallback-explained gaps: `PUT /base-resumes/{slug}` commits, then a pdflatex failure is a 500 over the
    saved change; `POST /{slug}/render` answers 500, not 400, on a generic failure; the preview-page route's unlocked
    `exists()` can race a re-render; `STARTER_SOURCE` fails on a blank email with a link present.
35. Settings seed race: `text_settings.get_text` lazily INSERTs a missing `Setting` row and commits, so two first
    reads at once both insert and one fails on the key; the commit also ends an open transaction (hence `POST
    /api/proposals` reads `get_settings` before `begin_write`). Seed at startup or insert-or-ignore.
37. ATS reads "Mon YYYY" dates only (`resume_indexer.parse_month_year`): "2021-03", "03/2021", "2021" leave a job
    undated (the UI says so). More formats move scores: calibrate first (§9 `ats_calibration`).
38. A double-clicked "Tailor resume" opens and closes its confirm; with the backend down, every card on Settings,
    Analytics and Career repeats one error (a page-level message needs a shared mechanism).
39. Windows is unverified end to end: install, update, Companion load from `\\wsl.localhost\...` (GETTING_STARTED
    gives a copy-to-`C:` fallback), `.mcpb` on Windows Claude Desktop, and the WSL upload host root.
40. Companion reliability: ARIA label resolution, retry identity, unmatched combobox discovery, live-option decisions,
    popup ownership and committed-selection verification remain open. Reproductions and Jev-first proposal: [extension
    research report](docs/reports/2026-09-25-extension-reliability-research.md).
41. Health check follow-ups: one-at-a-time question mode; repeated-opener notes; a rubric check on tailored drafts; a dispute MCP tool
    (disputes are web-only); a **Not right?** reply on a row queued for Write is overwritten by its draft; a hand-set "Shows a result"
    leaves the report, so Done can't reset it; rename `BaseResumeDetail.version_number` to `edit_version_number`.
42. Answer trust follow-ups: fix-and-learn from the receipt; the auto-submit preview; a "What Maestro knows about you"
    page; a JD-extracted graduation/enrollment knock-out; `RECORD_NEVER` folded into `NEVER_FILLED`; receipt capture
    across a full-page navigation and for a manual Attach press. Phase-4 source limits: `docs/entities/filled-answers.md`.
43. "In N resumes" (`services/career_kb.used_in_bases`) reads `kb_port_log`, which is append-only: it means "added to or came
    from", so it can overcount; `create_from_kb` and base duplication write no rows, so those bases are missed.
44. Companion run limits left on purpose: a robot-trap option inside a real checkbox/radio group (shared name) is not filtered
    (honeypots are standalone text boxes); sync's duplicate resolution that keeps the laptop's twin drops the other copy's
    `apply_url`, and a replica's link is never sent to its owner; a password-only second sign-in screen parks (`no_email`); technique
    cards for group, select and date widgets are never reached (the adaptive step runs for popup and search only); a page with no
    heading never reads as a rejected Next, `heldValues` misses a select's shown text and a custom combobox, and the hand-attached-file
    check reads the run's own frame only; the run list, Queue view and parallel tabs wait for Phase 3 (`docs/plans/2026-10-10-companion-queued-run.md`);
    the rest of the 2026-10-14 live-check limits: `extension/INTERNALS.md`, "Known limits".
45. Scoring at save is inline on both paths; a background task for the ingest path raced the Companion's own `POST /api/ats-scores`
    on the base-score unique key (two concurrent `score_all_bases` runs always collide). Revisit with a savepoint-tolerant upsert in
    `score_target` if ingest latency on native installs needs it.
46. The Companion's `addJob` still scores after its ingest (`extension/panel/actions/job.js`), a harmless second upsert whose comment
    at lines 116-117 is stale; and the capture pipeline (`_find_existing`, `_persist_job`, `_insert_skills`, `_score_new_job`) lives
    in `routers/jobs.py` and could move to a `services/job_capture.py`.

## 12. Gotchas that have bitten before

- **A hidden tab stalled saves** (2026-10-13): TanStack v5 scoped mutations queue as paused and continue only while the tab
  is focused → serialize saves with a per-key promise chain (`lib/in-order.ts`), never a mutation scope.
- **An update served the old version's pages** (2026-10-12, 0.10.0): Next writes `.next/server/route-cache` inside the
  installed bundle at run time; uv replaces only shipped files, so 0.9.0's cached HTML (dead script and CSS links) outlived
  the update → `maestro run` clears it before the web starts (`runtime.clear_web_cache`).
- **Playwright makes every tab visible** (2026-10-11 spike): launch or `connect_over_cdp`, `document.hidden` stays false, so
  background-tab behaviour can't be measured attached → run Chromium unattached over the DevTools HTTP endpoints
  (`scripts/spike_background_fill.py`); macOS also hides every tab of a covered window.
- **Sync MCP tools deadlock on the event loop** (2026-10-10 spike): a same-backend REST call blocks single-worker
  uvicorn → `http.offload_tools` uses its own worker limiter; pinned by `tests/test_mcp_http_loopback.py`.
- **Owned-session prompt reads never seed** (2026-10-10): a lazy INSERT waited out `busy_timeout` behind a caller's
  write and hid a mocked outage → only caller-supplied sessions seed; startup seeds the rest (`tests/test_prompts_service.py`).
- **Guard files before commit** (2026-10-06): refusal still deleted documents/changed previews → check before disk I/O, including helpers (`tests/sync/test_guard.py`).
- **Retry keys must identify controls** (2026-09-25): rule attempts use composite labels, collection clean questions, so
  `country | field-12` never reaches the `country` retry → use element identity; a model upgrade cannot repair fields
  collection never sends (§11 item 40).
- **Same page is not same URL** (2026-09-23): the leave guard stopped every same-pathname popstate, so Back between `?tab=`
  or `?session=` entries changed the URL, not the screen → `samePage` decides what asks, the URL what renders (`lib/leave-guard.ts`).
- **A page's `searchParams` prop keeps its arrival value after a native `replaceState`** (2026-09-23): a link to
  another tab of the same page opened nothing → read `?tab=` with `useSearchParams`, and keep `use(searchParams)` in
  the page (without it `next build` fails on `useSearchParams` outside Suspense).
- **Base UI scrolls a tab into view along `offsetParent`s** (2026-09-23): an unpositioned tab row is not on that
  chain, so a dialog's padding was counted and Home left the first tab cut off → the row is `relative`.
- **An sr-only span beside a flex item is out of flow** (2026-09-24): Chrome's accessible name gains a space ("Agent
  inbox , 3 need you") → a one-phrase count goes in `aria-label`; check Chrome's AX tree.
- **Rewording a health `issue` orphans saved ask answers** (2026-09-24): `_fid` hashes the text → pass the old text as
  `id_key` (`resume_lint.py`). v3 kept the measure, digit-quoting analogue and uncertain keys; detail asks are new.
- **A prompt-contract change bumps `RUBRIC_VERSION`** (2026-09-25): cache rows key on text + rubric version + model,
  so unchanged text kept its old judgment → bump it and resync the prompt row; overrides and "no number" survive.
- **A GUI-launched process has no shell `PATH`** (2026-09-20): a bare `pdflatex` misses MacTeX's `/Library/TeX/texbin`
  in desktop apps → `engines.find_pdflatex` searches TeX homes after PATH; every run spawns its absolute path.
- **A seeded template copies source only on INSERT** (2026-09-20): import landed rows after migrations, restoring
  old bytes → `template_registry.SUPERSEDED_SEED_DIGESTS` resyncs at seed time, including Classic when another template is default.
- **SQLite and Alembic traps** (per-connection `foreign_keys`, TypeDecorator autogenerate, Boolean defaults, `commit()` flushing,
  unclosed `sqlite3.connect`, timestamp resolution): `docs/entities/others.md`, "SQLite and Alembic gotchas".
- **One path, every job** (2026-09-01): LinkedIn's list rewrites only `?currentJobId=` and the matcher dropped the
  query string, so every job was the first one saved. A query-keyed board needs its key in BOTH `posting_id` tables
  (§7); an SPA's `<head>` JSON-LD is the PREVIOUS job's until checked.
- **A starter that fails its own gate** (2026-09-01): the from-scratch template certified `false` on an untouched
  draft. What the app mints AND validates in one request must clear every probe.
- **Extension-only `accept` lists grey out real files** (2026-09-01): six hand-typed pickers, no MIME types. Every
  picker reads `frontend/lib/upload-accept.ts`.
- **A guard test mocked away the guard** (2026-08-25): a green suite hid a 100%-failing rewrite path because it replaced
  `guarded_rewrite` → when a guard or validator is the subject, fake `llm.call_openai`, never the guard.
- **The FAST model quietly caps score honesty** (2026-08-24): flash-lite extractions missed conceptual JD skills →
  base ATS scores inflated ~9 pts vs fuller extractors. Fast tier drives coverage/honesty/latency; Smart barely moves
  outcomes — re-benchmark FAST before changing model defaults.
- **`autoflush=False` sessions**: two `session.merge`s that canonicalize to the same PK in one flush both INSERT (no
  dedup) → IntegrityError. Dedupe in Python first (see `_insert_skills`).
- **Pydantic error mapping order**: `ValidationError` subclasses `ValueError` — catch it FIRST or 422s become 400s.
- **Transient response attrs**: `already_existed` (Job), `health_warning` (TailoringSession) are instance attrs set after
  refresh; `base_anchors` (TailoringSession) is a model property. None is a column — don't "fix" them into the ORM.
- **score_target(result=...)**: passes a precomputed engine result to persist; the double-run it replaced was audit
  finding C18 — don't re-add a second run.
- **The query cache keeps old key order** (2026-09-22): structural sharing made a refetch's `JSON.stringify` differ from
  the PATCH response, so a studio's own Save read as foreign → compare `serverKey` (sorted keys); §11 item 26.
- **PDFium is not thread-safe** (2026-09-23): parallel gallery previews segfaulted libpdfium → every PDFium use under
  `app/` holds `services/pdfium_lock.PDFIUM_LOCK` (AST scan in `tests/test_pdfium_lock.py`).
- **Worktree subagents** may edit the MAIN checkout: hand them absolute worktree paths, verify with `git -C <wt> status`.
- **Ports 8000/8001 may be squatted**: `/openapi.json` `info.title` is "Maestro CS API".
- **Check model capability in the ROUTER, never inside `run_turn`**: `run_turn` is a generator — anything it raises
  fires after the SSE headers are out and reaches the browser as a truncated stream. Capabilities are probed on save
  (`llm_capabilities.probe()`); `require()` raises `CapabilityMissing`; unprobed models are never blocked.
- **A probe must issue the SAME call as the surface it measures**: the adapter `stream` call in `llm_providers` (`provider.stream`), so client and kwargs
  match by construction. A re-implemented call's stored row SHADOWS reality (a false tools=No once 422'd every chat message).
- **LLM provider outages are ONE exception type**: `llm.py` normalizes them to `llm.LLMProviderError`; `app.main` maps it to
  502 + its `str()`, a user sentence; plain `RuntimeError` is LOCAL (500). Never catch `openai.*` in routers; classify on
  `provider_detail`, never `str(exc)` (a user sentence once replaced the text the capability probe matched on, 2026-09-24).
- **`delete-orphan` cascade vs bulk re-point**: a bulk `update()` moving children off a parent leaves its loaded
  collection stale, so `session.delete(parent)` cascades away the moved rows → expire the parent between (`career_kb.merge_entities`).
- **Workday apply steps read as "no form"** (2026-09-25): no `<form>`/`<select>`, a `type="text"` phone and no email on My
  Information, so every step but the résumé upload scored 1 and Fill was withheld → measure `detectPage`'s signals on the
  live page before blaming timing; the fix is `workday-apply-route`.
- **Tailwind v4 compiles some classes to nothing** (2026-10-06): a variant on a plain class (`data-confirm:animate-confirm`
  until it was an `@utility`) and an unknown role (`border-outline`; check `--color-*` in `globals.css`); `translate-*`/`scale-*`
  set those properties, so `transition-[…transform]` jumps → register a class that takes a variant; name those properties.
- **Agent sandboxes kill what a tool call starts** (2026-10-10): a server vanished between calls, even with `setsid` → run
  start, checks and stop in ONE call (`scripts/smoke_uv_install.py`), or use `maestro autostart`.
- **Child-server startup signals have separate meanings** (2026-10-10): reverse DNS can stall listening, while
  “Started” precedes child output → fixtures bypass DNS, report bound ports, and wait for asserted output before stopping.

## 13. Active migrations & deprecation ledger

**The rule.** A row tracks a superseded path until deletion, with an observable **removal trigger**.
§11 = work NOT YET BUILT; §13 = work built TWICE. Cut superseded prose from its home section;
leave "migration state: §13 `<id>`". Remove the row when the old path is gone.

**Machine-checked.** Rows with executable triggers are mirrored (TRIGGERS only, same ids) in
`.slopledger.json`; the maintainer runs `python3 ~/.claude/skills/ai-slop-detector/scripts/ledger_check.py
. --strict` (not shipped) to detect drift; rows without predicates are verify-by-hand. Re-verify triggers
on a schedule: a stale `ready-to-cut` claims a deletion is safe without evidence. Cut rows live in
`git log SYSTEM.md`.

Status: `both-live` (both reachable, old still default) · `new-is-default` (new path is canonical, old
survives as fallback/backup) · `blocked` (trigger cannot be evaluated until a named prerequisite lands)
· `ready-to-cut` (trigger met).

| id | old → new | status | removal trigger | effort |
|---|---|---|---|---|
| `mcp-stdio-venv` | stdio host venv (`setup-mcp.sh`, `maestro-career-studio-mcp`) and `docker exec` examples → URL (`/mcp`) + `.mcpb` bridge | new-is-default | The release after `/mcp` ships (v0.10.0): delete `scripts/setup-mcp.sh`, the venv paragraphs in docs/USING_MAESTRO.md, GETTING_STARTED and the mcp_server README, and every `docker exec … mcp_server.server` example. Keep the `maestro-career-studio-mcp` console script as the `maestro mcp` fallback until B′. | small |
| `typst-default-flip` | seed `default` (LaTeX Classic) → seed `typst-classic` | both-live | **HELD by owner 2026-08-09: LaTeX stays, both engines remain first-class.** This is a longer park than 2026-08-02's, not a cancellation — the row survives because the trigger is still reachable, but nothing is waiting on it and `latex-render-path`/`texlive-layer` stay blocked behind it indefinitely. Header defects fixed (Typst `ulink()`; LaTeX separator space), DB rows re-synced. **The CLEAN 8/8 parity corpus predates 2026-08-08's extractor swap** (PyMuPDF→pypdfium2, forced by the Apache relicence), so those numbers were taken with a different measuring tape — re-run the corpus before acting on them. Then repoint `_bootstrap_default` (template_registry.py:131); a runtime `set-default` is NOT enough, seeding re-mints the LaTeX default on every fresh install. | medium |
| `latex-render-path` | `pdf_render` latex branch + `*.tex.j2` → typst branch + `typst_classic.typ` | blocked | `select count(*) from templates where engine='latex'` = 0 **and still 0 after `GET /api/templates`** (which re-runs `ensure_seed_templates`); `cover_letter.tex.j2` has no caller, i.e. `render_cover_letter(engine="latex")` is unreachable — `compile_cover_letter_pdf` itself survives as the engine-dispatching entry point for both; no surface (web, chat, MCP, STARTER_SOURCE) can mint a latex row. Blocked on `typst-default-flip`. | large |
| `texlive-layer` | minimal TeX Live layer (`backend/Dockerfile`) → `typst==0.15.0` in-process | blocked | Layer is already slim (install-tl `scheme-basic` + 18 tlmgr packages) and XCharter is vendored at `backend/app/assets/fonts/xcharter/` (keep the Bitstream Charter notice alongside; `settings.typst_font_paths` defaults there, so typst no longer reaches into texlive). The remaining FULL cut requires only: `grep -rn pdflatex backend/app` returns only comments. Blocked on `latex-render-path`. | medium |
| `chat-selection-kind` | untagged resume chips → `ChatSelection.kind` (`resume`\|`kb_entity`) | both-live | All three scope-picker constructors emit `kind:"resume"`, THEN zero `chat_messages.meta_json->'selections'` elements lack a `kind` key. | small |
| `autofill-education-shape` | single-object `education`, coerced in 2 clients → list (the server returns the stored JSON as is) | both-live | `GET /api/settings/autofill` returns `education` absent or an array for a pre-normalization profile. Cut the frontend coercion first, the extension one release later. | small |
| `autofill-work-auth-shape` | `work_auth.authorized_to_work` + `requires_sponsorship` (two timeless booleans, stored "yes"/"no") → typed `WorkAuth` (`schemas/autofill_profile.py`: `status`, `authorized_now`, `sponsorship_now`, `sponsorship_future`, `authorization_expires_on`, `countries_authorized`) | both-live | Delete when no raw-profile reader uses either legacy key. Today's storage readers are FOUR: `services/autofill_profile.py`'s legacy branch, the Settings editor's legacy-on-edit bridge (`components/settings/autofill-section.tsx`), the fill engine's dual-read (`content/autofill.js`, the `w` binding in the profile normalizer; moved from agent.js at the phase-2 split), and the panel's `workAuthForWrite` (`panel/actions/pause.js`), which promotes the legacy pair before the first typed pause-row write. The panel copy is the trap: `.slopledger.json`'s trigger paths cover `extension/content` only, so the mechanical check goes GREEN while that reader lives — widen the paths or verify it by hand. `job_search_brief`'s identically named response fields are a frozen outward compatibility projection from typed `authorized_now` / `sponsorship_future`, not a legacy reader, and do not block removal. ALSO `GET /api/settings/autofill` must return a `work_auth` carrying neither legacy key. Then delete the legacy branch of BOTH `autofill_profile.get_work_auth` and the extension's `w` binding. Per `autofill-education-shape`: cut the frontend first, the extension one release later. | small |
| `job-location-raw` | `jobs.location` (dual-written) → `location_raw` + city/state/country | both-live | Stage 1 (schema shim + `.location` property) already met. Stage 2: no reader of `jobs.location` remains, then `op.drop_column`. | small |
| `health-rewrite-cache` | unattended rewrite always-LLM → `bullet_rewrites` (NULL text = tried-ask) + ephemeral ask answers → `health_ask_answers` | new-is-default | Migration `85a1bb628e28` (pre-SQLite chain, removed in v0.5.0; the tables are in the SQLite baseline). The LLM miss path is the intended fallback, not a second product — cut this row when a follow-up deletes either table or the GET `/api/resume-lint/{kind}/{key}/answers` rehydrate. | small |
| `chat-message-parts` | `chat_messages.tool_calls` / `tool_call_id` columns → neutral versioned `parts` (+ `provider`, `model`; migration `cf0804d00ae2` backfills) | new-is-default | The release after this one ships: drop both columns, `transcript.from_legacy` and the `ChatMessageRead` legacy fields in one migration. Readers: `transcript.from_legacy` fallback, `ChatMessageRead`. | small |
| `native-scripts-to-maestro` | `backend/scripts/native/*.sh` (always-on bot) → the `maestro` command | both-live | The always-on bot runs on `maestro` for one release, then delete `backend/scripts/native/`, `docs/native-install.md` and `tests/test_native_scripts.py`. | medium |
| `lock-wheel-deps` | `requirements.lock` as the image's whole runtime set (names the old `maestro-career-studio-backend`, no `psutil`) → regenerated lock that omits `nodejs-wheel-binaries` (`pip-compile --unsafe-package`); the image adds the project with `--no-deps -e .` | both-live | Lock regenerated in `python:3.12-slim`: it has `psutil==`, `nodejs-wheel-binaries` not pinned, no `maestro-career-studio-backend`. | small |

**Row notes** (only where the trigger hides a trap):

- `typst-*`: strictly ordered flip → delete-latex → drop-texlive (the font is vendored, so the old
  drop-the-layer-changes-the-font trap is closed).
- `chat-selection-kind`: inverted today — the branch four comments call "legacy" is the only form the
  frontend emits (`scope-picker.tsx` sets `kind` on kb chips only), so `kind:"resume"` is unreachable and
  those comments mislead until stage 1 ships.
- `autofill-work-auth-shape`: three traps. (0) The reader count is FOUR and one of them sits outside the
  trigger paths — see the row. (1) `sponsorship_now` has NO legacy source and stays `None` on purpose —
  defaulting it from `requires_sponsorship` answers the OPT case wrong (no sponsorship NOW, needed later);
  unknown must stay unknown. (2) `job_search_brief`'s public legacy-named response fields are a frozen
  projection of the typed reader, not a storage-migration blocker.
- `job-location-raw`: `JobSummary` exposes ONLY the old field (no `location_raw`), so the list endpoint is
  the hardest blocker to dropping the column.

**Not migrations — do not re-file these here** (each was proposed as a row and rejected): the 4-way
application-status vocabulary and the 3-way `quick_tailor_profile` shape are hand-synced by design; the
`/api/explore` prefix and 7 MCP tool names are a deliberately frozen public surface after the UI rename;
the typed-op vocabulary lives in `schemas/resume_edit.py` (item 1 tracks only the extras-payload
residual) and is not a migration. Cross-boundary duplication (a Python enum and its TypeScript mirror)
is never a ledger row — it needs a contract test, not a deletion. The two seniority lists are NOT a
subset relation and must not be merged — see §4 AtsScore, "Rank markers are domain data"; merging them
would be a scoring bug.
