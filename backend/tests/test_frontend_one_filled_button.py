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
    "Career history": "app/career/page.tsx",
    "Base resumes": "app/base-resumes/page.tsx",
    "Referrals": "app/referrals/page.tsx",
    "Career item": "app/career/[id]/page.tsx",
    "Chat": "app/chat/page.tsx",
    "Base resume editor": "app/base-resumes/[slug]/page.tsx",
    "Tailored resume editor": "app/applications/[id]/resume/page.tsx",
    "Gap analysis": "app/jobs/[id]/tailor/[sessionId]/page.tsx",
}

# Where each view's filled controls sit, {(file, function): how many}. Jobs, Automations and Analytics are a plain
# count (Jobs' Add job shows only while the sidebar's Add job is hidden; Analytics' lead card takes no action). In
# the others the controls are alternatives, each kept apart by the test that names that view below.
_FILLED = {
    "Today": {
        ("app/today/page.tsx", "NextUp"): 1,
        ("components/setup/setup-entry-card.tsx", "SetupEntryCard"): 1,
        ("components/today/first-job-card.tsx", "FirstJobCard"): 1,
    },
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
    "Profile": {("components/profile/next-up.tsx", "NextUp"): 4},
    "Career history": {
        ("app/career/page.tsx", "CareerPage"): 1,
        ("components/career/inbox-panel.tsx", "InboxPanel"): 1,
    },
    "Base resumes": {("app/base-resumes/page.tsx", "BaseResumesListPage"): 1},
    "Referrals": {("app/referrals/page.tsx", "ReferralsPage"): 1, ("app/referrals/page.tsx", "ReferralForm"): 1},
    "Career item": {("components/career/entity-detail.tsx", "EntityDetail"): 1},
    "Chat": {("components/chat/chat-page.tsx", "ChatPage"): 1},
    "Base resume editor": {("components/resume-editor/studio-save-button.tsx", "StudioSaveButton"): 1},
    "Tailored resume editor": {
        ("components/resume-editor/studio-save-button.tsx", "StudioSaveButton"): 1,
        ("components/resume-editor/tailored-resume-studio.tsx", "BuildDraft"): 1,
    },
    "Gap analysis": {("app/jobs/[id]/tailor/[sessionId]/page.tsx", "TailorSessionPage"): 5},
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
    # One ternary chain: Next up (all but a saved job's next step), else a skeleton while Setup's status loads, else
    # Setup's card, else a saved job's next step, else Add your first job, else a quiet line. Each branch is one card.
    page = _body("Today", ("app/today/page.tsx", "TodayPage"))
    lead = (
        '{data.next_up && data.next_up.kind !== "next_step" ? ( <NextUp item={data.next_up} '
        "onSkipped={() => (skipped.current = true)} /> ) : setup.isPending"
    )
    setup = ") : setup.data && needsSetup(setup.data) ? ( <SetupEntryCard status={setup.data} /> ) : data.next_up ? ("
    first = ") : !data.has_jobs ? ( <FirstJobCard /> ) : ("
    assert page.count("<NextUp") == 2 and page.count("<SetupEntryCard") == page.count("<FirstJobCard") == 1
    assert lead in page and setup in page and first in page
    assert page.index(lead) < page.index(setup) < page.index(first)


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
    # Where you apply's, diversity's, citizenship's and a field's: each its own early return, so one shows.
    next_up = _body("Profile", ("components/profile/next-up.tsx", "NextUp"))
    assert next_up.count("<LeadCard") == next_up.count("return ( <LeadCard") == 4
    assert next_up.index('if (current.kind === "where") {') < next_up.index("return ( <LeadCard")
    diversity = next_up.index('if (current.kind === "diversity") {')
    assert next_up.index("return ( <LeadCard", diversity) < next_up.index('if (current.kind === "citizenship") {')
    citizenship = next_up.index('if (current.kind === "citizenship") {')
    assert next_up.index("return ( <LeadCard", citizenship) < next_up.index("const field = current.field;")


def test_career_history_leads_with_approve_all_or_add_item_never_both():
    # With drafts to review the page showed Approve all shown, every draft's Approve and the header's Add item filled
    # at once. Add item is filled only while the panel's Approve all shown is hidden: the same three conditions.
    page = _body("Career history", ("app/career/page.tsx", "CareerPage"))
    assert (
        "const draftsToReview = !drafts.isLoading && !drafts.error && (drafts.data?.length ?? 0) > 0;" in page
        and "drafts={drafts.data ?? []}" in page and "isLoading={drafts.isLoading} error={drafts.error}" in page
    )
    (add,) = [tag for tag, label in _elements(page, "Button") if "Add item" in label]
    assert _variant(add) == '{draftsToReview ? "tonal" : "default"}', add
    panel = _body("Career history", ("components/career/inbox-panel.tsx", "InboxPanel"))
    (approve_all,) = _filled(panel)
    gate = "{drafts.length > 0 && !isLoading && !error && ("
    assert gate in panel and panel.index(gate) < panel.index(approve_all)


_DRAFT_APPROVE = '<ApproveIcon aria-hidden="true" /> {approving ? "Approving…" : "Approve"}'


def test_a_drafts_own_approve_and_save_are_tonal():
    # A draft row renders once per draft, so the count above sees it once: its actions are pinned by name.
    row = _body("Career history", ("components/career/inbox-panel.tsx", "DraftRow"))
    actions = {label: tag for tag, label in _elements(row, "Button") if label in (_DRAFT_APPROVE, "Save")}
    assert set(actions) == {_DRAFT_APPROVE, "Save"}
    for tag in actions.values():
        assert _variant(tag) == '"tonal"', tag


def _tag_for(body: str, label: str) -> str:
    (tag,) = [tag for tag, children in _elements(body, "Button") if label in children]
    return tag


def test_referrals_leads_with_add_referral_or_the_first_referral_form():
    # The header's Add referral shows only once there are referrals; before that the first-referral card's own Add
    # referral leads (the dialog's is its own view). An edited row's Save sat filled beside the header's: it is tonal.
    page = _body("Referrals", ("app/referrals/page.tsx", "ReferralsPage"))
    assert "actions={ populated ? ( <Button ref={addButtonRef}" in page
    assert ") : populated ? ( <ReferralsTable rows={rows} /> ) : ( <FirstReferralCard" in page
    edit = _body("Referrals", ("app/referrals/page.tsx", "ReferralEditRow"))
    assert _variant(_tag_for(edit, '{update.isPending ? "Saving…" : "Save"}')) == '"tonal"'


def test_a_career_items_lead_is_add_to_a_resume_and_its_cards_save_quietly():
    # Save notes and Save details are their cards' own saves, shown while Add to a resume stays on screen.
    notes = _body("Career item", ("components/career/notes-editor.tsx", "NotesEditor"))
    assert _variant(_tag_for(notes, '"Save notes"')) == '"tonal"'
    header = _body("Career item", ("components/career/entity-detail.tsx", "EntityHeader"))
    assert _variant(_tag_for(header, '"Save details"')) == '"tonal"'


def test_chat_leads_with_send_and_a_cards_answer_is_tonal():
    # Every message's proposal card renders its own button, so the count sees each card once: pinned by name.
    merge = _body("Chat", ("components/chat/proposal-card.tsx", "ProposalCard"))
    assert _variant(_tag_for(merge, '"Add to resume"')) == '"tonal"'
    apply = _body("Chat", ("components/chat/edit-proposal-card.tsx", "EditProposalCard"))
    assert _variant(_tag_for(apply, "apply.isPending")) == '"tonal"'


_EDITOR_DONES = {
    ("components/resume-editor/editable-card.tsx", "EditPane"),
    ("components/resume-editor/contact-form.tsx", "ContactForm"),
    ("components/resume-editor/editor-body.tsx", "SummaryBlock"),
    ("components/resume-editor/editor-body.tsx", "CertificationsBlock"),
    ("components/resume-editor/extra-sections-editor.tsx", "SectionCard"),
}


# editor-body.tsx is the base studio's; the tailored studio lays out its own summary and certifications.
_BASE_ONLY_DONES = {key for key in _EDITOR_DONES if key[0].endswith("editor-body.tsx")}


def _labelled(graph: dict[tuple[str, str], str], label: str) -> list[tuple[tuple[str, str], str]]:
    return [(key, tag) for key, body in graph.items() for tag, text in _elements(squash(body), "Button") if text == label]


@pytest.mark.parametrize(
    "view,expected",
    [("Base resume editor", _EDITOR_DONES), ("Tailored resume editor", _EDITOR_DONES - _BASE_ONLY_DONES)],
)
def test_a_resume_editor_leads_with_save_and_each_card_closes_quietly(view, expected):
    # Every open card's Done, the raw JSON pane's Apply and the sync pill's Add now sat filled beside Save.
    dones = _labelled(_rendered(_VIEWS[view]), "Done")
    assert {key for key, _ in dones} == expected
    assert [tag for _, tag in dones if _variant(tag) != '"tonal"'] == []
    raw = _body(view, ("components/resume-editor/raw-json-toggle.tsx", "RawJsonToggle"))
    assert _variant(_tag_for(raw, "Apply")) == '"tonal"'


def test_the_base_resume_editors_sync_pill_adds_quietly():
    pill = _body("Base resume editor", ("components/kb-sync-pill.tsx", "KbSyncPill"))
    assert _variant(_tag_for(pill, "Add now")) == '"tonal"'


def test_the_tailored_editor_builds_a_draft_or_opens_the_studio_never_both():
    studio = _body("Tailored resume editor", ("components/resume-editor/tailored-resume-studio.tsx", "TailoredResumeStudio"))
    assert studio.index("if (!adoptedData) { return ( <BuildDraft") < studio.index("return ( <StudioEditor")


def test_the_gap_analysis_leads_with_one_button_per_state():
    # Missing or failed: Back to job, each its own early return. Closed: View tailored resume (or Go to Resume and
    # gaps). Open: Tailor resume, except while the analysis is out of date, when Tailor resume cannot run, goes
    # tonal, and the banner's Start new gap analysis leads.
    page = _body("Gap analysis", ("app/jobs/[id]/tailor/[sessionId]/page.tsx", "TailorSessionPage"))
    error, closed, live = (
        page.index("if (sessionError != null) {"),
        page.index('if (session.data.status !== "open") {'),
        page.index("const gapsJson"),
    )
    hits = [page.index(hit) for hit in _filled(page)]
    assert error < hits[0] == hits[1] < closed < hits[2] < live < hits[3] < hits[4]
    # The two Back to job returns, then the loading skeleton's; the closed state's one return.
    assert page[error:closed].count("return (") == 3 and page[closed:live].count("return (") == 1
    stale = page.index("{staleReason ? (")
    assert stale < hits[3] < page.index(") : null}", stale)
    assert _variant(_tag_for(page, '"Tailor resume"')) == '{staleReason ? "tonal" : "default"}'
