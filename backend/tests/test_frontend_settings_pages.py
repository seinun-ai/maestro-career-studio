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


def _card_ids_by_panel(page: str, values: list[str]) -> dict[str, set[str]]:
    """The card ids each panel of `page` renders, read from the settings components it imports."""
    src = _read(page)
    files = {
        name.strip(): f"components/settings/{mod}.tsx"
        for names, mod in _IMPORT.findall(src)
        for name in names.split(",")
        if name.strip()
    }
    found: dict[str, set[str]] = {}
    for value, body in _panels(src, values).items():
        rendered = {n for n in re.findall(r"<(\w+)\b", body) if n in files}
        found[value] = {i for n in rendered for i in _CARD_ID.findall(_read(files[n]))}
    return found


@pytest.mark.parametrize(
    ("page", "table"),
    [("app/settings/page.tsx", "SETTINGS_TABS"), ("app/profile/page.tsx", "PROFILE_TABS")],
)
def test_every_card_id_resolves_to_the_tab_that_renders_it(page, table):
    """A deep link opens the tab `tabForAnchor` names. A card moved to another panel without
    its id moving in lib/settings-tabs.ts would land on the wrong tab, ringing nothing."""
    tabs = _tab_table(table)
    for value, ids in _card_ids_by_panel(page, list(tabs)).items():
        assert ids, f"{page}: panel {value} renders no settings card"
        assert ids <= tabs[value], (page, value, sorted(ids - tabs[value]))


def test_tab_panels_stay_mounted():
    src = _read("components/settings/settings-tabs.tsx")
    panel = src[src.index("<TabsContent") : src.index("</TabsContent>")]
    assert "keepMounted" in panel
    assert "data-settings-tab={t.value}" in panel
    assert "id=" not in panel  # Base UI's panel id is the tab's aria-controls target


def test_the_tab_is_read_live_and_written_natively():
    src = _read("components/settings/settings-tabs.tsx")
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


def _body(src: str, start: str, end: str) -> str:
    """The code between two markers, comments stripped."""
    chunk = src[src.index(start) : src.index(end, src.index(start))]
    return re.sub(r"/\*.*?\*/|^\s*//[^\n]*\n", "", chunk, flags=re.S | re.M)


def test_the_tab_helpers_keep_their_rules():
    """The node tests in settings-tabs.test.ts hold these; CI runs only pytest."""
    parse = _body(_TABS_LIB, "export function parseTab(", "export function tabForAnchor(")
    # A repeated ?tab= reads its FIRST value.
    assert 'const value = typeof raw === "string" ? raw : raw?.[0];' in parse
    href = _body(_TABS_LIB, "export function tabHref(", "export function settingsPageAt(")
    # The default tab of EITHER page writes no ?tab= (not /profile?tab=you).
    assert href.count("\n  ") == 2, href
    assert '  const query = tab === defaultTab(page) ? "" : `?tab=${tab}`;' in href
    anchor = _body(_TABS_LIB, "export function anchorHref(", "\n}\n")
    # A deep link names the tab that renders its anchor, not the page's default.
    assert "return tabHref(page, tabForAnchor(page, anchor) ?? defaultTab(page), anchor);" in anchor
    assert "const page = settingsPageAt(home);" in anchor


def test_the_tab_follows_every_url_change():
    """A hash link (hashchange), Back and Forward (popstate) and an in-page jump all move the
    tab: the anchor store listens for both, and its value is the id without the `#`."""
    src = _read("components/settings/settings-tabs.tsx")
    store = _body(src, "function subscribeToLocation(", "const noAnchor")
    for event in ("hashchange", "popstate"):
        assert f'window.addEventListener("{event}", onChange);' in store, event
        assert f'window.removeEventListener("{event}", onChange);' in store, event
    assert "const readAnchor = () => window.location.hash.slice(1);" in store


def test_the_tab_hook_resolves_hash_and_query_newest_first():
    """A hash names a tab only when it is NEW (a stale `#autofill` must not undo a later `?tab=`);
    a new hash beats a `?tab=` change in the same render; a click writes a parsed value; focus is
    handed over only when the tab really changed."""
    src = _read("components/settings/settings-tabs.tsx")
    hook = _body(src, "export function useSettingsTab(", "const LIST_LABEL")
    assert "const anchored = anchor !== seen.anchor ? tabForAnchor(page, anchor) : null;" in hook
    assert "    if (anchored) setTab(anchored);\n    else if (urlTab !== seen.urlTab) setTab(urlTab);" in hook
    assert "    if (shown.current === tab) return;\n    shown.current = tab;" in hook
    assert "    const value = parseTab(page, next);\n    setTab(value);" in hook
    # An id inside a card resolves by PREFIX, not anywhere in the id.
    assert "PREFIXES[page].find(([prefix]) => anchor.startsWith(prefix));" in _TABS_LIB


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
    assert "window.history.replaceState(null, \"\", href);" in src
    # A bare getElementById poll rang a card hidden in another tab and stopped.
    assert "const el = document.getElementById(hash);\n      if (el) {" not in src
    # The landing and an in-page jump share one poll, and the landing's cleanup cancels it.
    assert src.count("whenShown(") == 3  # the definition and its two callers
    assert "cancel();" in src


def test_an_in_page_jump_opens_the_hidden_tab_and_names_it():
    """The profile strip's jump to a card in the other tab: the card is mounted but hidden, so the
    jump announces it (the tab hook opens its tab) instead of giving up; a shown card is not
    announced again. The announced URL names that tab, so `?tab=` matches the tab on screen."""
    src = _read("lib/use-focus-section.ts")
    focus = _body(src, "const focus = useCallback(", "}, []);")
    assert "if (!document.getElementById(anchor)) return;\n    if (!shown(anchor)) announce(anchor);" in focus
    announce = _body(src, "function announce(", "\n}\n")
    assert "const page = settingsPageAt(pathname);" in announce
    assert "const tab = page && tabForAnchor(page, anchor);" in announce
    assert "const href = page && tab ? tabHref(page, tab, anchor) : `${pathname}${search}#${anchor}`;" in announce
    assert 'window.history.replaceState(null, "", href);' in announce


def test_the_landing_stops_once_its_page_has_gone():
    src = _read("lib/use-focus-section.ts")
    landing = src[src.index("const cancel = whenShown(hash, (el) => {") :]
    assert landing.index("if (cancelled) return;") < landing.index("el.scrollIntoView(")
    # The profile strip jumps in place on its own page (one poll, no navigation).
    steps = _read("components/setup/setup-steps.ts")
    assert ": pathname === step.home\n          ? { kind: \"focus\", anchor: step.anchor }" in steps


def test_the_section_poll_gives_up_and_is_cancelled():
    """The poll for a section that never shows stops after WAIT_MS; an in-page jump's poll is
    replaced by the next jump and cancelled when the page unmounts, like the landing's."""
    src = _read("lib/use-focus-section.ts")
    assert "\nconst WAIT_MS = 3000;\n" in src
    poll = _body(src, "function whenShown(", "\n}\n")
    assert "if (performance.now() - started > WAIT_MS) window.clearInterval(poll);" in poll
    assert "return () => window.clearInterval(poll);" in poll
    hook = src[src.index("export function useFocusSection()") :]
    assert "useEffect(() => () => pending.current(), []);" in hook
    assert "    pending.current();\n    pending.current = whenShown(anchor, (el) => {" in hook


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
        "group-data-horizontal/tabs:not-[.flex-wrap]:overflow-x-auto",
        "group-data-horizontal/tabs:[scrollbar-width:none]",
        "group-data-horizontal/tabs:[&::-webkit-scrollbar]:hidden",
        # Base UI's scroll-into-view walks offsetParents to the row: without `relative` a
        # dialog's padding was counted and Home left the first tab 16px under the edge.
        "group/tabs-list relative ",
        # A tab scrolled to an end keeps the row's 3px padding, room for its focus ring
        # (4px: at 3px the scroll stopped a rounding pixel short and clipped 1px of it).
        "group-data-horizontal/tabs:scroll-px-1",
    ):
        assert cls in base, cls
    # Centred overflow clips the first tab out of reach.
    assert re.search(r"\bjustify-center\b(?!-)", base) is None
    # A Tabs that is a grid item (the New base resume dialog) took the row's full label width
    # as its minimum, so the row widened the dialog instead of scrolling.
    root = tabs[tabs.index("function Tabs(") : tabs.index("const tabsListVariants")]
    assert '\n        "group/tabs flex min-w-0 gap-2 data-horizontal:flex-col",\n        className\n' in root


_WRAPPING_ROWS = (
    "app/analytics/page.tsx",
    "app/career/page.tsx",
    "components/resume-editor/tailored-resume-studio.tsx",
    "components/resume-editor/editor-body.tsx",
    "components/resume-editor/kb-import-drawer.tsx",
)


def test_a_wrapping_tab_row_shows_every_tab_and_grows_to_fit():
    """`overflow-x: auto` computes `overflow-y` to auto too, so a wrapped row (Analytics' "Gaps &
    growth" at 375px, Career history's item tabs at 375 and 768) clipped its own second line; and
    each trigger's `h-[calc(100%-1px)]` had no definite height to resolve against in a wrapped row,
    so triggers grew taller than their line and spilled over the filter bar and the next card."""
    tabs = _read("components/ui/tabs.tsx")
    section = tabs[tabs.index("const tabsListVariants") : tabs.index("function TabsList")]
    base = re.search(r'^\s*"(group/tabs-list [^"]*)"', section, re.M).group(1)
    # Every overflow on the row is scoped to rows that do not wrap.
    assert re.findall(r"\S*overflow-x-auto", base) == ["group-data-horizontal/tabs:not-[.flex-wrap]:overflow-x-auto"]
    assert "overflow-auto" not in base and "overflow-y" not in base and "overflow-hidden" not in base
    trigger = tabs[tabs.index("function TabsTrigger") : tabs.index("function TabsContent")]
    code = re.sub(r"^\s*//[^\n]*", "", trigger, flags=re.M)
    assert '"group-[.flex-wrap]/tabs-list:h-auto",' in code
    assert "h-[calc(100%-1px)]" in code  # a one-line row still fills its 32px


def test_every_wrapping_tab_row_carries_the_class_the_scopes_key_on():
    assert "never overflow sideways" not in _read("components/ui/tabs.tsx")  # the old comment said so
    for rel in _WRAPPING_ROWS:
        row = re.search(r"<TabsList\b[^>]*>", _read(rel)).group(0)
        assert re.search(r"\bflex-wrap\b", row), rel  # the class both scopes key on

