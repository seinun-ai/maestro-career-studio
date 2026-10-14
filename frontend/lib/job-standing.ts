// What the job page says first: the score pill and the "where this stands" line. Pure, so `node --test`
// loads it (no imports).

type ScoreRow = {
  phase: string;
  target_id: string;
  composite: number;
  application_id: string | null;
  created_at: string;
};

export type ScorePill = {
  /** "Resume match" for the application's tailored score, "Best base resume" for the best base score. */
  label: "Resume match" | "Best base resume";
  value: number;
  /** The base resume's id for a base score; the application's for a tailored one. */
  targetId: string;
  tailored: boolean;
};

/**
 * The header's one score. The application's newest tailored score when there is one ("Resume match N
 * (tailored)"), else the best base score ("Best base resume N"); null when neither exists.
 */
export function scorePill(scores: readonly ScoreRow[], applicationId: string | null): ScorePill | null {
  const tailored = applicationId
    ? scores
        .filter((s) => s.phase === "tailored" && s.application_id === applicationId)
        .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))[0]
    : undefined;
  if (tailored) {
    return { label: "Resume match", value: tailored.composite, targetId: tailored.target_id, tailored: true };
  }
  const best = scores.filter((s) => s.phase === "base").sort((a, b) => b.composite - a.composite)[0];
  return best ? { label: "Best base resume", value: best.composite, targetId: best.target_id, tailored: false } : null;
}
