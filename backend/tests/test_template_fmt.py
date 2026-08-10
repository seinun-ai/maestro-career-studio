"""Classic template consumes every fmt knob; defaults compile identically."""

import copy
from pathlib import Path

from app.services.pdf_render import render_tex_from_source

# Reuse the validation sample so content exercises every section.
from app.services.template_validation import SAMPLE_RESUME

TEMPLATE = (
    Path(__file__).parents[1] / "app" / "templates" / "resume.tex.j2"
).read_text(encoding="utf-8")

# SAMPLE_RESUME uses year-only dates (which pass through format_date verbatim);
# give one entry a month-bearing date so date_format reformatting is observable.
SAMPLE = copy.deepcopy(SAMPLE_RESUME)
SAMPLE["experience"][0]["start_date"] = "Jun 2021"


def _render(**formatting):
    return render_tex_from_source(TEMPLATE, SAMPLE, formatting=formatting or None)


def test_default_render_uses_classic_defaults():
    tex = _render()
    assert "\\documentclass[letterpaper,11pt]{article}" in tex
    assert "lmargin=0.4in" in tex and "tmargin=0.3in" in tex
    assert "\\begin{center}" in tex  # header centered
    assert "$\\bullet$" in tex  # bullet glyph
    assert "\\titlerule" in tex  # divider on
    assert "\\raggedright" in tex  # not justified


def test_each_knob_changes_output():
    assert "\\documentclass[letterpaper,12pt]{article}" in _render(font_size=12)
    assert "lmargin=0.75in" in _render(side_margins=0.75)
    assert "\\titlerule" not in _render(hide_divider=True)
    assert "$\\bullet$" not in _render(bullet_icon="dash")
    assert "\\begin{flushleft}" in _render(header_align="left")
    assert "\\raggedright" not in _render(justify=True)
    assert "\\linespread{1.2}" in _render(line_spacing=1.2)
    dated = _render(date_format="long_month")
    assert "June" in dated  # sample dates reformatted


def test_section_spacing_polarity_higher_means_more_space():
    # Default (6) reproduces Classic's negative vspaces exactly.
    default = _render()
    assert "\\vspace{-6pt}" in default and "\\vspace{-12pt}" in default
    # A HIGHER section_spacing must ADD space, i.e. produce LESS-negative
    # vspace — not tighten the layout (the control label promises more space).
    loose = _render(section_spacing=14)
    assert "\\vspace{2pt}" in loose and "\\vspace{-4pt}" in loose
    assert "\\vspace{-20pt}" not in loose  # must not go more negative
    # A LOWER value tightens.
    tight = _render(section_spacing=0)
    assert "\\vspace{-12pt}" in tight and "\\vspace{-18pt}" in tight


def test_education_order_and_skills_layout_change_output():
    # These knobs were previously only smoke-compiled; assert they alter output.
    inst_first = _render(education_order="institution_first")
    degree_first = _render(education_order="degree_first")
    assert inst_first != degree_first
    bulleted = _render(skills_layout="bulleted")
    inline = _render(skills_layout="inline")
    assert bulleted != inline


def test_extreme_values_compile(tmp_path):
    from app.services.pdf_render import compile_pdf

    for formatting in (
        {},
        {
            "font_size": 10,
            "side_margins": 0.3,
            "top_bottom_margin": 0.3,
            "section_spacing": 0,
            "line_spacing": 0.9,
            "bullet_icon": "dash",
            "hide_divider": True,
            "header_align": "left",
            "justify": True,
            "date_format": "numeric",
            "education_order": "institution_first",
            "skills_layout": "bulleted",
        },
        {
            "font_size": 12,
            "side_margins": 1.0,
            "top_bottom_margin": 1.0,
            "section_spacing": 14,
            "entry_spacing": 10,
            "line_spacing": 1.4,
            "header_align": "right",
        },
    ):
        tex = _render(**formatting)
        compile_pdf(tex, tmp_path / str(abs(hash(str(formatting)))))
