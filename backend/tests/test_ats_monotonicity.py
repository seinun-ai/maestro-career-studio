"""Monotonicity: adding TRUE evidence must never lower the composite.

The score is an ordinal instrument — what it is for is "does doing this to my
resume help?" — so a direction error is worse than an absolute-accuracy error.
A user who adds a certification they genuinely hold and watches the number fall
has been told a lie, however small the drop.

This is deliberately NOT asserted as a universal law, because two drops are
correct and wanted:

  * adding an UNCORROBORATED skills item can lower `format` — the L5 stuffing
    lint exists precisely to penalize keyword padding, and that is the honest
    answer to "should I stuff my skills list?" (kept here as the non-vacuity
    control: it proves the checker can actually report a drop)
  * adding unrelated prose to a dated entry dilutes that entry's embedding and
    can move a semantic match — inherent to embedding matching, not a defect

So the asserted set is the mutations where a drop has no honest explanation.
"""
from datetime import date

import pytest

from app.services.ats import embeddings, score_resume
from scripts.ats_calibration import (
    MONOTONE_MUTATIONS,
    add_uncorroborated_skill,
    check_monotonicity,
)
from tests.ats.fixtures import SAMPLE_JD, SAMPLE_RESUME, fake_embed_texts

AS_OF = date(2026, 7, 6)


@pytest.fixture(autouse=True)
def _fake_embedder(monkeypatch):
    monkeypatch.setattr(embeddings, "embed_texts", fake_embed_texts)


def _resume(**over):
    base = {
        "contact": {"name": "J", "email": "j@example.com", "phone": "1"},
        "summary": "Engineer.",
        "skills": [{"category": "Lang", "items": ["Python"]}],
        "experience": [
            {
                "company": "C",
                "role": "Data Engineer",
                "start_date": "Jan 2022",
                "end_date": "Present",
                "bullets": ["Built Python pipelines."],
            }
        ],
        "projects": [],
        "education": [{"institution": "S", "degree": "BS"}],
        "certifications": [],
    }
    base.update(over)
    return base


def _jd(*skills):
    return {
        "title": "Engineer",
        "skills": [{"skill_name": s, "requirement_level": "required"} for s in skills],
    }


def test_the_checker_reports_a_drop_when_one_exists():
    """Non-vacuity control. A checker that always returns [] would pass every
    other test in this file, so prove it can fail — using the ONE mutation whose
    drop is intentional (skills-list padding tripping the L5 stuffing lint).
    """
    # 1 of 2 items corroborated by the bullet == exactly the 0.5 lint ceiling, so
    # the resume passes; one more uncorroborated item pushes it over.
    resume = _resume(skills=[{"category": "Lang", "items": ["Python", "Rust"]}])
    violations = check_monotonicity(
        resume, _jd("Python"), as_of=AS_OF, mutations={"pad_skills": add_uncorroborated_skill}
    )

    assert violations, "the stuffing lint must still punish keyword padding"
    assert violations[0].after < violations[0].before


def test_adding_a_held_certification_never_lowers_the_score():
    resume = _resume()
    jd = _jd("AWS Certified Solutions Architect", "Python", "Kubernetes")

    assert check_monotonicity(resume, jd, as_of=AS_OF) == []


def test_adding_a_held_certification_actually_raises_the_score():
    """Non-decreasing is not enough — a credential the JD names must MOVE it,
    or the tool is telling the user their real credential is worthless."""
    jd = _jd("AWS Certified Solutions Architect")
    before = score_resume(_resume(), jd, as_of=AS_OF).composite
    after = score_resume(
        _resume(certifications=["AWS Certified Solutions Architect"]), jd, as_of=AS_OF
    ).composite

    assert after > before


def test_dual_placing_an_already_evidenced_skill_never_lowers_the_score():
    """Surfacing a skill that a dated bullet already proves into the skills list
    is the single most-recommended fix the gap builder emits. It must pay."""
    resume = _resume()
    jd = _jd("Python")

    assert check_monotonicity(resume, jd, as_of=AS_OF) == []


def test_the_golden_fixture_is_monotone():
    assert check_monotonicity(SAMPLE_RESUME, SAMPLE_JD, as_of=AS_OF) == []


def test_every_monotone_mutation_is_exercised_by_the_default_set():
    """Guard against a mutation being silently dropped from the asserted set."""
    assert set(MONOTONE_MUTATIONS) == {"add_certification", "dual_place_skill"}
