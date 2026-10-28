# Updating Maestro CS

The short version is in the [README](../README.md#updating): run
`maestro update` if you installed with uv, or `./scripts/update.sh` from the
folder you cloned if you use Docker. This page is the detail — what each does,
how to update a Docker install by hand, what happens to your data, and how to
roll back. Everything below the uv sections is the Docker route.

**A Docker install and a uv install are separate copies.** Each has its own data
and its own updates, and both use ports 8001 and 3000, so don't run both at once.
Updating one never touches the other. To move a Docker install's data into a uv
install once, see [Move from Docker to the uv install](#move-from-docker-to-the-uv-install).

**Contents:** [Updating a uv install](#updating-a-uv-install) ·
[Rolling back a uv install](#rolling-back-a-uv-install) ·
[Move from Docker to the uv install](#move-from-docker-to-the-uv-install) ·
[What the script does](#what-the-script-does) ·
[Updating by hand](#updating-by-hand) ·
[What happens to your data](#what-happens-to-your-data) ·
[Coming from v0.3.0 or older](#coming-from-v030-or-older) ·
[Rolling back](#rolling-back) ·
[After updating](#after-updating) ·
[Freeing disk space](#freeing-disk-space)

## Updating a uv install

```bash
maestro update
```

In order:

1. **Checks for a newer version.** One request to `pypi.org`. If yours is the
   newest, it says so and stops.
2. **Shows what breaks.** One request to `raw.githubusercontent.com` for the
   changelog, then every `### Breaking changes` entry between your version and
   the new one. If it can't read the changelog it prints the link and carries on.
3. **Asks** `Update from X to Y? [y/N]`. `maestro update --yes` skips the question
   (needed when no one is at the keyboard).
4. **Saves a verified snapshot** of your database to `backups/` in your Maestro
   folder, as `db-<timestamp>.sqlite3.gz`, and keeps the newest five. If the
   snapshot fails, nothing is stopped or changed.
5. **Stops Maestro**, runs `uv tool install --force --python 3.12
   maestro-career-studio==Y` (exactly the version whose changelog it showed; the
   `--force` also clears a version pin left by a rollback), and **starts it
   again** if it was running. Then it asks the running server for its version and
   compares it with the one it installed.

Your data folder is never moved or edited by the update, and the database upgrades
itself on the first start (which can take a little longer). If `uv` can't be found,
the command prints what to run by hand and changes nothing. If the new version
fails to start, or reports a different version, it prints where the snapshot is and
the rollback line below.

**On Windows**, a running `maestro.exe` can't be replaced. Claude Desktop keeps
`maestro mcp` running while it is open, and so does any other `maestro` command
(`maestro logs -f`), so `maestro update` first refuses, changing nothing, until
you quit Claude Desktop and stop them. After the snapshot and the stop, `maestro update` hands the upgrade to a background step and returns.
It finishes in about a minute. Don't run `maestro` commands meanwhile: files are
still being replaced. Watch `logs\update.log` in your Maestro folder (path in the
README) until its last line says `finished`, then run `maestro status`.

`maestro update --source PATH/TO/file.whl` installs a wheel file you already have
instead of the newest release. It makes no network request.

After an update, the same two steps as on Docker apply:
[the Companion and your assistant](#after-updating).

## Rolling back a uv install

Migrations only run forward, so an older version can't always open a database a
newer one changed. That is what the snapshot is for. Stop Maestro, put the old
version back, then put the old database back:

```bash
maestro stop
uv tool install --force --python 3.12 maestro-career-studio==0.9.0     # the version you were on
# in your Maestro folder (see the README: "Where your data lives"):
gunzip -c backups/db-<timestamp>.sqlite3.gz > data/maestro_cs.sqlite3
rm -f data/maestro_cs.sqlite3-wal data/maestro_cs.sqlite3-shm
maestro start
```

The `uv tool install` line is the one `maestro update` prints when something
goes wrong, with your version filled in. On Windows there is no `gunzip`; unpack
the snapshot with 7-Zip, or run
`uv run --python 3.12 python -c "import gzip, shutil; shutil.copyfileobj(gzip.open(r'backups\db-<timestamp>.sqlite3.gz'), open(r'data\maestro_cs.sqlite3', 'wb'))"`
from the Maestro folder. Delete the two helper files as shown: they belong to
the database you just replaced. Never copy the database file while Maestro is
running; `maestro backup` is safe on a running copy.

## Move from Docker to the uv install

A new uv install starts empty, while your real history still sits in the Docker
folder. `maestro import-docker` copies it across, once. Think of it as a
photocopy: the Docker folder is only read, and nothing in it is changed, moved
or deleted, so the original is still there if you ever want to go back.

1. Update the Docker install to the same version as the uv one (`./scripts/update.sh`,
   then `maestro --version` to compare). A database from an older or newer
   release is refused with the version to update to.
2. Stop it: `docker compose down` in the Docker folder. Stop the uv copy too
   (`maestro stop`).
3. Look first: `maestro import-docker /path/to/maestro-career-studio --dry-run`
   prints what it would copy, rewrite and carry over, and changes nothing.
4. Run it without `--dry-run`, then `maestro start`.

What it does, in order:

- Refuses, in one sentence and changing nothing, if either install is running,
  the Docker database is not at this version's schema, or the uv install already
  holds your jobs, applications or resumes (add `--replace` to overwrite them).
- Saves a verified snapshot of the uv install's current database
  (`backups/db-*.sqlite3.gz`, the undo point) and prints its path.
- Builds the new database from a copy of the Docker one using SQLite's online
  backup, rewrites the stored file locations (`/app/applications/...` becomes
  your Maestro folder) in one transaction, and checks every table has the same
  row count. Values that merely mention `/app/` inside longer text or JSON
  (for example a saved tailoring result) are counted, listed by column and left
  as written.
- Copies `applications/`, `base_resumes/`, `kb_documents/`, `exports/` and
  `settings/` (the Docker files win when a name exists in both), never following
  a symlink. Old snapshots (`data/backups/`) and `data/handoff/` stay behind.
- Places the sync key where the uv install reads it.
- Adds the settings Maestro understands from the Docker `.env` (API keys, models,
  proxy, sync host) to `maestro.env`, keeping any you already set there. Ports,
  paths and other Docker-only entries are left out. Only names are printed. A
  value that points at `host.docker.internal` gets a note: it only works inside
  Docker, so change it to `localhost` in `maestro.env`.
- Keeps a copy of every file of the uv install that it replaces (your old
  `sync-key`, settings, resumes, `maestro.env`) while it runs. If anything fails,
  those files, the database and `maestro.env` are all put back and the files it
  added are removed, so the earlier install is exactly as it was. If it succeeds,
  the copies stay in `backups/import-replaced-files-<time>/`, next to the snapshot.

**Undoing a finished import** (only needed if you want your earlier uv data
back): `maestro stop`, delete the three files `data/maestro_cs.sqlite3*`, unpack
the snapshot it printed over `data/maestro_cs.sqlite3` (macOS and Linux:
`gunzip -c backups/db-<time>.sqlite3.gz > data/maestro_cs.sqlite3`), copy the
contents of `backups/import-replaced-files-<time>/` back over the same names in
your Maestro folder, and `maestro start`. If the folder had no `sync-key` before
the import, also delete `sync-key` there; otherwise sync stays on with the Docker
install's key. The other files the import added are harmless and can stay.

**If the import is interrupted** (power loss, the terminal killed mid-run), the
next `maestro import-docker` refuses, and so does `maestro start` when the
database file is missing, naming the leftovers in `data/`
(`maestro_cs.sqlite3.before-import`, `maestro_cs.sqlite3-wal.before-import`, `.importing/`,
`.before-import/`). **First** copy what is in `data/.before-import/` back over the
same names in your Maestro folder: those are the only copies of your old sync key,
settings and `maestro.env`, and only then delete that folder. Put each
`*.before-import` database file back under its name without the suffix (or
restore the snapshot), delete `data/.importing/`, and run it again.

Afterwards, **don't start the Docker install again alongside this one**: both
would share one sync identity. The Docker folder is still yours; delete it when
you are sure.

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
folder: a browser extension loaded unpacked runs from `extension/`, and a hand-configured MCP
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

Neither Docker nor `maestro update` can update these two:

1. **The Companion** — the Chrome Web Store build updates itself once the new
   version is published there. One loaded unpacked needs `chrome://extensions` →
   **Reload** on the Maestro CS card; if that install predates the extension's
   fixed ID, press **Remove** and install again instead
   ([details](../extension/README.md)). Either way, reload any job tab that was
   already open (otherwise it shows "No job description found on this page"
   over a visible posting).
2. **Restart your AI assistant** (Claude, Codex, ChatGPT desktop) so it sees new
   tools. If you still use the legacy stdio setup, re-run `./scripts/setup-mcp.sh`
   to pick up dependencies. URL connections need no setup changes. Reinstall
   the Claude Desktop bundle once if yours is the older Docker-based one.

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
