"""seeding._import_legacy_postgres: the first-boot import hook.

The importer itself is covered in tests/tools. This is the hook's contract:
it runs between the migrations and the seed, it is inert without a legacy
URL, soft outcomes let the app boot, and ANY failure aborts startup (fails
closed) so the still-empty file is retried at the next boot instead of being
filled with demo rows.
"""
import logging
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.config import settings
from app.services import seeding
from app.tools import migrate_from_postgres as tool

LEGACY_URL = "postgresql://app:app@nowhere.invalid:5432/legacy"


@pytest.fixture
def legacy_url(monkeypatch):
    monkeypatch.setattr(settings, "legacy_database_url", LEGACY_URL)
    return LEGACY_URL


def _stub_import(monkeypatch, *, outcome=None, error=None):
    calls = []

    def fake(source_url, target_url, marker, *, log, upgrade_source=True):
        calls.append((source_url, target_url, marker))
        if error is not None:
            raise error
        return outcome

    monkeypatch.setattr(tool, "import_if_needed", fake)
    return calls


def test_run_startup_imports_between_the_migrations_and_the_seed(monkeypatch):
    calls = []
    monkeypatch.setattr(seeding, "run_migrations", lambda: calls.append("migrate"))
    monkeypatch.setattr(seeding, "_import_legacy_postgres", lambda: calls.append("import"))

    class FakeSession:
        def __enter__(self):
            calls.append("open")
            return self

        def __exit__(self, exc_type, exc, tb):
            calls.append("close")

    monkeypatch.setattr(seeding, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(seeding, "seed_startup_data", lambda session: calls.append("seed"))

    seeding.run_startup()

    assert calls == ["migrate", "import", "open", "seed", "close"]


def test_hook_is_inert_without_a_legacy_url(monkeypatch):
    monkeypatch.setattr(settings, "legacy_database_url", "")
    calls = _stub_import(monkeypatch, outcome="imported")

    seeding._import_legacy_postgres()

    assert calls == []


def test_hook_targets_the_app_database_and_the_marker_under_data_dir(legacy_url, monkeypatch):
    calls = _stub_import(monkeypatch, outcome="already-imported")

    seeding._import_legacy_postgres()

    assert calls == [
        (legacy_url, settings.database_url, Path(settings.data_dir) / tool.MARKER_NAME)
    ]


@pytest.mark.parametrize(
    "outcome",
    ["source-unreachable", "source-empty", "already-imported", "target-not-empty", "imported"],
)
def test_soft_outcomes_let_the_app_boot(legacy_url, monkeypatch, outcome):
    _stub_import(monkeypatch, outcome=outcome)

    seeding._import_legacy_postgres()


def test_imported_logs_the_handover_warning(legacy_url, monkeypatch, caplog):
    _stub_import(monkeypatch, outcome="imported")

    with caplog.at_level(logging.WARNING, logger=seeding.logger.name):
        seeding._import_legacy_postgres()

    assert "Imported your Postgres database" in caplog.text


@pytest.mark.parametrize(
    "error",
    [
        tool.ExportError("import verification failed for ['jobs']; nothing was committed"),
        sa.exc.IntegrityError("INSERT INTO jobs", {}, Exception("NOT NULL constraint failed")),
        sa.exc.OperationalError("SELECT 1", {}, Exception("database is locked")),
        ValueError("naive datetime bound to a UTCDateTime column"),
    ],
    ids=["verification-mismatch", "integrity", "operational", "type-coercion"],
)
def test_any_import_failure_aborts_startup(legacy_url, monkeypatch, caplog, error):
    _stub_import(monkeypatch, error=error)

    with caplog.at_level(logging.ERROR, logger=seeding.logger.name):
        with pytest.raises(RuntimeError, match="retries at the next boot") as info:
            seeding._import_legacy_postgres()

    assert info.value.__cause__ is error
    assert "unset LEGACY_DATABASE_URL" in str(info.value)
    assert "refusing to boot on an empty file" in caplog.text
