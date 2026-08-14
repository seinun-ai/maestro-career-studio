"""LLM-free consolidate_deterministic() — identity merge, verbatim points, ids.

A new entry point. Existing consolidate() tests stay untouched; this file
covers only the deterministic path used by MCP onboarding ingest.
"""

import pytest
from sqlalchemy import select

from app.models.career_kb import KBEntity, KBPoint, KBPortLog
from app.services.career_kb import get_or_create_profile
from app.services.kb_consolidation import consolidate_deterministic


def _resume(**sections):
    base = {
        "contact": {"name": "A", "email": "a@x.com"},
        "summary": None,
        "skills": [],
        "experience": [],
        "projects": [],
        "education": [],
        "certifications": [],
    }
    base.update(sections)
    return base


def _boom(*_a, **_k):
    raise AssertionError("call_openai must not be invoked on the deterministic path")


@pytest.fixture
def no_llm(monkeypatch):
    monkeypatch.setattr("app.services.llm.call_openai", _boom)


def test_identity_merge_experience_and_projects_across_sources(db_session, no_llm):
    r1 = _resume(
        experience=[{
            "company": "Acme", "role": "Engineer", "start_date": "2021",
            "bullets": ["Shipped the pipeline"],
        }],
        projects=[{"name": "Orbit", "bullets": ["Built Orbit"]}],
    )
    r2 = _resume(
        experience=[{
            "company": "acme", "role": "engineer", "start_date": "2021",
            "bullets": ["Owned on-call"],
        }],
        projects=[{"name": "orbit", "bullets": ["Documented Orbit"]}],
    )
    report = consolidate_deterministic(db_session, [("ds", r1), ("ml", r2)])

    ents = db_session.scalars(select(KBEntity)).all()
    by_kind = {e.kind: e for e in ents}
    assert set(by_kind) == {"experience", "project"}
    assert len(ents) == 2
    exp_pts = [p for p in db_session.scalars(select(KBPoint)) if p.entity_id == by_kind["experience"].id]
    proj_pts = [p for p in db_session.scalars(select(KBPoint)) if p.entity_id == by_kind["project"].id]
    assert {p.text for p in exp_pts} == {"Shipped the pipeline", "Owned on-call"}
    assert {p.text for p in proj_pts} == {"Built Orbit", "Documented Orbit"}
    created = [e for e in report.entities if e.created]
    assert len(created) == 2
    assert {e.kind for e in created} == {"experience", "project"}
    assert all(e.id for e in report.entities)
    assert all(p.id and p.entity_id and p.text for p in report.points)
    assert len(report.points) == 4


def test_exact_and_normalized_bullet_dedup_within_batch(db_session, no_llm):
    r1 = _resume(projects=[{"name": "Orbit", "bullets": ["Built the ingestion pipeline"]}])
    r2 = _resume(projects=[{"name": "Orbit", "bullets": ["built  the ingestion pipeline"]}])
    report = consolidate_deterministic(db_session, [("a", r1), ("b", r2)])

    pts = db_session.scalars(select(KBPoint)).all()
    assert len(pts) == 1
    assert pts[0].text == "Built the ingestion pipeline"
    assert report.duplicates_skipped == 1
    assert len(report.points) == 1


def test_near_duplicates_both_land(db_session, no_llm):
    r1 = _resume(projects=[{"name": "Orbit", "bullets": ["Increased recall by 30%"]}])
    r2 = _resume(projects=[{"name": "Orbit", "bullets": ["Boosted recall substantially"]}])
    consolidate_deterministic(db_session, [("a", r1), ("b", r2)])

    pts = db_session.scalars(select(KBPoint)).all()
    assert {p.text for p in pts} == {"Increased recall by 30%", "Boosted recall substantially"}


def test_rerun_is_idempotent_no_duplicate_entities_or_points(db_session, no_llm):
    r = _resume(
        experience=[{
            "company": "Acme", "role": "Engineer", "start_date": "2021",
            "bullets": ["Shipped the pipeline"],
        }],
        education=[{"institution": "MIT", "degree": "BS CS"}],
        certifications=["AWS SAA"],
    )
    first = consolidate_deterministic(db_session, [("ds", r)])
    second = consolidate_deterministic(db_session, [("ds", r)])

    ents = db_session.scalars(select(KBEntity)).all()
    pts = db_session.scalars(select(KBPoint)).all()
    assert len(ents) == 3  # experience + education + cert
    assert len(pts) == 1
    assert first.entities_created == 3
    assert second.entities_created == 0
    assert second.entities_matched == 3
    assert second.points == []
    assert second.points_created == 0
    assert all(not e.created for e in second.entities)


def test_profile_seeding_is_non_clobbering_last_source_wins(db_session, no_llm):
    r1 = _resume(
        skills=[{"category": "ML Ops", "items": ["Docker"]}],
        summary="First summary",
    )
    r1["contact"] = {"name": "First", "email": "first@x.com"}
    r2 = _resume(
        skills=[{"category": "MLOps", "items": ["MLflow", "Docker"]}],
        summary="Latest summary",
    )
    r2["contact"] = {"name": "Second", "email": "second@x.com"}
    consolidate_deterministic(db_session, [("first", r1), ("latest", r2)])

    profile = get_or_create_profile(db_session)
    # Blank profile: last source wins.
    assert profile.contact_json.get("name") == "Second"
    assert profile.summary == "Latest summary"
    cats = {g["category"] for g in profile.skills_json}
    assert cats == {"ML Ops", "MLOps"}

    r3 = _resume(summary="Must not clobber")
    r3["contact"] = {"name": "Third", "email": "third@x.com"}
    consolidate_deterministic(db_session, [("later", r3)])
    profile = get_or_create_profile(db_session)
    assert profile.contact_json.get("name") == "Second"
    assert profile.summary == "Latest summary"


def test_new_points_are_drafts_with_provenance(db_session, no_llm):
    r = _resume(projects=[{"name": "Orbit", "bullets": ["Built Orbit"]}])
    report = consolidate_deterministic(
        db_session, [("ds", r)], origin="mcp", origin_detail="Claude Desktop",
    )

    pts = db_session.scalars(select(KBPoint)).all()
    assert len(pts) == 1
    pt = pts[0]
    # An agent transcribed this; kb_approve_points is the gate, not this write.
    assert pt.state == "draft"
    assert pt.approved_at is None
    # origin 'mcp' (not 'consolidated') is what puts it in the /career timeline.
    assert pt.origin == "mcp"
    assert pt.origin_detail == "Claude Desktop"
    assert pt.merge_sources_json == [
        {"resume_key": "ds", "section": "projects", "text": "Built Orbit"}
    ]
    assert report.points_created == 1
    entity = db_session.scalars(select(KBEntity)).one()
    assert entity.origin == "mcp"
    assert entity.origin_detail == "Claude Desktop"


def test_web_origin_keeps_consolidated_point_origin(db_session, no_llm):
    r = _resume(projects=[{"name": "Orbit", "bullets": ["Built Orbit"]}])
    consolidate_deterministic(db_session, [("ds", r)])
    pt = db_session.scalars(select(KBPoint)).one()
    assert pt.origin == "consolidated"
    assert db_session.scalars(select(KBEntity)).one().origin is None


def test_port_logs_are_written_for_every_source_bullet(db_session, no_llm):
    r1 = _resume(projects=[{"name": "Orbit", "bullets": ["Built Orbit"]}])
    r2 = _resume(projects=[{"name": "Orbit", "bullets": ["Built Orbit"]}])
    consolidate_deterministic(db_session, [("ds", r1), ("ml", r2)])

    point = db_session.scalars(select(KBPoint)).one()
    logs = db_session.scalars(select(KBPortLog)).all()
    assert {(log.resume_key, log.section, log.ported_text) for log in logs} == {
        ("ds", "projects", "Built Orbit"),
        ("ml", "projects", "Built Orbit"),
    }
    assert {log.point_id for log in logs} == {point.id}

    # Re-running the same sources must not accumulate duplicate log rows.
    consolidate_deterministic(db_session, [("ds", r1), ("ml", r2)])
    assert len(db_session.scalars(select(KBPortLog)).all()) == 2


@pytest.mark.parametrize(
    "section,entry",
    [
        ("education", {"institution": "MIT", "degree": None}),
        ("experience", {"company": "Acme", "role": "", "start_date": "2021",
                        "bullets": ["Shipped the pipeline"]}),
        ("projects", {"name": "", "bullets": ["Built the thing"]}),
    ],
    ids=["education-no-degree", "experience-blank-role", "project-blank-name"],
)
def test_rerun_is_idempotent_when_the_title_field_is_blank(db_session, no_llm, section, entry):
    """The _make_* builders substitute a fallback title for a blank source
    field; the existing-entity index has to reverse it or the second run forks
    a second entity and re-creates every point under it."""
    r = _resume(**{section: [entry]})
    consolidate_deterministic(db_session, [("ds", r)])
    entities_after_first = len(db_session.scalars(select(KBEntity)).all())
    points_after_first = len(db_session.scalars(select(KBPoint)).all())

    second = consolidate_deterministic(db_session, [("ds", r)])

    assert second.entities_created == 0
    assert second.entities_matched == 1
    assert second.points_created == 0
    assert len(db_session.scalars(select(KBEntity)).all()) == entities_after_first
    assert len(db_session.scalars(select(KBPoint)).all()) == points_after_first


def test_duplicate_identity_keys_always_match_the_same_entity(db_session, no_llm):
    """Two pre-existing rows can share an identity key (the LLM resolver can
    mint one this path would too). An unordered index makes which one wins a
    coin flip, so points scatter across both over successive ingests."""
    older = KBEntity(kind="project", title="Orbit", status="completed")
    db_session.add(older)
    db_session.commit()
    newer = KBEntity(kind="project", title="Orbit", status="completed")
    db_session.add(newer)
    db_session.commit()
    assert older.created_at <= newer.created_at

    for text in ("Built Orbit", "Shipped v2", "Wrote the docs"):
        consolidate_deterministic(
            db_session, [("ds", _resume(projects=[{"name": "Orbit", "bullets": [text]}]))],
        )

    landed = db_session.scalars(select(KBPoint)).all()
    assert len(landed) == 3
    assert {p.entity_id for p in landed} == {older.id}


def test_retired_points_are_not_resurrected(db_session, no_llm):
    r = _resume(projects=[{"name": "Orbit", "bullets": ["Built Orbit"]}])
    consolidate_deterministic(db_session, [("ds", r)])
    point = db_session.scalars(select(KBPoint)).one()
    point.state = "retired"
    db_session.commit()

    report = consolidate_deterministic(db_session, [("ds", r)])

    pts = db_session.scalars(select(KBPoint)).all()
    assert len(pts) == 1
    assert pts[0].state == "retired"
    assert report.points_created == 0
    assert report.duplicates_skipped == 1


def test_duplicates_skipped_counts_bullets_already_on_the_entity(db_session, no_llm):
    r = _resume(projects=[{"name": "Orbit", "bullets": ["Built Orbit", "Wrote the docs"]}])
    consolidate_deterministic(db_session, [("ds", r)])

    again = _resume(projects=[{"name": "Orbit", "bullets": ["Built Orbit", "Shipped v2"]}])
    report = consolidate_deterministic(db_session, [("ml", again)])

    assert report.points_created == 1
    assert report.duplicates_skipped == 1


def test_extra_sections_are_stored(db_session, no_llm):
    r = _resume(
        projects=[{"name": "Orbit", "bullets": ["Built Orbit"]}],
        extra_sections=[
            {
                "type": "bullets",
                "key": "publications",
                "title": "Publications",
                "bullets": ["A paper"],
            },
            {
                "type": "entries",
                "key": "volunteer",
                "title": "Volunteer Experience",
                "entries": [
                    {
                        "heading": "Habitat for Humanity",
                        "subheading": "Volunteer Builder",
                        "bullets": ["Built houses."],
                    }
                ],
            },
        ],
    )
    report = consolidate_deterministic(db_session, [("ds", r)])
    assert not any("extra_sections" in w for w in report.warnings)
    assert report.entities_created == 3  # Orbit (project) + publications (extra) + volunteer (extra)
    entities = db_session.scalars(select(KBEntity).where(KBEntity.kind == "extra")).all()
    assert len(entities) == 2
    pub_ent = next(e for e in entities if e.detail_json.get("section_key") == "publications")
    assert pub_ent.title == "Publications"
    assert pub_ent.detail_json["section_type"] == "bullets"
    assert len(pub_ent.points) == 1
    assert pub_ent.points[0].text == "A paper"

    vol_ent = next(e for e in entities if e.detail_json.get("section_key") == "volunteer")
    assert vol_ent.title == "Habitat for Humanity"
    assert vol_ent.org == "Volunteer Builder"
    assert vol_ent.detail_json["section_type"] == "entries"
    assert len(vol_ent.points) == 1
    assert vol_ent.points[0].text == "Built houses."


def test_no_warning_when_there_are_no_extra_sections(db_session, no_llm):
    r = _resume(projects=[{"name": "Orbit", "bullets": ["Built Orbit"]}])
    report = consolidate_deterministic(db_session, [("ds", r)])
    assert report.warnings == []


def test_points_landing_on_an_archived_entity_warn(db_session, no_llm):
    r = _resume(projects=[{"name": "Orbit", "bullets": ["Built Orbit"]}])
    consolidate_deterministic(db_session, [("ds", r)])
    entity = db_session.scalars(select(KBEntity)).one()
    entity.status = "archived"
    db_session.commit()

    report = consolidate_deterministic(
        db_session, [("ml", _resume(projects=[{"name": "Orbit", "bullets": ["Shipped v2"]}]))],
    )
    assert report.points_created == 1
    assert any("archived entity 'Orbit'" in w for w in report.warnings)


def test_report_entities_carry_title_and_org(db_session, no_llm):
    r = _resume(experience=[{
        "company": "Acme", "role": "Engineer", "start_date": "2021",
        "bullets": ["Shipped the pipeline"],
    }])
    report = consolidate_deterministic(db_session, [("ds", r)])
    ref = report.entities[0]
    assert ref.title == "Engineer"
    assert ref.org == "Acme"


def test_deterministic_path_never_calls_openai(db_session, no_llm):
    r = _resume(
        experience=[{
            "company": "Acme", "role": "Engineer", "start_date": "2021",
            "bullets": ["Did a thing"],
        }],
        projects=[{"name": "Orbit", "bullets": ["Built Orbit"]}],
        education=[{"institution": "MIT", "degree": "BS CS"}],
        certifications=["AWS SAA"],
    )
    report = consolidate_deterministic(db_session, [("a", r)])
    assert report.entities_created == 4
    assert report.points_created == 2
