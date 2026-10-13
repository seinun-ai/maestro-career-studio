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


def test_a_checked_swatch_draws_a_check_and_the_solid_outline():
    assert "<Check" in _PICKER and "text-primary-foreground" in _PICKER
    assert 'on && "outline-2 outline-offset-2 outline-ring"' in _PICKER


def test_focus_is_a_separate_outer_ring_not_the_selected_outline():
    """A focused swatch must not look checked: focus is a box-shadow ring outside the outline."""
    ring = "focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-4 focus-visible:ring-offset-card"
    assert ring in _PICKER
    assert "focus-visible:outline" not in _PICKER
    assert "outline-none" not in _PICKER.replace("`outline-none`", "")  # it would blank the outline utilities


def test_a_taken_preset_is_named_and_marked_not_disabled():
    assert ", used by " in _PICKER
    # A taken color may still be chosen: two resumes can share one.
    assert "disabled={" not in _PICKER and "aria-disabled" not in _PICKER


def test_the_arrow_keys_move_between_swatches():
    for key in ("ArrowRight", "ArrowLeft", "ArrowDown", "ArrowUp", "Home", "End"):
        assert f'"{key}"' in _PICKER, key
    assert "tabIndex" in _PICKER  # a roving tab stop: one swatch in the tab order


def test_the_custom_hue_is_a_labelled_range_over_the_whole_wheel():
    for part in ('type="range"', "min={0}", "max={359}", ">Hue<"):
        assert part in _PICKER, part
    assert "aria-valuetext={presetName(value) ?? `Hue ${value ?? 0}`}" in _PICKER


def test_custom_opens_the_slider_and_a_custom_value_that_arrives_late_opens_it_too():
    assert "Custom" in _PICKER
    assert "aria-expanded={sliderOpen}" in _PICKER
    assert "aria-controls={sliderOpen ? sliderId : undefined}" in _PICKER
    assert "customOpen ?? isCustom" in _PICKER


def test_the_slider_stays_open_once_used_and_a_click_on_the_checked_swatch_is_no_new_choice():
    # A drag onto a preset hue would otherwise unmount the slider before its pointerup commits.
    assert "onFocus={() => { if (customOpen === null) setCustomOpen(true); }}" in _PICKER
    assert "if (preset.hue !== value) onCommit?.(preset.hue)" in _PICKER
    assert "p-1.5" in _PICKER  # the 6px focus ring stays inside the group


def test_the_picker_separates_the_live_value_from_the_settled_choice():
    """onChange is every step; onCommit is once per choice: a click, a keyup, the slider's pointerup, keyup or blur."""
    assert "onCommit?: (hue: number) => void;" in _PICKER
    assert "onCommit?.(preset.hue)" in _PICKER
    assert "onKeyUp" in _PICKER and "onPointerUp={settle} onKeyUp={settle} onBlur={settle}" in _PICKER


def test_the_random_hint_is_only_for_a_random_pick():
    assert "Picked at random from colors no other resume uses." in _PICKER
    assert "pickedAtRandom" in _PICKER


def test_the_hook_is_a_lookup_over_the_archived_inclusive_list():
    """Same shape as useBaseResumeLabel, so a row in a .map() can call it."""
    hook = _HOOK.split("export function useBaseResumeColor", 1)[1].split("/**", 1)[0]
    assert "useBaseResumes(true)" in hook and "useCallback((slug: string)" in hook
    assert "color_hue" in hook and "[data]" in hook
