# Getting started — from zero to your first tailored PDF

The [README](../README.md) explains *why* Maestro CS works the way it does.
This guide is the *how*: install it, find your way around, and run your first
application through it — in the order that actually works. It assumes no
prior Docker or terminal experience beyond copy-pasting commands.

**Contents:**
[Three pieces, and only the first is required](#0-three-pieces-and-only-the-first-is-required) ·
[Prerequisites](#1-prerequisites) ·
[Install and first boot](#2-install-and-first-boot) ·
[Find your way around](#3-find-your-way-around) ·
[Your first session, in order](#4-your-first-session-in-order) ·
[The browser extension](#5-the-browser-extension) ·
[Drive it from your assistant (MCP)](#6-drive-it-from-your-assistant-mcp) ·
[Where it can go next](#7-where-it-can-go-next) ·
[Keeping it up to date](#8-keeping-it-up-to-date)

---

## 0. Three pieces, and only the first is required

Maestro CS installs in three parts. **Part 1 is the product.** Parts 2 and 3 are
optional add-ons that connect *to* it — take either, both, or neither, now or
later. Neither changes how the app itself works, and neither is a prerequisite
for the other.

| | what it is | what it gives you | required? |
| --- | --- | --- | --- |
| **1. The app** | a Docker stack: web UI, API, database | everything — resumes, tailoring, ATS scoring, PDFs, tracking, at localhost:3000 | **yes** |
| **2. Your assistant** | an MCP server for Claude or Codex | drive all of the above by chat instead of clicking | no |
| **3. The extension** | a Chrome side panel | capture and fill postings in the tab you are already on | no |

If you only ever do Part 1, you have a complete working product.

---

### Part 1 — the app  *(required, ~5 minutes)*

**Prerequisite: Docker, installed and running** ([§1](#1-prerequisites)).
Nothing else — no Python, no Node.

```bash
git clone https://github.com/seinun-ai/maestro-career-studio.git
```

```bash
cd maestro-career-studio && cp .env.example .env && docker compose up -d
```

Open **<http://localhost:3000>**. That is the whole product; [§4](#4-your-first-session-in-order)
walks your first session. Details and troubleshooting: [§2](#2-install-and-first-boot).

---

### Part 2 — your assistant  *(optional, ~1 minute)*

Lets Claude or ChatGPT/Codex operate the app for you. **Requires Part 1 running**,
because the assistant talks to your own backend.

For **Claude Code** or **Codex**, add this repo as a plugin marketplace and
install `maestro-career-studio`. That is the whole setup — no paths to edit and
no host Python, because the server runs inside the container you already started.

**Claude Desktop is a separate surface** and is not covered by that marketplace;
it needs its own entry. Full instructions for every client, including Cursor and
Windsurf: [§6](#6-drive-it-from-your-assistant-mcp).

---

### Part 3 — the extension  *(optional, ~2 minutes)*

A Chrome side panel for saving and filling postings without leaving the tab.
**Requires Part 1 running.** Independent of Part 2 — you can have either without
the other. Steps: [§5](#5-the-browser-extension).

---

### Or let an AI agent do it

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
- **Not needed for most installs: Python.** The app runs in Docker and the
  marketplace plugin runs inside that container. A host **Python 3.12+** is
  required only for the `scripts/setup-mcp.sh` route in [§6](#6-drive-it-from-your-assistant-mcp)
  — a non-Docker backend, a client with no plugin support, or scoped profiles.

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
docker compose up -d
```

That downloads prebuilt images (a few minutes on a normal connection). If you
would rather compile from your own checkout — the contributor path — comment
out `IMAGE_REGISTRY` in `.env` and run `docker compose up -d --build` instead;
that takes longer, because it installs TeX Live and downloads the embedding
model. Either way, then open **http://localhost:3000**.

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

**Part 1 must be running** — the assistant talks to your own backend, so
`docker compose up -d` first. Three routes; pick by client.

### Claude Code and Codex — install the plugin *(recommended)*

```bash
claude plugin marketplace add https://github.com/seinun-ai/maestro-career-studio
```
```bash
claude plugin install maestro-career-studio@maestro-career-studio
```

For Codex, the same two steps with `codex plugin marketplace add
seinun-ai/maestro-career-studio` and `codex plugin add
maestro-career-studio@maestro-career-studio`.

Prefer clicking? Use **Plugins → Add → Add plugin marketplace** in either app and
fill it in exactly like this:

| field | value |
| --- | --- |
| Source | `seinun-ai/maestro-career-studio` |
| Git ref | `main` |
| Sparse paths | *leave empty* |

Then open the **Maestro Career Studio** entry that appears and press **Install**.
Leave sparse paths empty: the marketplace manifests live at the repo root
(`.claude-plugin/` and `.agents/plugins/`) and point at `./plugins/…`, so a
sparse checkout of `plugins/` alone would fetch the plugin but not the manifest
that lists it.

There is nothing to configure afterwards. The plugin runs `docker exec` into the
container Part 1 already started, so there is no host Python to install, no
absolute path to substitute, and the declaration is byte-identical on every
machine. If the tools error, the stack is down — check `docker compose ps`.

### Claude Desktop — add a connector

Claude Desktop is a **separate surface** from Claude Code; a plugin installed in
one gives the other nothing. It has no marketplace, so add it by hand:
**Settings → Connectors → Add custom connector** (older builds: Settings →
Developer), with

| field | value |
| --- | --- |
| Command | `docker` |
| Arguments | `exec -i -e BACKEND_URL=http://localhost:8000 -e MAESTRO_CS_MCP_PROFILE=full maestro-career-studio-backend-1 python -m mcp_server.server` |

That needs no host Python either. If you prefer editing
`claude_desktop_config.json` directly, **fully quit the app first** (Cmd+Q — the
app writes that file too and can discard an edit made while it is open), then
reopen and confirm the server is listed under Connectors.

### Everything else — the setup script

```bash
./scripts/setup-mcp.sh
```

Use this for Cursor, Windsurf and other stdio clients, for a backend you run
outside Docker (`uvicorn`), or for scoped profiles. It builds a host virtualenv
and prints a ready-to-paste block per client, so **this is the one route that
needs a host Python 3.12+**. Useful flags: `--write-desktop-config` (merges into
Claude Desktop, refusing to run while the app is open), `--profile hunt`,
`--print-only`.

### Enable one profile at a time

The server ships six profiles — `full` and five scoped subsets of it. They are
**subsets, not alternatives**, so enabling several at once costs more and buys
nothing:

| enabled | tool schemas | approx. tokens per request |
| --- | --- | --- |
| `full` alone | 83 | ~20,400 |
| `apply` alone | 46 | ~12,200 |
| `hunt` alone | 19 | ~3,400 |
| all six together | 189 | ~44,800 — **2.2x `full`, identical capability** |

Tool definitions are sent with every request, before the model reads your
prompt, so naming a tool in the prompt does not reduce what was loaded. They do
cache across a session, which softens the cost after the first request. The
plugin ships `full` only; scoped profiles come from the setup script or a
hand-written client entry, both of which give you a per-server toggle.

The full reference — every tool, all six profiles, troubleshooting — is
[`backend/mcp_server/README.md`](../backend/mcp_server/README.md).

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
