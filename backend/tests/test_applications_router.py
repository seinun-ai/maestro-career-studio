import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from tests.pdf_fixtures import write_blank_pdf
import pytest
from fastapi.testclient import TestClient

from app.config import settings as app_settings
from app.db import get_db
from app.main import app
from app.models.application import Application
from app.models.job import Job
from app.models.template import Template
from app.routers import applications
from app.services import bullet_classify, pdf_render


def _write_valid_pdf(path: Path, pages: int = 1) -> None:
    """Write a real (rasterizable) PDF so the render path's page-image step works."""
    write_blank_pdf(path, pages)


def _stub_render_compilers(monkeypatch) -> None:
    def fake_run(argv, **kwargs):
        out_dir = Path(
            next(
                arg.removeprefix("-output-directory=")
                for arg in argv
                if arg.startswith("-output-directory=")
            )
        )
        jobname = next(
            arg.removeprefix("-jobname=")
            for arg in argv
            if arg.startswith("-jobname=")
        )
        _write_valid_pdf(out_dir / f"{jobname}.pdf")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(pdf_render.subprocess, "run", fake_run)

    def fake_typst_compile(**kwargs):
        _write_valid_pdf(Path(kwargs["output"]))

    monkeypatch.setattr(pdf_render.typst_compiler, "compile_typst", fake_typst_compile)


def _seed_render_templates(db_session) -> None:
    source = (pdf_render.TEMPLATE_DIR / pdf_render.RESUME_TEMPLATE).read_text(
        encoding="utf-8"
    )
    db_session.add_all(
        [
            Template(
                id="default",
                display_name="Classic",
                source=source,
                engine="latex",
                status="ready",
                is_default=True,
                origin="seed",
            ),
            Template(
                id="observed_template",
                display_name="Observed",
                source='#text("observed")',
                engine="typst",
                status="ready",
                is_default=False,
                origin="frontend",
            ),
        ]
    )
    db_session.commit()


def _override_db(db_session):
    def _inner():
        yield db_session

    return _inner


def _job(db_session, *, role_category="data_scientist"):
    job = Job(
        raw_text="Need Python",
        raw_text_hash=f"applications-{role_category}",
        extracted_json={"title": "Data Scientist", "company": "Acme"},
        title="Data Scientist",
        company="Acme",
        role_category=role_category,
        extracted_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def test_plain_create_application_endpoint_removed(db_session):
    """The legacy AI create path (POST /api/applications) is gone; only
    /from-base remains."""
    job = _job(db_session)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            "/api/applications",
            json={"job_id": str(job.id), "base_resume": "data_scientist"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 405


def test_list_and_detail_applications(db_session):
    job = _job(db_session, role_category="ai_ml_engineer")
    application = Application(job_id=job.id, base_resume="ai_ml_engineer", status="draft")
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        list_response = client.get("/api/applications?status=draft&role_category=ai_ml_engineer")
        detail_response = client.get(f"/api/applications/{application.id}")
    finally:
        app.dependency_overrides.clear()

    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == str(application.id)
    assert detail_response.status_code == 200
    assert detail_response.json()["job"]["title"] == "Data Scientist"


def test_list_applications_ignores_removed_not_applied_param(db_session):
    """The not_applied filter was removed (dead after the tracker rewrite —
    saved jobs come from /api/jobs?without_application). An old caller passing
    it gets the unfiltered list instead of an error."""
    job = _job(db_session, role_category="hybrid")
    pending = Application(job_id=job.id, base_resume="hybrid", status="draft")
    submitted = Application(
        job_id=job.id,
        base_resume="ai_ml_engineer",
        status="interviewing",
        applied_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    db_session.add_all([pending, submitted])
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get("/api/applications?not_applied=true")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    ids = {row["id"] for row in response.json()}
    assert {str(pending.id), str(submitted.id)} <= ids


def test_patch_application_updates_fields(db_session):
    job = _job(db_session)
    application = Application(job_id=job.id, base_resume="hybrid", status="draft")
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).patch(
            f"/api/applications/{application.id}",
            json={
                "status": "interviewing",
                "notes": "Applied through portal",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "interviewing"
    assert response.json()["notes"] == "Applied through portal"


def test_patch_application_rejects_unknown_status(db_session):
    """Status is a backend-owned vocabulary now (audit C3): PATCH must reject
    anything the tracker can't display or filter."""
    job = _job(db_session)
    application = Application(job_id=job.id, base_resume="hybrid", status="draft")
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).patch(
            f"/api/applications/{application.id}",
            json={"status": "submitted"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "submitted" in str(response.json()["detail"])


def test_render_application_uses_generic_role_in_filename(db_session, tmp_path, monkeypatch):
    job = _job(db_session)
    job.title = "Junior LLM Data Scientist"
    db_session.commit()
    application = Application(
        job_id=job.id,
        base_resume="data_scientist",
        status="draft",
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    monkeypatch.setattr(app_settings, "applications_dir", tmp_path)
    monkeypatch.setattr(
        applications.base_resume_data,
        "load_base_resume",
        lambda slug, session=None: {
            "contact": {"name": "Riley Quill", "email": "x@y.com"},
            "summary": "Data scientist",
            "skills": [],
            "experience": [],
            "projects": [],
            "education": [],
            "certifications": [],
        },
    )
    monkeypatch.setattr(
        pdf_render,
        "render_document",
        lambda data, **kw: pdf_render.RenderedDoc("latex", "rendered tex"),
    )

    def fake_compile_pdf(tex_text, out_dir, stem="resume"):
        (out_dir / f"{stem}.tex").write_text(tex_text, encoding="utf-8")
        path = out_dir / f"{stem}.pdf"
        _write_valid_pdf(path)
        return path

    monkeypatch.setattr(pdf_render, "compile_pdf", fake_compile_pdf)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(f"/api/applications/{application.id}/render")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["pdf_path"].endswith(
        "Riley_Quill_DataScientist_Resume.pdf"
    )


def test_render_application_generates_files_and_updates_paths(db_session, tmp_path, monkeypatch):
    job = _job(db_session)
    application = Application(
        job_id=job.id,
        base_resume="data_scientist",
        status="draft",
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    monkeypatch.setattr(app_settings, "applications_dir", tmp_path)
    monkeypatch.setattr(
        applications.base_resume_data,
        "load_base_resume",
        lambda slug, session=None: {
            "contact": {"name": "Riley Quill", "email": "x@y.com"},
            "summary": "Data scientist",
            "skills": [],
            "experience": [],
            "projects": [],
            "education": [],
            "certifications": [],
        },
    )
    monkeypatch.setattr(
        pdf_render,
        "render_document",
        lambda data, **kw: pdf_render.RenderedDoc("latex", "rendered tex"),
    )

    def fake_compile_pdf(tex_text, out_dir, stem="resume"):
        (out_dir / f"{stem}.tex").write_text(tex_text, encoding="utf-8")
        path = out_dir / f"{stem}.pdf"
        _write_valid_pdf(path)
        return path

    monkeypatch.setattr(pdf_render, "compile_pdf", fake_compile_pdf)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(f"/api/applications/{application.id}/render")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert Path(body["tex_path"]).read_text(encoding="utf-8") == "rendered tex"
    assert Path(body["pdf_path"]).exists()
    assert body["pdf_path"].endswith(
        "Riley_Quill_DataScientist_Resume.pdf"
    )

    db_session.refresh(application)
    # No tailored draft stored -> render snapshots the base resume as-is.
    assert application.customized_json["summary"] == "Data scientist"
    assert application.tex_path == body["tex_path"]
    assert application.pdf_path == body["pdf_path"]
    assert application.artifact_dir
    artifact = Path(application.artifact_dir)
    assert artifact.name.endswith(f"_{application.id.hex[:8]}")
    assert Path(application.pdf_path).parent == artifact


def test_render_application_typst_writes_typ_and_pdf(db_session, tmp_path, monkeypatch):
    pytest.importorskip("typst")
    from app.services import template_registry as reg
    from tests.test_pdf_render_typst import EXTRAS_TYP

    job = _job(db_session)
    application = Application(
        job_id=job.id,
        base_resume="data_scientist",
        status="draft",
        customized_json=_FULL_RESUME,
    )
    db_session.add(application)
    reg.create_draft(
        db_session,
        id="typst-router",
        display_name="Typst Router",
        source=EXTRAS_TYP,
        origin="mcp",
        engine="typst",
    )
    template = reg.get(db_session, "typst-router")
    template.status = "ready"
    db_session.commit()
    db_session.refresh(application)

    monkeypatch.setattr(app_settings, "applications_dir", tmp_path)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            f"/api/applications/{application.id}/render?template_id=typst-router"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    db_session.refresh(application)
    assert application.tex_path.endswith(".typ")
    assert Path(application.tex_path).exists()
    assert Path(application.pdf_path).exists()


def test_render_falls_back_for_unknown_template(db_session, tmp_path, monkeypatch):
    # Render stays tolerant of a stale/deleted persisted template_id: falls back
    # to the default template rather than 404-ing the render endpoint.
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is not installed")
    job = _job(db_session)
    application = Application(
        job_id=job.id,
        base_resume="data_scientist",
        status="draft",
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    monkeypatch.setattr(app_settings, "applications_dir", tmp_path)
    # A compile-clean sample so the fallback render actually produces a PDF; the
    # point under test is that a stale template_id no longer 404s.
    from app.services.template_validation import SAMPLE_RESUME

    monkeypatch.setattr(
        applications.base_resume_data,
        "load_base_resume",
        lambda slug, session=None: SAMPLE_RESUME,
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            f"/api/applications/{application.id}/render?template_id=nope"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


def test_render_application_reports_explicit_resolved_template(
    db_session, tmp_path, monkeypatch
):
    job = _job(db_session)
    application = Application(
        job_id=job.id,
        base_resume="data_scientist",
        status="draft",
        customized_json=_FULL_RESUME,
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    monkeypatch.setattr(app_settings, "applications_dir", tmp_path)
    _stub_render_compilers(monkeypatch)
    _seed_render_templates(db_session)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            f"/api/applications/{application.id}/render"
            "?template_id=observed_template"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    assert response.json()["resolved_template_id"] == "observed_template"
    assert response.json()["resolved_engine"] == "typst"
    assert response.json()["template_fallback"] is False


def test_render_application_reports_explicit_template_fallback(
    db_session, tmp_path, monkeypatch
):
    job = _job(db_session)
    application = Application(
        job_id=job.id,
        base_resume="data_scientist",
        status="draft",
        customized_json=_FULL_RESUME,
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    monkeypatch.setattr(app_settings, "applications_dir", tmp_path)
    _stub_render_compilers(monkeypatch)
    _seed_render_templates(db_session)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            f"/api/applications/{application.id}/render"
            "?template_id=bogus_template"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    assert response.json()["resolved_template_id"] == "default"
    assert response.json()["resolved_engine"] == "latex"
    assert response.json()["template_fallback"] is True


def test_render_400_failure_persists_render_error(db_session, tmp_path, monkeypatch):
    # A render failure that maps to 400 (a broken base resume raising ValueError)
    # must still persist application.render_error so quick-tailor's pdf_ready=false
    # leaves a readable reason — same as the 500 path (fix B2).
    job = _job(db_session)
    application = Application(
        job_id=job.id,
        base_resume="data_scientist",
        status="draft",
        customized_json=None,
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    monkeypatch.setattr(app_settings, "applications_dir", tmp_path)

    def boom(slug, session=None):
        raise ValueError("base resume is broken")

    monkeypatch.setattr(applications.base_resume_data, "load_base_resume", boom)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(f"/api/applications/{application.id}/render")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["detail"] == "base resume is broken"
    db_session.expire_all()
    assert db_session.get(Application, application.id).render_error == "base resume is broken"


def test_get_application_pdf_streams_file(db_session, tmp_path):
    job = _job(db_session)
    pdf_path = tmp_path / "260501_Quill_Riley_DataAnalyst_TechCorp_Resume.pdf"
    pdf_path.write_bytes(b"%PDF test")
    application = Application(
        job_id=job.id,
        base_resume="hybrid",
        status="draft",
        pdf_path=str(pdf_path),
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get(f"/api/applications/{application.id}/pdf")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == b"%PDF test"
    assert (
        response.headers["content-disposition"]
        == 'inline; filename="260501_Quill_Riley_DataAnalyst_TechCorp_Resume.pdf"'
    )


def test_delete_application_removes_files_and_row(db_session, tmp_path):
    job = _job(db_session)
    out_dir = tmp_path / "Acme_Role"
    out_dir.mkdir()
    pdf_path = out_dir / "resume.pdf"
    tex_path = out_dir / "resume.tex"
    pdf_path.write_bytes(b"%PDF")
    tex_path.write_text("\\documentclass{article}", encoding="utf-8")

    application = Application(
        job_id=job.id,
        base_resume="hybrid",
        status="draft",
        pdf_path=str(pdf_path),
        tex_path=str(tex_path),
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).delete(f"/api/applications/{application.id}")
        get_response = TestClient(app).get(f"/api/applications/{application.id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert get_response.status_code == 404
    assert not pdf_path.exists()
    assert not tex_path.exists()
    assert not out_dir.exists()


def test_patch_application_sets_referral_id(db_session):
    from app.models.referral import Referral

    job = _job(db_session, role_category="data_engineer")
    referral = Referral(company="Acme", careers_url="https://acme.example/careers")
    db_session.add(referral)
    application = Application(job_id=job.id, base_resume="data_engineer", status="draft")
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)
    db_session.refresh(referral)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        response = client.patch(
            f"/api/applications/{application.id}",
            json={"referral_id": str(referral.id)},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["referral_id"] == str(referral.id)
    finally:
        app.dependency_overrides.clear()


def test_patch_application_clears_referral_id(db_session):
    from app.models.referral import Referral

    job = _job(db_session, role_category="data_engineer")
    referral = Referral(company="Acme", careers_url="https://acme.example/careers")
    db_session.add(referral)
    db_session.commit()
    db_session.refresh(referral)
    application = Application(
        job_id=job.id, base_resume="data_engineer", status="draft", referral_id=referral.id
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        response = client.patch(
            f"/api/applications/{application.id}",
            json={"referral_id": None},
        )
        assert response.status_code == 200
        assert response.json()["referral_id"] is None
    finally:
        app.dependency_overrides.clear()


def test_materialize_resume_sets_customized_without_pdf(db_session, monkeypatch):
    job = _job(db_session)
    application = Application(
        job_id=job.id,
        base_resume="data_scientist",
        status="draft",
        customized_json={"summary": "stale draft"},
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    base = {
        "contact": {"name": "Riley Quill", "email": "x@y.com"},
        "summary": "Data scientist",
        "skills": [],
        "experience": [],
        "projects": [],
        "education": [],
        "certifications": [],
    }
    monkeypatch.setattr(
        applications.base_resume_data,
        "load_base_resume",
        lambda slug, session=None: dict(base),
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            f"/api/applications/{application.id}/materialize-resume"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    # Materialize now snapshots the base resume, replacing any stale draft.
    assert body["customized_json"] == base
    assert body["pdf_path"] is None


def test_patch_customized_json_unlinks_pdf(db_session, tmp_path):
    job = _job(db_session)
    pdf_path = tmp_path / "old.pdf"
    pdf_path.write_bytes(b"%PDF old")
    application = Application(
        job_id=job.id,
        base_resume="hybrid",
        status="draft",
        customized_json={"summary": "x"},
        pdf_path=str(pdf_path),
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).patch(
            f"/api/applications/{application.id}",
            json={
                "customized_json": {
                    "contact": {"name": "Riley Quill", "email": "x@y.com"},
                    "summary": "Edited",
                    "skills": [],
                    "experience": [],
                    "projects": [],
                    "education": [],
                    "certifications": [],
                }
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["customized_json"]["summary"] == "Edited"
    assert not pdf_path.exists()
    assert response.json()["pdf_path"] is None


def test_render_uses_saved_customized_json_without_recompute(
    db_session, tmp_path, monkeypatch
):
    job = _job(db_session)
    customized = {
        "contact": {"name": "Riley Quill", "email": "x@y.com"},
        "summary": "Saved draft only",
        "skills": [],
        "experience": [],
        "projects": [],
        "education": [],
        "certifications": [],
    }
    application = Application(
        job_id=job.id,
        base_resume="data_scientist",
        status="draft",
        customized_json=customized,
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    def boom(*args, **kwargs):
        raise AssertionError("load_base_resume should not run when customized_json is set")

    monkeypatch.setattr(applications.base_resume_data, "load_base_resume", boom)
    monkeypatch.setattr(app_settings, "applications_dir", tmp_path)
    monkeypatch.setattr(
        pdf_render,
        "render_document",
        lambda data, **kw: pdf_render.RenderedDoc("latex", "rendered tex"),
    )

    def fake_compile_pdf(tex_text, out_dir, stem="resume"):
        (out_dir / f"{stem}.tex").write_text(tex_text, encoding="utf-8")
        path = out_dir / f"{stem}.pdf"
        _write_valid_pdf(path)
        return path

    monkeypatch.setattr(pdf_render, "compile_pdf", fake_compile_pdf)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(f"/api/applications/{application.id}/render")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    db_session.refresh(application)
    assert application.customized_json["summary"] == "Saved draft only"


def test_list_applications_slim_summary_and_pagination(db_session):
    job = _job(db_session, role_category="data_engineer")
    for i in range(3):
        db_session.add(
            Application(
                job_id=job.id,
                base_resume="data_engineer",
                status="draft",
                customized_json={"contact": {"name": "X"}, "summary": "big blob"},
            )
        )
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        full = client.get("/api/applications").json()
        page = client.get("/api/applications?limit=2&offset=2").json()
    finally:
        app.dependency_overrides.clear()

    assert len(full) == 3
    row = full[0]
    # Slim summary keeps lightweight fields...
    assert row["job_id"] == str(job.id)
    assert row["base_resume"] == "data_engineer"
    assert "status" in row and "applied_at" in row and "created_at" in row
    # ...and drops the heavy JSON blob.
    assert "customized_json" not in row
    # limit+offset honored
    assert len(page) == 1


def test_create_application_from_base_applies_ops_server_side(db_session, monkeypatch):
    job = _job(db_session)
    base = {
        "contact": {"name": "Riley Quill", "email": "a@example.com"},
        "summary": "Base summary.",
        "skills": [{"category": "Languages", "items": ["Python"]}],
        "experience": [
            {"company": "Acme", "role": "DS", "start_date": "2020", "bullets": ["Old.", "Keep."]}
        ],
        "projects": [],
        "education": [],
        "certifications": [],
    }
    monkeypatch.setattr(
        applications.base_resume_data,
        "load_base_resume",
        lambda slug, session=None: __import__("copy").deepcopy(base),
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            "/api/applications/from-base",
            json={
                "job_id": str(job.id),
                "base_resume": "data_scientist",
                "ops": [
                    {
                        "kind": "replace_bullet",
                        "section": "experience",
                        "index": 0,
                        "bullet_index": 0,
                        "value": "Tailored bullet.",
                    }
                ],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["base_resume"] == "data_scientist"
    cj = body["customized_json"]
    assert cj["experience"][0]["bullets"] == ["Tailored bullet.", "Keep."]
    # Untouched fields inherited from the stored base, not resent by the caller.
    assert cj["summary"] == "Base summary."
    assert cj["skills"][0]["items"] == ["Python"]


def test_create_application_from_base_out_of_range_returns_400(db_session, monkeypatch):
    job = _job(db_session)
    monkeypatch.setattr(
        applications.base_resume_data,
        "load_base_resume",
        lambda slug, session=None: {
            "contact": {"name": "A", "email": "a@e.com"},
            "experience": [],
            "projects": [],
            "education": [],
            "skills": [],
            "certifications": [],
        },
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            "/api/applications/from-base",
            json={
                "job_id": str(job.id),
                "base_resume": "data_scientist",
                "ops": [
                    {
                        "kind": "replace_bullet",
                        "section": "experience",
                        "index": 3,
                        "bullet_index": 0,
                        "value": "x",
                    }
                ],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400


def test_from_base_auto_scores(db_session, tmp_path, monkeypatch):
    import json

    from app.config import settings as app_settings
    from app.models.ats_score import AtsScore
    from app.models.base_resume import BaseResume
    from tests.ats.fixtures import SAMPLE_JD, SAMPLE_RESUME

    job = _job(db_session)
    job.extracted_json = SAMPLE_JD
    monkeypatch.setattr(app_settings, "base_resumes_dir", tmp_path)
    (tmp_path / "data_scientist.json").write_text(json.dumps(SAMPLE_RESUME))
    db_session.add(BaseResume(slug="data_scientist", data_json=SAMPLE_RESUME))
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            "/api/applications/from-base",
            json={"job_id": str(job.id), "base_resume": "data_scientist", "ops": []},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    application_id = response.json()["id"]

    rows = db_session.query(AtsScore).filter(AtsScore.job_id == job.id).all()
    by_phase = {row.phase: row for row in rows}
    assert set(by_phase) == {"base", "tailored"}
    assert by_phase["base"].target_type == "base_resume"
    assert by_phase["base"].target_id == "data_scientist"
    assert by_phase["base"].application_id is None
    assert by_phase["tailored"].target_type == "application"
    assert str(by_phase["tailored"].application_id) == application_id


def test_from_base_without_extracted_skills_creates_without_scores(
    db_session, tmp_path, monkeypatch
):
    import json

    from app.config import settings as app_settings
    from app.models.ats_score import AtsScore
    from app.models.base_resume import BaseResume
    from tests.ats.fixtures import SAMPLE_RESUME

    job = _job(db_session)  # extracted_json has no "skills" key
    monkeypatch.setattr(app_settings, "base_resumes_dir", tmp_path)
    (tmp_path / "data_scientist.json").write_text(json.dumps(SAMPLE_RESUME))
    db_session.add(BaseResume(slug="data_scientist", data_json=SAMPLE_RESUME))
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            "/api/applications/from-base",
            json={"job_id": str(job.id), "base_resume": "data_scientist", "ops": []},
        )
    finally:
        app.dependency_overrides.clear()

    # Scoring failure must never fail creation.
    assert response.status_code == 200
    assert response.json()["customized_json"] is not None
    assert db_session.query(AtsScore).filter(AtsScore.job_id == job.id).count() == 0


def test_from_base_survives_unexpected_scoring_error(db_session, tmp_path, monkeypatch):
    import json
    from uuid import UUID

    from app.config import settings as app_settings
    from app.models.ats_score import AtsScore
    from app.models.base_resume import BaseResume
    from tests.ats.fixtures import SAMPLE_JD, SAMPLE_RESUME

    job = _job(db_session)
    job.extracted_json = SAMPLE_JD
    monkeypatch.setattr(app_settings, "base_resumes_dir", tmp_path)
    (tmp_path / "data_scientist.json").write_text(json.dumps(SAMPLE_RESUME))
    db_session.add(BaseResume(slug="data_scientist", data_json=SAMPLE_RESUME))
    db_session.commit()

    def _boom(*args, **kwargs):
        raise RuntimeError("engine exploded mid-score")

    monkeypatch.setattr(applications.ats_score, "score_target", _boom)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            "/api/applications/from-base",
            json={"job_id": str(job.id), "base_resume": "data_scientist", "ops": []},
        )
    finally:
        app.dependency_overrides.clear()

    # A non-ValueError raised after the application commit must not turn a
    # successful creation into a 500 (MCP callers would retry and duplicate).
    assert response.status_code == 200
    application_id = response.json()["id"]
    assert db_session.get(Application, UUID(application_id)) is not None
    assert db_session.query(AtsScore).filter(AtsScore.job_id == job.id).count() == 0


def test_create_application_from_base_unknown_job_returns_404(db_session, monkeypatch):
    from uuid import uuid4

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(
            "/api/applications/from-base",
            json={"job_id": str(uuid4()), "base_resume": "data_scientist", "ops": []},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 404


def test_patch_status_applied_sets_applied_at(db_session):
    job = _job(db_session)
    application = Application(job_id=job.id, base_resume="hybrid", status="draft")
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).patch(
            f"/api/applications/{application.id}",
            json={"status": "applied"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "applied"
    assert response.json()["applied_at"] is not None


def test_patch_status_away_from_applied_clears_applied_at(db_session):
    job = _job(db_session)
    application = Application(
        job_id=job.id,
        base_resume="hybrid",
        status="applied",
        applied_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).patch(
            f"/api/applications/{application.id}",
            json={"status": "draft"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["applied_at"] is None


def test_patch_explicit_applied_at_not_overridden(db_session):
    job = _job(db_session)
    application = Application(job_id=job.id, base_resume="hybrid", status="draft")
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).patch(
            f"/api/applications/{application.id}",
            json={"status": "applied", "applied_at": "2026-03-15T00:00:00Z"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    # Explicit value wins; auto-stamp must not clobber it.
    assert response.json()["applied_at"].startswith("2026-03-15")


def test_patch_status_applied_idempotent_preserves_original_applied_at(db_session):
    job = _job(db_session)
    application = Application(
        job_id=job.id,
        base_resume="hybrid",
        status="applied",
        applied_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).patch(
            f"/api/applications/{application.id}",
            json={"status": "applied"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    # Re-applying an already-applied status must preserve the original
    # applied_at, not re-stamp it to "now" (the `is None` guard ensures this).
    assert response.json()["applied_at"].startswith("2020-01-01")


def test_create_application_from_base_with_id_updates_in_place(db_session, monkeypatch):
    job = _job(db_session)
    base = {
        "contact": {"name": "Riley Quill", "email": "a@example.com"},
        "summary": "Base summary.",
        "skills": [],
        "experience": [],
        "projects": [],
        "education": [],
        "certifications": [],
    }
    monkeypatch.setattr(
        applications.base_resume_data, "load_base_resume", lambda slug, session=None: __import__("copy").deepcopy(base)
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        res1 = client.post(
            "/api/applications/from-base",
            json={"job_id": str(job.id), "base_resume": "data_scientist", "ops": []},
        )
        assert res1.status_code == 200
        app_id = res1.json()["id"]

        res2 = client.post(
            "/api/applications/from-base",
            json={
                "job_id": str(job.id),
                "base_resume": "data_scientist",
                "application_id": app_id,
                "ops": [
                    {
                        "kind": "replace_summary",
                        "value": "Updated in place.",
                    }
                ],
            },
        )
        assert res2.status_code == 200
        assert res2.json()["id"] == app_id
        assert res2.json()["customized_json"]["summary"] == "Updated in place."

        # Verify no duplicate was created
        all_apps = client.get("/api/applications").json()
        assert len(all_apps) == 1
    finally:
        app.dependency_overrides.clear()


def test_patch_application_edits_updates_customized_json(db_session, monkeypatch):
    job = _job(db_session)
    base = {
        "contact": {"name": "Riley Quill", "email": "a@example.com"},
        "summary": "Base summary.",
        "skills": [],
        "experience": [],
        "projects": [],
        "education": [],
        "certifications": [],
    }
    monkeypatch.setattr(
        applications.base_resume_data, "load_base_resume", lambda slug, session=None: __import__("copy").deepcopy(base)
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        res1 = client.post(
            "/api/applications/from-base",
            json={"job_id": str(job.id), "base_resume": "data_scientist", "ops": []},
        )
        app_id = res1.json()["id"]

        res2 = client.patch(
            f"/api/applications/{app_id}/edits",
            json={
                "ops": [
                    {
                        "kind": "replace_summary",
                        "value": "Edited via patch endpoint.",
                        "expected_content_hash": bullet_classify.content_hash(
                            "Base summary."
                        ),
                    }
                ]
            },
        )
        assert res2.status_code == 200
        assert res2.json()["customized_json"]["summary"] == "Edited via patch endpoint."
    finally:
        app.dependency_overrides.clear()


def test_patch_application_edits_hash_mismatch_returns_409_without_write(
    db_session, monkeypatch
):
    job = _job(db_session, role_category="content_hash_guard")
    base = {
        "contact": {"name": "Riley Quill", "email": "a@example.com"},
        "summary": "Base summary.",
        "skills": [],
        "experience": [],
        "projects": [],
        "education": [],
        "certifications": [],
    }
    monkeypatch.setattr(
        applications.base_resume_data,
        "load_base_resume",
        lambda slug, session=None: __import__("copy").deepcopy(base),
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        app_id = _app_from_base(client, job, base)
        response = client.patch(
            f"/api/applications/{app_id}/edits",
            json={
                "ops": [
                    {"kind": "replace_summary", "value": "Interim summary."},
                    {
                        "kind": "replace_summary",
                        "value": "Stale rewrite.",
                        "expected_content_hash": bullet_classify.content_hash(
                            "Report-time summary."
                        ),
                    },
                ]
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["detail"].startswith("content changed since analysis")
    db_session.expire_all()
    row = db_session.get(Application, app_id)
    assert row.customized_json["summary"] == "Base summary."


def _app_from_base(client, job, base):
    """Create an application seeded straight from `base` (no tailoring ops)."""
    res = client.post(
        "/api/applications/from-base",
        json={"job_id": str(job.id), "base_resume": "data_scientist", "ops": []},
    )
    return res.json()["id"]


def test_patch_application_extra_section_ops_round_trip(db_session, monkeypatch):
    import copy

    # Distinct role_category -> distinct jobs.raw_text_hash so this test never
    # contends on the shared "applications-data_scientist" hash used elsewhere.
    job = _job(db_session, role_category="custom_sections_e2e")
    base = {
        "contact": {"name": "Riley Quill", "email": "a@example.com"},
        "summary": "Base summary.",
        "skills": [],
        "experience": [],
        "projects": [],
        "education": [],
        "certifications": [],
    }
    monkeypatch.setattr(
        applications.base_resume_data,
        "load_base_resume",
        lambda slug, session=None: copy.deepcopy(base),
    )
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        app_id = _app_from_base(client, job, base)

        # all four ops end to end on the application's customized_json.
        ok = client.patch(
            f"/api/applications/{app_id}/edits",
            json={"ops": [
                {"kind": "add_extra_section",
                 "value": {"key": "awards", "title": "Awards", "type": "bullets",
                           "bullets": ["First place, 2025"]}},
                {"kind": "add_extra_section",
                 "value": {"key": "volunteer", "title": "Volunteer", "type": "entries",
                           "entries": [{"heading": "Mentor", "date": "2024"}]}},
                {"kind": "move_extra_section", "section_key": "volunteer", "to_index": 0},
                {"kind": "replace_extra_section", "section_key": "awards",
                 "value": {"key": "awards", "title": "Honors", "type": "bullets",
                           "bullets": ["First place, 2025"]}},
                {"kind": "remove_extra_section", "section_key": "volunteer"},
            ]},
        )
        assert ok.status_code == 200
        sections = ok.json()["customized_json"]["extra_sections"]
        assert [s["key"] for s in sections] == ["awards"]
        assert sections[0]["title"] == "Honors"

        # unknown key -> 400
        bad = client.patch(
            f"/api/applications/{app_id}/edits",
            json={"ops": [{"kind": "remove_extra_section", "section_key": "nope"}]},
        )
        assert bad.status_code == 400
        assert "no extra section with key" in bad.json()["detail"]

        # duplicate key on add -> 400
        dup = client.patch(
            f"/api/applications/{app_id}/edits",
            json={"ops": [{"kind": "add_extra_section",
                           "value": {"key": "awards", "title": "Dup", "type": "bullets",
                                     "bullets": ["x"]}}]},
        )
        assert dup.status_code == 400
        assert "duplicate" in dup.json()["detail"]

        # atomic failure: a valid op followed by a failing one persists nothing.
        atomic = client.patch(
            f"/api/applications/{app_id}/edits",
            json={"ops": [
                {"kind": "remove_extra_section", "section_key": "awards"},
                {"kind": "move_extra_section", "section_key": "awards", "to_index": 9},
            ]},
        )
        assert atomic.status_code == 400
        after = client.get(f"/api/applications/{app_id}").json()
        assert [s["key"] for s in after["customized_json"]["extra_sections"]] == ["awards"]
    finally:
        app.dependency_overrides.clear()


_FULL_RESUME = {
    "contact": {"name": "Riley Quill", "email": "x@y.com"},
    "summary": "Data scientist",
    "skills": [{"category": "Core", "items": ["Python"]}],
    "experience": [],
    "projects": [],
    "education": [],
    "certifications": [],
}


def test_application_formatting_inherits_and_overrides(db_session, tmp_path, monkeypatch):
    from app.models.base_resume import BaseResume
    from app.services import pdf_render as pdf_render_mod

    job = _job(db_session)
    db_session.add(
        BaseResume(
            slug="data_scientist",
            display_name="DS",
            data_json=_FULL_RESUME,
            formatting_json={"font_size": 12},
        )
    )
    application = Application(
        job_id=job.id,
        base_resume="data_scientist",
        status="draft",
        customized_json=_FULL_RESUME,
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    monkeypatch.setattr(app_settings, "applications_dir", tmp_path)
    orig_render_document = pdf_render_mod.render_document

    def fake_render_document(data, *, template_id=None, session=None, formatting=None):
        # session=None -> use the on-disk fmt-parameterized template
        return orig_render_document(data, formatting=formatting)

    monkeypatch.setattr(pdf_render, "render_document", fake_render_document)

    def fake_compile_pdf(tex_text, out_dir, stem="resume"):
        (out_dir / f"{stem}.tex").write_text(tex_text, encoding="utf-8")
        path = out_dir / f"{stem}.pdf"
        _write_valid_pdf(path)
        return path

    monkeypatch.setattr(pdf_render, "compile_pdf", fake_compile_pdf)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)

        # No application-level formatting -> inherits base's font_size 12.
        r1 = client.post(f"/api/applications/{application.id}/render")
        assert r1.status_code == 200
        assert "12pt" in Path(r1.json()["tex_path"]).read_text(encoding="utf-8")

        # PATCH an override -> application formatting wins over base.
        patch = client.patch(
            f"/api/applications/{application.id}",
            json={"formatting": {"font_size": 10}},
        )
        assert patch.status_code == 200
        assert patch.json()["formatting"] == {"font_size": 10}

        r2 = client.post(f"/api/applications/{application.id}/render")
        assert r2.status_code == 200
        assert "10pt" in Path(r2.json()["tex_path"]).read_text(encoding="utf-8")
    finally:
        app.dependency_overrides.clear()

    db_session.refresh(application)
    assert application.formatting_json == {"font_size": 10}


def test_preview_manifest_and_page(db_session, tmp_path):
    job = _job(db_session)
    pdf_path = tmp_path / "app.pdf"
    _write_valid_pdf(pdf_path, pages=1)
    application = Application(
        job_id=job.id,
        base_resume="data_scientist",
        status="draft",
        pdf_path=str(pdf_path),
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        manifest = client.get(f"/api/applications/{application.id}/preview/pages")
        page = client.get(f"/api/applications/{application.id}/preview/page/1")
        missing = client.get(f"/api/applications/{application.id}/preview/page/99")
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
    job = _job(db_session)
    application = Application(job_id=job.id, base_resume="data_scientist", status="draft")
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        manifest = client.get(f"/api/applications/{application.id}/preview/pages")
        page = client.get(f"/api/applications/{application.id}/preview/page/1")
    finally:
        app.dependency_overrides.clear()

    assert manifest.status_code == 404
    assert page.status_code == 404


def test_patch_persists_template_id(db_session):
    """PATCH persists template_id and it round-trips on GET / in the response."""
    job = _job(db_session)
    application = Application(job_id=job.id, base_resume="data_scientist", status="draft")
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        resp = client.patch(
            f"/api/applications/{application.id}", json={"template_id": "themed"}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["template_id"] == "themed"

        got = client.get(f"/api/applications/{application.id}")
        assert got.status_code == 200
        assert got.json()["template_id"] == "themed"
    finally:
        app.dependency_overrides.clear()


def test_render_application_uses_stored_template_id(db_session, tmp_path, monkeypatch):
    """render_application falls back to application.template_id when the query
    param is absent; an explicit query param still wins."""
    job = _job(db_session)
    application = Application(
        job_id=job.id,
        base_resume="data_scientist",
        status="draft",
        template_id="stored_tmpl",
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    monkeypatch.setattr(app_settings, "applications_dir", tmp_path)
    monkeypatch.setattr(
        applications.base_resume_data,
        "load_base_resume",
        lambda slug, session=None: {
            "contact": {"name": "Riley Quill", "email": "x@y.com"},
            "summary": "Data scientist",
            "skills": [],
            "experience": [],
            "projects": [],
            "education": [],
            "certifications": [],
        },
    )

    captured = {}

    def fake_render_document(data, **kw):
        captured["template_id"] = kw.get("template_id")
        return pdf_render.RenderedDoc("latex", "rendered tex")

    monkeypatch.setattr(
        pdf_render, "render_document", fake_render_document
    )

    def fake_compile_pdf(tex_text, out_dir, stem="resume"):
        (out_dir / f"{stem}.tex").write_text(tex_text, encoding="utf-8")
        path = out_dir / f"{stem}.pdf"
        _write_valid_pdf(path)
        return path

    monkeypatch.setattr(pdf_render, "compile_pdf", fake_compile_pdf)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        # No query param -> use the stored template_id.
        resp = client.post(f"/api/applications/{application.id}/render")
        assert resp.status_code == 200, resp.text
        assert captured["template_id"] == "stored_tmpl"

        # Explicit query param overrides the stored choice.
        resp = client.post(
            f"/api/applications/{application.id}/render?template_id=override_tmpl"
        )
        assert resp.status_code == 200, resp.text
        assert captured["template_id"] == "override_tmpl"
    finally:
        app.dependency_overrides.clear()


def _ready_no_extras_template(db_session, tid: str) -> None:
    """A ready template whose source never references extra_sections — routing an
    extras-bearing resume through it must hard-fail (F1)."""
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


def test_render_incompatible_template_returns_400_not_500(db_session, tmp_path, monkeypatch):
    # F1: an extras-bearing resume rendered through a template that cannot render
    # custom sections must surface a clean, user-actionable 400 with the message
    # (TemplateMissingExtraSectionsError now subclasses ValueError) — never the
    # generic-Exception 500 branch it used to fall into.
    monkeypatch.setattr(app_settings, "applications_dir", tmp_path)
    job = _job(db_session)
    _ready_no_extras_template(db_session, "noextra_app")
    application = Application(
        job_id=job.id,
        base_resume="data_scientist",
        status="draft",
        template_id="noextra_app",
        customized_json={
            "contact": {"name": "Riley Quill", "email": "x@y.com"},
            "extra_sections": [
                {
                    "key": "awards",
                    "title": "Awards",
                    "type": "bullets",
                    "bullets": ["First place, Regional Hackathon"],
                }
            ],
        },
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).post(f"/api/applications/{application.id}/render")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert "custom section" in detail.lower()
    assert "awards" in detail  # names the offending section key


def test_list_applications_filters_by_source(db_session):
    job = _job(db_session)
    app_user = Application(job_id=job.id, base_resume="hybrid", source="user")
    app_agent = Application(job_id=job.id, base_resume="hybrid", source="agent")
    db_session.add_all([app_user, app_agent])
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        res_agent = client.get("/api/applications?source=agent")
        res_user = client.get("/api/applications?source=user")
        res_invalid = client.get("/api/applications?source=invalid")
    finally:
        app.dependency_overrides.clear()

    assert res_agent.status_code == 200
    assert len(res_agent.json()) == 1 and res_agent.json()[0]["id"] == str(app_agent.id)
    assert res_user.status_code == 200
    assert len(res_user.json()) == 1 and res_user.json()[0]["id"] == str(app_user.id)
    assert res_invalid.status_code == 422


def test_marking_applied_closes_open_proposals_for_the_job(db_session):
    # User override: they applied manually from the job workspace. Flipping the
    # StatusChip to applied must resolve the job's open proposal instead of
    # leaving it squatting in the triage/queued lanes (2026-08-01 request).
    from app.models.consent_event import ConsentEvent
    from app.services import proposals as svc

    job = _job(db_session)
    job.source = "agent"
    app_row = Application(job_id=job.id, base_resume="hybrid", source="agent")
    db_session.add(app_row)
    db_session.commit()
    prop = svc.create_proposal(
        db_session, job_id=job.id, application_id=app_row.id,
        fit={"chosen_base": "hybrid"}, plan={},
    )
    svc.transition(db_session, prop, "accepted", consent={"channel": "frontend"})

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        resp = TestClient(app).patch(
            f"/api/applications/{app_row.id}", json={"status": "applied"}
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    db_session.refresh(prop)
    assert prop.status == "rejected"
    assert prop.reason == "applied manually"
    assert db_session.query(ConsentEvent).filter_by(
        proposal_id=prop.id, action="rejected").count() == 1


def test_marking_applied_releases_an_approved_proposals_cap_slot(db_session):
    from app.services import proposals as svc

    job = _job(db_session)
    job.source = "agent"
    app_row = Application(job_id=job.id, base_resume="hybrid", source="agent")
    db_session.add(app_row)
    db_session.commit()
    prop = svc.create_proposal(
        db_session, job_id=job.id, application_id=app_row.id,
        fit={"chosen_base": "hybrid"}, plan={},
    )
    prop.evidence_json = [{
        "step": 99, "label": "final review", "path": "evidence/fr.png",
        "sha256": "fr", "kind": "final_review",
    }]
    svc.transition(db_session, prop, "approved", consent={"channel": "chat"})
    assert prop.cap_reserved_at is not None

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        resp = TestClient(app).patch(
            f"/api/applications/{app_row.id}", json={"status": "applied"}
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    db_session.refresh(prop)
    assert prop.status == "rejected"
    assert prop.cap_reserved_at is None  # slot freed for the agent lane


def test_non_applied_status_changes_leave_proposals_open(db_session):
    from app.services import proposals as svc

    job = _job(db_session)
    job.source = "agent"
    app_row = Application(job_id=job.id, base_resume="hybrid", source="agent")
    db_session.add(app_row)
    db_session.commit()
    prop = svc.create_proposal(
        db_session, job_id=job.id, application_id=app_row.id,
        fit={"chosen_base": "hybrid"}, plan={},
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        # rejected/withdrawn on the APPLICATION don't imply you applied — the
        # proposal stays open for the user to triage deliberately.
        resp = TestClient(app).patch(
            f"/api/applications/{app_row.id}", json={"status": "withdrawn"}
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    db_session.refresh(prop)
    assert prop.status == "pending_review"


def test_list_applications_summary_includes_source(db_session):
    job = _job(db_session)
    app_row = Application(job_id=job.id, base_resume="hybrid", source="agent")
    db_session.add(app_row)
    db_session.commit()
    db_session.refresh(app_row)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        resp = TestClient(app).get("/api/applications")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    row = next(r for r in resp.json() if r["id"] == str(app_row.id))
    assert row["source"] == "agent"


# --- GET /api/applications/{id}/resume-diff (Task 12) -----------------------


def test_resume_diff_404_unknown_application(db_session):
    from uuid import uuid4

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get(f"/api/applications/{uuid4()}/resume-diff")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_resume_diff_409_when_customized_json_empty(db_session):
    job = _job(db_session)
    application = Application(
        job_id=job.id, base_resume="data_scientist", status="draft", customized_json=None
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get(f"/api/applications/{application.id}/resume-diff")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409


def test_resume_diff_happy_path_attributes_via_newest_session(db_session, monkeypatch):
    from copy import deepcopy

    from app.models.tailoring_session import TailoringSession

    base = {
        "contact": {"name": "Riley Quill", "email": "r@example.com"},
        "summary": "Original summary.",
        "skills": [{"category": "Core", "items": ["Python"]}],
        "experience": [],
        "projects": [
            {
                "name": "RAG Search",
                "enabled": False,
                "bullets": ["Built retrieval pipeline."],
            }
        ],
        "education": [],
        "certifications": [],
        "extra_sections": [],
    }
    customized = deepcopy(base)
    customized["projects"][0]["enabled"] = True
    customized["summary"] = "Tailored summary."

    job = _job(db_session)
    application = Application(
        job_id=job.id,
        base_resume="data_scientist",
        status="draft",
        customized_json=customized,
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    older = TailoringSession(
        job_id=job.id,
        base_resume="data_scientist",
        status="superseded",
        gaps_json={"categories": []},
        resolutions_json=[],
        application_id=application.id,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    newer = TailoringSession(
        job_id=job.id,
        base_resume="data_scientist",
        status="tailored",
        gaps_json={"categories": []},
        resolutions_json=[
            {
                "gap_id": "skill:kafka",
                "action": "enable_entry",
                "payload": {
                    "section": "projects",
                    "index": 0,
                    "provenance": {"source": "library_auto"},
                },
            }
        ],
        application_id=application.id,
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
    )
    db_session.add_all([older, newer])
    db_session.commit()
    db_session.refresh(newer)

    monkeypatch.setattr(
        applications.base_resume_data,
        "load_base_resume",
        lambda slug, session=None: deepcopy(base),
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get(f"/api/applications/{application.id}/resume-diff")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["session_id"] == str(newer.id)
    kinds = {(h["kind"], h.get("provenance")) for h in body["hunks"]}
    assert ("entry_enabled", "kb_auto") in kinds
    assert ("summary_changed", "llm") in kinds


def test_resume_diff_no_session_defaults_all_llm(db_session, monkeypatch):
    from copy import deepcopy

    base = {
        "contact": {"name": "Riley Quill", "email": "r@example.com"},
        "summary": "Original.",
        "skills": [],
        "experience": [],
        "projects": [],
        "education": [],
        "certifications": [],
    }
    customized = deepcopy(base)
    customized["summary"] = "Changed."

    job = _job(db_session)
    application = Application(
        job_id=job.id,
        base_resume="data_scientist",
        status="draft",
        customized_json=customized,
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)

    monkeypatch.setattr(
        applications.base_resume_data,
        "load_base_resume",
        lambda slug, session=None: deepcopy(base),
    )

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        response = TestClient(app).get(f"/api/applications/{application.id}/resume-diff")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["session_id"] is None
    assert body["hunks"]
    assert all(h["provenance"] == "llm" for h in body["hunks"])



def test_coherence_check_409_when_not_tailored_and_flags_pass_through(
    db_session, monkeypatch
):
    from app.services import coherence_check as coherence_service

    job = _job(db_session)
    bare = Application(
        job_id=job.id, base_resume="data_scientist", status="draft", customized_json=None
    )
    db_session.add(bare)
    db_session.commit()
    db_session.refresh(bare)

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        assert client.post(f"/api/applications/{bare.id}/coherence-check").status_code == 409

        monkeypatch.setattr(
            coherence_service,
            "run",
            lambda base, customized, session, template_id=None: {
                "flags": [{"issue": "tense"}]
            },
        )
        monkeypatch.setattr(
            "app.routers.applications.base_resume_data.load_base_resume",
            lambda slug, session=None: {"projects": []},
        )
        bare.customized_json = {"projects": []}
        db_session.commit()
        response = client.post(f"/api/applications/{bare.id}/coherence-check")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"flags": [{"issue": "tense"}]}
