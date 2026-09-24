"""Pins: one word per kind of agent (UX IA plan, Task 15; appendix A5 and A8).

The Assistant is the in-app chat, connected agents are MCP clients, Companion
is the browser extension, and chat's approval cards are suggestions, so
"proposal" means only a job an agent filed. Each row is a string that left the
screen and the one that replaced it; identifiers and the API stay. The words
are the glossary's (appendix D0, planner decisions 19 and 20): "Quick tailor",
never "Fast tailor", and "Companion" as a proper name ("the Companion" in a
sentence).

The Settings › Connected agents tab opens with an explainer card; its mount
order is pinned in test_frontend_settings_pages.py.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_FRONTEND = _ROOT / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


# (file, gone, present)
_WORDS = [
    ("components/source-toggle.tsx", '"You" : "Agent"}', '"You" : "Agents"}'),
    ("components/career/points-list.tsx", 'mcp: "Agent",', 'mcp: "Connected agent",'),
    ("components/career/points-list.tsx", 'chat: "Capture",', 'chat: "Assistant",'),
    # A5 row 21: the origin chip's hover names the writer in words, never a slug ("claude-ai").
    ("components/career/points-list.tsx", "`Written by ${point.origin_detail}`",
     "`Written by ${agentDisplayName(point.origin_detail) ?? point.origin_detail}`"),
    ("components/settings/mcp-workflow-section.tsx", 'title="Agent workflow hints"',
     'title="Next-step hints for connected agents"'),
    ("components/settings/mcp-workflow-section.tsx", "Career Studio's MCP tool results",
     "Adds a suggested next step to what the app tells a connected agent,"),
    ("components/settings/mcp-workflow-section.tsx", "Suggest the next step in MCP tool results",
     "Suggest the next step to connected agents"),
    ("components/settings/auto-apply-section.tsx", "Guardrails for the agent hunt-and-apply lane.",
     "Limits on what connected agents may do when they find and apply to jobs."),
    ("components/settings/auto-apply-section.tsx", "Approving a proposal reserves a slot",
     "Each application you say yes to submit counts for 24 hours."),
    ("components/settings/auto-apply-section.tsx", '"Proposals per hunt run"', '"Jobs per search"'),
    ("components/settings/auto-apply-section.tsx", "The hunt never captures or proposes",
     "Connected agents can&apos;t propose jobs at these companies."),
    # The server refuses only a proposal at a blocked company (routers/proposals.py);
    # an agent can still save the job.
    ("components/settings/auto-apply-section.tsx", "never saves", 'aria-describedby="aa-blocklist-hint"'),
    ("components/settings/auto-apply-section.tsx", "Skipping a single", "Skipping one job does not block"),
    ("components/ats-score-panel.tsx", "any open agent proposal", "any open proposal in your Agent inbox"),
    ("components/chat/proposal-card.tsx", "Proposed project", "Suggested project"),
    ("components/chat/edit-proposal-card.tsx", "/> Suggested edit\n",
     '{`Suggested ${proposal.ops_count === 1 ? "edit" : "edits"}`}'),
    # The badge agrees in number with the chat card's.
    ("components/resume-editor/instruct-sheet.tsx", '{hasOps ? "Suggested edit" : "Answer"}',
     '{hasOps ? `Suggested ${proposal.ops_count === 1 ? "edit" : "edits"}` : "Answer"}'),
    ("components/resume-editor/instruct-sheet.tsx", '"Propose again" : "Propose"',
     '"Suggest again" : "Suggest edits"'),
    ("components/resume-editor/instruct-sheet.tsx", "No edits proposed.", "No edits suggested."),
    ("components/resume-editor/instruct-sheet.tsx", "you apply\n            a proposal,",
     "you apply\n            a suggestion,"),
    ("components/settings/quick-tailor-section.tsx", "Fast tailor",
     "What Quick tailor may change on your resume, on the gap analysis page and in the Companion."),
    ("components/settings/quick-tailor-section.tsx", "one-shot tailoring", 'title="Quick tailor"'),
    ("components/settings/autofill-section.tsx", "Preset answers the browser extension uses",
     "The Companion uses these to fill job applications."),
    ("components/settings/autofill-section.tsx", "Allow extension to fill these answers",
     "Let Companion fill these answers"),
    ("components/settings/autofill-section.tsx", "Allow extension to tick agreement boxes",
     "Let Companion tick agreement boxes"),
    ("components/settings/autofill-section.tsx", "matching the extension&apos;s",
     "Most recent first."),
    # The Companion has no ⋯ menu and no switch for capture (extension/README.md, "Turn it off").
    ("components/analytics/autofill-coverage-card.tsx", "extension card's",
     "Clearing removes what's recorded so far. Capture continues while the Companion runs."),
    ("components/analytics/autofill-coverage-card.tsx", "⋯ menu", "It cannot be undone."),
    ("components/analytics/autofill-coverage-card.tsx", "where the extension's fill pipeline",
     "where the Companion's fill pipeline fails."),
    ("components/analytics/autofill-coverage-card.tsx", "with the extension to start capturing",
     "with the Companion to start capturing"),
]


@pytest.mark.parametrize(
    ("rel", "gone", "present"),
    _WORDS,
    ids=[f"{rel.rsplit('/', 1)[-1]}:{i}" for i, (rel, _, _) in enumerate(_WORDS)],
)
def test_one_word_per_kind_of_agent(rel: str, gone: str, present: str):
    src = _read(rel)
    assert gone not in src, f"{rel} still says {gone!r}"
    assert present in src, f"{rel} lost {present!r}"


def test_no_screen_says_swarm_or_the_chat_agent():
    for root in ("app", "components"):
        for path in (_FRONTEND / root).rglob("*.tsx"):
            rel = path.relative_to(_FRONTEND).as_posix()
            src = path.read_text(encoding="utf-8")
            for word in ("hunt swarm", "the chat agent", "Found by agent", "Agent lane"):
                assert word not in src, f"{rel}: {word!r}"


def test_the_source_toggle_keeps_its_preview():
    """The segment reads "Agents"; lane 2's hover and focus preview stays wired."""
    src = _read("components/source-toggle.tsx")
    assert "onPointerEnter={() => onPreview?.(s)}" in src
    assert "onFocus={() => onPreview?.(s)}" in src


# --------------------------------------------------------------- Connected agents card

def _card() -> str:
    return _read("components/settings/connected-agents-card.tsx")


def test_the_connected_agents_card_explains_before_the_limits():
    card = _card()
    assert '<Card id="connected-agents">' in card
    assert "<SettingCard" not in card  # fetches nothing: the Appearance precedent
    assert '<CardTitle role="heading" aria-level={2}>' in card
    assert '<CardContent className="@container/setting">' in card
    # MCP is the one term that stays; it is spelled out where it first appears.
    assert "MCP (Model Context Protocol)" in card
    assert "setup-mcp.sh" not in card  # only Cursor and others need it; the guide covers it


# Exactly what a connected agent can and can't do, checked against the MCP tools
# (backend/mcp_server/server.py). An overclaim such as "Submit applications for
# you." without "after your yes", or "Delete anything" when it can't, fails here.
_CAN = (
    "Find jobs and file them in your {AGENT_INBOX} for you to queue or skip.",
    "Read your career history and job preferences.",
    "Add to and change your career history. New or reworded bullets arrive as drafts for you"
    " to approve. Other changes, such as an item&apos;s dates or your summary, skills and contact"
    " details, apply at once.",
    # kb_approve_points: its "only after the user said yes" is a docstring rule, not a server check.
    "Approve bullets, or mark them Not used, in your career history. They&apos;re told to do this only"
    " after you say yes. That&apos;s a rule they&apos;re given, not a lock.",
    "Create, edit and tailor your resumes.",
    "Fill in and submit applications you queued, after your yes.",
)
_CANT = (
    "Go past the daily limit below.",
    "Delete an item or a bullet from your career history.",
    "Connect from claude.ai or chatgpt.com in a browser.",
)
_AGENT_INBOX = '<Link href="/proposals" className="text-primary underline underline-offset-4"> Agent inbox </Link>'


def _list_items(heading_id: str) -> list[str]:
    flat = " ".join(_card().split())
    ul = flat[flat.index(f"<ul aria-labelledby={{{heading_id}}}") :]
    ul = ul[ul.index(">") + 1 : ul.index("</ul>")]
    items = re.findall(r"<li>\s*(.*?)\s*</li>", ul)
    return [re.sub(r"\{/\*.*?\*/\}\s*", "", i).replace('{" "}', " ").replace("  ", " ") for i in items]


def test_the_card_says_exactly_what_agents_can_do():
    assert _list_items("canId") == [c.replace("{AGENT_INBOX}", _AGENT_INBOX) for c in _CAN]


def test_the_card_says_exactly_what_agents_cant_do():
    assert _list_items("cantId") == list(_CANT)


def test_the_card_keeps_the_honesty_nuance():
    """Nothing is submitted without a yes, and that yes is a record, not a lock
    (README, "Going all the way"): the daily limit counts the recorded yeses, so
    an agent that skips recording isn't stopped. The app itself never hunts or
    applies."""
    flat = " ".join(_card().split())
    assert "Maestro CS itself never looks for jobs or submits an application." in flat
    assert "Before each submit, the agent asks for your yes and records it." in flat
    assert "The daily limit below counts those yeses over the last 24 hours." in flat
    assert "The app records each yes but can&apos;t stop an agent, so stay with it while it applies." in flat
    assert "apply sessions" not in flat


def test_the_card_names_the_two_helpers_that_are_not_connected_agents():
    """The glossary's one sentence that says what Companion is (appendix D0)."""
    flat = " ".join(_card().split())
    assert "Companion, the Maestro CS browser extension," in flat
    assert "the Assistant, which you talk to inside this app," in flat


def test_each_list_is_named_by_its_heading():
    card = _card()
    # Two ids: one shared id would name both lists "They can".
    assert re.findall(r"const (\w+) = useId\(\);", card) == ["canId", "cantId"]
    flat = " ".join(card.split())
    for var, heading in (("canId", "They can"), ("cantId", "They can&apos;t")):
        assert f'<h3 id={{{var}}} className="font-medium"> {heading} </h3>' in flat, var
        assert f"<ul aria-labelledby={{{var}}}" in card, var


def test_the_card_links_open_where_they_say():
    card = _card()
    assert '<Link href="/proposals" className="text-primary underline underline-offset-4">' in card
    # One external-link shape for the three guides: a new tab, no opener, no referrer.
    # Each label names the guide it opens.
    for name, label in (("CONNECT_AGENT_GUIDE_URL", "How to connect an agent"),
                        ("JOB_HUNT_SKILL_URL", "Ready-made skills"),
                        ("AGENT_APPLICATIONS_URL", "How agent applications work")):
        assert f'{{ href: {name}, label: "{label}" }},' in card, name
    assert len(re.findall(r"<a\s", card)) == 1
    flat = " ".join(card.split())
    assert '<a key={href} href={href} target="_blank" rel="noopener noreferrer"' in flat
    # A link that looks like a button is still a link: Base UI's Button gives the <a> it
    # renders role="button".
    assert 'className={buttonVariants({ variant: "outline", size: "sm" })}' in flat
    assert "nativeButton" not in card


_LINK_NAMES = ("REPO", "CONNECT_AGENT_GUIDE_URL", "JOB_HUNT_SKILL_URL", "AGENT_APPLICATIONS_URL")


def test_the_agent_links_have_one_home():
    """The card takes its guides from `lib/agent-links.ts`, the Agent inbox's
    file; that the anchors match real headings is pinned beside the inbox's
    empty state (test_frontend_agent_inbox.py)."""
    card = _card()
    assert (
        'import { AGENT_APPLICATIONS_URL, CONNECT_AGENT_GUIDE_URL, JOB_HUNT_SKILL_URL } '
        'from "@/lib/agent-links";'
    ) in card
    sources = [
        p for root in ("app", "components", "hooks", "lib")
        for p in (_FRONTEND / root).rglob("*.ts*") if p.suffix in (".ts", ".tsx")
    ]
    for name in _LINK_NAMES:
        # One definition: a copy left anywhere else would drift.
        homes = [p.relative_to(_FRONTEND).as_posix() for p in sources
                 if re.search(rf"\bconst {name} = ", p.read_text(encoding="utf-8"))]
        assert homes == ["lib/agent-links.ts"], (name, homes)
    # The repository the git remote and CITATION.cff name, on its main branch.
    citation = (_ROOT / "CITATION.cff").read_text(encoding="utf-8")
    repo = re.search(r'^repository-code: "([^"]+)"$', citation, re.M).group(1)
    assert repo == "https://github.com/seinun-ai/maestro-career-studio"
    assert f'const REPO = "{repo}/blob/main";' in _read("lib/agent-links.ts")


def test_the_guides_call_the_page_the_agent_inbox():
    for rel in ("README.md", "docs/GETTING_STARTED.md"):
        doc = (_ROOT / rel).read_text(encoding="utf-8")
        assert "Agent Proposals" not in doc, rel
        assert "**Agent inbox**" in doc, rel
