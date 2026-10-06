"""Field warnings never block a save; they flag a value that looks off (visual-language plan, Task 12)."""

from tests.node_ts import run_node_test


def test_field_checks_node_suite():
    result = run_node_test("lib/field-checks.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr


def _src(path: str) -> str:
    from pathlib import Path

    return (Path(__file__).resolve().parents[2] / "frontend" / path).read_text()


def test_contact_fields_use_the_checks_and_the_shared_message():
    for path in ("components/settings/autofill-section.tsx", "components/resume-editor/contact-form.tsx"):
        src = _src(path)
        assert "emailWarning(" in src
        assert "useFieldMessage" in src
    field = _src("components/resume-editor/field.tsx")
    assert "FieldMessage" in field and "data-warning" in field and "aria-invalid" in field


def test_inputs_style_the_warning_state():
    for path in ("components/ui/input.tsx", "components/ui/textarea.tsx"):
        assert "data-[warning=true]" in _src(path)


def test_answer_questions_is_disabled_while_the_box_is_empty():
    qa = _src("components/qa-tab.tsx")
    assert "disabled={noQuestions}" in qa and "focusableWhenDisabled" in qa and "Type at least one question." in qa
    assert "throw new Error(\"Type at least one question.\")" not in qa
