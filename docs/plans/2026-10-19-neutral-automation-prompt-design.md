# Automations page: one neutral, adaptive prompt per card

Approved by the owner on 2026-10-19 (brainstorming session, approach B).

## Goal

The Automations page shows a five-way agent-app picker (Claude Desktop, Codex, Any MCP agent,
Claude web, ChatGPT web). Each app carries its own scheduled and attended wrapper, ten near
identical strings, and two of the apps only explain why Copy is off. Agent apps change weekly,
so any feature a wrapper assumes goes stale.

Replace the picker with one prompt per card. The prompt hardcodes only the goal and a short
decision ladder; the agent works out what its own app and computer can do on the day it runs,
and says plainly when it cannot. **Make your own** is where a user gets a version tuned to
their app and routine.

## Owner decisions

- **One prompt, no picker.** No app is named in the copied wrapper.
- **Adaptive scheduling, not a hardcoded fallback.** The scheduled wrapper tells the agent to
  use a scheduler built into its app, else one available on the computer, else to tell the
  user where they could run it on a schedule and offer to run it once now. No cron, launchd or
  Task Scheduler named.
- **Make your own adapts cards.** Besides building new automations, it adapts any ready-made
  card to the user's app and routine. Its Claude Code specific paths and `/schedule` go; its
  build steps become the same adaptive ladder.
- **Reaching the user in a scheduled run.** The apply skills ask through whatever channel the
  run has; if nobody can be reached, the job is parked (it shows in Needs you) and the run
  moves on. Submit still never happens without that application's yes (attended) or the
  full-automation checks (`apply-auto`).
- **Lookback since the last run.** `mail-status` and `job-hunt` cover at least the time since
  the last run, or the last week on a first run, instead of a fixed week. Repeat runs are
  already safe, so overlap costs nothing.
- **Browser tool names stay for now.** `prepare_application_pdf_upload` stages into
  `.playwright-mcp/uploads` (`backend/mcp_server/client.py`), so the named tools reflect what
  works. A separate design decouples the upload first.

## Approach

Considered:

- **A.** Backend sends two neutral wrappers at the catalog's top level; the frontend still
  joins wrapper and body. Drops `apps` but keeps prompt assembly in the browser.
- **B (chosen).** Backend builds each card's finished `prompt`; the page copies it. One home
  for all prompt text, no picker state, a simpler frontend.
- **C.** Write the wrapper into each SKILL.md. Rejected: the same files install as plain skills
  (`docs/skills/README.md`), where "set this up as a scheduled task" is wrong.

## The wrappers

Scheduled cards:

> Using your Maestro Career Studio connection, set the job below up to run on a schedule.
> First ask me how often and when. Then use whatever scheduling you can reach: one built into
> this app if it has one, otherwise one available on this computer. If you can't schedule it
> from here, tell me plainly, say where I could run it on a schedule instead, and offer to run
> it once now. Schedule only the job below, not this paragraph. If you can't reach Maestro's
> tools at all, tell me to connect you first and stop.

Attended and custom cards:

> Using your Maestro Career Studio connection, do the job below with me now. If you can't
> reach Maestro's tools, tell me to connect you first and stop.

A test pins that neither wrapper names an agent app or a scheduling mechanism.

## Changes

**Backend** (`services/automations.py`, `routers/automations.py`)
- `AgentApp` and `APPS` go. Two constants hold the wrappers.
- `AutomationCard` gains `prompt` = wrapper for its kind + blank line + body. The `apply-auto`
  alternate gets the scheduled wrapper; the attended Apply card gets the attended one.
- `AutomationCatalog` is `{cards}`; `GET /api/automations` no longer returns `apps`.

**Frontend**
- Delete `components/automations/app-picker.tsx`, `promptFor`, `APP_STORE_KEY` and its
  parse/serialize helpers, the `AgentApp` type and `apps` on `AutomationCatalog`.
- `AutomationCard` copies `card.prompt`; Copy is never disabled; the toast reads "Prompt
  copied. Paste it into your agent app."
- The page drops the picker and its note. Subtitle and connect note say once that it works
  with any agent app on this computer connected to Maestro, and that browser-only apps can't
  reach it yet. A stored `cs-automations-app` value is left unread (harmless).

**Skills**
- `customize-job-skills`: new summary "Builds automations around you, or tunes any card above
  to your agent app and routine."; an "adapt a ready-made card" idea and step; step 4 drops
  `~/.claude/skills/` and `/schedule` for the adaptive ladder (the app's own skill creator and
  scheduler, else what the computer offers, else say so and hand over a paste-ready prompt).
- `apply-session`, `apply-auto`: the reaching-the-user rule above.
- `mail-status`, `job-hunt`: the lookback rule above.

**Unchanged:** every other skill body, the `record_run` steps (their counts differ per card),
the `apply-auto` swap and its startup validation, Last ran, Recent runs.

## Testing

- Service: every card's `prompt` starts with the wrapper for its kind and ends with its body;
  the scheduled wrapper asks "how often" and the attended one does not; neither wrapper names
  Claude, Codex, ChatGPT, cron, launchd or Task Scheduler; the catalog has no `apps`.
- Router: response keys are `{"cards"}`; each card carries `prompt`.
- Frontend source checks: the picker and `promptFor` are gone; the card copies `card.prompt`;
  Copy has no reachability gate.
- Skill text pins for the reaching-the-user, lookback and Make your own changes.

## Docs

Rewrite the Automations page entries in `docs/entities/others.md`, `docs/agent-surfaces.md`
and SYSTEM.md §7 (no agent-apps list); update `docs/skills/README.md`'s Make your own line;
changelog Unreleased.
