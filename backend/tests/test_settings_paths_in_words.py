"""Every "Settings › …" the app or its guides name is a tab Settings has (design refresh Task 7.3), and
every "Profile › …" a tile or fold Profile has (Task 7.2).

Settings went from five tabs (AI & models, Tailoring, Connected agents, Appearance, About) to four
(Basics, Companion, Agent apps, Advanced), and the server's error sentences, the Companion's notes and
the guides kept sending people to the old ones. The tab labels are read from `lib/settings-tabs.ts`, so
a renamed tab fails here until every sentence that names it follows. Profile lost its tabs (About you,
Autofill) for tiles and folds (Contact, Work permits, Start and pay, Diversity questions, …), read from
`lib/profile-tiles.ts` the same way.

- **The app's own words** (server messages, MCP text, the Companion, the web app; comments too, since
  they are copied into messages): the first place after "Settings ›" is a current tab label.
- **The guides a user reads**: the same.

Either may name another app's own Settings in its install steps (Claude Desktop's Extensions, Codex's
Plugins, Docker Desktop's Resources, macOS's General).
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

# "Settings › X", "Settings → X", "Settings > X" (spaced, so a TypeScript generic is not one) and the
# HTML entity; a path wrapped onto the next line of a comment or a Markdown paragraph still reads.
_PATH = re.compile(
    r"Settings(?:\s*(?:›|→|&gt;|\\u203a)|\s+>)(?:\s|//|\*|#)*([A-Z][^›→>.,;:()\n*`\"]*)"
)

# The same spellings after "Profile" (a whole word: "AutofillProfile → x" is no path, nor a generic).
_PROFILE_PATH = re.compile(
    r"\bProfile(?:\s*(?:›|→|&gt;|\\u203a)|\s+>)(?:\s|//|\*|#)*([A-Z][^›→>.,;:()\n*`\"]*)"
)

_SOURCE_TREES: dict[str, tuple[str, ...]] = {
    "backend/app": ("*.py", "*.md", "*.json"),
    "backend/mcp_server": ("*.py", "*.md", "*.json"),
    "extension": ("*.js", "*.html", "*.md", "*.json"),
    "frontend/app": ("*.ts", "*.tsx"),
    "frontend/components": ("*.ts", "*.tsx"),
    "frontend/lib": ("*.ts", "*.tsx"),
}

_GUIDES = (
    "README.md",
    "PRIVACY.md",
    "SECURITY.md",
    "UBIQUITOUS_LANGUAGE.md",
    ".env.example",
    "scripts/setup-mcp.sh",
    "plugins/maestro-career-studio/README.md",
    "docs/GETTING_STARTED.md",
    "docs/USING_MAESTRO.md",
    "docs/SETUP_REFERENCE.md",
    "docs/RELEASING.md",
    "docs/always-on-bot.md",
    "docs/sync-setup.md",
    "docs/skills/README.md",
    "docs/playbooks/agent-apply.md",
    "docs/frontend-conventions.md",
)

# Another app's Settings, named in install steps.
_FOREIGN = ("Extensions", "Plugins", "Resources", "General")


def _tab_labels() -> tuple[str, ...]:
    src = (_ROOT / "frontend/lib/settings-tabs.ts").read_text(encoding="utf-8")
    table = re.search(r"export const SETTINGS_TABS = \[(.+?)\] as const", src, re.S)
    assert table, "SETTINGS_TABS moved: this pin reads the tab labels from it"
    labels = tuple(re.findall(r'label: "([^"]+)"', table.group(1)))
    assert labels, "no tab labels found in SETTINGS_TABS"
    return labels


def _profile_places() -> tuple[str, ...]:
    """Profile's tile and fold titles, as `lib/profile-tiles.ts` names them."""
    src = (_ROOT / "frontend/lib/profile-tiles.ts").read_text(encoding="utf-8")
    titles = []
    for table in ("PROFILE_TILES", "PROFILE_FOLDS"):
        found = re.search(rf"export const {table} = \[(.+?)\] as const", src, re.S)
        assert found, f"{table} moved: this pin reads Profile's titles from it"
        titles += re.findall(r'title: "([^"]+)"', found.group(1))
    assert titles, "no tile or fold titles found in lib/profile-tiles.ts"
    return tuple(titles)


def _paths(text: str, pattern: re.Pattern[str] = _PATH) -> list[tuple[int, str]]:
    """(line, first place after "Settings ›", or after `pattern`'s page) for every path in `text`."""
    return [(text.count("\n", 0, m.start()) + 1, m.group(1).strip()[:40]) for m in pattern.finditer(text)]


def _own_words() -> list[tuple[Path, str]]:
    """Every source file of the app's own words, with its text."""
    out = []
    for tree, patterns in _SOURCE_TREES.items():
        for pattern in patterns:
            for path in sorted((_ROOT / tree).rglob(pattern)):
                if not _is_test(path.relative_to(_ROOT)):
                    out.append((path.relative_to(_ROOT), path.read_text(encoding="utf-8", errors="replace")))
    return out


def _is_test(path: Path) -> bool:
    parts = set(path.parts)
    return bool(parts & {"tests", "node_modules", "__pycache__"}) or ".test." in path.name


def test_the_scan_reads_a_path_however_it_is_written():
    """Not vacuous: each spelling a sentence, a comment or a guide used for a Settings path is read."""
    assert _paths("Add one in Settings › AI & models.") == [(1, "AI & models")]
    assert _paths("in Settings ›\n   * Connected agents (the tab)") == [(1, "Connected agents")]
    assert _paths("x\nunder **Settings ›\n  AI & models › Form filling**") == [(2, "AI & models")]
    assert _paths("from Settings > Connected agents > Connect") == [(1, "Connected agents")]
    assert _paths("Settings → Models in the web app") == [(1, "Models in the web app")]
    assert _paths("type Setting = SettingEnvelope<AutoApplySettings>;") == []


def test_every_settings_path_in_the_apps_own_words_names_a_current_tab():
    labels = _tab_labels()
    wrong = []
    for rel, text in _own_words():
        for line, place in _paths(text):
            if not place.startswith(labels + _FOREIGN):
                wrong.append(f"{rel}:{line}: Settings › {place}")
    assert not wrong, f"not a Settings tab ({', '.join(labels)}):\n" + "\n".join(wrong)


def test_the_guides_name_only_current_settings_tabs():
    labels = _tab_labels()
    wrong = []
    for rel in _GUIDES:
        text = (_ROOT / rel).read_text(encoding="utf-8")
        for line, place in _paths(text):
            if not place.startswith(labels + _FOREIGN):
                wrong.append(f"{rel}:{line}: Settings › {place}")
    assert not wrong, f"not a Settings tab ({', '.join(labels)}):\n" + "\n".join(wrong)


# --- Profile's tiles and folds -------------------------------------------------------------------------


def test_the_scan_reads_a_profile_path_however_it_is_written():
    """Not vacuous: a learn note, a wrapped comment, an arrow and a guide's bold path are each read, and a
    TypeScript generic or a longer name ending in "Profile" is not a path."""
    def read(text):
        return _paths(text, _PROFILE_PATH)

    assert read("Saved to Profile › Work permits (United Kingdom).") == [(1, "Work permits")]
    assert read("turned off in Profile ›\n   * Diversity questions, which") == [(1, "Diversity questions")]
    assert read("x\nanswers (**Profile ›\n  Autofill**)") == [(2, "Autofill")]
    assert read("(Profile → Eligibility) cover") == [(1, "Eligibility")]
    assert read("const answers = useAutosave<Profile>(initial);") == []
    assert read("SettingEnvelope<AutofillProfile> → Start") == []


def test_profile_places_come_from_its_tiles_and_folds():
    places = _profile_places()
    assert {"Contact", "Work permits", "Start and pay", "Your own questions"} <= set(places)
    assert {"Diversity questions", "Eligibility"} <= set(places)
    assert "Autofill" not in places and "About you" not in places


def test_every_profile_path_in_the_apps_own_words_names_a_tile_or_fold():
    places = _profile_places()
    wrong = []
    for rel, text in _own_words():
        for line, place in _paths(text, _PROFILE_PATH):
            if not place.startswith(places):
                wrong.append(f"{rel}:{line}: Profile › {place}")
    assert not wrong, f"not a Profile tile or fold ({', '.join(places)}):\n" + "\n".join(wrong)


def test_the_guides_name_only_profile_tiles_and_folds():
    places = _profile_places()
    wrong = []
    for rel in _GUIDES:
        for line, place in _paths((_ROOT / rel).read_text(encoding="utf-8"), _PROFILE_PATH):
            if not place.startswith(places):
                wrong.append(f"{rel}:{line}: Profile › {place}")
    assert not wrong, f"not a Profile tile or fold ({', '.join(places)}):\n" + "\n".join(wrong)
