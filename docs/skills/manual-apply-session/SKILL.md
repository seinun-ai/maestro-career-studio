---
name: manual-apply-session
description: Use for a manually invoked, user-driven application session over Maestro CS MCP plus a browser MCP — the user picks each application from the accepted queue and gives per-application consent in the session.
---

# Manual Apply Session

Use this skill for a manually invoked application session. It creates no
schedule, trigger, automation, or custom tools. Maestro CS (the `full` or `apply`
profile) provides the application data actions; a browser MCP (Playwright MCP with
headed real Chrome, or Claude-in-Chrome) provides browser actions.

The [agent-apply playbook](../../playbooks/agent-apply.md) is the canonical
policy owner and the
[agent-apply-execution skill](../agent-apply-execution/SKILL.md) the
execution overlay; this skill layers a stricter, pick-one interaction model
on top and cannot relax either.

## Required flow

1. Start by calling `list_proposals(status="accepted")`.
2. Show the user a numbered company · role queue.
3. Wait for explicit selection before doing any company-specific work.
4. Process one application at a time in this session, in order, with no
   delegation to subagents.
5. Confirm the selected company and role before preparing materials.

## Preparation vs execution

- Treat preparation as separate from submission.
- Tailor only missing or stale linked application content or PDF material.
- Never overwrite a user-tailored current draft.
- Upload the resume late, after the form is otherwise ready and reviewed.

## Form handling

- Verify dropdowns deliberately; do not assume the visible choice is the
  saved choice.
- Capture confirmation evidence immediately after submission.
- Keep the browser session state in mind; if the session resets, recover
  only by reloading the selected company, rechecking the accepted queue if
  needed, and resuming from the last confirmed step while keeping the job
  URL, resume path, application ID, and answer set accessible.

## Blockers and declines

- If a login wall, CAPTCHA, human-only field, or dead posting blocks
  progress, stop and report it.
- Use `report_failure` with `needs_human` and include the reason when human
  action is required.
- Use a posting-scoped decline when the posting is dead or cannot be
  completed as posted.
- Do not work around blockers indefinitely.

## Consent rule

- Before each submit, wait for a fresh explicit yes for that one
  application only.
- No, unclear, or absent consent means do not submit.
- Park the application or ask a clarifying question instead.

## Final review

Before any submission, present a concise final review with:

- company
- role
- PDF filename
- key answers
- `duplicate_submitted` warning

Also confirm that the current application is not a duplicate before
submitting.

## Reusable structure

Keep the session notes short and repeatable:

- queue
- selected company and role
- preparation status
- blocker status
- final review
- consent
- submit or park
