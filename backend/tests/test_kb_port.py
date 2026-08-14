"""Tests for porting approved KB points/entities into base resumes (Task 6)."""

import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.base_resume import BaseResume
from app.models.career_kb import KBEntity, KBPoint, KBPortLog, KBProfile
from app.models.resume_version import ResumeVersion
from app.routers import base_resumes as router_module
from app.services import base_resume_render

# --- Copied seed / render helpers from tests/test_base_resumes_router.py -----

SAMPLE_DATA = {
    "contact": {"name": "Riley", "email": "a@example.com"},
    "summary": "Summary",
    "skills": [{"category": "Core", "items": ["Python"]}],
    "experience": [],
    "projects": [],
    "education": [],
    "certifications": [],
}


def _override_db(db_session):
    def _inner():
        yield db_session

    return _inner


def _seed(db_session, slug: str = "data_scientist", **extra) -> BaseResume:
    row = BaseResume(
        slug=slug,
        display_name=extra.get("display_name", slug.replace("_", " ").title()),
        data_json=extra.get("data_json", SAMPLE_DATA),
        pdf_path=extra.get("pdf_path"),
        tex_path=extra.get("tex_path"),
        pdf_rendered_at=extra.get("pdf_rendered_at"),
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _stub_render(monkeypatch, tmp_path: Path) -> list[str]:
    monkeypatch.setattr(router_module.settings, "base_resumes_dir", tmp_path)
    monkeypatch.setattr(base_resume_render.settings, "base_resumes_dir", tmp_path)
    rendered: list[str] = []

    def fake_render(slug, db, *, template_id=None):
        rendered.append(slug)
        row = db.get(BaseResume, slug)
        row.pdf_path = str(tmp_path / "pdfs" / f"{slug}.pdf")
        row.tex_path = str(tmp_path / "tex" / f"{slug}.tex")
        from datetime import UTC, datetime

        row.pdf_rendered_at = datetime.now(UTC)
        db.commit()
        db.refresh(row)
        return row

    monkeypatch.setattr(base_resume_render, "render_base_resume", fake_render)
    monkeypatch.setattr(router_module.base_resume_render, "render_base_resume", fake_render)
    return rendered


def _fail_render(monkeypatch, tmp_path: Path, message: str = "latex boom") -> None:
    """Point the on-disk mirror at tmp_path but make the PDF render blow up."""
    monkeypatch.setattr(router_module.settings, "base_resumes_dir", tmp_path)
    monkeypatch.setattr(base_resume_render.settings, "base_resumes_dir", tmp_path)

    def boom(slug, db, *, template_id=None):
        raise RuntimeError(message)

    monkeypatch.setattr(base_resume_render, "render_base_resume", boom)
    monkeypatch.setattr(router_module.base_resume_render, "render_base_resume", boom)


# --- KB seed helper ----------------------------------------------------------


def _make_entity(
    db_session,
    *,
    kind: str,
    title: str,
    org: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    detail: dict | None = None,
    points: list[tuple[str, str]] | None = None,
) -> tuple[KBEntity, list[KBPoint]]:
    """Create a KB entity plus points. `points` is a list of (text, state)."""
    entity = KBEntity(
        kind=kind,
        title=title,
        org=org,
        start_date=start_date,
        end_date=end_date,
        status="completed",
        detail_json=detail or {},
    )
    db_session.add(entity)
    db_session.flush()
    created: list[KBPoint] = []
    for text, state in points or []:
        p = KBPoint(entity_id=entity.id, text=text, state=state, origin="manual")
        db_session.add(p)
        created.append(p)
    db_session.commit()
    db_session.refresh(entity)
    for p in created:
        db_session.refresh(p)
    return entity, created


def _post_port(db_session, payload: dict):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        return TestClient(app).post("/api/kb/port", json=payload)
    finally:
        app.dependency_overrides.clear()


def _versions(db_session, slug: str) -> int:
    return (
        db_session.query(ResumeVersion)
        .filter_by(resume_kind="base", resume_key=slug)
        .count()
    )


# --- Tests -------------------------------------------------------------------


def test_port_creates_project_entry_disabled(db_session, tmp_path, monkeypatch):
    _stub_render(monkeypatch, tmp_path)
    _seed(db_session, slug="data_scientist", data_json=SAMPLE_DATA)
    entity, points = _make_entity(
        db_session,
        kind="project",
        title="RAG Chatbot",
        detail={"tech": "Python"},
        points=[("Built a retrieval pipeline.", "approved"),
                ("Served 10k queries/day.", "approved")],
    )
    before = _versions(db_session, "data_scientist")

    res = _post_port(
        db_session,
        {"target_slug": "data_scientist", "items": [{"entity_id": str(entity.id)}]},
    )

    assert res.status_code == 200, res.text
    row = db_session.get(BaseResume, "data_scientist")
    projects = row.data_json["projects"]
    assert len(projects) == 1
    assert projects[0]["name"] == "RAG Chatbot"
    assert projects[0]["enabled"] is False
    assert sorted(projects[0]["bullets"]) == sorted(
        ["Built a retrieval pipeline.", "Served 10k queries/day."]
    )
    # Exactly one new import version.
    assert _versions(db_session, "data_scientist") == before + 1
    latest = (
        db_session.query(ResumeVersion)
        .filter_by(resume_kind="base", resume_key="data_scientist")
        .order_by(ResumeVersion.version_number.desc())
        .first()
    )
    assert latest.source == "import"
    # One port-log row per point.
    logs = db_session.query(KBPortLog).all()
    assert len(logs) == 2
    assert {log.ported_text for log in logs} == {
        "Built a retrieval pipeline.",
        "Served 10k queries/day.",
    }
    assert all(log.resume_key == "data_scientist" and log.section == "projects" for log in logs)
    assert all(log.point_id is not None for log in logs)

    report = res.json()["report"]
    assert report["items"][0]["created_entry"] is True
    assert len(report["items"][0]["ported_point_ids"]) == 2


def test_port_appends_bullets_to_matching_experience(db_session, tmp_path, monkeypatch):
    _stub_render(monkeypatch, tmp_path)
    data = {
        **SAMPLE_DATA,
        "experience": [
            {
                "company": "Fictional Employer Legacy",
                "role": "Analyst",
                "start_date": "Jul 2022",
                "end_date": "Jun 2024",
                "bullets": ["Existing bullet."],
            }
        ],
    }
    _seed(db_session, slug="data_scientist", data_json=data)
    entity, points = _make_entity(
        db_session,
        kind="experience",
        title="Analyst",
        org="Fictional Employer Legacy",
        start_date="Jul 2022",
        points=[("Existing bullet.", "approved"), ("New bullet.", "approved")],
    )
    dup_point = next(p for p in points if p.text == "Existing bullet.")
    new_point = next(p for p in points if p.text == "New bullet.")

    res = _post_port(
        db_session,
        {"target_slug": "data_scientist", "items": [{"entity_id": str(entity.id)}]},
    )

    assert res.status_code == 200, res.text
    row = db_session.get(BaseResume, "data_scientist")
    exp = row.data_json["experience"]
    assert len(exp) == 1  # no new entry
    assert exp[0]["bullets"] == ["Existing bullet.", "New bullet."]

    item = res.json()["report"]["items"][0]
    assert item["created_entry"] is False
    assert item["ported_point_ids"] == [str(new_point.id)]
    assert item["skipped_duplicate_point_ids"] == [str(dup_point.id)]

    # Only the newly-added bullet gets a port-log row.
    logs = db_session.query(KBPortLog).all()
    assert len(logs) == 1
    assert logs[0].ported_text == "New bullet."


def test_port_rejects_draft_point_400(db_session, tmp_path, monkeypatch):
    _stub_render(monkeypatch, tmp_path)
    _seed(db_session, slug="data_scientist", data_json=SAMPLE_DATA)
    entity, points = _make_entity(
        db_session,
        kind="project",
        title="Half-baked",
        points=[("A draft point.", "draft")],
    )

    res = _post_port(
        db_session,
        {
            "target_slug": "data_scientist",
            "items": [{"entity_id": str(entity.id), "point_ids": [str(points[0].id)]}],
        },
    )

    assert res.status_code == 400


def test_port_certification_maps_to_string(db_session, tmp_path, monkeypatch):
    _stub_render(monkeypatch, tmp_path)
    data = {**SAMPLE_DATA, "certifications": ["aws saa (amazon)"]}
    _seed(db_session, slug="data_scientist", data_json=data)
    # Normalized duplicate of the existing cert -> skipped.
    dup_entity, _ = _make_entity(db_session, kind="certification", title="AWS SAA", org="Amazon")
    # A genuinely new cert -> added.
    new_entity, _ = _make_entity(
        db_session, kind="certification", title="Azure Fundamentals", org="Microsoft"
    )

    res = _post_port(
        db_session,
        {
            "target_slug": "data_scientist",
            "items": [
                {"entity_id": str(dup_entity.id)},
                {"entity_id": str(new_entity.id)},
            ],
        },
    )

    assert res.status_code == 200, res.text
    row = db_session.get(BaseResume, "data_scientist")
    assert row.data_json["certifications"] == [
        "aws saa (amazon)",
        "Azure Fundamentals (Microsoft)",
    ]
    # Only the added cert gets a port-log row (entity-derived, point_id None).
    logs = db_session.query(KBPortLog).all()
    assert len(logs) == 1
    assert logs[0].section == "certifications"
    assert logs[0].point_id is None
    assert logs[0].ported_text == "Azure Fundamentals (Microsoft)"


def test_port_education_appends_via_replace_entry(db_session, tmp_path, monkeypatch):
    _stub_render(monkeypatch, tmp_path)
    data = {
        **SAMPLE_DATA,
        "education": [
            {"institution": "UTA", "degree": "MSBA", "bullets": ["Prior line."]}
        ],
    }
    _seed(db_session, slug="data_scientist", data_json=data)
    entity, points = _make_entity(
        db_session,
        kind="education",
        title="MSBA",
        org="UTA",
        points=[("Led the capstone project.", "approved")],
    )

    res = _post_port(
        db_session,
        {"target_slug": "data_scientist", "items": [{"entity_id": str(entity.id)}]},
    )

    assert res.status_code == 200, res.text
    row = db_session.get(BaseResume, "data_scientist")
    edu = row.data_json["education"]
    assert len(edu) == 1  # no new entry — appended via ReplaceEntry
    assert edu[0]["bullets"] == ["Prior line.", "Led the capstone project."]

    logs = db_session.query(KBPortLog).all()
    assert len(logs) == 1
    assert logs[0].section == "education"
    assert logs[0].ported_text == "Led the capstone project."


def test_port_skill_categories_merges_profile_groups(db_session, tmp_path, monkeypatch):
    _stub_render(monkeypatch, tmp_path)
    db_session.add(
        KBProfile(id=1, skills_json=[{"category": "ML Ops", "items": ["Docker", "MLflow"]}])
    )
    db_session.commit()
    data = {**SAMPLE_DATA, "skills": [{"category": "ML Ops", "items": ["Docker"]}]}
    _seed(db_session, slug="data_scientist", data_json=data)

    res = _post_port(
        db_session,
        {"target_slug": "data_scientist", "skill_categories": ["ML Ops"]},
    )

    assert res.status_code == 200, res.text
    row = db_session.get(BaseResume, "data_scientist")
    groups = {g["category"]: g for g in row.data_json["skills"]}
    assert groups["ML Ops"]["items"] == ["Docker", "MLflow"]  # union, no dup
    assert res.json()["report"]["skills_merged"] == ["ML Ops"]
    # Profile-level skills carry no entity -> no port-log rows.
    assert db_session.query(KBPortLog).count() == 0


def test_port_single_version_for_multi_item(db_session, tmp_path, monkeypatch):
    _stub_render(monkeypatch, tmp_path)
    _seed(db_session, slug="data_scientist", data_json=SAMPLE_DATA)
    e1, _ = _make_entity(
        db_session, kind="project", title="Proj A", points=[("Did A.", "approved")]
    )
    e2, _ = _make_entity(
        db_session, kind="project", title="Proj B", points=[("Did B.", "approved")]
    )
    before = _versions(db_session, "data_scientist")

    res = _post_port(
        db_session,
        {
            "target_slug": "data_scientist",
            "items": [{"entity_id": str(e1.id)}, {"entity_id": str(e2.id)}],
        },
    )

    assert res.status_code == 200, res.text
    row = db_session.get(BaseResume, "data_scientist")
    assert len(row.data_json["projects"]) == 2
    assert _versions(db_session, "data_scientist") == before + 1


def test_port_unknown_target_404(db_session):
    res = _post_port(db_session, {"target_slug": "does_not_exist", "items": []})
    assert res.status_code == 404


def test_port_two_education_entities_same_entry_no_clobber(db_session, tmp_path, monkeypatch):
    _stub_render(monkeypatch, tmp_path)
    data = {
        **SAMPLE_DATA,
        "education": [{"institution": "UTA", "degree": "MSBA", "bullets": []}],
    }
    _seed(db_session, slug="data_scientist", data_json=data)
    e1, _ = _make_entity(
        db_session, kind="education", title="MSBA", org="UTA",
        points=[("Point from A.", "approved")],
    )
    # Same identity (case-insensitive) -> matches the SAME resume entry.
    e2, _ = _make_entity(
        db_session, kind="education", title="msba", org="uta",
        points=[("Point from B.", "approved")],
    )

    res = _post_port(
        db_session,
        {
            "target_slug": "data_scientist",
            "items": [{"entity_id": str(e1.id)}, {"entity_id": str(e2.id)}],
        },
    )

    assert res.status_code == 200, res.text
    row = db_session.get(BaseResume, "data_scientist")
    edu = row.data_json["education"]
    assert len(edu) == 1
    # Both points survive — neither ReplaceEntry clobbers the other.
    assert edu[0]["bullets"] == ["Point from A.", "Point from B."]


def test_port_two_experience_entities_same_entry_no_double_append(db_session, tmp_path, monkeypatch):
    _stub_render(monkeypatch, tmp_path)
    data = {
        **SAMPLE_DATA,
        "experience": [
            {"company": "Fictional Employer Legacy", "role": "Analyst", "start_date": "Jul 2022", "bullets": []}
        ],
    }
    _seed(db_session, slug="data_scientist", data_json=data)
    # Two entities normalizing to the SAME company+role+start_date, sharing one
    # point text — the shared line must not be appended twice.
    e1, _ = _make_entity(
        db_session, kind="experience", title="Analyst", org="Fictional Employer Legacy", start_date="Jul 2022",
        points=[("Shared line.", "approved"), ("Only from A.", "approved")],
    )
    e2, _ = _make_entity(
        db_session, kind="experience", title="analyst",
        org="fictional employer legacy", start_date="Jul 2022",
        points=[("Shared line.", "approved"), ("Only from B.", "approved")],
    )

    res = _post_port(
        db_session,
        {
            "target_slug": "data_scientist",
            "items": [{"entity_id": str(e1.id)}, {"entity_id": str(e2.id)}],
        },
    )

    assert res.status_code == 200, res.text
    row = db_session.get(BaseResume, "data_scientist")
    exp = row.data_json["experience"]
    assert len(exp) == 1  # no new entry
    assert exp[0]["bullets"] == ["Shared line.", "Only from A.", "Only from B."]
    assert exp[0]["bullets"].count("Shared line.") == 1  # deduped across items


def test_port_render_failure_sets_error_but_keeps_port(db_session, tmp_path, monkeypatch):
    _fail_render(monkeypatch, tmp_path)
    _seed(db_session, slug="data_scientist", data_json=SAMPLE_DATA)
    entity, _ = _make_entity(
        db_session, kind="project", title="Breaks LaTeX",
        points=[("A ported bullet.", "approved")],
    )

    res = _post_port(
        db_session,
        {"target_slug": "data_scientist", "items": [{"entity_id": str(entity.id)}]},
    )

    # Render blew up, but the port is committed and versioned; render_error is set.
    assert res.status_code == 200, res.text
    assert res.json()["resume"]["render_error"] == "latex boom"
    row = db_session.get(BaseResume, "data_scientist")
    assert row.render_error == "latex boom"
    assert row.data_json["projects"][0]["bullets"] == ["A ported bullet."]


def test_port_entity_not_found_404(db_session, tmp_path, monkeypatch):
    _stub_render(monkeypatch, tmp_path)
    _seed(db_session, slug="data_scientist", data_json=SAMPLE_DATA)

    res = _post_port(
        db_session,
        {"target_slug": "data_scientist", "items": [{"entity_id": str(uuid.uuid4())}]},
    )

    assert res.status_code == 404


def test_port_extra_section_entries_and_bullets(db_session, tmp_path, monkeypatch):
    _stub_render(monkeypatch, tmp_path)
    _seed(db_session, slug="data_scientist", data_json=SAMPLE_DATA)

    # 1. Port a bullets-type extra entity
    awards_ent, _ = _make_entity(
        db_session,
        kind="extra",
        title="Awards & Honors",
        detail={
            "section_key": "awards",
            "section_type": "bullets",
            "section_title": "Awards & Honors",
        },
        points=[("First Place Hackathon", "approved")],
    )

    res1 = _post_port(
        db_session,
        {"target_slug": "data_scientist", "items": [{"entity_id": str(awards_ent.id)}]},
    )
    assert res1.status_code == 200, res1.text
    row1 = db_session.get(BaseResume, "data_scientist")
    extras1 = row1.data_json["extra_sections"]
    assert len(extras1) == 1
    assert extras1[0]["key"] == "awards"
    assert extras1[0]["type"] == "bullets"
    assert extras1[0]["bullets"] == ["First Place Hackathon"]

    # 2. Port an entries-type extra entity into a new section
    pub_ent, _ = _make_entity(
        db_session,
        kind="extra",
        title="Deep Learning at Scale",
        org="ICML",
        detail={
            "section_key": "publications",
            "section_type": "entries",
            "section_title": "Publications",
            "date": "2024",
        },
        points=[("Presented oral paper.", "approved")],
    )

    res2 = _post_port(
        db_session,
        {"target_slug": "data_scientist", "items": [{"entity_id": str(pub_ent.id)}]},
    )
    assert res2.status_code == 200, res2.text
    row2 = db_session.get(BaseResume, "data_scientist")
    extras2 = row2.data_json["extra_sections"]
    assert len(extras2) == 2
    pub_sec = next(s for s in extras2 if s["key"] == "publications")
    assert pub_sec["type"] == "entries"
    assert pub_sec["entries"][0]["heading"] == "Deep Learning at Scale"
    assert pub_sec["entries"][0]["subheading"] == "ICML"
    assert pub_sec["entries"][0]["bullets"] == ["Presented oral paper."]

    # 3. Port a second entry into existing entries-type section
    pub_ent2, _ = _make_entity(
        db_session,
        kind="extra",
        title="Attention Models in Practice",
        org="NeurIPS",
        detail={
            "section_key": "publications",
            "section_type": "entries",
            "section_title": "Publications",
            "date": "2025",
        },
        points=[("Poster presentation.", "approved")],
    )

    res3 = _post_port(
        db_session,
        {"target_slug": "data_scientist", "items": [{"entity_id": str(pub_ent2.id)}]},
    )
    assert res3.status_code == 200, res3.text
    row3 = db_session.get(BaseResume, "data_scientist")
    pub_sec3 = next(s for s in row3.data_json["extra_sections"] if s["key"] == "publications")
    assert len(pub_sec3["entries"]) == 2


def test_kb_port_item_model_validates_section_key():
    import pytest
    from pydantic import ValidationError

    from app.schemas.career_kb import KBPortItem

    item1 = KBPortItem(entity_id=uuid.uuid4())
    assert item1.section_key is None

    item2 = KBPortItem(entity_id=uuid.uuid4(), section_key="publications")
    assert item2.section_key == "publications"

    with pytest.raises(ValidationError) as exc:
        KBPortItem(entity_id=uuid.uuid4(), section_key="experience")
    assert "collides with the core" in str(exc.value)


def test_port_include_profile_summary(db_session, tmp_path, monkeypatch):
    _stub_render(monkeypatch, tmp_path)
    db_session.add(KBProfile(id=1, summary="Profile-level summary."))
    db_session.commit()
    _seed(db_session, slug="data_scientist", data_json=SAMPLE_DATA)

    res = _post_port(
        db_session,
        {"target_slug": "data_scientist", "include_profile_summary": True},
    )

    assert res.status_code == 200, res.text
    row = db_session.get(BaseResume, "data_scientist")
    assert row.data_json["summary"] == "Profile-level summary."
