import { cn } from "@/lib/utils";

/**
 * The one KPI tile.
 *
 * There were three: `StatTile` in analytics-overview (`rounded-xl p-4`),
 * `MetricCard` in explore-overview (`rounded-md p-3`), and `Stat` in
 * base-summary-cards (no box, `text-sm` value) — so the four Analytics tabs
 * showed the same kind of number three different ways.
 *
 * The first two were the same component with a different radius and padding,
 * and they merge here. The third is genuinely a different job — an unboxed stat
 * INSIDE a card, where a second tonal box would be the nested-container problem
 * again — so it survives as `InlineStat` rather than being forced into a tile.
 * Two components, one type scale, no accidental third.
 */
export function StatTile({
  label,
  value,
  sub,
  className,
}: {
  label: string;
  value: string;
  sub?: string;
  className?: string;
}) {
  return (
    <div className={cn("bg-muted/40 rounded-xl p-4", className)}>
      <p className="text-muted-foreground text-xs">{label}</p>
      <p className="text-foreground mt-0.5 text-xl font-medium">{value}</p>
      {sub ? (
        <p className="text-muted-foreground mt-0.5 text-xs">{sub}</p>
      ) : null}
    </div>
  );
}

/**
 * A stat rendered inside an existing card — no box of its own, and a body-sized
 * value rather than the tile's display size, because it sits in a row of peers
 * rather than standing alone on the page.
 */
export function InlineStat({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div>
      <p className="text-muted-foreground text-xs">{label}</p>
      <p className="text-sm font-medium">{value}</p>
    </div>
  );
}
