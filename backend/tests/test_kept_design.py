"""A design kept on a resume: its template and look settings, so later renders use them.

A base resume keeps one through `PATCH /api/base-resumes/{slug}/design`, which writes the
template and formatting only (no resume data, no version, no render), with the PUT's rules:
omitted is unchanged, null resets, and formatting passes the same write gate. A tailored resume
keeps one through its own PATCH (`template_id`, `formatting`). A one-off render with a
template_id leaves the kept design as it was. The compilers are faked; the render inputs are
what is checked."""

from pathlib import Path

from app.config import settings
from app.models.application import Application
from app.models.base_resume import BaseResume
from app.models.resume_version import ResumeVersion
from app.services import base_resume_render, pdf_render
from tests.pdf_fixtures import write_blank_pdf
from tests.test_applications_router import _job, _seed_render_templates

RESUME = {
    "contact": {"name": "Sample Person", "email": "sample@example.org"},
    "summary": "Field technician for renewable energy sites.",
    "skills": [{"category": "Core", "items": ["SCADA"]}],
    "experience": [],
    "projects": [],
    "education": [],
    "certifications": [],
}
KEPT_LOOK = {"font_size": 10, "header_align": "left"}


def _base(db_session, slug="field_tech", **extra):
    row = BaseResume(slug=slug, display_name="Field Tech", data_json=RESUME, **extra)
    db_session.add(row)
    db_session.commit()
    return row


def _capture_base_renders(monkeypatch, tmp_path) -> list[dict]:
    monkeypatch.setattr(settings, "base_resumes_dir", tmp_path)
    seen: list[dict] = []

    def fake_render_and_compile(data, tex_path, pdf_path, **kw):
        seen.append({"template_id": kw.get("template_id"), "formatting": kw.get("formatting")})
        tex_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        tex_path.write_text("tex", encoding="utf-8")
        write_blank_pdf(pdf_path)
        return tex_path, pdf_render.RenderedDoc("latex", "tex", resolved_template_id=kw.get("template_id") or "default")

    monkeypatch.setattr(base_resume_render.pdf_render, "render_and_compile", fake_render_and_compile)
    return seen


def _capture_application_renders(monkeypatch, tmp_path) -> list[dict]:
    monkeypatch.setattr(settings, "applications_dir", tmp_path)
    seen: list[dict] = []

    def fake_render_document(data, *, template_id=None, session=None, formatting=None):
        seen.append({"template_id": template_id, "formatting": formatting})
        return pdf_render.RenderedDoc("latex", "tex", resolved_template_id=template_id or "default")

    def fake_compile_document(doc, out_dir, stem="resume"):
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{stem}.tex").write_text("tex", encoding="utf-8")
        write_blank_pdf(out_dir / f"{stem}.pdf")
        return out_dir / f"{stem}.tex", out_dir / f"{stem}.pdf"

    monkeypatch.setattr(pdf_render, "render_document", fake_render_document)
    monkeypatch.setattr(pdf_render, "compile_document", fake_compile_document)
    return seen


def test_the_design_route_keeps_the_template_and_look_and_nothing_else(db_session, client, tmp_path, monkeypatch):
    renders = _capture_base_renders(monkeypatch, tmp_path)
    _base(db_session)

    response = client.patch("/api/base-resumes/field_tech/design",
                            json={"template_id": "observed_template", "formatting": KEPT_LOOK})

    assert response.status_code == 200, response.text
    assert (response.json()["template_id"], response.json()["formatting"]) == ("observed_template", KEPT_LOOK)
    db_session.expire_all()
    row = db_session.get(BaseResume, "field_tech")
    assert (row.template_id, row.formatting_json, row.data_json) == ("observed_template", KEPT_LOOK, RESUME)
    assert renders == []  # keeping is not rendering
    assert db_session.query(ResumeVersion).count() == 0  # the resume's text did not change


def test_an_omitted_field_stays_and_null_resets(db_session, client):
    _base(db_session, template_id="observed_template", formatting_json={"font_size": 12})

    look_only = client.patch("/api/base-resumes/field_tech/design", json={"formatting": KEPT_LOOK}).json()
    reset = client.patch("/api/base-resumes/field_tech/design", json={"template_id": None}).json()

    assert (look_only["template_id"], look_only["formatting"]) == ("observed_template", KEPT_LOOK)
    assert (reset["template_id"], reset["formatting"]) == (None, KEPT_LOOK)


def test_a_bad_look_is_refused_and_nothing_is_kept(db_session, client):
    _base(db_session)

    out_of_range = client.patch("/api/base-resumes/field_tech/design",
                                json={"template_id": "observed_template", "formatting": {"font_size": 99}})
    typo = client.patch("/api/base-resumes/field_tech/design", json={"formatting": {"section_order": ["skils"]}})
    unknown = client.patch("/api/base-resumes/field_tech/design", json={"formatting": {"bogus": True}})

    assert out_of_range.status_code == typo.status_code == unknown.status_code == 400
    db_session.expire_all()
    row = db_session.get(BaseResume, "field_tech")
    assert (row.template_id, row.formatting_json) == (None, None)


def test_an_unknown_base_resume_is_a_404(db_session, client):
    assert client.patch("/api/base-resumes/nobody/design", json={"template_id": "default"}).status_code == 404


def test_a_later_edit_re_renders_the_base_in_the_kept_design(db_session, client, tmp_path, monkeypatch):
    _seed_render_templates(db_session)
    renders = _capture_base_renders(monkeypatch, tmp_path)
    _base(db_session)
    client.patch("/api/base-resumes/field_tech/design",
                 json={"template_id": "observed_template", "formatting": KEPT_LOOK})

    edited = client.patch("/api/base-resumes/field_tech/edits",
                          json={"ops": [{"kind": "replace_summary", "value": "Wind and solar site technician."}]})

    assert edited.status_code == 200, edited.text
    assert renders == [{"template_id": "observed_template", "formatting": KEPT_LOOK}]


def test_a_one_off_base_render_leaves_the_kept_design(db_session, client, tmp_path, monkeypatch):
    _seed_render_templates(db_session)
    renders = _capture_base_renders(monkeypatch, tmp_path)
    _base(db_session, template_id="observed_template", formatting_json=KEPT_LOOK)

    rendered = client.post("/api/base-resumes/field_tech/render", params={"template_id": "default"})

    assert rendered.status_code == 200, rendered.text
    assert renders[-1]["template_id"] == "default"
    db_session.expire_all()
    row = db_session.get(BaseResume, "field_tech")
    assert (row.template_id, row.formatting_json) == ("observed_template", KEPT_LOOK)


def _application(db_session):
    job = _job(db_session)
    _base(db_session)
    application = Application(job_id=job.id, base_resume="field_tech", status="draft", customized_json=RESUME)
    db_session.add(application)
    db_session.commit()
    return application


def test_a_kept_application_design_is_used_by_the_render_after_an_edit(db_session, client, tmp_path, monkeypatch):
    _seed_render_templates(db_session)
    renders = _capture_application_renders(monkeypatch, tmp_path)
    application = _application(db_session)
    kept = client.patch(f"/api/applications/{application.id}",
                        json={"template_id": "observed_template", "formatting": KEPT_LOOK})
    assert kept.status_code == 200, kept.text

    client.patch(f"/api/applications/{application.id}/edits",
                 json={"ops": [{"kind": "replace_summary", "value": "Solar site technician."}]})
    rendered = client.post(f"/api/applications/{application.id}/render")

    assert rendered.status_code == 200, rendered.text
    assert renders == [{"template_id": "observed_template", "formatting": KEPT_LOOK}]


def test_a_one_off_application_render_leaves_the_kept_design(db_session, client, tmp_path, monkeypatch):
    _seed_render_templates(db_session)
    renders = _capture_application_renders(monkeypatch, tmp_path)
    application = _application(db_session)
    application.template_id, application.formatting_json = "observed_template", KEPT_LOOK
    db_session.commit()

    rendered = client.post(f"/api/applications/{application.id}/render", params={"template_id": "default"})

    assert rendered.status_code == 200, rendered.text
    assert renders[-1]["template_id"] == "default"
    db_session.expire_all()
    row = db_session.get(Application, application.id)
    assert (row.template_id, row.formatting_json) == ("observed_template", KEPT_LOOK)
    assert Path(row.pdf_path).exists()
