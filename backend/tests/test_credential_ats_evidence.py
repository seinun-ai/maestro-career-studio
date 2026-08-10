"""Credential (certification) ATS evidence.

`resume["certifications"]` was never read by the engine, so a candidate holding
the exact credential a JD names scored it `absent` — it sat in the L1/L2
denominators dragging a 52%-weighted slice down, and the gap builder told them to
go acquire a credential already on their resume.

Certifications now index as a dedicated, undated, deliberately conservative
evidence tier. Deliberately NOT indexed: education content (see the module-level
comment in resume_indexer), issuing dates, and anything that could turn a
credential into an employment-recency or tenure signal.
"""
from datetime import date

import pytest

from app.services.ats import embeddings, score_resume
from app.services.ats.config import load_config
from app.services.ats.resume_indexer import index_resume
from app.services.gap_analysis import build_gaps
from tests.ats.fixtures import fake_embed_texts

AS_OF = date(2026, 7, 6)

CERT = "AWS Certified Solutions Architect - Associate"


@pytest.fixture(autouse=True)
def _fake_embedder(monkeypatch):
    monkeypatch.setattr(embeddings, "embed_texts", fake_embed_texts)


def _resume(certifications=None, skills=None):
    return {
        "contact": {"name": "J", "email": "j@example.com", "phone": "1"},
        "summary": "Engineer.",
        "skills": [{"category": "Cloud", "items": list(skills)}] if skills else [],
        "experience": [
            {
                "company": "C",
                "role": "Data Engineer",
                "start_date": "Jan 2022",
                "end_date": "Present",
                "bullets": ["Built pipelines."],
            }
        ],
        "projects": [],
        "education": [{"institution": "School", "degree": "BS"}],
        "certifications": list(certifications or []),
    }


def _jd(*skills):
    return {
        "title": "Engineer",
        "skills": [{"skill_name": s, "requirement_level": "required"} for s in skills],
    }


def _row(result, skill):
    return next(r for r in result.skill_table if r["jd_skill"] == skill)


def test_certification_on_the_resume_matches_the_jd_row():
    result = score_resume(_resume(certifications=[CERT]), _jd(CERT), as_of=AS_OF)

    row = _row(result, CERT)
    assert row["matched"] is True
    assert row["placement"] == "credential_only"
    assert row["contribution"] > 0


def test_certification_the_candidate_lacks_is_still_absent():
    result = score_resume(_resume(certifications=[]), _jd(CERT), as_of=AS_OF)

    row = _row(result, CERT)
    assert row["matched"] is False
    assert row["fix_hint"] == "absent"


def test_credential_evidence_scores_below_dated_experience():
    """A named credential is a verifiable fact, but it is not applied work: it
    must never outscore a dated core entry."""
    jd = _jd("Kubernetes")
    by_cert = score_resume(_resume(certifications=["Kubernetes"]), jd, as_of=AS_OF)
    by_work = _resume()
    by_work["experience"][0]["bullets"] = ["Ran Kubernetes in production."]
    by_work = score_resume(by_work, jd, as_of=AS_OF)

    assert _row(by_cert, "Kubernetes")["contribution"] < _row(by_work, "Kubernetes")["contribution"]


def test_credential_evidence_scores_above_a_bare_skills_list_token():
    jd = _jd("Kubernetes")
    by_cert = score_resume(_resume(certifications=["Kubernetes"]), jd, as_of=AS_OF)
    by_list = score_resume(_resume(skills=["Kubernetes"]), jd, as_of=AS_OF)

    assert _row(by_cert, "Kubernetes")["contribution"] > _row(by_list, "Kubernetes")["contribution"]


def test_credentials_never_become_an_employment_recency_or_tenure_signal():
    index = index_resume(_resume(certifications=[CERT]), as_of=AS_OF, config=load_config())

    credential = [e for e in index.entries if e.section == "credential"]
    assert credential, "certification should be indexed"
    assert all(e.last_date is None and not e.is_current for e in credential)
    # tenure and recent-role come from experience only
    assert index.recent_role == "Data Engineer"
    assert index.total_experience_years == pytest.approx(4.4, abs=0.2)


def test_credentials_do_not_corroborate_the_skills_stuffing_lint():
    """A certifications list must not launder an uncorroborated skills section."""
    resume = _resume(certifications=["Terraform", "Kubernetes", "Docker", "Ansible"],
                     skills=["Terraform", "Kubernetes", "Docker", "Ansible"])
    resume["experience"][0]["bullets"] = ["Wrote documentation."]

    result = score_resume(resume, _jd("Terraform"), as_of=AS_OF)

    assert any("no supporting evidence" in f for f in result.format_flags)


def test_credential_only_evidence_still_produces_an_actionable_gap():
    result = score_resume(_resume(certifications=[CERT]), _jd(CERT), as_of=AS_OF)

    row = _row(result, CERT)
    assert row["fix_hint"] == "credential_only"
    # routed to a real bucket, NOT missing_skills: the candidate holds it
    buckets = {c["key"]: c["gaps"] for c in build_gaps(result)["categories"]}
    assert any(g.get("jd_skill") == CERT for g in buckets.get("resurface_recent", []))
    assert not any(g.get("jd_skill") == CERT for g in buckets.get("missing_skills", []))


def test_engine_is_unchanged_when_the_credential_block_is_absent(monkeypatch):
    """Feature-off fallback: a legacy weights.yaml without credential_evidence
    must score exactly as it did before this change."""
    cfg = load_config()
    weights = {k: v for k, v in cfg.weights.items() if k != "credential_evidence"}
    legacy = type(cfg)(
        weights=weights,
        aliases=cfg.aliases,
        adjacency=cfg.adjacency,
        title_families=cfg.title_families,
        version="legacy-test",
    )

    result = score_resume(_resume(certifications=[CERT]), _jd(CERT), as_of=AS_OF, config=legacy)

    assert _row(result, CERT)["matched"] is False


def test_a_credential_never_steals_attribution_from_dated_work(monkeypatch):
    """The semantic stage picks ONE winning candidate. A short credential string
    can out-cosine a long dated bullet, which would demote a skill the candidate
    genuinely practices from experience_only (1.0) to credential_only (0.5) and
    LOWER the score for adding true information.

    _select_placement already resolves this for the lexical path by effective
    multiplier rather than branch order (finding F#9); the semantic stage must
    follow the same rule.
    """
    import math

    def _embed(texts):
        out = []
        for t in texts:
            if t == "statistical modeling":                   # the JD term itself
                out.append([1.0, 0.0])
            elif "certificate" in t:
                out.append([0.99, math.sqrt(1 - 0.99**2)])   # closest, but weakest source
            else:
                out.append([0.70, math.sqrt(1 - 0.70**2)])   # dated bullet: further away
        return out

    monkeypatch.setattr(embeddings, "embed_texts", _embed)

    resume = _resume(certifications=["Statistical Analysis certificate"])
    resume["experience"][0]["bullets"] = ["Statistical analysis of live experiments."]

    result = score_resume(resume, _jd("statistical modeling"), as_of=AS_OF)

    row = _row(result, "statistical modeling")
    assert row["matched"] is True
    assert row["placement"] == "experience_only"
