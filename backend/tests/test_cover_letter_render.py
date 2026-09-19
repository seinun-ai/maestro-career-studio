import copy
import re
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

TILDE_PROJECT_LINK = "https://example.com/~jane/proj_1"

# Anchored on the package, never on the CWD.
USER_TEMPLATE_DIR = pdf_render.TEMPLATE_DIR / "user"

# resume.tex.j2 plus every bundled user template. Globbed, so a template added
# later is covered by the \href audit below without touching this file.
BUNDLED_LATEX_TEMPLATES = [
    pdf_render.TEMPLATE_DIR / pdf_render.RESUME_TEMPLATE,
    *sorted(USER_TEMPLATE_DIR.glob("*.tex.j2")),
]

# The URL argument of \href{url}{text}. Our fixtures put no braces in a URL,
# so "up to the first closing brace" captures the whole target.
HREF_ARG_RE = re.compile(r"\\href\{([^}]*)\}")


def _tilde_resume() -> dict:
    """SAMPLE_RESUME with a tilde/underscore in every URL a template can emit:
    the contact links and the first project's link. ``website`` is added on top
    of TILDE_CONTACT because two templates render a website \\href behind an
    ``((* if contact.website *))`` guard, and without it those lines would be
    silently skipped by the audit."""
    data = copy.deepcopy(SAMPLE_RESUME)
    data["contact"] = {**TILDE_CONTACT, "website": "example.com/~jane_site"}
    data["projects"][0]["link"] = TILDE_PROJECT_LINK
    return data


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
    "template_path", BUNDLED_LATEX_TEMPLATES, ids=lambda p: p.name
)
def test_bundled_latex_href_targets_never_carry_body_escaping(template_path):
    """No bundled template may run a \\href URL argument through latex_escape:
    it rewrites the link target (``~`` -> ``\\textasciitilde{}``). Display text
    is typeset and keeps body escaping, so only the captured URL is checked."""
    source = template_path.read_text(encoding="utf-8")
    tex = pdf_render.render_tex_from_source(source, _tilde_resume())
    urls = HREF_ARG_RE.findall(tex)
    assert urls, f"{template_path.name} rendered no \\href at all"
    # Non-vacuity: every bundled template emits at least one of the fixture's
    # tilde-bearing URLs, so a template that stopped rendering links fails here
    # instead of passing an empty audit.
    assert any("~" in url for url in urls), (
        f"{template_path.name} rendered no tilde-bearing URL: {urls}"
    )
    for url in urls:
        assert r"\textasciitilde" not in url, (template_path.name, url)
        assert r"\_" not in url, (template_path.name, url)


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
def test_bundled_latex_with_tilde_urls_compiles(template_path, tmp_path):
    """The escaping audit above is a string check; this proves the raw ``~ _``
    the fix leaves in a \\href target really compile. test_user_templates.py
    only ever compiles xcharter_serif, so without this carlito_dense and
    harshibar have no compile coverage at all."""
    source = template_path.read_text(encoding="utf-8")
    tex = pdf_render.render_tex_from_source(source, _tilde_resume())
    assert pdf_render.compile_pdf(tex, tmp_path, stem=template_path.stem).exists()


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex not installed")
def test_cover_letter_with_tilde_url_compiles(tmp_path):
    tex = render_cover_letter_tex(
        contact=TILDE_CONTACT, body="Hi", today=date(2026, 5, 1)
    )
    assert pdf_render.compile_cover_letter_pdf(tex, tmp_path).exists()
