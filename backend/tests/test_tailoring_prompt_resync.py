"""4022b54933e6 re-seeds the tailoring prompts only where the stored row is the old default."""
from contextlib import closing
from importlib import import_module
from pathlib import Path
import sqlite3

import pytest
from alembic import command
from alembic.config import Config

MIGRATION = "migrations.versions.4022b54933e6_resync_tailoring_prompts"


def _config(path: Path) -> Config:
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    return cfg


@pytest.mark.parametrize("key, const", [
    ("tailoring_skill", "OLD_TAILORING_SKILL"),
    ("gap_tailor", "OLD_GAP_TAILOR"),
    ("chat_system", "OLD_CHAT_SYSTEM"),
])
def test_resync_deletes_only_the_previous_default(tmp_path, key, const):
    old = getattr(import_module(MIGRATION), const)
    new = (Path(__file__).resolve().parents[1] / "app" / "prompts" / f"{key}.txt").read_text(
        encoding="utf-8")
    assert old != new, "the pinned previous default must differ from the shipped file"
    cfg = _config(tmp_path / "prompts.sqlite3")
    for value, should_survive in [(old, False), ("my custom rules", True)]:
        command.upgrade(cfg, "d08dd68e4eff")
        with closing(sqlite3.connect(tmp_path / "prompts.sqlite3")) as db:
            db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                       (f"prompt.{key}", value))
            db.commit()
        command.upgrade(cfg, "4022b54933e6")
        with closing(sqlite3.connect(tmp_path / "prompts.sqlite3")) as db:
            row = db.execute("SELECT value FROM settings WHERE key = ?", (f"prompt.{key}",)).fetchone()
            assert bool(row) is should_survive
            if row:
                assert row[0] == value
        command.downgrade(cfg, "d08dd68e4eff")
