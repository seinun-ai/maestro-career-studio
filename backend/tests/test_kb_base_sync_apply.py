"""One-click apply of the base→KB classification ladder."""

import json
from datetime import UTC, datetime

from sqlalchemy import select

from app.models.base_resume import BaseResume
from app.models.career_kb import KBEntity, KBPoint, KBPortLog, KBProfile
from app.services import kb_base_sync
from tests.test_kb_base_sync_classify import (
    _drifting_resume,
    _exp_entity,
    _port_log,
    _resume,
    _seed_base,
)


def test_apply_creates_drafts_with_base_sync_origin_and_user_authored_provenance(
    db_session, tmp_path, monkeypatch
):
    _exp_entity(db_session, text="Built the ingestion pipeline")
    data = _resume(
        experience=[
            {
                "company": "Acme",
                "role": "Engineer",
                "start_date": "2021",
                "bullets": [
                    "Built the ingestion pipeline",
                    "Negotiated a net-new vendor contract worth two million",
                ],
            }
        ]
    )
    _seed_base(db_session, tmp_path, monkeypatch, data)
    result = kb_base_sync.apply(db_session, "hybrid")
    points = db_session.scalars(select(KBPoint).where(KBPoint.origin == "base_sync")).all()
    assert len(points) == 1
    assert points[0].state == "draft"
    assert points[0].provenance == "user_authored"
    assert points[0].text == "Negotiated a net-new vendor contract worth two million"
    assert result["created"] == 1


def test_apply_creates_missing_entities_via_identity_keys(db_session, tmp_path, monkeypatch):
    data = _resume(
        experience=[
            {
                "company": "OtherCo",
                "role": "Lead",
                "start_date": "2024",
                "end_date": "2025",
                "bullets": ["Stood up a greenfield billing service"],
            }
        ],
        education=[{"institution": "State U", "degree": "BS CS"}],
        certifications=["AWS SAA"],
    )
    _seed_base(db_session, tmp_path, monkeypatch, data)
    kb_base_sync.apply(db_session, "hybrid")
    ents = db_session.scalars(select(KBEntity)).all()
    by_kind = {e.kind: e for e in ents}
    assert by_kind["experience"].org == "OtherCo"
    assert by_kind["experience"].title == "Lead"
    assert by_kind["education"].org == "State U"
    assert by_kind["certification"].title == "AWS SAA"
    point = db_session.scalars(select(KBPoint)).one()
    assert point.entity_id == by_kind["experience"].id
    assert point.origin == "base_sync"


def test_drift_writes_from_source_portlog_and_no_point(db_session, tmp_path, monkeypatch):
    ent = _exp_entity(db_session, text="machine learning")
    before = db_session.query(KBPoint).count()
    data = _resume(
        experience=[
            {
                "company": "Acme",
                "role": "Engineer",
                "start_date": "2021",
                "bullets": ["shipped ml models to production"],
            }
        ]
    )
    _seed_base(db_session, tmp_path, monkeypatch, data)
    result = kb_base_sync.apply(db_session, "hybrid")
    assert db_session.query(KBPoint).count() == before
    log = db_session.scalars(select(KBPortLog)).one()
    assert log.direction == "from_source"
    assert log.resume_kind == "base"
    assert log.resume_key == "hybrid"
    assert log.ported_text == "shipped ml models to production"
    assert log.source_text == "shipped ml models to production"
    assert log.point_id is not None
    assert log.entity_id == ent.id
    assert result["drifted"] == 1


def test_skills_merge_additively_never_remove(db_session, tmp_path, monkeypatch):
    db_session.add(
        KBProfile(
            id=1,
            skills_json=[
                {"category": "Languages", "items": ["Python", "Go"]},
            ],
        )
    )
    db_session.flush()
    data = _resume(skills=[{"category": "Languages", "items": ["Python", "Rust"]}])
    _seed_base(db_session, tmp_path, monkeypatch, data)
    kb_base_sync.apply(db_session, "hybrid")
    profile = db_session.get(KBProfile, 1)
    items = profile.skills_json[0]["items"]
    assert "Go" in items
    assert "Rust" in items
    assert "Python" in items


def test_apply_stamps_last_kb_synced_at(db_session, tmp_path, monkeypatch):
    data = _resume()
    row = _seed_base(db_session, tmp_path, monkeypatch, data)
    assert row.last_kb_synced_at is None
    before = datetime.now(UTC)
    kb_base_sync.apply(db_session, "hybrid")
    db_session.refresh(row)
    assert row.last_kb_synced_at is not None
    assert row.last_kb_synced_at >= before


def test_apply_twice_is_a_noop(db_session, tmp_path, monkeypatch):
    data = _resume(
        experience=[
            {
                "company": "OtherCo",
                "role": "Lead",
                "start_date": "2024",
                "bullets": ["Stood up a greenfield billing service"],
            }
        ],
        skills=[{"category": "Cloud", "items": ["AWS"]}],
    )
    _seed_base(db_session, tmp_path, monkeypatch, data)
    first = kb_base_sync.apply(db_session, "hybrid")
    assert first["created"] == 1
    n_points = db_session.query(KBPoint).count()
    n_ents = db_session.query(KBEntity).count()
    n_logs = db_session.query(KBPortLog).count()
    second = kb_base_sync.apply(db_session, "hybrid")
    assert second["created"] == 0
    assert second["drifted"] == 0
    assert second["skills"] == []
    assert db_session.query(KBPoint).count() == n_points
    assert db_session.query(KBEntity).count() == n_ents
    assert db_session.query(KBPortLog).count() == n_logs


def test_apply_twice_on_a_drifting_resume_is_a_noop(db_session, tmp_path, monkeypatch):
    """The 'recorded' tier must be skipped like 'in_sync': no second drift
    note, and no consolation draft point for the bullet that already drifted."""
    _exp_entity(db_session, text="machine learning")
    _seed_base(db_session, tmp_path, monkeypatch, _drifting_resume())
    first = kb_base_sync.apply(db_session, "hybrid")
    assert first["drifted"] == 1
    n_points = db_session.query(KBPoint).count()
    n_logs = db_session.query(KBPortLog).count()

    second = kb_base_sync.apply(db_session, "hybrid")
    assert second["created"] == 0
    assert second["drifted"] == 0
    assert second["skipped"] == []
    assert db_session.query(KBPoint).count() == n_points
    assert db_session.query(KBPortLog).count() == n_logs


def test_legacy_null_direction_row_blocks_a_duplicate_note(
    db_session, tmp_path, monkeypatch
):
    """Pre-migration rows carry direction NULL, but they still record the
    association, so apply must not write a second row for it."""
    ent = _exp_entity(db_session, text="machine learning")
    point = db_session.scalars(select(KBPoint)).one()
    _port_log(db_session, ent, point, direction=None)
    _seed_base(db_session, tmp_path, monkeypatch, _drifting_resume())

    result = kb_base_sync.apply(db_session, "hybrid")
    assert result["drifted"] == 0
    assert result["skipped"] == []
    assert db_session.query(KBPortLog).count() == 1


def test_removed_base_bullet_changes_nothing_in_kb(db_session, tmp_path, monkeypatch):
    data = _resume(
        experience=[
            {
                "company": "OtherCo",
                "role": "Lead",
                "start_date": "2024",
                "bullets": ["Stood up a greenfield billing service"],
            }
        ]
    )
    _seed_base(db_session, tmp_path, monkeypatch, data)
    kb_base_sync.apply(db_session, "hybrid")
    point_id = db_session.scalars(select(KBPoint)).one().id
    data2 = _resume(experience=[])
    (tmp_path / "hybrid.json").write_text(json.dumps(data2), encoding="utf-8")
    row = db_session.get(BaseResume, "hybrid")
    row.data_json = data2
    db_session.flush()
    kb_base_sync.apply(db_session, "hybrid")
    assert db_session.get(KBPoint, point_id) is not None
    assert db_session.query(KBPoint).count() == 1
