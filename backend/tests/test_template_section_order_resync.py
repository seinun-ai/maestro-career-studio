"""The section_order template update reaches untouched seeded rows safely.

Seeded rows shadow the bundled files, so a template change is invisible to an
existing install until a migration rewrites the row — and it must rewrite ONLY
rows the user never edited.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.services import pdf_render
from app.services.template_registry import HARSHIBAR_DEFAULT_FORMATTING


ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "migrations" / "versions"
PRE_SECTION_ORDER = ROOT / "tests" / "fixtures" / "templates_pre_section_order"
BUNDLED = {
    "default": "resume.tex.j2",
    "typst-classic": "typst_classic.typ",
    "xcharter_serif": "user/xcharter_serif.tex.j2",
    "xcharter_serif_typst": "user/xcharter_serif.typ",
    "carlito_dense": "user/carlito_dense.tex.j2",
    "harshibar": "user/harshibar.tex.j2",
}


def _migration_module():
    matches = list(VERSIONS.glob("*_resync_bundled_templates_section_order.py"))
    assert len(matches) == 1, "expected the section_order resync migration"
    spec = importlib.util.spec_from_file_location("section_order_resync", matches[0])
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _base_source(filename: str) -> str:
    return (PRE_SECTION_ORDER / filename).read_text(encoding="utf-8")


def test_pinned_hashes_are_the_frozen_pre_change_sources():
    """A wrong hash is a SILENT no-op: the migration would skip every row and
    every existing install would keep rendering the old template forever, with
    no error anywhere. So the digests are checked against the bytes they claim
    to describe, not merely against each other."""
    migration = _migration_module()
    assert set(migration._OLD_TEMPLATE_SOURCES) == set(BUNDLED)
    for template_id, filename in BUNDLED.items():
        pinned_file, pinned_hash = migration._OLD_TEMPLATE_SOURCES[template_id]
        assert pinned_file == filename
        old = _base_source(filename)
        assert hashlib.sha256(old.encode("utf-8")).hexdigest() == pinned_hash
        # ...and the snapshot really is the PREVIOUS state, not a stale copy of
        # the live file (which would make the guard vacuous).
        assert old != (pdf_render.TEMPLATE_DIR / filename).read_text(encoding="utf-8")


@pytest.fixture
def template_table():
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    table = sa.Table(
        "templates",
        metadata,
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("default_formatting", sa.JSON),
        sa.Column("parse_certified", sa.Boolean),
        sa.Column("parse_report_json", sa.Text),
        sa.Column("validated_at", sa.DateTime(timezone=True)),
    )
    metadata.create_all(engine)
    try:
        with engine.begin() as connection:
            yield connection, table
    finally:
        engine.dispose()


def _insert(connection, table, sources: dict[str, str], **extra):
    connection.execute(
        table.insert(),
        [
            {
                "id": template_id,
                "source": source,
                "parse_certified": True,
                "parse_report_json": '{"missing": []}',
                "validated_at": datetime(2026, 8, 1, tzinfo=timezone.utc),
                **extra,
            }
            for template_id, source in sources.items()
        ],
    )


def test_resync_updates_all_six_untouched_rows_and_clears_certification(
    template_table,
):
    connection, table = template_table
    _insert(
        connection,
        table,
        {tid: _base_source(name) for tid, name in BUNDLED.items()},
    )

    _migration_module()._resync(connection)

    rows = {row.id: row for row in connection.execute(sa.select(table)).all()}
    assert set(rows) == set(BUNDLED)
    for template_id, filename in BUNDLED.items():
        assert rows[template_id].source == (
            pdf_render.TEMPLATE_DIR / filename
        ).read_text(encoding="utf-8")
        # The old parse evidence describes the OLD source; leaving it would
        # claim the new template is certified without anything having read it.
        assert rows[template_id].parse_certified is None
        assert rows[template_id].parse_report_json is None
        assert rows[template_id].validated_at is None


def test_resync_preserves_customized_rows(template_table):
    """A row that differs from the exact shipped bytes is user-owned."""
    connection, table = template_table
    customized = {
        tid: _base_source(name) + "\n% user customization\n"
        for tid, name in BUNDLED.items()
    }
    _insert(connection, table, customized)

    _migration_module()._resync(connection)

    rows = {row.id: row for row in connection.execute(sa.select(table)).all()}
    for template_id in BUNDLED:
        assert rows[template_id].source == customized[template_id]
        assert rows[template_id].parse_certified is True


def test_harshibar_gets_its_native_order_when_it_has_none(template_table):
    connection, table = template_table
    _insert(connection, table, {"harshibar": _base_source(BUNDLED["harshibar"])})

    _migration_module()._seed_harshibar_order(connection)

    stored = connection.execute(
        sa.select(table.c.default_formatting).where(table.c.id == "harshibar")
    ).scalar_one()
    if isinstance(stored, str):
        stored = json.loads(stored)
    assert stored == HARSHIBAR_DEFAULT_FORMATTING


def test_harshibar_seeding_never_clobbers_a_stored_order(template_table):
    """`default_formatting` is user-editable through the templates API, so a
    migration that overwrote it would silently undo a deliberate choice."""
    connection, table = template_table
    users_own = {"section_order": ["skills", "summary"], "font_size": 12}
    _insert(
        connection,
        table,
        {"harshibar": _base_source(BUNDLED["harshibar"])},
        default_formatting=users_own,
    )

    _migration_module()._seed_harshibar_order(connection)

    stored = connection.execute(
        sa.select(table.c.default_formatting).where(table.c.id == "harshibar")
    ).scalar_one()
    if isinstance(stored, str):
        stored = json.loads(stored)
    assert stored == users_own


def test_harshibar_seeding_keeps_other_formatting_keys(template_table):
    """A row with formatting but no order gains the order and keeps the rest."""
    connection, table = template_table
    _insert(
        connection,
        table,
        {"harshibar": _base_source(BUNDLED["harshibar"])},
        default_formatting={"font_size": 12},
    )

    _migration_module()._seed_harshibar_order(connection)

    stored = connection.execute(
        sa.select(table.c.default_formatting).where(table.c.id == "harshibar")
    ).scalar_one()
    if isinstance(stored, str):
        stored = json.loads(stored)
    assert stored["font_size"] == 12
    assert stored["section_order"] == HARSHIBAR_DEFAULT_FORMATTING["section_order"]
