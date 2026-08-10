"use client"

import { Checkbox as CheckboxPrimitive } from "@base-ui/react/checkbox"
import { CheckIcon } from "lucide-react"

import { cn } from "@/lib/utils"

/**
 * The missing primitive.
 *
 * `components/ui/` shipped 20 of these and no checkbox, so every multi-select
 * surface reached for a bare `<input type="checkbox">` — nine of them, split
 * between `accent-primary` (Google blue) and `accent-foreground` (near-black),
 * two sizes and two baseline offsets. None of them got the app's focus ring
 * either: a native checkbox falls back to the UA outline, which is neither
 * `ring-3` nor `ring-ring/50`.
 *
 * Token usage mirrors Switch, which is the closest existing control, so a
 * checkbox and a switch in the same form finally agree on what "checked" and
 * "focused" look like.
 */
function Checkbox({
  className,
  ...props
}: CheckboxPrimitive.Root.Props) {
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      className={cn(
        "peer size-4 shrink-0 cursor-pointer rounded-[4px] border border-input bg-transparent transition-[color,box-shadow] outline-none",
        "data-checked:border-primary data-checked:bg-primary data-checked:text-primary-foreground",
        "focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50",
        "disabled:cursor-not-allowed disabled:opacity-50",
        "aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20",
        className
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator
        data-slot="checkbox-indicator"
        className="flex items-center justify-center text-current"
      >
        <CheckIcon className="size-3.5" />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  )
}

export { Checkbox }
