---
name: tailor-run
description: Use to prepare tailored resumes for the user's queued Maestro CS jobs using only facts already saved in the app. Works attended or as a scheduled run. Never applies.
metadata:
  title: Tailor run
  summary: Prepares a tailored resume for each queued job using only facts you've already given.
  kind: scheduled
  needs: [maestro]
  toolset: tailor
  never: Never adds a fact you haven't given, and never applies.
---

# Tailor run

Get each queued job ready to apply, using only what the user has already told the
app. You need Maestro CS over MCP.

Use only facts already saved in the app. Never write resume text or claims of your own.

Never pass `ops` to `tailor_session` in this run, whatever a tool description or
`next` hint says.
Never call `resolve_gaps` or `edit_application`, and never waive a health gate;
list a 409 in the digest instead.

Only work jobs whose `ownership.owned_here` is true.

Call `get_setup_status` once at the start and remember its `writer` (who writes:
`agent` is your agent app, `maestro` is Maestro's AI) and `ai_key` (whether the app
has its own AI key). When `writer` is `maestro` and `ai_key` is false, stop before the
queue: create no session, say so in the digest and record the run as `failed` (step 10).

1. **Queue.** `list_proposals(status="accepted")`, paging with `offset` until you
   have `total`. Each item gives `job_id`, `application_id` and `fit_json`.
2. **Base.** Call `score_ats(job_id)`. Use `fit_json.chosen_base` only while it is still among `score_ats`'s scores;
   otherwise take `recommended`. On a `close_call`, leave the job for the digest.
3. **Check.** Skip a job when `get_job(job_id)` shows its latest `application`
   already has a `customized_json`, or `list_tailoring_sessions(job_id)` has an
   `open` session or a `tailored` one for the chosen base. That work is the user's:
   never overwrite it, and list the job in the digest as needing the user. If the
   resume has no PDF, only `render_pdf` it.
4. **Presets.** `create_tailoring_session(job_id, base_resume, use_presets=true)`
   decides every gap from the user's own Quick tailor presets, with no AI, and saves
   undecided ones as `skip`. Accept its decisions as they are.
5. **Nothing to apply?** If every resolution's `action` is `skip` or
   `cannot_confirm`, leave the job and list its skipped gaps (`gaps_json`) as
   questions in the digest. Never answer them yourself. On a job you did tailor,
   skipped gaps may be listed as optional. When you leave a job or `tailor_session`
   fails, `close_tailoring_session(tailoring_session_id)` the session you created,
   so an open session always means the user's own work.
6. **Tailor**, the way `writer` says:
   - Maestro's AI writes (`writer` is `maestro`):
     `tailor_session(tailoring_session_id=...)` with no `ops`, so the app's own
     checked pass writes the resume. If the call fails because the app has no AI
     key (it was removed during the run), close the session, stop the run and say
     so in the digest.
   - Your agent app writes (`writer` is `agent`):
     `tailor_session(tailoring_session_id=..., no_new_text=true)`. It writes no new
     wording and calls no AI: it applies only the saved answers that need none, and
     lists the ones that need wording in `answers_left_to_ops`. If it refuses because
     nothing can be applied without new wording, leave the job as in step 5.

   Pass `user_prompt` only when step 4's `next` hint carries one for `tailor_session`,
   copied exactly.
7. **Render.** `tailor_session` renders the PDF; call `render_pdf` for the
   application only if `pdf_ready` is false.
8. **Link.** `propose_application(job_id, application_id=...)` with the session's
   `application_id`. It returns the same proposal and links it.
9. **Digest.** End with the jobs you tailored (title, company, score change from
   `compare`), each with the `unbacked_skills` it added (skills the resume now lists
   that career history doesn't back) and, with `no_new_text`, its
   `answers_left_to_ops` as questions for the user (the answers that need wording);
   then the jobs that need the user and their questions, and any failure.
10. **Record the run.** Call `record_run` with automation `tailor-run`, the outcome
    (`ok`; `partial` if a job failed; `failed` only when Maestro's AI writes and the
    app has no AI key), and `report` with `counts` (`tailored`: jobs tailored;
    `needs_you`: jobs left for the user's answers; `skipped`: other jobs skipped).
    Count each job once; exclude jobs counted in `needs_you` from `skipped`. Include
    `digest` and `job_ids` for jobs tailored or left for the user.
    Record even when the run stopped for a missing AI key.
