from app.services import pdf_render, template_registry as reg

SIMPLE = {"contact": {"name": "Ada Lovelace", "email": "ada@x.test"}, "summary": "Hi there"}


def test_render_from_source_uses_header_include():
    src = "((* set contact = resume.contact *))((* include '_header.tex.j2' *))\nBODY-MARKER"
    out = pdf_render.render_tex_from_source(src, SIMPLE)
    assert "Ada Lovelace" in out
    assert "BODY-MARKER" in out


def test_render_does_not_html_escape_ampersand():
    # A data value with "&" must become the LaTeX escape "\&", never the HTML
    # entity "&amp;". Regression: Jinja from_string defaulted autoescape ON,
    # which HTML-escaped every expression's output.
    data = {
        "contact": {"name": "A & B", "email": "x@y.z"},
        "summary": "R&D and Q&A",
    }
    src = (
        "((( resume.contact.name|latex_escape ))) // "
        "((( resume.summary|latex_escape )))"
    )
    out = pdf_render.render_tex_from_source(src, data)
    assert "&amp;" not in out
    assert r"A \& B" in out
    assert r"R\&D" in out


def test_render_tex_default_matches_file_default(db_session):
    reg.get_default(db_session)  # seeds default == file content
    from_db = pdf_render.render_document(SIMPLE, template_id=None, session=db_session).source_text
    from_file = pdf_render.render_tex_from_source(
        (pdf_render.TEMPLATE_DIR / pdf_render.RESUME_TEMPLATE).read_text(encoding="utf-8"), SIMPLE
    )
    assert from_db == from_file


def test_render_tex_no_session_uses_file_default():
    # backward-compat: no DB context falls back to the on-disk default
    out = pdf_render.render_document(SIMPLE).source_text
    assert "Ada Lovelace" in out


def test_render_tex_falls_back_for_draft(db_session):
    # A not-ready (draft) template is tolerated at render time: fall back to the
    # default rather than raising, so the resume stays renderable.
    reg.create_draft(db_session, id="d", display_name="D", source="X", origin="mcp")
    out = pdf_render.render_document(SIMPLE, template_id="d", session=db_session).source_text
    default_out = pdf_render.render_document(SIMPLE, template_id=None, session=db_session).source_text
    assert out == default_out
    assert "X" != out  # did not render the draft's trivial source


def test_render_tex_falls_back_for_unknown(db_session):
    # A persisted template_id pointing at a deleted/unknown template falls back
    # to the default instead of raising.
    out = pdf_render.render_document(SIMPLE, template_id="nope", session=db_session).source_text
    default_out = pdf_render.render_document(SIMPLE, template_id=None, session=db_session).source_text
    assert out == default_out
