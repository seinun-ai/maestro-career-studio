"""Pins: the Automations page (docs/plans/2026-10-04-automations-page-design.md).

Copy-only: the page puts a prompt on the clipboard for any connected agent app
and schedules nothing. Nothing about the user goes into the copied text, Copy is
always on, and a failed clipboard write opens the prompt so it can be selected.
There is no frontend test runner, so the branches that matter are pinned here
from the source.
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
_LIB_RUNS = _read("lib/agent-runs.ts")


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
    assert "Apps that run only in a browser can't reach it yet." in _PAGE


def test_one_prompt_for_every_agent_app():
    assert not (_FRONTEND / "components/automations/app-picker.tsx").exists()
    for src in (_PAGE, _CARD, _LIB):
        for word in ("AppPicker", "reachable", "AgentApp", "APP_STORE_KEY", "promptFor"):
            assert word not in src, word
    # Copy is always on; a disabled Copy would also lose keyboard focus.
    assert "disabled" not in _CARD


def test_a_failed_clipboard_write_opens_the_prompt_to_select():
    # useCopy owns the clipboard call (and the missing-API throw); the card handles the `false` branch.
    assert "useCopy" in _CARD and "navigator.clipboard" not in _CARD
    # The `false` branch (the hook already toasted via onError) opens the prompt.
    failed = _CARD[_CARD.index("if (ok)") :]
    failed = failed[: failed.index("\n  }\n")]
    assert "setOpen(true)" in failed and "else" in failed
    assert "select-all" in _CARD


def test_the_card_copy():
    assert "Prompt copied. Paste it into your agent app." in _CARD
    assert "Scheduled applying comes with full automation mode." in _CARD
    assert 'card.id === APPLY_CARD_ID && card.kind === "attended"' in _CARD


def test_last_ran_uses_cached_data_and_fails_quietly_without_it():
    assert 'apiFetch<AgentRunList>("/api/agent-runs/latest")' in _PAGE
    assert "const ran = runs.data ? latestByAutomation(runs.data.items) : null;" in _PAGE
    assert "lastRun={ran ? (ran.get(card.id)?.finished_at ?? null) : undefined}" in _PAGE
    assert "outcome={ran?.get(card.id)?.outcome}" in _PAGE
    assert 'title="Couldn\'t load runs.' not in _PAGE
    assert "isLoadFailure(runs)" not in _PAGE


def test_each_card_says_when_it_last_ran():
    assert "AGENT_RUNS_LATEST_KEY" in _PAGE
    assert 'apiFetch<AgentRunList>("/api/agent-runs/latest")' in _PAGE
    assert "lastRanLine(lastRun, formatTimeAgo)" in _CARD


def test_the_catalog_stays_db_free():
    # The Last ran line comes from its own read; GET /api/automations reads no table.
    assert "agent-runs" not in _LIB


def test_the_card_copies_the_prompt_the_backend_built():
    assert "const text = card.prompt;" in _CARD


def test_no_cadence_picker_and_nothing_about_the_user_in_the_prompt():
    for src in (_PAGE, _CARD, _LIB):
        for word in ("cadence", "schedule_time", "cron("):
            assert word not in src, word
    assert "profile" not in _LIB


def test_small_surfaces_gain_their_glyphs():
    card = _CARD
    assert "CONCEPT_ICONS.scheduled" in card and "CONCEPT_ICONS.notRun" in card
    assert "<CONCEPT_ICONS.cannot " in _read("components/settings/connected-agents-card.tsx")
    assert "CONCEPT_ICONS.cannot" in _CARD and "Globe2" in _CARD and "<Ban " not in _CARD
    assert "MessageSquareText" in _read("components/qa-tab.tsx")
    # The outcome glyph is Task 21's component, not a copy; lib/agent-runs.ts stays import-free.
    assert 'from "@/components/proposals/run-outcome"' in card
    assert "import " not in _LIB_RUNS


def test_the_connect_note_is_a_callout_until_an_automation_has_run():
    assert "bg-secondary-container text-on-secondary-container rounded-corner-md" in _PAGE
    assert "const anyRan = !!ran && !!data && data.cards.some((c) => ran.has(c.id));" in _PAGE
    # A failed runs query still shows the callout; nothing shows only while runs or the catalog are loading.
    assert "const noteReady = runs.isError || (!!runs.data && !!data);" in _PAGE
    assert "{!noteReady ? null : anyRan ? (" in _PAGE


def test_email_and_cover_letter_have_one_glyph_each():
    assert "CONCEPT_ICONS.email" in _CARD and "AtSign" not in _CARD
    assert "CONCEPT_ICONS.coverLetter" in _read("components/qa-tab.tsx")
    assert "CONCEPT_ICONS.email" in _read("components/career/profile-panel.tsx")
