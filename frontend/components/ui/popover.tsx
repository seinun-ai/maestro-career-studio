"use client"

import { Popover as PopoverPrimitive } from "@base-ui/react/popover"

import { cn } from "@/lib/utils"

/**
 * The floating-panel material: elevation, ring, radius, scroll behaviour and
 * the open/close transitions. Shared with `dropdown-menu.tsx`, which imports it
 * from here — a menu is this surface plus menu semantics, so the surface is the
 * more primitive of the two and owns the definition.
 *
 * It lives in one place because both files claim to look identical, and two
 * hand-copied ~1000-character class strings drift the first time one is
 * touched. Width and padding are NOT here: those are the parts that legitimately
 * differ (a menu matches its trigger's width and pads for rows; a popover is
 * sized by its content), so each file adds its own.
 */
export const POPUP_SURFACE =
  "z-50 max-h-(--available-height) min-w-32 origin-(--transform-origin) overflow-x-hidden overflow-y-auto rounded-lg bg-popover text-popover-foreground shadow-md ring-1 ring-foreground/10 duration-100 outline-none data-[side=bottom]:slide-in-from-top-2 data-[side=inline-end]:slide-in-from-left-2 data-[side=inline-start]:slide-in-from-right-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2 data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95 data-closed:animate-out data-closed:overflow-hidden data-closed:fade-out-0 data-closed:zoom-out-95"

/**
 * A non-modal popover surface.
 *
 * Same visual surface as `dropdown-menu.tsx` — deliberately, and now
 * structurally: both render `POPUP_SURFACE` above. The difference is semantic,
 * and it is the whole reason this exists: a Menu is `role="menu"` and its
 * children have to be menuitems. A panel whose contents are prose plus a button
 * plus a link is not a menu, and rendering it as one produces a menu with zero
 * menuitems — nothing for arrow keys to move between and an invalid tree for a
 * screen reader.
 *
 * Non-modal by default (Base UI's default): the page behind stays scrollable
 * and interactive, which is right for a status panel hanging off a toolbar.
 */
function Popover({ ...props }: PopoverPrimitive.Root.Props) {
  return <PopoverPrimitive.Root data-slot="popover" {...props} />
}

function PopoverTrigger({ ...props }: PopoverPrimitive.Trigger.Props) {
  return <PopoverPrimitive.Trigger data-slot="popover-trigger" {...props} />
}

function PopoverContent({
  align = "center",
  alignOffset = 0,
  side = "bottom",
  sideOffset = 4,
  className,
  ...props
}: PopoverPrimitive.Popup.Props &
  Pick<
    PopoverPrimitive.Positioner.Props,
    "align" | "alignOffset" | "side" | "sideOffset"
  >) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Positioner
        className="isolate z-50 outline-none"
        align={align}
        alignOffset={alignOffset}
        side={side}
        sideOffset={sideOffset}
      >
        {/* Adds only padding: no `w-(--anchor-width)`, because a popover is
            sized by its content rather than by its trigger. */}
        <PopoverPrimitive.Popup
          data-slot="popover-content"
          className={cn(POPUP_SURFACE, "p-3", className)}
          {...props}
        />
      </PopoverPrimitive.Positioner>
    </PopoverPrimitive.Portal>
  )
}

function PopoverTitle({ className, ...props }: PopoverPrimitive.Title.Props) {
  return (
    <PopoverPrimitive.Title
      data-slot="popover-title"
      className={cn("text-sm font-medium", className)}
      {...props}
    />
  )
}

function PopoverClose({ ...props }: PopoverPrimitive.Close.Props) {
  return <PopoverPrimitive.Close data-slot="popover-close" {...props} />
}

export { Popover, PopoverTrigger, PopoverContent, PopoverTitle, PopoverClose }
