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


def test_both_pages_read_the_tab_from_their_search_params():
    """`searchParams` + `use()` (the job page's pattern): the server renders the named tab, so
    an internal link that carries `?tab=` never flashes the default one, and no Suspense
    boundary is needed (useSearchParams under the root layout would need one)."""
    for page, name in (("app/settings/page.tsx", "settings"), ("app/profile/page.tsx", "profile")):
        src = _read(page)
        assert "const { tab } = use(searchParams);" in src, page
        assert f'<SettingsTabs\n        page="{name}"\n        param={{tab}}' in src, page
        assert "useSearchParams" not in src, page


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
