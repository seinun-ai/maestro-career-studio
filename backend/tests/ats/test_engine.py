import copy
from datetime import date

import pytest

from app.services.ats import embeddings, score_resume
from tests.ats.fixtures import SAMPLE_JD, SAMPLE_RESUME, fake_embed_texts

AS_OF = date(2026, 7, 6)


@pytest.fixture(autouse=True)
def _fake_embedder(monkeypatch):
    """Engine tests run model-free; the golden test (real model) has its own path."""
    monkeypatch.setattr(embeddings, "embed_texts", fake_embed_texts)


def test_score_resume_returns_full_result():
    result = score_resume(SAMPLE_RESUME, SAMPLE_JD, as_of=AS_OF)
    assert 0 <= result.composite <= 100
    assert set(result.subscores) == {
        "keyword", "placement_recency", "semantic_fit", "title", "format",
    }
    assert 0.0 <= result.subscores["semantic_fit"] <= 1.0
    assert isinstance(result.gate_warnings, list)
    assert len(result.skill_table) == len(SAMPLE_JD["skills"])
    row = next(r for r in result.skill_table if r["jd_skill"] == "Salesforce")
    assert row["fix_hint"] == "absent" and row["matched"] is False
    assert result.engine_version == "ats-2.5.0" and result.config_version


def test_score_resume_is_deterministic():
    a = score_resume(SAMPLE_RESUME, SAMPLE_JD, as_of=AS_OF)
    b = score_resume(SAMPLE_RESUME, SAMPLE_JD, as_of=AS_OF)
    assert a.composite == b.composite and a.skill_table == b.skill_table


def test_fixing_a_gap_raises_composite():
    improved = copy.deepcopy(SAMPLE_RESUME)
    improved["skills"][0]["items"].append("Salesforce")
    improved["experience"][0]["bullets"].append(
        "Integrated Salesforce CRM data into forecasting models."
    )
    base = score_resume(SAMPLE_RESUME, SAMPLE_JD, as_of=AS_OF).composite
    after = score_resume(improved, SAMPLE_JD, as_of=AS_OF).composite
    assert after > base


def test_score_resume_exposes_requirement_coverage():
    # L6 per-line coverage is surfaced additively: one {line, score} per non-blank
    # JD requirement line (responsibilities + qualifications), in requirement order.
    result = score_resume(SAMPLE_RESUME, SAMPLE_JD, as_of=AS_OF)
    rc = result.requirement_coverage
    assert isinstance(rc, list) and rc, "requirement_coverage must be a non-empty list"
    assert all(set(item) == {"line", "score"} for item in rc)
    assert all(isinstance(item["line"], str) for item in rc)
    assert all(isinstance(item["score"], float) for item in rc)
    # ordered exactly like the JD requirement lines (responsibilities + qualifications)
    assert [item["line"] for item in rc] == ["Build ML models", "5+ years of experience"]


def test_requirement_coverage_exposure_does_not_drift_semantic_fit():
    # No-drift guard: exposing the per-line maxima must reuse the SAME L6
    # computation, so the semantic_fit subscore is byte-for-byte what it was
    # before the coverage field existed (pinned for the fake-embedder fixture).
    result = score_resume(SAMPLE_RESUME, SAMPLE_JD, as_of=AS_OF)
    assert result.subscores["semantic_fit"] == 0.2587


def test_score_resume_minimal_resume_does_not_crash():
    minimal = {
        "contact": {}, "summary": "", "skills": [],
        "experience": [], "projects": [], "education": [], "certifications": [],
    }
    result = score_resume(minimal, SAMPLE_JD, as_of=AS_OF)
    assert 0 <= result.composite <= 100
    assert all(row["matched"] is False for row in result.skill_table)
    assert result.gate_warnings      # 0 dated years vs JD min 5
    assert result.format_flags       # missing contact + empty sections
