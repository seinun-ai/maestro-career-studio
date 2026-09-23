# Updating Maestro CS

The short version is in the [README](../README.md#updating): run
`./scripts/update.sh` from the folder you cloned. This page is the detail —
what the script does, how to do it by hand, what happens to your data, and how
to roll back.

**Contents:** [What the script does](#what-the-script-does) ·
[Updating by hand](#updating-by-hand) ·
[What happens to your data](#what-happens-to-your-data) ·
[Moving from Postgres to the database file](#moving-from-postgres-to-the-database-file) ·
[Rolling back](#rolling-back) ·
[After updating](#after-updating) ·
[Troubleshooting](#troubleshooting)

## What the script does

`./scripts/update.sh`:

1. backs up your database into `backups/` (readable only by you),
2. moves your checkout to the newest released version (a `v*` git tag),
3. lists any new settings in `.env.example` without editing your `.env`,
4. downloads (or rebuilds) the app for that same version,
5. waits until the app is healthy again, and
6. reminds you of the two things Docker can't update for you (see
   [After updating](#after-updating)).

Options: `--check` changes nothing and tells you whether you're up to date
(running version, your checkout, the newest release, and any `.env` changes);
`--force` updates even if you have local edits in the folder; `--help` lists the
flags. The script needs bash — on Windows, run it under WSL or follow
[Updating by hand](#updating-by-hand).

**Why the folder and the app move together.** Your install *is* the cloned
folder: the browser extension loads from `extension/`, and a hand-configured MCP
server runs from `backend/`. A bare `docker compose pull` updates the app but
leaves those behind, running code your app no longer matches. That's why the
script moves the folder to a release and downloads that same release.

## Updating by hand

```bash
# 1. Back up the database.
mkdir -p backups
#    a) The normal case — the database file exists (safe while the app runs):
( umask 077; docker compose run --rm -T --no-deps backend python -m app.tools.backup_db --stdout | gzip > backups/db-manual.sqlite3.gz )
#    b) Only if you are updating an install that still runs on Postgres
#       (there is no data/maestro_cs.sqlite3 yet):
docker compose up -d postgres
docker compose exec -T postgres pg_dump --clean --if-exists -U app maestro_cs | gzip > backups/db-manual.sql.gz

# 2. Move the folder to the newest release
git fetch --tags origin
git merge --ff-only "$(git tag -l 'v*' --sort=-v:refname | head -n1)"

# 3. Download the app for that same release (the image tag has no leading v)
TAG="$(git describe --tags --abbrev=0)"        # e.g. v0.1.2
IMAGE_TAG="${TAG#v}" docker compose pull       # e.g. 0.1.2
IMAGE_TAG="${TAG#v}" docker compose up -d --force-recreate --remove-orphans
```

`-U app` and `maestro_cs` in step 1b are the defaults (`POSTGRES_USER` /
`POSTGRES_DB`); use your own values if you changed them in `.env`.

- **`docker compose up -d` alone won't fetch a new release.** Docker reuses the
  copy it already downloaded until something pulls again — `docker compose pull`
  (or step 3) does that.
- **Pinning a version: drop the `v`.** The git tag is `v0.1.2`; the image tag is
  `0.1.2`. `IMAGE_TAG=v0.1.2` doesn't exist and the download fails. Set
  `IMAGE_TAG` in `.env` to pin permanently, or inline as above for one command.
- **Download or build.** `.env.example` sets `IMAGE_REGISTRY`, so installs
  download published images. Installs made before that have the line commented
  out and build from the folder instead; to switch, uncomment
  `IMAGE_REGISTRY=ghcr.io/seinun-ai/maestro-career-studio`. Contributors who
  build their own changes leave it commented — see
  [CONTRIBUTING](../CONTRIBUTING.md).

## What happens to your data

**Nothing.** `base_resumes/`, `applications/`, `settings/`, `kb_documents/`,
`exports/` and `logs/` are ordinary folders on your disk, and no update step
touches them. The database is one more file beside them —
`data/maestro_cs.sqlite3` (plus `-wal` and `-shm` helper files) — and no update
step touches it either. One consequence: `docker compose down -v` can't reach
your data, but **deleting the project folder deletes it.**

**Database changes apply themselves.** The app upgrades its database when it
starts, so the first start after an update can be slower; the script says it's
waiting rather than sitting silent.

**The backup.** Before changing anything, the script backs up whichever database
is live, into `backups/`:

- `db-<timestamp>-<version>.sqlite3.gz` — a snapshot of the database file (the
  normal case).
- `db-<timestamp>-<version>.sql.gz` — a Postgres dump, on the one update that
  moves an old install to the database file.
- Both, if both databases hold data and the script can't tell which one the app
  used. It takes both rather than guess.

It prints the restore command for whatever it took, and again if the app doesn't
come back healthy.

## Moving from Postgres to the database file

Older installs kept the database in Postgres. This release moves it into
`data/maestro_cs.sqlite3`: the first start after updating imports the old
database and checks the copy table by table (row counts plus a content hash)
before using it. The old Postgres data stays where it was, so nothing depends on
the import working first time — if it fails, the app refuses to start rather
than come up empty, and nothing is deleted.

- **Leave the `POSTGRES_*` values in `.env` as they are** until the import has
  run; the import reads them.
- **`./scripts/update.sh --check`** prints a `database:` line saying which one
  is live.
- **Once you're satisfied, you can delete the old data:**
  `docker volume rm maestro-career-studio_pgdata`. Nothing reads it after a
  successful import, and the next release removes the Postgres service.
- A fresh install has nothing to import; it starts Postgres once, finds nothing,
  and never reads it again.

## Rolling back

Rolling back means three things together: the old version of the folder, the old
app images, and the backup. Never load a backup into a newer database, and don't
try Alembic downgrades — they've never been a supported path.

**From a database-file snapshot (`.sqlite3.gz`)** — stop the app first, because
the restore replaces a file it holds open:

```bash
docker compose down
git checkout v0.1.1                                     # the version you were on
gunzip -c backups/db-<timestamp>-<version>.sqlite3.gz > data/maestro_cs.sqlite3
rm -f data/maestro_cs.sqlite3-wal data/maestro_cs.sqlite3-shm
IMAGE_TAG=0.1.1 docker compose up -d --force-recreate
```

Delete the two helper files as shown — they belong to the database you just
replaced. For the same reason, never copy the database file while the app is
running; use the `backup_db` command from [Updating by hand](#updating-by-hand),
which is safe on a running app.

**From a Postgres dump (`.sql.gz`)** — for going back to a release that still
used Postgres:

```bash
git checkout v0.1.1                                     # the version you were on
IMAGE_TAG=0.1.1 docker compose up -d --force-recreate
gunzip -c backups/db-<timestamp>-<version>.sql.gz | docker compose exec -T postgres psql -U app maestro_cs
```

## After updating

Docker can't update these two:

1. **Reload the browser extension** — `chrome://extensions` → **Reload** on the
   Maestro CS card, then reload any job tab that was already open (otherwise it
   shows "No job description found on this page" over a visible posting). If
   your install predates the extension's fixed ID, press **Remove** and **Load
   unpacked** again instead ([details](../extension/README.md)).
2. **Restart your AI assistant** (Claude, Codex, ChatGPT desktop) so it sees new
   tools. If you set the MCP server up with `./scripts/setup-mcp.sh`, re-run it
   too — it picks up new dependencies.

## Troubleshooting

**The app came up empty after updating.** Your data isn't gone. The first start
after this update imports your old Postgres database, which needs the `postgres`
service running at that moment. Check `docker compose logs backend | grep -i
legacy`, leave the `POSTGRES_*` values in `.env` as they were, and run `docker
compose up -d` again. The old Docker volume still holds every row.

**The backend won't start: "Importing the legacy Postgres database failed" or
the source "cannot be reached".** That's deliberate — starting on an empty file
would strand your data. Nothing was deleted and the import retries on the next
start; the log lines above the message name the cause. To skip the import
entirely, comment out the `LEGACY_DATABASE_URL` line in `docker-compose.yml`
(after that, `./scripts/update.sh` needs `--force` to get past its local-edits
check).
