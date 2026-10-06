---
name: job-hunt
description: Use to run a Maestro CS job hunt — find recent postings that fit the user's Job Search Brief, capture and score them, and propose the best ones for the user to triage. Works attended or as a scheduled run.
metadata:
  title: Job hunt
  summary: Finds recent postings that fit your brief, saves and scores them, and proposes the best.
  kind: scheduled
  needs: [maestro, web]
  never: Never applies, submits or triages for you.
---

# Job hunt

Find postings worth the user's time and hand them over as proposals. The hunt
captures, scores and proposes — it never applies, submits, or triages; triage is
the user's, in the app.

1. **Brief.** Call `get_job_search_brief` first. It is the search criteria: role
   categories, location, work authorization (use it verbatim), blocklist, and the
   per-run proposal ceiling.
2. **Source.** Pull recent postings (roughly the last week) from whatever job
   sources you can reach — job-board tools, scrapers, the brief's referral
   careers pages, or plain browsing. Spread across the brief's role categories.
   Prefer the employer's own posting URL over a board listing.
3. **Filter.** Drop blocklisted companies, postings without the full job
   description, ones `find_job_by_url` already knows, and employers that look
   like data harvesting rather than hiring (a quick web check is enough; keep
   staffing agencies but say so in the proposal).
4. **Capture and score** each survivor: `store_extracted_jd` with `source="agent"`
   and the posting's `source_url`, then `score_ats`. Extract only what the posting states.
5. **Propose** the best-scoring ones up to the ceiling with `propose_application`,
   skipping roles the brief rules out. Give each a one-line match reason and a
   short note on the company.
6. **Digest.** End with what you pulled per source, what you dropped and why,
   what you proposed (title, company, score, link), and any source that failed.
7. **Record the run.** Call `record_run` with automation `job-hunt`, the outcome
   (`ok`; `partial` if a source failed; `failed` if none could be read), and
   `report` with `counts` (`found`, `proposed`, `skipped`), `digest`, and
   `job_ids` for the jobs you proposed.

The tools' own descriptions carry the details (idempotency, blocklist refusals,
posting-scoped declines); follow them rather than working around a refusal.
