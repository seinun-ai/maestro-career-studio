"""Golden + parity tests for the bundled user templates."""
import copy
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from app.config import settings
from app.schemas.formatting import ResumeFormatting
from app.services import pdf_render, template_registry
from app.services.pdf_render import render_tex_from_source
from scripts.template_parity import (
    LINE_CLUSTER_TOL,
    cluster_line_tops,
    pdf_metrics,
    render_template_pdf,
)


def _xcharter_resolvable() -> bool:
    """Whether any configured font dir actually holds XCharter.

    Typst does not error on a missing font directory — it silently substitutes
    its embedded fonts, so an unresolvable XCharter shows up as a mystifying
    parity failure several assertions deep. The fonts are vendored (config
    VENDORED_FONTS_DIR), so this should always be true; it stays as a guard for
    a stripped checkout or a TYPST_FONT_PATHS override pointing somewhere empty,
    and turns that into one actionable skip instead of a wall of red.
    """
    return any(
        path.is_dir() and any(path.glob("XCharter-*.otf"))
        for path in settings.typst_font_paths
    )


requires_xcharter = pytest.mark.skipif(
    not _xcharter_resolvable(),
    reason=(
        "XCharter not found in settings.typst_font_paths "
        f"({[str(p) for p in settings.typst_font_paths]}). The fonts ship in "
        "backend/app/assets/fonts/xcharter — restore them, or point "
        "TYPST_FONT_PATHS at a directory containing XCharter-*.otf."
    ),
)

# Anchored on this file, never on the CWD: these run at COLLECTION time, so a
# relative path makes `pytest` from the repo root fail before a single test.
BACKEND_DIR = Path(__file__).resolve().parents[1]
USER_DIR = BACKEND_DIR / "app" / "templates" / "user"
FIXTURES = BACKEND_DIR / "tests" / "fixtures"
EXAMPLE = json.loads(
    (BACKEND_DIR.parent / "base_resumes" / "example.json").read_text(encoding="utf-8")
)

# Golden thresholds: identical structure, tolerant of a small uniform
# vertical shift (the fullpage->geometry switch moves the frame slightly).
SIZE_TOL = 0.25
REL_TOP_TOL = 6.0
ENGINE_REL_TOP_TOL = 6.0
# Cross-engine tolerance for a NON-default knob value: the two engines start
# from the same default calibration but accumulate their own rounding per
# section, so a knob sweep is held to a looser band than the default render.
KNOB_ENGINE_REL_TOP_TOL = 8.0
# The new render may not open a vertical band the original render lacks.
BLANK_BAND_TOL = 4.0
SECTION_TITLES = (
    "summary",
    "experience",
    "projects",
    "technical skills",
    "education",
)

# The parity CLI resolves `scripts.template_parity` relative to the backend
# package root; tests must not depend on pytest's CWD (repo root is canonical).
_BACKEND_DIR = Path(__file__).resolve().parents[1]


def _render(**formatting):
    source = (USER_DIR / "xcharter_serif.tex.j2").read_text()
    return render_tex_from_source(source, EXAMPLE, formatting=formatting or None)


def _relative_tops(m):
    tops = m["section_tops"]
    if not tops:
        return {}
    base = min(tops.values())
    return {k: v - base for k, v in tops.items()}


def _render_typst(tmp_path, stem, *, resume=EXAMPLE, **formatting):
    source = (USER_DIR / "xcharter_serif.typ").read_text()
    return render_template_pdf(
        source,
        "typst",
        resume,
        formatting or None,
        tmp_path,
        stem,
    )


@pytest.fixture(scope="module")
def typst_default_pdf(tmp_path_factory):
    return _render_typst(tmp_path_factory.mktemp("typst-default"), "default")


def _pdf_text(pdf_path):
    import pdfplumber

    with pdfplumber.open(pdf_path) as doc:
        return "\n".join(page.extract_text() or "" for page in doc.pages)


def _line_containing(pdf_path, phrase):
    """Locate a VISUAL line. Words must be clustered, not grouped on the raw
    top: XCharter's ascenders sit above its cap height, so "Workshop" reports a
    different top than "Open Metrics" on the very same line."""
    import pdfplumber

    phrase = phrase.casefold()
    page_offset = 0.0
    with pdfplumber.open(pdf_path) as doc:
        for page in doc.pages:
            words = page.extract_words(extra_attrs=["size"])
            for top, group in cluster_line_tops(words):
                group = sorted(group, key=lambda word: word["x0"])
                text = " ".join(word["text"] for word in group)
                if phrase in text.casefold():
                    return {
                        "top": page_offset + top,
                        "x0": min(word["x0"] for word in group),
                        "x1": max(word["x1"] for word in group),
                        "max_size": max(word["size"] for word in group),
                        "text": text,
                    }
            page_offset += page.height
    raise AssertionError(f"no PDF line contains {phrase!r}")


def _word_x0(pdf_path, word_text):
    """Left edge of a single extracted word (the bullet BODY column, when the
    word is the first one after a list marker)."""
    import pdfplumber

    with pdfplumber.open(pdf_path) as doc:
        for page in doc.pages:
            for word in page.extract_words():
                if word["text"] == word_text:
                    return word["x0"]
    raise AssertionError(f"no PDF word equals {word_text!r}")


def _drawing_count(pdf_path):
    """Count vector drawing objects across the document.

    pdfplumber (MIT), not PyMuPDF: `fitz` is AGPL-3.0 and this project ships
    under Apache 2.0, so it cannot be a dependency of any kind — see
    THIRD_PARTY_NOTICES.md. It was also in no dependency group, so this passed
    only on machines that happened to have PyMuPDF installed and failed in a
    clean environment.

    The absolute number differs from what `get_drawings()` returned, and that
    is fine: every caller compares two PDFs counted the same way, so only the
    DELTA has to be meaningful.
    """
    import pdfplumber

    with pdfplumber.open(pdf_path) as doc:
        return sum(
            len(page.lines) + len(page.rects) + len(page.curves) for page in doc.pages
        )


def _font_names_at_size(pdf_path, expected_size):
    import pdfplumber

    with pdfplumber.open(pdf_path) as doc:
        return {
            word["fontname"]
            for page in doc.pages
            for word in page.extract_words(extra_attrs=["size", "fontname"])
            if word["size"] == pytest.approx(expected_size, abs=0.15)
        }


def _normalized_tokens(words):
    return tuple(
        token
        for word in words
        for token in re.findall(r"[a-z0-9]+", word.casefold())
    )


@pytest.fixture(scope="module")
def section_spacing_pdfs(tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("section-spacing")
    sources = {
        "latex": (USER_DIR / "xcharter_serif.tex.j2").read_text(),
        "typst": (USER_DIR / "xcharter_serif.typ").read_text(),
    }
    return {
        (engine, value): render_template_pdf(
            source,
            engine,
            EXAMPLE,
            {"section_spacing": value},
            out_dir,
            f"{engine}-{value}",
        )
        for engine, source in sources.items()
        for value in (0, 6, 14)
    }


@pytest.fixture(scope="module")
def entry_spacing_pdfs(tmp_path_factory):
    resume = copy.deepcopy(EXAMPLE)
    second_education = copy.deepcopy(resume["education"][0])
    second_education["institution"] = "Second Sample University"
    resume["education"].append(second_education)
    resume["extra_sections"] = [
        {
            "key": "publications",
            "title": "Selected Publications",
            "type": "entries",
            "entries": [
                {
                    "heading": "Sentinel Publication Alpha",
                    "subheading": "Journal of Examples",
                    "location": "Remote",
                    "date": "June 2024",
                    "bullets": [],
                },
                {
                    "heading": "Sentinel Publication Beta",
                    "subheading": "Proceedings of Examples",
                    "location": "Remote",
                    "date": "July 2024",
                    "bullets": [],
                },
            ],
        }
    ]
    out_dir = tmp_path_factory.mktemp("entry-spacing")
    sources = {
        "latex": (USER_DIR / "xcharter_serif.tex.j2").read_text(),
        "typst": (USER_DIR / "xcharter_serif.typ").read_text(),
    }
    return {
        (engine, value): render_template_pdf(
            source,
            engine,
            resume,
            {"entry_spacing": value},
            out_dir,
            f"{engine}-{value}",
        )
        for engine, source in sources.items()
        for value in (0, 1)
    }


KNOB_SWEEP_CASES = {
    "font10": {"font_size": 10},
    "font12": {"font_size": 12},
    "bulleted": {"skills_layout": "bulleted"},
    "hidden": {"hide_divider": True},
    "dash": {"bullet_icon": "dash"},
}


@pytest.fixture(scope="module")
def knob_sweep_pdfs(tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("knob-sweep")
    sources = {
        "latex": (USER_DIR / "xcharter_serif.tex.j2").read_text(),
        "typst": (USER_DIR / "xcharter_serif.typ").read_text(),
    }
    return {
        (engine, case): render_template_pdf(
            source,
            engine,
            EXAMPLE,
            formatting,
            out_dir,
            f"{engine}-{case}",
        )
        for engine, source in sources.items()
        for case, formatting in KNOB_SWEEP_CASES.items()
    }


def test_bundled_latex_matches_original_golden(tmp_path):
    original = (FIXTURES / "xcharter_serif_original.tex.j2").read_text()
    bundled = (USER_DIR / "xcharter_serif.tex.j2").read_text()
    m_orig = pdf_metrics(
        render_template_pdf(original, "latex", EXAMPLE, None, tmp_path, "orig")
    )
    m_new = pdf_metrics(
        render_template_pdf(bundled, "latex", EXAMPLE, None, tmp_path, "new")
    )
    assert m_new["pages"] == m_orig["pages"]
    assert m_new["line_count"] == m_orig["line_count"]
    assert abs(m_new["left"] - m_orig["left"]) <= 1.0
    assert abs(m_new["width"] - m_orig["width"]) <= 1.5
    rel_o, rel_n = _relative_tops(m_orig), _relative_tops(m_new)
    assert set(rel_o) == set(SECTION_TITLES)
    assert rel_o.keys() == rel_n.keys()
    for k in rel_o:
        assert abs(rel_o[k] - rel_n[k]) <= REL_TOP_TOL, k
    # No blank bands: the knob wiring must not open a gap the original lacks.
    assert m_new["max_line_gap"] <= m_orig["max_line_gap"] + BLANK_BAND_TOL, (
        m_new["max_line_gap"],
        m_orig["max_line_gap"],
    )
    # The clustering tolerance must stay well clear of a real baseline pitch.
    assert m_new["min_line_gap"] > LINE_CLUSTER_TOL
    assert m_new["em_dashes"] == 0
    assert m_new["joined_suspects"] <= m_orig["joined_suspects"]
    assert sorted(m_new["words_pdfplumber"]) == sorted(m_orig["words_pdfplumber"])


@requires_xcharter
def test_typst_port_engine_parity(tmp_path):
    latex = (USER_DIR / "xcharter_serif.tex.j2").read_text()
    typst = (USER_DIR / "xcharter_serif.typ").read_text()
    m_l = pdf_metrics(render_template_pdf(latex, "latex", EXAMPLE, None, tmp_path, "l"))
    m_t = pdf_metrics(render_template_pdf(typst, "typst", EXAMPLE, None, tmp_path, "t"))
    # Hard-require XCharter actually loaded (no silent Libertinus fallback):
    assert any("XCharter" in f for f in m_t["fontnames"]), (
        "Typst fell back to embedded fonts — export TYPST_FONT_PATHS"
    )
    assert m_t["pages"] == m_l["pages"]
    assert m_t["line_count"] == m_l["line_count"]
    assert abs(m_t["left"] - m_l["left"]) <= 1.0
    assert abs(m_t["width"] - m_l["width"]) <= 2.0
    for a, b in ((m_t, m_l),):
        rel_a, rel_b = _relative_tops(a), _relative_tops(b)
        assert set(rel_a) == set(SECTION_TITLES)
        assert rel_a.keys() == rel_b.keys()
        for k in rel_a:
            assert abs(rel_a[k] - rel_b[k]) <= ENGINE_REL_TOP_TOL, k
    assert m_t["em_dashes"] == 0
    assert m_t["joined_suspects"] <= max(m_l["joined_suspects"], 4)
    # Extraction: every LaTeX word survives modulo separator/ligature noise.
    from collections import Counter

    diff = Counter(m_l["words_pdfplumber"]) - Counter(m_t["words_pdfplumber"])
    assert sum(diff.values()) <= 8, diff


@requires_xcharter
@pytest.mark.parametrize("case", sorted(KNOB_SWEEP_CASES))
def test_engine_parity_survives_non_default_knob_values(knob_sweep_pdfs, case):
    """The two engines must still agree once a knob leaves its default.

    justify and line_spacing are deliberately excluded: their cross-engine
    drift is an accepted line-breaking difference, not a calibration bug.
    """
    latex = pdf_metrics(knob_sweep_pdfs["latex", case])
    typst = pdf_metrics(knob_sweep_pdfs["typst", case])
    assert typst["pages"] == latex["pages"], case
    assert typst["line_count"] == latex["line_count"], case
    rel_l, rel_t = _relative_tops(latex), _relative_tops(typst)
    assert set(rel_l) == set(SECTION_TITLES), case
    assert rel_l.keys() == rel_t.keys(), case
    for title in rel_l:
        assert abs(rel_l[title] - rel_t[title]) <= KNOB_ENGINE_REL_TOP_TOL, (
            case,
            title,
            rel_l[title],
            rel_t[title],
        )


@requires_xcharter
@pytest.mark.parametrize("case", ["default", "dash"])
def test_typst_port_bullet_body_sits_on_the_latex_indent(
    knob_sweep_pdfs,
    section_spacing_pdfs,
    case,
):
    """The body column is LaTeX's \\leftmarginii and must not move with the
    marker: a wider marker grows leftwards, exactly as LaTeX's label box does."""
    if case == "default":
        latex_pdf, typst_pdf = (
            section_spacing_pdfs["latex", 6],
            section_spacing_pdfs["typst", 6],
        )
    else:
        latex_pdf, typst_pdf = (
            knob_sweep_pdfs["latex", case],
            knob_sweep_pdfs["typst", case],
        )
    latex_x0 = _word_x0(latex_pdf, "Designed")
    typst_x0 = _word_x0(typst_pdf, "Designed")
    assert abs(typst_x0 - latex_x0) <= 1.0, (case, typst_x0, latex_x0)


@pytest.mark.parametrize("engine", ["latex", "typst"])
@pytest.mark.parametrize(
    ("date_row", "second_row"),
    [
        ("Example Analytics Cooperative", "Senior Data Engineer"),
        ("Demo Logistics Laboratory", "Data Engineer Remote"),
        ("Bachelor of Science", "Sample State Institute"),
    ],
)
def test_entry_grid_second_row_is_right_aligned(
    section_spacing_pdfs,
    engine,
    date_row,
    second_row,
):
    """Location/GPA must land on the same right edge as the date above them."""
    pdf = section_spacing_pdfs[engine, 6]
    top = _line_containing(pdf, date_row)["x1"]
    bottom = _line_containing(pdf, second_row)["x1"]
    assert abs(bottom - top) <= 2.0, (engine, date_row, bottom, top)


@pytest.mark.parametrize("engine", ["latex", "typst"])
def test_header_align_right_pushes_the_name_to_the_right_margin(tmp_path, engine):
    filename = "xcharter_serif.tex.j2" if engine == "latex" else "xcharter_serif.typ"
    source = (USER_DIR / filename).read_text()
    centered = render_template_pdf(
        source, engine, EXAMPLE, None, tmp_path, f"{engine}-centered"
    )
    right = render_template_pdf(
        source,
        engine,
        EXAMPLE,
        {"header_align": "right"},
        tmp_path,
        f"{engine}-right",
    )
    assert (
        _line_containing(right, "Morgan Example")["x0"]
        > _line_containing(centered, "Morgan Example")["x0"] + 100
    )
    # A full-width entry row marks the text block's right edge.
    margin = _line_containing(right, "Example Analytics Cooperative")["x1"]
    assert _line_containing(right, "Morgan Example")["x1"] == pytest.approx(
        margin, abs=1.0
    )


@pytest.mark.parametrize("engine", ["latex", "typst"])
@pytest.mark.parametrize("value", [0, 14])
def test_section_spacing_moves_each_section_gap_by_exactly_one_point(
    section_spacing_pdfs,
    engine,
    value,
):
    default = pdf_metrics(section_spacing_pdfs[engine, 6])
    altered = pdf_metrics(section_spacing_pdfs[engine, value])
    knob_delta = value - 6

    assert tuple(default["section_tops"]) == SECTION_TITLES
    assert tuple(altered["section_tops"]) == SECTION_TITLES
    for gap_number, title in enumerate(SECTION_TITLES, start=1):
        cumulative_delta = (
            altered["section_tops"][title] - default["section_tops"][title]
        )
        assert cumulative_delta == pytest.approx(
            gap_number * knob_delta,
            abs=0.25,
        ), (engine, value, title)


@pytest.mark.parametrize("engine", ["latex", "typst"])
@pytest.mark.parametrize("value", [0, 6, 14])
def test_section_spacing_preserves_extracted_token_sequences(
    section_spacing_pdfs,
    engine,
    value,
):
    default = pdf_metrics(section_spacing_pdfs[engine, 6])
    altered = pdf_metrics(section_spacing_pdfs[engine, value])
    for extractor in ("words_pdfplumber", "words_pdfium"):
        assert _normalized_tokens(altered[extractor]) == _normalized_tokens(
            default[extractor]
        ), (engine, value, extractor)


def test_default_engine_parity_has_identical_dual_extractor_sequences(
    section_spacing_pdfs,
):
    latex = pdf_metrics(section_spacing_pdfs["latex", 6])
    typst = pdf_metrics(section_spacing_pdfs["typst", 6])
    for extractor in ("words_pdfplumber", "words_pdfium"):
        assert _normalized_tokens(latex[extractor]) == _normalized_tokens(
            typst[extractor]
        ), extractor


@requires_xcharter
@pytest.mark.parametrize(
    ("engine", "emphasis_role"),
    [
        # BOTH engines use the true italic. typst used to resolve to
        # XCharter-Slanted here, and that was never a decision — the vendored
        # set carried Italic and Slanted, both declaring family XCharter with
        # the italic bit, so the winner was whichever the filesystem enumerated
        # first. macOS picked Slanted, Linux picked Italic, and this assertion
        # was the only thing that noticed. The Slanted faces are gone; see
        # app/assets/fonts/xcharter/README.md.
        ("latex", "XCharter-Italic"),
        ("typst", "XCharter-Italic"),
    ],
)
def test_default_engine_parity_uses_named_xcharter_font_roles(
    section_spacing_pdfs,
    engine,
    emphasis_role,
):
    pdf = section_spacing_pdfs[engine, 6]
    # `all()` over an empty set is vacuously true, so every role set is
    # required to be non-empty before it is checked.
    name_fonts = _font_names_at_size(pdf, 24.8)
    assert name_fonts, engine
    assert all(name.endswith("XCharter-Roman") for name in name_fonts)
    title_fonts = _font_names_at_size(pdf, 12.0)
    assert title_fonts, engine
    assert all(name.endswith("XCharter-Bold") for name in title_fonts)
    body_fonts = _font_names_at_size(pdf, 10.0)
    assert body_fonts, engine
    for role in ("XCharter-Roman", "XCharter-Bold", emphasis_role):
        # Report what was ACTUALLY embedded, not just what was wanted. The
        # bare (engine, role) tuple this used to raise says a face is missing
        # and nothing about what took its place, which is unactionable on a
        # machine you cannot attach to — it cost a full CI cycle to learn that
        # much. Font names carry a random subset prefix (`ABCDEF+`), so the
        # set is only meaningful printed whole.
        assert any(name.endswith(role) for name in body_fonts), (
            f"{engine}: no body font matching {role!r}; embedded at 10.0pt: "
            f"{sorted(body_fonts)}"
        )
    # Entry heading rows are \small on both engines, so the document has no
    # text at the 11pt document size at all.
    assert not _font_names_at_size(pdf, 11.0), engine


@pytest.mark.parametrize("engine", ["latex", "typst"])
@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("Example Analytics Cooperative", "Demo Logistics Laboratory"),
        # Full titles: "Open" also matches "OpenTelemetry" in the skills block,
        # and _line_containing returns the FIRST line containing the substring.
        ("Open Metrics Workshop", "Transit Reliability Explorer"),
        ("Sentinel Publication Alpha", "Sentinel Publication Beta"),
        ("Sample State Institute", "Second Sample University"),
    ],
)
def test_entry_spacing_moves_each_entry_gap_by_exactly_one_point(
    entry_spacing_pdfs,
    engine,
    first,
    second,
):
    compact = entry_spacing_pdfs[engine, 0]
    roomier = entry_spacing_pdfs[engine, 1]
    compact_gap = (
        _line_containing(compact, second)["top"]
        - _line_containing(compact, first)["top"]
    )
    roomier_gap = (
        _line_containing(roomier, second)["top"]
        - _line_containing(roomier, first)["top"]
    )
    assert roomier_gap - compact_gap == pytest.approx(1.0, abs=0.25), (
        engine,
        first,
    )


def test_example_cli_aligns_corresponding_logical_lines():
    result = subprocess.run(
        [sys.executable, "-m", "scripts.template_parity", "--example"],
        check=True,
        capture_output=True,
        text=True,
        cwd=_BACKEND_DIR,
    )
    rows = result.stdout.splitlines()
    for heading in (
        "Summary",
        "Experience",
        "Projects",
        "Technical Skills",
        "Education",
    ):
        assert any(
            row.startswith("match ") and row.endswith(f"  {heading} | {heading}")
            for row in rows
        ), heading
    # Unmatched lines are ALLOWED (an engine may wrap one line differently) but
    # must never be the bulk of the dump; requiring them, as this once did,
    # would have made imperfect correspondence a passing condition.
    matched = sum(row.startswith("match ") for row in rows)
    unmatched = sum("<unmatched>" in row for row in rows)
    assert matched > 0
    assert unmatched <= matched


def test_bundled_latex_heading_size_does_not_depend_on_the_summary(tmp_path):
    """The summary's \\small used to leak document-wide, so entry heading rows
    silently changed size when a resume had no summary."""
    source = (USER_DIR / "xcharter_serif.tex.j2").read_text()
    without_summary = copy.deepcopy(EXAMPLE)
    without_summary["summary"] = None
    with_pdf = render_template_pdf(source, "latex", EXAMPLE, None, tmp_path, "sum")
    without_pdf = render_template_pdf(
        source, "latex", without_summary, None, tmp_path, "nosum"
    )
    for pdf in (with_pdf, without_pdf):
        for phrase in ("Example Analytics Cooperative", "Bachelor of Science"):
            assert _line_containing(pdf, phrase)["max_size"] == pytest.approx(
                10.0, abs=0.15
            ), (pdf, phrase)


def test_bundled_latex_escapes_contact_url_targets(tmp_path):
    """Brace/backslash in a contact URL must not break TeX's parse of \\href."""
    source = (USER_DIR / "xcharter_serif.tex.j2").read_text()
    resume = {
        "contact": {
            "name": "Brace Example",
            "email": "brace}user@example.com",
            "linkedin": "linkedin.com/in/a}b",
            "github": "github.com/c\\d",
            "website": "example.com/e#f",
        }
    }
    tex = render_tex_from_source(source, resume, formatting=None)
    # Every URL target is escaped; display text keeps the body escaping.
    assert r"\href{mailto:brace\}user@example.com}" in tex
    assert r"\href{https://linkedin.com/in/a\}b}" in tex
    assert r"\href{https://github.com/c\char92{}d}" in tex
    assert r"\href{https://example.com/e\#f}" in tex
    pdf = render_template_pdf(source, "latex", resume, None, tmp_path, "braces")
    text = _pdf_text(pdf)
    assert "linkedin.com/in/a" in text
    assert "github.com/c" in text


def test_bundled_latex_supports_all_13_knobs():
    source = (USER_DIR / "xcharter_serif.tex.j2").read_text()
    keys = template_registry.supported_fmt_keys(source, "latex")
    assert set(keys) == set(ResumeFormatting.model_fields)


def test_typst_port_source_invariants_and_supports_extra_sections():
    source = (USER_DIR / "xcharter_serif.typ").read_text()
    assert "\N{EM DASH}" not in source
    assert "---" not in source
    assert pdf_render.typst_source_references_extras(source)


def test_typst_port_supports_all_13_knobs():
    source = (USER_DIR / "xcharter_serif.typ").read_text()
    keys = template_registry.supported_fmt_keys(source, "typst")
    assert set(keys) == set(ResumeFormatting.model_fields)


def test_typst_port_font_size_scales_body_type_but_pins_the_name(
    tmp_path,
    typst_default_pdf,
):
    """\\small scales with the class option, \\Huge caps at 24.88pt in all three,
    so the body must move with font_size and the name must not."""
    smaller = _render_typst(tmp_path, "smaller-font", font_size=10)
    larger = _render_typst(tmp_path, "larger-font", font_size=12)

    def body(pdf):
        return _line_containing(pdf, "Data engineer with six years")["max_size"]

    def name(pdf):
        return _line_containing(pdf, "Morgan Example")["max_size"]

    assert body(smaller) < body(typst_default_pdf) < body(larger)
    for pdf in (smaller, larger):
        assert name(pdf) == pytest.approx(name(typst_default_pdf), abs=0.05)


def test_typst_port_side_margins_move_section_left_edge(tmp_path, typst_default_pdf):
    wider = _render_typst(tmp_path, "wider-margins", side_margins=0.6)
    assert (
        _line_containing(wider, "Summary")["x0"]
        > _line_containing(typst_default_pdf, "Summary")["x0"] + 10
    )


def test_typst_port_top_bottom_margin_moves_header_down(tmp_path, typst_default_pdf):
    taller = _render_typst(tmp_path, "taller-margins", top_bottom_margin=0.7)
    assert (
        _line_containing(taller, "Morgan Example")["top"]
        > _line_containing(typst_default_pdf, "Morgan Example")["top"] + 20
    )


@pytest.mark.parametrize(
    "value",
    [14, 0, 1, 2, 3, 4, 5],
)
def test_typst_port_section_spacing_tracks_one_point_delta_both_ways(
    tmp_path,
    typst_default_pdf,
    value,
):
    altered = _render_typst(
        tmp_path,
        f"section-spacing-{value}",
        section_spacing=value,
    )
    delta = (
        _line_containing(altered, "Summary")["top"]
        - _line_containing(typst_default_pdf, "Summary")["top"]
    )
    assert delta == pytest.approx(value - 6, abs=0.2)


def test_typst_port_entry_spacing_increases_inter_entry_gap(tmp_path, typst_default_pdf):
    roomier = _render_typst(tmp_path, "entry-spacing", entry_spacing=6)

    def company_gap(pdf_path):
        first = _line_containing(pdf_path, "Example Analytics Cooperative")["top"]
        second = _line_containing(pdf_path, "Demo Logistics Laboratory")["top"]
        return second - first

    assert company_gap(roomier) > company_gap(typst_default_pdf) + 4


def test_typst_port_line_spacing_increases_entry_height(tmp_path, typst_default_pdf):
    roomier = _render_typst(tmp_path, "line-spacing", line_spacing=1.2)

    def company_gap(pdf_path):
        first = _line_containing(pdf_path, "Example Analytics Cooperative")["top"]
        second = _line_containing(pdf_path, "Demo Logistics Laboratory")["top"]
        return second - first

    assert company_gap(roomier) > company_gap(typst_default_pdf) + 8


def test_typst_port_bullet_icon_changes_rendered_markers(tmp_path, typst_default_pdf):
    dashed = _render_typst(tmp_path, "dash-bullets", bullet_icon="dash")
    assert "\N{BULLET}" in _pdf_text(typst_default_pdf)
    assert "\N{BULLET}" not in _pdf_text(dashed)
    assert "\N{EN DASH}" in _pdf_text(dashed)


def test_typst_port_hide_divider_removes_exactly_one_rule_per_section(
    tmp_path,
    typst_default_pdf,
):
    hidden = _render_typst(tmp_path, "hidden-dividers", hide_divider=True)
    assert _drawing_count(hidden) == _drawing_count(typst_default_pdf) - len(
        SECTION_TITLES
    )


def test_typst_port_header_align_moves_name_left(tmp_path, typst_default_pdf):
    left_aligned = _render_typst(tmp_path, "left-header", header_align="left")
    assert (
        _line_containing(left_aligned, "Morgan Example")["x0"]
        < _line_containing(typst_default_pdf, "Morgan Example")["x0"] - 20
    )


def test_typst_port_justify_expands_summary_line(tmp_path, typst_default_pdf):
    justified = _render_typst(tmp_path, "justified", justify=True)
    assert (
        _line_containing(justified, "Data engineer with six years")["x1"]
        > _line_containing(typst_default_pdf, "Data engineer with six years")["x1"]
        + 5
    )


def test_typst_port_date_format_preformats_server_side():
    source = (USER_DIR / "xcharter_serif.typ").read_text()
    verbatim = json.loads(pdf_render.build_typst_sys_inputs(source, EXAMPLE)["resume"])
    shortened = json.loads(
        pdf_render.build_typst_sys_inputs(
            source,
            EXAMPLE,
            {"date_format": "short_month"},
        )["resume"]
    )
    assert verbatim["experience"][0]["start_date"] == "March 2022"
    assert shortened["experience"][0]["start_date"] == "Mar 2022"
    assert EXAMPLE["experience"][0]["start_date"] == "March 2022"


def test_typst_port_education_order_swaps_heading_rows(tmp_path):
    degree_first = _render_typst(
        tmp_path,
        "degree-first",
        education_order="degree_first",
    )
    institution_first = _render_typst(
        tmp_path,
        "institution-first",
        education_order="institution_first",
    )
    assert (
        _line_containing(degree_first, "Bachelor of Science")["top"]
        < _line_containing(degree_first, "Sample State Institute")["top"]
    )
    assert (
        _line_containing(institution_first, "Sample State Institute")["top"]
        < _line_containing(institution_first, "Bachelor of Science")["top"]
    )


def test_typst_port_skills_layout_adds_one_marker_per_group(
    tmp_path,
    typst_default_pdf,
):
    bulleted = _render_typst(tmp_path, "bulleted-skills", skills_layout="bulleted")
    expected = len(EXAMPLE["skills"]) + bool(EXAMPLE.get("certifications"))
    assert expected > 0
    added = _pdf_text(bulleted).count("\N{BULLET}") - _pdf_text(
        typst_default_pdf
    ).count("\N{BULLET}")
    assert added == expected


@pytest.mark.parametrize(
    ("knob", "value", "present", "absent"),
    [
        (
            "font_size",
            10,
            r"\documentclass[letterpaper,10pt]{article}",
            r"\documentclass[letterpaper,11pt]{article}",
        ),
        ("side_margins", 0.6, "lmargin=0.6in", "lmargin=0.4in"),
        ("top_bottom_margin", 0.7, "tmargin=0.7in", "tmargin=0.3in"),
        ("section_spacing", 14, r"\vspace{4pt}\scshape", r"\vspace{-4pt}\scshape"),
        (
            "entry_spacing",
            6,
            "leftmargin=0.0in, label={}, topsep=6pt, parsep=3pt, itemsep=9pt]",
            "leftmargin=0.0in, label={}, topsep=6pt, parsep=3pt, itemsep=3pt]",
        ),
        (
            "line_spacing",
            1.2,
            r"\linespread{1.2}",
            r"\linespread{1.0}",
        ),
        (
            "bullet_icon",
            "dash",
            r"\renewcommand\labelitemi{--}",
            r"\renewcommand\labelitemi{$\vcenter",
        ),
        ("hide_divider", True, r"}{}{0em}{}[\vspace{-5pt}]", r"\titlerule"),
        ("header_align", "left", r"\begin{flushleft}", r"\begin{center}"),
        ("header_align", "right", r"\begin{flushright}", r"\begin{center}"),
        (
            "justify",
            True,
            "\\raggedbottom\n\\setlength",
            "\\raggedbottom\n\\raggedright\n\\setlength",
        ),
        ("date_format", "short_month", "Mar 2022", "March 2022"),
    ],
)
def test_bundled_latex_knob_changes_rendered_tex(knob, value, present, absent):
    tex = _render(**{knob: value})
    assert present in tex
    assert absent not in tex


def test_bundled_latex_education_order_changes_structure():
    institution_first = _render(education_order="institution_first")
    degree_first = _render(education_order="degree_first")
    institution_heading = (
        "\\resumeSubheading\n"
        "      {Sample State Institute of Technology, Sampleton, IL}"
    )
    degree_heading = "\\resumeSubheading\n      {Bachelor of Science}"
    assert institution_heading in institution_first
    assert degree_heading not in institution_first
    assert degree_heading in degree_first
    assert institution_heading not in degree_first


def test_bundled_latex_skills_layout_changes_structure():
    bulleted = _render(skills_layout="bulleted")
    inline = _render(skills_layout="inline")
    bulleted_list = (
        r"\begin{itemize}[leftmargin=0.15in, topsep=6pt, parsep=3pt, itemsep=3pt]"
    )
    inline_list = (
        r"\begin{itemize}[leftmargin=0.15in, label={}, topsep=6pt, parsep=3pt, "
        r"itemsep=3pt]"
    )
    assert bulleted_list in bulleted
    assert inline_list not in bulleted
    assert inline_list in inline
    assert bulleted_list not in inline


def test_typst_port_renders_entry_and_bullet_extra_sections(tmp_path):
    source = (USER_DIR / "xcharter_serif.typ").read_text()
    resume = {
        "contact": {"name": "Extras Example", "email": "extras@example.com"},
        "extra_sections": [
            {
                "key": "publications",
                "title": "Selected Publications",
                "type": "entries",
                "entries": [
                    {
                        "heading": "Sentinel Publication Alpha",
                        "subheading": "Journal of Examples",
                        "location": "Remote",
                        "date": "June 2024",
                        "link": "https://example.com/paper",
                        "bullets": ["Sentinel entry bullet detail."],
                    }
                ],
            },
            {
                "key": "awards",
                "title": "Selected Awards",
                "type": "bullets",
                "bullets": ["Sentinel award bullet detail."],
            },
        ],
    }
    sys_inputs = pdf_render.build_typst_sys_inputs(
        source,
        resume,
        {"date_format": "short_month"},
        enforce_extras_support=True,
    )
    pdf = pdf_render.compile_typst_pdf(
        source,
        tmp_path,
        stem="typst-extras",
        sys_inputs=sys_inputs,
    )
    text = _pdf_text(pdf)
    assert "Selected Publications" in text
    assert "Sentinel Publication Alpha" in text
    assert "Jun 2024" in text
    assert "https://example.com/paper" in text
    assert "Sentinel entry bullet detail." in text
    assert "Selected Awards" in text
    assert "Sentinel award bullet detail." in text


def test_bundled_latex_renders_entry_and_bullet_extra_sections():
    source = (USER_DIR / "xcharter_serif.tex.j2").read_text()
    resume = {
        "contact": {"name": "Extras Example", "email": "extras@example.com"},
        "extra_sections": [
            {
                "key": "publications",
                "title": "Selected Publications",
                "type": "entries",
                "entries": [
                    {
                        "heading": "Sentinel Publication Alpha",
                        "subheading": "Journal of Examples",
                        "location": "Remote",
                        "date": "June 2024",
                        "link": "https://example.com/~author/paper%20one",
                        "bullets": ["Sentinel entry bullet detail."],
                    }
                ],
            },
            {
                "key": "awards",
                "title": "Selected Awards",
                "type": "bullets",
                "bullets": ["Sentinel award bullet detail."],
            },
        ],
    }
    tex = render_tex_from_source(
        source,
        resume,
        formatting={"date_format": "short_month"},
        enforce_extras_support=True,
    )
    assert r"\section{Selected Publications}" in tex
    assert "Sentinel Publication Alpha" in tex
    assert "Jun 2024" in tex
    assert r"\href{https://example.com/~author/paper\%20one}" in tex
    assert r"\section{Selected Awards}" in tex
    assert "Sentinel award bullet detail." in tex
