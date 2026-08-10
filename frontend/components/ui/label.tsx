"use client"

import * as React from "react"

import { cn } from "@/lib/utils"

/**
 * `optional` renders the project's optionality convention (SYSTEM.md §8): a
 * muted " · optional" suffix on the LABEL, never a placeholder reading
 * "Optional" — a placeholder disappears the moment you type, which is exactly
 * when you would want to know the field can be left empty. It lives here so
 * the suffix has one definition; it was written out by hand in three places.
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
      {children}
      {optional && (
        <span className="text-muted-foreground font-normal">· optional</span>
      )}
    </label>
  )
}

export { Label }
