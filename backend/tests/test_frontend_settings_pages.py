"""Pins for the Settings and Profile tabs, deep links and the shared tab row
(2026-09-23 UX IA plan, Appendix C §1-§5). Source pins: CI does not run the node
tests in frontend/lib/settings-tabs.test.ts.

Sections: "Tabs", "Deep links", "Tab row" (settings-tabs lane). The settings-cards
lane appends its own sections ("Models", "Rhythm") below them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


# --------------------------------------------------------------------------- Tabs

_TABS_LIB = _read("lib/settings-tabs.ts")
_TAB_ROW = re.compile(r'\{\s*value: "(\w+)",\s*label: "[^"]*",\s*anchors: \[([^\]]*)\]')
_IMPORT = re.compile(r'import\s*\{([^}]*)\}\s*from\s*"@/components/settings/([\w-]+)"')
_CARD_ID = re.compile(r'<(?:SettingCard|Card)\b[^>]*?\bid="([\w-]+)"', re.S)


def _tab_table(name: str) -> dict[str, set[str]]:
    start = _TABS_LIB.index(f"export const {name} = [")
    block = _TABS_LIB[start : _TABS_LIB.index("] as const", start)]
    return {v: set(re.findall(r'"([\w-]+)"', a)) for v, a in _TAB_ROW.findall(block)}


def _panels(src: str, values: list[str]) -> dict[str, str]:
    start = src.index("panels={{")
    block = src[start : src.index("}}\n", start)]
    marks = sorted((re.search(rf"\b{v}: ", block).start(), v) for v in values)
    bounds = [at for at, _ in marks] + [len(block)]
    return {v: block[bounds[i] : bounds[i + 1]] for i, (_, v) in enumerate(marks)}


def test_the_tab_table_is_node_loadable_and_resolves_card_bodies_by_prefix():
    assert "import " not in _TABS_LIB  # node --test loads it bare
    assert '["autofill-", "autofill"]' in _TABS_LIB
    # The default tab's URL carries no ?tab= (the analytics precedent).
    assert 'tab === defaultTab(page) ? ""' in _TABS_LIB
    # Tab names are owner decision 10; slugs are never shown.
    assert list(_tab_table("SETTINGS_TABS")) == ["models", "tailoring", "agents", "appearance", "about"]
    assert list(_tab_table("PROFILE_TABS")) == ["you", "autofill"]
    for label in ("AI & models", "Tailoring", "Connected agents", "Appearance", "About", "About you", "Autofill"):
        assert f'label: "{label}"' in _TABS_LIB, label


@pytest.mark.parametrize(
    ("page", "table"),
    [("app/settings/page.tsx", "SETTINGS_TABS"), ("app/profile/page.tsx", "PROFILE_TABS")],
)
def test_every_card_id_resolves_to_the_tab_that_renders_it(page, table):
    """A deep link opens the tab `tabForAnchor` names. A card moved to another panel without
    its id moving in lib/settings-tabs.ts would land on the wrong tab, ringing nothing."""
    tabs = _tab_table(table)
    src = _read(page)
    files = {
        name.strip(): f"components/settings/{mod}.tsx"
        for names, mod in _IMPORT.findall(src)
        for name in names.split(",")
        if name.strip()
    }
    for value, body in _panels(src, list(tabs)).items():
        rendered = {n for n in re.findall(r"<(\w+)\b", body) if n in files}
        assert rendered, f"{page}: panel {value} renders no settings card"
        ids = {i for n in rendered for i in _CARD_ID.findall(_read(files[n]))}
        assert ids and ids <= tabs[value], (page, value, sorted(ids - tabs[value]))


def test_tab_panels_stay_mounted_and_the_url_is_written_natively():
    src = _read("components/settings/settings-tabs.tsx")
    panel = src[src.index("<TabsContent") : src.index("</TabsContent>")]
    assert "keepMounted" in panel
    assert "data-settings-tab={t.value}" in panel
    assert "id=" not in panel  # Base UI's panel id is the tab's aria-controls target
    select = src[src.index("const select = (") :]
    assert 'window.history.replaceState(null, "", tabHref(page, value));' in select
    # A router.replace fetches the page's RSC payload on every click.
    assert "useRouter" not in src
    assert re.search(r"\brouter\.(?:replace|push)\(", src) is None
    assert "useSyncExternalStore(subscribeToLocation, readAnchor, noAnchor)" in src
    # The live URL, not the page's searchParams prop: the prop keeps the arrival value after a
    # native replaceState, so a link to another tab of the same page opened nothing.
    assert 'parseTab(page, useSearchParams().getAll("tab"))' in src
    assert "param" not in src


def test_both_pages_read_their_search_params_so_the_server_renders_the_tab():
    """`use(searchParams)` makes the route dynamic: the server renders the tab `?tab=` names (an
    internal link that carries it never flashes the default one), and SettingsTabs'
    useSearchParams needs no Suspense boundary. Without it `next build` prerenders the page
    and fails ("useSearchParams() should be wrapped in a suspense boundary")."""
    for page, name in (("app/settings/page.tsx", "settings"), ("app/profile/page.tsx", "profile")):
        src = _read(page)
        assert "\n  use(searchParams);\n" in src, page
        assert f'<SettingsTabs\n        page="{name}"\n        panels={{{{' in src, page
        assert "useSearchParams(" not in src, page  # the page itself needs no Suspense


def test_connected_agents_keeps_its_order_and_a_place_for_the_explainer():
    """Planner decision 18 (Q2): the explainer card (wave 2) first, then the hints, then
    Auto-apply. The hints and Auto-apply are pinned here; the explainer's lane extends it."""
    agents = _panels(_read("app/settings/page.tsx"), list(_tab_table("SETTINGS_TABS")))["agents"]
    assert "Connected agents explainer" in agents  # the mount point
    assert agents.index("Connected agents explainer") < agents.index("<McpWorkflowSection />")
    assert agents.index("<McpWorkflowSection />") < agents.index("<AutoApplySection />")


def test_profile_lands_a_hash_once():
    """Planner decision 18 (Q9): one `useFocusSection()` on /profile, so a hash landing polls
    and rings once. The strip is handed the page's `focus`."""
    page = _read("app/profile/page.tsx")
    assert page.count("useFocusSection()") == 1
    assert "<SetupStatusStrip" in page and "focus={focus}" in page
    strip = _read("components/setup/setup-status-strip.tsx")
    assert '"@/lib/use-focus-section"' not in strip
    assert "useFocusSection()" not in strip
    assert "focus: (anchor: string) => void;" in strip


# --------------------------------------------------------------------- Deep links

_SOURCES = [
    p
    for d in ("app", "components", "lib", "hooks")
    for p in (_FRONTEND / d).rglob("*.ts*")
    if ".test." not in p.name
]
_COMMENT = re.compile(r"/\*.*?\*/|^\s*//[^\n]*", re.S | re.M)


def test_links_into_settings_and_profile_name_their_tab():
    """A hash-only link renders the default tab on the server and flips after hydration; every
    in-app link goes through anchorHref so the server renders the right tab. Comments may
    quote a hash-only example."""
    offenders = [
        str(p.relative_to(_FRONTEND))
        for p in _SOURCES
        if re.search(r"""["'`]/(?:settings|profile)#""", _COMMENT.sub("", p.read_text()))
    ]
    assert offenders == [], offenders
    assert "anchorHref(step.home, step.anchor)" in _read("components/setup/setup-steps.ts")
    assert "anchorHref(row.home, row.anchor)" in _read("components/setup/getting-started-card.tsx")
    assert 'anchorHref("/profile", group ?' in _read("components/job-knockout-card.tsx")
    assert 'anchorHref("/settings", "api-keys")' in _read("app/new/page.tsx")


def test_a_section_lands_only_once_it_is_shown():
    src = _read("lib/use-focus-section.ts")
    assert "el.getClientRects().length > 0" in src
    assert 'window.dispatchEvent(new HashChangeEvent("hashchange"))' in src
    assert "window.history.replaceState(null, \"\", `${pathname}${search}#${anchor}`);" in src
    # A bare getElementById poll rang a card hidden in another tab and stopped.
    assert "const el = document.getElementById(hash);\n      if (el) {" not in src
    # The landing and an in-page jump share one poll, and the landing's cleanup cancels it.
    assert src.count("whenShown(") == 3  # the definition and its two callers
    assert "cancel();" in src


# ------------------------------------------------------------------------ Tab row


def test_a_tab_row_scrolls_inside_itself_instead_of_widening_the_page():
    """A `w-fit` row of `whitespace-nowrap` triggers was as wide as its labels: at 375px the
    job page's Q&A tab ran off-screen and the five Settings tabs (~480px) widened the page."""
    tabs = _read("components/ui/tabs.tsx")
    section = tabs[tabs.index("const tabsListVariants") : tabs.index("function TabsList")]
    base = re.search(r'^\s*"(group/tabs-list [^"]*)"', section, re.M).group(1)  # the class string, not comments
    for cls in (
        "max-w-full",
        "justify-center-safe",
        "group-data-horizontal/tabs:overflow-x-auto",
        "group-data-horizontal/tabs:[scrollbar-width:none]",
        "group-data-horizontal/tabs:[&::-webkit-scrollbar]:hidden",
        # Base UI's scroll-into-view walks offsetParents to the row: without `relative` a
        # dialog's padding was counted and Home left the first tab 16px under the edge.
        "group/tabs-list relative ",
        # A tab scrolled to an end keeps the row's 3px padding, room for its focus ring.
        "group-data-horizontal/tabs:scroll-px-[3px]",
    ):
        assert cls in base, cls
    # Centred overflow clips the first tab out of reach.
    assert re.search(r"\bjustify-center\b(?!-)", base) is None
    # A Tabs that is a grid item (the New base resume dialog) took the row's full label width
    # as its minimum, so the row widened the dialog instead of scrolling.
    root = tabs[tabs.index("function Tabs(") : tabs.index("const tabsListVariants")]
    assert re.search(r'^\s*"group/tabs flex min-w-0 ', root, re.M)
