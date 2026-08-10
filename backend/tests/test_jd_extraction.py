import pytest

from app.services import jd_extraction
from app.services.jd_extraction import apply_work_auth_backstop


def test_extract_jd_calls_fast_model_and_validates(monkeypatch):
    monkeypatch.setattr(
        jd_extraction.prompt_assembly,
        "build_extraction_prompt",
        lambda raw_text: f"prompt: {raw_text}",
    )
    monkeypatch.setattr(jd_extraction.model_settings, "get_fast_model", lambda session=None: "gpt-fast")

    calls = {}

    def fake_call_openai(**kwargs):
        calls.update(kwargs)
        return {
            "company": "Acme",
            "title": "Data Analyst",
            "role_category": "data_analyst",
            "skills": [
                {
                    "skill_name": "SQL",
                    "skill_category": "language",
                    "requirement_level": "required",
                }
            ],
        }

    monkeypatch.setattr(jd_extraction.llm, "call_openai", fake_call_openai)

    result = jd_extraction.extract_jd("Need SQL")

    assert calls["model"] == "gpt-fast"
    assert calls["response_format"] == "json"
    assert result["company"] == "Acme"
    assert result["skills"][0]["skill_name"] == "SQL"


def test_extract_jd_detects_hourly_salary_when_llm_omits_it(monkeypatch):
    monkeypatch.setattr(
        jd_extraction.prompt_assembly,
        "build_extraction_prompt",
        lambda raw_text: raw_text,
    )
    monkeypatch.setattr(
        jd_extraction.llm,
        "call_openai",
        lambda **kwargs: {"title": "Contract Analyst", "role_category": "data_analyst"},
    )
    monkeypatch.setattr(jd_extraction.model_settings, "get_fast_model", lambda session=None: "gpt-fast")

    result = jd_extraction.extract_jd("Pay range is $45 - $55/hour.")

    assert result["salary_min"] == "45"
    assert result["salary_max"] == "55"
    assert result["salary_period"] == "hour"




@pytest.mark.parametrize(
    "raw_text",
    [
        "We do not offer sponsorship for this role.",
        "The company will not sponsor work visas.",
        "We are unable to sponsor applicants at this time.",
        "Candidates must be authorized to work in the US without sponsorship.",
    ],
)
def test_backstop_flips_unstated_to_no_sponsorship(raw_text):
    out = apply_work_auth_backstop(raw_text, {"work_authorization": "unstated"})
    assert out["work_authorization"] == "no_sponsorship"


@pytest.mark.parametrize(
    "raw_text",
    [
        "This position is open to US citizens only.",
        "US citizenship is required for this role.",
        "An active security clearance is required.",
        "Applicants must be a US person to be considered.",
    ],
)
def test_backstop_flips_unstated_to_citizen_or_gc(raw_text):
    out = apply_work_auth_backstop(raw_text, {"work_authorization": "unstated"})
    assert out["work_authorization"] == "citizen_or_gc_required"


def test_backstop_ignores_inclusive_citizen_language():
    raw = "US citizens are encouraged to apply; we welcome all backgrounds."
    out = apply_work_auth_backstop(raw, {"work_authorization": "unstated"})
    assert out["work_authorization"] == "unstated"


@pytest.mark.parametrize(
    "raw_text",
    [
        "We do not offer event sponsorship.",
        "We do not provide media sponsorship for conferences.",
    ],
)
def test_backstop_ignores_non_work_sponsorship(raw_text):
    out = apply_work_auth_backstop(raw_text, {"work_authorization": "unstated"})
    assert out["work_authorization"] == "unstated"


def test_backstop_never_downgrades_stronger_llm_value():
    raw = "We do not offer sponsorship."
    out = apply_work_auth_backstop(raw, {"work_authorization": "sponsorship_available"})
    assert out["work_authorization"] == "sponsorship_available"


def test_backstop_noop_without_raw_text():
    out = apply_work_auth_backstop("", {"work_authorization": "unstated"})
    assert out["work_authorization"] == "unstated"


def test_backstop_prefers_no_sponsorship_over_citizen_when_both_present():
    raw = "US citizens only. We do not provide visa sponsorship."
    out = apply_work_auth_backstop(raw, {"work_authorization": "unstated"})
    assert out["work_authorization"] == "no_sponsorship"


def test_extract_jd_prompt_offers_the_certification_skill_category():
    """The credential evidence tier is dead weight unless the extractor has a
    sanctioned slot for a named certification. Without this the model has no
    category to put "AWS Certified Solutions Architect" in, and cert requirements
    scatter into free-text qualifications where only L6 sees them."""
    from app.services import prompts

    template = prompts._file_default("extract_jd")

    assert "certification" in template
    # and it must NOT invite inventing one
    assert "never infer" in template.lower()


def test_certification_is_a_storable_skill_category():
    from app.services.skill_normalize import coerce_skill_category

    assert coerce_skill_category("certification") == "certification"
