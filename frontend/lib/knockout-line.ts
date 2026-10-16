// How the knock-out scan shows on the job page: a banner only when it blocks, otherwise one line in
// the Job details card. Pure, so `node --test` loads it (no imports).

/** A conflict or a missing profile answer is the only news worth a banner. */
export function knockoutBanner(status: string): boolean {
  return status === "conflict" || status === "incomplete_profile";
}

export type KnockoutLineKind = "clear" | "unstated" | "not_run";

/**
 * The quiet line for a scan that blocks nothing. `clear` is any pass or warning (knockout.py), so the line
 * claims only that nothing conflicts. `notChecked`: the job lists pay or years the profile cannot answer,
 * which is not "no requirements listed".
 */
export function knockoutLine(status: string, notChecked: boolean): { kind: KnockoutLineKind; label: string } | null {
  if (knockoutBanner(status)) return null;
  if (status === "unstated" && notChecked) return { kind: "not_run", label: "Checks not run yet" };
  if (status === "clear") return { kind: "clear", label: "No knock-outs" };
  return { kind: "unstated", label: "No requirements listed" };
}

/**
 * The scan in a few words, for a summary line (the job page's step 1). The quiet statuses reuse the card's
 * line; the blocking ones name what the banner shows. `status` null: no scan at all.
 */
export function knockoutWords(status: string | null, notChecked: boolean): string {
  if (status == null) return "Requirements not checked";
  const line = knockoutLine(status, notChecked);
  if (line) return line.label;
  return status === "conflict" ? "A knock-out" : "An answer missing from your profile";
}
