"""Direct interface tests for the Placement Target module.

build_targets / coerce carry richer coverage in tests/ats/test_gap_enrichment.py
(they moved here from gap_enrichment); this file pins the parts that previously
had no direct test surface at all.
"""
import pytest

from app.services import placement_targets

_RESUME = {
    "skills": [{"category": "Languages", "items": ["Python"]}],
    "experience": [
        {"company": "A", "enabled": True},
        {"company": "B", "enabled": False},
    ],
    "projects": [{"name": "P", "enabled": True}],
}


def test_widen_for_enables_admits_pending_entries_without_mutating_the_base_view():
    targets = placement_targets.build_targets(_RESUME)
    widened = placement_targets.widen_for_enables(targets, {("experience", 1)})
    assert widened["experience_indices"] == {0, 1}
    # The unwidened view must be untouched: it still validates non-port actions.
    assert targets["experience_indices"] == {0}
    assert widened["projects_indices"] == {0}


def test_widen_for_enables_passes_through_on_no_enables_or_no_targets():
    targets = placement_targets.build_targets(_RESUME)
    assert placement_targets.widen_for_enables(targets, set()) is targets
    assert placement_targets.widen_for_enables(None, {("experience", 1)}) is None


def test_canonicalize_raises_where_coerce_returns_none():
    """The strict and best-effort adapters share one contract: every placement
    coerce() drops, canonicalize() must reject — same rules, two failure modes."""
    targets = placement_targets.build_targets(_RESUME)
    bad = {"section": "experience", "index_or_category": 1}  # disabled entry
    with pytest.raises(ValueError):
        placement_targets.canonicalize(bad, targets, missing_skill=False)
    assert placement_targets.coerce(bad, targets, None) is None


def test_additional_skills_is_always_a_valid_skills_placement():
    targets = placement_targets.build_targets(_RESUME)
    placement = {
        "section": "skills",
        "index_or_category": placement_targets.ADDITIONAL_SKILLS,
    }
    assert placement_targets.canonicalize(
        placement, targets, missing_skill=True
    ) == {"section": "skills", "index_or_category": placement_targets.ADDITIONAL_SKILLS}
