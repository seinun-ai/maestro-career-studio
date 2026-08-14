"""Comprehensive tests for Career KB Custom Sections (kind='extra')."""

from typing import Any
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from app.models.career_kb import KBEntity, KBPoint, KBProfile
from app.schemas.career_kb import KBEntityCreate, KBEntityPatch
from app.schemas.resume import ResumeData, TITLE_COLLISION_MESSAGE
from app.services import career_kb, kb_consolidation
from app.services.extra_section_presets import PRESETS


@pytest.fixture
def client(db_session):
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def no_llm(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("LLM was called on deterministic path")

    monkeypatch.setattr("app.services.llm.call_openai", boom)


def _make_resume(**kwargs: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "contact": {"name": "Riley Doe", "email": "riley@example.com"},
        "summary": "Experienced engineer",
        "skills": [{"category": "Languages", "items": ["Python", "Rust"]}],
        "experience": [],
        "projects": [],
        "education": [],
        "certifications": [],
        "extra_sections": [],
    }
    base.update(kwargs)
    return ResumeData.model_validate(base).model_dump(mode="json")


def test_extra_section_preset_catalog_endpoint(client):
    """GET /api/kb/extra-section-presets serves the 8 canonical backend presets."""
    r = client.get("/api/kb/extra-section-presets")
    assert r.status_code == 200, r.text
    presets = r.json()
    assert len(presets) == len(PRESETS)
    assert len(presets) == 8

    preset_keys = [p["key"] for p in presets]
    expected_keys = [p["key"] for p in PRESETS]
    assert preset_keys == expected_keys
    assert "publications" in preset_keys
    assert "awards" in preset_keys
    assert "volunteer" in preset_keys
    assert "clearance" in preset_keys


def test_extra_entity_schema_validations():
    """Validates kind='extra' rules and core section collisions."""
    # Valid entries-type
    ent = KBEntityCreate(
        kind="extra",
        title="Paper 1",
        section_key="publications",
        section_type="entries",
        section_title="Publications",
    )
    assert ent.section_key == "publications"
    assert ent.detail["section_key"] == "publications"
    assert ent.detail["section_type"] == "entries"

    # Valid bullets-type
    ent_b = KBEntityCreate(
        kind="extra",
        title="Awards",
        section_key="awards",
        section_type="bullets",
        section_title="Awards & Honors",
    )
    assert ent_b.section_type == "bullets"

    # Collides with core section key
    with pytest.raises(ValidationError) as exc:
        KBEntityCreate(
            kind="extra",
            title="My Skills",
            section_key="skills",
            section_type="bullets",
            section_title="Skills",
        )
    assert "collides with the core 'skills' section" in str(exc.value)

    # Collides with core section title
    with pytest.raises(ValidationError) as exc:
        KBEntityCreate(
            kind="extra",
            title="Experience",
            section_key="my_exp",
            section_type="entries",
            section_title="Experience",
        )
    assert TITLE_COLLISION_MESSAGE in str(exc.value)

    # Disallows extra fields when kind != 'extra'
    with pytest.raises(ValidationError) as exc:
        KBEntityCreate(
            kind="project",
            title="Proj",
            section_key="custom_proj",
        )
    assert "only valid when kind == 'extra'" in str(exc.value)


def test_extra_entity_patch_validation():
    patch_valid = KBEntityPatch(section_key="new_key", section_title="New Title")
    assert patch_valid.section_key == "new_key"

    with pytest.raises(ValidationError) as exc:
        KBEntityPatch(section_key="experience")
    assert "collides with core section" in str(exc.value)


def test_bullets_type_single_entity_contract(db_session, no_llm):
    """Multiple bullets on a bullets-type extra section map to a SINGLE KBEntity."""
    resume = _make_resume(
        extra_sections=[
            {
                "type": "bullets",
                "key": "awards",
                "title": "Awards & Honors",
                "bullets": [
                    "Best Innovation Award 2023",
                    "Top Performer Q3 2024",
                ],
            }
        ]
    )

    report = kb_consolidation.consolidate_deterministic(db_session, [("r1", resume)])
    assert report.entities_created == 1
    assert report.points_created == 2

    entities = db_session.scalars(select(KBEntity).where(KBEntity.kind == "extra")).all()
    assert len(entities) == 1
    entity = entities[0]
    assert entity.title == "Awards & Honors"
    assert entity.detail_json["section_key"] == "awards"
    assert entity.detail_json["section_type"] == "bullets"
    assert len(entity.points) == 2
    point_texts = {p.text for p in entity.points}
    assert point_texts == {"Best Innovation Award 2023", "Top Performer Q3 2024"}


def test_extra_sections_round_trip_compose(db_session, client, no_llm):
    """Round-trip: resume with extras -> consolidate -> approve points -> compose -> matching extras."""
    original_resume = _make_resume(
        extra_sections=[
            {
                "type": "entries",
                "key": "publications",
                "title": "Publications",
                "entries": [
                    {
                        "heading": "Transformers in Production",
                        "subheading": "ACM 2024",
                        "date": "2024-05",
                        "bullets": ["Presented scaling results."],
                    },
                    {
                        "heading": "Efficient Attention",
                        "subheading": "arXiv",
                        "date": "2023-11",
                        "bullets": ["Benchmarked quadratic vs linear attention."],
                    },
                ],
            },
            {
                "type": "bullets",
                "key": "clearance",
                "title": "Security Clearance",
                "bullets": ["Top Secret / SCI active."],
            },
        ]
    )

    # 1. Ingest via consolidation
    report = kb_consolidation.consolidate_deterministic(db_session, [("base_1", original_resume)])
    assert report.entities_created == 3  # 2 publication entries + 1 clearance section
    assert report.points_created == 3

    # 2. Approve all points
    points = db_session.scalars(select(KBPoint)).all()
    for p in points:
        p.state = "approved"
    db_session.commit()

    # 3. Compose
    body = client.get("/api/kb/compose").json()
    composed_extras = body["extra_sections"]
    assert len(composed_extras) == 2

    pub_sec = next(s for s in composed_extras if s["key"] == "publications")
    assert pub_sec["type"] == "entries"
    assert pub_sec["title"] == "Publications"
    assert len(pub_sec["entries"]) == 2
    headings = {e["heading"] for e in pub_sec["entries"]}
    assert headings == {"Transformers in Production", "Efficient Attention"}
    entry_trans = next(e for e in pub_sec["entries"] if e["heading"] == "Transformers in Production")
    assert entry_trans["subheading"] == "ACM 2024"
    assert entry_trans["date"] == "2024-05"
    assert entry_trans["bullets"] == ["Presented scaling results."]

    clearance_sec = next(s for s in composed_extras if s["key"] == "clearance")
    assert clearance_sec["type"] == "bullets"
    assert clearance_sec["title"] == "Security Clearance"
    assert clearance_sec["bullets"] == ["Top Secret / SCI active."]


def test_rerun_is_idempotent_for_extra_sections(db_session, no_llm):
    """Re-ingesting the same resume must MERGE extras, never duplicate them.

    Reviewer-added: the identity index for kind="extra" entities
    (`_existing_extra_index`) was unpinned — emptying it left every other
    extras test green while a re-run would have minted duplicate entities.
    """
    resume = _make_resume(
        extra_sections=[
            {
                "type": "entries",
                "key": "volunteer",
                "title": "Volunteer Experience",
                "entries": [
                    {
                        "heading": "Habitat for Humanity",
                        "subheading": "Volunteer Builder",
                        "bullets": ["Built houses."],
                    },
                    {
                        "heading": "Food Bank",
                        "bullets": ["Sorted donations."],
                    },
                ],
            },
            {
                "type": "bullets",
                "key": "awards",
                "title": "Awards & Honors",
                "bullets": ["Best Innovation Award 2023"],
            },
        ]
    )

    first = kb_consolidation.consolidate_deterministic(db_session, [("r1", resume)])
    second = kb_consolidation.consolidate_deterministic(db_session, [("r1", resume)])

    entities = db_session.scalars(select(KBEntity).where(KBEntity.kind == "extra")).all()
    assert len(entities) == 3  # 2 volunteer entries + 1 awards section
    assert first.entities_created == 3
    assert second.entities_created == 0
    assert second.points_created == 0
    points = db_session.scalars(select(KBPoint)).all()
    assert len(points) == 3


def test_frontend_preset_copy_matches_backend_catalog():
    """The TS `SECTION_PRESETS` mirror must carry the backend catalog verbatim.

    Cross-boundary duplication needs a contract test, not a deletion
    (SYSTEM.md §13 doctrine; precedent: the extension policy deny-list test).
    The 3-item frontend copy silently drifted from the 8-item backend catalog
    once already — this pins every (key, title, type) triple.
    """
    from pathlib import Path
    import re

    ts_path = (
        Path(__file__).resolve().parents[2] / "frontend" / "lib" / "extra-sections.ts"
    )
    ts_source = ts_path.read_text(encoding="utf-8")
    ts_entries = re.findall(
        r'\{\s*id:\s*"([^"]+)",\s*label:\s*"([^"]+)",\s*title:\s*"([^"]+)",\s*type:\s*"([^"]+)"',
        ts_source,
    )
    ts_by_id = {m[0]: {"title": m[2], "type": m[3]} for m in ts_entries}

    backend_by_key = {p["key"]: p for p in PRESETS}
    assert set(ts_by_id) == set(backend_by_key), (
        "frontend SECTION_PRESETS ids diverged from backend extra_section_presets"
    )
    for key, preset in backend_by_key.items():
        assert ts_by_id[key]["title"] == preset["title"], key
        assert ts_by_id[key]["type"] == preset["type"], key


def test_compose_warns_and_skips_cross_type_key_collision(db_session, no_llm, caplog):
    """Two extra entities sharing a section_key but disagreeing on type: the
    first composes, the second is skipped WITH a warning — never silently."""
    import logging

    profile = KBProfile(id=1, contact_json={"name": "R", "email": "r@x.com"})
    db_session.add(profile)
    db_session.add(
        KBEntity(
            kind="extra",
            title="Awards & Honors",
            status="completed",
            detail_json={
                "section_key": "awards",
                "section_type": "bullets",
                "section_title": "Awards & Honors",
            },
        )
    )
    db_session.add(
        KBEntity(
            kind="extra",
            title="Rogue Entry",
            status="completed",
            detail_json={
                "section_key": "awards",
                "section_type": "entries",
                "section_title": "Awards & Honors",
            },
        )
    )
    db_session.flush()

    with caplog.at_level(logging.WARNING, logger="app.services.career_kb"):
        data = career_kb.compose_resume_data(db_session)

    sections = [s for s in data["extra_sections"] if s["key"] == "awards"]
    assert len(sections) == 1
    assert sections[0]["type"] == "bullets"
    assert any("already composed as type" in r.message for r in caplog.records)
