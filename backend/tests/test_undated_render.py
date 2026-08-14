"""Undated experience and degree-less education render cleanly in BOTH engines.

`ExperienceEntry.start_date` and `EducationEntry.degree` are optional: a resume
that states no date for a role, or no degree title for a term of study, is a
legal representation and nothing may invent one for it. That puts the whole
burden on the renderers — no literal "None", no dangling en dash where a date
range lost one end, and no empty leading line where the degree used to be.

Both bundled sources are exercised through the same parity harness the corpus
gate uses, so a guard added to one engine and forgotten in the other fails here.
"""
import json

import pytest

from app.schemas.resume import ResumeData
from app.services import pdf_render
from scripts.template_parity import render_template_pdf

pytest.importorskip("typst")
pytest.importorskip("pdfplumber")

BUNDLED_SOURCES = {
    "classic_latex": ("latex", pdf_render.RESUME_TEMPLATE),
    "classic_typst": ("typst", "typst_classic.typ"),
    "xcharter_serif": ("latex", "user/xcharter_serif.tex.j2"),
    "xcharter_serif_typst": ("typst", "user/xcharter_serif.typ"),
    "carlito_dense": ("latex", "user/carlito_dense.tex.j2"),
    "harshibar": ("latex", "user/harshibar.tex.j2"),
}

# The legacy undated and education regression cases cover the original bundled
# LaTex/Typst pair. The ongoing-date case below runs the full bundled matrix.
ENGINE_SOURCES = {
    key: BUNDLED_SOURCES[key] for key in ("classic_latex", "classic_typst")
}


def _source(engine: str) -> str:
    _, filename = BUNDLED_SOURCES[engine]
    return (pdf_render.TEMPLATE_DIR / filename).read_text(encoding="utf-8")


def _resume(**overrides) -> dict:
    """A validated resume whose one role is undated and whose one education
    entry has no degree. Validated (not hand-built) so every optional key is
    present as null — the Typst path reads fields positionally off the JSON."""
    data = {
        # phone/location are present only to keep the shared LaTeX header's
        # second line non-empty — an unrelated pre-existing crash, not the
        # subject of these tests.
        "contact": {
            "name": "Riley Quill",
            "email": "riley@example.test",
            "phone": "555-0100",
            "location": "Portland, OR",
        },
        "experience": [
            {
                "company": "Harbor Clinic",
                "role": "Staff Nurse",
                "bullets": ["Ran the intake triage rotation."],
            }
        ],
        "education": [
            {
                "institution": "Lakeside Institute",
                "coursework": ["Anatomy"],
            }
        ],
    }
    data.update(overrides)
    return ResumeData.model_validate(data).model_dump(mode="json")


def _text(
    engine: str,
    resume: dict,
    tmp_path,
    stem: str,
    formatting=None,
    raw_typst_end: str | None = None,
) -> str:
    import pdfplumber

    template_engine, _ = BUNDLED_SOURCES[engine]
    source = _source(engine)
    if template_engine == "typst" and raw_typst_end is not None:
        sys_inputs = pdf_render.build_typst_sys_inputs(
            source, resume, formatting or {}, enforce_extras_support=False
        )
        payload = json.loads(sys_inputs["resume"])
        payload["experience"][0]["end_date"] = raw_typst_end
        if payload["education"]:
            payload["education"][0]["end_date"] = raw_typst_end
        sys_inputs["resume"] = json.dumps(payload)
        pdf = pdf_render.compile_typst_pdf(
            source, tmp_path, stem, sys_inputs=sys_inputs
        )
    else:
        pdf = render_template_pdf(
            source, template_engine, resume, formatting or {}, tmp_path, stem
        )
    with pdfplumber.open(pdf) as doc:
        return "\n".join(
            (page.extract_text(use_text_flow=True) or "") for page in doc.pages
        )


@pytest.mark.parametrize("engine", sorted(ENGINE_SOURCES))
def test_undated_entries_never_render_the_literal_none(engine, tmp_path):
    text = _text(engine, _resume(), tmp_path, "undated")
    assert "Harbor Clinic" in text and "Lakeside Institute" in text
    assert "none" not in text.lower()


@pytest.mark.parametrize("engine", sorted(ENGINE_SOURCES))
def test_undated_role_renders_no_date_cell_at_all(engine, tmp_path):
    """No start and no end means no date range — not a bare separator."""
    text = _text(engine, _resume(), tmp_path, "nodates")
    assert "–" not in text and "--" not in text


@pytest.mark.parametrize("engine", sorted(ENGINE_SOURCES))
def test_end_only_role_renders_the_end_without_a_leading_dash(engine, tmp_path):
    """A role with an end date but no start shows the end alone. The naive
    template emitted the separator unconditionally, so the PDF read "– Dec
    2020" as if the start had been dropped rather than never stated."""
    resume = _resume()
    resume["experience"][0]["end_date"] = "Dec 2020"
    text = _text(engine, resume, tmp_path, "endonly")
    assert "Dec 2020" in text
    for line in text.splitlines():
        assert not line.strip().startswith("–")
    assert "– Dec 2020" not in text


@pytest.mark.parametrize("engine", sorted(BUNDLED_SOURCES))
def test_ongoing_role_renders_start_to_present_once(engine, tmp_path):
    """A blank end date on a dated role is visibly ongoing, never omitted."""
    resume = _resume()
    resume["experience"][0]["start_date"] = "Jan 2022"
    resume["experience"][0]["end_date"] = ""
    text = _text(engine, resume, tmp_path, "ongoing")
    assert "Jan 2022 – Present" in text
    assert text.count("Present") == 1


@pytest.mark.parametrize("engine", sorted(BUNDLED_SOURCES))
def test_whitespace_end_renders_start_to_present_once(engine, tmp_path):
    """Template blankness matches the shared trimmed open-ended date rule."""
    resume = _resume()
    resume["experience"][0]["start_date"] = "Jan 2022"
    resume["experience"][0]["end_date"] = " \t "
    resume["education"][0]["start_date"] = "Sep 2019"
    resume["education"][0]["end_date"] = " \t "
    text = _text(
        engine,
        resume,
        tmp_path,
        "whitespace-ongoing",
        raw_typst_end=resume["experience"][0]["end_date"],
    )
    assert "Jan 2022 – Present" in text
    assert text.count("Present") == 1
    assert "Sep 2019" in text
    assert "Sep 2019 –" not in text


@pytest.mark.parametrize("engine", sorted(BUNDLED_SOURCES))
def test_start_only_education_does_not_render_present(engine, tmp_path):
    """A missing education end is unknown, not an ongoing employment claim."""
    resume = _resume()
    resume["experience"] = []
    resume["education"][0]["start_date"] = "Sep 2019"
    text = _text(engine, resume, tmp_path, "start-only-education")
    assert "Sep 2019" in text
    assert "Present" not in text


@pytest.mark.parametrize("engine", sorted(ENGINE_SOURCES))
def test_degree_less_education_ignores_education_order(engine, tmp_path):
    """With no degree there is nothing to order: both knob values must put the
    institution on the entry's own first line. The degree-first branch used to
    lead with an empty line and push the institution below its dates."""
    resume = _resume()
    resume["education"][0]["start_date"] = "Sep 2019"
    resume["education"][0]["end_date"] = "Jun 2020"
    degree_first = _text(
        engine, resume, tmp_path, "degfirst", {"education_order": "degree_first"}
    )
    institution_first = _text(
        engine, resume, tmp_path, "instfirst", {"education_order": "institution_first"}
    )
    assert degree_first == institution_first
    assert "Lakeside Institute Sep 2019 – Jun 2020" in degree_first


@pytest.mark.parametrize("engine", sorted(ENGINE_SOURCES))
def test_degree_bearing_education_still_honors_education_order(engine, tmp_path):
    """The fallback above is scoped to the degree-less case only."""
    resume = _resume()
    resume["education"][0]["degree"] = "B.S. Nursing"
    degree_first = _text(
        engine, resume, tmp_path, "hasdeg1", {"education_order": "degree_first"}
    )
    institution_first = _text(
        engine, resume, tmp_path, "hasdeg2", {"education_order": "institution_first"}
    )
    assert degree_first != institution_first
    assert "B.S. Nursing" in degree_first and "B.S. Nursing" in institution_first
