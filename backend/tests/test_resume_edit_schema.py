import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas.resume_edit import (
    AddBullet,
    AddExtraSection,
    AddSkillItem,
    MoveExtraSection,
    RemoveExtraSection,
    ReplaceBullet,
    ReplaceExtraSection,
    ReplaceSkillsGroup,
    ReplaceSummary,
    ResumeEdit,
    ResumeEditRequest,
    ToggleEntry,
)


def test_request_parses_each_op_kind():
    req = ResumeEditRequest.model_validate(
        {
            "ops": [
                {"kind": "replace_summary", "value": "New summary"},
                {"kind": "toggle_entry", "section": "projects", "index": 1, "enabled": False},
                {
                    "kind": "replace_bullet",
                    "section": "experience",
                    "index": 0,
                    "bullet_index": 2,
                    "value": "Led X.",
                },
                {"kind": "replace_skills_group", "category": "Languages", "items": ["Python", "Go"]},
                {"kind": "add_skill_item", "category": "Additional Skills", "item": "Salesforce"},
            ]
        }
    )
    assert isinstance(req.ops[0], ReplaceSummary)
    assert isinstance(req.ops[1], ToggleEntry)
    assert isinstance(req.ops[2], ReplaceBullet)
    assert isinstance(req.ops[3], ReplaceSkillsGroup)
    assert isinstance(req.ops[4], AddSkillItem)


def test_replace_summary_allows_none_value():
    op = TypeAdapter(ResumeEdit).validate_python({"kind": "replace_summary", "value": None})
    assert isinstance(op, ReplaceSummary)
    assert op.value is None
    assert op.expected_content_hash is None


def test_replace_summary_parses_expected_content_hash():
    op = TypeAdapter(ResumeEdit).validate_python(
        {
            "kind": "replace_summary",
            "value": "New summary",
            "expected_content_hash": "0123456789abcdef",
        }
    )
    assert isinstance(op, ReplaceSummary)
    assert op.expected_content_hash == "0123456789abcdef"


def test_toggle_entry_rejects_non_toggleable_section():
    with pytest.raises(ValidationError):
        TypeAdapter(ResumeEdit).validate_python(
            {"kind": "toggle_entry", "section": "education", "index": 0, "enabled": True}
        )


def test_replace_bullet_allows_education_section():
    op = TypeAdapter(ResumeEdit).validate_python(
        {"kind": "replace_bullet", "section": "education", "index": 0, "bullet_index": 0, "value": "x"}
    )
    assert isinstance(op, ReplaceBullet)
    assert op.expected_content_hash is None


def test_replace_bullet_parses_expected_content_hash():
    op = TypeAdapter(ResumeEdit).validate_python(
        {
            "kind": "replace_bullet",
            "section": "experience",
            "index": 0,
            "bullet_index": 0,
            "value": "x",
            "expected_content_hash": "fedcba9876543210",
        }
    )
    assert isinstance(op, ReplaceBullet)
    assert op.expected_content_hash == "fedcba9876543210"


def test_unknown_kind_rejected():
    with pytest.raises(ValidationError):
        TypeAdapter(ResumeEdit).validate_python({"kind": "delete_entry", "section": "projects", "index": 0})


def test_add_skill_item_rejects_empty_item():
    with pytest.raises(ValidationError):
        TypeAdapter(ResumeEdit).validate_python(
            {"kind": "add_skill_item", "category": "Languages", "item": "  "}
        )


def test_add_skill_item_strips_item():
    op = TypeAdapter(ResumeEdit).validate_python(
        {"kind": "add_skill_item", "category": "Languages", "item": " SQL "}
    )
    assert isinstance(op, AddSkillItem)
    assert op.item == "SQL"


def test_request_parses_add_bullet_op():
    req = ResumeEditRequest.model_validate(
        {
            "ops": [
                {"kind": "add_bullet", "section": "experience", "index": 0, "text": "Led migration."},
                {"kind": "add_bullet", "section": "projects", "index": 1, "text": "Shipped v2."},
            ]
        }
    )
    assert isinstance(req.ops[0], AddBullet)
    assert req.ops[0].section == "experience"
    assert req.ops[0].index == 0
    assert req.ops[0].text == "Led migration."
    assert isinstance(req.ops[1], AddBullet)


def test_add_bullet_rejects_non_bulletable_section():
    with pytest.raises(ValidationError):
        TypeAdapter(ResumeEdit).validate_python(
            {"kind": "add_bullet", "section": "education", "index": 0, "text": "x"}
        )


def test_add_bullet_rejects_empty_text():
    with pytest.raises(ValidationError):
        TypeAdapter(ResumeEdit).validate_python(
            {"kind": "add_bullet", "section": "experience", "index": 0, "text": "  "}
        )


def test_add_bullet_strips_text():
    op = TypeAdapter(ResumeEdit).validate_python(
        {"kind": "add_bullet", "section": "experience", "index": 0, "text": "  Led migration.  "}
    )
    assert isinstance(op, AddBullet)
    assert op.text == "Led migration."


# --- extra (custom) section ops --------------------------------------------


def test_request_parses_each_extra_section_op_kind():
    req = ResumeEditRequest.model_validate(
        {
            "ops": [
                {
                    "kind": "add_extra_section",
                    "value": {"key": "awards", "title": "Awards", "type": "bullets",
                              "bullets": ["First place, 2025"]},
                },
                {
                    "kind": "replace_extra_section",
                    "section_key": "awards",
                    "value": {"key": "awards", "title": "Honors", "type": "bullets",
                              "bullets": ["First place, 2025"]},
                },
                {"kind": "remove_extra_section", "section_key": "awards"},
                {"kind": "move_extra_section", "section_key": "awards", "to_index": 0},
            ]
        }
    )
    assert isinstance(req.ops[0], AddExtraSection)
    assert isinstance(req.ops[1], ReplaceExtraSection)
    assert req.ops[1].section_key == "awards"
    assert isinstance(req.ops[2], RemoveExtraSection)
    assert isinstance(req.ops[3], MoveExtraSection)
    assert req.ops[3].to_index == 0


def test_extra_section_ops_require_their_key_fields():
    # replace/remove/move need section_key; add needs value.
    with pytest.raises(ValidationError):
        TypeAdapter(ResumeEdit).validate_python({"kind": "remove_extra_section"})
    with pytest.raises(ValidationError):
        TypeAdapter(ResumeEdit).validate_python({"kind": "move_extra_section", "section_key": "x"})
    with pytest.raises(ValidationError):
        TypeAdapter(ResumeEdit).validate_python({"kind": "add_extra_section"})
