# Agent surfaces

> Reference tier, extracted from [SYSTEM.md](../SYSTEM.md) (§7 Agent surfaces). The header contract there governs this file too: integrate don't append, present tense, no dates outside the ledgers, update in the same change that alters the behaviour described. "§N" below cites SYSTEM.md's sections; the invariants named `inv-…` live in its §6.

The four surfaces — the MCP server (**connected agents**), the in-app chat (the **Assistant**), the Chrome extension (the **Companion**) and the Automations page — drive one backend. SYSTEM.md §7 holds the one-paragraph orientation and the index into this file; this file holds how each surface works.

## MCP server

- **MCP server** (`backend/mcp_server/`; on screen **connected agents**, Settings › Agent apps): thin REST wrappers
  (`@_guard` → `ToolError`) via httpx (`BACKEND_URL`, default localhost:8000; compose host 8001). Loopback bypasses proxies; other hosts honor them (`mcp_server/tests/test_client_loopback.py`).
  **The docstring is the API**: behavior, records and requirements, never instructions (directory policy).
  `test_server.py` ratchets `title`, four `ToolAnnotations` (`_read`/`_write`) and ~2048-dedented-char docstrings;
  overflow facts live in param `Field(description=…)` (`_EDIT_OPS_FIELD`). Lists page with bounded defaults;
  `_best_effort_hint` returns `next: null` on a failed lookup after a landed write.
  Coverage: [docs/entities/others.md](docs/entities/others.md), "MCP tool coverage".
  **Scoped profiles**:
  `profiles.py` owns `full` / `hunt` / `apply` / `explore` / `templates` / `career` (95 tools); `/mcp` = `full`, `/mcp/{profile}` = its allowlist.
  Lifespans run fresh stateful JSON sessions; tools use `http.py`'s eight-worker limiter (§6 inv-tools-off-loop).
  Stdio filters `MAESTRO_CS_MCP_PROFILE` (default `full`; migration state: §13 `mcp-stdio-venv`).
  Hints use request `CURRENT_PROFILE`, else env (pins: `mcp_server/tests/test_profiles.py`, `test_server.py`, `test_http.py`).
  **KB grooming tools** (`career` and `full`): `kb_groom_entity` (read-only similar-bullet report per entity, zero LLM calls),
  `kb_combine_points` (fold points into one keeper; the others become its wordings) and `kb_retire_points` (the retire twin of
  `kb_approve_points`); the two writes share `kb_approve_points`' convention gate and are `destructive=False` because `/career`
  reverses them. `kb_sync_base` keeps a rephrasing as a wording (0.80+) and returns `compared_wording` (docs/entities/others.md, Career KB).
  Enable ONE profile per chat (`full` carries KB writes); `MAESTRO_CS_*` has no legacy fallback. **Apply executor:** headed Chrome (`docs/entities/others.md`, "Attended executor"; apply playbook, "Unattended (full automation)").
  **Plugin:** `plugins/maestro-career-studio/`: Claude Code's `.mcp.json` and Codex's `.codex-mcp.json` connect by URL; Codex prompts for durable decisions, login/upload, health-gate waivers, restores, KB approve/combine/retire and sync. Claude installs use a tagged local checkout; Codex uses a release-tag Git ref and sparse paths `.agents/plugins` + `plugins`; policy `PRIVACY.md`.
  Settings › Agent apps' **Connect an agent app** (`connect-assistant`) selects a tool set and copies commands/URLs, opens install links or downloads the Claude Desktop bundle.
  `GET /api/setup/connect?profile=full` composes values from `MAESTRO_CS_PUBLIC_BACKEND_URL` (default localhost:8000; compose host port unless overridden); `/api/setup/connect/bundle` serves `MCPB_BUNDLE_PATH` (compose read-only mount; `tests/test_setup_connect.py`).
  The dependency-free Node ≥18 `.mcpb` bridges stdio↔HTTP with no assistant-side Docker/Python: `MAESTRO_CS_BACKEND_URL`
  defaults to localhost:8001; `MAESTRO_CS_MCP_PROFILE` selects `/mcp` or `/mcp/{profile}` (no trailing slash).
  Requests are ordered; stale sessions replay initialize + initialized before one retry, preserving `clientInfo`
  (`mcpb/tests/bridge.test.js`). HTTP `serverInfo.version` reads `APP_VERSION`, else `dev` (`mcp_server/tests/test_http.py`).

- **What tools send and read.** A status change through MCP (`update_application`, `mark_submitted`) carries the client's name
  (`X-Maestro-CS-Origin: mcp` with `X-Maestro-CS-Origin-Detail`), which becomes the status event's source, "mcp" when the client
  gave none (docs/entities/application.md); `update_application(from_email=True)` sends `status_source: "mail"` for a change the
  mail-status automation read in the user's mail. `get_autofill_profile` returns `work_auth` resolved for the job's country (none
  without one), every country's answers under `work_auth_by_country` (market keys, "UK") and `work_auth_market` naming whose set
  `work_auth` is (§6 inv-work-permit-per-country). `store_extracted_jd` stores `work_mode` and `level` as keys (`on_site`, `senior`)
  and reads a bare "$" as no currency, so the job's country's applies (`salary_currency_assumed`; docs/entities/job.md).
  `explore_skill_heatmap` rows carry `count` and `of` beside `pct_jobs`, and `explore_role_mix_over_time` returns every week from
  the first to the last for every role, 0 where it had none. No tool reads Today or the search summary; `set_markets` is the one
  door to the market and money settings, and the explore tools take no period or source.

- **Profile writes** (`set_autofill_profile`, `set_job_preferences`, `set_markets`, `set_persona`; `career` and `full`, and
  `set_autofill_profile` in `apply` too): an agent writes the facts Setup and Profile ask for, except the AI key and the diversity
  answers. Each PUT replaces its whole setting, so the client reads it, merges in only the fields passed (answers key by key, a null
  removes one; work permits per market, keyed from `markets.keys()`; education, languages and custom whole) and writes it back;
  there is no PATCH route. `set_autofill_profile` has no `eeo` field, the client refuses any other section, the stored `eeo` is
  written back as it was and never returned, and a call with nothing to save is refused (FastMCP drops undeclared arguments). The
  writes return setup's form readiness. Human-only, with no tool: full automation and auto-apply (§6 inv-auto-consent-gated), EEO
  consent and answers (inv-eeo-standing-consent), the job-site login (inv-job-site-password-local), the Screening answers dial, the
  hints switch, model keys, prompts and quick tailor (§6 inv-mcp-controls). After `create_base_resume_from_kb` the hint names
  `set_autofill_profile` while setup status reads the form answers as not done.

## Guided tailoring workflow

- **Guided tailoring workflow** (`mcp_server/workflow.py`): wrapped tools carry a `next` envelope
  (`state`/`blocking`/`offer`/`ask_user`/`options`/`call`) that walks §5's arc — score all bases → recommend →
  quick|custom → tailor → render → apply readiness — unnarrated. `workflow.py` is PURE (no httpx/DB/LLM), a
  **deliberate exception to the thin-wrapper rule**: the sequence must live somewhere and FastMCP
  `instructions=` is surfaced inconsistently across clients; purity is what keeps it testable under DB-free
  `mcp_server/tests`.
  - **Server ranks, agent narrates.** `rank_bases` is deterministic (composite desc, slug tie-break), so
    identical scores always yield the same pick and only prose differs. `close_call` (< `CLOSE_CALL_MARGIN`
    3.0) means present a CHOICE, not a verdict — NOT `auto_apply.auto_pick_margin`, which means "pick without
    asking" in the hunt lane. `coverage_warning` comes off the RECOMMENDED row, not the table:
    `_calc_coverage_signal` compares each resume's OWN matched ratio, so bases can disagree; only
    `extracted_count == 0` is uniform.
  - **`offer` ≠ `ask_user`.** `score_ats` emits only a non-blocking `offer` — mass JD capture scores twenty
    postings in a loop and a question on each would derail it; `ask_user` appears only mid-arc, after the user
    commits. **A hint never names a tool the active profile did not register** (`hunt` has no tailoring tools):
    options AND prose filter via `_active_allowed_tools()`; prose states facts, never commands (`test_workflow.py`).
  - **Two controls.** `mcp_workflow` `{hints: bool}` (`GET/PUT /api/settings/mcp-workflow` + its card in
    Settings › Agent apps) is the USER's master switch; `brief=true` on `score_ats` is the AGENT's, for
    triage loops, checked FIRST so a loop pays no settings read. Tools **always wrap** (`next: null` when
    suppressed) — one tool must not return two shapes per runtime flag.
  - **LLM-free arc.** MCP `create_tailoring_session` defaults `enrich=False`; `quick_tailor` = create + `POST
    .../apply-profile` (deterministic fill) → agent authors ops → `tailor_session(ops=…)` skips the backend
    LLM pass. Filling precedes authoring so saved resolutions and applied ops cannot disagree (§11 item 13).
    `apply-profile` discards `fill_checkpoint_session`'s standing-instruction return (persisting it would
    break the web path's transience), so the hint carries it as the `tailor_session` option's `user_prompt`,
    ONLY when the session has no note of its own — else quick tailor over MCP ignores a setting the web obeys.
    **The caller-ops honesty rule is enforced by DOCSTRING, not the server**: `apply_edits` has no honesty
    gate, keyword-survival is LLM-path only. The server-side evidence gates (`save_resolutions` re-running
    `enable_entry`/`port_kb_point`) still hold.
  - **Apply readiness** reads `setup/status`'s `autofill` block; the server cannot see whether the client holds
    browser tools, so the render offer says the handoff needs them rather than asserting the capability.

## Onboarding workflow

- **Onboarding workflow** (`workflow.py`): `kb_ingest_resume` (drafts) → `kb_approve_points` (the user's gate) →
  `create_base_resume_from_kb` → `render_pdf` (an application render returns a nullable `copy_path`, the visible copy) walks ingest-several
  → KB → role-targeted bases with zero in-house LLM (the client agent parses/authors; ingest the CURRENT resume first — over single-source
  MCP calls `_seed_profile` is first-write-wins). Ingest hints are offer-only (multi-resume loop, same mass-capture lesson as `score_ats`);
  `brief=true` suppresses before any settings read. Hint options carry only verbatim-callable args or none at all, offer prose is derived
  from the filtered options, and composers take the requested state explicitly rather than inferring intent from results. Scoring is
  mentioned in prose, never as an option — it needs a `job_id` no composer can know.

## Automations page

- **Automations page** (`/automations`, under the sidebar's More tools): **Copy prompt** hands work to the user's agent;
  Maestro runs NO scheduler (owner decision D5). Each run prompt ends with MCP `record_run`; a card's status comes only
  from those reports (`GET /api/agent-runs?limit=200`): an automation that reported in the last 14 days is a Reporting card
  (a `DayStrip`, the newest report's outcome and one line, one tonal Copy prompt, one link to the result), the rest are
  short rows, and Recent runs and What each one never does are folds. Never a schedule, a connection state, an app's name
  on a button or a logo; the connect note shows until a first run reports. Catalog, wrappers and startup rules:
  [docs/entities/others.md](docs/entities/others.md), "Automations page"; the run log: docs/entities/agent-runs.md.

## In-app chat (the Assistant)

- **In-app chat**, on screen the **Assistant** (`services/chat_agent.py` + `chat_tools.py`): a distinct toolset (resume edit, KB capture,
  template admin including the mutations MCP deliberately lacks). Its resume-edit tool runs the SAME pipeline as the REST endpoints
  (`services/resume_ops.py`); scope checks and ToolError mapping remain chat-side. Cards, selections and the analytics tools:
  `docs/entities/others.md`, "In-app chat: interaction model". **Pinned-resume resolution**: the pin is a HINT, not a guard (the enforced
  guard is `check_ops_in_scope` over selection PATHS); how it resolves, reloads and follows a changed base is reference tier:
  `docs/entities/others.md`, "In-app chat: pinned-resume resolution". **Social posts**: chat drafts LinkedIn/social posts as copy-out
  markdown — no card, no persistence, the transcript is the history — grounded via read-only `get_career_context`; conventions live in
  chat_system.txt. The router checks the Assistant's key before the capability check (no key → a 422 "The Assistant needs an API key…");
  `run_turn` streams through the adapter; working chips are words (`TOOL_PHRASES`), and deleting a chat asks first. Prompt rows seed at
  startup. `prompts.get_prompt` lazy-seeds only with a caller's session; its own session reads the file default without writing when a row
  is absent. Prompt-file changes need the DB `prompt.chat_system` row reset (Settings › Advanced › AI instructions → Reset to default, or
  delete the row); a deploy uses a SQLite-chain migration that deletes the row only while it still equals the previous default
  (`4022b54933e6` did it for `chat_system`; `tests/test_prompt_sync_guard.py` explains the mechanic).

## Chrome extension (the Companion)

- **Chrome extension** (`extension/`; on screen **the Companion**): MV3; the **side panel** (`panel/`) runs capture and fill; toolbar icon
  (`openPanelOnActionClick`) and hotkey (Alt+Shift+J → `sidePanel.open`, guarded: that method is Chrome 116 and the minimum is 114) both
  open it. Four-stage rail — Job → Resume → Fill → Track — INFERRED from the store by `ns.decisions.stageFor` every render, never set by a
  click. Job = saved AND a base chosen (a pick, the scored best preselected, or a bound application's own `base_resume`); Save job scores
  the bases in the same press, and an unscored saved job is scored once when Job opens. `hasForm` is NOT a stage input. ONE row shows a body
  (the active one, or a DONE row reopened as view state; the active row is the way back). Painted as direction C: a `#progress` bar ("Step N
  of 4", from the active row), the active row as a "Next" card, done rows as compact lines, locked rows hidden by CSS (still in the DOM);
  `scripts/panel_preview.py` renders each state. The footer's one primary follows the OPEN row: Save job (then Update scores), Quick tailor
  (Create PDF when an application lacks its PDF), Autofill; with full automation On the Job step's primary is Apply (below; **Add job**, the Save job press, sits beside it on an unsaved page). The panel document is a family of scripts (panel.html owns roster and order):
  `panel.js` owns the store, the loaders and the generation guard; per-STAGE bodies (`panel/stages/*.js`) get a per-render snapshot,
  per-CONCERN actions (`panel/actions/*.js`) a handle with one `write(patch)` door, and each roster THROWS at boot naming a missing script.
  `panel/icons.js` (`ns.icon`, inline Lucide svg) draws every icon; no emoji or text glyph (`test_extension_panel_icons.py`).
  `shared/status-roles.js` is the application status table the web `StatusChip` shares (`test_extension_status_roles.py`);
  `shared/resume-color.js` the base resume presets (`swatch`; §6 inv-resume-color-identity). `shared/` is what both worlds load: `decisions.js`
  (the ONE home of panel rules), `choose.js` (routing, /choose batch, `rest_fill` shaping, `QUESTIONY`). `guided-run.js` is panel-only.
  Failure copy (never server text; `failureNote`), revisit rules, sender model, COMMIT GESTURE and the ONE `attachableFileInputs`
  definition: `extension/INTERNALS.md`. Never rename bridge storage key `widget.sessions` (tab id → job entry) — that drops every live entry. **Posting identity
  is ONE table in two languages** — `job_url_match.posting_id` ↔ `decisions.postingId` (LinkedIn `currentJobId` / `/jobs/view/<id>`, Indeed
  `jk`/`vjk`, embedded Greenhouse `gh_jid`), pinned by `test_extension_posting_identity.py`; add a key to BOTH. Options (`options.html`,
  `options.js`) read `read_settings`, save `backendUrl`/`appUrl` in `storage.sync` and test `/health`. `scripts/pack_extension.py` gates
  matching versions; store upload and key handoff: `docs/RELEASING.md`. Rest: `extension/INTERNALS.md`.

## Guided fill

- **Guided fill** (design doc `2026-08-16-guided-apply-design`, unpublished — §10): the panel's **Fill** stage — **Autofill** →
  `panel_prepare` (the gesture-backed injection; `preparePage` is the only other) → a run. `fillMode` (`storage.sync`): "Saved
  answers + AI" (default) runs the fill loop (`shared/fill-loop.js`: Stop, report grouped by status, jump via `fill_focus`, `loop_fill`
  telemetry); "Saved answers only" runs the rule pass below; its rows are `reconcileFill`'s buckets plus the run's own
  writeResults-minus-residue, and the EEO row is the BACKEND's standing consent, never a local toggle. It claims `done.fill` (`touched`)
  only when a run both wrote something and left nothing open (a tick hides the open-fields list); a wizard's LATER pages are reached by
  REOPENING the ticked row, and `startFill`'s per-run clear keeps that re-run's report its own. Per stage ONE runner (`ns.guidedRun.runGuidedFill(deps, {aiAssist, applicationId})`; `aiAssist: false` skips `/choose` and
  residues the whole remainder) runs rule pass → collect → one batched `POST /api/autofill/choose` (qid-keyed, ≤40/call; the option guard
  lives SERVER-side only — any answer not among rendered options, invented qid, or skipped qid collapses to abstain) → `ns.guidedWrite`
  sequenced by widget shape with ONE bounded retry. EXCLUDE'd controls a rule tried and missed become RETRYABLES (`ns.lastRuleAttempts`,
  in-memory per run) routed straight to `guidedWrite`, so their identity VALUES never reach `/choose`; its prompt does carry the saved
  answers (EEO only under inv-eeo-standing-consent) and the career history. Readback is timer-sampled and never defaults to failure:
  unconfirmable is `filled_unverified`, not `not_stuck`. Submit stays human at every setting; Next only in the run below. After each run the panel posts the page's answer receipt
  (`shared/receipt.js`) and lists its flags under **Check before you submit**; a matched job's knock-out heads Fill.
  The loop never fills a robot trap (`fillBase.robotTrap`), leaves an optional field with no fact blank (`left_blank`, listed, not asked), reads pills,
  category rows, slow autocompletes, addresses, URLs and split dates as widgets of their own, commits and confirms each item of a list field (up to 20;
  never a closest pick), repeats no move that changed nothing (a run record's `memory` keeps what failed; `only` limits a call to named fields) and
  waits for the page to settle before typing (`extension/INTERNALS.md`, "The fill agent's rules"). **Answers decided in code** (`docs/entities/others.md`; `/pick`, `/step`): "How did you hear" takes the board the job came from (`jobs.referrer_board`, stamped from `services/board_visits`, the last board page the Companion looked up, 20 min, name only), else LinkedIn for a generic "Job board", always `assumed`; `derived.education_level` picks the highest threshold a finished degree meets, never "None of the above"; a "what type of sponsorship" list under a saved No takes none / not applicable (OPT counted as sponsorship uses the saved No: owner decision), else the user's; a saved No over a veteran list with exactly one "I am not a (protected) veteran" option takes it before polarity (`veteran_option`); `/map` is offered ONE start-date fact (the derived date), and a choice field gets the normalised words "Immediately".
  **`/choose` has two engines**, `fast` and `jev` (`llm.autofill_engine`; Settings › Companion › **Form-filling engine**): `docs/entities/others.md`, "Form-filling engines". The second opinions and the fast polarity call get a floor by provider inside the 9 s request budget (Claude 3 s; every other, a custom server and OpenRouter 1 s: `autofill_map.second_opinion_floor`), and the trace names the fact a below-floor `none` fell under (`top_fact`).

## Queued run, one job (Apply)

- **Queued run, one job (Apply)** (`shared/queue-run.js` driver, pure with injected deps; host `panel/actions/run.js`; card `panel/runs.js`; `extension/INTERNALS.md`, "Queued
  run"): with full automation On the Job step offers **Apply**: save, score, pick the resume (never overwriting a tailored draft or an open session), queue as the user's yes
  (consent channel `companion`), then drive THIS tab from the job's apply link (`apply_url`, else `source_url`; http(s) only; started on the job's saved posting it opens the
  saved link; on a job the user picked by hand, THIS page, saved as its `apply_url` if it has none, and `/api/jobs/match` reads both links) through sign-in, fill and Next to
  **Ready to submit**. While it prepares, a live checklist with Stop (taken between steps; what was done stays) shows each step and the base list is locked. Three switches,
  Settings › Companion › How the Companion applies (`companion_apply`, `GET/PUT /api/settings/companion-apply`, synced, read only with full automation On): **Choose the base resume for me** (default
  On: pick only when the top score reaches Auto-apply's floor and margin, else ask), **Stop after each step** (default Off: three presses, the yes at Start filling) and **Think when stuck** (default On, below).
  **Submit is never clicked, at any setting**: `shared/page-kind.js` treats any Submit word, a dialog about submitting or an unseen Submit as the review page (Ready only on a
  real Submit: §6 inv-ready-real-review), and Next is pressed only by `page_advance` (`content/page-reader.js`), which re-sorts the button's labels at click time. A posting's
  Apply (a career site's too, even asking for a new tab: §6 inv-press-filled-page), and a Workday start chooser's Apply Manually link alone, are followed only as a same-tab
  http(s) link (no click handlers) on the first read of a tab the run opened. CAPTCHA, email code, an account on a site it does not know (on a known ATS it creates the account
  itself, §6 inv-job-site-password-local), a job board's own apply, a review page that is not plainly the end, any other start chooser and an unrecognised page with no field PARK (Needs
  you), as does a required field it could not answer, once per page, a refused Next it cannot repair (inv-rejected-next) and a required upload it cannot fill
  (inv-one-resume-write); a required field a search or click landed a value on is listed under **Check before you submit** instead (never a protected one), an optional
  skills box stays empty, and an optional field left blank is listed as "Left blank — optional". The user answers in the page and presses **Resume**: every typed answer is remembered (Undo; long written ones never; also over a page-errors or
  upload park); one naming the job's company or city is held for that job only (`only_for` + `only_for_kind`, whole word, by `autofill_job.profile_for_job` for both `/context`
  and `/choose`; Settings has Use for every job). The hand fix teaches the recipe book (§6 gesture report). A run parked on a step the user does by hand follows them into the tab they
  open (only the application itself or a page the backend matches to the job: INTERNALS), never drives, and waits for one press, **Continue here**; the Job step's **Move the run to this tab** does
  the same from the other side; a driving run never moves. The user's own Submit is recorded only from a confirmation page on a host the run reached at the same employer,
  straight from the application's own pages, after an 8 s Undo (a tab closed during it marks at once); any other page sets `noAutoMark`, leaving the manual Mark applied, and
  Done on the Ready card ends the record writing nothing (per-run limits, leases and Apply on a live tab: INTERNALS). The Ask box (QnA drawer) sits under the run card only
  while the run is paused. The job memory is per tab (`chrome.storage.session` `widget.sessions`, no clock; origin, tenant, sibling-posting and backend-wins guards).

## Pages of web components

- **Pages of web components** (`ns.deep`, `content/detect.js`, a re-run file; INTERNALS, "Open shadow roots"): the page reader, fillable count, upload reader and `detectPage` read OPEN shadow roots as one composed tree (closed roots stay invisible), a host speaks for a control only when its root holds that one control, and an unknown first page the fill inventory lists fields on (search boxes and rich text left out) is filled, never parked "Page not recognised" and never Ready; the vendor's easy-apply box is a parser, a visible DataDome frame a CAPTCHA wall.

## Reasoning step

- **Reasoning step** (`shared/reason-loop.js`, host `panel/actions/reason.js`, `POST /api/autofill/reason`, Companion origin only; INTERNALS, "The reasoning step"): before a run parks on errors it
  could not map, open questions, an unknown page, no change, a loop or another site (never a wall, a review page with no fields, **Stop after each step** On or **Think when stuck** Off; a one-page form, a step-0 review page with fields, is worked on open questions and page errors with `one_page: true`: fields only, nothing pressed), the **Reasoning model** sees
  a value-free snapshot and names 1–3 actions the backend checks (ids, protected list, failed signatures); `write`/`choose`/`answer_from` run through `/choose`, `/pick` and `/map`, so no value comes
  from the model; 3 rounds, a minute a page; each round goes to the fill log (`reasoning`), replayable with `scripts/eval_reason.py`. A parked card speaks in the code's words (what it asks, else "It tried …; it took / it didn't take"), never the model's note.

## Screening answers dial

- **Screening answers dial** (Settings › Companion, under the agreements switch; `autofill.answer_level`, default **Balanced**, so an install that had
  the old low-stakes switch off now answers low-stakes questions; the one setting for the Companion, `/map` `/pick` `/step` and agents, via
  the brief's `applying.answer_level`; stored `facts`/`history`/`queued`, shown as the levels below): **Careful** (saved answers and history), **Balanced** (also low-stakes kinds in the
  job's favour, and "N years of a skill" Yes when the history shows it), **Confident** (also every requirement question Yes,
  and a years question Yes only when the history is silent or shows enough, else asked; only for the job's own posting: accepted/approved
  proposal plus `page_url` `is_same_posting` against `apply_url`/`source_url`). The protected list sits outside every level and parks unless
  a saved fact answers it: work authorization and sponsorship, salary, EEO (unless consented), criminal or background history, termination,
  agreements, debarment, clearance and agency employment (never a keen guess), signatures, attestations and authorization boxes (unless Agreements
  consent), licences, unsupported education or experience claims, the applicant's own military service. **Safe defaults** (owner; History level up): a status the profile lacks and that only
  adds something (tribal, union or association membership, a referral, a relative or household member at the company, a spouse's or household member's military
  service) is No (Not applicable, or "I don't wish to answer", if offered);
  willingness or consent to a standard pre-employment step (background check, drug test, references, I-9/E-Verify, documents; also when the model filed it as protected, but only as a question, never a first-person box, a pass/clear/eligibility/proof or a history) and basic means
  (transport, internet) is Yes; a "no fact" answer at any probability reaches the judge unless a second opinion named a fact. Every dial answer is marked on the receipt, so defaults are listed under **Check before you submit**; written drafts: §6 inv-drafted-answers.

## Streaming chat

- **Streaming chat** runs through `llm_providers` on any provider; eligibility is the tools probe.
