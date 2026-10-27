"""Pins for Settings in four tabs by purpose (design refresh plan, Task 7.3; owner decisions D10, D11).

- **Nothing removed.** Every Settings item on the "Where everything lives" board (the Map board's
  Settings groups: Basics 23, Companion 11, Agent apps 26, Advanced 22) still has a home, in the tab
  the board names. A board label is the board's own description of an item; its needles are the words
  the screen says for it. Today's items the board does not list keep a home too (`_EXTRA`).
- **Old links keep working.** Each `?tab=` value an older build wrote lands on the tab and card that
  hold it now, and every card id the old tabs named still opens a tab.

- **Diagnostics** (owner decision D6, Task 7.6): Autofill coverage and its Clear data moved from
  Analytics to Settings › Advanced, the card's file with them (components/settings/).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.node_ts import run_node_test, ts_map

_ROOT = Path(__file__).resolve().parents[2]
_FRONTEND = _ROOT / "frontend"
_PAGE = "app/settings/page.tsx"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


def _flat(src: str) -> str:
    return " ".join(src.split())


# --------------------------------------------------------------------------- The board

# (board group, board label, needles): every needle must be in the files the tab renders.
_BOARD: list[tuple[str, str, tuple[str, ...]]] = [
    # Settings › Basics: AI model
    ("basics", "Provider in use", ("`AI model: ${",)),
    ("basics", "Claude API key", ('label: "Claude API key"',)),
    ("basics", "OpenAI API key", ('label: "OpenAI API key"',)),
    ("basics", "Gemini API key", ('label: "Gemini API key"',)),
    ("basics", "OpenRouter API key", ('label: "OpenRouter API key"',)),
    ("basics", "Key status: saved, set outside, not added", ('"Set outside the app"', '"Saved"', "Not added")),
    ("basics", "Test", ('"Test again"',)),
    ("basics", "Use recommended models", ("Use recommended models",)),
    # Money
    ("basics", "Home currency", ("Home currency",)),
    ("basics", "Show pay per year, month or hour", ("Show pay per", '"Year"', '"Month"', '"Hour"')),
    ("basics", "Rates date and Update", ("Rates from ", "once a day", "Update")),
    ("basics", "Show the posted amount too", ("Show the posted amount too",)),
    # Resume PDFs
    ("basics", "Save a copy of each resume", ("Save a copy of each resume",)),
    ("basics", "Folder path", ("Folder path",)),
    ("basics", "Open folder", ("Open folder",)),
    ("basics", "Change folder", ("Change folder",)),
    # Appearance
    ("basics", "Dark mode, follows your computer", ('"Dark"', '"Like my computer"')),
    ("basics", "Light, dark or like my computer", ('"Light"', '"Dark"', '"Like my computer"')),
    # About, the page footer
    ("basics", "Version", ('label="Version"',)),
    ("basics", "How to update", ("How to update",)),
    ("basics", "Release notes", ("Release notes",)),
    ("basics", "Technical details", ("Technical details",)),
    ("basics", "Setup guide link", ("Setup guide",)),
    # Settings › Companion: what it may fill
    ("companion", "Fill agreements and signatures", ("Let the Companion fill agreements and signatures",)),
    ("companion", "Agreement date and policy", ("You agreed on", "(policy ")),
    ("companion", "Screening answers: Careful, Balanced, Confident",
     ("Screening answers", 'label: "Careful"', 'label: "Balanced"', 'label: "Confident"')),
    # How it applies
    ("companion", "Choose the base resume for me", ('label="Choose the base resume for me"',)),
    ("companion", "Stop after each step", ('label="Stop after each step"',)),
    ("companion", "Think when stuck", ('label="Think when stuck"',)),
    ("companion", "Fields it couldn't operate", ("<KnownGapsLine />", '"/api/autofill/gaps/summary"')),
    # Form-filling engine
    ("companion", "Jev API key", ('label="Jev API key"',)),
    ("companion", "Provider", ("<Label htmlFor={providerId}>Provider</Label>",)),
    ("companion", "Form filling decisions model", ("<Label htmlFor={engineId}>Form filling decisions</Label>",)),
    ("companion", "Test", ('"Testing…" : "Test"',)),
    # Settings › Agent apps: connect an app (the commands are the server's, `_CLIENTS` below)
    ("agents", "Tool set", ("Tool set",)),
    # What agents can and can't do, folded
    ("agents", "They can, they can't", (">\n                They can\n", ">\n                They can&apos;t\n")),
    ("agents", "How to connect an agent", ('label: "How to connect an agent"',)),
    ("agents", "Ready-made skills", ('label: "Ready-made skills"',)),
    ("agents", "How agent applications work", ('label: "How agent applications work"',)),
    # Limits
    ("agents", "Full automation", ('title="Full automation"',)),
    ("agents", "Applications per day", ('label: "Applications per day"',)),
    ("agents", "Jobs per search", ('label: "Jobs per search"',)),
    ("agents", "Move unreviewed jobs to History after", ('label: "Move unreviewed jobs to History after (days)"',)),
    ("agents", "Lowest match score to pick a resume", ('label: "Lowest match score to pick a resume"',)),
    ("agents", "Lead needed to pick a resume", ('label: "Lead needed to pick a resume"',)),
    ("agents", "Companies to skip", ('<Label htmlFor="aa-blocklist">Companies to skip</Label>',)),
    # Accounts and copies
    ("agents", "Job-site login email", ('title="Job-site login"', "Email</Label>")),
    ("agents", "Job-site login password", ("Password</Label>",)),
    ("agents", "Clear login", ('title: "Clear job-site login?"',)),
    ("agents", "Next-step hints for agents", ('title="Next-step hints for connected agents"',)),
    ("agents", "Second copy setup prompt", ('"Copy setup prompt"',)),
    ("agents", "Show a pairing code", ('"Show a pairing code"',)),
    ("agents", "Paired status", ("Paired with your bot at",)),
    # Settings › Advanced: model per job
    ("advanced", "Fast model", ('label: "Fast model"',)),
    ("advanced", "Smart model", ('label: "Smart model"',)),
    ("advanced", "Assistant model", ('label: "Assistant model"',)),
    ("advanced", "Reasoning model", ('label: "Reasoning model"',)),
    ("advanced", "Test each model", ("aria-label={`Test ${name}`}",)),
    ("advanced", "Capability badges", ('label: "Writing"', 'label: "Structured answers"')),
    ("advanced", "Which model should I pick?", ("Which model should I pick?",)),
    # More models
    ("advanced", "Find models per provider", ("Find {providerLabel(provider)} models",)),
    ("advanced", "Built-in and added models", ('title="Available models"',)),
    ("advanced", "Your own AI server: Ollama, LM Studio", ('title="Custom AI server"', "Ollama or LM Studio")),
    # AI instructions (all of them: `test_every_ai_instruction_is_in_advanced`)
    ("advanced", "Cover letter", ('title: "Cover letter"',)),
    ("advanced", "Application questions", ('title: "Application questions"',)),
    ("advanced", "Tailoring from your answers", ('title: "Tailoring from your answers"',)),
    ("advanced", "Assistant", ('title: "Assistant"',)),
    ("advanced", "18 more instructions", ("More instructions ({advanced.length})",)),
    # Quick tailor
    ("advanced", "Add missing keywords to Skills", ('label: "Add missing job description keywords to Skills"',)),
    ("advanced", "Use the job description's wording",
     ('label: "Use the job description\'s wording when your experience backs it up"',)),
    ("advanced", "Match summary and title", ('label: "Match your summary and title to the job"',)),
    ("advanced", "Add keywords to projects", ('label: "Add keywords to projects"',)),
    ("advanced", "Extra instruction", ("Extra instruction",)),
    # Diagnostics (from Analytics › Overview, D6)
    ("advanced", "Autofill coverage", ('title="Autofill coverage"',)),
    ("advanced", "Clear autofill data", ('"Clear data"', 'title: "Clear captured autofill data?"')),
]

# Connect an app: each command is the server's (backend/app/services/connect.py); the card renders
# every client by its kind. Board label -> (the client's label, the kinds it may come as).
_CLIENTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "Claude Code command": ("Claude Code", ("command",)),
    "Codex CLI command": ("Codex CLI", ("command",)),
    "Codex app address and steps": ("Codex app", ("steps",)),
    "Add to Cursor": ("Cursor", ("deeplink",)),
    "Add to VS Code": ("VS Code", ("deeplink",)),
    "Claude Desktop command": ("Claude Desktop", ("command", "download")),
    "Any MCP agent address": ("Any MCP agent", ("url",)),
}

# Today's items the board does not list: each keeps a home (nothing removed). The plan's Basics
# footer adds "Run setup again"; Hours per year is the money setting's, under Advanced (Task 3.4).
_EXTRA: list[tuple[str, str, tuple[str, ...]]] = [
    ("basics", "Run setup again", ("Run setup again", 'href="/setup"')),
    # Their words are lib/model-catalog.ts's (`test_the_model_rows_are_the_three_everyday_jobs`).
    ("basics", "The three plain-word model rows", ("{EVERYDAY_JOBS.map((job) => (", "{job.words}</dt>")),
    ("basics", "Change provider", ("Change provider",)),
    ("basics", "Use the default folder", ("Use the default",)),
    ("basics", "Choose a folder", ("Choose…",)),
    ("basics", "Save typed API keys", ("onClick={() => onSave(data.custom_endpoint)}",)),
    ("companion", "Save the Jev key", ("saveOnce({ api_key: key?.trim() || null })",)),
    ("agents", "Submit clean applications without asking", ('label="Submit clean applications without asking"',)),
    ("agents", "Suggest the next step to connected agents", ('label="Suggest the next step to connected agents"',)),
    ("agents", "Who writes for connected agents: your agent app or Maestro's AI",
     ('title="Who writes for connected agents"', 'label: "Your agent app"', 'label: "Maestro\'s AI"')),
    ("agents", "Copy pairing code", ('label="Copy pairing code"',)),
    ("agents", "Download for Claude Desktop", ("Download for Claude Desktop",)),
    ("agents", "Save auto-apply limits", ("onClick={() => draft && saveOnce(draft)}",)),
    ("advanced", "Strict reply format", ("Strict reply format",)),
    ("advanced", "Hours per year", ("Hours per year",)),
]

_TAB_ROW = re.compile(r'\{\s*value: "(\w+)",\s*label: "([^"]*)",\s*anchors: \[([^\]]*)\]')
_IMPORT = re.compile(r'import\s*\{([^}]*)\}\s*from\s*"@/components/(settings/[\w-]+)"')


def _tabs() -> dict[str, tuple[str, list[str]]]:
    lib = _read("lib/settings-tabs.ts")
    start = lib.index("export const SETTINGS_TABS = [")
    block = lib[start : lib.index("] as const", start)]
    return {v: (label, re.findall(r'"([\w-]+)"', a)) for v, label, a in _TAB_ROW.findall(block)}


def _files_from(src: str, names: set[str] | None = None) -> set[str]:
    """The component files `src` imports (only those naming one of `names`, when given)."""
    out = set()
    for imported, mod in _IMPORT.findall(src):
        wanted = {n.strip() for n in imported.split(",") if n.strip()}
        if names is None or wanted & names:
            out.add(f"components/{mod}.tsx")
    return out


def _panel(value: str) -> str:
    """The JSX of one tab's panel on the settings page."""
    page = _read(_PAGE)
    block = page[page.index("panels={{") : page.index("}}\n", page.index("panels={{"))]
    marks = sorted((re.search(rf"\b{v}: ", block).start(), v) for v in _tabs())
    ends = dict(zip([v for _, v in marks], [at for at, _ in marks][1:] + [len(block)]))
    start = {v: at for at, v in marks}[value]
    return block[start : ends[value]]


def _tab_source(value: str) -> str:
    """The tab's panel, every file it renders, and the settings files those import, joined."""
    body = _panel(value)
    seen: set[str] = set()
    todo = _files_from(_read(_PAGE), set(re.findall(r"<(\w+)\b", body)))
    while todo:
        rel = todo.pop()
        if rel in seen:
            continue
        seen.add(rel)
        todo |= _files_from(_read(rel)) - seen
    return body + "".join(_read(rel) for rel in sorted(seen))


def test_settings_has_the_four_tabs_by_purpose():
    tabs = _tabs()
    assert [(v, label) for v, (label, _) in tabs.items()] == [
        ("basics", "Basics"), ("companion", "Companion"), ("agents", "Agent apps"), ("advanced", "Advanced"),
    ]


def test_the_board_counts_match_the_plan():
    """The board's Settings groups hold 23, 11, 26 and 22 items."""
    counts = {group: 0 for group in ("basics", "companion", "agents", "advanced")}
    for group, _, _ in _BOARD:
        counts[group] += 1
    counts["agents"] += len(_CLIENTS)
    assert counts == {"basics": 23, "companion": 11, "agents": 26, "advanced": 22}


@pytest.mark.parametrize(("group", "label", "needles"), _BOARD + _EXTRA, ids=[f"{g}: {lbl}" for g, lbl, _ in _BOARD + _EXTRA])
def test_every_settings_item_still_has_a_home_in_its_tab(group: str, label: str, needles: tuple[str, ...]):
    src = _tab_source(group)
    missing = [needle for needle in needles if needle not in src]
    assert not missing, (group, label, missing)


def test_every_settings_item_is_in_the_settings_components():
    """The plan's form of the check (Task 7.2's), across every settings file and the page."""
    src = "".join(p.read_text(encoding="utf-8") for p in sorted((_FRONTEND / "components/settings").glob("*.tsx")))
    src += _read(_PAGE)
    missing = [label for _, label, needles in _BOARD + _EXTRA if any(n not in src for n in needles)]
    assert not missing, missing


@pytest.mark.parametrize("board", list(_CLIENTS))
def test_every_agent_app_command_has_a_home(board: str):
    label, kinds = _CLIENTS[board]
    server = (_ROOT / "backend/app/services/connect.py").read_text(encoding="utf-8")
    assert any(f'label="{label}", kind="{kind}"' in _flat(server) for kind in kinds), board
    src = _tab_source("agents")
    assert "{data.clients.map((client) => (" in src  # every client the server lists, none dropped
    for kind in kinds:
        assert f'kind === "{kind}"' in src, (board, kind)


def test_every_ai_instruction_is_in_advanced():
    """All 22: the four curated ones and the 18 under More instructions, one title per prompt file."""
    prompts = sorted(p.stem for p in (_ROOT / "backend/app/prompts").glob("*.txt"))
    src = _tab_source("advanced")
    section = _read("components/settings/prompts-section.tsx")
    essential = re.findall(r'key: "(\w+)",\s*title:', section)
    more = re.findall(r'\["(\w+)", \{ title:', section)
    assert len(prompts) == 22 and len(essential) == 4 and len(more) == 18
    assert sorted(essential + more) == prompts
    assert "<PromptsSection />" in src


def test_the_model_rows_are_the_three_everyday_jobs():
    """Three plain-word rows (the plan's Basics), each naming its role; the Reasoning model is not one."""
    lib = _read("lib/model-catalog.ts")
    jobs = lib[lib.index("export const EVERYDAY_JOBS = [") : lib.index("] as const;", lib.index("export const EVERYDAY_JOBS"))]
    assert re.findall(r'role: "(\w+)", words: "([^"]+)"', jobs) == [
        ("fast_model", "Reads jobs and documents"), ("smart_model", "Tailors and writes"), ("chat_model", "Runs the Assistant"),
    ]
    result = run_node_test("lib/model-catalog.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr


def test_autofill_coverage_lives_under_diagnostics_not_analytics():
    """D6: Settings › Advanced renders the card (Diagnostics, its own anchor), the file lives with the
    settings cards, and no Analytics file imports it."""
    assert not (_FRONTEND / "components/analytics/autofill-coverage-card.tsx").exists()
    card = _read("components/settings/autofill-coverage-card.tsx")
    assert "export function AutofillCoverageCard()" in card
    section = _read("components/settings/diagnostics-section.tsx")
    assert 'import { AutofillCoverageCard } from "@/components/settings/autofill-coverage-card";' in section
    assert '<div id="diagnostics"' in section and "<AutofillCoverageCard />" in section
    assert "<DiagnosticsSection />" in _panel("advanced")
    assert "diagnostics" in _tabs()["advanced"][1]
    for folder in ("app/analytics", "components/analytics", "components/explore", "components/charts"):
        for path in (_FRONTEND / folder).rglob("*.ts*"):
            assert "autofill-coverage-card" not in path.read_text(encoding="utf-8"), path.relative_to(_FRONTEND)


# ------------------------------------------------------------------------ Old links

_OLD_SETTINGS_TABS = {
    # The five tabs before the four, and the card each one opened with. `ai` is the plan's name for
    # the first one (its value was `models`, and as the default tab it wrote no `?tab=`).
    "ai": "api-keys",
    "models": "api-keys",
    "tailoring": "quick-tailor",
    "agents": None,  # the same value: Agent apps opens at its first card
    "appearance": "appearance",
    "about": "about",
}
_OLD_ANCHORS = (
    "api-keys", "models", "form-filling", "model-catalog", "custom-endpoint", "prompts",
    "quick-tailor", "resumes-folder",
    "connected-agents", "connect-assistant", "full-automation", "agent-hints", "auto-apply", "second-copy",
    "appearance", "about",
)


def _landing(tmp_path: Path, values: list[str]) -> list[dict]:
    module = tmp_path / "landing.ts"
    module.write_text(
        f'import {{ landingFor }} from "{_FRONTEND / "lib/settings-tabs.ts"}";\n'
        'export const probe = (raw: string) => landingFor("settings", raw);\n'
    )
    return ts_map(str(module), "probe", values)


def test_each_old_tab_value_lands_on_its_new_tab_and_card(tmp_path):
    tabs = _tabs()
    landed = dict(zip(_OLD_SETTINGS_TABS, _landing(tmp_path, list(_OLD_SETTINGS_TABS))))
    for old, card in _OLD_SETTINGS_TABS.items():
        tab, anchor = landed[old]["tab"], landed[old]["anchor"]
        assert tab in tabs, (old, tab)
        assert anchor == card, (old, anchor)
        if anchor is not None:
            assert anchor in tabs[tab][1], (old, tab, anchor)
    assert landed["agents"]["tab"] == "agents" and tabs["agents"][0] == "Agent apps"
    assert landed["tailoring"]["tab"] == "advanced"
    assert {landed[v]["tab"] for v in ("ai", "models", "appearance", "about")} == {"basics"}


def test_a_current_or_unknown_tab_value_moves_nothing(tmp_path):
    out = _landing(tmp_path, ["basics", "companion", "advanced", "nope", ""])
    assert [o["tab"] for o in out] == ["basics", "companion", "advanced", "basics", "basics"]
    assert all(o["anchor"] is None for o in out)


def test_every_old_card_id_still_opens_a_tab(tmp_path):
    """A deep link or a hash-only bookmark (`/settings#prompts`) to any card the old tabs held."""
    module = tmp_path / "anchor.ts"
    module.write_text(
        f'import {{ tabForAnchor }} from "{_FRONTEND / "lib/settings-tabs.ts"}";\n'
        'export const probe = (anchor: string) => tabForAnchor("settings", anchor);\n'
    )
    assert None not in ts_map(str(module), "probe", list(_OLD_ANCHORS))


def test_an_old_tab_rewrites_the_url_before_the_page_lands_its_card():
    """The server renders the new tab (`parseTab` reads an old value as its new tab); after hydration a
    layout effect writes the new tab and the card's hash, before `useFocusSection`'s landing effect
    (a passive effect of the page) reads the hash, so the card is scrolled to and rung."""
    lib = _read("lib/settings-tabs.ts")
    parse = lib[lib.index("export function parseTab(") : lib.index("export function landingFor(")]
    assert "return oldTab(page, value)?.tab ?? defaultTab(page);" in parse
    tabs = _read("components/settings/settings-tabs.tsx")
    hook = tabs[tabs.index("export function useSettingsTab(") : tabs.index("const LIST_LABEL")]
    assert "const moved = landingFor(page, raw).anchor;" in hook
    effect = hook[hook.index("useLayoutEffect(() => {\n    if (!moved) return;") :]
    assert "const target = window.location.hash.slice(1) || moved;" in effect  # a link's own hash wins
    assert 'window.history.replaceState(null, "", tabHref(page, tabForAnchor(page, target) ?? tab, target));' in effect


def test_the_node_tests_for_the_tab_table_run():
    result = run_node_test("lib/settings-tabs.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr


# -------------------------------------------------------------------------- Page

def test_the_page_has_no_subtitle_and_the_guide_moved_to_about():
    """D1: a page subtitle goes. The header's Setup guide button joins the About footer."""
    page = _read(_PAGE)
    header = page[page.index("<PageHeader") : page.index("/>", page.index("<PageHeader"))]
    assert "subtitle=" not in header and "actions=" not in header
    about = _read("components/settings/about-section.tsx")
    assert "Setup guide" in about and "Run setup again" in about


def test_the_about_footer_closes_basics():
    assert re.findall(r"<(\w+)\b[^>]*/>", _panel("basics"))[-1] == "AboutSection"
