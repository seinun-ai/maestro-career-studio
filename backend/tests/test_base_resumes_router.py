import json
import shutil
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from tests.pdf_fixtures import write_blank_pdf
import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.base_resume import BaseResume
from app.routers import base_resumes as router_module
from app.services import base_resume_render
from app.services.template_validation import SAMPLE_RESUME


def _write_valid_pdf(path: Path, pages: int = 1) -> None:
    """Write a real (rasterizable) PDF so the preview page-image step works."""
    write_blank_pdf(path, pages)


SAMPLE_DATA = {
    "contact": {"name": "Sample", "email": "a@example.com"},
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


def test_list_base_resumes_returns_summaries(db_session):
    _seed(db_session, slug="data_scientist")
    _seed(db_session, slug="ai_ml_engineer", display_name="AI/ML Engineer")

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/base-resumes")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert [item["slug"] for item in body] == ["ai_ml_engineer", "data_scientist"]
    assert body[0]["display_name"] == "AI/ML Engineer"
    assert "updated_at" in body[0]


def test_get_base_resume_returns_detail(db_session):
    _seed(db_session, slug="data_scientist", pdf_path="/tmp/ds.pdf")

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/base-resumes/data_scientist")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["slug"] == "data_scientist"
    assert body["pdf_path"] == "/tmp/ds.pdf"
    assert body["data"]["contact"]["name"] == "Sample"


def test_get_unknown_base_resume_returns_404(db_session):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/base-resumes/missing")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_create_base_resume_validates_slug_and_writes_file(db_session, tmp_path, monkeypatch):
    rendered = _stub_render(monkeypatch, tmp_path)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        bad = client.post(
            "/api/base-resumes",
            json={"slug": "Bad-Slug", "display_name": "x", "data": SAMPLE_DATA},
        )
        good = client.post(
            "/api/base-resumes",
            json={"slug": "custom", "display_name": "Custom", "data": SAMPLE_DATA},
        )
    finally:
        app.dependency_overrides.clear()

    assert bad.status_code == 400
    assert good.status_code == 200
    assert rendered == ["custom"]
    assert (tmp_path / "custom.json").exists()
    written = json.loads((tmp_path / "custom.json").read_text(encoding="utf-8"))
    assert written["contact"]["name"] == "Sample"


def test_create_base_resume_conflict_when_slug_exists(db_session, tmp_path, monkeypatch):
    _stub_render(monkeypatch, tmp_path)
    _seed(db_session, slug="data_scientist")

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            "/api/base-resumes",
            json={"slug": "data_scientist", "display_name": "x", "data": SAMPLE_DATA},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409


def test_update_base_resume_renders_and_persists(db_session, tmp_path, monkeypatch):
    rendered = _stub_render(monkeypatch, tmp_path)
    _seed(db_session, slug="data_scientist")

    new_data = {**SAMPLE_DATA, "summary": "Updated summary"}

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).put(
            "/api/base-resumes/data_scientist",
            json={"display_name": "Data Sci", "data": new_data},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert rendered == ["data_scientist"]
    assert response.json()["display_name"] == "Data Sci"
    assert response.json()["pdf_rendered_at"] is not None
    assert db_session.get(BaseResume, "data_scientist").data_json["summary"] == "Updated summary"


def test_delete_base_resume_soft_deletes_and_keeps_files(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(router_module.settings, "base_resumes_dir", tmp_path)
    pdf = tmp_path / "pdfs" / "data_scientist.pdf"
    tex = tmp_path / "tex" / "data_scientist.tex"
    pdf.parent.mkdir(parents=True)
    tex.parent.mkdir(parents=True)
    pdf.write_text("x")
    tex.write_text("x")
    json_path = tmp_path / "data_scientist.json"
    json_path.write_text("{}")
    _seed(db_session, slug="data_scientist", pdf_path=str(pdf), tex_path=str(tex))

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).delete("/api/base-resumes/data_scientist")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    # Preserve-history policy: row survives, stamped deleted_at, files kept.
    row = db_session.get(BaseResume, "data_scientist")
    assert row is not None
    assert row.deleted_at is not None
    assert pdf.exists()
    assert tex.exists()
    assert json_path.exists()


def test_deleted_base_resume_excluded_from_list_but_get_still_serves(db_session):
    from datetime import UTC, datetime

    _seed(db_session, slug="data_scientist")
    deleted = _seed(db_session, slug="old_track")
    deleted.deleted_at = datetime.now(UTC)
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        list_response = client.get("/api/base-resumes")
        get_response = client.get("/api/base-resumes/old_track")
    finally:
        app.dependency_overrides.clear()

    assert list_response.status_code == 200
    assert [item["slug"] for item in list_response.json()] == ["data_scientist"]
    # get_base_resume still serves a soft-deleted slug for history detail.
    assert get_response.status_code == 200
    assert get_response.json()["slug"] == "old_track"


def test_create_blocks_reuse_of_soft_deleted_slug(db_session, tmp_path, monkeypatch):
    from datetime import UTC, datetime

    _stub_render(monkeypatch, tmp_path)
    deleted = _seed(db_session, slug="old_track")
    deleted.deleted_at = datetime.now(UTC)
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            "/api/base-resumes",
            json={"slug": "old_track", "display_name": "x", "data": SAMPLE_DATA},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert "deleted" in response.json()["detail"].lower()


def test_port_project_appends_disabled_copy_to_target(db_session, tmp_path, monkeypatch):
    rendered = _stub_render(monkeypatch, tmp_path)
    source_data = {
        **SAMPLE_DATA,
        "projects": [
            {
                "name": "RAG Chatbot",
                "enabled": True,
                "tech": "Python",
                "bullets": ["Built a pipeline."],
            }
        ],
    }
    target_data = {**SAMPLE_DATA, "projects": []}
    _seed(db_session, slug="data_scientist", data_json=source_data)
    _seed(db_session, slug="hybrid", data_json=target_data)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            "/api/base-resumes/data_scientist/port-project",
            json={"target_slug": "hybrid", "project_index": 0},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"target_slug": "hybrid", "project_index": 0}
    assert rendered == ["hybrid"]

    target = db_session.get(BaseResume, "hybrid")
    assert len(target.data_json["projects"]) == 1
    assert target.data_json["projects"][0]["name"] == "RAG Chatbot"
    assert target.data_json["projects"][0]["enabled"] is False
    assert target.data_json["projects"][0]["bullets"] == ["Built a pipeline."]

    source = db_session.get(BaseResume, "data_scientist")
    assert len(source.data_json["projects"]) == 1
    assert source.data_json["projects"][0]["enabled"] is True


def test_port_project_rejects_same_slug(db_session):
    _seed(db_session, slug="data_scientist")

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            "/api/base-resumes/data_scientist/port-project",
            json={"target_slug": "data_scientist", "project_index": 0},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400


def test_duplicate_base_resume_copies_data(db_session, tmp_path, monkeypatch):
    rendered = _stub_render(monkeypatch, tmp_path)
    _seed(db_session, slug="data_scientist")

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            "/api/base-resumes/data_scientist/duplicate",
            json={"new_slug": "data_scientist_v2", "new_display_name": "DS v2"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert rendered == ["data_scientist_v2"]
    assert response.json()["slug"] == "data_scientist_v2"
    assert response.json()["display_name"] == "DS v2"
    assert db_session.get(BaseResume, "data_scientist_v2") is not None


def test_get_base_resume_pdf_returns_file(db_session, tmp_path):
    pdf = tmp_path / "ds.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    _seed(db_session, slug="data_scientist", pdf_path=str(pdf))

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/base-resumes/data_scientist/pdf")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"


def test_get_base_resume_pdf_404_when_missing(db_session):
    _seed(db_session, slug="data_scientist", pdf_path=None)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/base-resumes/data_scientist/pdf")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_render_endpoint_triggers_render(db_session, tmp_path, monkeypatch):
    rendered = _stub_render(monkeypatch, tmp_path)
    _seed(db_session, slug="data_scientist")

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post("/api/base-resumes/data_scientist/render")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert rendered == ["data_scientist"]
    assert response.json()["pdf_rendered_at"] is not None


def test_edits_render_failure_sets_render_error_then_clears(
    db_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(router_module.settings, "base_resumes_dir", tmp_path)
    _seed(db_session, slug="data_scientist")

    def boom(slug, db, *, template_id=None):
        raise RuntimeError("latex exploded")

    monkeypatch.setattr(base_resume_render, "render_base_resume", boom)
    monkeypatch.setattr(router_module.base_resume_render, "render_base_resume", boom)

    ops = [{"kind": "replace_summary", "value": "New summary"}]
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).patch(
            "/api/base-resumes/data_scientist/edits", json={"ops": ops}
        )
        assert response.status_code == 200
        assert response.json()["render_error"] == "latex exploded"

        def ok(slug, db, *, template_id=None):
            row = db.get(BaseResume, slug)
            row.render_error = None
            row.pdf_pages = 1
            db.commit()
            db.refresh(row)
            return row

        monkeypatch.setattr(base_resume_render, "render_base_resume", ok)
        monkeypatch.setattr(router_module.base_resume_render, "render_base_resume", ok)

        response2 = TestClient(app).patch(
            "/api/base-resumes/data_scientist/edits", json={"ops": ops}
        )
        assert response2.status_code == 200
        assert response2.json()["render_error"] is None
    finally:
        app.dependency_overrides.clear()


def test_render_falls_back_for_unknown_template(db_session, tmp_path, monkeypatch):
    # Render stays tolerant of a stale/deleted persisted template_id: the render
    # endpoint no longer 404s — it falls back to the default template.
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is not installed")
    monkeypatch.setattr(router_module.settings, "base_resumes_dir", tmp_path)
    _seed(db_session, slug="data_scientist", data_json=SAMPLE_RESUME)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).post(
            "/api/base-resumes/data_scientist/render?template_id=nope"
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    assert r.json()["render_error"] is None


def test_render_falls_back_for_draft_template(db_session, tmp_path, monkeypatch):
    # A not-ready (draft) template also falls back to default instead of 400.
    from app.services import template_registry as reg

    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is not installed")
    monkeypatch.setattr(router_module.settings, "base_resumes_dir", tmp_path)
    _seed(db_session, slug="data_scientist", data_json=SAMPLE_RESUME)
    reg.create_draft(
        db_session, id="draftt", display_name="D", source="X", origin="mcp"
    )
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).post(
            "/api/base-resumes/data_scientist/render?template_id=draftt"
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    assert r.json()["render_error"] is None


def test_update_falls_back_for_unknown_template(db_session, tmp_path, monkeypatch):
    # The update PUT re-renders; a bad template_id no longer 404s the request.
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is not installed")
    monkeypatch.setattr(router_module.settings, "base_resumes_dir", tmp_path)
    _seed(db_session, slug="data_scientist")
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).put(
            "/api/base-resumes/data_scientist",
            json={"display_name": "DS", "data": SAMPLE_RESUME, "template_id": "nope"},
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    assert r.json()["render_error"] is None


def test_update_falls_back_for_draft_template(db_session, tmp_path, monkeypatch):
    from app.services import template_registry as reg

    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is not installed")
    monkeypatch.setattr(router_module.settings, "base_resumes_dir", tmp_path)
    _seed(db_session, slug="data_scientist")
    reg.create_draft(
        db_session, id="draftt", display_name="D", source="X", origin="mcp"
    )
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).put(
            "/api/base-resumes/data_scientist",
            json={"display_name": "DS", "data": SAMPLE_RESUME, "template_id": "draftt"},
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    assert r.json()["render_error"] is None


def test_get_unknown_slug_404s_without_lazy_bootstrap(db_session, tmp_path, monkeypatch):
    """A GET must not mint a row or a JSON file for a slug that does not exist."""
    monkeypatch.setattr(router_module.settings, "base_resumes_dir", tmp_path)
    assert db_session.get(BaseResume, "retired_profile") is None
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        res = TestClient(app).get("/api/base-resumes/retired_profile")
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 404
    assert db_session.get(BaseResume, "retired_profile") is None
    assert not (tmp_path / "retired_profile.json").exists()


def test_patch_base_resume_edits_replaces_bullet_only(db_session, monkeypatch, tmp_path):
    data = {
        **SAMPLE_DATA,
        "experience": [
            {"company": "Acme", "role": "DS", "start_date": "2020", "bullets": ["Old.", "Keep."]}
        ],
    }
    _seed(db_session, slug="data_scientist", data_json=data)
    rendered = _stub_render(monkeypatch, tmp_path)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).patch(
            "/api/base-resumes/data_scientist/edits",
            json={
                "ops": [
                    {
                        "kind": "replace_bullet",
                        "section": "experience",
                        "index": 0,
                        "bullet_index": 0,
                        "value": "New bullet.",
                    }
                ]
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["experience"][0]["bullets"] == ["New bullet.", "Keep."]
    assert rendered == ["data_scientist"]


def test_patch_base_resume_edits_out_of_range_returns_400(db_session, monkeypatch, tmp_path):
    _seed(db_session, slug="data_scientist")
    _stub_render(monkeypatch, tmp_path)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).patch(
            "/api/base-resumes/data_scientist/edits",
            json={
                "ops": [
                    {
                        "kind": "replace_bullet",
                        "section": "experience",
                        "index": 7,
                        "bullet_index": 0,
                        "value": "x",
                    }
                ]
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "out of range" in response.json()["detail"]


def test_patch_base_resume_edits_missing_skills_category_returns_400(db_session, monkeypatch, tmp_path):
    _seed(db_session, slug="data_scientist")
    _stub_render(monkeypatch, tmp_path)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).patch(
            "/api/base-resumes/data_scientist/edits",
            json={"ops": [{"kind": "replace_skills_group", "category": "Robotics", "items": ["ROS"]}]},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400


def test_patch_base_resume_edits_unknown_slug_returns_404(db_session, monkeypatch, tmp_path):
    _stub_render(monkeypatch, tmp_path)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).patch(
            "/api/base-resumes/missing/edits",
            json={"ops": [{"kind": "replace_summary", "value": "x"}]},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 404


# --- extra (custom) section ops through the PATCH edits endpoint ------------

_EXTRAS_SEED = {
    **SAMPLE_DATA,
    "extra_sections": [
        {"key": "publications", "title": "Publications", "type": "entries", "enabled": True,
         "entries": [{"heading": "A paper", "date": "2025", "bullets": []}]},
        {"key": "awards", "title": "Awards", "type": "bullets", "enabled": True,
         "bullets": ["First place, 2025"]},
    ],
}


def _patch_edits(db_session, ops, slug="data_scientist"):
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        return TestClient(app).patch(f"/api/base-resumes/{slug}/edits", json={"ops": ops})
    finally:
        app.dependency_overrides.clear()


def test_patch_base_resume_extra_section_ops_round_trip(db_session, monkeypatch, tmp_path):
    _seed(db_session, slug="data_scientist", data_json=deepcopy(SAMPLE_DATA))
    _stub_render(monkeypatch, tmp_path)

    # add two, then move, replace, remove — all four ops end to end.
    resp = _patch_edits(
        db_session,
        [
            {"kind": "add_extra_section",
             "value": {"key": "publications", "title": "Publications", "type": "entries",
                       "entries": [{"heading": "A paper", "date": "2025"}]}},
            {"kind": "add_extra_section",
             "value": {"key": "awards", "title": "Awards", "type": "bullets",
                       "bullets": ["First place, 2025"]}},
            {"kind": "move_extra_section", "section_key": "awards", "to_index": 0},
            {"kind": "replace_extra_section", "section_key": "publications",
             "value": {"key": "publications", "title": "Selected Publications", "type": "entries",
                       "entries": [{"heading": "A paper", "date": "2025"}]}},
        ],
    )
    assert resp.status_code == 200
    sections = resp.json()["data"]["extra_sections"]
    assert [s["key"] for s in sections] == ["awards", "publications"]
    assert sections[1]["title"] == "Selected Publications"

    # remove one
    resp2 = _patch_edits(db_session, [{"kind": "remove_extra_section", "section_key": "awards"}])
    assert resp2.status_code == 200
    assert [s["key"] for s in resp2.json()["data"]["extra_sections"]] == ["publications"]


def test_patch_base_resume_extra_section_move_out_of_range_returns_400(
    db_session, monkeypatch, tmp_path
):
    _seed(db_session, slug="data_scientist", data_json=deepcopy(_EXTRAS_SEED))
    _stub_render(monkeypatch, tmp_path)
    resp = _patch_edits(
        db_session, [{"kind": "move_extra_section", "section_key": "awards", "to_index": 9}]
    )
    assert resp.status_code == 400
    assert "out of range" in resp.json()["detail"]


def test_patch_base_resume_extra_section_duplicate_key_add_returns_400(
    db_session, monkeypatch, tmp_path
):
    _seed(db_session, slug="data_scientist", data_json=deepcopy(_EXTRAS_SEED))
    _stub_render(monkeypatch, tmp_path)
    resp = _patch_edits(
        db_session,
        [{"kind": "add_extra_section",
          "value": {"key": "awards", "title": "Dup", "type": "bullets", "bullets": ["x"]}}],
    )
    assert resp.status_code == 400
    assert "duplicate" in resp.json()["detail"]


def test_patch_base_resume_extra_section_unknown_key_returns_400(
    db_session, monkeypatch, tmp_path
):
    _seed(db_session, slug="data_scientist", data_json=deepcopy(_EXTRAS_SEED))
    _stub_render(monkeypatch, tmp_path)
    remove = _patch_edits(db_session, [{"kind": "remove_extra_section", "section_key": "nope"}])
    assert remove.status_code == 400
    assert "no extra section with key" in remove.json()["detail"]

    replace = _patch_edits(
        db_session,
        [{"kind": "replace_extra_section", "section_key": "nope",
          "value": {"key": "nope", "title": "X", "type": "bullets", "bullets": ["y"]}}],
    )
    assert replace.status_code == 400
    assert "no extra section with key" in replace.json()["detail"]


def test_patch_base_resume_extra_section_batch_is_atomic(db_session, monkeypatch, tmp_path):
    row = _seed(db_session, slug="data_scientist", data_json=deepcopy(_EXTRAS_SEED))
    _stub_render(monkeypatch, tmp_path)
    resp = _patch_edits(
        db_session,
        [
            {"kind": "remove_extra_section", "section_key": "publications"},
            {"kind": "remove_extra_section", "section_key": "nope"},  # fails -> whole batch aborts
        ],
    )
    assert resp.status_code == 400
    db_session.refresh(row)
    # nothing persisted: both original sections remain.
    assert [s["key"] for s in row.data_json["extra_sections"]] == ["publications", "awards"]


def _real_tex_render(monkeypatch, tmp_path):
    """Point the render at tmp_path and produce a real .tex via the file
    template (reflecting fmt), but skip pdflatex."""
    from app.services import pdf_render

    monkeypatch.setattr(router_module.settings, "base_resumes_dir", tmp_path)
    monkeypatch.setattr(base_resume_render.settings, "base_resumes_dir", tmp_path)

    def fake_render_and_compile(
        data, tex_path, pdf_path, *, template_id=None, session=None, formatting=None
    ):
        tex_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        tex = pdf_render.render_document(data, formatting=formatting).source_text
        tex_path.write_text(tex, encoding="utf-8")
        write_blank_pdf(pdf_path)
        return tex_path

    monkeypatch.setattr(
        base_resume_render.pdf_render, "render_and_compile", fake_render_and_compile
    )


def test_put_persists_formatting_and_render_uses_it(db_session, tmp_path, monkeypatch):
    _real_tex_render(monkeypatch, tmp_path)
    _seed(db_session, slug="data_scientist")

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        resp = TestClient(app).put(
            "/api/base-resumes/data_scientist",
            json={"data": SAMPLE_DATA, "formatting": {"font_size": 12}},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["formatting"] == {"font_size": 12}
    row = db_session.get(BaseResume, "data_scientist")
    assert row.formatting_json == {"font_size": 12}
    tex = Path(row.tex_path).read_text(encoding="utf-8")
    assert "12pt" in tex


def test_put_rejects_invalid_formatting(db_session, tmp_path, monkeypatch):
    _real_tex_render(monkeypatch, tmp_path)
    _seed(db_session, slug="data_scientist")

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        # out-of-range value and unknown key are both rejected at write time,
        # so an invalid override can't be stored and brick later renders.
        bad_value = client.put(
            "/api/base-resumes/data_scientist",
            json={"data": SAMPLE_DATA, "formatting": {"font_size": 99}},
        )
        bad_key = client.put(
            "/api/base-resumes/data_scientist",
            json={"data": SAMPLE_DATA, "formatting": {"bogus": True}},
        )
    finally:
        app.dependency_overrides.clear()

    assert bad_value.status_code == 400
    assert bad_key.status_code == 400
    row = db_session.get(BaseResume, "data_scientist")
    assert row.formatting_json is None  # nothing invalid persisted


def test_put_omitting_formatting_leaves_it_unchanged(db_session, tmp_path, monkeypatch):
    _real_tex_render(monkeypatch, tmp_path)
    _seed(db_session, slug="data_scientist")
    row = db_session.get(BaseResume, "data_scientist")
    row.formatting_json = {"font_size": 12}
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        resp = TestClient(app).put(
            "/api/base-resumes/data_scientist",
            json={"data": SAMPLE_DATA},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["formatting"] == {"font_size": 12}
    db_session.refresh(row)
    assert row.formatting_json == {"font_size": 12}


def test_put_explicit_null_formatting_clears_it(db_session, tmp_path, monkeypatch):
    _real_tex_render(monkeypatch, tmp_path)
    _seed(db_session, slug="data_scientist")
    row = db_session.get(BaseResume, "data_scientist")
    row.formatting_json = {"font_size": 12}
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        resp = TestClient(app).put(
            "/api/base-resumes/data_scientist",
            json={"data": SAMPLE_DATA, "formatting": None},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["formatting"] is None
    db_session.refresh(row)
    assert row.formatting_json is None
    # cleared formatting -> default 11pt render
    assert "11pt" in Path(row.tex_path).read_text(encoding="utf-8")


def test_preview_manifest_and_page(db_session, tmp_path):
    pdf_path = tmp_path / "data_scientist.pdf"
    _write_valid_pdf(pdf_path, pages=1)
    _seed(
        db_session,
        slug="data_scientist",
        pdf_path=str(pdf_path),
        pdf_rendered_at=datetime.now(UTC),
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        manifest = client.get("/api/base-resumes/data_scientist/preview/pages")
        page = client.get("/api/base-resumes/data_scientist/preview/page/1")
        missing = client.get("/api/base-resumes/data_scientist/preview/page/99")
    finally:
        app.dependency_overrides.clear()

    assert manifest.status_code == 200
    body = manifest.json()
    assert body["page_count"] >= 1
    assert body["rendered_at"]
    assert page.status_code == 200
    assert page.headers["content-type"] == "image/png"
    assert missing.status_code == 404


def test_preview_404_before_first_render(db_session):
    _seed(db_session, slug="data_scientist")

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        manifest = client.get("/api/base-resumes/data_scientist/preview/pages")
        page = client.get("/api/base-resumes/data_scientist/preview/page/1")
    finally:
        app.dependency_overrides.clear()

    assert manifest.status_code == 404
    assert page.status_code == 404


def test_put_persists_template_id_and_render_uses_it(db_session, tmp_path, monkeypatch):
    """PUT with template_id persists it (round-trips on GET), and a later render
    that passes no template_id falls back to the stored choice."""
    from app.services import pdf_render
    from app.services import template_registry as reg

    # A ready non-default template whose source emits a recognizable marker.
    src = "THEMED_MARKER ((( fmt.font_size )))pt"
    reg.create_draft(db_session, id="themed", display_name="Themed", source=src, origin="mcp")
    themed = reg.get(db_session, "themed")
    themed.status = "ready"
    db_session.commit()

    _seed(db_session, slug="data_scientist")

    monkeypatch.setattr(router_module.settings, "base_resumes_dir", tmp_path)
    monkeypatch.setattr(base_resume_render.settings, "base_resumes_dir", tmp_path)

    def fake_render_and_compile(data, tex_path, pdf_path, *, template_id=None, session=None, formatting=None):
        tex = pdf_render.render_document(data, template_id=template_id, session=session, formatting=formatting).source_text
        tex_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        tex_path.write_text(tex, encoding="utf-8")
        _write_valid_pdf(pdf_path)
        return tex_path

    monkeypatch.setattr(pdf_render, "render_and_compile", fake_render_and_compile)

    tex_file = tmp_path / "tex" / "data_scientist.tex"

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        resp = client.put(
            "/api/base-resumes/data_scientist",
            json={"data": SAMPLE_DATA, "template_id": "themed"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["template_id"] == "themed"

        got = client.get("/api/base-resumes/data_scientist")
        assert got.status_code == 200
        assert got.json()["template_id"] == "themed"
        assert "THEMED_MARKER" in tex_file.read_text(encoding="utf-8")

        # Re-render WITHOUT a template_id -> falls back to the stored choice.
        tex_file.unlink()
        rr = client.post("/api/base-resumes/data_scientist/render")
        assert rr.status_code == 200
    finally:
        app.dependency_overrides.clear()

    assert "THEMED_MARKER" in tex_file.read_text(encoding="utf-8")


def _ready_no_extras_template(db_session, tid: str) -> None:
    """A ready template whose source never references extra_sections (F1)."""
    from app.services import template_registry as reg

    reg.create_draft(
        db_session,
        id=tid,
        display_name=tid,
        source=(
            r"\documentclass{article}\begin{document}"
            r"((( resume.contact.name|latex_escape )))\end{document}"
        ),
        origin="mcp",
    )
    row = reg.get(db_session, tid)
    row.status = "ready"
    db_session.commit()


_EXTRAS_PUT_DATA = {
    "contact": {"name": "Sample", "email": "a@example.com"},
    "extra_sections": [
        {"key": "awards", "title": "Awards", "type": "bullets", "bullets": ["First place"]}
    ],
}


def test_put_re_render_incompatible_template_returns_400(db_session, tmp_path, monkeypatch):
    # F1: base-resume PUT re-render with an extras-bearing resume + a template
    # that cannot render custom sections returns a clean 400 with the message
    # (via the ValueError->400 mapping), not an unhandled 500.
    monkeypatch.setattr(router_module.settings, "base_resumes_dir", tmp_path)
    _seed(db_session, "ds_put")
    _ready_no_extras_template(db_session, "noextra_put")

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).put(
            "/api/base-resumes/ds_put",
            json={"data": _EXTRAS_PUT_DATA, "template_id": "noextra_put"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert "custom section" in detail.lower()
    assert "awards" in detail


def test_edit_ops_incompatible_template_degrades_to_render_error(
    db_session, tmp_path, monkeypatch
):
    # F1 deliberate deviation: the typed-edit PATCH commits the edit BEFORE
    # rendering, so an incompatible template must NOT become a 4xx (that would
    # push clients to retry the applied ops). It degrades to a persisted
    # render_error (stale PDF) with a 200, exactly like a LaTeX failure — and the
    # edit itself survives.
    monkeypatch.setattr(router_module.settings, "base_resumes_dir", tmp_path)
    _seed(db_session, "ds_edit")
    _ready_no_extras_template(db_session, "noextra_edit")

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).patch(
            "/api/base-resumes/ds_edit/edits?template_id=noextra_edit",
            json={
                "ops": [
                    {
                        "kind": "add_extra_section",
                        "value": {
                            "key": "awards",
                            "title": "Awards",
                            "type": "bullets",
                            "bullets": ["First place"],
                        },
                    }
                ]
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["render_error"] is not None
    assert "custom section" in body["render_error"].lower()
    # The edit persisted despite the render failure.
    assert [s["key"] for s in body["data"]["extra_sections"]] == ["awards"]


def test_archived_base_resume_hidden_from_list_unless_requested(db_session):
    _seed(db_session, slug="data_scientist")
    _seed(db_session, slug="old_track")

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        archived = client.post("/api/base-resumes/old_track/archive")
        default_list = client.get("/api/base-resumes")
        with_archived = client.get("/api/base-resumes?include_archived=true")
    finally:
        app.dependency_overrides.clear()

    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    assert [i["slug"] for i in default_list.json()] == ["data_scientist"]
    assert [i["slug"] for i in with_archived.json()] == ["data_scientist", "old_track"]


def test_unarchive_restores_to_the_default_list(db_session):
    from datetime import UTC, datetime

    row = _seed(db_session, slug="old_track")
    row.archived_at = datetime.now(UTC)
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        restored = client.post("/api/base-resumes/old_track/unarchive")
        listing = client.get("/api/base-resumes")
    finally:
        app.dependency_overrides.clear()

    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None
    assert [i["slug"] for i in listing.json()] == ["old_track"]


def test_archived_base_resume_is_still_fully_resolvable(db_session):
    """Archive hides from menus; it must never break the resume itself."""
    from datetime import UTC, datetime

    row = _seed(db_session, slug="old_track")
    row.archived_at = datetime.now(UTC)
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        detail = TestClient(app).get("/api/base-resumes/old_track")
    finally:
        app.dependency_overrides.clear()

    assert detail.status_code == 200
    assert detail.json()["slug"] == "old_track"


def test_archive_404s_on_a_soft_deleted_resume(db_session):
    from datetime import UTC, datetime

    row = _seed(db_session, slug="old_track")
    row.deleted_at = datetime.now(UTC)
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post("/api/base-resumes/old_track/archive")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_list_exposes_render_error_and_archived_at(db_session):
    from datetime import UTC, datetime

    row = _seed(db_session, slug="data_scientist")
    row.render_error = "boom"
    row.archived_at = datetime(2026, 8, 4, tzinfo=UTC)
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/base-resumes?include_archived=true")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    item = response.json()[0]
    assert item["render_error"] == "boom"
    assert item["archived_at"] is not None
