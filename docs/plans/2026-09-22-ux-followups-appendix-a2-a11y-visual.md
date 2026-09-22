> **Appendix A2 (accessibility and visual consistency) to `docs/plans/2026-09-22-ux-followups.md`.** Research brief written read-only
> against `a3c800bb`; each task in the plan names the section it uses. Where this appendix offers
> options, the plan's "Owner decisions" section is binding. Line numbers drift: re-locate before editing.

# Implementation brief: Phase A2 (accessibility) + A3 (visual consistency)

Worktree `seinun-resume-update-45a8c0`, branch `claude/ux-followups` at `a3c800bb`. This is read-only research: no repo file was changed.
Paths are relative to `frontend/` unless they start with `backend/` or `docs/`.

**How the numbers were made.** Contrast values come from the OKLCH to sRGB to WCAG
arithmetic in `backend/tests/test_frontend_color_roles.py`, copied into a scratch script.
Alpha tints are composited in gamma sRGB, as the test and the browser do. The token values come from
`app/globals.css`. Some things were measured in the browser pane (Chrome 152) against the running `localhost:3000` stack,
with DOM-only experiments, nothing persisted, and the tab closed afterwards:
the UA focus outline (item 2), the template-editor scroll (item 6) and the 768px Contact overflow (item 7).
The code involved there is unchanged on this branch: `contact-form.tsx` is untouched since `e81696be`,
and the template page's `<main>` class matched.

## Suggested task grouping (for the plan)

| Task | Items | Files | Why grouped |
|---|---|---|---|
| T1 Tokens + pins | 2, 3 | `app/globals.css`, `backend/tests/test_frontend_color_roles.py` | Token-only, with no call-site changes. Everything later is measured against these values. |
| T2 Sidebar | 1, 9, 10 | `components/ui/sidebar.tsx`, `components/sidebar-reveal-trigger.tsx`, `components/app-sidebar.tsx`, `lib/nav.ts(+test)`, `backend/tests/test_frontend_sidebar_nav.py` | Same component and the same pin file. |
| T3 Storage hook + EditorShell | 12, 5, 4, 6 (edge rail) | new `hooks/use-local-storage-state.ts`, `lib/studio.ts(+test)`, `components/resume-editor/editor-shell.tsx`, `pdf-pages-preview.tsx`, `components/chat/chat-page.tsx` | Items 4, 5, 6 and 12 all rewrite the state block and the Splitter in `editor-shell.tsx`. Do them in one pass. |
| T4 Template editor height | 6 (page scroll) | `app/templates/[id]/page.tsx` | One-line wrapper swap. |
| T5 Contact grid | 7 | `components/resume-editor/contact-form.tsx` | Isolated. |
| T6 One selected-state rule | 8, 11 | `source-toggle.tsx`, `proposals/proposals-section.tsx`, `chat/chat-page.tsx`, `setup/setup-status-strip.tsx`, `charts/top-skills-chart.tsx`, + optional chips | Item 11 is solved by applying item 8's rule. |

Slop ratchet: frontend duplication sits at exactly 518/518. T3 removes three near-identical hydrate-effect blocks, so it should
lower the number. T6's chat change touches two identical "New chat" class strings (rail and sheet), so keep them
identical or extract the button. Run `slop_scan.py check frontend` after T3 and after T6.

---

## 1. The collapsed off-canvas sidebar stays in the Tab order

**Where:** `components/ui/sidebar.tsx:208-251`, the desktop branch of `Sidebar`.

```tsx
<div className="group peer hidden text-sidebar-foreground md:block" data-state={state}
     data-collapsible={state === "collapsed" ? collapsible : ""} ...>
  <div data-slot="sidebar-gap" .../>
  <div data-slot="sidebar-container" data-side={side}
       className={cn("fixed inset-y-0 z-10 hidden h-svh w-(--sidebar-width) ... data-[side=left]:group-data-[collapsible=offcanvas]:left-[calc(var(--sidebar-width)*-1)] ... md:flex", ...)}
       {...props}>
```

**Root cause.** Offcanvas collapse only moves the container to `left: -16rem`. It stays `display: flex` and
nothing removes it from the focus order, so the header toggle, the FAB, 8 nav links and 2 account links
(12 tab stops) are still tabbable while off screen. Below 768px the branch is not used: `isMobile` renders the
Base UI `Sheet`, and the desktop div is `hidden` there anyway.

**Fix (core).** React 19.2.4 and `@types/react` 19.2.14 type `inert?: boolean`. React 19 serializes `true` as `inert=""`
and omits the attribute when false. `inert` is already a keyed-on signal in this repo (`components/ui/tabs.tsx:94-99`).

```tsx
// in Sidebar, after the isMobile branch
// Off-canvas is only moved off screen, so without inert its links stay in
// the Tab order while invisible. Icon mode stays visible and operable.
const offcanvasHidden = collapsible === "offcanvas" && state === "collapsed"
...
<div
  data-slot="sidebar-container"
  data-side={side}
  inert={offcanvasHidden}
  className={cn(/* unchanged */)}
  {...props}
>
```

The following still work while the sidebar is inert:
- The reveal pill. It renders inside `SidebarInset`, not the sidebar (`app/layout.tsx:56-57`).
- Cmd/Ctrl+B. It is a `window` keydown listener (`sidebar.tsx:97-110`).
- The mobile sheet. It is a different branch.

**Fix (recommended companion): focus hand-off.** When focus is inside the sidebar at collapse, for example
Enter on the in-sidebar "Toggle sidebar" or Cmd+B from a nav link, `inert` drops it to `<body>`. The follow-ups
already name focus-to-`<body>` as a defect class. Put the hand-off in `components/sidebar-reveal-trigger.tsx`, which already
couples to the sidebar. It must fire on transitions only, never on first mount:

```tsx
export function SidebarRevealTrigger() {
  const hidden = useSidebarHidden();
  const { isMobile } = useSidebar();
  const mod = useModKey();
  const ref = useRef<HTMLButtonElement>(null);
  const was = useRef(hidden);
  useEffect(() => {
    if (was.current === hidden) return; // transitions only: never on page load
    was.current = hidden;
    if (isMobile) return; // the Sheet owns its own focus
    const active = document.activeElement;
    const orphaned = !active || active === document.body;
    if (hidden) {
      // The in-sidebar control that had focus just went inert.
      if (orphaned || active?.closest('[data-slot="sidebar-container"]')) ref.current?.focus();
    } else if (orphaned) {
      // The pill that had focus just unmounted.
      document
        .querySelector<HTMLElement>('[data-slot="sidebar-container"] [data-sidebar="trigger"]')
        ?.focus();
    }
  }, [hidden, isMobile]);
  if (!hidden) return null;
  return (/* unchanged, plus ref={ref} on SidebarTrigger (React 19: ref is a prop) */);
}
```

Cmd+B typed inside an editor field leaves `activeElement` on the field, so the caret is never stolen.

**Pins.** `backend/tests/test_frontend_sidebar_nav.py` reads `_UI` (only the cva string today) and `_REVEAL`. The existing
`test_sidebar_toggles_name_their_shortcut` needs `shortcutLabel(mod, "B")` and `aria-keyshortcuts` to stay in the reveal
file. Add `test_offcanvas_sidebar_is_inert_when_collapsed`: the slice of `_UI` between `data-slot="sidebar-container"` and
`data-slot="sidebar-inner"` contains `inert={offcanvasHidden}`.

**Risks.**
- Safari does not focus a button on mouse click, so a mouse collapse there finds `activeElement === body` and focuses the pill
  programmatically. The `:focus-visible` heuristic should not paint a ring after a pointer interaction, but check it once
  in the WebKit desktop shell.
- `SidebarRail` sets `tabIndex={-1}` and is not rendered by `AppSidebar`, so it is unaffected.

---

## 2. Light `--ring` is 2.52:1 on `--canvas` (WCAG 1.4.11)

**Where.**
- `app/globals.css:105` has `--ring: oklch(0.65 0.09 259);` for light and `:153` has `oklch(0.62 0.09 259)` for dark. `:126` and `:169` set `--sidebar-ring: var(--ring)`.
- `app/globals.css:180-182` has the base layer `* { @apply border-border outline-ring/50; }`.

**Current contrast of the solid ring** (the halo `ring-ring/50` is shown in brackets):

| surface | light now | dark now |
|---|---|---|
| background | 3.02 (1.66) | 5.42 (2.16) |
| card / white page | 3.24 (1.70) | 4.91 (2.16) |
| sidebar | 3.10 (1.67) | 4.91 (2.16) |
| **canvas** | **2.52** (1.54) | 5.58 (2.14) |
| muted | 2.72 (1.59) | 4.14 (2.05) |
| secondary-container (tonal, active nav) | 2.60 (1.56) | 3.35 (1.87) |
| formatting panel (`bg-background/60` over canvas) | 2.81 (1.61) | 5.49 (2.15) |

**Root cause (two parts).**
1. The light ring is too light for the darker surfaces this theme added: the page moved to 0.976 and the canvas is 0.915.
   It fails on canvas, muted and secondary container. Dark mode passes everywhere.
2. **A worse, unreported defect.** Every element that relies on the browser's own focus outline gets `outline-style: auto`
   in the `ring/50` colour. Chrome honours `outline-color` on `auto`: I verified this by recolouring the outline red, and it painted red.
   So those rings render at about 1.5 to 1.7:1. On a canvas-coloured probe the Tab-focused ring was practically invisible
   in the screenshot. Affected: every plain `<button>` or `<a>` with no focus classes, including all the canvas sites marked
   UA below, SourceToggle, the proposal filters, chat session rows, the formatting panel's segmented buttons, and both
   collapsed edge tabs.

**Fix.** Change the light token only and make the UA outline solid.

```css
/* :root */
--ring: oklch(0.57 0.11 259); /* #4e77b8; 3:1+ on every surface incl. --canvas */
/* .dark unchanged: oklch(0.62 0.09 259) */

@layer base { * { @apply border-border outline-ring; } }   /* was outline-ring/50 */
```

Light solid ring after the change:

| surface | contrast |
|---|---|
| background | 4.19 |
| card or white page | 4.49 |
| sidebar | 4.30 |
| **canvas** | **3.49** |
| muted | 3.76 |
| secondary-container | 3.60 |
| primary-container | 3.44 |
| formatting panel | 3.90 |

The value is in sRGB gamut and still clearly lighter than `--primary` (1.49:1 apart), so a focus ring stays distinct from
primary fills. The halo `ring-ring/50` rises to 1.77 on canvas and 1.90 on background. It stays decorative: the 1px
`focus-visible:border-ring` inside `buttonVariants` and `Input`, and the solid `ring-2` rings, carry the 3:1.

Rejected alternatives: L 0.60 gives canvas 3.08, too little margin; L 0.55 or darker starts to read as a primary border.
A canvas-only ring token was also rejected, because muted and secondary-container fail too.

**Every place a focus ring renders on canvas:**

| # | Site | Indicator | Surface |
|---|---|---|---|
| a | Preview header row inside the canvas pane (`editor-shell.tsx:153-180`): "Formatting" ghost Button (`:159-168`), "Hide PDF preview" ghost icon-sm (`:171-178`) | Button: 1px `border-ring` + `ring-3 ring-ring/50` | canvas |
| b | `previewHeader` contents on that row: base studio Download PDF and Open PDF in new tab (`editor-body.tsx:268-289`), tailored studio same (`tailored-resume-studio.tsx:634-655`) | Button | canvas |
| c | Template editor "Open PDF" plain `<a>` (`app/templates/[id]/page.tsx:334-341`) | **UA outline** | canvas |
| d | Formatting panel, open inside the pane on `bg-background/60` (`editor-shell.tsx:181-185`): segmented `<button>`s (`formatting-panel.tsx:148-161`, **UA outline**), Switch, Slider, Select, section-order `icon-xs` Buttons | mixed | bg/60 over canvas |
| e | Splitter (`editor-shell.tsx:269`): `focus-visible:ring-2 ring-ring`. The right half of the ring paints over the canvas pane | solid ring | background / canvas |
| f | Zoom presets (`pdf-pages-preview.tsx:105-119`): plain `<button>`s, **UA outline**, on the group's `bg-background`. Edge presets' outlines reach the group border next to canvas | UA | background / canvas |
| g | Page scroller focus overlay (`pdf-pages-preview.tsx:191-194`): `ring-ring ring-2 ring-inset`, over canvas and over the white page when scrolled | solid ring | canvas / white |
| h | The same f and g on the job page Resume tab (`components/application-panel.tsx:352`) and in the template editor preview | as above | canvas |
| i | If item 6's in-flow rail lands: the "Show PDF preview" rail button on `bg-canvas` | solid ring | canvas |

**Pins.** No test covers the ring today. Add these to `test_frontend_color_roles.py`:

```python
_RING_SURFACES = ("background", "card", "sidebar", "canvas", "muted", "secondary-container")

@pytest.mark.parametrize("mode", list(_MODES))
def test_focus_ring_meets_non_text_contrast(mode):
    t = _MODES[mode]
    for s in _RING_SURFACES:
        ratio = _contrast(_rgb(t, "ring"), _rgb(t, s))
        assert ratio >= 3.0, f"{mode}: --ring on --{s} is {ratio:.2f}:1"

def test_browser_focus_outline_is_the_solid_ring():
    # outline-style:auto paints in outline-color: ring/50 was ~1.6:1.
    assert "outline-ring/50" not in _CSS
```

`_tokens()` parses `oklch(0.57 0.11 259)` fine.

**Risks.**
- Every UA-outlined control that was effectively ring-less now shows a visible 1 to 2px blue ring. That is the point.
  Eyeball the zoom group and SourceToggle.
- Controls whose only indicator is translucent stay below 3:1 even after the change: `focus-within:ring-ring/50` in
  `role-picker.tsx:350`, `role-category-picker.tsx:149` and `ui/chip-input.tsx:105` (1.90), and `focus-visible:outline-ring/60`
  in `status-chip.tsx:66`, `career/points-list.tsx:368` and `career/entity-detail.tsx:417` (2.20). None of them are on canvas.
  Log them or fold them in by dropping the `/50` or `/60`.
- `docs/frontend-conventions.md:12-15` names "blue-tinted focus rings". Record the value and the canvas reason there.

---

## 3. `text-destructive` on `bg-destructive/N` (and plain on the page) fails AA in light mode

**Where.** `app/globals.css:102` has light `--destructive: oklch(0.577 0.245 27.325)`. That is Tailwind red-600 and
out of sRGB gamut; it renders `#e7000b`. `:150` has dark `oklch(0.704 0.191 22.216)`.

**Root cause.** The shadcn default red was tuned for a white page. This theme's page is 0.976 and the preview canvas
is 0.915, so even **plain** `text-destructive` fails on the page background (4.45) and on canvas (3.70). On its own tints
it fails everywhere in light mode.

**Fix: move the token, not the call sites.** This mirrors the primary's move to M3 tone 40.
- Light: `--destructive: oklch(0.49 0.185 27.3)` (`#b21a1b`). That is one step under M3's error tone 40 (`#ba1a1a` = oklch 0.506 0.193 27.7).
  Tone 40 exactly still fails on canvas at /10 (4.28), because canvas is darker than M3's surfaces.
- Dark: `--destructive: oklch(0.838 0.089 26.76)` (`#ffb4ab`), which is M3's error tone 80.

The only solid `bg-destructive` fills are non-text marks (`ats-compare-panel.tsx:54`, `career/documents-panel.tsx:216`).
They land at 6.9:1 on the light card and 10.5:1 on the dark card.

| site (text size, surface) | light now | light new | dark now | dark new |
|---|---|---|---|---|
| `pdf-pages-preview.tsx:123` render-error banner (xs, canvas, /10) | 3.13 | 4.56 | 6.44 | 10.43 |
| `app/templates/[id]/page.tsx:349` compile-error `<pre>` (xs, canvas, /10) | 3.13 | 4.56 | 6.44 | 10.43 |
| `ats-score-panel.tsx:119` `Badge variant="destructive"`, the gate warnings incl. "JD asks for N+ years…" (xs, card; dark /20) | 3.99 | 5.81 | 4.63 | 6.70 |
| `ui/badge.tsx:22` Badge destructive on background (dark /20) | 3.73 | 5.43 | 5.30 | 7.82 |
| `ui/button.tsx:35` Button destructive rest, bg (/10; dark /20) | 3.73 | 5.43 | 5.30 | 7.82 |
| Button destructive **hover**, bg (/20; dark /30) | 3.11 | 4.55 | 4.36 | 5.88 |
| Button destructive **hover**, card (/20; dark /30) | 3.31 | 4.84 | **3.83** | 5.10 |
| `ui/dropdown-menu.tsx:94` destructive item focused (popover; dark /20) | 3.99 | 5.81 | 4.63 | 6.70 |
| `resume-editor/raw-json-toggle.tsx:42` error pre (bg /10) | 3.73 | 5.43 | 6.19 | 9.95 |
| `gap-analysis/resolution-controls.tsx:399` (card /10) | 3.99 | 5.81 | 5.46 | 8.63 |
| `career/documents-panel.tsx:208` failed chip (card /10) | 3.99 | 5.81 | 5.46 | 8.63 |
| `analytics/base-summary-cards.tsx:18-19` D/F grade (card /10) | 3.99 | 5.81 | 5.46 | 8.63 |
| `job-knockout-card.tsx:18` conflict (sm, bg /5) | 4.08 | 5.92 | 6.56 | 10.90 |
| plain `text-destructive` on page background (e.g. `app/templates/[id]/page.tsx:183`, `app/base-resumes/[slug]/page.tsx`) | 4.45 | 6.43 | 6.84 | 11.65 |
| plain `text-destructive` on canvas / muted | 3.70 / 4.00 | 5.36 / 5.78 | 7.05 / 5.23 | 11.99 / 8.89 |

`app/career/page.tsx:207,287`, `career/profile-panel.tsx:40`, `career/entity-detail.tsx:130` and `career/inbox-panel.tsx:203`
tint the box `bg-destructive/10` but render foreground or muted text. They are unaffected and fine.

**Hand-rolled red pairs the token cannot reach.** These use Tailwind's `red-*` palette: `red-600` is the old `--destructive`,
`red-400` the old dark one.

| Site | Classes |
|---|---|
| `resume-health/finding-cards.tsx:315` | `bg-red-500/10 text-red-600` |
| `resume-health/finding-cards.tsx:351` | `/15` |
| `resume-health/finding-cards.tsx:362` | `/10` |
| `resume-health/finding-cards.tsx:1134` | `/10` |
| `resume-health/health-badges.tsx:152` | `/15` |
| `resume-health/demonstrate-skill-dialog.tsx:218` | `/10` |
| `resume-health/batch-ask-dialog.tsx:233` | `/10` |
| `resume-versions/version-diff-view.tsx:12` | `/10` |
| `resume-editor/diff-review.tsx:535` | `/10` |

In light mode they measure 4.13 at `/10` and 3.84 at `/15` over card; dark mode (`red-400`) passes at 5.4 to 5.7. Replace each
`bg-red-500/1X text-red-600 dark:text-red-400` with `bg-destructive/10 text-destructive`, so the token now governs them.
`status-chip.tsx:46` (`red-700` on `red-600/10`, 5.37:1) is the status vocabulary and passes. Leave it.

**Pins.** Add to `test_frontend_color_roles.py`. It is computed per surface, with the worst alpha actually used:

```python
# Destructive text sits on its own tints. Worst alpha per surface: Button hover
# /20 light, /30 dark; the render-error banner and compile error are /10 on canvas.
_DESTRUCTIVE_WORST = {
    "light": {"card": 0.20, "background": 0.20, "canvas": 0.10, "muted": 0.10},
    "dark":  {"card": 0.30, "background": 0.30, "canvas": 0.30, "muted": 0.20},
}

@pytest.mark.parametrize("mode", list(_MODES))
def test_destructive_text_on_its_tints_meets_aa(mode):
    t = _MODES[mode]
    d = _rgb(t, "destructive")
    for surface, worst in _DESTRUCTIVE_WORST[mode].items():
        bg = _rgb(t, surface)
        assert _contrast(d, bg) >= 4.5, f"{mode}: plain on --{surface}"
        for pct in (5, 10, 15, 20, 30):
            if pct / 100 > worst:
                continue
            ratio = _contrast(d, _over(d, bg, pct / 100))
            assert ratio >= 4.5, f"{mode}: destructive on /{pct} over --{surface} is {ratio:.2f}:1"
```

With the new values the tightest cases are canvas/10 at 4.56 and background/20 at 4.55. Muted /15 would be 4.50,
which is why muted is capped at /10.

**Risks.**
- Light red becomes darker and more brick-coloured: `#b21a1b` vs `#e7000b`. It is M3's error colour family, so this is intended.
- Dark red becomes salmon: `#ffb4ab`. That is M3 tone 80. If the owner wants more saturation, `oklch(0.80 0.11 22.2)` (`#fda19d`)
  also passes every row, with a worst case of 4.74 on card/30 and 5.06 on muted/20.
- `--chart-2` is separate and unaffected.

---

## 4. The divider has no single-pointer alternative to dragging (WCAG 2.5.7)

**Where:** `components/resume-editor/editor-shell.tsx:211-271` (`Splitter`). The only pointer paths are a drag, or
Hide/Show at `:171-178` and `:107-114`.

**Honest judgement.** 2.5.7 (WCAG 2.2 AA) needs the *functionality* to be reachable without dragging.
- Hide/Show gives two states, not resizing. It does not comply.
- Double-click to reset gives one width. It does not comply on its own.
- The keyboard path does not count: the criterion is about pointers.
- Two click targets that step the width on the same 5% grid as the arrow keys do comply. They reach every width
  a keyboard user can (25–70%). The Understanding document's own slider example is +/- buttons beside a draggable thumb.

**Fix: the smallest compliant affordance.** Add two ghost `icon-sm` Buttons in the preview header, before "Hide PDF preview".
They reuse `nextPreviewPct`, so they need no new maths:

```tsx
import { ArrowLeftToLine, ArrowRightToLine } from "lucide-react"; // both exist in lucide-react 1.8.0
...
<Button size="icon-sm" variant="ghost" aria-label="Widen preview" title="Widen preview"
  disabled={previewPct >= PREVIEW_PCT.max}
  onClick={() => setStoredPct(nextPreviewPct(previewPct, "ArrowLeft") ?? previewPct)}>
  <ArrowLeftToLine className="size-4" />
</Button>
<Button size="icon-sm" variant="ghost" aria-label="Narrow preview" title="Narrow preview"
  disabled={previewPct <= PREVIEW_PCT.min}
  onClick={() => setStoredPct(nextPreviewPct(previewPct, "ArrowRight") ?? previewPct)}>
  <ArrowRightToLine className="size-4" />
</Button>
```

Arrow-to-line icons are used rather than chevrons, because `ChevronRight` already means Hide.

Cheap extras (not compliance on their own):
- On the separator, `onDoubleClick={() => setStoredPct(PREVIEW_PCT.default)}` and `title="Drag to resize. Double-click to reset."`
- A wider hit area. The separator is `w-1` (4px). It passes 2.5.8 only through the spacing exception, so add an invisible
  pseudo-element: `before:absolute before:inset-y-0 before:-inset-x-1.5 before:content-['']`.

**Pins.** `test_frontend_studio.py::test_divider_is_keyboard_operable` slices the separator JSX from `role="separator"`
to the first `/>`. Keep the separator self-closing, and keep `/>` out of any handler or comment inside it.
Add `test_divider_has_a_pointer_alternative`: `aria-label="Widen preview"` and `aria-label="Narrow preview"` are in `_SHELL`.

**Risks.**
- The header gains two controls in a pane that can be 25% wide. The row already has `flex-wrap` (comment `:147-152`), so it wraps instead of overflowing.
- An alternative with one control is a "Preview width" DropdownMenu with a radio group. It costs more and adds a popup.

---

## 5. Drag scales by `window.innerWidth`, has no `pointercancel`, and writes localStorage on every move

**Where:** `editor-shell.tsx:225-244` (Splitter `start`), `:131-135` (onDrag) and `:86-90` (a write per `previewPct` change).

```tsx
const viewportW = window.innerWidth;              // :227
onDrag((deltaPx / viewportW) * 100);              // :232, percent of the SHELL applied
window.addEventListener("pointermove", move);     // :242
window.addEventListener("pointerup", up);         // :243, no pointercancel
useEffect(() => { ... localStorage.setItem(widthKey, ...) }, [previewPct, ...]) // :86-90, every move
```

**Root causes.**
1. The delta is a fraction of the window but is applied as a percent of the shell. At 1280 with the sidebar
   pinned, the shell is 1024px, so the divider moves 80% as far as the pointer. At 768 it moves 67%.
2. It is incremental and clamped. Past a limit, pointer motion is lost, so on the way back the divider detaches from the pointer.
3. There is no `pointercancel`. A pen or touch cancel, or the OS taking the gesture, leaves `body` stuck with
   `cursor: col-resize; user-select: none` and the listeners attached until the next `pointerup`.
4. localStorage (synchronous) is written on every pointermove through the effect.

**Fix.** Use pointer capture on the separator and absolute positioning against the shell, and persist on release only.
Continued in item 12, where the stored value comes from the hook:

```tsx
// Splitter
const drag = useRef<{ left: number; width: number; editorPct: number } | null>(null);
const finish = () => {
  const d = drag.current;
  if (!d) return;                 // pointerup + lostpointercapture both fire
  drag.current = null;
  document.body.style.cursor = "";
  document.body.style.userSelect = "";
  onDragEnd(d.editorPct);
};
<div role="separator" ... tabIndex={0}
  onPointerDown={(e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    // The shell's box, not the window: with the sidebar pinned a window
    // fraction moved the divider 80% as far as the pointer.
    const shell = e.currentTarget.parentElement!.getBoundingClientRect();
    drag.current = { left: shell.left, width: shell.width, editorPct };
    e.currentTarget.setPointerCapture(e.pointerId);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }}
  onPointerMove={(e) => {
    const d = drag.current;
    if (!d) return;
    // Absolute: the divider stays under the pointer and a clamp cannot drift.
    d.editorPct = ((e.clientX - d.left) / d.width) * 100;
    onDrag(d.editorPct);
  }}
  onPointerUp={finish}
  onPointerCancel={finish}
  onLostPointerCapture={finish}
  onDoubleClick={onReset}
  onKeyDown={/* unchanged */}
  className="... touch-none ..."   // or touch gestures turn into scrolls + pointercancel
/>
```

```tsx
// EditorShell
const [dragPct, setDragPct] = useState<number | null>(null); // rendered, not persisted
const previewPct = dragPct ?? storedPct;
<Splitter
  editorPct={100 - previewPct}
  onDrag={(editorPct) => setDragPct(clampPreviewPct(100 - editorPct))}
  onDragEnd={(editorPct) => { setStoredPct(clampPreviewPct(100 - editorPct)); setDragPct(null); }}
  onReset={() => setStoredPct(PREVIEW_PCT.default)}
  onKey={(key) => { const next = nextPreviewPct(previewPct, key); if (next === null) return false; setStoredPct(next); return true; }}
/>
```

Add a pure helper in `lib/studio.ts`. It rounds to 0.1 so the stored value never jumps visibly on release.
The old `Math.round` jumped up to 0.5% (about 5px):

```ts
export function clampPreviewPct(pct: number): number {
  const { min, max } = PREVIEW_PCT;
  return Math.round(Math.min(max, Math.max(min, pct)) * 10) / 10;
}
```

`onDragEnd` receives the value from the Splitter's ref, not from React state, so a `pointerup` that lands before the last
move's render cannot store a stale width.

**Pins.**
- `test_divider_is_keyboard_operable`: see the note on the `/>` slice in item 4.
- Add `node --test` cases in `lib/studio.test.ts` for `clampPreviewPct` (clamps both ends, rounds to 0.1) and `parsePreviewPct` (item 12).
- Optionally add a static pin that `_SHELL` contains `onPointerCancel=` and `setPointerCapture(` and does not contain `window.innerWidth`.

**Risks.**
- `parentElement!` relies on the Splitter being a direct child of the shell row, which is true at `editor-shell.tsx:120-128`.
- Pointer capture makes `e.target` for moves the separator itself, which is fine.

---

## 6. The template editor scrolls at 1280×800, and the collapsed edge tab covers the scrollbar and controls

**Measured** (1280×800, `/templates/harshibar`, preview open):
- The document is **1026px** tall in an 800px viewport. `<main>` is 1026px with class `flex min-h-0 w-full flex-1 flex-col`.
- The Knobs `TabsContent` is 941px with `overflow-y: auto`, but `clientHeight === scrollHeight` (941), so its scroller never engages.
- Scrollbars are overlay (0px wide).
- "School first" and "Bulleted" end at x=802, against the pane's right edge at 817. Their rows are at y 492–550.

**Root cause (page scroll).** `app/templates/[id]/page.tsx:220` renders `<main className="flex min-h-0 w-full flex-1 flex-col">`.
Every ancestor is content-sized:
- `SidebarGutter` is `flex-1 flex-col`.
- `SidebarInset` stretches to the wrapper.
- The wrapper is `min-h-svh` (`ui/sidebar.tsx:141`), which is a minimum, not a height.

So `flex-1 min-h-0` has nothing to bound, the `h-full` Tabs never gets a definite height, and the FormattingPanel (941px)
grows the page. The two studios avoid this with `FullscreenEditorPage` (`components/resume-editor/fullscreen-editor-page.tsx:12`,
`<main className="flex h-dvh flex-col overflow-hidden">`), which the template editor never adopted.

**Fix (page).** Replace the page's own `<main>` wrapper at `:220`/`:366` with the shared one:

```tsx
import { FullscreenEditorPage } from "@/components/resume-editor/fullscreen-editor-page";
...
return (
  <FullscreenEditorPage>
    <EditorShell fullHeightLeft storageKey="templateEditor" ... />
  </FullscreenEditorPage>
);
```

Verified by applying `height:100dvh; overflow:hidden` to that `<main>` in the DOM: the document becomes 800px and Knobs
scrolls internally (715 client, 941 scroll). The Code tab's Monaco `height="100%"` (`:320-328`) gains a definite height
the same way. The error and loading branches keep their own `<main>`.

**Root cause (edge tab).** The collapsed branch (`editor-shell.tsx:103-116`) places the button `absolute top-1/2 right-0 w-7 h-20`
over a left pane that fills the whole width. It overlays the rightmost 28px of the pane, which is where the right-aligned
choice rows end (15px inset) and where the overlay scrollbar sits: the page's today, the Knobs scroller's once the page fix lands.
Its vertical centre moves with the pane height, so after the page fix it covers different rows. Nudging it is not a fix.

**Fix (edge tab).** Replace the overlay with a 28px rail in normal flow, so the left pane and its scrollbar end where the rail begins:

```tsx
if (collapsed) {
  return (
    <div className="flex min-h-0 w-full flex-1">
      <div className={leftClass}>{editor}</div>
      {/* In flow, not an overlay: an absolutely-placed tab covered the left
          pane's scrollbar and its right-aligned controls. */}
      <div className="bg-canvas flex w-7 shrink-0 items-center border-l">
        <button
          type="button"
          aria-label="Show PDF preview"
          title="Show PDF preview"
          onClick={() => setCollapsed(false)}
          className="text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:ring-ring flex h-20 w-full items-center justify-center transition-colors outline-none focus-visible:ring-2 focus-visible:ring-inset"
        >
          <ChevronLeft className="size-4" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
```

`leftClass` for document surfaces keeps `mx-auto max-w-5xl flex-1`, and auto margins still centre it with the rail at the right.
Numbers: the chevron (`muted-foreground`) on canvas is 4.56 light and 7.86 dark. The solid ring on canvas is 3.49 light with the item 2 token.

**Pins.**
- `test_frontend_query_error_states.py:62` needs `tq.isLoading || !tq.data` in the template page. It is untouched.
- `test_frontend_studio.py::test_preview_pane_is_a_canvas` needs `bg-canvas` in `_SHELL`. It still holds.
- Add `"<FullscreenEditorPage>" in templates page` and `'aria-label="Show PDF preview"'` not inside an `absolute` class.

**Risks.**
- `VersionBanner` renders above `children` in `SidebarGutter` (`app/layout.tsx:59`). When it shows, an `h-dvh` page overflows
  by the banner height. This already affects both studios; log it, don't fix it here.
- `chat-page.tsx:593-600` has the mirror-image overlay edge button (left side). Check whether it covers the thread's scrollbar; the same rail pattern applies.

---

## 7. At 768px the base studio's Contact grid overflows its pane

**Measured** (768×800, sidebar pinned, preview at 45%, `/base-resumes/data_engineer`):
- The editor pane's `clientWidth` is 278 and its `scrollWidth` is **375**, a 97px horizontal overflow.
- The `<dl>` computes `grid-template-columns: 128px 193.93px` inside a 164px content box (204 minus `pr-10`).
- The longest value has a min-content width of 194px.

**Where:** `components/resume-editor/contact-form.tsx:73-92`, the read view.

```tsx
<div className="group/contact ... relative rounded-md border px-3 py-3">
  <dl className="grid grid-cols-[8rem_1fr] gap-x-4 gap-y-1.5 pr-10 text-sm">
    ... <div className="contents"><dt ...>{label}</dt><dd className="text-foreground/90">{v}</dd></div>
```

**Root cause.**
1. `1fr` is `minmax(auto, 1fr)`: the value column cannot shrink below its longest unbreakable token (an email or URL).
2. A fixed 8rem label column plus 16px gap leaves the value about 20px at this width (512px of page, 55% editor, `p-6`, `px-3`, `pr-10`).

The edit view (`:47`, `grid gap-3 sm:grid-cols-2`) does not overflow, because `grid-cols-2` is `minmax(0,1fr)` and `Input` is
`min-w-0`. But `sm:` keys on the **viewport**, so it gives two roughly 110px inputs in a 230px pane.
The tailored studio renders the same component (`tailored-resume-studio.tsx:899-903`).

**Fix.** Key both views to the pane with container queries, a pattern already used in `ats-score-panel.tsx:326,386`
and `ui/card.tsx:30`, and let values wrap anywhere, as `studio-overflow.tsx:60` does:

```tsx
// read view
<div className="group/contact @container border-border/0 hover:border-border/60 relative rounded-md border px-3 py-3">
  <dl className="grid gap-x-4 gap-y-1.5 pr-10 text-sm @xs:grid-cols-[8rem_minmax(0,1fr)]">
    {FIELDS.map(({ key, label }) => (
      // Narrow pane: each pair stacks as one grid item. From 20rem the
      // wrapper dissolves and dt/dd join the two-column grid.
      <div key={key} className="grid gap-0.5 @xs:contents">
        <dt className="text-muted-foreground text-sm font-medium">{label}</dt>
        <dd className="text-foreground/90 min-w-0 wrap-anywhere">…</dd>
      </div>
    ))}
  </dl>
// edit view
<div className="@container grid gap-3">
  <div className="grid gap-3 @md:grid-cols-2">…</div>
```

`@xs` is 20rem and `@md` is 28rem. At 768 the contact box is about 206px, so it stacks and does not overflow. At 1280 with the
sidebar pinned it is about 490px, so it uses two columns with a value column of about 300px, and long URLs wrap.

**Pins.** None exist. Add to `test_frontend_studio.py`: `"minmax(0,1fr)"` and `"wrap-anywhere"` are in `contact-form.tsx`,
and `"grid-cols-[8rem_1fr]"` is not.

**Risks.** The stacked read view changes the look below 20rem, so check it at 768 and at 375 (the sheet case).
`docs/frontend-conventions.md:229-234` (the 768 band) should name this case.

---

## 8. Hand-rolled primary tints for selected states: one rule

**The rule** (goes into `docs/frontend-conventions.md:16-35`, replacing the "known inconsistency" sentence at `:32-35`):
- **Selected in a set** (a toggle, filter chip or segment): `tonal` (secondary container) plus a leading `Check` plus `aria-pressed`.
  This is what the health filters, Review changes and the zoom presets already do.
- **Current place in a list or nav** (a sidebar row, the open chat): secondary container, semibold, and `aria-current`.
  No Check, which is the nav rule.
- **A create or secondary action**: `Button variant="tonal"`.
- **A non-interactive status chip**: `Badge variant="tonal"`, or the secondary-container pair on a custom-sized chip.
- `bg-primary/N text-primary` is retired as a component fill. Callout **containers** (`border-primary/25 bg-primary/5`
  with foreground text) are not component states and stay.

Why the Check is not optional, in numbers. In light mode:
- A selected secondary-container fill vs an unselected option under hover (`bg-muted`) is **1.046:1** (ΔE_ok 0.027).
- Either fill vs the page is about 1.16:1.

Today's `bg-primary/10 text-primary` passes AA (5.39 on background, 5.76 on card), so this item is consistency, not contrast.
The move gives 9.81:1 at rest and 8.46 on hover in light, 9.36 and 7.78 in dark.

**Per site:**

| Site | Now | Class | Change |
|---|---|---|---|
| `components/source-toggle.tsx:36-38` | `bg-primary/10 text-primary` (has `aria-pressed`) | **Selected** | `"bg-secondary-container text-on-secondary-container hover:bg-secondary-container-hover"`; add `inline-flex items-center gap-1` to the base class and `{value === s && <Check className="size-3" aria-hidden="true" />}` before the label |
| `components/proposals/proposals-section.tsx:604-617` history status filters | hand-rolled `<button>`, `border-transparent bg-primary/10 text-primary` | **Selected** | Copy `health-report-page.tsx:461-470`: `<Button size="xs" variant={active ? "tonal" : "outline"} aria-pressed={active} className="rounded-full" onClick=…>{active && <Check />}{label}</Button>`. This also gains Button's focus ring. |
| `components/chat/chat-page.tsx:573` rail "New chat", and `:746` the same in the sheet | ghost Button with `bg-primary/10 text-primary hover:bg-primary/15` | **Create action** | `variant="tonal"`, keep `h-10 flex-1 justify-start gap-2 rounded-full px-4` (no `flex-1` in the sheet). Keep the two strings identical or extract a `NewChatButton` (slop ratchet). |
| `components/chat/chat-page.tsx:786` active session row | `bg-primary/10 text-primary` on the row div | **Current** | Row: `activeId === s.id ? "bg-secondary-container text-on-secondary-container hover:bg-secondary-container-hover font-medium" : "hover:bg-muted"`. On the inner `<button>` (`:790-796`) add `aria-current={activeId === s.id ? "true" : undefined}`. Today the current chat has no programmatic signal at all. |
| `components/setup/setup-status-strip.tsx:21` done pill | `bg-primary/10 text-primary dark:bg-primary/15 hover:bg-primary/15` (already leads with Check) | **Status on an actionable pill** | `"bg-secondary-container text-on-secondary-container hover:bg-secondary-container-hover"`. This also fixes item 11. |
| `components/charts/top-skills-chart.tsx:132` Top-30% pills | `border-primary/30 bg-primary/10 text-primary hover:bg-primary/15 dark:bg-primary/20` | **Emphasis chip** (tooltip trigger, `cursor-default`) | `"border-transparent bg-secondary-container text-on-secondary-container hover:bg-secondary-container-hover"`. The rank label (`:51`) must change too, see item 11. |
| `resume-editor/tailored-resume-studio.tsx:413` tab change-count | `bg-primary/15 text-primary` 10px | Status count | `bg-secondary-container text-on-secondary-container` |
| `resume-editor/formatting-panel.tsx:283` "Customized" | `bg-primary/10 text-primary` | Status chip | same pair |
| `analytics/analytics-overview.tsx:199` "in your KB"; `analytics/gap-tiers-panel.tsx:36` `in_kb`; `career/send-to-resume-dialog.tsx:51-53`; `resume-editor/diff-review.tsx:34` `kb_auto` | `bg-primary/10 text-primary` | Status chips | `Badge variant="tonal"` or the pair. Optional, lowest priority. |
| `career/points-list.tsx:312` usage chip | `text-muted-foreground … bg-primary/10` | Status chip | the pair, or leave it |
| `career/profile-panel.tsx:117,258`, `career/timeline-panel.tsx:46`, `career/capture-box.tsx:120` | icon avatars | Decorative | Keep (primary icon on `/10` is 5.4:1 for a graphic) |
| `resume-editor/formatting-panel.tsx:148-161` segmented buttons (not in the grep: selected is `bg-primary text-primary-foreground`) | **no `aria-pressed`** | **Selected** | Add `aria-pressed={current === o.value}` at minimum. Optionally tonal plus Check, as M3's segmented button does. |
| `career/new-entity-dialog.tsx:241,259` | `border-primary bg-primary/5`, **no `aria-pressed`** | Selected card | Keep the look (the primary border is 6.26:1 against the background). Add `aria-pressed`. `extra-sections-editor.tsx:548` and `templates/template-select.tsx:180` already have it. |
| `setup/dropzone.tsx:177` | drag-over | Transient | Keep |
| Tailor page `:625,635`, `gap-card.tsx:529`, `chat/change-card.tsx:50`, `chat/kb-capture-card.tsx:10`, `first-run-import-card.tsx:57`, `getting-started-card.tsx:69`, `capture-box.tsx:103`, `entity-card.tsx:71` hover | callout containers | Container | Keep |
| `editor-shell.tsx:269` splitter tints | handle | Handle | Keep |

`analytics/agent-pipeline-card.tsx:59`: the `bg-primary/10` data bar is **1.16:1** against its `muted/50` track (1.20 dark).
A solid `bg-primary` bar would be 6.15:1. It is out of scope; log it as a 1.4.11 candidate.

**Pins.**
- `test_frontend_color_roles.py::test_primary_text_tints_stay_under_the_ceiling`: removing tints only helps.
- Extend `test_selected_tonal_toggles_show_a_check` with SourceToggle (`{value === s && <Check`) and the proposals filters.
- `test_frontend_query_error_states.py:73,76` anchor copy strings in `proposals-section.tsx` and `chat-page.tsx`. Keep those strings.
- Optionally add a ratchet: count `bg-primary/10 text-primary` in `components/`, and fail if it rises.

**Risks.**
- A Check changes a segment's width. The zoom presets already accept that.
- The light secondary container is greyer (C 0.022) than the blue tint, so selected chips read "calmer". That is the conventions' intent.

---

## 9. FAB (primary container) vs the active nav row (secondary container), and `/new` shows no current item

**Where.**
- `app/globals.css:85,88` (light) and `:139,141` (dark).
- `components/app-sidebar.tsx:97-110`, the FAB `Link`, which uses `buttonVariants({ variant: "fab" })` and `aria-current={navCurrent(pathname, "/new")}`.
- `components/ui/button.tsx:27`, the `fab` variant.

**Numbers.**

| pair | light | dark |
|---|---|---|
| FAB `#d1e3ff` vs active row `#dee7f5` | **1.047:1**, ΔE_ok 0.026 | `#203f6f` vs `#2c3645`: 1.163:1, ΔE 0.072 |
| FAB vs sidebar | 1.25 | 1.71 |
| active row vs sidebar | 1.19 | 1.47 |

M3 puts both roles at tone 90, so near-identity is by design, not a token bug. The rail tells them apart by shape and position.
The real defect is that on `/new` the FAB carries `aria-current="page"` and **nothing looks current**, which breaks the
conventions' "a current page you can see and hear" (`frontend-conventions.md:325`).

**Fix (recommended).** Selected means the full-strength role. For container-coloured toggles, M3's selected state is the
full-strength role (a filled icon-button toggle selects to `primary`). M3 Expressive's FAB menu also turns the FAB `primary`
while it is toggled open. So on `/new`, render the FAB with the `default` (primary) variant and keep its FAB geometry:

```tsx
const fabCurrent = navCurrent(pathname, "/new");
<Link
  href="/new"
  aria-current={fabCurrent}
  className={cn(
    // Current: the full-strength role, M3's selected state for a container-
    // coloured control; the container fill is ~1.05:1 from the active row.
    buttonVariants({ variant: fabCurrent ? "default" : "fab", size: "lg" }),
    "h-10 gap-2.5 rounded-[16px] px-4",
  )}
>
```

| When current | light | dark |
|---|---|---|
| primary `#1358bb` vs sidebar | **6.43:1** | 8.32 |
| vs the resting FAB fill | 5.14 | 4.88 |
| vs the active nav fill | 5.38 | 5.68 |
| label on primary | 6.43 | 8.34 |
| label on `hover:bg-primary/90` | 5.23 | — |

**Optional companion.** Pull the resting FAB away from the nav fill without leaving gamut. `--primary-container` has one
consumer, the `fab` variant.
- Light: `oklch(0.88 0.058 259)` (`#c1d9fe`, max in-gamut chroma at L 0.88). Against the active row it gives 1.150:1 and ΔE 0.058, up from 1.047 and 0.026. Text is 8.66 at rest and 7.51 on hover.
- Dark: `oklch(0.40 0.11 259)` (`#1f4682`). Against the active row it gives 1.312 and ΔE 0.106. Text is 7.35 and 6.14.

Luminance contrast between two tonal fills cannot get large, so don't chase it. The current-state fix above is the one that matters.

**Pins.**
- `test_frontend_sidebar_nav.py::test_create_action_is_the_fab_variant` asserts the substring `variant: "fab"`, which a ternary breaks.
  Update it to `re.search(r'variant:\s*fabCurrent \? "default" : "fab"', _SIDEBAR)`.
- `test_frontend_color_roles.py::test_fab_variant_uses_primary_container` reads `button.tsx`. It is unchanged.
- `test_container_text_meets_aa_at_rest_and_on_hover` covers the optional container change.

**Risks.** A filled primary pill on the create page could read as "press me". Its `aria-current` and its unchanged label
make it a location, and clicking it is a same-route no-op. The owner may prefer the optional tone change alone; see open question 1.

---

## 10. `/jobs/[id]` highlights no sidebar item

**Where.** `lib/nav.ts:8-15` (prefix-only `navCurrent`) and `components/app-sidebar.tsx:132-154`.

**How users arrive.**
- Every job is a tracker row: Saved jobs, and the proposal jobs through the agent-lane filters (`app/applications/page.tsx:69-73,144`).
  Links come from the tracker (`applications/page.tsx:553-554`), `/new` (`app/new/page.tsx:76`), `/applications/[id]`
  (a redirect, `:31`), `application-panel.tsx:97` and `job-extraction-summary.tsx:95`.
- Only `proposals-section.tsx:752` links `?from=proposals`. The job page reads `from` for its Back label
  ("Back to proposals", `app/jobs/[id]/page.tsx:315,322`), its prev/next queue and its post-delete target.

**Decision.**
- `/jobs/*` marks **Applications** `"true"`.
- With `?from=proposals` it marks **Agent Proposals** `"true"` instead, so the sidebar agrees with the page's own Back button.
- The tailor flow (`/jobs/[id]/tailor/*`) follows the same rule. Its links drop `from`, so it lands on Applications, which is still true.

**Fix.** A pure mapping in `lib/nav.ts`:

```ts
/**
 * The sidebar section a route belongs to when its URL does not say so. A job
 * page is a row of the Applications tracker (Saved jobs included) unless it
 * was opened from the proposals queue, whose Back button it then shows.
 */
export function navSection(pathname: string, from?: string | null): string {
  if (pathname === "/jobs" || pathname.startsWith("/jobs/")) {
    return from === "proposals" ? "/proposals" : "/applications";
  }
  return pathname;
}

export function navCurrent(
  pathname: string,
  href: string,
  from?: string | null,
): "page" | "true" | undefined {
  if (pathname === href) return "page";
  const section = navSection(pathname, from);
  if (section === href || section.startsWith(`${href}/`)) return "true";
  return undefined;
}
```

`app-sidebar.tsx` then reads `from`. `useSearchParams()` in a client component under the root layout needs a
Suspense boundary, or `next build` fails. The docs are at `node_modules/next/dist/docs/01-app/03-api-reference/04-functions/use-search-params.md:80-88,181`,
and the repo already follows the pattern in `app/chat/page.tsx:7-15` and `app/applications/page.tsx:706-714`.
The fallback renders the same nav with `from = null`, which is identical markup on every route except `/jobs/*`:

```tsx
<SidebarContent>
  {/* `?from=proposals` decides which section a job page sits in, and
      useSearchParams() needs a Suspense boundary for the static prerender
      (Next 16 CSR bailout). The fallback IS the nav without `from`. */}
  <Suspense fallback={<MainNav pathname={pathname} from={null} />}>
    <MainNavWithSearch pathname={pathname} />
  </Suspense>
</SidebarContent>
...
function MainNavWithSearch({ pathname }: { pathname: string }) {
  const from = useSearchParams().get("from");
  return <MainNav pathname={pathname} from={from} />;
}
function MainNav({ pathname, from }: { pathname: string; from: string | null }) {
  // the existing <nav aria-label="Main"> block: FAB (item 9) + NAV_GROUPS,
  // passing `from` down to NavMenu
}
// NavMenu: const current = navCurrent(pathname, item.href, from);
```

The footer's Account `NavMenu` passes `from={null}`.

**Pins.**
- `lib/nav.test.ts`. Add:
  - `navCurrent("/jobs/abc", "/applications") === "true"`
  - `navCurrent("/jobs/abc", "/proposals", "proposals") === "true"`
  - `navCurrent("/jobs/abc", "/applications", "proposals") === undefined`
  - `navCurrent("/jobs/abc/tailor/s1", "/applications") === "true"`
  - `navCurrent("/jobsite", "/applications") === undefined`
- `test_frontend_sidebar_nav.py::test_nav_links_carry_aria_current` needs `navCurrent(` and `aria-current={current}` to stay.
  Add a pin that `<Suspense` and `useSearchParams()` are in `app-sidebar.tsx`.

**Risks.**
- On statically prerendered routes the nav's server HTML is the fallback, which the client re-renders once on load.
  The markup is identical, so there is no visual change.
- A simpler alternative is to map `/jobs/*` to Applications always, with no Suspense. It is wrong only for the proposals
  entry point, where Back says "Back to proposals".

---

## 11. The setup pill and the top-skills chip have no dark-mode hover

**Where.** `components/setup/setup-status-strip.tsx:21` and `components/charts/top-skills-chart.tsx:132`.

**Root cause (verified in the built CSS).** `.dark\:bg-primary\/15:is(.dark *)` has specificity (0,2,0), the same as
`.hover\:bg-primary\/15:hover`. The `dark` custom variant is emitted **after** `hover` in
`.next/static/chunks/0g4k5z2fhi0v3.css` (offset 110757 vs 82204), so the resting dark fill wins over hover.
The setup pill's two values are also equal (`/15` and `/15`), so even the order would not matter there.

**Fix (recommended, the item 8 rule).** Both move to the secondary-container pair. Its `-hover` token is mixed once in
`:root` and follows `.dark` (`globals.css:78-90`), so there is no `dark:` class to lose to:
- Setup pill done: `"bg-secondary-container text-on-secondary-container hover:bg-secondary-container-hover"`.
- Top-skills: `"border-transparent bg-secondary-container text-on-secondary-container hover:bg-secondary-container-hover"`.
  **Also change the rank label** at `top-skills-chart.tsx:51` from `text-muted-foreground` to `text-on-secondary-container/80`.
  `muted-foreground` on the container is 4.71 at rest but **4.06 on hover** (dark 3.92). The `/80` label gives 5.68 at rest
  and 5.14 on hover in light, 6.62 and 5.65 in dark.
  Today the dark rank label already fails at rest: 4.44 on `primary/20` over the band.

State-layer visibility: the container vs its hover is 1.160 in light and 1.203 in dark (ΔE about 0.047). That is the same
step the tonal Button uses.

**Fix (minimal alternative), if the chips must stay blue.** Keep within the test's dark `/20` ceiling
(`test_frontend_color_roles.py:152`; a `dark:hover:bg-primary/25` next to `text-primary` fails the scan at `:179-191`):
- setup: `"bg-primary/10 text-primary hover:bg-primary/15 dark:bg-primary/15 dark:hover:bg-primary/20"`
- top-skills: `"border-primary/30 bg-primary/10 text-primary hover:bg-primary/15 dark:bg-primary/15 dark:hover:bg-primary/20"`
  (the dark rest drops from `/20` to `/15`)

The `/15` to `/20` step is only 1.12:1 in dark.

**Same file, extra defect.** The setup `PILL` (`:15`) and `setup/dropzone.tsx:173` use `focus-visible:ring-offset-2` with no
offset colour. Tailwind v4's `--tw-ring-offset-color` defaults to `#fff` (`@property … initial-value:#fff` in the built CSS),
so in dark mode a 2px **white** band sits between the pill and its ring. Add `focus-visible:ring-offset-background` to both.

**Pins.** `test_primary_text_tints_stay_under_the_ceiling` is satisfied by either variant. `test_frontend_query_error_states.py:83`
(`<SetupStatusStrip` on the profile page) is unaffected.

---

## 12. One-frame flash for localStorage-backed prefs

**Where.**
- `editor-shell.tsx:59-90`: `useState` defaults, a read in `useEffect`, a `hydrated` flag, and two write effects.
- `pdf-pages-preview.tsx:56-65`: `zoom` defaults to `"width"` and is read in an effect.
- `chat-page.tsx:103-151`: the same pattern for the history rail. Its comment at `:103-105` calls it the EditorShell pattern.

**Root cause.** An effect runs after the first commit, and for a non-discrete render usually after paint. So the default
(45% width, expanded, Fit width, rail open) paints for one frame before the stored value applies.

**Fix.** Add a hook, modelled on `hooks/use-mobile.ts` and `hooks/use-mod-key.ts`, which are `useSyncExternalStore` with a
server snapshot. Put it at `hooks/use-local-storage-state.ts`:

```ts
"use client";

import { useCallback, useMemo, useSyncExternalStore } from "react";

// Same-document writes notify here; other tabs arrive as `storage` events.
const listeners = new Set<() => void>();

function subscribe(onChange: () => void) {
  listeners.add(onChange);
  window.addEventListener("storage", onChange);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", onChange);
  };
}

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null; // storage disabled: behave as "never set"
  }
}

/**
 * A preference persisted in localStorage and read DURING render. The server
 * and hydration snapshot is null, so `parse(null)` is the default; a component
 * that mounts after hydration paints the stored value on its first frame. The
 * read-in-an-effect pattern this replaces painted the default first.
 * Pass a module-level `parse`/`serialize` so the parsed value is memoised.
 */
export function useLocalStorageState<T>(
  key: string,
  parse: (raw: string | null) => T,
  serialize: (value: T) => string,
): readonly [T, (next: T) => void] {
  const raw = useSyncExternalStore(subscribe, () => read(key), () => null);
  const value = useMemo(() => parse(raw), [parse, raw]);
  const set = useCallback(
    (next: T) => {
      try {
        window.localStorage.setItem(key, serialize(next));
      } catch {
        // Quota or disabled storage: the preference just doesn't persist.
      }
      listeners.forEach((notify) => notify());
    },
    [key, serialize],
  );
  return [value, set] as const;
}

export const parseFlag = (raw: string | null) => raw === "1";
export const serializeFlag = (value: boolean) => (value ? "1" : "0");
```

Add to `lib/studio.ts` (pure, so `node --test` can reach it):

```ts
/** A stored preview width; the default when absent, garbled or out of range. */
export function parsePreviewPct(raw: string | null): number {
  const n = raw === null ? NaN : Number(raw);
  return Number.isFinite(n) && n >= PREVIEW_PCT.min && n <= PREVIEW_PCT.max ? n : PREVIEW_PCT.default;
}
```

`Number("")` is 0, which is out of range, so it falls back to the default.

**Why this removes the flash at every current call site.** `useSyncExternalStore` uses the server snapshot only while
hydrating. None of these components render during hydration:
- EditorShell and PdfPagesPreview mount after a react-query load: `base-resumes/[slug]/page.tsx:38-50`,
  `applications/[id]/resume/page.tsx`, the template page `:195-202`, and the job page's Resume tab.
- ChatPage and GettingStartedCard sit under a `useSearchParams` Suspense boundary, which is CSR bailout.
- FirstRunImportCard renders null until its query resolves.

So each reads storage on its first render. If a future caller does render during hydration, it degrades to today's
behaviour (default first) and never mismatches.

**Call sites** (from `grep localStorage` in `components/`, `app/`, `hooks/` and `lib/`):

| Site | Change |
|---|---|
| `resume-editor/editor-shell.tsx:59-90` | `const [collapsed, setCollapsed] = useLocalStorageState(collapsedKey, parseFlag, serializeFlag);` and `const [storedPct, setStoredPct] = useLocalStorageState(widthKey, parsePreviewPct, String);`. Delete `hydrated`, the three effects and the eslint-disable at `:70`. Add `dragPct` per item 5. |
| `resume-editor/pdf-pages-preview.tsx:56-65` | `const [zoom, chooseZoom] = useLocalStorageState(ZOOM_KEY, parseZoom, String);` Delete the effect, the eslint-disable at `:59` and the manual `setItem`. |
| `chat/chat-page.tsx:103-151` (key `chatPage.historyCollapsed`, `:72`) | `useLocalStorageState(HISTORY_COLLAPSED_KEY, parseFlag, serializeFlag)`. Delete `historyHydrated`, both effects and the eslint-disable at `:140`. Rewrite the comments at `:102-105` and `:134-137`. |
| `setup/getting-started-card.tsx:35-39,83-84` (optional) | Replace the lazy `useState(() => … localStorage.getItem(DISMISS_KEY) === "1")`, a render-time read that would mismatch if it were ever SSR'd, with `useLocalStorageState(DISMISS_KEY, parseFlag, serializeFlag)`. |
| `career/first-run-import-card.tsx:29-31,78-79` (optional) | Same. |
| **Not adopted:** the sessionStorage prev/next sequences at `app/applications/page.tsx:118,126`, `proposals/proposals-section.tsx:50` and `app/jobs/[id]/page.tsx:91` | Session-scoped navigation state written on click, not a paint-time preference. |

All setters in these call sites take plain values, never functional updaters (checked), so the `(next: T) => void` signature fits.

**Pins.**
- `lib/studio.test.ts`: `parsePreviewPct(null)`, `("")`, `("abc")`, `("24")`, `("71")` all give 45; `("50")` gives 50; `("47.5")` gives 47.5.
- `test_frontend_studio.py`: the zoom pins slice from `{PREVIEW_ZOOMS.map(` and `aria-pressed={zoom === option.value}`, which stay.
  Optionally pin that `set-state-in-effect` no longer appears in `editor-shell.tsx`, `pdf-pages-preview.tsx` or `chat-page.tsx`.

**Risks.**
- **Behaviour change:** the preferences now sync live across tabs and across instances with the same key. Two open studio tabs
  share collapse and width, and every mounted preview shares the zoom. This is probably wanted; name it in the commit.
- With storage throwing on write (quota), a toggle does not stick. Today the write throws inside an effect, which is worse.
  An in-memory fallback map is possible but is not needed for the desktop shell.

---

## Docs to update in the same change (header contract: integrate, present tense)

`docs/frontend-conventions.md`:
- **`:12-35` Colour roles.**
  - Record the ring value and why it is 3:1 on canvas.
  - Note that the base-layer UA outline is the solid ring.
  - Record that destructive is M3 error, tuned for this page and canvas, and pinned.
  - Replace the "known inconsistency" sentence with item 8's rule.
- **`:127-132` Divider.** Add the pointer alternative (Widen/Narrow, double-click reset). Note that the drag is shell-relative
  with pointer capture and persists on release.
- **`:146-167` PdfPagesPreview.** Say the zoom is read through `useLocalStorageState` (no first-frame flash).
- **`:211-234` Panes and the 768 band.** Add Contact's container-query grid as the worked case.
- **`:325-347` Sidebar.**
  - The collapsed off-canvas sidebar is `inert`, with the focus hand-off.
  - The FAB's current state is primary on `/new`.
  - `/jobs/*` maps to Applications, or to Proposals with `?from=proposals`, through `navSection` and a Suspense-wrapped `useSearchParams`.

SYSTEM.md §12 candidate: "`useSearchParams()` under the root layout needs a Suspense boundary whose fallback is the same UI,
or `next build` fails and every static route loses the component."

## Open questions for the owner

1. Item 9: primary fill on `/new` (recommended), or only the stronger resting container tone?
2. Item 3: M3 tone 80 salmon `#ffb4ab` for dark, or the more saturated `oklch(0.80 0.11 22.2)` `#fda19d`? Both pass.
3. Item 8: move the top-skills Top-30% chips to the neutral tonal pair (recommended), or keep them blue with item 11's minimal fix?
