"use client";

import type { ReactNode } from "react";
import Link from "next/link";

import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/** The one grid a card gallery lays out in. */
export function GalleryGrid({ children }: { children: ReactNode }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{children}</div>
  );
}

/**
 * A gallery card whose whole face opens `href` while an actions menu inside it
 * stays clickable.
 *
 * The layering is load-bearing, which is why it lives in exactly one place: an
 * `<a>` WRAPPING the card would contain the actions menu, and a `<button>`
 * inside an `<a>` is invalid HTML and steals the click. So the link is a
 * SIBLING that covers the card at z-10, and the actions sit at z-20 (see
 * `GalleryCardActions`).
 *
 * Omit `href` for a card that is not itself a link — e.g. one wrapped in a
 * `<button>` for selection, where the button owns the interaction.
 */
export function GalleryCard({
  href,
  ariaLabel,
  className,
  children,
}: {
  href?: string;
  /** Required with `href` — the link has no text of its own to name it. */
  ariaLabel?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    // `pt-0` is the image-first DEFAULT, not a universal: a card leading with a
    // preview runs it full-bleed. `Card` carries `py-4` plus a
    // `has-[>img:first-child]` rule meant to strip the top pad for exactly this
    // case, but that selector wants a BARE <img> as the first child — ours is
    // wrapped in PreviewThumbnail's aspect-ratio box, and on template cards the
    // default star sits before it. So the rule never fired and the image ended
    // up inset 16px at the top while running flush to both sides. Asserting
    // full-bleed here beats a fragile child selector.
    //
    // A TEXT-first consumer overrides it with `pt-4`: `career/entity-card.tsx`
    // has no preview and reuses this shell purely for the link layering below.
    <Card className={cn("relative pt-0", className)}>
      {href && (
        <Link
          href={href}
          aria-label={ariaLabel}
          className="focus-visible:ring-ring/50 absolute inset-0 z-10 rounded-xl focus-visible:ring-2 focus-visible:outline-none"
        />
      )}
      {children}
    </Card>
  );
}

/**
 * Lifts a card's actions above the stretched link so they remain clickable.
 * `ml-auto` pushes them to the end of whatever row they share, which is how the
 * menu costs no extra card height.
 */
export function GalleryCardActions({ children }: { children: ReactNode }) {
  return <div className="relative z-20 ml-auto shrink-0">{children}</div>;
}
