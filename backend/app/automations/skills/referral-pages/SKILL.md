---
name: referral-pages
description: Use to check the careers pages of the user's referrals in Maestro CS for new roles that fit their Job Search Brief, capture and score them, and propose the best. Works attended or as a scheduled run.
metadata:
  title: Referral pages
  summary: Checks your referrals' careers pages for new roles that fit you and proposes them.
  kind: scheduled
  needs: [maestro, web]
  never: Never contacts a referral and never applies.
---

# Referral pages

A referral beats a cold application, so these pages come first. You need Maestro CS
over MCP and web access.

Never contact a referral, and never apply or submit.

1. **Brief.** Call `get_job_search_brief` first. It holds the role categories,
   location, work authorization (use it verbatim), blocklist and the proposal cap.
2. **Pages.** `list_referrals` gives each referral's `id`, company and
   `careers_url`. The brief lists the same pages without ids.
3. **Look.** Open each careers page and list its current postings. Keep the ones
   that fit the brief.
4. **Filter.** Drop postings `find_job_by_url` already knows, blocklisted
   companies, and postings without a full job description.
5. **Capture and score** each survivor: `store_extracted_jd` with
   `source="agent"` and the posting's `source_url`, then `score_ats(job_id)`.
   Extract only what the posting states.
6. **Propose** the best up to the cap with `propose_application`, passing the
   matching `referral_id`. Give each a one-line match reason in `plan`.
7. **Digest.** End with the pages you checked, what you proposed (title, company,
   score, link), and any page that failed to load.

The tools' own descriptions carry the details (blocklist refusals, posting-scoped
declines); follow them rather than working around a refusal.
