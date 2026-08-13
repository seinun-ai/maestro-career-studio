import shutil

import pytest

from app.services import pdf_render, template_registry as reg, template_validation as tv

pytestmark = pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex not installed")


def test_validate_good_template_marks_ready(db_session, tmp_path, monkeypatch):
    # settings.base_resumes_dir defaults to the read-only /app path; redirect the
    # preview directory to a writable tmp path (mirrors test_base_resume_render).
    monkeypatch.setattr(tv.settings, "base_resumes_dir", tmp_path)
    src = (pdf_render.TEMPLATE_DIR / pdf_render.RESUME_TEMPLATE).read_text(encoding="utf-8")
    reg.create_draft(db_session, id="good", display_name="Good", source=src, origin="mcp")
    result = tv.validate_template("good", db_session)
    assert result["ok"] is True
    row = reg.get(db_session, "good")
    assert row.status == "ready"
    assert row.validated_at is not None
    assert row.last_error is None
    # preview file exists
    assert tv._preview_path("good").exists()


def test_check_parse_fidelity_detects_present_and_missing(tmp_path):
    pytest.importorskip("pdfplumber")
    doc = (
        r"\documentclass{article}\begin{document}"
        r"Alpha One and Beta Two and Gamma Three here.\end{document}"
    )
    pdf = pdf_render.compile_pdf(doc, tmp_path, stem="fid")
    ok, missing = tv.check_parse_fidelity(pdf, probes=["Alpha One"])
    assert ok is True and missing == []
    bad_ok, bad_missing = tv.check_parse_fidelity(
        pdf, probes=["Totally Absent Phrase"]
    )
    assert bad_ok is False and "Totally Absent Phrase" in bad_missing


def test_check_parse_fidelity_partial_survival_not_certified(tmp_path):
    # New contract: certification requires ALL probes. A PDF where only some
    # probes survive is NOT certified — there is no majority tolerance anymore.
    pytest.importorskip("pdfplumber")
    doc = (
        r"\documentclass{article}\begin{document}"
        r"Alpha One and Beta Two and Gamma Three here.\end{document}"
    )
    pdf = pdf_render.compile_pdf(doc, tmp_path, stem="fid2")
    present3_absent3 = ["Alpha One", "Beta Two", "Gamma Three", "No A", "No B", "No C"]
    ok, _ = tv.check_parse_fidelity(pdf, probes=present3_absent3)
    assert ok is False  # 3/6 survive -> not all -> not certified
    present1_absent5 = ["Alpha One", "No A", "No B", "No C", "No D", "No E"]
    ok2, _ = tv.check_parse_fidelity(pdf, probes=present1_absent5)
    assert ok2 is False  # 1/6 survive -> not certified


def test_check_parse_fidelity_requires_all_probes(tmp_path):
    pytest.importorskip("pdfplumber")
    doc = (
        r"\documentclass{article}\begin{document}"
        r"Alpha One and Beta Two here.\end{document}"
    )
    pdf = pdf_render.compile_pdf(doc, tmp_path, stem="allprobes")
    # 2 of 3 probes present — majority would pass; all-probes must fail
    ok, missing = tv.check_parse_fidelity(pdf, probes=["Alpha One", "Beta Two", "Gamma Three"])
    assert ok is False and missing == ["Gamma Three"]


def test_check_parse_fidelity_degrades_closed(tmp_path, monkeypatch):
    # unreadable PDF → None (not assessed), NEVER True
    bogus = tmp_path / "not_a_pdf.pdf"
    bogus.write_text("hello")
    ok, missing = tv.check_parse_fidelity(bogus)
    assert ok is None

    # missing extractor → None
    import builtins
    real_import = builtins.__import__
    def no_pdfplumber(name, *a, **k):
        if name == "pdfplumber":
            raise ImportError("gone")
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", no_pdfplumber)
    ok, _ = tv.check_parse_fidelity(bogus)
    assert ok is None


def test_validate_template_stores_parse_report(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(tv.settings, "base_resumes_dir", tmp_path)
    src = (pdf_render.TEMPLATE_DIR / pdf_render.RESUME_TEMPLATE).read_text(encoding="utf-8")
    reg.create_draft(db_session, id="rep", display_name="Rep", source=src, origin="mcp")
    result = tv.validate_template("rep", db_session)
    assert result["ok"] is True
    row = reg.get(db_session, "rep")
    assert row.parse_report_json is not None
    assert row.parse_report_json["extractor"] == "pdfplumber"
    assert "email_ok" in row.parse_report_json
    assert "headers_missing" in row.parse_report_json


def test_validate_certifies_parse_fidelity(db_session, tmp_path, monkeypatch):
    pytest.importorskip("pdfplumber")
    monkeypatch.setattr(tv.settings, "base_resumes_dir", tmp_path)
    src = (pdf_render.TEMPLATE_DIR / pdf_render.RESUME_TEMPLATE).read_text(encoding="utf-8")
    reg.create_draft(db_session, id="cert", display_name="Cert", source=src, origin="mcp")
    result = tv.validate_template("cert", db_session)
    assert result["ok"] is True
    assert result["parse_certified"] is True
    row = reg.get(db_session, "cert")
    assert row.parse_certified is True


def test_default_formatting_applied_in_preview(tmp_path):
    # A template whose source wires fmt.font_size into visible body text: the
    # compile must render the template's default_formatting overlay (12), not the
    # bare schema default (11), so the preview reflects the theme defaults.
    pytest.importorskip("pdfplumber")
    src = (
        r"\documentclass{article}\begin{document}"
        r"FONTSIZE((( fmt.font_size )))MARK\end{document}"
    )
    keep = tmp_path / "prev.pdf"
    err = tv.compile_against_sample(
        src, keep_pdf_at=keep, default_formatting={"font_size": 12}
    )
    assert err is None
    assert keep.exists()

    import pdfplumber

    with pdfplumber.open(keep) as doc:
        text = " ".join((page.extract_text() or "") for page in doc.pages)
    normalized = " ".join(text.split())
    assert "FONTSIZE12MARK" in normalized
    assert "FONTSIZE11MARK" not in normalized


def test_validate_uses_default_formatting_for_preview(db_session, tmp_path, monkeypatch):
    # validate_template must feed the row's default_formatting into the compile so
    # the stored preview reflects the theme defaults.
    pytest.importorskip("pdfplumber")
    monkeypatch.setattr(tv.settings, "base_resumes_dir", tmp_path)
    src = (
        r"\documentclass{article}\begin{document}"
        r"FONTSIZE((( fmt.font_size )))MARK\end{document}"
    )
    reg.create_draft(db_session, id="fmt", display_name="Fmt", source=src, origin="mcp")
    row = reg.get(db_session, "fmt")
    row.default_formatting = {"font_size": 12}
    db_session.commit()

    result = tv.validate_template("fmt", db_session)
    assert result["ok"] is True

    import pdfplumber

    with pdfplumber.open(tv._preview_path("fmt")) as doc:
        text = " ".join((page.extract_text() or "") for page in doc.pages)
    normalized = " ".join(text.split())
    assert "FONTSIZE12MARK" in normalized


def test_validate_bad_template_stays_draft_with_error(db_session):
    reg.create_draft(
        db_session, id="bad", display_name="Bad",
        source="\\documentclass{article}\\begin{document}\\undefinedcommandxyz\\end{document}",
        origin="mcp",
    )
    result = tv.validate_template("bad", db_session)
    assert result["ok"] is False
    assert result["error"]
    row = reg.get(db_session, "bad")
    assert row.status == "draft"
    assert row.last_error


def test_validate_unknown_raises(db_session):
    with pytest.raises(LookupError):
        tv.validate_template("nope", db_session)


def test_sample_resume_is_valid_resumedata():
    from app.schemas.resume import ResumeData

    # Must not raise
    ResumeData.model_validate(tv.SAMPLE_RESUME)


def test_validate_returns_parse_report_detail(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(tv.settings, "base_resumes_dir", tmp_path)
    reg.ensure_seed_templates(db_session, validate=False)
    out = tv.validate_template("default", db_session)
    assert out["ok"] is True
    assert out["parse_report"]["extra_sections_supported"] is True
    assert out["parse_report"]["missing"] == []


def test_template_detail_exposes_parse_report(db_session, tmp_path, monkeypatch):
    from app.db import get_db
    from app.main import app
    from fastapi.testclient import TestClient

    monkeypatch.setattr(tv.settings, "base_resumes_dir", tmp_path)
    reg.ensure_seed_templates(db_session, validate=False)

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    try:
        client = TestClient(app)
        assert client.post("/api/templates/default/validate").status_code == 200
        detail = client.get("/api/templates/default").json()
    finally:
        app.dependency_overrides.clear()
    assert detail["parse_report"]["extra_sections_supported"] is True
