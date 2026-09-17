# SQLite as the only database — design

Status: approved in brainstorm 2026-09-17, awaiting implementation plan.
Scope: `backend/`, `docker-compose.yml`, `scripts/update.sh`, CI, docs.
Successor designs (not this doc): Typst-first engine probing, MCP over
Streamable HTTP, the desktop shell. This is step one of that sequence.

## Goal Card

**Goal:** Make Maestro CS installable as a native desktop app with a
one-click MCP connection, without Docker or git. The first step is to make
SQLite the only database, so the app never needs a database daemon, so a
user's whole relational state is one file they can copy, and so the later
installer has nothing to run, sign, or port-manage except the app itself.

**Principles** (how to decide when the plan is ambiguous or wrong):
- One dialect at the end. Postgres survives exactly one release, and only
  inside the exporter. No permanent dual-dialect code, no `with_variant`
  left behind.
- No existing install loses data. `update.sh` migrates automatically, the
  old Postgres volume stays on disk until the user removes it, and the
  backup taken before migration is a real restore path.
- Deterministic scores must not move. The ATS calibration snapshot taken on
  Postgres and the one taken on SQLite after the port must diff clean.
- The security boundary does not weaken. One fewer zero-auth port, the DB
  file is mode 0600, and every §6 invariant keeps its enforcement pin.
- Do not fix unrelated things while in there. No schema redesign, no table
  or column renames, no "while we are here" cleanups outside the port.

**Non-goals:** the desktop shell, engine probing for TeX, publishing the
extension, MCP over HTTP. Each gets its own design after this lands.

**Autonomy:** peer. The executor may adapt *how* when the repo disagrees
with this doc, must log every deviation with a one-line reason, and is
invited to flag anything here that contradicts the Goal Card. Scope is
never self-expanded.

## 1. Why SQLite, and why now

The product is single-user and local-first by design (README, §1). An audit
of the backend on 2026-09-17 found Postgres used as a JSON document store,
not for Postgres features:

| Feature | Count | Portability |
|---|---|---|
| `JSONB` columns | 27 | storage only; zero JSON operators in any query |
| `UUID(as_uuid=True)` primary keys | 13 columns, 20 `default=uuid.uuid4` | Python-side ids; `sa.Uuid` |
| `server_default=func.now()` | 35 | portable |
| `DateTime(timezone=True)` | 46 columns, 33 `datetime.now(UTC)` writers | the one real trap (§3.4) |
| `'{}'::jsonb` / `'[]'::jsonb` server defaults | 4 (`models/career_kb.py`) | rewrite |
| `postgresql_where` partial index | 1 (`models/ats_score.py`) | add `sqlite_where` |
| `func.date_trunc` | 3 (`routers/explore.py`, `services/explore_gaps.py`, `services/explore_activity.py`) | rewrite |
| `ilike` | 1 (`routers/jobs.py`) | SQLAlchemy emulates with `lower()` on SQLite |
| `func.row_number`, `func.count`, `coalesce`, `avg`, `min`, `max`, `lower` | many | portable |
| Upserts, row locks, arrays, GIN, pgvector, `RETURNING` | 0 | none (an earlier grep for `GIN` matched `BEGIN`/`ENGINE`; there are no GIN indexes) |
| Files importing `sqlalchemy.dialects.postgresql` | 18 model files | mechanical |
| Alembic revisions | 54, 18 touching PG types, 9 with raw `op.execute` | squash |
| Writer processes | 1 uvicorn process; MCP and extension go through REST | WAL is sufficient |

Nothing Postgres is good at is exercised: no concurrent writers, no JSON
indexing, no extensions. What Postgres costs is everything the installer
must not have: a daemon, a port (55432, plus its collision lore), binaries
to sign and notarize, `pg_dump` as the backup story, and a compose service
that is the reason a fresh clone downloads a database image.

**Why before the installer, not after.** Embedded Postgres (the
`postgresql_embedded` Rust crate) would ship the installer with zero schema
risk. It would also give early desktop users two database moves, compose
Postgres to embedded Postgres to SQLite. The user base is small ("young,
but rehearsed", README) and the migration tool is cheapest to build while
the only installs are compose installs.

**What this respects.** §13's held decision on LaTeX is untouched. §6's
invariants are untouched. The alembic revision-id rule in §12 still applies
to the new baseline.

## 2. Target architecture

### 2.1 Where the file lives

- New setting `data_dir: Path = Path("/app/data")` in `app/config.py`,
  beside the six existing data-dir settings, overridable by `DATA_DIR`.
- `database_url` default becomes `sqlite:///<data_dir>/maestro_cs.sqlite3`.
  SQLite writes `-wal` and `-shm` sidecars next to it; the three files are
  one database. Backups must use the online backup API, never a file copy
  of a live database (§2.6).
- The file is created with mode 0600 by the app on first boot. A raw copy
  by the user is still a legitimate offline backup once the app is stopped.
- `docker-compose.yml` bind-mounts `./data:/app/data` alongside the other
  PII mounts. `data/` joins `.gitignore` with the other runtime dirs.
- `TEST_DATABASE_URL` keeps its name and its protected-name guard. Its
  default becomes a SQLite file under a per-session temp dir (§2.7). A
  SQLite `TEST_DATABASE_URL` that resolves inside `data/` is refused, the
  same way a Postgres one naming the dev DB is refused today.

### 2.2 Engine setup (`app/db.py`)

- `create_engine(url, future=True, connect_args={"timeout": 30})`.
  SQLAlchemy 2.x already uses a real pool for file SQLite and sets
  `check_same_thread=False`; do not add `StaticPool`.
- A `connect` event listener issues, per connection:
  `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`,
  `PRAGMA synchronous=NORMAL`, `PRAGMA busy_timeout=30000`.
  `foreign_keys=ON` is mandatory: 21 relationships rely on `ondelete=` and
  SQLite does not enforce foreign keys unless told to, per connection.
- `normalize_postgres_url` goes away with its callers once the exporter is
  the only Postgres reader (§4). Until then it stays, unchanged.
- `SessionLocal` keeps `autoflush=False` (§12). This matters more on SQLite
  than it did on Postgres: with deferred flushes, a session takes its write
  lock at commit time, so a long transaction holds the lock for
  milliseconds, not for the duration of an LLM call (§3.3).

### 2.3 One type module (`app/models/types.py`)

Every model imports its column types from here and nowhere else:

- `JSONDoc` → `sa.JSON`. Behaves as before for load/store. Mutation
  tracking is unchanged (whatever `flag_modified`/mutable usage exists
  today keeps working; the type is not the tracker).
- `UUIDType` → `sa.Uuid`, called as `UUIDType(as_uuid=True)`. SQLite stores it
  as 32-char hex. The importer writes through this type, so the
  representation is consistent.
- `UTCDateTime` → a `TypeDecorator` over `sa.DateTime`. Bind: aware
  datetimes are converted to UTC and stored naive; a naive datetime raises,
  because every writer today uses `datetime.now(UTC)` and a naive value is
  a bug, not a convention. Result: naive values come back with `tzinfo=UTC`.
  `server_default=func.now()` renders `CURRENT_TIMESTAMP` on SQLite, which
  is UTC and naive, so it round-trips through the same decorator.
- The four `'{}'::jsonb` / `'[]'::jsonb` server defaults become
  `server_default=sa.text("'{}'")` / `"'[]'"` (SQLite stores JSON as text).
- The one `postgresql_where` index becomes `sqlite_where=` with the same
  expression. Not both: Postgres is never a runtime target again, and the
  exporter reads the source by reflection, not through the models.

**Pinned:** a new `tests/test_db_portability.py` asserts that no file under
`app/` other than `models/types.py` imports from `sqlalchemy.dialects`, and
that every `DateTime` column in `Base.metadata` is a `UTCDateTime`. This is
the enforcement point for the §6 invariant added in §5.

### 2.4 Query rewrites (three sites, one semantics)

`func.date_trunc("week", …)` at the three explore sites is Postgres-only.
Replace with one helper in `services/explore_activity.py` that buckets
Monday-start weeks (the file's own comment already states Monday to match
Postgres) and is used by all three callers. Prefer Python-side bucketing
over a fetched date column: the data is single-user scale, and it keeps
the SQL dialect-free. If the executor chooses SQLite `strftime` instead,
the Monday-start property must be pinned by a test either way.

`ilike` needs no change: SQLAlchemy renders `lower(a) LIKE lower(b)` on
SQLite. Non-ASCII case folding differs from Postgres; accepted for a skill
name search.

### 2.5 Alembic: squash, and keep the old chain in a box

- The 54 Postgres revisions move, unchanged, to
  `backend/legacy_postgres/migrations/` with their own
  `backend/legacy_postgres/alembic.ini`. Nothing in `app/` imports them.
  Only the exporter runs them (§2.6). They are deleted in release N+1.
- One new baseline revision is generated from the ported metadata against
  an empty SQLite file. Revision id per §12: `uuid.uuid4().hex[:12]`.
- `migrations/env.py` sets `render_as_batch=True`, so every future ALTER
  works on SQLite's copy-and-rename model.
- Seeding is unchanged: `seeding.run_startup()` still runs
  `alembic upgrade head` at boot, and `ensure_seed_templates` still mints
  templates at runtime. The data migrations in the old chain that mattered
  to a fresh install (template refreshes, the `9a0404101e5f` read of
  `resume.tex.j2` off disk) are superseded by runtime seeding, which
  also closes the trap recorded in §13's `latex-render-path` row notes.
- `GET /api/version` keeps reporting the live alembic revision; the
  frontend's version-mismatch warning needs no change.

### 2.6 The importer and the backup

**Where it runs: inside the backend, at the first boot of release N.** An
install on release N-1 runs N-1's `update.sh`, which cannot contain a step
added in N, and a user who updates by hand (`docker compose pull && up -d`)
never runs the script at all. So `seeding.run_startup()` calls
`import_if_needed()` right after `alembic upgrade head` and before any seed:
if `LEGACY_DATABASE_URL` is set (compose sets it for this one release), the
target file holds no user data, and the source holds some, the import runs
in one target transaction and writes `data/.migrated-from-postgres.json` on
success. An unreachable source is retried at the next boot; a verification
mismatch rolls back and is logged loudly; a target that already has data is
left alone. `update.sh`'s job shrinks to the pre-update backup and the
"remove the old volume" advice.

The same code is the command line tool
`python -m app.tools.migrate_from_postgres --source <url> --target <path>`
(in `app/tools/`, importable, unit-tested), which does, in order:

1. Run the legacy chain to head against the source (a user may skip
   releases; `update.sh` moves to the newest tag). Refuse if the source
   is not reachable rather than guess.
2. Refuse if the target exists and is non-empty, unless `--replace`, which
   first moves the existing file aside with a timestamp.
3. Create the target schema by running the new baseline to head.
4. Copy every table in `Base.metadata.sorted_tables` order: read the
   source by reflection, coerce values through the target types
   (`uuid.UUID`, JSON objects, aware datetimes to UTC), insert in batches
   with `foreign_keys=OFF` for speed, then require `PRAGMA
   foreign_key_check` to return nothing.
5. Verify: per-table row counts match, and a per-table content hash over
   a normalized JSON dump of every row (sorted keys, UTC ISO datetimes,
   canonical UUID text) matches source to target. Print the report;
   exit non-zero on any mismatch and leave the target in place for
   inspection.

The exporter is the only code that speaks Postgres after this lands.
`psycopg[binary]` moves from core dependencies to an optional extra
`legacy-postgres`, installed in the release-N image and dropped in N+1.

**Backup** (`update.sh` and a new `python -m app.tools.backup_db`):
from release N+1 the pre-update backup is a SQLite online backup
(`sqlite3.Connection.backup()`, WAL-safe, run inside the backend
container) gzipped to `backups/db-<ts>-<version>.sqlite3.gz`, pruned by the
existing `prune_keep_last`. Release N still takes the `pg_dump` first,
because the Postgres data is what the migration is about to read.

### 2.7 Tests and CI

- `conftest.py`: default `TEST_DATABASE_URL` becomes a SQLite file under
  `tmp_path_factory`'s session dir. The `CREATE DATABASE` branch and both
  "Postgres is unreachable, run `docker compose up -d postgres`" messages
  go. `_test_database_ready` keeps running `alembic upgrade head`.
- `db_session` builds one engine per session instead of per test (the
  per-test engine existed to dodge Postgres's 100-connection cap, which no
  longer applies) and still disposes it.
- `_clear_tables` becomes dialect-neutral: `DELETE FROM` in reverse
  `sorted_tables` order with `foreign_keys=OFF` for the duration.
- The three tests that already build an in-memory `sqlite://` engine keep
  working and stop being special.
- CI: the `test` job loses its `postgres` service. A `legacy-export` job
  with a Postgres service runs the exporter round-trip test (§6) and is
  deleted in N+1 together with the exporter.
- `mcp_server/tests/` are DB-free and unaffected.

## 3. Behaviour under load and failure

### 3.1 Concurrency model

One writer process. The web UI, the MCP server, the extension and the chat
agent all reach the database through the single uvicorn process. SQLite in
WAL mode gives readers no locks and writers a short exclusive window at
commit. `busy_timeout=30000` makes a second writer wait rather than fail.

### 3.2 "database is locked"

Reachable only if a transaction holds a write lock across something slow.
With `autoflush=False`, the write lock is taken at the first flushed
INSERT/UPDATE, normally at commit. The risk is an explicit `flush()` or
`commit()` **before** an LLM call inside the same session. A grep for the
LLM client names 22 files under `services/` (several are the client and
its tracing, not callers); the plan must audit each caller for that shape
and fix any found by moving the flush after the call or splitting the
transaction.
`tailoring_session.tailor()` is the first to check: it applies pre-ops in
memory and commits once at the end, which is the correct shape.
Acceptance for the audit: a tailoring run and an MCP `score_ats` on another
job, started concurrently, both succeed.

### 3.3 Disk and durability

`synchronous=NORMAL` under WAL is durable against an application crash and
can lose the last transactions on OS crash or power loss. Accepted for a
single-user tool with pre-update backups; `FULL` may be chosen later if a
user reports otherwise. Disk-full surfaces as `sqlite3.OperationalError`
from the ORM, which the existing error handling already maps to a 500 with
the message; no new handling.

### 3.4 Datetimes

The decorator in §2.3 is the whole fix. Two things prove it: a round-trip
test (write aware, read aware, equal), and the calibration monotonicity run,
because recency scoring compares stored dates to "today".

### 3.5 Migration failure modes

- Source unreachable: exporter refuses; `update.sh` stops before touching
  images and names the backup it took.
- Verification mismatch: exporter exits non-zero, leaves the target for
  inspection, `update.sh` stops. The Postgres volume is untouched, so the
  previous release still runs (`docs/RELEASING.md` rollback recipe).
- Interrupted mid-copy: the target is incomplete and non-empty; rerunning
  requires `--replace`, which is what `update.sh` passes on a retry.
- Fresh install (never had Postgres): the source has no `alembic_version`
  table, so the import records "source-empty" in the marker and boot
  creates the file. Every decision keys off the marker file and the
  target's emptiness, never off version arithmetic.

## 4. Rollout

Two releases. Removal triggers are stated so this can become a §13 row.

**Release N** (`postgres-to-sqlite`, status `new-is-default`):
- SQLite is the only runtime database. Compose keeps the `postgres`
  service for this one release, still `depends_on` by `backend`, and passes
  `LEGACY_DATABASE_URL` so the first boot can import (§2.6). A fresh install
  pulls the Postgres image one last time and imports nothing.
- `update.sh` takes a `pg_dump` while no import marker exists, an online
  SQLite backup afterwards, and prints where the old volume is and how to
  remove it once satisfied. `--check` reports which database is live.
- `.env.example` keeps `POSTGRES_*` and `POSTGRES_HOST_PORT` for this one
  release, marked legacy. New keys: none. `DATA_DIR` is container-absolute
  and needs no `.env` entry.
- Docs updated (§5). README's prerequisite drops "PostgreSQL ~170 MB" from
  the download estimate.

**Release N+1** (removal trigger: "N shipped, and no open issue reports a
failed export"): delete `legacy_postgres/`, the exporter, the
`legacy-postgres` extra and CI job, the compose profile, the `pgdata`
volume declaration, `normalize_postgres_url`, and every `POSTGRES_*` key.
Cut the §13 row. Users who never ran N's `update.sh` are told to install N
first; `update.sh --check` on N+1 detects a `pgdata` volume with no SQLite
file and says exactly that.

## 5. Documentation and SYSTEM.md

Per the header contract: rewrite in place, dated narrative stays in git.

- §2 repo layout: `data/`, `app/tools/`, `legacy_postgres/` (N only).
- §3: "Postgres holds all state except…" becomes "`data/maestro_cs.sqlite3`
  holds all state except…".
- §6, new invariant `{#inv-single-dialect}`: **Column types come from
  `models/types.py` and nothing under `app/` imports `sqlalchemy.dialects`.**
  Enforcement: `tests/test_db_portability.py`; pin it in
  `.system_md_enforcement.json`.
- §9: the Postgres/55432 bullets go; the test-DB bullet becomes "no
  service needed; `pytest tests/ mcp_server/tests/ -q` from `backend/`";
  the "two dependency sources" bullet notes the `legacy-postgres` extra
  for N.
- §12: keep the alembic revision-id rule; add whatever bit during the port
  (candidates: `foreign_keys` is per-connection; batch mode for ALTER).
- §13: add the `postgres-to-sqlite` row with the N+1 trigger above.
- README (11 mentions), CONTRIBUTING (6), `docs/GETTING_STARTED.md` (2),
  `docs/RELEASING.md` (2, plus checklist step 8 "prove the update path"
  gains the export rehearsal), SECURITY.md line 191 (data inventory),
  KNOWN_ISSUES "a backup is two things" (the database half becomes one
  file; the bundle command is still open), `.env.example`.
- `scripts/setup-mcp.sh`, `mcpb/`, `plugins/`: no change. The MCP server
  never touched the database.

## 6. Verification gates (all must pass before the branch is "done")

1. Full suite green on SQLite: `pytest tests/ mcp_server/tests/ -q` from
   `backend/`, no service running.
2. Exporter round trip (CI `legacy-export`): seed a Postgres test DB
   through the legacy chain with representative rows (every table
   non-empty, aware datetimes, nested JSON, `enabled: false` entries),
   export, and assert the §2.6 hashes match and `foreign_key_check` is
   empty.
3. Calibration: `python -m scripts.ats_calibration snapshot before.json`
   on the maintainer's Postgres, the same after export to SQLite, and
   `diff` reports no contribution changes. Then `monotonicity`.
4. Concurrency acceptance from §3.2.
5. `scripts/update.sh` rehearsed on a second machine holding a real
   compose install: backup, export, boot, open the tracker, render a PDF.
6. `python3 scripts/check_system_md.py`, the slop ratchet on `backend/`
   (this is a backend-surface change; name it in the claim), and
   `python3 scripts/check_mcpb_bundle.py` (expected untouched).

## 7. Decisions still open for the owner

1. **Directory name.** `data/` as proposed, or reuse `settings/`?
   Recommendation: `data/`; settings are user-editable JSON and the DB is
   not.
2. **N+1 timing.** Next minor release, or a calendar window?
   Recommendation: next minor release, so the trigger is a release event
   the checklist already has.
3. **`synchronous`.** `NORMAL` as proposed, or `FULL`? Recommendation:
   `NORMAL`; revisit on the first corruption report.

## 8. What this unblocks (not in scope here)

With no daemon in the stack, the desktop shell's job shrinks to: start the
backend sidecar, open the UI, run the updater. The Typst-first probe and the
MCP-over-HTTP endpoint are independent of this change and can be planned in
parallel; the installer itself waits for all three.
