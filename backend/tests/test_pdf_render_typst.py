import json
import shutil

import pytest

from app.schemas.formatting import merge_formatting
from app.services import pdf_render
from app.services.template_validation import SAMPLE_RESUME

typst = pytest.importorskip("typst")

# Minimal engine-contract template: binds both sys.inputs, renders core contact.
MINIMAL_TYP = (
    "#let r = json(bytes(sys.inputs.resume))\n"
    "#let fmt = json(bytes(sys.inputs.fmt))\n"
    "= #r.contact.name\n"
    "#r.contact.email\n"
    "#for e in r.experience [#e.role at #e.company. ]\n"
)
EXTRAS_TYP = MINIMAL_TYP + "#for s in r.extra_sections [#s.title ]\n"


def test_compile_typst_pdf_writes_typ_beside_pdf(tmp_path):
    sys_inputs = pdf_render.build_typst_sys_inputs(MINIMAL_TYP, SAMPLE_RESUME)
    pdf = pdf_render.compile_typst_pdf(MINIMAL_TYP, tmp_path, stem="doc", sys_inputs=sys_inputs)
    assert pdf == tmp_path / "doc.pdf" and pdf.exists()
    assert (tmp_path / "doc.typ").read_text(encoding="utf-8") == MINIMAL_TYP


def test_compile_typst_pdf_error_contract(tmp_path):
    sys_inputs = pdf_render.build_typst_sys_inputs(MINIMAL_TYP, SAMPLE_RESUME)
    with pytest.raises(RuntimeError, match="typst failed"):
        pdf_render.compile_typst_pdf("#undefinedfunc()", tmp_path, stem="bad", sys_inputs=sys_inputs)


def test_build_typst_sys_inputs_shapes():
    out = pdf_render.build_typst_sys_inputs(MINIMAL_TYP, SAMPLE_RESUME, {"font_size": 12})
    assert set(out) == {"resume", "fmt"}
    resume = json.loads(out["resume"])
    fmt = json.loads(out["fmt"])
    assert resume["contact"]["name"] == "Jordan Sample"
    assert fmt["font_size"] == 12
    # full 13-knob merge, defaults filled
    assert set(fmt) == set(merge_formatting(None).model_dump())


def test_build_typst_sys_inputs_preformats_dates():
    data = json.loads(json.dumps(SAMPLE_RESUME))
    data["experience"][0]["start_date"] = "Jan 2021"
    out = pdf_render.build_typst_sys_inputs(MINIMAL_TYP, data, {"date_format": "long_month"})
    resume = json.loads(out["resume"])
    assert resume["experience"][0]["start_date"] == "January 2021"
    # unparseable values pass through verbatim; None stays None (not "")
    assert resume["experience"][1]["end_date"] == "2021"
    assert resume["projects"][0]["date"] == "2024"


def test_typst_extras_scan_comment_and_string_aware():
    """FIX-8: the extras capability scan is comment/string aware.

    - extra_sections named ONLY in a comment is not credited (else custom
      sections silently drop);
    - a `//` inside a string literal must not eat a real reference on the same
      line (else a working template hard-rejects);
    - nested block comments are fully stripped (no leak of a buried token).
    """
    # comment-only -> not credited
    assert not pdf_render.typst_source_references_extras("// extra_sections\n= hi")
    assert not pdf_render.typst_source_references_extras("/* extra_sections */\n= hi")
    # // inside a string is NOT a comment: the live reference after it survives
    assert pdf_render.typst_source_references_extras(
        '#let u = "http://example.com"; #r.extra_sections\n'
    )
    # nested /* /* */ */ fully stripped -> the buried token is not credited
    assert not pdf_render.typst_source_references_extras(
        "/* outer /* inner */ still comment extra_sections */\n= hi\n"
    )
    # live reference is still credited
    assert pdf_render.typst_source_references_extras("#for s in r.extra_sections []\n")


def test_build_typst_sys_inputs_coerces_blank_strings_to_none():
    """The cleared-field editor writes '' (not null) for optional fields; the
    Typst path deep-coerces empty/whitespace-only strings to None so in-template
    `!= none` guards match LaTeX Jinja truthiness at every site at once."""
    data = json.loads(json.dumps(SAMPLE_RESUME))
    data["contact"]["location"] = ""
    data["contact"]["phone"] = "   "
    data["summary"] = "  "
    data["education"][0]["gpa"] = "\t"
    out = pdf_render.build_typst_sys_inputs(MINIMAL_TYP, data)
    resume = json.loads(out["resume"])
    assert resume["contact"]["location"] is None
    assert resume["contact"]["phone"] is None
    assert resume["summary"] is None
    assert resume["education"][0]["gpa"] is None
    # non-blank values are untouched
    assert resume["contact"]["name"] == "Jordan Sample"


def test_typst_extras_enforcement():
    with pytest.raises(pdf_render.TemplateMissingExtraSectionsError):
        pdf_render.build_typst_sys_inputs(MINIMAL_TYP, SAMPLE_RESUME, enforce_extras_support=True)
    # naming extra_sections only inside a comment is NOT support
    with pytest.raises(pdf_render.TemplateMissingExtraSectionsError):
        pdf_render.build_typst_sys_inputs(
            MINIMAL_TYP + "// renders extra_sections one day\n",
            SAMPLE_RESUME,
            enforce_extras_support=True,
        )
    assert pdf_render.build_typst_sys_inputs(EXTRAS_TYP, SAMPLE_RESUME, enforce_extras_support=True)


def _ready_typst_template(db_session, tid: str):
    from app.services import template_registry as reg

    reg.create_draft(
        db_session, id=tid, display_name=tid, source=EXTRAS_TYP, origin="mcp", engine="typst"
    )
    row = reg.get(db_session, tid)
    row.status = "ready"  # get_usable_template falls back to default unless ready
    db_session.commit()
    return row


def test_render_document_dispatches_by_engine(db_session):
    _ready_typst_template(db_session, "t1")
    doc = pdf_render.render_document(SAMPLE_RESUME, template_id="t1", session=db_session)
    assert doc.engine == "typst"
    assert doc.source_text == EXTRAS_TYP  # source IS the .typ, no Jinja pass
    assert set(doc.sys_inputs) == {"resume", "fmt"}
    latex_doc = pdf_render.render_document(SAMPLE_RESUME, template_id=None, session=db_session)
    assert latex_doc.engine == "latex" and latex_doc.sys_inputs is None
    assert "\\documentclass" in latex_doc.source_text


def test_render_document_merges_template_default_formatting(db_session):
    row = _ready_typst_template(db_session, "t2")
    row.default_formatting = {"font_size": 12}
    db_session.commit()
    doc = pdf_render.render_document(SAMPLE_RESUME, template_id="t2", session=db_session)
    assert json.loads(doc.sys_inputs["fmt"])["font_size"] == 12
    # caller layer wins over the theme layer (4-layer merge preserved)
    doc2 = pdf_render.render_document(
        SAMPLE_RESUME, template_id="t2", session=db_session, formatting={"font_size": 10}
    )
    assert json.loads(doc2.sys_inputs["fmt"])["font_size"] == 10


def test_render_and_compile_typst_writes_typ_and_returns_path(db_session, tmp_path):
    _ready_typst_template(db_session, "t3")
    src = pdf_render.render_and_compile(
        SAMPLE_RESUME,
        tmp_path / "tex" / "x.tex",
        tmp_path / "pdfs" / "x.pdf",
        template_id="t3",
        session=db_session,
    )
    assert src == tmp_path / "tex" / "x.typ" and src.exists()
    assert (tmp_path / "pdfs" / "x.pdf").exists()


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex not installed")
def test_render_and_compile_latex_returns_tex_path(db_session, tmp_path):
    src = pdf_render.render_and_compile(
        SAMPLE_RESUME, tmp_path / "x.tex", tmp_path / "x.pdf",
        template_id=None, session=db_session,
    )
    assert src == tmp_path / "x.tex" and src.exists()
    assert (tmp_path / "x.pdf").exists()
