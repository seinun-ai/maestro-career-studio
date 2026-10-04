---
name: mail-status
description: Use to keep Maestro CS application statuses in step with the user's job email — confirmations, interview invites, rejections and offers. Works attended or as a scheduled run. Reads mail only.
metadata:
  title: Mail status
  summary: Reads your job email and moves each application to applied, interviewing, rejected or offered.
  kind: scheduled
  needs: [maestro, email]
  never: Never sends or replies to email, and never copies email text into Maestro.
---

# Mail status

Keep the user's tracker in step with their inbox. You need Maestro CS over MCP and
read access to the user's email.

Never send, reply to, archive, label or delete email.

1. **Window.** Read job-related mail from the last 7 days, or the window the user
   gave. Repeat runs are safe: statuses only move forward and notes are not
   duplicated.
2. **Sort.** Keep application confirmations, interview invitations, assessments,
   rejections and offers. Ignore job alerts, newsletters and cold outreach.
3. **Match.** Page through `list_applications` (`limit`, `offset`) and match on
   company and role; confirm with `get_application`. Change nothing unless exactly one application matches.
4. **Move the status** with `update_application`, only forward:
   - confirmation → `applied`, only from `draft`
   - interview invite → `interviewing`, from `draft` or `applied`
   - rejection → `rejected`, from `draft`, `applied` or `interviewing`
   - offer → `offered`, from `draft`, `applied` or `interviewing`
   - an assessment adds a note but keeps the status.
   Leave `offered`, `accepted`, `rejected` and `withdrawn` as they are.
   Never set `accepted` or `withdrawn`; those are the user's.
5. **Note.** `update_application` replaces the whole notes field, so read the
   current notes first, then send them back with one line appended:
   `YYYY-MM-DD email: <confirmation|interview invite|assessment|rejection|offer>`,
   using the email's date. Skip the line if it is already there.
6. **Digest.** End with what changed, the emails you could not match, and the
   applications marked `applied` more than 21 days ago (see `applied_at`) with no reply.
