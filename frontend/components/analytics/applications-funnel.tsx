"use client";

import { RateLabel } from "@/components/analytics/rate-label";
import { LeadCard } from "@/components/ui/lead-card";
import { NumberRoll } from "@/components/visual";
import { formatShortDate } from "@/lib/format-date";
import { rateWords } from "@/lib/rates";
import { funnelRows } from "@/lib/search-summary";
import type { SearchSummary } from "@/lib/types";

/** The window the numbers cover: "In the last 12 weeks", or "Since Aug 3" for All. */
export function windowLine(summary: SearchSummary): string {
  return summary.weeks === null
    ? `Since ${formatShortDate(summary.window_start)}`
    : `In the last ${summary.weeks} ${summary.weeks === 1 ? "week" : "weeks"}`;
}

/**
 * Analytics' Lead: where the applications sent in the period went. Each row is a count with its bar on Applied's
 * scale, and its share of the row above through RateLabel: a percent with its likely range from 20, "5 of 12"
 * below (owner decision D7). The two rules sit under the rows as chips.
 */
export function ApplicationsFunnel({ summary }: { summary: SearchSummary }) {
  const rows = funnelRows(summary);
  const anyRange = rows.some((row) => row.rate !== null && rateWords(row.rate).range !== null);
  return (
    <LeadCard eyebrow="Where your applications went">
      <p className="text-title-medium">{windowLine(summary)}</p>
      {summary.applied === 0 ? (
        <p className="text-muted-foreground text-body-medium">
          {summary.weeks === null ? "No applications sent yet." : "No applications sent in this period."}
        </p>
      ) : (
        <>
          <ol className="flex flex-col gap-3.5">
            {rows.map((row) => (
              <li
                key={row.key}
                className="grid grid-cols-[6.5rem_minmax(0,1fr)_3.5rem_minmax(8.5rem,auto)] items-center gap-x-4"
              >
                <span className="text-title-small">{row.label}</span>
                <span aria-hidden="true" className="h-6 overflow-hidden rounded-r-corner-xs bg-surface-container">
                  <span
                    className="block h-full rounded-r-corner-xs bg-chart-1"
                    style={{ width: `${row.share}%`, minWidth: row.count > 0 ? 6 : 0 }}
                  />
                </span>
                <NumberRoll value={row.count} className="justify-self-end text-title-large" />
                <span className="text-muted-foreground text-body-medium">
                  {row.rate && row.unit ? <RateLabel value={row.rate} unit={row.unit} /> : null}
                </span>
              </li>
            ))}
          </ol>
          <ul aria-label="How the rates read" className="flex flex-wrap gap-2">
            <li className="rounded-full bg-surface-container px-2.5 py-1 text-body-small text-muted-foreground">
              A rate shows from {summary.min_rate_n}
            </li>
            {anyRange ? (
              <li className="rounded-full bg-surface-container px-2.5 py-1 text-body-small text-muted-foreground">
                In brackets: the 95% likely range
              </li>
            ) : null}
          </ul>
        </>
      )}
    </LeadCard>
  );
}
