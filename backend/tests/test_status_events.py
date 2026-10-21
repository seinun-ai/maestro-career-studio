"""The application status-event log: one dated row per status change (docs/entities/application.md).

Task 2.1: the table, its migration and the backfill. Task 2.2: every writer goes through
`application_status.set_status`.
"""

from contextlib import closing
from pathlib import Path
import sqlite3
import uuid

from alembic import command
from alembic.config import Config
import sqlalchemy as sa

from app import models
from app.config import settings
from app.services.sync import hooks, status as sync_status

BEFORE = "ff9591f140f7"
REVISION = "c5b4833bcc54"
STAMP = "2026-09-01 10:00:00.000000"


def _config(path: Path) -> Config:
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    return cfg


def _tables(db) -> set[str]:
    return {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


# ---------------------------------------------------------------------------- the table


def test_a_fresh_database_has_the_table_its_index_and_a_cascading_link(_test_engine):
    inspector = sa.inspect(_test_engine)
    columns = {column["name"]: column for column in inspector.get_columns("application_status_events")}
    assert set(columns) == {"id", "application_id", "from_status", "to_status", "at", "source",
                            "backfilled"}
    assert not columns["to_status"]["nullable"] and columns["from_status"]["nullable"]
    assert not columns["at"]["nullable"] and not columns["source"]["nullable"]
    indexes = {index["name"]: index["column_names"]
               for index in inspector.get_indexes("application_status_events")}
    assert indexes["ix_status_events_app_at"] == ["application_id", "at"]
    (link,) = inspector.get_foreign_keys("application_status_events")
    assert link["referred_table"] == "applications" and link["options"]["ondelete"] == "CASCADE"


def _job_and_application(db, **fields):
    job = models.Job(id=uuid.uuid4(), raw_text="Example role", raw_text_hash=uuid.uuid4().hex)
    db.add(job)
    db.flush()
    application = models.Application(id=uuid.uuid4(), job_id=job.id, base_resume="base", **fields)
    db.add(application)
    db.flush()
    return job, application


def _event(application, to_status="applied", **fields):
    return models.ApplicationStatusEvent(application_id=application.id, to_status=to_status,
                                         source="you", **fields)


def test_an_event_stores_an_aware_time_and_is_not_backfilled_by_default(db_session):
    _, application = _job_and_application(db_session)
    db_session.add(_event(application, from_status="draft"))
    db_session.commit()
    db_session.expire_all()
    (row,) = db_session.scalars(sa.select(models.ApplicationStatusEvent)).all()
    assert (row.from_status, row.to_status, row.source, row.backfilled) == ("draft", "applied", "you", False)
    assert row.at.tzinfo is not None


def test_deleting_an_application_deletes_its_events(db_session):
    _, application = _job_and_application(db_session)
    db_session.add_all([_event(application), _event(application, "interviewing")])
    db_session.commit()
    db_session.delete(application)
    db_session.commit()
    assert db_session.scalar(sa.select(sa.func.count()).select_from(models.ApplicationStatusEvent)) == 0


def test_deleting_a_job_deletes_its_applications_events(db_session):
    job, application = _job_and_application(db_session)
    db_session.add(_event(application))
    db_session.commit()
    db_session.delete(job)
    db_session.commit()
    assert db_session.scalar(sa.select(sa.func.count()).select_from(models.ApplicationStatusEvent)) == 0


def test_an_event_belongs_to_its_applications_job_under_sync(db_session, tmp_path, monkeypatch):
    """The flush guard ties the row to its job: allowed on this copy's job and stamped, refused on a
    replica (SYSTEM.md {#inv-flush-guard})."""
    monkeypatch.setattr(settings, "settings_dir", tmp_path / "settings")
    monkeypatch.setattr(settings, "sync_key_file", tmp_path / "absent-key")
    monkeypatch.setattr(settings, "sync_remote_url", "")
    job, application = _job_and_application(db_session)
    replica = models.Job(id=uuid.uuid4(), raw_text="Other role", raw_text_hash=uuid.uuid4().hex,
                         owner_machine="other-machine")
    db_session.add(replica)
    db_session.flush()
    theirs = models.Application(id=uuid.uuid4(), job_id=replica.id, base_resume="base")
    db_session.add(theirs)
    db_session.commit()
    sync_status.create_key()

    before = job.sync_rev
    db_session.add(_event(application))
    db_session.commit()
    assert job.sync_rev > before

    db_session.add(_event(theirs))
    try:
        db_session.flush()
    except hooks.NotOwnedHere:
        db_session.rollback()
    else:
        raise AssertionError("an event on the other copy's job was written")


# ---------------------------------------------------------------------------- the migration


def _seed_before(path: Path) -> dict[str, str | None]:
    """Applications at the revision before the log: three with a status, two without."""
    statuses = {"applied": "applied", "draft": "draft", "rejected": "rejected", "none-a": None,
                "none-b": None}
    with closing(sqlite3.connect(path)) as db:
        job_id = uuid.uuid4().hex
        db.execute("INSERT INTO jobs (id, raw_text, raw_text_hash) VALUES (?, 'jd', 'hash-1')",
                   (job_id,))
        for name, value in statuses.items():
            db.execute(
                "INSERT INTO applications (id, job_id, base_resume, status, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (uuid.uuid4().hex, job_id, name, value, STAMP, f"2026-09-0{len(name) % 9 + 1} 08:30:00.000000"),
            )
        db.commit()
    return statuses


def test_the_migration_backfills_one_marked_event_per_status_and_round_trips(tmp_path):
    path = tmp_path / "events.sqlite3"
    cfg = _config(path)
    command.upgrade(cfg, BEFORE)
    statuses = _seed_before(path)

    command.upgrade(cfg, REVISION)
    with closing(sqlite3.connect(path)) as db:
        rows = db.execute(
            "SELECT a.base_resume, e.from_status, e.to_status, e.at = a.updated_at, e.source,"
            " e.backfilled, length(e.id) FROM application_status_events e"
            " JOIN applications a ON a.id = e.application_id ORDER BY a.base_resume"
        ).fetchall()
    with_status = sorted(name for name, value in statuses.items() if value)
    assert [row[0] for row in rows] == with_status
    for name, from_status, to_status, same_time, source, backfilled, id_length in rows:
        assert (from_status, to_status, same_time, source, backfilled, id_length) == (
            None, statuses[name], 1, "backfill", 1, 32), name

    command.downgrade(cfg, BEFORE)
    with closing(sqlite3.connect(path)) as db:
        assert "application_status_events" not in _tables(db)
        assert db.execute("SELECT count(*) FROM applications").fetchone() == (len(statuses),)

    command.upgrade(cfg, "head")
    with closing(sqlite3.connect(path)) as db:
        assert "application_status_events" in _tables(db)
        assert db.execute("SELECT count(*) FROM application_status_events").fetchone() == (
            len(with_status),)
