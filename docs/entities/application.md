# Application (`models/application.py`)

> Reference tier, extracted from [SYSTEM.md](../../SYSTEM.md) (§4 Core entities). The header contract there governs this file too: integrate don't append, present tense, no dates outside the ledgers, update in the same change that alters the behaviour described.

One per (job, base_resume) in practice. Holds `status`, `applied_at`, `notes`,
`referral_id`, `customized_json` (the tailored draft), `formatting_json`,
`template_id`, `pdf_path`/`tex_path`/`pdf_pages`/`render_error`, `user_prompt`.
The list summary, the detail and the extension's `GET /api/jobs/match` summary
all carry `base_resume_name`, the résumé's own name read from its row
(`base_resume_data.display_name_of`; archived and soft-deleted rows included;
null when the slug has no row).

- **Status vocabulary is backend-owned**: `ALLOWED_STATUSES` in
  `schemas/application.py` = draft, applied, interviewing, offered, accepted,
  rejected, withdrawn. PATCH 422s on anything else. The frontend mirrors it as
  `APPLICATION_STATUSES` in `lib/types.ts` (kept in sync by hand — update both).
- **applied_at sync rule** (PATCH handler): entering applied/interviewing/
  offered/accepted stamps `applied_at` if unset (jumping straight to
  interviewing implies you applied); moving to draft clears it;
  rejected/withdrawn preserve whatever is there. An explicit `applied_at` in
  the same PATCH always wins.
- **Reuse policy** (both `POST /applications/from-base` and `tailor()`):
  with no explicit `application_id`, the job's newest application for that
  base is updated in place — never a second insert (a second insert becomes
  an unreachable orphan). Consequence: from-base can overwrite a tailored
  draft — the web UI confirms first; version history keeps every prior draft.

