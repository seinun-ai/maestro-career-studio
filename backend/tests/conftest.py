import os
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlparse

# Ensure TEST_DATABASE_URL defaults to the throwaway test database before any
# app or database modules are imported during pytest initialization.
DEFAULT_TEST_DATABASE_URL = "postgresql://app:app@127.0.0.1:55432/maestro_cs_test"
if not os.environ.get("TEST_DATABASE_URL"):
    os.environ["TEST_DATABASE_URL"] = DEFAULT_TEST_DATABASE_URL

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
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, delete
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.models.application import Application
from app.models.application_proposal import ApplicationProposal
from app.models.ats_score import AtsScore
from app.models.autofill_field_observation import AutofillFieldObservation
from app.models.base_resume import BaseResume
from app.models.bullet_classification import BulletClassification
from app.models.career_kb import KBDocument, KBEntity, KBPoint, KBPortLog, KBProfile
from app.models.chat import ChatAttachment, ChatMessage, ChatSession
from app.models.consent_event import ConsentEvent
from app.models.health_gate_waiver import HealthGateWaiver
from app.models.job import Job
from app.models.job_skill import JobSkill
from app.models.qa_entry import QAEntry
from app.models.referral import Referral
from app.models.resume_lint_report import ResumeLintReport
from app.models.resume_version import ResumeVersion
from app.models.setting import Setting
from app.models.tailoring_session import TailoringSession
from app.models.template import Template
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


# Tests delete from every user-data table. Refuse to run against an unset URL or
# the dev DB to prevent wiping real data. Set TEST_DATABASE_URL explicitly to
# point at a throwaway database (e.g. maestro_cs_test).
# Both names are protected: "maestro_cs" is the current dev DB, and
# "resume_auto" is the pre-rename one that still holds real data on any
# install predating the Maestro CS rename. Tests truncate every table.
FORBIDDEN_DB_NAMES = {"maestro_cs", "career_studio", "resume_auto"}
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _validate_test_db_url(url: str | None) -> str:
    if not url:
        raise RuntimeError(
            "TEST_DATABASE_URL is not set. Tests truncate every user-data table "
            "and refuse to default to the dev DB. Set TEST_DATABASE_URL to a "
            "throwaway database (e.g. postgresql://app:app@127.0.0.1:55432/maestro_cs_test)."
        )
    db_name = urlparse(url).path.lstrip("/")
    if db_name in FORBIDDEN_DB_NAMES:
        raise RuntimeError(
            f"TEST_DATABASE_URL points at protected database {db_name!r}. "
            f"Use a different database name (e.g. {db_name}_test)."
        )
    # Both engines in this file are built from the return value, so normalizing
    # here covers both. Imported locally: this module deliberately sets env vars
    # before any app import (see the E402 note in pyproject), and a top-level
    # app.config import would move that boundary.
    from app.config import normalize_postgres_url

    return normalize_postgres_url(url)


@pytest.fixture(scope="session", autouse=True)
def _test_database_ready() -> None:
    """Create and migrate the throwaway test database before anything runs.

    This used to happen by accident. Nothing here built the schema, so the
    tables appeared only when some test opened `TestClient(app)` as a context
    manager — that triggers the lifespan, which calls `seeding.run_startup()`,
    which runs `alembic upgrade head`. Whichever test got there first paid for
    everyone. Run one file on its own against a fresh database and it failed
    with `relation "consent_events" does not exist`, which reads like a broken
    test rather than a missing setup step.

    Worse, the database itself was never created. `TEST_DATABASE_URL` defaults
    to `.../maestro_cs_test`, a name that arrived with the Maestro CS rename and
    that no existing machine had, so the honest CI command produced ~969 setup
    errors on a first run — noise that looks catastrophic and means nothing.

    Doing it here makes the dependency explicit and order-independent, and it is
    safe: `_validate_test_db_url` has already refused every protected name, so
    this can only ever create and migrate a throwaway database.
    """
    url = _validate_test_db_url(TEST_DATABASE_URL)
    db_name = urlparse(url).path.lstrip("/")

    # CREATE DATABASE cannot run inside a transaction, hence AUTOCOMMIT, and it
    # needs a connection to some OTHER database — `postgres` always exists.
    admin_url = url.rsplit("/", 1)[0] + "/postgres"
    try:
        admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", future=True)
        with admin.connect() as connection:
            exists = connection.exec_driver_sql(
                "SELECT 1 FROM pg_database WHERE datname = %(name)s", {"name": db_name}
            ).scalar()
            if not exists:
                # Quote the identifier: the name comes from an env var. It has
                # already passed the protected-name guard above.
                quoted = '"' + db_name.replace('"', '""') + '"'
                connection.exec_driver_sql(f"CREATE DATABASE {quoted}")
    except OperationalError:
        raise RuntimeError(
            f"Postgres is unreachable at {admin_url!r}.\n"
            "Start it with:\n"
            "    docker compose up -d postgres\n"
            "(Check nothing else is already bound to port 55432.)"
        ) from None

    # Bring the schema to head. Cheap when already there, and it is the same
    # path the app itself uses at startup.
    alembic_ini = Path(__file__).resolve().parents[1] / "alembic.ini"
    cfg = Config(str(alembic_ini))
    cfg.set_main_option("script_location", str(alembic_ini.parent / "migrations"))
    command.upgrade(cfg, "head")


@pytest.fixture
def db_session() -> Iterator[Session]:
    url = _validate_test_db_url(TEST_DATABASE_URL)
    engine = create_engine(url, pool_pre_ping=True, future=True)
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("select 1")
    except OperationalError:
        raise RuntimeError(
            f"Postgres test database is unreachable at {url!r}.\n"
            "To launch PostgreSQL locally via Docker Compose, run:\n"
            "    docker compose up -d postgres\n"
            "(Ensure no conflicting local Postgres instance is utilizing port 55432.)"
        ) from None

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    try:
        with SessionLocal() as session:
            _clear_tables(session)
            session.commit()
            yield session
            session.rollback()
            _clear_tables(session)
            session.commit()
    finally:
        # DISPOSE. This fixture builds an engine PER TEST, and an undisposed
        # engine keeps its pooled connections open. ~2,700 tests against a
        # server whose default max_connections is 100 exhausts the server, and
        # the symptom is this fixture's own "database is unreachable" message —
        # which reads like the DB never came up rather than like a leak.
        #
        # Nondeterministic, so it hid for a long time: GC reclaims some engines
        # and closes their pools, so how far the run gets depends on collection
        # timing. Locally it always finished; the first CI run got through 1,964
        # tests and then errored the remaining 798.
        engine.dispose()


def _clear_tables(session: Session) -> None:
    for model in (
        ConsentEvent,
        ApplicationProposal,
        KBPortLog,
        KBPoint,
        KBDocument,
        KBEntity,
        KBProfile,
        ChatMessage,
        ChatAttachment,
        ChatSession,
        HealthGateWaiver,
        ResumeLintReport,
        ResumeVersion,
        TailoringSession,
        QAEntry,
        AtsScore,
        Application,
        JobSkill,
        Job,
        Referral,
        AutofillFieldObservation,
        BaseResume,
        BulletClassification,
        Setting,
        Template,
    ):
        session.execute(delete(model))
