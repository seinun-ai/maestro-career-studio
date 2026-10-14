"""b7e41c90d3a2 re-seeds the six voice-touched prompts only where the stored row is the old default."""
from contextlib import closing
from importlib import import_module
from pathlib import Path
import sqlite3

import pytest
from alembic import command
from alembic.config import Config

MIGRATION = "migrations.versions.b7e41c90d3a2_resync_voice_prompts"
KEYS = [
    ("tailoring_skill", "OLD_TAILORING_SKILL"),
    ("gap_tailor", "OLD_GAP_TAILOR"),
    ("resume_bullet_rewrite", "OLD_RESUME_BULLET_REWRITE"),
    ("base_resume_instruct", "OLD_BASE_RESUME_INSTRUCT"),
    ("base_from_kb_plan", "OLD_BASE_FROM_KB_PLAN"),
    ("kb_adapt", "OLD_KB_ADAPT"),
]


def _config(path: Path) -> Config:
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    return cfg


@pytest.mark.parametrize("key, const", KEYS)
def test_resync_deletes_only_the_previous_default(tmp_path, key, const):
    old = getattr(import_module(MIGRATION), const)
    new = (Path(__file__).resolve().parents[1] / "app" / "prompts" / f"{key}.txt").read_text(
        encoding="utf-8")
    assert old != new, "the pinned previous default must differ from the shipped file"
    cfg = _config(tmp_path / "prompts.sqlite3")
    for value, should_survive in [(old, False), ("my custom rules", True)]:
        command.upgrade(cfg, "36d355ef8595")
        with closing(sqlite3.connect(tmp_path / "prompts.sqlite3")) as db:
            db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                       (f"prompt.{key}", value))
            db.commit()
        command.upgrade(cfg, "b7e41c90d3a2")
        with closing(sqlite3.connect(tmp_path / "prompts.sqlite3")) as db:
            row = db.execute("SELECT value FROM settings WHERE key = ?", (f"prompt.{key}",)).fetchone()
            assert bool(row) is should_survive
            if row:
                assert row[0] == value
        command.downgrade(cfg, "36d355ef8595")
