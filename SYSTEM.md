# Maestro CS — System Reference

> **This is a living document.** If you are an agent (or human) making changes
> to this repo: **update this file after your change** whenever it alters an
> entity, lifecycle, endpoint, invariant, workflow step, or convention described
> here. The next agent starts from this file; stale docs cost more than no docs.
> Why these rules: `docs/system-md-contract.md`.
>
> **1. Integrate, don't append.** When your change alters described behavior,
> REWRITE the affected description in present tense — do not add a dated
> paragraph below it. Dates and change narratives belong in `git log`, not in
> the descriptive sections. Dated entries are legal ONLY in the three ledgers
> (Known deferred items, Gotchas, Active migrations).
> **2. Ledgers must shrink.** A deferred item leaves when shipped (git
> remembers) or when 30 days pass without a "do when" trigger; a migration row
> leaves when the migration completes; a gotcha leaves when its cause becomes
> enforced. If your change supersedes something without deleting it, add a
> migration row — and cut the prose it replaces.
> **3. Log what you paid for.** After a session, append genuinely new lessons
> to Gotchas (dated, symptom → cause → rule, ≤3 lines) and deliberately-not-fixed
> observations to Known deferred items, each with its trigger. Not a diary —
> only what would have saved you time.
> **4. Cover what you touched.** Working in an area this file does not
> describe? Add the section for it.
> **5. Caps are earned.** The size cap is in BYTES; lines are reported, never
> gated, because a line cap is met by widening lines. The cap moves only
> immediately after a grooming or extraction pass that failed to get under it —
> prove incompressibility before buying budget. `scripts/check_system_md.py`
> records every movement with its reason and writes the revision stamp below;
> no hand maintains it.
>
> **Section numbers are frozen.** Sections 1–13 keep their numbers permanently;
> new sections append at the end. Code, migrations, and handoff docs cite "§N"
> from ~129 places, and the last renumbering silently invalidated every one of
> them. Cross-cutting invariants additionally carry stable ids (`{#inv-slug}`) —
> cite those from code in preference to a section number, since they survive
> any grooming.
> **Two tiers.** This file is the ORIENTATION tier and stays whole. Pure
> reference — entity lifecycles (`docs/entities/`), agent surfaces
> (`docs/agent-surfaces.md`) and frontend conventions (`docs/frontend-conventions.md`)
> — is extracted, indexed from Core entities, Agent surfaces and Frontend
> conventions, and carries this same contract. When the cap is hit,
> extract more reference; never split orientation content.
> **Style rule:** every rule bullet in Cross-cutting invariants and in
> `docs/entities/` opens with a **bolded subject** naming what the rule governs,
> so the section scans by lead terms. Every invariant states its enforcement
> point — the test or module that fails if it breaks — and is pinned in
> `.system_md_enforcement.json`. Active migrations is machine-checked via
> `.slopledger.json`; the whole file via `scripts/check_system_md.py`.
>
> contract: v5
> Last revision: 2026-10-16 133dec89 (gate-written)

**Contents**
- [§1 What this is](#1-what-this-is) — the product in one paragraph
- [§2 Repo layout](#2-repo-layout) — directory map with one-line roles
- [§3 Architecture at a glance](#3-architecture-at-a-glance) — data-flow diagram, where state lives
- [§4 Core entities and their lifecycles](#4-core-entities-and-their-lifecycles) — INDEX into `docs/entities/`: per-model rules, state machines,
  scoring semantics
- [§5 The application workflow, end to end (web)](#5-the-application-workflow-end-to-end-web) — the nine user-facing steps
- [§6 Cross-cutting invariants (do not break these)](#6-cross-cutting-invariants-do-not-break-these) — rules that must never break, with enforcement points
- [§7 Agent surfaces](#7-agent-surfaces) — INDEX into `docs/agent-surfaces.md`: MCP server, in-app chat, extension
- [§8 Frontend conventions](#8-frontend-conventions) — INDEX into `docs/frontend-conventions.md`: layout, a11y, naming, copy rules
- [§9 Dev & test environment](#9-dev--test-environment) — interpreter, DBs, calibration, deploy, gates
- [§10 Design-decision record](#10-design-decision-record) — lineage, then one line per owner decision with the alternative it superseded
- [§11 Known deferred items](#11-known-deferred-items-priority-order) — ledger of work not yet built
- [§12 Gotchas that have bitten before](#12-gotchas-that-have-bitten-before) — dated symptom → cause → rule entries
- [§13 Active migrations & deprecation ledger](#13-active-migrations--deprecation-ledger) — built-twice rows with removal triggers

**Read for the task** — the file is read in slices; this names the slice. Every slice starts with the header.

| Work | Read |
|---|---|
| Any first visit | §1, §3, §12 |
| Backend write path, model, endpoint, migration | §5, §6, §9, `docs/entities/`, §13 |
| Extension, Companion, MCP server, in-app chat | §7 → `docs/agent-surfaces.md`, §6, §12 |
| Frontend | §8 → `docs/frontend-conventions.md`, §6, §12 |
| Planning a feature or a redesign | §3, §5, §6, §10, §11, §13 |
| Release, install, CI | §9, §13, `docs/RELEASING.md` |
| Docs-only change | the section you touch, §12 |

## 1. What this is

A single-user job-application copilot for any field and any country: capture job descriptions, score base resumes
against them with a deterministic ATS engine, walk a gap-analysis workflow, LLM-tailor the resume, render a LaTeX
PDF, generate the apply package (cover letter, screening answers), and track every application from Saved to
Accepted. It opens on **Today** (the one move that matters most), a new install runs a four-step **Setup** once, pay
reads in one home currency (ECB rates) and work-permit answers are kept per country applied in. Three
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
                       base_resumes, templates, qa, career_kb, chat, autofill, proposals, settings, today, fx, …)
    services/          business logic (ats/, tailoring_session, gap_analysis, kb_import, application_writes,
                       engines (the ONE probe), pdf_render (dual-engine: pdflatex + typst), jd_extraction,
                       resume_lint, resume_voice, health_*, chat_agent + chat_tools, transcript (chat rows as
                       neutral parts; NULL `parts` = legacy row), llm_providers/ (neutral LLM types, errors,
                       registry (model id to provider), OpenAI-compatible, Gemini and Claude adapters),
                       attachment_extract (bounded DOCX/PPTX + notes; decks are documents),
                       autofill_choose + autofill_reason + contact_scan + autofill_slots + autofill_education + autofill_place + autofill_sponsorship + board_visits + jev (Companion fill), resumes_folder (visible PDF copies),
                       application_status (the one status writer), countries + markets + autofill_country (data:
                       services/data/*.yaml), money + money_settings + fx_rates (ECB), rates, search_summary, today, …)
    automations/skills/  the agent prompts, one <name>/SKILL.md each: the Automations
                       source of the Automations page; indexed by docs/skills/README.md
    templates/         six seeded resume designs + both cover-letter sources (licenses: THIRD_PARTY_NOTICES.md)
    tools/             operator tools, `python -m app.tools.<name>`: backup_db
  mcp_server/          FastMCP registry → a server per tool set (build_set), on stdio or http.py's ASGI endpoint; client.py httpx → REST
  maestro_cs/          the `maestro` command (uv install, §9): CLI, supervisor, home layout, update, connect, stdio bridge
  migrations/          alembic: the SQLite chain, baseline 871d0425b64c + revisions (ids: §9; §12 has the revision-id gotcha)
  tests/               pytest on a throwaway SQLite file, no service; mcp_server/tests/ uses respx (no DB)
  scripts/             calibration + parity tooling (ats_*, template_parity, health_golden, fill_trace, eval_reason), run from backend/
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
 extension ─┼→ jobs router → Job row  ├─ MCP /mcp inside FastAPI (94 tools)
 MCP ingest┘        │                 └─ chat agent (chat_tools.py — separate toolset)
                    ▼ ATS engine (deterministic, LLM-free)  →  AtsScore rows (base upsert / tailored append)
                    ▼ TailoringSession (frozen gaps → resolutions → LLM tailor ops)
                    ▼ Application (customized_json draft) → LaTeX render → PDF + preview PNGs
                    ▼                              ▼
        status tracking (StatusChip)        QA router (cover letter / answers)
```

`data/maestro_cs.sqlite3` (SQLite, WAL) holds rows and local sync clocks; ORM flushes stamp jobs/profile, including imports and both sides of moves. A
job still at revision 0 is stamped from that clock when this copy pushes or lists its jobs. Deleted jobs leave tombstones; Core writers touch their
subtree (`services/sync/hooks.py`; the write guard is §6
inv-flush-guard). Resume JSON/rendered files stay on disk (`base_resumes` row + file required); job-site login: `settings/secrets/` (§6). A uv install
keeps all of it in one per-user folder (inv-one-home). **LLM calls** go through the front door `llm.py` (`call_openai`, key getters; four keys, env
keys as fallback). `llm_providers/registry.resolve` routes a model id by catalog tag, then keys/prefix, to an adapter (OpenAI-compatible incl. custom
servers and the privacy-locked OpenRouter preset, Claude, Gemini); chat streams through the same adapters. The scoring model's first download and the ECB
exchange rates (when a page asks: one success a day, a failed try waits an hour; `services/fx_rates.py`) are outbound calls with no
user data; PRIVACY.md lists every one.

**Sync** is optional, on only while a key file exists (`docs/sync-setup.md`): the laptop owns the profile, each job has one owner
(docs/entities/job.md), nothing merges (inv-one-writer-ownership). The always-on copy drives: `sync.sh` (cron; `--now` forces a round) or MCP
`sync_now` asks its
backend for a round (`POST /api/sync/round`, `services/sync/round.py`), which calls the laptop's `/api/sync/*` on the sealed channel
(inv-sync-channel), one transaction per step; failures back off 5 to 30 minutes. Changes to the other copy's job wait as `sync_requests`;
a laptop job is offered only when queued `accepted` on the laptop with full automation on (`offers.mark_when_queued`); switching it off withdraws offers.

## 4. Core entities and their lifecycles

Reference tier: consulted per task, not read for orientation, in `docs/entities/`, keeping the root orientation-sized; each file carries
this contract. Code citing "§4" lands here; the table says which file to open.

| Entity | File | Scope |
|---|---|---|
| Job (`models/job.py`) | [`docs/entities/job.md`](docs/entities/job.md) | raw JD text + sha256 dedup; one ISO `country_code`, work mode and level as keys, posted pay with `salary_currency_assumed`; has no status of its own |
| Application (`models/application.py`) | [`docs/entities/application.md`](docs/entities/application.md) | one per job (its base resume moves with a tailor); status vocabulary, the one writer `set_status` and its dated log (`ApplicationStatusEvent`), tailored draft, render artifacts |
| TailoringSession (`models/tailoring_session.py`) | [`docs/entities/tailoring-session.md`](docs/entities/tailoring-session.md) | the open → tailored | superseded | abandoned machine; frozen gaps |
| AtsScore (`models/ats_score.py`) | [`docs/entities/ats-score.md`](docs/entities/ats-score.md) | base upsert-singletons vs appended tailored history; deterministic engine |
| ResumeVersion (`models/resume_version.py`) | [`docs/entities/resume-version.md`](docs/entities/resume-version.md) | append-only snapshots on every write path — the undo story |
| FilledAnswer (`models/filled_answer.py`) | [`docs/entities/filled-answers.md`](docs/entities/filled-answers.md) | the answer receipt: what each form page run filled, each answer's source, the warn-only flags, the EEO lifecycle |
| AgentRun (`models/agent_run.py`) | [`docs/entities/agent-runs.md`](docs/entities/agent-runs.md) | finished automation reports; Reporting cards, Recent runs, retention and phase 4 limits |
| Health rubric | [docs/health-check-rubric.md](docs/health-check-rubric.md) | what the check judges and why: levels, questions, flags, word bank, disputes (the report's code contract: Others, ResumeLintReport) |
| Money and rates (`services/money.py`, `fx_rates.py`) | [`docs/entities/money.md`](docs/entities/money.md) | the home currency, the `money` setting, conversion rules, `formatPay`, the machine-local ECB rates cache |
| Others | [`docs/entities/others.md`](docs/entities/others.md) | BaseResume, the settings endpoints (model settings and recommended models, form-filling engines, persona draft, setup status), the `market` setting (`home` + `apply_in`) and work permits per country, Today (`GET /api/today`), the uv install (`maestro`) and the secondary entities that need rules but not a file each |

## 5. The application workflow, end to end (web)

The app opens on **Today** (`/today`; `/` redirects there): one read, `GET /api/today`, names the one move that matters most
(an offer, the best ready PDF, a proposal's question) with counts that link into the steps below; frontend-conventions, "Today".
A brand-new install (no key, no resume) opens **Setup** (`/setup`) once: four steps that write through the existing settings,
import and profile endpoints and store no progress of their own; frontend-conventions, "Setup".

1. **Capture** — `/new` (**Add job**): paste a job description → **Save job** → `POST /api/jobs` (LLM extract, dedup) → the
   job's page on step 2 (`?tab=fit`; the toast says "This job is already saved." on dedup). Or Companion/MCP `store_extracted_jd` → `POST
   /api/jobs/ingest` (pre-extracted; the client agent is the extractor by design). Both save paths score a new job against every
   selectable base after its commit (`_persist_job` → `score_all_bases`, inline); a failure rolls back only the scores, and a
   dedup hit is not re-scored, unless an ingest with `update` corrects it: a change in what scoring reads deletes both phases'
   scores, then rescores the job (docs/entities/job.md, "Correcting a saved job").
2. **Jobs** — `/applications` (the URL, `?status=`/`?source=`/`?stage=` and `cs-tracker-*` keep their names): the tracker. Columns
   Role, Match, Status (dated when it began from the status log, Applied by its date), **Next step** and a slot for where the job
   is (only when it is not on this copy), under a header of title, count and search. Five chips (All active, the default; Ready to
   apply; Waiting to hear; Interviews; Closed) are presets of the status and stage filters; the grouped status `Select`, the stage
   and a Tracked/Yours/Agents `SourceToggle` sit behind **Filters**, and the sort menu keeps every order. Next step and the stage
   read the server's stage, one ladder per job (saved → scored → gaps → tailored → pdf_ready → applied | closed;
   `services/stage.py`, docs/entities/job.md), sent on both list shapes and the detail. "Saved" = job with no application;
   agent-captured jobs stay out unless the toggle is `Agents`, so the default reads Tracked, not All. Status groups: All/All
   active/Interviews/Closed/Saved, **Your applications** and **Agent inbox** (`proposed`/`queued`/`needs_you`/`skipped`).
   **Select** is the Agent inbox's Select mode; its bar changes status, queues or deletes one row at a time through the rows' own
   endpoints. Rows, options and the Agent inbox page (`/proposals`): frontend-conventions, "Jobs row" and "Tracker filter".
3. **The job page** — `/jobs/[id]`: identity header (monogram, "Company · Place · Mode · pay" with the posted amount under a
   converted figure and the currency a post did not state named, ONE status: the application's inline StatusChip, else
   the proposal's pill worded like History (`headerProposalPill`), naming its filer, + Queue/Skip; a score pill, **Resume match**
   (tailored) or **Best base resume**; a Needs-you question adds **Keep it**, PATCH `pending_review`, linking the job's application
   when the proposal has none; the job link; a ⋯ **More actions**: Queue in Agent inbox, Refresh details, Delete job). Under it
   four numbered steps (`components/job-steps.tsx`, `lib/job-steps.ts`): **Job**, **Resume and gaps**, **Tailored resume**,
   **Apply**, each a 4px bar and ONE number from the data, no sentences (skills; gaps closed; base → tailored score), read from
   the detail's top-level `stage` (`hooks/use-job-steps.ts`, shared with the gap page). The stage's step opens, set once on load
   (step 1 while a proposal waits on you); a shown step 2, 3 or 4 is the page's `LeadCard`, its one filled button the card's
   action. A step with something to show is a button (3: a draft or PDF; 4: an application), one with nothing plain text, never
   locked. `?tab=` keeps jd/fit/output/qa/submitted so deep links land. Under the steps three folds: **Job description**, **What
   was submitted** (the receipt) and **Details and history** (the job's dates, the application's details). Step 1 (**Job**): the
   proposal's card, titled with its filer (`proposed_by`, worded by `lib/agent-name.ts`), only when it carries something
   (`proposalHasContent`), over the Job description fold, open while step 1 shows (folding it is yours): the **knock-out
   pre-scan** (`services/knockout.scan_for`: stated JD requirements vs the profile, flagged; the decision stays yours (or
   your agent's); verdicts and chips: docs/entities/job.md, "Knock-out pre-scan"), the job details and tracking link.
   `?from=proposals` flips Back + prev/next onto `cs-proposals-seq`, else `cs-tracker-seq`. Every job read derives
   `proposal_status`/`proposal_id` from the newest proposal.
4. **Score** — step 2 (**Resume and gaps**, `components/resume-step.tsx`) shows the bases set for the job's country (all when
   unknown), scored at save; its auto-run on first visit is the fallback for a job saved before any base resume existed or whose
   save-time scoring failed. The bases are toggle chips (top 3 by score, then "N more"); a pick is a preview, never a write. The
   default (`lib/resume-pick.ts`: the newest open session's base, else the application's, else the best match) gets a one-line
   summary with a Score breakdown popover, then **Analyze gaps** (creates a session), **Continue gap analysis** or, for
   the resume a finished analysis tailored, its counts and **View tailored resume**, the view's one filled button, and
   **Use resume as is**; Update scores, Restart gap analysis, Score them anyway, Mark applied without tailoring
   and Import resumes and documents sit in ⋯. One application per job: an action on another base asks first, worded for what the
   job holds (`hooks/use-resume-switch.ts`). Shared warnings show once above the chips; with no base resume the step offers the import.
5. **Gap analysis** — still step 2, on its own page `/jobs/[id]/tailor/[sessionId]` under the same stepper and resume chips (a chip
   opens that resume's gap analysis, `useResumeSwitch`; its Tailor asks first on the resume you applied with): per-gap resolutions
   (add_keyword / user_input / attach_project / skip + enable_entry / port_kb_point — see §4; plus cannot_confirm on claim-asking
   gaps: skip for the document + a durable `user_cannot_confirm` KB record written at SAVE time, so the claim is never re-asked —
   see §6 inv-provenance-no-decay) autosaved debounced with replace=true semantics (omitted gap_ids are deleted server-side);
   KB-auto-resolved gaps arrive pre-selected with provenance + Undo and a counting banner; optional per-session note
   (`user_prompt`, falls back into tailor()). **Use resume as is** (visible at 0 addressed) → from-base + closes the session;
   asks first as step 2 does (`confirmAsIs`). It, Tailor and Quick tailor need the job's detail (else Try again); no step or chip leaves mid-write.
6. **Tailor** — the gap page's **Tailor resume** → `POST /tailoring-sessions/{id}/tailor`: deterministic pre-ops → smart-model
   edit ops → keyword-survival and voice checks (§6 inv-resume-voice) → the job's one application (new, or the newest one taking
   the new base: "Switched to {resume}" in version history) + version row → draft-KBPoint write-back → session `tailored` →
   tailored score, one transaction (tailor() commits once at its end). The UI then lands in the studio's review mode
   (`?review=1`); step 3 shows the same changes. Internals: docs/entities/tailoring-session.md, "The tailor pipeline".
7. **Output** — step 3 (**Tailored resume**, `components/tailored-resume-step.tsx`): the lead card (the compact before/after
   compare and its Score breakdown; one filled button, **Create PDF** then **Continue to Apply**, with **Edit resume** → the
   studio `/applications/[id]/resume`, where Save chains render → re-score, and ⋯ with Tailor again and Delete application
   beside it). Below it the changes tailoring made (`GET …/resume-diff`, which carries the draft's `updated_at`), each with a Revert
   that PATCHes the draft with `expected_updated_at` (409, nothing written, if it moved) and re-scores it (wording checks
   stay in the studio).
   A draft write removes the PDF (Create PDF again): the PDF card shows only the draft's own, with Download / Open / **Show in
   Finder** (§6 inv-resumes-folder-one-way), **Update PDF** and the rasterized page preview.
8. **Apply** — step 4 (**Apply**, `components/apply-step.tsx`), the lead card: the job's resume (its page, band and square),
   its Match score and the gain over its base, **where this stands** (`lib/job-standing.ts`), **Open the job post** (apply link,
   else source link; the card's filled button, **Mark applied** when there is no link), **Mark applied** (outline) while a draft
   (the StatusChip's PATCH), and rows that open the **Cover letter** (tone; no
   PDF line: step 3 holds the PDF) and the application questions; their History (`QASections`) under it. The receipt is the
   page's **What was submitted** fold (docs/entities/filled-answers.md), and the application's details (applied date, tracking
   link, referral, notes, Delete application) its **Details and history** fold. Cold
   messages are free-form questions; the QA prompt injects the application's linked referral contact.
9. **Track** — StatusChip anywhere (Jobs row or job header): draft → applied → interviewing → offered → accepted / rejected /
   withdrawn. Every write goes through `set_status`, which logs the change with its source (you, the agent app by name, the
   Companion, mail: §6 inv-status-through-set-status); the Jobs row dates a status from that log, and Analytics' search summary
   and Today count from it. The Jobs row's Next step gives way to "Waiting to hear back" while Applied, then nothing. A base resume grown past
   your career history shows an "Add N things to career history" toolbar pill (N excludes already-recorded rewordings); its **Add
   now**, with no LLM, drafts only new bullets and keeps a rewording (cosine 0.80+, `services/kb_claims.place`) as a wording of the
   bullet it rewrites, near-matching entities instead of forking duplicates. An item's **Tidy bullets** combines near copies on a click
   (claims and wordings: `docs/entities/others.md`, Career KB).

## 6. Cross-cutting invariants (do not break these)

- **The browser is the attacker; six controls are the whole boundary.** `{#inv-browser-boundary}` The API has no authentication; the user's
  browser is inside the boundary and can be aimed at `127.0.0.1`. (1) **Host allowlist on BOTH servers:** `TrustedHostMiddleware` rejects any
  Host not in `settings.allowed_hosts` (without it DNS rebinding makes an attacker page same-origin); `frontend/proxy.ts` and the `/api` route
  repeat it from ONE definition, `lib/allowed-hosts.mjs`. (2) **Origin gate** (`app/origin_guard.py`): a present-but-unlisted `Origin` is
  refused before routing, an absent one allowed; raw ASGI, never `BaseHTTPMiddleware`. (3) **Extension origins are exact ids**
  (`settings.maestro_cs_extension_ids`), never a pattern. (4) **Template source is data, not code:** `pdf_render._environment()` is a
  `SandboxedEnvironment`. (5) **The compiler can neither execute, read siblings nor download:** `-no-shell-escape` unconditional, kpathsea
  paranoid mode, a fresh temp folder per run, Typst proxies pointed at a dead address. (6) **A template id is a slug, enforced in the
  REGISTRY** (`validate_template_id`). All six pinned in `tests/test_security_boundaries.py`,
  `test_frontend_host_guard.py`, `test_template_id_containment.py`. Why each exists, the middleware order and the related controls:
  `docs/entities/others.md`, "Browser boundary details".
- **An empty environment variable means UNSET.** `{#inv-empty-env-unset}` `config.scrub_empty_env()` deletes every empty or whitespace env var
  at import, before any SDK client is constructed (`config.SCRUBBED_ENV` records what went), because `docker-compose.yml` writes `VAR: ${VAR:-}`
  for optional settings — an EMPTY STRING, not an omission — and third-party SDKs read `os.environ` directly. App-level `or None` guards cannot
  help, so the rule is enforced once at the environment boundary: do not "simplify" it away, and do not add a `${VAR:-}` line believing the
  app will cope. Pinned by `tests/test_config.py` (the import-time case runs in a SUBPROCESS — reloading `app.config` in-process poisons later
  tests with `/app` paths). The symptom, the related key rule and the Langfuse rule: `docs/entities/others.md`, "Environment boundary details".
- **Staged artifact removal** `{#inv-staged-artifact-removal}`: NEVER delete rendered files in a transaction that can roll back. Every
  `customized_json` write uses `services/application_writes.stage_resume_update` (sets draft, clears refs, records version, returns stale
  paths); callers commit, THEN call `artifacts.remove_files(stale)` to remove files/PDF previews and prune empty folders (what warns and what
  stays quiet: `docs/entities/others.md`, "Artifact removal details"). Chat edits and version restores follow this pattern; never
  reintroduce an immediate unlink helper.
- **Stable per-application `artifact_dir`** `{#inv-stable-artifact-dir}`: one folder per application,
  `applications/Company_Role_YYYYMMDD_<idprefix>/`, allocated once via `services/application_artifacts.get_dir`, persisted on
  `Application.artifact_dir`; resume/source/PDF, previews, cover letters and proposal `evidence/` colocate there. Upload constraints:
  `docs/entities/others.md`, "PDF upload staging".
- **Status changes go through `set_status`.** `{#inv-status-through-set-status}` `application_status.set_status` alone writes
  `Application.status`, adding one dated `application_status_events` row per change (docs/entities/application.md). Pinned by
  `tests/test_status_events.py`.
- **Resumes folder copies go one way.** `{#inv-resumes-folder-one-way}` After the commit, each finished PDF is copied into the resumes folder
  (Documents by default), never read back or deleted there; a copy failure never fails the caller; `resumes_folder.*` is machine-local, off
  without `RESUMES_FOLDER_DEFAULT` and on the always-on copy. Pinned by `tests/test_resumes_folder.py`.
- **Honesty invariant** `{#inv-honesty}`: an `add_keyword` on a skill the engine found NO evidence of (`fix_hint == "absent"`) may only land in
  the skills section, never as a fabricated experience/project bullet. Enforced server-side in `save_resolutions` (guards MCP/API callers, not
  just the UI; `_is_missing_skill`). Pinned by `tests/test_tailoring_sessions_router.py`.
- **Placement validation twins** `{#inv-placement-validation-twins}`: `_validate_placement_target` (tailoring_session, raises) and
  `placement_targets.coerce` (scrubs LLM output) both call the pure `placement_targets.canonicalize` — `services/placement_targets.py` owns the
  placement-target contract, and the frontend's `buildPlacementTargets` hand-mirrors its targets shape. What an extra target requires:
  `docs/entities/others.md`,
  "Placement target details".
- **MCP control invariants** `{#inv-mcp-controls}`: no tool name contains "delete"; no set-default-template tool; MCP writes five settings
  through four routes, never `eeo`, and the form answers, job preferences and market (money rides on it) go through agent PATCH routes
  that read, merge and write in one transaction (`text_settings.one_commit`), never a client read-then-PUT; an id is one path segment,
  `client._seg` (`mcp_server/tests/test_server.py`, `test_profile_write_tools.py`, `test_client_path_ids.py`, `tests/test_settings_agent_patch.py`).
- **MCP lives inside the app.** `{#inv-mcp-inside-the-app}` `/mcp` and `/mcp/{profile}` are routed inside FastAPI behind REST's
  SyncPublicHost → Host → Origin → CORS stack; SDK DNS-rebinding protection is OFF so that stack stays the one definition; never a second port
  or `/api/sync` route. Pins: `tests/test_mcp_http_boundary.py`, `mcp_server/tests/test_http.py`.
- **MCP tools run off the event loop.** `{#inv-tools-off-loop}` Every registered MCP tool runs on a worker thread through `mcp_server.http`'s
  own limiter; module functions stay sync (`tests/test_mcp_http_loopback.py`, `mcp_server/tests/test_http.py`).
- **`edit_application` edits the current draft in place.** `{#inv-edit-in-place}` (MCP): its ops apply to the CURRENT `customized_json`,
  keeping every earlier edit (the base only with no draft yet); no MCP tool rebuilds a draft from the base outside a tailoring session
  (REST `from-base` stays for the web). Edit indices are **0-based into the full JSON array**, including `enabled: false` rows omitted
  from PDF; PATCH `/edits` echoes `applied[]`. Pinned by `mcp_server/tests/test_server.py`, `test_profiles.py` and
  `tests/test_resume_edit_service.py`.
- **An agent request never reaches Maestro's model while the agent app writes.** `{#inv-agent-writer}` A request with
  `X-Maestro-CS-Origin: mcp` (every MCP call) is an agent request; `mcp_workflow.writer` (default `"agent"`, set only in Settings ›
  Agent apps) says who writes for it. `app/agent_writer.py` marks and decides; each writing route refuses with a 409 naming the agent's
  own tool, `llm.call_openai`'s first statement is the backstop (`AgentWritesError`), and the health check hands the judging to the
  agent; MCP's resume import never calls a model. The header rule, the refusals and where the mark does not reach:
  `docs/agent-surfaces.md`, "Who writes". Pins: `tests/test_agent_writer.py` and the routes' refusal tests (`.system_md_enforcement.json`).
- **Autofill telemetry and run traces carry no VALUES.** `{#inv-autofill-telemetry-no-values}` `POST /api/autofill/telemetry` stores label,
  kind, rule id, option texts, outcome, host — never what was typed, was there before, or any AI answer: no value column, `extra="forbid"`, sw
  re-filters to six keys. `POST /runs` stores one strict, value-free `RunTrace` (newest 50 kept), any label or section holding a value the
  run saw blanked. `sw.js` `scrubTrace` whitelists against the schema; nothing posts unless `telemetryEnabled` is `true` (default off; Options
  › Keep a fill log), which `DELETE /telemetry` never clears. The **known-gaps table** (`autofill_widget_gap`) and the **gesture report**
  behind the recipe book (`content/recipes.js`) are value-free too. What each record holds, the blanking, what `DELETE` clears and
  `scripts/fill_trace.py`: `docs/entities/others.md`, "Autofill telemetry details".
- **Filled-answer values stay in the receipt table.** `{#inv-filled-answers-local}` What the Companion or an agent filled into an application
  form (`POST /api/jobs/{id}/filled-answers`, MCP `record_filled_answers`) lives only in the local `filled_answers` table
  (`services/filled_answers.py`; `docs/entities/filled-answers.md`): one row per page run, linked to the job's application (by base on a legacy
  multi-application job). It
  never enters telemetry, run traces, Langfuse or exports. An EEO value is stored only under recorded EEO consent (the fill's own gate,
  `eeo_consent.withhold_unconsented`, asked at write; the read is gated again as a second guard); withdrawing consent clears stored EEO answers;
  no agent read returns an EEO value, marked or not (the server classifies by question words too, the MCP client strips again, and no MCP path
  reads the web UI's `GET /api/jobs/{id}/filled-answers`). How the Companion panel posts it (never through telemetry, only from frames that
  earn the data): that file. Pins (invariant, panel receipt, API, agent and MCP client tests): `.system_md_enforcement.json`.
- **A frame must EARN the user's data.** `{#inv-frame-earns-data}` `sw.js` authorizes a broadcast at the sender, but `broadcastToFrames`
  targets every frame — a job page carries ad/analytics/chat iframes, and the ISOLATED world protects the message in transit, NOT the DOM
  written into: a frame owns its DOM, so a profile value in a third-party frame's input is readable by that frame's script. `agent.js` gates
  every fan-out write on `frameMayReceiveUserData(msg)`: the TOP frame passes; a SUBFRAME must show `detectPage().form`, OR sit on exactly
  the http(s) `flowOrigin` the panel vouches for (a confirmed form in this tab, same employer, within the hour). Detection throwing refuses;
  a refused frame returns the handler's EMPTY shape, never a throw. Attach also requires a VISIBLE input (`input.files` is readable with no
  gesture). The gated ops and the vouching rule: `docs/entities/others.md`, "Frame gate details". Pinned by `tests/test_extension_frame_gate.py`.
- **The policy deny-list is single-source, and it is TWO lists.** `{#inv-policy-deny-list-single-source}` `extension/shared/policy.js` (in
  `shared/`, since the panel consults it too) declares each exactly once: `NEVER_FILLED` (signatures/initials, passwords, government IDs) and
  `CONSENT_FORMS` (the application's OWN certify/acknowledge/attest/terms/arbitration/waiver boxes). WITHOUT the standing `consent_forms`
  permission (inv-eeo-standing-consent) both lists and the salary rule refuse; WITH it `isPolicyBlocked(label, {consentForms: true})` refuses
  NO label (the user's application, recorded revocable consent). Submit stays the user's at every setting; Next is clicked only by
  `page_advance` in a run the user started with Apply, full automation On (§7). The flag DEFAULTS to false and only a literal `true` counts;
  only `fillFormFromProfile` and the fill loop's inventory pass it. FOUR consumers across THREE surfaces, each ahead of the step it guards;
  which they are, the salary rule and what each guards: `docs/entities/others.md`, "Policy deny-list details".
  `test_both_copies_of_the_policy_deny_list_stay_identical` asserts exactly one declaration of EACH list; only the commit ladder stays a
  deliberate, pinned-identical twin (`…commit_ladder_stay_identical`).
- **One label-pattern table, two readers** `{#inv-one-label-pattern-table}` (`extension/shared/profile-fields.js`). The eleven patterns
  naming a TYPED home in the autofill profile (`eligibility.*`, `work_auth.*`, `preferences.*`) are read by `content/autofill.js`'s rule
  table, which FILLS those fields, and by the panel's `saveTargetFor`, which decides where a pause-row answer is LEARNED. They must be one
  table: an answer learned into `profile.custom` for a field the rules fill from `preferences.notice_period` lands where the rules do not
  look, so the same question pauses on every later application with nothing failing. **The learn store is the autofill profile, never
  `qa_entries`** — that table is application-scoped and no reader feeds it back into a fill, so "pause once, learn forever" is only true of
  `profile.custom` (matched by the deterministic rule pass on every later form) and the typed keys. Wiring faults are loud rather than silent
  (the two load-time throws: `docs/entities/others.md`, "Label-pattern table details").
- **Em-dash rule** `{#inv-em-dash}`: model- or agent-written answers, cover letters and `kb_add_points` drafts lose U+2014/U+2013 at store
  time (`qa.scrub_typographic_dashes`); a rendered PDF holds none (ATS parsers), and MCP `get_rendered_pdf` is the resume-PDF backstop
  (`docs/entities/others.md`, "Em-dash backstop").
- **EEO standing consent is enforced at the ENDPOINT.** `{#inv-eeo-standing-consent}` One record (`settings/eeo_consent.json`,
  `schemas/eeo_consent.py`; `eeo_consent` on `/api/autofill/context`), TWO permissions kept apart on purpose: `enabled` authorizes disclosing
  protected characteristics; `consent_forms` lifts the label policy (inv-policy-deny-list-single-source), only if agreed under policy ≥ 2 (an
  older yes is served off, `consent_forms_lapsed`); one flag for both would make an EEO yes agree to terms. ONE gate, `eeo_consent.withhold_unconsented`,
  strips `profile.eeo` unless `enabled` for every outward reader —
  `GET /api/autofill/context`, the `/choose` prompt AND the Jev engine's slot catalog — and fails CLOSED
  when consent cannot be computed; the MCP client keeps its OWN strip (two gates, not a relocated one). Which path asks never decides whether
  protected-class data is served. Pins (router, `/choose`, Jev): `.system_md_enforcement.json`. No inference or invented EEO answers. Human-only
  at ANY setting is Submit and nothing wider (Next belongs to the run, per inv-policy-deny-list-single-source); `consent_forms` lifts every
  label refusal for the callers that pass it, and only it, as served, adds `derived.agrees_to_terms`. The stamp, which callers, the chat rule
  and the provider list: `docs/entities/others.md`, "EEO consent details".
- **Provider data** `{#inv-provider-tagged-meta}`: opaque blocks (`ProviderMeta`: Claude thinking signatures, Gemini thought signatures)
  carry their provider and reach only that provider; `replay.for_provider` strips them for any other, so a model switch mid-chat never leaks
  one vendor's blocks to another. Pinned by `tests/test_replay.py`.
- **PDF word-spacing** `{#inv-pdf-word-spacing}`: pdflatex+XCharter joins words for strict extractors; `pdfinterwordspaceon` + the
  parse_certified gate protect this — see the shared header partial `_header.tex.j2`, which BOTH resume and cover-letter templates include
  (format/scanner changes must handle both). pdfTeX 1.40.27 misplaces that space for many Type 1 fonts → overprinted words that still
  extract cleanly; `template_validation.text_overprints` refuses such a LaTeX sample and `engines` warns on that build. The fonts, the boot
  re-check and the host-TeX rule: `docs/entities/others.md`, "PDF word-spacing details". Pinned by `tests/test_pdf_render.py` and
  `tests/test_template_overprint.py`.
- **A render never changes engine silently** `{#inv-render-fallback-explained}`: `services/engines` is the ONE probe; `MAESTRO_CS_PDFLATEX`
  overrides and fails CLOSED. Without `pdflatex`, `pdf_render.resolve_render_template` uses the first ready Typst template for LaTeX
  resumes, bases and cover letters; `render_note` names both. VALIDATION never substitutes. `base_resume_render.record_render_error`:
  committed writes persist `render_error`; render-only requests return 400, never 500. Startup validates seed templates before rendering
  bases, and a seed-render failure leaves the base usable (`docs/entities/others.md`, "Render fallback details"). Call sites:
  `tests/test_render_note_coverage.py`. Pins: `tests/test_render_fallback.py`, `tests/test_seeding.py`.
- **`user_cannot_confirm` is durable.** `{#inv-provenance-no-decay}` No code path upgrades that provenance to anything else — including the
  gap flow that writes it: a "cannot confirm" gap outcome stores a retired `user_cannot_confirm` point and future sessions pre-resolve the
  claim instead of re-asking (where it lands and how it matches: `docs/entities/others.md`, "KB provenance details"). Base-sync of the same claim
  drafts a NEW `user_authored` point and leaves the record untouched — new first-party
  evidence beats an old "don't know"; the draft queue is where the user reconciles. Pinned by `tests/test_kb_provenance_stamping.py`
  (`test_no_writer_flips_user_cannot_confirm`) and `tests/test_gap_cannot_confirm.py` (`test_nothing_upgrades_user_cannot_confirm`).
- **Column types come from ONE module.** `{#inv-single-dialect}` SQLite is the only runtime database. `app/models/types.py` (`JSONDoc`,
  `UUIDType`, `UTCDateTime`) is the only place a column type is chosen, and nothing under `app/` imports `sqlalchemy.dialects`.
  `UTCDateTime` is the whole timezone story: aware in Python, naive UTC on disk, and a NAIVE bind raises; the APP writes every timestamp
  (`default=utcnow`, `onupdate=utcnow`) so one format lands on disk. Pinned by `tests/test_db_portability.py`.
- **Job-site passwords stay in their local file.** `{#inv-job-site-password-local}` `settings/secrets/job-site-login.json` is 0600 (directory
  0700). Never DB, exports, telemetry or logs.
  Settings GET/PUT return only `{email, password_set}`; validation errors are sanitized. TWO routes hand it out, both needing full automation
  On, a Queued/approved proposal and a company off the skip list, each recording `ConsentEvent(action="login_shared")`, never the value. POST
  `/api/proposals/{id}/job-site-login` requires NO `Origin` (MCP origin; channel `mcp`, note = client name) and the login passes through the
  agent's AI provider. POST `/api/companion/job-site-login` (`{proposal_id}`; channel `companion`) is admitted only for the Companion
  extension's origin, which types it once (top frame, known ATS host) to sign in or create an account, and the password never reaches a
  model, run record, card, receipt, trace, telemetry or error (the file, frame, host, park and box rules: `docs/entities/others.md`,
  "Job-site login file details"). Pins:
  `tests/test_job_site_login*.py`, `test_companion_job_site_login.py`, `mcp_server/tests/test_client_job_site_login.py` (symbols in
  `.system_md_enforcement.json`).
- **Automatic consent is gated by the user's switch.** `{#inv-auto-consent-gated}` Off by default; only PUT `/api/settings/full-automation`
  writes it (StrictBool); PUT `/api/settings/auto-apply` preserves it. Channel `auto` approves only `accepted` (Queued),
  requires `final_review` evidence, re-checks the company blocklist, and keeps the daily-cap/already-applied gates; an auto-attested submit,
  including from `submission_uncertain`, needs a note with at least one letter or digit; both auto paths require full automation On; a
  company blocked after approval still has its submit recorded. Eligibility is the agent's `apply-auto` prompt, not a server-side review
  judgment. Only the Companion's exact extension origin may name channel `companion` (the user's Apply, a relink of an `accepted`
  proposal); the user's real Submit is recorded only by `POST /api/proposals/{id}/companion-submitted`, which clicks nothing (the queue
  and relink rules and the submit record: `docs/entities/others.md`, "Proposal relink from the Companion" and "The Companion's run"). A skipped
  (rejected) proposal blocks queuing its job again, except an
  "applied manually" one, which blocks only while an application of the job is still applied. Pins: `tests/test_full_automation_setting.py`,
  `test_proposal_state_machine.py`, `test_companion_submitted.py`, `test_proposals_router.py` (symbols in `.system_md_enforcement.json`).
- **One writer per job; the laptop owns the profile.** `{#inv-one-writer-ownership}` With sync on (a key file exists) every job has one owner
  machine (`jobs.owner_machine`, NULL = this one) and the other copy holds a read-only replica; the laptop owns the whole profile, which the
  always-on copy replaces on every round and never merges. A queue, skip, status or note change on the other copy's job is a `sync_requests`
  row ("Sent at the next sync") the OWNER applies under the normal rules (state machine, forward-only statuses, daily cap); anything else on
  it is refused. Only a handover moves ownership, `offered` (laptop to bot) or `returning` (bot to laptop); what starts, cancels or refuses
  each, the columns and the offers route: `docs/entities/job.md`, "Ownership under sync". The same JD text on
  both copies keeps the laptop's job (`duplicates.py`). Without a key every job is owned here and every `/api/sync/*` route is a 404. Pinned
  by `tests/sync/test_guard.py` and `tests/sync/test_home_endpoints.py`.
- **The flush guard is the ownership check, and it runs before disk.** `{#inv-flush-guard}` One SQLAlchemy `before_flush` hook
  (`services/sync/hooks.py`) guards EVERY write path (web, MCP, Companion, the Assistant's in-process writes): it raises `NotOwnedHere` (a
  409) for a replica, an offered job (laptop), a returning job (bot), a row it cannot tie to a job, and any profile row on the always-on
  copy, except scoped seeds and "cannot confirm" additions (sent home as `profile_addition` requests). A route that writes files or calls a
  model calls `require_owned`/`require_profile_writable` BEFORE the disk or the model, so a refusal deletes nothing; reads that write skip
  replicas (`owned_here`); a Core writer touches its job or the profile itself (`touch_job`/`touch_profile`); the sync's own writes pass
  inside `hooks.standing_aside(db)`; no key allows every write; transaction end and rollback clear the hook's state (the repair and
  session-state rules: `docs/entities/others.md`, "Flush guard details"). Pinned by `tests/sync/test_guard.py`.
- **Every sync message is sealed; the key never travels.** `{#inv-sync-channel}` Peer routes and `/api/sync/enroll` are AES-256-GCM, with
  HKDF-SHA256 keys derived from the sync key or the one-time pairing code; a header MAC is checked before any body. An unsealed request, a
  failed seal, or an `Origin` on a sealed route is a bare 404, byte-identical to sync being off (a 403 would show that sync is on); with no
  key file every `/api/sync/*` route is that 404 and the always-on copy serves no home routes. Only `/api/sync` may be published (Tailscale
  Funnel); while `SYNC_PUBLIC_HOST` is set every response on it is sealed or the bare 404, whatever Host says, and the public name stays
  refused off that tree. The profile, the AI key and the job-site login ride only this channel, and no key, pairing code, seal plaintext,
  bundle value or local path reaches a log or an error (fixed sentences). The routes, the post-seal checks, replay refusal, path and proxy
  rules, folder containment and the pairing code's life: `docs/entities/others.md`, "Sync channel details". Pinned by
  `tests/sync/test_seal.py`, `test_sealed_home.py`, `test_public_host.py`, `test_pairing.py` and `test_two_machines.py`.
- **One data folder per user; nothing writes into the install.** `{#inv-one-home}` A uv install's `MAESTRO_HOME` defaults to the
  platform's per-user application-data folder (the three paths: `docs/entities/others.md`, "Home folder paths"), the folder the future
  desktop app uses, so its data needs no import. `home.backend_env`
  points every writable path (data, applications, settings, logs, uploads, model cache) into it, so nothing lands under site-packages; its
  `maestro.env` is the only settings file. Pinned by `tests/maestro_cs/test_home.py`.
- **The install's environment is applied before `app` is imported.** `{#inv-env-before-app}` `app.config.settings` reads the environment at
  import, and its `env_file=".env"` would read a Docker checkout's file from the caller's folder. One-shot verbs (`check`, `migrate`,
  `connect`) call `home.apply_env()` first, which also `chdir`s into the home; servers get it as child env with cwd = home; `maestro mcp`
  imports no `app` module. Pinned by `tests/maestro_cs/test_maintenance.py` and `test_bridge.py`.
- **Base resume colour is identity, never state.** `{#inv-resume-color-identity}` One hue per base resume, drawn as a square beside its
  name, never as status; the recipe lives once in `globals.css` and the presets are mirrored across backend, frontend and extension. Pinned by
  `tests/test_frontend_resume_colors.py` and `test_resume_color_parity.py`.
- **Resume text is the owner's own, in implied first person.** `{#inv-resume-voice}` Every rewrite prompt carries the VOICE rule (built in
  code, so a customised row keeps it); `services/resume_voice.py` finds the shapes about the owner. Model and caller text NEVER stores a
  blocking third-person hit (one retry, then repair, then drop); the owner's base lines get only mechanical repairs and are never dropped.
  Ambiguous shapes are flagged, never rewritten. Agent and Assistant writes with a hit get a 400 (`docs/entities/others.md`,
  "Voice check details"). Pins: `tests/test_resume_voice.py`, `test_tailoring_voice.py`, `test_agent_write_voice.py`.
- **A Next the page rejects is not a move, and only a page the run filled is pressed.** `{#inv-rejected-next}` A press that leaves address
  and step heading while the page shows errors keeps `step` and `seen`; the driver reads `page_errors` (the page's own words, never a value),
  repairs ONLY the fields they name in at most `MAX_FIX_ROUNDS`, then presses again; what it cannot repair parks `page_errors` naming only
  what is left. Next is pressed only on the page last filled (`filledPage`); a press or repair that ends on another page counts as a step and
  that page is filled first. A posting's Apply is pressed as a same-tab link only to the queued link or a known ATS host, and the first read
  after it must land there too, else `moved_away` before any fill. The repair calls, the step keys and the host checks:
  `docs/entities/others.md`, "Queued-run invariant mechanics". Pinned by `tests/test_extension_queue_run.py`, `tests/browser/test_page_reader.py`.
- **The resume is written once per page, to a lone resume box, before Next.** `{#inv-one-resume-write}` Only a page's one required upload
  box whose own words name no other document counts as the resume's (or a lone box under a resume heading, or the box a page error named);
  never over a file already there, and never a second write after an `unconfirmed` one. **A parser box is never written** (the site's own
  import or fill-from-resume), nor one for another document, by any press. A required box still empty after the fill, a required parser or
  other-document box, or a choice among several, parks `upload` before `page_advance`. How the box and the proof are found:
  `docs/entities/others.md`, "Queued-run invariant mechanics". Pinned by `tests/test_extension_queue_run.py` and `tests/browser/test_upload_box.py`.
- **A worked-here No is never wrong.** `{#inv-worked-here-no}` The history answers No to "Have you worked at X?" only when it lists jobs and
  no employer is among the companies the question names (the whole history, any wording); a match is Yes; anything that could be an employer
  under another name is ASKED instead (`autofill_catalog.named_employer_fact`, read by /pick, /step and /map). Only an ALLOWLIST of question
  shapes about the applicant's own employment is rerouted to it (`asks_worked_here`, backed by an exclusion list); OTHER companies are
  rerouted too (`asks_worked_here_of_other`) and reported `assumed` (`derived.previously_employed_here#other`, `ASSUMED_SLOTS`). The shapes,
  the exclusion list and the name rules: `docs/entities/others.md`, "Worked here". Pinned by `tests/test_autofill_{catalog,map}.py`.
- **Veteran status is one Yes/No.** `{#inv-veteran-yes-no}` A No settles every "not a (protected) veteran" option and "currently or ever
  served" (reported `assumed`: `veteran_inferred`); a Yes, and any other saved Yes/No fact, never picks or answers a protected class, and a
  Yes never claims CURRENT service (`veteran_overreach`); a No picks the one "I am not a (protected) veteran" option in code
  (`veteran_option`). Legacy `veteran` reads as yes; legacy `not_veteran` reads as UNANSWERED (`stale_answers`). The readers and the
  option rules: `docs/entities/others.md`, "Veteran". Pinned by `tests/test_autofill_pick.py`.
- **Ready means a real review page with nothing missing.** `{#inv-ready-real-review}` The run reports Ready to submit only when the page is a
  review whose `by` is `submit_button` (a real Submit control inside the application and no real Next), shows no errors and has no required
  box empty (`requiredEmpty`). Any other reason a page reads as a review parks `unsure_page` only after the same read held for 4 reads; a
  field-less page with only a bare Continue or Proceed parks `confirm_page`; a plain Next is pressed. The user's word feeds Ready (`readyBy`
  "user", errors and empties still checked) only for the three unsure reasons, and is void once the read shows a Next. Closed means closed.
  The unsure reasons, the fix order and the resume-box excuse: `docs/entities/others.md`, "Queued-run invariant mechanics". Pinned by
  `tests/test_extension_queue_run.py`, `test_extension_page_kind.py` and `tests/browser/test_page_reader.py`.
- **A work-permit answer is per country and never guessed.** `{#inv-work-permit-per-country}` `work_auth_by_country` holds each market's
  answers ("UK", not "GB"). A question gets the set of the one country it names, else its job's (`markets.for_country`), else none: unknown
  is `missing_source`, asked on that job, never a default. `autofill_country` is the rule; `profile_for_job` and the fill loop's `_Catalog`
  apply it (the Companion's rule pass sees the job's set only). Storage and limits: `docs/entities/others.md`, "Work permits per country".
  Pinned by `tests/test_autofill_country.py`.
- **Low stakes are decisive; a draft is read, not trusted.** `{#inv-drafted-answers}` A low-stakes gap is filled and reported `assumed` with
  a fixed note, never left blank and never invented as a fact: a date box asking for more than the fact has takes the 1st (January for a
  year), https goes on a host, a phone type is Mobile, a dialing-code picker takes the profile country's code; the owner's No/Yes safe
  defaults are in the §7 dial; a middle name is never made from the first name, and the name is used as stored. `/choose` DRAFTS only a
  REQUIRED text or textarea that `/map` filed as `free_text` or `years_unanswered`, never at **Careful**, never when the never-list matches,
  in the owner's voice; it returns `assumed` with "Drafted from your history: read it" and saves nothing. The never-list, the length and
  the grounding: `docs/entities/others.md`, "Derived facts, drafted answers and degree levels". Pinned by `tests/test_autofill_choose.py`,
  `test_autofill_map.py` and
  `tests/browser/test_fill_core_fields.py`.

## 7. Agent surfaces

Reference tier, like §4: how each surface works — the MCP transport, profiles, docstring ratchets, plugin and `.mcpb` bridge; the two
workflow envelopes; the Assistant's toolset; the Companion's panel, Guided fill, queued run, reasoning step and dials — lives in
[`docs/agent-surfaces.md`](docs/agent-surfaces.md) under this same contract, and `extension/INTERNALS.md` holds the Companion's mechanics.
Code citing "§7" lands here; the table says which section to open. What orientation needs of each surface:

- **MCP server** (`backend/mcp_server/`; on screen **connected agents**): thin wrappers over REST via httpx (`@_guard` → `ToolError`),
  served at `/mcp` and `/mcp/{profile}` inside FastAPI (§6 inv-mcp-inside-the-app, inv-tools-off-loop); **the docstring is the API** —
  behavior, records and requirements, never instructions. Tool sets in journey order (profile, hunt, tailor, apply, track, templates;
  `/mcp` = `full`, 94 tools), each with its own instructions and, over HTTP, playbook prompts; enable ONE per chat; a removed tool's name
  answers with what replaced it (`replaced.py`). **Who writes** for its
  requests is the user's choice, the agent app by default (Settings › Agent apps; §6 inv-agent-writer): Maestro's writing routes then
  refuse and name the agent's own tool, and `tailor_session(no_new_text=True)` tailors with no new wording and no model.
  `workflow.py` (the guided tailoring and onboarding workflows) is PURE — a **deliberate exception to the thin-wrapper rule** — and its
  `next` envelopes walk §5's arc unnarrated: the server ranks, the agent narrates; `offer` ≠ `ask_user`; **a hint never names a tool the
  active profile did not register**.
- **Automations page** (`/automations`): **Copy prompt** hands work to the user's agent; Maestro runs NO scheduler, and a card
  shows only what its runs reported through MCP `record_run` (`agent_runs`), never a schedule or a connection state.
- **In-app chat**, the **Assistant** (`services/chat_agent.py` + `chat_tools.py`): a distinct toolset (resume edit, KB capture, template
  admin including the mutations MCP deliberately lacks); its resume-edit tool runs the SAME pipeline as the REST endpoints
  (`services/resume_ops.py`).
- **Chrome extension**, the **Companion** (`extension/`): MV3 side panel; a four-stage rail (Job → Resume → Fill → Track) INFERRED from the
  store, never set by a click; **Guided fill** runs the fill loop with `/choose`; with full automation On a **queued run** drives one job's
  application through sign-in, fill and Next to **Ready to submit** — Submit is never clicked, at any setting (§6 inv-ready-real-review,
  inv-policy-deny-list-single-source) — with a **reasoning step** before it parks and the **Screening answers dial** (Careful / Balanced /
  Confident) deciding how far a saved fact reaches.
- **Streaming chat** runs through `llm_providers` on any provider; eligibility is the tools probe.

| Surface | Section in `docs/agent-surfaces.md` | Scope |
|---|---|---|
| MCP server | [MCP server](docs/agent-surfaces.md#mcp-server) | transport and loopback, docstring ratchets, scoped profiles, who writes (the refusals and their limits), plugin, Connect an agent app, the `.mcpb` bridge, what tools send and read (status sources, per-country answers, analytics rows) |
| Guided tailoring workflow | [Guided tailoring workflow](docs/agent-surfaces.md#guided-tailoring-workflow) | the `next` envelope, ranking vs narrating, `offer` vs `ask_user`, the two controls, the LLM-free arc, apply readiness |
| Onboarding workflow | [Onboarding workflow](docs/agent-surfaces.md#onboarding-workflow) | ingest → approve → base → render with zero in-house LLM; hint rules |
| Automations page | [Automations page](docs/agent-surfaces.md#automations-page) | copy-only prompts, `record_run`, status from reports |
| In-app chat | [In-app chat (the Assistant)](docs/agent-surfaces.md#in-app-chat-the-assistant) | toolset, pinned-resume hint, social posts, key and capability checks, prompt rows and their reset |
| Chrome extension | [Chrome extension (the Companion)](docs/agent-surfaces.md#chrome-extension-the-companion) | panel family, rail, footer primary, shared scripts, posting identity, options, packing |
| Guided fill | [Guided fill](docs/agent-surfaces.md#guided-fill) | fill modes, the runner, `/choose` batching, readback, receipts, answers decided in code, the two engines |
| Queued run | [Queued run, one job (Apply)](docs/agent-surfaces.md#queued-run-one-job-apply) | Apply, the three switches, what parks, Resume and remembered answers, tab following, the user's Submit |
| Pages of web components | [Pages of web components](docs/agent-surfaces.md#pages-of-web-components) | open shadow roots, unknown first pages, parser and CAPTCHA markers |
| Reasoning step | [Reasoning step](docs/agent-surfaces.md#reasoning-step) | when it runs, the value-free snapshot, 1–3 checked actions, rounds and budget |
| Screening answers dial | [Screening answers dial](docs/agent-surfaces.md#screening-answers-dial) | Careful / Balanced / Confident, the protected list, safe defaults |

## 8. Frontend conventions

Reference tier, like §4: consulted while working in `frontend/`, not read for orientation. Lives in
[`docs/frontend-conventions.md`](docs/frontend-conventions.md): layout and sidebar rules, Tailwind v4 tokens and
M3 colour roles, the studios' save and preview model, a11y and focus behaviour, naming, the copy rules and the one
glossary (the app calls its fixed-rules score **Match score**; *Canonical terms*; ratchets `test_frontend_vocabulary.py`,
`test_frontend_sentence_length.py`), each
with the failure mode that bought it. One bullet per page (sidebar, Today, Setup, Profile, Settings' four tabs and their
anchors, Jobs, Agent inbox, job steps, Analytics); the tiers (one `LeadCard`, the Also tier, `Fold`s, no subtitle) and
`NextStep` are under Visual encodings. Code citing "§8" lands here.

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
  CI cold-installs `.[mcp]`, checks seven stdio sets and `/mcp` + `/mcp/hunt` over HTTP. xdist (~15 → ~3.5 min)
  uses `loadfile` to keep browser tests per file. conftest makes a SQLite file per process/worker (`TEST_DATABASE_URL` may name another,
  never under `data/` or with `-n`) and blanks the four provider keys (`OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`):
  a worker's `load_dotenv()` finds the
  nearest `.env`, so unstubbed tests made billed calls. Parity tests (`tests/node_ts.py`) need node 24: skip locally, FAIL in `CI`.
- **Deploying a local change = rebuilding BOTH images** (MAINTAINER path, MAIN checkout): `docker build -t maestro-career-studio-backend
  backend/` AND `…-frontend frontend/`, then `docker compose up -d --no-build --force-recreate backend frontend`. A frontend-only change
  still needs the frontend image rebuilt — a stale image once made fixed UI look broken for a whole review.
- **A USER updates instead** — `./scripts/update.sh`: online SQLite snapshot
  (`app.tools.backup_db --stdout` through the running backend container, else the checkout's own image tag —
  `.env`'s `latest` can predate the tool; 0600, magic-byte checked) → ff-only to the newest `v*` tag → images pinned to that tag →
  health poll → extension/MCP reminders (only legacy stdio re-runs setup-mcp.sh; an old Docker `.mcpb` is reinstalled once; README "Updating").
  Checkout and images
  move TOGETHER: a bare `docker compose pull` skews an install. Contributors build. The pre-v0.4.0 guard (a `<project>_pgdata` volume with no
  `data/.migrated-from-postgres.json`) and recovery steps: docs/UPDATING.md.
- **Windows = WSL for Docker; the uv install runs natively.** Docker needs Desktop's WSL 2 engine with the clone in the WSL home, never
  `/mnt/c` (SQLite WAL over the Windows share is untrusted; the scripts are bash). `.gitattributes` forces LF
  so a clone cannot CRLF scripts or `.env`; `setup-mcp.sh` is not a Windows route. The `.mcpb` uses HTTP on macOS, Windows and Linux without Docker on
  the assistant's side.
  The upload host root is `${PWD}` (compose cwd; `update.sh` pins it to the repo) unless `MAESTRO_CS_UPLOAD_HOST_ROOT` overrides it; Windows joins with `\`.
- **uv install (B′, `maestro`)** — `uv tool install --python 3.12 maestro-career-studio`: a `py3-none-any` PyPI wheel of `backend/`
  (version = `backend/pyproject.toml`) plus the Next standalone bundle (`maestro_cs/web/`; `scripts/build_wheel.py`, gated by
  `check_wheel.py`, including root legal files in PEP 639 `dist-info/licenses/`) and Node from `nodejs-wheel-binaries`.
  `maestro start` detaches `maestro run`, a foreground supervisor owning
  uvicorn (127.0.0.1:8001) and `node server.js` (:3000); stop = `run/stop.request` + a signal; process identity = pid + psutil
  create_time. `maestro update` = verified snapshot → stop → `uv tool install --force …==NEW` (Windows: a detached `cmd` script) → start. The web
  process gets no API keys (`home._WEB_STRIPPED`). CI: `maestro-cli`, `uv-wheel`, `uv-smoke`, `uv-upgrade`; `pypi.yml` publishes on
  `v*` tags. `maestro import-docker` copies a Docker checkout's data in once (the checkout is read, never written). Detail: `docs/entities/others.md`,
  "The uv install".
- **Native run (no Docker)** — `docs/native-install.md`: `backend/scripts/native/` runs one loopback worker under `$MAESTRO_HOME`; URLs follow the MCP
  rule above, `MCPB_BUNDLE_PATH` uses the checkout's `mcpb/maestro-career-studio.mcpb` (`tests/test_native_scripts.py`).
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
  on: the size ceiling; a `(YYYY-MM-DD` date in §1–§10 or any reference-tier file; a shipped item left in §11; a section over its byte
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

**Design docs dated before 2026-09-17 are not published.** They live in the upstream private repository (they are agent handoff
scripts — publishing them would ship instructions for a machine no reader has), and this file is the public record of what they
decided. From 2026-09-17 the design and implementation plans are in `docs/plans/`, named by date. The lineage of the unpublished docs
is one paragraph; after it, one line per owner decision: what was decided, the alternative it superseded, and why.

Key lineage: 2026-04-22 greenfield → 2026-05-29 jobs/applications consolidation → 2026-07-06 deterministic ATS
gap workflow (fit_scores deprecated; dropped in migration `09265240aade`) → 2026-07-08 tailoring refinements →
2026-07-12/14 health gates → 2026-07-14 career KB (sidecar) → **2026-07-15 applications workflow simplification
+ UI changeover** (D1–D13; the audit findings C# and review fixes referenced throughout this file) → 2026-07-15
parallel delegation tasks (MCP apply-package tools; health-check-v2 override UI) → 2026-07-16 UI polish (Career
KB + extension Q&A) → **2026-07-16 custom resume sections (`extra_sections`) phases 1-2**
(fixed-core-plus-typed-extras, then versioned ATS evidence + stable-key gap placement) → MCP guided tailoring
(caller-authored ops, hint envelope) → MCP onboarding: reversed "approving from MCP is unrepresentable" — a
draft gate needs an approver wherever review happens, and agent transcription is NOT the verbatim-file
exception, so ingest lands drafts and consent-gated `kb_approve_points` is the one approval path from MCP.

- 2026-08-09 — LaTeX stays and both engines remain first-class (§13 `typst-default-flip`, HELD); superseded the Typst-default flip and
  the LaTeX retirement queued behind it because nothing waits on them and the parity corpus predates the extractor swap.
- 2026-09-17 — SQLite is the only database, one file per install; superseded Postgres (kept for one release, inside the exporter)
  because a single-user, local-first app needs no daemon, and a later installer then has nothing to run, sign or port-manage.
- 2026-09-25 — Form filling routes Jev first with one fast-model fallback and no smart-model tier; superseded a smart tier because the
  fast tier drives coverage, honesty and latency and Smart barely moves outcomes (§12).
- 2026-09-25 — Health check v3: a concrete result stated in words earns full credit and the evaluator asks each bullet its own question;
  superseded the number quota because a number is natural in some bullets and not others.
- 2026-10-02 — The fill trace is a dedicated local store the extension assembles, the last 50 runs, outcomes only; superseded Langfuse
  (opt-in, usually off, and it holds values), two halves joined by a run id (two writers, a join and partial-run cleanup) and logs only
  (no per-run record).
- 2026-10-03 — Option texts and the chosen index are kept on every traced field, EEO included; superseded blanking them because a wrong
  pick must be readable back; a typed search keeps only its count because its rows echo what was typed.
- 2026-10-04 — Automations are prompts the user copies to their own agent, served from the skill files; superseded a Maestro scheduler
  (timing is the user's and their agent's), prompt text in the frontend (it would exist twice and drift) and MCP prompts alone (support
  differs by app and there is no copy button).
- 2026-10-05 — Under full automation the agent's prompt decides eligibility and its word, labelled channel `auto`, is proof of submission;
  superseded a server-side eligibility gate and the Companion submitting because the server still enforces the cap, the blocklist and
  already-applied on every approval.
- 2026-10-05 — Inbox readiness is computed when the list is read; superseded a second readiness request (two loading states, rows
  redraw) and readiness stored on the proposal (stale after profile edits, hooks in tailoring code).
- 2026-10-05 — Base resume identity is typed anchors (`base_anchors`); superseded the free-text "Target note" fed to five prompt readers
  because the owner cut it to a scope that scoring and the best-base pick can read.
- 2026-10-06 — Sync is split ownership: one writer per job, the laptop owns the profile, nothing merges; superseded CRDT sync (7 unique
  constraints, 23 cascading foreign keys and the state machine cannot survive last-writer-wins), cloud-hub engines, SQLite's session
  extension, one database on the always-on machine (the laptop would lose Maestro when it is down) and a job lease (runs dry while the
  laptop is off).
- 2026-10-06 — Pairing has no attempt limit; superseded a lockout because 80 bits make online guessing hopeless and a limit would only
  let outsiders burn the owner's code.
- 2026-10-06 — On small machines ATS scoring embeds in a short-lived helper process; superseded in-process embedding because the
  always-on machine has 640 MB and no swap, so the model's memory must be freed after each call.
- 2026-10-09 — The desktop shell is Electron, macOS Apple Silicon first, and a `uv tool` install (B′, the `maestro` command) ships
  first; superseded building the shell straight away because the first public desktop release waits for a Developer ID, and other
  shells because Electron has the most mature in-app updater and needs no frontend refactor.
- 2026-10-10 — LLM providers are official SDKs owned in `llm_providers/`, Claude native; superseded LiteLLM, Pydantic AI and LangChain
  runtime dependencies, and Anthropic's OpenAI-compatible endpoint, because provider quirks must live in one place.
- 2026-10-10 — The Companion's queued run clicks Next and stops on the review page, for Queued jobs only; superseded the 2026-09-26 rule
  "Next and Submit stay the user's" for the Next half alone, because the queue is the consent step; Submit stays the user's at every
  setting.
- 2026-10-11 — Answers typed into a parked run are always remembered, with Undo; superseded a save checkbox because an answer asked once
  must never park again.
- 2026-10-11 — The fill engine works in hidden and covered tabs; superseded taking turns in the foreground because a background tab ran
  fills 6.5× slower and failed every dropdown.
- 2026-10-11 — Each finished PDF is copied into a visible resumes folder; superseded leaving them only under the app's `applications/`
  because the owner's newly tailored resumes looked missing.
- 2026-10-14 — Low stakes are decisive: a format or precision gap (a day, a scheme, a dialing code) is filled and flagged, never parked,
  and facts are still never invented; superseded parking on every such gap because the filled field is listed under Check before you
  submit.
- 2026-10-14 — Safe defaults when the profile has no fact (No for a status that only adds something, Yes for willingness to a standard
  pre-employment step), from Balanced up; superseded parking on every unknown yes/no because the owner's rule is N/A or No for most and
  Yes for a readiness check, each listed under Check before you submit.
- 2026-10-14 — On a known ATS host the run creates the account with the saved login, once; superseded "account creation always parks"
  from the 2026-10-10 design because the saved login is already typed on those hosts; every other host keeps the wall.
- 2026-10-14 — Veteran status is one Yes/No question; superseded the `veteran` / `not_veteran` values because "not a protected veteran"
  is true of a veteran who is not protected.
- 2026-10-14 — A reasoning model runs only where the run would otherwise stop; superseded parking at once because a few cents a round
  buys an answer only where one is needed.
- 2026-10-15 — On a one-page form the reasoning step works fields only and never presses; superseded treating a step-0 review page as a
  review that parks because Submit sits on the same page.
- 2026-10-15 — A generic "How did you hear" answer takes LinkedIn or a specific board the list offers, assumed, and the saved sponsorship
  No holds even when a question counts OPT as sponsorship; superseded asking, and an extra OPT guard, because both are listed under Check
  before you submit.
- 2026-10-20 — The design refresh (`docs/plans/2026-10-20-design-refresh.md`, D1–D11): each page leads with one card, then a few
  secondary things, then folds, with no subtitle; superseded pages of equal-weight cards because the owner found the app "a lot going on".
- 2026-10-20 — Jobs drops its Resume and Where columns for one Next-step style and the Agent inbox's Select (D2–D4); superseded the
  Resume column because a resume is picked after a job is saved.
- 2026-10-20 — A rate shows only from 20 in its denominator, with a Wilson 95% range (D7); superseded a percentage on any count
  because 1 of 3 read as 33%.
- 2026-10-20 — Pay reads in one home currency on ECB reference rates, "≈" with the posted amount kept (D8); superseded figures in
  each posted currency and a USD default because pay across countries could not be compared.
- 2026-10-20 — Where you live plus where you apply, and work-permit answers per country (D9); superseded one `market` and one
  `work_auth` set because a form in one country was answered with another's facts.
- 2026-10-20 — Automations show only what runs reported (D5); superseded connection dots and per-app buttons because Maestro
  schedules nothing.
- 2026-10-20 — Profile holds facts about you, Settings how the app behaves in four tabs, and a four-step Setup runs first (D10,
  D11); superseded tabs by area because a new user needs one short path and each of the 156 items still needs a home.
- 2026-10-26 — Who writes over MCP is one setting for every feature, the agent app by default (§6 inv-agent-writer), and
  `quick_tailor` and `tailor_application` left MCP; superseded agent requests using Maestro's key whenever one was set, because a user
  must know before connecting who writes and who pays.
- 2026-10-26 — Near-duplicate MCP tools merge (99 → 92): `explore_trends(view)` for six chart tools, `get_career_context(format)`,
  `attach_evidence(image_base64 | file_path)`, approve-only `kb_approve_points`, and a removed name answers with its replacement;
  superseded one tool per view, format and input because each near-duplicate was a guess for the agent and the merge loses no
  capability. `list_jobs`/`export_jobs` and the pairs whose filters or payloads differ stay apart.
- 2026-10-26 — MCP's coverage holes close with parameters plus `save_referral` and `kb_merge_entities` (92 → 94), and agent profile
  saves merge on the server in one transaction; superseded the client's read-then-PUT, which lost a Companion answer saved in between,
  and a web-only KB merge, out of an MCP-only user's reach for an import's split duplicate.

## 11. Known deferred items (priority order)

**Item numbers are stable, not positional.** Code and migrations cite "§11 item N" from a dozen places,
so new items APPEND here and shipped items are deleted in place — renumbering silently invalidates every
citation. Priority lives in the item text, not in the ordinal.
**Every item carries a trigger** — "do when X", the observable condition that makes it worth building now;
an item 30 days without one is given one or deleted. This file keeps the items read every session (target ≤7);
overflow moves to `docs/deferred.md` under this same contract, each item keeping its number.

1. Extra-section op **payloads** stay loosely typed (op *kinds* are one source, `schemas/resume_edit.py`):
   `add_extra_section` / `replace_extra_section` `value` is `dict[str, Any]`, validated in the service
   (`resume_edit._validate_extra_section`, like `AddEntry`), so a bad extras payload is a 400, not a 422. Do when `schemas/resume_edit.py` or
   `resume_edit._validate_extra_section` is next changed.
2. One post-render readiness pipeline ("Ready to apply" gate: health, em-dash, pages, contact checks on the exact
   rendered artifact), consuming the shared rasterized preview + slim MCP `get_rendered_pdf` metadata. The JD-level
   half (stated requirements vs profile) is the knock-out pre-scan, §5 step 3. Do when one of its checks (health, em-dash, pages, contact) is next
   changed or a third surface reads them.
13. Quick-tailor: derive `applied` from the committed resume DIFF, not planned intent; employment-blocks v2. Do when `applied` disagrees with the
    committed resume diff, or employment blocks are next changed.
20. `extra_sections` remainder: calibrate the `extra_only` multiplier; nested extra-section entry/bullet ops are
    unbuilt (a bullet op would make the health check's custom-section suggestions appliable, not copy-only). Do when the `extra_only` multiplier is
    calibrated or a custom-section suggestion has to be appliable.
25. SQLite has one write lock, and two transactions hold it across LLM calls: `kb_consolidation.consolidate` (flush, one LLM call per
    entity, one commit — `seeding.seed_career_kb` relies on that via `commit=False`) and `tailoring_session.create_session` with enrichment
    (score flush + supersede UPDATE, then the call). A concurrent writer waits `busy_timeout` (30 s), then fails "database is locked". Fix:
    compute every LLM result first, then write in one short transaction, keeping the seeder's `commit=False` contract. Do when "database is locked"
    appears under a consolidation or an enriched session.
35. Settings seed race: `text_settings.get_text` lazily INSERTs a missing `Setting` row and commits, so two first
    reads at once both insert and one fails on the key; the commit also ends an open transaction (hence `POST
    /api/proposals` reads `get_settings` before `begin_write`). Seed at startup or insert-or-ignore. Do when two first reads race on a
    `Setting` row, or a startup seeder is added.
44. Companion run limits left on purpose: a robot-trap option inside a real checkbox/radio group (shared name) is not filtered
    (honeypots are standalone text boxes); sync's duplicate resolution that keeps the laptop's twin drops the other copy's
    `apply_url`, and a replica's link is never sent to its owner; a password-only second sign-in screen parks (`no_email`); technique
    cards for group, select and date widgets are never reached (the adaptive step runs for popup and search only); a page with no
    heading never reads as a rejected Next, `heldValues` misses a select's shown text and a custom combobox, and the hand-attached-file
    check reads the run's own frame only; the run list, Queue view and parallel tabs wait for Phase 3 (`docs/plans/2026-10-10-companion-queued-run.md`);
    the rest of the 2026-10-14 live-check limits: `extension/INTERNALS.md`, "Known limits". Do when Phase 3 (run list, Queue view, parallel tabs) is
    built or a listed limit is reproduced.

The other 47 items (3–6, 8, 10, 12, 14–17, 19, 21, 22, 24, 26–30, 32, 33, 37–43, 45–60, 62, 63) live in [`docs/deferred.md`](docs/deferred.md),
each keeping its number and carrying its trigger; code citing "§11 item N" for one of them lands there. The design refresh's
not-fixed observations are 53–60 and 62 there: one diversity set for every country, no per-country work-permit breakdown, Today never
expiring proposals, mail events dated when learned, no version check on profile saves, the chart palette, a picture from before
the refresh, the slop ratchet's stale pair, readers still on a job's country text.

## 12. Gotchas that have bitten before

**Ledger — evict when the cause becomes enforced.** A gotcha whose cause now has a test, type, lint or pinned
invariant has done its job: promote it (into Cross-cutting invariants or `.system_md_enforcement.json`) and delete
the entry here. Entries are dated symptom → cause → rule, ≤3 lines.

- **A faked compiler hid behind the probe cache** (2026-10-24): patching `pdf_render.subprocess.run` patches the shared module, so the
  resolver's `pdflatex --version` probe hit the fake (500 `{"detail":""}` run alone) unless an earlier real render had cached the banner
  (`engines._VERSION_CACHE`) → a test that fakes the compiler pins `engines.probe_pdflatex` too (`_stub_render_compilers`, `_with_tex`).
- **Tests leaked state through `/app/settings`** (2026-10-21): the settings file mirrors default to that container-absolute folder, so a
  test that saved a setting unisolated left `market.json`, `eeo_consent.json` or a `secrets/sync-key` behind (order-dependent
  `test_eeo_consent` / `test_market_settings` failures; a stray sync key failed 17 sync tests) → isolate every mirror, check the folder.
- **Parallel agents in one checkout swept each other's work** (2026-10-21): `git commit -- <path>` takes a file's whole working copy, so
  another agent's hunks in CHANGELOG.md, `lib/types.ts` or frontend-conventions.md rode in the wrong commit → one worktree per writer,
  or serialize the shared files.
- **A node-tested `lib/*.ts` file cannot import another's values** (2026-10-21): `node --test` needs the `.ts` specifier and `tsc`
  refuses it (TS5097) → a node-loaded lib file imports types only; a shared helper goes in its own file (`lib/setup-answers.ts`).
- **A copied stack rendered into its source** (2026-10-16): rows keep absolute paths (applications `pdf_path`/`tex_path`/`artifact_dir`,
  base_resumes, kb_documents), so a draft write and render on a copied state dir replaced the source stack's PDF → rewrite those
  paths to the copy before any render or draft write.
- **An Unreleased changelog bullet outlived its feature** (2026-10-16): ef3cfe15 removed the Job step's "Show N more" toggle, the bullet
  stayed, and the release audit and store plan repeated it → a commit that reverses an Unreleased feature edits its CHANGELOG bullet too.
- **A hidden tab stalled saves** (2026-10-13): TanStack v5 scoped mutations queue as paused and continue only while the tab
  is focused → serialize saves with a per-key promise chain (`lib/in-order.ts`), never a mutation scope.
- **An update served the old version's pages** (2026-10-12, 0.10.0): Next writes `.next/server/route-cache` inside the
  installed bundle at run time; uv replaces only shipped files, so 0.9.0's cached HTML (dead script and CSS links) outlived
  the update → `maestro run` clears it before the web starts (`runtime.clear_web_cache`).
- **Playwright makes every tab visible** (2026-10-11 spike): launch or `connect_over_cdp`, `document.hidden` stays false, so
  background-tab behaviour can't be measured attached → run Chromium unattached over the DevTools HTTP endpoints
  (`scripts/spike_background_fill.py`); macOS also hides every tab of a covered window.
- **Owned-session prompt reads never seed** (2026-10-10): a lazy INSERT waited out `busy_timeout` behind a caller's
  write and hid a mocked outage → only caller-supplied sessions seed; startup seeds the rest (`tests/test_prompts_service.py`).
- **Retry keys must identify controls** (2026-09-25): rule attempts use composite labels, collection clean questions, so
  `country | field-12` never reaches the `country` retry → use element identity; a model upgrade cannot repair fields collection never sends (§11 item 40).
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
  query string, so every job was the first one saved. A query-keyed board needs its key in BOTH `posting_id` tables (§7); an SPA's `<head>` JSON-LD is
  the PREVIOUS job's.
- **A starter that fails its own gate** (2026-09-01): the from-scratch template certified `false` on an untouched
  draft. What the app mints AND validates in one request must clear every probe.
- **Extension-only `accept` lists grey out real files** (2026-09-01): six hand-typed pickers had no MIME types → every picker reads
  `frontend/lib/upload-accept.ts`.
- **A guard test mocked away the guard** (2026-08-25): a green suite hid a 100%-failing rewrite path because it replaced
  `guarded_rewrite` → when a guard or validator is the subject, fake `llm.call_openai`, never the guard.
- **The FAST model quietly caps score honesty** (2026-08-24): flash-lite extractions missed conceptual JD skills →
  base ATS scores inflated ~9 pts vs fuller extractors. Fast tier drives coverage/honesty/latency; Smart barely moves
  outcomes — re-benchmark FAST before changing model defaults.
- **`autoflush=False` sessions**: two `session.merge`s that canonicalize to the same PK in one flush both INSERT (no
  dedup) → IntegrityError. Dedupe in Python first (see `_insert_skills`).
- **Pydantic error mapping order**: `ValidationError` subclasses `ValueError` — catch it FIRST or 422s become 400s.
- **Transient response attrs**: `already_existed` and `correction` (Job), `health_warning` (TailoringSession) are instance attrs set
  after refresh; `base_anchors` (TailoringSession) is a model property. None is a column — don't "fix" them into the ORM.
- **score_target(result=...)**: passes a precomputed engine result to persist, replacing a double run (audit finding C18); don't re-add a second.
- **The query cache keeps old key order** (2026-09-22): structural sharing made a refetch's `JSON.stringify` differ from
  the PATCH response, so a studio's own Save read as foreign → compare `serverKey` (sorted keys); §11 item 26.
- **PDFium is not thread-safe** (2026-09-23): parallel gallery previews segfaulted libpdfium → every PDFium use under
  `app/` and `mcp_server/` holds `services/pdfium_lock.PDFIUM_LOCK` (AST scan in `tests/test_pdfium_lock.py`).
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
  Information, so every step but the résumé upload scored 1 and Fill was withheld → measure `detectPage`'s signals on the live page first (fix:
  `workday-apply-route`).
- **Tailwind v4 compiles some classes to nothing** (2026-10-06): a variant on a plain class (`data-confirm:animate-confirm`
  until it was an `@utility`) and an unknown role (`border-outline`; check `--color-*` in `globals.css`); `translate-*`/`scale-*`
  set those properties, so `transition-[…transform]` jumps → register a class that takes a variant; name those properties.
- **Agent sandboxes kill what a tool call starts** (2026-10-10): a server vanished between calls, even with `setsid` → run
  start, checks and stop in ONE call (`scripts/smoke_uv_install.py`), or use `maestro autostart`.
- **Child-server startup signals have separate meanings** (2026-10-10): reverse DNS can stall listening, while “Started” precedes child output →
  fixtures bypass DNS, report bound ports, and wait for asserted output before stopping.
- **Updating main under an open Chrome tab breaks the page reader** (2026-10-15): re-injection runs old load-once files with new re-run ones → a
  re-run file never
  reads a newer load-once export (`tests/test_extension_manifest.py` scan); reload open job tabs after an update (a run parks `page_stale`).
- **A page of web components read as "nothing to fill"** (2026-10-15): `querySelectorAll`, `closest` and `contains` stop at a shadow root while the
  fill inventory walks in → every page read goes through `ns.deep` (`tests/browser/test_shadow_dom.py` pins fillable count > 0 exactly when the
  inventory lists a field).
- **A slow fast model lost the safe answers** (2026-10-15): limits tuned on a 1.5 s model timed out a Claude one three times a day → floors by
  provider (`FAST_PROVIDER_FLOORS`), the timeout given is logged and `top_fact` names the fact that fell under its floor.

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
| `autofill-work-auth-shape` | `work_auth.authorized_to_work` + `requires_sponsorship` (two timeless booleans, stored "yes"/"no") → typed `WorkAuth` (`schemas/autofill_profile.py`: `status`, `authorized_now`, `sponsorship_now`, `sponsorship_future`, `authorization_expires_on`, `countries_authorized`) | both-live | Delete when no raw-profile reader uses either legacy key. Today's storage readers are FOUR: `services/autofill_profile.py`'s legacy branch, Profile's legacy-on-edit bridge (`lib/autofill-options.ts` `typedEntry`, per country), the fill engine's dual-read (`content/autofill.js`, the `w` binding in the profile normalizer; moved from agent.js at the phase-2 split), and the panel's `workAuthForWrite` (`panel/actions/pause.js`), which promotes the legacy pair before the first typed pause-row write. All four sit under `.slopledger.json`'s trigger paths, which are directories (`extension/content`, `extension/panel`, `frontend/lib`), so a reader that moves stays covered; a new reader elsewhere needs its directory added. `job_search_brief`'s identically named response fields (the home `work_auth` and every `work_auth_by_country` entry) are one frozen outward yes/no projection from typed `authorized_now` / `sponsorship_future` (`_brief_work_auth`), not a legacy reader, and do not block removal. ALSO `GET /api/settings/autofill` must return no `work_auth` or `work_auth_by_country` entry carrying either legacy key. Then delete the legacy branch of BOTH `autofill_profile.typed_work_auth` and the extension's `w` binding. Per `autofill-education-shape`: cut the frontend first, the extension one release later. | small |
| `autofill-work-auth-by-country` | one top-level `work_auth` (the one market's answers) → `work_auth_by_country` keyed by market (`services/autofill_country`, inv-work-permit-per-country) | new-is-default | A stored `work_auth` reads as the home market's entry (mapped when read, folded into the map on the next save, pinned to that home before a move: `autofill_profile.pin_legacy_work_auth`), and a read still serves `work_auth` as the home set, named by `work_auth_market` (a save folds it into the market it names, never the home it finds), for clients that still write one set: Companion builds from before the pause row learned into `work_auth_by_country[<the market /context names>]` (`panel/actions/pause.js`); Profile and Setup write the map and send no `work_auth` (`lib/autofill-options.ts` `forSaving`). No current client writes `work_auth`: cut the projection and the one-set fold (`autofill_profile._with_work_auth_by_country`, the `work_auth` branch of `_as_stored`) once the release after this one has shipped; keep the legacy read until no stored profile holds a top-level `work_auth`. `content/autofill.js` reading the resolved `profile.work_auth` from /context is the design, not a legacy reader. | small |
| `brief-work-auth-home` | the brief's home set, `profile.work_auth` + `work_auth_market` → `profile.work_auth_by_country` | new-is-default | No shipped playbook reads it (`.slopledger.json`). Once the release after this one has shipped, delete both fields from `BriefProfile`, the home projection in `job_search_brief._work_permits` and the docstring's sentence. | small |
| `job-location-raw` | `jobs.location` (dual-written) → `location_raw` + city/state/country | both-live | Stage 1 (schema shim + `.location` property) already met. Stage 2: no reader of `jobs.location` remains, then `op.drop_column`. | small |
| `health-rewrite-cache` | unattended rewrite always-LLM → `bullet_rewrites` (NULL text = tried-ask) + ephemeral ask answers → `health_ask_answers` | new-is-default | Migration `85a1bb628e28` (pre-SQLite chain, removed in v0.5.0; the tables are in the SQLite baseline). The LLM miss path is the intended fallback, not a second product — cut this row when a follow-up deletes either table or the GET `/api/resume-lint/{kind}/{key}/answers` rehydrate. | small |
| `chat-message-parts` | `chat_messages.tool_calls` / `tool_call_id` columns → neutral versioned `parts` (+ `provider`, `model`; migration `cf0804d00ae2` backfills) | new-is-default | The release after this one ships: drop both columns, `transcript.from_legacy` and the `ChatMessageRead` legacy fields in one migration. Readers: `transcript.from_legacy` fallback, `ChatMessageRead`. | small |
| `native-scripts-to-maestro` | `backend/scripts/native/*.sh` (always-on bot) → the `maestro` command | both-live | The always-on bot runs on `maestro` for one release, then delete `backend/scripts/native/`, `docs/native-install.md` and `tests/test_native_scripts.py`. | medium |
| `lock-wheel-deps` | `requirements.lock` as the image's whole runtime set (names the old `maestro-career-studio-backend`, no `psutil`) → regenerated lock that omits `nodejs-wheel-binaries` (`pip-compile --unsafe-package`); the image adds the project with `--no-deps -e .` | both-live | Lock regenerated in `python:3.12-slim`: it has `psutil==`, `nodejs-wheel-binaries` not pinned, no `maestro-career-studio-backend`. | small |
| `market-home-apply-in` | one `market` setting → `home` (where you live: home currency, date format) + `apply_in` (every market you apply in), `schemas/market_settings.py` | new-is-default | A stored `{"market": X}` reads as home = X, apply_in = [X] (mapped when read, never migrated), and `market` (= `home`, a computed field) is still written so a sync peer that has not updated reads the same country. No reader of the setting's `.market` remains: `git grep -nE '\.market\b' backend/app` and `git grep -nE 'value\??\.market\b' frontend` are empty (the frontend's other `.market` is a permit question's own market key). Cut the `market` field when the release after this one has shipped; keep the legacy read until no stored `market` blob lacks `home`. | small |

**Row notes** (only where the trigger hides a trap):

- `typst-*`: strictly ordered flip → delete-latex → drop-texlive (the font is vendored, so the old
  drop-the-layer-changes-the-font trap is closed).
- `chat-selection-kind`: inverted today — the branch four comments call "legacy" is the only form the
  frontend emits (`scope-picker.tsx` sets `kind` on kb chips only), so `kind:"resume"` is unreachable and
  those comments mislead until stage 1 ships.
- `autofill-work-auth-shape`: three traps. (0) The reader count is FOUR, across three surfaces; the trigger
  paths are directories so a renamed file stays covered — see the row. (1) `sponsorship_now` has NO legacy source and stays `None` on purpose —
  defaulting it from `requires_sponsorship` answers the OPT case wrong (no sponsorship NOW, needed later);
  unknown must stay unknown. (2) `job_search_brief`'s public legacy-named response fields, per-country entries
  included, are a frozen projection of the typed reader, not a storage-migration blocker.
- `job-location-raw`: `JobSummary` exposes ONLY the old field (no `location_raw`), so the list endpoint is
  the hardest blocker to dropping the column.

**Not migrations — do not re-file these here** (each was proposed as a row and rejected): the 4-way
application-status vocabulary and the 3-way `quick_tailor_profile` shape are hand-synced by design; the
`/api/explore` prefix and the `explore_` names of the MCP analytics tools (`explore_trends`, `explore_gap_frequency`) are a
deliberately frozen public surface after the UI rename;
the typed-op vocabulary lives in `schemas/resume_edit.py` (item 1 tracks only the extras-payload
residual) and is not a migration. Cross-boundary duplication (a Python enum and its TypeScript mirror)
is never a ledger row — it needs a contract test, not a deletion. The two seniority lists are NOT a
subset relation and must not be merged — see §4 AtsScore, "Rank markers are domain data"; merging them
would be a scoring bug.
