# Updating Maestro CS

The short version is in the [README](../README.md#updating): run
`./scripts/update.sh` from the folder you cloned. This page is the detail —
what the script does, how to do it by hand, what happens to your data, and how
to roll back.

**Contents:** [What the script does](#what-the-script-does) ·
[Updating by hand](#updating-by-hand) ·
[What happens to your data](#what-happens-to-your-data) ·
[Coming from v0.3.0 or older](#coming-from-v030-or-older) ·
[Rolling back](#rolling-back) ·
[After updating](#after-updating) ·
[Freeing disk space](#freeing-disk-space)

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
# 1. Back up the database (safe while the app runs)
mkdir -p backups
( umask 077; docker compose run --rm -T --no-deps backend python -m app.tools.backup_db --stdout | gzip > backups/db-manual.sqlite3.gz )

# 2. Move the folder to the newest release
git fetch --tags origin
git merge --ff-only "$(git tag -l 'v*' --sort=-v:refname | head -n1)"

# 3. Download the app for that same release (the image tag has no leading v)
TAG="$(git describe --tags --abbrev=0)"        # e.g. v0.5.0
IMAGE_TAG="${TAG#v}" docker compose pull       # e.g. 0.5.0
IMAGE_TAG="${TAG#v}" docker compose up -d --force-recreate --remove-orphans
```

- **`docker compose up -d` alone won't fetch a new release.** Docker reuses the
  copy it already downloaded until something pulls again — `docker compose pull`
  (or step 3) does that.
- **Pinning a version: drop the `v`.** The git tag is `v0.5.0`; the image tag is
  `0.5.0`. `IMAGE_TAG=v0.5.0` doesn't exist and the download fails. Set
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

**The backup.** Before changing anything, the script saves a snapshot of the
database file to `backups/db-<timestamp>-<version>.sqlite3.gz` and prints the
command to restore it — again if the app doesn't come back healthy. It keeps
the last five.

## Coming from v0.3.0 or older

Versions before v0.4.0 kept the database in Postgres. **v0.4.0 is the release
that moves it into `data/maestro_cs.sqlite3`** (and checks the copy table by
table); later versions can no longer read Postgres. So an install on v0.3.0 or
older goes through v0.4.0 first:

```bash
docker compose down
[ -f data/maestro_cs.sqlite3 ] && mv data/maestro_cs.sqlite3 data/maestro_cs.sqlite3.not-imported
rm -f data/maestro_cs.sqlite3-wal data/maestro_cs.sqlite3-shm
git fetch --tags origin && git checkout v0.4.0
IMAGE_TAG=0.4.0 docker compose pull && IMAGE_TAG=0.4.0 docker compose up -d --force-recreate
```

Wait until `data/.migrated-from-postgres.json` exists (the first start writes
it when the import succeeds), then run `./scripts/update.sh` to move to the
newest version. Leave the `POSTGRES_*` values in `.env` as they were until
then — the import reads them.

- **`./scripts/update.sh` spots this for you.** From v0.5.0 on, if it finds an
  old Postgres volume that was never imported, `--check` warns and an update
  stops before changing anything, printing these same steps.
- **Did the app come up empty after updating from v0.3.0** (only the demo
  resume)? An older copy of the script skipped v0.4.0. Your data is still in the
  old Postgres volume — follow the steps above; the `mv` line sets the empty
  database aside.
- If the v0.4.0 import fails, it refuses to start rather than come up empty, and
  nothing is deleted; `docker compose logs backend` names the cause. The v0.4.0
  copy of this page has the full import troubleshooting.

## Rolling back

Rolling back means three things together: the old version of the folder, the old
app images, and the backup. Never load a backup into a newer database, and don't
try Alembic downgrades — they've never been a supported path. Stop the app
first, because the restore replaces a file it holds open:

```bash
docker compose down
git checkout v0.4.0                                     # the version you were on
gunzip -c backups/db-<timestamp>-<version>.sqlite3.gz > data/maestro_cs.sqlite3
rm -f data/maestro_cs.sqlite3-wal data/maestro_cs.sqlite3-shm
IMAGE_TAG=0.4.0 docker compose up -d --force-recreate
```

Delete the two helper files as shown — they belong to the database you just
replaced. For the same reason, never copy the database file while the app is
running; use the `backup_db` command from [Updating by hand](#updating-by-hand),
which is safe on a running app. (Going back to v0.3.0 or older means Postgres;
the v0.4.0 copy of this page covers that.)

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

## Freeing disk space

Docker keeps everything it has downloaded, so old versions pile up. Once the
updated app works:

```bash
docker volume rm maestro-career-studio_pgdata
```

removes the old Postgres database, if your install ever had one — only after it
was imported (see above). The script reminds you when it's there.

```bash
docker image rm postgres:16
```

removes the Postgres image (about 660 MB). Skip it if another project of yours
uses that image.

```bash
docker image prune -a
```

removes every image no container is using — including previous Maestro CS
versions, about 3 GB each. It also removes unused images from other projects,
so check `docker image ls` first.
