"""The Companion's Apply switches on Settings › Companion › How the Companion applies (source pins; the
browser review is separate). The panel reads the saved values when it binds a tab."""

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_CARD = " ".join((_FRONTEND / "components/settings/form-filling-section.tsx").read_text().split())


def _read_card_shell() -> str:
    return (_FRONTEND / "components/settings/setting-card.tsx").read_text()


def test_the_switches_are_in_their_own_card_with_their_help_lines():
    # Their own card now (design refresh Task 7.3), beside the fields it couldn't operate; the
    # form-filling engine is the card after it.
    assert '<SettingCard id="companion-apply" title="How the Companion applies"' in _CARD
    assert "<CompanionApplySwitches value={data.value} /> <KnownGapsLine />" in _CARD
    assert 'label="Choose the base resume for me"' in _CARD
    assert 'label="Stop after each step"' in _CARD
    assert "Apply picks the best match when it clearly leads, using the limits in Auto-apply." in _CARD
    assert "Apply stops after saving the job, after the resume, and before filling, so you press once for each." in _CARD


def test_each_switch_is_described_by_its_help_line_and_saves_on_toggle():
    assert "aria-describedby={pickHintId}" in _CARD and "aria-describedby={stopHintId}" in _CARD
    assert "aria-describedby={thinkHintId}" in _CARD
    assert 'const COMPANION_APPLY_PATH = "/api/settings/companion-apply";' in _CARD
    assert 'method: "PUT", body: JSON.stringify({ value: next }),' in _CARD
    assert "onCheckedChange={(checked) => change({ auto_pick: checked })}" in _CARD
    assert "onCheckedChange={(checked) => change({ stop_each_step: checked })}" in _CARD
    assert "onCheckedChange={(checked) => change({ think_when_stuck: checked })}" in _CARD
    # A toggle while a save is in flight is not sent; the pick shows at once from the pending value.
    # `value` is the card's loaded setting (SettingCard renders the switches only once it is there).
    assert "if (!save.isPending) saveOnce({ ...value, ...patch });" in _CARD
    assert "const shown = save.isPending ? save.variables : value;" in _CARD


def test_a_failed_load_says_so_and_offers_a_retry():
    # SettingCard's one LoadErrorState, whose Try again refetches the card's query.
    assert 'errorTitle="Couldn\'t load the Apply switches."' in _CARD and "query={setting}" in _CARD
    assert "for (const q of queries) void q.refetch();" in _read_card_shell()
    assert 'toast.error(couldnt("save this setting", err))' in _CARD


def test_think_when_stuck_is_the_third_switch_with_its_help_line():
    assert 'type CompanionApply = { auto_pick: boolean; stop_each_step: boolean; think_when_stuck: boolean };' in _CARD
    assert 'label="Think when stuck"' in _CARD
    assert 'checked={shown.think_when_stuck}' in _CARD
    # After "Stop after each step", before the closing of the group.
    assert _CARD.index('label="Stop after each step"') < _CARD.index('label="Think when stuck"')
    # What it uses, what it costs, when it runs, and what it never does.
    assert (
        "When a run would stop on a page, the Reasoning model looks at it and tries a few fixes first. "
        "Each round costs a few cents. It never answers protected questions and never presses Submit. "
        "Off, the run stops and asks you."
    ) in _CARD
