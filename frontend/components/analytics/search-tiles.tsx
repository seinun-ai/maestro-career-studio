"use client";

import { RateLabel } from "@/components/analytics/rate-label";
import { StatTile } from "@/components/analytics/stat-tile";
import { NumberRoll, Sparkline } from "@/components/visual";
import { useCountUp } from "@/hooks/use-count-up";
import { formatShortDate } from "@/lib/format-date";
import { showsRate } from "@/lib/rates";
import { timingTrack } from "@/lib/search-summary";
import type { SearchSummary } from "@/lib/types";
import { formatDelta } from "@/lib/visual";

/** A decimal that counts to its new value (the motion budget's `useCountUp`); a whole number rolls instead. */
function CountedDecimal({ value, signed = false }: { value: number; signed?: boolean }) {
  const shown = useCountUp(value);
  const digits = Number.isInteger(value) ? 0 : 1;
  return <span className="tabular-nums">{signed ? formatDelta(shown, digits).text : shown.toFixed(digits)}</span>;
}

const oneDecimal = (value: number) => (Number.isInteger(value) ? String(value) : value.toFixed(1));
const days = (n: number) => `${n} ${n === 1 ? "day" : "days"}`;

/** Analytics' Also tier, first row: applied per week, time to hear back, no reply after 30 days, score gain. */
export function SearchTiles({ summary }: { summary: SearchSummary }) {
  const weekly = summary.series.map((week) => week.applied);
  const since = formatShortDate(summary.window_start);
  const timing = summary.time_to_hear_back;
  const track = timingTrack(timing);
  const quiet = summary.quiet;
  const gain = summary.score_gain;
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <StatTile
        label="Applied per week"
        value={<CountedDecimal value={summary.applied_per_week} />}
        sub={summary.weeks === null ? `Average since ${since}` : `Average over ${summary.weeks} weeks`}
      >
        {weekly.length > 1 ? (
          <Sparkline values={weekly} width={96} height={28} label={`Applied each week: ${weekly.join(", ")}`} />
        ) : null}
      </StatTile>

      {track && timing.median_days !== null && timing.p25_days !== null && timing.p75_days !== null ? (
        <StatTile
          label="Time to hear back"
          value={
            <>
              <NumberRoll value={Math.round(timing.median_days)} />
              <span className="text-body-medium"> {Math.round(timing.median_days) === 1 ? "day" : "days"}</span>
            </>
          }
          sub={`Median of ${timing.replies} replies. Half took ${Math.round(timing.p25_days)} to ${days(Math.round(timing.p75_days))}.`}
        >
          <span aria-hidden="true" className="relative block h-1.5 rounded-full bg-surface-container">
            <span
              className="absolute inset-y-0 rounded-full bg-primary-container"
              style={{ left: `${track.from}%`, width: `${track.width}%` }}
            />
            <span className="absolute -top-0.75 h-3 w-0.75 rounded-full bg-primary" style={{ left: `${track.median}%` }} />
          </span>
        </StatTile>
      ) : (
        <StatTile
          label="Time to hear back"
          value={
            <>
              <NumberRoll value={timing.replies} />
              <span className="text-body-medium"> {timing.replies === 1 ? "reply" : "replies"} so far</span>
            </>
          }
          sub={`A typical time shows from ${summary.min_replies_for_timing} dated replies.`}
        />
      )}

      <StatTile
        label={`No reply after ${quiet.after_days} days`}
        value={<NumberRoll value={quiet.count} />}
        sub={
          quiet.of === 0 ? (
            `Nothing sent ${quiet.after_days} or more days ago yet.`
          ) : (
            <>
              <RateLabel value={quiet} unit={["application", "applications"]} />
              {showsRate(quiet) ? " of those" : ""} sent {quiet.after_days} or more days ago
            </>
          )
        }
      />

      {gain.n > 0 && gain.median !== null ? (
        <StatTile
          label="Score gain from tailoring"
          value={
            <>
              <CountedDecimal value={gain.median} signed />
              <span className="text-body-medium"> points</span>
            </>
          }
          sub={
            gain.median_base !== null && gain.median_tailored !== null
              ? `Median ${oneDecimal(gain.median_base)} → ${oneDecimal(gain.median_tailored)}, ${gain.n} tailored`
              : `${gain.n} tailored`
          }
        />
      ) : (
        <StatTile
          label="Score gain from tailoring"
          value="—"
          sub={summary.weeks === null ? "Nothing tailored yet" : "Nothing tailored in this period"}
        />
      )}
    </div>
  );
}
