# Agent prompts — starting points for your own hunt and apply sessions

These are **user-side prompts**: the text you paste into (or schedule on) the
agent that drives Maestro CS over MCP. They are the working prompts the
author runs daily, with the personal parts turned into placeholders — treat
them as starting points and edit them into your own voice and constraints.

They deliberately encode the project's consent posture: the hunt prompt
captures, scores and proposes but **never** applies or triages; the apply
prompts stop at a final review and wait for your explicit yes, one
application at a time. If you edit them, keep those boundaries — the policy
they implement lives in
[`docs/playbooks/agent-apply.md`](../playbooks/agent-apply.md) (canonical)
and [`docs/agentic-job-search.md`](../agentic-job-search.md), and a prompt
cannot relax what the playbook forbids.

## The prompts

| File | What it is | How it runs |
| --- | --- | --- |
| [`scheduled-hunt.md`](scheduled-hunt.md) | Daily job hunt: source postings, gate them, capture + score, propose up to your ceiling. Capture/score/propose **only**. | On a schedule, unattended |
| [`apply-run-attended.md`](apply-run-attended.md) | Work the whole accepted-proposal queue with a browser while you are at the keyboard; consent per application, in the session. | Attended session |
| [`apply-run-interactive.md`](apply-run-interactive.md) | Same queue, but nothing starts until you pick an application from a numbered list, and consent is given in the session itself. | Attended session, fully hands-on |

There is also a skill version of the interactive flow at
[`docs/skills/manual-apply-session/SKILL.md`](../skills/manual-apply-session/SKILL.md)
for clients that support skills.

## Before you use them

Each prompt marks its personal placeholders in `<ANGLE_BRACKETS>`. Fill in:

- **`<TARGET_MARKET>`** — the location scope for sourcing (e.g. "United
  States"). Role keywords, work authorization and per-run ceilings are NOT
  placeholders: they come from your Job Search Brief
  (`get_job_search_brief`), which is configured in the app.
- **Job sources** — the hunt prompt shows two worked examples (an Indeed MCP
  server, and an Apify LinkedIn-jobs actor). Swap in whatever your agent can
  actually reach: a job-board MCP, a scraper, or plain web browsing. Keep the
  7-day freshness rule and the per-source tallies whichever sources you use.
- **Tool names** — the prompts use bare Maestro CS tool names
  (`get_job_search_brief`, `score_ats`, …). Your client may prefix them with
  the server name you registered (e.g. `maestro-career-studio-hunt`). Clients
  that lazy-load MCP tools behind a search step (Claude Code does) should be
  told to load the tools first; clients that don't can ignore that line.

## Installing them

- **Claude Code / Claude Desktop:** paste the prompt into a session, or
  schedule the hunt with a routine/scheduled task (`/schedule` in Claude
  Code) so it runs daily. Register the MCP server first —
  `./scripts/setup-mcp.sh` from the repo root; the `hunt` profile fits the
  hunt prompt, `apply` fits the apply prompts.
- **ChatGPT desktop app / Codex CLI:** register the MCP server (the setup
  script prints the config block), then paste the prompt; the hunt prompt
  also works as a scheduled task where your client supports one.
- **As a skill:** copy `docs/skills/manual-apply-session/` into your client's
  skills directory (Claude Code: `.claude/skills/` in a project or
  `~/.claude/skills/` globally) and invoke it when you want a strict,
  pick-one application session.

Nothing here creates automation by itself — a prompt only does what the
session you run it in is allowed to do, and the consent gate stays at the
submit boundary regardless.
