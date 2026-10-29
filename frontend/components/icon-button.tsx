"use client";

import { useState, type ComponentProps, type ReactNode } from "react";
import { flushSync } from "react-dom";

import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

export interface IconButtonProps
  extends Omit<ComponentProps<typeof Button>, "children" | "size"> {
  label: string;
  icon: ReactNode;
  size?: "icon-xs" | "icon-sm" | "icon" | "icon-lg";
  side?: "top" | "bottom" | "left" | "right";
  /**
   * Its click leaves the page with a view transition (the job page's Back). The tooltip then neither closes on the
   * click nor answers hover after it, and goes with the page: Base UI settles both with a flushSync (the end of the
   * close animation, the browser's mouseleave as the transition starts), and a flushSync cancels a transition that
   * is still preparing.
   */
  transitionOnClick?: boolean;
}

/**
 * Ghost-by-default icon button with a tooltip wired in.
 * Use when the only label is the icon — never on a button that has visible text.
 */
export function IconButton({
  label,
  icon,
  size = "icon-sm",
  variant = "ghost",
  side = "top",
  transitionOnClick = false,
  ...buttonProps
}: IconButtonProps) {
  const [clicked, setClicked] = useState(false);
  return (
    <Tooltip>
      <TooltipTrigger
        disabled={clicked}
        closeOnClick={!transitionOnClick}
        onClick={transitionOnClick ? () => flushSync(() => setClicked(true)) : undefined}
        render={
          <Button
            size={size}
            variant={variant}
            aria-label={label}
            {...buttonProps}
          >
            {icon}
          </Button>
        }
      />
      <TooltipContent side={side}>{label}</TooltipContent>
    </Tooltip>
  );
}
