# Apply run — interactive, one application at a time

> The fully hands-on variant: nothing starts until you pick an application
> from the queue, and consent is given in the session itself. See
> [README.md](README.md) for setup; the same flow is packaged as a skill at
> [`docs/skills/manual-apply-session/SKILL.md`](../skills/manual-apply-session/SKILL.md).

---

Apply run with Maestro CS (apply profile + a headed real-Chrome browser via
Playwright MCP): follow the
[agent-apply playbook](../playbooks/agent-apply.md) and the
[execution skill](../skills/agent-apply-execution/SKILL.md).

First, call `list_proposals(status="accepted")` and show me the applications
currently in the queue as a numbered list (company · role). Do not begin any
application until I explicitly choose which one to start.

After I choose, work the queue sequentially in this session yourself. Never
delegate browser work, stuck-application handling, or consent gathering to
subagents.

For each application:

1. Confirm the selected company and role here before beginning.
2. Tailor only where the playbook says: when the linked application or its
   PDF is absent or stale. Never re-tailor or overwrite a current draft; a
   draft I tailored myself is current.
3. If blocked by a login wall, CAPTCHA, human-only field, or dead posting,
   use `report_failure` to mark it `needs_human` with the reason — or record
   a posting-scoped decline if the role is gone — then return here and ask
   whether I want to continue with the next queued application.
4. When the application reaches final review, present one consolidated
   summary here: company, role, PDF filename, key answers, and any
   `duplicate_submitted` warning.
5. Before submitting, wait for my explicit yes in this session. Record that
   consent as coming from this session. Consent applies to one application
   only.
6. If I say no or my answer is unclear, do not submit; ask for clarification
   or park the application.
