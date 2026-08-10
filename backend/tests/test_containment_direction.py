"""Token containment is directional, and the two directions are not equal.

Historically both directions returned ("fuzzy", term, 1.0):

  resume MORE specific  "apache spark" covers JD "Spark"        -> legitimate
  JD MORE specific      resume "aws" covers JD "AWS SageMaker"  -> over-credit

The second direction let a single skills-list token satisfy an unbounded family
of specific asks (measured on the live corpus: 88 of 211 fuzzy matches, 40 on
`required` skills), and routed them to a `mirror_wording` gap stamped
`score_effect: "hygiene"` whose one-click action wrote the JD's literal string —
including certification names — onto a resume that never evidenced it.

The narrower term now earns partial credit and an honest gap. Purely generic
modifiers ("CI/CD pipelines" over "ci/cd") are exempt: the JD added a noun, not
a distinct product.
"""
from datetime import date

import pytest

from app.services.ats import embeddings, score_resume
from app.services.ats.config import load_config
from app.services.ats.matching import SkillMatcher
from app.services.gap_analysis import build_gaps
from tests.ats.fixtures import fake_embed_texts

AS_OF = date(2026, 7, 6)


@pytest.fixture(autouse=True)
def _fake_embedder(monkeypatch):
    monkeypatch.setattr(embeddings, "embed_texts", fake_embed_texts)


@pytest.fixture
def matcher():
    return SkillMatcher(load_config())


def test_resume_more_specific_keeps_full_credit(matcher):
    form, term, credit = matcher.match_terms_lexical("Spark", {"apache spark"})

    assert (form, term, credit) == ("fuzzy", "apache spark", 1.0)


def test_jd_more_specific_earns_partial_credit(matcher):
    form, term, credit = matcher.match_terms_lexical("AWS SageMaker", {"aws"})

    assert form == "broader"
    assert term == "aws"
    assert credit == load_config().weights["adjacency_max_credit"]


def test_jd_more_specific_never_fully_credits_a_certification(matcher):
    _, _, credit = matcher.match_terms_lexical(
        "AWS Certified Solutions Architect Professional", {"aws"}
    )

    assert credit < 1.0


def test_a_purely_generic_modifier_keeps_full_credit(matcher):
    """The JD added a generic noun, not a distinct product."""
    form, _, credit = matcher.match_terms_lexical("CI/CD pipelines", {"ci/cd"})

    assert (form, credit) == ("fuzzy", 1.0)


def test_exact_and_alias_matches_are_untouched(matcher):
    assert matcher.match_terms_lexical("Python", {"python"})[2] == 1.0
    assert matcher.match_terms_lexical("Spark", {"apache spark"})[2] == 1.0


def _resume(*items):
    return {
        "contact": {"name": "J", "email": "j@example.com", "phone": "1"},
        "summary": "Engineer.",
        "skills": [{"category": "Cloud", "items": list(items)}],
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
        "education": [{"institution": "S", "degree": "BS"}],
        "certifications": [],
    }


def _jd(*skills):
    return {
        "title": "Engineer",
        "skills": [{"skill_name": s, "requirement_level": "required"} for s in skills],
    }


def test_one_broad_token_no_longer_scores_a_perfect_keyword_subscore():
    """The headline defect: `aws`+`sql` used to satisfy a JD naming five distinct
    products at keyword 1.0."""
    result = score_resume(
        _resume("AWS", "SQL"),
        _jd("AWS SageMaker", "AWS Redshift", "Oracle SQL", "AWS EMR"),
        as_of=AS_OF,
    )

    assert result.subscores["keyword"] < 1.0


def test_broader_match_is_not_advertised_as_free_hygiene():
    """It used to route to mirror_wording, which the gap builder labels
    `score_effect: "hygiene"` — telling the user that pasting the JD's literal
    product name onto their resume costs nothing and changes nothing."""
    result = score_resume(_resume("AWS"), _jd("AWS SageMaker"), as_of=AS_OF)

    row = next(r for r in result.skill_table if r["jd_skill"] == "AWS SageMaker")
    assert row["fix_hint"] != "mirror_wording"

    buckets = {c["key"]: c["gaps"] for c in build_gaps(result)["categories"]}
    hygiene = [
        g
        for gaps in buckets.values()
        for g in gaps
        if g.get("jd_skill") == "AWS SageMaker" and g.get("score_effect") == "hygiene"
    ]
    assert hygiene == []


def test_a_vendor_qualifier_keeps_full_credit(matcher):
    """"Microsoft Teams" over "teams" and "Amazon Redshift" over "redshift" are
    the same skill with the vendor spelled out — not a different product."""
    assert matcher.match_terms_lexical("Microsoft Teams", {"teams"})[2] == 1.0
    assert matcher.match_terms_lexical("Amazon Redshift", {"redshift"})[2] == 1.0


def test_a_product_name_is_not_a_vendor_qualifier(matcher):
    """The mirror case that must stay downgraded: same vendor, different product."""
    assert matcher.match_terms_lexical("AWS Redshift", {"aws"})[0] == "broader"


def test_a_broader_skills_token_does_not_suppress_an_exact_prose_match():
    """Found by the corpus monotonicity run (50.3 -> 50.1).

    The skills-list stage runs before the prose stage and its form wins. That was
    harmless when both paid 1.0, but a `broader` skills token ("aws") now pays
    0.5 — so adding "AWS" to the skills list DOWNGRADED a JD skill that a dated
    bullet already evidenced exactly, and surfacing a true skill lowered the
    score. A broader term is also not a skills-list PLACEMENT for the specific
    skill: a recruiter boolean search for "SageMaker" does not hit "AWS".
    """
    resume = _resume("AWS")
    resume["experience"][0]["bullets"] = ["Trained models on AWS SageMaker."]

    result = score_resume(resume, _jd("AWS SageMaker"), as_of=AS_OF)

    row = next(r for r in result.skill_table if r["jd_skill"] == "AWS SageMaker")
    assert row["match_form"] == "exact"
    assert row["match_credit"] == 1.0
    assert row["placement"] == "experience_only"


def test_a_broader_skills_token_does_not_preempt_a_better_semantic_match(monkeypatch):
    """Second, deeper form of the same corpus violation.

    `broader` is a lexical form, and the semantic stage only runs when EVERY
    lexical stage missed. So a broad skills token short-circuited a semantic
    match against a DATED entry (credit 0.6 x 1.0) and replaced it with
    skills-list partial credit (0.5 x 0.4) — a 3x drop for adding a true skill.
    `broader` is fallback-grade evidence and must be tried AFTER semantics, in
    the same position adjacency already occupies.
    """
    import math

    def _embed(texts):
        out = []
        for t in texts:
            if t == "aws sagemaker":                      # the JD term
                out.append([1.0, 0.0])
            elif "managed endpoints" in t:                # the dated bullet
                out.append([0.95, math.sqrt(1 - 0.95**2)])
            else:
                out.append([0.0, 1.0])
        return out

    monkeypatch.setattr(embeddings, "embed_texts", _embed)

    resume = _resume("AWS")
    resume["experience"][0]["bullets"] = ["Deployed models on AWS managed endpoints."]

    result = score_resume(resume, _jd("aws sagemaker"), as_of=AS_OF)

    row = next(r for r in result.skill_table if r["jd_skill"] == "aws sagemaker")
    assert row["match_form"] == "semantic"
    assert row["placement"] == "experience_only"
