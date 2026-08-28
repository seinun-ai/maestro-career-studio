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
  dump `scripts/update.sh` took before it started, together. The
  [README's Updating section](README.md#updating) has that recipe.
- **Patch releases (`0.1.1`) never change the schema or the `.env` contract.**
  They are safe to take without reading anything.

Version numbers appear in four places that must agree: the git tag (`v0.2.0`),
`backend/pyproject.toml`, `extension/manifest.json`, and `CITATION.cff`. The
published image tag is the same version with the leading `v` removed (`0.2.0`).

## [Unreleased]

Nothing yet.

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
