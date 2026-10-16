# Application (`models/application.py`)

> Reference tier, extracted from [SYSTEM.md](../../SYSTEM.md) (§4 Core entities). The header contract there governs this file too: integrate don't append, present tense, no dates outside the ledgers, update in the same change that alters the behaviour described.

One per job: its `base_resume` is the base the draft was last tailored or built from. A job
that already holds several applications from before this rule keeps them (no migration): the
detail shows the newest, and the Jobs list shows each row until one is deleted. Holds
`status`, `applied_at`, `notes`, `referral_id`, `customized_json` (the tailored draft),
`formatting_json`, `template_id`, `pdf_path`/`tex_path`/`pdf_pages`/`render_error`, `user_prompt`.
The list summary, the detail and the extension's `GET /api/jobs/match` summary
all carry `base_resume_name`, the résumé's own name read from its row
(`base_resume_data.display_name_of`, or an outer join in the list; archived
and soft-deleted rows included; null when the slug has no row). The list summary
alone also carries `ats_score`, the tracker's score column: the newest
`tailored` AtsScore row for the application, else the `base` row for
`(job, base_resume)`, else null. It is read-only (`ats_score.tracker_scores`,
one query per kind for the page; the list never scores or backfills). It also carries the
step the application sits on: `stage` (saved, scored, gaps, tailored, pdf_ready, applied or
closed), `open_session_id` with `gaps_done`/`gaps_total` on the gaps rung, and the booleans
`has_draft` and `has_pdf`, so the wire needs no `customized_json` to tell. All are read at
request time by `services/stage.py` (`for_applications`, three queries per page however many
rows it holds: the open sessions, the best base scores and each draft's newest ResumeVersion);
the list never writes them. An open session counts as later work than the draft only when it
is newer than that version (else the application's `created_at`), never `updated_at`, which
any column write moves (notes, referral, a render). The `GET /api/jobs/match` summary carries
the same six fields for the job's newest application (`for_job_rows`, four queries), so the Companion and `find_job_by_url` see the rung the Jobs
list shows.

- **Status vocabulary is backend-owned**: `ALLOWED_STATUSES` in
  `schemas/application.py` = draft, applied, interviewing, offered, accepted,
  rejected, withdrawn. PATCH 422s on anything else. The frontend mirrors it as
  `APPLICATION_STATUSES` in `lib/types.ts` (kept in sync by hand — update both).
- **applied_at sync rule** (PATCH handler): entering applied/interviewing/
  offered/accepted stamps `applied_at` if unset (jumping straight to
  interviewing implies you applied); moving to draft clears it;
  rejected/withdrawn preserve whatever is there. An explicit `applied_at` in
  the same PATCH always wins.
- **Reuse policy** (both `POST /applications/from-base` and `tailor()`,
  `application_writes.newest_for_job`): with no explicit `application_id`, the
  job's newest application (`created_at desc, id desc`, the order the detail
  reads), whatever its base, is updated in place — never a second insert (a
  second insert becomes an unreachable orphan). Its `base_resume` moves with the
  tailor, and the version row reads "Switched to {resume}" when the base changed;
  `status`, `applied_at`, `notes`, `referral_id` and the Q&A rows stay.
  Consequence: a tailor with another resume, or from-base, can replace a
  tailored draft and remove its PDF — the web UI confirms first; version history
  keeps every prior draft.

