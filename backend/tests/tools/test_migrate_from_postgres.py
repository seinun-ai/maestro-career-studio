"""app.tools.migrate_from_postgres.

The copy logic is dialect-agnostic (reflection on the source, the app's own
metadata on the target), so it is exercised here SQLite→SQLite. The one thing
only Postgres can prove — psycopg's dict/aware-datetime/Decimal values — is
covered by test_export_from_real_postgres, which CI's legacy job runs.
"""
import json
import os
import shutil
import sqlite3
import stat
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.db import make_engine
from app.models.ats_score import AtsScore
from app.models.career_kb import KBEntity
from app.models.job import Job
from app.models.resume_version import ResumeVersion
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
        # gaps_json OMITTED, not None: the ORM writes SQL NULL for a column it
        # was never given, while an explicit None is the JSON text 'null'.
        session.add(AtsScore(
            job_id=job.id, target_type="base_resume", target_id="example", phase="base",
            composite=Decimal("72.5"), subscores_json={"a": 1}, skill_table_json=[],
            config_version="v", engine_version="v",
        ))
        session.add(KBEntity(kind="experience", title="Thing"))
        # The child sorts BEFORE its parent by primary key, so copy_database
        # inserts it first: only defer_foreign_keys makes that legal.
        parent = ResumeVersion(
            id=uuid.UUID("ffffffff-ffff-4fff-8fff-ffffffffffff"), resume_kind="base",
            resume_key="example", version_number=1, snapshot={"v": 1}, source="create",
        )
        child = ResumeVersion(
            id=uuid.UUID("00000000-0000-4000-8000-000000000000"), resume_kind="base",
            resume_key="example", version_number=2, parent_version_id=parent.id,
            snapshot={"v": 2}, source="form_edit",
        )
        session.add_all([parent, child])
        session.commit()
    engine.dispose()
    return {"jobs": 1, "ats_scores": 1, "kb_entities": 1, "resume_versions": 2}


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


def _typeof(url: str, table: str, column: str) -> list[str]:
    engine = make_engine(url)
    try:
        with engine.connect() as conn:
            return conn.execute(sa.text(f"SELECT typeof({column}) FROM {table}")).scalars().all()
    finally:
        engine.dispose()


def test_copy_database_keeps_a_sql_null_json_column_null(tmp_path):
    src = f"sqlite:///{tmp_path / 'src.sqlite3'}"
    dst = f"sqlite:///{tmp_path / 'dst.sqlite3'}"
    _fresh_schema(src)
    _seed(src)
    _fresh_schema(dst)
    assert _typeof(src, "ats_scores", "gaps_json") == ["null"]
    assert _typeof(src, "jobs", "extracted_json") == ["text"]

    report = tool.copy_database(src, dst, log=lambda *_: None)

    # sa.JSON would bind None as the TEXT 'null' (IS NULL false); both sides read
    # None, so the hash alone cannot tell. typeof can.
    assert _typeof(dst, "ats_scores", "gaps_json") == ["null"]
    assert _typeof(dst, "jobs", "extracted_json") == ["text"]
    assert report["ats_scores"]["ok"] and report["jobs"]["ok"], report


def test_main_hides_the_password_of_a_malformed_source(tmp_path, capsys):
    dst = f"sqlite:///{tmp_path / 'dst.sqlite3'}"
    _fresh_schema(dst)

    # Parses, but names no dialect: an ArgumentError out of create_engine. A
    # string make_url cannot parse takes the same branch and is not echoed.
    code = tool.main([
        "--source", "postgresx://app:s3cret@localhost/db",
        "--target", dst, "--skip-source-upgrade",
    ])

    captured = capsys.readouterr()
    assert code == 1
    assert "malformed source URL (password hidden): postgresx://app:***@localhost/db" in captured.err
    assert "s3cret" not in captured.err + captured.out


def test_import_if_needed_hides_the_password_of_a_malformed_source(tmp_path):
    dst = f"sqlite:///{tmp_path / 'dst.sqlite3'}"
    _fresh_schema(dst)
    marker = tmp_path / ".migrated-from-postgres.json"

    with pytest.raises(tool.ExportError) as info:
        tool.import_if_needed("postgresx://app:s3cret@localhost/db", dst, marker, log=lambda *_: None)

    # The boot hook logs the whole chain: no link of it may carry the password.
    assert "s3cret" not in str(info.value)
    assert info.value.__cause__ is None and info.value.__suppress_context__
    assert not marker.exists()


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
    if os.name == "posix":
        # Like the database file: the marker names every table and its row count.
        assert stat.S_IMODE(marker.stat().st_mode) == 0o600


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


def _corrupt_target_hash_of(monkeypatch, table_name: str):
    """Make copy_database see a content mismatch on ONE table. It hashes each
    table's source rows first and reads the target back second, so the second
    call for that table's column set is the target side. Returns the real
    table_hash, so a test can put it back and prove the retry."""
    real = tool.table_hash
    columns = tuple(column.name for column in tool.Base.metadata.tables[table_name].columns)
    seen: set[tuple[str, ...]] = set()

    def corrupted(rows, column_names):
        key = tuple(column_names)
        if key == columns and key in seen:
            return "0" * 64
        seen.add(key)
        return real(rows, column_names)

    monkeypatch.setattr(tool, "table_hash", corrupted)
    return real


def _count(url: str, table: str) -> int:
    engine = make_engine(url)
    try:
        with engine.connect() as conn:
            return conn.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar()
    finally:
        engine.dispose()


def test_import_if_needed_rolls_back_a_verification_mismatch_then_retries(tmp_path, monkeypatch):
    src = f"sqlite:///{tmp_path / 'src.sqlite3'}"
    dst = f"sqlite:///{tmp_path / 'dst.sqlite3'}"
    _fresh_schema(src)
    _seed(src)
    _fresh_schema(dst)
    marker = tmp_path / ".migrated-from-postgres.json"
    real = _corrupt_target_hash_of(monkeypatch, "jobs")

    with pytest.raises(tool.ExportError, match=r"\['jobs'\]") as info:
        tool.import_if_needed(src, dst, marker, log=lambda *_: None, upgrade_source=False)

    assert info.value.report["jobs"]["ok"] is False
    assert info.value.report["kb_entities"]["ok"] is True
    assert not marker.exists()
    # The WHOLE transaction rolled back, not just the mismatched table.
    for table in ("jobs", "ats_scores", "kb_entities"):
        assert _count(dst, table) == 0

    # The file is as empty as it was, so the next boot retries and succeeds.
    monkeypatch.setattr(tool, "table_hash", real)
    assert tool.import_if_needed(src, dst, marker, log=lambda *_: None, upgrade_source=False) == "imported"
    assert _count(dst, "jobs") == 1 and marker.exists()


def test_main_prints_the_report_and_commits_nothing_on_a_mismatch(tmp_path, monkeypatch, capsys):
    src = f"sqlite:///{tmp_path / 'src.sqlite3'}"
    _fresh_schema(src)
    _seed(src)
    target = tmp_path / "dst.sqlite3"
    _corrupt_target_hash_of(monkeypatch, "jobs")

    code = tool.main(["--source", src, "--target", f"sqlite:///{target}", "--skip-source-upgrade"])

    captured = capsys.readouterr()
    assert code == 1
    assert "MISMATCH" in captured.out and "nothing was committed" in captured.err
    assert not (tmp_path / tool.MARKER_NAME).exists()
    assert _count(f"sqlite:///{target}", "jobs") == 0


def _wal_image_with_rows(tmp_path, name: str, rows: int):
    """A target whose committed rows live only in its -wal: the pooled
    connection is still open when the image is taken, so nothing has been
    checkpointed. Returns the image's URL."""
    from sqlalchemy.orm import Session

    live = tmp_path / "live.sqlite3"
    _fresh_schema(f"sqlite:///{live}")
    engine = make_engine(f"sqlite:///{live}")
    with Session(engine) as session:
        session.add_all(KBEntity(kind="project", title=f"Row {n}") for n in range(rows))
        session.commit()
    image = tmp_path / name
    shutil.copy(live, image)
    shutil.copy(f"{live}-wal", f"{image}-wal")
    # Taken now, before dispose() closes the last connection and checkpoints:
    # the main file alone must NOT have the rows, or the image proves nothing.
    bare = tmp_path / "bare.sqlite3"
    shutil.copy(live, bare)
    engine.dispose()
    assert _sqlite_count(bare, "kb_entities") == 0
    return f"sqlite:///{image}"


def _sqlite_count(path, table: str) -> int:
    conn = sqlite3.connect(path)
    try:
        return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def test_replace_folds_the_wal_in_so_the_moved_aside_copy_is_complete(tmp_path):
    src = f"sqlite:///{tmp_path / 'src.sqlite3'}"
    _fresh_schema(src)
    _seed(src)
    crash = _wal_image_with_rows(tmp_path, "crash.sqlite3", rows=3)

    code = tool.main(["--source", src, "--target", crash, "--replace", "--skip-source-upgrade"])

    assert code == 0
    (aside,) = tmp_path.glob("crash.sqlite3.replaced-*")
    assert _sqlite_count(aside, "kb_entities") == 3
    assert _count(crash, "kb_entities") == 1  # the fresh import, not the old rows


def test_move_aside_folds_the_wal_in_by_itself(tmp_path):
    # Direct call, so the checkpoint is _move_aside's own work: the end-to-end
    # path also runs _target_is_schema_only, whose connect/dispose can fold the
    # WAL in as a side effect and mask a _move_aside that no longer does.
    crash = tmp_path / "crash.sqlite3"
    _wal_image_with_rows(tmp_path, crash.name, rows=3)

    aside = tool._move_aside(crash)

    assert aside is not None and aside.name.startswith("crash.sqlite3.replaced-")
    assert not crash.exists()
    assert not (tmp_path / "crash.sqlite3-wal").exists()
    assert not (tmp_path / "crash.sqlite3-shm").exists()
    assert not list(tmp_path.glob("crash.sqlite3.replaced-*-wal"))
    assert _sqlite_count(aside, "kb_entities") == 3


def test_replace_refuses_while_another_process_holds_the_file(tmp_path, monkeypatch, capsys):
    src = f"sqlite:///{tmp_path / 'src.sqlite3'}"
    _fresh_schema(src)
    held = _wal_image_with_rows(tmp_path, "held.sqlite3", rows=3)
    reader = sqlite3.connect(tmp_path / "held.sqlite3")
    reader.execute("BEGIN")
    reader.execute("SELECT count(*) FROM kb_entities").fetchone()  # holds a WAL read mark
    monkeypatch.setattr(tool, "CHECKPOINT_TIMEOUT", 0)
    try:
        code = tool.main(["--source", src, "--target", held, "--replace", "--skip-source-upgrade"])
    finally:
        reader.close()

    assert code == 2
    assert "another process holds" in capsys.readouterr().out
    assert not list(tmp_path.glob("held.sqlite3.replaced-*"))
    assert _sqlite_count(tmp_path / "held.sqlite3", "kb_entities") == 3


def test_main_checks_the_source_before_touching_the_target(tmp_path, capsys):
    dst = f"sqlite:///{tmp_path / 'dst.sqlite3'}"
    _fresh_schema(dst)
    _seed(dst)

    code = tool.main([
        "--source", "sqlite:////nonexistent-dir-for-this-test/none.sqlite3",
        "--target", dst, "--replace", "--skip-source-upgrade",
    ])

    assert code == 1
    assert "cannot be reached" in capsys.readouterr().err
    assert not list(tmp_path.glob("dst.sqlite3.replaced-*"))
    assert _count(dst, "jobs") == 1


def test_main_imports_into_a_migrated_but_empty_target_without_replace(tmp_path):
    src = f"sqlite:///{tmp_path / 'src.sqlite3'}"
    _fresh_schema(src)
    _seed(src)
    dst = f"sqlite:///{tmp_path / 'dst.sqlite3'}"
    _fresh_schema(dst)  # what a failed-closed first boot leaves behind

    code = tool.main(["--source", src, "--target", dst, "--skip-source-upgrade"])

    assert code == 0
    assert _count(dst, "jobs") == 1
    assert (tmp_path / tool.MARKER_NAME).exists()


def _legacy_source_url() -> str:
    source = os.environ.get("LEGACY_POSTGRES_TEST_URL")
    if not source:
        # Skipping is right locally, where there is no Postgres. In CI it would
        # mean the legacy-postgres-export job quietly stopped testing anything:
        # its tests skip, pytest exits 0, and the job stays green forever.
        # So under CI a missing URL is a failure, not a skip.
        if os.environ.get("CI", "").lower() not in ("", "0", "false"):
            pytest.fail(
                "LEGACY_POSTGRES_TEST_URL is not set in CI; "
                "the legacy-postgres-export job must provide it"
            )
        pytest.skip("LEGACY_POSTGRES_TEST_URL not set (CI's legacy-postgres-export job sets it)")
    return source


# The legacy revision that adds application_proposals.proposed_by.
_ADDS_PROPOSED_BY = "3a17da2f7144"


def _drop_proposed_by_if_stamped_below_it(source: str) -> None:
    """Make the column match the stamp. A run that died between a downgrade and
    the next upgrade (or a revision run by hand, or a mutation check) can leave
    proposed_by on a database stamped below the revision that adds it; the next
    upgrade would then fail on a duplicate column, run after run."""
    scripts = ScriptDirectory.from_config(Config(str(tool.LEGACY_INI)))
    engine = sa.create_engine(tool.normalize_postgres_url(source), future=True)
    try:
        with engine.begin() as conn:
            inspector = sa.inspect(conn)
            if not inspector.has_table("alembic_version"):
                return
            stamped = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
            applied = {rev.revision for rev in scripts.iterate_revisions(stamped, "base")}
            columns = {col["name"] for col in inspector.get_columns("application_proposals")}
            if _ADDS_PROPOSED_BY not in applied and "proposed_by" in columns:
                conn.execute(sa.text("ALTER TABLE application_proposals DROP COLUMN proposed_by"))
    finally:
        engine.dispose()


def _upgraded_legacy_source() -> str:
    """The real Postgres URL, healed of any half-migrated state a failed run
    left behind, at the legacy chain's head."""
    source = _legacy_source_url()
    _drop_proposed_by_if_stamped_below_it(source)
    tool.upgrade_legacy_source(source)
    return source


@pytest.mark.legacy_postgres
def test_export_from_real_postgres(tmp_path):
    source = _upgraded_legacy_source()
    engine = sa.create_engine(tool.normalize_postgres_url(source), future=True)
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM ats_scores"))
        conn.execute(sa.text("DELETE FROM jobs"))
        job_id = uuid.uuid4()
        # The legacy jobs table has no updated_at column (none of the 54
        # revisions adds one, and the ported model has none either). The
        # salary pair is the one unscaled NUMERIC in the schema: psycopg
        # returns it at the writer's scale, SQLite at a fixed one.
        # Non-ASCII JSONB, a non-UTC timestamptz and a scaled NUMERIC(5,1)
        # are what only psycopg can hand back; each is pinned here.
        conn.execute(
            sa.text(
                "INSERT INTO jobs (id, raw_text, raw_text_hash, extracted_json, title, company, "
                "role_category, salary_min, salary_max, extracted_at, created_at) VALUES "
                "(:id, 'JD', 'h1', CAST(:extracted AS jsonb), 'x', 'Acme', 'data_scientist', "
                "120000, 150000.50, '2026-09-18 10:11:12.123456+05:30', now())"
            ),
            {
                "id": job_id,
                "extracted": json.dumps(
                    {"title": "Ingénieur", "n": [1.5, None, True]}, ensure_ascii=False
                ),
            },
        )
        conn.execute(
            sa.text(
                "INSERT INTO ats_scores (id, job_id, target_type, target_id, phase, composite, "
                "subscores_json, skill_table_json, config_version, engine_version, created_at) "
                "VALUES (:id, :job_id, 'base_resume', 'example', 'base', 72.5, '{}'::jsonb, "
                "'[]'::jsonb, 'c', 'e', now())"
            ),
            {"id": uuid.uuid4(), "job_id": job_id},
        )
    engine.dispose()
    dst = f"sqlite:///{tmp_path / 'dst.sqlite3'}"
    _fresh_schema(dst)

    report = tool.copy_database(source, dst, log=lambda *_: None)

    assert all(entry["ok"] for entry in report.values()), report
    assert report["jobs"]["rows"] == 1 and report["ats_scores"]["rows"] == 1


PROMOTED = "Promoted from the tracker by the user"


def _insert_pre_column_proposals(source: str) -> dict[str, str | None]:
    """A job and two proposals written before `proposed_by` existed: the web
    app's own promotion (fixed plan summary) and an agent's."""
    engine = sa.create_engine(tool.normalize_postgres_url(source), future=True)
    job_id, promoted, hunted = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    insert = sa.text(
        "INSERT INTO application_proposals (id, job_id, plan_json) "
        "VALUES (:id, :job_id, CAST(:plan AS jsonb))"
    )
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM jobs"))
        conn.execute(
            sa.text("INSERT INTO jobs (id, raw_text, raw_text_hash) VALUES (:id, 'JD', 'h1')"),
            {"id": job_id},
        )
        conn.execute(insert, {"id": promoted, "job_id": job_id, "plan": json.dumps({"summary": PROMOTED})})
        conn.execute(insert, {"id": hunted, "job_id": job_id, "plan": json.dumps({"summary": "fit"})})
    engine.dispose()
    return {promoted.hex: "you", hunted.hex: None}


@pytest.mark.legacy_postgres
def test_the_legacy_chain_backfills_proposed_by_and_the_import_copies_it(tmp_path):
    source = _upgraded_legacy_source()
    cfg = Config(str(tool.LEGACY_INI))
    cfg.set_main_option("sqlalchemy.url", tool.normalize_postgres_url(source).replace("%", "%%"))
    command.downgrade(cfg, "85a1bb628e28")
    expected = _insert_pre_column_proposals(source)
    tool.upgrade_legacy_source(source)
    dst = f"sqlite:///{tmp_path / 'dst.sqlite3'}"
    _fresh_schema(dst)

    report = tool.copy_database(source, dst, log=lambda *_: None)

    assert report["application_proposals"]["ok"], report
    engine = make_engine(dst)
    try:
        with engine.connect() as conn:
            select = sa.text("SELECT id, proposed_by FROM application_proposals")
            rows = dict(conn.execute(select).tuples().all())
    finally:
        engine.dispose()
    assert rows == expected
