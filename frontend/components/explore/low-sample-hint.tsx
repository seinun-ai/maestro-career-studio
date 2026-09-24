"use client";

import { cn } from "@/lib/utils";

export function lowSampleLabel(n: number, unit = "applications"): string {
  const noun = n === 1 ? unit.replace(/s$/, "") : unit;
  return `Based on only ${n} ${noun}`;
}

/** Muted "only N" badge. Renders nothing unless `lowSample` is set. */
export function LowSampleBadge({
  n,
  lowSample,
  unit = "applications",
  className,
}: {
  n: number;
  lowSample: boolean;
  unit?: string;
  className?: string;
}) {
  if (!lowSample) return null;
  return (
    <span
      className={cn(
        "text-muted-foreground text-[10px] font-medium tabular-nums",
        className,
      )}
      title={lowSampleLabel(n, unit)}
    >
      only {n}
    </span>
  );
}

export function LowSampleCaption({
  n,
  lowSample,
  unit = "applications",
}: {
  n: number;
  lowSample: boolean;
  unit?: string;
}) {
  if (!lowSample) return null;
  return (
    <p className="text-muted-foreground mb-2 text-xs">
      {lowSampleLabel(n, unit)}
    </p>
  );
}
