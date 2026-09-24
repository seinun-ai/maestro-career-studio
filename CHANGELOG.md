# Changelog

All notable changes to Maestro CS are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Versioning policy, stated honestly for 0.x

Maestro CS follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html),
with the qualification that version 0 actually carries:

- **Before 1.0, a breaking change may land in a minor version** (`0.2.0`) — that
  is what SemVer's major-zero clause permits, and pretending otherwise would
  mean either a dishonest changelog or a `4.0.0` by winter.
- **Every one of them is listed under a `### Breaking changes` heading.** That
  heading is the contract: if a release has one, read it before updating; if it
  does not, the update is a normal one.
- **Migrations only run forward.** The backend applies `alembic upgrade head` at
  boot. Downgrade functions exist in the migration files but have never been a
  supported path — rolling back means the old git ref, the old images, and the
  backup `scripts/update.sh` took before it started, together.
  [`docs/UPDATING.md`](docs/UPDATING.md#rolling-back) has that recipe.
- **Patch releases (`0.1.1`) never change the schema or the `.env` contract.**
  They are safe to take without reading anything.

Version numbers appear in seven places that must agree — the git tag (`v0.2.0`)
and six files listed in [`docs/RELEASING.md`](docs/RELEASING.md). The published
image tag is the same version with the leading `v` removed (`0.2.0`).

## [Unreleased]

### Added

- **Agent inbox.** Jobs an agent proposes live on their own page with their own
  words, and every proposal says who filed it: "Proposed by <agent name>" or
  "Queued by you". A new migration records the filer and marks the jobs you
  queued from the web app before this release as yours.
- Settings and Profile are split into tabs you can link to directly; unsaved
  edits still warn before you leave, across tabs too.
- **Gender options.** Profile › Autofill adds Non-binary and Prefer to
  self-describe (with a box for your own words) beside Male, Female and
  Decline to answer. With diversity consent on, the Companion picks the form's
  matching option ("Non-binary", "Nonbinary", "I prefer to self-describe"…)
  and types your words only into a box that asks for them; a form without
  the option is left for you. Answers you already saved keep working.

### Changed

- Plain words everywhere: one name per thing across the web app, the
  Companion extension and the server's error messages, which now say what
  happened and what to do next instead of showing technical detail.
- Long lists keep their toolbar (and, where the table fits, its header) in view
  while you scroll, and say so when a list is cut off at 500 rows.
- "Which model should I pick?" (Settings › AI & models) compares the two
  models in words and links OpenAI's and Google's own pricing pages, instead
  of quoting prices that go out of date.
- The "restrictive covenant" question in Profile › Autofill now says what one
  is: "Such as a non-compete or non-solicit agreement."

### Fixed

- **Privacy:** when autofill asks the AI how to fill a field, your diversity
  answers (race, gender, veteran and disability status) are sent only if
  diversity consent is on. Before, they reached the AI provider even with it
  off.
- Pressing Queue twice quickly no longer creates two proposals for the same job.

## [0.5.0] — 2026-09-23

### Breaking changes

- **Postgres is gone.** The compose file no longer has a `postgres` service or
  `pgdata` volume, and the backend no longer imports a Postgres database —
  v0.4.0 was the release that did that. **On v0.3.0 or older? Update to v0.4.0
  first**; `./scripts/update.sh` now spots an old Postgres volume that was never
  imported, stops before changing anything, and prints the steps
  ([`docs/UPDATING.md`](docs/UPDATING.md#coming-from-v030-or-older)). If an
  older copy of the script already moved you past v0.4.0 and the app came up
  empty, your data is still in the old volume and the same steps recover it.
- `LEGACY_DATABASE_URL`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
  and `POSTGRES_HOST_PORT` are no longer read; leaving them in `.env` is
  harmless. The `legacy-postgres` extra and `python -m
  app.tools.migrate_from_postgres` are removed.

### Changed

- A fresh install downloads and runs two containers instead of three: no
  Postgres image (about 170 MB to download, 660 MB on disk), no idle container,
  no port 55432, no wait at first start.
- After an update, `update.sh` suggests removing the old Postgres volume and
  the `postgres:16` image when they are still on disk; `docs/UPDATING.md` has a
  new "Freeing disk space" section.

### Fixed

- `update.sh` no longer stops in git's pager (`:`) while listing the commits it
  brought in, which hid the extension and MCP reminders printed after it.

## [0.4.0] — 2026-09-23

### Breaking changes

- **The database is now `data/maestro_cs.sqlite3`.** Existing installs are
  imported from Postgres automatically at the first boot of this release
  (verified by row count and content hash; the old volume is left in place).
  Keep your `POSTGRES_*` values in `.env` until the import has run;
  `./scripts/update.sh --check` reports which database is live. The import
  fails closed — if the `postgres` service cannot be reached, or the copy does
  not verify, the backend refuses to start and says why, and nothing is
  deleted. The next release deletes the `postgres` service entirely: install
  this one first.
- **`DATABASE_URL` accepts only `sqlite:///` URLs.** Anything else — a
  Postgres URL in either spelling included — is refused at startup with a
  message saying what to do instead. Leave it unset and the file is derived
  from the new `DATA_DIR` setting (default `/app/data`, where compose mounts
  `./data`). The other new setting, `LEGACY_DATABASE_URL`, is the one place a
  Postgres URL still belongs: compose builds it from your `POSTGRES_*` values,
  and it names the source of the first-boot import.
- **The migration history is squashed to one SQLite baseline**
  (`871d0425b64c`). The Postgres chain survives only inside the importer, so a
  branch carrying a revision parented on the old chain will not apply after
  this release — rebase it onto the baseline.
- **`applied_at`, and the applications list's `created_after` / `created_before`
  filters, now require a UTC offset.** A naive timestamp is refused at the
  boundary with a 422 instead of failing at write time with a 500.

### Added

- **`SQLITE_JOURNAL_MODE`** in `.env` — set it to `DELETE` for a filesystem
  that cannot support WAL; the default (WAL) is right everywhere else.
- **`python -m app.tools.backup_db`** takes an online snapshot of the database
  while the stack runs, and **`python -m app.tools.migrate_from_postgres`** is
  the first-boot import as a command you can run yourself.
- **PDF engine probe** on `GET /api/setup/status` (`engines`), `render_note` on
  render responses when a LaTeX template is rendered through Typst because TeX
  is missing, `engine_available` on templates, a Typst cover letter
  (`cover_letter.typ`), and **`MAESTRO_CS_PDFLATEX`** to name a pdflatex binary
  outside the usual locations (host/venv backends; the image already has TeX).

### Changed

- The backend test suite needs no database service: each test process gets its
  own throwaway SQLite file when `TEST_DATABASE_URL` is unset. When it is set,
  it must be a `sqlite:///` file URL; one under `data/` or naming the app's own
  database is refused.
- psycopg moved into an optional `legacy-postgres` extra, which leaves with the
  `postgres` service next release. A source install that has to import a
  Postgres database needs `pip install -e ".[dev,legacy-postgres]"`.
- `docs/agent-prompts/` is replaced by generic skills in `docs/skills/`:
  `job-hunt`, an autonomous `apply-session` (which also replaces
  `manual-apply-session`), and `customize-job-skills`, which suggests skills
  from what your agent knows about you and your data, asks a few questions, and
  builds your own version or a new skill with your client's skill creator and
  scheduler. `apply-session` asks you only for information the app doesn't
  have, plus one yes per application before it submits.
- The user docs are rewritten for someone new: a plain opening and glossary in
  the README and Getting Started, a five-step first run, and far less jargon.
  The full update procedure (by hand, backups, rolling back, the Postgres
  import) moved to [`docs/UPDATING.md`](docs/UPDATING.md); the extension's
  internals moved to `extension/INTERNALS.md`; development mode and LLM tracing
  moved to `CONTRIBUTING.md`. The docs no longer point to a `⋯` menu in the
  extension panel, which no longer exists.

### Fixed

- **Security:** Next.js 16.3.6, which fixes a critical remote-code-execution
  advisory in its image optimizer (GHSA-2xp9-vwfh-vxw4), plus updated
  `fast-uri`, `hono`, `js-yaml`, `qs` and `sharp` for their advisories.
- Cover-letter regeneration and document upload commit before their LLM call,
  so a slow model no longer holds the database's write lock while it thinks.
- Contact URLs with `~`/`_` in the shared header partial no longer corrupt the
  link target (resume and cover letter). The header also compiles for a contact
  without a location. User templates `carlito_dense` and `harshibar` pass
  `\href` targets through `latex_escape_url` the same way, and existing
  installs are resynced at seed time.

## [0.3.0] — 2026-08-29

### Breaking changes

None.

### Added

- **Claude Desktop extension (`.mcpb`).** `mcpb/maestro-career-studio.mcpb`
  installs the MCP server from Claude's own Settings → Extensions dialog — no
  terminal, no config file, no host Python; the shim runs the server inside
  the backend container. One install covers Claude Desktop and Claude Code
  sessions running inside the Claude app. `scripts/check_mcpb_bundle.py` gates
  the bundle in CI.

### Changed

- `scripts/setup-mcp.sh` slimmed down now that the extension and plugin routes
  cover the common clients; it remains the route for Cursor, Windsurf and
  other stdio clients, a backend outside Docker, and scoped profiles.
- README and Getting Started reorganized around the extension/plugin installs,
  with hand-written client-config fallbacks (Claude Desktop JSON, Codex TOML)
  documented for when a packaged install fails.
- Install docs now state the image **download** size (~1 GB compressed) ahead
  of the unpacked footprint (~3–4 GB), and list Git as a prerequisite.
- Scoped MCP profiles are presented as an opt-in customization everywhere:
  every install route defaults to `full`, the Claude extension's **Tool
  profile** field or a hand-edited config entry scopes it, and the agent
  prompts no longer read as if they require the `hunt`/`apply` profiles.

### Fixed

- The two marketplace plugin manifests (`.claude-plugin/plugin.json`,
  `.codex-plugin/plugin.json`) now carry the release version — they had
  silently stayed at `0.1.2` through two releases.

## [0.2.0] — 2026-08-28

### Breaking changes

- **The compose project name is now fixed to `maestro-career-studio`.**
  `docker-compose.yml` sets it explicitly, because the shipped plugin manifest
  has to name the container as a literal (Codex plugin manifests support no
  `${VAR}` interpolation). This is a **no-op for a normal install** — cloning
  the repo already produced that name. It is *not* a no-op if your stack's
  project name came from a differently-named directory: that stack points at a
  different Postgres volume and comes up **looking empty rather than failing**.
  If that is you, set `COMPOSE_PROJECT_NAME` to your old name in `.env` before
  updating; it still overrides, and it stays the supported way to run two
  stacks side by side.

### Added

- **Install the MCP server from a marketplace.** `claude plugin marketplace
  add` / `codex plugin marketplace add` against this repo, then install
  `maestro-career-studio` — no paths to edit and **no host Python**, because
  the server runs inside the backend container you already started. The `mcp`
  extra is now baked into the image so the container can be the MCP server.
  Claude Desktop is a separate surface and still needs its own entry.
- **A three-part install story** in `docs/GETTING_STARTED.md`: the app is Part
  1 and the only required one; the assistant and the extension are independent
  optional add-ons.

### Fixed

- `prepare_application_pdf_upload` now reports the upload path **the browser
  can open**, not the in-container path it wrote to.
- Requests are no longer paused as "offline" against a local API.
- `scripts/setup-mcp.sh`: dropped a `claude mcp add` scope the CLI never had,
  and a venv check that never ran. Added `--write-desktop-config`, which
  refuses while Claude Desktop is running and backs the file up first.
- `.gitignore`'s `.mcp.json` rule is anchored to the repo root — unanchored, it
  swallowed the shipped plugin payload at `plugins/*/.mcp.json`.

## [0.1.2] — 2026-08-26

### Changed

- **`.env.example` now ships in pull mode.** `IMAGE_REGISTRY` and
  `IMAGE_TAG=latest` are set rather than commented, so a fresh
  `cp .env.example .env && docker compose up -d` DOWNLOADS the published
  multi-arch images instead of compiling TeX Live. Contributors comment
  `IMAGE_REGISTRY` out and keep using `--build` — see CONTRIBUTING. Existing
  installs are unaffected: `update.sh` never edits your `.env`, and it reports
  the two new keys as drift rather than changing modes under you.

## [0.1.1] — 2026-08-26

**The first public release.** Everything before this point predates the
changelog, so the entries below cover only the final pre-release round — the
rest of the product is the baseline this file measures from.

*(A `v0.1.0` tag exists but was never released: it landed on a commit whose
image workflow could not publish, and the tag ruleset — correctly — refused
to let it move. No images, no Release, no consumers; this tag supersedes it
per the policy above.)*

### Added

- **An update path.** `scripts/update.sh` moves an installed instance to the
  newest released version in one command: it backs the database up first, moves
  the checkout to the newest `v*` tag, reports `.env` drift without editing the
  file, brings the images to that same tag, waits for the stack to be healthy,
  and names the two surfaces Docker cannot update (the unpacked extension and
  the MCP client registration). `--check` answers "am I up to date?" and mutates
  nothing; `--force` overrides the dirty-tree refusal.
- **Version identity.** `APP_VERSION` is baked into both images at build time
  and reported by `GET /api/version` alongside the live Alembic schema revision.
  A Settings → About card shows both, and the app raises a persistent banner
  when the frontend and backend images turn out to be different versions — the
  stale-image failure that previously had no symptom at all. A version starting
  with `dev` means "locally built, do not compare" and suppresses the banner.
- **Prebuilt multi-arch images** published to ghcr.io on every `v*` tag, so a
  fresh install downloads instead of compiling TeX Live.
- **Release discipline.** This file, plus a maintainer checklist at
  [`docs/RELEASING.md`](docs/RELEASING.md).

### Changed

- The `latest` image tag now follows tagged releases only. A
  `workflow_dispatch` build publishes `dev-<sha>` and no longer overwrites
  `latest` with an unreleased build.

### Breaking changes

- None.

<!-- Template for the next release — copy, do not accrete. Drop any heading with
     nothing under it, but never drop "Breaking changes" when there is one.

## [0.2.0] — YYYY-MM-DD

### Breaking changes
### Added
### Changed
### Fixed
### Removed
-->
