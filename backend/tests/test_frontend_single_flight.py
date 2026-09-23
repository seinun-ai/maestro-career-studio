"""One submit per click (UX next, Task 19; appendix F4).

`isPending` cannot guard a double click: react-query re-renders its observers
on a zero-delay timeout, so a second click already queued reads `false` and
starts a second request (two referral rows). Each create button and each
studio's Save starts its request through `useSingleFlight`, and nothing else
calls the guarded `mutate`, or the guard never clears (the hook's docstring).
The hook's own shape is pinned in `test_frontend_focus.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

_SITES = [
    ("app/referrals/page.tsx", "create"),
    ("app/templates/page.tsx", "create"),
    ("components/resume-editor/editor-body.tsx", "save"),
    ("components/resume-editor/tailored-resume-studio.tsx", "save"),
]


@pytest.mark.parametrize(("rel", "name"), _SITES)
def test_a_submit_starts_one_request_per_gesture(rel: str, name: str):
    src = (_FRONTEND / rel).read_text()
    guarded = f"useSingleFlight({name}.mutate)"
    assert src.count(guarded) == 1, f"{rel}: {name} is not started through useSingleFlight"
    rest = src.replace(guarded, "")
    # Neither called nor handed on (`onAdd={create.mutate}`) around the guard.
    assert f"{name}.mutate" not in rest, f"{rel}: {name}.mutate is reachable without the guard"
    assert f"{name}.reset(" not in rest, f"{rel}: reset() drops the call that clears the guard"


def test_both_referral_forms_share_the_one_guard():
    page = (_FRONTEND / "app/referrals/page.tsx").read_text()
    assert "const add = useSingleFlight(create.mutate);" in page
    assert page.count("onAdd={add}") == 2
    assert "onAdd={create.mutate}" not in page


def test_template_create_button_goes_through_the_guard():
    page = (_FRONTEND / "app/templates/page.tsx").read_text()
    assert "const createOnce = useSingleFlight(create.mutate);" in page
    assert "onClick={() => createOnce()}" in page


@pytest.mark.parametrize(
    "rel", ["components/resume-editor/editor-body.tsx", "components/resume-editor/tailored-resume-studio.tsx"]
)
def test_studio_save_click_and_shortcut_share_the_guard(rel: str):
    src = (_FRONTEND / rel).read_text()
    assert "const saveOnce = useSingleFlight(save.mutate);" in src
    on_save = src[src.index("const onSave = () =>") :]
    on_save = on_save[: on_save.index(";\n")]
    # Button and Cmd/Ctrl+S both call onSave (StudioSaveButton), so both pass
    # the one guard; the raw draft is applied first, as before.
    assert "raw.commitThen(setData, (applied) =>" in on_save
    assert "saveOnce({" in on_save
