"""Pins: the sidebar SHOWS and ANNOUNCES the current page, and its create
action is the M3 FAB. See docs/plans/2026-09-22-honest-studio.md, Task 2."""

from __future__ import annotations

import re
from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_SIDEBAR = (_FRONTEND / "components/app-sidebar.tsx").read_text()
_UI = (_FRONTEND / "components/ui/sidebar.tsx").read_text()
_REVEAL = (_FRONTEND / "components/sidebar-reveal-trigger.tsx").read_text()


def test_nav_links_carry_aria_current():
    assert "navCurrent(" in _SIDEBAR
    assert "aria-current={current}" in _SIDEBAR


def _menu_button_base() -> str:
    # The cva BASE string only: `SidebarMenuSubButton` further down still
    # carries shadcn's neutral active style, and the app never renders it.
    start = _UI.index("const sidebarMenuButtonVariants = cva(")
    open_quote = _UI.index('"', start)
    return _UI[open_quote + 1 : _UI.index('"', open_quote + 1)]


def test_active_row_is_a_tinted_indicator_distinct_from_hover():
    # Exact tokens, not substrings: "hover:bg-sidebar-accent" is also inside
    # "data-open:hover:bg-sidebar-accent", so a substring check passes even
    # with the neutral hover deleted.
    toks = set(_menu_button_base().split())
    for tok in (
        "data-active:bg-secondary-container",
        "data-active:font-semibold",
        "data-active:text-on-secondary-container",
        # `data-active` is a zero-specificity :where(), so the bare fill and
        # label lose to `hover:` on the active row without these pairs.
        "data-active:hover:bg-secondary-container-hover",
        "data-active:hover:text-on-secondary-container",
        "data-active:[&_svg]:text-primary",
        "hover:bg-sidebar-accent",  # hover stays neutral
    ):
        assert tok in toks, tok
    assert "data-active:bg-sidebar-accent" not in toks


def test_create_action_is_the_fab_variant():
    # Current on /new is the full-strength primary; everywhere else it stays fab.
    assert re.search(r'variant:\s*fabCurrent \? "default" : "fab"', _SIDEBAR)
    assert "bg-primary/15" not in _SIDEBAR


def test_offcanvas_sidebar_is_inert_when_collapsed():
    start = _UI.index('data-slot="sidebar-container"')
    end = _UI.index('data-slot="sidebar-inner"', start)
    assert "inert={offcanvasHidden}" in _UI[start:end]


def test_job_pages_read_from_under_suspense():
    assert "<Suspense" in _SIDEBAR
    assert "useSearchParams()" in _SIDEBAR
    # Node tests cover the mapping; CI only runs this file, so pin the branch.
    nav = (_FRONTEND / "lib/nav.ts").read_text()
    assert 'from === "proposals" ? "/proposals" : "/applications"' in nav


def test_nav_fallback_never_marks_a_wrong_section():
    """The Suspense fallback is server-rendered before `?from=` is read. It
    passes `from` as UNKNOWN (undefined), and a job page with an unknown
    `from` marks no section: `null` there painted Applications current for a
    job opened from proposals until the real nav replaced it."""
    assert "<Suspense fallback={<MainNav pathname={pathname} from={undefined} />}>" in _SIDEBAR
    nav = (_FRONTEND / "lib/nav.ts").read_text()
    jobs = nav[nav.index('if (pathname === "/jobs"') :]
    assert jobs.index("if (from === undefined) return null;") < jobs.index('from === "proposals"')
    assert "section !== null &&" in nav


def test_hiding_the_sidebar_hands_focus_to_the_reveal_pill():
    """A collapse makes the container inert, so focus inside it would drop to
    <body>; the pill takes it. Reopening sends focus back to the in-sidebar
    trigger when the pill unmounts with it. Transitions only, never on load."""
    assert "ref={ref}" in _REVEAL
    assert "if (was.current === hidden) return;" in _REVEAL
    assert (
        "if (orphaned || active?.closest('[data-slot=\"sidebar-container\"]')) "
        "ref.current?.focus();"
    ) in _REVEAL
    assert "'[data-slot=\"sidebar-container\"] [data-sidebar=\"trigger\"]'" in _REVEAL
    # The selectors must name attributes the primitive really renders.
    assert 'data-slot="sidebar-container"' in _UI
    assert 'data-sidebar="trigger"' in _UI


def test_sidebar_toggles_name_their_shortcut():
    for src in (_SIDEBAR, _REVEAL):
        assert 'shortcutLabel(mod, "B")' in src  # visible hint (title)
        assert 'aria-keyshortcuts="Meta+B Control+B"' in src  # programmatic


def test_the_sidebar_uses_the_glossary_names():
    # docs/frontend-conventions.md, Canonical terms (appendix D7.1).
    for present in ('label: "Career history"', 'label: "Base resumes"', 'label: "Assistant"', "Add job\n"):
        assert present in _SIDEBAR, present
    for gone in ("Career KB", "Base Resumes", 'label: "Chat"', "New application"):
        assert gone not in _SIDEBAR, gone


def test_the_sidebar_toggles_name_what_a_press_does():
    # "Toggle" named the mechanism; each control says the result (appendix D7.1).
    assert "title={`Hide sidebar (${shortcutLabel(mod, \"B\")})`}" in _SIDEBAR
    assert "title={`Show sidebar (${shortcutLabel(mod, \"B\")})`}" in _REVEAL
    assert '{open ? "Hide sidebar" : "Show sidebar"}' in _UI
    assert "const open = isMobile ? openMobile : state === \"expanded\"" in _UI
    assert "Toggle" not in _SIDEBAR + _REVEAL + _UI.replace("toggleSidebar", "")
