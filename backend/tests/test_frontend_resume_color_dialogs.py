"""Colour in the New base resume dialog and the Target dialog (resume-colour plan, Task 6).

Source pins in the style of test_frontend_resume_swatch.py: the frontend has no component runner.
"""

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_NEW = (_FRONTEND / "components/base-resumes/new-base-resume-dialog.tsx").read_text(encoding="utf-8")
_TARGET_FILE = (_FRONTEND / "components/role-category-picker.tsx").read_text(encoding="utf-8")
_STUDIO = (_FRONTEND / "components/resume-editor/editor-body.tsx").read_text(encoding="utf-8")
_PICKER = (_FRONTEND / "components/base-resumes/resume-color-picker.tsx").read_text(encoding="utf-8")


def _squash(src: str) -> str:
    return " ".join(src.split())


def _target() -> str:
    return _TARGET_FILE[_TARGET_FILE.index("export function TargetDialog(") :]


# ── The New base resume dialog ─────────────────────────────────────────────


def test_the_new_dialog_mounts_the_picker_and_starts_at_a_free_random_color():
    new = _squash(_NEW)
    assert "<ResumeColorPicker" in new
    assert "pickFreeHue(" in new and "useBaseResumes(false" in new
    assert "const [seed] = useState(Math.random);" in new
    # Random until the person chooses: the hint is on while nothing was chosen.
    assert "pickedAtRandom={chosen === null}" in new
    assert "const hue = chosen ?? randomHue;" in new
    assert "onChange={setChosen}" in new
    # The picker's `used` is the OTHER resumes, by name.
    assert "baseResumeLabel(r.slug, [r])" in new


def test_every_create_path_sends_the_color():
    request = _squash(_NEW[_NEW.index("const request = async () => {") : _NEW.index("const create = useMutation")])
    # kb, duplicate and blank are JSON bodies; the file lane is FormData.
    assert request.count("color_hue: hue,") == 3
    assert 'form.append("color_hue", String(hue));' in request


def test_start_over_throws_a_chosen_color_away_with_the_rest_of_the_draft():
    assert "chosen !== null" in _squash(_NEW[_NEW.index("const touched =") :])


# ── The Target dialog ──────────────────────────────────────────────────────


def test_target_saves_the_color_on_commit_not_on_every_change():
    dialog = _squash(_target())
    picker = dialog[dialog.index("<ResumeColorPicker") : dialog.index("/>", dialog.index("<ResumeColorPicker")) + 2]
    assert "value={live}" in picker
    assert "onChange={setLive}" in picker
    assert "onCommit={(hue) => saveColor.mutate(hue, { onError: () => setLive(colorHue) })}" in picker
    assert "pickedAtRandom" not in picker
    assert "const saveColor = useAnchorSave(slug, \"color_hue\");" in dialog


def test_target_keeps_the_live_value_in_state_and_follows_the_saved_one():
    dialog = _squash(_target())
    assert "const [live, setLive] = useState(colorHue);" in dialog
    # A changed saved color (a save landing, or another tab) is adopted; a failed save puts it back.
    assert "if (seen !== colorHue) {" in dialog and "setLive(colorHue);" in dialog


def test_the_color_save_invalidates_both_list_keys_and_the_detail_key_and_reports_an_error():
    hook = _squash(_TARGET_FILE[_TARGET_FILE.index("function useAnchorSave<") : _TARGET_FILE.index("/** A Target field:")])
    assert 'qc.setQueryData(["base-resumes", slug], updated);' in hook
    assert 'qc.invalidateQueries({ queryKey: ["base-resumes"] });' in hook  # prefix: both list keys and the detail key
    assert "toast.error(couldnt(`save the ${FIELD_WORDS[field]}`, err))" in hook
    assert 'color_hue: "color"' in _squash(_TARGET_FILE)


def test_the_studio_passes_the_saved_color_to_target():
    dialog = _squash(_STUDIO[_STUDIO.index("<TargetDialog") :][:400])
    assert "colorHue={(live ?? initial).color_hue}" in dialog


# ── The picker, on Safari ──────────────────────────────────────────────────


def test_the_slider_latches_open_on_pointer_down_too():
    """Safari does not focus a range input on click, so onFocus alone never latches the slider before a drag."""
    latch = "if (customOpen === null) setCustomOpen(true);"
    assert f"onPointerDown={{() => {{ {latch} }}}}" in _squash(_PICKER)
    assert f"onFocus={{() => {{ {latch} }}}}" in _squash(_PICKER)
