"""Pins for the extra leave-guard surfaces (UX next, Task 13).

Persona, Autofill, Prompts and a pasted job description ask before a link
drops the text. Extract on /new starts one request per click.
"""

from __future__ import annotations

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


def test_explicit_save_cards_ask_before_leaving():
    assert "useLeaveGuard(dirty)" in _read("components/settings/persona-section.tsx")
    assert "useLeaveGuard(dirty)" in _read("components/settings/autofill-section.tsx")
    assert "useLeaveGuard(value !== prompt.value)" in _read(
        "components/settings/prompts-section.tsx"
    )


def test_new_job_page_guards_the_paste_and_extracts_once():
    src = _read("app/new/page.tsx")
    assert "useLeaveGuard(rawText.trim().length > 0 && savedJob === null)" in src
    assert "useSingleFlight(extractJob.mutate)" in src
    rest = src.replace("useSingleFlight(extractJob.mutate)", "")
    assert "extractJob.mutate(" not in rest
