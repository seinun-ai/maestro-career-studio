"""The conftest guard: `_validate_test_db_url` refuses anything that could be
real data before a single DELETE runs.

Every case is a URL that a shell could plausibly carry into TEST_DATABASE_URL:
unset, the old Postgres default, an in-memory database (per-connection, so the
app and the fixtures would never see the same tables), anything under the
repo's data/ mount however it is spelled, a file named like the dev database,
and the app's own database as Settings derives it.
"""
from pathlib import Path

import pytest

from tests.conftest import REPO_DATA_DIR, _validate_test_db_url


def _sqlite(path: Path) -> str:
    return f"sqlite:///{path}"


@pytest.mark.parametrize(
    ("url", "match"),
    [
        pytest.param(None, "not set", id="unset"),
        pytest.param("", "not set", id="empty"),
        pytest.param(
            "postgresql+psycopg://app@127.0.0.1/maestro_cs_test", "must be a sqlite", id="postgres"
        ),
        pytest.param("sqlite://", "must name a FILE", id="no-file"),
        pytest.param("sqlite:///:memory:", "must name a FILE", id="memory"),
        pytest.param(_sqlite(REPO_DATA_DIR / "x.sqlite3"), "looks like real data", id="data-dir"),
        pytest.param(
            _sqlite(REPO_DATA_DIR / "nested" / "deeper" / "x.sqlite3"),
            "looks like real data",
            id="data-dir-nested",
        ),
        # Pins the .resolve(): spelled through `..`, the path is still data/.
        pytest.param(
            _sqlite(REPO_DATA_DIR / ".." / "data" / "x.sqlite3"),
            "looks like real data",
            id="data-dir-via-dotdot",
        ),
        pytest.param("sqlite:////tmp/maestro_cs.sqlite3", "looks like real data", id="stem-maestro_cs"),
        pytest.param("sqlite:////tmp/resume_auto.sqlite3", "looks like real data", id="stem-resume_auto"),
        pytest.param(
            "sqlite:////tmp/career_studio.sqlite3", "looks like real data", id="stem-career_studio"
        ),
    ],
)
def test_refuses(url, match):
    with pytest.raises(RuntimeError, match=match):
        _validate_test_db_url(url)


def test_refuses_the_apps_own_database():
    from app.config import settings

    with pytest.raises(RuntimeError, match="app's own database"):
        _validate_test_db_url(settings.database_url)


def test_accepts_a_throwaway_file_unchanged(tmp_path):
    url = _sqlite(tmp_path / "ok.sqlite3")
    assert _validate_test_db_url(url) == url
