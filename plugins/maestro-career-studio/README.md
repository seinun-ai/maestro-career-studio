# Maestro Career Studio plugin

Lets Claude drive [Maestro Career Studio](https://github.com/seinun-ai/maestro-career-studio),
a free, open-source job-application copilot that runs on your own computer.
Your assistant reads a job posting, scores it against your resumes, suggests
tailoring edits, renders the PDF and tracks the application. The app keeps your
data; the plugin is the connector between it and your assistant.

## Before you install

The plugin needs the Maestro CS app running on the same computer:

```bash
git clone https://github.com/seinun-ai/maestro-career-studio.git
cd maestro-career-studio && cp .env.example .env
docker compose up -d
```

Docker must be installed and on the `PATH` of the app you use. Setup, updating
and troubleshooting are in the
[repository README](https://github.com/seinun-ai/maestro-career-studio#readme).

## Install

```bash
claude plugin marketplace add https://github.com/seinun-ai/maestro-career-studio
claude plugin install maestro-career-studio@maestro-career-studio
```

## Where it runs

The plugin declares one local (stdio) MCP server. Local MCP servers in plugins
run in **Claude Code** and in **Cowork** sessions that run on your computer. They
do not run in claude.ai chat. The Claude Desktop extension and other clients are
covered in the
[MCP server README](https://github.com/seinun-ai/maestro-career-studio/blob/main/backend/mcp_server/README.md).

## What it runs and what it sends

The plugin runs one command: `docker exec` into the backend container of your
own Maestro CS stack (`maestro-career-studio-backend-1`), which starts the MCP
server (`python -m mcp_server.server`) inside it. The command is in
[`.mcp.json`](.mcp.json). It sets two environment variables, the backend address
(`http://localhost:8000`, inside the container) and the tool profile.

- **The plugin itself sends nothing.** The MCP server talks only to your local
  backend. It makes no other network connection, and the plugin has no
  telemetry, no accounts and no credentials.
- **Tool results go to your assistant.** A tool exists to hand information to
  the assistant that called it: job postings, resume text, your career history
  and saved answers. They are then handled under your assistant provider's
  privacy policy. Voluntary EEO answers are returned only after you turn on the
  standing EEO consent in the app.
- **AI features call the model provider you configured in the app.** Tools that
  generate text (tailoring, cover letters, screening answers, building your
  career history, health checks) make the backend send resume and job content
  to OpenAI or an OpenAI-compatible endpoint, Google Gemini, or, for the
  Companion's form filling, OpenRouter. With no key at all, the backend calls
  no AI service. A model running on your own computer can be configured but is
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

The plugin loads the `full` profile (all 84 tools). Scoped profiles are subsets
that keep a chat focused: `hunt` (19 tools), `apply` (46), `explore` (11),
`templates` (12), `career` (18). To use one, edit `MAESTRO_CS_MCP_PROFILE` in
the plugin's `.mcp.json`, or use the setup script in the repository. Enable one
profile at a time.

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
