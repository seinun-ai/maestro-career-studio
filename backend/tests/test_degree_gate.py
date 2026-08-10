"""Advisory degree gate.

Degree requirements are surfaced, never scored. Every ATS platform surveyed puts
the education knockout in an application-form QUESTION, not in resume parsing, so
the honest product behavior is to tell the user a question is coming — not to
move a number they cannot change.

The gate is deliberately fail-silent: it warns only when it positively reads a
LOWER degree level than the JD asked for. An unparseable degree, an unstated
requirement, or an "or equivalent experience" clause all produce silence, because
a false accusation ("your degree does not qualify") is far worse than saying
nothing.
"""
from datetime import date

import pytest

from app.services.ats import embeddings, score_resume
from tests.ats.fixtures import fake_embed_texts

AS_OF = date(2026, 7, 6)


@pytest.fixture(autouse=True)
def _fake_embedder(monkeypatch):
    monkeypatch.setattr(embeddings, "embed_texts", fake_embed_texts)


def _resume(education):
    return {
        "contact": {"name": "J", "email": "j@example.com", "phone": "1"},
        "summary": "Engineer.",
        "skills": [{"category": "Lang", "items": ["Python"]}],
        "experience": [
            {
                "company": "C",
                "role": "Engineer",
                "start_date": "Jan 2022",
                "end_date": "Present",
                "bullets": ["Wrote Python."],
            }
        ],
        "projects": [],
        "education": education,
        "certifications": [],
    }


def _jd(*qualifications):
    return {
        "title": "Engineer",
        "skills": [{"skill_name": "Python", "requirement_level": "required"}],
        "qualifications": list(qualifications),
    }


def _degree_warnings(result):
    return [w for w in result.gate_warnings if "degree" in w.lower()]


def test_warns_when_the_jd_asks_for_a_higher_degree_than_the_resume_shows():
    result = score_resume(
        _resume([{"institution": "S", "degree": "BS", "field": "CS"}]),
        _jd("Master's degree in Computer Science required"),
        as_of=AS_OF,
    )

    assert _degree_warnings(result)


def test_is_silent_when_the_resume_degree_meets_or_exceeds_the_ask():
    result = score_resume(
        _resume([{"institution": "S", "degree": "MS", "field": "CS"}]),
        _jd("Bachelor's degree in Computer Science required"),
        as_of=AS_OF,
    )

    assert _degree_warnings(result) == []


def test_is_silent_when_the_jd_allows_equivalent_experience():
    result = score_resume(
        _resume([{"institution": "S", "degree": "BS"}]),
        _jd("Master's degree or equivalent practical experience"),
        as_of=AS_OF,
    )

    assert _degree_warnings(result) == []


def test_is_silent_when_the_resume_degree_cannot_be_parsed():
    """Fail-silent: never tell a user their real degree does not qualify just
    because the parser did not recognize it."""
    result = score_resume(
        _resume([{"institution": "S", "degree": "Licenciatura en Informatica"}]),
        _jd("Master's degree required"),
        as_of=AS_OF,
    )

    assert _degree_warnings(result) == []


def test_is_silent_when_the_jd_states_no_degree_requirement():
    result = score_resume(
        _resume([{"institution": "S", "degree": "BS"}]),
        _jd("Experience shipping production services"),
        as_of=AS_OF,
    )

    assert _degree_warnings(result) == []


def test_the_warning_does_not_move_the_composite():
    """Advisory only — the knockout lives in the application form.

    Same JD both times (so the L6 text is identical); only the degree varies, so
    the gate is the ONLY thing that differs between the two runs.
    """
    jd = _jd("PhD required")
    warned = score_resume(_resume([{"institution": "S", "degree": "BS"}]), jd, as_of=AS_OF)
    silent = score_resume(_resume([{"institution": "S", "degree": "PhD"}]), jd, as_of=AS_OF)

    assert _degree_warnings(warned) and not _degree_warnings(silent)
    assert warned.composite == silent.composite
    assert warned.subscores == silent.subscores


def test_degree_text_still_never_becomes_skill_evidence():
    """The gate reads education; the SCORER still must not. A JD skill named
    after a field of study must not match on the education line alone."""
    result = score_resume(
        _resume([{"institution": "S", "degree": "MS", "field": "Machine Learning"}]),
        {
            "title": "Engineer",
            "skills": [{"skill_name": "Machine Learning", "requirement_level": "required"}],
        },
        as_of=AS_OF,
    )

    row = next(r for r in result.skill_table if r["jd_skill"] == "Machine Learning")
    assert row["matched"] is False
