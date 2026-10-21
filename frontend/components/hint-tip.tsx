"use client";

import { Info } from "lucide-react";
import { useId } from "react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

/**
 * The rest of a section's explanation, one hover or focus away (design refresh, Task 4.6): an Info button
 * beside a title or a label, its tooltip holding the sentence. The sentence is also the button's
 * description, so a screen reader hears it without the tooltip; pass `id` to let a field describe itself
 * with it too (`aria-describedby`). The gap page's "About these suggestions" is the same pattern.
 */
export function HintTip({ label, children, id, className }: {
  /** The button's name: "About notes". */
  label: string;
  children: string;
  id?: string;
  className?: string;
}) {
  const ownId = useId();
  const hintId = id ?? ownId;
  return (
    <>
      <Tooltip>
        <TooltipTrigger
          render={
            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              aria-label={label}
              aria-describedby={hintId}
              className={cn("text-muted-foreground", className)}
            >
              <Info className="size-3.5" aria-hidden="true" />
            </Button>
          }
        />
        <TooltipContent>{children}</TooltipContent>
      </Tooltip>
      <span id={hintId} hidden>
        {children}
      </span>
    </>
  );
}
