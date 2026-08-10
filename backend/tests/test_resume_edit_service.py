import logging
from copy import deepcopy

import pytest

from app.schemas.resume_edit import ResumeEditRequest
from app.services.resume_edit import apply_edits


BASE = {
    "contact": {"name": "Sample", "email": "a@example.com"},
    "summary": "Original summary.",
    "skills": [
        {"category": "Languages", "items": ["Python"]},
        {"category": "Cloud", "items": ["AWS"]},
    ],
    "experience": [
        {
            "company": "Acme",
            "role": "DS",
            "start_date": "2020",
            "enabled": True,
            "bullets": ["Built pipeline.", "Shipped model."],
        }
    ],
    "projects": [{"name": "Proj", "enabled": True, "bullets": ["Did a thing."]}],
    "education": [{"institution": "Uni", "degree": "BS", "bullets": ["Graduated."]}],
    "certifications": [],
}


def _ops(*raw):
    return ResumeEditRequest.model_validate({"ops": list(raw)}).ops


def test_replace_bullet_round_trip_only_that_bullet_differs():
    base = deepcopy(BASE)
    ops = _ops(
        {
            "kind": "replace_bullet",
            "section": "experience",
            "index": 0,
            "bullet_index": 1,
            "value": "Deployed RAG service.",
        }
    )
    result = apply_edits(base, ops)

    assert result["experience"][0]["bullets"][1] == "Deployed RAG service."
    # Only that one bullet changed; everything else equals the base.
    expected = deepcopy(BASE)
    expected["experience"][0]["bullets"][1] = "Deployed RAG service."
    assert result == expected
    # Input not mutated.
    assert base == BASE


def test_replace_summary_and_none():
    result = apply_edits(deepcopy(BASE), _ops({"kind": "replace_summary", "value": None}))
    assert result["summary"] is None


def test_toggle_entry_flips_enabled():
    result = apply_edits(
        deepcopy(BASE),
        _ops({"kind": "toggle_entry", "section": "projects", "index": 0, "enabled": False}),
    )
    assert result["projects"][0]["enabled"] is False
    assert result["experience"][0]["enabled"] is True  # untouched


def test_replace_skills_group_case_insensitive_match():
    result = apply_edits(
        deepcopy(BASE),
        _ops({"kind": "replace_skills_group", "category": "languages", "items": ["Python", "Go"]}),
    )
    langs = [g for g in result["skills"] if g["category"] == "Languages"][0]
    assert langs["items"] == ["Python", "Go"]


def test_add_skill_item_appends_to_existing_category():
    result = apply_edits(
        deepcopy(BASE),
        _ops({"kind": "add_skill_item", "category": "Languages", "item": "SQL"}),
    )
    langs = [g for g in result["skills"] if g["category"] == "Languages"][0]
    assert langs["items"] == ["Python", "SQL"]


def test_add_skill_item_creates_category_when_absent():
    result = apply_edits(
        deepcopy(BASE),
        _ops({"kind": "add_skill_item", "category": "Additional Skills", "item": "Salesforce"}),
    )
    cats = {g["category"]: g["items"] for g in result["skills"]}
    assert cats["Additional Skills"] == ["Salesforce"]
    assert cats["Languages"] == ["Python"]  # untouched


def test_add_skill_item_is_case_insensitive_dedupe():
    result = apply_edits(
        deepcopy(BASE),
        _ops({"kind": "add_skill_item", "category": "languages", "item": "python"}),
    )
    langs = [g for g in result["skills"] if g["category"] == "Languages"][0]
    assert langs["items"] == ["Python"]  # already present (ci) -> no dup


def test_add_skill_item_strips_whitespace_before_storing():
    result = apply_edits(
        deepcopy(BASE),
        _ops({"kind": "add_skill_item", "category": "Languages", "item": " SQL "}),
    )
    langs = [g for g in result["skills"] if g["category"] == "Languages"][0]
    assert langs["items"] == ["Python", "SQL"]  # trimmed, then appended


def test_add_skill_item_stripped_item_dedupes_case_insensitively():
    result = apply_edits(
        deepcopy(BASE),
        _ops({"kind": "add_skill_item", "category": "Languages", "item": "  python  "}),
    )
    langs = [g for g in result["skills"] if g["category"] == "Languages"][0]
    assert langs["items"] == ["Python"]  # " python " -> "python" matches "Python" (ci) -> no dup


def test_add_skill_item_creates_skills_list_when_key_absent():
    # a resume dict lacking a "skills" list at all still works: the op creates it.
    resume = {"contact": {"name": "Sample", "email": "a@example.com"}}
    result = apply_edits(
        resume,
        _ops({"kind": "add_skill_item", "category": "Additional Skills", "item": "Salesforce"}),
    )
    assert result["skills"] == [{"category": "Additional Skills", "items": ["Salesforce"]}]
    assert resume == {"contact": {"name": "Sample", "email": "a@example.com"}}  # input untouched


def test_add_bullet_appends_to_experience_entry():
    base = deepcopy(BASE)
    result = apply_edits(
        base,
        _ops({"kind": "add_bullet", "section": "experience", "index": 0, "text": "Deployed RAG service."}),
    )
    bullets = result["experience"][0]["bullets"]
    assert bullets == ["Built pipeline.", "Shipped model.", "Deployed RAG service."]
    assert bullets[-1] == "Deployed RAG service."  # appended as the last bullet
    assert base == BASE  # input not mutated


def test_add_bullet_appends_to_project_with_empty_bullets():
    base = deepcopy(BASE)
    base["projects"][0]["bullets"] = []
    result = apply_edits(
        base,
        _ops({"kind": "add_bullet", "section": "projects", "index": 0, "text": "Built the MVP."}),
    )
    assert result["projects"][0]["bullets"] == ["Built the MVP."]
    assert len(result["projects"][0]["bullets"]) == 1


def test_add_bullet_strips_text_before_storing():
    result = apply_edits(
        deepcopy(BASE),
        _ops({"kind": "add_bullet", "section": "experience", "index": 0, "text": "  Owned rollout.  "}),
    )
    assert result["experience"][0]["bullets"][-1] == "Owned rollout."


def test_add_bullet_result_passes_resume_data_validation():
    from app.schemas.resume import ResumeData

    result = apply_edits(
        deepcopy(BASE),
        _ops({"kind": "add_bullet", "section": "projects", "index": 0, "text": "New bullet."}),
    )
    # Should not raise.
    ResumeData.model_validate(result)


def test_add_bullet_out_of_range_index_raises_value_error():
    with pytest.raises(ValueError, match="experience index 5 out of range"):
        apply_edits(
            deepcopy(BASE),
            _ops({"kind": "add_bullet", "section": "experience", "index": 5, "text": "x"}),
        )


def test_entry_index_out_of_range_raises_value_error():
    with pytest.raises(ValueError, match="experience index 5 out of range"):
        apply_edits(
            deepcopy(BASE),
            _ops(
                {
                    "kind": "replace_bullet",
                    "section": "experience",
                    "index": 5,
                    "bullet_index": 0,
                    "value": "x",
                }
            ),
        )


def test_bullet_index_out_of_range_raises_value_error():
    with pytest.raises(ValueError, match="bullet_index 9 out of range"):
        apply_edits(
            deepcopy(BASE),
            _ops(
                {
                    "kind": "replace_bullet",
                    "section": "experience",
                    "index": 0,
                    "bullet_index": 9,
                    "value": "x",
                }
            ),
        )


def test_missing_skills_category_raises_value_error():
    with pytest.raises(ValueError, match="No skills group"):
        apply_edits(
            deepcopy(BASE),
            _ops({"kind": "replace_skills_group", "category": "Robotics", "items": ["ROS"]}),
        )


def test_ambiguous_skills_category_raises_value_error():
    base = deepcopy(BASE)
    base["skills"].append({"category": "languages", "items": ["Rust"]})  # dup of "Languages"
    with pytest.raises(ValueError, match="Ambiguous skills group"):
        apply_edits(
            base,
            _ops({"kind": "replace_skills_group", "category": "Languages", "items": ["Python"]}),
        )


def test_invalid_result_raises_validation_error():
    # Replacing the only bullet with a non-string would fail ResumeData validation;
    # bullets must be str. Force it by toggling an experience index that breaks shape.
    base = deepcopy(BASE)
    base["contact"] = {}  # missing required name/email -> model_validate fails
    with pytest.raises(Exception):
        apply_edits(base, _ops({"kind": "replace_summary", "value": "x"}))


def test_replace_skills_group_warns_on_item_removal(caplog):
    caplog.set_level(logging.WARNING)
    base = deepcopy(BASE)
    base["skills"] = [{"category": "Languages", "items": ["Python", "SQL"]}]
    # Replace with a truncated list that drops "SQL" -> suspicious, should warn.
    result = apply_edits(
        base,
        _ops({"kind": "replace_skills_group", "category": "Languages", "items": ["Python"]}),
    )
    assert result["skills"][0]["items"] == ["Python"]  # behavior unchanged
    assert any("removes items" in r.message for r in caplog.records)


def test_replace_skills_group_superset_logs_no_warning(caplog):
    caplog.set_level(logging.WARNING)
    base = deepcopy(BASE)
    base["skills"] = [{"category": "Languages", "items": ["Python", "SQL"]}]
    # Replace with a superset (adds "Pandas", drops nothing) -> no warning.
    result = apply_edits(
        base,
        _ops(
            {
                "kind": "replace_skills_group",
                "category": "Languages",
                "items": ["Python", "SQL", "Pandas"],
            }
        ),
    )
    assert result["skills"][0]["items"] == ["Python", "SQL", "Pandas"]
    assert not any("removes items" in r.message for r in caplog.records)


def test_non_dict_entry_raises_value_error():
    base = deepcopy(BASE)
    base["experience"] = ["not a dict"]
    with pytest.raises(ValueError):
        apply_edits(
            base,
            _ops({"kind": "toggle_entry", "section": "experience", "index": 0, "enabled": False}),
        )


# ---------------------------------------------------------------------------
# Extended ops (chat editing coverage)


def test_add_entry_appends_validated_project():
    ops = _ops(
        {
            "kind": "add_entry",
            "section": "projects",
            "value": {"name": "New Proj", "tech": "Python", "bullets": ["Built it."]},
        }
    )
    result = apply_edits(deepcopy(BASE), ops)
    assert result["projects"][-1]["name"] == "New Proj"
    assert result["projects"][-1]["enabled"] is True  # model default applied


def test_add_entry_rejects_malformed_value():
    ops = _ops({"kind": "add_entry", "section": "experience", "value": {"company": "X"}})
    with pytest.raises(ValueError):
        apply_edits(deepcopy(BASE), ops)


def test_replace_entry_swaps_item_wholesale():
    ops = _ops(
        {
            "kind": "replace_entry",
            "section": "experience",
            "index": 0,
            "value": {
                "company": "Acme",
                "role": "Senior DS",
                "start_date": "2020",
                "bullets": ["Led team."],
            },
        }
    )
    result = apply_edits(deepcopy(BASE), ops)
    assert result["experience"][0]["role"] == "Senior DS"
    assert result["experience"][0]["bullets"] == ["Led team."]


def test_remove_entry_and_out_of_range():
    result = apply_edits(deepcopy(BASE), _ops({"kind": "remove_entry", "section": "projects", "index": 0}))
    assert result["projects"] == []
    with pytest.raises(ValueError):
        apply_edits(deepcopy(BASE), _ops({"kind": "remove_entry", "section": "projects", "index": 5}))


def test_remove_bullet():
    ops = _ops({"kind": "remove_bullet", "section": "experience", "index": 0, "bullet_index": 0})
    result = apply_edits(deepcopy(BASE), ops)
    assert result["experience"][0]["bullets"] == ["Shipped model."]
    with pytest.raises(ValueError):
        apply_edits(
            deepcopy(BASE),
            _ops({"kind": "remove_bullet", "section": "experience", "index": 0, "bullet_index": 9}),
        )


def test_replace_contact():
    ops = _ops(
        {"kind": "replace_contact", "value": {"name": "Sample Applicant", "email": "new@example.com"}}
    )
    result = apply_edits(deepcopy(BASE), ops)
    assert result["contact"]["email"] == "new@example.com"


def test_replace_certifications():
    ops = _ops({"kind": "replace_certifications", "items": ["AWS SAA"]})
    result = apply_edits(deepcopy(BASE), ops)
    assert result["certifications"] == ["AWS SAA"]


# ---------------------------------------------------------------------------
# Extra (custom) section ops

BASE_WITH_EXTRAS = {
    **deepcopy(BASE),
    "extra_sections": [
        {"key": "publications", "title": "Publications", "type": "entries", "enabled": True,
         "entries": [{"heading": "A paper", "date": "2025", "bullets": []}]},
        {"key": "awards", "title": "Awards", "type": "bullets", "enabled": True,
         "bullets": ["First place, 2025"]},
    ],
}


def test_add_extra_section_appends_normalized_bullets_section():
    result = apply_edits(
        deepcopy(BASE),
        _ops({"kind": "add_extra_section",
              "value": {"key": "awards", "title": "Awards", "type": "bullets",
                        "bullets": ["First place, 2025"]}}),
    )
    assert result["extra_sections"][-1]["key"] == "awards"
    assert result["extra_sections"][-1]["type"] == "bullets"
    assert result["extra_sections"][-1]["enabled"] is True  # model default applied


def test_add_extra_section_appends_entries_section():
    result = apply_edits(
        deepcopy(BASE),
        _ops({"kind": "add_extra_section",
              "value": {"key": "publications", "title": "Publications", "type": "entries",
                        "entries": [{"heading": "A paper", "date": "2025"}]}}),
    )
    section = result["extra_sections"][-1]
    assert section["type"] == "entries"
    assert section["entries"][0]["heading"] == "A paper"
    assert section["entries"][0]["enabled"] is True  # entry default applied


def test_add_extra_section_rejects_bad_key_slug():
    with pytest.raises(ValueError, match="invalid extra section"):
        apply_edits(
            deepcopy(BASE),
            _ops({"kind": "add_extra_section",
                  "value": {"key": "Not A Slug", "title": "X", "type": "bullets", "bullets": ["y"]}}),
        )


def test_add_extra_section_rejects_both_content_branches():
    # discriminator routes to `bullets`; an extra `entries` field is forbidden.
    with pytest.raises(ValueError, match="invalid extra section"):
        apply_edits(
            deepcopy(BASE),
            _ops({"kind": "add_extra_section",
                  "value": {"key": "awards", "title": "Awards", "type": "bullets",
                            "bullets": ["x"], "entries": []}}),
        )


def test_add_extra_section_duplicate_key_raises():
    with pytest.raises(ValueError, match="duplicate"):
        apply_edits(
            deepcopy(BASE_WITH_EXTRAS),
            _ops({"kind": "add_extra_section",
                  "value": {"key": "awards", "title": "More Awards", "type": "bullets",
                            "bullets": ["Second place"]}}),
        )


def test_add_extra_section_reserved_key_collision_raises():
    with pytest.raises(ValueError, match="collides"):
        apply_edits(
            deepcopy(BASE),
            _ops({"kind": "add_extra_section",
                  "value": {"key": "skills", "title": "Skills", "type": "bullets", "bullets": ["x"]}}),
        )


def test_replace_extra_section_swaps_by_key():
    result = apply_edits(
        deepcopy(BASE_WITH_EXTRAS),
        _ops({"kind": "replace_extra_section", "section_key": "awards",
              "value": {"key": "awards", "title": "Honors & Awards", "type": "bullets",
                        "bullets": ["First place, 2025", "Dean's list"]}}),
    )
    awards = [s for s in result["extra_sections"] if s["key"] == "awards"][0]
    assert awards["title"] == "Honors & Awards"
    assert awards["bullets"] == ["First place, 2025", "Dean's list"]
    # order preserved: publications still first
    assert result["extra_sections"][0]["key"] == "publications"


def test_replace_extra_section_can_switch_type_keeping_key():
    result = apply_edits(
        deepcopy(BASE_WITH_EXTRAS),
        _ops({"kind": "replace_extra_section", "section_key": "awards",
              "value": {"key": "awards", "title": "Awards", "type": "entries",
                        "entries": [{"heading": "Best Paper", "date": "2025"}]}}),
    )
    awards = [s for s in result["extra_sections"] if s["key"] == "awards"][0]
    assert awards["type"] == "entries"


def test_replace_extra_section_unknown_key_raises():
    with pytest.raises(ValueError, match="no extra section with key 'nope'"):
        apply_edits(
            deepcopy(BASE_WITH_EXTRAS),
            _ops({"kind": "replace_extra_section", "section_key": "nope",
                  "value": {"key": "nope", "title": "X", "type": "bullets", "bullets": ["y"]}}),
        )


def test_replace_extra_section_may_not_change_key():
    with pytest.raises(ValueError, match="may not change the key"):
        apply_edits(
            deepcopy(BASE_WITH_EXTRAS),
            _ops({"kind": "replace_extra_section", "section_key": "awards",
                  "value": {"key": "honors", "title": "Honors", "type": "bullets", "bullets": ["y"]}}),
        )


def test_remove_extra_section_by_key():
    result = apply_edits(
        deepcopy(BASE_WITH_EXTRAS),
        _ops({"kind": "remove_extra_section", "section_key": "publications"}),
    )
    assert [s["key"] for s in result["extra_sections"]] == ["awards"]


def test_remove_extra_section_unknown_key_raises():
    with pytest.raises(ValueError, match="no extra section with key 'nope'"):
        apply_edits(
            deepcopy(BASE_WITH_EXTRAS),
            _ops({"kind": "remove_extra_section", "section_key": "nope"}),
        )


def test_remove_extra_section_when_none_present_raises():
    # BASE has no extra_sections key at all -> clean unknown-key ValueError.
    with pytest.raises(ValueError, match="no extra section with key"):
        apply_edits(deepcopy(BASE), _ops({"kind": "remove_extra_section", "section_key": "awards"}))


def test_move_extra_section_reorders():
    result = apply_edits(
        deepcopy(BASE_WITH_EXTRAS),
        _ops({"kind": "move_extra_section", "section_key": "awards", "to_index": 0}),
    )
    assert [s["key"] for s in result["extra_sections"]] == ["awards", "publications"]


def test_move_extra_section_out_of_range_raises():
    with pytest.raises(ValueError, match="extra section index 5 out of range"):
        apply_edits(
            deepcopy(BASE_WITH_EXTRAS),
            _ops({"kind": "move_extra_section", "section_key": "awards", "to_index": 5}),
        )


def test_move_extra_section_unknown_key_raises():
    with pytest.raises(ValueError, match="no extra section with key 'nope'"):
        apply_edits(
            deepcopy(BASE_WITH_EXTRAS),
            _ops({"kind": "move_extra_section", "section_key": "nope", "to_index": 0}),
        )


def test_extra_section_case_insensitive_key_lookup():
    result = apply_edits(
        deepcopy(BASE_WITH_EXTRAS),
        _ops({"kind": "remove_extra_section", "section_key": "AWARDS"}),
    )
    assert [s["key"] for s in result["extra_sections"]] == ["publications"]


def test_extra_section_batch_is_atomic_on_failure():
    base = deepcopy(BASE_WITH_EXTRAS)
    ops = _ops(
        {"kind": "remove_extra_section", "section_key": "publications"},
        {"kind": "remove_extra_section", "section_key": "nope"},  # 2nd op fails
    )
    with pytest.raises(ValueError, match="no extra section with key 'nope'"):
        apply_edits(base, ops)
    # input untouched: the deep-copied working dict is discarded on failure.
    assert base == BASE_WITH_EXTRAS
    assert [s["key"] for s in base["extra_sections"]] == ["publications", "awards"]


def test_replace_bullet_full_array_index_skips_disabled_and_echoes_applied():
    """PDF ordinals omit enabled:false; edit index is still full-array."""
    base = deepcopy(BASE)
    base["projects"] = [
        {"name": "DisabledOld", "enabled": False, "bullets": ["old work"]},
        {"name": "AlsoOff", "enabled": False, "bullets": ["hidden"]},
        {"name": "VisibleTarget", "enabled": True, "bullets": ["keep me", "touch me"]},
    ]
    applied: list = []
    result = apply_edits(
        base,
        _ops({
            "kind": "replace_bullet",
            "section": "projects",
            "index": 2,
            "bullet_index": 1,
            "value": "updated visible bullet",
        }),
        applied=applied,
    )
    assert result["projects"][0]["bullets"][0] == "old work"
    assert result["projects"][2]["bullets"][1] == "updated visible bullet"
    assert applied == [{
        "kind": "replace_bullet",
        "section": "projects",
        "index": 2,
        "name": "VisibleTarget",
        "bullet_index": 1,
        "before": "touch me",
        "after": "updated visible bullet",
    }]
