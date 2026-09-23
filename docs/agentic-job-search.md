# Agentic job search — constraints

The rules any agent follows when it hunts for jobs through the Maestro CS MCP
server. The ready-made skill that follows them is
[`job-hunt`](skills/job-hunt/SKILL.md). Applying is a separate lane:
[playbooks/agent-apply.md](playbooks/agent-apply.md) governs everything past
capture, and a session that does both runs under both documents.

## Where postings come from

Maestro CS ships no job-board search and no scraper. It captures and scores
postings that you or your agent bring to it. Your agent may source them from
wherever you point it — job-board tools, scraper tools you have connected,
referral careers pages, plain browsing — within these limits:

- **Referral careers pages first.** Every `referrals[].careers_url` in the
  brief, warm contacts (`has_contact: true`) first, then everything else.
- **Only access you already have.** Use your own existing logged-in sessions.
  Never create accounts, and never work around login walls, rate limits,
  CAPTCHAs or bot detection, or use stealth or fingerprint-evasion tooling.
  Respect each site's terms. A posting you cannot legitimately see is skipped
  and named in the digest as inaccessible.
- **The employer's own posting.** Prefer it over a board listing. A listing
  whose apply link bounces through a third-party redirect vendor is not an
  employer posting: skip it and name the domain in the digest so it can be
  blocklisted.

## Hard rules

- **Brief first.** Call `get_job_search_brief` before searching. Its job
  preferences are the filtering criteria. Work authorization is used verbatim —
  never guessed, corrected or interpreted. Relay any `warnings[]` to the user
  before searching; fixing them is the user's job.
- **The hunt captures, scores and proposes.** It never applies, submits or
  triages; accepting or declining a proposal is the user's decision, in the app.
  Propose at most the brief's per-run ceiling (`max_proposals_per_run`).
- **Blocklist and past decisions hold.** Skip `company_blocklist` companies
  before extraction. Check `find_job_by_url` before extracting: a job already
  tracked is not captured again, and one that was scored and passed over, or
  whose proposal was declined, is not proposed again.
- **No fabrication.** Extract only what the posting states; anything it does not
  state takes the schema's explicit absent value (`null`, `"unstated"`,
  `"unknown"`). The `store_extracted_jd` tool description owns the schema. Pass
  `source="agent"` and the `source_url`, plus the raw text when you have it. An
  `already_existed: true` response is an already-tracked job, never a new
  capture.
- **Consent, EEO and submission belong to the apply lane.** A hunting session
  never clicks a final submit control. Those rules live in
  [playbooks/agent-apply.md](playbooks/agent-apply.md).

## The digest

End every run with: postings pulled per source, what was dropped and why
(blocklist, duplicate, inaccessible, redirect), what was proposed (company,
title, score, link), `already_existed` hits, sources that failed, and any brief
warnings relayed.
