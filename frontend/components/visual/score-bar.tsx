import { clampPct } from "@/lib/visual";
import { cn } from "@/lib/utils";

/** A value on a fixed scale, with the number beside it (an ATS score, skills covered). No thresholds, no warning colour (D4). */
export function ScoreBar({ value, max = 100, label, valueText, digits = 0, width = "w-12", className }: {
  value: number; max?: number; label: string; valueText?: string; digits?: number; width?: string; className?: string;
}) {
  const shown = valueText ?? value.toFixed(digits);
  return (
    <span className={cn("inline-flex min-w-0 items-center gap-2", className)}>
      <span role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={max} aria-valuenow={Math.min(max, Math.max(0, value))}
        aria-valuetext={shown}
        className={cn("h-1.5 shrink-0 overflow-hidden rounded-full bg-surface-container", width)}>
        <span className="block h-full rounded-full bg-primary transition-[width] duration-(--duration-medium2) ease-(--ease-standard)"
          style={{ width: `${clampPct(value, max)}%` }} />
      </span>
      <span className="text-label-medium tabular-nums" aria-hidden="true">{shown}</span>
    </span>
  );
}
