import os
from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context


def _normalize_postgres_url(value: str) -> str:
    # Mirrors app.config.normalize_postgres_url and dies with this box. Inlined
    # so this env.py never imports app.config: instantiating Settings() reads
    # .env and refuses a compose-era DATABASE_URL before the box can say
    # "no source URL". The bare scheme selects psycopg2, which this project
    # does not install.
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value[len("postgresql://") :]
    return value


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
# A module variable, never written back with set_main_option: ConfigParser
# interpolation breaks on the '%' of a URL-encoded password.
SOURCE_URL = _normalize_postgres_url(_url)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    # disable_existing_loggers defaults to TRUE, which switches off every logger
    # already created. The importer (app.tools.migrate_from_postgres) runs this
    # chain in-process through alembic.command, so the default would silence
    # its own loggers for the rest of the run.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Upgrade-only: the ported models describe the SQLite schema, not this one.
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine; calls to
    context.execute() emit the given string to the script output.
    """
    context.configure(
        url=SOURCE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode: create an Engine and associate a
    connection with the context."""
    connectable = create_engine(SOURCE_URL, poolclass=pool.NullPool, future=True)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
