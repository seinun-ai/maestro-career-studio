import copy
import re
import shutil
import zlib
from datetime import date
from pathlib import Path

import pytest

from app.services import pdf_render, template_registry
from app.services.pdf_render import render_cover_letter_tex
from app.services.template_validation import SAMPLE_RESUME

TILDE_CONTACT = {
    "name": "Jane Doe",
    "email": "jane@example.com",
    "location": "Austin, TX",
    "linkedin": "linkedin.com/in/~jane",
    "github": "github.com/jane_dev",
}

TILDE_PROJECT_LINK = "https://example.com/~jane/proj_1"
TILDE_ENTRY_LINK = "https://example.com/~jane/sentinel_paper"

# Anchored on the package, never on the CWD.
USER_TEMPLATE_DIR = pdf_render.TEMPLATE_DIR / "user"

# resume.tex.j2 plus every bundled user template. Globbed, so a template added
# later is covered by the \href audit below without touching this file.
BUNDLED_LATEX_TEMPLATES = [
    pdf_render.TEMPLATE_DIR / pdf_render.RESUME_TEMPLATE,
    *sorted(USER_TEMPLATE_DIR.glob("*.tex.j2")),
]

# The audit runs over every LaTeX source we ship, which is NOT only the files
# under app/templates/: STARTER_SOURCE is the canonical starter every
# from-scratch draft is seeded with, and it renders four \href of its own.
AUDIT_SOURCES = [
    *((path.name, path.read_text(encoding="utf-8")) for path in BUNDLED_LATEX_TEMPLATES),
    ("STARTER_SOURCE", template_registry.STARTER_SOURCE),
]

# The URL argument of \href{url}{text}. Our fixtures put no braces in a URL,
# so "up to the first closing brace" captures the whole target.
HREF_ARG_RE = re.compile(r"\\href\{([^}]*)\}")

# A link annotation's target in a PDF: /URI (https://…).
PDF_URI_RE = re.compile(rb"/URI\s*\((.*?)\)")
PDF_STREAM_RE = re.compile(rb"stream\r?\n(.*?)endstream", re.S)


def _tilde_resume() -> dict:
    """SAMPLE_RESUME with a tilde and an underscore in all THREE kinds of URL a
    template can emit: the contact links, the first project's link, and the
    first extra-section entry's link.

    Every kind has to carry both characters or the audit goes vacuous for the
    sites that render it — SAMPLE_RESUME's own contact/project/entry links are
    all plain, so a template reverted to ``latex_escape`` on an unseeded site
    would still render clean URLs and pass. ``website`` is added on top of
    TILDE_CONTACT for the same reason: two templates render a website \\href
    behind an ``((* if contact.website *))`` guard.
    """
    data = copy.deepcopy(SAMPLE_RESUME)
    data["contact"] = {**TILDE_CONTACT, "website": "example.com/~jane_site"}
    data["projects"][0]["link"] = TILDE_PROJECT_LINK
    data["extra_sections"][0]["entries"][0]["link"] = TILDE_ENTRY_LINK
    return data


def _tilde_urls_in(tex: str) -> set[str]:
    """The rendered \\href targets that carry a tilde or an underscore — i.e.
    exactly the ones this fix is about."""
    return {
        url
        for url in HREF_ARG_RE.findall(tex)
        if "~" in url or "_" in url
    }


def _pdf_uris(pdf: Path) -> set[str]:
    """Every /URI target in a PDF's link annotations. pdflatex may park the
    annotation dictionaries in a FlateDecode object stream, so scan the raw
    bytes AND every stream we can inflate."""
    raw = pdf.read_bytes()
    chunks = [raw]
    for match in PDF_STREAM_RE.findall(raw):
        try:
            chunks.append(zlib.decompress(match))
        except zlib.error:
            pass  # not deflate (or not a whole stream) — the raw scan covers it
    return {
        uri.decode("latin-1")
        for chunk in chunks
        for uri in PDF_URI_RE.findall(chunk)
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


@pytest.mark.parametrize(
    "label, source", AUDIT_SOURCES, ids=[label for label, _ in AUDIT_SOURCES]
)
def test_shipped_latex_href_targets_never_carry_body_escaping(label, source):
    """No LaTeX source we ship may run a \\href URL argument through
    latex_escape: it rewrites the link target (``~`` -> ``\\textasciitilde{}``).
    Display text is typeset and keeps body escaping, so only the captured URL
    argument is checked."""
    tex = pdf_render.render_tex_from_source(source, _tilde_resume())
    urls = HREF_ARG_RE.findall(tex)
    assert urls, (
        f"{label} rendered no \\href at all — if that is intentional, exempt it "
        f"from AUDIT_SOURCES; otherwise the fixture stopped reaching its links."
    )
    # Non-vacuity: with all three link kinds seeded, every shipped source emits
    # at least one tilde-bearing target, so a source whose links stopped
    # rendering fails here instead of passing an empty audit.
    assert any("~" in url for url in urls), (
        f"{label} rendered {len(urls)} \\href but none carrying a tilde, so this "
        f"audit proves nothing about it: add a tilde-bearing URL to "
        f"_tilde_resume for the field it renders, or exempt this template. "
        f"Got: {urls}"
    )
    for url in urls:
        assert r"\textasciitilde" not in url, (label, url)
        assert r"\_" not in url, (label, url)


def test_harshibar_project_link_target_survives_a_tilde_and_underscore():
    """harshibar is the only bundled template whose sole \\href is the project
    link, and it renders the project NAME as display text — so this asserts the
    changed line directly and cannot be satisfied by any other \\href."""
    source = (USER_TEMPLATE_DIR / "harshibar.tex.j2").read_text(encoding="utf-8")
    tex = pdf_render.render_tex_from_source(source, _tilde_resume())
    assert "\\href{" + TILDE_PROJECT_LINK + "}" in tex


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex not installed")
@pytest.mark.parametrize(
    "template_path", BUNDLED_LATEX_TEMPLATES, ids=lambda p: p.name
)
def test_bundled_latex_tilde_urls_reach_the_pdf_intact(template_path, tmp_path):
    """The audit above is a string check on the .tex; this compiles and reads
    the link annotations back out, proving the raw ``~ _`` the fix leaves in a
    \\href target survive pdflatex as a working link target rather than merely
    compiling. Expected targets are derived from what THIS template rendered,
    so each one is held to its own links (harshibar has only a project link,
    carlito_dense has no entry link, and so on).

    test_user_templates.py only ever compiles xcharter_serif, so without this
    carlito_dense and harshibar have no compile coverage at all.
    """
    source = template_path.read_text(encoding="utf-8")
    tex = pdf_render.render_tex_from_source(source, _tilde_resume())
    expected = _tilde_urls_in(tex)
    assert expected, f"{template_path.name} rendered no tilde/underscore URL"

    pdf = pdf_render.compile_pdf(
        tex, tmp_path, stem=template_path.name.split(".")[0]
    )
    assert pdf.exists()

    uris = _pdf_uris(pdf)
    assert uris, f"{template_path.name}: no /URI annotations found in the PDF"
    missing = expected - uris
    assert not missing, (
        f"{template_path.name}: these \\href targets did not reach the PDF "
        f"intact: {sorted(missing)}. Found: {sorted(uris)}"
    )


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex not installed")
def test_cover_letter_with_tilde_url_compiles(tmp_path):
    tex = render_cover_letter_tex(
        contact=TILDE_CONTACT, body="Hi", today=date(2026, 5, 1)
    )
    pdf = pdf_render.compile_cover_letter_pdf(tex, tmp_path)
    assert pdf.exists()
    uris = _pdf_uris(pdf)
    assert "https://linkedin.com/in/~jane" in uris, uris
    assert "https://github.com/jane_dev" in uris, uris
