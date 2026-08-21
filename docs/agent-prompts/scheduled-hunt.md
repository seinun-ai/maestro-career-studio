# Scheduled hunt — capture, score, and propose only

> Fill in `<TARGET_MARKET>`, swap the two sourcing examples for whatever job
> sources your agent has, and schedule it daily. The run's final message is
> the digest — read it wherever your client surfaces scheduled-run results.
> See [README.md](README.md) for setup.

---

Run today's Maestro CS job hunt: CAPTURE, SCORE, AND PROPOSE ONLY. Never
apply, submit, click apply controls, use browser automation on forms, or call
`record_triage` — triage is the user's, in the app.

If your client lazy-loads MCP tools, load these first: your job-source tools,
and from Maestro CS: `get_job_search_brief`, `find_job_by_url`,
`store_extracted_jd`, `score_ats`, `propose_application`.

1. BRIEF: `get_job_search_brief` drives everything — `job_preferences` are
   the search criteria, work authorization is used VERBATIM (never
   paraphrased), and `auto_apply.max_proposals_per_run` is this run's
   proposal ceiling (the submission cap is unrelated — ignore
   `cap.remaining`).

2. SOURCE roughly 30 postings per source, last 7 days only, spread across the
   brief's `role_categories` (rotate coverage across the week). Two worked
   examples — replace with your own sources:
   - An Indeed MCP server: `search_jobs(search=<role keywords>,
     location="<TARGET_MARKET>")` — if the source has no date filter, skip
     results clearly older than 7 days but keep undated ones; fetch full text
     and the apply link per posting.
   - An Apify LinkedIn-jobs actor (e.g. `apimaestro/linkedin-jobs-scraper-api`):
     input `{keywords, location: "<TARGET_MARKET>", date_posted: "day",
     sort: "recent", limit: <small>}`, second pass with `date_posted: "week"`
     only to fill shortfall. Never set a single-value experience-level filter
     (it over-filters — levels are filtered at step 5). Drop Easy-Apply rows
     (indicator field, or no off-LinkedIn apply URL) — tally
     "skipped: easy apply".

3. GATES, cheapest first, per posting:
   - Blocklist (case-insensitive company match) → tally "blocklisted".
   - No full JD text (teaser only) → tally "skipped: no JD text".
   - `source_url` = the employer's own posting/ATS URL when provided; board
     listing URL only as fallback. `find_job_by_url` on it — found → tally
     "duplicate".
   - Company vet (survivors only; ONE web search per new company per run,
     reused within the run): data-harvest signals — redirect/aggregator apply
     chains, employer mismatch across the chain, no real website or LinkedIn
     presence, the same text replicated across many cities, PII
     (SSN/DOB/bank) requested pre-interview → HARD-DROP, tally
     "skipped: suspicious company". Staffing/consultancy ("our client"
     postings) → KEEP, but prefix `plan.summary` with "[staffing] ". Direct
     employer → proceed.

4. CAPTURE + SCORE every survivor: extract to the `JobExtraction` schema
   (unstated → null, never invented; `requisition_id` verbatim from the
   posting, never the board's own listing id), then
   `store_extracted_jd(source="agent", raw_text=<full text>)`, then
   `score_ats` (no target = all bases).

5. PROPOSE selectively, best score first, up to the ceiling — counting only
   genuinely NEW creations (idempotent 200 returns don't count).
   Scope-exclude from proposing (they stay captured): senior/staff/principal-
   only postings when the brief targets below that; outside the target market
   with no remote; work-authorization exclusions (extracted
   `no_sponsorship` / citizen-or-permanent-resident-required, or a
   disqualifying OPT flag) ONLY when the brief says sponsorship will be
   needed — if the brief's work-auth is missing or contradictory, don't
   filter on it; let proposal warnings surface it. Propose with
   `fit={chosen_base, scores (all bases), decided_by: "auto"}` and
   `plan={summary: one-line match reason, company_note: 1–2 sentences on
   what the company is/does, direct vs staffing (whose client if known), any
   vet doubt — reused per company}`.

6. DIGEST (final message): per-source
   pull counts; tallies for blocklisted / no-JD / easy-apply / duplicate /
   suspicious-company / captured / scored-but-not-proposed / proposed; top 5
   proposals (title, company, score, source_url); a "suggested blocklist
   additions" line for suspicious companies or domains hit; and if a source
   errored entirely, say so plainly.
