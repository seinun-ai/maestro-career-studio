"""The Jobs list, refreshed (design refresh Task 4.1, board "Jobs, fewer words").

Five columns (Role, Match, Status with its date, Next step, a 32px slot for where the job is), five
chips with counts, the other filters behind one Filters control, a quiet Select that borrows the Agent
inbox's Select mode, and no subtitle. Source pins in the style of test_frontend_jobs_where.py; the node
tests in lib/tracker-filters.test.ts and lib/tracker-counts.test.ts run here too.
"""

import re
from pathlib import Path

from tests._jsx_pins import open_tag, squash
from tests.node_ts import run_node_test

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _src(path: str) -> str:
    return (_FRONTEND / path).read_text(encoding="utf-8")


_PAGE = _src("app/applications/page.tsx")
_TABLE = _PAGE[_PAGE.index("<TableHeader>") :]
_BULK = _src("app/applications/job-bulk.tsx")
_BAR = _src("components/selection-bar.tsx")


def test_jobs_table_has_no_resume_where_or_added_column():
    head = squash(_TABLE[: _TABLE.index("</TableHeader>")])
    for gone in (">Resume<", ">Where</TableHead>", 'header("created_at"'):
        assert gone not in head
    # Role, Match, Status, Next step and the slot; the Applied date moved into the Status cell.
    names = re.findall(r">(Role|Match|Status|Next step|Applied|Added)</TableHead>", head)
    assert names == ["Role", "Match", "Status", "Next step"], names
    assert "ownershipWhere" not in _PAGE and "showWhere" not in _PAGE


def test_every_next_step_uses_next_step_and_rows_are_hover_groups():
    assert "<NextStep " in _PAGE and "group/row" in _PAGE
    assert 'variant="secondary"' not in _TABLE  # no tonal buttons at rest in rows
    cell = _TABLE[_TABLE.index("{step ? (") :]
    cell = squash(cell[: cell.index("</TableCell>")])
    # Your move links where the job waits; theirs is grey text, never a link.
    assert "<NextStep label={step.label} href={nextStepHref(jobId, step)} />" in cell
    assert '<NextStep waiting="Waiting to hear back" />' in cell
    assert "variant={step.variant}" not in _PAGE and "<Button" not in cell


def test_select_mode_and_ownership_popover_come_from_the_inbox():
    assert "JobOwnershipPopover" in _PAGE and "selectMode" in _PAGE
    # The slot holds the popover, which draws nothing for a job on this laptop with nothing waiting.
    assert "<JobOwnershipPopover jobId={jobId} ownership={owner} />" in squash(_PAGE)
    # The inbox's bar and Select button, not a copy of them.
    assert 'import { SelectToggle } from "@/components/selection-bar";' in _PAGE
    assert 'import { SelectionBar } from "@/components/selection-bar";' in _BULK
    triage = _src("components/proposals/triage-actions.tsx")
    assert 'import { SelectionBar } from "@/components/selection-bar";' in triage
    assert 'data-slot="bulk-bar"' in _BAR and 'data-slot="bulk-bar"' not in triage
    # The bar acts only on the rows shown, as the inbox's does.
    assert "selectedAmong(" in _PAGE


def test_the_bulk_bar_offers_only_what_the_existing_endpoints_do():
    """No archive and no bulk endpoint exist for jobs or applications: the bar loops the single-item
    PATCH and DELETE, and the Queue the row offers, one at a time, as the inbox's Delete does."""
    for invented in ("/bulk", "/archive", "Promise.all"):
        assert invented not in _BULK, invented
    assert "`/api/applications/${id}`" in _BULK and 'method: "PATCH"' in _BULK
    assert 'kind === "saved" ? `/api/jobs/${id}` : `/api/applications/${id}`' in _BULK
    assert "promoteJobToAgentQueue(jobId)" in _BULK
    assert _BULK.count("for (const ") == 3
    # An action shows only when every picked row's own controls allow it, under the same ownership locks.
    page = squash(_PAGE)
    assert 'if (r.kind === "application" && ownership.canRequest) out.push("status");' in page
    assert 'if (r.kind === "saved" && !r.job.proposal_status && ownership.canWrite) out.push("queue");' in page
    assert 'if (ownership.canWrite) out.push(r.kind === "saved" ? "deleteJob" : "deleteApp");' in page
    # Delete asks once; one filled button per view, so every bar action is outline.
    assert "confirmed = await confirm(" in _BULK
    assert all("variant=" in t for t in re.findall(r"<Button\b[^>]*>", _BULK, re.S))


def test_five_chips_with_counts_filter_the_list():
    page = squash(_PAGE)
    for label in ('active: "All active"', 'ready: "Ready to apply"', 'waiting: "Waiting to hear"',
                  'interviews: "Interviews"', 'closed: "Closed"'):
        assert label in page, label
    # Each chip counts the rows pressing it shows, in the source the toggle names.
    assert "count: stale ? \"…\" : chipCount(countRows, VIEW_FILTERS[v], {})," in page
    assert "aria-pressed={on}" in page and 'role="group" aria-label="Show"' in page
    # A chip is a preset of the Status filter and the stage: the URL and session memory stay as they were.
    lib = _src("lib/tracker-filters.ts")
    assert 'export const DEFAULT_FILTER = "active";' in lib
    assert "update(on ? { filter: \"all\", stage: null } : VIEW_FILTERS[v])" in page


def test_the_other_filters_sit_behind_one_filters_control_and_none_is_lost():
    page = squash(_PAGE)
    assert "<FiltersButton " in page and "aria-controls={controls}" in _src("components/filters-button.tsx")
    panel = _PAGE[_PAGE.index("<div id={filtersId}") :]
    panel = panel[: panel.index("</ListToolbar>")]
    # Status (every application status and agent lane), the stage chips and the source toggle.
    assert 'aria-label="Filter by status"' in panel
    assert 'aria-label="Filter by stage"' in panel
    assert "<SourceToggle" in panel and 'allLabel="Tracked"' in panel
    assert "hidden={!filtersOpen}" in squash(panel)
    for stage in ('pdf_ready: "Ready to apply",', 'tailored: "Tailored, review",', 'gaps: "Gaps open",'):
        assert stage in _PAGE, stage


def test_sorting_by_added_stays_in_the_sort_menu():
    page = squash(_PAGE)
    assert 'added: { label: "Newest first", key: "created_at", dir: "desc" },' in page
    assert 'applied: { label: "Recently applied", key: "applied_at", dir: "desc" },' in page
    assert 'aria-label="Sort"' in page


def test_no_subtitle_the_header_is_the_title_a_count_and_the_search():
    header = _PAGE[_PAGE.index("<PageHeader") : _PAGE.index("<ListToolbar>")]
    assert "subtitle=" not in header
    assert 'title="Jobs"' in header and "meta={" in header
    assert '<ListSearch label="Search jobs" value={q} onChange={setQ} />' in header
    shell = _src("components/page-shell.tsx")
    assert "meta?: ReactNode;" in shell


def test_the_status_cell_carries_the_applied_date():
    cell = _TABLE[_TABLE.index("<StatusChip") :]
    cell = cell[: cell.index("</TableCell>")]
    assert "r.app.applied_at ?" in cell and "formatShortDate(r.app.applied_at)" in cell
    assert '<span className="sr-only">Applied </span>' in cell


def test_the_tracker_lib_node_tests_pass():
    for name in ("lib/tracker-filters.test.ts", "lib/tracker-counts.test.ts"):
        result = run_node_test(name)
        assert result.returncode == 0, result.stdout + result.stderr


def test_the_select_toggle_and_filters_button_are_quiet():
    toggle = open_tag(_BAR[_BAR.index("export function SelectToggle(") :], "Button")
    button = _src("components/filters-button.tsx")
    filters = open_tag(button[button.index("export function FiltersButton(") :], "Button")
    for tag in (toggle, filters):
        assert 'variant="ghost"' in tag and 'size="sm"' in tag
