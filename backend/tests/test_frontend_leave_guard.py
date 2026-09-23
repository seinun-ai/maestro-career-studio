"""Pins for the leave guard (docs/plans/2026-09-22-ux-next.md Task 1, U1).

Source pins, not behaviour: CI does not run the node tests in
``frontend/lib/leave-guard.test.ts``. Each assertion names the regression
it exists to catch.
"""

from __future__ import annotations

import re
from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_ROOTS = ("app", "components", "hooks", "lib")
_NEXT_LINK = re.compile(r"""from\s+["']next/link["']""")


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


def _sources() -> list[str]:
    found: list[str] = []
    for root in _ROOTS:
        base = _FRONTEND / root
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.suffix in {".ts", ".tsx"} and path.is_file():
                found.append(str(path.relative_to(_FRONTEND)))
    return found


def test_next_link_is_imported_only_by_guarded_link():
    # Match the import, not the word: a comment may mention <Link>.
    found = sorted(rel for rel in _sources() if _NEXT_LINK.search(_read(rel)))
    assert found == ["components/guarded-link.tsx"]


def test_guarded_link_cancels_before_it_asks():
    src = _read("components/guarded-link.tsx")
    on_nav = src.index("onNavigate=")
    blocked = src.index('leaveBlocked("in-app")', on_nav)
    prevent = src.index("event.preventDefault()", blocked)
    ask = src.index("confirmLeave()", prevent)
    assert blocked < prevent < ask
    allow = src.index("allowLeave()")
    assert allow < src.index("router.push(")
    assert allow < src.index("router.replace(")
    # `await` as a keyword. The comment says "awaited", which is not a keyword;
    # an `await confirm()` before preventDefault is too late (link.js reads the
    # flag when onNavigate returns).
    assert re.search(r"\bawait\b", src[:prevent]) is None


def test_leave_confirm_copy():
    src = _read("components/guarded-link.tsx")
    fn = src[src.index("function useConfirmLeave") : src.index("type GuardedLinkProps")]
    assert 'title: "Leave without saving?"' in fn
    assert 'confirmLabel: "Leave"' in fn
    assert 'cancelLabel: "Stay"' in fn
    assert "destructive: true" in fn
    count = sum(_read(rel).count('"Leave without saving?"') for rel in _sources())
    assert count == 1


def test_one_beforeunload_listener():
    hits = sorted(rel for rel in _sources() if "beforeunload" in _read(rel))
    assert hits == ["components/leave-guard-listeners.tsx"]
    src = _read("components/leave-guard-listeners.tsx")
    assert 'leaveBlocked("unload")' in src
    assert "consumeLeaveBypass()" in src


def test_listeners_sit_inside_the_confirm_provider():
    src = _read("app/providers.tsx")
    open_tag = src.index("<ConfirmDialogProvider>")
    listeners = src.index("<LeaveGuardListeners />", open_tag)
    close_tag = src.index("</ConfirmDialogProvider>", listeners)
    assert open_tag < listeners < close_tag


def test_editors_register():
    assert "useLeaveGuard(hasUnsavedChanges)" in _read(
        "components/resume-editor/editor-body.tsx"
    )
    studio = _read("components/resume-editor/tailored-resume-studio.tsx")
    assert "useLeaveGuard(unsaved)" in studio
    assert "useLeaveGuard(dirty)" not in studio
    assert "useLeaveGuard(dirty)" in _read("app/templates/[id]/page.tsx")
    assert not (_FRONTEND / "hooks/use-unsaved-changes-warning.ts").exists()
    for rel in _sources():
        assert "useUnsavedChangesWarning" not in _read(rel), rel


def test_leave_store_is_pure():
    src = _read("lib/leave-guard.ts")
    assert re.search(r"^\s*import\s", src, re.M) is None
    assert 'leaveBlocked(exit: "in-app" | "unload")' in src
    assert "setLeaveGuard(" in src
    assert "allowLeave(" in src
    assert "consumeLeaveBypass(" in src
    # In-app blocking is the "all" scope only. `owners.size > 0` is the unload
    # check; using it for in-app would ask about work a navigation still saves.
    in_app = src.split('if (exit === "unload")', 1)[1]
    assert 'if (scope === "all") return true;' in in_app
    assert "owners.size > 0" not in in_app.split("return false;", 1)[0].split(
        "for (const scope", 1
    )[-1]


def test_back_forward_sentinel_stops_next_before_it_renders():
    # Next's own popstate listener is on window, bubble phase (app-router.js).
    # Capture runs first. stopImmediatePropagation keeps Next from rendering
    # the destination after the URL has already moved.
    listeners = _read("components/leave-guard-listeners.tsx")
    assert 'addEventListener("popstate", onPopState, { capture: true })' in listeners
    assert "stopImmediatePropagation()" in listeners
    store = _read("lib/leave-guard.ts")
    # Next 16.3.0's patched pushState passes a state that already carries
    # `__NA` straight through. The sentinel must spread that state or a
    # traverse to it does not render this route.
    assert "state.__NA" in store
    assert "history.pushState({ ...state," in store
    link = _read("components/guarded-link.tsx")
    sentinel = link.index("onSentinel()")
    assert sentinel < link.index("router.replace(", sentinel)


def test_registered_editors_have_no_router():
    # A router.refresh/replace on these pages would let HistoryUpdater drop the
    # Back/Forward sentinel's marker (U1 option A). Re-check before adding one.
    for rel in (
        "components/resume-editor/editor-body.tsx",
        "components/resume-editor/tailored-resume-studio.tsx",
        "app/templates/[id]/page.tsx",
    ):
        assert "useRouter" not in _read(rel), rel
