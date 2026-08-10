import copy
from datetime import date

import pytest

from app.services import role_categories
from app.services.ats import embeddings, layers
from app.services.ats.config import load_config
from app.services.ats.jd_normalizer import normalize_jd
from app.services.ats.matching import SkillMatcher
from app.services.ats.resume_indexer import index_resume
from tests.ats.fixtures import SAMPLE_JD, SAMPLE_RESUME, fake_embed_texts

AS_OF = date(2026, 7, 6)


@pytest.fixture(autouse=True)
def _fake_embedder(monkeypatch):
    """Every test in this file runs model-free. Unrelated texts get the 0.0-cosine
    default vector, so existing lexical behavior is unchanged (Salesforce/Docker
    stay absent, etc.) — proving the semantic stage never disturbs lexical hits."""
    monkeypatch.setattr(embeddings, "embed_texts", fake_embed_texts)


def _evidence():
    cfg = load_config()
    return layers.resolve_evidence(
        normalize_jd(SAMPLE_JD),
        index_resume(SAMPLE_RESUME, as_of=AS_OF),
        SkillMatcher(cfg), cfg, as_of=AS_OF,
    ), cfg


def _row(rows, name):
    return next(r for r in rows if r.jd_skill == name)


def test_evidence_placements():
    rows, _ = _evidence()
    python = _row(rows, "Python")     # skills list + current DataCo bullet
    assert python.matched and python.placement == "dual"
    assert python.recency_weight == 1.0 and python.fix_hint is None

    aws = _row(rows, "AWS")           # "Amazon Web Services" in skills + bullet -> alias dual
    assert aws.matched and aws.placement == "dual" and aws.match_form == "alias"
    assert aws.fix_hint == "mirror_wording"  # literal "AWS" token absent from skills list

    tableau = _row(rows, "Tableau")   # only in OldCo bullet (ended Jun 2021)
    assert tableau.placement == "experience_only"
    assert tableau.recency_weight < 0.7 and tableau.fix_hint == "resurface_recent"

    snowflake = _row(rows, "Snowflake")  # bigquery adjacency from skills list
    assert snowflake.match_form == "adjacent" and snowflake.fix_hint == "adjacent_available"
    assert snowflake.contribution < _row(rows, "Python").contribution
    assert snowflake.recency_weight is None  # no dated evidence -> nothing to report

    salesforce = _row(rows, "Salesforce")  # only in DISABLED entry -> invisible
    assert not salesforce.matched and salesforce.fix_hint == "absent"

    docker = _row(rows, "Docker")
    assert not docker.matched


def test_skills_list_only_placement():
    rows, _ = _evidence()
    # Snowflake's adjacency evidence (bigquery) lives only in the skills section
    snowflake = _row(rows, "Snowflake")
    assert snowflake.placement == "skills_list_only"


def test_undated_prose_only_placement_is_undated_only():
    # A skill found ONLY in an undated project's prose must not masquerade as
    # skills_list_only: it gets the honest placement, no recency claim, and
    # the intervention is to surface it in a dated entry.
    cfg = load_config()
    resume = {
        "contact": {"name": "J", "email": "j@x.com", "phone": "1"},
        "summary": "Engineer.",
        "skills": [{"category": "Core", "items": ["Python"]}],
        "experience": [],
        "projects": [{
            "name": "Infra Modules", "enabled": True, "tech": "Terraform",
            "link": None, "date": None, "bullets": ["Wrote Terraform modules."],
        }],
    }
    jd = {"title": "Engineer", "skills": [
        {"skill_name": "Terraform", "requirement_level": "required"},
    ]}
    rows = layers.resolve_evidence(
        normalize_jd(jd), index_resume(resume, as_of=AS_OF),
        SkillMatcher(cfg), cfg, as_of=AS_OF,
    )
    tf = rows[0]
    assert tf.matched and tf.placement == "undated_only"
    assert tf.fix_hint == "resurface_recent"
    assert tf.recency_weight is None
    assert tf.evidence_entries == ["Infra Modules"]
    # contribution: undated_only multiplier, no recency decay applied
    mult = cfg.weights["placement_multipliers"]["undated_only"]
    assert tf.contribution == round(2.0 * 1.0 * mult * 1.0, 4)


def test_skills_hit_plus_undated_prose_stays_skills_list_only():
    cfg = load_config()
    resume = {
        "contact": {"name": "J", "email": "j@x.com", "phone": "1"},
        "summary": "Engineer.",
        "skills": [{"category": "Core", "items": ["Terraform"]}],
        "experience": [],
        "projects": [{
            "name": "Infra Modules", "enabled": True, "tech": "Terraform",
            "link": None, "date": None, "bullets": ["Wrote Terraform modules."],
        }],
    }
    jd = {"title": "Engineer", "skills": [
        {"skill_name": "Terraform", "requirement_level": "required"},
    ]}
    rows = layers.resolve_evidence(
        normalize_jd(jd), index_resume(resume, as_of=AS_OF),
        SkillMatcher(cfg), cfg, as_of=AS_OF,
    )
    tf = rows[0]
    assert tf.placement == "skills_list_only" and tf.fix_hint == "dual_place"
    assert tf.recency_weight is None


def test_tf_idf_prose_does_not_upgrade_tensorflow_placement():
    # "TF-IDF" normalizes to "tf idf"; the "tf" alias must NOT prose-match it,
    # so a skills-list TensorFlow with only TF-IDF prose nearby stays
    # skills_list_only with the legitimate dual_place hint
    cfg = load_config()
    resume = {
        "contact": {"name": "J", "email": "j@x.com", "phone": "1"},
        "summary": "Engineer.",
        "skills": [{"category": "ML", "items": ["TensorFlow"]}],
        "experience": [{
            "company": "NowCo", "role": "Engineer", "location": "Remote",
            "start_date": "Jan 2024", "end_date": None, "enabled": True,
            "bullets": ["Implemented TF-IDF vectorization for search ranking."],
        }],
    }
    jd = {"title": "Engineer", "skills": [
        {"skill_name": "TensorFlow", "requirement_level": "required"},
    ]}
    rows = layers.resolve_evidence(
        normalize_jd(jd), index_resume(resume, as_of=AS_OF),
        SkillMatcher(cfg), cfg, as_of=AS_OF,
    )
    tf = rows[0]
    assert tf.matched and tf.placement == "skills_list_only"
    assert tf.fix_hint == "dual_place"
    assert tf.evidence_entries == []


def test_prose_only_alias_reports_found_form():
    # prose-only match via an alias form must report the form actually found
    cfg = load_config()
    resume = {
        "contact": {"name": "J", "email": "j@x.com", "phone": "1"},
        "summary": "Engineer.",
        "skills": [],
        "experience": [{
            "company": "NowCo", "role": "Engineer", "location": "Remote",
            "start_date": "Jan 2024", "end_date": None, "enabled": True,
            "bullets": ["Managed k8s clusters in production."],
        }],
    }
    jd = {"title": "Engineer", "skills": [
        {"skill_name": "Kubernetes", "requirement_level": "required"},
    ]}
    rows = layers.resolve_evidence(
        normalize_jd(jd), index_resume(resume, as_of=AS_OF),
        SkillMatcher(cfg), cfg, as_of=AS_OF,
    )
    k8s = rows[0]
    assert k8s.matched and k8s.match_form == "alias" and k8s.matched_term == "k8s"


def test_prose_exact_preferred_over_alias_across_entries():
    # first entry hits an alias form, a later entry hits the exact token:
    # the row must report the exact hit
    cfg = load_config()
    resume = {
        "contact": {"name": "J", "email": "j@x.com", "phone": "1"},
        "summary": "Engineer.",
        "skills": [],
        "experience": [
            {
                "company": "AliasCo", "role": "Engineer", "location": "Remote",
                "start_date": "Jan 2024", "end_date": None, "enabled": True,
                "bullets": ["Deployed on Amazon Web Services infrastructure."],
            },
            {
                "company": "ExactCo", "role": "Engineer", "location": "Remote",
                "start_date": "Jan 2020", "end_date": "Dec 2023", "enabled": True,
                "bullets": ["Built AWS data pipelines."],
            },
        ],
    }
    jd = {"title": "Engineer", "skills": [
        {"skill_name": "AWS", "requirement_level": "required"},
    ]}
    rows = layers.resolve_evidence(
        normalize_jd(jd), index_resume(resume, as_of=AS_OF),
        SkillMatcher(cfg), cfg, as_of=AS_OF,
    )
    aws = rows[0]
    assert aws.matched and aws.match_form == "exact" and aws.matched_term == "aws"
    assert len(aws.evidence_entries) == 2


def test_future_end_date_recency_clamped():
    # resume_indexer can emit last_date > as_of (future end date); the recency
    # weight must clamp to 1.0 — never exceed it, never raise.
    cfg = load_config()
    resume = {
        "contact": {"name": "J", "email": "j@x.com", "phone": "1"},
        "summary": "Engineer.",
        "skills": [],
        "experience": [{
            "company": "FutureCo", "role": "Engineer", "location": "Remote",
            "start_date": "Jan 2025", "end_date": "Dec 2027", "enabled": True,
            "bullets": ["Built pipelines in Kotlin."],
        }],
    }
    jd = {"title": "Engineer", "skills": [
        {"skill_name": "Kotlin", "requirement_level": "required"},
    ]}
    rows = layers.resolve_evidence(
        normalize_jd(jd), index_resume(resume, as_of=AS_OF),
        SkillMatcher(cfg), cfg, as_of=AS_OF,
    )
    kotlin = rows[0]
    assert kotlin.matched and kotlin.placement == "experience_only"
    assert kotlin.recency_weight == 1.0


def test_l1_keyword_score_weights_required_higher():
    rows, cfg = _evidence()
    score = layers.l1_keyword(rows, cfg)
    assert 0.0 < score < 1.0
    # dropping a required match must hurt more than dropping a preferred one
    without_python = [r for r in rows if r.jd_skill != "Python"]
    without_docker = [r for r in rows if r.jd_skill != "Docker"]
    assert layers.l1_keyword(without_python, cfg) < layers.l1_keyword(without_docker, cfg)


def test_l2_placement_recency_in_unit_range():
    rows, cfg = _evidence()
    assert 0.0 <= layers.l2_placement_recency(rows, cfg) <= 1.0


def test_l2_all_dual_current_exact_is_exactly_one():
    # every JD skill exact-matched, dual-placed, in a current role -> l2 == 1.0
    # (locks the numerator/denominator symmetry)
    cfg = load_config()
    resume = {
        "contact": {"name": "J", "email": "j@x.com", "phone": "1"},
        "summary": "Engineer.",
        "skills": [{"category": "Core", "items": ["Python", "SQL"]}],
        "experience": [{
            "company": "NowCo", "role": "Engineer", "location": "Remote",
            "start_date": "Jan 2024", "end_date": None, "enabled": True,
            "bullets": ["Used Python and SQL daily."],
        }],
    }
    jd = {"title": "Engineer", "skills": [
        {"skill_name": "Python", "requirement_level": "required"},
        {"skill_name": "SQL", "requirement_level": "preferred"},
    ]}
    rows = layers.resolve_evidence(
        normalize_jd(jd), index_resume(resume, as_of=AS_OF),
        SkillMatcher(cfg), cfg, as_of=AS_OF,
    )
    assert layers.l2_placement_recency(rows, cfg) == 1.0


def test_l3_title_direct():
    profile = normalize_jd(SAMPLE_JD)
    index = index_resume(SAMPLE_RESUME, as_of=AS_OF)
    tier, score = layers.l3_title(profile, index, load_config())
    # "Senior Data Scientist" vs recent role "Data Scientist" -> direct (seniority stripped)
    assert tier == "direct" and score == 1.0


def test_l3_title_adjacent():
    cfg = load_config()
    profile = normalize_jd(SAMPLE_JD)  # role_category "data_scientist"
    resume = copy.deepcopy(SAMPLE_RESUME)
    resume["experience"][0]["role"] = "Applied Scientist"  # family member, not the JD title
    resume["summary"] = "Scientist with production ML experience."
    tier, score = layers.l3_title(profile, index_resume(resume, as_of=AS_OF), cfg)
    assert tier == "adjacent" and score == cfg.weights["title_credit"]["adjacent"]


def test_l3_title_none():
    cfg = load_config()
    profile = normalize_jd(SAMPLE_JD)
    resume = copy.deepcopy(SAMPLE_RESUME)
    resume["experience"][0]["role"] = "Software Engineer"
    resume["summary"] = "Engineer who ships."
    tier, score = layers.l3_title(profile, index_resume(resume, as_of=AS_OF), cfg)
    assert tier == "none" and score == 0.0


def test_l3_title_no_cross_word_false_positive():
    # "ML Engineer" must not match inside "XML engineering" — word boundaries
    cfg = load_config()
    profile = normalize_jd(dict(SAMPLE_JD, title="ML Engineer", role_category="ai_ml_engineer"))
    resume = copy.deepcopy(SAMPLE_RESUME)
    resume["experience"][0]["role"] = "Accountant"
    resume["summary"] = "Built XML engineering pipelines."
    tier, score = layers.l3_title(profile, index_resume(resume, as_of=AS_OF), cfg)
    assert tier == "none" and score == 0.0


def test_l3_title_direct_via_summary_with_boundaries():
    # boundary check must still allow the JD title inside a longer summary phrase
    cfg = load_config()
    profile = normalize_jd(SAMPLE_JD)
    resume = copy.deepcopy(SAMPLE_RESUME)
    resume["experience"][0]["role"] = "Accountant"
    resume["summary"] = "Senior data scientist consultant with ML background."
    tier, score = layers.l3_title(profile, index_resume(resume, as_of=AS_OF), cfg)
    assert tier == "direct" and score == 1.0


@pytest.mark.parametrize(
    "jd_title",
    ["Data Scientist I", "Data Scientist II", "Data Scientist III",
     "Data Scientist IV", "Data Scientist V",
     "Data Scientist 1", "Data Scientist 3", "Data Scientist 5",
     "Senior Data Scientist", "Staff Data Scientist", "Principal Data Scientist",
     "Associate Data Scientist", "Entry Level Data Scientist", "Jr Data Scientist"],
)
def test_l3_title_direct_across_every_level_spelling(jd_title):
    """A level suffix is how the EMPLOYER spells the ladder, not a different job.

    Regression: the seniority list carried roman i/ii/iii but neither iv/v nor
    the arabic forms, so "Data Scientist IV" fell to `adjacent` against a
    "Data Scientist" resume. Title is 20% of the composite and direct/adjacent
    is a 0.5 credit gap, so that spelling alone cost 10 composite points.
    """
    cfg = load_config()
    profile = normalize_jd(dict(SAMPLE_JD, title=jd_title))
    resume = copy.deepcopy(SAMPLE_RESUME)
    resume["experience"][0]["role"] = "Data Scientist"
    resume["summary"] = "Builds models."
    tier, score = layers.l3_title(profile, index_resume(resume, as_of=AS_OF), cfg)
    assert (tier, score) == ("direct", 1.0)


@pytest.mark.parametrize(
    "jd_title", ["Engineering Manager", "Data Science Manager", "Director of Data Science"]
)
def test_l3_title_management_is_not_a_rank_marker(jd_title):
    """`manager`/`director` name a DIFFERENT job and must never be stripped.

    They live in `role_titles._MANAGEMENT_PATTERN` (display labels only), not in
    the shared seniority vocabulary. If they leaked into it, an individual-
    contributor resume would score `direct` against a people-management JD.
    """
    cfg = load_config()
    profile = normalize_jd(dict(SAMPLE_JD, title=jd_title))
    resume = copy.deepcopy(SAMPLE_RESUME)
    resume["experience"][0]["role"] = "Data Scientist"
    resume["summary"] = "Builds models."
    tier, _ = layers.l3_title(profile, index_resume(resume, as_of=AS_OF), cfg)
    assert tier != "direct"


def test_seniority_vocabulary_is_hashed_into_config_version():
    """An input that moves scores must move `config_version`.

    `load_config` hashes an explicit dict, not the data directory, so a new YAML
    key is invisible to the hash until added by hand. Left out, scores would
    shift while the version stayed fixed and `compare()`'s cross-version guard
    would wave through incomparable rows instead of offering a re-score.
    """
    from unittest.mock import patch

    load_config.cache_clear()
    baseline = load_config().version
    try:
        with patch.object(
            role_categories, "seniority_terms", return_value=("senior", "sr")
        ):
            load_config.cache_clear()
            assert load_config().version != baseline
    finally:
        load_config.cache_clear()


def test_l4_gate_no_warning_within_tolerance():
    # fixture shows ~5.0 dated years vs years_experience_min=5 -> inside the
    # 0.25 tolerance, so no warning
    profile = normalize_jd(SAMPLE_JD)
    index = index_resume(SAMPLE_RESUME, as_of=AS_OF)
    assert layers.l4_gate(profile, index) == []


def test_l4_gate_warns_when_clearly_short():
    jd = dict(SAMPLE_JD, years_experience_min=8)
    profile = normalize_jd(jd)
    index = index_resume(SAMPLE_RESUME, as_of=AS_OF)
    warnings = layers.l4_gate(profile, index)
    assert len(warnings) == 1
    assert "8" in warnings[0] and "5.0" in warnings[0]


def test_l5_format_lint():
    rows, cfg = _evidence()
    index = index_resume(SAMPLE_RESUME, as_of=AS_OF)
    score, flags = layers.l5_format(index, rows, cfg)
    assert 0.0 <= score <= 1.0
    assert isinstance(flags, list)


def test_l5_flags_uncorroborated_skills_stuffing():
    cfg = load_config()
    resume = copy.deepcopy(SAMPLE_RESUME)
    # 3 of 4 skills items have zero corroboration anywhere -> over the 0.5 cap
    resume["skills"] = [{"category": "Stuffed", "items": ["Python", "Cobol", "Fortran", "Pascal"]}]
    index = index_resume(resume, as_of=AS_OF)
    rows = layers.resolve_evidence(
        normalize_jd(SAMPLE_JD), index, SkillMatcher(cfg), cfg, as_of=AS_OF,
    )
    score, flags = layers.l5_format(index, rows, cfg)
    assert score < 1.0
    assert any("no supporting evidence" in f for f in flags)


# --- semantic evidence stage --------------------------------------------------
# The fake embedder (autouse) maps a handful of known strings to 4-D vectors;
# everything else gets the 0.0-cosine default. Entry text is normalized, so the
# resume bullets below are written to normalize to the fake's known keys.


def _resolve(jd, resume, cfg=None):
    cfg = cfg or load_config()
    return layers.resolve_evidence(
        normalize_jd(jd), index_resume(resume, as_of=AS_OF),
        SkillMatcher(cfg), cfg, as_of=AS_OF,
    ), cfg


def test_semantic_match_via_entry_chunk():
    # "Statistical Modeling" is not in skills or prose lexically, but a dated
    # entry's text ("statistical analysis") shares the token "statistical" (anchor
    # gate ok) AND embeds close (cos 0.96 >= 0.60) -> semantic match,
    # experience_only. matched_term is None (C3: no raw fragment surfaced).
    resume = {
        "contact": {"name": "J", "email": "j@x.com", "phone": "1"},
        "summary": "Engineer.",
        "skills": [{"category": "Core", "items": ["Python"]}],
        # role left blank so the indexer's entry text normalizes to exactly the
        # fake's known key (role would otherwise be prepended).
        "experience": [{
            "company": "NowCo", "role": "", "location": "Remote",
            "start_date": "Jan 2024", "end_date": None, "enabled": True,
            "bullets": ["statistical analysis"],
        }],
    }
    jd = {"title": "Engineer", "skills": [
        {"skill_name": "Statistical Modeling", "requirement_level": "required"},
    ]}
    rows, cfg = _resolve(jd, resume)
    stat = _row(rows, "Statistical Modeling")
    assert stat.matched and stat.match_form == "semantic"
    assert stat.placement == "experience_only"
    assert stat.fix_hint == "mirror_wording"
    credit = cfg.weights["semantic"]["match_credit"]
    assert stat.match_credit == credit
    assert stat.matched_term is None  # C3: no raw candidate fragment as evidence
    assert stat.evidence_entries == ["NowCo — "]
    # contribution = req(2.0) * credit * experience_only(1.0) * recency(current=1.0)
    assert stat.contribution == round(2.0 * credit * 1.0 * 1.0, 4)
    assert stat.recency_weight == 1.0


def test_semantic_match_via_skills_item():
    # skills-list item shares a token with the JD term (anchor ok) and embeds
    # close, but is not a lexical match -> semantic hit attributed to the skills
    # list: skills_list_only, recency None, matched_term None.
    resume = {
        "contact": {"name": "J", "email": "j@x.com", "phone": "1"},
        "summary": "Engineer.",
        "skills": [{"category": "Analytics", "items": ["statistical analysis"]}],
        "experience": [{
            "company": "NowCo", "role": "Engineer", "location": "Remote",
            "start_date": "Jan 2024", "end_date": None, "enabled": True,
            "bullets": ["did unrelated work"],
        }],
    }
    jd = {"title": "Engineer", "skills": [
        {"skill_name": "Statistical Modeling", "requirement_level": "required"},
    ]}
    rows, cfg = _resolve(jd, resume)
    stat = _row(rows, "Statistical Modeling")
    assert stat.matched and stat.match_form == "semantic"
    assert stat.placement == "skills_list_only"
    assert stat.recency_weight is None
    assert stat.matched_term is None  # C3
    assert stat.match_credit == cfg.weights["semantic"]["match_credit"]


def test_semantic_zero_overlap_blocked_by_anchor_gate():
    # "Kubernetes" <-> "container orchestration experience": cos 0.96 (above
    # threshold) but ZERO shared tokens -> anchor gate blocks the semantic path.
    # With no adjacency skills item present either, the skill stays absent — the
    # gate (not the threshold) is what suppresses this false positive.
    resume = {
        "contact": {"name": "J", "email": "j@x.com", "phone": "1"},
        "summary": "Engineer.",
        "skills": [{"category": "Core", "items": ["Python"]}],
        "experience": [{
            "company": "NowCo", "role": "", "location": "Remote",
            "start_date": "Jan 2024", "end_date": None, "enabled": True,
            "bullets": ["container orchestration experience"],
        }],
    }
    jd = {"title": "Engineer", "skills": [
        {"skill_name": "Kubernetes", "requirement_level": "required"},
    ]}
    rows, _ = _resolve(jd, resume)
    k8s = _row(rows, "Kubernetes")
    assert not k8s.matched and k8s.fix_hint == "absent"


def test_generic_only_anchor_below_floor_blocked():
    # "Data Mining" anchors only generic tokens ("data", "mining"->non-generic?
    # 'mining' is NOT in the generic set, but the candidate below shares only
    # 'data'). The candidate "data pipeline chores" shares only "data" (generic)
    # and embeds at cos 0.60 -> clears the 0.60 base but NOT the 0.82 generic floor
    # -> blocked. This is the Data-Structures->data-analyst-bullet class the
    # two-threshold rule exists to kill.
    resume = {
        "contact": {"name": "J", "email": "j@x.com", "phone": "1"},
        "summary": "Engineer.",
        "skills": [{"category": "Core", "items": ["data pipeline chores"]}],
        "experience": [{
            "company": "NowCo", "role": "", "location": "Remote",
            "start_date": "Jan 2024", "end_date": None, "enabled": True,
            "bullets": ["did work"],
        }],
    }
    jd = {"title": "Engineer", "skills": [
        {"skill_name": "Data Mining", "requirement_level": "required"},
    ]}
    rows, _ = _resolve(jd, resume)
    dm = _row(rows, "Data Mining")
    assert not dm.matched and dm.fix_hint == "absent"


def test_generic_only_anchor_above_floor_hits():
    # "Data Analysis" (generic-only anchors) <-> "statistical analysis": shares
    # only "analysis" (generic) BUT cos 0.96 >= 0.82 generic floor -> hit. A real
    # variant the rule must keep.
    resume = {
        "contact": {"name": "J", "email": "j@x.com", "phone": "1"},
        "summary": "Engineer.",
        "skills": [{"category": "Analytics", "items": ["statistical analysis"]}],
        "experience": [{
            "company": "NowCo", "role": "Engineer", "location": "Remote",
            "start_date": "Jan 2024", "end_date": None, "enabled": True,
            "bullets": ["did work"],
        }],
    }
    jd = {"title": "Engineer", "skills": [
        {"skill_name": "Data Analysis", "requirement_level": "required"},
    ]}
    rows, _ = _resolve(jd, resume)
    da = _row(rows, "Data Analysis")
    assert da.matched and da.match_form == "semantic"
    assert da.placement == "skills_list_only"


def test_non_generic_anchor_below_generic_floor_still_hits():
    # "Statistical Modeling" <-> "statistical analysis" shares "statistical"
    # (NON-generic), so the base 0.60 floor applies even though cos 0.8 < the 0.82
    # generic floor -> hit. Proves the rule only tightens generic-ONLY candidates.
    resume = {
        "contact": {"name": "J", "email": "j@x.com", "phone": "1"},
        "summary": "Engineer.",
        "skills": [{"category": "Analytics", "items": ["statistical analysis"]}],
        "experience": [{
            "company": "NowCo", "role": "Engineer", "location": "Remote",
            "start_date": "Jan 2024", "end_date": None, "enabled": True,
            "bullets": ["did work"],
        }],
    }
    jd = {"title": "Engineer", "skills": [
        {"skill_name": "Statistical Modeling", "requirement_level": "required"},
    ]}
    rows, _ = _resolve(jd, resume)
    stat = _row(rows, "Statistical Modeling")
    assert stat.matched and stat.match_form == "semantic"


def test_zero_overlap_reformulation_caught_by_adjacency():
    # The genuine kubernetes <-> "container orchestration" reformulation lives in
    # adjacency.yaml, so a resume skills item "container orchestration" credits
    # Kubernetes deterministically (adjacent), independent of the embedder.
    resume = {
        "contact": {"name": "J", "email": "j@x.com", "phone": "1"},
        "summary": "Engineer.",
        "skills": [{"category": "Infra", "items": ["container orchestration"]}],
        "experience": [{
            "company": "NowCo", "role": "Engineer", "location": "Remote",
            "start_date": "Jan 2024", "end_date": None, "enabled": True,
            "bullets": ["ran systems"],
        }],
    }
    jd = {"title": "Engineer", "skills": [
        {"skill_name": "Kubernetes", "requirement_level": "required"},
    ]}
    rows, _ = _resolve(jd, resume)
    k8s = _row(rows, "Kubernetes")
    assert k8s.matched and k8s.match_form == "adjacent"
    assert k8s.matched_term == "container orchestration"
    assert k8s.fix_hint == "adjacent_available"


def test_semantic_miss_falls_through_to_adjacency():
    # Snowflake has no semantic neighbour here (all texts unrelated -> 0.0 cosine),
    # so it must still land the bigquery adjacency exactly as before.
    resume = {
        "contact": {"name": "J", "email": "j@x.com", "phone": "1"},
        "summary": "Engineer.",
        "skills": [{"category": "Data", "items": ["bigquery"]}],
        "experience": [{
            "company": "NowCo", "role": "Engineer", "location": "Remote",
            "start_date": "Jan 2024", "end_date": None, "enabled": True,
            "bullets": ["ran queries"],
        }],
    }
    jd = {"title": "Engineer", "skills": [
        {"skill_name": "Snowflake", "requirement_level": "required"},
    ]}
    rows, _ = _resolve(jd, resume)
    snow = _row(rows, "Snowflake")
    assert snow.matched and snow.match_form == "adjacent"
    assert snow.fix_hint == "adjacent_available"


def test_lexical_hit_never_invokes_embeddings(monkeypatch):
    # A clean lexical hit must short-circuit before the semantic stage: the
    # embedder is never called for it.
    calls: list = []

    def spy(texts):
        calls.append(list(texts))
        return fake_embed_texts(texts)

    monkeypatch.setattr(embeddings, "embed_texts", spy)
    resume = {
        "contact": {"name": "J", "email": "j@x.com", "phone": "1"},
        "summary": "Engineer.",
        "skills": [{"category": "Core", "items": ["Python"]}],
        "experience": [{
            "company": "NowCo", "role": "Engineer", "location": "Remote",
            "start_date": "Jan 2024", "end_date": None, "enabled": True,
            "bullets": ["Wrote Python daily."],
        }],
    }
    jd = {"title": "Engineer", "skills": [
        {"skill_name": "Python", "requirement_level": "required"},
    ]}
    rows, _ = _resolve(jd, resume)
    assert _row(rows, "Python").match_form == "exact"
    assert calls == []  # lexical hit short-circuited: embedder untouched


def test_l6_semantic_fit_mean_of_per_line_maxima():
    # 2 JD lines x 2 resume chunks, hand-computed against the fake vectors.
    #   JD line "machine learning": max(cos vs chunk1, cos vs chunk2)
    #   JD line "kubernetes":       max(cos vs chunk1, cos vs chunk2)
    # chunks (index summary + one entry text):
    #   summary "shipped ml models to production" -> (0.96, 0.28, ...)
    #   entry   "container orchestration experience" -> (0.28, 0.96, ...)
    #   cos("machine learning", summary) = 0.96 ; cos("machine learning", entry) = 0.28  -> max 0.96
    #   cos("kubernetes", summary)       = 0.28 ; cos("kubernetes", entry)       = 0.96  -> max 0.96
    #   mean(0.96, 0.96) = 0.96
    from app.services.ats.resume_indexer import ResumeIndex, IndexedEntry

    profile = normalize_jd({
        "title": "X",
        "skills": [{"skill_name": "Python", "requirement_level": "required"}],
        "responsibilities": ["Machine Learning"],
        "qualifications": ["Kubernetes"],
    })
    index = ResumeIndex(
        skills_items=[], summary="shipped ml models to production",
        entries=[IndexedEntry(
            section="experience", index=0, label="E",
            text="container orchestration experience",
            last_date=None, is_current=True, date_parse_ok=True,
        )],
        recent_role="", contact_ok=True, total_experience_years=1.0,
        sections_present={},
    )
    assert layers.l6_semantic_fit_coverage(profile, index)[0] == pytest.approx(0.96)


def test_l6_semantic_fit_zero_when_no_jd_lines():
    from app.services.ats.resume_indexer import ResumeIndex
    # requirement_lines falls back to skill names, so force truly-empty lines by
    # constructing a profile whose requirement_lines are all blank.
    profile = normalize_jd({
        "title": "X",
        "skills": [{"skill_name": "Python", "requirement_level": "required"}],
        "responsibilities": ["   "], "qualifications": [""],
    })
    # fallback kicks in -> ["Python"]; blank-only should still fall back, so to get
    # a truly empty set we override requirement_lines directly.
    object.__setattr__(profile, "requirement_lines", [])
    index = ResumeIndex(
        skills_items=[], summary="anything", entries=[],
        recent_role="", contact_ok=True, total_experience_years=0.0, sections_present={},
    )
    assert layers.l6_semantic_fit_coverage(profile, index)[0] == 0.0


def test_l6_semantic_fit_zero_when_no_resume_chunks():
    from app.services.ats.resume_indexer import ResumeIndex
    profile = normalize_jd({
        "title": "X",
        "skills": [{"skill_name": "Python", "requirement_level": "required"}],
        "responsibilities": ["Machine Learning"],
    })
    index = ResumeIndex(
        skills_items=[], summary="", entries=[],
        recent_role="", contact_ok=True, total_experience_years=0.0, sections_present={},
    )
    assert layers.l6_semantic_fit_coverage(profile, index)[0] == 0.0


# --- extra-section evidence tiering (findings F#8, F#9, F#12) -----------------


def _extras_resume(*, skills=None, projects=None, extra_sections):
    return {
        "contact": {"name": "J", "email": "j@x.com", "phone": "1"},
        "summary": "Engineer.",
        "skills": skills or [],
        "experience": [],
        "projects": projects or [],
        "extra_sections": extra_sections,
    }


def test_extra_only_lexical_match_gets_extra_only_fix_hint():
    # F#8: a JD skill whose ONLY evidence is an enabled custom section resolves to
    # extra_only and now carries fix_hint "extra_only" (was None -> silently
    # dropped from the gap workflow despite real placement headroom).
    load_config()
    resume = _extras_resume(extra_sections=[{
        "key": "publications", "title": "Publications", "type": "entries",
        "enabled": True,
        "entries": [{"heading": "Kafka at scale", "enabled": True,
                     "bullets": ["Ran Kafka clusters."]}],
    }])
    jd = {"title": "Engineer", "skills": [
        {"skill_name": "Kafka", "requirement_level": "required"},
    ]}
    rows, _ = _resolve(jd, resume)
    kafka = _row(rows, "Kafka")
    assert kafka.matched and kafka.match_form == "exact"
    assert kafka.placement == "extra_only"
    assert kafka.fix_hint == "extra_only"
    assert kafka.recency_weight is None  # no dated evidence


def test_undated_core_plus_extra_takes_stronger_extra_tier_by_multiplier():
    # F#9: a skill with BOTH an undated core project (undated_only=0.4) AND a
    # custom section (extra_only=0.8) is credited at the STRONGER tier chosen by
    # effective multiplier (deterministic max), not lexical branch order. Both
    # sources are attributed as evidence.
    cfg = load_config()
    resume = _extras_resume(
        projects=[{"name": "Infra", "enabled": True, "tech": "Kafka", "link": None,
                   "date": None, "bullets": ["Wrote Kafka consumers."]}],
        extra_sections=[{
            "key": "talks", "title": "Talks", "type": "bullets", "enabled": True,
            "bullets": ["Presented Kafka best practices."],
        }],
    )
    jd = {"title": "Engineer", "skills": [
        {"skill_name": "Kafka", "requirement_level": "required"},
    ]}
    rows, cfg = _resolve(jd, resume)
    kafka = _row(rows, "Kafka")
    assert kafka.placement == "extra_only"
    assert kafka.fix_hint == "extra_only"
    assert set(kafka.evidence_entries) == {"Infra", "Talks"}
    extra_mult = cfg.weights["extra_section_evidence"]["placement_multiplier"]
    assert kafka.contribution == round(2.0 * 1.0 * extra_mult * 1.0, 4)


def test_dated_core_plus_extra_stays_experience_only():
    # F#9: dated core evidence (experience_only=1.0) beats the extra tier (0.8),
    # so a dated project + custom-section repeat stays experience_only with a real
    # recency claim — the stronger single source wins, single-source semantics
    # preserved.
    load_config()
    resume = _extras_resume(
        projects=[{"name": "Infra", "enabled": True, "tech": "Kafka", "link": None,
                   "date": "Jan 2025", "bullets": ["Wrote Kafka consumers."]}],
        extra_sections=[{
            "key": "talks", "title": "Talks", "type": "bullets", "enabled": True,
            "bullets": ["Presented Kafka best practices."],
        }],
    )
    jd = {"title": "Engineer", "skills": [
        {"skill_name": "Kafka", "requirement_level": "required"},
    ]}
    rows, _ = _resolve(jd, resume)
    kafka = _row(rows, "Kafka")
    assert kafka.placement == "experience_only"
    assert kafka.recency_weight is not None
    assert set(kafka.evidence_entries) == {"Infra", "Talks"}


def test_skills_item_plus_bullets_extra_is_not_dual():
    # F#12: a JD skill in the skills list AND repeated in a flat bullets extra must
    # NOT be promoted to dual (which needs a DATED core entry). The extra is
    # undated, so placement is extra_only, never dual.
    load_config()
    resume = _extras_resume(
        skills=[{"category": "Core", "items": ["Docker"]}],
        extra_sections=[{
            "key": "notes", "title": "Notes", "type": "bullets", "enabled": True,
            "bullets": ["Docker everywhere."],
        }],
    )
    jd = {"title": "Engineer", "skills": [
        {"skill_name": "Docker", "requirement_level": "required"},
    ]}
    rows, _ = _resolve(jd, resume)
    docker = _row(rows, "Docker")
    assert docker.placement != "dual"
    assert docker.placement == "extra_only"
    assert docker.fix_hint == "extra_only"


def test_bullets_extra_does_not_corroborate_skills_stuffing_lint():
    # F#12: an unstructured flat-bullets custom section must NOT rescue the l5
    # stuffing lint. A skills list with 3/4 uncorroborated items still flags, and
    # the composite is IDENTICAL to having no extras at all (the bullets extra did
    # not launder the items into "corroborated").
    from app.services.ats import score_resume

    base = copy.deepcopy(SAMPLE_RESUME)
    base["skills"] = [{"category": "Stuffed", "items": ["Python", "Cobol", "Fortran", "Pascal"]}]
    with_extra = copy.deepcopy(base)
    with_extra["extra_sections"] = [{
        "key": "keywords", "title": "Keywords", "type": "bullets", "enabled": True,
        "bullets": ["Cobol Fortran Pascal specialist"],  # repeats 3 stuffed items
    }]

    index = index_resume(with_extra, as_of=AS_OF)
    rows = layers.resolve_evidence(
        normalize_jd(SAMPLE_JD), index, SkillMatcher(load_config()), load_config(), as_of=AS_OF,
    )
    _, flags = layers.l5_format(index, rows, load_config())
    assert any("no supporting evidence" in f for f in flags)  # lint still fires

    scored_base = score_resume(base, SAMPLE_JD, as_of=AS_OF)
    scored_extra = score_resume(with_extra, SAMPLE_JD, as_of=AS_OF)
    assert scored_extra.subscores["format"] == scored_base.subscores["format"]
    assert scored_extra.composite == scored_base.composite


def test_structured_entries_extra_still_corroborates_skills_lint():
    # F#12 is scoped to the flat `bullets` channel: a STRUCTURED `entries` custom
    # section is allowed to corroborate skills-list items (SYSTEM.md §4 — extra
    # evidence may affect skills-item corroboration). Here a stuffed skills item
    # gains corroboration from an entries-extra, so the lint's uncorroborated
    # share drops vs the bullets/no-extra case.
    cfg = load_config()
    resume = _extras_resume(
        skills=[{"category": "Stuffed", "items": ["Python", "Cobol", "Fortran", "Pascal"]}],
        extra_sections=[{
            "key": "oss", "title": "Open Source", "type": "entries", "enabled": True,
            "entries": [{"heading": "Cobol modernization", "enabled": True,
                         "bullets": ["Ported Fortran and Pascal jobs."]}],
        }],
    )
    index = index_resume(resume, as_of=AS_OF)
    assert not any(e.is_keyword_channel for e in index.entries)  # entries-extra, not flat
    rows = layers.resolve_evidence(
        normalize_jd(SAMPLE_JD), index, SkillMatcher(cfg), cfg, as_of=AS_OF,
    )
    # Cobol/Fortran/Pascal now appear in a structured entry -> corroborated, so the
    # uncorroborated share falls under the 0.5 cap and the lint does NOT fire.
    _, flags = layers.l5_format(index, rows, cfg)
    assert not any("no supporting evidence" in f for f in flags)


def test_disabled_entry_text_is_not_a_semantic_candidate():
    # The only ML-adjacent text lives in a DISABLED entry -> invisible to the
    # semantic stage exactly as to the lexical stages. Skill stays absent.
    resume = {
        "contact": {"name": "J", "email": "j@x.com", "phone": "1"},
        "summary": "Engineer.",
        "skills": [{"category": "Core", "items": ["Python"]}],
        "experience": [{
            "company": "HiddenCo", "role": "Engineer", "location": "Remote",
            "start_date": "Jan 2024", "end_date": None, "enabled": False,
            "bullets": ["shipped ml models to production"],
        }],
    }
    jd = {"title": "Engineer", "skills": [
        {"skill_name": "Machine Learning", "requirement_level": "required"},
    ]}
    rows, _ = _resolve(jd, resume)
    ml = _row(rows, "Machine Learning")
    assert not ml.matched and ml.fix_hint == "absent"


def test_title_family_keys_are_real_role_categories():
    """The L3 "adjacent" tier must be reachable with values production stores.

    Regression guard for a bug that survived because the fixtures hid it: the
    families file was keyed by title-cased domain nouns ("Data Science") while
    Job.role_category holds snake_case keys ("data_scientist"), so
    cfg.title_families.get(role_category) never matched and the whole adjacent
    tier was dead outside tests. Both vocabularies now come from
    ats/data/role_categories.yaml; this pins them together.
    """
    from app.services import role_categories

    cfg = load_config()
    valid = set(role_categories.all_keys())
    assert cfg.title_families, "no title families loaded"
    unknown = sorted(set(cfg.title_families) - valid)
    assert not unknown, f"family keys are not storable role_category values: {unknown}"
    # and the reverse: every declared category can be looked up
    for key in role_categories.keys():
        assert key in cfg.title_families, f"{key} has no adjacent-title list"


@pytest.mark.parametrize(
    "title,core",
    [
        # Leading rank — still stripped, the tech cases that already worked.
        ("Associate Data Scientist", "data scientist"),
        ("Staff Engineer", "engineer"),
        ("Lead Engineer", "engineer"),
        ("Principal Consultant", "consultant"),
        ("Senior Staff Engineer", "engineer"),
        # SUFFIX rank words are head nouns — the regression this pins.
        ("Tech Lead", "tech lead"),
        ("Team Lead", "team lead"),
        ("Data Lead", "data lead"),
        ("Sales Associate", "sales associate"),
        ("Research Associate", "research associate"),
        # Never reduce to nothing.
        ("Senior Associate", "associate"),
        ("Lead", "lead"),
        ("Senior", "senior"),
        # Management is not a rank and was never stripped here.
        ("Engineering Manager", "engineering manager"),
    ],
)
def test_strip_seniority_prefix_vs_suffix(title, core):
    """`associate`/`principal`/`staff`/`lead` are ranks when they LEAD a title
    and job nouns when they end one. Stripping them in the suffix position
    turned "Tech Lead" into "tech" — a core that matches nothing, so the title
    tier (0.20 of the composite) collapsed to `none` for an ordinary title."""
    assert layers._strip_seniority(title) == core


def test_suffix_rank_title_can_reach_direct():
    """End to end: the tier, not just the helper."""
    cfg = load_config()
    profile = normalize_jd(dict(SAMPLE_JD, title="Tech Lead"))
    resume = copy.deepcopy(SAMPLE_RESUME)
    resume["experience"][0]["role"] = "Tech Lead"
    resume["summary"] = "Builds things."
    tier, score = layers.l3_title(profile, index_resume(resume, as_of=AS_OF), cfg)
    assert (tier, score) == ("direct", 1.0)


def test_select_placement_single_source_returns_that_tier():
    """The semantic path's classify() delegates here with exactly ONE evidence
    flag set; each single source must map to its own tier and multiplier. This
    pins the delegation contract that retired the second, parallel
    classification site (a tier added to one and not the other used to
    silently demote semantic matches)."""
    placements = {
        "dual": 1.5,
        "experience_only": 1.0,
        "skills_list_only": 0.4,
        "undated_only": 0.4,
    }
    kw = dict(
        placements=placements,
        extra_tier="extra_only",
        extra_mult=0.8,
        credential_tier="credential_only",
        credential_mult=0.5,
    )
    base = dict(skills_hit=False, has_dated=False, has_undated_core=False, has_extra=False)
    assert layers._select_placement(**{**base, "skills_hit": True}, **kw) == ("skills_list_only", 0.4)
    assert layers._select_placement(**{**base, "has_dated": True}, **kw) == ("experience_only", 1.0)
    assert layers._select_placement(**{**base, "has_undated_core": True}, **kw) == ("undated_only", 0.4)
    assert layers._select_placement(**{**base, "has_extra": True}, **kw) == ("extra_only", 0.8)
    assert layers._select_placement(**base, has_credential=True, **kw) == ("credential_only", 0.5)
