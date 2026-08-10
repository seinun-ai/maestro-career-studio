/**
 * What is left of the attention-zone layer: one chip, on the health report.
 *
 * The editors used to wash the summary and the first role's bullets in amber
 * under the legend "Highlighted zones are read first by a recruiter." That
 * claim was removed (2026-08-06, owner decision) because it is not one this
 * product can support. The rule behind it is a fixed positional heuristic, and
 * the reading research it gestured at is directional at best — the widely-cited
 * eye-tracking study is n=30, vendor-funded and not peer-reviewed. Asserting a
 * specific reader's behaviour as fact, in the editor, on every resume, was
 * claiming more than we know.
 *
 * The zones themselves are NOT gone, because they are not decoration: they
 * drive `severity()` (a weak bullet is `critical` in a hot zone, `minor`
 * outside) and `cost()`, which orders the health report's fix list. That is
 * scoring, and it belongs on the scoring surface — so the marker survives
 * exactly there, saying what it actually means: this finding is weighted
 * higher.
 */

/** Inline chip for a finding the health report weights above the others. */
export const ATTENTION_BADGE =
  "bg-amber-500/10 text-amber-700 dark:text-amber-400";

/** One label, so the chip and any future copy cannot drift apart. */
export const ATTENTION_BADGE_LABEL = "weighted higher";
