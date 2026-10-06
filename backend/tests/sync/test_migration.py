"""Split-ownership schema changes preserve populated installs and round-trip sync rows."""

import sqlite3
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from app.db import Base, make_engine
import app.models  # noqa: F401  registers every table

PRE_SYNC_REVISION = "7d3c1a9e5b20"
JOB_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
RUN_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
SYNC_TABLES = {"sync_state", "sync_tombstones", "sync_requests"}


def _seed_existing_rows(path):
    with closing(sqlite3.connect(path)) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute(
            "INSERT INTO jobs (id, raw_text, raw_text_hash) VALUES (?, ?, ?)",
            (JOB_ID.hex, "A role description", "a" * 64),
        )
        db.execute(
            "INSERT INTO job_skills (job_id, skill_name, skill_category, requirement_level) "
            "VALUES (?, 'Python', 'technical', 'required')",
            (JOB_ID.hex,),
        )
        db.execute(
            "INSERT INTO agent_runs (id, automation, outcome, counts, digest, job_ids) "
            "VALUES (?, 'hunt', 'ok', '{}', 'Run completed', '[]')",
            (RUN_ID.hex,),
        )
        db.commit()


@pytest.fixture
def migrated_db(tmp_path):
    path = tmp_path / "sync-migration.sqlite3"
    backend = Path(__file__).resolve().parents[2]
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    command.upgrade(cfg, PRE_SYNC_REVISION)
    _seed_existing_rows(path)
    command.upgrade(cfg, "head")
    return cfg, path


def _assert_existing_rows(db):
    assert db.execute("SELECT id, raw_text, raw_text_hash FROM jobs").fetchall() == [
        (JOB_ID.hex, "A role description", "a" * 64)
    ]
    assert db.execute("SELECT * FROM job_skills").fetchall() == [
        (JOB_ID.hex, "Python", "technical", "required")
    ]
    assert db.execute("SELECT id, digest FROM agent_runs").fetchall() == [
        (RUN_ID.hex, "Run completed")
    ]
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def _assert_upgraded_schema(db):
    assert db.execute("SELECT owner_machine, sync_rev, handover FROM jobs").fetchall() == [
        (None, 0, None)
    ]
    assert db.execute("SELECT machine FROM agent_runs").fetchall() == [(None,)]
    assert db.execute("SELECT name, value FROM sync_state ORDER BY name").fetchall() == [
        ("clock", 0), ("profile_rev", 0)
    ]
    assert {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} >= SYNC_TABLES
    _assert_existing_rows(db)


def test_upgrade_downgrade_upgrade_preserves_existing_rows(migrated_db):
    cfg, path = migrated_db
    with closing(sqlite3.connect(path)) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
        assert {"owner_machine", "sync_rev", "handover"} <= columns
        _assert_upgraded_schema(db)
    command.downgrade(cfg, PRE_SYNC_REVISION)
    with closing(sqlite3.connect(path)) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
        assert not {"owner_machine", "sync_rev", "handover"} & columns
        assert "machine" not in {row[1] for row in db.execute("PRAGMA table_info(agent_runs)")}
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert not SYNC_TABLES & tables
        _assert_existing_rows(db)
    command.upgrade(cfg, "head")
    with closing(sqlite3.connect(path)) as db:
        _assert_upgraded_schema(db)
        db.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO jobs (id, raw_text, raw_text_hash) VALUES (?, 'Duplicate', ?)",
                (uuid.uuid4().hex, "a" * 64),
            )
        db.execute("DELETE FROM jobs WHERE id=?", (JOB_ID.hex,))
        assert db.execute("SELECT * FROM job_skills").fetchall() == []


@pytest.mark.parametrize(
    ("table", "expected"),
    [
        ("sync_state", {"name": (False, True), "value": (False, False)}),
        ("sync_tombstones", {
            "job_id": (False, True), "rev": (False, False), "deleted_at": (False, False),
        }),
        ("sync_requests", {
            "id": (False, True), "job_id": (True, False), "kind": (False, False),
            "payload_json": (False, False), "status": (False, False), "reason": (True, False),
            "created_at": (False, False), "answered_at": (True, False), "origin": (False, False),
        }),
    ],
)
def test_sync_table_columns_and_nullability(migrated_db, table, expected):
    _, path = migrated_db
    engine = make_engine(f"sqlite:///{path}")
    try:
        inspector = sa.inspect(engine)
        assert table in inspector.get_table_names()
        columns = inspector.get_columns(table)
        assert {c["name"]: (c["nullable"], bool(c["primary_key"])) for c in columns} == expected
        assert inspector.get_foreign_keys(table) == []
    finally:
        engine.dispose()


def test_sync_models_round_trip_without_a_job_foreign_key(migrated_db):
    assert SYNC_TABLES <= Base.metadata.tables.keys()
    from app.models import AgentRun, Job, SyncRequest, SyncState, SyncTombstone

    _, path = migrated_db
    engine = make_engine(f"sqlite:///{path}")
    missing_job_id = uuid.uuid4()
    answered_at = datetime(2026, 10, 6, 12, 30, tzinfo=UTC)
    try:
        with Session(engine) as db:
            assert db.get(Job, JOB_ID).owner_machine is None
            assert db.get(Job, JOB_ID).sync_rev == 0
            assert db.get(AgentRun, RUN_ID).machine is None
            db.add(SyncTombstone(job_id=missing_job_id, rev=4))
            request = SyncRequest(
                job_id=missing_job_id, kind="take_over", payload_json={},
                status="pending", origin="local",
            )
            incoming = SyncRequest(
                job_id=None, kind="application_patch", payload_json={"fields": {"notes": "Follow up"}},
                status="refused", origin="incoming", reason="No longer available", answered_at=answered_at,
            )
            db.add_all([request, incoming])
            db.commit()
            request_id, incoming_id = request.id, incoming.id
        with Session(engine) as db:
            tombstone = db.get(SyncTombstone, missing_job_id)
            assert tombstone.rev == 4 and tombstone.deleted_at.tzinfo is UTC
            assert db.get(SyncState, "clock").value == 0
            request = db.get(SyncRequest, request_id)
            assert isinstance(request.id, uuid.UUID) and request.job_id == missing_job_id
            assert request.created_at.tzinfo is UTC and request.answered_at is None
            assert (request.kind, request.payload_json, request.status, request.origin, request.reason) == (
                "take_over", {}, "pending", "local", None,
            )
            incoming = db.get(SyncRequest, incoming_id)
            assert (incoming.job_id, incoming.status, incoming.origin, incoming.reason, incoming.answered_at) == (
                None, "refused", "incoming", "No longer available", answered_at,
            )
            assert incoming.payload_json == {"fields": {"notes": "Follow up"}}
    finally:
        engine.dispose()
