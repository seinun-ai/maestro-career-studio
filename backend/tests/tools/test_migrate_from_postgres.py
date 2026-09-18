"""app.tools.migrate_from_postgres.

The copy logic is dialect-agnostic (reflection on the source, the app's own
metadata on the target), so it is exercised here SQLite→SQLite. The one thing
only Postgres can prove — psycopg's dict/aware-datetime/Decimal values — is
covered by test_export_from_real_postgres, which CI's legacy job runs.
"""
import os
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from app.db import make_engine
from app.models.ats_score import AtsScore
from app.models.career_kb import KBEntity
from app.models.job import Job
from app.tools import migrate_from_postgres as tool

BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _fresh_schema(url: str) -> None:
    cfg = Config(os.path.join(BACKEND, "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(cfg, "head")


def _seed(url: str) -> dict[str, int]:
    engine = make_engine(url)
    from sqlalchemy.orm import Session

    with Session(engine) as session:
        job = Job(
            raw_text="JD", raw_text_hash="h1", extracted_json={"title": "x", "n": [1, 2]},
            title="x", company="Acme", role_category="data_scientist",
            extracted_at=datetime.now(UTC),
        )
        session.add(job)
        session.flush()
        session.add(AtsScore(
            job_id=job.id, target_type="base_resume", target_id="example", phase="base",
            composite=Decimal("72.5"), subscores_json={"a": 1}, skill_table_json=[],
            config_version="v", engine_version="v",
        ))
        session.add(KBEntity(kind="experience", title="Thing"))
        session.commit()
    engine.dispose()
    return {"jobs": 1, "ats_scores": 1, "kb_entities": 1}


def test_normalize_value_is_canonical():
    ref = uuid.uuid4()
    assert tool.normalize_value(ref) == str(ref)
    naive = datetime(2026, 9, 17, 6, 30)
    aware = datetime(2026, 9, 17, 6, 30, tzinfo=UTC)
    assert tool.normalize_value(naive) == tool.normalize_value(aware)
    # Scale-free: psycopg returns NUMERIC at the writer's scale, SQLite's
    # dialect at a fixed 10-digit one; the same number must hash the same.
    assert tool.normalize_value(Decimal("72.50")) == "72.5"
    assert tool.normalize_value(Decimal("120000")) == tool.normalize_value(
        Decimal("120000.0000000000")
    )
    assert tool.normalize_value(Decimal("120000.5")) != tool.normalize_value(Decimal("120000"))
    assert tool.normalize_value({"b": 1, "a": [2]}) == tool.normalize_value({"a": [2], "b": 1})


def test_copy_database_round_trips_and_verifies(tmp_path):
    src = f"sqlite:///{tmp_path / 'src.sqlite3'}"
    dst = f"sqlite:///{tmp_path / 'dst.sqlite3'}"
    _fresh_schema(src)
    expected = _seed(src)
    _fresh_schema(dst)

    report = tool.copy_database(src, dst, log=lambda *_: None)

    assert all(entry["ok"] for entry in report.values()), report
    for table, n in expected.items():
        assert report[table]["rows"] == n == report[table]["target_rows"]
    assert report["jobs"]["source_hash"] == report["jobs"]["target_hash"]


def test_main_refuses_a_non_empty_target_without_replace(tmp_path, capsys):
    src = f"sqlite:///{tmp_path / 'src.sqlite3'}"
    _fresh_schema(src)
    target = tmp_path / "dst.sqlite3"
    target.write_bytes(b"not empty")

    code = tool.main(["--source", src, "--target", f"sqlite:///{target}", "--skip-source-upgrade"])

    assert code == 2
    assert "refusing" in capsys.readouterr().out


def test_import_if_needed_is_idempotent_and_writes_the_marker(tmp_path):
    src = f"sqlite:///{tmp_path / 'src.sqlite3'}"
    dst = f"sqlite:///{tmp_path / 'dst.sqlite3'}"
    _fresh_schema(src)
    _seed(src)
    _fresh_schema(dst)
    marker = tmp_path / ".migrated-from-postgres.json"
    log: list[str] = []

    first = tool.import_if_needed(src, dst, marker, log=log.append, upgrade_source=False)
    second = tool.import_if_needed(src, dst, marker, log=log.append, upgrade_source=False)

    assert first == "imported" and second == "already-imported"
    assert marker.exists() and '"jobs"' in marker.read_text()


def test_import_if_needed_skips_a_target_that_already_has_data(tmp_path):
    src = f"sqlite:///{tmp_path / 'src.sqlite3'}"
    dst = f"sqlite:///{tmp_path / 'dst.sqlite3'}"
    _fresh_schema(src)
    _seed(src)
    _fresh_schema(dst)
    _seed(dst)
    marker = tmp_path / ".migrated-from-postgres.json"

    outcome = tool.import_if_needed(src, dst, marker, log=lambda *_: None, upgrade_source=False)

    assert outcome == "target-not-empty"
    assert not marker.exists()


def test_import_if_needed_skips_an_unreachable_source(tmp_path):
    dst = f"sqlite:///{tmp_path / 'dst.sqlite3'}"
    _fresh_schema(dst)
    marker = tmp_path / ".migrated-from-postgres.json"

    # A sqlite file in a directory that does not exist: "unable to open" is the
    # same SQLAlchemyError class an unreachable Postgres raises, and this runs
    # without psycopg installed (CI's suite job has no legacy extra).
    outcome = tool.import_if_needed(
        "sqlite:////nonexistent-dir-for-this-test/none.sqlite3", dst, marker, log=lambda *_: None
    )

    assert outcome == "source-unreachable"
    assert not marker.exists()


@pytest.mark.legacy_postgres
def test_export_from_real_postgres(tmp_path):
    source = os.environ.get("LEGACY_POSTGRES_TEST_URL")
    if not source:
        pytest.skip("LEGACY_POSTGRES_TEST_URL not set (CI's legacy-postgres-export job sets it)")
    tool.upgrade_legacy_source(source)
    engine = sa.create_engine(tool.normalize_postgres_url(source), future=True)
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM ats_scores"))
        conn.execute(sa.text("DELETE FROM jobs"))
        job_id = uuid.uuid4()
        # The legacy jobs table has no updated_at column (none of the 54
        # revisions adds one, and the ported model has none either). The
        # salary pair is the one unscaled NUMERIC in the schema: psycopg
        # returns it at the writer's scale, SQLite at a fixed one.
        conn.execute(
            sa.text(
                "INSERT INTO jobs (id, raw_text, raw_text_hash, extracted_json, title, company, "
                "role_category, salary_min, salary_max, extracted_at, created_at) VALUES "
                "(:id, 'JD', 'h1', '{\"title\": \"x\"}'::jsonb, 'x', 'Acme', 'data_scientist', "
                "120000, 150000.50, now(), now())"
            ),
            {"id": job_id},
        )
    engine.dispose()
    dst = f"sqlite:///{tmp_path / 'dst.sqlite3'}"
    _fresh_schema(dst)

    report = tool.copy_database(source, dst, log=lambda *_: None)

    assert report["jobs"]["ok"] and report["jobs"]["rows"] == 1
