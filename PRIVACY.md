# Privacy Policy

**Effective 2026-10-05 · Maestro Career Studio 0.7.0 and later**

Maestro Career Studio ("Maestro CS") is free, open-source software that you run
on your own computer. It is published by an individual, Ajey Dhayashanker
Loganathan, at
[github.com/seinun-ai/maestro-career-studio](https://github.com/seinun-ai/maestro-career-studio).

**The short version:** there is no Maestro CS server, account, or sign-up, and
the author never receives your data. Your career record lives in files on your
machine. It leaves when you use an AI service, connect an AI assistant, or
submit an application to an employer, going to the recipient you choose.
A model running on your own computer processes it locally.

## What it stores, and where

Almost everything is stored in the folder you cloned, in directories git
ignores. The exceptions are the rendered-PDF folder and the browser output
folder, listed last:

- `data/`: one SQLite database with your career history, jobs, applications,
  resume versions, chat history, saved answers, and settings.
- `base_resumes/`, `applications/`, `kb_documents/`, `exports/`: resume files and
  PDFs, per-application documents, documents you upload, and downloads such as
  `career.md`.
- `settings/`: your profile, persona, and autofill details as text files.
- `settings/secrets/job-site-login.json`: an optional job-site email and
  password, stored in cleartext in a 0600 file inside a 0700 directory. They
  never enter the database, exports, telemetry or application logs. Settings
  returns only `{email, password_set}`; validation errors never echo credentials.
- `logs/`: application logs, plus one small file per AI call (model name, sizes,
  and a hash, **not** the text, unless you set `LLM_LOG_CONTENT=true`).
- `.env`: configuration, including any API keys you put there.
- `.playwright-mcp/`: when an assistant drives a browser through Playwright MCP,
  its output lands here: copies of your resume PDFs staged for upload
  (`uploads/`) and screenshots, which can show application forms with your
  answers filled in.
- A rendered-PDF folder outside the clone, written when an assistant fetches a
  rendered resume over MCP (`get_rendered_pdf`): `$MAESTRO_CS_PDF_DIR` if set,
  otherwise `maestro-cs-pdfs` in your system temp directory.

This includes sensitive information: employment history, contact details,
work-authorization answers, optionally your voluntary EEO (diversity) answers,
and your API keys. **API keys are stored in plain text**, in `.env` and in the
local database. The web API never returns them, but anyone who can read those
files can. See [`SECURITY.md`](SECURITY.md) §5.

There is no login. The app listens only on `127.0.0.1`; do not expose it to a
network.

## What leaves your machine

### AI services you choose

Maestro CS has no AI model of its own. AI features work only after you add a key
or an endpoint; scoring, PDF rendering, and tracking work without one. When you
use an AI feature, the app sends a request to the service you configured:

- **OpenAI**, or any **OpenAI-compatible endpoint** you enter (OpenRouter,
  Ollama, LM Studio, vLLM). The default is `api.openai.com`.
- **Google Gemini** (`generativelanguage.googleapis.com`), if you add a Gemini key.
- **Jev (TypeSafe AI), via OpenRouter** (default `openrouter.ai`), only if you
  add a Jev key and switch the Companion's form filling to it.

What a request contains depends on the feature: resume text, your career
history, job descriptions, your saved answers, what you type to the Assistant,
and page images of scanned documents you upload. For form filling it includes
the form's field labels and answer options. Your voluntary EEO answers are
included only while you have turned on the standing EEO consent. Each request
carries your API key.

**A custom endpoint receives your key and your content.** If its address is not
on your machine, it goes to that host. Settings warns when it isn't local. Point
it only somewhere you trust.

**"Stays on your machine" is true only for a local endpoint.** With a hosted key,
your content goes to that provider, under *its* terms and privacy policy, which
this one does not cover. The author has no access to it.

### Optional Langfuse tracing

Off by default. It turns on only if you set `LANGFUSE_PUBLIC_KEY`,
`LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST` yourself. When on, each traced AI
call sends its full prompt and response, which include your resume and job
text, to the host you named.

### The Chrome extension (the Companion)

You load it from the repository folder; it is not distributed through a store.
It requests access to all websites so it can read job postings and application
forms wherever you use it. The only network address its code contacts is your
own Maestro CS backend (default `http://localhost:8001`): saved job details and
form-filling requests go there, and nothing goes to any other server from the
extension. The AI step of form filling is done by the backend, as above.

It also keeps a usage log in your local database: which kinds of fields it met
(label, field type, outcome, site hostname), never what you typed. It is on by
default. A fill that uses AI also keeps a run trace of how each field was
decided: the page's own option texts and which option was chosen, demographic
(EEO) questions included, never anything you typed or any text from your
profile. The last 50 runs are kept. The same opt-out turns both off, and the
extension README explains how. **Analytics → Autofill coverage → Clear data**
deletes the usage log and the run traces, and leaves only counters that hold
no sites, labels or answers. Withdrawing your EEO consent does not remove
traces already kept; Clear data does. Extension preferences (not career data)
use Chrome's own settings sync.

### Connecting an AI assistant (MCP)

The MCP server, including the `.mcpb` extension for Claude Desktop, runs inside
your local Docker container and talks only to the local backend. The `.mcpb`
shim starts it with `docker exec` and makes no network connections itself.

But an MCP tool exists to hand information to the assistant that called it. Your
career history, job data, resume text, and saved answers can be returned to the
assistant you connected (Claude, Codex, ChatGPT desktop, and so on). From there
the data is processed under **that assistant's provider's privacy policy**
(for Claude, Anthropic's), not this one. Voluntary EEO answers are returned only
with your standing consent. If you use the agent-driven apply lane, the browser
tool your assistant uses is separate software, and an employer receives what
you submit.

Full automation is Off by default in Settings › Connected agents. Turning it
On lets your agent submit queued jobs whose final review is clean without
asking each time, within the daily cap and Companies to skip. Its automatic yes
and its note confirming submission are labelled `auto` in the consent ledger.
The agent checks review eligibility; Maestro records the result and enforces
the approval gates. Jobs with anything to check go to Needs you and the agent
asks you. Order, batching and timing stay between you and your agent.

While full automation is On, MCP `get_job_site_login(proposal_id)` can return
your saved `{email, password}` for a Queued or approved job whose company is
off the skip list. The hand-off refuses browser requests carrying an `Origin`
header and requires the MCP origin header. Each successful hand-off records a
`login_shared` consent event with the proposal, time and client name, never the
value. MCP errors never include the response body. **The login passes through
your agent's AI provider and is processed under that provider's privacy
policy. Use it only for job-site accounts.** Turning full automation Off
refuses later hand-offs and automatic consent; it cannot recall data already
sent to a provider.

### No telemetry from the author

The code contains no analytics, crash-reporting, or advertising service. Maestro
CS does not check for updates or phone home; the version check is local. Updates
happen when you run `scripts/update.sh`, which uses git and Docker to reach
GitHub and the container registry. Fonts are fetched when the web app is built,
and the code editor is bundled, so nothing loads from a CDN at runtime.

One third party to know about: **Next.js**, the web framework, has anonymous
usage telemetry of its own (to Vercel). The frontend Dockerfiles, release and
dev, set `NEXT_TELEMETRY_DISABLED=1`, so it is off in images built from them. If
you run the frontend outside Docker (`npm run dev` or `npm start` on your own
machine), set that variable yourself to opt out.

## Retention and deletion

Your data stays until you remove it; there is no server-side copy.

- Delete records in the app (applications, jobs, chats, saved answers, career
  history items, uploaded documents), or delete the files directly. Deleting
  `data/` removes the whole database. Everything can also be exported to one
  `career.md`.
- Deleting a base resume only hides it; its files stay on disk until you remove
  them. `backups/` copies made by updates, `exports/`, and `logs/` are also yours
  to delete, as are `.playwright-mcp/` and the rendered-PDF folder (which also
  holds page-preview PNGs of the PDFs).
- Removing the folder and its Docker volumes removes the software and its data.
- Data already sent to an AI provider or assistant is kept under that provider's
  policy. Ask them to delete it.
- **Clear** under Job-site login in Settings › Connected agents removes the
  saved email and password file (`DELETE /api/settings/job-site-login`). Turning
  full automation Off keeps the saved login until you clear it.

## Children, sale of data, changes

Maestro CS is not directed at children under 13. The author does not sell, rent,
or share your data, because the author never has it. If this policy changes, the
new text is committed here with a new effective date.

## Contact

Privacy questions: open an issue at
[github.com/seinun-ai/maestro-career-studio/issues](https://github.com/seinun-ai/maestro-career-studio/issues),
and do not post personal data in it. For anything sensitive, use GitHub's
**Security → Report a vulnerability** on the repository, as described in
[`SECURITY.md`](SECURITY.md) §6.
