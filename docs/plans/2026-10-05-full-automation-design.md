# Full automation mode, and a bot-run main copy

Approved by the owner on 2026-10-05 (brainstorming session, approach 2: the prompt decides).
This is phase 4 of four. Phases 1 (Automations page), 2 (answer receipt,
`docs/entities/filled-answers.md`) and 3 (agent dashboard, `docs/entities/agent-runs.md`) are
merged.

## Goal

The owner's end state: "our application should support a fully automated job application if
that's user's wish, with appropriate settings to enable or disable." Phase 4 lets the user's own
agent apply without a per-application yes when a job passes every check, and lets that agent run
24/7 on another machine with its own copy of Maestro as the main copy, mirrored to the laptop.

## Owner decisions

- **Who submits:** the user's own agent (Claude, Codex, or an always-on agent app) with its own
  browser tool. The Companion keeps its never-submit promise; nothing in `extension/` changes.
- **24/7 agents:** supported when each user runs their own Maestro copy next to the agent. A
  shared multi-user copy stays refused (CONTRIBUTING #3).
- **Switch:** Off / On. No rehearsal mode, no per-board switches.
- **Approach 2, the prompt decides.** The agent judges eligibility from `get_final_review`; the
  server does not judge eligibility. The server still enforces the daily cap, the blocklist and
  the already-applied check on every approval, as today. Rejected: (1) a server-side eligibility
  gate; (3) the Companion submitting.
- **Consent label:** a new consent channel `auto`, accepted by the server only while full
  automation is On. It labels the agent's automatic yes so the record can tell it from the user's.
- **Password:** one job-site password, stored in a local file, handed to the agent by MCP.
- **Out of the design on purpose:** how the agent handles CAPTCHAs, mail, sign-in codes or how it
  reaches the user. That happens outside Maestro. The prompt only says: park the job and ask the
  user.
- **Bot copy:** inside phase 4. Transport is a shared folder the user picks.

## Part 1: The switch and the job-site login

**Setting.** `full_automation: bool = False` joins the auto-apply settings
(`schemas/auto_apply.py`, `services/auto_apply_settings.py`, `GET/PUT /api/settings/auto-apply`),
shown in Settings › Connected agents (`components/settings/auto-apply-section.tsx`). Turning it
On opens a confirm dialog saying what the agent will now do without asking. The brief's
auto-apply block (`job_search_brief._auto_apply_block`) reports it, so agents read it live.

**Job-site login** (shown while On): an email (default: the profile email) and a password used
only for job-site accounts.
- Stored in `settings/secrets/job-site-login.json`, file mode 0600, created by the backend. Never
  in the database, exports, telemetry, logs or snapshots (Part 4).
- `GET /api/settings/job-site-login` returns `{email, password_set}`; `PUT` sets either;
  `DELETE` clears both. The password is never returned by the web API.
- New invariant `{#inv-job-site-password-local}`.

**MCP `get_job_site_login(job_id)`** returns `{email, password}`.
- Refused unless full automation is On and the job exists.
- Each call writes an audit row (job id, time, client name; never the value).
- Its description states the trade-off as a fact: the value passes through the agent's AI
  provider, so it is a password used for nothing else.

## Part 2: The Apply automation when On

- `automations.apply_kind()` reads the setting: On → `"scheduled"` and the card serves a new
  skill, `apply-auto`; Off → today's attended `apply-session`, unchanged.
- **Eligibility, stated in `apply-auto`:** a job is submitted without asking only when its
  `get_final_review` shows: the PDF ready and its file present, no knock-out conflict, no flags
  (`flags` empty), `duplicate_submitted` false, no blocked or manual items, and every screening
  answer recorded with the saved fact it came from (its `slot`). Phase 2's flags already carry the
  owner's rule (an inferred or written screening answer flags `guessed_screening`; a mismatch
  flags `differs_from_profile`; EEO without a saved answer flags; ticking every option flags).
- **Per queued job:** fill each page and record it (`record_filled_answers`) → `get_final_review`
  → if eligible: `record_consent(channel="auto")`, submit once, attach the site's confirmation,
  `mark_submitted` with that receipt (never attested) → otherwise `request_decision` naming what
  blocked it, ask the user, and move on. A yes from the user is recorded as `chat` and the agent
  submits. After the user fixes the cause, a later run can submit it.
- Anything that stops the agent mid-form: park it (`request_decision` or `report_failure`) and
  ask the user. The prompt says nothing more about how.
- `get_job_site_login` when a site needs an account or a sign-in.
- The run ends with `record_run` (`updated`: submitted, `needs_you`, `skipped`).

## Part 3: Policy text, server label, tests, docs

- **CONTRIBUTING refusal #1** becomes "Unchecked volume auto-apply or bulk blast": full
  automation is opt-in, capped, limited to jobs the user queued, and limited to answers that pass
  every check. Unscored, uncapped or unqueued applying stays refused.
- **Consent channel `auto`:** added to every channel list (`services/proposals.py`
  `CONSENT_CHANNELS`, `schemas/proposal.py` `ConsentPayload`, MCP `record_consent`); the server
  accepts it only for `approved` and only while full automation is On (409 otherwise). New
  invariant `{#inv-auto-consent-gated}`.
- **SYSTEM.md §7:** `record_consent` stores the user's yes/no, or in full automation mode the
  agent's automatic yes (channel `auto`). Companion invariants unchanged.
- **Copy that changes on purpose:** the Connected agents explainer (the full-automation
  exception), the Apply card's never line when On, `agent-apply-execution` (points unattended runs
  to `apply-auto`), the agent-apply playbook (an unattended section), SECURITY.md and PRIVACY.md
  (the password file; snapshots).
- **Tests:** first a pin that the server refuses past the daily cap (none exists today). Then the
  setting round trip; the password file (mode, never in a GET, absent from exports and
  snapshots); `get_job_site_login` and `auto` refused while Off; `apply_kind` flips;
  `apply-auto` guardrail sentences; the "after your yes" pins updated on purpose; the browser
  check of the switch, dialog and password field.
- **Public repo:** examples use made-up companies (Acme, Globex), never real ones.

## Part 4: The bot's copy is the main one; the laptop mirrors it

**On the bot (the working copy):**
- `SNAPSHOT_DIR` (env; mounted into Docker) names the shared folder (any synced folder: Google
  Drive, Dropbox, iCloud).
- After each `record_run`, at most once per 15 minutes, and from a **Create snapshot now** button
  in Settings, the backend writes `maestro-snapshot-<UTC>/` there:
  - `maestro_cs.sqlite3` made with SQLite's own backup (consistent under WAL);
  - `applications/`, `base_resumes/`, `kb_documents/`, and `settings/` except `settings/secrets/`;
  - `manifest.json`: schema revision, app version, created time, source host name, sha256 of
    every file.
- The newest 3 snapshots are kept; a snapshot is written to a temp name and renamed when complete,
  so a reader never sees a half-written one.

**On the laptop (the mirror):**
- `scripts/pull-snapshot.sh` (and `scripts/install-pull-agent.sh`, a macOS LaunchAgent running it
  every 15 minutes while the laptop is awake). For a snapshot newer than the last import it:
  1. verifies every checksum;
  2. refuses a schema revision newer than the laptop's code ("update this Maestro first");
  3. if the laptop's database changed since the last import, keeps it as
     `data/backups/laptop-edits-<time>.sqlite3` and says so;
  4. backs up the current database (keeping one previous copy), stops the backend, swaps the
     files in, starts the backend (its startup migration upgrades an older snapshot), and records
     the import in `data/mirror.json` (snapshot time, source host).
- **Mirror banner:** while `data/mirror.json` exists, `/api/version` reports it and the web app
  shows "This is a copy of your bot's Maestro, last synced …. Changes here are replaced at the
  next sync."

**Privacy:** a snapshot is a whole-database backup the user sends to a folder they choose; filled
answers and EEO answers travel with it, and that folder's provider can read them.
`{#inv-filled-answers-local}` gains this as its one named exception; PRIVACY.md says it plainly.
The job-site password never leaves the bot.

**Docs:** "Run Maestro next to an always-on agent" (Docker on the bot's machine, `SNAPSHOT_DIR`,
MCP on that machine, the pull agent on the laptop).

## Out of scope

The Companion submitting; a rehearsal mode; per-board switches; a shared multi-user copy;
anything about CAPTCHAs, mail or how the agent contacts the user; two-way sync (laptop edits are
kept aside, never merged back).
