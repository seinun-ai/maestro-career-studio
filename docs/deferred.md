# Known deferred items (overflow)

> Reference tier, extracted from [SYSTEM.md](../SYSTEM.md) (§11 Known deferred items). The header contract there governs this file too: integrate don't append, present tense, update in the same change that alters the behaviour described. A ledger: an item leaves when shipped (git remembers) or when 30 days pass without a "do when" trigger.

**Item numbers are stable, not positional.** Code and migrations cite "§11 item N" from a dozen places, so an item keeps its number here; the gap it left in SYSTEM.md stays, and the seven items read every session stay in SYSTEM.md's §11. Every item ends with its trigger — "do when X", the observable condition that makes it worth building now.

3. Base-score staleness on from-base: re-score only when the base's updated_at is newer than the score row — never unconditionally. Do when a from-base re-score runs on a base whose `updated_at` is older than its score row.
4. JD promoted-field correction before gap freezing (today only source_url and apply_url are editable) + score provenance
   (engine/config version) surfaced in the UI. Do when a promoted field other than `source_url` needs correcting before gaps freeze, or an engine/config change moves scores.
5. Server-side pagination for the tracker (client caps at 500 rows and says so). Do when a tracker reaches the 500-row client cap.
6. Chat KB document provenance: `ChatAttachment` stores extracted text only, so a chat-added document never becomes a
   KB source document — persist bytes, or hand chat a `kb_ingest_document` tool. Do when a chat-added document has to become a KB source document.
8. Agentic job-search phase 2: JobBoard registry (kind/tags/last_checked), SavedSearch model, Job triage state,
   cross-session search-run logging. Do when a second job board, a saved search or a cross-session search run is wanted.
10. Work-auth warning CODES: `services/job_search_brief` still reads the two legacy keys and pattern-matches loose
    strings in `warnings[]`; it should understand the typed `WorkAuth` shape. Do when `services/job_search_brief` or the `warnings[]` strings it pattern-matches are next changed.
12. Extension identity-combobox reconciliation (ARIA-widget overwrite is riskier), and block-scoped
    education-vs-employment rule matching (`not:` label guards miss unheaded education containers). Do when an ARIA-widget overwrite or an unheaded education-container misfill is reproduced.
14. Telemetry v2: option-set fingerprint + normalization; capture-session record for per-site/per-kind saturation;
    failure-count ranking + Analytics drill-down/export; label/option-text redaction; summary pagination. Do when the telemetry summary saturates per site or kind, or option sets drift between runs.
15. Typst phase 2 (the LaTeX retirement itself is §13): `typst query` AST introspection over source-text capability heuristics; web engine
    picker; in-product .tex→Typst conversion (expose `backend/scripts/template_parity.py --compare` as a backend tool). Do when the LaTeX retirement rows in §13 move, or a template needs more than source-text heuristics.
16. Onboarding intake: entity resolution ACROSS kinds (a certificate merges into its experience entity, not a
    sibling); a re-runnable "import more"; bounding LLM cost (file cap of 10 in `services/kb_import`). Do when an import lands a certificate as a sibling entity, needs a re-run, or hits the 10-file cap.
17. ATS follow-ups: (a) alias/adjacency vocabulary via an OFFLINE human-gated miner over stored `extracted_json`,
    guarded by `SkillMatcher._tokens_contained`; (b) education-as-evidence stays OFF pending a dot-stripping degree
    normalizer; (c) lexical-vs-semantic cert attribution, 1 row in 6,993 — re-check if it grows; (d) stamp `as_of` +
    `jd_extraction_hash` on `AtsScore` and add both to `compare()`'s guard. Do when (c) grows past 1 row in 6,993, or a matcher or tier change lands (calibrate first, §9).
19. Auto-apply follow-ups: `source` threading through the explore builders; Telegram consent channel (rejected for
    v1); extension-less CDP fill (HARD constraint: backend CORS must never admit ATS/web origins). Do when an explore builder needs `source`, a Telegram channel is reconsidered, or an extension-less fill is built.
21. MCP onboarding follow-ups: `near_duplicate_of` hints in the ingest report (normalized-distance vs existing points, so the agent can
    retire one copy without the LLM clusterer); a batch `sources` variant of `kb_ingest_resume` (single-source calls make profile seeding
    order-dependent); a consent story for `_seed_profile`/`_merge_skills` — profile contact and skills have no draft state yet compose onto
    EVERY base; `enabled: false` entries still ingest (LLM-path parity, revisit). Do when an ingest report shows near-duplicate points, a multi-source ingest is needed, or profile seeding order bites.
22. Guided Apply follow-ups (design doc has R2 stepper + R3 vault): checkbox collection needs its own safe design (group-level collection,
    legend-level policy screening, mirroring radios; `skipped_checkbox` holds until then); per-ATS selector blueprints; the essay path onto
    qid-keyed `/choose`; `guidedIsListboxButton` stays looser than the two pinned strict discriminators (it rechecks vetted elements only). Do when a checkbox group must be collected, a per-ATS blueprint is needed, or an essay reaches `/choose`.
24. Surface `schemas/job_extraction._coerce_enum` warnings through the jobs-ingest response, so `store_extracted_jd`
    callers see that input X was stored as `unstated` (audit 2026-08-22, finding A1). Do when a `store_extracted_jd` caller needs to see what was stored as `unstated`.
26. Tailored-studio adoption gaps (`TailoredResumeStudio`): (a) two Saves in one refetch window, the second returning
    to adopted content, read as foreign (`onSaved` queues no key equal to `adoptedKey`): a false "changed outside the
    editor" banner; (b) the parent-held `templateId` never re-syncs from the server, so it survives Rebuild and Load
    latest, and a foreign template-only change reads as an unsaved local edit. Do when a false "changed outside the editor" banner or a template-only foreign change reads as unsaved is reproduced.
27. `FullscreenEditorPage` is `h-dvh` (both studios, the template editor), and `VersionBanner` renders above it in
    `SidebarGutter`, so the page overflows by the banner's height whenever the banner shows. Do when `VersionBanner` shows above a fullscreen editor.
28. Dark `--ring` on `--primary-container` (the FAB) is 2.88:1, so that surface is not in `_RING_SURFACES` (1.4.11). Do when the FAB's dark ring contrast is next adjusted.
29. Focus lands on `<body>` on Escape from the <768px sidebar sheet (which stays open after a nav tap) and after any
    client-side link navigation. `Button nativeButton={false} render={<a>}` announces a link as a button (~40 sites,
    21 files): use `buttonVariants` on a plain `<a>` or `GuardedLink`, the sidebar's pattern. Do when the <768px sidebar sheet or a `nativeButton={false}` link is next touched.
30. Raw keys or jargon still reach the user or an agent: MCP `explore_*` results carry role slugs with no `role_label`; the Assistant's
    Edited and project cards call an application target only "tailored resume"; `resume_diff.attribute` labels any unmatched change `"llm"`
    (the Review changes chip is hidden for it; an `"unknown"` value would change the endpoint's response). Do when a raw slug or an `"llm"` attribution reaches a user or agent on a surface being changed.
32. Small UI gaps: `/base-resumes/<unknown>/health` shows a skeleton ~7 s before its error (the 404 takes react-query's three default
    retries; `app/providers.tsx` sets no `retry`); `/templates`' stale-chip tooltip sits under `GalleryCard`'s `z-10` stretched link; three
    hint/control pairs keep hardcoded ids (`new_id_hint`/`new_id_error`, `kb-profile-notes-hint`, `job-preferences-locations-hint`); Escape
    out of the job Details date field blur-saves `applied_at: null`; an Assistant edit card's Discard stays clickable while Apply runs; a
    failing settings autosave toasts once per keystroke; a failed send in a NEW chat leaves an "Untitled chat" (the session is created
    before the message); the proposal's Overview card shows "expires" on a Queued proposal, which never expires. Do when any of the listed screens is next touched.
33. inv-render-fallback-explained gaps: `PUT /base-resumes/{slug}` commits, then a pdflatex failure is a 500 over the
    saved change; `POST /{slug}/render` answers 500, not 400, on a generic failure; the preview-page route's unlocked
    `exists()` can race a re-render; `STARTER_SOURCE` fails on a blank email with a link present. Do when `PUT /base-resumes/{slug}`, `POST /{slug}/render` or the preview-page route is next changed.
37. ATS reads "Mon YYYY" dates only (`resume_indexer.parse_month_year`): "2021-03", "03/2021", "2021" leave a job
    undated (the UI says so). More formats move scores: calibrate first (§9 `ats_calibration`). Do when a date format other than "Mon YYYY" is needed; calibrate first (§9 `ats_calibration`).
38. A double-clicked "Tailor resume" opens and closes its confirm; with the backend down, every card on Settings,
    Analytics and Career repeats one error (a page-level message needs a shared mechanism). Do when the double-clicked confirm or the repeated backend-down error is reproduced.
39. Windows is unverified end to end: install, update, Companion load from `\\wsl.localhost\...` (GETTING_STARTED
    gives a copy-to-`C:` fallback), `.mcpb` on Windows Claude Desktop, and the WSL upload host root. Do when a Windows install is verified end to end.
40. Companion reliability: ARIA label resolution, retry identity, unmatched combobox discovery, live-option decisions,
    popup ownership and committed-selection verification remain open. Reproductions and Jev-first proposal: [extension
    research report](docs/reports/2026-09-25-extension-reliability-research.md). Do when one of the report's reproductions is worked.
41. Health check follow-ups: one-at-a-time question mode; repeated-opener notes; a rubric check on tailored drafts; a dispute MCP tool
    (disputes are web-only); a **Not right?** reply on a row queued for Write is overwritten by its draft; a hand-set "Shows a result"
    leaves the report, so Done can't reset it; rename `BaseResumeDetail.version_number` to `edit_version_number`. Do when the health check's question mode, disputes or Write queue is next changed.
42. Answer trust follow-ups: fix-and-learn from the receipt; the auto-submit preview; a "What Maestro knows about you"
    page; a JD-extracted graduation/enrollment knock-out; `RECORD_NEVER` folded into `NEVER_FILLED`; receipt capture
    across a full-page navigation and for a manual Attach press. Phase-4 source limits: `docs/entities/filled-answers.md`. Do when the receipt, the auto-submit preview or a JD knock-out is next built.
43. "In N resumes" (`services/career_kb.used_in_bases`) reads `kb_port_log`, which is append-only: it means "added to or came
    from", so it can overcount; `create_from_kb` and base duplication write no rows, so those bases are missed. Do when an "In N resumes" count is next read or shown.
45. Scoring at save is inline: on ingest a background task raced the Companion's own `POST /api/ats-scores` (two `score_all_bases`
    runs collide on the base-score unique key). Revisit with a savepoint-tolerant upsert in `score_target`. Do when ingest latency
    from the inline score is measured or reported.
46. The Companion's `addJob` still scores after its ingest (`panel/actions/job.js`; a harmless second upsert, stale comment), and the
    capture pipeline (`_find_existing`, `_persist_job`, `_insert_skills`, `_score_new_job`) could leave `routers/jobs.py` for a service.
    Do when `panel/actions/job.js` or the capture pipeline in `routers/jobs.py` is next changed.
47. Step 2 offers **Continue gap analysis** on a stale open gap analysis (its base or job changed): `GET /api/tailoring-sessions`
    sets no `stale_reason`, only the single GET does, so only the gap page's banner says so. Do when a stale analysis is reported
    from the job page, or the list endpoint is next changed.
48. The Companion's from-base calls (`panel/actions/track.js` `trackThis`, `actions/job.js` `newResume`) ask nothing: they trust the
    panel's "no application bound" state, so a stale binding over a tailored draft replaces the draft silently (one application per
    job). Do when a Companion from-base call replaces a draft the user did not expect, or the binding logic is next changed.
49. A skills item with a parenthesised list ("AWS (SageMaker, EKS, S3)") reads to the ATS engine as one term, so AWS and SageMaker
    match by alias and gap as **Different wording**, and the resolver auto-fills them; tailoring then adds nothing (the line names them,
    issue #50), but the gap page still lists the fill. `resume_diff.attribute` also labels a whole skills-group hunk by the first
    resolution whose wording appears anywhere in the group, so that line's user-added "MLOps" reads "From your career history". Do when
    the resume indexer's skill splitting is next changed (calibrate first, §9) or a hunk's provenance is reported wrong.
50. Career KB intakes other than base sync keep their own "same claim" test: import
    (`consolidate_deterministic._write_verbatim_points`), the document mint, the gap write-back and the tailoring write-back
    (`tailoring_session._write_back_elicited_points`, `_WRITE_BACK_DEDUP_COSINE` 0.90) each dedup on their own instead of
    `services/kb_claims.place`, so a rewrite arriving there is still a second bullet. Route them through `place` one at a time,
    each with its own tests. A per-claim "Write a neutral version" (one explicit LLM call, a `derived_unverified` draft, never
    automatic) is the only way a claim's line becomes something other than the user's own sentence. Do when one of those
    intakes is next changed, or a user reports a rewrite that arrived as a second bullet by a path other than sync.
51. Tidy bullets limits: **Not the same**'s Undo forgets every pair among the group's ids, including a pair kept apart earlier
    and joined through a third bullet (a faithful Undo needs the POST to return only newly stored pairs plus a per-pair
    DELETE); a group's "% similar" is its strongest pair, so a single-link chain's ends can be further apart (`best_score` per
    member is in the report); a KB-wide "items with similar bullets" count would embed every item on list load. Separately,
    two project items differing only by an em dash versus a hyphen slip past `kb_consolidation.find_near_identity`
    (`_near_project`); merge them by hand meanwhile. Do when Tidy bullets or `kb_groom` is next changed, a wrong Undo or
    label is reported, or a dash-variant duplicate item is reported again.
52. The Companion's deterministic rule pass (`content/autofill.js`) reads one resolved `work_auth` (the job's country's, from
    /context) and cannot see which country a label names, so on a job in one country a work-permit question about another gets the
    job's answers there; only the fill loop (/map, /pick, /step) reads the question's country (inv-work-permit-per-country). The fix
    is the extension's: send a work-permit label that names a country other than the job's to the fill loop instead of the rules.
    The answer flags (`filled_answers.flag_context`) likewise compare with the job's set. Do when the rule pass's work-authorization
    rules are next changed, or a wrong-country answer is reported.
53. Diversity answers are one set for every country: the profile stores one `eeo` set, so Profile and Setup show it wherever an
    apply-in market `offers_eeo` and name those countries, a UK form (the GSS categories) reads the same answers as a US one
    (EEO-1), and a UK-only user's readiness counts the stored US-shaped fields, since the profile has no UK question set.
    Per-country answers need a storage change (`eeo` keyed by market, like `work_auth_by_country`) and a UK question set. Do when a
    second checked set's categories must differ from the stored set's, or a UK-only user reports a US-only diversity question.
54. No payload breaks work authorization down by the countries you apply in: Analytics' Market in detail shows the jobs' stated
    work authorization (the overview's `work_auth` block) and narrows it to one country through the fold's Country filter. A view per
    apply-in country needs an explore payload keyed by market. Do when a per-country work-permit view is asked for, or the overview's
    work-authorization block is next changed.
55. Today's reads never write: `GET /api/today` runs no `proposals.expire_stale`, so a proposal past `expires_at` stays
    `pending_review` until the Agent inbox's next read retires it. Today leaves such a proposal out of next up and of agent jobs to
    review (`proposals.past_expiry`); any other reader that counts `pending_review` must apply the same predicate. Do when another
    reader counts pending proposals, or expiry moves to a write path (at startup, or on each proposal write).
56. A status change found in mail is dated when Maestro learned of it: `update_application(from_email=True)` writes its event at
    the time of the call, not the email's date, so time to hear back from replies the mail-status automation finds runs late by the
    gap between the email and the run. Fix: let `from_email` carry the message's date as the event's `at` (validated, never in the
    future). Do when time to hear back looks long for mail-found replies, or `update_application` or the mail-status prompt is next
    changed.
57. Whole-profile saves have no version check: a `PUT /api/settings/autofill` from a page or a Companion that read the profile
    before another save overwrites that save's answers for the same country (`work_auth_market` protects only other countries'
    answers). It needs an `expected_updated_at` with a 409 when the profile moved, as the resume draft has. Do when a lost
    same-country edit is reported, or the autofill PUT is next changed.
58. The chart palette fails the dataviz skill's validator: chart-3's chroma sits at its 0.10 floor, chart-2 and chart-3 are ΔE 7.3
    apart for protanopia in light, and the dark steps (L 0.72) sit outside its lightness band. The six tokens hold 3:1 on `card` and
    are pinned (`test_frontend_color_roles.py`), so they stay as they are. Do when a chart draws chart-2 and chart-3 as neighbours a
    reader must tell apart, or the palette is next revised (rerun the validator and move the pins with it).
59. A picture from before the refresh: `docs/assets/connected-agents.png` (USING_MAESTRO's Agent apps section) shows the
    old Settings tab; its alt text is current. The design-system previews are listed under "Not synced" in
    `docs/design-system/README.md`. Do when the screenshots are next retaken, or that section of USING_MAESTRO is next
    changed.
60. `frontend/.slopconfig.json` (`allowed_clones`) and `frontend/.slop-baseline.json` still name
    `components/settings/autofill-section.tsx`, which the Profile rebuild split into `components/profile/*`, so the slop ratchet
    (maintainer-run, SYSTEM.md §9) reads a pair that no longer exists. Do when the frontend slop ratchet is next run: drop the pair
    and re-baseline with a reason.
62. Readers still on a job's country TEXT: `base_eligibility`, `inbox_readiness`, `proposals` (the proposal's `job_country`) and
    `explore_gaps` call `countries.normalize(job.country)` instead of reading `job.country_code`, so a job whose country is named
    only in its location line (`countries.for_job`'s fallback) reads as having none there; Analytics' places group the raw state,
    city or country text. Do when one of those readers is next changed, or a job with a location-only country is scored or proposed
    as if it had none.
