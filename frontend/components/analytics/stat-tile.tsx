import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * The one KPI tile.
 *
 * There were three: `StatTile` in analytics-overview (a 14px corner and `p-4`),
 * `MetricCard` in explore-overview (an 8px corner and `p-3`), and `Stat` in
 * base-summary-cards (no box, `text-title-small` value) — so the four Analytics tabs
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
  icon,
  children,
  className,
}: {
  label: string;
  value: string;
  sub?: string;
  /** A glyph that already means this tile's thing, beside the label. Decorative: the label names it. */
  icon?: ReactNode;
  /** A graphic under the sub line (a Sparkline); it carries its own accessible name. */
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("bg-surface-container-low rounded-corner-md p-4", className)}>
      <p className="text-body-small text-muted-foreground flex items-center gap-1.5">
        {icon}
        {label}
      </p>
      <p className="text-title-large text-foreground mt-0.5 font-medium">
        {value}
      </p>
      {sub ? (
        <p className="text-body-small text-muted-foreground mt-0.5">{sub}</p>
      ) : null}
      {children ? <div className="mt-2">{children}</div> : null}
    </div>
  );
}

/**
 * A stat rendered inside an existing card — no box of its own, and a title-small
 * value rather than the tile's title-large size, because it sits in a row of peers
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
      <p className="text-muted-foreground text-body-small">{label}</p>
      <p className="text-title-small">{value}</p>
    </div>
  );
}
