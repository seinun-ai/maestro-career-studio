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
answers, and live API keys. Please treat a compromise as costing all of that.

### Zero authentication is a real constraint

There is **no authentication or authorization on any HTTP or MCP endpoint.** Any
client that can reach the port can read and write everything. Consequences:

- **Never bind these services to `0.0.0.0`, a LAN interface, or the public
  internet.** If you must reach the app from another machine, put it behind a
  reverse proxy that terminates TLS and enforces authentication itself, and add
  that proxy's hostname to `ALLOWED_HOSTS` (§3).
- **Keep MCP on the STDIO transport.** The HTTP transport means exposing an
  unauthenticated backend holding your full employment history.
- Anything else running as your user on the same machine can reach the API. This
  is inherent to the design, and it is the trade that buys you a tool with no
  cloud account attached.

---

## 3. Controls you should know about

Four controls are the boundary between a zero-auth local API and the browser.
None is optional; if you change one, understand what it was doing.

### `ALLOWED_HOSTS` — the DNS-rebinding defence

The backend rejects any request whose `Host` header is not on this list, before
routing. Binding to `127.0.0.1` does **not** by itself make a local service
private: a malicious page can point its own domain at `127.0.0.1`, at which point
your browser treats the app as same-origin, CORS is never consulted, and the page
can read every endpoint. Host validation is what stops that.

Default: `localhost,127.0.0.1,backend`. Add hostnames only when you actually
serve on them.

### `MAESTRO_CS_EXTENSION_IDS` — one extension, not all of them

The companion extension calls the API from a `chrome-extension://` origin, and
CORS admits those origins **by exact id**. Set it to the id shown on
`chrome://extensions`; leave it unset and no extension can call the API. Do not
widen this to a pattern — every extension you have installed would then be able
to read your entire career record.

### Template rendering is sandboxed

Resume templates are Jinja source stored in the database and editable from the
web editor, the chat agent and MCP. They render in a `SandboxedEnvironment`, so a
template body cannot reach Python internals and execute code. **Treat a template
file from someone else as untrusted input** — the sandbox is what makes importing
one merely unwise rather than dangerous.

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
  before a field is ever offered to a model.

**What the consent ledger is, precisely.** Approving or submitting a proposal
writes an append-only consent event, approval reserves a slot against a daily
cap you set, and a submit needs either a receipt or an explicit attestation —
so a *buggy* agent cannot quietly submit, every action is attributable
afterwards, and the blast radius is bounded by the cap.

It is **not** a channel we control to you. The agent supplies the consent
payload when it calls the tool, so what the ledger records is that *the agent
asserted you said yes*. An agent that has been successfully prompt-injected can
assert that. The real protection is the one you are already exercising: the
apply lane runs only in a live session you are watching, on postings you chose,
with a cap on how many submissions a day are possible at all. Treat the ledger
as an audit trail and a rate limit, not as a lock. If you want a hard gate,
accept proposals in the web UI (`/proposals`) and keep agent sessions to hunting
and drafting.

**If you use the agent-driven apply lane, understand its three exposures:**
prompt injection from postings, employers you have not verified receiving your
details, and employers that filter automated submissions. We do not implement
evasion of that filtering. Use the lane on postings you have looked at yourself.

---

## 5. Secrets and personal data on your machine

Runtime state lives in gitignored directories — `settings/`, `base_resumes/`,
`kb_documents/`, `applications/`, `exports/`, `logs/` — plus `.env` and your
Postgres volume. Never commit any of it.

- **API keys are stored in cleartext** in `.env` and in your local database. The
  HTTP API never returns them (it reports only whether one is configured), but
  anything that can read those files or that database has them. Consider
  `chmod 600 .env`.
- **Your API key is sent to whatever `base_url` you configure.** That is the
  point of a configurable OpenAI-compatible endpoint, and it means the endpoint
  field is a credential-disclosure decision: your key and your prompt bodies
  (resume text, job descriptions) go to that host. Settings warns when the host
  is not local. Only point it somewhere you trust.
- **Langfuse traces contain your prompts**, i.e. your resume text. No Langfuse
  stack ships with this repo; if you enable tracing, point it at an instance you
  control.
- The browser extension's telemetry records *which* fields it encountered and
  whether they filled — never a value you typed. The schema has no column for
  one.

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
