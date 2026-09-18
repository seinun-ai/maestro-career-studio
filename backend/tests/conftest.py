import atexit
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
    # The session fixture removes the dir on a normal run. This covers
    # `--collect-only` and a collection-time abort, where no fixture ever runs
    # and every invocation would otherwise leave an empty dir behind.
    atexit.register(shutil.rmtree, _OWNED_TMP, ignore_errors=True)

# Same reason, same timing: `app.main` installs TrustedHostMiddleware from
# `settings.allowed_hosts` at import, and starlette's TestClient sends
# `Host: testserver`. 52 test modules build their own `TestClient(app)`, so the
# allowlist is widened here rather than at ~700 call sites. Kept OUT of the
# production default on purpose — see config.allowed_hosts.
if not os.environ.get("ALLOWED_HOSTS"):
    os.environ["ALLOWED_HOSTS"] = "localhost,127.0.0.1,backend,testserver"

# CORS now admits chrome-extension:// origins by EXACT id (it used to admit all
# of them by regex). Configure the id the extension tests use, so "the companion
# extension can call the API" and "no other extension can" are both testable.
if not os.environ.get("MAESTRO_CS_EXTENSION_IDS"):
    os.environ["MAESTRO_CS_EXTENSION_IDS"] = "abcdefghijklmnopabcdefghijklmnop"

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from tests.ats.fixtures import fake_embed_texts


@pytest.fixture(autouse=True)
def _hermetic_embedder(request, monkeypatch):
    """Make the ENTIRE backend suite model-free and deterministic across machines.

    Every test that scores a resume (directly, via the ATS service, or through a
    router) would otherwise hit the real pinned embedding model — a ~100MB
    download and machine-dependent floats. Patching embed_texts with the
    deterministic fake keeps the suite hermetic and its numbers stable.

    Two opt-out markers keep the fake from clobbering tests that own the seam:
      - `real_model`: run against the ACTUAL model (only the golden snapshot).
      - `embeddings_internals`: exercise embed_texts itself (its memoization /
        batching logic, with `_model` stubbed) — patching embed_texts would
        defeat the very thing under test.
    """
    marker = request.node.get_closest_marker
    if marker("real_model") or marker("embeddings_internals"):
        return
    from app.services.ats import embeddings

    monkeypatch.setattr(embeddings, "embed_texts", fake_embed_texts)


# Tests delete from every table. Refuse anything that could be real data: the
# app's own database, a file under the repo's data/ mount, or a file named
# like the dev database.
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
    # Imported here, not at module top: this module sets env vars before any
    # app import (see the E402 note in pyproject), and app.config reads them.
    from app.config import settings

    own = make_url(settings.database_url).database
    if own and path == Path(own).resolve():
        raise RuntimeError(
            f"TEST_DATABASE_URL {url!r} is the app's own database "
            "(settings.database_url); tests delete every table."
        )
    if REPO_DATA_DIR in path.parents or path.stem in FORBIDDEN_DB_STEMS:
        raise RuntimeError(
            f"TEST_DATABASE_URL {url!r} looks like real data; use a throwaway file "
            f"outside {REPO_DATA_DIR} whose name is not one of {sorted(FORBIDDEN_DB_STEMS)}."
        )
    return url


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
def _test_engine(_test_database_ready):
    # Imported here, not at module top: this module sets env vars before any
    # app import (see the E402 note in pyproject), and app.db reads them.
    from app.db import make_engine

    engine = make_engine(_validate_test_db_url(TEST_DATABASE_URL))
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(_test_engine) -> Iterator[Session]:
    """A session on the shared engine, every table cleared before and after.

    One reachable stall: a test that leaves an app-side session (app.db's
    SessionLocal, a TestClient dependency) holding an UNCOMMITTED write keeps
    SQLite's write lock, so the clearing DELETEs here wait the full
    busy_timeout (30 s) and then fail with "database is locked" — in this
    fixture's teardown or the next test's setup, attributed to the wrong test.
    """
    SessionLocal = sessionmaker(bind=_test_engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        _clear_tables(session)
        session.commit()
        yield session
        # Load-bearing: commit() flushes pending objects, so without this
        # rollback a never-flushed `add` would be written AFTER the deletes
        # below and leak into the next test.
        session.rollback()
        _clear_tables(session)
        session.commit()


def _clear_tables(session: Session) -> None:
    from app.db import Base
    import app.models  # noqa: F401  registers every table

    # Children before parents, so no DELETE trips a foreign key: the
    # connection has foreign_keys=ON (app.db.make_engine), which is the point,
    # and it stays ON everywhere else. Deferral is belt-and-braces for the
    # ORDER: SQLite then checks the constraints at COMMIT instead of per
    # statement, so the reverse-sorted_tables walk stays correct even if a
    # future mutual FK pair makes that order arbitrary. The pragma switches
    # itself off at each COMMIT or ROLLBACK, so it covers exactly this
    # transaction; pysqlite opens that transaction at the first DELETE, and a
    # flag set before it carries in (verified: parent-first DELETE, clean commit).
    session.execute(sa.text("PRAGMA defer_foreign_keys=ON"))
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
