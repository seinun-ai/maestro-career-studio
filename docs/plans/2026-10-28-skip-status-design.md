# Skip on Today, and a Skipped status

Owner ask (2026-10-28): Today's Next up card has only Apply; there is no way to pass on the job it
shows. Does skip need to be a status?

## Decision

Yes. Today is computed on every read, so a skip that is not stored brings the same job back on the
next visit. The only way to close a draft you will not send was **Withdrawn**, which says you pulled
an application you sent. The Agent inbox already words "you passed on this job" as **Skipped**.

- **New application status `skipped`** ("Skipped"): you decided not to apply. It closes the job
  (stage `closed`, like rejected and withdrawn), keeps `applied_at` as it is, and is reversible from
  the status chip (back to Draft).
- **Skipping closes the job's open proposals** (declined, consent channel `frontend`), as marking
  it applied does: a queued agent must not apply to a job you skipped.
- **Today's Next up gets a quiet Skip** beside Apply (LeadCard `secondary`, outline):
  - a ready PDF: PATCH the application to `skipped`, toast with Undo (back to `draft`), Today
    refetches and shows the next one;
  - an agent's job waiting on you: the job page's Skip (the Decline dialog, the proposal to
    `rejected`, shown as Skipped);
  - an offer: no Skip; an offer needs an answer.
- **Jobs list filter**: "Your applications › Skipped" is the new status. The Agent inbox lane's
  filter key, until now `skipped`, becomes `agent_skipped` (still labelled Skipped), so the two
  groups keep distinct keys. Both count as Closed.

Rejected alternatives: reusing Withdrawn (wrong word, counted as a withdrawal); a "not today" snooze
(a new stored field, and the job keeps coming back).

## Touch points

Backend `ALLOWED_STATUSES`, `stage._CLOSED_STATUSES`, `application_status.apply_status_effects`,
the MCP `update_application` description, the mail-status skill (never set `skipped`); the
Companion's `status-roles.js`; frontend `APPLICATION_STATUSES`, the status chip and `STATUS_TONES`,
the Jobs filter keys and `tracker-counts`, the Today page, `useProposalActions` (refresh Today);
docs/entities/application.md, docs/frontend-conventions.md (Today, Jobs filter), SYSTEM.md §5.

Sync: a skip on a job the other copy owns is queued like any status change; that copy must run a
version that knows `skipped`, else its PATCH refuses the request.
