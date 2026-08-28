# Maestro CS MCP Server

A thin [MCP](https://modelcontextprotocol.io) wrapper around the Maestro CS
FastAPI backend, so Claude Desktop — or another stdio MCP client, such as the
ChatGPT desktop app / Codex CLI — can drive the app directly. Claude is the
brain — it extracts job descriptions, compares them to your resumes, and does
the profile-coaching analysis. The app stays the system of record: it stores the
structured data, renders the LaTeX PDFs, and serves everything back. The tools
below are just typed entry points into the existing backend HTTP API.

## Prerequisites

- The **Maestro CS backend running and reachable from the host**. Start it the
  usual way — `docker compose up -d --build` from the repo root, or, from
  `backend/`: `uvicorn app.main:app --port 8000`.

  **Set `BACKEND_URL` to the host port your setup actually publishes.** The
  backend container listens on `8000` internally, but docker-compose maps it to a
  host port — in this repo's typical setup that's **`8001`** (`8001:8000`), so
  `BACKEND_URL=http://localhost:8001`. If you run the backend directly with
  `uvicorn ... --port 8000`, use `http://localhost:8000`. Check the published port
  with `docker compose ps` (or your Docker dashboard) and don't confuse it with an
  unrelated app on `8000`.

- A **host** Python **3.12+** with the backend installed (this is what Claude
  Desktop, the ChatGPT desktop app, or Codex CLI launches as a subprocess — it
  runs on your machine, not in Docker, so the container's Python doesn't
  count). A fresh macOS ships 3.9: get a current one with
  `brew install python@3.12` (Debian/Ubuntu: `sudo apt install python3.12
  python3.12-venv`). `scripts/setup-mcp.sh` checks this and tells you the same
  thing if it finds only an old Python. The MCP server was tested with `mcp`
  1.26.

## Install as a plugin (Claude Code, Codex)

The shortest route, and the only one with nothing machine-specific in it. Add
this repo as a plugin marketplace and install `maestro-career-studio`:

```bash
claude plugin marketplace add https://github.com/seinun-ai/maestro-career-studio
claude plugin install maestro-career-studio@maestro-career-studio
```

Codex takes the same two steps as `codex plugin marketplace add
seinun-ai/maestro-career-studio` and `codex plugin add
maestro-career-studio@maestro-career-studio`.

The shipped declaration is one file
([`plugins/maestro-career-studio/.mcp.json`](../../plugins/maestro-career-studio/.mcp.json))
read by both ecosystems, and it runs the server **inside the backend
container**:

```
docker exec -i -e BACKEND_URL=http://localhost:8000 \
  -e MAESTRO_CS_MCP_PROFILE=full \
  maestro-career-studio-backend-1 python -m mcp_server.server
```

Three consequences worth knowing:

- **No host Python.** The prerequisites below apply to the venv route only.
- **`BACKEND_URL` is a constant.** Inside the container the app is always on
  `localhost:8000`, so the host-port confusion described below cannot happen.
- **The container name is a literal**, fixed by `name: maestro-career-studio`
  in `docker-compose.yml`, because Codex plugin manifests support no `${VAR}`
  interpolation. See RELEASING.md's third standing constraint before changing
  it. If you set `COMPOSE_PROJECT_NAME`, your container is named differently
  and the plugin will not find it — use the setup script instead.

The plugin ships `full` only. Scoped profiles need a per-server toggle, which
plugin-provided servers do not have, so they come from the setup script or a
hand-written client entry.

## Install (host virtualenv)

Use the setup script from the repo root — it resolves the venv path, the
backend port and the absolute binary path, registers the server with Claude
Code, and prints paste-ready config for the GUI clients:

```bash
./scripts/setup-mcp.sh
```

To do it by hand instead, from the `backend/` directory:

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[mcp]"
```

That pulls in `mcp` and `httpx`. The server is then runnable two ways:

- `python -m mcp_server.server`
- the console script `maestro-career-studio-mcp` (declared in `pyproject.toml`)

Both read the `BACKEND_URL` env var (default `http://localhost:8000`; set it to
`http://localhost:8001` when the backend is published on host port 8001 — see
Prerequisites).

> **`mcp` is pinned below 2.0** in `pyproject.toml`. The 2.0 release moved
> `mcp.server.fastmcp` (`FastMCP`, `Context`, `ToolError` now live under
> `mcp.server.mcpserver`), so an unbounded requirement resolves to 2.x and
> `mcp_server.server` fails on its very first import. Do not lift the ceiling
> without doing the 2.x migration in the same change.

## Scoped profiles (`MAESTRO_CS_MCP_PROFILE`)

By default the server registers **all** tools (`full`). For workflow-specific
sessions (especially apply + Playwright) in Claude, the ChatGPT desktop app, or
Codex CLI, set `MAESTRO_CS_MCP_PROFILE` so unused domains never appear in the
tool list:

| Profile | Use when | Approx tools |
| --- | --- | --- |
| `full` | Mixed / default | all (83) |
| `hunt` | Job search + propose (no browser fill) | 19 |
| `apply` | Tailor → PDF → autofill → evidence/consent/submit | 46 |
| `explore` | Analytics (`explore_*`) | ~11 |
| `templates` | Template draft/validate/render | ~12 |
| `career` | Career KB read/write (`kb_*`, career context/export) | 18 |

Same binary; each client's entries differ only by `env`. Example apply entry
alongside Playwright — **share one folder tree** so staged PDFs are already
inside Playwright’s output dir (no agent-side copy, no per-apply folder grant):

```json
"maestro-career-studio-apply": {
  "command": "<MAESTRO_CS_MCP>",
  "env": {
    "BACKEND_URL": "http://localhost:8001",
    "MAESTRO_CS_MCP_PROFILE": "apply",
    "MAESTRO_CS_UPLOAD_DIR": "<REPO>/.playwright-mcp/uploads"
  }
},
"playwright": {
  "command": "<NODE>",
  "args": [
    "<HOME>/.maestro-cs/mcp/node_modules/@playwright/mcp/cli.js",
    "--browser=chrome",
    "--user-data-dir=<HOME>/.maestro-cs/apply-profile",
    "--output-dir=<REPO>/.playwright-mcp"
  ],
  "env": {
    "HOME": "<HOME>",
    "npm_config_cache": "<HOME>/.npm"
  }
}
```

`<MAESTRO_CS_MCP>` is the absolute path to the `maestro-career-studio-mcp` console
script, `<REPO>` your clone, `<HOME>` your home directory, `<NODE>` your node
binary — same placeholders as
[`claude_desktop_config.example.json`](./claude_desktop_config.example.json).

`prepare_application_pdf_upload` writes under `MAESTRO_CS_UPLOAD_DIR` (default
repo `.playwright-mcp/uploads`). Playwright’s `--output-dir` must be the parent
`.playwright-mcp` tree so the returned `upload_path` is already allowed for the
file chooser. Enable **only** `maestro-career-studio-apply` + `playwright` for apply
chats (not `full` at the same time). Restart Claude Desktop (Cmd+Q) after
changing config so tools and env reload. If Claude asks once for
`.playwright-mcp`, approve that folder; do not grant `applications/` for upload
staging.

## The tools

**Read**

| Tool | Description |
| --- | --- |
| `list_base_resumes` | List all base resumes (slug + display name). |
| `get_base_resume(slug)` | Fetch one base resume's full structured data. |
| `list_jobs(limit?, offset?, without_application?)` | List stored jobs as a **thin summary array, paginated** (limit + offset; no `raw_text`/`extracted_json` — use `get_job` for detail). Optionally only those without an application. |
| `get_job(job_id)` | Fetch one job's extracted fields. |
| `get_application(application_id)` | Fetch one application's full detail — its job and the full `customized_json` (plus any legacy LLM fit scores kept for history). The detail counterpart to the slim `list_applications`. For the before/after ATS view, use `compare_ats`. |
| `get_career_export()` | Return the exact generated `career.md` body. Use `get_career_context()` when structured resume and memory fields are preferable. This is a portable Markdown view, not a tailoring input. |
| `get_career_context()` | Read the full composed Career KB view — the approved-points resume plus the beyond-the-resume `memory` text — for grounding outreach or social writing. |
| `list_referrals` | List referral contacts (company, careers URL, contact name, notes, applications count). |
| `list_qa_entries(application_id)` | List the generated screening answers and cover letters for an application, newest first. |
| `get_job_search_brief()` | Read the server-composed job-search brief (profile constraints, persona, base-resume summaries, role mix, top skills, referral pages) — call first in an agentic search session. |
| `get_autofill_profile(application_id?, base?)` | Read the user's stored application-form autofill data (contact, work-authorization, preferences, consented EEO) — the same feed the Chrome extension's deterministic fill uses. |
| `find_job_by_url(source_url)` | Check whether a posting is already captured, by URL, before spending an extraction on it. |

**JD ingest**

| Tool | Description |
| --- | --- |
| `store_extracted_jd(extracted_json, raw_text?, source_url?)` | Store a JD that Claude extracted. `extracted_json` must match the `JobExtraction` schema (company, title, role_category, level, employment_type, work_mode, city/state/country, location_raw, salary_min/max, salary_period, work_authorization, opt_accepted, years_experience_min/max, `skills[{skill_name, skill_category, requirement_level}]`, responsibilities[], qualifications[]). |

**Health check**

| Tool | Description |
| --- | --- |
| `run_health_check(kind, key)` | Run the JD-independent resume health check on a base resume or application — classifies every bullet on the evidence ladder and returns a score, grade, gates, and ranked findings. Run this before `create_tailoring_session`. |
| `get_health_report(kind, key)` | Fetch the most recently stored health report without re-running it. |
| `waive_health_gate(kind, key, gate_id, reason)` | Bypass a failing fatal health gate — call only when the user has explicitly said to waive it. |
| `unwaive_health_gate(kind, key, gate_id)` | Remove a health-gate waiver and restore the gate's protection. |

**Career KB**

| Tool | Description |
| --- | --- |
| `kb_list_entities(kind?, status?)` | List Career KB entities with their IDs — start here before editing anything, since `get_career_context` returns prose with no IDs. |
| `kb_get_entity(entity_id)` | Full detail for one Career KB entity: dates, notes, points, attached documents, activity timeline. |
| `kb_list_points(state?)` | List Career KB points across all entities, optionally filtered by state (draft/approved/retired). |
| `kb_capture(text, entity_id?)` | Capture free-text career news into DRAFT points for the user to approve at `/career`. |
| `kb_edit_point(point_id, text?, tags?)` | Reword or retag a Career KB point; changing the text sends it back to DRAFT. |
| `kb_create_entity(kind, title, org?, start_date?, end_date?, status?, notes?, detail?)` | Create a Career KB entity (experience/project/education/certification/extra). Writes immediately, not draft-gated. |
| `kb_edit_entity(entity_id, title?, org?, start_date?, end_date?, status?, notes?, detail?)` | Fix an entity's dates, title, org, notes, or lifecycle status. Writes immediately, not draft-gated. |
| `kb_edit_profile(contact?, summary?, skills?, notes?)` | Update the Career KB profile (contact, summary, skills, notes). Writes immediately; each supplied field replaces its stored value wholesale. |
| `kb_ingest_resume(resume_key, data, brief?)` | Persist one caller-parsed resume into the Career KB as DRAFT points, merging by identity key across resumes. No in-house LLM. |
| `kb_approve_points(point_ids, state?)` | Batch-approve or retire Career KB points — the gate that puts a point on composed resumes. Call only after the user has approved. |
| `kb_sync_base(slug)` | Deterministic sync of one base resume into the Career KB. Draft-only; never edits resumes; safe to rerun. |
| `create_base_resume_from_kb(entity_ids, role_category?, role_label?, display_name?, include_summary?, summary?)` | Compose a new base resume from selected, approved Career KB entities. LLM-free. |

**Base resume writes**

| Tool | Description |
| --- | --- |
| `edit_base_resume(slug, ops)` | Apply typed edit `ops` to a base resume (read-then-edit; the server keeps every untouched field). Call `get_base_resume` first to pick indices/categories, then send only the changes. Op kinds: `replace_summary`, `toggle_entry`, `replace_bullet`, `replace_skills_group`. Re-renders the PDF. Use `update_base_resume` only for a full wholesale replace. |
| `update_base_resume(slug, data, display_name?)` | Replace a base resume. `data` is **required** — it's a full `ResumeData` replacement, not a patch. |
| `create_base_resume(slug, display_name, data)` | Create a new base resume from full `ResumeData`. |
| `duplicate_base_resume(slug, new_slug, new_display_name?)` | Copy an existing base resume to a new slug. |
| `archive_base_resume(slug)` | Hide a base resume from pickers without deleting it — a reversible `archived_at` timestamp; JSON, PDF, TEX and version history all stay. |
| `unarchive_base_resume(slug)` | Restore an archived base resume to `list_base_resumes`' default view; nothing else changes. |

**Resume versions**

| Tool | Description |
| --- | --- |
| `list_resume_versions(kind, key)` | List the append-only resume snapshots for one target, newest last. `kind` is `"base"` (key = slug) or `"application"` (key = application id) — note this is not `render_pdf`'s `target_type` vocabulary. |
| `get_resume_version(kind, key, number)` | Fetch one version including its snapshot and the diff vs its parent. |
| `restore_resume_version(kind, key, number)` | Copy a past version's snapshot into the live resume — the restore is itself a new version; history is append-only and nothing is deleted. |

**Tailor + render**

| Tool | Description |
| --- | --- |
| `tailor_application(job_id, base_resume, ops)` | Create an application by applying typed edit `ops` to a base resume server-side. Read the base with `get_base_resume`, then send only the changed fields as `ops` (same op kinds as `edit_base_resume`). The server inherits every untouched field from the stored base and validates the result. No backend LLM call. |
| `edit_application(application_id, ops)` | Apply typed edit `ops` on top of an application's *current* tailored resume, preserving every prior edit — the right tool for an incremental fix after a PDF preview. Contrast with `tailor_application`, which rebuilds from the base and discards existing tailored edits. |
| `update_application(application_id, status?, applied_at?, notes?, referral_id?)` | Update an application's tracking fields (status, applied_at, notes, referral_id). Only the arguments passed are sent — omitting one leaves it untouched, so this cannot clear a field to null. |
| `render_pdf(target_type, target_id)` | Render a PDF. `target_type` is `"base_resume"` (`target_id` = slug) or `"application"` (`target_id` = application id). |
| `get_rendered_pdf(target_type, target_id)` | Save a local PDF inspection copy plus per-page PNG paths and return slim metadata. No image base64 is included. |
| `get_rendered_pdf_page_image(target_type, target_id, page_number)` | Explicitly fetch one 1-based page preview, including only that page's `page_image_b64`. |
| `prepare_application_pdf_upload(application_id)` | Stage an atomic disposable copy of the canonical application PDF for direct browser upload, rendering and retrying once when no PDF exists yet. |

### PDF previews + the no-em-dash rule

`get_rendered_pdf` also rasterizes the PDF to one PNG per page (`{id}.pN.png`,
~120 dpi) next to the saved PDF and returns `page_count`, `page_images` (absolute
paths you can open with the `Read` tool), and `em_dash_found` / `em_dash_pages`.
It intentionally returns no image bytes. When a path is not reachable across the
MCP host boundary, call `get_rendered_pdf_page_image` with one 1-based page
number; that opt-in response includes `page_image_b64` for only the requested
page, never all pages.
A rendered resume must contain **no em dash** (U+2014) — an en dash (U+2013) is
acceptable only for numeric/date ranges. Check `em_dash_found` before sending a
resume; if true, fix the source and re-render. Rendering needs `pypdfium2` and
`pdfplumber` (the `[mcp]` extra); if either is missing or the PDF is unreadable,
`page_count` is `null`
and `page_images` is empty (the core result is still returned).

`prepare_application_pdf_upload(application_id)` accepts application IDs only.
It retrieves the canonical server-rendered application PDF, preserving that
artifact, and atomically stages a copy under
`$MAESTRO_CS_UPLOAD_DIR/<application_id>/<safe canonical filename>`. If the
environment variable is unset, the root is the repository-relative
`.playwright-mcp/uploads` directory (resolved from the installed module, not the
process working directory). Pair with Playwright `--output-dir` on the parent
`.playwright-mcp` tree so the returned `upload_path` is already inside
Playwright’s allowed output. Pass that absolute path straight to the file
chooser — do not copy/move with shell or Claude filesystem tools. The result
includes the upload path, byte count, SHA-256 digest, page count, and em-dash
findings. This prepares a browser attachment only; it does not authorize or
submit an application.

**Apply package**

| Tool | Description |
| --- | --- |
| `generate_qa_answers(application_id, questions)` | Generate a batch of screening-question answers for an application, grounded in the resume and any linked referral contact. |
| `generate_cover_letter(application_id, tone)` | Generate a cover letter for an application in the requested tone, replacing any prior generated one. |

**Templates**

| Tool | Description |
| --- | --- |
| `list_templates()` | List resume templates across both engines — id, display name, status (draft/ready), engine, default flag. |
| `get_template(template_id)` | Get a template's full source (Jinja2+LaTeX, or raw Typst) plus engine and supported format keys. |
| `create_template_draft(id, display_name, source?, validate?, engine?)` | Create a DRAFT template (`engine` defaults to `latex`; pass `engine="typst"` with required raw `.typ` source). Pass `validate=true` to test-compile in the same call. |
| `update_template_draft(template_id, source?, display_name?, validate?)` | Edit a draft template; changing the source resets it to draft. The active default template cannot be edited here. |
| `validate_template(template_id)` | Test-compile a template against a sample resume; becomes `ready` on success, or returns the compile error to fix. |

**ATS scoring + gap tailoring**

Scoring is deterministic — a hybrid engine of deterministic lexical layers
(keyword coverage, placement & recency, title match, experience gate, format lint)
plus a pinned local embedding model for two semantic signals: an **anchored**
per-skill fallback (a soft match needs both a shared lexical anchor token and
embedding proximity) and a section-level `semantic_fit` coverage score — all over
versioned YAML config, **no LLM anywhere in the score**. The one LLM call in this
workflow is `tailor_session`, which turns saved gap resolutions into typed resume
edits.
These tools share persistent sessions with the web UI's gap page, so a
walkthrough started in either surface can be finished in the other.

**Breaking change for MCP clients:** Scripts and clients calling
`get_tailoring_session`, `close_tailoring_session`, `resolve_gaps`, or
`tailor_session` must rename the argument key from `session_id` to
`tailoring_session_id`, then reconnect or refresh cached tool schemas after
upgrading. Backend REST URLs and stored session IDs are unchanged. There is no
legacy `session_id` alias because exposing it would recreate the Cowork/MCP
transport-session collision this rename avoids.

| Tool | Description |
| --- | --- |
| `score_ats(job_id, target_type?, target_id?)` | Deterministic ATS score (replaces the old `score_fit` LLM scorer). Omit the target to score **all** base resumes (fast, no LLM calls); or target one `"base_resume"` (`target_id` = slug) / `"application"` (`target_id` = id). Returns a 0–100 composite, per-layer subscores, gate warnings, and a per-skill diagnostic table with fix hints. |
| `compare_ats(application_id)` | Before/after ATS comparison for an application: composite and per-layer deltas plus a per-skill diff (absent→matched, skills-list-only→dual, decayed→recent). Computes any missing phase row on demand. |
| `create_tailoring_session(job_id, base_resume, enrich?)` | Start the gap-analysis workflow: scores the base (persisted as the "before" score) and returns the session's gap list in fix-cost order. `enrich=true` (default) runs one LLM pass adding display-only helper text and elicitation questions per gap — narrative never feeds the score. |
| `quick_tailor(job_id, base_resume)` | Fast-path tailoring: fills the gap session from the user's saved quick-tailor profile instead of walking gaps one by one. Makes no in-house LLM call of its own. |
| `list_tailoring_sessions(job_id)` | List all tailoring sessions for a job, newest first, so you can resume an open one instead of spawning a duplicate. |
| `get_tailoring_session(tailoring_session_id)` | Resume a half-done gap walkthrough: the frozen gap list, resolutions saved so far, and status (`open`/`tailored`). |
| `close_tailoring_session(tailoring_session_id)` | Abandon an open tailoring session without tailoring it. |
| `resolve_gaps(tailoring_session_id, resolutions)` | Save `{gap_id, action, payload}` resolutions (merged by gap_id, idempotent). Actions: `add_keyword` (wording/placement fixes where evidence already exists), `user_input` (the user's real experience, for missing skills), `attach_project`, `skip`. |
| `tailor_session(tailoring_session_id, user_prompt?)` | Run the tailor pipeline: resolutions → one LLM edit-ops call → tailored application, auto-scored. Returns the session plus the before/after ATS compare. |

**Profile coach**

| Tool | Description |
| --- | --- |
| `explore_top_skills(role_category?, level?, employment_type?, limit?)` | Most-requested skills across collected JDs. |
| `explore_skill_heatmap(limit?)` | Skill-frequency heatmap. |
| `explore_role_mix_over_time()` | Role mix of collected jobs over time. |
| `explore_fit_distribution()` | How each base resume's ATS composites (deterministic engine, not LLM fit scores) are distributed across jobs. |
| `explore_gap_frequency(role_category?, level?, employment_type?, limit?)` | Skills that recur as gaps across saved JDs, ranked by how many jobs want them and their ATS point headroom — recurring demand, not a "you lack this" list. |
| `explore_ats_over_time(role_category?, level?, employment_type?)` | Average ATS composite over time (weekly), split by phase (base vs tailored) and role category. |
| `explore_tailoring_lift(role_category?, level?, employment_type?)` | How much tailoring lifts the ATS score (base→tailored), averaged per role category, plus an overall row. |
| `list_applications(status?, role_category?, limit?, offset?)` | List applications as a **thin summary array, paginated** (limit + offset; carries each row's legacy `verdict` + `gap_summary` where present, but no `customized_json` — use `get_application` for detail), optionally filtered. |
| `export_jobs(role_category?, level?, since?, skill?)` | Export filtered job rows for analysis. |

**Proposal ledger**

Agent-hunted applications route through a proposal ledger with an explicit
human consent gate before anything is submitted — these tools file, triage,
and carry a proposal through that lifecycle.

| Tool | Description |
| --- | --- |
| `propose_application(job_id, fit?, plan?, application_id?, referral_id?)` | File an agent-hunted application proposal for user review; idempotent if one is already open for the job. Refused for a blocklisted company or a previously declined posting. |
| `list_proposals(status?)` | List application proposals, optionally filtered by status. Apply runs execute `status="accepted"` proposals only. |
| `get_proposal(proposal_id)` | Get proposal detail: job facts, application summary, QA entries, evidence manifest. |
| `record_decision(proposal_id, fit, application_id?)` | Record the user's decision on a proposal in `needs_decision`, resolving it back to `pending_review`. |
| `request_decision(proposal_id, reason)` | Escalate an unlinked or ambiguous proposal to `needs_decision`. |
| `resume_proposal(proposal_id)` | Return a `needs_human` proposal to `pending_review` so preparation can continue. |
| `get_final_review(proposal_id)` | Compact final-review bundle — job summary, chosen base/ATS delta, PDF readiness, QA answers, EEO consent flag, blocked items, evidence manifest — read before asking for consent. |
| `record_consent(proposal_id, action, channel, note?)` | Record the user's explicit approve/reject decision. Call only after the user has actually said yes or no; writes an append-only audit row. |
| `attach_evidence(proposal_id, step, label, image_base64, kind?)` | Attach step evidence as base64 image bytes. Prefer `attach_evidence_file` whenever the screenshot already exists as a file. |
| `attach_evidence_file(proposal_id, step, label, file_path, kind?)` | Attach evidence from an image file already on disk (e.g. a Playwright screenshot); bytes are read and uploaded server-side. |
| `mark_submitted(proposal_id, user_attested?, channel?, note?)` | Flip an approved proposal to submitted, linking the application to applied. Normally requires submission-receipt evidence. |
| `record_triage(proposal_ids, action, channel?, note?, reason?)` | Record the user's accept/decline triage decision over one or many proposals; accept queues them for the next apply run. |
| `report_failure(proposal_id, reason)` | Report execution failure, transitioning a proposal to `needs_human` (or the terminal `submission_uncertain` status). |

## Add to Claude Desktop

> **Claude Desktop and Claude Code are separate surfaces.** A server
> registered with Claude Code — in `.mcp.json` or via `claude mcp add` — gives
> Desktop chats nothing, and the reverse is equally true. Each has to be set
> up on its own.

### Route 1 — let the setup script do it

```bash
./scripts/setup-mcp.sh --write-desktop-config
```

Opt-in, because that file is shared with your other MCP servers. It **refuses
to run while Claude Desktop is open** (the app writes this file too), backs the
file up first, merges a single `mcpServers` key, and leaves every other server
and top-level key exactly as it found them. It touches **only** this file —
`~/.codex/config.toml` is printed for you to paste and is never written, so a
Codex or ChatGPT desktop setup cannot be affected. Runs fine from inside a
Claude Code session. Other Maestro profiles already in
the file are reported and left alone — Claude Desktop can toggle servers per
chat, so having several registered is fine.

### Route 2 — the app's Connectors UI

**Settings → Connectors → Add custom connector** (older builds put this under
**Settings → Developer**), then:

| Field | Value |
| --- | --- |
| **Name** | `maestro-career-studio` |
| **Type / transport** | **STDIO** (see [Keep the transport STDIO](#keep-the-transport-stdio)) |
| **Command** | absolute path to the console script, e.g. `<REPO>/backend/.venv/bin/maestro-career-studio-mcp` |
| **Environment variables** | `BACKEND_URL` = `http://localhost:8001`<br>`MAESTRO_CS_MCP_PROFILE` = `full`<br>`MAESTRO_CS_MCP_CLIENT` = `Claude Desktop` |

`scripts/setup-mcp.sh` prints these exact values with every placeholder
already resolved.

### Route 3 — editing `claude_desktop_config.json` by hand

**Fully quit Claude Desktop first (Cmd+Q — a window close is not enough).**
The app writes this file too, so an edit made while it is running can be
discarded when it exits. Then, on macOS, edit:

```
~/Library/Application Support/Claude/claude_desktop_config.json
```

Use [`claude_desktop_config.example.json`](./claude_desktop_config.example.json)
in this directory as a starting point — merge its `maestro-career-studio` entry into your
existing `mcpServers` map and replace `/absolute/path/to/maestro-career-studio` with the
repository's absolute path.

Install the backend with its MCP extras in a virtual environment so the
`maestro-career-studio-mcp` console script is available, then point `command` at that
script. For example:

```json
"command": "/absolute/path/to/maestro-career-studio/backend/.venv/bin/maestro-career-studio-mcp"
```

The console script resolves the installed package directly, so this form does
not need a `cwd` entry.

Restart Claude Desktop, then **verify under Settings → Connectors that the
server is actually listed**. This route does work — a normal install carries
all six profiles in this file indefinitely — but verify rather than assume, and
if a block does go missing after a relaunch, use Route 1 or 2 instead of
editing the file a third time.

## Add to Claude Code

Easiest of all is the plugin above. Failing that, `scripts/setup-mcp.sh`. It covers both routes below — but they are
different routes with different reach, and knowing which one is serving you is
most of MCP troubleshooting.

**Claude Code has three scopes**, and the difference is not cosmetic:

| Scope | Where it lives | Who sees it | Approval |
| --- | --- | --- | --- |
| `project` | `.mcp.json` at the repo root | sessions opened **in this repo** | **yes**, once per project |
| `local` (the CLI **default**) | `~/.claude.json`, keyed by directory | sessions in **that one directory** | no |
| `user` | `~/.claude.json`, global | sessions in **any** directory | no |

**Route 1 — `.mcp.json` (project scope).** The setup script writes it
(gitignored: it holds this machine's absolute venv path). Two properties
surprise people. It is **approval-gated** — the offer appears when you start a
session and stays inert until you accept, with the answer recorded in the
project's `enabledMcpjsonServers` — and the session that *ran* the script has
already read its config, so **the offer reaches your next session**, not the
current one. The script also keeps this file to a **single** profile, because
every entry in it is offered to every session in the repo.

**Route 2 — `claude mcp add` (user scope).** For sessions outside the repo:

```bash
claude mcp add --scope user maestro-career-studio \
  -e BACKEND_URL=http://localhost:8001 \
  -e MAESTRO_CS_MCP_PROFILE=full \
  -- /absolute/path/to/backend/.venv/bin/maestro-career-studio-mcp
```

`--scope user` is load-bearing. **The CLI defaults to `local`**, which is
private to whichever directory you happened to run the command in — so a
"global" registration made without the flag silently works in exactly one
place. Use `--scope project` to write `.mcp.json` at the repo root instead.
The `--` separates Claude's own flags from the command that launches the
server; everything after it is executed verbatim.

Verify and manage — `list` shows every registration, `get` names the scope of
one:

```bash
claude mcp list
claude mcp get maestro-career-studio
```

## Add to Cursor, Windsurf, and other stdio clients

Anything that speaks stdio MCP takes the same three facts: the **command**
(`maestro-career-studio-mcp`), and the two env vars `BACKEND_URL` and
`MAESTRO_CS_MCP_PROFILE`. Most use Claude Desktop's exact JSON shape, so the
example file in this directory usually drops straight in.

## Add to the ChatGPT desktop app / Codex

The ChatGPT **desktop** app launches local stdio servers, so this works the same
way it does in Claude Desktop. (ChatGPT on the **web** is different — its
connectors take remote HTTPS endpoints only. Use the desktop app.)

Two routes. The config file is the one verified end to end.

### Route 1 — `~/.codex/config.toml` (verified working)

The ChatGPT desktop app and Codex CLI share this personal config, so one file
serves both. Note the key is `mcp_servers` (snake_case) and each server's `env`
is its own table:

```toml
[mcp_servers.maestro-career-studio]
command = "<PYTHON>"
args = ["-m", "mcp_server.server"]

[mcp_servers.maestro-career-studio.env]
BACKEND_URL = "http://localhost:8001"
MAESTRO_CS_MCP_PROFILE = "full"

[mcp_servers.maestro-career-studio-hunt]
command = "<PYTHON>"
args = ["-m", "mcp_server.server"]

[mcp_servers.maestro-career-studio-hunt.env]
BACKEND_URL = "http://localhost:8001"
MAESTRO_CS_MCP_PROFILE = "hunt"

[mcp_servers.maestro-career-studio-apply]
command = "<PYTHON>"
args = ["-m", "mcp_server.server"]

[mcp_servers.maestro-career-studio-apply.env]
BACKEND_URL = "http://localhost:8001"
MAESTRO_CS_MCP_PROFILE = "apply"
MAESTRO_CS_UPLOAD_DIR = "<REPO>/.playwright-mcp/uploads"
```

`<PYTHON>` is the **absolute path to the interpreter you installed the backend
into** — the same environment where `pip install -e ".[mcp]"` ran, e.g.
`<REPO>/backend/.venv/bin/python3`. Find it with `which python3` inside that
environment.

The module form (`-m mcp_server.server`) needs no working directory because the
package is installed, so Python resolves it from site-packages rather than the
process cwd.

Repeat the pair of tables for `explore` and `templates` if you want them.
Defining all five is fine — pick which one a given chat uses in the app's
source/connector picker rather than enabling `full` alongside a scoped profile in
the same conversation.

Verify by asking a fresh chat *"can you see maestro-career-studio mcp?"* — it should list
the tool domains, and something like *"what base resumes do I have?"* should
return your real slugs.

### Route 2 — the GUI dialog

**Settings → Plugins → MCPs → Connect to a custom MCP**, then:

| Field | Value |
| --- | --- |
| **Name** | `maestro-career-studio` |
| **Type** | **STDIO** |
| **Command to launch** | absolute path to the console script, e.g. `<REPO>/backend/.venv/bin/maestro-career-studio-mcp` |
| **Arguments** | *(leave empty)* |
| **Environment variables** | `BACKEND_URL` = `http://localhost:8001`<br>`MAESTRO_CS_MCP_PROFILE` = `full` |
| **Environment variable passthrough** | *(leave empty; add `PATH` only if the command cannot resolve)* |
| **Working directory** | *(leave empty)* |

Then **Save**.

Notes:

- **Use an absolute path** for the command. GUI apps do not inherit your shell's
  `PATH`, so a bare `maestro-career-studio-mcp` will usually fail to launch. Find it with
  `which maestro-career-studio-mcp` after `pip install -e ".[mcp]"`.
- **No working directory is needed.** The console script resolves the installed
  package directly rather than the process working directory.
- If you prefer the module form, set the command to your Python interpreter's
  absolute path and add two arguments: `-m` and `mcp_server.server`.
- `BACKEND_URL` must be the **host** port compose publishes (`8001` by default),
  not the container's internal `8000`.
- Add one entry per profile if you want scoped tool lists — same command, only
  `MAESTRO_CS_MCP_PROFILE` differs.

### Keep the transport STDIO

The other Type in that dialog takes a URL, which means exposing the backend over
the network. Maestro CS's backend has **zero authentication** by design (see
[`SECURITY.md`](../../SECURITY.md)) and binds to `127.0.0.1` precisely because
anyone who can reach it gets full read/write on your employment history, salary
expectations and EEO answers. STDIO keeps the server a local subprocess, which is
the whole point — stay on it.

## Example prompts

1. **Extract and store a JD.**
   > "Here's a JD: `<paste>`. Extract it and store it."

   Claude extracts the posting into the `JobExtraction` schema, then calls
   `store_extracted_jd`.

2. **Tailor a resume to a job and produce a PDF.**
   > "Compare my `data_scientist` resume to job `<id>` and tailor it, then make a PDF."

   Claude calls `get_base_resume` + `get_job` to read both, decides the edits,
   calls `tailor_application` to save the result, then `render_pdf` for the PDF.

3. **Gap-driven tailoring with a before/after ATS score.**
   > "Run the gap workflow for job `<id>` against my `data_scientist` resume."

   Claude calls `score_ats` to pick the base, `create_tailoring_session` to get
   the gap list, walks the gaps conversationally (asking each elicitation
   question), saves answers with `resolve_gaps`, then `tailor_session` — and
   relays the before/after ATS compare.

4. **Profile coaching across everything collected.**
   > "Across all the JDs I've collected, what skills should I learn next to
   > improve my data-engineer profile?"

   Claude pulls `explore_top_skills` + `explore_fit_distribution` + `export_jobs`
   + `list_applications`, then reasons over the aggregates.

## How it works

Claude Desktop (or another stdio MCP client — the ChatGPT desktop app, Codex
CLI, Cursor, etc.) launches this server as a stdio subprocess. Each tool call
is turned into an HTTP request to the FastAPI backend, which owns persistence
and rendering. Claude does the reasoning; the app does the storage and the
LaTeX.

```
MCP client --stdio--> maestro-career-studio-mcp --HTTP--> FastAPI (:8000) --> Postgres + LaTeX
```

### List responses are a single JSON array (audit #10)

The list tools (`list_jobs`, `list_applications`) return **one** JSON array, not a
concatenated object stream. `client._request` returns a single `response.json()`,
and FastAPI serializes `list[Model]` as one array — there is no `}{` concatenation
anywhere in `client.py`/`server.py`. This is covered by
`test_list_endpoints_return_single_json_array`. The list payloads are intentionally
slim; fetch full records via `get_job` / `get_application`.

## Development / tests

From `backend/`:

```bash
pip install -e ".[dev,mcp]"
python -m pytest mcp_server/tests/ -v
```

The tests use [`respx`](https://lundberg.github.io/respx/) to mock the backend's
HTTP responses, so **no database or running backend is needed**.

To sanity-check the stdio handshake, run:

```bash
python -m mcp_server.server
```

It starts and blocks reading stdin — that's expected; Claude Desktop drives it
over stdio. Ctrl-C to exit.

## Troubleshooting

- **"Could not reach the backend… Is it running on :8000?"** — the FastAPI
  backend isn't up, or `BACKEND_URL` points at the wrong host port. Confirm the
  published port (`docker compose ps`) and that it answers, e.g.
  `curl http://localhost:8001/health`. The default message says `:8000`, but your
  `BACKEND_URL` may be `:8001`.
- **A tool errors with a `422`** — the JSON Claude sent didn't match the backend
  schema (e.g. a malformed `extracted_json` or `ResumeData`). The validation
  detail comes back in the error, so Claude can see what's wrong and correct it.
- **The tools don't appear in Claude Code** — work out which route you expected
  to serve you (see [Add to Claude Code](#add-to-claude-code)). `claude mcp get
  maestro-career-studio` prints the scope of a CLI registration; a `local`-scope
  one only works in the directory it was added from. A `.mcp.json` entry needs
  both a **new session** started in the repo and your **approval** — until then
  the file is correct and inert, and the project's `enabledMcpjsonServers` list
  is empty. Re-running `scripts/setup-mcp.sh` is always safe: it is keyed by
  server name, so it overwrites rather than accumulates.
- **The tools appear twice, or the model picks the wrong one** — you have two
  profiles registered at once (`full` beside a scoped one). The setup script
  prunes siblings from `.mcp.json`, but registrations you made with
  `claude mcp add` are yours: `claude mcp list`, then
  `claude mcp remove <name>`.
- **A Claude Desktop config edit did not survive** — the app writes
  `claude_desktop_config.json` itself, so an edit made while it is running can
  be lost when it exits. Quit fully (Cmd+Q) before editing, or let
  `./scripts/setup-mcp.sh --write-desktop-config` do it — it refuses to run
  while the app is open, which removes the failure mode entirely. If an edit
  still vanishes, add the server through Settings → Connectors instead. Note
  also that Claude Desktop is a **separate surface** from Claude Code — a
  working `claude mcp list` says nothing about what Desktop can see.
