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


def test_two_pane_not_page_measure():
    assert "PageMeasure" not in _PAGE
    assert "lg:grid-cols-[18.75rem_minmax(0,1fr)]" in _PAGE
    assert "lg:sticky" in _PAGE
    assert "Too little to grade" in _PAGE
    assert "scoreCompositionLine" in _PAGE


def test_groups_by_location_and_renames_heading():
    assert "groupFindings" in _PAGE
    assert "Biggest problems first" in _PAGE
    assert "What it" not in _PAGE  # old "What it's costing you, in order"


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
    assert "expected_content_hash" in _CARDS
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
    assert "addNumbersLabel(metricAsks.length)" in _PAGE
    assert "BatchAskDialog" in _PAGE
    assert "MetricAskInput" in _CARDS
    assert "DemonstrateSkillDialog" in _CARDS
    assert "ExpandedFindingChrome" in _CARDS
    assert "Shorten" in _CARDS
    assert "draftRewrite" in _CARDS
    assert "explainScoreDelta" in _PAGE
    # (The T10 pin here asserted 'This bullet is ${lowered}', which encoded the
    # broken conjugation — see test_hoist_blurb_does_not_conjugate_backend_copy.)
    assert "hoistBlurb" in _HELPERS
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

    Two guards, both required: the badge shows only the label tail (the group
    header already names the entry) AND it is width-capped + truncating, so a
    pathological label still cannot grow the row.
    """
    assert "shortFindingLabel(finding.label)" in _CARDS
    assert "break-words" in _CARDS
    # The action + overflow menu hold their width instead of being squeezed,
    # and wrap under the chips at 375 rather than push the page sideways.
    assert 'className="ml-auto flex shrink-0 items-center gap-2"' in _CARDS


def test_hoist_blurb_does_not_conjugate_backend_copy():
    helpers = (_FRONTEND / "lib/health-report.ts").read_text()
    # The count is introduced with a colon; no copula is inserted before the
    # backend's own sentence ("Has a scale metric…", "A reader can't tell…").
    assert "bullets here: " in helpers
    assert "items here are ${" not in helpers  # the old copula template


def test_judged_text_is_never_italic_or_one_line_truncated():
    for name in ("finding-cards", "batch-ask-dialog", "demonstrate-skill-dialog"):
        src = (_FRONTEND / f"components/resume-health/{name}.tsx").read_text()
        assert not re.search(r'className="[^"]*\bitalic\b', src), "judged text must be upright"
    quote = _CARDS[_CARDS.index("function SourceQuote"):]
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
    notes = _CARDS[_CARDS.index("export function NotesTable("):]
    assert "[notesOpen, setNotesOpen] = useState(false)" in notes
    assert "aria-expanded={notesOpen}" in notes
    assert "hidden={!notesOpen}" in notes
    assert "export function groupPoints" in _HELPERS
    assert 'label: "Specific, no result"' in _CARDS
    assert 'label: "Partial result"' in _CARDS


def test_per_bullet_metric_contract_and_alternative_are_wired():
    assert "isMetricAsk(finding)" in _CARDS
    assert "isMetricAsk(f)" in _PAGE
    assert "No number? Answer this instead" in _CARDS
    assert "finding.alt_question" in _CARDS and "finding.measure_target" in _CARDS
    assert "metricAsk && !useAlternative" in _CARDS
    assert "nextGradeLine(body)" in _PAGE
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
    # Focus lands on the reply in place and after the re-run that replaces the card.
    assert "focusIfDropped(replyRef.current)" in box


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
    for card in ("export function FixCard(", "export function AskCard("):
        body = _CARDS[_CARDS.index(card):]
        body = body[: body.index("\n}\n")]
        assert "renderSuggestion={(s) => (" in body
        assert "<SuggestionBlock" in body[body.index("renderSuggestion={(s) => ("):]
    block = _CARDS[_CARDS.index("function SuggestionBlock("): _CARDS.index("function SuggestionCopyOnly(")]
    assert block.index('finding.location.section.startsWith("extra:")') < block.index("<SuggestionCopyOnly")
    assert block.index("<SuggestionCopyOnly") < block.index("<SuggestionEditor")


def test_a_dispute_that_moves_the_rating_re_runs_the_report():
    assert "export function disputeChangedRating" in _HELPERS
    after = _PAGE[_PAGE.index("const afterDispute = async ("):]
    after = after[: after.index("\n  };\n")]
    assert "setDisputes(" in after
    assert "if (!disputeChangedRating(result)) return;" in after
    assert after.index("runLintReport(kind, resumeKey)") < after.index("adoptReport(")
    assert after.index("adoptReport(") < after.index("qc.invalidateQueries(")
    assert _PAGE.count("onDisputed={afterDispute}") == 2
    assert _PAGE.count("dispute={finding.content_hash ? disputes[finding.content_hash] : undefined}") == 2
