"""The base resume square, its tag and the colour picker (resume-colour plan, Task 4).

Source pins in the style of test_frontend_visual_primitives.py: the frontend has
no component runner, so these read the files for the rules that must not drift.
"""

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_SWATCH = (_FRONTEND / "components/visual/resume-swatch.tsx").read_text(encoding="utf-8")
_PICKER = (_FRONTEND / "components/base-resumes/resume-color-picker.tsx").read_text(encoding="utf-8")
_HOOK = (_FRONTEND / "hooks/use-base-resume-label.ts").read_text(encoding="utf-8")
_INDEX = (_FRONTEND / "components/visual/index.ts").read_text(encoding="utf-8")


def test_the_square_is_a_hidden_two_pixel_cornered_resume_fill():
    swatch = _SWATCH.split("export function ResumeSwatch", 1)[1].split("export function ResumeTag", 1)[0]
    assert 'aria-hidden="true"' in swatch
    assert "resumeColorStyle(hue)" in swatch
    for cls in ("size-2.5", "shrink-0", "rounded-corner-2xs", "bg-resume"):
        assert cls in swatch, cls


def test_round_means_status_and_opacity_means_disabled_so_the_square_has_neither():
    assert "rounded-full" not in _SWATCH
    assert "opacity-" not in _SWATCH and "/50" not in _SWATCH


def test_the_tag_is_the_square_then_the_name():
    tag = _SWATCH.split("export function ResumeTag", 1)[1]
    assert "inline-flex items-center gap-1.5" in tag
    assert tag.index("<ResumeSwatch") < tag.index("{children}")


def test_the_square_is_exported_with_the_visual_primitives():
    assert 'export { ResumeSwatch, ResumeTag } from "./resume-swatch";' in _INDEX


def test_the_picker_is_a_radiogroup_of_checkable_swatches():
    assert 'role="radiogroup"' in _PICKER
    assert 'role="radio"' in _PICKER and "aria-checked" in _PICKER
    assert "RESUME_PRESETS" in _PICKER and "resumeColorStyle" in _PICKER


def test_the_picker_swatch_is_a_control_not_a_pill_and_never_faded():
    """Only the small taken-marker dot is round; the swatch itself is a control's corner."""
    assert "rounded-corner-sm" in _PICKER and "bg-resume" in _PICKER
    round_lines = [line for line in _PICKER.splitlines() if "rounded-full" in line]
    assert all("bg-card" in line for line in round_lines), round_lines
    assert "opacity-" not in _PICKER


def test_a_checked_swatch_draws_a_check_and_the_solid_ring():
    assert "<Check" in _PICKER and "text-primary-foreground" in _PICKER
    assert "outline-2" in _PICKER and "outline-offset-2" in _PICKER and "outline-ring" in _PICKER


def test_a_taken_preset_is_named_and_marked_not_disabled():
    assert ", used by " in _PICKER
    assert "disabled" not in _PICKER  # a taken colour may still be chosen: two resumes can share one


def test_the_arrow_keys_move_between_swatches():
    for key in ("ArrowRight", "ArrowLeft", "ArrowDown", "ArrowUp", "Home", "End"):
        assert f'"{key}"' in _PICKER, key
    assert "tabIndex" in _PICKER  # a roving tab stop: one swatch in the tab order


def test_the_custom_hue_is_a_labelled_range_over_the_whole_wheel():
    assert 'type="range"' in _PICKER and 'min={0}' in _PICKER and 'max={359}' in _PICKER
    assert ">Hue<" in _PICKER
    assert "Custom" in _PICKER and "aria-expanded" in _PICKER


def test_the_random_hint_is_only_for_a_random_pick():
    assert "Picked at random from colors no other resume uses." in _PICKER
    assert "pickedAtRandom" in _PICKER


def test_the_hook_reads_the_archived_inclusive_list():
    hook = _HOOK.split("export function useBaseResumeColor", 1)[1]
    assert "useBaseResumes(true)" in hook and "color_hue" in hook
