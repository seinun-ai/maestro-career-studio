import pytest

from app.services import template_registry as reg, template_validation as tv

pytest.importorskip("typst")
pytest.importorskip("pdfplumber")

# Consumes fmt.font_size so the default_formatting test below has a knob whose
# effect is measurable in the compiled PDF.
CORE_TYP = (
    "#let r = json(bytes(sys.inputs.resume))\n"
    "#let fmt = json(bytes(sys.inputs.fmt))\n"
    "#set text(size: fmt.font_size * 1pt)\n"
    "= #r.contact.name\n"
    "#r.contact.email\n"
)


def test_compile_against_sample_typst_success_keeps_pdf(tmp_path):
    keep = tmp_path / "p.pdf"
    assert tv.compile_against_sample(CORE_TYP, keep_pdf_at=keep, engine="typst") is None
    assert keep.exists()


def test_compile_against_sample_typst_error_returned_not_raised():
    err = tv.compile_against_sample("#undefinedfunc()", engine="typst")
    assert err is not None and "typst" in err


def test_compile_against_sample_typst_honors_default_formatting(tmp_path):
    # font_size knob visibly changes the compiled sample (char size grows).
    import pdfplumber

    a, b = tmp_path / "a.pdf", tmp_path / "b.pdf"
    assert tv.compile_against_sample(CORE_TYP, keep_pdf_at=a, engine="typst") is None
    assert (
        tv.compile_against_sample(
            CORE_TYP, keep_pdf_at=b, default_formatting={"font_size": 12}, engine="typst"
        )
        is None
    )
    with pdfplumber.open(a) as d:
        size_a = d.pages[0].chars[0]["size"]
    with pdfplumber.open(b) as d:
        size_b = d.pages[0].chars[0]["size"]
    assert size_b > size_a


def test_validate_template_dispatches_by_engine(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(tv.settings, "base_resumes_dir", tmp_path)
    reg.create_draft(
        db_session, id="tval", display_name="TV", source=CORE_TYP, origin="mcp", engine="typst"
    )
    result = tv.validate_template("tval", db_session)
    assert result["ok"] is True
    assert result["parse_report"]["extra_sections_supported"] is False
    row = reg.get(db_session, "tval")
    assert row.status == "ready"
    # name+email only -> experience/education probes missing -> honestly NOT certified
    assert row.parse_certified is False
    assert row.parse_report_json["extra_sections_supported"] is False


def test_validate_bad_typst_source_stays_draft(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(tv.settings, "base_resumes_dir", tmp_path)
    reg.create_draft(
        db_session, id="tbad", display_name="TB", source="#undefinedfunc()",
        origin="mcp", engine="typst",
    )
    result = tv.validate_template("tbad", db_session)
    assert result["ok"] is False and result["error"]
    assert result["parse_report"] is None
    row = reg.get(db_session, "tbad")
    assert row.status == "draft" and row.last_error
