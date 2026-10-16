"""The Jobs table's Where column and one row height (resume-colour plan, Task 10).

Source pins in the style of test_frontend_resume_square.py: the frontend has no component runner. The
Node tests in lib/job-ownership.test.ts and components/job-ownership.test.mjs cover the helpers.
"""

import re
from pathlib import Path

from tests._jsx_pins import open_tag, squash, tokens

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_ROOT = _FRONTEND.parent


def _src(path: str) -> str:
    return (_FRONTEND / path).read_text(encoding="utf-8")


_PAGE = _src("app/applications/page.tsx")
_TABLE = _PAGE[_PAGE.index("<TableHeader>") :]


def test_the_role_cell_is_two_lines_with_no_ownership_in_it():
    assert "JobOwnershipMark" not in _PAGE and "JobOwnershipNotice" not in _PAGE
    role_cell = _TABLE[_TABLE.index("<TableCell") : _TABLE.index("</TableCell>")]
    assert role_cell.count("<p ") == 2 and "ownership" not in role_cell


def test_the_where_head_sits_after_status_and_only_shows_when_a_row_has_a_mark():
    head = squash(_TABLE[: _TABLE.index("</TableHeader>")])
    assert head.index('header("status"') < head.index(">Where</TableHead>") < head.index('header("applied_at"')
    assert "{showWhere ? <TableHead " in head and "</TableHead> : null}" in head
    assert "const showWhere = filtered.some((r) => ownershipWhere(" in squash(_PAGE)


def test_columns_with_fixed_content_are_in_rem_and_role_takes_the_rest_as_a_percentage():
    """A percentage of a table that scrolls at its min width gave "Offer accepted" less room than its chip
    needs; Role takes what the fixed columns leave, with or without Where."""
    head = squash(_TABLE[: _TABLE.index("</TableHeader>")])
    for key in ("ats", "status", "applied_at", "created_at"):
        width = re.search(rf'header\("{key}", "[^"]+", "(w-[^"]+)"\)', head)
        assert width and "%" not in width.group(1), key
        assert "px-3" in width.group(1), key  # head and cell share the tighter padding
    for after in ("{showWhere ?", '{header("applied_at"'):  # Where, then Next step
        fixed = tokens(open_tag(head, "TableHead", after=after))
        assert any(re.fullmatch(r"w-(\d+|\[[\d.]+rem\])", t) for t in fixed), fixed
        assert "px-3" in fixed


def test_the_fixed_columns_pad_their_cells_like_their_heads_and_role_keeps_the_table_padding():
    row = _TABLE[_TABLE.index("<TableRow\n                    key={key}") :]
    starts = [m.start() for m in re.finditer("<TableCell", row)]
    padded = ["px-3" in open_tag(row[i:], "TableCell") for i in starts]
    # Role, then Match score, Status, Where, Applied, Next step, Added carry px-3; the actions cell is last.
    assert padded == [False, True, True, True, True, True, True, False]


def test_role_is_the_only_percentage_column_and_the_resume_column_is_gone():
    """The fixed columns take 45.5rem with Where and 41rem without, so at the 57rem min width Role keeps
    11.5rem and 16rem (it had 11.7rem and 14.6rem at 52rem beside Resume). The Match score names the resume on hover."""
    head = squash(_TABLE[: _TABLE.index("</TableHeader>")])
    assert 'header("role", "Role", "w-full")' in head
    assert "%" not in head  # Role's w-full is the only width that is not in rem
    assert ">Resume</TableHead>" not in head
    assert 'minWidth="57rem"' in _PAGE


def test_the_match_score_names_the_resume_to_readers_and_on_hover_and_the_page_draws_no_resume_square():
    cell = _TABLE[_TABLE.index("const score = rowScore(r);") :]
    cell = cell[: cell.index("</TableCell>")]
    assert "title={resumeName || undefined}" in open_tag(cell, "span", after=": (")
    meter = squash(open_tag(cell, "ScoreBar"))
    assert ('label={ r.kind === "saved" ? "Best match score" : resumeName ? `Match score, ${resumeName}` : "Match score" }'
            in meter)
    # A saved job's best base is not named by the API, so its resumeName is "" and the title is left off.
    assert ('const resumeName = r.kind === "application" ? r.app.base_resume_name || baseName(r.app.base_resume) : "";'
            in squash(_PAGE))
    assert "ResumeTag" not in _PAGE and "useBaseResumeColor" not in _PAGE


def test_the_next_step_cell_links_the_one_control_from_the_servers_stage():
    head = squash(_TABLE[: _TABLE.index("</TableHeader>")])
    assert head.index('header("applied_at"') < head.index(">Next step</TableHead>") < head.index('header("created_at"')
    assert 'import { nextStep, nextStepHref, type Rung } from "@/lib/next-step";' in _PAGE
    assert 'const step = nextStep(stage, r.kind === "saved" ? r.job : r.app);' in squash(_PAGE)
    # List rows carry the rung at their top level (JobSummary, ApplicationSummary), unlike the detail's nested job.
    assert 'return r.kind === "saved" ? r.job.stage : r.app.stage;' in _PAGE
    from app.schemas.application import ApplicationSummary
    from app.schemas.job import JobRead, JobSummary

    assert "stage" in JobSummary.model_fields and "stage" in ApplicationSummary.model_fields
    assert "stage" not in JobRead.model_fields  # the detail's nested job: its rung sits beside it
    # The frontend type matches: JobDetail's `job` leaves the rung out, so a job page cannot read it there.
    types = squash(_src("lib/types.ts"))
    detail = types[types.index("export interface JobDetail {") :]
    assert 'job: Omit<Job, "stage" | "open_session_id" | "gaps_done" | "gaps_total">;' in detail[: detail.index("}")]
    cell = _TABLE[_TABLE.index("{step ? (") :]
    cell = cell[: cell.index("</TableCell>")]
    # The button keeps its click from opening the row; the rest of the cell opens the job like the row.
    opener = _TABLE[_TABLE.rindex("<TableCell", 0, _TABLE.index("{step ? (")) :]
    assert "onClick" not in open_tag(opener, "TableCell")
    button = squash(open_tag(cell, "Button"))
    assert "onClick={(e) => e.stopPropagation()}" in button
    assert 'size="sm"' in button and "variant={step.variant}" in button and "nativeButton={false}" in button
    # It only navigates, so it is never disabled: the page it opens says whose the job is.
    assert "disabled" not in button and "canWrite" not in button
    assert tokens(open_tag(cell, "Button")) >= {"tabular-nums"} and "data-disabled" not in button
    assert "render={<Link href={nextStepHref(jobId, step)}>{step.label}</Link>}" in button
    # Applied rows say they wait only while the status is applied; later statuses and closed say nothing.
    assert ('const waiting = stage === "applied" && r.kind === "application" && r.app.status === "applied";'
            in squash(_PAGE))
    waiting = open_tag(cell, "span", after="waiting ? (")
    assert {"text-muted-foreground", "text-body-small"} <= tokens(waiting)
    # Nothing else: any other row leaves the cell empty.
    assert squash(cell).endswith(">Waiting to hear back</span> ) : null}")


def test_the_stage_chips_are_their_own_filter_in_the_url_and_the_session():
    """The resolver, the URL and the chip counts are node-tested: lib/tracker-filters.test.ts and
    lib/tracker-counts.test.ts. These pins hold the page to them."""
    src = squash(_PAGE)
    assert 'import { chipCount } from "@/lib/tracker-counts";' in src
    assert 'import { STAGE_FILTERS, type StageFilter } from "@/lib/tracker-filters";' in src
    assert "const { filter, stage: stageFilter, source, update } = useTrackerFilters(FILTERS);" in src
    assert "storedValue(" not in src.replace("storeValue(", "")  # session memory is read in the hook only
    hook = squash(_src("app/applications/use-tracker-filters.ts"))
    assert "resolveTrackerFilters((key) => searchParams.get(key), storedValue, filters)" in hook
    assert "storeValue(TRACKER_STORE_KEYS[axis], next[axis] ?? \"\");" in hook
    lib = _src("lib/tracker-filters.ts")
    assert 'stage: "cs-tracker-stage"' in lib and 'stage: "stage"' in lib
    # It ANDs with the Status select, which keeps its options.
    filtered = src[src.index("const filtered = useMemo(") : src.index("const needle")]
    assert "list.filter((r) => rowFilterKey(r) === filter)" in filtered
    assert "list.filter((r) => rowStage(r) === stageFilter)" in filtered
    # A chip counts what pressing it shows, and stays while it is on.
    assert "count: chipCount(countRows, axes, { stage })," in src
    assert 'count: chipCount(countRows, axes, { filter: "needs_you" }),' in src
    assert ".filter((s) => s.count > 0 || s.on)" in src


def test_the_where_cell_is_an_icon_and_a_word_with_the_long_sentence_for_the_tooltip_and_for_readers():
    cell = _TABLE[_TABLE.index("{showWhere ? (") :]
    cell = cell[: cell.index("</TableCell>")]
    squashed = squash(cell)
    # The bot is where your connected agents run, so it wears their glyph, as the header mark does.
    assert "where?.bot ? CONCEPT_ICONS.agentInbox : CONCEPT_ICONS.laptop" in squash(_PAGE)
    assert "title={where.sentence}" in open_tag(cell, "span")
    icon = open_tag(cell, "WhereIcon")
    assert "text-muted-foreground" in tokens(icon) and 'aria-hidden="true"' in icon
    assert "{where.word}" in squashed
    assert '<span className="sr-only">{where.sentence}</span>' in squashed


def test_a_request_still_on_its_way_shows_as_waiting_under_the_label():
    cell = _TABLE[_TABLE.index("{showWhere ? (") :]
    cell = cell[: cell.index("</TableCell>")]
    squashed = squash(cell)
    # A request still on its way shows as a small muted word under the label; the sentence says the rest.
    queued = open_tag(cell, "span", after="{where.pending ?")
    assert "text-muted-foreground" in tokens(queued) and ">Waiting</span>" in squashed
    assert ">Queued<" not in squashed  # Queued is a saved job's status chip
    # Every row of a table that shows Where has an owner; a row without one just leaves the cell empty.
    assert "—" not in cell


def test_the_page_reads_row_data_only():
    # tests/sync/test_frontend_ownership.py forbids the hook module; the cell reads the row's ownership.
    assert "use-job-ownership" not in _PAGE
    assert "const owner = r.kind === \"saved\" ? r.job.ownership : r.app.ownership;" in _PAGE


def test_a_chip_on_a_job_that_is_moving_is_locked_but_still_focusable():
    chip = open_tag(_TABLE, "StatusChip")
    assert "disabled=" not in chip  # StatusChip derives locked from the reason
    assert "lockedReason={ownership.canRequest ? undefined : (ownership.reason ?? undefined)}" in squash(chip)
    src = squash(_src("components/status-chip.tsx"))
    assert "lockedReason?: string;" in src
    assert "const locked = disabled || !!lockedReason;" in src
    assert "const blocked = pending || !!lockedReason;" in src
    # The pending path: aria-disabled, and a menu that refuses to open, so the chip keeps focus.
    assert "open={open && !blocked}" in src
    assert "if (!blocked) setOpen(next);" in src
    assert "aria-disabled={blocked || undefined}" in src


def test_a_locked_chip_explains_itself_and_does_not_invite_a_click():
    src = squash(_src("components/status-chip.tsx"))
    assert "aria-describedby={lockedReason ? reasonId : undefined}" in src
    assert 'id={reasonId} className="sr-only">{lockedReason}</span>' in src
    assert "useId()" in src
    # No hover lift or pointer cursor while locked, and the chevron is a lock.
    assert "chipClasses(!locked, locked)" in src
    assert 'locked && "cursor-default' in src
    assert "<CONCEPT_ICONS.locked" in src


def test_the_row_menu_offers_the_ownership_action_before_delete():
    menu = squash(_TABLE[_TABLE.index("<DropdownMenuContent") : _TABLE.index("</DropdownMenuContent>")])
    action = ("{ownership.action ? ( <> <OwnershipMenuItem jobId={jobId} action={ownership.action} /> "
              "<DropdownMenuSeparator /> </> ) : null}")
    assert action in menu and menu.index(action) < menu.index("Delete job")
    comp = _src("components/job-ownership.tsx")
    item = squash(comp[comp.index("export function OwnershipMenuItem") : comp.index("export function JobOwnershipNotice")])
    assert "<DropdownMenuItem disabled={busy}" in item and "CONCEPT_ICONS.laptop" in item
    # The words come from one table. A request merely waiting for the next sync does not disable it:
    # pending_requests counts status changes too, and the server keeps one take-over per job.
    assert "{ACTION_LABEL[action]}" in item and "pending" not in item.replace("pending_requests", "")
    assert "ACTION_LABEL[view.action]" in comp


def test_the_header_mark_and_the_row_menu_share_one_request_state_per_job():
    comp = _src("components/job-ownership.tsx")
    assert comp.count("ownershipKey(jobId)") == 2  # the mutation's key, and the one read for "busy"
    assert "mutationKey: ownershipKey(jobId)" in comp
    assert "useIsMutating({ mutationKey: ownershipKey(jobId) }) > 0" in comp
    mark = comp[comp.index("export function JobOwnershipMark") : comp.index("export function OwnershipMenuItem")]
    item = comp[comp.index("export function OwnershipMenuItem") : comp.index("export function JobOwnershipNotice")]
    assert "useOwnershipBusy(jobId)" in mark and "pending={busy}" in mark
    assert "useOwnershipBusy(jobId)" in item


def test_the_where_column_is_in_the_design_system():
    readme = (_ROOT / "docs/design-system/components/JobsTable/README.md").read_text(encoding="utf-8")
    assert "Where" in readme and "Laptop" in readme and "Moving" in readme
