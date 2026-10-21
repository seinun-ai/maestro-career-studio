import { outcomeWord, type RunOutcome } from "@/lib/agent-runs";
import { STRIP_DAYS, dayStrip, dayStripLabel } from "@/lib/day-strip";
import { cn } from "@/lib/utils";

const DOT: Record<RunOutcome, string> = { ok: "bg-success", partial: "bg-warning", failed: "bg-destructive" };
const ORDER: RunOutcome[] = ["ok", "partial", "failed"];
const EMPTY = "bg-surface-container-high";

/** What an automation's runs reported, one round dot per local day (round means status), oldest on
 * the left and today on the right: the day's worst outcome, or an empty dot for no report. Only
 * what the runs reported: Maestro schedules nothing, so an empty day is not a miss. The strip is one
 * `role="img"` sentence; the legend under it names each colour that appears, in words. */
export function DayStrip({ runs, today = new Date(), days = STRIP_DAYS, className }: {
  runs: readonly { finished_at: string; outcome: RunOutcome }[];
  today?: Date;
  days?: number;
  className?: string;
}) {
  const cells = dayStrip(runs, today, days);
  const shown = ORDER.filter((o) => cells.some((c) => c.outcome === o));
  const anyEmpty = cells.some((c) => c.outcome === null);
  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <div role="img" aria-label={dayStripLabel(cells)} className="flex items-center justify-between gap-1">
        {cells.map((c) => (
          <span key={c.day} className={cn("size-3.5 shrink-0 rounded-full", c.outcome ? DOT[c.outcome] : EMPTY)} />
        ))}
      </div>
      <div aria-hidden="true" className="flex justify-between text-body-small text-muted-foreground">
        {/* The oldest dot is today minus days - 1: a 14-day strip starts 13 days ago. */}
        <span>{`${days - 1} days ago`}</span>
        <span>today</span>
      </div>
      <ul aria-hidden="true" className="flex flex-wrap gap-x-4 gap-y-1 text-body-small text-muted-foreground">
        {shown.map((o) => (
          <li key={o} className="inline-flex items-center gap-1.5">
            <span className={cn("size-2 rounded-full", DOT[o])} />
            {outcomeWord(o)}
          </li>
        ))}
        {anyEmpty ? (
          <li className="inline-flex items-center gap-1.5">
            <span className={cn("size-2 rounded-full", EMPTY)} />
            No report
          </li>
        ) : null}
      </ul>
    </div>
  );
}
