from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, field_validator


class ReplaceSummary(BaseModel):
    kind: Literal["replace_summary"]
    value: str | None = None


class ToggleEntry(BaseModel):
    kind: Literal["toggle_entry"]
    # `enabled` exists only on ExperienceEntry/ProjectEntry (schemas/resume.py).
    section: Literal["experience", "projects"]
    index: int
    enabled: bool


class ReplaceBullet(BaseModel):
    kind: Literal["replace_bullet"]
    section: Literal["experience", "projects", "education"]
    index: int
    bullet_index: int
    value: str


class ReplaceSkillsGroup(BaseModel):
    kind: Literal["replace_skills_group"]
    category: str
    items: list[str]


class AddSkillItem(BaseModel):
    kind: Literal["add_skill_item"]
    category: str
    item: str

    @field_validator("item")
    @classmethod
    def _strip_non_empty_item(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("item must not be empty")
        return stripped


class AddBullet(BaseModel):
    kind: Literal["add_bullet"]
    section: Literal["experience", "projects"]
    index: int
    text: str

    @field_validator("text")
    @classmethod
    def _strip_non_empty_text(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("text must not be empty")
        return stripped


class AddEntry(BaseModel):
    """Append a whole entry; `value` is validated against the section's model."""

    kind: Literal["add_entry"]
    section: Literal["experience", "projects", "education"]
    value: dict[str, Any]


class ReplaceEntry(BaseModel):
    """Wholesale replace an entry (covers arbitrary field edits)."""

    kind: Literal["replace_entry"]
    section: Literal["experience", "projects", "education"]
    index: int
    value: dict[str, Any]


class RemoveEntry(BaseModel):
    kind: Literal["remove_entry"]
    section: Literal["experience", "projects", "education"]
    index: int


class RemoveBullet(BaseModel):
    kind: Literal["remove_bullet"]
    section: Literal["experience", "projects", "education"]
    index: int
    bullet_index: int


class ReplaceContact(BaseModel):
    kind: Literal["replace_contact"]
    value: dict[str, Any]


class ReplaceCertifications(BaseModel):
    kind: Literal["replace_certifications"]
    items: list[str]


# --- Custom (extra) section ops ----------------------------------------------
#
# Phase 1 is section-level only: add/replace/remove/move a whole custom section.
# Fine-grained entry/bullet ops inside a custom section are OUT of phase 1 (the
# UI replaces one section atomically). `value` is a raw dict validated against
# the ExtraSection discriminated union in the service (mirrors AddEntry so a bad
# payload becomes a clean ValueError -> HTTP 400, not a parse-time 422). Lookups
# resolve `section_key` against the stored ExtraSection.key.


class AddExtraSection(BaseModel):
    """Append a whole custom section; `value` is validated as an ExtraSection."""

    kind: Literal["add_extra_section"]
    value: dict[str, Any]


class ReplaceExtraSection(BaseModel):
    """Replace the custom section whose key == section_key (key may not change)."""

    kind: Literal["replace_extra_section"]
    section_key: str
    value: dict[str, Any]


class RemoveExtraSection(BaseModel):
    kind: Literal["remove_extra_section"]
    section_key: str


class MoveExtraSection(BaseModel):
    kind: Literal["move_extra_section"]
    section_key: str
    to_index: int


ResumeEdit = Annotated[
    Union[
        ReplaceSummary,
        ToggleEntry,
        ReplaceBullet,
        ReplaceSkillsGroup,
        AddSkillItem,
        AddBullet,
        AddEntry,
        ReplaceEntry,
        RemoveEntry,
        RemoveBullet,
        ReplaceContact,
        ReplaceCertifications,
        AddExtraSection,
        ReplaceExtraSection,
        RemoveExtraSection,
        MoveExtraSection,
    ],
    Field(discriminator="kind"),
]


class ResumeEditRequest(BaseModel):
    ops: list[ResumeEdit]


# ---------------------------------------------------------------------------
# Scope registry
#
# The single source of truth for "which part of the resume does this op
# touch", used by the chat scope guard (services/chat_tools.py) and any
# future surface that needs to authorize ops against a selection. Lives here
# so adding an op kind and forgetting its scope is impossible to miss in
# review (the chat-side copy drifted once — review F3, 2026-07-16).

def op_scope(op: "ResumeEdit") -> tuple[str | None, int | None, int | None]:
    """(section, entry_index, bullet_index) an op targets; None = unscoped level.

    Custom-section ops scope to the section's own KEY (a slug that can never
    shadow a core section name — schema CORE_SECTION_KEYS), matching the
    per-section chips the chat scope picker emits.
    """
    if op.kind == "replace_summary":
        return ("summary", None, None)
    if op.kind == "replace_contact":
        return ("contact", None, None)
    if op.kind in ("replace_skills_group", "add_skill_item"):
        return ("skills", None, None)
    if op.kind == "replace_certifications":
        return ("certifications", None, None)
    if op.kind == "add_extra_section":
        # A new section's key lives in its value payload.
        return ((op.value or {}).get("key"), None, None)
    if op.kind in ("replace_extra_section", "remove_extra_section", "move_extra_section"):
        return (op.section_key, None, None)
    return (
        getattr(op, "section", None),
        getattr(op, "index", None),
        getattr(op, "bullet_index", None),
    )


# ---------------------------------------------------------------------------
# Op reference registry
#
# The other half of the single-source story (op_scope above is the scope
# half): every surface that DESCRIBES the op vocabulary to an agent renders
# it from here instead of hand-writing its own copy. Five copies drifted
# before (SYSTEM.md §11 item 1; two documented whole-resume-PUT incidents on
# the MCP surface). Field names come mechanically from the union; the shape
# lines below are prose and stay hand-written, but live beside the schema and
# are key-checked against the union in tests, so adding an op kind without a
# shape line fails the suite.

def _op_models() -> list[type[BaseModel]]:
    """The union's member models, in declaration order."""
    import typing

    return list(typing.get_args(typing.get_args(ResumeEdit)[0]))


def op_kinds_ordered() -> list[str]:
    """Every op `kind` literal, in union declaration order."""
    import typing

    return [
        typing.get_args(model.model_fields["kind"].annotation)[0]
        for model in _op_models()
    ]


def op_kinds() -> set[str]:
    return set(op_kinds_ordered())


def render_ops_brief() -> str:
    """Compact `kind{field,field}` list (the chat tool-spec flavor), derived
    mechanically from the union so it can never miss or invent a kind."""
    import typing

    parts = []
    for model in _op_models():
        kind = typing.get_args(model.model_fields["kind"].annotation)[0]
        fields = [name for name in model.model_fields if name != "kind"]
        parts.append(f"{kind}{{{','.join(fields)}}}")
    return ", ".join(parts)


# JSON-ish shape line per kind (the MCP docstring flavor). Values carry the
# semantic annotations an agent needs beyond field names; keys are asserted
# equal to op_kinds() in tests/test_resume_edit_reference.py.
OP_SHAPES: dict[str, str] = {
    "replace_summary": '{"kind":"replace_summary","value": str|null}',
    "toggle_entry": '{"kind":"toggle_entry","section":"experience"|"projects","index":int,"enabled":bool}',
    "replace_bullet": '{"kind":"replace_bullet","section":<sec>,"index":int,"bullet_index":int,"value":str}',
    "replace_skills_group": '{"kind":"replace_skills_group","category":str,"items":[str]}  (case-insensitive)',
    "add_skill_item": '{"kind":"add_skill_item","category":str,"item":str}',
    "add_bullet": '{"kind":"add_bullet","section":"experience"|"projects","index":int,"text":str}',
    "add_entry": '{"kind":"add_entry","section":<sec>,"value":<entry object>}  (appends)',
    "replace_entry": (
        '{"kind":"replace_entry","section":<sec>,"index":int,"value":<entry object>}\n'
        "   — the field-level workhorse: replaces ONE entry, scoped to that entry, so\n"
        "     unrelated entries and sections cannot be touched. Send the entry you read\n"
        "     with only the fields you meant to change edited."
    ),
    "remove_entry": '{"kind":"remove_entry","section":<sec>,"index":int}',
    "remove_bullet": '{"kind":"remove_bullet","section":<sec>,"index":int,"bullet_index":int}',
    "replace_contact": '{"kind":"replace_contact","value":<contact object>}',
    "replace_certifications": '{"kind":"replace_certifications","items":[str]}',
    "add_extra_section": '{"kind":"add_extra_section","value":<ExtraSection>}',
    "replace_extra_section": '{"kind":"replace_extra_section","section_key":str,"value":<ExtraSection>}  (key may not change)',
    "remove_extra_section": '{"kind":"remove_extra_section","section_key":str}',
    "move_extra_section": '{"kind":"move_extra_section","section_key":str,"to_index":int}',
}


def render_ops_shapes() -> str:
    """One `- {shape}` line per op, in union declaration order — the MCP
    docstring flavor. A kind missing from OP_SHAPES renders as its brief form
    rather than vanishing (and the parity test fails loudly anyway)."""
    lines = []
    for kind in op_kinds_ordered():
        shape = OP_SHAPES.get(kind, f'{{"kind":"{kind}", ...}}')
        lines.append(f"  - {shape}")
    return "\n".join(lines)
