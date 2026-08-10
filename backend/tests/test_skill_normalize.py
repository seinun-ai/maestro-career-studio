from typing import get_args

from app.services.skill_normalize import (
    SKILL_CATEGORIES,
    SkillCategory,
    canonicalize_skill_name,
    coerce_skill_category,
)


def test_skill_categories_match_literal():
    # SKILL_CATEGORIES is the runtime tuple backing the Literal type.
    assert set(SKILL_CATEGORIES) == set(get_args(SkillCategory))


def test_skill_categories_are_the_audit_set():
    assert set(SKILL_CATEGORIES) == {
        "language",
        "framework",
        "library",
        "ml_modeling",
        "nlp_genai",
        "cloud",
        "data_engineering",
        "database",
        "bi_visualization",
        "methodology",
        "tool",
        "domain",
        "soft_skills",
        "certification",
        "other",
    }


def test_coerce_known_category_passes_through():
    assert coerce_skill_category("language") == "language"
    assert coerce_skill_category("ml_modeling") == "ml_modeling"


def test_coerce_normalizes_case_and_whitespace():
    assert coerce_skill_category("  Language  ") == "language"
    assert coerce_skill_category("NLP_GenAI") == "nlp_genai"


def test_coerce_unknown_buckets_to_other():
    assert coerce_skill_category("frontend") == "other"
    assert coerce_skill_category("") == "other"
    assert coerce_skill_category(None) == "other"


def test_canonicalize_casefolds_and_strips():
    assert canonicalize_skill_name("  Python  ") == "python"
    assert canonicalize_skill_name("SQL") == "sql"


def test_canonicalize_collapses_internal_whitespace():
    assert canonicalize_skill_name("Data   Modeling") == "data modeling"


def test_canonicalize_aliases_llm():
    assert (
        canonicalize_skill_name("LLM")
        == canonicalize_skill_name("Large Language Models")
        == "large language models"
    )


def test_canonicalize_aliases_are_conservative():
    # No alias map entry => identity (just normalized casing/whitespace).
    assert canonicalize_skill_name("Kubernetes") == "kubernetes"


def test_canonicalize_empty_returns_empty():
    assert canonicalize_skill_name("") == ""
    assert canonicalize_skill_name(None) == ""
