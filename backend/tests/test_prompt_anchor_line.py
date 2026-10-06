"""The anchor line: what a base resume is written for, in the tailoring prompt."""

from app.services import prompt_assembly
from app.services.prompt_assembly import anchor_block

BODY_TEMPLATE = "Resume=${resume_json}${user_prompt_section}"


def _patch_prompts(monkeypatch):
    monkeypatch.setattr(
        prompt_assembly.prompts, "get_prompt", lambda key: BODY_TEMPLATE
    )


def _gap_prompt(**kwargs):
    return prompt_assembly.build_gap_tailor_prompt(
        {"summary": "Builder"}, {}, resolutions=[], skipped_gaps=[], **kwargs
    )


def test_anchor_block_empty_and_listed():
    assert anchor_block(None, for_job=True) == ""
    assert anchor_block(
        {"countries": [], "role": None, "company": None, "focus": None}, for_job=True
    ) == ""
    text = anchor_block(
        {"countries": ["IN"], "role": "Data Engineer", "company": "Example Corp", "focus": None},
        for_job=False,
    )
    assert text.startswith(
        "RESUME ANCHORS: Countries: India · Role: Data Engineer · Company: Example Corp\n"
    )
    assert "Focus" not in text and "this application's employer" not in text
    assert "The anchor company is the resume's own target and may differ from this application's employer." in anchor_block(
        {"countries": [], "role": None, "company": "Example Bank", "focus": None}, for_job=True
    )


def test_anchor_block_exact_text_and_order():
    text = anchor_block(
        {"countries": ["GB", "IN"], "role": "Data Engineer", "company": "Example Bank",
         "focus": "payments"},
        for_job=True,
    )
    assert text == (
        "RESUME ANCHORS: Countries: United Kingdom, India · Role: Data Engineer"
        " · Company: Example Bank · Focus: payments\n"
        "Emphasize these where relevant. They are not evidence of experience."
        " The anchor company is the resume's own target and may differ from this application's employer."
        "\n\n---\n\n"
    )


def test_anchor_block_degrades_an_unknown_stored_code_to_the_code():
    text = anchor_block(
        {"countries": ["GB", "ZZ"], "role": None, "company": None, "focus": None}, for_job=False
    )
    assert text.startswith("RESUME ANCHORS: Countries: United Kingdom, ZZ\n")


def test_employer_clause_needs_both_for_job_and_a_company():
    only_focus = {"countries": [], "role": None, "company": None, "focus": "payments"}
    assert "employer" not in anchor_block(only_focus, for_job=True)
    with_company = {"countries": [], "role": None, "company": "Example Bank", "focus": None}
    assert "employer" not in anchor_block(with_company, for_job=False)


def test_anchor_text_stays_literal(monkeypatch):
    _patch_prompts(monkeypatch)
    anchors = {"countries": [], "role": None, "company": "$role_label ${x}", "focus": None}
    assert "Company: $role_label ${x}" in anchor_block(anchors, for_job=False)
    assert "Company: $role_label ${x}" in _gap_prompt(anchors=anchors)


def test_gap_tailor_prompt_without_anchors_is_unchanged(monkeypatch):
    _patch_prompts(monkeypatch)
    persona_text = "Quiet builder."
    plain = _gap_prompt(persona=persona_text)
    assert _gap_prompt(persona=persona_text, anchors=None) == plain
    assert "RESUME ANCHORS" not in plain
    assert plain.startswith(
        f"{prompt_assembly._skill_preamble()}\n\n---\n\n"
        f"{prompt_assembly._persona_block(persona_text)}Resume="
    )
    empty = {"countries": [], "role": None, "company": None, "focus": None}
    assert _gap_prompt(persona=persona_text, anchors=empty) == plain


def test_gap_tailor_prompt_puts_the_anchors_after_the_persona(monkeypatch):
    _patch_prompts(monkeypatch)
    anchors = {"countries": ["IN"], "role": None, "company": "Example Corp", "focus": None}
    result = _gap_prompt(persona="Quiet builder.", anchors=anchors)
    assert result.startswith(
        f"{prompt_assembly._skill_preamble()}\n\n---\n\n"
        f"{prompt_assembly._persona_block('Quiet builder.')}"
        f"{anchor_block(anchors, for_job=True)}Resume="
    )
