import json
from pathlib import Path

from app.schemas.resume import ResumeData


def test_all_base_resumes_parse():
    root = Path(__file__).parent.parent.parent / "base_resumes"
    paths = sorted(root.glob("*.json"))

    assert len(paths) >= 1

    for path in paths:
        ResumeData.model_validate(json.loads(path.read_text()))


def test_archived_slug_is_not_selectable_but_stays_active(db_session):
    """Archive removes a base from CHOICE sets, never from resolution."""
    from datetime import UTC, datetime

    from app.models.base_resume import BaseResume
    from app.services import base_resume_data

    db_session.add(BaseResume(slug="kept", data_json={}))
    db_session.add(
        BaseResume(slug="stale_track", data_json={}, archived_at=datetime.now(UTC))
    )
    db_session.commit()

    assert base_resume_data.selectable_base_resume_slugs(db_session) == ["kept"]
    # active_ is the RESOLUTION gate — archived rows must remain in it, or the
    # archived resume's own editor and version history 404.
    assert base_resume_data.active_base_resume_slugs(db_session) == [
        "kept",
        "stale_track",
    ]
