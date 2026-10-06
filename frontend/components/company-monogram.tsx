"use client";

import { cn } from "@/lib/utils";

/** A company's tint is identity, not state: the name hashes to one of four
 *  tones so a row stays recognisable at a glance. StatusChip is the only place
 *  a state is named and coloured, so the status containers (success, warning,
 *  attention, error) are not in this list: a monogram's tint is never read as a
 *  state, and the initial and the row's own chip say the state. Each tone holds
 *  AA on its own solid fill (the container pairs are pinned in
 *  test_frontend_color_roles.py, foreground on the ladder in
 *  test_frontend_design_tokens.py). The order is fixed because it is the
 *  hash's modulo: a company keeps its tone. The neutral tone is the ladder's
 *  highest step so it stays visible on a hovered row (dark rows hover to -high). */
const TONES = [
  "bg-primary-container text-on-primary-container",
  "bg-tertiary-container text-on-tertiary-container",
  "bg-secondary-container text-on-secondary-container",
  "bg-surface-container-highest text-foreground",
];

export function CompanyMonogram({
  name,
  className,
}: {
  name: string | null | undefined;
  className?: string;
}) {
  const label = (name ?? "").trim();
  const initial = label ? label[0].toUpperCase() : "?";
  let hash = 0;
  for (let i = 0; i < label.length; i += 1) {
    hash = (hash * 31 + label.charCodeAt(i)) | 0;
  }
  const tone = TONES[Math.abs(hash) % TONES.length];
  return (
    <span
      aria-hidden
      className={cn(
        "flex size-8 shrink-0 items-center justify-center rounded-full text-label-large",
        tone,
        className,
      )}
    >
      {initial}
    </span>
  );
}
