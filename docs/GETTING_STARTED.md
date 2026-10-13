# Getting started — from zero to your first tailored PDF

Maestro Career Studio helps you adapt your existing resumes to each job you want to apply for. Save a job, compare its requirements with your experience, review suggested changes, and download a resume PDF. Your career history and application tracker are stored on your computer. When you use AI features, resume and job information is sent to the AI service you choose.

Three steps: [install it](#1-what-you-need) → [add your resumes](#3-your-first-tailored-resume) → [save a job and get your tailored resume](#3-your-first-tailored-resume).

**Contents:**
[Words used in this guide](#words-used-in-this-guide) ·
[1. What you need](#1-what-you-need) ·
[2. Install and start the app](#2-install-and-start-the-app) ·
[3. Your first tailored resume](#3-your-first-tailored-resume) ·
[4. The Companion browser extension (optional)](#4-the-companion-browser-extension-optional) ·
[5. Connect your AI assistant (optional)](#5-connect-your-ai-assistant-optional) ·
[6. Where it can go next](#6-where-it-can-go-next) ·
[7. Keeping it up to date](#7-keeping-it-up-to-date)

---

## Words used in this guide

- **Career history** — one organized record of your work, built from your resumes. Each job, project or school in it is an **item**; each line is a **bullet**.
- **Base resume** — your main resume for one kind of role, such as Data Scientist.
- **Tailoring** — adjusting a base resume to one job, using only things you actually did.
- **Match score** — Maestro's comparison of your resume with a saved job description. It is not an employer's score or a prediction of an interview.
- **AI service** — OpenAI, Gemini or Claude (Anthropic), whichever you choose; you add its key in Settings › AI & models.
- **Companion** — the Maestro CS browser extension, a side panel in Chrome.
- **Assistant** — the chat inside the app. **Connected agents** are AI assistants outside it (Claude, Codex, ChatGPT desktop) that use the app over MCP.

The app is the only required part. Two add-ons are optional, and you can add
them at any time: the **Companion**, a browser extension for saving and filling job pages
([§4](#4-the-companion-browser-extension-optional)), and a connection to your **AI
assistant** ([§5](#5-connect-your-ai-assistant-optional)).

## 1. What you need

> **Comfortable in a terminal and want no Docker?** Skip this list and use the
> [uv route](#or-install-with-uv-no-docker-no-git) in step 2. It needs only
> [uv](https://docs.astral.sh/uv/), which installs Python for you.

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
  tools" prompt). On Windows, install it inside WSL
  ([below](#on-windows-use-wsl)). On Linux, use your
  package manager.
- **Disk space.** About a 1 GB download, which takes roughly 3–4 GB once
  unpacked ([details](SETUP_REFERENCE.md#prerequisites)).
- **An AI key — optional for now.** OpenAI, Gemini or Claude (or a local
  OpenAI-compatible server). You add it inside the app after it starts.
  Without one, scoring, PDFs and tracking still work
  ([No-Key Mode](SETUP_REFERENCE.md#do-you-need-an-api-key)).

You do **not** need Python or Node.

### On Windows: use WSL

On Windows, run Maestro from **WSL** (the Linux that ships with Windows).
Every command in this guide then works exactly as written, and your data sits
on a Linux disk, which the app's database needs. Windows is the least-tested
platform so far — if a step here fails,
[open an issue](https://github.com/seinun-ai/maestro-career-studio/issues).

1. **Install Docker Desktop** and leave **Use the WSL 2 based engine** on (the
   default). If you have no WSL yet, open PowerShell as administrator, run
   `wsl --install`, and restart. That installs Ubuntu.
2. In Docker Desktop, open **Settings › Resources › WSL integration** and
   switch on your Ubuntu. That is what makes `docker` work inside WSL.
3. Open **Ubuntu** from the Start menu. **Type every command in this guide
   there**, not in PowerShell or Command Prompt.
4. In that window, install Git with `sudo apt update && sudo apt install git`
   (you don't need Git for Windows), then go to your WSL home with `cd ~` before
   [installing](#2-install-and-start-the-app). **Don't clone into `/mnt/c/...`** (your `C:` drive): the app
   runs slower there, and its database can report `database is locked`.

The app still opens in your normal Windows browser at
<http://localhost:3000>. To see the project folder in File Explorer, go to
`\\wsl.localhost\Ubuntu\home\<your-user>\maestro-career-studio`.

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

Don't put your AI key in `.env`. Add it in the app (Settings › AI & models), which
is step 3 below. A key saved in the app always wins over one in `.env`. Use
`.env` only for a setup with no browser: paste the key after `OPENAI_API_KEY=`
(or `GEMINI_API_KEY=`, `ANTHROPIC_API_KEY=`, `OPENROUTER_API_KEY=`) and don't also save one in the app.

**Already use a coding agent** (Claude Code, the Codex CLI)? Install Docker
and Git yourself, run the `git clone` command, open the agent in that folder,
and ask: *"Read docs/GETTING_STARTED.md and set Maestro CS up for me — start
it and wait until it is ready."* Adding your AI key in Settings › AI & models and
loading the browser extension stay your jobs.

Want to build the app from source instead? See [CONTRIBUTING.md](../CONTRIBUTING.md).

### If something goes wrong

| You see | It means | Do |
| --- | --- | --- |
| `Cannot connect to the Docker daemon` | Docker isn't running | Start Docker Desktop, wait until it says running, run the command again |
| `port is already allocated` | Another program uses a port the app needs | Change the `*_HOST_PORT` values in `.env` ([details](SETUP_REFERENCE.md#troubleshooting--common-questions)) |
| The page loads but everything shows errors | The app is still starting | Wait a minute. It is ready when <http://localhost:8001/health> shows `{"status":"ok"}` |
| You added a key to `.env` after starting | Keys are read at start | Run `docker compose restart backend` |
| AI features fail although Settings says "Configured" | An old key is being used | Enter the key again in Settings › AI & models and press **Test** |

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

### Or install with uv (no Docker, no Git)

uv installs Maestro as a command, and Python 3.12 with it. The package carries the
web app and its own Node, so there is nothing else to install. It runs on macOS,
Linux and Windows (x64), natively; on Windows you do not need WSL for this route.

1. **Install uv, once.** On macOS or Linux:

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

   On Windows, in PowerShell:

   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

   Then **open a new terminal** so the `uv` command is found.
2. **Install Maestro and start it:**

   ```bash
   uv tool install --python 3.12 maestro-career-studio
   maestro start
   ```

   `maestro start` runs Maestro in the background and opens
   **<http://localhost:3000>**. Closing the terminal does not stop it. The first
   start downloads the scoring model (about 100 MB, once) from Hugging Face,
   so give it a minute or two. If the terminal says `maestro` is not found, run
   `uv tool update-shell` and open another new terminal.

   Best effort, untested: on **Windows ARM64** the PDF engine (typst) has no ARM64 wheel, so use
   `uv tool install --python cpython-3.12-windows-x86_64-none maestro-career-studio`
   (x64 Python under emulation). **Alpine and other musl Linux** are not supported; use a glibc distro or Docker.

Then carry on with step 3. The commands you will use:

| Command | What it does |
| --- | --- |
| `maestro status` | Tells you whether Maestro is running and which version (`--offline` skips the check for a newer release) |
| `maestro stop` / `maestro restart` | Stop it; stop and start it again (needed after you edit `maestro.env`) |
| `maestro open` | Opens the app in your browser |
| `maestro logs` | Shows the end of the backend log (`maestro logs web`, `supervisor` or `update` for the others; `-f` follows) |
| `maestro autostart on` | Starts Maestro every time you log in (`off` and `status` too) |
| `maestro backup` | Saves a snapshot of your data now |
| `maestro update` | Saves a snapshot, updates and restarts ([step 7](#7-keeping-it-up-to-date)) |
| `maestro connect` | Adds Maestro to your AI assistant ([step 5](#5-connect-your-ai-assistant-optional)) |

**Your data** sits in one folder, not in a project folder:

| System | Folder |
| --- | --- |
| macOS | `~/Library/Application Support/Maestro Career Studio` |
| Windows | `%APPDATA%\Maestro Career Studio` |
| Linux | `$XDG_DATA_HOME/maestro-career-studio` (default `~/.local/share/maestro-career-studio`) |

It holds the database, your resumes and settings, `backups/`, `logs/` and
`maestro.env`, the one settings file (API keys and, if ever needed, port
overrides; `maestro restart` after editing it). To uninstall, run
`maestro autostart off` and `maestro stop` first (otherwise the login item keeps
retrying a launcher that is gone), then `uv tool uninstall maestro-career-studio`.
That leaves the folder; deleting the folder deletes your data. Add your AI key in the app (Settings › AI & models), as in the
Docker route.

- **Don't run a Docker install and a uv install at the same time.** They are
  separate copies with separate data, and both use ports 8001 and 3000. Coming
  from Docker? `maestro import-docker` moves your data over once
  ([steps](UPDATING.md#move-from-docker-to-the-uv-install)).
- **The Companion needs no changes**: it expects the same ports. Load it from
  the repository's `extension` folder ([step 4](#4-the-companion-browser-extension-optional)).
- **PDFs** render with the Typst engine that ships inside. LaTeX templates need
  TeX on your computer; without it Maestro builds them through Typst and says so.
  TeX Live 2025 needs its pdfTeX update (1.40.28 or later): on 1.40.27 a
  template whose words would print on top of each other is refused. Install
  MacTeX 2026, or update TeX Live 2025 from its final repository:
  `sudo tlmgr option repository https://ftp.math.utah.edu/pub/tex/historic/systems/texlive/2025/tlnet-final && sudo tlmgr update --self --all`
- **Something wrong?** `maestro status` and `maestro logs` come first. A port in
  use is named in the message. `maestro check` prints the install's facts as JSON
  to paste into an issue; it makes no network call.

## 3. Your first tailored resume

Five steps from nothing to a PDF:

1. **Import your resumes.** Follow the setup screen, or go to **Career history**
   and click **Import resumes and documents**. You can add up to 10 files at a time (PDF, DOCX, Markdown or
   text). Add old versions too — they all hold useful experience. Use the **Other documents** tab for
   PowerPoint decks (.pptx), certificates and reports; these add draft bullets to career history.
2. **Review and approve bullets in your career history.** Imported bullets arrive as
   drafts under **Drafts to review**. Only *approved* bullets ever appear on a resume. Merge duplicates
   while you're there.
3. **Add your AI key** — **Settings › AI & models**. Paste the key under **API
   keys**, then press **Test** next to each model to check it works.
4. **Save a job.** Click **Add job**, paste the job description or
   its link, and click **Save job** — or save it from the job page with the
   [Companion](#4-the-companion-browser-extension-optional). Maestro reads the
   job description and gives it a match score against your resumes.
5. **Tailor and download the PDF.** On the job's **Score and tailor** tab, click
   **Analyze gaps**. Each gap is a requirement your resume doesn't show
   yet. Answer its questions honestly — new true facts are saved to your career
   history for next time — then click **Tailor resume**. Every AI change is shown
   for you to accept or undo. On the **Resume** tab, click **Create PDF**, then
   **Download PDF**.
   A copy of every PDF is also saved in the `applications/` folder, so you can
   always check what you sent.

**Next:**

- **Fill in your Profile** — contact details, job preferences (roles, level,
  location, work authorization) under **About you**, and the answers the
  Companion fills in under **Autofill**.
- **Build a base resume per kind of role** — Base resumes › New base resume ›
  **From career history**, then open its **Health report** and fix what it finds.
- **Pick a default template** on the Templates page. You can switch any time.
- **Use Quick tailor** once you've done a few jobs by hand — set it up in
  Settings › Tailoring.
- **Track your applications** — mark them applied and record outcomes. After
  about 10 saved jobs, **Analytics** shows what employers keep asking for.
- **Choose your models** — see
  [choosing models](USING_MAESTRO.md#5-choose-your-models-deliberately).

## 4. The Companion browser extension (optional)

The **Companion** is a Chrome side panel: save the job posting you're looking at, score your
resumes against it, fill the application form from your saved answers (Profile › Autofill), and
mark it applied — without leaving the tab. The app must be running.

1. Open `chrome://extensions` and switch on **Developer mode** (top right).
2. Click **Load unpacked** and select the `extension` folder inside
   `maestro-career-studio`.
3. Pin the icon, then click it on any job page to open the panel.

**On Windows with WSL**, type
`\\wsl.localhost\Ubuntu\home\<your-user>\maestro-career-studio\extension` in the
folder picker's address bar. If Chrome won't load it from there, copy the
folder to your `C:` drive from the Ubuntu window and load the copy instead:
`cp -r extension /mnt/c/Users/<your-windows-user>/maestro-extension`. The copy
doesn't update itself, so repeat that command after every update.

On a uv install there is no project folder, because the package does not carry the
extension: run `maestro --version`, then on GitHub open Releases › that version
(`vX.Y.Z`) › **Source code** and download it. Unpack it and load its `extension`
folder, so the Companion matches the Maestro you run. It then works unchanged
against Maestro on the default ports.

There is nothing to set up if you kept the default ports. If you changed the
ports in `.env`, open `chrome://extensions` → **Details** on the Maestro CS
Companion card → **Extension options**. Set **Backend address** and **App address**,
press **Test connection**, then **Save**. Close and reopen the panel to use them.

The Companion can keep a fill log: which form fields it could fill, kept on
your computer, never what you typed. It is off unless you turn it on in the
same **Extension options** page (**Keep a fill log**). Turn it on if you want
**Analytics → Autofill coverage** to show where autofill misses, or to help fix
it. **Clear data** on that card deletes what was collected. Full detail: [`extension/README.md`](../extension/README.md)
and the [Companion section of Using Maestro CS](USING_MAESTRO.md#the-companion-browser-extension).

## 5. Connect your AI assistant (optional)

MCP lets an AI assistant use Maestro by chat. Keep the app running. HTTP MCP
clients connect to the backend on this computer; claude.ai and chatgpt.com web
connectors are outside this setup.

Open Settings › Connected agents › **Connect an agent app**. Its **Tool set**
selector defaults to `full` (all 88 tools). Choose one set per chat.

### On a uv install: `maestro connect`

If you installed with uv, one command per app does the setup, and it needs
Maestro's folder and nothing else:

```bash
maestro connect                    # lists the apps and which already have Maestro
maestro connect claude-desktop
maestro connect claude-code        # also: codex, cursor, vscode, other
```

`claude-code` and `codex` run that app's own `mcp add` command for you (with
`--scope user` for Claude Code, so Maestro shows up in every folder); `cursor` and
`vscode` open the install link; `other` prints the URL. `claude-desktop` edits
Claude Desktop's settings file with the **full path** to the `maestro` command
(Desktop does not see your terminal's PATH) and keeps a `.bak` copy of the old
file. Desktop rewrites that file while it runs, so if it is open the command waits
in the background and writes after you quit Desktop; `--now` writes at once, and
`--print` shows the entry without changing anything. Add `--profile hunt` (or
`apply`, `explore`, `templates`, `career`) for a smaller tool set. Restart the
app afterwards so it sees the tools.

### Claude Desktop

On a Docker install, download `maestro-career-studio.mcpb` from the card or the
[release](https://github.com/seinun-ai/maestro-career-studio/releases), then
double-click it to install in Claude Desktop. You can also use Settings →
**Extensions** → **Install Extension** and select the downloaded file.

The bundle is a Node stdio-to-HTTP bridge to Maestro on this computer. It needs
no Docker or Python on Claude's side and works on macOS, Windows and Linux.
Leave **Maestro address** at `http://localhost:8001` unless you changed the
backend port. The bundle's **Tool profile** selects the tool set. If you used
the older Docker-based bundle, reinstall this one.

### URL clients: Claude Code, Codex, Cursor and VS Code

The card copies a command for Claude Code or Codex CLI, opens an install link
for Cursor or VS Code, and copies the URL for any other HTTP MCP client. With
the default Docker install, the commands are:

```bash
claude mcp add --scope user --transport http maestro-career-studio http://localhost:8001/mcp
codex mcp add maestro-career-studio --url http://localhost:8001/mcp
```

Use `/mcp` exactly — no trailing slash (`POST /mcp/` redirects with 307).
`--scope user` makes Maestro available in every folder; without it, Claude Code adds it to the current project only.
Scoped tool sets use `/mcp/hunt`, `/mcp/apply`, `/mcp/explore`, `/mcp/templates`
or `/mcp/career`. If you changed the backend port, copy the card's values.

For the Codex app, open **Plugins** › **Add** › **Create custom MCP server**,
choose **Server URL**, paste the URL and set **Authentication** to **No authentication**. Leave
**Tunnel** off: it would share your unauthenticated local Maestro.

For the Codex plugin route, choose **Add a marketplace** with:

| field | value |
| --- | --- |
| Source | `seinun-ai/maestro-career-studio` |
| Git ref | the release tag you are installing, for example `v0.9.0` |
| Sparse paths | `.agents/plugins` and `plugins` |

Install **Maestro Career Studio**. The CLI equivalent is (replace `v0.9.0`
with your release tag):

```bash
codex plugin marketplace add seinun-ai/maestro-career-studio --ref v0.9.0 --sparse .agents/plugins --sparse plugins
codex plugin add maestro-career-studio@maestro-career-studio
```

For a Claude Code plugin install, use the release-tag local checkout in the
[plugin guide](../plugins/maestro-career-studio/README.md#install).
Choose one connection route per client so tools appear once.

**Hand-config fallback.** Codex CLI and the Codex app share
`~/.codex/config.toml`. Append:

```toml
[mcp_servers.maestro-career-studio]
url = "http://localhost:8001/mcp"
enabled = true
```

Claude Code and Cursor use an HTTP entry in their `mcpServers` map:

```json
{
  "mcpServers": {
    "maestro-career-studio": {
      "type": "http",
      "url": "http://localhost:8001/mcp"
    }
  }
}
```

VS Code's `.vscode/mcp.json` uses `servers` instead of `mcpServers`, with the
same `type` and `url`. Claude Desktop uses the bundle above; its manual Node
bridge fallback is in the [MCP guide](../backend/mcp_server/README.md#by-hand).

`/mcp` has no authentication by design: a local process can already reach REST.
It sits behind the same Host/Origin checks as REST. Never publish port 8001 or
proxy `/mcp` beyond this computer.

### Legacy stdio (one release)

Existing stdio connections keep working for one release. If your client only
speaks stdio, use [`scripts/setup-mcp.sh`](../scripts/setup-mcp.sh). The script
and host stdio venv are deprecated and removed in v0.10.0; the
`maestro-career-studio-mcp` entry point remains as a compatibility fallback.

If tools do not appear, check that Maestro is running and that your URL uses
its backend port. Every tool, profile and troubleshooting step is in the
[MCP guide](../backend/mcp_server/README.md).

## 6. Where it can go next

Once your assistant is connected, it can run the whole loop.
[`docs/skills/`](skills/) has ready-made skills for it, and the app's
**Automations** page copies each one as a prompt you paste into Claude
Desktop, Codex or any MCP agent. Your agent asks you when to run it:

- **`job-hunt`** — finds recent postings that fit you, saves and scores them,
  and proposes the best ones. You decide in the **Agent inbox**. It can run on
  a daily schedule, and can check the careers pages of companies where you
  have contacts (added under **Referrals**).
- **`apply-session`** — works through the jobs you accepted. It prepares each
  application on its own and asks you only for information the app doesn't
  have, plus one yes per application before the final submit.
- **`mail-status`** — reads your job email and moves each application to
  applied, interviewing, rejected or offered. It never sends mail.
- **`referral-pages`** — checks your referrals' careers pages for new roles that
  fit you and proposes them.
- **`tailor-run`** — prepares a tailored resume for each queued job, using only
  facts you've already given.
- **`customize-job-skills`** — suggests skills from what your agent knows about
  you, then builds your own version with your client's skill creator and
  scheduler.

Nothing is ever submitted without your yes, and everything is written down —
proposals, your yes/no decisions, and evidence.

To keep that work going while your laptop is off, see
[Run an always-on bot](always-on-bot.md).

## 7. Keeping it up to date

**Installed with uv?** Run `maestro update`. It checks PyPI, shows any breaking
changes from the changelog, saves a snapshot of your data to `backups/` in your
Maestro folder, and only then stops Maestro, updates it and starts it again
(on Windows, quit Claude Desktop first, since it keeps `maestro mcp` running; the update finishes in the background in about a minute: watch
`logs\update.log` in your Maestro folder for `finished`, then run `maestro status`). The reload-the-extension and restart-your-assistant steps below
apply here too. [UPDATING.md](UPDATING.md#updating-a-uv-install) has the detail.

**On Docker**, from the project folder:

```bash
./scripts/update.sh
```

(On Windows, run it in the Ubuntu window.) That is the whole update: it saves
a database backup, moves to the newest release, and waits until the app is
ready again. To only check whether
there is anything new, run `./scripts/update.sh --check` — it changes nothing.

- **Your resumes, applications and settings are not touched.**
- **The first start after an update takes longer**, because the database is
  upgraded. The script tells you it is waiting.
- **Two things are manual:** reload the extension at `chrome://extensions`
  (and reload any job tab that was already open), and restart your AI
  assistant app. If you still use the legacy stdio setup, re-run
  `./scripts/setup-mcp.sh`; URL connections need no setup changes. Reinstall the
  Claude Desktop bundle once if yours is the older Docker-based one. The script
  reminds you of these steps.

Updating from an older version? Read [UPDATING.md](UPDATING.md) first. It covers
the manual steps, choosing a specific version, and rolling back. The README's
[Updating section](../README.md#updating) has the short version.
