# Privacy Policy

**Effective 2026-10-16 · Maestro Career Studio 0.11.0 and later**

Maestro Career Studio ("Maestro CS") is free, open-source software that you run
on your own computer. It is published by an individual, Ajey Dhayashanker
Loganathan, at
[github.com/seinun-ai/maestro-career-studio](https://github.com/seinun-ai/maestro-career-studio).

**The short version:** there is no Maestro CS server, account, or sign-up, and
the author never receives your data. Your career record lives in files on your
machine. It leaves when you use an AI service, connect an AI assistant, or
fill in and send an application on an employer's site, going to the recipient
you choose. With the Companion's **Apply**, the pages it moves past with Next,
and the job-site login it signs in with, reach that site before you press
Submit.
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

**Installed with uv instead of Docker** (`maestro start`, see the README), the
same folders and files live in one per-user folder instead of a clone:
`~/Library/Application Support/Maestro Career Studio` on macOS,
`%APPDATA%\Maestro Career Studio` on Windows,
`$XDG_DATA_HOME/maestro-career-studio` (default
`~/.local/share/maestro-career-studio`) on Linux. Its `maestro.env` takes the
place of `.env`, and it also holds `backups/` (database snapshots), the scoring
model in `fastembed_cache/`, and small process records in `run/`.

This includes sensitive information: employment history, contact details,
work-authorization answers, optionally your voluntary EEO (diversity) answers,
and your API keys. **API keys are stored in plain text**, in `.env` and in the
local database. The web API never returns them, but anyone who can read those
files can. See [`SECURITY.md`](SECURITY.md) §5.

There is no login. The app listens only on `127.0.0.1`; do not expose it to a
network.

**Optional: a second, always-on copy.** If you set up sync
([`docs/sync-setup.md`](docs/sync-setup.md)), a second Maestro on a machine you
choose holds a read-only copy of your profile. That includes your resumes and
career history, your settings with your AI key, any EEO answers you saved, and
your job-site login. It also holds the jobs, applications and files that copy
owns, and the laptop holds replicas of them. The hosting platform for that
copy already holds this replica. Every sync message is sealed with keys derived
from the sync key, and the key never travels. On the HTTPS route, the
internet, Tailscale's relay and a proxy that decrypts TLS see ciphertext, plus
the path (it names each operation), query strings (the job cursor and the
profile `since`), the plaintext `X-Maestro-Sync` header (protocol, schema
revision, and this copy's machine id), status codes, body sizes and timing.
The profile, the AI key and the job-site password are not in that cleartext.
The pasted code plus a recorded enrollment would let that
platform recover the sync key. That is nothing beyond the key file already in
its sandbox, but the code can outlive the sandbox in a transcript. Prefer
`sync.sh --pair --code -`. If the platform is ever suspect, delete both key
files and pair again. Nothing in a sync message goes to the author or to a
Maestro server. The key, the code and the message bodies are not logged. The agent that runs on
the always-on machine, and its provider, can read what that copy holds, under
that provider's privacy policy. Without a sync key, none of this exists. The
app still listens only on `127.0.0.1`. The one published path is `/api/sync`,
through Tailscale Funnel, as the setup guide describes.

## What leaves your machine

### AI services you choose

Maestro CS has no AI model of its own. AI features work only after you add a key
or an endpoint; scoring, PDF rendering, and tracking work without one. When you
use an AI feature, the app sends a request to the service you configured:

- **OpenAI**, or any **OpenAI-compatible endpoint** you enter (Ollama, LM
  Studio, vLLM). The default is `api.openai.com`.
- **Google Gemini** (`generativelanguage.googleapis.com`), if you add a Gemini key.
- **Anthropic Claude** (`api.anthropic.com`), if you add a Claude key. Your key,
  and Anthropic's retention terms.
- **OpenRouter** (`openrouter.ai`), if you add an OpenRouter key. Maestro asks
  OpenRouter to route only to model providers with zero data retention and no
  data collection. OpenRouter itself may still keep inputs: its
  [privacy policy](https://openrouter.ai/privacy) says inputs containing
  personal data are collected, so a resume sent through OpenRouter reaches
  OpenRouter under its terms.
- **Jev (TypeSafe AI), via OpenRouter** (default `openrouter.ai`), only if you
  add a Jev key and switch the Companion's form filling to it.

What a request contains depends on the feature: resume text, your career
history, job descriptions, your saved answers, what you type to the Assistant,
and page images of scanned documents you upload. For form filling it includes
the form's field labels and answer options. A written question your saved
answers cannot answer is drafted from your career history and the job. When an
Apply run is stuck on a page and **Think when stuck** is on, a snapshot of that
page goes to your Reasoning model: its questions, whether each is filled, the
options, the buttons, the error lines and the site name of a tab the
application opened, with no answer in it. Your voluntary EEO answers are
included only while you have turned on the standing EEO consent. Each request
carries your API key.

**A custom endpoint receives your key and your content.** If its address is not
on your machine, it goes to that host. Settings warns when it isn't local. Point
it only somewhere you trust.

**"Stays on your machine" is true only for a local endpoint.** With a hosted key,
your content goes to that provider, under *its* terms and privacy policy, which
this one does not cover. The author has no access to it.

### What the `maestro` command and first start download

Nothing here is your career data. Each request carries what any web request does
(your IP address, the program's name) and the addresses below, and nothing else.

- **The code** comes from PyPI (`pypi.org`) when you run `uv tool install` or
  `maestro update`; uv also fetches a Python 3.12 build from GitHub if you have none.
  Those downloads are uv's, under its terms.
- **`maestro status`** asks `pypi.org` for the newest version, unless you add
  `--offline`. **`maestro update`** asks `pypi.org` the same way and reads the
  changelog from `raw.githubusercontent.com`. They run only when you run them: no
  background check exists, and the Maestro servers never look for updates.
  Both name each request on screen (`maestro status` says "checked pypi.org").
- **The scoring model** (`BAAI/bge-small-en-v1.5`, about 100 MB) downloads from
  Hugging Face (`huggingface.co`). On a uv install `maestro start` does it once, on
  the first start, into `fastembed_cache/` in your Maestro folder, and says it is
  downloading from Hugging Face; `maestro start --skip-model` leaves it for the first score.
  The Docker backend downloads the same model the first time it scores, into the
  container's temporary folder, so it downloads it again after an update or any
  recreated container. The request names the model; no resume or job text is
  sent, and the scoring itself runs on your computer.

### Exchange rates

To show pay in your home currency, the backend asks the European Central Bank
for its daily euro reference rates
(`www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml`). It asks only when a
page needs the rates and the saved ones are more than a day old, so at most
once a day (after a failed try it waits an hour), and again when you ask for an
update. The request carries what any web request does (your IP address, the
program's name) and nothing about you: no job, no pay, no currency. The rates
are kept in that machine's database, and each copy fetches its own. Offline,
the last rates stay in use; with none yet, pay shows as posted and nothing is
converted.

### Optional Langfuse tracing

Off by default. It requires the optional `tracing` SDK extra (included in the
Docker image and native installs; a uv install and the planned desktop build omit it) and all three settings set by you:
`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST`. Each traced AI
call sends its full prompt and response, which include your resume and job
text, to the host you named.

### The Chrome extension (the Companion)

You load it from the repository folder; it is not distributed through a store.
It requests access to all websites so it can read job postings and application
forms wherever you use it. The only network address its code contacts is your
own Maestro CS backend (default `http://localhost:8001`): saved job details and
form-filling requests go there, and nothing goes to any other server from the
extension. The AI step of form filling is done by the backend, as above.
You set this address in the extension's options; an address off this computer
receives the same saved job details and form-filling data.

It also keeps a usage log in your local database: which kinds of fields it met
(label, field type, outcome, site hostname), never what you typed. It is off
unless you turn it on: the extension's options page has a **Keep a fill log**
switch. A fill that uses AI also keeps a run trace of how each field was
decided: the page's own option texts and which option was chosen, demographic
(EEO) questions included, never anything you typed or any text from your
profile. The last 50 runs are kept. The same switch covers both, and nothing
is recorded while it is off. **Settings → Advanced → Autofill coverage → Clear data**
deletes the usage log and the run traces, and leaves only counters that hold
no sites, labels or answers. Withdrawing your EEO consent does not remove
traces already kept; Clear data does. Extension preferences (not career data)
use Chrome's own settings sync.

With the fill log on, two more things are kept in your local database: each
round of **Think when stuck**, with the page snapshot the model saw, inside
the run traces, and a list of fields the fill could not work (site names and
field shapes, never answers). **Clear data** deletes both.

Some things are kept whether or not the fill log is on:

- **In this browser only:** which clicks and keys worked on each kind of form
  control (at most 200 entries, each dropped after 60 days unused), noted from
  the Companion's own fills and from the gestures you used to fix a field while
  a run waited, never what you typed. **Forget learned widget moves**, in the
  panel's Fill step, clears it. The panel also remembers which job each tab is
  on, in session storage, until you close the tab or the browser.
- **In your backend's memory:** the name of the last job board page you opened
  (never its address), for about 20 minutes. A job you save from an employer's
  page in that time keeps that board's name, for "How did you hear about us?".
- **In your Maestro data:** the answers you type into a page while an Apply
  run waits for you, saved to your profile when you press Resume (with an
  Undo), and a `companion` consent event when the panel marks a job applied
  after it sees the confirmation page of your Submit.

### Connecting an AI assistant (MCP)

The MCP server runs inside your local Maestro backend, reached by default at
`http://localhost:8001/mcp`. Scoped tool sets use `/mcp/<profile>` on that same
backend. The `.mcpb` bundle for Claude Desktop is a bridge that connects only
to the backend address set in the bundle (default `http://localhost:8001`).
Neither the bridge nor an assistant connecting by URL needs Docker on the
assistant's side. On a uv install, `maestro mcp` is the same kind of bridge, and
`maestro connect` only edits the app you name (Claude Desktop's settings file, or
that app's own `mcp add`), pointing it at your local address.

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

The same switch turns on the Companion's **Apply**. Apply fills each page,
presses Next, and on known application sites signs in or makes an account
with your saved job-site login. It never presses Submit.

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

The Companion has its own route for the same login (`POST
/api/companion/job-site-login`, admitted only for the Companion extension's
origin, same gates, recorded as a `login_shared` event on the `companion`
channel). The Companion types it into the sign-in page itself, only on a known
application site and only in the page's top frame, and sends it to no AI
provider: it never reaches a model, a run record, a receipt, a trace or the fill
log.

### No telemetry from the author

The code contains no analytics, crash-reporting, or advertising service. Maestro
CS does not phone home, and the servers never check for updates. Updates happen
when you run `scripts/update.sh` (it uses git and Docker to reach GitHub and the
container registry) or `maestro update` (it reaches PyPI and GitHub, as listed
[above](#what-the-maestro-command-and-first-start-download)). Fonts are fetched
when the web app is built, and the code editor is bundled, so nothing loads from
a CDN at runtime.

One third party to know about: **Next.js**, the web framework, has anonymous
usage telemetry of its own (to Vercel). The frontend Dockerfiles, release and
dev, set `NEXT_TELEMETRY_DISABLED=1`, so it is off in images built from them, and
the uv install sets it for its web server. If you run the frontend outside Docker
and the uv install (`npm run dev` or `npm start` on your own machine), set that
variable yourself to opt out.

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
  On a uv install, run `maestro autostart off` and `maestro stop`, then
  `uv tool uninstall maestro-career-studio`: that removes the software and leaves
  your Maestro folder; deleting that folder removes the data.
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
