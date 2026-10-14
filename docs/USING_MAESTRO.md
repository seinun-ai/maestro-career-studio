# Using Maestro CS

This is the part of the README that explains what Maestro does and how to use it well: why it works the way it does, how the score and tailoring work, the five steps of a job search in the app, how to drive it from Claude, Codex or ChatGPT, and the rest of the toolkit. The install steps are in the [README Quickstart](../README.md#quickstart) and, step by step, in [Getting started](GETTING_STARTED.md). Keys, prerequisites and troubleshooting are in the [setup reference](SETUP_REFERENCE.md).

**Contents:**
[Why Maestro CS?](#why-maestro-cs) ·
[Using it well](#using-it-well) ·
[Driving it from Claude, Codex, or ChatGPT (MCP)](#driving-it-from-claude-codex-or-chatgpt-mcp) ·
[Always-on bot (optional)](#always-on-bot-optional) ·
[The rest of the toolkit](#the-rest-of-the-toolkit)

---

## Why Maestro CS?

**Your time belongs in your career, not in the paperwork around it.** Most of a
job search goes into documents thrown away a week later: a resume rebuilt for
each role, a cover letter written again from memory, the same "tell us about a
time you…" answered for the fourth time. Here you record what you actually did
once, and every document after that is assembled from that record.

**It never writes things you didn't do.** Your work goes into one **career
history**. Resumes are built from the bullets you approved, word
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
  ([`KNOWN_ISSUES.md`](../KNOWN_ISSUES.md)).
- **Tailoring.** Suggested changes arrive as a before/after view you accept or
  undo, one by one.
- **PDFs.** Built on your computer with LaTeX or Typst, two professional
  typesetting systems.

### How it compares

Only claims you can check yourself (as of August 2026 — tell us if a row has
gone stale):

| | Typical AI resume builders | CLI skill frameworks | **Maestro CS** |
|---|---|---|---|
| Match scoring | An AI guesses — same input, different score each run | AI judgment | **Fixed rules — same input, same score, every time** |
| Shows whether tailoring helped | Static score only | Not measured | **Score before and after, per application** |
| See what the AI changed | No history | No | **Every change shown, undoable** |
| PDF output | House web templates | HTML → PDF | **LaTeX and Typst, bring your own template** |
| Career record | None (per document) | Plain markdown/YAML files | **Organized, versioned — exports to one `career.md`** |
| Works with AI assistants | No | Command-line skill files | **88 tools for Claude, Codex, ChatGPT desktop — on your own computer** |
| Submits applications for you | N/A | Never (stated) | **Never without your yes, per application** |
| Cost | $15–75/month | Free + AI usage | **Free (Apache 2.0) + your own AI usage — [≈1¢ per application](SETUP_REFERENCE.md#do-you-need-an-api-key)** |

---

## Using it well

Maestro CS is built for **fewer, stronger applications**, not volume. Most
openings now draw hundreds of applicants, and many employers filter out resumes
that read as machine-written — so the leverage is in depth per application.

**Words you'll see:**

- **Career history** — one organized record of your work, built from your
  resumes. Each job, project or school in it is an **item**; each line is a
  **bullet**.
- **Base resume** — your main resume for one kind of role, such as Data Scientist.
- **Tailoring** — adjusting a base resume to one job, using only things you
  actually did.
- **Match score** — Maestro's comparison of your resume with a saved job
  description. It is not an employer's score or a prediction of an interview.
- **AI service** — OpenAI, Gemini or Claude, whichever you choose.

### 1. Build your career history first (once)

![Drop in your resumes, get your career history](assets/kb-onboarding.png)

Upload **every** resume version you have — old ones, role-specific ones, the
too-long one. Maestro merges duplicates across them and builds one **career
history**: your verified record in one place.

This step pays off every time. Everything later is built from approved bullets,
so its quality is the ceiling on everything else. Add certifications,
project write-ups and performance-review notes too — anything true about your
work can become evidence later. Import PDF, DOCX, PowerPoint (.pptx, including
speaker notes), Markdown or text files.

> **Review your drafts before tailoring.** Bullets taken unchanged from your files
> are approved on import; anything merged across resumes, or written by AI,
> waits in **Drafts to review**. Only approved bullets go into a resume, and fixing a
> duplicate once fixes every future application.

### 2. Build a base resume per career track

<!-- base-resume.png refreshed 2026-08-23 (post UI-clarity round). Contact
     header is the approved public set (sanitized +1-999-999-9999,
     ajey@seinun.com); "Liberty Hill, TX" experience location previously
     reviewed and accepted. 1400px wide to match the asset set. -->

![One base resume per track, with its health grade and live preview](assets/base-resume.png)

One base per kind of role you actually target (such as *Data Scientist* or *ML
Engineer*) — not one per job. **New base resume › From career history** suggests
which entries belong, with a reason for each one it leaves out, plus a drafted
summary.

<!-- kb-import.png captured 2026-08-23: the editor's Add from career history
     drawer; background contact panel deliberately blurred at capture time. -->

![Adding bullets from your career history is explicit and versioned](assets/kb-import.png)

The optional instruction box steers the *shape*, not the facts: "lead with
pipeline and cloud work, keep it mid-level, leave off teaching." **Bullets are
never rewritten at this step** — approved bullets go in word for word, which is
what keeps a generated resume defensible.

### 3. Save the job, then close the gaps

![Every job you have saved, from saved to signed](assets/applications.png)

Paste the job description (**Add job**) or save it with the Companion, then score it
against your base resumes. Scoring uses no AI service, so the same resume and
job always get the same number.

<!-- Screenshots in this guide were retaken 2026-10-12 on v0.10.1 with the
     fictional demo persona (Jordan Ellis, example.com, sample-company names);
     sources live in the private marketing repo (site-media/). -->

![The job's details and Match score, with a check of its stated requirements against your profile](assets/job-overview.png)

Every saved job also gets a **requirements check**: what the posting *states*
about work authorization, visa (OPT) policy, salary and years of experience,
compared with your profile — so a mismatch shows up now, not at the screening
call.

Then work through the **gaps** rather than accepting a rewrite. Maestro asks
targeted questions to find things that are true but not yet written down. Your
answers are saved to your career history, so closing a gap once helps every
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

**Settings › AI & models** has three model roles: **Fast** (reading postings, bulk work),
**Smart** (tailoring, finding gaps) and **Assistant** (the in-app Assistant). We
tested the combinations on real job postings, and the **Fast** model turned out
to decide almost everything — how completely a posting's requirements are read,
how honest your score is, and most of the waiting time. So it comes down to two
tested setups, one per AI service:

| | **OpenAI** · most thorough | **Gemini** · fastest |
|---|---|---|
| Every role set to | `gpt-5.6-luna` | `gemini-3.7-flash` |
| The one key you need | OpenAI | Gemini |
| Job requirements captured | the most complete we measured | about ¾ of that, strongest on named tools |
| Save + tailor takes | ~40 seconds | ~10 seconds |
| Cost per application | **about a penny** | **under 3¢** *(Gemini promo pricing doubles Jan 2027)* |
| Made-up skills | none measured | none measured |

| | **Claude** · your key, your roles |
|---|---|
| The one key you need | Claude (Anthropic) |
| Models you can pick | `claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-opus-5-5` |
| Roles | you choose per role (Fast, Smart, Assistant) in **Settings › AI & models** |

We have not measured Claude against the other two, so there are no figures for
it here. Press **Test** next to each model to check it works. An OpenRouter key
reaches many other models; Maestro asks OpenRouter to use only providers that
keep no data, but see [PRIVACY.md](../PRIVACY.md) for what OpenRouter itself
may keep.

Neither OpenAI nor Gemini is better overall, and any OpenAI-compatible model can be used instead.
A fresh install starts with the OpenAI setup, because a model that misses
requirements quietly *inflates* your score — by about nine points in our tests.
With only a Gemini or Claude key, switch all three roles in **Settings › AI & models** (or set
`FAST_MODEL`/`SMART_MODEL`/`CHAT_MODEL` in `.env`). Press **Test** next to each model
to check it works; **Find Gemini models** (or **Find OpenAI models**, **Find Claude models**) lists
what your key can use.

### Driving it from Claude, Codex, or ChatGPT (MCP)

**MCP** is the connector that lets an AI assistant use the app for you. With it,
Claude (Desktop or Code), the ChatGPT desktop app or the Codex CLI can run the
whole process in conversation — read a posting, score it, work the gaps, make
the PDF. It runs on **your computer** against **your** data.

![Settings › Connected agents: what a connected agent can and can't do, and the one-line command to connect Claude Code or Codex](assets/connected-agents.png)

<!-- TODO(P4) mcp-chat.png — a SECOND shot for this section is still open: a
     Claude conversation answering a real question over the explore tools
     ("what keeps coming up in the jobs I'm saving that I'm not showing well?"
     -> surface vs build tiers). Two candidates exist and both need work: the
     gap-query capture reports `kb_points: 0` / "your Career KB is nearly
     empty", which argues against §1's own advice, and the base-resume-listing
     capture is one tool call ending on a question with no result. Re-capture
     against a scored instance, then save here and add below the dashboard. -->

With the app running, open Settings › Connected agents › **Connect an agent app**
and choose a **Tool set**:

- **Claude Desktop** — on a Docker install, download the `.mcpb` bundle from the card or the
  [release](https://github.com/seinun-ai/maestro-career-studio/releases), then
  double-click it. It bridges Claude's stdio connection to Maestro's local HTTP
  endpoint and needs no Docker or Python on Claude's side. Reinstall the bundle
  if you have the older Docker-based extension. On a uv install, run
  `maestro connect claude-desktop` instead: it writes Maestro into Claude
  Desktop's settings. Desktop rewrites that file while it runs, so with Desktop
  open the command waits, writes the entry after you quit it, and `--now` writes at once.
- **URL clients** — Claude Code and Codex CLI get a copyable command; Cursor and
  VS Code get install buttons; other HTTP MCP clients get a URL. The default is
  `http://localhost:8001/mcp`. Use `/mcp` exactly — no trailing slash.

**On a uv install, `maestro connect` does this from the terminal.** With no app
it lists them and says which already have Maestro; `maestro connect claude-code`,
`codex`, `cursor` or `vscode` adds Maestro to that app, and `--print` shows what
it would add without changing anything.

For Claude Code or Codex CLI, the commands are:

```bash
claude mcp add --scope user --transport http maestro-career-studio http://localhost:8001/mcp
codex mcp add maestro-career-studio --url http://localhost:8001/mcp
```

`--scope user` makes Maestro available in every folder; without it, Claude Code adds it to the current project only.

The [plugin guide](../plugins/maestro-career-studio/README.md) covers release-tag
marketplace installs. In Codex's app, use the release tag as **Git ref** and
`.agents/plugins` plus `plugins` as **Sparse paths**. Plugins connect by URL too.
Legacy stdio through `./scripts/setup-mcp.sh` remains for one release and is
removed in v0.10.0; see the [MCP guide](../backend/mcp_server/README.md#legacy-stdio).

**Things to ask once it's connected:**

- "Here's a job posting: `<paste>`. Save it, score it against my base resumes,
  and tell me what it asks for that my resume doesn't show."
- "Tailor my Data Scientist resume to that job, show me what changed, then make
  the PDF."
- "Mark the Acme application as applied, and list everything still waiting on a
  reply."
- "Across the jobs I've saved, which skills keep showing up as gaps?"

**Tool sets.** All 88 tools are on by default (`full`). Smaller sets — `hunt`,
`apply`, `explore`, `templates`, `career` — keep a chat focused; pick one in the
card's **Tool set** selector or the Claude Desktop bundle's **Tool profile**
setting. Scoped URLs end in `/mcp/hunt`, `/mcp/apply`, `/mcp/explore`,
`/mcp/templates` or `/mcp/career`. Use one set at a time.

**Skills.** [`docs/skills/`](skills/) has ready-made skills for a daily job
hunt, an apply run that asks you only for what the app doesn't know (plus one
yes before each submit), mail-status, referral pages and a tailor run.
`customize-job-skills` suggests skills from what your agent knows about you,
asks a few questions, and builds them with your assistant's own skill creator
and scheduler. The **Automations** page in the app puts each one on the
clipboard: copy a prompt into Claude Desktop, Codex or any MCP agent, and your
agent asks when to run it.

`/mcp` has no authentication by design: a local process can already reach REST.
It sits behind the same Host/Origin checks as REST. Never publish port 8001 or
proxy `/mcp` beyond this computer. claude.ai and chatgpt.com web connectors are
outside this local setup.

Manual setup, every tool, and troubleshooting:
[`backend/mcp_server/README.md`](../backend/mcp_server/README.md).

### Always-on bot (optional)

An agent on a machine that stays on can work your job search while your laptop
is off. Your laptop keeps your profile, and each job has one owner.
[Run an always-on bot](always-on-bot.md) is the setup. On your laptop, open
Settings › Connected agents › Second copy and click **Copy setup prompt**. Paste
that into the agent on the other machine.

---

## The rest of the toolkit

The steps above are the core. These make each application quicker than the last.

### Talk to one resume — or one section, or one bullet

The **Assistant** (the in-app chat) works on what you pin. Pin a base resume and it works on that
one; pin a section, a job entry or a single bullet and it **refuses** edits
outside it. Pin a career history item — a project, a role, a certification — to
bring its detail into the conversation without letting the Assistant change it.
Suggested edits arrive as a card you accept or discard; nothing changes
silently.

### No more `resume_v2_FINAL(3).docx`

Every change — a manual edit, an Assistant edit, a tailoring run, even a restore —
saves a **resume version**. Open a resume's history to compare two versions or
restore one; nothing is ever lost. Old resumes you no longer use are archived,
not deleted.

### Tell it how you sound — once

A **persona** describes you as a candidate: vision, strengths, goals, working
style, how your writing should sound. Set it once in Profile › About you (or have it drafted
from your career history, then review and save it), and every generated document
uses that voice. It shapes tone and emphasis only — never facts.

### Health Report — is this resume sound at all?

![A grade for the resume on its own, and what each problem is costing you](assets/health-report.png)

A gap needs a job. A **Health Report** doesn't: it checks one resume on its own —
can it be read by application systems, are the dates right, is the evidence
strong, is the format sound. A serious problem **blocks** tailoring, because
tailoring can't fix a broken resume. You can **Mark as OK** a check you disagree with, with a reason
on record.

### Templates you actually own

![LaTeX and Typst templates, built on your computer](assets/templates.png)

Switching templates is a button, not a rebuild: your content stays the same and
renders through any template. There are two kinds — **LaTeX** and **Typst** —
both built on your computer. Start from a bundled design, adapt one you liked,
or write your own in the built-in editor; every template is test-built and
checked so that one that application systems couldn't read never goes live.
*(The web "New template" button starts from a LaTeX template; Typst templates
are created through the API or MCP.)*

### Quick tailor, when you already know the answer

The guided gap process is the careful path. **Quick tailor** is the fast one:
one click against a job, answers taken from your saved preferences, tailored and
rendered in one go. The honesty rule still holds — a skill Maestro found no
evidence for can only go in your skills list, never into an invented bullet.

### The Companion browser extension

<!-- P4 extension.gif — CLEARED for publish 2026-08-20. Contact header scrubbed;
     the Job/Score/Resume/Fill/Track ladder and the multi-base scoring panel
     ("4 base resumes scored against this JD") are the feature moments. The Fill
     step is never executed in this take, so NO autofill values are ever on
     screen — preserve that if re-recording. Real employer careers page and the
     "Liberty Hill, TX" experience location reviewed and accepted by the owner.
     1000px / 10fps / 64 colors, 2.6 MB; re-encode any replacement to match. -->

![The Companion on a job page](assets/extension.gif)

The **Companion** is a side panel in Chrome: save a job from the job board you're reading, score
it, and fill application forms from your saved answers (**Profile › Autofill**). It leaves
signatures, agreement boxes, passwords and government IDs to you unless you turn
on the agreement permission in Profile, and it never submits. Autofill does not move to the next page either; only **Apply** does, with full automation on (see the Companion's README).

With full automation on, a job page you have not saved yet shows **Add job** beside **Apply**: it saves the job and
scores your resumes, then stops on the ranked list without tailoring or starting anything. **Apply** shows a live checklist while it gets ready (save, score, the resume it
uses, queue, tailor, make the PDF, open the application) and a **Stop** button that ends it between steps.
Two switches under **Settings › AI & models › Form filling** steer it. **Choose the base resume for me**
(on) picks a resume only when its match score clearly wins, using the limits in Auto-apply, and asks you
when it is close; off, you always pick. **Stop after each step** (off) makes Apply three presses, **Save
job**, **Tailor resume** and **Start filling**, and your yes to queueing comes with the last one. When a
page refuses Next and says why, Apply fixes only the fields it names and stops if that does not help;
it attaches your resume before pressing Next and never presses Next over an empty required upload.

**Ready to submit** means nothing is missing: the page has a real Submit button and no Next, shows no
error and has no required box left empty. When Apply is not sure about a page it stops and says why:
**More than one Next**, **May send the application**, **No Next button found** or **Not sure about this
page**. Look, then press **Resume**: Apply fills what is still open first, and your Resume counts as
"this is the last page" only when no Next is left on it. Dropdowns and Yes/No buttons are fields, never
Next or Submit. On a Workday "Start Your Application" page Apply presses **Apply Manually** and nothing
else there; if it cannot, it says **Choose how to apply** and waits for you. If you start Apply on the job's own posting,
it opens the application link saved with the job rather than staying there; on a career site whose **Apply** button asks for a
new tab, Apply presses it in the same tab, but only when it leads to that link or to a known application site. When Apply waits for
a step you do by hand, it follows you into the tab you open for the application and says "The run moved to this tab"; press
**Continue here** to carry on (nothing is filled until you do). If you are on the job's tab and its run waits in another one, the
Job step offers **Move the run to this tab**; a run that is filling never moves. On a known application
site that asks you to make an account, Apply makes it with your saved job-site login, once, waits up to
20 seconds for the site to finish, and only then stops with **Account not created** if the site refuses
it, **Email code** if the site wants an email check and **CAPTCHA** if it shows one. A required
written question your saved answers cannot answer is **drafted from your career history for you to
read** ("Drafted from your history: read it"), never saved as a standing answer; **Careful** turns
drafting off. The **Ask** box at the foot of the Fill step answers any question from a form in one
paragraph you can copy; it opens when a run pauses.

A question your profile cannot answer gets a safe default from **Balanced** up: No (or Not
applicable when offered) for membership of a tribe, union or association, a referral, or relatives at the
company, and No (or "I don't wish to answer") for a spouse's or household member's military service; Yes for willingness to a standard step such as a background check, drug test, references,
I-9 or providing documents, and for basic means such as transport and internet. Criminal or background
history, salary, work authorization, demographic questions and your own military service are never defaulted. Every default is
listed under **Check before you submit**, and so is a required field that a search or a click filled for you (Field of Study, say),
which no longer stops the run; the page's own check decides. An optional Skills box stays empty in a run. What you type in the page
while a run waits on "The page asks for more" or on an upload is remembered like any other answer. The Companion also reads a job posting that has no built-in job data, taking the
description from the section under a "Job Description" or "About the role" heading.

Veteran status is one question in **Profile › Autofill**: "Are you a veteran?" (Yes, No, or "I don't
wish to answer"). A No answers every "I am not a protected veteran" option on a form. A Yes never picks
a protected class for you, so the Companion leaves that list to you, and a Yes never answers "are you currently serving?" either. A No
also answers "have you ever served?" with the never-served option, and says it was assumed. If your Profile still held the old
"Not a protected veteran" answer, the question is empty and asks again.

It can keep a **fill log**: *which* fields it met and whether they filled,
never what you typed. The log is off unless you tick **Keep a fill log** in the
Companion's options (right-click its toolbar icon, then **Options**). It stays
on your computer, but it does show which companies you applied to and when, so
it is yours to switch on. With it on, **Analytics → Autofill coverage** shows
where autofill misses; **Clear data** there deletes it.

### Analytics: what the market keeps asking you for

![Your search in numbers: applications over time, where they stand, and the gaps that keep coming up](assets/analytics.png)

Every saved job adds to a picture of the market you're applying into — top
skills, a skill heatmap, role mix over time — filterable by role, level and job
type. The most useful view is **Skill gaps**: skills jobs keep asking for,
marked as *not in your career history*, *in your career history* or *used before*. Frequent
and missing is worth learning next; frequent and already in your history is
something you have but keep forgetting to say. **Resume fit** shows the score
before and after tailoring for each base resume, so you can see whether
tailoring is helping.

### Hunt with the agent you already use

![What a hunt found, waiting in your Agent inbox for your review](assets/agent-inbox.png)

Your AI assistant can job-hunt for you. It reads your job preferences from the
app, finds postings on whatever sites it can use, saves and scores them against
your resumes, and hands back a ranked shortlist for you to review. There's no
job-board integration to be locked into.

Ready-made skills (`job-hunt`, `apply-session`, `mail-status`, `referral-pages`,
`tailor-run`) are in [`docs/skills/`](skills/) — copy a prompt from the
app's **Automations** page into Claude Desktop, Codex or any MCP agent (your
agent asks when to run it), copy the skills into your assistant's skills folder
as-is, or run **`customize-job-skills`** to make them yours or build new ones
(batch tailoring, referral-first hunting, a weekly digest) from your own data.

### Going all the way: agent applications

<!-- TODO(P4) proposals.png — the /proposals view: the Captured/Proposed/
     Accepted/Approved/Submitted counters, the daily cap chip, and the queued
     proposals with their match scores. It shows this section's core claim -- the
     lane stops before submitting -- in the app's own words ("What the hunt
     found. Submitting still needs your approval."). Captured but not yet saved
     to a file; drop it at docs/assets/proposals.png and uncomment: -->
<!-- ![What the hunt found. Submitting still needs your approval.](assets/proposals.png) -->

Maestro CS can take an application right up to the submit button. Read this
part rather than skim it.

A job your agent finds becomes a **proposal**. You review proposals in the
**Agent inbox** and **Queue** or **Skip** them (in bulk if you like). An
apply run then works **only the ones you queued**: it tailors, renders and
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
  [Project Scope](../CONTRIBUTING.md#2-project-scope).

Use it on jobs you have looked at yourself. Everything is written down —
proposals, your yes, and the screenshots behind them.

### Your resumes folder

Every finished resume PDF, and every cover letter PDF, is also copied to a folder
you can see: `Documents/Maestro Career Studio/Applications` (on Windows, your real
Documents folder, even when OneDrive moved it). Each job gets one folder named
`Company – Job title (date)`. The name is chosen once, so editing the job title
later does not move it, and two jobs with the same name get a "(2)" on the second.

The copy happens after you create or update a PDF, after a cover letter is
rendered and after a job arrives from your second copy. Every start also
copies the resume PDFs you already have, with their cover letters, skipping the ones
already there, and so does changing the folder or switching copies back on. Maestro only writes there. It
never reads a copy back and never deletes anything. Deleting or renaming a copy is
fine: Maestro brings a job's copy back only when that resume changes (a new PDF) or
you click **Show in Finder**.

**Show in Finder** (**Show in File Explorer** on Windows, **Show in folder** on
Linux) on the PDF card and in the tailored-resume studio opens the copy. In Settings ›
Tailoring › **Resumes folder** you can switch it off, **Open folder**, **Change
folder** (type a path or press **Choose…**) or **Use the default**. If a copy
fails, for example because a drive is unplugged, the last problem shows there.
The Docker route keeps PDFs in `applications/` instead and has no resumes folder.

### Leave with everything

`career.md` is your whole career history as one Markdown file — downloadable from
the Career history page or over MCP. Every application's PDF is saved in
`applications/`, in a folder named after the company and role, so checking what
you actually sent is opening a folder. Your data is yours, in files on your
disk, and nothing about leaving is made difficult.
