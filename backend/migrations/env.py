import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import make_url

from app.config import settings
from app.db import Base, prepare_sqlite_file
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

# TEST_DATABASE_URL bypasses Settings._only_sqlite, and Postgres URLs are still
# live in compose, CI and shells for one release: without this guard `alembic
# upgrade head` would apply the SQLite baseline to a Postgres database.
if make_url(DATABASE_URL).get_backend_name() != "sqlite":
    raise RuntimeError(
        "migrations/: this chain is SQLite only; the Postgres chain lives in "
        "legacy_postgres/ and is read only by app.tools.migrate_from_postgres"
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
    # make_engine turns it ON for every connection. The file still has to be
    # created 0600 (first boot creates it HERE, via `alembic upgrade head`),
    # so prepare it the way make_engine would before this engine touches it.
    # The 30 s busy timeout is make_engine's too: a concurrent backup or dev
    # shell is otherwise a 5 s lock window.
    prepare_sqlite_file(DATABASE_URL)
    connectable = create_engine(
        DATABASE_URL,
        future=True,
        poolclass=pool.NullPool,
        connect_args={"timeout": 30},
    )
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
