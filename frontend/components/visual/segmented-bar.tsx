import { segmentShares } from "@/lib/visual";
import { cn } from "@/lib/utils";

/** A status's role, a chart series for parts that are not a status (a work mode), or `empty` for a part with nothing
 * stated. A legend of statuses keys each part with a round dot (round means status); a legend with any series keys
 * every part with a short bar, the segment's own shape. */
export type SegmentTone =
  | "primary" | "muted" | "success" | "warning" | "attention" | "tertiary" | "error" | "empty"
  | "chart-1" | "chart-2" | "chart-3" | "chart-4" | "chart-5" | "chart-6";

const TONE: Record<SegmentTone, string> = {
  primary: "bg-primary",
  muted: "bg-muted-foreground",
  success: "bg-success",
  warning: "bg-warning",
  attention: "bg-attention",
  tertiary: "bg-tertiary",
  error: "bg-destructive",
  empty: "bg-transparent",
  "chart-1": "bg-chart-1",
  "chart-2": "bg-chart-2",
  "chart-3": "bg-chart-3",
  "chart-4": "bg-chart-4",
  "chart-5": "bg-chart-5",
  "chart-6": "bg-chart-6",
};

const isSeries = (tone: SegmentTone) => tone.startsWith("chart-");

/** A whole split into counted parts. The legend under the bar is the text; the bar itself is decoration. */
export function SegmentedBar({ name, parts, className }: {
  name: string;
  parts: { key: string; label: string; count: number; tone: SegmentTone }[];
  className?: string;
}) {
  const shares = segmentShares(parts);
  const series = parts.some((p) => isSeries(p.tone));
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <div className="flex h-2 gap-0.5 overflow-hidden rounded-full bg-surface-container" aria-hidden="true">
        {parts.map((p, i) =>
          shares[i].share > 0 ? (
            <span key={p.key} className={cn("h-full", TONE[p.tone])} style={{ width: `${shares[i].share}%` }} />
          ) : null,
        )}
      </div>
      <ul aria-label={name} className="legend flex flex-wrap gap-x-3 gap-y-1 text-body-small text-muted-foreground">
        {parts.map((p) => (
          <li key={p.key} className="inline-flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className={cn(
                "shrink-0",
                series ? "h-2 w-3 rounded-corner-2xs" : "size-2 rounded-full",
                TONE[p.tone],
                p.tone === "empty" && "border border-border",
              )}
            />
            {p.count} {p.label}
          </li>
        ))}
      </ul>
    </div>
  );
}
