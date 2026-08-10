# Agentic job search — phase 1 playbook (brief + capture)

**Contract:** Maestro CS MCP is the brain and ledger; a Claude session with
browser access is the hands and eyes. Phase 1 is **capture and score only**.
Everything found lands as a Saved job for human review. Discovery
infrastructure (board registry, saved searches, triage states, search-run logs)
is deferred — see SYSTEM.md §11.

**The apply lane is a separate playbook.** Applying — filling, staging, and
consent-gated submission through the proposal ledger — is governed by
[playbooks/agent-apply.md](playbooks/agent-apply.md). This document covers
hunting and capture only; when a capture session is also filing proposals it
runs under both documents, and the apply playbook's constraints govern
everything past capture.

## Hard constraints (non-negotiable)

- **No submission without validated consent.** An agent may capture, tailor,
  fill, and stage an application without prompting on each ordinary page, but
  agent policy permits the irreversible final submit click only after one
  consolidated final review and the user's same-turn affirmative response.
  That response triggers `record_consent`; the target approval transition
  atomically verifies `final_review` evidence and idempotently reserves one
  daily-cap slot keyed by proposal before the click. Re-approval cannot
  double-count. `submitted` and `submission_uncertain` keep the slot consumed;
  explicit rejection before the click or `resume_proposal` after a pre-click
  interruption releases it; pre-approval `needs_human` has no reservation. If
  approval or preflight fails, do not click. The backend writes an append-only
  `consent_events` row and refuses `mark_submitted` without valid consent and
  `submission_receipt` evidence, but it cannot physically prevent the browser
  executor from clicking. Same-turn, single-use approval is therefore an
  agent-policy boundary and expires on interruption; there is no second
  go-ahead. Never click an irreversible final submission control in an "Easy
  Apply"-style flow outside that policy; launch, open, and staging controls are
  not submission. Sessions without the apply playbook loaded remain
  capture-only: the human applies.
- **Evidence is typed.** The target manifest's evidence-kind enum is `step`,
  `final_review`, and `submission_receipt`; `attach_evidence_file` requires one
  of those kinds. Approval requires `final_review`, and `mark_submitted`
  requires `submission_receipt`.
- **EEO is consent-gated for agent/Playwright fill.** Equal-opportunity,
  disability, veteran, race/ethnicity, and gender fields may be filled from
  `get_autofill_profile` when Profile standing consent is active
  (`eeo_consent.enabled`) and `profile.eeo` is returned — use exact stored
  answers only; never infer or invent. Without consent, MCP strips
  `profile.eeo`. Never ask the user to paste EEO/demographic answers into
  chat; if Profile values are missing, hand off in-browser or have them update
  Profile. WOTC/public assistance, signatures, penalties-of-perjury
  attestations, terms, credentials, and certifications remain human-only; the
  user acts directly in the browser and the agent never relay-enters answers.
- **A submit click is never retried.** After the browser clicks final submit,
  failure to verify ATS success, attach the receipt, or stamp the ledger with
  `mark_submitted` enters the distinct terminal proposal status
  `submission_uncertain`; call
  `report_failure(proposal_id, "submission_uncertain")`. Never click submit
  again, and never route it through `needs_human` or `resume_proposal`; report
  the available evidence and leave ATS/employer reconciliation to the human.
  One ledger-only exception (2026-08-01): when the USER later states the
  submission went through (confirmation email, portal check),
  `mark_submitted(proposal_id, user_attested=true, note="<their words>")`
  closes the record as submitted with an attested consent event — user
  statement only, never the agent's own judgment, and still no browser action.
- **No bot-detection or auth-wall workarounds.** Never bypass or solve
  CAPTCHAs, rate limits, or login walls, and never use stealth/fingerprint-
  evasion tooling. If a posting is behind a wall you cannot legitimately see
  through an existing logged-in session, skip it. Before proposal creation,
  report it in the run digest as inaccessible; `report_failure` is used only
  when an active proposal ID already exists, in which case the apply lane
  transitions it to `needs_human`.
- **No fabrication.** Extract only what the posting states. Anything the JD
  does not state is `null` / `"unstated"` / `"unknown"` — the JobExtraction
  schema has explicit values for absence; use them.

## Step 1 — Read the brief

Call `get_job_search_brief` (GET /api/jobs/search-brief). It returns:

- `profile` — city/state/country, willing_to_relocate, and work-auth values
  **verbatim** from the autofill profile.
- `job_preferences` — the typed search preferences (role_categories, levels,
  employment_types, locations, remote posture, min_salary, notes), verbatim
  (2026-08-01). These ARE the hunt's filtering criteria; never guess or
  override them.
- `auto_apply` — hunt guardrails: `company_blocklist` (never capture-and-score
  a blocklisted company — skip before extraction), `max_proposals_per_run`,
  and `cap` (`max_per_day` / `reserved_last_24h` / `remaining`) so a run
  sizes itself instead of discovering limits by 409.
- `warnings[]` — non-empty when the work-auth values are contradictory or
  missing. **Relay warnings to the user before searching**; the fix is theirs
  to make (Settings → Autofill). Never infer the "intended" values.
- `persona` — freeform voice/goals text. May be empty: then weigh the
  analytics-derived targets (role_mix, top_skills, build_areas) higher.
- `base_resumes` — active base-resume summaries (slug, health, avg base ATS,
  lift, application counts): what the candidate can credibly apply as.
- `role_mix` / `top_skills` — the demand picture across already-captured JDs.
- `build_areas` — frequent gap skills with KB-evidence status, each carrying a
  `tier`. Read the tier before treating a row as a deficit: only `build` (no
  resume evidence AND nothing in the KB) is something to stretch toward;
  `surface` means the material already exists and just needs porting or
  corroborating; `wording` is a zero-headroom footnote (`n_jobs: 0`,
  `avg_potential_points: 0.0`) and is neither. Weigh `build` rows when choosing
  between borderline postings.
- `referrals` — company + careers_url + has_contact: the warm targets.
- `captured_last_30_days` — role-category counts of recent captures: what is
  already well-covered. Prefer breadth over piling onto a covered category.

## Step 2 — Browse

Priority order:

1. **Referral careers pages** — every `referrals[].careers_url`, warm-contact
   companies (`has_contact: true`) first.
2. **LinkedIn / Handshake searches** — build queries from the brief: base
   resume target roles x role_mix categories x top_skills, constrained by
   `profile` location/relocation. Use an existing logged-in session only;
   never create accounts or work around a login wall.

## Step 3 — Dedupe before extracting

For each promising posting, call `find_job_by_url` with the posting's
canonical URL (exact match — strip tracking query params if the site decorates
links). If `found: true`, skip extraction; note whether `application_exists`
in the session report.

**Aggregator/redirect postings (first live run, 2026-08-01):** postings whose
apply URL resolves through redirect vendors (observed:
`collegerecruiter-redirect.com` chaining into aiapply.co / jobget /
lead-gen pages, with the listing attributed to a different employer than the
posting claimed) are not real employer postings — skip them at hunt time when
the redirect is visible, and report the domain in the digest so it can be
blocklisted. A posting whose "employer" domain immediately bounces through a
third-party redirect vendor is the tell.

**Previously-evaluated captures (2026-08-01):** a found job that already has
base ATS scores but no proposal was evaluated and passed over in a prior run —
skip it, do not re-propose. A job with a **rejected proposal was deliberately
declined**: hard-skip (re-proposing 409s; declines are posting-scoped, so
other roles at the same company remain fair game). The backend additionally
dedupes on `(company, requisition_id)` at capture, so the same requisition
found on a second board returns the tracked row with `already_existed: true`.

## Step 4 — Extract to the JobExtraction shape

Read the full posting and produce one JSON object with exactly these fields
(`backend/app/schemas/job_extraction.py` is the source of truth):

- `company`, `title`, `level`, `employment_type`, `work_mode` — strings or null
- `role_category` — one of `data_scientist | data_analyst | data_engineer |
  ai_ml_engineer | other | unknown`
- `city`, `state`, `country`, `location_raw` — strings or null
- `requisition_id` — the ATS requisition/job ID copied verbatim when the
  posting shows one (Workday `R-…`/`JR…`, Greenhouse/Lever ids), else null;
  never invent or derive one
- `salary_min`, `salary_max` — numbers or null; `salary_period` — e.g.
  `year | month | hour`, or null
- `work_authorization` — `sponsorship_available | no_sponsorship |
  citizen_or_gc_required | unstated`
- `opt_accepted` — `yes | stem_opt_ok | no | unstated`
- `years_experience_min`, `years_experience_max` — integers or null
- `skills` — `[{skill_name, skill_category, requirement_level}]` with
  `requirement_level` one of `required | preferred | mentioned`
- `responsibilities`, `qualifications` — string arrays (may be empty)

## Step 5 — Store

Call `store_extracted_jd(extracted_json, raw_text, source_url)`. Always pass
`source_url`; pass the posting's raw text when you have it (it is the primary
dedupe key). The response's `already_existed` flag is authoritative — report
those hits as "already tracked", never as new captures.

## Step 6 — Optionally score, then report

For the strongest captures, `score_ats(job_id)` (no target = all base
resumes) to rank fit. End the session with a summary table: postings visited,
new captures (company / title / role_category / composite if scored),
`already_existed` hits, inaccessible postings skipped, and any brief
`warnings[]` relayed. All captures await human review in the tracker — this
workflow never applies to anything.
