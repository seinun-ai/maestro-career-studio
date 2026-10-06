"use client";

import { Copy, CircleCheck } from "lucide-react";

import { IconButton, type IconButtonProps } from "@/components/icon-button";
import { useCopy } from "@/hooks/use-copy";

/** Copy with the confirmation in place: the icon turns to a CircleCheck (the done state) and a "Copied"
 *  chip rises from the button for a moment, and a screen reader hears "Copied". */
export function CopyButton({
  text,
  label = "Copy",
  ...rest
}: { text: string; label?: string } & Omit<IconButtonProps, "label" | "icon" | "onClick">) {
  const { copied, copy } = useCopy();
  return (
    <span className="relative inline-flex">
      <IconButton
        {...rest}
        label={copied ? "Copied" : label}
        icon={copied ? <CircleCheck /> : <Copy />}
        onClick={() => void copy(text)}
      />
      <span
        aria-hidden="true"
        data-show={copied || undefined}
        className="bg-foreground text-background pointer-events-none absolute -top-6 left-1/2 inline-flex h-5 -translate-x-1/2 translate-y-1 items-center gap-1 rounded-full px-2 text-label-small whitespace-nowrap opacity-0 transition-[opacity,transform] duration-(--duration-short3) ease-(--ease-spring) data-show:translate-y-0 data-show:opacity-100"
      >
        <CircleCheck className="size-3" />
        Copied
      </span>
      <span className="sr-only" aria-live="polite">
        {copied ? "Copied" : ""}
      </span>
    </span>
  );
}
