"""Pins for dialogs that keep what the user typed, or paid a model call for.

Esc, an overlay click and the Close button used to throw away every field and
every LLM proposal in five dialogs. Each pin names the gesture it keeps: the
draft lives above the popup (or the popup stays mounted), the caller mounts
the dialog for the page's lifetime, and only a success clears it. A kept
proposal that edits by index carries the resume it was made against.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


def _flat(source: str) -> str:
    return " ".join(source.split())


def _between(source: str, start: str, end: str) -> str:
    """From `start` up to the first `end` after it."""
    i = source.index(start)
    return source[i : source.index(end, i + len(start))]


_DIALOG = _read("components/ui/dialog.tsx")
_NBR = _read("components/base-resumes/new-base-resume-dialog.tsx")
_GETTING_STARTED = _read("components/setup/getting-started-card.tsx")
_SHEET = _read("components/resume-editor/instruct-sheet.tsx")
_DEMONSTRATE = _read("components/resume-health/demonstrate-skill-dialog.tsx")
_FINDINGS = _read("components/resume-health/finding-cards.tsx")
_SEND = _read("components/career/send-to-resume-dialog.tsx")
_ENTITY = _read("components/career/entity-detail.tsx")
_NEW_ENTITY = _read("components/career/new-entity-dialog.tsx")
_CAREER_PAGE = _read("app/career/page.tsx")
_RESUMES_HOOK = _read("hooks/use-base-resume-label.ts")
_RESUMES_PAGE = _read("app/base-resumes/page.tsx")
_ROLE_HOOK = _read("components/role-category-picker.tsx")
_HEALTH_PAGE = _read("components/resume-health/health-report-page.tsx")


def _mounted_for_good(src: str, tag: str) -> bool:
    """The element is rendered unconditionally: not behind `&&`, `?` or `(`."""
    return f"<{tag}" in src and not re.search(rf"(&&|\?|\()\s*<{tag}\b", src)


def test_dialog_content_can_stay_mounted():
    """Opt-in: a dialog passes `keepMounted` and its popup, state and requests
    live on while closed. Every other dialog still unmounts on close."""
    content = _between(_DIALOG, "function DialogContent(", "\n}\n")
    assert "keepMounted = false," in content
    assert "keepMounted?: boolean" in content
    assert "<DialogPortal keepMounted={keepMounted}>" in content


def test_new_base_resume_keeps_its_form():
    """Esc or an overlay click mid-"Suggesting" kept nothing: the form lived in
    the popup and remounted per open. Now the popup stays mounted, a landed plan
    arrives into the kept form, and only Start over clears it."""
    wrapper = _between(_NBR, "export function NewBaseResumeDialog(", "\nfunction NewBaseResumeForm(")
    assert 'key={open ? "open" : "closed"}' not in _NBR
    assert "key={formGen}" in wrapper
    start_over = _flat(_between(wrapper, "onStartOver={() => {", "}}"))
    assert "setFormGen((g) => g + 1);" in start_over
    # The pressed button unmounts with the old form; focus goes to the new one.
    assert "focusNext(popupRef);" in start_over
    assert '<DialogContent size="lg" keepMounted ref={popupRef}>' in wrapper


def test_the_base_resumes_page_keeps_its_dialog_mounted():
    assert "<NewBaseResumeDialog open={createOpen}" in _flat(_RESUMES_PAGE)
    assert _mounted_for_good(_RESUMES_PAGE, "NewBaseResumeDialog")


def test_a_kept_new_base_resume_form_fetches_roles_only_when_opened():
    """Mounted while closed, the form fetched the role vocabulary on every
    page that holds it. Its pickers get the list from the form ([] while it
    loads), or each would fetch it itself."""
    assert "const roles = useRoleCategories({ enabled: open });" in _NBR
    assert "const roleCategories = roles.data ?? NO_ROLES;" in _NBR
    assert "roleCategories={roles.data}" not in _NBR
    assert _NBR.count("roleCategories={roleCategories}") == 3
    hook = _between(_ROLE_HOOK, "export function useRoleCategories(", "\n}\n")
    assert "{ enabled = true }: { enabled?: boolean } = {}" in hook
    assert re.search(r"\benabled,\n", hook)


def test_start_over_knows_what_a_draft_is():
    """Start over shows once anything differs from a fresh form; switching tabs
    is not a draft. The kept form must not fetch the KB on every visit."""
    assert 'enabled: open && mode === "kb"' in _NBR
    touched = _flat(_between(_NBR, "const touched =", ";"))
    for field in ("name", "instruction", "selected.size", "plan", "source", "file"):
        assert re.search(rf"[(|] ?{re.escape(field)} ?[|)]", touched), field
    assert "tag !== initialTag" in touched
    assert "const [tag, setTag] = useState<FavoredRole | null>(initialTag);" in _NBR


def test_start_over_shows_only_for_a_touched_draft():
    footer = _flat(_between(_NBR, "<DialogFooter>", "</DialogFooter>"))
    assert footer.count("Start over") == 1
    start_over = footer[footer.index("{touched && (") : footer.index("Start over")]
    assert "onClick={onStartOver}" in start_over
    assert "disabled={busy}" in start_over
    assert "> Close </Button>" in footer
    assert "Cancel" not in footer


def test_new_base_resume_ids_are_per_instance():
    """Getting started keeps one form per suggestion, all mounted at once. A
    fixed id then names the first (hidden) form's field, and the open form's
    label and hint point at nothing."""
    assert not re.search(r'(?:id|htmlFor|aria-describedby)="nbr_', _NBR)
    assert "useId()" in _NBR


def test_getting_started_keeps_one_draft_per_suggestion():
    """Closing suggestion A and opening B used to unmount A's form."""
    assert "composeSuggestion" not in _GETTING_STARTED
    flat = _flat(_GETTING_STARTED)
    assert (
        "setOpened((all) => all.some((s) => s.role_category === suggestion.role_category) "
        "? all : [...all, suggestion], );"
    ) in flat
    dialogs = flat[flat.index("{opened.map((suggestion) => (") :]
    dialogs = dialogs[: dialogs.index("))}")]
    assert (
        "<NewBaseResumeDialog key={suggestion.role_category} "
        "open={openRole === suggestion.role_category}"
    ) in dialogs
    assert "initialRole={suggestion}" in dialogs
    assert "if (!next) setOpenRole(null);" in dialogs
    assert "onClick={() => compose(suggestion)}" in flat


def test_a_suggested_role_is_named_by_its_label():
    """The suggestion's picker showed the raw key ("ai_ml_engineer"), and a
    create sent it as the role label. The caller hands over the catalog label
    it already has (mutant: the key as the label)."""
    assert "initialRole?: { role_category: string; label: string };" in _NBR
    initial = _flat(_between(_NBR, "const [initialTag] = useState<FavoredRole | null>(() =>", ");"))
    assert (
        "initialRole ? { role: initialRole.role_category, label: initialRole.label, category: null } : null"
    ) in initial
    assert "favoredRoleFromTag(initialRole" not in _NBR


def test_instruct_sheet_keeps_a_proposal_until_applied():
    """Esc, the overlay and Close used to reset the instruction and the paid
    proposal. Only Apply's success and Discard clear it now."""
    assert "handleOpenChange" not in _SHEET
    assert "reset" not in _SHEET
    assert "<Sheet open={open} onOpenChange={onOpenChange}>" in _SHEET
    apply_success = _between(_SHEET, "const apply = useMutation(", "onError:")
    assert "setKept(null);" in apply_success
    assert 'setInstruction("");' in apply_success
    assert "onOpenChange(false);" in apply_success
    assert _SHEET.count("setKept(null)") == 2, "Apply's success and Discard only"
    assert "onClick={() => setKept(null)}" in _flat(_SHEET)


def test_a_kept_proposal_refuses_to_apply_once_the_resume_moved():
    """Ops edit by index. A proposal made before a Save would PATCH the wrong
    bullets, so each one carries the saved copy it was made against."""
    assert "const basis = useMemo(() => serverKey(resume), [resume]);" in _SHEET
    assert "const stale = kept !== null && kept.basis !== basis;" in _SHEET
    propose = _flat(_between(_SHEET, "const propose = useMutation(", "onError:"))
    assert "mutationFn: (sent: { instruction: string; basis: string }) =>" in propose
    assert "body: JSON.stringify({ instruction: sent.instruction })" in propose
    assert ".then((result) => ({ result, basis: sent.basis }))" in propose
    assert "onSuccess: setKept" in propose
    assert "onClick={() => proposeOnce({ instruction, basis })}" in _flat(_SHEET)


def test_a_stale_proposal_says_so_and_cannot_apply():
    apply_button = _flat(_SHEET[_SHEET.index("onClick={() => applyOnce()}") - 400 :])
    apply_button = apply_button[: apply_button.index("onClick={() => applyOnce()}")]
    assert "disabled={busy || stale}" in apply_button
    note = _flat(_between(_SHEET, "{stale ? (", ") : null}"))
    assert "The resume changed since this was proposed." in note


def test_instruct_sheet_keeps_focus_while_it_works():
    """Propose disabled the button that had focus, and focus fell to <body>."""
    textarea = _flat(_between(_SHEET, "<Textarea", "/>"))
    assert "readOnly={busy}" in textarea
    assert "disabled={busy}" not in textarea
    flat = _flat(_SHEET)
    for click in ("proposeOnce({ instruction, basis })", "applyOnce()"):
        button = flat[flat.rindex("<Button", 0, flat.index(click)) : flat.index(click)]
        assert "focusableWhenDisabled" in button, click
        assert "data-disabled:opacity-50" in button, click


def test_demonstrate_skill_keeps_its_draft():
    """Esc or Cancel reset the picked bullet, the prose and the drafted rewrite."""
    assert "<Dialog open={open} onOpenChange={onOpenChange}>" in _flat(_DEMONSTRATE)
    calls = _DEMONSTRATE.replace("const reset = () =>", "")
    assert calls.count("reset()") == 1
    apply_success = _between(_DEMONSTRATE, "const applyMut = useMutation(", "onError:")
    assert "reset();" in apply_success
    assert "> Close </Button>" in _flat(_DEMONSTRATE)
    assert "Cancel" not in _DEMONSTRATE


def test_findings_keep_one_demonstrate_dialog_per_skill():
    assert "{skill && data && (" not in _FINDINGS
    flat = _flat(_FINDINGS)
    assert "setOpened((s) => (s.includes(subject) ? s : [...s, subject]));" in flat
    dialogs = flat[flat.index("{data && opened.map((s) => (") :]
    dialogs = dialogs[: dialogs.index("/> ))}")]
    assert "<DemonstrateSkillDialog key={s} open={skill === s}" in dialogs
    # Closing only closes: the dialog, and its draft, stay in `opened`.
    assert "onOpenChange={(open) => { if (!open) setSkill(null); }}" in dialogs
    assert "setDoneSkills((d) => new Set(d).add(s));" in dialogs
    assert "onClick={() => !done && openSkill(subject)}" in flat


def test_send_to_resume_stays_mounted():
    """The page mounted the dialog only while open, so a close dropped the
    adapted rows and a reopen mid-Apply offered a second Apply."""
    assert "sendOpen ? (" not in _ENTITY
    flat = _flat(_ENTITY)
    assert "<SendToResumeDialog key={sendGen} open={sendOpen}" in flat
    assert _mounted_for_good(_ENTITY, "SendToResumeDialog")
    assert "onSent={() => setSendGen((g) => g + 1)}" in flat
    finish = _flat(_between(_SEND, "const finishPort =", "\n  };\n"))
    assert finish.endswith("onOpenChange(false); onSent();")

    footer = _flat(_between(_SEND, "<DialogFooter>", "</DialogFooter>"))
    assert "> Close </Button>" in footer
    assert "Cancel" not in footer


def test_a_kept_send_selection_follows_the_points():
    """The dialog outlives many opens: the selection is read against the
    points as they are NOW, so a point retired or deleted since drops out
    and one approved since is in (while untouched)."""
    flat = _flat(_SEND)
    assert (
        "const approved = useMemo( () => entity.points.filter((point) => point.state === \"approved\"),"
        " [entity.points], );" in flat
    )
    assert "const approvedIds = useMemo(() => new Set(approved.map((p) => p.id)), [approved]);" in flat
    assert (
        "(picked === null ? approvedIds : new Set([...picked].filter((id) => approvedIds.has(id))))"
        in flat
    )
    assert "const next = new Set(current ?? approvedIds);" in flat
    assert "useState(\n    () => new Set(approved" not in _SEND


def test_a_kept_send_dialog_fetches_resumes_only_when_opened():
    """Mounted with the page, the dialog would fetch the resume list on every
    career item visit."""
    assert "useBaseResumes(false, { enabled: open })" in _SEND
    hook = _between(_RESUMES_HOOK, "export function useBaseResumes(", "\n}\n")
    assert "{ enabled = true }: { enabled?: boolean } = {}" in hook
    assert re.search(r"\benabled,\n", hook)


def test_a_failed_refresh_keeps_the_career_item_page():
    """A failed background refetch swapped the page for an error and unmounted
    the kept Send dialog and any open editor with it."""
    assert "const loadError = useLoadFailureError(entity);" in _ENTITY
    assert "entity.error ||" not in _ENTITY
    body = _ENTITY[_ENTITY.index("export function EntityDetail(") :]
    assert body.index("if (loadError != null) {") < body.index("if (!entity.data) {")


def test_the_findings_filter_hides_notes_instead_of_unmounting_them():
    """The notes table holds the kept Demonstrate-skill drafts."""
    flat = _flat(_HEALTH_PAGE)
    assert "showNotes && notes.length > 0" not in flat
    assert "{notes.length > 0 && ( <NotesTable hidden={!showNotes}" in flat
    assert "<section ref={sectionRef} id=\"notes\" tabIndex={-1} hidden={hidden}" in _FINDINGS


def test_new_entity_keeps_its_draft():
    """SYSTEM.md §11 item 32: Esc or an overlay click reset the form."""
    assert "<Dialog open={open} onOpenChange={onOpenChange}>" in _flat(_NEW_ENTITY)
    assert _NEW_ENTITY.count("reset();") == 1
    success = _between(_NEW_ENTITY, "onSuccess: async (entity) =>", "onError:")
    assert "reset();" in success
    assert "key={newEntity.kind}" not in _CAREER_PAGE
    footer = _flat(_between(_NEW_ENTITY, "<DialogFooter>", "</DialogFooter>"))
    assert "onClick={() => onOpenChange(false)}" in footer
    assert "> Close </Button>" in footer
    assert "Cancel" not in footer


def test_a_new_default_kind_moves_only_an_untouched_draft():
    """Opened from another tab: an empty form takes that tab's kind; typed text
    keeps the kind it was typed for. Checked on every OPEN, not only when the
    tab changes: a title cleared and closed on Projects, reopened on Education,
    stayed a Project (mutant: the old `defaultKind !== shownDefault` check)."""
    pristine = _flat(_between(_NEW_ENTITY, "const pristine =", ";"))
    for field in ("title", "org", "startDate", "endDate"):
        assert f"!{field}.trim()" in pristine, field
    assert 'sectionTitle === (defaultSectionTitle ?? "")' in pristine
    assert 'sectionKey === (defaultSectionKey ?? "")' in pristine
    assert "const [wasOpen, setWasOpen] = useState(open);" in _NEW_ENTITY
    adjust = _flat(_between(_NEW_ENTITY, "if (open !== wasOpen) {", "}"))
    assert "setWasOpen(open);" in adjust
    assert "if (open && pristine) setKind(defaultKind);" in adjust
    assert "shownDefault" not in _NEW_ENTITY


@pytest.mark.parametrize(
    ("rel", "src", "call"),
    [
        ("new-entity-dialog", _NEW_ENTITY, "if (isValid) createOnce();"),
        ("new-base-resume-dialog", _NBR, "onClick={() => submit()}"),
    ],
    ids=["new-entity", "new-base-resume"],
)
def test_a_dialog_creates_once_per_gesture(rel, src, call):
    """A double click read `isPending === false` twice and created twice."""
    assert "useSingleFlight(create.mutate)" in src, rel
    assert call in _flat(src), rel
    assert "create.mutate" not in src.replace("useSingleFlight(create.mutate)", ""), rel


@pytest.mark.parametrize(
    ("rel", "src", "mutation", "guarded"),
    [
        ("new-base-resume", _NBR, "proposePlan", "proposeOnce"),
        ("instruct-sheet", _SHEET, "propose", "proposeOnce"),
        ("instruct-sheet", _SHEET, "apply", "applyOnce"),
        ("demonstrate-skill", _DEMONSTRATE, "draftMut", "draftOnce"),
        ("demonstrate-skill", _DEMONSTRATE, "applyMut", "applyOnce"),
        ("send-to-resume", _SEND, "port", "portOnce"),
        ("send-to-resume", _SEND, "adapt", "adaptOnce"),
        ("send-to-resume", _SEND, "apply", "applyOnce"),
    ],
    ids=lambda v: v if isinstance(v, str) and len(v) < 20 else "",
)
def test_a_dialog_generates_or_applies_once_per_gesture(rel, src, mutation, guarded):
    """Decision 2: every create and generate button is single-flight. A double
    click paid for two model calls, or applied ops (add_bullet) twice."""
    assert f"const {guarded} = useSingleFlight({mutation}.mutate);" in src, rel
    rest = src.replace(f"useSingleFlight({mutation}.mutate)", "")
    assert f"{mutation}.mutate" not in rest, f"{rel}: a direct start skips the guard"
    assert f"onClick={{() => {guarded}(" in rest, rel
