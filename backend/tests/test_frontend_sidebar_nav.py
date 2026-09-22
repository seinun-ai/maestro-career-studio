"""Pins: the sidebar SHOWS and ANNOUNCES the current page, and its create
action is the M3 FAB. See docs/ux/research-studio-and-ui-direction.md Part B
C1, C2 and C5."""

from __future__ import annotations

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
    assert 'variant: "fab"' in _SIDEBAR
    assert "bg-primary/15" not in _SIDEBAR


def test_sidebar_toggles_name_their_shortcut():
    for src in (_SIDEBAR, _REVEAL):
        assert 'shortcutLabel(mod, "B")' in src  # visible hint (title)
        assert 'aria-keyshortcuts="Meta+B Control+B"' in src  # programmatic
