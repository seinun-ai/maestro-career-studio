"""Pins: Today is the home page (design refresh, Task 6.2; board "Today page").

`/` opens Today, the sidebar leads with it and folds the rarer tools under More tools, and the page
reads `GET /api/today` (services/today.py) with the browser's zone name and offset. Next up is one
LeadCard whose button is the view's one filled button; a failed read is its own state, never the
empty one. The words are pure (lib/today.ts, its node suite) and the page is rendered with seeded
reads (components/today/today-page.test.mjs).
"""

from __future__ import annotations

import re
from pathlib import Path

from tests._jsx_pins import open_tag
from tests.node_ts import run_node_render_test, run_node_test

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


_HOME = _read("app/page.tsx")
_PAGE = _read("app/today/page.tsx")
_LIB = _read("lib/today.ts")
_SETUP = _read("components/setup/setup-entry-card.tsx")
_SIDEBAR = _read("components/app-sidebar.tsx")


def _nav_items(name: str) -> list[tuple[str, str]]:
    """The (href, label) pairs of one `NavItem[]` list in the sidebar, in order."""
    body = _SIDEBAR[_SIDEBAR.index(f"const {name}: NavItem[] = [") :]
    body = body[: body.index("\n];")]
    return re.findall(r'\{ href: "([^"]+)", label: "([^"]+)"', body)


# ── The home route ──────────────────────────────────────────────────────────


def test_the_home_route_redirects_to_today():
    assert 'redirect("/today");' in _HOME
    assert "/applications" not in _HOME


# ── The sidebar ─────────────────────────────────────────────────────────────


def test_the_sidebar_lists_today_first():
    assert _nav_items("MAIN_ITEMS") == [
        ("/today", "Today"),
        ("/applications", "Jobs"),
        ("/proposals", "Agent inbox"),
        ("/base-resumes", "Base resumes"),
        ("/career", "Career history"),
        ("/analytics", "Analytics"),
    ]
    assert _nav_items("MORE_TOOLS") == [
        ("/automations", "Automations"),
        ("/referrals", "Referrals"),
        ("/templates", "Templates"),
        ("/chat", "Assistant"),
    ]
    # Profile and Settings stay at the bottom, in the footer's own <nav>.
    assert _nav_items("ACCOUNT_ITEMS") == [("/profile", "Profile"), ("/settings", "Settings")]
    footer = _SIDEBAR[_SIDEBAR.index("<SidebarFooter>") : _SIDEBAR.index("</SidebarFooter>")]
    assert "items={ACCOUNT_ITEMS}" in footer
    # The main list renders before the disclosure, the disclosure inside the Main landmark.
    main = _SIDEBAR[_SIDEBAR.index('<nav aria-label="Main"') :]
    assert main.index("items={MAIN_ITEMS}") < main.index("<MoreTools") < main.index("</nav>")


def test_every_destination_stays_reachable():
    """The regroup moves rows; it drops none (every route the old three groups and the footer held)."""
    hrefs = {href for name in ("MAIN_ITEMS", "MORE_TOOLS", "ACCOUNT_ITEMS") for href, _ in _nav_items(name)}
    for href in ("/applications", "/proposals", "/automations", "/referrals", "/career", "/base-resumes",
                 "/templates", "/chat", "/analytics", "/profile", "/settings"):
        assert href in hrefs, href
    assert "NAV_GROUPS" not in _SIDEBAR  # one flat list and a disclosure, not labelled groups


def test_more_tools_is_a_disclosure_with_aria_expanded():
    more = _SIDEBAR[_SIDEBAR.index("function MoreTools(") :]
    button = open_tag(more, "SidebarMenuButton")
    assert 'type="button"' in button
    assert "aria-expanded={expanded}" in button
    assert "aria-controls={panelId}" in button
    assert "More tools" in more[: more.index("</SidebarMenuButton>")]
    # A closed panel is hidden: out of the tab order and the accessibility tree.
    assert "<div id={panelId} hidden={!expanded}>" in more
    assert "items={MORE_TOOLS}" in more
    # Untouched, it is open on a page it holds, so the current page is never folded out of sight.
    assert "const expanded = open ?? holdsCurrent;" in more
    assert "navCurrent(pathname, item.href, from) !== undefined" in more


def test_the_needs_you_badge_moved_to_today():
    assert 'badges={{ "/today": needsYou }}' in _SIDEBAR
    assert '"/proposals": needsYou' not in _SIDEBAR
    assert _SIDEBAR.count("useNeedsYouCount()") == 1


def test_today_has_its_own_icon_in_the_register():
    assert "today: House," in _read("lib/concept-icons.ts")
    assert '{ href: "/today", label: "Today", icon: CONCEPT_ICONS.today },' in _SIDEBAR


# ── The page ────────────────────────────────────────────────────────────────


def test_the_page_sends_the_zone_name_and_the_offset():
    """A Windows install may have no zone database, so the offset always goes with the name."""
    assert "tz: Intl.DateTimeFormat().resolvedOptions().timeZone || null," in _PAGE
    assert "offsetMinutes: -new Date().getTimezoneOffset()," in _PAGE
    assert "queryKey: todayKey(zone)," in _PAGE
    assert "apiFetch<TodayResponse>(todayPath(zone))" in _PAGE
    assert 'if (zone.tz) params.set("tz", zone.tz);' in _LIB
    assert 'params.set("utc_offset_minutes", String(zone.offsetMinutes));' in _LIB


def test_next_up_is_one_lead_card_with_one_action():
    assert _PAGE.count("<LeadCard") == 1
    assert open_tag(_PAGE, "LeadCard").count("action=") == 1
    # Its button is the view's one filled button: the page's other buttons are Next up's quiet Skip, outline.
    buttons = re.findall(r"<Button\b[^>]*>", _PAGE)
    assert len(buttons) == 2 and all('variant="outline"' in b for b in buttons), buttons
    assert "buttonVariants(" not in _PAGE
    assert "secondary={<SkipControl item={item} onSkipped={onSkipped} />}" in _PAGE
    # Setup's entry card stands in the same place and holds the same one button.
    assert _SETUP.count("<LeadCard") == 1
    assert open_tag(_SETUP, "LeadCard").count("action=") == 1
    assert "<Button" not in _SETUP


def test_skip_writes_skipped_with_undo_and_an_agents_job_takes_the_job_pages_skip():
    """A ready PDF's Skip sets the application Skipped and Undo puts it back to Draft; an agent's question
    takes the reason dialog and the proposal's own Skip; an offer has none."""
    assert 'mutationFn: (id: string) => patchStatus(id, "skipped"),' in _PAGE
    assert 'patchStatus(id, "draft")' in _PAGE and 'label: "Undo",' in _PAGE
    assert 'if (item.kind === "pdf_ready" && item.application_id) {' in _PAGE
    assert 'if (item.kind === "needs_you" && item.proposal_id) {' in _PAGE
    assert 'proposalActions.transition({ id, status: "rejected", reason })' in _PAGE
    assert '"offer"' not in _PAGE.split("function SkipControl", 1)[1].split("\n}\n", 1)[0]
    # A skip on the other copy's job is a request, worded as every other one is.
    assert 'if (isSyncQueued(data)) {\n        toast.success("Sent at the next sync");' in _PAGE
    # A Skip anywhere in the Agent inbox refreshes Today too.
    triage = _read("components/proposals/triage-actions.tsx")
    assert 'void qc.invalidateQueries({ queryKey: ["today"] });' in triage
    # A Skip that leaves nothing next hands focus to what replaces the card: the lead slot holds every branch.
    assert "if (!data.next_up) lead.current?.focus();" in _PAGE
    assert '<div ref={lead} tabIndex={-1} className="outline-none">' in _PAGE

def test_a_failed_load_is_its_own_state():
    assert "isLoadFailure(today) ? (" in _PAGE
    assert "<LoadErrorState" in _PAGE
    assert 'title="Couldn\'t load Today."' in _PAGE
    # The error branch comes first: a failed read never reaches "Nothing waiting on you".
    assert _PAGE.index("isLoadFailure(today)") < _PAGE.index("Nothing waiting on you")


def test_the_cards_carry_the_base_resume_square_and_pay_in_the_home_currency():
    # D2: Today's cards carry the square; D8: pay reads through the one formatter.
    assert "<ResumeTag hue={item.base_resume.color_hue}>" in _PAGE
    assert "formatPay(item.pay, money)" in _PAGE and "useMoney()" in _PAGE
    assert "<NumberRoll" in _PAGE
    assert "<Fold" in _PAGE
    # AI waits only: a load is a skeleton, never the working dots.
    assert "WorkingDots" not in _PAGE


def test_setup_shows_only_while_a_required_step_is_open():
    assert "export function needsSetup(status: SetupStatus): boolean {" in _SETUP
    assert "return !status.model_key.done || !status.import_resumes.done;" in _SETUP
    # Its steps come from the one step list the Getting started card reads.
    assert "buildSetupSteps(status, pathname)" in _SETUP


def test_today_words_node_suite():
    result = run_node_test("lib/today.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr


def test_today_page_node_suite():
    """The page rendered with seeded reads: each next-up kind, the counts, the week, the empty and failed states."""
    result = run_node_render_test("components/today/today-page.test.mjs")
    assert result.returncode == 0, result.stdout + result.stderr
