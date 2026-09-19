"""Cover letters follow the resume's engine (design 2026-09-19 §2.3)."""
import inspect
import json
import re
import shutil
from datetime import date
from pathlib import Path

import pytest

from app.services import pdf_render

pytest.importorskip("typst")
pytest.importorskip("pdfplumber")

CONTACT = {
    "name": "Jane Doe",
    "email": "jane@example.com",
    "phone": "",          # cleared in the editor: must not print "None"
    "location": "Austin, TX",
    "linkedin": "linkedin.com/in/janedoe",
    "github": None,
}
BODY = (
    "Dear Hiring Manager,\n\n"
    "I am excited to apply for the Data Analyst role at Acme.\n\n"
    "Sincerely,\nJane Doe"
)
TODAY = date(2026, 5, 1)


def _text(pdf: Path) -> str:
    import pdfplumber

    with pdfplumber.open(pdf) as doc:
        return " ".join(" ".join((p.extract_text() or "").split()) for p in doc.pages)


# pdfplumber's stand-in for a glyph with no ToUnicode entry: the LaTeX header's
# fontawesome icons come out as "(cid:239)" and would split into "cid"/"239".
_UNMAPPED_GLYPH_RE = re.compile(r"\(cid:\d+\)")


def _words(text: str) -> set[str]:
    # Icon glyphs (LaTeX fontawesome) and layout tokens fall out; words stay.
    # The Typst "·" separator and LaTeX's "~" / icon glue sit outside the
    # [a-z0-9] class by design, so only the words the reader sees are compared.
    text = _UNMAPPED_GLYPH_RE.sub(" ", text.lower())
    return set(re.findall(r"[a-z0-9][a-z0-9@./'-]*", text))


def test_typst_cover_letter_compiles_with_header_date_and_body(tmp_path):
    doc = pdf_render.render_cover_letter(engine="typst", contact=CONTACT, body=BODY, today=TODAY)
    assert doc.engine == "typst"
    pdf = pdf_render.compile_cover_letter_pdf(
        doc.source_text, tmp_path, stem="cl", engine=doc.engine, sys_inputs=doc.sys_inputs
    )
    text = _text(pdf)
    for needle in ("Jane Doe", "jane@example.com", "Austin, TX", "May 1, 2026",
                   "I am excited to apply", "Sincerely"):
        assert needle in text, text
    assert "None" not in text and "null" not in text


def test_latex_cover_letter_renders_tex():
    doc = pdf_render.render_cover_letter(engine="latex", contact=CONTACT, body=BODY, today=TODAY)
    assert doc.engine == "latex"
    assert "\\begin{document}" in doc.source_text
    # Callers that predate the engine parameter still get LaTeX.
    signature = inspect.signature(pdf_render.compile_cover_letter_pdf)
    assert signature.parameters["engine"].default == "latex"


def test_cover_letter_typst_inputs_pin_the_data_contract():
    inputs = pdf_render.cover_letter_typst_inputs(
        contact={**CONTACT, "phone": "  "}, body="x\n\n\n\ny", today=TODAY
    )
    contact = json.loads(inputs["contact"])
    assert contact["phone"] is None  # whitespace-only → null, never "None"
    assert contact["github"] is None
    assert json.loads(inputs["paragraphs"]) == ["x", "y"]
    assert inputs["today"] == "May 1, 2026"
    fmt = json.loads(inputs["fmt"])
    assert "font_size" in fmt and "header_align" in fmt
    # Typst mirrors LaTeX (decision 2026-09-19): a lone newline is a space.
    signoff = pdf_render.cover_letter_typst_inputs(
        contact=CONTACT, body="Sincerely,\nJane", today=TODAY
    )
    assert json.loads(signoff["paragraphs"]) == ["Sincerely, Jane"]


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex not installed")
def test_cover_letter_parity_across_engines(tmp_path):
    latex = pdf_render.render_cover_letter(engine="latex", contact=CONTACT, body=BODY, today=TODAY)
    typst = pdf_render.render_cover_letter(engine="typst", contact=CONTACT, body=BODY, today=TODAY)
    a = _text(pdf_render.compile_cover_letter_pdf(latex.source_text, tmp_path / "l", engine="latex"))
    b = _text(pdf_render.compile_cover_letter_pdf(
        typst.source_text, tmp_path / "t", engine="typst", sys_inputs=typst.sys_inputs
    ))
    assert _words(a) == _words(b)
