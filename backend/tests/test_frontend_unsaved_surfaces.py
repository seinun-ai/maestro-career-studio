"""Pins for the extra leave-guard surfaces (UX next, Task 13, plus the review fixes).

Persona, Autofill, Prompts and a pasted job description ask before a link
drops the text. Extract on /new starts one request per click. A Save that
lands while the user kept typing keeps the later text, and keeps it dirty.
"""

from __future__ import annotations

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


def _flat(source: str) -> str:
    return " ".join(source.split())


_AUTOFILL = _read("components/settings/autofill-section.tsx")
_NEW = _read("app/new/page.tsx")


def test_explicit_save_cards_ask_before_leaving():
    assert "useLeaveGuard(dirty)" in _read("components/settings/persona-section.tsx")
    assert "useLeaveGuard(dirty)" in _AUTOFILL
    assert "useLeaveGuard(value !== prompt.value)" in _read(
        "components/settings/prompts-section.tsx"
    )


def test_new_job_page_guards_only_an_unextracted_paste():
    assert "useLeaveGuard(rawText.trim().length > 0 && savedJob === null)" in _NEW


def test_new_job_page_extracts_once_per_click():
    assert "useSingleFlight(extractJob.mutate)" in _NEW
    assert "onClick={() => extract(undefined)}" in _NEW
    # Any other start (mutate or mutateAsync) bypasses the single flight.
    rest = _NEW.replace("useSingleFlight(extractJob.mutate)", "")
    assert "extractJob.mutate" not in rest


def test_autofill_counts_every_edit():
    update = _AUTOFILL[_AUTOFILL.index("const updateProfile = (") :]
    assert update.index("editRevision.current += 1;") < update.index("setProfile(next);")


def test_autofill_save_keeps_text_typed_while_it_ran():
    # Marking the form clean re-seeds it from the saved copy, overwriting what
    # was typed meanwhile, and disables Save. Clean only if nothing changed.
    src = _flat(_AUTOFILL)
    assert "save.mutate({ value: profileRef.current, revision: editRevision.current })" in src
    assert "if (editRevision.current === revision) setDirty(false);" in src
    assert "setDirty(false)" not in src.replace(
        "if (editRevision.current === revision) setDirty(false);", ""
    )
