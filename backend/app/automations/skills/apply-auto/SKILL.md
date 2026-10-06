---
name: apply-auto
description: Use in Maestro CS full automation mode to work the user's queued applications and submit each one whose final review is clean.
metadata:
  title: Apply automatically
  summary: Works your queued jobs and submits the ones whose final review is clean.
  kind: scheduled
  needs: [maestro, browser]
  never: Never submits a job whose final review shows anything to check.
  include: [agent-apply-execution]
---

# Apply automatically

Full automation mode must be on in the brief; otherwise stop.

1. **Queue.** Call `list_proposals(status="accepted")` only.
   Work the queue the way the user has asked you to.
   Jobs in Needs you go back through the user's queue before a later automatic run.
   Stop when the daily cap in the brief is used up.
2. **Prepare.** Tailor or render only when the linked application or its PDF is missing.
3. **Accounts.** When a site needs an account or sign-in, call `get_job_site_login(proposal_id)`.
4. **Fill.** Answer from the user's profile, career history and saved answers.
   Record every completed page with `record_filled_answers`.
   Name the saved fact (`slot`) behind every screening answer.
5. **Check.** Call `get_final_review(proposal_id)`.
   Submit without asking only when `get_final_review` shows all of these:
   - the PDF is ready;
   - there is no knock-out conflict;
   - `flags` is empty;
   - `duplicate_submitted` is false;
   - there are no blocked or manual items;
   - every screening answer you recorded names its saved fact (`slot`).
6. **Submit.** Attach a screenshot of the filled form as `final_review` evidence.
   Record `record_consent` with channel `auto` and action `approved`.
   Submit once.
   Never submit the same application twice.
   Then call `mark_submitted` with channel `auto` and a `note` naming what confirmed it.
   A confirmation screenshot is optional.
   If you cannot tell whether submission succeeded, call `report_failure` with reason `submission_uncertain` and never retry.
7. **Everything else.** Call `report_failure` with the reason, ask the user, and move on.
   If the user says yes:
   Attach the filled-form screenshot as `final_review` evidence.
   Then call `record_consent` with channel `chat`, action `approved`, and the user's words.
   Submit once.
   Then call `mark_submitted` with channel `auto` and a note naming what confirmed it.
8. **Record the run.** Call `record_run` with automation `apply-session`.
   Report outcome `ok`, `partial` if a job failed, or `failed` if no job could be worked.
   Include `counts` (`updated`: submitted; `needs_you`: parked for the user; `skipped`: declined), `digest`, and `job_ids` for the jobs worked.
