"""Parity guards for the op-reference registry (SYSTEM.md §11 item 1).

The pydantic union is ground truth; every surface that DESCRIBES the vocabulary
either renders from the registry (MCP schema field + docstring, chat tool spec)
or is pinned here (the gap_tailor prompt, which deliberately teaches a SUBSET —
the tailor must not remove entries or rewrite contact — so its guard is
prompt-kinds ⊆ schema-kinds, never set-equality).
"""
import re
from pathlib import Path

import app
from app.schemas import resume_edit


def test_registry_keys_match_the_union_exactly():
    assert set(resume_edit.OP_SHAPES) == resume_edit.op_kinds(), (
        "OP_SHAPES drifted from the ResumeEdit union: "
        f"{sorted(set(resume_edit.OP_SHAPES) ^ resume_edit.op_kinds())}"
    )


def test_rendered_brief_names_every_kind_with_its_fields():
    brief = resume_edit.render_ops_brief()
    for kind in resume_edit.op_kinds():
        assert f"{kind}{{" in brief, f"brief omits {kind}"
    # Spot-check a derived field list so a renamed field surfaces here too.
    assert (
        "replace_bullet{section,index,bullet_index,value,expected_content_hash}"
        in brief
    )


def test_rendered_shapes_name_every_kind():
    shapes = resume_edit.render_ops_shapes()
    documented = set(re.findall(r'"kind":"([a-z_]+)"', shapes))
    assert documented == resume_edit.op_kinds()


def test_chat_tool_spec_renders_every_kind():
    from app.services.chat_tools import TOOL_SPECS

    spec = next(s for s in TOOL_SPECS if s["name"] == "edit_resume")
    for kind in resume_edit.op_kinds():
        assert kind in spec["description"], f"chat edit_resume spec omits {kind}"


def test_gap_tailor_prompt_names_only_real_kinds():
    """The prompt file is the seed for the user-editable DB prompt row; a
    renamed or phantom kind here would teach the tailor LLM ops that 400.
    Subset on purpose: the gap tailor is deliberately NOT taught destructive
    kinds (remove_entry, replace_contact, ...)."""
    prompt = (Path(app.__file__).parent / "prompts" / "gap_tailor.txt").read_text()
    mentioned = set(re.findall(r'"kind":\s*"([a-z_]+)"', prompt))
    assert mentioned, "no op kinds found in gap_tailor.txt — did the format change?"
    phantom = mentioned - resume_edit.op_kinds()
    assert not phantom, f"gap_tailor.txt teaches nonexistent op kinds: {sorted(phantom)}"
