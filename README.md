<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/brand/maestro_lockup_dark.svg">
    <img src="docs/assets/brand/maestro_lockup_light.svg" alt="Maestro Career Studio" width="460">
  </picture>
</p>

<p align="center">
  <a href="https://github.com/seinun-ai/maestro-career-studio/actions/workflows/ci.yml"><img src="https://github.com/seinun-ai/maestro-career-studio/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/seinun-ai/maestro-career-studio/actions/workflows/codeql.yml"><img src="https://github.com/seinun-ai/maestro-career-studio/actions/workflows/codeql.yml/badge.svg" alt="CodeQL"></a>
  <a href="https://github.com/seinun-ai/maestro-career-studio/actions/workflows/ci.yml"><img src="https://img.shields.io/badge/tests-4%2C922%20passing-brightgreen" alt="Tests"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="License"></a>
  <a href="https://maestrocareerstudio.com"><img src="https://img.shields.io/badge/site-maestrocareerstudio.com-1a3a5c" alt="Project site"></a>
  <a href="https://github.com/seinun-ai/maestro-career-studio/pkgs/container/maestro-career-studio-backend"><img src="https://img.shields.io/badge/ghcr.io-multi--arch-blue" alt="Container images"></a>
</p>
<!-- The ghcr badge went up with v0.1.1, once both packages were public — a
     badge for a private package renders as a broken promise. It and the static
     test-count badge are refreshed from the release checklist in
     docs/RELEASING.md; edit them there, not here. -->

**Maestro Career Studio helps you adapt your existing resumes to each job you
want to apply for.** Save a job posting, compare its requirements with your
experience, review suggested changes, and download a resume PDF. Your career
record and application tracker are stored on your computer. When you use AI
features, resume and job information is sent to the AI service you choose.

**Get started:** [install it](#quickstart) → add your resumes → save a job and
get your tailored resume. New to this? The
[Getting Started guide](docs/GETTING_STARTED.md) walks you through every step.

<!-- P4 hero.gif — CLEARED for publish 2026-08-20. Recorded on the mock instance:
     contact header scrubbed (ajey@seinun.com, placeholder phone), lift
     49.2 -> 70.8 is a real deterministic score. Two items reviewed and
     accepted by the owner rather than fixed: the real Visa posting stays (an
     employer-published public document), and the "Liberty Hill, TX" experience
     location stays (already the contact city on the public resume).
     1000px / 10fps / 64 colors, 1.8 MB; re-encode any replacement to match. -->

![Score, tailor, see every AI edit, download the PDF — end to end](docs/assets/hero.gif)

**Works with Claude, Codex or the ChatGPT desktop app** (83 tools) ·
**bring your own AI key** — OpenAI or Gemini; scoring, PDFs and tracking work
without one · **runs on your computer, no account** · **take everything with
you** — your whole record exports to one `career.md` file

> **Made for one person on one computer.** There is no login: anything that can
> reach the app can read and change your whole career record and your saved API
> keys. Out of the box it only listens on your own machine (`127.0.0.1`), so
> that's safe. **Never expose it to a network** — not the internet, your home
> network, or a tunnel. [`SECURITY.md`](SECURITY.md) has the details.

**Contents:** [Why Maestro CS?](#why-maestro-cs) ·
[Prerequisites](#prerequisites) · [Quickstart](#quickstart) ·
[Updating](#updating) ·
[Using it well](#using-it-well) ·
[Driving it from Claude, Codex, or ChatGPT (MCP)](#driving-it-from-claude-codex-or-chatgpt-mcp) ·
[The rest of the toolkit](#the-rest-of-the-toolkit) ·
[Where your files live](#where-your-files-live) ·
[Community & contributing](#community-documentation--contributing) ·
[Licensing](#licensing) ·
[Troubleshooting](#troubleshooting--common-questions)

---

## Why Maestro CS?

**Your time belongs in your career, not in the paperwork around it.** Most of a
job search goes into documents thrown away a week later: a resume rebuilt for
each role, a cover letter written again from memory, the same "tell us about a
time you…" answered for the fourth time. Here you record what you actually did
once, and every document after that is assembled from that record.

**It never writes things you didn't do.** Your work goes into one **career
record** (the Career KB). Resumes are built from the points you approved, word
for word; rewording a bullet is a separate step that asks you first. When a job
asks for something your resume doesn't show, Maestro asks you about it — if it's
true, it's saved for every future application; if not, it stays a gap. Every
change is saved as a **resume version**, so you can always compare or go back.

**Real, professional PDFs without the formatting headache.** You edit content in
a simple editor — a bullet is a bullet — and a template handles the layout, so
changing a word can never break the formatting. Switch templates any time
without touching your content, or bring your own design.

**Nothing here is rented.** Free and open source (Apache 2.0), no account, no
subscription. Use the AI service you choose and pay only for what you use —
about a penny per application.

### How it works

- **Your career record.** Upload every resume version you have. Maestro merges
  them into one record of your jobs, projects and skills, removing duplicates.
  Bullets taken unchanged from your files are approved automatically; anything
  merged or written by AI waits for your review.
- **The match score.** Maestro compares your resume with a saved job using
  fixed scoring rules plus a small model that runs on your computer — no AI
  service is involved, so the same resume and job always get the same 0–100
  score. It is **not** an employer's score or a prediction of an interview; use
  it to compare your own drafts and catch gaps. One thing moves over time:
  recent experience counts more, so a score can shift slightly as months pass
  ([`KNOWN_ISSUES.md`](KNOWN_ISSUES.md)).
- **Tailoring.** Suggested changes arrive as a before/after view you accept or
  undo, one by one.
- **PDFs.** Built on your computer with LaTeX or Typst, two professional
  typesetting systems.

### How it compares

Only claims you can check yourself (as of August 2026 — tell us if a row has
gone stale):

| | Typical AI resume builders | CLI skill frameworks (e.g. career-ops) | **Maestro CS** |
|---|---|---|---|
| Match scoring | An AI guesses — same input, different score each run | AI judgment | **Fixed rules — same input, same score, every time** |
| Shows whether tailoring helped | Static score only | Not measured | **Score before and after, per application** |
| See what the AI changed | No history | No | **Every change shown, undoable** |
| PDF output | House web templates | HTML → PDF | **LaTeX and Typst, bring your own template** |
| Career record | None (per document) | Plain markdown/YAML files | **Organized, versioned — exports to one `career.md`** |
| Works with AI assistants | No | Command-line skill files | **83 tools for Claude, Codex, ChatGPT desktop — on your own computer** |
| Submits applications for you | N/A | Never (stated) | **Never without your yes, per application** |
| Cost | $15–75/month | Free + AI usage | **Free (Apache 2.0) + your own AI usage — [≈1¢ per application](#do-you-need-an-api-key)** |

---

## Prerequisites

- **Docker Desktop** (or Docker Engine + Compose v2). Docker runs the app in a
  self-contained box on your computer, so you don't install anything else.
- **Git** — it downloads the app and, later, its updates (macOS offers to
  install it on first use; Windows takes
  [Git for Windows](https://git-scm.com/download/win)).
- **Disk space** — about a 1 GB download, roughly 3–4 GB once unpacked. Most of
  it is the PDF tools and the small scoring model.
- **An AI key — OpenAI or Gemini; either one is enough.** It powers tailoring,
  cover letters and screening answers, building your career record, the
  extension's form filling, and chat. Without a key, scoring, PDFs and tracking
  still work — see [Do you need an API key?](#do-you-need-an-api-key)

---

## Quickstart

> **New here?** [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md) is the
> step-by-step version — from installing Docker to your first tailored PDF.

The app is the only required piece; the rest are optional and can be added any
time:

| Piece | What it takes |
|---|---|
| **1. The app** | one `docker compose up -d` (below) — runs on your own computer only |
| **2. An AI key** | **Settings → Models** in the app; OpenAI *or* Gemini, [either alone is enough](#5-choose-your-models-deliberately) |
| **3. Your AI assistant** | **optional.** Claude: install the `.mcpb` extension from Settings → Extensions. Codex / ChatGPT desktop: add the plugin from Settings → Plugins. [Details](#driving-it-from-claude-codex-or-chatgpt-mcp) |
| **4. The browser extension** | **optional.** `chrome://extensions` → Developer mode → **Load unpacked** → the repo's `extension/` folder. Nothing to configure — [full steps](extension/README.md) |

```bash
# 1. Download the project and create your settings file
git clone https://github.com/seinun-ai/maestro-career-studio.git
cd maestro-career-studio
cp .env.example .env

# 2. Start the app (downloads about 1 GB the first time)
docker compose up -d
```

Then open **http://localhost:3000** and add your AI key in **Settings →
Models**. The first start sets up your database and adds a demo resume so you
have something to look at.

> **Young, but rehearsed.** The app runs daily on my machine, and a fresh
> install — clone, start, first tailored resume — has been checked end to end on
> a second machine. It has had little testing on machines that aren't mine. If
> it fails on yours, please
> [open an issue](https://github.com/seinun-ai/maestro-career-studio/issues)
> with the log — that report is one of the most valuable contributions there is.

### Do you need an API key?

**Recommended: yes.** Tailoring, the extension's form filling, cover letters and
screening answers, building your career record, and chat all use an AI service.

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
[Gemini setup](#5-choose-your-models-deliberately) is faster and costs under 3¢
per application.)

**Your key stays with you.** It's stored on your computer and sent only to the
AI service you configured. The app never shows a saved key back; its logs never
record keys, and record your prompts only if you turn that on.

**No key, but you use Claude or Codex?** Connect them over MCP and your
assistant does the AI work itself: it reads the posting and writes the tailoring
edits, and the app applies them with the same honesty checks — no AI key
needed.

**No key at all?** Scoring, gap diagnostics, health reports, manual editing, PDF
creation, application tracking and analytics all work without one. Features that
need AI ask you to add a key instead of failing.

### Local model servers (untested)

You can point the app at a local AI server (Ollama, LM Studio, vLLM) by setting
`OPENAI_BASE_URL` in `.env` (`http://host.docker.internal:<port>/v1` reaches your
computer from inside Docker). **We haven't validated any local model end to end
yet**, and long prompts and strict JSON output are where small models struggle
([`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) tracks this). If you try it, press **Test**
on each model in **Settings → Models** and tell us what worked in an issue.

---

## Updating

**One command, from the folder you cloned:**

```bash
./scripts/update.sh
```

It backs up your database, moves to the newest release, downloads the matching
app, and waits until it's healthy again. `./scripts/update.sh --check` tells you
whether you're up to date without changing anything. (It needs bash — on
Windows, run it under WSL.)

> **On v0.3.0 or older?** Those versions kept your data in Postgres, and only
> v0.4.0 can move it into the database file — so update to v0.4.0 first. The
> script spots this and prints the steps;
> [`docs/UPDATING.md`](docs/UPDATING.md#coming-from-v030-or-older) has them too.

**Your data is safe during updates.** Your resumes, applications and settings are
ordinary folders on your disk, and no update step touches them. **Deleting the
project folder does delete them**, so keep it.

**After updating,** reload the browser extension (`chrome://extensions` →
**Reload**, then reload any open job tabs) and restart your AI assistant so it
sees new tools.

[`docs/UPDATING.md`](docs/UPDATING.md) has the rest: updating by hand, pinning a
version, what the backup covers, and rolling back.

---

## Using it well

Maestro CS is built for **fewer, stronger applications**, not volume. Most
openings now draw hundreds of applicants, and many employers filter out resumes
that read as machine-written — so the leverage is in depth per application.

**Words you'll see:**

- **Career record (Career KB)** — one organized record of your work, built from
  your resumes.
- **Base resume** — your main resume for one kind of role (e.g. Data Scientist).
- **Tailoring** — adjusting a base resume to one job, using only things you
  actually did.
- **Match score** — Maestro's comparison of your resume with a saved job
  description (the app labels it **ATS score**). It is not an employer's score
  or a prediction of an interview.
- **AI service** — OpenAI or Gemini, whichever you choose.

### 1. Feed the Career KB first (once)

![Drop in your resumes, get a knowledge base](docs/assets/kb-onboarding.png)

Upload **every** resume version you have — old ones, role-specific ones, the
too-long one. Maestro merges duplicates across them and builds one **career
record**: your verified history in one place.

This step pays off every time. Everything later is built from approved points,
so the record's quality is the ceiling on everything else. Add certifications,
project write-ups and performance-review notes too — anything true about your
work can become evidence later.

> **Review the inbox before tailoring.** Bullets taken unchanged from your files
> are approved on import; anything merged across resumes, or written by AI,
> waits in the review inbox. Only approved points go into a resume, and fixing a
> duplicate once fixes every future application.

### 2. Build a base resume per career track

<!-- base-resume.png refreshed 2026-08-23 (post UI-clarity round). Contact
     header is the approved public set (sanitized +1-999-999-9999,
     ajey@seinun.com); "Liberty Hill, TX" experience location previously
     reviewed and accepted. 1400px wide to match the asset set. -->

![One base resume per track, with its health grade and live preview](docs/assets/base-resume.png)

One base per kind of role you actually target (e.g. *Data Scientist*, *ML
Engineer*) — not one per job. **New base resume → From Career KB** suggests
which entries belong, with a reason for each one it leaves out, plus a drafted
summary.

<!-- kb-import.png captured 2026-08-23: the editor's Import from Career KB
     drawer; background contact panel deliberately blurred at capture time. -->

![Adding points from your career record is explicit and versioned](docs/assets/kb-import.png)

The optional instruction box steers the *shape*, not the facts: "lead with
pipeline and cloud work, keep it mid-level, leave off teaching." **Bullets are
never rewritten at this step** — approved points go in word for word, which is
what keeps a generated resume defensible.

### 3. Save the job, then close the gaps

![Every job you have saved, from saved to signed](docs/assets/applications.png)

Paste the job posting or save it with the browser extension, then score it
against your base resumes. Scoring uses no AI service, so the same resume and
job always get the same number.

<!-- job-overview.png captured 2026-08-23: real Lightning AI posting kept on
     the same precedent as the Visa posting (employer-published public
     document); the "your profile states 2" line matches the years already
     public in the shipped resume captures. -->

![The job's details, and a check of its stated requirements against your profile — including mismatches](docs/assets/job-overview.png)

Every saved job also gets a **requirements check**: what the posting *states*
about work authorization, visa (OPT) policy, salary and years of experience,
compared with your profile — so a mismatch shows up now, not at the screening
call.

Then work through the **gaps** rather than accepting a rewrite. Maestro asks
targeted questions to find things that are true but not yet written down. Your
answers are saved to your career record, so closing a gap once helps every
future application.

> **About the score.** It's *our* score: fixed and repeatable, but **not** a
> prediction of what an employer's system shows — no consumer tool can offer
> that. Independent tests make the point: the same resume scored
> [66–99 across 100 runs](https://danunparsed.com/p/hackerrank-open-source-ats)
> on a popular AI-judged checker, with an
> [18-point spread](https://resumeoptimizerpro.com/blog/ats-resume-checker-tools-compared)
> across five commercial ones. Use ours to compare your own drafts and catch
> gaps. Chasing 100 produces keyword-stuffed resumes that modern screens flag.
>
> **Languages.** English resumes and job postings, including accented letters
> (*Zürich*, *José*, *São Paulo*). Non-Latin scripts (Chinese, Japanese, Korean,
> Cyrillic, Arabic, Hebrew, Devanagari, Thai) aren't supported yet and are
> refused on import rather than given a misleading score.

### 4. Generate the package, then read it

Cover letter, screening answers, and the PDF. Read everything before it goes
anywhere — it's your name on it.

### 5. Choose your models deliberately

**Settings → Models** has three slots: **Fast** (reading postings, bulk work),
**Smart** (tailoring, finding gaps) and **Chat** (the in-app assistant). We
tested the combinations on real job postings, and the **Fast** model turned out
to decide almost everything — how completely a posting's requirements are read,
how honest your score is, and most of the waiting time. So it comes down to two
tested setups, one per AI service:

| | **OpenAI** · most thorough | **Gemini** · fastest |
|---|---|---|
| Every slot set to | `gpt-5.6-luna` | `gemini-3.7-flash` |
| The one key you need | OpenAI | Gemini |
| Job requirements captured | the most complete we measured | about ¾ of that, strongest on named tools |
| Save + tailor takes | ~40 seconds | ~10 seconds |
| Cost per application | **about a penny** | **under 3¢** *(Gemini promo pricing doubles Jan 2027)* |
| Made-up skills | none measured | none measured |

Neither is better overall, and any OpenAI-compatible model can be used instead.
A fresh install starts with the OpenAI setup, because a model that misses
requirements quietly *inflates* your score — by about nine points in our tests.
With only a Gemini key, switch all three slots in **Settings → Models** (or set
`FAST_MODEL`/`SMART_MODEL`/`CHAT_MODEL` in `.env`). Press **Test** on any model
to check it works.

### Driving it from Claude, Codex, or ChatGPT (MCP)

**MCP** is the connector that lets an AI assistant use the app for you. With it,
Claude (Desktop or Code), the ChatGPT desktop app or the Codex CLI can run the
whole process in conversation — read a posting, score it, work the gaps, make
the PDF. It runs on **your computer** against **your** data.

![Claude pulling the whole pipeline over MCP and building its own view of it](docs/assets/mcp-dashboard.png)

<!-- TODO(P4) mcp-chat.png — a SECOND shot for this section is still open: a
     Claude conversation answering a real question over the explore tools
     ("what keeps coming up in the jobs I'm saving that I'm not showing well?"
     -> surface vs build tiers). Two candidates exist and both need work: the
     gap-query capture reports `kb_points: 0` / "your Career KB is nearly
     empty", which argues against §1's own advice, and the base-resume-listing
     capture is one tool call ending on a question with no result. Re-capture
     against a scored instance, then save here and add below the dashboard. -->

With the app running, both install from their own settings — no terminal, no
config file:

- **Claude** — Settings → **Extensions** → **Install Extension** → select
  `maestro-career-studio/mcpb/maestro-career-studio.mcpb` inside the folder you
  cloned. One install covers Claude Desktop *and* Claude Code sessions inside the
  Claude app.
- **Codex / ChatGPT desktop** — Settings → **Plugins** → **Add** → add
  `seinun-ai/maestro-career-studio` as a marketplace (ref `main`, sparse paths
  empty), then **Install**.

Neither needs Python on your computer: both run inside the app you already
started.

**Other assistants** (Cursor, Windsurf, and others) — run the setup script; it
prints a ready-to-paste config for each one (needs **Python 3.12+**):

```bash
./scripts/setup-mcp.sh
```

Or open Claude Code or the Codex CLI in this folder and ask it to run the
script for you.

**Tool sets.** All 83 tools are on by default (`full`). Smaller sets — `hunt`,
`apply`, `explore`, `templates`, `career` — keep a chat focused; pick one in the
Claude extension's **Tool profile** setting or with
`setup-mcp.sh --profile`. Use one set at a time.

**Skills.** [`docs/skills/`](docs/skills/) has ready-made skills for a daily job
hunt and an apply run that works on its own and asks you only for what the app
doesn't know, plus one yes before each submit. `customize-job-skills` suggests
skills from what your agent knows about you, asks a few questions, and builds
them with your assistant's own skill creator and scheduler.

Keep the connection type **STDIO** (the default). The HTTP option would expose
the app, which has no login — don't. (ChatGPT on the *web* can't reach a local
app; use the desktop app.)

Manual setup, every tool, and troubleshooting:
[`backend/mcp_server/README.md`](backend/mcp_server/README.md).

---

## The rest of the toolkit

The steps above are the core. These make each application quicker than the last.

### Talk to one resume — or one section, or one bullet

The in-app chat works on what you pin. Pin a base resume and it works on that
one; pin a section, a job entry or a single bullet and it **refuses** edits
outside it. Pin a career-record item — a project, a role, a certification — to
bring its detail into the conversation without letting the chat change it.
Suggested edits arrive as a card you accept or discard; nothing changes
silently.

### No more `resume_v2_FINAL(3).docx`

Every change — a manual edit, a chat edit, a tailoring run, even a restore —
saves a **resume version**. Open a resume's history to compare two versions or
restore one; nothing is ever lost. Old resumes you no longer use are archived,
not deleted.

### Tell it how you sound — once

A **persona** describes you as a candidate: vision, strengths, goals, working
style, how your writing should sound. Set it once in Profile (or have it drafted
from your career record, then review and save it), and every generated document
uses that voice. It shapes tone and emphasis only — never facts.

### Health Report — is this resume sound at all?

![A grade for the resume on its own, and what each problem is costing you](docs/assets/health-report.png)

A gap needs a job. A **Health Report** doesn't: it checks one resume on its own —
can it be read by application systems, are the dates right, is the evidence
strong, is the format sound. A serious problem **blocks** tailoring, because
tailoring can't fix a broken resume. You can overrule a finding, with a reason
on record.

### Templates you actually own

![LaTeX and Typst templates, built on your computer](docs/assets/templates.png)

Switching templates is a button, not a rebuild: your content stays the same and
renders through any template. There are two kinds — **LaTeX** and **Typst** —
both built on your computer. Start from a bundled design, adapt one you liked,
or write your own in the built-in editor; every template is test-built and
checked so that one that application systems couldn't read never goes live.
*(The web "New template" button starts from a LaTeX template; Typst templates
are created through the API or MCP.)*

### Quick Tailor, when you already know the answer

The guided gap process is the careful path. **Quick Tailor** is the fast one:
one click against a job, answers taken from your saved preferences, tailored and
rendered in one go. The honesty rule still holds — a skill Maestro found no
evidence for can only go in your skills list, never into an invented bullet.

### The browser extension

<!-- P4 extension.gif — CLEARED for publish 2026-08-20. Contact header scrubbed;
     the Job/Score/Resume/Fill/Track ladder and the multi-base scoring panel
     ("4 base resumes scored against this JD") are the feature moments. The Fill
     step is never executed in this take, so NO autofill values are ever on
     screen — preserve that if re-recording. Real employer careers page and the
     "Liberty Hill, TX" experience location reviewed and accepted by the owner.
     1000px / 10fps / 64 colors, 2.6 MB; re-encode any replacement to match. -->

![The extension on a job page](docs/assets/extension.gif)

A side panel in Chrome: save a posting from the job board you're reading, score
it, and fill application forms from your **Autofill Profile**. It never fills
signatures, passwords or government IDs, only ticks agreement boxes if you turn
that on in Profile, and never submits.

To improve form filling, it records *which* fields it met and whether they
filled — never what you typed. That data stays on your computer, but it does
show which companies you applied to and when. Clear it any time in **Analytics
→ Autofill coverage → Clear data**. There's no on/off switch in the panel yet;
[`extension/README.md`](extension/README.md) shows how to turn it off.

### Analytics: what the market keeps asking you for

![The market you are actually applying into, in numbers](docs/assets/analytics.png)

Every saved job adds to a picture of the market you're applying into — top
skills, a skill heatmap, role mix over time — filterable by role, level and job
type. The most useful view is **Gaps & growth**: skills jobs keep asking for,
marked as *missing*, *in your career record* or *already on a resume*. Frequent
and missing is worth learning next; frequent and already in your record is
something you have but keep forgetting to say. **Resume fit** shows the score
before and after tailoring for each base resume, so you can see whether
tailoring is helping.

### Hunt with the agent you already use

![A scheduled hunt reporting back — and stopping at your review](docs/assets/hunt-digest.png)

Your AI assistant can job-hunt for you. It reads your job preferences from the
app, finds postings on whatever sites it can use, saves and scores them against
your resumes, and hands back a ranked shortlist for you to review. There's no
job-board integration to be locked into.

Ready-made **`job-hunt`** and **`apply-session`** skills are in
[`docs/skills/`](docs/skills/) — copy them into your assistant's skills folder
as-is, or run **`customize-job-skills`** to make them yours or build new ones
(batch tailoring, referral-first hunting, a weekly digest) from your own data.

### Going all the way: agent applications

<!-- TODO(P4) proposals.png — the /proposals view: the Captured/Proposed/
     Accepted/Approved/Submitted counters, the daily cap chip, and the queued
     proposals with their ATS scores. It shows this section's core claim -- the
     lane stops before submitting -- in the app's own words ("What the hunt
     found. Submitting still needs your approval."). Captured but not yet saved
     to a file; drop it at docs/assets/proposals.png and uncomment: -->
<!-- ![What the hunt found. Submitting still needs your approval.](docs/assets/proposals.png) -->

Maestro CS can take an application right up to the submit button. Read this
part rather than skim it.

A job your agent finds becomes a **proposal**. You review proposals on the
**Agent Proposals** page and accept or decline them (in bulk if you like). An
apply run then works **only the ones you accepted**: it tailors, renders and
fills each application in a live agent session with a browser, asks you only
for information the app doesn't have (and hands you logins, CAPTCHAs and
signatures), and **waits for your yes before each submit**. Nothing is ever submitted from the web app itself, and a daily limit
you set caps how many submissions are possible.

Be clear about what that yes is: the agent records it, so the record shows *that
the agent said you agreed*. It's an audit trail and a volume limit, not a lock
that a manipulated agent can't pick — so run it while you're watching. An agent
can't mark an application submitted without a confirmation or your own word,
and if it can't tell whether a submit went through, it stops and never clicks
again.

**The risks, plainly.** Letting an agent read job pages and drive a browser
means three real exposures:

- **Manipulated instructions.** A job posting is untrusted text; text hidden in
  one can try to instruct the agent reading it.
- **Unverified employers.** A posting the agent found isn't a vetted one, and an
  application sends your contact details and history to whoever posted it.
- **Bot detection.** Some employers filter applications that look automated, and
  we won't help you hide it — no stealth browsing, no CAPTCHA bypass, no
  invisible (headless) submitting. See
  [Project Scope](CONTRIBUTING.md#2-project-scope).

Use it on jobs you have looked at yourself. Everything is written down —
proposals, your yes, and the screenshots behind them.

### Leave with everything

`career.md` is your whole career record as one Markdown file — downloadable from
the Career KB page or over MCP. Every application's PDF is saved in
`applications/`, in a folder named after the company and role, so checking what
you actually sent is opening a folder. Your data is yours, in files on your
disk, and nothing about leaving is made difficult.

---

## Where your files live

Everything stays inside the folder you cloned. These are yours, never uploaded,
and ignored by git:

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
[`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## Community, Documentation & Contributing

**Contribution fast-path:** docs fixes, resume/cover-letter templates and
extension job-board adapters go straight to a pull request — no issue needed.
Features and bigger changes: open an issue first. Every pull request gets a
human reply within 48 hours and is read by a human — we don't merge AI slop.

This is an early release. If something doesn't work, please say so — a clear bug
report is one of the most valuable contributions right now.

- **Project site:** [maestrocareerstudio.com](https://maestrocareerstudio.com) — a five-minute tour before you clone anything.
- **Getting Started:** [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md) — install to first tailored PDF, step by step.
- **Updating:** [`docs/UPDATING.md`](docs/UPDATING.md) — updating by hand, backups, rolling back.
- **Known issues:** [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) — what works well, what's rough, and what's a deliberate limitation.
- **Skills for your AI assistant:** [`docs/skills/`](docs/skills/) — job hunt, apply run, and a skill that builds your own.
- **Contributing:** [`CONTRIBUTING.md`](CONTRIBUTING.md) — development setup, tests, development mode and LLM tracing, and where help is wanted.
- **How it's built:** [`SYSTEM.md`](SYSTEM.md) — the architecture reference for contributors and coding agents; read the relevant part before changing behaviour.
- **Glossary:** [`UBIQUITOUS_LANGUAGE.md`](UBIQUITOUS_LANGUAGE.md) — the project's vocabulary, worth ten minutes before your first contribution.
- **Changelog:** [`CHANGELOG.md`](CHANGELOG.md) — what changed in each release; read any **Breaking changes** heading before [updating](#updating).
- **Releasing (maintainers):** [`docs/RELEASING.md`](docs/RELEASING.md).
- **Security & privacy:** [`SECURITY.md`](SECURITY.md) — the local-only rule and how to report a vulnerability.
- **License:** [`LICENSE`](LICENSE) — Apache License 2.0, plus [`NOTICE`](NOTICE).

---

## Licensing

Maestro CS is free software under the **[Apache License 2.0](LICENSE)**.

**You may use it commercially, and you don't have to publish your changes.**
Fork it, build it into a product, run a modified copy as a hosted service — all
permitted. Apache 2.0 asks three things in return: keep the license and
copyright notices, say what you changed in the files you changed, and pass along
the [`NOTICE`](NOTICE) file with any redistribution. It also includes an
**explicit patent grant** from every contributor, the main practical reason to
prefer it over MIT or BSD.

Credits for the third-party pieces we redistribute — the LaTeX resume template,
the XCharter font, the scoring model — are in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md), which the license also asks
you to carry forward.

**No CLA.** Contributions are licensed under Apache 2.0 by
[section 5](LICENSE) of the license itself; there's nothing to sign. Commercial
questions: **ajey@seinun.com**.

---

## Credits & Citation

Maestro CS stands on other people's work. The full list — bundled sources, the
scoring model, the PDF tools, and every dependency with its license — is in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md). The ones that shape the
product most:

- **[Jake's Resume](https://github.com/jakegut/resume)** by Jake Gutierrez (MIT)
  — the LaTeX resume and cover-letter templates are adapted from it.
- **[BAAI/bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5)**
  (MIT) — the small model behind the match score, running on your computer.
  Please cite [C-Pack (arXiv:2309.07597)](https://arxiv.org/abs/2309.07597) if
  you build on the scoring engine.
- **[TeX Live](https://tug.org/texlive/)** and
  **[Typst](https://github.com/typst/typst)** — the two PDF engines, with
  XCharter and FontAwesome 5 for type and icons.
- **[Next.js](https://nextjs.org)**, **[React](https://react.dev)**,
  **[Tailwind CSS](https://tailwindcss.com)**, **[Base UI](https://base-ui.com)**,
  **[shadcn/ui](https://ui.shadcn.com)**, **[Monaco Editor](https://github.com/microsoft/monaco-editor)**,
  **[FastAPI](https://fastapi.tiangolo.com)**, **[SQLAlchemy](https://www.sqlalchemy.org)**,
  and **[fastembed](https://github.com/qdrant/fastembed)** carry the rest.

Using Maestro CS in published work? Cite it with GitHub's **"Cite this
repository"** button, which reads [`CITATION.cff`](CITATION.cff).

---

## Troubleshooting & Common Questions

**"port is already allocated" when starting:**
Another program is using a port the app needs. Change `FRONTEND_HOST_PORT`
(3000) or `BACKEND_HOST_PORT` (8001) in `.env` and run `docker compose up -d`
again (`lsof -i :<port>` shows what's using it). If you change the backend port,
the browser extension needs the new address too — see
[`extension/README.md`](extension/README.md).

**AI features fail with "401 Unauthorized" or quota errors:**
Check the key in **Settings → Models** and press **Test**. If you put the key in
`.env` after starting, run `docker compose restart backend`.

**"database is locked":**
The database takes one writer at a time. Usually a program on your computer
opened `data/maestro_cs.sqlite3` while the app was running — stop the app first,
or open a copy from `backups/` instead. It also happens during long writes (like
building your career record); give it a few minutes. On a drive that doesn't
support the default mode (some network drives), set
`SQLITE_JOURNAL_MODE=DELETE` in `.env` and restart.

**PDFs fail to build:**
LaTeX templates need TeX, which the app's Docker image includes. If you run the
backend outside Docker without TeX, LaTeX templates build through a Typst
template instead and the app says so.

**The app came up empty after updating from v0.3.0 or older:**
Your data isn't gone — it's still in the old Postgres volume. See
[Coming from v0.3.0 or older](docs/UPDATING.md#coming-from-v030-or-older).
