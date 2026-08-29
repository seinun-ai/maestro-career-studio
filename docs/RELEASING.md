# Releasing Maestro CS

Maintainer checklist. Cutting a release here is not only "tag and push": users
install by **cloning**, so a release moves their checkout *and* their images at
once, and a mistake in this file's steps reaches every installed instance.

The versioning policy — SemVer as honestly applied to 0.x, and the
`### Breaking changes` contract — lives at the top of
[`../CHANGELOG.md`](../CHANGELOG.md). Read it before choosing a number.

---

## Three standing constraints

These are not steps. They hold between releases, and each is cheap to respect
and impossible to repair afterwards.

**1. From the first public tag onward, the published history is append-only.**
`scripts/update.sh` moves a user's checkout with `git merge --ff-only`. A single
force-push to a published branch or a moved tag breaks that fast-forward *for
every installed user, permanently* — their only recovery is a fresh clone and a
manual data move. Never rewrite published history. Never move a tag; supersede
it with a new one.

**2. Between releases, `main` must stay compatible with the latest released
images.** Users run released images against a checkout somewhere between two
releases, and the files that live in their tree — `docker-compose.yml`,
`.env.example`, `scripts/`, `extension/` — are read by code that shipped weeks
ago. If a change on `main` cannot be satisfied by the images already published
(a new required env var, a compose service the old image does not answer, a
script that assumes a new endpoint), then that change *is* a release: cut one
rather than leaving the combination broken.

**3. The compose project name is fixed and must never move again.**
`docker-compose.yml` sets `name: maestro-career-studio`, so containers are
`maestro-career-studio-backend-1` and the volume is
`maestro-career-studio_pgdata`. That container name is a **literal** in the
shipped plugin manifest (`plugins/maestro-career-studio/.mcp.json`) because
Codex plugin manifests support no `${VAR}` interpolation — there is nowhere to
put a variable. Changing the project name therefore breaks marketplace installs
on every machine at once, and separately points existing stacks at a different
Postgres volume, which presents as an empty app rather than an error.
`COMPOSE_PROJECT_NAME` still overrides it for anyone who needs a second stack
side by side; that is the supported escape hatch, and such a user configures
their MCP server with `scripts/setup-mcp.sh` rather than the plugin.

---

## The checklist

### 1. Pick the version and write it down

- Choose `X.Y.Z` per the policy in `CHANGELOG.md`. Before 1.0, a breaking change
  is allowed in a minor — but it must be under `### Breaking changes`.
- **Tags are cut in ascending order only.** The image-publish workflow attaches
  `latest` to *the tag push that ran most recently*, not to the highest semantic
  version. Pushing an older `v*` tag after a newer one silently moves `latest`
  backwards for every user who has not pinned. If you must publish a fix for an
  older line, give it a higher number.

### 2. Bump the seven places a version lives

They must agree, and most of them will keep lying silently if you forget:

| File | Value |
|---|---|
| `backend/pyproject.toml` | `version = "X.Y.Z"` |
| `extension/manifest.json` | `"version": "X.Y.Z"` |
| `CITATION.cff` | `version: "X.Y.Z"` + `date-released` (cffconvert cannot catch a stale one — check by eye) |
| `mcpb/manifest.json` | `"version": "X.Y.Z"` — what Claude Desktop shows for the installed extension. Re-pack the bundle after editing (`scripts/check_mcpb_bundle.py` fails otherwise) |
| `plugins/maestro-career-studio/.claude-plugin/plugin.json` | `"version": "X.Y.Z"` — what `/plugins` shows for the marketplace install |
| `plugins/maestro-career-studio/.codex-plugin/plugin.json` | `"version": "X.Y.Z"` — its Codex twin; the two must not diverge |
| the git tag (step 4) | `vX.Y.Z` |

The published image tag is the version **without** the `v` (`X.Y.Z`) — the
workflow strips it. Anything documented as `IMAGE_TAG=vX.Y.Z` is wrong and 404s.

### 3. Changelog and gates

- Rename `## [Unreleased]` to `## [X.Y.Z] — YYYY-MM-DD` and start a fresh
  `## [Unreleased]` above it. Keep `### Breaking changes` even to say "None" —
  its absence should mean "not yet written", never "nothing broke".
- Confirm CI is green on `main`, and run the gates that are not in CI:
  ```bash
  cd backend && TEST_DATABASE_URL=postgresql://app:app@127.0.0.1:55432/maestro_cs_test pytest tests/ mcp_server/tests/ -q
  cd frontend && npx tsc --noEmit && npm run build
  python3 scripts/check_system_md.py
  ```
- Confirm `SYSTEM.md` describes what is about to ship (its header contract).

### 4. Tag and push

```bash
git checkout main && git pull --ff-only
git tag vX.Y.Z
git push origin vX.Y.Z
```

The tag push is what fires `.github/workflows/images.yml`. Nothing else does.

### 5. Verify the images before announcing anything

The workflow builds each architecture on a native runner and merges the digests
into one manifest list. Both halves have to have worked:

```bash
docker buildx imagetools inspect ghcr.io/seinun-ai/maestro-career-studio-backend:X.Y.Z
docker buildx imagetools inspect ghcr.io/seinun-ai/maestro-career-studio-frontend:X.Y.Z
```

Expect `linux/amd64` **and** `linux/arm64` in each manifest. A single-arch
manifest means the merge job took the wrong path — fix it and cut the next
patch; do not move the tag.

### 6. Create the GitHub Release from the tag

```bash
gh release create vX.Y.Z --title "vX.Y.Z" --notes "<the changelog section>"
```

**A bare tag is not a Release.** GitHub's `releases/latest` API returns published
Release objects and ignores tags entirely, so a tag-only release is invisible to
anything that asks GitHub what the newest version is — including the update
check this project has designed but not yet shipped. Creating the Release every
time is what keeps that option open.

### 7. Package visibility, and an unauthenticated pull

ghcr packages default to **private regardless of repository visibility**. Until
they are switched, every user's `docker compose pull` fails with a 403 that
reads like a bug in their setup.

- First release only: on the org's **Packages** settings, set **both**
  `maestro-career-studio-backend` and `maestro-career-studio-frontend` to
  public.
- Every release: prove it from outside, because your own machine is logged in.
  ```bash
  docker logout ghcr.io
  docker pull ghcr.io/seinun-ai/maestro-career-studio-backend:X.Y.Z
  docker pull ghcr.io/seinun-ai/maestro-career-studio-frontend:X.Y.Z
  ```

### 8. Prove the update path, not just the artifacts

On a scratch clone sitting at the *previous* tag, with a stack running on
non-default `*_HOST_PORT`s:

```bash
./scripts/update.sh --check     # reports the new tag as available
./scripts/update.sh             # backup → ff-to-tag → pull → healthy
```

Confirm the backup file in `backups/` is non-empty, the checkout lands on the
new tag, and the stack comes back healthy. This is the step that catches a
release which publishes perfectly and updates nobody.

### 9. After the release

- Refresh the static test-count badge in `README.md`.
- The ghcr image badge is already up (it went live with v0.1.1, once both
  packages were public). It is the one badge that
  would otherwise advertise something a stranger cannot pull.

---

## First release only

Preconditions the later releases inherit and do not need to re-check:

1. **The repository is public.** While it is private, clone, tags and pull are
   all maintainer-only and none of this reaches a user.
2. Both ghcr packages are public (step 7) and an unauthenticated pull works from
   a machine that has never logged in.
3. Only *then* flip `.env.example` to
   `IMAGE_REGISTRY=ghcr.io/seinun-ai/maestro-career-studio` with
   `IMAGE_TAG=latest`, and change the README quickstart from
   `docker compose up -d --build` to `docker compose up -d`. The order is
   load-bearing: the README must not promise a pull-mode install before images
   exist at that path.
