"""Where a Jobs row's job is, and one row height (resume-colour plan, Task 10; design refresh Task 4.1).

The Where column went (owner decision D4): a row shows the Agent inbox's ownership pop-up in its last,
32px slot, and only when the job is not on this copy or a request waits. Source pins in the style of
test_frontend_resume_square.py: the frontend has no component runner. The Node tests in
lib/job-ownership.test.ts and components/job-ownership.test.mjs cover the helpers.
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


def _role_cell() -> str:
    start = _TABLE.index('<TableCell className="max-w-0 whitespace-normal py-2.5">')
    return _TABLE[start : _TABLE.index("</TableCell>", start)]


def test_the_role_cell_is_two_lines_with_no_ownership_in_it():
    assert "JobOwnershipMark" not in _PAGE and "JobOwnershipNotice" not in _PAGE
    role_cell = _role_cell()
    assert role_cell.count("<p ") == 2 and "ownership" not in role_cell
    # The title leads; the second line is "Company · Place" (board "Jobs, fewer words").
    assert role_cell.index("{title}") < role_cell.index("{place || company}")


def test_the_ownership_slot_is_last_and_shows_only_what_the_pop_up_has_to_say():
    """D4: no Where column. The last 32px slot holds the Agent inbox's pop-up while the job is on the
    other copy or a request waits (`ownershipSays`, node-tested), else the row's ⋯, whose writes a job
    on the other copy could not take anyway."""
    head = squash(_TABLE[: _TABLE.index("</TableHeader>")])
    assert head.endswith('<TableHead className="w-10 px-1" /> </TableRow>')
    assert "showWhere" not in _PAGE and "ownershipWhere" not in _PAGE and ">Where<" not in _PAGE
    slot = squash(_TABLE[_TABLE.index("{ownershipSays(owner) ? (") :])
    assert slot.startswith(
        "{ownershipSays(owner) ? ( <JobOwnershipPopover jobId={jobId} ownership={owner} /> ) : selectMode ? null : ("
    )
    lib = squash(_src("lib/job-ownership.ts"))
    assert "return !!view.mark && (!!view.action || !!view.reason || view.pending);" in lib
    comp = squash(_src("components/job-ownership.tsx"))
    assert "if (!ownershipSays(ownership)) return null;" in comp


def test_columns_with_fixed_content_are_in_rem_and_role_takes_the_rest_as_a_percentage():
    """A percentage of a table that scrolls at its min width gave "Offer accepted" less room than its chip
    needs; Role takes what the fixed columns leave."""
    head = squash(_TABLE[: _TABLE.index("</TableHeader>")])
    for name in ("Match", "Status", "Next step"):
        end = head.index(f">{name}</TableHead>")
        tag = head[head.rindex("<TableHead", 0, end) : end + 1]
        width = [t for t in tokens(tag) if t.startswith("w-")]
        assert width and re.fullmatch(r"w-\[[\d.]+rem\]", width[0]), (name, tag)
        assert "px-3" in tokens(tag), name  # head and cell share the tighter padding


def test_the_fixed_columns_pad_their_cells_like_their_heads_and_role_keeps_the_table_padding():
    row = _TABLE[_TABLE.index("<TableRow\n                    key={key}") :]
    row = row[: row.index("</TableRow>")]
    starts = [m.start() for m in re.finditer("<TableCell", row)]
    padded = ["px-3" in open_tag(row[i:], "TableCell") for i in starts]
    # Select mode's checkbox, Role, then Match, Status and Next step carry px-3; the ownership slot is last.
    assert padded == [False, False, True, True, True, False]


def test_role_is_the_only_percentage_column_and_the_resume_column_is_gone():
    """The fixed columns take 31.25rem (Match 6.75, Status 12.5, Next step 12), so at the 57rem min width Role
    keeps about 23.25rem beside the 2.5rem slot. The Match score names the resume on hover."""
    head = squash(_TABLE[: _TABLE.index("</TableHeader>")])
    assert '<TableHead className="w-full" aria-sort={sortedAs("role")}>Role</TableHead>' in head
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
    assert head.index(">Status</TableHead>") < head.index(">Next step</TableHead>")
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
    # One look for every row (D3): your move is NextStep's link, its click kept from opening the row; the rest
    # of the cell opens the job like the row.
    opener = _TABLE[_TABLE.rindex("<TableCell", 0, _TABLE.index("{step ? (")) :]
    assert "onClick" not in open_tag(opener, "TableCell")
    link = squash(cell[: cell.index(") : waiting ? (")])
    assert '<span className="inline-flex" onClick={(e) => e.stopPropagation()} onClickCapture={(e) => {' in link
    assert "<NextStep label={step.label} href={nextStepHref(jobId, step)} />" in link
    # It only navigates, so it is never disabled: the page it opens says whose the job is.
    assert "disabled=" not in link and "canWrite" not in link
    # Applied rows say they wait only while the status is applied; later statuses and closed say nothing.
    assert ('const waiting = stage === "applied" && r.kind === "application" && r.app.status === "applied";'
            in squash(_PAGE))
    # Nothing else: any other row leaves the cell empty.
    assert squash(cell).endswith('<NextStep waiting="Waiting to hear back" /> ) : null}')


def test_the_stage_chips_are_their_own_filter_in_the_url_and_the_session():
    """The resolver, the URL, the group values and the chip counts are node-tested: lib/tracker-filters.test.ts
    and lib/tracker-counts.test.ts (run by test_frontend_jobs_refresh.py). These pins hold the page to them."""
    src = squash(_PAGE)
    assert 'import { chipCount, matchesFilter } from "@/lib/tracker-counts";' in src
    assert "STAGE_FILTERS, TRACKER_VIEWS, VIEW_FILTERS, type StageFilter, type TrackerView, viewOf, } from \"@/lib/tracker-filters\";" in src
    assert "const { filter, stage: stageFilter, source, update } = useTrackerFilters(FILTERS);" in src
    assert "storedValue(" not in src.replace("storeValue(", "")  # session memory is read in the hook only
    hook = squash(_src("app/applications/use-tracker-filters.ts"))
    assert "resolveTrackerFilters((key) => searchParams.get(key), storedValue, filters)" in hook
    assert "storeValue(TRACKER_STORE_KEYS[axis], next[axis] ?? \"\");" in hook
    lib = _src("lib/tracker-filters.ts")
    assert 'stage: "cs-tracker-stage"' in lib and 'stage: "stage"' in lib
    # The stage ANDs with the Status filter, whose group values (active, interviews, closed) the chips set.
    filtered = src[src.index("const filtered = useMemo(") : src.index("const needle")]
    assert "list.filter((r) => matchesFilter(filter, rowFilterKey(r)))" in filtered
    assert "list.filter((r) => rowStage(r) === stageFilter)" in filtered
    # A chip, and a stage option, counts what pressing it shows; a stage option stays while it is on.
    assert 'count: stale ? "…" : chipCount(countRows, VIEW_FILTERS[v], {}),' in src
    assert "chipCount(countRows, axes, { stage: s })" in src
    assert "({ s, count }) => count > 0 || s === stageFilter," in src


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


def test_the_rows_ownership_request_is_in_its_pop_up():
    """Work on it here and Keep it here moved from the row's ⋯ into the pop-up the Agent inbox rows use (D4);
    the ⋯ keeps Queue in Agent inbox and Delete, each only for a row this copy can write."""
    comp = _src("components/job-ownership.tsx")
    pop = squash(comp[comp.index("export function JobOwnershipPopover") :])
    # The request and its words, as the header mark draws them (OwnershipRequest).
    assert "<OwnershipRequest view={view} {...request} />" in pop
    request = squash(comp[comp.index("function OwnershipRequest(") : comp.index("export function JobOwnershipMark")])
    assert '<Button size="xs" variant="outline" pending={busy} onClick={() => act(view.action!)}>' in request
    assert "{ACTION_LABEL[view.action]}" in request
    # A request waiting for the next sync: a dot on the icon, and its words inside.
    assert "{view.pending ? <span className=\"absolute top-1 right-1 size-1.5 rounded-full bg-primary\" aria-hidden=\"true\" /> : null}" in pop
    assert '{view.pending ? <span role="status" className="text-muted-foreground text-body-small">{REQUEST_QUEUED}</span> : null}' in request
    assert "OwnershipMenuItem" not in comp and "OwnershipMenuItem" not in _PAGE
    menu = squash(_TABLE[_TABLE.index("<DropdownMenuContent") : _TABLE.index("</DropdownMenuContent>")])
    assert menu.index("Queue in Agent inbox") < menu.index("Delete job")
    assert menu.count("disabled={promoteJob.isPending || !ownership.canWrite}") == 1
    assert menu.count("disabled={!ownership.canWrite}") == 2


def test_the_header_mark_and_the_row_pop_up_share_one_request_state_per_job():
    comp = _src("components/job-ownership.tsx")
    assert comp.count("ownershipKey(jobId)") == 2  # the mutation's key, and the one read for "busy"
    assert "mutationKey: ownershipKey(jobId)" in comp
    assert "useIsMutating({ mutationKey: ownershipKey(jobId) }) > 0" in comp
    mark = comp[comp.index("export function JobOwnershipMark") : comp.index("export function JobOwnershipNotice")]
    pop = comp[comp.index("export function JobOwnershipPopover") :]
    hook = comp[comp.index("function useOwnershipRequest(") : comp.index("function OwnershipRequest(")]
    assert "useOwnershipBusy(jobId)" in hook
    assert "pending={busy}" in comp[comp.index("function OwnershipRequest(") : comp.index("export function JobOwnershipMark")]
    for user in (mark, pop):
        assert "const request = useOwnershipRequest(jobId);" in user and "<OwnershipRequest view={view} {...request} />" in user


def test_the_ownership_slot_is_in_the_design_system():
    readme = (_ROOT / "docs/design-system/components/JobsTable/README.md").read_text(encoding="utf-8")
    assert "Where column" in readme and "not on this copy" in readme and "JobOwnershipPopover" in readme
