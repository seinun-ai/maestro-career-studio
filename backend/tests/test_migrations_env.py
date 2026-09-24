"""The alembic chain at its edges, driven through alembic.command the way
seeding.run_startup() drives it: it refuses any non-SQLite URL before it
connects and creates a fresh file 0600.
"""
import os
import sqlite3
import stat
import sys
from contextlib import closing
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_sqlite_chain_refuses_non_sqlite_url():
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", "postgresql+psycopg://nobody@127.0.0.1:1/none")
    # The guard fires while env.py resolves the URL, before any connection.
    with pytest.raises(RuntimeError, match="SQLite only"):
        command.upgrade(cfg, "head")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
def test_fresh_file_from_alembic_is_0600(tmp_path):
    path = tmp_path / "m.sqlite3"
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    command.upgrade(cfg, "head")
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute("select count(*) from alembic_version").fetchone()[0] == 1
