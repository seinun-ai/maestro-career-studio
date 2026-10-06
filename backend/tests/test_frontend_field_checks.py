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


def test_field_message_is_a_live_region_with_a_stable_id():
    field = _src("components/resume-editor/field.tsx")
    body = field[field.index("export function FieldMessage("): field.index("Labelled text input")]
    # `empty:absolute` keeps the live region mounted but out of the parent grid while empty (no 6px gap row);
    # `hidden` would drop it from the accessibility tree.
    assert '<div id={id} aria-live="polite" className="empty:absolute">' in body
    assert "className=\"hidden\"" not in body
    assert "if (!text) return null" not in body  # the wrapper stays mounted
    assert "{text ? (" in body
