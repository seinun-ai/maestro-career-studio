# Maestro CS MCP Server

A connector that lets your AI assistant (Claude, the ChatGPT desktop app,
Codex) use Maestro Career Studio. Your assistant does the thinking: it reads
job postings, compares them with your resumes and suggests edits. The app keeps
your data, renders the PDFs (LaTeX or Typst) and tracks your applications. Each
tool below is one action your assistant can take in the app.

## Before you start

Keep Maestro running on the same computer as your assistant. Docker publishes
the backend at `http://localhost:8001` by default (`BACKEND_HOST_PORT` in `.env`).
A direct `uvicorn app.main:app --port 8000` run uses port 8000; the
[native scripts](../../docs/native-install.md) use `http://127.0.0.1:8001`.
The assistant needs no Docker or Python to connect over HTTP. A
[uv install](../../README.md#quickstart) (`maestro start`) serves the
same URL, and its `maestro connect` command does the setup below from the terminal.

## Install

Open Settings › Agent apps › **Connect an agent app** and choose a
**Tool set**. Every route defaults to `full` (all 92 tools); see
[Profiles](#profiles) to narrow it. Enable one connection per client.

### Claude Desktop

**On a uv install**, run `maestro connect claude-desktop`. It adds a
`maestro-career-studio` entry to `claude_desktop_config.json` that runs the
install's own `maestro mcp` (a Python stdio bridge to the same endpoint) by its
full path, because Claude Desktop does not see your terminal's PATH. It keeps a
`.bak` copy of the old file and changes nothing else. Claude Desktop rewrites that
file while it runs, so when it is open the command waits and writes after you
quit it (`--now` writes at once; `--print` shows the entry). `--profile hunt` and
the other profile names choose a smaller tool set. On Docker, use the bundle:

Download the `.mcpb` from the card or the
[release](https://github.com/seinun-ai/maestro-career-studio/releases) and
double-click it. Settings → **Extensions** → **Install Extension** can also
open the downloaded bundle. Reinstall if you have the older Docker-based bundle.

The dependency-free Node ≥18 bridge forwards stdio to Maestro's HTTP endpoint;
it starts no Python or Docker process on Claude's side. **Maestro address**
defaults to `http://localhost:8001`; **Tool profile** chooses the tool set.
It works on macOS, Windows and Linux.

### URL clients

The card copies CLI commands, opens install links for Cursor and VS Code,
and gives other HTTP MCP clients a URL. For the default Docker port:

```bash
claude mcp add --scope user --transport http maestro-career-studio http://localhost:8001/mcp
codex mcp add maestro-career-studio --url http://localhost:8001/mcp
```

Use `/mcp` exactly — no trailing slash (`POST /mcp/` is a 307 redirect).
`--scope user` makes Maestro available in every folder; without it, Claude Code adds it to the current project only.
For a scoped profile, append its name, for example `/mcp/hunt`.

In the Codex app, open **Plugins** › **Add** › **Create custom MCP server**,
choose **Server URL**, paste the URL and set **Authentication** to **No authentication**.
Leave **Tunnel** off: it would share an unauthenticated Maestro.
claude.ai and chatgpt.com web connectors are outside this local setup.

For Claude Code and Codex plugins, follow the
[release-tag marketplace guide](../../plugins/maestro-career-studio/README.md#install).
The Codex marketplace uses the release tag as **Git ref** and `.agents/plugins`
plus `plugins` as **Sparse paths**. Both plugins connect by URL and load `full`.

### By hand

Codex CLI and the Codex app share `~/.codex/config.toml`:

```toml
[mcp_servers.maestro-career-studio]
url = "http://localhost:8001/mcp"
enabled = true
```

Claude Code and Cursor use this entry inside `mcpServers`:

```json
"maestro-career-studio": {
  "type": "http",
  "url": "http://localhost:8001/mcp"
}
```

VS Code uses the same entry under `servers` in `.vscode/mcp.json`.
[Codex examples](./codex_config.example.toml) cover every profile.
Claude Desktop needs the bundle or a Node bridge entry in
`claude_desktop_config.json`:

```json
"maestro-career-studio": {
  "command": "node",
  "args": ["<REPO>/mcpb/server/index.js"],
  "env": {
    "MAESTRO_CS_BACKEND_URL": "http://localhost:8001",
    "MAESTRO_CS_MCP_PROFILE": "full"
  }
}
```

(On a uv install, `maestro connect claude-desktop` writes the equivalent entry,
`"command": "<full path to maestro>", "args": ["mcp"]`, for you.)
Replace `<REPO>` with your clone's absolute path; use an absolute Node path if
Claude cannot find `node`. The file is at
`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS or
`%APPDATA%\Claude\claude_desktop_config.json` on Windows. Quit Claude Desktop
fully before editing, then restart. [Bridge examples](./claude_desktop_config.example.json)
cover every profile. Use one route per client to avoid duplicate tools.

### Legacy stdio

Existing `setup-mcp.sh` and `maestro-career-studio-mcp` connections keep working
for one release. The [setup script](../../scripts/setup-mcp.sh) is the fallback
for stdio-only clients and needs host Python 3.12+. It and the host stdio venv
are deprecated and removed in v0.10.0; the console entry point stays as a
compatibility fallback (SYSTEM.md §13 `mcp-stdio-venv`).

### Keep the connection local

`/mcp` has no authentication by design: a local process can already reach REST.
It lives inside the FastAPI app behind the same Host → Origin → CORS checks as
REST, with no second port or security definition. Never publish port 8001 or
proxy `/mcp` beyond this computer. See [SECURITY.md](../../SECURITY.md).

## Profiles

The **Tool set** selector picks a profile URL (`/mcp` for `full`, or
`/mcp/{profile}`); the bundle uses `MAESTRO_CS_MCP_PROFILE` for the same choice.
Each scoped URL lists exactly its allowlist and refuses tools outside it.

| Profile | Use when | Tools |
| --- | --- | --- |
| `full` | Mixed use (default) | all 92 |
| `hunt` | Finding jobs and proposing them, no browser filling | 21 |
| `apply` | Tailor, PDF, form autofill, evidence, consent, submit | 51 |
| `explore` | Charts and trends across your saved jobs (`explore_*`) | 11 |
| `templates` | Creating and testing resume templates | 13 |
| `career` | Reading and editing your Career KB | 21 |

**Enable one profile per chat.** The scoped profiles are subsets of `full`, so
running `full` beside one lists every shared tool twice and the model has to
guess which to call.

### Applying with a browser tool

For apply chats, pair the `/mcp/apply` URL with Playwright MCP. The browser's
output folder and Maestro's upload staging must agree, so the browser can use
the staged PDF. An HTTP-capable client can use:

```json
"maestro-career-studio-apply": {
  "type": "http",
  "url": "http://localhost:8001/mcp/apply"
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

The Playwright placeholders are the same as in
[`claude_desktop_config.example.json`](./claude_desktop_config.example.json),
which also shows Claude Desktop's Node bridge entry for `apply`.
Playwright's `--output-dir` must be the parent `.playwright-mcp` folder. Set
`MAESTRO_CS_UPLOAD_DIR` on the backend process for a native install. Enable
only these two servers for apply chats. If Claude asks once for access to
`.playwright-mcp`, approve it.

When the backend runs inside Docker,
`upload_path` is rewritten to the same folder as your computer sees it:
`<folder you ran docker compose from>/.playwright-mcp/uploads`. If the browser
sees the checkout under a different path, set `MAESTRO_CS_UPLOAD_HOST_ROOT` in
`.env` and run `docker compose up -d`. The usual case is a WSL clone driven by a
browser on Windows:
`MAESTRO_CS_UPLOAD_HOST_ROOT=\\wsl.localhost\Ubuntu\home\<you>\maestro-career-studio\.playwright-mcp\uploads`.

## Skills

Ready-made skills for a daily job hunt (`job-hunt`), an apply run
(`apply-session`), email status (`mail-status`), referral careers pages
(`referral-pages`), tailoring (`tailor-run`), and building your own versions
(`customize-job-skills`) are in [`docs/skills/`](../../docs/skills/README.md). Copy one into your client's
skills folder and ask for it, or open the app's **Automations** page and copy a
prompt into any agent app connected to Maestro; for a scheduled job, your agent
asks when to run it.

## The tools

Each tool's own description (which your assistant sees) has the full details.

**Jobs and search**
- `get_job_search_brief`: your profile, constraints, resume summaries, sync status (`enabled`, `role`) and an `applying` block (`answer_level`: your Screening answers setting, `facts`, `history` or `queued`); call first in a job-search chat.
- `sync_now`: ask the always-on copy to sync now; returns the round's outcome and per-step counts. On your laptop, it explains that your bot runs the sync; with sync off, it says "Sync isn't set up."
- `find_job_by_url`: check whether a posting is already saved.
- `store_extracted_jd`: save a job. Your assistant fills in the job's details in the format the tool describes. Saving scores the job against every base resume you can pick for it.
- `list_jobs`, `get_job`: saved jobs (a short paginated list, then one job in full), with ownership to identify jobs owned here and replicas. Each job carries its `stage`: `saved`, `scored`, `gaps`, `tailored`, `pdf_ready`, `applied` or `closed`.
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
- `set_base_resume_identity`: set what a resume is for — its countries, role, company and focus. A resume set for some countries is scored and recommended only for jobs in them.
- `list_resume_versions`, `get_resume_version`, `restore_resume_version`: every saved version of a resume; restoring adds a new version and deletes nothing.

**Health check** (run before tailoring)
- `run_health_check`, `get_health_report`: score a resume on its own, without a job, and list what to fix.
- `judge_health_bullets`: with no model key in the app, store your assistant's judgment of each bullet, by the app's own rubric, so the check can grade.
- `waive_health_gate`, `unwaive_health_gate`: skip a failing check only when you say so, or undo that.

**Scoring and tailoring**
- `score_ats`: score one resume, or all your base resumes set for the job's country, against a job.
- `compare_ats`: before/after scores for a tailored application.
- `create_tailoring_session`, `list_tailoring_sessions`, `get_tailoring_session`, `close_tailoring_session`: start, find, resume or abandon a gap walkthrough. These are the same sessions as the web app's gap page, so you can start in one and finish in the other.
- `resolve_gaps`: save your answer for each gap (add a keyword, describe real experience, attach a project, skip, or "can't confirm" so it's never asked again).
- `tailor_session`: turn your answers into a tailored application and show the before/after score. Edits your assistant writes itself must read in first person ("Built X"); a third-person line is refused with an error naming it.
- `quick_tailor`: fill the gaps from your saved quick-tailor profile instead of walking them one by one.
- `tailor_application`: tailor the job's one application from a base resume with the edits your assistant chose. It replaces the draft and takes the new base; status, notes and answers stay, and the old PDF is removed.
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
- `store_qa_answers`, `store_cover_letter`: keep answers or a cover letter your assistant wrote itself, with no AI key in Maestro. The letter replaces the saved one and gets its PDF; both show on the job's Apply step.
- `list_qa_entries`: the answers and cover letters saved so far.

**Proposals and consent** (your yes, or automatic approval while full automation is On)
- `propose_application`, `list_proposals`, `get_proposal`: file a job your assistant found for your review, and read the queue.
- `record_triage`: accept or decline proposals; accepted ones are queued for the next apply run.
- `request_decision`, `record_decision`, `resume_proposal`, `report_failure`: handle proposals that need your input or hit a problem.
- `get_final_review`: everything to check before you approve, including the flagged answers.
- `record_filled_answers`: records what was filled on each form page and where each answer came from; its flags show again in `get_final_review`.
- `record_consent`: record your approve/reject after you answer, or the agent's automatic approval with channel `auto` while full automation is On. Auto approval requires a Queued proposal, final-review evidence, a company off the skip list and a daily-cap slot.
- `get_job_site_login`: the saved job-site email and password, only while full automation is On, for a Queued or approved proposal off the skip list. Each hand-off is audited without the value; the login passes through your agent's AI provider. Use it only for job-site accounts.
- `record_run`: record one finished automation run; it appears under Recent runs on the Automations page.
- `attach_evidence`, `attach_evidence_file`: attach the final-review screenshot and, when using receipt evidence, the submission confirmation.
- `mark_submitted`: mark an approved proposal as submitted with receipt evidence or the user's attestation. While full automation is On, channel `auto` records the agent's word with a note naming what confirmed submission (at least one letter or digit); a receipt is optional. It can also confirm `submission_uncertain`, without another submit click.

**Career KB**
- `get_career_context`, `get_career_export`: your full career record, as structured data or as `career.md`.
- `kb_list_entities`, `kb_get_entity`, `kb_list_points`: browse entries and points, with their IDs.
- `kb_capture`, `kb_add_points`, `kb_ingest_resume`, `kb_sync_base`: add new material as draft points for you to approve. `kb_add_points` takes bullets your assistant already wrote for an entry, with no AI call. `kb_sync_base` keeps a rephrased bullet as a wording of the one it rewrites instead of a new draft.
- `kb_edit_point`, `kb_create_entity`, `kb_edit_entity`, `kb_edit_profile`: correct or add entries.
- `kb_approve_points`: approve or retire points, only after you have approved them.
- `kb_groom_entity`: find similar bullets on one entry, grouped, with one proposed to keep. Reads only, no AI call.
- `kb_combine_points`, `kb_retire_points`: fold similar points into the one you keep, or stop using a stale one, only after you said yes. Resumes keep their text, and `/career` undoes both.
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

HTTP MCP runs inside Maestro's FastAPI backend. Sync tool functions execute on
worker threads and call REST on that same backend, which stores your data and
renders PDFs. Profiles share one registry. The bridge preserves the caller's
`clientInfo`, so Career KB timeline rows keep the agent's name.

```
URL client --------------------HTTP--> /mcp inside FastAPI --> REST --> data + LaTeX/Typst
Claude Desktop --stdio--> Node bridge (.mcpb) or `maestro mcp` --HTTP--^ (same backend port and Host/Origin checks)
```

Contributing and running the tests: see [../../CONTRIBUTING.md](../../CONTRIBUTING.md).

## Troubleshooting

- **"Could not reach the maestro-career-studio backend at …"**: the app isn't
  running, or `BACKEND_URL` points at the wrong address. The message names the
  address the server tried. Check with `docker compose ps` and
  `curl http://localhost:8001/health`.
- **A tool fails with a `422`**: the data your assistant sent didn't match what
  the app expects. The error says what's wrong, so your assistant can fix it and
  retry.
- **The tools don't appear in Claude Code**: `claude mcp get
  maestro-career-studio` shows how it is registered; a `local`-scope entry only
  works in the directory it was added from. Copy the HTTP command from
  **Connect an agent app** and start a new session; approve the server when asked.
- **Tools appear twice, or the model picks the wrong one**: two profiles are
  enabled at once (`full` beside a scoped one). In Claude Code, `claude mcp
  list`, then `claude mcp remove <name>`.
- **A Claude Desktop config edit didn't stick**: the app rewrites
  `claude_desktop_config.json` when it quits. Quit fully (Cmd+Q) before
  editing, or use the extension instead, which Desktop manages itself.
- **It works in Claude Code but not Claude Desktop (or the reverse)**: they are
  set up separately; see [Install](#install).
- **The bundle or plugin cannot connect**: check its Maestro address and the
  backend's `/health`. Docker's host port defaults to 8001; direct uvicorn's
  port may differ. Reinstall an older Docker-based bundle. Container names no
  longer affect the connection.
