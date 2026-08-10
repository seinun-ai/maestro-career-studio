"use client";

import type { ComponentProps, ReactNode } from "react";

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
  ...buttonProps
}: IconButtonProps) {
  return (
    <Tooltip>
      <TooltipTrigger
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
