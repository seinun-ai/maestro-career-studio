"""The Companion's Apply switches on Settings > AI & models > Form filling (source pins; the browser
review is separate). The panel reads the saved values when it binds a tab."""

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_CARD = " ".join((_FRONTEND / "components/settings/form-filling-section.tsx").read_text().split())


def test_the_two_switches_are_in_the_form_filling_card_with_their_help_lines():
    assert "<CompanionApplySwitches />" in _CARD
    assert 'label="Choose the base resume for me"' in _CARD
    assert 'label="Stop after each step"' in _CARD
    assert "Apply picks the best match when it clearly leads, using the limits in Auto-apply." in _CARD
    assert "Apply stops after saving the job, after the resume, and before filling, so you press once for each." in _CARD


def test_each_switch_is_described_by_its_help_line_and_saves_on_toggle():
    assert "aria-describedby={pickHintId}" in _CARD and "aria-describedby={stopHintId}" in _CARD
    assert 'const COMPANION_APPLY_PATH = "/api/settings/companion-apply";' in _CARD
    assert 'method: "PUT", body: JSON.stringify({ value }),' in _CARD
    assert "onCheckedChange={(checked) => change({ auto_pick: checked })}" in _CARD
    assert "onCheckedChange={(checked) => change({ stop_each_step: checked })}" in _CARD
    # A toggle while a save is in flight is not sent; the pick shows at once from the pending value.
    assert "if (setting.data && !save.isPending) saveOnce({ ...setting.data.value, ...patch });" in _CARD
    assert "const shown = save.isPending ? save.variables : setting.data?.value;" in _CARD


def test_a_failed_load_says_so_and_offers_a_retry():
    assert 'title="Couldn\'t load the Apply switches."' in _CARD
    assert "onRetry={() => void setting.refetch()}" in _CARD
    assert 'toast.error(couldnt("save this setting", err))' in _CARD
