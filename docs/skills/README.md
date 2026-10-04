# Skills for driving Maestro CS from your agent

Ready-made skills for any agent that has the Maestro CS MCP server registered
(Claude, Codex, the ChatGPT desktop app). They stay short on purpose: the
details live in the tools' own descriptions and in your Job Search Brief, so
the same skill works for anyone.

The skill files live in [`backend/app/automations/skills/`](../../backend/app/automations/skills/).
The app shows these on the Automations page, with a Copy button for each.

| Skill | What it does |
| --- | --- |
| [`job-hunt`](../../backend/app/automations/skills/job-hunt/SKILL.md) | Finds recent postings that fit your brief, captures and scores them, and proposes the best for you to review. Never applies. |
| [`apply-session`](../../backend/app/automations/skills/apply-session/SKILL.md) | Works your accepted queue with a browser. Asks you only for information the app doesn't have, plus one yes per application before it submits. |
| [`mail-status`](../../backend/app/automations/skills/mail-status/SKILL.md) | Reads your job email and moves each application to applied, interviewing, rejected or offered. Never sends mail. |
| [`referral-pages`](../../backend/app/automations/skills/referral-pages/SKILL.md) | Checks your referrals' careers pages for new roles that fit you and proposes them. |
| [`tailor-run`](../../backend/app/automations/skills/tailor-run/SKILL.md) | Prepares a tailored resume for each queued job using only facts you've already given. |
| [`customize-job-skills`](../../backend/app/automations/skills/customize-job-skills/SKILL.md) | Suggests skills that fit you — from what your agent knows about you and your data in the app — then asks a few questions and builds your own version, or something new (batch tailoring, referral-first hunting, a weekly digest…), with your client's skill creator and scheduler. |
| [`agent-apply-execution`](../../backend/app/automations/skills/agent-apply-execution/SKILL.md) | Optional: detailed browser technique for apply runs (PDF upload, dropdowns, evidence, what to hand to you). |

**Use one as-is:** copy its folder into your client's skills directory (Claude
Code: `~/.claude/skills/` or a project's `.claude/skills/`) and ask for it. A
client without skills can take the SKILL.md text as a prompt.

**Make them yours, or make new ones:** install `customize-job-skills` next to
the others and run it.
