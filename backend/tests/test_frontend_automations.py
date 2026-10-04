"""Pins: the Automations page (docs/plans/2026-10-04-automations-page-design.md).

Copy-only: the page puts a prompt on the clipboard for the chosen agent app and
schedules nothing. Nothing about the user goes into the copied text, Copy is off
for an app Maestro can't reach (and says why), and a failed clipboard write opens
the prompt so it can be selected. There is no frontend test runner, so the
branches that matter are pinned here from the source.
"""

from __future__ import annotations

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


_SIDEBAR = _read("components/app-sidebar.tsx")
_PAGE = _read("app/automations/page.tsx")
_CARD = _read("components/automations/automation-card.tsx")
_LIB = _read("lib/automations.ts")
_STORAGE = _read("hooks/use-local-storage-state.ts")


def test_the_sidebar_lists_automations_between_agent_inbox_and_referrals():
    inbox = _SIDEBAR.index('{ href: "/proposals", label: "Agent inbox"')
    automations = _SIDEBAR.index('{ href: "/automations", label: "Automations"')
    referrals = _SIDEBAR.index('{ href: "/referrals"')
    assert inbox < automations < referrals


def test_the_page_reads_the_catalog_and_points_at_the_connect_guide():
    assert 'apiFetch<AutomationCatalog>("/api/automations")' in _PAGE
    assert 'title="Automations"' in _PAGE
    assert "It asks when to run" in _PAGE
    assert "CONNECT_AGENT_GUIDE_URL" in _PAGE
    assert "Your agent needs to be connected to Maestro first." in _PAGE


def test_copy_is_off_for_an_unreachable_app_and_says_why():
    assert "disabled={!app.reachable}" in _CARD
    # A disabled <button> drops keyboard focus; this one stays focusable and
    # points at the app note.
    assert "focusableWhenDisabled" in _CARD
    assert "aria-describedby={!app.reachable ? disabledReasonId : undefined}" in _CARD
    assert "id={noteId}" in _PAGE
    assert "disabledReasonId={noteId}" in _PAGE
    assert 'aria-live="polite"' in _PAGE


def test_a_failed_clipboard_write_opens_the_prompt_to_select():
    # A missing clipboard API throws at once, before any promise exists.
    assert "Promise.resolve()" in _CARD
    catch = _CARD[_CARD.index(".catch(") :]
    catch = catch[: catch.index("});")]
    assert "setOpen(true)" in catch
    assert "select-all" in _CARD


def test_the_card_copy():
    assert "Prompt copied. Paste it into" in _CARD
    assert "Scheduled applying comes with full automation mode." in _CARD
    assert 'card.id === APPLY_CARD_ID && card.kind === "attended"' in _CARD


def test_a_scheduled_card_gets_the_wrapper_that_asks_when_to_run():
    assert 'card.kind === "scheduled" ? app.preamble : app.attended_preamble' in _LIB


def test_no_cadence_picker_and_nothing_about_the_user_in_the_prompt():
    for src in (_PAGE, _CARD, _LIB):
        for word in ("cadence", "schedule_time", "cron("):
            assert word not in src, word
    # promptFor reads the card and the app, nothing else.
    assert "profile" not in _LIB


def test_the_remembered_app_is_best_effort():
    assert "useLocalStorageState(" in _PAGE
    assert "APP_STORE_KEY" in _PAGE
    # With storage blocked the choice still switches.
    assert "picked ??" in _PAGE
    # The hook guards both the read and the write.
    assert _STORAGE.count("catch") >= 2
