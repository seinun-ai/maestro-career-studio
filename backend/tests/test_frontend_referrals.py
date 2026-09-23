"""Pins for the referrals page: the table is the page, adding opens a form.

`test_frontend_query_error_states.py` only proves an error branch comes before
the empty-state copy. It kept passing with a bare `<p>` for the error, with no
initial focus in the dialog, with delete skipping its confirm, and with the
header button beside the error state. These pins carry the behaviour: each one
names a gesture the page must keep.
"""

from __future__ import annotations

import re
from pathlib import Path

_PAGE = (
    Path(__file__).resolve().parents[2] / "frontend/app/referrals/page.tsx"
).read_text()


def _top_level(head: str) -> str:
    """One top-level function, from its signature to its closing brace."""
    start = _PAGE.index(head)
    return _PAGE[start : _PAGE.index("\n}\n", start)]


def _squash(source: str) -> str:
    return re.sub(r"\s+", " ", source)


_ROOT = _top_level("export default function ReferralsPage(")
_CARD = _top_level("function FirstReferralCard(")
_FORM = _top_level("function ReferralForm(")
_VIEW_ROW = _top_level("function ReferralViewRow(")


def _create_success() -> str:
    """The page's create mutation, `onSuccess` up to `onError`."""
    start = _ROOT.index("const create = useMutation(")
    return _ROOT[_ROOT.index("onSuccess:", start) : _ROOT.index("onError:", start)]


def test_a_failed_fetch_is_the_shared_error_state():
    branch = _ROOT[
        _ROOT.index("isLoadFailure(referrals) ?") : _ROOT.index(") : referrals.isLoading ?")
    ]
    assert "<LoadErrorState" in branch, "a failed fetch renders LoadErrorState"
    assert "onRetry=" in branch, "the error state offers a retry"


def test_header_action_shows_only_beside_the_table():
    flat = _squash(_ROOT)
    # Rows held are shown even after a failed refresh (it keeps the loaded
    # table); a data-less failure or load has no rows, so no header action.
    assert "const rows = referrals.data ?? [];" in flat
    assert "const populated = rows.length > 0;" in flat
    assert "actions={ populated ? ( <Button ref={addButtonRef}" in flat
    assert ") : undefined }" in flat


def test_add_dialog_opens_on_the_company_field():
    assert re.search(r"<DialogContent\b[^>]*\binitialFocus=\{companyRef\}", _ROOT)
    dialog = _ROOT[_ROOT.index("<Dialog ") :]
    assert "companyRef={companyRef}" in dialog
    assert re.search(r"id=\{companyId\}\s+ref=\{companyRef\}", _FORM)


def test_first_create_moves_focus_to_the_header_button():
    """The inline form unmounts on the first create; focus must not drop to <body>."""
    effect = _ROOT[_ROOT.index("useEffect(() => {") :]
    effect = effect[: effect.index("}, [populated]);")]
    assert "addButtonRef.current?.focus()" in effect
    assert "focusAddAfterCreate.current" in effect
    # The flag is raised only when this create is the one that makes the table
    # appear, and before the cache update that renders it.
    success = _create_success()
    flat = _squash(success)
    assert (
        "if (!qc.getQueryData<Referral[]>(REFERRALS_KEY)?.length) {"
        " focusAddAfterCreate.current = true; }"
    ) in flat
    assert flat.index("focusAddAfterCreate.current = true") < flat.index("qc.setQueryData")


def test_delete_waits_for_the_confirm():
    on_delete = _VIEW_ROW[_VIEW_ROW.index("const onDelete = async") :]
    confirmed = on_delete.index("await confirm(")
    assert confirmed < on_delete.index("if (!ok) return;") < on_delete.index(
        "remove.mutate()"
    )
    assert _PAGE.count("remove.mutate(") == 1, "no second, unconfirmed delete path"
    button = _VIEW_ROW[_VIEW_ROW.index('label="Delete referral"') :]
    assert "onClick={onDelete}" in button[: button.index("</div>")]


def test_optional_fields_say_so_on_the_label():
    assert "<Label htmlFor={contactId} optional>" in _FORM
    assert "<Label htmlFor={notesId} optional>" in _FORM
    assert "<Label htmlFor={companyId}>" in _FORM
    assert "<Label htmlFor={careersUrlId}>" in _FORM


def test_create_form_placeholders_are_examples():
    placeholders = re.findall(r'placeholder="([^"]*)"', _FORM)
    assert len(placeholders) == 4
    assert all(p.startswith("e.g. ") for p in placeholders), placeholders


def test_field_ids_come_from_use_id():
    names = re.findall(r"htmlFor=\{(\w+)\}", _FORM)
    assert len(names) == 4
    assert all(f"const {n} = useId();" in _FORM for n in names), names
    assert all(f"id={{{n}}}" in _FORM for n in names), names
    assert 'htmlFor="' not in _PAGE


def test_field_rows_are_grids():
    assert "space-y-1.5" not in _PAGE
    rows = re.findall(r'<div className="grid gap-1\.5\b', _FORM)
    assert len(rows) == _FORM.count("<Label ")


def test_the_draft_outlives_the_dialog():
    """Esc or an overlay click unmounts DialogContent; the typed text must stay."""
    assert "const [draft, setDraft] = useState<ReferralDraft>(EMPTY_DRAFT);" in _ROOT
    assert "useState" not in _FORM, "the form holds no field state of its own"
    assert _squash(_ROOT).count("draft={draft} onDraftChange={setDraft}") == 2
    assert "{...draftProps}" in _CARD
    assert "<Dialog open={addOpen} onOpenChange={setAddOpen}>" in _ROOT


def test_only_a_successful_create_clears_the_draft():
    clears = re.findall(r"(?:setDraft|onDraftChange)\(EMPTY_DRAFT\)", _PAGE)
    assert len(clears) == 1
    success = _create_success()
    assert "setDraft(EMPTY_DRAFT)" in success
    assert "setAddOpen(false)" in success, "success closes the dialog"
    assert _PAGE.count("setAddOpen(false)") == 1


def test_one_create_and_the_page_owns_it():
    """The dialog's form unmounts on close; a create it owned ran on unseen,
    and a reopened dialog offered an enabled submit and a second POST."""
    posts = re.findall(r'"/api/referrals",\s*\{\s*method: "POST"', _PAGE)
    assert len(posts) == 1, "one create request in the page"
    assert "useMutation" not in _FORM, "the form starts no request of its own"
    assert "useMutation" not in _CARD
    assert _ROOT.count("useMutation(") == 1
    assert "const create = useMutation(" in _ROOT
    assert _squash(_ROOT).count(
        "adding={create.isPending} onAdd={add}"
    ) == 2, "the inline form and the dialog share the one create (and its guard)"


def test_submit_waits_for_the_shared_create():
    """Wherever the form shows, including a reopened dialog, a pending create
    reads "Adding…" and cannot be submitted again."""
    can_submit = _squash(_FORM[_FORM.index("const canSubmit =") :])
    can_submit = can_submit[: can_submit.index(";")]
    assert can_submit.endswith("&& !adding"), can_submit
    submit = _FORM[_FORM.index("const submit =") :]
    assert "if (!canSubmit) return;" in submit[: submit.index("onAdd(")]
    button = _squash(_FORM[_FORM.index("const submitButton =") :])
    assert "disabled={!canSubmit}" in button
    assert '{adding ? "Adding…" : "Add referral"}' in button
