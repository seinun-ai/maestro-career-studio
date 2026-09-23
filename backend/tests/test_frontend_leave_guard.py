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
    # With nothing unsaved it must stay plain Link: the early return, not its inverse.
    assert 'if (!leaveBlocked("in-app")) return;' in src[on_nav:prevent]
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
    # One registration inside that file too: two would warn twice.
    assert len(re.findall(r"addEventListener\(\s*[\"']beforeunload", src)) == 1
    assert 'leaveBlocked("unload")' in src
    assert "consumeLeaveBypass()" in src


def test_beforeunload_listener_warns():
    # Chrome needs preventDefault; older engines read returnValue. Either missing
    # and a reload drops the edits without a word.
    src = _read("components/leave-guard-listeners.tsx")
    body = src[src.index("const onBeforeUnload") : src.index('addEventListener("beforeunload"')]
    skip = body.index('if (!leaveBlocked("unload") || consumeLeaveBypass()) return;')
    assert skip < body.index("event.preventDefault();", skip)
    assert skip < body.index('event.returnValue = "";', skip)


def test_use_leave_guard_scopes_and_unregisters():
    src = _read("hooks/use-leave-guard.ts")
    # reloadOnly is the "unload" scope: the gap page and settings (Tasks 11, 12)
    # flush on unmount, so an in-app exit must not ask for them.
    assert 'const scope = when ? (reloadOnly ? "unload" : "all") : null;' in src
    effect = src[src.index("useEffect(") :]
    assert "setLeaveGuard(owner, scope);" in effect
    # An editor that unmounts without unregistering blocks every later exit.
    assert "return () => setLeaveGuard(owner, null);" in effect
    assert "[owner, scope]" in effect


def test_global_error_stays_off_the_leave_guard():
    # global-error.tsx replaces the root layout, so it renders outside
    # ConfirmDialogProvider, where useConfirm (inside GuardedLink) throws.
    src = _read("app/global-error.tsx")
    for name in ("guarded-link", "GuardedLink", "useConfirm", "leave-guard"):
        assert name not in src, name


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


def _listeners() -> str:
    return _read("components/leave-guard-listeners.tsx")


def test_every_popstate_goes_through_the_machine():
    # Next's own popstate listener is on window, bubble phase (app-router.js).
    # Capture runs first, so the machine decides before Next renders.
    src = _listeners()
    assert 'addEventListener("popstate", onPopState, { capture: true })' in src
    assert 'removeEventListener("popstate", onPopState, { capture: true })' in src
    handler = src[src.index("const onPopState") : src.index("const onPageShow")]
    # Only our own replay is skipped; every other pop is fed to the machine.
    assert "if (isReplaying()) return;" in handler
    assert handler.count("return") == 1
    assert 'feed({ type: "pop", entry: currentEntry(), length: window.history.length })' in handler
    assert ", event);" in handler


def test_popstate_is_stopped_only_when_the_machine_says_so():
    src = _listeners()
    assert src.count("stopImmediatePropagation()") == 1
    assert 'if (command.type === "stop") event?.stopImmediatePropagation();' in src
    # Chrome ignores history.go() while a popstate is being dispatched.
    assert "if (event) setTimeout(() => later.forEach(perform), 0);" in src


def test_the_machine_is_pure():
    src = _read("lib/leave-guard.ts")
    machine = src[src.index("const POSITION") :]
    code = re.sub(r"/\*.*?\*/|//[^\n]*", "", machine, flags=re.S)
    assert re.search(r"\b(window|document|location|history)\b", code) is None
    for name in ("export function stepGuard(", "export function startGuard("):
        assert name in src


def test_the_position_stamp_spreads_next_state():
    # Next 16.3.0's patched pushState/replaceState pass a state that carries
    # `__NA` straight through; spreading keeps `__NA` and the tree, so a
    # traverse to a stamped entry (or to the sentinel) renders this route.
    store = _read("lib/leave-guard.ts")
    assert "{ ...(state as Record<string, unknown>) }" in store
    assert "return { ...markSentinel(state, sentinel), [POSITION]: at };" in store
    # Next's own reading of an entry: no state is ignored, no `__NA` reloads.
    assert 'kind: "none", sentinel: false, url };' in store
    assert 'kind: fields.__NA === true ? "next" : "foreign",' in store
    src = _listeners()
    assert "replace(stampState(history.state as object, at, sentinel)" in src
    # Installed at module scope, before Next's app router effect captures pushState.
    assert '\nif (typeof window !== "undefined") installPositionStamps();\n' in src
    assert "const push = history.pushState.bind(history);" in src


def test_entry_numbers_survive_the_history_cap():
    # Chrome keeps 50 entries and drops the oldest on a push; history.length
    # stops growing. A push numbered `length - 1` would give every new entry
    # the same number at the cap (first Back dead, Stay corrupting history), so
    # a push is the entry it left + 1, and a new fragment is one above.
    store = _read("lib/leave-guard.ts")
    fn = store[store.index("export function stampAfterWrite(") : store.index("export type GuardPhase")]
    assert 'if (how === "push") return { at: (before.at ?? believedAt ?? length - 2) + 1,' in fn
    frag = store[store.index("function placeFragment(") : store.index("function popped(")]
    assert "if (length > s.length) return from + 1;" in frag
    assert "length - 1" not in frag
    # Next can commit a render (HistoryUpdater's replaceState) after the browser
    # moved but before its popstate; that write must not stand in for the move.
    wrote = store[store.index("function wrote(") : store.index("function placeFragment(")]
    guard = 'if (how === "replace" && entry.at !== null && s.here.at !== null && entry.at !== s.here.at) {'
    assert guard in wrote
    assert wrote.index(guard) < wrote.index("here: entry")


def test_one_machine_across_hot_reloads():
    # The history patch is installed once; the machine lives on its slot, so
    # the listener and the patch never feed two machines.
    src = _listeners()
    assert "slot.guard ??= startGuard(" in src
    assert "stampHooks().guard = next;" in src
    assert "let guard" not in src


def test_sentinel_duplicates_only_app_router_entries():
    src = _listeners()
    fn = src[src.index("function pushSentinel()") : src.index("function restorePage()")]
    guard = fn.index('if (!state || currentEntry().kind !== "next") return;')
    assert guard < fn.index("window.history.pushState(markSentinel(state, true)")


def test_a_leave_never_leaves_the_bypass_set():
    store = _read("lib/leave-guard.ts")
    # Every same-document pop ends the bypass (no unload is coming).
    assert 'out.push({ type: "setBypass", on: false });' in store
    src = _listeners()
    # A Leave's go that brings neither a pop nor an unload falls back.
    assert 'watchLeave(() => run(feed({ type: "stalled" })))' in src
    # A Leave that became a client navigation has no unload to bypass.
    assert "useEffect(() => {\n    clearLeaveBypass();\n  }, [pathname]);" in src
    unload = src[src.index("const onBeforeUnload") :]
    assert unload.index("settleLeave();") < unload.index("consumeLeaveBypass()")


def test_guarded_link_replaces_the_sentinel():
    link = _read("components/guarded-link.tsx")
    assert "if (replace || isSentinelState(window.history.state)) router.replace(" in link


def test_registered_editors_have_no_router():
    # A router.replace to another URL on these pages would turn the Back/Forward
    # sentinel into a different page (a same-URL refresh keeps its flag: see
    # stampAfterWrite). Re-check the machine before adding one.
    for rel in (
        "components/resume-editor/editor-body.tsx",
        "components/resume-editor/tailored-resume-studio.tsx",
        "app/templates/[id]/page.tsx",
    ):
        assert "useRouter" not in _read(rel), rel
