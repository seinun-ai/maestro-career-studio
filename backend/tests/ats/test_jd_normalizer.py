from app.services.ats.jd_normalizer import normalize_jd
from tests.ats.fixtures import SAMPLE_JD


def test_normalize_jd_extracts_profile():
    profile = normalize_jd(SAMPLE_JD)
    assert profile.title == "Senior Data Scientist"
    assert profile.role_category == "data_scientist"
    assert profile.years_experience_min == 5
    names = [s.name for s in profile.skills]
    assert "Python" in names and "Salesforce" in names
    required = [s for s in profile.skills if s.requirement_level == "required"]
    assert len(required) == 3


def test_normalize_jd_degrades_an_unrecognized_stored_role_category_to_other():
    profile = normalize_jd({
        "title": "Data Wizard",
        "role_category": "retired_family",
        "skills": [{"skill_name": "Python", "requirement_level": "required"}],
    })

    assert profile.role_category == "other"


def test_normalize_jd_dedupes_and_defaults_level():
    jd = {"title": "X", "skills": [
        {"skill_name": "Python", "requirement_level": "required"},
        {"skill_name": "python ", "requirement_level": "preferred"},  # dup, keep strongest
        {"skill_name": "SQL"},  # missing level -> mentioned
    ]}
    profile = normalize_jd(jd)
    assert len(profile.skills) == 2
    python = next(s for s in profile.skills if s.canonical == "python")
    assert python.requirement_level == "required"
    sql = next(s for s in profile.skills if s.canonical == "sql")
    assert sql.requirement_level == "mentioned"


def test_normalize_jd_requires_skills():
    import pytest
    with pytest.raises(ValueError, match="no extracted skills"):
        normalize_jd({"title": "X", "skills": []})


def test_requirement_lines_from_responsibilities_and_qualifications():
    profile = normalize_jd(SAMPLE_JD)
    # responsibilities + qualifications, in order, str-coerced, blank-filtered
    assert profile.requirement_lines == ["Build ML models", "5+ years of experience"]


def test_requirement_lines_str_coerce_and_blank_filter():
    jd = {
        "title": "X",
        "skills": [{"skill_name": "Python", "requirement_level": "required"}],
        "responsibilities": ["  Own the pipeline ", "", None, 42],
        "qualifications": ["   ", "BS in CS"],
    }
    profile = normalize_jd(jd)
    # blanks/None dropped, non-strings coerced, whitespace stripped
    assert profile.requirement_lines == ["Own the pipeline", "42", "BS in CS"]


def test_requirement_lines_fallback_to_skill_names_when_both_empty():
    jd = {
        "title": "X",
        "skills": [
            {"skill_name": "Python", "requirement_level": "required"},
            {"skill_name": "SQL", "requirement_level": "mentioned"},
        ],
        "responsibilities": [],
        "qualifications": [],
    }
    profile = normalize_jd(jd)
    assert profile.requirement_lines == ["Python", "SQL"]


def test_requirement_lines_fallback_when_keys_absent():
    jd = {"title": "X", "skills": [{"skill_name": "Python", "requirement_level": "required"}]}
    profile = normalize_jd(jd)
    assert profile.requirement_lines == ["Python"]
