> **Appendix B (sticky list chrome and the capped-list notice) to the 2026-09-23 UX IA/copy plan.** Research brief
> written read-only against `8cac7cf9` (main; branch `claude/ux-ia-copy-plan`). Each task in the plan names the
> section it uses. Where this appendix offers options, the plan's "Owner decisions" section is binding. Line numbers
> drift: re-locate by the quoted code before editing.

# Phase B: long lists keep their controls and column names in view, and a capped list says so

Worktree `.claude/worktrees/ux-next-plan-continue-03c4a1`, branch `claude/ux-ia-copy-plan` at `8cac7cf9`. All paths
are relative to the repo root, and all line numbers are at `8cac7cf9`.

**Owner decisions this appendix implements (binding):**
1. Sticky table headers and filter toolbars **app-wide**, through one shared mechanism.
2. A notice at the **end** of a list fetched with a row limit, when the limit was hit. One shared component,
   `components/list-cap-notice.tsx`, used on Applications here and reused by the Agent inbox appendix.

**Goal Card (this phase):** on every long list, the search/filter/sort row and the column names stay visible while
the rows scroll, without ever hiding keyboard focus; and no list drops rows silently.
Principles: WCAG 2.2 AA (2.4.11 Focus Not Obscured, 1.4.10 Reflow); focus never dropped or hidden; no new
dependencies; React Compiler lint at error level; conventions change with the code.

## B0. Read this first

**Nine findings shape the design:**

1. **The window is the scroll container on every list page.** Nothing between a page and `<html>` sets `overflow`:
   - `SidebarProvider`'s wrapper is `flex min-h-svh w-full` (`components/ui/sidebar.tsx:140-141`);
   - `SidebarInset` is `relative flex w-full min-w-0 flex-1 flex-col bg-background …` (`:314-331`);
   - `SidebarGutter` is `flex min-w-0 flex-1 flex-col …` (`components/sidebar-reveal-trigger.tsx:84-88`);
   - `PageShell` is `mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 p-6` (`components/page-shell.tsx:29-33`);
   - `html` and `body` set no overflow (`app/globals.css:186-191`; `app/layout.tsx:38-43`).

   The health report's rail already sticks to the window this way (`lg:sticky lg:top-6`,
   `components/resume-health/health-report-page.tsx:338`). Only `FullscreenEditorPage` (`h-dvh overflow-hidden`)
   scrolls itself, and it holds no list. B2 pins the chain so it stays that way.
2. **Two containers break a sticky table header today, not one:**
   - `Table` wraps every `<table>` in `relative w-full overflow-x-auto` (`components/ui/table.tsx:9-12`). A non-visible
     `overflow-x` forces `overflow-y` to `auto`, so that div is a scroll container on both axes. A header inside it
     sticks to a box that never scrolls vertically, which means it never sticks.
   - `TableFrame` is `animate-fade-rise overflow-hidden rounded-xl border` (`components/empty-state.tsx:69-73`).
     `overflow: hidden` is a scroll container too.

   `overflow: clip` rounds the corners the same way and does **not** make a scroll container. I checked this on a
   Chromium scratch page: a sticky `thead` inside a `clip` frame with a 12px radius stuck to the window, and the
   radius survived.
3. **No CSS lets one box scroll sideways and also pass vertical stickiness to the window.** `overflow-x: auto` with
   `overflow-y: visible` computes to `auto/auto`. So I chose: **a header sticks only while its table fits.** A
   container query on the frame's width compares it with the table's min width.
   - When the table fits, nothing can scroll sideways. The container switches to `overflow-x: clip` and the header
     sticks to the window.
   - When it does not fit, the container scrolls sideways as it does today, and the header scrolls away with the
     rows. The toolbar still sticks.

   Options and trade-offs are in B3. Chromium check on the scratch page:
   - at 1280×800, the header was `sticky` and the container `clip`; the header's top was 101px and the toolbar's
     bottom 101px;
   - at 768, the header was `static`, the container `auto` (sideways scroll worked) and the page had no sideways
     scroll.
4. **Where the Applications header can stick (the table's min width is `min-w-[52rem]` = 832px).** The frame's inner
   width is the viewport, minus 256px for a pinned sidebar or 56px for the `pl-14` gutter while it is hidden, minus
   48px of `PageShell` padding, minus 2px of border:

   | Viewport | Sidebar | Frame inner width | Header sticks? |
   |---|---|---|---|
   | 1440 | pinned | 1102px (shell cap) | yes |
   | 1280 | pinned | 974px | yes |
   | 1024 | collapsed | 918px | yes |
   | 1024 | pinned | 718px | no |
   | 768 | either | 462 or 662px | no |
   | 375 | sheet | 269px | no |

   Referrals (`min-w-[48rem]` = 768px) gives the same answers. Open question O1 covers the narrow band.
5. **Collapsed table borders can stay behind when the header moves.** Preflight sets `border-collapse: collapse`, and
   the header row's rule is a `tr` border: `TableHeader`'s `[&_tr]:border-b` and `TableRow`'s own `border-b`
   (`table.tsx:26`, `:60`). Engines paint collapsed borders with the table grid, so the rule can be left at its
   original place. The sticky header therefore draws its rule inside its cells (an inset box-shadow) and drops the
   `tr` border. The scratch page confirms that the shadow travels with the header.
6. **A sticky header does hide keyboard focus unless the scroller is told about it.** On the scratch page:
   - Without `scroll-padding-top`: I scrolled a row under the stuck header, focused the next row, and pressed a real
     Shift+Tab. Focus moved to the covered row, and Chromium did not scroll (its top was 105px, under a header whose
     bottom was 141px). That is a WCAG 2.4.11 failure.
   - With `html { scroll-padding-top: <toolbar + header> }` (technique C43): the same key scrolled the row clear
     (top 455px).

   B5 builds this in. WebKit is unverified (see Risks).
7. **The sticky offsets start at `top: 0`, because nothing above a page sticks.**
   - `VersionBanner` renders in normal flow above the page (`app/layout.tsx:58-61`; `components/version-banner.tsx:27-31`),
     so it scrolls away.
   - The app has **no mobile header bar**: below 768px the sidebar is a Sheet.
   - The only fixed chrome is the reveal pill, `fixed top-3 left-3 z-50`, 28px (`sidebar-reveal-trigger.tsx:52`). It
     sits inside the 56px `pl-14` gutter that `SidebarGutter` reserves while it shows, so it never overlaps a stuck
     toolbar.
8. **Short viewports must not stick.** At 375px the Applications toolbar wraps to about 146px. On a landscape phone
   (height about 375px), or at 400% zoom (a 1280×1024 screen becomes 320×256 CSS px), a stuck toolbar and header
   would cover a third of the screen or more. WCAG 1.4.10 expects that content to scroll. So nothing sticks below
   40rem (640px) of viewport height: a `tall:` custom variant.
9. **Backend limits and totals** (B9):
   - `GET /api/applications` and `GET /api/jobs` take `limit` with `ge=1, le=500`, default 100
     (`backend/app/routers/applications.py:178`, `backend/app/routers/jobs.py:310`). Both return a **bare array with
     no total**. The frontend cannot ask for 501 rows to learn whether there are more.
   - `GET /api/proposals` has default 500, max 500, and **returns `total`** (`backend/app/routers/proposals.py:182,
     190, 214`). So the inbox can say "500 of 812". Applications cannot, and does not invent a total.
   - Two more silent caps turned up:
     - the saved-jobs cap counts agent-captured jobs, so an active hunt can push the user's own saved jobs out of
       the 500 (O4);
     - the Career KB draft inbox calls `/api/kb/points?state=draft` with the default `limit=500`
       (`frontend/lib/api.ts:467`; `backend/app/routers/career_kb.py:353`) (O8).

**The inventory is short.** Only three files use `components/ui/table.tsx`: Applications, Referrals and the ATS
compare panel. B1 decides each list page.

## Global constraints (every task)

- **Lint (`cd frontend && npm run lint`) has the React Compiler rules at error level.** The only new hook code is
  `ListToolbar`'s effect. It reads `ref.current` inside the effect, and writes a CSS variable from a
  `ResizeObserver` / `matchMedia` callback. It calls no `setState`, and it does not mutate props or query-cache
  objects. `Table` and `TableHeader` read a React context. No refs are read during render.
- **No new dependencies.** The design uses Tailwind 4.2.4 features already in the tree. I compiled each new class
  with the repo's own `tailwindcss` (`node_modules/tailwindcss/dist/lib.mjs` `compile()`), and each produced the
  intended CSS:
  - `@container/table`;
  - `@min-[52rem]/table:overflow-x-clip` → `@container table (width >= 52rem) { overflow-x: clip }`;
  - `@min-[52rem]/table:tall:sticky` → nested `@container` + `@media`;
  - `top-(--list-sticky-top,0px)`;
  - `overflow-clip`;
  - `[&_th]:shadow-[inset_0_-1px_0_var(--color-border)]`;
  - `[&_tr]:border-b-0`;
  - a `@custom-variant tall (@media (min-height: 40rem))`.

  The repo already uses named container queries (`@container/chat`, `@2xl/chat:`) and one custom variant
  (`globals.css:5`).
- **`lib/*.ts` imports nothing** (appendix F finding 7: `node --test` needs `.ts` extensions that `tsc` rejects).
  `lib/list-cap.ts` is pure.
- **Node unit tests are not in CI.** Run `cd frontend && node --test lib/*.test.ts`. New file: `lib/list-cap.test.ts`.
- **Source pins** go in a new `backend/tests/test_frontend_sticky_lists.py`. Run
  `cd backend && python -m pytest tests/test_frontend_*.py -q`.
  - **Mutation-check every new pin**: revert the fix line and watch the pin fail. Each section lists the mutation.
- **Frontend duplication ratchet**: run `python3 ~/.claude/skills/ai-slop-detector/scripts/slop_scan.py check frontend`
  from the repo root before and after. The new files are small and unique, and Applications loses about 5 lines.
- **`frontend/AGENTS.md`**: no Next.js API is touched (only client components, CSS and a context). Nothing needs a
  read of `node_modules/next/dist/docs/` beyond the usual.
- **Docs contract**: the conventions bullets (B11) change in the same commit as their code. SYSTEM.md is at
  **1000/1000** lines, so the one SYSTEM.md edit is a same-length rewording, queued for the docs sweep. Run
  `python3 scripts/check_system_md.py`.
- **Browser checks** follow the worktree verification recipe: a throwaway DB and a fresh uvicorn/next stack on
  spare ports, never the compose images (SYSTEM.md §9). Use Playwright with real key events
  (`page.keyboard.press`) in **Chromium and WebKit**. The desktop shell is WebKit (conventions, "PdfPagesPreview":
  "arrow keys scroll it in WebKit (the desktop shell)").

---

## B1. Inventory: which pages qualify

A page qualifies when its list can grow past one screen **and** it scrolls in the window.
- A qualifying table gets a sticky header.
- A qualifying list with search, filter or sort controls above it gets a sticky toolbar.

| Page / surface | File:line | List | Grows past a screen? | Controls above | Decision |
|---|---|---|---|---|---|
| Applications | `app/applications/page.tsx:417-473`, `:532-702` | `<Table>` in `TableFrame`, `min-w-[52rem] table-fixed` | yes (up to 500 + 500 rows) | search, status `Select`, `SourceToggle` | **toolbar + header (B6); cap notice (B10)** |
| Agent inbox | `components/proposals/proposals-section.tsx:413-485` (toolbar), `:487-642` (lanes) | `Card` rows in lanes, no table | yes (up to 500) | Sort/Role/Board/Min score (the Agent inbox appendix replaces them with an Applications-style toolbar) | **toolbar only (B8, contract for that appendix); cap notice with `total`** |
| Referrals | `app/referrals/page.tsx:317-345` | `<Table>` in `TableFrame`, `min-w-[48rem] table-fixed` | can (no API limit; `routers/referrals.py:37`); edit rows are taller | none (Add referral is in the page header) | **header only (B7)** |
| Career KB | `app/career/page.tsx:104-147` | `Tabs` over card grids (`EntityCard`) | no: per-kind counts are small | `TabsList` | no |
| KB draft inbox | `components/career/inbox-panel.tsx:222-245` | grouped draft rows | can (up to the silent 500 cap) | none | no (O8 for the cap) |
| Templates | `app/templates/page.tsx` | `GalleryGrid` | no | none | no |
| Base résumés | `app/base-resumes/page.tsx` | `GalleryGrid` | no | none | no |
| Analytics · autofill top failures | `components/analytics/autofill-coverage-card.tsx:178-181` | raw `<table>` | no: `TOP_FAILURES_LIMIT = 10` (`services/autofill_telemetry.py:78`) | none | no |
| Analytics · skills heatmap | `components/charts/heatmap-chart.tsx:60-67` | raw `<table>` in `overflow-x-auto`, sticky-left column | medium | none | no. It must scroll sideways, so under B0 finding 3 its header cannot stick to the window. It already sticks its first column. |
| Job page · ATS compare | `components/ats-compare-panel.tsx:231-238` | `<Table>` in a `Card` (`overflow-hidden`) | no (JD skills, tens of rows) | none | no |
| Chat sessions rail | `components/chat/chat-page.tsx` | rail list | inside its own scroller | none | no |

**Rule for new pages** (B11): a new list page that qualifies adopts `ListToolbar` and `<Table minWidth stickyHeader>`.
The conventions bullet and the B3 pins make that the default path.

---

## B2. The scroll container stays the window

### Current code (quoted in B0 finding 1). No change; pin it.

### Pins (`backend/tests/test_frontend_sticky_lists.py`, file header and helpers first)
```python
"""Pins for sticky list chrome (a list's toolbar and its table header) and the
notice at the end of a capped list.
Design: docs/plans/2026-09-23-ux-ia-appendix-b-sticky-and-cap.md."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_FRONTEND = _ROOT / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


def _body(src: str, start: str) -> str:
    """From `start` to the end of that top-level function (a `}` alone at column 0)."""
    i = src.index(start)
    return src[i : src.index("\n}\n", i)]


_TABLE = _read("components/ui/table.tsx")
_TOOLBAR = _read("components/list-toolbar.tsx")
_CSS = _read("app/globals.css")
_TRACKER = _read("app/applications/page.tsx")
_REFERRALS = _read("app/referrals/page.tsx")

_SCROLL_CHAIN = [
    ("components/ui/sidebar.tsx", "function SidebarProvider("),
    ("components/ui/sidebar.tsx", "function SidebarInset("),
    ("components/sidebar-reveal-trigger.tsx", "export function SidebarGutter("),
    ("components/page-shell.tsx", "export function PageShell("),
]


@pytest.mark.parametrize("rel,start", _SCROLL_CHAIN)
def test_the_window_stays_the_only_scroller(rel: str, start: str):
    """position: sticky sticks to the nearest scrolling ancestor. The list
    toolbar and header rely on that being the window: an overflow class on any
    shell element between them and <html> pins them to a box that never
    scrolls, and they silently stop sticking."""
    found = re.findall(r"\boverflow-[\w-]+", _body(_read(rel), start))
    assert found == [], f"{rel} {start}: {found}"


def test_layout_and_document_do_not_scroll_themselves():
    assert not re.search(r"\boverflow-[\w-]+", _read("app/layout.tsx"))
    for sel in ("  html {", "  body {"):
        i = _CSS.index(sel)
        assert "overflow" not in _CSS[i : _CSS.index("}", i)], sel
```
These pass on `8cac7cf9` as they stand. I ran the extraction: `SidebarInset`'s comment says "overflow container"
without a hyphen, so the regex skips it. **Mutation:** add `overflow-hidden` to `PageShell` and the pin fails.

### Browser check B2-a (scroll-container audit)
On `/applications` at 1280×800 with the sidebar pinned, run this in the console:
```js
const th = document.querySelector('[data-slot="table-header"]');
const bad = [];
for (let e = th.parentElement; e; e = e.parentElement) {
  const s = getComputedStyle(e);
  if (!/^(visible|clip)$/.test(s.overflowY)) bad.push([e.tagName, e.dataset.slot, s.overflowX, s.overflowY]);
}
[document.scrollingElement.tagName, bad];
```
- **At 1280:** expect `["HTML", []]`.
- **At 768:** expect exactly one entry, `["DIV","table-container","auto","auto"]`. That is the sideways scroller,
  by design.

---

## B3. `Table`: a `minWidth`, and a header that sticks while the table fits

### Options considered for the horizontal-scroll conflict

| Option | How | For | Against | Verdict |
|---|---|---|---|---|
| **A. Stick while it fits** (container query) | The scope div is `@container/table`. At ≥ min width the container is `overflow-x: clip` and the header sticks to the window. Below it the container scrolls sideways and the header does not stick. | Pure CSS, no JS. The page scroll is unchanged. SSR-correct (no flash). Reacts live to the sidebar toggling. The min width is one literal per table. | No sticky header where the table is wider than its frame: 1024 with the sidebar pinned, 768 and 375 on Applications (B0 finding 4). | **Chosen** |
| B. The table box scrolls both ways | The container gets `max-h-[calc(100dvh-…)] overflow-auto`, and the header sticks inside it. | Works at every width. | A nested scroller: the wheel and touch get trapped until the inner box ends (a known anti-pattern on touch tablets at 768). WebKit does not focus scrollers, so it needs `role="region"` + `tabIndex` + a name (conventions, `PdfPagesPreview`). Its max-height depends on the measured toolbar height. The cap notice drops below a box the user must scroll past. | Rejected |
| C. Sticky only at a viewport breakpoint (`lg:`) | A media query instead of a container query. | Simple. | Cannot see the sidebar: at 1024 pinned the frame is 718px, so the header would stick while the container still scrolls sideways (broken), or the container would clip real columns. | Rejected |
| D. A cloned header synced by JS | A second, `aria-hidden` header outside the scroller, with `translateX` synced to `scrollLeft`. | Works at every width. | Duplicate sort controls, or a mouse-only clone; scroll-event jank; two headers for screen readers to reconcile. | Rejected |

Option A leaves the narrow widths as they are today. O1 offers the one change that would widen its reach: hide two
columns in the narrow band so the table fits.

### Current code (`components/ui/table.tsx:7-30`)
```tsx
function Table({ className, ...props }: React.ComponentProps<"table">) {
  return (
    <div
      data-slot="table-container"
      className="relative w-full overflow-x-auto"
    >
      <table
        data-slot="table"
        className={cn("w-full caption-bottom text-sm", className)}
        {...props}
      />
    </div>
  )
}

function TableHeader({ className, ...props }: React.ComponentProps<"thead">) {
  return (
    <thead
      data-slot="table-header"
      className={cn("[&_tr]:border-b", className)}
      {...props}
    />
  )
}
```

### New code (replaces `:7-30`; the rest of the file is unchanged)
```tsx
/**
 * A list table's min width, and the two classes that key on it.
 *
 * `position: sticky` sticks to the nearest SCROLLING ancestor, and this
 * container's `overflow-x-auto` is one (a non-visible overflow-x forces
 * overflow-y to auto). A header inside it sticks to a box that never scrolls
 * vertically, so it never sticks. No CSS lets one box scroll sideways and pass
 * vertical stickiness through to the window, so a sticky table sticks only
 * while it FITS. When the `@container/table` scope is at least the table's
 * min width, nothing can scroll sideways, and the container clips instead
 * (`overflow: clip` makes no scroll container). The header then sticks to the
 * window. Narrower, the container scrolls sideways as before and the header
 * scrolls with the rows. One literal per width, because Tailwind reads class
 * names from source: the three strings of an entry must agree (pinned).
 */
const MIN_WIDTH = {
  "48rem": {
    table: "min-w-[48rem]",
    fits: "@min-[48rem]/table:overflow-x-clip",
    head: "@min-[48rem]/table:tall:sticky",
  },
  "52rem": {
    table: "min-w-[52rem]",
    fits: "@min-[52rem]/table:overflow-x-clip",
    head: "@min-[52rem]/table:tall:sticky",
  },
} as const

type TableMinWidth = keyof typeof MIN_WIDTH

/** The sticky class for this table's header, or null when it does not stick. */
const StickyHeadContext = React.createContext<string | null>(null)

type TableProps = React.ComponentProps<"table"> &
  (
    | { minWidth?: TableMinWidth; stickyHeader?: false }
    // A sticky header needs the width it sticks from.
    | { minWidth: TableMinWidth; stickyHeader: true }
  )

function Table({ className, minWidth, stickyHeader, ...props }: TableProps) {
  const width = minWidth ? MIN_WIDTH[minWidth] : undefined
  const sticky = stickyHeader && width ? width : undefined
  const table = (
    <div
      data-slot="table-container"
      className={cn("relative w-full overflow-x-auto", sticky?.fits)}
    >
      <table
        data-slot="table"
        className={cn("w-full caption-bottom text-sm", width?.table, className)}
        {...props}
      />
    </div>
  )
  if (!sticky) return table
  return (
    // The container the fit is measured on: the frame's width, not the
    // table's. inline-size containment: use it only where the parent gives
    // the width (a block or a stretched flex item), never in a shrink-to-fit
    // box, which would collapse it to zero.
    <div data-slot="table-scope" className="@container/table w-full">
      <StickyHeadContext.Provider value={sticky.head}>
        {table}
      </StickyHeadContext.Provider>
    </div>
  )
}

function TableHeader({ className, ...props }: React.ComponentProps<"thead">) {
  const sticky = React.useContext(StickyHeadContext)
  return (
    <thead
      data-slot="table-header"
      // html:has([data-sticky]) reserves the header's height in
      // scroll-padding-top (globals.css), so focus never lands under it.
      data-sticky={sticky ? "" : undefined}
      className={cn(
        sticky
          ? [
              sticky,
              // Under a ListToolbar, below it; with none, at the window's top.
              "top-(--list-sticky-top,0px) z-10 print:static",
              // Opaque cells, or rows show through. A table on a card passes
              // [&_th]:bg-card.
              "[&_th]:bg-background",
              // A collapsed border belongs to the table grid and can stay put
              // when the header moves, so the header draws its rule inside
              // its cells and drops the row border.
              "[&_tr]:border-b-0 [&_th]:shadow-[inset_0_-1px_0_var(--color-border)]",
            ]
          : "[&_tr]:border-b",
        className
      )}
      {...props}
    />
  )
}
```
Notes:
- **Only the tables that opt in change.** `ats-compare-panel.tsx:231` passes no props, so it renders exactly the old
  markup.
- **The rule wins by specificity.** `[&_tr]:border-b-0` (`.x tr`, 0,1,1) beats `TableRow`'s own `border-b` (0,1,0).
- **Unstuck, the look is unchanged.** It is still one 1px rule under the 40px (`h-10`) header row, drawn inside the
  cells instead of on the row edge.
- **`z-10` only applies while the header is positioned.** `thead` is not a flex item.
- **The context is the owner's "sticky option on TableHeader", moved to `Table`.** `Table` owns the scroll container
  and the width gate, so a header cannot opt in without them. That makes it impossible to write a sticky header that
  can never stick.

### Pins
```python
_WIDTH_ENTRY = re.compile(
    r'"(\d+rem)": \{\s*'
    r'table: "min-w-\[(\d+rem)\]",\s*'
    r'fits: "@min-\[(\d+rem)\]/table:overflow-x-clip",\s*'
    r'head: "@min-\[(\d+rem)\]/table:tall:sticky",\s*\}'
)


def test_a_table_sticks_from_exactly_its_own_min_width():
    entries = _WIDTH_ENTRY.findall(_TABLE)
    assert len(entries) >= 2, "MIN_WIDTH entries not found"
    for widths in entries:
        assert len(set(widths)) == 1, widths
    block = _TABLE[_TABLE.index("const MIN_WIDTH = {") : _TABLE.index("} as const")]
    assert block.count('table: "min-w-[') == len(entries)  # no entry the regex skipped


def test_every_call_site_width_is_in_the_map_and_nowhere_else():
    keys = {w[0] for w in _WIDTH_ENTRY.findall(_TABLE)}
    for root in ("app", "components"):
        for p in sorted((_FRONTEND / root).rglob("*.tsx")):
            src = p.read_text(encoding="utf-8")
            for w in re.findall(r'<Table\b[^>]*\bminWidth="([^"]+)"', src):
                assert w in keys, f"{p}: minWidth={w} has no MIN_WIDTH entry"
            # One source for the number: a call site never restates it.
            assert not re.search(r'<Table\b[^>]*className="[^"]*min-w-\[', src), p


def test_the_container_scrolls_sideways_until_the_table_fits():
    table = _body(_TABLE, "function Table(")
    assert '"relative w-full overflow-x-auto", sticky?.fits' in table
    assert '"@container/table w-full"' in table
    assert "StickyHeadContext.Provider value={sticky.head}" in table


def test_a_sticky_header_is_opaque_ruled_stacked_and_placed_under_the_toolbar():
    head = _body(_TABLE, "function TableHeader(")
    for part in (
        "React.useContext(StickyHeadContext)",
        'data-sticky={sticky ? "" : undefined}',
        '"top-(--list-sticky-top,0px) z-10 print:static"',
        '"[&_th]:bg-background"',
        '"[&_tr]:border-b-0 [&_th]:shadow-[inset_0_-1px_0_var(--color-border)]"',
        ': "[&_tr]:border-b"',
    ):
        assert part in head, part
```
**Mutations:**
- change one `fits` to `@min-[50rem]` → the first pin fails;
- put `min-w-[52rem]` back in the tracker's `className` → the second pin fails;
- drop `[&_th]:bg-background` → the fourth pin fails.

### Existing pins affected
None. No existing test reads `components/ui/table.tsx` (grep of `backend/tests`).

### Browser checks: see B12, rows 1-7.

---

## B4. `TableFrame` clips without becoming a scroller

### Current code (`components/empty-state.tsx:61-78`)
```tsx
export function TableFrame({ … }) {
  return (
    <div
      className={cn(
        "animate-fade-rise overflow-hidden rounded-xl border",
        className,
      )}
    >
```
### New code
```tsx
export function TableFrame({ … }) {
  return (
    <div
      className={cn(
        // clip, not hidden: both round the corners, but `hidden` makes a
        // scroll container, and a sticky header inside one sticks to it and
        // never moves. `clip` makes none, so the header sticks to the window.
        "animate-fade-rise overflow-clip rounded-xl border",
        className,
      )}
    >
```
Notes:
- **Stacking.** `animate-fade-rise` leaves a `translateY(0)` (fill-mode `both`), so the frame is a stacking context
  at z auto. The header's `z-10` stays inside it, above the rows, and the toolbar's `z-30` outside it wins.
- **Reduced motion.** `.animate-fade-rise { animation: none }` (`globals.css:252-266`) removes the transform. The
  header then stacks in the page context at z-10, still above the unpositioned rows and still under the toolbar.
- **`Card` keeps `overflow-hidden`** (`components/ui/card.tsx:17`), so a table inside a Card cannot stick. That is
  recorded in the convention (B11). No qualifying table sits in a Card.

### Pin
```python
def test_the_table_frame_clips_without_becoming_a_scroller():
    frame = _body(_read("components/empty-state.tsx"), "export function TableFrame(")
    assert '"animate-fade-rise overflow-clip rounded-xl border"' in frame
    assert "overflow-hidden" not in frame
```
**Mutation:** revert to `overflow-hidden` and the pin fails. B12 row 1 then shows the header scrolling away at 1280.

---

## B5. `ListToolbar`, the `tall:` variant, and focus clearance

### New file `frontend/components/list-toolbar.tsx`
```tsx
"use client";

import { useEffect, useRef, type ReactNode } from "react";

import { cn } from "@/lib/utils";

/** The `tall:` variant's query (app/globals.css). Below it nothing sticks. */
export const TALL_QUERY = "(min-height: 40rem)";
/** Read by a sticky TableHeader's `top` and by html's scroll-padding-top. */
const STICKY_TOP_VAR = "--list-sticky-top";

/**
 * The search, filter and sort controls above a long list. The toolbar sticks
 * to the top of the window while the list scrolls under it, and a sticky
 * table header (`<Table stickyHeader>`) sticks right under it.
 *
 * The header cannot know the toolbar's height (it wraps at narrow widths, and
 * a filter label carries a count), so the toolbar measures itself and
 * publishes the height as `--list-sticky-top` on <html>. It goes on <html>
 * and not on a wrapper because html's `scroll-padding-top` reads it too:
 * that is what keeps a focused row from landing under the stuck chrome
 * (WCAG 2.4.11, technique C43).
 *
 * One per page. Nothing sticks below `TALL_QUERY`: on a landscape phone or at
 * high zoom, the stuck chrome would take too much of the screen (WCAG 1.4.10).
 */
export function ListToolbar({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const root = document.documentElement;
    const tall = window.matchMedia(TALL_QUERY);
    let written = "";
    const write = () => {
      // floor, not ceil: a header placed a fraction of a pixel too HIGH
      // tucks under the toolbar (z-30 over z-10); too LOW leaves a slit
      // that rows show through.
      written = tall.matches
        ? `${Math.floor(el.getBoundingClientRect().height)}px`
        : "0px";
      root.style.setProperty(STICKY_TOP_VAR, written);
    };
    write();
    const observer = new ResizeObserver(write);
    observer.observe(el);
    tall.addEventListener("change", write);
    return () => {
      observer.disconnect();
      tall.removeEventListener("change", write);
      // Only our own value: a list page that mounted before this one
      // unmounted has written its own.
      if (root.style.getPropertyValue(STICKY_TOP_VAR) === written) root.style.removeProperty(STICKY_TOP_VAR);
    };
  }, []);
  return (
    <div
      ref={ref}
      data-slot="list-toolbar"
      className={cn(
        // -my-3 py-3: the same place in the flow, with 12px of page colour
        // above and below the controls once stuck. z-30: over a gallery
        // card's z-20 actions, under the fixed bulk bar (z-40) and every
        // portalled popup (z-50).
        "bg-background -my-3 flex flex-col gap-3 py-3 tall:sticky tall:top-0 tall:z-30 print:static",
        className,
      )}
    >
      {children}
    </div>
  );
}
```
Notes:
- **Not `role="toolbar"`.** That role promises arrow-key roving between controls. These controls are separate Tab
  stops (a text input, a Select, a segmented toggle). A `<search>` landmark would fit; see O6.
- **`tall:z-30`, not `z-30`.** The toolbar is a flex item of `PageShell`, and a flex item's `z-index` applies even
  when it is static. Gating it keeps an unstuck toolbar out of the stacking order.
- **The React Compiler rules are satisfied.** The effect reads `ref.current` in its body, never during render, and
  the callbacks only write a style property. There is no `setState`.

### `frontend/app/globals.css`
**Current** (`:5`, `:189-191`):
```css
@custom-variant dark (&:is(.dark *));
…
  html {
    @apply font-sans;
  }
```
**New:**
```css
@custom-variant dark (&:is(.dark *));
/* Sticky list chrome only where it can afford the room. Below 40rem of
   height (a landscape phone, 200% zoom on a laptop, 400% zoom anywhere), a
   stuck toolbar and header would take a third of the screen or more, and
   WCAG 1.4.10 wants that content to scroll. Mirrored by TALL_QUERY in
   components/list-toolbar.tsx and by the --list-head-h query below (pinned). */
@custom-variant tall (@media (min-height: 40rem));
…
  html {
    @apply font-sans;
    /* WCAG 2.4.11 (C43): a focus scrolled into view lands below the sticky
       list chrome, not under it. --list-sticky-top is ListToolbar's height,
       written by it while mounted; --list-head-h is a sticky table header's
       h-10 plus 0.5rem for the focus ring. Both unset: 0, the default. */
    scroll-padding-top: calc(var(--list-sticky-top, 0px) + var(--list-head-h, 0px));
  }
  @media (min-height: 40rem) {
    html:has([data-slot="table-header"][data-sticky]) {
      --list-head-h: 3rem;
    }
  }
```
Notes:
- **The `--list-head-h` rule also applies while the table is too narrow to stick** (CSS cannot see a container-query
  result from `<html>`). The only cost is 48px of extra clearance when focus scrolls on a narrow table.
- **With no list page mounted, the padding is 0.** No behaviour changes on other pages (the health report jump list,
  `useFocusSection`, anchors).
- **`next-themes` writes `color-scheme` to `<html>`'s inline style.** `setProperty` on a different property does not
  disturb it, and `<html>` already carries `suppressHydrationWarning` (`layout.tsx:38-40`).

### Pins
```python
def test_the_tall_threshold_is_one_number():
    css = re.search(r"@custom-variant tall \(@media (\(min-height: [\d.]+rem\))\);", _CSS)
    assert css, "the tall variant"
    ts = re.search(r'export const TALL_QUERY = "(\(min-height: [\d.]+rem\))";', _TOOLBAR)
    assert ts and ts.group(1) == css.group(1)
    head = re.search(
        r'@media (\(min-height: [\d.]+rem\)) \{\s*html:has\(\[data-slot="table-header"\]\[data-sticky\]\)',
        _CSS,
    )
    assert head and head.group(1) == css.group(1)


def test_the_toolbar_sticks_on_the_page_colour_above_the_list():
    for part in ("tall:sticky", "tall:top-0", "tall:z-30", "bg-background", "-my-3", "py-3", "print:static"):
        assert part in _TOOLBAR, part


def test_the_toolbar_publishes_its_height_and_takes_it_back():
    body = _body(_TOOLBAR, "export function ListToolbar(")
    assert 'const STICKY_TOP_VAR = "--list-sticky-top";' in _TOOLBAR
    assert "new ResizeObserver(write)" in body
    assert "window.matchMedia(TALL_QUERY)" in body
    assert 'tall.addEventListener("change", write)' in body
    assert "Math.floor(el.getBoundingClientRect().height)" in body
    assert "root.style.setProperty(STICKY_TOP_VAR, written)" in body
    cleanup = body[body.index("return () => {") :]
    assert "observer.disconnect()" in cleanup
    assert "=== written) root.style.removeProperty(STICKY_TOP_VAR)" in cleanup
    assert "--list-sticky-top" in _body(_TABLE, "function TableHeader(")


def test_focus_scrolled_into_view_clears_the_sticky_chrome():
    """WCAG 2.4.11 (C43). Browser-verified in Chromium: without it, Shift+Tab
    onto a row under a stuck header leaves that row under it."""
    html = _CSS[_CSS.index("  html {") :]
    html = html[: html.index("}")]
    assert "scroll-padding-top: calc(var(--list-sticky-top, 0px) + var(--list-head-h, 0px));" in html
    assert re.search(
        r'html:has\(\[data-slot="table-header"\]\[data-sticky\]\) \{\s*--list-head-h: 3rem;', _CSS
    )
```
**Mutations:**
- delete the `scroll-padding-top` line → the last pin fails (and B12 row 5 fails in the browser);
- change `TALL_QUERY` to `36rem` → the first pin fails;
- drop the `=== written` guard → the third pin fails.

### Contingency: only if B12 row 5 fails in WebKit
WebKit may not honour `scroll-padding` when sequential focus navigation scrolls. If so, add this to `ListToolbar`'s
effect (and the same four lines to a `useLayoutEffect` in `Table` when `sticky`, for Referrals, which has no
toolbar). Keep the CSS: Chromium and Firefox use it.
```ts
const onFocusIn = (e: FocusEvent) => {
  const t = e.target;
  if (!(t instanceof HTMLElement) || el.contains(t)) return;
  requestAnimationFrame(() => {
    const clear = parseFloat(getComputedStyle(root).scrollPaddingTop) || 0;
    const top = t.getBoundingClientRect().top;
    if (top < clear) window.scrollBy({ top: top - clear });
  });
};
document.addEventListener("focusin", onFocusIn);
// cleanup: document.removeEventListener("focusin", onFocusIn);
```

---

## B6. Applications adopts the toolbar and the sticky header

### Current code
`app/applications/page.tsx:417-473` (the toolbar):
```tsx
      <div className="flex flex-col gap-3">
        <div className="relative w-full max-w-sm">
          <Search … />
          <Input aria-label="Search applications" … />
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Select value={filter} …> … </Select>
          <SourceToggle className="ml-auto" value={source} onChange={setSourceAndUrl} />
        </div>
      </div>
```
`:532-541` (the table):
```tsx
        <TableFrame>
          {/* min-w engages Table's own overflow-x-auto container. Without it the
              table shrinks to whatever width is left — 462px at 768px, where the
              sidebar has not yet collapsed — and because the layout is fixed the
              status chip cannot widen its column, so it paints over the Applied
              date instead. */}
          <Table className="min-w-[52rem] table-fixed">
            <TableHeader>
```
### New code
```tsx
import { ListToolbar } from "@/components/list-toolbar";
…
      <ListToolbar>
        <div className="relative w-full max-w-sm">
          {/* unchanged */}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {/* unchanged */}
        </div>
      </ListToolbar>
…
        <TableFrame>
          {/* minWidth engages Table's own overflow-x-auto container. Without
              it the table shrinks to whatever width is left (462px at 768px,
              where the sidebar has not yet collapsed), and because the layout
              is fixed the status chip cannot widen its column, so it paints
              over the Applied date instead. It is also the width the header
              sticks from: a table wider than its frame scrolls sideways, and
              then its header cannot stick to the window. */}
          <Table minWidth="52rem" stickyHeader className="table-fixed">
            <TableHeader>
```
Notes:
- **The toolbar stays a direct child of `PageShell`'s `<main>`.** Its sticky range is the whole page body, and it
  stays stuck down to the cap notice (B10).
- **Unstuck spacing is unchanged.** PageHeader to toolbar is still 24px (`gap-6` minus 12px margin, plus 12px
  padding), and so is toolbar to table.
- **The `TableRow className="hover:bg-transparent"` header row stays.** Its hover is transparent over the opaque
  `th` cells.
- **The em dashes in the old comment go.** They are prose (the conventions' em-dash rule is for UI copy, but the
  rewrite is free).

### Pin
```python
def test_the_tracker_toolbar_and_header_stick():
    assert "<ListToolbar>" in _TRACKER
    # A direct child of the page's <main>: no wrapper that could scroll or end early.
    shell = _TRACKER[_TRACKER.index("<PageShell>") : _TRACKER.index("<ListToolbar>")]
    assert "<div" not in shell
    assert '<Table minWidth="52rem" stickyHeader className="table-fixed">' in _TRACKER
```
**Mutation:** wrap the toolbar in a `<div>` and the pin fails.

### Existing pins affected (all still pass; re-run them)
- `test_frontend_placeholders.py:40`: `"Search company or role…"` is unchanged.
- `test_frontend_first_run.py:17-30`: slices from `filtered.length === 0 ?` and from `actions={` to `<Link href="/new">`.
  Both are unchanged.
- `test_frontend_query_error_states.py:280`: `loadFailed ? (` still precedes `animate-shimmer h-12`.
- `test_frontend_plain_words.py:127-129`: the Base cell is unchanged.

---

## B7. Referrals: header only

### Current code (`app/referrals/page.tsx:325-327`)
```tsx
      <TableFrame>
        <Table className="min-w-[48rem] table-fixed">
          <TableHeader>
```
### New code
```tsx
      <TableFrame>
        <Table minWidth="48rem" stickyHeader className="table-fixed">
          <TableHeader>
```
Notes:
- **No toolbar, so `--list-sticky-top` is unset and the header sticks at the window's top.**
- **An edit row is taller** (inputs plus a two-line textarea, `:506-568`). Tabbing into its fields under a stuck
  header is covered by the scroll padding (`--list-head-h`).
- **`useFocusHandoff(rootRef)`'s wrapper** (`:322-324`, `tabIndex={-1} outline-none`) sets no overflow, so it does
  not break sticking.

### Pin
```python
def test_referrals_header_sticks():
    assert '<Table minWidth="48rem" stickyHeader className="table-fixed">' in _REFERRALS
```
### Existing pins affected
None. `test_frontend_referrals.py` pins the header action and focus, not table classes.

---

## B8. Agent inbox: the contract for the Agent inbox appendix

That appendix owns `components/proposals/proposals-section.tsx` and replaces the labelled Selects (`:413-485`) with an
Applications-style toolbar. To get the sticky behaviour and the cap notice, it:

1. **Wraps the new toolbar in `<ListToolbar>`,** as a direct child of the section's root
   `<div className="flex flex-col gap-6 pb-20">` (`:411-412`). Never put it inside a `Lane`: `Lane` is
   `overflow-x-auto` (`:693`), a scroll container. `FunnelStrip` above it scrolls away. `BulkBar` is fixed at z-40
   (`triage-actions.tsx:233`) and cannot collide with the toolbar's z-30 at the top edge.
2. **Adds no table,** so there is no header offset. `--list-sticky-top` (the toolbar's height, including its 12px
   bottom padding) is the whole focus clearance.
3. **Names its limit once and uses the server's total:**
   ```tsx
   // The API's max page (routers/proposals.py: le=500); `total` counts them all.
   const PROPOSALS_LIMIT = 500;
   …
   queryFn: () => apiFetch<ProposalListResponse>(`/api/proposals?limit=${PROPOSALS_LIMIT}`),
   …
   // last child before <BulkBar>, after the History section:
   <ListCapNotice loaded={items.length} limit={PROPOSALS_LIMIT} total={data?.total} noun="proposals" />
   ```
   With `total`, `isListCapped` is exact (`total > loaded`). The notice then reads, for example: "Only the 500 most
   recent of your 812 proposals are loaded, so older ones don't appear in this list."
4. **Pins, which land with that task in `test_frontend_sticky_lists.py`:**
   ```python
   def test_the_inbox_toolbar_sticks_and_its_cap_uses_the_server_total():
       src = _read("components/proposals/proposals-section.tsx")
       assert "<ListToolbar>" in src
       lane = _body(src, "function Lane(")
       assert "ListToolbar" not in lane
       assert "/api/proposals?limit=${PROPOSALS_LIMIT}" in src and "limit=500" not in src
       assert "total={data?.total}" in src and 'noun="proposals"' in src
   ```

---

## B9. `ListCapNotice` and its words (`lib/list-cap.ts`)

### Backend facts (at `8cac7cf9`)
| Endpoint | Frontend call | `limit` default / max | Total in the response? |
|---|---|---|---|
| `GET /api/applications` (`routers/applications.py:168-209`) | `?limit=500` (`page.tsx:191`) | 100 / 500 (`:178`) | **no**: bare `list[ApplicationSummary]` |
| `GET /api/jobs` (`routers/jobs.py:307-333`) | `?without_application=true&limit=500` (`page.tsx:195`) | 100 / 500 (`:310`) | **no**: bare `list[JobSummary]` |
| `GET /api/proposals` (`routers/proposals.py:178-214`) | `?limit=500` (`proposals-section.tsx:192`) | 500 / 500 (`:182`) | **yes**: `total` = count before offset/limit (`:190`) |

A count of applications does exist elsewhere: `GET /api/explore/activity` → `totals.applications`
(`services/explore_activity.py:102, 123-124`). It is an analytics call that also computes series. There is none for
saved jobs. Adding a third query to the tracker for half an answer is not cheap. So **Applications says "Showing
your 500 most recent", with no total.** O3 covers an additive `X-Total-Count` header if the owner wants "500 of 812".

### New file `frontend/lib/list-cap.ts`
```ts
/**
 * A list fetched with `?limit=`: how many rows came back, the limit asked
 * for, what they are, and the server's count of all of them when the
 * endpoint reports one (`/api/proposals` does; `/api/applications` and
 * `/api/jobs` return a bare array).
 */
export type ListCap = {
  loaded: number;
  limit: number;
  /** Plural, lower case: "applications", "saved jobs", "proposals". */
  noun: string;
  total?: number | null;
};

/**
 * Whether older rows may be missing. With a total, the answer is exact.
 * Without one, a full page counts as capped: a list of exactly `limit` rows
 * reads as capped too, and the sentence below stays true for it.
 */
export function isListCapped({ loaded, limit, total }: ListCap): boolean {
  return total != null ? total > loaded : loaded >= limit;
}

/**
 * The notice, or null when nothing was left out. It speaks of what is
 * LOADED, not what is shown, so it stays true under any filter or search,
 * and when a filter shows nothing.
 */
export function listCapSentence(cap: ListCap): string | null {
  if (!isListCapped(cap)) return null;
  const loaded = cap.loaded.toLocaleString("en-US");
  const tail = "so older ones don't appear in this list.";
  return cap.total != null
    ? `Only the ${loaded} most recent of your ${cap.total.toLocaleString("en-US")} ${cap.noun} are loaded, ${tail}`
    : `Only your ${loaded} most recent ${cap.noun} are loaded, ${tail}`;
}
```
**Copy notes.** The owner will tighten the copy later. The draft keeps these properties:
- one sentence;
- it names the number;
- it says "loaded", not "showing", because "Showing your 500…" is false under a filter that shows 12;
- "in this list" covers the filters and the search;
- no em dash (conventions, Microcopy rules), and a straight apostrophe like the rest of the app ("Couldn't load…").

### New file `frontend/lib/list-cap.test.ts`
```ts
import assert from "node:assert/strict";
import { test } from "node:test";

import { isListCapped, listCapSentence } from "./list-cap.ts";

test("without a total, a full page reads as capped", () => {
  assert.equal(isListCapped({ loaded: 500, limit: 500, noun: "applications" }), true);
  assert.equal(isListCapped({ loaded: 499, limit: 500, noun: "applications" }), false);
  assert.equal(isListCapped({ loaded: 0, limit: 500, noun: "applications" }), false);
});

test("a server total makes the check exact", () => {
  assert.equal(isListCapped({ loaded: 500, limit: 500, noun: "proposals", total: 500 }), false);
  assert.equal(isListCapped({ loaded: 500, limit: 500, noun: "proposals", total: 812 }), true);
  assert.equal(isListCapped({ loaded: 12, limit: 500, noun: "proposals", total: 12 }), false);
  assert.equal(isListCapped({ loaded: 12, limit: 500, noun: "proposals", total: null }), false);
});

test("the sentence names what is loaded, not what is shown", () => {
  assert.equal(
    listCapSentence({ loaded: 500, limit: 500, noun: "applications" }),
    "Only your 500 most recent applications are loaded, so older ones don't appear in this list.",
  );
  assert.equal(
    listCapSentence({ loaded: 500, limit: 500, noun: "proposals", total: 1234 }),
    "Only the 500 most recent of your 1,234 proposals are loaded, so older ones don't appear in this list.",
  );
  assert.equal(listCapSentence({ loaded: 20, limit: 500, noun: "applications" }), null);
});
```

### New file `frontend/components/list-cap-notice.tsx`
```tsx
import { Info } from "lucide-react";

import { listCapSentence, type ListCap } from "@/lib/list-cap";
import { cn } from "@/lib/utils";

/**
 * The last line of a list fetched with a row limit, when the limit was hit:
 * say that older rows were left out instead of dropping them silently.
 *
 * Plain text, not a live region: it is there on arrival, not news, and a
 * status role would be announced on every load. Screen readers reach it in
 * reading order, after the list. Renders nothing when the list is whole.
 * The inbox passes the server's `total`; the tracker has none.
 */
export function ListCapNotice({ className, ...cap }: ListCap & { className?: string }) {
  const sentence = listCapSentence(cap);
  if (!sentence) return null;
  return (
    <p
      data-slot="list-cap-notice"
      className={cn("text-muted-foreground flex items-start gap-2 text-sm", className)}
    >
      <Info className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <span>{sentence}</span>
    </p>
  );
}
```
`text-muted-foreground` on `--background` meets 4.5:1 in both themes. It is already pinned by
`test_frontend_color_roles.py`.

### Pins
```python
def test_the_cap_rule_is_pure_and_exact_when_the_server_counts():
    src = _read("lib/list-cap.ts")
    assert "import " not in src  # node --test runs it as-is (appendix F finding 7)
    assert "return total != null ? total > loaded : loaded >= limit;" in src
    assert (_FRONTEND / "lib/list-cap.test.ts").is_file()


def test_the_notice_is_plain_text_not_a_live_region():
    src = _read("components/list-cap-notice.tsx")
    assert "listCapSentence(cap)" in src and "<p" in src
    assert "role=" not in src and "aria-live" not in src
```
**Mutations:**
- `loaded > limit` → the node test fails at 500/500;
- add `role="status"` → the second pin fails.

---

## B10. Applications ends a capped list with the notice

### Current code (`app/applications/page.tsx:187-196`, `:701-705`)
```tsx
  const apps = useQuery({
    queryKey: ["applications"],
    queryFn: () => apiFetch<ApplicationSummary[]>("/api/applications?limit=500"),
  });
  const savedJobs = useQuery({
    queryKey: ["jobs", "without-application"],
    queryFn: () => apiFetch<Job[]>("/api/jobs?without_application=true&limit=500"),
  });
…
          </Table>
        </TableFrame>
      )}
    </PageShell>
```
### New code
Module level, beside `SEQUENCE_STORE_KEY` (`:114`):
```tsx
// The API's max page (routers/applications.py, routers/jobs.py: le=500).
// Older rows are not loaded; the list says so at its end (ListCapNotice).
const LIST_LIMIT = 500;
```
The queries:
```tsx
  const apps = useQuery({
    queryKey: ["applications"],
    queryFn: () => apiFetch<ApplicationSummary[]>(`/api/applications?limit=${LIST_LIMIT}`),
  });
  const savedJobs = useQuery({
    queryKey: ["jobs", "without-application"],
    queryFn: () => apiFetch<Job[]>(`/api/jobs?without_application=true&limit=${LIST_LIMIT}`),
  });
```
After `loadFailed` (`:333`):
```tsx
  // What was LOADED hit the cap, whatever the filter, search or source shows:
  // the notice is about the fetch, so it stays true under all of them.
  const caps = [
    { loaded: apps.data?.length ?? 0, limit: LIST_LIMIT, noun: "applications" },
    { loaded: savedJobs.data?.length ?? 0, limit: LIST_LIMIT, noun: "saved jobs" },
  ].filter(isListCapped);
```
The last child of `PageShell`, after the result ternary:
```tsx
          </Table>
        </TableFrame>
      )}

      {!loading && !loadFailed && caps.length > 0 ? (
        <div className="flex flex-col gap-1">
          {caps.map((cap) => (
            <ListCapNotice key={cap.noun} {...cap} />
          ))}
        </div>
      ) : null}
    </PageShell>
```
Imports: `import { ListCapNotice } from "@/components/list-cap-notice";` and
`import { isListCapped } from "@/lib/list-cap";`.

**Cases:**

| State | Rendered at the end |
|---|---|
| Loading, or load failed | nothing (the gate) |
| Neither list full | nothing (`caps` is empty, so there is no empty `div` and no stray `gap-6`) |
| Only applications at 500 | "Only your 500 most recent applications are loaded, so older ones don't appear in this list." |
| Only saved jobs at 500 | "Only your 500 most recent saved jobs are loaded, so older ones don't appear in this list." |
| Both | both lines, `gap-1` apart |
| A filter or search is active, rows shown | same lines (they speak of the fetch) |
| A filter or search shows nothing | `EmptyState` "Nothing matches this filter", then the lines. This is where the notice matters most: the job may be one of the older ones. |
| `allRows.length === 0` (new user) | cannot be capped, so nothing |
| Source toggle `You` with saved jobs at 500 | the saved-jobs line still shows: the 500 include agent captures that the toggle hides (O4) |

The job page's prev/next sequence (`SEQUENCE_STORE_KEY`, `:357-365`) walks only loaded rows, as before.

### Pins
```python
def _backend_max(rel: str, fn: str) -> int:
    src = (_ROOT / "backend" / rel).read_text(encoding="utf-8")
    body = src[src.index(f"def {fn}(") :]
    return int(re.search(r"limit: Annotated\[int, Query\(ge=1, le=(\d+)\)\]", body).group(1))


def test_the_tracker_asks_for_one_limit_the_api_accepts():
    m = re.search(r"^const LIST_LIMIT = (\d+);", _TRACKER, re.M)
    assert m, "LIST_LIMIT"
    limit = int(m.group(1))
    # Above the API's max, the request is a 422 and the tracker shows its error.
    assert limit <= _backend_max("app/routers/applications.py", "list_applications")
    assert limit <= _backend_max("app/routers/jobs.py", "list_jobs")
    assert "/api/applications?limit=${LIST_LIMIT}" in _TRACKER
    assert "/api/jobs?without_application=true&limit=${LIST_LIMIT}" in _TRACKER
    assert "limit=500" not in _TRACKER


def test_a_capped_tracker_says_so_at_the_end_of_the_list():
    assert "<ListCapNotice" in _TRACKER[_TRACKER.index("</TableFrame>") :]
    gate = _TRACKER[_TRACKER.index("{!loading && !loadFailed && caps.length > 0 ? (") :]
    assert gate.index("<ListCapNotice") < gate.index("</PageShell>")
    caps = _TRACKER[_TRACKER.index("const caps = [") :]
    caps = caps[: caps.index("].filter(isListCapped);")]
    # What is LOADED, before any filter: never `filtered` or `sourceScopedRows`.
    assert "apps.data?.length ?? 0" in caps and "savedJobs.data?.length ?? 0" in caps
    assert "filtered" not in caps and "sourceScoped" not in caps
```
**Mutations:**
- count `filtered.length` → the second pin fails;
- set `LIST_LIMIT = 600` → the first pin fails (the API would answer 422).

### Existing pins affected
`test_frontend_query_error_states.py:234` pins `const loadFailed = isLoadFailure(apps) || isLoadFailure(savedJobs);`
verbatim. That line is unchanged, and `caps` goes after it.

---

## B11. Conventions and docs

### `docs/frontend-conventions.md`
**1. New bullet**, after "The 768–1023px band" (`:494-503`):

> - **Long lists keep their controls and column names in view** (`components/list-toolbar.tsx`,
>   `<Table minWidth stickyHeader>`). A list page whose list can outgrow the window does two things:
>   - it puts its search/filter/sort row in `ListToolbar` (one per page, a direct child of `PageShell`);
>   - it gives its table a `minWidth` from `MIN_WIDTH` plus `stickyHeader`.
>
>   The toolbar sticks to the window's top on the page colour. It publishes its height as `--list-sticky-top` on
>   `<html>`, and the header sticks right under it.
>   **The window is the only scroller.** `SidebarInset`, `SidebarGutter`, `PageShell`, and every element between a
>   sticky element and `<html>`, stay `overflow: visible`. A frame that clips rounded corners uses `overflow-clip`,
>   never `overflow-hidden`: `hidden` is a scroll container, so a sticky child sticks to it and never moves.
>   `TableFrame` is `clip`. `Card` is still `hidden`, so a table in a card does not stick. `stickyHeader` also needs
>   a parent that gives the width (inline-size containment).
>   **A header sticks only while its table fits.** Sideways scrolling and window stickiness cannot share a box, so
>   below its `minWidth` (the `@min-[…]/table` container query) the table scrolls sideways and the header scrolls
>   away; the toolbar still sticks. Applications: both stick at 1280 with the sidebar pinned, and only the toolbar at
>   1024 pinned, 768 and 375.
>   **Nothing sticks below 40rem of height** (`tall:`: landscape phones, 200–400% zoom; WCAG 1.4.10).
>   **Focus is never hidden under it.** `html` carries `scroll-padding-top` from the same variables (WCAG 2.4.11,
>   C43). A new sticky element adds its height there.
>   **Stacking and offsets:**
>   - the toolbar is z-30, over a gallery card's z-20 actions;
>   - the header is z-10 inside its table;
>   - menus and popovers portal at z-50;
>   - the reveal pill is z-50 but sits in the gutter.
>
>   The offsets start at `top: 0` because nothing above a page sticks (`VersionBanner` scrolls away, and there is no
>   mobile header). A sticky banner added later must add its height to `--list-sticky-top`.
>   **Print:** both are `print:static`.
>   Pinned by `test_frontend_sticky_lists.py`.
>
> - **A capped list says so at its end** (`components/list-cap-notice.tsx`; the words and the rule are in
>   `lib/list-cap.ts`). A list fetched with `?limit=` ends with `ListCapNotice` when the fetch came back full, and
>   passes the server's `total` when the endpoint reports one (proposals does; applications and jobs do not, so
>   those never print an invented count).
>   - The sentence speaks of what is LOADED, so it stays true under any filter or search, and it still shows under a
>     filtered empty state.
>   - It is plain text, not a live region.
>   - The limit is one named constant per page, at most the API's `le=` (pinned).

**2. Edit** "The 768–1023px band" (`:498-499`): "The Applications table carries `min-w-[52rem]` because…" becomes
"The Applications table carries `minWidth="52rem"` because…".

### `SYSTEM.md` (docs sweep; SYSTEM.md is at 1000/1000)
- §11 item 5 (`:770`): "Server-side pagination for the tracker (client caps at limit=500 today)." becomes
  "Server-side pagination for the tracker (client caps at 500 rows and says so)." The line count is the same.
- No §12 entry. The gotchas (a scroll container breaks sticky; `overflow-clip` versus `hidden`) live in the
  conventions bullet beside the rule they explain.

---

## B12. Browser checks

**Setup.**
- Use a throwaway stack (the worktree verification recipe) with **at least 40 tracker rows and 25 referrals**, so
  every list outgrows the window. The cap cases use Playwright route mocking (row 10), not 500 real rows.
- Run every row in **light and dark**, in **Chromium and WebKit**.
- Viewports: 1280×800 (sidebar pinned), 1024×768 (pinned, then collapsed with Cmd/Ctrl+B), 768×1024, and 375×812
  (the `mobile` preset).

| # | Where | Steps | Expected |
|---|---|---|---|
| 1 | `/applications` 1280×800 | Scroll 1000px. Read `thead.getBoundingClientRect().top` and `[data-slot=list-toolbar]` `.bottom`. | Toolbar top is 0. The header top equals the toolbar bottom (within 1px). The header is `position: sticky` and the container `overflow-x: clip`. Header cells are opaque (hover a row under the header: no tint shows through). The 1px rule under the header stays visible. The frame keeps its rounded top and bottom corners. |
| 2 | same | Keep scrolling to the end. | The header un-sticks at the table's end (the table is its containing block). The toolbar stays stuck over the gap and the cap notice (row 10). There is no page sideways scroll (`document.documentElement.scrollWidth <= innerWidth`). |
| 3 | `/applications` at 1024×768 pinned, 768×1024, 375×812 | Scroll 1000px, then scroll the table sideways. | The toolbar sticks. The header is `static` and scrolls away. `[data-slot=table-container]` scrolls sideways (`scrollWidth > clientWidth`). No page sideways scroll. At 375 the toolbar wraps to two filter lines (about 146px) and still sticks (812 ≥ 640). The reveal pill (12–40px) does not overlap the toolbar, which starts at x ≥ 80px. |
| 4 | `/applications` 1024×768 | Collapse the sidebar with Cmd/Ctrl+B, scroll. | The header now sticks (frame 918px ≥ 832px): the container query reacts without a reload. Expanding the sidebar again un-sticks it. |
| 5 | Focus, 1280×800 | Scroll so row N+1 sits just under the header, focus it with `preventScroll`, press a real **Shift+Tab**. Then Tab forward through 30 rows' controls (row link, status chip, ⋯) from the toolbar. | The focused element's top is always ≥ the header's bottom, and its focus ring shows in full. **WebKit:** if this fails, apply the B5 contingency and re-run. Repeat on `/referrals` (header only) and on the inbox (toolbar only) once that appendix lands. |
| 6 | Menus, 1280×800 | While stuck: open the status filter `Select` in the toolbar, a row's ⋯ menu and a row's `StatusChip` menu for a row just under the header (keyboard: Enter on the trigger). Scroll near the bottom and open a ⋯ menu that flips upward over the header. | Every popup paints above the toolbar and header (`document.elementFromPoint` at the popup's centre is inside the popup). The page does not scroll while a modal menu is open. Closing returns focus to its trigger, fully visible. |
| 7 | Dark mode, row 1 | Compare `getComputedStyle(th).backgroundColor` and the toolbar's with `getComputedStyle(document.body).backgroundColor`. | All equal (`--background`). The header rule uses the dark `--border`. |
| 8 | Short viewport 1280×560 | Scroll. Read the `--list-sticky-top` and `scroll-padding-top` of `document.documentElement`. | Nothing sticks. `--list-sticky-top` is `0px`, scroll-padding is `0px`. Resize to 800 tall without reloading: both stick again and the variable updates (the `matchMedia` listener). |
| 9 | `/referrals` 1280×800 | Scroll. Tab into a row's Edit, then through its inputs. | The header sticks at top 0 (no toolbar). Inputs never land under it. Save and Cancel return focus as `test_frontend_referrals.py` expects. |
| 10 | The cap notice (Playwright) | Route `**/api/applications?limit=500**` to the real response padded to 500 rows (clone rows with new `id`s). Then pad `**/api/jobs?without_application=true&limit=500**` the same way. Then both. Then filter to a status with 0 rows, search "zzz", switch the source toggle, return 499 rows, force an error, and delay the response (loading). | 500 apps: only the applications line. 500 jobs: only the saved-jobs line. Both: two lines, `gap-1`. Filtered empty: `EmptyState`, then the line or lines. Search, filter and source change nothing about the lines. 499: nothing. Error or loading: nothing. VoiceOver/NVDA read it after the table, not on load. |
| 11 | `VersionBanner` shown | Route `**/api/version` to a different version, then scroll `/applications`. | The banner scrolls away with the page. The toolbar sticks at 0 with no gap above it. |
| 12 | Print | `page.emulateMedia({ media: "print" })` after scrolling to the middle. | The toolbar and header are `static` (no stray bar mid-page). |
| 13 | Reduced motion | Emulate `prefers-reduced-motion: reduce` and repeat row 1. | Same result. The header is still over the rows and under the toolbar (the frame has no transform now). |
| 14 | Route change | From `/applications` (scrolled), go to `/templates`, then `/career`. | `--list-sticky-top` is removed from `<html>` (inline style has no such property), and scroll-padding is `0px` on those pages. |

---

## Risks

- **WebKit is unverified.** The desktop shell is WebKit. The scratch-page proof ran in Chromium only. Three things
  to confirm there:
  - that `scroll-padding` is honoured on sequential focus navigation (B5 has a contingency);
  - sticky `thead` with an inset-shadow rule;
  - `overflow: clip` with `border-radius` (Safari 16+).
- **No sticky header in the 720–830px frame band.** That band is 1024 with the sidebar pinned, plus 768 and 375.
  The toolbar still sticks. O1 is the only cheap widening.
- **A global CSS variable on `<html>`.** The owner-token cleanup covers overlapping mounts. Two `ListToolbar`s on one
  page would fight (last writer wins); the convention says one per page.
- **`stickyHeader` adds inline-size containment.** In a shrink-to-fit parent (an `inline-flex` item, a `w-fit`
  popover) the table would collapse to zero width. The only call sites are block frames; the convention says so.
- **`overflow-x: clip` at wide widths clips content that overflows a cell.** That is what `TableFrame`'s
  `overflow-hidden` already did, so nothing visible changes.
- **The toolbar's height.** At 1280 the stuck chrome is about 108px + 40px (18.5% of 800). At 375 it is about 146px
  (18% of 812), with no header. Below 640px of height nothing sticks.
- **Find-in-page (Cmd+F) can scroll a match under the stuck chrome** in some engines. That is not keyboard focus
  (2.4.11 does not apply), but it is worth a glance in row 5.
- **The applications notice cannot tell "exactly 500" from "more than 500".** The words stay true (O2).
- **Sort headers are click-only.** They are `TableHead` with `onClick` (`page.tsx:367-391`), not keyboard-operable
  (WCAG 2.1.1). Sticking makes them more visible, not less reachable. See "Seen nearby".

---

## Suggested task split and file ownership

| Task | Sections | Files (owner) | Size | Depends on |
|---|---|---|---|---|
| **B-T1 Sticky primitives** | B2, B3, B4, B5 | `frontend/components/ui/table.tsx`; `frontend/components/empty-state.tsx` (`TableFrame` only); new `frontend/components/list-toolbar.tsx`; `frontend/app/globals.css` (`:5`, `:189-191`); new `backend/tests/test_frontend_sticky_lists.py` (B2-B5 pins) | M | none |
| **B-T2 Adopt on Applications and Referrals** | B6, B7 | `frontend/app/applications/page.tsx` (toolbar + `<Table>` only); `frontend/app/referrals/page.tsx` (`:326` only); pins appended to `test_frontend_sticky_lists.py` | S | B-T1 |
| **B-T3 Cap notice** | B9, B10 | new `frontend/lib/list-cap.ts`, `frontend/lib/list-cap.test.ts`, `frontend/components/list-cap-notice.tsx`; `frontend/app/applications/page.tsx` (queries, `caps`, the notice); pins appended | S | none (the code is independent), but it shares `applications/page.tsx` with B-T2, so run it in the **same lane after B-T2** |
| **B-T4 Docs** | B11 | `docs/frontend-conventions.md` (the two new bullets after `:494-503`, and the `:498-499` edit); SYSTEM.md §11 item 5 goes to the docs sweep | XS | B-T1–B-T3 |
| *Agent inbox appendix's task* | B8 | `frontend/components/proposals/proposals-section.tsx` is **owned by that appendix**. It imports `ListToolbar` and `ListCapNotice` and appends the B8 pin. | none here | B-T1 and B-T3 |

**Shared files:**
- `docs/frontend-conventions.md` is also edited by other appendices. Each adds its own bullets; this one touches only
  `:494-503` and after.
- `test_frontend_sticky_lists.py` is new and owned here. The inbox task appends one function to it.

---

## Open questions for the planner / owner

1. **O1. The narrow band.** Accept that the Applications and Referrals headers do not stick below their min width
   (recommended for now). The alternative is to hide the Base and Added columns under the same container query, so
   the tracker's min width drops to about 40rem and the header also sticks at 1024 with the sidebar pinned. That
   hides data at those widths, so it is a UX call. A bounded-height inner scroller (option B) is not recommended.
2. **O2. Exactly 500.** Accept "capped" wording at exactly 500 rows (recommended: the sentence stays true). The
   alternative probes `?limit=1&offset=500` once a list comes back full, which is exact and costs one tiny request,
   only at the cap.
3. **O3. Totals for the tracker.** Add an additive `X-Total-Count` response header to `GET /api/applications` and
   `GET /api/jobs` (MCP callers read the body only, so the contract is unchanged)? The notice could then say "500 of
   812". This is backend scope that this plan does not take by default.
4. **O4. Agent captures crowd out saved jobs.** The saved-jobs fetch counts agent-captured jobs, which the tracker
   hides unless the toggle is Agent (`page.tsx:253-259`). A busy hunt can push the user's own saved jobs past 500.
   Fetch the user's saved jobs separately (`&source=user`) and the agent's only for the Agent toggle?
5. **O5. A divider when stuck.** No divider on a stuck toolbar (recommended). Tables get the header's rule, and cards
   have their own ring. Otherwise, an `IntersectionObserver` sentinel could add a hairline only while stuck.
   (`scroll-state()` container queries would do it in CSS, but WebKit lacks them.)
6. **O6. A `<search>` landmark.** Render `ListToolbar` as `<search aria-label=…>` (HTML's element for "search or
   filtering" controls; typed in `@types/react`; Safari 17+)? It adds a landmark on each list page. Not required.
7. **O7. The inbox bulk bar hides focus from below.** `BulkBar` is `fixed bottom-0 z-40`
   (`triage-actions.tsx:233`) and can cover a focused row (WCAG 2.4.11). The same technique applies:
   `html:has([data-slot="bulk-bar"]) { scroll-padding-bottom: 5rem }`. This belongs to the Agent inbox appendix.
8. **O8. The KB draft inbox's silent cap.** `/api/kb/points?state=draft` uses the default `limit=500`. Reuse
   `ListCapNotice` there (one line), in this plan or later?
9. **O9. Referrals.** Referrals is included, header only, because it is cheap once B-T1 lands and the list has no
   limit. Drop it if the owner wants the first pass to be Applications and the inbox only.

## Seen nearby, not in scope

- **Sortable column headers are mouse-only.** `app/applications/page.tsx:367-391` puts `onClick` on the `<th>`, with
  no `<button>` and no key handler. A keyboard user cannot sort (WCAG 2.1.1). The usual fix is a `<button>` inside
  the `th`, keeping `aria-sort` on the `th`.
- **The Agent inbox day toggles** (`proposals-section.tsx:508-531`) and **the History toggle** (`:578-592`) are
  disclosure buttons with no `aria-expanded`.
- **`focusIfDropped` focuses with `preventScroll: true`** (`lib/focus.ts`). A handed-off focus target, such as the
  Referrals table wrapper after a delete, can sit above the viewport, off-screen rather than under sticky chrome.
- **SYSTEM.md §11 item 27** (`FullscreenEditorPage` is `h-dvh` under a showing `VersionBanner`) is the same banner.
  No list page is affected.
