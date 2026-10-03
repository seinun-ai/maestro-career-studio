"""Pins for the 2026-08-25 health report page redesign (lane B).

There is no JS test runner in CI for React; behaviour of the pure helpers is
covered by `frontend/lib/health-report.test.ts` (Node). This file pins the
structural properties CI can actually check from source.
"""

from __future__ import annotations

from pathlib import Path
import re

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_PAGE = (_FRONTEND / "components/resume-health/health-report-page.tsx").read_text()
_CARDS = (_FRONTEND / "components/resume-health/finding-cards.tsx").read_text()
_TYPES = (_FRONTEND / "lib/types.ts").read_text()
_ZONES = (_FRONTEND / "lib/health-zones.ts").read_text()
_HELPERS = (_FRONTEND / "lib/health-report.ts").read_text()
_BADGES = (_FRONTEND / "components/resume-health/health-badges.tsx").read_text()
_GALLERY = (_FRONTEND / "components/base-resumes/base-resume-gallery.tsx").read_text()
_JUDGED = (_FRONTEND / "components/resume-health/judged-text.tsx").read_text()
# Task 11 review: the page's runs, its summary band and the Shorten tab have their own files.
_RUNS = (_FRONTEND / "components/resume-health/use-health-runs.ts").read_text()
_BAND = (_FRONTEND / "components/resume-health/summary-band.tsx").read_text()
_SHORTEN = (_FRONTEND / "components/resume-health/shorten-list.tsx").read_text()


def test_the_left_rail_and_its_filters_are_gone():
    # Task 11 (owner decision 8): no two-pane rail, no jump list, no filter chips, no "Add numbers".
    assert "PageMeasure" not in _PAGE
    assert "lg:grid-cols-[18.75rem_minmax(0,1fr)]" not in _PAGE
    assert "lg:sticky" not in _PAGE
    assert "<aside" not in _PAGE
    assert 'aria-label="Report sections"' not in _PAGE
    assert "FILTERS" not in _PAGE and "aria-pressed" not in _PAGE
    assert "addNumbersLabel" not in _PAGE and "BatchAskDialog" not in _PAGE
    assert "filterFindings" not in _HELPERS and "StreamFilter" not in _HELPERS
    assert "Biggest problems first" not in _PAGE


def test_finding_at_rest_is_one_line():
    assert "CollapsedRow" in _CARDS
    assert "DetailsDisclosure" not in _CARDS
    assert "This rating is wrong…" in _CARDS
    assert "FindingOverflow" in _CARDS


def test_not_assessed_gate_is_visible():
    assert "Not checked" in _CARDS
    assert "hasn&apos;t been checked yet" in _CARDS or "hasn't been checked yet" in _CARDS
    assert "not_assessed" in _CARDS


def test_notes_are_a_rule_table():
    assert "subject?: string" in _TYPES
    assert "rule?: string" in _TYPES
    assert "NotesTable" in _CARDS
    assert "groupNotesByRule" in _HELPERS


def test_stale_is_surfaced_and_apply_locks():
    assert "reportIsStale" in _PAGE
    assert "changed since" in _PAGE
    assert "Check again to update it." in _PAGE
    assert "STALE_APPLY_HINT" in _CARDS
    assert "disabled:pointer-events-auto" in _CARDS


def test_apply_sends_content_hash_and_handles_409():
    assert "expected_content_hash" in _SHORTEN and "expectedHash ?? finding.content_hash" in _CARDS
    assert "isContentChangedError" in _CARDS
    assert "content changed since analysis" in _HELPERS


def test_close_the_loop_footer_and_delta():
    assert "applied." in _PAGE
    assert "Check again to update your grade." in _PAGE
    assert "scoreDelta" in _PAGE
    assert "ResolvedFinding" in _PAGE


def test_list_grade_chip():
    assert "HealthListChip" in _GALLERY
    assert "Must fix" in _BADGES
    assert "fatalGateFailed" in _BADGES


def test_close_the_loop_round2_surfaces():
    assert "MetricAskInput" in _CARDS
    assert "DemonstrateSkillDialog" in _CARDS
    assert "ExpandedFindingChrome" in _CARDS
    assert "Shorten" in _SHORTEN
    assert "draftRewrite" in _SHORTEN
    assert "explainScoreDelta" in _RUNS
    assert "Something else" in (
        _FRONTEND / "components/resume-health/metric-ask-input.tsx"
    ).read_text()
    assert "draft-rewrite" in (
        _FRONTEND / "lib/api.ts"
    ).read_text()


def test_level_values_mirrored_in_health_zones():
    assert '"direct": 1.0' in _ZONES or "direct: 1.0" in _ZONES
    assert "analogue: 0.8" in _ZONES
    assert "adjacent: 0.5" in _ZONES
    assert "implied: 0.3" in _ZONES
    assert "unaddressed: 0.0" in _ZONES
    assert "direct: 1.0" in _HELPERS


def test_collapsed_row_cannot_overflow_on_a_long_entry_label():
    """A long entry name used to push the chips and action past the card edge.

    The group header names the rule now, not the entry, so the row shows the whole label
    ("<entry> · bullet N"), wrapping inside the card rather than widening it.
    """
    row = _CARDS[_CARDS.index("function CollapsedRow("): _CARDS.index("export function FindingGroupHeader(")]
    assert "{finding.label} · <LevelChip finding={finding} />" in row
    assert "shortFindingLabel" not in _CARDS and "shortFindingLabel" not in _HELPERS
    assert "break-words" in row
    # The action + overflow menu hold their width instead of being squeezed,
    # and wrap under the chips at 375 rather than push the page sideways.
    assert 'className="ml-auto flex shrink-0 items-center gap-2"' in _CARDS


def test_judged_text_is_never_italic_or_one_line_truncated():
    for name in ("finding-cards", "demonstrate-skill-dialog", "wording-checklist", "word-list-dialog",
                 "judged-text", "summary-band", "shorten-list", "done-tab"):
        src = (_FRONTEND / f"components/resume-health/{name}.tsx").read_text()
        assert not re.search(r'className="[^"]*\bitalic\b', src), "judged text must be upright"
    quote = _JUDGED[_JUDGED.index("export function SourceQuote("):]
    quote = quote[:quote.index("\n}\n")]
    assert "truncate" not in quote
    assert "text-muted-foreground" not in quote
    assert "line-clamp-3" in quote
    assert 'aria-expanded={open}' in quote
    assert 'Show all' in quote
    assert 'text.length >' not in quote
    # "Show all" appears only when the clamp actually cuts the quote (measured).
    assert 'ResizeObserver' in quote and 'scrollHeight > el.clientHeight' in quote
    assert '(open || cut)' in quote
    assert 'border-l-2 border-border pl-3' in quote


def test_status_is_text_points_are_grouped_and_notes_start_closed():
    row = _CARDS[_CARDS.index("function CollapsedRow("): _CARDS.index("export function FindingGroupHeader(")]
    assert "<Badge" not in row
    assert "+{pts} points" not in _CARDS
    header = _CARDS[_CARDS.index("export function FindingGroupHeader("): _CARDS.index("export function FixCard(")]
    assert "groupPoints(findings, nScoreable)" in header
    assert "nScoreable={nScoreable}" in _PAGE
    # Notes are a tab now: the tab is the disclosure, so the table holds no second one.
    notes = _CARDS[_CARDS.index("export function NotesTable("):]
    assert "notesOpen" not in notes
    assert "These don&apos;t change your score." in notes
    assert "export function groupPoints" in _HELPERS
    assert 'label: "Specific, no result"' in _CARDS
    assert 'label: "Partial result"' in _CARDS


def test_per_bullet_metric_contract_and_alternative_are_wired():
    assert "isMetricAsk(finding)" in _CARDS
    assert 'isMetricAsk(finding) ? "number" : "detail"' in _HELPERS
    assert "No number? Answer this instead" in _CARDS
    assert "finding.alt_question" in _CARDS and "finding.measure_target" in _CARDS
    assert "metricAsk && !useAlternative" in _CARDS
    assert "nextGradeLine(body)" in _BAND
    assert 'ask_kind?: "measure" | "detail" | "reword" | null' in _TYPES


# --- Task 8: disputes ("Not right?") ------------------------------------------------------------

def _dispute_box() -> str:
    return (_FRONTEND / "components/resume-health/dispute-box.tsx").read_text()


def test_not_right_is_offered_beside_the_answer_controls_and_never_for_an_override():
    box = _dispute_box()
    assert "Not right?" in box
    assert "Tell us why" in box
    assert "For example: there&apos;s no number for this, it&apos;s confidential, or you misread it." in box
    # Hidden for a rating the user set by hand (the endpoint would 409 behind it).
    can = box[box.index("export function canDispute("):]
    can = can[: can.index("\n}\n")]
    assert 'finding.classification_source !== "override"' in can
    assert "finding.content_hash" in can and "finding.classification_level" in can
    assert "{offered && (" in box
    # The call site, not only the definition: the trigger and the panel both read `offered`.
    assert "const offered = canDispute(finding) && Boolean(onDisputed) && !locked;" in box
    # Both cards carry it; the ⋯ menu keeps its override.
    ask = _CARDS[_CARDS.index("export function AskCard("): _CARDS.index("export function NotesTable(")]
    fix = _CARDS[_CARDS.index("export function FixCard("): _CARDS.index("export function AskCard(")]
    for card in (ask, fix):
        assert "<DisputeBox" in card
        assert "onDisputed={onDisputed}" in card
    assert "controls={" in ask  # Write new wording sits beside "Not right?"
    assert "This rating is wrong…" in _CARDS


def test_dispute_send_is_one_quiet_outline_button_through_the_single_flight_guard():
    box = _dispute_box()
    assert "const sendOnce = useSingleFlight(send.mutate);" in box
    send = box[box.rfind("<Button", 0, box.index("onClick={() => sendOnce()}")): box.index("onClick={() => sendOnce()}")]
    assert 'variant="outline"' in send and 'size="sm"' in send
    assert "focusableWhenDisabled" in send
    assert "disputeBullet(" in box and "expected_content_hash: finding.content_hash" in box


def test_dispute_reply_is_a_status_line_that_takes_focus():
    box = _dispute_box()
    reply = box[box.index("ref={replyRef}"):]
    reply = reply[: reply.index("</p>")]
    assert 'role="status"' in reply
    assert "tabIndex={-1}" in reply
    assert "{result.reply}" in reply
    assert "text-foreground" in reply and "italic" not in reply
    # Focus lands on a NEW reply (in place, or on the card a re-run put in place: `land`), inside the
    # layout effect keyed on the reply; one the box mounted with (a re-expanded card) does not.
    at = box.index("focusIfDropped(replyRef.current)")
    effect = box[box.rfind("useLayoutEffect(() => {", 0, at): box.index("]);", at) + 3]
    assert effect.startswith("useLayoutEffect(() => {")
    assert "if (result && (result !== mountResult || land)) focusIfDropped(replyRef.current);" in effect
    assert "}, [result, mountResult, land]);" in effect
    assert "const [mountResult] = useState(result);" in box
    for card in ("export function FixCard(", "export function AskCard("):
        body = _CARDS[_CARDS.index(card):]
        body = body[: body.index("\n}\n")]
        assert "const fresh = dispute != null && Boolean(disputeFresh);" in body
        assert "useState(fresh);" in body and body.count("setLandOnReply(false);") == 1
        assert "land={landOnReply}" in body
        # The landing is spent once: on the reply's first landing, or on collapse.
        assert "onLanded={endLanding}" in body and "onDisputeSeen?.();" in body
        assert body.count("endLanding();") == 1
    assert "if (result && land) onLanded?.();" in box
    assert _PAGE.count("onDisputeSeen={() => setLastDisputed(null)}") == 2
    assert _PAGE.count("disputeFresh={finding.content_hash != null && finding.content_hash === lastDisputed}") == 2


def test_dispute_box_aria_and_busy_states():
    box = _dispute_box()
    assert "aria-controls={open ? panelId : undefined}" in box
    assert "if (open) setFailure(null);" in box
    assert "disabled={send.isPending || rerunning}" in box
    assert "note.trim().length === 0 || send.isPending || rerunning" in box
    assert ".finally(() => setRerunning(false))" in box


def test_dispute_409s_are_told_apart_and_errors_never_print_raw_text():
    box = _dispute_box()
    assert "disputeFailure(err)" in box
    assert "This bullet changed since the check." in box and "Check again?" in box
    assert "DISPUTE_DETAIL.overridden" in box
    assert 'couldnt("re-read this bullet"' in box
    assert "err.message}" not in box and "{String(err)}" not in box
    fn = _HELPERS[_HELPERS.index("export function disputeFailure("):]
    fn = fn[: fn.index("\n}\n")]
    assert fn.index("isContentChangedError(err)") < fn.index("DISPUTE_DETAIL.overridden")
    assert "err.status === 409" in fn


def test_dispute_detail_mirrors_the_service_sentences():
    from app.routers import resume_lint as lint_router
    from app.services import health_disputes

    assert f'overridden: "{health_disputes.OVERRIDDEN}"' in _HELPERS
    assert f'unreadable: "{health_disputes.UNREADABLE}"' in _HELPERS
    prefix = re.search(r'CONTENT_CHANGED_PREFIX = "([^"]+)"', _HELPERS).group(1)
    assert lint_router.CONTENT_CHANGED.startswith(prefix)


def test_a_dispute_suggestion_uses_the_guarded_apply_and_is_copy_only_for_other_sections():
    box = _dispute_box()
    assert "renderSuggestion(result.suggestion)" in box
    # One suggestion component: the guarded editor, or plain wording when there is no text.
    helper = _CARDS[_CARDS.index("function CardSuggestion("): _CARDS.index("export function SuggestionEditor(")]
    assert helper.index("if (currentText == null)") < helper.index("<SuggestionBlock")
    for card, own in (("export function FixCard(", "finding.suggestion != null && disputeSuggestion == null && renderSuggestion(finding.suggestion)"),
                      ("export function AskCard(", "disputeSuggestion == null && renderSuggestion(suggestion)")):
        body = _CARDS[_CARDS.index(card):]
        body = body[: body.index("\n}\n")]
        assert body.count("const renderSuggestion = (s: string) => (") == 1
        assert "<SuggestionBlock" not in body and body.count("<CardSuggestion") == 1
        assert "renderSuggestion={renderSuggestion}" in body
        # A dispute's suggestion is newer: the card's own gives way to it.
        assert "const disputeSuggestion = dispute?.suggestion ?? null;" in body and own in body
        assert "onApplied={onApplied}" in body
    block = _CARDS[_CARDS.index("function SuggestionBlock("): _CARDS.index("function CardSuggestion(")]
    assert block.index('finding.location.section.startsWith("extra:")') < block.index("<SuggestionCopyOnly")
    assert block.index("<SuggestionCopyOnly") < block.index("<SuggestionEditor")


def test_a_dispute_that_moves_the_rating_re_runs_the_report():
    assert "export function disputeChangedRating" in _HELPERS
    after = _RUNS[_RUNS.index("const afterDispute = async ("):]
    after = after[: after.index("\n  };\n")]
    assert "setDisputes(" in after
    assert "if (!disputeChangedRating(result)) return;" in after
    assert after.index("const fresh = await runLatest();") < after.index("if (!fresh) return;") < after.index("adoptReport(")
    assert after.index("adoptReport(") < after.index("await qc.invalidateQueries(")
    # Only this dispute's own re-run marks the bullet lifted (its Fixed entry carries the reply).
    lift = "if (!hasOpenRating(fresh.findings, hash)) setLifted((l) => new Set(l).add(hash));"
    assert after.index("adoptReport(") < after.index(lift) < after.index("await qc.invalidateQueries(")
    # Only a dispute whose re-run may replace its card is "fresh".
    assert after.index("if (!disputeChangedRating(result)) return;") < after.index("setLastDisputed(hash);")
    # An Apply never drops a dispute: that unmounted the applied editor (focus to <body>) and put the
    # check's old suggestion back against changed text. Disputes are only ever added.
    applied = _RUNS[_RUNS.index("const invalidateAfterApply = () => {"):]
    applied = applied[: applied.index("\n  };\n")]
    assert "setDisputes" not in applied
    # The only other change is Reopen's, which drops that bullet's reply with the dispute.
    assert _RUNS.count("setDisputes(") == 2 and "setDisputes(" not in _PAGE
    reopen = _RUNS[_RUNS.index("const reopen = async ("):]
    assert "setDisputes((d) => Object.fromEntries(Object.entries(d).filter(([key]) => key !== hash)));" in reopen[: reopen.index("\n  };\n")]
    assert _PAGE.count("onDisputed={afterDispute}") == 2
    assert _PAGE.count("dispute={finding.content_hash ? disputes[finding.content_hash] : undefined}") == 2


def test_a_dispute_that_resolves_a_bullet_keeps_its_reply_and_focus():
    # The card leaves with the bullet; its reply (and any suggestion, copy-only) moves onto the
    # "Fixed" entry, which takes focus. Only a bullet this dispute's re-run lifted gets one.
    assert "dispute={liftedDispute(finding, lifted, disputes)}" in _PAGE
    fn = _HELPERS[_HELPERS.index("export function liftedDispute<"):]
    fn = fn[: fn.index("\n}\n")]
    assert "lifted.has(hash)" in fn
    entry = _CARDS[_CARDS.index("export function ResolvedFinding("):]
    assert 'role="status"' in entry and "{dispute.reply}" in entry
    assert "if (dispute) focusIfDropped(ref.current);" in entry
    assert "data-resolved-hash=" in entry and "tabIndex={dispute ? -1 : undefined}" in entry
    assert "<SuggestionCopyOnly currentText={currentText} suggestion={dispute.suggestion} />" in entry
    assert "SuggestionEditor" not in entry and "SuggestionBlock" not in entry
    # Whichever commit comes last: the leaving card hands focus to the entry.
    box = _dispute_box()
    handoff = box[box.index("const reply = replyRef.current;"):]
    handoff = handoff[: handoff.index("}, [result, hash]);")]
    assert "document.activeElement !== reply" in handoff
    assert "queueMicrotask(" in handoff and '[data-resolved-hash="${hash}"]' in handoff


def test_a_changed_question_is_not_a_fixed_bullet():
    # adoptReport (every re-run: Check again, an override, a dispute) lists as fixed only a
    # location nothing in the new report still asks or fixes; the finding id is not the test.
    adopt = _RUNS[_RUNS.index("const adoptReport = ("):]
    adopt = adopt[: adopt.index("\n  };\n")]
    assert "const fresh = resolvedFindings(priorFindings.current, result.findings);" in adopt
    assert "nextIds" not in adopt
    fn = _HELPERS[_HELPERS.index("export function resolvedFindings<"):]
    fn = fn[: fn.index("\n}\n")]
    # Rated text: open while any ask or fix rates the same hash. No rated text (gaps, C2): the id.
    assert "!hasOpenRating(next, f.content_hash!) && !rewrittenOpen.has(where(f))" in fn
    assert ": !nextIds.has(f.id)" in fn
    # A still-flagged rewrite: new text (a hash the prior report never had) open at the same place.
    assert "!priorHashes.has(f.content_hash)" in fn
    assert "question" not in fn
    # C2 carries the summary's hash but rates nothing: it must not hold the summary's ask open.
    assert "const ratesText = (f: Rated) => Boolean(f.content_hash && f.classification_level);" in _HELPERS
    assert _RUNS.count("adoptReport(result, true);") + _RUNS.count("adoptReport(fresh, true);") == 3


# --- Task 10b: the Wording checklist and its word list ------------------------------------------

def _wording() -> str:
    return (_FRONTEND / "components/resume-health/wording-checklist.tsx").read_text()


def _word_list_dialog() -> str:
    return (_FRONTEND / "components/resume-health/word-list-dialog.tsx").read_text()


def _fn(src: str, head: str) -> str:
    body = src[src.index(head):]
    return body[: body.index("\n}\n")]


def _row() -> str:
    return _fn(_wording(), "function WordingRow(")


def _checklist() -> str:
    return _fn(_wording(), "export function WordingChecklist(")


def test_wording_notes_are_one_group_by_the_language_prefix():
    assert 'rule.startsWith("language.")' in _fn(_HELPERS, "export function isWordingRule(")
    split = _fn(_HELPERS, "export function splitWordingNotes<")
    assert "isWordingRule(note.rule)" in split
    notes = _fn(_CARDS, "export function NotesTable(")
    # The rule table never sees a wording note; the Wording group gets every one.
    assert "const { wording, other } = splitWordingNotes(notes);" in notes
    assert "const allGroups = groupNotesByRule(other);" in notes
    assert "notes={wording}" in notes
    assert "onWordingChanged={reanalyzeReport}" in _PAGE


def test_the_wording_group_and_its_word_list_are_there_with_no_hits():
    # Planner decision: Edit word list must be reachable with zero wording hits, so the Notes
    # disclosure renders with any report and the Wording group renders in it unconditionally.
    notes = _fn(_CARDS, "export function NotesTable(")
    # Unconditional: the element opens its own line in the table, and no count guards it.
    assert "*/}\n      <WordingChecklist\n        notes={wording}" in notes
    assert "wording.length" not in notes
    # The Notes tab renders it with every report (its panel is kept mounted).
    notes_tab = _PAGE[_PAGE.index('<TabsContent value="notes"'):]
    notes_tab = notes_tab[: notes_tab.index("</TabsContent>")]
    assert "<NotesTable" in notes_tab and "notes={tabs.notes}" in notes_tab
    group = _checklist()
    assert "notes.length === 0 ?" in group and "No wording issues." in group
    header = group[: group.index("notes.length === 0 ?")]
    assert "Edit word list" in header and "These never change your score." in header


def test_the_wording_actions_are_text_style():
    # One filled button per view: the header's link and every row action are text-style.
    src = _wording()
    tags = re.findall(r"<Button\b[\s\S]*?>(?=\s*[{A-Z])", src)
    assert len(tags) == 3
    for tag in tags:
        assert 'variant="link"' in tag, tag


def test_apply_and_remove_send_the_guarded_suggestion_with_its_hash():
    op = _fn(_HELPERS, "export function wordingEditOp(")
    assert "note.suggestion == null" in op and 'startsWith("extra:")' in op
    assert "return bulletEditOp(note.location, note.suggestion, note.content_hash);" in op
    edit = _fn(_HELPERS, "export function bulletEditOp(")
    assert "hash != null ? { expected_content_hash: hash } : {}" in edit
    assert edit.count("...guard") == 2
    # SuggestionEditor writes through the same op.
    assert "bulletEditOp(finding.location, draft, expectedHash ?? finding.content_hash)" in _CARDS
    row = _row()
    assert "const op = data ? wordingEditOp(note) : null;" in row
    assert "mutationFn: (edit: LintEditOp) => applyResumeEdits(kind, resumeKey, [edit])," in row
    assert "const applyOnce = useSingleFlight(apply.mutate);" in row
    assert "onClick={() => applyOnce(op)}" in row
    # Apply leaves with its button: "Applied" (or "Removed") takes the focus once the write lands.
    on_success = row[row.index("onSuccess: (result) => {"): row.index("onError:", row.index("onSuccess: (result) => {"))]
    assert "focusNext(appliedRef);" in on_success and "onApplied();" in on_success
    assert '{slip ? "Applied" : "Removed"}' in row


def test_row_actions_have_unique_names():
    row = _row()
    assert 'aria-label={slip ? `Apply fix to "${word}"` : `Remove "${word}"`}' in row
    assert 'aria-label={`Ignore "${word}"`}' in row


def test_a_null_or_other_section_suggestion_is_copy_only():
    row = _row()
    assert "const fix = slip ? slipFix(note) : null;" in row
    assert "const otherSection = note.location.section.startsWith(\"extra:\");" in row
    assert "const copyOnly = otherSection && note.suggestion != null && currentText != null;" in row
    # The copy-only diff is gated on the Other section; with it, the slip's own diff gives way.
    gate = row[row.index("{data && !op && !applied &&"):]
    assert gate.index("copyOnly &&") < gate.index("<SuggestionCopyOnly")
    assert "{fix != null && !copyOnly ? (" in row
    assert "Can&apos;t apply this fix here." in row and "Can&apos;t remove it here. Edit the {thing} in the resume." in row
    # Nothing to act on (no action, no "Can't apply") until the resume text has loaded.
    assert row.count("{data && (") == 1 and "{data && !op && !applied &&" in row
    assert 'const thing = note.location.section === "summary" ? "summary" : "bullet";' in row


def test_a_changed_bullet_shows_on_its_row():
    row = _row()
    assert "isContentChangedError(err)" in row
    assert 'role="alert"' in row
    assert "This {thing} changed since the check." in row and "Check again?" in row
    assert "err.message}" not in row
    # A re-run on changed text keeps the note id: the row is keyed by the text's hash as well, so
    # its "changed since the check" (and "Applied") never outlive the text they were about.
    assert 'key={`${note.id}:${note.content_hash ?? ""}`}' in _wording()


def test_ignore_adds_the_subject_to_never_flag_and_re_runs():
    src = _wording()
    assert "const ignoreOnce = useSingleFlight(ignore.mutate);" in src
    group = _checklist()
    ignore = group[group.index("const ignoreWord = (subject: string) =>"):]
    ignore = ignore[: ignore.index("\n    });\n")]
    assert "exclusive(async () => {" in ignore
    assert ignore.index("await getWording()") < ignore.index("await putWording(withIgnored(")
    assert ignore.index("await putWording(") < ignore.index("await rerun()")
    assert "await onWordingChanged();" in group[group.index("const rerun = async () => {"):]
    assert "onIgnore={ignoreWord}" in group
    fn = _fn(_HELPERS, "export function withIgnored(")
    assert "normalizeWord(subject)" in fn and "...wording.ignored" in fn
    api = (_FRONTEND / "lib/api.ts").read_text()
    assert 'apiFetch<WordingRead>("/api/resume-lint/wording", {' in api
    assert 'method: "PUT"' in _fn(api, "export function putWording(")


def test_one_word_list_change_at_a_time():
    # Two Ignores each PUT the lists they read: the later one dropped the earlier word. The group
    # runs one GET -> PUT -> re-run at a time and disables every Ignore and the word list's Save.
    group = _checklist()
    ex = group[group.index("const exclusive = async ("):]
    ex = ex[: ex.index("\n  };\n")]
    assert "if (changing.current) return;" in ex
    assert ex.index("changing.current = true;") < ex.index("await change();")
    assert "finally {" in ex and "changing.current = false;" in ex and "setWordingBusy(false);" in ex
    assert "wordingBusy={wordingBusy}" in group and "busy={wordingBusy}" in group
    assert "onSaved={() => void exclusive(() => rerun())}" in group
    assert "disabled={busy || wordingBusy}" in _row()
    form = _fn(_word_list_dialog(), "function WordListForm(")
    assert "const busy = save.isPending || groupBusy;" in form
    save = form[form.rindex("<Button", 0, form.index("onClick={submit}")): form.index("onClick={submit}")]
    assert "disabled={busy}" in save


def test_an_older_report_never_replaces_a_newer_one():
    latest = _RUNS[_RUNS.index("const runLatest = async ("):]
    latest = latest[: latest.index("\n  };\n")]
    assert latest.index("const seq = ++runSeq.current;") < latest.index("runLintReport(kind, resumeKey)")
    assert latest.index("runLintReport(") < latest.index("if (seq < adoptedSeq.current) return null;")
    assert latest.index("return null;") < latest.index("adoptedSeq.current = seq;")
    # Every re-run goes through it, and adopts only what it returned.
    assert _RUNS.count("runLintReport(") == 1 and "runLintReport" not in _PAGE
    assert _RUNS.count("await runLatest();") == 3 and "mutationFn: runLatest," in _RUNS
    assert _RUNS.count("if (!result) return;") == 3 and _RUNS.count("if (!fresh) return;") == 1


def test_the_word_list_dialog_has_three_lists_and_reset():
    src = _word_list_dialog()
    for title in ('title="Clichés"', 'title="Filler words"', 'title="Never flag"'):
        assert title in src
    assert "Reset to defaults" in src
    assert "wording.defaults.cliche" in src and "wording.defaults.filler" in src
    assert "aria-label={`Remove ${word}`}" in src
    assert re.search(r"onClick=\{add\}>\s*Add\s*</Button>", src)
    assert 'if (e.key === "Enter")' in src
    assert "addWord(" in src and 'role="alert"' in src
    assert "const saveOnce = useSingleFlight(save.mutate);" in src
    assert "mutationFn: (body: WordingBody) => putWording(body)," in src
    assert "Cancel" in src
    # Save closes, then the checklist re-runs; the close returns to the opener or what survived.
    assert src.index("onClose();") < src.index("onSaved();")
    assert "const returnToOpener = useOpenerReturn(open);" in src
    assert "finalFocus={returnToOpener}" in src


def test_save_commits_a_typed_word_or_stops_with_its_error():
    form = _fn(_word_list_dialog(), "function WordListForm(")
    submit = form[form.index("const submit = () => {"):]
    submit = submit[: submit.index("\n  };\n")]
    assert "withDraft(lists[key], drafts[key])" in submit
    assert submit.index("if (LISTS.some((key) => found[key])) return setErrors(found);") < submit.index("saveOnce(body);")
    assert "onClick={submit}" in form
    assert "return normalizeWord(draft) ? addWord(list, draft) : { list };" in _HELPERS


def test_the_form_copies_the_lists_only_after_the_refetch_on_open():
    src = _word_list_dialog()
    assert "const ready = wording.data != null && !wording.isFetching;" in src
    assert "{ready ? (" in src and "<WordListForm wording={wording.data!}" in src


def test_word_list_limits_mirror_the_backend():
    from app.services import health_wording

    assert f"export const WORD_MAX_CHARS = {health_wording.MAX_CHARS};" in _HELPERS
    assert f"export const WORD_LIST_MAX = {health_wording.MAX_ENTRIES};" in _HELPERS
    norm = _fn(_HELPERS, "export function normalizeWord(")
    assert ".toLowerCase()" in norm and ".split(/\\s+/)" in norm


def test_slip_fix_reads_the_backend_issue_sentence():
    backend = (_FRONTEND.parent / "backend/app/services/resume_lint.py").read_text()
    assert "f\"'{span}' looks like a slip: '{fix}'.\"" in backend
    fn = _fn(_HELPERS, "export function slipFix(")
    assert "`'${note.subject}' looks like a slip: '`" in fn


def test_wording_rows_hand_focus_on_when_they_leave():
    src = _wording()
    group = _checklist()
    assert '<div tabIndex={-1} className="rounded-corner-md border outline-none">' in group
    leave = _fn(src, "function useSuccessorOnLeave(")
    assert "useLayoutEffect(" in leave and "row.contains(document.activeElement)" in leave
    assert 'focusSuccessor(row, "[data-wording-action]")' in leave
    assert "queueMicrotask(" in leave and "focusIfDropped(" in leave
    assert src.count("focusableWhenDisabled") >= 2


def test_wording_rows_show_the_bullet_upright_and_in_full():
    row = _row()
    assert "<SourceQuote text={currentText} clamp />" in row
    assert "export function SourceQuote(" in _JUDGED
    assert "{note.label}" in row


def test_judged_text_has_one_home_and_no_import_cycle():
    for name in ("DiffText", "SuggestionCopyOnly", "SourceQuote"):
        assert f"export function {name}(" in _JUDGED
        assert f"function {name}(" not in _CARDS
    assert "@/components/resume-health/finding-cards" not in _wording()
    assert "@/components/resume-health/judged-text" in _wording()


def test_opening_not_right_puts_focus_in_tell_us_why():
    # Browser check: opening the box left focus on the page's <main>, so typing went nowhere.
    box = _dispute_box()
    assert "const noteRef = useRef<HTMLTextAreaElement>(null);" in box
    effect = box[box.rfind("useEffect(() => {", 0, box.index("noteRef.current?.focus()")):]
    effect = effect[: effect.index("]);") + 3]
    assert "if (open) noteRef.current?.focus();" in effect and effect.endswith("}, [open]);")
    area = box[box.index("<Textarea"): box.index("/>", box.index("<Textarea"))]
    assert "ref={noteRef}" in area and "id={noteId}" in area


def test_a_cliche_row_says_to_rewrite_it_not_that_it_cannot():
    # Clichés never get a suggestion (by design): the row shows the note's own advice. Filler and
    # slips whose suggestion the guards refused keep the can't-apply wording.
    row = _row()
    gate = row[row.index("{data && !op && !applied &&"):]
    cliche = gate.index('note.rule === "language.cliche" ? (')
    assert gate.index("<SuggestionCopyOnly") < cliche < gate.index("Can&apos;t apply this fix here.")
    assert "{note.how}</p>" in gate[cliche: gate.index("Can&apos;t apply this fix here.")]


# --- Task 11: summary band, action tabs, no left rail --------------------------------------------

_ROUTE = (_FRONTEND / "app/base-resumes/[slug]/health/page.tsx").read_text()
_DONE = (_FRONTEND / "components/resume-health/done-tab.tsx").read_text()
_BOX = (_FRONTEND / "components/resume-health/dispute-box.tsx").read_text()

# Every component the report page renders its controls from (a dialog is its own view).
_ON_PAGE = {
    "health-report-page": _PAGE, "summary-band": _BAND, "finding-cards": _CARDS, "done-tab": _DONE,
    "shorten-list": _SHORTEN, "dispute-box": _BOX,
    "wording-checklist": (_FRONTEND / "components/resume-health/wording-checklist.tsx").read_text(),
}


def test_the_summary_band_holds_the_grade_the_next_band_and_the_one_filled_button():
    assert "<SummaryBand" in _PAGE and "data-summary-band" in _BAND
    assert "Too little to grade" in _BAND and "GRADE_STYLES[body.grade]" in _BAND
    assert "TIER_LABELS[body.tier]" in _BAND and "{body.score}/100" in _BAND
    # The bar to the next band, with its words.
    assert "const progress = !insufficient ? nextGradeProgress(body) : null;" in _BAND
    assert "progress != null &&" in _BAND and "nextGradeLine(body)" in _BAND
    assert "scoreCompositionLine(body.score, body.score_breakdown, gates)" in _BAND
    # The stale banner, as before, in the band (the page passes it: it hands focus to Check again).
    band_call = _PAGE[_PAGE.index("<SummaryBand"): _PAGE.index("</SummaryBand>")]
    assert "Your resume changed since this check. Check again to update it." in band_call
    assert "marked={disputeRows.length}" in band_call
    assert "{marked} marked not right" in _BAND and "marked > 0 &&" in _BAND
    # The page's one filled control opens the question pass, hidden at zero asks, as a LINK styled
    # as the button (SYSTEM.md §11 item 29), carrying the tab to come back to.
    assert "askCount > 0 &&" in _BAND
    assert '<Link href={startHref} className={cn(buttonVariants(), "ml-auto")}>' in _BAND
    assert "Start the questions ({askCount})" in _BAND
    assert "startHref={`${questionsHref}?from=${tab}`}" in band_call
    assert 'questionsHref={`/base-resumes/${slug}/health/questions`}' in _ROUTE


def test_one_filled_button_per_view():
    # Every Button the page renders names a quieter variant; the only filled control is the band's
    # Start link. The first check's Check health is filled only while there is no report (no band).
    for name, src in _ON_PAGE.items():
        for tag in re.findall(r"<Button\b[^>]*?>", src, flags=re.S):
            assert "variant=" in tag, (name, tag)
    assert "nativeButton" not in _BAND
    assert sum(src.count("buttonVariants()") for src in _ON_PAGE.values()) == 1
    assert 'variant={body ? "outline" : "default"}' in _PAGE
    for label in ('{draft.isPending ? "Writing…" : "Write new wording"}',
                  '{apply.isPending ? "Applying…" : "Apply suggestion"}',
                  '{markOk.isPending ? "Saving…" : "Mark as OK"}'):
        at = _CARDS.index(label)
        assert 'variant="tonal"' in _CARDS[_CARDS.rindex("<Button", 0, at): at], label


def test_no_numbers_anywhere_is_a_highlighted_callout_not_a_note():
    assert "noNumbers &&" in _BAND
    assert "bg-warning-container" in _BAND and "text-on-warning-container" in _BAND
    for part in ("{noNumbers.label}", "{noNumbers.issue}", "{noNumbers.why}", "{noNumbers.how}"):
        assert part in _BAND
    # It links to the Needs a number tab only when that tab has something in it.
    assert "numberCount > 0 &&" in _BAND and "numberCount={tabs.number.length}" in _PAGE
    assert 'onOpenNumberTab={() => openTab("number")}' in _PAGE
    open_tab = _PAGE[_PAGE.index("const openTab = (id: HealthTab) => {"):]
    open_tab = open_tab[: open_tab.index("\n  };\n")]
    assert open_tab.index("flushSync(() => selectTab(id));") < open_tab.index("?.focus();")
    assert 'export const NO_NUMBERS_RULE = "evidence.no_numbers";' in _HELPERS
    assert "f.rule === NO_NUMBERS_RULE" in _PAGE
    backend = (_FRONTEND.parent / "backend/app/services/resume_lint.py").read_text()
    assert 'rule="evidence.no_numbers"' in backend


def test_findings_are_grouped_by_action_in_six_tabs():
    for label in ('"Needs a number"', '"Needs detail"', '"Reword"', '"Shorten"', '"Notes"', '"Done"'):
        assert f"label: {label}" in _HELPERS
    fn = _fn(_HELPERS, "export function actionTabOf(")
    assert 'if (finding.type === "ask") return isMetricAsk(finding) ? "number" : "detail";' in fn
    assert 'if (finding.type === "fix") return "reword";' in fn
    assert "if (finding.rule === NO_NUMBERS_RULE) return null;" in fn
    assert 'return finding.rule === "bullet.too_long" ? "shorten" : "notes";' in fn
    # Gates stay above the tabs; the tabs are the shared primitive, every panel kept mounted.
    assert _PAGE.index("<GateBanner") < _PAGE.index("<Tabs ")
    assert "@/components/ui/tabs" in _PAGE
    assert _PAGE.count("<TabsContent") == _PAGE.count("keepMounted") == 4  # 3 card tabs mapped, then 3
    assert "CARD_TABS.map((id) => (" in _PAGE
    for tab in ("shorten", "notes", "done"):
        assert f'<TabsContent value="{tab}" keepMounted data-health-tab="{tab}"' in _PAGE
    # Plain counts on the tabs, said in one phrase in the name.
    assert '<span className="tabular-nums text-muted-foreground">{countOf(t.id)}</span>' in _PAGE
    assert "aria-label={`${t.label} ${countOf(t.id)}`}" in _PAGE


def test_the_tab_comes_from_the_url_and_defaults_to_the_largest_gain():
    assert "use(searchParams);" in _ROUTE and "searchParams: Promise<" in _ROUTE
    assert 'parseHealthTab(useSearchParams().get("tab"))' in _PAGE
    assert "window.history.replaceState(null, \"\", `${window.location.pathname}?tab=${next}`);" in _PAGE
    assert "defaultHealthTab(" in _PAGE
    fn = _fn(_HELPERS, "export function defaultHealthTab<")
    assert "gain ?? 0" in _HELPERS and "> best" in fn


def test_a_dispute_that_moves_its_bullet_opens_the_new_tab_with_the_report():
    # "No number exists" turns a number question into a detail question: the new card must mount in
    # the OPEN panel, or it mounts inert and focus drops to <body>.
    assert "onDisputed!(reply, finding.location)" in _BOX
    after = _RUNS[_RUNS.index("const afterDispute = async ("):]
    after = after[: after.index("\n  };\n")]
    move = "const moved = disputeTabMove(priorFindings.current, fresh.findings, hash, where);"
    assert after.index("if (!fresh) return;") < after.index(move)
    assert after.index(move) < after.index("if (moved) onDisputeMovesTab(moved, fresh.id);") < after.index("adoptReport(fresh, true);")
    assert "onDisputeMovesTab: moveTabWith," in _PAGE
    # The page opens that tab in the render the re-run's report arrives in (react-query hands it over
    # a tick after a state update, so a plain tab switch rendered first and the panel took focus).
    assert "if (tabMove && report.data?.id === tabMove.reportId) {\n    setTabMove(null);\n    setPicked(tabMove.tab);\n  }" in _PAGE
    fn = _fn(_HELPERS, "export function disputeTabMove<")
    assert "samePlace(f.location, where)" in fn and "f.content_hash === hash" in fn
    assert "return from && to && from !== to ? to : null;" in fn


def test_every_dispute_refreshes_the_done_tab():
    # A dispute that keeps its rating never re-runs; its Done row and the band's count still update.
    after = _RUNS[_RUNS.index("const afterDispute = async ("):]
    after = after[: after.index("\n  };\n")]
    assert after.index("void qc.invalidateQueries({ queryKey: disputesKey });") < after.index(
        "if (!disputeChangedRating(result)) return;")
    assert 'const disputesKey = ["resume-lint", kind, resumeKey, "disputes"];' in _RUNS
    assert "queryKey: disputesKey," in _RUNS


def test_fixed_this_session_is_the_page_session():
    adopt = _RUNS[_RUNS.index("const adoptReport = ("):]
    adopt = adopt[: adopt.index("\n  };\n")]
    assert "setResolved((kept) => mergeResolved(kept, fresh, result.findings));" in adopt
    fn = _fn(_HELPERS, "export function mergeResolved<")
    assert "for (const f of [...kept, ...fresh]) byId.set(f.id, f);" in fn
    assert ".filter((f) => !reopened(f))" in fn


def test_a_tab_groups_its_rows_by_rule_and_states_each_rule_once():
    assert "ruleGroups(" in _PAGE
    header = _CARDS[_CARDS.index("export function FindingGroupHeader("): _CARDS.index("export function FixCard(")]
    assert header.count("groupPoints(findings, nScoreable)") == 1
    assert "coaching.why" in header and "coaching.how" in header
    # No ids built from sentences.
    assert "id=" not in header and "group-" not in _PAGE
    assert "renderFinding(finding, Boolean(sharedCoaching(group.findings)))" in _PAGE
    # A row: the entry and bullet, the clamped quote, the bullet's own question, one text-style action, ⋯.
    row = _CARDS[_CARDS.index("function CollapsedRow("): _CARDS.index("export function FindingGroupHeader(")]
    assert "<SourceQuote text={quote} clamp />" in row
    assert "{finding.question}" in row
    assert 'variant="link"' in row and 'variant="outline"' not in row
    assert "aria-label={`${actionLabel}: ${finding.label}`}" in row
    assert "{overflow}" in row


def test_shorten_rows_keep_focus():
    shorten = _fn(_SHORTEN, "export function ShortenList(")
    assert "draftRewrite(" in shorten and 'objective: "condense"' in shorten
    assert "<SourceQuote" in shorten and "{note.label}" in shorten
    button = shorten[shorten.index("<Button"): shorten.index("</Button>")]
    assert 'variant="link"' in button and "focusableWhenDisabled" in button
    assert "aria-label={`Shorten: ${note.label}`}" in button
    assert "onClick={() => condenseOnce(note)}" in button
    # Apply never unmounts its editor: the draft stays, so "Applied" takes the focus; the row loses
    # only its Shorten.
    assert shorten.count("setDrafts(") == 1 and "onSuccess: (result) => setDrafts(" in shorten
    assert "setApplied((a) => new Set(a).add(note.id));" in shorten
    assert "{!applied.has(note.id) && (" in shorten
    assert "function ShortenList(" not in _CARDS and "draftRewrite" not in _CARDS
    notes = _fn(_CARDS, "export function NotesTable(")
    assert "condense" not in notes and "bullet.too_long" not in notes


def test_unscored_skills_are_a_table_with_a_show_it_action():
    notes = _fn(_CARDS, "export function NotesTable(")
    assert "<th" in notes and ">Skill</th>" in notes and ">Listed in</th>" in notes
    assert "skillGroupOf(data, subject)" in notes
    assert "Show it in a bullet" in notes and "data-skill={subject}" in notes
    assert "rounded-full border px-2" not in notes  # the old chips
    assert "export function skillGroupOf(" in _HELPERS


def test_the_done_tab_lists_fixes_disputes_and_corrected_ratings():
    done = _DONE
    assert "Fixed this session" in done and "<ResolvedFinding" in done
    assert "Marked not right" in done and "{d.note}" in done and "{d.reply}" in done
    assert "Corrected ratings" in done
    assert 'action="Reopen"' in done and 'action="Back to automatic"' in done
    assert "onAct={() => onReopen(d.content_hash)}" in done
    assert "onAct={() => onBackToAutomatic(f.content_hash!)}" in done
    # Reopen deletes the dispute, then re-runs; Back to automatic clears the override, then re-runs.
    reopen = _RUNS[_RUNS.index("const reopen = async ("):]
    reopen = reopen[: reopen.index("\n  };\n")]
    assert reopen.index("await reopenDispute(hash);") < reopen.index("await reanalyzeReport();")
    assert "overrideClassification(hash, null, \"\")" in _PAGE
    assert 'f.classification_source === "override"' in _PAGE
    assert "getDisputes(kind, resumeKey)" in _RUNS
    # Only the Fixed entry a dispute lifted carries the reply (and data-resolved-hash, the focus
    # target): it renders in the tab it came from, while Done lists every fix without it.
    assert "dispute={liftedDispute(finding, lifted, disputes)}" in _PAGE
    assert "dispute=" not in done[done.index("<ResolvedFinding"): done.index("/>", done.index("<ResolvedFinding"))]
    # A row that leaves (reopened, back to automatic) hands focus to the next row's action.
    assert 'focusSuccessor(row, "[data-done-action]")' in done


def test_the_header_has_the_stamp_and_a_quiet_check_again():
    assert "checkedWords(formatTimeAgo(body.created_at), body.resume_version_number)" in _PAGE
    assert "`Checked ${ago} · Version ${version}`" in _HELPERS
    head = _PAGE[_PAGE.index("<PageHeader"): _PAGE.index("{reportFailed ? (")]
    assert "<IconButton" in head and "ref={checkRef}" in head
    assert '"Check again"' in head and "RefreshCw" in head
    assert "onClick={() => analyzeOnce()}" in head and "focusableWhenDisabled" in head


def test_re_runs_run_one_at_a_time():
    # Overlapping runs let the SERVER's latest report be the older one (it orders by created_at, set
    # when a run finishes). Each re-run starts only after the previous one settled.
    latest = _RUNS[_RUNS.index("const runLatest = async ("):]
    latest = latest[: latest.index("\n  };\n")]
    assert "const turn = runQueue.current.then(() => runLintReport(kind, resumeKey));" in latest
    assert "runQueue.current = turn.catch(() => undefined);" in latest
    assert latest.index("runQueue.current = turn") < latest.index("const result = await turn;")
    assert "const runQueue = useRef<Promise<unknown>>(Promise.resolve());" in _RUNS


def test_grade_floors_mirror_the_backend_bands():
    from app.services import health_score

    floors = sorted(floor for floor, _ in health_score.GRADE_BANDS)
    assert f"export const GRADE_FLOORS = [{', '.join(map(str, floors))}] as const;" in _HELPERS
