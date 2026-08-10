import shutil

import pytest

from app.services.pdf_render import compile_pdf, latex_escape
from app.services.template_validation import SAMPLE_RESUME


# A serif font (XCharter) in a wrapping, book-set paragraph makes pdfTeX place
# most interword gaps as positional kerns rather than space glyphs, so a strict
# extractor (pdfplumber) joins the words. Reliable repro of the fidelity bug.
FRAGILE_XCHARTER_DOC = r"""\documentclass[letterpaper,11pt]{article}
\usepackage{XCharter}
\usepackage[T1]{fontenc}
\begin{document}
\small Data Scientist with over two years of hands-on production experience
building and shipping Solutions Architect grade machine learning systems on AWS,
with deep Technical Skills across data engineering and applied research work.
\end{document}
"""


def test_pdflatex_argv_enables_interword_spaces(tmp_path):
    from app.services.pdf_render import _pdflatex_argv

    tex = tmp_path / "resume.tex"
    argv = _pdflatex_argv(tex, tmp_path, "resume")
    assert argv[0] == "pdflatex"
    assert "-no-shell-escape" in argv
    assert "-interaction=nonstopmode" in argv
    assert "-halt-on-error" in argv
    assert f"-output-directory={tmp_path}" in argv
    assert "-jobname=resume" in argv
    # The final arg is TeX code: enable interword spaces, then \input the file.
    assert argv[-1] == (
        r"\pdfmapline{+dummy-space <dummy-space}\pdfinterwordspaceon"
        r"\input{" + str(tex) + "}"
    )
    # There is no opt-out. The cover-letter compile used to pass
    # no_shell_escape=False, handing `\write18` (arbitrary host commands) to a
    # document built from LLM-generated text; the parameter is gone on purpose.
    # The stronger assertion lives in test_security_boundaries.py.
    cl = _pdflatex_argv(tex, tmp_path, "cl")
    assert "-no-shell-escape" in cl


def test_compile_pdf_preserves_word_spacing_for_strict_extractor(tmp_path):
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is not installed")
    pdfplumber = pytest.importorskip("pdfplumber")

    pdf = compile_pdf(FRAGILE_XCHARTER_DOC, tmp_path, stem="frag")
    with pdfplumber.open(pdf) as doc:
        text = "\n".join((p.extract_text() or "") for p in doc.pages).replace("\n", " ")
    # Without the interword-space fix a strict extractor joins these phrases.
    for phrase in ["Data Scientist", "Solutions Architect", "Technical Skills"]:
        assert phrase in text, f"{phrase!r} lost its spaces: {text!r}"


def test_latex_escape_exhaustive_special_characters():
    assert latex_escape(r"\&%$#_{}~^") == (
        r"\textbackslash{}"
        r"\&"
        r"\%"
        r"\$"
        r"\#"
        r"\_"
        r"\{"
        r"\}"
        r"\textasciitilde{}"
        r"\textasciicircum{}"
    )


def test_compile_pdf_creates_pdf_when_pdflatex_available(tmp_path):
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is not installed")

    pdf_path = compile_pdf(
        r"""
\documentclass{article}
\begin{document}
Hello
\end{document}
""",
        tmp_path,
    )

    assert pdf_path.exists()
    assert pdf_path.name == "resume.pdf"


def test_compile_pdf_uses_custom_stem_when_pdflatex_available(tmp_path):
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is not installed")

    pdf_path = compile_pdf(
        r"""
\documentclass{article}
\begin{document}
Hello
\end{document}
""",
        tmp_path,
        stem="260501_Quill_Riley_DataAnalyst_TechCorp_Resume",
    )

    assert pdf_path.exists()
    assert pdf_path.name == "260501_Quill_Riley_DataAnalyst_TechCorp_Resume.pdf"


def test_render_tex_passes_fmt_to_template():
    from app.services.pdf_render import render_tex_from_source

    source = "((( fmt.font_size )))pt ((( fmt.header_align )))"
    out = render_tex_from_source(source, SAMPLE_RESUME)
    assert out == "11pt center"

    out = render_tex_from_source(
        source, SAMPLE_RESUME, formatting={"font_size": 12, "header_align": "left"}
    )
    assert out == "12pt left"


def test_render_merges_template_default_formatting(db_session):
    # a template whose default_formatting sets font_size 12, resume overrides
    # header_align only
    from app.services import template_registry as reg
    from app.services.pdf_render import render_document

    src = "((( fmt.font_size )))pt ((( fmt.header_align )))"
    reg.create_draft(db_session, id="themed", display_name="T", source=src, origin="mcp")
    row = reg.get(db_session, "themed")
    row.default_formatting = {"font_size": 12}
    row.status = "ready"
    db_session.commit()
    out = render_document(
        {
            "contact": {"name": "x", "email": "x@x.co"},
            "summary": "",
            "skills": [],
            "experience": [],
            "projects": [],
            "education": [],
            "certifications": [],
        },
        template_id="themed",
        session=db_session,
        formatting={"header_align": "left"},
    ).source_text
    assert out == "12pt left"  # font_size from template default, header_align from override


def _minimal_resume() -> dict:
    return {
        "contact": {"name": "x", "email": "x@x.co"},
        "summary": "",
        "skills": [],
        "experience": [],
        "projects": [],
        "education": [],
        "certifications": [],
    }


def test_render_falls_back_to_default_for_missing_template(db_session):
    # A persisted template_id pointing at a deleted template must still render
    # (via the default) rather than raising and 404-ing the render endpoint.
    from app.services import template_registry as reg
    from app.services.pdf_render import render_document

    reg.get_default(db_session)
    out = render_document(_minimal_resume(), template_id="ghost", session=db_session).source_text
    assert "documentclass" in out.lower()  # rendered the default template


def test_render_falls_back_to_default_for_not_ready_template(db_session):
    # A being-edited (draft, not-ready) template also falls back to default.
    from app.services import template_registry as reg
    from app.services.pdf_render import render_document

    reg.get_default(db_session)
    reg.create_draft(
        db_session, id="draft1", display_name="D", source=r"NEVER-RENDERED", origin="mcp"
    )
    out = render_document(_minimal_resume(), template_id="draft1", session=db_session).source_text
    assert "NEVER-RENDERED" not in out
    assert "documentclass" in out.lower()  # rendered the default template
