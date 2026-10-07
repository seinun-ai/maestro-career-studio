# Security Policy

## 1. Supported versions

Maestro CS is developed on `main`. Because it is self-hosted and single-user,
fixes ship to the repository rather than to backported release branches — run the
latest tag or the latest `main` commit.

---

## 2. The threat model, stated plainly

Most arguments about this app's security turn on an unstated premise, so here is
the premise.

**What "local-first, single-user, no authentication" defends against:** a remote
attacker with network access. Nothing listens on a routable interface — every
port Compose publishes binds `127.0.0.1`. There is also no account system to
compromise, no shared tenancy, and no server of ours holding your data.

**What it does not defend against, on its own:** the browser you are already
using, other software on your machine, and text written by other people that the
app is designed to read. Those are the real adversaries for a tool like this, and
they are what the controls in §3 and §4 exist for.

**The asset** is not "a hobby app's database." It is your complete employment
history, contact details, work-authorization answers, optionally your EEO
answers, live API keys, and any saved job-site login. Please treat a compromise
as costing all of that.

### Zero authentication is a real constraint

There is **no authentication or authorization on any HTTP or MCP endpoint.** Any
client that can reach the port can read and write everything. Consequences:

- **Never bind these services to `0.0.0.0`, a LAN interface, or the public
  internet.** If you must reach the app from another machine, put it behind a
  reverse proxy that terminates TLS and enforces authentication itself, and add
  that proxy's hostname to **both** `ALLOWED_HOSTS` and `FRONTEND_ALLOWED_HOSTS`,
  plus its origin to `ALLOWED_WEB_ORIGINS` (§3). All three, or one of the layers
  refuses the traffic.
- **Keep MCP on the STDIO transport.** The HTTP transport means exposing an
  unauthenticated backend holding your full employment history.
- Anything else running as your user on the same machine can reach the API. This
  is inherent to the design, and it is the trade that buys you a tool with no
  cloud account attached.

---

## 3. Controls you should know about

Six controls are the boundary between a zero-auth local API and the browser.
None is optional; if you change one, understand what it was doing.

### Host validation — the DNS-rebinding defence, on **both** servers

Binding to `127.0.0.1` does **not** by itself make a local service private: a
malicious page can point its own domain at `127.0.0.1`, at which point your
browser treats the app as same-origin, CORS is never consulted, and the page can
read every endpoint. Rejecting a `Host` header you do not serve on is what stops
that.

It has to happen on both listening servers. You open the app on Next at :3000,
and Next's `/api` route proxies to the backend while rebuilding the request, so
the backend always sees a trusted `Host` and cannot see the attacker's. The
frontend therefore performs the check first, in `frontend/proxy.ts` and again
inside the `/api` route itself; the backend checks its own `Host` as well.

- `ALLOWED_HOSTS` (backend) — default `localhost,127.0.0.1,backend`.
- `FRONTEND_ALLOWED_HOSTS` (Next) — default `localhost,127.0.0.1,[::1]`.

Add hostnames only when you actually serve on them, and add them to both.

### `ALLOWED_WEB_ORIGINS` — what may RUN, as opposed to what may be READ

CORS is often mistaken for a request filter. It is not one: it decides whether a
page may **read** a response. A form-encoded or multipart `POST` is a "simple
request", which a browser sends cross-origin with no preflight — so against an
API with no authentication the write lands and the browser merely withholds the
reply. Reading the answer was never the attack.

So an `Origin` header that is present and not on the allowlist is refused
outright, before routing. A request with **no** `Origin` is allowed: MCP over
stdio-to-HTTP, `curl`, and the container healthcheck send none, and none of them
is a browser. Browsers are the only clients that attach the header, and they
attach it truthfully.

Default: `http://localhost:3000,http://127.0.0.1:3000`. A host is `studio.lan`;
an origin is `http://studio.lan` — this list and `ALLOWED_HOSTS` move together.

### `MAESTRO_CS_EXTENSION_IDS` — one extension, not all of them

The companion extension calls the API from a `chrome-extension://` origin, and
CORS admits those origins **by exact id**. Set it to the id shown on
`chrome://extensions`; leave it unset and no extension can call the API. Do not
widen this to a pattern — every extension you have installed would then be able
to read your entire career record.

### Template rendering is sandboxed, and the compiler's file access is restricted

Resume templates are Jinja source stored in the database and editable from the
web editor, the chat agent and MCP. They render in a `SandboxedEnvironment`, so a
template body cannot reach Python internals and execute code.

**That sandbox constrains the template language, not the compiler.** Jinja
finishes its work and hands LaTeX to `pdflatex`, and TeX has its own file
primitives: `\input`, `\include` and `\verbatiminput` read whatever the
compiler is allowed to read. `-no-shell-escape` does not touch them — it blocks
`\write18`, which is command execution, a different thing.

The compiler therefore runs under kpathsea's paranoid mode (`openin_any=p`,
`openout_any=p`, with `TEXMFOUTPUT` pinned to the per-render staging directory),
which refuses dotfiles, parent-directory traversal, and absolute paths outside
that directory.

**This bounds the damage; it is not isolation.** A render worker that holds no
secrets, no PII mounts and no network is the real answer, and it is not built
yet — see KNOWN_ISSUES. Until it is: **treat a template from someone else as
untrusted code, and do not render one you have not read.**

### Template ids are slugs, and previews stay in the preview directory

A template's id is also a filename. It is validated (lowercase letters, digits,
hyphen, underscore) in the registry that every surface crosses — REST, chat,
MCP and seeding — rather than at one door, and the preview path is separately
checked to resolve inside the preview directory, so an id like
`../../logs/pwned` is refused whichever surface it arrives through.

### PDF compilation cannot run shell commands

`pdflatex` is always invoked with `-no-shell-escape`, with no opt-out, so no
document — including one built from model-generated text — can use `\write18` to
run host commands.

Additionally: both containers run as a non-root user (`APP_UID`/`APP_GID`) over
the bind-mounted data directories, and Compose sets `no-new-privileges`.

---

## 4. Untrusted input: what the AI reads is data, never instructions

Maestro CS deliberately feeds attacker-authorable text to language models.
Job descriptions you paste or capture, documents you upload, and — in the
agent-driven apply lane — live web pages are all read by a model that holds
tools. **No system can make a model immune to instructions hidden in text it
reads.** We do not claim otherwise, and you should distrust anyone who does.

What we do instead is bound what an injection can reach:

- **Content it can influence** — a bullet, an extracted field, a drafted answer —
  is reviewable and reversible. Chat edits arrive as approval cards, every write
  records a resume version, and nothing is published on your behalf.
- **Privileged actions it must not reach** are cut off structurally, not
  detected: template source cannot execute code (§3), and the deny-list for
  signatures, attestations, consent, credentials and government IDs is consulted
  before a field is ever offered to a model — unless the user has turned on the
  standing agreement permission, which lifts it. The Companion never clicks
  Next or Submit. A connected agent follows the apply policy below.

**What the consent ledger is, precisely.** Approving or submitting a proposal
writes an append-only consent event, approval reserves a slot against a daily
cap you set, and a submit needs either a receipt or an attestation. Outside full
automation, that attestation is the user's own statement. With full automation
On, channel `auto` records the agent's confirmation instead, with a note naming
what confirmed it and containing at least one letter or digit; no receipt is
required, including when reconciling `submission_uncertain`. Never click again
to reconcile an uncertain submit. A company blocked after approval still has
its submit recorded.

It is **not** a channel we control to you. The agent supplies the consent
payload when it calls the tool, so what the ledger records is that *the agent
asserted you said yes*, or supplied its own automatic yes. An agent that has
been successfully prompt-injected can assert either. Automatic approval is
accepted only while full automation is On and only for an `accepted` proposal
(your Queued lane), with `final_review` evidence. It re-checks Companies to skip,
the already-applied guard and the daily cap. The agent's `apply-auto` prompt
judges the clean-review checks; the server does not judge their result. If
anything needs checking, it parks the job through `report_failure` and asks you.
The user's yes then requires final-review evidence and recorded `chat` approval
before one submit. Order, batching and schedule are your strategy with your
agent. These gates control the ledger; the backend cannot prevent a browser
click. Treat the ledger as an audit trail and a rate limit. Keep agent sessions
to hunting and drafting if you do not want them submitting applications.

Full automation is Off by default. Only PUT `/api/settings/full-automation`
with a strict boolean `{value: bool}` changes it; PUT `/api/settings/auto-apply`
preserves the stored switch. Settings › Connected agents asks for confirmation
before turning it On. Turning it Off refuses both channel `auto` and login
hand-offs.

**If you use the agent-driven apply lane, understand its three exposures:**
prompt injection from postings, employers you have not verified receiving your
details, and employers that filter automated submissions. We do not implement
evasion of that filtering. Use the lane on postings you have looked at yourself.

---

## 5. Secrets and personal data on your machine

Runtime state lives in gitignored directories — `settings/`, `base_resumes/`,
`kb_documents/`, `applications/`, `exports/`, `logs/` — plus `.env` and `data/`,
which holds the SQLite database `maestro_cs.sqlite3` and its `-wal`/`-shm`
sidecars (the file is created mode 0600). An install that started on v0.3.0 or
older may also still have its old Postgres volume, a full copy of that data,
until you remove it (docs/UPDATING.md). Never commit any of it.

- **API keys are stored in cleartext** in `.env` and in your local database. The
  HTTP API never returns them (it reports only whether one is configured), but
  anything that can read those files or that database has them. Consider
  `chmod 600 .env`.
- **The job-site login is stored in cleartext** in
  `settings/secrets/job-site-login.json`, mode 0600 in a 0700 directory. It never
  enters the database, exports, telemetry or logs. Writes are serialized and
  replace from a unique 0600 temporary file; damaged JSON or a non-object file
  reads as empty. Settings GET/PUT return only `{email, password_set}`, and
  validation errors never echo credentials. Clear in Settings deletes both.
  MCP `get_job_site_login(proposal_id)` hands `{email, password}` to your agent
  through POST `/api/proposals/{id}/job-site-login`. It requires full automation
  On, a Queued or approved proposal and a company off the skip list; ANY `Origin`
  header is refused, even with the MCP header. `X-Maestro-CS-Origin: mcp` is also
  required; it is provenance, not authentication against local software.
  Each hand-off writes `ConsentEvent(action="login_shared", channel="mcp",
  note=client name)`, never the value. MCP error messages are fixed by status
  and never carry the response body. **The login passes through your agent's AI
  provider. Use it only for job-site accounts.**
- **Your API key is sent to whatever `base_url` you configure.** That is the
  point of a configurable OpenAI-compatible endpoint, and it means the endpoint
  field is a credential-disclosure decision: your key and your prompt bodies
  (resume text, job descriptions) go to that host. Settings warns when the host
  is not local. Only point it somewhere you trust.
- **Langfuse traces contain your prompts**, i.e. your resume text. No Langfuse
  stack ships with this repo; if you enable tracing, point it at an instance you
  control.
- **The LLM call log keeps metadata, not content, by default.** `logs/llm_calls`
  records one file per call — model, attempt, sizes, and a sha256 of the prompt
  and the response — written `0600`. Setting `LLM_LOG_CONTENT=true` adds the
  full text, which means a second permanent copy of your resume and every
  generated answer; the backend warns at startup while it is on. There is not
  yet a rotation policy or an in-app purge: if you enable it, delete the files yourself afterwards.
- The browser extension's telemetry records *which* fields it encountered and
  whether they filled — never a value you typed. The schema has no column for
  one.
- **A second, always-on copy holds your profile.** Only if you set up sync
  ([docs/sync-setup.md](docs/sync-setup.md)). That copy keeps a read-only copy of
  your profile, and it includes your AI key, your EEO answers if you saved
  them, and your job-site login. Treat the machine that holds it like your
  laptop: anything that can read its files or its database has all of that.
  The profile travels only inside an SSH channel you open from the always-on
  machine to the laptop. Nothing in sync logs a key, a login, a bundle or a
  request body. Errors are fixed sentences plus a status code.
  - **The sync endpoints refuse by default.** With no sync key file they answer
    404, for every route. Only the laptop serves data and enrollment routes;
    the always-on backend serves its own local round route.
  - **A browser can never reach them.** Any request with an `Origin` header is
    refused with 403, before the key is read, even with the right key.
  - **Data routes need the key, checked in constant time.** The key is a bearer token
    from a 0600 file in a 0700 folder. A wrong or missing key is a 401 that
    echoes nothing. The key is checked before the version.
  - **They listen on the laptop's loopback only.** The always-on machine
    reaches them through an SSH forward. Restrict that SSH key to one forward
    (`restrict,port-forwarding,permitopen="127.0.0.1:8001"`), and use a private
    network. Never expose the port. Request bodies are capped, a stalled sender
    times out, and one sync request runs at a time.
  - **One writer per job.** The always-on copy cannot change your profile or
    your jobs, and the laptop cannot change a job the bot owns. A write to a
    row the other copy owns is refused at the database flush.
  - **Pairing is an explicit, one-use approval.** Settings › Connected agents ›
    Second copy opens a 10-minute window and creates the laptop's key if needed
    (`POST /api/settings/second-copy`). Stop closes the window. The tunnel-only
    `POST /api/sync/enroll` needs no bearer key during that window, checks the
    protocol and schema, refuses any Origin before reading the key or body, and
    shares the sync lock. Success closes the window and records the time in the
    same transaction. Five closed-window or failed version checks in 10 minutes
    block enrollment for 10 minutes, including after a restart or reopening.
    Only the fixed line “A copy fetched the sync key.” is logged.
  - **A replay after restart is idempotent.** While the laptop process is up, a
    byte-for-byte replay of a sealed request is a bare 404. After a restart the
    in-memory replay cache is empty, so the same bytes are accepted inside the
    5-minute window and change nothing: the handlers are idempotent, and
    `request_apply` dedupes by id.
  - **Setup stays outside `/api/sync/`.** The settings read works without a key
    and creates nothing; only its POST opts in. On the always-on backend,
    `POST /api/sync-setup/enroll` requires a configured loopback tunnel, refuses
    any Origin, bypasses proxies and redirects, and installs the fetched key in
    an exclusive 0600 file in a 0700 directory. It never returns the key to the
    caller. An existing file or symlink is never overwritten. No-key data routes
    remain 404. A local process reaching the restricted tunnel during an open
    window can enroll: the SSH forward and private-network rule are the trust.
    The manual alternative is `sync_key show` in your own terminal and a secure
    transfer into the other key file. Never paste a key into a chat.

---

## 6. Reporting a vulnerability

1. **Do not open a public issue** or discuss it publicly first.
2. Report privately through the repository's **Security → Report a
   vulnerability** (GitHub private vulnerability reporting), or contact the
   maintainers directly.
3. Include impact, reproduction steps, and any mitigation you would suggest.

Findings that are in scope and genuinely useful: anything reachable from a web
page, another extension, a shared template or resume file, a job posting's text,
or a dependency — i.e. anything crossing the boundaries in §2. Reports that the
API has no authentication, or that someone with a shell on your machine can read
your data, are documented design properties rather than vulnerabilities.

Thank you for practising responsible disclosure.
