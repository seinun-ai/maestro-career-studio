# SQLite Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `data/maestro_cs.sqlite3` the only runtime database, with an automatic one-time import of an existing compose-era Postgres database, so the app needs no database daemon.

**Architecture:** One type module (`app/models/types.py`) replaces every Postgres dialect import; one engine constructor (`app/db.make_engine`) sets the SQLite pragmas per connection; the 54-revision Postgres chain is boxed under `backend/legacy_postgres/` and replaced by a single SQLite baseline; a tool under `app/tools/` copies a legacy Postgres database into the file at the first boot of this release and verifies it by row counts and per-table hashes. Everything Postgres is deleted one release later (SYSTEM.md §13 row `postgres-to-sqlite`).

**Tech Stack:** Python 3.12, SQLAlchemy 2.0, Alembic 1.18, pysqlite (stdlib), FastAPI, pytest, Docker Compose, GitHub Actions.

**Design:** [`2026-09-17-sqlite-migration-design.md`](2026-09-17-sqlite-migration-design.md). Read it first. One amendment is recorded there and applied here: the legacy import runs inside the backend at first boot (Task 11), not from `update.sh`, because an install on the previous release runs the previous release's `update.sh`, which cannot contain a step added in this one.

---

## Goal Card

**Goal:** Make Maestro CS installable as a native desktop app with a one-click MCP connection, without Docker or git. This step makes SQLite the only database, so the app never needs a database daemon, so a user's whole relational state is one file they can copy, and so the later installer has nothing to run, sign, or port-manage except the app itself.

**Principles:**
- One dialect at the end. Postgres survives exactly one release, and only inside the importer. No permanent dual-dialect code, no `with_variant` left behind.
- No existing install loses data. The import is automatic, atomic, verified, and leaves the Postgres volume untouched.
- Deterministic scores must not move. The ATS calibration snapshot on Postgres and on SQLite must diff clean.
- The security boundary does not weaken. One fewer zero-auth port; the DB file is mode 0600; every §6 invariant keeps its enforcement pin.
- Do not fix unrelated things while in there.

**Non-goals:** the desktop shell, engine probing for TeX, publishing the extension, MCP over HTTP.

**Autonomy:** peer. Adapt *how* when the repo disagrees with this plan; log every deviation in the **Deviation log** at the bottom of this file, with a one-line reason and the Goal Card line it serves. Never widen scope. When a step contradicts the Goal Card, stop and write a deviation note instead of working around it.

---

## Read before starting

- **Repo rules live in `SYSTEM.md`.** Its header contract applies to every doc edit you make: rewrite in place, no dated paragraphs outside §11–§13, section numbers frozen. Task 17 updates it; do not touch it earlier.
- **Interpreter.** Use the Python that has the backend installed editable. In this worktree that is `/opt/anaconda3/bin/python3` (SQLAlchemy 2.0.43, Alembic present). Verify: `python3 -c "import app, alembic, sqlalchemy"` from `backend/`. Every command below runs from `backend/` unless it says otherwise.
- **Tests need no service after Task 7.** Until Task 7, run only the test file each task names; the suite is inconsistent mid-port and that is expected.
- **Sessions use `autoflush=False`** (`app/db.py`). Keep it. On SQLite it is what keeps write locks short.
- **Alembic revision ids** are `uuid.uuid4().hex[:12]` (SYSTEM.md §12). Never hand-type one.
- **Lint gate:** `ruff check .` must pass before every commit (CI runs it before tests).
- **Commits:** small, one task each, conventional prefix, and end the message with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- **Do not touch** `mcp_server/`, `frontend/`, `extension/`, `mcpb/`, `plugins/`. None of them reach the database.
- **Deviation log** is the last section of this file. Append there; never rewrite an earlier entry.

---

### Task 1: The portability test (fails first, drives the port)

**Files:**
- Create: `backend/tests/test_db_portability.py`

**Step 1: Write the failing test**

```python
"""Pins SYSTEM.md §6 {#inv-single-dialect}: column types come from
app/models/types.py and nothing under app/ imports a SQLAlchemy dialect.

SQLite is the only runtime database. A dialect import anywhere else is how a
Postgres-only type or DDL option creeps back in and breaks the next fresh
install at boot.
"""
import re
from pathlib import Path

import sqlalchemy as sa

from app.db import Base
import app.models  # noqa: F401  registers every table
from app.models.types import UTCDateTime

APP = Path(__file__).resolve().parents[1] / "app"
TYPES_MODULE = APP / "models" / "types.py"
DIALECT_IMPORT = re.compile(r"^\s*(from|import)\s+sqlalchemy\.dialects", re.M)
POSTGRES_ONLY_DDL = re.compile(r"::jsonb|postgresql_where|postgresql_using|postgresql_ops")


def test_no_dialect_imports_outside_types_module():
    offenders = sorted(
        str(p.relative_to(APP))
        for p in APP.rglob("*.py")
        if p != TYPES_MODULE and DIALECT_IMPORT.search(p.read_text(encoding="utf-8"))
    )
    assert offenders == []


def test_no_postgres_only_ddl_in_models():
    offenders = sorted(
        p.name
        for p in (APP / "models").glob("*.py")
        if POSTGRES_ONLY_DDL.search(p.read_text(encoding="utf-8"))
    )
    assert offenders == []


def test_every_datetime_column_is_utcdatetime():
    # A bare sa.DateTime column would come back naive from SQLite and compare
    # unequal (or raise) against the aware datetimes every writer produces.
    bare = [
        f"{table.name}.{column.name}"
        for table in Base.metadata.sorted_tables
        for column in table.columns
        if isinstance(column.type, sa.DateTime)
    ]
    assert bare == []
    assert any(
        isinstance(column.type, UTCDateTime)
        for table in Base.metadata.sorted_tables
        for column in table.columns
    )
```

**Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_db_portability.py -q`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'app.models.types'`.

**Step 3: Commit**

```bash
git add tests/test_db_portability.py
git commit -m "test(db): pin the single-dialect invariant (red)"
```

---

### Task 2: The type module

> **Amended after review (2026-09-17):** `compare_type_unwrapping_decorators` and its test are REMOVED. Alembic 1.18 compares types by compiled DDL, so a `UTCDateTime` column already matches the `DATETIME` it created; the hook overrode that with a coarser check. `UTCDateTime.process_bind_param` also raises `TypeError` on a non-`datetime` value. See the deviation log.

**Files:**
- Create: `backend/app/models/types.py`
- Create: `backend/tests/test_model_types.py`

**Step 1: Write the failing tests**

```python
"""app.models.types: the one place a column type is chosen."""
import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.models.types import JSONDoc, UTCDateTime, UUIDType


class _Base(DeclarativeBase):
    pass


class _Row(_Base):
    __tablename__ = "rows"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    stamped: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=sa.func.now())
    doc: Mapped[dict | None] = mapped_column(JSONDoc)
    ref: Mapped[uuid.UUID | None] = mapped_column(UUIDType(as_uuid=True))


@pytest.fixture
def session():
    engine = sa.create_engine("sqlite://", future=True)
    _Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    engine.dispose()


def test_aware_datetime_round_trips_as_utc(session):
    ist = timezone(timedelta(hours=5, minutes=30))
    session.add(_Row(id=1, at=datetime(2026, 9, 17, 12, 0, tzinfo=ist)))
    session.commit()
    session.expunge_all()
    got = session.get(_Row, 1).at
    assert got.tzinfo == UTC
    assert got == datetime(2026, 9, 17, 6, 30, tzinfo=UTC)


def test_naive_datetime_is_refused(session):
    session.add(_Row(id=2, at=datetime(2026, 1, 1)))
    with pytest.raises(sa.exc.StatementError, match="naive datetime"):
        session.commit()


def test_server_default_reads_back_aware(session):
    session.add(_Row(id=3))
    session.commit()
    session.expunge_all()
    got = session.get(_Row, 3).stamped
    assert got.tzinfo == UTC
    assert abs(datetime.now(UTC) - got) < timedelta(minutes=5)


def test_json_and_uuid_round_trip(session):
    ref = uuid.uuid4()
    session.add(_Row(id=4, doc={"b": [1, 2], "a": None}, ref=ref))
    session.commit()
    session.expunge_all()
    row = session.get(_Row, 4)
    assert row.doc == {"b": [1, 2], "a": None}
    assert row.ref == ref and isinstance(row.ref, uuid.UUID)


def test_compare_type_unwraps_decorators():
    from sqlalchemy.dialects import sqlite

    from app.models.types import compare_type_unwrapping_decorators

    same = compare_type_unwrapping_decorators(None, None, None, sqlite.DATETIME(), UTCDateTime())
    other = compare_type_unwrapping_decorators(None, None, None, sa.Text(), UTCDateTime())
    passthrough = compare_type_unwrapping_decorators(None, None, None, sa.Text(), sa.Text())
    assert same is False and other is True and passthrough is None
```

**Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_model_types.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models.types'`.

**Step 3: Write the module**

```python
"""The ONE place a column type is chosen. SYSTEM.md §6 {#inv-single-dialect}.

SQLite is the only runtime database. These names exist so the port to it
happened in one file, and so nothing under app/ ever imports a dialect again.
"""
from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.types import TypeDecorator

# A JSON document: stored as text by SQLite, loaded as dict/list. Every query in
# the app treats these columns as opaque (load and store), which is what made
# the port from JSONB a rename.
JSONDoc = sa.JSON

# uuid.UUID in Python, CHAR(32) hex on disk. Call it exactly as the old dialect
# type was called: UUIDType(as_uuid=True).
UUIDType = sa.Uuid


class UTCDateTime(TypeDecorator):
    """Timezone-aware in Python, naive UTC on disk.

    SQLite has no timezone-aware column type. Every writer in the app uses
    datetime.now(UTC), so a NAIVE bind is a bug, not a convention, and it
    raises here rather than storing an ambiguous instant. Values read back
    (including CURRENT_TIMESTAMP server defaults, which SQLite emits in UTC)
    are stamped UTC so comparisons against datetime.now(UTC) stay legal.
    """

    impl = sa.DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError(
                "naive datetime bound to a UTCDateTime column; use datetime.now(UTC)"
            )
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def compare_type_unwrapping_decorators(
    context, inspected_column, metadata_column, inspected_type, metadata_type
):
    """Alembic `compare_type` hook. Alembic compares a TypeDecorator by its
    class name and would report every UTCDateTime as a change against the
    DATETIME it created. Compare by the decorator's impl instead; defer to
    Alembic for everything else (None)."""
    if isinstance(metadata_type, TypeDecorator):
        return not isinstance(inspected_type, type(metadata_type.impl))
    return None
```

**Step 4: Run to verify they pass**

Run: `python3 -m pytest tests/test_model_types.py -q`
Expected: 5 passed.

**Step 5: Commit**

```bash
git add app/models/types.py tests/test_model_types.py
git commit -m "feat(db): one type module for SQLite (JSONDoc, UUIDType, UTCDateTime)"
```

---

### Task 3: Port the 18 model files (codemod, then the red test goes green)

**Files:**
- Modify: every `backend/app/models/*.py` that imports `sqlalchemy.dialects.postgresql` (18 files; the codemod finds them)
- Modify: `backend/app/models/ats_score.py:22` (`postgresql_where` → `sqlite_where`)
- Modify: `backend/app/models/career_kb.py:28,75,143,147` (`'{}'::jsonb` / `'[]'::jsonb` defaults)

**Step 1: Run the codemod once (not committed as a file)**

From `backend/`:

```bash
python3 - <<'PY'
import re
from pathlib import Path

models = Path("app/models")
for path in sorted(models.glob("*.py")):
    if path.name in {"types.py", "__init__.py"}:
        continue
    src = path.read_text(encoding="utf-8")
    out = src
    out = re.sub(r"^from sqlalchemy\.dialects\.postgresql import [A-Za-z_, ]+\n", "", out, flags=re.M)
    names = set()
    if re.search(r"\bJSONB\b", out):
        out = re.sub(r"\bJSONB\b", "JSONDoc", out)
        names.add("JSONDoc")
    if "UUID(as_uuid=True)" in out:
        out = out.replace("UUID(as_uuid=True)", "UUIDType(as_uuid=True)")
        names.add("UUIDType")
    if "DateTime(timezone=True)" in out:
        out = out.replace("DateTime(timezone=True)", "UTCDateTime()")
        names.add("UTCDateTime")
    out = out.replace("sa_text(\"'{}'::jsonb\")", "sa_text(\"'{}'\")")
    out = out.replace("sa_text(\"'[]'::jsonb\")", "sa_text(\"'[]'\")")
    out = out.replace("postgresql_where=", "sqlite_where=")
    if names:
        lines = out.split("\n")
        anchor = max(
            i for i, line in enumerate(lines)
            if line.startswith("from sqlalchemy") or line.startswith("import sqlalchemy")
        )
        lines.insert(anchor + 1, f"from app.models.types import {', '.join(sorted(names))}")
        out = "\n".join(lines)
    if out != src:
        path.write_text(out, encoding="utf-8")
        print("rewrote", path.name)
PY
```

Expected: 18 or more `rewrote` lines (files that only had `DateTime(timezone=True)` are rewritten too).

**Step 2: Let ruff drop the now-unused `DateTime` imports, then read the diff**

```bash
ruff check --fix app/models && git diff --stat app/models
```

Read `git diff app/models/ats_score.py app/models/career_kb.py` in full: the unique index must now say `sqlite_where=text("phase = 'base'")`, and the four server defaults must be `'{}'` / `'[]'` with no cast. If a file imports `DateTime` for another reason ruff will keep it; that is fine.

**Step 2b: The API boundary for `applied_at`** (added after review)

`ApplicationPatch.applied_at` (`app/schemas/application.py:35`) is the one request-side `datetime` field, and `routers/applications.py:343-344` writes it through. Pydantic parses `"2026-08-18T14:32:11"` as a NAIVE datetime, which `UTCDateTime` now refuses at flush, i.e. a 500. Type the field as `pydantic.AwareDatetime` so a naive value is a 422 at the boundary. Add to `tests/test_applications_router.py` a test that PATCHes `{"applied_at": "2026-08-18T14:32:11"}` and asserts 422, and one that PATCHes `"2026-08-18T14:32:11+00:00"` and asserts 200 with the value stored.

**Step 3: Run the portability test**

Run: `python3 -m pytest tests/test_db_portability.py tests/test_model_types.py -q`
Expected: all pass. If `test_every_datetime_column_is_utcdatetime` lists a column, that model used a bare `DateTime` with no `timezone=True`; convert it to `UTCDateTime()` by hand and note it in the deviation log (it was naive by accident, not by design; check its writers use `datetime.now(UTC)`).

**Step 4: Lint and commit**

```bash
ruff check . && git add app/models && git commit -m "refactor(models): route every column type through app.models.types"
```

---

### Task 4: Settings: `data_dir`, a derived SQLite `database_url`, and a loud refusal of Postgres URLs

> **Amended after review (2026-09-17):** the refusal is an ALLOWLIST (`make_url(value).get_backend_name() != "sqlite"` → refuse), the same rule Task 7's conftest enforces, so `postgres://` and any other backend are refused with one message; `database_url` derives from `data_dir.resolve()`; tests import `app.config` before writing env vars (the module builds a `settings` singleton at import) and cover `sqlite_journal_mode` normalization and refusal. See the deviation log.

**Files:**
- Modify: `backend/app/config.py:17-32` (docstring of `normalize_postgres_url`), `:68` (`database_url`), `:82-86` (validator), `:163-168` (data dirs)
- Modify: `backend/tests/test_config.py:1-11`

**Step 1: Write the failing tests** (replace `test_settings_reads_env` at the top of `tests/test_config.py`; keep every other test)

```python
import pytest
from pydantic import ValidationError


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("DATABASE_URL", "sqlite:////tmp/x.sqlite3")

    from app.config import Settings

    s = Settings(_env_file=None)

    assert s.openai_api_key == "sk-test"
    assert s.database_url == "sqlite:////tmp/x.sqlite3"
    assert s.fast_model == "gpt-5.6-luna"


def test_database_url_derives_from_data_dir(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATA_DIR", "/srv/mcs")

    from app.config import Settings

    assert Settings(_env_file=None).database_url == "sqlite:////srv/mcs/maestro_cs.sqlite3"


def test_postgres_database_url_is_refused(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://app:app@postgres:5432/maestro_cs")

    from app.config import Settings

    with pytest.raises(ValidationError, match="no longer a runtime database"):
        Settings(_env_file=None)


def test_legacy_database_url_is_a_plain_setting(monkeypatch):
    monkeypatch.setenv("LEGACY_DATABASE_URL", "postgresql://app:app@postgres:5432/maestro_cs")

    from app.config import Settings

    assert Settings(_env_file=None).legacy_database_url.startswith("postgresql")
```

**Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_config.py -q`
Expected: the four new tests fail (`database_url` still normalizes to `postgresql+psycopg://…`; `DATA_DIR` and `LEGACY_DATABASE_URL` unknown).

**Step 3: Edit `app/config.py`**

Replace the `database_url` field and its validator with:

```python
    # Empty = derived from data_dir after validation (see _derive_database_url).
    # Set it only to point at another FILE: sqlite:////absolute/path.sqlite3.
    # Postgres URLs are refused on purpose: SQLite is the only runtime database
    # and the legacy importer is the only Postgres reader (SYSTEM.md §13).
    database_url: str = ""
    # ONE release only (SYSTEM.md §13 postgres-to-sqlite): the compose-era
    # Postgres database to import at first boot. Unset = nothing to import.
    legacy_database_url: str = ""
    # WAL is right on a local disk. The escape hatch exists for filesystems whose
    # shared-memory semantics SQLite cannot trust (some Docker Desktop bind-mount
    # backends): set DELETE there. Only these two values are accepted.
    sqlite_journal_mode: str = "WAL"

    @field_validator("database_url")
    @classmethod
    def _refuse_postgres(cls, value: str) -> str:
        if value.startswith("postgresql"):
            raise ValueError(
                "DATABASE_URL points at Postgres, which is no longer a runtime database. "
                "Leave DATABASE_URL unset; a compose-era database is imported into the "
                "SQLite file automatically at boot when LEGACY_DATABASE_URL is set "
                "(or run: python -m app.tools.migrate_from_postgres)."
            )
        return value

    @field_validator("sqlite_journal_mode")
    @classmethod
    def _journal_mode_is_known(cls, value: str) -> str:
        mode = value.strip().upper()
        if mode not in {"WAL", "DELETE"}:
            raise ValueError("SQLITE_JOURNAL_MODE must be WAL or DELETE")
        return mode

    @model_validator(mode="after")
    def _derive_database_url(self):
        if not self.database_url:
            self.database_url = f"sqlite:///{self.data_dir / 'maestro_cs.sqlite3'}"
        return self
```

Add `model_validator` to the `pydantic` import line. Add the directory next to the other data dirs:

```python
    # Everything relational lives in ONE file under here (SYSTEM.md §3):
    # maestro_cs.sqlite3 plus its -wal/-shm sidecars. Bind-mounted from ./data
    # in compose; override with DATA_DIR when running the backend yourself.
    data_dir: Path = Path("/app/data")
```

`data_dir` must be declared **above** `database_url` is not required (the model validator runs after all fields), but keep it with its siblings at lines 163–168 for readability.

Change the docstring of `normalize_postgres_url` to begin: `"""Force the psycopg v3 dialect onto a bare postgresql:// URL. Used ONLY by the legacy importer (app/tools/migrate_from_postgres.py); delete with it (SYSTEM.md §13 postgres-to-sqlite).` Keep the function.

**Step 4: Run to verify they pass**

Run: `python3 -m pytest tests/test_config.py -q`
Expected: all pass. (`scrub_empty_env` already deletes an empty `DATABASE_URL` from the environment, so `VAR: ${VAR:-}` style empties still mean "derive".)

**Step 5: Commit**

```bash
ruff check . && git add app/config.py tests/test_config.py && git commit -m "feat(config): data_dir, derived SQLite database_url, refuse Postgres URLs"
```

---

### Task 5: One engine constructor with the SQLite pragmas

**Files:**
- Modify: `backend/app/db.py` (whole file)
- Modify: `backend/tests/test_db.py` (whole file)

**Step 1: Write the failing tests** (replace `tests/test_db.py`)

```python
import os
import stat
from pathlib import Path

from app.db import make_engine, sqlite_path


def test_session_factory_creates_session():
    from app.db import SessionLocal

    with SessionLocal() as s:
        assert s is not None


def test_make_engine_applies_sqlite_pragmas_per_connection(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 't.sqlite3'}")
    try:
        with engine.connect() as conn:
            assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
            assert conn.exec_driver_sql("PRAGMA journal_mode").scalar().lower() == "wal"
            assert conn.exec_driver_sql("PRAGMA busy_timeout").scalar() == 30000
            assert conn.exec_driver_sql("PRAGMA synchronous").scalar() == 1  # NORMAL
    finally:
        engine.dispose()


def test_make_engine_honours_delete_journal_mode(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 't.sqlite3'}", journal_mode="DELETE")
    try:
        with engine.connect() as conn:
            assert conn.exec_driver_sql("PRAGMA journal_mode").scalar().lower() == "delete"
    finally:
        engine.dispose()


def test_make_engine_creates_the_file_with_mode_0600(tmp_path):
    path = tmp_path / "nested" / "t.sqlite3"
    make_engine(f"sqlite:///{path}").dispose()
    assert path.exists()
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_sqlite_path_only_for_file_urls():
    assert sqlite_path("sqlite://") is None
    assert sqlite_path("sqlite:///:memory:") is None
    assert sqlite_path("postgresql+psycopg://x/y") is None
    assert sqlite_path("sqlite:////tmp/a.sqlite3") == Path("/tmp/a.sqlite3")
```

**Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_db.py -q`
Expected: FAIL with `ImportError: cannot import name 'make_engine'`.

**Step 3: Rewrite `app/db.py`**

```python
"""Engine and session factory.

SQLite is the only runtime database (SYSTEM.md §3). `make_engine` is the ONE
engine constructor: the app, the test suite, the migrations' verify step and
the legacy importer all go through it, so every connection carries the same
pragmas. A connection without them is not "the same database": SQLite forgets
all four when a connection closes, and foreign_keys defaults to OFF.
"""
import os
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

DB_FILENAME = "maestro_cs.sqlite3"


def sqlite_path(url: str) -> Path | None:
    """The file behind a sqlite URL, or None for another backend or :memory:."""
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite":
        return None
    if not parsed.database or parsed.database == ":memory:":
        return None
    return Path(parsed.database)


def _prepare_sqlite_file(path: Path) -> None:
    # Pre-create with the mode set rather than chmod-ing after (the
    # llm._log_call precedent): a zero-byte file is a valid empty SQLite
    # database, and the window between sqlite's own create and a chmod is a
    # window in which a world-readable copy of the career record exists.
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
        os.close(fd)


def make_engine(url: str, *, journal_mode: str | None = None) -> Engine:
    """Build an engine for `url` with the SQLite pragmas installed per connection."""
    mode = (journal_mode or settings.sqlite_journal_mode).upper()
    if mode not in {"WAL", "DELETE"}:
        raise ValueError(f"journal_mode must be WAL or DELETE, not {mode!r}")

    connect_args: dict = {}
    is_sqlite = make_url(url).get_backend_name() == "sqlite"
    if is_sqlite:
        # The DBAPI-level busy wait, in seconds. PRAGMA busy_timeout below is
        # the same knob for connections sqlite3 hands to other code paths.
        connect_args["timeout"] = 30
        path = sqlite_path(url)
        if path is not None:
            _prepare_sqlite_file(path)

    engine = create_engine(url, future=True, connect_args=connect_args)

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_connection, _record):
        if not isinstance(dbapi_connection, sqlite3.Connection):
            return
        cursor = dbapi_connection.cursor()
        cursor.execute(f"PRAGMA journal_mode={mode}")
        # 21 relationships rely on ondelete=; without this line they silently
        # stop cascading. Per connection, not per database.
        cursor.execute("PRAGMA foreign_keys=ON")
        # Durable against an app crash; may lose the last transactions on OS
        # crash or power loss. Accepted for a single-user tool with pre-update
        # backups (design §3.3).
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

    return engine


# TEST_DATABASE_URL first, on purpose: the suite must never touch the file under
# data/ (tests/conftest.py refuses a URL that resolves there).
_db_url = os.environ.get("TEST_DATABASE_URL") or settings.database_url
engine = make_engine(_db_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    with SessionLocal() as session:
        yield session
```

**Step 4: Run to verify they pass**

Run: `python3 -m pytest tests/test_db.py -q`
Expected: 5 passed. (`conftest.py` still exports a Postgres `TEST_DATABASE_URL` at this point; `make_engine` builds it without connecting, so import succeeds. If the import fails with `No module named 'psycopg'`, run this one task with `TEST_DATABASE_URL=sqlite:////tmp/task5.sqlite3` exported.)

**Step 5: Commit**

```bash
ruff check . && git add app/db.py tests/test_db.py && git commit -m "feat(db): make_engine installs the SQLite pragmas per connection"
```

---

### Task 6: Box the Postgres chain; generate the SQLite baseline

**Files:**
- Move: `backend/migrations/` → `backend/legacy_postgres/migrations/` (git mv; includes `versions/`, `env.py`, `script.py.mako`, `README`, `prompt_defaults.lock.json`)
- Create: `backend/legacy_postgres/alembic.ini` (copy of `backend/alembic.ini`)
- Modify: `backend/legacy_postgres/migrations/env.py`
- Create: `backend/migrations/env.py`, `backend/migrations/script.py.mako` (copy), `backend/migrations/versions/<id>_sqlite_baseline.py`
- Modify: `backend/alembic.ini:89` (delete the placeholder `sqlalchemy.url` line) and the same line in the legacy copy

**Step 1: Check nothing in the app reads a file that is about to move**

```bash
grep -rn "prompt_defaults.lock.json\|migrations/" app scripts | grep -v "^app/services/seeding.py"
```

Expected: no hits outside the migrations tree. If the app reads `migrations/prompt_defaults.lock.json`, copy the file into the new `migrations/` as well and log a deviation.

**Step 2: Move the chain**

```bash
mkdir -p legacy_postgres
git mv migrations legacy_postgres/migrations
cp alembic.ini legacy_postgres/alembic.ini
sed -i '' '/^sqlalchemy.url = driver:/d' alembic.ini legacy_postgres/alembic.ini
```

(`sed -i ''` is the macOS form; on Linux use `sed -i`.) `script_location = %(here)s/migrations` in each ini resolves relative to that ini's directory, so both work unchanged.

**Step 3: Make the legacy `env.py` read ONLY an explicit URL and no models**

Replace the block from `from app.config import …` through `config.set_main_option(...)` in `legacy_postgres/migrations/env.py` with:

```python
from app.config import normalize_postgres_url

# ONE release only (SYSTEM.md §13 postgres-to-sqlite). This chain never sees the
# app's own database again: it runs only against a compose-era Postgres source,
# named explicitly by the importer (set_main_option) or on the command line.
config = context.config
_url = config.get_main_option("sqlalchemy.url") or os.environ.get("LEGACY_DATABASE_URL")
if not _url:
    raise RuntimeError(
        "legacy_postgres: no source URL. Set LEGACY_DATABASE_URL or pass it through "
        "app.tools.migrate_from_postgres; this chain must never run against the SQLite file."
    )
config.set_main_option("sqlalchemy.url", normalize_postgres_url(_url))
```

Delete `from app.db import Base` and `from app.models import *`, and set `target_metadata = None` (the chain only ever upgrades now; autogenerate against the ported models would be nonsense).

**Step 4: Write the new `migrations/env.py`**

```python
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import settings
from app.db import Base
from app.models import *  # noqa: F403  registers models for autogenerate

config = context.config

# Same resolution order as app/db.py, and it must stay that way: the test
# suite migrates its own throwaway file through alembic, and reading only
# settings.database_url here would point those migrations at the real data.
# The importer sets sqlalchemy.url explicitly to build a schema elsewhere.
DATABASE_URL = (
    config.get_main_option("sqlalchemy.url")
    or os.environ.get("TEST_DATABASE_URL")
    or settings.database_url
)

if config.config_file_name is not None:
    # disable_existing_loggers defaults to TRUE and would silence the app's own
    # loggers: seeding.run_startup() runs `alembic upgrade head` in-process.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # A plain engine, NOT app.db.make_engine: SQLite's documented ALTER TABLE
    # recipe (which batch mode implements) must run with foreign_keys OFF, and
    # make_engine turns it ON for every connection.
    connectable = create_engine(DATABASE_URL, future=True, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

```bash
cp legacy_postgres/migrations/script.py.mako migrations/script.py.mako
mkdir -p migrations/versions
```

**Step 5: Generate the baseline against an empty file**

```bash
rm -f /tmp/mcs-baseline.sqlite3
REV="$(python3 -c 'import uuid; print(uuid.uuid4().hex[:12])')"
TEST_DATABASE_URL=sqlite:////tmp/mcs-baseline.sqlite3 python3 -m alembic revision --autogenerate -m "sqlite baseline" --rev-id "$REV"
```

Expected: `Generating .../migrations/versions/<REV>_sqlite_baseline.py ... done`, with one `create_table` per model.

**Step 6: Review and hand-fix the generated file** (each item is a known Alembic rendering gap, not a judgment call)

1. `grep -n "postgresql\|JSONB" migrations/versions/*_sqlite_baseline.py` → must print nothing.
2. `grep -n "sa.UTCDateTime()" …` → replace every occurrence with `sa.DateTime()`. Alembic renders a user TypeDecorator under the `sa.` prefix, where it does not exist. The on-disk type is DateTime; the decorator is a Python-side concern.
3. `grep -n "sqlite_where" …` → exactly one, on `uq_ats_scores_base_target`.
4. `grep -n "sa.JSON()\|sa.Uuid()" …` → present.
5. Replace the module docstring with:
   ```
   """SQLite baseline.

   The 54-revision Postgres chain (head 85a1bb628e28) lives under
   backend/legacy_postgres/ for one release and is read only by
   app/tools/migrate_from_postgres.py (SYSTEM.md §13 postgres-to-sqlite). A
   fresh database starts here; runtime seeding (ensure_seed_templates,
   seeding.run_startup) covers what the old chain's data migrations did.
   """
   ```

**Step 7: Prove the baseline is the models**

```bash
rm -f /tmp/mcs-check.sqlite3
TEST_DATABASE_URL=sqlite:////tmp/mcs-check.sqlite3 python3 -m alembic upgrade head
TEST_DATABASE_URL=sqlite:////tmp/mcs-check.sqlite3 python3 -m alembic check
```

Expected: the upgrade logs one `Running upgrade -> <REV>` line; `alembic check` prints `No new upgrade operations detected.` If it reports a type change, read the diff it prints: Alembic compares by compiled DDL, so a real report means the baseline and the models disagree. Fix the baseline, never the comparison. Log it.

**Step 8: Lint and commit**

```bash
ruff check . && git add -A alembic.ini legacy_postgres migrations && git commit -m "refactor(db): box the Postgres migration chain; add the SQLite baseline"
```

---

### Task 7: Test fixtures on a throwaway SQLite file

**Files:**
- Modify: `backend/tests/conftest.py:1-10`, `:79-110`, `:112-201`, `:203-236`
- Modify: `backend/tests/test_migration_model_parity.py`

**Step 1: Replace the DB parts of `tests/conftest.py`**

Top of file (replace lines 1–10):

```python
import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

# The suite runs on a throwaway SQLite FILE (not :memory:) so the app's own
# engine (app.db, read at import) and the fixtures' engine open the same
# database. Per process, so two sessions running the suite at once cannot
# trip over each other the way the shared Postgres test database used to.
_OWNED_TMP: str | None = None
if not os.environ.get("TEST_DATABASE_URL"):
    _OWNED_TMP = tempfile.mkdtemp(prefix="maestro_cs_test_")
    os.environ["TEST_DATABASE_URL"] = f"sqlite:///{Path(_OWNED_TMP) / 'maestro_cs_test.sqlite3'}"
```

Keep the `ALLOWED_HOSTS` and `MAESTRO_CS_EXTENSION_IDS` blocks as they are. Replace the imports at lines 27–55 with:

```python
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from tests.ats.fixtures import fake_embed_texts
```

(The 22 model imports existed only for `_clear_tables`; it now walks `Base.metadata`.)

Replace the block from `FORBIDDEN_DB_NAMES = …` through the end of `_validate_test_db_url` with:

```python
# Tests delete from every table. Refuse anything that could be real data: a
# file under the repo's data/ mount, or a file named like the dev database.
FORBIDDEN_DB_STEMS = {"maestro_cs", "career_studio", "resume_auto"}
REPO_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _validate_test_db_url(url: str | None) -> str:
    if not url:
        raise RuntimeError(
            "TEST_DATABASE_URL is not set. Tests delete every table and refuse to "
            "guess; leave it unset to get a throwaway file under the temp dir."
        )
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite":
        raise RuntimeError(
            "TEST_DATABASE_URL must be a sqlite:/// URL. SQLite is the only runtime "
            "database (SYSTEM.md §3); Postgres reaches the app only through "
            "app/tools/migrate_from_postgres.py."
        )
    if not parsed.database or parsed.database == ":memory:":
        raise RuntimeError(
            "TEST_DATABASE_URL must name a FILE: the app process and the fixtures "
            "open separate connections, and an in-memory database is per-connection."
        )
    path = Path(parsed.database).resolve()
    if REPO_DATA_DIR in path.parents or path.stem in FORBIDDEN_DB_STEMS:
        raise RuntimeError(
            f"TEST_DATABASE_URL {url!r} looks like real data; use a throwaway file "
            f"outside {REPO_DATA_DIR} whose name is not one of {sorted(FORBIDDEN_DB_STEMS)}."
        )
    return url
```

Replace `_test_database_ready`, `db_session` and `_clear_tables` (lines 112–236) with:

```python
@pytest.fixture(scope="session", autouse=True)
def _test_database_ready() -> Iterator[None]:
    """Migrate the throwaway file before anything runs, and remove it after.

    Explicit and order-independent: without this the schema appeared only when
    some test opened `TestClient(app)` as a context manager (whose lifespan
    runs `alembic upgrade head`), and a file run alone failed with
    "no such table" — which reads like a broken test, not a missing setup.
    """
    _validate_test_db_url(TEST_DATABASE_URL)
    alembic_ini = Path(__file__).resolve().parents[1] / "alembic.ini"
    cfg = Config(str(alembic_ini))
    cfg.set_main_option("script_location", str(alembic_ini.parent / "migrations"))
    command.upgrade(cfg, "head")
    yield
    if _OWNED_TMP:
        shutil.rmtree(_OWNED_TMP, ignore_errors=True)


@pytest.fixture(scope="session")
def _test_engine():
    # Imported here, not at module top: this module sets env vars before any
    # app import (see the E402 note in pyproject), and app.db reads them.
    from app.db import make_engine

    engine = make_engine(_validate_test_db_url(TEST_DATABASE_URL))
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(_test_engine) -> Iterator[Session]:
    SessionLocal = sessionmaker(bind=_test_engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        _clear_tables(session)
        session.commit()
        yield session
        session.rollback()
        _clear_tables(session)
        session.commit()


def _clear_tables(session: Session) -> None:
    from app.db import Base
    import app.models  # noqa: F401  registers every table

    # Children before parents, so no DELETE trips a foreign key: the
    # connection has foreign_keys=ON (app.db.make_engine), which is the point.
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
```

**Step 2: Update `tests/test_migration_model_parity.py`**

```python
"""Catch a model shipped without its migration.

The suite migrates its file through alembic and only ever DELETEs, so a new
column on a model would otherwise surface as "no such column" in unrelated
tests rather than as a clear failure here.
"""

import os

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app.db import Base, make_engine
import app.models  # noqa: F401  import side effect: registers every table


def test_models_match_migrations(db_session):
    engine = make_engine(os.environ["TEST_DATABASE_URL"])
    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn, opts={"compare_type": True})
            diff = compare_metadata(ctx, Base.metadata)
    finally:
        engine.dispose()

    def owned(entry) -> bool:
        table = getattr(entry[1] if len(entry) > 1 else None, "name", None) or ""
        return not str(table).startswith("alembic_")

    unexpected = [d for d in diff if owned(d)]
    assert not unexpected, (
        "models and migrations disagree — generate a revision "
        f"(uuid.uuid4().hex[:12] per SYSTEM.md §12):\n{unexpected}"
    )
```

**Step 3: Run the DB-shaped tests first**

Run: `python3 -m pytest tests/test_db.py tests/test_migration_model_parity.py tests/test_db_portability.py tests/test_config.py -q`
Expected: all pass, with no service running.

**Step 4: Run the whole suite once and record the shape of the failures**

Run: `python3 -m pytest tests/ mcp_server/tests/ -q --ignore=tests/ats/test_golden.py -x -p no:randomly 2>&1 | tail -30` then without `-x`:

`python3 -m pytest tests/ mcp_server/tests/ -q --ignore=tests/ats/test_golden.py 2>&1 | tail -40`

Expected: failures concentrated in the explore tests (`date_trunc`) and any test binding naive datetimes. Paste the summary line (`N failed, M passed`) into the deviation log as the Task 7 baseline. Do not fix anything yet.

**Step 5: Commit**

```bash
ruff check . && git add tests/conftest.py tests/test_migration_model_parity.py && git commit -m "test: run the suite on a throwaway SQLite file, no service"
```

---

### Task 8: Week buckets without `date_trunc` (three sites, one definition)

**Files:**
- Modify: `backend/app/services/explore_activity.py:7-10`, `:24-33`, `:50-60`
- Modify: `backend/app/routers/explore.py:5`, `:258-282`
- Modify: `backend/app/services/explore_gaps.py:7-12`, `:192-226`
- Tests already exist: `tests/test_explore_activity.py::test_activity_week_granularity_and_coercion`, `tests/test_explore_router.py` (role-mix at line ~409), `tests/test_explore_gaps.py::test_ats_over_time_buckets_weekly_by_phase_and_role`, `::test_ats_over_time_flags_low_sample_buckets`

**Step 1: Run the three test files to see them fail**

Run: `python3 -m pytest tests/test_explore_activity.py tests/test_explore_router.py tests/test_explore_gaps.py -q`
Expected: failures mentioning `date_trunc` (`OperationalError: no such function`).

**Step 2: `explore_activity.py`: the one definition of a week bucket**

Change the imports to `from datetime import UTC, date, datetime, time, timedelta` and drop `Date` from the sqlalchemy import. Add above `_bucket_starts`:

```python
def week_start(day: date) -> date:
    """Monday of the week holding `day`. The ONE definition of a week bucket;
    explore.role_mix_over_time and explore_gaps.ats_over_time import it, so
    the three weekly charts can never disagree about where a week begins."""
    return day - timedelta(days=day.weekday())


def bucket_for(value: datetime, granularity: str) -> date:
    day = value.astimezone(UTC).date()
    return week_start(day) if granularity == "week" else day
```

In `_bucket_starts`, replace `this_monday = today - timedelta(days=today.weekday())` with `this_monday = week_start(today)` and update its docstring line to `Week buckets start on Monday (week_start).`

Replace `_series` inside `activity()`:

```python
    def _series(column) -> dict[str, int]:
        # Bucketed in Python, not SQL: date_trunc was Postgres-only and the
        # data is single-user scale, so a dialect-free query costs nothing.
        stmt = select(column).where(column.is_not(None), column >= window_start)
        if source:
            stmt = stmt.where(Application.source == source)
        counts: dict[str, int] = {}
        for (value,) in db.execute(stmt):
            key = bucket_for(value, granularity).isoformat()
            counts[key] = counts.get(key, 0) + 1
        return counts
```

**Step 3: `routers/explore.py`: role mix over time**

Drop `Date` from the sqlalchemy import; add `from datetime import UTC, date` and `from app.services.explore_activity import week_start`. Replace the body of `role_mix_over_time` after the `window` guard:

```python
    rows = db.execute(
        select(Job.created_at, Job.role_category).where(Job.role_category.is_not(None))
    ).all()
    counts: dict[tuple[date, str], int] = {}
    for created_at, category in rows:
        key = (week_start(created_at.astimezone(UTC).date()), category)
        counts[key] = counts.get(key, 0) + 1
    return [
        {"week_start": ws.isoformat(), "role_category": category, "count": n}
        for (ws, category), n in sorted(counts.items())
    ]
```

**Step 4: `services/explore_gaps.py`: ATS over time**

Drop `Date` from the sqlalchemy import; add `from datetime import UTC, date` and `from app.services.explore_activity import week_start`. Replace the body of `ats_over_time` from `week_start = …` to the end of the function:

```python
    stmt = (
        select(AtsScore.created_at, AtsScore.phase, Job.role_category, AtsScore.composite)
        .join(Job, Job.id == AtsScore.job_id)
        .where(Job.role_category.is_not(None))
    )
    stmt = _apply_job_filters(stmt, role_category, level, employment_type)

    groups: dict[tuple[date, str, str], list[float]] = defaultdict(list)
    for created_at, phase, category, composite in db.execute(stmt):
        groups[(week_start(created_at.astimezone(UTC).date()), phase, category)].append(
            float(composite)
        )

    # Same order the SQL version produced: week, role_category, phase.
    ordered = sorted(groups.items(), key=lambda item: (item[0][0], item[0][2], item[0][1]))
    return [
        {
            "week_start": ws.isoformat(),
            "phase": phase,
            "role_category": category,
            "avg_composite": round(sum(values) / len(values), 1),
            "n": len(values),
            "low_sample": _low_sample(len(values)),
        }
        for (ws, phase, category), values in ordered
    ]
```

(`defaultdict` is already imported in that module. If `_apply_job_filters` needs the select to carry a specific shape, read its body before assuming; it adds `where` clauses on `Job` columns and does not care which columns are selected.)

**Step 5: Run the three test files**

Run: `python3 -m pytest tests/test_explore_activity.py tests/test_explore_router.py tests/test_explore_gaps.py -q`
Expected: all pass. If a test binds a naive `datetime(...)` and now raises `naive datetime`, make the test's datetime aware with `tzinfo=UTC`: the production writers already are, and the test was passing a value production never produces.

**Step 6: Commit**

```bash
ruff check . && git add app/services/explore_activity.py app/routers/explore.py app/services/explore_gaps.py tests/ && git commit -m "refactor(explore): bucket weeks in Python; one week_start definition"
```

---

### Task 9: Green the whole suite

**Files:** whatever the failures name. Expect tests, not app code.

**Step 1: Run**

Run: `python3 -m pytest tests/ mcp_server/tests/ -q --ignore=tests/ats/test_golden.py 2>&1 | tail -60`

**Step 2: Fix by category, smallest change that keeps production semantics**

| Symptom | Cause | Fix |
|---|---|---|
| `StatementError … naive datetime` | a test builds `datetime(2026, …)` without tz | add `tzinfo=UTC` in the test |
| rows come back in a different order | a query with no `ORDER BY` relied on Postgres heap order | if the endpoint promises an order, add the `order_by` in the query; if the test assumed one, sort in the test |
| `SAWarning: Dialect sqlite+pysqlite does not support Decimal objects natively` | `Numeric(5, 1)` on SQLite | leave the warning; it is correct and harmless. Do NOT switch to `asdecimal=False` (callers may compare `Decimal`) |
| `no such function: …` | another Postgres function | list it in the deviation log with the file and line, then port it in Python the way Task 8 did |
| an `ilike` test on non-ASCII case | SQLAlchemy emulates ILIKE with `lower()` | accept and log |
| `test_settings_reads_env`-style assertions on `postgresql+psycopg://` | old normalization expectation | rewrite the expectation; the URL is refused now |
| `AttributeError: 'str' object has no attribute 'hex'` | a test (or app path) binds a string to a `UUIDType` column; native Postgres UUID accepted strings, SQLite's CHAR(32) path does not | tests: pass `uuid.UUID` objects. App code: none known (Task 3 sweep); if one appears, convert at the boundary and log it |
| a `>=`/`<=` filter or ordering is off by one row within the same second | SQLite stores ORM-bound datetimes as `YYYY-MM-DD HH:MM:SS.ffffff` but `server_default=func.now()` / `onupdate=func.now()` rows as `YYYY-MM-DD HH:MM:SS`; comparisons are lexicographic | make the app write every timestamp itself: in `types.py` add `def utcnow(): return datetime.now(UTC)`; codemod `server_default=func.now()` → `default=utcnow, server_default=func.now()` and `onupdate=func.now()` → `onupdate=utcnow` (keep the server default for DDL). One format on disk, microseconds preserved for imported Postgres rows. Do this in Task 9 whether or not a test fails; add a portability-test assertion that every `UTCDateTime` column with a `server_default` also has a Python `default` |

Every fix outside `tests/` gets a deviation-log line.

**Step 3: Repeat until green**

Run: `python3 -m pytest tests/ mcp_server/tests/ -q --ignore=tests/ats/test_golden.py`
Expected: `… passed` with 0 failed, 0 errors. Record the count next to Task 7's baseline in the deviation log.

**Step 4: Commit**

```bash
ruff check . && git add -A tests app && git commit -m "test: suite green on SQLite"
```

---

### Task 10: Concurrency: prove writers wait, and audit flush-before-LLM

**Files:**
- Create: `backend/tests/test_sqlite_concurrency.py`
- Read (audit only): every file `grep -ln "call_openai\|llm\." app/services/*.py` prints

**Step 1: The lock test**

```python
"""A second writer waits for the first (busy_timeout), it does not fail."""
import threading
import time

import sqlalchemy as sa

from app.db import make_engine


def test_second_writer_waits_instead_of_failing(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'c.sqlite3'}")
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")

        errors: list[Exception] = []
        first_holds_lock = threading.Event()

        def first_writer():
            with engine.begin() as conn:
                conn.exec_driver_sql("INSERT INTO t (v) VALUES ('a')")  # takes the write lock
                first_holds_lock.set()
                time.sleep(2.0)  # hold it across the second writer's attempt

        def second_writer():
            first_holds_lock.wait(5)
            try:
                with engine.begin() as conn:
                    conn.exec_driver_sql("INSERT INTO t (v) VALUES ('b')")
            except Exception as exc:  # noqa: BLE001  the assertion below reports it
                errors.append(exc)

        threads = [threading.Thread(target=first_writer), threading.Thread(target=second_writer)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)

        assert errors == []
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT count(*) FROM t")).scalar() == 2
    finally:
        engine.dispose()
```

Run: `python3 -m pytest tests/test_sqlite_concurrency.py -q` → 1 passed (takes ~2 s).

**Step 2: The audit (no code unless it finds something)**

For each file in `grep -ln "call_openai\|llm\." app/services/*.py`, find every LLM call and answer: is there a `session.flush()` or `session.commit()` on the same session **before** the call and **inside** the same transaction? A write flushed before a slow call holds SQLite's write lock for the call's duration; every other writer then waits up to 30 s and fails.

Record the table in the deviation log:

```
| file | LLM call (line) | write flushed before it? | action |
```

For `tailoring_session.tailor()` the expected answer is "no": pre-ops are applied in memory and it commits once at the end. `_cannot_confirm_holder` flushes (line ~722) but on the save path, not the tailor path.

If a file DOES flush before an LLM call: move the flush after the call when the call does not need the row's id; otherwise split into two transactions (commit the row, call the LLM, open a new transaction for the result) and note the change. That is a `how` adaptation within scope; log it.

**Step 3: Commit**

```bash
ruff check . && git add tests/test_sqlite_concurrency.py && git commit -m "test(db): second writer waits on busy_timeout"
```

---

### Task 11: The importer: CLI, boot hook, verification

**Files:**
- Create: `backend/app/tools/__init__.py` (empty)
- Create: `backend/app/tools/migrate_from_postgres.py`
- Modify: `backend/app/services/seeding.py:182-185` (`run_startup`)
- Create: `backend/tests/tools/__init__.py` (empty), `backend/tests/tools/test_migrate_from_postgres.py`
- Modify: `backend/pyproject.toml` (`[tool.pytest.ini_options]` markers) and root `pytest.ini` (markers)

**Step 1: Write the failing tests**

```python
"""app.tools.migrate_from_postgres.

The copy logic is dialect-agnostic (reflection on the source, the app's own
metadata on the target), so it is exercised here SQLite→SQLite. The one thing
only Postgres can prove — psycopg's dict/aware-datetime/Decimal values — is
covered by test_export_from_real_postgres, which CI's legacy job runs.
"""
import os
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from app.db import make_engine
from app.models.ats_score import AtsScore
from app.models.career_kb import KBEntity
from app.models.job import Job
from app.tools import migrate_from_postgres as tool

BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _fresh_schema(url: str) -> None:
    cfg = Config(os.path.join(BACKEND, "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")


def _seed(url: str) -> dict[str, int]:
    engine = make_engine(url)
    from sqlalchemy.orm import Session

    with Session(engine) as session:
        job = Job(
            raw_text="JD", raw_text_hash="h1", extracted_json={"title": "x", "n": [1, 2]},
            title="x", company="Acme", role_category="data_scientist",
            extracted_at=datetime.now(UTC),
        )
        session.add(job)
        session.flush()
        session.add(AtsScore(
            job_id=job.id, target_type="base_resume", target_id="example", phase="base",
            composite=Decimal("72.5"), subscores_json={"a": 1}, skill_table_json=[], config_version="v",
        ))
        session.add(KBEntity(kind="experience", title="Thing"))
        session.commit()
    engine.dispose()
    return {"jobs": 1, "ats_scores": 1, "kb_entities": 1}


# If a constructor above trips a NOT NULL column, copy the kwargs an existing
# test uses: `grep -n "AtsScore(\|KBEntity(" tests/test_explore_gaps.py tests/test_career_kb_router.py | head`.


def test_normalize_value_is_canonical():
    ref = uuid.uuid4()
    assert tool.normalize_value(ref) == str(ref)
    naive = datetime(2026, 9, 17, 6, 30)
    aware = datetime(2026, 9, 17, 6, 30, tzinfo=UTC)
    assert tool.normalize_value(naive) == tool.normalize_value(aware)
    assert tool.normalize_value(Decimal("72.50")) == "72.50"
    assert tool.normalize_value({"b": 1, "a": [2]}) == tool.normalize_value({"a": [2], "b": 1})


def test_copy_database_round_trips_and_verifies(tmp_path):
    src = f"sqlite:///{tmp_path / 'src.sqlite3'}"
    dst = f"sqlite:///{tmp_path / 'dst.sqlite3'}"
    _fresh_schema(src)
    expected = _seed(src)
    _fresh_schema(dst)

    report = tool.copy_database(src, dst, log=lambda *_: None)

    assert all(entry["ok"] for entry in report.values()), report
    for table, n in expected.items():
        assert report[table]["rows"] == n == report[table]["target_rows"]
    assert report["jobs"]["source_hash"] == report["jobs"]["target_hash"]


def test_main_refuses_a_non_empty_target_without_replace(tmp_path, capsys):
    src = f"sqlite:///{tmp_path / 'src.sqlite3'}"
    _fresh_schema(src)
    target = tmp_path / "dst.sqlite3"
    target.write_bytes(b"not empty")

    code = tool.main(["--source", src, "--target", f"sqlite:///{target}", "--skip-source-upgrade"])

    assert code == 2
    assert "refusing" in capsys.readouterr().out


def test_import_if_needed_is_idempotent_and_writes_the_marker(tmp_path):
    src = f"sqlite:///{tmp_path / 'src.sqlite3'}"
    dst = f"sqlite:///{tmp_path / 'dst.sqlite3'}"
    _fresh_schema(src)
    _seed(src)
    _fresh_schema(dst)
    marker = tmp_path / ".migrated-from-postgres.json"
    log: list[str] = []

    first = tool.import_if_needed(src, dst, marker, log=log.append, upgrade_source=False)
    second = tool.import_if_needed(src, dst, marker, log=log.append, upgrade_source=False)

    assert first == "imported" and second == "already-imported"
    assert marker.exists() and '"jobs"' in marker.read_text()


def test_import_if_needed_skips_a_target_that_already_has_data(tmp_path):
    src = f"sqlite:///{tmp_path / 'src.sqlite3'}"
    dst = f"sqlite:///{tmp_path / 'dst.sqlite3'}"
    _fresh_schema(src)
    _seed(src)
    _fresh_schema(dst)
    _seed(dst)
    marker = tmp_path / ".migrated-from-postgres.json"

    assert tool.import_if_needed(src, dst, marker, log=lambda *_: None, upgrade_source=False) == "target-not-empty"
    assert not marker.exists()


def test_import_if_needed_skips_an_unreachable_source(tmp_path):
    dst = f"sqlite:///{tmp_path / 'dst.sqlite3'}"
    _fresh_schema(dst)
    marker = tmp_path / ".migrated-from-postgres.json"

    # A sqlite file in a directory that does not exist: "unable to open" is the
    # same SQLAlchemyError class an unreachable Postgres raises, and this runs
    # without psycopg installed (CI's suite job has no legacy extra).
    outcome = tool.import_if_needed(
        "sqlite:////nonexistent-dir-for-this-test/none.sqlite3", dst, marker, log=lambda *_: None
    )

    assert outcome == "source-unreachable"
    assert not marker.exists()


@pytest.mark.legacy_postgres
def test_export_from_real_postgres(tmp_path):
    source = os.environ.get("LEGACY_POSTGRES_TEST_URL")
    if not source:
        pytest.skip("LEGACY_POSTGRES_TEST_URL not set (CI's legacy-postgres-export job sets it)")
    tool.upgrade_legacy_source(source)
    engine = sa.create_engine(tool.normalize_postgres_url(source), future=True)
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM ats_scores"))
        conn.execute(sa.text("DELETE FROM jobs"))
        job_id = uuid.uuid4()
        conn.execute(
            sa.text(
                "INSERT INTO jobs (id, raw_text, raw_text_hash, extracted_json, title, company, "
                "role_category, extracted_at, created_at, updated_at) VALUES (:id, 'JD', 'h1', "
                "'{\"title\": \"x\"}'::jsonb, 'x', 'Acme', 'data_scientist', now(), now(), now())"
            ),
            {"id": job_id},
        )
    engine.dispose()
    dst = f"sqlite:///{tmp_path / 'dst.sqlite3'}"
    _fresh_schema(dst)

    report = tool.copy_database(source, dst, log=lambda *_: None)

    assert report["jobs"]["ok"] and report["jobs"]["rows"] == 1
```

(The raw INSERT names the `jobs` columns the legacy schema has; check `legacy_postgres/migrations/versions` for `jobs` if it 500s on a NOT NULL column and add that column. Log it.)

Register the marker: in `backend/pyproject.toml` under `[tool.pytest.ini_options]` add `markers = ["legacy_postgres: needs LEGACY_POSTGRES_TEST_URL; run by CI's legacy-postgres-export job"]` (if a `markers` list exists, append to it), and append the same line to the `markers =` block in the root `pytest.ini`.

**Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/tools -q`
Expected: `ModuleNotFoundError: No module named 'app.tools'`.

**Step 3: Write `app/tools/migrate_from_postgres.py`**

```python
"""Move a compose-era Postgres database into the SQLite file.

ONE release only (SYSTEM.md §13 `postgres-to-sqlite`); delete with that row.

Two entry points:
- `import_if_needed(...)` — called by seeding.run_startup() at boot. Idempotent
  (a marker file records success), atomic (one transaction on the target),
  verified (row counts and a per-table content hash, source vs target).
- `python -m app.tools.migrate_from_postgres` — the same thing by hand.

The source is read by reflection (the legacy schema at its head); the target
is written through the app's own metadata, so every value passes through
app.models.types exactly as the app would write it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.types import TypeDecorator

from app.config import normalize_postgres_url, settings
from app.db import Base, make_engine, sqlite_path
import app.models  # noqa: F401  registers every table on Base.metadata

BACKEND_ROOT = Path(__file__).resolve().parents[2]
LEGACY_INI = BACKEND_ROOT / "legacy_postgres" / "alembic.ini"
NEW_INI = BACKEND_ROOT / "alembic.ini"
MARKER_NAME = ".migrated-from-postgres.json"
BATCH = 1000
# Tables whose emptiness means "this target has never held user data".
_USER_DATA_TABLES = ("jobs", "applications", "base_resumes", "kb_entities")

Log = Callable[[str], None]


class ExportError(RuntimeError):
    pass


def normalize_value(value):
    """One canonical form per value so a hash means the same on both sides:
    psycopg hands back dicts, aware datetimes and Decimals; SQLite hands back
    the same through app.models.types."""
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        aware = value if value.tzinfo else value.replace(tzinfo=UTC)
        return aware.astimezone(UTC).isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=normalize_value)
    if isinstance(value, bytes):
        return value.hex()
    return value


def table_hash(rows: list[dict], column_names: list[str]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        line = json.dumps(
            [normalize_value(row[name]) for name in column_names],
            separators=(",", ":"),
            default=str,
        )
        digest.update(line.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _pk_names(table: sa.Table) -> list[str]:
    return [column.name for column in table.primary_key.columns]


def read_rows(conn: sa.Connection, table: sa.Table) -> list[dict]:
    # Sorted in Python by the normalized primary key: a text key sorts by
    # collation in Postgres and by bytes in SQLite, and the hash needs one order.
    rows = [dict(row._mapping) for row in conn.execute(sa.select(table))]
    keys = _pk_names(table)
    rows.sort(key=lambda row: tuple(str(normalize_value(row[key])) for key in keys))
    return rows


def _coerce_for_target(table: sa.Table, row: dict) -> dict:
    """Shape a reflected source row the way the app's types expect it. psycopg
    already hands back uuid.UUID and aware datetimes; a SQLite source (the
    unit tests) hands back 32-hex strings and naive datetimes. Hashing runs
    on the coerced row, so both sides are compared in one representation."""
    out = {}
    for column in table.columns:
        value = row[column.name]
        if value is not None:
            if isinstance(column.type, sa.Uuid) and isinstance(value, str):
                value = uuid.UUID(value)
            elif (
                isinstance(column.type, TypeDecorator)
                and isinstance(value, datetime)
                and value.tzinfo is None
            ):
                value = value.replace(tzinfo=UTC)
        out[column.name] = value
    return out


def copy_database(source_url: str, target_url: str, *, log: Log = print) -> dict[str, dict]:
    """Copy every table in dependency order, in ONE target transaction, then
    verify. Returns {table: {rows, source_hash, target_rows, target_hash, ok}}."""
    source = sa.create_engine(source_url, future=True)
    target = make_engine(target_url)
    reflected = sa.MetaData()
    report: dict[str, dict] = {}
    try:
        with source.connect() as sconn, target.begin() as tconn:
            # Foreign keys are checked at COMMIT instead of per statement, so a
            # self-referential table (resume_versions.parent_version_id) copies
            # in any row order. Violations still fail the whole transaction.
            tconn.exec_driver_sql("PRAGMA defer_foreign_keys=ON")
            for table in Base.metadata.sorted_tables:
                src_table = sa.Table(table.name, reflected, autoload_with=sconn)
                columns = [column.name for column in table.columns]
                missing = [name for name in columns if name not in src_table.c]
                if missing:
                    raise ExportError(
                        f"{table.name}: source lacks {missing}; the source must be at the "
                        "legacy chain's head (run without --skip-source-upgrade)"
                    )
                rows = [_coerce_for_target(table, row) for row in read_rows(sconn, src_table)]
                for start in range(0, len(rows), BATCH):
                    chunk = rows[start:start + BATCH]
                    tconn.execute(table.insert(), [{name: row[name] for name in columns} for row in chunk])
                report[table.name] = {"rows": len(rows), "source_hash": table_hash(rows, columns)}
                log(f"  {table.name}: {len(rows)} rows")
        with target.connect() as tconn:
            for table in Base.metadata.sorted_tables:
                columns = [column.name for column in table.columns]
                rows = read_rows(tconn, table)
                entry = report[table.name]
                entry["target_rows"] = len(rows)
                entry["target_hash"] = table_hash(rows, columns)
                entry["ok"] = (
                    entry["rows"] == entry["target_rows"]
                    and entry["source_hash"] == entry["target_hash"]
                )
    finally:
        source.dispose()
        target.dispose()
    return report


def upgrade_legacy_source(source_url: str) -> None:
    """Bring a compose-era database to the legacy chain's head. A user may have
    skipped releases; the chain still knows how to get there."""
    try:
        import psycopg  # noqa: F401
    except ModuleNotFoundError as exc:
        raise ExportError(
            "psycopg is not installed; install the legacy-postgres extra: "
            "pip install -e '.[legacy-postgres]'"
        ) from exc
    cfg = Config(str(LEGACY_INI))
    cfg.set_main_option("sqlalchemy.url", normalize_postgres_url(source_url))
    command.upgrade(cfg, "head")


def create_target_schema(target_url: str) -> None:
    cfg = Config(str(NEW_INI))
    cfg.set_main_option("sqlalchemy.url", target_url)
    command.upgrade(cfg, "head")


def _source_has_data(source_url: str) -> bool | None:
    """True/False, or None when the source cannot be reached."""
    try:
        engine = sa.create_engine(source_url, future=True)
    except ModuleNotFoundError as exc:  # the postgresql dialect needs psycopg
        raise ExportError(
            "psycopg is not installed; install the legacy-postgres extra: "
            "pip install -e '.[legacy-postgres]'"
        ) from exc
    try:
        with engine.connect() as conn:
            if not sa.inspect(conn).has_table("alembic_version"):
                return False
            for name in _USER_DATA_TABLES:
                if sa.inspect(conn).has_table(name):
                    if conn.execute(sa.text(f"SELECT count(*) FROM {name}")).scalar():
                        return True
            return False
    except sa.exc.SQLAlchemyError:
        return None
    finally:
        engine.dispose()


def _target_is_empty(target_url: str) -> bool:
    engine = make_engine(target_url)
    try:
        with engine.connect() as conn:
            for name in _USER_DATA_TABLES:
                if conn.execute(sa.text(f"SELECT count(*) FROM {name}")).scalar():
                    return False
        return True
    finally:
        engine.dispose()


def import_if_needed(
    source_url: str,
    target_url: str,
    marker: Path,
    *,
    log: Log = print,
    upgrade_source: bool = True,
) -> str:
    """Boot-time entry point. Returns one of: already-imported, no-source,
    source-unreachable, source-empty, target-not-empty, imported. Raises
    ExportError only on a verification mismatch (the transaction has already
    rolled back; the target is left as it was)."""
    if marker.exists():
        return "already-imported"
    if not source_url:
        return "no-source"
    source_url = normalize_postgres_url(source_url)
    has_data = _source_has_data(source_url)
    if has_data is None:
        log("legacy Postgres source is unreachable; will retry at the next boot")
        return "source-unreachable"
    if not has_data:
        _write_marker(marker, {"outcome": "source-empty"})
        return "source-empty"
    if not _target_is_empty(target_url):
        log("SQLite file already holds data and no import marker exists; leaving both alone")
        return "target-not-empty"
    if upgrade_source:
        log("bringing the Postgres source to the legacy chain's head")
        upgrade_legacy_source(source_url)
    log("importing the Postgres database into the SQLite file")
    report = copy_database(source_url, target_url, log=log)
    bad = sorted(name for name, entry in report.items() if not entry["ok"])
    if bad:
        raise ExportError(f"import verification failed for {bad}; nothing was kept")
    _write_marker(marker, {"outcome": "imported", "tables": report})
    total = sum(entry["rows"] for entry in report.values())
    log(f"imported {total} rows from Postgres; the pgdata volume is no longer read")
    return "imported"


def _write_marker(marker: Path, payload: dict) -> None:
    marker.parent.mkdir(parents=True, exist_ok=True)
    payload = {"at": datetime.now(UTC).isoformat(), **payload}
    marker.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", default=os.environ.get("LEGACY_DATABASE_URL"), help="postgresql://… (default: $LEGACY_DATABASE_URL)")
    parser.add_argument("--target", default=settings.database_url, help="sqlite:///… (default: the app's database_url)")
    parser.add_argument("--replace", action="store_true", help="move a non-empty target aside first")
    parser.add_argument("--skip-source-upgrade", action="store_true", help="do not run the legacy chain on the source")
    args = parser.parse_args(argv)
    if not args.source:
        parser.error("--source or LEGACY_DATABASE_URL is required")
    path = sqlite_path(args.target)
    if path is None:
        parser.error("--target must be a sqlite:/// file URL")

    if path.exists() and path.stat().st_size > 0:
        if not args.replace:
            print(f"refusing: {path} exists and is not empty (pass --replace to move it aside)")
            return 2
        aside = path.with_name(f"{path.name}.replaced-{datetime.now(UTC):%Y%m%dT%H%M%S}")
        path.rename(aside)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{path}{suffix}")
            if sidecar.exists():
                sidecar.unlink()
        print(f"moved {path} -> {aside}")

    try:
        if not args.skip_source_upgrade:
            print("upgrading the source through the legacy migration chain")
            upgrade_legacy_source(args.source)
        print(f"creating the SQLite schema at {path}")
        create_target_schema(args.target)
        print("copying tables")
        report = copy_database(normalize_postgres_url(args.source), args.target)
    except ExportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    width = max(len(name) for name in report)
    for name, entry in report.items():
        flag = "ok" if entry["ok"] else "MISMATCH"
        print(f"{name:<{width}}  {entry['rows']:>7} -> {entry['target_rows']:>7}  {flag}")
    if all(entry["ok"] for entry in report.values()):
        _write_marker(path.parent / MARKER_NAME, {"outcome": "imported", "tables": report})
        print("verified: every table matches by count and content hash")
        return 0
    print("verification FAILED; the target was left in place for inspection", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

**Step 4: The boot hook in `seeding.py`**

Replace `run_startup`:

```python
def run_startup() -> None:
    run_migrations()
    _import_legacy_postgres()
    with SessionLocal() as session:
        seed_startup_data(session)


def _import_legacy_postgres() -> None:
    """ONE release only (SYSTEM.md §13 postgres-to-sqlite). Runs before any
    seed so a compose-era database lands in an empty file, never beside demo
    rows. Unreachable source = retry next boot; a verification failure is
    logged loudly and the app still boots (the transaction rolled back)."""
    if not settings.legacy_database_url:
        return
    from app.tools import migrate_from_postgres as tool

    marker = Path(settings.data_dir) / tool.MARKER_NAME
    try:
        outcome = tool.import_if_needed(
            settings.legacy_database_url, settings.database_url, marker, log=logger.info
        )
    except tool.ExportError:
        logger.exception("legacy Postgres import failed verification; booting with the empty file")
        return
    if outcome == "imported":
        logger.warning(
            "Imported your Postgres database into %s. The old Docker volume is no longer "
            "read; remove it when satisfied (README: Updating).",
            settings.database_url,
        )
```

(`Path` and `settings` are already imported in `seeding.py`; check the import block.)

**Step 5: Run the tests**

Run: `python3 -m pytest tests/tools -q`
Expected: 6 passed, 1 skipped (the real-Postgres one). Then the full suite once more: `python3 -m pytest tests/ mcp_server/tests/ -q --ignore=tests/ats/test_golden.py` → green.

**Step 6: Commit**

```bash
ruff check . && git add app/tools app/services/seeding.py tests/tools pyproject.toml ../pytest.ini && git commit -m "feat(db): import a legacy Postgres database at first boot, verified"
```

---

### Task 12: The backup tool

**Files:**
- Create: `backend/app/tools/backup_db.py`
- Create: `backend/tests/tools/test_backup_db.py`

**Step 1: Write the failing test**

```python
import gzip
import sqlite3

from app.tools import backup_db


def _db_with_rows(path):
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        conn.executemany("INSERT INTO t (v) VALUES (?)", [("a",), ("b",), ("c",)])
    return path


def test_backup_writes_a_gzipped_consistent_snapshot(tmp_path):
    src = _db_with_rows(tmp_path / "live.sqlite3")
    out = tmp_path / "backup.sqlite3.gz"

    assert backup_db.main(["--source", str(src), "--out", str(out)]) == 0

    restored = tmp_path / "restored.sqlite3"
    restored.write_bytes(gzip.decompress(out.read_bytes()))
    with sqlite3.connect(restored) as conn:
        assert conn.execute("SELECT count(*) FROM t").fetchone()[0] == 3
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_backup_streams_raw_bytes_to_stdout(tmp_path, capsysbinary):
    src = _db_with_rows(tmp_path / "live.sqlite3")

    assert backup_db.main(["--source", str(src), "--stdout"]) == 0

    raw = capsysbinary.readouterr().out
    assert raw.startswith(b"SQLite format 3\x00")
```

Run: `python3 -m pytest tests/tools/test_backup_db.py -q` → `ImportError`.

**Step 2: Write `app/tools/backup_db.py`**

```python
"""SQLite online backup, for scripts/update.sh and by hand.

Never copy a live database file: pages not yet checkpointed live in the -wal
sidecar, and a plain cp takes a torn snapshot. sqlite3's backup API copies a
consistent image while the app keeps running.

    python -m app.tools.backup_db --out backups/db-<ts>.sqlite3.gz
    python -m app.tools.backup_db --stdout | gzip > backups/db-<ts>.sqlite3.gz
"""
from __future__ import annotations

import argparse
import gzip
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

from app.config import settings
from app.db import sqlite_path


def snapshot(source: Path, destination: Path) -> None:
    with sqlite3.connect(source) as live, sqlite3.connect(destination) as copy:
        live.backup(copy)
    with sqlite3.connect(destination) as check:
        verdict = check.execute("PRAGMA integrity_check").fetchone()[0]
    if verdict != "ok":
        raise RuntimeError(f"snapshot failed integrity_check: {verdict}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", default=None, help="database file (default: the app's database_url)")
    output = parser.add_mutually_exclusive_group(required=True)
    output.add_argument("--out", help="write a gzipped snapshot here")
    output.add_argument("--stdout", action="store_true", help="write the raw snapshot bytes to stdout")
    args = parser.parse_args(argv)

    source = Path(args.source) if args.source else sqlite_path(settings.database_url)
    if source is None or not source.exists():
        print(f"error: no database file at {source}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        image = Path(tmp) / "snapshot.sqlite3"
        snapshot(source, image)
        if args.stdout:
            with image.open("rb") as handle:
                shutil.copyfileobj(handle, sys.stdout.buffer)
            sys.stdout.buffer.flush()
        else:
            out = Path(args.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            with image.open("rb") as handle, gzip.open(out, "wb") as packed:
                shutil.copyfileobj(handle, packed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 3: Run and commit**

Run: `python3 -m pytest tests/tools/test_backup_db.py -q` → 2 passed.

```bash
ruff check . && git add app/tools/backup_db.py tests/tools/test_backup_db.py && git commit -m "feat(tools): online SQLite backup for update.sh"
```

---

### Task 13: Dependencies and the image

**Files:**
- Modify: `backend/pyproject.toml:18` (remove `psycopg[binary]` from core), `:38-62` (new extra)
- Modify: `backend/Dockerfile` (the `pip install … -e ".[dev]"` line)
- Regenerate: `backend/requirements.lock`

**Step 1: pyproject**

Delete the line `    "psycopg[binary]>=3.2",` from `dependencies`. Add after the `mcp = [...]` extra:

```toml
# ONE release only (SYSTEM.md §13 postgres-to-sqlite): the importer that moves
# a compose-era Postgres database into the SQLite file. Delete with it.
legacy-postgres = [
    "psycopg[binary]>=3.2",
]
```

**Step 2: Dockerfile**

Change `pip install --no-cache-dir --no-deps -e ".[dev]"` to `pip install --no-cache-dir --no-deps -e ".[dev,legacy-postgres]"` and add above it: `# legacy-postgres is a one-release extra (SYSTEM.md §13); drop it with that row.`

**Step 3: Regenerate the lock on Linux** (the Dockerfile's own recipe, plus the new extra), from the repo root:

```bash
docker run --rm -v "$PWD/backend:/w" -w /w python:3.12-slim \
  sh -c "pip install pip-tools && pip-compile --extra dev --extra mcp --extra legacy-postgres \
         --generate-hashes --output-file requirements.lock pyproject.toml"
```

Expected: `psycopg` and `psycopg-binary` still pinned (they were core before), nothing else materially moves. `git diff --stat backend/requirements.lock` should be small.

**Step 4: Prove the editable install without the extra still imports**

```bash
python3 -c "import app.main, app.tools.migrate_from_postgres; print('ok')"
```

Expected: `ok` (the importer imports psycopg lazily, inside `upgrade_legacy_source`).

**Step 5: Commit**

```bash
git add pyproject.toml Dockerfile requirements.lock && git commit -m "build: psycopg becomes the one-release legacy-postgres extra"
```

---

### Task 14: Compose, env template, ignore rules

**Files:**
- Modify: `docker-compose.yml:9-28` (postgres), `:48-52` (backend depends_on/env), backend `volumes:` block
- Modify: `.env.example:1-17`, the `POSTGRES_*` block
- Modify: `.gitignore` (after the `kb_documents` rules)
- Create: `data/.gitkeep`

**Step 1: `docker-compose.yml`**

Above `  postgres:` add:

```yaml
  # ONE release only (SYSTEM.md §13 postgres-to-sqlite). The backend imports
  # this database into ./data/maestro_cs.sqlite3 at its first boot and never
  # reads it again; the next release deletes this service, the pgdata volume
  # below, and the POSTGRES_* keys. Remove the volume yourself once satisfied:
  #   docker volume rm maestro-career-studio_pgdata
```

In `backend`: keep `depends_on: postgres: condition: service_healthy` for this release (the import needs it up at boot). Replace the `DATABASE_URL:` line with:

```yaml
      # The runtime database is the SQLite file under /app/data (bind-mounted
      # below); DATABASE_URL is deliberately NOT set. This is the compose-era
      # database the first boot imports, one release only (see the postgres
      # service above).
      LEGACY_DATABASE_URL: postgresql://${POSTGRES_USER:-app}:${POSTGRES_PASSWORD:-app}@postgres:5432/${POSTGRES_DB:-maestro_cs}
```

In the backend `volumes:` list add, first:

```yaml
      # The database: maestro_cs.sqlite3 plus its -wal/-shm sidecars. PII like
      # every other mount here. Never open it from the host while the backend
      # runs — WAL needs shared memory the Docker Desktop mount does not
      # promise; stop the stack or read a backups/ snapshot instead.
      - ./data:/app/data
```

**Step 2: `.env.example`**

Line 2: `# HOST PORTS. All three bind to 127.0.0.1 only` → `# HOST PORTS. Every one binds to 127.0.0.1 only`. Above `POSTGRES_HOST_PORT=55432` add `# LEGACY, one release: only the first-boot import reads Postgres now.` Above the `POSTGRES_USER=app` block add:

```
# LEGACY, one release (SYSTEM.md §13 postgres-to-sqlite): credentials for the
# compose-era database the first boot imports into data/maestro_cs.sqlite3.
# Leave them as they were on your install so the import can read it.
```

**Step 3: `.gitignore` and the placeholder**

After the `kb_documents` pair add:

```
/data/*
!/data/.gitkeep
```

`touch data/.gitkeep`.

**Step 4: Validate the compose file parses**

Run from the repo root: `docker compose config --quiet && echo ok`
Expected: `ok`.

**Step 5: Commit**

```bash
git add docker-compose.yml .env.example .gitignore data/.gitkeep && git commit -m "compose: SQLite under ./data; Postgres stays one release for the import"
```

---

### Task 15: `scripts/update.sh`: the right backup, and the volume advice

**Files:**
- Modify: `scripts/update.sh:178-186` (`print_restore`), `:208-225` (keep `wait_postgres`), `:264-296` (backup block), `:352-366` (post-update notes), `do_check`

**Step 1: Helpers** (add after `wait_postgres`)

```bash
SQLITE_FILE="$REPO/data/maestro_cs.sqlite3"
IMPORT_MARKER="$REPO/data/.migrated-from-postgres.json"

pgdata_volume() {
  # The compose file pins the project name; COMPOSE_PROJECT_NAME still overrides
  # it, the same way it does for compose.
  local project="${COMPOSE_PROJECT_NAME:-maestro-career-studio}"
  docker volume ls --format '{{.Name}}' 2>/dev/null | grep -Fx "${project}_pgdata" || true
}

# True while the database that matters still lives in Postgres: no import
# marker yet, and a pgdata volume to import from.
legacy_postgres_is_live() {
  [ ! -f "$IMPORT_MARKER" ] && [ -n "$(pgdata_volume)" ]
}

backup_sqlite() {
  local dump="$1"
  note "backing up the SQLite database to $dump"
  # Through the app's own tool (online backup): a plain cp of a live database
  # is a torn snapshot, WAL pages sit in the -wal sidecar until a checkpoint.
  if ! compose run --rm -T --no-deps backend python -m app.tools.backup_db --stdout | gzip > "$dump"; then
    rm -f "$dump"
    die "sqlite backup failed"
  fi
}
```

**Step 2: The backup block in `do_update`** (replace from `note "starting postgres so there is a database to back up"` through `ok "backup written …"`)

```bash
  if legacy_postgres_is_live; then
    note "starting postgres so there is a database to back up"
    compose up -d postgres
    wait_postgres "$user" "$db"
    dump="$REPO/backups/db-${ts}-${version}.sql.gz"
    note "backing up database to $dump"
    # --clean --if-exists so the printed restore command works into a database
    # that already has the schema (a plain dump errors on every duplicate table).
    if ! compose exec -T postgres pg_dump --clean --if-exists -U "$user" "$db" | gzip > "$dump"; then
      rm -f "$dump"
      die "pg_dump failed"
    fi
  else
    dump="$REPO/backups/db-${ts}-${version}.sqlite3.gz"
    backup_sqlite "$dump"
  fi
  if [ ! -s "$dump" ]; then
    rm -f "$dump"
    die "backup is empty — gzip would otherwise hide a failed dump"
  fi
  gzip -t "$dump" || die "backup is not valid gzip"
  ok "backup written ($(wc -c < "$dump" | tr -d ' ') bytes)"
```

**Step 3: `print_restore`** takes the dump path and branches on its suffix:

```bash
print_restore() {
  local dump="$1"
  local user="$2"
  local db="$3"
  case "$dump" in
    *.sqlite3.gz)
      note "restore this snapshot (stack STOPPED):  docker compose --project-directory \"$REPO\" down && gunzip -c $dump > $SQLITE_FILE && rm -f $SQLITE_FILE-wal $SQLITE_FILE-shm"
      ;;
    *)
      note "restore this dump:  gunzip -c $dump | docker compose --project-directory \"$REPO\" exec -T postgres psql -U $user $db"
      ;;
  esac
  note "Rollback is one recipe: old git ref + old images + this backup. Never restore a backup into a newer schema."
  note "This backup guards the migration. base_resumes/, applications/, settings/, kb_documents/ are on disk and no step here touches them."
}
```

**Step 4: After `ok "update complete"`** add:

```bash
  if [ -f "$IMPORT_MARKER" ] && [ -n "$(pgdata_volume)" ]; then
    printf '\n'
    note "Your database now lives in data/maestro_cs.sqlite3 (imported from Postgres, verified)."
    note "The old Postgres volume is no longer read. Once you are satisfied, remove it:"
    note "  docker volume rm $(pgdata_volume)"
  fi
```

**Step 5: `do_check`** after `probe_backend "$port"` add:

```bash
  if legacy_postgres_is_live; then
    note "database: Postgres (legacy); the next update imports it into data/maestro_cs.sqlite3"
  elif [ -s "$SQLITE_FILE" ]; then
    ok "database: data/maestro_cs.sqlite3"
  else
    note "database: not created yet (first boot creates it)"
  fi
```

**Step 6: Shell-check and commit**

```bash
bash -n scripts/update.sh && (command -v shellcheck >/dev/null && shellcheck scripts/update.sh || true)
git add scripts/update.sh && git commit -m "update.sh: SQLite-aware backup, restore recipe, and volume advice"
```

---

### Task 16: CI

**Files:**
- Modify: `.github/workflows/ci.yml:13-26` (delete the `services:` block of the `backend` job), add a job

**Step 1: Delete the Postgres service from the `backend` job.** The `Run backend and MCP test suites` step is unchanged; the suite creates its own file.

**Step 2: Add the one-release job** after `backend`:

```yaml
  legacy-postgres-export:
    name: Legacy Postgres import (one release; SYSTEM.md §13 postgres-to-sqlite)
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: app
          POSTGRES_PASSWORD: app
          POSTGRES_DB: maestro_cs_legacy
        ports:
          - 55432:5432
        options: >-
          --health-cmd="pg_isready -U app -d maestro_cs_legacy"
          --health-interval=5s
          --health-timeout=5s
          --health-retries=5
    steps:
      - name: Checkout repository
        uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
      - name: Setup Python 3.12
        uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5
        with:
          python-version: "3.12"
      - name: Install with the legacy extra
        run: |
          python -m pip install --upgrade pip
          cd backend && pip install -e ".[dev,legacy-postgres]"
      - name: Import from a real Postgres and verify
        run: |
          cd backend
          LEGACY_POSTGRES_TEST_URL=postgresql://app:app@127.0.0.1:55432/maestro_cs_legacy \
            pytest tests/tools/test_migrate_from_postgres.py -q -m legacy_postgres
```

**Step 3: Commit**

```bash
git add .github/workflows/ci.yml && git commit -m "ci: no database service for the suite; one-release legacy import job"
```

---

### Task 17: SYSTEM.md, its enforcement pin, the ledger mirror

**Files:**
- Modify: `SYSTEM.md` §2 (lines ~69–104), §3 (line 121), §6 (append before `## 7.`), §9 (lines 649–668, 691), §12 (append), §13 (append a row)
- Modify: `.system_md_enforcement.json`
- Modify: `.slopledger.json`

Rewrite in place; no dated prose outside §12/§13.

**§2** — replace the `migrations/` and `tests/` lines and add three:

```
    tools/             operator tools, `python -m app.tools.<name>`: migrate_from_postgres (one release, §13), backup_db
  migrations/          alembic: ONE SQLite baseline (§12 for the revision-id gotcha)
  legacy_postgres/     the pre-SQLite chain + its alembic.ini; read ONLY by app/tools/migrate_from_postgres (§13)
  tests/               pytest on a throwaway SQLite file, no service; mcp_server/tests/ uses respx (no DB)
…
data/                  the database: maestro_cs.sqlite3 + -wal/-shm sidecars (bind-mounted, PII)
```

**§3** — line 121–122 becomes:

```
`data/maestro_cs.sqlite3` (SQLite, WAL) holds all state except resume file data
(`base_resumes/<slug>.json` on disk — DB `base_resumes` row + file must both
exist) and rendered artifacts.
```

**§6** — append before `## 7. Agent surfaces`:

```
- **Column types come from ONE module.** `{#inv-single-dialect}` SQLite is the
  only runtime database. `app/models/types.py` (`JSONDoc`, `UUIDType`,
  `UTCDateTime`) is the only place a column type is chosen, and nothing under
  `app/` imports `sqlalchemy.dialects`. `UTCDateTime` is the whole timezone
  story: aware in Python, naive UTC on disk, and a NAIVE bind raises. Pinned
  by `tests/test_db_portability.py`.
```

**§9** — replace the Postgres bullet (649–654) with:

```
- **The database is a file.** `data/maestro_cs.sqlite3` (compose bind-mounts
  `./data` to `/app/data`), WAL mode, pragmas set per connection by
  `app/db.make_engine` — the ONE engine constructor (app, tests, tools). Never
  open the container's file from the host while the backend runs: WAL needs
  shared memory the Docker Desktop mount does not promise; stop the stack or
  read a `backups/` snapshot. `SQLITE_JOURNAL_MODE=DELETE` is the escape hatch
  for a filesystem WAL cannot trust. Postgres survives one release, for the
  first-boot import only (§13 `postgres-to-sqlite`).
```

In the calibration bullet replace `DATABASE_URL=…55432/maestro_cs` with `DATABASE_URL=sqlite:///<main-checkout>/data/maestro_cs.sqlite3` and add `(stack stopped)`. Replace the Backend-tests bullet (668–670) with:

```
- Backend tests: `pytest tests/ mcp_server/tests/ -q` from `backend/` (CI's
  command; a bare `tests/` silently skips the MCP suite). No service: conftest
  creates a throwaway SQLite file per process under the temp dir.
  `TEST_DATABASE_URL` may name another sqlite file, never one under `data/`.
```

In the two-dependency-sources bullet add one sentence: `legacy-postgres` is a one-release extra (§13).

**§12** — append (fill the date with the landing date):

```
- YYYY-MM-DD: SQLite forgets every PRAGMA when a connection closes and ships
  `foreign_keys=OFF` → 21 `ondelete=` cascades silently stop → every engine
  goes through `app.db.make_engine`; never `create_engine` in app code.
- YYYY-MM-DD: Alembic autogenerate renders a TypeDecorator as `sa.<Name>()`,
  which does not exist → replace with the impl type by hand in the revision.
  Comparison needs no hook: Alembic ≥1.4 compares compiled DDL, so
  `compare_type=True` already sees `UTCDateTime` as the `DATETIME` it made.
```

**§13** — append the row:

```
| `postgres-to-sqlite` | compose `postgres` service + `legacy_postgres/` chain → `data/maestro_cs.sqlite3` + one baseline | new-is-default | The next release ships. Then delete: `legacy_postgres/`, `app/tools/migrate_from_postgres.py`, `seeding._import_legacy_postgres`, `legacy_database_url`, `normalize_postgres_url`, the `legacy-postgres` extra and CI job, the compose `postgres` service + `pgdata` volume + `LEGACY_DATABASE_URL`, every `POSTGRES_*` env key, `update.sh`'s pg_dump branch. `update.sh --check` must then say "install <this release> first" when a `pgdata` volume exists without `data/.migrated-from-postgres.json`. | medium |
```

**`.system_md_enforcement.json`** — add to `invariants`:

```json
    "inv-single-dialect": [
      {"path": "backend/tests/test_db_portability.py", "symbol": "test_no_dialect_imports_outside_types_module"},
      {"path": "backend/app/models/types.py", "symbol": "UTCDateTime"}
    ],
```

**`.slopledger.json`** — add to `rows`:

```json
    {
      "id": "postgres-to-sqlite",
      "status": "new-is-default",
      "hand_check": "Release event: cut when the release AFTER the SQLite one ships. SYSTEM.md §13 lists every file to delete."
    }
```

**Run the gate**

```bash
python3 scripts/check_system_md.py
```

Expected: `check_system_md: OK …`. If a section is over its line budget, shorten the prose you just added (or the bullets it replaced) inside that section; do not re-baseline for this change.

**Commit**

```bash
git add SYSTEM.md .system_md_enforcement.json .slopledger.json && git commit -m "docs(SYSTEM): SQLite is the database; inv-single-dialect; postgres-to-sqlite ledger row"
```

---

### Task 18: User-facing docs and the changelog

**Files:** `README.md`, `CONTRIBUTING.md`, `docs/GETTING_STARTED.md`, `docs/RELEASING.md`, `SECURITY.md`, `KNOWN_ISSUES.md`, `CHANGELOG.md`, `backend/scripts/ats_snapshot.py:4`, `backend/scripts/ats_calibration.py:8-11`, `backend/scripts/apply_template_sources.py:5-6`

Find every line with `grep -n -i "postgres\|55432\|pg_dump" <file>` and rewrite it. The substance for each:

- **README.md**
  - line 170: drop `PostgreSQL ~170 MB compressed` from the download estimate; note the Postgres image is pulled one more release for the import.
  - lines 309–313 (first boot): `1. Create data/maestro_cs.sqlite3 and run migrations. (Updating from an earlier release: import your Postgres database into it, verified row for row.) 2. Seed … 3. Serve …`.
  - lines 348–380 (manual update): step 1 becomes `docker compose run --rm -T --no-deps backend python -m app.tools.backup_db --stdout | gzip > backups/db-manual.sqlite3.gz`; delete the `-U app … POSTGRES_USER` paragraph.
  - lines 396–425: "Postgres lives in a named Docker volume …" becomes "the database is `data/maestro_cs.sqlite3`, git-ignored like the other data directories; `down -v` no longer touches it". Rollback recipe: `gunzip -c backups/db-<…>.sqlite3.gz > data/maestro_cs.sqlite3` with the stack stopped, then remove `-wal`/`-shm`.
  - line 899: `(postgres, backend, frontend)` → `(backend, frontend; postgres one more release for the import)`.
  - lines 1000–1003: two host ports; delete the "Postgres data looks wrong" entry, add: **"The app came up empty after updating"** → the import needs the old `postgres` service reachable at first boot; check `docker compose logs backend | grep -i legacy`, keep `POSTGRES_*` in `.env` as they were, and rerun `docker compose up -d`. Nothing was deleted.
  - Add one troubleshooting entry: **"database is locked"** → another process holds the file (a host tool opened it while the stack ran); stop it, or set `SQLITE_JOURNAL_MODE=DELETE` if the mount cannot do WAL.
- **CONTRIBUTING.md** lines 130–145, 200–208: stack is `FastAPI, Next.js 16, SQLite`; delete the Database Setup section; testing needs no service and is per-process (the "check for active pytest" warning goes).
- **docs/GETTING_STARTED.md** 191–193, 199–202: first boot creates the file; the table row `only postgres reports healthy` → `the backend reports healthy once migrations finish`. Section "Starting over" (206–233): the database is now `data/maestro_cs.sqlite3` inside the folder, so deleting the folder DOES delete it (the opposite of before); `docker compose down -v` removes only the legacy volume; a clean slate is `docker compose down && rm -rf data/*`. Keep the `.gitkeep`.
- **docs/RELEASING.md** line 42 (project-name paragraph): the volume consequence applies only until the import lands. Step 8: add "on a scratch clone at the previous tag WITH data in Postgres, run `./scripts/update.sh`, then confirm `data/.migrated-from-postgres.json` exists, the tracker shows the old applications, and a PDF renders".
- **SECURITY.md** 189–191: `… plus \`.env\` and \`data/\` (the SQLite database with its -wal/-shm sidecars; file mode 0600)`.
- **KNOWN_ISSUES.md** 142–146: the database half of a backup is now one file (`backup_db`), the directories are the other half; the bundle command is still open.
- **CHANGELOG.md** under Unreleased:
  ```
  ### Breaking changes
  - The database is now `data/maestro_cs.sqlite3`. Existing installs are
    imported from Postgres automatically at the first boot of this release
    (verified by row count and content hash; the old volume is left in
    place). Keep your `POSTGRES_*` values in `.env` until the import has
    run; `./scripts/update.sh --check` reports which database is live. The
    next release deletes the `postgres` service entirely: install this one
    first.
  ```
- **backend/scripts/*.py** docstrings: `DATABASE_URL=sqlite:////absolute/path/to/data/maestro_cs.sqlite3` (stack stopped, or a `backups/` snapshot).

Run `python3 scripts/check_system_md.py` again (it reads the reference tier too), then:

```bash
git add README.md CONTRIBUTING.md docs SECURITY.md KNOWN_ISSUES.md CHANGELOG.md backend/scripts && git commit -m "docs: the database is a file"
```

---

### Task 19: Verification gates (design §6)

Run every one; paste results into the deviation log's **Gate results** table.

1. **Suite**, from `backend/`: `python3 -m pytest tests/ mcp_server/tests/ -q --ignore=tests/ats/test_golden.py` → 0 failed.
2. **Lint**: `ruff check .` → clean.
3. **Docs gate**, repo root: `python3 scripts/check_system_md.py` → OK. `python3 scripts/check_mcpb_bundle.py` → OK (untouched).
4. **Calibration** (maintainer machine, main checkout):
   - Before the port, on Postgres: `cd backend && DATABASE_URL=postgresql://app:app@127.0.0.1:55432/maestro_cs BASE_RESUMES_DIR=<main>/base_resumes python -m scripts.ats_calibration snapshot /tmp/before.json` (run this on the commit BEFORE Task 4; `DATABASE_URL` is refused after it).
   - After: stop the stack, then `DATABASE_URL=sqlite:///<main>/data/maestro_cs.sqlite3 BASE_RESUMES_DIR=<main>/base_resumes python -m scripts.ats_calibration snapshot /tmp/after.json` and `python -m scripts.ats_calibration diff /tmp/before.json /tmp/after.json` → no contribution changes. Then `… monotonicity` → passes.
5. **Concurrency acceptance**: with the compose stack up, start a tailoring run in the UI and, during it, call MCP `score_ats` on another job (or `curl -X POST …/api/ats/score`). Both succeed; `docker compose logs backend | grep -i "database is locked"` prints nothing.
6. **Bind-mount WAL smoke** (macOS Docker Desktop): `for i in $(seq 1 200); do curl -s -o /dev/null -X POST localhost:8001/api/autofill/telemetry -H 'content-type: application/json' -d '[]' & done; wait` then the grep above prints nothing and `/health` still answers.
7. **Update rehearsal** (design §6 item 5): a scratch clone at the previous tag with real rows in Postgres → `./scripts/update.sh` → `data/.migrated-from-postgres.json` exists, tracker shows the rows, a PDF renders, `--check` says `database: data/maestro_cs.sqlite3`.
8. **Slop ratchet** (maintainer tooling, repo root): `python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check backend` → name the surface in the claim. This change touches `backend/` only.

Gate 4 needs the Postgres snapshot taken first; do it before starting Task 4 if the maintainer's stack is available, and record the file path in the deviation log.

---

## Deviation log

Append-only. One line per deviation: task, what the plan said, what was found, what was done, which Goal Card line it serves.

| Task | Planned | Found | Done | Goal Card line |
|---|---|---|---|---|
| 2 | `types.py` imports `UTC, datetime` | `datetime` unused; ruff F401 blocks the commit | import `UTC` only | do not fix unrelated things |
| 2 | ship `compare_type_unwrapping_decorators` | Alembic 1.18 compares compiled DDL; hook redundant and coarser (ignores type args) | removed the hook and its test; Tasks 6/7 use `compare_type=True` | one dialect, no extra machinery |
| 2 | — | `UTCDateTime` given a `date` fails with `AttributeError`, not the intended message | `process_bind_param` raises `TypeError` for non-`datetime` | correctness |
| 1 | `import app.models` registers every table | `app/models/__init__.py` omitted `referral`; `sorted_tables` raised `NoReferencedTableError` unless conftest had imported it | added the import + a static pin that every model module is imported by `__init__` | no data loss (a table the registry forgets is a table the importer skips) |
| 3 | naive binds only ever come from server code | `ApplicationPatch.applied_at` accepts a naive ISO string from clients | field typed `AwareDatetime`, 422 at the boundary (Task 3 Step 2b) | security boundary / correctness |
| 19 | pre-port calibration snapshot taken in this worktree before Task 4 | Postgres refused after Task 4 in THIS tree only; the main checkout still runs the old code | snapshot taken from the main checkout at `b4afd7ef` against the live Postgres: 2015 pairs, ats-2.5.0, `scratchpad/ats-before.json` | deterministic scores |
| 3 | codemod rewrites 18 files | 20: `bullet_classification.py` and `bullet_rewrite.py` had only `DateTime(timezone=True)` | rewritten by the same codemod | one dialect |
| 3 | "expect tests, not app code" | `routers/jobs.py:386-395` binds a `date` query param to `created_at`; `UTCDateTime` refuses it → `/api/jobs/export?since=` 500 | router converts to midnight UTC (`datetime.combine(since, time.min, tzinfo=UTC)`), same instant Postgres implied | no data loss / correctness |
| 3 | `mcp_server/` untouched | `update_application`'s docstring says `applied_at` is "ISO 8601"; a naive value is now a 422 | follow-up: docstring to say "with a UTC offset"; do it with the final review, ratchet test permitting | correctness |
| 3 | transitional suite | full suite on the Postgres test DB after Task 3: `2 failed, 3878 passed, 1 skipped` — the `since=` bug above and the parity test (expected until Task 7) | — | — |
| 3 | `applied_at` is the only request-side datetime | `GET /api/applications?created_after=&created_before=` are `datetime | None` too; a naive value would 500 at flush | both typed `AwareDatetime` → 422 at the boundary, with tests | correctness |
| 3 | — | quality review: codemod placed `from app.models.types import …` inside the third-party import block in 20 files | moved next to `from app.db import Base` as a housekeeping commit at the start of Task 4 | do not fix unrelated things (our own diff) |
| 3 | — | quality review watch-items for later tasks: mixed datetime text formats on SQLite (server defaults lack microseconds), `sa.Uuid` string binds raise on SQLite, `Numeric(5,1)` rounds half-even on SQLite vs half-away on Postgres (harmless: `ats/engine.py:84` rounds before persisting) | first two added to Task 9's fix table; the third is pinned by the Task 19 calibration diff and a comment on `ats_score.composite` | deterministic scores |
| 4 | `startswith("postgresql")` blocklist | Task 7's conftest uses a sqlite allowlist; two doors, two rules; `postgres://` slipped to a `NoSuchModuleError` | allowlist in `_only_sqlite`, same message | one dialect |
| 4 | derive from `data_dir` as given | a relative `DATA_DIR` meant a different file per working directory | `data_dir.resolve()` | no data loss |
| 4 | four config tests | `sqlite_journal_mode` had no test; the refusal test imported `app.config` after setting env and passed only via conftest's earlier import | tests added/reordered | correctness |
| 4 | — | `backend/scripts/{ats_calibration,ats_snapshot,apply_template_sources}.py` docstrings still say `DATABASE_URL=postgresql://…` | Task 18 already lists them; for the desktop work later, build the URL with `URL.create("sqlite", database=…)` rather than an f-string (a `?` in a home path would truncate) | — |
| 5 | `make_engine` pre-creates the file at construction | that runs at `import app.db`, i.e. for every model import; a host process without `DATA_DIR` died on `mkdir('/app/data')` (read-only), and the MCP host venv, scripts and dev shells import models without a writable `/app` | file is prepared in a `do_connect` listener, so import touches nothing and a wrong `DATA_DIR` fails at the first real connection; test pins that `import app.db` in a subprocess with an unwritable URL exits 0 | correctness / no data loss |
| 5 | docstring: "SQLite forgets all four when a connection closes" | `journal_mode` persists in the file; the other three are per-connection | docstring corrected; all four still set on every connection so a `DELETE` override wins | — |
| 5 | run this task's tests with conftest | the Postgres-era conftest cannot host a sqlite URL (its fixture runs `CREATE DATABASE`) and its bare `postgresql://` default only imports here because anaconda carries an undeclared psycopg2 | Tasks 5–6 run their named tests with `--noconftest` and an explicit sqlite `TEST_DATABASE_URL`; Task 7 retires the fixture | — |
| 5 | "`tests/test_model_types.py` does not import app.db" | it does, through `app.models.__init__` → `application.py` → `app.db` | plan note corrected here; no code change | — |
| 7 | — | suite baseline on SQLite before fixes: `N failed, M passed` | — | — |

**LLM-call audit (Task 10):**

| file | LLM call (line) | write flushed before it? | action |
|---|---|---|---|

**Gate results (Task 19):**

| gate | result | evidence |
|---|---|---|
