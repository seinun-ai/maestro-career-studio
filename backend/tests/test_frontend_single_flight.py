"""One submit per click (UX next, Task 19; appendix F4).

`isPending` cannot guard a double click: react-query re-renders its observers
on a zero-delay timeout, so a second click already queued reads `false` and
starts a second request (two referral rows). Each create button and each
studio's Save, and every create, generate and apply button in a dialog
that keeps its draft, starts its request through `useSingleFlight`, and nothing else
calls the guarded `mutate`, or the guard never clears (the hook's docstring).
The hook's own shape is pinned in `test_frontend_focus.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

_SITES = [
    ("app/referrals/page.tsx", "create"),
    ("app/templates/page.tsx", "create"),
    ("app/templates/page.tsx", "duplicate"),
    ("components/resume-editor/editor-body.tsx", "save"),
    ("components/resume-editor/tailored-resume-studio.tsx", "save"),
    # The dialogs and editors that keep drafts (Tasks 14-16).
    ("components/base-resumes/new-base-resume-dialog.tsx", "create"),
    ("components/base-resumes/new-base-resume-dialog.tsx", "proposePlan"),
    ("components/career/new-entity-dialog.tsx", "create"),
    ("components/career/capture-box.tsx", "capture"),
    ("components/career/capture-box.tsx", "ingest"),
    ("components/career/send-to-resume-dialog.tsx", "port"),
    ("components/career/send-to-resume-dialog.tsx", "adapt"),
    ("components/career/send-to-resume-dialog.tsx", "apply"),
    ("components/resume-editor/instruct-sheet.tsx", "propose"),
    ("components/resume-editor/instruct-sheet.tsx", "apply"),
    ("components/resume-health/demonstrate-skill-dialog.tsx", "draftMut"),
    ("components/resume-health/demonstrate-skill-dialog.tsx", "applyMut"),
    ("components/qa-tab.tsx", "askQuestions"),
    ("components/qa-tab.tsx", "coverLetter"),
    ("components/qa-tab.tsx", "regenerateEntry"),
    # The settings Saves and the catalog's + and Remove (IA wave-1 browser pass: a tight double
    # click sent two PUTs, two POSTs or two DELETEs, the second an error toast).
    ("components/settings/models-section.tsx", "saveKeys"),
    ("components/settings/prompts-section.tsx", "save"),
    ("components/settings/prompts-section.tsx", "reset"),
    ("components/settings/auto-apply-section.tsx", "save"),
    ("components/settings/persona-section.tsx", "save"),
    ("components/settings/persona-section.tsx", "draft"),
    ("components/settings/llm-endpoint.tsx", "save"),
    ("components/settings/model-catalog-panel.tsx", "add"),
    ("components/settings/model-catalog-panel.tsx", "remove"),
    # Profile › Autofill's Save and the Assistant's New chat (waves 1+2 integrated browser pass: a
    # double click sent two PUTs and two toasts, or made two chats).
    ("components/settings/autofill-section.tsx", "save"),
    ("components/chat/chat-page.tsx", "newSession"),
    # Build draft and Rebuild share one guard; Queue for agent on a tracker row and the job header
    # (a double click filed two accepted proposals for one job).
    ("components/resume-editor/tailored-resume-studio.tsx", "materialize"),
    ("app/applications/page.tsx", "promoteJob"),
    ("app/jobs/[id]/page.tsx", "promote"),
    # The Agent inbox's triage: a row's Queue, Skip or Delete, the bulk bar's Queue and Skip, and the job
    # header's (a double click on Queue sent two PATCHes, the second "cannot go accepted -> accepted").
    ("components/proposals/triage-actions.tsx", "transition"),
    ("components/proposals/triage-actions.tsx", "bulk"),
    ("components/proposals/triage-actions.tsx", "remove"),
    # The job workspace (IA wave 3 first read): a double click on Update scores sent a second POST
    # that failed after the first succeeded, Create PDF rendered twice, Find gaps and tailor started
    # two gap analyses, and Use resume as is made two applications for one job.
    ("components/ats-score-panel.tsx", "run"),
    ("components/ats-score-panel.tsx", "createSession"),
    ("components/ats-score-panel.tsx", "appliedAsIs"),
    ("components/application-panel.tsx", "renderPdf"),
    ("app/jobs/[id]/tailor/[sessionId]/page.tsx", "useAsIs"),
]


@pytest.mark.parametrize(("rel", "name"), _SITES)
def test_a_submit_starts_one_request_per_gesture(rel: str, name: str):
    src = (_FRONTEND / rel).read_text()
    guarded = f"useSingleFlight({name}.mutate)"
    assert src.count(guarded) == 1, f"{rel}: {name} is not started through useSingleFlight"
    rest = src.replace(guarded, "")
    # Neither called nor handed on (`onAdd={create.mutate}`) around the guard.
    assert f"{name}.mutate" not in rest, f"{rel}: {name}.mutate is reachable without the guard"
    # Called or handed on (`onClick={save.reset}`): reset() drops the call
    # that clears the guard.
    assert not re.search(rf"\b{name}\.reset\b", rest), f"{rel}: {name}.reset is reachable"


def test_both_referral_forms_share_the_one_guard():
    page = (_FRONTEND / "app/referrals/page.tsx").read_text()
    assert "const add = useSingleFlight(create.mutate);" in page
    assert page.count("onAdd={add}") == 2
    assert "onAdd={create.mutate}" not in page


def test_template_create_and_duplicate_go_through_the_guard():
    page = (_FRONTEND / "app/templates/page.tsx").read_text()
    assert "const createOnce = useSingleFlight(create.mutate);" in page
    assert "onClick={() => createOnce()}" in page
    assert "const duplicateOnce = useSingleFlight(duplicate.mutate);" in page
    assert "<DropdownMenuItem onClick={() => duplicateOnce(t)}>" in page


def test_template_create_keeps_focus_while_it_runs():
    page = (_FRONTEND / "app/templates/page.tsx").read_text()
    create = page[page.index("onClick={() => createOnce()}") :]
    create = create[: create.index("</Button>")]
    # It disables itself while creating: a native `disabled` drops focus.
    assert "focusableWhenDisabled" in create
    assert "data-disabled:pointer-events-none data-disabled:opacity-50" in create


@pytest.mark.parametrize(
    "rel", ["components/resume-editor/editor-body.tsx", "components/resume-editor/tailored-resume-studio.tsx"]
)
def test_studio_save_click_and_shortcut_share_the_guard(rel: str):
    src = (_FRONTEND / rel).read_text()
    assert "const saveOnce = useSingleFlight(save.mutate);" in src
    on_save = src[src.index("const onSave = () =>") :]
    on_save = on_save[: on_save.index(";\n")]
    # Button and Cmd/Ctrl+S both call onSave (StudioSaveButton), so both pass
    # the one guard; the raw draft is applied first, as before.
    assert "raw.commitThen(setData, (applied) =>" in on_save
    assert "saveOnce({" in on_save


def _button_at(src: str, marker: str, tag: str = "<Button") -> str:
    """The `tag` element around `marker`: from its opening to its close."""
    at = src.index(marker)
    close = "/>" if tag == "<IconButton" else "</Button>"
    return src[src.rfind(tag, 0, at) : src.index(close, at)]


def test_build_draft_keeps_focus_while_it_runs_and_hands_it_on():
    # A native `disabled` Build dropped focus to <body>, and the empty state leaves with the button
    # once the draft lands: its handoff lands on the studio's <main>.
    src = (_FRONTEND / "components/resume-editor/tailored-resume-studio.tsx").read_text()
    assert "onBuild={() => materializeOnce()}" in src
    assert "onRebuild={() => materializeOnce()}" in src
    empty = src[src.index("function BuildDraft(") :]
    build = _button_at(empty, "onClick={onBuild}")
    assert "focusableWhenDisabled" in build and "data-disabled:opacity-50" in build
    assert "useFocusHandoff(rootRef);" in empty and "<div ref={rootRef}" in empty


def test_a_tracker_row_queue_keeps_focus_on_the_row():
    # The Queue button unmounts once the job has a proposal; focus went to <body>.
    tracker = (_FRONTEND / "app/applications/page.tsx").read_text()
    queue = _button_at(tracker, "promoteJobOnce(r.job.id);", "<IconButton")
    assert "focusableWhenDisabled" in queue and "data-disabled:opacity-50" in queue
    # The row's ⋯ takes focus once the button leaves, read at the click.
    assert "queued.current = { jobId: r.job.id, next: focusReturnPoint(moreActions(e.currentTarget)) };" in queue
    handoff = tracker[tracker.index("const q = queued.current;") :]
    handoff = handoff[: handoff.index("}, [filtered]);")]
    assert 'r.kind === "saved" && r.job.id === q.jobId && !r.job.proposal_status' in handoff
    assert "focusIfDropped(q.next());" in handoff
    # A failed queue disarms it.
    on_error = tracker[tracker.index("const promoteJob = useMutation(") :]
    assert "queued.current = null;" in on_error[: on_error.index("\n  });")]


def test_the_job_header_queue_keeps_focus_in_the_header():
    job = (_FRONTEND / "app/jobs/[id]/page.tsx").read_text()
    header = _button_at(job, "promoteOnce();")
    assert "focusableWhenDisabled" in header and "data-disabled:opacity-50" in header
    assert "queued.current = true;" in header
    handoff = job[job.index("useLayoutEffect(() => {\n    if (!queued.current || !hasProposal) return;") :]
    assert "focusIfDropped(focusTarget(actionsRef.current));" in handoff[: handoff.index("}, [hasProposal]);")]
    assert "<div ref={actionsRef}" in job


def test_a_queue_race_never_accepts_twice():
    # The POST returns the job's open proposal when one exists; accepting an accepted one again is
    # an illegal transition, which read as a failed queue.
    api = (_FRONTEND / "lib/api.ts").read_text()
    fn = api[api.index("export async function promoteJobToAgentQueue(") :]
    fn = fn[: fn.index("\n}\n")]
    assert fn.index('if (prop.status === "pending_review") {') < fn.index('method: "PATCH"')
    # The PATCH is the guarded block's only statement.
    guarded = fn[fn.index('if (prop.status === "pending_review") {') :]
    assert guarded.index('method: "PATCH"') < guarded.index("\n  }\n")
