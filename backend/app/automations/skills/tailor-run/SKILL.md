---
name: tailor-run
description: Use to prepare tailored resumes for the user's queued Maestro CS jobs using only facts already saved in the app. Works attended or as a scheduled run. Never applies.
metadata:
  title: Tailor run
  summary: Prepares a tailored resume for each queued job using only facts you've already given.
  kind: scheduled
  needs: [maestro]
  never: Never adds a fact you haven't given, and never applies.
---

# Tailor run

Get each queued job ready to apply, using only what the user has already told the app.
You need Maestro CS over MCP.

Use only facts already saved in the app. Never write resume text or claims of your own.

1. **Queue.** `list_proposals(status="accepted")`, paging with `offset` until you
   have `total`. Each item gives `job_id`, `application_id` and `fit_json`.
2. **Skip** a job whose linked application already has a tailored resume
   (`get_application`). If its PDF is missing, only `render_pdf` it. Never re-tailor a draft.
3. **Base.** Use `fit_json.chosen_base`. If it is empty, take the recommended
   base from `score_ats(job_id)`; on a close call, leave the job for the digest.
4. **Quick tailor.** `quick_tailor(job_id, base_resume)`. It fills gaps from the
   user's saved profile and never writes prose.
5. **Needs you.** If gaps remain that only the user can answer, stop on that job and list its open questions in the digest. Never answer them yourself.
   A gap is open when `gaps_json` has a `gap_id` missing from `resolutions_json`
   (or `next.state` is `gaps_pending`).
6. **Tailor.** Otherwise `tailor_session(tailoring_session_id=...)` with no `ops`,
   so the app's own checked pass writes the resume. Then `render_pdf` with
   `target_type="application"` and the new application's id.
7. **Digest.** End with the jobs you tailored (title, company, score change from
   `compare`), the jobs that need the user, and any failure with its message.
