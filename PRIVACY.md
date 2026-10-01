# Privacy Policy

**Effective 2026-10-01 · Maestro Career Studio 0.7.0 and later**

Maestro Career Studio ("Maestro CS") is free, open-source software that you run
on your own computer. It is published by an individual, Ajey Dhayashanker
Loganathan, at
[github.com/seinun-ai/maestro-career-studio](https://github.com/seinun-ai/maestro-career-studio).

**The short version:** there is no Maestro CS server, account, or sign-up, and
the author never receives your data. Your career record lives in files on your
machine. It leaves only when *you* configure an AI service and use an AI
feature, and then it goes to *that* service. If you use a model running on your
own computer, it goes nowhere.

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
default. **Analytics → Autofill coverage → Clear data** deletes it, and the
extension README explains how to turn it off. Extension preferences (not career
data) use Chrome's own settings sync.

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
