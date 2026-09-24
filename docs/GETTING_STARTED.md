# Getting started — from zero to your first tailored PDF

Maestro Career Studio helps you adapt your existing resumes to each job you want to apply for. Save a job posting, compare its requirements with your experience, review suggested changes, and download a resume PDF. Your career record and application tracker are stored on your computer. When you use AI features, resume and job information is sent to the AI service you choose.

Three steps: [install it](#1-what-you-need) → [add your resumes](#3-your-first-tailored-resume) → [save a job and get your tailored resume](#3-your-first-tailored-resume).

**Contents:**
[Words used in this guide](#words-used-in-this-guide) ·
[1. What you need](#1-what-you-need) ·
[2. Install and start the app](#2-install-and-start-the-app) ·
[3. Your first tailored resume](#3-your-first-tailored-resume) ·
[4. The browser extension (optional)](#4-the-browser-extension-optional) ·
[5. Connect your AI assistant (optional)](#5-connect-your-ai-assistant-optional) ·
[6. Where it can go next](#6-where-it-can-go-next) ·
[7. Keeping it up to date](#7-keeping-it-up-to-date)

---

## Words used in this guide

- **Career record (Career KB)** — one organized record of your work, built from your resumes.
- **Base resume** — your main resume for one kind of role (e.g. Data Scientist).
- **Tailoring** — adjusting a base resume to one job, using only things you actually did.
- **Match score** — Maestro's comparison of your resume with a saved job description. It is not an employer's score or a prediction of an interview. The app labels it **ATS score**.
- **AI service** — OpenAI or Gemini, whichever you choose; you add its key in Settings → Models.

The app is the only required part. Two add-ons are optional, and you can add
them at any time: a **browser extension** for saving and filling job pages
([§4](#4-the-browser-extension-optional)), and a connection to your **AI
assistant** ([§5](#5-connect-your-ai-assistant-optional)).

## 1. What you need

- **Docker.** Docker is a free program that runs Maestro in a self-contained
  box on your computer, so you don't install anything else. On macOS or
  Windows install [Docker Desktop](https://docs.docker.com/desktop/); on
  Linux, [Docker Engine + Compose v2](https://docs.docker.com/engine/install/).
  **Start it and leave it running.** Check it works:

  ```bash
  docker info
  ```

  If the output ends without an error, you're fine.
- **Git.** It downloads Maestro, and later its updates. macOS offers to
  install it the first time you run `git` (accept the "command line developer
  tools" prompt). On Windows install
  [Git for Windows](https://git-scm.com/download/win). On Linux, use your
  package manager.
- **Disk space.** About a 1 GB download, which takes roughly 3–4 GB once
  unpacked ([details](../README.md#prerequisites)).
- **An AI key — optional for now.** OpenAI or Gemini (or a local
  OpenAI-compatible server). You add it inside the app after it starts.
  Without one, scoring, PDFs and tracking still work
  ([No-Key Mode](../README.md#do-you-need-an-api-key)).

You do **not** need Python or Node.

## 2. Install and start the app

Open a terminal and run these two commands:

```bash
git clone https://github.com/seinun-ai/maestro-career-studio.git
```

```bash
cd maestro-career-studio && cp .env.example .env && docker compose up -d
```

The first command downloads the project into a folder called
`maestro-career-studio`. **Keep that folder** — your data lives in it, and
updates run from it. The second command starts the app. The first start
downloads about 1 GB, so give it a few minutes.

Then open **<http://localhost:3000>**. The first start sets up your database
and adds a demo resume so you have something to look at.

Don't put your AI key in `.env`. Add it in the app (Settings → Models), which
is step 3 below. A key saved in the app always wins over one in `.env`. Use
`.env` only for a setup with no browser: paste the key after `OPENAI_API_KEY=`
(or `GEMINI_API_KEY=`) and don't also save one in the app.

**Already use a coding agent** (Claude Code, the Codex CLI)? Install Docker
and Git yourself, run the `git clone` command, open the agent in that folder,
and ask: *"Read docs/GETTING_STARTED.md and set Maestro CS up for me — start
it and wait until it is ready."* Adding your AI key in Settings → Models and
loading the browser extension stay your jobs.

Want to build the app from source instead? See [CONTRIBUTING.md](../CONTRIBUTING.md).

### If something goes wrong

| You see | It means | Do |
| --- | --- | --- |
| `Cannot connect to the Docker daemon` | Docker isn't running | Start Docker Desktop, wait until it says running, run the command again |
| `port is already allocated` | Another program uses a port the app needs | Change the `*_HOST_PORT` values in `.env` ([details](../README.md#troubleshooting--common-questions)) |
| The page loads but everything shows errors | The app is still starting | Wait a minute. It is ready when <http://localhost:8001/health> shows `{"status":"ok"}` |
| You added a key to `.env` after starting | Keys are read at start | Run `docker compose restart backend` |
| AI features fail although Settings says "Configured" | An old key is being used | Enter the key again in Settings → Models and press **Test** |

### Your data, backups and starting over

Everything lives inside the project folder: the database is
`data/maestro_cs.sqlite3`, and your PDFs and settings sit in the folders
beside it. **Deleting the project folder deletes your data.** Nothing is kept
anywhere else.

- **Backups.** Every update saves a database backup to `backups/` first. To
  make one yourself, run this from the project folder:

  ```bash
  mkdir -p backups && ( umask 077; docker compose run --rm -T --no-deps backend python -m app.tools.backup_db --stdout | gzip > backups/db-manual.sqlite3.gz )
  ```

- **Start over.** To erase everything — demo data, your data, saved keys —
  run these from the project folder. This cannot be undone.

  ```bash
  docker compose down -v
  rm -rf data/*
  ```

## 3. Your first tailored resume

Five steps from nothing to a PDF:

1. **Import your resumes.** Follow the setup screen, or go to **Career KB**
   and import. You can add up to 10 files at a time (PDF, DOCX, Markdown or
   text). Add old versions too — they all hold useful experience.
2. **Review and approve points in the Career KB.** Imported points arrive as
   drafts. Only *approved* points ever appear on a resume. Merge duplicates
   while you're there.
3. **Add your AI key** — **Settings → Models**. Paste the key under **API
   keys**, then press **Test** next to each model to check it works.
4. **Save a job.** Click **New application** and paste the posting text or
   its URL — or save it from the job page with the
   [browser extension](#4-the-browser-extension-optional). Maestro reads the
   posting and gives it a match score against your resumes.
5. **Tailor and download the PDF.** On the job's **Score & Tailor** tab, each
   gap is a requirement your resume doesn't show yet. Answer its questions
   honestly — new true facts are saved to your Career KB for next time. Every
   AI change is shown for you to accept or undo. Then click **Download PDF**.
   A copy of every PDF is also saved in the `applications/` folder, so you can
   always check what you sent.

**Next:**

- **Fill in your Profile** — contact details, job preferences (roles, level,
  location, work authorization) and the autofill details the extension uses.
- **Build a base resume per kind of role** — Base Resumes → New → **From
  Career KB**, then open its **Health report** and fix what it finds.
- **Pick a default template** on the Templates page. You can switch any time.
- **Use Quick Tailor** once you've done a few jobs by hand — set it up in
  Settings → Quick tailor.
- **Track your applications** — mark them applied and record outcomes. After
  about 10 saved jobs, **Analytics** shows what employers keep asking for.
- **Choose your models** — see
  [choosing models](../README.md#5-choose-your-models-deliberately).

## 4. The browser extension (optional)

A Chrome side panel: save the job posting you're looking at, score your
resumes against it, fill the application form from your autofill details, and
mark it applied — without leaving the tab. The app must be running.

1. Open `chrome://extensions` and switch on **Developer mode** (top right).
2. Click **Load unpacked** and select the `extension` folder inside
   `maestro-career-studio`.
3. Pin the icon, then click it on any job page to open the panel.

There is nothing to set up if you kept the default ports. If you changed the
ports in `.env`, the extension's addresses are set in `extension/sw.js`
(`DEFAULTS`), or can be overridden in the extension's stored settings.

The extension records which form fields it could fill, and keeps that on your
computer. There is no on/off switch in the panel: to turn it off, set
`telemetryEnabled` to `false` in the extension's stored settings
(`chrome.storage.sync`). **Analytics → Autofill coverage → Clear data** deletes
what was collected. Full detail: [`extension/README.md`](../extension/README.md)
and the [README's extension section](../README.md#the-browser-extension).

## 5. Connect your AI assistant (optional)

MCP is a connector that lets Claude, ChatGPT or Codex use the app for you, by
chat instead of clicking. The app must be running (`docker compose up -d`).

It works in the **desktop and command-line apps** — Claude Desktop, Claude
Code, the Codex CLI and the ChatGPT desktop app — not in claude.ai or
chatgpt.com in a web browser.

### Claude

Settings → **Extensions** → **Install Extension**, then select
`maestro-career-studio/mcpb/maestro-career-studio.mcpb` inside your project
folder. Leave the fields as they are. One install covers Claude Desktop and
Claude Code sessions inside the Claude app.

Do **not** use Settings → Connectors → Add custom connector — that is for
online services, and this runs on your computer.

### Codex / ChatGPT desktop

Settings → **Plugins** → **Add** → **Add plugin marketplace**, with:

| field | value |
| --- | --- |
| Source | `seinun-ai/maestro-career-studio` |
| Git ref | `main` |
| Sparse paths | *leave empty* |

Then open the **Maestro Career Studio** entry and press **Install**. From a
terminal instead:

```bash
codex plugin marketplace add seinun-ai/maestro-career-studio
```
```bash
codex plugin add maestro-career-studio@maestro-career-studio
```

A standalone Claude Code CLI uses the same marketplace:
`claude plugin marketplace add https://github.com/seinun-ai/maestro-career-studio`.

### Other apps: the setup script

For Cursor, Windsurf and other apps, run this from the project folder. It
needs **Python 3.12 or newer** on your computer, and prints the settings to
paste into each app:

```bash
./scripts/setup-mcp.sh
```

### If the install did not work: write the config by hand

Both apps read a plain config file, and adding the server there always
works. Use it **instead of** the extension or plugin, never alongside it —
otherwise every tool shows up twice.

<details><summary><b>Claude Desktop</b> — claude_desktop_config.json</summary>

Open the file from **Settings → Developer → Edit Config**. It lives at
`~/Library/Application Support/Claude/claude_desktop_config.json`.

**Fully quit Claude first** (Cmd+Q — closing the window is not enough), or
your edit may be lost. Add to `mcpServers`:

```json
"maestro-career-studio": {
  "command": "docker",
  "args": ["exec", "-i",
           "-e", "BACKEND_URL=http://localhost:8000",
           "-e", "MAESTRO_CS_MCP_PROFILE=full",
           "maestro-career-studio-backend-1",
           "python", "-m", "mcp_server.server"]
}
```

Reopen Claude and check that it is listed under **Settings → Connectors**.

</details>

<details><summary><b>Codex / ChatGPT desktop</b> — ~/.codex/config.toml</summary>

Open the file from **Settings → Configuration → open config.toml** (labels
vary between versions). It lives at `~/.codex/config.toml`. Append:

```toml
[mcp_servers.maestro-career-studio]
command = "docker"
args = ["exec", "-i",
        "-e", "BACKEND_URL=http://localhost:8000",
        "-e", "MAESTRO_CS_MCP_PROFILE=full",
        "maestro-career-studio-backend-1",
        "python", "-m", "mcp_server.server"]
enabled = true
```

Restart the app and check that it is listed under **Settings → MCPs**. You
can also enter the same command and arguments in **MCPs → Connect to a custom
MCP**, type **STDIO**.

</details>

If the tools don't appear, check that the app is running (`docker compose ps`).
Leave the tool profile on `full`. Every tool, the other profiles and more
troubleshooting are in
[`backend/mcp_server/README.md`](../backend/mcp_server/README.md).

## 6. Where it can go next

Once your assistant is connected, it can run the whole loop.
[`docs/skills/`](skills/) has ready-made skills for it:

- **`job-hunt`** — finds recent postings that fit you, saves and scores them,
  and proposes the best ones. You decide in the **Agent inbox**. It can run on
  a daily schedule, and can check the careers pages of companies where you
  have contacts (added under **Referrals**).
- **`apply-session`** — works through the jobs you accepted. It prepares each
  application on its own and asks you only for information the app doesn't
  have, plus one yes per application before the final submit.
- **`customize-job-skills`** — suggests skills from what your agent knows about
  you, then builds your own version with your client's skill creator and
  scheduler.

Nothing is ever submitted without your yes, and everything is written down —
proposals, your yes/no decisions, and evidence.

## 7. Keeping it up to date

From the project folder:

```bash
./scripts/update.sh
```

That is the whole update: it saves a database backup, moves to the newest
release, and waits until the app is ready again. To only check whether
there is anything new, run `./scripts/update.sh --check` — it changes nothing.

- **Your resumes, applications and settings are not touched.**
- **The first start after an update takes longer**, because the database is
  upgraded. The script tells you it is waiting.
- **Two things are manual:** reload the extension at `chrome://extensions`
  (and reload any job tab that was already open), and restart your AI
  assistant app (re-running `./scripts/setup-mcp.sh` if you used it). The
  script reminds you of both.

Updating from an older version? Read [UPDATING.md](UPDATING.md) first. The
[README's Updating section](../README.md#updating) covers the manual steps,
choosing a specific version, and rolling back.
