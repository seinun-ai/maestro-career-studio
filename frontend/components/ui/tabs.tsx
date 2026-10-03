"use client"

import { Tabs as TabsPrimitive } from "@base-ui/react/tabs"

import { cn } from "@/lib/utils"

function Tabs({
  className,
  orientation = "horizontal",
  ...props
}: TabsPrimitive.Root.Props) {
  return (
    <TabsPrimitive.Root
      data-slot="tabs"
      data-orientation={orientation}
      className={cn(
        // min-w-0: a Tabs that is a grid or flex item (the New base resume
        // dialog's body is a grid) otherwise takes its tab row's full label
        // width as its minimum, and the row widens the dialog instead of
        // scrolling inside itself (the list's max-w-full resolves against that).
        "group/tabs flex min-w-0 gap-2 data-horizontal:flex-col",
        className
      )}
      {...props}
    />
  )
}

// Tabs are one style: the line tabs of docs/design-system/components/Tabs. A 40px
// row with a hairline under it, labels in title-small, a 2px `primary` underline
// on the current tab. A two- or three-way view switch is a SegmentedToggle, not
// tabs; the filled pill strip that used to be the default is gone.
//
// The row is full width so the hairline spans its container, start-aligned
// (a section row is not a centred control), and has `p-0` and a definite height
// so each trigger fills it, and `shrink-0` so a tab row in a column that overflows
// (the chat scope picker, the template editor) is never squeezed under its panel. The row's horizontal bits are scoped to the
// horizontal orientation (`group-data-horizontal/tabs`).
//
// max-w-full + overflow-x-auto: a row wider than its container scrolls INSIDE
// itself instead of widening the page (the job page's Q&A tab ran off-screen at
// 375px, the five Settings tabs need ~480px, and the resume studios' seven tabs
// are ~590px in a fractional pane). A scroll container's min-width:auto is 0, so
// it also shrinks as a flex item. Base UI scrolls the focused tab into view on
// arrow keys (composite `scrollIntoViewIfNeeded`) and a click does the same
// (TabsTrigger below). The scrollbar is hidden: the cut-off last label is the
// cue, and keys and swipes reach it. A row never wraps: `overflow-x: auto`
// computes `overflow-y` to auto as well, so a wrapped row would clip its own
// second line.
// `relative` makes the row its triggers' offsetParent: Base UI measures a tab's
// offsetLeft up the offsetParent chain and stops at the scroller only if it is
// on that chain, so without it a dialog's padding was counted in and Home left
// the first tab 16px under the row's left edge.
// The underline sits INSIDE each trigger (`after:bottom-0`), not below it: the
// row scrolls, and `overflow-x: auto` clips whatever hangs outside its padding
// box. The trigger has no border of its own, so the underline lies directly on
// the row's hairline. For the same reason the focus ring is a 2px outline drawn
// inside the trigger (`-outline-offset-2`), not an outer halo.
// (`cn`, not a bare string: the vocabulary scan reads a class list as a class list only inside it.)
const TABS_LIST = cn(
  "group/tabs-list relative flex max-w-full items-center gap-1 bg-transparent p-0 text-muted-foreground group-data-horizontal/tabs:h-10 group-data-horizontal/tabs:w-full group-data-horizontal/tabs:shrink-0 group-data-horizontal/tabs:justify-start group-data-horizontal/tabs:overflow-x-auto group-data-horizontal/tabs:overscroll-x-contain group-data-horizontal/tabs:border-b group-data-horizontal/tabs:[scrollbar-width:none] group-data-horizontal/tabs:[&::-webkit-scrollbar]:hidden group-data-vertical/tabs:h-fit group-data-vertical/tabs:flex-col"
)

function TabsList({ className, ...props }: TabsPrimitive.List.Props) {
  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      className={cn(TABS_LIST, className)}
      {...props}
    />
  )
}

function TabsTrigger({ className, onClick, ...props }: TabsPrimitive.Tab.Props) {
  return (
    <TabsPrimitive.Tab
      data-slot="tabs-trigger"
      onClick={(event) => {
        // A click on a partly hidden tab brings it into view (the row scrolls, 7 tabs in a
        // narrow pane). `nearest` on both axes: no scroll at all when it is already visible.
        event.currentTarget.scrollIntoView({ inline: "nearest", block: "nearest" })
        onClick?.(event)
      }}
      className={cn(
        "relative inline-flex h-full flex-none items-center justify-center gap-1.5 rounded-corner-xs bg-transparent px-3 text-title-small whitespace-nowrap text-muted-foreground transition-colors group-data-vertical/tabs:w-full group-data-vertical/tabs:justify-start hover:text-foreground focus-visible:border-transparent focus-visible:ring-0 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-50 aria-disabled:pointer-events-none aria-disabled:opacity-50 data-active:text-foreground [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        "after:absolute after:rounded-full after:bg-primary after:opacity-0 after:transition-opacity group-data-horizontal/tabs:after:inset-x-3 group-data-horizontal/tabs:after:bottom-0 group-data-horizontal/tabs:after:h-0.5 group-data-vertical/tabs:after:inset-y-0 group-data-vertical/tabs:after:-right-1 group-data-vertical/tabs:after:w-0.5 data-active:after:opacity-100",
        className
      )}
      {...props}
    />
  )
}

function TabsContent({ className, keepMounted = true, ...props }: TabsPrimitive.Panel.Props) {
  return (
    <TabsPrimitive.Panel
      data-slot="tabs-content"
      // Every panel stays mounted (the Tabs README): a draft survives a switch, a deep link has
      // its target, and a leave guard registered inside a hidden panel keeps asking.
      keepMounted={keepMounted}
      className={cn(
        // Base UI makes the open panel a tab stop (APG). Its indicator is an
        // OVERLAY, not the panel's own outline: an element paints its outline
        // BEFORE its positioned and transformed descendants, so a `relative`
        // card or a finished `animate-fade-rise` (a fill-mode transform)
        // covered all but one edge of an inset outline. The ::after comes
        // last and sits on top (z-50); `isolate` keeps that z-index inside the
        // panel, so it never climbs over a sticky header outside it. It
        // reaches 4px past the panel so the ring does not touch the text at
        // the panel's edge; every call site has that room (browser-measured).
        // The panel's own outline is hidden, and never beside an outline-N:
        // outline-hidden zeroes --tw-outline-style, which outline-N reads.
        "relative isolate flex-1 text-body-medium focus-visible:outline-hidden",
        "focus-visible:after:pointer-events-none focus-visible:after:absolute focus-visible:after:-inset-1 focus-visible:after:z-50 focus-visible:after:rounded-corner-md focus-visible:after:border-2 focus-visible:after:border-ring",
        // A panel that scrolls ITSELF (the chat scope picker's) would carry an
        // absolute overlay away with its content, so it keeps a solid inset
        // outline instead; nothing positioned sits in those lists.
        "[&.overflow-y-auto]:focus-visible:after:hidden [&.overflow-y-auto]:focus-visible:outline-2 [&.overflow-y-auto]:focus-visible:outline-solid [&.overflow-y-auto]:focus-visible:-outline-offset-2 [&.overflow-y-auto]:focus-visible:outline-ring",
        // Hide de-selected panels. Base UI hides a panel by setting `hidden`
        // from its `mounted` state, and `mounted` is only cleared by
        // useOpenChangeComplete once the CLOSING transition finishes. These
        // panels have no transition, that callback never fires, so every panel
        // you visit stays behind with `hidden` unset: click through the tabs
        // and the page grows by one panel per click, all of them visible at
        // once. Analytics made it obvious (four chart panels stacked), but it
        // affected every tabbed surface in the app.
        //
        // `inert` is the attribute to key on: Base UI sets it as `!open`,
        // straight off the value comparison, so it is exactly "this is not the
        // selected panel" and never lags the way `mounted` does. It also
        // already carries the right semantics — an inert panel is out of the
        // tab order and the a11y tree, and now out of the layout too.
        "[&[inert]]:hidden",
        className
      )}
      {...props}
    />
  )
}

export { Tabs, TabsList, TabsTrigger, TabsContent }
