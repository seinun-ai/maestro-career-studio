from datetime import date

import pytest

from app.services import gap_enrichment, placement_targets
from app.services.ats import score_resume
from app.services.gap_analysis import build_gaps
from tests.ats.fixtures import SAMPLE_JD, SAMPLE_RESUME


def _gaps():
    return build_gaps(score_resume(SAMPLE_RESUME, SAMPLE_JD, as_of=date(2026, 7, 6)))


def _all_gaps(gaps):
    return [gap for category in gaps["categories"] for gap in category["gaps"]]


def _mock_plumbing(monkeypatch, call_openai, prompt_builder=None):
    monkeypatch.setattr(
        gap_enrichment.prompt_assembly,
        "build_gap_enrichment_prompt",
        prompt_builder
        or (
            lambda resume_json, jd_json, gaps_json, **kwargs: "enrichment prompt"
        ),
    )
    monkeypatch.setattr(
        gap_enrichment.model_settings, "get_fast_model", lambda session=None: "gpt-fast"
    )
    monkeypatch.setattr(gap_enrichment.llm, "call_openai", call_openai)


def test_enrich_gaps_merges_by_gap_id(db_session, monkeypatch):
    gaps = _gaps()
    calls = {}

    def fake_call_openai(**kwargs):
        calls.update(kwargs)
        return {
            "enrichments": [
                {
                    "gap_id": "skill:salesforce",
                    "suggested_wording": None,
                    "project_candidates": ["RAG Search"],
                    "elicitation_question": "Have you worked with Salesforce data?",
                },
                {
                    # unknown gap_id: must be ignored, not appended anywhere
                    "gap_id": "skill:not-a-real-gap",
                    "suggested_wording": "ignored",
                    "project_candidates": [],
                    "elicitation_question": None,
                },
            ]
        }

    _mock_plumbing(monkeypatch, fake_call_openai)

    enriched = gap_enrichment.enrich_gaps(gaps, SAMPLE_RESUME, SAMPLE_JD, session=db_session)

    assert calls["model"] == "gpt-fast"
    assert calls["response_format"] == "json"
    by_id = {gap["gap_id"]: gap for gap in _all_gaps(enriched)}
    assert by_id["skill:salesforce"]["enrichment"] == {
        "suggested_wording": None,
        "project_candidates": ["RAG Search"],
        "elicitation_question": "Have you worked with Salesforce data?",
        "suggested_placement": None,
    }
    assert "skill:not-a-real-gap" not in by_id
    # gaps without an enrichment entry stay None
    others = [gap for gap in _all_gaps(enriched) if gap["gap_id"] != "skill:salesforce"]
    assert others and all(gap["enrichment"] is None for gap in others)
    # the input dict is not mutated
    assert all(gap["enrichment"] is None for gap in _all_gaps(gaps))


def test_enrich_gaps_sends_trimmed_gap_payload(db_session, monkeypatch):
    gaps = _gaps()
    captured = {}

    def capture_prompt(resume_json, jd_json, gaps_json):
        captured["gaps_json"] = gaps_json
        return "enrichment prompt"

    _mock_plumbing(monkeypatch, lambda **kwargs: {"enrichments": []}, capture_prompt)

    gap_enrichment.enrich_gaps(gaps, SAMPLE_RESUME, SAMPLE_JD, session=db_session)

    sent = captured["gaps_json"]["gaps"]
    assert {gap["gap_id"] for gap in sent} == {gap["gap_id"] for gap in _all_gaps(gaps)}
    skill = next(gap for gap in sent if gap["gap_id"] == "skill:salesforce")
    assert skill["category"] == "missing_skills"
    assert skill["kind"] == "skill"
    assert skill["jd_skill"] == "Salesforce"
    assert skill["requirement_level"] == "required"
    assert skill["fix_hint"] == "absent"
    assert set(skill["actions"]) == {
        "add_keyword",
        "user_input",
        "attach_project",
        "skip",
        "enable_entry",
        "port_kb_point",
    }
    # token thrift: the heavy diagnostic row and the empty enrichment slot stay home
    assert "diagnostic" not in skill
    assert "enrichment" not in skill


def test_enrich_gaps_coerces_wrong_typed_fields(db_session, monkeypatch):
    gaps = _gaps()
    _mock_plumbing(
        monkeypatch,
        lambda **kwargs: {
            "enrichments": [
                {
                    "gap_id": "skill:salesforce",
                    "suggested_wording": {"text": "not a string"},
                    "project_candidates": "RAG Search",  # string, not list
                    "elicitation_question": 42,
                },
                {
                    "gap_id": "skill:aws",
                    "suggested_wording": "AWS",
                    "project_candidates": ["RAG Search", {"name": "bad"}, 7],
                    "elicitation_question": None,
                },
            ]
        },
    )

    enriched = gap_enrichment.enrich_gaps(gaps, SAMPLE_RESUME, SAMPLE_JD, session=db_session)

    by_id = {gap["gap_id"]: gap for gap in _all_gaps(enriched)}
    # wrong-typed values must not freeze into gaps_json
    assert by_id["skill:salesforce"]["enrichment"] == {
        "suggested_wording": None,
        "project_candidates": [],
        "elicitation_question": None,
        "suggested_placement": None,
    }
    assert by_id["skill:aws"]["enrichment"] == {
        "suggested_wording": "AWS",
        "project_candidates": ["RAG Search"],
        "elicitation_question": None,
        "suggested_placement": None,
    }


def test_enrich_gaps_tolerates_missing_enrichments_key(db_session, monkeypatch):
    gaps = _gaps()
    _mock_plumbing(monkeypatch, lambda **kwargs: {"unexpected": True})

    enriched = gap_enrichment.enrich_gaps(gaps, SAMPLE_RESUME, SAMPLE_JD, session=db_session)

    assert all(gap["enrichment"] is None for gap in _all_gaps(enriched))


def test_enrich_gaps_does_not_swallow_llm_errors(db_session, monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("llm down")

    _mock_plumbing(monkeypatch, boom)

    # best-effort handling lives in the caller (session creation), not here
    with pytest.raises(RuntimeError, match="llm down"):
        gap_enrichment.enrich_gaps(_gaps(), SAMPLE_RESUME, SAMPLE_JD, session=db_session)


def test_enrich_gaps_rejects_non_list_enrichments(db_session, monkeypatch):
    _mock_plumbing(monkeypatch, lambda **kwargs: {"enrichments": {"gap_id": "skill:salesforce"}})

    with pytest.raises(ValueError, match="enrichments"):
        gap_enrichment.enrich_gaps(_gaps(), SAMPLE_RESUME, SAMPLE_JD, session=db_session)


_LIBRARY_RESUME = {
    "projects": [
        {
            "name": "Ingestion Pipeline",
            "enabled": False,
            "bullets": ["Streamed events with Apache Kafka into S3"],
            "tech": ["Kafka", "Spark"],
        },
        {
            "name": "Churn Model",
            "enabled": True,
            "bullets": ["Trained XGBoost model"],
            "tech": [],
        },
    ],
    "experience": [],
    "skills": [{"category": "Data & ETL", "items": ["SQL"]}],
}

_LIBRARY_KB = {
    "profile_skills": ["Airflow", "Kafka"],
    "entities": [
        {
            "id": "e1",
            "kind": "project",
            "title": "Churn Model",
            "status": "completed",
            "tech": ["MLflow"],
            "points": [
                {"id": "p1", "state": "approved", "text": "Tracked runs in MLflow"},
                {"id": "p2", "state": "draft", "text": "Deployed with Docker"},
            ],
        }
    ],
}

_LIBRARY_GAPS = {
    "categories": [
        {
            "key": "missing_skills",
            "gaps": [
                {
                    "gap_id": "skill:kafka",
                    "kind": "skill",
                    "jd_skill": "Kafka",
                    "requirement_level": "required",
                    "actions": [
                        "add_keyword",
                        "user_input",
                        "attach_project",
                        "skip",
                        "enable_entry",
                        "port_kb_point",
                    ],
                    "diagnostic": {"fix_hint": "absent"},
                    "enrichment": None,
                }
            ],
        }
    ]
}


def test_enrichment_proposals_are_gated_and_stamped(db_session, monkeypatch):
    _mock_plumbing(
        monkeypatch,
        lambda **kwargs: {
            "enrichments": [
                {
                    "gap_id": "skill:kafka",
                    "library_candidates": [
                        {"kind": "disabled", "section": "projects", "index": 0},
                        {"kind": "kb_point", "point_id": "p999", "entity_id": "e1"},
                        {"kind": "kb_point", "point_id": "p2", "entity_id": "e1"},
                    ],
                }
            ]
        },
    )

    out = gap_enrichment.enrich_gaps(
        _LIBRARY_GAPS,
        _LIBRARY_RESUME,
        {"skills": [{"name": "Kafka"}]},
        kb_snapshot=_LIBRARY_KB,
        session=db_session,
    )

    gap = out["categories"][0]["gaps"][0]
    candidates = gap["library_candidates"]
    # Self-nomination adds the profile hit (Kafka is a profile skill) even
    # though the LLM never proposed it; autos order before suggestions.
    assert [candidate["kind"] for candidate in candidates] == [
        "disabled",
        "profile",
        "kb_point",
    ]
    assert candidates[0]["auto"] is True
    assert candidates[1]["auto"] is True
    assert candidates[2]["auto"] is False  # draft point stays a suggestion


def test_no_kb_snapshot_means_no_candidate_stamping(db_session, monkeypatch):
    _mock_plumbing(
        monkeypatch,
        lambda **kwargs: {
            "enrichments": [
                {
                    "gap_id": "skill:kafka",
                    "library_candidates": [
                        {"kind": "disabled", "section": "projects", "index": 0}
                    ],
                }
            ]
        },
    )

    out = gap_enrichment.enrich_gaps(
        _LIBRARY_GAPS,
        _LIBRARY_RESUME,
        {"skills": [{"name": "Kafka"}]},
        kb_snapshot=None,
        session=db_session,
    )

    assert "library_candidates" not in out["categories"][0]["gaps"][0]


def test_wrong_typed_library_candidates_fall_back_to_self_nomination(
    db_session, monkeypatch
):
    """Wrong-typed LLM output is ignored, but discovery no longer depends on
    the LLM: self-nominated lexical hits are stamped regardless (live E2E
    2026-08-05 caught the fast model returning null for literal matches)."""
    _mock_plumbing(
        monkeypatch,
        lambda **kwargs: {
            "enrichments": [
                {"gap_id": "skill:kafka", "library_candidates": {"kind": "profile"}}
            ]
        },
    )

    out = gap_enrichment.enrich_gaps(
        _LIBRARY_GAPS,
        _LIBRARY_RESUME,
        {"skills": [{"name": "Kafka"}]},
        kb_snapshot=_LIBRARY_KB,
        session=db_session,
    )

    candidates = out["categories"][0]["gaps"][0]["library_candidates"]
    assert [c["kind"] for c in candidates] == ["disabled", "profile"]
    assert all(c["auto"] for c in candidates)


def test_self_nomination_stamps_lexical_hits_when_llm_proposes_nothing(
    db_session, monkeypatch
):
    _mock_plumbing(
        monkeypatch,
        lambda **kwargs: {"enrichments": [{"gap_id": "skill:kafka"}]},
    )

    out = gap_enrichment.enrich_gaps(
        _LIBRARY_GAPS,
        _LIBRARY_RESUME,
        {"skills": [{"name": "Kafka"}]},
        kb_snapshot=_LIBRARY_KB,
        session=db_session,
    )

    candidates = out["categories"][0]["gaps"][0]["library_candidates"]
    # Disabled Kafka project + Kafka profile skill found without any LLM help;
    # the non-matching MLflow/Docker points are NOT demoted into noise chips.
    assert [c["kind"] for c in candidates] == ["disabled", "profile"]
    assert all(c["auto"] for c in candidates)


def test_enrich_gaps_sends_kb_and_full_index_disabled_entries(db_session, monkeypatch):
    captured = {}

    def capture_prompt(
        resume_json, jd_json, gaps_json, *, kb_snapshot=None, disabled_entries=None
    ):
        captured["kb_snapshot"] = kb_snapshot
        captured["disabled_entries"] = disabled_entries
        return "enrichment prompt"

    _mock_plumbing(monkeypatch, lambda **kwargs: {"enrichments": []}, capture_prompt)

    gap_enrichment.enrich_gaps(
        _LIBRARY_GAPS,
        _LIBRARY_RESUME,
        {"skills": [{"name": "Kafka"}]},
        kb_snapshot=_LIBRARY_KB,
        session=db_session,
    )

    assert captured["kb_snapshot"] is _LIBRARY_KB
    assert captured["disabled_entries"] == [
        {
            "section": "projects",
            "index": 0,
            "name": "Ingestion Pipeline",
            # entry_evidence_texts: bullets, tech items, then the project name
            # (a name like "Kafka Migration" is fair evidence for the gate).
            "text": "Streamed events with Apache Kafka into S3\nKafka\nSpark\nIngestion Pipeline",
        }
    ]


def test_gap_enrichment_prompt_renders_real_library_ids(monkeypatch):
    monkeypatch.setattr(
        gap_enrichment.prompt_assembly.prompts,
        "get_prompt",
        lambda key: (
            "JUDGMENT RULES" if key == "tailoring_skill" else
            "Resume=${resume_json}\nJD=${jd_json}\nGaps=${gaps_json}"
        ),
    )

    prompt = gap_enrichment.prompt_assembly.build_gap_enrichment_prompt(
        _LIBRARY_RESUME,
        {"skills": [{"name": "Kafka"}]},
        _LIBRARY_GAPS,
        kb_snapshot=_LIBRARY_KB,
        disabled_entries=[
            {
                "section": "projects",
                "index": 0,
                "name": "Ingestion Pipeline",
                "text": "Streamed events with Apache Kafka into S3",
            }
        ],
    )

    assert "## Career knowledge base" in prompt
    assert "entity_id=e1" in prompt
    assert "point_id=p1" in prompt
    assert "## Disabled resume entries" in prompt
    assert "section=projects index=0" in prompt
    assert "never invent ids" in prompt.lower()


# --- diagnostic evidence in the trimmed payload ---------------------------


def test_trim_gaps_includes_present_diagnostic_evidence():
    """The model needs the diagnostic's grounding evidence to justify a
    placement/wording suggestion; only the sub-fields that are present and
    non-None travel — the heavy diagnostic row itself never does."""
    gaps = {
        "categories": [
            {
                "key": "mirror_wording",
                "gaps": [
                    {
                        "gap_id": "skill:aws",
                        "kind": "skill",
                        "jd_skill": "AWS",
                        "requirement_level": "preferred",
                        "actions": ["add_keyword", "skip"],
                        "diagnostic": {
                            "fix_hint": "mirror_wording",
                            "placement": "dual",
                            "matched_term": "amazon web services",
                            "last_used": "current",
                            "evidence_entries": ["DataCo - Data Scientist"],
                            # recency math the model doesn't need -> must stay home
                            "recency_weight": 1.0,
                            "contribution": 0.42,
                        },
                        "enrichment": None,
                    },
                    {
                        "gap_id": "skill:snowflake",
                        "kind": "skill",
                        "jd_skill": "Snowflake",
                        "requirement_level": "required",
                        "actions": ["add_keyword", "user_input", "attach_project", "skip"],
                        "diagnostic": {
                            "fix_hint": "absent",
                            "placement": None,      # None -> excluded
                            "matched_term": None,   # None -> excluded
                            "last_used": None,      # None -> excluded
                            "evidence_entries": [],  # present (empty, non-None) -> kept
                        },
                        "enrichment": None,
                    },
                ],
            }
        ]
    }

    trimmed = gap_enrichment._trim_gaps(gaps)["gaps"]

    aws = next(g for g in trimmed if g["gap_id"] == "skill:aws")
    assert aws["placement"] == "dual"
    assert aws["matched_term"] == "amazon web services"
    assert aws["last_used"] == "current"
    assert aws["evidence_entries"] == ["DataCo - Data Scientist"]
    assert aws["fix_hint"] == "mirror_wording"
    # recency math is not part of the evidence set the model sees
    assert "recency_weight" not in aws
    assert "contribution" not in aws
    # the raw diagnostic row never travels
    assert "diagnostic" not in aws

    snow = next(g for g in trimmed if g["gap_id"] == "skill:snowflake")
    # None-valued sub-fields are dropped
    assert "placement" not in snow
    assert "matched_term" not in snow
    assert "last_used" not in snow
    # a present (empty) list is kept
    assert snow["evidence_entries"] == []


# --- suggested_placement validation --------------------------------------


def _entry(placement):
    return {"gap_id": "skill:x", "suggested_placement": placement}


def test_coerce_enrichment_drops_out_of_range_experience_index():
    targets = placement_targets.build_targets(SAMPLE_RESUME)
    # SAMPLE_RESUME has 2 ENABLED experience entries at full-array indices 0,1
    # (HiddenCo is disabled, at index 2)
    assert targets["experience_indices"] == {0, 1}

    coerced = gap_enrichment._coerce_enrichment(
        _entry({"section": "experience", "index_or_category": 5}),
        targets,
        "resurface_recent",
    )
    assert coerced["suggested_placement"] is None


def test_coerce_placement_accepts_enabled_index_beyond_enabled_count():
    """Regression: the frontend emits FULL-ARRAY indices (skipping disabled
    entries but keeping their positions). A disabled entry earlier in the array
    pushes a valid later entry's index past the enabled *count*, which a
    count-based bound wrongly rejected. Validate against enabled indices instead."""
    resume = {
        "skills": [{"category": "Cloud", "items": ["AWS"]}],
        "experience": [{"enabled": False}, {"enabled": True}],
        "projects": [
            {"enabled": True},
            {"enabled": False},
            {"enabled": False},
            {"enabled": True},
        ],
    }
    targets = placement_targets.build_targets(resume)
    assert targets["experience_indices"] == {1}
    assert targets["projects_indices"] == {0, 3}
    # enabled experience at full-array index 1 (beyond enabled count 1) is accepted
    assert placement_targets.coerce(
        {"section": "experience", "index_or_category": 1}, targets, "resurface_recent"
    ) == {"section": "experience", "index_or_category": 1}
    # enabled project at full-array index 3 (the exact user-reported case) accepted
    assert placement_targets.coerce(
        {"section": "projects", "index_or_category": 3}, targets, "dual_place"
    ) == {"section": "projects", "index_or_category": 3}
    # a DISABLED entry's index is rejected
    assert placement_targets.coerce(
        {"section": "experience", "index_or_category": 0}, targets, "resurface_recent"
    ) is None


def test_coerce_enrichment_drops_non_skills_placement_for_absent():
    targets = placement_targets.build_targets(SAMPLE_RESUME)
    # index 0 is in range, so only the honesty invariant can reject this:
    # an absent (unverified) skill may only be placed into the skills list.
    coerced = gap_enrichment._coerce_enrichment(
        _entry({"section": "experience", "index_or_category": 0}),
        targets,
        "absent",
    )
    assert coerced["suggested_placement"] is None


def test_coerce_enrichment_keeps_valid_skills_category():
    targets = placement_targets.build_targets(SAMPLE_RESUME)
    # case-insensitive match against a real category ("Cloud")
    coerced = gap_enrichment._coerce_enrichment(
        _entry({"section": "skills", "index_or_category": "cloud"}),
        targets,
        "absent",
    )
    assert coerced["suggested_placement"] == {"section": "skills", "index_or_category": "cloud"}

    # the literal fallback is always accepted even without a matching category
    fallback = gap_enrichment._coerce_enrichment(
        _entry({"section": "skills", "index_or_category": "Additional Skills"}),
        targets,
        "absent",
    )
    assert fallback["suggested_placement"] == {
        "section": "skills",
        "index_or_category": "Additional Skills",
    }


def test_coerce_enrichment_keeps_valid_experience_index():
    targets = placement_targets.build_targets(SAMPLE_RESUME)
    coerced = gap_enrichment._coerce_enrichment(
        _entry({"section": "experience", "index_or_category": 1}),
        targets,
        "resurface_recent",
    )
    assert coerced["suggested_placement"] == {"section": "experience", "index_or_category": 1}


_RESUME_WITH_EXTRAS = {
    "skills": [{"category": "Cloud", "items": ["AWS"]}],
    "experience": [{"enabled": True}, {"enabled": False}],
    "projects": [{"enabled": True}],
    "extra_sections": [
        {
            "key": "volunteer",
            "title": "Volunteer Work",
            "type": "entries",
            "enabled": True,
            "entries": [
                {"heading": "Mentor", "enabled": True},
                {"heading": "Old Mentor", "enabled": False},
                {"heading": "Organizer"},
            ],
        },
        {
            "key": "awards",
            "title": "Awards",
            "type": "bullets",
            "enabled": True,
            "bullets": ["Innovation Award"],
        },
        {
            "key": "hidden",
            "title": "Hidden",
            "type": "entries",
            "enabled": False,
            "entries": [{"heading": "Invisible", "enabled": True}],
        },
    ],
}


def test_build_resume_targets_indexes_only_enabled_extra_destinations():
    targets = placement_targets.build_targets(_RESUME_WITH_EXTRAS)

    assert targets["extra_sections"] == {
        "volunteer": {"type": "entries", "indices": {0, 2}},
        "awards": {"type": "bullets"},
    }


def test_build_resume_targets_tolerates_null_extra_sections():
    # F#13: an explicit "extra_sections": null must not raise (`or []` guard);
    # matches the ATS indexer, which uses the same guarded form.
    assert placement_targets.build_targets({"extra_sections": None})["extra_sections"] == {}


def test_indexer_and_target_builder_agree_on_enabled_none():
    # F#6: the ATS-evidence view (index_resume) and the placement-target view
    # (placement_targets.build_targets) must agree on which custom content is live. An
    # omitted/None `enabled` reads as LIVE for BOTH — previously the target
    # builder's truthy check treated None as disabled while the indexer kept it.
    from datetime import date

    from app.services.ats.resume_indexer import index_resume

    resume = {
        "extra_sections": [{
            "key": "pubs", "title": "Pubs", "type": "entries", "enabled": None,
            "entries": [{"heading": "E", "enabled": None, "bullets": ["Kafka work."]}],
        }],
    }
    # ATS-evidence view: the section+entry are live custom evidence
    idx = index_resume(resume, as_of=date(2026, 7, 6))
    assert [e.label for e in idx.entries if e.section == "extra"] == ["E"]
    # placement-target view: the same section+entry are live targets
    targets = placement_targets.build_targets(resume)
    assert targets["extra_sections"] == {"pubs": {"type": "entries", "indices": {0}}}


@pytest.mark.parametrize(
    ("placement", "missing_skill", "accepted"),
    [
        ({"section": "skills", "index_or_category": "Cloud"}, True, True),
        ({"section": "experience", "index_or_category": 0}, False, True),
        ({"section": "projects", "index_or_category": 0}, False, True),
        (
            {
                "section": "extra",
                "section_key": "volunteer",
                "index_or_category": 0,
            },
            False,
            True,
        ),
        (
            {
                "section": "extra",
                "section_key": "volunteer",
                "index_or_category": 2,
            },
            False,
            True,
        ),
        (
            {
                "section": "extra",
                "section_key": "awards",
                "index_or_category": "awards",
            },
            False,
            True,
        ),
        # Disabled entry and section, unknown key, malformed bullets sentinel.
        (
            {
                "section": "extra",
                "section_key": "volunteer",
                "index_or_category": 1,
            },
            False,
            False,
        ),
        (
            {"section": "extra", "section_key": "hidden", "index_or_category": 0},
            False,
            False,
        ),
        (
            {"section": "extra", "section_key": "missing", "index_or_category": 0},
            False,
            False,
        ),
        (
            {"section": "extra", "section_key": "awards", "index_or_category": 0},
            False,
            False,
        ),
        # An engine-absent skill cannot use an otherwise-valid custom target.
        (
            {
                "section": "extra",
                "section_key": "volunteer",
                "index_or_category": 0,
            },
            True,
            False,
        ),
    ],
)
def test_enrichment_and_strict_placement_validators_have_exact_parity(
    placement, missing_skill, accepted
):
    from app.services.tailoring_session import _validate_placement_target

    targets = placement_targets.build_targets(_RESUME_WITH_EXTRAS)
    coerced = placement_targets.coerce(
        placement, targets, "absent" if missing_skill else "resurface_recent"
    )

    try:
        _validate_placement_target(
            placement,
            targets,
            "skill:x",
            missing_skill=missing_skill,
        )
        strict_accepted = True
    except ValueError:
        strict_accepted = False

    assert (coerced is not None) is accepted
    assert strict_accepted is accepted
    assert strict_accepted is (coerced is not None)
    if accepted:
        assert coerced == placement
