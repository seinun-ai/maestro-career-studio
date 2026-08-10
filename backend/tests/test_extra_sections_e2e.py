"""End-to-end integration smoke for custom (extra) resume sections.

Exercises the whole phase-1 pipeline through the real HTTP surface:

  1. create a base resume that carries extras via ``POST /api/base-resumes``;
  2. render its stored data and assert extra-section text reaches the ``.tex``;
  3. build a from-base application (extras inherited into ``customized_json``);
  4. apply a typed ``add_extra_section`` edit op via ``PATCH .../edits``;
  5. read the resulting version diff and assert it names the new section.

Rendering is asserted at the ``.tex`` layer (pdflatex-free) so the smoke runs
in any environment; the PDF/extraction fidelity path is covered separately in
test_extra_sections_render.py.
"""
import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.config import settings
from app.db import get_db
from app.main import app
from app.models.base_resume import BaseResume
from app.models.job import Job
from app.services import base_resume_render, pdf_render


def _override_db(db_session):
    def _inner():
        yield db_session

    return _inner


def _job(db_session) -> Job:
    # No "skills" in extracted_json -> from-base auto-score is cleanly skipped
    # (best-effort), so the smoke needs no embeddings model.
    job = Job(
        raw_text="Need Python",
        raw_text_hash="extra-sections-e2e",
        extracted_json={"title": "Data Scientist", "company": "Acme"},
        title="Data Scientist",
        company="Acme",
        role_category="data_scientist",
        extracted_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


BASE_DATA = {
    "contact": {"name": "Sample Applicant", "email": "sample@example.com", "location": "SF, CA"},
    "summary": "Data scientist.",
    "skills": [{"category": "Languages", "items": ["Python"]}],
    "experience": [
        {
            "company": "DataCo",
            "role": "Data Scientist",
            "start_date": "Jul 2023",
            "bullets": ["Shipped forecasting models."],
        }
    ],
    "extra_sections": [
        {
            "key": "publications",
            "title": "Publications",
            "type": "entries",
            "entries": [
                {
                    "heading": "Deep Learning at Scale",
                    "subheading": "NeurIPS",
                    "date": "2023",
                    "link": "https://example.com/paper",
                    "bullets": ["Cited over 100 times."],
                }
            ],
        },
        {
            "key": "awards",
            "title": "Awards & Honors",
            "type": "bullets",
            "bullets": ["First place, Regional Hackathon, 2024"],
        },
    ],
}


def test_extra_sections_e2e_create_render_frombase_edit_diff(
    db_session, tmp_path, monkeypatch
):
    # Keep base JSON writes/reads inside the test tmp dir, and stub the actual
    # pdflatex render invoked by create (the .tex is asserted directly below).
    monkeypatch.setattr(settings, "base_resumes_dir", tmp_path)
    monkeypatch.setattr(
        base_resume_render, "render_base_resume", lambda slug, db, **kw: None
    )

    job = _job(db_session)
    client = TestClient(app)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        # 1. Create the base resume WITH extras via the API.
        create = client.post(
            "/api/base-resumes",
            json={"slug": "ds_extras", "display_name": "DS", "data": BASE_DATA},
        )
        assert create.status_code == 200, create.text
        created_sections = create.json()["data"]["extra_sections"]
        assert [s["key"] for s in created_sections] == ["publications", "awards"]

        # Persisted to DB JSONB and the on-disk mirror.
        row = db_session.get(BaseResume, "ds_extras")
        assert [s["key"] for s in row.data_json["extra_sections"]] == [
            "publications",
            "awards",
        ]
        on_disk = json.loads((tmp_path / "ds_extras.json").read_text(encoding="utf-8"))
        assert [s["key"] for s in on_disk["extra_sections"]] == ["publications", "awards"]

        # 2. Render the stored base data: extras reach the .tex output.
        tex = pdf_render.render_document(row.data_json).source_text
        assert r"\section{Publications}" in tex
        assert "Deep Learning at Scale" in tex  # entry heading
        assert "Cited over 100 times." in tex  # entry bullet
        assert r"\section{Awards \& Honors}" in tex  # bullets-section title (escaped)
        assert "First place, Regional Hackathon, 2024" in tex

        # 3. From-base application inherits the extras into customized_json.
        frombase = client.post(
            "/api/applications/from-base",
            json={"job_id": str(job.id), "base_resume": "ds_extras", "ops": []},
        )
        assert frombase.status_code == 200, frombase.text
        application_id = frombase.json()["id"]
        inherited = frombase.json()["customized_json"]["extra_sections"]
        assert [s["key"] for s in inherited] == ["publications", "awards"]

        # 4. Apply a typed add_extra_section edit op.
        edit = client.patch(
            f"/api/applications/{application_id}/edits",
            json={
                "ops": [
                    {
                        "kind": "add_extra_section",
                        "value": {
                            "key": "volunteer",
                            "title": "Volunteer Work",
                            "type": "bullets",
                            "bullets": ["Habitat for Humanity build, 2025"],
                        },
                    }
                ]
            },
        )
        assert edit.status_code == 200, edit.text
        edited = edit.json()["customized_json"]["extra_sections"]
        assert [s["key"] for s in edited] == ["publications", "awards", "volunteer"]

        # 5. The version diff for the edit names the newly added custom section.
        versions = client.get(
            f"/api/resume-versions/application/{application_id}"
        ).json()
        latest = max(v["version_number"] for v in versions)
        assert latest >= 2, versions  # from-base v1, edit-ops v2
        diff = client.get(
            f"/api/resume-versions/application/{application_id}/{latest}/diff"
        ).json()
    finally:
        app.dependency_overrides.clear()

    added = [
        c
        for c in diff
        if c.get("section") == "extra" and c.get("kind") == "added"
    ]
    assert any(c.get("label") == "Volunteer Work" for c in added), diff
