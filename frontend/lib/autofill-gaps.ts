// The known-gaps line in Settings (backend services/autofill_gaps.py). Pure: `node --test` loads it.

export interface AutofillGapsSummary {
  kinds: number;
  sites: number;
  user_fixed: number;
  top: { family: string; shape: string; outcome: string; count: number; sites: number }[];
}

/** What a card says when the fill log has recorded nothing: the log is off unless the user turns
 *  it on in the Companion's options (extension/options.html). The same words as the Analytics
 *  coverage card's empty state (a backend test pins the two together). */
export const FILL_LOG_OFF_TEXT =
  "No data yet. The fill log is off unless you turn it on." +
  " To turn it on, right-click the Companion's toolbar icon, choose Options, and tick Keep a fill log.";

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** "Fields the Companion couldn't operate: 4 kinds on 3 sites, 2 fixed by you." Never a host. */
export function gapsLine(summary: AutofillGapsSummary): string {
  if (summary.kinds === 0) return FILL_LOG_OFF_TEXT;
  return (
    `Fields the Companion couldn't operate: ${plural(summary.kinds, "kind", "kinds")}`
    + ` on ${plural(summary.sites, "site", "sites")}, ${summary.user_fixed} fixed by you.`
  );
}
