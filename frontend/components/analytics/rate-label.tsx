import { rateWords } from "@/lib/rates";
import type { RateCount } from "@/lib/types";
import { cn } from "@/lib/utils";

/** A share from the search summary (owner decision D7): "19% (11–30%)" from 20 in its denominator, with the likely
 * range in brackets, and "5 of 12" below. Every Analytics share renders through this, so none reads a rate itself. */
export function RateLabel({ value, unit, className }: {
  value: RateCount;
  /** The denominator's noun, one and many: "5 of 12 replies". */
  unit?: readonly [string, string];
  className?: string;
}) {
  const words = rateWords(value, unit);
  return (
    <span className={cn("tabular-nums", className)}>
      {words.value}
      {words.range ? <span className="text-muted-foreground text-body-small"> ({words.range})</span> : null}
    </span>
  );
}
