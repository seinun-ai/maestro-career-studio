# Getting started — from zero to your first tailored PDF

The [README](../README.md) explains *why* Maestro CS works the way it does.
This guide is the *how*: install it, find your way around, and run your first
application through it — in the order that actually works. It assumes no
prior Docker or terminal experience beyond copy-pasting commands.

**Contents:**
[The fastest path: let an AI agent set it up](#0-the-fastest-path-let-an-ai-agent-set-it-up) ·
[Prerequisites](#1-prerequisites) ·
[Install and first boot](#2-install-and-first-boot) ·
[Find your way around](#3-find-your-way-around) ·
[Your first session, in order](#4-your-first-session-in-order) ·
[The browser extension](#5-the-browser-extension) ·
[Drive it from your assistant (MCP)](#6-drive-it-from-your-assistant-mcp) ·
[Where it can go next](#7-where-it-can-go-next) ·
[Keeping it up to date](#8-keeping-it-up-to-date)

---

## 0. The fastest path: let an AI agent set it up

If you use a coding agent or AI IDE (Claude Code, Codex CLI, Cursor, …), you
can skip most of this guide's mechanics: open a session and paste something
like —

> Clone https://github.com/seinun-ai/maestro-career-studio, check that the
> prerequisites in docs/GETTING_STARTED.md are present on this machine, set
> up the `.env`, and start the stack with docker compose. Then tell me what
> still needs me.

— and later, from a session opened inside the cloned repo:

> Set up this repo's MCP server for my assistant. Run ./scripts/setup-mcp.sh
> and apply its output; docs/GETTING_STARTED.md §6 has the per-client paths.

Two things an agent cannot do for you: **install and start Docker Desktop**
(it needs an admin password and a GUI first-run), and **decide where your
API key goes** (§2). Everything else — cloning, `.env`, compose, the MCP
config — an agent handles, and the repo's own scripts cooperate with it.

---

## 1. Prerequisites

- **Docker.** On macOS or Windows install
  [Docker Desktop](https://docs.docker.com/desktop/); on Linux,
  [Docker Engine + Compose v2](https://docs.docker.com/engine/install/).
  Then **start it and leave it running** — the single most common first-run
  error, `Cannot connect to the Docker daemon`, just means Docker Desktop
  isn't running. Verify with:

  ```bash
  docker info
  ```

  (Any output ending without an error means you're fine.)
- **~4 GB of disk** for the three images (see the README's
  [Prerequisites](../README.md#prerequisites) for the breakdown).
- **An LLM API key — optional at this point.** OpenAI or Gemini, or a local
  OpenAI-compatible server. The place to add it is **inside the app**
  (Settings → Models, after first boot) — and without one, the deterministic
  core (ATS scoring, PDF rendering, tracking) works fully in
  [No-Key Mode](../README.md#try-it-before-you-bring-a-key-no-key-mode).
- **For the MCP server only** (§6): a host **Python 3.12+**. Not needed for
  the app itself.

## 2. Install and first boot

```bash
git clone https://github.com/seinun-ai/maestro-career-studio.git
cd maestro-career-studio
cp .env.example .env
```

Don't put your API key here yet — the recommended place is **Settings →
Models inside the app**, after first boot (step 4 of §4). Adding it there
keeps one source of truth: a key saved in the app **always wins** over one
in `.env`, so mixing the two is how you end up staring at a stale key you
forgot about. `.env` keys exist for the cases that need them — headless
setups, or a fully scripted install — and if that's you, paste it after
`OPENAI_API_KEY=` (or `GEMINI_API_KEY=`) now and then *don't* also save one
in Settings.

```bash
docker compose up -d --build
```

The first build takes several minutes (it installs TeX Live and downloads
the embedding model — one-time). Then open **http://localhost:3000**.

First boot starts PostgreSQL on port 55432, runs migrations, seeds a demo
resume with rendered previews, and — if a key is present — builds a demo
Career KB from it.

### If something goes wrong

| You see | It means | Do |
| --- | --- | --- |
| `Cannot connect to the Docker daemon` | Docker isn't running | Start Docker Desktop, wait for "running", re-run the command |
| `port is already allocated` | Another app owns 3000/8001/55432 | Change `*_HOST_PORT` in `.env` ([details](../README.md#troubleshooting--common-questions)) |
| Build sits at TeX Live / model download | Normal on first build | Wait it out; later builds are fast |
| Page loads but everything errors | Backend still starting | `curl -s localhost:8001/health` answers `{"status":"ok"}` when it's ready (also at `/api/health`); `docker compose ps` shows it `Up` — only postgres reports `healthy` |
| Added a key to `.env` after starting | Keys are read at process start | `docker compose restart backend` — and remember a key saved in Settings overrides `.env` |
| LLM calls fail 401 though Settings says "Configured" | A stale key — the label says where it lives (in-app beats `.env`) | Re-enter the key in Settings → Models and press **Test** |

### Starting over (a genuinely clean slate)

Deleting the project folder does **not** delete your data — and neither does
`docker compose down` or removing containers. The database lives in a Docker
**volume** stored inside Docker itself, named after the project folder
(`maestro-career-studio_pgdata`). Two consequences worth knowing before they
surprise you:

- **A re-clone into a folder with the same name re-attaches the old
  database.** Your resumes, applications, and even a saved API key are back —
  which is the right default (an update or an accidental folder deletion
  never costs you data), but it means "delete the folder and clone again" is
  *not* a fresh install. To test a truly fresh one, clone into a differently
  named folder.
- **Deleting only the folder leaves the two halves of your state out of
  sync**: the database survives, but the rendered PDFs that lived under
  `applications/` and `base_resumes/` in the folder are gone, so the app may
  list documents whose files no longer exist. Re-render them from the UI —
  the content itself is safe in the database.

When you *want* everything gone — demo data, your data, stored keys, all of
it — this is the one command, run from the project folder, and it is not
undoable:

```bash
docker compose down -v
```

## 3. Find your way around

The sidebar, top to bottom:

- **New application** — capture a job and start tailoring against it.
- **Applications** — every job you've captured, from saved to signed.
- **Agent Proposals** — the triage inbox for agent-hunted jobs (§7).
- **Referrals** — contacts and their company careers pages.
- **Career KB** — your evidence: work history as approved, reusable points.
- **Base Resumes** — one resume per career track, composed from the KB.
- **Templates** — the LaTeX/Typst designs your PDFs render through.
- **Chat** — the scoped in-app assistant (pin a resume, section, or bullet).
- **Analytics** — what the market you're applying into keeps asking for.
- **Profile** — persona, job preferences, and your autofill contact details.
- **Settings** — models and API keys, prompts, quick-tailor defaults,
  hunt caps, appearance.

## 4. Your first session, in order

The order matters: everything downstream composes from the Career KB, so
feed it first and the rest gets easier.

1. **Import every resume you have.** The onboarding flow (or Career KB →
   import) takes up to 10 files per batch. Old versions, role-specific
   variants, the too-long one — they all carry evidence.
2. **Approve the KB inbox.** Imported points arrive as drafts; only
   *approved* points ever land on a resume. Merge the duplicates once and
   every future application benefits.
3. **Fill in your Profile.** Contact details, persona, **job preferences**
   (roles, seniority, location, work authorization — these drive scoring
   warnings and agent hunts), and the autofill profile the extension uses.
4. **Add your API key and pick models** — Settings → Models, if you didn't
   put a key in `.env`. Press **Test** on each model: it measures what the
   model can actually do before you depend on it.
5. **Pick a default template** on the Templates page. Every render uses it
   unless a resume overrides it; you can switch any time without touching
   content.
6. **Build a base resume per career track** — Base Resumes → New →
   **From Career KB**. Then open it and run the **Health check**: it's the
   job-independent gate, and fixing its findings now beats fixing them
   after every tailoring run.
7. **Capture a job** — New application, paste the posting text or URL (or
   use the extension, §5). Extraction structures it; the deterministic ATS
   engine scores it against every base.
8. **Tailor through the gap workflow** — Score & Tailor tab. Each gap names
   a requirement your resume doesn't evidence; answer the questions honestly
   and true-but-unwritten material becomes permanent KB evidence. Every AI
   edit lands as a reviewable, revertible diff — read it.
9. **Set quick-tailor preferences** (Settings → Quick Tailor) once you've
   done a few manual passes — then **Quick Tailor** handles the
   already-know-the-answer cases in one step.
10. **Generate the package and read it** — cover letter, screening answers,
    the rendered PDF. Every render is also filed on disk under
    `applications/` in a company-and-role-named folder, so you can always
    verify exactly what you sent.
11. **Track it** — mark applied, record outcomes. **Analytics** starts
    paying off after ~10 captured jobs: *Gaps & growth* shows what the
    market keeps asking that you're not showing, and *Resume fit* shows
    whether tailoring is actually lifting your scores.

## 5. The browser extension

The companion extension is a **side panel**: save the posting in front of
you, score your bases against it, fill the application form from your
autofill profile, and mark it applied — without leaving the tab.

1. Open `chrome://extensions`, switch on **Developer mode** (top right).
2. **Load unpacked** → select the repo's `extension/` folder.
3. Pin the icon; click it on any job page to open the panel.

If you changed the app's ports in `.env`, set the backend/app URLs under the
panel's `⋯` menu. What its telemetry does and doesn't store is in the
[README's extension section](../README.md#the-browser-extension);
[`extension/README.md`](../extension/README.md) has the full reference.

## 6. Drive it from your assistant (MCP)

With the backend running, one command prepares everything:

```bash
./scripts/setup-mcp.sh
```

Then per client:

- **Claude Code** — nothing more to do for sessions opened in this repo:
  the script writes a repo-level `.mcp.json`, and the session offers the
  server automatically (approve when prompted). For sessions elsewhere, the
  script registers user-wide too (or prints the command to run).
- **Claude Desktop** — **quit the app first (Cmd+Q)**, then Settings →
  **Developer** → **Edit Config** opens `claude_desktop_config.json`; paste
  the block the script printed into `mcpServers`, save, reopen the app.
  (Quit-first matters: the running app rewrites that file on exit and will
  silently drop your edit.)
- **ChatGPT desktop app / Codex CLI** — both read `~/.codex/config.toml`;
  append the TOML block the script printed and restart the app.

No further installation is needed beyond what the script already did — the
venv it created *is* the server. The full reference (profiles, every tool,
troubleshooting) is [`backend/mcp_server/README.md`](../backend/mcp_server/README.md).

## 7. Where it can go next

Once the MCP server is registered, your assistant can run the whole loop —
and [`docs/agent-prompts/`](agent-prompts/) ships the author's own prompts
as adaptable starting points:

- **A scheduled daily hunt** — capture, score, and propose only; you triage
  the results on Agent Proposals. Works as a Claude Code routine or any
  client's scheduled task.
- **Referral-first hunting** — add contacts and their company careers pages
  under **Referrals**, then point a hunt at those URLs specifically: a
  browser-capable agent (Claude in Chrome, a Playwright-equipped session)
  reads the pages you would have read and captures what fits.
- **Attended apply runs** — working the accepted-proposal queue with a
  browser, one consent per application, always stopping before submit.

Whatever the agent does, the consent posture holds: nothing is ever
submitted without your explicit per-application yes, and everything is
written down — proposals, consent events, evidence.

## 8. Keeping it up to date

From the folder you cloned:

```bash
./scripts/update.sh
```

That is the whole update. It takes a database backup, moves your checkout to
the newest released version, brings the images to that same version, and
waits until the stack is healthy again. Run `./scripts/update.sh --check`
first if you only want to know whether there is anything new — it changes
nothing.

Three things worth knowing before your first update:

- **Your data is not involved.** Your resumes, applications, KB documents and
  settings are files on disk that no update step touches, and the database
  lives in a Docker volume that survives everything here — including folder
  deletion and re-cloning (see
  [Starting over](#starting-over-a-genuinely-clean-slate) for when that
  persistence surprises you). The backup the script takes guards the
  database *migration* specifically.
- **Migrations run themselves** when the backend starts, so the first boot
  after an update takes longer than usual. The script tells you it is waiting.
- **Two things stay manual**, because Docker cannot reach them: reload the
  extension at `chrome://extensions` (and reload any job tab that was already
  open), and restart your MCP client, re-running `./scripts/setup-mcp.sh`.
  The script prints both reminders when it finishes.

The [README's Updating section](../README.md#updating) has the rest: the
manual command-by-command equivalent, how to pin a specific version, and the
rollback recipe.
