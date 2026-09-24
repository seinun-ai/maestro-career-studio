"use client"

import * as React from "react"

import { cn } from "@/lib/utils"

/**
 * `optional` renders the project's optionality convention
 * (docs/frontend-conventions.md, Form conventions): a muted "(optional)" on
 * the LABEL, GOV.UK's wording, never a placeholder. A placeholder disappears
 * the moment you type, which is exactly when you would want to know the field
 * can be left empty. It lives here so the marker has one definition; never
 * write it by hand. The label text and the marker are one inline run, so a
 * label that wraps keeps "(optional)" after its last word instead of pushing
 * it to the far edge as a separate flex item.
 */
function Label({
  className,
  optional = false,
  children,
  ...props
}: React.ComponentProps<"label"> & { optional?: boolean }) {
  return (
    <label
      data-slot="label"
      className={cn(
        "flex items-center gap-2 text-sm leading-none font-medium select-none group-data-[disabled=true]:pointer-events-none group-data-[disabled=true]:opacity-50 peer-disabled:cursor-not-allowed peer-disabled:opacity-50",
        className
      )}
      {...props}
    >
      {optional ? (
        <span>
          {children}{" "}
          <span className="text-muted-foreground font-normal">(optional)</span>
        </span>
      ) : (
        children
      )}
    </label>
  )
}

export { Label }
