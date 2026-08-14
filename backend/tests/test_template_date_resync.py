"""The ongoing-role template update reaches untouched seeded rows safely."""
from __future__ import annotations

import hashlib
import importlib.util
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.services import pdf_render


ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "migrations" / "versions"
BUNDLED = {
    "default": "resume.tex.j2",
    "typst-classic": "typst_classic.typ",
    "xcharter_serif": "user/xcharter_serif.tex.j2",
    "xcharter_serif_typst": "user/xcharter_serif.typ",
    "carlito_dense": "user/carlito_dense.tex.j2",
    "harshibar": "user/harshibar.tex.j2",
}
_DATE_BRANCH_REVERSALS = {
    "resume.tex.j2": (
        (" and (exp.start_date|string|trim)", ""),
        (" and (exp.end_date|string|trim)", "", 2),
        (" and (edu.start_date|string|trim)", "", 2),
        (" and (edu.end_date|string|trim)", ""),
        ("if (edu.start_date) else", "if edu.start_date else"),
        ("((* else *)) -- Present", ""),
    ),
    "user/xcharter_serif.tex.j2": (
        (" and (exp.start_date|string|trim)", ""),
        (" and (exp.end_date|string|trim)", "", 2),
        (" and (edu.start_date|string|trim)", "", 2),
        (" and (edu.end_date|string|trim)", ""),
        ("if (edu.start_date) else", "if edu.start_date else"),
        (
            "((* if exp.start_date *))((( exp.start_date|format_date(fmt.date_format)|latex_escape )))((* if exp.end_date *)) -- ((( exp.end_date|format_date(fmt.date_format)|latex_escape )))((* else *)) -- Present((* endif *))((* elif exp.end_date *))((( exp.end_date|format_date(fmt.date_format)|latex_escape )))((* endif *))",
            "((( exp.start_date|format_date(fmt.date_format)|latex_escape )))((* if exp.end_date *)) -- ((( exp.end_date|format_date(fmt.date_format)|latex_escape )))((* endif *))",
        ),
    ),
    "user/carlito_dense.tex.j2": (
        (" and (exp.start_date|string|trim)", ""),
        (" and (exp.end_date|string|trim)", "", 2),
        (" and (edu.start_date|string|trim)", "", 2),
        (" and (edu.end_date|string|trim)", ""),
        ("if (edu.start_date) else", "if edu.start_date else"),
        (
            "((* if exp.start_date *))((( exp.start_date|format_date(fmt.date_format)|latex_escape )))((* if exp.end_date *)) -- ((( exp.end_date|format_date(fmt.date_format)|latex_escape )))((* else *)) -- Present((* endif *))((* elif exp.end_date *))((( exp.end_date|format_date(fmt.date_format)|latex_escape )))((* endif *))",
            "((( exp.start_date|format_date(fmt.date_format)|latex_escape )))((* if exp.end_date *)) -- ((( exp.end_date|format_date(fmt.date_format)|latex_escape )))((* endif *))",
        ),
    ),
    "user/harshibar.tex.j2": (
        (" and (e.start_date|string|trim)", ""),
        (" and (e.end_date|string|trim)", "", 2),
        (" and (edu.start_date|string|trim)", ""),
        (" and (edu.end_date|string|trim)", ""),
        (" and (edu.graduation_date|string|trim)", ""),
        ("if (edu.start_date) else", "if edu.start_date else"),
        ("if (edu.end_date) else", "if edu.end_date else"),
        ("if (edu.graduation_date) else", "if edu.graduation_date else"),
        (
            "((* if e.start_date *))((( e.start_date|format_date(fmt.date_format)|latex_escape )))((* if e.end_date *)) -- ((( e.end_date|format_date(fmt.date_format)|latex_escape )))((* else *)) -- Present((* endif *))((* elif e.end_date *))((( e.end_date|format_date(fmt.date_format)|latex_escape )))((* endif *))",
            "((( e.start_date|format_date(fmt.date_format)|latex_escape )))((* if e.end_date *)) -- ((( e.end_date|format_date(fmt.date_format)|latex_escape )))((* endif *))",
        ),
    ),
    "typst_classic.typ": (
        (
            "#let has_date(value) = value != none and value.trim() != \"\"\n\n#let date_range(start, end, ongoing: false) = {\n  if has_date(start) and has_date(end) [#start #sym.dash.en #end] else if has_date(start) and ongoing [#start #sym.dash.en Present] else if has_date(start) [#start] else if has_date(end) [#end]\n}",
            "#let date_range(start, end) = {\n  if start != none and end != none [#start #sym.dash.en #end] else if start != none [#start] else if end != none [#end]\n}",
        ),
        (
            "date_range(job.start_date, job.end_date, ongoing: true)",
            "date_range(job.start_date, job.end_date)",
        ),
    ),
    "user/xcharter_serif.typ": (
        (
            "#let has_date(value) = value != none and value.trim() != \"\"\n\n#let date_range(start, end, ongoing: false) = {\n  if has_date(start) and has_date(end) [#start -- #end] else if has_date(start) and ongoing [#start #sym.dash.en Present] else if has_date(start) [#start] else if has_date(end) [#end]\n}",
            "#let date_range(start, end) = {\n  if start != none and end != none [#start -- #end] else if start != none [#start] else if end != none [#end]\n}",
        ),
        (
            "date_range(job.start_date, job.end_date, ongoing: true)",
            "date_range(job.start_date, job.end_date)",
        ),
    ),
}


def _migration_module():
    matches = list(VERSIONS.glob("*_resync_bundled_template_dates_present.py"))
    assert len(matches) == 1, "expected the Present-template resync migration"
    spec = importlib.util.spec_from_file_location("template_date_resync", matches[0])
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _base_source(filename: str) -> str:
    """Reverse known date-branch changes and verify the exact old bytes."""
    current = (pdf_render.TEMPLATE_DIR / filename).read_text(encoding="utf-8")
    old_source = current
    for reversal in _DATE_BRANCH_REVERSALS[filename]:
        present_branch, old_branch, *count = reversal
        expected_count = count[0] if count else 1
        assert old_source.count(present_branch) == expected_count
        old_source = old_source.replace(present_branch, old_branch, expected_count)

    migration = _migration_module()
    template_id = next(key for key, value in BUNDLED.items() if value == filename)
    old_hash = migration._OLD_TEMPLATE_SOURCES[template_id][1]
    assert hashlib.sha256(old_source.encode("utf-8")).hexdigest() == old_hash
    return old_source


def test_base_sources_are_reconstructed_without_git_history(monkeypatch):
    """A shallow checkout must still reproduce every byte-identical old seed."""

    def reject_git(*args, **kwargs):
        raise AssertionError("old template fixtures must not read Git history")

    monkeypatch.setattr(subprocess, "run", reject_git)
    migration = _migration_module()
    for template_id, filename in BUNDLED.items():
        old_source = _base_source(filename)
        assert hashlib.sha256(old_source.encode("utf-8")).hexdigest() == (
            migration._OLD_TEMPLATE_SOURCES[template_id][1]
        )


@pytest.fixture
def template_table():
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    table = sa.Table(
        "templates",
        metadata,
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("source", sa.Text, nullable=False),
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


def test_resync_updates_all_six_untouched_rows_and_clears_source_certification(
    template_table,
):
    """Changing the pinned base source replaces every bundled seed, not edits."""
    connection, table = template_table
    connection.execute(
        table.insert(),
        [
            {
                "id": template_id,
                "source": _base_source(filename),
                "parse_certified": True,
                "parse_report_json": '{"missing": []}',
                "validated_at": datetime(2026, 8, 1, tzinfo=timezone.utc),
            }
            for template_id, filename in BUNDLED.items()
        ],
    )

    _migration_module()._resync(connection)

    rows = {row.id: row for row in connection.execute(sa.select(table)).all()}
    assert set(rows) == set(BUNDLED)
    for template_id, filename in BUNDLED.items():
        assert rows[template_id].source == (pdf_render.TEMPLATE_DIR / filename).read_text(
            encoding="utf-8"
        )
        assert rows[template_id].parse_certified is None
        assert rows[template_id].parse_report_json is None
        assert rows[template_id].validated_at is None


def test_resync_preserves_customized_rows(template_table):
    """Rows differing from the exact shipped base are user-owned and unchanged."""
    connection, table = template_table
    customized = {
        template_id: _base_source(filename) + "\n% user customization\n"
        for template_id, filename in BUNDLED.items()
    }
    connection.execute(
        table.insert(),
        [
            {
                "id": template_id,
                "source": source,
                "parse_certified": True,
                "parse_report_json": '{"custom": true}',
                "validated_at": datetime(2026, 8, 1, tzinfo=timezone.utc),
            }
            for template_id, source in customized.items()
        ],
    )

    _migration_module()._resync(connection)

    rows = {row.id: row for row in connection.execute(sa.select(table)).all()}
    for template_id, source in customized.items():
        assert rows[template_id].source == source
        assert rows[template_id].parse_certified is True
        assert rows[template_id].parse_report_json == '{"custom": true}'
        assert rows[template_id].validated_at == datetime(2026, 8, 1)
