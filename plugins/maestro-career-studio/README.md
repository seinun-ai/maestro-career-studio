# Maestro Career Studio plugin

Lets your assistant drive [Maestro Career Studio](https://github.com/seinun-ai/maestro-career-studio),
a free, open-source job-application copilot that runs on your own computer.
Your assistant reads a job posting, scores it against your resumes, suggests
tailoring edits, renders the PDF and tracks the application. The app keeps your
data; the plugin is the connector between it and your assistant.

## Before you install

The plugin needs Maestro running on the same computer at
`http://localhost:8001`. It connects to `http://localhost:8001/mcp` and needs
no Docker or Python on the assistant's side. Setup, updating and troubleshooting
are in the
[repository README](https://github.com/seinun-ai/maestro-career-studio#readme).

## Install

For Claude Code, add a local marketplace from a release-tag checkout. Replace
`v0.9.0` with the release you are installing:

```bash
git clone --branch v0.9.0 --depth 1 https://github.com/seinun-ai/maestro-career-studio.git maestro-career-studio-v0.9.0
claude plugin marketplace add ./maestro-career-studio-v0.9.0
claude plugin install maestro-career-studio@maestro-career-studio
```

Claude Code's marketplace-add help accepts local paths and
`--sparse <paths...>`, but shows no Git ref option. The tagged checkout above
pins the release without relying on an undocumented ref syntax.

In the Codex app, choose **Add a marketplace** and enter:

- **Source:** `seinun-ai/maestro-career-studio`
- **Git ref:** the release tag you are installing, for example `v0.9.0`
- **Sparse paths:** `.agents/plugins` and `plugins`

Install **Maestro Career Studio** from that marketplace. Pin the Git ref to
a release tag so updates are deliberate.

The Codex CLI equivalent (replace `v0.9.0` with your release tag) is:

```bash
codex plugin marketplace add seinun-ai/maestro-career-studio --ref v0.9.0 --sparse .agents/plugins --sparse plugins
codex plugin add maestro-career-studio@maestro-career-studio
```

For a direct URL connection in Claude Code or Codex CLI, open Maestro's
Settings › Agent apps › **Connect an agent app**, or run:

```bash
claude mcp add --scope user --transport http maestro-career-studio http://localhost:8001/mcp
codex mcp add maestro-career-studio --url http://localhost:8001/mcp
```

On a uv install (`uv tool install --python 3.12 maestro-career-studio`), `maestro connect`
runs these for you, and `maestro connect claude-desktop` sets up Claude Desktop.

Choose one connection route per client. The Codex plugin's approval prompts
below apply to the plugin route.

## Where it runs

The plugin declares one HTTP MCP connection to your local app. Claude Code
reads [`.mcp.json`](.mcp.json); Codex reads [`.codex-mcp.json`](.codex-mcp.json).
Claude Desktop uses the `.mcpb` bundle: download it from **Connect an agent app**
and double-click it. Other clients are covered in the
[MCP server README](https://github.com/seinun-ai/maestro-career-studio/blob/main/backend/mcp_server/README.md).

## What it runs and what it sends

The plugin connects by URL to `http://localhost:8001/mcp`, served inside
Maestro's backend. It starts no subprocess. Never publish port 8001 or proxy
`/mcp` beyond this computer: the local backend has no authentication.

The Codex plugin asks for approval before these tools:
`mark_submitted`, `record_consent`, `record_decision`, `get_job_site_login`,
`prepare_application_pdf_upload`, `report_failure`, `waive_health_gate`,
`restore_resume_version`, `record_triage`, `kb_approve_points`,
`kb_combine_points`, `kb_retire_points`, and `sync_now`.
These can record a durable decision, waive a health gate, share a login,
stage an upload, replace resume content, or sync data to your paired copy.
The client prompts are
**in addition to Maestro's own consent gates**. Other tools have no per-tool
client prompt in this configuration.

- **The connection stays local.** MCP requests and responses travel between
  your assistant and Maestro's local backend. The plugin has no telemetry,
  accounts or credentials.
- **Tool results go to your assistant.** A tool exists to hand information to
  the assistant that called it: job postings, resume text, your career history
  and saved answers. They are then handled under your assistant provider's
  privacy policy. Voluntary EEO answers are returned only after you turn on the
  standing EEO consent in the app.
- **Your assistant writes, unless you choose Maestro's AI.** By default your
  assistant writes the text over MCP with its own AI, and Maestro's backend
  calls no AI service for its requests. If you pick Maestro's AI in Settings ›
  Agent apps › **Who writes for connected agents**, tools that generate text
  (tailoring, cover letters, screening answers, building your career history,
  health checks) make the backend send resume and job content to the model
  provider you configured in the app (OpenAI or an OpenAI-compatible endpoint,
  Claude, Google Gemini or OpenRouter). The web app and the Companion use that
  provider whatever you pick. With no key at all, the backend calls no AI
  service. A model running on your own computer can be configured but is
  untested. Scoring, PDF rendering and application tracking never call an AI
  service.

The full data-flow detail is in the
[privacy policy](https://github.com/seinun-ai/maestro-career-studio/blob/main/PRIVACY.md).

## Example prompts

- "Here is a job posting: `<paste>`. Save it, score it against my base resumes
  and tell me which skills it asks for that my resume doesn't show."
- "Tailor my `data_scientist` resume to job `<id>`, show me what changed, then
  render the PDF."
- "Add this application to my tracker as Applied, and list everything still
  waiting on a response."
- "Across all the jobs I've saved, which skills keep showing up as gaps?"
  (the explore tools chart skills, roles and scores over time)
- "Turn my career history into a new base resume for ML engineering roles."

The tools cover capturing and scoring jobs, gap analysis and tailoring,
rendering PDFs, tracking applications, reading and editing your career history,
and analytics across your saved jobs.

## Tool profiles

The plugin loads the `full` set (all 92 tools). Smaller sets keep a chat focused,
one job each: `profile` (38 tools), `hunt` (22), `tailor` (31), `apply` (34),
`track` (13), `templates` (13). Choose a tool set in **Connect an agent app**,
or change the URL in your client's declaration to `/mcp/profile`, `/mcp/hunt`, `/mcp/tailor`, `/mcp/apply`,
`/mcp/track` or `/mcp/templates` (`/mcp/career` and `/mcp/explore` still serve `profile` and `track` for one
release). Enable one profile at a time.

## Privacy policy

[PRIVACY.md](https://github.com/seinun-ai/maestro-career-studio/blob/main/PRIVACY.md)
covers what is stored, what leaves your computer, retention and deletion, and
how to reach the author.

## Support

Bugs and questions:
[github.com/seinun-ai/maestro-career-studio/issues](https://github.com/seinun-ai/maestro-career-studio/issues).
Do not post personal data in an issue.

## License

Apache License 2.0. See the
[LICENSE](https://github.com/seinun-ai/maestro-career-studio/blob/main/LICENSE).
