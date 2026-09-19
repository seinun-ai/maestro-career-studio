import shutil
from datetime import date

import pytest

from app.services import pdf_render
from app.services.pdf_render import render_cover_letter_tex
from app.services.template_validation import SAMPLE_RESUME

TILDE_CONTACT = {
    "name": "Jane Doe",
    "email": "jane@example.com",
    "location": "Austin, TX",
    "linkedin": "linkedin.com/in/~jane",
    "github": "github.com/jane_dev",
}


def test_render_cover_letter_tex_includes_header_date_and_body():
    contact = {
        "name": "Jane Doe",
        "email": "jane@example.com",
        "location": "Austin, TX",
    }
    body = "Dear Hiring Manager,\n\nI am excited to apply.\n\nSincerely,\nJane"

    tex = render_cover_letter_tex(contact=contact, body=body, today=date(2026, 5, 1))

    assert "Jane Doe" in tex
    assert "jane@example.com" in tex
    assert "May 1, 2026" in tex
    assert "I am excited to apply." in tex
    assert "\\begin{document}" in tex


def test_cover_letter_header_urls_survive_a_tilde_and_underscore():
    tex = render_cover_letter_tex(
        contact=TILDE_CONTACT, body="Hi", today=date(2026, 5, 1)
    )
    assert r"\href{https://linkedin.com/in/~jane}" in tex
    assert r"\href{https://github.com/jane_dev}" in tex
    # Display text is typeset, so it keeps body escaping.
    assert r"\textasciitilde{}jane" in tex


def test_resume_header_urls_survive_a_tilde_and_underscore():
    source = (pdf_render.TEMPLATE_DIR / pdf_render.RESUME_TEMPLATE).read_text(
        encoding="utf-8"
    )
    tex = pdf_render.render_tex_from_source(
        source, {**SAMPLE_RESUME, "contact": TILDE_CONTACT}
    )
    assert r"\href{https://linkedin.com/in/~jane}" in tex
    assert r"\href{https://github.com/jane_dev}" in tex


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex not installed")
def test_cover_letter_with_tilde_url_compiles(tmp_path):
    tex = render_cover_letter_tex(
        contact=TILDE_CONTACT, body="Hi", today=date(2026, 5, 1)
    )
    assert pdf_render.compile_cover_letter_pdf(tex, tmp_path).exists()
