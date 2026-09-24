"use client"

import { Tabs as TabsPrimitive } from "@base-ui/react/tabs"
import { cva, type VariantProps } from "class-variance-authority"

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

const tabsListVariants = cva(
  // min-h-8, not h-8. A fixed height cannot contain a wrapped list: the three
  // call sites that wrap (both resume studios' section tabs, the KB import
  // drawer) add `h-auto flex-wrap`, but a plain `h-auto` does not override a
  // variant-prefixed `group-data-horizontal/tabs:h-8` — so the pill stayed 32px
  // while rows two and three spilled out below it and painted over the content
  // underneath. A minimum keeps single-row lists at exactly the same 32px and
  // lets a wrapped one grow to fit its own rows.
  //
  // max-w-full + overflow-x-auto: a row wider than its container scrolls INSIDE
  // itself instead of widening the page (the job page's Q&A tab ran off-screen at
  // 375px, and the five Settings tabs need ~480px). A scroll container's
  // min-width:auto is 0, so it also shrinks as a flex item. `justify-center-safe`,
  // not plain centring: centred content that overflows clips its START, which no
  // scroll can reach. Base UI scrolls the focused tab into view on arrow keys
  // (composite `scrollIntoViewIfNeeded`). The scrollbar is hidden: the cut-off
  // last label is the cue, and keys and swipes reach it.
  // Wrapping rows (`h-auto flex-wrap`: Analytics, Career history, both studios,
  // the KB import drawer) are NOT scrollers: `overflow-x: auto` computes
  // `overflow-y` to auto as well, so a wrapped row became a box clipping its own
  // second line. The scroll is scoped to `not-[.flex-wrap]`; scroll padding,
  // overscroll and the hidden scrollbar do nothing on a box that does not scroll.
  // `relative` makes the row its triggers' offsetParent: Base UI measures a
  // tab's offsetLeft up the offsetParent chain and stops at the scroller only
  // if it is on that chain, so without it a dialog's padding was counted in
  // and Home left the first tab 16px under the row's left edge.
  // `scroll-px-1` (4px, one more than the padding): a tab scrolled to an end
  // keeps the row's 3px around it, so its 3px focus ring is not cut off. At 3px
  // the scroll-into-view stopped a rounding pixel short of the end (1px of the
  // last Settings tab's ring was clipped at 375px).
  "group/tabs-list relative inline-flex w-fit max-w-full items-center justify-center-safe rounded-lg p-[3px] text-muted-foreground group-data-horizontal/tabs:min-h-8 group-data-horizontal/tabs:not-[.flex-wrap]:overflow-x-auto group-data-horizontal/tabs:scroll-px-1 group-data-horizontal/tabs:overscroll-x-contain group-data-horizontal/tabs:[scrollbar-width:none] group-data-horizontal/tabs:[&::-webkit-scrollbar]:hidden group-data-vertical/tabs:h-fit group-data-vertical/tabs:flex-col data-[variant=line]:rounded-none",
  {
    variants: {
      variant: {
        default: "bg-muted",
        // No call site uses `line`: its indicator (`after:bottom-[-5px]` on the
        // trigger) would be clipped by 2px by the scrolling row above.
        line: "gap-1 bg-transparent",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function TabsList({
  className,
  variant = "default",
  ...props
}: TabsPrimitive.List.Props & VariantProps<typeof tabsListVariants>) {
  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      data-variant={variant}
      className={cn(tabsListVariants({ variant }), className)}
      {...props}
    />
  )
}

function TabsTrigger({ className, ...props }: TabsPrimitive.Tab.Props) {
  return (
    <TabsPrimitive.Tab
      data-slot="tabs-trigger"
      className={cn(
        // `h-[calc(100%-1px)]` fills a one-line row. In a wrapping row (`flex-wrap`)
        // the percentage has no definite height to resolve against, and triggers
        // grew taller than their line and spilled over the content below; there
        // each trigger is its own height and the row grows to fit its lines.
        "group-[.flex-wrap]/tabs-list:h-auto",
        "relative inline-flex h-[calc(100%-1px)] flex-1 items-center justify-center gap-1.5 rounded-md border border-transparent px-1.5 py-0.5 text-sm font-medium whitespace-nowrap text-foreground/60 transition-all group-data-vertical/tabs:w-full group-data-vertical/tabs:justify-start hover:text-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-1 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-50 has-data-[icon=inline-end]:pr-1 has-data-[icon=inline-start]:pl-1 aria-disabled:pointer-events-none aria-disabled:opacity-50 dark:text-muted-foreground dark:hover:text-foreground group-data-[variant=default]/tabs-list:data-active:shadow-sm group-data-[variant=line]/tabs-list:data-active:shadow-none [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        "group-data-[variant=line]/tabs-list:bg-transparent group-data-[variant=line]/tabs-list:data-active:bg-transparent dark:group-data-[variant=line]/tabs-list:data-active:border-transparent dark:group-data-[variant=line]/tabs-list:data-active:bg-transparent",
        "data-active:bg-background data-active:text-foreground dark:data-active:border-input dark:data-active:bg-input/30 dark:data-active:text-foreground",
        "after:absolute after:bg-foreground after:opacity-0 after:transition-opacity group-data-horizontal/tabs:after:inset-x-0 group-data-horizontal/tabs:after:bottom-[-5px] group-data-horizontal/tabs:after:h-0.5 group-data-vertical/tabs:after:inset-y-0 group-data-vertical/tabs:after:-right-1 group-data-vertical/tabs:after:w-0.5 group-data-[variant=line]/tabs-list:data-active:after:opacity-100",
        className
      )}
      {...props}
    />
  )
}

function TabsContent({ className, ...props }: TabsPrimitive.Panel.Props) {
  return (
    <TabsPrimitive.Panel
      data-slot="tabs-content"
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
        "relative isolate flex-1 text-sm focus-visible:outline-hidden",
        "focus-visible:after:pointer-events-none focus-visible:after:absolute focus-visible:after:-inset-1 focus-visible:after:z-50 focus-visible:after:rounded-md focus-visible:after:border-2 focus-visible:after:border-ring",
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

export { Tabs, TabsList, TabsTrigger, TabsContent, tabsListVariants }
