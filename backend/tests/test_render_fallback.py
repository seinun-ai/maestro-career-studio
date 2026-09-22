"""Design 2026-09-19 §2.2: a render never changes engine silently, and a
missing pdflatex is an actionable error, never a 500 from FileNotFoundError."""
import json
import shutil
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings as app_settings
from app.db import get_db
from app.main import app
from app.models.application import Application
from app.models.base_resume import BaseResume
from app.models.template import Template
from app.routers import applications as applications_router
from app.services import base_resume_render, engines, pdf_render, resume_lint
from app.services.chat_tools import ToolContext, tool_edit_resume
from app.services import template_registry as reg
from app.services import template_validation as tv
from app.services.resume_versions import record_version
from app.services.template_validation import SAMPLE_RESUME
from tests.test_applications_router import _job
from tests.test_base_resumes_router import _override_db, _seed
from tests.test_kb_import import _json_upload
from tests.test_kb_port import _make_entity

MINIMAL_TEX = "\\documentclass{article}\\begin{document}x\\end{document}"


def _no_tex(monkeypatch):
    """THE no-TeX switch: every seam the render path reads. The resolver probes
    ONCE via `probe_pdflatex`; `_run_pdflatex` reads `find_pdflatex` for its
    error reason and `pdflatex_command` for argv[0]."""
    monkeypatch.setattr(engines, "find_pdflatex", lambda: (None, "pdflatex not found (test)"))
    monkeypatch.setattr(engines, "pdflatex_command", lambda: "/nonexistent/pdflatex")
    monkeypatch.setattr(
        engines,
        "probe_pdflatex",
        lambda: engines.EngineStatus("pdflatex", False, reason="pdflatex not found (test)"),
    )
    monkeypatch.setattr(engines, "pdflatex_available", lambda: False)


def _with_tex(monkeypatch):
    """The opposite switch, so a with-TeX expectation does not depend on the
    host running the suite."""
    monkeypatch.setattr(
        engines,
        "probe_pdflatex",
        lambda: engines.EngineStatus(
            "pdflatex", True, version="pdfTeX (test)", path="/opt/tex/bin/pdflatex"
        ),
    )
    monkeypatch.setattr(engines, "pdflatex_available", lambda: True)


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
    _with_tex(monkeypatch)
    _seed_rows(db_session)
    tmpl, note = pdf_render.resolve_render_template("default", db_session)
    assert tmpl.id == "default"
    assert note is None


def test_render_note_is_none_when_nothing_was_substituted(db_session, monkeypatch):
    _with_tex(monkeypatch)
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
    # No explicit template_id was passed, so the substitution of the resume's
    # persisted choice leaves the flag False — render_note is the only signal.
    assert body["template_fallback"] is False
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
    body = r.json()
    assert body["resolved_engine"] == "typst"
    assert "TeX is not installed" in body["render_note"]
    assert Path(body["pdf_path"]).exists()


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


def test_edits_response_reports_the_fallback(db_session, tmp_path, monkeypatch):
    """PATCH /edits re-renders, so it is a render response: without the note a
    web user on a TeX-less host gets a silently substituted PDF (the web app
    never calls POST /render)."""
    _no_tex(monkeypatch)
    _seed_rows(db_session)
    monkeypatch.setattr(app_settings, "base_resumes_dir", tmp_path)
    _seed(db_session, slug="data_scientist", data_json=SAMPLE_RESUME)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).patch(
            "/api/base-resumes/data_scientist/edits",
            json={"ops": [{"kind": "replace_summary", "value": "New summary"}]},
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["render_error"] is None
    assert "TeX is not installed" in body["render_note"]


def test_a_failed_re_render_does_not_leave_a_stale_note(db_session, tmp_path, monkeypatch):
    """render_note is an unmapped attribute on a session-identity row, so a
    rollback/refresh cannot clear it — render_base_resume must null it itself."""
    _no_tex(monkeypatch)
    _seed_rows(db_session)
    monkeypatch.setattr(app_settings, "base_resumes_dir", tmp_path)
    row = _seed(db_session, slug="data_scientist", data_json=SAMPLE_RESUME)

    base_resume_render.render_base_resume("data_scientist", db_session)
    assert "TeX is not installed" in row.render_note

    def boom(*a, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(pdf_render, "_compile_typst_file", boom)
    with pytest.raises(RuntimeError, match="boom"):
        base_resume_render.render_base_resume("data_scientist", db_session)
    assert row.render_note is None


def test_extras_error_after_a_substitution_says_the_substitution_happened(
    db_session, monkeypatch
):
    """The user picked a LaTeX template that CAN render extras; the TeX-less
    substitute cannot. The incompatibility message must say the engine was
    swapped, or the user is told their own template lacks a feature it has."""
    _no_tex(monkeypatch)
    _seed_rows(db_session, typst_ready=False)
    # The only ready Typst template never names extra_sections.
    plain = Template(
        id="plain", display_name="Plain", engine="typst", status="ready",
        source="#let r = json(bytes(sys.inputs.resume))\n#r.contact.name",
    )
    db_session.add(plain)
    db_session.commit()
    assert reg.first_ready_typst(db_session).id == "plain"
    # SAMPLE_RESUME carries enabled, non-empty extra sections (the sentinels).
    assert pdf_render._renderable_extra_sections(SAMPLE_RESUME)

    with pytest.raises(pdf_render.TemplateMissingExtraSectionsError) as info:
        pdf_render.render_document(SAMPLE_RESUME, template_id="default", session=db_session)
    message = str(info.value)
    assert "TeX is not installed" in message
    assert "Plain" in message and "Classic" in message
    assert "cannot render custom sections" in message


# --- Validation and health gates without TeX ----------------------------------


def test_validating_a_latex_template_without_tex_reports_requires_tex(db_session, monkeypatch):
    # Validation never substitutes: template A must never validate template B.
    _no_tex(monkeypatch)
    _seed_rows(db_session)
    result = tv.validate_template("default", db_session)
    assert result["ok"] is False
    assert result["error"] == "requires TeX (pdflatex not found)"
    row = db_session.get(Template, "default")
    assert row.status == "draft" and row.last_error == result["error"]


def test_health_gates_follow_the_template_that_renders(
    db_session, tmp_path, monkeypatch, caplog
):
    # Without TeX the resume renders through Typst Classic, so the structure
    # gates must be Typst Classic's, and no lazy LaTeX certification may run.
    _no_tex(monkeypatch)
    _seed_rows(db_session)
    # Typst Classic's lazy certification compiles for real and writes a preview.
    monkeypatch.setattr(app_settings, "base_resumes_dir", tmp_path)
    seen: list[str] = []
    real_validate = tv.validate_template

    def spy(template_id, session):
        seen.append(template_id)
        return real_validate(template_id, session)

    monkeypatch.setattr(tv, "validate_template", spy)
    gates = resume_lint.structure_gates(db_session, "default", SAMPLE_RESUME)
    assert seen == [reg.TYPST_CLASSIC_ID]
    assert "lazy template certification failed" not in caplog.text
    assert {g["id"] for g in gates} >= {"S1", "S2"}


def test_health_gates_fall_back_to_the_requested_template_when_no_typst_is_ready(
    db_session, monkeypatch
):
    _no_tex(monkeypatch)
    _seed_rows(db_session, typst_ready=False)
    gates = resume_lint.structure_gates(db_session, "default", SAMPLE_RESUME)
    # The health run never fails on the no-Typst ValueError; S1 is not_assessed
    # with the requires-TeX reason recorded on the template.
    s1 = next(g for g in gates if g["id"] == "S1")
    assert s1["status"] == "not_assessed"
    assert db_session.get(Template, "default").last_error == "requires TeX (pdflatex not found)"


def test_create_side_base_resume_responses_carry_the_note(db_session, tmp_path, monkeypatch):
    _no_tex(monkeypatch)
    _seed_rows(db_session)
    monkeypatch.setattr(app_settings, "base_resumes_dir", tmp_path)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        created = client.post(
            "/api/base-resumes",
            json={"slug": "made_here", "role_category": "data_scientist", "data": SAMPLE_RESUME},
        )
        assert created.status_code == 200, created.text
        assert "TeX is not installed" in created.json()["render_note"]
        dup = client.post("/api/base-resumes/made_here/duplicate", json={"new_slug": "made_copy"})
        assert dup.status_code == 200, dup.text
        assert "TeX is not installed" in dup.json()["render_note"]
        # /import delegates to the create handler; a JSON upload needs no model.
        imported = client.post(
            "/api/base-resumes/import",
            data={"slug": "made_import"},
            files={"file": ("resume.json", json.dumps(SAMPLE_RESUME), "application/json")},
        )
        assert imported.status_code == 200, imported.text
        assert "TeX is not installed" in imported.json()["render_note"]
    finally:
        app.dependency_overrides.clear()


def test_port_project_reports_the_fallback(db_session, tmp_path, monkeypatch):
    """POST /port-project re-renders the TARGET and otherwise answers with two
    ids, so without the note the substitution would be invisible."""
    _no_tex(monkeypatch)
    _seed_rows(db_session)
    monkeypatch.setattr(app_settings, "base_resumes_dir", tmp_path)
    _seed(db_session, slug="data_scientist", data_json=SAMPLE_RESUME)
    _seed(db_session, slug="hybrid", data_json=SAMPLE_RESUME)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).post(
            "/api/base-resumes/data_scientist/port-project",
            json={"target_slug": "hybrid", "project_index": 0},
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["target_slug"] == "hybrid"
    assert "TeX is not installed" in body["render_note"]


def test_kb_port_reports_the_fallback(db_session, tmp_path, monkeypatch):
    _no_tex(monkeypatch)
    _seed_rows(db_session)
    monkeypatch.setattr(app_settings, "base_resumes_dir", tmp_path)
    _seed(db_session, slug="data_scientist", data_json=SAMPLE_RESUME)
    entity, _points = _make_entity(
        db_session,
        kind="project",
        title="RAG Chatbot",
        detail={"tech": "Python"},
        points=[("Built a retrieval pipeline.", "approved")],
    )
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).post(
            "/api/kb/port",
            json={"target_slug": "data_scientist", "items": [{"entity_id": str(entity.id)}]},
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    resume = r.json()["resume"]
    # The port's tolerant render succeeded (under Typst) — not a recorded failure.
    assert resume["render_error"] is None
    assert "TeX is not installed" in resume["render_note"]


def test_version_restore_reports_the_fallback(db_session, tmp_path, monkeypatch):
    _no_tex(monkeypatch)
    _seed_rows(db_session)
    monkeypatch.setattr(app_settings, "base_resumes_dir", tmp_path)
    row = _seed(db_session, slug="data_scientist", data_json=SAMPLE_RESUME)
    record_version(db_session, "base", "data_scientist", SAMPLE_RESUME, source="create")
    changed = deepcopy(SAMPLE_RESUME)
    changed["summary"] = "A different summary"
    row.data_json = changed
    record_version(db_session, "base", "data_scientist", changed, source="form_edit")
    db_session.commit()
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).post("/api/resume-versions/base/data_scientist/1/restore")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "restore"
    assert "TeX is not installed" in body["render_note"]


def test_kb_port_adapt_apply_reports_the_fallback(db_session, tmp_path, monkeypatch):
    """The adapted port persists through the same _persist_port as the verbatim
    one, so it is a render response too. Apply takes bullets the user already
    approved and makes no LLM call."""
    _no_tex(monkeypatch)
    _seed_rows(db_session)
    monkeypatch.setattr(app_settings, "base_resumes_dir", tmp_path)
    _seed(db_session, slug="data_scientist", data_json=SAMPLE_RESUME)
    entity, points = _make_entity(
        db_session,
        kind="project",
        title="RAG Chatbot",
        detail={"tech": "Python"},
        points=[("Built a retrieval pipeline.", "approved")],
    )
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).post(
            "/api/kb/port/adapt/apply",
            json={
                "target_slug": "data_scientist",
                "entity_id": str(entity.id),
                "bullets": [
                    {
                        "text": "Built a retrieval pipeline serving 10k queries a day.",
                        "source_point_ids": [str(points[0].id)],
                    }
                ],
            },
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    resume = r.json()["resume"]
    assert resume["render_error"] is None
    assert "TeX is not installed" in resume["render_note"]


def test_kb_import_reports_the_fallback(db_session, tmp_path, monkeypatch):
    """The onboarding import mints AND renders each base — on a TeX-less
    desktop it is the first render the user ever sees. A JSON upload with
    consolidate=false makes no LLM call (test_kb_import proves both halves),
    so nothing needs stubbing but the data dir."""
    _no_tex(monkeypatch)
    _seed_rows(db_session)
    monkeypatch.setattr(app_settings, "base_resumes_dir", tmp_path)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app).post(
            "/api/kb/import?consolidate=false",
            files=[_json_upload("plain.json", SAMPLE_RESUME)],
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    base = r.json()["bases"][0]
    assert base["render_error"] is None
    assert "TeX is not installed" in base["render_note"]


def test_tex_present_leaves_the_note_null_on_every_re_rendering_route(
    db_session, tmp_path, monkeypatch
):
    """The null half of the contract for the four routes Task 10c wired.

    The positive tests above would all still pass if a route hard-coded a
    note, and `POST /render` is the only route the null case was pinned on.
    These renders are the real LaTeX path (that is the point: TeX present, no
    substitution), so a TeX-less host skips rather than fails.
    """
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is not installed")
    _with_tex(monkeypatch)
    _seed_rows(db_session)
    monkeypatch.setattr(app_settings, "base_resumes_dir", tmp_path)
    row = _seed(db_session, slug="data_scientist", data_json=SAMPLE_RESUME)
    entity, points = _make_entity(
        db_session,
        kind="project",
        title="RAG Chatbot",
        detail={"tech": "Python"},
        points=[("Built a retrieval pipeline.", "approved")],
    )
    record_version(db_session, "base", "data_scientist", SAMPLE_RESUME, source="create")
    changed = deepcopy(SAMPLE_RESUME)
    changed["summary"] = "A different summary"
    row.data_json = changed
    record_version(db_session, "base", "data_scientist", changed, source="form_edit")
    db_session.commit()

    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        port = client.post(
            "/api/kb/port",
            json={"target_slug": "data_scientist", "items": [{"entity_id": str(entity.id)}]},
        )
        assert port.status_code == 200, port.text
        # render_error None too: a FAILED render also leaves the note null, so
        # without this the null pin would pass vacuously on a broken TeX.
        assert port.json()["resume"]["render_error"] is None
        assert port.json()["resume"]["render_note"] is None

        adapted = client.post(
            "/api/kb/port/adapt/apply",
            json={
                "target_slug": "data_scientist",
                "entity_id": str(entity.id),
                "bullets": [
                    {
                        "text": "Built a retrieval pipeline serving 10k queries a day.",
                        "source_point_ids": [str(points[0].id)],
                    }
                ],
            },
        )
        assert adapted.status_code == 200, adapted.text
        assert adapted.json()["resume"]["render_error"] is None
        assert adapted.json()["resume"]["render_note"] is None

        restored = client.post("/api/resume-versions/base/data_scientist/1/restore")
        assert restored.status_code == 200, restored.text
        assert restored.json()["render_error"] is None
        assert restored.json()["render_note"] is None

        imported = client.post(
            "/api/kb/import?consolidate=false",
            files=[_json_upload("plain.json", SAMPLE_RESUME)],
        )
        assert imported.status_code == 200, imported.text
        assert imported.json()["bases"][0]["render_error"] is None
        assert imported.json()["bases"][0]["render_note"] is None
    finally:
        app.dependency_overrides.clear()


def test_a_tolerated_render_failure_reports_no_note(db_session, tmp_path, monkeypatch):
    """Where a failed render still answers with a body, that body must carry
    `render_error` AND a null note: the two are alternatives, never both, and
    `render_note` is an unmapped attribute that no rollback clears."""
    _no_tex(monkeypatch)
    _seed_rows(db_session)
    monkeypatch.setattr(app_settings, "base_resumes_dir", tmp_path)
    _seed(db_session, slug="data_scientist", data_json=SAMPLE_RESUME)
    entity, _points = _make_entity(
        db_session,
        kind="project",
        title="RAG Chatbot",
        detail={"tech": "Python"},
        points=[("Built a retrieval pipeline.", "approved")],
    )

    def boom(*a, **kw):
        raise RuntimeError("! typst exploded")

    monkeypatch.setattr(pdf_render, "_compile_typst_file", boom)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        client = TestClient(app)
        port = client.post(
            "/api/kb/port",
            json={"target_slug": "data_scientist", "items": [{"entity_id": str(entity.id)}]},
        )
        assert port.status_code == 200, port.text
        resume = port.json()["resume"]
        assert "typst exploded" in resume["render_error"]
        assert resume["render_note"] is None

        imported = client.post(
            "/api/kb/import?consolidate=false",
            files=[_json_upload("plain.json", SAMPLE_RESUME)],
        )
        assert imported.status_code == 200, imported.text
        base = imported.json()["bases"][0]
        assert "typst exploded" in base["render_error"]
        assert base["render_note"] is None
    finally:
        app.dependency_overrides.clear()


# --- No ready Typst template: a 400-class failure, never a 500 ---------------


def test_port_project_without_a_typst_fallback_does_not_500(
    db_session, tmp_path, monkeypatch
):
    """Design §2.2: no ready Typst template on a TeX-less host is a 400-class
    failure, never a 500.

    The port is COMMITTED before the render, so this route degrades rather
    than raising: 200, the port landed, and a persisted `render_error` (the
    stale-PDF banner) instead of a 500 over a silently stale PDF.
    """
    _no_tex(monkeypatch)
    _seed_rows(db_session, typst_ready=False)
    monkeypatch.setattr(app_settings, "base_resumes_dir", tmp_path)
    _seed(db_session, slug="data_scientist", data_json=SAMPLE_RESUME)
    _seed(db_session, slug="hybrid", data_json=SAMPLE_RESUME)
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app, raise_server_exceptions=False).post(
            "/api/base-resumes/data_scientist/port-project",
            json={"target_slug": "hybrid", "project_index": 0},
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code != 500, r.text
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["render_note"] is None
    assert "needs TeX" in body["render_error"]
    target = db_session.get(BaseResume, "hybrid")
    db_session.refresh(target)
    # The port landed, and the row itself says the PDF is stale.
    assert len(target.data_json["projects"]) == len(SAMPLE_RESUME["projects"]) + 1
    assert "needs TeX" in target.render_error


def test_version_restore_without_a_typst_fallback_does_not_500(
    db_session, tmp_path, monkeypatch
):
    """The same rule at the restore: the snapshot IS the live resume by the
    time the render runs, so a 4xx would report failure for a write that
    landed (and a retry would append yet another version)."""
    _no_tex(monkeypatch)
    _seed_rows(db_session, typst_ready=False)
    monkeypatch.setattr(app_settings, "base_resumes_dir", tmp_path)
    row = _seed(db_session, slug="data_scientist", data_json=SAMPLE_RESUME)
    record_version(db_session, "base", "data_scientist", SAMPLE_RESUME, source="create")
    changed = deepcopy(SAMPLE_RESUME)
    changed["summary"] = "A different summary"
    row.data_json = changed
    record_version(db_session, "base", "data_scientist", changed, source="form_edit")
    db_session.commit()
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app, raise_server_exceptions=False).post(
            "/api/resume-versions/base/data_scientist/1/restore"
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code != 500, r.text
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "restore"
    assert body["render_note"] is None
    assert "needs TeX" in body["render_error"]
    db_session.refresh(row)
    assert row.data_json["summary"] == SAMPLE_RESUME["summary"]
    assert "needs TeX" in row.render_error


def test_chat_edit_resume_card_reports_the_fallback(db_session, tmp_path, monkeypatch):
    """The chat edit tool re-renders through resume_ops, so its change card is
    a render response. It was the last silent base-resume re-render: the
    card's own Revert explains itself, the forward edit did not."""
    _no_tex(monkeypatch)
    _seed_rows(db_session)
    monkeypatch.setattr(app_settings, "base_resumes_dir", tmp_path)
    _seed(db_session, slug="data_scientist", data_json=SAMPLE_RESUME)

    result = tool_edit_resume(
        ToolContext(db=db_session, message_id="msg-1"),
        "base",
        "data_scientist",
        [{"kind": "replace_summary", "value": "Sharper summary."}],
    )

    card = result["change_card"]
    assert card["version_number"] == 1
    assert "TeX is not installed" in card["render_note"]


def test_kb_port_without_a_typst_fallback_degrades_like_the_others(
    db_session, tmp_path, monkeypatch
):
    """The ONE rule for all four post-commit re-renders: the write already
    landed, so the render failure degrades.

    `_persist_port` used to re-raise the no-ready-Typst ValueError as the
    router's 400 — the port had been committed, the user was told it failed,
    and a retry ported the same entity again."""
    _no_tex(monkeypatch)
    _seed_rows(db_session, typst_ready=False)
    monkeypatch.setattr(app_settings, "base_resumes_dir", tmp_path)
    _seed(db_session, slug="data_scientist", data_json=SAMPLE_RESUME)
    entity, _points = _make_entity(
        db_session,
        kind="project",
        title="RAG Chatbot",
        detail={"tech": "Python"},
        points=[("Built a retrieval pipeline.", "approved")],
    )
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app, raise_server_exceptions=False).post(
            "/api/kb/port",
            json={"target_slug": "data_scientist", "items": [{"entity_id": str(entity.id)}]},
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    resume = r.json()["resume"]
    assert resume["render_note"] is None
    assert "needs TeX" in resume["render_error"]
    row = db_session.get(BaseResume, "data_scientist")
    db_session.refresh(row)
    # The port landed: the entity is on the resume and the row says so.
    assert any(p.get("name") == "RAG Chatbot" for p in row.data_json["projects"])
    assert "needs TeX" in row.render_error


def test_kb_port_adapt_apply_without_a_typst_fallback_degrades_too(
    db_session, tmp_path, monkeypatch
):
    """The adapted port persists through the same `_persist_port`, so it takes
    the same answer — a pre-commit ValueError (a bad bullet, a non-approved
    source point) is still the router's 400; only the render degrades."""
    _no_tex(monkeypatch)
    _seed_rows(db_session, typst_ready=False)
    monkeypatch.setattr(app_settings, "base_resumes_dir", tmp_path)
    _seed(db_session, slug="data_scientist", data_json=SAMPLE_RESUME)
    entity, points = _make_entity(
        db_session,
        kind="project",
        title="RAG Chatbot",
        detail={"tech": "Python"},
        points=[("Built a retrieval pipeline.", "approved")],
    )
    app.dependency_overrides[get_db] = _override_db(db_session)
    try:
        r = TestClient(app, raise_server_exceptions=False).post(
            "/api/kb/port/adapt/apply",
            json={
                "target_slug": "data_scientist",
                "entity_id": str(entity.id),
                "bullets": [
                    {
                        "text": "Built a retrieval pipeline serving 10k queries a day.",
                        "source_point_ids": [str(points[0].id)],
                    }
                ],
            },
        )
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    resume = r.json()["resume"]
    assert resume["render_note"] is None
    assert "needs TeX" in resume["render_error"]
