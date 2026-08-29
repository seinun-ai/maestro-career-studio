# Job (`models/job.py`)

> Reference tier, extracted from [SYSTEM.md](../../SYSTEM.md) (§4 Core entities). The header contract there governs this file too: integrate don't append, present tense, no dates outside the ledgers, update in the same change that alters the behaviour described.

Raw JD text + `raw_text_hash` (sha256, unique) + `source_url` + `extracted_json`
plus promoted scalar columns (title, company, salary + currency, work-auth, …) and
JobSkill rows. **A Job has no status** — "Saved" (UI term) is derived as
job-without-application (`GET /api/jobs?without_application=true`).

- **Salary is optional and often absent** (~40%+ of US postings state no
  pay; some laws let a posting hyperlink a pay page — capture that as
  `salary_source_url`, leave min/max null). Never treat a null salary as a
  parse failure or quality defect.
- **`salary_currency`** (ISO 4217, nullable; migration `c37b89e136ad`). Amounts
  without a code fall back to `HOME_CURRENCY` (default `USD`) in
  `_apply_extraction` and in the migration backfill — never hard-code `USD` at
  the call site. `salary_period` accepts `hour|day|week|month|year` (day/week
  for UK/EU contractor rates).
- **Extraction→columns mapping** lives in ONE place: `_apply_extraction`
  (routers/jobs.py) — used by create and re-extract. Keep it that way; a drifted
  second mapper once wrote only 12 of 22 fields, so never reintroduce a
  parallel copy.
- **Dedup rules** (`_find_existing`): exact `raw_text_hash` always;
  `source_url` fallback **only when there is no raw text** (MCP/extension
  capture path, whose hash is of the LLM extraction JSON and unstable) — and
  that fallback matches by POSTING, not by string (next bullet). Never
  URL-dedup the paste path: careers pages reuse URLs across different postings.
  **Requisition dedup** (G11): post-extraction, a match on `(lower(company),
  requisition_id)` returns the tracked row with `already_existed` — the same
  requisition on two boards differs in URL AND page text, so hash/url dedup
  misses it. `requisition_id` is a promoted column, extracted verbatim-or-null
  (never invented; prompt rule in `extract_jd.txt`). Without one, company+title
  is only ever a SOFT duplicate signal (final-review `duplicate_submitted` + a
  triage chip), never a capture-time merge.
- **Posting equality, not string equality** (`services/job_url_match.is_same_posting`,
  behind `find_job_by_url` / `GET /api/jobs/match`): the same host AND the saved
  path being a PREFIX of the current one (equal counts). Query strings are
  ignored outright, so tracking parameters cannot make one posting look like two,
  and a deeper apply-flow URL still matches the saved posting. Never raises —
  `source_url` is user-supplied and the caller is a request path with nowhere to
  report a parse failure, so an unusable URL simply does not match. TWO callers,
  same predicate: `GET /api/jobs/match` (what the extension is looking at) and
  `_find_existing`'s url_fallback above — so the no-raw-text capture path dedupes
  by POSTING too. Both scan newest-first and take the first hit, so overlapping
  saves resolve deterministically to the most recent capture.
- **Dedup response**: create/ingest return `already_existed: true` (transient
  attr → `JobRead`) on a dedup hit; the capture UI must not claim a fresh
  extraction.
- **Re-extract guard**: 400s when `raw_text` is blank (capture-path job)
  instead of sending an empty prompt to the LLM.

