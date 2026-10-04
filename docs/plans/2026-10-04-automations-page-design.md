# Automations page: copy a prompt, your own agent runs it

Approved by the owner on 2026-10-04 (brainstorming session, approach A). This is phase 1 of
four.

## Goal

Let a user automate their job search with the agent subscription they already pay for. The
user should not need to read GitHub. Maestro runs nothing in the background. A page in the
app lists automations; each one copies a prompt. The user pastes it into their agent app, the
agent asks how often and when to run, and then it runs the work against Maestro through the
MCP connector.

This page is the first step toward the owner's end state: a fully automated job application,
if the user wants it, turned on and off in Settings.

## The four phases

Each phase gets its own design.

1. **Automations page** (this doc).
2. **Answer receipt and on-site check.**
   - A small source pill on each filled answer: Autofill profile, Résumé, Career KB, Custom,
     or Inferred. No more than that.
   - A per-application "what was submitted" view.
   - On-site/relocation added to the existing knock-out pre-scan. Custom Q&A already exists in
     Profile → Autofill → "Your own questions".
3. **Agent dashboard.** The Agent inbox becomes the place where new jobs arrive (ready / needs
   you / submitted).
4. **Full automation mode.**
   - A Settings switch for auto-submit, allowed only when every answer comes from a saved fact
     or the question can't screen the user out.
   - An account-creation password stored locally.
   - This reverses CONTRIBUTING refusal #1 and the "Next/Submit stay the user's" invariants on
     purpose.

## Owner decisions

- **Agent apps:**
  - Claude app (Desktop and web);
  - ChatGPT / Codex;
  - a generic variant for any MCP agent.

  Claude Code is not a target for this page; its users already have the skills.
- **Location:** a new sidebar page, `/automations`, under "Agent inbox".
- **Timing is the user's.** No cadence picker and no default schedule. Every prompt tells the
  agent to ask the user how often and when, then use its own scheduler. Nothing about the user
  is inserted into the copied text; the agent reads the brief, caps and preferences live from
  Maestro.
- **Approach A.** The skill files are the single source of prompt text, served to the page by
  the backend. Rejected:
  - **(B) prompt text hard-coded in the frontend:** the text would exist twice and drift.
  - **(C) MCP prompts only:** support differs by app, and there's no copy button. C can be
    added on top of A later, using the same files.
- **Unreachable apps are shown, not hidden.** Claude web and ChatGPT can't reach a local MCP
  server; remote connectors need a public URL, which the local-only rule forbids for now. Their
  variants carry the note "Needs remote access, not available yet" and Copy is disabled.
- **The Apply card switches mode.** It is attended today: one yes per submit, because the
  consent ledger and playbook require it. It reads its mode from the backend, so phase 4 only
  adds the setting and an auto-submit prompt, and the page doesn't change.

## Catalog

| Card | Skill (`backend/app/automations/skills/<name>/SKILL.md`) | Kind | Needs | Never |
|---|---|---|---|---|
| Mail status | `mail-status` (new) | scheduled | maestro, email | Sends or replies to mail; stores mail in Maestro |
| Job hunt | `job-hunt` (moved) | scheduled | maestro, web | Applies or triages |
| Referral pages | `referral-pages` (new) | scheduled | maestro, web | Contacts a referral |
| Tailor run | `tailor-run` (new) | scheduled | maestro | Writes a fact the user never gave |
| Apply session | `apply-session` (moved) | attended (until phase 4) | maestro, browser | Submits without the user's yes |
| *Make your own* (footer) | `customize-job-skills` (moved) | n/a | maestro | n/a |

`agent-apply-execution` moves with the others. It is a technique file, not a card; the Apply
session card's prompt points to it.

### New skills

- **mail-status:**
  1. Reads job-related mail since the last run.
  2. Matches each message to an application by company and role (`list_applications`, then
     `get_application`).
  3. Moves the status: confirmation → `applied` (only from `draft`), interview invite →
     `interviewing`, rejection → `rejected`, offer → `offered`.
  4. Adds a dated one-line note naming the email's subject. The note must append; it must not
     replace existing notes (the plan must check `update_application`'s notes behavior).

  An unclear match changes nothing. It ends with a short digest: what changed, unclear matches,
  and applications with no reply in 21+ days. No new status is added.
- **referral-pages:**
  1. Reads `list_referrals` careers URLs and checks each page for new postings that fit
     `get_job_search_brief`.
  2. Skips postings `find_job_by_url` already knows.
  3. Saves the rest with `store_extracted_jd`, scores them, and proposes the fits within the
     brief's ceiling.
  4. Ends with a digest.
- **tailor-run:** for queued jobs without a tailored résumé, runs `quick_tailor`. Quick tailor
  uses saved facts only and writes no résumé prose; absent-evidence keywords only go to Skills.
  It renders the PDF. A job with gaps only the user can answer is listed as "needs you" in the
  digest and left alone. It never calls `resolve_gaps` with new facts.

## Storage and serving

- **Files move.** `docs/skills/*` goes to `backend/app/automations/skills/<name>/SKILL.md`.
  The backend image is built from `backend/` only, so this puts the files in the image.
  `docs/skills/README.md` becomes an index linking to the new paths.
- **Skill format is kept** (`name`, `description`), so a folder can still go into
  `~/.claude/skills/`. App-only fields sit under `metadata:` so skill loaders ignore them:
  `title`, `summary`, `kind`, `needs`, `never`.
- **Endpoint.** `GET /api/automations` reads the files once (cached) and returns:
  - `cards: [{id, title, summary, kind, needs, never, body}]`
  - `apps: [{id, label, reachable, preamble, note}]`

  The Apply card's `kind` comes from a function that returns `"attended"` until phase 4's
  setting exists.
- **Per-app wrappers** live in one backend module:
  - **Claude Desktop:** "Using your Maestro Career Studio connector, set this up as a scheduled
    task. First ask me how often and when."
  - **Codex:** same wording; the note explains Codex has no scheduler and gives an example
    `codex exec` line for cron or launchd.
  - **Generic:** "Use your agent's own scheduler."
  - **Claude web and ChatGPT:** `reachable: false`, with the remote-access note.
- **What is copied:** `preamble + "\n\n" + body`. Attended cards use a wrapper without
  scheduling: "Run this now with me."
- **Failure handling:**
  - A missing or malformed file fails at startup; a test catches it first.
  - If the endpoint fails, the page shows the standard error state.
  - If the clipboard is blocked, the text stays readable in "Show prompt" so it can be selected
    by hand.

## Page

- **Sidebar:** "Automations", directly under "Agent inbox" (`frontend/components/app-sidebar.tsx`).
- **Header:** "Automations", plus "Copy a prompt into your own agent app. It asks when to run,
  then does these jobs with Maestro."
- **Setup line:** "Your agent needs the Maestro connector first." It links to the existing
  "How to connect an agent" URL in `frontend/lib/agent-links.ts`.
- **App picker:** a segmented control for Claude Desktop · Codex · Any MCP agent · Claude web
  · ChatGPT. The last choice is remembered in `localStorage`, wrapped in try/catch, and the
  page works without it. For an unreachable app, a quiet note shows and Copy is disabled on
  every card.
- **Cards:** a two-column grid at 1280 and 1024. Each card has:
  - a title and a Scheduled/Attended badge;
  - the summary;
  - Needs chips;
  - a muted Never line;
  - a **Copy prompt** button, which raises the toast "Prompt copied. Paste it into
    {app label}.";
  - **Show prompt**, an expandable section with the exact text, selectable.
- **Apply card:** Attended badge, plus "Scheduled applying comes with full automation mode."
- **Footer:** "Make your own: copy a prompt that builds automations around you."
- **Copy rules:** design-system tokens and components; existing glossary terms only; UI
  sentences of 25 words or fewer; desktop-only (1024px and up).

## Testing

- **Backend:**
  - every skill file parses and has its metadata;
  - card ids are unique;
  - the endpoint shape is as specified;
  - the Apply card reports `attended`;
  - every scheduled wrapper tells the agent to ask the user for timing;
  - Claude web and ChatGPT are `reachable: false`;
  - the guardrail lines are present: mail-status never sends, tailor-run never resolves gaps
    with new facts.
- **Frontend**, through source-reading tests in the style of
  `backend/tests/test_frontend_agent_inbox.py`:
  - the sidebar entry exists;
  - the page reads `/api/automations`;
  - Copy is disabled when `reachable` is false;
  - the clipboard fallback exists.

  Then lint, typecheck and build, and a live check on a fresh stack on spare ports.

## Docs

- **SYSTEM.md:** §2 (the automations dir) and §7 (the Automations page as an agent surface).
- **`docs/skills/README.md`:** rewritten as the index.
- **Links that reference `docs/skills`:** README, `docs/GETTING_STARTED.md`,
  `backend/mcp_server/README.md`, `frontend/lib/agent-links.ts`, `docs/entities/others.md`,
  and `backend/tests/test_frontend_agent_inbox.py`.
- **CHANGELOG.**

## Out of scope

- Exposing the skills as MCP prompts.
- Remote access for Claude web and ChatGPT.
- Any scheduler inside Maestro.
- Phases 2–4.
