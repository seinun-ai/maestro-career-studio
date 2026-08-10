"""Phase-2 ATS evidence semantics for custom (extra) resume sections.

Enabled custom prose is now deterministic skill evidence under an explicit,
versioned, undated placement tier. The allow-list is intentionally narrow:
entry headings, subheadings and bullets plus bullet-section bullets. Display
titles, locations, links and dates remain non-evidence metadata.
"""
import copy
from datetime import date

import pytest

from app.schemas.resume import ResumeData
from app.services.ats import embeddings, score_resume
from app.services.ats.config import ENGINE_VERSION, AtsConfig, load_config
from app.services.ats.resume_indexer import index_resume
from app.services.gap_analysis import build_gaps
from tests.ats.fixtures import SAMPLE_JD, SAMPLE_RESUME, fake_embed_texts

AS_OF = date(2026, 7, 6)


@pytest.fixture(autouse=True)
def _fake_embedder(monkeypatch):
    monkeypatch.setattr(embeddings, "embed_texts", fake_embed_texts)


def _resume(extra_sections=None):
    return {
        "contact": {"name": "J", "email": "j@example.com", "phone": "1"},
        "summary": "Engineer.",
        "skills": [],
        "experience": [],
        "projects": [],
        "education": [{"institution": "School", "degree": "BS"}],
        "extra_sections": copy.deepcopy(extra_sections or []),
    }


def _jd(*skills):
    return {
        "title": "Engineer",
        "skills": [
            {"skill_name": skill, "requirement_level": "required"}
            for skill in skills
        ],
    }


def _row(result, skill):
    return next(row for row in result.skill_table if row["jd_skill"] == skill)


EVIDENCE_EXTRAS = [
    {
        "key": "publications",
        "title": "Kubernetes",  # title is deliberately NOT searchable
        "type": "entries",
        "enabled": True,
        "entries": [
            {
                "heading": "Salesforce Architecture",
                "subheading": "Snowflake Guild",
                "location": "Terraform",  # not searchable
                "date": "Jan 2026",  # ignored for recency
                "link": "https://example.com/pulumi",  # not searchable
                "enabled": True,
                "bullets": ["Shipped Docker workloads."],
            }
        ],
    },
    {
        "key": "awards",
        "title": "Awards",
        "type": "bullets",
        "enabled": True,
        "bullets": ["Named the Tableau community champion."],
    },
]


def test_enabled_extra_fields_contribute_at_configured_undated_tier():
    cfg = load_config()
    result = score_resume(
        _resume(EVIDENCE_EXTRAS),
        _jd("Salesforce", "Snowflake", "Docker", "Tableau", "Kubernetes", "Terraform"),
        as_of=AS_OF,
    )

    for skill in ("Salesforce", "Snowflake", "Docker", "Tableau"):
        row = _row(result, skill)
        assert row["matched"] is True
        assert row["placement"] == cfg.weights["extra_section_evidence"]["placement_tier"]
        assert row["last_used"] is None
        assert row["recency_weight"] is None
        assert row["contribution"] == round(
            cfg.weights["requirement_weights"]["required"]
            * cfg.weights["extra_section_evidence"]["placement_multiplier"],
            4,
        )

    # Config omits titles/locations/dates/links, so those strings cannot become
    # skill evidence merely because the renderer displays them.
    assert _row(result, "Kubernetes")["matched"] is False
    assert _row(result, "Terraform")["matched"] is False
    # Bumped 2.1.0 -> 2.1.1 by the post-phase-2 review fixes (F#8 extra_only
    # fix_hint, F#12 stuffing-lint scoping) which change emitted values for
    # extra-section resumes; the tier/multiplier assertions above are unchanged.
    assert result.engine_version == ENGINE_VERSION == "ats-2.5.0"
    assert result.config_version == cfg.version


def test_extra_section_scoring_is_deterministic():
    resume = _resume(EVIDENCE_EXTRAS)
    jd = _jd("Salesforce", "Snowflake", "Docker", "Tableau")
    first = score_resume(resume, jd, as_of=AS_OF)
    second = score_resume(copy.deepcopy(resume), copy.deepcopy(jd), as_of=AS_OF)
    assert first == second


def test_extra_chunks_participate_in_semantic_evidence_and_l6_fit():
    extras = [{
        "key": "research",
        "title": "Research",
        "type": "entries",
        "enabled": True,
        "entries": [{
            "heading": "Statistical analysis",
            "enabled": True,
            "bullets": [],
        }],
    }]
    jd = _jd("Statistical modeling")
    jd["responsibilities"] = ["Statistical modeling"]
    result = score_resume(_resume(extras), jd, as_of=AS_OF)
    row = _row(result, "Statistical modeling")
    assert row["matched"] is True
    assert row["match_form"] == "semantic"
    assert row["placement"] == "extra_only"
    assert row["evidence_entries"] == ["Statistical analysis"]
    assert row["contribution"] == pytest.approx(2.0 * 0.6 * 0.8)
    assert result.subscores["semantic_fit"] == pytest.approx(0.8)


def test_disabled_sections_and_entries_contribute_nothing():
    disabled = copy.deepcopy(EVIDENCE_EXTRAS)
    disabled[0]["entries"][0]["enabled"] = False
    disabled[1]["enabled"] = False
    jd = _jd("Salesforce", "Snowflake", "Docker", "Tableau")

    baseline = score_resume(_resume(), jd, as_of=AS_OF)
    with_disabled = score_resume(_resume(disabled), jd, as_of=AS_OF)

    assert with_disabled == baseline
    assert all(row["matched"] is False for row in with_disabled.skill_table)


def _core_only_no_extras_key():
    resume = copy.deepcopy(SAMPLE_RESUME)
    resume.pop("extra_sections", None)  # ensure the key is truly ABSENT
    return resume


def test_no_op_representations_score_byte_identically():
    # F#3: three representations carrying NO live extra evidence must produce a
    # byte-identical FULL AtsResult under the phase-2 engine — key absent, an
    # explicit empty list, and the canonical ResumeData round-trip (which always
    # materializes extra_sections). Restores the no-op coverage the phase-2
    # rewrite dropped.
    no_key = _core_only_no_extras_key()
    empty = {**no_key, "extra_sections": []}
    canonical = ResumeData.model_validate(no_key).model_dump(mode="json")
    assert canonical["extra_sections"] == []  # normalization materializes the key

    base = score_resume(no_key, SAMPLE_JD, as_of=AS_OF)
    assert score_resume(empty, SAMPLE_JD, as_of=AS_OF) == base
    assert score_resume(canonical, SAMPLE_JD, as_of=AS_OF) == base


def test_enabled_extras_never_shift_gate_title_or_section_presence():
    # F#11: enabled extras DO become keyword/semantic evidence (skill_table
    # shifts) — but must never move the structural signals: the experience-year
    # gate, title tier, format flags/section-presence, recent role, or tenure.
    # This is the enabled-path equivalent of the old byte-identical proof, which
    # now only holds field-wise (the extra_only tier deliberately moves keywords).
    core = _core_only_no_extras_key()
    withx = copy.deepcopy(core)
    withx["extra_sections"] = copy.deepcopy(EVIDENCE_EXTRAS)

    base = score_resume(core, SAMPLE_JD, as_of=AS_OF)
    ex = score_resume(withx, SAMPLE_JD, as_of=AS_OF)

    assert ex.skill_table != base.skill_table  # extras changed keyword evidence...
    # ...but NOT these structural, non-extra signals:
    assert ex.gate_warnings == base.gate_warnings                        # tenure gate
    assert ex.title_tier == base.title_tier                             # title
    # Section-PRESENCE flags are unchanged: extras never make a core section
    # count as present. (The stuffing-lint flag CAN legitimately shift — extras
    # are real keyword evidence that participates in skills-list corroboration —
    # so full format_flags equality is deliberately NOT asserted here.)
    def section_flags(flags):
        return [f for f in flags if f.startswith("Section missing or empty:")]
    assert section_flags(ex.format_flags) == section_flags(base.format_flags)

    ci = index_resume(core, as_of=AS_OF)
    xi = index_resume(withx, as_of=AS_OF)
    assert xi.recent_role == ci.recent_role                            # recent role
    assert xi.total_experience_years == ci.total_experience_years      # tenure
    assert xi.sections_present == ci.sections_present  # extras never mark experience present


def test_scoring_without_extras_config_key_behaves_pre_phase2():
    # F#2: a legacy/custom config whose weights lack the extra_section_evidence key
    # must not crash the engine — extras contribute nothing and scoring matches a
    # core-only resume (feature-off fallback in both the indexer and the layers).
    cfg = load_config()
    legacy_weights = copy.deepcopy(cfg.weights)
    legacy_weights.pop("extra_section_evidence")
    legacy_cfg = AtsConfig(
        weights=legacy_weights,
        aliases=cfg.aliases,
        adjacency=cfg.adjacency,
        title_families=cfg.title_families,
        version="legacy-test",
    )
    jd = _jd("Salesforce", "Snowflake", "Docker", "Tableau")
    with_extras = score_resume(_resume(EVIDENCE_EXTRAS), jd, as_of=AS_OF, config=legacy_cfg)
    core_only = score_resume(_resume(), jd, as_of=AS_OF, config=legacy_cfg)
    assert with_extras == core_only
    assert all(row["matched"] is False for row in with_extras.skill_table)


def test_extra_only_skill_surfaces_as_a_resurface_gap():
    # F#8: an extras-only-evidence skill is NOT dropped from the workflow — it
    # carries fix_hint "extra_only" and is routed to the resurface_recent category
    # (same honest intervention as an undated-core match: move it into a dated
    # core section), with the resurface action set.
    resume = _resume([{
        "key": "publications", "title": "Publications", "type": "entries",
        "enabled": True,
        "entries": [{"heading": "Kafka at scale", "enabled": True,
                     "bullets": ["Ran Kafka clusters."]}],
    }])
    result = score_resume(resume, _jd("Kafka"), as_of=AS_OF)
    row = _row(result, "Kafka")
    assert row["matched"] is True and row["placement"] == "extra_only"
    assert row["fix_hint"] == "extra_only"

    by_cat = {c["key"]: c for c in build_gaps(result)["categories"]}
    assert "resurface_recent" in by_cat
    kafka_gap = next(g for g in by_cat["resurface_recent"]["gaps"] if g["jd_skill"] == "Kafka")
    assert kafka_gap["actions"] == ["add_keyword", "user_input", "skip"]
    assert kafka_gap["diagnostic"]["fix_hint"] == "extra_only"


def test_extra_dates_do_not_affect_recent_role_years_or_recency():
    resume = _resume(EVIDENCE_EXTRAS)
    resume["experience"] = [
        {
            "company": "CoreCo",
            "role": "Analyst",
            "start_date": "Jan 2020",
            "end_date": "Jan 2021",
            "enabled": True,
            "bullets": ["Core work."],
        }
    ]
    jd = _jd("Salesforce")
    result = score_resume(resume, jd, as_of=AS_OF)
    row = _row(result, "Salesforce")
    assert row["placement"] == "extra_only"
    assert row["last_used"] is None
    assert row["recency_weight"] is None
    # The extra entry's Jan 2026 date does not enter core employment semantics.
    index = index_resume(resume, as_of=AS_OF)
    assert index.recent_role == "Analyst"
    assert 0.9 < index.total_experience_years < 1.1
