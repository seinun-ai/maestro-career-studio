"use client";

import { cn } from "@/lib/utils";

/** A company's tint is identity, not state: the name hashes to one of six
 *  role containers so a row stays recognisable at a glance. The same hue
 *  carries a status elsewhere (a green monogram is not "accepted"), so a
 *  monogram's tint is never read as one; the initial and the row's own chip say
 *  the state. Every tone is a container pair, which holds AA on its own solid
 *  fill (pinned in test_frontend_color_roles.py and test_frontend_design_tokens.py),
 *  and the order is fixed because it is the hash's modulo: a company keeps its tone. */
const TONES = [
  "bg-primary-container text-on-primary-container",
  "bg-tertiary-container text-on-tertiary-container",
  "bg-success-container text-on-success-container",
  "bg-warning-container text-on-warning-container",
  "bg-attention-container text-on-attention-container",
  "bg-secondary-container text-on-secondary-container",
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
