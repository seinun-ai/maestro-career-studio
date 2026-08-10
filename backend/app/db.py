import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import normalize_postgres_url, settings


# normalize_postgres_url, not the raw value: TEST_DATABASE_URL skips Settings
# entirely, so without this a bare `postgresql://` resolves to the psycopg2
# dialect we do not install.
_db_url = normalize_postgres_url(
    os.environ.get("TEST_DATABASE_URL") or settings.database_url
)
engine = create_engine(_db_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    with SessionLocal() as session:
        yield session
