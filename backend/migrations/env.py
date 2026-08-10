import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

from app.config import normalize_postgres_url, settings
from app.db import Base
from app.models import *  # noqa: F403 - registers models for Alembic autogenerate

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config
# Same resolution order as app/db.py, and it must stay that way: the test suite
# migrates its own throwaway database through alembic, and reading only
# settings.database_url here would silently point those migrations at the DEV
# database instead — the one holding real career data.
# Wrapped in normalize_postgres_url for the same reason app/db.py is: the
# TEST_DATABASE_URL branch never passes through Settings, so a bare
# `postgresql://` would select the psycopg2 dialect this project does not ship.
config.set_main_option(
    "sqlalchemy.url",
    normalize_postgres_url(os.environ.get("TEST_DATABASE_URL") or settings.database_url),
)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    # disable_existing_loggers defaults to TRUE, which switches off every logger
    # already created. That is wrong for both callers we have: the app runs
    # `alembic upgrade head` from seeding.run_startup() during the FastAPI
    # lifespan, so the default would silence the app's own loggers for the rest
    # of the process; and the test suite migrates its database at session start,
    # where it emptied `caplog` and broke assertions about logged output.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
