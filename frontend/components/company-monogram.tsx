"use client";

import { cn } from "@/lib/utils";

/** Deterministic tonal hue per company so rows stay recognizable at a glance. */
const TONES = [
  "bg-blue-600/10 text-blue-700 dark:bg-blue-400/15 dark:text-blue-300",
  "bg-violet-600/10 text-violet-700 dark:bg-violet-400/15 dark:text-violet-300",
  "bg-green-600/10 text-green-700 dark:bg-green-400/15 dark:text-green-300",
  "bg-amber-500/15 text-amber-700 dark:bg-amber-400/15 dark:text-amber-300",
  "bg-rose-600/10 text-rose-700 dark:bg-rose-400/15 dark:text-rose-300",
  "bg-cyan-600/10 text-cyan-700 dark:bg-cyan-400/15 dark:text-cyan-300",
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
        "flex size-8 shrink-0 items-center justify-center rounded-full text-sm font-medium",
        tone,
        className,
      )}
    >
      {initial}
    </span>
  );
}
