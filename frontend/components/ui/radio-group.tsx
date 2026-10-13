"use client"

import { Radio as RadioPrimitive } from "@base-ui/react/radio"
import { RadioGroup as RadioGroupPrimitive } from "@base-ui/react/radio-group"

import { cn } from "@/lib/utils"

/** One choice from a few, every choice said in words. Arrow keys move the pick, as a native group does.
 *  A radio takes effect when it is picked, like a switch; use a Select once there are more than about five. */
function RadioGroup<Value>({ className, ...props }: RadioGroupPrimitive.Props<Value>) {
  return <RadioGroupPrimitive data-slot="radio-group" className={cn("grid gap-3", className)} {...props} />
}

/** The round control only. The caller wraps it and its text in a `<label>`, so the whole line is the target. */
function Radio({ className, ...props }: RadioPrimitive.Root.Props) {
  return (
    <RadioPrimitive.Root
      data-slot="radio"
      className={cn(
        "peer mt-0.5 flex size-4 shrink-0 cursor-pointer items-center justify-center rounded-full border border-input bg-transparent transition-[color,box-shadow] outline-none",
        "data-checked:border-primary",
        "focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50",
        "data-disabled:cursor-not-allowed data-disabled:opacity-50",
        className
      )}
      {...props}
    >
      <RadioPrimitive.Indicator data-slot="radio-indicator" className="size-2 rounded-full bg-primary" />
    </RadioPrimitive.Root>
  )
}

export { RadioGroup, Radio }
