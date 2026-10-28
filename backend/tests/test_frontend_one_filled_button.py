"""One filled button per view (docs/design-system/README.md, "Selection and state"; the design refresh's Goal Card).

Everything but a view's one lead action is tonal, outline, ghost or text-style. A dialog's confirm is filled because
the dialog is its own view, so what a `<DialogContent>` or `<SheetContent>` holds is not counted with the page under
it. A FILLED control is a `<Button>` with no variant or one that can be "default", `buttonVariants()` with no variant
(a link styled as the button), and a `<LeadCard>` with an `action` (its button is filled: test_frontend_tiers.py).

Each view is read as a render graph from its route: a top-level function, then every function of its file and every
imported component its body names, never into `components/ui/` or `components/visual/` (primitives; a LeadCard
counts where it is used). A function counts once however many times a `.map` renders it, so a count alone misses a
filled control repeated per item (one Save per AI instruction): Settings is counted per tab AND each of its Saves is
pinned by name. Every Settings card saves its own form, so no action leads a tab and each Save is tonal.

The other views: where every filled control can show at once (Jobs, Automations, Analytics) the count is the pin.
Where two sit in branches that never show together (Today leads with Next up OR Setup's card; a job step is hidden
unless it is open), a static count would say two, so the pin lists where each one sits and checks the branch that
keeps them apart.
"""

from __future__ import annotations

import os
import re
from functools import cache
from pathlib import Path

import pytest

from tests._jsx_pins import squash

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


# --- The render graph ----------------------------------------------------------------------------


def _strip_comments(src: str) -> str:
    """The source without `/* */` and `//` comments: a comment naming `<Button>` is not a button, and an
    apostrophe in one would end a tag early."""
    out, i, quote = [], 0, ""
    while i < len(src):
        c = src[i]
        if quote:
            if c == "\\":
                out.append(src[i : i + 2])
                i += 2
                continue
            quote = "" if c == quote else quote
        elif src.startswith("/*", i):
            end = src.find("*/", i + 2)
            i = len(src) if end == -1 else end + 2
            continue
        elif src.startswith("//", i) and (i == 0 or src[i - 1] in " \t\n"):
            end = src.find("\n", i)
            i = len(src) if end == -1 else end
            continue
        elif c in "\"'`":
            quote = c
        out.append(c)
        i += 1
    return "".join(out)


_TOP = re.compile(r"^(?:export|function|const|let|type|interface|class|import|async)\b", re.M)
_DECL = re.compile(r"(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function|const|let)\s+(\w+)")
_IMPORT = re.compile(r'^import\s+(?:type\s+)?([^;]*?)\s+from\s+"([^"]+)";', re.M)
_REEXPORT = re.compile(r'^export\s+(\{[^}]*\})\s+from\s+"([^"]+)";', re.M)


def _resolve(spec: str, here: str) -> str | None:
    if spec.startswith("@/"):
        base = spec[2:]
    elif spec.startswith("."):
        base = os.path.normpath(os.path.join(os.path.dirname(here), spec))
    else:
        return None
    for ext in (".tsx", ".ts", "/index.ts"):
        if (_FRONTEND / f"{base}{ext}").exists():
            return f"{base}{ext}"
    return None


def _names(clause: str) -> list[tuple[str, str]]:
    """(local, exported) per name an import clause binds."""
    pairs = []
    default = clause.split("{")[0].strip().rstrip(",").strip()
    if default and not default.startswith("*"):
        pairs.append((default, "default"))
    braces = re.search(r"\{([^}]*)\}", clause)
    for part in braces.group(1).split(",") if braces else ():
        part = part.strip().removeprefix("type ").strip()
        if part:
            exported, _, local = part.partition(" as ")
            pairs.append(((local or exported).strip(), exported.strip()))
    return pairs


@cache
def _module(rel: str):
    """A file's imports {local: (file, exported)}, re-exports, top-level declarations {name: source} and default."""
    src = _strip_comments(_read(rel))
    imports, reexports = {}, {}
    for pattern, into in ((_IMPORT, imports), (_REEXPORT, reexports)):
        for m in pattern.finditer(src):
            target = _resolve(m.group(2), rel)
            if target:
                into.update({local: (target, exported) for local, exported in _names(m.group(1))})
    starts = [m.start() for m in _TOP.finditer(src)] + [len(src)]
    decls, default = {}, None
    for a, b in zip(starts, starts[1:]):
        if m := _DECL.match(src, a):
            decls[m.group(1)] = src[a:b]
            default = m.group(1) if re.match(r"export\s+default\b", src[a:b]) else default
    return imports, reexports, decls, default


def _decl(rel: str, name: str) -> tuple[str, str] | None:
    _, reexports, decls, default = _module(rel)
    name = default if name == "default" else name
    if name in decls:
        return rel, name
    return _decl(*reexports[name]) if name in reexports else None


def _cut_dialogs(body: str) -> str:
    """The body without what its dialogs and sheets hold: a dialog is its own view."""
    for name in ("DialogContent", "SheetContent"):
        while (at := body.find(f"<{name}")) != -1:
            end = body.find(f"</{name}>", at)
            body = body[:at] + (body[end + len(name) + 3 :] if end != -1 else "")
    return body


def _step(c: str, quote: str, depth: int) -> tuple[str, int]:
    if quote:
        return ("" if c == quote else quote), depth
    return (c if c in "\"'`" else ""), depth + {"{": 1, "}": -1}.get(c, 0)


def _elements(src: str, name: str) -> list[tuple[str, str]]:
    """(opening tag, children) per `<name>` element: the tag through its `>`, skipping braces and quotes, whitespace
    squashed; the children up to `</name>` (none for a self-closing tag)."""
    elements = []
    for found in re.finditer(rf"<{name}(?=[\s/>])", src):
        quote, depth = "", 0
        for i in range(found.start(), len(src)):
            quote, depth = _step(src[i], quote, depth)
            if src[i] == ">" and depth == 0 and not quote and src[i - 1] != "=":
                closed = src[i - 1] == "/"
                children = "" if closed else src[i + 1 : src.find(f"</{name}>", i)]
                elements.append((squash(src[found.start() : i + 1]), squash(children)))
                break
    return elements


def _tags(src: str, name: str) -> list[str]:
    return [tag for tag, _ in _elements(src, name)]


def _variant(tag: str) -> str | None:
    found = re.search(r'variant=(\{[^}]*\}|"[^"]*")', tag)
    return found.group(1) if found else None


def _filled(body: str) -> list[str]:
    hits = [t for t in _tags(body, "Button") if _variant(t) is None or '"default"' in _variant(t)]
    hits += [
        m.group(0)
        for m in re.finditer(r"buttonVariants\(([^)]*)\)", body)
        if "variant" not in m.group(1) or '"default"' in m.group(1)
    ]
    return hits + [t for t in _tags(body, "LeadCard") if "action=" in t]


_PRIMITIVES = ("components/ui/", "components/visual/")


@cache
def _rendered(rel: str, name: str = "default") -> dict[tuple[str, str], str]:
    """{(file, function): body, dialogs cut} for every function the root names, and the ones those name."""
    seen: dict[tuple[str, str], str] = {}
    todo = [_decl(rel, name)]
    while todo:
        key = todo.pop()
        if key is None or key in seen:
            continue
        file, fn = key
        imports, _, decls, _ = _module(file)
        body = seen[key] = _cut_dialogs(decls[fn])
        todo += [(file, local) for local in decls if local != fn and re.search(rf"\b{local}\b", body)]
        todo += [
            _decl(*target)
            for local, target in imports.items()
            if target[0].endswith((".tsx", "index.ts"))
            and not target[0].startswith(_PRIMITIVES)
            and re.search(rf"\b{re.escape(local)}\b", body)
        ]
    return seen


def _filled_in(graph: dict[tuple[str, str], str]) -> dict[tuple[str, str], int]:
    return {key: len(hits) for key, body in graph.items() if (hits := _filled(body))}


# --- Settings: per tab ---------------------------------------------------------------------------

_SETTINGS = "app/settings/page.tsx"


def _settings_tabs() -> dict[str, dict[tuple[str, str], str]]:
    """{tab: render graph of the cards its panel lists}, read from the page's `panels`."""
    src = _strip_comments(_read(_SETTINGS))
    imports = _module(_SETTINGS)[0]
    tabs = {}
    for m in re.finditer(r"(\w+): \(\s*<>(.*?)</>\s*\)", src, re.S):
        graph: dict[tuple[str, str], str] = {}
        for card in re.findall(r"<(\w+) />", m.group(2)):
            graph.update(_rendered(*imports[card]))
        tabs[m.group(1)] = graph
    return tabs


def test_every_settings_tab_is_read_with_its_cards():
    # Mutant: a tab the parser missed would pass every count below with nothing in it.
    values = re.findall(r'\{ value: "(\w+)"|^\s+value: "(\w+)"', _read("lib/settings-tabs.ts"), re.M)
    tabs = _settings_tabs()
    assert set(tabs) == {a or b for a, b in values} == {"basics", "companion", "agents", "advanced"}
    # The graph reaches the cards' nested parts: the key editor, the job-site login's actions, each prompt.
    assert ("components/settings/models-section.tsx", "ApiKeysEditor") in tabs["basics"]
    assert ("components/settings/resumes-folder-section.tsx", "FolderRow") in tabs["basics"]
    assert ("components/settings/full-automation-section.tsx", "JobSiteLoginActions") in tabs["agents"]
    assert ("components/settings/auto-apply-section.tsx", "AutoApplyEditor") in tabs["agents"]
    assert ("components/settings/prompts-section.tsx", "PromptCard") in tabs["advanced"]
    assert ("components/settings/form-filling-section.tsx", "FormFillingSection") in tabs["companion"]


@pytest.mark.parametrize("tab", ["basics", "companion", "agents", "advanced"])
def test_a_settings_tab_has_at_most_one_filled_button(tab):
    # The Agent apps tab with full automation on showed Auto-apply's and the job-site login's filled Saves at once.
    filled = [hit for body in _settings_tabs()[tab].values() for hit in _filled(body)]
    assert len(filled) <= 1, filled


def test_a_settings_save_is_tonal_or_outline():
    # Every card saves its own form, so none leads the tab: a Save is tonal (outline beside a field, as the custom
    # AI server's address), never filled. Its label and `pending` words stay.
    saves = {
        (key, tag)
        for graph in _settings_tabs().values()
        for key, body in graph.items()
        for tag, label in _elements(body, "Button")
        if re.search(r'(?:^|[\s>"])Save\b', label)
    }
    # The AI model card's keys, the resumes folder, the Companion's form-filling key, Auto-apply, the job-site
    # login, the custom AI server and each AI instruction.
    assert {fn for (_, fn), _ in saves} == {
        "ApiKeysEditor", "FolderRow", "FormFillingSection", "AutoApplyEditor", "JobSiteLoginActions",
        "EndpointControls", "PromptCard",
    }
    for key, tag in saves:
        assert _variant(tag) in ('"tonal"', '"outline"'), (key, tag)


# --- The other views -----------------------------------------------------------------------------

_VIEWS = {
    "Today": "app/today/page.tsx",
    "Jobs": "app/applications/page.tsx",
    "Agent inbox": "app/proposals/page.tsx",
    "Job page": "app/jobs/[id]/page.tsx",
    "Automations": "app/automations/page.tsx",
    "Analytics": "app/analytics/page.tsx",
    "Setup": "app/setup/page.tsx",
    "Profile": "app/profile/page.tsx",
}

# Where each view's filled controls sit, {(file, function): how many}. Jobs, Automations and Analytics are a plain
# count (Jobs' Add job shows only while the sidebar's Add job is hidden; Analytics' lead card takes no action). In
# the others the controls are alternatives, each kept apart by the test that names that view below.
_FILLED = {
    "Today": {("app/today/page.tsx", "NextUp"): 1, ("components/setup/setup-entry-card.tsx", "SetupEntryCard"): 1},
    "Jobs": {("app/applications/page.tsx", "ApplicationsContent"): 1},
    "Agent inbox": {
        ("components/proposals/proposals-section.tsx", "ProposalsSection"): 1,
        ("components/proposals/triage-actions.tsx", "BulkBar"): 1,
    },
    "Job page": {
        ("components/resume-step.tsx", "ResumeStep"): 3,
        ("components/tailored-resume-step.tsx", "TailoredResumeStep"): 1,
        ("components/apply-step.tsx", "ApplyStep"): 1,
    },
    "Automations": {},
    "Analytics": {},
    "Setup": {("components/setup/setup-flow.tsx", "StepNav"): 1, ("components/setup/setup-done.tsx", "SetupDone"): 1},
    "Profile": {("components/profile/next-up.tsx", "NextUp"): 2},
}


@pytest.mark.parametrize("view", list(_VIEWS))
def test_a_views_filled_controls_are_its_leads(view):
    # Mutants: the cover letter's Save filled beside Apply's lead card, the persona's Save beside Profile's Next up.
    assert _filled_in(_rendered(_VIEWS[view])) == _FILLED[view]


def test_the_graph_reaches_a_cards_own_save_and_not_a_dialogs():
    # A cover letter's Save sits in Apply's lead card; the persona editor in a Profile tile. The graph follows
    # functions, not files: the job page renders triage-actions' Skip dialog, never the Select-mode bar beside it.
    job = _rendered(_VIEWS["Job page"])
    assert ("components/qa-tab.tsx", "QAEntryCard") in job
    assert ("components/proposals/triage-actions.tsx", "BulkBar") not in job
    assert ("components/profile/how-you-come-across.tsx", "PersonaEditor") in _rendered(_VIEWS["Profile"])


def _body(view: str, key: tuple[str, str]) -> str:
    return squash(_rendered(_VIEWS[view])[key])


def test_today_leads_with_next_up_or_setup_never_both():
    # One ternary chain: Next up, else a skeleton while Setup's status loads, else Setup's card, else a quiet line.
    page = _body("Today", ("app/today/page.tsx", "TodayPage"))
    lead = "{data.next_up ? ( <NextUp item={data.next_up} onSkipped={() => (skipped.current = true)} /> ) : setup.isPending"
    setup = ") : setup.data && needsSetup(setup.data) ? ( <SetupEntryCard status={setup.data} /> ) : ("
    assert page.count("<NextUp") == page.count("<SetupEntryCard") == 1
    assert lead in page and setup in page and page.index(lead) < page.index(setup)


def test_the_inbox_empty_state_returns_before_the_select_bar():
    section = _body("Agent inbox", ("components/proposals/proposals-section.tsx", "ProposalsSection"))
    empty = section[section.index("if (items.length === 0) {") :]
    empty = empty[: empty.index(" ); }") + 5]
    assert "return ( <EmptyState" in empty and empty.count("buttonVariants()") == 1
    assert section.count("buttonVariants()") == 1
    assert section.index(empty) < section.index("{selecting ? ( <BulkBar")


def test_a_job_step_shows_alone_and_leads_with_its_card():
    page = _body("Job page", ("app/jobs/[id]/page.tsx", "JobDetailPage"))
    for step, card in (("fit", "<ResumeStep"), ("output", "<TailoredResumeStep"), ("qa", "<ApplyStep")):
        assert page.index(f'<div hidden={{step !== "{step}"}} className="space-y-4">') < page.index(card)
    # Step 2 with nothing scored: the import or Score my resumes, each its own early return, before the lead card.
    resume = _body("Job page", ("components/resume-step.tsx", "ResumeStep"))
    unscored = resume[resume.index("if (baseRows.length === 0) {") : resume.index("const lowCoverageEverywhere")]
    assert len(_filled(unscored)) == 2 and unscored.count("return (") == 2 and "<LeadCard" not in unscored
    assert resume.index("const lowCoverageEverywhere") < resume.index("<LeadCard")


def test_setup_continue_and_the_done_card_never_show_together():
    flow = _body("Setup", ("components/setup/setup-flow.tsx", "SetupScreens"))
    assert "{step < SETUP_STEPS.length ? <StepNav {...nav} onSkip={() => go(step + 1)} /> : null}" in flow
    body = _body("Setup", ("components/setup/setup-flow.tsx", "StepBody"))
    assert body.index("default: return ( <SetupDone") > body.index('case "answers":')


def test_profile_next_up_returns_one_lead_card():
    next_up = _body("Profile", ("components/profile/next-up.tsx", "NextUp"))
    assert next_up.count("<LeadCard") == next_up.count("return ( <LeadCard") == 2
    assert next_up.index('if (current.kind === "diversity") {') < next_up.index("return ( <LeadCard")
