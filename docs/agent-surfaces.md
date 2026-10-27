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
  **Tool sets**: `profiles.py` owns the allowlists and `orientation.py` the ordered table of what each holds: `profile` (onboarding:
  career history, base resumes and anchors, health check, versions, form answers, preferences), `hunt` (the brief, saving, scoring and
  proposing jobs, referral contacts), `tailor` (saved job to tailored PDF; 31 tools), `apply` (PDF to submitted), `track` (statuses,
  referrals, charts), `templates`, and `full` (94 tools); `/mcp` = `full`,
  `/mcp/{set}` = its allowlist, and `career`/`explore` still serve `profile`/`track` for one release (`PROFILE_ALIASES`).
  Each set's server instructions (`orientation.instructions_for`, under Claude Code's 4,096-character
  cut) say what it holds, the other sets and that the rules hold however the agent talks with the user; every set but templates
  (which has no `get_setup_status`) also says "start with `get_setup_status`" and what its `writer` means, addressing the agent as
  "you, the agent app"; each HTTP set serves the automation playbooks whose `metadata.toolset` names it as MCP prompts (the Copy
  prompt's exact text, from `GET /api/automations`). Pins: `test_profiles.py`, `test_orientation.py`, `test_http.py`,
  `test_http_modern.py`, `tests/test_automations_service.py`.
  **Orientation reads** (no writes): `get_setup_status` (every set but templates: `ai_key`, `writer` ("Who writes" below),
  `demo_bases`, the first undone setup step and its set from the pure `workflow.setup_next_step`, which counts form answers done
  without the diversity answers an agent cannot
  save, the set table) and `get_tailoring_options` (tailor and full: each Quick tailor switch
  with its plain meaning from `QuickTailorProfile`'s field descriptions, the instruction and persona; the presets stay the user's).
  Each set is its own server built from the one registry (`server.build_set`, holding the registry's `Tool` objects): stdio serves
  the set `MAESTRO_CS_MCP_PROFILE` names (default `full`; migration state: §13 `mcp-stdio-venv`), HTTP every set as an
  `http._ServedSet`, which adds the prompts ("The server on SDK 2.x" below).
  Hints use request `CURRENT_PROFILE`, else env (pins: `mcp_server/tests/test_profiles.py`, `test_server.py`, `test_http.py`).
  **KB grooming tools** (`profile` and `full`): `kb_groom_entity` (read-only similar-bullet report per entity, zero LLM calls),
  `kb_combine_points` (fold points into one keeper; the others become its wordings) and `kb_retire_points` (the one way to retire;
  `kb_approve_points` only approves); the two writes share `kb_approve_points`' convention gate and are `destructive=False` because `/career`
  reverses them. `kb_merge_entities(keep_id, merge_id)` is the web's manual merge (`POST /api/kb/entities/{merge_id}/merge`
  `{target_id: keep_id}`; docs/entities/others.md, Career KB), under the same convention gate but `destructive=True`, since nothing
  unmerges; its description names what moves (every bullet state, the wordings, documents and port records), what keep_id absorbs (blank
  fields, missing detail keys) and what is lost (merge_id's title, status, creation record and each value keep_id already holds
  differently). An unknown id is a 404, "The item to merge wasn't found." or "The item to keep wasn't found.".
  `kb_sync_base` keeps a rephrasing as a wording (0.80+) and returns `compared_wording` (docs/entities/others.md, Career KB).
  **Removed names** (`replaced.py`): a call to a tool a change removed (`REPLACED_TOOLS`: the six old analytics tools,
  `get_career_export`, `attach_evidence_file`, `quick_tailor`, `tailor_application`) answers "<name> was replaced by <replacement>.",
  e.g. `explore_top_skills was replaced by explore_trends(view="top_skills").`, not "Unknown tool", on stdio and every HTTP set
  (`server._ServedMCP.call_tool`, which every set's server runs, `full` included); a set that lacks the replacement adds
  the sets that hold it (`…, in the track set.`). A removed argument is refused the same
  way and never acted on: MCPServer drops an undeclared argument, so `kb_approve_points` with a `state` other than "approved" answers
  "kb_approve_points only approves; kb_retire_points retires points." rather than approving drafts the user rejected. Pins:
  `test_replaced.py`, `test_http.py`.
  **Caller-authored twins.** The tools where Maestro's AI writes have caller-authored twins (all but `run_health_check`, which hands the
  judging over instead), so the agent app does the writing when the user's `writer` says so, or with no key in Maestro, and the server
  validates and stores it: `store_extracted_jd` (extraction), `tailor_session(ops=…)`
  (tailoring), `store_cover_letter` (replaces the application's letter, then renders its PDF; a failed render returns `render_error`
  with the letter kept), `store_qa_answers` (replaces the answer to the same question) and `kb_add_points` (DRAFT bullets on an
  existing entity). The store rules: the dash scrub (§6 inv-em-dash) and answers as plain form text, as for generated ones, and the
  voice rule for KB bullets (inv-resume-voice), which `kb_capture` does not apply; a letter and its answers are the owner's first person.
  Enable ONE profile per chat (`full` carries KB writes); `MAESTRO_CS_*` has no legacy fallback. **Apply executor:** headed Chrome (`docs/entities/others.md`, "Attended executor"; apply playbook, "Unattended (full automation)").
  **Plugin:** `plugins/maestro-career-studio/`: Claude Code's `.mcp.json` and Codex's `.codex-mcp.json` connect by URL; Codex prompts for durable decisions, login/upload, health-gate waivers, restores, KB approve/combine/merge/retire and sync. Claude installs use a tagged local checkout; Codex uses a release-tag Git ref and sparse paths `.agents/plugins` + `plugins`; policy `PRIVACY.md`.
  Settings › Agent apps' **Connect an agent app** (`connect-assistant`) selects a tool set and copies commands/URLs, opens install links or downloads the Claude Desktop bundle.
  `GET /api/setup/connect?profile=full` composes values from `MAESTRO_CS_PUBLIC_BACKEND_URL` (default localhost:8000; compose host port unless overridden); `/api/setup/connect/bundle` serves `MCPB_BUNDLE_PATH` (compose read-only mount; `tests/test_setup_connect.py`).
  The dependency-free Node ≥18 `.mcpb` bridges stdio↔HTTP with no assistant-side Docker/Python: `MAESTRO_CS_BACKEND_URL`
  defaults to localhost:8001; `MAESTRO_CS_MCP_PROFILE` selects `/mcp` or `/mcp/{profile}` (no trailing slash).
  Requests are ordered. 2025 traffic (no revision in `params._meta`, or a handshake one: 2024-11-05 to 2025-11-25) holds the
  session, and a stale one (404) replays initialize + initialized before one retry, preserving the initialize's `clientInfo`. A
  message whose `_meta` names a newer revision, such as 2026-07-28, carries `MCP-Protocol-Version`, `Mcp-Method` and, for `tools/call`,
  `prompts/get` and `resources/read`, `Mcp-Name` (`params.name` or `uri`), each through the SDK's header codec (printable ASCII as
  is, else `=?base64?…?=`); it sends and adopts no session, a 404 is the server's answer and is never replayed, and a 4xx carrying
  a JSON-RPC error for its id reaches the client as the server wrote it. Any other non-2xx reads -32000 "Maestro Career Studio
  returned HTTP n." (`mcpb/tests/bridge.test.js`). A re-pack moves `server.json`'s `fileSha256`. `maestro mcp`
  (`maestro_cs/bridge.py`, the uv install's Python twin) carries 2025 traffic only. Each set's `serverInfo.version`, on stdio and
  HTTP, reads `APP_VERSION`, else `dev` (`mcp_server/tests/test_http_modern.py`, `test_profiles.py`).

- **The server on SDK 2.x** (`mcp>=2.3,<3`; `mcp_server/server.py`, `http.py`). `server.mcp`, the one registry, is a `_ServedMCP`
  (the SDK's `MCPServer`); `build_set` makes each set a `_ServedMCP` of its own, and `http.McpEndpoint(registry)` takes any registry
  (tests pass a scratch one) and gives each set a fresh `StreamableHTTPSessionManager` per lifespan run (JSON responses, stateful
  2025 path, 6-hour idle, 16 MiB bodies, SDK DNS-rebinding protection off: §6 inv-mcp-inside-the-app).
  **Every server, the registry included:** the SDK's OpenTelemetry middleware is dropped (the private `mcp.server._otel` import is
  fail-safe and the class is matched by name if it moves, so the app still starts), so a configured Langfuse sees only model calls;
  cache hints say TTL 0, private, for every cacheable method; `subscriptions=False` serves no `subscriptions/listen`, so discovery's
  `listChanged`/`subscribe` flags are false, as in the 2025 initialize; the `mcp.server.mcpserver.server` logger runs at WARNING (at
  INFO it logs each refusal's words); and each set advertises the SDK's empty resources capability, as stdio always did, with
  `resources/list` answering an empty list.
  **Threads:** the SDK runs sync tools on worker threads from anyio's default limiter, which FastAPI's sync endpoints share; over
  HTTP, `http.offload_tools` wraps the registry's `Tool`s (every set holds the same objects) onto `http._LIMITER`'s 8 tokens, reset
  per lifespan, so tool threads waiting on loopback REST never starve REST (§6 inv-tools-off-loop, pinned by `test_http.py`'s
  `test_set_tools_run_on_the_dedicated_limiter`; the single-worker loopback passes either way). Tools read only
  `ctx.session.client_params`; a worker thread never awaits a `Context` method.
  **Refusal words:** each tool's `_guard` turns a `BackendError` into a `ToolError`, read word for word; `_ServedMCP.call_tool`
  translates one raised outside `_guard` ("Error executing tool <name>: <reason>"). Any other exception is a crash: the agent reads
  "Error executing tool <name>" and the log keeps the traceback at ERROR (the owner's call). Input the agent can correct is a
  `BackendError` sentence, never a crash: `image_base64` that isn't base64, an evidence file that can't be resolved or read (or grew
  past 5 MB), NaN, Infinity or a lone surrogate in a request body (checked before anything is sent), and a PDF or upload folder that
  refuses the write, named with `MAESTRO_CS_PDF_DIR` or `MAESTRO_CS_UPLOAD_DIR` (`test_input_refusals.py`). A prompt refusal (an
  unknown playbook, the catalog read failing) is `MCPError(code=0, …)`: code 0 and the same words on both eras.
  **Both protocol eras, one endpoint per set:** the session manager routes on `MCP-Protocol-Version`. None, or a handshake revision,
  takes the 2025 path (initialize, `Mcp-Session-Id`, a 404 for a stale session); a newer one takes the 2026-07-28 path, with no
  handshake or session: each request names its revision, client and capabilities in `params._meta`, `Mcp-Method` and `Mcp-Name` must
  match the body, `server/discover` gives the instructions and capabilities, and `serverInfo` rides in each result's `_meta`. On that
  path `ping` and `subscriptions/listen` answer Method not found, and a protocol error carries HTTP 404 (Method not found) or 400 (a
  bad envelope, or an unsupported revision with the supported list), while tool and prompt refusals stay inside a 200. An unknown
  method answers -32601 "Method not found" on both. `_client_label` reads `client_params.client_info.name`: from initialize on 2025,
  from each request's `_meta` clientInfo on 2026-07-28, else `MAESTRO_CS_MCP_CLIENT`, else nothing. Pins: `test_http.py`,
  `test_http_modern.py` (one test per answer, over both eras where both serve it), `tests/test_mcp_http_loopback.py` (legacy,
  2026-07-28 and auto against a real single-worker uvicorn).

- **Who writes** (`app/agent_writer.py`; SYSTEM.md §6 inv-agent-writer). The saved `mcp_workflow` setting (`McpWorkflowSettings`:
  `hints`, `writer: "agent" | "maestro"`, default `"agent"`) says who writes for an agent request. Only Settings › Agent apps' **Who
  writes for connected agents** card (`agent-writer`) sets it; no tool writes it, and `get_setup_status` reads it back. An **agent
  request** carries `X-Maestro-CS-Origin: mcp`, which the MCP client sends on every call (`write_origin.origin_from` is the one rule
  for that header and its legacy alias); the web app and the Companion send none, so Maestro's AI always writes for them.
  `AgentRequestMiddleware` (raw ASGI, the innermost middleware, pinned) sets a ContextVar mark for the request; `maestro_writes()` is
  true outside an agent request and, inside one, only while `writer` is `"maestro"` (a missing setting reads as the agent app;
  `peek_settings` never seeds a row); `model_available()` also needs a key. While the agent app writes, each writing route refuses an
  agent request with a 409 whose sentence names the agent's own tool, after the error the web gets for an unknown target (a
  404; a 422 for `create_tailoring_session`'s job or base) and, on `tailor_session`, a closed session's own 409:

  | Tool | While the agent app writes |
  |---|---|
  | `generate_cover_letter`, `generate_qa_answers` | 409: write it and save it with `store_cover_letter` / `store_qa_answers` |
  | `kb_capture` | 409: write the bullets and save them with `kb_add_points` |
  | `create_tailoring_session(enrich=True)` | 409: run it without `enrich` (refused before the session is created) |
  | `tailor_session` with neither `ops` nor `no_new_text` | 409: pass your own `ops`, or `no_new_text` |
  | `run_health_check` | no refusal: the agent always judges (`judging`, `judge_health_bullets`), even with a key |
  | resume import | no refusal: `kb_ingest_resume` (`/api/kb/ingest-parsed`) never calls a model; consolidation (`/api/kb/import`, seeding), which no MCP tool reaches, asks `model_available()`, so its no-model path (no warning) serves only the web or seeding with no key |

  The backstop is `llm.call_openai`'s first statement: `AgentWritesError`, which `main.py` answers with a 409, never a 500. **Where the
  mark does not reach:** it crosses `asyncio.to_thread` and anyio's worker threads, not `loop.run_in_executor`, a `ThreadPoolExecutor`
  or a raw `threading.Thread`; and `chat_agent` (the Assistant) and `llm_capabilities` (the probe on a model save) call providers
  outside `call_openai`, neither reachable over MCP. Tool lists are the same under both settings (clients cache them when they connect,
  so the refusal is the source of truth); each writing tool's description says Maestro's AI writes it and names the agent's own tool.
  With `writer` `"maestro"` the routes write with the key as they do for the web, and without a key they return the no-key error (the
  health check hands the judging over instead). Pins: `tests/test_agent_writer.py`, the refusal tests in `test_qa_router.py`, `test_kb_ingest.py`,
  `test_tailoring_sessions_router.py`, `test_resume_lint_router.py` and `test_kb_import.py`, `mcp_server/tests/test_client_origin.py`.

- **What tools send and read.** A status change through MCP (`update_application`, `mark_submitted`) carries the client's name
  (`X-Maestro-CS-Origin: mcp` with `X-Maestro-CS-Origin-Detail`), which becomes the status event's source, "mcp" when the client
  gave none (docs/entities/application.md); `update_application(from_email=True)` sends `status_source: "mail"` for a change the
  mail-status automation read in the user's mail. `get_autofill_profile` returns `work_auth` resolved for the job's country (none
  without one), every country's answers under `work_auth_by_country` (market keys, "UK") and `work_auth_market` naming whose set
  `work_auth` is (§6 inv-work-permit-per-country). `store_extracted_jd` stores `work_mode` and `level` as keys (`on_site`, `senior`)
  and reads a bare "$" as no currency, so the job's country's applies (`salary_currency_assumed`; docs/entities/job.md).
  `explore_trends(view)` reads each view from the REST route its old tool called (`client.EXPLORE_VIEWS`): `top_skills`, `heatmap`,
  `role_mix`, `fit_distribution`, `ats_over_time`, `tailoring_lift`. The job filters (`role_category`, `level`, `employment_type`) go
  to every view but `fit_distribution` (its route takes none), `limit` (1–100) only to `top_skills` and `heatmap`; a filter or limit
  the view does not take is refused ("fit_distribution takes no filters") before any request. `heatmap` rows carry `count` and `of` beside `pct_jobs`, and `role_mix`
  returns every week from the first to the last for every role, 0 where it had none; `explore_gap_frequency` stays its own tool.
  `get_career_context` returns the structured context (`GET /api/kb/context`) or, with `format="markdown"`, the exact career.md text
  (`GET /api/exports/career`). `attach_evidence` takes exactly one of `image_base64` or `file_path` (PNG/JPEG by magic bytes, 5 MB,
  a host `.playwright-mcp/` path read from the container's mount; the bytes never enter the model context), and refuses both or
  neither before an upload. No tool reads Today or the search summary; `set_markets` is the one
  door to the market and money settings, and the explore tools take no period or source.
  **Corrections and kept choices.** `store_extracted_jd(update=True)` corrects a saved posting in place and its `apply_url` records the
  application address (docs/entities/job.md, "Correcting a saved job"). `render_pdf(keep=True)` saves the `template_id` and/or
  `formatting` given on the base (`PATCH /api/base-resumes/{slug}/design`) or the application (`PATCH /api/applications/{id}`) before
  rendering, and the response adds `kept`; `formatting` without `keep` is refused, and only a ready template is kept (a not-ready one
  would fall back to the default on every later render). `list_base_resumes(include_archived=True)` adds the archived bases with
  `archived_at`. `prepare_application_pdf_upload(document="cover_letter")` stages the stored letter's PDF (rendered first when it has
  none) beside the resume's copy under its own file name; with no letter stored it is refused and nothing is staged.
  `update_application(clear=[...])` empties `notes` or unlinks `referral_id` (an explicit null); a field given a value and cleared in one
  call is refused. `save_referral` (hunt, apply, track) POSTs a new referral (company and careers_url required) or PUTs only the
  fields given onto `referral_id`'s; it is `destructive=True`, since an edit keeps no earlier value.
  **The brief** (`get_job_search_brief`) carries `profile.work_auth_by_country` (each apply-in market's yes/no answers, keyed by market),
  the home set `profile.work_auth` named by `work_auth_market` for one release (SYSTEM.md §13 `brief-work-auth-home`), warnings each led
  by its country's name unless the user lives and applies in one country, `last_runs` (each automation's newest run that did not fail,
  by finish time, `agent_runs.last_finished`) and `roles` (the catalog as `{key, label}`). A role the catalog does not know
  (`set_job_preferences`, `create_base_resume_from_kb`'s `role_category`) is refused naming up to three closest roles and the way out
  (docs/entities/others.md, "Role refusals").

- **The health check when Maestro's model does not judge.** No model key is set, or the request is an agent request while the agent
  app writes (even with a key): `run_health_check` then calls no model and returns a report that counts only stored
  judgments (`judged`, null `score`/`grade` while a scored bullet waits) plus `judging`: the app's own evaluator prompt filled with
  the waiting bullets. `judge_health_bullets` (`apply`, `templates`, `full`) sends the agent's answers in that prompt's output
  shape under the client's name; each passes `_validate`, and the report, rebuilt with no model, comes back with `accepted`/`rejected`.
  The write is a 409 only while Maestro's model judges: a key is set and the caller is the web app, or an agent app whose user
  chose Maestro's AI (docs/entities/others.md, "The keyless check").

- **Profile writes** (`set_autofill_profile`, `set_job_preferences`, `set_markets`, `set_persona`; `profile` and `full`, and
  `set_autofill_profile` in `apply` too): an agent writes the facts Setup and Profile ask for, except the AI key and the diversity
  answers. The first three send only the fields passed, in one PATCH (`PATCH /api/settings/autofill`, `/job-preferences`, `/market`),
  and the server reads, merges and writes the setting in one transaction (`text_settings.one_commit`: SQLite's write lock, file mirrors
  written after the commit, a commit inside the block refused), so a save another writer made before the call (a Companion learn, a web
  edit) is kept and none lands between the read and the write (SYSTEM.md §6 inv-mcp-controls). The merge
  (`autofill_profile.patch_profile`, `job_preferences.patch_preferences`, `market_settings.patch_place`): answers key by key, a null
  removing one; work permits per market, keyed from `markets.keys()`; education and languages replace the stored list whole; `custom`,
  the Companion's learn store, upserts by question (case and spacing ignored, same `only_for` and `only_for_kind`) and never removes a
  saved answer, which stays the user's, in Profile; each preference named replaces the stored one (`role_categories` follows
  `favored_roles`); `set_markets` writes the market and money's `home_currency` as one save, both validated before either lands.
  `set_persona` PUTs its text. The web's and the Companion's PUTs still replace the whole setting, and every agent route is a profile
  write, refused on the always-on copy. `set_autofill_profile` has no `eeo` field, the client and the server each refuse any other
  section, the stored `eeo` stays as it was and is never returned, and a call with nothing to save is refused (MCPServer drops undeclared
  arguments). The writes return setup's form readiness. Human-only, with no tool: full automation and auto-apply (§6 inv-auto-consent-gated), EEO
  consent and answers (inv-eeo-standing-consent), the job-site login (inv-job-site-password-local), the Screening answers dial, the
  hints switch, who writes, model keys, prompts and quick tailor (§6 inv-mcp-controls). After `create_base_resume_from_kb` the hint names
  `set_autofill_profile` while setup status reads the form answers as not done.

## Guided tailoring workflow

- **Guided tailoring workflow** (`mcp_server/workflow.py`): wrapped tools carry a `next` envelope
  (`state`/`blocking`/`offer`/`ask_user`/`options`/`call`) that walks §5's arc — score all bases → recommend →
  presets|custom → tailor (which renders the PDF) → render again only when `pdf_ready` is false → apply readiness — unnarrated.
  `workflow.py` is PURE (no httpx/DB/LLM), a
  **deliberate exception to the thin-wrapper rule**: the sequence must live somewhere and a server's
  `instructions` are surfaced inconsistently across clients; purity is what keeps it testable under DB-free
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
  - **Two controls.** `mcp_workflow`'s `hints` (`GET/PUT /api/settings/mcp-workflow` + its card in
    Settings › Agent apps; the same record holds `writer`, MCP server, "Who writes") is the USER's master switch;
    `brief=true` on `score_ats` is the AGENT's, for
    triage loops, checked FIRST so a loop pays no settings read. Tools **always wrap** (`next: null` when
    suppressed) — one tool must not return two shapes per runtime flag.
  - **LLM-free arc.** MCP `create_tailoring_session` defaults `enrich=False`; `use_presets=True` = create + `POST
    .../apply-profile` (deterministic fill from the Quick tailor presets; when the fill fails, the error names the session it
    created, so a retry never loses it) → the agent authors ops → `tailor_session(ops=…)`, or `tailor_session(no_new_text=True)`,
    which writes no new wording; neither calls the backend LLM. Filling precedes authoring so saved resolutions and applied ops
    cannot disagree (§11 item 13). `apply-profile` discards `fill_checkpoint_session`'s standing-instruction return (persisting it
    would break the web path's transience), so the hint carries it as the `tailor_session` option's `user_prompt`, ONLY when the
    session has no note of its own — else the presets over MCP ignore a setting the web obeys. The session hint says who writes the
    edits (`detail.writer`, one settings read): the agent app's ops or `no_new_text` by default, ops omitted when the user chose
    Maestro's AI; its args are the same either way, so with every gap resolved it is the `call` only when Maestro's AI writes.
    **The caller-ops honesty rule is enforced by DOCSTRING, not the server**: `apply_edits` has no honesty
    gate. Keyword survival runs on every path (a saved `add_keyword` the edits leave out lands in the skills
    list, never a bullet: `keywords_added`). `user_input`/`attach_project` answers reach the resume only through the ops, and
    with `no_new_text` not at all: `answers_left_to_ops` names them (with `no_new_text`, also an `add_keyword` whose word needs a
    rewritten bullet). Every tailor returns `unbacked_skills`: missing skills it put on the resume that career history does not back
    (docs/entities/tailoring-session.md). `tailor_session` renders the PDF and reports `pdf_ready`; its hint: `render_pdf` while
    `pdf_ready` is false, else apply readiness (the render hint's readiness and handoff). After `no_new_text` the answers left
    come first (an `edit_application` option with an `ask_user`, and no `call`); after the caller's ops the list may be answers the
    ops wrote, so the same option is conditional and neither asks nor blocks. The server-side evidence gates (`save_resolutions` re-running
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
  on a button or a logo; the connect note shows until a first run reports. The job-hunt and mail-status prompts read from an hour
  before their entry in the brief's `last_runs`, so a posting or mail that came while the last run worked is read too (job-hunt's
  dedup drops what is already saved); with no entry, from their first-run window. Catalog, wrappers and startup rules:
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
