import pytest
from pydantic import ValidationError

from app.schemas.formatting import ResumeFormatting, merge_formatting


def test_defaults_match_classic():
    fmt = ResumeFormatting()
    assert fmt.font_size == 11
    assert fmt.side_margins == 0.4
    assert fmt.top_bottom_margin == 0.3
    assert fmt.section_spacing == 6
    assert fmt.entry_spacing == 0
    assert fmt.line_spacing == 1.0
    assert fmt.bullet_icon == "bullet"
    assert fmt.hide_divider is False
    assert fmt.header_align == "center"
    assert fmt.justify is False
    assert fmt.date_format == "verbatim"
    assert fmt.education_order == "degree_first"
    assert fmt.skills_layout == "inline"


def test_merge_layers_later_wins():
    fmt = merge_formatting({"font_size": 10}, {"font_size": 12, "justify": True})
    assert fmt.font_size == 12
    assert fmt.justify is True
    assert fmt.header_align == "center"  # untouched -> default


def test_merge_ignores_none_layers_and_none_values():
    fmt = merge_formatting(None, {"side_margins": None, "section_spacing": 10})
    assert fmt.side_margins == 0.4
    assert fmt.section_spacing == 10


def test_rejects_unknown_keys_and_out_of_range():
    with pytest.raises(ValidationError):
        ResumeFormatting(font_size=14)
    with pytest.raises(ValidationError):
        ResumeFormatting(nonsense=True)
    with pytest.raises(ValidationError):
        ResumeFormatting(side_margins=2.0)


def test_overlay_merges_partials_without_filling_defaults():
    from app.schemas.formatting import overlay

    assert overlay({"font_size": 12}, {"header_align": "left"}) == {
        "font_size": 12,
        "header_align": "left",
    }
    assert overlay({"font_size": 12}, {"font_size": 10}) == {"font_size": 10}  # later wins
    assert overlay(None, {"justify": True}) == {"justify": True}
    assert overlay(None, None) == {}
