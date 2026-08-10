# Maestro CS MCP Server

A thin [MCP](https://modelcontextprotocol.io) wrapper around the Maestro CS
FastAPI backend, so Claude Desktop can drive the app directly. Claude is the
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

- A Python environment with the backend installed (this is what Claude Desktop
  launches as a subprocess). The MCP server was tested with `mcp` 1.26.

## Install

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
Claude sessions (especially apply + Playwright), set
`MAESTRO_CS_MCP_PROFILE` so unused domains never appear in the tool list:

| Profile | Use when | Approx tools |
| --- | --- | --- |
| `full` | Mixed / default | all (73) |
| `hunt` | Job search + propose (no browser fill) | 19 |
| `apply` | Tailor → PDF → autofill → evidence/consent/submit | 45 |
| `explore` | Analytics (`explore_*`) | ~11 |
| `templates` | Template draft/validate/render | ~12 |
| `career` | Career KB read/write (`kb_*`, career context/export) | ~10 |

Same binary; Claude Desktop entries differ only by `env`. Example apply entry
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
| `list_referrals` | List referral contacts (company, careers URL, contact name, notes, applications count). |

**JD ingest**

| Tool | Description |
| --- | --- |
| `store_extracted_jd(extracted_json, raw_text?, source_url?)` | Store a JD that Claude extracted. `extracted_json` must match the `JobExtraction` schema (company, title, role_category, level, employment_type, work_mode, city/state/country, location_raw, salary_min/max, salary_period, work_authorization, opt_accepted, years_experience_min/max, `skills[{skill_name, skill_category, requirement_level}]`, responsibilities[], qualifications[]). |

**Base resume writes**

| Tool | Description |
| --- | --- |
| `edit_base_resume(slug, ops)` | Apply typed edit `ops` to a base resume (read-then-edit; the server keeps every untouched field). Call `get_base_resume` first to pick indices/categories, then send only the changes. Op kinds: `replace_summary`, `toggle_entry`, `replace_bullet`, `replace_skills_group`. Re-renders the PDF. Use `update_base_resume` only for a full wholesale replace. |
| `update_base_resume(slug, data, display_name?)` | Replace a base resume. `data` is **required** — it's a full `ResumeData` replacement, not a patch. |
| `create_base_resume(slug, display_name, data)` | Create a new base resume from full `ResumeData`. |
| `duplicate_base_resume(slug, new_slug, new_display_name?)` | Copy an existing base resume to a new slug. |

**Tailor + render**

| Tool | Description |
| --- | --- |
| `tailor_application(job_id, base_resume, ops)` | Create an application by applying typed edit `ops` to a base resume server-side. Read the base with `get_base_resume`, then send only the changed fields as `ops` (same op kinds as `edit_base_resume`). The server inherits every untouched field from the stored base and validates the result. No backend LLM call. |
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
| `list_applications(status?, role_category?, limit?, offset?)` | List applications as a **thin summary array, paginated** (limit + offset; carries each row's legacy `verdict` + `gap_summary` where present, but no `customized_json` — use `get_application` for detail), optionally filtered. |
| `export_jobs(role_category?, level?, since?, skill?)` | Export filtered job rows for analysis. |

## Add to Claude Desktop

On macOS, edit:

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

Restart Claude Desktop (Cmd+Q, not just closing the window), then the
maestro-career-studio tools appear.

## Add to Claude Code

No config file needed — one command per profile:

```bash
claude mcp add maestro-career-studio \
  -e BACKEND_URL=http://localhost:8001 \
  -e MAESTRO_CS_MCP_PROFILE=full \
  -- /absolute/path/to/backend/.venv/bin/maestro-career-studio-mcp
```

The `--` separates Claude's own flags from the command that launches the server;
everything after it is executed verbatim. Add `--scope project` to write
`.mcp.json` at the repo root instead of your user config.

Verify and manage:

```bash
claude mcp list
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

Claude Desktop launches this server as a stdio subprocess. Each tool call is
turned into an HTTP request to the FastAPI backend, which owns persistence and
rendering. Claude does the reasoning; the app does the storage and the LaTeX.

```
Claude Desktop --stdio--> maestro-career-studio-mcp --HTTP--> FastAPI (:8000) --> Postgres + LaTeX
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
