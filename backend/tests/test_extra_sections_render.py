"""Stage C rendering + template-certification tests for custom (extra) sections.

Covers the default LaTeX template rendering both union variants, disabled
filtering, latex escaping of special characters, the render-time
template-incompatibility hard-fail (block, never silently omit), certification's
extra_sections_supported capability flag, and a cover-letter regression proving
the shared header partial is untouched.
"""
import shutil
from datetime import date

import pytest

from app.services import (
    pdf_render,
    template_registry as reg,
    template_validation as tv,
)
from app.services.pdf_render import (
    TemplateMissingExtraSectionsError,
    compile_cover_letter_pdf,
    compile_pdf,
    render_cover_letter_tex,
    render_document,
    render_tex_from_source,
    source_references_extras,
)


def _tex(*args, **kwargs) -> str:
    """render_document's latex source text — replaces the deleted render_tex."""
    return render_document(*args, **kwargs).source_text

pdflatex = pytest.mark.skipif(
    shutil.which("pdflatex") is None, reason="pdflatex not installed"
)

DEFAULT_SOURCE = (pdf_render.TEMPLATE_DIR / pdf_render.RESUME_TEMPLATE).read_text(
    encoding="utf-8"
)

CONTACT = {"name": "Sample Applicant", "email": "sample@example.com", "location": "SF, CA"}

# A minimal ready template whose source never references extra_sections — the
# canonical "incompatible" template that must hard-fail an extras-bearing resume.
NO_EXTRAS_SOURCE = (
    r"\documentclass{article}\begin{document}"
    r"((( resume.contact.name|latex_escape )))\end{document}"
)


def _entries_section(**over) -> dict:
    section = {
        "key": "publications",
        "title": "Publications",
        "type": "entries",
        "entries": [
            {
                "heading": "Deep Learning at Scale",
                "subheading": "NeurIPS",
                "location": "New Orleans, LA",
                "date": "2023",
                "link": "https://example.com/paper",
                "bullets": ["Cited over 100 times."],
            }
        ],
    }
    section.update(over)
    return section


def _bullets_section(**over) -> dict:
    section = {
        "key": "awards",
        "title": "Awards & Honors",
        "type": "bullets",
        "bullets": ["First place, Regional Hackathon, 2024"],
    }
    section.update(over)
    return section


def _resume(sections: list[dict]) -> dict:
    return {"contact": CONTACT, "summary": "Summary.", "extra_sections": sections}


def _ready_template(db_session, tid: str, source: str) -> None:
    reg.create_draft(db_session, id=tid, display_name=tid, source=source, origin="mcp")
    row = reg.get(db_session, tid)
    row.status = "ready"
    db_session.commit()


# --------------------------------------------------------------------------- #
# Default template renders both union variants
# --------------------------------------------------------------------------- #


def test_default_template_renders_entries_variant():
    tex = _tex(_resume([_entries_section()]))
    assert r"\section{Publications}" in tex
    assert "Deep Learning at Scale" in tex  # heading
    assert "NeurIPS" in tex  # subheading
    assert "New Orleans, LA" in tex  # location
    assert "2023" in tex  # date
    assert "Cited over 100 times." in tex  # bullet
    # link rendered via the escaped \href idiom (matches the shared header)
    assert r"\href{https://example.com/paper}" in tex


def test_default_template_renders_bullets_variant():
    tex = _tex(_resume([_bullets_section()]))
    assert r"\section{Awards \& Honors}" in tex  # title, & escaped
    assert "First place, Regional Hackathon, 2024" in tex
    assert r"\resumeItemListStart" in tex


def test_extras_rendered_at_anchor_after_projects_before_skills():
    resume = {
        "contact": CONTACT,
        "projects": [{"name": "Proj", "bullets": ["Did a thing."]}],
        "skills": [{"category": "Languages", "items": ["Python"]}],
        "extra_sections": [_bullets_section()],
    }
    tex = _tex(resume)
    pos_projects = tex.index(r"\section{Projects}")
    pos_extra = tex.index(r"\section{Awards \& Honors}")
    pos_skills = tex.index(r"\section{Technical Skills}")
    assert pos_projects < pos_extra < pos_skills


@pdflatex
def test_default_template_both_variants_compile_and_extract(tmp_path):
    pdfplumber = pytest.importorskip("pdfplumber")
    tex = _tex(_resume([_entries_section(), _bullets_section()]))
    pdf = compile_pdf(tex, tmp_path, stem="extras")
    with pdfplumber.open(pdf) as doc:
        text = " ".join((p.extract_text() or "") for p in doc.pages)
    norm = " ".join(text.split())
    for phrase in (
        "Deep Learning at Scale",
        "Cited over 100 times",
        "First place, Regional Hackathon",
    ):
        assert phrase in norm, f"{phrase!r} missing from extraction: {norm!r}"


# --------------------------------------------------------------------------- #
# Disabled filtering
# --------------------------------------------------------------------------- #


def test_disabled_section_omitted_from_render():
    tex = _tex(
        _resume([_entries_section(enabled=False), _bullets_section(key="shown", title="Shown")])
    )
    assert r"\section{Publications}" not in tex
    assert "Deep Learning at Scale" not in tex
    assert r"\section{Shown}" in tex


def test_disabled_entry_within_enabled_section_omitted():
    section = _entries_section()
    section["entries"].append({"heading": "Hidden Paper", "enabled": False})
    tex = _tex(_resume([section]))
    assert "Deep Learning at Scale" in tex
    assert "Hidden Paper" not in tex


def test_enabled_but_empty_section_renders_no_header():
    empty = {"key": "empty", "title": "Empty Section", "type": "entries", "entries": []}
    tex = _tex(_resume([empty]))
    # No lone header, and critically no empty itemize (a LaTeX compile error).
    assert r"\section{Empty Section}" not in tex


@pdflatex
def test_enabled_but_empty_section_still_compiles(tmp_path):
    empty_entries = {"key": "e1", "title": "E1", "type": "entries", "entries": []}
    empty_bullets = {"key": "e2", "title": "E2", "type": "bullets", "bullets": []}
    tex = _tex(_resume([empty_entries, empty_bullets, _bullets_section()]))
    compile_pdf(tex, tmp_path, stem="emptyextra")  # must not raise


# --------------------------------------------------------------------------- #
# Latex escaping of special characters in extras
# --------------------------------------------------------------------------- #


def test_latex_escaping_in_extra_section_fields():
    section = {
        "key": "pubs",
        "title": "R&D 100% $tuff",
        "type": "entries",
        "entries": [
            {
                "heading": "Cost_Model & Profit#1",
                "subheading": "50% ~gain^2",
                "location": "A_B",
                "date": "Q1",
                "link": "https://x.com/a_b?q=1&r=2",
                "bullets": ["Saved $5 on #hashtags & more_stuff"],
            }
        ],
    }
    tex = _tex(_resume([section]))
    assert r"\section{R\&D 100\% \$tuff}" in tex
    assert r"Cost\_Model \& Profit\#1" in tex
    assert r"50\% \textasciitilde{}gain\textasciicircum{}2" in tex
    assert r"Saved \$5 on \#hashtags \& more\_stuff" in tex
    # link text is escaped too (same idiom as _header.tex.j2's contact links)
    assert r"x.com/a\_b?q=1\&r=2" in tex
    # no raw unescaped metacharacters leaked into the section title
    assert "R&D" not in tex


def test_latex_escaping_in_bullets_section():
    section = {
        "key": "awards",
        "title": "Grants & Awards",
        "type": "bullets",
        "bullets": ["$10k grant (95% funded) for R&D_work"],
    }
    tex = _tex(_resume([section]))
    assert r"\section{Grants \& Awards}" in tex
    assert r"\$10k grant (95\% funded) for R\&D\_work" in tex


@pdflatex
def test_extras_with_special_chars_compile(tmp_path):
    section = {
        "key": "pubs",
        "title": "R&D 100% $tuff",
        "type": "entries",
        "entries": [
            {
                "heading": "Cost_Model & Profit#1",
                "subheading": "50% ~gain",
                "location": "A_B",
                "date": "Q1",
                "link": "https://x.com/a_b?q=1&r=2",
                "bullets": ["Saved $5 on #hashtags & more_stuff"],
            }
        ],
    }
    tex = _tex(_resume([section]))
    compile_pdf(tex, tmp_path, stem="special")  # must not raise


# --------------------------------------------------------------------------- #
# Render-time template incompatibility: hard-fail, never silent omission
# --------------------------------------------------------------------------- #


def test_source_references_extras_detection():
    assert source_references_extras("body ((* for s in resume.extra_sections *))") is True
    assert source_references_extras("no custom sections here") is False
    assert source_references_extras(DEFAULT_SOURCE) is True


def test_incompatible_template_hard_fails_for_extras_resume(db_session):
    _ready_template(db_session, "noextra", NO_EXTRAS_SOURCE)
    with pytest.raises(TemplateMissingExtraSectionsError) as exc:
        _tex(_resume([_bullets_section()]), template_id="noextra", session=db_session)
    msg = str(exc.value)
    assert "custom section" in msg.lower()
    assert "awards" in msg  # names the offending section key


def test_incompatible_template_ok_for_core_only_resume(db_session):
    # A template without extra-section support stays fully usable for a resume
    # that has no (renderable) custom sections.
    _ready_template(db_session, "noextra_core", NO_EXTRAS_SOURCE)
    out = _tex(
        {"contact": CONTACT, "summary": "S"}, template_id="noextra_core", session=db_session
    )
    assert "Sample Applicant" in out


def test_disabled_only_extras_do_not_trip_incompatibility_guard(db_session):
    # Extras that are all disabled/empty produce no visible output, so they must
    # not block an otherwise-compatible core-only render.
    _ready_template(db_session, "noextra_dis", NO_EXTRAS_SOURCE)
    out = _tex(
        _resume([_bullets_section(enabled=False), {"key": "e", "title": "E", "type": "entries", "entries": []}]),
        template_id="noextra_dis",
        session=db_session,
    )
    assert "Sample Applicant" in out


def test_default_template_never_trips_guard():
    # The bundled default supports extras, so an extras resume renders through it.
    tex = _tex(_resume([_entries_section(), _bullets_section()]), template_id=None)
    assert "Deep Learning at Scale" in tex


def test_primitive_render_is_permissive_by_default():
    # render_tex_from_source is the certification/measurement primitive: it must
    # NOT hard-fail on extras + a non-referencing source unless opted in.
    out = render_tex_from_source(
        "PLAIN ((( resume.contact.name|latex_escape )))", _resume([_bullets_section()])
    )
    assert "Sample Applicant" in out
    with pytest.raises(TemplateMissingExtraSectionsError):
        render_tex_from_source(
            "PLAIN ((( resume.contact.name|latex_escape )))",
            _resume([_bullets_section()]),
            enforce_extras_support=True,
        )


# --------------------------------------------------------------------------- #
# Certification: extra_sections_supported capability flag
# --------------------------------------------------------------------------- #


# These assert the capability logic directly on a compiled preview via
# build_parse_report — no DB commit, so they avoid the shared db_session
# fixture's pre-existing StaleDataError flake. validate_template simply stores
# the report build_parse_report returns (covered by test_template_validation.py::
# test_validate_template_stores_parse_report), so the DB-persistence half is
# already exercised there.

# A template that renders core sections but never references extra_sections: it
# would SILENTLY drop a real resume's custom sections.
CORE_ONLY_SOURCE = (
    "\\documentclass[letterpaper,11pt]{article}\n"
    "\\usepackage{XCharter}\n"
    "\\usepackage[T1]{fontenc}\n"
    "\\begin{document}\n"
    "((( resume.contact.name|latex_escape )))\n\n"
    "((( resume.contact.email|latex_escape )))\n\n"
    "((* for e in resume.experience *))"
    "((( e.company|latex_escape ))): ((( e.role|latex_escape )))\n\n"
    "((* endfor *))"
    "((* for edu in resume.education *))"
    "((( edu.institution|latex_escape ))): ((( edu.degree|latex_escape )))\n\n"
    "((* endfor *))"
    "\\end{document}\n"
)


@pdflatex
def test_certification_marks_default_template_extras_supported(tmp_path):
    pytest.importorskip("pdfplumber")
    keep = tmp_path / "default_preview.pdf"
    # compile_against_sample renders the sentinel-bearing SAMPLE_RESUME through
    # the source (permissively — no hard-fail), so capability is measured, not
    # enforced.
    err = tv.compile_against_sample(DEFAULT_SOURCE, keep_pdf_at=keep)
    assert err is None
    report = tv.build_parse_report(keep)
    assert report is not None
    assert report["extra_sections_supported"] is True
    assert report["extra_sections_missing"] == []
    # Capability is independent of core parse fidelity, which still certifies.
    assert report["missing"] == []


@pdflatex
def test_certification_detects_silent_omission(tmp_path):
    # A core-only template must be flagged extra_sections_supported=False (it
    # would silently drop custom sections) yet can still certify parse fidelity
    # for core-only resumes.
    pytest.importorskip("pdfplumber")
    keep = tmp_path / "core_preview.pdf"
    err = tv.compile_against_sample(CORE_ONLY_SOURCE, keep_pdf_at=keep)
    assert err is None
    report = tv.build_parse_report(keep)
    assert report is not None
    assert report["extra_sections_supported"] is False
    assert set(report["extra_sections_missing"]) == set(tv.EXTRA_SECTION_PROBES)
    # Core-only template still certifies parse fidelity (extras are separate).
    assert report["missing"] == []


def test_sample_resume_extras_are_valid_and_present():
    from app.schemas.resume import ResumeData

    data = ResumeData.model_validate(tv.SAMPLE_RESUME)
    keys = [s.key for s in data.extra_sections]
    assert keys == ["publications", "awards"]
    types = {s.key: s.type for s in data.extra_sections}
    assert types == {"publications": "entries", "awards": "bullets"}


# --------------------------------------------------------------------------- #
# Cover-letter regression: shared _header.tex.j2 untouched
# --------------------------------------------------------------------------- #


def test_cover_letter_renders_without_resume_or_extras():
    tex = render_cover_letter_tex(
        contact={"name": "Sample Applicant", "email": "sample@example.com", "location": "SF, CA"},
        body="First paragraph.\n\nSecond paragraph.",
        today=date(2026, 7, 16),
    )
    assert "Sample Applicant" in tex
    assert "First paragraph." in tex
    assert "Second paragraph." in tex
    # The cover letter has no resume object, so no custom-section machinery.
    assert "extra_sections" not in tex
    assert r"\section{Publications}" not in tex


@pdflatex
def test_cover_letter_still_compiles(tmp_path):
    tex = render_cover_letter_tex(
        contact={"name": "Sample Applicant", "email": "sample@example.com", "location": "SF, CA"},
        body="First paragraph with R&D and 100% effort.\n\nSecond paragraph.",
        today=date(2026, 7, 16),
    )
    compile_cover_letter_pdf(tex, tmp_path)  # must not raise


# --------------------------------------------------------------------------- #
# F4: capability sniff — ignore comment-only mentions, follow included partials
# --------------------------------------------------------------------------- #


def test_source_references_extras_ignores_comment_only_mention():
    # extra_sections named ONLY inside a LaTeX % comment does not render them —
    # must NOT read as supporting (old false positive -> silent drop).
    src = (
        r"\documentclass{article}\begin{document}"
        "\n% could loop resume.extra_sections here but does not\n"
        r"((( resume.contact.name|latex_escape )))\end{document}"
    )
    assert source_references_extras(src) is False


def test_comment_only_extras_template_hard_fails_for_extras_resume(db_session):
    src = (
        r"\documentclass{article}\begin{document}"
        "\n% resume.extra_sections mentioned only in this comment\n"
        r"((( resume.contact.name|latex_escape )))\end{document}"
    )
    _ready_template(db_session, "commentonly", src)
    with pytest.raises(TemplateMissingExtraSectionsError):
        _tex(_resume([_bullets_section()]), template_id="commentonly", session=db_session)


@pytest.fixture
def extras_partial():
    # A bundled partial that renders the extras block. _resolve_partial only
    # resolves basenames physically inside TEMPLATE_DIR, so it must live there.
    name = "_extras_test_partial.tex.j2"
    path = pdf_render.TEMPLATE_DIR / name
    path.write_text(
        "((* for section in resume.extra_sections *))"
        "((* if section.type == 'bullets' and section.bullets *))"
        "\\section{((( section.title|latex_escape )))}"
        "((* endif *))((* endfor *))",
        encoding="utf-8",
    )
    try:
        yield name
    finally:
        path.unlink(missing_ok=True)


def test_source_references_extras_follows_included_partial(extras_partial):
    # The top-level source never names extra_sections inline; it renders them via
    # an included partial — that must count as supporting (old false negative ->
    # hard-fail).
    src = (
        r"\documentclass{article}\begin{document}"
        f"((* include '{extras_partial}' *))"
        r"((( resume.contact.name|latex_escape )))\end{document}"
    )
    assert "extra_sections" not in src  # not inline
    assert source_references_extras(src) is True


def test_partial_rendered_extras_do_not_hard_fail(db_session, extras_partial):
    src = (
        r"\documentclass{article}\begin{document}"
        f"((* include '{extras_partial}' *))"
        r"((( resume.contact.name|latex_escape )))\end{document}"
    )
    _ready_template(db_session, "partialextras", src)
    out = _tex(
        _resume([_bullets_section()]), template_id="partialextras", session=db_session
    )
    # No hard-fail, and the partial's extra-section output is present (escaped).
    assert r"\section{Awards \& Honors}" in out


# --------------------------------------------------------------------------- #
# F5: href URL argument uses latex_escape_url (raw ~), display keeps latex_escape
# --------------------------------------------------------------------------- #


def test_entry_link_url_arg_keeps_raw_tilde():
    section = {
        "key": "pubs",
        "title": "Pubs",
        "type": "entries",
        "entries": [{"heading": "Paper", "link": "https://ex.com/~user/a%20b"}],
    }
    tex = _tex(_resume([section]))
    # URL argument: raw ~, escaped % (latex_escape_url).
    assert r"\href{https://ex.com/~user/a\%20b}" in tex
    # Display text: latex_escape still maps ~ -> \textasciitilde{}.
    assert r"\underline{https://ex.com/\textasciitilde{}user/a\%20b}" in tex


@pdflatex
def test_entry_link_with_tilde_and_percent_compiles(tmp_path):
    section = {
        "key": "pubs",
        "title": "Pubs",
        "type": "entries",
        "entries": [{"heading": "Paper", "link": "https://ex.com/~user/a%20b?x=1&y=2"}],
    }
    tex = _tex(_resume([section]))
    assert "~user" in tex  # raw tilde survives into the .tex URL arg
    compile_pdf(tex, tmp_path, stem="urllink")  # must not raise
