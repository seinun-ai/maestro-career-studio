import json
from pathlib import Path

from app.services.pdf_render import latex_escape, render_document


def test_latex_escape_handles_special_characters():
    assert latex_escape("40% & SQL_1") == r"40\% \& SQL\_1"


def test_template_renders_with_sample_data():
    path = Path(__file__).parent.parent.parent / "base_resumes" / "example.json"
    data = json.loads(path.read_text())

    tex = render_document(data).source_text

    assert "\\documentclass" in tex
    assert data["contact"]["name"] in tex
    assert "38\\%" in tex
    assert "\\section{Technical Skills}" in tex
