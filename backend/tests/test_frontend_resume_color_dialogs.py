"""Colour in the New base resume dialog and the Target dialog (resume-colour plan, Task 6).

Source pins in the style of test_frontend_resume_swatch.py: the frontend has no component runner.
"""

from pathlib import Path

from tests._jsx_pins import open_tag, squash
from tests.node_ts import run_node_test

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_NEW = (_FRONTEND / "components/base-resumes/new-base-resume-dialog.tsx").read_text(encoding="utf-8")
_TARGET_FILE = (_FRONTEND / "components/role-category-picker.tsx").read_text(encoding="utf-8")
_STUDIO = (_FRONTEND / "components/resume-editor/editor-body.tsx").read_text(encoding="utf-8")
_PICKER = (_FRONTEND / "components/base-resumes/resume-color-picker.tsx").read_text(encoding="utf-8")

_SEND = "...(hue !== null && { color_hue: hue })"


def _target() -> str:
    return _TARGET_FILE[_TARGET_FILE.index("export function TargetDialog(") :]


def _hook() -> str:
    return squash(_TARGET_FILE[_TARGET_FILE.index("function useAnchorSave<") : _TARGET_FILE.index("/** A Target field:")])


# ── The New base resume dialog ─────────────────────────────────────────────


def test_the_new_dialog_mounts_the_picker_and_starts_at_a_free_random_color():
    new = squash(_NEW)
    picker = open_tag(_NEW, "ResumeColorPicker")
    assert "pickFreeHue(" in new and "useBaseResumes(false" in new
    # Drawn once per form, so the pick holds still while the form re-renders.
    assert "const [seed] = useState(Math.random);" in new
    # The "picked at random" hint is for a pick nobody made, and only once there is one.
    assert "pickedAtRandom={chosen === null && hue !== null}" in picker
    assert "onChange={setChosen}" in picker
    # The picker's `used` is the OTHER resumes, by name.
    assert "baseResumeLabel(r.slug, [r])" in picker


def test_the_new_dialog_holds_no_color_until_the_list_has_loaded():
    """The form stays mounted while closed and loads the list on open: until then there is nothing to pick from, so
    nothing is shown or sent, and the server picks with the same rule."""
    new = squash(_NEW)
    assert "const randomHue = others ? pickFreeHue(" in new and ": null;" in new
    assert "const hue = chosen ?? randomHue;" in new


def test_every_create_path_sends_the_color_when_it_is_known():
    request = squash(_NEW[_NEW.index("const request = async () => {") : _NEW.index("const create = useMutation")])
    # kb, duplicate and blank are JSON bodies; the file lane is FormData.
    assert request.count(_SEND) == 3
    assert 'if (hue !== null) form.append("color_hue", String(hue));' in request


def test_a_chosen_color_counts_as_a_draft_that_start_over_throws_away():
    assert "chosen !== null" in squash(_NEW[_NEW.index("const touched =") :])


# ── The Target dialog ──────────────────────────────────────────────────────


def test_target_saves_a_color_only_when_the_choice_settles():
    """onChange is every drag step and never saves; onCommit saves once."""
    picker = open_tag(_target(), "ResumeColorPicker")
    change = picker[picker.index("onChange=") : picker.index("onCommit=")]
    commit = picker[picker.index("onCommit=") :]
    assert "mutate" not in change
    assert commit.count("saveColor.mutate(") == 1
    assert "pickedAtRandom" not in picker


def test_target_shows_the_drag_then_the_pending_save_then_the_saved_color_with_no_copy_in_state():
    dialog = squash(_target())
    assert "const [drag, setDrag] = useState<number | null>(null);" in dialog
    assert "const shown = drag ?? (saveColor.isPending ? saveColor.variables : colorHue);" in dialog
    assert "value={shown}" in open_tag(_target(), "ResumeColorPicker")
    # A settled choice hands the display from the drag to the save; a failed save falls back to the saved color.
    assert "setDrag(null);" in dialog
    assert "setLive" not in dialog and "seen" not in dialog.split("useAnchorSave", 1)[1].split("return (", 1)[0]


def test_identity_saves_for_one_resume_run_in_order_and_each_field_has_one_toast():
    """A chain per resume, not a mutation `scope`: a queued scoped mutation waits for tab focus and a hidden tab could lose it."""
    hook = _hook()
    assert "scope:" not in squash(_TARGET_FILE)
    assert "mutationFn: (value: AnchorValues[K]) => inOrder(`identity-${slug}`, () => apiFetch" in hook
    role = squash(_TARGET_FILE[_TARGET_FILE.index("export function RoleCategoryPicker(") :])
    assert "inOrder(`identity-${slug}`" in role
    assert 'import { inOrder } from "@/lib/in-order";' in _TARGET_FILE
    assert hook.count("{ id: `anchor-${field}` }") == 2


def test_the_in_order_chain_passes_its_node_tests():
    result = run_node_test("lib/in-order.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_already_checked_swatch_clears_the_drag():
    picker = open_tag(_target(), "ResumeColorPicker")
    assert "onChange={(hue) => setDrag(hue === shown ? null : hue)}" in picker


def test_the_color_save_invalidates_both_list_keys_and_the_detail_key_and_reports_an_error():
    hook = _hook()
    assert 'qc.setQueryData(["base-resumes", slug], updated);' in hook
    assert 'qc.invalidateQueries({ queryKey: ["base-resumes"] });' in hook  # prefix: both list keys and the detail key
    assert "toast.error(couldnt(`save the ${FIELD_WORDS[field]}`, err)" in hook
    assert 'color_hue: "color"' in squash(_TARGET_FILE)


def test_a_hue_of_zero_is_a_color_not_a_cleared_one():
    """0 is falsy: the saved/cleared word must test `!== null` for the color, as `Boolean(updated[field])` would say cleared."""
    assert 'field === "color_hue" ? updated.color_hue !== null' in _hook()


def test_the_studio_passes_the_saved_color_to_target():
    assert "colorHue={(live ?? initial).color_hue}" in squash(_STUDIO[_STUDIO.index("<TargetDialog") :][:400])


# ── The picker, on Safari ──────────────────────────────────────────────────


def test_the_slider_latches_open_on_pointer_down_and_on_focus():
    """Safari does not focus a range input on click, so onFocus alone never latches the slider before a drag."""
    slider = open_tag(_PICKER, "input", after="<input id={sliderId}")
    latch = "{() => { if (customOpen === null) setCustomOpen(true); }}"
    assert f"onPointerDown={latch}" in slider
    assert f"onFocus={latch}" in slider
