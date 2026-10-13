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
    assert '{showWhere ? <TableHead className="w-[9%] px-3">Where</TableHead> : null}' in head
    assert "const showWhere = filtered.some((r) => ownershipWhere(" in squash(_PAGE)
    # Today's 96%: Role 27 with Where, 36 without (it gets Where's 9). The others never change. Status is
    # 16, not the 13 the plan listed: "Interviewing" is 118px and ran into Where's icon at the table's 52rem.
    assert 'showWhere ? "w-[27%]" : "w-[36%]"' in head
    rest = [int(w) for w in re.findall(r"w-\[(\d+)%\]", head.replace("w-[27%]", "").replace("w-[36%]", ""))]
    assert rest == [15, 11, 16, 9, 9, 9] and 27 + sum(rest) == 36 + sum(rest) - 9 == 96


def test_the_where_cell_is_an_icon_and_a_word_with_the_long_sentence_as_its_title():
    cell = _TABLE[_TABLE.index("{showWhere ? (") :]
    cell = cell[: cell.index("</TableCell>")]
    squashed = squash(cell)
    # The bot is where your connected agents run, so it wears their glyph, as the header mark does.
    assert "where?.bot ? CONCEPT_ICONS.agentInbox : CONCEPT_ICONS.laptop" in squash(_PAGE)
    span = open_tag(cell, "span")
    assert "title={where.sentence}" in span
    icon = open_tag(cell, "WhereIcon")
    assert "text-muted-foreground" in tokens(icon) and 'aria-hidden="true"' in icon
    assert "{where.word}" in squashed


def test_the_page_reads_row_data_only():
    # tests/sync/test_frontend_ownership.py forbids the hook module; the cell reads the row's ownership.
    assert "use-job-ownership" not in _PAGE
    assert "const owner = r.kind === \"saved\" ? r.job.ownership : r.app.ownership;" in _PAGE


def test_a_row_the_laptop_cannot_ask_about_shows_a_lock_in_its_status_chip():
    chip = open_tag(_TABLE, "StatusChip")
    assert "disabled={!ownership.canRequest}" in chip
    assert "lockedReason={ownership.canRequest ? undefined : (ownership.reason ?? undefined)}" in squash(chip)
    src = _src("components/status-chip.tsx")
    assert "lockedReason?: string;" in src
    assert "CONCEPT_ICONS.locked" in src and "title={lockedReason}" in src
    # A chip without a reason keeps its chevron.
    assert "lockedReason ? " in src and "<ChevronDown" in src


def test_the_row_menu_offers_the_ownership_action_before_delete():
    menu = squash(_TABLE[_TABLE.index("<DropdownMenuContent") : _TABLE.index("</DropdownMenuContent>")])
    action = '{ownership.action ? ( <> <OwnershipMenuItem jobId={jobId} action={ownership.action} /> <DropdownMenuSeparator /> </> ) : null}'
    assert action in menu and menu.index(action) < menu.index("Delete job")
    comp = _src("components/job-ownership.tsx")
    item = comp[comp.index("export function OwnershipMenuItem") :]
    assert "useOwnershipAction(jobId)" in item and "<DropdownMenuItem" in item
    assert 'view.action === "keep-here" ? "Keep it here" : "Work on it here"' not in item  # one place picks the words
    assert "CONCEPT_ICONS.laptop" in item


def test_the_where_column_is_in_the_design_system():
    readme = (_ROOT / "docs/design-system/components/JobsTable/README.md").read_text(encoding="utf-8")
    assert "Where" in readme and "Laptop" in readme and "Moving" in readme
