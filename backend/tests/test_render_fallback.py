"""Design 2026-09-19 §2.2: a render never changes engine silently, and a
missing pdflatex is an actionable error, never a 500 from FileNotFoundError."""
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings as app_settings
from app.db import get_db
from app.main import app
from app.models.application import Application
from app.models.template import Template
from app.routers import applications as applications_router
from app.services import engines, pdf_render
from app.services import template_registry as reg
from app.services.template_validation import SAMPLE_RESUME
from tests.test_applications_router import _job
from tests.test_base_resumes_router import _override_db, _seed

MINIMAL_TEX = "\\documentclass{article}\\begin{document}x\\end{document}"


def _no_tex(monkeypatch):
    monkeypatch.setattr(engines, "find_pdflatex", lambda: (None, "pdflatex not found (test)"))
    monkeypatch.setattr(engines, "pdflatex_command", lambda: "/nonexistent/pdflatex")
    monkeypatch.setattr(engines, "pdflatex_available", lambda: False)


def test_argv_uses_the_resolved_binary(monkeypatch, tmp_path):
    monkeypatch.setattr(engines, "pdflatex_command", lambda: "/opt/tex/bin/pdflatex")
    argv = pdf_render._pdflatex_argv(tmp_path / "x.tex", tmp_path, "x")
    assert argv[0] == "/opt/tex/bin/pdflatex"
    assert "-no-shell-escape" in argv


def test_compile_pdf_without_pdflatex_is_a_runtime_error(monkeypatch, tmp_path):
    _no_tex(monkeypatch)
    with pytest.raises(RuntimeError, match="pdflatex is not installed"):
        pdf_render.compile_pdf(MINIMAL_TEX, tmp_path)


def test_render_and_compile_without_pdflatex_is_a_runtime_error(monkeypatch, tmp_path):
    _no_tex(monkeypatch)
    with pytest.raises(RuntimeError, match="pdflatex is not installed"):
        pdf_render.render_and_compile(
            SAMPLE_RESUME, tmp_path / "r.tex", tmp_path / "r.pdf"
        )


def test_a_directory_as_pdflatex_is_the_same_runtime_error(monkeypatch, tmp_path):
    # A wrong MAESTRO_CS_PDFLATEX may name a directory: exec of one raises
    # PermissionError (EACCES), not FileNotFoundError.
    monkeypatch.setattr(engines, "find_pdflatex", lambda: (None, "MAESTRO_CS_PDFLATEX points at a directory (test)"))
    monkeypatch.setattr(engines, "pdflatex_command", lambda: str(tmp_path))
    monkeypatch.setattr(engines, "pdflatex_available", lambda: False)
    with pytest.raises(RuntimeError, match="pdflatex is not installed"):
        pdf_render.compile_pdf(MINIMAL_TEX, tmp_path / "out")


def test_a_found_binary_that_cannot_start_is_not_reported_as_missing(monkeypatch, tmp_path):
    # The probe found a binary but the spawn still failed (EACCES here; a fork
    # failure or ENOEXEC in the wild): "not installed" would send the user to
    # install TeX they already have.
    fake = tmp_path / "pdflatex"
    fake.write_text("not a program")
    fake.chmod(0o644)
    monkeypatch.setattr(engines, "find_pdflatex", lambda: (str(fake), None))
    monkeypatch.setattr(engines, "pdflatex_command", lambda: str(fake))
    with pytest.raises(RuntimeError, match="could not be started") as info:
        pdf_render.compile_pdf(MINIMAL_TEX, tmp_path / "out")
    assert "not installed" not in str(info.value)


# --- The fallback resolver ---------------------------------------------------


def _seed_rows(db_session, *, typst_ready: bool = True):
    """Every seed as a draft row (no compile), then mark typst-classic ready."""
    reg.reset_seed_validation_attempts()
    reg.ensure_seed_templates(db_session, validate=False)
    if typst_ready:
        db_session.get(Template, reg.TYPST_CLASSIC_ID).status = "ready"
        db_session.commit()


def _mark_ready(db_session, template_id: str) -> None:
    db_session.get(Template, template_id).status = "ready"
    db_session.commit()


def test_latex_template_without_tex_renders_with_typst_and_says_so(db_session, monkeypatch):
    _no_tex(monkeypatch)
    _seed_rows(db_session)
    tmpl, note = pdf_render.resolve_render_template("default", db_session)
    assert tmpl.id == reg.TYPST_CLASSIC_ID
    assert "TeX is not installed" in note
    assert "Typst Classic" in note and "Classic" in note

    doc = pdf_render.render_document(SAMPLE_RESUME, template_id="default", session=db_session)
    assert doc.engine == "typst"
    assert doc.resolved_template_id == reg.TYPST_CLASSIC_ID
    assert doc.render_note == note


def test_a_ready_typst_default_wins_over_typst_classic(db_session, monkeypatch):
    _no_tex(monkeypatch)
    _seed_rows(db_session)
    # Ready, so get_usable_template hands the resolver the LaTeX template itself
    # (a draft would already have fallen back to the default before the rule).
    _mark_ready(db_session, "xcharter_serif")
    mine = Template(id="mine", display_name="Mine", engine="typst", status="ready",
                    source=db_session.get(Template, reg.TYPST_CLASSIC_ID).source)
    db_session.add(mine)
    db_session.commit()
    reg.set_default(db_session, "mine")
    tmpl, note = pdf_render.resolve_render_template("xcharter_serif", db_session)
    assert tmpl.id == "mine"
    assert note == pdf_render.tex_fallback_note("Mine", "XCharter Serif")


def test_first_ready_typst_order_is_default_then_classic_then_by_id(db_session):
    _seed_rows(db_session, typst_ready=False)
    assert reg.first_ready_typst(db_session) is None
    # Only a non-classic Typst seed is ready: it wins by id (the last tier).
    _mark_ready(db_session, "xcharter_serif_typst")
    assert reg.first_ready_typst(db_session).id == "xcharter_serif_typst"
    # typst-classic outranks it once ready...
    _mark_ready(db_session, reg.TYPST_CLASSIC_ID)
    assert reg.first_ready_typst(db_session).id == reg.TYPST_CLASSIC_ID
    # ...and a ready Typst default outranks both. Archived is never a candidate.
    mine = Template(id="mine", display_name="Mine", engine="typst", status="ready", source="x")
    db_session.add(mine)
    db_session.commit()
    reg.set_default(db_session, "mine")
    assert reg.first_ready_typst(db_session).id == "mine"
    mine.archived_at = datetime.now(UTC)
    db_session.commit()
    assert reg.first_ready_typst(db_session).id == reg.TYPST_CLASSIC_ID


def test_no_ready_typst_template_is_a_400_class_error(db_session, monkeypatch):
    _no_tex(monkeypatch)
    _seed_rows(db_session, typst_ready=False)
    with pytest.raises(ValueError, match="needs TeX"):
        pdf_render.resolve_render_template("default", db_session)


def test_typst_templates_are_untouched_without_tex(db_session, monkeypatch):
    _no_tex(monkeypatch)
    _seed_rows(db_session)
    tmpl, note = pdf_render.resolve_render_template(reg.TYPST_CLASSIC_ID, db_session)
    assert tmpl.id == reg.TYPST_CLASSIC_ID
    assert note is None


def test_latex_templates_are_untouched_with_tex(db_session, monkeypatch):
    monkeypatch.setattr(engines, "pdflatex_available", lambda: True)
    _seed_rows(db_session)
    tmpl, note = pdf_render.resolve_render_template("default", db_session)
    assert tmpl.id == "default"
    assert note is None


def test_render_note_is_none_when_nothing_was_substituted(db_session, monkeypatch):
    monkeypatch.setattr(engines, "pdflatex_available", lambda: True)
    _seed_rows(db_session)
    doc = pdf_render.render_document(
        SAMPLE_RESUME, template_id=reg.TYPST_CLASSIC_ID, session=db_session
    )
    assert doc.engine == "typst"
    assert doc.render_note is None


# --- The note on the wire -----------------------------------------------------


def test_base_resume_render_reports_the_fallback(db_session, tmp_path, monkeypatch):
    _no_tex(monkeypatch)
    _seed_rows(db_session)
    monkeypatch.setattr(app_settings, "base_resumes_dir", tmp_path)
    _seed(db_session, slug="data_scientist", data_json=SAMPLE_RESUME)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).post("/api/base-resumes/data_scientist/render")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["resolved_engine"] == "typst"
    assert "TeX is not installed" in body["render_note"]
    assert Path(body["pdf_path"]).exists()


def test_application_render_reports_the_fallback(db_session, tmp_path, monkeypatch):
    _no_tex(monkeypatch)
    _seed_rows(db_session)
    monkeypatch.setattr(app_settings, "applications_dir", tmp_path)
    monkeypatch.setattr(
        applications_router.base_resume_data,
        "load_base_resume",
        lambda slug, session=None: SAMPLE_RESUME,
    )
    job = _job(db_session)
    application = Application(job_id=job.id, base_resume="data_scientist", status="draft")
    db_session.add(application)
    db_session.commit()
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).post(f"/api/applications/{application.id}/render")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    assert r.json()["resolved_engine"] == "typst"
    assert "TeX is not installed" in r.json()["render_note"]


def test_render_note_is_null_on_the_wire_when_nothing_was_substituted(
    db_session, tmp_path, monkeypatch
):
    _seed_rows(db_session)
    monkeypatch.setattr(app_settings, "base_resumes_dir", tmp_path)
    _seed(db_session, slug="data_scientist", data_json=SAMPLE_RESUME)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).post(
            f"/api/base-resumes/data_scientist/render?template_id={reg.TYPST_CLASSIC_ID}"
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    assert r.json()["render_note"] is None
