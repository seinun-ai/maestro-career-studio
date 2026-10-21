import { MIN_RATE_N } from "@/lib/rates";
import { MIN_REPLIES_FOR_TIMING, QUIET_AFTER_DAYS } from "@/lib/search-summary";
import type { SearchSummary } from "@/lib/types";

/** "How these are counted": what each number on Analytics means and how few is too few, in the server's own
 * numbers once the summary has loaded (`services/search_summary.py`, `services/rates.py`). */
export function HowCounted({ summary }: { summary: SearchSummary | undefined }) {
  const minRate = summary?.min_rate_n ?? MIN_RATE_N;
  const minReplies = summary?.min_replies_for_timing ?? MIN_REPLIES_FOR_TIMING;
  const quietDays = summary?.quiet.after_days ?? QUIET_AFTER_DAYS;
  const rows: [string, string][] = [
    ["Applied", "Applications you sent in the period, counted in the week you sent them. Weeks start on Monday."],
    ["Heard back", "Any word after you applied: a no, an interview or an offer. Its share is of the applications sent."],
    ["Interview", "Reached an interview or later. Its share is of the applications that heard back."],
    ["Offer", "Reached an offer. Its share is of the applications that reached an interview."],
    [
      "Rates",
      `A rate shows once the number it is a share of reaches ${minRate}; below that you see the counts, such as 5 of 12. The range in brackets is a 95% Wilson range: where the true rate likely is.`,
    ],
    [
      "Time to hear back",
      `Days from applying to the first reply, from replies with a recorded date. It shows from ${minReplies} of them: the median, and the days the middle half took.`,
    ],
    [
      `No reply after ${quietDays} days`,
      `Applications sent ${quietDays} or more days ago that have heard nothing since. Newer ones count neither way yet.`,
    ],
    ["By resume", "Each base resume's applications. There, heard back and interview are both shares of that resume's applications."],
    ["Score gain", "Your tailored resume's match score minus its base resume's, the median over the resumes tailored in the period."],
    ["Yours and Agents", "Split the applications by who sent them: you, or a connected agent."],
    [
      "Yearly pay",
      "Jobs that list a yearly pay, in your home currency. Pay posted in another currency is converted on the European Central Bank's daily rate and marked ≈. Missing pay is never estimated, and a role with too few jobs that list pay is hidden and counted.",
    ],
  ];
  return (
    <dl className="grid max-w-[65ch] gap-3 text-body-medium">
      {rows.map(([term, words]) => (
        <div key={term}>
          <dt className="text-title-small">{term}</dt>
          <dd className="text-muted-foreground">{words}</dd>
        </div>
      ))}
    </dl>
  );
}
