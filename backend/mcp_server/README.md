# Maestro CS MCP Server

A connector that lets your AI assistant (Claude, the ChatGPT desktop app,
Codex) use Maestro Career Studio. Your assistant does the thinking: it reads
job postings, compares them with your resumes and suggests edits. The app keeps
your data, renders the PDFs (LaTeX or Typst) and tracks your applications. Each
tool below is one action your assistant can take in the app.

## Before you start

- **The app must be running.** From the repo root: `docker compose up -d --build`.
  The backend is then on **http://localhost:8001** by default (set by
  `BACKEND_HOST_PORT` in `.env`). If you run the backend directly with
  `uvicorn app.main:app --port 8000` from `backend/`, it is on port 8000 instead.
- The extension and plugin routes below need nothing else. Only the setup-script
  and hand-config routes need a **host Python 3.12+** (a fresh macOS ships 3.9:
  `brew install python@3.12`; Debian/Ubuntu: `sudo apt install python3.12
  python3.12-venv`).

## Install

Pick the route for your assistant. Every route defaults to the `full` profile
(all 83 tools); see [Profiles](#profiles) to narrow it.

### Claude (Desktop, and Claude Code inside the Claude app)

Settings → **Extensions** → **Install Extension**, then pick
[`mcpb/maestro-career-studio.mcpb`](../../mcpb/maestro-career-studio.mcpb) in
your clone. Leave the fields empty; the defaults are correct. The **Tool
profile** field is where you choose a scoped profile.

The extension runs the server inside the backend container, so it needs no host
Python and no config file.

Claude Desktop and the Claude Code CLI are set up separately: a server added to
one does not appear in the other. For the Claude Code CLI, install the plugin:

```bash
claude plugin marketplace add https://github.com/seinun-ai/maestro-career-studio
claude plugin install maestro-career-studio@maestro-career-studio
```

### Codex and the ChatGPT desktop app

In the app: Settings → **Plugins** → **Add** → add
`seinun-ai/maestro-career-studio` as a marketplace, then **Install**. From the
Codex CLI:

```bash
codex plugin marketplace add seinun-ai/maestro-career-studio
codex plugin add maestro-career-studio@maestro-career-studio
```

ChatGPT on the **web** only takes remote HTTPS connectors, so use the desktop
app.

The plugins (Claude Code and Codex) run the server inside the backend container
and always load the `full` profile. For a scoped profile, use the setup script
or a hand-written config below.

**Don't set `COMPOSE_PROJECT_NAME`** if you use the extension or a plugin. They
look for the container by its default name, `maestro-career-studio-backend-1`;
renaming the project renames the container and they can't find it. If you need
a different name, use the setup script instead (or, for the extension, fill in
its **Container name** field).

### Cursor, Windsurf and other clients: the setup script

From the repo root:

```bash
./scripts/setup-mcp.sh                 # full profile
./scripts/setup-mcp.sh --profile hunt  # a scoped profile
./scripts/setup-mcp.sh --print-only    # change nothing, just print the config
```

It builds a host virtualenv, works out the backend port, registers the server
with Claude Code, and prints a paste-ready block for each client. You can also
ask a coding agent (Claude Code, Codex CLI) in this repo to run it for you.

### By hand

From `backend/`:

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[mcp]"
```

That gives you the command `backend/.venv/bin/maestro-career-studio-mcp` (or
`python -m mcp_server.server`). Every client needs the same three things:

- **command**: the absolute path to `maestro-career-studio-mcp`. Desktop apps
  don't see your shell's `PATH`, so a bare name usually fails; find the path
  with `which maestro-career-studio-mcp` inside the venv.
- **`BACKEND_URL`**: `http://localhost:8001` (the host port, not the
  container's internal 8000). Without it the server assumes
  `http://localhost:8000`.
- **`MAESTRO_CS_MCP_PROFILE`**: `full` or a scoped profile.

Templates with every profile filled in:

- **Claude Desktop and most stdio clients** (Cursor, Windsurf):
  [`claude_desktop_config.example.json`](./claude_desktop_config.example.json).
  On macOS the Desktop file is
  `~/Library/Application Support/Claude/claude_desktop_config.json`. **Quit
  Claude Desktop fully (Cmd+Q) before editing**: the app writes this file too
  and can discard an edit made while it is open. Merge the entries you want into
  `mcpServers`, restart, and check the server is listed under Settings →
  Connectors.
- **Codex CLI and the ChatGPT desktop app** (they share `~/.codex/config.toml`):
  [`codex_config.example.toml`](./codex_config.example.toml). The key is
  `mcp_servers` (snake_case) and each server's `env` is its own table. The
  ChatGPT app's custom MCP dialog takes the same values; set Type to **STDIO**
  and leave the working directory empty.
- **Claude Code CLI**, for sessions in any directory:

  ```bash
  claude mcp add --scope user maestro-career-studio \
    -e BACKEND_URL=http://localhost:8001 \
    -e MAESTRO_CS_MCP_PROFILE=full \
    -- /absolute/path/to/backend/.venv/bin/maestro-career-studio-mcp
  ```

  Keep `--scope user`. Without it the CLI uses `local` scope, which works only
  in the directory you ran the command from.

### Keep the transport STDIO

Some clients offer an HTTP/URL transport. Don't use it: that means exposing the
backend over the network, and the backend has no login by design (see
[`SECURITY.md`](../../SECURITY.md)). Anyone who can reach it can read and change
your employment history, salary expectations and EEO answers. STDIO keeps the
server a local process on your machine.

## Profiles

`MAESTRO_CS_MCP_PROFILE` picks which tools your assistant sees, so a focused
chat isn't cluttered with unrelated ones.

| Profile | Use when | Tools |
| --- | --- | --- |
| `full` | Mixed use (default) | all 83 |
| `hunt` | Finding jobs and proposing them, no browser filling | 19 |
| `apply` | Tailor, PDF, form autofill, evidence, consent, submit | 46 |
| `explore` | Charts and trends across your saved jobs (`explore_*`) | 11 |
| `templates` | Creating and testing resume templates | 12 |
| `career` | Reading and editing your Career KB | 18 |

**Enable one profile per chat.** The scoped profiles are subsets of `full`, so
running `full` beside one lists every shared tool twice and the model has to
guess which to call.

### Applying with a browser tool

For apply chats, pair the `apply` profile with Playwright MCP and point both at
the same folder, so the PDF the app stages is already somewhere the browser
can upload from:

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

The placeholders are the same as in
[`claude_desktop_config.example.json`](./claude_desktop_config.example.json).
Playwright's `--output-dir` must be the parent `.playwright-mcp` folder. Enable
only these two servers for apply chats, and restart Claude Desktop (Cmd+Q)
after changing the config. If Claude asks once for access to `.playwright-mcp`,
approve it.

## Skills

Ready-made skills for a daily job hunt (`job-hunt`), an apply run
(`apply-session`), and building your own versions (`customize-job-skills`) are
in [`docs/skills/`](../../docs/skills/README.md). Copy one into your client's
skills folder and ask for it.

## The tools

Each tool's own description (which your assistant sees) has the full details.

**Jobs and search**
- `get_job_search_brief`: your profile, constraints and resume summaries; call first in a job-search chat.
- `find_job_by_url`: check whether a posting is already saved.
- `store_extracted_jd`: save a job. Your assistant fills in the job's details in the format the tool describes.
- `list_jobs`, `get_job`: saved jobs (a short paginated list, then one job in full).
- `list_referrals`: referral contacts.

**Tracking**
- `list_applications`, `get_application`: your applications (a short paginated list, then one in full).
- `update_application`: set status, applied date, notes or referral.
- `export_jobs`: export filtered job rows for analysis.

**Resumes**
- `list_base_resumes`, `get_base_resume`: your base resumes.
- `edit_base_resume`: change parts of a base resume and re-render its PDF. The tool's own description lists the edit types.
- `update_base_resume`, `create_base_resume`: replace or create a whole base resume.
- `duplicate_base_resume`, `archive_base_resume`, `unarchive_base_resume`: copy, hide or restore one (archiving deletes nothing).
- `list_resume_versions`, `get_resume_version`, `restore_resume_version`: every saved version of a resume; restoring adds a new version and deletes nothing.

**Health check** (run before tailoring)
- `run_health_check`, `get_health_report`: score a resume on its own, without a job, and list what to fix.
- `waive_health_gate`, `unwaive_health_gate`: skip a failing check only when you say so, or undo that.

**Scoring and tailoring**
- `score_ats`: score one resume, or all your base resumes, against a job.
- `compare_ats`: before/after scores for a tailored application.
- `create_tailoring_session`, `list_tailoring_sessions`, `get_tailoring_session`, `close_tailoring_session`: start, find, resume or abandon a gap walkthrough. These are the same sessions as the web app's gap page, so you can start in one and finish in the other.
- `resolve_gaps`: save your answer for each gap (add a keyword, describe real experience, attach a project, skip, or "can't confirm" so it's never asked again).
- `tailor_session`: turn your answers into a tailored application and show the before/after score.
- `quick_tailor`: fill the gaps from your saved quick-tailor profile instead of walking them one by one.
- `tailor_application`: create a tailored application from a base resume with the edits your assistant chose.
- `edit_application`: make a further fix to a tailored application, keeping earlier edits.

Scoring compares your resume with the job using fixed rules plus a small model
that runs on your computer; the same inputs always give the same score. It is
not an employer's score. `create_tailoring_session` can add helper text and
questions per gap with `enrich=true`; that text is only for display and never
changes the score.

**PDFs**
- `render_pdf`: render a base resume or an application.
- `get_rendered_pdf`: save the PDF locally with one PNG per page, and report any em dashes.
- `get_rendered_pdf_page_image`: fetch one page image, for clients that can't open local files.
- `prepare_application_pdf_upload`: save a copy of the application PDF where the browser tool can upload it. It does not submit anything.

A rendered resume should contain **no em dash** (—); an en dash (–) is fine for
date and number ranges. If `em_dash_found` is true, fix the text and re-render.

**Application answers**
- `get_autofill_profile`: your stored form-fill details (contact, work authorization, consented EEO answers).
- `generate_qa_answers`: answers to an application's screening questions.
- `generate_cover_letter`: a cover letter in the tone you ask for.
- `list_qa_entries`: the answers and cover letters generated so far.

**Proposals and consent** (nothing is submitted without your yes)
- `propose_application`, `list_proposals`, `get_proposal`: file a job your assistant found for your review, and read the queue.
- `record_triage`: accept or decline proposals; accepted ones are queued for the next apply run.
- `request_decision`, `record_decision`, `resume_proposal`, `report_failure`: handle proposals that need your input or hit a problem.
- `get_final_review`: everything to check before you approve.
- `record_consent`: record your approve/reject, only after you have actually answered.
- `attach_evidence`, `attach_evidence_file`: attach screenshots of each step.
- `mark_submitted`: mark an approved proposal as submitted.

**Career KB**
- `get_career_context`, `get_career_export`: your full career record, as structured data or as `career.md`.
- `kb_list_entities`, `kb_get_entity`, `kb_list_points`: browse entries and points, with their IDs.
- `kb_capture`, `kb_ingest_resume`, `kb_sync_base`: add new material as draft points for you to approve.
- `kb_edit_point`, `kb_create_entity`, `kb_edit_entity`, `kb_edit_profile`: correct or add entries.
- `kb_approve_points`: approve or retire points, only after you have approved them.
- `create_base_resume_from_kb`: build a new base resume from approved entries.

**Templates**
- `list_templates`, `get_template`: resume templates (LaTeX or Typst).
- `create_template_draft`, `update_template_draft`, `validate_template`: create, edit and test-compile a template.

**Insights**
- `explore_top_skills`, `explore_skill_heatmap`, `explore_gap_frequency`: which skills your saved jobs ask for, and which keep showing up as gaps.
- `explore_role_mix_over_time`, `explore_fit_distribution`, `explore_ats_over_time`, `explore_tailoring_lift`: trends in roles, scores and how much tailoring helps.

## Example prompts

- "Here's a job posting: `<paste>`. Save it."
- "Compare my `data_scientist` resume with job `<id>`, tailor it, then make a PDF."
- "Run the gap workflow for job `<id>` against my `data_scientist` resume."
- "Across all the jobs I've saved, what skills should I learn next for data engineering roles?"

## How it works

Your assistant starts this server as a local process and talks to it over
stdio. Each tool call becomes a request to the app's backend, which stores
everything and renders the PDFs.

```
AI assistant --stdio--> maestro-career-studio-mcp --HTTP--> backend --> your data + LaTeX/Typst
```

Contributing and running the tests: see [../../CONTRIBUTING.md](../../CONTRIBUTING.md).

## Troubleshooting

- **"Could not reach the backend… Is it running on :8000?"**: the app isn't
  running, or `BACKEND_URL` points at the wrong port. Check with
  `docker compose ps` and `curl http://localhost:8001/health`. The message
  always says `:8000`, even when your `BACKEND_URL` is `:8001`.
- **A tool fails with a `422`**: the data your assistant sent didn't match what
  the app expects. The error says what's wrong, so your assistant can fix it and
  retry.
- **The tools don't appear in Claude Code**: `claude mcp get
  maestro-career-studio` shows how it is registered; a `local`-scope entry only
  works in the directory it was added from. If the setup script wrote
  `.mcp.json`, start a **new** session in the repo and **approve** the server
  when asked. Re-running `./scripts/setup-mcp.sh` is always safe.
- **Tools appear twice, or the model picks the wrong one**: two profiles are
  enabled at once (`full` beside a scoped one). In Claude Code, `claude mcp
  list`, then `claude mcp remove <name>`.
- **A Claude Desktop config edit didn't stick**: the app rewrites
  `claude_desktop_config.json` when it quits. Quit fully (Cmd+Q) before
  editing, or use the extension instead, which Desktop manages itself.
- **It works in Claude Code but not Claude Desktop (or the reverse)**: they are
  set up separately; see [Install](#install).
- **The extension or plugin can't find the container**: check `docker ps`. If
  the backend container isn't named `maestro-career-studio-backend-1` (for
  example, because `COMPOSE_PROJECT_NAME` is set), put its name in the
  extension's **Container name** field, or use the setup script.
