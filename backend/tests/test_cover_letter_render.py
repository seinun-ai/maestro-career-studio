from datetime import date

from app.services.pdf_render import render_cover_letter_tex


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
