# Setup reference

The detail behind the README's Quickstart: the full `maestro` command table and the uv install notes, what the Docker route needs, what an AI key costs and does, running against a local model, where the Docker route keeps your files, and troubleshooting. The two commands that install Maestro are in the [README Quickstart](../README.md#quickstart).

**Contents:**
[The `maestro` command and the uv install](#the-maestro-command-and-the-uv-install) ·
[Prerequisites](#prerequisites) ·
[The Docker route, in full](#the-docker-route-in-full) ·
[Do you need an API key?](#do-you-need-an-api-key) ·
[Local model servers (untested)](#local-model-servers-untested) ·
[Where your files live (Docker)](#where-your-files-live-docker) ·
[Troubleshooting & Common Questions](#troubleshooting--common-questions)

---

## The `maestro` command and the uv install

| Command | What it does |
|---|---|
| `maestro start` | Start Maestro and open the app (`--no-browser`, `--skip-model`) |
| `maestro stop` | Stop it |
| `maestro restart` | Stop, then start (use it after editing `maestro.env`) |
| `maestro status` | Whether it is running, its version and whether a newer one exists (`--offline` skips that check, `--json` for scripts; exit code 3 means stopped) |
| `maestro logs [backend\|web\|supervisor\|update]` | The end of a log (`-n` lines, `-f` to follow) |
| `maestro open` | Open the app in your browser |
| `maestro update` | Save a snapshot of your data, update, restart (`-y` skips the question) |
| `maestro connect [app]` | Add Maestro to Claude Desktop, Claude Code, Codex, Cursor or VS Code |
| `maestro autostart on\|off\|status` | Start Maestro when you log in |
| `maestro backup` | Save a snapshot of your data now (`--out PATH`) |
| `maestro import-docker CHECKOUT` | Move your data from a Docker install into this one, once (`--dry-run` shows the plan; [steps](UPDATING.md#move-from-docker-to-the-uv-install)) |

`maestro migrate`, `maestro check` and `maestro mcp` are for repair and for
agents; `maestro --help` lists everything.

To uninstall, run `maestro autostart off` and `maestro stop` first (otherwise the
login item keeps retrying a launcher that is gone), then
`uv tool uninstall maestro-career-studio`. That leaves your data folder ([where it lives](../README.md#where-your-files-live));
deleting the folder deletes your data.

- **Docker and uv are separate copies.** They keep separate data, and both want
  ports 8001 and 3000, so run one at a time. To bring your Docker data over once,
  stop Docker and run `maestro import-docker` ([steps](UPDATING.md#move-from-docker-to-the-uv-install)).
- **Everything else works as in the Docker route**: add your AI key in
  **Settings › Basics**, load the [Companion](USING_MAESTRO.md#the-companion-browser-extension)
  (it expects the same ports), and run `maestro connect` to
  [connect your agent](USING_MAESTRO.md#driving-it-from-claude-codex-or-chatgpt-mcp).
- **PDFs** render with the Typst engine that ships inside. LaTeX templates need
  TeX on your computer; without it they build through Typst and the app says so.
  TeX Live 2025 needs its pdfTeX update (1.40.28 or later): on 1.40.27 a
  template whose words would print on top of each other is refused. Install
  MacTeX 2026, or update TeX Live 2025 from its final repository:
  `sudo tlmgr option repository https://ftp.math.utah.edu/pub/tex/historic/systems/texlive/2025/tlnet-final && sudo tlmgr update --self --all`
- **Resumes folder:** `maestro` sets `RESUMES_FOLDER_DEFAULT` to
  `Documents/Maestro Career Studio/Applications` (your real Documents folder on
  Windows and Linux) for each run, which is what turns the
  [resumes folder](USING_MAESTRO.md#your-resumes-folder) on. A value in `maestro.env` or your shell
  wins, and a blank one counts as unset. The Docker route sets nothing, so it
  keeps PDFs in `applications/` only.
- **What it contacts, and when:** [PRIVACY.md](../PRIVACY.md#what-the-maestro-command-and-first-start-download).
- **Updating** is `maestro update`; see [Updating](../README.md#updating).

Docker stays the route for contributors and for servers.

---

## Prerequisites

These are for the Docker route below.

- **Docker Desktop** (or Docker Engine + Compose v2). Docker runs the app in a
  self-contained box on your computer, so you don't install anything else.
- **On Windows, WSL.** Install Docker Desktop with its WSL 2 engine, and run
  every command below in the Ubuntu (WSL) window from your WSL home folder —
  [step by step](GETTING_STARTED.md#on-windows-use-wsl).
- **Git** — it downloads the app and, later, its updates (macOS offers to
  install it on first use; on Windows, install it inside WSL with
  `sudo apt install git`).
- **Disk space** — about a 1 GB download, roughly 3–4 GB once unpacked. Most of
  it is the PDF tools and the small scoring model.
- **An AI key — OpenAI, Gemini or Claude; any one is enough.** It powers tailoring,
  cover letters and screening answers, building your career history, the
  Companion's form filling, and the Assistant. Without a key, scoring, PDFs and tracking
  still work — see [Do you need an API key?](#do-you-need-an-api-key)

---

## The Docker route, in full


> **New here?** [`docs/GETTING_STARTED.md`](GETTING_STARTED.md) is the
> step-by-step version — from installing Docker to your first tailored PDF.

The app is the only required piece; the rest are optional and can be added any
time:

| Piece | What it takes |
|---|---|
| **1. The app** | one `docker compose up -d` (below) — runs on your own computer only |
| **2. An AI key** | **Settings › Basics** in the app; OpenAI, Gemini *or* Claude, [any one alone is enough](USING_MAESTRO.md#5-choose-your-models-deliberately) |
| **3. Your AI assistant** | **optional.** Claude: install the `.mcpb` extension from Settings → Extensions. Codex / ChatGPT desktop: add the plugin from Settings → Plugins. [Details](USING_MAESTRO.md#driving-it-from-claude-codex-or-chatgpt-mcp) |
| **4. The Companion (browser extension)** | **optional.** **Add to Chrome** from its [Chrome Web Store page](https://chromewebstore.google.com/detail/maestro-cs-companion/bppkeipififkepldkogmfpkkhoakgndl). From a source checkout: `chrome://extensions` → Developer mode → **Load unpacked** → the repo's `extension/` folder. Nothing to configure — [full steps](../extension/README.md) |

```bash
# 1. Download the project and create your settings file
git clone https://github.com/seinun-ai/maestro-career-studio.git
cd maestro-career-studio
cp .env.example .env

# 2. Start the app (downloads about 1 GB the first time)
docker compose up -d
```

Then open **http://localhost:3000** and add your AI key in **Settings ›
Basics**. The first start sets up your database and adds a demo resume so you
have something to look at.

### Do you need an API key?

**Recommended: yes.** Tailoring, the Companion's form filling, cover letters and
screening answers, building your career history, and the Assistant all use an AI service.

**It costs far less than you'd think — measured, not estimated.** We traced real
applications end to end (Aug 2026) on the default model
([GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna),
$0.20 per million input tokens, $1.20 per million output tokens):

| Step | Cost |
|---|---|
| Reading the job posting | ~¼¢ |
| Finding gaps and questions | ~½¢ |
| Tailoring | ~¼¢ |
| Cover letter + screening answers | ~¼¢ |
| **Save a job → tailored resume → full application package** | **≈1.3¢** |
| Building your career record, per imported resume (once) | ~⅓¢ |

A busy month of applications costs about fifty cents; my whole search so far,
using every feature daily, has cost under **$2**. (The
[Gemini setup](USING_MAESTRO.md#5-choose-your-models-deliberately) is faster and costs under 3¢
per application.)

One cost is not in that table. With full automation on, the Companion's **Think
when stuck** calls your Reasoning model only when an Apply run is stuck on a
page. By default that is your provider's strong model, which costs a few cents
a round; the **Reasoning model** in **Settings › Advanced › Model per job** takes a cheaper one.

**Your key stays with you.** It's stored on your computer and sent only to the
AI service you configured. The app never shows a saved key back; its logs never
record keys, and record your prompts only if you turn that on.

**No key, but you use Claude or Codex?** Connect them over MCP and your
assistant does the AI work itself: it reads the posting and writes the tailoring
edits, and the app applies them with the same honesty checks — no AI key
needed. That is the default even with a key: Settings › Agent apps › **Who
writes for connected agents** switches the writing to Maestro's AI.

**No key at all?** Scoring, gap diagnostics, health reports, manual editing, PDF
creation, application tracking and analytics all work without one. Features that
need AI ask you to add a key instead of failing.

### Local model servers (untested)

You can point the app at a local AI server (Ollama, LM Studio, vLLM) by setting
`OPENAI_BASE_URL` in `.env` (`http://host.docker.internal:<port>/v1` reaches your
computer from inside Docker). **We haven't validated any local model end to end
yet**, and long prompts and strict JSON output are where small models struggle
([`KNOWN_ISSUES.md`](../KNOWN_ISSUES.md) tracks this). If you try it, press **Test**
on each model in **Settings › Advanced › Model per job** and tell us what worked in an issue.

---

## Where your files live (Docker)

On the Docker route, everything stays inside the folder you cloned. (A
[uv install](../README.md#quickstart) keeps the same folders in its per-user
data folder instead.) These are yours, never uploaded, and ignored by git:

- `data/` — the database (`maestro_cs.sqlite3`). Deleting it deletes every
  application, resume version and career-record entry.
- `base_resumes/` — your base resumes and their PDFs (plus one demo resume).
- `applications/` — every application's PDF and source, one folder per company
  and role.
- `settings/` — your profile, persona and autofill details.
- `kb_documents/` — supporting documents you added to your career record.
- `exports/` — downloads such as `career.md`.
- `backups/` — database backups made by updates.
- `logs/` — the app's logs.

The code lives in `backend/` (the server), `frontend/` (the web app) and
`extension/` (the Chrome extension); contributors start at
[`CONTRIBUTING.md`](../CONTRIBUTING.md).

---

## Troubleshooting & Common Questions

**"port is already allocated" when starting:**
Another program is using a port the app needs. Change `FRONTEND_HOST_PORT`
(3000) or `BACKEND_HOST_PORT` (8001) in `.env` and run `docker compose up -d`
again (`lsof -i :<port>` shows what's using it). If you change the backend port,
the Companion needs the new address too — see
[`extension/README.md`](../extension/README.md).

**AI features fail with "401 Unauthorized" or quota errors:**
Check the key in **Settings › Basics** and press **Test**. If you put the key in
`.env` after starting, run `docker compose restart backend`.

**"database is locked":**
The database takes one writer at a time. Usually a program on your computer
opened `data/maestro_cs.sqlite3` while the app was running — stop the app first,
or open a copy from `backups/` instead. It also happens during long writes (like
building your career record); give it a few minutes. On a drive that doesn't
support the default mode (some network drives), set
`SQLITE_JOURNAL_MODE=DELETE` in `.env` and restart.

**PDFs fail to build:**
LaTeX templates need TeX, which the app's Docker image includes. On a uv install
or any backend outside Docker, without TeX, LaTeX templates build through a Typst
template instead and the app says so. A template marked "text overprints" needs
pdfTeX 1.40.28 or later (TeX Live 2025 shipped 1.40.27; a plain `tlmgr update`
refuses because the default repository is now 2026). Install MacTeX 2026, or update TeX Live 2025 from its final repository:
`sudo tlmgr option repository https://ftp.math.utah.edu/pub/tex/historic/systems/texlive/2025/tlnet-final && sudo tlmgr update --self --all`
Then re-validate the template.

**The app came up empty after updating from v0.3.0 or older:**
Your data isn't gone — it's still in the old Postgres volume. See
[Coming from v0.3.0 or older](UPDATING.md#coming-from-v030-or-older).
