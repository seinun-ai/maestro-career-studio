"""The kb_capture prompt migration updates untouched rows only."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa


ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "migrations" / "versions"


def _migration_module():
    matches = list(VERSIONS.glob("*_resync_untouched_kb_capture_prompt.py"))
    assert len(matches) == 1, "expected the kb_capture prompt resync migration"
    spec = importlib.util.spec_from_file_location("kb_capture_resync", matches[0])
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _old_default() -> str:
    return (ROOT / "app" / "prompts" / "kb_capture.txt").read_text(encoding="utf-8").replace(
        '- When the dump starts in a leading "Label: ..." form, do not echo the label in the title; title the work described instead.\n',
        "",
    )


def _table():
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    settings = sa.Table(
        "settings",
        metadata,
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("value", sa.Text),
    )
    metadata.create_all(engine)
    return engine, settings


def test_resync_updates_untouched_kb_capture_row():
    engine, settings = _table()
    try:
        old = _old_default()
        with engine.begin() as connection:
            connection.execute(settings.insert().values(key="prompt.kb_capture", value=old))
            _migration_module()._resync(connection)
            stored = connection.execute(
                sa.select(settings.c.value).where(settings.c.key == "prompt.kb_capture")
            ).scalar_one()
        assert stored == (ROOT / "app" / "prompts" / "kb_capture.txt").read_text(encoding="utf-8")
    finally:
        engine.dispose()


def test_resync_preserves_customized_kb_capture_row():
    engine, settings = _table()
    try:
        customized = _old_default() + "\nUser customization\n"
        with engine.begin() as connection:
            connection.execute(
                settings.insert().values(key="prompt.kb_capture", value=customized)
            )
            _migration_module()._resync(connection)
            stored = connection.execute(
                sa.select(settings.c.value).where(settings.c.key == "prompt.kb_capture")
            ).scalar_one()
        assert stored == customized
    finally:
        engine.dispose()


def test_resync_write_rechecks_old_value_after_interleaving():
    """A customization arriving after SELECT must win the write race."""
    engine, settings = _table()
    try:
        old = _old_default()
        customized = old + "\nInterleaved user customization\n"
        with engine.begin() as connection:
            connection.execute(settings.insert().values(key="prompt.kb_capture", value=old))

            class InterleavingBind:
                def __init__(self):
                    self.interleaved = False

                def execute(self, statement, parameters=None):
                    result = connection.execute(statement, parameters or {})
                    if not self.interleaved and "SELECT value FROM settings" in str(statement):
                        self.interleaved = True
                        connection.execute(
                            settings.update()
                            .where(settings.c.key == "prompt.kb_capture")
                            .values(value=customized)
                        )
                    return result

            _migration_module()._resync(InterleavingBind())
            stored = connection.execute(
                sa.select(settings.c.value).where(settings.c.key == "prompt.kb_capture")
            ).scalar_one()
        assert stored == customized
    finally:
        engine.dispose()
