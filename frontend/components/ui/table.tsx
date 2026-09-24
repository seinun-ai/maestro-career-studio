"use client"

import * as React from "react"

import { cn } from "@/lib/utils"

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

function TableBody({ className, ...props }: React.ComponentProps<"tbody">) {
  return (
    <tbody
      data-slot="table-body"
      className={cn("[&_tr:last-child]:border-0", className)}
      {...props}
    />
  )
}

function TableFooter({ className, ...props }: React.ComponentProps<"tfoot">) {
  return (
    <tfoot
      data-slot="table-footer"
      className={cn(
        "border-t bg-muted/50 font-medium [&>tr]:last:border-b-0",
        className
      )}
      {...props}
    />
  )
}

function TableRow({ className, ...props }: React.ComponentProps<"tr">) {
  return (
    <tr
      data-slot="table-row"
      className={cn(
        "border-b transition-colors hover:bg-muted/50 has-aria-expanded:bg-muted/50 data-[state=selected]:bg-muted",
        className
      )}
      {...props}
    />
  )
}

// px-4, matching CardContent. At px-2 a table dropped into a Card started its
// first column 24px from the card edge while the CardTitle above it started at
// 16px — a visible stagger down the left edge (ats-compare-panel). 16px is the
// app's one horizontal content rhythm; standalone tables gain it too.
function TableHead({ className, ...props }: React.ComponentProps<"th">) {
  return (
    <th
      // Column header by default — every TableHead in this app sits in a
      // <thead> row. `scope` is what tells a screen reader which cells this
      // header names; a row header overrides it via props below.
      scope="col"
      data-slot="table-head"
      className={cn(
        "h-10 px-4 text-left align-middle font-medium whitespace-nowrap text-foreground [&:has([role=checkbox])]:pr-0",
        className
      )}
      {...props}
    />
  )
}

function TableCell({ className, ...props }: React.ComponentProps<"td">) {
  return (
    <td
      data-slot="table-cell"
      className={cn(
        "px-4 py-2 align-middle whitespace-nowrap [&:has([role=checkbox])]:pr-0",
        className
      )}
      {...props}
    />
  )
}

function TableCaption({
  className,
  ...props
}: React.ComponentProps<"caption">) {
  return (
    <caption
      data-slot="table-caption"
      className={cn("mt-4 text-sm text-muted-foreground", className)}
      {...props}
    />
  )
}

export {
  Table,
  TableHeader,
  TableBody,
  TableFooter,
  TableHead,
  TableRow,
  TableCell,
  TableCaption,
}
