"""Canonical extras-preset catalog: shape, key hygiene, and the prompt block."""

from app.schemas.resume import CORE_SECTION_KEYS, CORE_SECTION_TITLES, ResumeData
from app.services import extra_section_presets as presets


def test_presets_have_valid_unique_keys_and_types():
    keys = [p["key"] for p in presets.PRESETS]
    assert len(keys) == len(set(keys))
    for p in presets.PRESETS:
        assert p["type"] in ("entries", "bullets")
        assert p["key"] not in CORE_SECTION_KEYS
        assert p["title"].strip().casefold() not in CORE_SECTION_TITLES
        assert p["match"], f"preset {p['key']} has no match headings"


def test_every_preset_validates_as_a_resume_extra_section():
    sections = [
        {"key": p["key"], "title": p["title"], "type": p["type"]}
        for p in presets.PRESETS
    ]
    resume = ResumeData.model_validate(
        {"contact": {"name": "A", "email": "a@b.c"}, "extra_sections": sections}
    )
    assert len(resume.extra_sections) == len(presets.PRESETS)


def test_catalog_carries_the_canonical_presets():
    """Content pin: the other tests iterate PRESETS and are vacuous on an empty
    list — this one fails if the catalog is gutted or a canonical key is lost."""
    by_key = {p["key"]: p for p in presets.PRESETS}
    assert len(presets.PRESETS) >= 8
    assert {
        "publications", "presentations", "volunteer", "awards",
        "languages", "licenses", "clearance", "memberships",
    } <= set(by_key)
    # Heading routing that matters across domains: bar admissions and board
    # certifications are licenses, not education/certifications.
    assert "bar admissions" in by_key["licenses"]["match"]
    assert "board certifications" in by_key["licenses"]["match"]
    assert by_key["publications"]["type"] == "entries"
    assert by_key["awards"]["type"] == "bullets"


def test_prompt_block_lists_every_preset():
    block = presets.prompt_block()
    for p in presets.PRESETS:
        assert p["key"] in block
        assert p["title"] in block
        assert p["type"] in block
