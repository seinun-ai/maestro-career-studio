import { segmentShares } from "@/lib/visual";
import { cn } from "@/lib/utils";

export type SegmentTone = "primary" | "muted" | "success" | "warning" | "attention" | "tertiary" | "error" | "empty";

const TONE: Record<SegmentTone, string> = {
  primary: "bg-primary",
  muted: "bg-muted-foreground",
  success: "bg-success",
  warning: "bg-warning",
  attention: "bg-attention",
  tertiary: "bg-tertiary",
  error: "bg-destructive",
  empty: "bg-transparent",
};

/** A whole split into counted parts. The legend under the bar is the text; the bar itself is decoration. */
export function SegmentedBar({ name, parts, className }: {
  name: string;
  parts: { key: string; label: string; count: number; tone: SegmentTone }[];
  className?: string;
}) {
  const shares = segmentShares(parts);
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
            <span aria-hidden="true" className={cn("size-2 shrink-0 rounded-full", TONE[p.tone], p.tone === "empty" && "border border-border")} />
            {p.count} {p.label}
          </li>
        ))}
      </ul>
    </div>
  );
}
