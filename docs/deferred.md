# Known deferred items (overflow)

> Reference tier, extracted from [SYSTEM.md](../SYSTEM.md) (§11 Known deferred items). The header contract there governs this file too: integrate don't append, present tense, update in the same change that alters the behaviour described. A ledger: an item leaves when shipped (git remembers) or when 30 days pass without a "do when" trigger.

**Item numbers are stable, not positional.** Code and migrations cite "§11 item N" from a dozen places, so an item keeps its number here; the gap it left in SYSTEM.md stays, and the seven items read every session stay in SYSTEM.md's §11. Every item ends with its trigger — "do when X", the observable condition that makes it worth building now.

3. Base-score staleness on from-base: re-score only when the base's updated_at is newer than the score row — never unconditionally. Do when a from-base re-score runs on a base whose `updated_at` is older than its score row.
4. JD promoted-field correction before gap freezing (today only source_url is editable) + score provenance
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
34. A model tested with no key is stored as unable to do anything: `NO_KEY_MESSAGE` is not among
    `llm_capabilities._UNREACHABLE_SIGNS`, so the probe counts it as reached and saves text/json/tools all No, and
    `require` then blocks the Assistant until the model is tested again after a key is added. Do when a model tested without a key must work after a key is added.
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
