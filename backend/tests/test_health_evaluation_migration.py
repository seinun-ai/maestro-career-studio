"""A populated old cache survives upgrading and downgrading the health schema."""
from contextlib import closing
from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config


def test_health_schema_preserves_old_cache_and_false_default(tmp_path):
    path = tmp_path / "health.sqlite3"
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    command.upgrade(cfg, "9a5744f9b9d9")
    with closing(sqlite3.connect(path)) as db:
        db.execute("INSERT INTO bullet_classifications (content_hash, level) VALUES ('old', 'adjacent')")
        db.commit()
    command.upgrade(cfg, "head")
    with closing(sqlite3.connect(path)) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(bullet_classifications)")}
        assert "rubric_version" in columns
        assert db.execute("SELECT level, rubric_version FROM bullet_classifications WHERE content_hash='old'").fetchone() == ('adjacent', 1)
        db.execute("INSERT INTO bullet_disputes (content_hash, note, original_json, revised_json, reply, rubric_version, created_at) VALUES ('x', 'note', '{}', '{}', 'reply', 2, '2026-01-01 00:00:00')")
        assert db.execute("SELECT metric_unavailable FROM bullet_disputes").fetchone()[0] == 0
        db.commit()
    command.downgrade(cfg, "9a5744f9b9d9")
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT level FROM bullet_classifications WHERE content_hash='old'").fetchone()[0] == 'adjacent'
        assert "rubric_version" not in {row[1] for row in db.execute("PRAGMA table_info(bullet_classifications)")}
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='bullet_disputes'").fetchall()


def test_quote_demoted_evaluations_are_cleared_and_everything_else_kept(tmp_path):
    path = tmp_path / "demoted.sqlite3"
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    command.upgrade(cfg, "4022b54933e6")
    rows = [("demoted", "adjacent", None, 2, "[]"),
            ("overridden", "adjacent", "adjacent", 2, "[]"),
            ("quoted", "adjacent", None, 2, '["built the thing"]'),
            ("direct", "direct", None, 2, "[]"),
            ("old_rubric", "adjacent", None, 1, None)]
    with closing(sqlite3.connect(path)) as db:
        db.executemany("INSERT INTO bullet_classifications (content_hash, level, override_level,"
                       " rubric_version, evidence_json) VALUES (?, ?, ?, ?, ?)", rows)
        db.commit()
    command.upgrade(cfg, "643ba5470e73")
    with closing(sqlite3.connect(path)) as db:
        kept = {r[0] for r in db.execute("SELECT content_hash FROM bullet_classifications")}
    assert kept == {"overridden", "quoted", "direct", "old_rubric"}


def test_prompt_resync_deletes_only_previous_default(tmp_path):
    from importlib import import_module
    old = import_module("migrations.versions.d08dd68e4eff_resync_health_prompts").OLD_RESUME_BULLET_CLASSIFY
    path = tmp_path / "prompts.sqlite3"
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    for value, should_survive in [(old, False), ("my custom evaluator", True)]:
        command.upgrade(cfg, "980498217fe6")
        with closing(sqlite3.connect(path)) as db:
            db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('prompt.resume_bullet_classify', ?)", (value,))
            db.commit()
        command.upgrade(cfg, "head")
        with closing(sqlite3.connect(path)) as db:
            row = db.execute("SELECT value FROM settings WHERE key='prompt.resume_bullet_classify'").fetchone()
            assert bool(row) is should_survive
            if row:
                assert row[0] == value
        command.downgrade(cfg, "980498217fe6")
