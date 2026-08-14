"""The `section_order` formatting knob, across every bundled template.

Four properties matter and each is pinned per template:

1. **Absent = native.** No stored order reproduces the template's own order.
   This is the regression baseline for the macro refactor.
2. **Reorder works.** A full list emits the sections in that order.
3. **A partial list appends the remainder.** This is the property that makes a
   stale stored list safe: it can reorder, never drop.
4. **Render tolerates a token it does not know**, because stored data outlives
   the code that wrote it. Rejection belongs at the write gate.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.schemas.formatting import (
    SECTION_ORDER_TOKENS,
    ResumeFormatting,
    merge_formatting,
    resolve_section_order,
    validate_formatting,
)
from app.services.pdf_render import render_tex_from_source

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = BACKEND_DIR / "app" / "templates"
EXAMPLE = json.loads(
    (BACKEND_DIR.parent / "base_resumes" / "example.json").read_text(encoding="utf-8")
)

# Every bundled LaTeX template and the order its body emits when nothing is
# stored. Carlito has no extras block and Harshibar renders Certifications
# standalone, so the native lists genuinely differ -- which is the point: the
# knob has to be a per-template contract, not one global list.
LATEX_TEMPLATES = {
    "resume.tex.j2": [
        "summary", "experience", "projects", "extra_sections", "skills", "education",
    ],
    "user/xcharter_serif.tex.j2": [
        "summary", "experience", "projects", "extra_sections", "skills", "education",
    ],
    "user/carlito_dense.tex.j2": [
        "summary", "experience", "projects", "skills", "education",
    ],
    "user/harshibar.tex.j2": [
        "summary", "experience", "projects", "education", "certifications", "skills",
    ],
}
TYPST_TEMPLATES = {
    "typst_classic.typ": [
        "summary", "experience", "projects", "extra_sections", "skills", "education",
    ],
    "user/xcharter_serif.typ": [
        "summary", "experience", "projects", "extra_sections", "skills", "education",
    ],
}

# Heading text each token produces, casefolded. Several spellings per token on
# purpose: Harshibar sets its headings in caps and calls the section "SKILLS"
# where the others say "Technical Skills". `extra_sections` renders the user's
# own title, so it is keyed to the fixture resume below.
HEADINGS = {
    "summary": {"summary"},
    "experience": {"experience"},
    "projects": {"projects"},
    "extra_sections": {"sentinel publications"},
    "skills": {"technical skills", "skills"},
    "education": {"education"},
    "certifications": {"certifications"},
}

RESUME = {
    **EXAMPLE,
    "extra_sections": [
        {
            "key": "sentinel-publications",
            "title": "Sentinel Publications",
            "type": "bullets",
            "enabled": True,
            "bullets": ["Sentinel publication alpha", "Sentinel publication beta"],
        }
    ],
}


def _source(name: str) -> str:
    return (TEMPLATE_DIR / name).read_text(encoding="utf-8")


def _rendered_headings(tex: str) -> list[str]:
    """Section titles in the order the rendered LaTeX emits them."""
    return re.findall(r"\\section\{([^}]*)\}", tex)


def _matches(rendered: str, token: str) -> bool:
    return rendered.strip().casefold() in HEADINGS[token]


# --------------------------------------------------------------------------
# The ordering rule itself
# --------------------------------------------------------------------------

NATIVE = ["summary", "experience", "projects", "skills", "education"]


@pytest.mark.parametrize("requested", [None, []])
def test_no_request_is_the_template_order(requested):
    assert resolve_section_order(requested, NATIVE) == NATIVE


def test_full_list_is_honored_verbatim():
    wanted = ["education", "skills", "projects", "experience", "summary"]
    assert resolve_section_order(wanted, NATIVE) == wanted


def test_partial_list_appends_the_remaining_native_sections():
    """The load-bearing rule. A list naming two sections must still render all
    five, or a stale stored order would silently delete a resume's content."""
    assert resolve_section_order(["education", "summary"], NATIVE) == [
        "education", "summary", "experience", "projects", "skills",
    ]


def test_tokens_the_template_does_not_render_fall_out():
    """`certifications` is a section in one bundled template and folded into
    Skills in the others; the caller does not have to know which."""
    assert resolve_section_order(
        ["certifications", "education"], NATIVE
    ) == ["education", "summary", "experience", "projects", "skills"]


def test_a_repeated_token_does_not_render_its_section_twice():
    """The schema sanitiser de-duplicates before this is ever called, so this
    pins the helper's OWN contract rather than the shipped path's: "every native
    section exactly once, whatever you hand me"."""
    assert resolve_section_order(["skills", "skills", "summary"], NATIVE) == [
        "skills", "summary", "experience", "projects", "education",
    ]


def test_every_native_section_survives_any_request():
    """Property check over the whole token space: no request can shrink the
    output, and no request can duplicate a section."""
    for k in range(len(SECTION_ORDER_TOKENS) + 1):
        requested = list(SECTION_ORDER_TOKENS[:k])
        for candidate in (requested, requested + requested, list(reversed(requested))):
            got = resolve_section_order(candidate, NATIVE)
            assert sorted(got) == sorted(NATIVE), candidate
            assert len(got) == len(set(got)), candidate


# --------------------------------------------------------------------------
# Schema: tolerant at render, strict at the write gate
# --------------------------------------------------------------------------

def test_default_is_none_so_absent_means_native():
    assert ResumeFormatting().section_order is None


def test_merge_drops_unknown_and_duplicate_tokens_instead_of_raising():
    """Render must survive stored data written by another version."""
    fmt = merge_formatting(
        {"section_order": ["summary", "bogus", "summary", "education", 7]}
    )
    assert fmt.section_order == ["summary", "education"]


def test_merge_rejects_a_non_list_by_falling_back_to_native():
    assert merge_formatting({"section_order": "summary"}).section_order is None


def test_merge_layers_let_an_application_override_a_base_order():
    """The knob rides the existing 4-layer merge; nothing about it is special."""
    fmt = merge_formatting(
        {"section_order": ["summary", "experience"]},
        {"section_order": ["education", "skills"]},
    )
    assert fmt.section_order == ["education", "skills"]


@pytest.mark.parametrize(
    "value",
    [
        ["summary", "bogus"],
        ["summary", "summary"],
        ["summary", 7],
        "summary",
    ],
)
def test_write_gate_rejects_what_render_would_have_silently_dropped(value):
    with pytest.raises(ValueError, match="section_order"):
        validate_formatting({"section_order": value})


def test_write_gate_accepts_a_valid_partial_order_and_an_explicit_clear():
    assert validate_formatting({"section_order": ["education", "summary"]}) == {
        "section_order": ["education", "summary"]
    }
    assert validate_formatting({"section_order": None}) == {"section_order": None}


def test_write_gate_names_the_offending_token_and_the_valid_ones():
    """A rejection the user cannot act on is barely better than silence."""
    with pytest.raises(ValueError) as excinfo:
        validate_formatting({"section_order": ["summary", "skils"]})
    message = str(excinfo.value)
    assert "skils" in message
    for token in SECTION_ORDER_TOKENS:
        assert token in message


def test_template_default_formatting_endpoint_rejects_an_unknown_section(db_session):
    """The template-level write gate. Same 400 contract as every other invalid
    formatting override -- the knob does not get its own status code."""
    from app.db import get_db
    from app.main import app
    from fastapi.testclient import TestClient

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    try:
        c = TestClient(app)
        c.post("/api/templates", json={"id": "so", "display_name": "SO", "source": "X"})
        bad = c.put(
            "/api/templates/so/default-formatting",
            json={"formatting": {"section_order": ["summary", "skils"]}},
        )
        assert bad.status_code == 400
        assert "skils" in bad.json()["detail"]

        dupe = c.put(
            "/api/templates/so/default-formatting",
            json={"formatting": {"section_order": ["summary", "summary"]}},
        )
        assert dupe.status_code == 400

        good = c.put(
            "/api/templates/so/default-formatting",
            json={"formatting": {"section_order": ["education", "summary"]}},
        )
        assert good.status_code == 200
        assert good.json()["default_formatting"] == {
            "section_order": ["education", "summary"]
        }
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------
# Per-template rendering (LaTeX: compare the rendered source, no compile)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(LATEX_TEMPLATES))
def test_latex_absent_knob_is_byte_identical_to_the_explicit_native_order(name):
    """The regression baseline for the macro refactor: an untouched resume must
    render exactly what it rendered before the dispatch loop existed."""
    source = _source(name)
    absent = render_tex_from_source(source, RESUME, formatting=None)
    explicit = render_tex_from_source(
        source, RESUME, formatting={"section_order": LATEX_TEMPLATES[name]}
    )
    assert absent == explicit


@pytest.mark.parametrize("name", sorted(LATEX_TEMPLATES))
def test_latex_native_order_headings(name):
    native = LATEX_TEMPLATES[name]
    headings = _rendered_headings(render_tex_from_source(source := _source(name), RESUME))
    assert source  # rendered from the bundled file, not a fixture
    assert len(headings) == len(native)
    for got, token in zip(headings, native):
        assert _matches(got, token), (name, got, token)


@pytest.mark.parametrize("name", sorted(LATEX_TEMPLATES))
def test_latex_full_reorder_emits_the_requested_order(name):
    native = LATEX_TEMPLATES[name]
    wanted = list(reversed(native))
    headings = _rendered_headings(
        render_tex_from_source(_source(name), RESUME, formatting={"section_order": wanted})
    )
    assert len(headings) == len(wanted)
    for got, token in zip(headings, wanted):
        assert _matches(got, token), (name, got, token)


@pytest.mark.parametrize("name", sorted(LATEX_TEMPLATES))
def test_latex_partial_order_appends_the_rest_and_keeps_every_section(name):
    native = LATEX_TEMPLATES[name]
    partial = [native[-1], native[0]]
    expected = resolve_section_order(partial, native)
    headings = _rendered_headings(
        render_tex_from_source(_source(name), RESUME, formatting={"section_order": partial})
    )
    assert len(headings) == len(native), (name, headings)
    for got, token in zip(headings, expected):
        assert _matches(got, token), (name, got, token)


@pytest.mark.parametrize("name", sorted(LATEX_TEMPLATES))
def test_latex_render_tolerates_a_token_it_cannot_place(name):
    """Stored orders outlive releases. An unknown name must be ignored and the
    document must stay whole, not raise and not lose a section."""
    native = LATEX_TEMPLATES[name]
    tolerant = render_tex_from_source(
        _source(name),
        RESUME,
        formatting={"section_order": ["from_a_later_release", native[-1]]},
    )
    headings = _rendered_headings(tolerant)
    assert len(headings) == len(native)
    assert _matches(headings[0], native[-1])


# --------------------------------------------------------------------------
# Per-template rendering (Typst: needs a real compile)
# --------------------------------------------------------------------------

pdfplumber = pytest.importorskip("pdfplumber")
pytest.importorskip("typst")


def _typst_text(tmp_path, name, stem, formatting):
    from scripts.template_parity import render_template_pdf

    pdf = render_template_pdf(
        _source(name), "typst", RESUME, formatting, tmp_path, stem
    )
    with pdfplumber.open(pdf) as doc:
        pages = [page.extract_text() or "" for page in doc.pages]
    return "\n".join(pages)


def _heading_order(text: str, native: list[str]) -> list[str]:
    """Tokens ordered by where their heading appears in the extracted text."""
    found = []
    for token in native:
        lowered = text.casefold()
        position = min(
            (lowered.find(option) for option in HEADINGS[token] if option in lowered),
            default=-1,
        )
        if position >= 0:
            found.append((position, token))
    return [token for _, token in sorted(found)]


@pytest.mark.parametrize("name", sorted(TYPST_TEMPLATES))
def test_typst_absent_knob_matches_the_explicit_native_order(tmp_path, name):
    native = TYPST_TEMPLATES[name]
    absent = _typst_text(tmp_path, name, "absent", None)
    explicit = _typst_text(tmp_path, name, "explicit", {"section_order": native})
    assert absent == explicit
    assert _heading_order(absent, native) == native


@pytest.mark.parametrize("name", sorted(TYPST_TEMPLATES))
def test_typst_full_reorder_and_partial_append(tmp_path, name):
    native = TYPST_TEMPLATES[name]
    wanted = list(reversed(native))
    reordered = _typst_text(tmp_path, name, "reordered", {"section_order": wanted})
    assert _heading_order(reordered, native) == wanted
    # Reordering is presentation only: the same words come out, in a new order.
    assert sorted(reordered.split()) == sorted(
        _typst_text(tmp_path, name, "native", None).split()
    )

    partial = [native[-1], native[0]]
    appended = _typst_text(tmp_path, name, "partial", {"section_order": partial})
    assert _heading_order(appended, native) == resolve_section_order(partial, native)


@pytest.mark.parametrize("name", sorted(TYPST_TEMPLATES))
def test_typst_render_tolerates_a_token_it_cannot_place(tmp_path, name):
    native = TYPST_TEMPLATES[name]
    text = _typst_text(
        tmp_path,
        name,
        "unknown",
        {"section_order": ["from_a_later_release", native[-1]]},
    )
    assert _heading_order(text, native) == resolve_section_order([native[-1]], native)
