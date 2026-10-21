"""Pins for the extra leave-guard surfaces (UX next, Task 13, plus the review fixes).

Persona, Prompts and a pasted job description ask before a link drops the text,
and Profile's answers for job forms ask while a failed save leaves them unsaved
(they save as you go since design refresh Task 7.2). Extract on /new starts one
request per click. A save that lands while the user kept typing keeps the later
text.
"""

from __future__ import annotations

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


def _flat(source: str) -> str:
    return " ".join(source.split())


_AUTOFILL = _read("components/profile/autofill-profile.tsx")
_NEW = _read("app/new/page.tsx")


def test_explicit_save_cards_ask_before_leaving():
    assert "useLeaveGuard(dirty)" in _read("components/profile/how-you-come-across.tsx")
    # Autosaved: only a failed write leaves answers on screen the server lacks.
    assert "useLeaveGuard(answers.failed)" in _AUTOFILL
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
    # Every editor's change goes through the one autosave: each edit is queued, the newest goes out next.
    # The edit is counted for its editor's status first (lib/save-surfaces.ts), and each write is the PUT.
    update = _flat(_AUTOFILL[_AUTOFILL.index("update: (surface, next) => {") :])
    assert update.startswith(
        "update: (surface, next) => { track((state) => edited(state, surface)); answers.update(next); },")
    src = _flat(_AUTOFILL)
    assert "useAutosave<Profile>(initial, (next) => {" in src
    assert "return save.mutateAsync(next).then((result) => {" in src


def test_autofill_save_keeps_text_typed_while_it_ran():
    # A save landing re-seeds nothing while an edit is queued or in flight (`adopt` refuses), so text typed
    # while it ran stays and goes out next; the server copy is taken only once every edit is on it.
    src = _flat(_AUTOFILL)
    assert "adopt(profileForEditing(served));" in src
    hook = _flat(_read("lib/use-autosave.ts"))
    assert "if (inFlight.current !== null || failedNow.current) return;" in hook
    assert "if (queued.current !== inFlight.current) { flush(); return; }" in hook
