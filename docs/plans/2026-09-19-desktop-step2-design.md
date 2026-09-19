# Desktop step 2: engines that explain themselves, MCP over HTTP — design

Status: approved in brainstorm 2026-09-19, awaiting implementation plans.
Scope: `backend/`, `frontend/` (templates gallery, setup checklist, one
Settings section), `extension/` (options page, packaging), `mcpb/`,
`plugins/`, `docker-compose.yml`, CI, docs, SYSTEM.md.
Predecessor: `2026-09-17-sqlite-migration-design.md` (merged to `main` at
`2526d367`). Successor: the desktop shell (step 3).

## Goal Card

**Goal:** A fresh install with no TeX, no host Python and no Docker on the
client side renders its first PDF and connects any MCP-capable assistant
in under a minute, while a compose install sees no behaviour change it did
not ask for.

**Principles** (how to decide when the plan is ambiguous or wrong):
- Both engines stay first-class and LaTeX stays the default wherever TeX
  exists. SYSTEM.md §13 `typst-default-flip` is HELD by the owner; nothing
  here flips, repoints or retires it.
- Explain, never substitute silently. Every fallback names itself in the
  response, in the UI and in `setup/status`.
- One supported path per client after one release. Old routes get a §13
  ledger row with a removal trigger, the same pattern as Postgres.
- `/mcp` shares the REST trust boundary exactly: loopback bind, the
  existing Host → Origin → CORS stack, no second security definition, no
  second port.
- Docker stays the contributor path. Nothing here needs a host toolchain to
  develop, and the Dockerfile is not touched.
- Do not fix unrelated things while in there. The one adjacent fix taken
  (§11 item 7) is taken because this design writes the tests it was
  waiting on.

**Non-goals:** the desktop shell; upgrading the `mcp` SDK past the 1.29.1
lock (2.x exists and is a separate change); flipping the default engine;
remote or authenticated MCP; claude.ai and chatgpt.com (they take public
HTTPS connectors only); cover letters as registry templates; `typst query`
introspection (§11 item 15); the Chrome Web Store submission itself (an
owner task with a checklist here).

**Autonomy:** peer. The executor may adapt *how* when the repo disagrees
with this doc, must log every deviation with a one-line reason, and is
invited to flag anything here that contradicts the Goal Card. Scope is
never self-expanded.

## 1. What the code says today, and what was verified

Read on 2026-09-19 against `main` at `2526d367`:

- `pdf_render.py` has two `pdflatex` subprocess call sites (`compile_pdf`,
  `render_and_compile`) and one in-process Typst path (`typst_compiler`,
  sandboxed, 60 s cap, `@preview` imports rejected). No code probes for
  `pdflatex`; a missing binary is an unhandled `FileNotFoundError`, a 500.
- Six seeded templates: four LaTeX (`default` Classic, `xcharter_serif`,
  `carlito_dense`, `harshibar`), two Typst (`typst-classic`,
  `xcharter_serif_typst`). `get_usable_template` already falls back to the
  default when a template is not `ready`. `_seed_validate` runs each seed
  once per process; a failed validation records `last_error`.
- Cover letters ignore the registry: `routers/qa.py:render_cover_letter`
  renders `cover_letter.tex.j2` + `_header.tex.j2` and calls
  `compile_cover_letter_pdf`. LaTeX-only, the last document without a
  Typst path. §11 item 7 (contact URLs through `latex_escape` instead of
  `latex_escape_url` in `_header.tex.j2`) is open for want of exactly the
  cover-letter regression tests this design adds.
- Renders already return `resolved_engine` and `resolved_template_id`
  (`RenderResult`, base-resume response), transient, set after commit.
- `setup/status` has no engines block. `SetupStatus.template.detail` is
  the natural home for "is the default's engine available".
- The MCP server is stdio only (`mcp.run()`), 83 tools, six profiles
  applied at import by deleting from `_tool_manager._tools`. Every tool is
  sync, wrapped by `_guard`, and calls the backend over sync httpx.
- Three install routes: the `.mcpb` (a Node shim running `docker exec`),
  the Claude Code and Codex plugin marketplaces (`docker exec` in
  `plugins/maestro-career-studio/.mcp.json`), and `scripts/setup-mcp.sh`
  (a host venv, needs Python 3.12+). `compatibility.platforms` is
  `["darwin"]`.
- The extension pins a manifest `key` (id `pjmfonfapjdabkoicnelpflpjojdjgan`),
  has no `options_ui`, and reads `chrome.storage.sync` over `sw.js`
  `DEFAULTS` (`backendUrl: http://localhost:8001`). A store install cannot
  edit `sw.js`.
- `docker-compose.yml` binds the backend to `127.0.0.1:${BACKEND_HOST_PORT:-8001}`
  and sets `MAESTRO_CS_UPLOAD_*` on the backend service already.

Verified during the brainstorm (interpreter `/opt/anaconda3/bin/python`,
`mcp` 1.26.0; the lock is 1.29.1 and the plan re-verifies there):

| Fact | Consequence |
|---|---|
| `FastMCP.streamable_http_app()` exists, with `stateless_http`, `json_response`, `transport_security` settings; DNS-rebinding protection is OFF by default. | The app's own Host → Origin → CORS stack stays the single definition. |
| `FuncMetadata.call_fn_with_arg_validation` calls a sync tool directly on the event loop. | Mounting in-process with sync httpx self-calls deadlocks a single-worker uvicorn unless tools run off the loop. |
| An `async` `functools.wraps` wrapper running the tool via `anyio.to_thread.run_sync` keeps the input schema (`ctx` hidden) and `Context` injection; the tool ran on an AnyIO worker thread. | `_guard` is the one place to make every tool off-loop. |
| Stateless mode creates a fresh server session per request; stateful mode keys sessions by `Mcp-Session-Id`. | Stateless would drop `clientInfo`, which `_client_label` puts on KB timeline rows. Use stateful. |
| Claude Desktop custom connectors require a public HTTPS URL; `localhost` is refused. | Claude Desktop keeps needing a stdio process: the `.mcpb` stays, its shim becomes an HTTP bridge. |
| The MCPB manifest spec (0.3; 0.4 current) supports `node`, `python`, `binary`, `uv` process types only, no URL servers; `platform_overrides` and `compatibility.platforms` exist. | Same conclusion; a pure-Node bridge makes the bundle cross-platform. |
| Codex: `codex mcp add <name> --url <url>`; Claude Code: `claude mcp add --transport http <name> <url>` and `.mcp.json` `{"type":"http","url":…}`; Cursor: `cursor://anysphere.cursor-deeplink/mcp/install?name=…&config=<base64 json>`; VS Code: `vscode:mcp/install?<url-encoded json with type:"http">`. | The connect page is string composition, done server-side so pytest pins the formats. |
| Chrome Web Store forbids `key` in the manifest on the FIRST upload and assigns its own id; afterwards the store's public key goes into the manifest so every build hashes to that id. 2026 policies (enforced since 2026-08-01) require a privacy-policy URL even for unlisted items and a written justification per broad permission. | The committed key changes once; two ids coexist for one release; store materials live in the repo. |
| `typst` 0.15.0 is the latest on PyPI. | Nothing to upgrade. |

## 2. Engines

### 2.1 Probe (`app/services/engines.py`, new)

`EngineStatus {name, available, version, path, reason}` and
`EnginesStatus {pdflatex, typst}`.

- `pdflatex`: `settings.pdflatex_path` (env `MAESTRO_CS_PDFLATEX`) wins
  when set, and a wrong value FAILS (reason recorded, no search): an
  explicit setting is not a hint, the MCPB shim's Docker-path precedent.
  Otherwise `shutil.which("pdflatex")` over `PATH` extended with the TeX
  homes a GUI-launched process never has on its `PATH`:
  `/Library/TeX/texbin`, `/usr/local/texlive/*/bin/*`, `~/.TinyTeX/bin/*`,
  MiKTeX's per-user bin (`%LOCALAPPDATA%\Programs\MiKTeX\miktex\bin\x64`)
  and `C:\texlive\*\bin\windows`. One `--version` run confirms it.
- `typst`: in-process; version from the package; `available` also requires
  every `settings.typst_font_paths` entry to exist (typst falls back to
  embedded fonts silently, which is how a font regression would hide).
- Cache: the `--version` result is kept per process, keyed by the resolved
  path; `which` is re-run on every call (microseconds). Installing TeX
  while the app runs is noticed on the next probe with no restart.
- `_pdflatex_argv` uses the resolved absolute path as `argv[0]`, so the
  subprocess finds TeX wherever the probe found it.

### 2.2 Fallback rule (`pdf_render`)

`resolve_render_template(template_id, session) -> (Template, note | None)`:
resolve as today (`get_usable_template`), then apply ONE rule: engine is
`latex` and `pdflatex` is unavailable → substitute the first ready Typst
template in the order default-if-Typst, `typst-classic`, any ready Typst.
None ready → `ValueError` (400): "This template needs TeX, which is not
installed. Install TeX or pick a Typst template." The note reads "TeX is
not installed on this machine; rendered with {typst display_name} instead
of {latex display_name}."

- Used by `render_document` and `render_and_compile` (all resume renders)
  and by the cover letter (§2.3). NOT used by template validation:
  validating a LaTeX template without TeX reports "requires TeX (pdflatex
  not found)" cleanly and never validates a different template.
- `RenderedDocument.render_note`; `RenderResult.render_note` and the
  base-resume response gain `render_note: str | None`, transient like
  `resolved_engine`. Null on every render where nothing was substituted.
- `compile_pdf` and the second call site map `FileNotFoundError` to a
  `RuntimeError("pdflatex is not installed …")`, belt and braces for any
  path that bypasses the resolver.

### 2.3 Cover letter on both engines

- New bundled `templates/cover_letter.typ`, self-contained (its header
  mirrors `_header.tex.j2`: name, contact line, links; XCharter from the
  vendored font dir so the two engines look alike). Data via `sys_inputs`
  like resumes: `contact`, `today` (already formatted), `paragraphs`,
  `fmt` (`merge_formatting(None)`).
- `routers/qa.py:render_cover_letter` resolves the application's resume
  template exactly as `application_render.render_resume` does, applies the
  fallback rule, and renders with that engine. LaTeX-template users with
  TeX see no change; Typst-template users and TeX-less installs get Typst.
  `compile_cover_letter_pdf` becomes engine-dispatching and keeps its name
  (the §13 `latex-render-path` row tracks it by name).
- Parity test: one body through both engines, extracted text equal modulo
  whitespace (pypdfium2, the current extractor).
- §11 item 7 fixed here: contact URLs in `_header.tex.j2` go through
  `latex_escape_url`, with regression tests for BOTH `resume.tex.j2` and
  `cover_letter.tex.j2` (a `~` in a URL must survive). Item 7 is deleted in
  place.

### 2.4 Seeds, gallery, picker

- `_seed_validate` short-circuits a LaTeX seed when the probe says
  unavailable: `last_error = "requires TeX (pdflatex not found)"`, status
  stays `draft`, and the per-process attempt guard is NOT consumed (only a
  real compile attempt consumes it), so the next `GET /api/templates` after
  TeX appears validates it without a restart. Typst seeds are unaffected.
- `TemplateSummary` and `TemplateDetail` gain `engine_available: bool`,
  set by the router from one probe per request. The gallery card and the
  picker show "requires TeX" on LaTeX templates while TeX is absent;
  picking one is allowed (the render explains its fallback).
- `SetupStatus.engines: EnginesStatus`; `template.detail` gains
  `default_engine_available`. The getting-started checklist shows one row:
  "Typst ready · TeX not found (LaTeX templates render with Typst
  Classic)", or "Typst ready · TeX 2025 (pdflatex)".
- MCP passthrough: `list_templates`/`get_template` carry
  `engine_available`; `render_pdf` carries `render_note`;
  `create_template_draft`'s docstring says a LaTeX draft cannot validate
  without TeX. All DB-free changes in `mcp_server/`.

### 2.5 Docker and dev hosts

The image keeps its slim TeX Live; the probe reports available;
`render_note` is null on every render (a gate asserts it). On a dev host
TeX becomes optional: SYSTEM.md §9 stops requiring `/Library/TeX/texbin`
on `PATH` for the suite (LaTeX compile tests skip with the probe's reason,
never silently pass).

### 2.6 Tests (engines)

Probe with monkeypatched `which` and override (wrong override fails,
version cached per path, re-`which` per call); resolver (latex→typst
order, no ready Typst → 400, Typst templates untouched, `render_note`
wording); `render_note` on both render routes; cover letter compiles on
both engines plus parity; `_header.tex.j2` URL escaping on both
templates; seed validation without TeX (draft with reason, guard not
consumed, heals when the probe flips); `setup/status` engines block;
`engine_available` on list/detail; MCP passthrough in `mcp_server/tests`.

## 3. MCP over HTTP

### 3.1 Serving (`app/main.py`, `mcp_server/server.py`)

- `mcp_server.server.mcp` is built with `json_response=True` and stateful
  sessions (the default). `app.mount("/mcp", <profile wrapper>)` where the
  wrapper (§3.3) delegates to `mcp.streamable_http_app()` with
  `streamable_http_path="/"`. The existing lifespan runs
  `async with mcp.session_manager.run():` after `seeding.run_startup()`.
- `_guard` becomes `async def`, runs the tool through
  `anyio.to_thread.run_sync`, keeps `functools.wraps` (signature, `ctx`
  injection) and the `BackendError → ToolError` mapping. Tools stay sync,
  thin and DB-free; `mcp_server/tests` keep calling them as today.
- In-process tools call the backend over loopback. `BACKEND_URL` keeps its
  default `http://localhost:8000` (the container's own port); a venv dev
  run sets it to its uvicorn port (§9 note). Loopback requests carry a
  `Host` on the allowlist and no `Origin`, so they pass the guards.
- Sessions are in-memory; a backend restart invalidates them. URL clients
  re-initialize on their own; the bridge heals (§3.4).
- JSON responses are pinned by a test: nobody flips `json_response` to
  SSE without the bridge test failing.
- `mcp` moves from the `[mcp]` extra into core dependencies (the backend
  now imports `mcp_server` at startup). The lock diff is a move.

### 3.2 Security

Nothing new to configure: `/mcp` is inside the app, so the loopback bind,
`TrustedHost`, `OriginGuard` (absent `Origin` allowed for non-browser
clients, present-but-unlisted refused) and CORS already cover it. The SDK's
own DNS-rebinding protection stays off, on purpose: one definition, two
readers, as `app/main.py` already says. Pinned: forged `Host` → 400 and
foreign `Origin` → 403 on `/mcp`. README and SECURITY.md replace "keep the
transport STDIO" with the true rule: never publish port 8001 beyond
loopback and never proxy `/mcp` publicly, exactly like REST.

### 3.3 Profiles by path

`/mcp` serves `full`; `/mcp/hunt`, `/mcp/apply`, `/mcp/explore`,
`/mcp/templates`, `/mcp/career` serve the scoped sets; anything else → 404.
`apply_profile_filter`'s import-time deletion cannot serve six sets from
one process, so it becomes a request-scoped filter: a small ASGI wrapper
reads the first path segment into a `ContextVar` (default: the
`MAESTRO_CS_MCP_PROFILE` env, so stdio uses the same mechanism) and
rewrites the path; the low-level `list_tools` and `call_tool` handlers
filter through `profiles.allowed_tools()` (a hidden tool called by name
raises `ToolError`); workflow hints read the same variable.
`list_registered_tool_names()` reads through the filter. One mechanism,
one allowlist source.

### 3.4 The bridge (`mcpb/server/index.js`)

A zero-dependency stdio↔HTTP bridge on Node ≥ 18's built-in `fetch`,
replacing the `docker exec` shim:

- Each stdin JSON-RPC line is POSTed to `${backend_url}/mcp[/profile]`
  with `Accept: application/json, text/event-stream`, `Content-Type:
  application/json` and `Mcp-Session-Id` once known (taken from the
  `initialize` response header). A JSON reply goes to stdout, one line;
  202 (a notification) writes nothing; any other status becomes a JSON-RPC
  error with the request's id. Batches pass through untouched.
- 404 on a known session: replay the cached `initialize` and
  `notifications/initialized`, adopt the new session id, retry the message
  once. A backend restart mid-chat heals without restarting the client.
- Connection refused: one sentence on stderr ("Maestro CS is not running:
  `docker compose up -d`, or open the app") and a JSON-RPC error to the
  client. Stdout never carries anything but JSON-RPC.
- `manifest.json`: `user_config.backend_url` (string, default
  `http://localhost:8001`) and `profile`; `container_name` and
  `docker_path` go; `compatibility.platforms` becomes
  `["darwin","win32","linux"]`; `manifest_version` stays `0.3` unless the
  packer requires `0.4`. `scripts/check_mcpb_bundle.py` is unchanged in
  shape (two tracked files).
- `mcpb/tests/shim.test.js` is rewritten against an in-test `node:http`
  fake (session header, 202, 404 replay, refused connection, JSON-only
  stdout), so it runs everywhere, not only where Docker exists.

### 3.5 Connect endpoint and page

- `GET /api/setup/connect` → `ConnectInfo {backend_url, mcp_url,
  profiles: [{name, url}], bundle_available, clients: [{id, label, kind:
  "command" | "deeplink" | "url" | "download", value}]}`. `backend_url` is
  `settings.public_backend_url` (env `MAESTRO_CS_PUBLIC_BACKEND_URL`);
  compose sets it to `http://localhost:${BACKEND_HOST_PORT:-8001}`; the
  default is `http://localhost:8000`. A `?profile=` query rewrites every
  value. Link composition is server-side so pytest pins the formats:
  Claude Code (`claude mcp add --transport http maestro-career-studio
  <url>`), Codex (`codex mcp add maestro-career-studio --url <url>`),
  Cursor (base64 of `{"url": …}`), VS Code (URL-encoded
  `{"name","type":"http","url"}`), Claude Desktop (download), anything
  else (the raw URL).
- `GET /api/setup/connect/bundle` serves the packed `.mcpb` with
  `FileResponse` from `settings.mcpb_bundle_path` (default
  `/app/mcpb/maestro-career-studio.mcpb`; compose adds `./mcpb:/app/mcpb:ro`);
  absent → 404 with a hint, and the page shows the clone path instead.
  The path is fixed configuration, never request input.
- Frontend: `components/settings/connect-section.tsx` ("Connect your
  assistant") renders the rows with copy buttons and deep-link buttons and
  a profile chooser; the getting-started checklist gains a row linking to
  it. No new state, no new hooks beyond one query.

### 3.6 Declarations, examples, deprecations

- `plugins/maestro-career-studio/.mcp.json` → `{"maestro-career-studio":
  {"type": "http", "url": "http://localhost:8001/mcp"}}`. The Codex
  marketplace shares that file; the plan verifies Codex's plugin
  `.mcp.json` accepts a `url` entry, else Codex keeps a `docker exec`
  entry for this one release and its users take the `codex mcp add` line
  from the connect page.
- `claude_desktop_config.example.json` shows the bridge form (`node
  <clone>/mcpb/server/index.js` with `MAESTRO_CS_BACKEND_URL`,
  `MAESTRO_CS_MCP_PROFILE`); `codex_config.example.toml` shows the `url`
  form.
- New §13 row `mcp-stdio-venv`: this release `scripts/setup-mcp.sh` still
  works and prints a deprecation banner plus the HTTP one-liners; the
  removal trigger is the next release after the connect page ships, and
  the deletion is the script, the venv paragraphs in README and
  GETTING_STARTED, and the `docker exec` examples.
- `docs/GETTING_STARTED.md` §6 becomes three routes: Claude Desktop (the
  bundle), URL clients (paste or click), legacy stdio (one release).

### 3.7 CI and tests (MCP)

- The `mcp-cold-install` job stops needing Docker: install the backend,
  start uvicorn on a temp SQLite dir, POST `initialize` → `tools/list` →
  one read tool on `/mcp`, then `node --test mcpb/tests`.
- In the suite: the load-bearing single-worker loopback test (spawn
  `uvicorn app.main:app`, drive `/mcp` end-to-end including a tool that
  calls the backend, inside a timeout, marked `integration`); `_guard`
  keeps the schema and runs off the loop; profile paths list exactly their
  allowlists and reject hidden tools; unknown profile → 404; `json_response`
  pinned; forged Host / foreign Origin on `/mcp`; `ConnectInfo`
  composition (both encoders, `?profile=`, bundle 404); the bridge's
  `node:test` suite.

## 4. Store readiness (code now, listing when you are ready)

- `extension/options.html` + `options.js` (`options_ui`, embedded) edit
  `backendUrl` and `appUrl` into `chrome.storage.sync` with a "Test
  connection" button against `${backendUrl}/health` (the extension origin
  is already on the CORS allowlist). `sw.js` `DEFAULTS` stay the fallback;
  the panel already reads through `read_settings`.
- `scripts/pack_extension.py` (stdlib only): zips `extension/` minus dev
  files into `dist/maestro-cs-companion-<version>.zip`, `--first-upload`
  strips `key`, the version must match `backend/pyproject.toml`.
- `extension/STORE_LISTING.md`: the single-purpose statement, the
  per-permission justification (`storage`, `tabs`, `webNavigation`,
  `scripting`, `sidePanel`, and the all-URL host permission: the panel reads
  whatever posting or ATS page the user opens), "no remote code", "no data
  collected by the developer", and the screenshot list (five, 1280×800).
- `docs/PRIVACY.md`: the policy text to publish at
  maestrocareerstudio.com/privacy. Everything stays on the machine; the
  only outbound calls go to the LLM provider the user configured; telemetry
  stays in the local database; no accounts, no analytics, no sale of data.
- `docs/RELEASING.md` §10 "Chrome Web Store": account, first upload
  without `key`, copy the store's public key into `manifest.json` (from
  then on every build, unpacked included, hashes to the store id), append
  the store id to `maestro_cs_extension_ids`' default, unlisted first,
  listed after review passes.
- New §13 row `extension-id-swap`: once the store key is committed, the
  old id `pjmfonfapjdabkoicnelpflpjojdjgan` stays in the default allowlist
  for one release (existing unpacked installs keep it until reinstalled),
  then is deleted with its README note.

## 5. Rollout

1. Branch `engines` (§2): probe, fallback, cover letter, seeds, gallery,
   setup status, MCP passthrough, docs. Merge.
2. Branch `mcp-http` (§3 and §4): guard, mount, profiles by path, bridge,
   connect endpoint and page, declarations, deprecations, store-readiness
   code, docs. Merge.
3. One release carrying both, with two notices: MCP clients should move
   to the URL now (stdio-venv leaves next release); the extension gained
   an options page, store listing pending.

Each branch is executed the same way as step 1: subagent-driven, one
fresh subagent per task, two-stage review, an append-only deviation log
and a gate table in the plan.

## 6. Documentation and SYSTEM.md

Docs touched: README (MCP section URL-first, extension section, Updating
reminders), `docs/GETTING_STARTED.md` (§6 and Part 3), SECURITY.md (`/mcp`
boundary), KNOWN_ISSUES.md (TeX optional, profiles by path, store status),
CHANGELOG.md, `backend/mcp_server/README.md`, `extension/README.md`
(options page, id swap), `docs/RELEASING.md` (§10).

SYSTEM.md is at 999 of 1000 lines. Every edit is net-zero or paired with
grooming of the sections it touches, word-stream verified as in step 1;
the cap is not raised. Changes: §2 and §3 (engines.py, connect route,
bridge, `/mcp` on the backend); §6 three pinned invariants,
`{#inv-render-fallback-explained}` (a render never changes engine
silently; `render_note` says why), `{#inv-mcp-inside-the-app}` (`/mcp` is
mounted in the FastAPI app so one Host → Origin → CORS policy covers it;
never a second policy or port), `{#inv-tools-off-loop}` (every MCP tool
executes off the event loop; the loopback test is the pin); §7 transport
paragraph rewritten (HTTP + bridge, profiles by path, `mcp.run()` no
longer "stdio only"); §9 (host TeX optional, `BACKEND_URL` for loopback,
`MAESTRO_CS_PUBLIC_BACKEND_URL`, `MAESTRO_CS_PDFLATEX`); §10 lineage line;
§11 item 7 deleted in place; §12 three dated gotchas (GUI `PATH` has no
TeX; stateless HTTP drops `clientInfo`; mount path composition); §13 rows
`mcp-stdio-venv` and `extension-id-swap` added, `latex-render-path`'s
cover-letter clause updated. `.system_md_enforcement.json` gains the three
pins.

## 7. Verification gates (all must pass before a branch is "done")

- G1 (both): suite, ruff, `check_system_md`, `check_mcpb_bundle`,
  `node --test mcpb/tests`, slop ratchet, all green.
- G2 (engines): a venv run with TeX hidden from `PATH` renders a
  LaTeX-template base resume and a cover letter through Typst, both
  carrying `render_note`; `setup/status` shows the engines row; the gallery
  shows "requires TeX".
- G3 (engines): the Docker stack reports both engines available,
  `render_note` is null on every render, and LaTeX PDFs extract to
  identical text before and after the branch.
- G4 (mcp): single-worker uvicorn end-to-end over `/mcp`: initialize →
  tools/list (83) → `list_jobs` → `render_pdf` → `get_rendered_pdf`,
  inside timeouts.
- G5 (mcp): Claude Desktop installs the new `.mcpb` on the maintainer's
  Mac against the compose stack with no Docker on the client path, runs a
  tool, and survives `docker compose restart backend` mid-chat.
- G6 (mcp): Claude Code (`claude mcp add --transport http`), a Cursor
  deep link and Codex `--url` each list 83 tools; `/mcp/hunt` lists exactly
  the hunt allowlist.
- G7 (mcp): forged `Host` → 400 and foreign `Origin` → 403 on `/mcp`, by
  curl.
- G8 (store): a zip packed with `--first-upload` loads unpacked under a
  new id, is refused by CORS until that id is added to
  `MAESTRO_CS_EXTENSION_IDS`, then works. Proves the id-swap path with no
  store account.
- G9 (mcp): `./scripts/setup-mcp.sh --print-only --skip-install` still
  works and prints the deprecation banner.

## 8. Decisions taken pending the owner's objection

- Stateful sessions with JSON responses (§3.1): `clientInfo` survives,
  the bridge stays trivial.
- Profiles by path through one `ContextVar` (§3.3), stdio included.
- The bundle served from a read-only bind mount (§3.5), not baked into
  the image (the build context is `backend/`).
- `MAESTRO_CS_PDFLATEX` as an explicit override that fails loudly (§2.1).
- `mcp` becomes a core dependency (§3.1).
- The store's key becomes the committed key; the old id stays one release
  (§4).
- No auth token on `/mcp`: a local process can already reach REST, so a
  token adds friction without a boundary.
- `engines` ships first.

## 9. Owner tasks and what this unblocks

Owner tasks outside the branches: a Chrome Web Store developer account
($5), publishing `docs/PRIVACY.md` at maestrocareerstudio.com/privacy, the
five screenshots, appending the store id after the first upload, and the
version bump in the seven places (`docs/RELEASING.md` §2).

Step 3 (the shell) then needs no engine and no transport work: one
PyInstaller sidecar serves the UI, REST and `/mcp`; the shell registers
the bundle and the deep links from the connect endpoint; TeX detection
already copes with a GUI `PATH`; the extension installs from the store.
Still open for step 3: Tauri versus Electron, the signing budget (Apple
Developer ID; SignPath Foundation for Windows), and confirming that
"detect installed TeX, never bundle it" is the LaTeX-in-desktop policy.
