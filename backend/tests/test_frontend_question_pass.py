"""Pins for the health question pass (health check v3, Task 12): every ask on one page.

The pure helpers (`passProgress`, `batchEditOps`, `passOutcome`, `bulletContext`, `mapPool`) are
covered by `frontend/lib/health-report.test.ts` (Node, not in CI); this file pins what CI can check
from source, including the helpers' load-bearing lines.
"""

from __future__ import annotations

import re
from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_PASS = (_FRONTEND / "components/resume-health/question-pass.tsx").read_text()
_ROUTE = (_FRONTEND / "app/base-resumes/[slug]/health/questions/page.tsx").read_text()
_HELPERS = (_FRONTEND / "lib/health-report.ts").read_text()
_API = (_FRONTEND / "lib/api.ts").read_text()
_WRITES = (_FRONTEND / "components/resume-health/use-pass-writes.ts").read_text()
_ROWS = (_FRONTEND / "components/resume-health/pass-rows.ts").read_text()
_DIALOG = (_FRONTEND / "components/resume-health/accept-all-dialog.tsx").read_text()


def _fn(src: str, head: str, end: str = "\n}\n") -> str:
    body = src[src.index(head):]
    return body[: body.index(end)]


def test_the_page_renders_the_pass_and_back_returns_to_the_tab_it_came_from():
    assert "use(params)" in _ROUTE and "use(searchParams)" in _ROUTE
    assert "<QuestionPass resumeKey={slug} />" in _ROUTE
    assert "Task 12" not in _ROUTE
    # `?from=` is read with useSearchParams (SYSTEM.md §12) and checked; Back opens that tab.
    assert 'const from = parseHealthTab(useSearchParams().get("from"));' in _PASS
    assert 'const reportHref = `/base-resumes/${resumeKey}/health${from ? `?tab=${from}` : ""}`;' in _PASS
    assert "href={reportHref}" in _PASS


def test_the_add_numbers_dialog_is_gone():
    assert not (_FRONTEND / "components/resume-health/batch-ask-dialog.tsx").exists()
    assert "addNumbersLabel" not in _HELPERS


def test_rows_ask_their_own_question_with_the_right_field():
    row = _fn(_PASS, "function PassRowView(")
    assert "isMetricAsk(row.finding)" in _ROWS
    assert "row.useAlternative ? row.finding.alt_question : row.finding.question" in row
    assert '"No number? Answer this instead"' in row
    assert "label={row.finding.measure_target ? `Number for: ${row.finding.measure_target}` : undefined}" in row
    assert "<MetricAskInput" in row and "rows={2}" in row
    # The two quiet controls: Not right? (DisputeBox) and Skip for now.
    assert "<DisputeBox" in row and "Skip for now" in row
    # The bullet in full, as judged text.
    assert "<SourceQuote text={row.original} />" in row


def test_a_skipped_row_still_counts():
    progress = _fn(_HELPERS, "export function passProgress(")
    assert "const total = rows.length;" in progress
    assert "row.answered && !row.skipped" in progress
    # The footer's count and the closing toast both read every row, skipped included.
    assert "passProgress(all.map((row) => ({ answered: isAnswered(row, disputes), skipped: row.skipped })))" in _PASS
    assert "{progress.words}" in _PASS
    assert "const skipped = passRows.filter((row) => row.skipped).length;" in _PASS


def test_drafts_run_three_at_a_time_through_answer_ask():
    assert "const POOL = 3;" in _PASS
    assert "await mapPool(targets, POOL, async (row) => {" in _PASS
    assert "answerAsk(kind, resumeKey, row.finding.id, rowContext(row))" in _PASS


def test_a_queued_row_is_shut_until_its_draft_lands():
    # Write reads the answers on the click: every row it drafts is queued first, and a queued row's
    # fields, Skip and Not right? are shut, so a row skipped or edited after the click is never
    # drafted from its old answer.
    write = _fn(_PASS, "  const writeAll = useMutation({", "\n  });\n")
    assert "onMutate: (targets: PassRow[]) => {" in write
    assert '{ ...row, status: "queued" }' in write
    assert write.index("onMutate") < write.index("mutationFn")
    opened = _fn(_HELPERS, "export function passRowOpen(")
    assert 'return status === "answering" || status === "failed";' in opened
    row = _fn(_PASS, "function PassRowView(")
    assert "const open = passRowOpen(row.status);" in row
    assert row.count("disabled={!open}") == 3  # the number swap, the number fields, the answer box
    assert "locked={!passRowDisputable(row.status)}" in row
    assert 'disabled={!open && row.status !== "drafted" && row.status !== "unrewritable"}' in row


def test_accepted_rows_are_one_write():
    # ONE /edits call for the whole batch: one op per row, each with its hash (one transaction,
    # one new version). The only applyResumeEdits in the pass, never inside a loop.
    assert "applyResumeEdits(" not in _PASS and _WRITES.count("applyResumeEdits(") == 1
    assert (
        "applyResumeEdits(kind, resumeKey, batchEditOps(sent.map((row) => ({ finding: row.finding, text: rowText(row) }))))"
        in _WRITES
    )
    assert "saveBatch(targets, {" in _WRITES and "write: writeBatch," in _WRITES
    assert "bulletEditOp(" not in _PASS and "bulletEditOp(" not in _WRITES
    ops = _fn(_HELPERS, "export function batchEditOps(")
    assert "rows.map((row) => bulletEditOp(row.finding.location, row.text, row.finding.content_hash))" in ops
    # Accept all first lists the rows it will change, each with a checkbox.
    assert "<AcceptAllDialog" in _PASS
    assert "<Checkbox" in _DIALOG and "acceptable.map((row, i)" in _DIALOG
    # Only wording that changes its bullet is offered: a batch that changes nothing writes no version.
    assert "const acceptable = all.filter((row) => !row.skipped && canSave(row));" in _PASS
    assert "changesText(row.original, rowText(row))" in _ROWS
    changes = _fn(_HELPERS, "export function changesText(")
    assert "return original != null && next.length > 0 && next !== original.trim();" in changes
    assert "No change to save" in _PASS


def test_a_409_drops_the_changed_rows_and_resends_the_rest_once():
    batch = _fn(_HELPERS, "export async function saveBatch<")
    assert batch.count("await deps.write(sent)") == 2
    assert batch.index("await deps.changedKeys(sent)") < batch.rindex("await deps.write(sent)")
    # The 409 does not say which op failed: the rows whose text no longer matches are the changed ones.
    assert "staleFindingIds(sent.map((row) => row.finding), fresh.data)" in _WRITES
    assert "This bullet changed." in _PASS and "Write it again?" in _PASS


def test_undo_restores_only_over_its_own_write():
    batch = _fn(_HELPERS, "export async function saveBatch<")
    # V0 is read before the write, and Undo is offered only when the write is V0 + 1.
    assert batch.index("await deps.latestVersion()") < batch.index("await deps.write(sent)")
    assert "undoTo: undoTarget(v0, result.version_number)" in batch
    target = _fn(_HELPERS, "export function undoTarget(")
    assert "written === v0 + 1 ? v0 : null" in target
    save = _fn(_WRITES, "  const save = useMutation({", "\n  });\n")
    assert save.index("if (undoTo == null) {") < save.index('label: "Undo"')
    assert 'toast.success("Saved");' in save
    assert "restoreResumeVersion(kind, resumeKey, v0, { ifLatest: v0 + 1 })" in _WRITES
    assert '"Saved as a new version"' in _WRITES
    assert "\"Can't undo: the resume changed since. Use version history.\"" in _WRITES
    assert "ifLatest != null ? `?if_latest=${ifLatest}` : \"\"" in _API
    # /edits says which version it wrote (none new when nothing changed).
    router = (_FRONTEND.parent / "backend/app/routers/base_resumes.py").read_text()
    assert "version_number=version.version_number," in router
    # A failed Undo still lands focus: on the row's Saved line.
    undo = _fn(_WRITES, "  const undo = useMutation({", "\n  });\n")
    error = undo[undo.index("onError:"):]
    assert "landOn.current = sent[0]?.key ?? null;" in error
    assert "[data-saved]" in _WRITES and "data-saved" in _PASS


def test_one_filled_button_in_view():
    tags = re.findall(r"<Button\b[^>]*?>", _PASS, flags=re.S)
    assert all("variant=" in t for t in tags), [t for t in tags if "variant=" not in t]
    assert 'variant={primary === "write" ? "default" : "tonal"}' in _PASS
    assert 'variant={primary === "accept" ? "default" : "tonal"}' in _PASS
    assert 'const primary = writable.length > 0 || acceptable.length === 0 ? "write" : "accept";' in _PASS
    # The Accept all dialog's own confirm is the one filled button of that (modal) view.
    assert 'variant="default"' not in _PASS and _DIALOG.count('variant="default"') == 1
    assert all("variant=" in t for t in re.findall(r"<Button\b[^>]*?>", _DIALOG, flags=re.S))


def test_the_context_pane_highlights_the_active_bullet():
    assert "hidden xl:block" in _PASS and "xl:hidden" in _PASS
    assert "bg-primary/10 border-l-2 border-primary" in _PASS
    assert "bulletContext(" in _PASS
    assert "max-w-[65ch]" in _PASS


def test_unsent_answers_and_edits_ask_before_leaving():
    assert "useLeaveGuard(unsaved)" in _PASS
    # A typed answer on a changed row (or one being checked again) is unsaved too.
    assert '["answering", "failed", "changed", "checking"].includes(row.status) && rowContext(row).length > 0' in _PASS


def test_one_write_it_again_at_a_time():
    assert 'const checking = all.some((row) => row.status === "checking");' in _PASS
    assert "recheckBusy={checking}" in _PASS
    assert 'disabled={row.status === "checking" || recheckBusy}' in _PASS


def test_a_version_is_the_resumes_the_bullet_gets_wording():
    assert "writeWordingsLabel(writable.length)" in _PASS
    assert 'Accept {chosen.length} new {chosen.length === 1 ? "wording" : "wordings"}' in _DIALOG
    for src in (_PASS, _DIALOG):
        assert "new version" not in src.replace("one new version of your resume", "")


def test_closing_re_runs_the_check_and_says_what_changed_once():
    close = _fn(_PASS, "  const closePass = (", "\n  };\n")
    assert "runLintReport(kind, resumeKey)" in close
    assert "toast.success(passOutcomeWords(passOutcome(" in close
    # Never over a newer report (a Check again that finished first).
    assert "Date.parse(cached.created_at) <= Date.parse(after.created_at)" in close
    assert close.index("Date.parse(") < close.index("qc.setQueryData(reportKey, after);")
    assert "useEffect(() => () => closing.current?.(), []);" in _PASS


def test_judged_text_is_upright():
    for src in (_PASS, _DIALOG):
        assert not re.search(r'className="[^"]*\bitalic\b', src), "judged text must be upright"
