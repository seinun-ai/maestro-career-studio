from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from app.services.ats import layers
from app.services.ats.config import ENGINE_VERSION, AtsConfig, load_config
from app.services.ats.jd_normalizer import normalize_jd
from app.services.ats.matching import SkillMatcher
from app.services.ats.resume_indexer import index_resume
from app.services.script_guard import extract_text_for_script_check, validate_script

LOW_COVERAGE_THRESHOLD = 0.25
LOW_COVERAGE_MESSAGE = "I could not read this posting — treat this score as unreliable"


@dataclass(frozen=True)
class AtsResult:
    composite: float                 # 0-100
    subscores: dict[str, float]      # keyword / placement_recency / semantic_fit / title / format (each 0-1)
    title_tier: str
    gate_warnings: list[str]
    format_flags: list[str]
    skill_table: list[dict[str, Any]]
    engine_version: str
    config_version: str
    # Per-JD-requirement-line semantic coverage from L6: [{"line": str, "score":
    # float}, ...] ordered as the requirement lines. Purely additive exposure of
    # the maxima l6_semantic_fit already computes (feeds weak_coverage gaps).
    requirement_coverage: list[dict[str, Any]] = field(default_factory=list)
    jd_skills_extracted_count: int = 0
    jd_skills_matched_count: int = 0
    coverage_ratio: float = 0.0
    coverage_warning: str | None = None


def _calc_coverage_signal(extracted_count: int, rows: list[Any]) -> tuple[int, float, str | None]:
    matched_count = sum(1 for r in rows if r.matched or r.match_form is not None)
    ratio = round(matched_count / max(1, extracted_count), 4)
    warning = (
        LOW_COVERAGE_MESSAGE
        if (extracted_count == 0 or ratio < LOW_COVERAGE_THRESHOLD)
        else None
    )
    return matched_count, ratio, warning


def _validate_input_script(jd_json: dict[str, Any], resume_json: dict[str, Any]) -> None:
    jd_text = extract_text_for_script_check(jd_json)
    if jd_text:
        validate_script(jd_text, source_label="job description")
    resume_text = extract_text_for_script_check(resume_json)
    if resume_text:
        validate_script(resume_text, source_label="resume")


def score_resume(
    resume_json: dict[str, Any],
    jd_json: dict[str, Any],
    *,
    as_of: date | None = None,
    config: AtsConfig | None = None,
) -> AtsResult:
    _validate_input_script(jd_json, resume_json)

    cfg = config or load_config()
    as_of = as_of or date.today()
    profile = normalize_jd(jd_json)
    index = index_resume(resume_json, as_of=as_of, config=cfg)
    matcher = SkillMatcher(cfg)

    rows = layers.resolve_evidence(profile, index, matcher, cfg, as_of=as_of)
    title_tier, title_score = layers.l3_title(profile, index, cfg)
    format_score, format_flags = layers.l5_format(index, rows, cfg)
    # Single L6 embed call yields both the subscore and its per-line detail.
    semantic_score, requirement_coverage = layers.l6_semantic_fit_coverage(profile, index)
    subscores = {
        "keyword": round(layers.l1_keyword(rows, cfg), 4),
        "placement_recency": round(layers.l2_placement_recency(rows, cfg), 4),
        "semantic_fit": round(semantic_score, 4),
        "title": round(title_score, 4),
        "format": round(format_score, 4),
    }
    weights = cfg.weights["composite_weights"]
    composite = round(100 * sum(subscores[k] * weights[k] for k in weights), 1)

    jd_skills_extracted_count = len(profile.skills)
    jd_skills_matched_count, coverage_ratio, coverage_warning = _calc_coverage_signal(
        jd_skills_extracted_count, rows
    )

    return AtsResult(
        composite=composite,
        subscores=subscores,
        title_tier=title_tier,
        gate_warnings=layers.l4_gate(profile, index),
        format_flags=format_flags,
        skill_table=[asdict(r) for r in rows],
        engine_version=ENGINE_VERSION,
        config_version=cfg.version,
        requirement_coverage=requirement_coverage,
        jd_skills_extracted_count=jd_skills_extracted_count,
        jd_skills_matched_count=jd_skills_matched_count,
        coverage_ratio=coverage_ratio,
        coverage_warning=coverage_warning,
    )
