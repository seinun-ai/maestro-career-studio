# Apply run — attended, with a channel in the loop

> For a session where the agent works the whole accepted queue while you are
> reachable (at your desk or on a channel like Slack). Fill in `<CHANNEL>`,
> or delete the channel lines to keep everything in the session. See
> [README.md](README.md) for setup.

---

Apply run with Maestro CS (apply profile + a headed real-Chrome browser via
Playwright MCP): work through `list_proposals(status="accepted")` per the
Maestro CS tools' guidance, the
[agent-apply playbook](../playbooks/agent-apply.md), and the
[execution skill](../skills/agent-apply-execution/SKILL.md).

Work the queue sequentially in this session yourself — never delegate
browser work, stuck-application handling, or consent gathering to subagents.
A blocked application (login wall, CAPTCHA, human-only field, dead posting)
goes to `needs_human` via `report_failure` with its reason — or a
posting-scoped decline if the role is gone — then move on to the next.

Tailor only where the playbook says: when the linked application or its PDF
is absent or stale. Never re-tailor or overwrite a current draft — if I
tailored one myself, that IS the current version.

Comms via <CHANNEL>: post one line when you start each application
(company · role), and IMMEDIATELY when anything needs me, saying exactly
what's needed and where. When an application reaches its final review, post
the consolidated summary there too (company, role, PDF filename, key
answers, any `duplicate_submitted` warning).

I'm present. Before any submit: one consolidated final review, then wait for
my explicit yes — given either here in the session or as a reply to that
summary on <CHANNEL>. Check the channel for my reply before proceeding, and
record consent with the channel I actually used. One application, one
consent — a yes never carries over to the next. If my answer is no or
unclear, don't click; ask or park it.

End with a short digest here and on <CHANNEL>: submitted / needs-me /
declined-dead / remaining in queue.
