# Job (`models/job.py`)

> Reference tier, extracted from [SYSTEM.md](../../SYSTEM.md) (§4 Core entities). The header contract there governs this file too: integrate don't append, present tense, no dates outside the ledgers, update in the same change that alters the behaviour described.

Raw JD text + `raw_text_hash` (sha256, unique) + `source_url` + `extracted_json`
plus promoted scalar columns (title, company, salary + currency, work-auth, …) and
JobSkill rows. **A Job has no status** — "Saved" (UI term) is derived as
job-without-application (`GET /api/jobs?without_application=true`). The list summary alone carries
`best_ats_score`, the max `composite` over the job's `base` AtsScore rows (null
when none; `ats_score.best_base_scores`, one grouped query per page, read-only:
the list never scores or backfills). It also carries the step the job is on: `stage`,
`open_session_id`, `gaps_done` and `gaps_total`, read at request time by
`services/stage.for_job_rows`: the job's newest application (`created_at`, then the higher id)
rated by the application rule, else the job alone. That costs three more queries per page however
many jobs it holds (the newest application per job, the open sessions, the drafts' newest
versions), reusing the best base scores the list already reads. `GET /api/jobs/{id}/detail`, the
`job` of `GET /api/jobs/match` and every proposal's `job` (`/api/proposals`, one call for the
page) carry the same four fields from the same rule (four queries for the one job, three when it
has no application: no draft time to read).

- **Salary is optional and often absent** (~40%+ of US postings state no
  pay; some laws let a posting hyperlink a pay page — capture that as
  `salary_source_url`, leave min/max null). Never treat a null salary as a
  parse failure or quality defect.
- **`salary_currency`** (ISO 4217, nullable; migration `c37b89e136ad`) and
  **`salary_currency_assumed`** (bool, NOT NULL default false; migration `ff9591f140f7`).
  A bare "$" is no currency (`JobExtraction.normalize_salary_currency`; "US$" and "USD" are
  USD). An amount without a code takes `market_settings.default_currency_for_capture(session,
  country_code)`: the job's country's currency (`countries.currency`, data in
  `services/data/country_currencies.yaml`), wherever the user lives, else the home currency (the
  chosen home market's, else `HOME_CURRENCY`), both marked `salary_currency_assumed` by
  `_salary_currency_for`; never hard-code `USD` at the call site.
  The backfill marked rows whose extraction named no currency; a "$" the old symbol table read as USD
  cannot be told from a stated one and stays unmarked. `salary_period` accepts `hour|day|week|month|year`
  (day/week for UK/EU contractor rates). The hourly pay hint (`jd_extraction._apply_salary_hints`, used
  only when the model left pay out) needs a currency mark or a pay word beside the amount and a
  per-hour unit, so "40 hours per week" is never pay.
- **Extraction→columns mapping** lives in ONE place: `_apply_extraction`
  (routers/jobs.py) — used by create, and by re-extract and a correction through
  `_replace_extraction` (the columns, `touch_job`, the skill rows deleted and
  written again by `_insert_skills`). Keep it that way; a drifted second mapper once
  wrote only 12 of 22 fields, so never reintroduce a parallel copy.
- **One spelling per value** (migration `2d3de2d60a4c`). `country_code` is the job's country as one
  ISO 3166-1 alpha-2 code beside `country`, which keeps what the posting said: `services/countries.for_job`
  reads the country field, else the one country the location line names (`named_in`: names and aliases
  only, never a bare two-letter part, since "San Francisco, CA" is California; two countries or none is
  null). `work_mode` is stored as a key, `on_site` | `hybrid` | `remote` (`schemas/job_extraction.work_mode_key`),
  and `level` as the extraction vocabulary `intern` | `entry` | `mid` | `senior` | `lead` (`level_key`;
  a level outside it keeps its own words as one key, "director"); the web app words the keys
  (`ENUM_LABELS`). Every capture writes them through `_apply_extraction` and the validators; the migration
  backfilled `country_code` and re-spelled older rows, and the analytics overview still folds any other
  spelling into its key (`explore_overview._count_by_key`; a country it cannot name is `unknown`, shown
  "Not stated"). Its Country filter takes any spelling and matches `country_code`.
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
- **`apply_url`** (nullable; migration `d3ea5090cc80`): the employer's own apply link, recorded when the Companion saves a job from a
  page that exposes one (an external Apply link, a LinkedIn `/safety/go` wrapper unwrapped one level, or the posting's structured data;
  only the page the user is viewing is read, nothing is fetched). It is written only through `HttpUrlStr` (http/https with a host, at most
  2048 characters; `javascript:`, `data:`, scheme-relative and empty values are a 422 on create, ingest and `PATCH /api/jobs/{id}`).
  A job saved again gains the link it lacked (`_fill_apply_url`, on the hash, `source_url` and requisition-twin dedup paths) but a stored
  link is never replaced by a save, only by a correction that sends one (next bullet), and a replica or an offered job is left alone for
  its owner to record (a PATCH of one is a 409). The
  Companion's run opens `apply_url` when present, else `source_url`; `queued` answers and `GET /api/jobs/match` match the page against
  either (`is_same_posting`). A job the user picked by hand for a page gets that page as its `apply_url` (the Companion PATCHes only when it has none and the page
  names a posting; the PATCH itself replaces whatever is stored), so the next visit matches. `/api/jobs/match` trusts an apply link only
  when it names a posting (`names_posting`: an id in a path segment or a posting-id query key): one that does not is a prefix of every
  posting of that employer. Reads are plain `str | None`
  on purpose, so one bad synced value cannot break job listing. Sync carries it; a duplicate resolution that keeps the laptop's twin drops
  the other copy's link.
- **`referrer_board`** (nullable; migration `e5a1c2d77b04`): the job board the user came from, a name from `autofill_job.BOARD_NAMES` ("LinkedIn", "Built In"), never an address.
  `POST /api/jobs` stamps it when the saved `source_url` is not a board's address, from `services/board_visits`: the last known job board page the Companion asked
  `GET /api/jobs/match?url=` about (the Companion's origin only; an agent's lookup is not the user's browsing), kept 20 minutes in one in-memory slot. It
  is the third place "How did you hear about us?" looks for the board after `?source=` and the host of `source_url` (`routers/autofill._job_hint`), so the answer
  is the board the person actually used, listed as assumed. Dedup paths do not rewrite it; it travels with the job through sync (a jobs column). A restart forgets the slot, and
  a job saved from any non-board address inside the window carries the board.
- **Ownership under sync** (`owner_machine`, `sync_rev`, `handover`; docs/sync-setup.md). `owner_machine`
  is the machine id of the job's one writer; NULL means this machine. `sync_rev` is the job's revision
  from a local clock: any write to the job or a row attached to it bumps it (`services/sync/hooks.py`,
  a `before_flush` hook), and a round sends only jobs past the last acknowledged revision. `handover` is
  `offered` (the laptop will give the job to the always-on copy at the next round; **Keep it here** clears
  it, and so does switching full automation off, `offers.withdrawing`; it is set when a job is queued with full automation on,
  `offers.mark_when_queued`; `GET /api/sync/handover/offers` lists them and is empty while full automation is off) or
  `returning` (the always-on copy is giving it back after **Work on it here**, refused while the job's proposal is `approved` or
  `submission_uncertain`), else NULL. A job in either
  state is not writable on the side that holds it. Without a sync key every job counts as owned here.
  The same JD text on both copies keeps the laptop's job; when both have progressed, the replica keeps a
  hash derived from its id (`services/sync/duplicates.py`), so `raw_text_hash` stays unique.
  The `ownership` field (`owned_here`, `owner`, `handover`, `pending_requests`, `can_keep_here`) is read
  from each row's own columns by `services/sync/ownership.py`, in one batch per request, and rides on
  the job, application and proposal reads; sync off (no key) is the default value, so the web app reads
  no ownership of its own and a row without the field is owned here.
- **Dedup response**: create/ingest return `already_existed: true` (transient
  attr → `JobRead`) on a dedup hit; the capture UI must not claim a fresh
  extraction.
- **Correcting a saved job** (`_correct_job`; `POST /api/jobs/ingest` with `update: true`, MCP `store_extracted_jd(update=True)`):
  when the ingest's dedup finds a saved posting (the same raw text's hash; with no raw text, the posting at `source_url`; or the
  requisition twin), the new extraction replaces its columns and skill rows through `_replace_extraction`, and a given `apply_url`
  replaces the stored one. The job keeps its id, status, applications, proposals, `source`, `raw_text` and `raw_text_hash`, so a
  correction finds it by resending the saved raw text or by `source_url` alone (new text misses the hash and saves a new job, as an
  `update` for a posting not yet saved does). A job another copy owns is refused (`require_owned`, 409) before any write, while a
  plain repeat capture of it still answers `already_existed`. The reply carries `already_existed` and the transient `correction`
  (`JobCorrection`, never stored): `changed` (the columns whose value changed, then the extraction's own lists such as
  responsibilities and qualifications, then `skills` when the skill rows changed), `scores_cleared`, `rescored`, `rescore_failed`
  (`"bases"` or an application id, which `score_ats` computes later), `tailored_applications`, `open_sessions` and
  `proposals_fit_stale`. When anything but `apply_url` changed, the job's match scores of both phases are deleted in the correction's
  commit and then scored again ([ats-score](ats-score.md)); a failed rescore never undoes the correction. A tailored resume, an open
  gap analysis (out of date once the extraction differs: [tailoring-session](tailoring-session.md)) and a proposal's stored fit
  (named only when scores were replaced) are named, never rewritten. A correction overwrites the stored extraction and nothing undoes
  it; the tool's annotation stays non-destructive. Pins: `tests/test_jobs_ingest_update.py`, `tests/sync/test_job_correction_sync.py`.
- **Re-extract guard**: 400s when `raw_text` is blank (capture-path job)
  instead of sending an empty prompt to the LLM.
- **Knock-out pre-scan** (`services/knockout.scan_for`, embedded in `GET /api/jobs/{id}/detail`,
  `get_final_review` and `GET /api/jobs/match` as `knockout`): the JD's stated requirements (work
  auth, OPT, salary, on-site vs where you live and relocation) against the profile, recomputed on
  every read. Verdicts are `conflict` / `clear` / `incomplete_profile` / `unstated`: unstated is
  NEVER a pass, and salary only warns (pay is negotiable). Work authorization is screened with the job's
  country's answers (a job with no country, the home market's; inv-work-permit-per-country). Salary
  compares in one currency: the posted ceiling converted (`money.convert`, ECB rates) into the desired
  salary's currency, the one its text names, else the home currency; with no rate, or a side that names
  no currency, the check is `cant_compare` (Can't compare), never a pass or a warning. On the job page
  (step 1, Job) only a conflict or a missing profile answer is a banner, with a per-check chip strip (OK /
  Conflict / Warning / Add answer / Not listed / Not run / Can't compare); anything else is one small line
  in the Job details card. It is
  informational, like G11 tier 2: it flags, and the consent/submit decision stays human unless the
  user's agent follows the full-automation prompt (SYSTEM.md §7). Inbox readiness reads only a
  `conflict` ([agent-runs](agent-runs.md)); the on-site check rides with the answer receipt
  ([filled-answers](filled-answers.md)).

